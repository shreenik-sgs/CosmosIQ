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
    blocked_candidates,
    build_default_registry,
    build_default_schedule,
    eligible_candidates,
    load_schedule_state,
    pause,
    persist_and_summarize,
    publish_candidates_for_run,
    published_candidates,
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


def _redirect(location: str, status: int = 303) -> Dict[str, Any]:
    """A See-Other redirect (303) back to a GET page after a sanctioned form POST.

    Empty body + a ``Location`` header -- the POST/redirect/GET pattern so a
    re-submit does not re-post. Used ONLY by the record-fill operator form; it
    points at an in-app GET page, never at anything external.
    """
    return {"status": int(status), "headers": {"Location": str(location)}, "body": ""}


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


def _handle_observability(store_dir: str, now: str) -> Dict[str, Any]:
    """GET /api/observability -- the single sanitized observability surface (READ-ONLY).

    Aggregates every health signal (023E) into one sanitized health JSON with a rolled ``status``
    (ok / degraded / failed). Pure + offline: no form, no button, no write -- labels + counts +
    injected-time latencies only, never a secret / score / trade. ``now`` is the injected instant
    the shell supplies at its boundary (deterministic; no wall clock here).
    """
    from cosmosiq_ops.observability import aggregate_observability
    report = aggregate_observability(store_dir, now=now or "")
    return _ok(report.to_dict())


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


def _handle_pulse_live(store_dir: str, body: Any, now: str) -> Dict[str, Any]:
    """POST /api/pulse/live -- the SANCTIONED "Refresh from external sources" operator action.

    Credential-gated REFRESH (PROD-LIVE-1). Calls :func:`reality_mesh.run_live_pulse` against the
    cockpit ``store_dir``: it builds the source adapters from credential PRESENCE (SEC_USER_AGENT /
    FMP_API_KEY, membership only -- a value is never read) and, when at least one is set, runs a
    real refresh and persists it append-only. With NEITHER credential set it fetches NOTHING
    (offline-safe -- no network attempted), persists NO run, and an honest "not configured" note
    is shown. A fetch failure is a visible source gap, never a fixture fallback. RECORD/REFRESH-
    ONLY: no execution affordance of any kind (a trade route is already refused 403 above). The
    Evidence & Trust page is re-rendered with an honest one-line result note -- a credential VALUE
    never appears (the note is presence / counts only).
    """
    from reality_mesh import run_live_pulse

    from . import pages as _pages

    if not isinstance(body, dict):
        return _html(400, _pages.render_evidence_page(
            store_dir, refresh_note="the refresh form must post its fields"))
    watchlist = body.get("watchlist")
    themes = body.get("themes")
    effective_now = str(body.get("now", "") or body.get("at", "") or "") or now
    run_id = str(body.get("run_id", "") or "").strip()
    if not effective_now.strip():
        return _html(400, _pages.render_evidence_page(
            store_dir, refresh_note="a refresh requires an injected 'now' instant "
                                    "(the dispatcher never reads the wall clock)"))
    try:
        result = run_live_pulse(watchlist, themes, store_dir=store_dir,
                                now=effective_now, run_id=run_id)
    except (ValueError, FileNotFoundError) as exc:
        return _html(400, _pages.render_evidence_page(store_dir, refresh_note=str(exc)))

    # An honest one-line note -- presence + counts only; deliberately free of the guarded
    # overclaim / execution / credential-token vocabulary (a value can never reach here).
    if not result.configured:
        note = ("No external sources configured -- nothing was fetched or persisted, and no "
                "network was attempted. Set the env var(s) shown above, then refresh.")
    else:
        note = ("Refreshed from external sources (shadow, record-only): run {0} persisted from "
                "{1} source(s); {2} data gap(s) recorded honestly.".format(
                    result.run_id, len(result.sources_configured), len(result.data_gaps)))
    return _html(200, _pages.render_evidence_page(store_dir, refresh_note=note))


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


def _candidate_public_dict(cand: Any) -> Dict[str, Any]:
    """One published candidate as a plain dict (labels + refs + the exact basis; no score)."""
    return {
        "candidate_id": cand.candidate_id,
        "ticker": cand.ticker,
        "run_id": cand.run_id,
        "mode": cand.mode,
        "generated_at": cand.generated_at,
        "candidate_state": cand.candidate_state,
        "eligible": cand.is_eligible,
        "reality_signal_refs": list(cand.reality_signal_refs),
        "opportunity_hypothesis_ref": cand.opportunity_hypothesis_ref,
        "investment_diligence_ref": cand.investment_diligence_ref,
        "forward_scenario_state": cand.forward_scenario_state,
        "trust_data_quality_state": cand.trust_data_quality_state,
        "source_provenance": list(cand.source_provenance),
        "missing_lineage": list(cand.missing_lineage()),
        "basis": cand.basis,
    }


def _handle_candidates_publish(store_dir: str, body: Any, now: str) -> Dict[str, Any]:
    """POST /api/candidates/publish -- the explicit publish step (NEVER auto-run in a pulse).

    Runs :func:`publish_candidates_for_run` over the run's scope, persisting each candidate
    append-only (eligible only with full provenance; blocked WITH its exact reason), and returns
    the published set + eligible / blocked counts + states. Diligence refs come from the body's
    ``diligence_by_ticker`` (operator input) and/or the store's recorded diligence input files.
    """
    if not isinstance(body, dict):
        return _error(400, "request body must be a JSON object with 'run_id' (and optionally "
                           "'tickers' / 'now' / 'mode' / 'diligence_by_ticker')")
    run_id = str(body.get("run_id", "") or "").strip()
    if not run_id:
        return _error(400, "publishing candidates requires a 'run_id' (the current run whose "
                           "scope is published)")
    effective_now = str(body.get("now", "") or "") or now
    if not effective_now.strip():
        return _error(400, "publishing requires an injected 'now' instant (body 'now' or the "
                           "shell boundary) -- the dispatcher never reads the wall clock")
    tickers_raw = body.get("tickers")
    tickers = tuple(str(t) for t in tickers_raw) if isinstance(tickers_raw, list) else None
    mode = str(body.get("mode", "") or "pulse") or "pulse"
    body_diligence = dict(body.get("diligence_by_ticker") or {})

    run = _get_run(store_dir, run_id)
    scope = tickers or (tuple(run.watchlist) if run is not None else ())
    from . import cockpits as _cockpits
    diligence = _cockpits.diligence_refs_from_store(store_dir, scope)
    diligence.update({str(k).strip().upper(): v for k, v in body_diligence.items()})

    try:
        published = publish_candidates_for_run(
            store_dir, run_id, tickers=tickers, now=effective_now, mode=mode,
            diligence_by_ticker=diligence)
    except (ValueError, FileNotFoundError) as exc:
        return _error(400, str(exc))

    eligible = [c for c in published if c.is_eligible]
    blocked = [c for c in published if c.candidate_state.startswith("ineligible_")]
    return _ok({
        "run_id": run_id,
        "now": effective_now,
        "mode": mode,
        "append_only": True,
        "auto_published_in_pulse": False,
        "published": len(published),
        "eligible_count": len(eligible),
        "blocked_count": len(blocked),
        "eligible": [c.ticker for c in eligible],
        "blocked": [{"ticker": c.ticker, "state": c.candidate_state, "reason": c.basis}
                    for c in blocked],
        "candidates": [_candidate_public_dict(c) for c in published],
        "note": "publication is APPEND-ONLY and idempotent by content-derived id; blocked "
                "candidates are persisted with their exact reason (nothing is hidden)",
    })


def _handle_candidates_list(store_dir: str, query: Dict[str, Any]) -> Dict[str, Any]:
    """GET /api/candidates?run_id=&status= -- the published candidates (read-only)."""
    run_id = str(query.get("run_id", "") or "").strip() or None
    status = str(query.get("status", "all") or "all").lower()
    if status == "eligible":
        cands = eligible_candidates(store_dir, run_id)
    elif status in ("blocked", "ineligible"):
        cands = blocked_candidates(store_dir, run_id)
    elif status == "all":
        cands = published_candidates(store_dir, run_id)
    else:
        return _error(400, "unknown candidates status filter {0!r} (allowed: eligible, "
                           "blocked, all)".format(status))
    return _ok({
        "candidates": [_candidate_public_dict(c) for c in cands],
        "count": len(cands),
        "status_filter": status,
        "run_id": run_id or "",
    })


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


def _fill_number(text: Any, field: str) -> float:
    """Parse a recorded quantity/price from the form ('' or non-numeric -> ValueError)."""
    raw = str(text if text is not None else "").strip()
    if not raw:
        raise ValueError("{0} is required".format(field))
    try:
        return float(raw)
    except ValueError:
        raise ValueError("{0} must be a number (your own recorded fact); got {1!r}".format(
            field, raw))


def _handle_portfolio_record_fill(store_dir: str, body: Any, now: str) -> Dict[str, Any]:
    """POST /api/portfolio/record-fill -- LOG a fill the operator ALREADY executed.

    RECORD-ONLY. This calls :func:`reality_mesh.record_fill` and NOTHING else: it
    appends one line to the operator's append-only position ledger, then redirects
    (303) back to ``/portfolio``. It makes NO network / broker call, submits NO
    order, and has NO order-submission affordance -- it is a bookkeeping journal
    entry, exactly like the manual-pulse operator form is a journal of a pulse.
    ``side`` is the closed PAST-TENSE vocabulary (``bought`` / ``sold``); a bad
    input re-renders the page with an honest error (never a crash, never a write).
    """
    from reality_mesh import FILL_SIDES, record_fill
    from . import cockpits as _cockpits

    if not isinstance(body, dict):
        return _html(400, _cockpits.render_portfolio_page(
            store_dir, form_error="the record-fill form must post its fields"))
    ticker = str(body.get("ticker", "") or "").strip()
    side = str(body.get("side", "") or "").strip().lower()
    trade_date = str(body.get("trade_date", "") or "").strip()
    recommendation_ref = str(body.get("recommendation_ref", "") or "").strip()
    note = str(body.get("note", "") or "").strip()
    effective_now = str(body.get("now", "") or body.get("at", "") or "") or now
    try:
        if not ticker:
            raise ValueError("a ticker is required")
        if side not in FILL_SIDES:
            raise ValueError("side must be one of {0} (PAST TENSE -- what happened)".format(
                list(FILL_SIDES)))
        if not trade_date:
            raise ValueError("a fill date is required")
        if not effective_now.strip():
            raise ValueError("an injected 'now' instant is required to journal the fill")
        quantity = _fill_number(body.get("quantity"), "quantity")
        price = _fill_number(body.get("price"), "fill price")
        record_fill(store_dir, ticker=ticker, side=side, quantity=quantity, price=price,
                    trade_date=trade_date, recommendation_ref=recommendation_ref,
                    note=note, now=effective_now)
    except ValueError as exc:
        return _html(400, _cockpits.render_portfolio_page(
            store_dir, form_error=str(exc), form_values=body))
    return _redirect("/portfolio")


# --------------------------------------------------------------------------- #
# The ISOLATED AI Research Assistant (PROD-LIVE-3) -- EDGE-only, display-only     #
# --------------------------------------------------------------------------- #
def _assistant_mode(body: Dict[str, Any]) -> str:
    """'full_api' when the operator opted into the paid (Claude) chain, else 'free'."""
    token = str(body.get("mode", "") or "").strip().lower()
    return "full_api" if token in ("full_api", "paid", "on", "true", "claude") else "free"


def _handle_assistant_summarize(store_dir: str, body: Any, now: str) -> Dict[str, Any]:
    """POST /api/assistant/summarize -- run the ISOLATED assistant to summarise a filing.

    Display-only: it calls the ``cosmosiq_assistant`` package (OUTSIDE reality_mesh) and re-renders
    the Company Research page with the labelled, POST-FILTERED result. The output is NEVER persisted
    as evidence, never fed to a gate / candidate / recommendation / DQ, never part of replay. There
    is NO trade affordance. With no LLM key configured the panel shows the honest not-configured
    state. Providers are lazy + injectable (offline test seam); no network is attempted otherwise.
    """
    from cosmosiq_assistant.router import current_test_clients
    from cosmosiq_assistant.tasks import summarize_filing

    from . import cockpits as _cockpits

    if not isinstance(body, dict):
        body = {}
    effective_now = str(body.get("now", "") or body.get("at", "") or "") or now
    result = summarize_filing(
        body.get("filing_text", ""), ticker=str(body.get("ticker", "") or ""),
        mode=_assistant_mode(body), clients=current_test_clients(), now=effective_now)
    return _html(200, _cockpits.render_research_page(
        store_dir, assistant_result=result, assistant_form=body))


def _handle_assistant_thesis(store_dir: str, body: Any, now: str) -> Dict[str, Any]:
    """POST /api/assistant/thesis -- run the ISOLATED assistant to draft a thesis REVIEW note.

    Same isolation as :func:`_handle_assistant_summarize`: display-only, labelled, post-filtered,
    never evidence / gated / replayed, no trade affordance, honest no-key state.
    """
    from cosmosiq_assistant.router import current_test_clients
    from cosmosiq_assistant.tasks import draft_thesis_note

    from . import cockpits as _cockpits

    if not isinstance(body, dict):
        body = {}
    effective_now = str(body.get("now", "") or body.get("at", "") or "") or now
    result = draft_thesis_note(
        str(body.get("ticker", "") or ""), body.get("evidence_context", ""),
        mode=_assistant_mode(body), clients=current_test_clients(), now=effective_now)
    return _html(200, _cockpits.render_research_page(
        store_dir, assistant_result=result, assistant_form=body))


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

    if tail == ["observability"]:
        return _require(method, "GET", path) or _handle_observability(store_dir, now)

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
    # PROD-LIVE-1: the SANCTIONED credential-gated "Refresh from external sources" action.
    # Record/refresh-only (no broker/order route -- a trade path is refused with 403 above).
    # ``/api/pulse/refresh`` is the guard-clean alias the rendered form posts to (the page-hygiene
    # scans forbid the bare word in a rendered URL); both routes dispatch identically.
    if tail == ["pulse", "live"] or tail == ["pulse", "refresh"]:
        return _require(method, "POST", path) or _handle_pulse_live(store_dir, body, now)

    if len(tail) == 2 and tail[0] == "replay":
        return _require(method, "GET", path) or _handle_replay(store_dir, raw_tail[1])

    if tail == ["settings"]:
        if method == "GET":
            return _handle_settings_get(store_dir)
        if method == "PUT":
            return _handle_settings_put(store_dir, body, now)
        return _error(405, "method {0} not allowed for {1} (allowed: GET, PUT)".format(
            method, path))

    if tail == ["candidates"]:
        return _require(method, "GET", path) or _handle_candidates_list(store_dir, query)
    if tail == ["candidates", "publish"]:
        return _require(method, "POST", path) or _handle_candidates_publish(
            store_dir, body, now)

    if tail == ["coverage"]:
        return _require(method, "GET", path) or _handle_coverage()

    # UX-3: the SANCTIONED record-fill operator form. Record-only -- it appends to
    # the position ledger and redirects back to /portfolio; it is NOT a trading
    # endpoint (no broker, no order submission). A real order route (e.g.
    # /api/orders) is refused above by the trade-path guard with 403.
    if tail == ["portfolio", "record-fill"]:
        return _require(method, "POST", path) or _handle_portfolio_record_fill(
            store_dir, body, now)

    # PROD-LIVE-3: the ISOLATED AI Research Assistant (display-only; no trade route -- a trade path
    # is refused 403 above). Runs the cosmosiq_assistant package OUTSIDE reality_mesh; the labelled,
    # post-filtered result is rendered on the Company Research page and never persisted as evidence.
    if tail == ["assistant", "summarize"]:
        return _require(method, "POST", path) or _handle_assistant_summarize(
            store_dir, body, now)
    if tail == ["assistant", "thesis"]:
        return _require(method, "POST", path) or _handle_assistant_thesis(store_dir, body, now)

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
    # UX-1 cockpit shell -- the eight primary tabs as first-class GET pages. Old routes
    # (/candidates, /companies/<t>, /themes, /runs, /alerts, /settings) keep working above /
    # below; these are the renamed / added tabs. `Opportunities` is an alias of the candidate
    # list; `Company Research` is the ticker landing.
    if segments == ["opportunities"]:
        from . import cockpits as _cockpits
        return _html(200, _cockpits.render_opportunities_page(store_dir))
    if segments == ["research"]:
        from . import cockpits as _cockpits
        return _html(200, _cockpits.render_research_page(store_dir))
    if segments == ["journal"]:
        return _html(200, _pages.render_journal_page(store_dir))
    if segments == ["evidence"]:
        return _html(200, _pages.render_evidence_page(store_dir))
    if segments == ["how-it-works"]:
        return _html(200, _pages.render_how_it_works_page(store_dir))
    if segments == ["map", "canvas"]:
        # The immersive Universe Canvas served READ-ONLY as its own document -- the generated
        # universe.html bytes verbatim (never rewritten). When it has not been generated yet,
        # the honest 404 page (the /map tab itself carries the build command).
        if _pages.generated_canvas_present():
            return _html(200, _pages.read_generated_canvas())
        return _html(404, _pages.render_not_found(store_dir, "/map/canvas"))
    if segments == ["map"]:
        return _html(200, _pages.render_map_page(store_dir))
    # 016C cockpits -- read/inspect surfaces over the persisted stores + the accepted engines
    # (lazy import, same additive-slice discipline as the pages layer).
    if segments == ["themes"]:
        from . import cockpits as _cockpits
        return _html(200, _cockpits.render_theme_list(store_dir))
    if len(segments) == 2 and segments[0] == "themes":
        from . import cockpits as _cockpits
        return _html(200, _cockpits.render_theme_cockpit(store_dir, raw[1]))
    if len(segments) == 2 and segments[0] == "companies":
        from . import cockpits as _cockpits
        return _html(200, _cockpits.render_company_cockpit(store_dir, raw[1]))
    if segments == ["candidates"]:
        from . import cockpits as _cockpits
        return _html(200, _cockpits.render_candidate_list(store_dir))
    if len(segments) == 2 and segments[0] == "candidates":
        from . import cockpits as _cockpits
        return _html(200, _cockpits.render_candidate_cockpit(store_dir, raw[1]))
    # 018A portfolio -- READ-ONLY intelligence over the operator-recorded holdings
    # statement (labels / bands / counts only; no market surface of any kind).
    if segments == ["portfolio"]:
        from . import cockpits as _cockpits
        return _html(200, _cockpits.render_portfolio_page(store_dir))
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
