"""Use Case 8 — Syndicated / Co-Financing over A2A (Agent2Agent) · live view + log."""
from __future__ import annotations

import json
import uuid

import streamlit as st
import streamlit.components.v1 as components

from app.core.config import get_settings
from app.core.models import SyndicationRequest
from app.governance.audit_log import get_audit_logger
from app.observability.otel_setup import setup_observability
from app.portal.agent_viz import A2A_DETAILS, FlowState, render_a2a_html
from app.portal.portal_utils import (
    render_audit_legend,
    render_pattern_explainer,
    render_tech_log,
    rupiah,
    run_async,
)
from app.workflows import data_access as sor
from app.workflows.a2a_workflow import run_syndication

setup_observability()

settings = get_settings()

st.title("🔗 Sindikasi / Co-Financing — A2A (Agent2Agent)")
st.caption("BNS Lead Arranger mendelegasikan co-underwriting ke agen bank lain via protokol A2A")

render_pattern_explainer(
    pattern="A2A — Agent2Agent Protocol (interoperabilitas antar-agen)",
    what=("**A2A** adalah protokol terbuka (kini di bawah **Linux Foundation**; didukung Microsoft "
          "Agent Framework, Foundry, Copilot Studio) agar **agen berbicara ke agen lain** yang "
          "**dimiliki/di-deploy pihak berbeda**. Setiap agen menerbitkan **Agent Card** (kartu "
          "identitas + skill) dan menerima tugas via **JSON-RPC `message/send`**. Ini **melengkapi "
          "MCP**: MCP = agen→tool/data; A2A = agen→agen."),
    flow=("BNS Lead Arranger ─► A2A: discover Agent Card ─► Partner Bank Agent (organisasi lain)\n"
          "                    A2A: message/send task  ◄─  ParticipationOffer\n"
          "                 ─► Sindikasi Final (porsi BNS + porsi partner, blended pricing)"),
    how=("Saat fasilitas melebihi **batas single-obligor** BNS, Lead Arranger memutuskan porsi yang "
         "ditahan vs disindikasikan, lalu **menemukan Agent Card** partner dan mengirim tugas "
         "co-underwriting **lintas-organisasi via HTTPS**. Agen partner (Bank Mitra Sejahtera) — "
         "**di-deploy terpisah, opaque** — menilai dengan selera risikonya sendiri dan mengembalikan "
         "penawaran partisipasi. BNS menggabungkan hasilnya."),
    why=("Sindikasi melibatkan **institusi berbeda** dengan sistem & model berbeda. Point-to-point "
         "integrasi rapuh; **A2A menstandardkan penemuan + delegasi** antar agen otonom, tanpa "
         "berbagi kode/data/model. Inilah kasus di mana multi-agen **butuh** A2A (bukan sekadar "
         "orkestrasi intra-aplikasi)."),
    ms_term="**A2A (Agent2Agent)** — protokol **interop antar-agen** (Linux Foundation; didukung "
            "Microsoft). Pelengkap MCP; **bukan** salah satu dari 5 orkestrasi (yang bersifat "
            "koordinasi intra-aplikasi).",
)

with st.expander("📚 A2A untuk FSI — apa, kapan dipakai, dan contoh use case", expanded=False):
    st.markdown(
        """
**Apa itu A2A (ringkas).** Protokol standar agar agen dari sistem/vendor/organisasi berbeda dapat
saling **menemukan** (Agent Card), **mendelegasikan tugas** (JSON-RPC `message/send`, task lifecycle,
streaming, push), dan bekerja **opaque** (tak berbagi internal).

**MCP vs A2A (jangan tertukar):**
| | MCP | A2A |
|---|---|---|
| Menghubungkan | agen → **tool/data/sistem** | agen → **agen lain** |
| Sumbu | vertikal | horizontal |
| Contoh di app ini | Credit Bureau/KYC/Policy MCP | halaman ini (BNS ↔ Bank Mitra) |

**Kapan pakai A2A (bukan orkestrasi in-process):**
- Agen **di-deploy terpisah / dimiliki tim/vendor/organisasi berbeda**.
- Perlu **interop lintas-framework** (mis. mitra pakai LangGraph/CrewAI).
- **Delegasi lintas-institusi** dengan logika yang tetap **opaque**.
- Tugas **long-running / streaming / human-gated** melewati batas layanan.

**Kapan TIDAK perlu A2A:** agen satu tim, satu framework, satu proses → cukup orkestrasi in-process
(Sequential/Concurrent/Handoff/Group Chat/Magentic). Menambel A2A di situ hanya menambah latensi.

**Contoh use case A2A di FSI (Financial Services):**
- **Sindikasi / co-financing** (halaman ini): lead arranger ↔ agen bank peserta.
- **Correspondent / cross-border payment**: bank pengirim ↔ agen bank penerima (skrining sanksi/AML).
- **Trade finance (LC)**: agen bank importir ↔ agen bank eksportir.
- **Verifikasi lintas-lembaga**: agen bank ↔ agen otoritas pajak/dukcapil/biro kredit pihak-3.
- **Klaim asuransi bancassurance**: agen bank ↔ agen perusahaan asuransi.
- **Onboarding korporasi**: agen bank ↔ agen penyedia KYB/registrasi perusahaan.
"""
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
    submitted = st.button("▶️ Arrange Sindikasi (A2A)", type="primary", use_container_width=True)
    with st.expander("🧩 Agen yang terlibat & sistem yang dipanggil"):
        for title, desc in A2A_DETAILS:
            st.markdown(f"**{title}**  \n{desc}")

dia, logc = st.columns([3, 2], gap="medium")
dia.markdown("#### 🎬 Alur Agen — LIVE")
viz = dia.empty()
with viz:
    components.html(render_a2a_html(), height=VIZ_H)
logc.markdown("#### 📜 Log Agentic (real-time)")
log_ph = logc.empty()
with log_ph.container(height=VIZ_H):
    st.caption("Log Lead Arranger + panggilan A2A ke partner akan tampil di sini…")

results = st.container()

if submitted:
    components.html("<script>window.parent.scrollTo({top:0,behavior:'smooth'});</script>", height=0)
    request = SyndicationRequest(
        company_id=co["company_id"], legal_name=co["legal_name"], sector=co["sector"],
        requested_amount_idr=int(amount), tenor_months=int(tenor), purpose=purpose,
    )
    request_id = f"SYN-{uuid.uuid4().hex[:8]}"
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

    result, cost, a2a_meta = run_async(run_syndication(request, request_id, on_event=_on_event))
    with viz:
        components.html(render_a2a_html(fs.active, fs.done), height=VIZ_H)

    with results:
        st.divider()
        color = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}[result.decision.value]
        st.subheader(f"{color} Sindikasi: {result.decision.value}")
        st.write(result.summary)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total fasilitas", rupiah(result.total_amount_idr))
        m2.metric("Porsi BNS", rupiah(result.bns_amount_idr))
        m3.metric("Porsi Partner", rupiah(result.partner_offer.participation_amount_idr
                                          if result.partner_offer else 0))
        m4.metric("Kekurangan", rupiah(result.shortfall_idr))
        st.caption(f"Blended rate indikatif: **{result.blended_rate_pct}%** p.a. · "
                   f"terkumpul {rupiah(result.arranged_amount_idr)}/{rupiah(result.total_amount_idr)}")

        if result.partner_offer:
            o = result.partner_offer
            badge = {"APPROVE": "✅", "DECLINE": "⛔", "REFER": "🔎"}.get(o.decision.value, "•")
            st.markdown(f"**🤝 Penawaran partner (via A2A) — {o.partner_name}:** {badge} "
                        f"{o.decision.value} · {rupiah(o.participation_amount_idr)} @ "
                        f"{o.indicative_rate_pct}% p.a.")
            st.caption(o.rationale)
            if o.conditions:
                st.markdown("**Syarat partner:** " + "; ".join(o.conditions))

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
