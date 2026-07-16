"""Architecture & how-it-works — in-app explainer with diagrams."""
from __future__ import annotations

import streamlit as st

from app.portal.theme import hero, inject_theme

inject_theme()
hero("📖 Arsitektur & Cara Kerja", "Bagaimana dua agen Foundry + mesin aturan bekerja, dan "
     "beda Opsi A vs B.")

st.markdown(
    "<div class='bca-card'><h4>Alur end-to-end</h4>"
    "Sistem eksternal mengirim gambar faktur → <b>Agen 1</b> mengekstrak field → "
    "<b>Agen 2</b> menilai kelengkapan & kepatuhan kebijakan → <b>mesin aturan</b> "
    "menghitung keputusan mengikat (APPROVE/REFER/REJECT).</div>",
    unsafe_allow_html=True,
)

st.markdown("#### Diagram alur")
st.graphviz_chart("""
digraph {
  rankdir=LR; node [shape=box style="rounded,filled" fontname="Segoe UI" fillcolor="#E8F1FC" color="#1565C0"];
  up [label="Unggah faktur"]; sw [label="Pilih Opsi A/B"];
  di [label="Document Intelligence\\n(Opsi A)" fillcolor="#FBF3E0" color="#B8860B"];
  mm [label="Model Vision\\n(Opsi B)" fillcolor="#FBF3E0" color="#B8860B"];
  a1 [label="Agen 1\\nEkstraksi (Foundry)"];
  a2 [label="Agen 2\\nReviewer (Foundry)"];
  rl [label="Rules engine\\n(config-driven)" fillcolor="#EAF6EE" color="#1B873F"];
  out [label="Keputusan +\\nReview" fillcolor="#EAF6EE" color="#1B873F"];
  up -> sw; sw -> di; sw -> mm; di -> a1; mm -> a1; a1 -> a2; a2 -> rl; rl -> out;
}
""")

c1, c2 = st.columns(2)
with c1:
    st.markdown(
        "<div class='bca-card'><h4>🅰️ Document Intelligence — kelebihan</h4>"
        "<ul><li>Deterministik & dapat diaudit</li><li>Skor keyakinan per field</li>"
        "<li>Lebih murah & cepat di skala besar</li><li>Risiko halusinasi rendah</li></ul>"
        "<b>Kekurangan:</b> perlu model terlatih untuk dokumen non-standar; rigid.</div>",
        unsafe_allow_html=True)
with c2:
    st.markdown(
        "<div class='bca-card'><h4>🅱️ Multimodal — kelebihan</h4>"
        "<ul><li>Tanpa pelatihan; fleksibel</li><li>Menangani foto/tata letak baru</li>"
        "<li>Menalar konteks gambar</li></ul>"
        "<b>Kekurangan:</b> non-deterministik, bisa berhalusinasi, tanpa confidence native, "
        "lebih mahal per gambar.</div>",
        unsafe_allow_html=True)

st.markdown(
    "<div class='bca-card'><h4>🔧 Kebijakan yang dapat diubah on-the-fly (2 lapis)</h4>"
    "<b>Lapis 1 (stabil):</b> peran & skema output agen — tersimpan sebagai versi agen di Foundry. "
    "Ubah = provisioning ulang.<br>"
    "<b>Lapis 2 (dinamis):</b> parameter kebijakan di <code>config/review_rules.yaml</code> "
    "(atau Blob) — dibaca <b>fresh tiap request</b>, disuntikkan ke prompt reviewer & dipakai "
    "mesin aturan. Ubah nilai → keputusan berubah <b>tanpa deploy/provisioning ulang</b>.</div>",
    unsafe_allow_html=True,
)

st.info("Detail lengkap (newbie-friendly) ada di folder `docs/` — 01..08 + diagram.")
