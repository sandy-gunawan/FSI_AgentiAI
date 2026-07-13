"""Use Case 2 (v2) — SME underwriting with **agents hosted in Microsoft Foundry**.

Same orchestration + governance as the v1 SME page, but each reasoning step calls a
persistent Foundry prompt agent (provisioned by scripts/provision_foundry_agents.py)
instead of an agent built in code. The surrounding systems (REST + MCP) are still
called by the agents server-side. v1 pages are untouched.
"""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.models import SMEFinancingRequest
from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import FlowState, render_sme_html
from app.portal.portal_utils import render_audit_legend, render_tech_log, rupiah, run_async
from app.workflows import data_access as sor
from app.workflows.sme_foundry_workflow import run_sme_foundry

setup_observability()

st.title("🏢🟣 Pembiayaan UKM — Agen di Microsoft Foundry (v2)")
st.caption("Orkestrasi Python yang SAMA, tetapi 4 agen spesialis + orchestrator berjalan sebagai "
           "**prompt agent di Foundry** · governance (token/biaya/audit) tetap aktif")

# ---- Registry / prerequisite check ---------------------------------------- #
try:
    _registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

with st.expander("🧠 Apa bedanya dengan halaman UKM (v1)?", expanded=False):
    st.markdown(
        "- **v1** ([2_SME_Underwriting](/SME_Underwriting)): agen dibangun **di kode** (instruksi inline) "
        "lalu dijalankan Agent Framework. Foundry hanya jadi backend model.\n"
        "- **v2 (halaman ini)**: agen **sudah ada di Foundry** (prompt agent) — kode hanya **memanggilnya**. "
        "Orkestrasi (paralel 4 spesialis → agregasi) tetap di Python, governance tetap sama.\n"
        f"- Project: `{_registry.get('project_endpoint','')}` · Model: `{_registry.get('model','')}`\n"
        f"- Agen dipakai: `sme-financial-analyst`, `sme-collateral-agent`, `sme-aml-fraud-agent`, "
        f"`sme-market-risk-agent`, `sme-underwriting-orchestrator`."
    )

VIZ_H = 640


def _log_render(placeholder, lines: list[str]) -> None:
    with placeholder.container(height=VIZ_H):
        if not lines:
            st.caption("Log langkah agen (Foundry) akan tampil di sini…")
        for ln in lines:
            st.markdown(ln)


# ---- Form ------------------------------------------------------------------ #
companies = sor.list_companies()
labels = {f"{c['company_id']} — {c['legal_name']} ({c['sector']})": c for c in companies}
fc1, fc2, fc3, fc4 = st.columns([3, 2, 2, 2])
pick = fc1.selectbox("Perusahaan", list(labels.keys()))
co = labels[pick]
amount = fc2.number_input("Fasilitas (IDR)", min_value=100_000_000, max_value=20_000_000_000,
                          value=2_000_000_000, step=100_000_000)
tenor = fc3.slider("Tenor (bln)", 12, 60, 36, step=6)
rm = fc4.text_input("RM", value="Budi Santoso")
purpose = st.text_input("Tujuan fasilitas", value="ekspansi kapasitas produksi")
submitted = st.button("▶️ Jalankan Analisis (agen Foundry)", type="primary")

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen (di Foundry) — LIVE")
viz = dia.empty()
with viz:
    components.html(render_sme_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
_log_render(log_ph, [])
results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    req = SMEFinancingRequest(
        company_id=co["company_id"], legal_name=co["legal_name"], npwp=co["npwp"],
        sector=co["sector"], requested_amount_idr=int(amount), tenor_months=int(tenor),
        purpose=purpose, collateral_id=co["collateral_id"], relationship_manager=rm,
    )
    request_id = f"SMEF-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []
    fs = FlowState()

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        with viz:
            components.html(render_sme_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
        if detail:
            lines.insert(0, detail)
            _log_render(log_ph, lines)

    try:
        result, cost = run_async(run_sme_foundry(req, request_id, on_event=_on_event))
    except Exception as exc:  # surface auth/registry/runtime errors cleanly
        st.error(f"Gagal menjalankan agen Foundry: {exc}")
        st.stop()

    with viz:
        components.html(render_sme_html(fs.active, fs.done, fs.waiting), height=VIZ_H)

    with results:
        st.divider()
        badge = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}.get(result["decision"], "•")
        st.subheader(f"{badge} Keputusan (OJK/BI, deterministik): {result['decision']}")
        st.caption(result["reason"])

        m = result["metrics"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("LTV", m["ltv"])
        c2.metric("DSCR", m["dscr"])
        c3.metric("DER", m["debt_to_equity"])
        c4.metric("Skor kredit", m["credit_score"])

        st.markdown("#### 🧑‍🔬 Temuan 4 agen spesialis (dari Foundry)")
        friendly = {"financial_analyst": "📊 Analis Keuangan", "collateral": "🏠 Penilai Agunan",
                    "aml_fraud": "🛡️ AML/Fraud", "market_risk": "🌐 Risiko Pasar"}
        for key, label in friendly.items():
            with st.expander(label, expanded=False):
                st.write(result["findings"].get(key, "-"))

        st.markdown("#### 🧮 Rekomendasi Underwriting (orchestrator Foundry)")
        st.write(result["recommendation"])

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

        proj = _registry.get("project_endpoint", "")
        st.info("🔎 **Monitoring bawaan Foundry:** setiap langkah juga tercatat di **Traces/Monitor** "
                "pada agen di portal Foundry (project `financing`) — selain governance lokal di atas.")
