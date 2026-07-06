"""The Candidate Discovery Engine for the Reality Mesh (IMPLEMENTATION-021E).

Turns the Theme Graph (021D-graph) + the persisted live-source evidence into a set of
:class:`DiscoveryCandidate`s -- companies flagged as **WORTHY OF DILIGENCE**. A
``DiscoveryCandidate`` is emphatically **NOT a recommendation, NOT a buy, and NOT a stock pick**:
it means only "this company may be worth diligence because it is connected to a theme / value
chain / bottleneck / catalyst / signal cluster, AND some real (non-social) evidence corroborates
looking closer." Nothing here confers capital standing:

* **Graph membership ALONE, an SEC filing ALONE, or an FMP row ALONE never creates a
  CapitalCandidate or a recommendation.** A ``DiscoveryCandidate`` at most FLAGS "worth
  diligence"; becoming a :class:`~reality_mesh.capital_candidate.CapitalCandidate` STILL requires
  the full 020A publish path (source provenance + fused ``RealitySignal`` refs + an
  ``OpportunityHypothesis`` + an ``InvestmentDiligence`` thesis + a healthy DQ gate). Discovery
  may TRIGGER a diligence INPUT (:func:`trigger_diligence_input`) but it NEVER auto-publishes --
  publication is exclusively :func:`~reality_mesh.capital_candidate.publish_candidates_for_run`.

* **NO score / rank / rating.** The output is a CLOSED categorical ``discovery_state`` +
  labelled PRESENCE ``factor_flags`` (a flag is a label that was PRESENT, never a number) +
  plain-English ``reasons`` + refs. There is NO numeric ranking, NO hidden score, and NO
  buy / sell / order / submit field or affordance anywhere (``assert_no_trade_fields``-clean).

* **Honesty over volume.** A social / rumor-only basis (or a DQ-failed run) can NEVER reach
  ``diligence_candidate`` -- it stays ``monitor_only`` or a ``blocked_*`` state. Absent evidence
  is a labelled ``data_gap`` flag, never an invented factor. Deterministic (injected ``now`` +
  a content-derived id), stdlib-only, Python 3.9, OFFLINE. No network / scheduler / broker; no
  wall-clock.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import labels as _labels
from .sensors.financial_inflection import FINANCIAL_INFLECTION_FILING_EVENT_TYPES
from .theme_graph import ThemeGraph
from .validation import assert_no_trade_fields

__all__ = [
    "DISCOVERY_STATES",
    "BLOCKED_DISCOVERY_STATES",
    "FACTOR_FLAGS",
    "DISCOVERY_MODELS",
    "DiscoveryCandidate",
    "discover_candidates",
    "trigger_diligence_input",
    "discovery_id_for",
]


# --------------------------------------------------------------------------- #
# Closed vocabularies                                                           #
# --------------------------------------------------------------------------- #

# The candidate's categorical state -- a CLOSED verdict about diligence-worthiness, never a
# score. ``diligence_candidate`` is the only state that says "worth diligence"; it is reachable
# ONLY from a graph connection PLUS real (non-social) corroborating evidence on a non-failed run
# with no dominating risk. Every other state is either "watch" (``monitor_only``) or a labelled
# block WITH an exact reason.
DISCOVERY_STATES: Tuple[str, ...] = (
    "monitor_only",
    "diligence_candidate",
    "blocked_insufficient_evidence",
    "blocked_dq_failed",
    "blocked_risk_too_high",
)

# The three blocked verdicts (every ``blocked_*`` state), for callers.
BLOCKED_DISCOVERY_STATES: Tuple[str, ...] = tuple(
    s for s in DISCOVERY_STATES if s.startswith("blocked_"))

# The closed PRESENCE-flag vocabulary. Each flag is a LABEL recording that a factor was PRESENT
# in the graph connection + the persisted evidence -- it is NEVER a number, weight, or rank. An
# ABSENT factor is simply not in the tuple (and, where relevant, surfaced as ``data_gap``).
FACTOR_FLAGS: Tuple[str, ...] = (
    "theme_relevant",              # the company is a graph node resolving to a theme (bare membership)
    "bottleneck_exposed",          # the company is linked to a bottleneck / chokepoint on the map
    "financial_inflection_hint",   # a 021B financial-inflection finding / SEC financial filing
    "revenue_acceleration",        # a revenue-acceleration inflection finding
    "margin_expansion",            # a margin-expansion (improving) inflection finding
    "capex_capacity_signal",       # a capex / capacity-expansion inflection
    "customer_contract_signal",    # a customer-evidence / material-agreement filing signal
    "dilution_liquidity_risk",     # a dilution / shelf-offering inflection (a RISK factor)
    "valuation_stretch",           # an explicit valuation-stretch read (a RISK factor)
    "technical_setup_available",   # a technical-regime setup finding / signal exists
    "red_team_risk",               # an applicable red-team / thesis-hazard risk node
    "data_gap",                    # evidence is thin / missing -- an explicit gap, never invented
)

# Producing-run DQ states a candidate may carry (a subset of RUN_STATUSES). ``blocked_by_policy``
# maps to ``failed``; anything unrecognised is an honestly-unstated ("") DQ.
_TRUST_DQ_STATES: Tuple[str, ...] = ("healthy", "degraded", "failed")

# Real (non-social) source-authority-summary values that mark thin, weak corroboration.
_SOCIAL_AUTHORITIES = frozenset({"rumor"})

# SEC filing event types that read as a DILUTION / liquidity-structure factor (from 021B).
_DILUTION_EVENT_TYPES = frozenset(
    et for et, (_sub, ftype) in FINANCIAL_INFLECTION_FILING_EVENT_TYPES.items()
    if ftype == "dilution_inflection")


def _require_id(obj, name: str) -> None:
    value = getattr(obj, name, "")
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(
            "{0}.{1} is a required id and must be non-empty".format(type(obj).__name__, name))


# --------------------------------------------------------------------------- #
# The typed contract                                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DiscoveryCandidate:
    """A frozen "worth-diligence?" verdict for one monitored ticker under one discovery run.

    It carries a CLOSED ``discovery_state``, a tuple of PRESENT ``factor_flags`` (labels, never
    numbers), plain-English ``reasons``, the graph connections it rests on, and its evidence
    refs. There is NO numeric score / rank / rating field and NO buy / sell / order / submit
    field anywhere (``assert_no_trade_fields``-clean). It is NOT a recommendation and confers NO
    capital standing -- a :class:`~reality_mesh.capital_candidate.CapitalCandidate` is created
    ONLY by the 020A publish path, and this object is not part of that lineage.
    """

    discovery_id: str = ""                  # REQUIRED, deterministic (run + ticker derived)
    run_id: str = ""                        # REQUIRED -- the discovery run that produced it
    generated_at: str = ""                  # injected timestamp (no wall-clock)
    ticker: str = ""                        # REQUIRED
    theme_refs: Tuple[str, ...] = field(default_factory=tuple)      # graph theme connections
    bottleneck_refs: Tuple[str, ...] = field(default_factory=tuple)  # graph bottleneck connections
    discovery_state: str = "monitor_only"   # closed: DISCOVERY_STATES
    factor_flags: Tuple[str, ...] = field(default_factory=tuple)     # closed PRESENCE flags
    reasons: Tuple[str, ...] = field(default_factory=tuple)          # plain-English
    trust_data_quality_state: str = ""      # the producing run's DQ ("" = unstated)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)      # evidence / source refs
    basis: str = ""                         # plain-English lineage citing the refs

    def __post_init__(self) -> None:
        for name in ("discovery_id", "run_id", "ticker"):
            _require_id(self, name)
        if self.discovery_state not in DISCOVERY_STATES:
            raise ValueError(
                "DiscoveryCandidate.discovery_state {0!r} invalid (allowed: {1})".format(
                    self.discovery_state, list(DISCOVERY_STATES)))
        for flag in self.factor_flags:
            if flag not in FACTOR_FLAGS:
                raise ValueError(
                    "DiscoveryCandidate.factor_flags: invalid flag {0!r} (allowed: {1})".format(
                        flag, list(FACTOR_FLAGS)))
        if self.trust_data_quality_state and self.trust_data_quality_state not in _TRUST_DQ_STATES:
            raise ValueError(
                "DiscoveryCandidate.trust_data_quality_state {0!r} invalid (allowed: {1})".format(
                    self.trust_data_quality_state, list(_TRUST_DQ_STATES)))

    @property
    def is_diligence_candidate(self) -> bool:
        return self.discovery_state == "diligence_candidate"

    @property
    def is_blocked(self) -> bool:
        return self.discovery_state in BLOCKED_DISCOVERY_STATES


# The contract (for registry / test introspection). Trade/score-clean.
DISCOVERY_MODELS = (DiscoveryCandidate,)


# --------------------------------------------------------------------------- #
# Deterministic id                                                              #
# --------------------------------------------------------------------------- #
def discovery_id_for(run_id: str, ticker: str) -> str:
    """A deterministic discovery id from the run + ticker (no wall-clock, order-stable)."""
    return "disc:{0}:{1}".format(str(run_id or "").strip(), str(ticker or "").strip().upper())


def _normalize_dq(dq_state: str) -> str:
    """Map a raw run DQ onto the trust-DQ subset (``blocked_by_policy`` -> ``failed``)."""
    raw = str(dq_state or "").strip()
    if raw in _TRUST_DQ_STATES:
        return raw
    if raw == "blocked_by_policy":
        return "failed"
    return ""


# --------------------------------------------------------------------------- #
# Graph-connection + evidence introspection (pure, deterministic)               #
# --------------------------------------------------------------------------- #
def _theme_refs_for(graph: ThemeGraph, bottleneck_refs: Tuple[str, ...]) -> Tuple[str, ...]:
    """The distinct theme ids a company's linked bottlenecks resolve to (order-stable)."""
    chain_of = {b.bottleneck_id: b.value_chain_ref for b in graph.bottlenecks}
    theme_of = {v.value_chain_id: v.theme_ref for v in graph.value_chains}
    themes: List[str] = []
    for bref in bottleneck_refs:
        chain = chain_of.get(bref, "")
        theme = theme_of.get(chain, "")
        if theme and theme not in themes:
            themes.append(theme)
    return tuple(themes)


def _is_social_input(item) -> bool:
    """True iff an event / finding / signal is X/social / rumor-tier (never real corroboration)."""
    discipline = str(getattr(item, "discipline", "") or "")
    source_type = str(getattr(item, "source_type", "") or "")
    authority = str(getattr(item, "source_authority", "")
                    or getattr(item, "source_authority_summary", "") or "")
    claim = str(getattr(item, "claim_status", "") or "")
    if _labels.is_social_source(source_type=source_type, discipline=discipline):
        return True
    if source_type and _labels.is_social_source_type(source_type):
        return True
    return authority in _SOCIAL_AUTHORITIES or claim == "rumor"


def _for_ticker(items, ticker: str):
    """The subset of items whose ``affected_companies`` include ``ticker`` (order-stable)."""
    return tuple(i for i in items if ticker in tuple(getattr(i, "affected_companies", ()) or ()))


def _refs_of(item) -> Tuple[str, ...]:
    src = tuple(getattr(item, "source_refs", ()) or ())
    ev = tuple(getattr(item, "evidence_refs", ()) or ())
    return src + ev


def _applicable_risks(ticker, theme_refs, bottleneck_refs, graph, risk_nodes):
    """Every risk node (graph + injected) that attaches to this ticker / its themes / bottlenecks."""
    scope = {ticker} | set(theme_refs) | set(bottleneck_refs)
    out = []
    for r in tuple(graph.risks) + tuple(risk_nodes or ()):
        if str(getattr(r, "theme_or_company_ref", "") or "") in scope:
            out.append(r)
    return out


def _factor_flags_and_refs(
    graph, ticker, node, theme_refs, bottleneck_refs,
    events, findings, signals, risks,
) -> Tuple[List[str], List[str], List[str], bool, bool]:
    """Compute the PRESENT factor flags + refs + reasons for one ticker. Never fabricates a flag.

    Returns ``(flags, source_refs, reasons, has_real_corroboration, has_social_input)``.
    """
    flags: List[str] = []
    reasons: List[str] = []
    refs: List[str] = []

    # -- graph-connection flags (bare membership -- NEVER enough on their own) -- #
    if node is not None and theme_refs:
        flags.append("theme_relevant")
        reasons.append(
            "connected on the Theme Graph to theme(s) {0} (bare map membership -- an input, "
            "not a recommendation)".format(", ".join(theme_refs)))
    if node is not None and bottleneck_refs:
        flags.append("bottleneck_exposed")
        reasons.append(
            "mapped to bottleneck(s) {0} in the value chain".format(", ".join(bottleneck_refs)))

    # -- split the ticker's evidence into real (non-social) vs social/rumor -- #
    social_items = [i for i in (list(events) + list(findings) + list(signals))
                    if _is_social_input(i)]
    real_events = [e for e in events if not _is_social_input(e)]
    real_findings = [f for f in findings if not _is_social_input(f)]
    real_signals = [s for s in signals if not _is_social_input(s)]
    real_items = real_events + real_findings + real_signals

    for item in real_items:
        refs.extend(_refs_of(item))

    fin_types = {str(getattr(f, "finding_type", "") or ""): f for f in real_findings}
    fin_disciplines = {str(getattr(f, "discipline", "") or "") for f in real_findings}
    sig_disciplines = {str(getattr(s, "discipline", "") or "") for s in real_signals}
    event_types = {str(getattr(e, "event_type", "") or "") for e in real_events}
    event_disciplines = {str(getattr(e, "discipline", "") or "") for e in real_events}

    def _any_finding(ftype, direction=None) -> bool:
        for f in real_findings:
            if str(getattr(f, "finding_type", "") or "") != ftype:
                continue
            if direction is not None and str(getattr(f, "direction_label", "") or "") != direction:
                continue
            return True
        return False

    sec_financial = any(et in FINANCIAL_INFLECTION_FILING_EVENT_TYPES for et in event_types)
    if ("financial_inflection" in fin_disciplines
            or "financial_inflection" in event_disciplines or sec_financial):
        flags.append("financial_inflection_hint")
        reasons.append("a financial-inflection hint is present from real (non-social) evidence")
    if _any_finding("revenue_acceleration"):
        flags.append("revenue_acceleration")
        reasons.append("revenue-acceleration inflection observed")
    if _any_finding("margin_inflection", direction="improving"):
        flags.append("margin_expansion")
        reasons.append("margin-expansion inflection observed")
    if _any_finding("capex_inflection") or any("capex" in et for et in event_types):
        flags.append("capex_capacity_signal")
        reasons.append("capex / capacity-expansion signal observed")
    if "customer_evidence" in fin_disciplines or any(
            ("material_agreement" in et or "contract" in et) for et in event_types):
        flags.append("customer_contract_signal")
        reasons.append("customer / material-agreement contract signal observed")
    if _any_finding("dilution_inflection") or any(et in _DILUTION_EVENT_TYPES for et in event_types):
        flags.append("dilution_liquidity_risk")
        reasons.append("dilution / shelf-offering (liquidity-structure) risk factor present")
    if _any_finding("valuation_stretch") or any("valuation" in et for et in event_types):
        flags.append("valuation_stretch")
        reasons.append("an explicit valuation-stretch read is present")
    if "technical_regime" in fin_disciplines or "technical_regime" in sig_disciplines:
        flags.append("technical_setup_available")
        reasons.append("a technical-regime setup finding / signal is available")

    # -- red-team risk (a labelled hazard, never a rank) -- #
    red_team = [r for r in risks
                if str(getattr(r, "severity_label", "") or "") in ("major", "severe")]
    if red_team:
        flags.append("red_team_risk")
        reasons.append("red-team hazard(s) present: {0}".format(
            "; ".join(sorted(str(getattr(r, "risk_id", "") or "") for r in red_team))))

    # -- social / rumor evidence is SURFACED but never counted as corroboration -- #
    for item in social_items:
        refs.extend(_refs_of(item))
    if social_items and not real_items:
        reasons.append(
            "only social / rumor-tier evidence is present -- monitored, never promoted to a "
            "diligence candidate")

    # -- data-gap flag: thin / missing evidence, or an explicit gap on any input -- #
    inherited_gaps = []
    for item in list(events) + list(findings) + list(signals):
        inherited_gaps.extend(tuple(getattr(item, "data_gaps", ()) or ()))
    has_real = bool(real_items)
    if inherited_gaps or not has_real:
        flags.append("data_gap")
        if not has_real:
            reasons.append(
                "no real (non-social) corroborating evidence beyond bare graph membership -- "
                "an explicit gap, never a fabricated factor")

    # de-dup flags in the canonical FACTOR_FLAGS order; refs sorted-unique.
    ordered_flags = [f for f in FACTOR_FLAGS if f in set(flags)]
    ordered_refs = sorted(set(r for r in refs if str(r or "").strip()))
    return ordered_flags, ordered_refs, reasons, has_real, bool(social_items)


# --------------------------------------------------------------------------- #
# The discovery engine                                                          #
# --------------------------------------------------------------------------- #
def discover_candidates(
    graph: ThemeGraph,
    *,
    run_id: str,
    now: str,
    signals: Tuple = (),
    events: Tuple = (),
    findings: Tuple = (),
    dq_state: str = "",
    risk_nodes: Tuple = (),
    watchlist: Optional[Tuple[str, ...]] = None,
) -> Tuple[DiscoveryCandidate, ...]:
    """Emit a :class:`DiscoveryCandidate` for each monitored / watchlist ticker.

    For each ticker it computes the PRESENT ``factor_flags`` from the graph connection + the
    persisted evidence (SEC events, FMP rows, 021B financial-inflection findings, fused signals,
    red-team risks, data gaps), then derives the categorical ``discovery_state``:

    * ``blocked_dq_failed`` -- the run's DQ is failed (or ``blocked_by_policy``);
    * ``blocked_risk_too_high`` -- an unresolved thesis-killer (company-level ``severe``) red-team
      risk dominates;
    * ``diligence_candidate`` -- graph-connected AND real (non-social) corroborating evidence AND
      DQ not failed AND no dominating risk (the ONLY "worth diligence" state);
    * ``monitor_only`` -- connected but thin, evidence off the map, or social / rumor-only;
    * ``blocked_insufficient_evidence`` -- neither a graph connection NOR any real corroborating
      evidence (nothing to go on).

    Never fabricates a factor; a social / rumor-only basis (or a failed DQ) can NEVER reach
    ``diligence_candidate``. Deterministic (injected ``now`` + a content-derived id); offline.
    """
    if not str(run_id or "").strip():
        raise ValueError("discover_candidates requires a non-empty run_id")

    dq = _normalize_dq(dq_state)
    universe = tuple(watchlist) if watchlist is not None else graph.monitored_tickers
    node_by_ticker = {c.ticker: c for c in graph.companies}

    ev = tuple(events or ())
    fi = tuple(findings or ())
    si = tuple(signals or ())

    out: List[DiscoveryCandidate] = []
    for raw_ticker in universe:
        ticker = str(raw_ticker or "").strip().upper()
        if not ticker:
            continue
        node = node_by_ticker.get(ticker)
        bottleneck_refs = tuple(node.linked_bottleneck_refs) if node is not None else ()
        # keep only bottleneck refs that actually resolve in the graph
        known_bn = {b.bottleneck_id for b in graph.bottlenecks}
        bottleneck_refs = tuple(b for b in bottleneck_refs if b in known_bn)
        theme_refs = _theme_refs_for(graph, bottleneck_refs) if node is not None else ()

        t_events = _for_ticker(ev, ticker)
        t_findings = _for_ticker(fi, ticker)
        t_signals = _for_ticker(si, ticker)
        risks = _applicable_risks(ticker, theme_refs, bottleneck_refs, graph, risk_nodes)

        flags, refs, reasons, has_real, has_social = _factor_flags_and_refs(
            graph, ticker, node, theme_refs, bottleneck_refs,
            t_events, t_findings, t_signals, risks)

        connected = "theme_relevant" in flags
        dominating = [r for r in risks
                      if str(getattr(r, "theme_or_company_ref", "") or "") == ticker
                      and str(getattr(r, "severity_label", "") or "") == "severe"]

        # -- derive the categorical state (order matters) -- #
        if dq == "failed":
            state = "blocked_dq_failed"
            reasons = list(reasons) + [
                "BLOCKED: the producing run's data quality is FAILED -- discovery never promotes "
                "a candidate off a failed-DQ run"]
        elif dominating:
            state = "blocked_risk_too_high"
            reasons = list(reasons) + [
                "BLOCKED: an unresolved thesis-killer red-team risk dominates ({0}) -- risk too "
                "high to flag for diligence".format(
                    ", ".join(sorted(str(getattr(r, "risk_id", "") or "") for r in dominating)))]
        elif connected and has_real:
            state = "diligence_candidate"
            reasons = list(reasons) + [
                "WORTH DILIGENCE: graph-connected AND corroborated by real (non-social) evidence "
                "-- flagged as a diligence candidate (NOT a recommendation; publication still "
                "requires the full 020A gate)"]
        elif has_real or has_social:
            state = "monitor_only"
            reasons = list(reasons) + [
                "MONITOR ONLY: {0} -- kept on watch, not promoted".format(
                    "evidence present but not connected on the Theme Graph" if not connected
                    else "connected but corroboration is thin / social-only")]
        elif connected:
            state = "blocked_insufficient_evidence"
            reasons = list(reasons) + [
                "BLOCKED: connected on the Theme Graph but NO real corroborating evidence beyond "
                "bare graph membership -- insufficient evidence to flag for diligence"]
        else:
            state = "blocked_insufficient_evidence"
            reasons = list(reasons) + [
                "BLOCKED: no graph connection AND no real corroborating evidence -- nothing to go "
                "on (insufficient evidence)"]

        basis = (
            "discovery run {0} for {1}: state={2}; flags=[{3}]; graph themes=[{4}]; "
            "evidence refs={5}; dq={6}".format(
                run_id, ticker, state, ", ".join(flags), ", ".join(theme_refs),
                len(refs), dq or "unstated"))

        out.append(DiscoveryCandidate(
            discovery_id=discovery_id_for(run_id, ticker),
            run_id=str(run_id).strip(),
            generated_at=str(now),
            ticker=ticker,
            theme_refs=theme_refs,
            bottleneck_refs=bottleneck_refs,
            discovery_state=state,
            factor_flags=tuple(flags),
            reasons=tuple(reasons),
            trust_data_quality_state=dq,
            source_refs=tuple(refs),
            basis=basis))

    return tuple(out)


# --------------------------------------------------------------------------- #
# Diligence handoff -- records an INPUT, NEVER publishes a CapitalCandidate       #
# --------------------------------------------------------------------------- #
def trigger_diligence_input(
    candidate: DiscoveryCandidate,
    *,
    store_dir: str,
) -> str:
    """Record a DILIGENCE INPUT stub for a ``diligence_candidate``. NEVER publishes.

    Writes an operator/engine-enrichable diligence-input record to
    ``<store_dir>/diligence_inputs/<TICKER>.json`` -- the input the 020A publish path CONSUMES.
    It does NOT create a :class:`~reality_mesh.capital_candidate.CapitalCandidate` and does NOT
    make a recommendation: publication still runs the full 020A gate
    (:func:`~reality_mesh.capital_candidate.publish_candidates_for_run`), which requires source
    provenance + fused-signal refs + an opportunity hypothesis + an investment-diligence thesis +
    a healthy DQ. Deterministic (content is derived from the candidate + its injected timestamp);
    returns the path written. Raises ``ValueError`` if the candidate is not a diligence candidate.
    """
    if not isinstance(candidate, DiscoveryCandidate):
        raise TypeError("trigger_diligence_input expects a DiscoveryCandidate")
    if candidate.discovery_state != "diligence_candidate":
        raise ValueError(
            "trigger_diligence_input only records an input for a 'diligence_candidate'; {0} is "
            "{1!r} -- a non-diligence discovery never enters the diligence queue".format(
                candidate.ticker, candidate.discovery_state))
    if not str(store_dir or "").strip():
        raise ValueError("trigger_diligence_input requires a non-empty store_dir")

    inputs_dir = os.path.join(str(store_dir), "diligence_inputs")
    os.makedirs(inputs_dir, exist_ok=True)
    path = os.path.join(inputs_dir, "{0}.json".format(candidate.ticker))

    record = {
        "diligence_input_id": "din:{0}".format(candidate.discovery_id),
        "discovery_id": candidate.discovery_id,
        "run_id": candidate.run_id,
        "generated_at": candidate.generated_at,
        "ticker": candidate.ticker,
        "theme_refs": list(candidate.theme_refs),
        "bottleneck_refs": list(candidate.bottleneck_refs),
        "factor_flags": list(candidate.factor_flags),
        "reasons": list(candidate.reasons),
        "trust_data_quality_state": candidate.trust_data_quality_state,
        "source_refs": list(candidate.source_refs),
        "basis": candidate.basis,
        # An INPUT only -- NOT a publication and NOT a recommendation.
        "kind": "diligence_input_stub",
        "publishes_capital_candidate": False,
        "requires_020a_publish_gate": True,
        "note": (
            "Diligence INPUT stub produced by the Candidate Discovery Engine (021E). This flags "
            "the company as worth diligence; it is NOT a recommendation and does NOT publish a "
            "CapitalCandidate. Publication STILL requires the full 020A gate: source provenance + "
            "fused RealitySignal refs + an OpportunityHypothesis + an InvestmentDiligence thesis "
            "+ a healthy DQ gate."),
    }

    line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path


# --------------------------------------------------------------------------- #
# Construction-time guard: the contract may carry NO trade / score field.        #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(DiscoveryCandidate)
