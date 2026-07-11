"""KYC/AML MCP server — Dukcapil (NIK), DTTOT sanctions, PPATK, PEP.

Screens individuals and entities for identity verification, terrorism-list
(DTTOT) sanctions hits, PPATK suspicious-transaction flags, PEP status and
adverse media.

Run standalone:  python -m mock_services.mcp_servers.kyc_aml_server
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mock_services.data import load

mcp = FastMCP(
    "kyc-aml", stateless_http=True, streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def screen_individual(nik: str) -> dict:
    """Screen an individual by NIK against Dukcapil and the DTTOT sanctions list.

    Returns dukcapil_verified, dttot_sanctions_hit (terrorism watchlist),
    pep_status, adverse_media and an overall risk_rating.
    """
    data = load("kyc.json")["individuals"]
    record = data.get(nik)
    if record is None:
        return {"nik": nik, "dukcapil_verified": False, "risk_rating": "unknown",
                "error": "NIK not found in Dukcapil"}
    return record


@mcp.tool()
def screen_entity(company_id: str) -> dict:
    """Screen an SME/company against DTTOT sanctions and PPATK flags.

    Returns dttot_sanctions_hit, ppatk_flag (suspicious transaction report),
    beneficial_owner_pep, adverse_media and an overall risk_rating.
    """
    data = load("kyc.json")["companies"]
    record = data.get(company_id)
    if record is None:
        return {"company_id": company_id, "risk_rating": "unknown",
                "error": "entity not found"}
    return record


if __name__ == "__main__":
    mcp.run()
