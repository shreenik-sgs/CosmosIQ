"""Opportunity Prioritization -- REQ-GEN-019 (GEN-001, Opportunity Generation / layer 3).

The specification has always required this and it was never built:

    "Not every Opportunity carries equal significance. Genesis SHALL continuously prioritize
    Opportunities according to their expected significance." (GEN-001 §Opportunity Prioritization)

Its six factors -- magnitude, timing, confidence, breadth of impact, strength of grounding,
uncertainty -- are all already computed upstream and then thrown away: ``ThemePulse`` carries the
state, breadth, bottleneck and freshness labels; ``OpportunityHypothesisPacket`` carries the
grounding refs, the conflicts and the honest gaps. Nothing read them together and said which of
these matters most. This module does exactly that and nothing more.

WHERE THIS SITS. ADR-0008 fixes the layering: "Scientific Understanding -> Domain Understanding ->
Opportunity Formation", and "**Understanding flows upward through these layers; purpose never flows
downward**". Prioritising is a purpose. So it lives HERE, in Opportunity Formation, and reaches
back into nothing: it reads the pulses and packets the purpose-free core already produced and
never influences how they were produced. The core does not know it is being prioritised, which is
precisely what keeps the core trustworthy.

WHAT THIS IS NOT (GEN-001, verbatim):

    "Prioritization SHALL express relative significance, not investment recommendation."

Significance is a statement about the WORLD: how much does this opportunity matter, how broadly,
how well is it grounded, how sure are we, and is it happening now. It is NOT a claim that a name
will pay, and this module computes no such claim. Whether prioritisation may ever express expected
RETURN -- the "multibagger order" -- is a separate architectural question that would need its own
ADR; it is deliberately not answered here, and nothing in this file may be read as answering it.

NO HIDDEN NUMBER. The standing discipline is "no HIDDEN score / rank / rating -- every verdict is
a LABEL, a plain reason, or a qualitative range". So this module stores no number and no ordering
field. The ORDER IS THE OUTPUT: :func:`prioritize` returns the opportunities in order, each
carrying the closed :data:`SIGNIFICANCE_LABELS` verdict, the six factor labels it was formed from,
and a plain sentence saying why. The sort key is a tuple of label positions computed transiently
and never persisted -- the same ordinal-label idiom the fusion synthesizer already uses. A reader
can always reconstruct the order from the labels shown; there is nothing hidden to trust.

    "Prioritization SHALL remain continuously re-evaluable as understanding evolves."

Hence a pure function over the current pulses -- never a stored verdict that could go stale.

Deterministic (order-stable; ties broken by theme_id, never arbitrarily), stdlib-only, Python 3.9,
OFFLINE: no network, no wall-clock, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "SIGNIFICANCE_LABELS",
    "PrioritizedOpportunity",
    "prioritize",
    "significance_of",
]

# The verdict vocabulary -- closed, ordinal, and qualitative. "insufficient" is not the bottom of
# a scale, it is an HONEST ABSTENTION: too little is known to place this opportunity at all.
SIGNIFICANCE_LABELS: Tuple[str, ...] = (
    "insufficient", "slight", "moderate", "substantial", "decisive")

# Upstream label orders, mirrored here rather than imported, so layer 3 depends on the core's
# DATA and not on its internals. Weakest first; a label the core never emits sorts weakest.
_MAGNITUDE_ORDER: Tuple[str, ...] = (
    "unknown", "negligible", "minor", "moderate", "major", "extreme")
_CONFIDENCE_ORDER: Tuple[str, ...] = (
    "missing", "unknown", "very_low", "low", "moderate", "high", "very_high")
_FRESHNESS_ORDER: Tuple[str, ...] = ("expired", "stale", "aging", "recent", "fresh")

# TIMING: a theme's state says whether the opportunity is happening NOW. This is the one factor
# that is not monotone -- "Crowded"/"Exhausting" mean the move is largely spent, which is LESS
# significant to act on than "Igniting", not more. Ordered weakest-to-strongest by how much a
# fresh commitment could still matter.
_TIMING_ORDER: Tuple[str, ...] = (
    "Data insufficient", "Conflicted", "Breaking down", "Exhausting", "Crowded",
    "Dormant", "Warming", "Broadening", "Igniting")


def _index(order: Tuple[str, ...], label: object) -> int:
    """Position of ``label`` in ``order`` -- unknown labels sort weakest, never crash."""
    try:
        return order.index(str(label or "").strip())
    except ValueError:
        return 0


def _bucket(count: int, *, thresholds: Tuple[int, int, int]) -> int:
    """A count -> a 0..3 ordinal band. Counts are evidence VOLUME, never a score."""
    low, mid, high = thresholds
    if count >= high:
        return 3
    if count >= mid:
        return 2
    if count >= low:
        return 1
    return 0


_BAND_LABELS: Tuple[str, ...] = ("none", "narrow", "moderate", "broad")
_GROUNDING_LABELS: Tuple[str, ...] = ("ungrounded", "thin", "corroborated", "well_grounded")
_UNCERTAINTY_LABELS: Tuple[str, ...] = ("clean", "some_gaps", "material_gaps", "contested")


@dataclass(frozen=True)
class PrioritizedOpportunity:
    """One opportunity placed in the order, with the labels that placed it and a plain reason.

    Deliberately carries NO number and NO position field: the order is the tuple this arrives in.
    Storing a position would make the ordering a fact about the object rather than a currently-held
    judgment about a set -- and GEN-001 requires it stay "continuously re-evaluable".
    """

    hypothesis_id: str = ""
    theme_id: str = ""
    theme_name: str = ""
    significance_label: str = "insufficient"      # closed: SIGNIFICANCE_LABELS
    factors: Mapping[str, str] = field(default_factory=dict)   # the six, as labels
    why: str = ""                                  # a plain sentence, never a formula
    beneficiary_candidates: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.significance_label not in SIGNIFICANCE_LABELS:
            raise ValueError(
                "significance_label {0!r} invalid (allowed: {1})".format(
                    self.significance_label, list(SIGNIFICANCE_LABELS)))


def _factor_labels(pulse, packet) -> Dict[str, str]:
    """The six REQ-GEN-019 factors, read off what the core already computed. Nothing invented."""
    supporting = len(getattr(pulse, "supporting_signals", ()) or ())
    contradicting = len(getattr(pulse, "contradicting_signals", ()) or ())
    gaps = len(getattr(packet, "data_gaps", ()) or ()) + len(getattr(packet, "conflicts", ()) or ())
    refs = len(getattr(packet, "source_refs", ()) or ()) + len(
        getattr(packet, "supporting_evidence_refs", ()) or ())
    beneficiaries = len(getattr(packet, "beneficiary_candidates", ()) or ())

    uncertainty = _bucket(gaps + contradicting, thresholds=(1, 4, 8))
    return {
        # magnitude: how scarce is the capacity this theme is gated by
        "magnitude": str(getattr(pulse, "bottleneck_label", "") or "unknown"),
        # timing: is it happening now, or spent
        "timing": str(getattr(pulse, "state", "") or "Data insufficient"),
        # confidence: the core's own confidence in the hypothesis
        "confidence": str(getattr(packet, "confidence_label", "") or "missing"),
        # breadth of impact: how many companies the move reaches
        "breadth": _BAND_LABELS[_bucket(beneficiaries, thresholds=(1, 3, 6))],
        # strength of grounding: how much real evidence stands under it
        "grounding": _GROUNDING_LABELS[_bucket(refs, thresholds=(1, 3, 8))],
        # uncertainty: gaps + contradictions, surfaced not hidden (weakens significance)
        "uncertainty": _UNCERTAINTY_LABELS[uncertainty],
        "freshness": str(getattr(pulse, "freshness_label", "") or "missing"),
        "supporting_signals": str(supporting),
    }


def _key(factors: Mapping[str, str]) -> Tuple[int, ...]:
    """The transient sort key: label POSITIONS, never a stored number.

    Ordered by what makes an opportunity matter most, in declining priority: how scarce the gated
    capacity is, how sure we are, how well grounded it is, how broadly it reaches, whether it is
    happening now -- then LESS uncertainty and fresher evidence rank higher. Nothing is weighted or
    summed: this is a lexicographic comparison over ordinal labels, so no hidden arithmetic can
    smuggle a score in.
    """
    return (
        _index(_MAGNITUDE_ORDER, factors.get("magnitude")),
        _index(_CONFIDENCE_ORDER, factors.get("confidence")),
        _GROUNDING_LABELS.index(factors.get("grounding", "ungrounded")),
        _BAND_LABELS.index(factors.get("breadth", "none")),
        _index(_TIMING_ORDER, factors.get("timing")),
        -_UNCERTAINTY_LABELS.index(factors.get("uncertainty", "clean")),
        _index(_FRESHNESS_ORDER, factors.get("freshness")),
    )


def significance_of(factors: Mapping[str, str]) -> str:
    """The closed significance verdict for one factor set -- an honest abstention when thin.

    An opportunity is only as significant as its evidence permits: ungrounded, or confidence at
    ``missing``/``unknown``, or a theme with nothing to say, abstains as ``insufficient`` rather
    than being ranked low. Ranking a thing we know nothing about is a claim; abstaining is not.
    """
    grounding = factors.get("grounding", "ungrounded")
    confidence = factors.get("confidence", "missing")
    timing = factors.get("timing", "Data insufficient")
    if (grounding == "ungrounded" or confidence in ("missing", "unknown")
            or timing == "Data insufficient"):
        return "insufficient"

    strength = (
        _index(_MAGNITUDE_ORDER, factors.get("magnitude"))
        + _index(_CONFIDENCE_ORDER, confidence)
        + _GROUNDING_LABELS.index(grounding)
        + _BAND_LABELS.index(factors.get("breadth", "none"))
    )
    # A contested or materially-gapped opportunity cannot be "decisive", whatever else it has.
    contested = factors.get("uncertainty") in ("material_gaps", "contested")
    if strength >= 12 and not contested:
        return "decisive"
    if strength >= 9:
        return "substantial"
    if strength >= 5:
        return "moderate"
    return "slight"


def _why(factors: Mapping[str, str], label: str) -> str:
    """A plain sentence a reader can check against the labels -- never a formula or a number."""
    if label == "insufficient":
        return ("too little is established to place this yet -- grounding {0}, confidence {1}, "
                "theme {2}".format(factors.get("grounding"), factors.get("confidence"),
                                   factors.get("timing")))
    return ("{0} scarcity at the gated capacity, {1} confidence, {2} evidence, {3} reach, theme "
            "{4}; uncertainty {5}".format(
                factors.get("magnitude"), factors.get("confidence"), factors.get("grounding"),
                factors.get("breadth"), factors.get("timing"), factors.get("uncertainty")))


def prioritize(theme_pulses: Sequence[object],
               hypothesis_packets: Sequence[object]) -> Tuple[PrioritizedOpportunity, ...]:
    """Order the current opportunities by relative significance. Re-evaluable, never stored.

    Pairs each hypothesis packet with the theme pulse it came from and places them most-significant
    first. Ties break on ``theme_id`` so the order is stable rather than incidental. An
    ``insufficient`` opportunity is NOT dropped -- it is placed last, still visible, because what
    the system cannot yet judge is exactly what an operator most needs to see.

    Returns significance, not a recommendation (GEN-001). Nothing here says a name will pay.
    """
    by_pulse_id = {getattr(p, "theme_pulse_id", ""): p for p in (theme_pulses or ())}
    out: List[PrioritizedOpportunity] = []

    for packet in (hypothesis_packets or ()):
        pulse = by_pulse_id.get(str(getattr(packet, "theme_pulse", "") or ""))
        if pulse is None:
            # A packet whose pulse is absent is an honest gap, not a reason to guess a theme.
            continue
        factors = _factor_labels(pulse, packet)
        label = significance_of(factors)
        out.append(PrioritizedOpportunity(
            hypothesis_id=str(getattr(packet, "hypothesis_id", "") or ""),
            theme_id=str(getattr(pulse, "theme_id", "") or ""),
            theme_name=str(getattr(pulse, "theme_name", "") or ""),
            significance_label=label,
            factors=factors,
            why=_why(factors, label),
            beneficiary_candidates=tuple(getattr(packet, "beneficiary_candidates", ()) or ()),
            data_gaps=tuple(getattr(packet, "data_gaps", ()) or ())))

    out.sort(key=lambda o: (
        -SIGNIFICANCE_LABELS.index(o.significance_label), [-k for k in _key(o.factors)],
        o.theme_id))
    return tuple(out)
