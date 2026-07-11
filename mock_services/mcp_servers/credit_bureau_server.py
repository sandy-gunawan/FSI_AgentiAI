"""Credit Bureau MCP server — SLIK OJK + Biro Kredit (Pefindo/CLIK).

Exposes credit reports for individuals and companies over the Model Context
Protocol (stdio). Launched by agents via MCPStdioTool.

Run standalone:  python -m mock_services.mcp_servers.credit_bureau_server
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mock_services.data import load

mcp = FastMCP(
    "credit-bureau", stateless_http=True, streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def get_credit_report(customer_id: str) -> dict:
    """Get the SLIK OJK + Biro Kredit report for an individual customer.

    Returns credit score (250-900), risk grade (A-D), SLIK collectibility
    (kol 1-5), outstanding debt and monthly obligations in IDR, active
    facilities, delinquencies and recent enquiries.
    """
    data = load("credit_bureau.json")["individuals"]
    report = data.get(customer_id)
    if report is None:
        return {"error": f"no credit record for {customer_id}"}
    return {"customer_id": customer_id, **report}


@mcp.tool()
def get_company_credit(company_id: str) -> dict:
    """Get the SLIK OJK + Biro Kredit report for an SME/company."""
    data = load("credit_bureau.json")["companies"]
    report = data.get(company_id)
    if report is None:
        return {"error": f"no credit record for {company_id}"}
    return {"company_id": company_id, **report}


if __name__ == "__main__":
    mcp.run()
