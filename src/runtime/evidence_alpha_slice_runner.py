"""Evidence -> Alpha end-to-end vertical slice (IMPLEMENTATION-009G).

A deterministic, fixture-backed END-TO-END slice that starts at the
evidence-ingestion layer (009E/F) and runs FORWARD through the EXISTING alpha
pipeline, proving that INGESTED evidence -- not hand-authored assessment inputs --
can drive the whole reasoning chain:

    fixtures (SEC / FMP / yfinance)
      -> run_fixture_ingestion_slice  (parse -> arbitrate -> map -> Tattva)
      -> IntelligenceAssessment (IA)
      -> generate_opportunity_hypothesis          (Sphurana / Genesis)
      -> generate_investment_thesis               (Nivesha / Prometheus gauntlet)
      -> generate_investment_action               (Investment Action)
      -> generate_personalized_action             (Saarathi / Personal CIO)
      -> make_manual_execution_intent             (Kriya user-sized intent)
      -> create_or_get_ticket                     (ticket PREVIEW only)
      -> build_alpha_decision_cockpit_view        (Infinite Canvas read-model)
      -> render_cockpit_html                       (optional static HTML)

Discipline this module keeps:

* It CALLS only EXISTING constructors/runners. It adds NO new alpha logic, NO new
  scoring, NO formula changes. Every reasoning object comes from the existing
  layer's own constructor -- this module only orchestrates and reports provenance.
* NO network, NO live calls, NO API keys / secrets, NO scheduler / background
  jobs, NO broker automation. Everything is a pure function of already-loaded
  fixture dicts and an explicit ``now`` -- two runs produce byte-identical ids.
* The ingested IA drives the OpportunityHypothesis ONLY through the assessment's
  inferred SIGNALS (which already EXCLUDE factual OHLCV/profile/ownership/quote
  observations per 009F). Factual observations are NEVER passed as extra signal
  evidence.
* The DiligenceInputs and portfolio remain hand-fed fixtures (that is expected at
  this stage): ingestion drives the Opportunity Hypothesis, not yet the
  price/financial diligence inputs.
* The slice goes to the ticket PREVIEW and the cockpit. It NEVER confirms, places,
  fills, or reconciles a ticket -- ``broker_order_id`` stays ``None`` and the
  ticket state is ``previewed``.
* Nothing here forces a specific investability. The thesis / action / personalized
  status is whatever the ingested Opportunity Hypothesis + hand-fed DiligenceInputs
  honestly yield.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from eios_core.ids import stable_id

from evidence_ingestion.vertical_slice import (
    run_fixture_ingestion_slice,
    IngestionVerticalSliceResult,
)

from genesis.opportunity_hypothesis import generate_opportunity_hypothesis
from prometheus.investment_thesis import generate_investment_thesis
from prometheus.investment_action import generate_investment_action
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.personalized_action import generate_personalized_action
from execution_manual.manual_execution_intent import make_manual_execution_intent
from execution_manual.manual_trade_ticket import create_or_get_ticket
from infinite_canvas.cockpit import build_alpha_decision_cockpit_view
from infinite_canvas.render_html import render_cockpit_html

# The hand-fed diligence / portfolio fixtures reused verbatim from the 009D slice.
from runtime.vertical_slice_runner import (
    iren_diligence_inputs,
    iren_portfolio_snapshot,
)


@dataclass(frozen=True)
class EvidenceAlphaSliceResult:
    """The deterministic outcome of one evidence -> alpha end-to-end slice.

    Every reasoning object is produced by the EXISTING pipeline constructor; this
    result only carries them together with a stitched provenance chain and a
    boundary audit. Downstream objects are ``None`` when the ingestion produced no
    signal-bearing Intelligence Assessment (factual/deferred-only input).
    """

    subject: str = ""
    ingestion_result: Optional[IngestionVerticalSliceResult] = None
    observations: Tuple[Any, ...] = ()
    intelligence_assessment: Optional[Any] = None
    opportunity_hypothesis: Optional[Any] = None
    investment_thesis: Optional[Any] = None
    investment_action: Optional[Any] = None
    personalized_action: Optional[Any] = None
    manual_execution_intent: Optional[Any] = None
    manual_trade_ticket: Optional[Any] = None
    cockpit_view: Optional[Any] = None
    rendered_html: Optional[str] = None
    conflict_warnings: Tuple[str, ...] = ()
    deferred_records: Tuple[Any, ...] = ()
    data_gaps: Tuple[Tuple[str, str], ...] = ()
    provenance_chain: Dict[str, Any] = field(default_factory=dict)
    boundary_audit_summary: Dict[str, Any] = field(default_factory=dict)


def _downstream_provenance(
    *, intelligence_assessment, opportunity_hypothesis, investment_thesis,
    investment_action, personalized_action, manual_execution_intent, ticket,
) -> Tuple[Dict[str, Any], ...]:
    """The ordered downstream binding refs IA -> OH -> ... -> Ticket.

    Each entry names the producing object's (id, version) and the upstream id it is
    bound to -- enough to audit that every link is a real content-addressed binding
    (not a re-computation), from the assessment through to the ticket preview.
    """
    links = []
    if opportunity_hypothesis is not None:
        links.append({
            "stage": "IntelligenceAssessment->OpportunityHypothesis",
            "object_id": opportunity_hypothesis.id,
            "object_version": opportunity_hypothesis.version,
            "bound_to": tuple(opportunity_hypothesis.triggering_assessment_ids),
            "ref": opportunity_hypothesis.ref("OpportunityHypothesis"),
        })
    if investment_thesis is not None:
        links.append({
            "stage": "OpportunityHypothesis->InvestmentThesis",
            "object_id": investment_thesis.id,
            "object_version": investment_thesis.version,
            "bound_to": (investment_thesis.opportunity_id,),
            "ref": investment_thesis.ref("InvestmentThesis"),
        })
    if investment_action is not None:
        links.append({
            "stage": "InvestmentThesis->InvestmentAction",
            "object_id": investment_action.id,
            "object_version": investment_action.version,
            "bound_to": (investment_action.source_thesis_id,),
            "ref": investment_action.ref("InvestmentAction"),
        })
    if personalized_action is not None:
        links.append({
            "stage": "InvestmentAction->PersonalizedAction",
            "object_id": personalized_action.id,
            "object_version": personalized_action.version,
            "bound_to": (personalized_action.source_action_id,),
            "ref": personalized_action.ref("PersonalizedAction"),
        })
    if manual_execution_intent is not None:
        links.append({
            "stage": "PersonalizedAction->ManualExecutionIntent",
            "object_id": manual_execution_intent.id,
            "object_version": manual_execution_intent.version,
            "bound_to": (manual_execution_intent.source_personalized_action_id,),
            "ref": manual_execution_intent.ref("ManualExecutionIntent"),
        })
    if ticket is not None:
        links.append({
            "stage": "ManualExecutionIntent->ManualTradeTicket",
            "object_id": ticket.id,
            "object_version": ticket.version,
            "bound_to": (ticket.cio_decision_record_id,),
            "ref": ticket.ref("ManualTradeTicket"),
        })
    return tuple(links)


def _overridden_facts(ingestion: IngestionVerticalSliceResult) -> Tuple[Dict[str, str], ...]:
    """The overridden financial facts (lost arbitration), from the ingestion result."""
    out = []
    for rec, reason in zip(ingestion.deferred_records, ingestion.deferred_reasons):
        if str(reason).startswith("overridden"):
            src = rec.source.source_name if rec.source is not None else ""
            out.append({
                "normalized_type": rec.normalized_type,
                "source_name": src,
                "source_authority": rec.source_authority,
                "reason": reason,
            })
    return tuple(out)


def run_evidence_alpha_slice(
    *,
    subject: str = "IREN",
    domain: str = "ai-infrastructure",
    now: float,
    sec_submissions: Any = None,
    sec_companyfacts: Any = None,
    fmp_income_statement: Any = None,
    fmp_profile: Any = None,
    fmp_ohlcv: Any = None,
    fmp_news: Any = None,
    fmp_ownership: Any = None,
    yf_history: Any = None,
    yf_quote: Any = None,
    yf_quote_as_of: str = "",
    diligence_inputs: Any = None,
    profile: Any = None,
    portfolio: Any = None,
    user_selected_allocation_amount: float = 2000.0,
    execution_side: str = "open_candidate",
    render_html: bool = False,
    actor: str = "evidence-alpha-slice",
) -> EvidenceAlphaSliceResult:
    """Run the evidence -> alpha end-to-end slice deterministically from fixtures.

    Calls only EXISTING constructors/runners; adds no reasoning of its own. If the
    ingestion produces no signal-bearing Intelligence Assessment (factual/deferred
    input only), the slice returns early with the ingestion result and ``None``
    downstream objects plus a boundary-audit note.
    """
    # --- A. Ingestion (existing 009E/F slice) --------------------------------
    ingestion = run_fixture_ingestion_slice(
        subject=subject,
        domain=domain,
        sec_submissions=sec_submissions,
        sec_companyfacts=sec_companyfacts,
        fmp_income_statement=fmp_income_statement,
        fmp_profile=fmp_profile,
        fmp_ohlcv=fmp_ohlcv,
        fmp_news=fmp_news,
        fmp_ownership=fmp_ownership,
        yf_history=yf_history,
        yf_quote=yf_quote,
        yf_quote_as_of=yf_quote_as_of,
        now=now,
        actor=actor,
    )
    ia = ingestion.intelligence_assessment

    base_boundary = {
        "manual_execution_only": True,
        "ticket_state": None,
        "broker_order_id": None,
        "no_broker_automation": True,
        "factual_partition_preserved": True,
        "source_hierarchy": "SEC>FMP>yf",
        "stops_before": None,
    }
    base_provenance = {
        "ingestion": ingestion.provenance_chain,
        "source_traces": (ingestion.provenance_chain.traces
                          if ingestion.provenance_chain is not None else ()),
        "conflict_winners": ingestion.resolved_facts,
        "overridden_facts": _overridden_facts(ingestion),
        "downstream": (),
        "cockpit": (),
    }

    # An IA with no signals cannot honestly drive an opportunity hypothesis -- the
    # signal-bearing chain does not start from raw facts alone. Stop cleanly.
    if ia is None or len(ia.signals) == 0:
        boundary = dict(base_boundary)
        boundary["stops_before"] = "opportunity_hypothesis"
        boundary["note"] = (
            "ingestion produced no signal-bearing Intelligence Assessment "
            "(factual/deferred input only); no opportunity hypothesis created"
        )
        boundary["factual_partition_preserved"] = True
        return EvidenceAlphaSliceResult(
            subject=subject,
            ingestion_result=ingestion,
            observations=ingestion.observations,
            intelligence_assessment=ia,
            conflict_warnings=ingestion.conflict_warnings,
            deferred_records=ingestion.deferred_records,
            data_gaps=ingestion.data_gaps,
            provenance_chain=base_provenance,
            boundary_audit_summary=boundary,
        )

    # --- B. Sphurana / Genesis -- driven ONLY by the IA's inferred signals ---
    oh = generate_opportunity_hypothesis([ia], domain=domain, actor=actor, now=now)

    # --- C. Nivesha / Prometheus gauntlet (hand-fed DiligenceInputs) ---------
    thesis = generate_investment_thesis(
        oh, diligence_inputs or iren_diligence_inputs(domain=domain),
        actor=actor, now=now,
    )

    # --- D. Investment Action / Saarathi / Kriya (preview only) --------------
    action = generate_investment_action(thesis, actor=actor, now=now)

    profile = profile or make_personal_investment_profile(
        account="BROKER-ACCT-1", actor=actor, now=now)
    portfolio = portfolio or iren_portfolio_snapshot(account="BROKER-ACCT-1", now=now)
    personalized = generate_personalized_action(
        thesis, action, profile, portfolio, actor=actor, now=now)

    # The USER's explicit chosen size is REQUIRED here (Kriya boundary): the intent
    # constructor raises ValueError without a positive user-selected amount.
    intent = make_manual_execution_intent(
        personalized,
        selected_instrument=thesis.security_or_instrument_mapping or subject,
        user_selected_allocation_amount=user_selected_allocation_amount,
        execution_side=execution_side,
        actor="user", now=now,
    )

    # PREVIEW ONLY -- create the ticket and stop. No confirm / place / fill /
    # reconcile; broker_order_id stays None; state stays "previewed".
    ticket_params = {
        "order_type": "limit",
        "limit_price": None,
        "time_in_force": "day",
        "venue": "MANUAL",
        "price": float(user_selected_allocation_amount),
        "actor": "user",
        "queue_item_id": stable_id("QUE", action.id),
        "risk_warning": "manual execution only; preview does not place an order",
    }
    ticket = create_or_get_ticket({}, intent, ticket_params, now=now)

    # --- E. Infinite Canvas cockpit + optional static HTML -------------------
    cockpit = build_alpha_decision_cockpit_view(
        opportunity_hypothesis=oh,
        investment_thesis=thesis,
        investment_action=action,
        personalized_action=personalized,
        manual_execution_intent=intent,
        intelligence_assessment=ia,
        observations=ingestion.observations,
        ticket=ticket,
    )
    html = render_cockpit_html(cockpit) if render_html else None

    # --- Provenance stitch + boundary audit ----------------------------------
    provenance = dict(base_provenance)
    provenance["downstream"] = _downstream_provenance(
        intelligence_assessment=ia,
        opportunity_hypothesis=oh,
        investment_thesis=thesis,
        investment_action=action,
        personalized_action=personalized,
        manual_execution_intent=intent,
        ticket=ticket,
    )
    provenance["cockpit"] = cockpit.provenance_chain

    boundary = dict(base_boundary)
    boundary["ticket_state"] = ticket.state
    boundary["broker_order_id"] = ticket.broker_order_id
    boundary["stops_before"] = None  # slice completes at ticket preview + cockpit

    return EvidenceAlphaSliceResult(
        subject=subject,
        ingestion_result=ingestion,
        observations=ingestion.observations,
        intelligence_assessment=ia,
        opportunity_hypothesis=oh,
        investment_thesis=thesis,
        investment_action=action,
        personalized_action=personalized,
        manual_execution_intent=intent,
        manual_trade_ticket=ticket,
        cockpit_view=cockpit,
        rendered_html=html,
        conflict_warnings=ingestion.conflict_warnings,
        deferred_records=ingestion.deferred_records,
        data_gaps=ingestion.data_gaps,
        provenance_chain=provenance,
        boundary_audit_summary=boundary,
    )
