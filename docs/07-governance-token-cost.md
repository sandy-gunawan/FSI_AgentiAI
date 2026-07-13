# 7 · Governance, Logs, Token Usage, and Cost (EN/ID)

This document explains how governance and measurement work in code, including:

- What is logged and where
- How token usage is counted
- How cost is calculated
- How to retrieve numbers per request and in aggregate
- What is real vs estimated

Dokumen ini menjelaskan detail teknis governance dan metrik:

- Apa yang dilog dan disimpan di mana
- Bagaimana token dihitung
- Bagaimana biaya dikalkulasi
- Cara mengambil angka per request dan agregat
- Mana angka real dan mana estimasi

---

## 1) Governance Building Blocks

### EN

- Audit persistence: [app/governance/audit_log.py#L19](../app/governance/audit_log.py#L19)
- Content safety and PII masking: [app/governance/content_safety.py#L27](../app/governance/content_safety.py#L27)
- Token budget and estimated cost: [app/governance/cost_tracker.py#L22](../app/governance/cost_tracker.py#L22)
- Technical tool-call log (name, args, result, latency): [app/governance/tech_log.py#L33](../app/governance/tech_log.py#L33)
- Runtime glue that records usage and audit per agent step: [app/agents/shared/model_client.py#L58](../app/agents/shared/model_client.py#L58)

### ID

Komponen governance utama:

- Audit trail persisten
- Penyaringan konten dan redaksi PII
- Tracking token budget per request
- Estimasi biaya berbasis token
- Log teknis panggilan tool beserta latency

---

## 2) What Gets Logged

### EN

Audit events store core fields like:

- request_id
- use_case
- step
- actor
- detail
- decision
- tokens
- ts

Data is stored in SQLite table audit_events via [app/governance/audit_log.py](../app/governance/audit_log.py).
Schema anchor: [app/governance/audit_log.py#L27](../app/governance/audit_log.py#L27)

Technical tool log stores per request:

- tool name
- arguments (trimmed and PII-redacted)
- result (trimmed and PII-redacted)
- latency in milliseconds

This is captured by middleware inside [app/agents/shared/model_client.py](../app/agents/shared/model_client.py) and mapped to endpoint metadata by [app/governance/tech_log.py](../app/governance/tech_log.py).
Anchors:

- Middleware capture: [app/agents/shared/model_client.py#L39](../app/agents/shared/model_client.py#L39)
- Endpoint map: [app/governance/tech_log.py#L13](../app/governance/tech_log.py#L13)
- Endpoint lookup: [app/governance/tech_log.py#L41](../app/governance/tech_log.py#L41)

### ID

Audit log menyimpan jejak langkah agen dan keputusan. Technical log menyimpan bukti pemanggilan tool nyata (MCP/REST/A2A) termasuk durasi ms.

---

## 3) Token Usage Calculation

### EN

Per agent step:

1. Runtime reads usage fields from model result in [app/agents/shared/model_client.py](../app/agents/shared/model_client.py)
2. Input and output tokens are added into request scope tracker in [app/governance/cost_tracker.py](../app/governance/cost_tracker.py)
3. If total exceeds budget, BudgetExceededError is raised

Anchors:

- Usage extraction: [app/agents/shared/model_client.py#L91](../app/agents/shared/model_client.py#L91)
- Add token counts: [app/governance/cost_tracker.py#L32](../app/governance/cost_tracker.py#L32)
- Budget exception: [app/governance/cost_tracker.py#L18](../app/governance/cost_tracker.py#L18)
- Summary payload: [app/governance/cost_tracker.py#L65](../app/governance/cost_tracker.py#L65)

Tracker summary fields include:

- input_tokens
- output_tokens
- total_tokens
- budget
- budget_used_pct
- estimated_cost_usd

### EN: Example result payload and extraction

Yes, token usage is read from the result returned by agent run.

Example flow:

```python
result = await agent.run(prompt, options=options)
usage = getattr(result, "usage_details", None) or {}

in_tok = int(usage.get("input_token_count") or usage.get("prompt_tokens") or 0)
out_tok = int(usage.get("output_token_count") or usage.get("completion_tokens") or 0)
```

Example usage_details shape (representative):

```json
{
	"input_token_count": 1287,
	"output_token_count": 412,
	"total_token_count": 1699
}
```

Runtime implementation anchor:

- result capture: [app/agents/shared/model_client.py#L111](../app/agents/shared/model_client.py#L111)
- usage extraction helper: [app/agents/shared/model_client.py#L58](../app/agents/shared/model_client.py#L58)
- token add into budget tracker: [app/agents/shared/model_client.py#L115](../app/agents/shared/model_client.py#L115)

Where to see the real runtime payload now:

- Each agent step appends a `model:usage` entry into technical log from `result.usage_details`.
- The entry is visible in the UI technical log panel (same place as MCP/REST call traces).
- Runtime source: [app/agents/shared/model_client.py](../app/agents/shared/model_client.py)
- UI label mapping: [app/governance/tech_log.py](../app/governance/tech_log.py)

### ID: Contoh result dan cara ambil token

Benar, token diambil dari object result hasil agent.run.

Contohnya:

```python
result = await agent.run(prompt, options=options)
usage = getattr(result, "usage_details", None) or {}

in_tok = int(usage.get("input_token_count") or usage.get("prompt_tokens") or 0)
out_tok = int(usage.get("output_token_count") or usage.get("completion_tokens") or 0)
```

Jadi angka token mengikuti usage yang dikembalikan runtime model/Foundry melalui result.

### ID

Token dihitung per step agen dari usage yang dikembalikan runtime model, lalu diakumulasi per request. Jika lewat budget, request dihentikan dengan error budget.

---

## 4) Cost Formula

### EN

Current implementation uses fixed demo rates in [app/governance/cost_tracker.py](../app/governance/cost_tracker.py):
Line anchors:

- Pricing constants and formula property: [app/governance/cost_tracker.py#L58](../app/governance/cost_tracker.py#L58)

- input: 0.15 USD per 1M tokens
- output: 0.60 USD per 1M tokens

Formula:

estimated_cost_usd = input_tokens / 1,000,000 * 0.15 + output_tokens / 1,000,000 * 0.60

### ID

Biaya saat ini adalah estimasi dengan tarif tetap untuk demo, bukan billing Azure final.

---

## 5) Is This Real Number?

### EN

Short answer:

- Token counts: mostly real runtime-reported usage for model calls
- Cost: estimated from fixed constants, not billing-export truth
- Tool latency: real wall-clock around middleware span

Accuracy caveats:

1. If usage fields are missing in a result, token increment can be zero for that step
2. Estimated cost can diverge from actual bill if model pricing, region, or meter differs
3. Technical log storage is in-memory per process for tool entries in [app/governance/tech_log.py](../app/governance/tech_log.py)
Anchor: [app/governance/tech_log.py#L10](../app/governance/tech_log.py#L10)

Foundry accuracy note:

- The app tracks the usage reported in result.usage_details.
- If Foundry returns input/output token fields, this app records those same values.
- Accuracy differences usually come from aggregation scope (per-step vs per-request vs billing window), not from formula mismatch.
- You can now inspect the per-step usage payload directly via the `model:usage` row in technical log.

### ID

Jawaban singkat:

- Token: berbasis usage runtime model, jadi relatif real untuk konsumsi model
- Cost: estimasi, bukan angka invoice
- Latency: real secara wall-clock dari sisi aplikasi

Catatan penting: jika ingin angka biaya resmi, pakai data billing Azure sebagai sumber utama.

---

## 6) How to Retrieve Numbers

### EN: In UI

Per-request view:

- Use-case pages render total token, estimated cost, and budget usage (example: [app/portal/views/1_Retail_Loan.py](../app/portal/views/1_Retail_Loan.py))
- Technical log panel is rendered via [app/portal/portal_utils.py#L30](../app/portal/portal_utils.py#L30)

Example metric anchors:

- token metric: [app/portal/views/1_Retail_Loan.py#L120](../app/portal/views/1_Retail_Loan.py#L120)
- estimated cost metric: [app/portal/views/1_Retail_Loan.py#L121](../app/portal/views/1_Retail_Loan.py#L121)
- budget metric: [app/portal/views/1_Retail_Loan.py#L122](../app/portal/views/1_Retail_Loan.py#L122)
- technical log call: [app/portal/views/1_Retail_Loan.py#L123](../app/portal/views/1_Retail_Loan.py#L123)

Aggregate view:

- Governance dashboard in [app/portal/views/3_Audit_Governance.py](../app/portal/views/3_Audit_Governance.py)
Anchors:

- recent events load: [app/portal/views/3_Audit_Governance.py#L18](../app/portal/views/3_Audit_Governance.py#L18)
- total token aggregate: [app/portal/views/3_Audit_Governance.py#L32](../app/portal/views/3_Audit_Governance.py#L32)
- SME case list: [app/portal/views/3_Audit_Governance.py#L72](../app/portal/views/3_Audit_Governance.py#L72)
- AML case list: [app/portal/views/3_Audit_Governance.py#L75](../app/portal/views/3_Audit_Governance.py#L75)

### EN: From SQLite

Audit trail by request:

SELECT request_id, use_case, step, actor, decision, tokens, ts
FROM audit_events
WHERE request_id = 'RET-XXXXXXX'
ORDER BY ts;

Recent token-heavy requests:

SELECT request_id, use_case, SUM(tokens) AS total_tokens
FROM audit_events
GROUP BY request_id, use_case
ORDER BY total_tokens DESC
LIMIT 20;

Human-in-the-loop case status and tokens:

SELECT request_id, status, tokens, updated_ts
FROM sme_cases
ORDER BY updated_ts DESC;

SELECT request_id, status, tokens, updated_ts
FROM aml_cases
ORDER BY updated_ts DESC;

Table schema anchors:

- sme_cases schema: [app/workflows/case_store.py#L29](../app/workflows/case_store.py#L29)
- aml_cases schema: [app/workflows/case_store.py#L45](../app/workflows/case_store.py#L45)
- sme token accumulation on complete: [app/workflows/case_store.py#L75](../app/workflows/case_store.py#L75)
- aml token accumulation on complete: [app/workflows/case_store.py#L129](../app/workflows/case_store.py#L129)

### ID: Ambil Angka

- Per request: lihat halaman use case
- Rekap: lihat dashboard governance
- Query teknis: langsung dari SQLite audit_events, sme_cases, aml_cases

---

## 7) Agent Usage Visibility: Who Did What

### EN

To answer what agent was used for what, and how many tokens/time:

1. Use request_id from portal result
2. Open audit rows for that request (actor and step columns)
3. Open technical log section for tool calls and latency
4. Read cost summary for total token and estimated cost

Cross-reference docs:

- Implementation map: [06-use-case-code-walkthrough.md](06-use-case-code-walkthrough.md)
- Workflow overviews: [03-use-cases.md](03-use-cases.md)

### ID

Untuk menjawab agen apa dipakai untuk apa, berapa token, dan berapa lama:

1. Ambil request_id
2. Lihat audit trail per step dan actor
3. Lihat log teknis untuk tool call dan ms
4. Lihat ringkasan biaya untuk token total dan estimasi biaya

---

## 8) Production Validation Checklist

### EN

Use this if stakeholders require billing-grade confidence:

1. Treat app-level estimated_cost_usd as internal estimate
2. Compare model usage totals with provider telemetry exports
3. Compare estimated cost against Azure billing/cost data for same period
4. Keep pricing constants versioned and timestamped in docs
5. Report both numbers: estimated (app) and actual (billing)

### ID

Checklist produksi:

1. Anggap estimated_cost_usd sebagai estimasi internal
2. Cocokkan total usage dengan telemetry/provider export
3. Cocokkan estimasi dengan data billing Azure periode yang sama
4. Versioning tarif harus jelas
5. Tampilkan dua angka: estimasi aplikasi dan real billing
