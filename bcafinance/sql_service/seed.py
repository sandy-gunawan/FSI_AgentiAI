"""Schema + seed data for the BCA Finance credit-context database (SQL Server 2019).

Creates the `bcacredit` database, the tables, and inserts demo rows that are
ALIGNED with the 20 sample invoices (same sellers = clients, same buyers). This
runs once on service startup (idempotent: drops + recreates for a clean demo).

Tables:
  clients            — the sellers we finance (from invoice VendorName)
  facilities         — each client's financing facility (limit / outstanding)
  buyers             — the debtors who must pay the invoice (creditworthiness)
  buyer_exposure     — how much we're already exposed to each buyer
  payment_behaviour  — how each buyer actually pays (days late, disputes)
  invoice_history    — invoices already financed (for duplicate detection)
  watchlist          — DTTOT/PPATK sanctions by NPWP
"""
from __future__ import annotations


# ---- clients (sellers) — mirror _SELLERS in generate_sample_invoices.py ---- #
CLIENTS = [
    ("CLI-01", "PT Maju Bersama", "8820-1177-9043", "Energi Terbarukan", "Budi Santoso", "low"),
    ("CLI-02", "PT Sinar Teknologi", "8811-2244-1090", "Teknologi", "Sari Dewi", "low"),
    ("CLI-03", "CV Karya Mandiri", "8890-5533-2211", "Konstruksi", "Andi Wijaya", "medium"),
    ("CLI-04", "PT Nusantara Logistik", "8802-7788-6655", "Logistik", "Rina Putri", "low"),
    ("CLI-05", "PT Agro Sejahtera", "8877-1122-3344", "Agrikultur", "Dewi Lestari", "medium"),
]

# ---- facilities (headroom = limit - outstanding) --------------------------- #
FACILITIES = [
    # facility_id, client_id, limit, outstanding, advance_rate, status
    ("FAC-01", "CLI-01", 1_000_000_000, 800_000_000, 0.80, "active"),   # headroom 200 jt
    ("FAC-02", "CLI-02", 3_000_000_000, 1_200_000_000, 0.80, "active"),
    ("FAC-03", "CLI-03", 500_000_000, 450_000_000, 0.75, "active"),     # tight headroom 50 jt
    ("FAC-04", "CLI-04", 2_000_000_000, 300_000_000, 0.80, "active"),
    ("FAC-05", "CLI-05", 1_500_000_000, 1_450_000_000, 0.80, "suspended"),
]

# ---- buyers (debtors) — mirror _BUYERS ------------------------------------- #
BUYERS = [
    # buyer_id, name, npwp, rating, credit_limit, pd_pct
    ("BUY-01", "PT Karya Retail Nusantara", "01.234.567.8-901.000", "B", 1_500_000_000, 4.0),
    ("BUY-02", "PT Global Distribusi", "02.345.678.9-012.000", "A", 5_000_000_000, 1.2),
    ("BUY-03", "PT Prima Konstruksi", "03.456.789.0-123.000", "C", 800_000_000, 9.5),
    ("BUY-04", "PT Sentosa Manufaktur", "04.567.890.1-234.000", "B", 2_000_000_000, 3.5),
    ("BUY-05", "PT Bahari Niaga", "05.678.901.2-345.000", "D", 300_000_000, 18.0),
]

# ---- buyer_exposure (total outstanding we hold against each buyer) --------- #
EXPOSURE = [
    ("BUY-01", 1_800_000_000, 6),   # OVER its 1.5 bn credit limit -> concentration flag
    ("BUY-02", 900_000_000, 3),
    ("BUY-03", 620_000_000, 4),
    ("BUY-04", 400_000_000, 2),
    ("BUY-05", 120_000_000, 1),
]

# ---- payment_behaviour ------------------------------------------------------ #
BEHAVIOUR = [
    ("BUY-01", 12, 0.88, 0),
    ("BUY-02", 4, 0.98, 0),
    ("BUY-03", 25, 0.71, 2),   # pays late, disputes
    ("BUY-04", 9, 0.93, 0),
    ("BUY-05", 40, 0.55, 3),
]

# ---- invoice_history (already financed) — includes INV-2026-1000 (=INV-01) - #
INVOICE_HISTORY = [
    # invoice_no, client_id, buyer_id, amount, issue, due, status, paid_date, dpd
    ("INV-2026-1000", "CLI-01", "BUY-01", 109_179_600, "2026-07-01", "2026-09-29", "financed", None, 0),
    ("INV-2026-0500", "CLI-01", "BUY-02", 250_000_000, "2026-05-10", "2026-08-08", "paid", "2026-08-05", 0),
    ("INV-2026-0611", "CLI-03", "BUY-03", 180_000_000, "2026-06-01", "2026-07-31", "overdue", None, 12),
    ("INV-2026-0722", "CLI-02", "BUY-04", 420_000_000, "2026-06-20", "2026-09-18", "financed", None, 0),
    ("INV-2026-0733", "CLI-04", "BUY-02", 300_000_000, "2026-06-25", "2026-08-24", "paid", "2026-08-20", 0),
    ("INV-2026-0810", "CLI-05", "BUY-05", 120_000_000, "2026-06-30", "2026-10-28", "financed", None, 0),
]

# ---- watchlist (DTTOT sanctions) ------------------------------------------- #
WATCHLIST = [
    ("05.678.901.2-345.000", "DTTOT", "Terduga pendanaan terlarang (contoh demo)"),
]

_SCHEMA = """
IF OBJECT_ID('watchlist','U') IS NOT NULL DROP TABLE watchlist;
IF OBJECT_ID('invoice_history','U') IS NOT NULL DROP TABLE invoice_history;
IF OBJECT_ID('payment_behaviour','U') IS NOT NULL DROP TABLE payment_behaviour;
IF OBJECT_ID('buyer_exposure','U') IS NOT NULL DROP TABLE buyer_exposure;
IF OBJECT_ID('facilities','U') IS NOT NULL DROP TABLE facilities;
IF OBJECT_ID('buyers','U') IS NOT NULL DROP TABLE buyers;
IF OBJECT_ID('clients','U') IS NOT NULL DROP TABLE clients;

CREATE TABLE clients (
  client_id   VARCHAR(16) PRIMARY KEY,
  legal_name  NVARCHAR(120) NOT NULL,
  npwp        VARCHAR(32),
  sector      NVARCHAR(60),
  rm          NVARCHAR(60),
  kyc_risk    VARCHAR(10)
);
CREATE TABLE facilities (
  facility_id     VARCHAR(16) PRIMARY KEY,
  client_id       VARCHAR(16) NOT NULL,
  facility_limit_idr BIGINT NOT NULL,
  outstanding_idr    BIGINT NOT NULL,
  advance_rate    DECIMAL(4,2) NOT NULL,
  status          VARCHAR(16) NOT NULL
);
CREATE TABLE buyers (
  buyer_id        VARCHAR(16) PRIMARY KEY,
  legal_name      NVARCHAR(120) NOT NULL,
  npwp            VARCHAR(32),
  internal_rating VARCHAR(4),
  credit_limit_idr BIGINT,
  pd_pct          DECIMAL(5,2)
);
CREATE TABLE buyer_exposure (
  buyer_id             VARCHAR(16) PRIMARY KEY,
  total_outstanding_idr BIGINT NOT NULL,
  invoice_count        INT NOT NULL
);
CREATE TABLE payment_behaviour (
  buyer_id         VARCHAR(16) PRIMARY KEY,
  avg_days_to_pay  INT NOT NULL,
  on_time_rate     DECIMAL(4,2) NOT NULL,
  disputes_12m     INT NOT NULL
);
CREATE TABLE invoice_history (
  invoice_no  VARCHAR(40) NOT NULL,
  client_id   VARCHAR(16) NOT NULL,
  buyer_id    VARCHAR(16) NOT NULL,
  amount_idr  BIGINT NOT NULL,
  issue_date  DATE,
  due_date    DATE,
  status      VARCHAR(16),
  paid_date   DATE NULL,
  dpd         INT
);
CREATE TABLE watchlist (
  npwp       VARCHAR(32) NOT NULL,
  list_type  VARCHAR(16) NOT NULL,
  reason     NVARCHAR(200)
);
"""


def seed() -> dict:
    """Create the database, schema, and rows. Idempotent (drops + recreates)."""
    from sql_service import db as _db

    # 1) Ensure the database exists (autocommit on master).
    master = _db.connect(database="master")
    master.autocommit(True)
    cur = master.cursor()
    cur.execute("IF DB_ID('bcacredit') IS NULL CREATE DATABASE bcacredit;")
    master.close()

    # 2) Schema + data in bcacredit.
    conn = _db.connect(database="bcacredit")
    cur = conn.cursor()
    for stmt in [s for s in _SCHEMA.split(";\n") if s.strip()]:
        cur.execute(stmt)
    cur.executemany(
        "INSERT INTO clients VALUES (%s,%s,%s,%s,%s,%s)", CLIENTS)
    cur.executemany(
        "INSERT INTO facilities VALUES (%s,%s,%s,%s,%s,%s)", FACILITIES)
    cur.executemany(
        "INSERT INTO buyers VALUES (%s,%s,%s,%s,%s,%s)", BUYERS)
    cur.executemany(
        "INSERT INTO buyer_exposure VALUES (%s,%s,%s)", EXPOSURE)
    cur.executemany(
        "INSERT INTO payment_behaviour VALUES (%s,%s,%s,%s)", BEHAVIOUR)
    cur.executemany(
        "INSERT INTO invoice_history VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", INVOICE_HISTORY)
    cur.executemany(
        "INSERT INTO watchlist VALUES (%s,%s,%s)", WATCHLIST)
    conn.commit()

    counts = {}
    for t in ("clients", "facilities", "buyers", "buyer_exposure",
              "payment_behaviour", "invoice_history", "watchlist"):
        cur.execute(f"SELECT COUNT(*) AS n FROM {t}")
        counts[t] = cur.fetchone()["n"]
    conn.close()
    return counts
