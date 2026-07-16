"""bcafinance tools service — the DI wrapper that a Foundry agent calls as a tool.

Two endpoints:
  * POST /images          {filename, content_b64}  -> {image_id}   (portal pre-uploads the image)
  * POST /analyze_invoice {image_id}               -> DI fields     (the AGENT calls this)

This is what makes Option 1 genuinely agentic: the extractor agent decides to call
`analyze_invoice` itself (server-side in Foundry), instead of the orchestrator calling DI.

Runs as a single-replica Container App (`ca-bcafinance-tools`) with a managed identity
that has `Cognitive Services User` on the Document Intelligence resource. Anonymous ingress
(demo posture) — no secrets are exposed; DI is reached via managed identity.
"""
from __future__ import annotations

import base64
import os
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="bcafinance-tools", version="1.0.0",
              description="Document Intelligence wrapper tools for the invoice extractor agent.")

# Bounded in-memory image store (single replica). Keeps the last N uploads.
_MAX = 64
_IMAGES: "OrderedDict[str, bytes]" = OrderedDict()

DI_ENDPOINT = os.getenv("DOC_INTELLIGENCE_ENDPOINT", "")
DI_KEY = os.getenv("DOC_INTELLIGENCE_KEY", "")


class UploadRequest(BaseModel):
    filename: str = "invoice"
    content_b64: str


class UploadResponse(BaseModel):
    image_id: str


class AnalyzeRequest(BaseModel):
    image_id: str


@app.get("/", operation_id="health")
def health() -> dict:
    return {"status": "ok", "di_configured": bool(DI_ENDPOINT), "images_cached": len(_IMAGES)}


@app.post("/images", response_model=UploadResponse, operation_id="upload_image")
def upload_image(req: UploadRequest) -> UploadResponse:
    """Store an invoice image and return an id the agent can reference."""
    try:
        data = base64.b64decode(req.content_b64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid base64: {exc}")
    image_id = uuid.uuid4().hex
    _IMAGES[image_id] = data
    while len(_IMAGES) > _MAX:
        _IMAGES.popitem(last=False)
    return UploadResponse(image_id=image_id)


@app.post("/analyze_invoice", operation_id="analyze_invoice")
def analyze_invoice(req: AnalyzeRequest) -> dict:
    """Run Azure AI Document Intelligence (prebuilt-invoice) on a stored image.

    THE AGENT CALLS THIS. Returns raw extracted fields + per-field confidence.
    """
    data = _IMAGES.get(req.image_id)
    if data is None:
        raise HTTPException(status_code=404, detail="image_id not found (expired or never uploaded)")
    if not DI_ENDPOINT:
        raise HTTPException(status_code=500, detail="DOC_INTELLIGENCE_ENDPOINT not configured")
    return _run_di(data)


def _run_di(image_bytes: bytes) -> dict:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

    if DI_KEY:
        from azure.core.credentials import AzureKeyCredential
        cred: Any = AzureKeyCredential(DI_KEY)
    else:
        from azure.identity import DefaultAzureCredential
        cred = DefaultAzureCredential()

    client = DocumentIntelligenceClient(endpoint=DI_ENDPOINT, credential=cred)
    poller = client.begin_analyze_document("prebuilt-invoice", AnalyzeDocumentRequest(bytes_source=image_bytes))
    result = poller.result()
    if not result.documents:
        return {"_raw": "no invoice detected", "confidence": {}}

    fields = result.documents[0].fields or {}
    out: dict[str, Any] = {"confidence": {}}

    def grab(di_key: str, canon: str) -> None:
        f = fields.get(di_key)
        if f is None:
            return
        val = (getattr(f, "value_string", None) or getattr(f, "value_number", None)
               or getattr(f, "value_date", None) or getattr(f, "value_currency", None)
               or getattr(f, "content", None))
        if hasattr(val, "amount"):
            val = val.amount
        if val is not None:
            out[canon] = val if isinstance(val, (int, float)) else str(val)
        conf = getattr(f, "confidence", None)
        if conf is not None:
            out["confidence"][canon] = round(float(conf), 2)

    grab("InvoiceId", "invoice_number")
    grab("InvoiceDate", "issue_date")
    grab("DueDate", "due_date")
    grab("VendorName", "seller_name")
    grab("CustomerName", "buyer_name")
    grab("CustomerTaxId", "buyer_npwp")
    grab("SubTotal", "subtotal_idr")
    grab("TotalTax", "tax_idr")
    grab("InvoiceTotal", "total_amount_idr")
    grab("PurchaseOrder", "po_number")
    return out
