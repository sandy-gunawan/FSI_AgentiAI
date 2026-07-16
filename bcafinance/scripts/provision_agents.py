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
from azure.ai.projects.models import (  # noqa: E402
    OpenApiAnonymousAuthDetails,
    OpenApiFunctionDefinition,
    OpenApiTool,
    PromptAgentDefinition,
)
import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.agents.invoice.agents import (  # noqa: E402
    EXTRACTOR_DI,
    EXTRACTOR_DI_AGENTIC,
    EXTRACTOR_VISION,
    REVIEWER,
)


@dataclass
class AgentSpec:
    name: str
    instructions: str
    openapi_tool: bool = False  # attach the tools-service analyze_invoice OpenAPI tool


AGENTS: list[AgentSpec] = [
    AgentSpec("bca-invoice-extractor-di", EXTRACTOR_DI),
    AgentSpec("bca-invoice-extractor-di-agentic", EXTRACTOR_DI_AGENTIC, openapi_tool=True),
    AgentSpec("bca-invoice-extractor-vision", EXTRACTOR_VISION),
    AgentSpec("bca-invoice-reviewer", REVIEWER),
]


def _build_tools_openapi(base_url: str) -> dict:
    """Hand-built minimal OpenAPI 3.0.3 spec for the analyze_invoice tool.

    We do NOT reuse FastAPI's auto /openapi.json because FastAPI emits OpenAPI 3.1.0,
    which the Foundry OpenAPI tool executor rejects ("Invalid OpenAPI specification").
    A tiny, self-contained 3.0.3 spec with one operation is robust and Foundry-safe.
    """
    base_url = base_url.rstrip("/")
    return {
        "openapi": "3.0.3",
        "info": {"title": "bca-invoice-tools", "version": "1.0.0"},
        "servers": [{"url": base_url}],
        "paths": {
            "/analyze_invoice": {
                "post": {
                    "operationId": "analyze_invoice",
                    "summary": "Run Azure AI Document Intelligence on a stored invoice image.",
                    "description": "Given an image_id (from a prior upload), returns extracted "
                                   "invoice fields with per-field confidence.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "image_id": {
                                            "type": "string",
                                            "description": "Id of the previously uploaded invoice image.",
                                        }
                                    },
                                    "required": ["image_id"],
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Extracted invoice fields (+ confidence).",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            }
        },
    }


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

    # Build the OpenAPI tool once (if the tools service URL is configured).
    tools_url = s.tools_service_url
    openapi_tool = None
    if tools_url:
        try:
            spec = _build_tools_openapi(tools_url)
            openapi_tool = OpenApiTool(openapi=OpenApiFunctionDefinition(
                name="bca_invoice_tools", spec=spec,
                description="Document Intelligence wrapper: analyze_invoice(image_id) returns invoice fields.",
                auth=OpenApiAnonymousAuthDetails()))
            print(f"Tools   : {tools_url} (OpenAPI tool attached to agentic agent)")
        except Exception as exc:
            print(f"Tools   : WARN could not fetch OpenAPI from {tools_url}: {exc}")

    with project:
        for spec_a in AGENTS:
            try:
                tools = [openapi_tool] if (spec_a.openapi_tool and openapi_tool) else None
                agent = project.agents.create_version(
                    agent_name=spec_a.name,
                    definition=PromptAgentDefinition(model=model, instructions=spec_a.instructions,
                                                     tools=tools),
                )
                created[spec_a.name] = {
                    "id": getattr(agent, "id", None),
                    "name": getattr(agent, "name", spec_a.name),
                    "version": str(getattr(agent, "version", "")),
                }
                note = " [analyze_invoice tool]" if tools else ""
                print(f"  OK  {spec_a.name:<34} v{created[spec_a.name]['version']}{note}")
            except Exception as exc:
                failures.append((spec_a.name, str(exc)))
                print(f"  FAIL {spec_a.name:<34} {exc}")

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
