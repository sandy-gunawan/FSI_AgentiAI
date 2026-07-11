"""Use Case 6 — Credit Committee (GROUP CHAT) · live view + log."""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.models import CommitteeRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import COMMITTEE_DETAILS, FlowState, render_committee_html
from app.portal.portal_utils import (
    render_audit_legend,
    render_pattern_explainer,
    render_tech_log,
    rupiah,
    run_async,
)
from app.workflows import data_access as sor
from app.workflows.committee_workflow import run_committee

setup_observability()

st.title("⚖️ Komite Kredit — Group Chat")
st.caption("Optimist ⇄ Skeptic ⇄ Compliance berdebat dalam satu percakapan → Chair memutuskan")

render_pattern_explainer(
    pattern="Group Chat",
    what=("Beberapa agen berdebat dalam **satu percakapan bersama** (transkrip yang sama terlihat "
          "semua peserta). Seorang **Chair/Manager** mengatur giliran bicara dan menutup dengan "
          "keputusan."),
    flow=("Ringkasan kasus ─► [ Risk Optimist ⇄ Risk Skeptic ⇄ Compliance ] × N ronde\n"
          "                                (transkrip dibagikan)\n"
          "                 ─► Chair menyimpulkan ─► Keputusan Komite"),
    how=("Chair membuka dengan ringkasan kasus (dari SoR + metrik). Tiga agen berdebat bergiliran "
         "selama 2 ronde — tiap agen **melihat transkrip** dan menanggapi argumen sebelumnya. Chair "
         "lalu memutuskan APPROVE/DECLINE/REFER, dengan gerbang deterministik OJK/BI sebagai batas "
         "(tak boleh approve bila ada pelanggaran keras)."),
    why=("Kasus **borderline** (REFER) menuntut penimbangan sudut pandang yang **berlawanan** "
         "(pertumbuhan vs risiko vs kepatuhan). Group chat meniru **komite kredit** nyata: dialog "
         "dan sanggahan menghasilkan keputusan yang lebih matang daripada satu agen tunggal."),
    ms_term="**Group Chat** — salah satu dari 5 orkestrasi resmi Microsoft Agent Framework.",
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
    submitted = st.button("▶️ Sidangkan ke Komite", type="primary", use_container_width=True)
    with st.expander("🧩 Agen yang terlibat & sistem yang dipanggil"):
        for title, desc in COMMITTEE_DETAILS:
            st.markdown(f"**{title}**  \n{desc}")

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen — LIVE")
viz = dia.empty()
with viz:
    components.html(render_committee_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Transkrip debat komite akan tampil di sini saat dijalankan…")

results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = CommitteeRequest(
        company_id=co["company_id"], legal_name=co["legal_name"],
        requested_amount_idr=int(amount), tenor_months=int(tenor), purpose=purpose,
    )
    request_id = f"CMT-{uuid.uuid4().hex[:8]}"
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

    decision, cost = run_async(run_committee(request, request_id, on_event=_on_event))
    with viz:
        components.html(render_committee_html(fs.active, fs.done, rnd["n"] or None), height=VIZ_H)

    with results:
        st.divider()
        color = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}[decision.decision.value]
        st.subheader(f"{color} Keputusan Komite: {decision.decision.value} · "
                     f"{'konsensus' if decision.consensus else 'tanpa konsensus'} · {decision.rounds} ronde")
        st.write(decision.summary)
        st.markdown("**Transkrip debat:**")
        icon = {"approve": "📈", "reject": "🛑", "neutral": "⚖️"}
        for t in decision.transcript:
            st.markdown(f"{icon.get(t.stance, '•')} **{t.speaker}** ({t.stance}): {t.argument}")
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
