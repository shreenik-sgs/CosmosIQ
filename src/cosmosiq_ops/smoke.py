"""Production smoke test for CosmosIQ (Phase 019). OFFLINE, local files only.

``run_production_smoke`` walks the WHOLE operator chain end-to-end against a fresh scratch
work dir, entirely offline, and reports each step pass/fail with a plain-English reason:

1. run a pulse and PERSIST it (append-only stores under the work dir);
2. the persisted run REPLAYS deterministically (``deterministic_match`` True);
3. the production gates raise NO hard fail (no gate ``fail``; overall not ``failed`` /
   ``blocked_by_policy``);
4. the app dispatcher renders ``/`` , ``/runs`` , ``/portfolio`` (honest absence, not a crash)
   and ``/themes`` -- each a 200 HTML page;
5. the alert inbox is QUIET on the first run (baseline, zero alerts -- never a flood);
6. a backup SNAPSHOT of the store verifies clean (sha256 + line-count roundtrip).

Deterministic + offline: ``now`` is injected everywhere; no wall clock, no network, no
subprocess. Overall pass iff every step passed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Tuple

from cosmosiq_app.api import dispatch
from cosmosiq_ops.backup import snapshot_store, verify_snapshot
from reality_mesh import (
    DataQualityStore,
    generate_alerts_for_run,
    persist_and_summarize,
    run_pulse,
)

SMOKE_WATCHLIST = ("IREN", "NVDA")
SMOKE_THEMES = ("physical_ai", "robotics")
SMOKE_RUN_ID = "RUN-SMOKE-001"

# A store-level status worse than this fails the gate step (a "hard fail").
HARD_FAIL_RUN_STATUSES = frozenset({"failed", "blocked_by_policy"})

# The pages the smoke chain renders; each must answer 200 text/html.
SMOKE_PAGES = ("/", "/runs", "/portfolio", "/themes")


@dataclass(frozen=True)
class SmokeStep:
    """One step of the chain: a name, a boolean outcome, and a plain reason."""

    name: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class SmokeReport:
    """The whole chain. ``passed`` is strict: any failing step fails the smoke."""

    work_dir: str
    steps: Tuple[SmokeStep, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return bool(self.steps) and all(step.passed for step in self.steps)

    @property
    def failed_steps(self) -> Tuple[str, ...]:
        return tuple(step.name for step in self.steps if not step.passed)


def _render_page(store_dir: str, path: str, now: str) -> SmokeStep:
    response = dispatch({"method": "GET", "path": path, "query": {}, "body": None},
                        store_dir=store_dir, now=now)
    status = response.get("status")
    headers = response.get("headers") or {}
    content_type = str(headers.get("Content-Type", headers.get("content-type", "")))
    body = str(response.get("body") or "")
    is_html = "html" in content_type.lower() or body.lstrip().lower().startswith("<!doctype")
    ok = status == 200 and is_html and bool(body.strip())
    reason = ("{0} -> 200 HTML ({1} bytes)".format(path, len(body)) if ok
              else "{0} -> status {1}, html={2}".format(path, status, is_html))
    return SmokeStep("page " + path, ok, reason)


def run_production_smoke(work_dir: str, *, now: str) -> SmokeReport:
    """Run the full operator chain OFFLINE against ``work_dir``; return the frozen report.

    ``now`` is injected everywhere -- no wall clock is read here (this is the runtime chain,
    not the perf probe). ``work_dir`` should be fresh; the chain seeds it and never touches the
    network. Overall pass iff every step passed.
    """
    if not str(now).strip():
        raise ValueError("run_production_smoke requires an injected 'now' instant")

    store_dir = os.path.join(str(work_dir), "store")
    backup_dir = os.path.join(str(work_dir), "backups")
    os.makedirs(store_dir, exist_ok=True)
    steps = []

    # 1 + 2. pulse -> persist -> deterministic replay. --------------------------------------- #
    pulse = run_pulse(list(SMOKE_WATCHLIST), list(SMOKE_THEMES), now=now)
    _run, replay_result, _panels = persist_and_summarize(
        pulse, store_dir=store_dir, run_id=SMOKE_RUN_ID, now=now)
    steps.append(SmokeStep(
        "pulse_persisted",
        pulse is not None and _run is not None,
        "persisted {0}: {1} findings, {2} signals, {3} theme pulses".format(
            SMOKE_RUN_ID, len(pulse.findings), len(pulse.signals),
            len(pulse.theme_pulses))))
    steps.append(SmokeStep(
        "replay_deterministic",
        replay_result.deterministic_match,
        "replay deterministic_match={0}{1}".format(
            replay_result.deterministic_match,
            "" if replay_result.deterministic_match
            else " -- differences: " + "; ".join(replay_result.differences))))

    # 3. gates raise no hard fail (read the persisted gate verdicts, never re-judge). --------- #
    dq_records = DataQualityStore(store_dir).query(run_id=SMOKE_RUN_ID)
    failed_gates = tuple(r.category for r in dq_records
                         if r.category != "gate_overall" and r.status == "fail")
    overall = next((r.status for r in dq_records if r.category == "gate_overall"), "healthy")
    gates_ok = not failed_gates and overall not in HARD_FAIL_RUN_STATUSES
    steps.append(SmokeStep(
        "gates_no_hard_fail",
        gates_ok,
        "overall gate status {0!r}; {1}".format(
            overall,
            "no gate failed" if not failed_gates
            else "failed gates: " + ", ".join(failed_gates))))

    # 4. the app renders each page as 200 HTML (portfolio shows honest absence). -------------- #
    for path in SMOKE_PAGES:
        steps.append(_render_page(store_dir, path, now))

    # 5. the alert inbox is quiet on the first run (baseline, zero alerts). ------------------- #
    alerts = generate_alerts_for_run(store_dir, SMOKE_RUN_ID, now=now)
    quiet = alerts.baseline and not alerts.alerts
    steps.append(SmokeStep(
        "alert_inbox_quiet_first_run",
        quiet,
        "first run baseline={0}, {1} alert(s)".format(alerts.baseline, len(alerts.alerts))))

    # 6. snapshot the store + verify the roundtrip (sha256 + line counts). -------------------- #
    snapshot = snapshot_store(store_dir, backup_dir, now=now)
    verify = verify_snapshot(snapshot.snapshot_path)
    steps.append(SmokeStep(
        "backup_snapshot_verifies",
        verify.ok,
        "snapshot captured {0} files / {1} jsonl lines; verify ok={2}{3}".format(
            snapshot.total_files, snapshot.total_jsonl_lines, verify.ok,
            "" if verify.ok else " -- " + "; ".join(
                verify.mismatched + verify.missing + verify.extra))))

    return SmokeReport(work_dir=str(work_dir), steps=tuple(steps))


def format_smoke_report(report: SmokeReport) -> str:
    lines = ["CosmosIQ production smoke -- {0}".format(
                 "PASS" if report.passed else "FAIL"),
             "work dir: {0}".format(report.work_dir)]
    for step in report.steps:
        lines.append("  [{0:^4}] {1}: {2}".format(
            "ok" if step.passed else "FAIL", step.name, step.reason))
    return "\n".join(lines)
