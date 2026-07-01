"""Staged adapters that PREPARE terrain nodes from pipeline outputs (fixture/demo).

IMPLEMENTATION-010B seam. These are PURE mapping functions from prior, already-computed
pipeline objects (an investment thesis, an intelligence assessment, a red-team summary,
the IREN evidence-alpha slice) into the typed terrain nodes of :mod:`universe_ui.terrain`.

They do NOT perform any live data access, scheduling, broker automation, or new scoring,
and they do NOT mutate the upstream reasoning objects -- they only READ existing fields
and re-express them as metadata. Today ``terrain_from_slice`` returns the demo terrain
(the one real anchor is IREN, already wired through the demo terrain). The full
live-wiring -- building a terrain node PER pipeline candidate -- lands in a later phase;
these functions define the boundary and the field mapping now.

Deterministic, stdlib-only, Python 3.9. No network, no clock, no secrets.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from .demo_terrain import _catalyst_status, build_demo_terrain
from .terrain import CatalystNode, CompanyNode, RiskNode, VisualEncoding
from .view_models import assign_buckets, card_label_for, glow_level, visual_size


def _get(obj: Any, name: str, default=None):
    """Read a field from a dataclass/object OR a dict, without mutating it."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def company_node_from_thesis(thesis: Any, *, node_id: str, ticker: str,
                             company_name: str = "", theme_id: str = "",
                             value_chain_id: str = "", bottleneck_id: str = "",
                             value_chain_role: str = "", directness_to_bottleneck: str = "",
                             market_cap: Optional[float] = None, data_quality: str = "medium",
                             is_real: bool = False, cockpit_link: Optional[str] = None,
                             source_refs: Tuple[str, ...] = (),
                             recommendation_label: str = "") -> CompanyNode:
    """Map an already-computed investment thesis into a :class:`CompanyNode`.

    Reads EXISTING thesis fields (investability_assessment / timing_confirmation /
    red-team verdict); introduces no new score. Does not modify ``thesis``.
    """
    investability = _get(thesis, "investability_assessment", "") or ""
    timing = ("timing confirmed" if bool(_get(thesis, "timing_confirmation", False))
              else "timing not confirmed")
    red_team = _get(_get(thesis, "red_team_summary"), "red_team_verdict", "") or ""
    severe = (red_team or "").lower() in ("concern", "fail")

    primary, _cross = assign_buckets(
        investability_label=investability, timing_label=timing, red_team_label=red_team,
        recommendation_label=recommendation_label, catalyst_label="",
        capital_structure_risk=severe, data_quality=data_quality, evidence_count=0)
    bucket = "{0} ({1})".format(primary, card_label_for(primary, investability))

    return CompanyNode(
        id=node_id, ticker=ticker, company_name=company_name or ticker, theme_id=theme_id,
        value_chain_id=value_chain_id, bottleneck_id=bottleneck_id,
        value_chain_role=value_chain_role, directness_to_bottleneck=directness_to_bottleneck,
        market_cap=market_cap, candidate_bucket=bucket, thesis_status=investability,
        timing_confirmation_status=timing, red_team_status=red_team,
        dilution_or_capital_structure_warnings=(
            ("capital-structure / dilution risk flagged",) if severe else ()),
        data_quality=data_quality, is_real=is_real, cockpit_link=cockpit_link,
        source_refs=tuple(source_refs),
        visual_encoding=VisualEncoding(
            size_value=visual_size(market_cap, "planet"),
            size_basis="market_cap (economic magnitude)",
            glow_level=glow_level(investability_label=investability, timing_label=timing,
                                  recommendation_label=recommendation_label),
            glow_basis="thesis status", red_shadow=severe,
            dashed_outline=(market_cap is None), layout_group="company"),
    )


def catalyst_nodes_from_assessment(assessment: Any, *, related_object_id: str = "",
                                   evidence_quality: str = "") -> Tuple[CatalystNode, ...]:
    """Map catalyst-like entries from an assessment/cockpit panel into CatalystNodes.

    Accepts a catalyst panel (``positive_catalysts`` / ``negative_catalysts``) or a plain
    iterable of catalyst descriptions. Reads only; mutates nothing.
    """
    positives = _get(assessment, "positive_catalysts", None)
    negatives = _get(assessment, "negative_catalysts", None)
    if positives is None and negatives is None and assessment is not None:
        # A plain iterable of descriptions.
        try:
            positives = tuple(assessment)
        except TypeError:
            positives = ()
    out = []
    for i, c in enumerate(tuple(positives or ())):
        out.append(CatalystNode(
            id="cat-pos-{0}".format(i), related_object_id=related_object_id,
            catalyst_type="positive", description=str(c), status=_catalyst_status(str(c)),
            evidence_quality=evidence_quality))
    for i, c in enumerate(tuple(negatives or ())):
        out.append(CatalystNode(
            id="cat-neg-{0}".format(i), related_object_id=related_object_id,
            catalyst_type="negative", description=str(c), status=_catalyst_status(str(c)),
            evidence_quality=evidence_quality))
    return tuple(out)


def risk_nodes_from_red_team(red_team: Any, *, related_object_id: str = "",
                             evidence_quality: str = "") -> Tuple[RiskNode, ...]:
    """Map a red-team summary (or an iterable of concern strings) into RiskNodes."""
    verdict = _get(red_team, "red_team_verdict", "") or ""
    concerns = _get(red_team, "concerns", None)
    if concerns is None and red_team is not None and not verdict:
        try:
            concerns = tuple(red_team)
        except TypeError:
            concerns = ()
    concerns = tuple(concerns or ())
    if not concerns and verdict:
        concerns = (verdict,)
    return tuple(
        RiskNode(id="risk-{0}".format(i), related_object_id=related_object_id,
                 risk_type="red-team", description=str(c),
                 red_team_status=verdict or "concern", evidence_quality=evidence_quality)
        for i, c in enumerate(concerns))


def terrain_from_slice(iren_slice):
    """Prepare a :class:`UniverseTerrain` for the given slice.

    Today this returns the demo terrain (with IREN as the one real anchor). Live wiring
    -- projecting a terrain node per real pipeline candidate via the mappers above --
    comes in a later phase; this function is the single entry point that will change.
    """
    return build_demo_terrain(iren_slice)
