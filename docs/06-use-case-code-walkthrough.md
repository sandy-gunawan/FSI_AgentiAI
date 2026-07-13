# 6 · Use Case Code Walkthrough (EN/ID)

This document is the implementation companion to [03-use-cases.md](03-use-cases.md).
It focuses on code traceability:

- Which page calls which workflow
- Which agents and tools are actually used
- Where deterministic decisions happen
- Where users can see token, cost, and timing numbers

Dokumen ini melengkapi [03-use-cases.md](03-use-cases.md) dari sisi implementasi kode:

- Halaman portal mana memanggil workflow mana
- Agen dan tool mana yang benar-benar dipakai
- Di mana keputusan deterministik dijalankan
- Di mana user melihat angka token, biaya, dan durasi

---

## Quick Map (EN)

| Use case | Portal page | Workflow entry | Pattern | Human gate |
|---|---|---|---|---|
| Retail loan | [app/portal/views/1_Retail_Loan.py](../app/portal/views/1_Retail_Loan.py) | [run_retail](../app/workflows/retail_workflow.py) | Sequential | No |
| SME underwriting | [app/portal/views/2_SME_Underwriting.py](../app/portal/views/2_SME_Underwriting.py) | [run_sme_analysis](../app/workflows/sme_workflow.py), [resume_sme_with_decision](../app/workflows/sme_workflow.py) | Concurrent + resume | Yes |
| Customer servicing | [app/portal/views/4_Customer_Servicing.py](../app/portal/views/4_Customer_Servicing.py) | [run_servicing](../app/workflows/servicing_workflow.py) | Routing | No |
| Restructuring | [app/portal/views/5_Restructuring.py](../app/portal/views/5_Restructuring.py) | [run_restructure](../app/workflows/restructure_workflow.py) | Evaluator-optimizer loop | No |
| AML investigation | [app/portal/views/6_AML_Investigation.py](../app/portal/views/6_AML_Investigation.py) | [run_aml_investigation](../app/workflows/aml_workflow.py), [resume_aml_with_decision](../app/workflows/aml_workflow.py) | ReAct + resume | Yes |
| Credit committee | [app/portal/views/7_Credit_Committee.py](../app/portal/views/7_Credit_Committee.py) | [run_committee](../app/workflows/committee_workflow.py) | Group chat | No |
| Complex investigation | [app/portal/views/8_Complex_Investigation.py](../app/portal/views/8_Complex_Investigation.py) | [run_magentic](../app/workflows/magentic_workflow.py) | Magentic manager-worker | No |
| Syndication A2A | [app/portal/views/9_Syndication_A2A.py](../app/portal/views/9_Syndication_A2A.py) | [run_syndication](../app/workflows/a2a_workflow.py) | A2A cross-org | No |

## Line-Anchored Code Jumps (EN)

- Retail entry: [run_retail](../app/workflows/retail_workflow.py#L42)
- SME phase A: [run_sme_analysis](../app/workflows/sme_workflow.py#L57)
- SME phase B: [resume_sme_with_decision](../app/workflows/sme_workflow.py#L216)
- Servicing router flow: [run_servicing](../app/workflows/servicing_workflow.py#L42)
- Restructure loop: [run_restructure](../app/workflows/restructure_workflow.py#L42)
- AML phase A: [run_aml_investigation](../app/workflows/aml_workflow.py#L36)
- AML phase B: [resume_aml_with_decision](../app/workflows/aml_workflow.py#L112)
- Committee group chat: [run_committee](../app/workflows/committee_workflow.py#L46)
- Magentic manager-worker flow: [run_magentic](../app/workflows/magentic_workflow.py#L71)
- A2A syndication: [run_syndication](../app/workflows/a2a_workflow.py#L35)

## Tautan Baris Kode (ID)

Gunakan daftar di atas untuk lompat langsung ke fungsi utama setiap use case.

## Peta Cepat (ID)

Semua use case masuk dari halaman Streamlit lalu memanggil workflow async.
Alur orkestrasi ada di folder [app/workflows](../app/workflows), sedangkan instruksi agen ada di [app/agents](../app/agents).

---

## Shared Runtime Path (EN)

Every use case runs through the same runtime wrapper:

1. Open session via [financing_session](../app/agents/shared/model_client.py)
2. Run one or more agent steps via [AgentRunner.run](../app/agents/shared/model_client.py)
3. Capture per-step tokens and audit events
4. Return workflow result + cost summary

Shared components:

- Model runtime and usage capture: [app/agents/shared/model_client.py](../app/agents/shared/model_client.py)
- Audit persistence: [app/governance/audit_log.py](../app/governance/audit_log.py)
- Cost and budget: [app/governance/cost_tracker.py](../app/governance/cost_tracker.py)
- Technical tool call log: [app/governance/tech_log.py](../app/governance/tech_log.py)

Runtime anchors:

- Tool middleware capture: [app/agents/shared/model_client.py#L39](../app/agents/shared/model_client.py#L39)
- Agent runtime class: [app/agents/shared/model_client.py#L58](../app/agents/shared/model_client.py#L58)
- Per-step run method: [app/agents/shared/model_client.py#L70](../app/agents/shared/model_client.py#L70)
- Usage field extraction: [app/agents/shared/model_client.py#L91](../app/agents/shared/model_client.py#L91)
- Session scope wrapper: [app/agents/shared/model_client.py#L118](../app/agents/shared/model_client.py#L118)

## Jalur Runtime Umum (ID)

Semua use case memakai jalur runtime yang sama: buka session, jalankan step agen, simpan audit/token, lalu kembalikan hasil + ringkasan biaya.

---

## Use Case 1 · Retail Personal Loan

### EN: Code POV

- Entry page: [app/portal/views/1_Retail_Loan.py](../app/portal/views/1_Retail_Loan.py)
- Workflow: [run_retail](../app/workflows/retail_workflow.py)
- Agent instruction constants: [app/agents/retail/agents.py](../app/agents/retail/agents.py)
- Tools used:
  - KYC MCP and account summary in intake stage
  - Credit bureau MCP in credit stage
- Deterministic gate:
  - Policy decision is enforced by [evaluate_retail](../app/workflows/retail_workflow.py) and compliance result
- Outputs:
  - Decision object and optional offer (approve/decline/refer)
- Where user sees numbers:
  - Token, estimated cost, budget progress, and technical log on the same page

### ID: Detail Implementasi

- Halaman: [app/portal/views/1_Retail_Loan.py](../app/portal/views/1_Retail_Loan.py)
- Fungsi utama: [run_retail](../app/workflows/retail_workflow.py)
- Keputusan compliance dipaksa lewat rule deterministik, bukan bebas diputus LLM
- Metrik token, estimasi biaya USD, persentase budget, dan log teknis tampil langsung di halaman ini

---

## Use Case 2 · SME Underwriting

### EN: Code POV

- Entry page: [app/portal/views/2_SME_Underwriting.py](../app/portal/views/2_SME_Underwriting.py)
- Workflow phase A: [run_sme_analysis](../app/workflows/sme_workflow.py)
- Workflow phase B: [resume_sme_with_decision](../app/workflows/sme_workflow.py)
- Pattern:
  - Four specialists run concurrently via gather
  - Aggregate result is persisted as pending human case
- Human gate persistence:
  - Case storage in [app/workflows/case_store.py](../app/workflows/case_store.py)
- Deterministic policy gate:
  - Prescreen decision from policy evaluation before final recommendation
- Metrics:
  - Tokens/cost shown after phase A and phase B; technical call log is renderable per request

### ID: Detail Implementasi

- Pola utamanya paralel: 4 agen spesialis jalan bersamaan, lalu hasil digabung
- Setelah fase analisis, kasus disimpan status pending dan menunggu keputusan petugas kredit
- Saat resume, term sheet dibentuk sesuai keputusan manusia
- Total token kasus akan bertambah lintas fase karena case store menambahkan token fase lanjutan

---

## Use Case 3 · Smart Customer Servicing

### EN: Code POV

- Entry page: [app/portal/views/4_Customer_Servicing.py](../app/portal/views/4_Customer_Servicing.py)
- Workflow: [run_servicing](../app/workflows/servicing_workflow.py)
- Routing map:
  - Intent is classified first, then dispatched through handler dictionary
- Tool usage depends on selected intent handler
- Metrics are shown in page summary and technical log panel

### ID: Detail Implementasi

- Router hanya memilih satu intent, lalu satu handler yang dijalankan
- Karena single-path, token biasanya lebih efisien dibanding pola paralel
- Bukti API/MCP call bisa dilihat dari log teknis per request

---

## Use Case 4 · Loan Restructuring

### EN: Code POV

- Entry page: [app/portal/views/5_Restructuring.py](../app/portal/views/5_Restructuring.py)
- Workflow: [run_restructure](../app/workflows/restructure_workflow.py)
- Loop behavior:
  - Proposer creates a scheme
  - Deterministic affordability recompute is applied
  - Evaluator critiques and loop continues up to max iterations
- Deterministic calculations include monthly installment and DBR checks

### ID: Detail Implementasi

- Ini pola iteratif propose-evaluate
- Putaran pertama sengaja konservatif, lalu bisa direvisi sampai batas iterasi
- Lolos/tidaknya affordability ditentukan rule deterministik, bukan semata opini model

---

## Use Case 5 · AML Investigation

### EN: Code POV

- Entry page: [app/portal/views/6_AML_Investigation.py](../app/portal/views/6_AML_Investigation.py)
- Workflow phase A: [run_aml_investigation](../app/workflows/aml_workflow.py)
- Workflow phase B: [resume_aml_with_decision](../app/workflows/aml_workflow.py)
- ReAct behavior:
  - Investigator dynamically selects tools based on intermediate observations
- Deterministic escalation:
  - Sanctions hit can force SAR filing recommendation
- Human gate:
  - AML analyst decision is persisted before final filing narrative

### ID: Detail Implementasi

- Investigasi tahap awal bersifat dinamis: urutan tool tidak fixed
- Setelah rekomendasi dibuat, keputusan final tetap lewat analis AML (human-in-the-loop)
- Resume tahap akhir menyusun narasi filing atau penutupan kasus

---

## Use Case 6 · Credit Committee

### EN: Code POV

- Entry page: [app/portal/views/7_Credit_Committee.py](../app/portal/views/7_Credit_Committee.py)
- Workflow: [run_committee](../app/workflows/committee_workflow.py)
- Group chat pattern:
  - Multi-round debate with shared transcript
  - Chair synthesizes final decision
- Guardrail:
  - Deterministic prescreen can hard-block approval

### ID: Detail Implementasi

- Tiga peran debat berbagi transkrip yang sama setiap ronde
- Chair merangkum dan memutuskan, tetapi tetap terikat hard block dari rule deterministik

---

## Use Case 7 · Complex Investigation (Magentic)

### EN: Code POV

- Entry page: [app/portal/views/8_Complex_Investigation.py](../app/portal/views/8_Complex_Investigation.py)
- Workflow: [run_magentic](../app/workflows/magentic_workflow.py)
- Manager-worker pattern:
  - Manager plans ledger steps
  - Specialized workers execute tool-backed tasks
  - Manager may replan with bounded retries, then finalize dossier

### ID: Detail Implementasi

- Manager membuat task ledger dulu, bukan langsung eksekusi linear
- Worker dipilih sesuai assigned_to pada tiap step
- Replan dibatasi agar tetap terkendali biaya dan kompleksitas

---

## Use Case 8 · Syndication A2A

### EN: Code POV

- Entry page: [app/portal/views/9_Syndication_A2A.py](../app/portal/views/9_Syndication_A2A.py)
- Workflow: [run_syndication](../app/workflows/a2a_workflow.py)
- A2A path:
  - Build invitation locally
  - Discover partner agent card
  - Send A2A message and parse participation offer
  - Synthesize final structure
- A2A client code: [app/tools/a2a_client.py](../app/tools/a2a_client.py)

### ID: Detail Implementasi

- Use case ini satu-satunya yang benar-benar lintas organisasi lewat protokol A2A
- Partner agent dipanggil sebagai remote participant, bukan tool lokal MCP/REST biasa
- Hasil partner kemudian digabung ke keputusan sindikasi final

---

## Where to See Numbers (EN)

- Per request metrics and technical log on use-case pages (example retail):
  - [token metric](../app/portal/views/1_Retail_Loan.py#L120)
  - [estimated cost metric](../app/portal/views/1_Retail_Loan.py#L121)
  - [budget progress](../app/portal/views/1_Retail_Loan.py#L122)
  - [technical log render](../app/portal/views/1_Retail_Loan.py#L123)
- Governance dashboard aggregates:
  - [events load](../app/portal/views/3_Audit_Governance.py#L18)
  - [total token aggregate metric](../app/portal/views/3_Audit_Governance.py#L32)
  - [SME case list](../app/portal/views/3_Audit_Governance.py#L72)
  - [AML case list](../app/portal/views/3_Audit_Governance.py#L75)
- Technical log renderer used across pages:
  - [app/portal/portal_utils.py#L30](../app/portal/portal_utils.py#L30)

## Tempat Melihat Angka (ID)

- Angka per request: halaman use case masing-masing
- Rekap lintas request: dashboard governance
- Detail call API/MCP/A2A plus latency: panel log teknis

Lanjut ke [07-governance-token-cost.md](07-governance-token-cost.md) untuk detail cara angka dihitung dan validasi realness.