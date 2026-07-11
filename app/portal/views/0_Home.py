"""BNS Agentic AI Financing — portal home (Beranda)."""
from __future__ import annotations

import streamlit as st

from app.core.config import get_settings

settings = get_settings()

st.title("🏦 Bank Nusantara Sejahtera — Agentic AI Financing")
st.caption("Demo agentic AI untuk skenario pembiayaan (financing) — Indonesia · Microsoft Agent Framework")

st.markdown(
    """
Portal ini menjalankan **delapan use case agentic AI** di atas **Microsoft Agent Framework**
(backend Python, model di **Microsoft Foundry**), dengan sistem sekitar (data, REST API, MCP, dan
**A2A**) yang **di-host di cloud**. Tiap use case sengaja memakai **pola orkestrasi yang berbeda**,
dikelompokkan di menu samping.

### 🧭 Orkestrasi — Dasar
1. **Kredit Personal Ritel** — *Sequential* (rantai berurutan) · straight-through.
2. **Pembiayaan UKM/Komersial** — *Concurrent* (hub-and-spoke paralel) + **Human-in-the-loop**.
3. **Layanan Nasabah Cerdas** — *Routing* (versi sederhana dari **Handoff**).

### 🧠 Orkestrasi — Lanjutan
4. **Restrukturisasi Kredit** — *Evaluator–Optimizer* (loop refleksi). *Pola workflow, bukan salah satu dari 5 orkestrasi resmi MS.*
5. **Investigasi AML/Fraud** — *ReAct* (single-agent, tool dinamis) + **Human SAR gate**.
6. **Komite Kredit** — *Group Chat* (debat multi-agen dimoderasi Chair).
7. **Investigasi Kompleks** — *Magentic* (Manager + task ledger + replanning).

### 🔗 Interoperabilitas (A2A)
8. **Sindikasi / Co-Financing** — *A2A (Agent2Agent)*: BNS Lead Arranger mendelegasikan
   co-underwriting ke **agen bank lain** (di-deploy terpisah) via Agent Card + JSON-RPC. Beda dari
   MCP (agen→tool): A2A = **agen→agen** lintas-organisasi.

> **Istilah:** *Concurrent, Sequential, Handoff, Group Chat, Magentic* adalah **5 orkestrasi resmi
> Microsoft Agent Framework / Semantic Kernel**. *Routing, Evaluator–Optimizer, ReAct* adalah pola
> *workflow* umum (Anthropic) yang kami implementasikan sebagai pelengkap.

### Governance & Monitoring
- **Audit log** setiap langkah agen, tool, dan keputusan (halaman *Audit & Governance*)
- **Content safety + redaksi PII** (NIK, NPWP, telepon, email)
- **Human approval gate** (UKM & AML)
- **Policy engine** deterministik (OJK/BI)
- **Cost/token budget** per permohonan
- **OpenTelemetry → Azure Application Insights** + Aspire dashboard lokal
    """
)

col1, col2, col3 = st.columns(3)
col1.metric("Model (Foundry)", settings.foundry_model)
col2.metric("Surrounding systems", settings.rest_base_url.replace("https://", "").replace("http://", ""))
col3.metric("Token budget / request", f"{settings.token_budget_per_request:,}")

st.info("Gunakan menu berkelompok di sidebar. Baru mengenal agentic AI/MCP/A2A? Buka **📖 FAQ & Referensi** "
        "(tanya-jawab pemula→pakar, matriks keputusan, MCP vs A2A, cara menghubungkan).")
