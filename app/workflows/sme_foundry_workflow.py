"""Use Case 2 (v2) — SME underwriting orchestrated with **Foundry-hosted agents**.

Same orchestration + governance as v1 ``run_sme_analysis`` (concurrent specialists +
deterministic OJK/BI pre-screen + token/cost/audit tracking), but every reasoning step
calls a persistent Foundry prompt agent by reference instead of an inline Agent. The
surrounding systems (REST + MCP) are still used — the agents call them server-side.

Additive: this file does not change v1. It returns a plain dict the v2 page renders.
"""
from __future__ import annotations

import asyncio

from app.agents.shared.foundry_runner import foundry_session
from app.core.models import SMEFinancingRequest
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance.rules_engine import dscr as calc_dscr
from app.governance.rules_engine import loan_to_value, monthly_installment, sme_ratios
from app.workflows import data_access as sor
from mock_services.data import load
from mock_services.policy import evaluate_sme


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


async def run_sme_foundry(
    request: SMEFinancingRequest, request_id: str, on_event=None
) -> tuple[dict, dict]:
    """Concurrent SME analysis using Foundry-hosted agents. Returns (result, cost_summary)."""
    audit = get_audit_logger()

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "sme", "submitted", "portal",
                 redact_pii(f"{request.legal_name} ({request.company_id}) mengajukan "
                            f"{request.requested_amount_idr:,} IDR — {request.purpose}"))

    safety = check_text(request.purpose)
    audit.record(request_id, "sme", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    # ---- System-of-record facts + deterministic metrics (identical to v1) ----
    company = sor.company(request.company_id)
    credit = sor.credit_company(request.company_id)
    kyc = sor.kyc_company(request.company_id)
    statements = load("financials.json")[request.company_id]
    collateral_id = request.collateral_id or company.get("collateral_id")
    collateral = load("collateral.json").get(collateral_id, {})

    ratios = sme_ratios(statements)
    grade = credit.get("risk_grade", "C")
    products = load("products.json")
    rate = round(products["base_rate_pct"] + products["risk_spread_by_grade"].get(grade, 4.5), 2)
    installment = monthly_installment(request.requested_amount_idr, rate, request.tenor_months)
    dscr_val = calc_dscr(ratios.get("operating_cashflow_idr", 0), installment * 12)
    ltv = loan_to_value(request.requested_amount_idr, collateral.get("appraised_value_idr", 0))
    dte = ratios.get("debt_to_equity", 9.9)
    years_operating = max(0, __import__("datetime").date.today().year - company.get("established_year", 2020))

    pol = evaluate_sme(
        years_operating=years_operating, ltv_ratio=ltv, dscr=dscr_val,
        debt_to_equity=dte, credit_score=credit.get("credit_score", 0),
        sanctions_hit=bool(kyc.get("dttot_sanctions_hit", False)),
        ppatk_flag=bool(kyc.get("ppatk_flag", False)),
    )

    with foundry_session(request_id, "sme") as (runner, cost):
        _emit("orchestrator", "active",
              f"🧭 **Orchestrator (Foundry)** menyebar tugas ke 4 agen spesialis Foundry (PARALEL). "
              f"company_id={request.company_id}, plafon={_rp(request.requested_amount_idr)}.")
        for node, label in [("financial", "Analis Keuangan"), ("collateral", "Penilai Agunan"),
                            ("aml", "AML/Fraud"), ("market", "Risiko Pasar")]:
            _emit(node, "active", f"⚙️ **{label}** (agen di Foundry) mulai bekerja…")

        def _call(step, name, agent_key, prompt):
            return asyncio.to_thread(
                runner.run, step=step, name=name, agent_key=agent_key, prompt=prompt
            )

        financial, collateral_txt, aml_txt, market = await asyncio.gather(
            _call("specialist:financial", "FinancialAnalyst", "sme-financial-analyst",
                  f"company_id={request.company_id}. Precomputed ratios: {ratios}."),
            _call("specialist:collateral", "CollateralAgent", "sme-collateral-agent",
                  f"collateral_id={collateral_id}. Requested facility {request.requested_amount_idr} IDR. "
                  f"Precomputed LTV={ltv}."),
            _call("specialist:aml", "AmlFraudAgent", "sme-aml-fraud-agent",
                  f"company_id={request.company_id}."),
            _call("specialist:market", "MarketRiskAgent", "sme-market-risk-agent",
                  f"Sector={company.get('sector')}, established {company.get('established_year')}, "
                  f"annual revenue {company.get('annual_revenue_idr')} IDR, facility "
                  f"{request.requested_amount_idr} IDR for: {request.purpose}."),
        )
        findings = {
            "financial_analyst": financial,
            "collateral": collateral_txt,
            "aml_fraud": aml_txt,
            "market_risk": market,
        }
        for node, label, key in [("financial", "📊 Analis Keuangan", "financial_analyst"),
                                 ("collateral", "🏠 Penilai Agunan", "collateral"),
                                 ("aml", "🛡️ AML/Fraud", "aml_fraud"),
                                 ("market", "🌐 Risiko Pasar", "market_risk")]:
            _emit(node, "done", f"{label} selesai · {findings[key][:140]}")

        audit.record(request_id, "sme", "prescreen", "policy-engine (OJK/BI)",
                     f"LTV={ltv} DSCR={dscr_val} DER={dte} rules={pol['triggered_rules']}",
                     decision=pol["decision"])

        _emit("aggregate", "active",
              f"🧮 **Underwriting Orchestrator (Foundry)** menggabungkan 4 temuan. "
              f"LTV={ltv}, DSCR={dscr_val}, DER={dte}. Pra-skrining: {pol['decision']}.")
        recommendation = await asyncio.to_thread(
            runner.run,
            step="aggregate", name="UnderwritingOrchestrator",
            agent_key="sme-underwriting-orchestrator",
            prompt=(
                f"company_id={request.company_id}, requested {request.requested_amount_idr} IDR, "
                f"tenor {request.tenor_months} months, indicative rate {rate}% p.a. "
                f"Metrics: LTV={ltv}, DSCR={dscr_val}, debt_to_equity={dte}, "
                f"credit_score={credit.get('credit_score')}. Deterministic pre-screen: {pol['decision']} "
                f"({pol['reason']}). Specialist findings: "
                f"Financial: {financial} | Collateral: {collateral_txt} | "
                f"AML: {aml_txt} | Market: {market}"
            ),
        )
        audit.record(request_id, "sme", "final", "foundry:sme-underwriting-orchestrator",
                     redact_pii(recommendation[:400]), decision=pol["decision"],
                     tokens=cost.total_tokens)
        _emit("aggregate", "done",
              f"🧮 **Underwriting** selesai · keputusan (deterministik): {pol['decision']}.")
        _emit("orchestrator", "done", "🧭 **Orchestrator (Foundry)** selesai.")

    tech_log.save(request_id, runner.tech)

    result = {
        "company_id": request.company_id,
        "legal_name": request.legal_name,
        "decision": pol["decision"],
        "reason": pol["reason"],
        "triggered_rules": pol["triggered_rules"],
        "metrics": {"ltv": ltv, "dscr": dscr_val, "debt_to_equity": dte,
                    "credit_score": credit.get("credit_score", 0), "rate_pct": rate,
                    "installment_idr": installment},
        "findings": findings,
        "recommendation": recommendation,
    }
    return result, cost.summary()
