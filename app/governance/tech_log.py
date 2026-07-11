"""Technical call log — captures the real MCP/REST tool calls made by agents.

Populated by the function-middleware in the agent runner (actual tool name,
arguments, returned data, latency). Stored per request so the portal can show
concrete proof that agents really call the cloud-hosted MCP servers and REST
APIs (with the exact endpoint URLs).
"""
from __future__ import annotations

_STORE: dict[str, list[dict]] = {}

# tool name -> (protocol, path under REST_BASE_URL, human label)
_ENDPOINT = {
    "get_account_summary": ("REST GET", "/core-banking/customers/{id}/...", "Core Banking API"),
    "get_transactions": ("REST GET", "/core-banking/customers/{id}/transactions", "Core Banking API"),
    "get_collateral": ("REST GET", "/collateral/{id}", "Collateral API"),
    "get_financial_statements": ("REST GET", "/financials/companies/{id}", "Financials API"),
    "get_existing_loans": ("REST GET", "/servicing/loans/{id}", "Loan Servicing API"),
    "get_monitoring_alerts": ("REST GET", "/monitoring/alerts/{id}", "Transaction Monitoring API"),
    "get_price_quote": ("REST POST", "/pricing/quote", "Pricing API"),
    "get_credit_report": ("MCP", "/mcp/credit-bureau/", "Credit Bureau MCP (SLIK)"),
    "get_company_credit": ("MCP", "/mcp/credit-bureau/", "Credit Bureau MCP (SLIK)"),
    "screen_individual": ("MCP", "/mcp/kyc-aml/", "KYC/AML MCP"),
    "screen_entity": ("MCP", "/mcp/kyc-aml/", "KYC/AML MCP"),
    "evaluate_retail": ("MCP", "/mcp/policy-rules/", "Policy Rules MCP"),
    "evaluate_sme": ("MCP", "/mcp/policy-rules/", "Policy Rules MCP"),
    "list_rules": ("MCP", "/mcp/policy-rules/", "Policy Rules MCP"),
    "a2a:discover": ("A2A", "/.well-known/agent-card.json", "Partner Bank (BMS) — Agent Card"),
    "a2a:message/send": ("A2A JSON-RPC", "/a2a", "Partner Bank (BMS) — co-underwrite"),
}


def save(request_id: str, entries: list[dict]) -> None:
    _STORE[request_id] = list(entries)


def get(request_id: str) -> list[dict]:
    return _STORE.get(request_id, [])


def endpoint_for(tool: str) -> tuple[str, str, str]:
    return _ENDPOINT.get(tool, ("TOOL", "-", tool))
