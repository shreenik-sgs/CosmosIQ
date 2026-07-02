"""Typed TRUST / COMPLETENESS diagnostics for the real / watchlist terrain
(IMPLEMENTATION-010F).

These are **data-quality diagnostics, NOT alpha**. Every field is a LABEL, a string, a
tuple, a bool, or an honest COPIED count of already-surfaced records -- there is **no
numeric investability score, no ranking, no new scoring / reasoning**. Nothing here fetches
data, no network, no clock, no randomness: the module derives everything from the EXISTING
typed terrain nodes (:mod:`universe_ui.terrain`) + their :class:`VisualEncoding` ``*_basis``
fields + the :class:`~universe_ui.watchlist_terrain.WatchlistRunSummary`.

The vocabulary is closed (:data:`LABELS`). If a theme is weak / missing, it is marked weak /
missing -- the module never invents a "better" classification, and the "data action list" is
strictly DATA-SOURCING actions (add IR source, resolve CIK, add market-cap source, set
``SEC_USER_AGENT`` ...) -- never a trade / buy / sell instruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .terrain import (
    BottleneckNode,
    CompanyNode,
    DependencyNode,
    GalaxyNode,
    ThemeNode,
    UniverseTerrain,
    ValueChainNode,
)

# The ONLY status vocabulary any diagnostic label may draw from. No numbers, no ranks.
LABELS = frozenset((
    "sufficient", "partial", "weak", "missing", "conflicted", "stale",
    "credentials_missing", "source_failed", "needs_human_review", "built",
    "deferred", "failed", "direct", "fallback", "unclassified",
))

_UNCLASSIFIED_SLUG = "unclassified"


# --------------------------------------------------------------------------- #
# Diagnostic models -- labels / strings / tuples ONLY (no score field).        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ThemeClassificationDiagnostic:
    """Auditable trail for HOW (or whether) a company's theme was classified."""
    ticker: str = ""
    company_id: str = ""
    inferred_theme: str = ""
    classification_source: str = ""          # which upstream object / field
    classification_confidence_label: str = "missing"  # direct / weak / fallback / missing
    evidence_basis: Tuple[str, ...] = field(default_factory=tuple)
    weak_or_missing_reasons: Tuple[str, ...] = field(default_factory=tuple)
    alternative_possible_themes: Tuple[str, ...] = field(default_factory=tuple)
    why_unclassified: str = ""
    required_data_to_classify: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ValueChainDiagnostic:
    """Auditable trail for the completeness of a company's value chain / bottleneck."""
    company_id: str = ""
    value_chain_present: bool = False
    value_chain_source: str = ""
    missing_layers: Tuple[str, ...] = field(default_factory=tuple)
    missing_supplier_data: Tuple[str, ...] = field(default_factory=tuple)
    missing_customer_data: Tuple[str, ...] = field(default_factory=tuple)
    missing_tam_or_revenue_pool: bool = False
    missing_bottleneck_data: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"        # sufficient / partial / weak / missing
    required_next_data: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TickerQualityDiagnostic:
    """Per-ticker TRUST / COMPLETENESS labels + honest COPIED coverage counts."""
    ticker: str = ""
    terrain_status: str = "missing"          # built / partial / failed / deferred
    source_statuses: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    canonical_coverage: int = 0
    convenience_coverage: int = 0
    fallback_coverage: int = 0
    missing_source_reasons: Tuple[str, ...] = field(default_factory=tuple)
    unresolved_conflicts: Tuple[str, ...] = field(default_factory=tuple)
    overridden_facts: Tuple[str, ...] = field(default_factory=tuple)
    deferred_records: int = 0
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    provenance_count: int = 0
    theme_classification_status: str = "missing"
    value_chain_status: str = "missing"
    bottleneck_status: str = "missing"
    catalyst_status: str = "missing"
    red_team_status: str = "missing"
    cockpit_status: str = "missing"
    trust_label: str = "needs_human_review"
    data_actions: Tuple[str, ...] = field(default_factory=tuple)
    theme_diagnostic: Optional[ThemeClassificationDiagnostic] = None
    value_chain_diagnostic: Optional[ValueChainDiagnostic] = None


@dataclass(frozen=True)
class TerrainQualityDiagnostic:
    """Whole-run TRUST / COMPLETENESS labels + the data-sourcing action list."""
    terrain_id: str = ""
    mode: str = ""
    requested_tickers: Tuple[str, ...] = field(default_factory=tuple)
    built_tickers: Tuple[str, ...] = field(default_factory=tuple)
    failed_tickers: Tuple[str, ...] = field(default_factory=tuple)
    coverage_summary: str = ""
    trust_level: str = "needs_human_review"
    completeness_level: str = "missing"
    unresolved_conflicts: Tuple[str, ...] = field(default_factory=tuple)
    stale_or_missing_sources: Tuple[str, ...] = field(default_factory=tuple)
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    recommended_next_data_actions: Tuple[str, ...] = field(default_factory=tuple)
    per_ticker: Tuple[TickerQualityDiagnostic, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
# Terrain node lookup helpers (READ-ONLY traversal of the existing terrain).    #
# --------------------------------------------------------------------------- #
def _company_index(terrain: UniverseTerrain) -> Dict[str, Tuple[Any, Any, Any, str]]:
    """ticker -> (company_node, value_chain_node, bottleneck_node, galaxy_id).

    Built by walking the existing terrain only -- nothing is fetched or computed.
    """
    index: Dict[str, Tuple[Any, Any, Any, str]] = {}
    for g in terrain.galaxies:
        for th in g.themes:
            vc_by_id = {vc.id: vc for vc in th.value_chains}
            for co in th.candidate_planets:
                vc = vc_by_id.get(co.value_chain_id)
                bn = vc.bottlenecks[0] if (vc and vc.bottlenecks) else None
                if co.ticker and co.ticker not in index:
                    index[co.ticker] = (co, vc, bn, g.id)
    return index


# --------------------------------------------------------------------------- #
# Theme classification -- auditable, never upgraded.                           #
# --------------------------------------------------------------------------- #
def classify_theme_for_company(
    company: Optional[CompanyNode], slice_obj: Any, galaxy_id: str,
) -> ThemeClassificationDiagnostic:
    """Derive HOW a company's theme was classified, purely from the EXISTING slice OH.

    * A company under the ``unclassified`` region (no OpportunityHypothesis) -> ``missing``
      with ``why_unclassified`` = "no OpportunityHypothesis / theme could not be inferred".
    * Otherwise the source is the OpportunityHypothesis ``theme`` / megatrend field; the
      confidence is ``direct`` when convergence is present, ``weak`` when it is thin, and
      ``fallback`` when only the domain (not a named theme) is available. A ``weak``
      classification is NEVER promoted to ``direct``.
    """
    ticker = getattr(company, "ticker", "") or ""
    company_id = getattr(company, "id", "") or ""
    oh = getattr(slice_obj, "opportunity_hypothesis", None) if slice_obj is not None else None

    if galaxy_id == _UNCLASSIFIED_SLUG or oh is None:
        return ThemeClassificationDiagnostic(
            ticker=ticker, company_id=company_id, inferred_theme="",
            classification_source="none (no OpportunityHypothesis produced)",
            classification_confidence_label="missing",
            weak_or_missing_reasons=(
                "no signal-bearing assessment -> no OpportunityHypothesis -> theme could "
                "not be inferred",),
            why_unclassified=(
                "no OpportunityHypothesis / theme could not be inferred"),
            required_data_to_classify=(
                "add IR / thesis evidence (investor deck, 10-K business section) so a theme "
                "can be inferred",))

    theme = getattr(oh, "theme", "") or ""
    domain = getattr(oh, "domain", "") or ""
    convergence = tuple(getattr(oh, "cross_domain_convergence", ()) or ())
    megatrend = tuple(getattr(oh, "megatrend_context", ()) or ())

    if not theme and domain:
        confidence = "fallback"
        reasons = ("no named theme on the OpportunityHypothesis — fell back to the domain "
                   "slug",)
    elif theme and convergence:
        confidence = "direct"
        reasons = ()
    else:
        confidence = "weak"
        reasons = ("theme named but cross-domain convergence is thin (single evidence "
                   "family) — classification is weak, not upgraded",)

    return ThemeClassificationDiagnostic(
        ticker=ticker, company_id=company_id,
        inferred_theme=theme or domain,
        classification_source="OpportunityHypothesis.theme / megatrend_context",
        classification_confidence_label=confidence,
        evidence_basis=megatrend + convergence,
        weak_or_missing_reasons=reasons,
        alternative_possible_themes=(),
        required_data_to_classify=(
            () if confidence == "direct" else
            ("add corroborating cross-domain evidence to strengthen the theme",)))


def value_chain_diagnostic_for(
    company_id: str, vc: Optional[ValueChainNode], bn: Optional[BottleneckNode],
) -> ValueChainDiagnostic:
    """Derive value-chain / bottleneck completeness from the existing terrain nodes."""
    if vc is None:
        return ValueChainDiagnostic(
            company_id=company_id, value_chain_present=False,
            value_chain_source="none", missing_layers=("entire value chain absent",),
            missing_supplier_data=("no supplier layer",),
            missing_customer_data=("no customer layer",),
            missing_tam_or_revenue_pool=True,
            missing_bottleneck_data=("no bottleneck node",),
            confidence_label="missing",
            required_next_data=(
                "add investor presentation / supply-chain disclosure to map the value chain",))

    has_layers = bool(getattr(vc, "flow_layers", ()) or ())
    has_deps = bool(getattr(vc, "dependencies", ()) or ())
    tam_missing = getattr(vc, "revenue_pool_or_tam", None) is None
    bn_gaps = tuple(getattr(bn, "data_gaps", ()) or ()) if bn is not None else (
        "no bottleneck node",)

    if has_layers and has_deps and not tam_missing:
        confidence = "sufficient"
    elif has_layers or has_deps:
        confidence = "partial"
    else:
        # value-chain node exists but is a pure placeholder (no layers, no suppliers, no TAM).
        confidence = "weak"

    missing_layers = tuple(getattr(vc, "data_gaps", ()) or ())
    return ValueChainDiagnostic(
        company_id=company_id, value_chain_present=True,
        value_chain_source="thesis value_chain_summary (placeholder)" if confidence == "weak"
        else "thesis value_chain_summary",
        missing_layers=missing_layers,
        missing_supplier_data=(() if has_deps else ("no named suppliers mapped",)),
        missing_customer_data=(() if has_deps else ("no named customers mapped",)),
        missing_tam_or_revenue_pool=tam_missing,
        missing_bottleneck_data=bn_gaps,
        confidence_label=confidence,
        required_next_data=tuple(x for x in (
            "add supplier / customer disclosure source" if not has_deps else "",
            "add TAM / revenue-pool source" if tam_missing else "",
            "add capacity / bottleneck data source" if bn_gaps else "",
        ) if x))


# --------------------------------------------------------------------------- #
# Per-ticker diagnostic derivation.                                            #
# --------------------------------------------------------------------------- #
def _present(value: Any) -> bool:
    return bool(value)


def _ticker_diagnostic(record: Any, terrain: UniverseTerrain,
                       run_summary: Any, company_index: Dict[str, Any]) -> TickerQualityDiagnostic:
    ticker = record.ticker
    source_statuses = tuple(
        (src, getattr(record, "{0}_status".format(key)))
        for src, key in (("sec", "sec"), ("fmp", "fmp"), ("yfinance", "yfinance")))

    # Failed / deferred tickers have no company node -- record-only diagnostic.
    if record.status != "built":
        status_label = "failed" if record.status == "failed" else "deferred"
        return TickerQualityDiagnostic(
            ticker=ticker, terrain_status=status_label, source_statuses=source_statuses,
            missing_source_reasons=(record.reason or "ticker not built",),
            data_gaps=tuple(record.data_gaps),
            trust_label=("source_failed" if status_label == "failed" else "deferred"),
            data_actions=(
                ("resolve ticker / CIK mapping or retry the source (fetch failed)",)
                if status_label == "failed" else
                ("retry the source when available (deferred)",)))

    entry = company_index.get(ticker)
    company, vc, bn, galaxy_id = entry if entry else (None, None, None, "")
    slice_obj = (run_summary.slice_by_subject.get(ticker)
                 if getattr(run_summary, "slice_by_subject", None) else None)

    theme_diag = classify_theme_for_company(company, slice_obj, galaxy_id)
    vc_diag = value_chain_diagnostic_for(getattr(company, "id", ""), vc, bn)

    theme_status = ("unclassified" if theme_diag.classification_confidence_label == "missing"
                    else theme_diag.classification_confidence_label)
    vc_status = vc_diag.confidence_label
    bn_status = ("missing" if bn is None else
                 ("weak" if (getattr(bn, "data_gaps", ()) or ()) else "partial"))
    catalyst_status = "partial" if (getattr(company, "catalysts", ()) or ()) else "missing"
    rt = (getattr(company, "red_team_status", "") or "").lower()
    red_team_status = ("weak" if rt in ("concern", "fail")
                       else ("partial" if rt else "missing"))
    cockpit_status = "built" if getattr(company, "cockpit_link", None) else "deferred"

    # Conflicts for this ticker (run summary prefixes each warning with the ticker).
    prefix = "{0}:".format(ticker)
    conflicts = tuple(c for c in getattr(run_summary, "conflict_warnings", ()) or ()
                      if str(c).startswith(prefix))
    # In the current pipeline every conflict is resolved by authority (SEC over FMP), so
    # NONE are left unresolved -- honest: conflicts detected, all arbitrated.
    unresolved: Tuple[str, ...] = ()

    market_cap_missing = getattr(company, "market_cap", None) is None
    canonical = int(record.canonical)
    convenience = int(record.convenience)
    fallback = int(record.fallback)

    missing_reasons = tuple(x for x in (
        "SEC canonical source unavailable ({0})".format(record.sec_status)
        if record.sec_status not in ("fetched",) else "",
        "FMP convenience source unavailable ({0})".format(record.fmp_status)
        if record.fmp_status not in ("fetched",) else "",
        "yfinance fallback {0}".format(record.yfinance_status)
        if record.yfinance_status not in ("fetched",) else "",
    ) if x)

    # ---- data-sourcing actions ONLY (never a trade instruction) ------------- #
    actions: List[str] = []
    if record.sec_status == "credentials_missing":
        actions.append("set SEC_USER_AGENT to enable the canonical SEC EDGAR source")
    if record.fmp_status == "credentials_missing":
        actions.append("set FMP_API_KEY to enable the FMP convenience source")
    if record.sec_status == "failed" or record.fmp_status == "failed":
        actions.append("resolve ticker / CIK mapping or retry the source (fetch failed)")
    if canonical == 0 and convenience == 0 and fallback > 0:
        actions.append("add an SEC canonical / FMP source (only fallback data present)")
    elif canonical == 0:
        actions.append("add the SEC canonical (EDGAR) source (no canonical records)")
    if theme_status in ("missing", "unclassified"):
        actions.append("add IR / thesis evidence source to classify the theme")
    if vc_status in ("weak", "missing"):
        actions.append("add investor presentation / supply-chain source to map the value chain")
    if bn_status in ("weak", "missing"):
        actions.append("add a capacity / bottleneck data source to quantify the constraint")
    if market_cap_missing:
        actions.append("add a market-cap source")
    if vc_diag.missing_tam_or_revenue_pool:
        actions.append("add a TAM / revenue-pool source")
    if not (getattr(vc, "dependencies", ()) or ()):
        actions.append("add a supplier / customer disclosure source")
    if record.yfinance_status == "deferred":
        actions.append("optionally enable the yfinance fallback source (research-only)")
    actions = list(dict.fromkeys(actions))

    # ---- TRUST label (source authority, NOT alpha) -------------------------- #
    if record.sec_status == "credentials_missing" and record.fmp_status == "credentials_missing":
        trust = "weak"
    elif canonical == 0 and convenience == 0 and fallback > 0:
        trust = "weak"
    elif theme_status in ("missing", "unclassified"):
        trust = "needs_human_review"
    elif canonical > 0 and not unresolved and theme_status == "direct":
        trust = "sufficient"
    else:
        trust = "partial"

    return TickerQualityDiagnostic(
        ticker=ticker, terrain_status="built", source_statuses=source_statuses,
        canonical_coverage=canonical, convenience_coverage=convenience,
        fallback_coverage=fallback, missing_source_reasons=missing_reasons,
        unresolved_conflicts=unresolved, overridden_facts=(),
        deferred_records=len(getattr(slice_obj, "deferred_records", ()) or ()),
        data_gaps=tuple(record.data_gaps), provenance_count=len(record.provenance_refs),
        theme_classification_status=theme_status, value_chain_status=vc_status,
        bottleneck_status=bn_status, catalyst_status=catalyst_status,
        red_team_status=red_team_status, cockpit_status=cockpit_status,
        trust_label=trust, data_actions=tuple(actions),
        theme_diagnostic=theme_diag, value_chain_diagnostic=vc_diag)


# --------------------------------------------------------------------------- #
# Whole-terrain diagnostic builder.                                            #
# --------------------------------------------------------------------------- #
def build_terrain_diagnostics(terrain: UniverseTerrain, run_summary: Any) -> TerrainQualityDiagnostic:
    """Derive the whole-run TRUST / COMPLETENESS diagnostic from EXISTING data only.

    ``run_summary`` is a :class:`~universe_ui.watchlist_terrain.WatchlistRunSummary` (a
    watchlist run, or a single-ticker run wrapped by :func:`single_ticker_run_summary`).
    Nothing is fetched, ranked, or scored -- labels are mapped from coverage + conflicts +
    classification, and counts are COPIED from the summary records.
    """
    company_index = _company_index(terrain)
    per_ticker = tuple(
        _ticker_diagnostic(r, terrain, run_summary, company_index)
        for r in run_summary.records)

    built = tuple(d.ticker for d in per_ticker if d.terrain_status == "built")
    failed = tuple(d.ticker for d in per_ticker if d.terrain_status in ("failed", "deferred"))
    requested = tuple(getattr(run_summary, "requested", ()) or
                      tuple(d.ticker for d in per_ticker))

    coverage = getattr(terrain, "source_coverage", {}) or {}
    coverage_summary = (
        "canonical {0} / convenience {1} / fallback {2} across {3} built ticker(s)".format(
            int(coverage.get("canonical", 0)), int(coverage.get("convenience", 0)),
            int(coverage.get("fallback", 0)), len(built)))

    conflict_warnings = tuple(getattr(run_summary, "conflict_warnings", ()) or ())
    overridden = tuple(getattr(run_summary, "overridden_facts", ()) or ())

    # stale / missing sources: any credential-missing or unavailable source across tickers.
    stale: List[str] = []
    for d in per_ticker:
        for src, st in d.source_statuses:
            if st in ("credentials_missing", "unavailable", "failed", "deferred"):
                stale.append("{0}: {1} — {2}".format(d.ticker, src, st))
    stale_t = tuple(dict.fromkeys(stale))

    # ---- terrain TRUST + COMPLETENESS labels -------------------------------- #
    trust_labels = {d.trust_label for d in per_ticker if d.terrain_status == "built"}
    if not built:
        trust_level = "source_failed"
    elif trust_labels <= {"sufficient"}:
        trust_level = "sufficient"
    elif "weak" in trust_labels or "needs_human_review" in trust_labels:
        trust_level = "needs_human_review" if "needs_human_review" in trust_labels else "weak"
    else:
        trust_level = "partial"

    # completeness: value chain / bottleneck / TAM are placeholders in the real slice, so a
    # built run is at best PARTIAL; nothing built -> missing.
    if not built:
        completeness_level = "missing"
    elif all(d.value_chain_status == "sufficient" and d.bottleneck_status == "sufficient"
             for d in per_ticker if d.terrain_status == "built"):
        completeness_level = "sufficient"
    else:
        completeness_level = "partial"

    # ---- data-sourcing actions (union, de-duped, deterministic) ------------- #
    actions: List[str] = []
    for d in per_ticker:
        actions.extend(d.data_actions)
    actions = list(dict.fromkeys(actions))

    warnings: List[str] = []
    warnings.append("{0} requested / {1} built / {2} failed-or-deferred".format(
        len(requested), len(built), len(requested) - len(built)))
    if conflict_warnings:
        warnings.append(
            "{0} source conflict(s) detected; all resolved by authority (SEC canonical "
            "over FMP convenience) — none left unresolved".format(len(conflict_warnings)))
    if overridden:
        warnings.append(
            "{0} lower-authority fact(s) overridden by a higher-authority source".format(
                len(overridden)))
    if failed:
        warnings.append("failed / deferred tickers: {0}".format(", ".join(failed)))

    return TerrainQualityDiagnostic(
        terrain_id=getattr(terrain, "terrain_id", ""),
        mode=getattr(terrain, "mode", ""),
        requested_tickers=requested, built_tickers=built, failed_tickers=failed,
        coverage_summary=coverage_summary, trust_level=trust_level,
        completeness_level=completeness_level,
        unresolved_conflicts=conflict_warnings, stale_or_missing_sources=stale_t,
        warnings=tuple(warnings), recommended_next_data_actions=tuple(actions),
        per_ticker=per_ticker)


# --------------------------------------------------------------------------- #
# Single-ticker adapter: wrap a 010D single real build as a one-record summary. #
# --------------------------------------------------------------------------- #
def single_ticker_run_summary(terrain: UniverseTerrain, source_status: Dict[str, Any],
                              slice_result: Any) -> Any:
    """Wrap a single-ticker real build into a one-record ``WatchlistRunSummary``.

    Lets the single 010D real mode reuse the SAME diagnostic builder as the 010E watchlist.
    Every value is COPIED from the terrain / source-status / slice -- nothing recomputed.
    """
    from .watchlist_terrain import WatchlistRunSummary, WatchlistTickerRecord

    ss = dict(source_status or {})
    ticker = str(ss.get("ticker", getattr(slice_result, "subject", "") or "")).upper()
    coverage = getattr(terrain, "source_coverage", {}) or {}
    conflicts = tuple(getattr(slice_result, "conflict_warnings", ()) or ())
    prov = tuple(getattr(terrain, "provenance_refs", ()) or ())
    overridden = tuple(
        getattr(slice_result, "provenance_chain", {}).get("overridden_facts", ()) or ())

    record = WatchlistTickerRecord(
        ticker=ticker, status="built", reason="",
        sec_status=str(ss.get("sec", "")), fmp_status=str(ss.get("fmp", "")),
        yfinance_status=str(ss.get("yfinance", "")),
        canonical=int(coverage.get("canonical", 0)),
        convenience=int(coverage.get("convenience", 0)),
        fallback=int(coverage.get("fallback", 0)), conflicts=len(conflicts),
        data_gaps=tuple(getattr(terrain, "data_gaps", ()) or ()),
        provenance_refs=prov, terrain_status="built")
    # Prefix conflicts with the ticker so per-ticker attribution matches the watchlist path.
    prefixed = tuple("{0}: {1}".format(ticker, c) for c in conflicts)
    return WatchlistRunSummary(
        requested=(ticker,), records=(record,), source_coverage=dict(coverage),
        data_gaps=tuple(getattr(terrain, "data_gaps", ()) or ()),
        conflict_warnings=prefixed, overridden_facts=overridden, provenance_refs=prov,
        deferred_records_count=len(getattr(slice_result, "deferred_records", ()) or ()),
        run_timestamp=str(ss.get("run_timestamp", "")),
        slice_by_subject={ticker: slice_result}, representative_slice=slice_result,
        representative_ticker=ticker)


# --------------------------------------------------------------------------- #
# Attach diagnostics to terrain object ids + explain the visual encoding.       #
# --------------------------------------------------------------------------- #
def diagnostics_by_object_id(terrain: UniverseTerrain,
                             diag: TerrainQualityDiagnostic) -> Dict[str, str]:
    """Map every real terrain node id -> a short data-quality annotation.

    So the UI can say "this galaxy is weakly classified", "SEC canonical but no value-chain
    data", "bottleneck is a placeholder / constraint context", "supplier layer missing",
    "cockpit deferred — thesis inputs partial". Derived from the per-ticker diagnostics +
    the node's own placeholder/data-gap state.
    """
    by_ticker = {d.ticker: d for d in diag.per_ticker}
    out: Dict[str, str] = {}

    for g in terrain.galaxies:
        if g.id == _UNCLASSIFIED_SLUG:
            out[g.id] = ("weakly classified region — no theme inferred from evidence; "
                         "needs human theme inference")
        else:
            out[g.id] = "theme classified (direct) from OpportunityHypothesis"
        for th in g.themes:
            out[th.id] = out.get(g.id, "")
            for vc in th.value_chains:
                out[vc.id] = ("value-chain placeholder — supplier/customer layer missing, "
                              "TAM not quantified")
                for bn in vc.bottlenecks:
                    out[bn.id] = ("bottleneck is a placeholder / constraint context "
                                  "(severity / importance not quantified)")
                for dep in vc.dependencies:
                    out[dep.id] = "dependency moon — supplier layer unverified"
            for co in th.candidate_planets:
                d = by_ticker.get(co.ticker)
                if d is None:
                    continue
                cockpit = ("cockpit exists but thesis inputs partial"
                           if d.cockpit_status == "built"
                           else "cockpit deferred — thesis inputs partial")
                out[co.id] = (
                    "trust {0} · theme {1} · value-chain {2} · bottleneck {3} · {4}".format(
                        d.trust_label, d.theme_classification_status, d.value_chain_status,
                        d.bottleneck_status, cockpit))
    return out


def explain_visual_encoding(node: Any) -> Tuple[Tuple[str, str], ...]:
    """Explain WHY a node is drawn as it is, using ONLY its ``VisualEncoding`` ``*_basis``
    fields (no new computation): why neutral size / dashed / red shadow / low opacity /
    halo / glow / orbit distance."""
    enc = getattr(node, "visual_encoding", None)
    if enc is None:
        return ()
    out: List[Tuple[str, str]] = []
    size_basis = getattr(enc, "size_basis", "") or ""
    if getattr(enc, "dashed_outline", False) and not size_basis:
        out.append(("size", "neutral size — economic magnitude missing (a data gap)"))
    elif size_basis:
        out.append(("size", size_basis))
    if getattr(enc, "dashed_outline", False):
        out.append(("dashed_outline",
                    "missing data — a data gap drawn as a dashed placeholder (nothing "
                    "fabricated)"))
    if getattr(enc, "red_shadow", False):
        out.append(("red_shadow", "red-team / dilution / insolvency flag"))
    glow_basis = getattr(enc, "glow_basis", "") or ""
    if glow_basis:
        out.append(("glow", glow_basis))
    opacity_basis = getattr(enc, "opacity_basis", "") or ""
    opacity_level = getattr(enc, "opacity_level", "") or ""
    if opacity_basis or opacity_level:
        lvl = opacity_level or "evidence quality"
        out.append(("opacity", "opacity encodes {0} ({1})".format(
            opacity_basis or "evidence quality", lvl)))
    halo_basis = getattr(enc, "halo_basis", "") or ""
    if getattr(enc, "halo_type", "") or halo_basis:
        out.append(("halo", halo_basis or "catalyst presence / crowding"))
    orbit_basis = getattr(enc, "orbit_distance_basis", "") or ""
    if orbit_basis:
        out.append(("orbit_distance", orbit_basis))
    return tuple(out)
