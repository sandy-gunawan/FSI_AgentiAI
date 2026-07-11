"""Domain models (pydantic) for the BNS financing demo — Indonesia context.

Amounts are in Indonesian Rupiah (IDR). Personal ID = NIK (16 digits),
company tax ID = NPWP. Regulatory framing follows OJK/BI norms.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Decision(str, Enum):
    APPROVE = "APPROVE"
    DECLINE = "DECLINE"
    REFER = "REFER"  # route to human review


class RiskTier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class EmploymentType(str, Enum):
    SALARIED = "salaried"
    SELF_EMPLOYED = "self_employed"


# --------------------------------------------------------------------------- #
# Use Case 1 — Retail personal loan (sequential pipeline)
# --------------------------------------------------------------------------- #
class RetailLoanApplication(BaseModel):
    customer_id: str = Field(examples=["CUST-1001"])
    full_name: str
    nik: str = Field(description="16-digit Indonesian national ID (PII)")
    dob: str = Field(description="YYYY-MM-DD")
    employment_type: EmploymentType
    monthly_income_idr: int
    requested_amount_idr: int
    tenor_months: int
    purpose: str


class IntakeResult(BaseModel):
    customer_id: str
    identity_verified: bool
    income_verified: bool
    verified_monthly_income_idr: int
    kyc_risk_rating: Literal["low", "medium", "high"]
    notes: str


class CreditAssessment(BaseModel):
    customer_id: str
    credit_score: int
    risk_grade: RiskTier
    monthly_debt_obligations_idr: int
    projected_installment_idr: int
    dti_ratio: float = Field(description="Debt-to-income incl. new installment")
    affordable: bool
    rationale: str


class ComplianceResult(BaseModel):
    decision: Decision
    triggered_rules: list[str] = Field(default_factory=list)
    sanctions_hit: bool = False
    reason: str


class LoanOffer(BaseModel):
    product_code: str
    approved_amount_idr: int
    tenor_months: int
    annual_rate_pct: float
    monthly_installment_idr: int
    total_repayment_idr: int


class RetailDecision(BaseModel):
    application: RetailLoanApplication
    decision: Decision
    offer: LoanOffer | None = None
    explanation: str
    routed_to_human: bool = False


# --------------------------------------------------------------------------- #
# Use Case 2 — SME/commercial financing (concurrent star + human-in-the-loop)
# --------------------------------------------------------------------------- #
class SMEFinancingRequest(BaseModel):
    company_id: str = Field(examples=["SME-5001"])
    legal_name: str
    npwp: str = Field(description="Company tax ID (PII)")
    sector: str
    requested_amount_idr: int
    tenor_months: int
    purpose: str
    collateral_id: str | None = None
    relationship_manager: str


class SpecialistFinding(BaseModel):
    specialist: str = Field(examples=["financial_analyst", "collateral", "aml_fraud", "market_risk"])
    risk_rating: Literal["low", "medium", "high"]
    score: float = Field(ge=0, le=100, description="0=worst, 100=best")
    key_findings: list[str] = Field(default_factory=list)
    summary: str


class UnderwritingRecommendation(BaseModel):
    company_id: str
    recommended_decision: Decision
    composite_risk_rating: Literal["low", "medium", "high"]
    recommended_amount_idr: int
    recommended_rate_pct: float
    findings: list[SpecialistFinding] = Field(default_factory=list)
    summary: str
    conditions: list[str] = Field(default_factory=list)


class HumanDecision(BaseModel):
    action: Literal["approve", "reject", "request_info"]
    officer_name: str
    notes: str = ""
    adjusted_amount_idr: int | None = None
    adjusted_rate_pct: float | None = None


class SMETermSheet(BaseModel):
    company_id: str
    legal_name: str
    facility_type: str
    approved_amount_idr: int
    tenor_months: int
    annual_rate_pct: float
    conditions: list[str] = Field(default_factory=list)
    approved_by: str
    decision: Decision


# --------------------------------------------------------------------------- #
# Use Case 3 — Smart Customer Servicing (ROUTING)
# --------------------------------------------------------------------------- #
class ServiceRequest(BaseModel):
    customer_id: str = Field(examples=["CUST-1001"])
    full_name: str
    channel: Literal["chat", "email", "call_center", "mobile_app"] = "chat"
    message: str = Field(description="Free-text customer message / inquiry")


class RoutingDecision(BaseModel):
    intent: Literal["dispute", "limit_increase", "hardship", "balance_inquiry", "general"]
    confidence: float = Field(ge=0, le=1, description="Router confidence 0-1")
    rationale: str


class ServiceResolution(BaseModel):
    intent: str
    status: Literal["resolved", "escalated", "info_provided"]
    actions_taken: list[str] = Field(default_factory=list)
    summary: str
    explanation: str


# --------------------------------------------------------------------------- #
# Use Case 4 — Loan Restructuring Advisor (EVALUATOR-OPTIMIZER / reflection)
# --------------------------------------------------------------------------- #
class RestructureRequest(BaseModel):
    customer_id: str = Field(examples=["CUST-1006"])
    full_name: str
    hardship_reason: str = Field(description="Why the borrower needs relief (free text)")
    requested_relief: str | None = Field(
        default=None, description="Optional preferred relief (e.g. 'perpanjang tenor')")


class RestructureProposal(BaseModel):
    principal_idr: int = Field(description="Outstanding principal being restructured")
    new_tenor_months: int
    new_rate_pct: float
    grace_period_months: int = Field(ge=0, description="Payment holiday on principal")
    new_installment_idr: int
    rationale: str


class ProposalCritique(BaseModel):
    approved: bool = Field(description="True if proposal passes the evaluator")
    score: float = Field(ge=0, le=100, description="Overall quality/affordability score")
    affordability_ok: bool
    policy_ok: bool
    issues: list[str] = Field(default_factory=list)
    feedback: str = Field(description="Concrete guidance for the next revision")


class RestructureOutcome(BaseModel):
    customer_id: str
    decision: Decision
    final_proposal: RestructureProposal | None = None
    iterations: int = Field(description="How many propose→evaluate rounds ran")
    explanation: str


# --------------------------------------------------------------------------- #
# Use Case 5 — AML / Fraud Investigation (ReAct + human SAR gate)
# --------------------------------------------------------------------------- #
class AmlInvestigationRequest(BaseModel):
    subject_id: str = Field(examples=["CUST-1010"], description="Customer under review")
    subject_name: str
    alert_type: str = Field(description="Triggering alert typology")
    alert_detail: str


class SARRecommendation(BaseModel):
    subject_id: str
    risk_level: Literal["low", "medium", "high"]
    file_sar: bool = Field(description="Whether to recommend filing a SAR/LTKM to PPATK")
    typologies: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    narrative: str = Field(description="Investigation narrative (Indonesian)")
    recommended_action: str


class SARDecision(BaseModel):
    action: Literal["file", "dismiss", "escalate"]
    analyst_name: str
    notes: str = ""


class SARFiling(BaseModel):
    subject_id: str
    filed: bool
    decision: Decision
    narrative: str
    filed_by: str


# --------------------------------------------------------------------------- #
# Use Case 6 — Credit Committee (GROUP CHAT)
# --------------------------------------------------------------------------- #
class CommitteeRequest(BaseModel):
    company_id: str = Field(examples=["SME-5001"])
    legal_name: str
    requested_amount_idr: int
    tenor_months: int
    purpose: str


class CommitteeTurn(BaseModel):
    speaker: str = Field(description="e.g. Risk Optimist / Risk Skeptic / Compliance")
    stance: Literal["approve", "reject", "neutral"]
    argument: str


class CommitteeDecision(BaseModel):
    company_id: str
    decision: Decision
    rounds: int
    transcript: list[CommitteeTurn] = Field(default_factory=list)
    consensus: bool = False
    summary: str


# --------------------------------------------------------------------------- #
# Use Case 7 — Complex Investigation (MAGENTIC)
# --------------------------------------------------------------------------- #
class MagenticRequest(BaseModel):
    subject_id: str = Field(examples=["SME-5008"])
    subject_name: str
    objective: str = Field(description="Open-ended investigation objective")


class LedgerStep(BaseModel):
    task: str
    assigned_to: Literal["kyc", "transactions", "credit", "financials"]
    status: Literal["planned", "done"] = "planned"
    finding: str = ""


class MagenticPlan(BaseModel):
    steps: list[LedgerStep] = Field(default_factory=list)


class MagenticDossier(BaseModel):
    subject_id: str
    objective: str
    steps: list[LedgerStep] = Field(default_factory=list)
    replans: int = 0
    risk_level: Literal["low", "medium", "high"]
    findings: list[str] = Field(default_factory=list)
    recommendation: str
    summary: str


# --------------------------------------------------------------------------- #
# Use Case 8 — Syndicated / Co-Financing (A2A · Agent2Agent protocol)
# --------------------------------------------------------------------------- #
class SyndicationRequest(BaseModel):
    company_id: str = Field(examples=["SME-5001"])
    legal_name: str
    sector: str
    requested_amount_idr: int
    tenor_months: int
    purpose: str


class ParticipationOffer(BaseModel):
    partner_name: str
    decision: Decision
    participation_amount_idr: int
    indicative_rate_pct: float
    conditions: list[str] = Field(default_factory=list)
    rationale: str


class SyndicationResult(BaseModel):
    company_id: str
    total_amount_idr: int
    bns_amount_idr: int
    syndicated_target_idr: int
    partner_offer: ParticipationOffer | None = None
    arranged_amount_idr: int
    shortfall_idr: int
    blended_rate_pct: float
    decision: Decision
    summary: str


# --------------------------------------------------------------------------- #
# Governance / audit
# --------------------------------------------------------------------------- #
class AuditEvent(BaseModel):
    request_id: str
    use_case: Literal["retail", "sme", "servicing", "restructure", "aml",
                      "committee", "magentic", "syndication"]
    step: str
    actor: str = Field(description="agent / tool / human / system")
    detail: str
    decision: str | None = None
    tokens: int = 0
    ts: datetime = Field(default_factory=datetime.utcnow)
