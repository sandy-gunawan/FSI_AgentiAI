"""Use Case 7 (v2) — Complex Investigation (Magentic) with **agents hosted in Microsoft Foundry**.

Same MAGENTIC pattern + governance as the v1 page; manager (plan/replan/dossier) + worker
are Foundry prompt agents that call MCP+REST server-side. v1 page is untouched.
"""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.core.models import MagenticRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import FlowState, render_magentic_html
from app.portal.portal_utils import render_audit_legend, render_tech_log, run_async
from app.workflows import data_access as sor
from app.workflows.magentic_foundry_workflow import run_magentic_foundry

setup_observability()

st.title("🧠🟣 Investigasi Kompleks (Magentic) — Agen di Microsoft Foundry (v2)")
st.caption("Pola MAGENTIC yang SAMA (Manager + task ledger + worker), tetapi agen berjalan di "
           "**Foundry** · governance tetap aktif")

try:
    _registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

with st.expander("🧠 Apa bedanya dengan halaman Investigasi Kompleks (v1)?", expanded=False):
    st.markdown(
        "- **v1** ([Investigasi Kompleks](/Complex_Investigation)): agen dibangun di kode.\n"
        "- **v2 (halaman ini)**: `magentic-manager-plan/-replan/-dossier` + `magentic-worker` "
        "**dipanggil dari Foundry**. Task ledger deterministik untuk auditabilitas.\n"
        f"- Project: `{_registry.get('project_endpoint','')}` · Model: `{_registry.get('model','')}`"
    )

VIZ_H = 720

_OBJECTIVES = [
    "Nilai profil risiko menyeluruh & indikasi pencucian uang.",
    "Selidiki dugaan penyalahgunaan fasilitas & pihak terkait.",
    "Tinjau kelayakan lanjutan untuk kenaikan eksposur.",
]

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
    st.header("📝 Objektif Investigasi")
    pick = st.selectbox("Subjek (nasabah)", list(labels.keys()))
    subj = labels[pick]
    objective = st.selectbox("Objektif", _OBJECTIVES)
    objective = st.text_area("Objektif (bebas)", value=objective, height=70)
    submitted = st.button("▶️ Jalankan (agen Foundry)", type="primary", use_container_width=True)

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen (di Foundry) — LIVE")
viz = dia.empty()
with viz:
    components.html(render_magentic_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Rencana Manager & temuan worker (Foundry) akan tampil di sini…")

results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = MagenticRequest(
        subject_id=subj["customer_id"], subject_name=subj["full_name"], objective=objective,
    )
    request_id = f"MAGF-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []
    fs = FlowState()

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        with viz:
            components.html(render_magentic_html(fs.active, fs.done), height=VIZ_H)
        if detail:
            lines.insert(0, detail)
            with log_ph.container(height=VIZ_H):
                for ln in lines:
                    st.markdown(ln)

    try:
        result, cost = run_async(run_magentic_foundry(request, request_id, on_event=_on_event))
    except Exception as exc:
        st.error(f"Gagal menjalankan agen Foundry: {exc}")
        st.stop()
    with viz:
        components.html(render_magentic_html(fs.active, fs.done), height=VIZ_H)

    with results:
        st.divider()
        badge = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(result["risk_level"], "•")
        st.subheader(f"{badge} Dosir Investigasi · risiko {result['risk_level']}")
        st.write(result["dossier"])
        with st.expander("🗺️ Rencana Manager (task ledger)", expanded=False):
            st.write(result["plan"])
        st.markdown("**Task ledger (langkah & temuan — dari worker Foundry):**")
        st.dataframe(
            [{"worker": s["assigned_to"], "task": s["task"], "finding": s["finding"]}
             for s in result["steps"]],
            use_container_width=True, hide_index=True,
        )
        a1, a2 = st.columns([3, 1])
        with a1:
            st.markdown("**Jejak audit (per langkah):**")
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
