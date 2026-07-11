"""Combined mock REST service for BNS surrounding systems (Bank Nusantara Sejahtera).

Serves four logical back-office systems on a single port (8080):
  /core-banking   account & transaction history
  /collateral     collateral appraisals
  /financials     SME financial statements
  /pricing        loan product catalog & pricing quotes
  /servicing      existing/outstanding loan facilities (restructuring)
  /monitoring     transaction-monitoring AML alerts (investigation)

Run:  uvicorn mock_services.rest_apis.app:app --port 8080
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from mock_services.data import load

app = FastAPI(title="BNS Mock Back-Office REST Services", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "bns-mock-rest"}


# --------------------------------------------------------------------------- #
# Core Banking
# --------------------------------------------------------------------------- #
@app.get("/core-banking/customers/{customer_id}/accounts")
def get_accounts(customer_id: str) -> dict:
    accounts = load("accounts.json")
    if customer_id not in accounts:
        raise HTTPException(404, f"customer {customer_id} not found")
    return {"customer_id": customer_id, "accounts": accounts[customer_id]}


@app.get("/core-banking/customers/{customer_id}/transactions")
def get_transactions(customer_id: str, months: int = Query(6, ge=1, le=6)) -> dict:
    txns = load("transactions.json")
    if customer_id not in txns:
        raise HTTPException(404, f"customer {customer_id} not found")
    rows = txns[customer_id]
    credits = sum(t["amount_idr"] for t in rows if t["direction"] == "credit")
    debits = sum(t["amount_idr"] for t in rows if t["direction"] == "debit")
    return {
        "customer_id": customer_id,
        "months": months,
        "avg_monthly_credit_idr": credits // months,
        "avg_monthly_debit_idr": debits // months,
        "transactions": rows,
    }


# --------------------------------------------------------------------------- #
# Collateral
# --------------------------------------------------------------------------- #
@app.get("/collateral/{collateral_id}")
def get_collateral(collateral_id: str) -> dict:
    collateral = load("collateral.json")
    if collateral_id not in collateral:
        raise HTTPException(404, f"collateral {collateral_id} not found")
    return collateral[collateral_id]


# --------------------------------------------------------------------------- #
# Financials (SME)
# --------------------------------------------------------------------------- #
@app.get("/financials/companies/{company_id}")
def get_financials(company_id: str, years: int = Query(3, ge=1, le=3)) -> dict:
    financials = load("financials.json")
    if company_id not in financials:
        raise HTTPException(404, f"company {company_id} not found")
    return {"company_id": company_id, "statements": financials[company_id][-years:]}


# --------------------------------------------------------------------------- #
# Loan Servicing (existing/outstanding facilities)
# --------------------------------------------------------------------------- #
@app.get("/servicing/loans/{customer_id}")
def get_existing_loan(customer_id: str) -> dict:
    loans = load("existing_loans.json")
    if customer_id not in loans:
        raise HTTPException(404, f"no existing loan for {customer_id}")
    return loans[customer_id]


# --------------------------------------------------------------------------- #
# Transaction Monitoring (AML alerts)
# --------------------------------------------------------------------------- #
@app.get("/monitoring/alerts/{customer_id}")
def get_alerts(customer_id: str) -> dict:
    alerts = load("alerts.json")
    if customer_id not in alerts:
        raise HTTPException(404, f"customer {customer_id} not found")
    return alerts[customer_id]


# --------------------------------------------------------------------------- #
# Pricing
# --------------------------------------------------------------------------- #
@app.get("/pricing/products")
def get_products() -> dict:
    return load("products.json")


@app.post("/pricing/quote")
def quote(amount_idr: int, tenor_months: int, risk_grade: str, product_code: str) -> dict:
    products = load("products.json")
    catalog = {p["product_code"]: p for p in products["products"]}
    if product_code not in catalog:
        raise HTTPException(404, f"product {product_code} not found")
    spread = products["risk_spread_by_grade"].get(risk_grade.upper(), 5.0)
    annual_rate = round(products["base_rate_pct"] + spread, 2)
    monthly_rate = annual_rate / 100 / 12
    n = tenor_months
    if monthly_rate > 0:
        installment = amount_idr * monthly_rate * (1 + monthly_rate) ** n / ((1 + monthly_rate) ** n - 1)
    else:
        installment = amount_idr / n
    installment = int(installment)
    return {
        "product_code": product_code,
        "amount_idr": amount_idr,
        "tenor_months": tenor_months,
        "annual_rate_pct": annual_rate,
        "monthly_installment_idr": installment,
        "total_repayment_idr": installment * n,
    }
