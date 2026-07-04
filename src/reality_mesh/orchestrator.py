"""PulseOrchestrator: the explicitly-started scheduled-pulse runner (IMPLEMENTATION-015B).

015A shipped the cadence CORE (:mod:`reality_mesh.scheduler`): frozen data plus the pure
``due_policies`` decision. This slice is the thing that ACTS on that answer -- and it is still
NOT a daemon. :func:`run_due_pulses` is ONE synchronous, operator-invoked tick:

1. asks :func:`~reality_mesh.scheduler.due_policies` what is due at the injected ``now``;
2. maps each due policy to a pulse scope via the :class:`Subscription`\\ s that reference it
   (no subscription -> a VISIBLE note, nothing runs for that policy -- never an error);
3. runs :func:`~reality_mesh.pulse.run_pulse` + the FULL 013 chain
   (:func:`~reality_mesh.pulse_persistence.persist_and_summarize`: append-only stores, agent-run
   ledger, health roll-ups, data-quality gates, deterministic verification replay);
4. supersedes the persisted run record with a ``trigger_type="scheduled"`` correction that
   carries ``scheduled_by_policy:<policy_id>`` in ``generated_outputs`` plus an audit
   attribution (append-only: the original line is byte-unchanged forever);
5. records success/failure back into the schedule via
   :func:`~reality_mesh.scheduler.record_run` (a failure backs the policy off
   deterministically -- and NEVER aborts the tick: other due policies still run);
6. appends the resulting schedule state to the append-style JSONL journal
   (:class:`ScheduleStateStore`, the 013B store pattern: new lines, never mutation);
7. returns. NO loop, NO timed waiting, NO thread, NO process: the NEXT tick happens only when
   an operator (or a future 015C/016 runner process the OPERATOR starts) calls again.

Per ADR-CANDIDATE-015 the reserved ``scheduled`` trigger type unlocks WITH this runner
(``streaming`` stays reserved/rejected). Everything ARCHITECTURE_CONTRACT_012 §G forbids beyond
cadence + evidence stays forbidden and approval-gated. IMPLEMENTATION-015C adds the alert hook:
after each persisted scheduled pulse the tick asks the diff-based engine in
:mod:`reality_mesh.alerts` to observe state changes vs the previous persisted run (alerts
OBSERVE -- they never act; first run -> baseline note; unchanged -> quiet). A failed pulse is
also alerted (one honest failure record). Alert generation failing NEVER fails the pulse -- it
surfaces as a visible note instead.

Deterministic, stdlib-only, Python 3.9, OFFLINE: every timestamp is an injected ISO-8601 string
(the wall clock is never read), run ids derive from policy id + injected instant, and all
persistence is local append-only JSONL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Dict, List, Mapping, Optional, Tuple

from .alerts import Alert, generate_alerts_for_run, record_failed_pulse_alert
from .ledger import AgentRunLedger
from .pulse import run_pulse
from .pulse_persistence import persist_and_summarize
from .runtime import AgentRunResult, PulseRun
from .scheduler import (
    DEFAULT_MARKET_HOURS,
    MarketHoursCalendar,
    PulseSchedule,
    _format_utc,
    _parse_utc,
    due_policies,
    record_run,
    schedule_from_dict,
    schedule_to_dict,
    state_for,
    throttled,
)
from .stores import AppendOnlyStore, AuditStore, DataQualityRecord, DataQualityStore, RunStore

__all__ = [
    "ORCHESTRATOR_ACTOR",
    "SCHEDULED_BY_POLICY_PREFIX",
    "Subscription",
    "TickResult",
    "PulseOrchestrator",
    "ScheduleStateStore",
    "run_due_pulses",
    "scheduled_policy_for",
    "subscription_to_dict",
    "subscription_from_dict",
    "append_schedule_state",
    "load_schedule_state",
]

# The actor name stamped on orchestrator-written audit / health records.
ORCHESTRATOR_ACTOR = "pulse_orchestrator"

# A scheduled PulseRun carries the policy that scheduled it as this generated_outputs entry
# (attribution lives in generated_outputs + audit rather than a new PulseRun field: the
# persisted 013 schema is unchanged, old records still round-trip, and nothing new needs
# validation -- the least invasive carrier).
SCHEDULED_BY_POLICY_PREFIX = "scheduled_by_policy:"


# --------------------------------------------------------------------------- #
# 1. Subscription -- WHAT a cadence policy pulses over (labels/paths, no        #
#    secrets)                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Subscription:
    """One watchlist/theme subscription: the pulse scope a cadence policy resolves to.

    ``policy_ids`` names WHICH cadence policies apply to this scope. ``data_dir`` and
    ``adapter_refs`` are config REFERENCES only (a local path / opaque labels an operator
    resolves to pre-built adapters at tick time) -- never a credential, never a secret.
    """

    subscription_id: str = ""
    watchlist: Tuple[str, ...] = field(default_factory=tuple)
    themes: Tuple[str, ...] = field(default_factory=tuple)
    policy_ids: Tuple[str, ...] = field(default_factory=tuple)
    data_dir: str = ""
    adapter_refs: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.subscription_id, str) or self.subscription_id.strip() == "":
            raise ValueError(
                "Subscription.subscription_id is a required id and must be non-empty")
        for name in ("watchlist", "themes", "policy_ids", "adapter_refs"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        for name in ("watchlist", "themes"):
            values = getattr(self, name)
            if not values:
                raise ValueError(
                    "Subscription.{0} must be non-empty (a pulse needs an explicit scope; "
                    "nothing is fabricated from an empty subscription)".format(name))
            if any(not str(v).strip() for v in values):
                raise ValueError(
                    "Subscription.{0} contains a blank token".format(name))
        if any(not str(p).strip() for p in self.policy_ids):
            raise ValueError("Subscription.policy_ids contains a blank token")


def subscription_to_dict(subscription: Subscription) -> Dict[str, object]:
    return {
        "subscription_id": subscription.subscription_id,
        "watchlist": list(subscription.watchlist),
        "themes": list(subscription.themes),
        "policy_ids": list(subscription.policy_ids),
        "data_dir": subscription.data_dir,
        "adapter_refs": list(subscription.adapter_refs),
    }


def subscription_from_dict(data: Mapping[str, object]) -> Subscription:
    return Subscription(
        subscription_id=str(data.get("subscription_id", "")),
        watchlist=tuple(data.get("watchlist", ()) or ()),
        themes=tuple(data.get("themes", ()) or ()),
        policy_ids=tuple(data.get("policy_ids", ()) or ()),
        data_dir=str(data.get("data_dir", "")),
        adapter_refs=tuple(data.get("adapter_refs", ()) or ()))


# --------------------------------------------------------------------------- #
# 2. Schedule-state journal -- the 013B append-only pattern for the schedule    #
# --------------------------------------------------------------------------- #
class ScheduleStateStore(AppendOnlyStore):
    """The schedule-state journal: one JSONL line per tick, append-style, never mutated.

    Composes the 013B :class:`~reality_mesh.stores.AppendOnlyStore` so it inherits the same
    hard guarantees (no update/delete, replay envelope, credential-key refusal, deterministic
    ``sort_keys`` JSONL). Each line is a full :func:`~reality_mesh.scheduler.schedule_to_dict`
    snapshot plus the tick note -- a NEW state is a NEW line; history is never rewritten.
    """

    filename = "schedule_state_store.jsonl"
    record_cls = None                       # plain payload dicts (schedule snapshots)
    id_field = None
    timestamp_field = None


def append_schedule_state(store_dir: str, schedule: PulseSchedule, *, now: str,
                          note: str = "") -> str:
    """Append ONE schedule-state snapshot line to the journal; return its record_id.

    Append-style state: a correction / new state is a NEW line (``schedule-state-NNNNNN``,
    numbered in append sequence); prior lines stay byte-unchanged forever.
    """
    journal = ScheduleStateStore(store_dir)
    stamped = _format_utc(_parse_utc(now, name="now"))
    record_id = "schedule-state-{0:06d}".format(len(journal.read_records()) + 1)
    payload = {
        "kind": "schedule_state",
        "recorded_at": stamped,
        "note": note,
        "schedule": schedule_to_dict(schedule),
    }
    return journal.append(payload, timestamp=stamped, record_id=record_id)


def load_schedule_state(store_dir: str) -> Optional[PulseSchedule]:
    """Reload the LATEST journaled schedule state (None if nothing was ever journaled).

    Reads only -- reloading then re-serializing yields the same state the last tick appended.
    """
    records = ScheduleStateStore(store_dir).read_all()
    if not records:
        return None
    return schedule_from_dict(dict(records[-1].get("schedule", {}) or {}))


# --------------------------------------------------------------------------- #
# 3. TickResult -- what ONE tick did (and why anything was skipped)             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TickResult:
    """The outcome of ONE synchronous tick. Unpacks as ``(schedule, pulse_runs)``.

    ``ran`` / ``failed`` / ``skipped`` / ``notes`` are honest human-readable lines naming
    every policy the tick touched and WHY anything did not run (paused / backoff / throttled /
    market closed / interval not elapsed / max_pulses / no subscription). ``alerts`` (015C)
    are the frozen observation records the tick's alert hook appended to the inbox --
    observations only, nothing acts on them.
    """

    schedule: PulseSchedule = field(default_factory=PulseSchedule)
    pulse_runs: Tuple[PulseRun, ...] = field(default_factory=tuple)
    ran: Tuple[str, ...] = field(default_factory=tuple)
    failed: Tuple[str, ...] = field(default_factory=tuple)
    skipped: Tuple[str, ...] = field(default_factory=tuple)
    notes: Tuple[str, ...] = field(default_factory=tuple)
    alerts: Tuple[Alert, ...] = field(default_factory=tuple)

    def __iter__(self):
        """Support ``new_schedule, runs = run_due_pulses(...)`` (the documented contract)."""
        return iter((self.schedule, self.pulse_runs))


def scheduled_policy_for(pulse_run: PulseRun) -> str:
    """The policy_id that scheduled ``pulse_run`` ("" for a manual / unattributed run)."""
    for entry in pulse_run.generated_outputs:
        if str(entry).startswith(SCHEDULED_BY_POLICY_PREFIX):
            return str(entry)[len(SCHEDULED_BY_POLICY_PREFIX):]
    return ""


# --------------------------------------------------------------------------- #
# Internal helpers (pure; injected time only)                                   #
# --------------------------------------------------------------------------- #
def _tick_run_id(policy_id: str, now: str) -> str:
    """Deterministic run id for a scheduled pulse: policy + injected instant, no wall clock."""
    compact = _parse_utc(now, name="now").strftime("%Y%m%dT%H%M%SZ")
    return "sched.{0}.{1}".format(policy_id, compact)


def _skip_reason(schedule: PulseSchedule, policy, now: str,
                 calendar: MarketHoursCalendar) -> str:
    """WHY a policy is not due at ``now`` (mirrors the due_policies decision sequence)."""
    if schedule.paused_all:
        return "schedule paused (paused_all=True) -- resume required before anything runs"
    if throttled(schedule, now):
        return ("throttled: global max_runs_per_hour ({0}) exhausted in the current "
                "window".format(schedule.max_runs_per_hour))
    state = state_for(schedule, policy.policy_id)
    if state.paused:
        return "policy paused -- resume required"
    if state.backoff_until and _parse_utc(now, name="now") < _parse_utc(state.backoff_until):
        return ("failure backoff active until {0} (consecutive_failures={1})".format(
            state.backoff_until, state.consecutive_failures))
    if policy.market_hours_only and not calendar.is_market_open(now):
        return "market closed (market_hours_only policy)"
    return "interval not elapsed (every {0}m; last run at {1})".format(
        policy.interval_minutes, state.last_run_at or "never")


def _merge_scope(subscriptions: Tuple[Subscription, ...]):
    """Union the matching subscriptions into ONE pulse scope (sequence-stable, deduped)."""
    watchlist: List[str] = []
    themes: List[str] = []
    adapter_refs: List[str] = []
    data_dir = ""
    for sub in subscriptions:
        for ticker in sub.watchlist:
            if ticker not in watchlist:
                watchlist.append(ticker)
        for theme in sub.themes:
            if theme not in themes:
                themes.append(theme)
        for ref in sub.adapter_refs:
            if ref not in adapter_refs:
                adapter_refs.append(ref)
        if not data_dir and sub.data_dir:
            data_dir = sub.data_dir
    return tuple(watchlist), tuple(themes), data_dir, tuple(adapter_refs)


def _attributed_scheduled_run(base_run: PulseRun, policy_id: str) -> PulseRun:
    """The scheduled supersession of a persisted run: trigger + policy attribution, nothing else.

    A scheduled run can never lose its attribution: the policy_id is required and lands in
    ``generated_outputs`` as ``scheduled_by_policy:<id>``.
    """
    if not str(policy_id).strip():
        raise ValueError("a scheduled PulseRun requires the policy_id that scheduled it")
    attribution = SCHEDULED_BY_POLICY_PREFIX + policy_id
    return replace(
        base_run,
        trigger_type="scheduled",
        generated_outputs=tuple(base_run.generated_outputs) + (attribution,))


def _safe_message(exc: BaseException) -> str:
    """A bounded, single-line failure note (no secret is ever constructed here)."""
    text = "{0}: {1}".format(type(exc).__name__, exc)
    return " ".join(text.split())[:300]


def _record_failure(store_dir: str, run_id: str, policy_id: str, message: str,
                    now: str) -> None:
    """Land a failed scheduled pulse in the run's health records -- visible, never hidden.

    One failed :class:`~reality_mesh.runtime.AgentRunResult` in the 013D ledger plus one
    ``failed`` :class:`~reality_mesh.stores.DataQualityRecord` -- the same surfaces a manual
    run's failures roll onto.
    """
    AgentRunLedger(store_dir).append_result(AgentRunResult(
        run_id=run_id, agent_id=ORCHESTRATOR_ACTOR, status="failed",
        started_at=now, completed_at=now,
        errors=("scheduled pulse for policy {0} failed: {1}".format(policy_id, message),),
        data_gaps=("nothing was persisted for run {0} -- the failure is recorded, never "
                   "papered over".format(run_id),),
        health_status="failed"))
    DataQualityStore(store_dir).append(DataQualityRecord(
        dq_id="dq.{0}.orchestration".format(run_id), run_id=run_id,
        category="source_failure", status="failed",
        summary="scheduled pulse for policy {0} failed: {1}".format(policy_id, message),
        at=now))


# --------------------------------------------------------------------------- #
# 4. run_due_pulses -- ONE synchronous tick (no loop, no waiting, no thread)    #
# --------------------------------------------------------------------------- #
def run_due_pulses(
    schedule: PulseSchedule,
    *,
    now: str,
    store_dir: str,
    subscriptions: Tuple[Subscription, ...] = (),
    adapters: Optional[Mapping[str, object]] = None,
    calendar: MarketHoursCalendar = DEFAULT_MARKET_HOURS,
    max_pulses: int = 1,
    fixture_dir: Optional[str] = None,
) -> TickResult:
    """Run ONE synchronous tick at the injected ``now``; return ``(new_schedule, pulse_runs)``.

    For each policy due per :func:`~reality_mesh.scheduler.due_policies` (up to ``max_pulses``
    attempts), the tick resolves the :class:`Subscription`\\ s referencing that policy into one
    merged pulse scope, runs the FULL 013 chain (``run_pulse`` -> ``persist_and_summarize``:
    stores / ledger / health / gates / verification replay), supersedes the run record with the
    ``scheduled`` trigger + ``scheduled_by_policy`` attribution (append-only correction), and
    records the outcome via :func:`~reality_mesh.scheduler.record_run` -- a failed pulse backs
    its policy off and lands in the health records WITHOUT aborting the tick (other due
    policies still run). The global throttle is honored ACROSS the tick: attempts recorded
    this tick count against ``max_runs_per_hour`` for the policies after them.

    A due policy with NO subscription is a visible note (nothing to run), not an error and not
    an attempt. The finishing schedule state is appended to the JSONL journal
    (:func:`append_schedule_state`) before returning. ``adapters`` optionally maps a
    subscription's ``adapter_refs`` to pre-built source-adapter instances; an unresolvable ref
    is an honest pulse failure. This function returns after ONE pass -- there is no loop, no
    timed waiting, and no background anything; the operator calls it again for the next tick.
    """
    if not str(store_dir).strip():
        raise ValueError("run_due_pulses requires a non-empty store_dir")
    if not isinstance(max_pulses, int) or isinstance(max_pulses, bool) or max_pulses < 1:
        raise ValueError("run_due_pulses max_pulses must be an integer >= 1")
    _parse_utc(now, name="now")             # the injected instant must be valid ISO-8601
    subscriptions = tuple(subscriptions)
    adapter_map = dict(adapters) if adapters else {}

    due = due_policies(schedule, now, calendar=calendar)
    current = schedule
    pulse_runs: List[PulseRun] = []
    ran: List[str] = []
    failed: List[str] = []
    skipped: List[str] = []
    notes: List[str] = []
    alerts: List[Alert] = []
    attempts = 0

    if schedule.paused_all:
        notes.append("schedule is paused (paused_all=True) -- nothing runs this tick")
    if not subscriptions:
        notes.append("no subscriptions configured -- a due policy has nothing to run over")

    for policy in schedule.policies:
        policy_id = policy.policy_id
        if policy_id not in due:
            skipped.append("{0}: {1}".format(
                policy_id, _skip_reason(schedule, policy, now, calendar)))
            continue
        if attempts >= max_pulses:
            skipped.append("{0}: due, but max_pulses={1} already used this tick -- the next "
                           "explicit tick picks it up".format(policy_id, max_pulses))
            continue
        if throttled(current, now):
            skipped.append("{0}: due, but throttled mid-tick -- global max_runs_per_hour "
                           "({1}) exhausted by this tick's earlier runs".format(
                               policy_id, current.max_runs_per_hour))
            continue
        matching = tuple(s for s in subscriptions if policy_id in s.policy_ids)
        if not matching:
            notes.append("{0}: due, but no subscription references this policy -- nothing to "
                         "run (visible note, not an error)".format(policy_id))
            continue

        watchlist, themes, data_dir, adapter_refs = _merge_scope(matching)
        run_id = _tick_run_id(policy_id, now)
        attempts += 1
        try:
            if data_dir and not os.path.isdir(data_dir):
                raise ValueError(
                    "subscription data_dir {0!r} does not exist -- a missing source dir is a "
                    "failed pulse, never a silent fixture fall-back".format(data_dir))
            missing_refs = tuple(r for r in adapter_refs if r not in adapter_map)
            if missing_refs:
                raise ValueError(
                    "adapter ref(s) {0} not resolvable -- pass pre-built adapters for every "
                    "subscription adapter_ref".format(sorted(missing_refs)))
            resolved = tuple(adapter_map[r] for r in adapter_refs)

            result = run_pulse(
                watchlist, themes, now=now,
                fixture_dir=fixture_dir,
                data_dir=data_dir or None,
                adapters=resolved or None)
            base_run, replay_result, _panel = persist_and_summarize(
                result, store_dir=store_dir, run_id=run_id, now=now)

            # Append-only supersession: the persisted 'manual' spine line stays byte-unchanged;
            # a NEW run record carries the scheduled trigger + policy attribution, and the
            # audit trail records the correction that links the two.
            scheduled_run = _attributed_scheduled_run(base_run, policy_id)
            RunStore(store_dir).append(scheduled_run, timestamp=now)
            AuditStore(store_dir).append_correction(
                audit_id="audit.trigger.{0}".format(run_id), corrects=run_id,
                run_id=run_id, actor=ORCHESTRATOR_ACTOR, subject_ref=run_id, at=now,
                reason="trigger_type superseded manual -> scheduled (015B, "
                       "ADR-CANDIDATE-015)",
                note=SCHEDULED_BY_POLICY_PREFIX + policy_id)

            current = record_run(current, policy_id, now, True)
            pulse_runs.append(scheduled_run)
            ran.append("{0}: ran pulse {1} over {2} (replay deterministic_match={3})".format(
                policy_id, run_id, ",".join(watchlist), replay_result.deterministic_match))

            # 015C alert hook: AFTER persist + record_run, observe this run against the
            # previous persisted run (diff-based; first run -> baseline note; unchanged ->
            # quiet). Alerts OBSERVE only -- and an alert-generation failure never fails
            # the pulse: it is surfaced as a visible note instead.
            try:
                observed = generate_alerts_for_run(store_dir, run_id, now=now)
                alerts.extend(observed.alerts)
                for note in observed.notes:
                    notes.append("{0}: {1}".format(policy_id, note))
            except Exception as alert_exc:
                notes.append("{0}: alert generation FAILED ({1}) -- the pulse itself "
                             "succeeded; the failure is surfaced here, not hidden".format(
                                 policy_id, _safe_message(alert_exc)))
        except Exception as exc:  # failure isolation: this policy backs off, the tick goes on
            message = _safe_message(exc)
            current = record_run(current, policy_id, now, False)
            _record_failure(store_dir, run_id, policy_id, message, now)
            state = state_for(current, policy_id)
            failed.append("{0}: pulse {1} FAILED ({2}) -- backoff until {3} "
                          "(consecutive_failures={4}); other due policies were not "
                          "affected".format(policy_id, run_id, message, state.backoff_until,
                                            state.consecutive_failures))
            # 015C: a failed scheduled pulse is itself an observable state change -- one
            # honest failure alert (idempotent per run id; never aborts the tick).
            try:
                failure_alert = record_failed_pulse_alert(
                    store_dir, run_id, policy_id=policy_id, message=message, now=now)
                if failure_alert is not None:
                    alerts.append(failure_alert)
            except Exception as alert_exc:
                notes.append("{0}: failure-alert generation FAILED ({1}) -- surfaced, "
                             "not hidden".format(policy_id, _safe_message(alert_exc)))

    tick_note = "tick at {0}: ran={1} failed={2} skipped={3} notes={4}".format(
        now, len(ran), len(failed), len(skipped), len(notes))
    append_schedule_state(store_dir, current, now=now, note=tick_note)

    return TickResult(
        schedule=current, pulse_runs=tuple(pulse_runs), ran=tuple(ran),
        failed=tuple(failed), skipped=tuple(skipped), notes=tuple(notes),
        alerts=tuple(alerts))


# --------------------------------------------------------------------------- #
# 5. PulseOrchestrator -- a thin, explicitly-constructed convenience wrapper    #
# --------------------------------------------------------------------------- #
class PulseOrchestrator:
    """Holds one tick configuration (store dir / subscriptions / calendar / adapters).

    Nothing starts on construction; :meth:`tick` is the same ONE synchronous pass as
    :func:`run_due_pulses` -- an operator calls it explicitly, every time.
    """

    def __init__(self, *, store_dir: str,
                 subscriptions: Tuple[Subscription, ...] = (),
                 adapters: Optional[Mapping[str, object]] = None,
                 calendar: MarketHoursCalendar = DEFAULT_MARKET_HOURS,
                 fixture_dir: Optional[str] = None) -> None:
        if not str(store_dir).strip():
            raise ValueError("PulseOrchestrator requires a non-empty store_dir")
        self.store_dir = str(store_dir)
        self.subscriptions = tuple(subscriptions)
        self.adapters = dict(adapters) if adapters else {}
        self.calendar = calendar
        self.fixture_dir = fixture_dir

    def tick(self, schedule: PulseSchedule, *, now: str, max_pulses: int = 1) -> TickResult:
        """Run ONE synchronous tick (see :func:`run_due_pulses`); returns, never loops."""
        return run_due_pulses(
            schedule, now=now, store_dir=self.store_dir,
            subscriptions=self.subscriptions, adapters=self.adapters,
            calendar=self.calendar, max_pulses=max_pulses, fixture_dir=self.fixture_dir)
