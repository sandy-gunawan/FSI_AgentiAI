"""Use Case 3 (v2) — Smart Customer Servicing with **Foundry-hosted agents**.

Same ROUTING pattern + governance as v1 ``run_servicing``: a router picks ONE handler,
only that handler runs. Intent is classified deterministically (keywords) for
auditability; the Foundry router agent explains the routing and the chosen Foundry
handler agent produces the resolution. Additive — v1 untouched. Returns a plain dict.
"""
from __future__ import annotations

import asyncio

from app.agents.shared.foundry_runner import foundry_session
from app.core.models import ServiceRequest
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii

# intent -> (viz node, agent display name, foundry agent key, status)
_HANDLERS = {
    "dispute": ("dispute", "DisputeHandler", "servicing-dispute", "escalated"),
    "limit_increase": ("limit", "LimitIncreaseHandler", "servicing-limit-increase", "info_provided"),
    "hardship": ("hardship", "HardshipHandler", "servicing-hardship", "escalated"),
    "balance_inquiry": ("balance", "BalanceHandler", "servicing-balance", "info_provided"),
    "general": ("general", "GeneralHandler", "servicing-general", "info_provided"),
}

# deterministic keyword → intent (mirrors what the router agent would classify)
_KEYWORDS = [
    ("dispute", ("tidak saya kenali", "sengketa", "tagihan", "tidak dikenal", "fraud", "salah potong",
                 "tidak saya lakukan", "dispute")),
    ("hardship", ("kesulitan", "tidak mampu", "lesu", "menunggak", "gagal bayar", "keringanan",
                  "restrukturisasi", "susah bayar")),
    ("limit_increase", ("naik limit", "kenaikan limit", "menaikkan limit", "tambah limit", "limit kartu")),
    ("balance_inquiry", ("saldo", "mutasi", "berapa uang", "rekening saya")),
]


def _classify(message: str) -> tuple[str, float]:
    low = message.lower()
    for intent, kws in _KEYWORDS:
        if any(k in low for k in kws):
            return intent, 0.9
    return "general", 0.6


async def run_servicing_foundry(
    request: ServiceRequest, request_id: str, on_event=None,
    via_apim: bool | None = None,
) -> tuple[dict, dict]:
    """Route one message to a Foundry handler agent. Returns (result, cost)."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "servicing", "submitted", "portal",
                 redact_pii(f"{request.full_name} ({request.channel}): {request.message}"))
    safety = check_text(request.message)
    audit.record(request_id, "servicing", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    intent, confidence = _classify(request.message)
    node, name, agent_key, status = _HANDLERS[intent]

    with foundry_session(request_id, "servicing", via_apim) as (runner, cost):
        def _call(step, disp, akey, prompt):
            return asyncio.to_thread(runner.run, step=step, name=disp, agent_key=akey, prompt=prompt)

        # ---- Stage 1: Router (Foundry) explains the classification ----
        _emit("router", "active",
              f"🧭 **Router** (agen Foundry) mengklasifikasikan pesan · \"{request.message[:120]}\".")
        rationale = await _call("route", "ServicingRouter", "servicing-router",
                                f"customer_id={request.customer_id}, channel={request.channel}. "
                                f"Pesan nasabah: \"{request.message}\". Intent terdeteksi: {intent}. "
                                f"Jelaskan singkat alasan klasifikasi.")
        audit.record(request_id, "servicing", "route", "foundry:servicing-router",
                     f"intent={intent} confidence={confidence}", decision=intent.upper())
        _emit("router", "done",
              f"🧭 **Router** selesai · intent=**{intent}** (keyakinan {confidence:.0%}).")

        # ---- Stage 2: the single routed handler resolves the request ----
        _emit(node, "active", f"📌 **{name}** (agen Foundry) menangani intent '{intent}'.")
        summary = await _call(f"handle:{intent}", name, agent_key,
                              f"customer_id={request.customer_id}, channel={request.channel}. "
                              f"Pesan nasabah: \"{request.message}\". Tangani sesuai peran Anda dan "
                              f"berikan ringkasan penyelesaian untuk nasabah.")
        audit.record(request_id, "servicing", "final", f"foundry:{agent_key}",
                     redact_pii(summary[:400]), decision=status.upper(), tokens=cost.total_tokens)
        _emit(node, "done", f"📌 **{name}** selesai · status={status} · {summary[:140]}")

    tech_log.save(request_id, runner.tech)
    result = {
        "intent": intent,
        "confidence": confidence,
        "rationale": rationale,
        "handler": name,
        "status": status,
        "summary": summary,
    }
    return result, cost.summary()
