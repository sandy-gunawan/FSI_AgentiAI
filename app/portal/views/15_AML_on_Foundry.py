"""Use Case 5 (v2) — AML / Fraud Investigation with **agents hosted in Microsoft Foundry**.

Same ReAct-style investigation + SAR gate as the v1 AML page; the investigator + SAR
writer are Foundry prompt agents. For a self-contained demo the human gate is
auto-confirmed inline (v1's full case-store HITL queue stays on the v1 page). v1 untouched.
"""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.core.models import AmlInvestigationRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import FlowState, render_aml_html
from app.portal.portal_utils import render_audit_legend, render_gateway_toggle, render_tech_log, run_async
from app.workflows import data_access as sor
from app.workflows.aml_foundry_workflow import run_aml_foundry

setup_observability()

st.title("🕵️🟣 Investigasi AML — Agen di Microsoft Foundry (v2)")
st.caption("Pola ReAct + human SAR gate yang SAMA, tetapi Investigator & SAR writer berjalan di "
           "**Foundry** · governance tetap aktif · gate manusia otomatis untuk demo")

try:
    _registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

with st.expander("🧠 Apa bedanya dengan halaman AML (v1)?", expanded=False):
    st.markdown(
        "- **v1** ([Investigasi AML](/AML_Investigation)): agen dibangun di kode + antrian analis "
        "(human-in-the-loop) via case store.\n"
        "- **v2 (halaman ini)**: `aml-investigator` + `aml-sar-writer` **dipanggil dari Foundry**. "
        "Eskalasi deterministik (sanksi DTTOT ⇒ wajib lapor). Gate analis **otomatis** untuk demo.\n"
        f"- Project: `{_registry.get('project_endpoint','')}` · Model: `{_registry.get('model','')}`"
    )

VIZ_H = 640


def _log_render(placeholder, lines: list[str]) -> None:
    with placeholder.container(height=VIZ_H):
        if not lines:
            st.caption("Log langkah agen (reason · act · observe) di Foundry akan tampil di sini…")
        for ln in lines:
            st.markdown(ln)


customers = sor.list_customers()

def _risk(cid: str) -> str:
    return sor.monitoring_alerts(cid).get("monitoring_risk_rating", "low")

order = {"high": 0, "medium": 1, "low": 2}
customers = sorted(customers, key=lambda c: order.get(_risk(c["customer_id"]), 3))
labels = {}
for c in customers:
    r = _risk(c["customer_id"])
    tag = {"high": " · 🔴 high", "medium": " · 🟠 medium"}.get(r, "")
    labels[f"{c['customer_id']} — {c['full_name']}{tag}"] = c

with st.sidebar:
    st.header("📝 Subjek Investigasi")
    pick = st.selectbox("Subjek (nasabah dalam pemantauan)", list(labels.keys()))
    subj = labels[pick]
    mon = sor.monitoring_alerts(subj["customer_id"])
    alerts = mon.get("alerts", [])
    if alerts:
        default_type = alerts[0]["typology"]
        default_detail = alerts[0]["detail"]
    else:
        default_type = "manual_review"
        default_detail = "Peninjauan manual atas profil nasabah."
    alert_type = st.text_input("Tipe alert", value=default_type)
    alert_detail = st.text_area("Detail alert", value=default_detail, height=70)
    submitted = st.button("▶️ Jalankan (agen Foundry)", type="primary", use_container_width=True)

if alerts:
    st.markdown("**Alert pemantauan transaksi:**")
    st.dataframe(alerts, use_container_width=True, hide_index=True)

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen (di Foundry) — LIVE")
viz = dia.empty()
with viz:
    components.html(render_aml_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
_log_render(log_ph, [])

via_apim = render_gateway_toggle("aml")
results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    req = AmlInvestigationRequest(
        subject_id=subj["customer_id"], subject_name=subj["full_name"],
        alert_type=alert_type, alert_detail=alert_detail,
    )
    request_id = f"AMLF-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []
    fs = FlowState()

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        with viz:
            components.html(render_aml_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
        if detail:
            lines.insert(0, detail)
            _log_render(log_ph, lines)

    try:
        result, cost = run_async(run_aml_foundry(req, request_id, on_event=_on_event, via_apim=via_apim))
    except Exception as exc:
        st.error(f"Gagal menjalankan agen Foundry: {exc}")
        st.stop()
    with viz:
        components.html(render_aml_html(fs.active, fs.done, fs.waiting), height=VIZ_H)

    with results:
        st.divider()
        badge = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(result["risk_level"], "•")
        st.subheader(f"{badge} {'SAR/LTKM Diterbitkan' if result['file_sar'] else 'Tidak file SAR'} "
                     f"· risiko {result['risk_level']}")
        st.markdown("**🕵️ Temuan investigasi (agen Foundry):**")
        st.write(result["investigation"])
        if result["typologies"]:
            st.markdown("**Tipologi terdeteksi:** " + ", ".join(result["typologies"]))
        if result["evidence"]:
            st.markdown("**Bukti:**")
            for e in result["evidence"]:
                st.markdown(f"- {e}")
        if result["sar_narrative"]:
            st.markdown("**📄 Narasi SAR / penutupan (agen Foundry):**")
            st.write(result["sar_narrative"])
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
