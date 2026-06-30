"""Stage A -- Historical pattern matching against a curated archetype library.

Each Opportunity Hypothesis (+ hand-fed DiligenceInputs) is matched against 14
named alpha archetypes. An archetype is a structured pattern: the conditions that
must hold, the early / confirming / failure signals to watch, the financial and
market signature it usually carries, historical analogs, and the way it most
often fails. Matching is a deterministic predicate evaluation over the OH and the
inputs -- never a free-text similarity guess.

The library deliberately includes ONE late-cycle / euphoria archetype whose match
sets ``bubble_or_false_positive_flag`` so a crowded, thinly-supported "opportunity"
is recognised as a likely trap rather than an edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from ._common import clamp

# --------------------------------------------------------------------------- #
# Curated archetype library (14). ``required_conditions`` are context-predicate
# keys (see ``_context``); the rest is human-readable diligence scaffolding.
# --------------------------------------------------------------------------- #

ARCHETYPES: Tuple[Dict, ...] = (
    {
        "name": "bottleneck_capacity_owner",
        "required_conditions": ("bottleneck_driven", "has_constraint",
                                 "before_obvious", "revenue_inflection"),
        "early_signals": ("capacity contracts signed", "utilisation rising"),
        "confirming_signals": ("pricing power realised", "backlog extending"),
        "failure_signals": ("constraint eases", "new supply floods in"),
        "expected_financial_signature": "revenue inflection with margin expansion",
        "expected_market_signature": "still lightly covered / hidden",
        "historical_analogs": ("rail capacity 1990s", "memory up-cycles"),
        "failure_mode": "the bottleneck resolves faster than the market repriced",
    },
    {
        "name": "picks_and_shovels",
        "required_conditions": ("has_constraint", "cross_domain", "theme_early"),
        "early_signals": ("enabling-layer demand broadening",),
        "confirming_signals": ("multi-customer adoption",),
        "failure_signals": ("the enabling layer commoditises",),
        "expected_financial_signature": "broad, durable demand pull-through",
        "expected_market_signature": "early, under-followed",
        "historical_analogs": ("test-and-measurement in booms",),
        "failure_mode": "the enabling layer has no pricing power",
    },
    {
        "name": "second_derivative_beneficiary",
        "required_conditions": ("has_constraint", "cross_domain", "revenue_inflection"),
        "early_signals": ("supplier-of-supplier orders rising",),
        "confirming_signals": ("lead times extending upstream",),
        "failure_signals": ("primary demand stalls",),
        "expected_financial_signature": "lagged revenue inflection",
        "expected_market_signature": "overlooked one step up the chain",
        "historical_analogs": ("substrate makers in chip cycles",),
        "failure_mode": "demand never reaches the second derivative",
    },
    {
        "name": "margin_inflection",
        "required_conditions": ("margin_expansion", "revenue_inflection"),
        "early_signals": ("operating leverage appearing",),
        "confirming_signals": ("gross margin steps up",),
        "failure_signals": ("cost base re-inflates",),
        "expected_financial_signature": "margin expansion ahead of estimates",
        "expected_market_signature": "estimates lag the inflection",
        "historical_analogs": ("software scale inflections",),
        "failure_mode": "the margin gain is one-off, not structural",
    },
    {
        "name": "demand_supply_imbalance",
        "required_conditions": ("bottleneck_driven", "has_constraint"),
        "early_signals": ("waitlists / allocation rationing",),
        "confirming_signals": ("spot pricing rising",),
        "failure_signals": ("capacity additions announced broadly",),
        "expected_financial_signature": "pricing-led revenue growth",
        "expected_market_signature": "imbalance not yet consensus",
        "historical_analogs": ("shipping rate spikes",),
        "failure_mode": "supply responds quickly",
    },
    {
        "name": "early_adoption_s_curve",
        "required_conditions": ("theme_early", "before_obvious", "cross_domain"),
        "early_signals": ("lighthouse customers adopting",),
        "confirming_signals": ("adoption breadth widening",),
        "failure_signals": ("adoption plateaus early",),
        "expected_financial_signature": "accelerating top-line",
        "expected_market_signature": "before-obvious, low recognition",
        "historical_analogs": ("early cloud migration",),
        "failure_mode": "the S-curve flattens prematurely",
    },
    {
        "name": "capital_cycle_underinvestment",
        "required_conditions": ("has_constraint", "theme_early"),
        "early_signals": ("years of underinvestment in supply",),
        "confirming_signals": ("incumbent discipline holding",),
        "failure_signals": ("a capex super-cycle restarts",),
        "expected_financial_signature": "returns on capital rising",
        "expected_market_signature": "the sector is unloved",
        "historical_analogs": ("energy capex troughs",),
        "failure_mode": "capital floods back in",
    },
    {
        "name": "platform_shift_convergence",
        "required_conditions": ("cross_domain", "theme_early"),
        "early_signals": ("multiple independent trends converging",),
        "confirming_signals": ("ecosystem forming",),
        "failure_signals": ("the convergence stalls",),
        "expected_financial_signature": "multi-vector demand",
        "expected_market_signature": "narrative still forming",
        "historical_analogs": ("mobile + cloud convergence",),
        "failure_mode": "the convergence was a coincidence, not causal",
    },
    {
        "name": "hidden_compounder",
        "required_conditions": ("low_recognition", "revenue_inflection", "margin_expansion"),
        "early_signals": ("quietly compounding fundamentals",),
        "confirming_signals": ("reinvestment runway proven",),
        "failure_signals": ("growth decelerates",),
        "expected_financial_signature": "durable compounding",
        "expected_market_signature": "under-followed, mispriced",
        "historical_analogs": ("under-the-radar industrials",),
        "failure_mode": "the moat was thinner than it looked",
    },
    {
        "name": "catalyst_repricing",
        "required_conditions": ("has_constraint", "revenue_inflection"),
        "early_signals": ("a confirmable near-term catalyst pending",),
        "confirming_signals": ("the catalyst lands as expected",),
        "failure_signals": ("the catalyst slips or disappoints",),
        "expected_financial_signature": "step-change on the catalyst",
        "expected_market_signature": "catalyst not yet priced",
        "historical_analogs": ("contract-win re-rates",),
        "failure_mode": "the catalyst never materialises",
    },
    {
        "name": "constrained_supply_pricing_power",
        "required_conditions": ("bottleneck_driven", "has_constraint", "margin_expansion"),
        "early_signals": ("scarcity granting price control",),
        "confirming_signals": ("price increases sticking",),
        "failure_signals": ("substitutes emerge",),
        "expected_financial_signature": "expanding margins on scarcity",
        "expected_market_signature": "scarcity under-appreciated",
        "historical_analogs": ("specialty materials shortages",),
        "failure_mode": "substitution erodes the scarcity rent",
    },
    {
        "name": "vertical_integration_capture",
        "required_conditions": ("has_constraint", "revenue_inflection"),
        "early_signals": ("owning the choke point of the chain",),
        "confirming_signals": ("capturing more of the chain's economics",),
        "failure_signals": ("the choke point is bypassed",),
        "expected_financial_signature": "rising share of chain economics",
        "expected_market_signature": "capture node mis-attributed",
        "historical_analogs": ("integrated producers",),
        "failure_mode": "the chain re-routes around the node",
    },
    {
        "name": "structural_tailwind",
        "required_conditions": ("cross_domain", "theme_early", "before_obvious"),
        "early_signals": ("a multi-year structural tailwind forming",),
        "confirming_signals": ("policy / demand reinforcing it",),
        "failure_signals": ("the tailwind reverses",),
        "expected_financial_signature": "multi-year demand visibility",
        "expected_market_signature": "tailwind not yet consensus",
        "historical_analogs": ("electrification build-outs",),
        "failure_mode": "the structural thesis was a fad",
    },
    {
        "name": "late_cycle_euphoria_bubble",
        "required_conditions": ("theme_crowded_or_euphoric", "thin_financials"),
        "early_signals": ("everyone already owns the theme",),
        "confirming_signals": ("valuation detached from fundamentals",),
        "failure_signals": ("first earnings miss de-rates the group",),
        "expected_financial_signature": "thin or absent fundamental support",
        "expected_market_signature": "euphoric, crowded, fully recognised",
        "historical_analogs": ("dot-com 2000", "any blow-off top"),
        "failure_mode": "the narrative breaks and the crowd exits at once",
    },
)

BUBBLE_ARCHETYPE = "late_cycle_euphoria_bubble"

# Minimum fraction of required conditions for an archetype to count as matched.
MATCH_THRESHOLD = 0.5
BUBBLE_PENALTY = 0.4


@dataclass(frozen=True)
class MatchedArchetype:
    name: str
    relevance_score: float
    conditions_met: Tuple[str, ...]
    conditions_missing: Tuple[str, ...]
    confidence_effect: float
    asymmetry_effect: float
    bubble_or_false_positive_flag: bool
    failure_mode: str = ""


@dataclass(frozen=True)
class PatternMatchingResult:
    matched_archetypes: Tuple[MatchedArchetype, ...] = field(default_factory=tuple)
    pattern_quality: float = 0.0
    bubble_flag: bool = False
    context: Dict = field(default_factory=dict)


def _context(opportunity_hypothesis, diligence_inputs) -> Dict:
    oh = opportunity_hypothesis
    cands = diligence_inputs.candidates
    constraint = (oh.driving_constraint or "").lower()

    def _rev_up(c):
        return (c.revenue is not None and c.prior_revenue is not None
                and c.revenue > c.prior_revenue)

    def _margin_up(c):
        return (c.gross_margin is not None and c.prior_gross_margin is not None
                and c.gross_margin > c.prior_gross_margin)

    revenue_inflection = any(_rev_up(c) for c in cands)
    margin_expansion = any(_margin_up(c) for c in cands)
    return {
        "bottleneck_driven": bool(oh.bottleneck_driven),
        "has_constraint": bool(oh.driving_constraint),
        "power_constraint": ("power" in constraint or "energy" in constraint),
        "before_obvious": oh.opportunity_timing == "before_obvious",
        "theme_early": oh.theme_maturity in ("hidden", "emerging"),
        "theme_accelerating": oh.theme_maturity == "accelerating",
        "theme_crowded_or_euphoric": oh.theme_maturity in ("crowded", "euphoric"),
        "cross_domain": len(oh.cross_domain_convergence) >= 2,
        "revenue_inflection": revenue_inflection,
        "margin_expansion": margin_expansion,
        "thin_financials": not revenue_inflection,
        "low_recognition": oh.opportunity_timing in ("before_obvious", "emerging"),
        "high_false_positive": oh.false_positive_risk == "high",
        "bubble_risk": oh.bubble_hype_risk == "high",
    }


def analyze_pattern_matching(opportunity_hypothesis, diligence_inputs) -> PatternMatchingResult:
    ctx = _context(opportunity_hypothesis, diligence_inputs)
    matched = []
    bubble_flag = False
    for arch in ARCHETYPES:
        required = arch["required_conditions"]
        met = tuple(k for k in required if ctx.get(k))
        missing = tuple(k for k in required if not ctx.get(k))
        relevance = round(len(met) / len(required), 4) if required else 0.0
        if relevance < MATCH_THRESHOLD:
            continue
        is_bubble = arch["name"] == BUBBLE_ARCHETYPE
        if is_bubble:
            bubble_flag = True
            confidence_effect = round(-0.30 * relevance, 4)
            asymmetry_effect = round(-0.30 * relevance, 4)
        else:
            confidence_effect = round(0.10 * relevance, 4)
            asymmetry_effect = round(0.05 * relevance, 4)
        matched.append(MatchedArchetype(
            name=arch["name"],
            relevance_score=relevance,
            conditions_met=met,
            conditions_missing=missing,
            confidence_effect=confidence_effect,
            asymmetry_effect=asymmetry_effect,
            bubble_or_false_positive_flag=is_bubble,
            failure_mode=arch["failure_mode"],
        ))

    non_bubble = [m.relevance_score for m in matched if not m.bubble_or_false_positive_flag]
    best = max(non_bubble) if non_bubble else 0.0
    pattern_quality = clamp(best - (BUBBLE_PENALTY if bubble_flag else 0.0))
    return PatternMatchingResult(
        matched_archetypes=tuple(matched),
        pattern_quality=round(pattern_quality, 4),
        bubble_flag=bubble_flag,
        context=ctx,
    )
