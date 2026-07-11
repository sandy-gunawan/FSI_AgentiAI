"""Use Case 2 — SME financing (CONCURRENT star + HUMAN-IN-THE-LOOP) · live view + log."""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.models import HumanDecision, SMEFinancingRequest, UnderwritingRecommendation
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import SME_DETAILS, FlowState, render_sme_html
from app.portal.portal_utils import render_audit_legend, render_pattern_explainer, render_tech_log, rupiah, run_async
from app.workflows import data_access as sor
from app.workflows.case_store import get_case_store
from app.workflows.sme_workflow import resume_sme_with_decision, run_sme_analysis

setup_observability()

st.title("🏢 Pembiayaan UKM — Concurrent Star + Human-in-the-Loop")
st.caption("Orchestrator → 4 agen spesialis paralel → rekomendasi → keputusan petugas kredit")

render_pattern_explainer(
    pattern="Orchestrator-Workers (Concurrent Star) + Human-in-the-Loop",
    what=("Satu **orchestrator** menyebar tugas ke beberapa **agen pekerja spesialis** yang "
          "berjalan **paralel**, lalu menggabungkan (agregasi) hasilnya. Ditambah **gerbang "
          "keputusan manusia** sebelum hasil final diterbitkan."),
    flow=("               ┌─► Analis Keuangan ─┐\n"
          "Orchestrator ──┼─► Penilai Agunan   ┼─► agregasi ─► Rekomendasi\n"
          "   (hub)       ├─► AML / Fraud      ┤                   │\n"
          "               └─► Risiko Pasar ────┘                   ▼\n"
          "                                          🧑‍⚖️ Petugas Kredit → Term Sheet"),
    how=("Orchestrator memicu 4 spesialis sekaligus (`asyncio.gather`): Keuangan, Agunan, "
         "AML/Fraud, dan Risiko Pasar — masing-masing memanggil tool/MCP-nya sendiri. Hasil "
         "digabung + pra-skrining kebijakan OJK/BI, lalu **petugas kredit** menyetujui/menolak "
         "sebelum term sheet terbit. Case dijeda & disimpan hingga manusia memutuskan."),
    why=("Underwriting UKM butuh **beberapa analisis independen** yang tidak saling bergantung — "
         "menjalankannya paralel jauh **lebih cepat** daripada seri. Karena nilainya besar & "
         "berisiko, keputusan akhir memerlukan **persetujuan manusia** (kepatuhan & akuntabilitas), "
         "sehingga pola hub-and-spoke + human-in-the-loop paling tepat."),
    ms_term="**Concurrent** — salah satu dari 5 orkestrasi resmi Microsoft Agent Framework "
            "(ditambah gate Human-in-the-Loop).",
)

VIZ_H = 640


def _log_render(placeholder, lines: list[str]) -> None:
    with placeholder.container(height=VIZ_H):
        if not lines:
            st.caption("Log langkah agen (input · tool · output) akan tampil di sini…")
        for ln in lines:
            st.markdown(ln)


def _render_recommendation(rec: UnderwritingRecommendation, cost: dict | None = None) -> None:
    badge = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}.get(rec.recommended_decision.value, "•")
    st.subheader(f"{badge} Rekomendasi: {rec.recommended_decision.value} · risiko {rec.composite_risk_rating}")
    st.write(rec.summary)
    st.info("ℹ️ **Cara baca skor 0–100:** ini **keluaran (output) tiap agen AI spesialis** — makin tinggi "
            "makin baik/aman (100 = terbaik, 0 = paling berisiko). Skor digabung oleh Orchestrator, lalu "
            "dicek ulang dengan aturan OJK/BI yang deterministik untuk keputusan akhir.")
    friendly = {"financial_analyst": "📊 Analis Keuangan", "collateral": "🏠 Penilai Agunan",
                "aml_fraud": "🛡️ AML/Fraud", "market_risk": "🌐 Risiko Pasar"}
    cols = st.columns(len(rec.findings) or 1)
    for col, f in zip(cols, rec.findings):
        label = friendly.get(f.specialist, f.specialist)
        col.metric(f"{label} (skor)", f"{f.score:.0f}/100", f"risiko {f.risk_rating}",
                   help=f"Keluaran agen {label}. 0 = risiko tinggi, 100 = paling baik/aman. "
                        f"Ringkasan: {f.summary}")
        col.caption(f.summary)
    m1, m2 = st.columns(2)
    m1.metric("Rekomendasi plafon", rupiah(rec.recommended_amount_idr))
    m2.metric("Indikasi bunga", f"{rec.recommended_rate_pct}%")
    if rec.conditions:
        st.markdown("**Syarat/kovenan:** " + "; ".join(rec.conditions))
    if cost:
        st.caption(f"Token: {cost['total_tokens']:,} · est. ${cost['estimated_cost_usd']:.4f} "
                   f"· {cost['budget_used_pct']}% budget")


with st.sidebar:
    with st.expander("🧩 Agen yang terlibat & sistem yang dipanggil", expanded=True):
        for title, desc in SME_DETAILS:
            st.markdown(f"**{title}**  \n{desc}")

tab_new, tab_review = st.tabs(["➕ Pengajuan Baru (analisis)", "🧑‍⚖️ Antrian Review Petugas"])

# --------------------------------------------------------------------------- #
# Phase A — new application + concurrent specialist analysis
# --------------------------------------------------------------------------- #
with tab_new:
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
    submitted = st.button("▶️ Jalankan Analisis Paralel (4 agen)", type="primary")

    dia, logc = st.columns([3, 2], gap="medium")
    dia.markdown("#### 🎬 Alur Agen — LIVE")
    viz_a = dia.empty()
    with viz_a:
        components.html(render_sme_html(), height=VIZ_H)
    logc.markdown("#### 📜 Log Agentic (real-time)")
    log_a = logc.empty()
    _log_render(log_a, [])
    out_a = st.container()

    if submitted:
        components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
        req = SMEFinancingRequest(
            company_id=co["company_id"], legal_name=co["legal_name"], npwp=co["npwp"],
            sector=co["sector"], requested_amount_idr=int(amount), tenor_months=int(tenor),
            purpose=purpose, collateral_id=co["collateral_id"], relationship_manager=rm,
        )
        request_id = f"SME-{uuid.uuid4().hex[:8]}"
        lines: list[str] = []
        fs = FlowState()

        def _on_event(node: str, state: str, detail: str = "") -> None:
            fs.apply(node, state)
            with viz_a:
                components.html(render_sme_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
            if detail:
                lines.insert(0, detail)
                _log_render(log_a, lines)

        rec, cost = run_async(run_sme_analysis(req, request_id, on_event=_on_event))
        with viz_a:
            components.html(render_sme_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
        with out_a:
            st.success(f"Analisis selesai. Case **{request_id}** menunggu keputusan petugas (tab sebelah).")
            _render_recommendation(rec, cost)
            render_tech_log(request_id)

# --------------------------------------------------------------------------- #
# Phase B — human loan officer review queue
# --------------------------------------------------------------------------- #
with tab_review:
    store = get_case_store()
    pending = store.list_pending()
    if not pending:
        st.info("Tidak ada case menunggu review. Jalankan analisis di tab sebelah dahulu.")
    else:
        options = {f"{p['request_id']} — {p['company_id']} ({p['created_ts'][:19]})": p for p in pending}
        sel = st.selectbox("Case menunggu keputusan", list(options.keys()))
        case = store.get(options[sel]["request_id"])
        rec = UnderwritingRecommendation(**case["recommendation_json"])
        done0 = {"orchestrator", "financial", "collateral", "aml", "market", "aggregate"}

        dia, logc = st.columns([3, 2], gap="medium")
        dia.markdown("#### 🎬 Alur Agen — LIVE")
        viz_b = dia.empty()
        with viz_b:
            components.html(render_sme_html(active=set(), waiting="human", done=done0), height=VIZ_H)
        logc.markdown("#### 📜 Log Agentic (real-time)")
        log_b = logc.empty()
        _log_render(log_b, ["🧑‍⚖️ Menunggu keputusan **Petugas Kredit** (human-in-the-loop)."])

        with st.form("human"):
            hc1, hc2, hc3 = st.columns(3)
            officer = hc1.text_input("Nama petugas", value="Sri Wahyuni")
            action = hc2.radio("Keputusan", ["approve", "reject", "request_info"])
            notes = hc3.text_input("Catatan", value="")
            c1, c2 = st.columns(2)
            adj_amount = c1.number_input("Plafon disesuaikan (0=ikuti)", min_value=0, value=0, step=100_000_000)
            adj_rate = c2.number_input("Bunga disesuaikan (0=ikuti)", min_value=0.0, value=0.0, step=0.5)
            decide = st.form_submit_button("Simpan Keputusan", type="primary")

        out_b = st.container()
        with out_b:
            _render_recommendation(rec)

        if decide:
            human = HumanDecision(
                action=action, officer_name=officer, notes=notes,
                adjusted_amount_idr=int(adj_amount) or None,
                adjusted_rate_pct=float(adj_rate) or None,
            )
            lines = ["🧑‍⚖️ Menunggu keputusan **Petugas Kredit**."]
            fs = FlowState()
            fs.done |= done0

            def _on_event2(node: str, state: str, detail: str = "") -> None:
                fs.apply(node, state)
                with viz_b:
                    components.html(render_sme_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
                if detail:
                    lines.insert(0, detail)
                    _log_render(log_b, lines)

            termsheet, _ = run_async(
                resume_sme_with_decision(options[sel]["request_id"], human, on_event=_on_event2)
            )
            with viz_b:
                components.html(render_sme_html(fs.active, fs.done, fs.waiting), height=VIZ_H)
            with out_b:
                if termsheet is None:
                    st.warning("Case dikembalikan untuk informasi tambahan (tetap di antrian).")
                else:
                    badge = {"APPROVE": "✅", "DECLINE": "⛔"}.get(termsheet.decision.value, "•")
                    st.subheader(f"{badge} Term Sheet — {termsheet.decision.value}")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Plafon disetujui", rupiah(termsheet.approved_amount_idr))
                    m2.metric("Bunga p.a.", f"{termsheet.annual_rate_pct}%")
                    m3.metric("Tenor", f"{termsheet.tenor_months} bln")
                    st.caption(f"Disetujui oleh: {termsheet.approved_by} · {termsheet.facility_type}")
                render_tech_log(options[sel]["request_id"])
