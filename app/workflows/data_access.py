"""Deterministic 'system of record' reads for the orchestrator.

The loan-origination orchestrator reads authoritative facts (customer, credit
bureau, KYC) directly so that the deterministic compliance gate and edge cases
are reproducible, while agents independently gather/reason over the same
back-office systems via their tools.
"""
from __future__ import annotations

from datetime import date

from mock_services.data import load


def customer(customer_id: str) -> dict:
    for c in load("customers.json"):
        if c["customer_id"] == customer_id:
            return c
    raise KeyError(f"customer {customer_id} not found")


def company(company_id: str) -> dict:
    for c in load("companies.json"):
        if c["company_id"] == company_id:
            return c
    raise KeyError(f"company {company_id} not found")


def credit_individual(customer_id: str) -> dict:
    return load("credit_bureau.json")["individuals"].get(customer_id, {})


def credit_company(company_id: str) -> dict:
    return load("credit_bureau.json")["companies"].get(company_id, {})


def kyc_individual(nik: str) -> dict:
    return load("kyc.json")["individuals"].get(nik, {})


def kyc_company(company_id: str) -> dict:
    return load("kyc.json")["companies"].get(company_id, {})


def existing_loan(customer_id: str) -> dict:
    """Existing/outstanding retail facility for a customer (restructuring)."""
    return load("existing_loans.json").get(customer_id, {})


def monitoring_alerts(customer_id: str) -> dict:
    """Transaction-monitoring AML alerts for a customer (investigation)."""
    return load("alerts.json").get(customer_id, {})


def transactions(customer_id: str) -> list[dict]:
    """Raw 6-month transaction history for a customer."""
    return load("transactions.json").get(customer_id, [])


def age_from_dob(dob: str) -> int:
    y, m, d = (int(x) for x in dob.split("-"))
    today = date.today()
    return today.year - y - ((today.month, today.day) < (m, d))


def list_customers() -> list[dict]:
    return load("customers.json")


def list_companies() -> list[dict]:
    return load("companies.json")
