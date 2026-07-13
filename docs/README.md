# Developer Documentation — BNS Agentic AI Financing

This folder explains **how the app is built in code**: what an "agent" actually is here,
how the **Microsoft Agent Framework** is called, how each use case is **orchestrated**, where
**decisions** are made, and how the **MCP** and **A2A** protocols are wired.

> 🟣 **Looking for the v2, Foundry-hosted version?** There is a parallel doc set at
> **[../docs-foundry-v2/](../docs-foundry-v2/README.md)** that explains, at the code level, how each
> use case is **called in Microsoft Foundry** (agents provisioned as prompt agents and invoked by
> reference), while keeping the same orchestration and governance described here.

Read in this order:

| # | Doc | What it answers |
|---|-----|-----------------|
| 1 | [01-what-is-an-agent.md](01-what-is-an-agent.md) | **"Where are the agents? Everything looks like one file!"** — the #1 question. |
| 2 | [02-architecture-and-flow.md](02-architecture-and-flow.md) | Layers, component map, the end-to-end **request trace**, and how the framework is called. |
| 3 | [03-use-cases.md](03-use-cases.md) | For **each of the 8 use cases**: entry point, components, agents, orchestration, diagram, decisions. |
| 4 | [04-surrounding-systems.md](04-surrounding-systems.md) | The **REST / MCP / A2A** systems around the agents: what they are, why one container, what data, and **exactly how to call them** (URLs, auth, examples). |
| 5 | [05-deploy-to-azure.md](05-deploy-to-azure.md) | Newbie step-by-step Azure deployment: build images, update Container Apps, set env vars, verify live URLs. |
| 6 | [06-use-case-code-walkthrough.md](06-use-case-code-walkthrough.md) | **Bilingual (EN/ID)** code-level trace for each use case: page -> workflow -> agents -> tools -> outputs -> where token/cost/time are shown. |
| 7 | [07-governance-token-cost.md](07-governance-token-cost.md) | **Bilingual (EN/ID)** governance internals: audit logging, technical logs, token accounting, cost formula, realism caveats, and how to retrieve numbers. |
| 8 | [08-observability-and-analytics.md](08-observability-and-analytics.md) | **Bilingual (EN/ID)** observability layer: OpenTelemetry -> Application Insights, how to log/instrument, access, and query telemetry with KQL examples. |

> Diagrams use **Mermaid**, which renders in VS Code's Markdown preview and on GitHub.

## TL;DR for the impatient

- An **"agent"** in this code is **not a class or a file**. It is a **configuration** —
  `(name + instructions + tools + output schema)` — handed to **one reusable runner**
  (`AgentRunner.run(...)` in [app/agents/shared/model_client.py](../app/agents/shared/model_client.py)),
  which builds a framework `Agent` on the fly and runs it.
- The **"agent files"** ([app/agents/&lt;use_case&gt;/agents.py](../app/agents)) contain only the
  **instructions** (system prompts) as plain strings — e.g. `INTAKE_AGENT`, `CREDIT_RISK_AGENT`.
- The **orchestration** (order, parallelism, loops, branches, human gates) is **plain Python**
  in [app/workflows/&lt;use_case&gt;_workflow.py](../app/workflows). That is the "multi-agent" logic.
- **Decisions** are split on purpose: **deterministic** rules (OJK/BI policy, affordability) are
  plain Python; **reasoning + narrative** is done by the LLM agents.
- For operators and auditors, read [06-use-case-code-walkthrough.md](06-use-case-code-walkthrough.md)
  and [07-governance-token-cost.md](07-governance-token-cost.md) after [03-use-cases.md](03-use-cases.md).
