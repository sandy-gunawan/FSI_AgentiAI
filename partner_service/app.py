"""Bank Mitra Sejahtera (BMS) — a SEPARATE partner-bank agent exposed via the
Agent2Agent (A2A) protocol.

This is an independently-deployed service (its own container `ca-bns-partner`),
owned by a different institution. It publishes an **Agent Card** at the A2A
well-known path and answers **JSON-RPC `message/send`** tasks. BNS's Lead
Arranger agent discovers this card and delegates a co-underwriting task over A2A
— without sharing code, data, or model with the partner.

The partner's underwriting is deterministic (an automated STP engine) and runs
with NO cloud credentials — proving A2A works across opaque, independently-owned
agents. The wire format follows the open A2A spec (Agent Card + JSON-RPC
`message/send`); the official `a2a` SDK models the same shapes.

Run standalone:  uvicorn partner_service.app:app --port 8090
"""
from __future__ import annotations

import json
import uuid

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

PROVIDER = "Bank Mitra Sejahtera (BMS)"
A2A_PROTOCOL_VERSION = "0.3.0"
CARD_PATH = "/.well-known/agent-card.json"
RPC_PATH = "/a2a"

# ---- Partner bank's OWN, independent risk appetite (opaque to BNS) ---------- #
_APPETITE = {
    "max_participation_idr": 8_000_000_000,   # partner's single-deal ceiling
    "min_dscr": 1.25,                          # stricter than BNS
    "max_ltv": 0.75,
    "min_credit_score": 640,
    "base_rate_pct": 12.5,                     # partner prices a touch higher
    "risk_spread_by_grade": {"A": 0.0, "B": 2.5, "C": 5.0, "D": 8.0},
    "preferred_sectors": ["manufacturing", "food_beverage", "healthcare", "logistics"],
    "avoided_sectors": ["construction", "textile"],
}


def _agent_card(base_url: str) -> dict:
    """A2A Agent Card — how other agents discover this agent's identity & skills."""
    return {
        "protocolVersion": A2A_PROTOCOL_VERSION,
        "name": "BMS Co-Underwriting Agent",
        "description": ("Agen underwriting otomatis milik Bank Mitra Sejahtera. Menerima "
                        "undangan sindikasi/co-financing dan mengembalikan penawaran "
                        "partisipasi (plafon, indikasi bunga, syarat) berdasarkan selera "
                        "risiko BMS yang independen."),
        "provider": {"organization": PROVIDER, "url": "https://bms.example.id"},
        "version": "1.0.0",
        "url": f"{base_url}{RPC_PATH}",
        "preferredTransport": "JSONRPC",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "skills": [
            {
                "id": "co_underwrite",
                "name": "Co-underwriting participation",
                "description": ("Menilai permintaan co-financing dan mengembalikan penawaran "
                                "partisipasi (accept/partial/decline)."),
                "tags": ["syndication", "co-financing", "underwriting", "fsi"],
                "examples": [
                    "Ajakan sindikasi fasilitas SME 8 miliar IDR, tenor 48 bln, sektor manufaktur.",
                ],
            }
        ],
    }


def _co_underwrite(deal: dict) -> dict:
    """Deterministic partner-side underwriting. Input = deal facts from BNS."""
    a = _APPETITE
    sector = str(deal.get("sector", "")).lower()
    requested_participation = int(deal.get("requested_participation_idr", 0))
    dscr = float(deal.get("dscr", 0) or 0)
    ltv = float(deal.get("ltv", 0) or 0)
    score = int(deal.get("credit_score", 0) or 0)
    grade = str(deal.get("risk_grade", "C")).upper()
    tenor = int(deal.get("tenor_months", 0) or 0)

    reasons: list[str] = []
    hard_decline = False
    if sector in a["avoided_sectors"]:
        reasons.append(f"Sektor '{sector}' di luar selera risiko BMS")
        hard_decline = True
    if dscr and dscr < a["min_dscr"]:
        reasons.append(f"DSCR {dscr} < minimum BMS {a['min_dscr']}")
        hard_decline = True
    if ltv and ltv > a["max_ltv"]:
        reasons.append(f"LTV {ltv} > maksimum BMS {a['max_ltv']}")
        hard_decline = True
    if score and score < a["min_credit_score"]:
        reasons.append(f"Skor kredit {score} < minimum BMS {a['min_credit_score']}")
        hard_decline = True

    rate = round(a["base_rate_pct"] + a["risk_spread_by_grade"].get(grade, 5.0), 2)

    if hard_decline:
        return {
            "partner_name": PROVIDER,
            "decision": "DECLINE",
            "participation_amount_idr": 0,
            "indicative_rate_pct": rate,
            "conditions": [],
            "rationale": "BMS menolak partisipasi: " + "; ".join(reasons) + ".",
        }

    # Cap participation to the partner's ceiling; trim appetite for non-preferred sectors.
    ceiling = a["max_participation_idr"]
    if sector not in a["preferred_sectors"]:
        ceiling = int(ceiling * 0.6)
    participation = min(requested_participation, ceiling)
    partial = participation < requested_participation
    conditions = [
        "Pari-passu security sharing dengan lead arranger (BNS)",
        "Laporan keuangan triwulanan & covenant DSCR ≥ 1,25",
    ]
    if partial:
        conditions.append("Partisipasi dibatasi plafon internal BMS (partial take)")
    if tenor > 48:
        conditions.append("Review tahunan untuk tenor > 48 bulan")

    return {
        "partner_name": PROVIDER,
        "decision": "APPROVE",
        "participation_amount_idr": participation,
        "indicative_rate_pct": rate,
        "conditions": conditions,
        "rationale": (f"BMS setuju berpartisipasi {participation:,} IDR @ {rate}% p.a. "
                      + ("(partial, dibatasi plafon internal). " if partial else "(penuh). ")
                      + f"Sektor '{sector}' "
                      + ("disukai" if sector in a["preferred_sectors"] else "netral")
                      + ", DSCR & LTV memenuhi ambang BMS.").replace(",", "."),
    }


async def agent_card(request: Request) -> JSONResponse:
    # Behind a TLS-terminating ingress (Azure Container Apps), the internal scheme
    # is http; honor the forwarded headers so the advertised URL is the public https one.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    base = f"{proto}://{host}"
    return JSONResponse(_agent_card(base))


async def a2a_rpc(request: Request) -> JSONResponse:
    """A2A JSON-RPC 2.0 endpoint. Supports the `message/send` method."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "Parse error"}}, status_code=400)

    rpc_id = body.get("id")
    method = body.get("method")
    if method != "message/send":
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id,
                             "error": {"code": -32601, "message": f"Method not found: {method}"}})

    # Extract the text of the incoming A2A message (BNS's deal payload as JSON).
    params = body.get("params") or {}
    message = params.get("message") or {}
    parts = message.get("parts") or []
    text = ""
    for p in parts:
        if isinstance(p, dict) and p.get("text"):
            text = p["text"]
            break
    try:
        deal = json.loads(text) if text else {}
    except Exception:
        deal = {}

    offer = _co_underwrite(deal)

    # Reply as an A2A agent Message whose text part carries the structured offer.
    result = {
        "kind": "message",
        "role": "agent",
        "messageId": uuid.uuid4().hex,
        "parts": [{"kind": "text", "text": json.dumps(offer, ensure_ascii=False)}],
    }
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "bms-partner-a2a", "provider": PROVIDER})


app = Starlette(
    routes=[
        Route("/health", health),
        Route(CARD_PATH, agent_card),
        Route("/.well-known/agent.json", agent_card),  # legacy well-known alias
        Route(RPC_PATH, a2a_rpc, methods=["POST"]),
    ]
)
