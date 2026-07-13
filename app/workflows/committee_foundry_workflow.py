"""Use Case 6 (v2) — Credit Committee with **Foundry-hosted agents**.

Same GROUP CHAT debate + governance as v1 ``run_committee``: optimist ⇄ skeptic ⇄
compliance debate over N rounds on a shared transcript, then the Chair synthesises.
The deterministic OJK/BI pre-screen is the hard guardrail (no APPROVE through a hard
policy breach). Each speaker is a persistent Foundry agent. Additive — v1 untouched.
Returns a plain dict.
"""
from __future__ import annotations

import asyncio
import datetime

from app.agents.shared.foundry_runner import foundry_session
from app.core.models import CommitteeRequest
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance.rules_engine import dscr as calc_dscr
from app.governance.rules_engine import loan_to_value, monthly_installment, sme_ratios
from app.workflows import data_access as sor
from mock_services.data import load
from mock_services.policy import evaluate_sme

ROUNDS = 2

# viz node, display speaker, foundry agent key, stance label
_DEBATERS = [
    ("optimist", "Risk Optimist", "committee-risk-optimist", "pro"),
    ("skeptic", "Risk Skeptic", "committee-risk-skeptic", "con"),
    ("compliance", "Compliance", "committee-compliance", "policy"),
]


async def run_committee_foundry(
    request: CommitteeRequest, request_id: str, on_event=None
) -> tuple[dict, dict]:
    """Moderated committee debate over a borderline case using Foundry agents."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "committee", "submitted", "portal",
                 redact_pii(f"{request.legal_name} ({request.company_id}) — komite kredit untuk "
                            f"{request.requested_amount_idr:,} IDR — {request.purpose}"))
    safety = check_text(request.purpose)
    audit.record(request_id, "committee", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    # ---- System-of-record facts + deterministic pre-screen ----
    company = sor.company(request.company_id)
    credit = sor.credit_company(request.company_id)
    kyc = sor.kyc_company(request.company_id)
    statements = load("financials.json")[request.company_id]
    collateral = load("collateral.json").get(company.get("collateral_id"), {})
    ratios = sme_ratios(statements)
    grade = credit.get("risk_grade", "C")
    products = load("products.json")
    rate = round(products["base_rate_pct"] + products["risk_spread_by_grade"].get(grade, 4.5), 2)
    installment = monthly_installment(request.requested_amount_idr, rate, request.tenor_months)
    dscr_val = calc_dscr(ratios.get("operating_cashflow_idr", 0), installment * 12)
    ltv = loan_to_value(request.requested_amount_idr, collateral.get("appraised_value_idr", 0))
    dte = ratios.get("debt_to_equity", 9.9)
    years_operating = max(0, datetime.date.today().year - company.get("established_year", 2020))

    pol = evaluate_sme(
        years_operating=years_operating, ltv_ratio=ltv, dscr=dscr_val, debt_to_equity=dte,
        credit_score=credit.get("credit_score", 0),
        sanctions_hit=bool(kyc.get("dttot_sanctions_hit", False)),
        ppatk_flag=bool(kyc.get("ppatk_flag", False)),
    )
    hard_block = pol["decision"] == "DECLINE"
    brief = (
        f"Perusahaan {request.legal_name} ({request.company_id}), sektor {company.get('sector')}, "
        f"berdiri {company.get('established_year')} ({years_operating} th). Fasilitas diminta "
        f"{request.requested_amount_idr} IDR, tenor {request.tenor_months} bln, tujuan {request.purpose}. "
        f"Metrik: LTV={ltv}, DSCR={dscr_val}, DER={dte}, skor kredit={credit.get('credit_score')}, "
        f"grade={grade}. Pra-skrining OJK/BI: {pol['decision']} ({pol['reason']}). "
        f"Angsuran≈{installment} IDR/bln @ {rate}% p.a."
    )

    transcript: list[dict] = []

    with foundry_session(request_id, "committee") as (runner, cost):
        def _call(step, name, agent_key, prompt):
            return asyncio.to_thread(runner.run, step=step, name=name, agent_key=agent_key, prompt=prompt)

        _emit("chair", "active",
              f"⚖️ **Chair (agen Foundry)** membuka komite · memimpin debat {ROUNDS} ronde. "
              f"Pra-skrining: {pol['decision']}.")
        _emit("chair", "done", f"⚖️ **Chair** membuka sidang. Ringkasan: {brief[:160]}")

        for rnd in range(1, ROUNDS + 1):
            for node, speaker, agent_key, stance in _DEBATERS:
                _emit(node, "active", f"🗣️ **{speaker}** (agen Foundry, ronde {rnd}) berbicara…")
                convo = "\n".join(f"- {t['speaker']} ({t['stance']}): {t['argument']}"
                                  for t in transcript) or "(belum ada)"
                argument = await _call(f"turn:{node}#{rnd}", f"Committee:{speaker}", agent_key,
                                       f"RINGKASAN KASUS:\n{brief}\n\nTRANSKRIP SEJAUH INI:\n{convo}\n\n"
                                       f"Ronde {rnd}. Sampaikan giliran Anda ({stance}).")
                transcript.append({"speaker": speaker, "stance": stance, "argument": argument})
                audit.record(request_id, "committee", f"turn:{node}#{rnd}", f"foundry:{agent_key}",
                             f"stance={stance}: {redact_pii(argument[:160])}")
                _emit(node, "done", f"🗣️ **{speaker}** ({stance}): {argument[:140]}")

        _emit("chair", "active", "⚖️ **Chair** menutup debat & menyusun keputusan komite…")
        convo = "\n".join(f"- {t['speaker']} ({t['stance']}): {t['argument']}" for t in transcript)
        summary = await _call("decision", "CommitteeChair", "committee-chair",
                              f"RINGKASAN KASUS:\n{brief}\n\nTRANSKRIP DEBAT:\n{convo}\n\n"
                              f"Pra-skrining deterministik: {pol['decision']} ({pol['reason']}). "
                              f"{'ADA pelanggaran kebijakan keras — TIDAK boleh APPROVE.' if hard_block else ''} "
                              f"Rangkum keputusan komite.")
        decision = "DECLINE" if hard_block else pol["decision"]
        consensus = not hard_block
        audit.record(request_id, "committee", "final", "foundry:committee-chair",
                     redact_pii(summary[:400]), decision=decision, tokens=cost.total_tokens)
        _emit("chair", "done",
              f"⚖️ **Chair** memutuskan: **{decision}** (konsensus={consensus}) · {summary[:140]}")

    tech_log.save(request_id, runner.tech)
    result = {
        "decision": decision,
        "reason": pol["reason"],
        "consensus": consensus,
        "rounds": ROUNDS,
        "metrics": {"ltv": ltv, "dscr": dscr_val, "debt_to_equity": dte,
                    "credit_score": credit.get("credit_score", 0)},
        "transcript": transcript,
        "summary": summary,
    }
    return result, cost.summary()
