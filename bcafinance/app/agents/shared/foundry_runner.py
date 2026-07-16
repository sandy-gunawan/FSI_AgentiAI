"""Runtime: call persistent **Foundry prompt agents** by reference.

The 3 agents (bca-invoice-extractor-di, bca-invoice-extractor-vision,
bca-invoice-reviewer) are created in Microsoft Foundry by
``scripts/provision_agents.py`` — NEVER built in code. This runner invokes them
through the Responses API by ``agent_reference`` and records governance
(tokens, audit, technical log) for every call.

``run``        -> text-only agents (DI normalizer, reviewer).
``run_vision`` -> multimodal agent that receives the invoice image directly.
"""
from __future__ import annotations

import base64
import json
import time
from contextlib import contextmanager
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from app.core.config import get_settings
from app.governance.audit_log import get_audit_logger
from app.governance.cost_tracker import CostTracker


class FoundryAgentsNotProvisioned(RuntimeError):
    """Raised when data/agents.json is missing (run scripts/provision_agents.py)."""


def load_agent_registry() -> dict:
    """Load the agent name map written by the provisioning script."""
    s = get_settings()
    path = s.agents_registry_path
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not s.foundry_project_endpoint:
        raise FoundryAgentsNotProvisioned(
            "data/agents.json not found and FOUNDRY_PROJECT_ENDPOINT is unset. "
            "Run: python scripts/provision_agents.py"
        )
    # Synthetic fallback: agent name == key.
    return {"project_endpoint": s.foundry_project_endpoint, "model": s.foundry_model, "agents": {}}


def _usage_tokens(usage: Any) -> tuple[int, int]:
    if not usage:
        return 0, 0
    if isinstance(usage, dict):
        inp = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        out = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        return int(inp), int(out)
    inp = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None) or 0
    out = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None) or 0
    return int(inp), int(out)


class FoundryAgentRunner:
    """Runs Foundry-hosted prompt agents with governance hooks."""

    def __init__(self, project: AIProjectClient, request_id: str, cost: CostTracker,
                 registry: dict) -> None:
        self.project = project
        self.openai = project.get_openai_client()
        self.request_id = request_id
        self.cost = cost
        self.registry = registry
        self.audit = get_audit_logger()
        self.tech: list[dict] = []

    def agent_name(self, agent_key: str) -> str:
        entry = self.registry.get("agents", {}).get(agent_key)
        return entry["name"] if entry else agent_key

    def _finish(self, *, tool: str, step: str, agent_name: str, text: str, usage: Any,
                started: float) -> str:
        in_tok, out_tok = _usage_tokens(usage)
        self.cost.add(in_tok, out_tok)
        self.tech.append({
            "tool": tool, "args": f"agent={agent_name} step={step}",
            "result": f"in={in_tok} out={out_tok} tokens", "ms": round((time.time() - started) * 1000, 1),
        })
        self.audit.record(self.request_id, "invoice_review", step, f"foundry:{agent_name}",
                          text[:600], tokens=in_tok + out_tok)
        return text

    def run(self, *, tool: str, step: str, agent_key: str, prompt: str) -> str:
        """Invoke a text-only Foundry agent by reference."""
        agent_name = self.agent_name(agent_key)
        started = time.time()
        response = self.openai.responses.create(
            input=prompt,
            extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
        )
        text = getattr(response, "output_text", None) or ""
        return self._finish(tool=tool, step=step, agent_name=agent_name, text=text,
                            usage=getattr(response, "usage", None), started=started)

    def run_vision(self, *, tool: str, step: str, agent_key: str, prompt: str,
                   image_bytes: bytes, mime: str = "image/png") -> str:
        """Invoke a multimodal Foundry agent with an inline image."""
        agent_name = self.agent_name(agent_key)
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        started = time.time()
        response = self.openai.responses.create(
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }],
            extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
        )
        text = getattr(response, "output_text", None) or ""
        return self._finish(tool=tool, step=step, agent_name=agent_name, text=text,
                            usage=getattr(response, "usage", None), started=started)


@contextmanager
def foundry_session(request_id: str):
    """Own the AIProjectClient + cost tracker for one invoice-review request."""
    registry = load_agent_registry()
    endpoint = registry.get("project_endpoint") or get_settings().foundry_project_endpoint
    cost = CostTracker(request_id)
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    try:
        runner = FoundryAgentRunner(project, request_id, cost, registry)
        yield runner, cost
    finally:
        try:
            project.close()
        except Exception:
            pass
