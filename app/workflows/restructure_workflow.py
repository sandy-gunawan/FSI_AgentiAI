"""Use Case 4 — Loan Restructuring Advisor.

Communication architecture: EVALUATOR–OPTIMIZER (reflection loop).

    Proposer ──> [deterministic affordability check] ──> Evaluator
        ^                                                    │
        └──────────── feedback (revise) ────────────────────┘   (≤ MAX_ITERS)
    ──> Writer (final explanation)

The Proposer drafts a scheme; a deterministic policy check + an Evaluator agent
critique it; concrete feedback is looped back until the scheme is affordable or
the iteration cap is reached (then it is REFERred to a human officer). The
monthly installment is recomputed deterministically for auditability.
"""
from __future__ import annotations

from app.agents.restructure.agents import EVALUATOR_AGENT, PROPOSER_AGENT, WRITER_AGENT
from app.agents.shared.model_client import financing_session
from app.core.models import (
    Decision,
    ProposalCritique,
    RestructureOutcome,
    RestructureProposal,
    RestructureRequest,
)
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance import tech_log
from app.governance.rules_engine import debt_burden_ratio, monthly_installment
from app.tools.mcp_tools import credit_bureau_tool
from app.tools.rest_tools import get_existing_loans
from app.workflows import data_access as sor
from mock_services.policy import evaluate_restructure

MAX_ITERS = 3


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


async def run_restructure(
    request: RestructureRequest, request_id: str, on_event=None, via_apim: bool | None = None
) -> tuple[RestructureOutcome, dict]:
    """Iteratively propose → evaluate a restructuring scheme until affordable."""
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

    # ---- System-of-record facts (deterministic) ----
    cust = sor.customer(request.customer_id)
    credit = sor.credit_individual(request.customer_id)
    loan = sor.existing_loan(request.customer_id)
    income = cust["monthly_income_idr"]
    principal = loan.get("outstanding_principal_idr", 0)
    original_installment = loan.get("monthly_installment_idr", 0)
    other_debt = max(0, credit.get("monthly_debt_obligations_idr", 0) - original_installment)

    proposal: RestructureProposal | None = None
    critique: ProposalCritique | None = None
    iterations = 0

    async with financing_session(request_id, "restructure", via_apim) as (runner, cost):
        for i in range(1, MAX_ITERS + 1):
            iterations = i
            # ---- Proposer (optimizer) ----
            fb = "" if critique is None else (
                f" Umpan balik evaluator sebelumnya (WAJIB diperbaiki): {critique.feedback} "
                f"Isu: {critique.issues}.")
            _emit("proposer", "active",
                  f"🧩 **Proposer** (iterasi #{i}"
                  + (" — skema KONSERVATIF/konsesi minimal" if i == 1 else "")
                  + f") aktif · Tool: Loan Servicing `get_existing_loans` + "
                  f"Credit Bureau MCP. Menyusun skema untuk meringankan angsuran "
                  f"(saat ini {_rp(original_installment)}/bln).{(' ↺ merevisi.' if critique else '')}")
            async with credit_bureau_tool() as credit_tool:
                proposal = await runner.run(
                    step=f"propose#{i}", name="RestructureProposer", instructions=PROPOSER_AGENT,
                    response_format=RestructureProposal,
                    tools=[get_existing_loans, credit_tool],
                    prompt=(
                        f"customer_id={request.customer_id}. Alasan kesulitan: {request.hardship_reason}. "
                        f"Preferensi: {request.requested_relief or 'tidak ada'}. "
                        f"Pokok terutang {principal} IDR, angsuran saat ini {original_installment} IDR/bln, "
                        f"bunga saat ini {loan.get('annual_rate_pct')}% p.a., sisa tenor "
                        f"{loan.get('remaining_tenor_months')} bln, tunggakan "
                        f"{loan.get('days_past_due')} hari.{fb}"
                    ),
                )

            # ---- Deterministic recompute + affordability/policy gate ----
            # Round 1: the bank tries a CONSERVATIVE, minimal-concession scheme first
            # (small tenor extension, ≤1% rate cut, no grace). This mirrors real policy
            # and ensures genuinely distressed borrowers need a revision (≥2 iterations).
            if i == 1:
                cur_rate = float(loan.get("annual_rate_pct", proposal.new_rate_pct))
                proposal.new_tenor_months = min(proposal.new_tenor_months,
                                                int(loan.get("remaining_tenor_months", 12)) + 6)
                proposal.grace_period_months = 0
                proposal.new_rate_pct = max(proposal.new_rate_pct, round(cur_rate - 1.0, 2))
            eff_tenor = max(1, proposal.new_tenor_months - proposal.grace_period_months)
            new_installment = monthly_installment(principal, proposal.new_rate_pct, eff_tenor)
            proposal.principal_idr = principal
            proposal.new_installment_idr = new_installment
            new_dbr = debt_burden_ratio(income, other_debt, new_installment)
            gate = evaluate_restructure(
                new_dbr_ratio=new_dbr, new_installment_idr=new_installment,
                original_installment_idr=original_installment,
                new_tenor_months=proposal.new_tenor_months,
            )
            audit.record(request_id, "restructure", f"affordability#{i}", "policy-engine (OJK/BI)",
                         f"DBR_baru={new_dbr} angsuran_baru={new_installment} "
                         f"issues={gate['issues']}", decision="OK" if gate["affordable"] else "REVISE")
            _emit("proposer", "done",
                  f"🧩 **Proposer** #{i} selesai · usul: tenor {proposal.new_tenor_months} bln, "
                  f"bunga {proposal.new_rate_pct}%, grace {proposal.grace_period_months} bln → "
                  f"angsuran {_rp(new_installment)}/bln (DBR {new_dbr}).")

            # ---- Evaluator (critic) ----
            _emit("evaluator", "active",
                  f"🔎 **Evaluator** (iterasi #{i}) aktif · Tool: Policy MCP `evaluate_restructure`. "
                  f"Cek keterjangkauan (DBR ≤ {gate['max_dbr_ratio']}) & kebijakan.")
            critique = await runner.run(
                step=f"evaluate#{i}", name="RestructureEvaluator", instructions=EVALUATOR_AGENT,
                response_format=ProposalCritique,
                prompt=(
                    f"Proposal: tenor {proposal.new_tenor_months} bln, bunga {proposal.new_rate_pct}%, "
                    f"grace {proposal.grace_period_months} bln, angsuran baru {new_installment} IDR "
                    f"(sebelumnya {original_installment} IDR). Cek deterministik: "
                    f"affordable={gate['affordable']}, policy_ok={gate['policy_ok']}, "
                    f"DBR_baru={new_dbr} (batas {gate['max_dbr_ratio']}), issues={gate['issues']}."
                ),
            )
            # Enforce deterministic verdict onto the critique (governance).
            critique.affordability_ok = gate["affordable"]
            critique.policy_ok = gate["policy_ok"]
            critique.approved = gate["affordable"]
            critique.issues = critique.issues or gate["issues"]
            audit.record(request_id, "restructure", f"critique#{i}", "RestructureEvaluator",
                         f"approved={critique.approved} score={critique.score} "
                         f"{redact_pii(critique.feedback[:160])}",
                         decision="APPROVED" if critique.approved else "REVISE")
            _emit("evaluator", "done",
                  f"🔎 **Evaluator** #{i} selesai · {'✅ lolos' if critique.approved else '↺ perlu revisi'} "
                  f"· skor {critique.score:.0f}/100 · {critique.feedback[:140]}")

            if critique.approved:
                break

        # ---- Writer (final explanation) ----
        approved = bool(critique and critique.approved)
        decision = Decision.APPROVE if approved else Decision.REFER
        _emit("writer", "active",
              f"📝 **Penjelasan** aktif · menyusun keputusan akhir ({decision.value}).")
        explanation = await runner.run(
            step="explain", name="RestructureWriter", instructions=WRITER_AGENT,
            prompt=(
                f"Hasil: {decision.value} setelah {iterations} iterasi. "
                + (f"Skema disetujui: pokok {proposal.principal_idr} IDR, tenor "
                   f"{proposal.new_tenor_months} bln, bunga {proposal.new_rate_pct}%, grace "
                   f"{proposal.grace_period_months} bln, angsuran baru {proposal.new_installment_idr} IDR/bln "
                   f"(sebelumnya {original_installment} IDR)."
                   if approved else
                   "Skema belum memenuhi ambang keterjangkauan otomatis — diteruskan ke petugas kredit "
                   f"untuk keputusan manual. Usulan terbaik: angsuran {proposal.new_installment_idr} IDR/bln.")
            ),
        )
        outcome = RestructureOutcome(
            customer_id=request.customer_id,
            decision=decision,
            final_proposal=proposal if approved else proposal,
            iterations=iterations,
            explanation=explanation,
        )
        audit.record(request_id, "restructure", "final", "RestructureWriter",
                     redact_pii(explanation[:400]), decision=decision.value, tokens=cost.total_tokens)
        _emit("writer", "done",
              f"📝 **Penjelasan** selesai · Keputusan: {decision.value} "
              f"({iterations} iterasi propose→evaluate).")

    tech_log.save(request_id, runner.tech)
    return outcome, cost.summary()
