"""Cloud entrypoint — ONE ASGI app exposing all BNS surrounding systems.

Mounts the REST back-office and the three MCP servers (Streamable HTTP) so the
whole "surrounding system" is reachable over public HTTPS and callable from any
system:

    REST                          MCP (Streamable HTTP)
    /core-banking/...             /mcp/credit-bureau
    /collateral/...               /mcp/kyc-aml
    /financials/...               /mcp/policy-rules
    /pricing/...
    /health                       /   (index with links)

Run locally:  uvicorn mock_services.server:app --port 8080
"""
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mock_services.mcp_servers.credit_bureau_server import mcp as credit_mcp
from mock_services.mcp_servers.kyc_aml_server import mcp as kyc_mcp
from mock_services.mcp_servers.policy_rules_server import mcp as policy_mcp
from mock_services.rest_apis.app import app as rest_app

# Build each MCP Streamable-HTTP sub-app once (wires routes to its session manager).
_credit_app = credit_mcp.streamable_http_app()
_kyc_app = kyc_mcp.streamable_http_app()
_policy_app = policy_mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def _lifespan(app: Starlette) -> AsyncIterator[None]:
    """Run all three MCP session managers for the lifetime of the process."""
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(credit_mcp.session_manager.run())
        await stack.enter_async_context(kyc_mcp.session_manager.run())
        await stack.enter_async_context(policy_mcp.session_manager.run())
        yield


async def _index(_request) -> JSONResponse:
    return JSONResponse(
        {
            "service": "BNS Surrounding Systems (data + REST + MCP)",
            "rest": ["/core-banking", "/collateral", "/financials", "/pricing", "/health"],
            "mcp": {
                "credit_bureau": "/mcp/credit-bureau",
                "kyc_aml": "/mcp/kyc-aml",
                "policy_rules": "/mcp/policy-rules",
            },
        }
    )


app = Starlette(
    routes=[
        Route("/", _index),
        Mount("/mcp/credit-bureau", app=_credit_app),
        Mount("/mcp/kyc-aml", app=_kyc_app),
        Mount("/mcp/policy-rules", app=_policy_app),
        Mount("/", app=rest_app),
    ],
    lifespan=_lifespan,
)
