"""The Diligence-Lineage orchestration for the Reality Mesh (DILIGENCE-LINEAGE slice 1).

Wires the ALREADY-BUILT discovery -> hypothesis -> capital-candidate stages into ONE
end-to-end pass over a run's PERSISTED, REAL evidence, and reports each ticker's HONEST state.
It ORCHESTRATES existing engines -- it invents nothing:

1. loads the persisted run's fused ``RealitySignal``s / events / findings / data-quality from the
   013B stores (:class:`~reality_mesh.stores.SignalStore` / ``EventStore`` / ``FindingStore`` /
   ``DataQualityStore``);
2. runs the 021E Candidate Discovery Engine
   (:func:`~reality_mesh.discovery.discover_candidates`) over ``graph or build_seed_theme_graph()``
   -- the ONLY state that says "worth diligence" is ``diligence_candidate`` (graph-connected AND
   real, non-social corroboration AND DQ not failed AND no dominating risk);
3. for each ``diligence_candidate`` LINKS the run's Sphurana (012F) OpportunityHypothesis packet
   that already names the ticker as a beneficiary candidate -- a REAL packet id, never fabricated;
4. assembles a :class:`~reality_mesh.capital_candidate.CapitalCandidate` per diligence candidate
   with the refs that ACTUALLY exist (fused-signal refs + the linked hypothesis id;
   ``investment_diligence_ref`` stays EMPTY in slice 1 -- there is no accepted diligence thesis
   yet), and calls :func:`~reality_mesh.capital_candidate.assess_candidate_eligibility` for the
   honest ``candidate_state``;
5. persists candidates append-only via the 020A :class:`~reality_mesh.capital_candidate.
   CapitalCandidateStore` (and records the 021E diligence INPUT stub) when ``persist=True``.

THE HONESTY CEILING (slice 1): with no accepted diligence thesis, a fully-corroborated,
graph-connected ticker reaches AT MOST ``ineligible_missing_diligence`` -- NEVER ``eligible``.
This module never fabricates a ref and never forces ``eligible``; the ``CapitalCandidate``
construction invariant makes a forged eligible unreachable anyway. A graph-unconnected ticker is
``blocked_insufficient_evidence`` (honest); a social/rumor-only or failed-DQ basis is never a
diligence candidate (the 021E engine already enforces this -- this module does not weaken it).

Deterministic (injected ``now``), stdlib-only, Python 3.9, OFFLINE. No network / scheduler /
broker; no wall-clock; no fixture-as-real (it runs on the persisted evidence, never re-injects a
fixture event).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .capital_candidate import (
    CapitalCandidate,
    CapitalCandidateStore,
    assess_candidate_eligibility,
)
from .discovery import DiscoveryCandidate, discover_candidates, trigger_diligence_input
from .sphurana import ThemePulseSynthesizer
from .stores import (
    DataQualityStore,
    EventStore,
    FindingStore,
    RunStore,
    SignalStore,
)
from .theme_graph import ThemeGraph, build_seed_theme_graph

__all__ = [
    "LineageOutcome",
    "DiligenceLineageResult",
    "run_diligence_lineage",
]


# --------------------------------------------------------------------------- #
# Per-ticker honest outcome                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LineageOutcome:
    """The HONEST lineage state for one ticker under one run -- labels + refs, never a score.

    ``candidate_state`` is empty when no :class:`CapitalCandidate` was assembled (a ticker that
    never reached ``diligence_candidate`` has no capital standing to assess -- its honest state IS
    its ``discovery_state``). ``missing_link`` is the EXACT next thing required; ``why`` is a
    plain-English summary. There is NO numeric / rank / trade field anywhere.
    """

    ticker: str = ""
    discovery_state: str = ""
    candidate_state: str = ""                 # "" when no CapitalCandidate assembled
    graph_connected: bool = False
    theme_refs: Tuple[str, ...] = field(default_factory=tuple)
    factor_flags: Tuple[str, ...] = field(default_factory=tuple)
    reality_signal_refs: Tuple[str, ...] = field(default_factory=tuple)
    opportunity_hypothesis_ref: str = ""
    investment_diligence_ref: str = ""
    trust_data_quality_state: str = ""
    missing_link: str = ""
    why: str = ""


@dataclass(frozen=True)
class DiligenceLineageResult:
    """The whole pass: the discovery verdicts, the assembled capital candidates, the outcomes.

    Iterable as ``(discovery_candidates, capital_candidates, outcomes)`` for convenient unpacking.
    """

    run_id: str = ""
    generated_at: str = ""
    trust_data_quality_state: str = ""
    discovery_candidates: Tuple[DiscoveryCandidate, ...] = field(default_factory=tuple)
    capital_candidates: Tuple[CapitalCandidate, ...] = field(default_factory=tuple)
    outcomes: Tuple[LineageOutcome, ...] = field(default_factory=tuple)

    def __iter__(self):
        return iter((self.discovery_candidates, self.capital_candidates, self.outcomes))


# --------------------------------------------------------------------------- #
# Producing-run data-quality (mirrors the 020A publish path, read-only)         #
# --------------------------------------------------------------------------- #
_TRUST_DQ_STATES: Tuple[str, ...] = ("healthy", "degraded", "failed")


def _run_trust_dq_state(store_dir: str, run) -> str:
    """The producing run's Trust / Data-Quality state, mapped onto the trust-DQ subset.

    Read from the run's persisted ``gate_overall`` DQ record (falling back to the run's own
    ``data_quality_status``): ``healthy`` / ``degraded`` / ``failed`` pass through; a
    ``blocked_by_policy`` run is treated as ``failed``; anything else is honestly-unstated ("").
    """
    overall = ""
    for record in DataQualityStore(store_dir).query(run_id=run.run_id):
        if getattr(record, "category", "") == "gate_overall":
            overall = getattr(record, "status", "")
    raw = str(overall or getattr(run, "data_quality_status", "") or "")
    if raw in _TRUST_DQ_STATES:
        return raw
    if raw == "blocked_by_policy":
        return "failed"
    return ""


# --------------------------------------------------------------------------- #
# Honest "what is missing" for one ticker                                       #
# --------------------------------------------------------------------------- #
def _missing_link(disc: DiscoveryCandidate, cand: Optional[CapitalCandidate]) -> str:
    """The EXACT next thing this ticker needs, honestly -- never a fabricated promise."""
    state = disc.discovery_state
    if state == "diligence_candidate":
        if cand is None:
            return "worth diligence -- capital-candidate not yet assembled"
        cs = cand.candidate_state
        if cs == "ineligible_missing_diligence":
            return ("needs an accepted diligence thesis (no investment_diligence_ref yet) -- "
                    "this is the honest ceiling in slice 1")
        if cs == "ineligible_missing_provenance":
            return ("no opportunity-hypothesis packet links this ticker yet -- missing current-"
                    "run provenance")
        if cs == "ineligible_dq_failed":
            return "the producing run's data quality is failed"
        if cs == "ineligible_stale":
            return "the producing run's data quality is not healthy (degraded / unstated)"
        if cs == "eligible":
            return "full evidence lineage present"
        return cs
    if state == "blocked_dq_failed":
        return "the producing run's data quality is failed -- blocked before diligence"
    if state == "blocked_risk_too_high":
        return "an unresolved thesis-killer red-team risk dominates -- blocked before diligence"
    if state == "monitor_only":
        return ("kept on watch -- corroboration is thin or off the theme graph, not promoted to "
                "a diligence candidate")
    if state == "blocked_insufficient_evidence":
        if disc.theme_refs:
            return ("connected on the theme graph but no real corroboration in the evidence yet "
                    "-- blocked_insufficient_evidence")
        return ("not in the theme graph -- no graph connection and no real corroboration in the "
                "evidence -- blocked_insufficient_evidence")
    return state


def _why(disc: DiscoveryCandidate, cand: Optional[CapitalCandidate]) -> str:
    """A plain-English lineage summary combining the discovery basis + candidate basis."""
    parts = ["discovery: {0}".format(disc.discovery_state)]
    if disc.theme_refs:
        parts.append("themes [{0}]".format(", ".join(disc.theme_refs)))
    if disc.factor_flags:
        parts.append("factors [{0}]".format(", ".join(disc.factor_flags)))
    if cand is not None:
        parts.append("candidate: {0}".format(cand.candidate_state))
        parts.append(cand.basis)
    return "; ".join(parts)


# --------------------------------------------------------------------------- #
# The orchestration                                                             #
# --------------------------------------------------------------------------- #
def run_diligence_lineage(
    store_dir: str,
    *,
    run_id: str,
    watchlist: Tuple[str, ...],
    now: str,
    graph: Optional[ThemeGraph] = None,
    persist: bool = True,
) -> DiligenceLineageResult:
    """Run the end-to-end discovery -> hypothesis -> candidate lineage over ONE persisted run.

    Composes the existing stages -- it does NOT re-implement any of them:

    * loads the run's persisted fused signals / events / findings / DQ from the 013B stores;
    * :func:`~reality_mesh.discovery.discover_candidates` (021E) over ``graph`` (or the seed graph)
      + that evidence, scoped to ``watchlist``;
    * :meth:`~reality_mesh.sphurana.ThemePulseSynthesizer.synthesize` (012F) over the run's fused
      signals -> OpportunityHypothesis packets; a ``diligence_candidate`` is LINKED to the packet
      that already names it as a beneficiary candidate (a real packet id, never fabricated);
    * :func:`~reality_mesh.capital_candidate.assess_candidate_eligibility` (020A) per diligence
      candidate, with the refs that actually exist -- ``investment_diligence_ref`` stays EMPTY in
      slice 1, so the honest ceiling is ``ineligible_missing_diligence`` (NEVER ``eligible``).

    When ``persist`` is True the assembled candidates are written append-only to the 020A
    :class:`~reality_mesh.capital_candidate.CapitalCandidateStore` (idempotent by content-derived
    id) and each diligence candidate's 021E diligence INPUT stub is recorded; when False nothing
    is written (the read-only path the cockpit uses to render honest state).

    ``now`` is injected (never a wall-clock read); deterministic + offline. Returns a
    :class:`DiligenceLineageResult` (discovery verdicts + capital candidates + per-ticker honest
    outcomes with the exact what's-missing link). Raises ``ValueError`` on an empty / unknown run.
    """
    if not str(run_id or "").strip():
        raise ValueError("run_diligence_lineage requires a non-empty run_id")
    runs = RunStore(store_dir).query(run_id=run_id)
    if not runs:
        raise ValueError(
            "no persisted run with run_id {0!r} -- the lineage needs a CURRENT run that produced "
            "the evidence".format(run_id))
    run = runs[-1]
    the_graph = graph if graph is not None else build_seed_theme_graph()
    universe = tuple(watchlist or ())

    # -- load the run's PERSISTED, REAL evidence (never a re-injected fixture) -- #
    signals = tuple(SignalStore(store_dir).query(run_id=run_id))
    events = tuple(EventStore(store_dir).query(run_id=run_id))
    findings = tuple(FindingStore(store_dir).query(run_id=run_id))
    dq_state = _run_trust_dq_state(store_dir, run)
    mode = str(getattr(run, "mode", "") or "pulse")

    # -- 021E discovery over the graph + evidence, scoped to the watchlist -- #
    discovery_candidates = discover_candidates(
        the_graph, run_id=run_id, now=now,
        signals=signals, events=events, findings=findings,
        dq_state=dq_state, watchlist=universe)

    # -- 012F Sphurana: fused signals -> opportunity-hypothesis packets -- #
    sphurana = ThemePulseSynthesizer().synthesize(signals=signals, now=now)
    # Map ticker -> the FIRST hypothesis that names it as a beneficiary candidate (a real, existing
    # packet id -- we only LINK, never fabricate).
    hyp_by_ticker: Dict[str, str] = {}
    for hyp in sphurana.hypotheses:
        for beneficiary in hyp.beneficiary_candidates:
            hyp_by_ticker.setdefault(beneficiary, hyp.hypothesis_id)

    store = CapitalCandidateStore(store_dir) if persist else None
    capital_candidates: List[CapitalCandidate] = []
    outcomes: List[LineageOutcome] = []

    for disc in discovery_candidates:
        ticker = disc.ticker
        signal_refs = tuple(sorted(
            s.signal_id for s in signals if ticker in tuple(s.affected_companies or ())))
        cand: Optional[CapitalCandidate] = None

        if disc.is_diligence_candidate:
            hyp_ref = hyp_by_ticker.get(ticker, "")
            # Assemble the typed candidate with the refs that ACTUALLY exist. The diligence ref
            # stays EMPTY in slice 1 -- assess() therefore returns the honest ceiling
            # (ineligible_missing_diligence), and the eligible-construction invariant is never hit.
            cand = assess_candidate_eligibility(
                ticker=ticker, run_id=run_id,
                reality_signal_refs=signal_refs,
                opportunity_hypothesis_ref=hyp_ref,
                investment_diligence_ref="",           # no accepted thesis yet (slice 1)
                forward_scenario_state="absent",
                trust_data_quality_state=dq_state,
                mode=mode, now=now)
            capital_candidates.append(cand)
            if persist and store is not None:
                store.publish(cand)
                # Record the 021E diligence INPUT stub (an input, never a publication).
                trigger_diligence_input(disc, store_dir=store_dir)

        outcomes.append(LineageOutcome(
            ticker=ticker,
            discovery_state=disc.discovery_state,
            candidate_state=(cand.candidate_state if cand is not None else ""),
            graph_connected=bool(disc.theme_refs),
            theme_refs=disc.theme_refs,
            factor_flags=disc.factor_flags,
            reality_signal_refs=(cand.reality_signal_refs if cand is not None else signal_refs),
            opportunity_hypothesis_ref=(cand.opportunity_hypothesis_ref if cand is not None
                                        else ""),
            investment_diligence_ref=(cand.investment_diligence_ref if cand is not None else ""),
            trust_data_quality_state=dq_state,
            missing_link=_missing_link(disc, cand),
            why=_why(disc, cand)))

    return DiligenceLineageResult(
        run_id=run_id,
        generated_at=str(now),
        trust_data_quality_state=dq_state,
        discovery_candidates=discovery_candidates,
        capital_candidates=tuple(capital_candidates),
        outcomes=tuple(outcomes))
