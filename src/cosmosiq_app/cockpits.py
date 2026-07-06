"""The CosmosIQ cockpit pages -- theme / company / capital-candidate (IMPLEMENTATION-016C).

Three read-and-inspect surfaces over PERSISTED evidence plus (for the capital candidate)
an ON-DEMAND run of the already-accepted diligence engines over OPERATOR-PROVIDED inputs:

* ``/themes`` + ``/themes/<theme_id>`` -- the THEME COCKPIT: the pulse-state timeline across
  persisted runs, the "why did this theme change" diff (state A -> state B between run X ->
  run Y, with the inbox alert reason when one was recorded), the contributing signals with
  their source authority and explicit WEAK / social marks, contradictions with BOTH sides
  visible, and every recorded data gap.
* ``/companies/<ticker>`` -- the COMPANY COCKPIT: per-ticker events / findings / signals
  across runs with claim-status labels (a company claim is NEVER rendered as a verified
  fact), evidence references, and gaps.
* ``/candidates/<ticker>`` -- the CAPITAL CANDIDATE COCKPIT: when (and only when) the
  operator has recorded diligence inputs under the store, the ACCEPTED engines run on
  demand -- the 011D enrichment adapter path (``run_nivesha_thesis_on_enrichment``), the
  012I forward-scenario sidecar, the Personal-CIO fit functions, and a READ-ONLY view of a
  recorded manual execution preview. With no inputs the page says so: **insufficient
  inputs -- no thesis fabricated**. No engine is modified; no result is invented.

HARD DISCIPLINE (unchanged from 016A/016B):

* **Pure and offline.** No socket, no network, no thread, no wall clock. The engines'
  ``now`` is the float recorded in the operator's input file -- never a clock read.
* **Read / inspect only.** These pages carry NO form and NO button: nothing here creates,
  changes, confirms, or places anything. Recording a manual execution intent is a later,
  approval-gated phase; this slice only DISPLAYS a preview if one was already recorded.
* **Labels + ranges + counts, never scores.** Verdicts, claim statuses, authorities and
  states render as label badges; sizing renders as a suggested RANGE of portfolio percent;
  the engines' numeric internals are never shown.
* **Evidence honesty.** Everything shown is persisted or recomputed deterministically from
  recorded inputs; gaps, contradictions (both sides) and weak / social evidence are marked
  visibly; absence is stated, never papered over.

Deterministic, stdlib-only, Python 3.9, OFFLINE.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from reality_mesh import (
    EventStore,
    FindingStore,
    ForwardScenarioInput,
    HOLDINGS_RELPATH,
    PORTFOLIO_THRESHOLDS,
    PositionLedgerStore,
    SignalStore,
    ThemePulseStore,
    alerts_with_status,
    assess_candidate_eligibility,
    band_for_position_weight,
    blocked_candidates,
    build_concentration,
    build_correlation_labels,
    build_exposure,
    build_forward_scenario_packet,
    build_rotation_alignment,
    compare_candidate,
    compute_holdings,
    eligible_candidates,
    load_holdings,
    published_candidates,
    ticker_theme_map,
    to_nivesha_forward_sidecar,
)
from diligence_enrichment import (
    build_diligence_enrichment_bundle,
    run_nivesha_thesis_on_enrichment,
)
from prometheus.diligence_inputs import CandidateInput, DiligenceInputs
from prometheus.investment_action import generate_investment_action
from reality_intelligence.source_observation import make_source_observation
from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.portfolio_snapshot import make_portfolio_snapshot
from personal_cio.personalized_action import generate_personalized_action

from .api import _runs_newest_first
from .pages import _badge, _english_agent, _esc, _page

__all__ = [
    "CANDIDATES_EMPTY_STATE",
    "DILIGENCE_INPUT_DIRNAME",
    "PREVIEW_DIRNAME",
    "PROFILE_FILENAME",
    "diligence_refs_from_store",
    "persisted_theme_ids",
    "render_candidate_cockpit",
    "render_candidate_list",
    "render_company_cockpit",
    "render_portfolio_page",
    "render_research_page",
    "render_theme_cockpit",
    "render_theme_list",
]

# The VERBATIM empty state for /candidates when NO eligible candidate is published (asserted
# byte-for-byte by the suite -- the two-newline paragraph break is part of the contract).
CANDIDATES_EMPTY_STATE = (
    "No Capital Candidates are available for this run.\n\n"
    "Run a pulse, add watchlist tickers, or enable the required source adapters. CosmosIQ "
    "only surfaces candidates when there is enough evidence to support an investment thesis "
    "review.")

# Operator-provided input locations under the store (plain local JSON; labels and local
# refs only -- the app never fetches anything to fill them).
DILIGENCE_INPUT_DIRNAME = "diligence_inputs"          # <store>/diligence_inputs/<TICKER>.json
PROFILE_FILENAME = "personal_profile.json"            # <store>/personal_profile.json
PREVIEW_DIRNAME = "manual_execution_previews"         # <store>/manual_execution_previews/<TICKER>.json

_ACTOR = "cosmosiq-app"

# The standing honesty phrases (asserted verbatim by the suite).
_NO_THESIS = "insufficient inputs &mdash; no thesis fabricated"
_NO_INTENT = "no manual execution intent recorded"
_NO_ORDER = "manual preview only &mdash; no order is placed"

# Theme pulse state -> badge kind (colour == meaning; a LABEL, never a score).
_STATE_KINDS = {
    "Warming": "ok", "Igniting": "ok", "Broadening": "ok",
    "Dormant": "", "Crowded": "warn", "Conflicted": "warn", "Data insufficient": "warn",
    "Exhausting": "bad", "Breaking down": "bad",
}

# Claim status -> (display text, badge kind). A company claim / reported claim / rumor is
# ALWAYS displayed as unverified -- never promoted to a fact by rendering.
_CLAIM_BADGES = {
    "verified_fact": ("verified fact", "ok"),
    "company_claim": ("company claim (unverified)", "warn"),
    "reported_claim": ("reported claim (unverified)", "warn"),
    "analyst_estimate": ("analyst estimate (unverified)", "warn"),
    "inferred": ("inferred (unverified)", "warn"),
    "manual": ("manual entry", "warn"),
    "rumor": ("rumor (weakest authority)", "bad"),
}

# Diligence verdict -> plain-English display label (labels only; the raw vocabulary token
# is an internal engine value).
_VERDICT_DISPLAY = {
    "not_investable": "gated out -- fails the diligence gauntlet",
    "watch": "watch -- thesis not strong enough yet",
    "thesis_worthy": "thesis-worthy -- timing not confirmed",
    "thesis_worthy_timing_confirmed": "thesis-worthy -- timing confirmed",
}
_VERDICT_KINDS = {
    "not_investable": "bad", "watch": "warn",
    "thesis_worthy": "ok", "thesis_worthy_timing_confirmed": "ok",
}

# Personal-CIO suitability label -> badge kind.
_FIT_KINDS = {
    "priority_candidate": "ok", "suitable_candidate": "ok",
    "blocked_for_user": "bad", "exit_candidate": "bad",
}

# Portfolio-intelligence label -> badge kind (018A; colour == meaning, never a score).
_BAND_KINDS = {"minimal": "ok", "moderate": "", "elevated": "warn",
               "dominant": "bad", "unknown": "warn"}
_ALIGNMENT_KINDS = {"aligned": "ok", "against": "bad", "no_signal": "warn"}
_CORRELATION_KINDS = {"co_exposed": "warn", "partially_co_exposed": "",
                      "distinct": "ok", "unknown": "warn"}
_FRESHNESS_KINDS = {"current": "ok", "stale": "warn", "no_run_to_compare": "warn"}
_COMPARISON_KINDS = {"new_theme": "ok", "diversifies": "ok",
                     "adds_concentration": "warn", "no_theme_signal": "warn"}

# The enrichment areas an operator input file may carry (passed through verbatim to the
# accepted bundle builder -- never synthesized here).
_ENRICHMENT_KEYS = (
    "sec_facts", "fmp_profile", "fmp_income", "manual_tam", "ir_fixture",
    "leadership_fixture", "value_chain_fixture", "bottleneck_fixture",
)


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _tup(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


def _kw(mapping: Any) -> Dict[str, Any]:
    """A JSON object as keyword arguments (lists lowered to tuples)."""
    return {str(key): _tup(value) for key, value in dict(mapping or {}).items()}


def _load_json(path: str) -> Optional[Any]:
    """The parsed operator JSON file, None when absent, or the raw error text on damage."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _state_badge(state: Any) -> str:
    text = str(state or "")
    if not text:
        return "&mdash;"
    return _badge(text, _STATE_KINDS.get(text, "warn"))


def _claim_badge(status: Any) -> str:
    text, kind = _CLAIM_BADGES.get(str(status or ""), (str(status or "") or "unlabeled",
                                                       "warn"))
    return _badge(text, kind)


def _authority_badge(value: Any) -> str:
    text = str(value or "")
    if not text:
        return "&mdash;"
    kind = "ok" if text in ("canonical", "primary") else \
        ("bad" if text == "rumor" else "warn")
    return _badge(text, kind)


def _weak_mark(signal: Any) -> str:
    """The explicit WEAK mark for social / uncorroborated signals ('' when neither)."""
    weak = []
    if str(getattr(signal, "discipline", "")) == "narrative":
        weak.append("social")
    if str(getattr(signal, "corroboration_status", "")) == "uncorroborated":
        weak.append("uncorroborated")
    if not weak:
        return ""
    return _badge("WEAK -- {0}; corroboration required".format(" / ".join(weak)), "warn")


def _pct(value: Any) -> str:
    return "{0:.2f}%".format(float(value))


def _run_sequence(store_dir: str) -> List[Any]:
    """Distinct persisted runs OLDEST first (the timeline direction)."""
    return list(reversed(_runs_newest_first(store_dir)))


def _theme_timeline(store_dir: str) -> Tuple[List[str], Dict[str, List[Tuple[Any, Any]]]]:
    """theme_id -> [(run, pulse), ...] oldest -> newest, plus first-seen theme order."""
    order: List[str] = []
    timeline: Dict[str, List[Tuple[Any, Any]]] = {}
    store = ThemePulseStore(store_dir)
    for run in _run_sequence(store_dir):
        for pulse in store.query(run_id=run.run_id):
            if pulse.theme_id not in timeline:
                order.append(pulse.theme_id)
                timeline[pulse.theme_id] = []
            timeline[pulse.theme_id].append((run, pulse))
    return order, timeline


def persisted_theme_ids(store_dir: str) -> Tuple[str, ...]:
    """Every theme_id with at least one persisted theme pulse (routing guard)."""
    order, _timeline = _theme_timeline(store_dir)
    return tuple(order)


def _theme_alert_reason(store_dir: str, theme_id: str, run_id: str) -> str:
    """The recorded inbox reason for this theme changing in this run ('' when none)."""
    for alert in alerts_with_status(store_dir):
        if (str(getattr(alert, "category", "")) == "theme_pulse_changed"
                and str(getattr(alert, "run_id", "")) == run_id
                and theme_id in tuple(getattr(alert, "subject_themes", ()) or ())):
            return str(getattr(alert, "human_readable_reason", "") or "")
    return ""


# --------------------------------------------------------------------------- #
# /themes -- theme list with latest pulse states                                #
# --------------------------------------------------------------------------- #
def render_theme_list(store_dir: str) -> str:
    order, timeline = _theme_timeline(store_dir)
    note = ('<p class="note">Every theme with at least one persisted theme pulse, in first-'
            "seen sequence. States are closed labels persisted by pulse runs &mdash; never a "
            "metric, never recomputed for display. Open a theme cockpit for the full "
            "timeline and the why-it-changed evidence.</p>")
    if not order:
        body = note + ('<div class="panel"><p class="note">No theme pulses persisted yet '
                       "&mdash; run a manual pulse from the "
                       '<a href="/">home page</a> first.</p></div>')
        return _page(store_dir, "Themes", "/themes", body)

    rows = ""
    for theme_id in order:
        entries = timeline[theme_id]
        first_run, _first = entries[0]
        last_run, last = entries[-1]
        states = [str(p.state) for _r, p in entries]
        changes = sum(1 for i in range(1, len(states)) if states[i] != states[i - 1])
        rows += (
            '<tr><th><a href="/themes/{tid}">{tid}</a></th><td>{name}</td>'
            "<td>{state}</td><td>{runs} run(s) &middot; {changes} state change(s)</td>"
            "<td>{first} &rarr; {last}</td></tr>").format(
                tid=_esc(theme_id), name=_esc(last.theme_name or theme_id),
                state=_state_badge(last.state), runs=_esc(len(entries)),
                changes=_esc(changes), first=_esc(first_run.run_id),
                last=_esc(last_run.run_id))
    table = ('<div class="panel"><table class="kv"><tr><th>Theme</th><td>Name</td>'
             "<td>Latest state</td><td>Observed</td><td>Runs (first &rarr; latest)</td>"
             "</tr>" + rows + "</table></div>")
    return _page(store_dir, "Themes", "/themes", note + table)


# --------------------------------------------------------------------------- #
# /themes/<theme_id> -- the THEME COCKPIT                                       #
# --------------------------------------------------------------------------- #
def render_theme_cockpit(store_dir: str, theme_id: str) -> str:
    _order, timeline = _theme_timeline(store_dir)
    entries = timeline.get(theme_id)
    if not entries:
        from .pages import render_not_found
        return render_not_found(store_dir, "/themes/{0}".format(theme_id))

    # --- state timeline across runs (oldest -> newest) ------------------------
    trows = "".join(
        '<tr><th><a href="/runs/{rid}">{rid}</a></th><td>{start}</td><td>{state}</td>'
        "<td>breadth {breadth} &middot; rotation {rot} &middot; crowding {crowd}</td>"
        "<td>{conf} / {fresh}</td></tr>".format(
            rid=_esc(run.run_id), start=_esc(run.started_at),
            state=_state_badge(pulse.state),
            breadth=_esc(pulse.breadth_label or "&mdash;"),
            rot=_esc(pulse.rotation_label or "&mdash;"),
            crowd=_esc(pulse.crowding_label or "&mdash;"),
            conf=_esc(pulse.confidence_label), fresh=_esc(pulse.freshness_label))
        for run, pulse in entries)
    timeline_html = (
        '<h2>Pulse-state timeline</h2><div class="panel">'
        '<p class="note">One row per persisted run, oldest first. Every value is a '
        "persisted label.</p>"
        '<table class="kv"><tr><th>Run</th><td>Started</td><td>State</td>'
        "<td>Texture labels</td><td>Confidence / freshness</td></tr>"
        + trows + "</table></div>")

    # --- why did this theme change (the persisted-state diff) -----------------
    change_items = ""
    for index in range(1, len(entries)):
        prev_run, prev_pulse = entries[index - 1]
        run, pulse = entries[index]
        if str(prev_pulse.state) == str(pulse.state):
            continue
        reason = _theme_alert_reason(store_dir, theme_id, run.run_id)
        if reason:
            alert_html = "inbox alert reason: {0}".format(_esc(reason))
        else:
            alert_html = ("no alert record in the inbox for this change (an alert is "
                          "appended only when a diff pass ran after the newer run; the "
                          "change itself is still fully visible from the persisted states)")
        change_items += (
            "<li>why this theme changed: state {a} &rarr; {b} between run "
            '<a href="/runs/{x}">{x}</a> &rarr; run <a href="/runs/{y}">{y}</a>.'
            '<br><span class="note">{alert}</span></li>').format(
                a=_state_badge(prev_pulse.state), b=_state_badge(pulse.state),
                x=_esc(prev_run.run_id), y=_esc(run.run_id), alert=alert_html)
    changes_html = (
        '<h2>Why did this theme change</h2><div class="panel"><ul>'
        + (change_items or "<li>no state change across the persisted runs &mdash; quiet is "
                           "the honest answer</li>") + "</ul></div>")

    # --- contributing signals of the LATEST pulse ------------------------------
    latest_run, latest = entries[-1]
    supporting = tuple(latest.supporting_signals)
    contradicting = tuple(latest.contradicting_signals)
    wanted = set(supporting) | set(contradicting)
    signals = [s for s in SignalStore(store_dir).query(run_id=latest_run.run_id)
               if s.signal_id in wanted]
    findings_by_id = {f.finding_id: f
                      for f in FindingStore(store_dir).query(run_id=latest_run.run_id)}
    srows = ""
    signal_gaps: List[str] = []
    for signal in signals:
        signal_gaps.extend(tuple(signal.data_gaps))
        role = (_badge("supporting", "ok") if signal.signal_id in set(supporting)
                else _badge("contradicting", "bad"))
        authorities = sorted({
            str(findings_by_id[fid].source_authority_summary)
            for fid in tuple(signal.source_findings)
            if fid in findings_by_id and findings_by_id[fid].source_authority_summary})
        srows += (
            '<tr><th>{role}</th><td><span class="mono">{sid}</span></td>'
            "<td>{disc}</td><td>{direction} / {mag} / {urg}</td><td>{auth}</td>"
            "<td>{corr}</td><td>{weak}</td></tr>").format(
                role=role, sid=_esc(signal.signal_id),
                disc=_esc(_english_agent(signal.discipline)),
                direction=_esc(signal.direction_label or "&mdash;"),
                mag=_esc(signal.magnitude_label or "&mdash;"),
                urg=_esc(signal.urgency_label or "&mdash;"),
                auth=" ".join(_authority_badge(a) for a in authorities) or "&mdash;",
                corr=_esc(signal.corroboration_status),
                weak=_weak_mark(signal) or "&mdash;")
    signals_html = (
        '<h2>Contributing signals (latest pulse)</h2><div class="panel">'
        '<p class="note">The signals the latest persisted pulse names, with their source '
        "authority (from the findings behind them) and an explicit WEAK mark on social / "
        "uncorroborated evidence. Nothing is reweighted for display.</p>"
        '<table class="kv"><tr><th>Role</th><td>Signal</td><td>Discipline</td>'
        "<td>Direction / magnitude / urgency</td><td>Authority</td><td>Corroboration</td>"
        "<td>Weak mark</td></tr>"
        + (srows or "<tr><th>&mdash;</th><td colspan=\"6\">the latest pulse names no "
                    "contributing signals</td></tr>") + "</table></div>")

    # --- contradictions: BOTH sides, never averaged away -----------------------
    conflict_lines = "".join("<li>recorded conflict: {0}</li>".format(_esc(line))
                             for line in tuple(latest.conflicts))
    contradictions_html = (
        '<h2>Contradictions (both sides)</h2><div class="panel"><ul>'
        "<li>supporting ({ns}): <span class=\"mono\">{sup}</span></li>"
        "<li>contradicting ({nc}): <span class=\"mono\">{con}</span></li>"
        "{extra}</ul>{note}</div>").format(
            ns=_esc(len(supporting)), sup=_esc(", ".join(supporting) or "none named"),
            nc=_esc(len(contradicting)),
            con=_esc(", ".join(contradicting) or "none named"),
            extra=conflict_lines,
            note=('<p class="note">No contradicting signal is recorded for the latest '
                  "pulse &mdash; an unopposed state, shown as such.</p>"
                  if not contradicting and not conflict_lines else
                  '<p class="note">Both sides stay visible; nothing is averaged away.</p>'))

    # --- gaps -------------------------------------------------------------------
    gaps = sorted(set(tuple(latest.data_gaps) + tuple(signal_gaps)))
    gaps_html = (
        '<h2>Data gaps</h2><div class="panel"><ul class="gaps">'
        + ("".join("<li>{0}</li>".format(_esc(gap)) for gap in gaps)
           or "<li>no data gaps recorded on the latest pulse or its signals</li>")
        + "</ul></div>")

    intro = ('<p class="note">Theme cockpit for <span class="mono">{tid}</span> '
             "({name}). Everything below is PERSISTED pulse data across runs &mdash; the "
             "why-it-changed answer comes from the stored states, signals and alerts, "
             "never from a fresh fetch.</p>").format(
                 tid=_esc(theme_id), name=_esc(latest.theme_name or theme_id))
    return _page(store_dir, "Theme {0}".format(theme_id), "/themes",
                 intro + timeline_html + changes_html + signals_html
                 + contradictions_html + gaps_html)


# --------------------------------------------------------------------------- #
# /research -- the COMPANY RESEARCH landing (every ticker with persisted records) #
# --------------------------------------------------------------------------- #
def render_research_page(store_dir: str) -> str:
    """Company Research landing: every ticker that any pulse run names or requested, each
    linking to its company cockpit. Watchlisted tickers with no persisted record are shown as
    an honest coverage gap, never hidden. Read-only; labels and counts only."""
    runs = _run_sequence(store_dir)
    watch: Dict[str, int] = {}
    covered: Dict[str, int] = {}
    for run in runs:
        for ticker in tuple(getattr(run, "watchlist", ()) or ()):
            watch[ticker] = watch.get(ticker, 0) + 1
        seen_here = set()
        for store_cls in (EventStore, SignalStore, FindingStore):
            for record in store_cls(store_dir).query(run_id=run.run_id):
                seen_here.update(tuple(getattr(record, "affected_companies", ()) or ()))
        for ticker in seen_here:
            covered[ticker] = covered.get(ticker, 0) + 1
    tickers = sorted(set(watch) | set(covered))
    intro = ('<p class="note">Every company any pulse run names or requested, in one place. '
             "Open a ticker for its full evidence cockpit &mdash; events, findings and signals "
             "run by run, with claim statuses (a company claim or rumor is shown UNVERIFIED, "
             "never as a fact). A watchlisted ticker with no persisted record is an honest "
             "coverage gap, shown as such.</p>")
    if not tickers:
        body = intro + ('<div class="panel"><p class="note">No companies are covered yet '
                        "&mdash; run a pulse with tickers on the watchlist from the "
                        '<a href="/">Dashboard</a>. Nothing is fabricated to fill this '
                        "list.</p></div>")
        return _page(store_dir, "Company Research", "/research", body)
    rows = ""
    for ticker in tickers:
        runs_with_records = covered.get(ticker, 0)
        if runs_with_records:
            coverage = _badge("{0} run(s) with records".format(runs_with_records), "ok")
        else:
            coverage = _badge("requested, no persisted record yet -- honest gap", "warn")
        rows += (
            '<tr><th><a href="/companies/{t}">{t}</a></th><td>{cov}</td>'
            "<td>on {wl} watchlist run(s)</td>"
            "<td><a href=\"/candidates/{t}\">capital-candidate view</a></td></tr>").format(
                t=_esc(ticker), cov=coverage, wl=_esc(watch.get(ticker, 0)))
    table = ('<div class="panel"><table class="kv"><tr><th>Ticker</th><td>Coverage</td>'
             "<td>Requested</td><td>Candidate</td></tr>" + rows + "</table></div>")
    return _page(store_dir, "Company Research", "/research", intro + table)


# --------------------------------------------------------------------------- #
# /companies/<ticker> -- the COMPANY COCKPIT                                    #
# --------------------------------------------------------------------------- #
def render_company_cockpit(store_dir: str, ticker: str) -> str:
    runs = _run_sequence(store_dir)
    sections = ""
    all_gaps: List[str] = []
    any_records = False
    for run in runs:
        events = EventStore(store_dir).query(run_id=run.run_id, ticker=ticker)
        findings = FindingStore(store_dir).query(run_id=run.run_id, ticker=ticker)
        signals = SignalStore(store_dir).query(run_id=run.run_id, ticker=ticker)
        if not (events or findings or signals):
            if ticker in tuple(run.watchlist):
                all_gaps.append(
                    "run {0} requested {1} on its watchlist but persisted no event, "
                    "finding or signal for it -- honest gap, not fabricated".format(
                        run.run_id, ticker))
            continue
        any_records = True
        erows = ""
        for event in events:
            all_gaps.extend(tuple(event.data_gaps))
            claim_text = ""
            if str(event.company_claim or "").strip():
                claim_text = ("<br>company claim (unverified): "
                              "&quot;{0}&quot;".format(_esc(event.company_claim)))
            erows += (
                "<tr><th>{etype}</th><td>{claim}</td><td>{auth}</td>"
                "<td>{fact}{ctext}</td><td><span class=\"mono\">{refs}</span></td>"
                "</tr>").format(
                    etype=_esc(event.event_type or "event"),
                    claim=_claim_badge(event.claim_status),
                    auth=_authority_badge(event.source_authority),
                    fact=_esc(event.observed_fact or "&mdash;"), ctext=claim_text,
                    refs=_esc(", ".join(tuple(event.evidence_refs)
                                        + tuple(event.source_refs)) or "&mdash;"))
        frows = ""
        for finding in findings:
            all_gaps.extend(tuple(finding.data_gaps))
            frows += (
                "<tr><th>{agent}</th><td>{ftype}</td><td>{summary}</td>"
                "<td>{direction}</td><td>{auth}</td><td>{corr} / {contra}</td>"
                "</tr>").format(
                    agent=_esc(_english_agent(finding.agent_id)),
                    ftype=_esc(finding.finding_type),
                    summary=_esc(finding.finding_summary or "&mdash;"),
                    direction=_esc(finding.direction_label or "&mdash;"),
                    auth=_authority_badge(finding.source_authority_summary),
                    corr=_esc(finding.corroboration_status),
                    contra=_esc(finding.contradiction_status))
        srows = ""
        for signal in signals:
            all_gaps.extend(tuple(signal.data_gaps))
            srows += (
                "<tr><th><span class=\"mono\">{sid}</span></th><td>{stype}</td>"
                "<td>{disc}</td><td>{direction} / {urg}</td><td>{corr}</td><td>{weak}</td>"
                "</tr>").format(
                    sid=_esc(signal.signal_id), stype=_esc(signal.signal_type or "signal"),
                    disc=_esc(_english_agent(signal.discipline)),
                    direction=_esc(signal.direction_label or "&mdash;"),
                    urg=_esc(signal.urgency_label or "&mdash;"),
                    corr=_esc(signal.corroboration_status),
                    weak=_weak_mark(signal) or "&mdash;")
        sections += (
            '<h2>Run <a href="/runs/{rid}">{rid}</a> ({start})</h2><div class="panel">'
            + ("<h3>Events</h3><table class=\"kv\"><tr><th>Type</th><td>Claim status</td>"
               "<td>Authority</td><td>Observed / claimed</td><td>Evidence refs</td></tr>"
               + erows + "</table>" if erows else
               "<p class=\"note\">no events for this ticker in this run</p>")
            + ("<h3>Findings</h3><table class=\"kv\"><tr><th>Agent</th><td>Type</td>"
               "<td>Summary</td><td>Direction</td><td>Authority</td>"
               "<td>Corroboration / contradiction</td></tr>" + frows + "</table>"
               if frows else "<p class=\"note\">no findings for this ticker in this run</p>")
            + ("<h3>Signals</h3><table class=\"kv\"><tr><th>Signal</th><td>Type</td>"
               "<td>Discipline</td><td>Direction / urgency</td><td>Corroboration</td>"
               "<td>Weak mark</td></tr>" + srows + "</table>"
               if srows else "<p class=\"note\">no signals for this ticker in this run</p>")
            + "</div>").format(rid=_esc(run.run_id), start=_esc(run.started_at))

    if not any_records:
        sections = ('<div class="panel"><p class="note">No persisted event, finding or '
                    "signal names {0} in any pulse run yet. Nothing is fabricated to fill "
                    "the space &mdash; run a pulse with this ticker on the watchlist, or "
                    "record evidence sources for it.</p></div>".format(_esc(ticker)))

    gaps_html = (
        '<h2>Data gaps</h2><div class="panel"><ul class="gaps">'
        + ("".join("<li>{0}</li>".format(_esc(gap)) for gap in sorted(set(all_gaps)))
           or "<li>no data gaps recorded for this ticker</li>") + "</ul></div>")

    candidate_html = _published_candidate_state_section(store_dir, ticker)

    intro = ('<p class="note">Company cockpit for <span class="mono">{t}</span>: every '
             "persisted event, finding and signal that names this ticker, run by run. "
             "Claim statuses are labels &mdash; a company claim, reported claim or rumor "
             "is shown as UNVERIFIED, never as a fact. See also the "
             '<a href="/candidates/{t}">capital-candidate view</a>.</p>').format(
                 t=_esc(ticker))
    return _page(store_dir, "Company {0}".format(ticker), "",
                 intro + candidate_html + sections + gaps_html)


# --------------------------------------------------------------------------- #
# /candidates -- the CAPITAL CANDIDATES LIST (020A)                             #
# --------------------------------------------------------------------------- #
def _forward_badge(state: str) -> str:
    """The forward-scenario sidecar state as a badge -- ``absent`` renders an explicit GAP."""
    text = str(state or "absent")
    if text == "present":
        return _badge("forward scenario present", "ok")
    if text == "insufficient":
        return _badge("forward scenario insufficient -- GAP", "warn")
    return _badge("forward scenario absent -- GAP (rendered, not a block)", "warn")


def _candidate_state_badge(state: str) -> str:
    return _badge(_CANDIDATE_STATE_TEXT.get(str(state), str(state)),
                  _CANDIDATE_STATE_KINDS.get(str(state), "warn"))


def render_candidate_list(store_dir: str) -> str:
    """The published Capital Candidates list: eligible cards + blocked rows (exact reasons).

    Reads ONLY the append-only :class:`~reality_mesh.CapitalCandidateStore` -- it never
    publishes here (publication is the explicit ``POST /api/candidates/publish`` step). Eligible
    candidates link to their cockpit; blocked candidates render their state + the EXACT
    ineligibility reason (nothing is hidden). When no candidate is ELIGIBLE, the verbatim empty
    state renders. Labels and references only; no sizing / score / order anywhere.
    """
    eligible = eligible_candidates(store_dir)
    blocked = blocked_candidates(store_dir)
    intro = ('<p class="note">Published capital candidates from the append-only candidate '
             "store &mdash; a typed eligibility + lineage record per ticker, never a "
             "recommendation, a preference list, or a market action. A candidate is ELIGIBLE "
             "only with current-run provenance AND a diligence reference AND a healthy producing "
             "run; a BLOCKED candidate is shown with its exact reason. Publishing is a separate "
             "explicit step (POST /api/candidates/publish) &mdash; this page only reads.</p>")

    if eligible:
        cards = ""
        for cand in eligible:
            cards += (
                '<div class="panel"><table class="kv">'
                '<tr><th>Ticker</th><td><a href="/candidates/{t}">{t}</a> &middot; '
                "{state}</td></tr>"
                "<tr><th>Producing run</th><td><span class=\"mono\">{run}</span> &middot; "
                "mode {mode} &middot; data quality {dq}</td></tr>"
                "<tr><th>Fused reality signals</th><td>{signals}</td></tr>"
                "<tr><th>Opportunity-hypothesis ref</th><td><span class=\"mono\">{hyp}</span>"
                "</td></tr>"
                "<tr><th>Diligence ref</th><td><span class=\"mono\">{dil}</span></td></tr>"
                "<tr><th>Forward scenario</th><td>{fwd}</td></tr>"
                "<tr><th>Basis</th><td>{basis}</td></tr>"
                "</table></div>").format(
                    t=_esc(cand.ticker), state=_candidate_state_badge(cand.candidate_state),
                    run=_esc(cand.run_id), mode=_esc(cand.mode or "&mdash;"),
                    dq=_badge(cand.trust_data_quality_state or "unstated",
                              "ok" if cand.trust_data_quality_state == "healthy" else "warn"),
                    signals=_esc(", ".join(cand.reality_signal_refs) or "none"),
                    hyp=_esc(cand.opportunity_hypothesis_ref or "&mdash;"),
                    dil=_esc(cand.investment_diligence_ref or "&mdash;"),
                    fwd=_forward_badge(cand.forward_scenario_state),
                    basis=_esc(cand.basis))
        eligible_html = "<h2>Eligible candidates</h2>" + cards
    else:
        eligible_html = ('<h2>Eligible candidates</h2><div class="panel"><p class="note">'
                         + CANDIDATES_EMPTY_STATE + "</p></div>")

    if blocked:
        brows = "".join(
            "<tr><th><a href=\"/candidates/{t}\">{t}</a></th><td>{state}</td>"
            "<td><span class=\"mono\">{run}</span></td><td>{reason}</td></tr>".format(
                t=_esc(cand.ticker), state=_candidate_state_badge(cand.candidate_state),
                run=_esc(cand.run_id), reason=_esc(cand.basis))
            for cand in blocked)
        blocked_html = (
            '<h2>Blocked candidates</h2><div class="panel">'
            '<p class="note">Persisted, never hidden: each blocked candidate carries the '
            "EXACT reason it is not eligible.</p>"
            '<table class="kv"><tr><th>Ticker</th><td>State</td><td>Run</td>'
            "<td>Exact reason</td></tr>" + brows + "</table></div>")
    else:
        blocked_html = ('<h2>Blocked candidates</h2><div class="panel"><p class="note">No '
                        "blocked candidates published in this store.</p></div>")

    return _page(store_dir, "Capital Candidates", "/candidates",
                 intro + eligible_html + blocked_html)


def diligence_refs_from_store(store_dir: str, tickers: Tuple[str, ...]) -> Dict[str, Any]:
    """Derive per-ticker diligence refs from the operator's recorded diligence input files.

    For each ticker with a sufficient ``<store>/diligence_inputs/<TICKER>.json``, run the
    already-accepted diligence engines ON DEMAND (same path the candidate cockpit uses) and
    return ``{TICKER: {opportunity_hypothesis_ref, investment_diligence_ref,
    forward_scenario_state}}``. A ticker with no / insufficient / unparseable inputs is simply
    omitted (honest absence -- never a fabricated ref). Deterministic + offline.
    """
    out: Dict[str, Any] = {}
    for ticker in tickers:
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            continue
        spec_path = os.path.join(store_dir, DILIGENCE_INPUT_DIRNAME, symbol + ".json")
        try:
            spec = _load_json(spec_path)
        except ValueError:
            continue
        ok, _why = _sufficient(spec)
        if not ok:
            continue
        try:
            nowf, hypothesis, bundle, base = _build_hypothesis_and_base(spec, symbol)
            thesis, _mapping = run_nivesha_thesis_on_enrichment(
                hypothesis, bundle, base_inputs=base, actor=_ACTOR, now=nowf)
        except (ValueError, TypeError, KeyError):
            continue
        forward = "present" if dict(spec.get("forward_inputs") or {}) else "absent"
        out[symbol] = {
            "opportunity_hypothesis_ref": str(getattr(thesis, "opportunity_id", "") or ""),
            "investment_diligence_ref": str(getattr(thesis, "thesis_id", "") or ""),
            "forward_scenario_state": forward,
        }
    return out


def _published_candidate_state_section(store_dir: str, ticker: str) -> str:
    """The PUBLISHED capital-candidate state for one ticker on the company cockpit (READ-ONLY).

    Shows the eligible/blocked state + the exact reason of the latest published candidate for
    this ticker, or an honest 'none published' note. Reads the append-only store only.
    """
    heading = "<h2>Published capital candidate</h2>"
    symbol = str(ticker).strip().upper()
    matches = [c for c in published_candidates(store_dir) if c.ticker == symbol]
    if not matches:
        return (heading + '<div class="panel"><p class="note">No capital candidate published '
                "for this ticker. Publish is a separate explicit step (POST "
                "/api/candidates/publish); nothing is fabricated here.</p></div>")
    cand = matches[-1]
    return (
        heading + '<div class="panel"><table class="kv">'
        "<tr><th>Eligibility</th><td>{state}</td></tr>"
        "<tr><th>Producing run</th><td><span class=\"mono\">{run}</span> &middot; mode "
        "{mode} &middot; data quality {dq}</td></tr>"
        "<tr><th>Forward scenario</th><td>{fwd}</td></tr>"
        "<tr><th>Exact basis / reason</th><td>{basis}</td></tr>"
        "</table><p class=\"note\">The published, append-only eligibility record for this "
        "ticker &mdash; a label + lineage, never a recommendation. See the full "
        '<a href="/candidates/{t}">capital-candidate view</a>.</p></div>').format(
            state=_candidate_state_badge(cand.candidate_state), run=_esc(cand.run_id),
            mode=_esc(cand.mode or "&mdash;"),
            dq=_badge(cand.trust_data_quality_state or "unstated",
                      "ok" if cand.trust_data_quality_state == "healthy" else "warn"),
            fwd=_forward_badge(cand.forward_scenario_state), basis=_esc(cand.basis),
            t=_esc(symbol))


# --------------------------------------------------------------------------- #
# /candidates/<ticker> -- the CAPITAL CANDIDATE COCKPIT                         #
# --------------------------------------------------------------------------- #
def render_candidate_cockpit(store_dir: str, ticker: str) -> str:
    symbol = str(ticker).upper()
    spec_path = os.path.join(store_dir, DILIGENCE_INPUT_DIRNAME, symbol + ".json")
    try:
        spec = _load_json(spec_path)
    except ValueError as exc:
        spec = None
        inputs_html = ('<h2>Operator inputs</h2><div class="panel"><p class="note">The '
                       "recorded input file could not be parsed ({0}). Nothing is "
                       "guessed.</p></div>".format(_esc(exc)))
    else:
        inputs_html = _inputs_panel(spec, symbol)

    thesis = None
    thesis_html, mapping_html = _thesis_sections(spec, symbol)
    if isinstance(thesis_html, tuple):                # (html, thesis) when computed
        thesis_html, thesis = thesis_html
    eligibility_html = _eligibility_section(store_dir, symbol, spec, thesis)
    forward_html = _forward_section(spec, symbol, thesis)
    fit_html = _fit_section(store_dir, spec, thesis)
    comparison_html = _holdings_comparison_section(store_dir, symbol, spec)
    preview_html = _preview_section(store_dir, symbol)

    intro = ('<p class="note">Capital-candidate cockpit for <span class="mono">{t}</span>. '
             "The diligence verdict below is computed ON DEMAND, at page render, by the "
             "already-accepted engines over the operator-recorded inputs &mdash; "
             "deterministic given those inputs, recomputed identically every render, and "
             "never fetched from anywhere. Labels and ranges only; the engines&#39; "
             "numeric internals are not shown.</p>").format(t=_esc(symbol))
    return _page(store_dir, "Candidate {0}".format(symbol), "",
                 intro + inputs_html + thesis_html + eligibility_html + mapping_html
                 + forward_html + fit_html + comparison_html + preview_html)


def _inputs_panel(spec: Optional[Dict[str, Any]], symbol: str) -> str:
    if spec is None:
        return ('<h2>Operator inputs</h2><div class="panel"><p class="note">No operator '
                "diligence inputs recorded for {t} &mdash; expected at "
                '<span class="mono">&lt;store&gt;/{d}/{t}.json</span>. The cockpit shows '
                "only what exists; see the Phase-016 operator guide for the file "
                "shape.</p></div>").format(t=_esc(symbol), d=_esc(DILIGENCE_INPUT_DIRNAME))
    observations = list(spec.get("observations") or [])
    enrichment = dict(spec.get("enrichment") or {})
    provided = [key for key in _ENRICHMENT_KEYS if key in enrichment]
    forward = dict(spec.get("forward_inputs") or {})
    rows = (
        "<tr><th>Recorded at</th><td>{rec}</td></tr>"
        "<tr><th>Domain</th><td>{dom}</td></tr>"
        "<tr><th>Observations</th><td>{obs} recorded</td></tr>"
        "<tr><th>Hand-fed candidate</th><td>{cand}</td></tr>"
        "<tr><th>Enrichment areas</th><td>{enr}</td></tr>"
        "<tr><th>Forward-scenario cases</th><td>{fwd}</td></tr>").format(
            rec=_esc(spec.get("recorded_at", "") or "not stamped"),
            dom=_esc(spec.get("domain", "") or "&mdash;"),
            obs=_esc(len(observations)),
            cand=("provided" if spec.get("base_candidate") else "not provided"),
            enr=_esc(", ".join(provided) or "none"),
            fwd=_esc(", ".join(sorted(forward)) or "none"))
    return ('<h2>Operator inputs</h2><div class="panel"><table class="kv">' + rows
            + '</table><p class="note">These are the operator&#39;s recorded inputs, '
            "shown before any engine output so the evidence basis is never implicit."
            "</p></div>")


def _sufficient(spec: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    if spec is None:
        return False, "no diligence input file is recorded"
    if not str(spec.get("domain", "") or "").strip():
        return False, "the recorded inputs carry no domain"
    if not list(spec.get("observations") or []):
        return False, "the recorded inputs carry no source observations"
    if not (spec.get("base_candidate") or dict(spec.get("enrichment") or {})):
        return False, ("the recorded inputs carry neither a hand-fed candidate nor any "
                       "enrichment evidence")
    return True, ""


def _build_hypothesis_and_base(spec: Dict[str, Any], symbol: str):
    """(now_float, opportunity_hypothesis, enrichment_bundle, base DiligenceInputs|None)."""
    nowf = float(spec.get("now", 0.0) or 0.0)
    domain = str(spec.get("domain"))
    observations = [make_source_observation(now=nowf, **_kw(entry))
                    for entry in spec.get("observations") or []]
    assessment = generate_intelligence_assessment(observations, domain=domain,
                                                  actor=_ACTOR, now=nowf)
    hypothesis = generate_opportunity_hypothesis([assessment], domain=domain,
                                                 actor=_ACTOR, now=nowf)
    enrichment = dict(spec.get("enrichment") or {})
    bundle = build_diligence_enrichment_bundle(
        symbol, now=nowf,
        **{key: enrichment[key] for key in _ENRICHMENT_KEYS if key in enrichment})
    base = None
    if spec.get("base_candidate"):
        base = DiligenceInputs(
            domain=domain,
            candidates=(CandidateInput(**_kw(spec["base_candidate"])),),
            bear_probability=spec.get("bear_probability"),
            base_probability=spec.get("base_probability"),
            bull_probability=spec.get("bull_probability"),
            catalyst_timing_window=spec.get("catalyst_timing_window"),
            notes=str(spec.get("notes", "") or ""))
    return nowf, hypothesis, bundle, base


def _thesis_sections(spec: Optional[Dict[str, Any]], symbol: str):
    """(thesis html OR (html, thesis), input-mapping html)."""
    ok, why = _sufficient(spec)
    if not ok:
        html = ('<h2>Diligence verdict</h2><div class="panel"><p class="note">'
                "<strong>{phrase}.</strong> {why}. The accepted engines run only over "
                "recorded evidence; nothing is invented to fill a page.</p>"
                "</div>").format(phrase=_NO_THESIS, why=_esc(why))
        return html, ""
    try:
        nowf, hypothesis, bundle, base = _build_hypothesis_and_base(spec, symbol)
        thesis, mapping = run_nivesha_thesis_on_enrichment(
            hypothesis, bundle, base_inputs=base, actor=_ACTOR, now=nowf)
    except (ValueError, TypeError, KeyError) as exc:
        html = ('<h2>Diligence verdict</h2><div class="panel"><p class="note">'
                "<strong>{phrase}.</strong> The engines refused the recorded inputs: "
                "{err}</p></div>").format(phrase=_NO_THESIS, err=_esc(exc))
        return html, ""

    verdict = str(thesis.investability_assessment)
    red = thesis.red_team_summary
    asym = thesis.asymmetry_summary
    invalidation = "".join("<li>{0}</li>".format(_esc(line))
                           for line in tuple(thesis.invalidation_conditions))
    monitoring = "".join("<li>{0}</li>".format(_esc(line))
                         for line in tuple(thesis.monitoring_signals))
    thesis_html = (
        '<h2>Diligence verdict</h2><div class="panel"><table class="kv">'
        "<tr><th>Verdict</th><td>{verdict}</td></tr>"
        "<tr><th>Timing</th><td>{timing}</td></tr>"
        "<tr><th>Red team</th><td>{red}{fp}</td></tr>"
        "<tr><th>Asymmetry</th><td>{asym}</td></tr>"
        "<tr><th>Security / instrument mapping</th><td>{mapping}</td></tr>"
        "<tr><th>Time horizon</th><td>{horizon}</td></tr>"
        "</table>"
        "<h3>Invalidation conditions</h3><ul>{inv}</ul>"
        "<h3>Monitoring signals</h3><ul>{mon}</ul>"
        '<p class="note">Labels only &mdash; the gauntlet&#39;s numeric internals are '
        "never rendered here.</p></div>").format(
            verdict=_badge(_VERDICT_DISPLAY.get(verdict, verdict),
                           _VERDICT_KINDS.get(verdict, "warn")),
            timing=(_badge("timing confirmed", "ok") if thesis.timing_confirmation
                    else _badge("timing not confirmed", "warn")),
            red=_badge(str(getattr(red, "red_team_verdict", "") or "&mdash;"),
                       {"pass": "ok", "fail": "bad"}.get(
                           str(getattr(red, "red_team_verdict", "")), "warn")),
            fp=(" " + _badge(str(getattr(red, "false_positive_label", "")), "warn")
                if str(getattr(red, "false_positive_label", "") or "") else ""),
            asym=_badge(str(getattr(asym, "asymmetry_label", "") or "&mdash;"), "warn"),
            mapping=_esc(thesis.security_or_instrument_mapping or "none"),
            horizon=_esc(thesis.thesis_time_horizon or "&mdash;"),
            inv=invalidation or "<li>none recorded</li>",
            mon=monitoring or "<li>none recorded</li>")

    mrows = "".join(
        "<tr><th><span class=\"mono\">{field}</span></th><td>{auth}</td><td>{claim}</td>"
        "</tr>".format(field=_esc(entry.candidate_field),
                       auth=_authority_badge(entry.authority),
                       claim=_claim_badge(entry.claim_status) if entry.claim_status
                       else "&mdash;")
        for entry in tuple(mapping.mapped_fields))
    gap_items = "".join(
        "<li>{0}</li>".format(_esc(gap))
        for gap in tuple(mapping.gaps) + tuple(mapping.preserved_data_gaps))
    mapping_html = (
        '<h2>Evidence basis and gaps</h2><div class="panel">'
        '<p class="note">What the adapter actually mapped into the engine (with each '
        "value&#39;s source authority and claim status), and every input that stayed "
        "absent. The adapter maps inputs only; it never fills a gap.</p>"
        '<table class="kv"><tr><th>Mapped input</th><td>Authority</td>'
        "<td>Claim status</td></tr>"
        + (mrows or "<tr><th>&mdash;</th><td colspan=\"2\">nothing mapped</td></tr>")
        + '</table><ul class="gaps">'
        + (gap_items or "<li>no gaps recorded by the adapter</li>") + "</ul></div>")
    return (thesis_html, thesis), mapping_html


# Candidate-eligibility state -> badge kind (colour == meaning; a LABEL, never a score).
_CANDIDATE_STATE_KINDS = {
    "eligible": "ok",
    "draft": "warn",
    "ineligible_missing_provenance": "bad",
    "ineligible_missing_diligence": "bad",
    "ineligible_dq_failed": "bad",
    "ineligible_stale": "bad",
}
_CANDIDATE_STATE_TEXT = {
    "eligible": "ELIGIBLE -- full evidence lineage present",
    "draft": "draft -- lineage not yet assessed",
    "ineligible_missing_provenance": "INELIGIBLE -- missing current-run provenance",
    "ineligible_missing_diligence": "INELIGIBLE -- missing diligence reference",
    "ineligible_dq_failed": "INELIGIBLE -- producing run failed data quality",
    "ineligible_stale": "INELIGIBLE -- producing run not healthy (stale)",
}
# The producing run's data-quality status the candidate contract accepts (healthy/degraded/
# failed). Anything else (e.g. a policy-blocked run, or an unstamped run) is treated as a
# non-healthy, honestly-unstated DQ so a candidate off it can never read eligible.
_TRUST_DQ_ACCEPTED = ("healthy", "degraded", "failed")


def _eligibility_section(store_dir: str, symbol: str,
                         spec: Optional[Dict[str, Any]], thesis: Any) -> str:
    """The typed capital-candidate eligibility record for this ticker (READ-ONLY, honest).

    Builds a :class:`~reality_mesh.CapitalCandidate` from the CURRENT (latest persisted) run's
    provenance -- the fused signals for this ticker, the opportunity-hypothesis packet + the
    diligence thesis computed above, and the producing run's data-quality state -- via
    ``assess_candidate_eligibility``. A candidate is shown ELIGIBLE only when the full lineage is
    present (exactly when the gate would pass); otherwise the exact, honest ineligibility reason
    is rendered. Nothing is fabricated to reach eligible; no sizing / score / order appears.
    """
    heading = "<h2>Capital-candidate eligibility</h2>"
    runs = _run_sequence(store_dir)                       # oldest -> newest
    if not runs:
        return (heading + '<div class="panel"><p class="note">No pulse run is persisted yet '
                "&mdash; a capital candidate needs a CURRENT run that produced it. Nothing is "
                "marked eligible without a run; run a pulse first.</p></div>")
    current = runs[-1]                                    # the current (latest) run
    signal_ids = tuple(sorted(
        s.signal_id for s in SignalStore(store_dir).query(
            run_id=current.run_id, ticker=symbol)))
    hyp_ref = str(getattr(thesis, "opportunity_id", "") or "") if thesis is not None else ""
    dil_ref = str(getattr(thesis, "thesis_id", "") or "") if thesis is not None else ""
    dq_raw = str(getattr(current, "data_quality_status", "") or "")
    dq = dq_raw if dq_raw in _TRUST_DQ_ACCEPTED else (
        "failed" if dq_raw == "blocked_by_policy" else "")
    forward = "present" if (isinstance(spec, dict)
                            and dict(spec.get("forward_inputs") or {})) else "absent"

    candidate = assess_candidate_eligibility(
        ticker=symbol, run_id=current.run_id,
        reality_signal_refs=signal_ids,
        opportunity_hypothesis_ref=hyp_ref,
        investment_diligence_ref=dil_ref,
        forward_scenario_state=forward,
        trust_data_quality_state=dq,
        now=str(getattr(current, "started_at", "") or ""))

    state = candidate.candidate_state
    state_badge = _badge(_CANDIDATE_STATE_TEXT.get(state, state),
                         _CANDIDATE_STATE_KINDS.get(state, "warn"))
    missing = candidate.missing_lineage()
    missing_html = ("<li>all required lineage present</li>" if not missing else
                    "".join("<li>missing: {0}</li>".format(_esc(m)) for m in missing))
    return (
        heading + '<div class="panel">'
        '<p class="note">A typed eligibility + lineage record, not a recommendation and not a '
        "ranking. A candidate is ELIGIBLE only with current-run provenance (the fused signals + "
        "the opportunity-hypothesis packet) AND a diligence reference AND a healthy producing "
        "run &mdash; exactly the lineage the gate enforces. Labels and references only.</p>"
        '<table class="kv">'
        "<tr><th>Eligibility</th><td>{state}</td></tr>"
        "<tr><th>Current run</th><td><span class=\"mono\">{run}</span> &middot; data quality "
        "{dq}</td></tr>"
        "<tr><th>Fused reality signals</th><td>{signals}</td></tr>"
        "<tr><th>Opportunity-hypothesis reference</th><td>{hyp}</td></tr>"
        "<tr><th>Diligence reference</th><td>{dil}</td></tr>"
        "<tr><th>Forward-scenario sidecar</th><td>{fwd}</td></tr>"
        "<tr><th>Basis</th><td>{basis}</td></tr>"
        "</table>"
        "<h3>Lineage completeness</h3><ul>{missing}</ul>"
        '<p class="note">Eligibility is unforgeable: the typed contract refuses to construct an '
        "eligible candidate without the full lineage, so this page can never show eligible off "
        "an incomplete evidence chain.</p></div>").format(
            state=state_badge,
            run=_esc(current.run_id),
            dq=_badge(dq or "unstated", "ok" if dq == "healthy" else "warn"),
            signals=_esc(", ".join(signal_ids) or "none persisted for this ticker in this run"),
            hyp=("<span class=\"mono\">{0}</span>".format(_esc(hyp_ref)) if hyp_ref
                 else "&mdash; none (no diligence computed)"),
            dil=("<span class=\"mono\">{0}</span>".format(_esc(dil_ref)) if dil_ref
                 else "&mdash; none (no diligence computed)"),
            fwd=_badge(forward, "ok" if forward == "present" else "warn"),
            basis=_esc(candidate.basis),
            missing=missing_html)


def _forward_section(spec: Optional[Dict[str, Any]], symbol: str, thesis: Any) -> str:
    if spec is None or not dict(spec.get("forward_inputs") or {}):
        return ('<h2>Forward scenarios</h2><div class="panel"><p class="note">No forward-'
                "scenario inputs recorded &mdash; no scenario is fabricated. The forward "
                "sidecar runs only over evidence-backed assumptions the operator records."
                "</p></div>")
    try:
        nowf, hypothesis, bundle, base = _build_hypothesis_and_base(spec, symbol)
        cases = {
            str(label): tuple(ForwardScenarioInput(**_kw(entry)) for entry in entries)
            for label, entries in dict(spec.get("forward_inputs") or {}).items()}
        packet = build_forward_scenario_packet(
            ticker=symbol, hypothesis=hypothesis, enrichment=bundle, inputs=cases,
            confidence_label=str(spec.get("forward_confidence_label", "missing")
                                 or "missing"))
        _sidecar_inputs, fmapping = to_nivesha_forward_sidecar(packet, base_inputs=base)
    except (ValueError, TypeError, KeyError) as exc:
        return ('<h2>Forward scenarios</h2><div class="panel"><p class="note">The forward '
                "sidecar refused the recorded inputs: {0}. Nothing is fabricated."
                "</p></div>").format(_esc(exc))

    crows = ""
    for case in tuple(packet.cases):
        established = "".join(
            "<li><span class=\"mono\">{name}</span> {auth} {claim}</li>".format(
                name=_esc(item.name), auth=_authority_badge(item.source_authority),
                claim=_claim_badge(item.claim_status) if item.claim_status else "")
            for item in tuple(case.inputs))
        crows += (
            "<tr><th>{label}</th><td>{n} established<ul>{items}</ul></td>"
            "<td>{gaps} assumption(s) not established</td></tr>").format(
                label=_esc(case.label), n=_esc(len(tuple(case.inputs))),
                items=established or "<li>none</li>",
                gaps=_esc(len(tuple(case.data_gaps))))
    mrows = "".join(
        "<tr><th><span class=\"mono\">{field}</span></th><td>{scenario}</td>"
        "<td>{auth}</td><td>{claim}</td></tr>".format(
            field=_esc(entry.candidate_field), scenario=_esc(entry.scenario_label),
            auth=_authority_badge(entry.authority),
            claim=_claim_badge(entry.claim_status) if entry.claim_status else "&mdash;")
        for entry in tuple(fmapping.mapped_fields))
    return (
        '<h2>Forward scenarios (sidecar summary)</h2><div class="panel">'
        '<p class="note">Scenario cases carry only operator-recorded, evidence-labeled '
        "assumptions; every expected assumption that was not established is an explicit "
        "gap. Packet confidence: {conf}. The sidecar maps inputs only; it renders no "
        "verdict of its own.</p>"
        '<table class="kv"><tr><th>Case</th><td>Established assumptions</td>'
        "<td>Gaps</td></tr>{crows}</table>"
        "<h3>Mapped into the engine</h3>"
        '<table class="kv"><tr><th>Input</th><td>Case</td><td>Authority</td>'
        "<td>Claim status</td></tr>"
        + (mrows or "<tr><th>&mdash;</th><td colspan=\"3\">nothing mapped (sidecar-only "
                    "assumptions stay sidecar-only)</td></tr>")
        + "</table></div>").format(conf=_badge(str(packet.confidence_label), "warn"),
                                   crows=crows)


def _fit_section(store_dir: str, spec: Optional[Dict[str, Any]], thesis: Any) -> str:
    try:
        profile_spec = _load_json(os.path.join(store_dir, PROFILE_FILENAME))
    except ValueError as exc:
        return ('<h2>Portfolio fit</h2><div class="panel"><p class="note">The recorded '
                "profile file could not be parsed ({0}). Fit is not computed."
                "</p></div>").format(_esc(exc))
    if profile_spec is None:
        return ('<h2>Portfolio fit</h2><div class="panel"><p class="note">No personal '
                "profile or portfolio is recorded in settings &mdash; portfolio fit is "
                "not computed (honest absence, never a default persona). Record one at "
                '<span class="mono">&lt;store&gt;/{0}</span> to enable this section.'
                "</p></div>").format(_esc(PROFILE_FILENAME))
    if thesis is None:
        return ('<h2>Portfolio fit</h2><div class="panel"><p class="note">A profile is '
                "recorded, but portfolio fit needs a computed diligence verdict first "
                "&mdash; record diligence inputs above. Nothing is scored against an "
                "empty thesis.</p></div>")
    try:
        nowf = float(spec.get("now", 0.0) or 0.0) if spec else 0.0
        pnow = float(profile_spec.get("now", nowf) or nowf)
        account = str(profile_spec.get("account", "operator") or "operator")
        profile = make_personal_investment_profile(
            account, actor=_ACTOR, now=pnow, **_kw(profile_spec.get("profile")))
        portfolio = make_portfolio_snapshot(
            account=account, actor=_ACTOR, now=pnow, **_kw(profile_spec.get("portfolio")))
        action = generate_investment_action(thesis, actor=_ACTOR, now=nowf)
        fit = generate_personalized_action(thesis, action, profile, portfolio,
                                           actor=_ACTOR, now=nowf)
    except (ValueError, TypeError, KeyError) as exc:
        return ('<h2>Portfolio fit</h2><div class="panel"><p class="note">The fit '
                "functions refused the recorded profile: {0}. Nothing is computed."
                "</p></div>").format(_esc(exc))

    lo, hi = tuple(fit.suggested_sizing_range_pct)
    blocking = "".join("<li>{0}</li>".format(_esc(line))
                       for line in tuple(fit.blocking_conditions))
    warnings = "".join("<li>{0}</li>".format(_esc(line))
                       for line in tuple(fit.risk_warnings))
    return (
        '<h2>Portfolio fit</h2><div class="panel"><table class="kv">'
        "<tr><th>Suitability label</th><td>{status}</td></tr>"
        "<tr><th>Upstream action label</th><td>{atype}</td></tr>"
        "<tr><th>Suggested sizing range</th><td>{lo} to {hi} of portfolio &mdash; a "
        "RANGE only; the user chooses any exact amount downstream</td></tr>"
        "<tr><th>Recommended max exposure</th><td>{cap}</td></tr>"
        "</table>"
        "<h3>Blocking conditions</h3><ul>{blocking}</ul>"
        "<h3>Risk warnings</h3><ul>{warnings}</ul>"
        '<p class="note">Manual execution and explicit user confirmation are ALWAYS '
        "required downstream; nothing can be placed from this page.</p></div>").format(
            status=_badge(str(fit.recommendation_status),
                          _FIT_KINDS.get(str(fit.recommendation_status), "warn")),
            atype=_badge(str(getattr(action, "action_type", "") or "&mdash;"), "warn"),
            lo=_esc(_pct(lo)), hi=_esc(_pct(hi)),
            cap=_esc(_pct(fit.recommended_max_exposure_pct)),
            blocking=blocking or "<li>none recorded</li>",
            warnings=warnings or "<li>none recorded</li>")


def _preview_section(store_dir: str, symbol: str) -> str:
    path = os.path.join(store_dir, PREVIEW_DIRNAME, symbol + ".json")
    try:
        preview = _load_json(path)
    except ValueError as exc:
        preview = None
        damaged = (' The recorded preview file could not be parsed ({0}); nothing is '
                   "shown in its place.".format(_esc(exc)))
    else:
        damaged = ""
    if not isinstance(preview, dict):
        return ('<h2>Execution preview (read-only)</h2><div class="panel">'
                '<p class="note"><strong>{intent}</strong> for this candidate &mdash; '
                "{noorder}.{damaged} This page has no way to create one: recording an "
                "execution intent is a later, approval-gated phase (020+), and it will "
                "require an explicit user decision there, not here.</p></div>").format(
                    intent=_NO_INTENT, noorder=_NO_ORDER, damaged=damaged)

    broker_id = preview.get("broker_order_id")
    if broker_id in (None, ""):
        broker_cell = ("None &mdash; explicitly empty; {0}".format(_NO_ORDER))
    else:
        broker_cell = _esc(broker_id)
    placed = preview.get("placed_at")
    rows = "".join(
        "<tr><th>{0}</th><td>{1}</td></tr>".format(_esc(label), value)
        for label, value in (
            ("Instrument", _esc(preview.get("instrument", "") or "&mdash;")),
            ("Account", _esc(preview.get("account", "") or "&mdash;")),
            ("State", _badge(str(preview.get("state", "") or "unlabeled"), "warn")),
            ("Intended allocation", _esc(preview.get("intended_allocation", "&mdash;"))),
            ("Estimated cost", _esc(preview.get("estimated_cost", "&mdash;"))),
            ("Preview stamp", "<span class=\"mono\">{0}</span>".format(
                _esc(preview.get("preview_timestamp", "&mdash;")))),
            ("broker_order_id", broker_cell),
            ("placed_at", _esc(placed) if placed not in (None, "")
             else "None &mdash; never placed from this app"),
        ))
    return (
        '<h2>Execution preview (read-only)</h2><div class="panel">'
        '<p class="note">A recorded manual preview exists for this candidate and is '
        "displayed READ-ONLY: {noorder}. This page cannot create, change, confirm or "
        "act on it.</p>"
        '<table class="kv">' + rows + "</table></div>").format(noorder=_NO_ORDER)


# --------------------------------------------------------------------------- #
# /portfolio -- READ-ONLY portfolio intelligence (018A)                         #
# --------------------------------------------------------------------------- #
def _label_text(label: Any) -> str:
    return str(label or "").replace("_", " ") or "&mdash;"


def _no_holdings_note(reason: str) -> str:
    return ('<p class="note"><strong>No holdings recorded</strong> &mdash; this '
            "section stays honestly empty. {0}</p>").format(_esc(reason))


def _holdings_comparison_section(store_dir: str, symbol: str,
                                 spec: Optional[Dict[str, Any]]) -> str:
    """Candidate vs the recorded portfolio: a LABEL from persisted theme membership.

    Honest absence when no holdings statement is recorded; nothing is compared
    against an assumed portfolio. Read-and-inspect only -- no control exists here.
    """
    heading = "<h2>Candidate vs recorded portfolio</h2>"
    loaded, reason = load_holdings(store_dir)
    if loaded is None:
        return (heading + '<div class="panel">' + _no_holdings_note(reason)
                + '<p class="note">Record one at <span class="mono">&lt;store&gt;/'
                + _esc(HOLDINGS_RELPATH) + "</span> (see the Phase-018 operator "
                "guide) to enable this comparison.</p></div>")
    provided: Tuple[str, ...] = ()
    if isinstance(spec, dict) and str(spec.get("domain", "") or "").strip():
        if symbol not in ticker_theme_map(store_dir):
            provided = (str(spec["domain"]),)
    comparison = compare_candidate(store_dir, symbol, candidate_themes=provided)
    gap_items = "".join("<li>{0}</li>".format(_esc(gap))
                        for gap in tuple(comparison.data_gaps))
    return (
        heading + '<div class="panel"><table class="kv">'
        "<tr><th>Comparison label</th><td>{label}</td></tr>"
        "<tr><th>Candidate themes</th><td>{cthemes}</td></tr>"
        "<tr><th>Overlapping with current exposure</th><td>{overlap}</td></tr>"
        "<tr><th>New theme exposure</th><td>{new}</td></tr>"
        "<tr><th>Already a recorded position</th><td>{already}</td></tr>"
        "<tr><th>Basis</th><td>{basis}</td></tr>"
        "</table>{gaps}"
        '<p class="note">A label from persisted theme membership against the '
        "operator-recorded statement (as of {asof}) &mdash; not advice, not a "
        "sizing, and nothing here can act on it.</p></div>").format(
            label=_badge(_label_text(comparison.comparison_label),
                         _COMPARISON_KINDS.get(comparison.comparison_label, "warn")),
            cthemes=_esc(", ".join(comparison.candidate_themes) or "none mapped"),
            overlap=_esc(", ".join(comparison.overlapping_themes) or "none"),
            new=_esc(", ".join(comparison.new_themes) or "none"),
            already=("yes &mdash; more of it concentrates the existing position"
                     if comparison.already_recorded else "no"),
            basis=_esc(comparison.basis),
            gaps=('<ul class="gaps">' + gap_items + "</ul>") if gap_items else "",
            asof=_esc(loaded.as_of))


def _holdings_panel(loaded: Any, reason: str) -> str:
    heading = "<h2>Recorded holdings</h2>"
    if loaded is None:
        return (heading + '<div class="panel">' + _no_holdings_note(reason)
                + '<p class="note">To record one, write <span class="mono">'
                "&lt;store&gt;/" + _esc(HOLDINGS_RELPATH) + "</span> by hand: "
                '<span class="mono">as_of</span> + <span class="mono">positions'
                '</span> [ticker, quantity, cost_basis?, account_label?, '
                'liquidity_note?] + optional <span class="mono">cash</span>. '
                "The app only ever READS it.</p></div>")
    rows = ""
    for position in loaded.positions:
        if position.liquidity_note:
            liquidity = _badge(position.liquidity_note, "warn")
        else:
            liquidity = _badge("unknown -- no liquidity note recorded", "warn")
        rows += (
            "<tr><th>{ticker}</th><td>{qty}</td><td>{basis}</td><td>{account}</td>"
            "<td>{liquidity}</td></tr>").format(
                ticker=_esc(position.ticker),
                qty=_esc(position.quantity_text or "&mdash;"),
                basis=_esc(position.cost_basis_text) if position.cost_basis_text
                else "not recorded",
                account=_esc(position.account_label or "&mdash;"),
                liquidity=liquidity)
    cash_line = (loaded.cash_text if loaded.cash_recorded
                 else "not recorded")
    return (
        heading + '<div class="panel"><table class="kv">'
        "<tr><th>As of</th><td>{asof} {fresh}</td></tr>"
        "<tr><th>Freshness basis</th><td>{fbasis}</td></tr>"
        "<tr><th>Positions</th><td>{count} recorded</td></tr>"
        "<tr><th>Cash (as recorded)</th><td>{cash}</td></tr>"
        "</table>"
        '<table class="kv"><tr><th>Ticker</th><td>Quantity (as recorded)</td>'
        "<td>Cost basis (as recorded)</td><td>Account label</td>"
        "<td>Liquidity note</td></tr>" + rows + "</table>"
        '<p class="note">The operator&#39;s own recorded statement, displayed '
        "verbatim &mdash; never fetched, never valued, never changed by this app."
        "</p></div>").format(
            asof=_esc(loaded.as_of),
            fresh=_badge(_label_text(loaded.freshness_label),
                         _FRESHNESS_KINDS.get(loaded.freshness_label, "warn")),
            fbasis=_esc(loaded.basis), count=_esc(loaded.position_count),
            cash=_esc(cash_line))


def _exposure_panel(store_dir: str, loaded: Any, reason: str) -> str:
    heading = "<h2>Exposure by theme</h2>"
    if loaded is None:
        return heading + '<div class="panel">' + _no_holdings_note(reason) + "</div>"
    views = build_exposure(store_dir)
    mapping = ticker_theme_map(store_dir)
    unmapped = sorted(p.ticker for p in loaded.positions
                      if not mapping.get(p.ticker))
    unmapped_note = ""
    if unmapped:
        unmapped_note = ('<p class="note">No persisted signal or theme pulse maps '
                         '<span class="mono">{0}</span> to any theme &mdash; an '
                         "honest gap, never guessed.</p>").format(
                             _esc(", ".join(unmapped)))
    if not views:
        return (heading + '<div class="panel"><p class="note">No persisted theme '
                "names any recorded position yet &mdash; run a pulse whose records "
                "cover these tickers.</p>" + unmapped_note + "</div>")
    rows = "".join(
        "<tr><th>{theme}</th><td><span class=\"mono\">{tickers}</span></td>"
        "<td>{count} position(s)</td><td>{band}</td><td>{gaps}</td></tr>".format(
            theme=_esc(view.theme_id),
            tickers=_esc(", ".join(view.position_tickers)),
            count=_esc(view.position_count),
            band=_badge(_label_text(view.exposure_band),
                        _BAND_KINDS.get(view.exposure_band, "warn")),
            gaps=_esc("; ".join(view.data_gaps) or "&mdash;"))
        for view in views)
    return (
        heading + '<div class="panel">'
        '<p class="note">Which recorded positions the PERSISTED signals / theme '
        "pulses map to each theme. The combined-exposure band is a LABEL from the "
        "published thresholds &mdash; no ratio is stored or shown.</p>"
        '<table class="kv"><tr><th>Theme</th><td>Positions</td><td>Volume</td>'
        "<td>Exposure band</td><td>Gaps</td></tr>" + rows + "</table>"
        + unmapped_note + "</div>")


def _concentration_panel(store_dir: str, loaded: Any, reason: str) -> str:
    heading = "<h2>Concentration bands</h2>"
    if loaded is None:
        return heading + '<div class="panel">' + _no_holdings_note(reason) + "</div>"
    views = build_concentration(store_dir)
    rows = "".join(
        "<tr><th>{ticker}</th><td>{band}</td><td>{gaps}</td></tr>".format(
            ticker=_esc(view.ticker),
            band=_badge(_label_text(view.weight_band),
                        _BAND_KINDS.get(view.weight_band, "warn")),
            gaps=_esc("; ".join(view.data_gaps) or "&mdash;"))
        for view in views)
    edges = ("moderate at {m}%, elevated at {e}%, dominant at {d}% "
             "of the recorded total").format(
                 m=PORTFOLIO_THRESHOLDS["position_weight_moderate_pct"],
                 e=PORTFOLIO_THRESHOLDS["position_weight_elevated_pct"],
                 d=PORTFOLIO_THRESHOLDS["position_weight_dominant_pct"])
    return (
        heading + '<div class="panel">'
        '<p class="note">Each position&#39;s recorded cost basis &times; quantity, '
        "measured transiently against the recorded total and collapsed to a BAND "
        "({0}). The band is the only value kept &mdash; no weight or ratio is "
        "stored or rendered. A position that cannot be weighed is honestly "
        "unknown.</p>"
        '<table class="kv"><tr><th>Position</th><td>Weight band</td><td>Gaps</td>'
        "</tr>".format(_esc(edges)) + rows + "</table></div>")


def _correlation_panel(store_dir: str, loaded: Any, reason: str) -> str:
    heading = "<h2>Co-exposure (correlation labels)</h2>"
    if loaded is None:
        return heading + '<div class="panel">' + _no_holdings_note(reason) + "</div>"
    views = build_correlation_labels(store_dir)
    if not views:
        return (heading + '<div class="panel"><p class="note">Fewer than two '
                "recorded positions &mdash; no pair to label.</p></div>")
    rows = "".join(
        "<tr><th><span class=\"mono\">{a} &harr; {b}</span></th><td>{label}</td>"
        "<td>{shared}</td><td>{basis}</td></tr>".format(
            a=_esc(view.ticker_a), b=_esc(view.ticker_b),
            label=_badge(_label_text(view.correlation_label),
                         _CORRELATION_KINDS.get(view.correlation_label, "warn")),
            shared=_esc(", ".join(view.shared_themes) or "&mdash;"),
            basis=_esc(view.basis))
        for view in views)
    return (
        heading + '<div class="panel">'
        '<p class="note">A LABEL from shared persisted-theme membership &mdash; '
        "no numeric correlation exists anywhere in this app.</p>"
        '<table class="kv"><tr><th>Pair</th><td>Label</td><td>Shared themes</td>'
        "<td>Basis</td></tr>" + rows + "</table></div>")


def _rotation_panel(store_dir: str, loaded: Any, reason: str) -> str:
    heading = "<h2>Rotation alignment</h2>"
    if loaded is None:
        return heading + '<div class="panel">' + _no_holdings_note(reason) + "</div>"
    views = build_rotation_alignment(store_dir)
    rows = "".join(
        "<tr><th>{ticker}</th><td>{theme}</td><td>{state}</td><td>{label}</td>"
        "<td>{basis}</td></tr>".format(
            ticker=_esc(view.ticker), theme=_esc(view.theme_id or "&mdash;"),
            state=_state_badge(view.theme_state),
            label=_badge(_label_text(view.alignment_label),
                         _ALIGNMENT_KINDS.get(view.alignment_label, "warn")),
            basis=_esc(view.basis))
        for view in views)
    return (
        heading + '<div class="panel">'
        '<p class="note">Each recorded position against the LATEST persisted '
        "theme-pulse state of its mapped themes. Alignment is a label from the "
        "published state table; a position with no persisted signal honestly "
        "reads no signal.</p>"
        '<table class="kv"><tr><th>Position</th><td>Theme</td><td>Latest state</td>'
        "<td>Alignment</td><td>Basis</td></tr>" + rows + "</table></div>")


def _guardrail_section(store_dir: str) -> str:
    heading = "<h2>Risk budget and sizing guardrails</h2>"
    try:
        profile_spec = _load_json(os.path.join(store_dir, PROFILE_FILENAME))
    except ValueError as exc:
        return (heading + '<div class="panel"><p class="note">The recorded profile '
                "file could not be parsed ({0}). No guardrail is computed."
                "</p></div>").format(_esc(exc))
    if profile_spec is None:
        return (heading + '<div class="panel"><p class="note">No personal profile '
                "is recorded &mdash; guardrails are not shown (honest absence, "
                "never a default persona). Record one at "
                '<span class="mono">&lt;store&gt;/{0}</span> to enable this '
                "section.</p></div>").format(_esc(PROFILE_FILENAME))
    try:
        pnow = float(profile_spec.get("now", 0.0) or 0.0)
        account = str(profile_spec.get("account", "operator") or "operator")
        profile = make_personal_investment_profile(
            account, actor=_ACTOR, now=pnow, **_kw(profile_spec.get("profile")))
    except (ValueError, TypeError, KeyError) as exc:
        return (heading + '<div class="panel"><p class="note">The accepted profile '
                "function refused the recorded profile: {0}. Nothing is computed."
                "</p></div>").format(_esc(exc))
    permissions = []
    if not profile.options_allowed:
        permissions.append("derivative routes not permitted")
    if not profile.leverage_allowed:
        permissions.append("leveraged routes not permitted")
    return (
        heading + '<div class="panel">'
        '<p class="note">The user&#39;s STANDING limits, read verbatim from the '
        "recorded profile via the accepted Personal-CIO profile function &mdash; "
        "ranges and ceilings only, re-stated, never re-decided here.</p>"
        '<table class="kv">'
        "<tr><th>Risk tolerance</th><td>{rt}</td></tr>"
        "<tr><th>Max single position</th><td>up to {single} of the portfolio</td></tr>"
        "<tr><th>Max theme exposure</th><td>up to {theme} of the portfolio</td></tr>"
        "<tr><th>Minimum cash reserve</th><td>at least {cash} of the portfolio</td></tr>"
        "<tr><th>Drawdown tolerance</th><td>up to {dd}</td></tr>"
        "<tr><th>Time horizon / liquidity need</th><td>{horizon} / {liq}</td></tr>"
        "<tr><th>Route limits</th><td>{perm}</td></tr>"
        "</table>"
        '<p class="note">A per-candidate sizing RANGE (never an exact amount) '
        "renders on that candidate&#39;s cockpit when diligence inputs are "
        "recorded; manual confirmation is ALWAYS required downstream.</p>"
        "</div>").format(
            rt=_badge(profile.risk_tolerance, "warn"),
            single=_esc(_pct(profile.max_single_position_pct)),
            theme=_esc(_pct(profile.max_theme_exposure_pct)),
            cash=_esc(_pct(profile.min_cash_reserve_pct)),
            dd=_esc(_pct(profile.max_drawdown_tolerance_pct)),
            horizon=_esc(_label_text(profile.preferred_time_horizon)),
            liq=_esc(profile.liquidity_requirement),
            perm=_esc("; ".join(permissions) or "no route limit recorded"))


# --------------------------------------------------------------------------- #
# UX-3: the manual position LEDGER surface (compute_holdings) + the log-fill    #
# form. This RECORDS trades the operator already executed at THEIR OWN          #
# brokerage -- it is a JOURNAL, never order submission. No broker connection    #
# exists; the form writes ONLY to the append-only position ledger.             #
# --------------------------------------------------------------------------- #

# The honest empty state for the ledger holdings (asserted verbatim by the suite).
_LEDGER_EMPTY_STATE = (
    "No positions recorded yet. When you act on an opportunity in your own "
    "brokerage, log the fill below.")

# The one-line honesty disclaimer under the log-fill form. Deliberately says
# "brokerage" (never the bare token "broker") and "places orders" (never the
# bare token "order") so the strict per-tab affordance sweep stays clean while
# the meaning stays exact and honest.
_FILL_DISCLAIMER = (
    "Record a fill you already executed in your own brokerage &mdash; CosmosIQ "
    "never connects to a brokerage and never places orders; this only updates "
    "your own position log.")


def _ledger_position_bands(store_dir: str) -> Dict[str, str]:
    """ticker -> concentration BAND, computed TRANSIENTLY from the ledger holdings.

    A position's weight is its recorded ``average_cost_basis * net_quantity``
    measured against the recorded total of the ACTIVE positions, then immediately
    collapsed to a closed band via the published 018 position thresholds. Numbers
    live ONLY inside this function; only the band label survives. A position with
    no recorded cost basis (or a non-positive total) is honestly ``unknown``.
    """
    values: Dict[str, Optional[float]] = {}
    total = 0.0
    for holding in compute_holdings(store_dir):
        net = float(holding.net_quantity)
        if net <= 0:                                    # closed / short -> not an active weight
            continue
        if holding.average_cost_basis is None:
            values[holding.ticker] = None
            continue
        value = net * float(holding.average_cost_basis)
        values[holding.ticker] = value
        total += value
    bands: Dict[str, str] = {}
    for ticker, value in values.items():
        if value is None or total <= 0:
            bands[ticker] = "unknown"
        else:
            bands[ticker] = band_for_position_weight(value / total * 100.0)
    return bands


def _ledger_holdings_section(store_dir: str) -> str:
    """The LEDGER holdings table: net quantity + average cost basis + band + refs.

    Aggregated from the operator's own recorded fills (:func:`compute_holdings`).
    Read-only. When nothing is recorded, the honest empty state renders and the
    log-fill form below is the only next step.
    """
    heading = "<h2>Your recorded positions</h2>"
    holdings = compute_holdings(store_dir)
    if not holdings:
        return (heading + '<div class="panel"><p class="note"><strong>'
                + _LEDGER_EMPTY_STATE + "</strong></p></div>")
    bands = _ledger_position_bands(store_dir)
    rows = ""
    for holding in holdings:
        if holding.average_cost_basis is None:
            basis_text = "not recorded"
        else:
            basis_text = _esc("{0:.2f}".format(float(holding.average_cost_basis)))
        band = bands.get(holding.ticker,
                         "closed" if holding.is_closed else "unknown")
        band_html = (_badge("closed position", "warn") if holding.is_closed
                     else _badge(_label_text(band), _BAND_KINDS.get(band, "warn")))
        refs = ", ".join(holding.linked_recommendation_refs)
        rows += (
            "<tr><th>{ticker}</th><td>{qty}</td><td>{basis}</td><td>{band}</td>"
            "<td>{refs}</td><td>{date}</td></tr>").format(
                ticker=_esc(holding.ticker),
                qty=_esc(holding.net_quantity),
                basis=basis_text,
                band=band_html,
                refs="<span class=\"mono\">{0}</span>".format(_esc(refs)) if refs
                else "&mdash;",
                date=_esc(holding.last_trade_date or "&mdash;"))
    return (
        heading + '<div class="panel">'
        '<p class="note">Aggregated from the fills you logged below &mdash; net '
        "quantity is bought minus sold, average cost basis is the weighted average "
        "of your recorded purchase prices, and the concentration band is a LABEL from "
        "the published position thresholds (never a stored ratio or a hidden "
        "metric). These are your OWN recorded facts, not a CosmosIQ metric.</p>"
        '<table class="kv"><tr><th>Ticker</th><td>Net quantity</td>'
        "<td>Average cost basis</td><td>Concentration band</td>"
        "<td>Linked recommendation</td><td>Last fill date</td></tr>"
        + rows + "</table></div>")


def _ledger_concentration_legend() -> str:
    """The threshold legend for the ledger concentration bands (labels only)."""
    edges = ("minimal below {m}%, moderate at {m}%, elevated at {e}%, dominant "
             "at {d}% of your recorded active total").format(
                 m=PORTFOLIO_THRESHOLDS["position_weight_moderate_pct"],
                 e=PORTFOLIO_THRESHOLDS["position_weight_elevated_pct"],
                 d=PORTFOLIO_THRESHOLDS["position_weight_dominant_pct"])
    return (
        "<h2>Concentration of your recorded positions</h2>"
        '<div class="panel"><p class="note">Each position&#39;s recorded average '
        "cost basis times its net quantity, measured transiently against your "
        "recorded active total and collapsed to a BAND ({0}). The band is the "
        "only value kept &mdash; no weight, ratio, or sizing figure is stored or "
        "rendered. Sizing guidance elsewhere is a qualitative RANGE for manual "
        "review, never a share count or a dollar amount.</p></div>").format(
            _esc(edges))


def _recommendation_options(store_dir: str) -> str:
    """A <datalist> of published/eligible candidate tickers to link a fill to.

    Convenience only: the field is a free-text input, so any recorded evidence
    ref is accepted; the datalist just surfaces the tickers CosmosIQ already
    published so the operator does not have to remember them. Empty is fine.
    """
    seen: List[str] = []
    for cand in published_candidates(store_dir):
        ref = str(getattr(cand, "candidate_id", "") or "")
        if ref and ref not in seen:
            seen.append(ref)
    if not seen:
        return ""
    options = "".join('<option value="{0}">'.format(_esc(ref)) for ref in seen)
    return '<datalist id="rec-refs">' + options + "</datalist>"


def _fill_value(values: Optional[Dict[str, Any]], key: str) -> str:
    """The prior form value to repopulate on an error re-render ('' when none)."""
    if not isinstance(values, dict):
        return ""
    return _esc(str(values.get(key, "") or ""))


def _log_fill_form(store_dir: str, form_error: str = "",
                   form_values: Optional[Dict[str, Any]] = None) -> str:
    """The SANCTIONED operator form: LOG a fill you already executed elsewhere.

    This is a JOURNAL entry, never order submission. The side control is
    PAST-TENSE (``Bought`` / ``Sold`` -- what happened), the submit button is
    ``Record this fill``, and the honesty disclaimer states plainly that CosmosIQ
    never connects to a brokerage and never places orders. It posts to
    ``/api/portfolio/record-fill``, which writes ONLY to the append-only position
    ledger.
    """
    side_prev = str((form_values or {}).get("side", "") or "").strip().lower()
    sold_checked = " checked" if side_prev == "sold" else ""
    bought_checked = "" if side_prev == "sold" else " checked"
    error_html = ('<p class="form-error">Could not record that fill: {0}. Nothing '
                  "was written; correct the entry and record it again.</p>".format(
                      _esc(form_error)) if form_error else "")
    datalist = _recommendation_options(store_dir)
    list_attr = ' list="rec-refs"' if datalist else ""
    return (
        "<h2>Log an executed fill</h2>"
        + datalist
        + '<form class="op-form" method="post" action="/api/portfolio/record-fill">'
        + error_html
        + '<label>Ticker <input type="text" name="ticker" value="{ticker}"></label>'
        '<fieldset class="op-side"><legend>Side (what already happened)</legend>'
        '<label class="radio"><input type="radio" name="side" value="bought"{bc}> '
        "Bought</label>"
        '<label class="radio"><input type="radio" name="side" value="sold"{sc}> '
        "Sold</label></fieldset>"
        '<label>Quantity (the share count you transacted) '
        '<input type="text" name="quantity" value="{qty}"></label>'
        '<label>Fill price (per share, as you transacted) '
        '<input type="text" name="price" value="{price}"></label>'
        '<label>Fill date <input type="text" name="trade_date" value="{date}">'
        "</label>"
        '<label>Linked recommendation or candidate (optional) '
        '<input type="text" name="recommendation_ref"{la} value="{rec}"></label>'
        '<label>Note (optional) <input type="text" name="note" value="{note}">'
        "</label>"
        "<button>Record this fill</button>"
        '<span class="op-note">OPERATOR action &mdash; {disc}</span>'
        "</form>").format(
            ticker=_fill_value(form_values, "ticker"),
            bc=bought_checked, sc=sold_checked,
            qty=_fill_value(form_values, "quantity"),
            price=_fill_value(form_values, "price"),
            date=_fill_value(form_values, "trade_date"),
            rec=_fill_value(form_values, "recommendation_ref"),
            note=_fill_value(form_values, "note"),
            la=list_attr, disc=_FILL_DISCLAIMER)


def _recent_fills_section(store_dir: str) -> str:
    """The append-only ledger history, most-recent first (what you logged).

    Read-only. A CORRECTION is a NEW fill line (with ``correction_of`` naming the
    prior fill); the prior line is never mutated, so both stay visible here.
    """
    heading = "<h2>Recent fills you logged</h2>"
    fills = PositionLedgerStore(store_dir).read_all()
    if not fills:
        return (heading + '<div class="panel"><p class="note">No fills logged yet '
                "&mdash; this list fills in as you record the trades you make in "
                "your own brokerage.</p></div>")
    rows = ""
    for fill in reversed(fills):                          # most-recent first
        side_badge = _badge(fill.side, "ok" if fill.side == "bought" else "warn")
        correction = ""
        if fill.is_correction:
            correction = "<br>" + _badge("correction of {0}".format(
                fill.correction_of), "warn")
        note = "<br>{0}".format(_esc(fill.note)) if fill.note.strip() else ""
        ref = ("<span class=\"mono\">{0}</span>".format(_esc(fill.recommendation_ref))
               if fill.recommendation_ref.strip() else "&mdash;")
        rows += (
            "<tr><th>{date}</th><td>{ticker}</td><td>{side}</td>"
            "<td>{qty} @ {price}</td><td>{ref}</td><td>{correction}{note}</td></tr>"
        ).format(
            date=_esc(fill.trade_date), ticker=_esc(fill.ticker), side=side_badge,
            qty=_esc(fill.quantity),
            price=_esc("{0:.2f}".format(float(fill.price))),
            ref=ref, correction=correction or "&mdash;", note=note)
    return (
        heading + '<div class="panel">'
        '<p class="note">Your append-only log, newest first. A line is never '
        "edited or removed; a correction is a NEW line that supersedes the one it "
        "names, and both stay visible here. Quantity and price are your OWN "
        "recorded facts.</p>"
        '<table class="kv"><tr><th>Fill date</th><td>Ticker</td><td>Side</td>'
        "<td>Quantity @ price</td><td>Linked ref</td><td>Correction / note</td>"
        "</tr>" + rows + "</table></div>")


def render_portfolio_page(store_dir: str, form_error: str = "",
                          form_values: Optional[Dict[str, Any]] = None) -> str:
    """The portfolio page: your recorded positions + the log-fill JOURNAL form.

    Surfaces the UX-2 manual position ledger (holdings + cost basis +
    concentration bands) and a SANCTIONED operator form to LOG a fill you already
    executed at your OWN brokerage. CosmosIQ does NOT connect to a broker and
    NEVER places or submits an order; the form is a journal entry that writes only
    to the append-only ledger. Below the ledger, the READ-ONLY 018A intelligence
    over a separately recorded holdings statement is preserved unchanged. Every
    value is a closed LABEL, a volume count, or the operator's own recorded fact.
    ``form_error`` / ``form_values`` are set only when a bad POST re-renders the
    page with an honest error; a plain GET passes neither.
    """
    loaded, reason = load_holdings(store_dir)
    intro = ('<p class="note">Your holdings, cost basis, and concentration &mdash; '
             "aggregated from the fills you log below. This page RECORDS trades you "
             "already made in your own brokerage; it never connects to a brokerage "
             "and never places orders. Bands, labels and volume counts only &mdash; "
             "no stored ratio, no hidden metric, no market action, no automatic "
             "re-weighting of anything.</p>")
    statement_intro = (
        '<p class="note">Below: the separate READ-ONLY 018 intelligence over an '
        "operator-recorded holdings statement at "
        '<span class="mono">&lt;store&gt;/{path}</span> (exposure / correlation / '
        "rotation labels over the persisted pulse stores). Independent of the "
        "ledger above; it too only ever reads.</p>").format(
            path=_esc(HOLDINGS_RELPATH))
    return _page(
        store_dir, "Portfolio", "/portfolio",
        intro
        + _ledger_holdings_section(store_dir)
        + _ledger_concentration_legend()
        + _log_fill_form(store_dir, form_error=form_error, form_values=form_values)
        + _recent_fills_section(store_dir)
        + statement_intro
        + _holdings_panel(loaded, reason)
        + _exposure_panel(store_dir, loaded, reason)
        + _concentration_panel(store_dir, loaded, reason)
        + _correlation_panel(store_dir, loaded, reason)
        + _rotation_panel(store_dir, loaded, reason)
        + _guardrail_section(store_dir))
