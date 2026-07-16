"""Landing page — overview of the invoice-review demo."""
from __future__ import annotations

import streamlit as st

from app.portal.theme import hero, inject_theme

inject_theme()
hero(
    "BCA Finance · Review Pembiayaan Faktur (Agentic)",
    "Sistem eksternal mengirim gambar faktur → Agen 1 mengekstrak data → Agen 2 menilai "
    "kelengkapan & kepatuhan kebijakan → keputusan deterministik. Dua opsi ekstraksi.",
    ["Anjak Piutang / Invoice Financing", "2 Agen di Microsoft Foundry", "OJK/BI-aware",
     "Governance + Observability"],
)

c1, c2 = st.columns(2)
with c1:
    st.markdown(
        "<div class='bca-card'><h4>🅰️ Opsi A — Document Intelligence</h4>"
        "OCR deterministik (model <code>prebuilt-invoice</code>) menghasilkan field + "
        "skor keyakinan. <b>Agen 1</b> menormalisasi ke skema kanonik. Cocok untuk volume "
        "besar, dokumen terstruktur, dan audit yang ketat.</div>",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        "<div class='bca-card'><h4>🅱️ Opsi B — Multimodal</h4>"
        "Model vision (gpt-4o / gpt-4o-mini) <b>membaca gambar langsung</b>. Tanpa pelatihan, "
        "fleksibel untuk tata letak baru / foto / dokumen tidak standar. Perlu guardrail "
        "karena non-deterministik.</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    "<div class='bca-card'><h4>Alur singkat</h4>"
    "<ol>"
    "<li><b>Unggah</b> faktur (PDF/PNG/JPG) atau pilih contoh.</li>"
    "<li>Pilih <b>Opsi A / B</b> lalu jalankan.</li>"
    "<li><b>Agen 1</b> → JSON kanonik · <b>Agen 2</b> → review kebijakan · "
    "<b>Rules engine</b> → APPROVE / REFER / REJECT.</li>"
    "<li>Lihat token, biaya, jejak audit, log teknis, dan Foundry Traces.</li>"
    "</ol></div>",
    unsafe_allow_html=True,
)

st.info("Buka **🧾 Review Faktur (Agen)** di sidebar untuk mulai. Kebijakan dapat diubah "
        "on-the-fly di `config/review_rules.yaml` (atau Blob) tanpa deploy ulang.")
