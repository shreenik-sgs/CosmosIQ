"""Production observability / monitoring / health surface for CosmosIQ (IMPLEMENTATION-023E).

A SINGLE, sanitized observability surface that AGGREGATES every health signal the accepted
upstream slices already produce -- it re-implements NONE of them. It READS the persisted
append-only stores + the operator artifacts and folds them into one frozen
:class:`ObservabilityReport`, one health JSON, one metrics file, and one structured-log helper:

* :func:`aggregate_observability` -- the read-only aggregation core. It COMPOSES the 020C
  :class:`~cosmosiq_service.service.ServiceHealth` (``load_health``), the 013D source / agent
  health (:class:`~reality_mesh.health.AgentHealthMonitor` over the append-only
  :class:`~reality_mesh.ledger.AgentRunLedger`), the 013E Data-Quality diagnostics
  (:class:`~reality_mesh.stores.DataQualityStore`), the 015 schedule journal
  (``load_schedule_state``), the 020E alert-delivery ledger (``delivery_results``), the 013B
  :class:`~reality_mesh.stores.RunStore` run timestamps (run latency, last successful / failed
  pulse), the 013C :class:`~reality_mesh.replay.ReplayHarness` (last replay check), and the 023D
  persistence-hardening integrity / schema posture (``integrity_check`` /
  ``schema_compatibility_check``). Every instant is the INJECTED ``now`` -- there is NO wall-clock
  read anywhere in the aggregation path, so the whole surface is byte-deterministic.

* :func:`render_health_json` -- the sanitized health JSON (a rolled ``status``: ok / degraded /
  failed).
* :func:`render_metrics` -- a stable ``key value`` metrics file (counts + labels + injected-time
  latencies; deterministic; no secret).
* :func:`emit_structured_log` -- ONE sanitized JSON log line reusing the 020C structured-log shape.

HARD DISCIPLINE: every string is passed through the accepted 020C :func:`~cosmosiq_service.service.sanitize`
so NO secret VALUE ever reaches the health JSON, the metrics file, or a log line (env vars are
PRESENCE labels only, never values). Failures AND successes both update the health honestly.
Metrics are LABELS + COUNTS + injected-time-derived latencies -- NEVER a score / rank / trade /
order. Reads only; mutates nothing. Deterministic, stdlib-only, Python 3.9, OFFLINE.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

# Reuse the accepted 020C service-health load + the single sanitize() helper (no re-implementation).
from cosmosiq_service.service import ServiceConfig, ServiceHealth, load_health, sanitize

# Reuse the 023D persistence-hardening integrity + schema posture.
from cosmosiq_ops.persistence_hardening import (
    SUPPORTED_SCHEMA_VERSIONS,
    integrity_check,
    schema_compatibility_check,
)

# Reuse the injected-time parse/format the whole runtime uses (NO wall-clock helper is imported).
from reality_mesh.scheduler import _format_utc, _parse_utc

# Config env-var NAMES (presence labels only -- a value is NEVER read).
from cosmosiq_ops.secrets_config import ALL_CONFIG_ENV_VARS, REQUIRED_ENV_VARS

__all__ = [
    "STATUS_OK",
    "STATUS_DEGRADED",
    "STATUS_FAILED",
    "STATUS_SEVERITY",
    "ObservabilityReport",
    "aggregate_observability",
    "render_health_json",
    "render_metrics",
    "emit_structured_log",
]

# The three rolled health states (severity-ordered) -- never a score.
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_FAILED = "failed"
STATUS_SEVERITY: Dict[str, int] = {STATUS_OK: 0, STATUS_DEGRADED: 1, STATUS_FAILED: 2}

# The persisted DQ / run status ladder -> a health status contribution.
_RUN_STATUS_TO_HEALTH: Dict[str, str] = {
    "healthy": STATUS_OK,
    "pass": STATUS_OK,
    "degraded": STATUS_DEGRADED,
    "warn": STATUS_DEGRADED,
    "failed": STATUS_FAILED,
    "fail": STATUS_FAILED,
    "blocked_by_policy": STATUS_FAILED,
}
_RUN_STATUS_SEVERITY: Dict[str, int] = {
    "healthy": 0, "pass": 0, "degraded": 1, "warn": 1, "failed": 2, "fail": 2,
    "blocked_by_policy": 3,
}


def _worst_status(statuses) -> str:
    """The worst health status (ok < degraded < failed) across contributions (ok if none)."""
    worst = STATUS_OK
    for status in statuses:
        if STATUS_SEVERITY.get(status, 0) > STATUS_SEVERITY[worst]:
            worst = status
    return worst


def _seconds_between(earlier_iso: str, later_iso: str) -> Optional[float]:
    """Injected-time latency in seconds between two ISO instants (None if unparseable)."""
    try:
        return (_parse_utc(later_iso) - _parse_utc(earlier_iso)).total_seconds()
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# The frozen aggregate report                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ObservabilityReport:
    """The single, sanitized observability surface -- every health signal in one frozen object.

    Each field is a label / count / injected-time latency / small summary dict -- NEVER a secret,
    NEVER a score / rank / trade. ``status`` is the rolled ok / degraded / failed verdict. Build
    with :func:`aggregate_observability`; render with :func:`render_health_json` /
    :func:`render_metrics`.
    """

    store_dir: str = ""
    generated_at: str = ""
    status: str = STATUS_OK
    service_health: Dict[str, object] = field(default_factory=dict)
    source_health_summary: Dict[str, object] = field(default_factory=dict)
    agent_health_summary: Dict[str, object] = field(default_factory=dict)
    scheduler_health: Dict[str, object] = field(default_factory=dict)
    alert_delivery_health: Dict[str, object] = field(default_factory=dict)
    dq_status_summary: Dict[str, object] = field(default_factory=dict)
    run_latency: Dict[str, object] = field(default_factory=dict)
    failure_counts: Dict[str, object] = field(default_factory=dict)
    last_successful_pulse: Dict[str, object] = field(default_factory=dict)
    last_failed_pulse: Dict[str, object] = field(default_factory=dict)
    last_replay_check: Dict[str, object] = field(default_factory=dict)
    storage_health: Dict[str, object] = field(default_factory=dict)
    backup_health: Dict[str, object] = field(default_factory=dict)
    env_presence: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """A deterministic, SANITIZED plain-dict form (safe to write to disk / print / serve)."""
        return sanitize({
            "app": "CosmosIQ",
            "surface": "observability",
            "store_dir": self.store_dir,
            "generated_at": self.generated_at,
            "status": self.status,
            "service_health": self.service_health,
            "source_health_summary": self.source_health_summary,
            "agent_health_summary": self.agent_health_summary,
            "scheduler_health": self.scheduler_health,
            "alert_delivery_health": self.alert_delivery_health,
            "dq_status_summary": self.dq_status_summary,
            "run_latency": self.run_latency,
            "failure_counts": self.failure_counts,
            "last_successful_pulse": self.last_successful_pulse,
            "last_failed_pulse": self.last_failed_pulse,
            "last_replay_check": self.last_replay_check,
            "storage_health": self.storage_health,
            "backup_health": self.backup_health,
            "env_presence": self.env_presence,
            "notes": [
                "single sanitized observability surface -- labels + volume counts + "
                "injected-time latencies only; never a metric, never an execution control, "
                "never a secret value",
            ],
        })


# --------------------------------------------------------------------------- #
# Component aggregators (each READ-ONLY, deterministic, injected-time)           #
# --------------------------------------------------------------------------- #
def _service_health(store_dir: str) -> Tuple[ServiceHealth, Dict[str, object]]:
    """The 020C service-health snapshot as (typed, sanitized plain dict)."""
    health = load_health(ServiceConfig(store_dir=store_dir))
    return health, health.to_dict()


def _agent_health(store_dir: str) -> Dict[str, object]:
    """Roll every persisted agent-run result into a labels + counts summary (013D)."""
    from reality_mesh.health import AgentHealthMonitor
    from reality_mesh.ledger import AgentRunLedger

    results = AgentRunLedger(store_dir).read_all()
    succeeded = sum(1 for r in results if r.status in ("success", "partial"))
    failed = sum(1 for r in results if r.status == "failed")
    blocked = sum(1 for r in results if r.status == "blocked_by_policy")
    skipped = sum(1 for r in results if r.status == "skipped")
    records = AgentHealthMonitor().roll_agent_health(results)
    currently_failed = sum(1 for rec in records if rec.last_status == "failed")
    return {
        "results": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "blocked": blocked,
        "skipped": skipped,
        "agents_tracked": len(records),
        "agents_currently_failed": currently_failed,
    }


def _source_health(store_dir: str, service_health: ServiceHealth) -> Dict[str, object]:
    """Source-delivery health from the persisted DQ diagnostics + the last service tick (013D)."""
    from reality_mesh.stores import DataQualityStore

    records = DataQualityStore(store_dir).read_all()
    coverage_records = sum(1 for r in records if r.category == "coverage")
    source_failure_records = sum(1 for r in records if r.category == "source_failure")
    return {
        "coverage_records": coverage_records,
        "source_failure_records": source_failure_records,
        "last_tick_source_summary": dict(service_health.source_health_summary or {}),
    }


def _scheduler_health(store_dir: str) -> Dict[str, object]:
    """The 015 schedule posture: policies / paused / backoff / failures (labels + counts)."""
    from reality_mesh.orchestrator import load_schedule_state
    from reality_mesh.scheduler import state_for

    schedule = load_schedule_state(store_dir)
    if schedule is None:
        return {"configured": False, "paused_all": False, "policies": 0,
                "paused_policies": 0, "backoff_policies": 0, "consecutive_failures": 0}
    paused = 0
    backoff = 0
    failures = 0
    for policy in schedule.policies:
        state = state_for(schedule, policy.policy_id)
        if state.paused:
            paused += 1
        if state.backoff_until:
            backoff += 1
        failures += state.consecutive_failures
    return {
        "configured": True,
        "paused_all": bool(schedule.paused_all),
        "policies": len(schedule.policies),
        "paused_policies": paused,
        "backoff_policies": backoff,
        "consecutive_failures": failures,
    }


def _alert_delivery_health(store_dir: str) -> Dict[str, object]:
    """The 020E delivery ledger rolled to counts by status + the last (sanitized) attempt."""
    from reality_mesh.alert_delivery import AlertDeliveryStatus, delivery_results

    results = delivery_results(store_dir)
    by_status: Dict[str, int] = {}
    last_at = ""
    for res in results:
        by_status[res.status] = by_status.get(res.status, 0) + 1
        if res.attempted_at > last_at:
            last_at = res.attempted_at
    failed = (by_status.get(AlertDeliveryStatus.FAILED_PERMANENT, 0)
              + by_status.get(AlertDeliveryStatus.FAILED_RETRYABLE, 0))
    return {
        "attempts": len(results),
        "delivered": by_status.get(AlertDeliveryStatus.DELIVERED, 0),
        "failed": failed,
        "by_status": {k: by_status[k] for k in sorted(by_status)},
        "last_attempt_at": last_at,
    }


def _dq_status_summary(store_dir: str) -> Tuple[Dict[str, object], str]:
    """Per-run DQ diagnostics rolled to counts + the worst persisted gate verdict (013E)."""
    from reality_mesh.stores import DataQualityStore

    records = DataQualityStore(store_dir).read_all()
    by_status: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    fail_records = 0
    worst = "healthy"
    for rec in records:
        by_status[rec.status] = by_status.get(rec.status, 0) + 1
        by_category[rec.category] = by_category.get(rec.category, 0) + 1
        if rec.status in ("fail", "failed", "blocked_by_policy"):
            fail_records += 1
        if rec.category == "gate_overall":
            if _RUN_STATUS_SEVERITY.get(rec.status, 0) > _RUN_STATUS_SEVERITY.get(worst, 0):
                worst = rec.status
    summary = {
        "records": len(records),
        "fail_records": fail_records,
        "gate_overall_worst": worst,
        "by_status": {k: by_status[k] for k in sorted(by_status)},
        "by_category": {k: by_category[k] for k in sorted(by_category)},
    }
    return summary, worst


def _runs_newest_first(store_dir: str):
    """Every persisted PulseRun, newest first (by injected started_at then run_id)."""
    from reality_mesh.stores import RunStore

    runs = list(RunStore(store_dir).read_all())
    return sorted(runs, key=lambda r: (r.started_at, r.run_id), reverse=True)


def _run_latency(runs) -> Dict[str, object]:
    """Per-run injected-time latency (completed - started) + aggregates (deterministic)."""
    per_run: List[Dict[str, object]] = []
    seconds: List[float] = []
    for run in sorted(runs, key=lambda r: (r.started_at, r.run_id)):
        latency = _seconds_between(run.started_at, run.completed_at)
        if latency is None:
            continue
        per_run.append({"run_id": run.run_id, "latency_seconds": latency})
        seconds.append(latency)
    return {
        "runs_measured": len(seconds),
        "last_latency_seconds": per_run[-1]["latency_seconds"] if per_run else 0,
        "min_latency_seconds": min(seconds) if seconds else 0,
        "max_latency_seconds": max(seconds) if seconds else 0,
        "total_latency_seconds": sum(seconds) if seconds else 0,
        "per_run": per_run,
    }


def _last_pulses(runs, service_health: ServiceHealth, store_dir: str
                 ) -> Tuple[Dict[str, object], Dict[str, object]]:
    """(last_successful_pulse, last_failed_pulse) from the service snapshot + the stores."""
    # Success: prefer the 020C service tick, else the newest persisted run (a completed pulse).
    if service_health.last_successful_run_id:
        last_success = {"run_id": service_health.last_successful_run_id,
                        "at": service_health.last_tick_completed_at}
    elif runs:
        newest = runs[0]
        last_success = {"run_id": newest.run_id, "at": newest.completed_at or newest.started_at}
    else:
        last_success = {"run_id": "", "at": ""}

    # Failure: prefer the 020C service tick, else the newest failed agent-run result.
    if service_health.last_failed_run_id:
        last_failed = {"run_id": service_health.last_failed_run_id,
                       "at": service_health.last_tick_failed_at}
    else:
        last_failed = {"run_id": "", "at": ""}
        from reality_mesh.ledger import AgentRunLedger

        failed_results = [r for r in AgentRunLedger(store_dir).read_all()
                          if r.status == "failed"]
        if failed_results:
            failed_results.sort(key=lambda r: (r.completed_at or r.started_at, r.run_id))
            worst = failed_results[-1]
            last_failed = {"run_id": worst.run_id,
                           "at": worst.completed_at or worst.started_at}
    return last_success, last_failed


def _last_replay_check(store_dir: str, runs, now: str) -> Dict[str, object]:
    """Re-run the 013C deterministic replay over the newest persisted run (injected now)."""
    if not runs:
        return {"available": False, "deterministic_match": False, "run_id": "", "when": ""}
    newest = runs[0]
    try:
        from reality_mesh import (
            EventStore,
            FindingStore,
            ReplayHarness,
            ReplayRequest,
            RunStore,
            SignalStore,
            ThemePulseStore,
        )

        harness = ReplayHarness(
            EventStore(store_dir), FindingStore(store_dir), SignalStore(store_dir),
            ThemePulseStore(store_dir), RunStore(store_dir))
        result = harness.replay(ReplayRequest(run_id=newest.run_id), now=now)
        return {
            "available": True,
            "deterministic_match": bool(result.deterministic_match),
            "run_id": newest.run_id,
            "when": now,
            "differences": len(result.differences),
        }
    except Exception as exc:  # never crash the health surface; surface the fact, sanitized
        return {
            "available": True,
            "deterministic_match": False,
            "run_id": newest.run_id,
            "when": now,
            "error_class": type(exc).__name__,
        }


def _storage_health(store_dir: str) -> Dict[str, object]:
    """The 023D append-only integrity posture (structural + sealed append-only check)."""
    report = integrity_check(store_dir)
    return {
        "ok": bool(report.ok),
        "sealed": bool(report.sealed),
        "append_only_ok": bool(report.append_only_ok),
        "stores": len(report.stores),
        "total_lines": report.total_lines,
        "findings": len(report.corruption_findings),
    }


def _backup_health(store_dir: str) -> Dict[str, object]:
    """The 023D backup-readiness posture: schema compatibility + whether a seal exists."""
    schema = schema_compatibility_check(store_dir)
    integrity = integrity_check(store_dir)
    return {
        "schema_compatible": bool(schema.compatible),
        "supported_schema_versions": list(SUPPORTED_SCHEMA_VERSIONS),
        "seen_schema_versions": list(schema.all_versions),
        "sealed": bool(integrity.sealed),
        "incompatible": list(schema.incompatible),
    }


def _env_presence(env: Mapping[str, object]) -> Dict[str, object]:
    """Config env-var PRESENCE labels only -- ``name in env`` is the ONLY access, never a value."""
    present = {name: (name in env) for name in ALL_CONFIG_ENV_VARS}
    required = tuple(sorted({v for names in REQUIRED_ENV_VARS.values() for v in names}))
    required_present = all(name in env for name in required) if required else True
    return {
        "vars": {name: present[name] for name in sorted(present)},
        "present_count": sum(1 for name in present if present[name]),
        "required_present": bool(required_present),
    }


# --------------------------------------------------------------------------- #
# The aggregation core                                                          #
# --------------------------------------------------------------------------- #
def aggregate_observability(store_dir: str, *, now: str,
                            env: Optional[Mapping[str, object]] = None) -> ObservabilityReport:
    """Aggregate EVERY health signal into ONE frozen, sanitized :class:`ObservabilityReport`.

    READS the persisted stores + operator artifacts under ``store_dir`` and COMPOSES the accepted
    upstream slices (020C service health, 013D source/agent health, 013E DQ, 015 schedule, 020E
    delivery ledger, 013B run timestamps, 013C replay, 023D integrity/schema). ``now`` is the
    INJECTED instant -- the ONLY clock; there is NO wall-clock read here, so two calls over the
    same store + same ``now`` produce a byte-identical report. Reads only; mutates nothing. Every
    string is sanitized on render so no secret VALUE can escape (env vars are PRESENCE labels only).
    """
    if not str(store_dir).strip():
        raise ValueError("aggregate_observability requires a non-empty store_dir")
    generated_at = _format_utc(_parse_utc(now, name="now")) if str(now).strip() else ""
    presence_env = env if env is not None else os.environ

    service, service_dict = _service_health(store_dir)
    agent_summary = _agent_health(store_dir)
    source_summary = _source_health(store_dir, service)
    scheduler = _scheduler_health(store_dir)
    delivery = _alert_delivery_health(store_dir)
    dq_summary, dq_worst = _dq_status_summary(store_dir)
    runs = _runs_newest_first(store_dir)
    latency = _run_latency(runs)
    last_success, last_failed = _last_pulses(runs, service, store_dir)
    replay = _last_replay_check(store_dir, runs, generated_at)
    storage = _storage_health(store_dir)
    backup = _backup_health(store_dir)
    env_presence = _env_presence(presence_env)

    failure_counts = _failure_counts(service, agent_summary, source_summary, dq_summary,
                                     delivery, scheduler, storage)
    status = _roll_status(service, agent_summary, dq_worst, delivery, storage, replay)

    return ObservabilityReport(
        store_dir=str(store_dir),
        generated_at=generated_at,
        status=status,
        service_health=service_dict,
        source_health_summary=source_summary,
        agent_health_summary=agent_summary,
        scheduler_health=scheduler,
        alert_delivery_health=delivery,
        dq_status_summary=dq_summary,
        run_latency=latency,
        failure_counts=failure_counts,
        last_successful_pulse=last_success,
        last_failed_pulse=last_failed,
        last_replay_check=replay,
        storage_health=storage,
        backup_health=backup,
        env_presence=env_presence)


def _failure_counts(service: ServiceHealth, agents: Dict[str, object],
                    sources: Dict[str, object], dq: Dict[str, object],
                    delivery: Dict[str, object], scheduler: Dict[str, object],
                    storage: Dict[str, object]) -> Dict[str, object]:
    """Every failure signal rolled to volume counts (a failure ALWAYS raises the total)."""
    service_failures = int(service.consecutive_failures or 0)
    agents_failed = int(agents.get("failed", 0) or 0)
    source_failures = int(sources.get("source_failure_records", 0) or 0)
    dq_fail_records = int(dq.get("fail_records", 0) or 0)
    delivery_failed = int(delivery.get("failed", 0) or 0)
    scheduler_failures = int(scheduler.get("consecutive_failures", 0) or 0)
    integrity_findings = int(storage.get("findings", 0) or 0)
    total = (service_failures + agents_failed + source_failures + dq_fail_records
             + delivery_failed + scheduler_failures + integrity_findings)
    return {
        "service_consecutive_failures": service_failures,
        "agents_failed": agents_failed,
        "source_failures": source_failures,
        "dq_fail_records": dq_fail_records,
        "delivery_failed": delivery_failed,
        "scheduler_consecutive_failures": scheduler_failures,
        "integrity_findings": integrity_findings,
        "total": total,
    }


def _roll_status(service: ServiceHealth, agents: Dict[str, object], dq_worst: str,
                 delivery: Dict[str, object], storage: Dict[str, object],
                 replay: Dict[str, object]) -> str:
    """Roll every component into ONE ok / degraded / failed verdict (worst wins, honestly)."""
    contributions: List[str] = []

    # Service: a failure with no offsetting success is failed; a failure with a prior success is
    # degraded; a clean snapshot is ok.
    if service.consecutive_failures and not service.last_successful_run_id:
        contributions.append(STATUS_FAILED)
    elif service.consecutive_failures:
        contributions.append(STATUS_DEGRADED)
    else:
        contributions.append(STATUS_OK)

    # Agents: some failed but some succeeded -> degraded; failed with none succeeded -> failed.
    failed = int(agents.get("failed", 0) or 0)
    succeeded = int(agents.get("succeeded", 0) or 0)
    if failed and succeeded:
        contributions.append(STATUS_DEGRADED)
    elif failed:
        contributions.append(STATUS_FAILED)
    else:
        contributions.append(STATUS_OK)

    # Data-quality gate verdict, delivery, storage integrity, replay.
    contributions.append(_RUN_STATUS_TO_HEALTH.get(dq_worst, STATUS_OK))
    contributions.append(STATUS_DEGRADED if int(delivery.get("failed", 0) or 0) else STATUS_OK)
    contributions.append(STATUS_OK if storage.get("ok", True) else STATUS_FAILED)
    if replay.get("available") and not replay.get("deterministic_match", True):
        contributions.append(STATUS_DEGRADED)

    return _worst_status(contributions)


# --------------------------------------------------------------------------- #
# Renderers -- health JSON, metrics file, structured log (all sanitized)         #
# --------------------------------------------------------------------------- #
def render_health_json(report: ObservabilityReport) -> str:
    """The sanitized health JSON (a rolled ``status``: ok / degraded / failed). Deterministic."""
    return json.dumps(report.to_dict(), sort_keys=True, indent=2)


def _metric_flag(value: object) -> int:
    """A boolean-ish health flag as 1 / 0 (metrics are numeric)."""
    return 1 if value else 0


def render_metrics(report: ObservabilityReport) -> str:
    """A stable ``key value`` metrics file: counts + labels + injected-time latencies.

    Deterministic (keys sorted; injected-time latencies; no wall clock) and secret-free (every
    line passes through :func:`~cosmosiq_service.service.sanitize`). NO score / rank / trade
    metric is ever emitted -- volumes, labels, and latencies only.
    """
    svc = report.service_health
    agents = report.agent_health_summary
    sources = report.source_health_summary
    dq = report.dq_status_summary
    delivery = report.alert_delivery_health
    scheduler = report.scheduler_health
    latency = report.run_latency
    failures = report.failure_counts
    storage = report.storage_health
    backup = report.backup_health
    env = report.env_presence
    replay = report.last_replay_check

    metrics: Dict[str, object] = {
        "cosmosiq_observability_status": report.status,
        "cosmosiq_service_mode": str(svc.get("service_mode", "")),
        "cosmosiq_service_consecutive_failures": int(svc.get("consecutive_failures", 0) or 0),
        "cosmosiq_agents_results": int(agents.get("results", 0) or 0),
        "cosmosiq_agents_succeeded": int(agents.get("succeeded", 0) or 0),
        "cosmosiq_agents_failed": int(agents.get("failed", 0) or 0),
        "cosmosiq_agents_blocked": int(agents.get("blocked", 0) or 0),
        "cosmosiq_agents_skipped": int(agents.get("skipped", 0) or 0),
        "cosmosiq_source_coverage_records": int(sources.get("coverage_records", 0) or 0),
        "cosmosiq_source_failure_records": int(sources.get("source_failure_records", 0) or 0),
        "cosmosiq_dq_records": int(dq.get("records", 0) or 0),
        "cosmosiq_dq_fail_records": int(dq.get("fail_records", 0) or 0),
        "cosmosiq_dq_gate_overall_worst": str(dq.get("gate_overall_worst", "")),
        "cosmosiq_delivery_attempts": int(delivery.get("attempts", 0) or 0),
        "cosmosiq_delivery_delivered": int(delivery.get("delivered", 0) or 0),
        "cosmosiq_delivery_failed": int(delivery.get("failed", 0) or 0),
        "cosmosiq_scheduler_policies": int(scheduler.get("policies", 0) or 0),
        "cosmosiq_scheduler_paused_all": _metric_flag(scheduler.get("paused_all")),
        "cosmosiq_scheduler_backoff_policies": int(scheduler.get("backoff_policies", 0) or 0),
        "cosmosiq_run_latency_runs_measured": int(latency.get("runs_measured", 0) or 0),
        "cosmosiq_run_latency_last_seconds": latency.get("last_latency_seconds", 0),
        "cosmosiq_run_latency_min_seconds": latency.get("min_latency_seconds", 0),
        "cosmosiq_run_latency_max_seconds": latency.get("max_latency_seconds", 0),
        "cosmosiq_run_latency_total_seconds": latency.get("total_latency_seconds", 0),
        "cosmosiq_failures_total": int(failures.get("total", 0) or 0),
        "cosmosiq_storage_ok": _metric_flag(storage.get("ok", True)),
        "cosmosiq_storage_total_lines": int(storage.get("total_lines", 0) or 0),
        "cosmosiq_storage_findings": int(storage.get("findings", 0) or 0),
        "cosmosiq_backup_schema_compatible": _metric_flag(backup.get("schema_compatible", True)),
        "cosmosiq_env_present_count": int(env.get("present_count", 0) or 0),
        "cosmosiq_env_required_present": _metric_flag(env.get("required_present", True)),
        "cosmosiq_replay_deterministic_match": _metric_flag(
            replay.get("deterministic_match", False)),
    }
    lines = ["{0} {1}".format(key, metrics[key]) for key in sorted(metrics)]
    return str(sanitize("\n".join(lines)))


def emit_structured_log(event: str, *, now: str, level: str = "info",
                        **fields: object) -> str:
    """ONE sanitized JSON log line (reuses the 020C structured-log shape: ts / level / event).

    ``now`` is the injected instant (the log line's ``ts``) -- no wall clock. Extra ``**fields``
    are merged in; the WHOLE line is passed through :func:`~cosmosiq_service.service.sanitize` so
    no secret VALUE can leak. Returns the single-line JSON string (deterministic, ``sort_keys``).
    """
    if not str(event).strip():
        raise ValueError("emit_structured_log requires a non-empty event name")
    if not str(now).strip():
        raise ValueError("emit_structured_log requires a non-empty injected 'now' instant")
    record: Dict[str, object] = {"ts": str(now), "level": str(level), "event": str(event)}
    for key, value in fields.items():
        record[key] = value
    return json.dumps(sanitize(record), sort_keys=True)
