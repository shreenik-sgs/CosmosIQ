"""The CosmosIQ backend API -- a PURE dispatcher over the 013B/015 stores (IMPLEMENTATION-016A).

:func:`dispatch` is the ENTIRE product surface: a pure function from a plain request dict
(``{"method", "path", "query", "body"}``) to a plain response dict (``{"status", "headers",
"body"}``). It reads and appends to the Phase-013 append-only JSONL stores and the Phase-015
schedule journal / alert inbox under a caller-supplied ``store_dir`` -- and NOTHING else.

HARD DISCIPLINE (Phase 016; ARCHITECTURE_CONTRACT_012 + the 013/015 contracts stay in force):

* **Pure.** NO sockets, NO ``http`` import, NO network, NO thread, NO loop, NO daemon. The
  operator-started shell lives in :mod:`cosmosiq_app.server`; the offline test suite exercises
  THIS module only.
* **No wall clock.** ``now`` is always an injected string: a POST body may carry ``now`` (tests),
  or the shell passes wall-clock ``now`` at the shell boundary -- dispatch itself never calls
  ``.now()`` / ``time.time()``.
* **Labels + counts, never scores.** Every response carries closed labels and volume counts;
  no score / rank / rating / investability field is constructed anywhere here, and no secret
  ever appears in a response (credential PRESENCE labels only, upstream).
* **Append-only writes.** Ack / pause / resume / settings / pulse all APPEND new records via
  the 013B/015 store functions; no stored line is ever rewritten.
* **No trading endpoint exists.** Any buy / sell / order / submit / execute / trade / broker
  route is refused with 403: execution is manual preview only.

Deterministic, stdlib-only, Python 3.9, OFFLINE.
"""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional, Tuple

from reality_mesh import (
    ALL_POLICIES,
    AgentRunLedger,
    AppendOnlyStore,
    BottleneckEvidenceAgent,
    CustomerEvidenceAgent,
    DataQualityStore,
    EventStore,
    FindingStore,
    LeadershipEvidenceAgent,
    MacroRegimeAgent,
    MarketRegimeAgent,
    NewsFilingsAgent,
    ReplayHarness,
    ReplayRequest,
    RunStore,
    SectorRotationAgent,
    SignalStore,
    SocialNarrativeAgent,
    SupplierEvidenceAgent,
    TechnicalRegimeAgent,
    ThemePulseStore,
    ThemeRotationAgent,
    acknowledge_alert,
    acknowledged_alerts,
    alerts_with_status,
    append_schedule_state,
    build_default_registry,
    build_default_schedule,
    load_schedule_state,
    pause,
    persist_and_summarize,
    resume,
    run_pulse,
    schedule_to_dict,
    throttled,
    unacknowledged_alerts,
)

__all__ = [
    "APP_NAME",
    "EXECUTION_REFUSAL",
    "TRADE_PATH_TOKENS",
    "SettingsStore",
    "current_settings",
    "dispatch",
]

APP_NAME = "CosmosIQ"

# The refusal returned (with 403) for ANY trade-like route. No such endpoint exists; none is
# hidden behind a flag; the refusal names the policy in plain English.
EXECUTION_REFUSAL = "execution is manual preview only; no trading endpoints exist"

# Path tokens that mark an attempted trade-like route (matched as substrings of the lowercased
# path segments, BEFORE routing -- a trade route is refused even if it would 404 anyway).
TRADE_PATH_TOKENS: Tuple[str, ...] = (
    "buy", "sell", "order", "submit", "execute", "trade", "broker",
)

_JSON_HEADERS = {"Content-Type": "application/json"}
_HTML_HEADERS = {"Content-Type": "text/html; charset=utf-8"}

# The record kinds the per-run stores expose (URL tail -> store class + response key).
_RUN_RECORD_STORES = {
    "signals": SignalStore,
    "findings": FindingStore,
    "events": EventStore,
    "theme_pulses": ThemePulseStore,
}

# The sensor agents that actually RUN inside a pulse (012K core five + the 014 conditional
# six). Everything else in the 26-descriptor registry is descriptor-only -- an honest label,
# never an implied capability.
_IMPLEMENTED_AGENT_FACTORIES = (
    MarketRegimeAgent,
    SectorRotationAgent,
    ThemeRotationAgent,
    NewsFilingsAgent,
    SocialNarrativeAgent,
    TechnicalRegimeAgent,
    MacroRegimeAgent,
    CustomerEvidenceAgent,
    SupplierEvidenceAgent,
    BottleneckEvidenceAgent,
    LeadershipEvidenceAgent,
)


# --------------------------------------------------------------------------- #
# The settings journal -- append-style, corrections-not-mutations (013B shape)  #
# --------------------------------------------------------------------------- #
class SettingsStore(AppendOnlyStore):
    """The operator settings journal: one JSONL snapshot line per PUT, never rewritten.

    Composes the 013B :class:`~reality_mesh.stores.AppendOnlyStore`, so it inherits the same
    hard guarantees: no update/delete, the replay envelope, credential-key + trade/score-key
    refusal, and deterministic ``sort_keys`` JSONL. A settings change is a NEW full snapshot
    line (a correction); prior lines stay byte-unchanged forever, and the CURRENT settings are
    simply the latest line.
    """

    filename = "settings_store.jsonl"
    record_cls = None                       # plain payload dicts (settings snapshots)
    id_field = None
    timestamp_field = None


# The three operator-editable settings axes (plain JSON values; the API stores, never
# interprets, them -- resolution to pulse scopes happens at explicit pulse/tick time).
_SETTINGS_KEYS = ("watchlists", "themes", "subscriptions")
_SETTINGS_BODY_KEYS = _SETTINGS_KEYS + ("at", "now", "note")


def current_settings(store_dir: str) -> Tuple[Dict[str, Any], int]:
    """The latest journaled settings snapshot plus the journal revision (line count).

    Revision 0 with empty defaults if nothing was ever journaled -- an explicit empty state,
    never a fabricated one.
    """
    records = SettingsStore(store_dir).read_records()
    if not records:
        return {key: [] for key in _SETTINGS_KEYS}, 0
    payload = dict(records[-1].get("payload", {}) or {})
    return {key: list(payload.get(key, []) or []) for key in _SETTINGS_KEYS}, len(records)


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _json(status: int, body: Any) -> Dict[str, Any]:
    return {"status": int(status), "headers": dict(_JSON_HEADERS), "body": body}


def _ok(body: Any) -> Dict[str, Any]:
    return _json(200, body)


def _error(status: int, reason: str) -> Dict[str, Any]:
    return _json(status, {"error": str(reason)})


def _html(status: int, text: str) -> Dict[str, Any]:
    """A server-rendered HTML page response (016B). Body is the full page string."""
    return {"status": int(status), "headers": dict(_HTML_HEADERS), "body": str(text)}


def _to_plain(obj: Any) -> Any:
    """A frozen dataclass (or nested structure) lowered to JSON-able dicts/lists."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return _to_plain(asdict(obj))
    if isinstance(obj, dict):
        return {key: _to_plain(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(value) for value in obj]
    return obj


def _compact_instant(now: str) -> str:
    """An id-safe token from an injected ISO instant (pure string filtering, no parsing)."""
    return "".join(ch for ch in str(now) if ch.isalnum()) or "unstamped"


def _runs_newest_first(store_dir: str) -> List[Any]:
    """Distinct persisted runs, NEWEST first; the latest superseding line wins per run_id.

    (A scheduled run appends a correction line for the same run_id -- append-only
    supersession -- so the latest line is the current record of that run.)
    """
    by_id: Dict[str, Any] = {}
    sequence: List[str] = []
    for run in RunStore(store_dir).read_all():
        if run.run_id not in by_id:
            sequence.append(run.run_id)
        by_id[run.run_id] = run
    return [by_id[run_id] for run_id in reversed(sequence)]


def _get_run(store_dir: str, run_id: str) -> Optional[Any]:
    """The current (latest superseding) persisted record of one run, or None."""
    runs = RunStore(store_dir).query(run_id=run_id)
    return runs[-1] if runs else None


def _load_schedule(store_dir: str):
    """The latest journaled schedule, or a fresh default schedule if never journaled."""
    return load_schedule_state(store_dir) or build_default_schedule()


def _harness(store_dir: str) -> ReplayHarness:
    return ReplayHarness(EventStore(store_dir), FindingStore(store_dir),
                         SignalStore(store_dir), ThemePulseStore(store_dir),
                         RunStore(store_dir))


def _run_summary_dict(run: Any) -> Dict[str, Any]:
    """One run as a plain dict (labels + volume counts -- the PulseRun shape verbatim)."""
    return _to_plain(run)


# --------------------------------------------------------------------------- #
# Route handlers (each pure: stores in, plain dict out)                         #
# --------------------------------------------------------------------------- #
def _handle_health(store_dir: str) -> Dict[str, Any]:
    present = os.path.isdir(store_dir)
    counts = {
        "runs": len(_runs_newest_first(store_dir)) if present else 0,
        "events": len(EventStore(store_dir).read_records()) if present else 0,
        "findings": len(FindingStore(store_dir).read_records()) if present else 0,
        "signals": len(SignalStore(store_dir).read_records()) if present else 0,
        "theme_pulses": len(ThemePulseStore(store_dir).read_records()) if present else 0,
        "alerts": len(alerts_with_status(store_dir)) if present else 0,
        "data_quality_records": len(DataQualityStore(store_dir).read_records()) if present else 0,
    }
    return _ok({
        "app": APP_NAME,
        "status": "ok",
        "store_dir_present": present,
        "counts": counts,
        "notes": ["local app; operator-started shell; read-only + explicit manual actions",
                  "labels and volume counts only -- no score, no rank, no trading endpoint"],
    })


def _handle_runs_list(store_dir: str) -> Dict[str, Any]:
    runs = _runs_newest_first(store_dir)
    return _ok({"runs": [_run_summary_dict(r) for r in runs], "count": len(runs)})


def _handle_run_detail(store_dir: str, run_id: str) -> Dict[str, Any]:
    run = _get_run(store_dir, run_id)
    if run is None:
        return _error(404, "no persisted run with run_id {0!r}".format(run_id))
    agent_results = AgentRunLedger(store_dir).results_for_run(run_id)
    dq_records = DataQualityStore(store_dir).query(run_id=run_id)
    gate_overall = ""
    for record in dq_records:
        if record.category == "gate_overall":
            gate_overall = record.status
    return _ok({
        "run": _run_summary_dict(run),
        "agent_results": [_to_plain(r) for r in agent_results],
        "data_quality_records": [_to_plain(r) for r in dq_records],
        "gate_overall": gate_overall,
    })


def _handle_run_records(store_dir: str, run_id: str, kind: str) -> Dict[str, Any]:
    run = _get_run(store_dir, run_id)
    if run is None:
        return _error(404, "no persisted run with run_id {0!r}".format(run_id))
    store = _RUN_RECORD_STORES[kind](store_dir)
    records = store.query(run_id=run_id)
    return _ok({"run_id": run_id, kind: [_to_plain(r) for r in records],
                "count": len(records)})


def _handle_alerts_list(store_dir: str, query: Dict[str, Any]) -> Dict[str, Any]:
    wanted = str(query.get("status", "all") or "all").lower()
    if wanted == "unacked":
        alerts = unacknowledged_alerts(store_dir)
    elif wanted == "acked":
        alerts = acknowledged_alerts(store_dir)
    elif wanted == "all":
        alerts = alerts_with_status(store_dir)
    else:
        return _error(400, "unknown alerts status filter {0!r} (allowed: unacked, acked, "
                           "all)".format(wanted))
    return _ok({"alerts": [_to_plain(a) for a in alerts], "count": len(alerts),
                "status_filter": wanted})


def _handle_alert_ack(store_dir: str, alert_id: str, body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        return _error(400, "request body must be a JSON object with 'at' (and optionally "
                           "'acknowledged_by' / 'note')")
    at = str(body.get("at", "") or "").strip()
    if not at:
        return _error(400, "acknowledging an alert requires an injected 'at' instant in the "
                           "body (the dispatcher never reads the wall clock)")
    acknowledged_by = str(body.get("acknowledged_by", "") or "operator")
    note = str(body.get("note", "") or "")
    try:
        ack_id = acknowledge_alert(store_dir, alert_id, at=at,
                                   acknowledged_by=acknowledged_by, note=note)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "unknown alert_id" in message else 400
        return _error(status, message)
    return _ok({"ack_id": ack_id, "alert_id": alert_id, "acknowledged_by": acknowledged_by,
                "at": at, "append_only": True,
                "note": "acknowledgment appended as a NEW record; the alert line is "
                        "byte-unchanged"})


def _handle_schedule_get(store_dir: str, query: Dict[str, Any], now: str) -> Dict[str, Any]:
    schedule = _load_schedule(store_dir)
    body: Dict[str, Any] = {
        "schedule": schedule_to_dict(schedule),
        "policy_count": len(schedule.policies),
        "paused_all": schedule.paused_all,
    }
    effective_now = str(query.get("now", "") or "") or now
    if effective_now:
        try:
            body["throttled"] = throttled(schedule, effective_now)
            body["as_of"] = effective_now
        except ValueError as exc:
            return _error(400, str(exc))
    return _ok(body)


def _handle_schedule_pause_resume(store_dir: str, body: Any, now: str, *,
                                  resuming: bool) -> Dict[str, Any]:
    if not isinstance(body, dict):
        return _error(400, "request body must be a JSON object with 'policy_id' (or 'all') "
                           "and 'at'")
    policy_id = str(body.get("policy_id", "") or "").strip()
    if not policy_id:
        return _error(400, "pause/resume requires 'policy_id' (a cadence policy id, or "
                           "'{0}' for every policy)".format(ALL_POLICIES))
    at = str(body.get("at", "") or "").strip() or now
    if not at:
        return _error(400, "pause/resume requires an injected 'at' instant (the dispatcher "
                           "never reads the wall clock)")
    schedule = _load_schedule(store_dir)
    action = "resume" if resuming else "pause"
    try:
        new_schedule = (resume if resuming else pause)(schedule, policy_id, at)
        record_id = append_schedule_state(
            store_dir, new_schedule, now=at,
            note="api {0} {1} at {2}".format(action, policy_id, at))
    except ValueError as exc:
        return _error(400, str(exc))
    return _ok({
        "action": action,
        "policy_id": policy_id,
        "at": at,
        "journaled_record_id": record_id,
        "paused_all": new_schedule.paused_all,
        "schedule": schedule_to_dict(new_schedule),
    })


def _handle_pulse(store_dir: str, body: Any, now: str) -> Dict[str, Any]:
    if not isinstance(body, dict):
        return _error(400, "request body must be a JSON object with 'watchlist' and 'themes' "
                           "(and optionally 'now' / 'run_id')")
    effective_now = str(body.get("now", "") or "") or now
    if not effective_now.strip():
        return _error(400, "a manual pulse requires an injected 'now' instant (body 'now' or "
                           "the shell boundary) -- the dispatcher never reads the wall clock")
    run_id = str(body.get("run_id", "") or "").strip() \
        or "api.manual.{0}".format(_compact_instant(effective_now))
    if _get_run(store_dir, run_id) is not None:
        return _error(409, "run_id {0!r} is already persisted (append-only history) -- pass "
                           "a distinct 'now' or an explicit 'run_id'".format(run_id))
    try:
        pulse = run_pulse(body.get("watchlist"), body.get("themes"), now=effective_now)
        pulse_run, replay_result, _panel = persist_and_summarize(
            pulse, store_dir=store_dir, run_id=run_id, now=effective_now)
    except (ValueError, FileNotFoundError) as exc:
        return _error(400, str(exc))
    return _ok({
        "run_id": run_id,
        "trigger_type": pulse_run.trigger_type,      # always "manual" on this endpoint
        "mode": pulse_run.mode,
        "counts": {
            "events_loaded": pulse.events_loaded,
            "findings": len(pulse.findings),
            "signals": len(pulse.signals),
            "theme_pulses": len(pulse.theme_pulses),
            "agent_runs": len(pulse.agent_runs),
        },
        "gaps": list(pulse.data_gaps),
        "replay": {
            "deterministic_match": replay_result.deterministic_match,
            "differences": len(replay_result.differences),
        },
    })


def _handle_replay(store_dir: str, run_id: str) -> Dict[str, Any]:
    run = _get_run(store_dir, run_id)
    if run is None:
        return _error(404, "no persisted run with run_id {0!r}".format(run_id))
    result = _harness(store_dir).replay(ReplayRequest(run_id=run_id), now=run.started_at)
    return _ok({
        "run_id": run_id,
        "replay_id": result.replay_id,
        "deterministic_match": result.deterministic_match,
        "differences": len(result.differences),
        "difference_details": list(result.differences),
        "counts": {
            "events_replayed": result.events_replayed,
            "findings_replayed": result.findings_replayed,
            "signals_replayed": result.signals_replayed,
        },
    })


def _handle_settings_get(store_dir: str) -> Dict[str, Any]:
    settings, revision = current_settings(store_dir)
    return _ok({"settings": settings, "revision": revision,
                "journal": SettingsStore.filename,
                "note": "append-style journal -- a change is a NEW snapshot line, never a "
                        "mutation"})


def _handle_settings_put(store_dir: str, body: Any, now: str) -> Dict[str, Any]:
    if not isinstance(body, dict):
        return _error(400, "request body must be a JSON object carrying any of {0}".format(
            list(_SETTINGS_KEYS)))
    unknown = sorted(set(body) - set(_SETTINGS_BODY_KEYS))
    if unknown:
        return _error(400, "unknown settings key(s) {0} (allowed: {1})".format(
            unknown, list(_SETTINGS_BODY_KEYS)))
    provided = [key for key in _SETTINGS_KEYS if key in body]
    if not provided:
        return _error(400, "settings PUT must carry at least one of {0}".format(
            list(_SETTINGS_KEYS)))
    for key in provided:
        if not isinstance(body[key], list):
            return _error(400, "settings {0!r} must be a JSON list".format(key))
    settings, revision = current_settings(store_dir)
    for key in provided:
        settings[key] = body[key]           # full-field replacement inside a NEW snapshot
    at = str(body.get("at", "") or body.get("now", "") or "") or now
    snapshot = {"kind": "settings", "recorded_at": at,
                "note": str(body.get("note", "") or "")}
    snapshot.update(settings)
    journal = SettingsStore(store_dir)
    record_id = "settings-{0:06d}".format(len(journal.read_records()) + 1)
    try:
        journal.append(snapshot, timestamp=at, record_id=record_id)
    except ValueError as exc:               # credential-like / trade-like key refused
        return _error(400, str(exc))
    return _ok({"settings": settings, "revision": revision + 1,
                "journaled_record_id": record_id, "append_only": True})


def _handle_coverage() -> Dict[str, Any]:
    implemented_ids = frozenset(
        factory().descriptor.agent_id for factory in _IMPLEMENTED_AGENT_FACTORIES)
    agents = []
    for descriptor in build_default_registry().descriptors():
        status = ("implemented" if descriptor.agent_id in implemented_ids
                  else "descriptor_only")
        agents.append({
            "agent_id": descriptor.agent_id,
            "agent_name": descriptor.agent_name,
            "layer": descriptor.layer,
            "discipline": descriptor.discipline,
            "agent_type": descriptor.agent_type,
            "subagent_count": len(descriptor.subagents),
            "implementation_status": status,     # an honest label, never an implied capability
        })
    implemented = sum(1 for a in agents if a["implementation_status"] == "implemented")
    return _ok({
        "agents": agents,
        "total": len(agents),
        "implemented": implemented,
        "descriptor_only": len(agents) - implemented,
    })


# --------------------------------------------------------------------------- #
# dispatch -- the pure router                                                   #
# --------------------------------------------------------------------------- #
def dispatch(request: Dict[str, Any], *, store_dir: str, now: str = "") -> Dict[str, Any]:
    """Route ONE request dict onto the stores; return ONE response dict. Pure and offline.

    ``request`` carries ``method`` / ``path`` / ``query`` (a str->str dict) / ``body`` (a
    parsed JSON value or None). ``now`` is an injected instant the shell supplies at its
    boundary; a POST body's own ``now``/``at`` takes precedence so tests stay fully
    deterministic. Unknown route -> 404; malformed body -> 400 with a plain reason; ANY
    trade-like route -> 403 (no trading endpoint exists).
    """
    if not str(store_dir).strip():
        raise ValueError("dispatch requires a non-empty store_dir")
    method = str(request.get("method", "GET") or "GET").upper()
    path = str(request.get("path", "") or "")
    query = dict(request.get("query") or {})
    body = request.get("body")

    raw = [seg for seg in path.strip("/").split("/") if seg]   # ids keep their case
    segments = [seg.lower() for seg in raw]                    # routing is case-insensitive

    # The execution guard runs BEFORE routing: a trade-like path is refused outright, never
    # merely unrouted.
    for segment in segments:
        for token in TRADE_PATH_TOKENS:
            if token in segment:
                return _error(403, EXECUTION_REFUSAL)

    if not segments or segments[0] != "api":
        # 016B: the server-rendered app pages live OUTSIDE /api (GET-only, text/html).
        if method == "GET":
            page = _dispatch_page(segments, raw, store_dir)
            if page is not None:
                return page
        return _error(404, "unknown route {0!r} -- the CosmosIQ pages live at / /runs "
                           "/alerts /settings and the API lives under /api".format(path))
    tail = segments[1:]
    raw_tail = raw[1:]

    if tail == ["health"]:
        return _require(method, "GET", path) or _handle_health(store_dir)

    if tail == ["runs"]:
        return _require(method, "GET", path) or _handle_runs_list(store_dir)
    if len(tail) == 2 and tail[0] == "runs":
        return _require(method, "GET", path) or _handle_run_detail(store_dir, raw_tail[1])
    if len(tail) == 3 and tail[0] == "runs" and tail[2] in _RUN_RECORD_STORES:
        return _require(method, "GET", path) or _handle_run_records(
            store_dir, raw_tail[1], tail[2])

    if tail == ["alerts"]:
        return _require(method, "GET", path) or _handle_alerts_list(store_dir, query)
    if len(tail) == 3 and tail[0] == "alerts" and tail[2] == "ack":
        return _require(method, "POST", path) or _handle_alert_ack(
            store_dir, raw_tail[1], body)

    if tail == ["schedule"]:
        return _require(method, "GET", path) or _handle_schedule_get(store_dir, query, now)
    if tail == ["schedule", "pause"]:
        return _require(method, "POST", path) or _handle_schedule_pause_resume(
            store_dir, body, now, resuming=False)
    if tail == ["schedule", "resume"]:
        return _require(method, "POST", path) or _handle_schedule_pause_resume(
            store_dir, body, now, resuming=True)

    if tail == ["pulse"]:
        return _require(method, "POST", path) or _handle_pulse(store_dir, body, now)

    if len(tail) == 2 and tail[0] == "replay":
        return _require(method, "GET", path) or _handle_replay(store_dir, raw_tail[1])

    if tail == ["settings"]:
        if method == "GET":
            return _handle_settings_get(store_dir)
        if method == "PUT":
            return _handle_settings_put(store_dir, body, now)
        return _error(405, "method {0} not allowed for {1} (allowed: GET, PUT)".format(
            method, path))

    if tail == ["coverage"]:
        return _require(method, "GET", path) or _handle_coverage()

    return _error(404, "unknown route {0!r}".format(path))


def _dispatch_page(segments: List[str], raw: List[str],
                   store_dir: str) -> Optional[Dict[str, Any]]:
    """Route ONE GET request onto the 016B server-rendered pages (None -> not a page route).

    Pages are PURE functions from the stores to full HTML (:mod:`cosmosiq_app.pages`); the
    import is deliberately function-local so the pure-dispatcher module keeps loading first
    and the page layer stays an additive slice on top of it. An unknown run id renders the
    honest 404 page with a 404 status. ``/canvas/<name>`` serves a generated Universe Canvas
    artifact READ-ONLY when (and only when) it exists under the store -- never a dead link.
    """
    from . import pages as _pages

    if not segments:
        return _html(200, _pages.render_app_home(store_dir))
    if segments == ["runs"]:
        return _html(200, _pages.render_run_history(store_dir))
    if len(segments) == 2 and segments[0] == "runs":
        run_id = raw[1]
        if _get_run(store_dir, run_id) is None:
            return _html(404, _pages.render_not_found(store_dir, "/runs/" + run_id))
        return _html(200, _pages.render_run_detail(store_dir, run_id))
    if len(segments) == 2 and segments[0] == "replay":
        run_id = raw[1]
        if _get_run(store_dir, run_id) is None:
            return _html(404, _pages.render_not_found(store_dir, "/replay/" + run_id))
        return _html(200, _pages.render_replay_view(store_dir, run_id))
    if segments == ["alerts"]:
        return _html(200, _pages.render_alert_inbox(store_dir))
    if segments == ["settings"]:
        return _html(200, _pages.render_settings_page(store_dir))
    if len(segments) == 2 and segments[0] == "canvas":
        name = raw[1]
        if name in _pages.CANVAS_PAGES:
            artifact = os.path.join(store_dir, _pages.CANVAS_DIRNAME, name)
            if os.path.isfile(artifact):
                with open(artifact, encoding="utf-8") as handle:
                    return _html(200, handle.read())
        return _html(404, _pages.render_not_found(store_dir, "/canvas/" + name))
    return None


def _require(method: str, allowed: str, path: str) -> Optional[Dict[str, Any]]:
    """A 405 response when ``method`` is not ``allowed`` for this route, else None."""
    if method != allowed:
        return _error(405, "method {0} not allowed for {1} (allowed: {2})".format(
            method, path, allowed))
    return None
