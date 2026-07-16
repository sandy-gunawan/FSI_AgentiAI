"""Cloud entrypoint for the credit-context service (SQL Server 2019 backend).

ONE ASGI app that exposes the SAME 5 lookups two ways:
    REST (OpenAPI)                 MCP (Streamable HTTP)
    /get_client_facility           /mcp/credit
    /get_buyer_credit
    /get_buyer_payment_behaviour   /health   (row counts)
    /check_duplicate_invoice       /admin/reseed
    /check_watchlist

On startup it waits for the SQL Server sidecar (localhost:1433), then creates +
seeds the `bcacredit` database (aligned to the 20 sample invoices).
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from sql_service.mcp_server import mcp as credit_mcp
from sql_service.rest_app import rest as rest_app
from sql_service import db, seed as seed_module

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bca.sql")

_credit_app = credit_mcp.streamable_http_app()
_STATE: dict = {"seeded": False, "counts": {}, "error": None}


def _do_seed() -> None:
    try:
        log.info("Waiting for SQL Server engine…")
        db.wait_for_server()
        log.info("Seeding bcacredit…")
        _STATE["counts"] = seed_module.seed()
        _STATE["seeded"] = True
        log.info("Seed complete: %s", _STATE["counts"])
    except Exception as exc:  # noqa: BLE001
        _STATE["error"] = str(exc)
        log.exception("Seed failed")


@contextlib.asynccontextmanager
async def _lifespan(app: Starlette) -> AsyncIterator[None]:
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(credit_mcp.session_manager.run())
        # Seed in a background thread so the app can start serving immediately.
        import threading
        threading.Thread(target=_do_seed, daemon=True).start()
        yield


async def _health(_request) -> JSONResponse:
    return JSONResponse({"status": "ok", **_STATE})


async def _reseed(_request) -> JSONResponse:
    _do_seed()
    return JSONResponse({"reseeded": _STATE["seeded"], "counts": _STATE["counts"],
                         "error": _STATE["error"]})


app = Starlette(
    routes=[
        Route("/health", _health),
        Route("/admin/reseed", _reseed, methods=["POST"]),
        Mount("/mcp/credit", app=_credit_app),
        Mount("/", app=rest_app),
    ],
    lifespan=_lifespan,
)
