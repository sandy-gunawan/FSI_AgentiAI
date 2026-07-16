"""Database connection helper for the SQL credit-context service.

Connects to the SQL Server 2019 container (sidecar) over localhost using SQL
auth. In production/on-prem this connection string is the ONE thing that
changes — point SQL_HOST at the on-prem SQL Server 2019 instance.

We use ``pymssql`` (bundled FreeTDS wheels — no system ODBC driver needed).
The equivalent with the official Microsoft driver would be ``pyodbc`` +
``ODBC Driver 18 for SQL Server`` (shown in the docs).
"""
from __future__ import annotations

import os
import time

import pymssql

SQL_HOST = os.getenv("SQL_HOST", "localhost")
SQL_PORT = int(os.getenv("SQL_PORT", "1433"))
SQL_USER = os.getenv("SQL_USER", "sa")
SQL_PASSWORD = os.getenv("SQL_PASSWORD", "")
SQL_DB = os.getenv("SQL_DB", "bcacredit")


def connect(database: str = SQL_DB, timeout: int = 15):
    """Open a new connection to the SQL Server (a specific database)."""
    return pymssql.connect(
        server=SQL_HOST, port=SQL_PORT, user=SQL_USER, password=SQL_PASSWORD,
        database=database, timeout=timeout, login_timeout=timeout, as_dict=True,
    )


def wait_for_server(max_seconds: int = 240) -> None:
    """Block until the SQL Server engine accepts connections (cold start)."""
    deadline = time.time() + max_seconds
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            conn = pymssql.connect(server=SQL_HOST, port=SQL_PORT, user=SQL_USER,
                                   password=SQL_PASSWORD, database="master",
                                   timeout=5, login_timeout=5)
            conn.close()
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(3)
    raise RuntimeError(f"SQL Server not ready after {max_seconds}s: {last_err}")
