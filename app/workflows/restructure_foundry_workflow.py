"""Use Case 4 (v2) — Loan Restructuring with **Foundry-hosted agents**.

Same EVALUATOR–OPTIMIZER (reflection) loop + governance as v1 ``run_restructure``:
propose → deterministic affordability/policy gate → evaluate → revise, until affordable
or the iteration cap is hit. The scheme numbers are computed deterministically for
auditability; Foundry agents supply the proposal rationale, critique, and final
explanation. Additive — v1 untouched. Returns a plain dict.
"""
from __future__ import annotations

import asyncio

from app.agents.shared.foundry_runner import foundry_session
from app.core.models import RestructureRequest
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance.rules_engine import debt_burden_ratio, monthly_installment
from app.workflows import data_access as sor
from mock_services.policy import evaluate_restructure

MAX_ITERS = 3


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


def _scheme(iteration: int, cur_rate: float, remaining_tenor: int) -> dict:
    """Deterministic relief scheme per iteration: progressively more generous."""
    if iteration == 1:  # conservative, minimal concession
        return {"new_tenor_months": remaining_tenor + 6, "new_rate_pct": round(cur_rate - 1.0, 2),
                "grace_period_months": 0}
    if iteration == 2:  # moderate relief
        return {"new_tenor_months": remaining_tenor + 24, "new_rate_pct": round(cur_rate - 3.0, 2),
                "grace_period_months": 3}
    return {"new_tenor_months": remaining_tenor + 36, "new_rate_pct": round(max(4.0, cur_rate - 4.0), 2),
            "grace_period_months": 6}


async def run_restructure_foundry(
    request: RestructureRequest, request_id: str, on_event=None,
    via_apim: bool | None = None,
) -> tuple[dict, dict]:
    """Iterative propose → evaluate with Foundry agents. Returns (result, cost)."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "restructure", "submitted", "portal",
                 redact_pii(f"{request.full_name} ({request.customer_id}) minta restrukturisasi — "
                            f"{request.hardship_reason}"))
    safety = check_text(f"{request.hardship_reason} {request.requested_relief or ''}")
    audit.record(request_id, "restructure", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    cust = sor.customer(request.customer_id)
    credit = sor.credit_individual(request.customer_id)
    loan = sor.existing_loan(request.customer_id)
    income = cust["monthly_income_idr"]
    principal = loan.get("outstanding_principal_idr", 0)
    original_installment = loan.get("monthly_installment_idr", 0)
    cur_rate = float(loan.get("annual_rate_pct", 12.0))
    remaining_tenor = int(loan.get("remaining_tenor_months", 12))
    other_debt = max(0, credit.get("monthly_debt_obligations_idr", 0) - original_installment)

    proposal: dict = {}
    critiques: list[str] = []
    iterations = 0
    approved = False

    with foundry_session(request_id, "restructure", via_apim) as (runner, cost):
        def _call(step, name, agent_key, prompt):
            return asyncio.to_thread(runner.run, step=step, name=name, agent_key=agent_key, prompt=prompt)

        for i in range(1, MAX_ITERS + 1):
            iterations = i
            fb = "" if not critiques else f" Umpan balik sebelumnya (WAJIB diperbaiki): {critiques[-1][:200]}"
            _emit("proposer", "active",
                  f"🧩 **Proposer** (agen Foundry, iterasi #{i}"
                  + (" — skema KONSERVATIF" if i == 1 else "") + ") menyusun skema keringanan…")
            scheme = _scheme(i, cur_rate, remaining_tenor)
            eff_tenor = max(1, scheme["new_tenor_months"] - scheme["grace_period_months"])
            new_installment = monthly_installment(principal, scheme["new_rate_pct"], eff_tenor)
            new_dbr = debt_burden_ratio(income, other_debt, new_installment)
            proposal = {**scheme, "principal_idr": principal, "new_installment_idr": new_installment,
                        "new_dbr": new_dbr}

            rationale = await _call(f"propose#{i}", "RestructureProposer", "restructure-proposer",
                                    f"customer_id={request.customer_id}. Alasan kesulitan: "
                                    f"{request.hardship_reason}. Preferensi: {request.requested_relief or '-'}. "
                                    f"Pokok {principal} IDR, angsuran saat ini {original_installment} IDR/bln, "
                                    f"bunga {cur_rate}% p.a., sisa tenor {remaining_tenor} bln. "
                                    f"Skema usulan: tenor {scheme['new_tenor_months']} bln, bunga "
                                    f"{scheme['new_rate_pct']}%, grace {scheme['grace_period_months']} bln → "
                                    f"angsuran baru {new_installment} IDR/bln (DBR {new_dbr}).{fb}")

            gate = evaluate_restructure(
                new_dbr_ratio=new_dbr, new_installment_idr=new_installment,
                original_installment_idr=original_installment,
                new_tenor_months=scheme["new_tenor_months"],
            )
            audit.record(request_id, "restructure", f"affordability#{i}", "policy-engine (OJK/BI)",
                         f"DBR_baru={new_dbr} angsuran_baru={new_installment} issues={gate['issues']}",
                         decision="OK" if gate["affordable"] else "REVISE")
            _emit("proposer", "done",
                  f"🧩 **Proposer** #{i} · tenor {scheme['new_tenor_months']} bln, bunga "
                  f"{scheme['new_rate_pct']}%, grace {scheme['grace_period_months']} bln → "
                  f"angsuran {_rp(new_installment)}/bln (DBR {new_dbr}). {rationale[:120]}")

            _emit("evaluator", "active",
                  f"🔎 **Evaluator** (agen Foundry, iterasi #{i}) cek keterjangkauan "
                  f"(DBR ≤ {gate['max_dbr_ratio']}) & kebijakan…")
            critique = await _call(f"evaluate#{i}", "RestructureEvaluator", "restructure-evaluator",
                                   f"Proposal: tenor {scheme['new_tenor_months']} bln, bunga "
                                   f"{scheme['new_rate_pct']}%, grace {scheme['grace_period_months']} bln, "
                                   f"angsuran baru {new_installment} IDR (sebelumnya {original_installment}). "
                                   f"Cek deterministik: affordable={gate['affordable']}, "
                                   f"policy_ok={gate['policy_ok']}, DBR_baru={new_dbr} "
                                   f"(batas {gate['max_dbr_ratio']}), issues={gate['issues']}.")
            critiques.append(critique)
            approved = bool(gate["affordable"])
            audit.record(request_id, "restructure", f"critique#{i}", "foundry:restructure-evaluator",
                         f"approved={approved} {redact_pii(critique[:160])}",
                         decision="APPROVED" if approved else "REVISE")
            _emit("evaluator", "done",
                  f"🔎 **Evaluator** #{i} · {'✅ lolos' if approved else '↺ perlu revisi'} · {critique[:130]}")
            if approved:
                break

        decision = "APPROVE" if approved else "REFER"
        _emit("writer", "active",
              f"📝 **Penjelasan** (agen Foundry) menyusun keputusan akhir ({decision})…")
        explanation = await _call("explain", "RestructureWriter", "restructure-writer",
                                  f"Hasil: {decision} setelah {iterations} iterasi. "
                                  + (f"Skema disetujui: pokok {principal} IDR, tenor "
                                     f"{proposal['new_tenor_months']} bln, bunga {proposal['new_rate_pct']}%, "
                                     f"grace {proposal['grace_period_months']} bln, angsuran baru "
                                     f"{proposal['new_installment_idr']} IDR/bln (sebelumnya "
                                     f"{original_installment} IDR)." if approved else
                                     "Skema belum memenuhi ambang keterjangkauan otomatis — diteruskan ke "
                                     f"petugas kredit. Usulan terbaik: angsuran "
                                     f"{proposal['new_installment_idr']} IDR/bln."))
        audit.record(request_id, "restructure", "final", "foundry:restructure-writer",
                     redact_pii(explanation[:400]), decision=decision, tokens=cost.total_tokens)
        _emit("writer", "done",
              f"📝 **Penjelasan** selesai · Keputusan: {decision} ({iterations} iterasi propose→evaluate).")

    tech_log.save(request_id, runner.tech)
    result = {
        "decision": decision,
        "iterations": iterations,
        "original_installment_idr": original_installment,
        "proposal": proposal,
        "critiques": critiques,
        "explanation": explanation,
    }
    return result, cost.summary()
