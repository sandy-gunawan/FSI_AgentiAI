"""bcafinance portal entrypoint — Invoice Financing Document Review.

Grouped navigation over the invoice-review page, governance, and docs. Agents are
hosted in Microsoft Foundry (v2 pattern); this app orchestrates and governs.
"""
from __future__ import annotations

import streamlit as st

from app.observability.otel_setup import setup_observability
from app.portal.theme import inject_theme

st.set_page_config(page_title="BCA Finance · Invoice Review", page_icon="🧾", layout="wide")
setup_observability()
inject_theme()

home = st.Page("views/0_Home.py", title="Beranda", icon="🏠", default=True)
review = st.Page("views/1_Invoice_Review.py", title="Review Faktur (Agen)", icon="🧾")
policy = st.Page("views/4_Policy.py", title="Kebijakan Review", icon="⚙️")
database = st.Page("views/5_Database.py", title="Database (SQL)", icon="🗄️")
audit = st.Page("views/2_Audit_Governance.py", title="Audit & Governance", icon="🛡️")
about = st.Page("views/3_About.py", title="Arsitektur & Cara Kerja", icon="📖")

pg = st.navigation({
    "🏠 Beranda": [home],
    "🧾 Pembiayaan Faktur": [review, policy, database],
    "🛡️ Governance": [audit],
    "📖 Belajar": [about],
})
pg.run()
