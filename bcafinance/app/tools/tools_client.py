"""Client for the bcafinance tools service (Option 1 — agentic DI).

The portal/orchestrator uploads the invoice image here to get an ``image_id``. That id
is then handed to the ``bca-invoice-extractor-di-agentic`` agent, which calls the tools
service's ``analyze_invoice`` endpoint ITSELF (server-side, as a Foundry OpenAPI tool).
"""
from __future__ import annotations

import base64

import httpx

from app.core.config import get_settings


def upload_image(image_bytes: bytes, filename: str = "invoice") -> str:
    """Upload an image to the tools service; return its image_id."""
    s = get_settings()
    if not s.tools_service_configured:
        raise RuntimeError("TOOLS_SERVICE_URL is not set — Option 1 (agentic DI) unavailable.")
    url = s.tools_service_url.rstrip("/") + "/images"
    payload = {"filename": filename, "content_b64": base64.b64encode(image_bytes).decode("ascii")}
    resp = httpx.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["image_id"]
