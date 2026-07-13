"""Smoke test — run each v1 (in-code agents) workflow once, DIRECT path (no APIM).

Verifies the gateway plumbing didn't break the direct route. Requires Azure auth
(az login) and the deployed systems Container App.
Run: $env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"; python -m scripts.smoke_v1
"""
from __future__ import annotations

import asyncio
import traceback
import uuid

from app.core.models import (
    AmlInvestigationRequest,
    CommitteeRequest,
    EmploymentType,
    MagenticRequest,
    RestructureRequest,
    RetailLoanApplication,
    SMEFinancingRequest,
    ServiceRequest,
    SyndicationRequest,
)
from app.workflows import data_access as sor
from app.workflows.aml_workflow import run_aml_investigation
from app.workflows.committee_workflow import run_committee
from app.workflows.magentic_workflow import run_magentic
from app.workflows.restructure_workflow import run_restructure
from app.workflows.retail_workflow import run_retail
from app.workflows.servicing_workflow import run_servicing
from app.workflows.sme_workflow import run_sme_analysis
from app.workflows.a2a_workflow import run_syndication


def _tok(cost: dict) -> str:
    return f"tokens={cost['total_tokens']} cost=${cost['estimated_cost_usd']:.4f}"


async def _try(name, coro, pick_cost):
    try:
        out = await coro
        cost = pick_cost(out)
        print(f"OK  {name:14s} {_tok(cost)}")
    except Exception as exc:
        print(f"XX  {name:14s} FAILED: {exc}")
        traceback.print_exc()


async def main() -> None:
    cust = sor.list_customers()[0]
    co = sor.list_companies()[0]

    await _try("retail", run_retail(RetailLoanApplication(
        customer_id=cust["customer_id"], full_name=cust["full_name"], nik=cust["nik"], dob=cust["dob"],
        employment_type=EmploymentType(cust["employment_type"]),
        monthly_income_idr=cust["monthly_income_idr"], requested_amount_idr=50_000_000,
        tenor_months=24, purpose="renovasi rumah"), f"RET-{uuid.uuid4().hex[:6]}"),
        lambda o: o[1])

    await _try("sme", run_sme_analysis(SMEFinancingRequest(
        company_id=co["company_id"], legal_name=co["legal_name"], npwp=co["npwp"], sector=co["sector"],
        requested_amount_idr=2_000_000_000, tenor_months=36, purpose="ekspansi",
        collateral_id=co.get("collateral_id"), relationship_manager="Budi"),
        f"SME-{uuid.uuid4().hex[:6]}"), lambda o: o[1])

    await _try("servicing", run_servicing(ServiceRequest(
        customer_id=cust["customer_id"], full_name=cust["full_name"], channel="chat",
        message="Saya ingin menaikkan limit kartu kredit saya."), f"SVC-{uuid.uuid4().hex[:6]}"),
        lambda o: o[2])

    await _try("restructure", run_restructure(RestructureRequest(
        customer_id=cust["customer_id"], full_name=cust["full_name"],
        hardship_reason="Pendapatan usaha menurun drastis.", requested_relief="perpanjang tenor"),
        f"RST-{uuid.uuid4().hex[:6]}"), lambda o: o[1])

    await _try("aml", run_aml_investigation(AmlInvestigationRequest(
        subject_id=cust["customer_id"], subject_name=cust["full_name"],
        alert_type="structuring", alert_detail="Beberapa setoran tunai di bawah ambang."),
        f"AML-{uuid.uuid4().hex[:6]}"), lambda o: o[1])

    await _try("committee", run_committee(CommitteeRequest(
        company_id=co["company_id"], legal_name=co["legal_name"],
        requested_amount_idr=3_000_000_000, tenor_months=48, purpose="ekspansi pabrik"),
        f"CMT-{uuid.uuid4().hex[:6]}"), lambda o: o[1])

    await _try("magentic", run_magentic(MagenticRequest(
        subject_id=cust["customer_id"], subject_name=cust["full_name"],
        objective="Nilai profil risiko menyeluruh & indikasi pencucian uang."),
        f"MAG-{uuid.uuid4().hex[:6]}"), lambda o: o[1])

    await _try("syndication", run_syndication(SyndicationRequest(
        company_id=co["company_id"], legal_name=co["legal_name"], sector=co["sector"],
        requested_amount_idr=12_000_000_000, tenor_months=48, purpose="ekspansi kapasitas"),
        f"SYN-{uuid.uuid4().hex[:6]}"), lambda o: o[1])


if __name__ == "__main__":
    asyncio.run(main())
