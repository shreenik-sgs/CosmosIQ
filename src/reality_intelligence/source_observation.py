"""Reality Intelligence -- the Observation input format for manually-supplied
source material.

An Observation here is the canonical, immutable record of one piece of
manually-supplied source material about a domain. It carries the raw excerpt plus
the *structured raw facts* extracted from it -- metric values, an observed
up/down/flat change, a novelty tag, a source-reliability tag -- from which the
Intelligence Assessment generator (``intelligence_assessment.py``) INFERS a typed
reality signal. The Observation itself makes no judgement and forms no opportunity
-- it is evidence, not an assessment.

MVP boundary: an Observation may carry manual *hints* (raw facts, a novelty tag, a
reliability tag, an optional ``signal_type_hint``). It must NOT carry the final
assessment's inferred direction / significance / confidence -- those are derived
downstream, never hand-fed. The legacy ``polarity`` / ``signal_strength`` fields
are still accepted (older callers/tests supply them) but are treated as a weak
fallback hint, not as a final verdict.

The Observation is content-addressed (a deterministic id over source type, entity,
excerpt, and as-of date), so the same source material always yields the same
Observation id, supporting deterministic replay.
"""

from __future__ import annotations

from typing import Optional, Tuple

from eios_core.canonical_objects import Observation
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

# The kinds of manually-supplied source material accepted in this MVP.
SOURCE_TYPES = frozenset({
    "earnings_excerpt",
    "news_excerpt",
    "analyst_note_excerpt",
    "filing_excerpt",
    "infrastructure_milestone",
    "capacity_power_demand_signal",
    # Catalyst / financial-report / capital-structure source material.
    "earnings_call_transcript",
    "sec_filing",
    "press_release",
    "investor_presentation",
    "management_guidance",
    "customer_announcement",
    "contract_win",
    "strategic_partnership",
    "capacity_reservation",
    "regulatory_event",
    "product_launch",
    "capital_structure_event",
    "financial_report",
})

# A catalyst's confirmation discipline (how settled the event is).
CATALYST_STATUSES = frozenset({"confirmed", "probable", "possible", "speculative_rumor"})

# The expected directional effect a catalyst would have on the domain reading.
EXPECTED_DIRECTIONS = frozenset({"positive", "negative"})

# Legacy polarity vocabulary. Retained for backward compatibility only -- newer
# Observations carry structured facts (metric/observed_change) instead.
POLARITIES = frozenset({"supportive", "contradictory", "neutral"})

# The observed direction of a raw change, when the source states one directly.
OBSERVED_CHANGES = frozenset({"up", "down", "flat"})


def make_source_observation(
    *,
    source_type: str,
    domain: str,
    entity: str,
    excerpt: str = "",
    as_of: str,
    # --- legacy hint fields (accepted, weak fallback only) -----------------
    polarity: str = "neutral",
    signal_strength: float = 1.0,
    metric: Optional[dict] = None,
    # --- structured raw-fact fields (preferred inputs) ---------------------
    entities: Tuple[str, ...] = (),
    raw_excerpt: str = "",
    metric_name: Optional[str] = None,
    metric_value: Optional[float] = None,
    metric_unit: Optional[str] = None,
    prior_value: Optional[float] = None,
    consensus_expectation: Optional[float] = None,
    source_reliability: Optional[object] = None,
    novelty: Optional[object] = None,
    signal_type_hint: Optional[str] = None,
    evidence_quality: Optional[object] = None,
    uncertainty_notes: str = "",
    observed_change: Optional[str] = None,
    # --- catalyst / financial-report fields (preferred inputs) -------------
    catalyst_type: Optional[str] = None,
    catalyst_status: Optional[str] = None,
    expected_direction: Optional[str] = None,
    expected_timing_window: Optional[str] = None,
    expected_business_impact: Optional[str] = None,
    affected_value_chain_node: Optional[str] = None,
    affected_domain: Optional[str] = None,
    financial_metric: Optional[str] = None,
    # --- provenance --------------------------------------------------------
    source_ref: str = "",
    actor: str = "analyst",
    now: float,
) -> Observation:
    """Build an Observation from a single manually-supplied source excerpt.

    ``now`` is explicit epoch-seconds (deterministic); ``as_of`` is the date the
    source material refers to. ``excerpt`` and ``raw_excerpt`` are aliases -- pass
    either (at least one must be non-empty). Structured facts (``metric_value`` /
    ``prior_value`` / ``observed_change`` / ``novelty`` / ``source_reliability`` /
    ``signal_type_hint``) are the preferred inputs; the assessment infers the
    typed signal from them. ``polarity`` / ``signal_strength`` remain accepted as
    a legacy fallback hint.

    Validation is strict: unknown source types, polarities, or observed-change
    values are rejected, and the excerpt may not be empty.
    """
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            "unknown source_type: {0} (allowed: {1})".format(source_type, sorted(SOURCE_TYPES))
        )
    if polarity not in POLARITIES:
        raise ValueError(
            "unknown polarity: {0} (allowed: {1})".format(polarity, sorted(POLARITIES))
        )
    if observed_change is not None and observed_change not in OBSERVED_CHANGES:
        raise ValueError(
            "unknown observed_change: {0} (allowed: {1})".format(
                observed_change, sorted(OBSERVED_CHANGES))
        )
    if signal_type_hint is not None and not str(signal_type_hint).strip():
        raise ValueError("signal_type_hint, if given, must be non-empty")
    if catalyst_status is not None and catalyst_status not in CATALYST_STATUSES:
        raise ValueError(
            "unknown catalyst_status: {0} (allowed: {1})".format(
                catalyst_status, sorted(CATALYST_STATUSES))
        )
    if expected_direction is not None and expected_direction not in EXPECTED_DIRECTIONS:
        raise ValueError(
            "unknown expected_direction: {0} (allowed: {1})".format(
                expected_direction, sorted(EXPECTED_DIRECTIONS))
        )

    eff_excerpt = excerpt or raw_excerpt
    if not eff_excerpt or not eff_excerpt.strip():
        raise ValueError("a source Observation requires a non-empty excerpt")

    if entities:
        ents = tuple(entities)
    elif entity:
        ents = (entity,)
    else:
        ents = ()

    content = {
        "source_type": source_type,
        "domain": domain,
        "entity": entity,
        "entities": ents,
        "excerpt": eff_excerpt,
        "raw_excerpt": raw_excerpt or eff_excerpt,
        # legacy hints
        "polarity": polarity,
        "signal_strength": float(signal_strength),
        "metric": dict(metric) if metric else None,
        # structured raw facts
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit,
        "prior_value": prior_value,
        "consensus_expectation": consensus_expectation,
        "source_reliability": source_reliability,
        "novelty": novelty,
        "signal_type_hint": signal_type_hint,
        "evidence_quality": evidence_quality,
        "uncertainty_notes": uncertainty_notes,
        "observed_change": observed_change,
        # catalyst / financial-report facts
        "catalyst_type": catalyst_type,
        "catalyst_status": catalyst_status,
        "expected_direction": expected_direction,
        "expected_timing_window": expected_timing_window,
        "expected_business_impact": expected_business_impact,
        "affected_value_chain_node": affected_value_chain_node,
        "affected_domain": affected_domain,
        "financial_metric": financial_metric,
        "as_of": as_of,
        "source_ref": source_ref,
    }
    oid = stable_id("OBS", source_type, entity, eff_excerpt[:80], str(as_of))
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=())
    return Observation(id=oid, version=1, provenance=prov, content=content)
