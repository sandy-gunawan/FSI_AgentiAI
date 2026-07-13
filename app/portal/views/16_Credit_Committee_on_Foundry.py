"""Use Case 6 (v2) — Credit Committee with **agents hosted in Microsoft Foundry**.

Same GROUP CHAT debate + governance as the v1 Committee page; optimist/skeptic/
compliance/chair are Foundry prompt agents. v1 page is untouched.
"""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.core.models import CommitteeRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import FlowState, render_committee_html
from app.portal.portal_utils import render_audit_legend, render_tech_log, run_async
from app.workflows import data_access as sor
from app.workflows.committee_foundry_workflow import run_committee_foundry

setup_observability()

st.title("⚖️🟣 Komite Kredit — Agen di Microsoft Foundry (v2)")
st.caption("Pola GROUP CHAT yang SAMA (Optimist ⇄ Skeptic ⇄ Compliance → Chair), tetapi agen "
           "berjalan di **Foundry** · governance tetap aktif")

try:
    _registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

with st.expander("🧠 Apa bedanya dengan halaman Komite Kredit (v1)?", expanded=False):
    st.markdown(
        "- **v1** ([Komite Kredit](/Credit_Committee)): agen dibangun di kode.\n"
        "- **v2 (halaman ini)**: `committee-risk-optimist`, `-risk-skeptic`, `-compliance`, `-chair` "
        "**dipanggil dari Foundry**. Pra-skrining OJK/BI deterministik jadi guardrail keras.\n"
        f"- Project: `{_registry.get('project_endpoint','')}` · Model: `{_registry.get('model','')}`"
    )

VIZ_H = 720

companies = sor.list_companies()
labels = {f"{c['company_id']} — {c['legal_name']} ({c['sector']})": c for c in companies}
with st.sidebar:
    st.header("📝 Kasus untuk Komite")
    pick = st.selectbox("Perusahaan", list(labels.keys()))
    co = labels[pick]
    amount = st.number_input("Fasilitas (IDR)", min_value=100_000_000, max_value=20_000_000_000,
                             value=3_000_000_000, step=100_000_000)
    tenor = st.slider("Tenor (bln)", 12, 60, 48, step=6)
    purpose = st.text_input("Tujuan fasilitas", value="ekspansi pabrik & modal kerja")
    submitted = st.button("▶️ Sidangkan (agen Foundry)", type="primary", use_container_width=True)

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen (di Foundry) — LIVE")
viz = dia.empty()
with viz:
    components.html(render_committee_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Transkrip debat komite (Foundry) akan tampil di sini…")

results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = CommitteeRequest(
        company_id=co["company_id"], legal_name=co["legal_name"],
        requested_amount_idr=int(amount), tenor_months=int(tenor), purpose=purpose,
    )
    request_id = f"CMTF-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []
    fs = FlowState()
    rnd = {"n": 0}

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        if node == "optimist" and state == "active":
            rnd["n"] += 1
        with viz:
            components.html(render_committee_html(fs.active, fs.done, rnd["n"] or None), height=VIZ_H)
        if detail:
            lines.insert(0, detail)
            with log_ph.container(height=VIZ_H):
                for ln in lines:
                    st.markdown(ln)

    try:
        result, cost = run_async(run_committee_foundry(request, request_id, on_event=_on_event))
    except Exception as exc:
        st.error(f"Gagal menjalankan agen Foundry: {exc}")
        st.stop()
    with viz:
        components.html(render_committee_html(fs.active, fs.done, rnd["n"] or None), height=VIZ_H)

    with results:
        st.divider()
        color = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}.get(result["decision"], "•")
        st.subheader(f"{color} Keputusan Komite: {result['decision']} · "
                     f"{'konsensus' if result['consensus'] else 'tanpa konsensus'} · "
                     f"{result['rounds']} ronde")
        st.write(result["summary"])
        st.markdown("**Transkrip debat:**")
        icon = {"pro": "📈", "con": "🛑", "policy": "🛡️"}
        for t in result["transcript"]:
            st.markdown(f"{icon.get(t['stance'], '•')} **{t['speaker']}** ({t['stance']}): {t['argument']}")
        a1, a2 = st.columns([3, 1])
        with a1:
            st.markdown("**Jejak audit (per giliran agen):**")
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
