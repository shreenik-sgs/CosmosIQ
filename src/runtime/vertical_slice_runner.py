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

from reality_intelligence.intelligence_assessment import make_intelligence_assessment
from genesis.opportunity_hypothesis import make_opportunity_hypothesis
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

    # --- Reasoning chain (minimal placeholder models) ----------------------
    observation = Observation(
        id=stable_id("OBS", instrument, "signal"),
        version=1,
        provenance=make_provenance(actor="reality-intelligence", created_at=iso_from_epoch(t0)),
        content={"instrument": instrument, "signal": "datacenter/AI capacity pivot"},
    )
    assessment = make_intelligence_assessment(
        [observation],
        subject=instrument,
        assessment="structurally improving capacity economics",
        actor="reality-intelligence",
        now=t0,
        confidence=0.7,
    )
    hypothesis = make_opportunity_hypothesis(
        assessment,
        subject=instrument,
        hypothesis="re-rating on AI datacenter buildout",
        actor="genesis",
        now=t0,
        confidence=0.6,
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
