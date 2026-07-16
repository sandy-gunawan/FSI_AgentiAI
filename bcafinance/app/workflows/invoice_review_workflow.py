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
from app.tools import doc_intelligence
from app.tools.json_utils import parse_json


async def run_invoice_review(
    *, image_bytes: bytes, source_name: str, mime: str, mode: ExtractionMode,
    request_id: str, on_event=None,
) -> tuple[dict, dict]:
    """Run the 2-agent invoice review. Returns (result, cost_summary)."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "invoice_review", "submitted", "portal",
                 f"mode={mode.value} file={source_name} ({len(image_bytes)} bytes)")

    with foundry_session(request_id) as (runner, cost):
        # ---- Agent 1: extraction (mode-dependent) --------------------------- #
        _emit("extract", "active",
              f"📤 **Agen 1 — Ekstraksi** ({'Document Intelligence' if mode == ExtractionMode.DOC_INTELLIGENCE else 'Multimodal'}) "
              f"membaca `{source_name}`…")

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
