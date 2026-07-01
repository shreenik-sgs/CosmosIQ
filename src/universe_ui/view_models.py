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
class EconomicUniverseView:
    mode: str
    live_enabled: bool
    scheduler_enabled: bool
    broker_automation_enabled: bool
    clusters: Tuple[GalaxyClusterView, ...]
    themes: Tuple[GalaxyThemeView, ...]
    dashboard: CIODashboardView
    data_quality: DataQualityView
    real_subject: str


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
def _planet_view(galaxy: DemoGalaxy, planet: DemoPlanet, iren_slice) -> PlanetCandidateView:
    locate = "galaxy.html#g-{0}".format(galaxy.slug)
    magnitude_missing = planet.market_cap is None
    size_px = visual_size(planet.market_cap, "planet")
    if planet.is_real and iren_slice is not None:
        st = _iren_real_status(iren_slice)
        return PlanetCandidateView(
            candidate_id="{0}--{1}".format(galaxy.slug, slugify(planet.ticker)),
            ticker=planet.ticker, company=planet.company,
            galaxy_name=galaxy.theme_name, galaxy_slug=galaxy.slug,
            value_chain_role=planet.value_chain_role,
            proximity_to_bottleneck=planet.proximity_to_bottleneck,
            investability_label=st["investability_label"],
            timing_label=st["timing_label"], red_team_label=st["red_team_label"],
            recommendation_label=st["recommendation_label"],
            catalyst_label=st["catalyst_label"],
            capital_structure_risk=st["capital_structure_risk"],
            evidence_count=planet.evidence_count, data_quality=planet.data_quality,
            is_real=True, security_mapping_qualifier=SECURITY_MAPPING_QUALIFIER,
            cockpit_link="cockpit.html", locate_link=locate,
            provenance_available=True, ordering_value=st["ordering_value"],
            source_authority_badges=st["source_authority_badges"],
            market_cap=planet.market_cap, visual_size_px=size_px,
            magnitude_missing=magnitude_missing,
            glow_level=glow_level(investability_label=st["investability_label"],
                                  timing_label=st["timing_label"],
                                  recommendation_label=st["recommendation_label"]),
            data_origin="LIVE-FIXTURE",
        )
    return PlanetCandidateView(
        candidate_id="{0}--{1}".format(galaxy.slug, slugify(planet.ticker)),
        ticker=planet.ticker, company=planet.company,
        galaxy_name=galaxy.theme_name, galaxy_slug=galaxy.slug,
        value_chain_role=planet.value_chain_role,
        proximity_to_bottleneck=planet.proximity_to_bottleneck,
        investability_label=planet.investability_label, timing_label=planet.timing_label,
        red_team_label=planet.red_team_label, recommendation_label=planet.recommendation_label,
        catalyst_label=planet.catalyst_label, capital_structure_risk=planet.capital_structure_risk,
        evidence_count=planet.evidence_count, data_quality=planet.data_quality,
        is_real=False, security_mapping_qualifier=SECURITY_MAPPING_QUALIFIER,
        cockpit_link=None, locate_link=locate, provenance_available=False,
        ordering_value=float(planet.evidence_count),
        source_authority_badges=("demo terrain — no live sources",),
        market_cap=planet.market_cap, visual_size_px=size_px,
        magnitude_missing=magnitude_missing,
        glow_level=glow_level(investability_label=planet.investability_label,
                              timing_label=planet.timing_label,
                              recommendation_label=planet.recommendation_label),
        data_origin=planet.data_origin,
    )


def _node_view(node) -> NodeView:
    return NodeView(
        node_id=node.node_id, tier=node.tier, role=node.role,
        economics_capture=node.economics_capture, bottleneck_exposure=node.bottleneck_exposure,
        evidence_quality=node.evidence_quality, missing_data=tuple(node.missing_data),
        candidate_companies=tuple(node.candidate_companies),
        has_dynamic_evidence=bool(node.dynamic_evidence),
        dynamic_evidence_note=("live delta attached" if node.dynamic_evidence
                               else "static terrain — no dynamic evidence delta (demo)"),
        data_origin=node.data_origin,
    )


def _solar_system_view(galaxy: DemoGalaxy, ss) -> SolarSystemValueChainView:
    nodes = tuple(_node_view(n) for n in ss.nodes)
    ticker_map = tuple(
        (n.role, tuple(n.candidate_companies)) for n in ss.nodes if n.candidate_companies)
    return SolarSystemValueChainView(
        galaxy_name=galaxy.theme_name, galaxy_slug=galaxy.slug,
        name=ss.name, slug="{0}--{1}".format(galaxy.slug, slugify(ss.name)),
        description=ss.description, nodes=nodes,
        security_mapping_qualifier=SECURITY_MAPPING_QUALIFIER,
        node_ticker_map=ticker_map, data_origin=ss.data_origin,
    )


def _star_view(galaxy: DemoGalaxy, star, index: int) -> StarBottleneckView:
    return StarBottleneckView(
        galaxy_name=galaxy.theme_name, galaxy_slug=galaxy.slug,
        slug="{0}--star-{1}".format(galaxy.slug, index),
        star_type=star.star_type, constrained_node=star.constrained_node,
        severity=star.severity, duration=star.duration,
        beneficiaries=tuple(star.beneficiaries), losers=tuple(star.losers),
        resolution_risk=star.resolution_risk, evidence=tuple(star.evidence),
        data_gaps=tuple(star.data_gaps), data_origin=star.data_origin,
    )


def _cluster_view(galaxy: DemoGalaxy) -> GalaxyClusterView:
    return GalaxyClusterView(
        theme_name=galaxy.theme_name, slug=galaxy.slug, megatrend=galaxy.megatrend,
        capital_cycle=galaxy.capital_cycle, heat_label=galaxy.heat_label,
        priority_label=galaxy.priority_label, signal_convergence=galaxy.signal_convergence,
        evidence_count=galaxy.evidence_count, data_quality=galaxy.data_quality,
        bottleneck_severity=galaxy.bottleneck_severity, candidate_count=galaxy.candidate_count,
        maturity_timing=galaxy.maturity_timing, crowded_euphoric=galaxy.crowded_euphoric,
        red_team_risk=galaxy.red_team_risk,
        data_poor=(galaxy.data_quality or "").lower() in ("low", "sparse"),
        theme_tam=galaxy.theme_tam, megatrend_magnitude=galaxy.megatrend_magnitude,
        visual_size_px=visual_size(galaxy.theme_tam, "galaxy"),
        magnitude_missing=(galaxy.theme_tam is None),
        data_origin=galaxy.data_origin,
    )


def _theme_view(galaxy: DemoGalaxy, iren_slice) -> GalaxyThemeView:
    return GalaxyThemeView(
        cluster=_cluster_view(galaxy),
        why_now=galaxy.why_now, why_before_obvious=galaxy.why_before_obvious,
        confirmed_signals=tuple(galaxy.confirmed_signals),
        speculative_signals=tuple(galaxy.speculative_signals),
        positive_catalysts=tuple(galaxy.positive_catalysts),
        negative_catalysts=tuple(galaxy.negative_catalysts),
        red_team_notes=tuple(galaxy.red_team_notes), data_gaps=tuple(galaxy.data_gaps),
        solar_systems=tuple(_solar_system_view(galaxy, ss) for ss in galaxy.solar_systems),
        stars=tuple(_star_view(galaxy, s, i) for i, s in enumerate(galaxy.stars)),
        planets=tuple(_planet_view(galaxy, p, iren_slice) for p in galaxy.planets),
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


def build_data_quality_view(iren_slice) -> DataQualityView:
    ing = iren_slice.ingestion_result
    ia = iren_slice.intelligence_assessment
    authority = getattr(ing, "authority_summary", {}) or {}

    overridden = tuple(
        "{0}: {1} ({2}) — {3}".format(
            f.get("normalized_type", ""), f.get("source_name", ""),
            f.get("source_authority", ""), f.get("reason", ""))
        for f in iren_slice.provenance_chain.get("overridden_facts", ()))

    gaps = tuple("{0}: {1}".format(kind, detail) for kind, detail in iren_slice.data_gaps)

    chain = tuple(
        "{0}. {1} {2} (v{3})".format(i + 1, r.kind, r.object_id, r.version)
        for i, r in enumerate(getattr(iren_slice.cockpit_view, "provenance_chain", ()) or ()))

    signal_n = len(getattr(ia, "signals", ()) or ()) if ia is not None else 0
    factual_n = len(getattr(ia, "factual_observation_ids", ()) or ()) if ia is not None else 0

    return DataQualityView(
        run_mode="fixture/demo (deterministic replay of local IREN fixtures)",
        fixture_demo_status="fixtures loaded; demo terrain hand-authored",
        live_enabled=False,
        scheduler_status="not enabled",
        broker_automation_status="disabled",
        manual_review_required=True,
        source_hierarchy="SEC EDGAR (canonical) > FMP (convenience) > yfinance (fallback)",
        canonical_count=int(authority.get("canonical", 0)),
        convenience_count=int(authority.get("convenience", 0)),
        fallback_count=int(authority.get("fallback", 0)),
        signal_observation_count=signal_n, factual_observation_count=factual_n,
        conflict_warnings=tuple(iren_slice.conflict_warnings),
        overridden_facts=overridden, data_gaps=gaps, provenance_chain=chain,
        real_subject=iren_slice.subject,
    )


def build_economic_universe_view(iren_slice, universe: Optional[DemoUniverse] = None
                                 ) -> EconomicUniverseView:
    """Assemble the whole read-only Economic Universe view (pure projection)."""
    universe = universe or build_demo_universe()
    themes = tuple(_theme_view(g, iren_slice) for g in universe.galaxies)
    clusters = tuple(t.cluster for t in themes)
    dashboard = build_cio_dashboard_view(themes)
    data_quality = build_data_quality_view(iren_slice)
    return EconomicUniverseView(
        mode=universe.mode, live_enabled=universe.live_enabled,
        scheduler_enabled=universe.scheduler_enabled,
        broker_automation_enabled=universe.broker_automation_enabled,
        clusters=clusters, themes=themes, dashboard=dashboard,
        data_quality=data_quality, real_subject=iren_slice.subject,
    )
