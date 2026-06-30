"""Stage K -- Repricing trigger.

The repricing trigger is the GATED conjunction of everything upstream: a real,
confirmable catalyst AND a fundamental inflection AND a still-early recognition
AND a favorable payoff AND a confirming chart. Only when all of these line up is
the opportunity "ready to reprice". A speculative rumour cannot materially raise
it (its catalyst score is ~0), and high dilution drags it down -- so a positive
catalyst sitting on top of heavy dilution is NOT action-ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from ._common import clamp, mean

GATE = 0.50  # the per-leg threshold and the action-ready repricing threshold


@dataclass(frozen=True)
class RepricingTriggerResult:
    catalyst_score: float = 0.0
    financial_inflection_score: float = 0.0
    market_recognition_score: float = 0.0
    asymmetry_score: float = 0.0
    technical_trigger_score: float = 0.0
    repricing_probability: float = 0.0
    gate_passed: bool = False
    repricing_timing_window: str = ""
    key_trigger_events: Tuple[str, ...] = field(default_factory=tuple)
    invalidation_conditions: Tuple[str, ...] = field(default_factory=tuple)
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)


def _catalyst_score(opportunity_hypothesis, top_candidate) -> float:
    oh = opportunity_hypothesis
    mon = " ".join(oh.monitoring_signals).lower()
    rumor_only = ("rumour" in mon or "rumor" in mon) and "catalyst" in mon
    confirmed = "confirmed/probable positive catalyst" in (oh.why_now or "").lower()
    if confirmed:
        return 0.80
    if rumor_only:
        # a speculative rumour cannot materially raise the trigger: ~0, which
        # fails the ``catalyst_score > 0`` gate below.
        return 0.0
    if top_candidate is not None and top_candidate.guidance == "raise":
        return 0.50
    return 0.20


def analyze_repricing_trigger(opportunity_hypothesis, top_candidate, financial_result,
                              market_result, asymmetry_result,
                              technical_result, bottleneck_result) -> RepricingTriggerResult:
    catalyst = _catalyst_score(opportunity_hypothesis, top_candidate)
    fin = financial_result.financial_inflection_score
    mkt = market_result.market_recognition_score
    asym = asymmetry_result.asymmetry_score
    tech = technical_result.technical_setup_score
    technical_confirmation = technical_result.technical_confirmation

    gate_passed = bool(
        catalyst > 0.0
        and fin >= GATE
        and mkt >= GATE
        and asym >= GATE
        and technical_confirmation
    )

    if gate_passed:
        probability = clamp(mean([catalyst, fin, mkt, asym, tech]))
    else:
        # ungated: a partial signal, deliberately well below the action threshold.
        probability = clamp(0.30 * mean([catalyst, fin, mkt, asym, tech]))

    # high dilution drags the trigger down (and out of action-ready range)
    if top_candidate is not None and top_candidate.dilution_risk == "high":
        probability = clamp(probability - 0.30)
        gate_passed = gate_passed and probability >= GATE

    window = bottleneck_result.timing_window or "to be monitored"

    triggers = []
    if catalyst >= 0.80:
        triggers.append("a confirmable near-term catalyst lands as expected")
    if fin >= GATE:
        triggers.append("the fundamental inflection prints in results")
    if technical_confirmation:
        triggers.append("the chart confirms (stacked EMAs, breakout on volume)")

    invalidations = [
        "the bottleneck eases / the constraint resolves",
        "recognition runs ahead of fundamentals (crowding)",
        "the EMA structure breaks down or the breakout fails",
    ]
    monitoring = [
        "catalyst confirmation vs slippage",
        "fundamental inflection vs guidance",
        "recognition / crowding drift",
        "chart structure and relative strength",
    ]

    return RepricingTriggerResult(
        catalyst_score=round(catalyst, 4),
        financial_inflection_score=round(fin, 4),
        market_recognition_score=round(mkt, 4),
        asymmetry_score=round(asym, 4),
        technical_trigger_score=round(tech, 4),
        repricing_probability=round(probability, 4),
        gate_passed=gate_passed,
        repricing_timing_window=window,
        key_trigger_events=tuple(triggers),
        invalidation_conditions=tuple(invalidations),
        monitoring_signals=tuple(monitoring),
    )
