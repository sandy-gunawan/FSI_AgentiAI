# Developer Documentation — BNS Agentic AI Financing · **v2: Agents Hosted in Microsoft Foundry**

This folder is the **v2 companion** to the original [../docs](../docs/README.md) set. Same app, same
8 use cases, same governance — but the **agents now live in Microsoft Foundry** (as persistent
*prompt agents*) and the code **calls them by reference** instead of building them in-process.

> **v1 vs v2 in one line:** v1 builds an agent from an inline system prompt and runs it locally via
> the Agent Framework; **v2 calls an agent that already exists in Foundry**. The orchestration
> (order/parallel/loops) and the governance (audit + token + cost) stay **identical**.

Read in this order (mirrors the v1 docs, but every page is about the **Foundry-hosted** path):

| # | Doc | What it answers |
|---|-----|-----------------|
| 1 | [01-what-is-a-foundry-agent.md](01-what-is-a-foundry-agent.md) | **"If the agent is in Foundry, what is left in my code?"** — the #1 v2 question. |
| 2 | [02-architecture-and-flow-foundry.md](02-architecture-and-flow-foundry.md) | Layers, the moved boundary, and the end-to-end **request trace** for a v2 run. |
| 3 | [03-use-cases-foundry.md](03-use-cases-foundry.md) | For **each of the 8 use cases (v2)**: page, workflow, Foundry agent keys, pattern, diagram, decisions. |
| 4 | [04-surrounding-systems-foundry.md](04-surrounding-systems-foundry.md) | How **MCP + REST tools are attached to Foundry agents** so they reach the same systems — server-side. |
| 5 | [05-provision-and-deploy-foundry.md](05-provision-and-deploy-foundry.md) | Newbie step-by-step: **provision the 30 agents**, RBAC, `data/foundry_agents.json`, deploy the portal. |
| 6 | [06-use-case-code-walkthrough-foundry.md](06-use-case-code-walkthrough-foundry.md) | **Bilingual (EN/ID)** code-level trace per use case: page → v2 workflow → `agent_reference` call → outputs. |
| 7 | [07-governance-token-cost-foundry.md](07-governance-token-cost-foundry.md) | **Bilingual (EN/ID)** governance in v2: where **real Foundry tokens** come from, cost formula, audit/tech logs. |
| 8 | [08-observability-and-analytics-foundry.md](08-observability-and-analytics-foundry.md) | **Bilingual (EN/ID)** two telemetry layers: app OpenTelemetry → App Insights **and** Foundry's built-in Traces/Monitor. |
| 9 | [09-apim-ai-gateway.md](09-apim-ai-gateway.md) | **Bilingual (EN/ID)** optional **APIM AI Gateway**: per-transaction direct/APIM toggle for **both v1 & v2**, per-agent token metrics + thresholds, SKU choice (Developer, Indonesia Central), policies. |
| 10 | [10-apim-implementation-reference.md](10-apim-implementation-reference.md) | **Bilingual (EN/ID)** APIM **implementation reference**: full setup CLI, how the code calls it, complete **policy XML for v1 & v2**, sample threshold use cases, everything else APIM can do, high-level + low-level **diagrams**, troubleshooting. |
| 11 | [11-stateful-agentic-loops.md](11-stateful-agentic-loops.md) | **Newbie deep-dive:** what a **stateful agentic loop** (Foundry Agents v2 / Responses API) is, how it differs from our current **stateless** v2 calls, applied to Use Case 4 (Restructure) with code, sequence + fork **diagrams**, and exactly what would change in our repo. |

> Diagrams use **Mermaid** (renders in VS Code preview + GitHub). Where the v1 doc already explains a
> shared concept (e.g. the deterministic OJK/BI gate), this set links back to it instead of repeating.

## TL;DR for the impatient

- The **only real code difference** between v1 and v2 is **one runner**:
  [app/agents/shared/foundry_runner.py](../app/agents/shared/foundry_runner.py). Instead of
  `runner.run(instructions=..., tools=[...])` (v1), you call
  `runner.run(agent_key="retail-intake", prompt=...)` and it invokes the **already-provisioned**
  Foundry agent by reference.
- The **agents were created once** by [scripts/provision_foundry_agents.py](../scripts/provision_foundry_agents.py),
  which reads the **same instruction strings** from `app/agents/*/agents.py` and registers ~30
  prompt agents in Foundry, attaching MCP + REST tools. Their ids/names are saved to
  [data/foundry_agents.json](../data/foundry_agents.json).
- The **v2 workflows** ([app/workflows/*_foundry_workflow.py](../app/workflows)) keep the exact same
  orchestration and governance as v1; the deterministic OJK/BI logic is still plain Python.
- The **v2 pages** ([app/portal/views/11..18](../app/portal/views)) mirror the v1 pages and appear
  under the **🟣 Hosted di Foundry (v2)** group in the portal nav.
- **Nothing in v1 changed.** v2 is 100% additive.

## Where each layer lives (quick map)

| Layer | v1 file | v2 file |
|-------|---------|---------|
| Agent "brain" (instructions) | `app/agents/<uc>/agents.py` | **same strings**, but uploaded to Foundry by the provisioning script |
| The runner | [model_client.py](../app/agents/shared/model_client.py) `AgentRunner` | [foundry_runner.py](../app/agents/shared/foundry_runner.py) `FoundryAgentRunner` |
| Orchestration | `app/workflows/<uc>_workflow.py` | `app/workflows/<uc>_foundry_workflow.py` |
| UI page | `app/portal/views/<n>_<UseCase>.py` | `app/portal/views/1x_<UseCase>_on_Foundry.py` |
| Governance | audit_log + cost_tracker + tech_log | **identical** |
