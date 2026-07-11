"""Deterministic financial calculators used by agents as function tools.

Keeping the math in plain, tested Python (not the LLM) makes decisions
reproducible and auditable — a core governance requirement.
"""
from __future__ import annotations


def monthly_installment(principal_idr: int, annual_rate_pct: float, tenor_months: int) -> int:
    """Amortising monthly installment (anuitas)."""
    r = annual_rate_pct / 100 / 12
    n = max(1, tenor_months)
    if r <= 0:
        return int(principal_idr / n)
    inst = principal_idr * r * (1 + r) ** n / ((1 + r) ** n - 1)
    return int(round(inst))


def debt_burden_ratio(
    monthly_income_idr: int,
    existing_monthly_debt_idr: int,
    new_installment_idr: int,
) -> float:
    """DBR / DTI = (existing debt + new installment) / income."""
    if monthly_income_idr <= 0:
        return 1.0
    return round((existing_monthly_debt_idr + new_installment_idr) / monthly_income_idr, 4)


def loan_to_value(loan_amount_idr: int, collateral_value_idr: int) -> float:
    """LTV = loan / appraised collateral value."""
    if collateral_value_idr <= 0:
        return 99.0
    return round(loan_amount_idr / collateral_value_idr, 4)


def dscr(operating_cashflow_idr: int, annual_debt_service_idr: int) -> float:
    """Debt Service Coverage Ratio = operating cashflow / annual debt service."""
    if annual_debt_service_idr <= 0:
        return 99.0
    return round(operating_cashflow_idr / annual_debt_service_idr, 4)


def sme_ratios(statements: list[dict]) -> dict:
    """Derive key ratios from the latest year of SME financial statements."""
    if not statements:
        return {}
    latest = statements[-1]
    equity = max(1, latest["equity_idr"])
    curr_liab = max(1, latest["current_liabilities_idr"])
    revenue = max(1, latest["revenue_idr"])
    ratios = {
        "current_ratio": round(latest["current_assets_idr"] / curr_liab, 2),
        "debt_to_equity": round(latest["total_liabilities_idr"] / equity, 2),
        "net_margin": round(latest["net_income_idr"] / revenue, 4),
        "operating_cashflow_idr": latest["operating_cashflow_idr"],
    }
    if len(statements) >= 2:
        first_rev = max(1, statements[0]["revenue_idr"])
        years = len(statements) - 1
        ratios["revenue_cagr"] = round((revenue / first_rev) ** (1 / years) - 1, 4)
    return ratios
