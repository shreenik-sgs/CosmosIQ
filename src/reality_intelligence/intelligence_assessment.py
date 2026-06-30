"""Reality Intelligence -- the Intelligence Assessment (reasoning object).

The first non-placeholder upstream layer. ``generate_intelligence_assessment``
consumes one or more Observations (manually-supplied source material) and
INFERS a structured assessment of a domain by a small, deterministic, rule-based
procedure. It does NOT relabel hand-supplied verdicts: from each Observation's
*structured raw facts* (metric values, an observed up/down/flat change, a novelty
tag, a reliability tag) it extracts one typed ``RealitySignal`` (a direction, a
strength, a novelty, an evidence-quality, a corroboration count), then aggregates
those signals into the assessment's direction, significance, confidence, typed
indicators, weak-signal set, contradiction notes, and uncertainty.

The MVP may accept manual *hints* (the raw facts above, an optional
``signal_type_hint``). It MUST NOT accept the assessment's final direction /
significance / confidence as hand-fed -- those are always inferred here.

Boundary (ADR-0008): Reality Intelligence forms *understanding only*. Purpose --
opportunity, value, investment, a trade recommendation -- enters at Genesis and
Prometheus, never here. Two protections enforce this:

* the ``IntelligenceAssessment`` carries no opportunity/thesis/action field; and
* the generator synthesises its own text from *structured* signal fields, never
  quotes raw source excerpts, then refuses (``_assert_no_leakage``) to emit any
  assessment whose text carries investment-decision language -- so source
  investment language cannot leak through.

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
    "opportunity", "thesis", "valuation", "price target", "stock", "position",
    "target price",
)

ALLOWED_ASSESSMENT_TYPES = frozenset({
    "domain_state",
    "capacity_economics",
    "demand_trajectory",
    "constraint",
    "readiness_timing",
})

# The typed reality signals this MVP can extract.
SIGNAL_TYPES = frozenset({
    "constraint",
    "adoption",
    "supply_chain",
    "economic_inflection",
    "readiness",
    "market_recognition",
    "catalyst",
    "capital_structure_risk",
})

# Source types that denote a catalyst / capital-structure event (not a raw metric
# excerpt). A catalyst observation routes through the catalyst extraction rules.
_CATALYST_SOURCE_TYPES = frozenset({
    "earnings_call_transcript", "sec_filing", "press_release", "investor_presentation",
    "management_guidance", "customer_announcement", "contract_win", "strategic_partnership",
    "capacity_reservation", "regulatory_event", "product_launch", "capital_structure_event",
    "financial_report",
})

# Catalyst-type substrings that mark a capital-structure / dilution risk.
_CAP_STRUCTURE_TOKENS = (
    "dilution", "atm", "shelf", "offering", "convertible", "warrant",
    "covenant", "refinancing", "going_concern", "insider_selling",
)

# Financial metrics that read as an economic inflection (direction from the move).
_ECON_FINANCIAL = frozenset({
    "revenue", "gross_margin", "ebitda", "operating_leverage", "backlog", "guidance",
})

# Financial metrics that read as a capital-structure / dilution risk (deteriorating).
_CAP_RISK_FINANCIAL = frozenset({"dilution_risk", "shelf", "atm", "cash_runway", "debt"})

# Catalyst confirmation discipline -> evidence-quality multiplier. A speculative
# rumor is heavily discounted, so it cannot materially raise IA confidence.
_STATUS_WEIGHT = {"confirmed": 1.0, "probable": 0.7, "possible": 0.4, "speculative_rumor": 0.2}

# Map a source type to its default signal type (overridden by signal_type_hint).
_TYPE_BY_SOURCE = {
    "earnings_excerpt": "economic_inflection",
    "news_excerpt": "adoption",
    "analyst_note_excerpt": "economic_inflection",
    "filing_excerpt": "economic_inflection",
    "infrastructure_milestone": "readiness",
    "capacity_power_demand_signal": "constraint",
}

# Infer the assessment type from the dominant signal type (when not overridden).
_ASSESSMENT_TYPE_BY_SIGNAL = {
    "constraint": "constraint",
    "readiness": "readiness_timing",
    "adoption": "demand_trajectory",
    "economic_inflection": "capacity_economics",
    "supply_chain": "capacity_economics",
    "market_recognition": "domain_state",
    "catalyst": "readiness_timing",
    "capital_structure_risk": "constraint",
}

_LEVELS = {"low": 0.3, "moderate": 0.6, "high": 0.9}
_NOVELTY_LEVELS = {"low": 0.2, "moderate": 0.5, "high": 0.85}

# Purpose-free direction phrasing per signal type, for the typed indicators.
_INDICATOR_PHRASING = {
    "constraint": {
        "improving": "domain constraint easing",
        "deteriorating": "domain constraint tightening",
        "neutral": "domain constraint steady",
    },
    "readiness": {
        "improving": "capacity-expansion readiness increasing",
        "deteriorating": "capacity-expansion readiness declining",
        "neutral": "capacity-expansion readiness steady",
    },
    "adoption": {
        "improving": "adoption accelerating",
        "deteriorating": "adoption slowing",
        "neutral": "adoption steady",
    },
    "supply_chain": {
        "improving": "supply-chain conditions easing",
        "deteriorating": "supply-chain conditions tightening",
        "neutral": "supply-chain conditions steady",
    },
    "economic_inflection": {
        "improving": "economic inflection strengthening",
        "deteriorating": "economic inflection weakening",
        "neutral": "economic inflection flat",
    },
    "market_recognition": {
        "improving": "market recognition rising",
        "deteriorating": "market recognition fading",
        "neutral": "market recognition steady",
    },
    "catalyst": {
        "improving": "positive catalyst pending",
        "deteriorating": "negative catalyst pending",
        "neutral": "catalyst status unclear",
    },
    "capital_structure_risk": {
        "improving": "capital-structure risk easing",
        "deteriorating": "capital-structure / dilution risk present",
        "neutral": "capital-structure risk steady",
    },
}


@dataclass(frozen=True)
class RealitySignal:
    """One typed signal inferred from a single Observation's structured facts."""

    signal_id: str
    signal_type: str
    direction: str  # improving | deteriorating | neutral
    strength: float
    novelty: float
    evidence_quality: float
    as_of: str
    supporting_evidence_ids: Tuple[str, ...] = field(default_factory=tuple)
    uncertainty: str = ""
    contradiction_flag: bool = False
    is_weak: bool = False
    monitoring_only: bool = False


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
    # --- inferred structured products --------------------------------------
    signals: Tuple[RealitySignal, ...] = field(default_factory=tuple)
    weak_signals: Tuple[RealitySignal, ...] = field(default_factory=tuple)
    constraint_indicators: Tuple[str, ...] = field(default_factory=tuple)
    readiness_indicators: Tuple[str, ...] = field(default_factory=tuple)
    adoption_indicators: Tuple[str, ...] = field(default_factory=tuple)
    supply_chain_indicators: Tuple[str, ...] = field(default_factory=tuple)
    economic_inflection_indicators: Tuple[str, ...] = field(default_factory=tuple)
    market_recognition_indicators: Tuple[str, ...] = field(default_factory=tuple)
    domain_reality_change: str = ""
    signal_novelty: float = 0.0
    evidence_quality: float = 0.0
    entities: Tuple[str, ...] = field(default_factory=tuple)
    # --- catalyst / capital-structure products -----------------------------
    catalysts: Tuple[dict, ...] = field(default_factory=tuple)
    capital_structure_risks: Tuple[dict, ...] = field(default_factory=tuple)
    catalyst_indicators: Tuple[str, ...] = field(default_factory=tuple)
    capital_structure_risk_indicators: Tuple[str, ...] = field(default_factory=tuple)
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)


def _clamp(x: float, lo: float = 0.0, hi: float = 0.95) -> float:
    return max(lo, min(hi, x))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _content(o: Any) -> dict:
    c = getattr(o, "content", None)
    return c if isinstance(c, dict) else {}


def _level(value, mapping, default):
    """Resolve a label ('low'/'moderate'/'high') or a numeric 0..1 value."""
    if value is None:
        return default
    if isinstance(value, str):
        key = value.strip().lower()
        if key in mapping:
            return mapping[key]
        try:
            return _clamp01(float(key))
        except (TypeError, ValueError):
            return default
    try:
        return _clamp01(float(value))
    except (TypeError, ValueError):
        return default


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _assert_no_leakage(*texts: str) -> None:
    blob = " ".join(t for t in texts if t).lower()
    hits = [term for term in _FORBIDDEN_TERMS if term in blob]
    if hits:
        raise ValueError(
            "Intelligence Assessment must carry no investment/opportunity language "
            "(found {0}); that boundary belongs to Genesis/Prometheus (ADR-0008).".format(hits)
        )


def _extract_signal(o: Any, c: dict) -> Tuple[RealitySignal, str]:
    """Infer ONE typed RealitySignal from one Observation's structured facts.

    Returns the (corroboration-unaware) signal plus the observation's entity, so
    cross-signal corroboration and contradiction can be computed afterwards.
    """
    # --- signal type -------------------------------------------------------
    hint = c.get("signal_type_hint")
    catalyst_type = c.get("catalyst_type")
    expected_direction = c.get("expected_direction")
    financial_metric = c.get("financial_metric")
    source_type = c.get("source_type")
    catalyst_status = c.get("catalyst_status")

    forced_direction = None
    if isinstance(hint, str) and hint in SIGNAL_TYPES:
        signal_type = hint
    elif financial_metric in _CAP_RISK_FINANCIAL:
        signal_type = "capital_structure_risk"
        forced_direction = "deteriorating"
    elif financial_metric in _ECON_FINANCIAL:
        signal_type = "economic_inflection"
    elif catalyst_type or source_type in _CATALYST_SOURCE_TYPES:
        ct = str(catalyst_type or "").lower()
        is_cap = (expected_direction == "negative") or any(t in ct for t in _CAP_STRUCTURE_TOKENS)
        signal_type = "capital_structure_risk" if is_cap else "catalyst"
        if is_cap:
            forced_direction = "deteriorating"
    else:
        signal_type = _TYPE_BY_SOURCE.get(source_type, "adoption")

    metric_value = _num(c.get("metric_value"))
    prior_value = _num(c.get("prior_value"))
    consensus = _num(c.get("consensus_expectation"))
    observed_change = c.get("observed_change")
    polarity = c.get("polarity")

    # --- surprise vs consensus --------------------------------------------
    surprise = 0.0
    if metric_value is not None and consensus not in (None, 0):
        surprise = min(1.0, abs(metric_value - consensus) / abs(consensus))

    # --- direction + magnitude --------------------------------------------
    # Precedence: a forced capital-structure deterioration, then a stated catalyst
    # expected_direction, then the metric move / observed_change / legacy polarity.
    if forced_direction is not None:
        direction = forced_direction
        if metric_value is not None and prior_value not in (None, 0):
            magnitude = min(1.0, abs((metric_value - prior_value) / prior_value) / 0.30)
        else:
            magnitude = 0.5
    elif expected_direction in ("positive", "negative"):
        direction = "improving" if expected_direction == "positive" else "deteriorating"
        magnitude = 0.5
    elif metric_value is not None and prior_value not in (None, 0):
        pct = (metric_value - prior_value) / abs(prior_value)
        if pct > 0.02:
            direction = "improving"
        elif pct < -0.02:
            direction = "deteriorating"
        else:
            direction = "neutral"
        magnitude = min(1.0, abs(pct) / 0.30)
    elif observed_change in ("up", "down", "flat"):
        direction = {"up": "improving", "down": "deteriorating", "flat": "neutral"}[observed_change]
        magnitude = 0.1 if observed_change == "flat" else 0.5
    elif polarity in ("supportive", "contradictory", "neutral"):
        direction = {"supportive": "improving", "contradictory": "deteriorating",
                     "neutral": "neutral"}[polarity]
        magnitude = min(1.0, float(c.get("signal_strength") or 1.0))
    else:
        direction = "neutral"
        magnitude = 0.1

    # strength is INFERRED (never the hand-fed signal_strength directly).
    strength = _clamp01(0.6 * magnitude + 0.4 * surprise)

    # novelty -- from the novelty hint, lifted by any consensus surprise.
    novelty_hint = _level(c.get("novelty"), _NOVELTY_LEVELS, 0.0)
    novelty = max(novelty_hint, surprise)

    # evidence quality -- a DISTINCT dimension from strength. Catalyst confirmation
    # discipline: discount evidence_quality by the status weight, so a speculative
    # rumor ends with very low evidence_quality and cannot raise IA confidence.
    eq = _level(c.get("evidence_quality"), _LEVELS, None)
    if eq is None:
        eq = _level(c.get("source_reliability"), _LEVELS, 0.5)
    eq = _clamp01(eq * _STATUS_WEIGHT.get(catalyst_status, 1.0))
    monitoring_only = catalyst_status in ("possible", "speculative_rumor")

    signal = RealitySignal(
        signal_id=stable_id("SIG", getattr(o, "id", ""), signal_type, direction),
        signal_type=signal_type,
        direction=direction,
        strength=round(strength, 4),
        novelty=round(novelty, 4),
        evidence_quality=round(eq, 4),
        as_of=str(c.get("as_of", "")),
        supporting_evidence_ids=(getattr(o, "id", ""),),
        uncertainty=str(c.get("uncertainty_notes") or ""),
        monitoring_only=monitoring_only,
    )
    return signal, str(c.get("entity") or "")


def generate_intelligence_assessment(
    observations,
    *,
    domain: Optional[str] = None,
    assessment_type: Optional[str] = None,
    actor: str = "reality-intelligence",
    now: float,
    confidence: Optional[float] = None,
) -> IntelligenceAssessment:
    """Synthesise an IntelligenceAssessment by INFERRING typed signals from the
    structured facts of one or more Observations.

    Validation: at least one Observation is required; the assessment binds the
    exact ``(id, version)`` of every Observation; Observations are never mutated;
    and the result carries no investment-decision language. ``assessment_type``
    and ``confidence`` are inferred unless explicitly overridden by the caller.
    """
    obs = list(observations)
    if not obs:
        raise ValueError("an Intelligence Assessment requires at least one Observation")
    if assessment_type is not None and assessment_type not in ALLOWED_ASSESSMENT_TYPES:
        raise ValueError("unknown assessment_type: {0}".format(assessment_type))

    contents = [_content(o) for o in obs]
    obs_domains = {c.get("domain") for c in contents if c.get("domain")}
    if domain is None:
        domain = obs_domains.pop() if len(obs_domains) == 1 else "unspecified"

    entities = tuple(sorted({c.get("entity") for c in contents if c.get("entity")}))

    # --- 1. extract one typed signal per observation -----------------------
    extracted = [_extract_signal(o, c) for o, c in zip(obs, contents)]
    base = [s for s, _ in extracted]
    sig_entities = [e for _, e in extracted]

    # --- 2. corroboration + contradiction across signals -------------------
    has_improving = any(s.direction == "improving" for s in base)
    has_deteriorating = any(s.direction == "deteriorating" for s in base)

    signals = []
    corroborations = []
    for i, s in enumerate(base):
        corro = sum(
            1 for j, o2 in enumerate(base)
            if j != i and o2.signal_type == s.signal_type and o2.direction == s.direction
        )
        corroborations.append(corro)
        contradiction_flag = (
            (s.direction == "improving" and has_deteriorating)
            or (s.direction == "deteriorating" and has_improving)
        )
        is_weak = (
            s.strength <= 0.45 and s.novelty >= 0.7
            and corro <= 1 and s.evidence_quality >= 0.4
        )
        signals.append(RealitySignal(
            signal_id=s.signal_id,
            signal_type=s.signal_type,
            direction=s.direction,
            strength=s.strength,
            novelty=s.novelty,
            evidence_quality=s.evidence_quality,
            as_of=s.as_of,
            supporting_evidence_ids=s.supporting_evidence_ids,
            uncertainty=s.uncertainty,
            contradiction_flag=contradiction_flag,
            is_weak=is_weak,
            monitoring_only=s.monitoring_only,
        ))
    signals = tuple(signals)
    weak_signals = tuple(s for s in signals if s.is_weak)

    # --- 3. typed indicators (one note per signal of that type) ------------
    indicators = {st: [] for st in SIGNAL_TYPES}
    for s in signals:
        note = _INDICATOR_PHRASING[s.signal_type][s.direction]
        indicators[s.signal_type].append(
            "{0} ({1} {2})".format(note, s.signal_type, s.direction)
        )

    # --- 3b. catalyst + capital-structure structured records ---------------
    # These records may hold the raw catalyst facts (evidence); they are NOT routed
    # through the synthesized-text leakage guard. The monitoring list, by contrast,
    # is synthesized and purpose-free.
    catalysts = []
    capital_structure_risks = []
    monitoring_signals = []
    for s, c in zip(signals, contents):
        if s.signal_type == "catalyst":
            catalysts.append({
                "catalyst_type": c.get("catalyst_type"),
                "catalyst_status": c.get("catalyst_status"),
                "expected_direction": c.get("expected_direction"),
                "expected_timing_window": c.get("expected_timing_window"),
                "expected_business_impact": c.get("expected_business_impact"),
                "affected_value_chain_node": c.get("affected_value_chain_node"),
                "novelty": s.novelty,
                "evidence_quality": s.evidence_quality,
                "monitoring_only": s.monitoring_only,
                "supporting_evidence_ids": s.supporting_evidence_ids,
            })
        elif s.signal_type == "capital_structure_risk":
            ct = str(c.get("catalyst_type") or "").lower()
            fm = c.get("financial_metric")
            dilution_flag = (
                any(t in ct for t in ("dilution", "atm", "shelf", "offering",
                                      "convertible", "warrant"))
                or fm in ("dilution_risk", "shelf", "atm")
            )
            capital_structure_risks.append({
                "risk_type": c.get("catalyst_type") or fm or "capital_structure_risk",
                "expected_direction": c.get("expected_direction") or s.direction,
                "dilution_flag": dilution_flag,
                "evidence_quality": s.evidence_quality,
                "supporting_evidence_ids": s.supporting_evidence_ids,
            })
        if s.monitoring_only:
            status = c.get("catalyst_status") or "unconfirmed"
            monitoring_signals.append(
                "a {0} {1} ({2}) is monitoring-only pending confirmation".format(
                    status, s.signal_type, s.direction)
            )
    catalysts = tuple(catalysts)
    capital_structure_risks = tuple(capital_structure_risks)
    monitoring_signals = tuple(monitoring_signals)

    # --- 4. inferred assessment-level fields -------------------------------
    def _sign(d):
        return 1.0 if d == "improving" else -1.0 if d == "deteriorating" else 0.0

    net = sum(_sign(s.direction) * s.strength * s.evidence_quality for s in signals)
    eps = 1e-9
    direction = "improving" if net > eps else "deteriorating" if net < -eps else "mixed"

    max_strength = max((s.strength for s in signals), default=0.0)
    num_types = len({s.signal_type for s in signals})
    sig_score = 0.6 * max_strength + 0.4 * min(1.0, num_types / 3.0)
    significance = "high" if sig_score >= 0.7 else "moderate" if sig_score >= 0.45 else "low"

    # contradiction notes -- structural, never quoting raw excerpts.
    improving = [s for s in signals if s.direction == "improving"]
    deteriorating = [s for s in signals if s.direction == "deteriorating"]
    contradictions: Tuple[str, ...] = ()
    if improving and deteriorating:
        minority, opposite = (
            (deteriorating, improving) if len(deteriorating) <= len(improving)
            else (improving, deteriorating)
        )
        opp_dir = opposite[0].direction
        notes = []
        for s, ent in zip(signals, sig_entities):
            if s in minority:
                notes.append(
                    "a {0} {1} signal for {2} opposes {3} {4} signal(s)".format(
                        s.direction, s.signal_type, ent or "the domain",
                        len(opposite), opp_dir,
                    )
                )
        contradictions = tuple(notes)
    num_contradictions = len(contradictions)

    # confidence -- distinct from novelty and from strength.
    total_strength = sum(s.strength for s in signals)
    if total_strength > 0:
        weighted_eq = sum(s.strength * s.evidence_quality for s in signals) / total_strength
    else:
        weighted_eq = (sum(s.evidence_quality for s in signals) / len(signals)) if signals else 0.0
    num_corroborated = sum(1 for c in corroborations if c >= 1)
    corroboration_ratio = num_corroborated / len(signals) if signals else 0.0
    if confidence is None:
        confidence = _clamp(
            weighted_eq * (0.6 + 0.4 * corroboration_ratio) - 0.10 * num_contradictions
        )

    signal_novelty = round(max((s.novelty for s in signals), default=0.0), 4)
    agg_evidence_quality = round(weighted_eq, 4)

    # --- 5. assessment type (inferred unless overridden) -------------------
    if assessment_type is None:
        if signals:
            strength_by_type = {}
            for s in signals:
                strength_by_type[s.signal_type] = strength_by_type.get(s.signal_type, 0.0) + s.strength
            dominant = max(sorted(strength_by_type), key=lambda t: strength_by_type[t])
            resolved_type = _ASSESSMENT_TYPE_BY_SIGNAL.get(dominant, "domain_state")
        else:
            resolved_type = "domain_state"
    else:
        resolved_type = assessment_type

    # --- 6. synthesised purpose-free text ----------------------------------
    entity_str = ", ".join(entities) if entities else "the domain"
    type_str = ", ".join(sorted({s.signal_type for s in signals})) if signals else "no signal"
    change_notes = []
    for st in ("readiness", "constraint", "adoption", "supply_chain",
               "economic_inflection", "market_recognition", "catalyst",
               "capital_structure_risk"):
        for n in indicators[st]:
            change_notes.append(n.split(" (")[0])
    domain_reality_change = "{0} reality: {1}.".format(
        domain, "; ".join(change_notes) if change_notes else "no directional change detected"
    )

    current_assessment = (
        "{0} for {1}: {2}; {3} signal(s) ({4} weak) across {5}; significance {6}.".format(
            domain, entity_str, direction,
            len(signals), len(weak_signals), type_str, significance,
        )
    )

    weak_note = "{0} weak/novel signal(s) surfaced".format(len(weak_signals))
    uncertainty = (
        "derived from {0} structured observation(s); {1} opposing-direction signal pair(s); "
        "{2}; deterministic MVP rule-based inference (no autonomous research)".format(
            len(obs), num_contradictions, weak_note),
    )

    indicator_blob = " ".join(
        n for st in SIGNAL_TYPES for n in indicators[st]
    )
    _assert_no_leakage(
        current_assessment, domain_reality_change, indicator_blob,
        " ".join(contradictions), " ".join(uncertainty), " ".join(monitoring_signals),
        resolved_type, str(domain),
    )

    grounding_ids = tuple(o.id for o in obs)
    sources = tuple(o.ref("Observation") for o in obs)  # binds exact (id, version)
    oid = stable_id("IA", str(domain), resolved_type, *grounding_ids)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return IntelligenceAssessment(
        id=oid,
        version=1,
        provenance=prov,
        assessment_type=resolved_type,
        domain=str(domain),
        current_assessment=current_assessment,
        direction=direction,
        significance=significance,
        confidence=round(float(confidence), 4),
        grounding_observation_ids=grounding_ids,
        uncertainty=uncertainty,
        contradictions=contradictions,
        signals=signals,
        weak_signals=weak_signals,
        constraint_indicators=tuple(indicators["constraint"]),
        readiness_indicators=tuple(indicators["readiness"]),
        adoption_indicators=tuple(indicators["adoption"]),
        supply_chain_indicators=tuple(indicators["supply_chain"]),
        economic_inflection_indicators=tuple(indicators["economic_inflection"]),
        market_recognition_indicators=tuple(indicators["market_recognition"]),
        domain_reality_change=domain_reality_change,
        signal_novelty=signal_novelty,
        evidence_quality=agg_evidence_quality,
        entities=entities,
        catalysts=catalysts,
        capital_structure_risks=capital_structure_risks,
        catalyst_indicators=tuple(indicators["catalyst"]),
        capital_structure_risk_indicators=tuple(indicators["capital_structure_risk"]),
        monitoring_signals=monitoring_signals,
    )


def make_intelligence_assessment(
    observations, subject="", assessment="", actor="reality-intelligence",
    now=0, confidence=None, assessment_type="domain_state", domain=None,
):
    """Backward-compatible convenience constructor used to thread the slice.

    Runs the real synthesis. ``subject`` is taken as the domain hint; ``assessment``
    is accepted for source compatibility but the current assessment is *inferred
    from the Observations*, not from this label. ``assessment_type`` is passed
    through as an explicit override (its default keeps legacy callers stable).
    """
    return generate_intelligence_assessment(
        observations,
        domain=(domain if domain is not None else (subject or None)),
        assessment_type=assessment_type,
        actor=actor,
        now=now,
        confidence=confidence,
    )
