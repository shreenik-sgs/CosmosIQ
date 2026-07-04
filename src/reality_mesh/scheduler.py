"""Pulse cadence core for the scheduled pulse (IMPLEMENTATION-015A).

Phase 015 is the FIRST phase in which a scheduler is permitted (SPEC-013 §D; the master
production authorization unlocks it now that the 013 runtime / persistence / replay /
observability / data-quality gates exist). This slice is the CORE only: cadence policies,
a market-hours calendar, per-policy schedule state, throttle + deterministic backoff, and
pause/resume -- **frozen data plus pure decision functions, NOT a daemon**.

The discipline (recorded in ``ADR-CANDIDATE-015_SCHEDULED_PULSE_UNLOCK.md``):

* **Data + a pure ``tick`` decision.** :func:`due_policies` computes *what is due* for an
  injected ``now``; it never runs anything. Something else -- the 015B explicitly-started
  runner, or a human operator -- acts on the answer. Nothing here starts on import; there is
  no loop, no background thread, no event loop, no timed waiting, no process, and no such
  module is imported (the repo-wide AST guards stay green).
* **Deterministic.** Every timestamp is an injected ISO-8601 string; the wall clock is never
  read (no ``.now()``-style call anywhere). There is no randomness: failure backoff is a pure
  exponential function of the consecutive-failure count, with no jitter.
* **Append-style state.** Every object is a frozen dataclass; every transition
  (:func:`record_run`, :func:`pause`, :func:`resume`) returns a NEW :class:`PulseSchedule`
  and never mutates an input.
* **Still forbidden.** Everything ARCHITECTURE_CONTRACT_012 §G forbids beyond cadence
  decisions stays forbidden and approval-gated (Phase 020+); see
  ``ADR-CANDIDATE-015_SCHEDULED_PULSE_UNLOCK.md``. Alerting is 015B/C, not this slice.
  Actually RUNNING a scheduled pulse (and unlocking the reserved ``scheduled`` trigger
  type in :mod:`reality_mesh.runtime`) is 015B -- this core only DECIDES.

Deterministic, stdlib-only, Python 3.9. No network on import; every timestamp is an injected
string (no wall-clock in any decision path).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

__all__ = [
    "ALL_POLICIES",
    "MAX_BACKOFF_MINUTES",
    "MINUTES_PER_DAY",
    "MINUTES_PER_WEEK",
    "THROTTLE_WINDOW_MINUTES",
    "CadencePolicy",
    "MarketHoursCalendar",
    "ScheduleState",
    "PulseSchedule",
    "DEFAULT_CADENCE_POLICIES",
    "DEFAULT_MARKET_HOURS",
    "build_default_schedule",
    "state_for",
    "due_policies",
    "record_run",
    "pause",
    "resume",
    "throttled",
    "calendar_to_dict",
    "calendar_from_dict",
    "policy_to_dict",
    "policy_from_dict",
    "state_to_dict",
    "state_from_dict",
    "schedule_to_dict",
    "schedule_from_dict",
]

# Sentinel policy_id accepted by pause / resume to address EVERY policy at once.
ALL_POLICIES = "all"

MINUTES_PER_DAY = 24 * 60
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY

# Failure backoff is capped at 24 hours regardless of the failure count.
MAX_BACKOFF_MINUTES = MINUTES_PER_DAY

# The global rate-limit window (max_runs_per_hour is counted over this window).
THROTTLE_WINDOW_MINUTES = 60


# --------------------------------------------------------------------------- #
# Injected-time helpers (pure string/date math; the wall clock is NEVER read)   #
# --------------------------------------------------------------------------- #
def _parse_utc(value: str, *, name: str = "timestamp") -> datetime:
    """Parse an injected ISO-8601 string to an aware UTC datetime. Never reads a clock."""
    text = (value or "").strip()
    if not text:
        raise ValueError("{0} must be a non-empty ISO-8601 string".format(name))
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("{0} is not ISO-8601: {1!r}".format(name, value))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _format_utc(moment: datetime) -> str:
    """Render an aware UTC datetime back to the repo-standard ``...Z`` ISO form."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _minutes_between(earlier_iso: str, later: datetime) -> float:
    """Minutes elapsed from an injected ISO string to an already-parsed UTC moment."""
    return (later - _parse_utc(earlier_iso)).total_seconds() / 60.0


def _parse_hhmm(value: str, *, name: str) -> int:
    """Parse ``HH:MM`` to minutes-of-day (calendar open/close boundaries)."""
    parts = (value or "").split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError("{0} must be 'HH:MM', got {1!r}".format(name, value))
    hours, minutes = int(parts[0]), int(parts[1])
    if hours > 23 or minutes > 59:
        raise ValueError("{0} out of range: {1!r}".format(name, value))
    return hours * 60 + minutes


# --------------------------------------------------------------------------- #
# 1. CadencePolicy -- HOW OFTEN one discipline / adapter may pulse              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CadencePolicy:
    """One cadence rule. Intervals are MINUTES (volumes of time, never a metric).

    ``interval_minutes`` is the target cadence; ``min_interval_minutes`` is the rate-limit
    floor a future runner may tighten toward but never cross. Closed validation:
    ``interval_minutes >= min_interval_minutes >= 1`` -- sub-minute cadence is rejected.
    """
    policy_id: str = ""
    discipline_or_adapter: str = ""
    interval_minutes: int = 0
    market_hours_only: bool = False
    active_only_for: Tuple[str, ...] = field(default_factory=tuple)
    min_interval_minutes: int = 1
    notes: str = ""

    def __post_init__(self) -> None:
        for name in ("policy_id", "discipline_or_adapter"):
            value = getattr(self, name)
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "CadencePolicy.{0} is a required id and must be non-empty".format(name))
        for name in ("interval_minutes", "min_interval_minutes"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(
                    "CadencePolicy.{0} must be an integer number of minutes".format(name))
        if self.min_interval_minutes < 1:
            raise ValueError(
                "CadencePolicy.min_interval_minutes must be >= 1 (sub-minute cadence is "
                "rejected): {0!r}".format(self.min_interval_minutes))
        if self.interval_minutes < self.min_interval_minutes:
            raise ValueError(
                "CadencePolicy.interval_minutes ({0}) must be >= min_interval_minutes "
                "({1})".format(self.interval_minutes, self.min_interval_minutes))
        object.__setattr__(self, "active_only_for", tuple(self.active_only_for))


# The accepted SPEC-013 §D cadence examples, AS DATA (a future 015B runner reads these;
# nothing in this module acts on them).
DEFAULT_CADENCE_POLICIES: Tuple[CadencePolicy, ...] = (
    CadencePolicy(
        policy_id="cadence.social_narrative", discipline_or_adapter="social_narrative",
        interval_minutes=5, market_hours_only=False,
        active_only_for=("active_themes", "watchlist"), min_interval_minutes=1,
        notes="weak-signal social sweep; 1-5 minute band, only while themes are active"),
    CadencePolicy(
        policy_id="cadence.news_filings", discipline_or_adapter="news_filings",
        interval_minutes=5, market_hours_only=False,
        active_only_for=("active_themes", "watchlist"), min_interval_minutes=1,
        notes="news / press-release sweep; 1-5 minute band, only while themes are active"),
    CadencePolicy(
        policy_id="cadence.market_regime", discipline_or_adapter="market_regime",
        interval_minutes=15, market_hours_only=True, min_interval_minutes=5,
        notes="market regime; 5-15 minute band, market hours only"),
    CadencePolicy(
        policy_id="cadence.sector_rotation", discipline_or_adapter="sector_rotation",
        interval_minutes=15, market_hours_only=True, min_interval_minutes=5,
        notes="sector rotation; 5-15 minute band, market hours only"),
    CadencePolicy(
        policy_id="cadence.theme_rotation", discipline_or_adapter="theme_rotation",
        interval_minutes=15, market_hours_only=True, min_interval_minutes=5,
        notes="theme rotation; 5-15 minute band, market hours only"),
    CadencePolicy(
        policy_id="cadence.technical_regime", discipline_or_adapter="technical_regime",
        interval_minutes=15, market_hours_only=True, min_interval_minutes=1,
        notes="technical inflection; 1-15 minute band, market hours only"),
    CadencePolicy(
        policy_id="cadence.sec_filings", discipline_or_adapter="sec_fmp_evidence",
        interval_minutes=60, market_hours_only=False, min_interval_minutes=60,
        notes="SEC filings; event-driven with an hourly sweep floor"),
    CadencePolicy(
        policy_id="cadence.company_documents", discipline_or_adapter="company_documents",
        interval_minutes=MINUTES_PER_DAY, market_hours_only=False, min_interval_minutes=60,
        notes="IR decks / investor presentations / transcripts; daily sweep"),
    CadencePolicy(
        policy_id="cadence.macro_regime", discipline_or_adapter="macro_regime",
        interval_minutes=60, market_hours_only=False, min_interval_minutes=60,
        notes="macro readings; hourly-to-daily band"),
    CadencePolicy(
        policy_id="cadence.learning_daily", discipline_or_adapter="learning",
        interval_minutes=MINUTES_PER_DAY, market_hours_only=False,
        min_interval_minutes=MINUTES_PER_DAY,
        notes="learning loop; daily roll-up"),
    CadencePolicy(
        policy_id="cadence.learning_weekly", discipline_or_adapter="learning",
        interval_minutes=MINUTES_PER_WEEK, market_hours_only=False,
        min_interval_minutes=MINUTES_PER_DAY,
        notes="learning deep review; weekly roll-up"),
)


# --------------------------------------------------------------------------- #
# 2. MarketHoursCalendar -- WHEN market-hours-only policies are allowed         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MarketHoursCalendar:
    """Regular NYSE-style session expressed in UTC. Pure data + a pure query.

    Defaults: weekdays 14:30-21:00 UTC (09:30-16:00 US/Eastern during daylight time).
    Weekends are always closed; ``holidays`` is an injectable tuple of ``YYYY-MM-DD``
    UTC dates (empty by default). All queries are pure string/date math over an injected
    ``now`` -- the wall clock is never read.
    """
    open_utc: str = "14:30"
    close_utc: str = "21:00"
    holidays: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        open_minute = _parse_hhmm(self.open_utc, name="MarketHoursCalendar.open_utc")
        close_minute = _parse_hhmm(self.close_utc, name="MarketHoursCalendar.close_utc")
        if open_minute >= close_minute:
            raise ValueError(
                "MarketHoursCalendar.open_utc must be earlier than close_utc "
                "({0!r} vs {1!r})".format(self.open_utc, self.close_utc))
        for day in self.holidays:
            parts = (day or "").split("-")
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                raise ValueError(
                    "MarketHoursCalendar.holidays entries must be 'YYYY-MM-DD', got "
                    "{0!r}".format(day))
        object.__setattr__(self, "holidays", tuple(self.holidays))

    def is_market_open(self, now_iso: str) -> bool:
        """True iff the injected ``now`` falls in a weekday session outside holidays.

        Open boundary inclusive, close boundary exclusive.
        """
        moment = _parse_utc(now_iso, name="now_iso")
        if moment.weekday() >= 5:                     # Saturday / Sunday
            return False
        if moment.strftime("%Y-%m-%d") in self.holidays:
            return False
        minute_of_day = moment.hour * 60 + moment.minute
        return (_parse_hhmm(self.open_utc, name="open_utc") <= minute_of_day
                < _parse_hhmm(self.close_utc, name="close_utc"))


DEFAULT_MARKET_HOURS = MarketHoursCalendar()


# --------------------------------------------------------------------------- #
# 3. ScheduleState -- the per-policy runtime facts (frozen; replaced, never     #
#    mutated)                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ScheduleState:
    """Per-policy schedule facts. Counters are VOLUME counts, never a metric."""
    policy_id: str = ""
    last_run_at: str = ""                   # injected timestamp of the last recorded run
    consecutive_failures: int = 0           # volume count
    paused: bool = False
    backoff_until: str = ""                 # "" = no backoff; else an injected ISO instant
    runs_in_window: int = 0                 # volume count inside the throttle window
    window_started_at: str = ""             # "" = no window open yet

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or self.policy_id.strip() == "":
            raise ValueError("ScheduleState.policy_id is a required id and must be non-empty")
        for name in ("consecutive_failures", "runs_in_window"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    "ScheduleState.{0} must be a non-negative integer count".format(name))


# --------------------------------------------------------------------------- #
# 4. PulseSchedule -- policies + states + the global controls                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PulseSchedule:
    """The whole schedule: cadence policies, their states, and global controls."""
    policies: Tuple[CadencePolicy, ...] = field(default_factory=tuple)
    states: Tuple[ScheduleState, ...] = field(default_factory=tuple)
    paused_all: bool = False
    max_runs_per_hour: int = 60             # global rate limit (a volume ceiling)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policies", tuple(self.policies))
        object.__setattr__(self, "states", tuple(self.states))
        if (not isinstance(self.max_runs_per_hour, int)
                or isinstance(self.max_runs_per_hour, bool)
                or self.max_runs_per_hour < 1):
            raise ValueError("PulseSchedule.max_runs_per_hour must be an integer >= 1")
        policy_ids = [p.policy_id for p in self.policies]
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("PulseSchedule.policies contains a duplicate policy_id")
        known = set(policy_ids)
        state_ids = [s.policy_id for s in self.states]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("PulseSchedule.states contains a duplicate policy_id")
        for state_id in state_ids:
            if state_id not in known:
                raise ValueError(
                    "PulseSchedule.states references unknown policy_id {0!r}".format(state_id))


def build_default_schedule(*, max_runs_per_hour: int = 60) -> PulseSchedule:
    """A fresh schedule over the accepted default cadence policies (nothing has run)."""
    return PulseSchedule(
        policies=DEFAULT_CADENCE_POLICIES,
        states=tuple(ScheduleState(policy_id=p.policy_id) for p in DEFAULT_CADENCE_POLICIES),
        paused_all=False,
        max_runs_per_hour=max_runs_per_hour)


def _policy_for(schedule: PulseSchedule, policy_id: str) -> CadencePolicy:
    for policy in schedule.policies:
        if policy.policy_id == policy_id:
            return policy
    raise ValueError("unknown policy_id {0!r} (known: {1})".format(
        policy_id, sorted(p.policy_id for p in schedule.policies)))


def state_for(schedule: PulseSchedule, policy_id: str) -> ScheduleState:
    """The state for a policy (a pristine state if none has been recorded yet)."""
    _policy_for(schedule, policy_id)        # closed: the policy must exist
    for state in schedule.states:
        if state.policy_id == policy_id:
            return state
    return ScheduleState(policy_id=policy_id)


def _with_state(schedule: PulseSchedule, new_state: ScheduleState) -> PulseSchedule:
    """A NEW schedule carrying ``new_state`` (replace-or-append; inputs untouched)."""
    replaced = False
    states: List[ScheduleState] = []
    for state in schedule.states:
        if state.policy_id == new_state.policy_id:
            states.append(new_state)
            replaced = True
        else:
            states.append(state)
    if not replaced:
        states.append(new_state)
    return replace(schedule, states=tuple(states))


# --------------------------------------------------------------------------- #
# 5. The pure decision functions (the "tick" -- they DECIDE, they never run)    #
# --------------------------------------------------------------------------- #
def throttled(schedule: PulseSchedule, now_iso: str) -> bool:
    """True iff the GLOBAL hourly rate limit is exhausted at the injected ``now``.

    Counts every run recorded inside a still-open per-policy throttle window
    (windows older than :data:`THROTTLE_WINDOW_MINUTES` have expired and count zero).
    """
    now = _parse_utc(now_iso, name="now_iso")
    total = 0
    for state in schedule.states:
        if state.window_started_at and (
                _minutes_between(state.window_started_at, now) < THROTTLE_WINDOW_MINUTES):
            total += state.runs_in_window
    return total >= schedule.max_runs_per_hour


def due_policies(
    schedule: PulseSchedule,
    now_iso: str,
    *,
    calendar: MarketHoursCalendar = DEFAULT_MARKET_HOURS,
) -> Tuple[str, ...]:
    """The policy_ids due at the injected ``now`` -- a pure decision, nothing is run.

    A policy is due iff ALL of: the schedule is not globally paused; the global rate limit
    is not exhausted; the policy is not individually paused; any failure backoff has
    elapsed; market hours are satisfied (when ``market_hours_only``); and the policy's
    interval has elapsed since ``last_run_at`` (a never-run policy is immediately due,
    market hours permitting). Deterministic: same inputs, same answer, in policy sequence.
    """
    now = _parse_utc(now_iso, name="now_iso")
    if schedule.paused_all or throttled(schedule, now_iso):
        return ()
    due: List[str] = []
    for policy in schedule.policies:
        state = state_for(schedule, policy.policy_id)
        if state.paused:
            continue
        if state.backoff_until and now < _parse_utc(state.backoff_until):
            continue
        if policy.market_hours_only and not calendar.is_market_open(now_iso):
            continue
        if state.last_run_at and (
                _minutes_between(state.last_run_at, now) < policy.interval_minutes):
            continue
        due.append(policy.policy_id)
    return tuple(due)


def record_run(
    schedule: PulseSchedule,
    policy_id: str,
    now_iso: str,
    succeeded: bool,
) -> PulseSchedule:
    """Record one run outcome for ``policy_id`` at the injected ``now`` -- a NEW schedule.

    Success resets ``consecutive_failures`` and clears any backoff. Failure increments the
    count and sets a DETERMINISTIC exponential backoff (no jitter, no randomness):
    ``backoff_until = now + min(2**failures * interval_minutes, 24h)``. Either way the
    throttle window advances (reused while open, restarted once expired).
    """
    policy = _policy_for(schedule, policy_id)
    now = _parse_utc(now_iso, name="now_iso")
    state = state_for(schedule, policy_id)

    if state.window_started_at and (
            _minutes_between(state.window_started_at, now) < THROTTLE_WINDOW_MINUTES):
        window_started_at = state.window_started_at
        runs_in_window = state.runs_in_window + 1
    else:
        window_started_at = _format_utc(now)
        runs_in_window = 1

    if succeeded:
        new_state = replace(
            state, last_run_at=_format_utc(now), consecutive_failures=0, backoff_until="",
            runs_in_window=runs_in_window, window_started_at=window_started_at)
    else:
        failures = state.consecutive_failures + 1
        backoff_minutes = min((2 ** failures) * policy.interval_minutes, MAX_BACKOFF_MINUTES)
        new_state = replace(
            state, last_run_at=_format_utc(now), consecutive_failures=failures,
            backoff_until=_format_utc(now + timedelta(minutes=backoff_minutes)),
            runs_in_window=runs_in_window, window_started_at=window_started_at)
    return _with_state(schedule, new_state)


def pause(schedule: PulseSchedule, policy_id: str, now_iso: str) -> PulseSchedule:
    """Pause one policy (or every policy via :data:`ALL_POLICIES`) -- a NEW schedule."""
    _parse_utc(now_iso, name="now_iso")     # the instant must be a valid injected timestamp
    if policy_id == ALL_POLICIES:
        return replace(schedule, paused_all=True)
    return _with_state(schedule, replace(state_for(schedule, policy_id), paused=True))


def resume(schedule: PulseSchedule, policy_id: str, now_iso: str) -> PulseSchedule:
    """Resume one policy (or all via :data:`ALL_POLICIES`) -- a NEW schedule.

    Resume only lifts the pause; an unexpired failure backoff STILL applies (an operator
    resuming a failing policy does not erase its failure history).
    """
    _parse_utc(now_iso, name="now_iso")
    if policy_id == ALL_POLICIES:
        return replace(schedule, paused_all=False)
    return _with_state(schedule, replace(state_for(schedule, policy_id), paused=False))


# --------------------------------------------------------------------------- #
# 6. Serialization -- plain, deterministic dicts (JSONL-friendly for 015B)      #
# --------------------------------------------------------------------------- #
def policy_to_dict(policy: CadencePolicy) -> Dict[str, object]:
    return {
        "policy_id": policy.policy_id,
        "discipline_or_adapter": policy.discipline_or_adapter,
        "interval_minutes": policy.interval_minutes,
        "market_hours_only": policy.market_hours_only,
        "active_only_for": list(policy.active_only_for),
        "min_interval_minutes": policy.min_interval_minutes,
        "notes": policy.notes,
    }


def policy_from_dict(data: Dict[str, object]) -> CadencePolicy:
    return CadencePolicy(
        policy_id=str(data.get("policy_id", "")),
        discipline_or_adapter=str(data.get("discipline_or_adapter", "")),
        interval_minutes=int(data.get("interval_minutes", 0)),
        market_hours_only=bool(data.get("market_hours_only", False)),
        active_only_for=tuple(data.get("active_only_for", ()) or ()),
        min_interval_minutes=int(data.get("min_interval_minutes", 1)),
        notes=str(data.get("notes", "")))


def state_to_dict(state: ScheduleState) -> Dict[str, object]:
    return {
        "policy_id": state.policy_id,
        "last_run_at": state.last_run_at,
        "consecutive_failures": state.consecutive_failures,
        "paused": state.paused,
        "backoff_until": state.backoff_until,
        "runs_in_window": state.runs_in_window,
        "window_started_at": state.window_started_at,
    }


def state_from_dict(data: Dict[str, object]) -> ScheduleState:
    return ScheduleState(
        policy_id=str(data.get("policy_id", "")),
        last_run_at=str(data.get("last_run_at", "")),
        consecutive_failures=int(data.get("consecutive_failures", 0)),
        paused=bool(data.get("paused", False)),
        backoff_until=str(data.get("backoff_until", "")),
        runs_in_window=int(data.get("runs_in_window", 0)),
        window_started_at=str(data.get("window_started_at", "")))


def calendar_to_dict(calendar: MarketHoursCalendar) -> Dict[str, object]:
    return {
        "open_utc": calendar.open_utc,
        "close_utc": calendar.close_utc,
        "holidays": list(calendar.holidays),
    }


def calendar_from_dict(data: Dict[str, object]) -> MarketHoursCalendar:
    return MarketHoursCalendar(
        open_utc=str(data.get("open_utc", "14:30")),
        close_utc=str(data.get("close_utc", "21:00")),
        holidays=tuple(data.get("holidays", ()) or ()))


def schedule_to_dict(schedule: PulseSchedule) -> Dict[str, object]:
    """A deterministic plain-dict form (policies/states sorted by policy_id)."""
    return {
        "max_runs_per_hour": schedule.max_runs_per_hour,
        "paused_all": schedule.paused_all,
        "policies": [policy_to_dict(p)
                     for p in sorted(schedule.policies, key=lambda p: p.policy_id)],
        "states": [state_to_dict(s)
                   for s in sorted(schedule.states, key=lambda s: s.policy_id)],
    }


def schedule_from_dict(data: Dict[str, object]) -> PulseSchedule:
    return PulseSchedule(
        policies=tuple(policy_from_dict(p) for p in data.get("policies", ()) or ()),
        states=tuple(state_from_dict(s) for s in data.get("states", ()) or ()),
        paused_all=bool(data.get("paused_all", False)),
        max_runs_per_hour=int(data.get("max_runs_per_hour", 60)))
