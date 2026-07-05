"""The PURE service-state CORE of the supervised operator service (IMPLEMENTATION-020C).

Phases 012-020B shipped the offline reality mesh, the persistence / replay / gate chain, the
015A cadence core, the 015B one-tick orchestrator, and the 016A operator-started app shell.
This slice is the supervised, always-on-CAPABLE **local operator service** -- and this module is
its DETERMINISTIC, OFFLINE-TESTABLE CORE. It holds only pure state logic:

* the mode state machine (:class:`ServiceMode`: ``OFF`` / ``MANUAL`` / ``SHADOW_24X7`` /
  ``PRODUCTION_24X7``; default ``OFF``);
* the single-instance lockfile (:func:`acquire_lock` / :func:`release_lock` -- a second acquire
  while held is refused; a stale lock is reclaimable);
* :func:`run_once` -- ONE supervised tick that CALLS the accepted 015B
  :func:`reality_mesh.orchestrator.run_due_pulses` through the FULL 013 chain (it never bypasses
  the DQ gates, replay, or the append-only stores);
* failure / backoff / health accounting and a sanitized, structured (JSONL) log line;
* the 020C health snapshot (:class:`ServiceHealth`) written to ``health_path`` as sanitized JSON.

The discipline that keeps this safe + testable: **there is NO loop here.** No ``while``, no
``time.sleep``, no thread, no socket, no wall-clock read -- every instant is an injected ISO-8601
``now`` string, exactly like the scheduler / orchestrator it drives. The ONLY place with a
``while`` + ``time.sleep`` loop is the operator-started :mod:`cosmosiq_service.__main__` process,
which is never imported by the tests. Importing this module starts nothing.

Activation gating (safe defaults): continuous ``PRODUCTION_24X7`` operation is REFUSED here and
requires the Phase-020F activation gate. Continuous ``SHADOW_24X7`` operation is ACTIVATED by
IMPLEMENTATION-020D: a shadow tick runs the full 013 chain and generates SHADOW (non-production)
alerts into the in-app inbox -- NO external delivery, NO production escalation. ``SHADOW_24X7`` is
NOT the default (the service starts ``OFF``) and is enabled only when an operator sets it
explicitly. A single :func:`run_once` tick is permitted in any non-``OFF`` mode; the continuous
PRODUCTION loop is what the remaining gate guards (see :mod:`cosmosiq_service.__main__`).

Stdlib-only, Python 3.9, OFFLINE. No network on import; no secret is ever written to the log or
the health file (every string is passed through :func:`sanitize`).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import timedelta
from enum import Enum
from typing import Dict, List, Mapping, Optional, Tuple

# The CORE consumes the accepted upstream slices; it never re-implements them.
from reality_mesh.ledger import AgentRunLedger
from reality_mesh.orchestrator import (
    Subscription,
    load_schedule_state,
    run_due_pulses,
)
from reality_mesh.scheduler import (
    DEFAULT_MARKET_HOURS,
    MarketHoursCalendar,
    PulseSchedule,
    _format_utc,
    _parse_utc,
    build_default_schedule,
    pause as _pause_schedule,
    resume as _resume_schedule,
    state_for,
)
from reality_mesh.orchestrator import append_schedule_state
from reality_mesh.scheduler import ALL_POLICIES
from reality_mesh.stores import DataQualityStore
from reality_mesh.alerts import generate_shadow_alerts_for_run

__all__ = [
    "ServiceMode",
    "DEFAULT_MODE",
    "continuous_activation_gate",
    "requires_activation_gate",
    "ServiceConfig",
    "ServiceHealth",
    "LockError",
    "LockHandle",
    "acquire_lock",
    "release_lock",
    "read_lock",
    "sanitize",
    "run_once",
    "pause",
    "resume",
    "load_health",
    "service_status",
]


# --------------------------------------------------------------------------- #
# 1. Modes -- the state machine (default OFF; continuous SHADOW/PRODUCTION      #
#    gated)                                                                     #
# --------------------------------------------------------------------------- #
class ServiceMode(Enum):
    """The four supervised-operator modes. ``OFF`` is the default and the safe posture.

    * ``OFF`` -- the service does nothing; :func:`run_once` is a no-op.
    * ``MANUAL`` -- operator-attended single ticks (``run-once``); the supervised loop is
      permitted only in this safe, attended mode.
    * ``SHADOW_24X7`` -- continuous shadow operation, GATED to the Phase-020D activation gate.
    * ``PRODUCTION_24X7`` -- continuous production operation, GATED to the Phase-020F gate; it is
      NOT the default and continuous operation must be explicitly activated there.
    """

    OFF = "off"
    MANUAL = "manual"
    SHADOW_24X7 = "shadow_24x7"
    PRODUCTION_24X7 = "production_24x7"

    @classmethod
    def parse(cls, value: object) -> "ServiceMode":
        """Parse a mode from a member / name / value (case-insensitive) -- closed vocabulary."""
        if isinstance(value, ServiceMode):
            return value
        text = str(value or "").strip().lower()
        for member in cls:
            if text in (member.value, member.name.lower()):
                return member
        raise ValueError(
            "unknown service mode {0!r} (allowed: {1})".format(
                value, [m.value for m in cls]))


# PRODUCTION_24X7 is deliberately NOT the default; the service starts OFF.
DEFAULT_MODE = ServiceMode.OFF

# Continuous operation in these modes is gated to a later phase (the machinery is here, the
# activation is not). A single run_once tick is always allowed (in any non-OFF mode).
#
# IMPLEMENTATION-020D LIFTS the SHADOW_24X7 continuous gate: continuous SHADOW operation is now
# activated -- a shadow tick runs the full 013 chain and generates SHADOW (non-production)
# alerts into the in-app inbox, with NO external delivery and NO production escalation.
# Continuous PRODUCTION_24X7 stays REFUSED here and requires the Phase-020F activation gate.
_CONTINUOUS_ACTIVATION_GATE: Dict[ServiceMode, str] = {
    ServiceMode.PRODUCTION_24X7: "Phase-020F",
}


def requires_activation_gate(mode: ServiceMode) -> bool:
    """True iff CONTINUOUS operation in ``mode`` is gated (SHADOW_24X7 / PRODUCTION_24X7)."""
    return ServiceMode.parse(mode) in _CONTINUOUS_ACTIVATION_GATE


def continuous_activation_gate(mode: ServiceMode) -> str:
    """The gate phase that must grant CONTINUOUS operation in ``mode`` ("" if none needed).

    ``SHADOW_24X7`` -> ``Phase-020D``; ``PRODUCTION_24X7`` -> ``Phase-020F``. ``OFF`` / ``MANUAL``
    return "" (OFF runs nothing; MANUAL is the attended supervised loop this slice permits).
    """
    return _CONTINUOUS_ACTIVATION_GATE.get(ServiceMode.parse(mode), "")


# --------------------------------------------------------------------------- #
# 2. Secret sanitization -- no secret ever reaches a log line or the health     #
#    file                                                                       #
# --------------------------------------------------------------------------- #
# key=value / key: value shapes for a credential-ish key (the VALUE is redacted).
_SECRET_KV = re.compile(
    r"(?i)\b(api[\-_]?key|secret[\-_]?key|client[\-_]?secret|access[\-_]?key|secret|token|"
    r"password|passwd|pwd|bearer|authorization|auth[\-_]?token)\b\s*[=:]\s*[^\s,;\"']+")
# Common opaque-secret token shapes (OpenAI-style, AWS access-key id, long opaque blobs).
_SECRET_TOKENS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"\bAKIA[0-9A-Z]{8,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{8,}"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),   # long base64/hex blob (run ids are dotted)
)
_REDACTED = "<redacted>"


def sanitize(value: object) -> object:
    """Redact secret-shaped tokens from any string (recurses into dict / list / tuple).

    A credential ``key=value`` keeps its key and redacts the value; a bare ``sk-``/``AKIA``/long
    opaque blob is redacted whole. Counts, labels, ids, and timestamps pass through unchanged.
    Every string written to the log or the health file passes through here.
    """
    if isinstance(value, str):
        text = _SECRET_KV.sub(lambda m: m.group(0).split("=")[0].split(":")[0].rstrip()
                              + "=" + _REDACTED, value)
        for pattern in _SECRET_TOKENS:
            text = pattern.sub(_REDACTED, text)
        return text
    if isinstance(value, Mapping):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    return value


# --------------------------------------------------------------------------- #
# 3. ServiceConfig -- frozen operator configuration                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ServiceConfig:
    """The frozen configuration for one supervised operator service.

    ``store_dir`` is the append-only 013B/015 store the tick persists into. ``subscriptions`` are
    the watchlist/theme scopes cadence policies resolve to (config references only, never a
    secret). ``health_path`` / ``log_path`` / ``lock_path`` default under ``store_dir``. Backoff
    is deterministic: ``base_backoff_seconds * backoff_multiplier**(failures-1)`` capped at
    ``max_backoff_seconds``. ``poll_interval_seconds`` is the loop cadence (used ONLY by the
    operator-started __main__ process; the CORE never sleeps).
    """

    mode: ServiceMode = DEFAULT_MODE
    store_dir: str = ""
    subscriptions: Tuple[Subscription, ...] = field(default_factory=tuple)
    max_runs_per_hour: int = 60
    calendar: MarketHoursCalendar = DEFAULT_MARKET_HOURS
    max_pulses: int = 1
    health_path: str = ""
    log_path: str = ""
    lock_path: str = ""
    base_backoff_seconds: int = 30
    backoff_multiplier: int = 2
    max_backoff_seconds: int = 3600
    max_consecutive_failures: int = 5
    lock_stale_seconds: int = 3600
    poll_interval_seconds: int = 60

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ServiceMode.parse(self.mode))
        if not str(self.store_dir).strip():
            raise ValueError("ServiceConfig.store_dir is required and must be non-empty")
        object.__setattr__(self, "subscriptions", tuple(self.subscriptions))
        for name in ("max_runs_per_hour", "max_pulses", "base_backoff_seconds",
                     "backoff_multiplier", "max_backoff_seconds", "max_consecutive_failures",
                     "lock_stale_seconds", "poll_interval_seconds"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(
                    "ServiceConfig.{0} must be an integer >= 1 (got {1!r})".format(name, value))
        store = str(self.store_dir)
        if not str(self.health_path).strip():
            object.__setattr__(self, "health_path",
                               os.path.join(store, "service_health.json"))
        if not str(self.log_path).strip():
            object.__setattr__(self, "log_path", os.path.join(store, "service_log.jsonl"))
        if not str(self.lock_path).strip():
            object.__setattr__(self, "lock_path", os.path.join(store, "service.lock"))


# --------------------------------------------------------------------------- #
# 4. ServiceHealth -- the 020C health snapshot (frozen; sanitized JSON)         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ServiceHealth:
    """The 020C health model. Written to ``health_path`` as sanitized JSON.

    Every field is a label / count / injected timestamp / small summary dict -- never a secret
    and never a score. ``last_error_message_sanitized`` is already scrubbed of secret shapes.
    """

    service_mode: str = DEFAULT_MODE.value
    is_running: bool = False
    is_paused: bool = False
    pid: int = 0
    lock_status: str = "free"           # free / held / stale_reclaimed / unknown
    last_tick_started_at: str = ""
    last_tick_completed_at: str = ""
    last_tick_failed_at: str = ""
    last_successful_run_id: str = ""
    last_failed_run_id: str = ""
    consecutive_failures: int = 0
    last_error_class: str = ""
    last_error_message_sanitized: str = ""
    next_scheduled_tick_at: str = ""
    next_retry_at: str = ""             # deterministic backoff instant ("" = no backoff)
    source_health_summary: Dict[str, object] = field(default_factory=dict)
    agent_health_summary: Dict[str, object] = field(default_factory=dict)
    dq_status_summary: Dict[str, object] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> Dict[str, object]:
        """A deterministic, sanitized plain-dict form (safe to write to disk / print)."""
        return sanitize({
            "service_mode": self.service_mode,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "pid": self.pid,
            "lock_status": self.lock_status,
            "last_tick_started_at": self.last_tick_started_at,
            "last_tick_completed_at": self.last_tick_completed_at,
            "last_tick_failed_at": self.last_tick_failed_at,
            "last_successful_run_id": self.last_successful_run_id,
            "last_failed_run_id": self.last_failed_run_id,
            "consecutive_failures": self.consecutive_failures,
            "last_error_class": self.last_error_class,
            "last_error_message_sanitized": self.last_error_message_sanitized,
            "next_scheduled_tick_at": self.next_scheduled_tick_at,
            "next_retry_at": self.next_retry_at,
            "source_health_summary": self.source_health_summary,
            "agent_health_summary": self.agent_health_summary,
            "dq_status_summary": self.dq_status_summary,
            "updated_at": self.updated_at,
        })

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ServiceHealth":
        data = dict(data or {})
        return cls(
            service_mode=str(data.get("service_mode", DEFAULT_MODE.value)),
            is_running=bool(data.get("is_running", False)),
            is_paused=bool(data.get("is_paused", False)),
            pid=int(data.get("pid", 0) or 0),
            lock_status=str(data.get("lock_status", "free")),
            last_tick_started_at=str(data.get("last_tick_started_at", "")),
            last_tick_completed_at=str(data.get("last_tick_completed_at", "")),
            last_tick_failed_at=str(data.get("last_tick_failed_at", "")),
            last_successful_run_id=str(data.get("last_successful_run_id", "")),
            last_failed_run_id=str(data.get("last_failed_run_id", "")),
            consecutive_failures=int(data.get("consecutive_failures", 0) or 0),
            last_error_class=str(data.get("last_error_class", "")),
            last_error_message_sanitized=str(data.get("last_error_message_sanitized", "")),
            next_scheduled_tick_at=str(data.get("next_scheduled_tick_at", "")),
            next_retry_at=str(data.get("next_retry_at", "")),
            source_health_summary=dict(data.get("source_health_summary", {}) or {}),
            agent_health_summary=dict(data.get("agent_health_summary", {}) or {}),
            dq_status_summary=dict(data.get("dq_status_summary", {}) or {}),
            updated_at=str(data.get("updated_at", "")))


# --------------------------------------------------------------------------- #
# 5. Single-instance lock -- a duplicate service is refused; a stale lock is     #
#    reclaimable                                                                 #
# --------------------------------------------------------------------------- #
class LockError(RuntimeError):
    """Raised when the single-instance lock is already held (a duplicate service is refused)."""


@dataclass(frozen=True)
class LockHandle:
    """A held lock: its path, the pid that holds it, when it was acquired, was it reclaimed."""

    lock_path: str = ""
    pid: int = 0
    acquired_at: str = ""
    reclaimed_stale: bool = False


def read_lock(lock_path: str) -> Optional[Dict[str, object]]:
    """The current lock payload ({pid, acquired_at}) or None (no lock / unreadable)."""
    try:
        with open(lock_path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, ValueError, OSError):
        return None
    return None


def _seconds_between(earlier_iso: str, now_iso: str) -> Optional[float]:
    try:
        return (_parse_utc(now_iso) - _parse_utc(earlier_iso)).total_seconds()
    except ValueError:
        return None


def acquire_lock(lock_path: str, *, pid: int, now: str,
                 stale_after_seconds: int = 3600) -> LockHandle:
    """Acquire the single-instance lock at ``lock_path`` -- or refuse a live duplicate.

    A SECOND acquire while a valid (non-stale) lock is held raises :class:`LockError` -- this is
    what prevents two services from running at once. A lock whose ``acquired_at`` is older than
    ``stale_after_seconds`` (relative to the injected ``now``) is considered stale and is
    reclaimed (``reclaimed_stale=True``); a corrupt / unreadable lockfile is likewise reclaimable.
    Deterministic: the injected ``now`` is the only clock.
    """
    if not str(lock_path).strip():
        raise ValueError("acquire_lock requires a non-empty lock_path")
    stamped = _format_utc(_parse_utc(now, name="now"))
    existing = read_lock(lock_path)
    reclaimed = False
    if existing is not None:
        acquired_at = str(existing.get("acquired_at", ""))
        age = _seconds_between(acquired_at, stamped) if acquired_at else None
        is_stale = age is not None and age >= float(stale_after_seconds)
        if not is_stale:
            raise LockError(
                "service lock at {0} already held by pid {1} since {2} -- a duplicate service "
                "is refused (single-instance)".format(
                    lock_path, existing.get("pid", "?"), acquired_at or "unknown"))
        reclaimed = True
    parent = os.path.dirname(lock_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    payload = {"pid": int(pid), "acquired_at": stamped}
    tmp = lock_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True)
    os.replace(tmp, lock_path)
    return LockHandle(lock_path=lock_path, pid=int(pid), acquired_at=stamped,
                      reclaimed_stale=reclaimed)


def release_lock(handle: Optional[LockHandle]) -> None:
    """Release a held lock (idempotent -- a missing lockfile is not an error)."""
    if handle is None:
        return
    try:
        os.remove(handle.lock_path)
    except FileNotFoundError:
        pass


# --------------------------------------------------------------------------- #
# 6. Health / log persistence (sanitized; deterministic; injected now)          #
# --------------------------------------------------------------------------- #
def load_health(config: ServiceConfig) -> ServiceHealth:
    """Reload the last persisted health snapshot (a default snapshot if none exists yet)."""
    try:
        with open(config.health_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return ServiceHealth.from_dict(data)
    except (FileNotFoundError, ValueError, OSError):
        return ServiceHealth(service_mode=config.mode.value)


def _write_health(config: ServiceConfig, health: ServiceHealth) -> None:
    parent = os.path.dirname(config.health_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = config.health_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(health.to_dict(), fh, sort_keys=True, indent=2)
    os.replace(tmp, config.health_path)


def _emit_log(config: ServiceConfig, line: Dict[str, object]) -> None:
    """Append ONE structured (JSON) sanitized log line to ``log_path``."""
    parent = os.path.dirname(config.log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    record = sanitize(line)
    with open(config.log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


# --------------------------------------------------------------------------- #
# 7. Pure helpers (injected time only; no wall clock)                           #
# --------------------------------------------------------------------------- #
def _resolved_schedule(config: ServiceConfig) -> PulseSchedule:
    """The journaled schedule if one exists, else a fresh default over the accepted policies."""
    schedule = load_schedule_state(config.store_dir)
    if schedule is None:
        schedule = build_default_schedule(max_runs_per_hour=config.max_runs_per_hour)
    return schedule


def _next_boundary(schedule: PulseSchedule, now: str) -> str:
    """The earliest injected instant the schedule could next be due (a cadence-boundary hint)."""
    if schedule.paused_all:
        return ""
    candidates: List[str] = []
    for policy in schedule.policies:
        state = state_for(schedule, policy.policy_id)
        if state.paused:
            continue
        if state.backoff_until:
            candidates.append(state.backoff_until)
        elif state.last_run_at:
            nxt = _parse_utc(state.last_run_at) + timedelta(minutes=policy.interval_minutes)
            candidates.append(_format_utc(nxt))
        else:
            candidates.append(_format_utc(_parse_utc(now)))     # never run -> due now
    return min(candidates) if candidates else ""


def _backoff_seconds(config: ServiceConfig, failures: int) -> int:
    """Deterministic exponential backoff seconds for ``failures`` consecutive failures."""
    if failures < 1:
        return 0
    raw = config.base_backoff_seconds * (config.backoff_multiplier ** (failures - 1))
    return int(min(raw, config.max_backoff_seconds))


def _failed_run_id(failed_lines: Tuple[str, ...]) -> str:
    """Pull the failed pulse's run id out of an orchestrator ``failed`` note ("" if absent)."""
    for line in failed_lines:
        match = re.search(r"pulse (\S+) FAILED", line)
        if match:
            return match.group(1)
    return ""


def _run_summaries(store_dir: str, run_id: str) -> Tuple[Dict, Dict, Dict]:
    """Roll the persisted records for ``run_id`` into the 3 health summary dicts (counts only)."""
    dq = DataQualityStore(store_dir).query(run_id=run_id)
    dq_statuses: Dict[str, int] = {}
    coverage = 0
    source_failures = 0
    gate_ran = False
    for record in dq:
        dq_statuses[record.status] = dq_statuses.get(record.status, 0) + 1
        if record.category == "coverage":
            coverage += 1
        if record.category == "source_failure":
            source_failures += 1
        if record.category.startswith("gate"):
            gate_ran = True
    dq_summary = {
        "records": len(dq),
        "gate_ran": gate_ran,
        "statuses": {k: dq_statuses[k] for k in sorted(dq_statuses)},
    }
    source_summary = {
        "coverage_records": coverage,
        "failed_source_records": source_failures,
    }
    results = AgentRunLedger(store_dir).results_for_run(run_id)
    agent_summary = {
        "results": len(results),
        "succeeded": sum(1 for r in results if r.status in ("success", "partial")),
        "failed": sum(1 for r in results if r.status == "failed"),
    }
    return source_summary, agent_summary, dq_summary


def _commit(config: ServiceConfig, health: ServiceHealth, log_line: Dict[str, object]
            ) -> ServiceHealth:
    """Persist the health snapshot + append the structured log line; return the health."""
    _write_health(config, health)
    _emit_log(config, log_line)
    return health


# --------------------------------------------------------------------------- #
# 8. pause / resume -- journaled schedule state (a paused service runs nothing)  #
# --------------------------------------------------------------------------- #
def pause(config: ServiceConfig, *, now: str) -> ServiceHealth:
    """Pause the service: journal ``paused_all`` on the schedule (append-only) + update health.

    A paused service's :func:`run_once` runs nothing (the journaled schedule is ``paused_all``).
    """
    schedule = _pause_schedule(_resolved_schedule(config), ALL_POLICIES, now)
    append_schedule_state(config.store_dir, schedule, now=now, note="service paused by operator")
    prev = load_health(config)
    stamped = _format_utc(_parse_utc(now, name="now"))
    health = replace(prev, service_mode=config.mode.value, is_paused=True, updated_at=stamped,
                     next_scheduled_tick_at="")
    return _commit(config, health, {
        "ts": stamped, "level": "info", "event": "service.paused",
        "service_mode": config.mode.value, "is_paused": True})


def resume(config: ServiceConfig, *, now: str) -> ServiceHealth:
    """Resume the service: journal ``resume(all)`` (an unexpired per-policy backoff still holds)."""
    schedule = _resume_schedule(_resolved_schedule(config), ALL_POLICIES, now)
    append_schedule_state(config.store_dir, schedule, now=now,
                          note="service resumed by operator")
    prev = load_health(config)
    stamped = _format_utc(_parse_utc(now, name="now"))
    health = replace(prev, service_mode=config.mode.value, is_paused=False, updated_at=stamped,
                     next_scheduled_tick_at=_next_boundary(schedule, now))
    return _commit(config, health, {
        "ts": stamped, "level": "info", "event": "service.resumed",
        "service_mode": config.mode.value, "is_paused": False})


def service_status(config: ServiceConfig) -> ServiceHealth:
    """The current health snapshot, refreshed with the live lock status (read-only)."""
    health = load_health(config)
    lock = read_lock(config.lock_path)
    lock_status = "held" if lock is not None else "free"
    return replace(health, service_mode=config.mode.value, lock_status=lock_status,
                   pid=int(lock.get("pid", 0)) if lock else health.pid)


# --------------------------------------------------------------------------- #
# 9. run_once -- ONE supervised tick that CALLS run_due_pulses (never bypasses   #
#    it)                                                                         #
# --------------------------------------------------------------------------- #
def run_once(config: ServiceConfig, *, now: str, is_running: bool = False,
             pid: int = 0) -> ServiceHealth:
    """Run ONE supervised tick at the injected ``now``; persist health + a structured log line.

    Flow: OFF / paused / active-backoff -> a recorded no-op (nothing runs, the reason is logged).
    Otherwise acquire the single-instance lock, call the accepted 015B
    :func:`reality_mesh.orchestrator.run_due_pulses` for ONE tick through the FULL 013 chain
    (stores / ledger / health / DQ gates / verification replay -- never bypassed), then release
    the lock. A successful pulse updates ``last_successful_run_id`` / ``last_tick_completed_at``
    and clears the failure count; a failed pulse increments ``consecutive_failures``, sets
    ``last_error_class`` / ``last_error_message_sanitized`` / ``last_tick_failed_at``, and applies
    deterministic backoff (``next_retry_at``) -- WITHOUT corrupting the append-only stores, WITHOUT
    a fixture fall-back, and WITHOUT any production alert (mode-gated). Returns the new health.
    """
    stamped = _format_utc(_parse_utc(now, name="now"))
    prev = load_health(config)
    base = replace(prev, service_mode=config.mode.value, is_running=is_running, pid=pid,
                   updated_at=stamped)

    # -- OFF: the safe default runs nothing ---------------------------------- #
    if config.mode is ServiceMode.OFF:
        health = replace(base, is_paused=False, lock_status="free")
        return _commit(config, health, {
            "ts": stamped, "level": "info", "event": "tick.off",
            "service_mode": config.mode.value,
            "message": "service_mode=OFF -- run_once does nothing (default safe posture)"})

    schedule = _resolved_schedule(config)

    # -- paused: nothing runs ------------------------------------------------ #
    if schedule.paused_all:
        health = replace(base, is_paused=True, lock_status="free", next_scheduled_tick_at="")
        return _commit(config, health, {
            "ts": stamped, "level": "info", "event": "tick.paused",
            "service_mode": config.mode.value,
            "message": "service is paused (paused_all) -- run_once runs nothing until resume"})

    # -- active failure backoff: skip this tick ------------------------------ #
    if prev.next_retry_at and stamped < prev.next_retry_at:
        health = replace(base, is_paused=False, lock_status="free")
        return _commit(config, health, {
            "ts": stamped, "level": "warning", "event": "tick.backoff",
            "service_mode": config.mode.value,
            "consecutive_failures": prev.consecutive_failures,
            "next_retry_at": prev.next_retry_at,
            "message": "in failure backoff until {0} -- skipping this tick".format(
                prev.next_retry_at)})

    # -- acquire the single-instance lock (a duplicate service is refused) ---- #
    try:
        handle = acquire_lock(config.lock_path, pid=pid, now=stamped,
                              stale_after_seconds=config.lock_stale_seconds)
    except LockError as exc:
        health = replace(base, lock_status="held")
        return _commit(config, health, {
            "ts": stamped, "level": "warning", "event": "tick.lock_held",
            "service_mode": config.mode.value,
            "message": sanitize(str(exc))})

    lock_status = "stale_reclaimed" if handle.reclaimed_stale else "held"
    try:
        try:
            result = run_due_pulses(
                schedule, now=stamped, store_dir=config.store_dir,
                subscriptions=config.subscriptions, calendar=config.calendar,
                max_pulses=config.max_pulses)
        except Exception as exc:            # a hard tick failure (bad config etc.)
            health = _record_failure(
                config, base, now=stamped, run_id="",
                error_class=type(exc).__name__,
                message=" ".join("{0}: {1}".format(type(exc).__name__, exc).split())[:300],
                lock_status=lock_status)
            return health

        if result.ran:
            return _record_success(config, base, result, now=stamped, lock_status=lock_status)
        if result.failed:
            run_id = _failed_run_id(result.failed)
            return _record_failure(
                config, base, now=stamped, run_id=run_id,
                error_class="ScheduledPulseFailure",
                message=result.failed[0], lock_status=lock_status,
                new_schedule=result.schedule)
        # nothing due / everything skipped -> an honest idle tick (not a failure)
        health = replace(
            base, lock_status="free", is_paused=False,
            last_tick_started_at=stamped,
            next_scheduled_tick_at=_next_boundary(result.schedule, stamped))
        return _commit(config, health, {
            "ts": stamped, "level": "info", "event": "tick.idle",
            "service_mode": config.mode.value,
            "skipped": len(result.skipped), "notes": len(result.notes),
            "message": "no policy was due this tick -- nothing ran"})
    finally:
        release_lock(handle)


def _record_success(config: ServiceConfig, base: ServiceHealth, result, *, now: str,
                    lock_status: str) -> ServiceHealth:
    run_id = result.pulse_runs[-1].run_id
    source_summary, agent_summary, dq_summary = _run_summaries(config.store_dir, run_id)
    health = replace(
        base, lock_status="free", is_paused=False,
        last_tick_started_at=now, last_tick_completed_at=now,
        last_successful_run_id=run_id, consecutive_failures=0,
        last_error_class="", last_error_message_sanitized="", next_retry_at="",
        next_scheduled_tick_at=_next_boundary(result.schedule, now),
        source_health_summary=source_summary, agent_health_summary=agent_summary,
        dq_status_summary=dq_summary)
    log: Dict[str, object] = {
        "ts": now, "level": "info", "event": "tick.success",
        "service_mode": config.mode.value, "run_id": run_id,
        "ran": len(result.ran), "dq_gate_ran": dq_summary.get("gate_ran", False),
        "message": "scheduled tick persisted through the 013 chain (run {0})".format(run_id)}

    # 020D SHADOW hook: a shadow tick ALSO generates SHADOW (non-production) alerts into the
    # in-app inbox -- marked, review-tagged, DQ-carrying. It NEVER escalates and there is NO
    # external delivery (that is Phase-020E); a shadow-alert failure never fails the tick.
    if config.mode is ServiceMode.SHADOW_24X7:
        log["external_delivery"] = False
        log["production_escalation"] = False
        try:
            observed = generate_shadow_alerts_for_run(config.store_dir, run_id, now=now)
            log["shadow_alerts"] = len(observed.alerts)
            log["alerts_channel"] = "in_app_inbox_only"
        except Exception as exc:            # surfaced, never hidden; the pulse still succeeded
            log["shadow_alerts_error"] = sanitize(
                " ".join("{0}: {1}".format(type(exc).__name__, exc).split())[:200])
    return _commit(config, health, log)


def _record_failure(config: ServiceConfig, base: ServiceHealth, *, now: str, run_id: str,
                    error_class: str, message: str, lock_status: str,
                    new_schedule: Optional[PulseSchedule] = None) -> ServiceHealth:
    failures = base.consecutive_failures + 1
    backoff = _backoff_seconds(config, failures)
    next_retry = _format_utc(_parse_utc(now) + timedelta(seconds=backoff)) if backoff else ""
    safe_message = sanitize(message)
    circuit_open = failures >= config.max_consecutive_failures
    schedule = new_schedule if new_schedule is not None else _resolved_schedule(config)
    health = replace(
        base, lock_status="free", is_paused=False,
        last_tick_started_at=now, last_tick_failed_at=now,
        last_failed_run_id=run_id or base.last_failed_run_id,
        consecutive_failures=failures, last_error_class=error_class,
        last_error_message_sanitized=safe_message, next_retry_at=next_retry,
        next_scheduled_tick_at=_next_boundary(schedule, now))
    return _commit(config, health, {
        "ts": now, "level": "error", "event": "tick.failed",
        "service_mode": config.mode.value, "run_id": run_id,
        "error_class": error_class, "consecutive_failures": failures,
        "backoff_seconds": backoff, "next_retry_at": next_retry,
        "circuit_open": circuit_open, "message": safe_message})
