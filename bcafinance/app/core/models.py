"""Domain models (pydantic) for bcafinance — Indonesia invoice financing.

Amounts in Indonesian Rupiah (IDR). Company tax ID = NPWP. Regulatory framing
follows OJK/BI norms for anjak piutang (invoice financing / discounting).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ExtractionMode(str, Enum):
    """Which Agent-1 extraction path produced the fields."""

    DOC_INTELLIGENCE = "doc_intelligence"            # Option 2: Python calls DI, agent normalizes
    DOC_INTELLIGENCE_AGENTIC = "doc_intelligence_agentic"  # Option 1: agent calls DI as a tool
    MULTIMODAL = "multimodal"                        # vision agent reads the image


class Decision(str, Enum):
    APPROVE = "APPROVE"   # advanceable as-is
    REFER = "REFER"       # route to human credit officer
    REJECT = "REJECT"     # hard policy breach


class LineItem(BaseModel):
    description: str = ""
    quantity: Optional[float] = None
    unit_price_idr: Optional[float] = None
    amount_idr: Optional[float] = None


class Party(BaseModel):
    name: str = ""
    account: str = ""
    npwp: str = ""


class InvoiceExtraction(BaseModel):
    """Canonical schema produced by BOTH extraction options (Agent 1)."""

    doc_type: str = "commercial_invoice"
    invoice_number: str = ""
    issue_date: str = ""            # YYYY-MM-DD
    due_date: str = ""              # YYYY-MM-DD
    term_days: Optional[int] = None
    seller: Party = Field(default_factory=Party)
    buyer: Party = Field(default_factory=Party)
    currency: str = "IDR"
    subtotal_idr: Optional[float] = None
    tax_idr: Optional[float] = None
    total_amount_idr: Optional[float] = None
    has_signature: Optional[bool] = None
    has_company_stamp: Optional[bool] = None
    po_number: str = ""
    line_items: list[LineItem] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)

    # Provenance (not from the model — set by the workflow)
    extraction_mode: ExtractionMode = ExtractionMode.DOC_INTELLIGENCE
    source_name: str = ""


class ReviewResult(BaseModel):
    """Agent 2 (reviewer) output — the human-readable review."""

    data_sufficiency: Literal["SUFFICIENT", "SUFFICIENT_WITH_NOTE", "INCOMPLETE"] = "INCOMPLETE"
    missing_or_low_confidence: list[str] = Field(default_factory=list)
    policy_flags: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    recommendation: str = ""


class PolicyDecision(BaseModel):
    """Deterministic decision computed by the config-driven rules engine."""

    decision: Decision
    reasons: list[str] = Field(default_factory=list)
    advance_amount_idr: Optional[int] = None


class AuditEvent(BaseModel):
    request_id: str
    use_case: str = "invoice_review"
    step: str
    actor: str
    detail: str
    decision: Optional[str] = None
    tokens: int = 0
    ts: datetime = Field(default_factory=datetime.utcnow)
