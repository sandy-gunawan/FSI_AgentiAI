"""Use Case 5 (v2) — AML / Fraud Investigation with **Foundry-hosted agents**.

Same ReAct-style autonomous investigation + human SAR gate as v1 ``run_aml_investigation``,
but the investigator and SAR writer are persistent Foundry agents. Deterministic
escalation (DTTOT sanctions ⇒ must file) stays in Python. For a self-contained demo the
human gate is auto-confirmed inline (v1's full case-store HITL lives on the v1 page).
Additive — v1 untouched. Returns a plain dict.
"""
from __future__ import annotations

import asyncio

from app.agents.shared.foundry_runner import foundry_session
from app.core.models import AmlInvestigationRequest
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.workflows import data_access as sor

_TYPOLOGY = {
    "structuring": ["structuring / smurfing"],
    "layering": ["layering"],
    "rapid_movement": ["rapid movement of funds"],
    "high_risk_jurisdiction": ["high-risk jurisdiction exposure"],
    "unusual_pattern": ["unusual transaction pattern"],
}


async def run_aml_foundry(
    request: AmlInvestigationRequest, request_id: str, on_event=None,
    via_apim: bool | None = None,
) -> tuple[dict, dict]:
    """Autonomous investigation + SAR drafting using Foundry agents. Returns (result, cost)."""
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

    cust = sor.customer(request.subject_id)
    nik = cust["nik"]
    kyc = sor.kyc_individual(nik)
    sanctioned = bool(kyc.get("dttot_sanctions_hit", False))

    typologies = _TYPOLOGY.get(request.alert_type, ["unusual transaction pattern"])
    evidence = [f"alert '{request.alert_type}': {request.alert_detail[:120]}"]
    if sanctioned:
        evidence.append("sanksi_DTTOT terkonfirmasi")

    with foundry_session(request_id, "aml", via_apim) as (runner, cost):
        def _call(step, name, agent_key, prompt):
            return asyncio.to_thread(runner.run, step=step, name=name, agent_key=agent_key, prompt=prompt)

        # ---- Phase A: autonomous investigation (Foundry, uses MCP+REST server-side) ----
        _emit("investigator", "active",
              f"🕵️ **Investigator (ReAct, agen Foundry)** memilih tool dinamis (KYC/AML, "
              f"Monitoring, Core Banking, Credit Bureau). Subjek={request.subject_id}, "
              f"alert={request.alert_type}.")
        investigation = await _call("investigate", "AmlInvestigator", "aml-investigator",
                                    f"Subjek investigasi: customer_id={request.subject_id}, "
                                    f"nama={request.subject_name}, NIK={nik}. Alert pemicu: "
                                    f"{request.alert_type} — {request.alert_detail}. "
                                    f"Konteks deterministik: sanksi_DTTOT={sanctioned}. "
                                    f"Selidiki secara mandiri dan rangkum temuan + rekomendasi SAR.")

        # ---- Deterministic escalation ----
        risk_level = "high" if sanctioned else ("medium" if request.alert_type in _TYPOLOGY else "low")
        file_sar = sanctioned or request.alert_type in ("structuring", "layering", "high_risk_jurisdiction")
        audit.record(request_id, "aml", "recommendation", "foundry:aml-investigator",
                     f"risk={risk_level} file_sar={file_sar} typologies={typologies}",
                     decision="FILE_SAR" if file_sar else "NO_SAR", tokens=cost.total_tokens)
        _emit("investigator", "done",
              f"🕵️ **Investigator** selesai · risiko={risk_level}, rekomendasi SAR="
              f"{'YA' if file_sar else 'TIDAK'} · tipologi={typologies}")

        # ---- Human SAR gate (auto-confirmed for this demo page) ----
        _emit("human", "active",
              "🧑‍⚖️ **Analis AML** (human-in-the-loop) — untuk demo v2, keputusan otomatis mengikuti "
              "rekomendasi deterministik.")
        action = "file" if file_sar else "dismiss"
        audit.record(request_id, "aml", "human_decision", "aml_analyst:auto-demo",
                     f"action={action}", decision=action.upper())
        _emit("human", "done", f"🧑‍⚖️ Keputusan analis (demo): **{action.upper()}**.")

        # ---- Phase B: SAR writer (Foundry) ----
        sar_narrative = None
        _emit("filing", "active",
              f"📄 **Pelaporan SAR** (agen Foundry) menyusun "
              f"{'laporan SAR/LTKM' if file_sar else 'penutupan kasus'}…")
        sar_narrative = await _call("filing", "SarWriter", "aml-sar-writer",
                                    f"Keputusan analis: {action.upper()}. Subjek {request.subject_name} "
                                    f"({request.subject_id}). Tipologi: {typologies}. Risiko: {risk_level}. "
                                    f"Bukti: {evidence}. "
                                    + ("Susun narasi SAR/LTKM untuk PPATK." if file_sar
                                       else "Susun ringkasan penutupan kasus (tanpa pelaporan)."))
        audit.record(request_id, "aml", "final", "foundry:aml-sar-writer",
                     redact_pii(sar_narrative[:400]),
                     decision="SAR_FILED" if file_sar else "DISMISSED", tokens=cost.total_tokens)
        _emit("filing", "done",
              f"📄 **Pelaporan SAR** selesai · "
              f"{'SAR/LTKM diterbitkan ke PPATK' if file_sar else 'kasus ditutup'}.")

    tech_log.save(request_id, runner.tech)
    result = {
        "subject_id": request.subject_id,
        "subject_name": request.subject_name,
        "risk_level": risk_level,
        "file_sar": file_sar,
        "typologies": typologies,
        "evidence": evidence,
        "investigation": investigation,
        "sar_narrative": sar_narrative,
    }
    return result, cost.summary()
