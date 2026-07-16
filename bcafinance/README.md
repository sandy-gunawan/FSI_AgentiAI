# BCA Finance — Agentic Invoice Financing Review

A **self-contained** agentic demo (sibling of the parent `finance` project) for a real
Indonesian financing use case: **invoice financing / anjak piutang**.

> An external system sends an invoice image → **Agent 1** extracts the details →
> **Agent 2** reviews them against policy + data-sufficiency → (optional) **Agent 3**
> enriches with structured data from **SQL Server** → a **deterministic rules engine**
> issues the binding decision (APPROVE / REFER / REJECT).

Three extraction modes, switchable in the UI:

| | Mode A · DI direct | Mode A+ · DI agentic | Mode B · Multimodal |
|---|--------------------|----------------------|---------------------|
| **Who calls DI** | Python orchestrator | **Agent 1 (tool call)** | nobody (vision reads image) |
| **Agent 1** | `bca-invoice-extractor-di` | `bca-invoice-extractor-di-agentic` | `bca-invoice-extractor-vision` |
| **Agent 2** | `bca-invoice-reviewer` (shared) | `bca-invoice-reviewer` (shared) | `bca-invoice-reviewer` (shared) |
| **Truly agentic extract** | partial | ✅ yes | ✅ yes |

Both agents are **hosted in Microsoft Foundry** (never built in code) and invoked by
reference. Policy is **config-driven** and changeable **on the fly** (local YAML or Blob).

---

## Quick start (local, Windows PowerShell)

```powershell
cd bcafinance
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env      # then fill FOUNDRY_PROJECT_ENDPOINT (+ DOC_INTELLIGENCE_ENDPOINT for Option A)

python scripts/generate_sample_invoices.py     # 20 sample invoices (PDF+PNG)
az login                                        # DefaultAzureCredential for Foundry
python scripts/provision_agents.py              # create the 3 agents in Foundry (once)

$env:PYTHONPATH="."
streamlit run app/portal/Home.py --server.port 8502
```

Open http://localhost:8502 → **🧾 Review Faktur (Agen)**, pick Option A/B, choose a sample, run.

### Offline sanity check (no Azure needed)

```powershell
$env:PYTHONPATH="."; python scripts/smoke_offline.py
```

---

## Project layout

```
bcafinance/
  app/
    core/        config.py · models.py
    governance/  audit_log.py · cost_tracker.py · tech_log.py
    observability/ otel_setup.py
    agents/
      invoice/   agents.py           # 3 agent instruction strings (source of truth)
      shared/    foundry_runner.py   # calls Foundry agents by reference
    tools/       doc_intelligence.py · vision (in runner) · json_utils.py
    review/      rules_engine.py     # config-driven decision + prompt injection
    workflows/   invoice_review_workflow.py   # 2-agent orchestration
    portal/      Home.py · theme.py · flow_viz.py · views/*
  config/        review_rules.yaml   # editable policy (hot-reload)
  scripts/       provision_agents.py · generate_sample_invoices.py · smoke_offline.py
  infra/         azure-setup.ps1     # same resource group as parent
  docs/          01..08 newbie guides + diagrams
```

See [docs/README.md](docs/README.md) for the full, newbie-friendly walkthrough.

## Azure services (all in `rg-finance-agenticai`)

- Microsoft **Foundry** project `financing` (reused) — hosts the 3 prompt agents
- Azure AI **Document Intelligence** — Option A OCR
- **Blob Storage** — invoice images + hot-reloadable `review_rules.yaml`
- **Container Apps** — `ca-bcafinance-portal`
- **Application Insights** — app telemetry (Foundry Traces cover the agent side)
