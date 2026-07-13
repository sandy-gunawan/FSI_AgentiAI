"""One-shot APIM route probe for v1 and v2 (retail). Validates the gateway path end to end.

Usage: python -m scripts.apim_probe [v1|v2|both]
Reads APIM_* from the environment (set by the caller). Prints token totals or the
real gateway error so we can validate the APIM path.
"""
import asyncio
import sys
import uuid

from app.workflows import data_access as sor
from app.core.models import RetailLoanApplication, EmploymentType
from app.workflows.retail_workflow import run_retail
from app.workflows.retail_foundry_workflow import run_retail_foundry


def _app(cust):
    return RetailLoanApplication(
        customer_id=cust["customer_id"], full_name=cust["full_name"], nik=cust["nik"],
        dob=cust["dob"], employment_type=EmploymentType(cust["employment_type"]),
        monthly_income_idr=cust["monthly_income_idr"], requested_amount_idr=50_000_000,
        tenor_months=24, purpose="probe apim",
    )


async def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    cust = sor.list_customers()[0]
    if which in ("v1", "both"):
        result, cost = await run_retail(_app(cust), f"APIMv1-{uuid.uuid4().hex[:6]}", via_apim=True)
        print(f"[v1 APIM] OK tokens={cost['total_tokens']} decision={getattr(result, 'decision', '?')}")
    if which in ("v2", "both"):
        result, cost = await run_retail_foundry(_app(cust), f"APIMv2-{uuid.uuid4().hex[:6]}", via_apim=True)
        print(f"[v2 APIM] OK tokens={cost['total_tokens']} keys={list(result)[:4]}")


if __name__ == "__main__":
    asyncio.run(main())
