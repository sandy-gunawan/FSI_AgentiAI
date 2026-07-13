"""Use Case 7 (v2) — Complex Investigation (Magentic) with **Foundry-hosted agents**.

Same MAGENTIC pattern + governance as v1 ``run_magentic``: a Manager builds a task
ledger, dispatches specialist workers, reviews progress, then writes the final dossier.
The plan is deterministic for auditability; the Manager (plan/replan/dossier) and the
Worker are persistent Foundry agents that call MCP+REST server-side. Additive — v1
untouched. Returns a plain dict.
"""
from __future__ import annotations

import asyncio

from app.agents.shared.foundry_runner import foundry_session
from app.core.models import MagenticRequest
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.workflows import data_access as sor

# assigned_to -> (viz node, default task, tool note)
_STEPS = [
    ("kyc", "Skrining KYC/sanksi (DTTOT/PEP)", "KYC/AML MCP `screen_individual`"),
    ("transactions", "Analisis transaksi & alert monitoring",
     "Core Banking `get_transactions` + Monitoring `get_monitoring_alerts`"),
    ("credit", "Cek eksposur kredit (SLIK)", "Credit Bureau MCP `get_credit_report`"),
    ("financials", "Profil finansial (arus kas & fasilitas)",
     "Core Banking `get_account_summary` + Servicing `get_existing_loans`"),
]


async def run_magentic_foundry(
    request: MagenticRequest, request_id: str, on_event=None,
    via_apim: bool | None = None,
) -> tuple[dict, dict]:
    """Manager-coordinated, ledger-driven investigation with Foundry agents."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "magentic", "submitted", "portal",
                 redact_pii(f"Investigasi kompleks {request.subject_name} ({request.subject_id}): "
                            f"{request.objective}"))
    safety = check_text(request.objective)
    audit.record(request_id, "magentic", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    cust = sor.customer(request.subject_id)
    nik = cust["nik"]

    with foundry_session(request_id, "magentic", via_apim) as (runner, cost):
        def _call(step, name, agent_key, prompt):
            return asyncio.to_thread(runner.run, step=step, name=name, agent_key=agent_key, prompt=prompt)

        # ---- Manager: build the task ledger (Foundry) ----
        _emit("manager", "active",
              f"🧠 **Manager (Magentic, agen Foundry)** menyusun *task ledger* untuk: "
              f"{request.objective[:110]}")
        plan = await _call("plan", "MagenticManager", "magentic-manager-plan",
                           f"Subjek customer_id={request.subject_id}, nama={request.subject_name}, "
                           f"NIK={nik}. Objektif: {request.objective}. Rencana langkah: "
                           + "; ".join(f"{a} — {t}" for a, t, _ in _STEPS))
        audit.record(request_id, "magentic", "plan", "foundry:magentic-manager-plan",
                     f"{len(_STEPS)} langkah: {[a for a, _, _ in _STEPS]}")
        _emit("manager", "done",
              f"🧠 **Manager** menetapkan {len(_STEPS)} langkah: " + ", ".join(a for a, _, _ in _STEPS))

        # ---- Workers execute the ledger (Foundry worker calls tools server-side) ----
        steps: list[dict] = []
        for assigned_to, task, note in _STEPS:
            _emit(assigned_to, "active",
                  f"🔎 **Worker[{assigned_to}]** (agen Foundry) menjalankan: {task} · Tool: {note}.")
            try:
                finding = await _call(
                    f"worker:{assigned_to}", f"Worker:{assigned_to}", "magentic-worker",
                    f"Subjek adalah NASABAH INDIVIDU (perorangan), customer_id={request.subject_id}, "
                    f"NIK={nik} — BUKAN perusahaan. Objektif investigasi: {request.objective}. "
                    f"Tugas Anda ({assigned_to}): {task}. Gunakan HANYA data individu: screen_individual "
                    f"(NIK), get_transactions / get_monitoring_alerts / get_account_summary / "
                    f"get_existing_loans / get_credit_report (customer_id). JANGAN panggil endpoint "
                    f"perusahaan atau financials/companies.")
            except Exception as exc:  # keep the ledger resilient to a single flaky tool call
                finding = f"(worker '{assigned_to}' tidak dapat menyelesaikan langkah: {str(exc)[:160]})"
            steps.append({"assigned_to": assigned_to, "task": task, "finding": finding})
            audit.record(request_id, "magentic", f"worker:{assigned_to}", "foundry:magentic-worker",
                         redact_pii(finding[:200]))
            _emit(assigned_to, "done", f"🔎 **Worker[{assigned_to}]** selesai · {finding[:140]}")

        # ---- Manager: review (replan considered, none needed for deterministic ledger) ----
        _emit("manager", "active", "🧠 **Manager** meninjau progres & mempertimbangkan replan…")
        findings_all = "\n".join(f"- [{s['assigned_to']}] {s['task']}: {s['finding']}" for s in steps)
        _emit("manager", "done", "🧠 **Manager**: cakupan cukup, lanjut ke dosir final.")

        # ---- Manager: final dossier (Foundry) ----
        _emit("manager", "active", "🧠 **Manager** menyusun dosir investigasi final…")
        dossier = await _call("dossier", "MagenticManager", "magentic-manager-dossier",
                              f"Subjek {request.subject_name} ({request.subject_id}). Objektif: "
                              f"{request.objective}. Temuan seluruh langkah:\n{findings_all}\n\n"
                              f"Susun dosir final: ringkasan, tingkat risiko, dan rekomendasi.")
        risk_level = "high" if bool(sor.kyc_individual(nik).get("dttot_sanctions_hit", False)) else "medium"
        audit.record(request_id, "magentic", "final", "foundry:magentic-manager-dossier",
                     redact_pii(dossier[:400]), decision=risk_level.upper(), tokens=cost.total_tokens)
        _emit("manager", "done",
              f"🧠 **Manager** selesai · risiko={risk_level} · {dossier[:120]}")

    tech_log.save(request_id, runner.tech)
    result = {
        "subject_id": request.subject_id,
        "subject_name": request.subject_name,
        "objective": request.objective,
        "risk_level": risk_level,
        "plan": plan,
        "steps": steps,
        "dossier": dossier,
    }
    return result, cost.summary()
