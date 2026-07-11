"""Use Case 3 — Smart Customer Servicing (ROUTING) · single-window live view + log."""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.models import ServiceRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import SERVICING_DETAILS, FlowState, render_servicing_html
from app.portal.portal_utils import render_audit_legend, render_pattern_explainer, render_tech_log, run_async
from app.workflows import data_access as sor
from app.workflows.servicing_workflow import run_servicing

setup_observability()

st.title("🎧 Layanan Nasabah Cerdas — Routing")
st.caption("Router mengklasifikasikan pesan → satu handler spesialis menyelesaikannya")

render_pattern_explainer(
    pattern="Routing",
    what=("Satu **agen router** mengklasifikasikan permintaan yang masuk, lalu mengarahkannya ke "
          "**handler khusus**. Hanya **satu** handler yang dieksekusi per permintaan."),
    flow=("Pesan nasabah ─► Router (klasifikasi intent) ─┬─► Handler Sengketa\n"
          "                                              ├─► Handler Naik Limit\n"
          "                                              ├─► Handler Kesulitan Bayar\n"
          "                                              ├─► Handler Info Saldo\n"
          "                                              └─► Handler Umum"),
    how=("Agen **Router** membaca pesan bebas nasabah dan memilih 1 dari 5 intent. Berdasarkan "
         "intent, hanya handler yang relevan dijalankan dengan tool yang sesuai (mis. sengketa → "
         "`get_transactions`, naik limit → cashflow + SLIK). Handler lain tidak pernah jalan."),
    why=("Permintaan nasabah **sangat beragam** dan tiap jenis butuh penanganan + tool berbeda. "
         "Routing **memisahkan klasifikasi dari penyelesaian** sehingga tiap handler tetap "
         "sederhana & fokus, dan **hemat token/biaya** karena tidak semua agen dijalankan — hanya "
         "yang dibutuhkan."),
    ms_term="**Routing** — versi sederhana (satu lompatan) dari orkestrasi **Handoff** MS "
            "(Handoff penuh: delegasi dinamis multi-lompatan antar-agen).",
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
    submitted = st.button("▶️ Kirim ke Agentic Servicing", type="primary", use_container_width=True)
    with st.expander("🧩 Agen yang terlibat & sistem yang dipanggil"):
        for title, desc in SERVICING_DETAILS:
            st.markdown(f"**{title}**  \n{desc}")

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen — LIVE")
viz = dia.empty()
with viz:
    components.html(render_servicing_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Log langkah agen (input · tool · output) akan tampil di sini saat dijalankan…")

results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = ServiceRequest(
        customer_id=cust["customer_id"], full_name=cust["full_name"],
        channel=channel, message=message,
    )
    request_id = f"SVC-{uuid.uuid4().hex[:8]}"
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

    resolution, routing, cost = run_async(run_servicing(request, request_id, on_event=_on_event))
    with viz:
        components.html(render_servicing_html(fs.active, fs.done), height=VIZ_H)

    with results:
        st.divider()
        st.markdown(f"**🧭 Router →** intent `{routing.intent}` "
                    f"(keyakinan {routing.confidence:.0%}) · {routing.rationale}")
        badge = {"resolved": "✅", "escalated": "🔎", "info_provided": "ℹ️"}.get(resolution.status, "•")
        st.subheader(f"{badge} Status: {resolution.status}")
        st.write(resolution.explanation)
        if resolution.actions_taken:
            st.markdown("**Tindakan:** " + "; ".join(resolution.actions_taken))
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
