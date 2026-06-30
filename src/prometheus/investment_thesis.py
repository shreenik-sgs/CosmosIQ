"""Prometheus / Nivesha -- the GATED Investment Thesis (reasoning object).

``generate_investment_thesis`` runs an Opportunity Hypothesis (the 003R product)
plus hand-fed ``DiligenceInputs`` through an eleven-stage alpha diligence
gauntlet (A..K) and synthesises a frozen ``InvestmentThesis``. The thesis says
WHETHER the opportunity is investable, WHICH security/instrument expresses it,
WHY the payoff is asymmetric, and WHETHER the chart confirms the timing -- but it
carries NO allocation, NO position size, and NO buy/sell/enter/exit instruction.
That boundary (cognition, not actuation -- ADR-0010) is enforced two ways: the
object has no allocation/order field, and ``_assert_no_leakage`` refuses any
synthesised text that carries trade / allocation / order language.

GATING is the heart of this stage. The thesis is NOT an additive score: a poor
payoff, a failed red team, a euphoric/bubble recognition, no credible winner, or
severe dilution DOWNGRADES or BLOCKS investability regardless of how high the
other legs score. A strong chart on a weak thesis is only a watch; a strong
thesis without chart confirmation is thesis-worthy but not action-ready.
``action_ready`` is a technical-timing flag, never an order.

Determinism: every output is a pure function of the inputs and the explicit
``now``; no wall clock, no randomness; upstream objects are never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

from ._common import clamp, mean
from .pattern_matching import analyze_pattern_matching
from .theme_context import analyze_theme_context
from .value_chain import analyze_value_chain
from .bottleneck import analyze_bottleneck
from .winner_mapping import analyze_winner_mapping
from .financial_inflection import analyze_financial_inflection
from .market_recognition import analyze_market_recognition
from .asymmetry import analyze_asymmetry
from .technical_inflection import analyze_technical_inflection
from .red_team import analyze_red_team, severe_dilution
from .repricing_trigger import analyze_repricing_trigger

# Trade / allocation / order language that must never appear in a thesis's
# synthesised text. Nivesha MAY say: investable, asymmetry, valuation, security /
# ticker mapping, repricing, action-ready (a technical-timing flag), risk/reward.
_FORBIDDEN_TERMS = (
    "buy", "sell", " hold", "enter ", "exit ", "trim", " add ", "rotate",
    "allocat", "position size", "order", "trade ticket", "manual execution",
    "ticket",
)

INVESTABILITY_LEVELS = (
    "not_investable", "watch", "thesis_worthy", "thesis_worthy_action_ready",
)

_BASE_THRESHOLD = 0.50


@dataclass(frozen=True)
class InvestmentThesis(ReasoningObject):
    """A deterministic, gated alpha thesis bound to one Opportunity Hypothesis.

    Carries the security/instrument mapping and the structured output of every
    gauntlet stage, but NO allocation / position size / order (boundary).
    """

    thesis_id: str = ""
    opportunity_id: str = ""
    opportunity_version: int = 1
    # provenance / binding
    triggering_assessment_ids: Tuple[str, ...] = field(default_factory=tuple)
    triggering_assessment_versions: Tuple[int, ...] = field(default_factory=tuple)
    upstream_observation_ids: Tuple[str, ...] = field(default_factory=tuple)
    # stage summaries (structured results from A..K)
    matched_historical_patterns: Tuple[Any, ...] = field(default_factory=tuple)
    theme_megatrend_context: Any = None
    value_chain_summary: Any = None
    bottleneck_summary: Any = None
    winner_mapping: Tuple[Any, ...] = field(default_factory=tuple)
    financial_inflection_summary: Any = None
    market_recognition_summary: Any = None
    asymmetry_summary: Any = None
    red_team_summary: Any = None
    technical_inflection_summary: Any = None
    repricing_trigger_summary: Any = None
    # verdict
    security_or_instrument_mapping: str = ""
    investability_assessment: str = "not_investable"
    action_ready: bool = False
    thesis_confidence: float = 0.0
    thesis_time_horizon: str = ""
    base_score: float = 0.0
    # synthesised narrative (guarded for leakage)
    thesis_summary: str = ""
    key_drivers: Tuple[str, ...] = field(default_factory=tuple)
    key_risks: Tuple[str, ...] = field(default_factory=tuple)
    invalidation_conditions: Tuple[str, ...] = field(default_factory=tuple)
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)


def _assert_no_leakage(*texts: str) -> None:
    blob = " ".join(t for t in texts if t).lower()
    hits = [t for t in _FORBIDDEN_TERMS if t in blob]
    if hits:
        raise ValueError(
            "Investment Thesis must carry no trade/allocation/order language "
            "(found {0}); Nivesha says WHETHER/WHICH/WHY and a technical-timing "
            "flag, not HOW MUCH or an instruction to trade (ADR-0010).".format(hits)
        )


def _candidate_for(winner, diligence_inputs):
    if winner is None:
        return None
    for c in diligence_inputs.candidates:
        if c.ticker == winner.ticker and c.name == winner.name:
            return c
    return None


def generate_investment_thesis(opportunity_hypothesis, diligence_inputs, *,
                               actor: str = "prometheus", now: float) -> InvestmentThesis:
    """Run the A..K gauntlet over an Opportunity Hypothesis + DiligenceInputs and
    synthesise a gated Investment Thesis. Requires at least one candidate; binds
    the exact (id, version) of the upstream hypothesis; never mutates it."""
    oh = opportunity_hypothesis
    if diligence_inputs is None or not diligence_inputs.candidates:
        raise ValueError(
            "an Investment Thesis requires DiligenceInputs with at least one candidate "
            "-- an Opportunity Hypothesis must pass diligence before a thesis exists"
        )

    # --- A..K -----------------------------------------------------------------
    pattern = analyze_pattern_matching(oh, diligence_inputs)
    theme = analyze_theme_context(oh)
    value_chain = analyze_value_chain(oh)
    bottleneck = analyze_bottleneck(oh)
    winner = analyze_winner_mapping(oh, diligence_inputs, bottleneck, value_chain)
    top_candidate = _candidate_for(winner.best_winner, diligence_inputs)
    financial = analyze_financial_inflection(top_candidate)
    market = analyze_market_recognition(oh, top_candidate)
    asymmetry = analyze_asymmetry(top_candidate, diligence_inputs.scenario_probabilities())
    technical = analyze_technical_inflection(top_candidate)
    red = analyze_red_team(oh, pattern, bottleneck, winner, financial, market,
                           asymmetry, technical, top_candidate)
    repricing = analyze_repricing_trigger(oh, top_candidate, financial, market,
                                          asymmetry, technical, bottleneck)

    # --- base score (mean of the seven thesis legs) ---------------------------
    base = round(mean([
        pattern.pattern_quality,
        value_chain.value_chain_capture,
        bottleneck.bottleneck_leverage,
        winner.best_winner_score,
        financial.financial_inflection_score,
        market.market_recognition_score,
        asymmetry.asymmetry_score,
    ]), 4)

    # --- GATING (not additive-only) ------------------------------------------
    severe_dil = severe_dilution(top_candidate)
    not_investable = (
        asymmetry.asymmetry_label == "poor"
        or red.red_team_verdict == "fail"
        or market.recognition_stage == "euphoric_bubble_risk"
        or winner.no_credible_winner
    )
    watch_downgrade = (financial.financial_inflection_score < 0.40 or severe_dil)
    strong_thesis = (base >= _BASE_THRESHOLD) and not watch_downgrade
    technical_confirmation = technical.technical_confirmation
    repricing_gate = repricing.gate_passed

    if not_investable:
        investability = "not_investable"
        action_ready = False
    elif not strong_thesis:
        # strong chart but weak thesis -> watch (not action-ready)
        investability = "watch"
        action_ready = False
    elif technical_confirmation and repricing_gate:
        investability = "thesis_worthy_action_ready"
        action_ready = True
    else:
        # strong thesis but no technical confirmation -> thesis-worthy, not action-ready
        investability = "thesis_worthy"
        action_ready = False

    thesis_confidence = clamp(base - red.confidence_haircut)
    if not_investable:
        thesis_confidence = min(thesis_confidence, 0.20)

    horizon = repricing.repricing_timing_window or bottleneck.timing_window or "to be monitored"

    # --- synthesised narrative (controlled phrasing, then guarded) ------------
    mapping = winner.security_or_instrument_mapping
    bw = winner.best_winner

    key_drivers = []
    key_drivers.append("Theme: {0} ({1}, recognition {2})".format(
        theme.theme, theme.capital_cycle_stage, market.recognition_stage))
    key_drivers.append("Bottleneck: {0} -- {1}".format(
        bottleneck.bottleneck_type, bottleneck.constrained_node))
    if value_chain.capture_role:
        key_drivers.append("Value-chain capture at the {0} node (leverage {1})".format(
            value_chain.capture_role, value_chain.value_chain_capture))
    if bw is not None:
        key_drivers.append("Mapped winner {0} (winner-score {1})".format(
            bw.ticker or bw.name, bw.winner_score))
    key_drivers.append("Financial inflection probability {0}".format(
        financial.financial_inflection_score))
    key_drivers.append("Risk/reward asymmetry: {0} (up/down {1})".format(
        asymmetry.asymmetry_label, asymmetry.upside_downside_ratio))
    key_drivers.append("Repricing trigger probability {0}".format(
        repricing.repricing_probability))
    if pattern.matched_archetypes:
        non_bubble = [m for m in pattern.matched_archetypes
                      if not m.bubble_or_false_positive_flag]
        if non_bubble:
            top_arch = max(non_bubble, key=lambda m: m.relevance_score)
            key_drivers.append("Closest archetype: {0} (relevance {1})".format(
                top_arch.name, top_arch.relevance_score))

    key_risks = []
    if bw is not None:
        key_risks.extend(bw.key_risks)
    for ch in red.checks:
        if ch.verdict in ("concern", "fail"):
            key_risks.append("{0}: {1}".format(ch.check, ch.rationale))
    key_risks.extend(financial.notes)
    key_risks.extend(asymmetry.notes)
    key_risks.extend(technical.notes)
    if pattern.bubble_flag:
        key_risks.append("pattern: matches a late-cycle euphoria archetype")
    if red.false_positive_label:
        key_risks.append("red-team label: {0}".format(red.false_positive_label))
    # de-duplicate while preserving order
    seen = set()
    key_risks = [r for r in key_risks if not (r in seen or seen.add(r))]

    invalidation_conditions = list(repricing.invalidation_conditions)
    if asymmetry.asymmetry_label == "poor":
        invalidation_conditions.append("risk/reward asymmetry is poor")

    monitoring_signals = list(repricing.monitoring_signals)

    thesis_summary = (
        "Investability {0}; thesis confidence {1}; security/instrument mapping {2}; "
        "action-ready {3} (a technical-timing flag, not an instruction)".format(
            investability, round(thesis_confidence, 4), mapping or "none", action_ready))

    # --- boundary guard over synthesised text ---------------------------------
    _assert_no_leakage(
        thesis_summary, investability, mapping, horizon,
        " ".join(key_drivers), " ".join(key_risks),
        " ".join(invalidation_conditions), " ".join(monitoring_signals),
    )

    # --- binding + provenance -------------------------------------------------
    sources = (oh.ref("OpportunityHypothesis"),)
    tid = stable_id("THS", oh.id, mapping or "no-winner", investability)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)

    return InvestmentThesis(
        id=tid,
        version=1,
        provenance=prov,
        thesis_id=tid,
        opportunity_id=oh.id,
        opportunity_version=int(getattr(oh, "version", 1)),
        triggering_assessment_ids=tuple(getattr(oh, "triggering_assessment_ids", ())),
        triggering_assessment_versions=tuple(getattr(oh, "triggering_assessment_versions", ())),
        upstream_observation_ids=tuple(getattr(oh, "upstream_observation_ids", ())),
        matched_historical_patterns=pattern.matched_archetypes,
        theme_megatrend_context=theme,
        value_chain_summary=value_chain,
        bottleneck_summary=bottleneck,
        winner_mapping=winner.winners,
        financial_inflection_summary=financial,
        market_recognition_summary=market,
        asymmetry_summary=asymmetry,
        red_team_summary=red,
        technical_inflection_summary=technical,
        repricing_trigger_summary=repricing,
        security_or_instrument_mapping=mapping,
        investability_assessment=investability,
        action_ready=action_ready,
        thesis_confidence=round(thesis_confidence, 4),
        thesis_time_horizon=horizon,
        base_score=base,
        thesis_summary=thesis_summary,
        key_drivers=tuple(key_drivers),
        key_risks=tuple(key_risks),
        invalidation_conditions=tuple(invalidation_conditions),
        monitoring_signals=tuple(monitoring_signals),
    )


@dataclass(frozen=True)
class _ToyInvestmentThesis(ReasoningObject):
    """A deliberately minimal TOY thesis used ONLY by ``make_investment_thesis``
    to thread the pre-existing generic / Kriya tests. It is NOT the alpha thesis
    and performs NO diligence; it simply carries an instrument + allocation +
    timing forward so the legacy action -> ticket path still resolves. The real,
    gated, allocation-free thesis is ``InvestmentThesis`` via
    ``generate_investment_thesis``.
    """

    instrument: str = ""
    intended_allocation: float = 0.0
    timing: str = "now"
    direction: str = "long"
    rationale: str = ""


def make_investment_thesis(hypothesis, instrument, intended_allocation, actor, now,
                           direction="long", timing="now", rationale=""):
    """Backward-compatible TOY shim (predates the alpha gauntlet). Builds a
    ``_ToyInvestmentThesis`` carrying the instrument/allocation/timing so legacy
    threading tests keep working; it performs NO diligence. Real theses come from
    ``generate_investment_thesis`` (which carries no allocation -- the boundary).
    """
    sources = (hypothesis.ref("OpportunityHypothesis"),)
    tid = stable_id("THS", hypothesis.id, instrument, str(intended_allocation))
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return _ToyInvestmentThesis(
        id=tid,
        version=1,
        provenance=prov,
        instrument=instrument,
        intended_allocation=float(intended_allocation),
        timing=timing,
        direction=direction,
        rationale=rationale,
    )
