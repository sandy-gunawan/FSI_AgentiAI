"""Provision the 3 bcafinance prompt agents into Microsoft Foundry.

Creates persistent Foundry **prompt agents** from the instruction strings in
``app/agents/invoice/agents.py`` (single source of truth) and writes their
id/name/version to ``data/agents.json`` so the workflow can call them by
reference. Re-running creates a NEW version of each agent (that is how you roll
out an instruction change).

These agents have NO MCP/REST tools — Agent 1 receives OCR/image input and Agent
2 receives extracted JSON + the current POLICY block (injected at call time).

PREREQUISITES
-------------
  1. ``az login`` (DefaultAzureCredential must succeed) with **Azure AI Developer**
     (or higher) on the Foundry project.
  2. ``pip install -r requirements.txt``.
  3. .env has FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL (vision-capable, e.g. gpt-4o-mini).

RUN
---
    az login
    python scripts/provision_agents.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from azure.identity import DefaultAzureCredential  # noqa: E402
from azure.ai.projects import AIProjectClient  # noqa: E402
from azure.ai.projects.models import PromptAgentDefinition  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.agents.invoice.agents import EXTRACTOR_DI, EXTRACTOR_VISION, REVIEWER  # noqa: E402


@dataclass
class AgentSpec:
    name: str
    instructions: str


AGENTS: list[AgentSpec] = [
    AgentSpec("bca-invoice-extractor-di", EXTRACTOR_DI),
    AgentSpec("bca-invoice-extractor-vision", EXTRACTOR_VISION),
    AgentSpec("bca-invoice-reviewer", REVIEWER),
]


def main() -> None:
    s = get_settings()
    endpoint = s.foundry_project_endpoint
    model = s.foundry_model
    if not endpoint:
        raise SystemExit("FOUNDRY_PROJECT_ENDPOINT is not set (.env).")

    print(f"Project : {endpoint}")
    print(f"Model   : {model}")
    print(f"Agents  : {len(AGENTS)}\n")

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    created: dict[str, dict] = {}
    failures: list[tuple[str, str]] = []

    with project:
        for spec in AGENTS:
            try:
                agent = project.agents.create_version(
                    agent_name=spec.name,
                    definition=PromptAgentDefinition(model=model, instructions=spec.instructions),
                )
                created[spec.name] = {
                    "id": getattr(agent, "id", None),
                    "name": getattr(agent, "name", spec.name),
                    "version": str(getattr(agent, "version", "")),
                }
                print(f"  OK  {spec.name:<30} v{created[spec.name]['version']}")
            except Exception as exc:
                failures.append((spec.name, str(exc)))
                print(f"  FAIL {spec.name:<30} {exc}")

    out_path = _REPO_ROOT / "data" / "agents.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"project_endpoint": endpoint, "model": model, "agents": created},
        indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nCreated {len(created)}/{len(AGENTS)} agents. Wrote {out_path.relative_to(_REPO_ROOT)}")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for name, err in failures:
            print(f"  - {name}: {err}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
