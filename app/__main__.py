"""Self-check entrypoint: `python -m app`.

Runs one real retail financing request end-to-end so a deployed container can be
verified in place — exercises module imports, DefaultAzureCredential → Foundry,
the cloud-hosted REST + MCP systems, governance and audit.
"""
from __future__ import annotations

import asyncio
import uuid

from app.core.models import EmploymentType, RetailLoanApplication
from app.workflows import data_access as sor
from app.workflows.retail_workflow import run_retail


async def _main() -> None:
    c = sor.customer("CUST-1001")
    application = RetailLoanApplication(
        customer_id="CUST-1001", full_name=c["full_name"], nik=c["nik"], dob=c["dob"],
        employment_type=EmploymentType(c["employment_type"]),
        monthly_income_idr=c["monthly_income_idr"], requested_amount_idr=50_000_000,
        tenor_months=24, purpose="renovasi rumah",
    )
    decision, cost = await run_retail(application, f"SELFCHECK-{uuid.uuid4().hex[:6]}")
    print(f"SELFCHECK_OK decision={decision.decision.value} tokens={cost['total_tokens']}")


if __name__ == "__main__":
    asyncio.run(_main())
