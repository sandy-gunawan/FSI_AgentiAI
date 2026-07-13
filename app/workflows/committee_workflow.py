"""Use Case 6 — Credit Committee.

Microsoft Agent Framework orchestration: GROUP CHAT.

    Case brief ─► [ Risk Optimist ⇄ Risk Skeptic ⇄ Compliance ] × N rounds
                                     (shared transcript)
                  ─► Chair (manager) synthesises ─► CommitteeDecision

Several agents debate in a shared conversation; a Chair moderates turn-taking and
declares the decision. A deterministic OJK/BI pre-screen is a hard guardrail: the
Chair may not approve through a hard policy breach.
"""
from __future__ import annotations

from app.agents.committee.agents import (
    CHAIR_AGENT,
    COMPLIANCE_OFFICER,
    RISK_OPTIMIST,
    RISK_SKEPTIC,
)
from app.agents.shared.model_client import financing_session
from app.core.models import CommitteeDecision, CommitteeRequest, CommitteeTurn, Decision
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance import tech_log
from app.governance.rules_engine import dscr as calc_dscr
from app.governance.rules_engine import loan_to_value, monthly_installment, sme_ratios
from app.workflows import data_access as sor
from mock_services.data import load
from mock_services.policy import evaluate_sme

ROUNDS = 2

# viz node id, display speaker, instructions
_DEBATERS = [
    ("optimist", "Risk Optimist", RISK_OPTIMIST),
    ("skeptic", "Risk Skeptic", RISK_SKEPTIC),
    ("compliance", "Compliance", COMPLIANCE_OFFICER),
]


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


async def run_committee(
    request: CommitteeRequest, request_id: str, on_event=None, via_apim: bool | None = None
) -> tuple[CommitteeDecision, dict]:
    """Run a moderated committee debate (group chat) over a borderline case."""
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

    # ---- System-of-record facts → case brief + deterministic pre-screen ----
    company = sor.company(request.company_id)
    credit = sor.credit_company(request.company_id)
    kyc = sor.kyc_company(request.company_id)
    statements = load("financials.json")[request.company_id]
    collateral = load("collateral.json").get(company.get("collateral_id"), {})
    ratios = sme_ratios(statements)
    grade = credit.get("risk_grade", "C")
    products = load("products.json")
    rate = products["base_rate_pct"] + products["risk_spread_by_grade"].get(grade, 4.5)
    installment = monthly_installment(request.requested_amount_idr, rate, request.tenor_months)
    dscr_val = calc_dscr(ratios.get("operating_cashflow_idr", 0), installment * 12)
    ltv = loan_to_value(request.requested_amount_idr, collateral.get("appraised_value_idr", 0))
    dte = ratios.get("debt_to_equity", 9.9)
    years_operating = max(0, __import__("datetime").date.today().year - company.get("established_year", 2020))

    pol = evaluate_sme(
        years_operating=years_operating, ltv_ratio=ltv, dscr=dscr_val,
        debt_to_equity=dte, credit_score=credit.get("credit_score", 0),
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
        f"Angsuran≈{installment} IDR/bln @ {rate:.1f}% p.a."
    )

    transcript: list[CommitteeTurn] = []

    async with financing_session(request_id, "committee", via_apim) as (runner, cost):
        _emit("chair", "active",
              f"⚖️ **Chair** membuka komite · menyusun ringkasan kasus & memimpin debat "
              f"{ROUNDS} ronde. Pra-skrining: {pol['decision']}.")
        _emit("chair", "done", f"⚖️ **Chair** membuka sidang. Ringkasan: {brief[:160]}")

        for rnd in range(1, ROUNDS + 1):
            for node, speaker, instructions in _DEBATERS:
                _emit(node, "active",
                      f"🗣️ **{speaker}** (ronde {rnd}) berbicara dalam group chat…")
                convo = "\n".join(f"- {t.speaker} ({t.stance}): {t.argument}" for t in transcript) or "(belum ada)"
                turn: CommitteeTurn = await runner.run(
                    step=f"turn:{node}#{rnd}", name=f"Committee:{speaker}",
                    instructions=instructions, response_format=CommitteeTurn,
                    prompt=(f"RINGKASAN KASUS:\n{brief}\n\nTRANSKRIP SEJAUH INI:\n{convo}\n\n"
                            f"Ronde {rnd}. Sampaikan giliran Anda."),
                )
                turn.speaker = speaker
                transcript.append(turn)
                audit.record(request_id, "committee", f"turn:{node}#{rnd}", f"Committee:{speaker}",
                             f"stance={turn.stance}: {redact_pii(turn.argument[:160])}")
                _emit(node, "done",
                      f"🗣️ **{speaker}** ({turn.stance}): {turn.argument[:140]}")

        # ---- Chair synthesises & decides (guardrail on hard policy breach) ----
        _emit("chair", "active", "⚖️ **Chair** menutup debat & menyusun keputusan komite…")
        convo = "\n".join(f"- {t.speaker} ({t.stance}): {t.argument}" for t in transcript)
        decision: CommitteeDecision = await runner.run(
            step="decision", name="CommitteeChair", instructions=CHAIR_AGENT,
            response_format=CommitteeDecision,
            prompt=(f"RINGKASAN KASUS:\n{brief}\n\nTRANSKRIP DEBAT:\n{convo}\n\n"
                    f"Pra-skrining deterministik: {pol['decision']} ({pol['reason']}). "
                    f"{'ADA pelanggaran kebijakan keras — TIDAK boleh APPROVE.' if hard_block else ''} "
                    f"Putuskan APPROVE/DECLINE/REFER."),
        )
        decision.company_id = request.company_id
        decision.rounds = ROUNDS
        decision.transcript = transcript
        if hard_block:
            decision.decision = Decision.DECLINE
        audit.record(request_id, "committee", "final", "CommitteeChair",
                     redact_pii(decision.summary[:400]), decision=decision.decision.value,
                     tokens=cost.total_tokens)
        _emit("chair", "done",
              f"⚖️ **Chair** memutuskan: **{decision.decision.value}** "
              f"(konsensus={decision.consensus}) · {decision.summary[:140]}")

    tech_log.save(request_id, runner.tech)
    return decision, cost.summary()
