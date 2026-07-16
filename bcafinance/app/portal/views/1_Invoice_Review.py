"""Main page — upload a faktur, choose Option A/B, run the 2 Foundry agents."""
from __future__ import annotations

import json
import pathlib
import uuid

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from app.agents.shared.foundry_runner import FoundryAgentsNotProvisioned, load_agent_registry
from app.core.config import get_settings
from app.core.models import ExtractionMode
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.portal.flow_viz import FlowState, render_flow_html
from app.portal.portal_utils import rupiah, run_async
from app.portal.theme import decision_banner, hero, inject_theme, metric_tile, pills
from app.workflows.invoice_review_workflow import run_invoice_review

inject_theme()
hero("🧾 Review Pembiayaan Faktur", "Dua agen di Microsoft Foundry · keputusan deterministik "
     "berbasis kebijakan yang dapat diubah on-the-fly",
     ["Agen 1: Ekstraksi", "Agen 2: Reviewer", "Rules engine: keputusan mengikat"])

settings = get_settings()

# ---- Prerequisite: agents provisioned? ------------------------------------ #
try:
    registry = load_agent_registry()
except FoundryAgentsNotProvisioned as exc:
    st.error(str(exc))
    st.stop()

FLOW_H = 190


def _run_flow(ph, fs: FlowState, mode_label: str) -> None:
    with ph:
        components.html(render_flow_html(fs.active, fs.done, mode_label), height=FLOW_H)


# ---- Input: option, upload / sample --------------------------------------- #
left, right = st.columns([1, 1], gap="large")

with left:
    st.markdown("#### 1 · Pilih metode ekstraksi (Agen 1)")
    opt = st.radio(
        "Metode",
        ["🅰️ DI direct — Python panggil DI, agen normalisasi",
         "🅰️➕ DI agentic — agen panggil DI sendiri (tool)",
         "🅱️ Multimodal — agen baca gambar"],
        label_visibility="collapsed",
    )
    if opt.startswith("🅰️➕"):
        mode = ExtractionMode.DOC_INTELLIGENCE_AGENTIC
    elif opt.startswith("🅰️"):
        mode = ExtractionMode.DOC_INTELLIGENCE
    else:
        mode = ExtractionMode.MULTIMODAL
    mode_label = {
        ExtractionMode.DOC_INTELLIGENCE: "DI direct",
        ExtractionMode.DOC_INTELLIGENCE_AGENTIC: "DI agentic (tool)",
        ExtractionMode.MULTIMODAL: "Multimodal (Vision)",
    }[mode]
    if mode in (ExtractionMode.DOC_INTELLIGENCE, ExtractionMode.DOC_INTELLIGENCE_AGENTIC) \
            and not settings.doc_intelligence_configured:
        st.warning("⚠️ `DOC_INTELLIGENCE_ENDPOINT` belum diset — mode DI akan gagal.")
    if mode == ExtractionMode.DOC_INTELLIGENCE_AGENTIC and not settings.tools_service_configured:
        st.warning("⚠️ `TOOLS_SERVICE_URL` belum diset — mode **DI agentic** butuh tools service.")
    st.caption({
        ExtractionMode.DOC_INTELLIGENCE: "1 langkah agentic (reviewer). DI dipanggil kode.",
        ExtractionMode.DOC_INTELLIGENCE_AGENTIC: "2 agen. Agen 1 **memanggil DI sebagai tool** — truly agentic.",
        ExtractionMode.MULTIMODAL: "2 agen. Agen 1 (vision) membaca gambar langsung.",
    }[mode])

with right:
    st.markdown("#### 2 · Unggah faktur atau pilih contoh")
    upload = st.file_uploader("Faktur (PDF / PNG / JPG)", type=["pdf", "png", "jpg", "jpeg"],
                              label_visibility="collapsed")

# Sample picker (from generated set).
sample_dir = settings.sample_invoices_dir
samples = sorted([p for p in sample_dir.glob("*.png")]) if sample_dir.exists() else []
sample_choice = None
_di_modes = (ExtractionMode.DOC_INTELLIGENCE, ExtractionMode.DOC_INTELLIGENCE_AGENTIC)
if samples:
    names = ["— (pakai unggahan) —"] + [p.stem for p in samples]
    pick = st.selectbox("…atau pilih faktur contoh (20 tersedia)", names)
    if pick != names[0]:
        # Prefer PDF for DI modes (better OCR), PNG for Multimodal (image input).
        stem = pick
        pdf = sample_dir / f"{stem}.pdf"
        png = sample_dir / f"{stem}.png"
        sample_choice = (pdf if mode in _di_modes and pdf.exists() else png)
else:
    st.caption("💡 Belum ada faktur contoh. Jalankan: `python scripts/generate_sample_invoices.py`")

st.markdown("#### 3 · Pengayaan data terstruktur (SQL Server) — opsional")
enrich_opt = st.radio(
    "Enrichment", ["Nonaktif", "🔵 REST tool → SQL", "🟢 MCP tool → SQL"],
    horizontal=True, label_visibility="collapsed",
    help="Agen Credit-Context membaca SQL Server (fasilitas, kredit pembeli, duplikat, "
         "watchlist) via REST atau MCP — protokol berbeda, query SQL sama.")
enrich = "rest" if enrich_opt.startswith("🔵") else "mcp" if enrich_opt.startswith("🟢") else "off"

run = st.button("▶️ Jalankan Review (agen Foundry)", type="primary")

# ---- Live flow ------------------------------------------------------------ #
st.markdown("#### 🎬 Alur Agen — LIVE")
flow_ph = st.empty()
fs = FlowState()
_run_flow(flow_ph, fs, mode_label)
log_ph = st.empty()
results = st.container()

# ---- Resolve input bytes -------------------------------------------------- #
def _resolve_input():
    if upload is not None:
        data = upload.getvalue()
        mime = "application/pdf" if upload.name.lower().endswith("pdf") else \
            ("image/jpeg" if upload.name.lower().endswith(("jpg", "jpeg")) else "image/png")
        return data, upload.name, mime
    if sample_choice is not None:
        data = sample_choice.read_bytes()
        mime = "application/pdf" if sample_choice.suffix == ".pdf" else "image/png"
        return data, sample_choice.name, mime
    return None, None, None


if run:
    image_bytes, source_name, mime = _resolve_input()
    if not image_bytes:
        st.warning("Unggah sebuah faktur atau pilih contoh terlebih dahulu.")
        st.stop()
    if mode == ExtractionMode.MULTIMODAL and mime == "application/pdf":
        st.warning("Opsi B (Multimodal) memerlukan gambar (PNG/JPG). Pilih file PNG contoh "
                   "atau unggah gambar.")
        st.stop()

    request_id = f"BCA-{uuid.uuid4().hex[:8]}"
    lines: list[str] = []

    def _on_event(node: str, state: str, detail: str = "") -> None:
        fs.apply(node, state)
        _run_flow(flow_ph, fs, mode_label)
        if detail:
            lines.insert(0, detail)
            with log_ph.container(height=170):
                for ln in lines:
                    st.markdown(ln)

    try:
        result, cost = run_async(run_invoice_review(
            image_bytes=image_bytes, source_name=source_name, mime=mime, mode=mode,
            request_id=request_id, enrich=enrich, on_event=_on_event))
    except Exception as exc:
        st.error(f"Gagal menjalankan agen: {exc}")
        st.stop()

    _run_flow(flow_ph, fs, mode_label)

    with results:
        st.divider()
        decision_banner(result["decision"])
        with st.container():
            st.caption("Alasan keputusan (deterministik):")
            for r in result["decision_reasons"]:
                st.markdown(f"- {r}")

        ex = result["extraction"]
        m1, m2, m3, m4 = st.columns(4)
        metric_tile(m1, "No. Faktur", ex.get("invoice_number") or "—")
        metric_tile(m2, "Total", rupiah(ex.get("total_amount_idr")))
        metric_tile(m3, "Advance (80%)", rupiah(result.get("advance_amount_idr")))
        metric_tile(m4, "Metode", mode_label)

        tab_rev, tab_ext, tab_sql, tab_gov, tab_tech = st.tabs(
            ["🔎 Review (Agen 2)", "📤 Ekstraksi (Agen 1)", "🏦 Konteks Kredit (SQL)",
             "🛡️ Audit & Biaya", "🔧 Log Teknis"])

        with tab_rev:
            rev = result["review"]
            st.markdown(f"**Kelengkapan data:** `{rev['data_sufficiency']}`")
            st.markdown("**Flag kebijakan:**", unsafe_allow_html=True)
            st.markdown(pills(rev.get("policy_flags", [])), unsafe_allow_html=True)
            if rev.get("missing_or_low_confidence"):
                st.markdown("**Kekurangan / keyakinan rendah:**")
                for it in rev["missing_or_low_confidence"]:
                    st.markdown(f"- {it}")
            if rev.get("risk_notes"):
                st.markdown("**Catatan risiko:**")
                for it in rev["risk_notes"]:
                    st.markdown(f"- {it}")
            st.success(f"**Rekomendasi:** {rev.get('recommendation', '—')}")

        with tab_ext:
            cext1, cext2 = st.columns([1, 1])
            with cext1:
                st.markdown("**Ringkasan field**")
                st.dataframe(pd.DataFrame([
                    {"field": "Penjual", "nilai": ex["seller"]["name"]},
                    {"field": "Rekening", "nilai": ex["seller"]["account"]},
                    {"field": "Pembeli", "nilai": ex["buyer"]["name"]},
                    {"field": "NPWP pembeli", "nilai": ex["buyer"]["npwp"] or "—"},
                    {"field": "Terbit", "nilai": ex["issue_date"] or "—"},
                    {"field": "Jatuh tempo", "nilai": ex["due_date"] or "—"},
                    {"field": "PO", "nilai": ex["po_number"] or "—"},
                    {"field": "Subtotal", "nilai": rupiah(ex["subtotal_idr"])},
                    {"field": "PPN", "nilai": rupiah(ex["tax_idr"])},
                    {"field": "Total", "nilai": rupiah(ex["total_amount_idr"])},
                ]), use_container_width=True, hide_index=True)
            with cext2:
                st.markdown("**Confidence per field**")
                conf = ex.get("confidence", {})
                if conf:
                    st.dataframe(pd.DataFrame(
                        [{"field": k, "confidence": v} for k, v in conf.items()]),
                        use_container_width=True, hide_index=True)
                else:
                    st.caption("Tidak ada skor confidence (umum untuk Opsi B / Multimodal).")
                with st.expander("JSON kanonik penuh"):
                    st.json(ex)

        with tab_sql:
            enr = result.get("enrichment")
            if not enr:
                st.info("Pengayaan SQL nonaktif. Pilih **REST** atau **MCP** di langkah 3 "
                        "untuk membaca data terstruktur dari SQL Server 2019.")
            else:
                proto = enr.get("_protocol", "?").upper()
                st.markdown(f"**Protokol:** `{proto}` → SQL Server 2019 "
                            f"(agen `bca-credit-context-{enr.get('_protocol')}`)")
                cinfo1, cinfo2 = st.columns(2)
                with cinfo1:
                    st.markdown("**Fasilitas klien**"); st.json(enr.get("facility", {}))
                    st.markdown("**Perilaku bayar pembeli**"); st.json(enr.get("payment_behaviour", {}))
                with cinfo2:
                    st.markdown("**Kredit pembeli**"); st.json(enr.get("buyer", {}))
                    st.markdown("**Duplikat / Watchlist**")
                    st.json({"duplicate": enr.get("duplicate", {}), "watchlist": enr.get("watchlist", {})})
                if enr.get("flags"):
                    st.markdown("**Flag risiko (dari data SQL):**")
                    st.markdown(pills(enr["flags"]), unsafe_allow_html=True)
                if enr.get("summary"):
                    st.success(enr["summary"])

        with tab_gov:
            g1, g2 = st.columns([3, 1])
            with g1:
                events = get_audit_logger().events_for(request_id)
                st.markdown("**Jejak audit (per langkah agen):**")
                st.dataframe([
                    {"step": e["step"], "actor": e["actor"], "decision": e["decision"],
                     "tokens": e["tokens"], "detail": e["detail"]} for e in events],
                    use_container_width=True, hide_index=True)
            with g2:
                metric_tile(st, "Total token", f"{cost['total_tokens']:,}")
                metric_tile(st, "Est. biaya (USD)", f"${cost['estimated_cost_usd']:.4f}")
                st.progress(min(1.0, cost["budget_used_pct"] / 100),
                            text=f"{cost['budget_used_pct']}% budget")

        with tab_tech:
            tech = tech_log.get(request_id)
            st.caption("Bukti layanan yang benar-benar dipanggil (Document Intelligence, agen "
                       "Foundry, pembacaan konfigurasi Blob, mesin aturan) beserta latensi.")
            for i, e in enumerate(tech, 1):
                proto, label = tech_log.endpoint_for(e["tool"])
                st.markdown(f"**{i}. `{proto}` · {label}** · {e['ms']} ms  \n"
                            f"↳ in → `{e['args']}` · out → `{e['result']}`")
            st.info("🔎 Selain log di atas, setiap pemanggilan agen juga tercatat di **Traces/"
                    "Monitor** pada project Foundry `financing`.")
