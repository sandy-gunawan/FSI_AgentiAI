"""Offline smoke test — imports + deterministic rules engine (no Azure calls)."""
from __future__ import annotations

from app.core.models import InvoiceExtraction, Party
from app.portal.flow_viz import render_flow_html
from app.review import rules_engine
from app.tools.json_utils import parse_json
from app.workflows.invoice_review_workflow import _to_extraction, _to_review  # noqa: F401


def main() -> None:
    rules = rules_engine.load_rules()
    print("rules loaded · max_facility_idr =", rules["policy"]["max_facility_idr"])
    print("policy_block preview:", rules_engine.policy_block(rules)[:60], "...")

    base = InvoiceExtraction(
        invoice_number="INV-1", issue_date="2026-07-01", due_date="2026-09-29",
        total_amount_idr=597_180_000, subtotal_idr=538_000_000, tax_idr=59_180_000,
        seller=Party(name="PT A", account="123"), buyer=Party(name="PT B", npwp="01.234"),
    )
    print("APPROVE case      ->", rules_engine.evaluate(base, rules).decision.value)

    over = base.model_copy(update={"total_amount_idr": 1_200_000_000})
    print("over-limit        ->", rules_engine.evaluate(over, rules).decision.value)

    expired = base.model_copy(update={"due_date": "2027-06-01"})
    print("expired-tenor     ->", rules_engine.evaluate(expired, rules).decision.value)

    miss = base.model_copy(update={"buyer": Party(name="", npwp="")})
    print("missing-fields    ->", rules_engine.evaluate(miss, rules).decision.value)

    math_err = base.model_copy(update={"total_amount_idr": 500_000_000})
    print("math-error        ->", rules_engine.evaluate(math_err, rules).decision.value)

    # JSON parsing robustness + tolerant model coercion.
    parsed = parse_json('```json\n{"invoice_number":"X","total_amount_idr":100}\n```')
    assert parsed["invoice_number"] == "X"
    print("json_utils        -> OK")

    assert render_flow_html({"extract"}, set()).startswith("\n    <style>")
    print("flow_viz          -> OK")
    print("\nALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
