"""Use Case 4 (v2) — Loan Restructuring with **agents hosted in Microsoft Foundry**.

Same EVALUATOR–OPTIMIZER (reflection) loop + governance as the v1 Restructuring page;
proposer/evaluator/writer are Foundry prompt agents. v1 page is untouched.
"""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.core.models import RestructureRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import FlowState, render_restructure_html
from app.portal.portal_utils import render_audit_legend, render_gateway_toggle, render_tech_log, rupiah, run_async
from app.workflows import data_access as sor
from app.workflows.restructure_foundry_workflow import run_restructure_foundry

setup_observability()

st.title("♻️🟣 Restrukturisasi — Agen di Microsoft Foundry (v2)")
st.caption("Loop EVALUATOR–OPTIMIZER yang SAMA (propose → evaluate → revise), tetapi agen berjalan "
           "di **Foundry** · governance tetap aktif")

try:
    _registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

with st.expander("🧠 Apa bedanya dengan halaman Restrukturisasi (v1)?", expanded=False):
    st.markdown(
        "- **v1** ([Restrukturisasi](/Restructuring)): agen dibangun di kode.\n"
        "- **v2 (halaman ini)**: `restructure-proposer`, `restructure-evaluator`, `restructure-writer` "
        "**dipanggil dari Foundry**. Skema & keterjangkauan (DBR) dihitung deterministik.\n"
        f"- Project: `{_registry.get('project_endpoint','')}` · Model: `{_registry.get('model','')}`"
    )

VIZ_H = 720

customers = sor.list_customers()
def _dpd(cid: str) -> int:
    return sor.existing_loan(cid).get("days_past_due", 0)
customers = sorted(customers, key=lambda c: _dpd(c["customer_id"]), reverse=True)
labels = {}
for c in customers:
    ln = sor.existing_loan(c["customer_id"])
    tag = f" · ⚠️ {ln.get('days_past_due')} DPD" if ln.get("days_past_due", 0) > 0 else ""
    labels[f"{c['customer_id']} — {c['full_name']}{tag}"] = c

with st.sidebar:
    st.header("📝 Permohonan Restrukturisasi")
    pick = st.selectbox("Nasabah (debitur)", list(labels.keys()))
    cust = labels[pick]
    st.caption("💡 Untuk melihat **>1 proposal** (loop refleksi), pilih debitur dengan DPD tinggi.")
    loan = sor.existing_loan(cust["customer_id"])
    if loan:
        st.caption(f"Fasilitas: **{rupiah(loan.get('outstanding_principal_idr'))}** terutang · "
                   f"angsuran **{rupiah(loan.get('monthly_installment_idr'))}/bln** · "
                   f"{loan.get('annual_rate_pct')}% p.a. · sisa {loan.get('remaining_tenor_months')} bln")
    hardship = st.text_area("Alasan kesulitan", value="Pendapatan usaha menurun drastis 6 bulan terakhir.",
                            height=80)
    relief = st.text_input("Preferensi keringanan (opsional)", value="perpanjang tenor")
    submitted = st.button("▶️ Jalankan (agen Foundry)", type="primary", use_container_width=True)

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen (di Foundry) — LIVE")
viz = dia.empty()
with viz:
    components.html(render_restructure_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Log langkah agen (propose · evaluate · revise) di Foundry akan tampil di sini…")

via_apim = render_gateway_toggle("restructure")
results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = RestructureRequest(
        customer_id=cust["customer_id"], full_name=cust["full_name"],
        hardship_reason=hardship, requested_relief=relief or None,
    )
    request_id = f"RSTF-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []
    fs = FlowState()
    itcount = {"n": 0}

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        if node == "proposer" and state == "active":
            itcount["n"] += 1
        with viz:
            components.html(render_restructure_html(fs.active, fs.done, itcount["n"]), height=VIZ_H)
        if detail:
            lines.insert(0, detail)
            with log_ph.container(height=VIZ_H):
                for ln in lines:
                    st.markdown(ln)

    try:
        result, cost = run_async(run_restructure_foundry(request, request_id, on_event=_on_event, via_apim=via_apim))
    except Exception as exc:
        st.error(f"Gagal menjalankan agen Foundry: {exc}")
        st.stop()
    with viz:
        components.html(render_restructure_html(fs.active, fs.done, result["iterations"]), height=VIZ_H)

    with results:
        st.divider()
        color = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}.get(result["decision"], "•")
        st.subheader(f"{color} Keputusan: {result['decision']} · {result['iterations']} iterasi")
        st.write(result["explanation"])
        p = result["proposal"]
        if p:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Angsuran baru", rupiah(p["new_installment_idr"]))
            m2.metric("Tenor baru", f"{p['new_tenor_months']} bln")
            m3.metric("Bunga baru", f"{p['new_rate_pct']}%")
            m4.metric("Grace period", f"{p['grace_period_months']} bln")
            delta = result["original_installment_idr"] - p["new_installment_idr"]
            st.caption(f"Keringanan angsuran ≈ **{rupiah(max(0, delta))}/bln** dibanding sebelumnya "
                       f"({rupiah(result['original_installment_idr'])}).")
        a1, a2 = st.columns([3, 1])
        with a1:
            st.markdown("**Jejak audit (perhatikan loop propose→evaluate):**")
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
