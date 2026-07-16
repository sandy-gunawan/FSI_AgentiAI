"""Professional theme + reusable UI components for the bcafinance portal.

A single ``inject_theme()`` call applies a refined, corporate look (BCA-inspired
navy/blue palette, card surfaces, pill badges, gradient hero). Helper functions
render decision banners, metric cards, and section headers consistently.
"""
from __future__ import annotations

import streamlit as st

# BCA-inspired palette.
NAVY = "#0B2A5B"
BLUE = "#1565C0"
SKY = "#E8F1FC"
GOLD = "#F5A623"
GREEN = "#1B873F"
AMBER = "#B8860B"
RED = "#C0392B"

_CSS = f"""
<style>
:root {{
  --bca-navy: {NAVY}; --bca-blue: {BLUE}; --bca-sky: {SKY};
}}
/* Base */
.stApp {{ background: #F4F6FA; }}
section.main > div {{ padding-top: 1rem; }}
h1, h2, h3, h4 {{ color: {NAVY}; font-weight: 700; letter-spacing: -0.01em; }}

/* Hero header */
.bca-hero {{
  background: linear-gradient(120deg, {NAVY} 0%, {BLUE} 100%);
  border-radius: 18px; padding: 26px 30px; color: #fff; margin-bottom: 18px;
  box-shadow: 0 10px 30px rgba(11,42,91,0.18);
}}
.bca-hero h1 {{ color: #fff; margin: 0 0 4px 0; font-size: 1.7rem; }}
.bca-hero p {{ color: #dce8fb; margin: 0; font-size: 0.98rem; }}
.bca-chip {{
  display:inline-block; background: rgba(255,255,255,0.16); color:#fff;
  border:1px solid rgba(255,255,255,0.25); padding: 3px 12px; border-radius: 999px;
  font-size: 0.78rem; margin-right: 8px; margin-top: 10px;
}}

/* Cards */
.bca-card {{
  background:#fff; border:1px solid #E3E9F2; border-radius:14px; padding:18px 20px;
  box-shadow: 0 2px 10px rgba(16,42,91,0.05); margin-bottom: 14px;
}}
.bca-card h4 {{ margin-top:0; }}

/* Metric tiles */
.bca-metric {{
  background:#fff; border:1px solid #E3E9F2; border-radius:14px; padding:14px 18px;
  box-shadow:0 2px 10px rgba(16,42,91,0.05);
}}
.bca-metric .lbl {{ color:#607089; font-size:0.78rem; text-transform:uppercase; letter-spacing:0.04em; }}
.bca-metric .val {{ color:{NAVY}; font-size:1.5rem; font-weight:800; margin-top:2px; }}

/* Decision banner */
.bca-decision {{ border-radius:14px; padding:18px 22px; color:#fff; font-weight:700;
  display:flex; align-items:center; gap:14px; box-shadow:0 8px 24px rgba(0,0,0,0.12); }}
.bca-decision .big {{ font-size:1.5rem; }}
.bca-approve {{ background: linear-gradient(120deg, {GREEN}, #27ae60); }}
.bca-refer   {{ background: linear-gradient(120deg, {AMBER}, {GOLD}); }}
.bca-reject  {{ background: linear-gradient(120deg, {RED}, #e74c3c); }}

/* Pills */
.bca-pill {{ display:inline-block; padding:2px 11px; border-radius:999px; font-size:0.8rem;
  font-weight:600; margin:2px 4px 2px 0; }}
.pill-pass {{ background:#E6F4EA; color:{GREEN}; border:1px solid #B7E1C1; }}
.pill-watch {{ background:#FBF3E0; color:{AMBER}; border:1px solid #EAD8A6; }}
.pill-fail {{ background:#FCE9E7; color:{RED}; border:1px solid #F3C2BC; }}

/* Primary button */
.stButton>button[kind="primary"] {{
  background: {BLUE}; border:0; border-radius:10px; font-weight:700; padding:0.55rem 1.1rem;
}}
.stButton>button[kind="primary"]:hover {{ background:{NAVY}; }}

/* Radio as segmented control */
div[role="radiogroup"] {{ gap: 8px; }}

/* Sidebar */
section[data-testid="stSidebar"] {{ background:#fff; border-right:1px solid #E3E9F2; }}
</style>
"""


def inject_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, chips: list[str] | None = None) -> None:
    chip_html = "".join(f"<span class='bca-chip'>{c}</span>" for c in (chips or []))
    st.markdown(
        f"<div class='bca-hero'><h1>{title}</h1><p>{subtitle}</p>{chip_html}</div>",
        unsafe_allow_html=True,
    )


def metric_tile(col, label: str, value: str) -> None:
    col.markdown(
        f"<div class='bca-metric'><div class='lbl'>{label}</div>"
        f"<div class='val'>{value}</div></div>",
        unsafe_allow_html=True,
    )


def decision_banner(decision: str) -> None:
    cfg = {
        "APPROVE": ("bca-approve", "✅", "Disetujui (dapat dicairkan)"),
        "REFER": ("bca-refer", "🔎", "Diteruskan ke petugas kredit"),
        "REJECT": ("bca-reject", "⛔", "Ditolak (pelanggaran kebijakan)"),
    }.get(decision, ("bca-refer", "•", decision))
    st.markdown(
        f"<div class='bca-decision {cfg[0]}'><span class='big'>{cfg[1]} {decision}</span>"
        f"<span>· {cfg[2]}</span></div>",
        unsafe_allow_html=True,
    )


def pills(items: list[str]) -> str:
    out = []
    for it in items:
        low = it.lower()
        cls = "pill-pass" if low.startswith("pass") else "pill-fail" if low.startswith("fail") else "pill-watch"
        out.append(f"<span class='bca-pill {cls}'>{it}</span>")
    return " ".join(out) or "<span class='bca-pill pill-pass'>—</span>"
