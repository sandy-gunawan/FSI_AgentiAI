"""Use Case 7 — Complex Investigation.

Microsoft Agent Framework orchestration: MAGENTIC.

    Manager builds a Task Ledger (plan) ─► dispatch to specialist workers
        ▲                                        │  (kyc · transactions · credit · financials)
        └──── review progress + REPLAN ◄─────────┘
                       ─► Manager writes final dossier

Unlike a single-agent ReAct loop, a Manager coordinates a TEAM against a ledger
and can add steps (replan) when the objective isn't yet covered.
"""
from __future__ import annotations

from app.agents.magentic.agents import (
    MANAGER_DOSSIER,
    MANAGER_PLAN,
    MANAGER_REPLAN,
    WORKER_AGENT,
)
from app.agents.shared.model_client import financing_session
from app.core.models import LedgerStep, MagenticDossier, MagenticPlan, MagenticRequest
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance import tech_log
from app.tools.mcp_tools import credit_bureau_tool, kyc_aml_tool
from app.tools.rest_tools import (
    get_account_summary,
    get_existing_loans,
    get_monitoring_alerts,
    get_transactions,
)
from app.workflows import data_access as sor

MAX_REPLANS = 1

# assigned_to -> (viz node, tool note)
_WORKER_NODE = {
    "kyc": ("kyc", "KYC/AML MCP `screen_individual`"),
    "transactions": ("transactions", "Core Banking `get_transactions` + Monitoring `get_monitoring_alerts`"),
    "credit": ("credit", "Credit Bureau MCP `get_credit_report`"),
    "financials": ("financials", "Core Banking `get_account_summary` + Servicing `get_existing_loans`"),
}


async def _run_worker(runner, step: LedgerStep, subject_id: str, nik: str, objective: str):
    """Execute one ledger step with the specialist worker + right tools."""
    who = step.assigned_to
    base = (f"Subjek customer_id={subject_id} (NIK={nik}). Objektif investigasi: {objective}. "
            f"Tugas Anda: {step.task}.")
    if who == "kyc":
        async with kyc_aml_tool() as kyc_tool:
            return await runner.run(
                step=f"worker:kyc", name="Worker:KYC", instructions=WORKER_AGENT,
                tools=[kyc_tool], prompt=base + f" Panggil screen_individual dengan NIK={nik}.")
    if who == "credit":
        async with credit_bureau_tool() as credit_tool:
            return await runner.run(
                step="worker:credit", name="Worker:Credit", instructions=WORKER_AGENT,
                tools=[credit_tool], prompt=base)
    if who == "transactions":
        return await runner.run(
            step="worker:transactions", name="Worker:Transactions", instructions=WORKER_AGENT,
            tools=[get_transactions, get_monitoring_alerts], prompt=base)
    # financials (individual financial profile)
    return await runner.run(
        step="worker:financials", name="Worker:Financials", instructions=WORKER_AGENT,
        tools=[get_account_summary, get_existing_loans], prompt=base)


async def run_magentic(
    request: MagenticRequest, request_id: str, on_event=None
) -> tuple[MagenticDossier, dict]:
    """Manager-coordinated, ledger-driven investigation with bounded replanning."""
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
    valid = set(_WORKER_NODE.keys())

    async with financing_session(request_id, "magentic") as (runner, cost):
        # ---- Manager: build the task ledger (plan) ----
        _emit("manager", "active",
              f"🧠 **Manager (Magentic)** menyusun *task ledger* untuk: {request.objective[:110]}")
        plan: MagenticPlan = await runner.run(
            step="plan", name="MagenticManager", instructions=MANAGER_PLAN,
            response_format=MagenticPlan,
            prompt=(f"Subjek customer_id={request.subject_id}, nama={request.subject_name}, NIK={nik}. "
                    f"Objektif: {request.objective}. Susun rencana 3-5 langkah."),
        )
        steps = [s for s in plan.steps if s.assigned_to in valid][:5] or [
            LedgerStep(task="Skrining KYC/sanksi", assigned_to="kyc"),
            LedgerStep(task="Analisis transaksi & alert", assigned_to="transactions"),
            LedgerStep(task="Cek eksposur kredit", assigned_to="credit"),
        ]
        audit.record(request_id, "magentic", "plan", "MagenticManager",
                     f"{len(steps)} langkah: {[s.assigned_to for s in steps]}")
        _emit("manager", "done",
              f"🧠 **Manager** menetapkan {len(steps)} langkah: "
              + ", ".join(f"{s.assigned_to}" for s in steps))

        async def _execute(step_list, replans):
            for st in step_list:
                node, note = _WORKER_NODE[st.assigned_to]
                _emit(node, "active",
                      f"🔎 **Worker[{st.assigned_to}]** menjalankan: {st.task[:90]} · Tool: {note}.")
                finding = await _run_worker(runner, st, request.subject_id, nik, request.objective)
                st.finding = finding
                st.status = "done"
                audit.record(request_id, "magentic", f"worker:{st.assigned_to}", f"Worker:{st.assigned_to}",
                             redact_pii(finding[:200]))
                _emit(node, "done",
                      f"🔎 **Worker[{st.assigned_to}]** selesai · {finding[:140]}")

        await _execute(steps, 0)

        # ---- Manager: review progress + bounded replan ----
        replans = 0
        for _ in range(MAX_REPLANS):
            _emit("manager", "active", "🧠 **Manager** meninjau progres & mempertimbangkan replan…")
            findings_so_far = "\n".join(f"- [{s.assigned_to}] {s.task}: {s.finding}" for s in steps)
            more: MagenticPlan = await runner.run(
                step=f"replan#{replans + 1}", name="MagenticManager", instructions=MANAGER_REPLAN,
                response_format=MagenticPlan,
                prompt=(f"Objektif: {request.objective}. Temuan sejauh ini:\n{findings_so_far}\n\n"
                        f"Kembalikan langkah tambahan (kosong bila cukup)."),
            )
            extra = [s for s in more.steps if s.assigned_to in valid][:2]
            if not extra:
                _emit("manager", "done", "🧠 **Manager**: cakupan cukup, tidak perlu replan.")
                break
            replans += 1
            audit.record(request_id, "magentic", f"replan#{replans}", "MagenticManager",
                         f"+{len(extra)} langkah: {[s.assigned_to for s in extra]}")
            _emit("manager", "done",
                  f"🧠 **Manager** REPLAN (+{len(extra)} langkah): "
                  + ", ".join(s.assigned_to for s in extra))
            await _execute(extra, replans)
            steps.extend(extra)

        # ---- Manager: final dossier ----
        _emit("manager", "active", "🧠 **Manager** menyusun dosir investigasi final…")
        findings_all = "\n".join(f"- [{s.assigned_to}] {s.task}: {s.finding}" for s in steps)
        dossier: MagenticDossier = await runner.run(
            step="dossier", name="MagenticManager", instructions=MANAGER_DOSSIER,
            response_format=MagenticDossier,
            prompt=(f"Subjek {request.subject_name} ({request.subject_id}). Objektif: {request.objective}. "
                    f"Temuan seluruh langkah:\n{findings_all}\n\nSusun dosir final."),
        )
        dossier.subject_id = request.subject_id
        dossier.objective = request.objective
        dossier.steps = steps
        dossier.replans = replans
        audit.record(request_id, "magentic", "final", "MagenticManager",
                     redact_pii(dossier.summary[:400]), decision=dossier.risk_level.upper(),
                     tokens=cost.total_tokens)
        _emit("manager", "done",
              f"🧠 **Manager** selesai · risiko={dossier.risk_level} · {replans} replan · "
              f"{dossier.recommendation[:120]}")

    tech_log.save(request_id, runner.tech)
    return dossier, cost.summary()
