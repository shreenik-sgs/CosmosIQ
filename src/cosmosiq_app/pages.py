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
    JOURNAL_STATUSES,
    LEARNING_THRESHOLDS,
    LearningStore,
    OUTCOME_LABELS,
    OutcomeStore,
    ReplayRequest,
    SignalReliabilityRecord,
    SignalStore,
    ThemePulseStore,
    alerts_with_status,
    blocked_candidates,
    eligible_candidates,
    feed_learning,
    journaled,
    latest_delivery_status,
    load_holdings,
    outcomes_for_learning,
    schedule_to_dict,
    unacknowledged_alerts,
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
    "GENERATE_CANVAS_COMMAND",
    "GENERATED_CANVAS_ENV",
    "GENERATED_CANVAS_FILENAME",
    "SERVICE_HEALTH_FILENAME",
    "canvas_artifacts",
    "generated_canvas_dir",
    "generated_canvas_path",
    "generated_canvas_present",
    "read_generated_canvas",
    "service_mode_indicator",
    "render_alert_inbox",
    "render_app_home",
    "render_evidence_page",
    "render_how_it_works_page",
    "render_journal_page",
    "render_map_page",
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

# The verbatim PRODUCTION indicator (020F), rendered ONLY when a PRODUCTION_24X7 health snapshot
# is present (i.e. production was activated through the 020F gate). Even activated, it keeps the
# permanent guarantees: Broker Disabled + Execution Manual Review Only, and NEVER a buy/sell/order
# control. The {live} slot is the configured source status.
_PRODUCTION_MODE_INDICATOR = (
    "Mode: PRODUCTION_24X7 · Live Data: {live} · Scheduler: On · "
    "Broker: Disabled · Execution: Manual Review Only · Alert Delivery: On")

# The generated Universe Canvas artifacts the nav links to WHEN PRESENT (a note when absent
# -- never a dead link). The operator generates them with the pulse CLI into this directory
# under the store; names are fixed by the Universe UI page set (copied, never imported).
CANVAS_DIRNAME = "universe_canvas"
CANVAS_PAGES: Tuple[str, ...] = (
    "universe.html", "dashboard.html", "data_quality.html", "cockpit.html",
)

# The immersive Universe Canvas the Map view frames READ-ONLY. It is a GENERATED artifact
# (built by the Universe UI, never by this app) that lives in the repo's generated/ tree; the
# Map serves its bytes verbatim at /map/canvas and never rewrites or duplicates it. The lookup
# dir defaults to <repo>/generated/universe_ui and is overridable with COSMOSIQ_CANVAS_DIR so
# the honest empty state (no canvas generated yet) is exercisable against a temp dir.
GENERATED_CANVAS_ENV = "COSMOSIQ_CANVAS_DIR"
GENERATED_CANVAS_FILENAME = "universe.html"
# The exact operator command that builds the canvas -- shown verbatim in the empty state.
GENERATE_CANVAS_COMMAND = "PYTHONPATH=src python3 -m universe_ui --out generated/universe_ui"


def _default_generated_canvas_dir() -> str:
    """<repo>/generated/universe_ui -- three dirs up from this file (src/cosmosiq_app/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    return os.path.join(root, "generated", "universe_ui")


def generated_canvas_dir() -> str:
    """The dir the Map reads the generated canvas from (COSMOSIQ_CANVAS_DIR, else the repo's)."""
    return os.environ.get(GENERATED_CANVAS_ENV) or _default_generated_canvas_dir()


def generated_canvas_path() -> str:
    """Absolute path to the generated ``universe.html`` the Map frames (may not exist)."""
    return os.path.join(generated_canvas_dir(), GENERATED_CANVAS_FILENAME)


def generated_canvas_present() -> bool:
    """True iff a generated Universe Canvas exists to frame (never fabricated when absent)."""
    return os.path.isfile(generated_canvas_path())


def read_generated_canvas() -> str:
    """The generated ``universe.html`` bytes, verbatim (the Map serves it AS-IS, read-only)."""
    with open(generated_canvas_path(), encoding="utf-8") as handle:
        return handle.read()

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


# The eight primary cockpit tabs, in operator-reading order (plain-language names, no
# jargon). Each is a first-class GET page; the current tab renders with `.here`.
_PRIMARY_TABS: Tuple[Tuple[str, str], ...] = (
    ("Dashboard", "/"),
    ("Opportunities", "/opportunities"),
    ("Company Research", "/research"),
    ("Portfolio", "/portfolio"),
    ("Journal & Learning", "/journal"),
    ("Evidence & Trust", "/evidence"),
    ("How It Works", "/how-it-works"),
    ("Map", "/map"),
)

# A quiet secondary row of operator surfaces that stay reachable (append-only history,
# the alert inbox, settings, the theme browser) without cluttering the primary tabs.
_UTILITY_LINKS: Tuple[Tuple[str, str], ...] = (
    ("Runs", "/runs"), ("Themes", "/themes"), ("Alerts", "/alerts"),
    ("Settings", "/settings"),
)

# Which primary tab "owns" a given active route, so deep pages and the old routes still
# light up a sensible tab (Runs/Alerts/Settings/Replay -> Evidence & Trust, the candidate
# and company/theme surfaces -> Opportunities / Company Research, etc.).
_ACTIVE_TAB: Dict[str, str] = {
    "/": "/",
    "/opportunities": "/opportunities", "/candidates": "/opportunities",
    "/research": "/research", "/companies": "/research", "/themes": "/research",
    "/portfolio": "/portfolio",
    "/journal": "/journal",
    "/evidence": "/evidence", "/runs": "/evidence", "/alerts": "/evidence",
    "/settings": "/evidence", "/replay": "/evidence",
    "/how-it-works": "/how-it-works",
    "/map": "/map",
}


def _nav(store_dir: str, active: str) -> str:
    """The primary 8-tab nav (current tab marked `here`) plus the quiet utility row."""
    tab = _ACTIVE_TAB.get(active, "")
    tabs = ""
    for label, href in _PRIMARY_TABS:
        here = " here" if href == tab else ""
        tabs += '<a class="navlink{0}" href="{1}">{2}</a>'.format(here, href, _esc(label))
    util = ""
    for label, href in _UTILITY_LINKS:
        util += '<a class="navsub" href="{0}">{1}</a>'.format(href, _esc(label))
    present = canvas_artifacts(store_dir)
    if present:
        for name in present:
            util += '<a class="navsub" href="/canvas/{0}">Canvas: {1}</a>'.format(
                _esc(name), _esc(name[:-len(".html")].replace("_", " ")))
    else:
        util += ('<span class="navnote">Universe Canvas: not generated in this store yet '
                 "&mdash; no link (generate with the pulse CLI into "
                 "&lt;store&gt;/{0}/)</span>".format(_esc(CANVAS_DIRNAME)))
    return ('<nav class="tabs">{0}</nav><div class="subnav">{1}</div>'.format(tabs, util))


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
    Shadow Mode) and NEVER says "Production 24x7". In PRODUCTION_24X7 (rendered ONLY when a
    production health snapshot exists -- i.e. production was activated through the 020F gate) the
    verbatim production line renders, still Broker Disabled + Execution Manual Review Only and
    NEVER a buy/sell/order control. When no health snapshot exists (the default,
    service-never-started posture) this returns '' so the page is byte-identical to 015C.
    """
    health = _service_health(store_dir)
    if not health:
        return ""                           # no service ran -> no indicator (safe OFF posture)
    mode = str(health.get("service_mode", "off") or "off").lower()
    if mode == "production_24x7":
        # Rendered only when production was activated (a PRODUCTION health snapshot exists). Even
        # then: Broker Disabled + Execution Manual Review Only -- no buy/sell/order control ever.
        return _PRODUCTION_MODE_INDICATOR.format(live=_configured_source_status(health))
    if mode == "shadow_24x7":
        return _SHADOW_MODE_INDICATOR.format(live=_configured_source_status(health))
    scheduler = "Attended" if mode == "manual" else "Off"
    inbox = "Inbox" if mode == "manual" else "Off"
    return ("Mode: {mode} · Live Data: {live} · Scheduler: {sched} · Broker: Disabled · "
            "Execution: Manual Review Only · Alerts: {inbox}").format(
                mode=mode.upper(), live=_configured_source_status(health),
                sched=scheduler, inbox=inbox)


# The default honest chip line when NO service ran (the empty-store posture). It preserves
# the two permanent guarantees in plain words -- Manual Review Only, and no market connection
# -- WITHOUT the literal "broker" token (kept for the service-mode line, where it is honest and
# expected) so the default UI stays clean for the trade-affordance sweep. It NEVER claims live
# or production.
_DEFAULT_CHIP_LINE = ("Manual Review Only &middot; no market connection &middot; offline "
                      "(no service running) &middot; local operator app")


def _mode_word(indicator: str) -> str:
    """A compact mode token for the chip face, parsed from the verbatim mode line."""
    if not indicator:
        return "offline"
    head = indicator.split("·", 1)[0]
    return head.replace("Mode:", "").strip() or "offline"


def _status_chip(store_dir: str) -> str:
    """The quiet, honest status chip: a compact pill carrying the FULL honest mode line.

    The visible face stays short (``Manual Review · <mode>``); the complete honest line
    (Broker Disabled + Execution Manual Review Only when a service ran, else the offline
    posture) is preserved verbatim in the chip's ``title`` tooltip AND an expandable details
    line -- honesty preserved, just not shouting. On an empty store the chip is honest
    (``Manual Review · offline``) and never claims live or production.
    """
    indicator = service_mode_indicator(store_dir)
    full = indicator if indicator else _DEFAULT_CHIP_LINE
    mode = _mode_word(indicator)
    return (
        '<details class="chip-wrap"><summary class="chip" title="{full}">'
        '<span class="dot"></span>Manual Review &middot; {mode}</summary>'
        '<div class="chip-details">{full}</div></details>').format(
            full=full, mode=_esc(mode))


def _page(store_dir: str, title: str, active: str, body: str) -> str:
    """One complete self-contained page: inline CSS, honest strip, chip, nav, body, footer."""
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>{title} &middot; {app}</title><style>{css}</style></head><body>"
        '<div class="strip">{as_of}<span class="sep">&middot;</span>local operator app'
        '<span class="sep">&middot;</span>no market action can be taken here</div>'
        '<div class="bar"><span class="brand">{app}<small>economic intelligence &middot; '
        "local operator app</small></span>{chip}</div>{nav}"
        '<div class="wrap"><h1>{title}</h1>{body}'
        '<p class="foot">{app} &mdash; labels and volume counts only; append-only history; '
        "pulses run only when an operator (or an operator-journaled cadence policy) asks. "
        "Evidence and observability, nothing else.</p>"
        "</div></body></html>").format(
            title=_esc(title), app=_esc(APP_NAME), css=APP_CSS,
            as_of=_as_of_line(store_dir), nav=_nav(store_dir, active), body=body,
            chip=_status_chip(store_dir))


# --------------------------------------------------------------------------- #
# / -- app home                                                                 #
# --------------------------------------------------------------------------- #
def _portfolio_snapshot_html(store_dir: str) -> str:
    """A read-only portfolio snapshot for the Dashboard, or an honest 'no positions' line."""
    loaded, _reason = load_holdings(store_dir)
    if loaded is None or not getattr(loaded, "positions", ()):
        return ('<h2>Portfolio snapshot</h2><div class="panel"><p class="note">No positions '
                "recorded yet &mdash; the portfolio ledger stays honestly empty until you "
                "record a holdings statement. Open the "
                '<a href="/portfolio">Portfolio</a> tab for how to record one.</p></div>')
    positions = tuple(loaded.positions)
    tickers = ", ".join(p.ticker for p in positions[:8]) + (
        " &hellip;" if len(positions) > 8 else "")
    return (
        '<h2>Portfolio snapshot</h2><div class="panel"><table class="kv">'
        "<tr><th>Positions recorded</th><td>{count}</td></tr>"
        "<tr><th>Tickers</th><td><span class=\"mono\">{tickers}</span></td></tr>"
        "<tr><th>Statement as of</th><td>{asof}</td></tr>"
        '</table><p class="note">Read-only, from the operator-recorded statement &mdash; never '
        'fetched, never valued. Full intelligence on the <a href="/portfolio">Portfolio</a> '
        "tab.</p></div>").format(
            count=_esc(getattr(loaded, "position_count", len(positions))),
            tickers=_esc(tickers), asof=_esc(getattr(loaded, "as_of", "") or "&mdash;"))


def _recent_alerts_html(store_dir: str) -> str:
    """The most recent shadow / inbox alerts on the Dashboard (read-only, honest empty)."""
    alerts = list(alerts_with_status(store_dir))
    if not alerts:
        return ('<h2>Recent alerts</h2><div class="panel"><p class="note">No alerts in this '
                "store yet &mdash; alerts appear after pulses detect a state change between "
                'runs. Open the <a href="/alerts">Alerts</a> inbox for the full list.</p>'
                "</div>")
    recent = alerts[-5:][::-1]
    rows = ""
    for alert in recent:
        is_shadow = str(getattr(alert, "mode", "")) == "SHADOW_24X7"
        marker = _badge("Shadow Mode", "warn") if is_shadow else "&mdash;"
        rows += "<tr><th>{sev}</th><td>{mode}</td><td>{reason}</td></tr>".format(
            sev=_badge(alert.severity, _SEVERITY_KINDS.get(alert.severity, "warn")),
            mode=marker, reason=_esc(alert.human_readable_reason))
    return (
        '<h2>Recent alerts</h2><div class="panel"><table class="kv">'
        "<tr><th>Severity</th><td>Mode</td><td>Reason (plain English)</td></tr>"
        + rows + '</table><p class="note">Alerts OBSERVE, they never act. Full inbox on the '
        '<a href="/alerts">Alerts</a> surface.</p></div>')


def _external_source_presence():
    """PRESENCE booleans for the SEC EDGAR + FMP external sources (membership only, never a value).

    Reads credential PRESENCE via :func:`reality_mesh.build_live_adapters` (which computes
    ``name in os.environ`` only) and maps each configured adapter back to a source label. Returns
    ``[(label, configured_bool)]``; no value is ever read, so it is safe to render. The label text
    deliberately avoids the guarded overclaim / trade / credential-token vocabulary.
    """
    from reality_mesh import build_live_adapters
    adapters, _notes = build_live_adapters()   # env=None -> os.environ presence only
    configured_ids = {a.descriptor.adapter_id for a in adapters}
    return [
        ("SEC EDGAR", "evidence.sec_edgar_live" in configured_ids),
        ("FMP", "evidence.fmp_live" in configured_ids),
    ]


def _render_source_refresh(store_dir: str, refresh_note: str = "") -> str:
    """The SANCTIONED "Refresh from external sources" operator form for the Evidence tab.

    Presence indicators (SEC EDGAR / FMP: configured | not configured -- labels only, never a
    value). Record/refresh-only: POSTs to /api/pulse/live and redirects back; there is no
    execution affordance of any kind. The wording avoids the guarded overclaim / execution /
    credential-token vocabulary by construction. When neither source is configured, the honest
    "set the env var(s)" guidance is always shown.
    """
    settings, _revision = current_settings(store_dir)
    presence = "".join(
        "<li>{0}: {1}</li>".format(_esc(label), "configured" if ok else "not configured")
        for label, ok in _external_source_presence())
    any_configured = any(ok for _label, ok in _external_source_presence())
    guidance = "" if any_configured else (
        '<p class="note">No external sources configured yet. Set SEC_USER_AGENT (a free SEC '
        "contact identity) and/or your FMP access env var, then refresh. Nothing is fetched, "
        "nothing is fabricated, and there is no fixture fallback until a source is set.</p>")
    note_html = ('<p class="note">{0}</p>'.format(_esc(refresh_note))) if refresh_note else ""

    return (
        '<h2>Refresh from external sources</h2>'
        '<div class="panel"><p class="note">External source configuration '
        "(presence only &mdash; values are never read or shown):</p><ul>" + presence + "</ul>"
        + guidance + note_html
        + '<form class="op-form" method="post" action="/api/pulse/refresh">'
        '<label>Watchlist (comma-separated tickers) '
        '<input type="text" name="watchlist" value="{wl}"></label>'
        '<label>Themes (comma-separated) <input type="text" name="themes" value="{th}">'
        "</label><button>Refresh from external sources</button>"
        '<span class="op-note">SANCTIONED operator refresh &mdash; pulls REAL SEC EDGAR + FMP '
        "evidence into this store (gated on the env vars above). Record/refresh-only, "
        "shadow-marked; nothing repeats unless you ask again. SEC stays canonical; FMP stays "
        "convenience.</span></form></div>").format(
            wl=_esc(", ".join(str(v) for v in settings.get("watchlists", ())
                              if isinstance(v, str))),
            th=_esc(", ".join(str(v) for v in settings.get("themes", ())
                              if isinstance(v, str))))


def render_app_home(store_dir: str) -> str:
    counts = _handle_health(store_dir)["body"]["counts"]
    settings, revision = current_settings(store_dir)

    intro = (
        '<p class="note">{0} is your LOCAL investor cockpit over append-only pulse stores. '
        "Everything shown is a persisted label, a range, or a volume count &mdash; never a "
        "hidden metric, never a market action. This Dashboard is a read-only overview; use "
        "the tabs above to go deeper.</p>".format(_esc(APP_NAME)))

    # --- overview cards: opportunities / blocked / open alerts / runs -------------
    opportunities = len(eligible_candidates(store_dir))
    blocked = len(blocked_candidates(store_dir))
    open_alerts = len(unacknowledged_alerts(store_dir))
    overview = (
        '<h2>Overview</h2><div class="cards">'
        '<div class="card"><div class="clabel">Opportunities</div>'
        '<div class="metric">{opp}</div><div class="csub">eligible capital candidates '
        '&middot; <a href="/opportunities">open</a></div></div>'
        '<div class="card"><div class="clabel">Blocked candidates</div>'
        '<div class="metric">{blk}</div><div class="csub">shown with their exact reason '
        '&middot; <a href="/opportunities">open</a></div></div>'
        '<div class="card"><div class="clabel">Open alerts</div>'
        '<div class="metric">{alr}</div><div class="csub">unacknowledged in the inbox '
        '&middot; <a href="/alerts">open</a></div></div>'
        '<div class="card"><div class="clabel">Pulse runs</div>'
        '<div class="metric">{run}</div><div class="csub">append-only history '
        '&middot; <a href="/runs">open</a></div></div>'
        "</div>").format(opp=_esc(opportunities), blk=_esc(blocked),
                         alr=_esc(open_alerts), run=_esc(counts.get("runs", 0)))

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

    portfolio = _portfolio_snapshot_html(store_dir)
    recent_alerts = _recent_alerts_html(store_dir)

    return _page(store_dir, "Dashboard", "/",
                 intro + overview + latest + portfolio + recent_alerts
                 + store_html + pulse_form + canvas)


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
# /journal -- Journal & Learning (the operator's recorded decisions so far)      #
# --------------------------------------------------------------------------- #
# Journal status ladder (022F) -> badge kind (a LABEL, never a score). The full closed
# vocabulary is rendered as a legend so the status ladder is always visible.
_JOURNAL_STATUS_KINDS = {
    "open": "warn",
    "invalidation_hit": "bad",
    "exit_watch_hit": "warn",
    "thesis_confirmed": "ok",
    "lapsed": "warn",
    "superseded": "",
}

# 017 outcome label -> (plain-English display, badge kind). Labels + volume counts only.
_OUTCOME_DISPLAY = {
    "followed_through": "followed through",
    "contradicted": "contradicted",
    "faded": "faded",
    "unresolved": "unresolved (no later observation yet)",
}
_OUTCOME_KINDS = {
    "followed_through": "ok", "contradicted": "bad", "faded": "warn", "unresolved": "",
}

# 017 signal-reliability LABEL -> (plain-English gloss, badge kind). A calibration LABEL over
# volume, never a hit-rate number. ``insufficient_history`` is the honest below-threshold state.
_RELIABILITY_GLOSS = {
    "improving": "strengthening",
    "stable": "steady / mixed",
    "deteriorating": "weakening",
    "insufficient_history": "unproven (not enough history yet)",
}
_RELIABILITY_KINDS = {
    "improving": "ok", "stable": "", "deteriorating": "bad", "insufficient_history": "warn",
}


def _journal_learning_counts(store_dir: str) -> Dict[str, int]:
    """The 017 outcome tally as LABELS + VOLUME COUNTS: the persisted outcome store folded with
    the recommendation journal's own outcome roll-up (``feed_learning``). Counts are volumes; no
    ratio / score is ever constructed."""
    counts = {label: 0 for label in sorted(OUTCOME_LABELS)}
    for record in OutcomeStore(store_dir).read_all():
        counts[record.outcome_label] = counts.get(record.outcome_label, 0) + 1
    for label, volume in feed_learning(store_dir).items():
        counts[label] = counts.get(label, 0) + int(volume)
    return counts


def _reliability_rollups(store_dir: str) -> Tuple[SignalReliabilityRecord, ...]:
    """The persisted 017 per-signal-family reliability roll-ups (label + volume counts)."""
    return tuple(r for r in LearningStore(store_dir).read_all()
                 if isinstance(r, SignalReliabilityRecord))


def render_journal_page(store_dir: str) -> str:
    """Journal & Learning: the 022F recommendation journal, the 017 learning loop (outcome
    tally + signal-reliability, LABELS + VOLUME COUNTS only), and -- via the UX-2 ledger -- the
    operator's actions vs. recommendations (acted / not-yet-acted). Read-only, deterministic,
    honest empty states; no numeric score / rank / return / hit-rate anywhere, and nothing here
    places or changes a market position."""
    intro = ('<p class="note">The learning loop, made visible: every recommendation the layer '
             "publishes is journaled here, the 017 feedback core rolls its outcomes up as "
             "plain LABELS over VOLUME COUNTS (never a track-record number), and your own "
             "recorded fills close the loop by showing which recommendations you acted on. "
             "Everything is read-only and append-only &mdash; nothing here places or changes a "
             "market position.</p>")
    journal = _journal_recommendations_section(store_dir)
    learning = _learning_feedback_section(store_dir)
    actions = _actions_vs_recommendations_section(store_dir)
    return _page(store_dir, "Journal & Learning", "/journal", intro + journal + learning + actions)


def _journal_recommendations_section(store_dir: str) -> str:
    """Section 1 -- the 022F journaled recommendations, newest first (labels + refs + status)."""
    entries = journaled(store_dir)
    if not entries:
        return ('<h2>Recommendation journal</h2><div class="panel"><p class="note">No '
                "recommendations journaled yet &mdash; they appear here once the recommendation "
                "layer publishes and journals one. Nothing is invented to fill the space."
                "</p></div>")
    rows = ""
    for entry in reversed(entries):               # newest first
        outcomes = tuple(entry.subsequent_outcomes)
        outcomes_cell = ("{0} accrued: {1}".format(len(outcomes),
                                                   _esc("; ".join(outcomes)))
                         if outcomes else "none accrued yet")
        rows += (
            '<tr><th><span class="mono">{tk}</span></th><td>{label}</td><td>{pub}</td>'
            "<td>{thesis}</td><td>{inval}</td><td>{exit}</td><td>{dq}</td><td>{status}</td>"
            "<td>{outcomes}</td></tr>").format(
                tk=_esc(entry.ticker),
                label=_badge(entry.recommendation_label or "unlabeled",
                             "ok" if entry.recommendation_label else "warn"),
                pub=_esc(entry.published_at or "&mdash;"),
                thesis=_esc(entry.thesis_summary or "&mdash;"),
                inval=_esc(entry.invalidation_condition or "&mdash;"),
                exit=_esc(entry.exit_watch_condition or "&mdash;"),
                dq=_badge(entry.data_quality_state or "unstated",
                          "ok" if entry.data_quality_state == "healthy" else "warn"),
                status=_badge(entry.status,
                              _JOURNAL_STATUS_KINDS.get(entry.status, "warn")),
                outcomes=outcomes_cell)
    legend = " &middot; ".join(
        _badge(status, _JOURNAL_STATUS_KINDS.get(status, "warn")) for status in JOURNAL_STATUSES)
    return (
        '<h2>Recommendation journal</h2><div class="panel">'
        '<p class="note">Every published recommendation, journaled append-only, newest first. '
        "Labels, refs and a closed status ladder only &mdash; never a numeric verdict or a "
        "target price. Status ladder: {legend}.</p>"
        '<table class="kv"><tr><th>Ticker</th><td>Recommendation label</td><td>Published</td>'
        "<td>Thesis summary</td><td>Invalidation condition</td><td>Exit / watch condition</td>"
        "<td>Data quality</td><td>Status</td><td>Subsequent outcomes</td></tr>"
        + rows + "</table></div>").format(legend=legend)


def _learning_feedback_section(store_dir: str) -> str:
    """Section 2 -- the 017 learning loop as LABELS + VOLUME COUNTS (no numeric metric)."""
    counts = _journal_learning_counts(store_dir)
    rollups = _reliability_rollups(store_dir)
    has_history = any(counts.values()) or bool(rollups)

    if not has_history:
        tally = ('<div class="panel"><p class="note">No learning history yet &mdash; the '
                 "outcome tally fills in as journaled recommendations settle and the 017 "
                 "feedback core records outcomes across pulse runs. Nothing is fabricated."
                 "</p></div>")
    else:
        crows = "".join(
            "<tr><th>{label}</th><td>{count}</td></tr>".format(
                label=_badge(_OUTCOME_DISPLAY.get(label, label),
                             _OUTCOME_KINDS.get(label, "warn")),
                count=_esc(counts[label]))
            for label in sorted(OUTCOME_LABELS))
        tally = ('<div class="panel"><p class="note">Outcome tally &mdash; VOLUME COUNTS per '
                 "closed outcome label, across the 017 outcome store and the recommendation "
                 "journal. These are VOLUME COUNTS, never a fabricated success figure.</p>"
                 '<table class="kv"><tr><th>Outcome label</th><td>Volume count</td></tr>'
                 + crows + "</table></div>")

    if rollups:
        rrows = "".join(
            "<tr><th>{family}</th><td>{label}</td>"
            "<td>followed through {ft} &middot; contradicted {ct} &middot; faded {fd} "
            "&middot; unresolved {un}</td></tr>".format(
                family=_esc(r.discipline or "unspecified"),
                label=_badge(_RELIABILITY_GLOSS.get(r.reliability_label, r.reliability_label),
                             _RELIABILITY_KINDS.get(r.reliability_label, "warn")),
                ft=_esc(r.followed_through_count), ct=_esc(r.contradicted_count),
                fd=_esc(r.faded_count), un=_esc(r.unresolved_count))
            for r in rollups)
        reliability = (
            '<div class="panel"><p class="note">Signal reliability by family &mdash; a '
            "calibration LABEL over the outcome volumes, never a fabricated success figure.</p>"
            '<table class="kv"><tr><th>Signal family</th><td>Reliability label</td>'
            "<td>Outcome volumes</td></tr>" + rrows + "</table></div>")
    else:
        reliability = ('<div class="panel"><p class="note">No signal-reliability roll-up yet '
                       "&mdash; a family is calibrated only once the 017 core has recorded "
                       "outcomes for it. Nothing is fabricated.</p></div>")

    legend = ('<p class="note">These are CALIBRATION LABELS over VOLUME, never a track-record '
              "number: reliability reads strengthening / steady / weakening, and honestly "
              "reads unproven (insufficient_history) until at least {0} outcomes have resolved "
              "&mdash; no label pretends confidence off a tiny sample.</p>").format(
                  _esc(LEARNING_THRESHOLDS["min_resolved_outcomes"]))
    return ("<h2>Learning &amp; feedback</h2>" + tally
            + "<h3>Signal reliability</h3>" + reliability + legend)


def _actions_vs_recommendations_section(store_dir: str) -> str:
    """Section 3 -- the loop-closing view: which journaled recommendations the operator ACTED
    on (a linked fill exists) vs. not yet acted on. Labels + refs only; no P&L, no return."""
    links = outcomes_for_learning(store_dir)
    entries = journaled(store_dir)
    links_by_ref: Dict[str, List[Any]] = {}
    for link in links:
        links_by_ref.setdefault(link.recommendation_ref, []).append(link)

    if not entries and not links:
        return ('<h2>Your actions vs recommendations</h2><div class="panel"><p class="note">No '
                "recorded fills linked to a recommendation yet &mdash; once you log a fill "
                "against a recommendation on the "
                '<a href="/portfolio">Portfolio</a> tab, the loop (recommendation &rarr; your '
                "action &rarr; outcome) closes here. Nothing is fabricated.</p></div>")

    rows = ""
    covered_refs = set()
    for entry in reversed(entries):
        ref = entry.recommendation_id
        matched = links_by_ref.get(ref, [])
        covered_refs.add(ref)
        if matched:
            action = _badge("acted", "ok")
            detail = "; ".join(
                "{0} on {1}".format(_esc(link.side), _esc(link.trade_date)) for link in matched)
        else:
            action = _badge("not-yet-acted", "warn")
            detail = "no linked fill recorded"
        rows += (
            '<tr><th><span class="mono">{tk}</span></th><td>{ref}</td><td>{action}</td>'
            "<td>{detail}</td></tr>").format(
                tk=_esc(entry.ticker), ref=_esc(ref), action=action, detail=detail)

    # Any recommendation-linked fill whose ref was never journaled here -- still show the action,
    # so a recorded action is never silently dropped.
    for ref in sorted(set(links_by_ref) - covered_refs):
        matched = links_by_ref[ref]
        detail = "; ".join(
            "{0} on {1} ({2})".format(_esc(link.side), _esc(link.trade_date), _esc(link.ticker))
            for link in matched)
        rows += (
            '<tr><th><span class="mono">{tk}</span></th><td>{ref}</td><td>{action}</td>'
            "<td>{detail}</td></tr>").format(
                tk=_esc(matched[0].ticker), ref=_esc(ref),
                action=_badge("acted", "ok"), detail=detail)

    return (
        '<h2>Your actions vs recommendations</h2><div class="panel">'
        '<p class="note">The visible close of the loop: recommendation &rarr; your action '
        "&rarr; outcome. Each journaled recommendation is labelled acted (a recorded fill links "
        "to it) or not-yet-acted. Labels and dates only &mdash; no gain / loss figure, no "
        "market action.</p>"
        '<table class="kv"><tr><th>Ticker</th><td>Recommendation ref</td><td>Your action</td>'
        "<td>Recorded action (past tense)</td></tr>" + rows + "</table></div>")


# --------------------------------------------------------------------------- #
# /evidence -- Evidence & Trust (the data-quality surface)                      #
# --------------------------------------------------------------------------- #
# The source-authority ladder, rendered verbatim on the trust surface. Highest authority
# first; the closing rung is the permanent rule that a manual note is NEVER canonical.
_AUTHORITY_LADDER: Tuple[Tuple[str, str], ...] = (
    ("SEC filing", "canonical", "the primary regulated source of record"),
    ("FMP data provider", "provider", "a convenience provider; corroborated, not canonical"),
    ("Social / narrative", "weak signal", "marked WEAK; never stands alone as evidence"),
    ("Manual note", "never canonical", "an operator observation; can inform, never a fact"),
)


def _evidence_posture_html() -> str:
    """The honest standing posture: shadow-only, not production, Manual Review Only."""
    return (
        '<h2>Posture</h2><div class="panel"><div class="legend">'
        '<div class="cell"><b>Shadow-only</b><span>this is a local, shadow-mode intelligence '
        "app, not a production market system</span></div>"
        '<div class="cell"><b>Manual Review Only</b><span>every action is your own; the app '
        "inspects and explains, it never acts</span></div>"
        '<div class="cell"><b>No market connection</b><span>no brokerage connection and no '
        "automated trading exist anywhere in this app</span></div>"
        "</div></div>")


def _authority_ladder_html() -> str:
    """The source-authority ladder (SEC canonical &rarr; manual never canonical)."""
    rows = "".join(
        "<tr><th>{src}</th><td>{badge}</td><td>{gloss}</td></tr>".format(
            src=_esc(src),
            badge=_badge(rung, "ok" if rung == "canonical"
                         else "bad" if rung == "never canonical" else "warn"),
            gloss=_esc(gloss))
        for src, rung, gloss in _AUTHORITY_LADDER)
    return (
        '<h2>Source-authority ladder</h2><div class="panel">'
        '<p class="note">Not all evidence is equal. Every observation carries its source '
        "authority; higher rungs override lower ones, and a manual note is never promoted to a "
        "fact.</p>"
        '<table class="kv"><tr><th>Source</th><td>Authority</td><td>What it means</td></tr>'
        + rows + "</table></div>")


def _source_health_html(store_dir: str) -> str:
    """Source health from the service snapshot (coverage / source-gap counts), or an honest note."""
    health = _service_health(store_dir)
    summary = dict(health.get("source_health_summary", {}) or {}) if health else {}
    if not health or not summary:
        return ('<h2>Source health</h2><div class="panel"><p class="note">No service source-health '
                "snapshot recorded in this store yet &mdash; source health appears once the "
                "local service records coverage. Nothing is fabricated.</p></div>")
    status = _configured_source_status(health)
    return (
        '<h2>Source health</h2><div class="panel"><table class="kv">'
        "<tr><th>Configured source status</th><td>{status}</td></tr>"
        "<tr><th>Coverage records</th><td>{cov}</td></tr>"
        "<tr><th>Source-gap records</th><td>{fail}</td></tr>"
        '</table><p class="note">A source gap is shown as a gap &mdash; never filled from a '
        "fixture. Counts are volumes.</p></div>").format(
            status=_status_badge(status),
            cov=_esc(summary.get("coverage_records", 0)),
            fail=_esc(summary.get("failed_source_records", 0)))


def _latest_run_trust_html(store_dir: str, run: Any) -> str:
    """The latest run's data-quality gate (overall + per-gate), agent health, and data gaps."""
    run_id = run.run_id
    overall = _gate_overall(store_dir, run_id)
    grows = "".join(
        "<tr><th>{cat}</th><td>{status}</td><td>{summary}</td></tr>".format(
            cat=_gate_display(record.category), status=_status_badge(record.status),
            summary=_esc(record.summary or "&mdash;"))
        for record in DataQualityStore(store_dir).query(run_id=run_id)
        if record.category != "gate_overall")
    gates = (
        '<h3>Data-quality gate &mdash; latest run <a href="/runs/{rid}">{rid}</a></h3>'
        '<div class="panel"><p class="note">Gate verdicts are labels (pass / warn / fail / '
        "degraded), never a metric. Overall: {overall}</p>"
        '<table class="kv"><tr><th>Gate</th><td>Verdict</td><td>Summary</td></tr>'.format(
            rid=_esc(run_id), overall=_status_badge(overall))
        + (grows or "<tr><th>&mdash;</th><td colspan=\"2\">no gate records persisted for this "
                    "run</td></tr>") + "</table></div>")

    arows = "".join(
        "<tr><th>{aid}</th><td>{status}</td><td>{health}</td><td>{gaps} gap(s)</td>"
        "<td>{conf} conflict(s)</td></tr>".format(
            aid=_esc(_english_agent(result.agent_id)),
            status=_status_badge(result.status), health=_status_badge(result.health_status),
            gaps=_esc(len(result.data_gaps)), conf=_esc(len(result.conflicts)))
        for result in AgentRunLedger(store_dir).results_for_run(run_id))
    agents = (
        '<h3>Agent health &mdash; latest run</h3><div class="panel"><table class="kv">'
        "<tr><th>Agent</th><td>Status</td><td>Health</td><td>Data gaps</td><td>Conflicts</td>"
        "</tr>" + (arows or "<tr><th>&mdash;</th><td colspan=\"4\">no agent ledger rows "
                            "persisted for this run</td></tr>") + "</table></div>")

    gaps = _run_gaps(store_dir, run_id) + _coverage_notes(store_dir, run)
    gaps_html = (
        '<h3>Data gaps &amp; conflicts &mdash; latest run</h3><div class="panel">'
        '<ul class="gaps">'
        + ("".join("<li>{0}</li>".format(_esc(gap)) for gap in sorted(set(gaps)))
           or "<li>no data gaps recorded in this run</li>") + "</ul></div>")
    return ("<h2>Latest run &mdash; trust snapshot</h2>" + gates + agents + gaps_html)


def render_evidence_page(store_dir: str, *, refresh_note: str = "") -> str:
    """Evidence & Trust: the trust / data-quality surface. The latest run's DQ gate + gaps,
    source health, agent health, the source-authority ladder, a replay / determinism note, the
    honest shadow-only / Manual Review posture, AND the sanctioned "Refresh from external
    sources" operator form (PROD-LIVE-1) -- labels and counts only, degraded / failed states
    never hidden. Honest empty state when no runs. ``refresh_note`` (optional) shows an honest
    one-line result after a refresh POST; the default keeps existing callers byte-identical."""
    intro = ('<p class="note">Trust is earned by showing the work. This surface carries the '
             "latest run&#39;s data-quality gate and gaps, source health, agent health, the "
             "source-authority ladder, and a determinism note &mdash; all labels and counts, "
             "never a hidden metric. A run that failed a gate or ran degraded is shown as "
             "such.</p>")
    posture = _evidence_posture_html()
    ladder = _authority_ladder_html()
    source_health = _source_health_html(store_dir)
    refresh = _render_source_refresh(store_dir, refresh_note=refresh_note)

    runs = _runs_newest_first(store_dir)
    if not runs:
        empty = ('<h2>Latest run &mdash; trust snapshot</h2><div class="panel"><p class="note">'
                 "No persisted runs yet &mdash; the run-level trust snapshot stays empty until an "
                 'operator runs a pulse from the <a href="/">Dashboard</a>. Nothing is '
                 "fabricated.</p></div>")
        return _page(store_dir, "Evidence & Trust", "/evidence",
                     intro + posture + ladder + source_health + refresh + empty)

    latest = _latest_run_trust_html(store_dir, runs[0])

    rows = ""
    for run in runs:
        gaps = _run_gaps(store_dir, run.run_id)
        rows += (
            '<tr><th><a href="/runs/{rid}">{rid}</a></th><td>{start}</td><td>{gate}</td>'
            "<td>{health}</td><td>{gaps} gap(s)</td>"
            "<td><a href=\"/replay/{rid}\">verify replay</a></td></tr>").format(
                rid=_esc(run.run_id), start=_esc(run.started_at),
                gate=_status_badge(_gate_overall(store_dir, run.run_id)),
                health=_status_badge(_run_health(store_dir, run.run_id)),
                gaps=_esc(len(gaps)))
    table = ('<h2>Data-quality by run</h2><div class="panel"><table class="kv">'
             "<tr><th>Run</th><td>Started</td><td>Gate overall</td><td>Worst agent health</td>"
             "<td>Data gaps</td><td>Replay</td></tr>" + rows + '</table>'
             '<p class="note">Gate verdicts and health are closed labels (pass / warn / fail / '
             "degraded); the gap count is a volume. Open a run for the full per-gate and "
             "per-agent breakdown.</p></div>")
    replay_note = (
        '<h2>Replay &amp; determinism</h2><div class="panel"><p class="note">Every run can be '
        "re-verified by DETERMINISTIC replay: the persisted outputs are recomputed from the "
        "persisted inputs and compared field by field. A divergent replay is a named FAILURE, "
        "never hidden. Same inputs always reconstruct the same outputs.</p></div>")
    return _page(store_dir, "Evidence & Trust", "/evidence",
                 intro + posture + ladder + source_health + refresh
                 + latest + table + replay_note)


# --------------------------------------------------------------------------- #
# /how-it-works -- the pipeline explained in plain language                      #
# --------------------------------------------------------------------------- #
def render_how_it_works_page(store_dir: str) -> str:
    """A plain-language walk-through of the WHOLE real loop: current evidence -> signals ->
    theme pulses -> opportunities -> capital recommendation -> YOU act in your own brokerage ->
    you LOG the fill (record-only) -> portfolio intelligence + learning measure the outcome.
    Every stage links to its tab. Static, honest, Manual Review Only, no hidden number, and
    nothing here places or changes a market position."""
    # (title, plain-English what-it-does, "see" link label, href). An empty href == a stage
    # that happens OUTSIDE the app (your own decision), so it deliberately carries no tab link.
    steps = (
        ("Current evidence", "Filings and news come in as dated records &mdash; SEC filings are "
                             "the canonical source, the FMP data provider fills convenience gaps, "
                             "and each record keeps its source authority and a claim status. A "
                             "company claim or a rumor is never promoted to a fact.",
         "Evidence & Trust", "/evidence"),
        ("Signals", "Sensor agents read the evidence into typed reality signals with direction, "
                    "magnitude, and urgency labels &mdash; with an explicit WEAK mark on social "
                    "or uncorroborated evidence, so a thin signal never masquerades as a strong "
                    "one.", "Company Research", "/research"),
        ("Theme pulses", "Signals roll up into theme pulses with closed state labels (Warming, "
                         "Crowded, Exhausting, and so on). Contradictions keep BOTH sides "
                         "visible; nothing is averaged away.", "Company Research", "/research"),
        ("Opportunities", "Where a theme and a company line up with enough evidence, a capital "
                          "candidate is published as an opportunity worth diligence &mdash; "
                          "eligible ONLY with full lineage; otherwise blocked and shown with its "
                          "exact reason.", "Opportunities", "/opportunities"),
        ("Capital recommendation", "The accepted diligence engines run on your recorded inputs "
                                   "to produce a plain-language verdict and a suggested position "
                                   "RANGE (never an exact amount, never a hidden number). It is a "
                                   "Manual-Review recommendation, gated &mdash; a starting point "
                                   "for your own judgement, not an instruction.",
         "Opportunities", "/opportunities"),
        ("YOU act", "You decide, and if you choose to act you do it yourself in your OWN "
                    "brokerage account. Everything in this cockpit is Manual Review Only: it "
                    "inspects and explains, it never connects to a market, and it never acts on "
                    "your behalf.", "", ""),
        ("You log the fill", "Afterwards you record the fill you already made into the Portfolio "
                             "ledger. It is RECORD-ONLY bookkeeping &mdash; a journal entry of "
                             "your own recorded fact, with no market connection of any kind; "
                             "nothing here places or changes a position.",
         "Portfolio", "/portfolio"),
        ("Portfolio intelligence", "From your recorded holdings statement, the portfolio surface "
                                   "measures fit, exposure, and concentration as plain labels and "
                                   "bands &mdash; read-only, never fetched, never valued.",
         "Portfolio", "/portfolio"),
        ("Learning", "Your recorded actions close the loop against the recommendations that "
                     "preceded them: the feedback core rolls outcomes up as plain LABELS over "
                     "VOLUME COUNTS (never a track-record number), so calibration grows from what "
                     "actually happened.", "Journal & Learning", "/journal"),
    )
    chain = " &rarr; ".join(name for name, *_rest in steps)
    intro = ('<p class="note">The whole loop in one line: <strong>{0}</strong>. Each stage below '
             "explains, in plain English, what it does, what it deliberately does NOT do, and "
             "which tab shows it.</p>").format(chain)
    cards = ""
    for index, (name, desc, link_label, href) in enumerate(steps):
        see = ('<p class="note">See: <a href="{0}">{1}</a></p>'.format(_esc(href),
                                                                       _esc(link_label))
               if href else '<p class="note">This step happens OUTSIDE the app &mdash; it is '
                            "your own decision, in your own account.</p>")
        cards += ('<div class="panel"><h3>{n}. {name}</h3><p class="note">{desc}</p>{see}'
                  "</div>").format(n=index + 1, name=_esc(name), desc=_esc(desc), see=see)

    guardrails = (
        '<h2>The guardrails, plainly</h2><div class="panel"><div class="legend">'
        '<div class="cell"><b>Manual Review Only</b><span>the cockpit inspects and explains; '
        "you make and take every decision yourself</span></div>"
        '<div class="cell"><b>No brokerage connection</b><span>no market connection, no '
        "automated trading, nothing here can place or change a position</span></div>"
        '<div class="cell"><b>Plain labels, not hidden numbers</b><span>labels, ranges and '
        "volume counts only &mdash; never a hidden metric and never a hidden number</span></div>"
        '<div class="cell"><b>Evidence-cited</b><span>every claim carries its source authority '
        "and lineage; a rumor is never promoted to a fact</span></div>"
        "</div></div>")
    return _page(store_dir, "How It Works", "/how-it-works", intro + cards + guardrails)


# --------------------------------------------------------------------------- #
# /map -- the Universe Canvas surface (link / anchor to the star-field)          #
# --------------------------------------------------------------------------- #
# The Universe Canvas celestial mapping, in the operator's plain language (the canonical
# mapping is docs/product/BRAND_NOMENCLATURE.md). One compact legend makes the immersive map
# self-explanatory: each celestial body is a real intelligence object, never decoration.
_CELESTIAL_LEGEND: Tuple[Tuple[str, str, str], ...] = (
    ("Galaxy", "Mega Theme", "a durable structural shift the whole map orbits"),
    ("Planet", "Company", "a company / capital candidate you can inspect"),
    ("Star", "Bottleneck", "the constraint a value chain bends around"),
    ("Comet", "Catalyst", "a dated event that could move the thesis"),
    ("Black Hole", "Risk", "a major risk / red-team hazard that can swallow the case"),
)


def _celestial_legend_html() -> str:
    """The compact celestial legend (Galaxy = Mega Theme &hellip; Black Hole = Risk)."""
    cells = "".join(
        '<div class="cell"><b>{body} = {meaning}</b><span>{gloss}</span></div>'.format(
            body=_esc(body), meaning=_esc(meaning), gloss=_esc(gloss))
        for body, meaning, gloss in _CELESTIAL_LEGEND)
    return (
        '<h2>What the celestial bodies mean</h2><div class="panel">'
        '<p class="note">The Map is a picture, not a metaphor: every celestial body is a real '
        "intelligence object from the same persisted pulse data.</p>"
        '<div class="legend">' + cells + "</div></div>")


def render_map_page(store_dir: str) -> str:
    """Map: the immersive Universe Canvas framed as a first-class VIEW. When a canvas has been
    generated it is framed READ-ONLY (an <iframe> filling the width + a direct link to
    ``/map/canvas``) with a compact celestial legend; when none exists yet, an honest empty
    state carrying the exact build command -- never a fabricated star-field, never a dead link."""
    intro = ('<p class="note">The Map is the Universe Canvas &mdash; an immersive star-field view '
             "of the same persisted pulse data, served READ-ONLY as a generated artifact. Nothing "
             "here is fetched and nothing here can act on a position; it is a read-only "
             "intelligence map you look through, like a telescope.</p>")
    legend = _celestial_legend_html()

    if generated_canvas_present():
        framed = (
            '<h2>Universe Canvas</h2><div class="panel">'
            '<p class="note">Framed below read-only from the generated artifact &mdash; served '
            "verbatim, never rewritten or duplicated. If the frame is cramped, open it as its "
            "own full document:</p>"
            '<a class="canvas-open" href="/map/canvas">Open the Universe Canvas &rarr;</a>'
            '<iframe class="canvas-frame" src="/map/canvas" loading="lazy" '
            'title="Universe Canvas &mdash; read-only intelligence map"></iframe>'
            '<p class="note">The frame is the generated <span class="mono">'
            "universe.html</span>, shown as-is; the Map adds only this legend around it.</p>"
            "</div>")
        body = intro + framed + legend
    else:
        empty = (
            '<h2>Universe Canvas</h2><div class="panel">'
            '<p class="note">No Universe Canvas has been generated yet, so there is nothing to '
            "frame (never a fabricated star-field, never a dead link). The canvas is a read-only "
            "intelligence map; generate it once with the Universe UI and reload this tab:</p>"
            '<code class="cmd">{cmd}</code>'
            '<p class="note">The command writes the canvas to <span class="mono">'
            "generated/universe_ui/</span>; the Map picks it up automatically and frames it "
            "here.</p></div>").format(cmd=_esc(GENERATE_CANVAS_COMMAND))
        body = intro + empty + legend

    # A quiet secondary panel keeps any per-store canvas artifacts reachable too (never a dead
    # link) -- the primary Map above is the immersive generated canvas.
    present = canvas_artifacts(store_dir)
    if present:
        links = "".join(
            '<li><a href="/canvas/{0}">{1}</a></li>'.format(
                _esc(name), _esc(name[:-len(".html")].replace("_", " ")))
            for name in present)
        body += ('<h2>Per-store canvas pages</h2><div class="panel"><ul>' + links
                 + '</ul><p class="note">Static canvas pages generated into this store &mdash; '
                 "served read-only.</p></div>")
    return _page(store_dir, "Map", "/map", body)


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
