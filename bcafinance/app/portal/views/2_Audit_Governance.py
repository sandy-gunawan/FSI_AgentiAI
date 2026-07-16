"""Audit & Governance — recent requests, decisions, and token usage."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.governance.audit_log import get_audit_logger
from app.portal.theme import hero, inject_theme

inject_theme()
hero("🛡️ Audit & Governance", "Setiap langkah agen, ekstraksi, dan keputusan tercatat "
     "(append-only) di SQLite lokal / PostgreSQL di cloud.")

rows = get_audit_logger().recent(limit=400)
if not rows:
    st.info("Belum ada aktivitas. Jalankan sebuah review di halaman **🧾 Review Faktur**.")
    st.stop()

df = pd.DataFrame(rows)

c1, c2, c3 = st.columns(3)
c1.metric("Total event", len(df))
c2.metric("Permohonan unik", df["request_id"].nunique())
c3.metric("Total token", f"{int(df['tokens'].sum()):,}")

st.markdown("#### Keputusan final terbaru")
finals = df[df["step"] == "final"][["request_id", "actor", "decision", "tokens", "ts"]]
st.dataframe(finals, use_container_width=True, hide_index=True)

st.markdown("#### Semua event")
st.dataframe(df[["request_id", "step", "actor", "decision", "tokens", "detail", "ts"]],
             use_container_width=True, hide_index=True)
