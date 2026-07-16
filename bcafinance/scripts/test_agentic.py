"""Quick end-to-end test of the DI-agentic mode (agent calls DI tool)."""
from __future__ import annotations

import asyncio
import pathlib

from app.core.config import get_settings
from app.core.models import ExtractionMode
from app.workflows.invoice_review_workflow import run_invoice_review


async def main() -> None:
    sample = get_settings().sample_invoices_dir / "INV-01-clean.png"
    data = sample.read_bytes()
    result, cost = await run_invoice_review(
        image_bytes=data, source_name=sample.name, mime="image/png",
        mode=ExtractionMode.DOC_INTELLIGENCE_AGENTIC, request_id="TEST-AGENTIC")
    ex = result["extraction"]
    print("decision      :", result["decision"])
    print("invoice_number:", ex.get("invoice_number"))
    print("total_amount  :", ex.get("total_amount_idr"))
    print("tokens        :", cost["total_tokens"])
    print("OK — agentic mode worked (agent called the analyze_invoice tool).")


if __name__ == "__main__":
    asyncio.run(main())
