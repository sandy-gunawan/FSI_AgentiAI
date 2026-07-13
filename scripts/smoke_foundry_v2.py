"""Temporary smoke test — run each v2 (Foundry) workflow once and print decision + tokens.

Requires Azure auth (az login / DefaultAzureCredential) and the systems Container App up.
Run: python scripts/smoke_foundry_v2.py
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
    ServiceRequest,
    SyndicationRequest,
)
from app.workflows import data_access as sor
from app.workflows.aml_foundry_workflow import run_aml_foundry
from app.workflows.committee_foundry_workflow import run_committee_foundry
from app.workflows.magentic_foundry_workflow import run_magentic_foundry
from app.workflows.restructure_foundry_workflow import run_restructure_foundry
from app.workflows.retail_foundry_workflow import run_retail_foundry
from app.workflows.servicing_foundry_workflow import run_servicing_foundry
from app.workflows.syndication_foundry_workflow import run_syndication_foundry


async def main() -> None:
    cust = sor.list_customers()[0]
    co = sor.list_companies()[0]

    async def _try(name, coro):
        try:
            out = await coro
            res, cost = out[0], out[1]
            dec = res.get("decision") or res.get("risk_level") or res.get("intent") or res.get("file_sar")
            print(f"✅ {name:14s} decision={dec} tokens={cost['total_tokens']} "
                  f"cost=${cost['estimated_cost_usd']:.4f}")
        except Exception as exc:
            print(f"❌ {name:14s} FAILED: {exc}")
            traceback.print_exc()

    await _try("retail", run_retail_foundry(RetailLoanApplication(
        customer_id=cust["customer_id"], full_name=cust["full_name"], nik=cust["nik"], dob=cust["dob"],
        employment_type=EmploymentType(cust["employment_type"]),
        monthly_income_idr=cust["monthly_income_idr"], requested_amount_idr=50_000_000,
        tenor_months=24, purpose="renovasi rumah"), f"RETF-{uuid.uuid4().hex[:6]}"))

    await _try("servicing", run_servicing_foundry(ServiceRequest(
        customer_id=cust["customer_id"], full_name=cust["full_name"], channel="chat",
        message="Saya ingin menaikkan limit kartu kredit saya."), f"SVCF-{uuid.uuid4().hex[:6]}"))

    await _try("restructure", run_restructure_foundry(RestructureRequest(
        customer_id=cust["customer_id"], full_name=cust["full_name"],
        hardship_reason="Pendapatan usaha menurun drastis.", requested_relief="perpanjang tenor"),
        f"RSTF-{uuid.uuid4().hex[:6]}"))

    await _try("aml", run_aml_foundry(AmlInvestigationRequest(
        subject_id=cust["customer_id"], subject_name=cust["full_name"],
        alert_type="structuring", alert_detail="Beberapa setoran tunai di bawah ambang."),
        f"AMLF-{uuid.uuid4().hex[:6]}"))

    await _try("committee", run_committee_foundry(CommitteeRequest(
        company_id=co["company_id"], legal_name=co["legal_name"],
        requested_amount_idr=3_000_000_000, tenor_months=48, purpose="ekspansi pabrik"),
        f"CMTF-{uuid.uuid4().hex[:6]}"))

    await _try("magentic", run_magentic_foundry(MagenticRequest(
        subject_id=cust["customer_id"], subject_name=cust["full_name"],
        objective="Nilai profil risiko menyeluruh & indikasi pencucian uang."),
        f"MAGF-{uuid.uuid4().hex[:6]}"))

    await _try("syndication", run_syndication_foundry(SyndicationRequest(
        company_id=co["company_id"], legal_name=co["legal_name"], sector=co["sector"],
        requested_amount_idr=12_000_000_000, tenor_months=48, purpose="ekspansi kapasitas"),
        f"SYNF-{uuid.uuid4().hex[:6]}"))


if __name__ == "__main__":
    asyncio.run(main())
