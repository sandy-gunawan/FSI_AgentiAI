"""Use Case 8 — Syndicated / Co-Financing.

Communication architecture: A2A (Agent2Agent protocol) — CROSS-ORGANISATION.

    BNS Lead Arranger (LLM) ──> A2A: discover Agent Card ──> Partner Bank Agent (remote, other org)
                                A2A: message/send task <── ParticipationOffer
            └─────────────────► synthesise final syndication structure

Unlike MCP (agent → tools) or in-process orchestration, here BNS delegates to an
INDEPENDENTLY-OWNED, separately-deployed agent it does not control, using the open
A2A protocol (Agent Card discovery + JSON-RPC message/send).
"""
from __future__ import annotations

import json

from app.agents.shared.model_client import financing_session
from app.agents.syndication.agents import LEAD_ARRANGER, SYNTHESIZER
from app.core.config import get_settings
from app.core.models import Decision, ParticipationOffer, SyndicationRequest, SyndicationResult
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance import tech_log
from app.governance.rules_engine import dscr as calc_dscr
from app.governance.rules_engine import loan_to_value, monthly_installment, sme_ratios
from app.tools.a2a_client import a2a_send
from app.workflows import data_access as sor
from mock_services.data import load


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


async def run_syndication(
    request: SyndicationRequest, request_id: str, on_event=None
) -> tuple[SyndicationResult, dict, dict]:
    """Arrange a syndication by delegating co-underwriting to a partner bank over A2A."""
    settings = get_settings()
    audit = get_audit_logger()
    tech: list[dict] = []

    def _emit(node: str, state: str, detail: str = "") -> None:
        if on_event:
            on_event(node, state, detail)

    audit.record(request_id, "syndication", "submitted", "portal",
                 redact_pii(f"{request.legal_name} ({request.company_id}) — sindikasi "
                            f"{request.requested_amount_idr:,} IDR — {request.purpose}"))

    safety = check_text(request.purpose)
    audit.record(request_id, "syndication", "content_safety", "governance",
                 f"safe={safety['safe']} provider={safety['provider']} categories={safety['categories']}")

    # ---- System-of-record facts + deterministic metrics ----
    company = sor.company(request.company_id)
    credit = sor.credit_company(request.company_id)
    statements = load("financials.json")[request.company_id]
    collateral = load("collateral.json").get(company.get("collateral_id"), {})
    ratios = sme_ratios(statements)
    grade = credit.get("risk_grade", "C")
    products = load("products.json")
    bns_rate = round(products["base_rate_pct"] + products["risk_spread_by_grade"].get(grade, 4.5), 2)
    installment = monthly_installment(request.requested_amount_idr, bns_rate, request.tenor_months)
    dscr_val = calc_dscr(ratios.get("operating_cashflow_idr", 0), installment * 12)
    ltv = loan_to_value(request.requested_amount_idr, collateral.get("appraised_value_idr", 0))

    cap = settings.bns_single_obligor_cap_idr
    bns_hold = min(request.requested_amount_idr, cap)
    syndicate_target = max(0, request.requested_amount_idr - bns_hold)

    async with financing_session(request_id, "syndication") as (runner, cost):
        # ---- Stage 1: Lead Arranger structures the syndication ----
        _emit("arranger", "active",
              f"🏛️ **Lead Arranger (BNS)** aktif · fasilitas {_rp(request.requested_amount_idr)} > "
              f"batas single-obligor {_rp(cap)} → BNS tahan {_rp(bns_hold)}, sindikasikan "
              f"{_rp(syndicate_target)}.")
        invitation = await runner.run(
            step="arrange", name="LeadArranger", instructions=LEAD_ARRANGER,
            prompt=(f"company_id={request.company_id}, sektor {request.sector}. Total fasilitas "
                    f"{request.requested_amount_idr} IDR, tenor {request.tenor_months} bln. BNS "
                    f"menahan {bns_hold} IDR (batas single-obligor {cap}), mensindikasikan "
                    f"{syndicate_target} IDR. Metrik: DSCR={dscr_val}, LTV={ltv}, grade={grade}, "
                    f"skor={credit.get('credit_score')}. Tujuan: {request.purpose}."),
        )
        audit.record(request_id, "syndication", "arrange", "LeadArranger",
                     redact_pii(invitation[:300]))
        _emit("arranger", "done",
              f"🏛️ **Lead Arranger** selesai · undangan sindikasi disusun untuk porsi "
              f"{_rp(syndicate_target)}.")

        # ---- Stage 2: A2A delegation to the partner bank's remote agent ----
        offer: ParticipationOffer | None = None
        a2a_meta: dict = {}
        if syndicate_target > 0:
            _emit("a2a", "active",
                  f"🔗 **A2A** aktif · menemukan **Agent Card** partner & mengirim `message/send` "
                  f"(co-underwrite {_rp(syndicate_target)}) ke {settings.partner_a2a_url}.")
            deal_payload = {
                "company_id": request.company_id,
                "legal_name": request.legal_name,
                "sector": request.sector,
                "requested_participation_idr": syndicate_target,
                "tenor_months": request.tenor_months,
                "dscr": dscr_val,
                "ltv": ltv,
                "credit_score": credit.get("credit_score", 0),
                "risk_grade": grade,
                "invitation": invitation[:400],
            }
            a2a_meta = await a2a_send(settings.partner_a2a_url, json.dumps(deal_payload, ensure_ascii=False))
            tech.append({
                "tool": "a2a:discover", "args": settings.partner_a2a_url,
                "result": f"card '{a2a_meta['card'].get('name')}' v{a2a_meta['card'].get('version')} "
                          f"skills={[s.get('id') for s in a2a_meta['card'].get('skills', [])]}",
                "ms": a2a_meta.get("card_ms", 0),
                "url": f"{settings.partner_a2a_url.rstrip('/')}/.well-known/agent-card.json",
            })
            tech.append({
                "tool": "a2a:message/send", "args": redact_pii(json.dumps(deal_payload)[:220]),
                "result": redact_pii(a2a_meta.get("reply_text", "")[:220]),
                "ms": a2a_meta.get("send_ms", 0), "url": a2a_meta.get("rpc_url"),
            })
            try:
                offer = ParticipationOffer(**json.loads(a2a_meta["reply_text"]))
            except Exception:
                offer = None
            audit.record(request_id, "syndication", "a2a_delegate",
                         f"partner:{a2a_meta['card'].get('provider', {}).get('organization', 'partner')}",
                         (f"decision={offer.decision.value} amount={offer.participation_amount_idr}"
                          if offer else "no valid offer"),
                         decision=(offer.decision.value if offer else None))
            _emit("partner", "active",
                  f"🤝 **Partner Bank (BMS)** — agen remote (organisasi lain) menilai via A2A…")
            if offer:
                _emit("partner", "done",
                      f"🤝 **Partner Bank (BMS)** menjawab: {offer.decision.value} · partisipasi "
                      f"{_rp(offer.participation_amount_idr)} @ {offer.indicative_rate_pct}% p.a.")
            else:
                _emit("partner", "done", "🤝 **Partner Bank** tidak memberi penawaran valid.")

        # ---- Stage 3: synthesise the final syndication structure ----
        partner_take = offer.participation_amount_idr if (offer and offer.decision == Decision.APPROVE) else 0
        arranged = bns_hold + partner_take
        shortfall = max(0, request.requested_amount_idr - arranged)
        if partner_take > 0:
            blended = round((bns_hold * bns_rate + partner_take * offer.indicative_rate_pct) / arranged, 2)
        else:
            blended = bns_rate
        decision = Decision.APPROVE if shortfall == 0 else Decision.REFER

        _emit("finalize", "active",
              f"🧾 **Sindikasi Final** aktif · BNS {_rp(bns_hold)} + Partner {_rp(partner_take)} = "
              f"{_rp(arranged)} (kekurangan {_rp(shortfall)}).")
        summary = await runner.run(
            step="finalize", name="SyndicationSynthesizer", instructions=SYNTHESIZER,
            prompt=(f"Total {request.requested_amount_idr} IDR. Porsi BNS {bns_hold} IDR @ {bns_rate}% "
                    f"p.a. Penawaran partner (via A2A): "
                    + (f"{offer.decision.value}, partisipasi {partner_take} IDR @ "
                       f"{offer.indicative_rate_pct}% p.a., syarat: {', '.join(offer.conditions) or '-'}."
                       if offer else "tidak ada.")
                    + f" Terkumpul {arranged} IDR, kekurangan {shortfall} IDR, blended rate {blended}%."),
        )
        result = SyndicationResult(
            company_id=request.company_id,
            total_amount_idr=request.requested_amount_idr,
            bns_amount_idr=bns_hold,
            syndicated_target_idr=syndicate_target,
            partner_offer=offer,
            arranged_amount_idr=arranged,
            shortfall_idr=shortfall,
            blended_rate_pct=blended,
            decision=decision,
            summary=summary,
        )
        audit.record(request_id, "syndication", "final", "SyndicationSynthesizer",
                     redact_pii(summary[:400]), decision=decision.value, tokens=cost.total_tokens)
        _emit("finalize", "done",
              f"🧾 **Sindikasi Final** selesai · {decision.value} · terkumpul {_rp(arranged)}/"
              f"{_rp(request.requested_amount_idr)} · blended {blended}%.")

    tech_log.save(request_id, tech + runner.tech)
    return result, cost.summary(), a2a_meta
