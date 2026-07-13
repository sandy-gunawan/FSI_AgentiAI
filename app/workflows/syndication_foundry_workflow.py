"""Use Case 8 (v2) — Syndicated / Co-Financing with **Foundry-hosted agents**.

Same A2A (Agent2Agent) cross-organisation delegation + governance as v1
``run_syndication``: BNS's Lead Arranger structures the deal, delegates co-underwriting
to an INDEPENDENT partner-bank agent over the open A2A protocol, then synthesises the
final structure. The Lead Arranger and Synthesizer are persistent Foundry agents; the
A2A call to the partner is unchanged. Additive — v1 untouched. Returns a plain dict.
"""
from __future__ import annotations

import asyncio
import json

from app.agents.shared.foundry_runner import foundry_session
from app.core.config import get_settings
from app.core.models import SyndicationRequest
from app.governance import tech_log
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import check_text, redact_pii
from app.governance.rules_engine import dscr as calc_dscr
from app.governance.rules_engine import loan_to_value, monthly_installment, sme_ratios
from app.tools.a2a_client import a2a_send
from app.workflows import data_access as sor
from mock_services.data import load


def _rp(x) -> str:
    return f"Rp {int(x):,}".replace(",", ".")


async def run_syndication_foundry(
    request: SyndicationRequest, request_id: str, on_event=None,
    via_apim: bool | None = None,
) -> tuple[dict, dict, dict]:
    """Arrange a syndication via A2A delegation, using Foundry agents. Returns (result, cost, a2a_meta)."""
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

    offer: dict | None = None
    a2a_meta: dict = {}

    with foundry_session(request_id, "syndication", via_apim) as (runner, cost):
        def _call(step, name, agent_key, prompt):
            return asyncio.to_thread(runner.run, step=step, name=name, agent_key=agent_key, prompt=prompt)

        # ---- Stage 1: Lead Arranger structures the syndication (Foundry) ----
        _emit("arranger", "active",
              f"🏛️ **Lead Arranger (BNS, agen Foundry)** · fasilitas {_rp(request.requested_amount_idr)} > "
              f"batas single-obligor {_rp(cap)} → BNS tahan {_rp(bns_hold)}, sindikasikan "
              f"{_rp(syndicate_target)}.")
        invitation = await _call("arrange", "LeadArranger", "syndication-lead-arranger",
                                 f"company_id={request.company_id}, sektor {request.sector}. Total "
                                 f"fasilitas {request.requested_amount_idr} IDR, tenor {request.tenor_months} "
                                 f"bln. BNS menahan {bns_hold} IDR (batas single-obligor {cap}), "
                                 f"mensindikasikan {syndicate_target} IDR. Metrik: DSCR={dscr_val}, LTV={ltv}, "
                                 f"grade={grade}, skor={credit.get('credit_score')}. Tujuan: {request.purpose}. "
                                 f"Susun undangan sindikasi.")
        audit.record(request_id, "syndication", "arrange", "foundry:syndication-lead-arranger",
                     redact_pii(invitation[:300]))
        _emit("arranger", "done",
              f"🏛️ **Lead Arranger** selesai · undangan untuk porsi {_rp(syndicate_target)}.")

        # ---- Stage 2: A2A delegation to the partner bank's remote agent (unchanged) ----
        if syndicate_target > 0:
            _emit("a2a", "active",
                  f"🔗 **A2A** · menemukan **Agent Card** partner & mengirim `message/send` "
                  f"(co-underwrite {_rp(syndicate_target)}) ke {settings.partner_a2a_url}.")
            deal_payload = {
                "company_id": request.company_id, "legal_name": request.legal_name,
                "sector": request.sector, "requested_participation_idr": syndicate_target,
                "tenor_months": request.tenor_months, "dscr": dscr_val, "ltv": ltv,
                "credit_score": credit.get("credit_score", 0), "risk_grade": grade,
                "invitation": invitation[:400],
            }
            try:
                a2a_meta = await a2a_send(settings.partner_a2a_url,
                                          json.dumps(deal_payload, ensure_ascii=False))
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
                    offer = json.loads(a2a_meta["reply_text"])
                except Exception:
                    offer = None
                audit.record(request_id, "syndication", "a2a_delegate",
                             f"partner:{a2a_meta['card'].get('provider', {}).get('organization', 'partner')}",
                             (f"decision={offer.get('decision')} amount={offer.get('participation_amount_idr')}"
                              if offer else "no valid offer"),
                             decision=(offer.get("decision") if offer else None))
                _emit("partner", "active", "🤝 **Partner Bank (BMS)** — agen remote menilai via A2A…")
                if offer:
                    _emit("partner", "done",
                          f"🤝 **Partner Bank (BMS)** menjawab: {offer.get('decision')} · partisipasi "
                          f"{_rp(offer.get('participation_amount_idr', 0))} @ "
                          f"{offer.get('indicative_rate_pct')}% p.a.")
                else:
                    _emit("partner", "done", "🤝 **Partner Bank** tidak memberi penawaran valid.")
            except Exception as exc:  # partner service unreachable → degrade gracefully
                offer = None
                a2a_meta = {}
                audit.record(request_id, "syndication", "a2a_error", "partner",
                             f"A2A gagal: {str(exc)[:160]}")
                _emit("partner", "done",
                      f"🤝 **Partner Bank** tidak dapat dihubungi via A2A ({str(exc)[:80]}).")

        # ---- Stage 3: synthesise final structure (Foundry) ----
        partner_approved = bool(offer and str(offer.get("decision", "")).upper() == "APPROVE")
        partner_take = int(offer.get("participation_amount_idr", 0)) if partner_approved else 0
        partner_rate = float(offer.get("indicative_rate_pct", bns_rate)) if partner_approved else bns_rate
        arranged = bns_hold + partner_take
        shortfall = max(0, request.requested_amount_idr - arranged)
        blended = round((bns_hold * bns_rate + partner_take * partner_rate) / arranged, 2) if arranged else bns_rate
        decision = "APPROVE" if shortfall == 0 else "REFER"

        _emit("finalize", "active",
              f"🧾 **Sindikasi Final (agen Foundry)** · BNS {_rp(bns_hold)} + Partner {_rp(partner_take)} = "
              f"{_rp(arranged)} (kekurangan {_rp(shortfall)}).")
        summary = await _call("finalize", "SyndicationSynthesizer", "syndication-synthesizer",
                              f"Total {request.requested_amount_idr} IDR. Porsi BNS {bns_hold} IDR @ "
                              f"{bns_rate}% p.a. Penawaran partner (via A2A): "
                              + (f"{offer.get('decision')}, partisipasi {partner_take} IDR @ "
                                 f"{partner_rate}% p.a., syarat: "
                                 f"{', '.join(offer.get('conditions', [])) or '-'}." if offer else "tidak ada.")
                              + f" Terkumpul {arranged} IDR, kekurangan {shortfall} IDR, blended {blended}%.")
        audit.record(request_id, "syndication", "final", "foundry:syndication-synthesizer",
                     redact_pii(summary[:400]), decision=decision, tokens=cost.total_tokens)
        _emit("finalize", "done",
              f"🧾 **Sindikasi Final** selesai · {decision} · terkumpul {_rp(arranged)}/"
              f"{_rp(request.requested_amount_idr)} · blended {blended}%.")

    tech_log.save(request_id, tech + runner.tech)
    result = {
        "decision": decision,
        "total_amount_idr": request.requested_amount_idr,
        "bns_amount_idr": bns_hold,
        "syndicated_target_idr": syndicate_target,
        "partner_offer": offer,
        "arranged_amount_idr": arranged,
        "shortfall_idr": shortfall,
        "blended_rate_pct": blended,
        "invitation": invitation,
        "summary": summary,
    }
    return result, cost.summary(), a2a_meta
