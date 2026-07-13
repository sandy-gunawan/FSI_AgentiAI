"""v2 runtime: call persistent **Foundry prompt agents** instead of building agents in code.

This is the only real code difference between v1 and v2. v1 builds an ephemeral
``Agent`` from inline instructions and runs it via the Agent Framework; v2 calls the
agents you already provisioned in Foundry (see ``scripts/provision_foundry_agents.py``
-> ``data/foundry_agents.json``) through the Responses API by ``agent_reference``.

Everything else — token/cost tracking (CostTracker), audit log, technical log — stays
identical, so the portal's governance panels light up the same way. Additive; v1 is
untouched.
"""
from __future__ import annotations

import json
import pathlib
from contextlib import contextmanager
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from openai import OpenAI

from app.agents.shared.gateway import apim_base_url, apim_headers, route_label, use_apim
from app.core.config import get_settings
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import redact_pii
from app.governance.cost_tracker import CostTracker

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REGISTRY_PATH = _REPO_ROOT / "data" / "foundry_agents.json"


class FoundryAgentsNotProvisioned(RuntimeError):
    """Raised when data/foundry_agents.json is missing (run the provisioning script)."""


def load_agent_registry() -> dict:
    """Load the agent id/name map written by the provisioning script.

    Falls back to a synthetic registry (endpoint from settings, agent name == key) when
    ``data/foundry_agents.json`` is absent — so the app also works in containers where the
    file wasn't shipped, as long as FOUNDRY_PROJECT_ENDPOINT is set and the agents exist.
    """
    if _REGISTRY_PATH.exists():
        return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    endpoint = get_settings().foundry_project_endpoint
    if not endpoint:
        raise FoundryAgentsNotProvisioned(
            "data/foundry_agents.json not found and FOUNDRY_PROJECT_ENDPOINT is unset. "
            "Run: python scripts/provision_foundry_agents.py"
        )
    return {"project_endpoint": endpoint, "model": get_settings().foundry_model, "agents": {}}


def _trim(obj: Any, n: int = 500) -> str:
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return redact_pii(s)[:n] + ("…" if len(str(s)) > n else "")


def _usage_tokens(usage: Any) -> tuple[int, int]:
    """Extract (input, output) tokens from a Responses API usage object or dict."""
    if not usage:
        return 0, 0
    if isinstance(usage, dict):
        inp = usage.get("input_tokens") or usage.get("input_token_count") or usage.get("prompt_tokens") or 0
        out = usage.get("output_tokens") or usage.get("output_token_count") or usage.get("completion_tokens") or 0
        return int(inp), int(out)
    inp = (getattr(usage, "input_tokens", None) or getattr(usage, "input_token_count", None)
           or getattr(usage, "prompt_tokens", None) or 0)
    out = (getattr(usage, "output_tokens", None) or getattr(usage, "output_token_count", None)
           or getattr(usage, "completion_tokens", None) or 0)
    return int(inp), int(out)


def _usage_snapshot(usage: Any) -> dict:
    inp, out = _usage_tokens(usage)
    return {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}


class FoundryAgentRunner:
    """Runs Foundry-hosted prompt agents with the SAME governance hooks as v1."""

    def __init__(self, project: AIProjectClient, request_id: str, use_case: str,
                 cost: CostTracker, registry: dict, openai_client=None,
                 route: str = "direct") -> None:
        self.project = project
        # Injected client (APIM) or the direct Foundry OpenAI client.
        self.openai = openai_client or project.get_openai_client()
        self.route = route
        self.request_id = request_id
        self.use_case = use_case
        self.cost = cost
        self.registry = registry
        self.audit = get_audit_logger()
        self.tech: list[dict] = []

    def agent_name(self, agent_key: str) -> str:
        """Foundry agent name for a logical key (agent names equal the keys by convention)."""
        entry = self.registry.get("agents", {}).get(agent_key)
        return entry["name"] if entry else agent_key

    def run(self, *, step: str, name: str, agent_key: str, prompt: str) -> str:
        """Invoke one Foundry-hosted agent by reference; track tokens + audit + tech log."""
        agent_name = self.agent_name(agent_key)
        kwargs: dict = {}
        if self.route == "apim":
            # Tag the call so APIM can meter/limit per agent + use-case (see AI-gateway policies).
            kwargs["extra_headers"] = {"x-bns-agent": agent_name, "x-bns-usecase": self.use_case}
        response = self.openai.responses.create(
            input=prompt,
            extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
            **kwargs,
        )
        text = getattr(response, "output_text", None) or ""
        usage = getattr(response, "usage", None)
        in_tok, out_tok = _usage_tokens(usage)
        self.cost.add(in_tok, out_tok)

        # Record the real Foundry usage payload into the technical log (like v1's model:usage).
        self.tech.append({
            "tool": "foundry:agent",
            "args": _trim({"agent": agent_name, "step": step, "route": self.route}),
            "result": _trim(_usage_snapshot(usage)),
            "ms": 0.0,
        })
        self.audit.record(
            request_id=self.request_id,
            use_case=self.use_case,
            step=step,
            actor=f"foundry:{agent_name}",
            detail=redact_pii(text[:600]),
            tokens=in_tok + out_tok,
        )
        return text


@contextmanager
def foundry_session(request_id: str, use_case: str, via_apim: bool | None = None):
    """Own the AIProjectClient + cost tracker for one Foundry-backed request.

    ``via_apim`` is the per-request routing override from the portal toggle. When APIM
    is requested *and configured*, the agent calls go through the gateway; otherwise
    they go directly to Foundry (see app/agents/shared/gateway.py).
    """
    registry = load_agent_registry()
    endpoint = registry.get("project_endpoint") or get_settings().foundry_project_endpoint
    cost = CostTracker(request_id)
    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=endpoint, credential=credential)

    route = route_label(via_apim)
    openai_client = None
    if use_apim(via_apim):
        s = get_settings()
        openai_client = OpenAI(
            base_url=apim_base_url("responses"),
            api_key=s.apim_subscription_key,       # APIM validates via subscription key header
            default_headers=apim_headers(),
        )
    # Governance: record the effective route so the audit trail shows direct vs APIM.
    get_audit_logger().record(request_id, use_case, "gateway", f"route:{route}",
                              f"Routing agen v2 via {route.upper()}", decision=route.upper())
    try:
        yield FoundryAgentRunner(project, request_id, use_case, cost, registry,
                                 openai_client=openai_client, route=route), cost
    finally:
        for closeable in (project, credential):
            try:
                closeable.close()
            except Exception:  # pragma: no cover
                pass
