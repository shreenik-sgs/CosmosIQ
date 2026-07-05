"""Build the demo Economic-Universe terrain AS a typed :class:`UniverseTerrain`.

``build_demo_terrain()`` is a faithful projection of the frozen synthetic demo data
(:func:`universe_ui.demo_universe.build_demo_universe`) into the typed metadata model
of :mod:`universe_ui.terrain`. It is the source of truth the renderer and the default
Data-Quality control panel consume.

Discipline (identical to the rest of this package):

* **No new scoring.** Every :class:`VisualEncoding` channel is computed with the
  EXISTING helpers -- :func:`visual_size` for magnitude size, :func:`glow_level` for
  heat, :func:`assign_buckets` / :func:`card_label_for` for a company's candidate
  bucket, and a data-quality colour/opacity map. Size encodes economic magnitude only
  and stays decoupled from ranking.
* **No real ticker in default demo.** Historical evidence-alpha slices stay in explicit
  fixture / real-run paths. The default product UI uses synthetic, non-tradeable
  company placeholders only.
* **Node ids match the render / zoom-path scheme** (galaxy id = galaxy slug, value
  chain = ``{gslug}--{vc-slug}``, bottleneck = ``{gslug}--star-N``, planet =
  :func:`planet_universe_path`, dependency = the demo node id) so the projected view
  ids -- and therefore the HTML object ids -- come from the terrain.
* **Semantic edges only, no centre.** The eight demo theme edges become
  :class:`RelationshipEdge` objects between real galaxy ids; ``terrain.validate()``
  passes with no warnings.

Deterministic, stdlib-only, Python 3.9. No clock, no randomness, no network.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .demo_universe import (
    DemoGalaxy,
    DemoPlanet,
    DemoSolarSystem,
    DemoStar,
    build_demo_universe,
    build_theme_edges,
    slugify,
)
from .terrain import (
    BottleneckNode,
    CatalystNode,
    CompanyNode,
    DependencyNode,
    GalaxyNode,
    RelationshipEdge,
    RiskNode,
    ThemeNode,
    UniverseTerrain,
    ValueChainLayer,
    ValueChainNode,
    VisualEncoding,
)
from .view_models import (
    _iren_real_status,
    assign_buckets,
    card_label_for,
    glow_level,
    planet_universe_path,
    visual_size,
)

# The eight visual channels (legend), described once.
VISUAL_LEGEND = (
    ("size", "economic magnitude (market cap / TAM / revenue pool / importance)"),
    ("glow", "signal heat / conviction / convergence (from existing status)"),
    ("color", "status / risk class (from data quality / verdict)"),
    ("opacity", "evidence quality (thin evidence -> more transparent)"),
    ("halo", "catalyst presence / crowding"),
    ("red_shadow", "red-team / dilution / insolvency flag"),
    ("dashed_outline", "missing data (a data gap, never a fabricated value)"),
    ("orbit_distance", "directness of exposure to the bottleneck"),
)


def _color_class(quality: str) -> str:
    """Colour class from data quality (mirrors render._ev_class; not a score)."""
    q = (quality or "").lower()
    if q == "sparse":
        return "ev-sparse"
    if q == "low":
        return "ev-low"
    return ""


def _opacity_level(quality: str) -> str:
    q = (quality or "").lower()
    return q or "medium"


def _catalyst_status(text: str) -> str:
    t = (text or "").lower()
    # Rumor / unconfirmed / speculative is checked FIRST so "unconfirmed" (which
    # contains the substring "confirmed") is not misread as a confirmed catalyst.
    if "rumor" in t or "unconfirmed" in t or "speculative" in t:
        return "speculative_rumor"
    if "confirmed" in t:
        return "confirmed"
    if "probable" in t:
        return "probable"
    if "possible" in t:
        return "possible"
    return "possible"


# --------------------------------------------------------------------------- #
# Encoding builders (one per object kind) -- all via EXISTING helpers          #
# --------------------------------------------------------------------------- #
def _galaxy_encoding(g: DemoGalaxy) -> VisualEncoding:
    heat = {"hot": 3, "warm": 2, "cool": 2, "dim": 1}.get((g.heat_label or "").lower(), 1)
    return VisualEncoding(
        size_value=visual_size(g.theme_tam, "galaxy"),
        size_basis="theme_tam (economic magnitude)",
        glow_level=heat, glow_basis="heat_status",
        color_class=_color_class(g.data_quality),
        opacity_level=_opacity_level(g.data_quality), opacity_basis="data_quality",
        halo_type="crowded/euphoric" if g.crowded_euphoric else "",
        halo_basis="crowded_euphoric",
        red_shadow=bool(g.red_team_risk),
        dashed_outline=(g.theme_tam is None),
        layout_group="galaxy",
        visual_notes="size=magnitude; glow=heat; NOT a candidate ranking",
    )


def _value_chain_encoding(ss: DemoSolarSystem) -> VisualEncoding:
    return VisualEncoding(
        size_value=visual_size(ss.value_chain_revenue_pool, "solar_system"),
        size_basis="value_chain_revenue_pool (economic magnitude)",
        glow_level=2, glow_basis="value-chain (neutral)",
        dashed_outline=(ss.value_chain_revenue_pool is None),
        layout_group="value_chain",
    )


def _bottleneck_encoding(star: DemoStar) -> VisualEncoding:
    high = (star.severity or "").lower() == "high"
    return VisualEncoding(
        size_value=visual_size(star.bottleneck_economic_importance, "star"),
        size_basis="bottleneck_economic_importance (economic magnitude)",
        glow_level=3 if high else 2, glow_basis="severity",
        red_shadow=high,
        dashed_outline=(star.bottleneck_economic_importance is None),
        layout_group="bottleneck",
    )


def _dependency_encoding(node) -> VisualEncoding:
    return VisualEncoding(
        size_value=visual_size(node.dependency_exposure, "moon"),
        size_basis="dependency_exposure (economic magnitude)",
        glow_level=1, glow_basis="dependency (dim)",
        color_class=_color_class(node.evidence_quality),
        opacity_level=_opacity_level(node.evidence_quality), opacity_basis="evidence_quality",
        dashed_outline=(node.dependency_exposure is None),
        orbit_distance_basis="bottleneck_exposure",
        layout_group="dependency",
    )


def _company_encoding(*, market_cap, investability_label, timing_label,
                      recommendation_label, data_quality, has_catalyst, severe,
                      directness) -> VisualEncoding:
    return VisualEncoding(
        size_value=visual_size(market_cap, "planet"),
        size_basis="market_cap (economic magnitude)",
        glow_level=glow_level(investability_label=investability_label,
                              timing_label=timing_label,
                              recommendation_label=recommendation_label),
        glow_basis="investability / timing / recommendation status",
        color_class=_color_class(data_quality),
        opacity_level=_opacity_level(data_quality), opacity_basis="data_quality",
        halo_type="catalyst" if has_catalyst else "", halo_basis="catalyst presence",
        red_shadow=bool(severe),
        dashed_outline=(market_cap is None),
        orbit_distance_basis="directness_to_bottleneck: {0}".format(directness),
        layout_group="company",
        visual_notes="size=magnitude only; glow=status; decoupled from ranking",
    )


# --------------------------------------------------------------------------- #
# Company (planet) node                                                        #
# --------------------------------------------------------------------------- #
def _company_node(g: DemoGalaxy, p: DemoPlanet, iren_slice, *, vc_id: str,
                  bottleneck_id: str, universe_path: str) -> CompanyNode:
    if p.is_real and iren_slice is not None:
        st = _iren_real_status(iren_slice)
        investability = st["investability_label"]
        timing = st["timing_label"]
        red_team = st["red_team_label"]
        recommendation = st["recommendation_label"]
        catalyst_label = st["catalyst_label"]
        cap_risk = st["capital_structure_risk"]
        source_refs = st["source_authority_badges"]
        cockpit_link = "cockpit.html"
    else:
        investability = p.investability_label
        timing = p.timing_label
        red_team = p.red_team_label
        recommendation = p.recommendation_label
        catalyst_label = p.catalyst_label
        cap_risk = p.capital_structure_risk
        source_refs = ("demo terrain — no live sources",)
        cockpit_link = None

    primary, _cross = assign_buckets(
        investability_label=investability, timing_label=timing, red_team_label=red_team,
        recommendation_label=recommendation, catalyst_label=catalyst_label,
        capital_structure_risk=cap_risk, data_quality=p.data_quality,
        evidence_count=p.evidence_count)
    bucket = "{0} ({1})".format(primary, card_label_for(primary, investability))
    severe = (red_team or "").lower() in ("concern", "fail") or bool(cap_risk)
    has_catalyst = bool((catalyst_label or "").strip())

    catalysts = ()
    if has_catalyst:
        catalysts = (CatalystNode(
            id="cat-" + slugify("{0}-{1}".format(p.ticker, catalyst_label))[:60],
            related_object_id=universe_path, catalyst_type="repricing/company",
            description=catalyst_label, status=_catalyst_status(catalyst_label),
            evidence_quality=p.data_quality),)

    dilution = ("capital-structure / dilution risk flagged",) if cap_risk else ()

    return CompanyNode(
        id=universe_path, ticker=p.ticker, company_name=p.company, theme_id=g.slug,
        value_chain_id=vc_id, bottleneck_id=bottleneck_id,
        value_chain_role=p.value_chain_role,
        directness_to_bottleneck=p.proximity_to_bottleneck, market_cap=p.market_cap,
        candidate_bucket=bucket, thesis_status=investability,
        timing_confirmation_status=timing, red_team_status=red_team,
        top_reasons=("value-chain role: {0}".format(p.value_chain_role),
                     "proximity to bottleneck: {0}".format(p.proximity_to_bottleneck)),
        top_risks=(("red-team: {0}".format(red_team),) if severe else ())
                  + ("manual review required before any action",),
        catalysts=catalysts, dilution_or_capital_structure_warnings=dilution,
        data_quality=p.data_quality, is_real=bool(p.is_real), cockpit_link=cockpit_link,
        evidence_count=p.evidence_count, source_refs=source_refs,
        visual_encoding=_company_encoding(
            market_cap=p.market_cap, investability_label=investability,
            timing_label=timing, recommendation_label=recommendation,
            data_quality=p.data_quality, has_catalyst=has_catalyst, severe=severe,
            directness=p.proximity_to_bottleneck),
    )


# --------------------------------------------------------------------------- #
# Value chain + bottleneck + dependencies                                      #
# --------------------------------------------------------------------------- #
def _value_chain_node(g: DemoGalaxy, ss: DemoSolarSystem, bottlenecks) -> ValueChainNode:
    vc_id = "{0}--{1}".format(g.slug, slugify(ss.name))
    layers = tuple(
        ValueChainLayer(
            id="{0}::layer-{1}".format(vc_id, i), label=n.role, order=i,
            description=n.economics_capture, companies=tuple(n.candidate_companies),
            dependencies=(n.node_id,), bottleneck_exposure=n.bottleneck_exposure,
            data_quality=n.evidence_quality)
        for i, n in enumerate(ss.nodes))
    deps = tuple(
        DependencyNode(
            id=n.node_id, parent_company_id="", parent_bottleneck_id=vc_id,
            name=n.role, dependency_type=n.tier, tier=n.tier,
            exposure_type=n.bottleneck_exposure, magnitude=n.dependency_exposure,
            evidence_quality=n.evidence_quality, missing_data=tuple(n.missing_data),
            candidate_companies=tuple(n.candidate_companies),
            economics_capture=n.economics_capture,
            visual_encoding=_dependency_encoding(n))
        for n in ss.nodes)
    all_missing = tuple(
        "{0}: {1}".format(n.node_id, m) for n in ss.nodes for m in n.missing_data)
    return ValueChainNode(
        id=vc_id, theme_id=g.slug, name=ss.name, description=ss.description,
        flow_layers=layers, bottlenecks=tuple(bottlenecks), dependencies=deps,
        revenue_pool_or_tam=ss.value_chain_revenue_pool, data_gaps=all_missing,
        visual_encoding=_value_chain_encoding(ss))


def _bottleneck_node(g: DemoGalaxy, star: DemoStar, vc_id: str, index: int) -> BottleneckNode:
    return BottleneckNode(
        id="{0}--star-{1}".format(g.slug, index), value_chain_id=vc_id,
        name=star.constrained_node, bottleneck_type=star.star_type,
        severity=star.severity, expected_duration=star.duration,
        constrained_resource=star.constrained_node,
        beneficiaries=tuple(star.beneficiaries), losers_or_risks=tuple(star.losers),
        resolution_risk=star.resolution_risk, evidence=tuple(star.evidence),
        economic_importance=star.bottleneck_economic_importance,
        data_gaps=tuple(star.data_gaps), visual_encoding=_bottleneck_encoding(star))


# --------------------------------------------------------------------------- #
# Galaxy + theme                                                               #
# --------------------------------------------------------------------------- #
def _galaxy_node(g: DemoGalaxy, iren_slice) -> GalaxyNode:
    gslug = g.slug
    # Bottleneck stars (shared by the galaxy's single value chain in the demo).
    bottlenecks = tuple(_bottleneck_node(g, s, "", i) for i, s in enumerate(g.stars))
    vc0 = "{0}--{1}".format(gslug, slugify(g.solar_systems[0].name)) if g.solar_systems else "vc0"
    star0 = bottlenecks[0].id if bottlenecks else "{0}--star-0".format(gslug)
    # Re-key bottlenecks with their value-chain id now that vc0 is known.
    bottlenecks = tuple(
        BottleneckNode(**{**bn.__dict__, "value_chain_id": vc0}) for bn in bottlenecks)

    value_chains = tuple(
        _value_chain_node(g, ss, bottlenecks if i == 0 else ())
        for i, ss in enumerate(g.solar_systems))

    planets = tuple(
        _company_node(g, p, iren_slice, vc_id=vc0, bottleneck_id=star0,
                      universe_path=planet_universe_path(gslug, vc0, star0, p.ticker))
        for p in g.planets)

    catalysts = tuple(
        CatalystNode(id="cat-{0}-pos-{1}".format(gslug, i), related_object_id=gslug,
                     catalyst_type="positive", description=c,
                     status=_catalyst_status(c), evidence_quality=g.data_quality)
        for i, c in enumerate(g.positive_catalysts)) + tuple(
        CatalystNode(id="cat-{0}-neg-{1}".format(gslug, i), related_object_id=gslug,
                     catalyst_type="negative", description=c,
                     status=_catalyst_status(c), evidence_quality=g.data_quality)
        for i, c in enumerate(g.negative_catalysts))

    risks = tuple(
        RiskNode(id="risk-{0}-{1}".format(gslug, i), related_object_id=gslug,
                 risk_type="red-team", description=note,
                 red_team_status="concern" if g.red_team_risk else "note",
                 severity=g.bottleneck_severity, evidence_quality=g.data_quality)
        for i, note in enumerate(g.red_team_notes))

    theme = ThemeNode(
        id=gslug, galaxy_id=gslug, name=g.theme_name, thesis=g.megatrend,
        evidence_convergence=g.signal_convergence, why_now=g.why_now,
        why_before_obvious=g.why_before_obvious, value_chains=value_chains,
        candidate_planets=planets, catalysts=catalysts, red_team_risks=risks,
        data_gaps=tuple(g.data_gaps), visual_encoding=_galaxy_encoding(g))

    return GalaxyNode(
        id=gslug, name=g.theme_name, description=g.capital_cycle,
        thesis_summary=g.megatrend, why_now=g.why_now,
        why_before_obvious=g.why_before_obvious, economic_magnitude=g.theme_tam,
        heat_status=g.heat_label, data_quality=g.data_quality,
        candidate_count=g.candidate_count, themes=(theme,), risks=risks,
        catalysts=catalysts, visual_encoding=_galaxy_encoding(g))


# --------------------------------------------------------------------------- #
# Data-quality bundle for the default synthetic demo terrain                   #
# --------------------------------------------------------------------------- #
def _data_quality_bundle(iren_slice):
    if iren_slice is None:
        return (
            {"canonical": 0, "convenience": 0, "fallback": 0, "signal": 0, "factual": 0},
            ("demo terrain only: no active run candidate provenance",),
            (),
            (),
        )
    ing = iren_slice.ingestion_result
    ia = iren_slice.intelligence_assessment
    authority = getattr(ing, "authority_summary", {}) or {}
    signal_n = len(getattr(ia, "signals", ()) or ()) if ia is not None else 0
    factual_n = len(getattr(ia, "factual_observation_ids", ()) or ()) if ia is not None else 0
    coverage = {
        "canonical": int(authority.get("canonical", 0)),
        "convenience": int(authority.get("convenience", 0)),
        "fallback": int(authority.get("fallback", 0)),
        "signal": signal_n,
        "factual": factual_n,
    }
    gaps = tuple("{0}: {1}".format(kind, detail) for kind, detail in iren_slice.data_gaps)
    provenance = tuple(
        "{0}. {1} {2} (v{3})".format(i + 1, r.kind, r.object_id, r.version)
        for i, r in enumerate(getattr(iren_slice.cockpit_view, "provenance_chain", ()) or ()))
    warnings = tuple(iren_slice.conflict_warnings)
    return coverage, gaps, provenance, warnings


# --------------------------------------------------------------------------- #
# Relationship edges (semantic; between real galaxy ids; no centre)            #
# --------------------------------------------------------------------------- #
def _relationship_edges(galaxies) -> Tuple[RelationshipEdge, ...]:
    slug_by_name = {g.theme_name: g.slug for g in galaxies}
    out = []
    for e in build_theme_edges():
        src = slug_by_name.get(e.source)
        tgt = slug_by_name.get(e.target)
        if not src or not tgt or src == tgt:
            continue
        out.append(RelationshipEdge(
            id="edge-{0}--{1}".format(src, tgt), source_id=src, target_id=tgt,
            relationship_type=e.type, description=e.reason, strength=e.strength,
            evidence_quality=e.evidence_quality,
            visual_encoding=VisualEncoding(
                glow_basis="semantic relationship", visual_notes="semantic edge; no centre")))
    return tuple(out)


def build_demo_terrain(iren_slice=None, universe=None) -> UniverseTerrain:
    """Build the demo terrain AS a typed :class:`UniverseTerrain` (source of truth)."""
    universe = universe or build_demo_universe()
    galaxies = tuple(_galaxy_node(g, iren_slice) for g in universe.galaxies)
    edges = _relationship_edges(universe.galaxies)
    coverage, gaps, provenance, _conflicts = _data_quality_bundle(iren_slice)
    # terrain.warnings is reserved for integrity/authoring notes (empty for the clean
    # demo); data-quality conflict warnings are surfaced by the Data-Quality view.
    terrain = UniverseTerrain(
        terrain_id="economic-universe", title="Economic Universe",
        mode="demo", build_id="demo-terrain",
        galaxies=galaxies, relationship_edges=edges, source_coverage=coverage,
        data_gaps=gaps, provenance_refs=provenance, visual_legend=VISUAL_LEGEND,
        warnings=())
    return terrain
