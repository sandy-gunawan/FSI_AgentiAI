"""MCP server exposing the 5 credit lookups as MCP tools (Streamable HTTP).

Mirrors the parent repo's mock_services MCP pattern. Each @mcp.tool() wraps the
SAME function in queries.py — so MCP and REST hit identical SQL.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from sql_service import queries

mcp = FastMCP(
    "bca-credit", stateless_http=True, streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def get_client_facility(client_id: str) -> dict:
    """Get a client's (seller's) financing facility: limit, outstanding, headroom."""
    return queries.get_client_facility(client_id)


@mcp.tool()
def get_buyer_credit(buyer_id: str) -> dict:
    """Get a buyer's (debtor's) credit rating, credit limit, PD and our exposure."""
    return queries.get_buyer_credit(buyer_id)


@mcp.tool()
def get_buyer_payment_behaviour(buyer_id: str) -> dict:
    """Get a buyer's payment behaviour: avg days to pay, on-time rate, disputes."""
    return queries.get_buyer_payment_behaviour(buyer_id)


@mcp.tool()
def check_duplicate_invoice(invoice_no: str, client_id: str) -> dict:
    """Check whether an invoice number was already financed for a client."""
    return queries.check_duplicate_invoice(invoice_no, client_id)


@mcp.tool()
def check_watchlist(npwp: str) -> dict:
    """Check whether an NPWP is on the DTTOT/PPATK sanctions watchlist."""
    return queries.check_watchlist(npwp)
