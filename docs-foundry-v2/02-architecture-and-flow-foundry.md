# 2 · Architecture & Flow (v2 — Foundry-hosted)

This mirrors [../docs/02-architecture-and-flow.md](../docs/02-architecture-and-flow.md) but shows the
**one boundary that moves** in v2: the agent + its tool-calling loop move **into Foundry**.

---

## Where the boundary moves

**v1** — the tool-calling loop runs **in your Python process**; the model is remote:

```mermaid
flowchart LR
    UI[Streamlit page] --> WF[workflow.py<br/>orchestration]
    WF --> R1[AgentRunner]
    R1 -->|builds Agent + runs tool loop locally| M[(Model in Foundry)]
    R1 -->|calls MCP/REST from local code| SYS[Systems Container App]
```

**v2** — you hand the task to a **hosted agent**; Foundry runs the tool loop and calls the systems:

```mermaid
flowchart LR
    UI[Streamlit page] --> WF[*_foundry_workflow.py<br/>SAME orchestration]
    WF --> R2[FoundryAgentRunner]
    R2 -->|responses.create agent_reference| FA[Foundry prompt agent<br/>instructions + tools + model]
    FA -->|MCP + OpenAPI tool calls SERVER-SIDE| SYS[Systems Container App]
    R2 -.governance: audit + token + cost.-> GOV[(SQLite audit.db)]
```

Key point: in v2 your code **never** calls MCP/REST directly for reasoning steps — the **Foundry
agent** does, because the tools are attached to the agent (see
[doc 04](04-surrounding-systems-foundry.md)). Your code still calls the systems directly only for
**deterministic** facts (e.g. reading financials to compute DSCR) and for **A2A** (syndication).

---

## Layer map (v2)

| Layer | Files | Role |
|-------|-------|------|
| **UI** | [app/portal/views/11..18](../app/portal/views) | v2 pages; same live viz + governance panels as v1 |
| **Orchestration** | [app/workflows/*_foundry_workflow.py](../app/workflows) | order / parallel / loops / gates — **plain Python** |
| **Runner** | [app/agents/shared/foundry_runner.py](../app/agents/shared/foundry_runner.py) | calls Foundry agents by reference; records governance |
| **Agent registry** | [data/foundry_agents.json](../data/foundry_agents.json) | maps `agent_key` → Foundry agent name |
| **Agents (remote)** | Microsoft Foundry project `financing` | persistent prompt agents (instructions + tools + model) |
| **Deterministic rules** | [app/governance/rules_engine.py](../app/governance/rules_engine.py), [mock_services/policy.py](../mock_services/policy.py) | OJK/BI gates — **no LLM** |
| **Governance** | [audit_log.py](../app/governance/audit_log.py) · [cost_tracker.py](../app/governance/cost_tracker.py) · [tech_log.py](../app/governance/tech_log.py) | identical to v1 |
| **Systems** | [mock_services](../mock_services) on `ca-bns-systems` | REST + 3 MCP servers — called **by the Foundry agent** |
| **Observability** | [otel_setup.py](../app/observability/otel_setup.py) + Foundry Traces | app OTel → App Insights **and** Foundry's built-in monitor |

---

## End-to-end request trace (v2 SME example)

Follow one click of **"Jalankan Analisis (agen Foundry)"** on
[11_SME_on_Foundry.py](../app/portal/views/11_SME_on_Foundry.py):

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant P as 11_SME_on_Foundry.py
    participant W as sme_foundry_workflow.py
    participant D as data_access + rules_engine (Python)
    participant R as FoundryAgentRunner
    participant F as Foundry agents (financing)
    participant S as Systems (ca-bns-systems)
    participant G as Governance (audit/cost/tech)

    U->>P: submit SME request
    P->>W: run_sme_foundry(request, request_id, on_event)
    W->>D: read SoR facts → compute LTV / DSCR / DER (DETERMINISTIC)
    W->>D: evaluate_sme(...) → pre-screen APPROVE/DECLINE/REFER
    W->>R: run(agent_key="sme-financial-analyst", prompt=...)  (×4 in PARALLEL)
    R->>F: responses.create(agent_reference)
    F->>S: MCP/OpenAPI tool calls (server-side)
    S-->>F: data
    F-->>R: output_text + usage (real tokens)
    R->>G: cost.add(tokens) · audit.record(...) · tech.append("foundry:agent")
    R-->>W: specialist findings (text)
    W->>R: run(agent_key="sme-underwriting-orchestrator", prompt=...aggregate)
    R-->>W: recommendation (text)
    W-->>P: {decision (deterministic), findings, recommendation} + cost.summary()
    P-->>U: decision + 4 findings + tokens/USD + audit table + tech log
```

The shape is the **same** as the v1 trace — only the "who runs the agent + tools" step changed
from `AgentRunner` (local) to `FoundryAgentRunner` → Foundry (remote).

---

## What stays deterministic (and why it matters)

Exactly as in v1, the **decision** in v2 is **not** taken by the LLM for regulated flows. Example
from [sme_foundry_workflow.py](../app/workflows/sme_foundry_workflow.py):

```python
pol = evaluate_sme(years_operating=..., ltv_ratio=ltv, dscr=dscr_val, ...)   # pure Python
...
audit.record(request_id, "sme", "final", "foundry:sme-underwriting-orchestrator",
             recommendation[:400], decision=pol["decision"], tokens=cost.total_tokens)
```

The Foundry orchestrator agent writes the **narrative recommendation**; the **binding decision**
(`APPROVE/DECLINE/REFER`) is the deterministic `pol["decision"]`. This keeps v2 auditable and
regulator-safe, and means the LLM (local or hosted) can never approve through a hard policy breach.

---

## Two things your code still calls directly

1. **Deterministic data reads** — `data_access` + `mock_services.data.load(...)` to compute ratios.
   These are facts, not reasoning, so they stay in Python.
2. **A2A (syndication only)** — [a2a_client.py](../app/tools/a2a_client.py) `a2a_send(...)` to the
   partner bank agent. That is agent-to-agent across organisations and is unchanged in v2
   (only the BNS-side Lead Arranger/Synthesizer moved to Foundry).

Next: [03-use-cases-foundry.md](03-use-cases-foundry.md) — the 8 use cases, v2 edition.
