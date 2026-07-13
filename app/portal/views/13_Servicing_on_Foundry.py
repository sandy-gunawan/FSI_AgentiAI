"""Use Case 3 (v2) — Smart Customer Servicing with **agents hosted in Microsoft Foundry**.

Same ROUTING pattern + governance as the v1 Servicing page; the router + chosen handler
are Foundry prompt agents. v1 page is untouched.
"""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.core.models import ServiceRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import FlowState, render_servicing_html
from app.portal.portal_utils import render_audit_legend, render_gateway_toggle, render_tech_log, run_async
from app.workflows import data_access as sor
from app.workflows.servicing_foundry_workflow import run_servicing_foundry

setup_observability()

st.title("🎧🟣 Layanan Nasabah — Agen di Microsoft Foundry (v2)")
st.caption("Pola ROUTING yang SAMA (Router → satu handler), tetapi agen berjalan di **Foundry** · "
           "governance tetap aktif")

try:
    _registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

with st.expander("🧠 Apa bedanya dengan halaman Layanan Nasabah (v1)?", expanded=False):
    st.markdown(
        "- **v1** ([Layanan Nasabah](/Customer_Servicing)): agen dibangun di kode.\n"
        "- **v2 (halaman ini)**: `servicing-router` + handler (`servicing-dispute`, `-limit-increase`, "
        "`-hardship`, `-balance`, `-general`) **dipanggil dari Foundry**. Intent diklasifikasi "
        "deterministik untuk auditabilitas.\n"
        f"- Project: `{_registry.get('project_endpoint','')}` · Model: `{_registry.get('model','')}`"
    )

VIZ_H = 720

_SAMPLES = {
    "Sengketa transaksi": "Saya melihat tagihan Rp 2.500.000 yang tidak saya kenali, tolong dicek.",
    "Naik limit": "Saya ingin mengajukan kenaikan limit kartu kredit saya.",
    "Kesulitan bayar": "Usaha saya sedang lesu, saya kesulitan membayar cicilan bulan ini.",
    "Info saldo": "Berapa saldo rekening tabungan saya sekarang?",
    "Umum": "Apa saja syarat membuka deposito di bank ini?",
}

customers = sor.list_customers()
labels = {f"{c['customer_id']} — {c['full_name']}": c for c in customers}
with st.sidebar:
    st.header("📝 Pesan Nasabah")
    pick = st.selectbox("Nasabah", list(labels.keys()))
    cust = labels[pick]
    channel = st.selectbox("Kanal", ["chat", "email", "call_center", "mobile_app"])
    sample = st.selectbox("Contoh pesan", ["(tulis sendiri)"] + list(_SAMPLES.keys()))
    default_msg = _SAMPLES.get(sample, "")
    message = st.text_area("Pesan", value=default_msg or "Saya ingin menaikkan limit kartu kredit.",
                           height=90)
    submitted = st.button("▶️ Kirim (agen Foundry)", type="primary", use_container_width=True)

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen (di Foundry) — LIVE")
viz = dia.empty()
with viz:
    components.html(render_servicing_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Log langkah agen (Foundry) akan tampil di sini…")

via_apim = render_gateway_toggle("servicing")
results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = ServiceRequest(
        customer_id=cust["customer_id"], full_name=cust["full_name"],
        channel=channel, message=message,
    )
    request_id = f"SVCF-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []
    fs = FlowState()

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        with viz:
            components.html(render_servicing_html(fs.active, fs.done), height=VIZ_H)
        if detail:
            lines.insert(0, detail)
            with log_ph.container(height=VIZ_H):
                for ln in lines:
                    st.markdown(ln)

    try:
        result, cost = run_async(run_servicing_foundry(request, request_id, on_event=_on_event, via_apim=via_apim))
    except Exception as exc:
        st.error(f"Gagal menjalankan agen Foundry: {exc}")
        st.stop()
    with viz:
        components.html(render_servicing_html(fs.active, fs.done), height=VIZ_H)

    with results:
        st.divider()
        st.markdown(f"**🧭 Router →** intent `{result['intent']}` "
                    f"(keyakinan {result['confidence']:.0%}) · {result['rationale']}")
        badge = {"resolved": "✅", "escalated": "🔎", "info_provided": "ℹ️"}.get(result["status"], "•")
        st.subheader(f"{badge} Status: {result['status']}")
        st.write(result["summary"])
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
