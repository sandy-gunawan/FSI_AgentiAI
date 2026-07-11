"""Minimal Agent2Agent (A2A) client used by BNS to delegate to a partner bank's
remote agent.

Implements the open A2A protocol wire format: (1) discover the partner's
**Agent Card** at the well-known path, then (2) send a **JSON-RPC `message/send`**
task and read the agent's reply. The official `a2a` SDK models the same shapes;
this thin client keeps the demo dependency-light and fully observable.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

_TIMEOUT = 20.0
CARD_PATH = "/.well-known/agent-card.json"


async def fetch_agent_card(base_url: str) -> dict[str, Any]:
    """A2A discovery — GET the partner agent's Agent Card."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
        r = await c.get(f"{base_url.rstrip('/')}{CARD_PATH}")
    r.raise_for_status()
    return r.json()


async def a2a_send(base_url: str, text: str) -> dict[str, Any]:
    """Discover the card, then send a JSON-RPC `message/send` task.

    Returns a dict with the card, the raw request/response envelopes, the
    extracted reply text, and latencies (ms) — for display and the tech log.
    """
    base = base_url.rstrip("/")
    t0 = time.perf_counter()
    card = await fetch_agent_card(base)
    card_ms = round((time.perf_counter() - t0) * 1000, 1)

    rpc_url = card.get("url") or f"{base}/a2a"
    # Behind an HTTPS ingress the card may advertise an http:// URL; POSTing there
    # triggers a 301 http→https redirect (which drops the JSON-RPC body). Force the
    # RPC call to https when we discovered the card over https.
    if base.startswith("https://") and rpc_url.startswith("http://"):
        rpc_url = "https://" + rpc_url[len("http://"):]
    request_env = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": uuid.uuid4().hex,
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }
    t1 = time.perf_counter()
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
        r = await c.post(rpc_url, json=request_env)
    send_ms = round((time.perf_counter() - t1) * 1000, 1)
    r.raise_for_status()
    response_env = r.json()

    reply_text = ""
    result = response_env.get("result") or {}
    for part in result.get("parts", []) or []:
        if isinstance(part, dict) and part.get("text"):
            reply_text = part["text"]
            break

    return {
        "card": card,
        "rpc_url": rpc_url,
        "request": request_env,
        "response": response_env,
        "reply_text": reply_text,
        "card_ms": card_ms,
        "send_ms": send_ms,
    }
