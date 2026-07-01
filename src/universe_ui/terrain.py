"""Formal, typed metadata model for the Economic Universe UI (IMPLEMENTATION-010B).

This module defines the **Knowledge Terrain** -- the single, typed SOURCE OF TRUTH
that the renderer and the Data-Quality control panel consume. It is a *metadata*
model: it describes WHAT exists in the economic map (galaxies / themes / value chains
/ bottlenecks / company planets / dependency moons / catalysts / risks) and HOW each
object is drawn (:class:`VisualEncoding`). It computes NOTHING on its own -- no score,
no ranking, no reasoning. The demo terrain (``demo_terrain.build_demo_terrain``) fills
these nodes from the existing frozen demo data plus the one real IREN slice; a later
phase (see ``terrain_adapters``) will fill them from live pipeline outputs.

Design rules baked into the shape:

* **Frozen dataclasses, stdlib only, Python 3.9, deterministic.** No clock, no
  randomness, no I/O, no network, no secrets.
* **Visual encoding is meaning-preserving, never a new metric.** Every channel on
  :class:`VisualEncoding` is a projection of an EXISTING field (economic magnitude,
  status, evidence quality, catalyst/crowding, red-team/dilution, missing data). None
  of them creates an alpha score, bucket, or ordering.
* **Semantic relationships only.** :class:`RelationshipEdge` connects two REAL node
  ids. There is NO centre-of-universe node and NO hub-and-spoke scaffold; unrelated
  objects are simply not connected. :meth:`UniverseTerrain.validate` enforces this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Set, Tuple

DATA_ORIGIN = "DEMO"


# --------------------------------------------------------------------------- #
# Visual encoding -- the meaning-preserving channels every node carries.       #
#                                                                              #
# Each channel is a projection of an EXISTING field; NONE creates alpha        #
# scoring, a bucket, or an ordering:                                           #
#                                                                              #
#   size          -> economic MAGNITUDE (market_cap / TAM / revenue pool /     #
#                    bottleneck importance / dependency exposure)              #
#   glow          -> signal HEAT / conviction / convergence (from status)      #
#   color         -> STATUS / RISK class (from data-quality / verdict)         #
#   opacity       -> EVIDENCE QUALITY (thin evidence -> more transparent)      #
#   halo          -> CATALYST presence / CROWDING                              #
#   red_shadow    -> RED-TEAM / dilution / insolvency flag                     #
#   dashed_outline-> MISSING data (a data gap, never a fabricated value)       #
#   orbit_distance-> DIRECTNESS of exposure to the bottleneck                  #
#                                                                              #
# size is DECOUPLED from glow/color/opacity/halo: a mega-cap with a weak       #
# status is drawn large but dim; a small-cap with a strong status is drawn     #
# small but bright.                                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class VisualEncoding:
    # size = economic magnitude (bounded, log-scaled pixel value from visual_size)
    size_value: int = 0
    size_basis: str = ""
    size_bucket: str = ""
    # glow = signal heat / conviction (categorical tier from EXISTING statuses)
    glow_level: int = 1
    glow_basis: str = ""
    # color = status / risk class
    color_class: str = ""
    # opacity = evidence quality
    opacity_level: str = ""
    opacity_basis: str = ""
    # halo = catalyst presence / crowding
    halo_type: str = ""
    halo_basis: str = ""
    # red-team / dilution / insolvency
    red_shadow: bool = False
    # missing data -> dashed placeholder
    dashed_outline: bool = False
    # directness of exposure to the bottleneck
    orbit_distance: Optional[float] = None
    orbit_distance_basis: str = ""
    # layout hints (purely presentational)
    position_hint: str = ""
    layout_group: str = ""
    visual_notes: str = ""


# --------------------------------------------------------------------------- #
# Leaf metadata nodes                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CatalystNode:
    id: str = ""
    related_object_id: str = ""
    catalyst_type: str = ""
    description: str = ""
    # confirmed / probable / possible / speculative_rumor
    status: str = "possible"
    expected_date_or_window: str = ""
    evidence_quality: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


@dataclass(frozen=True)
class RiskNode:
    id: str = ""
    related_object_id: str = ""
    risk_type: str = ""
    description: str = ""
    severity: str = ""
    red_team_status: str = ""
    evidence_quality: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


@dataclass(frozen=True)
class DependencyNode:
    """A supplier / dependency 'moon' hanging off a company or a bottleneck."""
    id: str = ""
    parent_company_id: str = ""
    parent_bottleneck_id: str = ""
    name: str = ""
    dependency_type: str = ""
    tier: str = ""
    exposure_type: str = ""
    magnitude: Optional[float] = None
    evidence_quality: str = ""
    missing_data: Tuple[str, ...] = field(default_factory=tuple)
    candidate_companies: Tuple[str, ...] = field(default_factory=tuple)
    economics_capture: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


@dataclass(frozen=True)
class CompanyNode:
    """A company 'planet' placed by value-chain role and proximity to a bottleneck."""
    id: str = ""
    ticker: str = ""
    company_name: str = ""
    theme_id: str = ""
    value_chain_id: str = ""
    bottleneck_id: str = ""
    value_chain_role: str = ""
    directness_to_bottleneck: str = ""
    market_cap: Optional[float] = None
    candidate_bucket: str = ""
    thesis_status: str = ""
    timing_confirmation_status: str = ""
    red_team_status: str = ""
    top_reasons: Tuple[str, ...] = field(default_factory=tuple)
    top_risks: Tuple[str, ...] = field(default_factory=tuple)
    catalysts: Tuple[CatalystNode, ...] = field(default_factory=tuple)
    dilution_or_capital_structure_warnings: Tuple[str, ...] = field(default_factory=tuple)
    data_quality: str = ""
    is_real: bool = False
    cockpit_link: Optional[str] = None
    evidence_count: int = 0
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


@dataclass(frozen=True)
class ValueChainLayer:
    """One ordered layer of a value chain (upstream .. downstream)."""
    id: str = ""
    label: str = ""
    order: int = 0
    description: str = ""
    companies: Tuple[str, ...] = field(default_factory=tuple)
    dependencies: Tuple[str, ...] = field(default_factory=tuple)
    bottleneck_exposure: str = ""
    data_quality: str = ""


@dataclass(frozen=True)
class BottleneckNode:
    """A scarce, constrained node (a 'star') that concentrates economics (10x)."""
    id: str = ""
    value_chain_id: str = ""
    name: str = ""
    bottleneck_type: str = ""
    severity: str = ""
    expected_duration: str = ""
    constrained_resource: str = ""
    beneficiaries: Tuple[str, ...] = field(default_factory=tuple)
    losers_or_risks: Tuple[str, ...] = field(default_factory=tuple)
    resolution_risk: str = ""
    evidence_quality: str = ""
    economic_importance: Optional[float] = None
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


@dataclass(frozen=True)
class ValueChainNode:
    id: str = ""
    theme_id: str = ""
    name: str = ""
    description: str = ""
    flow_layers: Tuple[ValueChainLayer, ...] = field(default_factory=tuple)
    bottlenecks: Tuple[BottleneckNode, ...] = field(default_factory=tuple)
    companies: Tuple[CompanyNode, ...] = field(default_factory=tuple)
    dependencies: Tuple[DependencyNode, ...] = field(default_factory=tuple)
    revenue_pool_or_tam: Optional[float] = None
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


@dataclass(frozen=True)
class ThemeNode:
    id: str = ""
    galaxy_id: str = ""
    name: str = ""
    thesis: str = ""
    evidence_convergence: str = ""
    why_now: str = ""
    why_before_obvious: str = ""
    value_chains: Tuple[ValueChainNode, ...] = field(default_factory=tuple)
    candidate_planets: Tuple[CompanyNode, ...] = field(default_factory=tuple)
    catalysts: Tuple[CatalystNode, ...] = field(default_factory=tuple)
    red_team_risks: Tuple[RiskNode, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


@dataclass(frozen=True)
class GalaxyNode:
    id: str = ""
    name: str = ""
    description: str = ""
    thesis_summary: str = ""
    why_now: str = ""
    why_before_obvious: str = ""
    economic_magnitude: Optional[float] = None
    heat_status: str = ""
    data_quality: str = ""
    candidate_count: int = 0
    themes: Tuple[ThemeNode, ...] = field(default_factory=tuple)
    risks: Tuple[RiskNode, ...] = field(default_factory=tuple)
    catalysts: Tuple[CatalystNode, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


@dataclass(frozen=True)
class RelationshipEdge:
    """A SEMANTIC economic relationship between two real nodes (galaxies).

    ``source_id`` and ``target_id`` MUST be real node ids in the terrain. These are
    the only lines drawn at the Universe (L0) level -- there is NO edge to any centre
    node and NO hub-and-spoke scaffold.
    """
    id: str = ""
    source_id: str = ""
    target_id: str = ""
    relationship_type: str = ""
    description: str = ""
    strength: str = ""
    evidence_quality: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_encoding: VisualEncoding = field(default_factory=VisualEncoding)


# Ids that would indicate an artificial centre node (a hub-and-spoke scaffold). These
# are matched as WHOLE ids, never substrings, so a legitimate id like "data-centers"
# is never mistaken for a centre.
_CENTRE_IDS = frozenset((
    "centre", "center", "hub", "core-of-universe", "universe-centre",
    "universe-center", "universe", "root"))
# Relationship-type tokens that would indicate a hub-and-spoke scaffold.
_HUB_TYPE_TOKENS = ("hub-and-spoke", "hub_and_spoke", "spoke", "centre-link", "center-link")


@dataclass(frozen=True)
class UniverseTerrain:
    """The whole typed terrain: galaxies + semantic edges + coverage metadata."""
    terrain_id: str = "economic-universe"
    title: str = "Economic Universe"
    # demo / fixture / live / mixed
    mode: str = "demo"
    build_id: str = ""
    galaxies: Tuple[GalaxyNode, ...] = field(default_factory=tuple)
    relationship_edges: Tuple[RelationshipEdge, ...] = field(default_factory=tuple)
    source_coverage: Dict[str, int] = field(default_factory=dict)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: Tuple[str, ...] = field(default_factory=tuple)
    visual_legend: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    warnings: Tuple[str, ...] = field(default_factory=tuple)

    # --- traversal ------------------------------------------------------- #
    def all_nodes(self) -> Tuple[Tuple[str, Any], ...]:
        """Every metadata node in the terrain, as ``(id, node)`` pairs."""
        out = []

        def add(node):
            nid = getattr(node, "id", "")
            out.append((nid, node))

        for g in self.galaxies:
            add(g)
            for r in g.risks:
                add(r)
            for cat in g.catalysts:
                add(cat)
            for th in g.themes:
                add(th)
                for cat in th.catalysts:
                    add(cat)
                for r in th.red_team_risks:
                    add(r)
                for pl in th.candidate_planets:
                    add(pl)
                    for cat in pl.catalysts:
                        add(cat)
                for vc in th.value_chains:
                    add(vc)
                    for layer in vc.flow_layers:
                        add(layer)
                    for bn in vc.bottlenecks:
                        add(bn)
                    for dep in vc.dependencies:
                        add(dep)
                    for co in vc.companies:
                        add(co)
        return tuple(out)

    def node_ids(self) -> Set[str]:
        return {nid for nid, _ in self.all_nodes() if nid}

    # --- integrity ------------------------------------------------------- #
    def validate(self, strict: bool = False) -> Tuple[str, ...]:
        """Return a tuple of integrity warnings (empty = clean).

        Flags (a) any edge whose endpoint does not resolve to a real node id, and
        (b) any edge that is a centre / hub-and-spoke scaffold. There must be none of
        either. With ``strict=True`` a non-empty result raises ``ValueError``.
        """
        ids = self.node_ids()
        warnings = list(self.warnings)
        for e in self.relationship_edges:
            if e.source_id not in ids:
                warnings.append(
                    "edge {0}: source '{1}' does not resolve".format(e.id, e.source_id))
            if e.target_id not in ids:
                warnings.append(
                    "edge {0}: target '{1}' does not resolve".format(e.id, e.target_id))
            if e.source_id == e.target_id:
                warnings.append("edge {0}: self-loop".format(e.id))
            rtype = (e.relationship_type or "").lower()
            if ((e.source_id or "").lower() in _CENTRE_IDS
                    or (e.target_id or "").lower() in _CENTRE_IDS
                    or any(tok in rtype for tok in _HUB_TYPE_TOKENS)):
                warnings.append(
                    "edge {0}: centre / hub-and-spoke scaffold detected".format(e.id))
        result = tuple(warnings)
        if strict and result:
            raise ValueError("terrain validation failed: {0}".format("; ".join(result)))
        return result
