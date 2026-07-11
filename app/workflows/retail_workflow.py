"""Use Case 1 — Retail personal loan auto-assessment.

Communication architecture: SEQUENTIAL ("serial") pipeline.
    Intake  ->  Credit Risk  ->  Compliance (deterministic gate)  ->  Decision/Offer

Straight-through processing: no human in the loop. Amounts at/above the OJK
auto-approve ceiling are REFERred to human review (Use Case 2 territory).
Every step is audited; token usage is budget-tracked.
"""
from __future__ import annotations

from app.agents.retail.agents import CREDIT_RISK_AGENT, DECISION_AGENT, INTAKE_AGENT
from app.agents.shared.model_client import financing_session
from app.core.models import (
    ComplianceResult,
    CreditAssessment,
    Decision,
    IntakeResult,
    LoanOffer,
    RetailDecision,
    RetailLoanApplication,
    RiskTier,
)
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance.rules_engine import debt_burden_ratio, monthly_installment
from app.governance import tech_log
from app.tools.mcp_tools import credit_bureau_tool, kyc_aml_tool
from app.tools.rest_tools import get_account_summary
from app.workflows import data_access as sor
from mock_services.data import load
from mock_services.policy import evaluate_retail


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


PRODUCT_CODE = "KTA-STD"


async def run_retail(application: RetailLoanApplication, request_id: str,
                     on_event=None) -> tuple[RetailDecision, dict]:
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "retail", "submitted", "portal",
                 redact_pii(f"{application.full_name} mengajukan {application.requested_amount_idr:,} IDR "
                            f"tenor {application.tenor_months} bln — {application.purpose}"))

    # ---- Governance: content safety on free text ----
    safety = check_text(application.purpose)
    audit.record(request_id, "retail", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    # ---- System-of-record facts (deterministic) ----
    cust = sor.customer(application.customer_id)
    credit = sor.credit_individual(application.customer_id)
    kyc = sor.kyc_individual(cust["nik"])
    age = sor.age_from_dob(cust["dob"])

    products = load("products.json")
    grade = credit.get("risk_grade", "D")
    rate = products["base_rate_pct"] + products["risk_spread_by_grade"].get(grade, 7.0)
    installment = monthly_installment(application.requested_amount_idr, rate, application.tenor_months)
    dbr = debt_burden_ratio(cust["monthly_income_idr"],
                            credit.get("monthly_debt_obligations_idr", 0), installment)

    async with financing_session(request_id, "retail") as (runner, cost):
        # ---- Stage 1: Intake & verification (KYC MCP + core banking REST) ----
        _emit("intake", "active",
              f"🧾 **Intake & Verifikasi** aktif · Tool: KYC/AML MCP `screen_individual` + "
              f"Core Banking `get_account_summary`. Masukan: customer_id={application.customer_id}, "
              f"penghasilan_diklaim={_rp(application.monthly_income_idr)}/bln.")
        async with kyc_aml_tool() as kyc_tool:
            intake: IntakeResult = await runner.run(
                step="intake", name="IntakeAgent", instructions=INTAKE_AGENT,
                response_format=IntakeResult,
                tools=[get_account_summary, kyc_tool],
                prompt=(
                    f"Applicant: customer_id={application.customer_id}, name={application.full_name}, "
                    f"NIK={cust['nik']}, employment={application.employment_type.value}, "
                    f"declared_monthly_income_idr={application.monthly_income_idr}."
                ),
            )

        # ---- Stage 2: Credit risk scoring (Credit Bureau MCP) ----
        _emit("intake", "done",
              f"🧾 **Intake & Verifikasi** selesai · Hasil: identitas_terverifikasi={intake.identity_verified}, "
              f"penghasilan_terverifikasi={_rp(intake.verified_monthly_income_idr)}/bln, "
              f"risiko_KYC={intake.kyc_risk_rating}.")
        _emit("credit", "active",
              f"📊 **Credit Risk Scoring** aktif · Tool: Credit Bureau MCP `get_credit_report`. "
              f"Masukan: customer_id={application.customer_id}, plafon={_rp(application.requested_amount_idr)}, "
              f"tenor={application.tenor_months} bln.")
        async with credit_bureau_tool() as credit_tool:
            assessment: CreditAssessment = await runner.run(
                step="credit_risk", name="CreditRiskAgent", instructions=CREDIT_RISK_AGENT,
                response_format=CreditAssessment,
                tools=[credit_tool],
                prompt=(
                    f"customer_id={application.customer_id}. Requested amount "
                    f"{application.requested_amount_idr} IDR over {application.tenor_months} months. "
                    f"Projected monthly installment ~{installment} IDR at {rate:.1f}% p.a. "
                    f"Precomputed DBR ratio = {dbr}. Verified monthly income "
                    f"{intake.verified_monthly_income_idr} IDR."
                ),
            )

        # ---- Stage 3: Compliance (deterministic OJK/BI policy gate) ----
        _emit("credit", "done",
              f"📊 **Credit Risk Scoring** selesai · Hasil: skor={assessment.credit_score}, "
              f"grade={assessment.risk_grade.value}, DBR={dbr}, angsuran≈{_rp(installment)}/bln, "
              f"mampu_bayar={assessment.affordable}.")
        _emit("compliance", "active",
              f"⚖️ **Compliance OJK/BI** aktif · Tool: Policy Rules MCP `evaluate_retail`. "
              f"Masukan: DBR={dbr}, skor={credit.get('credit_score', 0)}, "
              f"SLIK_kol={credit.get('slik_kol', 1)}, sanksi_DTTOT={bool(kyc.get('dttot_sanctions_hit', False))}.")
        pol = evaluate_retail(
            age=age,
            monthly_income_idr=cust["monthly_income_idr"],
            dbr_ratio=dbr,
            credit_score=credit.get("credit_score", 0),
            slik_kol=credit.get("slik_kol", 1),
            sanctions_hit=bool(kyc.get("dttot_sanctions_hit", False)),
            requested_amount_idr=application.requested_amount_idr,
        )
        compliance = ComplianceResult(
            decision=Decision(pol["decision"]),
            triggered_rules=pol["triggered_rules"],
            sanctions_hit=bool(kyc.get("dttot_sanctions_hit", False)),
            reason=pol["reason"],
        )
        audit.record(request_id, "retail", "compliance", "policy-engine (OJK/BI)",
                     f"DBR={dbr} score={credit.get('credit_score')} kol={credit.get('slik_kol')} "
                     f"rules={pol['triggered_rules']}", decision=pol["decision"])

        # ---- Stage 4: Decision & offer ----
        _emit("compliance", "done",
              f"⚖️ **Compliance OJK/BI** selesai · Keputusan: {pol['decision']} · "
              f"aturan_terpicu={pol['triggered_rules'] or 'tidak ada'} · {pol['reason']}")
        _emit("decision", "active",
              "✅ **Decision & Offer** aktif · menyusun keputusan akhir & penawaran (Pricing).")
        offer: LoanOffer | None = None
        if compliance.decision == Decision.APPROVE:
            offer = LoanOffer(
                product_code=PRODUCT_CODE,
                approved_amount_idr=application.requested_amount_idr,
                tenor_months=application.tenor_months,
                annual_rate_pct=round(rate, 2),
                monthly_installment_idr=installment,
                total_repayment_idr=installment * application.tenor_months,
            )

        explanation = await runner.run(
            step="decision", name="DecisionAgent", instructions=DECISION_AGENT,
            prompt=(
                f"Outcome: {compliance.decision.value}. Reason: {compliance.reason}. "
                f"Risk grade {assessment.risk_grade.value}, DBR {dbr}. "
                + (f"Offer: {offer.approved_amount_idr} IDR, {offer.annual_rate_pct}% p.a., "
                   f"installment {offer.monthly_installment_idr} IDR/month over {offer.tenor_months} months."
                   if offer else "No offer (declined or referred).")
            ),
        )

        decision = RetailDecision(
            application=application,
            decision=compliance.decision,
            offer=offer,
            explanation=explanation,
            routed_to_human=(compliance.decision == Decision.REFER),
        )
        audit.record(request_id, "retail", "final", "DecisionAgent",
                     redact_pii(explanation[:400]), decision=compliance.decision.value,
                     tokens=cost.total_tokens)
        _emit("decision", "done",
              f"✅ **Decision & Offer** selesai · Keputusan: {decision.decision.value}."
              + (f" Penawaran: plafon={_rp(offer.approved_amount_idr)}, bunga={offer.annual_rate_pct}% p.a., "
                 f"angsuran={_rp(offer.monthly_installment_idr)}/bln." if offer else " (tanpa penawaran)."))

    tech_log.save(request_id, runner.tech)
    return decision, cost.summary()
