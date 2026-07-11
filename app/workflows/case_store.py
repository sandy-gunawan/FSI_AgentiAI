"""Persistent SME case store — enables human-in-the-loop across sessions.

Use Case 2 pauses for a human loan officer. Because the Streamlit portal is
stateless across reruns, the underwriting recommendation and case status are
persisted here (SQLite locally, maps to Azure PostgreSQL in the cloud) and keyed
by request_id, so the case can be paused and resumed reliably.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from app.core.config import get_settings

_LOCK = threading.Lock()

STATUS_PENDING = "PENDING_HUMAN"
STATUS_COMPLETED = "COMPLETED"


class CaseStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or get_settings().audit_db_abspath)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sme_cases (
                request_id     TEXT PRIMARY KEY,
                company_id     TEXT,
                status         TEXT NOT NULL,
                request_json   TEXT NOT NULL,
                recommendation_json TEXT,
                human_json     TEXT,
                termsheet_json TEXT,
                tokens         INTEGER DEFAULT 0,
                created_ts     TEXT,
                updated_ts     TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS aml_cases (
                request_id     TEXT PRIMARY KEY,
                subject_id     TEXT,
                status         TEXT NOT NULL,
                request_json   TEXT NOT NULL,
                recommendation_json TEXT,
                decision_json  TEXT,
                filing_json    TEXT,
                tokens         INTEGER DEFAULT 0,
                created_ts     TEXT,
                updated_ts     TEXT
            )
            """
        )
        self._conn.commit()

    def create_pending(self, request_id: str, company_id: str, request: dict,
                       recommendation: dict, tokens: int) -> None:
        now = datetime.utcnow().isoformat()
        with _LOCK:
            self._conn.execute(
                "INSERT OR REPLACE INTO sme_cases "
                "(request_id, company_id, status, request_json, recommendation_json, "
                " human_json, termsheet_json, tokens, created_ts, updated_ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (request_id, company_id, STATUS_PENDING, json.dumps(request),
                 json.dumps(recommendation), None, None, tokens, now, now),
            )
            self._conn.commit()

    def complete(self, request_id: str, human: dict, termsheet: dict, add_tokens: int) -> None:
        now = datetime.utcnow().isoformat()
        with _LOCK:
            self._conn.execute(
                "UPDATE sme_cases SET status=?, human_json=?, termsheet_json=?, "
                "tokens=tokens+?, updated_ts=? WHERE request_id=?",
                (STATUS_COMPLETED, json.dumps(human), json.dumps(termsheet),
                 add_tokens, now, request_id),
            )
            self._conn.commit()

    def get(self, request_id: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM sme_cases WHERE request_id=?", (request_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        rec = dict(zip(cols, row))
        for k in ("request_json", "recommendation_json", "human_json", "termsheet_json"):
            rec[k] = json.loads(rec[k]) if rec[k] else None
        return rec

    def list_pending(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT request_id, company_id, created_ts FROM sme_cases WHERE status=? "
            "ORDER BY created_ts DESC", (STATUS_PENDING,))
        return [{"request_id": r[0], "company_id": r[1], "created_ts": r[2]} for r in cur.fetchall()]

    def list_all(self, limit: int = 100) -> list[dict]:
        cur = self._conn.execute(
            "SELECT request_id, company_id, status, tokens, updated_ts FROM sme_cases "
            "ORDER BY updated_ts DESC LIMIT ?", (limit,))
        return [
            {"request_id": r[0], "company_id": r[1], "status": r[2], "tokens": r[3], "updated_ts": r[4]}
            for r in cur.fetchall()
        ]

    # ----------------------------------------------------------------------- #
    # AML investigation cases (Use Case 5 — human SAR gate)
    # ----------------------------------------------------------------------- #
    def create_aml_pending(self, request_id: str, subject_id: str, request: dict,
                           recommendation: dict, tokens: int) -> None:
        now = datetime.utcnow().isoformat()
        with _LOCK:
            self._conn.execute(
                "INSERT OR REPLACE INTO aml_cases "
                "(request_id, subject_id, status, request_json, recommendation_json, "
                " decision_json, filing_json, tokens, created_ts, updated_ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (request_id, subject_id, STATUS_PENDING, json.dumps(request),
                 json.dumps(recommendation), None, None, tokens, now, now),
            )
            self._conn.commit()

    def complete_aml(self, request_id: str, decision: dict, filing: dict, add_tokens: int) -> None:
        now = datetime.utcnow().isoformat()
        with _LOCK:
            self._conn.execute(
                "UPDATE aml_cases SET status=?, decision_json=?, filing_json=?, "
                "tokens=tokens+?, updated_ts=? WHERE request_id=?",
                (STATUS_COMPLETED, json.dumps(decision), json.dumps(filing),
                 add_tokens, now, request_id),
            )
            self._conn.commit()

    def get_aml(self, request_id: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM aml_cases WHERE request_id=?", (request_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        rec = dict(zip(cols, row))
        for k in ("request_json", "recommendation_json", "decision_json", "filing_json"):
            rec[k] = json.loads(rec[k]) if rec[k] else None
        return rec

    def list_aml_pending(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT request_id, subject_id, created_ts FROM aml_cases WHERE status=? "
            "ORDER BY created_ts DESC", (STATUS_PENDING,))
        return [{"request_id": r[0], "subject_id": r[1], "created_ts": r[2]} for r in cur.fetchall()]

    def list_aml_all(self, limit: int = 100) -> list[dict]:
        cur = self._conn.execute(
            "SELECT request_id, subject_id, status, tokens, updated_ts FROM aml_cases "
            "ORDER BY updated_ts DESC LIMIT ?", (limit,))
        return [
            {"request_id": r[0], "subject_id": r[1], "status": r[2], "tokens": r[3], "updated_ts": r[4]}
            for r in cur.fetchall()
        ]


_STORE: CaseStore | None = None


def get_case_store() -> CaseStore:
    global _STORE
    if _STORE is None:
        _STORE = CaseStore()
    return _STORE
