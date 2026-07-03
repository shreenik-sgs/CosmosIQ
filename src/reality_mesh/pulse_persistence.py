"""Persist ONE manual pulse and summarize it for the observability surface (IMPLEMENTATION-013F).

The small glue layer that connects a :func:`~reality_mesh.pulse.run_pulse` output to the Phase-013
substrate: :func:`persist_and_summarize` persists the pulse via the 013C
:meth:`~reality_mesh.replay.ReplayHarness.persist_pulse` into the 013B append-only stores under a
caller-supplied ``store_dir``, records one 013A :class:`~reality_mesh.runtime.AgentRunResult` per
sensor agent in the 013D :class:`~reality_mesh.ledger.AgentRunLedger`, rolls agent / run / data-
quality health via the 013D :class:`~reality_mesh.health.AgentHealthMonitor`, runs the 013E
:class:`~reality_mesh.gates.DataQualityGateRunner` over the PERSISTED records, executes a
verification replay (read-only) proving ``deterministic_match``, and returns the rendered
observability panel (:func:`~reality_mesh.render_adapters.build_run_observability_panel`) for the
Trust & Data-Quality page.

EVIDENCE + OBSERVABILITY, never a trade action. There is NO scheduler, NO daemon, NO streaming,
NO broker, NO buy/sell affordance, and NO hidden metric anywhere here: everything persisted or
rendered is labels + volume counts. Degraded / failed / skipped agent states are recorded and
rendered honestly (a visible gap), never hidden and never fabricated. The panel introduces no
``data-intel`` ref and no ``href`` anchor, so the closed UI link graph stays trivially intact.

Deterministic, stdlib-only, Python 3.9, OFFLINE: ``run_id`` is caller-supplied, ``now`` is an
injected string (no wall-clock), stores are local JSONL files, and the verification replay reads
(never mutates) what was just persisted.
"""

from __future__ import annotations

from typing import Tuple

from .gates import DataQualityGateRunner
from .health import AgentHealthMonitor, SourceHealthRecord
from .ledger import AgentRunLedger
from .pulse import PulseResult
from .render_adapters import _is_weak_social, build_run_observability_panel
from .replay import ReplayHarness
from .runtime import AgentRunResult, PulseRun, ReplayRequest, ReplayResult
from .stores import (
    DataQualityRecord,
    DataQualityStore,
    EventStore,
    FindingStore,
    RunStore,
    SignalStore,
    ThemePulseStore,
)

__all__ = [
    "PULSE_FIXTURE_SOURCE_ID",
    "agent_results_from_pulse",
    "persist_and_summarize",
]

# The (single, offline) source a fixture-backed pulse reads: local JSON fixtures. No credential
# applies to a local file (the credentials label stays the "" explicit-gap sentinel -- presence
# is never fabricated) and a local read cannot be rate-limited.
PULSE_FIXTURE_SOURCE_ID = "offline_pulse_fixtures"

# PulseAgentRun.status -> the closed AGENT_RUN_STATUSES member it maps to. ``no_findings`` /
# ``no_matching_events`` are honest coverage absence, not malfunctions.
_AGENT_STATUS_MAP = {
    "ok": "success",
    "no_findings": "success",
    "no_matching_events": "skipped",
}


def agent_results_from_pulse(pulse_result: PulseResult, *, run_id: str,
                             now: str = "") -> Tuple[AgentRunResult, ...]:
    """One frozen :class:`~reality_mesh.runtime.AgentRunResult` per sensor agent of the pulse.

    Maps each :class:`~reality_mesh.pulse.PulseAgentRun` status onto the closed
    ``AGENT_RUN_STATUSES`` vocabulary: ``ok`` / ``no_findings`` -> ``success`` (a clean run that
    read nothing actionable is still a clean run -- noted, not failed); ``no_matching_events`` ->
    ``skipped`` + an explicit data gap (honest coverage absence, never a fabricated finding).
    Deterministic: timestamps are the injected ``now``.
    """
    if not str(run_id).strip():
        raise ValueError("agent_results_from_pulse requires a non-empty run_id")
    results = []
    for run in pulse_result.agent_runs:
        status = _AGENT_STATUS_MAP.get(run.status, "partial")
        warnings = ()
        gaps = ()
        if run.status == "no_findings":
            warnings = ("agent saw {0} event(s) in its discipline but produced no findings -- "
                        "honest absence, nothing fabricated".format(run.events_seen),)
        elif run.status == "no_matching_events":
            gaps = ("agent {0} had no fixture events in its discipline in run {1} -- honest "
                    "coverage gap, no fabricated value".format(run.agent_id, run_id),)
        elif run.status not in _AGENT_STATUS_MAP:
            warnings = ("unrecognised pulse agent status {0!r} recorded as 'partial' -- "
                        "surfaced, not hidden".format(run.status),)
        results.append(AgentRunResult(
            run_id=run_id, agent_id=run.agent_id, status=status,
            started_at=now, completed_at=now,
            finding_ids=tuple(run.finding_ids),
            warnings=warnings, data_gaps=gaps,
            health_status="healthy" if status in ("success", "skipped") else "degraded"))
    return tuple(results)


def _fixture_source_health(pulse_result: PulseResult, *, now: str = "") -> SourceHealthRecord:
    """The health record of the pulse's one offline fixture source (a delivered-nothing dir is
    a VISIBLE ``source_unavailable`` gap, never silently healthy)."""
    if pulse_result.events_loaded > 0:
        return SourceHealthRecord(
            source_id=PULSE_FIXTURE_SOURCE_ID, last_status="healthy",
            rate_limit_status="ok", last_success_at=now)
    return SourceHealthRecord(
        source_id=PULSE_FIXTURE_SOURCE_ID, last_status="source_unavailable",
        rate_limit_status="ok", last_failure_at=now,
        unavailable_reason="fixture directory delivered no events -- visible gap, nothing "
                           "fabricated")


def _weak_social_ids(pulse_result: PulseResult) -> Tuple[str, ...]:
    """The signal ids that are weak / social (rumor tier) -- mirrors the 012J panel's test."""
    auth = dict(pulse_result.authority_by_signal or {})
    return tuple(sorted(
        getattr(s, "signal_id", "") for s in pulse_result.signals
        if _is_weak_social(s, auth.get(getattr(s, "signal_id", ""), ""))))


def _persist_gate_records(dq_store: DataQualityStore, run_id: str, gate_results,
                          overall_status: str, *, now: str = "") -> None:
    """Append the run's gate verdicts + overall status to the append-only DataQualityStore.

    ``warn`` rolls to the closed ``degraded`` diagnostic status (surfaced, not hidden); findings
    text is secret-free by construction upstream (token names + refs only).
    """
    for result in gate_results:
        status = {"pass": "pass", "fail": "fail"}.get(result.status, "degraded")
        dq_store.append(DataQualityRecord(
            dq_id="dq.{0}.{1}".format(run_id, result.category),
            run_id=run_id, category=result.category, status=status,
            summary="; ".join(result.findings) or "no findings",
            records=tuple(result.subject_refs), at=now))
    dq_store.append(DataQualityRecord(
        dq_id="dq.{0}.overall".format(run_id), run_id=run_id, category="gate_overall",
        status=overall_status, summary="worst gate verdict rolled onto the run-status ladder",
        at=now))


def persist_and_summarize(pulse_result: PulseResult, *, store_dir: str, run_id: str,
                          now: str = "") -> Tuple[PulseRun, ReplayResult, str]:
    """Persist ONE pulse into ``store_dir``, verify it replays, and render its observability.

    Returns ``(pulse_run, replay_result, panels_html)``:

    1. persists the run + events + findings + signals + theme pulses via
       :meth:`~reality_mesh.replay.ReplayHarness.persist_pulse` (append-only stores);
    2. records one :class:`~reality_mesh.runtime.AgentRunResult` per sensor agent in the
       :class:`~reality_mesh.ledger.AgentRunLedger` and rolls agent / run / data-quality health;
    3. runs the :class:`~reality_mesh.gates.DataQualityGateRunner` over the PERSISTED records
       and appends the gate verdicts to the DataQualityStore;
    4. executes a read-only verification replay (``deterministic_match`` proven, never assumed);
    5. renders :func:`~reality_mesh.render_adapters.build_run_observability_panel` from all of it.

    Deterministic + offline: caller-supplied ``run_id``, injected ``now`` (defaults to the
    pulse's own), local JSONL stores only. Re-invoking with the SAME ``run_id`` into the SAME
    ``store_dir`` appends new history (append-only) -- use a fresh run_id per persisted run.
    """
    if not str(run_id).strip():
        raise ValueError("persist_and_summarize requires a non-empty run_id")
    run_now = now or pulse_result.now

    event_store = EventStore(store_dir)
    finding_store = FindingStore(store_dir)
    signal_store = SignalStore(store_dir)
    theme_pulse_store = ThemePulseStore(store_dir)
    run_store = RunStore(store_dir)
    harness = ReplayHarness(event_store, finding_store, signal_store,
                            theme_pulse_store, run_store)

    # 1. persist the run (the only writer; replay below only reads).
    pulse_run = harness.persist_pulse(
        pulse_result, run_id=run_id, now=run_now, mode="pulse", runtime_version="013F")

    # 2. agent run ledger + health roll-ups (a degraded run still summarizes -- honestly).
    ledger = AgentRunLedger(store_dir)
    results = agent_results_from_pulse(pulse_result, run_id=run_id, now=run_now)
    for result in results:
        ledger.append_result(result)
    source = _fixture_source_health(pulse_result, now=run_now)
    monitor = AgentHealthMonitor()
    agent_health = monitor.roll_agent_health(results)
    run_health = monitor.build_run_health_summary(
        run_id, results, sources=(source,), gaps=pulse_result.data_gaps)
    dq_summary = monitor.build_data_quality_summary(
        run_id, results, sources=(source,), gaps=pulse_result.data_gaps,
        weak_social=_weak_social_ids(pulse_result))

    # 3. verification replay: read the stores back + recompute + compare (never rubber-stamp).
    replay_result = harness.replay(ReplayRequest(run_id=run_id), now=run_now)

    # 4. production gates over the PERSISTED records (not the in-memory originals).
    runner = DataQualityGateRunner()
    gate_results, overall_status = runner.run(
        signals=signal_store.query(run_id=run_id),
        findings=finding_store.query(run_id=run_id),
        events=event_store.query(run_id=run_id),
        records=theme_pulse_store.query(run_id=run_id),
        authority_by_signal=dict(pulse_result.authority_by_signal or {}),
        run_mode="pulse",
        replay_results=(replay_result,))
    _persist_gate_records(DataQualityStore(store_dir), run_id, gate_results,
                          overall_status, now=run_now)

    # 5. the rendered observability panel (labels + counts; degraded/failed VISIBLE).
    panels_html = build_run_observability_panel(
        pulse_run=pulse_run, run_health=run_health, dq_summary=dq_summary,
        agent_health=agent_health, source_health=(source,),
        gate_results=gate_results, replay_result=replay_result)
    return pulse_run, replay_result, panels_html
