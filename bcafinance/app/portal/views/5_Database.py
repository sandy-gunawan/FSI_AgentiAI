"""Database viewer — browse the seeded SQL Server 2019 tables from the portal.

Read-only. Calls the credit-context service (`SQL_TOOLS_URL`):
  GET  /health         → seed status + row counts
  GET  /admin/tables   → every row of all 7 tables
  POST /admin/reseed    → reset to the pristine demo data
The database itself has no public port; this page reaches it through the service.
"""
from __future__ import annotations

import httpx
import pandas as pd
import streamlit as st

from app.core.config import get_settings
from app.portal.theme import hero, inject_theme, metric_tile

inject_theme()
hero("🗄️ Database Konteks Kredit (SQL Server 2019)",
     "Lihat data terstruktur yang dibaca agen lewat REST / MCP · read-only",
     ["7 tabel", "localhost:1433 di dalam container", "data seed contoh"])

settings = get_settings()

if not settings.sql_tools_configured:
    st.warning("`SQL_TOOLS_URL` belum diset — layanan konteks kredit tidak dikonfigurasi. "
               "Set env `SQL_TOOLS_URL` ke URL app `ca-bcafinance-sql` untuk melihat database.")
    st.stop()

base = settings.sql_tools_url.rstrip("/")
st.caption(f"Sumber: `{base}` · database `bcacredit`")


def _get(path: str) -> dict:
    resp = httpx.get(f"{base}{path}", timeout=30)
    resp.raise_for_status()
    return resp.json()


c1, c2 = st.columns([1, 1])
with c1:
    if st.button("🔄 Muat ulang data", use_container_width=True):
        st.rerun()
with c2:
    if st.button("♻️ Reset ke data contoh (reseed)", use_container_width=True):
        try:
            httpx.post(f"{base}/admin/reseed", timeout=120).raise_for_status()
            st.success("Database di-seed ulang ke data contoh.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Gagal reseed: {exc}")

# ---- Health / seed status -------------------------------------------------- #
try:
    health = _get("/health")
except Exception as exc:  # noqa: BLE001
    st.error(f"Tidak bisa menghubungi layanan SQL: {exc}\n\n"
             "Jika app di-scale ke nol, tunggu ~30–60 dtk (cold start SQL Server) lalu muat ulang.")
    st.stop()

if not health.get("seeded"):
    st.info("Database sedang di-seed… tunggu beberapa detik lalu **Muat ulang data**. "
            f"({health.get('error') or 'startup'})")

counts = health.get("counts", {})
if counts:
    cols = st.columns(len(counts))
    for col, (name, n) in zip(cols, counts.items()):
        metric_tile(col, name, f"{n:,}")

# ---- Tables ---------------------------------------------------------------- #
_LABELS = {
    "clients": "clients — penjual (yang minta pembiayaan)",
    "facilities": "facilities — plafon kredit tiap klien",
    "buyers": "buyers — pembeli (yang harus bayar faktur)",
    "buyer_exposure": "buyer_exposure — eksposur berjalan per pembeli",
    "payment_behaviour": "payment_behaviour — riwayat perilaku bayar",
    "invoice_history": "invoice_history — faktur yang sudah terlihat (deteksi duplikat)",
    "watchlist": "watchlist — screening sanksi (DTTOT/PPATK)",
}

try:
    data = _get("/admin/tables")
except Exception as exc:  # noqa: BLE001
    st.error(f"Tidak bisa mengambil tabel: {exc}")
    st.stop()

st.markdown(f"### Isi tabel · database `{data.get('database', 'bcacredit')}`")
tables = data.get("tables", {})
for name, label in _LABELS.items():
    rows = tables.get(name, [])
    with st.expander(f"📋 {label}  ·  {len(rows)} baris", expanded=(name == "buyers")):
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("Tidak ada baris.")

st.info("🔒 Read-only: port SQL (1433) tidak terekspos ke internet. Halaman ini membaca "
        "database lewat endpoint `/admin/tables` pada layanan `ca-bcafinance-sql`. "
        "Detail: lihat dok **11 · Database di dalam container**.")
