# 06 · Code walkthrough — following one request

We trace a single click of **"Jalankan Review"** through the code.

## 1. UI captures input
[app/portal/views/1_Invoice_Review.py](../app/portal/views/1_Invoice_Review.py)
- Radio picks `mode = DOC_INTELLIGENCE | MULTIMODAL`.
- File uploader or sample picker gives `image_bytes`, `source_name`, `mime`.
- On run, it calls `run_invoice_review(...)` via `run_async` and streams events to the
  live flow (`flow_viz.render_flow_html`) and the log box.

## 2. Orchestration
[app/workflows/invoice_review_workflow.py](../app/workflows/invoice_review_workflow.py)
```python
with foundry_session(request_id) as (runner, cost):
    if mode == DOC_INTELLIGENCE:
        raw = analyze_invoice(image_bytes)                 # Azure Document Intelligence
        extract_text = runner.run("extractor-di", raw)     # Agent 1A normalizes
    else:
        extract_text = runner.run_vision("extractor-vision", image_bytes)  # Agent 1B sees image
    extraction = _to_extraction(parse_json(extract_text))
    rules = load_rules(runner.tech)                        # FRESH read (hot-reload)
    review = runner.run("reviewer", extraction + policy_block(rules))       # Agent 2
    policy = evaluate(extraction, rules)                   # DETERMINISTIC decision
```
Governance is recorded at each step (`audit.record`, `cost.add`, `tech.append`).

## 3. The runner (calls Foundry agents)
[app/agents/shared/foundry_runner.py](../app/agents/shared/foundry_runner.py)
- `run(...)` → `openai.responses.create(input=prompt, extra_body={agent_reference})`.
- `run_vision(...)` → same, but `input` is a content list with an `input_image` data URL.
- Both extract token `usage`, add to `CostTracker`, append to the technical log, and
  write an audit row. **No agent is built in code** — they are referenced by name.

## 4. Extraction tool (Option A)
[app/tools/doc_intelligence.py](../app/tools/doc_intelligence.py)
- Calls `prebuilt-invoice`, maps DI field names (`InvoiceId`, `InvoiceTotal`, …) to the
  canonical keys, and keeps per-field `confidence`.

## 5. Config-driven rules
[app/review/rules_engine.py](../app/review/rules_engine.py)
- `load_rules()` reads Blob first (if configured) else `config/review_rules.yaml`,
  **fresh every call** (no cache) → genuine hot-reload.
- `policy_block(rules)` renders the current thresholds into a text block that is injected
  into the reviewer prompt.
- `evaluate(extraction, rules)` computes the **binding** decision:
  - over `max_facility_idr` or over `max_tenor_days` → `REJECT`
  - missing required fields / low confidence / math mismatch → `REFER`
  - otherwise → `APPROVE`

## 6. Agent instructions (source of truth)
[app/agents/invoice/agents.py](../app/agents/invoice/agents.py)
- `EXTRACTOR_DI`, `EXTRACTOR_VISION`, `REVIEWER` — uploaded to Foundry by
  [scripts/provision_agents.py](../scripts/provision_agents.py). Editing a string + re-running
  provisioning creates a **new agent version** in Foundry.

## 7. Governance & models
- [app/core/models.py](../app/core/models.py): `InvoiceExtraction`, `ReviewResult`, `PolicyDecision`.
- [app/governance/*](../app/governance): audit (SQLite), cost (tokens/USD), technical log.

## Data contract (the canonical JSON)

Both extractors emit the same schema, so the reviewer and rules engine don't care which
option produced it:
```json
{ "invoice_number": "...", "issue_date": "YYYY-MM-DD", "due_date": "YYYY-MM-DD",
  "seller": {"name":"...","account":"..."}, "buyer": {"name":"...","npwp":"..."},
  "subtotal_idr": 0, "tax_idr": 0, "total_amount_idr": 0, "po_number": "",
  "confidence": {"total_amount_idr": 0.99} }
```

Next → [07 · Config hot-reload](07-config-hot-reload.md)
