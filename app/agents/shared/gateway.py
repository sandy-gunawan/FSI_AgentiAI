"""AI Gateway (Azure API Management) routing helper — shared by v1 and v2.

Central decision point for whether a given agent call goes **direct** to Microsoft
Foundry or **through APIM** (so the gateway can enforce token limits, emit token
metrics, cache, etc.). The toggle is additive and OFF by default:

  * ``use_apim(via_apim)`` returns True only when APIM is *both requested and configured*
    — so flipping the portal toggle without a configured gateway safely falls back to the
    direct path (the UI shows the effective route).

This module is intentionally tiny and dependency-free so both runners can import it.
"""
from __future__ import annotations

from app.core.config import get_settings


def apim_configured() -> bool:
    """True when an APIM gateway URL + subscription key are available."""
    s = get_settings()
    return bool(s.apim_gateway_url and s.apim_subscription_key)


def use_apim(via_apim: bool | None = None) -> bool:
    """Resolve the effective routing decision.

    ``via_apim`` is the per-request override from the portal toggle:
      * None  -> fall back to the ``ROUTE_VIA_APIM`` setting default;
      * True  -> route via APIM *if configured*, else direct;
      * False -> always direct.
    """
    want = get_settings().route_via_apim if via_apim is None else bool(via_apim)
    return want and apim_configured()


def route_label(via_apim: bool | None = None) -> str:
    """Human/log label for the effective route: ``"apim"`` or ``"direct"``."""
    return "apim" if use_apim(via_apim) else "direct"


def apim_headers() -> dict[str, str]:
    """Gateway auth header (APIM subscription key)."""
    return {"Ocp-Apim-Subscription-Key": get_settings().apim_subscription_key}


def apim_base_url(kind: str) -> str:
    """Full base URL for a surface behind APIM.

    ``kind`` is ``"responses"`` (v2 agents/Responses API) or ``"chat"`` (v1
    chat-completions). Combines the gateway URL with the configured path suffix.
    """
    s = get_settings()
    suffix = s.apim_responses_path if kind == "responses" else s.apim_chat_path
    return s.apim_gateway_url.rstrip("/") + (suffix or "")
