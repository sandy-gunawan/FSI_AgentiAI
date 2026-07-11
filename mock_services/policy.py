"""Deterministic OJK/BI-aligned policy evaluation.

Shared by the Policy Rules MCP server (agent-facing tool) and the workflow
orchestrator (deterministic compliance gate) so both use identical logic.
"""
from __future__ import annotations

from mock_services.data import load


def rules() -> dict:
    return load("policy_rules.json")


def evaluate_retail(
    age: int,
    monthly_income_idr: int,
    dbr_ratio: float,
    credit_score: int,
    slik_kol: int,
    sanctions_hit: bool,
    requested_amount_idr: int,
) -> dict:
    r = rules()["retail"]
    triggered: list[str] = []

    if sanctions_hit and r["sanctions_block"]:
        return {"decision": "DECLINE", "triggered_rules": ["DTTOT_SANCTIONS_HIT"],
                "reason": "Nasabah cocok dengan daftar sanksi DTTOT — ditolak."}
    if age < r["min_age"]:
        triggered.append("BELOW_MIN_AGE")
    if age > r["max_age"]:
        triggered.append("ABOVE_MAX_AGE")
    if monthly_income_idr < r["min_monthly_income_idr"]:
        triggered.append("BELOW_MIN_INCOME")
    if dbr_ratio > r["max_dbr_ratio"]:
        triggered.append("DBR_EXCEEDS_LIMIT")
    if credit_score and credit_score < r["min_credit_score"]:
        triggered.append("CREDIT_SCORE_TOO_LOW")
    if slik_kol > r["max_slik_kol"]:
        triggered.append("SLIK_COLLECTIBILITY_TOO_HIGH")

    if triggered:
        return {"decision": "DECLINE", "triggered_rules": triggered,
                "reason": "Melanggar satu atau lebih ketentuan kelayakan OJK/BI."}
    if requested_amount_idr >= r["auto_approve_ceiling_idr"]:
        return {"decision": "REFER", "triggered_rules": ["ABOVE_AUTO_APPROVE_CEILING"],
                "reason": "Jumlah di atas plafon straight-through — perlu review manusia."}
    return {"decision": "APPROVE", "triggered_rules": [],
            "reason": "Memenuhi seluruh ketentuan kelayakan."}


def evaluate_sme(
    years_operating: int,
    ltv_ratio: float,
    dscr: float,
    debt_to_equity: float,
    credit_score: int,
    sanctions_hit: bool,
    ppatk_flag: bool,
) -> dict:
    r = rules()["sme"]
    triggered: list[str] = []

    if (sanctions_hit or ppatk_flag) and r["sanctions_block"]:
        rule = "DTTOT_SANCTIONS_HIT" if sanctions_hit else "PPATK_STR_FLAG"
        return {"decision": "DECLINE", "triggered_rules": [rule],
                "reason": "Terindikasi sanksi DTTOT / laporan PPATK — ditolak."}
    if years_operating < r["min_years_operating"]:
        triggered.append("BELOW_MIN_OPERATING_YEARS")
    if ltv_ratio > r["max_ltv_ratio"]:
        triggered.append("LTV_EXCEEDS_LIMIT")
    if dscr < r["min_dscr"]:
        triggered.append("DSCR_BELOW_MIN")
    if debt_to_equity > r["max_debt_to_equity"]:
        triggered.append("DEBT_TO_EQUITY_TOO_HIGH")
    if credit_score and credit_score < r["min_credit_score"]:
        triggered.append("CREDIT_SCORE_TOO_LOW")

    if triggered:
        return {"decision": "DECLINE", "triggered_rules": triggered,
                "reason": "Tidak memenuhi ketentuan kredit UKM OJK/BI."}
    return {"decision": "REFER", "triggered_rules": [],
            "reason": "Lolos pra-skrining — diteruskan ke underwriter untuk keputusan manusia."}


def evaluate_restructure(
    new_dbr_ratio: float,
    new_installment_idr: int,
    original_installment_idr: int,
    new_tenor_months: int,
) -> dict:
    """Deterministic affordability/policy check for a loan-restructuring proposal.

    Reuses the retail DBR ceiling as the affordability bar. Returns an
    'affordable' verdict plus concrete reasons that feed the Evaluator agent's
    optimization loop.
    """
    r = rules()["retail"]
    max_dbr = r["max_dbr_ratio"]
    max_tenor = 60  # restructuring may extend tenor further than a fresh KTA
    issues: list[str] = []

    if new_dbr_ratio > max_dbr:
        issues.append(f"DBR_EXCEEDS_LIMIT (baru={new_dbr_ratio} > {max_dbr})")
    if new_installment_idr >= original_installment_idr:
        issues.append("NO_PAYMENT_RELIEF (angsuran baru tidak lebih ringan)")
    if new_tenor_months > max_tenor:
        issues.append(f"TENOR_EXCEEDS_MAX ({new_tenor_months} > {max_tenor} bln)")

    affordable = not issues
    return {
        "affordable": affordable,
        "policy_ok": new_dbr_ratio <= max_dbr and new_tenor_months <= max_tenor,
        "max_dbr_ratio": max_dbr,
        "max_tenor_months": max_tenor,
        "issues": issues,
        "reason": ("Proposal memenuhi ambang keterjangkauan & kebijakan."
                   if affordable else "Proposal belum memenuhi ambang; perlu revisi."),
    }
