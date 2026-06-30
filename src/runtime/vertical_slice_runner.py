"""Runtime vertical slice -- threads the full EIOS chain end to end.

Observation -> IntelligenceAssessment -> OpportunityHypothesis -> InvestmentThesis
-> InvestmentAction -> PersonalizedAction -> ManualTradeTicket
-> (revalidate -> stale -> re-preview -> confirm) -> place (manual)
-> Fills -> reconcile -> feedback Observation.

This is the working manual-execution mechanics of the slice. It performs NO
investment reasoning of its own (the upstream layers are minimal placeholders);
it demonstrates the operational spine and the actuation gate. All timestamps are
explicit (deterministic) -- nothing reads the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from eios_core.canonical_objects import Observation
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

from reality_intelligence.source_observation import make_source_observation
from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis
from prometheus.investment_thesis import make_investment_thesis
from prometheus.investment_action import make_investment_action
from prometheus.position_lifecycle import position_state
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.personalized_action import make_personalized_action

from execution_manual.manual_trade_ticket import create_or_get_ticket, re_preview
from execution_manual.execution_checklist import (
    Thresholds,
    revalidate,
    confirm,
    place_order,
    mark_recorded,
    mark_reconciled,
)
from execution_manual.fill_record import make_fill, aggregate
from execution_manual.reconciliation import reconcile
from execution_manual.audit_trail import AuditTrail


@dataclass(frozen=True)
class SliceResult:
    observation: Any
    observations: Tuple[Any, ...]
    assessment: Any
    hypothesis: Any
    thesis: Any
    action: Any
    profile: Any
    personalized_action: Any
    ticket_preview1: Any
    revalidate_stale: Any
    ticket_preview2: Any
    revalidate_ok: Any
    ticket_confirmed: Any
    ticket_placed: Any
    fills: Tuple[Any, ...]
    aggregate: Any
    reconciliation: Any
    position: Any
    feedback_observation: Any
    audit_trail: Any
    registry: Dict[str, Any] = field(default_factory=dict)


def iren_source_observations(now):
    """The concrete, manually-supplied source material the IREN slice begins from.

    Five enriched Observations in the AI-infrastructure / data-center power domain.
    None carries a hand-fed assessment verdict -- each carries only *structured raw
    facts* (a metric move, an observed up/down/flat change, novelty / reliability
    tags), from which Reality Intelligence INFERS the typed signals, the direction,
    the significance, the confidence, the weak-signal set, and a contradiction note.

    The set is constructed so the inference produces: a strong improving
    readiness/capacity reading (metric value above prior), an improving readiness
    milestone, a WEAK constraint signal (an observed deterioration that is highly
    novel but only moderately reliable and uncorroborated), an improving adoption
    signal, and a deteriorating economic-inflection reading that contradicts the
    rest. The contradictory analyst note deliberately carries investment language
    ("buy rating", "price target") in its raw excerpt to prove the assessment never
    leaks it.
    """
    return (
        make_source_observation(
            source_type="earnings_excerpt", domain="ai-infrastructure", entity="IREN",
            excerpt=("Operating capacity expanded; contracted data-center power capacity "
                     "increased quarter over quarter, with AI cloud compute revenue ramping."),
            signal_type_hint="readiness",
            metric_name="contracted_power_capacity_mw", metric_value=240.0, prior_value=200.0,
            metric_unit="MW", as_of="2026-Q1",
            source_ref="IREN FY26 Q1 results", actor="analyst", now=now,
        ),
        make_source_observation(
            source_type="infrastructure_milestone", domain="ai-infrastructure", entity="IREN",
            excerpt=("Additional grid-connected megawatts energized at the Texas site; "
                     "power-secured buildout ahead of prior schedule."),
            observed_change="up", metric_name="energized_power_mw", metric_value=200.0,
            metric_unit="MW", as_of="2026-05",
            source_ref="company infrastructure update", actor="analyst", now=now,
        ),
        make_source_observation(
            source_type="capacity_power_demand_signal", domain="ai-infrastructure", entity="IREN",
            excerpt=("Available grid power is tightening as a binding constraint while demand "
                     "for power-secured data-center capacity keeps rising across the sector."),
            observed_change="down", novelty="high", source_reliability="moderate",
            as_of="2026-06", source_ref="sector capacity/power signal", actor="analyst", now=now,
        ),
        make_source_observation(
            source_type="news_excerpt", domain="ai-infrastructure", entity="IREN",
            excerpt=("Hyperscaler interest in contracted AI compute capacity is broadening; "
                     "adoption of power-secured colocation is accelerating."),
            observed_change="up", as_of="2026-06",
            source_ref="trade press", actor="analyst", now=now,
        ),
        make_source_observation(
            source_type="analyst_note_excerpt", domain="ai-infrastructure", entity="IREN",
            excerpt="Note flags financing and dilution risk and bitcoin-linked revenue volatility.",
            raw_excerpt=("Note flags financing and dilution risk and bitcoin-linked revenue "
                         "volatility; analysts reiterate a buy rating and raise the price target."),
            observed_change="down", source_reliability="moderate", as_of="2026-06",
            source_ref="sell-side note", actor="analyst", now=now,
        ),
    )


def run_iren_slice(
    instrument="IREN",
    intended_allocation=2000.0,
    limit_price_initial=10.00,
    price_t0=10.00,
    price_t1=10.40,
    t0=1_700_000_000.0,
    preview_ttl=120.0,
    market_move_tolerance=0.005,
    fills_plan=((100, 10.38), (92, 10.40)),
    broker_order_id="IBKR-12345",
    account="BROKER-ACCT-1",
    actor="user",
    venue="IBKR",
):
    thresholds = Thresholds(
        preview_ttl=preview_ttl, market_move_tolerance=market_move_tolerance
    )
    registry: Dict[str, Any] = {}
    audit = AuditTrail()

    # --- Reasoning chain: begins with concrete manually-supplied Observations,
    #     from which Reality Intelligence synthesises a real assessment ---------
    observations = iren_source_observations(t0)
    observation = observations[0]
    # No assessment_type override: Reality Intelligence (Tattva) INFERS it from the
    # enriched signals, and Genesis reasons opportunity from those signals -- not
    # from a hand-supplied label.
    assessment = generate_intelligence_assessment(
        observations,
        domain="ai-infrastructure",
        actor="reality-intelligence",
        now=t0,
    )
    hypothesis = generate_opportunity_hypothesis(
        [assessment],
        domain="ai-infrastructure",
        actor="genesis",
        now=t0,
    )
    thesis = make_investment_thesis(
        hypothesis,
        instrument=instrument,
        intended_allocation=intended_allocation,
        actor="prometheus",
        now=t0,
        rationale="enter a starter position",
    )
    action = make_investment_action(thesis, "enter", actor="prometheus", now=t0)
    profile = make_personal_investment_profile(account=account, actor="personal-cio", now=t0)
    personalized = make_personalized_action(action, profile, actor="personal-cio", now=t0, priority=1)

    grounding = {
        "investment_action_version": action.version,
        "thesis_version": thesis.version,
        "opportunity_version": hypothesis.version,
        "profile_version": profile.version,
    }

    audit.append(t0, "", "queue_item_presented", "personal-cio",
                 payload={"investment_action_id": action.id}, grounding_versions=grounding)

    # --- Ticket: create + first preview at t0 ------------------------------
    params = {
        "order_type": "limit",
        "limit_price": limit_price_initial,
        "time_in_force": "day",
        "venue": venue,
        "price": price_t0,
        "actor": actor,
        "queue_item_id": stable_id("QUE", action.id),
        "risk_warning": "limit order may not fill",
    }
    ticket1 = create_or_get_ticket(registry, action, personalized, params, now=t0)
    audit.append(t0, ticket1.id, "ticket_created", actor,
                 payload={"quantity": ticket1.quantity, "preview_hash": ticket1.preview_hash},
                 grounding_versions=grounding)
    audit.append(t0, ticket1.id, "previewed", actor,
                 payload={"quantity": ticket1.quantity, "preview_hash": ticket1.preview_hash,
                          "price": price_t0})

    # --- Revalidate at t1 (stale + market moved) -> return to preview ------
    t1 = t0 + preview_ttl + 60.0
    ctx = {
        "action_current": True,
        "account_ok": True,
        "tradable": True,
        "market_open": True,
        "execution_enabled": True,
    }
    revalidate_stale = revalidate(ticket1, now=t1, current_price=price_t1, ctx=ctx, thresholds=thresholds)
    audit.append(t1, ticket1.id, "stale_detected", "system",
                 payload={"reasons": list(revalidate_stale.reasons), "current_price": price_t1})
    audit.append(t1, ticket1.id, "returned_to_preview", "system",
                 payload={"reasons": list(revalidate_stale.reasons)})

    # --- Re-preview at the new price (qty re-derived) ----------------------
    ticket2 = re_preview(registry, ticket1, price=price_t1, now=t1, limit_price=price_t1)
    audit.append(t1, ticket2.id, "previewed", actor,
                 payload={"quantity": ticket2.quantity, "preview_hash": ticket2.preview_hash,
                          "price": price_t1})

    # --- Revalidate the fresh preview -> ok --------------------------------
    revalidate_ok = revalidate(ticket2, now=t1, current_price=price_t1, ctx=ctx, thresholds=thresholds)
    audit.append(t1, ticket2.id, "checklist_completed", actor,
                 payload={"status": revalidate_ok.status})

    # --- Confirm bound to the NEW preview hash -----------------------------
    confirmed = confirm(ticket2, ticket2.preview_hash)
    registry[confirmed.id] = confirmed
    audit.append(t1, confirmed.id, "confirmed", actor,
                 payload={"preview_hash": confirmed.preview_hash})

    # --- User places the trade manually (records broker_order_id) ----------
    placed_at = t1 + 30.0
    placed = place_order(registry, confirmed, broker_order_id=broker_order_id, placed_at=placed_at)
    audit.append(placed_at, placed.id, "placed_by_user", actor,
                 payload={"broker_order_id": placed.broker_order_id, "placed_at": placed.placed_at},
                 grounding_versions=grounding)

    # --- Fills (Observations of reality) -----------------------------------
    fills = []
    fill_time = placed_at
    for idx, (qty, px) in enumerate(fills_plan):
        fill_time = fill_time + 30.0
        fill = make_fill(placed, quantity=qty, price=px, time=fill_time, actor=actor, index=idx)
        fills.append(fill)
        cumulative = sum(f.quantity for f in fills)
        event = "fill_recorded" if cumulative >= placed.quantity else "partial_fill"
        audit.append(fill_time, placed.id, event, actor,
                     payload={"quantity": qty, "price": px, "time": fill_time})
    fills = tuple(fills)

    agg = aggregate(fills, placed.quantity)
    recorded = mark_recorded(registry, placed)

    # --- Reconcile ---------------------------------------------------------
    broker_record = {
        "broker_order_id": broker_order_id,
        "acknowledged": True,
        "filled_quantity": agg.cumulative_filled,
    }
    expected = {
        "position_quantity": placed.quantity,
        "outcome_recorded": True,
    }
    reconciliation = reconcile(recorded, fills, broker_record, expected)
    reconciled = mark_reconciled(registry, recorded)
    audit.append(fill_time, reconciled.id, "reconciled", "system",
                 payload={"all_reconciled": reconciliation.all_reconciled})

    # --- Derived position + feedback Observation up the chain --------------
    position = position_state([action], fills)
    feedback_sources = (placed.ref("ManualTradeTicket"),) + tuple(f.ref("Fill") for f in fills)
    feedback = Observation(
        id=stable_id("OBS", "feedback", placed.id),
        version=1,
        provenance=make_provenance(
            actor="execution", created_at=iso_from_epoch(fill_time), sources=feedback_sources
        ),
        content={
            "outcome": agg.outcome,
            "average_price": agg.average_price,
            "filled": agg.cumulative_filled,
            "reconciled": reconciliation.all_reconciled,
        },
    )

    return SliceResult(
        observation=observation,
        observations=observations,
        assessment=assessment,
        hypothesis=hypothesis,
        thesis=thesis,
        action=action,
        profile=profile,
        personalized_action=personalized,
        ticket_preview1=ticket1,
        revalidate_stale=revalidate_stale,
        ticket_preview2=ticket2,
        revalidate_ok=revalidate_ok,
        ticket_confirmed=confirmed,
        ticket_placed=placed,
        fills=fills,
        aggregate=agg,
        reconciliation=reconciliation,
        position=position,
        feedback_observation=feedback,
        audit_trail=audit,
        registry=registry,
    )
