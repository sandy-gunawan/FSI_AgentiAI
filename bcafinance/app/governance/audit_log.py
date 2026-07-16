"""Persistent audit log — every agent step, extraction, and decision.

Stored in SQLite locally (data/audit.db). The same interface maps to Azure
Database for PostgreSQL in the cloud. The portal's "Audit & Governance" panels
read from here.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from app.core.config import get_settings
from app.core.models import AuditEvent

_LOCK = threading.Lock()


class AuditLogger:
    """Thread-safe append-only audit store."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or get_settings().audit_db_abspath)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                use_case   TEXT NOT NULL,
                step       TEXT NOT NULL,
                actor      TEXT NOT NULL,
                detail     TEXT NOT NULL,
                decision   TEXT,
                tokens     INTEGER DEFAULT 0,
                ts         TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def log(self, event: AuditEvent) -> None:
        with _LOCK:
            self._conn.execute(
                "INSERT INTO audit_events "
                "(request_id, use_case, step, actor, detail, decision, tokens, ts) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (event.request_id, event.use_case, event.step, event.actor,
                 event.detail, event.decision, event.tokens, event.ts.isoformat()),
            )
            self._conn.commit()

    def record(self, request_id: str, use_case: str, step: str, actor: str,
               detail: str, decision: str | None = None, tokens: int = 0) -> None:
        self.log(AuditEvent(
            request_id=request_id, use_case=use_case, step=step, actor=actor,
            detail=detail, decision=decision, tokens=tokens, ts=datetime.utcnow(),
        ))

    def events_for(self, request_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT request_id, use_case, step, actor, detail, decision, tokens, ts "
            "FROM audit_events WHERE request_id=? ORDER BY id", (request_id,),
        )
        return [self._row(r) for r in cur.fetchall()]

    def recent(self, limit: int = 200) -> list[dict]:
        cur = self._conn.execute(
            "SELECT request_id, use_case, step, actor, detail, decision, tokens, ts "
            "FROM audit_events ORDER BY id DESC LIMIT ?", (limit,),
        )
        return [self._row(r) for r in cur.fetchall()]

    @staticmethod
    def _row(r: tuple) -> dict:
        return {"request_id": r[0], "use_case": r[1], "step": r[2], "actor": r[3],
                "detail": r[4], "decision": r[5], "tokens": r[6], "ts": r[7]}


_AUDIT: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = AuditLogger()
    return _AUDIT
