"""Function tools that call the mock REST back-office (core banking, collateral,
financials, pricing). Agents invoke these directly as tools.
"""
from __future__ import annotations

from typing import Annotated

import httpx
from pydantic import Field

from agent_framework import tool

from app.core.config import get_settings

_TIMEOUT = 15.0


def _base() -> str:
    return get_settings().rest_base_url.rstrip("/")


@tool(approval_mode="never_require")
async def get_account_summary(
    customer_id: Annotated[str, Field(description="Customer id, e.g. CUST-1001")],
) -> dict:
    """Get core-banking accounts and 6-month cashflow summary for a customer."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        acc = await c.get(f"{_base()}/core-banking/customers/{customer_id}/accounts")
        txn = await c.get(f"{_base()}/core-banking/customers/{customer_id}/transactions", params={"months": 6})
    acc.raise_for_status()
    txn.raise_for_status()
    t = txn.json()
    return {
        "accounts": acc.json()["accounts"],
        "avg_monthly_credit_idr": t["avg_monthly_credit_idr"],
        "avg_monthly_debit_idr": t["avg_monthly_debit_idr"],
    }


@tool(approval_mode="never_require")
async def get_collateral(
    collateral_id: Annotated[str, Field(description="Collateral id, e.g. COL-9001")],
) -> dict:
    """Get a collateral appraisal (declared vs appraised value, type, condition)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{_base()}/collateral/{collateral_id}")
    r.raise_for_status()
    return r.json()


@tool(approval_mode="never_require")
async def get_financial_statements(
    company_id: Annotated[str, Field(description="Company id, e.g. SME-5001")],
) -> dict:
    """Get up to 3 years of SME financial statements."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{_base()}/financials/companies/{company_id}", params={"years": 3})
    r.raise_for_status()
    return r.json()


@tool(approval_mode="never_require")
async def get_transactions(
    customer_id: Annotated[str, Field(description="Customer id, e.g. CUST-1001")],
    months: Annotated[int, Field(description="Months of history, 1-6")] = 6,
) -> dict:
    """Get raw core-banking transaction history (6 months) for a customer."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{_base()}/core-banking/customers/{customer_id}/transactions",
                        params={"months": max(1, min(6, months))})
    r.raise_for_status()
    return r.json()


@tool(approval_mode="never_require")
async def get_existing_loans(
    customer_id: Annotated[str, Field(description="Customer id, e.g. CUST-1001")],
) -> dict:
    """Get the customer's existing/outstanding loan facility and arrears status."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{_base()}/servicing/loans/{customer_id}")
    r.raise_for_status()
    return r.json()


@tool(approval_mode="never_require")
async def get_monitoring_alerts(
    customer_id: Annotated[str, Field(description="Customer id, e.g. CUST-1001")],
) -> dict:
    """Get transaction-monitoring AML alerts (typologies, severity) for a customer."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{_base()}/monitoring/alerts/{customer_id}")
    r.raise_for_status()
    return r.json()


@tool(approval_mode="never_require")
async def get_price_quote(
    amount_idr: Annotated[int, Field(description="Loan principal in IDR")],
    tenor_months: Annotated[int, Field(description="Tenor in months")],
    risk_grade: Annotated[str, Field(description="Risk grade A/B/C/D")],
    product_code: Annotated[str, Field(description="Product code, e.g. KTA-STD, SME-TERM")],
) -> dict:
    """Get a pricing quote (rate, installment, total repayment) for a facility."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(
            f"{_base()}/pricing/quote",
            params={
                "amount_idr": amount_idr,
                "tenor_months": tenor_months,
                "risk_grade": risk_grade,
                "product_code": product_code,
            },
        )
    r.raise_for_status()
    return r.json()
