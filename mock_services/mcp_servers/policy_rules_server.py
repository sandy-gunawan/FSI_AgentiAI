"""Policy Rules MCP server — OJK / BI aligned deterministic eligibility engine.

This is intentionally NOT an LLM: it applies hard rules so that compliance
decisions are reproducible and auditable. Agents call these tools; the returned
`triggered_rules` list is written to the audit trail.

Run standalone:  python -m mock_services.mcp_servers.policy_rules_server
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mock_services import policy

mcp = FastMCP(
    "policy-rules", stateless_http=True, streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def list_rules() -> dict:
    """Return the full OJK/BI-aligned rule set (retail + SME thresholds)."""
    return policy.rules()


@mcp.tool()
def evaluate_retail(
    age: int,
    monthly_income_idr: int,
    dbr_ratio: float,
    credit_score: int,
    slik_kol: int,
    sanctions_hit: bool,
    requested_amount_idr: int,
) -> dict:
    """Evaluate a retail loan against OJK/BI policy.

    Returns decision (APPROVE/DECLINE/REFER), triggered_rules and a reason.
    REFER means the amount exceeds the straight-through ceiling and must go to
    human review.
    """
    return policy.evaluate_retail(
        age, monthly_income_idr, dbr_ratio, credit_score,
        slik_kol, sanctions_hit, requested_amount_idr,
    )


@mcp.tool()
def evaluate_sme(
    years_operating: int,
    ltv_ratio: float,
    dscr: float,
    debt_to_equity: float,
    credit_score: int,
    sanctions_hit: bool,
    ppatk_flag: bool,
) -> dict:
    """Pre-screen an SME facility against OJK/BI policy.

    SME facilities always require human review (requires_human_review=true), so
    a clean pass returns REFER (to underwriter), not APPROVE. Hard blocks
    (sanctions / PPATK) return DECLINE.
    """
    return policy.evaluate_sme(
        years_operating, ltv_ratio, dscr, debt_to_equity,
        credit_score, sanctions_hit, ppatk_flag,
    )


if __name__ == "__main__":
    mcp.run()
