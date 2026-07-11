"""Content safety & PII governance.

Two responsibilities:
  1. redact_pii()  — mask Indonesian PII (NIK, NPWP, phone, email) before any
     text is written to logs/audit or shown outside the secure flow.
  2. check_text()  — screen free-text inputs for harmful content using Azure AI
     Content Safety when configured, with a keyword fallback for offline demos.
"""
from __future__ import annotations

import logging
import re

from app.core.config import get_settings

logger = logging.getLogger("bns.content_safety")

# --- Indonesian PII patterns ------------------------------------------------ #
_NIK_RE = re.compile(r"\b\d{16}\b")
_NPWP_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}\b")
_PHONE_RE = re.compile(r"\+?62\d{8,12}\b")
_EMAIL_RE = re.compile(r"\b[\w.\-]+@[\w.\-]+\.\w+\b")

_HARMFUL_KEYWORDS = {"bomb", "terror", "kill", "senjata", "narkoba", "pencucian uang"}


def redact_pii(text: str) -> str:
    """Return text with Indonesian PII masked. Safe for logs and audit trails."""
    if not text:
        return text
    text = _NIK_RE.sub(lambda m: m.group()[:4] + "********" + m.group()[-4:], text)
    text = _NPWP_RE.sub("**.***.***.*-***.***", text)
    text = _PHONE_RE.sub(lambda m: m.group()[:5] + "****" + m.group()[-2:], text)
    text = _EMAIL_RE.sub(lambda m: m.group()[0] + "***@***", text)
    return text


def check_text(text: str) -> dict:
    """Screen text for harmful content.

    Returns {"safe": bool, "categories": [...], "provider": "azure"|"keyword"}.
    """
    settings = get_settings()
    if settings.content_safety_endpoint:
        result = _check_azure(text, settings)
        if result is not None:
            return result
    return _check_keyword(text)


def _check_azure(text: str, settings) -> dict | None:
    try:
        from azure.ai.contentsafety import ContentSafetyClient
        from azure.ai.contentsafety.models import AnalyzeTextOptions
        from azure.core.credentials import AzureKeyCredential

        if settings.content_safety_key:
            credential = AzureKeyCredential(settings.content_safety_key)
        else:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        client = ContentSafetyClient(settings.content_safety_endpoint, credential)
        resp = client.analyze_text(AnalyzeTextOptions(text=text))
        flagged = [c.category for c in resp.categories_analysis if c.severity and c.severity >= 4]
        return {"safe": not flagged, "categories": flagged, "provider": "azure"}
    except Exception as exc:  # pragma: no cover - offline fallback
        logger.warning("Content Safety unavailable, using keyword fallback: %s", exc)
        return None


def _check_keyword(text: str) -> dict:
    low = (text or "").lower()
    hits = [w for w in _HARMFUL_KEYWORDS if w in low]
    return {"safe": not hits, "categories": hits, "provider": "keyword"}
