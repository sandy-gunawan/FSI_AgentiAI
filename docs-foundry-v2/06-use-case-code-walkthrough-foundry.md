# 6 · Use-Case Code Walkthrough — v2 (Foundry) · Bilingual EN/ID

This mirrors [../docs/06-use-case-code-walkthrough.md](../docs/06-use-case-code-walkthrough.md) but
traces the **Foundry-hosted** path: **page → v2 workflow → `FoundryAgentRunner.run` (agent_reference)
→ governance → outputs**. / *Dokumen ini menelusuri jalur **v2 (Foundry)**: halaman → workflow v2 →
pemanggilan agen Foundry → governance → keluaran.*

---

## The shared v2 call shape / Bentuk pemanggilan v2 yang dipakai semua

**EN:** Every v2 workflow uses the same three-part shape. **ID:** Semua workflow v2 memakai pola yang sama.

```python
with foundry_session(request_id, use_case) as (runner, cost):        # 1) open Foundry client + cost
    text = await asyncio.to_thread(                                  # 2) call a hosted agent
        runner.run, step="…", name="…", agent_key="retail-intake", prompt="…",
    )
tech_log.save(request_id, runner.tech)                               # 3) persist technical log
return result, cost.summary()                                        #    + return tokens/USD
```

- **`foundry_session`** ([foundry_runner.py](../app/agents/shared/foundry_runner.py)) opens the
  `AIProjectClient` and the `CostTracker`. / *Membuka klien Foundry + pelacak biaya.*
- **`runner.run(agent_key=…)`** invokes the persistent Foundry agent by reference; it records audit +
  token + tech automatically. / *Memanggil agen Foundry via reference; mencatat audit + token + tech.*
- **`cost.summary()`** returns `{total_tokens, estimated_cost_usd, budget_used_pct}` for the page. /
  *Mengembalikan token/biaya untuk ditampilkan halaman.*

---

## 1 · Retail (sequential) / Ritel (berurutan)

- **Page / Halaman:** [12_Retail_on_Foundry.py](../app/portal/views/12_Retail_on_Foundry.py) →
  builds `RetailLoanApplication`, calls `run_retail_foundry(...)`.
- **Workflow:** [retail_foundry_workflow.py](../app/workflows/retail_foundry_workflow.py).

**EN:** Deterministic first (rate, installment, DBR, `evaluate_retail` → decision), then 3 Foundry
agents for narrative. **ID:** Deterministik dulu (bunga, angsuran, DBR, keputusan OJK/BI), lalu 3 agen
Foundry untuk narasi.

```python
pol = evaluate_retail(age=…, dbr_ratio=dbr, credit_score=…, sanctions_hit=…)   # decision (Python)
decision = pol["decision"]
with foundry_session(request_id, "retail") as (runner, cost):
    intake      = await _call("intake",      "IntakeAgent",     "retail-intake",      …)
    credit_text = await _call("credit_risk", "CreditRiskAgent", "retail-credit-risk", …)
    explanation = await _call("decision",    "DecisionAgent",   "retail-decision",    …)
```

- **Outputs / Keluaran:** `decision`, `metrics` (score/grade/DBR/rate/installment), `offer`,
  `intake` / `credit_text` / `explanation`.
- **Where numbers show / Angka tampil di:** token/USD from `cost.summary()`; audit table from
  `get_audit_logger().events_for(request_id)`; tech log via `render_tech_log(request_id)`.

---

## 2 · SME (concurrent) / UKM (paralel)

- **Page:** [11_SME_on_Foundry.py](../app/portal/views/11_SME_on_Foundry.py)
- **Workflow:** [sme_foundry_workflow.py](../app/workflows/sme_foundry_workflow.py)

**EN:** 4 specialists run in parallel, then the orchestrator aggregates; the decision is the
deterministic `evaluate_sme` pre-screen. **ID:** 4 spesialis paralel, lalu orchestrator menggabungkan;
keputusan = pra-skrining deterministik.

```python
financial, collateral_txt, aml_txt, market = await asyncio.gather(
    _call("specialist:financial",  "FinancialAnalyst", "sme-financial-analyst", …),
    _call("specialist:collateral", "CollateralAgent",  "sme-collateral-agent",  …),
    _call("specialist:aml",        "AmlFraudAgent",    "sme-aml-fraud-agent",   …),
    _call("specialist:market",     "MarketRiskAgent",  "sme-market-risk-agent", …),
)
recommendation = await asyncio.to_thread(runner.run, agent_key="sme-underwriting-orchestrator", …)
```

---

## 3 · Servicing (routing) / Layanan (routing)

- **Page:** [13_Servicing_on_Foundry.py](../app/portal/views/13_Servicing_on_Foundry.py)
- **Workflow:** [servicing_foundry_workflow.py](../app/workflows/servicing_foundry_workflow.py)

**EN:** Intent is classified deterministically (`_classify`), the router agent explains it, then a
single handler agent resolves it. **ID:** Intent diklasifikasi deterministik, router menjelaskan,
lalu satu handler menyelesaikan.

```python
intent, confidence = _classify(request.message)               # deterministic
node, name, agent_key, status = _HANDLERS[intent]
rationale = await _call("route", "ServicingRouter", "servicing-router", …)
summary   = await _call(f"handle:{intent}", name, agent_key, …)   # only ONE handler runs
```

---

## 4 · Restructuring (evaluator–optimizer) / Restrukturisasi

- **Page:** [14_Restructuring_on_Foundry.py](../app/portal/views/14_Restructuring_on_Foundry.py)
- **Workflow:** [restructure_foundry_workflow.py](../app/workflows/restructure_foundry_workflow.py)

**EN:** Loop up to 3×: deterministic scheme → proposer narrative → `evaluate_restructure` gate →
evaluator narrative; break when affordable; writer explains. **ID:** Loop ≤3×: skema deterministik →
narasi proposer → gerbang keterjangkauan → narasi evaluator; berhenti bila terjangkau; writer menutup.

```python
for i in range(1, MAX_ITERS + 1):
    scheme = _scheme(i, cur_rate, remaining_tenor)                 # deterministic
    new_installment = monthly_installment(principal, scheme["new_rate_pct"], eff_tenor)
    await _call(f"propose#{i}",  "RestructureProposer",  "restructure-proposer",  …)
    gate = evaluate_restructure(new_dbr_ratio=…, …)               # deterministic verdict
    await _call(f"evaluate#{i}", "RestructureEvaluator", "restructure-evaluator", …)
    if gate["affordable"]: break
await _call("explain", "RestructureWriter", "restructure-writer", …)
```

---

## 5 · AML (ReAct + human gate) / AML

- **Page:** [15_AML_on_Foundry.py](../app/portal/views/15_AML_on_Foundry.py)
- **Workflow:** [aml_foundry_workflow.py](../app/workflows/aml_foundry_workflow.py)

**EN:** Investigator agent (tools server-side) → deterministic escalation (DTTOT ⇒ file) →
auto-confirmed human gate → SAR writer. **ID:** Investigator (tool di sisi Foundry) → eskalasi
deterministik → gate manusia (otomatis untuk demo) → penulis SAR.

```python
investigation = await _call("investigate", "AmlInvestigator", "aml-investigator", …)
file_sar = sanctioned or request.alert_type in ("structuring", "layering", "high_risk_jurisdiction")
action   = "file" if file_sar else "dismiss"                      # deterministic
sar_narrative = await _call("filing", "SarWriter", "aml-sar-writer", …)
```

---

## 6 · Committee (group chat) / Komite

- **Page:** [16_Credit_Committee_on_Foundry.py](../app/portal/views/16_Credit_Committee_on_Foundry.py)
- **Workflow:** [committee_foundry_workflow.py](../app/workflows/committee_foundry_workflow.py)

**EN:** 3 debaters × 2 rounds on a shared transcript, then Chair; decision = pre-screen (DECLINE on
hard breach). **ID:** 3 pendebat × 2 ronde pada transkrip bersama, lalu Chair; keputusan =
pra-skrining (DECLINE bila pelanggaran keras).

```python
for rnd in range(1, ROUNDS + 1):
    for node, speaker, agent_key, stance in _DEBATERS:            # optimist, skeptic, compliance
        argument = await _call(f"turn:{node}#{rnd}", f"Committee:{speaker}", agent_key, …)
        transcript.append({"speaker": speaker, "stance": stance, "argument": argument})
summary  = await _call("decision", "CommitteeChair", "committee-chair", …)
decision = "DECLINE" if hard_block else pol["decision"]          # deterministic
```

---

## 7 · Magentic / Investigasi Kompleks

- **Page:** [17_Complex_Investigation_on_Foundry.py](../app/portal/views/17_Complex_Investigation_on_Foundry.py)
- **Workflow:** [magentic_foundry_workflow.py](../app/workflows/magentic_foundry_workflow.py)

**EN:** Manager plans, 4 workers execute the ledger (each wrapped in `try/except`), manager writes
the dossier. **ID:** Manager merencana, 4 worker menjalankan ledger (tiap langkah dibungkus
`try/except`), manager menyusun dosir.

```python
plan = await _call("plan", "MagenticManager", "magentic-manager-plan", …)
for assigned_to, task, note in _STEPS:                            # kyc, transactions, credit, financials
    try:
        finding = await _call(f"worker:{assigned_to}", f"Worker:{assigned_to}", "magentic-worker", …)
    except Exception as exc:
        finding = f"(worker '{assigned_to}' gagal: {exc})"       # resilient
dossier = await _call("dossier", "MagenticManager", "magentic-manager-dossier", …)
```

---

## 8 · Syndication (A2A) / Sindikasi

- **Page:** [18_Syndication_on_Foundry.py](../app/portal/views/18_Syndication_on_Foundry.py)
- **Workflow:** [syndication_foundry_workflow.py](../app/workflows/syndication_foundry_workflow.py)

**EN:** Lead Arranger (Foundry) → A2A to partner (wrapped, degrades to REFER) → Synthesizer
(Foundry); decision deterministic. **ID:** Lead Arranger (Foundry) → A2A ke partner (dibungkus,
turun ke REFER bila gagal) → Synthesizer (Foundry); keputusan deterministik.

```python
invitation = await _call("arrange", "LeadArranger", "syndication-lead-arranger", …)
try:
    a2a_meta = await a2a_send(settings.partner_a2a_url, json.dumps(deal_payload))   # A2A (unchanged)
    offer    = json.loads(a2a_meta["reply_text"])
except Exception:
    offer = None                                                 # graceful degrade
summary = await _call("finalize", "SyndicationSynthesizer", "syndication-synthesizer", …)
```

---

## Where every number on the page comes from / Asal setiap angka di halaman

| UI element | Source |
|---|---|
| Decision badge | deterministic `pol[...]` / result `decision` |
| 4 findings / transcript | Foundry agents' `output_text` |
| **Total token** | `cost.summary()["total_tokens"]` (sum of `response.usage`) |
| **Est. biaya (USD)** | `cost.summary()["estimated_cost_usd"]` (see [doc 07](07-governance-token-cost-foundry.md)) |
| Audit table | `get_audit_logger().events_for(request_id)` |
| Technical log | `render_tech_log(request_id)` — entries `tool="foundry:agent"` |

Next: [07-governance-token-cost-foundry.md](07-governance-token-cost-foundry.md).
