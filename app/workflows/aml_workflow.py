"""Use Case 5 — AML / Fraud Investigation.

Communication architecture: ReAct (autonomous, dynamic tool use) + HUMAN SAR GATE.

    Phase A (investigate):
        Investigator ──(reason→act→observe loop, chooses tools)──> SARRecommendation
        (case persisted as PENDING_HUMAN)

    Phase B (resume, after a human AML analyst decides):
        SARDecision ──> SAR writer ──> SARFiling  (case COMPLETED)

A single Investigator agent decides which back-office tools to call based on what
it observes, unlike the fixed pipelines of the other use cases. A human analyst
confirms filing before a SAR/LTKM is issued.
"""
from __future__ import annotations

from app.agents.aml.agents import INVESTIGATOR_AGENT, SAR_WRITER_AGENT
from app.agents.shared.model_client import financing_session
from app.core.models import (
    AmlInvestigationRequest,
    Decision,
    SARDecision,
    SARFiling,
    SARRecommendation,
)
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance import tech_log
from app.tools.mcp_tools import credit_bureau_tool, kyc_aml_tool
from app.tools.rest_tools import get_monitoring_alerts, get_transactions
from app.workflows import data_access as sor
from app.workflows.case_store import get_case_store


async def run_aml_investigation(
    request: AmlInvestigationRequest, request_id: str, on_event=None, via_apim: bool | None = None
) -> tuple[SARRecommendation, dict]:
    """Phase A — autonomous ReAct investigation. Persists a PENDING case."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "aml", "submitted", "portal",
                 redact_pii(f"Alert '{request.alert_type}' pada {request.subject_name} "
                            f"({request.subject_id}): {request.alert_detail}"))

    safety = check_text(request.alert_detail)
    audit.record(request_id, "aml", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    # ---- System-of-record facts (deterministic escalation basis) ----
    cust = sor.customer(request.subject_id)
    nik = cust["nik"]
    kyc = sor.kyc_individual(nik)
    sanctioned = bool(kyc.get("dttot_sanctions_hit", False))

    async with financing_session(request_id, "aml", via_apim) as (runner, cost):
        _emit("investigator", "active",
              f"🕵️ **Investigator (ReAct)** aktif · memilih tool secara dinamis: KYC/AML MCP "
              f"`screen_individual`, Transaction Monitoring `get_monitoring_alerts`, Core Banking "
              f"`get_transactions`, Credit Bureau MCP. Subjek={request.subject_id}, alert="
              f"{request.alert_type}.")
        async with kyc_aml_tool() as kyc_tool, credit_bureau_tool() as credit_tool:
            recommendation: SARRecommendation = await runner.run(
                step="investigate", name="AmlInvestigator", instructions=INVESTIGATOR_AGENT,
                response_format=SARRecommendation,
                tools=[kyc_tool, credit_tool, get_monitoring_alerts, get_transactions],
                prompt=(
                    f"Subjek investigasi: customer_id={request.subject_id}, "
                    f"nama={request.subject_name}, NIK={nik}. "
                    f"Alert pemicu: {request.alert_type} — {request.alert_detail}. "
                    f"Selidiki secara mandiri dan susun rekomendasi SAR."
                ),
            )

        # ---- Deterministic escalation: DTTOT sanctions => must file ----
        recommendation.subject_id = request.subject_id
        if sanctioned:
            recommendation.risk_level = "high"
            recommendation.file_sar = True
            if "sanksi_DTTOT" not in recommendation.evidence:
                recommendation.evidence = list(recommendation.evidence) + ["sanksi_DTTOT terkonfirmasi"]
        audit.record(request_id, "aml", "recommendation", "AmlInvestigator",
                     f"risk={recommendation.risk_level} file_sar={recommendation.file_sar} "
                     f"typologies={recommendation.typologies}",
                     decision="FILE_SAR" if recommendation.file_sar else "NO_SAR",
                     tokens=cost.total_tokens)

        get_case_store().create_aml_pending(
            request_id=request_id, subject_id=request.subject_id,
            request=request.model_dump(), recommendation=recommendation.model_dump(mode="json"),
            tokens=cost.total_tokens,
        )
        audit.record(request_id, "aml", "await_human", "system",
                     "Menunggu keputusan analis AML (human-in-the-loop).",
                     decision="FILE_SAR" if recommendation.file_sar else "NO_SAR",
                     tokens=cost.total_tokens)
        _emit("investigator", "done",
              f"🕵️ **Investigator** selesai · risiko={recommendation.risk_level}, "
              f"rekomendasi SAR={'YA' if recommendation.file_sar else 'TIDAK'} · "
              f"tipologi={recommendation.typologies}")
        _emit("human", "waiting",
              "🧑‍⚖️ Menunggu keputusan **Analis AML** (human-in-the-loop) — file / dismiss / escalate.")

    tech_log.save(request_id, runner.tech)
    return recommendation, cost.summary()


async def resume_aml_with_decision(
    request_id: str, decision: SARDecision, on_event=None, via_apim: bool | None = None
) -> tuple[SARFiling | None, dict]:
    """Phase B — apply the human analyst's decision and issue the SAR filing."""
    store = get_case_store()
    case = store.get_aml(request_id)
    if case is None:
        raise KeyError(f"AML case {request_id} not found")

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    request = AmlInvestigationRequest(**case["request_json"])
    rec = SARRecommendation(**case["recommendation_json"])
    _emit("human", "active",
          f"🧑‍⚖️ **Analis AML** {decision.analyst_name} memutuskan: **{decision.action.upper()}**.")
    audit = get_audit_logger()
    audit.record(request_id, "aml", "human_decision", f"aml_analyst:{decision.analyst_name}",
                 f"action={decision.action} notes={redact_pii(decision.notes)[:200]}",
                 decision=decision.action.upper())

    # escalate: keep the case pending (senior review), no filing yet.
    if decision.action == "escalate":
        return None, {"status": "pending", "request_id": request_id}

    filed = decision.action == "file"
    final = Decision.APPROVE if filed else Decision.DECLINE

    async with financing_session(request_id, "aml", via_apim) as (runner, cost):
        _emit("filing", "active",
              f"📄 **Pelaporan SAR** aktif · menyusun {'laporan SAR/LTKM' if filed else 'penutupan kasus'} "
              f"untuk {request.subject_name}.")
        narrative = await runner.run(
            step="filing", name="SarWriter", instructions=SAR_WRITER_AGENT,
            prompt=(
                f"Keputusan analis: {decision.action.upper()}. Subjek {request.subject_name} "
                f"({request.subject_id}). Tipologi: {rec.typologies}. Risiko: {rec.risk_level}. "
                f"Bukti: {rec.evidence}. Catatan analis: {decision.notes or '-'}."
            ),
        )
        filing = SARFiling(
            subject_id=request.subject_id,
            filed=filed,
            decision=final,
            narrative=narrative,
            filed_by=decision.analyst_name,
        )
        store.complete_aml(request_id, decision.model_dump(), filing.model_dump(mode="json"),
                           cost.total_tokens)
        audit.record(request_id, "aml", "final", "SarWriter",
                     redact_pii(narrative[:400]),
                     decision="SAR_FILED" if filed else "DISMISSED", tokens=cost.total_tokens)
        _emit("filing", "done",
              f"📄 **Pelaporan SAR** selesai · {'SAR/LTKM diterbitkan ke PPATK' if filed else 'kasus ditutup'}.")
        _emit("human", "done", "🧑‍⚖️ Keputusan analis AML tercatat.")

    tech_log.save(request_id, tech_log.get(request_id) + runner.tech)
    return filing, cost.summary()
