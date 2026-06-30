"""Reality Intelligence -- the Intelligence Assessment (reasoning object).

The first non-placeholder upstream layer. ``generate_intelligence_assessment``
consumes one or more Observations (manually-supplied source material) and
synthesises a structured assessment of a domain by a small, deterministic,
rule-based procedure: it aggregates the explicit polarity/strength signals
carried by the Observations into a direction, a significance, a confidence, and
explicit contradiction and uncertainty notes.

Boundary (ADR-0008): Reality Intelligence forms *understanding only*. Purpose --
opportunity, value, investment, a trade recommendation -- enters at Genesis and
Prometheus, never here. Two protections enforce this:

* the ``IntelligenceAssessment`` carries no opportunity/thesis/action field; and
* the generator synthesises its own text and never quotes raw source excerpts,
  then refuses (``_assert_no_leakage``) to emit any assessment whose text carries
  investment-decision language -- so source investment language cannot leak
  through.

Determinism: every output is a pure function of the input Observations (and the
explicit ``now``); no wall clock and no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

# Investment-decision language that must never appear in an assessment's own text.
_FORBIDDEN_TERMS = (
    "investment", "buy ", "sell ", "allocat", "trade", "portfolio",
    "opportunity", "thesis", "valuation", "price target",
)

ALLOWED_ASSESSMENT_TYPES = frozenset({
    "domain_state",
    "capacity_economics",
    "demand_trajectory",
    "constraint",
    "readiness_timing",
})


@dataclass(frozen=True)
class IntelligenceAssessment(ReasoningObject):
    """A structured, purpose-free assessment of a domain, grounded in Observations."""

    assessment_type: str = "domain_state"
    domain: str = ""
    current_assessment: str = ""
    direction: str = "mixed"  # improving | deteriorating | mixed
    significance: str = "low"  # low | moderate | high
    confidence: float = 0.0
    grounding_observation_ids: Tuple[str, ...] = field(default_factory=tuple)
    uncertainty: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)


def _clamp(x: float, lo: float = 0.0, hi: float = 0.95) -> float:
    return max(lo, min(hi, x))


def _content(o: Any) -> dict:
    c = getattr(o, "content", None)
    return c if isinstance(c, dict) else {}


def _assert_no_leakage(*texts: str) -> None:
    blob = " ".join(t for t in texts if t).lower()
    hits = [term for term in _FORBIDDEN_TERMS if term in blob]
    if hits:
        raise ValueError(
            "Intelligence Assessment must carry no investment/opportunity language "
            "(found {0}); that boundary belongs to Genesis/Prometheus (ADR-0008).".format(hits)
        )


def generate_intelligence_assessment(
    observations,
    *,
    domain: Optional[str] = None,
    assessment_type: str = "domain_state",
    actor: str = "reality-intelligence",
    now: float,
    confidence: Optional[float] = None,
) -> IntelligenceAssessment:
    """Synthesise an IntelligenceAssessment from one or more Observations.

    Validation: at least one Observation is required; the assessment binds the
    exact ``(id, version)`` of every Observation; Observations are never mutated;
    and the result carries no investment-decision language.
    """
    obs = list(observations)
    if not obs:
        raise ValueError("an Intelligence Assessment requires at least one Observation")
    if assessment_type not in ALLOWED_ASSESSMENT_TYPES:
        raise ValueError("unknown assessment_type: {0}".format(assessment_type))

    contents = [_content(o) for o in obs]
    obs_domains = {c.get("domain") for c in contents if c.get("domain")}
    if domain is None:
        domain = obs_domains.pop() if len(obs_domains) == 1 else "unspecified"

    entities = sorted({c.get("entity") for c in contents if c.get("entity")})
    types = sorted({c.get("source_type") for c in contents if c.get("source_type")})

    supportive, contradictory, neutral = [], [], []
    for o, c in zip(obs, contents):
        pol = c.get("polarity", "neutral")
        bucket = supportive if pol == "supportive" else contradictory if pol == "contradictory" else neutral
        bucket.append((o, c))

    def _weight(items):
        return sum(float(c.get("signal_strength", 1.0)) for _, c in items)

    net = _weight(supportive) - _weight(contradictory)
    eps = 1e-9
    direction = "improving" if net > eps else "deteriorating" if net < -eps else "mixed"

    magnitude = _weight(supportive) + _weight(contradictory) + _weight(neutral)
    significance = "high" if magnitude >= 3.0 else "moderate" if magnitude >= 1.5 else "low"

    if confidence is None:
        confidence = _clamp(0.40 + 0.10 * len(supportive) - 0.15 * len(contradictory))

    # Structural contradiction notes -- by source type + entity, never quoting the
    # raw excerpt (so source investment language cannot pass into the assessment).
    contradictions: Tuple[str, ...] = ()
    if supportive and contradictory:
        notes = []
        for _, c in contradictory:
            notes.append(
                "a {0} signal for {1} runs counter to {2} supportive signal(s)".format(
                    c.get("source_type", "manual"), c.get("entity", "the domain"), len(supportive)
                )
            )
        contradictions = tuple(notes)

    entity_str = ", ".join(entities) if entities else "the domain"
    type_str = ", ".join(types) if types else "manual sources"
    current_assessment = (
        "{0} for {1}: {2} -- {3} supportive, {4} contradictory, {5} neutral signal(s) "
        "across {6}.".format(
            domain, entity_str, direction,
            len(supportive), len(contradictory), len(neutral), type_str,
        )
    )

    uncertainty = (
        "derived from {0} manually-supplied source excerpt(s); single-domain, non-exhaustive; "
        "deterministic rule-based aggregation (no autonomous research)".format(len(obs)),
    )

    _assert_no_leakage(current_assessment, " ".join(contradictions), " ".join(uncertainty),
                       assessment_type, str(domain))

    grounding_ids = tuple(o.id for o in obs)
    sources = tuple(o.ref("Observation") for o in obs)  # binds exact (id, version)
    oid = stable_id("IA", str(domain), assessment_type, *grounding_ids)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return IntelligenceAssessment(
        id=oid,
        version=1,
        provenance=prov,
        assessment_type=assessment_type,
        domain=str(domain),
        current_assessment=current_assessment,
        direction=direction,
        significance=significance,
        confidence=round(float(confidence), 4),
        grounding_observation_ids=grounding_ids,
        uncertainty=uncertainty,
        contradictions=contradictions,
    )


def make_intelligence_assessment(
    observations, subject="", assessment="", actor="reality-intelligence",
    now=0, confidence=None, assessment_type="domain_state", domain=None,
):
    """Backward-compatible convenience constructor used to thread the slice.

    Runs the real synthesis. ``subject`` is taken as the domain hint; ``assessment``
    is accepted for source compatibility but the current assessment is *derived from
    the Observations*, not from this label.
    """
    return generate_intelligence_assessment(
        observations,
        domain=(domain if domain is not None else (subject or None)),
        assessment_type=assessment_type,
        actor=actor,
        now=now,
        confidence=confidence,
    )
