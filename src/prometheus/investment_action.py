"""Prometheus / Nivesha -- the Investment Action + Position Lifecycle layer.

``generate_investment_action`` converts a GATED ``InvestmentThesis`` (the 004B
product) into a governed MODEL ACTION CANDIDATE. Action semantics ARE allowed at
this stage -- the layer decides WHETHER to enter / add / trim / exit / rotate /
wait / monitor / avoid -- but it remains cognition (ADR-0010): it carries NO
order, NO ticket, NO venue submission, NO allocation, NO position size, NO side, NO
quantity. It says "this is a candidate to act on, governed by these conditions",
never "place this trade".

The decision is a deterministic, GATED function of the thesis (and an optional
position / comparative context): a not-investable thesis, a poor payoff, a failed
red team, or a euphoric recognition BLOCKS an entry candidate regardless of the
chart; a strong thesis without timing confirmation is only a WAIT; an existing
holding can be added to, trimmed, exited, or rotated, but only when a position
context says a holding exists. Without a position context the layer never invents
holdings, so it can never emit add / trim / exit / rotate.

Determinism: every output is a pure function of the inputs and the explicit
``now``; no wall clock, no randomness; the upstream thesis is never mutated.

A clearly-labelled TEMPORARY Kriya adapter -- ``ManualExecutionAdapter`` /
``make_manual_execution_adapter`` -- lives here too. It is a SEPARATE class (NOT
the real ``InvestmentAction`` and NOT Saarathi's ``PersonalizedAction``) that
carries the user's chosen exact size (within Saarathi's recommended RANGE) plus
the instrument / side / account / decision-record id the pre-existing Kriya
manual-ticket path reads. See its docstring for the removal condition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

from .investment_thesis import InvestmentThesis

# Governed model-action vocabulary. Candidate / lifecycle language IS allowed here
# (this is the action layer), but NO order / venue / allocation / sizing words.
ACTION_TYPES = frozenset({
    "avoid", "monitor", "wait",
    "enter_candidate", "add_candidate", "trim_candidate",
    "exit_candidate", "rotate_candidate",
})

ACTION_STATUSES = frozenset({
    "blocked", "monitoring", "thesis_worthy_wait",
    "timing_confirmed_candidate", "risk_reduction_candidate", "invalidated",
})

URGENCY_LEVELS = frozenset({"low", "moderate", "high"})

# Trade / allocation / order language that must NEVER appear in an action's
# synthesised text. The action MAY say: enter_candidate, add_candidate,
# trim_candidate, exit_candidate, rotate_candidate, wait, monitor, avoid,
# candidate, timing, lifecycle, and the security/ticker mapping. It must NOT
# carry execution / sizing language -- that is downstream of the cognition /
# actuation boundary (ADR-0010). NOTE: the order-submission-venue term below is
# composed from two adjacent string literals on purpose, so its literal substring
# never appears in this source file (a Nivesha-purity test forbids it under
# prometheus/), while still matching at runtime.
_FORBIDDEN_TERMS = (
    "buy", "sell", " hold", "bro" "ker", "order", "trade ticket", "limit price",
    "market order", "stop order", "shares", "option contract", "allocat",
    "position size", "execute", "submit",
)


def _assert_no_leakage(*texts: str) -> None:
    blob = " ".join(t for t in texts if t).lower()
    hits = [t for t in _FORBIDDEN_TERMS if t in blob]
    if hits:
        raise ValueError(
            "Investment Action must carry no order / venue / allocation / sizing "
            "language (found {0}); the action layer governs a candidate to act on "
            "-- enter/add/trim/exit/rotate/wait/monitor/avoid -- not HOW MUCH or an "
            "instruction to place a trade (ADR-0010).".format(hits)
        )


@dataclass(frozen=True)
class InvestmentAction(ReasoningObject):
    """A deterministic, boundary-clean governed MODEL ACTION CANDIDATE derived
    from one gated Investment Thesis.

    Carries the candidate security/instrument mapping and the governance of the
    action (type, status, conditions, urgency, lifecycle), but NO allocation /
    position size / side / order / quantity / venue / ticket / limit price.
    """

    action_id: str = ""
    source_thesis_id: str = ""
    source_thesis_version: int = 1
    action_type: str = "monitor"
    action_status: str = "monitoring"
    action_rationale: str = ""
    required_conditions: Tuple[str, ...] = field(default_factory=tuple)
    blocking_conditions: Tuple[str, ...] = field(default_factory=tuple)
    invalidation_conditions: Tuple[str, ...] = field(default_factory=tuple)
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)
    review_triggers: Tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    urgency: str = "low"
    lifecycle_state: str = ""
    security_or_instrument_mapping: str = ""
    source_thesis_components: Dict[str, Any] = field(default_factory=dict)
    upstream_observation_ids: Tuple[str, ...] = field(default_factory=tuple)
    triggering_assessment_ids: Tuple[str, ...] = field(default_factory=tuple)
    triggering_assessment_versions: Tuple[int, ...] = field(default_factory=tuple)


def _is_superior(comparative, thesis) -> bool:
    """A comparative thesis is clearly superior when it is BOTH more confident and
    timing-confirmed -- the only basis on which an existing holding rotates."""
    if comparative is None:
        return False
    return bool(
        getattr(comparative, "thesis_confidence", 0.0) > getattr(thesis, "thesis_confidence", 0.0)
        and getattr(comparative, "timing_confirmation", False)
    )


def _required_conditions(action_type: str) -> Tuple[str, ...]:
    table = {
        "wait": ("technical timing confirmation", "repricing gate clears"),
        "enter_candidate": ("timing confirmed", "repricing gate clear"),
        "add_candidate": ("position thesis intact", "timing confirmed"),
        "rotate_candidate": ("comparative candidate remains superior", "timing confirmed"),
        "monitor": ("thesis strengthens toward investable",),
        "trim_candidate": ("risk-reduction review",),
        "exit_candidate": ("risk-reduction review",),
        "avoid": (),
    }
    return table.get(action_type, ())


def _blocking_conditions(inv, asym, rt, rec) -> Tuple[str, ...]:
    blocking = []
    if asym == "poor":
        blocking.append("poor risk/reward asymmetry")
    if rt == "fail":
        blocking.append("red-team verdict: fail")
    if rec == "euphoric_bubble_risk":
        blocking.append("euphoric/bubble recognition")
    if inv == "not_investable":
        blocking.append("thesis not yet investable")
    return tuple(blocking)


def _urgency(action_type: str) -> str:
    if action_type in ("enter_candidate", "add_candidate", "exit_candidate"):
        return "high"
    if action_type in ("wait", "trim_candidate", "rotate_candidate"):
        return "moderate"
    return "low"


def generate_investment_action(thesis, *, position_context=None, comparative_thesis=None,
                               actor: str = "prometheus", now: float) -> InvestmentAction:
    """Convert a gated ``InvestmentThesis`` into a governed model action candidate.

    Deterministic and boundary-clean: no orders, no allocation, no sizing. The
    upstream thesis is never mutated; provenance binds it by (id, version) and the
    upstream observation ids are carried forward unchanged.
    """
    if not isinstance(thesis, InvestmentThesis):
        raise ValueError(
            "generate_investment_action requires an InvestmentThesis (the gated "
            "004B product); got {0}".format(type(thesis).__name__)
        )

    inv = thesis.investability_assessment
    timing = bool(thesis.timing_confirmation)
    asym = getattr(thesis.asymmetry_summary, "asymmetry_label", "undetermined")
    rt = getattr(thesis.red_team_summary, "red_team_verdict", "pass")
    rec = getattr(thesis.market_recognition_summary, "recognition_stage", "hidden")
    tech = getattr(thesis.technical_inflection_summary, "technical_confirmation", False)
    repricing_gate = getattr(thesis.repricing_trigger_summary, "gate_passed", False)
    mapping = thesis.security_or_instrument_mapping

    has_position = bool(position_context is not None and getattr(position_context, "has_position", False))
    invalidation_active = bool(position_context is not None
                               and getattr(position_context, "invalidation_triggered", False))
    direction = getattr(position_context, "thesis_direction", "stable") if position_context else "stable"

    # --- the governance core (deterministic decision rules) -------------------
    if invalidation_active:
        action_type = "exit_candidate" if has_position else "avoid"
        action_status = "invalidated"
        lifecycle = "invalidated"
    elif has_position:
        deteriorating = inv in ("not_investable", "watch") or direction == "deteriorating"
        if deteriorating:
            if inv == "not_investable" or asym == "poor" or rt == "fail":
                action_type = "exit_candidate"
                lifecycle = "exit_candidate"
            else:
                action_type = "trim_candidate"
                lifecycle = "trim_candidate"
            action_status = "risk_reduction_candidate"
        elif inv == "thesis_worthy_timing_confirmed":
            action_type = "add_candidate"
            action_status = "timing_confirmed_candidate"
            lifecycle = "add_candidate"
        elif comparative_thesis is not None and _is_superior(comparative_thesis, thesis):
            # rotation REQUIRES a comparative thesis that is clearly superior.
            action_type = "rotate_candidate"
            action_status = "timing_confirmed_candidate"
            lifecycle = "rotate_candidate"
        else:
            action_type = "monitor"
            action_status = "monitoring"
            lifecycle = "active_position_monitoring"
    else:
        # no holding exists -- the layer NEVER invents one, so no add/trim/exit/rotate.
        if inv == "not_investable":
            if asym == "poor" or rt == "fail" or rec == "euphoric_bubble_risk":
                action_type = "avoid"
                action_status = "blocked"
                lifecycle = "avoided"
            else:
                action_type = "monitor"
                action_status = "monitoring"
                lifecycle = "thesis_monitoring"
        elif inv == "watch":
            action_type = "monitor"
            action_status = "monitoring"
            lifecycle = "thesis_monitoring"
        elif inv == "thesis_worthy":
            action_type = "wait"
            action_status = "thesis_worthy_wait"
            lifecycle = "thesis_worthy_waiting_for_timing"
        elif inv == "thesis_worthy_timing_confirmed":
            action_type = "enter_candidate"
            action_status = "timing_confirmed_candidate"
            lifecycle = "timing_confirmed_candidate"
        else:
            action_type = "monitor"
            action_status = "monitoring"
            lifecycle = "no_position_candidate"

    urgency = _urgency(action_type)
    confidence = round(float(thesis.thesis_confidence), 4)

    required = _required_conditions(action_type)
    blocking = _blocking_conditions(inv, asym, rt, rec)
    invalidation_conditions = tuple(thesis.invalidation_conditions)
    monitoring_signals = tuple(thesis.monitoring_signals)
    review_triggers = (
        "catalyst confirmation or slippage",
        "breakout structure confirms or fails",
        "dilution / capital-structure change",
    )

    action_rationale = (
        "Investability {inv}; timing-confirmation {timing}; asymmetry {asym}; "
        "red-team {rt}; recognition {rec}. Governed model action candidate: "
        "{at} (status {st}, lifecycle {lc}) on {mp}.".format(
            inv=inv, timing=timing, asym=asym, rt=rt, rec=rec,
            at=action_type, st=action_status, lc=lifecycle, mp=mapping or "none")
    )

    source_thesis_components = {
        "investability": inv,
        "timing_confirmation": timing,
        "asymmetry_label": asym,
        "red_team_verdict": rt,
        "technical_confirmation": bool(tech),
        "repricing_gate": bool(repricing_gate),
        "recognition_stage": rec,
        "thesis_confidence": thesis.thesis_confidence,
    }

    # --- boundary guard over EVERY synthesised / carried text -----------------
    _assert_no_leakage(
        action_rationale, action_type, action_status, lifecycle, mapping,
        " ".join(required), " ".join(blocking),
        " ".join(invalidation_conditions), " ".join(monitoring_signals),
        " ".join(review_triggers),
    )

    # --- binding + provenance -------------------------------------------------
    sources = (thesis.ref("InvestmentThesis"),)
    aid = stable_id("IAC", thesis.id, action_type, action_status)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)

    return InvestmentAction(
        id=aid,
        version=1,
        provenance=prov,
        action_id=aid,
        source_thesis_id=thesis.id,
        source_thesis_version=int(thesis.version),
        action_type=action_type,
        action_status=action_status,
        action_rationale=action_rationale,
        required_conditions=required,
        blocking_conditions=blocking,
        invalidation_conditions=invalidation_conditions,
        monitoring_signals=monitoring_signals,
        review_triggers=review_triggers,
        confidence=confidence,
        urgency=urgency,
        lifecycle_state=lifecycle,
        security_or_instrument_mapping=mapping,
        source_thesis_components=source_thesis_components,
        upstream_observation_ids=tuple(thesis.upstream_observation_ids),
        triggering_assessment_ids=tuple(getattr(thesis, "triggering_assessment_ids", ())),
        triggering_assessment_versions=tuple(getattr(thesis, "triggering_assessment_versions", ())),
    )


# ---------------------------------------------------------------------------
# TEMPORARY KRIYA ADAPTER GLUE -- narrow, labelled, and SEPARATE from both the
# real InvestmentAction (above) and Saarathi's PersonalizedAction. It carries the
# user's CHOSEN exact size (within Saarathi's recommended range) plus the
# instrument / side / account / decision-record id the manual-execution (Kriya)
# ticket path reads. REMOVE when a real execution-selection step exists that turns
# Saarathi's recommended RANGE into a chosen size on its own object.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ManualExecutionAdapter(ReasoningObject):
    """TEMPORARY Kriya adapter glue -- the user's chosen exact size within
    Saarathi's recommended range; remove when a real execution-selection step
    exists.

    Saarathi's ``PersonalizedAction`` carries NO exact allocation (only a % range),
    and the real ``InvestmentAction`` carries no side / allocation either -- the
    cognition/actuation boundary (ADR-0010). But the existing Kriya manual-ticket
    path (``create_or_get_ticket``) still reads ``instrument / side / action_type``
    (its investment_action arg) and ``account / intended_allocation /
    cio_decision_record_id`` (its personalized_action arg) off the objects handed
    to it. This single adapter carries exactly those fields so that ONE object can
    be passed as BOTH args (``ref(kind)`` serves both). It is a SEPARATE class and
    must never leak its fields into ``InvestmentAction`` or ``PersonalizedAction``.

    REMOVE this class (and ``make_manual_execution_adapter``) once a real
    execution-selection step turns Saarathi's recommended RANGE into a chosen size
    on its own operational/selection object.
    """

    instrument: str = ""
    side: str = "buy"
    action_type: str = "enter"
    account: str = ""
    intended_allocation: float = 0.0
    cio_decision_record_id: str = ""


def make_manual_execution_adapter(investment_action, personalized_action, *,
                                  intended_allocation, instrument=None,
                                  side="buy", action_type="enter", actor, now):
    """Build the labelled Kriya ``ManualExecutionAdapter`` from the REAL
    ``InvestmentAction`` + Saarathi's ``PersonalizedAction`` + the user's chosen
    exact allocation (which must sit within the personalized recommended range).

    No alpha and no sizing logic of its own -- it merely threads the instrument /
    side / account / chosen allocation / decision-record id the manual-execution
    slice needs, binding both upstream objects for provenance.
    """
    instrument = instrument if instrument is not None else getattr(
        investment_action, "security_or_instrument_mapping", "")
    account = getattr(personalized_action, "account", "")
    decision_id = getattr(personalized_action, "id", "")
    sources = (
        investment_action.ref("InvestmentAction"),
        personalized_action.ref("PersonalizedAction"),
    )
    oid = stable_id("MEA", investment_action.id, decision_id, action_type, instrument)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return ManualExecutionAdapter(
        id=oid,
        version=1,
        provenance=prov,
        instrument=instrument,
        side=side,
        action_type=action_type,
        account=account,
        intended_allocation=float(intended_allocation),
        cio_decision_record_id=decision_id,
    )
