"""Read-only projections for the Economic Universe UI (IMPLEMENTATION-010A).

Pure PROJECTION view models. They COPY and GROUP existing fields and statuses --
demo-terrain fields from :mod:`universe_ui.demo_universe`, and explicit evidence /
real-run candidate statuses when those runs are requested. They compute
NOTHING beyond grouping and formatting:

* **No new score.** There is no composite, master, ranking, or alpha number here.
  Candidate buckets are chosen from EXISTING pipeline statuses only
  (investability_assessment / timing_confirmation / red-team verdict /
  recommendation_status). Within-bucket ordering reuses an EXISTING field
  (``thesis_confidence`` for active-run candidates; ``evidence_count`` for demo ones) --
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

# Terrain modes whose view is projected DIRECTLY from the terrain's own nodes (not the
# demo universe): the evidence-ingested fixture terrain and the real on-demand terrain.
EVIDENCE_FIXTURE_MODE = "evidence_ingested_fixture"
REAL_ON_DEMAND_MODE = "real_evidence_on_demand"


def _is_evidence_terrain_mode(mode: str) -> bool:
    return mode in (EVIDENCE_FIXTURE_MODE, REAL_ON_DEMAND_MODE)


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
    # IMPLEMENTATION-011C diligence-enrichment context (label-only; empty unless a real /
    # watchlist run supplied a source-backed bundle for THIS ticker). Every line carries its
    # source authority; there is NO score / rank / buy / sell here.
    enrichment_context: Tuple[str, ...] = ()      # source-backed profile / leadership facts
    enrichment_coverage_line: str = ""            # e.g. "enrichment partial — 2/6 areas"
    enrichment_gaps: Tuple[str, ...] = ()         # honest per-ticker enrichment gaps


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
    # IMPLEMENTATION-011C: per-company diligence-enrichment context (label-only; empty in
    # demo). Evidence + coverage + gaps only — never a decision, score, or trade action.
    enrichment_context: Tuple[str, ...] = ()
    enrichment_coverage_line: str = ""
    enrichment_gaps: Tuple[str, ...] = ()


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
    # IMPLEMENTATION-010D real-mode additions (optional; empty in demo/fixture modes).
    source_status: Tuple[Tuple[str, str], ...] = ()
    run_timestamp: str = ""
    tickers: Tuple[str, ...] = ()
    mode_label: str = ""
    deferred_records_count: int = 0
    # IMPLEMENTATION-010E watchlist additions (optional; empty in single-ticker modes).
    is_watchlist: bool = False
    wl_requested: int = 0
    wl_succeeded: int = 0
    wl_failed: int = 0
    wl_deferred: int = 0
    # per-ticker source-status rows: (ticker, sec, fmp, yf, canonical, convenience,
    # fallback, conflicts, data_gaps_count, provenance_count, terrain_status)
    per_ticker_rows: Tuple[Tuple[Any, ...], ...] = ()
    # (kind/ticker label, human message) failure & gap cards
    failure_cards: Tuple[Tuple[str, str], ...] = ()
    # IMPLEMENTATION-010F diagnostics (label-only; None in demo / fixture modes).
    # The typed TerrainQualityDiagnostic; per-ticker rows / cards / actions / encoding
    # explanations are pre-projected so the renderer stays dumb.
    terrain_diagnostics: Any = None
    diagnostic_cards: Tuple[Tuple[str, str], ...] = ()
    data_action_rows: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    object_annotations: Tuple[Tuple[str, str], ...] = ()
    visual_encoding_explanations: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = ()
    # IMPLEMENTATION-011A diligence-enrichment coverage (label-only; None unless a real /
    # watchlist run supplied enrichment bundles). Demo / evidence modes stay None.
    enrichment_coverage: Any = None


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
    # IMPLEMENTATION-010E: appended to the status strip for a watchlist run
    # (e.g. " · 3 requested / 2 built / 1 failed-or-deferred"); empty otherwise.
    run_summary_line: str = ""


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
# Real fixture / run status extraction (copied from the slice; nothing recomputed) #
# --------------------------------------------------------------------------- #
def _iren_real_status(iren_slice) -> dict:
    """Copy an explicit real/evidence slice's already-computed statuses."""
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
        enrichment_context=p.enrichment_context,
        enrichment_coverage_line=p.enrichment_coverage_line,
        enrichment_gaps=p.enrichment_gaps,
    )


def _order_cards(cards) -> Tuple[CandidateCardView, ...]:
    # Deterministic within-bucket ordering by an EXISTING field, then ticker.
    return tuple(sorted(cards, key=lambda c: (-round(c.ordering_value, 6), c.ticker)))


def _eligible_capital_candidate(p: PlanetCandidateView) -> bool:
    """Candidate Eligibility Gate for production candidate surfaces.

    A company may appear as a Capital Candidate only when it is real/current-run style
    output with provenance and Investment Diligence/cockpit context. Synthetic demo
    planets remain clickable in Universe Canvas, but do not become candidate rows.
    """
    if not p.is_real:
        return False
    if not p.provenance_available:
        return False
    if not p.candidate_id or not p.data_origin:
        return False
    if not p.source_authority_badges:
        return False
    if not p.data_quality:
        return False
    return True


def build_cio_dashboard_view(themes: Tuple[GalaxyThemeView, ...]) -> CIODashboardView:
    all_cards = []
    for theme in themes:
        for p in theme.planets:
            if _eligible_capital_candidate(p):
                all_cards.append(_card_from_planet(p))

    buckets = []
    for name in BUCKET_ORDER:
        in_bucket = [c for c in all_cards
                     if c.primary_bucket == name or name in c.cross_cut_buckets]
        buckets.append(BucketView(name=name, description=_BUCKET_DESCRIPTIONS[name],
                                  cards=_order_cards(in_bucket)))
    real_count = sum(1 for c in all_cards if c.is_real)
    return CIODashboardView(
        banner=("CosmosIQ Capital — no active-run Capital Candidates in default demo."
                if not all_cards else "CosmosIQ Capital — active-run candidates surfaced."),
        buckets=tuple(buckets), total_candidates=len(all_cards),
        real_candidate_count=real_count,
    )


def build_data_quality_view(iren_slice, terrain=None, source_status=None,
                            watchlist_summary=None, enrichment_bundles=None) -> DataQualityView:
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
    mode = getattr(terrain, "mode", "")
    is_real = mode == REAL_ON_DEMAND_MODE
    is_evidence = _is_evidence_terrain_mode(mode)

    # IMPLEMENTATION-010E: for a watchlist run, source conflicts / overridden facts /
    # deferred counts / subject are aggregated ACROSS tickers in the run summary; a
    # single-ticker run reads them from its one slice as before.
    is_watchlist = watchlist_summary is not None
    if is_watchlist:
        overridden_src = tuple(watchlist_summary.overridden_facts)
        conflict_src = tuple(watchlist_summary.conflict_warnings)
        deferred_n = int(watchlist_summary.deferred_records_count)
    elif not _is_evidence_terrain_mode(getattr(terrain, "mode", "")):
        overridden_src = ()
        conflict_src = ()
        deferred_n = 0
    else:
        overridden_src = tuple(iren_slice.provenance_chain.get("overridden_facts", ()))
        conflict_src = tuple(iren_slice.conflict_warnings)
        deferred_n = len(getattr(iren_slice, "deferred_records", ()) or ())

    overridden = tuple(
        "{0}: {1} ({2}) — {3}".format(
            f.get("normalized_type", ""), f.get("source_name", ""),
            f.get("source_authority", ""), f.get("reason", ""))
        for f in overridden_src)

    # Per-source STATUS + run metadata (single real-ticker mode only; a watchlist shows a
    # PER-TICKER table instead, so the single-source panel stays empty for it).
    ss = dict(source_status or {})
    status_pairs = tuple(
        (k, str(ss[k])) for k in ("sec", "fmp", "yfinance") if k in ss)
    run_ts = str(ss.get("run_timestamp", ""))
    subject = getattr(iren_slice, "subject", "") or "" if is_evidence else ""

    wl_fields = _watchlist_dq_fields(watchlist_summary)
    diag_fields = _diagnostic_dq_fields(
        terrain, iren_slice, source_status, watchlist_summary,
        is_real=is_real, is_watchlist=is_watchlist)
    # IMPLEMENTATION-011A: enrichment-coverage diagnostic (real / watchlist only; None in
    # demo / evidence modes so those pages stay byte-identical).
    enrichment_coverage = None
    if is_real and enrichment_bundles:
        from diligence_enrichment.coverage import build_enrichment_coverage
        cov = build_enrichment_coverage(
            [b for b in enrichment_bundles if b is not None])
        enrichment_coverage = cov if cov.present else None
    if is_watchlist:
        status_pairs = ()
        run_ts = str(watchlist_summary.run_timestamp)
        tickers = tuple(r.ticker for r in watchlist_summary.records if r.status == "built")
    else:
        tickers = (subject,) if (is_real and subject) else ()

    if is_watchlist:
        run_mode = ("real_evidence_on_demand — WATCHLIST ({0} requested / {1} built / "
                    "{2} failed-or-deferred); REAL SEC/FMP/yfinance, manual refresh; not "
                    "scheduled, not broker-connected; may be incomplete".format(
                        watchlist_summary.requested_count, watchlist_summary.succeeded_count,
                        watchlist_summary.failed_or_deferred_count))
        fixture_status = ("real sources fetched on demand for {0} companies; merged "
                          "terrain sparse — completeness NOT claimed".format(
                              watchlist_summary.succeeded_count))
    elif is_real:
        run_mode = ("real_evidence_on_demand (REAL SEC/FMP/yfinance sources, manual "
                    "refresh; not scheduled, not broker-connected; may be incomplete)")
        fixture_status = ("real sources fetched on demand for {0}; terrain sparse — "
                          "completeness NOT claimed".format(subject or "ticker"))
    elif is_evidence:
        run_mode = ("evidence_ingested_fixture (deterministic replay of ingested IREN "
                    "SEC/FMP/yfinance fixtures)")
        fixture_status = ("evidence-ingested from local fixtures; terrain sparse "
                          "(single candidate)")
    else:
        run_mode = "fixture/demo (synthetic demo terrain; no active-run candidates)"
        fixture_status = "synthetic demo terrain loaded; no real ticker provenance"

    return DataQualityView(
        run_mode=run_mode,
        fixture_demo_status=fixture_status,
        live_enabled=False,
        scheduler_status="Off",
        broker_automation_status="Disabled",
        manual_review_required=True,
        source_hierarchy="SEC EDGAR (canonical) > FMP (convenience) > yfinance (fallback)",
        canonical_count=int(coverage.get("canonical", 0)),
        convenience_count=int(coverage.get("convenience", 0)),
        fallback_count=int(coverage.get("fallback", 0)),
        signal_observation_count=int(coverage.get("signal", 0)),
        factual_observation_count=int(coverage.get("factual", 0)),
        conflict_warnings=conflict_src,
        overridden_facts=overridden, data_gaps=tuple(terrain.data_gaps),
        provenance_chain=tuple(terrain.provenance_refs),
        real_subject=(", ".join(tickers) if is_watchlist else subject),
        source_status=status_pairs, run_timestamp=run_ts, tickers=tickers,
        mode_label=(str(ss.get("mode_label", ""))
                    or (REAL_ON_DEMAND_MODE if (is_real or is_watchlist) else "")),
        deferred_records_count=deferred_n,
        enrichment_coverage=enrichment_coverage,
        **wl_fields,
        **diag_fields,
    )


def _watchlist_dq_fields(watchlist_summary) -> dict:
    """Per-ticker table + failure/gap cards for the watchlist Data-Quality panel.

    All values are COPIED from the run summary's per-ticker records + credential /
    coverage state — nothing is recomputed, ranked, or fabricated. Returns kwargs for
    :class:`DataQualityView` (empty for a single-ticker run)."""
    if watchlist_summary is None:
        return {}
    rows = []
    cards = []
    for r in watchlist_summary.records:
        rows.append((
            r.ticker, r.sec_status, r.fmp_status, r.yfinance_status,
            r.canonical, r.convenience, r.fallback, r.conflicts,
            len(r.data_gaps), len(r.provenance_refs), r.terrain_status))
        if r.status != "built":
            cards.append((
                "ticker {0} — {1}".format(r.ticker, r.status),
                r.reason or "recorded as a visible failure (not silently dropped)"))
        else:
            if r.sec_status == "credentials_missing":
                cards.append(("ticker {0} — SEC User-Agent missing".format(r.ticker),
                              "canonical SEC source unavailable (no key leaked; a data gap)"))
            if r.fmp_status == "credentials_missing":
                cards.append(("ticker {0} — FMP key missing".format(r.ticker),
                              "convenience FMP source unavailable (key never shown; a data gap)"))
            if r.yfinance_status == "deferred":
                cards.append(("ticker {0} — yfinance deferred".format(r.ticker),
                              "fallback / research-only source not wired for this run"))
            if r.sec_status == "failed" or r.fmp_status == "failed":
                cards.append(("ticker {0} — source fetch failed".format(r.ticker),
                              "a source degraded; the run continued with what was fetched"))
    return {
        "is_watchlist": True,
        "wl_requested": watchlist_summary.requested_count,
        "wl_succeeded": watchlist_summary.succeeded_count,
        "wl_failed": watchlist_summary.failed_count,
        "wl_deferred": watchlist_summary.deferred_count,
        "per_ticker_rows": tuple(rows),
        "failure_cards": tuple(cards),
    }


# --------------------------------------------------------------------------- #
# IMPLEMENTATION-010F: typed TRUST / COMPLETENESS diagnostics (labels, not      #
# scores) projected for the Data-Quality dashboard. Empty unless the terrain is #
# a real-evidence terrain (single 010D ticker or 010E watchlist).               #
# --------------------------------------------------------------------------- #
def _node_label(node) -> str:
    """A short, human, deterministic label for a terrain node (for the diagnostic UI)."""
    kind = type(node).__name__.replace("Node", "")
    name = getattr(node, "ticker", "") or getattr(node, "company_name", "") \
        or getattr(node, "name", "") or getattr(node, "id", "")
    return "{0} · {1}".format(kind, name)


def _diagnostic_cards_from(diag) -> Tuple[Tuple[str, str], ...]:
    """Diagnostic CARDS (one per distinct condition present). Data-quality only."""
    from .terrain import CompanyNode  # noqa: F401 -- kept local; module-level import unused
    seen = set()
    cards: list = []

    def add(label, body):
        if label in seen:
            return
        seen.add(label)
        cards.append((label, body))

    for d in diag.per_ticker:
        if d.terrain_status in ("failed", "deferred"):
            add("source failure", "{0}: {1} — recorded as a visible failure, not dropped"
                .format(d.ticker, d.terrain_status))
            continue
        if d.theme_classification_status in ("missing", "unclassified"):
            add("unclassified ticker",
                "{0}: no OpportunityHypothesis / theme could not be inferred — parked for "
                "human theme inference".format(d.ticker))
        if d.theme_classification_status == "weak":
            add("weak theme", "{0}: theme named but convergence is thin (weak, not upgraded)"
                .format(d.ticker))
        if d.value_chain_status in ("weak", "missing"):
            add("missing value chain",
                "{0}: value-chain coverage is a placeholder (no supplier/customer layers)"
                .format(d.ticker))
        if d.bottleneck_status in ("weak", "missing"):
            add("missing bottleneck",
                "{0}: bottleneck is constraint context — not quantified".format(d.ticker))
        acts = " ".join(d.data_actions)
        if "market-cap" in acts:
            add("missing market cap", "{0}: market cap not surfaced — neutral size + gap"
                .format(d.ticker))
        if "TAM" in acts:
            add("missing TAM", "{0}: theme TAM / revenue pool not quantified".format(d.ticker))
        if "supplier / customer" in acts:
            add("missing supplier/customer",
                "{0}: no named suppliers/customers mapped".format(d.ticker))
        if d.source_statuses and any(st == "credentials_missing" and src == "sec"
                                     for src, st in d.source_statuses):
            add("missing SEC User-Agent",
                "{0}: canonical SEC source unavailable (no key leaked; a data gap)"
                .format(d.ticker))
        if d.source_statuses and any(st == "credentials_missing" and src == "fmp"
                                     for src, st in d.source_statuses):
            add("missing FMP key",
                "{0}: convenience FMP source unavailable (key never shown; a data gap)"
                .format(d.ticker))

    if diag.unresolved_conflicts:
        add("conflicting financial facts",
            "{0} source conflict(s) detected; all resolved by authority (SEC canonical over "
            "FMP convenience)".format(len(diag.unresolved_conflicts)))
    if diag.stale_or_missing_sources:
        add("stale / deferred source",
            "sources credential-missing / deferred / unavailable: {0}".format(
                len(diag.stale_or_missing_sources)))
    return tuple(cards)


def _diagnostic_dq_fields(terrain, iren_slice, source_status, watchlist_summary,
                          *, is_real, is_watchlist) -> dict:
    """Project the typed diagnostics into render-ready view fields (labels, not scores).

    Nothing is fetched or scored: the diagnostic builder derives everything from the
    existing terrain nodes + run summary. Returns ``{}`` for demo / evidence-fixture modes
    so those pages stay byte-identical."""
    if not is_real:
        return {}
    from .terrain import (BottleneckNode, CompanyNode, DependencyNode, GalaxyNode,
                          ValueChainNode)
    from .terrain_diagnostics import (
        build_terrain_diagnostics, diagnostics_by_object_id, explain_visual_encoding,
        single_ticker_run_summary)

    if is_watchlist:
        summary = watchlist_summary
    else:
        summary = single_ticker_run_summary(terrain, source_status or {}, iren_slice)

    diag = build_terrain_diagnostics(terrain, summary)
    ann_map = diagnostics_by_object_id(terrain, diag)

    object_annotations = tuple(
        (_node_label(node), ann_map[nid])
        for nid, node in terrain.all_nodes()
        if nid in ann_map and ann_map[nid])

    ve_types = (GalaxyNode, ValueChainNode, BottleneckNode, CompanyNode, DependencyNode)
    ve = tuple(
        (_node_label(node), explain_visual_encoding(node))
        for _nid, node in terrain.all_nodes()
        if isinstance(node, ve_types) and explain_visual_encoding(node))

    action_rows = tuple(
        (d.ticker, d.data_actions) for d in diag.per_ticker if d.data_actions)

    return {
        "terrain_diagnostics": diag,
        "diagnostic_cards": _diagnostic_cards_from(diag),
        "data_action_rows": action_rows,
        "object_annotations": object_annotations,
        "visual_encoding_explanations": ve,
    }


def build_economic_universe_view(iren_slice, terrain=None, source_status=None,
                                 slice_by_subject=None,
                                 watchlist_summary=None,
                                 enrichment_bundles=None,
                                 enrichment_by_subject=None) -> EconomicUniverseView:
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
    if terrain is not None and _is_evidence_terrain_mode(getattr(terrain, "mode", "")):
        return _build_evidence_universe_view(
            iren_slice, terrain, source_status=source_status,
            slice_by_subject=slice_by_subject, watchlist_summary=watchlist_summary,
            enrichment_bundles=enrichment_bundles,
            enrichment_by_subject=enrichment_by_subject)
    from .demo_terrain import build_demo_terrain
    universe = build_demo_universe()
    terrain = terrain or build_demo_terrain(None, universe)

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
        data_quality=data_quality, real_subject="", terrain=terrain,
    )


# --------------------------------------------------------------------------- #
# Evidence-ingested projection: build the view DIRECTLY from an evidence terrain #
# (IMPLEMENTATION-010C). Every sub-view derives from the terrain node's fields   #
# + the real slice statuses; nothing comes from the demo universe.               #
# --------------------------------------------------------------------------- #
_EVIDENCE_ORIGIN = "EVIDENCE-INGESTED-FIXTURE"
_REAL_ORIGIN = "REAL-SOURCE-ON-DEMAND"


def _origin_for_mode(mode: str) -> str:
    return _REAL_ORIGIN if mode == REAL_ON_DEMAND_MODE else _EVIDENCE_ORIGIN


def _fmt_enrichment_value(label: str, ev) -> str:
    """Format one source-backed EnrichmentValue as ``label value (authority)`` — a LABEL,
    never a score. A ratio renders as a percentage; a magnitude with thousands separators."""
    unit = getattr(ev, "unit", "") or ""
    auth = getattr(ev, "authority", "") or "?"
    if unit == "ratio":
        try:
            return "{0}: {1:.1%} ({2})".format(label, float(ev.value), auth)
        except (TypeError, ValueError):
            return "{0}: {1} ({2})".format(label, ev.value, auth)
    try:
        return "{0}: {1:,.0f} {2} ({3})".format(label, float(ev.value), unit, auth).replace(
            "  ", " ")
    except (TypeError, ValueError):
        return "{0}: {1} ({2})".format(label, ev.value, auth)


def _enrichment_card_fields(bundle):
    """Per-company enrichment card fields (context / coverage line / gaps) from a
    SOURCE-BACKED :class:`DiligenceEnrichmentBundle`. ``(),"",()`` when ``bundle`` is None.

    Every context line is authority-stamped (SEC canonical / FMP convenience / manual /
    company IR). Leadership is surfaced as a DIAGNOSTIC label only (never a rank/score).
    Missing areas stay explicit gaps; nothing is fabricated and no decision is produced."""
    if bundle is None:
        return (), "", ()
    from diligence_enrichment.coverage import build_enrichment_coverage
    context = []
    p = bundle.profile
    for label, ev in (("sector", p.sector), ("industry", p.industry),
                      ("exchange", p.exchange)):
        if ev.present:
            context.append("{0}: {1} ({2})".format(label, ev.value, ev.authority))
    for key, label, ev in bundle.market.metric_items():
        if key in ("revenue", "net_income", "gross_margin", "operating_margin",
                   "shares") and ev.present:
            context.append(_fmt_enrichment_value(label, ev))
    ld = bundle.leadership
    if ld.present:
        context.append(
            "leadership: {0} named leader(s) ({1} — diagnostic evidence only, "
            "not a rank)".format(len(ld.members), ld.authority or "company IR"))
    cov = build_enrichment_coverage([bundle])
    tc = cov.per_ticker[0] if cov.per_ticker else None
    if tc is None:
        return tuple(context), "", ()
    avail = sum(1 for a in tc.areas if a.available)
    coverage_line = "enrichment {0} — {1}/{2} diligence areas source-backed".format(
        tc.enrichment_status, avail, len(tc.areas))
    return tuple(context), coverage_line, tuple(tc.gaps)


def _evidence_node_view(dep, origin=_EVIDENCE_ORIGIN) -> NodeView:
    enc = dep.visual_encoding
    return NodeView(
        node_id=dep.id, tier=str(dep.tier), role=dep.name,
        economics_capture=dep.economics_capture, bottleneck_exposure=dep.exposure_type,
        evidence_quality=dep.evidence_quality, missing_data=tuple(dep.missing_data),
        candidate_companies=tuple(dep.candidate_companies), has_dynamic_evidence=False,
        dynamic_evidence_note="evidence terrain — no dynamic delta",
        dependency_exposure=dep.magnitude, visual_size_px=enc.size_value,
        magnitude_missing=enc.dashed_outline, data_origin=origin)


def _evidence_planet_view(conode, iren_slice, galaxy_name, galaxy_slug,
                          origin=_EVIDENCE_ORIGIN,
                          enrichment_bundle=None) -> PlanetCandidateView:
    st = _iren_real_status(iren_slice)
    enc = conode.visual_encoding
    upath = conode.id
    enr_context, enr_cov_line, enr_gaps = _enrichment_card_fields(enrichment_bundle)
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
        universe_path=upath, data_origin=origin,
        enrichment_context=enr_context, enrichment_coverage_line=enr_cov_line,
        enrichment_gaps=enr_gaps)


def _evidence_star_view(bn, galaxy_name, galaxy_slug, origin=_EVIDENCE_ORIGIN) -> StarBottleneckView:
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
        data_origin=origin)


def _evidence_vc_view(vc, galaxy_name, galaxy_slug, origin=_EVIDENCE_ORIGIN) -> SolarSystemValueChainView:
    enc = vc.visual_encoding
    nodes = tuple(_evidence_node_view(d, origin=origin) for d in vc.dependencies)
    return SolarSystemValueChainView(
        galaxy_name=galaxy_name, galaxy_slug=galaxy_slug, name=vc.name, slug=vc.id,
        description=vc.description, nodes=nodes,
        security_mapping_qualifier=SECURITY_MAPPING_QUALIFIER, node_ticker_map=(),
        value_chain_revenue_pool=vc.revenue_pool_or_tam,
        visual_size_px=enc.size_value, magnitude_missing=enc.dashed_outline,
        data_origin=origin)


def _evidence_cluster_view(g, theme, iren_slice, evidence_count,
                           origin=_EVIDENCE_ORIGIN) -> GalaxyClusterView:
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
        data_origin=origin)


def _evidence_theme_view(g, iren_slice, slice_by_subject=None,
                         origin=_EVIDENCE_ORIGIN,
                         enrichment_by_subject=None) -> GalaxyThemeView:
    """Project ONE galaxy's theme view.

    A single-ticker terrain has one company; a merged 010E watchlist galaxy may hold
    SEVERAL co-located companies. Each company is projected from ITS OWN slice (looked up
    in ``slice_by_subject`` by ticker); theme-level narrative (why-now, signals) uses the
    first company's slice as the representative for that co-located theme."""
    smap = slice_by_subject or {}
    emap = enrichment_by_subject or {}
    theme = g.themes[0]
    gname = g.name
    gslug = g.id
    companies = theme.candidate_planets

    def _slice_for(co):
        return smap.get(getattr(co, "ticker", ""), iren_slice)

    def _enrichment_for(co):
        return emap.get(getattr(co, "ticker", ""))

    rep_slice = _slice_for(companies[0]) if companies else iren_slice
    planets = tuple(
        _evidence_planet_view(co, _slice_for(co), gname, gslug, origin=origin,
                              enrichment_bundle=_enrichment_for(co))
        for co in companies)
    ss_views = tuple(_evidence_vc_view(vc, gname, gslug, origin=origin)
                     for vc in theme.value_chains)
    star_views = tuple(_evidence_star_view(bn, gname, gslug, origin=origin)
                       for vc in theme.value_chains for bn in vc.bottlenecks)
    pos_cat = tuple(c.description for c in theme.catalysts
                    if c.catalyst_type in ("positive", "repricing-trigger"))
    neg_cat = tuple(c.description for c in theme.catalysts if c.catalyst_type == "negative")
    red_notes = tuple(r.description for r in theme.red_team_risks)
    oh = getattr(rep_slice, "opportunity_hypothesis", None)
    confirmed = tuple(getattr(oh, "megatrend_context", ()) or ())
    speculative = tuple(getattr(oh, "monitoring_signals", ()) or ())
    ev_count = companies[0].evidence_count if companies else 0
    cluster = _evidence_cluster_view(g, theme, rep_slice, ev_count, origin=origin)
    return GalaxyThemeView(
        cluster=cluster, why_now=theme.why_now, why_before_obvious=theme.why_before_obvious,
        confirmed_signals=confirmed, speculative_signals=speculative,
        positive_catalysts=pos_cat, negative_catalysts=neg_cat, red_team_notes=red_notes,
        data_gaps=tuple(theme.data_gaps), solar_systems=ss_views, stars=star_views,
        planets=planets)


def _build_evidence_universe_view(iren_slice, terrain, source_status=None,
                                  slice_by_subject=None,
                                  watchlist_summary=None,
                                  enrichment_bundles=None,
                                  enrichment_by_subject=None) -> EconomicUniverseView:
    """Project the whole Economic Universe view from an evidence / real terrain.

    For a 010E watchlist, ``slice_by_subject`` maps ticker -> that company's slice (so each
    co-located planet projects from its own evidence) and ``watchlist_summary`` drives the
    aggregated Data-Quality panel + the status-strip run summary line."""
    mode = getattr(terrain, "mode", EVIDENCE_FIXTURE_MODE)
    origin = _origin_for_mode(mode)
    themes = tuple(_evidence_theme_view(g, iren_slice, slice_by_subject, origin=origin,
                                        enrichment_by_subject=enrichment_by_subject)
                   for g in terrain.galaxies)
    clusters = tuple(t.cluster for t in themes)
    dashboard = build_cio_dashboard_view(themes)
    data_quality = build_data_quality_view(
        iren_slice, terrain, source_status=source_status,
        watchlist_summary=watchlist_summary, enrichment_bundles=enrichment_bundles)
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
    run_summary_line = ""
    real_subject = getattr(iren_slice, "subject", "") or ""
    if watchlist_summary is not None:
        run_summary_line = (
            " · {0} requested / {1} built / {2} failed-or-deferred".format(
                watchlist_summary.requested_count, watchlist_summary.succeeded_count,
                watchlist_summary.failed_or_deferred_count))
        real_subject = ", ".join(
            r.ticker for r in watchlist_summary.records if r.status == "built")
    return EconomicUniverseView(
        mode=mode, live_enabled=False, scheduler_enabled=False,
        broker_automation_enabled=False, clusters=clusters, themes=themes, edges=edges,
        dashboard=dashboard, data_quality=data_quality,
        real_subject=real_subject, terrain=terrain, run_summary_line=run_summary_line)
