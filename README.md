# Bank Nusantara Sejahtera (BNS) — Agentic AI Financing Demo 🇮🇩

A demo of **eight agentic AI use cases** for financial-services **financing** scenarios,
built on **Microsoft Agent Framework** (Python) with models on **Microsoft Foundry**.
Each use case intentionally showcases a **different agentic pattern** (incl. the 5 official
Microsoft/Semantic Kernel orchestrations and the **A2A / Agent2Agent** protocol).
Localized for **Indonesia** (IDR, NIK/NPWP, SLIK OJK, Dukcapil, DTTOT, PPATK, OJK/BI rules).

The **surrounding systems (data, REST APIs, MCP servers, and a partner-bank A2A agent) are hosted
on Azure**, so they are callable over HTTPS from any system — not just this app.

> 🧑‍💻 **New to the code?** Start with **[docs/](docs/README.md)** — it explains *what an "agent"
> actually is in this codebase* (there's no class-per-agent), how the Microsoft Agent Framework is
> called, the end-to-end request trace, and a diagrammed walkthrough of every use case.
>
> ☁️ **Need Azure deployment steps?** Follow **[docs/05-deploy-to-azure.md](docs/05-deploy-to-azure.md)**
> for beginner-friendly, copy-paste commands (build images, update Container Apps, set env vars,
> verify portal/systems/partner URLs).

---

## The five use cases

| # | Use case | Agentic pattern |
|---|----------|-----------------|
| 1 | Retail Personal Loan | **Prompt Chaining** (Sequential) |
| 2 | SME / Commercial Financing | **Orchestrator-Workers** (Concurrent) + Human-in-the-loop |
| 3 | Smart Customer Servicing | **Routing** (a simplified Handoff) |
| 4 | Loan Restructuring Advisor | **Evaluator–Optimizer** (reflection loop) |
| 5 | AML / Fraud Investigation | **ReAct** (autonomous tool use) + Human SAR gate |
| 6 | Credit Committee | **Group Chat** (moderated multi-agent debate) |
| 7 | Complex Investigation | **Magentic** (manager + task ledger + replanning) |
| 8 | Syndication / Co-Financing | **A2A (Agent2Agent)** — cross-organisation agent delegation |

> *Concurrent, Sequential, Handoff, Group Chat, Magentic* are the **5 official Microsoft Agent
> Framework / Semantic Kernel orchestrations**. *Routing, Evaluator–Optimizer, ReAct* are common
> workflow patterns. **A2A** is the open agent-to-agent interoperability protocol (Linux Foundation),
> complementary to **MCP** (agent→tools): here BNS's Lead Arranger delegates co-underwriting to a
> **separately-deployed partner-bank agent** (`ca-bns-partner`) via an **Agent Card + JSON-RPC
> `message/send`**.

### 1. Retail Personal Loan — *Prompt Chaining* ("serial") pipeline · straight-through
```
Intake ─► Credit Risk ─► Compliance (OJK/BI, deterministic) ─► Decision / Offer
```
No human in the loop. Applications at/above the OJK auto-approve ceiling are **referred** to human review.

### 2. SME / Commercial Financing — *Orchestrator-Workers* (hub-and-spoke) + **Human-in-the-loop**
```
                 ┌─► Financial Analyst ─┐
Orchestrator ────┼─► Collateral         ┼─► aggregate ─► Underwriting Recommendation
   (hub)         ├─► AML / Fraud        ┤                         │
                 └─► Market Risk  ──────┘                         ▼
                                                    🧑‍⚖️ Loan Officer decides
                                                    (approve / reject / request-info)
                                                                  │
                                                                  ▼
                                                            SME Term Sheet
```
The four specialists run **in parallel**; the case is **paused and persisted** until a human decides
(survives portal restarts via a persistent case store).

### 3. Smart Customer Servicing — *Routing*
```
Customer message ─► Router (classify intent) ─┬─► Dispute handler
                                              ├─► Limit-increase handler
                                              ├─► Hardship handler
                                              ├─► Balance handler
                                              └─► General handler
```
A Router agent classifies a free-text message into **one** intent; only the chosen handler runs.

### 4. Loan Restructuring Advisor — *Evaluator–Optimizer* (reflection loop)
```
Proposer ─► [deterministic affordability check] ─► Evaluator ─┐
   ▲                                                          │
   └──────────────── feedback (revise, ≤ 3 iters) ────────────┘  ─► Writer
```
The Proposer drafts a restructuring scheme; a deterministic policy check + an Evaluator agent critique it;
concrete feedback loops back until the scheme is affordable (or it is **referred** to a human officer).

### 5. AML / Fraud Investigation — *ReAct* (autonomous tool use) + **Human SAR gate**
```
Investigator ─(reason → act → observe loop, chooses tools dynamically)─► SAR Recommendation
                                                                              │
                                                        🧑‍⚖️ AML Analyst decides (file / dismiss / escalate)
                                                                              │
                                                                              ▼
                                                                     SAR / LTKM filing
```
A single Investigator agent decides which back-office tools to call based on what it observes; a human
analyst confirms filing (case paused & persisted, like Use Case 2).

---

## Architecture

```
┌──────────────────────────┐        ┌───────────────────────────────────────────┐
│  Streamlit Portal (ACA)  │        │  Surrounding Systems (ACA, public HTTPS)    │
│  ca-bns-portal           │        │  ca-bns-systems                             │
│                          │  REST  │   /core-banking  /collateral                │
│  Microsoft Agent         ├───────►│   /financials    /pricing                   │
│  Framework agents        │        │   /servicing     /monitoring                │
│                          │  MCP   │   /mcp/credit-bureau  (SLIK OJK/Pefindo)     │
│  + workflows             ├───────►│   /mcp/kyc-aml        (Dukcapil/DTTOT/PPATK) │
│                          │        │   /mcp/policy-rules   (OJK/BI engine)        │
│  Governance +            │        └───────────────────────────────────────────┘
│  OpenTelemetry           │        ┌───────────────────────────────────────────┐
│                          ├───────►│  Microsoft Foundry (gpt-4o-mini)            │
└─────────┬────────────────┘        │  Azure Content Safety · Application Insights│
          │  telemetry              └───────────────────────────────────────────┘
          └────────────────────────► Azure Monitor / App Insights (appi-finance-agenticai)
```

### Governance & monitoring (built in)
- **Audit log** — every agent step, tool call, and decision persisted (`data/audit.db`; SQLite → Azure PostgreSQL in prod).
- **Content safety + PII redaction** — Azure AI Content Safety + regex redaction of NIK/NPWP/phone/email.
- **Human approval gate** — Use Case 2 (loan officer) & Use Case 5 (AML analyst / SAR filing).
- **Deterministic policy engine** — OJK/BI rules (not the LLM) decide compliance, affordability, and AML sanctions escalation, so outcomes are reproducible & auditable.
- **Cost / token budget** — enforced per financing request.
- **OpenTelemetry** — GenAI traces/metrics/logs → **Application Insights** (and a local **Aspire** dashboard).

---

## Live Azure resources (redacted template)

| Resource | Name | Notes |
|---|---|---|
| Foundry (AI Services) | `<your-foundry-resource>` | project `<your-project>`, model `gpt-4o-mini` (GlobalStandard) |
| Container Apps env | `<your-containerapps-env>` | |
| **Surrounding systems** | `<your-systems-app>` | public — REST + MCP |
| **Portal** | `<your-portal-app>` | public — Streamlit, managed identity |
| Container Registry | `<your-acr-name>` | Basic |
| App Insights | `<your-appinsights-name>` | workspace-based |
| Log Analytics | `<your-loganalytics-name>` | |

**Public endpoints**
- Portal: `https://<your-portal-app-fqdn>`
- Systems (callable from any system): `https://<your-systems-app-fqdn>`
  - REST: `/core-banking/...`, `/collateral/...`, `/financials/...`, `/pricing/...`, `/servicing/...`, `/monitoring/...`, `/health`
  - MCP (Streamable HTTP): `/mcp/credit-bureau/`, `/mcp/kyc-aml/`, `/mcp/policy-rules/`

---

## Surrounding systems & data

All dummy data is generated deterministically by `mock_services/data/seed.py` (Faker `id_ID`, fixed seed),
with **intentional edge cases** (below-min income, high DBR, DTTOT sanctions hit, over-ceiling amount, PEP
director, PPATK STR flag, weak collateral, declining-revenue SME).

| System | Type | Data |
|---|---|---|
| Credit Bureau | MCP | SLIK OJK + Biro Kredit: score, grade, SLIK kol, debts, delinquencies |
| KYC / AML | MCP | Dukcapil verify, DTTOT sanctions, PPATK STR, PEP, adverse media |
| Policy Rules | MCP | OJK/BI thresholds + deterministic `evaluate_retail` / `evaluate_sme` / `evaluate_restructure` |
| Core Banking | REST | accounts + 6 months transactions |
| Collateral | REST | declared vs appraised value, LTV |
| Financials | REST | 3 years of SME statements |
| Pricing | REST | product catalog + quote (rate, installment) |
| Loan Servicing | REST | existing/outstanding facilities + arrears (restructuring) |
| Transaction Monitoring | REST | AML alerts & typologies (investigation) |

---

## Run locally

> Always use the virtual environment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1) Generate dummy data
python mock_services/data/seed.py

# 2) Start the surrounding systems (REST + MCP) locally on :8080
uvicorn mock_services.server:app --port 8080
#    then set REST_BASE_URL=http://localhost:8080 in .env

# 3) (optional) local telemetry dashboard
docker compose up -d aspire-dashboard    # Aspire UI on http://localhost:18888

# 4) Run the portal
streamlit run app/portal/Home.py
```

Configuration lives in `.env` (see `.env.example`). Auth uses `DefaultAzureCredential`
(`az login` locally, managed identity in Azure).

---

## Project layout

```
app/
  core/            config + pydantic domain models
  agents/          agent instructions (retail, sme, servicing, restructure, aml) + shared model client / runner
  tools/           REST function tools + MCP (Streamable HTTP) tool clients
  workflows/       retail (chaining) · sme (concurrent+HITL) · servicing (routing) ·
                   restructure (evaluator-optimizer) · aml (ReAct+HITL) orchestrators
  governance/      audit log · content safety/PII · cost tracker · rules engine
  observability/   OpenTelemetry / Azure Monitor setup
  portal/          Streamlit portal (Home entrypoint + grouped st.navigation over views/)
mock_services/
  server.py        combined ASGI app (REST + 3 MCP)  ← deployed to ACA
  rest_apis/       core banking, collateral, financials, pricing
  mcp_servers/     credit bureau, kyc/aml, policy rules (Streamable HTTP)
  policy.py        shared OJK/BI evaluation logic
  data/            seed.py + generated JSON datasets
Dockerfile.systems / Dockerfile.portal / docker-compose.yml
```

---

## Notes
- Smallest cost-effective SKUs: AI Services S0 (only tier), `gpt-4o-mini` GlobalStandard (pay-per-token),
  ACR Basic, ACA consumption (0.25–0.5 vCPU).
- This is a **demo** with synthetic data; not production financial advice. Implement your own
  responsible-AI mitigations, data controls, and security review before real use.
