"""BNS Agentic AI Financing — portal entrypoint with grouped navigation.

Uses st.navigation to organise the seven use cases into orchestration groups
(leaving room for a future A2A / Interoperability section).
"""
from __future__ import annotations

import streamlit as st

from app.observability.otel_setup import setup_observability

st.set_page_config(page_title="BNS Agentic Financing", page_icon="🏦", layout="wide")
setup_observability()

# ---- Pages (paths relative to this entrypoint's folder: app/portal/) --------- #
home = st.Page("views/0_Home.py", title="Beranda", icon="🏠", default=True)

retail = st.Page("views/1_Retail_Loan.py", title="Kredit Ritel — Sequential", icon="👤")
sme = st.Page("views/2_SME_Underwriting.py", title="Pembiayaan UKM — Concurrent", icon="🏢")
servicing = st.Page("views/4_Customer_Servicing.py", title="Layanan Nasabah — Routing/Handoff", icon="🎧")

restructure = st.Page("views/5_Restructuring.py", title="Restrukturisasi — Evaluator–Optimizer", icon="♻️")
aml = st.Page("views/6_AML_Investigation.py", title="Investigasi AML — ReAct", icon="🕵️")
committee = st.Page("views/7_Credit_Committee.py", title="Komite Kredit — Group Chat", icon="⚖️")
magentic = st.Page("views/8_Complex_Investigation.py", title="Investigasi Kompleks — Magentic", icon="🧠")

syndication = st.Page("views/9_Syndication_A2A.py", title="Sindikasi — A2A (Agent2Agent)", icon="🔗")

audit = st.Page("views/3_Audit_Governance.py", title="Audit & Governance", icon="🛡️")
faq = st.Page("views/10_FAQ.py", title="FAQ & Referensi", icon="📖")

sme_foundry = st.Page("views/11_SME_on_Foundry.py", title="UKM — Agen di Foundry (v2)", icon="🟣")

pg = st.navigation(
    {
        "🏠 Beranda": [home],
        "🧭 Orkestrasi — Dasar": [retail, sme, servicing],
        "🧠 Orkestrasi — Lanjutan": [restructure, aml, committee, magentic],
        "🔗 Interoperabilitas (A2A)": [syndication],
        "� Hosted di Foundry (v2)": [sme_foundry],
        "�🛡️ Governance": [audit],
        "📖 Belajar": [faq],
    }
)
pg.run()
