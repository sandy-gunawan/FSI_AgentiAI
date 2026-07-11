"""MCP tool clients (Streamable HTTP) for the cloud-hosted surrounding systems.

All three MCP servers are mounted under the combined surrounding-systems service
(REST base URL) at /mcp/*. Locally, run `uvicorn mock_services.server:app
--port 8080`; in the cloud, point REST_BASE_URL at the Container App URL. Use as
async context managers::

    async with credit_bureau_tool() as credit:
        agent = Agent(client=..., tools=[credit], ...)
"""
from __future__ import annotations

from agent_framework import MCPStreamableHTTPTool

from app.core.config import get_settings


def _base() -> str:
    return get_settings().rest_base_url.rstrip("/")


def credit_bureau_tool() -> MCPStreamableHTTPTool:
    """SLIK OJK + Biro Kredit MCP server (remote)."""
    return MCPStreamableHTTPTool(name="credit_bureau", url=f"{_base()}/mcp/credit-bureau/")


def kyc_aml_tool() -> MCPStreamableHTTPTool:
    """Dukcapil / DTTOT / PPATK KYC-AML MCP server (remote)."""
    return MCPStreamableHTTPTool(name="kyc_aml", url=f"{_base()}/mcp/kyc-aml/")


def policy_rules_tool() -> MCPStreamableHTTPTool:
    """OJK/BI policy rules MCP server (remote)."""
    return MCPStreamableHTTPTool(name="policy_rules", url=f"{_base()}/mcp/policy-rules/")
