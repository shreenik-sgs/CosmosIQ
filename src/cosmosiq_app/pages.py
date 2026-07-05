"""The CosmosIQ app UI pages -- server-rendered HTML from PURE functions (IMPLEMENTATION-016B).

Each ``render_*(store_dir, ...)`` function below is a pure function from the Phase-013/015
append-only stores to ONE complete, self-contained HTML page. The pages are served by the
016A dispatcher (GET ``/``, ``/runs``, ``/runs/<id>``, ``/replay/<id>``, ``/alerts``,
``/settings``) and are fully testable offline through :func:`cosmosiq_app.api.dispatch`
alone -- no client-side fetch, no JavaScript, no external asset, no CDN, no remote font.

HARD DISCIPLINE (same as the dispatcher):

* **Pure.** No socket, no network, no thread, no wall clock -- every timestamp shown is a
  PERSISTED one; every page carries an honest "as of <persisted run time>" line and never
  claims to be anything but on-demand pulse data.
* **Labels + counts, never scores.** Severity / health / gate values render as label badges;
  volumes render as counts; no numeric quality metric is constructed anywhere.
* **NO trade affordance.** No route, form, button, or verb for placing, changing, or
  previewing a market transaction exists on any page. The ONLY forms are the explicit
  OPERATOR actions (acknowledge an alert, pause/resume a cadence policy, save settings,
  run a manual pulse) and each one says so in plain English.
* **Honesty surfaces.** Trigger attribution (manual / scheduled + policy), gate verdicts,
  agent health, data gaps and conflicts (both sides) are rendered VISIBLY -- degraded and
  failed states are never hidden, and a divergent replay is shown as a failure.
* **English layer terminology only** -- a legacy layer prefix inside a persisted agent id is
  normalized to its approved English value for display.

Deterministic, stdlib-only, Python 3.9, OFFLINE.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Tuple

from reality_mesh import (
    AgentRunLedger,
    DataQualityStore,
    EventStore,
    FindingStore,
    ReplayRequest,
    SignalStore,
    ThemePulseStore,
    alerts_with_status,
    latest_delivery_status,
    schedule_to_dict,
)
from reality_mesh import labels as _labels

from .api import (
    APP_NAME,
    _get_run,
    _handle_health,
    _harness,
    _load_schedule,
    _runs_newest_first,
    current_settings,
)
from .app_assets import APP_CSS

__all__ = [
    "CANVAS_DIRNAME",
    "CANVAS_PAGES",
    "SERVICE_HEALTH_FILENAME",
    "canvas_artifacts",
    "service_mode_indicator",
    "render_alert_inbox",
    "render_app_home",
    "render_not_found",
    "render_replay_view",
    "render_run_detail",
    "render_run_history",
    "render_settings_page",
]

# The 020C/020D service writes its sanitized health snapshot here; the product pages read the
# service MODE from it (if present) to render an honest mode indicator, else the safe OFF
# posture. Reading is best-effort and never fails a page render.
SERVICE_HEALTH_FILENAME = "service_health.json"

# The verbatim shadow-mode indicator (020D). Asserted by the suite; the {live} slot is the
# configured source status. In shadow the line NEVER says "Production 24x7".
_SHADOW_MODE_INDICATOR = (
    "Mode: SHADOW_24X7 · Live Data: {live} · Scheduler: On · "
    "Broker: Disabled · Execution: Manual Review Only · Alerts: Shadow Mode")

# The generated Universe Canvas artifacts the nav links to WHEN PRESENT (a note when absent
# -- never a dead link). The operator generates them with the pulse CLI into this directory
# under the store; names are fixed by the Universe UI page set (copied, never imported).
CANVAS_DIRNAME = "universe_canvas"
CANVAS_PAGES: Tuple[str, ...] = (
    "universe.html", "dashboard.html", "data_quality.html", "cockpit.html",
)

# A scheduled PulseRun carries its policy attribution in generated_outputs as this prefix
# (015B orchestrator convention -- read here for honest trigger attribution).
_POLICY_ATTRIBUTION_PREFIX = "scheduled_by_policy:"

# Health / gate labels -> badge kind (colour == meaning; a LABEL, never a score).
_GOOD = frozenset({"healthy", "success", "pass", "ok", "full", "present"})
_BAD = frozenset({"failed", "fail", "blocked_by_policy", "rate_limited",
                  "source_unavailable"})

# Alert severity label -> badge kind (a human-attention ladder, never a score).
_SEVERITY_KINDS = {"info": "ok", "notice": "warn", "warning": "bad", "critical": "bad"}

# Delivery status label -> badge kind + human phrasing (020E). A LABEL, never a score.
_DELIVERY_KINDS = {
    "delivered": "ok",
    "not_delivered": "warn",
    "suppressed_by_mode": "warn",
    "suppressed_by_policy": "warn",
    "failed_retryable": "bad",
    "failed_permanent": "bad",
}
_DELIVERY_DISPLAY = {
    "delivered": "delivered",
    "not_delivered": "not delivered",
    "suppressed_by_mode": "suppressed (mode)",
    "suppressed_by_policy": "suppressed (policy)",
    "failed_retryable": "failed (retryable)",
    "failed_permanent": "failed (permanent)",
}

# Display names for gate categories whose raw id would put a sensitive-looking token into
# the page (the page itself must stay free of credential-like and trade-like words).
_GATE_DISPLAY = {
    "security_secrets": "output hygiene (no sensitive value in output)",
    "scheduler_broker_trading_guardrail": "manual-only guardrail (no market connection)",
}


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _esc(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _badge(text: Any, kind: str = "") -> str:
    cls = "badge" + ((" " + kind) if kind else "")
    return '<span class="{0}">{1}</span>'.format(cls, _esc(text))


def _status_badge(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "&mdash;"
    if text in _BAD:
        return _badge(text, "bad")
    if text in _GOOD:
        return _badge(text, "ok")
    return _badge(text, "warn")   # degraded / partial / skipped / warn / stale / unknown ...


def _english_agent(agent_id: Any) -> str:
    """The agent id with any legacy layer prefix normalized to approved English."""
    text = str(agent_id or "")
    head, sep, tail = text.partition(".")
    if sep:
        return "{0}.{1}".format(_labels.normalize_layer(head), tail)
    return text


def _gate_display(category: Any) -> str:
    raw = str(category or "")
    return _GATE_DISPLAY.get(raw, raw.replace("_", " ") or "&mdash;")


def canvas_artifacts(store_dir: str) -> Tuple[str, ...]:
    """The generated Universe Canvas pages actually PRESENT under this store (may be empty)."""
    base = os.path.join(store_dir, CANVAS_DIRNAME)
    return tuple(name for name in CANVAS_PAGES
                 if os.path.isfile(os.path.join(base, name)))


def _trigger_text(run: Any) -> str:
    """Honest trigger attribution: manual (operator-run) or scheduled (+ which policy)."""
    trigger = str(getattr(run, "trigger_type", "") or "manual")
    policies = [entry[len(_POLICY_ATTRIBUTION_PREFIX):]
                for entry in tuple(getattr(run, "generated_outputs", ()) or ())
                if str(entry).startswith(_POLICY_ATTRIBUTION_PREFIX)]
    if trigger == "scheduled":
        return "scheduled &middot; policy {0}".format(_esc(", ".join(policies) or "(unattributed)"))
    return "manual &middot; operator-run"


def _run_gaps(store_dir: str, run_id: str) -> Tuple[str, ...]:
    """Every distinct persisted data-gap note for one run, across ALL its record stores
    (agent ledger + events + findings + signals + theme pulses) -- gaps stay visible."""
    gaps: List[str] = []
    for result in AgentRunLedger(store_dir).results_for_run(run_id):
        gaps.extend(tuple(getattr(result, "data_gaps", ()) or ()))
    for store_cls in (EventStore, FindingStore, SignalStore, ThemePulseStore):
        for record in store_cls(store_dir).query(run_id=run_id):
            gaps.extend(tuple(getattr(record, "data_gaps", ()) or ()))
    return tuple(sorted(set(gaps)))


def _coverage_notes(store_dir: str, run: Any) -> Tuple[str, ...]:
    """Requested watchlist tickers with NO persisted signal or event in this run.

    Derived purely from the stores: a requested ticker that nothing persisted covers is an
    honest coverage gap, surfaced -- never silently dropped and never fabricated.
    """
    covered = set()
    for store_cls in (SignalStore, EventStore):
        for record in store_cls(store_dir).query(run_id=run.run_id):
            covered.update(tuple(getattr(record, "affected_companies", ()) or ()))
    return tuple(
        "requested watchlist ticker {0} has no persisted signal or event in this run "
        "-- honest gap, not fabricated (a real source would be required)".format(ticker)
        for ticker in run.watchlist if ticker not in covered)


def _gate_overall(store_dir: str, run_id: str) -> str:
    overall = ""
    for record in DataQualityStore(store_dir).query(run_id=run_id):
        if record.category == "gate_overall":
            overall = record.status
    return overall


def _run_health(store_dir: str, run_id: str) -> str:
    """The worst per-agent health label persisted for one run ('' when no ledger rows)."""
    worst = ""
    ladder = {"healthy": 0, "degraded": 1, "failed": 2}
    for result in AgentRunLedger(store_dir).results_for_run(run_id):
        status = str(getattr(result, "health_status", "") or "")
        if ladder.get(status, -1) >= ladder.get(worst, -1):
            worst = status
    return worst


def _as_of_line(store_dir: str) -> str:
    """The honesty line every page carries: persisted run time + trigger, never a clock."""
    runs = _runs_newest_first(store_dir)
    if not runs:
        return ("as of &mdash; no persisted pulse yet &middot; data appears here only after "
                "an operator runs a manual pulse")
    run = runs[0]
    stamp = getattr(run, "completed_at", "") or getattr(run, "started_at", "")
    return ("as of {0} &middot; {1} pulse data &middot; persisted run {2} &middot; refreshed "
            "only when a pulse is run".format(
                _esc(stamp), _esc(getattr(run, "trigger_type", "") or "manual"),
                _esc(getattr(run, "run_id", ""))))


def _nav(store_dir: str, active: str) -> str:
    items = (("CosmosIQ", "/"), ("Runs", "/runs"), ("Themes", "/themes"),
             ("Capital Candidates", "/candidates"), ("Portfolio", "/portfolio"),
             ("Alerts", "/alerts"), ("Settings", "/settings"))
    html = ""
    for label, href in items:
        here = " here" if href == active else ""
        html += '<a class="navlink{0}" href="{1}">{2}</a>'.format(here, href, label)
    present = canvas_artifacts(store_dir)
    if present:
        for name in present:
            html += '<a class="navlink" href="/canvas/{0}">Canvas: {1}</a>'.format(
                _esc(name), _esc(name[:-len(".html")].replace("_", " ")))
    else:
        html += ('<span class="navnote">Universe Canvas: not generated in this store yet '
                 "&mdash; no link (generate with the pulse CLI into "
                 "&lt;store&gt;/{0}/)</span>".format(_esc(CANVAS_DIRNAME)))
    return html


def _service_health(store_dir: str) -> Dict[str, Any]:
    """The service's persisted health snapshot as a plain dict ({} if none / unreadable)."""
    path = os.path.join(store_dir, SERVICE_HEALTH_FILENAME)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return dict(data) if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _configured_source_status(health: Dict[str, Any]) -> str:
    """A LABEL for the configured live-source status, derived from the health summary.

    ``Source gap`` when the run recorded a failed source (a visible source gap -- never a
    fixture fall-back), ``On`` when coverage was recorded, else ``Off``. A label, never a score.
    """
    summary = dict(health.get("source_health_summary", {}) or {})
    try:
        failed = int(summary.get("failed_source_records", 0) or 0)
        coverage = int(summary.get("coverage_records", 0) or 0)
    except (TypeError, ValueError):
        failed, coverage = 0, 0
    if failed > 0:
        return "Source gap"
    return "On" if coverage > 0 else "Off"


def service_mode_indicator(store_dir: str) -> str:
    """The honest service-mode indicator for the product pages ('' when no service ran yet).

    Reads the service mode from ``<store>/service_health.json`` if present, else OFF. In SHADOW
    the verbatim shadow line renders (Broker Disabled, Execution Manual Review Only, Alerts
    Shadow Mode) and NEVER says "Production 24x7". When no health snapshot exists (the default,
    service-never-started posture) this returns '' so the page is byte-identical to 015C.
    """
    health = _service_health(store_dir)
    if not health:
        return ""                           # no service ran -> no indicator (safe OFF posture)
    mode = str(health.get("service_mode", "off") or "off").lower()
    if mode == "shadow_24x7":
        return _SHADOW_MODE_INDICATOR.format(live=_configured_source_status(health))
    scheduler = "Attended" if mode == "manual" else "Off"
    inbox = "Inbox" if mode == "manual" else "Off"
    return ("Mode: {mode} · Live Data: {live} · Scheduler: {sched} · Broker: Disabled · "
            "Execution: Manual Review Only · Alerts: {inbox}").format(
                mode=mode.upper(), live=_configured_source_status(health),
                sched=scheduler, inbox=inbox)


def _page(store_dir: str, title: str, active: str, body: str) -> str:
    """One complete self-contained page: inline CSS, honest strip, nav, body, footer."""
    indicator = service_mode_indicator(store_dir)
    mode_html = ('<span class="sep">&middot;</span><span class="mode-indicator">{0}</span>'
                 .format(indicator) if indicator else "")
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>{title} &middot; {app}</title><style>{css}</style></head><body>"
        '<div class="strip">{as_of}<span class="sep">&middot;</span>local operator app'
        '<span class="sep">&middot;</span>no market action can be taken here{mode}</div>'
        '<div class="bar"><span class="brand">{app}<small>economic intelligence &middot; '
        "local operator app</small></span>{nav}</div>"
        '<div class="wrap"><h1>{title}</h1>{body}'
        '<p class="foot">{app} &mdash; labels and volume counts only; append-only history; '
        "pulses run only when an operator (or an operator-journaled cadence policy) asks. "
        "Evidence and observability, nothing else.</p>"
        "</div></body></html>").format(
            title=_esc(title), app=_esc(APP_NAME), css=APP_CSS,
            as_of=_as_of_line(store_dir), nav=_nav(store_dir, active), body=body,
            mode=mode_html)


# --------------------------------------------------------------------------- #
# / -- app home                                                                 #
# --------------------------------------------------------------------------- #
def render_app_home(store_dir: str) -> str:
    counts = _handle_health(store_dir)["body"]["counts"]
    settings, revision = current_settings(store_dir)

    intro = (
        '<p class="note">{0} is a LOCAL operator app over append-only pulse stores: '
        "run history, replay verification, the alert inbox, and operator settings. "
        "Everything shown is a persisted label or a volume count &mdash; never a hidden "
        "metric, never a market action.</p>".format(_esc(APP_NAME)))

    rows = "".join(
        "<tr><th>{0}</th><td>{1}</td></tr>".format(_esc(name.replace("_", " ")), _esc(value))
        for name, value in sorted(counts.items()))
    rows += "<tr><th>settings revision</th><td>{0}</td></tr>".format(_esc(revision))
    store_html = ('<h2>Store status</h2><div class="panel"><table class="kv">' + rows
                  + "</table></div>")

    runs = _runs_newest_first(store_dir)
    if runs:
        run = runs[0]
        latest = (
            '<h2>Latest persisted run</h2><div class="panel"><table class="kv">'
            '<tr><th>Run</th><td><a href="/runs/{rid}">{rid}</a></td></tr>'
            "<tr><th>Started</th><td>{start}</td></tr>"
            "<tr><th>Trigger</th><td>{trig}</td></tr>"
            "<tr><th>Gate overall</th><td>{gate}</td></tr>"
            "<tr><th>Run health</th><td>{health}</td></tr>"
            "</table></div>").format(
                rid=_esc(run.run_id), start=_esc(run.started_at),
                trig=_trigger_text(run),
                gate=_status_badge(_gate_overall(store_dir, run.run_id)),
                health=_status_badge(_run_health(store_dir, run.run_id)))
    else:
        latest = ('<h2>Latest persisted run</h2><div class="panel"><p class="note">No '
                  "persisted runs yet &mdash; use the manual pulse form below to run the "
                  "first one.</p></div>")

    pulse_form = (
        '<h2>Run a pulse</h2><form class="op-form" method="post" action="/api/pulse">'
        '<label>Watchlist (comma-separated tickers) '
        '<input type="text" name="watchlist" value="{wl}"></label>'
        '<label>Themes (comma-separated) <input type="text" name="themes" value="{th}">'
        "</label><button>Run manual pulse</button>"
        '<span class="op-note">OPERATOR action &mdash; manual, on-demand; no scheduler '
        "started. Appends ONE new run to the append-only history; nothing repeats unless "
        "you ask again.</span></form>").format(
            wl=_esc(", ".join(str(v) for v in settings.get("watchlists", ())
                              if isinstance(v, str))),
            th=_esc(", ".join(str(v) for v in settings.get("themes", ())
                              if isinstance(v, str))))

    present = canvas_artifacts(store_dir)
    if present:
        links = "".join('<li><a href="/canvas/{0}">{0}</a></li>'.format(_esc(name))
                        for name in present)
        canvas = ('<h2>Universe Canvas</h2><div class="panel"><ul>' + links
                  + '</ul><p class="note">Generated artifacts found under this store '
                  "&mdash; served read-only.</p></div>")
    else:
        canvas = ('<h2>Universe Canvas</h2><div class="panel"><p class="note">No generated '
                  "Universe Canvas artifacts in this store yet, so nothing is linked "
                  "(never a dead link). Generate them with the pulse CLI into "
                  "&lt;store&gt;/{0}/ and they will appear here and in the nav."
                  "</p></div>".format(_esc(CANVAS_DIRNAME)))

    return _page(store_dir, "{0} home".format(APP_NAME), "/",
                 intro + store_html + latest + pulse_form + canvas)


# --------------------------------------------------------------------------- #
# /runs -- run-history browser                                                  #
# --------------------------------------------------------------------------- #
def render_run_history(store_dir: str) -> str:
    runs = _runs_newest_first(store_dir)
    note = ('<p class="note">Every persisted pulse run, newest first &mdash; with its honest '
            "trigger attribution, gate verdict, worst agent health, and data-gap count. "
            "Counts are volumes only; verdicts and health are labels only.</p>")
    if not runs:
        body = note + ('<div class="panel"><p class="note">No persisted runs yet &mdash; '
                       'run a manual pulse from the <a href="/">home page</a>.</p></div>')
        return _page(store_dir, "Run history", "/runs", body)

    rows = ""
    for run in runs:
        gaps = _run_gaps(store_dir, run.run_id)
        rows += (
            '<tr><th><a href="/runs/{rid}">{rid}</a></th><td>{start}</td><td>{trig}</td>'
            "<td>{gate}</td><td>{health}</td><td>{gaps} gap(s)</td>"
            "<td>events {ev} &middot; findings {fi} &middot; signals {si} &middot; "
            "theme pulses {tp}</td><td><a href=\"/replay/{rid}\">replay</a></td></tr>").format(
                rid=_esc(run.run_id), start=_esc(run.started_at),
                trig=_trigger_text(run),
                gate=_status_badge(_gate_overall(store_dir, run.run_id)),
                health=_status_badge(_run_health(store_dir, run.run_id)),
                gaps=_esc(len(gaps)), ev=_esc(run.events_created),
                fi=_esc(run.findings_created), si=_esc(run.signals_created),
                tp=_esc(run.theme_pulses_created))
    table = (
        '<div class="panel"><table class="kv"><tr><th>Run</th><td>Started</td>'
        "<td>Trigger</td><td>Gate overall</td><td>Worst agent health</td><td>Data gaps</td>"
        "<td>Volumes (counts)</td><td>Replay</td></tr>" + rows + "</table></div>")
    return _page(store_dir, "Run history", "/runs", note + table)


# --------------------------------------------------------------------------- #
# /runs/<id> -- run detail                                                      #
# --------------------------------------------------------------------------- #
def render_run_detail(store_dir: str, run_id: str) -> str:
    run = _get_run(store_dir, run_id)
    if run is None:
        return render_not_found(store_dir, "/runs/{0}".format(run_id))

    meta = (
        '<div class="panel"><table class="kv">'
        "<tr><th>Run</th><td>{rid}</td></tr>"
        "<tr><th>Mode</th><td>{mode}</td></tr>"
        "<tr><th>Trigger</th><td>{trig}</td></tr>"
        "<tr><th>Started / completed</th><td>{start} / {done}</td></tr>"
        "<tr><th>Watchlist</th><td>{wl}</td></tr>"
        "<tr><th>Themes</th><td>{th}</td></tr>"
        "<tr><th>Volumes (counts, not metrics)</th><td>events {ev} &middot; findings {fi} "
        "&middot; signals {si} &middot; theme pulses {tp}</td></tr>"
        "<tr><th>Schema / runtime version</th><td>{schema} / {rt}</td></tr>"
        "</table></div>").format(
            rid=_esc(run.run_id), mode=_esc(run.mode), trig=_trigger_text(run),
            start=_esc(run.started_at), done=_esc(run.completed_at),
            wl=_esc(", ".join(run.watchlist) or "&mdash;"),
            th=_esc(", ".join(run.themes) or "&mdash;"),
            ev=_esc(run.events_created), fi=_esc(run.findings_created),
            si=_esc(run.signals_created), tp=_esc(run.theme_pulses_created),
            schema=_esc(run.schema_version), rt=_esc(run.runtime_version))

    # Agent health: failed / degraded agents rendered VISIBLY; English layer terms only.
    results = AgentRunLedger(store_dir).results_for_run(run_id)
    arows = "".join(
        "<tr><th>{aid}</th><td>{status}</td><td>{health}</td><td>{gaps} gap(s)</td>"
        "<td>{conf} conflict(s)</td><td>{err} error(s) &middot; {warn} warning(s)</td>"
        "</tr>".format(
            aid=_esc(_english_agent(result.agent_id)),
            status=_status_badge(result.status),
            health=_status_badge(result.health_status),
            gaps=_esc(len(result.data_gaps)), conf=_esc(len(result.conflicts)),
            err=_esc(len(result.errors)), warn=_esc(len(result.warnings)))
        for result in results)
    agents = (
        '<h2>Agent health</h2><div class="panel"><table class="kv">'
        "<tr><th>Agent</th><td>Status</td><td>Health</td><td>Data gaps</td>"
        "<td>Conflicts</td><td>Errors / warnings</td></tr>"
        + (arows or "<tr><th>&mdash;</th><td colspan=\"5\">no agent ledger rows persisted "
                    "for this run</td></tr>") + "</table></div>")

    # Gate verdicts: per-category badges plus the overall roll-up, prominently.
    dq_records = DataQualityStore(store_dir).query(run_id=run_id)
    overall = _gate_overall(store_dir, run_id)
    grows = "".join(
        "<tr><th>{cat}</th><td>{status}</td><td>{summary}</td></tr>".format(
            cat=_gate_display(record.category), status=_status_badge(record.status),
            summary=_esc(record.summary or "&mdash;"))
        for record in dq_records if record.category != "gate_overall")
    gates = (
        '<h2>Data-quality gates</h2><div class="panel">'
        '<p class="note">Gate verdicts are labels (pass / warn / fail / degraded), never a '
        "metric. Overall: {0}</p>".format(_status_badge(overall))
        + '<table class="kv"><tr><th>Gate</th><td>Verdict</td><td>Summary</td></tr>'
        + (grows or "<tr><th>&mdash;</th><td colspan=\"2\">no gate records persisted for "
                    "this run</td></tr>") + "</table></div>")

    # Data gaps: always visible, never collapsed, never hidden -- persisted gap notes plus
    # store-derived coverage gaps (a requested ticker nothing covered).
    gaps = _run_gaps(store_dir, run_id) + _coverage_notes(store_dir, run)
    gaps_html = (
        '<h2>Data gaps</h2><div class="panel"><ul class="gaps">'
        + ("".join("<li>{0}</li>".format(_esc(gap)) for gap in sorted(set(gaps)))
           or "<li>no data gaps recorded in this run</li>") + "</ul></div>")

    # Conflicts: BOTH sides visible, never averaged away.
    conflict_items = ""
    for result in results:
        for conflict in tuple(getattr(result, "conflicts", ()) or ()):
            conflict_items += "<li>{0}: {1}</li>".format(
                _esc(_english_agent(result.agent_id)), _esc(conflict))
    for signal in SignalStore(store_dir).query(run_id=run_id):
        status = str(getattr(signal, "contradiction_status", "") or "")
        if "contradict" in status.lower():
            conflict_items += (
                "<li>signal {sid}: {badge} &mdash; direction &quot;{direction}&quot;; "
                "{notes} conflict note(s), both sides preserved</li>").format(
                    sid=_esc(signal.signal_id), badge=_badge("contradicted", "bad"),
                    direction=_esc(signal.direction_label),
                    notes=_esc(len(tuple(getattr(signal, "conflicts", ()) or ()))))
    for pulse in ThemePulseStore(store_dir).query(run_id=run_id):
        contradicting = tuple(getattr(pulse, "contradicting_signals", ()) or ())
        if contradicting:
            supporting = tuple(getattr(pulse, "supporting_signals", ()) or ())
            conflict_items += (
                "<li>theme pulse {pid}: supporting {sup} ({sups}) vs contradicting {con} "
                "({cons}) &mdash; both sides shown</li>").format(
                    pid=_esc(pulse.theme_pulse_id), sup=_esc(len(supporting)),
                    sups=_esc(", ".join(supporting) or "&mdash;"),
                    con=_esc(len(contradicting)), cons=_esc(", ".join(contradicting)))
    conflicts_html = (
        '<h2>Conflicts (both sides)</h2><div class="panel"><ul>'
        + (conflict_items or "<li>no conflicts recorded in this run</li>") + "</ul></div>")

    replay_link = (
        '<h2>Replay verification</h2><div class="panel"><p class="note">'
        '<a href="/replay/{0}">Verify this run&#39;s deterministic replay</a> &mdash; the '
        "persisted outputs are recomputed from the persisted inputs and compared field by "
        "field; a divergence is a named failure, never hidden.</p></div>").format(
            _esc(run_id))

    return _page(store_dir, "Run {0}".format(run_id), "/runs",
                 meta + agents + gates + gaps_html + conflicts_html + replay_link)


# --------------------------------------------------------------------------- #
# /replay/<id> -- replay viewer                                                 #
# --------------------------------------------------------------------------- #
def render_replay_view(store_dir: str, run_id: str) -> str:
    run = _get_run(store_dir, run_id)
    if run is None:
        return render_not_found(store_dir, "/replay/{0}".format(run_id))
    result = _harness(store_dir).replay(ReplayRequest(run_id=run_id), now=run.started_at)

    if result.deterministic_match:
        verdict = ('<div class="verdict ok">deterministic_match: True &mdash; the persisted '
                   "run reconstructs exactly from its persisted inputs</div>")
        diff_html = ""
    else:
        verdict = ('<div class="verdict bad">deterministic_match: False &mdash; the replay '
                   "DIVERGED from the persisted record. A divergent replay is a FAILURE; "
                   "every difference is named below.</div>")
        diff_html = ('<h2>Named differences</h2><div class="panel"><ul class="diffs">'
                     + "".join("<li>{0}</li>".format(_esc(diff))
                               for diff in result.differences) + "</ul></div>")

    counts = (
        '<h2>Replay volumes</h2><div class="panel"><table class="kv">'
        "<tr><th>Source run</th><td>{src}</td></tr>"
        "<tr><th>Replay id</th><td>{rid}</td></tr>"
        "<tr><th>Replayed</th><td>events {ev} &middot; findings {fi} &middot; signals {si}"
        "</td></tr>"
        "<tr><th>Differences</th><td>{nd}</td></tr>"
        "</table></div>").format(
            src=_esc(result.source_run_id), rid=_esc(result.replay_id),
            ev=_esc(result.events_replayed), fi=_esc(result.findings_replayed),
            si=_esc(result.signals_replayed), nd=_esc(len(result.differences)))

    note = ('<p class="note">Replay reads the append-only stores and recomputes; it never '
            'rewrites a stored byte. Back to <a href="/runs/{0}">run detail</a> or '
            '<a href="/runs">run history</a>.</p>').format(_esc(run_id))

    return _page(store_dir, "Replay {0}".format(run_id), "/runs",
                 verdict + diff_html + counts + note)


# --------------------------------------------------------------------------- #
# /alerts -- alert inbox                                                        #
# --------------------------------------------------------------------------- #
def render_alert_inbox(store_dir: str) -> str:
    alerts = alerts_with_status(store_dir)
    note = ('<p class="note">Alerts OBSERVE, they never act: each one names a state change '
            "between persisted pulse runs in plain English and points at its evidence. "
            "Severities are labels on a human-attention ladder, nothing numeric. Acknowledging "
            "appends a NEW record referencing the alert &mdash; the alert line itself stays "
            "byte-unchanged.</p>")
    if not alerts:
        body = note + ('<div class="panel"><p class="note">No alerts in this store yet. '
                       "Alerts appear after pulses detect a state change between runs."
                       "</p></div>")
        return _page(store_dir, "Alert inbox", "/alerts", body)

    any_shadow = any(str(getattr(a, "mode", "")) == "SHADOW_24X7" for a in alerts)
    shadow_note = (
        '<p class="note">Shadow Mode alerts are marked below and are NON-PRODUCTION: they land '
        "in this in-app inbox only, they never escalate as a production notification, and each "
        "carries a plain-English recommended REVIEW action &mdash; nothing here places or "
        "changes anything.</p>" if any_shadow else "")
    rows = ""
    for alert in alerts:
        subjects = ", ".join(tuple(alert.subject_tickers) + tuple(alert.subject_themes)) \
            or "&mdash;"
        if alert.acknowledged:
            action = _badge("acknowledged", "ok")
        else:
            action = (
                '<form class="op-form" method="post" action="/api/alerts/{aid}/ack">'
                '<input type="hidden" name="acknowledged_by" value="operator">'
                "<button>Acknowledge</button>"
                '<span class="op-note">OPERATOR action &mdash; appends an acknowledgment '
                "record; not a market action.</span></form>").format(aid=_esc(alert.alert_id))
        is_shadow = str(getattr(alert, "mode", "")) == "SHADOW_24X7"
        mode_cell = (_badge("Shadow Mode", "warn") if is_shadow
                     else _badge("production inbox", "ok") if getattr(alert, "mode", "")
                     else "&mdash;")
        review = str(getattr(alert, "recommended_review_action", "") or "")
        review_cell = _badge(review, "warn") if review else "&mdash;"
        dq_state = str(getattr(alert, "dq_state", "") or "")
        review_cell += (" &middot; DQ {0}".format(_esc(dq_state)) if dq_state else "")
        delivery = str(latest_delivery_status(store_dir, alert.alert_id) or "")
        delivery_cell = (
            _badge(_DELIVERY_DISPLAY.get(delivery, delivery), _DELIVERY_KINDS.get(delivery, "warn"))
            if delivery else "&mdash;")
        rows += (
            "<tr><th>{sev}</th><td>{mode}</td><td>{cat}</td><td>{reason}</td><td>{review}</td>"
            "<td>{delivery}</td><td>{run}</td><td>{subjects}</td><td>{created}</td>"
            "<td>{action}</td></tr>").format(
                sev=_badge(alert.severity, _SEVERITY_KINDS.get(alert.severity, "warn")),
                mode=mode_cell,
                cat=_esc(str(alert.category).replace("_", " ")),
                reason=_esc(alert.human_readable_reason), review=review_cell,
                delivery=delivery_cell,
                run=_esc(alert.run_id), subjects=_esc(subjects),
                created=_esc(alert.created_at), action=action)
    table = (
        '<div class="panel"><table class="kv"><tr><th>Severity</th><td>Mode</td>'
        "<td>Category</td><td>Reason (plain English)</td><td>Recommended review</td>"
        "<td>Delivery</td><td>Run</td><td>Subjects</td><td>Created</td><td>Status</td></tr>"
        + rows + "</table></div>")
    return _page(store_dir, "Alert inbox", "/alerts", note + shadow_note + table)


# --------------------------------------------------------------------------- #
# /settings -- operator settings + schedule controls                            #
# --------------------------------------------------------------------------- #
def render_settings_page(store_dir: str) -> str:
    settings, revision = current_settings(store_dir)

    def _joined(key: str) -> str:
        return ", ".join(str(v) for v in settings.get(key, ()) if isinstance(v, str))

    def _shown(key: str) -> str:
        values = settings.get(key, [])
        if not values:
            return "&mdash; (empty)"
        return _esc("; ".join(str(v) for v in values))

    current = (
        '<h2>Current settings</h2><div class="panel"><table class="kv">'
        "<tr><th>Watchlists</th><td>{wl}</td></tr>"
        "<tr><th>Themes</th><td>{th}</td></tr>"
        "<tr><th>Subscriptions</th><td>{sub}</td></tr>"
        "<tr><th>Journal revision</th><td>{rev} (append-style journal &mdash; a change is a "
        "NEW snapshot line, never a mutation)</td></tr>"
        "</table></div>").format(wl=_shown("watchlists"), th=_shown("themes"),
                                 sub=_shown("subscriptions"), rev=_esc(revision))

    settings_form = (
        '<h2>Change settings</h2><form class="op-form" method="post" action="/api/settings">'
        '<input type="hidden" name="_method" value="PUT">'
        '<label>Watchlists (comma-separated) '
        '<input type="text" name="watchlists" value="{wl}"></label>'
        '<label>Themes (comma-separated) <input type="text" name="themes" value="{th}">'
        "</label><button>Save settings</button>"
        '<span class="op-note">OPERATOR action &mdash; PUT /api/settings; appends a NEW '
        "settings snapshot to the journal (prior lines stay byte-unchanged). Not a market "
        "action.</span></form>").format(wl=_esc(_joined("watchlists")),
                                        th=_esc(_joined("themes")))

    schedule = schedule_to_dict(_load_schedule(store_dir))
    paused_by_policy: Dict[str, Any] = {
        str(state.get("policy_id", "")): state.get("paused", False)
        for state in schedule.get("states", ())}
    prows = ""
    options = '<option value="all">all policies</option>'
    for policy in schedule.get("policies", ()):
        pid = str(policy.get("policy_id", ""))
        paused = bool(paused_by_policy.get(pid, False))
        prows += (
            "<tr><th>{pid}</th><td>every {mins} min</td><td>{hours}</td><td>{state}</td>"
            "</tr>").format(
                pid=_esc(pid), mins=_esc(policy.get("interval_minutes", "")),
                hours=("market hours only" if policy.get("market_hours_only")
                       else "any hour"),
                state=(_badge("paused", "warn") if paused else _badge("active", "ok")))
        options += '<option value="{0}">{0}</option>'.format(_esc(pid))
    overall = (_badge("ALL POLICIES PAUSED", "warn") if schedule.get("paused_all")
               else _badge("not paused", "ok"))
    schedule_html = (
        '<h2>Cadence policies</h2><div class="panel">'
        '<p class="note">Cadence policies say how often a SCHEDULED pulse may run once an '
        "operator explicitly ticks the scheduler; nothing here starts a background process. "
        "Overall: {overall}</p>"
        '<table class="kv"><tr><th>Policy</th><td>Cadence</td><td>Window</td>'
        "<td>State</td></tr>{rows}</table>"
        '<form class="op-form" method="post" action="/api/schedule/pause">'
        '<label>Policy <select name="policy_id">{options}</select></label>'
        "<button>Pause</button>"
        '<span class="op-note">OPERATOR action &mdash; journals a paused schedule state '
        "(append-only). Not a market action.</span></form>"
        '<form class="op-form" method="post" action="/api/schedule/resume">'
        '<label>Policy <select name="policy_id">{options}</select></label>'
        "<button>Resume</button>"
        '<span class="op-note">OPERATOR action &mdash; journals a resumed schedule state '
        "(append-only). Not a market action.</span></form>"
        "</div>").format(overall=overall, rows=prows, options=options)

    return _page(store_dir, "Settings", "/settings",
                 current + settings_form + schedule_html)


# --------------------------------------------------------------------------- #
# 404 -- honest not-found page                                                  #
# --------------------------------------------------------------------------- #
def render_not_found(store_dir: str, path: str) -> str:
    body = (
        '<div class="panel"><p class="note">404 &mdash; nothing is served at '
        "<span class=\"mono\">{0}</span>. Nothing was created and nothing was hidden: "
        "either the id was never persisted or the path does not exist. Try "
        '<a href="/">home</a>, <a href="/runs">run history</a>, '
        '<a href="/alerts">the alert inbox</a> or <a href="/settings">settings</a>.'
        "</p></div>").format(_esc(path))
    return _page(store_dir, "Not found", "", body)
