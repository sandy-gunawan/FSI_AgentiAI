"""Shared helpers for the Streamlit portal."""
from __future__ import annotations

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Run an async workflow from Streamlit's synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():  # pragma: no cover
            import nest_asyncio  # type: ignore

            nest_asyncio.apply()
            return loop.run_until_complete(coro)  # type: ignore[arg-type]
    except RuntimeError:
        pass
    return asyncio.run(coro)  # type: ignore[arg-type]


def rupiah(amount: int | float | None) -> str:
    if amount is None:
        return "-"
    return f"Rp {int(amount):,}".replace(",", ".")


def render_gateway_toggle(key: str) -> bool:
    """Sidebar toggle: route this run via APIM AI Gateway vs direct to Foundry.

    Returns the *requested* boolean; the effective route (which falls back to direct
    when APIM is not configured) is shown as a badge. Pass the returned value as
    ``via_apim=`` to the workflow.
    """
    import streamlit as st

    from app.agents.shared.gateway import apim_configured, use_apim

    with st.sidebar:
        st.divider()
        st.caption("🌐 AI Gateway (APIM)")
        want = st.toggle(
            "Route via APIM", value=st.session_state.get(f"{key}_apim", False), key=f"{key}_apim",
            help="Kirim panggilan agen melalui Azure API Management (token limit, metrics, cache). "
                 "Bila APIM belum dikonfigurasi, otomatis kembali ke DIRECT.",
        )
        effective = use_apim(want)
        badge = "🟢 **APIM**" if effective else "⚪ **Direct**"
        if want and not apim_configured():
            st.caption(f"Rute efektif: {badge} · ⚠️ APIM belum dikonfigurasi → fallback direct")
        else:
            st.caption(f"Rute efektif: {badge}")
    return want


def render_tech_log(request_id: str, height: int = 260) -> None:
    """Collapsible, scrollable technical log proving the real MCP/API calls."""
    import streamlit as st

    from app.core.config import get_settings
    from app.governance import tech_log

    tech = tech_log.get(request_id)
    with st.expander(f"🔧 Log Teknis — bukti pemanggilan MCP/API nyata ({len(tech)} panggilan)"):
        st.caption("Setiap baris = pemanggilan tool NYATA oleh agen ke sistem cloud: nama tool, argumen "
                   "masuk (in), data yang dikembalikan (out), dan latensi (ms). URL = endpoint Azure "
                   "Container Apps yang benar-benar dipanggil.")
        base = get_settings().rest_base_url
        with st.container(height=height):
            if not tech:
                st.caption("Belum ada panggilan tool tercatat untuk permohonan ini.")
            for i, e in enumerate(tech, 1):
                proto, path, label = tech_log.endpoint_for(e["tool"])
                url = e.get("url") or f"{base}{path}"
                st.markdown(
                    f"**{i}. `{proto}` · {label}** · `{e['tool']}()` · {e['ms']} ms  \n"
                    f"↳ URL: `{url}`  \n"
                    f"↳ **in** → `{e['args']}`  \n"
                    f"↳ **out** ← `{e['result']}`"
                )


def render_pattern_explainer(pattern: str, what: str, flow: str, how: str, why: str,
                             ms_term: str) -> None:
    """Explain the agentic pattern used by a use case: what, how, why + MS term."""
    import streamlit as st

    with st.expander(f"🧠 Pola agentic yang dipakai: **{pattern}** — apa, bagaimana, kenapa",
                     expanded=False):
        st.markdown(f"🏷️ **Microsoft Agent Framework — orkestrasi:** {ms_term}")
        st.markdown(f"**Apa itu pola ini?**  \n{what}")
        st.markdown(f"**Alur (flow):**")
        st.code(flow, language="text")
        st.markdown(f"**Bagaimana bekerja di skenario ini?**  \n{how}")
        st.markdown(f"**Kenapa pola ini cocok untuk skenario ini?**  \n{why}")


def render_audit_legend() -> None:
    """Newbie-friendly explanation of the 'decision' and 'tokens' columns."""
    import streamlit as st

    with st.expander("ℹ️ Apa arti kolom **tokens** & **decision**? (penjelasan untuk awam)"):
        st.markdown(
            "Di setiap langkah agen ada **dua hal berbeda** yang terjadi:\n\n"
            "1. **Panggil API / MCP** untuk **mengambil data** (Core Banking, Credit Bureau/SLIK, KYC). "
            "Ini pemanggilan API **nyata** — lihat **🔧 Log Teknis**. *Tidak* memakai token.\n"
            "2. **Panggil model AI** (gpt-4o-mini di Microsoft Foundry) untuk **menalar** data dan "
            "menghasilkan output terstruktur/penjelasan. Inilah yang memakai **tokens**.\n\n"
            "**Token** = satuan teks yang diproses model AI (1 token ≈ beberapa huruf). "
            "`input token` = data/prompt yang dikirim ke model; `output token` = jawaban yang dibuat model. "
            "Jadi **token = pemakaian model AI** (dan penentu biaya), **bukan** jumlah panggilan API.\n\n"
            "**Kenapa sebagian baris 0 token?**\n"
            "- `intake`, `credit_risk`, `decision`, `final` → memakai **model AI** → **ada token**.\n"
            "- `submitted`, `content_safety`, `compliance` → **deterministik / tanpa AI** "
            "(compliance = mesin aturan OJK/BI, logika biasa) → **0 token**.\n\n"
            "**Kenapa hanya sebagian baris punya `decision`?** Kolom `decision` hanya terisi pada langkah "
            "yang benar-benar **membuat/mencatat keputusan** — `compliance` (APPROVE/DECLINE/REFER) dan "
            "`final` (hasil akhir). Langkah pengumpulan data tidak membuat keputusan → kosong (None).\n\n"
            "> Token bukan hanya untuk ringkasan — mencakup **seluruh** input+output model: membaca data, "
            "mengekstrak field, menalar, dan menulis penjelasan. Total token → estimasi biaya (USD)."
        )
