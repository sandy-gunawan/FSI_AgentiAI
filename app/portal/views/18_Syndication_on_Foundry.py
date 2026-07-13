"""Use Case 8 (v2) — Syndication / Co-Financing (A2A) with **agents hosted in Microsoft Foundry**.

Same A2A cross-organisation delegation + governance as the v1 Syndication page; the Lead
Arranger + Synthesizer are Foundry prompt agents, and the A2A call to the partner bank is
unchanged. v1 page is untouched.
"""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.core.config import get_settings
from app.core.models import SyndicationRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import FlowState, render_a2a_html
from app.portal.portal_utils import render_audit_legend, render_gateway_toggle, render_tech_log, rupiah, run_async
from app.workflows import data_access as sor
from app.workflows.syndication_foundry_workflow import run_syndication_foundry

setup_observability()
settings = get_settings()

st.title("🔗🟣 Sindikasi (A2A) — Agen di Microsoft Foundry (v2)")
st.caption("Pola A2A yang SAMA (BNS Lead Arranger ↔ agen partner lintas-organisasi), tetapi agen "
           "BNS berjalan di **Foundry** · governance tetap aktif")

try:
    _registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

with st.expander("🧠 Apa bedanya dengan halaman Sindikasi (v1)?", expanded=False):
    st.markdown(
        "- **v1** ([Sindikasi A2A](/Syndication_A2A)): agen BNS dibangun di kode.\n"
        "- **v2 (halaman ini)**: `syndication-lead-arranger` + `syndication-synthesizer` **dipanggil "
        "dari Foundry**. Panggilan **A2A** ke agen partner (Bank Mitra) tetap sama.\n"
        f"- Project: `{_registry.get('project_endpoint','')}` · Model: `{_registry.get('model','')}`"
    )

VIZ_H = 720

companies = sor.list_companies()
labels = {f"{c['company_id']} — {c['legal_name']} ({c['sector']})": c for c in companies}
with st.sidebar:
    st.header("📝 Fasilitas Sindikasi")
    pick = st.selectbox("Perusahaan", list(labels.keys()))
    co = labels[pick]
    st.caption(f"Batas single-obligor BNS: **{rupiah(settings.bns_single_obligor_cap_idr)}** · "
               f"di atas ini fasilitas disindikasikan via A2A.")
    amount = st.number_input("Total fasilitas (IDR)", min_value=1_000_000_000,
                             max_value=30_000_000_000, value=12_000_000_000, step=1_000_000_000)
    tenor = st.slider("Tenor (bln)", 12, 60, 48, step=6)
    purpose = st.text_input("Tujuan fasilitas", value="ekspansi kapasitas produksi")
    partner = settings.partner_a2a_url.replace("https://", "").replace("http://", "")
    st.caption(f"🤝 Partner A2A: `{partner}`")
    submitted = st.button("▶️ Arrange (agen Foundry)", type="primary", use_container_width=True)

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen (di Foundry) — LIVE")
viz = dia.empty()
with viz:
    components.html(render_a2a_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Log Lead Arranger (Foundry) + panggilan A2A ke partner akan tampil di sini…")

via_apim = render_gateway_toggle("syndication")
results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = SyndicationRequest(
        company_id=co["company_id"], legal_name=co["legal_name"], sector=co["sector"],
        requested_amount_idr=int(amount), tenor_months=int(tenor), purpose=purpose,
    )
    request_id = f"SYNF-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []
    fs = FlowState()

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        with viz:
            components.html(render_a2a_html(fs.active, fs.done), height=VIZ_H)
        if detail:
            lines.insert(0, detail)
            with log_ph.container(height=VIZ_H):
                for ln in lines:
                    st.markdown(ln)

    try:
        result, cost, a2a_meta = run_async(run_syndication_foundry(request, request_id, on_event=_on_event, via_apim=via_apim))
    except Exception as exc:
        st.error(f"Gagal menjalankan agen Foundry: {exc}")
        st.stop()
    with viz:
        components.html(render_a2a_html(fs.active, fs.done), height=VIZ_H)

    with results:
        st.divider()
        color = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}.get(result["decision"], "•")
        st.subheader(f"{color} Sindikasi: {result['decision']}")
        st.write(result["summary"])
        po = result["partner_offer"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total fasilitas", rupiah(result["total_amount_idr"]))
        m2.metric("Porsi BNS", rupiah(result["bns_amount_idr"]))
        m3.metric("Porsi Partner", rupiah(int(po.get("participation_amount_idr", 0)) if po else 0))
        m4.metric("Kekurangan", rupiah(result["shortfall_idr"]))
        st.caption(f"Blended rate indikatif: **{result['blended_rate_pct']}%** p.a. · "
                   f"terkumpul {rupiah(result['arranged_amount_idr'])}/{rupiah(result['total_amount_idr'])}")

        if po:
            badge = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}.get(str(po.get("decision", "")), "•")
            st.markdown(f"**🤝 Penawaran partner (via A2A):** {badge} {po.get('decision')} · "
                        f"{rupiah(int(po.get('participation_amount_idr', 0)))} @ "
                        f"{po.get('indicative_rate_pct')}% p.a.")
            if po.get("conditions"):
                st.markdown("**Syarat partner:** " + "; ".join(po.get("conditions", [])))

        if a2a_meta:
            with st.expander("🪪 Agent Card partner (hasil A2A discovery)"):
                st.json(a2a_meta.get("card", {}))
            with st.expander("📨 Envelope A2A JSON-RPC (message/send)"):
                st.markdown("**Request →**")
                st.json(a2a_meta.get("request", {}))
                st.markdown("**Response ←**")
                st.json(a2a_meta.get("response", {}))

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
        st.info("🔎 **Monitoring Foundry:** langkah agen BNS juga tercatat di **Traces/Monitor** proyek "
                "`financing` di portal Foundry.")
