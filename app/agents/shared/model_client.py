"""Shared Microsoft Agent Framework plumbing for the financing demo.

Provides:
  * a FoundryChatClient factory (Azure AD auth via AzureCliCredential)
  * AgentRunner — runs an agent, captures token usage into the CostTracker,
    and writes an audit event for every step (governance).
  * financing_session() — async context manager that owns the credential +
    chat client + cost tracker for one financing request.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import time
from typing import Any, Sequence

from azure.identity.aio import DefaultAzureCredential
from pydantic import BaseModel

from agent_framework import Agent, function_middleware
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatClient

from app.agents.shared.gateway import apim_base_url, apim_headers, route_label, use_apim
from app.core.config import get_settings
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import redact_pii
from app.governance.cost_tracker import CostTracker


def _trim(obj: Any, n: int = 260) -> str:
    """Compact, PII-redacted string of a tool argument/result for the technical log."""
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    s = redact_pii(s)
    return s[:n] + ("…" if len(s) > n else "")


def _make_tool_logger(sink: list[dict]):
    """A function middleware that records every real tool/MCP call into `sink`."""

    @function_middleware
    async def _mw(context, next):  # noqa: A002 - framework signature
        name = getattr(getattr(context, "function", None), "name", "tool")
        t0 = time.perf_counter()
        await next()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        sink.append({
            "tool": name,
            "args": _trim(getattr(context, "arguments", None)),
            "result": _trim(getattr(context, "result", None)),
            "ms": ms,
        })

    return _mw


def _extract_usage_tokens(usage: Any) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from usage payload.

    Supports both dict-like and object-like usage payloads and common field names
    returned by different SDK response shapes.
    """
    if not usage:
        return 0, 0

    if isinstance(usage, dict):
        inp = usage.get("input_token_count") or usage.get("prompt_tokens") or 0
        out = usage.get("output_token_count") or usage.get("completion_tokens") or 0
        return int(inp), int(out)

    inp = getattr(usage, "input_token_count", None) or getattr(usage, "prompt_tokens", None) or 0
    out = getattr(usage, "output_token_count", None) or getattr(usage, "completion_tokens", None) or 0
    return int(inp), int(out)


def _usage_snapshot(usage: Any) -> dict:
    """Return a compact serializable snapshot of usage_details for traceability."""
    if not usage:
        return {}

    if isinstance(usage, dict):
        return {
            "input_token_count": int(usage.get("input_token_count") or usage.get("prompt_tokens") or 0),
            "output_token_count": int(usage.get("output_token_count") or usage.get("completion_tokens") or 0),
            "total_token_count": int(
                usage.get("total_token_count")
                or ((usage.get("input_token_count") or usage.get("prompt_tokens") or 0)
                    + (usage.get("output_token_count") or usage.get("completion_tokens") or 0))
            ),
            "raw": usage,
        }

    inp = int(getattr(usage, "input_token_count", None) or getattr(usage, "prompt_tokens", None) or 0)
    out = int(getattr(usage, "output_token_count", None) or getattr(usage, "completion_tokens", None) or 0)
    total = int(getattr(usage, "total_token_count", None) or (inp + out))
    return {
        "input_token_count": inp,
        "output_token_count": out,
        "total_token_count": total,
    }


class AgentRunner:
    """Runs Agent Framework agents with governance hooks attached."""

    def __init__(self, client: FoundryChatClient, request_id: str, use_case: str,
                 cost: CostTracker, route: str = "direct") -> None:
        self.client = client
        self.request_id = request_id
        self.use_case = use_case
        self.cost = cost
        self.route = route
        self.audit = get_audit_logger()
        self.tech: list[dict] = []  # real tool/MCP call log

    async def run(
        self,
        *,
        step: str,
        name: str,
        instructions: str,
        prompt: str,
        response_format: type[BaseModel] | None = None,
        tools: Sequence[Any] | None = None,
    ) -> Any:
        """Run one agent step. Returns a parsed model (if response_format) or text."""
        agent = Agent(
            client=self.client,
            name=name,
            instructions=instructions,
            tools=list(tools) if tools else None,
            middleware=[_make_tool_logger(self.tech)],
        )
        options = {"response_format": response_format} if response_format else None
        result = await agent.run(prompt, options=options)

        usage = getattr(result, "usage_details", None) or {}
        in_tok, out_tok = _extract_usage_tokens(usage)
        self.cost.add(in_tok, out_tok)
        self.tech.append({
            "tool": "model:usage",
            "args": _trim({"step": step, "actor": name, "route": self.route}),
            "result": _trim(_usage_snapshot(usage), n=500),
            "ms": 0.0,
        })

        detail = redact_pii((result.text or "")[:600])
        self.audit.record(
            request_id=self.request_id,
            use_case=self.use_case,
            step=step,
            actor=name,
            detail=detail,
            tokens=in_tok + out_tok,
        )
        return result.value if response_format else result.text


def make_chat_client(credential: DefaultAzureCredential, via_apim: bool | None = None):
    """Build the chat client for one request: direct FoundryChatClient, or an
    OpenAI-compatible client pointed at the APIM gateway when routing via APIM."""
    s = get_settings()
    if use_apim(via_apim):
        return OpenAIChatClient(
            model=s.foundry_model,
            base_url=apim_base_url("chat"),
            api_key=s.apim_subscription_key,       # APIM validates via subscription key header
            api_version=s.apim_api_version or None,
            default_headers=apim_headers(),
        )
    return FoundryChatClient(
        project_endpoint=s.foundry_project_endpoint,
        model=s.foundry_model,
        credential=credential,
    )


@asynccontextmanager
async def financing_session(request_id: str, use_case: str, via_apim: bool | None = None):
    """Own the credential + chat client + cost tracker for one request.

    ``via_apim`` is the per-request routing override from the portal toggle; falls back
    to the direct path when APIM is not configured (see app/agents/shared/gateway.py).
    """
    cost = CostTracker(request_id)
    route = route_label(via_apim)
    async with DefaultAzureCredential() as credential:
        client = make_chat_client(credential, via_apim)
        runner = AgentRunner(client, request_id, use_case, cost, route=route)
        get_audit_logger().record(request_id, use_case, "gateway", f"route:{route}",
                                  f"Routing agen v1 via {route.upper()}", decision=route.upper())
        yield runner, cost
