"""Genesis (Sphurana) -- the Opportunity Hypothesis (reasoning object).

The first real Genesis runtime behaviour. ``generate_opportunity_hypothesis``
consumes one or more Intelligence Assessments (purpose-free domain understanding)
and identifies an *emerging opportunity created by changing reality*, by a small,
deterministic, transparent scoring heuristic.

Boundary (ADR-0008): Genesis may say WHAT opportunity is emerging; it must NOT say
HOW to invest in it. The Opportunity Hypothesis names no security, recommends no
trade / allocation / entry / exit / position, and carries no investment-decision
language. Two protections enforce this:

* the object has no thesis / security / instrument / allocation / position field; and
* the generator refuses (``_assert_no_leakage``) to emit any hypothesis whose own
  text carries investment-decision language. It reads only the *structured* fields
  of the upstream assessments (which are themselves already purpose-free), never
  their free text, so nothing can leak through.

Determinism: every output is a pure function of the input Assessments and the
explicit ``now``; no wall clock and no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

# Investment-decision language that must never appear in an opportunity's text.
# (Genesis may say "opportunity"; it may not say how to act on it.)
_FORBIDDEN_TERMS = (
    "buy", "sell", "hold", "target price", "allocat", "position size",
    "portfolio", "invest", "trade", "security selection", "entry point", "exit point",
)

_SIGNIFICANCE = {"low": 0.34, "moderate": 0.67, "high": 1.0}

_OPPORTUNITY_TYPE_BY_ASSESSMENT = {
    "readiness_timing": "timing_inflection",
    "constraint": "supply_constraint",
    "capacity_economics": "capacity_expansion",
    "demand_trajectory": "secular_demand",
    "domain_state": "domain_shift",
}

_MAGNITUDE_RANKS = ("negligible", "small", "moderate", "large", "transformational")


@dataclass(frozen=True)
class OpportunityHypothesis(ReasoningObject):
    """A purpose-free statement of an emerging opportunity, grounded in Assessments."""

    opportunity_type: str = "emerging_theme"
    domain: str = ""
    opportunity_summary: str = ""
    opportunity_mechanism: str = ""
    triggering_assessment_ids: Tuple[str, ...] = field(default_factory=tuple)
    triggering_assessment_versions: Tuple[int, ...] = field(default_factory=tuple)
    evidence_strength: float = 0.0
    opportunity_magnitude: str = "negligible"
    timing_window: str = "unclear"
    confidence: float = 0.0
    uncertainty: Tuple[str, ...] = field(default_factory=tuple)
    contradictory_assessment_ids: Tuple[str, ...] = field(default_factory=tuple)


def _clamp(x: float, lo: float = 0.0, hi: float = 0.95) -> float:
    return max(lo, min(hi, x))


def _assert_no_leakage(*texts: str) -> None:
    blob = " ".join(t for t in texts if t).lower()
    hits = [t for t in _FORBIDDEN_TERMS if t in blob]
    if hits:
        raise ValueError(
            "Opportunity Hypothesis must carry no investment-decision language "
            "(found {0}); Genesis says WHAT opportunity is emerging, not HOW to invest "
            "(ADR-0008).".format(hits)
        )


def generate_opportunity_hypothesis(assessments, *, domain: Optional[str] = None,
                                    actor: str = "genesis", now: float) -> OpportunityHypothesis:
    """Identify an emerging Opportunity Hypothesis from one or more Intelligence
    Assessments.

    Validation: at least one assessment; binds the exact ``(id, version)`` of each;
    never mutates assessments; carries no investment-decision language.
    """
    items = list(assessments)
    if not items:
        raise ValueError(
            "an Opportunity Hypothesis requires at least one Intelligence Assessment"
        )

    domains = {getattr(a, "domain", "") for a in items if getattr(a, "domain", "")}
    if domain is None:
        domain = domains.pop() if len(domains) == 1 else "unspecified"

    n = len(items)
    confs = [float(getattr(a, "confidence", 0.0)) for a in items]
    avg_conf = sum(confs) / n

    directions = [getattr(a, "direction", "mixed") for a in items]
    improving = [a for a, d in zip(items, directions) if d == "improving"]
    deteriorating = [a for a, d in zip(items, directions) if d == "deteriorating"]
    internally_contradicted = [a for a in items if getattr(a, "contradictions", ())]
    types = sorted({getattr(a, "assessment_type", "domain_state") for a in items})

    # --- scoring heuristic (simple, transparent) ---------------------------
    net_direction = (len(improving) - len(deteriorating)) / n
    mechanism_strength = _clamp(net_direction, 0.0, 1.0)

    coverage = min(1.0, n / 2.0)  # 1 assessment -> 0.5, >= 2 -> 1.0
    evidence_strength = round(_clamp(avg_conf * coverage, 0.0, 0.99), 4)

    significance_score = max(
        (_SIGNIFICANCE.get(getattr(a, "significance", "low"), 0.34) for a in items), default=0.0
    )
    magnitude_score = significance_score * mechanism_strength
    raw_rank = (4 if magnitude_score >= 0.85 else 3 if magnitude_score >= 0.60
                else 2 if magnitude_score >= 0.34 else 1 if magnitude_score > 0 else 0)
    cap_rank = 4 if n >= 2 else 3  # a single assessment caps at "large"
    opportunity_magnitude = _MAGNITUDE_RANKS[min(raw_rank, cap_rank)]

    penalty_units = len(deteriorating) + len(internally_contradicted)
    confidence = round(_clamp(avg_conf - 0.10 * penalty_units, 0.0, 0.95), 4)

    if mechanism_strength <= 0:
        timing_window = "unclear"
    elif "readiness_timing" in types:
        timing_window = "imminent"
    elif "capacity_economics" in types or "demand_trajectory" in types:
        timing_window = "emerging"
    elif "constraint" in types:
        timing_window = "near-term"
    else:
        timing_window = "developing"

    opportunity_type = "emerging_theme"
    for t in ("readiness_timing", "constraint", "capacity_economics",
              "demand_trajectory", "domain_state"):
        if t in types:
            opportunity_type = _OPPORTUNITY_TYPE_BY_ASSESSMENT[t]
            break

    contradictory_ids = tuple(a.id for a in deteriorating)

    strength_word = ("a strengthening" if mechanism_strength >= 0.5
                     else "a tentative" if mechanism_strength > 0 else "no clear")
    change_word = "improving" if mechanism_strength > 0 else "mixed"
    opportunity_summary = (
        "{0} {1} opportunity in {2}: {3} change across {4} domain assessment(s) ({5}); "
        "magnitude {6}, evidence {7}.".format(
            strength_word, opportunity_type, domain, change_word,
            n, ", ".join(types), opportunity_magnitude, evidence_strength,
        )
    )
    opportunity_mechanism = (
        "driven by {0} improving and {1} deteriorating domain signal(s) across {2}".format(
            len(improving), len(deteriorating), ", ".join(types)
        )
    )
    uncertainty = (
        "based on {0} domain assessment(s); {1} contradiction/caveat unit(s); single-domain MVP "
        "heuristic; identifies an emerging opportunity only and makes no recommendation to act "
        "on it".format(n, penalty_units),
    )

    _assert_no_leakage(opportunity_summary, opportunity_mechanism, " ".join(uncertainty),
                       opportunity_type, str(domain), opportunity_magnitude, timing_window)

    sources = tuple(a.ref("IntelligenceAssessment") for a in items)  # exact (id, version)
    trig_ids = tuple(a.id for a in items)
    trig_versions = tuple(int(getattr(a, "version", 1)) for a in items)
    oid = stable_id("OPH", str(domain), opportunity_type, *trig_ids)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return OpportunityHypothesis(
        id=oid,
        version=1,
        provenance=prov,
        opportunity_type=opportunity_type,
        domain=str(domain),
        opportunity_summary=opportunity_summary,
        opportunity_mechanism=opportunity_mechanism,
        triggering_assessment_ids=trig_ids,
        triggering_assessment_versions=trig_versions,
        evidence_strength=evidence_strength,
        opportunity_magnitude=opportunity_magnitude,
        timing_window=timing_window,
        confidence=confidence,
        uncertainty=uncertainty,
        contradictory_assessment_ids=contradictory_ids,
    )


def make_opportunity_hypothesis(assessment, subject="", hypothesis="", actor="genesis",
                                now=0, confidence=None, domain=None):
    """Backward-compatible convenience constructor (single assessment) used to thread
    the slice. Runs the real generator; ``subject`` is the domain hint and
    ``hypothesis`` is accepted for source compatibility (the summary is derived)."""
    return generate_opportunity_hypothesis(
        [assessment],
        domain=(domain if domain is not None else (subject or None)),
        actor=actor,
        now=now,
    )
