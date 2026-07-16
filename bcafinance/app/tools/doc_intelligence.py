"""Option A extraction tool — Azure AI Document Intelligence (prebuilt-invoice).

Deterministic OCR: sends the invoice bytes to the ``prebuilt-invoice`` model and
returns a raw structured dict (fields + per-field confidence). This is a FACT
source (not reasoning), so it stays in Python. Agent 1A then normalizes it.
"""
from __future__ import annotations

from typing import Any

from app.core.config import get_settings


def _field(fields: dict, key: str) -> tuple[Any, float | None]:
    f = fields.get(key)
    if f is None:
        return None, None
    conf = getattr(f, "confidence", None)
    val = (getattr(f, "value_string", None) or getattr(f, "value_number", None)
           or getattr(f, "value_date", None) or getattr(f, "value_currency", None)
           or getattr(f, "content", None))
    if hasattr(val, "amount"):  # currency object
        val = val.amount
    return val, conf


def analyze_invoice(image_bytes: bytes) -> dict:
    """Return a raw structured dict from Document Intelligence prebuilt-invoice."""
    s = get_settings()
    if not s.doc_intelligence_configured:
        raise RuntimeError(
            "DOC_INTELLIGENCE_ENDPOINT is not set. Configure Document Intelligence "
            "(Option A) or use Option B (Multimodal)."
        )

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

    if s.doc_intelligence_key:
        from azure.core.credentials import AzureKeyCredential
        cred: Any = AzureKeyCredential(s.doc_intelligence_key)
    else:
        from azure.identity import DefaultAzureCredential
        cred = DefaultAzureCredential()

    client = DocumentIntelligenceClient(endpoint=s.doc_intelligence_endpoint, credential=cred)
    poller = client.begin_analyze_document(
        "prebuilt-invoice", AnalyzeDocumentRequest(bytes_source=image_bytes))
    result = poller.result()

    if not result.documents:
        return {"_raw": "no invoice detected", "confidence": {}}

    doc = result.documents[0]
    fields = doc.fields or {}
    out: dict[str, Any] = {"confidence": {}}

    def grab(di_key: str, canon: str) -> None:
        val, conf = _field(fields, di_key)
        if val is not None:
            out[canon] = str(val) if not isinstance(val, (int, float)) else val
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

    # Line items (best effort).
    items = []
    li = fields.get("Items")
    for it in (getattr(li, "value_array", None) or []):
        obj = getattr(it, "value_object", None) or {}
        def gv(k):
            v, _ = _field(obj, k)
            return v
        items.append({
            "description": str(gv("Description") or ""),
            "quantity": gv("Quantity"),
            "unit_price_idr": gv("UnitPrice"),
            "amount_idr": gv("Amount"),
        })
    if items:
        out["line_items"] = items
    return out
