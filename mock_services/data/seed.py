"""Deterministic dummy-data generator for the BNS financing demo (Indonesia).

Run once:  python mock_services/data/seed.py

Generates linked JSON datasets consumed by the mock MCP servers and REST APIs:
  customers.json     retail applicants (NIK, income, employment)
  companies.json     SME applicants (NPWP, sector, directors)
  credit_bureau.json SLIK OJK + Biro Kredit (Pefindo) reports
  kyc.json           Dukcapil / DTTOT sanctions / PPATK / PEP
  accounts.json      core-banking accounts
  transactions.json  6 months of transactions per customer
  collateral.json    collateral appraisals
  financials.json    3 years of SME financial statements
  products.json      loan product & pricing catalog
  policy_rules.json  OJK/BI-aligned eligibility thresholds

All records are fake. Edge cases are injected deterministically so the two
agentic workflows exercise approve / decline / refer / sanctions / human-review.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

DATA_DIR = Path(__file__).resolve().parent
SEED = 20260711
fake = Faker("id_ID")
Faker.seed(SEED)
random.seed(SEED)

JT = 1_000_000  # juta (million) IDR
M = 1_000_000_000  # miliar (billion) IDR

KABUPATEN = [
    "Jakarta Selatan", "Bandung", "Surabaya", "Medan", "Semarang",
    "Makassar", "Tangerang", "Depok", "Bekasi", "Yogyakarta",
]
SECTORS = [
    "manufacturing", "retail_trade", "agriculture", "construction",
    "food_beverage", "logistics", "textile", "healthcare",
]


def _nik() -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(16))


def _npwp() -> str:
    d = [str(random.randint(0, 9)) for _ in range(15)]
    return f"{''.join(d[0:2])}.{''.join(d[2:5])}.{''.join(d[5:8])}.{d[8]}-{''.join(d[9:12])}.{''.join(d[12:15])}"


def _mask_phone() -> str:
    return f"+62811{random.randint(1000000, 9999999)}"


def _installment(principal_idr: int, annual_rate_pct: float, tenor_months: int) -> int:
    """Amortising monthly installment (anuitas) — local copy to avoid app imports."""
    r = annual_rate_pct / 100 / 12
    n = max(1, tenor_months)
    if r <= 0:
        return int(principal_idr / n)
    return int(round(principal_idr * r * (1 + r) ** n / ((1 + r) ** n - 1)))


# --------------------------------------------------------------------------- #
# Retail customers (CUST-1001 .. CUST-1040)
# --------------------------------------------------------------------------- #
def gen_customers() -> list[dict]:
    customers = []
    for i in range(40):
        cid = f"CUST-{1001 + i}"
        emp = random.choice(["salaried", "self_employed"])
        income = random.choice([6, 9, 12, 15, 18, 22, 28, 35, 45]) * JT
        born = fake.date_between(start_date="-58y", end_date="-22y")
        customers.append(
            {
                "customer_id": cid,
                "full_name": fake.name(),
                "nik": _nik(),
                "dob": born.isoformat(),
                "email": fake.email(),
                "phone": _mask_phone(),
                "employment_type": emp,
                "monthly_income_idr": income,
                "customer_since": fake.date_between(
                    start_date="-8y", end_date="-1y"
                ).isoformat(),
                "kabupaten": random.choice(KABUPATEN),
            }
        )
    # ---- Edge cases ----
    customers[4]["monthly_income_idr"] = 4 * JT       # below min income -> decline
    customers[5]["monthly_income_idr"] = 9 * JT       # CUST-1006: hard restructuring (multi-iteration)
    customers[7]["dob"] = date.today().replace(year=date.today().year - 19).isoformat()  # underage (<21)
    return customers


# --------------------------------------------------------------------------- #
# SME companies (SME-5001 .. SME-5015)
# --------------------------------------------------------------------------- #
def gen_companies() -> list[dict]:
    companies = []
    for i in range(15):
        sid = f"SME-{5001 + i}"
        revenue = random.choice([8, 15, 24, 42, 60, 85, 120]) * M
        directors = [
            {
                "name": fake.name(),
                "nik": _nik(),
                "ownership_pct": pct,
                "is_pep": False,
            }
            for pct in ([60, 40] if random.random() > 0.5 else [100])
        ]
        companies.append(
            {
                "company_id": sid,
                "legal_name": f"PT {fake.company()}".replace(",", ""),
                "npwp": _npwp(),
                "sector": random.choice(SECTORS),
                "established_year": random.randint(2005, 2021),
                "annual_revenue_idr": revenue,
                "employees": random.randint(15, 400),
                "directors": directors,
                "collateral_id": f"COL-{9001 + i}",
            }
        )
    # ---- Edge cases ----
    companies[2]["directors"][0]["is_pep"] = True     # PEP director -> human scrutiny
    return companies


# --------------------------------------------------------------------------- #
# Credit bureau (SLIK OJK + Biro Kredit / Pefindo)
# --------------------------------------------------------------------------- #
def gen_credit_bureau(customers: list[dict], companies: list[dict]) -> dict:
    individuals: dict[str, dict] = {}
    for c in customers:
        score = random.randint(520, 860)
        grade = "A" if score >= 780 else "B" if score >= 680 else "C" if score >= 580 else "D"
        income = c["monthly_income_idr"]
        monthly_debt = int(income * random.uniform(0.05, 0.30))
        individuals[c["customer_id"]] = {
            "credit_score": score,
            "risk_grade": grade,
            "slik_kol": 1 if score >= 620 else random.choice([1, 2, 2]),
            "total_outstanding_debt_idr": monthly_debt * random.randint(12, 40),
            "monthly_debt_obligations_idr": monthly_debt,
            "active_facilities": [
                {"type": random.choice(["KTA", "KKB", "Kartu Kredit"]),
                 "monthly_payment_idr": monthly_debt}
            ],
            "delinquencies_12m": 0 if score >= 640 else random.randint(1, 3),
            "enquiries_6m": random.randint(0, 4),
        }
    # ---- Edge cases ----
    individuals["CUST-1006"].update(          # tight budget -> hard multi-round restructuring
        {"monthly_debt_obligations_idr": 5_300_000,
         "credit_score": 590, "risk_grade": "C", "slik_kol": 2, "delinquencies_12m": 2}
    )
    individuals["CUST-1011"].update(          # thin file
        {"credit_score": 0, "risk_grade": "D", "slik_kol": 1,
         "total_outstanding_debt_idr": 0, "monthly_debt_obligations_idr": 0,
         "active_facilities": [], "delinquencies_12m": 0, "enquiries_6m": 0}
    )

    companies_cb: dict[str, dict] = {}
    for co in companies:
        score = random.randint(560, 850)
        companies_cb[co["company_id"]] = {
            "credit_score": score,
            "risk_grade": "A" if score >= 780 else "B" if score >= 680 else "C",
            "slik_kol": 1 if score >= 640 else 2,
            "total_outstanding_debt_idr": int(co["annual_revenue_idr"] * random.uniform(0.1, 0.4)),
            "delinquencies_12m": 0 if score >= 660 else random.randint(1, 2),
        }
    return {"individuals": individuals, "companies": companies_cb}


# --------------------------------------------------------------------------- #
# KYC / AML (Dukcapil + DTTOT sanctions + PPATK + PEP)
# --------------------------------------------------------------------------- #
def gen_kyc(customers: list[dict], companies: list[dict]) -> dict:
    individuals: dict[str, dict] = {}
    for c in customers:
        individuals[c["nik"]] = {
            "nik": c["nik"],
            "dukcapil_verified": True,
            "dttot_sanctions_hit": False,
            "pep_status": False,
            "adverse_media": [],
            "risk_rating": "low",
        }
    # ---- Edge case: DTTOT sanctions hit (terrorism watchlist) ----
    individuals[customers[9]["nik"]].update(
        {"dttot_sanctions_hit": True, "risk_rating": "high",
         "adverse_media": ["nama cocok dengan daftar DTTOT 2024"]}
    )

    companies_kyc: dict[str, dict] = {}
    for co in companies:
        pep = any(d["is_pep"] for d in co["directors"])
        companies_kyc[co["company_id"]] = {
            "company_id": co["company_id"],
            "dttot_sanctions_hit": False,
            "ppatk_flag": False,
            "beneficial_owner_pep": pep,
            "adverse_media": [],
            "risk_rating": "medium" if pep else "low",
        }
    # ---- Edge case: PPATK suspicious transaction flag ----
    companies_kyc["SME-5008"].update(
        {"ppatk_flag": True, "risk_rating": "high",
         "adverse_media": ["laporan transaksi keuangan mencurigakan (STR) 2025"]}
    )
    return {"individuals": individuals, "companies": companies_kyc}


# --------------------------------------------------------------------------- #
# Core banking (accounts + 6 months transactions)
# --------------------------------------------------------------------------- #
def gen_core_banking(customers: list[dict]) -> tuple[dict, dict]:
    accounts: dict[str, list] = {}
    transactions: dict[str, list] = {}
    for c in customers:
        cid = c["customer_id"]
        income = c["monthly_income_idr"]
        bal = int(income * random.uniform(0.5, 4.0))
        accounts[cid] = [
            {
                "account_no": f"1{random.randint(10**9, 10**10 - 1)}",
                "type": "tabungan",
                "balance_idr": bal,
                "opened_date": c["customer_since"],
                "avg_balance_6m_idr": int(bal * random.uniform(0.7, 1.1)),
            }
        ]
        txns = []
        today = date.today()
        for m in range(6):
            month_start = today - timedelta(days=30 * (m + 1))
            # salary / business income credit
            txns.append({
                "date": (month_start + timedelta(days=1)).isoformat(),
                "amount_idr": income,
                "direction": "credit",
                "category": "gaji" if c["employment_type"] == "salaried" else "pendapatan_usaha",
                "counterparty": "PT Pemberi Kerja" if c["employment_type"] == "salaried" else "Penjualan",
            })
            for _ in range(random.randint(4, 8)):
                txns.append({
                    "date": (month_start + timedelta(days=random.randint(2, 28))).isoformat(),
                    "amount_idr": int(income * random.uniform(0.02, 0.20)),
                    "direction": "debit",
                    "category": random.choice(["belanja", "utilitas", "cicilan", "transfer", "transportasi"]),
                    "counterparty": fake.company(),
                })
        transactions[cid] = sorted(txns, key=lambda t: t["date"])
    return accounts, transactions


# --------------------------------------------------------------------------- #
# Collateral appraisals
# --------------------------------------------------------------------------- #
def gen_collateral(companies: list[dict]) -> dict:
    collateral: dict[str, dict] = {}
    for co in companies:
        cid = co["collateral_id"]
        ctype = random.choice(["properti", "kendaraan", "mesin"])
        declared = int(co["annual_revenue_idr"] * random.uniform(0.3, 0.9))
        appraised = int(declared * random.uniform(0.75, 1.0))
        collateral[cid] = {
            "collateral_id": cid,
            "type": ctype,
            "declared_value_idr": declared,
            "appraised_value_idr": appraised,
            "location": random.choice(KABUPATEN),
            "condition": random.choice(["baik", "baik", "cukup"]),
            "owner_ref": co["company_id"],
        }
    # ---- Edge case: weak collateral (low value -> high LTV) ----
    collateral["COL-9004"]["appraised_value_idr"] = int(collateral["COL-9004"]["declared_value_idr"] * 0.35)
    return collateral


# --------------------------------------------------------------------------- #
# SME financial statements (3 years)
# --------------------------------------------------------------------------- #
def gen_financials(companies: list[dict]) -> dict:
    financials: dict[str, list] = {}
    this_year = date.today().year
    for co in companies:
        base_rev = co["annual_revenue_idr"]
        growth = random.uniform(0.95, 1.20)
        rows = []
        for k in range(3):
            year = this_year - (2 - k)
            revenue = int(base_rev * (growth ** (k - 2)))
            cogs = int(revenue * random.uniform(0.55, 0.75))
            gross = revenue - cogs
            opex = int(revenue * random.uniform(0.10, 0.20))
            ebitda = gross - opex
            net = int(ebitda * random.uniform(0.4, 0.7))
            assets = int(revenue * random.uniform(0.6, 1.2))
            liab = int(assets * random.uniform(0.35, 0.65))
            rows.append({
                "year": year,
                "revenue_idr": revenue,
                "cogs_idr": cogs,
                "gross_profit_idr": gross,
                "ebitda_idr": ebitda,
                "net_income_idr": net,
                "total_assets_idr": assets,
                "total_liabilities_idr": liab,
                "equity_idr": assets - liab,
                "current_assets_idr": int(assets * random.uniform(0.4, 0.7)),
                "current_liabilities_idr": int(liab * random.uniform(0.4, 0.8)),
                "operating_cashflow_idr": int(ebitda * random.uniform(0.6, 0.95)),
            })
        financials[co["company_id"]] = rows
    # ---- Edge case: declining revenue + negative net income latest year ----
    dec = financials["SME-5006"]
    dec[0]["revenue_idr"], dec[1]["revenue_idr"], dec[2]["revenue_idr"] = 60 * M, 45 * M, 30 * M
    dec[2]["net_income_idr"] = -5 * M
    dec[2]["operating_cashflow_idr"] = -2 * M
    return financials


# --------------------------------------------------------------------------- #
# Loan servicing — existing/outstanding facilities (Use Case 5: restructuring)
# --------------------------------------------------------------------------- #
def gen_existing_loans(customers: list[dict], credit_bureau: dict) -> dict:
    """Current outstanding retail facilities per customer, with arrears state."""
    loans: dict[str, dict] = {}
    individuals = credit_bureau["individuals"]
    for i, c in enumerate(customers):
        cid = c["customer_id"]
        income = c["monthly_income_idr"]
        grade = individuals.get(cid, {}).get("risk_grade", "C")
        rate = 12.0 + {"A": 0.0, "B": 2.0, "C": 4.5, "D": 7.0}.get(grade, 4.5)
        original = random.choice([30, 50, 75, 100, 150]) * JT
        remaining_tenor = random.randint(6, 30)
        installment = _installment(original, rate, remaining_tenor + random.randint(0, 12))
        outstanding = int(installment * remaining_tenor * random.uniform(0.85, 1.0))
        dpd = 0
        arrears = 0
        status = "lancar"
        loans[cid] = {
            "loan_id": f"LN-{7001 + i}",
            "product_code": "KTA-STD",
            "original_amount_idr": original,
            "outstanding_principal_idr": outstanding,
            "annual_rate_pct": round(rate, 2),
            "remaining_tenor_months": remaining_tenor,
            "monthly_installment_idr": installment,
            "days_past_due": dpd,
            "arrears_amount_idr": arrears,
            "status": status,
        }
    # ---- Edge cases: financial hardship / delinquency (restructuring candidates) ----
    # CUST-1006: flagship HARD case — large high-rate loan vs modest income, so the
    # conservative first proposal fails affordability and the reflection loop must revise.
    if "CUST-1006" in loans:
        _ln = loans["CUST-1006"]
        _ln["original_amount_idr"] = 120 * JT
        _ln["outstanding_principal_idr"] = 100 * JT
        _ln["annual_rate_pct"] = 16.5
        _ln["remaining_tenor_months"] = 24
        _ln["monthly_installment_idr"] = _installment(100 * JT, 16.5, 24)
    for cid, dpd, kol_status in [("CUST-1006", 62, "kurang lancar"),
                                 ("CUST-1013", 35, "dalam perhatian khusus"),
                                 ("CUST-1020", 91, "diragukan")]:
        if cid in loans:
            ln = loans[cid]
            ln["days_past_due"] = dpd
            ln["arrears_amount_idr"] = ln["monthly_installment_idr"] * max(1, dpd // 30)
            ln["status"] = kol_status
    return loans


# --------------------------------------------------------------------------- #
# Transaction monitoring — AML alerts (Use Case 6: investigation)
# --------------------------------------------------------------------------- #
def gen_alerts(customers: list[dict], kyc: dict) -> dict:
    """Per-customer transaction-monitoring alerts with AML typologies."""
    typologies = [
        ("structuring", "Setoran tunai dipecah di bawah ambang pelaporan (Rp 100 juta) berulang kali."),
        ("rapid_movement", "Dana masuk lalu segera ditransfer keluar (pass-through) dalam 24 jam."),
        ("high_risk_jurisdiction", "Transfer ke/dari yurisdiksi berisiko tinggi (FATF grey list)."),
        ("unusual_counterparty", "Transaksi dengan pihak lawan yang tidak sesuai profil usaha."),
    ]
    alerts: dict[str, dict] = {}
    kyc_ind = kyc["individuals"]
    for i, c in enumerate(customers):
        cid = c["customer_id"]
        # Most customers: no alerts (clean baseline).
        rows: list[dict] = []
        if i % 7 == 3:  # a sparse subset gets a low/medium alert
            typ, detail = typologies[i % len(typologies)]
            rows.append({
                "alert_id": f"ALT-{8001 + i}",
                "typology": typ,
                "severity": "medium" if i % 2 else "low",
                "detail": detail,
                "amount_idr": random.choice([80, 95, 120, 240]) * JT,
                "date": (date.today() - timedelta(days=random.randint(3, 40))).isoformat(),
            })
        nik = c["nik"]
        sanctioned = kyc_ind.get(nik, {}).get("dttot_sanctions_hit", False)
        risk = "high" if sanctioned or any(r["severity"] == "high" for r in rows) else (
            "medium" if rows else "low")
        alerts[cid] = {
            "customer_id": cid,
            "alerts": rows,
            "monitoring_risk_rating": risk,
        }
    # ---- Edge case: strong SAR candidate (aligns with DTTOT sanctions hit CUST-1010) ----
    strong = alerts.get("CUST-1010")
    if strong is not None:
        strong["alerts"] = [
            {"alert_id": "ALT-9010A", "typology": "structuring",
             "severity": "high", "detail": typologies[0][1],
             "amount_idr": 95 * JT, "date": (date.today() - timedelta(days=6)).isoformat()},
            {"alert_id": "ALT-9010B", "typology": "rapid_movement",
             "severity": "high", "detail": typologies[1][1],
             "amount_idr": 480 * JT, "date": (date.today() - timedelta(days=4)).isoformat()},
            {"alert_id": "ALT-9010C", "typology": "high_risk_jurisdiction",
             "severity": "medium", "detail": typologies[2][1],
             "amount_idr": 260 * JT, "date": (date.today() - timedelta(days=2)).isoformat()},
        ]
        strong["monitoring_risk_rating"] = "high"
    return alerts


# --------------------------------------------------------------------------- #
# Pricing / product catalog
# --------------------------------------------------------------------------- #
def gen_products() -> dict:
    return {
        "base_rate_pct": 12.0,
        "risk_spread_by_grade": {"A": 0.0, "B": 2.0, "C": 4.5, "D": 7.0},
        "products": [
            {"product_code": "KTA-STD", "name": "Kredit Tanpa Agunan",
             "segment": "retail", "min_amount_idr": 5 * JT, "max_amount_idr": 300 * JT,
             "min_tenor_months": 6, "max_tenor_months": 36},
            {"product_code": "SME-TERM", "name": "Kredit Investasi UKM",
             "segment": "sme", "min_amount_idr": 100 * JT, "max_amount_idr": 20 * M,
             "min_tenor_months": 12, "max_tenor_months": 60},
            {"product_code": "SME-RC", "name": "Kredit Modal Kerja (Revolving)",
             "segment": "sme", "min_amount_idr": 100 * JT, "max_amount_idr": 15 * M,
             "min_tenor_months": 12, "max_tenor_months": 36},
        ],
    }


# --------------------------------------------------------------------------- #
# Policy rules (OJK / BI aligned)
# --------------------------------------------------------------------------- #
def gen_policy_rules() -> dict:
    return {
        "retail": {
            "min_monthly_income_idr": 5 * JT,
            "max_dbr_ratio": 0.40,          # Debt Burden Ratio (a.k.a. DTI)
            "min_age": 21,
            "max_age": 60,
            "min_credit_score": 580,
            "max_slik_kol": 2,              # collectibility; >2 = reject
            "sanctions_block": True,        # DTTOT hit = hard fail
            "auto_approve_ceiling_idr": 100 * JT,
        },
        "sme": {
            "min_years_operating": 2,
            "max_ltv_ratio": 0.80,          # loan-to-value on collateral
            "min_dscr": 1.20,               # debt service coverage ratio
            "max_debt_to_equity": 2.5,
            "min_credit_score": 620,
            "sanctions_block": True,        # DTTOT / PPATK STR = escalate/hard fail
            "requires_human_review": True,
        },
    }


def main() -> None:
    customers = gen_customers()
    companies = gen_companies()
    accounts, transactions = gen_core_banking(customers)
    credit_bureau = gen_credit_bureau(customers, companies)
    kyc = gen_kyc(customers, companies)

    outputs = {
        "customers.json": customers,
        "companies.json": companies,
        "credit_bureau.json": credit_bureau,
        "kyc.json": kyc,
        "accounts.json": accounts,
        "transactions.json": transactions,
        "collateral.json": gen_collateral(companies),
        "financials.json": gen_financials(companies),
        "products.json": gen_products(),
        "policy_rules.json": gen_policy_rules(),
        "existing_loans.json": gen_existing_loans(customers, credit_bureau),
        "alerts.json": gen_alerts(customers, kyc),
    }
    for name, payload in outputs.items():
        path = DATA_DIR / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {name} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
