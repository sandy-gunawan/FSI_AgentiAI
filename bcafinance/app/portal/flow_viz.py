"""Live flow visualization for the 2-agent invoice review.

Renders a compact 3-stage pipeline (Extract → Review → Decision) as inline HTML
that lights up as the workflow emits events. ``FlowState`` tracks node status.
"""
from __future__ import annotations

_NAVY = "#0B2A5B"
_BLUE = "#1565C0"
_GREEN = "#1B873F"
_GREY = "#9AA7BC"


class FlowState:
    """Tracks which pipeline nodes are active / done."""

    def __init__(self) -> None:
        self.active: set[str] = set()
        self.done: set[str] = set()

    def apply(self, node: str, state: str) -> None:
        if state == "active":
            self.active = {node}
        elif state == "done":
            self.active.discard(node)
            self.done.add(node)


def render_flow_html(active: set[str] | None = None, done: set[str] | None = None,
                     mode_label: str = "Document Intelligence") -> str:
    active = active or set()
    done = done or set()

    def node(key: str, icon: str, title: str, sub: str) -> str:
        if key in done:
            bg, br, fg, badge = "#EAF6EE", _GREEN, _NAVY, "✓"
        elif key in active:
            bg, br, fg, badge = "#E8F1FC", _BLUE, _NAVY, "●"
        else:
            bg, br, fg, badge = "#F4F6FA", "#DCE3EE", _GREY, "○"
        pulse = "animation:pulse 1.2s infinite;" if key in active else ""
        return f"""
        <div style="flex:1;background:{bg};border:2px solid {br};border-radius:14px;
             padding:14px 12px;text-align:center;{pulse}">
          <div style="font-size:26px;">{icon}</div>
          <div style="font-weight:700;color:{fg};font-size:14px;margin-top:4px;">{title}</div>
          <div style="color:#6B7A93;font-size:11px;margin-top:2px;">{sub}</div>
          <div style="color:{br};font-weight:800;margin-top:6px;">{badge}</div>
        </div>"""

    arrow = f"<div style='align-self:center;color:{_GREY};font-size:22px;padding:0 6px;'>→</div>"
    return f"""
    <style>@keyframes pulse{{0%{{box-shadow:0 0 0 0 rgba(21,101,192,.35);}}
      70%{{box-shadow:0 0 0 10px rgba(21,101,192,0);}}100%{{box-shadow:0 0 0 0 rgba(21,101,192,0);}}}}</style>
    <div style="display:flex;align-items:stretch;font-family:Segoe UI,Roboto,sans-serif;">
      {node("extract","📤","Agen 1 · Ekstraksi", mode_label)}
      {arrow}
      {node("review","🔎","Agen 2 · Reviewer","Kelengkapan + kebijakan")}
      {arrow}
      {node("decision","⚖️","Keputusan","Deterministik (rules)")}
    </div>"""
