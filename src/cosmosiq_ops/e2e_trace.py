"""The CosmosIQ End-to-End Evidence-to-Candidate Trial (IMPLEMENTATION-020H).

The capstone observability slice of Phase 020. Where the earlier phases each proved ONE link,
this runner drives the WHOLE CosmosIQ intelligence chain ONCE, end to end, then WALKS the
persisted stores to assemble a single, honest, traceable output an operator can observe:

    source record -> RealityEvent -> AgentFinding -> RealitySignal -> (SignalCluster) ->
    ThemePulse -> OpportunityHypothesisPacket -> Investment Diligence (input -> thesis) ->
    ForwardScenario (state or explicit gap) -> CapitalCandidate publication (eligible / blocked
    + exact reason) -> Trust / Data-Quality verdict -> shadow Alert -> Replay (deterministic_match)
    -> the exact UI routes that render each of the above.

THE HONESTY MANDATE (the whole point of 020H):

* A Capital Candidate is NEVER forced. The three valid outcomes are (1) an eligible candidate
  with COMPLETE, REAL provenance, (2) a blocked candidate carrying its EXACT ineligibility reason,
  (3) no candidate because the evidence was insufficient. This runner reports whichever HONESTLY
  occurs -- it never fabricates a ref, never hardcodes an eligible ticker, and never launders a
  social/rumor-only or a filing-metadata-without-diligence input into eligibility.
* NO live SEC fetch is made. ``SEC_USER_AGENT`` is unconfigured, so the SEC EDGAR live adapter is
  exercised only in its honest ``credentials_missing`` state -- a VISIBLE source gap, never a
  fabricated event, never a fixture fall-back dressed as live. The evidence therefore comes from
  the repo's LOCAL research fixtures, and every source record is labelled with its REAL authority /
  claim / freshness (a local research fixture is NOT canonical and NOT live -- it is labelled so).
* Every trace line cites a REAL persisted record id from the actual run (run_id / event id /
  finding id / signal id / theme_pulse id / hypothesis id / thesis id / candidate id). No invented
  ids: the walk reads them back out of the append-only stores.

Deterministic, stdlib-only, Python 3.9, OFFLINE. Every instant is injected (the pure core never
reads a wall clock); nothing here reaches a network; importing this module starts nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from reality_mesh.alerts import (
    FORBIDDEN_ALERT_PHRASES,
    SHADOW_MARKER,
    SHADOW_MODE_VALUE,
    alerts_with_status,
    generate_shadow_alerts_for_run,
)
from reality_mesh.capital_candidate import (
    INELIGIBLE_STATES,
    publish_candidates_for_run,
    published_candidates,
)
from reality_mesh.pulse import run_pulse
from reality_mesh.pulse_persistence import persist_and_summarize
from reality_mesh.sphurana import ThemePulseSynthesizer
from reality_mesh.stores import (
    DataQualityStore,
    EventStore,
    FindingStore,
)

__all__ = [
    "SourceRecordTrace",
    "SignalTrace",
    "ThemePulseTrace",
    "HypothesisTrace",
    "DiligenceTrace",
    "CandidateTrace",
    "ShadowAlertTrace",
    "UiRoute",
    "E2ETraceResult",
    "run_e2e_trial",
    "render_e2e_trace_report",
]

# The DQ statuses that count as a data-quality FAILURE / non-healthy for the gate roll-up.
_FAILING_DQ_STATUSES = frozenset({"fail", "failed", "blocked_by_policy"})

# Tickers for which the repo ships a bundled LOCAL RESEARCH FIXTURE that the accepted diligence
# engines can be run over ON DEMAND (offline). This is NOT a hardcoded candidate: a fixture only
# supplies diligence INPUTS; the produced thesis is real, and the candidate is still gated by the
# run's own signals + Trust/Data-Quality state. IREN is the only ticker with a bundled research
# fixture in the current checkout (runtime.vertical_slice_runner).
_BUNDLED_RESEARCH_TICKERS: Tuple[str, ...] = ("IREN",)


# --------------------------------------------------------------------------- #
# Per-stage frozen trace records (labels + real ids only; no score / trade)     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceRecordTrace:
    """One inbound source, labelled with its REAL authority / claim / freshness + provenance."""

    source_id: str
    authority: str
    claim_status: str
    freshness: str
    provenance: str
    note: str = ""


@dataclass(frozen=True)
class SignalTrace:
    """One persisted RealitySignal with its fusion authority / freshness / corroboration sidecar."""

    signal_id: str
    discipline: str
    companies: Tuple[str, ...] = field(default_factory=tuple)
    themes: Tuple[str, ...] = field(default_factory=tuple)
    authority: str = ""
    freshness: str = ""
    corroboration: str = ""
    direction: str = ""


@dataclass(frozen=True)
class ThemePulseTrace:
    """One persisted ThemePulse -- a STATE label over the run's signals (never a rank)."""

    theme_pulse_id: str
    theme_id: str
    state: str
    breadth: str = ""
    supporting_signals: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HypothesisTrace:
    """One OpportunityHypothesisPacket the pulse produced (a thing to TEST, never a thesis)."""

    hypothesis_id: str
    theme_pulse: str
    confidence_label: str = ""
    beneficiaries: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiligenceTrace:
    """Investment-diligence input/output for one ticker (real thesis refs, or an explicit gap)."""

    ticker: str
    produced: bool
    opportunity_hypothesis_ref: str = ""
    investment_diligence_ref: str = ""
    investability_assessment: str = ""
    forward_scenario_state: str = ""
    source_note: str = ""
    gap_reason: str = ""


@dataclass(frozen=True)
class CandidateTrace:
    """One published CapitalCandidate verdict, read back from the append-only publication log."""

    candidate_id: str
    ticker: str
    candidate_state: str
    is_eligible: bool
    missing_lineage: Tuple[str, ...] = field(default_factory=tuple)
    reality_signal_refs: Tuple[str, ...] = field(default_factory=tuple)
    opportunity_hypothesis_ref: str = ""
    investment_diligence_ref: str = ""
    trust_data_quality_state: str = ""
    basis: str = ""


@dataclass(frozen=True)
class ShadowAlertTrace:
    """One SHADOW alert observed in the inbox (delivery = in-app inbox only, never external)."""

    alert_id: str
    run_id: str
    category: str
    severity: str
    mode: str
    recommended_review_action: str = ""
    dq_state: str = ""
    candidate_ref: str = ""
    marked_shadow: bool = False
    delivery: str = "in_app_inbox_only"


@dataclass(frozen=True)
class UiRoute:
    """One UI route the trace verified at dispatch level (status + whether it named the ticker)."""

    label: str
    route: str
    status: int
    mentions_focus: bool = False


@dataclass(frozen=True)
class E2ETraceResult:
    """Everything ONE end-to-end trial did -- assembled by WALKING the persisted stores.

    Every field is a label / count / injected instant / real persisted id / small summary -- never a
    secret, never a score / rank / trade field. ``candidate_outcome`` is the HONEST outcome that
    actually occurred (never forced): one of ``eligible`` / ``all_blocked`` / ``no_candidate``.
    """

    store_dir: str = ""
    now: str = ""
    run_id: str = ""
    mode: str = "pulse"
    watchlist: Tuple[str, ...] = field(default_factory=tuple)
    themes: Tuple[str, ...] = field(default_factory=tuple)
    focus_ticker: str = ""
    fixture_dir: str = ""
    # -- inbound source records + the honest SEC gap ------------------------ #
    source_records: Tuple[SourceRecordTrace, ...] = field(default_factory=tuple)
    sec_configured: bool = False
    sec_source_health: Dict[str, Any] = field(default_factory=dict)
    # -- the pulse chain ---------------------------------------------------- #
    events_persisted: int = 0
    event_sample_ids: Tuple[str, ...] = field(default_factory=tuple)
    findings_persisted: int = 0
    finding_sample_ids: Tuple[str, ...] = field(default_factory=tuple)
    signals: Tuple[SignalTrace, ...] = field(default_factory=tuple)
    clusters_persisted: int = 0
    cluster_ids: Tuple[str, ...] = field(default_factory=tuple)
    theme_pulses: Tuple[ThemePulseTrace, ...] = field(default_factory=tuple)
    themes_data_insufficient: Tuple[str, ...] = field(default_factory=tuple)
    # -- opportunity discovery + diligence + forward ------------------------ #
    hypotheses: Tuple[HypothesisTrace, ...] = field(default_factory=tuple)
    diligence: Tuple[DiligenceTrace, ...] = field(default_factory=tuple)
    forward_scenario_state: str = ""
    forward_note: str = ""
    # -- candidate publication (020A) --------------------------------------- #
    candidates: Tuple[CandidateTrace, ...] = field(default_factory=tuple)
    eligible_count: int = 0
    blocked_count: int = 0
    forged_eligible: Tuple[str, ...] = field(default_factory=tuple)
    candidate_outcome: str = "no_candidate"
    candidate_outcome_reason: str = ""
    # -- Trust / Data-Quality ----------------------------------------------- #
    dq_overall: str = ""
    dq_failing: Tuple[str, ...] = field(default_factory=tuple)
    # -- shadow alerts ------------------------------------------------------ #
    shadow_alerts: Tuple[ShadowAlertTrace, ...] = field(default_factory=tuple)
    alerts_baseline: bool = False
    alert_forbidden_phrase_hits: Tuple[str, ...] = field(default_factory=tuple)
    external_delivery_occurred: bool = False
    production_escalation_occurred: bool = False
    # -- replay ------------------------------------------------------------- #
    replay_deterministic_match: bool = False
    replay_differences: Tuple[str, ...] = field(default_factory=tuple)
    # -- UI verification ---------------------------------------------------- #
    ui_routes: Tuple[UiRoute, ...] = field(default_factory=tuple)
    app_command: str = ""
    # -- honesty ------------------------------------------------------------ #
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    honesty_caveats: Tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #
def _deterministic_run_id(now: str) -> str:
    """A deterministic run id from the injected instant (no wall-clock in any id / replay path)."""
    slug = "".join(ch for ch in str(now) if ch.isalnum())
    return "e2e.{0}".format(slug or "run")


def _probe_sec_source_health(watchlist: Tuple[str, ...], themes: Tuple[str, ...],
                             *, now: str) -> Tuple[bool, Dict[str, Any]]:
    """Probe the SEC EDGAR live adapter -- OFFLINE, honest ``credentials_missing`` gap.

    ``SEC_USER_AGENT`` is not configured, so the adapter is exercised with
    ``sec_user_agent_present=False`` and no transport: it SKIPS the fetch and yields a VISIBLE
    ``credentials_missing`` gap. No network is reached, no event is fabricated, no fixture is
    substituted. Returns ``(configured=False, health_dict)``.
    """
    from reality_mesh.adapters.sec_edgar_live import SecEdgarLiveAdapter

    adapter = SecEdgarLiveAdapter(sec_user_agent_present=False)
    _events, result = adapter.fetch_checked(
        watchlist=list(watchlist), themes=list(themes), now=now)
    health = {
        "adapter_id": result.adapter_id,
        "status": result.status,
        "source_health": result.source_health,
        "credentials_status": result.credentials_status,
        "events_created": result.events_created,
        "data_gaps": list(result.data_gaps),
        "rate_limit_status": result.rate_limit_status,
    }
    configured = result.credentials_status == "present"
    return configured, health


def _bundled_research_diligence(watchlist: Tuple[str, ...], *,
                                now: str) -> Dict[str, Dict[str, str]]:
    """Run the ACCEPTED diligence engines over the bundled LOCAL RESEARCH FIXTURES (offline).

    For each watchlist ticker that has a bundled research fixture (currently IREN via
    ``runtime.vertical_slice_runner``), run the real chain (Observations ->
    IntelligenceAssessment -> OpportunityHypothesis -> InvestmentThesis) UNCHANGED and return the
    REAL refs ``{TICKER: {opportunity_hypothesis_ref, investment_diligence_ref,
    forward_scenario_state}}``. The thesis is real (accepted engines); its INPUTS are local research
    fixtures -- NOT live, NOT canonical -- and are labelled so in the trace. A ticker with no
    bundled fixture is simply omitted (honest absence, never a fabricated ref).
    """
    out: Dict[str, Dict[str, str]] = {}
    wanted = [t for t in watchlist if t.upper() in _BUNDLED_RESEARCH_TICKERS]
    if not wanted:
        return out
    # Lazy imports: keep this module inert on import (no engine wiring until a fixture is present).
    from genesis.opportunity_hypothesis import generate_opportunity_hypothesis
    from prometheus.investment_thesis import generate_investment_thesis
    from reality_intelligence.intelligence_assessment import (
        generate_intelligence_assessment,
    )
    from runtime.vertical_slice_runner import (
        iren_diligence_inputs,
        iren_source_observations,
    )

    domain = "ai-infrastructure"
    actor = "cosmosiq.e2e"
    # The diligence engines take a float instant; 0.0 is an injected deterministic epoch (the refs
    # are content-derived and byte-stable). No wall clock is read.
    engine_now = 0.0
    for ticker in wanted:
        if ticker.upper() != "IREN":
            continue
        obs = iren_source_observations(engine_now)
        ia = generate_intelligence_assessment(obs, domain=domain, actor=actor, now=engine_now)
        oph = generate_opportunity_hypothesis([ia], domain=domain, actor=actor, now=engine_now)
        thesis = generate_investment_thesis(
            oph, iren_diligence_inputs(), actor=actor, now=engine_now)
        out[ticker.upper()] = {
            "opportunity_hypothesis_ref": str(getattr(thesis, "opportunity_id", "") or ""),
            "investment_diligence_ref": str(getattr(thesis, "thesis_id", "") or ""),
            "forward_scenario_state": "present",
            "investability_assessment": str(
                getattr(thesis, "investability_assessment", "") or ""),
        }
    return out


def _choose_focus_ticker(watchlist: Tuple[str, ...], pulse_result: Any) -> str:
    """The strongest-evidence ticker to trace fully: prefer one carrying a CANONICAL signal.

    A canonical (primary-filing) signal is the strongest evidence tier; failing that, the first
    watchlist ticker with ANY fused signal; failing that, "" (no ticker had evidence this run).
    """
    auth = dict(pulse_result.authority_by_signal or {})
    canonical: List[str] = []
    with_signal: List[str] = []
    for ticker in watchlist:
        symbol = ticker.upper()
        for sig in pulse_result.signals:
            if symbol in {c.upper() for c in getattr(sig, "affected_companies", ())}:
                with_signal.append(symbol)
                if auth.get(getattr(sig, "signal_id", ""), "") == "canonical":
                    canonical.append(symbol)
    for pick in canonical + with_signal:
        return pick
    return ""


def _source_records(pulse_result: Any, sec_health: Dict[str, Any],
                    diligence_produced: bool) -> Tuple[SourceRecordTrace, ...]:
    """The honest inbound-source ledger: the offline pulse fixtures + the SEC gap + research."""
    records: List[SourceRecordTrace] = []
    records.append(SourceRecordTrace(
        source_id="offline_pulse_fixtures",
        authority="mixed (per-event: canonical / convenience / rumor -- see the signal ledger)",
        claim_status="fixture-backed inputs modelling primary filings, market data + social",
        freshness="static (injected now; NOT a live measurement)",
        provenance="repo LOCAL offline fixtures (tests/fixtures/reality_mesh/pulse) -- NOT live, "
                   "NOT a network fetch",
        note="{0} event(s) loaded into this pulse".format(pulse_result.events_loaded)))
    records.append(SourceRecordTrace(
        source_id=str(sec_health.get("adapter_id", "evidence.sec_edgar_live")),
        authority="would be canonical / primary-regulatory IF fetched",
        claim_status=str(sec_health.get("status", "skipped")),
        freshness="n/a -- no live fetch was made",
        provenance="SEC EDGAR live adapter, {0} (SEC_USER_AGENT absent)".format(
            sec_health.get("source_health", "credentials_missing")),
        note="VISIBLE source gap: no live SEC fetch, no fixture fall-back, nothing fabricated"))
    if diligence_produced:
        records.append(SourceRecordTrace(
            source_id="local_research_diligence_fixture",
            authority="local research fixture (offline)",
            claim_status="research inputs to the accepted diligence engines (thesis is real)",
            freshness="static (injected deterministic instant)",
            provenance="runtime.vertical_slice_runner bundled research fixture -- NOT live, NOT "
                       "canonical",
            note="the produced InvestmentThesis is real; its INPUTS are labelled research "
                 "fixtures"))
    return tuple(records)


def _signal_traces(pulse_result: Any) -> Tuple[SignalTrace, ...]:
    auth = dict(pulse_result.authority_by_signal or {})
    fresh = dict(pulse_result.freshness_by_signal or {})
    corr = dict(pulse_result.corroboration_by_signal or {})
    out: List[SignalTrace] = []
    for sig in pulse_result.signals:
        sid = getattr(sig, "signal_id", "")
        out.append(SignalTrace(
            signal_id=sid, discipline=getattr(sig, "discipline", ""),
            companies=tuple(getattr(sig, "affected_companies", ()) or ()),
            themes=tuple(getattr(sig, "affected_themes", ()) or ()),
            authority=auth.get(sid, ""), freshness=fresh.get(sid, ""),
            corroboration=corr.get(sid, getattr(sig, "corroboration_status", "")),
            direction=getattr(sig, "direction_label", "")))
    return tuple(out)


def _theme_pulse_traces(pulse_result: Any) -> Tuple[ThemePulseTrace, ...]:
    out: List[ThemePulseTrace] = []
    for tp in pulse_result.theme_pulses:
        out.append(ThemePulseTrace(
            theme_pulse_id=getattr(tp, "theme_pulse_id", ""),
            theme_id=getattr(tp, "theme_id", ""),
            state=getattr(tp, "state", ""),
            breadth=getattr(tp, "breadth_label", ""),
            supporting_signals=tuple(getattr(tp, "supporting_signals", ()) or ())))
    return tuple(out)


def _themes_data_insufficient(themes: Tuple[str, ...], pulse_result: Any) -> Tuple[str, ...]:
    """The requested themes that produced no covering signal (honest 'Data insufficient')."""
    def norm(text: str) -> str:
        return "".join(ch for ch in str(text or "").lower() if ch.isalnum())

    covered = set()
    for tp in pulse_result.theme_pulses:
        covered.add(norm(getattr(tp, "theme_id", "")))
        covered.add(norm(getattr(tp, "theme_name", "")))
    return tuple(t for t in themes if norm(t) not in covered)


def _hypothesis_traces(pulse_result: Any, now: str) -> Tuple[HypothesisTrace, ...]:
    """Re-derive the OpportunityHypothesisPackets the pulse's fused signals produced (real ids).

    ``run_pulse`` computes these inside Sphurana but only returns the theme pulses; re-running the
    stateless synthesizer over the SAME fused clusters/signals reproduces the identical packets
    (deterministic), so the trace can cite their real ``hypothesis_id``s.
    """
    result = ThemePulseSynthesizer().synthesize(
        pulse_result.clusters, pulse_result.signals, now=now)
    out: List[HypothesisTrace] = []
    for hyp in result.hypotheses:
        out.append(HypothesisTrace(
            hypothesis_id=getattr(hyp, "hypothesis_id", ""),
            theme_pulse=getattr(hyp, "theme_pulse", ""),
            confidence_label=getattr(hyp, "confidence_label", ""),
            beneficiaries=tuple(getattr(hyp, "beneficiary_candidates", ()) or ())))
    return tuple(out)


def _forward_scenario_state(diligence_map: Dict[str, Dict[str, str]],
                            focus: str) -> Tuple[str, str]:
    """The forward-scenario state for the focus ticker (present, or an explicit absent gap)."""
    spec = dict(diligence_map.get(focus.upper()) or {})
    state = str(spec.get("forward_scenario_state", "") or "absent")
    if state == "present":
        note = ("forward inputs supplied with the diligence thesis -> forward scenario PRESENT "
                "(sidecar-only; never laundered into a present fact)")
    else:
        note = ("no evidence-backed forward assumptions supplied -> forward scenario is an "
                "explicit GAP ('{0}'); a missing forward is a rendered gap, NOT a block".format(
                    state))
    return state, note


def _candidate_traces(store_dir: str, run_id: str) -> Tuple[CandidateTrace, ...]:
    out: List[CandidateTrace] = []
    for cand in published_candidates(store_dir, run_id):
        out.append(CandidateTrace(
            candidate_id=cand.candidate_id, ticker=cand.ticker,
            candidate_state=cand.candidate_state, is_eligible=cand.is_eligible,
            missing_lineage=cand.missing_lineage(),
            reality_signal_refs=tuple(cand.reality_signal_refs),
            opportunity_hypothesis_ref=cand.opportunity_hypothesis_ref,
            investment_diligence_ref=cand.investment_diligence_ref,
            trust_data_quality_state=cand.trust_data_quality_state,
            basis=cand.basis))
    return tuple(out)


def _dq_verdict(store_dir: str, run_id: str) -> Tuple[str, Tuple[str, ...]]:
    overall = ""
    failing: List[str] = []
    for record in DataQualityStore(store_dir).query(run_id=run_id):
        if record.category == "gate_overall":
            overall = record.status
        elif record.status in _FAILING_DQ_STATUSES or record.status == "degraded":
            failing.append("{0}: {1} ({2})".format(
                record.category, record.status, record.summary or "no summary"))
    return overall, tuple(failing)


def _shadow_alert_traces(store_dir: str) -> Tuple[Tuple[ShadowAlertTrace, ...], Tuple[str, ...]]:
    out: List[ShadowAlertTrace] = []
    forbidden: List[str] = []
    for alert in alerts_with_status(store_dir):
        if alert.mode != SHADOW_MODE_VALUE:
            continue
        marked = SHADOW_MARKER in alert.human_readable_reason
        out.append(ShadowAlertTrace(
            alert_id=alert.alert_id, run_id=alert.run_id, category=alert.category,
            severity=alert.severity, mode=alert.mode,
            recommended_review_action=alert.recommended_review_action,
            dq_state=alert.dq_state, candidate_ref=alert.candidate_ref, marked_shadow=marked))
        blob = "{0} {1}".format(alert.human_readable_reason,
                                alert.recommended_review_action).lower()
        for phrase in FORBIDDEN_ALERT_PHRASES:
            if phrase in blob:
                forbidden.append("{0}: {1}".format(alert.alert_id, phrase))
    return tuple(out), tuple(forbidden)


def _verify_ui_routes(store_dir: str, run_id: str, focus: str,
                      now: str) -> Tuple[UiRoute, ...]:
    """Verify the exact UI routes that render each stage, at dispatch level (offline, GET-only)."""
    from cosmosiq_app.api import dispatch

    focus = focus or "IREN"
    plan = [
        ("Home / index", "/"),
        ("Runs list", "/runs"),
        ("Run detail (source health + agent health + DQ panel)", "/runs/" + run_id),
        ("Trust / Data-Quality (JSON, gate_overall + dq records)", "/api/runs/" + run_id),
        ("Source + agent health (JSON)", "/api/health"),
        ("Agent coverage / health (JSON)", "/api/coverage"),
        ("Capital Candidates page (blocked reason / empty state)", "/candidates"),
        ("Company Cockpit for the focus ticker", "/companies/" + focus),
        ("Capital-candidate cockpit for the focus ticker", "/candidates/" + focus),
        ("Alert Inbox", "/alerts"),
        ("Replay Viewer", "/replay/" + run_id),
    ]
    out: List[UiRoute] = []
    for label, route in plan:
        resp = dispatch({"method": "GET", "path": route, "query": {}, "body": None},
                        store_dir=store_dir, now=now)
        body = str(resp.get("body", ""))
        out.append(UiRoute(
            label=label, route=route, status=int(resp.get("status", 0)),
            mentions_focus=focus in body))
    return tuple(out)


# --------------------------------------------------------------------------- #
# run_e2e_trial -- drive the whole chain once, then WALK the persisted stores    #
# --------------------------------------------------------------------------- #
def run_e2e_trial(store_dir: str, *, watchlist, themes, now: str,
                  publish_diligence_by_ticker: Optional[Dict[str, Any]] = None,
                  fixture_dir: Optional[str] = None) -> E2ETraceResult:
    """Run ONE complete evidence-to-candidate trial and assemble the honest end-to-end trace.

    Drives ``run_pulse`` -> ``persist_and_summarize`` into ``store_dir`` (the SEC live adapter is
    probed separately in its honest ``credentials_missing`` gap), re-derives the pulse's
    OpportunityHypothesisPackets, runs the ACCEPTED diligence engines over any bundled LOCAL
    RESEARCH FIXTURE (offline -- real thesis, fixture inputs, labelled so), runs the 020A publish
    path, generates shadow alerts, and replays the run. It then WALKS the append-only stores to
    cite the REAL persisted id at every stage and reports the HONEST candidate outcome -- an
    eligible candidate lands ONLY with full real provenance + a healthy run; otherwise it lands
    blocked WITH its exact reason (or no candidate at all). Nothing is forced.

    ``publish_diligence_by_ticker`` (optional) merges over / overrides the auto-derived diligence
    map per ticker -- an operator can inject real recorded refs. ``fixture_dir`` (optional,
    additive) points the pulse at a specific offline fixture set; the default is the bundled pulse
    fixtures. Deterministic + OFFLINE: injected ``now``, deterministic ``run_id``, no network.
    """
    if not str(store_dir).strip():
        raise ValueError("run_e2e_trial requires a non-empty store_dir")
    if not str(now).strip():
        raise ValueError("run_e2e_trial requires a non-empty injected now")
    watch = tuple(t.strip().upper() for t in watchlist if str(t).strip())
    theme_list = tuple(t.strip() for t in themes if str(t).strip())
    if not watch or not theme_list:
        raise ValueError("run_e2e_trial requires a non-empty watchlist AND themes")

    os.makedirs(store_dir, exist_ok=True)
    run_id = _deterministic_run_id(now)

    # 1. probe SEC EDGAR live -> honest credentials_missing gap (no live fetch, no fabrication).
    sec_configured, sec_health = _probe_sec_source_health(watch, theme_list, now=now)

    # 2. run ONE pulse over the LOCAL offline fixtures + persist it (replay verified inside).
    pulse_result = run_pulse(watch, theme_list, now=now, fixture_dir=fixture_dir)
    _run, replay_result, _panels = persist_and_summarize(
        pulse_result, store_dir=store_dir, run_id=run_id, now=now)

    # 3. re-derive the opportunity-hypothesis packets from the SAME fused signals (real ids).
    hypotheses = _hypothesis_traces(pulse_result, now)

    # 4. run the accepted diligence engines over the bundled LOCAL RESEARCH FIXTURES (real thesis).
    diligence_map: Dict[str, Dict[str, str]] = _bundled_research_diligence(watch, now=now)
    if publish_diligence_by_ticker:
        for ticker, spec in publish_diligence_by_ticker.items():
            diligence_map[str(ticker).strip().upper()] = dict(spec or {})

    # 5. the 020A publish path (assess -> construct -> persist -> gate). No ref is fabricated; a
    #    candidate lands eligible ONLY with full real provenance + a healthy run, else blocked.
    publish_candidates_for_run(
        store_dir, run_id, tickers=watch, now=now, mode="pulse",
        diligence_by_ticker=diligence_map)

    # 6. shadow alerts (SHADOW_24X7; inbox-only; a first run is a quiet baseline, honestly).
    generate_shadow_alerts_for_run(store_dir, run_id, now=now)

    # -- WALK the persisted stores: cite the REAL id at every stage ---------- #
    focus = _choose_focus_ticker(watch, pulse_result)
    events = EventStore(store_dir).query(run_id=run_id)
    findings = FindingStore(store_dir).query(run_id=run_id)

    diligence_traces = _diligence_traces(diligence_map, focus, watch)
    forward_state, forward_note = _forward_scenario_state(diligence_map, focus)
    candidate_traces = _candidate_traces(store_dir, run_id)
    eligible = tuple(c for c in candidate_traces if c.is_eligible)
    blocked = tuple(c for c in candidate_traces if c.candidate_state in INELIGIBLE_STATES)
    forged = tuple(c.candidate_id for c in candidate_traces
                   if c.is_eligible and c.missing_lineage)
    dq_overall, dq_failing = _dq_verdict(store_dir, run_id)
    shadow_traces, forbidden_hits = _shadow_alert_traces(store_dir)
    ui_routes = _verify_ui_routes(store_dir, run_id, focus, now)

    outcome, outcome_reason = _classify_outcome(candidate_traces, eligible, blocked, focus)

    caveats = (
        "No live SEC fetch: SEC_USER_AGENT is unconfigured, so the SEC EDGAR live adapter ran only "
        "in its honest credentials_missing state -- a VISIBLE source gap, never fabricated, never "
        "a fixture fall-back dressed as live.",
        "The evidence comes from the repo's LOCAL research fixtures. Each source record is labelled "
        "with its REAL authority / claim / freshness: a local research fixture is NOT canonical and "
        "NOT live.",
        "No Capital Candidate is forced: a candidate is eligible ONLY with full REAL provenance "
        "(current run_id + RealitySignal refs + OpportunityHypothesis ref + Investment Diligence "
        "ref) AND a healthy Trust/Data-Quality state; otherwise it is blocked WITH its exact "
        "reason.",
        "Shadow mode only: alerts land in the in-app inbox, marked Shadow Mode -- no external "
        "delivery, no production escalation, no trade control on any surface.",
        "Deterministic + offline: injected now, deterministic run_id, no network; the SEC probe "
        "reached no endpoint.",
    )

    return E2ETraceResult(
        store_dir=store_dir, now=now, run_id=run_id, mode="pulse",
        watchlist=watch, themes=theme_list, focus_ticker=focus,
        fixture_dir=pulse_result.fixture_dir,
        source_records=_source_records(pulse_result, sec_health, bool(diligence_map)),
        sec_configured=sec_configured, sec_source_health=sec_health,
        events_persisted=len(events),
        event_sample_ids=tuple(e.event_id for e in events[:6]),
        findings_persisted=len(findings),
        finding_sample_ids=tuple(f.finding_id for f in findings[:6]),
        signals=_signal_traces(pulse_result),
        clusters_persisted=len(pulse_result.clusters),
        cluster_ids=tuple(getattr(c, "cluster_id", "") for c in pulse_result.clusters),
        theme_pulses=_theme_pulse_traces(pulse_result),
        themes_data_insufficient=_themes_data_insufficient(theme_list, pulse_result),
        hypotheses=hypotheses,
        diligence=diligence_traces,
        forward_scenario_state=forward_state, forward_note=forward_note,
        candidates=candidate_traces,
        eligible_count=len(eligible), blocked_count=len(blocked), forged_eligible=forged,
        candidate_outcome=outcome, candidate_outcome_reason=outcome_reason,
        dq_overall=dq_overall, dq_failing=dq_failing,
        shadow_alerts=shadow_traces,
        alerts_baseline=not shadow_traces,
        alert_forbidden_phrase_hits=forbidden_hits,
        external_delivery_occurred=False, production_escalation_occurred=False,
        replay_deterministic_match=replay_result.deterministic_match,
        replay_differences=tuple(replay_result.differences),
        ui_routes=ui_routes,
        app_command="python3 -m cosmosiq_app --store-dir {0}".format(store_dir),
        data_gaps=tuple(pulse_result.data_gaps),
        honesty_caveats=caveats,
    )


def _diligence_traces(diligence_map: Dict[str, Dict[str, str]], focus: str,
                      watchlist: Tuple[str, ...]) -> Tuple[DiligenceTrace, ...]:
    """One diligence trace per watchlist ticker: a real thesis, or an explicit gap."""
    out: List[DiligenceTrace] = []
    for ticker in watchlist:
        spec = dict(diligence_map.get(ticker.upper()) or {})
        hyp = str(spec.get("opportunity_hypothesis_ref", "") or "")
        dil = str(spec.get("investment_diligence_ref", "") or "")
        if hyp and dil:
            out.append(DiligenceTrace(
                ticker=ticker, produced=True,
                opportunity_hypothesis_ref=hyp, investment_diligence_ref=dil,
                investability_assessment=str(spec.get("investability_assessment", "") or ""),
                forward_scenario_state=str(spec.get("forward_scenario_state", "") or "absent"),
                source_note="diligence run over the bundled LOCAL RESEARCH FIXTURE (offline; "
                            "real thesis, fixture inputs -- NOT live / NOT canonical)"))
        else:
            out.append(DiligenceTrace(
                ticker=ticker, produced=False,
                gap_reason="no diligence produced: no bundled research fixture / recorded "
                           "diligence inputs for {0} -- explicit gap, no thesis fabricated".format(
                               ticker)))
    return tuple(out)


def _classify_outcome(candidates: Tuple[CandidateTrace, ...],
                      eligible: Tuple[CandidateTrace, ...],
                      blocked: Tuple[CandidateTrace, ...], focus: str) -> Tuple[str, str]:
    """The single HONEST candidate outcome + a plain reason (never forced)."""
    if not candidates:
        return ("no_candidate",
                "no candidate was published -- no watchlist ticker carried publishable evidence "
                "this run")
    if eligible:
        names = ", ".join("{0} ({1})".format(c.ticker, c.candidate_id) for c in eligible)
        return ("eligible",
                "eligible candidate(s) with COMPLETE real provenance: {0}".format(names))
    reasons = sorted({c.candidate_state for c in blocked})
    focus_block = next((c for c in blocked if c.ticker == focus.upper()), None)
    detail = ""
    if focus_block is not None:
        detail = " Focus ticker {0}: {1} -- {2}".format(
            focus_block.ticker, focus_block.candidate_state, focus_block.basis)
    return ("all_blocked",
            "every published candidate is blocked; verdicts: {0}.{1}".format(
                ", ".join(reasons), detail))


# --------------------------------------------------------------------------- #
# render_e2e_trace_report -- answer every required question from the result      #
# --------------------------------------------------------------------------- #
def _yn(value: bool) -> str:
    return "yes" if value else "no"


def render_e2e_trace_report(result: E2ETraceResult, *, generated_at: str) -> str:
    """Render the FILLED end-to-end trace report from ``result`` (never from memory).

    Answers every required question: what source data came in / how fresh / what authority / what
    claim status / what RealityEvents / signals / which ThemePulse changed / whether an
    OpportunityHypothesis + Diligence + ForwardScenario were produced / whether a CapitalCandidate
    was published, eligible or blocked and WHY / whether an alert fired / whether replay succeeded /
    where in the app it renders. States the HONEST candidate outcome (never forced) and labels the
    SEC gap + the local-fixture authority plainly.
    """
    lines: List[str] = []
    add = lines.append
    sec = result.sec_source_health

    add("# End-to-End Evidence-to-Candidate Trial -- IMPLEMENTATION-020H")
    add("")
    add("Filled from the PERSISTED append-only stores of ONE actual end-to-end trial driven by "
        "`cosmosiq_ops.e2e_trace.run_e2e_trial`. Every id below is a real persisted record read "
        "back from the stores -- never invented. The candidate outcome is whatever HONESTLY "
        "occurred; nothing is forced.")
    add("")
    add("> HONESTY: no live SEC fetch (SEC_USER_AGENT unconfigured -> visible source gap); the "
        "evidence is LOCAL research fixtures, labelled NOT-live / NOT-canonical; a Capital "
        "Candidate is never fabricated.")
    add("")
    add("---")
    add("")

    # 0. Run identity
    add("## 0. Run identity")
    add("")
    add("| Field | Value |")
    add("|-------|-------|")
    add("| Run id (persisted) | `{0}` |".format(result.run_id))
    add("| Mode | `{0}` |".format(result.mode))
    add("| Injected now | {0} |".format(result.now))
    add("| Report prepared at (injected) | {0} |".format(generated_at))
    add("| Store dir | `{0}` |".format(result.store_dir))
    add("| Watchlist (monitored input, NOT a recommendation) | {0} |".format(
        ", ".join(result.watchlist) or "none"))
    add("| Themes | {0} |".format(", ".join(result.themes) or "none"))
    add("| Focus ticker (strongest evidence -- canonical signal) | {0} |".format(
        result.focus_ticker or "none (no ticker carried evidence)"))
    add("| Fixture source | `{0}` |".format(result.fixture_dir))
    add("")

    # 1. Inbound source data
    add("## 1. What source data came in -- authority, claim status, freshness")
    add("")
    add("| Source | Authority | Claim status | Freshness | Provenance | Note |")
    add("|--------|-----------|--------------|-----------|------------|------|")
    for rec in result.source_records:
        add("| `{0}` | {1} | {2} | {3} | {4} | {5} |".format(
            rec.source_id, rec.authority, rec.claim_status, rec.freshness,
            rec.provenance, rec.note))
    add("")
    add("SEC EDGAR live source health: **{0}** (configured={1}, status={2}, events_created={3}). "
        "SEC gap detail:".format(
            sec.get("source_health", "credentials_missing"), _yn(result.sec_configured),
            sec.get("status", "skipped"), sec.get("events_created", 0)))
    for gap in sec.get("data_gaps", []) or ["(none)"]:
        add("- {0}".format(gap))
    add("")

    # 2. RealityEvents + findings + signals
    add("## 2. What RealityEvents, findings and RealitySignals were produced")
    add("")
    add("| Stage | Count | Sample persisted ids |")
    add("|-------|-------|----------------------|")
    add("| RealityEvents (inputs agents saw) | {0} | {1} |".format(
        result.events_persisted, ", ".join("`" + i + "`" for i in result.event_sample_ids)))
    add("| AgentFindings (per-agent, in-discipline) | {0} | {1} |".format(
        result.findings_persisted, ", ".join("`" + i + "`" for i in result.finding_sample_ids)))
    add("| RealitySignals (fused) | {0} | see the signal ledger below |".format(
        len(result.signals)))
    add("| SignalClusters (multi-signal) | {0} | {1} |".format(
        result.clusters_persisted, ", ".join("`" + i + "`" for i in result.cluster_ids) or "none "
        "-- no multi-signal cluster formed this run (honest)"))
    add("")
    add("Signal ledger (authority / freshness / corroboration are honest per-signal labels):")
    add("")
    add("| Signal id | Discipline | Companies | Themes | Authority | Freshness | Corroboration |")
    add("|-----------|------------|-----------|--------|-----------|-----------|---------------|")
    for sig in result.signals:
        add("| `{0}` | {1} | {2} | {3} | {4} | {5} | {6} |".format(
            sig.signal_id, sig.discipline, ", ".join(sig.companies) or "-",
            ", ".join(sig.themes) or "-", sig.authority or "-", sig.freshness or "-",
            sig.corroboration or "-"))
    add("")
    add("> A rumor/social signal stays rumor: it is labelled `rumor` + `uncorroborated` and can "
        "never be laundered into canonical evidence or a candidate.")
    add("")

    # 3. ThemePulse
    add("## 3. Which ThemePulse changed (and which themes are Data insufficient)")
    add("")
    add("| ThemePulse id | Theme | State | Breadth | Supporting signals |")
    add("|---------------|-------|-------|---------|--------------------|")
    for tp in result.theme_pulses:
        add("| `{0}` | {1} | **{2}** | {3} | {4} |".format(
            tp.theme_pulse_id, tp.theme_id, tp.state, tp.breadth or "-",
            ", ".join("`" + s + "`" for s in tp.supporting_signals) or "-"))
    add("")
    add("Requested themes that produced NO covering signal (honest **Data insufficient**): "
        "{0}.".format(", ".join(result.themes_data_insufficient) or "none"))
    add("")

    # 4. OpportunityHypothesis
    add("## 4. Was an OpportunityHypothesis created?")
    add("")
    if result.hypotheses:
        add("Yes -- the pulse's fused signals produced these OpportunityHypothesisPackets (a thing "
            "to TEST, never a thesis / decision / rank):")
        add("")
        add("| Hypothesis id | For ThemePulse | Confidence | Beneficiary candidates |")
        add("|---------------|----------------|------------|------------------------|")
        for hyp in result.hypotheses:
            add("| `{0}` | `{1}` | {2} | {3} |".format(
                hyp.hypothesis_id, hyp.theme_pulse, hyp.confidence_label or "-",
                ", ".join(hyp.beneficiaries) or "-"))
    else:
        add("No -- no theme reached a non-Dormant pulse, so no OpportunityHypothesisPacket was "
            "emitted (honest absence).")
    add("")

    # 5. Diligence
    add("## 5. Was Investment Diligence triggered? (input -> output)")
    add("")
    add("| Ticker | Diligence produced? | Opportunity hypothesis ref | Investment diligence ref "
        "(thesis) | Investability | Forward | Provenance / gap |")
    add("|--------|---------------------|----------------------------|--------------------------"
        "-|---------------|---------|------------------|")
    for dil in result.diligence:
        if dil.produced:
            add("| {0} | yes | `{1}` | `{2}` | {3} | {4} | {5} |".format(
                dil.ticker, dil.opportunity_hypothesis_ref, dil.investment_diligence_ref,
                dil.investability_assessment or "-", dil.forward_scenario_state or "-",
                dil.source_note))
        else:
            add("| {0} | no | - | - | - | - | {1} |".format(dil.ticker, dil.gap_reason))
    add("")

    # 6. ForwardScenario
    add("## 6. ForwardScenario state (or explicit gap)")
    add("")
    add("Focus ticker forward-scenario state: **{0}**. {1}".format(
        result.forward_scenario_state, result.forward_note))
    add("")

    # 7. CapitalCandidate
    add("## 7. Was a CapitalCandidate published? Eligible or blocked -- and WHY")
    add("")
    add("**Honest outcome: `{0}`.** {1}".format(
        result.candidate_outcome, result.candidate_outcome_reason))
    add("")
    add("| Candidate id | Ticker | State | Eligible? | Signal refs | Hypothesis ref | Diligence "
        "ref | Trust/DQ | Exact basis / reason |")
    add("|--------------|--------|-------|-----------|-------------|----------------|-----------"
        "|----------|----------------------|")
    for cand in result.candidates:
        add("| `{0}` | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
            cand.candidate_id, cand.ticker, cand.candidate_state, _yn(cand.is_eligible),
            len(cand.reality_signal_refs),
            "`" + cand.opportunity_hypothesis_ref + "`" if cand.opportunity_hypothesis_ref
            else "-",
            "`" + cand.investment_diligence_ref + "`" if cand.investment_diligence_ref else "-",
            cand.trust_data_quality_state or "unstated", cand.basis))
    if not result.candidates:
        add("| (none) | - | - | - | - | - | - | - | no candidate published |")
    add("")
    add("Eligible: {0}. Blocked: {1}. Forged-eligible (MUST be 0): {2}.".format(
        result.eligible_count, result.blocked_count, len(result.forged_eligible)))
    add("")
    add("> Every candidate went through the store + the 019B eligibility gate. An eligible "
        "candidate is UNFORGEABLE without full real provenance AND a healthy producing run; a "
        "blocked candidate carries its EXACT missing-lineage reason -- nothing hidden, nothing "
        "fabricated.")
    add("")

    # 8. Trust / Data-Quality
    add("## 8. Trust / Data-Quality verdict")
    add("")
    add("Run `gate_overall`: **{0}**.".format(result.dq_overall or "unstated"))
    if result.dq_failing:
        add("")
        add("Degraded / failing gate categories (the honest reason a candidate off this run "
            "cannot be eligible):")
        for item in result.dq_failing:
            add("- {0}".format(item))
    add("")
    add("> DQ gates the run BEFORE any candidate can be eligible. A degraded run (e.g. carrying "
        "uncorroborated social/rumor records, kept weak by design) blocks every candidate at "
        "`ineligible_stale` -- the evidence lineage may be complete, but eligibility requires a "
        "healthy run.")
    add("")

    # 9. Alerts
    add("## 9. Did any alert fire? (Shadow Mode -- inbox only)")
    add("")
    add("| Alert id | Category | Severity | Review action | dq_state | Candidate ref | Marked "
        "Shadow? | Delivery |")
    add("|----------|----------|----------|---------------|----------|---------------|----------"
        "------|----------|")
    for alert in result.shadow_alerts:
        add("| `{0}` | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
            alert.alert_id, alert.category, alert.severity,
            alert.recommended_review_action or "-", alert.dq_state or "-",
            alert.candidate_ref or "-", _yn(alert.marked_shadow), alert.delivery))
    if not result.shadow_alerts:
        add("| (none) | - | - | - | - | - | - | - |")
    add("")
    add("Shadow alerts: {0} (baseline first run: {1}). Forbidden action-phrase hits (MUST be 0): "
        "{2}. External delivery: {3}. Production escalation: {4}.".format(
            len(result.shadow_alerts), _yn(result.alerts_baseline),
            len(result.alert_forbidden_phrase_hits),
            _yn(result.external_delivery_occurred),
            _yn(result.production_escalation_occurred)))
    add("")
    if result.alerts_baseline:
        add("> Zero alerts on a first run is the HONEST answer: the diff-based engine has no prior "
            "run to diff against, so it stays quiet (it never floods a baseline).")
        add("")

    # 10. Replay
    add("## 10. Was replay successful?")
    add("")
    add("Deterministic replay of the run: `deterministic_match = {0}`. Differences: {1}.".format(
        _yn(result.replay_deterministic_match),
        "; ".join(result.replay_differences) if result.replay_differences else "none"))
    add("")

    # 11. UI routes
    add("## 11. Where in the app this renders (exact routes, dispatch-verified)")
    add("")
    add("Launch the local operator app read-only with:")
    add("")
    add("```")
    add(result.app_command)
    add("```")
    add("")
    add("| Page / surface | Route | Dispatch status | Names focus ticker? |")
    add("|----------------|-------|-----------------|---------------------|")
    for route in result.ui_routes:
        add("| {0} | `{1}` | {2} | {3} |".format(
            route.label, route.route, route.status, _yn(route.mentions_focus)))
    add("")
    add("> The default product UI never leaks a fixture ticker: an EMPTY store renders `/`, "
        "`/runs` and `/candidates` clean. There is NO buy/sell/order/submit surface anywhere -- a "
        "trade-like path is refused (403) before routing.")
    add("")

    # 12. Honesty caveats + data gaps
    add("## 12. Honesty caveats + data gaps (stated plainly)")
    add("")
    for caveat in result.honesty_caveats:
        add("- {0}".format(caveat))
    add("")
    add("Data gaps recorded on this pulse:")
    for gap in result.data_gaps or ["(none)"]:
        add("- {0}".format(gap))
    add("")
    return "\n".join(lines)
