"""Read-only projections for the Economic Universe UI (IMPLEMENTATION-010A).

Pure PROJECTION view models. They COPY and GROUP existing fields and statuses --
demo-terrain fields from :mod:`universe_ui.demo_universe`, and (for the one real
IREN planet) already-computed statuses from the evidence-alpha slice. They compute
NOTHING beyond grouping and formatting:

* **No new score.** There is no composite, master, ranking, or alpha number here.
  Candidate buckets are chosen from EXISTING pipeline statuses only
  (investability_assessment / timing_confirmation / red-team verdict /
  recommendation_status). Within-bucket ordering reuses an EXISTING field
  (``thesis_confidence`` for the real candidate; ``evidence_count`` for demo ones) --
  it defines no new metric and displays no composite figure.
* **Ticker/security mapping comes AFTER value-chain context**, never as the entry
  point -- carried with an explicit "derived after value-chain / winner mapping"
  qualifier.
* **Frozen & deterministic.** Plain frozen dataclasses, stdlib only, Python 3.9.

Nothing here places, routes, or records an order; nothing refreshes live data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .demo_universe import (
    DemoGalaxy,
    DemoPlanet,
    DemoUniverse,
    build_demo_universe,
    slugify,
)

# The one place the ticker/security qualifier text is defined.
SECURITY_MAPPING_QUALIFIER = (
    "Security / ticker mapping — derived after value-chain / winner mapping "
    "(never the entry point)"
)


def planet_universe_path(galaxy_slug: str, value_chain_slug: str, star_slug: str,
                         ticker: str) -> str:
    """The canonical zoom path to a planet inside the single universe canvas.

    Shared by the universe renderer (which builds the matching level-panel) and the
    dashboard "Locate in Universe" link, so the two never drift.
    """
    return "universe/g:{0}/t:{0}/vc:{1}/st:{2}/pl:{3}".format(
        galaxy_slug, value_chain_slug, star_slug, slugify(ticker))


# --------------------------------------------------------------------------- #
# Purely-visual size encoding -- a bounded formatting helper, NOT a ranking    #
# input. Size encodes economic MAGNITUDE (market_cap / TAM / revenue_pool /    #
# importance) only; it feeds no score, no bucket, and no ordering. Brightness  #
# (glow), colour, orbit and halo are driven by DIFFERENT fields (see below).   #
# --------------------------------------------------------------------------- #
MIN_PX = 30
MAX_PX = 120
DEFAULT_PX = 46   # neutral size used when a magnitude is MISSING (with a gap marker)

# (low, high) magnitude bounds per object kind -- used only to normalise the
# bounded log scale so a trillion-dollar object never dwarfs a small one away.
_MAG_BOUNDS = {
    "planet": (1.0e8, 4.0e12),        # market cap
    "galaxy": (1.0e10, 5.0e13),       # theme TAM
    "solar_system": (1.0e9, 2.0e12),  # value-chain revenue pool
    "star": (1.0, 100.0),             # bottleneck economic importance
    "moon": (1.0e8, 4.0e12),          # dependency exposure
}


def visual_size(value: Optional[float], kind: str = "planet") -> int:
    """Bounded log-scaled pixel size for an economic magnitude (pure formatter).

    Monotonically increasing in ``value`` (larger magnitude -> larger px) but bounded
    to ``[MIN_PX, MAX_PX]`` via a log scale, so a trillion-dollar object is bigger yet
    never crushes a small asymmetric one into invisibility. A missing / non-positive
    magnitude returns the neutral :data:`DEFAULT_PX` (the caller flags the data gap).

    This is a VISUAL helper only: its output is never used as a score, a bucket key,
    or an ordering key anywhere in this package.
    """
    if value is None:
        return DEFAULT_PX
    try:
        v = float(value)
    except (TypeError, ValueError):
        return DEFAULT_PX
    if v <= 0:
        return DEFAULT_PX
    lo, hi = _MAG_BOUNDS.get(kind, _MAG_BOUNDS["planet"])
    v = max(lo, min(hi, v))
    span = math.log10(hi) - math.log10(lo)
    frac = 0.0 if span <= 0 else (math.log10(v) - math.log10(lo)) / span
    return int(round(MIN_PX + frac * (MAX_PX - MIN_PX)))


def glow_level(*, investability_label: str, timing_label: str,
               recommendation_label: str) -> int:
    """Brightness / glow tier (1 dim .. 3 bright) from EXISTING alpha statuses only.

    Brightness encodes signal heat / conviction from status -- it is DECOUPLED from
    economic size, so a small-cap with a strong status glows brighter than a mega-cap
    with a weak one. It is a categorical projection of existing statuses, not a new
    composite metric, and feeds no bucket or ordering.
    """
    inv = (investability_label or "").lower()
    rec = (recommendation_label or "").lower()
    t = (timing_label or "").lower()
    timing_ok = "confirmed" in t and "not confirmed" not in t
    if rec == "blocked_for_user" or inv == "not_investable":
        return 1
    if rec == "priority_candidate" or inv == "thesis_worthy_timing_confirmed" or timing_ok:
        return 3
    if inv == "thesis_worthy" or rec == "suitable_candidate":
        return 2
    return 1

# CIO dashboard bucket names (from EXISTING statuses only).
BUCKET_HIGHEST_CONVICTION = "Highest Conviction"
BUCKET_TIMING_CONFIRMED = "Timing-Confirmed"
BUCKET_EARLY_WATCHLIST = "Early Watchlist"
BUCKET_RESEARCH_DEEPER = "Research Deeper"
BUCKET_NEEDS_MORE_EVIDENCE = "Needs More Evidence"
BUCKET_BLOCKED_AVOID = "Blocked/Avoid"
BUCKET_CATALYST_WATCH = "Catalyst Watch"
BUCKET_RED_TEAM_ALERTS = "Red-Team Alerts"

BUCKET_ORDER = (
    BUCKET_HIGHEST_CONVICTION,
    BUCKET_TIMING_CONFIRMED,
    BUCKET_EARLY_WATCHLIST,
    BUCKET_RESEARCH_DEEPER,
    BUCKET_NEEDS_MORE_EVIDENCE,
    BUCKET_BLOCKED_AVOID,
    BUCKET_CATALYST_WATCH,
    BUCKET_RED_TEAM_ALERTS,
)

_BUCKET_DESCRIPTIONS = {
    BUCKET_HIGHEST_CONVICTION: "recommendation_status = priority_candidate",
    BUCKET_TIMING_CONFIRMED: "investability = thesis_worthy_timing_confirmed / timing confirmed",
    BUCKET_EARLY_WATCHLIST: "investability = watch / recommendation = monitor_only",
    BUCKET_RESEARCH_DEEPER: "investability = thesis_worthy / recommendation = wait_for_user / reduced_size",
    BUCKET_NEEDS_MORE_EVIDENCE: "evidence-limited: low data quality or thin evidence count",
    BUCKET_BLOCKED_AVOID: "recommendation = blocked_for_user / not_investable / red-team fail",
    BUCKET_CATALYST_WATCH: "has a tracked catalyst (cross-cut)",
    BUCKET_RED_TEAM_ALERTS: "red-team concern/fail or capital-structure risk (cross-cut)",
}


# --------------------------------------------------------------------------- #
# Frozen view models                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NodeView:
    node_id: str
    tier: str
    role: str
    economics_capture: str
    bottleneck_exposure: str
    evidence_quality: str
    missing_data: Tuple[str, ...]
    candidate_companies: Tuple[str, ...]
    has_dynamic_evidence: bool          # always False in demo (static-terrain seam)
    dynamic_evidence_note: str
    dependency_exposure: Optional[float]  # visual magnitude only (moon)
    visual_size_px: int
    magnitude_missing: bool
    data_origin: str


@dataclass(frozen=True)
class PlanetCandidateView:
    candidate_id: str
    ticker: str
    company: str
    galaxy_name: str
    galaxy_slug: str
    value_chain_role: str
    proximity_to_bottleneck: str
    investability_label: str
    timing_label: str
    red_team_label: str
    recommendation_label: str
    catalyst_label: str
    capital_structure_risk: bool
    evidence_count: int
    data_quality: str
    is_real: bool
    security_mapping_qualifier: str
    cockpit_link: Optional[str]
    locate_link: str
    provenance_available: bool
    ordering_value: float
    source_authority_badges: Tuple[str, ...]
    market_cap: Optional[float]         # visual magnitude only
    visual_size_px: int                 # bounded log-scaled size (NOT a ranking input)
    magnitude_missing: bool             # True -> neutral size + data-gap marker
    glow_level: int                     # brightness tier from status (NOT from size)
    universe_path: str                  # canonical zoom path into the universe canvas
    data_origin: str


@dataclass(frozen=True)
class CandidateCardView:
    candidate_id: str
    ticker: str
    company: str
    galaxy_name: str
    galaxy_slug: str
    value_chain_role: str
    proximity_to_bottleneck: str
    card_label: str                     # manual review / timing / thesis / watchlist / ...
    investability_label: str
    timing_label: str
    red_team_label: str
    recommendation_label: str
    catalyst_label: str
    capital_structure_risk: bool
    data_quality: str
    evidence_count: int
    is_real: bool
    security_mapping_qualifier: str
    cockpit_link: Optional[str]
    locate_link: str
    provenance_available: bool
    primary_bucket: str
    cross_cut_buckets: Tuple[str, ...]
    ordering_value: float
    source_authority_badges: Tuple[str, ...]
    market_cap: Optional[float]         # visual magnitude only
    visual_size_px: int                 # bounded log-scaled size (NOT a ranking input)
    magnitude_missing: bool
    glow_level: int                     # brightness tier from status (NOT from size)
    universe_path: str                  # canonical zoom path (for "Locate in Universe")
    data_origin: str


@dataclass(frozen=True)
class BucketView:
    name: str
    description: str
    cards: Tuple[CandidateCardView, ...]


@dataclass(frozen=True)
class GalaxyClusterView:
    theme_name: str
    slug: str
    megatrend: str
    capital_cycle: str
    heat_label: str
    priority_label: str
    signal_convergence: str
    evidence_count: int
    data_quality: str
    bottleneck_severity: str
    candidate_count: int
    maturity_timing: str
    crowded_euphoric: bool
    red_team_risk: bool
    data_poor: bool
    theme_tam: Optional[float]          # visual magnitude only
    megatrend_magnitude: Optional[float]
    visual_size_px: int                 # bounded log-scaled size (NOT a ranking input)
    magnitude_missing: bool             # True -> neutral size + data-gap marker
    data_origin: str


@dataclass(frozen=True)
class StarBottleneckView:
    galaxy_name: str
    galaxy_slug: str
    slug: str
    star_type: str
    constrained_node: str
    severity: str
    duration: str
    beneficiaries: Tuple[str, ...]
    losers: Tuple[str, ...]
    resolution_risk: str
    evidence: Tuple[str, ...]
    data_gaps: Tuple[str, ...]
    bottleneck_economic_importance: Optional[float]
    visual_size_px: int
    magnitude_missing: bool
    data_origin: str


@dataclass(frozen=True)
class SolarSystemValueChainView:
    galaxy_name: str
    galaxy_slug: str
    name: str
    slug: str
    description: str
    nodes: Tuple[NodeView, ...]
    security_mapping_qualifier: str
    node_ticker_map: Tuple[Tuple[str, Tuple[str, ...]], ...]  # (node role, tickers) AFTER chain
    value_chain_revenue_pool: Optional[float]
    visual_size_px: int
    magnitude_missing: bool
    data_origin: str


@dataclass(frozen=True)
class GalaxyThemeView:
    cluster: GalaxyClusterView
    why_now: str
    why_before_obvious: str
    confirmed_signals: Tuple[str, ...]
    speculative_signals: Tuple[str, ...]
    positive_catalysts: Tuple[str, ...]
    negative_catalysts: Tuple[str, ...]
    red_team_notes: Tuple[str, ...]
    data_gaps: Tuple[str, ...]
    solar_systems: Tuple[SolarSystemValueChainView, ...]
    stars: Tuple[StarBottleneckView, ...]
    planets: Tuple[PlanetCandidateView, ...]


@dataclass(frozen=True)
class CIODashboardView:
    banner: str
    buckets: Tuple[BucketView, ...]
    total_candidates: int
    real_candidate_count: int


@dataclass(frozen=True)
class DataQualityView:
    run_mode: str
    fixture_demo_status: str
    live_enabled: bool
    scheduler_status: str
    broker_automation_status: str
    manual_review_required: bool
    source_hierarchy: str
    canonical_count: int
    convenience_count: int
    fallback_count: int
    signal_observation_count: int
    factual_observation_count: int
    conflict_warnings: Tuple[str, ...]
    overridden_facts: Tuple[str, ...]
    data_gaps: Tuple[str, ...]
    provenance_chain: Tuple[str, ...]
    real_subject: str


@dataclass(frozen=True)
class ThemeEdgeView:
    """A validated semantic relationship between two galaxies (both must exist)."""
    source_slug: str
    target_slug: str
    source_name: str
    target_name: str
    type: str
    reason: str
    strength: str
    evidence_quality: str


@dataclass(frozen=True)
class EconomicUniverseView:
    mode: str
    live_enabled: bool
    scheduler_enabled: bool
    broker_automation_enabled: bool
    clusters: Tuple[GalaxyClusterView, ...]
    themes: Tuple[GalaxyThemeView, ...]
    edges: Tuple[ThemeEdgeView, ...]
    dashboard: CIODashboardView
    data_quality: DataQualityView
    real_subject: str
    # The typed knowledge terrain this view was PROJECTED FROM (source of truth).
    terrain: object = None


# --------------------------------------------------------------------------- #
# Bucket + label mapping (from EXISTING statuses only -- no new score)         #
# --------------------------------------------------------------------------- #
def _timing_confirmed(timing_label: str) -> bool:
    t = (timing_label or "").lower()
    return "confirmed" in t and "not confirmed" not in t


def assign_buckets(*, investability_label: str, timing_label: str, red_team_label: str,
                   recommendation_label: str, catalyst_label: str,
                   capital_structure_risk: bool, data_quality: str,
                   evidence_count: int) -> Tuple[str, Tuple[str, ...]]:
    """Map EXISTING statuses -> (primary bucket, cross-cut buckets). No computation."""
    inv = (investability_label or "").lower()
    rec = (recommendation_label or "").lower()
    rt = (red_team_label or "").lower()
    dq = (data_quality or "").lower()

    if rec == "blocked_for_user" or inv == "not_investable" or rt == "fail":
        primary = BUCKET_BLOCKED_AVOID
    elif rec == "priority_candidate":
        primary = BUCKET_HIGHEST_CONVICTION
    elif inv == "thesis_worthy_timing_confirmed" or _timing_confirmed(timing_label):
        primary = BUCKET_TIMING_CONFIRMED
    elif inv == "thesis_worthy" or rec in ("wait_for_user", "reduced_size_candidate"):
        primary = BUCKET_RESEARCH_DEEPER
    elif dq in ("low", "sparse") or int(evidence_count) < 4:
        primary = BUCKET_NEEDS_MORE_EVIDENCE
    else:
        primary = BUCKET_EARLY_WATCHLIST

    cross = []
    if (catalyst_label or "").strip():
        cross.append(BUCKET_CATALYST_WATCH)
    if rt in ("concern", "fail") or capital_structure_risk:
        cross.append(BUCKET_RED_TEAM_ALERTS)
    return primary, tuple(cross)


def card_label_for(primary_bucket: str, investability_label: str) -> str:
    """Human card label from the primary bucket (no buy/sell language)."""
    if primary_bucket == BUCKET_HIGHEST_CONVICTION:
        return "thesis candidate"
    if primary_bucket == BUCKET_TIMING_CONFIRMED:
        return "timing candidate"
    if primary_bucket == BUCKET_RESEARCH_DEEPER:
        return "manual review candidate"
    if primary_bucket == BUCKET_NEEDS_MORE_EVIDENCE:
        return "evidence-limited"
    if primary_bucket == BUCKET_BLOCKED_AVOID:
        return "avoid" if (investability_label or "").lower() == "not_investable" else "blocked"
    return "watchlist"


# --------------------------------------------------------------------------- #
# Real IREN status extraction (copied from the slice; nothing recomputed)      #
# --------------------------------------------------------------------------- #
def _iren_real_status(iren_slice) -> dict:
    """Copy IREN's already-computed statuses out of the evidence-alpha slice."""
    thesis = iren_slice.investment_thesis
    pa = iren_slice.personalized_action
    ing = iren_slice.ingestion_result

    timing = bool(getattr(thesis, "timing_confirmation", False))
    rt = getattr(getattr(thesis, "red_team_summary", None), "red_team_verdict", "") or ""
    catalyst_panel = getattr(iren_slice.cockpit_view, "catalyst", None)
    positives = tuple(getattr(catalyst_panel, "positive_catalysts", ()) or ())
    catalyst_label = (
        "repricing triggers tracked (real evidence slice)" if positives else "")

    authority = getattr(ing, "authority_summary", {}) or {}
    badges = (
        "SEC canonical ×{0}".format(authority.get("canonical", 0)),
        "FMP convenience ×{0}".format(authority.get("convenience", 0)),
        "yfinance fallback ×{0}".format(authority.get("fallback", 0)),
    )
    return {
        "investability_label": getattr(thesis, "investability_assessment", ""),
        "timing_label": "timing confirmed" if timing else "timing not confirmed",
        "red_team_label": rt,
        "recommendation_label": getattr(pa, "recommendation_status", ""),
        "catalyst_label": catalyst_label,
        "capital_structure_risk": rt in ("concern", "fail"),
        "ordering_value": float(getattr(thesis, "thesis_confidence", 0.0)),
        "source_authority_badges": badges,
    }


# --------------------------------------------------------------------------- #
# Builders                                                                     #
# --------------------------------------------------------------------------- #
def _planet_view(galaxy: DemoGalaxy, planet: DemoPlanet, iren_slice,
                 universe_path: str = "", enc=None,
                 source_badges: Optional[Tuple[str, ...]] = None) -> PlanetCandidateView:
    """Project a candidate planet view.

    ``enc`` (a terrain :class:`VisualEncoding`) and ``source_badges`` (a terrain
    company node's ``source_refs``) are supplied by the terrain projection so the view's
    visual size / glow / dashed marker and source-authority badges DERIVE FROM the
    terrain. When they are absent (e.g. an ad-hoc unit-test planet not in any terrain)
    the same values are computed from the existing helpers, so behaviour is unchanged.
    """
    locate = "universe.html#focus={0}".format(universe_path)
    if planet.is_real and iren_slice is not None:
        st = _iren_real_status(iren_slice)
        investability = st["investability_label"]; timing = st["timing_label"]
        red_team = st["red_team_label"]; recommendation = st["recommendation_label"]
        catalyst = st["catalyst_label"]; cap_risk = st["capital_structure_risk"]
        ordering = st["ordering_value"]; badges = st["source_authority_badges"]
        is_real = True; cockpit = "cockpit.html"; provenance = True
        data_origin = "LIVE-FIXTURE"
    else:
        investability = planet.investability_label; timing = planet.timing_label
        red_team = planet.red_team_label; recommendation = planet.recommendation_label
        catalyst = planet.catalyst_label; cap_risk = planet.capital_structure_risk
        ordering = float(planet.evidence_count)
        badges = ("demo terrain — no live sources",)
        is_real = False; cockpit = None; provenance = False
        data_origin = planet.data_origin
    if source_badges is not None:
        badges = tuple(source_badges)
    if enc is not None:
        size_px = enc.size_value; glow = enc.glow_level; magnitude_missing = enc.dashed_outline
    else:
        size_px = visual_size(planet.market_cap, "planet")
        glow = glow_level(investability_label=investability, timing_label=timing,
                          recommendation_label=recommendation)
        magnitude_missing = planet.market_cap is None
    return PlanetCandidateView(
        candidate_id="{0}--{1}".format(galaxy.slug, slugify(planet.ticker)),
        ticker=planet.ticker, company=planet.company,
        galaxy_name=galaxy.theme_name, galaxy_slug=galaxy.slug,
        value_chain_role=planet.value_chain_role,
        proximity_to_bottleneck=planet.proximity_to_bottleneck,
        investability_label=investability, timing_label=timing, red_team_label=red_team,
        recommendation_label=recommendation, catalyst_label=catalyst,
        capital_structure_risk=cap_risk, evidence_count=planet.evidence_count,
        data_quality=planet.data_quality, is_real=is_real,
        security_mapping_qualifier=SECURITY_MAPPING_QUALIFIER, cockpit_link=cockpit,
        locate_link=locate, provenance_available=provenance, ordering_value=ordering,
        source_authority_badges=badges, market_cap=planet.market_cap,
        visual_size_px=size_px, magnitude_missing=magnitude_missing, glow_level=glow,
        universe_path=universe_path, data_origin=data_origin,
    )


def _node_view(node, enc=None, node_id: Optional[str] = None) -> NodeView:
    if enc is not None:
        size_px = enc.size_value; magnitude_missing = enc.dashed_outline
    else:
        size_px = visual_size(node.dependency_exposure, "moon")
        magnitude_missing = (node.dependency_exposure is None)
    return NodeView(
        node_id=node_id or node.node_id, tier=node.tier, role=node.role,
        economics_capture=node.economics_capture, bottleneck_exposure=node.bottleneck_exposure,
        evidence_quality=node.evidence_quality, missing_data=tuple(node.missing_data),
        candidate_companies=tuple(node.candidate_companies),
        has_dynamic_evidence=bool(node.dynamic_evidence),
        dynamic_evidence_note=("live delta attached" if node.dynamic_evidence
                               else "static terrain — no dynamic evidence delta (demo)"),
        dependency_exposure=node.dependency_exposure,
        visual_size_px=size_px, magnitude_missing=magnitude_missing,
        data_origin=node.data_origin,
    )


def _solar_system_view(galaxy: DemoGalaxy, ss, enc=None, slug: Optional[str] = None,
                       dep_encs=None) -> SolarSystemValueChainView:
    dep_encs = dep_encs or {}
    nodes = tuple(_node_view(n, enc=dep_encs.get(n.node_id)) for n in ss.nodes)
    ticker_map = tuple(
        (n.role, tuple(n.candidate_companies)) for n in ss.nodes if n.candidate_companies)
    return SolarSystemValueChainView(
        galaxy_name=galaxy.theme_name, galaxy_slug=galaxy.slug,
        name=ss.name, slug=slug or "{0}--{1}".format(galaxy.slug, slugify(ss.name)),
        description=ss.description, nodes=nodes,
        security_mapping_qualifier=SECURITY_MAPPING_QUALIFIER,
        node_ticker_map=ticker_map,
        value_chain_revenue_pool=ss.value_chain_revenue_pool,
        visual_size_px=(enc.size_value if enc is not None
                        else visual_size(ss.value_chain_revenue_pool, "solar_system")),
        magnitude_missing=(enc.dashed_outline if enc is not None
                           else (ss.value_chain_revenue_pool is None)),
        data_origin=ss.data_origin,
    )


def _star_view(galaxy: DemoGalaxy, star, index: int, enc=None,
               slug: Optional[str] = None) -> StarBottleneckView:
    return StarBottleneckView(
        galaxy_name=galaxy.theme_name, galaxy_slug=galaxy.slug,
        slug=slug or "{0}--star-{1}".format(galaxy.slug, index),
        star_type=star.star_type, constrained_node=star.constrained_node,
        severity=star.severity, duration=star.duration,
        beneficiaries=tuple(star.beneficiaries), losers=tuple(star.losers),
        resolution_risk=star.resolution_risk, evidence=tuple(star.evidence),
        data_gaps=tuple(star.data_gaps),
        bottleneck_economic_importance=star.bottleneck_economic_importance,
        visual_size_px=(enc.size_value if enc is not None
                        else visual_size(star.bottleneck_economic_importance, "star")),
        magnitude_missing=(enc.dashed_outline if enc is not None
                           else (star.bottleneck_economic_importance is None)),
        data_origin=star.data_origin,
    )


def _cluster_view(galaxy: DemoGalaxy, enc=None, slug: Optional[str] = None) -> GalaxyClusterView:
    return GalaxyClusterView(
        theme_name=galaxy.theme_name, slug=slug or galaxy.slug, megatrend=galaxy.megatrend,
        capital_cycle=galaxy.capital_cycle, heat_label=galaxy.heat_label,
        priority_label=galaxy.priority_label, signal_convergence=galaxy.signal_convergence,
        evidence_count=galaxy.evidence_count, data_quality=galaxy.data_quality,
        bottleneck_severity=galaxy.bottleneck_severity, candidate_count=galaxy.candidate_count,
        maturity_timing=galaxy.maturity_timing, crowded_euphoric=galaxy.crowded_euphoric,
        red_team_risk=galaxy.red_team_risk,
        data_poor=(galaxy.data_quality or "").lower() in ("low", "sparse"),
        theme_tam=galaxy.theme_tam, megatrend_magnitude=galaxy.megatrend_magnitude,
        visual_size_px=(enc.size_value if enc is not None
                        else visual_size(galaxy.theme_tam, "galaxy")),
        magnitude_missing=(enc.dashed_outline if enc is not None
                           else (galaxy.theme_tam is None)),
        data_origin=galaxy.data_origin,
    )


def _theme_view(galaxy: DemoGalaxy, iren_slice, gnode=None) -> GalaxyThemeView:
    """Project a galaxy's theme view.

    When ``gnode`` (a terrain :class:`GalaxyNode`) is supplied, ids, visual encodings
    and source-authority badges DERIVE FROM the terrain nodes; without it the same
    values are computed from the demo record so the builder stays usable stand-alone.
    """
    theme_node = gnode.themes[0] if gnode is not None else None
    vc_by_slug = ({vc.id: vc for vc in theme_node.value_chains} if theme_node else {})
    bn_by_slug = ({bn.id: bn for vc in theme_node.value_chains for bn in vc.bottlenecks}
                  if theme_node else {})
    co_by_ticker = ({co.ticker: co for co in theme_node.candidate_planets}
                    if theme_node else {})

    ss_views = []
    for ss in galaxy.solar_systems:
        vc_slug = "{0}--{1}".format(galaxy.slug, slugify(ss.name))
        vcnode = vc_by_slug.get(vc_slug)
        dep_encs = ({dep.id: dep.visual_encoding for dep in vcnode.dependencies}
                    if vcnode else None)
        ss_views.append(_solar_system_view(
            galaxy, ss, enc=(vcnode.visual_encoding if vcnode else None),
            slug=(vcnode.id if vcnode else None), dep_encs=dep_encs))
    ss_views = tuple(ss_views)

    star_views = []
    for i, s in enumerate(galaxy.stars):
        bnnode = bn_by_slug.get("{0}--star-{1}".format(galaxy.slug, i))
        star_views.append(_star_view(
            galaxy, s, i, enc=(bnnode.visual_encoding if bnnode else None),
            slug=(bnnode.id if bnnode else None)))
    star_views = tuple(star_views)

    # All of a galaxy's planets hang off its first value chain + first bottleneck star.
    vc0 = ss_views[0].slug if ss_views else "vc0"
    star0 = star_views[0].slug if star_views else "star0"
    planets = []
    for p in galaxy.planets:
        conode = co_by_ticker.get(p.ticker)
        upath = conode.id if conode else planet_universe_path(galaxy.slug, vc0, star0, p.ticker)
        planets.append(_planet_view(
            galaxy, p, iren_slice, universe_path=upath,
            enc=(conode.visual_encoding if conode else None),
            source_badges=(conode.source_refs if conode else None)))
    planets = tuple(planets)
    return GalaxyThemeView(
        cluster=_cluster_view(galaxy, enc=(gnode.visual_encoding if gnode else None),
                              slug=(gnode.id if gnode else None)),
        why_now=galaxy.why_now, why_before_obvious=galaxy.why_before_obvious,
        confirmed_signals=tuple(galaxy.confirmed_signals),
        speculative_signals=tuple(galaxy.speculative_signals),
        positive_catalysts=tuple(galaxy.positive_catalysts),
        negative_catalysts=tuple(galaxy.negative_catalysts),
        red_team_notes=tuple(galaxy.red_team_notes), data_gaps=tuple(galaxy.data_gaps),
        solar_systems=ss_views, stars=star_views, planets=planets,
    )


def _card_from_planet(p: PlanetCandidateView) -> CandidateCardView:
    primary, cross = assign_buckets(
        investability_label=p.investability_label, timing_label=p.timing_label,
        red_team_label=p.red_team_label, recommendation_label=p.recommendation_label,
        catalyst_label=p.catalyst_label, capital_structure_risk=p.capital_structure_risk,
        data_quality=p.data_quality, evidence_count=p.evidence_count)
    return CandidateCardView(
        candidate_id=p.candidate_id, ticker=p.ticker, company=p.company,
        galaxy_name=p.galaxy_name, galaxy_slug=p.galaxy_slug,
        value_chain_role=p.value_chain_role, proximity_to_bottleneck=p.proximity_to_bottleneck,
        card_label=card_label_for(primary, p.investability_label),
        investability_label=p.investability_label, timing_label=p.timing_label,
        red_team_label=p.red_team_label, recommendation_label=p.recommendation_label,
        catalyst_label=p.catalyst_label, capital_structure_risk=p.capital_structure_risk,
        data_quality=p.data_quality, evidence_count=p.evidence_count, is_real=p.is_real,
        security_mapping_qualifier=p.security_mapping_qualifier, cockpit_link=p.cockpit_link,
        locate_link=p.locate_link, provenance_available=p.provenance_available,
        primary_bucket=primary, cross_cut_buckets=cross, ordering_value=p.ordering_value,
        source_authority_badges=p.source_authority_badges,
        market_cap=p.market_cap, visual_size_px=p.visual_size_px,
        magnitude_missing=p.magnitude_missing, glow_level=p.glow_level,
        universe_path=p.universe_path,
        data_origin=p.data_origin,
    )


def _order_cards(cards) -> Tuple[CandidateCardView, ...]:
    # Deterministic within-bucket ordering by an EXISTING field, then ticker.
    return tuple(sorted(cards, key=lambda c: (-round(c.ordering_value, 6), c.ticker)))


def build_cio_dashboard_view(themes: Tuple[GalaxyThemeView, ...]) -> CIODashboardView:
    all_cards = []
    for theme in themes:
        for p in theme.planets:
            all_cards.append(_card_from_planet(p))

    buckets = []
    for name in BUCKET_ORDER:
        in_bucket = [c for c in all_cards
                     if c.primary_bucket == name or name in c.cross_cut_buckets]
        buckets.append(BucketView(name=name, description=_BUCKET_DESCRIPTIONS[name],
                                  cards=_order_cards(in_bucket)))
    real_count = sum(1 for c in all_cards if c.is_real)
    return CIODashboardView(
        banner="Demo candidate dashboard — live ranking not enabled yet.",
        buckets=tuple(buckets), total_candidates=len(all_cards),
        real_candidate_count=real_count,
    )


def build_data_quality_view(iren_slice, terrain=None) -> DataQualityView:
    """Build the Data-Quality control panel view.

    Source coverage counts, data gaps and the provenance chain are read FROM the
    terrain (``terrain.source_coverage`` / ``terrain.data_gaps`` /
    ``terrain.provenance_refs``) -- the same content as before, now sourced through the
    typed terrain. Overridden facts + the real subject are read directly from the slice.
    When ``terrain`` is omitted the terrain is built from the slice.

    The run-mode / fixture status text reflects the terrain's mode: the demo terrain keeps
    the ``fixture/demo`` wording; an evidence-ingested terrain honestly labels itself
    ``evidence_ingested_fixture`` (never ``live``).
    """
    if terrain is None:
        from .demo_terrain import build_demo_terrain
        terrain = build_demo_terrain(iren_slice)
    coverage = terrain.source_coverage or {}
    is_evidence = getattr(terrain, "mode", "") == "evidence_ingested_fixture"

    overridden = tuple(
        "{0}: {1} ({2}) — {3}".format(
            f.get("normalized_type", ""), f.get("source_name", ""),
            f.get("source_authority", ""), f.get("reason", ""))
        for f in iren_slice.provenance_chain.get("overridden_facts", ()))

    return DataQualityView(
        run_mode=(
            "evidence_ingested_fixture (deterministic replay of ingested IREN "
            "SEC/FMP/yfinance fixtures)" if is_evidence
            else "fixture/demo (deterministic replay of local IREN fixtures)"),
        fixture_demo_status=(
            "evidence-ingested from local fixtures; terrain sparse (single candidate)"
            if is_evidence else "fixtures loaded; demo terrain hand-authored"),
        live_enabled=False,
        scheduler_status="not enabled",
        broker_automation_status="disabled",
        manual_review_required=True,
        source_hierarchy="SEC EDGAR (canonical) > FMP (convenience) > yfinance (fallback)",
        canonical_count=int(coverage.get("canonical", 0)),
        convenience_count=int(coverage.get("convenience", 0)),
        fallback_count=int(coverage.get("fallback", 0)),
        signal_observation_count=int(coverage.get("signal", 0)),
        factual_observation_count=int(coverage.get("factual", 0)),
        conflict_warnings=tuple(iren_slice.conflict_warnings),
        overridden_facts=overridden, data_gaps=tuple(terrain.data_gaps),
        provenance_chain=tuple(terrain.provenance_refs),
        real_subject=iren_slice.subject,
    )


def build_economic_universe_view(iren_slice, terrain=None) -> EconomicUniverseView:
    """Assemble the whole read-only Economic Universe view by PROJECTING the typed
    terrain (the source of truth). If ``terrain`` is None it is built from the slice.

    The renderer keeps consuming the same ``*View`` dataclasses, but their ids, visual
    encodings, source badges, data gaps and semantic edges now DERIVE FROM the terrain.
    The terrain itself is attached to the returned view (``view.terrain``).

    When ``terrain`` is an evidence-ingested terrain (mode ``evidence_ingested_fixture``)
    the whole view is projected DIRECTLY from that terrain's own galaxy/theme nodes -- NOT
    from the hand-authored demo universe -- so evidence mode shows only the ingested
    candidate's theme, sparse and honestly incomplete.
    """
    if terrain is not None and getattr(terrain, "mode", "") == "evidence_ingested_fixture":
        return _build_evidence_universe_view(iren_slice, terrain)
    from .demo_terrain import build_demo_terrain
    universe = build_demo_universe()
    terrain = terrain or build_demo_terrain(iren_slice, universe)

    gnode_by_id = {g.id: g for g in terrain.galaxies}
    themes = tuple(_theme_view(g, iren_slice, gnode=gnode_by_id.get(g.slug))
                   for g in universe.galaxies)
    clusters = tuple(t.cluster for t in themes)
    dashboard = build_cio_dashboard_view(themes)
    data_quality = build_data_quality_view(iren_slice, terrain)

    # Semantic edges come straight from the terrain's validated RelationshipEdges.
    name_by_slug = {g.id: g.name for g in terrain.galaxies}
    edges = tuple(
        ThemeEdgeView(
            source_slug=e.source_id, target_slug=e.target_id,
            source_name=name_by_slug.get(e.source_id, e.source_id),
            target_name=name_by_slug.get(e.target_id, e.target_id),
            type=e.relationship_type, reason=e.description,
            strength=e.strength, evidence_quality=e.evidence_quality)
        for e in terrain.relationship_edges
        if e.source_id in name_by_slug and e.target_id in name_by_slug
        and e.source_id != e.target_id)
    return EconomicUniverseView(
        mode="fixture/demo", live_enabled=False, scheduler_enabled=False,
        broker_automation_enabled=False,
        clusters=clusters, themes=themes, edges=edges, dashboard=dashboard,
        data_quality=data_quality, real_subject=iren_slice.subject, terrain=terrain,
    )


# --------------------------------------------------------------------------- #
# Evidence-ingested projection: build the view DIRECTLY from an evidence terrain #
# (IMPLEMENTATION-010C). Every sub-view derives from the terrain node's fields   #
# + the real slice statuses; nothing comes from the demo universe.               #
# --------------------------------------------------------------------------- #
_EVIDENCE_ORIGIN = "EVIDENCE-INGESTED-FIXTURE"


def _evidence_node_view(dep) -> NodeView:
    enc = dep.visual_encoding
    return NodeView(
        node_id=dep.id, tier=str(dep.tier), role=dep.name,
        economics_capture=dep.economics_capture, bottleneck_exposure=dep.exposure_type,
        evidence_quality=dep.evidence_quality, missing_data=tuple(dep.missing_data),
        candidate_companies=tuple(dep.candidate_companies), has_dynamic_evidence=False,
        dynamic_evidence_note="evidence-ingested terrain — no dynamic delta",
        dependency_exposure=dep.magnitude, visual_size_px=enc.size_value,
        magnitude_missing=enc.dashed_outline, data_origin=_EVIDENCE_ORIGIN)


def _evidence_planet_view(conode, iren_slice, galaxy_name, galaxy_slug) -> PlanetCandidateView:
    st = _iren_real_status(iren_slice)
    enc = conode.visual_encoding
    upath = conode.id
    return PlanetCandidateView(
        candidate_id="{0}--{1}".format(galaxy_slug, slugify(conode.ticker)),
        ticker=conode.ticker, company=conode.company_name,
        galaxy_name=galaxy_name, galaxy_slug=galaxy_slug,
        value_chain_role=conode.value_chain_role,
        proximity_to_bottleneck=conode.directness_to_bottleneck,
        investability_label=st["investability_label"], timing_label=st["timing_label"],
        red_team_label=st["red_team_label"], recommendation_label=st["recommendation_label"],
        catalyst_label=st["catalyst_label"], capital_structure_risk=st["capital_structure_risk"],
        evidence_count=conode.evidence_count, data_quality=conode.data_quality, is_real=True,
        security_mapping_qualifier=SECURITY_MAPPING_QUALIFIER, cockpit_link=conode.cockpit_link,
        locate_link="universe.html#focus={0}".format(upath), provenance_available=True,
        ordering_value=st["ordering_value"], source_authority_badges=tuple(conode.source_refs),
        market_cap=conode.market_cap, visual_size_px=enc.size_value,
        magnitude_missing=enc.dashed_outline, glow_level=enc.glow_level,
        universe_path=upath, data_origin=_EVIDENCE_ORIGIN)


def _evidence_star_view(bn, galaxy_name, galaxy_slug) -> StarBottleneckView:
    enc = bn.visual_encoding
    return StarBottleneckView(
        galaxy_name=galaxy_name, galaxy_slug=galaxy_slug, slug=bn.id,
        star_type=bn.bottleneck_type, constrained_node=bn.name,
        severity=bn.severity or "unquantified",
        duration=bn.expected_duration or "not quantified",
        beneficiaries=tuple(bn.beneficiaries), losers=tuple(bn.losers_or_risks),
        resolution_risk=bn.resolution_risk, evidence=tuple(bn.evidence),
        data_gaps=tuple(bn.data_gaps),
        bottleneck_economic_importance=bn.economic_importance,
        visual_size_px=enc.size_value, magnitude_missing=enc.dashed_outline,
        data_origin=_EVIDENCE_ORIGIN)


def _evidence_vc_view(vc, galaxy_name, galaxy_slug) -> SolarSystemValueChainView:
    enc = vc.visual_encoding
    nodes = tuple(_evidence_node_view(d) for d in vc.dependencies)
    return SolarSystemValueChainView(
        galaxy_name=galaxy_name, galaxy_slug=galaxy_slug, name=vc.name, slug=vc.id,
        description=vc.description, nodes=nodes,
        security_mapping_qualifier=SECURITY_MAPPING_QUALIFIER, node_ticker_map=(),
        value_chain_revenue_pool=vc.revenue_pool_or_tam,
        visual_size_px=enc.size_value, magnitude_missing=enc.dashed_outline,
        data_origin=_EVIDENCE_ORIGIN)


def _evidence_cluster_view(g, theme, iren_slice, evidence_count) -> GalaxyClusterView:
    enc = g.visual_encoding
    oh = iren_slice.opportunity_hypothesis
    return GalaxyClusterView(
        theme_name=g.name, slug=g.id, megatrend=g.thesis_summary, capital_cycle=g.description,
        heat_label=g.heat_status, priority_label="evidence-ingested candidate",
        signal_convergence=theme.evidence_convergence, evidence_count=int(evidence_count),
        data_quality=g.data_quality, bottleneck_severity="not quantified",
        candidate_count=g.candidate_count,
        maturity_timing=(getattr(oh, "opportunity_maturity", "") or "emerging"),
        crowded_euphoric=False, red_team_risk=bool(g.risks),
        data_poor=(g.data_quality or "").lower() in ("low", "sparse"),
        theme_tam=g.economic_magnitude, megatrend_magnitude=None,
        visual_size_px=enc.size_value, magnitude_missing=enc.dashed_outline,
        data_origin=_EVIDENCE_ORIGIN)


def _evidence_theme_view(g, iren_slice) -> GalaxyThemeView:
    theme = g.themes[0]
    gname = g.name
    gslug = g.id
    company = theme.candidate_planets[0]
    planets = (_evidence_planet_view(company, iren_slice, gname, gslug),)
    ss_views = tuple(_evidence_vc_view(vc, gname, gslug) for vc in theme.value_chains)
    star_views = tuple(_evidence_star_view(bn, gname, gslug)
                       for vc in theme.value_chains for bn in vc.bottlenecks)
    pos_cat = tuple(c.description for c in theme.catalysts
                    if c.catalyst_type in ("positive", "repricing-trigger"))
    neg_cat = tuple(c.description for c in theme.catalysts if c.catalyst_type == "negative")
    red_notes = tuple(r.description for r in theme.red_team_risks)
    oh = iren_slice.opportunity_hypothesis
    confirmed = tuple(getattr(oh, "megatrend_context", ()) or ())
    speculative = tuple(getattr(oh, "monitoring_signals", ()) or ())
    cluster = _evidence_cluster_view(g, theme, iren_slice, company.evidence_count)
    return GalaxyThemeView(
        cluster=cluster, why_now=theme.why_now, why_before_obvious=theme.why_before_obvious,
        confirmed_signals=confirmed, speculative_signals=speculative,
        positive_catalysts=pos_cat, negative_catalysts=neg_cat, red_team_notes=red_notes,
        data_gaps=tuple(theme.data_gaps), solar_systems=ss_views, stars=star_views,
        planets=planets)


def _build_evidence_universe_view(iren_slice, terrain) -> EconomicUniverseView:
    """Project the whole Economic Universe view from an evidence-ingested terrain."""
    themes = tuple(_evidence_theme_view(g, iren_slice) for g in terrain.galaxies)
    clusters = tuple(t.cluster for t in themes)
    dashboard = build_cio_dashboard_view(themes)
    data_quality = build_data_quality_view(iren_slice, terrain)
    name_by_slug = {g.id: g.name for g in terrain.galaxies}
    edges = tuple(
        ThemeEdgeView(
            source_slug=e.source_id, target_slug=e.target_id,
            source_name=name_by_slug.get(e.source_id, e.source_id),
            target_name=name_by_slug.get(e.target_id, e.target_id),
            type=e.relationship_type, reason=e.description,
            strength=e.strength, evidence_quality=e.evidence_quality)
        for e in terrain.relationship_edges
        if e.source_id in name_by_slug and e.target_id in name_by_slug
        and e.source_id != e.target_id)
    return EconomicUniverseView(
        mode="evidence_ingested_fixture", live_enabled=False, scheduler_enabled=False,
        broker_automation_enabled=False, clusters=clusters, themes=themes, edges=edges,
        dashboard=dashboard, data_quality=data_quality,
        real_subject=iren_slice.subject, terrain=terrain)
