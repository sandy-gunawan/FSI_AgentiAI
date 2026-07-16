"""Config-driven review rules — the "change on the fly" engine.

TWO LAYERS (see docs/07):
  * Layer 1 (stable): the reviewer agent's role + output schema live in Foundry.
  * Layer 2 (dynamic): the POLICY VALUES below are read FRESH on every request and
    (a) injected into the reviewer prompt, and (b) drive the deterministic decision.

Source precedence per request (no caching -> genuine hot-reload):
  1. Blob Storage (BLOB_CONTAINER_CONFIG/REVIEW_RULES_BLOB) if BLOB_ACCOUNT_URL set.
  2. Local config/review_rules.yaml otherwise.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import yaml

from app.core.config import get_settings
from app.core.models import Decision, InvoiceExtraction, PolicyDecision

_DEFAULTS: dict[str, Any] = {
    "policy": {
        "max_facility_idr": 1_000_000_000,
        "advance_rate": 0.80,
        "max_tenor_days": 180,
        "min_confidence": 0.75,
        "max_buyer_concentration": 0.40,
    },
    "required_fields": [
        "invoice_number", "issue_date", "due_date", "total_amount_idr",
        "seller_name", "buyer_name", "buyer_npwp",
    ],
    "reviewer_guidance": "Terapkan kebijakan anjak piutang BCA Finance sesuai norma OJK/BI.",
}


def load_rules(tech: list[dict] | None = None) -> dict[str, Any]:
    """Load review rules FRESH (no cache). Blob first, then local YAML, then defaults."""
    s = get_settings()

    if s.blob_configured:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient

            svc = BlobServiceClient(account_url=s.blob_account_url,
                                    credential=DefaultAzureCredential())
            blob = svc.get_blob_client(container=s.blob_container_config, blob=s.review_rules_blob)
            raw = blob.download_blob().readall().decode("utf-8")
            if tech is not None:
                tech.append({"tool": "blob:read-rules", "args": s.review_rules_blob,
                             "result": f"{len(raw)} bytes", "ms": 0.0})
            return _merge(yaml.safe_load(raw) or {})
        except Exception:
            pass  # fall through to local

    if s.local_rules_path.exists():
        raw = s.local_rules_path.read_text(encoding="utf-8")
        if tech is not None:
            tech.append({"tool": "blob:read-rules", "args": "config/review_rules.yaml (local)",
                         "result": f"{len(raw)} bytes", "ms": 0.0})
        return _merge(yaml.safe_load(raw) or {})

    return dict(_DEFAULTS)


def save_rules(rules: dict) -> str:
    """Persist edited rules so the NEXT request picks them up (hot-reload, no redeploy).

    Writes the local ``config/review_rules.yaml`` (read fresh by ``load_rules``) and, when
    Blob is configured, also uploads to Blob. Returns the YAML text written.
    """
    merged = _merge(rules)
    text = yaml.safe_dump(merged, allow_unicode=True, sort_keys=False)
    s = get_settings()
    s.local_rules_path.parent.mkdir(parents=True, exist_ok=True)
    s.local_rules_path.write_text(text, encoding="utf-8")

    if s.blob_configured:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient

            svc = BlobServiceClient(account_url=s.blob_account_url,
                                    credential=DefaultAzureCredential())
            blob = svc.get_blob_client(container=s.blob_container_config, blob=s.review_rules_blob)
            blob.upload_blob(text.encode("utf-8"), overwrite=True)
        except Exception:
            pass  # local write already succeeded
    return text


def _merge(loaded: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in _DEFAULTS.items()}
    if "policy" in loaded and isinstance(loaded["policy"], dict):
        out["policy"].update(loaded["policy"])
    if "required_fields" in loaded:
        out["required_fields"] = list(loaded["required_fields"])
    if "reviewer_guidance" in loaded:
        out["reviewer_guidance"] = str(loaded["reviewer_guidance"])
    return out


# --------------------------------------------------------------------------- #
# Prompt injection — turn the config into a POLICY block for the reviewer agent
# --------------------------------------------------------------------------- #
def policy_block(rules: dict) -> str:
    p = rules["policy"]
    req = ", ".join(rules["required_fields"])
    return (
        "POLICY (berlaku saat ini — patuhi persis):\n"
        f"- Batas fasilitas maksimal: Rp {int(p['max_facility_idr']):,}\n"
        f"- Advance rate: {p['advance_rate'] * 100:.0f}% dari nilai faktur\n"
        f"- Tenor maksimal (issue->due): {p['max_tenor_days']} hari\n"
        f"- Keyakinan minimal per field: {p['min_confidence']:.2f}\n"
        f"- Field wajib: {req}\n"
        f"PANDUAN: {rules['reviewer_guidance'].strip()}"
    ).replace(",", ".")


# --------------------------------------------------------------------------- #
# Deterministic decision — the BINDING call (never the LLM)
# --------------------------------------------------------------------------- #
def _field_value(inv: InvoiceExtraction, key: str) -> Any:
    mapping = {
        "invoice_number": inv.invoice_number,
        "issue_date": inv.issue_date,
        "due_date": inv.due_date,
        "total_amount_idr": inv.total_amount_idr,
        "seller_name": inv.seller.name,
        "buyer_name": inv.buyer.name,
        "buyer_npwp": inv.buyer.npwp,
        "po_number": inv.po_number,
    }
    return mapping.get(key)


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s.strip()[:10])
    except Exception:
        return None


def evaluate(inv: InvoiceExtraction, rules: dict) -> PolicyDecision:
    """Compute the binding decision + reasons from extraction + current rules."""
    p = rules["policy"]
    reasons: list[str] = []
    hard_breach = False
    needs_review = False

    # 1) Required fields present?
    missing = [f for f in rules["required_fields"] if not _field_value(inv, f)]
    if missing:
        needs_review = True
        reasons.append(f"Field wajib belum lengkap: {', '.join(missing)}")

    # 2) Amount within facility limit (hard breach if over).
    total = inv.total_amount_idr or 0
    if total > p["max_facility_idr"]:
        hard_breach = True
        reasons.append(
            f"Nilai faktur Rp {int(total):,} melebihi batas fasilitas "
            f"Rp {int(p['max_facility_idr']):,}".replace(",", "."))
    elif total <= 0:
        needs_review = True
        reasons.append("Total faktur tidak terbaca / nol.")

    # 3) Tenor within policy.
    d1, d2 = _parse_date(inv.issue_date), _parse_date(inv.due_date)
    if d1 and d2:
        term = (d2 - d1).days
        if term > p["max_tenor_days"]:
            hard_breach = True
            reasons.append(f"Tenor {term} hari melebihi maksimum {p['max_tenor_days']} hari.")
        elif term <= 0:
            needs_review = True
            reasons.append("Tanggal jatuh tempo tidak valid (<= tanggal terbit).")
    else:
        needs_review = True
        reasons.append("Tanggal terbit / jatuh tempo tidak dapat diparse.")

    # 4) Arithmetic consistency (subtotal + tax ~= total).
    if inv.subtotal_idr is not None and inv.tax_idr is not None and total:
        if abs((inv.subtotal_idr + inv.tax_idr) - total) > max(1000, 0.01 * total):
            needs_review = True
            reasons.append("Aritmetika faktur tidak konsisten (subtotal + PPN != total).")

    # 5) Low-confidence required fields.
    low = [f for f in rules["required_fields"]
           if f in inv.confidence and inv.confidence[f] < p["min_confidence"]]
    if low:
        needs_review = True
        reasons.append(f"Keyakinan rendah pada: {', '.join(low)} (< {p['min_confidence']:.2f}).")

    if hard_breach:
        decision = Decision.REJECT
    elif needs_review:
        decision = Decision.REFER
    else:
        decision = Decision.APPROVE
        reasons.append("Seluruh cek kebijakan & kelengkapan terpenuhi.")

    advance = int(total * p["advance_rate"]) if total and decision != Decision.REJECT else None
    return PolicyDecision(decision=decision, reasons=reasons, advance_amount_idr=advance)
