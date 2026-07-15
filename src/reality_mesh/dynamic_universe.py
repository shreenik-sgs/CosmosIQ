"""The DYNAMIC theme graph from the operator-accepted universe (UNIVERSE-DISCOVERY UD-4).

This is the slice that ENDS hand-curation: the operator-accepted, evidence-grounded universe
(UD-3, :func:`~reality_mesh.accepted_universe.accepted_universe`) becomes the watchlist AND the
theme graph that drives discovery + the diligence lineage -- WITHOUT ever fabricating a theme, a
company, or a value-chain / chokepoint analysis.

It is strictly ADDITIVE and COMPOSES existing parts -- it re-implements nothing:

* :func:`build_accepted_theme_graph` reads the accepted universe and returns a
  :class:`~reality_mesh.theme_graph.ThemeGraph` whose Monitored Company Universe is EXACTLY the
  accepted tickers, mapped under their accepted themes. The seed graph
  (:func:`~reality_mesh.theme_graph.build_seed_theme_graph`) and every default lineage / pulse
  path are byte-identical -- this builder is never on the default path.
* :func:`accepted_watchlist` is the accepted tickers (for :func:`~reality_mesh.live_pulse.
  run_live_pulse`).
* :func:`run_lineage_on_accepted_universe` runs the UNCHANGED
  :func:`~reality_mesh.diligence_lineage.run_diligence_lineage` with the dynamic graph + the
  accepted watchlist -- passing them, never altering its behaviour.

HONESTY IS THE INVARIANT (build ONLY from operator-accepted, evidence-grounded entries):

* the dynamic graph contains ONLY accepted tickers, each under its accepted theme(s);
* an accepted ``theme_id`` that EXISTS in the base (seed) map links the company to that theme's
  REAL bottleneck(s) -- the real value-chain / chokepoint structure is reused, never re-invented;
* an accepted ``theme_id`` NOT in the base gets a MINIMAL operator-defined scaffold -- the theme,
  ONE value chain, and ONE NEUTRAL membership node (``is_chokepoint=False``, no invented "why it
  matters" chokepoint rationale) explicitly labelled operator-defined so the UI can show it lacks
  a real value-chain analysis. A theme / company / chokepoint is NEVER fabricated;
* an EMPTY accepted universe -> an empty, honest graph (0 monitored tickers) -- NEVER the seed
  fallback silently;
* the lineage honesty ceiling is preserved end-to-end: a graph-connected accepted ticker with NO
  real corroborating evidence stays ``blocked_insufficient_evidence`` / ``monitor_only``; nothing
  is forced to ``eligible`` (the slice-2 diligence gate + healthy-DQ gate still apply). No
  fixture-as-real (PROD-LIVE-4).

Deterministic (order-stable by accepted order; ``now`` injected), stdlib-only, Python 3.9,
OFFLINE. No network / scheduler / broker; no wall-clock; no trade / order / score / rank field.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .accepted_universe import accepted_universe
from .diligence_lineage import DiligenceLineageResult, run_diligence_lineage
from .theme_graph import (
    Bottleneck,
    CompanyUniverseNode,
    MegaTheme,
    Theme,
    ThemeGraph,
    ValueChain,
    build_seed_theme_graph,
)

__all__ = [
    "OPERATOR_MEGA_THEME_ID",
    "OPERATOR_MEMBERSHIP_LABEL",
    "OPERATOR_MEMBERSHIP_NOTE",
    "accepted_graph_provenance",
    "accepted_watchlist",
    "build_accepted_theme_graph",
    "run_lineage_on_accepted_universe",
]

#: The single operator-defined MegaTheme container that holds scaffold themes for accepted
#: ``theme_id``s the base map does not know. It exists ONLY to keep the graph referentially whole;
#: it invents no thesis.
OPERATOR_MEGA_THEME_ID = "operator-accepted-universe"

#: The NEUTRAL membership node's name -- explicitly NOT a chokepoint. It records only that the
#: operator filed the company under this theme; it makes NO value-chain / chokepoint claim.
OPERATOR_MEMBERSHIP_LABEL = "theme membership (operator-accepted)"

#: The honest note carried by an operator-defined scaffold bottleneck: it exists so the UI can
#: show the theme lacks a real value-chain analysis. It states an ABSENCE, never a fabricated
#: rationale.
OPERATOR_MEMBERSHIP_NOTE = (
    "operator-defined theme membership -- no real value-chain / chokepoint analysis exists yet "
    "(NOT a chokepoint; nothing fabricated)")


def accepted_watchlist(store_dir: str) -> Tuple[str, ...]:
    """The accepted tickers -- the working watchlist for a live pulse (order-stable, distinct).

    Reads :func:`~reality_mesh.accepted_universe.accepted_universe` and returns each accepted
    ticker once, in first-accepted order. An empty accepted universe -> ``()`` (never a seed
    fallback). Deterministic; offline; no fabrication.
    """
    out: List[str] = []
    for entry in accepted_universe(store_dir):
        ticker = str(entry.ticker or "").strip().upper()
        if ticker and ticker not in out:
            out.append(ticker)
    return tuple(out)


def _base_lookups(base: ThemeGraph):
    """Order-stable lookup structures over the base map (mega ids, theme ids, chain->theme...)."""
    mega_ids = {m.mega_theme_id for m in base.mega_themes}
    theme_ids = {t.theme_id for t in base.themes}
    themes_of_mega: Dict[str, List[str]] = {}
    for t in base.themes:
        themes_of_mega.setdefault(t.mega_theme_ref, []).append(t.theme_id)
    chains_of_theme: Dict[str, List[str]] = {}
    for v in base.value_chains:
        chains_of_theme.setdefault(v.theme_ref, []).append(v.value_chain_id)
    bns_of_chain: Dict[str, List[str]] = {}
    for b in base.bottlenecks:
        bns_of_chain.setdefault(b.value_chain_ref, []).append(b.bottleneck_id)
    return mega_ids, theme_ids, themes_of_mega, chains_of_theme, bns_of_chain


def _base_bottlenecks_for(theme_id: str, mega_ids, theme_ids, themes_of_mega,
                          chains_of_theme, bns_of_chain) -> Tuple[str, ...]:
    """The REAL base bottleneck ids reachable from an accepted ``theme_id`` (order-stable).

    Resolves ``theme_id`` whether it names a base :class:`Theme` (direct) or a base
    :class:`MegaTheme` (all its themes). Returns ``()`` when the base map knows no bottleneck for
    it -- the caller then builds the operator-defined scaffold instead. NEVER invents a bottleneck.
    """
    resolved_themes: List[str] = []
    if theme_id in theme_ids:
        resolved_themes.append(theme_id)
    if theme_id in mega_ids:
        for tid in themes_of_mega.get(theme_id, []):
            if tid not in resolved_themes:
                resolved_themes.append(tid)
    out: List[str] = []
    for tid in resolved_themes:
        for chain in chains_of_theme.get(tid, []):
            for bn in bns_of_chain.get(chain, []):
                if bn not in out:
                    out.append(bn)
    return tuple(out)


def build_accepted_theme_graph(store_dir: str, *, base: Optional[ThemeGraph] = None,
                               now: str = "") -> ThemeGraph:
    """Build the DYNAMIC theme graph from the operator-accepted universe (UD-4). ADDITIVE.

    Reads :func:`~reality_mesh.accepted_universe.accepted_universe` and returns a
    :class:`~reality_mesh.theme_graph.ThemeGraph` whose ``monitored_tickers`` is EXACTLY the
    accepted tickers (distinct, first-accepted order). Mapping rules -- NEVER fabricate:

    * an accepted ``theme_id`` that EXISTS in ``base`` (or the seed map) -> the company node is
      linked to THAT theme's REAL bottleneck(s), reusing the real value-chain / chokepoint
      structure (so :func:`~reality_mesh.discovery._theme_refs_for` resolves it to the real theme);
    * an accepted ``theme_id`` NOT in the base -> a MINIMAL operator-defined scaffold: the theme
      (under the single :data:`OPERATOR_MEGA_THEME_ID`), ONE value chain, and ONE NEUTRAL
      membership :class:`Bottleneck` (:data:`OPERATOR_MEMBERSHIP_LABEL`, ``is_chokepoint=False``,
      only :data:`OPERATOR_MEMBERSHIP_NOTE` -- an ABSENCE, not an invented chokepoint claim). The
      company is linked to it. It is clearly operator-defined so the UI can show it lacks a real
      value-chain analysis.

    The base map's real theme / value-chain / bottleneck / catalyst / risk / weak-signal structure
    is REUSED (so real red-team risks correctly apply to an accepted ticker under a real theme);
    only the Monitored Company Universe is replaced with the accepted tickers, and base company
    dependencies are dropped unless BOTH endpoints are accepted (no dangling ref). An EMPTY
    accepted universe -> an empty ``ThemeGraph`` (0 monitored tickers) -- NEVER the seed fallback.

    ``now`` is accepted for API symmetry (the graph carries no timestamp); construction is fully
    deterministic and offline. Does NOT change :func:`~reality_mesh.theme_graph.build_seed_theme_graph`
    or any default path -- it is only ever called explicitly.
    """
    entries = accepted_universe(store_dir)
    if not entries:
        # Honest empty graph: 0 monitored tickers. NEVER a silent seed fallback.
        return ThemeGraph()

    the_base = base if base is not None else build_seed_theme_graph()
    (mega_ids, theme_ids, themes_of_mega,
     chains_of_theme, bns_of_chain) = _base_lookups(the_base)

    # -- per distinct ticker, collect its linked bottleneck refs across ALL its accepted themes -- #
    ticker_order: List[str] = []
    links_by_ticker: Dict[str, List[str]] = {}
    scaffold_themes: Dict[str, str] = {}      # accepted theme_id -> scaffold theme id (order-stable)
    scaffold_order: List[str] = []
    need_operator_mega = False

    for entry in entries:
        ticker = str(entry.ticker or "").strip().upper()
        theme_id = str(entry.theme_id or "").strip()
        if not ticker or not theme_id:
            continue
        if ticker not in links_by_ticker:
            ticker_order.append(ticker)
            links_by_ticker[ticker] = []

        base_bns = _base_bottlenecks_for(
            theme_id, mega_ids, theme_ids, themes_of_mega, chains_of_theme, bns_of_chain)
        if base_bns:
            # EXISTING seed theme -> reuse its REAL bottleneck(s).
            for bn in base_bns:
                if bn not in links_by_ticker[ticker]:
                    links_by_ticker[ticker].append(bn)
        else:
            # NEW theme -> a minimal, NEUTRAL, operator-defined scaffold (built once per theme_id).
            if theme_id not in scaffold_themes:
                # Namespace the scaffold theme id only if it would collide with a base id.
                sid = (theme_id if theme_id not in theme_ids and theme_id not in mega_ids
                       else "operator:{0}".format(theme_id))
                scaffold_themes[theme_id] = sid
                scaffold_order.append(theme_id)
                need_operator_mega = True
            sid = scaffold_themes[theme_id]
            bn_id = "bn:operator:{0}".format(sid)
            if bn_id not in links_by_ticker[ticker]:
                links_by_ticker[ticker].append(bn_id)

    # -- assemble the scaffold structural nodes (deterministic, order-stable) -- #
    extra_megas: List[MegaTheme] = []
    extra_themes: List[Theme] = []
    extra_chains: List[ValueChain] = []
    extra_bns: List[Bottleneck] = []
    if need_operator_mega:
        extra_megas.append(MegaTheme(
            mega_theme_id=OPERATOR_MEGA_THEME_ID,
            name="Operator-Accepted Universe",
            thesis=("Operator-defined themes for accepted tickers the base map does not know. "
                    "Membership only -- no fabricated value-chain / chokepoint analysis.")))
    for theme_id in scaffold_order:
        sid = scaffold_themes[theme_id]
        extra_themes.append(Theme(
            theme_id=sid, name=theme_id, mega_theme_ref=OPERATOR_MEGA_THEME_ID))
        vc_id = "vc:operator:{0}".format(sid)
        extra_chains.append(ValueChain(
            value_chain_id=vc_id, name=OPERATOR_MEMBERSHIP_LABEL, theme_ref=sid))
        extra_bns.append(Bottleneck(
            bottleneck_id="bn:operator:{0}".format(sid),
            name=OPERATOR_MEMBERSHIP_LABEL, value_chain_ref=vc_id,
            why_it_matters=OPERATOR_MEMBERSHIP_NOTE, is_chokepoint=False))

    # -- the Monitored Company Universe: EXACTLY the accepted tickers -- #
    companies = tuple(
        CompanyUniverseNode(
            ticker=ticker, company_name=ticker, role_label="beneficiary",
            linked_bottleneck_refs=tuple(links_by_ticker[ticker]))
        for ticker in ticker_order)
    accepted_set = set(ticker_order)

    # -- reuse the base MAP structure; only companies are replaced. Drop base dependencies whose
    #    endpoints are not both accepted (else a dangling ref); keep catalysts / risks / weak
    #    signals whose ref still resolves (a base ref to a dropped ticker is filtered out). -- #
    resolvable = (mega_ids | theme_ids | {sid for sid in scaffold_themes.values()}
                  | {v.value_chain_id for v in the_base.value_chains}
                  | {b.bottleneck_id for b in the_base.bottlenecks}
                  | {"bn:operator:{0}".format(sid) for sid in scaffold_themes.values()}
                  | {OPERATOR_MEGA_THEME_ID} | accepted_set)
    dependencies = tuple(
        d for d in the_base.dependencies
        if d.from_ticker in accepted_set and d.to_ticker in accepted_set)
    catalysts = tuple(c for c in the_base.catalysts if c.theme_or_company_ref in resolvable)
    risks = tuple(r for r in the_base.risks if r.theme_or_company_ref in resolvable)
    weak_signals = tuple(w for w in the_base.weak_signals if w.theme_or_company_ref in resolvable)

    return ThemeGraph(
        mega_themes=tuple(the_base.mega_themes) + tuple(extra_megas),
        themes=tuple(the_base.themes) + tuple(extra_themes),
        value_chains=tuple(the_base.value_chains) + tuple(extra_chains),
        bottlenecks=tuple(the_base.bottlenecks) + tuple(extra_bns),
        companies=companies,
        dependencies=dependencies,
        catalysts=catalysts,
        risks=risks,
        weak_signals=weak_signals)


def accepted_graph_provenance(store_dir: str) -> Dict[str, Dict[str, object]]:
    """A side-map of each accepted ticker's honest provenance (authority + real refs + themes).

    ``{TICKER: {"source_authority", "source_refs", "theme_ids", "theme_labels", "origins",
    "operator_defined_themes"}}`` -- carried ALONGSIDE :func:`build_accepted_theme_graph` because
    a :class:`~reality_mesh.theme_graph.CompanyUniverseNode` has no provenance field (it is a MAP
    node, not a claim). ``operator_defined_themes`` is True when ANY of the ticker's accepted
    themes is a scaffold theme the base map does not know (so the UI can flag the missing
    value-chain analysis). Highest authority wins (canonical > convenience > manual). Deterministic;
    offline; never fabricated.
    """
    base = build_seed_theme_graph()
    (mega_ids, theme_ids, themes_of_mega,
     chains_of_theme, bns_of_chain) = _base_lookups(base)
    _rank = {"canonical": 3, "convenience": 2, "manual": 1, "": 0}
    out: Dict[str, Dict[str, object]] = {}
    for entry in accepted_universe(store_dir):
        ticker = str(entry.ticker or "").strip().upper()
        theme_id = str(entry.theme_id or "").strip()
        if not ticker or not theme_id:
            continue
        rec = out.setdefault(ticker, {
            "source_authority": "", "source_refs": [], "theme_ids": [],
            "theme_labels": [], "origins": [], "operator_defined_themes": False})
        if _rank.get(entry.source_authority, 0) > _rank.get(str(rec["source_authority"]), 0):
            rec["source_authority"] = entry.source_authority
        for ref in entry.source_refs:
            if ref and ref not in rec["source_refs"]:
                rec["source_refs"].append(ref)
        if theme_id not in rec["theme_ids"]:
            rec["theme_ids"].append(theme_id)
        label = str(entry.theme_label or "").strip()
        if label and label not in rec["theme_labels"]:
            rec["theme_labels"].append(label)
        if entry.origin and entry.origin not in rec["origins"]:
            rec["origins"].append(entry.origin)
        if not _base_bottlenecks_for(theme_id, mega_ids, theme_ids, themes_of_mega,
                                     chains_of_theme, bns_of_chain):
            rec["operator_defined_themes"] = True
    for rec in out.values():
        rec["source_refs"] = tuple(rec["source_refs"])
        rec["theme_ids"] = tuple(rec["theme_ids"])
        rec["theme_labels"] = tuple(rec["theme_labels"])
        rec["origins"] = tuple(rec["origins"])
    return out


def run_lineage_on_accepted_universe(store_dir: str, *, run_id: str, now: str,
                                     persist: bool = False) -> DiligenceLineageResult:
    """Run the UNCHANGED diligence lineage over the DYNAMIC graph + the accepted watchlist (UD-4).

    A thin composition: calls :func:`~reality_mesh.diligence_lineage.run_diligence_lineage` with
    ``watchlist=`` :func:`accepted_watchlist` and ``graph=`` :func:`build_accepted_theme_graph`,
    over the persisted run ``run_id``. It passes the dynamic graph + accepted watchlist and changes
    NOTHING about the lineage's signature or behaviour: discovery still needs REAL corroborating
    evidence for a ``diligence_candidate``; an accepted, graph-connected ticker with no real pulse
    evidence stays ``blocked_insufficient_evidence`` / ``monitor_only``; nothing is forced to
    ``eligible`` (the slice-2 diligence + healthy-DQ gates still hold). No fixture-as-real.

    ``persist`` defaults to False (the read-only path the cockpit uses to render honest state);
    ``now`` is injected. Deterministic; offline. Raises ``ValueError`` on an empty / unknown run.
    """
    return run_diligence_lineage(
        store_dir,
        run_id=run_id,
        watchlist=accepted_watchlist(store_dir),
        now=now,
        graph=build_accepted_theme_graph(store_dir, now=now),
        persist=persist)
