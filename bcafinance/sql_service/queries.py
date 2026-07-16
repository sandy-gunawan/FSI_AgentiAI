"""The 5 fixed, parameterized SQL lookups — the SINGLE source of truth.

Both the REST endpoints (rest_app.py) and the MCP tools (mcp_server.py) call
these exact functions. The LLM never writes SQL; it only picks a function and
supplies a parameter. Every query uses parameter binding (``%s``) → no SQL
injection. Read-only SELECTs only.

(With the Microsoft ODBC driver / pyodbc the placeholder would be ``?`` instead
of pymssql's ``%s`` — otherwise identical.)
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sql_service import db


def _jsonable(row: dict) -> dict:
    """Convert SQL types (Decimal / date / datetime) into JSON-safe values."""
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _one(sql: str, params: tuple) -> dict | None:
    conn = db.connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def _all(sql: str, params: tuple) -> list[dict]:
    conn = db.connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


# Read-only table viewer (fixed table names, SELECT * — for the /admin/tables demo view).
_VIEWABLE_TABLES = (
    "clients", "facilities", "buyers", "buyer_exposure",
    "payment_behaviour", "invoice_history", "watchlist",
)


def dump_tables() -> dict:
    """Return every row of every table (read-only) — for viewing the seeded DB."""
    out: dict = {}
    conn = db.connect()
    try:
        cur = conn.cursor()
        for t in _VIEWABLE_TABLES:
            cur.execute(f"SELECT * FROM {t}")   # fixed identifier, no user input
            out[t] = [_jsonable(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return out


def get_client_facility(client_id: str) -> dict:
    """Facility limit / outstanding / headroom for a client (seller)."""
    row = _one(
        "SELECT f.facility_id, f.client_id, c.legal_name, f.facility_limit_idr, "
        "f.outstanding_idr, f.advance_rate, f.status "
        "FROM facilities f JOIN clients c ON c.client_id = f.client_id "
        "WHERE f.client_id = %s", (client_id,))
    if not row:
        return {"found": False, "client_id": client_id}
    row["found"] = True
    row["headroom_idr"] = int(row["facility_limit_idr"]) - int(row["outstanding_idr"])
    return row


def get_buyer_credit(buyer_id: str) -> dict:
    """Buyer (debtor) creditworthiness + our current exposure to them."""
    row = _one(
        "SELECT b.buyer_id, b.legal_name, b.npwp, b.internal_rating, b.credit_limit_idr, "
        "b.pd_pct, e.total_outstanding_idr, e.invoice_count "
        "FROM buyers b LEFT JOIN buyer_exposure e ON e.buyer_id = b.buyer_id "
        "WHERE b.buyer_id = %s", (buyer_id,))
    if not row:
        return {"found": False, "buyer_id": buyer_id}
    row["found"] = True
    limit = int(row["credit_limit_idr"] or 0)
    outstanding = int(row["total_outstanding_idr"] or 0)
    row["over_credit_limit"] = outstanding > limit
    return row


def get_buyer_payment_behaviour(buyer_id: str) -> dict:
    """How this buyer actually pays: avg days late, on-time rate, disputes."""
    row = _one(
        "SELECT buyer_id, avg_days_to_pay, on_time_rate, disputes_12m "
        "FROM payment_behaviour WHERE buyer_id = %s", (buyer_id,))
    return row or {"found": False, "buyer_id": buyer_id}


def check_duplicate_invoice(invoice_no: str, client_id: str) -> dict:
    """Has this invoice number already been financed for this client?"""
    rows = _all(
        "SELECT invoice_no, client_id, buyer_id, amount_idr, status "
        "FROM invoice_history WHERE invoice_no = %s AND client_id = %s",
        (invoice_no, client_id))
    return {"invoice_no": invoice_no, "client_id": client_id,
            "duplicate": len(rows) > 0, "matches": rows}


def check_watchlist(npwp: str) -> dict:
    """Is this NPWP on the DTTOT/PPATK sanctions watchlist?"""
    rows = _all(
        "SELECT npwp, list_type, reason FROM watchlist WHERE npwp = %s", (npwp,))
    return {"npwp": npwp, "hit": len(rows) > 0, "entries": rows}
