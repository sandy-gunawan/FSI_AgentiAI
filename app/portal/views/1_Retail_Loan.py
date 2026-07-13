"""Use Case 1 — Retail personal loan (SEQUENTIAL) · single-window live view + log."""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.models import EmploymentType, RetailLoanApplication
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import RETAIL_DETAILS, FlowState, render_retail_html
from app.portal.portal_utils import render_audit_legend, render_gateway_toggle, render_pattern_explainer, render_tech_log, rupiah, run_async
from app.workflows import data_access as sor
from app.workflows.retail_workflow import run_retail

setup_observability()

st.title("👤 Kredit Personal Ritel — Sequential Pipeline")
st.caption("Intake → Credit Risk → Compliance (OJK/BI) → Decision/Offer · straight-through")

render_pattern_explainer(
    pattern="Prompt Chaining (Sequential / Serial)",
    what=("Beberapa agen dirangkai **berurutan** — keluaran satu agen menjadi masukan agen "
          "berikutnya. Konteks bertambah di tiap tahap, dan sebuah gerbang deterministik dapat "
          "menghentikan alur lebih awal."),
    flow="Intake ─► Credit Risk ─► Compliance (OJK/BI, deterministik) ─► Decision / Offer",
    how=("Agen **Intake** memverifikasi identitas & penghasilan → hasilnya dipakai agen **Credit "
         "Risk** untuk menilai kapasitas bayar (DBR) → **Compliance** menjalankan aturan OJK/BI "
         "(bukan LLM) untuk APPROVE/DECLINE/REFER → **Decision** menyusun penawaran & penjelasan. "
         "Tiap langkah menambah data untuk langkah berikutnya."),
    why=("Proses kredit ritel bersifat **linear, terstandar, dan straight-through**: langkahnya "
         "punya urutan wajib dan dependensi yang jelas. Pipeline serial adalah pola paling "
         "sederhana, paling mudah diaudit, dan paling deterministik untuk alur seperti ini — "
         "tanpa kompleksitas paralel atau loop yang tidak diperlukan."),
    ms_term="**Sequential** — salah satu dari 5 orkestrasi resmi Microsoft Agent Framework.",
)

VIZ_H = 720

# --- Sidebar form (keeps the live view + log in one window) ------------------ #
customers = sor.list_customers()
labels = {f"{c['customer_id']} — {c['full_name']}": c for c in customers}
with st.sidebar:
    st.header("📝 Form Pengajuan")
    pick = st.selectbox("Nasabah", list(labels.keys()))
    cust = labels[pick]
    amount = st.number_input("Jumlah (IDR)", min_value=5_000_000, max_value=300_000_000,
                             value=50_000_000, step=5_000_000)
    tenor = st.slider("Tenor (bulan)", 6, 36, 24, step=6)
    purpose = st.text_input("Tujuan", value="renovasi rumah")
    st.caption(f"Penghasilan: **{rupiah(cust['monthly_income_idr'])}/bln** · {cust['employment_type']}")
    submitted = st.button("▶️ Jalankan Agentic Assessment", type="primary", use_container_width=True)
    with st.expander("🧩 Agen yang terlibat & sistem yang dipanggil"):
        for title, desc in RETAIL_DETAILS:
            st.markdown(f"**{title}**  \n{desc}")

# --- One window: live diagram (left) + real-time log (right) ------------------ #
dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen — LIVE")
viz = dia.empty()
with viz:
    components.html(render_retail_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Log langkah agen (input · tool · output) akan tampil di sini saat dijalankan…")

via_apim = render_gateway_toggle("retail")
results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    application = RetailLoanApplication(
        customer_id=cust["customer_id"], full_name=cust["full_name"], nik=cust["nik"],
        dob=cust["dob"], employment_type=EmploymentType(cust["employment_type"]),
        monthly_income_idr=cust["monthly_income_idr"], requested_amount_idr=int(amount),
        tenor_months=int(tenor), purpose=purpose,
    )
    request_id = f"RET-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []
    fs = FlowState()

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        with viz:
            components.html(render_retail_html(fs.active, fs.done), height=VIZ_H)
        if detail:
            lines.insert(0, detail)
            with log_ph.container(height=VIZ_H):
                for ln in lines:
                    st.markdown(ln)

    decision, cost = run_async(run_retail(application, request_id, on_event=_on_event, via_apim=via_apim))
    with viz:
        components.html(render_retail_html(fs.active, fs.done), height=VIZ_H)

    with results:
        st.divider()
        color = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}[decision.decision.value]
        st.subheader(f"{color} Keputusan: {decision.decision.value}")
        st.write(decision.explanation)
        if decision.offer:
            o = decision.offer
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Plafon", rupiah(o.approved_amount_idr))
            m2.metric("Bunga p.a.", f"{o.annual_rate_pct}%")
            m3.metric("Angsuran/bln", rupiah(o.monthly_installment_idr))
            m4.metric("Total bayar", rupiah(o.total_repayment_idr))
        a1, a2 = st.columns([3, 1])
        with a1:
            st.markdown("**Jejak audit (per langkah agen):**")
            events = get_audit_logger().events_for(request_id)
            st.dataframe(
                [{"step": e["step"], "actor": e["actor"], "decision": e["decision"],
                  "tokens": e["tokens"], "detail": e["detail"]} for e in events],
                use_container_width=True, hide_index=True,
            )
            render_audit_legend()
        with a2:
            st.metric("Total token", f"{cost['total_tokens']:,}")
            st.metric("Est. biaya (USD)", f"${cost['estimated_cost_usd']:.4f}")
            st.progress(min(1.0, cost["budget_used_pct"] / 100), text=f"{cost['budget_used_pct']}% budget")
        render_tech_log(request_id)
