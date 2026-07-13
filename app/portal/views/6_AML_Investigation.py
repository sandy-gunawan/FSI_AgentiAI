"""Use Case 5 — AML / Fraud Investigation (ReAct + human SAR gate) · live view + log."""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.models import AmlInvestigationRequest, SARDecision, SARRecommendation
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import AML_DETAILS, FlowState, render_aml_html
from app.portal.portal_utils import render_audit_legend, render_gateway_toggle, render_pattern_explainer, render_tech_log, run_async
from app.workflows import data_access as sor
from app.workflows.aml_workflow import resume_aml_with_decision, run_aml_investigation
from app.workflows.case_store import get_case_store

setup_observability()

st.title("🕵️ Investigasi AML / Fraud — ReAct + Human SAR Gate")
st.caption("Investigator otonom memilih tool secara dinamis → analis AML mengonfirmasi pelaporan SAR")

render_pattern_explainer(
    pattern="ReAct (Reason + Act) + Human-in-the-Loop",
    what=("Satu agen **otonom** yang bergantian **menalar** dan **memakai tool** dalam satu loop "
          "(*reason → act → observe*). Agen memutuskan **sendiri** tool mana yang dipanggil "
          "berikutnya berdasarkan apa yang ditemukannya. Diakhiri **gerbang keputusan manusia**."),
    flow=("Investigator ─(reason → act → observe, pilih tool dinamis)─► Rekomendasi SAR\n"
          "                                                                   │\n"
          "                              🧑‍⚖️ Analis AML memutuskan (file / dismiss / escalate)\n"
          "                                                                   ▼\n"
          "                                                          Pelaporan SAR / LTKM"),
    how=("**Investigator** diberi alert pemicu, lalu memilih tool secara dinamis: `screen_individual` "
         "(KYC/DTTOT), `get_monitoring_alerts`, `get_transactions`, `get_credit_report` — urutannya "
         "tidak ditentukan di awal, tergantung temuan. Setelah cukup bukti, ia menyusun rekomendasi "
         "SAR; **analis AML** menentukan apakah benar-benar dilaporkan ke PPATK."),
    why=("Investigasi bersifat **eksploratif** — langkahnya tidak bisa ditentukan di muka karena "
         "bergantung pada temuan tiap tahap. **ReAct** memberi fleksibilitas untuk 'mengikuti jejak' "
         "seperti penyelidik sungguhan. Karena pelaporan SAR berdampak hukum, keputusan akhir tetap "
         "di tangan **manusia**."),
    ms_term="**ReAct** — pola *single-agent* (bukan salah satu dari 5 orkestrasi multi-agen MS); "
            "sepupu multi-agennya adalah **Magentic**.",
)

VIZ_H = 640


def _log_render(placeholder, lines: list[str]) -> None:
    with placeholder.container(height=VIZ_H):
        if not lines:
            st.caption("Log langkah agen (reason · act · observe) akan tampil di sini…")
        for ln in lines:
            st.markdown(ln)


def _render_recommendation(rec: SARRecommendation, cost: dict | None = None) -> None:
    badge = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(rec.risk_level, "•")
    st.subheader(f"{badge} Rekomendasi: {'FILE SAR' if rec.file_sar else 'TIDAK file SAR'} "
                 f"· risiko {rec.risk_level}")
    st.write(rec.narrative)
    if rec.typologies:
        st.markdown("**Tipologi terdeteksi:** " + ", ".join(rec.typologies))
    if rec.evidence:
        st.markdown("**Bukti:**")
        for e in rec.evidence:
            st.markdown(f"- {e}")
    st.info(f"**Rekomendasi tindakan:** {rec.recommended_action}")
    if cost:
        st.caption(f"Token: {cost['total_tokens']:,} · est. ${cost['estimated_cost_usd']:.4f} "
                   f"· {cost['budget_used_pct']}% budget")


with st.sidebar:
    with st.expander("🧩 Agen yang terlibat & sistem yang dipanggil", expanded=True):
        for title, desc in AML_DETAILS:
            st.markdown(f"**{title}**  \n{desc}")

tab_new, tab_review = st.tabs(["➕ Investigasi Baru", "🧑‍⚖️ Antrian Analis AML"])

# --------------------------------------------------------------------------- #
# Phase A — new investigation (autonomous ReAct)
# --------------------------------------------------------------------------- #
with tab_new:
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

    pick = st.selectbox("Subjek (nasabah dalam pemantauan)", list(labels.keys()))
    subj = labels[pick]
    mon = sor.monitoring_alerts(subj["customer_id"])
    alerts = mon.get("alerts", [])
    if alerts:
        st.markdown("**Alert pemantauan transaksi:**")
        st.dataframe(alerts, use_container_width=True, hide_index=True)
        default_type = alerts[0]["typology"]
        default_detail = alerts[0]["detail"]
    else:
        st.caption("Tidak ada alert otomatis — investigasi manual.")
        default_type = "manual_review"
        default_detail = "Peninjauan manual atas profil nasabah."
    alert_type = st.text_input("Tipe alert", value=default_type)
    alert_detail = st.text_area("Detail alert", value=default_detail, height=70)
    submitted = st.button("▶️ Jalankan Investigasi ReAct", type="primary")

    dia, logc = st.columns([3, 2], gap="medium")
    dia.markdown("#### 🎬 Alur Agen — LIVE")
    viz_a = dia.empty()
    with viz_a:
        components.html(render_aml_html(), height=VIZ_H)
    logc.markdown("#### 📜 Log Agentic (real-time)")
    log_a = logc.empty()
    _log_render(log_a, [])
    via_apim = render_gateway_toggle("aml")
    out_a = st.container()

    if submitted:
        components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
        req = AmlInvestigationRequest(
            subject_id=subj["customer_id"], subject_name=subj["full_name"],
            alert_type=alert_type, alert_detail=alert_detail,
        )
        request_id = f"AML-{uuid.uuid4().hex[:8]}"
        lines: list[str] = []
        fs = FlowState()

        def _on_event(node: str, state: str, detail: str = "") -> None:
            fs.apply(node, state)
            with viz_a:
                components.html(render_aml_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
            if detail:
                lines.insert(0, detail)
                _log_render(log_a, lines)

        rec, cost = run_async(run_aml_investigation(req, request_id, on_event=_on_event, via_apim=via_apim))
        with viz_a:
            components.html(render_aml_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
        with out_a:
            st.success(f"Investigasi selesai. Case **{request_id}** menunggu keputusan analis (tab sebelah).")
            _render_recommendation(rec, cost)
            render_tech_log(request_id)

# --------------------------------------------------------------------------- #
# Phase B — human AML analyst review queue
# --------------------------------------------------------------------------- #
with tab_review:
    store = get_case_store()
    pending = store.list_aml_pending()
    if not pending:
        st.info("Tidak ada case menunggu review. Jalankan investigasi di tab sebelah dahulu.")
    else:
        options = {f"{p['request_id']} — {p['subject_id']} ({p['created_ts'][:19]})": p for p in pending}
        sel = st.selectbox("Case menunggu keputusan", list(options.keys()))
        case = store.get_aml(options[sel]["request_id"])
        rec = SARRecommendation(**case["recommendation_json"])
        done0 = {"investigator"}

        dia, logc = st.columns([3, 2], gap="medium")
        dia.markdown("#### 🎬 Alur Agen — LIVE")
        viz_b = dia.empty()
        with viz_b:
            components.html(render_aml_html(active=set(), waiting="human", done=done0), height=VIZ_H)
        logc.markdown("#### 📜 Log Agentic (real-time)")
        log_b = logc.empty()
        _log_render(log_b, ["🧑‍⚖️ Menunggu keputusan **Analis AML** (human-in-the-loop)."])

        with st.form("aml_human"):
            hc1, hc2 = st.columns(2)
            analyst = hc1.text_input("Nama analis", value="Rina Kartika")
            action = hc2.radio("Keputusan", ["file", "dismiss", "escalate"])
            notes = st.text_input("Catatan", value="")
            decide = st.form_submit_button("Simpan Keputusan", type="primary")

        out_b = st.container()
        with out_b:
            _render_recommendation(rec)

        if decide:
            human = SARDecision(action=action, analyst_name=analyst, notes=notes)
            lines = ["🧑‍⚖️ Menunggu keputusan **Analis AML**."]
            fs = FlowState()
            fs.done |= done0

            def _on_event2(node: str, state: str, detail: str = "") -> None:
                fs.apply(node, state)
                with viz_b:
                    components.html(render_aml_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
                if detail:
                    lines.insert(0, detail)
                    _log_render(log_b, lines)

            filing, _ = run_async(
                resume_aml_with_decision(options[sel]["request_id"], human, on_event=_on_event2)
            )
            with viz_b:
                components.html(render_aml_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
            with out_b:
                if filing is None:
                    st.warning("Case dieskalasi ke review senior (tetap di antrian).")
                else:
                    badge = "📄" if filing.filed else "🗂️"
                    st.subheader(f"{badge} {'SAR/LTKM Diterbitkan' if filing.filed else 'Kasus Ditutup'}")
                    st.write(filing.narrative)
                    st.caption(f"Diputuskan oleh: {filing.filed_by} · keputusan {filing.decision.value}")
                render_tech_log(options[sel]["request_id"])
