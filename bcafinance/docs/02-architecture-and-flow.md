# 02 · Architecture & flow

## The layers

| Layer | Files | Role |
|-------|-------|------|
| **UI** | [app/portal/views/1_Invoice_Review.py](../app/portal/views/1_Invoice_Review.py) | Upload, Option A/B toggle, live flow, results |
| **Orchestration** | [app/workflows/invoice_review_workflow.py](../app/workflows/invoice_review_workflow.py) | Runs Agent 1 → Agent 2 → rules; plain Python |
| **Runner** | [app/agents/shared/foundry_runner.py](../app/agents/shared/foundry_runner.py) | Calls Foundry agents by reference; records governance |
| **Agents (remote)** | Microsoft Foundry project `financing` | 3 persistent prompt agents |
| **Extraction (Option A)** | [app/tools/doc_intelligence.py](../app/tools/doc_intelligence.py) | Document Intelligence `prebuilt-invoice` |
| **Deterministic rules** | [app/review/rules_engine.py](../app/review/rules_engine.py) | Config-driven binding decision + prompt injection |
| **Config** | [config/review_rules.yaml](../config/review_rules.yaml) | Editable policy (hot-reload) |
| **Governance** | [audit_log.py](../app/governance/audit_log.py) · [cost_tracker.py](../app/governance/cost_tracker.py) · [tech_log.py](../app/governance/tech_log.py) | Audit trail, tokens/cost, technical proof |
| **Observability** | [otel_setup.py](../app/observability/otel_setup.py) + Foundry Traces | App telemetry + agent-side traces |

## Component diagram

```mermaid
flowchart LR
    SYS[External system / user] -->|invoice image| UI[Streamlit portal]
    UI --> WF[invoice_review_workflow.py]

    WF -->|mode A| DI[Azure AI Document Intelligence]
    DI --> A1A[Agent 1: extractor-di]
    WF -->|mode B| A1B[Agent 1: extractor-vision]

    A1A --> A2[Agent 2: reviewer]
    A1B --> A2

    WF --> CFG[(review_rules.yaml<br/>local or Blob)]
    A2 --> RULES[rules_engine.py<br/>DETERMINISTIC]
    CFG --> RULES
    RULES --> OUT[Decision + review]

    WF -.audit + tokens + tech.-> GOV[(audit.db)]
    WF -.traces.-> AI[App Insights + Foundry Traces]

    subgraph Foundry [Microsoft Foundry · project financing]
      A1A; A1B; A2
    end
```

## End-to-end sequence

```mermaid
sequenceDiagram
    participant U as User/system
    participant P as Portal (1_Invoice_Review.py)
    participant W as invoice_review_workflow.py
    participant DI as Document Intelligence (Option A)
    participant R as FoundryAgentRunner
    participant F as Foundry agents (financing)
    participant C as review_rules.yaml
    participant E as rules_engine (Python)
    participant G as Governance

    U->>P: upload invoice + choose A/B + run
    P->>W: run_invoice_review(image, mode, request_id)
    alt Option A
        W->>DI: analyze prebuilt-invoice (bytes)
        DI-->>W: fields + confidence
        W->>R: run(extractor-di, raw JSON)
    else Option B
        W->>R: run_vision(extractor-vision, image)
    end
    R->>F: responses.create(agent_reference)
    F-->>R: canonical JSON + usage
    W->>C: load_rules() FRESH (hot-reload)
    W->>R: run(reviewer, JSON + POLICY block)
    R->>F: responses.create(agent_reference)
    F-->>R: review JSON + usage
    W->>E: evaluate(extraction, rules)  DETERMINISTIC
    E-->>W: APPROVE / REFER / REJECT + reasons
    W->>G: audit.record + cost.add + tech.save
    W-->>P: {decision, extraction, review, cost}
    P-->>U: banner + tabs (review, extraction, audit, tech)
```

## Why the decision is deterministic

The reviewer agent writes the *narrative*. The **binding** APPROVE/REFER/REJECT is
computed by `rules_engine.evaluate()` in pure Python from the extracted fields and the
current policy. So:
- Hard breach (over limit, over max tenor) → **REJECT**.
- Missing fields, low confidence, math mismatch → **REFER**.
- All checks pass → **APPROVE**.

Next → [03 · The two options](03-the-two-options.md)
