"""Performance probe for CosmosIQ (Phase 019). OFFLINE, local files only.

Seeds a scratch store with ``scale`` synthetic persisted runs through the NORMAL append
path (``ReplayHarness.persist_pulse`` -- the same writer the live pulse uses), then MEASURES
how long the standing read paths take at that volume:

* every append-only store's ``read_all`` + a ``query`` by run_id;
* the run-history dispatch (``GET /api/runs``) the app serves;
* a deterministic verification replay of one seeded run.

WALL-CLOCK NOTE (sanctioned, ops-only): this module is the ONE place that reads a real wall
clock -- ``time.perf_counter`` -- and it does so ONLY to MEASURE elapsed DURATIONS. A duration
is a measurement, never a score / rank / quality judgement, and it never feeds any runtime
behaviour: the runtime packages (reality_mesh, cosmosiq_app) stay wall-clock-free and every
id / replay path is driven by the injected ``now``. cosmosiq_ops is operator tooling, not
runtime, so the measurement lives here and nowhere else.

Budgets are DATA (:data:`PERF_BUDGETS_SECONDS`) and deliberately generous: the probe answers
"does the read path stay responsive at volume", not "how fast is it".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Tuple

from cosmosiq_app.api import dispatch
from reality_mesh import (
    EventStore,
    FindingStore,
    ReplayHarness,
    ReplayRequest,
    RunStore,
    SignalStore,
    ThemePulseStore,
    run_pulse,
)

# The universe the probe seeds with (same offline fixtures the CI gate / smoke use).
PERF_WATCHLIST = ("IREN", "NVDA")
PERF_THEMES = ("physical_ai", "robotics")

# Budgets AS DATA -- generous by design (elapsed seconds an operator tolerates at scale 50).
PERF_BUDGETS_SECONDS = {
    "seed_runs": 60.0,
    "store_read_all": 5.0,
    "store_query_by_run": 5.0,
    "run_history_dispatch": 5.0,
    "verification_replay": 5.0,
}


@dataclass(frozen=True)
class PerfMeasurement:
    """One MEASURED duration vs its budget. A duration, never a score."""

    name: str
    seconds: float
    budget_seconds: float
    detail: str = ""

    @property
    def within_budget(self) -> bool:
        return self.seconds <= self.budget_seconds


@dataclass(frozen=True)
class PerfReport:
    """Every measured duration at ``scale``. ``within_budget`` is strict (all must pass)."""

    work_dir: str
    scale: int
    measurements: Tuple[PerfMeasurement, ...] = field(default_factory=tuple)

    @property
    def within_budget(self) -> bool:
        return bool(self.measurements) and all(m.within_budget for m in self.measurements)

    @property
    def over_budget(self) -> Tuple[str, ...]:
        return tuple(m.name for m in self.measurements if not m.within_budget)


def _time(fn: Callable[[], object]) -> Tuple[float, object]:
    """Return ``(elapsed_seconds, result)`` -- the ONLY wall-clock read in the package."""
    start = time.perf_counter()
    result = fn()
    return time.perf_counter() - start, result


def _budget(name: str) -> float:
    return float(PERF_BUDGETS_SECONDS.get(name, 5.0))


def run_perf_probe(work_dir: str, *, now: str, scale: int = 50) -> PerfReport:
    """Seed ``scale`` runs then measure the read paths at that volume. OFFLINE.

    ``now`` is injected (every persisted id / timestamp is deterministic); ``time.perf_counter``
    is read ONLY to measure elapsed durations (see the module docstring). Returns a frozen
    :class:`PerfReport` -- measured durations plus a pass/fail against the data-driven budgets.
    """
    if not str(now).strip():
        raise ValueError("run_perf_probe requires an injected 'now' instant")
    if int(scale) < 1:
        raise ValueError("run_perf_probe requires scale >= 1")
    scale = int(scale)

    store_dir = str(work_dir)
    event_store = EventStore(store_dir)
    finding_store = FindingStore(store_dir)
    signal_store = SignalStore(store_dir)
    theme_pulse_store = ThemePulseStore(store_dir)
    run_store = RunStore(store_dir)
    harness = ReplayHarness(event_store, finding_store, signal_store,
                            theme_pulse_store, run_store)

    # -- compute the pulse ONCE (deterministic), then persist it under `scale` distinct run ids
    # through the normal append writer -- append-only, no per-seed replay/gate overhead. ------- #
    pulse = run_pulse(list(PERF_WATCHLIST), list(PERF_THEMES), now=now)
    run_ids = tuple("RUN-PERF-{0:05d}".format(i) for i in range(scale))

    def _seed() -> None:
        for run_id in run_ids:
            harness.persist_pulse(pulse, run_id=run_id, now=now, mode="pulse",
                                  runtime_version="019")

    seed_seconds, _ = _time(_seed)

    # -- read_all across every seeded store ------------------------------------------------- #
    def _read_all() -> int:
        total = 0
        for store in (run_store, event_store, finding_store, signal_store, theme_pulse_store):
            total += len(store.read_all())
        return total

    read_seconds, read_total = _time(_read_all)

    last_run = run_ids[-1]

    def _query() -> int:
        total = 0
        for store in (run_store, event_store, finding_store, signal_store, theme_pulse_store):
            total += len(store.query(run_id=last_run))
        return total

    query_seconds, query_total = _time(_query)

    # -- run-history dispatch (the app's list endpoint over the seeded store) ---------------- #
    def _dispatch_runs() -> dict:
        return dispatch({"method": "GET", "path": "/api/runs", "query": {}, "body": None},
                        store_dir=store_dir, now=now)

    dispatch_seconds, dispatch_resp = _time(_dispatch_runs)

    # -- deterministic verification replay of one seeded run --------------------------------- #
    def _replay():
        return harness.replay(ReplayRequest(run_id=last_run), now=now)

    replay_seconds, replay_result = _time(_replay)

    measurements = (
        PerfMeasurement("seed_runs", seed_seconds, _budget("seed_runs"),
                        "persisted {0} runs via the append-only writer".format(scale)),
        PerfMeasurement("store_read_all", read_seconds, _budget("store_read_all"),
                        "read_all across 5 stores -> {0} records".format(read_total)),
        PerfMeasurement("store_query_by_run", query_seconds, _budget("store_query_by_run"),
                        "query(run_id={0}) across 5 stores -> {1} records".format(
                            last_run, query_total)),
        PerfMeasurement("run_history_dispatch", dispatch_seconds,
                        _budget("run_history_dispatch"),
                        "GET /api/runs -> status {0}".format(
                            dispatch_resp.get("status"))),
        PerfMeasurement("verification_replay", replay_seconds, _budget("verification_replay"),
                        "replay(run_id={0}) deterministic_match={1}".format(
                            last_run, replay_result.deterministic_match)),
    )
    return PerfReport(work_dir=store_dir, scale=scale, measurements=measurements)


def format_perf_report(report: PerfReport) -> str:
    lines = ["CosmosIQ perf probe -- {0}".format(
                 "WITHIN BUDGET" if report.within_budget else "OVER BUDGET"),
             "work dir: {0}".format(report.work_dir),
             "scale: {0} seeded runs".format(report.scale),
             "measured durations (seconds; a measurement, never a score):"]
    for m in report.measurements:
        lines.append("  [{0:^7}] {1}: {2:.4f}s (budget {3:.1f}s) -- {4}".format(
            "ok" if m.within_budget else "OVER", m.name, m.seconds,
            m.budget_seconds, m.detail))
    return "\n".join(lines)
