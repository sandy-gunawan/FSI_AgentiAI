# 8 · Observability & Analytics — v2 (Foundry) · Bilingual EN/ID

This mirrors [../docs/08-observability-and-analytics.md](../docs/08-observability-and-analytics.md).
In v2 you get **two** telemetry layers instead of one. / *Di v2 ada **dua** lapisan telemetry, bukan
satu.*

| Layer | What | Where to look |
|-------|------|---------------|
| **A. App telemetry** (same as v1) | OpenTelemetry spans from the app → **Application Insights** | `appi-finance-agenticai` (KQL, App map, Live metrics) |
| **B. Foundry agent telemetry** (new in v2) | Each agent invocation is traced by **Foundry itself** | Foundry portal → project `financing` → **Traces / Monitor** on each agent |

**EN:** Layer A is your app's view (workflow spans, token usage you record). Layer B is Foundry's own
view of the **hosted agent runs** (each `agent_reference` call, its tool calls, its tokens). **ID:**
Lapisan A = sudut pandang aplikasi; Lapisan B = sudut pandang Foundry atas **jalannya agen hosted**
(tiap panggilan agen, tool-nya, token-nya).

---

## Layer A — App → Application Insights (unchanged) / Lapisan A (tetap)

**EN:** Turned on by the same one call, `setup_observability()`
([otel_setup.py](../app/observability/otel_setup.py)), which every v2 page calls at startup. **ID:**
Diaktifkan oleh panggilan yang sama, `setup_observability()`, yang dipanggil tiap halaman v2 saat
start.

```python
# app/observability/otel_setup.py (excerpt)
configure_azure_monitor(connection_string=…, resource=create_resource(), enable_live_metrics=True)
enable_instrumentation()   # Agent Framework GenAI spans
```

Env vars, portal blades, and the **ready-to-import Workbook** + **KQL examples** are exactly as in the
v1 doc — reuse them as-is:
- Import the workbook [../docs/bns-agent-analytics.workbook.json](../docs/bns-agent-analytics.workbook.json)
  into `appi-finance-agenticai`.
- KQL patterns (token usage, latency P50/P95, errors, end-to-end trace) live in
  [../docs/08-observability-and-analytics.md §6](../docs/08-observability-and-analytics.md).

> **Tip:** filter to this app with `cloud_RoleName == "bns-financing-agents"` (from `OTEL_SERVICE_NAME`).

### Correlate a v2 run / Mengaitkan satu run v2

**EN:** To tie an App Insights trace to a specific v2 request, add your `request_id` as a span
attribute (the v2 prefixes are `SMEF-`, `RETF-`, …). **ID:** Untuk mengaitkan jejak App Insights ke
satu request v2, tambahkan `request_id` sebagai atribut span.

```python
from opentelemetry import trace
with trace.get_tracer("bns.workflow").start_as_current_span("sme.foundry") as span:
    span.set_attribute("bns.request_id", request_id)   # e.g. SMEF-abc12345
    span.set_attribute("bns.use_case", "sme")
```

```kusto
dependencies
| where customDimensions["bns.request_id"] == "SMEF-abc12345"
| project timestamp, name, duration, customDimensions
| order by timestamp asc
```

---

## Layer B — Foundry's built-in agent tracing (new) / Lapisan B (baru)

**EN:** Because the agents run **inside Foundry**, Foundry records every invocation for you — no code
needed. This is the big observability win of v2. **ID:** Karena agen berjalan **di Foundry**, Foundry
mencatat tiap pemanggilan — tanpa kode. Ini keunggulan observability v2.

### How to view / Cara melihat

1. Open the Foundry portal → your project **`financing`**.
2. Go to **Agents** → pick an agent (e.g. `sme-underwriting-orchestrator`).
3. Open its **Traces / Runs / Monitor** tab. Each entry is one `agent_reference` call from your
   workflow and shows:
   - the **input** (your prompt) and **output** (the agent's answer),
   - the **tool calls** it made (MCP `screen_individual`, OpenAPI `get_financials…`) and their
     results — **server-side**, which your app never sees directly,
   - **token usage** and **latency** for that run.

**EN:** This is where you debug *"why did the magentic worker call the wrong endpoint?"* — you can see
the exact tool call Foundry made. **ID:** Di sinilah Anda men-debug *"kenapa worker memanggil endpoint
salah?"* — Anda melihat panggilan tool persis yang dibuat Foundry.

### What the page hints / Petunjuk di halaman

Every v2 page ends with a note pointing you here:

```python
st.info("🔎 Monitoring Foundry: langkah agen juga tercatat di Traces/Monitor pada agen "
        "di portal Foundry (project financing) — selain governance lokal di atas.")
```

---

## When to use which layer / Kapan pakai lapisan mana

| Question | Layer |
|----------|-------|
| "What did each agent step decide, per request, for audit?" | governance (audit log, [doc 07](07-governance-token-cost-foundry.md)) |
| "Token/cost shown to the user in the UI" | governance `CostTracker` ([doc 07](07-governance-token-cost-foundry.md)) |
| "App-wide latency, error rates, traffic, KQL analytics" | **Layer A — App Insights** |
| "What tool did the hosted agent actually call, and with what args?" | **Layer B — Foundry Traces** |
| "Real-time during a demo" | Layer A **Live metrics** (app) + Layer B agent runs (Foundry) |

**EN:** Rule of thumb: **governance** = auditable business record; **App Insights** = app operations;
**Foundry Traces** = the hosted agent's inner tool behaviour. **ID:** Pegangan: **governance** =
catatan bisnis; **App Insights** = operasional aplikasi; **Foundry Traces** = perilaku tool agen
hosted.

---

## Recap / Ringkasan

- v2 keeps **Layer A** (OpenTelemetry → App Insights) unchanged — reuse the v1 workbook + KQL.
- v2 **adds Layer B** for free: Foundry traces every hosted-agent run, including its **server-side
  tool calls** and tokens, viewable per agent in the Foundry portal.
- Together with the governance layer ([doc 07](07-governance-token-cost-foundry.md)), you can see a
  v2 request from three angles: **business decision**, **app telemetry**, and **agent internals**.
