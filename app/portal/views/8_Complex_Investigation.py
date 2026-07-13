"""Use Case 7 — Complex Investigation (MAGENTIC) · live view + log."""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.models import MagenticRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import MAGENTIC_DETAILS, FlowState, render_magentic_html
from app.portal.portal_utils import (
    render_audit_legend,
    render_gateway_toggle,
    render_pattern_explainer,
    render_tech_log,
    run_async,
)
from app.workflows import data_access as sor
from app.workflows.magentic_workflow import run_magentic

setup_observability()

st.title("🧠 Investigasi Kompleks — Magentic")
st.caption("Manager menyusun task ledger, menugaskan worker, meninjau progres & replan → dosir")

render_pattern_explainer(
    pattern="Magentic",
    what=("Seorang **Manager** memelihara **task ledger** (rencana), mengoordinasikan tim **worker "
          "spesialis** secara dinamis, meninjau progres, dan dapat **replan** (menambah langkah) "
          "sebelum menyusun dosir akhir."),
    flow=("Manager buat Task Ledger ─► tugaskan worker (kyc · transaksi · kredit · finansial)\n"
          "   ▲                                   │\n"
          "   └──── tinjau progres + REPLAN ◄──────┘   ─► Manager tulis dosir"),
    how=("Manager membuat rencana 3-5 langkah, tiap langkah ditugaskan ke worker dengan tool yang "
         "tepat. Setelah worker selesai, Manager meninjau temuan dan dapat **menambah langkah** bila "
         "ada celah material, lalu menulis **dosir** (tingkat risiko, temuan, rekomendasi)."),
    why=("Investigasi kompleks bersifat **terbuka (open-ended)** — rencana lengkap tak diketahui di "
         "awal. Pola Magentic (**manajer + tim + ledger + replanning**) menangani tugas sulit yang "
         "butuh koordinasi banyak spesialis, melampaui satu agen ReAct tunggal."),
    ms_term="**Magentic** — salah satu dari 5 orkestrasi resmi Microsoft Agent Framework "
            "(berbasis Magentic-One).",
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
    submitted = st.button("▶️ Jalankan Investigasi Magentic", type="primary", use_container_width=True)
    with st.expander("🧩 Agen yang terlibat & sistem yang dipanggil"):
        for title, desc in MAGENTIC_DETAILS:
            st.markdown(f"**{title}**  \n{desc}")

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen — LIVE")
viz = dia.empty()
with viz:
    components.html(render_magentic_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Rencana Manager & temuan worker akan tampil di sini…")

via_apim = render_gateway_toggle("magentic")
results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = MagenticRequest(
        subject_id=subj["customer_id"], subject_name=subj["full_name"], objective=objective,
    )
    request_id = f"MAG-{uuid.uuid4().hex[:8]}"
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

    dossier, cost = run_async(run_magentic(request, request_id, on_event=_on_event, via_apim=via_apim))
    with viz:
        components.html(render_magentic_html(fs.active, fs.done), height=VIZ_H)

    with results:
        st.divider()
        badge = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(dossier.risk_level, "•")
        st.subheader(f"{badge} Dosir Investigasi · risiko {dossier.risk_level} · {dossier.replans} replan")
        st.write(dossier.summary)
        st.info(f"**Rekomendasi:** {dossier.recommendation}")
        if dossier.findings:
            st.markdown("**Temuan utama:**")
            for f in dossier.findings:
                st.markdown(f"- {f}")
        st.markdown("**Task ledger (langkah & temuan):**")
        st.dataframe(
            [{"task": s.task, "worker": s.assigned_to, "status": s.status, "finding": s.finding}
             for s in dossier.steps],
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
