"""On-demand REAL evidence WATCHLIST terrain builder (IMPLEMENTATION-010E).

``build_real_evidence_watchlist_terrain`` extends the accepted 010D single-ticker
``real_evidence_on_demand`` mode to a small, EXPLICIT watchlist. It builds ONE sparse,
honest, merged :class:`~universe_ui.terrain.UniverseTerrain` (mode
``real_evidence_on_demand``) containing multiple real, evidence-derived company planets.

Discipline (inherited from 010D and NOT relaxed):

* **Manual / on-demand only.** No scheduler, no background job, no broker automation, no
  automated trading, no new scoring / ranking / reasoning. Real mode is never the default.
* **Per-ticker isolation.** Each ticker is built INDEPENDENTLY in its own try/except via
  :func:`~universe_ui.real_terrain.build_real_evidence_terrain_for_ticker`. A ticker that
  raises is RECORDED (status ``failed`` + reason) and does NOT abort the run; the run
  fails only if EVERY ticker fails. Failures are never silently dropped and never padded
  with demo data.
* **No fake centre.** The per-ticker sparse terrains are merged by INFERRED theme:
  same-theme companies co-locate under ONE galaxy/theme (co-location IS the relationship);
  a company whose theme could not be inferred goes under an explicit ``unclassified``
  region. No default hub, no centre-of-universe, no watchlist-centre, and no edge is drawn
  just because tickers share a run. ``relationship_edges`` stays empty unless a genuine
  evidence-backed semantic relationship exists (the current fixtures yield none).
* **No network on import.** This module imports only the pure builder; the network
  boundary stays lazily imported inside ``real_terrain`` / ``live_transport``.

Deterministic where testable: with injected mock transports + a fixed ``now`` the merged
terrain is byte-stable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from .terrain import (
    CatalystNode,
    CompanyNode,
    DependencyNode,
    GalaxyNode,
    RiskNode,
    ThemeNode,
    UniverseTerrain,
    ValueChainNode,
    VisualEncoding,
)
from .view_models import planet_universe_path, slugify

# Keep the watchlist SMALL and explicit: each ticker is a real, on-demand network fetch
# (SEC + FMP + optional yfinance) with no caching, so a large list would hammer sources
# and slow a manual run. A human curates this list; a handful is the intended scale.
MAX_WATCHLIST_TICKERS = 10

_UNCLASSIFIED_SLUG = "unclassified"
_UNCLASSIFIED_NAME = "Unclassified / needs theme inference"


def normalize_tickers(raw: Any) -> Tuple[str, ...]:
    """Normalise a watchlist spec into clean tickers: strip / upper / dedupe (first-seen).

    Accepts a list/tuple of tickers OR a single comma-separated string
    (``"IREN,AAOI,INOD"`` -- the simpler CLI form). Empty / whitespace entries are
    dropped. The result preserves first-seen order and contains no duplicates.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = []
        for item in raw:
            parts.extend(str(item).split(","))
    out: List[str] = []
    seen = set()
    for part in parts:
        tk = str(part).strip().upper()
        if not tk or tk in seen:
            continue
        seen.add(tk)
        out.append(tk)
    return tuple(out)


# --------------------------------------------------------------------------- #
# Per-ticker record + run summary                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WatchlistTickerRecord:
    """Honest per-ticker outcome of one watchlist run (built / failed / deferred)."""
    ticker: str
    status: str  # "built" / "failed" / "deferred"
    reason: str = ""
    sec_status: str = ""
    fmp_status: str = ""
    yfinance_status: str = ""
    canonical: int = 0
    convenience: int = 0
    fallback: int = 0
    conflicts: int = 0
    data_gaps: Tuple[str, ...] = ()
    provenance_refs: Tuple[str, ...] = ()
    terrain_status: str = ""
    group: str = ""


@dataclass(frozen=True)
class WatchlistRunSummary:
    """Merged, honest summary of a whole watchlist run.

    Carries the per-ticker records plus merged source-coverage totals, data gaps,
    conflict warnings and overridden facts across all successfully-built tickers. The
    per-company slices (for the view projection) and a representative slice (for the
    cockpit page) ride along as side-channels; they are not rendered directly.
    """
    requested: Tuple[str, ...]
    records: Tuple[WatchlistTickerRecord, ...]
    source_coverage: Dict[str, int] = field(default_factory=dict)
    data_gaps: Tuple[str, ...] = ()
    conflict_warnings: Tuple[str, ...] = ()
    overridden_facts: Tuple[dict, ...] = ()
    provenance_refs: Tuple[str, ...] = ()
    deferred_records_count: int = 0
    run_timestamp: str = ""
    slice_by_subject: Dict[str, Any] = field(default_factory=dict)
    representative_slice: Any = None
    representative_ticker: str = ""
    # IMPLEMENTATION-011C: source-backed enrichment bundle per built ticker (or None). Rides
    # along so the app drives the DQ coverage panel + per-company cards + cockpit note.
    enrichment_by_subject: Dict[str, Any] = field(default_factory=dict)

    @property
    def enrichment_bundles(self) -> Tuple[Any, ...]:
        return tuple(b for b in self.enrichment_by_subject.values() if b is not None)

    @property
    def succeeded_count(self) -> int:
        return sum(1 for r in self.records if r.status == "built")

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.records if r.status == "failed")

    @property
    def deferred_count(self) -> int:
        return sum(1 for r in self.records if r.status == "deferred")

    @property
    def requested_count(self) -> int:
        return len(self.requested)

    @property
    def failed_or_deferred_count(self) -> int:
        return self.failed_count + self.deferred_count


# --------------------------------------------------------------------------- #
# Rekeying: namespace a single-ticker galaxy's internal ids by ticker so that   #
# merged tickers never collide, while re-parenting it to a shared group slug.    #
# --------------------------------------------------------------------------- #
@dataclass
class _RekeyedGalaxy:
    group_slug: str
    group_name: str
    value_chains: Tuple[ValueChainNode, ...]
    planets: Tuple[CompanyNode, ...]
    catalysts: Tuple[CatalystNode, ...]
    risks: Tuple[RiskNode, ...]
    data_gaps: Tuple[str, ...]
    heat_status: str
    thesis_summary: str
    why_now: str
    why_before_obvious: str
    description: str
    galaxy_encoding: VisualEncoding


def _rekey_galaxy(galaxy: GalaxyNode, ticker: str, *, group_slug: str,
                  group_name: str) -> _RekeyedGalaxy:
    """Re-id a single-ticker galaxy's contents under ``group_slug`` with a ``ticker``
    namespace, so several tickers can share ONE galaxy/theme with globally-unique ids.

    Structural ids (value chains, bottlenecks, dependencies, catalysts, risks) that were
    prefixed with the galaxy's own slug are re-prefixed ``<group_slug>--<ticker>--``; the
    galaxy/theme self-id becomes ``group_slug``; each company's universe path is rebuilt
    from the new (group, value-chain, bottleneck, ticker) coordinates. Cockpit links are
    routed to a per-ticker cockpit page (only where a cockpit exists).
    """
    old = galaxy.id
    ns = slugify(ticker)
    sp = "{0}--{1}".format(group_slug, ns)  # structural prefix for this ticker's subtree

    def rem(node_id: str) -> str:
        if node_id and node_id.startswith(old + "--"):
            return sp + node_id[len(old):]
        return node_id

    def top(node_id: str) -> str:
        return group_slug if node_id == old else rem(node_id)

    def rekey_catalyst(c: CatalystNode) -> CatalystNode:
        return replace(c, id=rem(c.id), related_object_id=top(c.related_object_id))

    def rekey_risk(r: RiskNode) -> RiskNode:
        return replace(r, id=rem(r.id), related_object_id=top(r.related_object_id))

    def rekey_dep(d: DependencyNode) -> DependencyNode:
        return replace(d, id=rem(d.id),
                       parent_company_id=rem(d.parent_company_id),
                       parent_bottleneck_id=rem(d.parent_bottleneck_id))

    theme = galaxy.themes[0] if galaxy.themes else ThemeNode(id=old, galaxy_id=old)

    new_vcs = []
    for vc in theme.value_chains:
        new_bns = tuple(replace(bn, id=rem(bn.id), value_chain_id=rem(bn.value_chain_id))
                        for bn in vc.bottlenecks)
        new_deps = tuple(rekey_dep(d) for d in vc.dependencies)
        new_vcs.append(replace(vc, id=rem(vc.id), theme_id=group_slug,
                               bottlenecks=new_bns, dependencies=new_deps, companies=()))

    new_planets = []
    for co in theme.candidate_planets:
        new_vc_id = rem(co.value_chain_id)
        new_bn_id = rem(co.bottleneck_id)
        new_path = planet_universe_path(group_slug, new_vc_id, new_bn_id, co.ticker)
        new_cats = tuple(
            replace(c, id="{0}--cat-{1}".format(new_path, i), related_object_id=new_path)
            for i, c in enumerate(co.catalysts))
        cockpit = ("cockpit_{0}.html".format(slugify(co.ticker))
                   if co.cockpit_link else None)
        new_planets.append(replace(
            co, id=new_path, theme_id=group_slug, value_chain_id=new_vc_id,
            bottleneck_id=new_bn_id, catalysts=new_cats, cockpit_link=cockpit))

    new_cats = tuple(rekey_catalyst(c) for c in theme.catalysts)
    new_risks = tuple(rekey_risk(r) for r in theme.red_team_risks)
    return _RekeyedGalaxy(
        group_slug=group_slug, group_name=group_name,
        value_chains=tuple(new_vcs), planets=tuple(new_planets),
        catalysts=new_cats, risks=new_risks, data_gaps=tuple(theme.data_gaps),
        heat_status=galaxy.heat_status, thesis_summary=galaxy.thesis_summary,
        why_now=galaxy.why_now, why_before_obvious=galaxy.why_before_obvious,
        description=galaxy.description, galaxy_encoding=galaxy.visual_encoding)


# --------------------------------------------------------------------------- #
# Merge: group rekeyed galaxies by theme into ONE UniverseTerrain              #
# --------------------------------------------------------------------------- #
def _merge_terrain(built: List[Tuple[str, GalaxyNode, Any]], *,
                   run_ts: str) -> Tuple[UniverseTerrain, Tuple[str, ...]]:
    """Merge per-ticker galaxies into ONE terrain, grouping same-theme companies.

    ``built`` is an ordered list of ``(ticker, galaxy, slice)``. Returns the merged
    terrain, the summed source-coverage totals and the merged data-gap list.
    """
    order: List[str] = []
    groups: Dict[str, List[_RekeyedGalaxy]] = {}
    for ticker, galaxy, sl in built:
        has_theme = getattr(sl, "opportunity_hypothesis", None) is not None
        if has_theme and galaxy.id and galaxy.id != _UNCLASSIFIED_SLUG:
            group_slug = galaxy.id
            group_name = galaxy.name or group_slug
        else:
            group_slug = _UNCLASSIFIED_SLUG
            group_name = _UNCLASSIFIED_NAME
        rk = _rekey_galaxy(galaxy, ticker, group_slug=group_slug, group_name=group_name)
        if group_slug not in groups:
            groups[group_slug] = []
            order.append(group_slug)
        groups[group_slug].append(rk)

    galaxies: List[GalaxyNode] = []
    all_gaps: List[str] = []
    for group_slug in order:
        parts = groups[group_slug]
        first = parts[0]
        value_chains: List[ValueChainNode] = []
        planets: List[CompanyNode] = []
        catalysts: List[CatalystNode] = []
        risks: List[RiskNode] = []
        gaps: List[str] = []
        for rk in parts:
            value_chains.extend(rk.value_chains)
            planets.extend(rk.planets)
            catalysts.extend(rk.catalysts)
            risks.extend(rk.risks)
            gaps.extend(rk.data_gaps)
        is_unclassified = group_slug == _UNCLASSIFIED_SLUG
        theme_name = first.group_name
        theme = ThemeNode(
            id=group_slug, galaxy_id=group_slug, name=theme_name,
            thesis=first.thesis_summary,
            evidence_convergence=(
                "co-located watchlist candidates sharing the inferred theme "
                "(co-location is the only relationship asserted)"
                if not is_unclassified else
                "theme not inferred from evidence — candidates parked for manual triage"),
            why_now=first.why_now, why_before_obvious=first.why_before_obvious,
            value_chains=tuple(value_chains), candidate_planets=tuple(planets),
            catalysts=tuple(catalysts), red_team_risks=tuple(risks),
            data_gaps=tuple(dict.fromkeys(gaps)),
            visual_encoding=first.galaxy_encoding)
        galaxy = GalaxyNode(
            id=group_slug, name=theme_name,
            description=(first.description if not is_unclassified else
                         "Companies whose theme / value-chain could not be inferred from "
                         "the ingested evidence — parked here for manual theme inference "
                         "(nothing fabricated)."),
            thesis_summary=first.thesis_summary, why_now=first.why_now,
            why_before_obvious=first.why_before_obvious, economic_magnitude=None,
            heat_status=(first.heat_status if not is_unclassified else "dim"),
            data_quality=("medium" if not is_unclassified else "sparse"),
            candidate_count=len(planets), themes=(theme,), risks=tuple(risks),
            catalysts=tuple(catalysts),
            visual_encoding=(first.galaxy_encoding if not is_unclassified else replace(
                first.galaxy_encoding, glow_level=1,
                visual_notes="unclassified region — neutral, dashed; needs theme inference")))
        galaxies.append(galaxy)
        all_gaps.extend(gaps)

    terrain = UniverseTerrain(
        terrain_id="economic-universe",
        title="Economic Universe (real evidence watchlist, on demand)",
        mode="real_evidence_on_demand",
        build_id="real-watchlist-terrain-{0}".format(len(built)),
        galaxies=tuple(galaxies),
        relationship_edges=(),  # only evidence-backed semantic edges; fixtures yield none
        source_coverage={},     # filled by caller (summed across tickers)
        data_gaps=(),           # filled by caller (header + per-ticker gaps)
        provenance_refs=(),     # filled by caller
        visual_legend=(
            ("size", "economic magnitude (missing here -> neutral, dashed)"),
            ("glow", "signal heat / conviction (from existing status)"),
            ("red_shadow", "red-team / dilution flag"),
            ("dashed_outline", "missing data (a data gap, never a fabricated value)"),
        ),
        warnings=())
    return terrain, tuple(all_gaps)


def build_real_evidence_watchlist_terrain(
    tickers: Any, *,
    transports_by_ticker: Optional[Dict[str, Dict[str, Callable[[str], Any]]]] = None,
    transports: Optional[Dict[str, Callable[[str], Any]]] = None,
    sec_user_agent: Optional[str] = None,
    fmp_api_key: Optional[str] = None,
    enable_yfinance: bool = False,
    domain: str = "ai-infrastructure",
    enrich: bool = False,
    now: Optional[float] = None,
    actor: str = "real-evidence-watchlist-on-demand",
) -> Tuple[UniverseTerrain, WatchlistRunSummary]:
    """Build ONE merged sparse REAL-evidence terrain for a small explicit watchlist.

    Each ticker is processed INDEPENDENTLY (try/except): a failure is recorded and the run
    continues; the run raises only if EVERY ticker fails or the list is empty. Returns
    ``(terrain, WatchlistRunSummary)``.

    ``transports_by_ticker[ticker]`` injects a MOCK transport bundle per ticker (tests,
    fully offline). Absent that, the per-ticker ``transports`` (or, if also None, the real
    lazily-built transports from the supplied credentials) are used. ``now`` is injectable
    for deterministic offline builds.
    """
    from .real_terrain import build_real_evidence_terrain_for_ticker

    requested = normalize_tickers(tickers)
    if not requested:
        raise ValueError(
            "real_evidence_on_demand watchlist requires at least one ticker "
            "(empty / whitespace list rejected; nothing fetched)")
    if len(requested) > MAX_WATCHLIST_TICKERS:
        raise ValueError(
            "watchlist too large: {0} tickers requested, max {1} (keep it small — every "
            "ticker is a live, uncached, manual fetch)".format(
                len(requested), MAX_WATCHLIST_TICKERS))

    run_now = float(now) if now is not None else time.time()
    run_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(run_now))
    tbt = transports_by_ticker or {}

    built: List[Tuple[str, GalaxyNode, Any]] = []
    records: List[WatchlistTickerRecord] = []
    slice_by_subject: Dict[str, Any] = {}
    enrichment_by_subject: Dict[str, Any] = {}
    coverage_total: Dict[str, int] = {}
    merged_conflicts: List[str] = []
    merged_overridden: List[dict] = []
    merged_provenance: List[str] = []
    deferred_records_total = 0

    for ticker in requested:
        ticker_transports = tbt.get(ticker, transports)
        try:
            terrain_i, status_i = build_real_evidence_terrain_for_ticker(
                ticker, transports=ticker_transports, sec_user_agent=sec_user_agent,
                fmp_api_key=fmp_api_key, enable_yfinance=enable_yfinance, domain=domain,
                enrich=enrich, now=run_now, actor=actor)
        except Exception as exc:  # noqa: BLE001 -- isolate: one bad ticker never aborts
            records.append(WatchlistTickerRecord(
                ticker=ticker, status="failed",
                reason="{0}: {1}".format(type(exc).__name__, str(exc)[:160]),
                sec_status="not run", fmp_status="not run", yfinance_status="not run",
                terrain_status="failed"))
            continue

        sl = status_i.get("slice_result")
        slice_by_subject[ticker] = sl
        enrichment_by_subject[ticker] = status_i.get("enrichment")
        galaxy = terrain_i.galaxies[0] if terrain_i.galaxies else GalaxyNode(id=domain)
        built.append((ticker, galaxy, sl))

        cov = terrain_i.source_coverage or {}
        for k, v in cov.items():
            coverage_total[k] = coverage_total.get(k, 0) + int(v)
        conflicts = tuple(getattr(sl, "conflict_warnings", ()) or ())
        merged_conflicts.extend("{0}: {1}".format(ticker, c) for c in conflicts)
        overridden = tuple(
            getattr(sl, "provenance_chain", {}).get("overridden_facts", ()) or ())
        merged_overridden.extend(overridden)
        merged_provenance.extend(
            "{0}: {1}".format(ticker, ref) for ref in terrain_i.provenance_refs)
        deferred_records_total += len(getattr(sl, "deferred_records", ()) or ())

        records.append(WatchlistTickerRecord(
            ticker=ticker, status="built", reason="",
            sec_status=str(status_i.get("sec", "")),
            fmp_status=str(status_i.get("fmp", "")),
            yfinance_status=str(status_i.get("yfinance", "")),
            canonical=int(cov.get("canonical", 0)),
            convenience=int(cov.get("convenience", 0)),
            fallback=int(cov.get("fallback", 0)), conflicts=len(conflicts),
            data_gaps=tuple(terrain_i.data_gaps), provenance_refs=terrain_i.provenance_refs,
            terrain_status="built"))

    if not built:
        reasons = "; ".join("{0}: {1}".format(r.ticker, r.reason) for r in records)
        raise ValueError(
            "watchlist run failed — all {0} tickers failed ({1})".format(
                len(requested), reasons or "no successful builds"))

    terrain, per_ticker_gaps = _merge_terrain(built, run_ts=run_ts)

    header_gap = (
        "terrain incomplete — real-evidence watchlist of {0} companies "
        "({1} built / {2} failed-or-deferred); sparse per-company terrains merged by "
        "inferred theme; missing-data placeholders shown, nothing fabricated".format(
            len(requested), len(built),
            len(requested) - len(built)))
    manual_gap = (
        "real evidence on demand — manual refresh only; not scheduled; not "
        "broker-connected; data may be incomplete")
    failure_gaps = tuple(
        "ticker {0}: {1} ({2})".format(r.ticker, r.status, r.reason)
        for r in records if r.status != "built")
    merged_gaps = ((header_gap, manual_gap) + failure_gaps
                   + tuple(dict.fromkeys(per_ticker_gaps)))

    terrain = replace(
        terrain, source_coverage=dict(coverage_total), data_gaps=merged_gaps,
        provenance_refs=tuple(merged_provenance))

    # Representative slice for the shared cockpit.html: the first built ticker that
    # actually produced a decision cockpit (else the first built ticker).
    rep_ticker = ""
    rep_slice = None
    for ticker, _g, sl in built:
        if rep_slice is None:
            rep_slice = sl
            rep_ticker = ticker
        if getattr(sl, "cockpit_view", None) is not None:
            rep_slice = sl
            rep_ticker = ticker
            break

    summary = WatchlistRunSummary(
        requested=requested, records=tuple(records),
        source_coverage=dict(coverage_total), data_gaps=merged_gaps,
        conflict_warnings=tuple(merged_conflicts),
        overridden_facts=tuple(merged_overridden),
        provenance_refs=tuple(merged_provenance),
        deferred_records_count=deferred_records_total, run_timestamp=run_ts,
        slice_by_subject=slice_by_subject, representative_slice=rep_slice,
        representative_ticker=rep_ticker,
        enrichment_by_subject=enrichment_by_subject)
    return terrain, summary
