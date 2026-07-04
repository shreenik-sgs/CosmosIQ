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
    SignalStore,
    ThemePulseStore,
    alerts_with_status,
    build_forward_scenario_packet,
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
    "DILIGENCE_INPUT_DIRNAME",
    "PREVIEW_DIRNAME",
    "PROFILE_FILENAME",
    "persisted_theme_ids",
    "render_candidate_cockpit",
    "render_company_cockpit",
    "render_theme_cockpit",
    "render_theme_list",
]

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

    intro = ('<p class="note">Company cockpit for <span class="mono">{t}</span>: every '
             "persisted event, finding and signal that names this ticker, run by run. "
             "Claim statuses are labels &mdash; a company claim, reported claim or rumor "
             "is shown as UNVERIFIED, never as a fact. See also the "
             '<a href="/candidates/{t}">capital-candidate view</a>.</p>').format(
                 t=_esc(ticker))
    return _page(store_dir, "Company {0}".format(ticker), "",
                 intro + sections + gaps_html)


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
    forward_html = _forward_section(spec, symbol, thesis)
    fit_html = _fit_section(store_dir, spec, thesis)
    preview_html = _preview_section(store_dir, symbol)

    intro = ('<p class="note">Capital-candidate cockpit for <span class="mono">{t}</span>. '
             "The diligence verdict below is computed ON DEMAND, at page render, by the "
             "already-accepted engines over the operator-recorded inputs &mdash; "
             "deterministic given those inputs, recomputed identically every render, and "
             "never fetched from anywhere. Labels and ranges only; the engines&#39; "
             "numeric internals are not shown.</p>").format(t=_esc(symbol))
    return _page(store_dir, "Candidate {0}".format(symbol), "",
                 intro + inputs_html + thesis_html + mapping_html + forward_html
                 + fit_html + preview_html)


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
