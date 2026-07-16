"""Policy editor — change the review rules on the fly (no redeploy, no Blob needed).

Edits are written to config/review_rules.yaml, which the rules engine reads FRESH on
every request. So the next review run immediately uses the new policy. This replaces
the need to toggle Blob/storage to public just to change configuration.
"""
from __future__ import annotations

import streamlit as st

from app.portal.portal_utils import rupiah
from app.portal.theme import hero, inject_theme
from app.review import rules_engine

inject_theme()
hero("⚙️ Kebijakan Review (on-the-fly)",
     "Ubah parameter kebijakan di sini → langsung dipakai pada review berikutnya. "
     "Tanpa deploy ulang, tanpa Blob, tanpa mengubah storage jadi publik.",
     ["Layer 2: parameter dinamis", "Dibaca fresh tiap request"])

st.info("💡 **Kenapa tidak lewat Blob?** Storage di langganan ini dikunci privat oleh "
        "kebijakan (policy) dan environment Container Apps tidak ber-VNet, jadi Blob publik "
        "tidak memungkinkan/aman. Editor ini mencapai tujuan yang sama — mengubah kebijakan "
        "secara langsung — tanpa menyentuh jaringan storage.")

rules = rules_engine.load_rules()
p = rules["policy"]

st.markdown("#### Parameter kebijakan")
c1, c2 = st.columns(2)
with c1:
    max_facility = st.number_input(
        "Batas fasilitas maksimal (IDR)", min_value=0, step=50_000_000,
        value=int(p["max_facility_idr"]),
        help="Faktur di atas nilai ini → REJECT (pelanggaran keras).")
    st.caption(f"= {rupiah(max_facility)}")
    advance_rate = st.slider("Advance rate", 0.0, 1.0, float(p["advance_rate"]), step=0.05,
                             help="Porsi nilai faktur yang dicairkan.")
    max_tenor = st.number_input("Tenor maksimal (hari)", min_value=1, max_value=365,
                                value=int(p["max_tenor_days"]),
                                help="issue_date → due_date lebih dari ini → REJECT.")
with c2:
    min_conf = st.slider("Keyakinan minimal per field", 0.0, 1.0, float(p["min_confidence"]),
                         step=0.05, help="Field wajib di bawah ini → REFER.")
    max_conc = st.slider("Batas konsentrasi pembeli (info)", 0.0, 1.0,
                         float(p.get("max_buyer_concentration", 0.4)), step=0.05)

st.markdown("#### Field wajib")
all_fields = ["invoice_number", "issue_date", "due_date", "total_amount_idr",
              "seller_name", "buyer_name", "buyer_npwp", "po_number"]
required = st.multiselect("Field yang wajib ada & terbaca yakin", all_fields,
                          default=list(rules["required_fields"]))

st.markdown("#### Panduan reviewer (disuntikkan ke prompt agen)")
guidance = st.text_area("reviewer_guidance", value=rules["reviewer_guidance"], height=120)

colA, colB = st.columns([1, 3])
with colA:
    apply = st.button("💾 Terapkan sekarang", type="primary")
with colB:
    reset = st.button("↩️ Kembalikan ke default")

if apply:
    new_rules = {
        "policy": {
            "max_facility_idr": int(max_facility),
            "advance_rate": float(advance_rate),
            "max_tenor_days": int(max_tenor),
            "min_confidence": float(min_conf),
            "max_buyer_concentration": float(max_conc),
        },
        "required_fields": required,
        "reviewer_guidance": guidance,
    }
    rules_engine.save_rules(new_rules)
    st.success("✅ Kebijakan diperbarui. Review berikutnya langsung memakainya "
               "(dibaca ulang tiap request).")
    st.balloons()

if reset:
    rules_engine.save_rules({
        "policy": {"max_facility_idr": 1_000_000_000, "advance_rate": 0.80,
                   "max_tenor_days": 180, "min_confidence": 0.75, "max_buyer_concentration": 0.40},
        "required_fields": ["invoice_number", "issue_date", "due_date", "total_amount_idr",
                            "seller_name", "buyer_name", "buyer_npwp"],
        "reviewer_guidance": "Terapkan kebijakan anjak piutang BCA Finance sesuai norma OJK/BI.",
    })
    st.success("↩️ Dikembalikan ke default. Muat ulang halaman untuk melihat nilai.")

st.divider()
st.markdown("#### 👀 Blok POLICY yang akan disuntikkan ke agen reviewer")
st.code(rules_engine.policy_block(rules_engine.load_rules()), language="text")
