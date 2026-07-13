"""Use Case 2 — SME / commercial financing underwriting.

Communication architecture: CONCURRENT "star" (hub-and-spoke) + HUMAN-IN-THE-LOOP.

    Phase A (analysis):
        Orchestrator ──fan-out──> [Financial] [Collateral] [AML/Fraud] [Market]
                     <──fan-in─── aggregate ──> UnderwritingRecommendation
        (case is persisted as PENDING_HUMAN)

    Phase B (resume, after a human loan officer decides):
        HumanDecision ──> Term Sheet agent ──> SMETermSheet  (case COMPLETED)

The pause between phases survives Streamlit reruns because the case state is
persisted in the CaseStore.
"""
from __future__ import annotations

import asyncio

from app.agents.shared.model_client import financing_session
from app.agents.sme.agents import (
    AML_FRAUD_AGENT,
    COLLATERAL_AGENT,
    FINANCIAL_ANALYST,
    MARKET_RISK_AGENT,
    ORCHESTRATOR,
    TERMSHEET_AGENT,
)
from app.core.models import (
    Decision,
    HumanDecision,
    SMEFinancingRequest,
    SMETermSheet,
    SpecialistFinding,
    UnderwritingRecommendation,
)
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance import tech_log
from app.governance.rules_engine import dscr as calc_dscr
from app.governance.rules_engine import loan_to_value, monthly_installment, sme_ratios
from app.tools.mcp_tools import kyc_aml_tool
from app.tools.rest_tools import get_collateral, get_financial_statements
from app.workflows import data_access as sor
from app.workflows.case_store import get_case_store
from mock_services.data import load
from mock_services.policy import evaluate_sme


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


FACILITY = "Kredit Investasi UKM (SME-TERM)"


async def run_sme_analysis(
    request: SMEFinancingRequest, request_id: str, on_event=None, via_apim: bool | None = None
) -> tuple[UnderwritingRecommendation, dict]:
    """Phase A — concurrent specialist analysis + aggregation. Persists PENDING case."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "sme", "submitted", "portal",
                 redact_pii(f"{request.legal_name} ({request.company_id}) mengajukan "
                            f"{request.requested_amount_idr:,} IDR — {request.purpose}"))

    safety = check_text(request.purpose)
    audit.record(request_id, "sme", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    # ---- System-of-record facts + deterministic metrics ----
    company = sor.company(request.company_id)
    credit = sor.credit_company(request.company_id)
    kyc = sor.kyc_company(request.company_id)
    statements = load("financials.json")[request.company_id]
    collateral = load("collateral.json").get(request.collateral_id or company.get("collateral_id"), {})

    ratios = sme_ratios(statements)
    grade = credit.get("risk_grade", "C")
    products = load("products.json")
    rate = products["base_rate_pct"] + products["risk_spread_by_grade"].get(grade, 4.5)
    installment = monthly_installment(request.requested_amount_idr, rate, request.tenor_months)
    annual_debt_service = installment * 12
    dscr_val = calc_dscr(ratios.get("operating_cashflow_idr", 0), annual_debt_service)
    ltv = loan_to_value(request.requested_amount_idr, collateral.get("appraised_value_idr", 0))
    dte = ratios.get("debt_to_equity", 9.9)
    years_operating = max(0, __import__("datetime").date.today().year - company.get("established_year", 2020))

    async with financing_session(request_id, "sme", via_apim) as (runner, cost):
        # ---- Concurrent fan-out to four specialists (the "star") ----
        _emit("orchestrator", "active",
              f"🧭 **Orchestrator** aktif · menyebar tugas ke 4 agen spesialis (PARALEL). "
              f"Masukan: company_id={request.company_id}, plafon={_rp(request.requested_amount_idr)}, "
              f"tenor={request.tenor_months} bln.")
        _emit("financial", "active",
              f"📊 **Analis Keuangan** aktif · Tool: Financials API `get_financial_statements`. "
              f"Masukan: company_id={request.company_id} (3 tahun laporan).")
        _emit("collateral", "active",
              f"🏠 **Penilai Agunan** aktif · Tool: Collateral API `get_collateral`. "
              f"Masukan: collateral_id={request.collateral_id or company.get('collateral_id')}, LTV_awal={ltv}.")
        _emit("aml", "active",
              f"🛡️ **AML/Fraud** aktif · Tool: KYC/AML MCP `screen_entity`. "
              f"Masukan: company_id={request.company_id} (cek DTTOT/PPATK/PEP).")
        _emit("market", "active",
              f"🌐 **Risiko Pasar** aktif · menilai sektor '{company.get('sector')}' (penalaran, tanpa tool).")

        async def run_financial() -> SpecialistFinding:
            return await runner.run(
                step="specialist:financial", name="FinancialAnalyst",
                instructions=FINANCIAL_ANALYST, response_format=SpecialistFinding,
                tools=[get_financial_statements],
                prompt=f"company_id={request.company_id}. Precomputed ratios: {ratios}.",
            )

        async def run_collateral() -> SpecialistFinding:
            return await runner.run(
                step="specialist:collateral", name="CollateralAgent",
                instructions=COLLATERAL_AGENT, response_format=SpecialistFinding,
                tools=[get_collateral],
                prompt=(f"collateral_id={request.collateral_id or company.get('collateral_id')}. "
                        f"Requested facility {request.requested_amount_idr} IDR. Precomputed LTV={ltv}."),
            )

        async def run_aml() -> SpecialistFinding:
            async with kyc_aml_tool() as kyc_tool:
                return await runner.run(
                    step="specialist:aml", name="AmlFraudAgent",
                    instructions=AML_FRAUD_AGENT, response_format=SpecialistFinding,
                    tools=[kyc_tool],
                    prompt=f"company_id={request.company_id}.",
                )

        async def run_market() -> SpecialistFinding:
            return await runner.run(
                step="specialist:market", name="MarketRiskAgent",
                instructions=MARKET_RISK_AGENT, response_format=SpecialistFinding,
                prompt=(f"Sector={company.get('sector')}, established {company.get('established_year')}, "
                        f"annual revenue {company.get('annual_revenue_idr')} IDR, facility "
                        f"{request.requested_amount_idr} IDR for: {request.purpose}."),
            )

        findings = list(await asyncio.gather(
            run_financial(), run_collateral(), run_aml(), run_market()
        ))
        _spec_nodes = ["financial", "collateral", "aml", "market"]
        for _i, _nid in enumerate(_spec_nodes):
            _f = findings[_i]
            _emit(_nid, "done",
                  f"{'📊🏠🛡️🌐'[_i]} **{_f.specialist}** selesai · skor={_f.score:.0f}/100, "
                  f"risiko={_f.risk_rating} · {_f.summary[:140]}")
        for f in findings:
            audit.record(request_id, "sme", f"finding:{f.specialist}", f"{f.specialist}Agent",
                         f"score={f.score} risk={f.risk_rating}: {redact_pii(f.summary[:200])}")

        # ---- Deterministic OJK/BI pre-screen (hard blocks enforced) ----
        pol = evaluate_sme(
            years_operating=years_operating, ltv_ratio=ltv, dscr=dscr_val,
            debt_to_equity=dte, credit_score=credit.get("credit_score", 0),
            sanctions_hit=bool(kyc.get("dttot_sanctions_hit", False)),
            ppatk_flag=bool(kyc.get("ppatk_flag", False)),
        )
        audit.record(request_id, "sme", "prescreen", "policy-engine (OJK/BI)",
                     f"LTV={ltv} DSCR={dscr_val} DER={dte} rules={pol['triggered_rules']}",
                     decision=pol["decision"])

        # ---- Aggregate (hub) ----
        _emit("aggregate", "active",
              f"🧮 **Underwriting** aktif · menggabungkan 4 temuan + pra-skrining Policy MCP "
              f"`evaluate_sme`. Metrik: LTV={ltv}, DSCR={dscr_val}, DER={dte}, "
              f"skor_kredit={credit.get('credit_score', 0)}. Pra-skrining: {pol['decision']}.")
        recommendation: UnderwritingRecommendation = await runner.run(
            step="aggregate", name="UnderwritingOrchestrator", instructions=ORCHESTRATOR,
            response_format=UnderwritingRecommendation,
            prompt=(
                f"company_id={request.company_id}, requested {request.requested_amount_idr} IDR, "
                f"tenor {request.tenor_months} months, indicative rate {rate:.1f}% p.a. "
                f"Metrics: LTV={ltv}, DSCR={dscr_val}, debt_to_equity={dte}, "
                f"credit_score={credit.get('credit_score')}. Deterministic pre-screen: {pol['decision']} "
                f"({pol['reason']}). Specialist findings: "
                + " | ".join(f"{f.specialist}: score {f.score}, {f.risk_rating}, {f.summary}" for f in findings)
            ),
        )
        # Enforce deterministic decision + real findings on the recommendation.
        recommendation.company_id = request.company_id
        recommendation.recommended_decision = Decision(pol["decision"])
        recommendation.findings = findings
        if not recommendation.recommended_amount_idr:
            recommendation.recommended_amount_idr = request.requested_amount_idr
        if not recommendation.recommended_rate_pct:
            recommendation.recommended_rate_pct = round(rate, 2)

        get_case_store().create_pending(
            request_id=request_id, company_id=request.company_id,
            request=request.model_dump(), recommendation=recommendation.model_dump(mode="json"),
            tokens=cost.total_tokens,
        )
        audit.record(request_id, "sme", "await_human", "system",
                     "Menunggu keputusan petugas kredit (human-in-the-loop).",
                     decision=recommendation.recommended_decision.value, tokens=cost.total_tokens)
        _emit("aggregate", "done",
              f"🧮 **Underwriting** selesai · rekomendasi={recommendation.recommended_decision.value}, "
              f"rating={recommendation.composite_risk_rating}, plafon={_rp(recommendation.recommended_amount_idr)}, "
              f"bunga={recommendation.recommended_rate_pct}% p.a.")
        _emit("orchestrator", "done", "🧭 **Orchestrator** selesai menggabungkan hasil.")
        _emit("human", "waiting",
              "🧑‍⚖️ Menunggu keputusan **Petugas Kredit** (human-in-the-loop) — approve / reject / minta info.")

    tech_log.save(request_id, runner.tech)
    return recommendation, cost.summary()


async def resume_sme_with_decision(
    request_id: str, human: HumanDecision, on_event=None, via_apim: bool | None = None
) -> tuple[SMETermSheet | None, dict]:
    """Phase B — apply the human loan officer's decision and issue a term sheet."""
    store = get_case_store()
    case = store.get(request_id)
    if case is None:
        raise KeyError(f"SME case {request_id} not found")

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    request = SMEFinancingRequest(**case["request_json"])
    rec = UnderwritingRecommendation(**case["recommendation_json"])
    _emit("human", "active",
          f"🧑‍⚖️ **Petugas Kredit** {human.officer_name} memutuskan: **{human.action.upper()}**.")
    audit = get_audit_logger()

    audit.record(request_id, "sme", "human_decision", f"loan_officer:{human.officer_name}",
                 f"action={human.action} notes={redact_pii(human.notes)[:200]}",
                 decision=human.action.upper())

    # request_info: keep the case pending, no term sheet yet.
    if human.action == "request_info":
        return None, {"status": "pending", "request_id": request_id}

    decision = Decision.APPROVE if human.action == "approve" else Decision.DECLINE
    amount = human.adjusted_amount_idr or rec.recommended_amount_idr
    rate = human.adjusted_rate_pct or rec.recommended_rate_pct

    async with financing_session(request_id, "sme", via_apim) as (runner, cost):
        _emit("termsheet", "active",
              f"📄 **Term Sheet** aktif · menyusun term sheet ({human.action}) untuk {request.legal_name}.")
        summary = await runner.run(
            step="termsheet", name="TermSheetAgent", instructions=TERMSHEET_AGENT,
            prompt=(
                f"Keputusan petugas: {human.action.upper()}. Perusahaan {request.legal_name}. "
                + (f"Fasilitas {amount} IDR, tenor {request.tenor_months} bulan, bunga {rate}% p.a. "
                   f"Syarat: {', '.join(rec.conditions) if rec.conditions else 'standar'}."
                   if decision == Decision.APPROVE else "Pengajuan ditolak.")
                + f" Catatan petugas: {human.notes or '-'}."
            ),
        )

        termsheet = SMETermSheet(
            company_id=request.company_id,
            legal_name=request.legal_name,
            facility_type=FACILITY,
            approved_amount_idr=amount if decision == Decision.APPROVE else 0,
            tenor_months=request.tenor_months,
            annual_rate_pct=rate if decision == Decision.APPROVE else 0.0,
            conditions=rec.conditions,
            approved_by=human.officer_name,
            decision=decision,
        )
        store.complete(request_id, human.model_dump(), termsheet.model_dump(mode="json"), cost.total_tokens)
        audit.record(request_id, "sme", "final", "TermSheetAgent",
                     redact_pii(summary[:400]), decision=decision.value, tokens=cost.total_tokens)
        _emit("termsheet", "done",
              f"📄 **Term Sheet** selesai · Keputusan: {decision.value}."
              + (f" Plafon={_rp(amount)}, bunga={rate}% p.a., tenor={request.tenor_months} bln."
                 if decision == Decision.APPROVE else " (ditolak)."))
        _emit("human", "done", "🧑‍⚖️ Keputusan petugas kredit tercatat.")

    tech_log.save(request_id, tech_log.get(request_id) + runner.tech)
    return termsheet, cost.summary()
