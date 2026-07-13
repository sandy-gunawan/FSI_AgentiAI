"""Use Case 4 — Loan Restructuring Advisor (EVALUATOR-OPTIMIZER) · live view + log."""
from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.models import RestructureRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import RESTRUCTURE_DETAILS, FlowState, render_restructure_html
from app.portal.portal_utils import render_audit_legend, render_gateway_toggle, render_pattern_explainer, render_tech_log, rupiah, run_async
from app.workflows import data_access as sor
from app.workflows.restructure_workflow import run_restructure

setup_observability()

st.title("♻️ Restrukturisasi Kredit — Evaluator–Optimizer (Refleksi)")
st.caption("Proposer menyusun skema → Evaluator menilai → umpan balik → revisi hingga terjangkau")

render_pattern_explainer(
    pattern="Evaluator–Optimizer (Reflection Loop)",
    what=("Satu agen **Proposer** menghasilkan solusi, lalu agen **Evaluator** menilainya. Umpan "
          "balik dari evaluator dipakai untuk **memperbaiki** solusi — berulang sampai memenuhi "
          "kriteria atau mencapai batas iterasi."),
    flow=("Proposer ─► [cek keterjangkauan deterministik] ─► Evaluator ─┐\n"
          "   ▲                                                          │\n"
          "   └────────── umpan balik (revisi, ≤ 3 iterasi) ────────────┘  ─► Penjelasan"),
    how=("**Proposer** menyusun skema (perpanjang tenor, turunkan bunga, grace period). Sistem "
         "menghitung ulang angsuran & DBR secara deterministik, lalu **Evaluator** menilai lolos "
         "atau tidak dan memberi **umpan balik konkret**. Jika belum lolos, umpan balik dikirim "
         "balik ke Proposer untuk revisi — hingga terjangkau atau di-*refer* ke petugas."),
    why=("Skema restrukturisasi yang baik jarang tepat di percobaan pertama — perlu "
         "**menyeimbangkan keringanan vs kebijakan** melalui iterasi. Loop *generate → critique → "
         "revise* menghasilkan kualitas yang jauh lebih baik daripada sekali jalan, sekaligus "
         "menjaga keputusan tetap dalam batas kebijakan OJK/BI."),
    ms_term="**Evaluator–Optimizer** — pola *workflow* (Anthropic), **bukan** salah satu dari 5 "
            "orkestrasi resmi MS; diimplementasikan sebagai loop refleksi kustom.",
)

VIZ_H = 720

# Prefer distressed borrowers (arrears) at the top of the list.
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
    st.caption("💡 Untuk melihat **>1 proposal** (loop refleksi bekerja), pilih **CUST-1006** — "
               "kasus sulit: proposal konservatif ronde-1 gagal keterjangkauan, lalu direvisi.")
    loan = sor.existing_loan(cust["customer_id"])
    if loan:
        st.caption(f"Fasilitas: **{rupiah(loan.get('outstanding_principal_idr'))}** terutang · "
                   f"angsuran **{rupiah(loan.get('monthly_installment_idr'))}/bln** · "
                   f"{loan.get('annual_rate_pct')}% p.a. · sisa {loan.get('remaining_tenor_months')} bln · "
                   f"status **{loan.get('status')}** ({loan.get('days_past_due')} DPD)")
    hardship = st.text_area("Alasan kesulitan", value="Pendapatan usaha menurun drastis 6 bulan terakhir.",
                            height=80)
    relief = st.text_input("Preferensi keringanan (opsional)", value="perpanjang tenor")
    submitted = st.button("▶️ Jalankan Advisor Restrukturisasi", type="primary", use_container_width=True)
    with st.expander("🧩 Agen yang terlibat & sistem yang dipanggil"):
        for title, desc in RESTRUCTURE_DETAILS:
            st.markdown(f"**{title}**  \n{desc}")

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen — LIVE")
viz = dia.empty()
with viz:
    components.html(render_restructure_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Log langkah agen (propose · evaluate · revise) akan tampil di sini…")

via_apim = render_gateway_toggle("restructure")
results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = RestructureRequest(
        customer_id=cust["customer_id"], full_name=cust["full_name"],
        hardship_reason=hardship, requested_relief=relief or None,
    )
    request_id = f"RST-{uuid.uuid4().hex[:8]}"
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

    outcome, cost = run_async(run_restructure(request, request_id, on_event=_on_event, via_apim=via_apim))
    with viz:
        components.html(render_restructure_html(fs.active, fs.done, outcome.iterations), height=VIZ_H)

    with results:
        st.divider()
        color = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}[outcome.decision.value]
        st.subheader(f"{color} Keputusan: {outcome.decision.value} · {outcome.iterations} iterasi")
        st.write(outcome.explanation)
        if outcome.final_proposal:
            p = outcome.final_proposal
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Angsuran baru", rupiah(p.new_installment_idr))
            m2.metric("Tenor baru", f"{p.new_tenor_months} bln")
            m3.metric("Bunga baru", f"{p.new_rate_pct}%")
            m4.metric("Grace period", f"{p.grace_period_months} bln")
            if loan:
                delta = loan.get("monthly_installment_idr", 0) - p.new_installment_idr
                st.caption(f"Keringanan angsuran ≈ **{rupiah(max(0, delta))}/bln** "
                           f"dibanding sebelumnya ({rupiah(loan.get('monthly_installment_idr'))}).")
        a1, a2 = st.columns([3, 1])
        with a1:
            st.markdown("**Jejak audit (per langkah agen — perhatikan loop propose→evaluate):**")
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
