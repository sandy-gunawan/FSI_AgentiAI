"""Use Case 1 (v2) — Retail personal loan with **Foundry-hosted agents**.

Same SEQUENTIAL pipeline + governance as v1 ``run_retail`` (Intake → Credit Risk →
Compliance gate → Decision), but each reasoning step calls a persistent Foundry prompt
agent by reference. Deterministic/OJK-BI logic stays in Python for auditability; the
Foundry agents produce the narrative. Additive — v1 is untouched. Returns a plain dict.
"""
from __future__ import annotations

import asyncio

from app.agents.shared.foundry_runner import foundry_session
from app.core.models import RetailLoanApplication
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance.rules_engine import debt_burden_ratio, monthly_installment
from app.workflows import data_access as sor
from mock_services.data import load
from mock_services.policy import evaluate_retail

PRODUCT_CODE = "KTA-STD"


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


async def run_retail_foundry(
    application: RetailLoanApplication, request_id: str, on_event=None,
    via_apim: bool | None = None,
) -> tuple[dict, dict]:
    """Sequential retail assessment using Foundry-hosted agents. Returns (result, cost)."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "retail", "submitted", "portal",
                 redact_pii(f"{application.full_name} mengajukan {application.requested_amount_idr:,} IDR "
                            f"tenor {application.tenor_months} bln — {application.purpose}"))
    safety = check_text(application.purpose)
    audit.record(request_id, "retail", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    # ---- System-of-record facts + deterministic metrics (identical to v1) ----
    cust = sor.customer(application.customer_id)
    credit = sor.credit_individual(application.customer_id)
    kyc = sor.kyc_individual(cust["nik"])
    age = sor.age_from_dob(cust["dob"])
    products = load("products.json")
    grade = credit.get("risk_grade", "D")
    rate = round(products["base_rate_pct"] + products["risk_spread_by_grade"].get(grade, 7.0), 2)
    installment = monthly_installment(application.requested_amount_idr, rate, application.tenor_months)
    dbr = debt_burden_ratio(cust["monthly_income_idr"],
                            credit.get("monthly_debt_obligations_idr", 0), installment)
    sanctioned = bool(kyc.get("dttot_sanctions_hit", False))
    identity_verified = not sanctioned
    kyc_risk = kyc.get("risk_rating", "high" if sanctioned else "low")

    pol = evaluate_retail(
        age=age, monthly_income_idr=cust["monthly_income_idr"], dbr_ratio=dbr,
        credit_score=credit.get("credit_score", 0), slik_kol=credit.get("slik_kol", 1),
        sanctions_hit=sanctioned, requested_amount_idr=application.requested_amount_idr,
    )
    decision = pol["decision"]

    with foundry_session(request_id, "retail", via_apim) as (runner, cost):
        def _call(step, name, agent_key, prompt):
            return asyncio.to_thread(runner.run, step=step, name=name, agent_key=agent_key, prompt=prompt)

        # ---- Stage 1: Intake & verification (Foundry) ----
        _emit("intake", "active",
              f"🧾 **Intake & Verifikasi** (agen Foundry) · customer_id={application.customer_id}, "
              f"penghasilan diklaim {_rp(application.monthly_income_idr)}/bln.")
        intake = await _call("intake", "IntakeAgent", "retail-intake",
                             f"customer_id={application.customer_id}, name={application.full_name}, "
                             f"NIK={cust['nik']}, employment={application.employment_type.value}, "
                             f"declared_monthly_income_idr={application.monthly_income_idr}. "
                             f"Deterministic checks: identity_verified={identity_verified}, "
                             f"kyc_risk={kyc_risk}, verified_income={cust['monthly_income_idr']}.")
        _emit("intake", "done",
              f"🧾 **Intake** selesai · identitas_terverifikasi={identity_verified}, risiko_KYC={kyc_risk}.")

        # ---- Stage 2: Credit risk scoring (Foundry) ----
        _emit("credit", "active",
              f"📊 **Credit Risk** (agen Foundry) · plafon {_rp(application.requested_amount_idr)}, "
              f"tenor {application.tenor_months} bln.")
        credit_text = await _call("credit_risk", "CreditRiskAgent", "retail-credit-risk",
                                  f"customer_id={application.customer_id}. Requested "
                                  f"{application.requested_amount_idr} IDR over {application.tenor_months} "
                                  f"months, installment ~{installment} IDR at {rate}% p.a. "
                                  f"Precomputed DBR={dbr}, credit_score={credit.get('credit_score')}, "
                                  f"grade={grade}, slik_kol={credit.get('slik_kol')}.")
        _emit("credit", "done",
              f"📊 **Credit Risk** selesai · skor={credit.get('credit_score')}, grade={grade}, "
              f"DBR={dbr}, angsuran≈{_rp(installment)}/bln.")

        # ---- Stage 3: Compliance (deterministic OJK/BI gate) ----
        _emit("compliance", "active",
              f"⚖️ **Compliance OJK/BI** (deterministik) · DBR={dbr}, skor={credit.get('credit_score')}, "
              f"SLIK_kol={credit.get('slik_kol', 1)}, sanksi_DTTOT={sanctioned}.")
        audit.record(request_id, "retail", "compliance", "policy-engine (OJK/BI)",
                     f"DBR={dbr} score={credit.get('credit_score')} kol={credit.get('slik_kol')} "
                     f"rules={pol['triggered_rules']}", decision=decision)
        _emit("compliance", "done",
              f"⚖️ **Compliance** selesai · Keputusan: {decision} · "
              f"aturan={pol['triggered_rules'] or 'tidak ada'} · {pol['reason']}")

        # ---- Stage 4: Decision & offer (Foundry) ----
        offer = None
        if decision == "APPROVE":
            offer = {
                "product_code": PRODUCT_CODE,
                "approved_amount_idr": application.requested_amount_idr,
                "tenor_months": application.tenor_months,
                "annual_rate_pct": rate,
                "monthly_installment_idr": installment,
                "total_repayment_idr": installment * application.tenor_months,
            }
        _emit("decision", "active", "✅ **Decision & Offer** (agen Foundry) menyusun keputusan akhir…")
        explanation = await _call("decision", "DecisionAgent", "retail-decision",
                                  f"Outcome: {decision}. Reason: {pol['reason']}. Grade {grade}, DBR {dbr}. "
                                  + (f"Offer: {application.requested_amount_idr} IDR, {rate}% p.a., "
                                     f"installment {installment} IDR/month over {application.tenor_months} "
                                     f"months." if offer else "No offer (declined or referred)."))
        audit.record(request_id, "retail", "final", "foundry:retail-decision",
                     redact_pii(explanation[:400]), decision=decision, tokens=cost.total_tokens)
        _emit("decision", "done",
              f"✅ **Decision & Offer** selesai · Keputusan: {decision}."
              + (f" Penawaran: plafon={_rp(offer['approved_amount_idr'])}, "
                 f"bunga={rate}% p.a., angsuran={_rp(installment)}/bln." if offer else " (tanpa penawaran)."))

    tech_log.save(request_id, runner.tech)
    result = {
        "decision": decision,
        "reason": pol["reason"],
        "triggered_rules": pol["triggered_rules"],
        "routed_to_human": decision == "REFER",
        "metrics": {"credit_score": credit.get("credit_score", 0), "risk_grade": grade,
                    "dbr": dbr, "rate_pct": rate, "installment_idr": installment},
        "offer": offer,
        "intake": intake,
        "credit_text": credit_text,
        "explanation": explanation,
    }
    return result, cost.summary()
