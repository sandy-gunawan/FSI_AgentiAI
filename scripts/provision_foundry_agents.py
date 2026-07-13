"""Provision ALL BNS demo agents as Microsoft Foundry *prompt agents* (v2 enabler).

WHAT THIS DOES
--------------
Reads the existing instruction constants from ``app/agents/*/agents.py`` and creates
one persistent Foundry **prompt agent** per role in your Foundry project, attaching
the correct tools so each agent can reach the SAME surrounding systems as v1:

  * MCP tools  -> credit-bureau, kyc-aml, policy-rules  (Streamable HTTP, anonymous)
  * OpenAPI    -> the REST back-office (core-banking, collateral, financials, ...)

It then writes every created agent's id/name/version to ``data/foundry_agents.json``
so the v2 workflows/UI can call the Foundry-hosted agents by id.

This is ADDITIVE and does not change anything that already works. It only creates
agents in Foundry (server-side). Re-running creates a new *version* of each agent.

PREREQUISITES
-------------
  1. ``az login`` (DefaultAzureCredential must succeed) with **Azure AI User** (or higher)
     on the Foundry project.
  2. ``pip install -r requirements.txt`` (needs azure-ai-projects>=2.1.0, jsonref, httpx).
  3. .env has FOUNDRY_PROJECT_ENDPOINT and REST_BASE_URL pointing at the deployed systems.

RUN
---
    az login
    python scripts/provision_foundry_agents.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass, field

# Allow running as a plain script from the repo root: `python scripts/provision_foundry_agents.py`
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx  # noqa: E402
from azure.identity import DefaultAzureCredential  # noqa: E402
from azure.ai.projects import AIProjectClient  # noqa: E402
from azure.ai.projects.models import (  # noqa: E402
    MCPTool,
    OpenApiAnonymousAuthDetails,
    OpenApiFunctionDefinition,
    OpenApiTool,
    PromptAgentDefinition,
)

from app.core.config import get_settings  # noqa: E402

# ---- Instruction constants (reused verbatim from v1 — single source of truth) ---- #
from app.agents.retail.agents import (  # noqa: E402
    CREDIT_RISK_AGENT,
    DECISION_AGENT,
    INTAKE_AGENT,
)
from app.agents.sme.agents import (  # noqa: E402
    AML_FRAUD_AGENT,
    COLLATERAL_AGENT,
    FINANCIAL_ANALYST,
    MARKET_RISK_AGENT,
    ORCHESTRATOR,
    TERMSHEET_AGENT,
)
from app.agents.servicing.agents import (  # noqa: E402
    BALANCE_AGENT,
    DISPUTE_AGENT,
    GENERAL_AGENT,
    HARDSHIP_AGENT,
    LIMIT_INCREASE_AGENT,
    ROUTER_AGENT,
)
from app.agents.restructure.agents import (  # noqa: E402
    EVALUATOR_AGENT,
    PROPOSER_AGENT,
    WRITER_AGENT,
)
from app.agents.aml.agents import INVESTIGATOR_AGENT, SAR_WRITER_AGENT  # noqa: E402
from app.agents.committee.agents import (  # noqa: E402
    CHAIR_AGENT,
    COMPLIANCE_OFFICER,
    RISK_OPTIMIST,
    RISK_SKEPTIC,
)
from app.agents.magentic.agents import (  # noqa: E402
    MANAGER_DOSSIER,
    MANAGER_PLAN,
    MANAGER_REPLAN,
    WORKER_AGENT,
)
from app.agents.syndication.agents import LEAD_ARRANGER, SYNTHESIZER  # noqa: E402

# MCP server labels -> path under REST_BASE_URL (trailing slash matters).
_MCP_PATHS = {
    "credit_bureau": "/mcp/credit-bureau/",
    "kyc_aml": "/mcp/kyc-aml/",
    "policy_rules": "/mcp/policy-rules/",
}


@dataclass
class AgentSpec:
    """One Foundry prompt agent to create."""

    name: str  # Foundry agent name (letters, digits, hyphens)
    instructions: str  # system prompt (reused from v1)
    mcp: list[str] = field(default_factory=list)  # MCP server labels to attach
    rest: bool = False  # attach the REST OpenAPI tool


# The full agent roster across all 8 use cases (~30 agents).
AGENTS: list[AgentSpec] = [
    # 1 - Retail (sequential)
    AgentSpec("retail-intake", INTAKE_AGENT, mcp=["kyc_aml"], rest=True),
    AgentSpec("retail-credit-risk", CREDIT_RISK_AGENT, mcp=["credit_bureau"]),
    AgentSpec("retail-decision", DECISION_AGENT),
    # 2 - SME (concurrent + human gate)
    AgentSpec("sme-financial-analyst", FINANCIAL_ANALYST, rest=True),
    AgentSpec("sme-collateral-agent", COLLATERAL_AGENT, rest=True),
    AgentSpec("sme-aml-fraud-agent", AML_FRAUD_AGENT, mcp=["kyc_aml"]),
    AgentSpec("sme-market-risk-agent", MARKET_RISK_AGENT),
    AgentSpec("sme-underwriting-orchestrator", ORCHESTRATOR, mcp=["policy_rules"]),
    AgentSpec("sme-termsheet-agent", TERMSHEET_AGENT),
    # 3 - Servicing (routing)
    AgentSpec("servicing-router", ROUTER_AGENT),
    AgentSpec("servicing-dispute", DISPUTE_AGENT, rest=True),
    AgentSpec("servicing-limit-increase", LIMIT_INCREASE_AGENT, mcp=["credit_bureau"], rest=True),
    AgentSpec("servicing-hardship", HARDSHIP_AGENT, rest=True),
    AgentSpec("servicing-balance", BALANCE_AGENT, rest=True),
    AgentSpec("servicing-general", GENERAL_AGENT),
    # 4 - Restructure (evaluator-optimizer loop)
    AgentSpec("restructure-proposer", PROPOSER_AGENT, mcp=["credit_bureau"], rest=True),
    AgentSpec("restructure-evaluator", EVALUATOR_AGENT, mcp=["policy_rules"]),
    AgentSpec("restructure-writer", WRITER_AGENT),
    # 5 - AML (ReAct + human gate)
    AgentSpec("aml-investigator", INVESTIGATOR_AGENT, mcp=["kyc_aml", "credit_bureau"], rest=True),
    AgentSpec("aml-sar-writer", SAR_WRITER_AGENT),
    # 6 - Committee (group chat)
    AgentSpec("committee-risk-optimist", RISK_OPTIMIST),
    AgentSpec("committee-risk-skeptic", RISK_SKEPTIC),
    AgentSpec("committee-compliance", COMPLIANCE_OFFICER, mcp=["policy_rules"]),
    AgentSpec("committee-chair", CHAIR_AGENT),
    # 7 - Magentic (manager + worker)
    AgentSpec("magentic-manager-plan", MANAGER_PLAN),
    AgentSpec("magentic-manager-replan", MANAGER_REPLAN),
    AgentSpec("magentic-manager-dossier", MANAGER_DOSSIER),
    AgentSpec("magentic-worker", WORKER_AGENT, mcp=["kyc_aml", "credit_bureau"], rest=True),
    # 8 - Syndication (A2A)
    AgentSpec("syndication-lead-arranger", LEAD_ARRANGER),
    AgentSpec("syndication-synthesizer", SYNTHESIZER),
]


def _fetch_rest_openapi(base_url: str) -> dict:
    """Fetch the REST back-office OpenAPI spec and make it Foundry-tool-safe.

    Two adjustments:
      * inject a public `servers` URL (FastAPI omits it) so the agent knows where to call;
      * strip FastAPI's auto `422` validation responses + unused components — their
        HTTPValidationError schema uses `anyOf`, which the Foundry OpenAPI tool validator
        rejects ("Invalid tool schema").
    """
    base_url = base_url.rstrip("/")
    spec = httpx.get(f"{base_url}/openapi.json", timeout=30).json()
    try:  # resolve $ref so the spec is self-contained
        import jsonref  # type: ignore

        spec = json.loads(jsonref.dumps(jsonref.replace_refs(spec), default=str))
    except Exception:  # pragma: no cover - jsonref optional
        pass
    # Drop 422 responses (contain anyOf) from every operation, then unused components.
    for methods in spec.get("paths", {}).values():
        if not isinstance(methods, dict):
            continue
        for op in methods.values():
            if isinstance(op, dict):
                op.get("responses", {}).pop("422", None)
    spec.pop("components", None)
    spec["servers"] = [{"url": base_url}]
    return spec


def _build_tools(spec: AgentSpec, mcp_base: str, rest_spec: dict) -> list:
    """Assemble the Foundry tool objects for one agent."""
    tools: list = []
    for label in spec.mcp:
        tools.append(
            MCPTool(
                server_label=label,
                server_url=f"{mcp_base}{_MCP_PATHS[label]}",
                require_approval="never",  # demo posture: surrounding systems have no auth
            )
        )
    if spec.rest:
        tools.append(
            OpenApiTool(
                openapi=OpenApiFunctionDefinition(
                    name="bns_rest_backoffice",
                    spec=rest_spec,
                    description=(
                        "BNS mock back-office REST API: core-banking accounts/transactions, "
                        "collateral appraisals, SME financial statements, existing loans, "
                        "monitoring alerts, and pricing quotes."
                    ),
                    auth=OpenApiAnonymousAuthDetails(),
                )
            )
        )
    return tools


def main() -> None:
    s = get_settings()
    endpoint = s.foundry_project_endpoint
    model = s.foundry_model
    mcp_base = s.rest_base_url.rstrip("/")

    if not endpoint:
        raise SystemExit("FOUNDRY_PROJECT_ENDPOINT is not set (.env).")
    if mcp_base.startswith("http://localhost") or mcp_base.startswith("http://127."):
        raise SystemExit(
            f"REST_BASE_URL is local ({mcp_base}). Foundry cannot reach localhost — "
            "point it at the deployed ca-bns-systems URL first."
        )

    print(f"Project : {endpoint}")
    print(f"Model   : {model}")
    print(f"Systems : {mcp_base}")
    print(f"Agents  : {len(AGENTS)}\n")

    rest_spec = _fetch_rest_openapi(mcp_base)

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    created: dict[str, dict] = {}
    failures: list[tuple[str, str]] = []

    with project:
        for spec in AGENTS:
            try:
                tools = _build_tools(spec, mcp_base, rest_spec)
                agent = project.agents.create_version(
                    agent_name=spec.name,
                    definition=PromptAgentDefinition(
                        model=model,
                        instructions=spec.instructions,
                        tools=tools or None,
                    ),
                )
                created[spec.name] = {
                    "id": getattr(agent, "id", None),
                    "name": getattr(agent, "name", spec.name),
                    "version": str(getattr(agent, "version", "")),
                    "mcp": spec.mcp,
                    "rest": spec.rest,
                }
                tool_note = ", ".join(spec.mcp + (["rest"] if spec.rest else [])) or "no tools"
                print(f"  OK  {spec.name:<32} v{created[spec.name]['version']:<3} [{tool_note}]")
            except Exception as exc:  # keep going; report at the end
                failures.append((spec.name, str(exc)))
                print(f"  FAIL {spec.name:<32} {exc}")

    out_path = _REPO_ROOT / "data" / "foundry_agents.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"project_endpoint": endpoint, "model": model, "systems_url": mcp_base, "agents": created},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"\nCreated {len(created)}/{len(AGENTS)} agents. Wrote {out_path.relative_to(_REPO_ROOT)}")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for name, err in failures:
            print(f"  - {name}: {err}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
