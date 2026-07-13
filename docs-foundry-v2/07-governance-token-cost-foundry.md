# 7 · Governance, Tokens & Cost — v2 (Foundry) · Bilingual EN/ID

This mirrors [../docs/07-governance-token-cost.md](../docs/07-governance-token-cost.md). The
governance model is **the same**; the only real difference is **where the token numbers come from**.
/ *Model governance-nya **sama**; beda utamanya: **dari mana angka token berasal**.*

**EN:** In v1 the tokens come from the Agent Framework's usage on each local run. In **v2** they come
from **`response.usage`** on the Foundry **Responses API** call — i.e. the **real** tokens Foundry
counted for that agent invocation. **ID:** Di v1 token berasal dari usage Agent Framework; di **v2**
dari **`response.usage`** panggilan **Responses API** Foundry — yaitu token **nyata** yang dihitung
Foundry untuk pemanggilan agen tersebut.

---

## The three governance objects (unchanged) / Tiga objek governance (tetap)

| Object | File | Role |
|--------|------|------|
| **Audit log** | [audit_log.py](../app/governance/audit_log.py) | one row per agent step (who/what/decision/tokens) → SQLite `data/audit.db` |
| **Cost tracker** | [cost_tracker.py](../app/governance/cost_tracker.py) | running token totals + USD estimate + budget % |
| **Technical log** | [tech_log.py](../app/governance/tech_log.py) | per-step tool/latency detail shown under each run |

**EN:** v2 uses the **exact same** three objects, so the portal's governance panels are identical.
**ID:** v2 memakai **objek yang sama**, sehingga panel governance di portal identik.

---

## Where tokens come from in v2 / Asal token di v2

Inside [`FoundryAgentRunner.run`](../app/agents/shared/foundry_runner.py):

```python
response = self.openai.responses.create(
    input=prompt,
    extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
)
usage = getattr(response, "usage", None)          # ← REAL usage from the Responses API
in_tok, out_tok = _usage_tokens(usage)            # input_tokens / output_tokens
self.cost.add(in_tok, out_tok)                    # feed the SAME CostTracker as v1
```

`_usage_tokens` is defensive about field names (input_tokens / prompt_tokens / …) so it works across
SDK versions. / *`_usage_tokens` toleran terhadap nama field agar lintas versi SDK.*

```python
def _usage_tokens(usage):
    inp = getattr(usage, "input_tokens", None)  or getattr(usage, "prompt_tokens", None)     or 0
    out = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None) or 0
    return int(inp), int(out)
```

> **Is it a real number? / Angka nyata?** **Yes** — these are the tokens Foundry billed for the call,
> read straight from the API response, summed across every agent step in the request. / **Ya** — token
> yang ditagih Foundry, dibaca langsung dari respons API, dijumlahkan sepanjang langkah dalam 1 request.

---

## The cost formula / Rumus biaya

**EN:** The USD estimate uses fixed per-million rates for the chosen model (gpt-4o-mini). **ID:**
Estimasi USD memakai tarif tetap per-juta token untuk model (gpt-4o-mini).

```python
# app/governance/cost_tracker.py (illustrative)
INPUT_PER_1M  = 0.15   # USD per 1M input tokens
OUTPUT_PER_1M = 0.60   # USD per 1M output tokens
cost_usd = input_tokens/1e6 * INPUT_PER_1M + output_tokens/1e6 * OUTPUT_PER_1M
```

`cost.summary()` returns `{total_tokens, estimated_cost_usd, budget_used_pct}`, which the page shows
as **Total token**, **Est. biaya (USD)**, and a **budget progress bar**.

> **Caveat / Catatan:** the USD figure is an **estimate** from fixed rates, not a billing source of
> truth. Tokens are real; the dollar value is indicative. / *Nilai USD adalah **estimasi** tarif
> tetap, bukan sumber tagihan resmi. Token nyata; dolar bersifat indikatif.*

---

## What each agent step records / Yang dicatat tiap langkah agen

Still inside `FoundryAgentRunner.run`:

```python
# technical log — one entry per Foundry call
self.tech.append({
    "tool": "foundry:agent",
    "args": _trim({"agent": agent_name, "step": step}),
    "result": _trim(_usage_snapshot(usage)),      # {input_tokens, output_tokens, total_tokens}
    "ms": 0.0,
})
# audit log — the durable business record
self.audit.record(
    request_id=self.request_id, use_case=self.use_case, step=step,
    actor=f"foundry:{agent_name}",                # e.g. "foundry:retail-intake"
    detail=redact_pii(text[:600]),
    tokens=in_tok + out_tok,
)
```

- **`actor="foundry:<agent>"`** — so the audit table clearly shows the step ran on a **hosted** agent.
  / *Menandai langkah berjalan di agen **Foundry**.*
- **`redact_pii(...)`** — PII redaction is applied before anything is written, same as v1. / *Redaksi
  PII diterapkan sebelum menulis, sama seperti v1.*
- **Content safety** — each workflow still runs `check_text(...)` on free-text input and audits the
  result. / *Setiap workflow tetap menjalankan `check_text(...)` dan mengauditnya.*

---

## The deterministic decision is still the record / Keputusan deterministik tetap jadi catatan

**EN:** The **binding decision** written to the audit `final` row is the **deterministic** policy
result, not the LLM's opinion — identical to v1. **ID:** **Keputusan mengikat** pada baris `final`
adalah hasil **kebijakan deterministik**, bukan opini LLM — sama seperti v1.

```python
audit.record(request_id, "sme", "final", "foundry:sme-underwriting-orchestrator",
             recommendation[:400], decision=pol["decision"], tokens=cost.total_tokens)
```

---

## How to retrieve the numbers / Cara mengambil angka

**In the portal / Di portal:** open any v2 page, run a case → the right-hand panel shows tokens/USD,
the audit table lists every step, and the technical log lists each `foundry:agent` call.

**From SQLite / Dari SQLite** (`data/audit.db`) — same schema as v1:

```sql
-- total tokens per request (v2 runs have request-id prefixes like SMEF-, RETF-, CMTF- …)
SELECT request_id, SUM(tokens) AS tokens
FROM audit_events
WHERE request_id LIKE 'SMEF-%'
GROUP BY request_id
ORDER BY MAX(ts) DESC;

-- every step of one request, in order
SELECT ts, step, actor, decision, tokens, detail
FROM audit_events
WHERE request_id = 'SMEF-abc12345'
ORDER BY ts ASC;

-- which Foundry agents were used, and their token totals
SELECT actor, COUNT(*) AS calls, SUM(tokens) AS tokens
FROM audit_events
WHERE actor LIKE 'foundry:%'
GROUP BY actor
ORDER BY tokens DESC;
```

> v2 request-id prefixes: `RETF-` (retail), `SMEF-` (SME), `SVCF-` (servicing), `RSTF-` (restructure),
> `AMLF-` (aml), `CMTF-` (committee), `MAGF-` (magentic), `SYNF-` (syndication).

---

## v1 vs v2 governance — quick diff

| | v1 | v2 |
|---|---|---|
| Token source | Agent Framework run usage | **Responses API `response.usage`** |
| Actor in audit | agent display name | **`foundry:<agent>`** |
| Tech-log tool | `model:usage` / tool spans | **`foundry:agent`** |
| Cost formula | same | **same** |
| Deterministic decision | same | **same** |
| PII redaction / content safety | same | **same** |

Next: [08-observability-and-analytics-foundry.md](08-observability-and-analytics-foundry.md).
