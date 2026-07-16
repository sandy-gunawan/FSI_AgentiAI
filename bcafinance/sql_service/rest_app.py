"""REST (OpenAPI) endpoints exposing the 5 credit lookups.

Each endpoint wraps the SAME function in queries.py — so REST and MCP hit
identical SQL. FastAPI auto-generates OpenAPI, but Foundry needs OpenAPI 3.0.x,
so the provisioning script attaches a hand-built 3.0.3 spec (see provision).
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from sql_service import queries

rest = FastAPI(title="bca-credit-rest", version="1.0.0",
               description="Credit-context lookups over SQL Server 2019.")


class ClientReq(BaseModel):
    client_id: str


class BuyerReq(BaseModel):
    buyer_id: str


class DuplicateReq(BaseModel):
    invoice_no: str
    client_id: str


class WatchlistReq(BaseModel):
    npwp: str


@rest.post("/get_client_facility", operation_id="get_client_facility")
def _facility(req: ClientReq) -> dict:
    return queries.get_client_facility(req.client_id)


@rest.post("/get_buyer_credit", operation_id="get_buyer_credit")
def _buyer(req: BuyerReq) -> dict:
    return queries.get_buyer_credit(req.buyer_id)


@rest.post("/get_buyer_payment_behaviour", operation_id="get_buyer_payment_behaviour")
def _behaviour(req: BuyerReq) -> dict:
    return queries.get_buyer_payment_behaviour(req.buyer_id)


@rest.post("/check_duplicate_invoice", operation_id="check_duplicate_invoice")
def _dup(req: DuplicateReq) -> dict:
    return queries.check_duplicate_invoice(req.invoice_no, req.client_id)


@rest.post("/check_watchlist", operation_id="check_watchlist")
def _watch(req: WatchlistReq) -> dict:
    return queries.check_watchlist(req.npwp)
