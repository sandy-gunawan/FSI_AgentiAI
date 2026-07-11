"""Use Case 3 — Smart Customer Servicing.

Communication architecture: ROUTING.

    ServiceRequest ──> Router (classify intent) ──┬─> Dispute handler
                                                   ├─> Limit-increase handler
                                                   ├─> Hardship handler
                                                   ├─> Balance handler
                                                   └─> General handler

A single Router agent picks ONE downstream specialist based on the message; only
that handler runs. Every step is audited and token-budget tracked.
"""
from __future__ import annotations

from app.agents.servicing.agents import (
    BALANCE_AGENT,
    DISPUTE_AGENT,
    GENERAL_AGENT,
    HARDSHIP_AGENT,
    LIMIT_INCREASE_AGENT,
    ROUTER_AGENT,
)
from app.agents.shared.model_client import financing_session
from app.core.models import RoutingDecision, ServiceRequest, ServiceResolution
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance import tech_log
from app.tools.mcp_tools import credit_bureau_tool
from app.tools.rest_tools import get_account_summary, get_existing_loans, get_transactions

# intent -> (viz node id, agent display name, instructions)
_HANDLERS = {
    "dispute": ("dispute", "DisputeHandler", DISPUTE_AGENT),
    "limit_increase": ("limit", "LimitIncreaseHandler", LIMIT_INCREASE_AGENT),
    "hardship": ("hardship", "HardshipHandler", HARDSHIP_AGENT),
    "balance_inquiry": ("balance", "BalanceHandler", BALANCE_AGENT),
    "general": ("general", "GeneralHandler", GENERAL_AGENT),
}


async def run_servicing(
    request: ServiceRequest, request_id: str, on_event=None
) -> tuple[ServiceResolution, RoutingDecision, dict]:
    """Route one customer message to the right handler and resolve it."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "servicing", "submitted", "portal",
                 redact_pii(f"{request.full_name} ({request.channel}): {request.message}"))

    # ---- Governance: content safety on the free-text message ----
    safety = check_text(request.message)
    audit.record(request_id, "servicing", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    async with financing_session(request_id, "servicing") as (runner, cost):
        # ---- Stage 1: Router classifies the intent ----
        _emit("router", "active",
              f"🧭 **Router** aktif · mengklasifikasikan pesan nasabah menjadi 1 intent. "
              f"Masukan: \"{request.message[:120]}\".")
        routing: RoutingDecision = await runner.run(
            step="route", name="ServicingRouter", instructions=ROUTER_AGENT,
            response_format=RoutingDecision,
            prompt=(f"customer_id={request.customer_id}, channel={request.channel}. "
                    f"Pesan nasabah: \"{request.message}\"."),
        )
        audit.record(request_id, "servicing", "route", "ServicingRouter",
                     f"intent={routing.intent} confidence={routing.confidence}",
                     decision=routing.intent.upper())

        node, name, instructions = _HANDLERS.get(routing.intent, _HANDLERS["general"])
        _emit("router", "done",
              f"🧭 **Router** selesai · intent=**{routing.intent}** "
              f"(keyakinan {routing.confidence:.0%}) · {routing.rationale}")

        # ---- Stage 2: the single routed handler resolves the request ----
        tool_note = {
            "dispute": "Core Banking `get_transactions`",
            "limit": "Core Banking `get_account_summary` + Credit Bureau MCP `get_credit_report`",
            "hardship": "Loan Servicing `get_existing_loans`",
            "balance": "Core Banking `get_account_summary`",
            "general": "tanpa tool (penalaran)",
        }[node]
        _emit(node, "active",
              f"📌 **{name}** aktif · menangani intent '{routing.intent}'. Tool: {tool_note}.")

        if routing.intent == "dispute":
            resolution: ServiceResolution = await runner.run(
                step=f"handle:{routing.intent}", name=name, instructions=instructions,
                response_format=ServiceResolution, tools=[get_transactions],
                prompt=(f"customer_id={request.customer_id}. Keluhan: \"{request.message}\". "
                        f"Periksa mutasi dan buka kasus sengketa."),
            )
        elif routing.intent == "limit_increase":
            async with credit_bureau_tool() as credit_tool:
                resolution = await runner.run(
                    step=f"handle:{routing.intent}", name=name, instructions=instructions,
                    response_format=ServiceResolution,
                    tools=[get_account_summary, credit_tool],
                    prompt=(f"customer_id={request.customer_id}. Permintaan: \"{request.message}\". "
                            f"Nilai kelayakan kenaikan limit dari arus kas & SLIK."),
                )
        elif routing.intent == "hardship":
            resolution = await runner.run(
                step=f"handle:{routing.intent}", name=name, instructions=instructions,
                response_format=ServiceResolution, tools=[get_existing_loans],
                prompt=(f"customer_id={request.customer_id}. Laporan kesulitan: \"{request.message}\". "
                        f"Konfirmasi fasilitas berjalan & arahkan ke restrukturisasi."),
            )
        elif routing.intent == "balance_inquiry":
            resolution = await runner.run(
                step=f"handle:{routing.intent}", name=name, instructions=instructions,
                response_format=ServiceResolution, tools=[get_account_summary],
                prompt=(f"customer_id={request.customer_id}. Pertanyaan: \"{request.message}\"."),
            )
        else:  # general
            resolution = await runner.run(
                step="handle:general", name=name, instructions=instructions,
                response_format=ServiceResolution,
                prompt=(f"customer_id={request.customer_id}. Pertanyaan umum: \"{request.message}\"."),
            )

        resolution.intent = routing.intent
        audit.record(request_id, "servicing", "final", name,
                     redact_pii(resolution.summary[:400]), decision=resolution.status.upper(),
                     tokens=cost.total_tokens)
        _emit(node, "done",
              f"📌 **{name}** selesai · status={resolution.status} · {resolution.summary[:140]}")

    tech_log.save(request_id, runner.tech)
    return resolution, routing, cost.summary()
