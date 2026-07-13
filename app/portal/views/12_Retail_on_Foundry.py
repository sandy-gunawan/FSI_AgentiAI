"""Use Case 1 (v2) — Retail personal loan with **agents hosted in Microsoft Foundry**.

Same SEQUENTIAL pipeline + governance as the v1 Retail page, but each step calls a
persistent Foundry prompt agent. v1 page is untouched.
"""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.core.models import EmploymentType, RetailLoanApplication
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import FlowState, render_retail_html
from app.portal.portal_utils import render_audit_legend, render_gateway_toggle, render_tech_log, rupiah, run_async
from app.workflows import data_access as sor
from app.workflows.retail_foundry_workflow import run_retail_foundry

setup_observability()

st.title("👤🟣 Kredit Ritel — Agen di Microsoft Foundry (v2)")
st.caption("Pipeline SEQUENTIAL yang SAMA, tetapi Intake → Credit → Decision berjalan sebagai "
           "**prompt agent di Foundry** · governance (token/biaya/audit) tetap aktif")

try:
    _registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

with st.expander("🧠 Apa bedanya dengan halaman Ritel (v1)?", expanded=False):
    st.markdown(
        "- **v1** ([Kredit Ritel](/Retail_Loan)): agen dibangun **di kode** lalu dijalankan Agent Framework.\n"
        "- **v2 (halaman ini)**: agen **sudah ada di Foundry** — kode hanya **memanggilnya**. "
        "Orkestrasi (sequential) & governance tetap sama.\n"
        f"- Project: `{_registry.get('project_endpoint','')}` · Model: `{_registry.get('model','')}`\n"
        "- Agen: `retail-intake`, `retail-credit-risk`, `retail-decision`."
    )

VIZ_H = 720

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
    submitted = st.button("▶️ Jalankan (agen Foundry)", type="primary", use_container_width=True)

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen (di Foundry) — LIVE")
viz = dia.empty()
with viz:
    components.html(render_retail_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Log langkah agen (Foundry) akan tampil di sini…")

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
    request_id = f"RETF-{uuid.uuid4().hex[:8]}"
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

    try:
        result, cost = run_async(run_retail_foundry(application, request_id, on_event=_on_event, via_apim=via_apim))
    except Exception as exc:
        st.error(f"Gagal menjalankan agen Foundry: {exc}")
        st.stop()
    with viz:
        components.html(render_retail_html(fs.active, fs.done), height=VIZ_H)

    with results:
        st.divider()
        color = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}.get(result["decision"], "•")
        st.subheader(f"{color} Keputusan (OJK/BI, deterministik): {result['decision']}")
        st.write(result["explanation"])
        if result["offer"]:
            o = result["offer"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Plafon", rupiah(o["approved_amount_idr"]))
            m2.metric("Bunga p.a.", f"{o['annual_rate_pct']}%")
            m3.metric("Angsuran/bln", rupiah(o["monthly_installment_idr"]))
            m4.metric("Total bayar", rupiah(o["total_repayment_idr"]))
        with st.expander("🧑‍🔬 Temuan agen (dari Foundry)", expanded=False):
            st.markdown("**🧾 Intake & Verifikasi**")
            st.write(result["intake"])
            st.markdown("**📊 Credit Risk**")
            st.write(result["credit_text"])
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
        st.info("🔎 **Monitoring Foundry:** langkah agen juga tercatat di **Traces/Monitor** proyek "
                "`financing` di portal Foundry.")
