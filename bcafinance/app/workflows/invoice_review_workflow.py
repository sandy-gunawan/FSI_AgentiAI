"""Invoice-review orchestration — 2 Foundry agents + deterministic decision.

Same shape for BOTH extraction options; only Agent 1 swaps:
  * mode = DOC_INTELLIGENCE : Document Intelligence (OCR) -> Agent bca-invoice-extractor-di
  * mode = MULTIMODAL       : Agent bca-invoice-extractor-vision (reads the image)

Agent 2 (bca-invoice-reviewer) is identical for both. The BINDING decision is
computed by the config-driven rules engine (never the LLM). Governance (tokens,
audit, technical log) is recorded throughout.
"""
from __future__ import annotations

import asyncio
import json

from app.agents.shared.foundry_runner import foundry_session
from app.core.models import ExtractionMode, InvoiceExtraction, ReviewResult
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.review import rules_engine
from app.tools import doc_intelligence, tools_client
from app.tools.json_utils import parse_json

# Map extracted invoice parties -> SQL ids (seed data is fixed for the demo).
_SELLER_ACCOUNT_TO_CLIENT = {
    "8820-1177-9043": "CLI-01", "8811-2244-1090": "CLI-02", "8890-5533-2211": "CLI-03",
    "8802-7788-6655": "CLI-04", "8877-1122-3344": "CLI-05",
}
_BUYER_NPWP_TO_ID = {
    "01.234.567.8-901.000": "BUY-01", "02.345.678.9-012.000": "BUY-02",
    "03.456.789.0-123.000": "BUY-03", "04.567.890.1-234.000": "BUY-04",
    "05.678.901.2-345.000": "BUY-05",
}


async def run_invoice_review(
    *, image_bytes: bytes, source_name: str, mime: str, mode: ExtractionMode,
    request_id: str, enrich: str = "off", on_event=None,
) -> tuple[dict, dict]:
    """Run the 2-agent invoice review. ``enrich`` = off|rest|mcp (SQL credit context).

    Returns (result, cost_summary).
    """
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "invoice_review", "submitted", "portal",
                 f"mode={mode.value} file={source_name} ({len(image_bytes)} bytes)")

    with foundry_session(request_id) as (runner, cost):
        # ---- Agent 1: extraction (mode-dependent) --------------------------- #
        _labels = {
            ExtractionMode.DOC_INTELLIGENCE: "Document Intelligence (Python memanggil DI)",
            ExtractionMode.DOC_INTELLIGENCE_AGENTIC: "DI Agentic (agen memanggil DI via tool)",
            ExtractionMode.MULTIMODAL: "Multimodal (agen membaca gambar)",
        }
        _emit("extract", "active", f"📤 **Agen 1 — Ekstraksi** ({_labels[mode]}) membaca `{source_name}`…")

        if mode == ExtractionMode.DOC_INTELLIGENCE:
            t0 = asyncio.get_event_loop().time()
            raw = await asyncio.to_thread(doc_intelligence.analyze_invoice, image_bytes)
            runner.tech.append({
                "tool": "doc_intelligence:analyze", "args": f"prebuilt-invoice · {source_name}",
                "result": f"{len(raw.get('confidence', {}))} fields",
                "ms": round((asyncio.get_event_loop().time() - t0) * 1000, 1)})
            extract_text = await asyncio.to_thread(
                runner.run, tool="foundry:extractor-di", step="extract",
                agent_key="bca-invoice-extractor-di",
                prompt=("Hasil OCR Document Intelligence (JSON mentah + confidence):\n"
                        + json.dumps(raw, ensure_ascii=False, default=str)
                        + "\n\nNormalisasi ke skema kanonik."))
        elif mode == ExtractionMode.DOC_INTELLIGENCE_AGENTIC:
            # Option 1: the AGENT calls DI itself via the tools-service OpenAPI tool.
            t0 = asyncio.get_event_loop().time()
            image_id = await asyncio.to_thread(tools_client.upload_image, image_bytes, source_name)
            runner.tech.append({
                "tool": "tools:upload-image", "args": f"{source_name} → image_id={image_id[:8]}…",
                "result": "stored", "ms": round((asyncio.get_event_loop().time() - t0) * 1000, 1)})
            extract_text = await asyncio.to_thread(
                runner.run, tool="foundry:extractor-di-agentic", step="extract",
                agent_key="bca-invoice-extractor-di-agentic",
                prompt=(f"Ekstrak faktur ini. image_id = \"{image_id}\". "
                        f"Panggil tool analyze_invoice dengan image_id tersebut, lalu "
                        f"normalisasi hasilnya ke skema kanonik."))
        else:
            extract_text = await asyncio.to_thread(
                runner.run_vision, tool="foundry:extractor-vision", step="extract",
                agent_key="bca-invoice-extractor-vision",
                prompt="Baca faktur pada gambar berikut dan ekstrak ke skema kanonik.",
                image_bytes=image_bytes, mime=mime)

        extraction = _to_extraction(parse_json(extract_text), mode, source_name)
        _emit("extract", "done",
              f"📤 **Agen 1** selesai · faktur `{extraction.invoice_number or '?'}` · "
              f"total Rp {int(extraction.total_amount_idr or 0):,}".replace(",", "."))

        # ---- Load current policy (hot-reload) ------------------------------- #
        rules = rules_engine.load_rules(runner.tech)

        # ---- Agent 2: reviewer (shared) ------------------------------------- #
        _emit("review", "active", "🔎 **Agen 2 — Reviewer** menilai kelengkapan & kepatuhan kebijakan…")
        review_text = await asyncio.to_thread(
            runner.run, tool="foundry:reviewer", step="review",
            agent_key="bca-invoice-reviewer",
            prompt=("DATA FAKTUR (JSON):\n"
                    + extraction.model_dump_json()
                    + "\n\n" + rules_engine.policy_block(rules)
                    + "\n\nNilai kelengkapan data & kepatuhan; kembalikan JSON review."))
        review = _to_review(parse_json(review_text))
        _emit("review", "done", f"🔎 **Agen 2** selesai · kelengkapan={review.data_sufficiency}")

        # ---- Optional: SQL credit-context enrichment (REST or MCP) ---------- #
        enrichment = None
        if enrich in ("rest", "mcp"):
            agent_key = f"bca-credit-context-{enrich}"
            client_id = _SELLER_ACCOUNT_TO_CLIENT.get(extraction.seller.account, "CLI-01")
            buyer_id = _BUYER_NPWP_TO_ID.get(extraction.buyer.npwp, "BUY-01")
            _emit("enrich", "active",
                  f"🏦 **Agen Credit-Context ({enrich.upper()})** membaca SQL Server · "
                  f"client={client_id} buyer={buyer_id}")
            enrich_text = await asyncio.to_thread(
                runner.run, tool=f"foundry:credit-context-{enrich}", step="enrich",
                agent_key=agent_key,
                prompt=(f"client_id={client_id}, buyer_id={buyer_id}, "
                        f"invoice_no={extraction.invoice_number or 'N/A'}, "
                        f"buyer_npwp={extraction.buyer.npwp or 'N/A'}. "
                        f"Panggil semua tool lalu rangkum konteks kredit."))
            enrichment = parse_json(enrich_text)
            enrichment["_protocol"] = enrich
            _emit("enrich", "done", f"🏦 **Credit-Context ({enrich.upper()})** selesai")

        # ---- Deterministic binding decision --------------------------------- #
        _emit("decision", "active", "⚖️ **Mesin aturan** menghitung keputusan mengikat (deterministik)…")
        policy = rules_engine.evaluate(extraction, rules)
        runner.tech.append({"tool": "rules:evaluate",
                            "args": f"mode={mode.value}", "result": policy.decision.value, "ms": 0.0})
        audit.record(request_id, "invoice_review", "final",
                     "foundry:bca-invoice-reviewer", review.recommendation[:400],
                     decision=policy.decision.value, tokens=cost.total_tokens)
        _emit("decision", "done", f"⚖️ Keputusan: **{policy.decision.value}**")

        tech_log.save(request_id, runner.tech)

    result = {
        "mode": mode.value,
        "extraction": extraction.model_dump(),
        "review": review.model_dump(),
        "decision": policy.decision.value,
        "decision_reasons": policy.reasons,
        "advance_amount_idr": policy.advance_amount_idr,
        "policy": rules["policy"],
        "enrichment": enrichment,
    }
    return result, cost.summary()


def _to_extraction(data: dict, mode: ExtractionMode, source_name: str) -> InvoiceExtraction:
    data = dict(data or {})
    data["extraction_mode"] = mode.value
    data["source_name"] = source_name
    try:
        return InvoiceExtraction.model_validate(data)
    except Exception:
        # Tolerant fallback so the pipeline never hard-crashes on a bad field.
        safe = InvoiceExtraction(extraction_mode=mode, source_name=source_name)
        for k in ("invoice_number", "issue_date", "due_date", "po_number", "currency"):
            if isinstance(data.get(k), str):
                setattr(safe, k, data[k])
        for k in ("subtotal_idr", "tax_idr", "total_amount_idr", "term_days"):
            v = data.get(k)
            if isinstance(v, (int, float)):
                setattr(safe, k, v)
        if isinstance(data.get("confidence"), dict):
            safe.confidence = {kk: float(vv) for kk, vv in data["confidence"].items()
                               if isinstance(vv, (int, float))}
        return safe


def _to_review(data: dict) -> ReviewResult:
    try:
        return ReviewResult.model_validate(data or {})
    except Exception:
        return ReviewResult(recommendation=str((data or {}).get("recommendation", "")))
