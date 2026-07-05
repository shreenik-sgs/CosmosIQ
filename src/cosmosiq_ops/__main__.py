"""``python3 -m cosmosiq_ops <command>`` -- the operator command line (Phase 019).

One argparse dispatch over the operator toolkit. Every command prints its report and exits
NON-ZERO on failure so a shell / CI pipeline can gate on it:

    python3 -m cosmosiq_ops ci-gate [--repo-root DIR] [--quick]
    python3 -m cosmosiq_ops prod-check   --work-dir DIR [--repo-root DIR] [--now INSTANT] [--quick]
    python3 -m cosmosiq_ops shadow-validate --work-dir DIR [--ticks N] [--start INSTANT]
                                            [--interval-minutes M] [--operator NAME]
                                            [--report-out PATH]
    python3 -m cosmosiq_ops smoke        --work-dir DIR [--now INSTANT]
    python3 -m cosmosiq_ops perf         --work-dir DIR [--now INSTANT] [--scale N]
    python3 -m cosmosiq_ops backup       --store-dir DIR --backup-dir DIR [--now INSTANT]
    python3 -m cosmosiq_ops verify       --backup-path DIR
    python3 -m cosmosiq_ops restore-check --backup-path DIR --target-dir DIR
    python3 -m cosmosiq_ops env

OFFLINE + honest: this is operator tooling. ``subprocess`` / wall-clock use is confined to
this package (ci-gate runs the suite; perf measures durations); no command touches the network,
prints a secret value, or edits an append-only store line.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from cosmosiq_ops.backup import (
    restore_check,
    snapshot_store,
    verify_snapshot,
)
from cosmosiq_ops.ci_gate import format_ci_gate_report, run_ci_gate
from cosmosiq_ops.env_config import environment_report, format_env_report
from cosmosiq_ops.perf import format_perf_report, run_perf_probe
from cosmosiq_ops.prod_check import format_prod_check_report, run_prod_check
from cosmosiq_ops.smoke import format_smoke_report, run_production_smoke

BANNER = ("CosmosIQ operator toolkit (Phase 019) -- OFFLINE, local files only; env NAMES + "
          "presence labels never values; append-only snapshots, never edits.")

# A default injected instant for the offline commands (deterministic; override with --now).
DEFAULT_NOW = "2026-06-29T00:00:00Z"


def _default_repo_root() -> str:
    # src/cosmosiq_ops/__main__.py -> repo root is three levels up.
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cmd_ci_gate(args: argparse.Namespace) -> int:
    report = run_ci_gate(args.repo_root or _default_repo_root(), quick=bool(args.quick))
    print(format_ci_gate_report(report))
    return 0 if report.passed else 1


def _cmd_prod_check(args: argparse.Namespace) -> int:
    report = run_prod_check(args.work_dir, args.repo_root or _default_repo_root(),
                            now=args.now, quick=bool(args.quick))
    print(format_prod_check_report(report))
    # Non-zero unless production is allowed -- the safe default (an honest OFFLINE run refuses).
    return 0 if report.production_mode_allowed else 1


_SHADOW_START = "2026-06-29T14:30:00Z"
# The default validation universe (IREN / AAOI over the physical-ai theme).
_SHADOW_WATCHLIST = ("IREN", "AAOI")
_SHADOW_THEMES = ("physical_ai",)


def _cmd_shadow_validate(args: argparse.Namespace) -> int:
    from reality_mesh.orchestrator import Subscription
    from reality_mesh.scheduler import DEFAULT_CADENCE_POLICIES
    from cosmosiq_ops.shadow_validation import (
        render_validation_report,
        run_shadow_window,
    )

    print("HONEST BANNER: this is a CONTROLLED shadow-validation window -- {0} scheduled ticks "
          "over an INJECTED-time span (each tick advances the injected 'now' by {1} minutes). It "
          "is NOT a wall-clock 24-72h calendar run. NO live SEC fetch is made: SEC_USER_AGENT is "
          "not configured, so the SEC EDGAR live adapter runs only in its honest "
          "credentials_missing state (a visible source gap). This pass NEVER promotes to "
          "production and NEVER flips the 020F gate.".format(args.ticks, args.interval_minutes))

    store_dir = os.path.join(args.work_dir, "store")
    os.makedirs(store_dir, exist_ok=True)
    subscription = Subscription(
        subscription_id="shadow-validation-universe",
        watchlist=_SHADOW_WATCHLIST, themes=_SHADOW_THEMES,
        policy_ids=tuple(p.policy_id for p in DEFAULT_CADENCE_POLICIES))
    result = run_shadow_window(
        store_dir, subscriptions=(subscription,), ticks=int(args.ticks),
        start=args.start, interval_minutes=int(args.interval_minutes))
    report = render_validation_report(
        result, operator=args.operator, generated_at=args.start)

    if args.report_out:
        parent = os.path.dirname(os.path.abspath(args.report_out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")

    print("CosmosIQ shadow-validation window (Phase 020G) -- COMPLETE")
    print("  duration: {0}".format(result.duration_label))
    print("  ticks scheduled/succeeded/failed: {0}/{1}/{2}".format(
        result.ticks_scheduled, result.ticks_succeeded, result.ticks_failed))
    print("  distinct pulses persisted: {0}".format(len(result.persisted_run_ids)))
    print("  SEC EDGAR live source health: {0} (configured={1})".format(
        result.sec_source_health.get("source_health", "credentials_missing"),
        str(result.sec_edgar_configured).lower()))
    print("  agent health: {0}".format(result.agent_health))
    print("  DQ gate ran every pulse: {0}; failing DQ records: {1}".format(
        str(result.dq_gate_ran_every_pulse).lower(), len(result.dq_failures)))
    print("  candidate attempts: {0}; forged-eligible: {1}; blocked verdicts: {2}".format(
        result.candidate_attempts, len(result.forged_eligible),
        ", ".join(result.blocked_candidate_reasons) or "none"))
    print("  shadow alerts: {0}; external delivery: {1}; production escalation: {2}".format(
        len(result.shadow_alerts), str(result.external_delivery_occurred).lower(),
        str(result.production_escalation_occurred).lower()))
    print("  replay divergences (must be 0): {0}".format(result.replay_divergences))
    print("  promotion recommendation: {0}".format(result.promotion_recommendation))
    if args.report_out:
        print("  report written: {0}".format(args.report_out))
    print("  live_source_health verified: {0} (stays manual -- no live SEC fetch)".format(
        str(result.live_source_health_verified).lower()))
    return 0


# The default end-to-end trial universe = the 020G shadow config set (watchlist + themes).
_E2E_WATCHLIST = ("IREN", "AAOI", "INOD")
_E2E_THEMES = ("ai-infrastructure", "power-and-grid", "optical-networking",
               "physical-ai", "space-and-defense")
_E2E_NOW = "2026-06-29T14:30:00Z"


def _cmd_e2e_trace(args: argparse.Namespace) -> int:
    from cosmosiq_ops.e2e_trace import render_e2e_trace_report, run_e2e_trial

    print("HONEST BANNER: this runs the WHOLE CosmosIQ intelligence chain ONCE end to end over "
          "LOCAL research fixtures and reports whatever HONESTLY occurs -- an eligible candidate "
          "with full provenance, a blocked candidate with its exact reason, or no candidate. NO "
          "live SEC fetch is made (SEC_USER_AGENT unconfigured -> visible source gap). Nothing is "
          "forced; no candidate is fabricated; shadow-only, no external delivery.")

    store_dir = os.path.join(args.work_dir, "store")
    os.makedirs(store_dir, exist_ok=True)
    result = run_e2e_trial(
        store_dir, watchlist=_E2E_WATCHLIST, themes=_E2E_THEMES, now=args.now)
    report = render_e2e_trace_report(result, generated_at=args.now)

    if args.report_out:
        parent = os.path.dirname(os.path.abspath(args.report_out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")

    print("CosmosIQ end-to-end evidence-to-candidate trial (Phase 020H) -- COMPLETE")
    print("  run id (persisted): {0}".format(result.run_id))
    print("  focus ticker (strongest evidence): {0}".format(result.focus_ticker or "none"))
    print("  events/findings/signals/clusters: {0}/{1}/{2}/{3}".format(
        result.events_persisted, result.findings_persisted, len(result.signals),
        result.clusters_persisted))
    print("  theme pulses: {0}".format(
        ", ".join("{0}={1}".format(t.theme_id, t.state) for t in result.theme_pulses) or "none"))
    print("  data-insufficient themes: {0}".format(
        ", ".join(result.themes_data_insufficient) or "none"))
    print("  SEC EDGAR live source health: {0} (configured={1})".format(
        result.sec_source_health.get("source_health", "credentials_missing"),
        str(result.sec_configured).lower()))
    print("  Trust/Data-Quality gate_overall: {0}".format(result.dq_overall or "unstated"))
    print("  candidate outcome (HONEST, not forced): {0}".format(result.candidate_outcome))
    print("    {0}".format(result.candidate_outcome_reason))
    print("  eligible/blocked/forged-eligible: {0}/{1}/{2}".format(
        result.eligible_count, result.blocked_count, len(result.forged_eligible)))
    print("  shadow alerts: {0} (baseline={1}); external delivery: {2}; escalation: {3}".format(
        len(result.shadow_alerts), str(result.alerts_baseline).lower(),
        str(result.external_delivery_occurred).lower(),
        str(result.production_escalation_occurred).lower()))
    print("  replay deterministic_match: {0}".format(
        str(result.replay_deterministic_match).lower()))
    print("  UI routes verified (all 200): {0}".format(
        str(all(u.status == 200 for u in result.ui_routes)).lower()))
    if args.report_out:
        print("  report written: {0}".format(args.report_out))
    print("  view it in the local operator app:")
    print("    {0}".format(result.app_command))
    return 0


def _cmd_activate(args: argparse.Namespace) -> int:
    from cosmosiq_ops.activate import (
        DEFAULT_SIGNOFF_REL,
        format_activation_report,
        run_activation,
    )
    repo_root = args.repo_root or _default_repo_root()
    signoff = args.signoff or os.path.join(repo_root, DEFAULT_SIGNOFF_REL)
    outcome = run_activation(args.work_dir, now=args.now, signoff_path=signoff,
                             repo_root=repo_root, quick=bool(args.quick))
    print(format_activation_report(outcome))
    # Non-zero unless production was actually activated -- the safe default (today: REFUSED).
    return 0 if outcome.activated else 1


def _cmd_rollback(args: argparse.Namespace) -> int:
    from cosmosiq_ops.activate import format_rollback_report, run_rollback
    outcome = run_rollback(args.work_dir, to=args.to, now=args.now, trigger=args.trigger)
    print(format_rollback_report(outcome))
    return 0 if outcome.allowed else 1


def _cmd_smoke(args: argparse.Namespace) -> int:
    report = run_production_smoke(args.work_dir, now=args.now)
    print(format_smoke_report(report))
    return 0 if report.passed else 1


def _cmd_perf(args: argparse.Namespace) -> int:
    report = run_perf_probe(args.work_dir, now=args.now, scale=args.scale)
    print(format_perf_report(report))
    return 0 if report.within_budget else 1


def _cmd_backup(args: argparse.Namespace) -> int:
    snapshot = snapshot_store(args.store_dir, args.backup_dir, now=args.now)
    verify = verify_snapshot(snapshot.snapshot_path)
    print("CosmosIQ backup snapshot -- {0}".format("VERIFIED" if verify.ok else "CORRUPT"))
    print("snapshot: {0}".format(snapshot.snapshot_path))
    print("captured: {0} files / {1} jsonl lines".format(
        snapshot.total_files, snapshot.total_jsonl_lines))
    for record in snapshot.files:
        print("  {0}  sha256={1}  lines={2}".format(
            record.path, record.sha256[:12], record.line_count))
    if not verify.ok:
        for issue in verify.mismatched + verify.missing + verify.extra:
            print("  ! " + issue)
    return 0 if verify.ok else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    verify = verify_snapshot(args.backup_path)
    print("CosmosIQ backup verify -- {0}".format("OK" if verify.ok else "FAIL"))
    print("backup: {0}".format(verify.backup_path))
    print("files checked: {0}".format(verify.files_checked))
    for issue in verify.mismatched + verify.missing + verify.extra:
        print("  ! " + issue)
    if verify.ok:
        print("  every file matches the manifest (sha256 + line counts)")
    return 0 if verify.ok else 1


def _cmd_restore_check(args: argparse.Namespace) -> int:
    check = restore_check(args.backup_path, args.target_dir)
    print("CosmosIQ restore check (DRY RUN -- nothing written) -- {0}".format(
        "ALLOWED" if check.allowed else "REFUSED"))
    print("backup: {0}".format(check.backup_path))
    print("target: {0} (state: {1})".format(check.target_dir, check.target_state))
    if not check.allowed:
        print("  refusal: {0}".format(check.refusal_reason))
    for rel, action in check.entries:
        print("  {0}: {1}".format(rel, action))
    return 0 if check.allowed else 1


def _cmd_env(_args: argparse.Namespace) -> int:
    print(format_env_report(environment_report()))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cosmosiq_ops", description=BANNER)
    sub = parser.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("ci-gate", help="run every guardrail sweep + the offline suite")
    gate.add_argument("--repo-root", default=None,
                      help="repo root to sweep (default: this checkout)")
    gate.add_argument("--quick", action="store_true",
                      help="skip the full-suite subprocess run; keep every sweep")
    gate.set_defaults(func=_cmd_ci_gate)

    prod = sub.add_parser(
        "prod-check",
        help="the Phase-020F production activation gate (OFFLINE; refuses production by default)")
    prod.add_argument("--work-dir", required=True, help="fresh scratch work dir")
    prod.add_argument("--repo-root", default=None,
                      help="repo root to sweep (default: this checkout)")
    prod.add_argument("--now", default=DEFAULT_NOW, help="injected instant (deterministic)")
    prod.add_argument("--quick", action="store_true",
                      help="skip the CI-gate full-suite subprocess run; keep every sweep")
    prod.set_defaults(func=_cmd_prod_check)

    shadow = sub.add_parser(
        "shadow-validate",
        help="run a CONTROLLED SHADOW_24X7 validation window (injected-time; not a wall-clock "
             "multi-day run) + fill the 020D report")
    shadow.add_argument("--work-dir", required=True, help="fresh scratch work dir")
    shadow.add_argument("--ticks", type=int, default=24,
                        help="number of scheduled ticks in the window (default 24)")
    shadow.add_argument("--start", default=_SHADOW_START,
                        help="injected first-tick instant (deterministic)")
    shadow.add_argument("--interval-minutes", type=int, default=60,
                        help="injected minutes between ticks (default 60)")
    shadow.add_argument("--operator", default="operator",
                        help="operator name recorded in the report")
    shadow.add_argument("--report-out", default=None,
                        help="path to write the filled 020D shadow-validation report")
    shadow.set_defaults(func=_cmd_shadow_validate)

    e2e = sub.add_parser(
        "e2e-trace",
        help="run the WHOLE evidence-to-candidate chain once end to end + fill the 020H trace "
             "report (honest outcome; no candidate forced)")
    e2e.add_argument("--work-dir", required=True, help="fresh scratch work dir")
    e2e.add_argument("--now", default=_E2E_NOW, help="injected instant (deterministic)")
    e2e.add_argument("--report-out", default=None,
                     help="path to write the filled 020H end-to-end trace report")
    e2e.set_defaults(func=_cmd_e2e_trace)

    activate = sub.add_parser(
        "activate",
        help="the Phase-021C production activation FLOW: read a filled operator sign-off, run "
             "prod-check, and flip to PRODUCTION_24X7 ONLY IF the evidence is complete (refuses "
             "by default)")
    activate.add_argument("--work-dir", required=True, help="the operator store work dir")
    activate.add_argument("--repo-root", default=None,
                          help="repo root to sweep (default: this checkout)")
    activate.add_argument(
        "--signoff", default=None,
        help="path to the filled operator sign-off (default: reports/OPERATOR_SIGNOFF_020J.md)")
    activate.add_argument("--now", default=DEFAULT_NOW, help="injected instant (deterministic)")
    activate.add_argument("--quick", action="store_true",
                          help="skip the CI-gate full-suite subprocess run; keep every sweep")
    activate.set_defaults(func=_cmd_activate)

    rollback = sub.add_parser(
        "rollback",
        help="step the sanctioned mode DOWN the ladder "
             "(PRODUCTION_24X7 -> SHADOW_24X7 -> MANUAL -> OFF); refuses an upgrade")
    rollback.add_argument("--work-dir", required=True, help="the operator store work dir")
    rollback.add_argument("--to", required=True,
                          choices=["SHADOW_24X7", "MANUAL", "OFF", "shadow_24x7", "manual", "off"],
                          help="the safer mode to roll back to")
    rollback.add_argument("--trigger", default=None,
                          help="the named rollback trigger (default: operator_manual)")
    rollback.add_argument("--now", default=DEFAULT_NOW, help="injected instant (deterministic)")
    rollback.set_defaults(func=_cmd_rollback)

    smoke = sub.add_parser("smoke", help="run the full operator chain offline")
    smoke.add_argument("--work-dir", required=True, help="fresh scratch work dir")
    smoke.add_argument("--now", default=DEFAULT_NOW, help="injected instant (deterministic)")
    smoke.set_defaults(func=_cmd_smoke)

    perf = sub.add_parser("perf", help="seed N runs and measure the read paths")
    perf.add_argument("--work-dir", required=True, help="fresh scratch work dir")
    perf.add_argument("--now", default=DEFAULT_NOW, help="injected instant (deterministic)")
    perf.add_argument("--scale", type=int, default=50, help="synthetic runs to seed")
    perf.set_defaults(func=_cmd_perf)

    backup = sub.add_parser("backup", help="snapshot a store + verify the roundtrip")
    backup.add_argument("--store-dir", required=True, help="the store to snapshot")
    backup.add_argument("--backup-dir", required=True, help="where the snapshot is written")
    backup.add_argument("--now", default=DEFAULT_NOW, help="injected instant (deterministic)")
    backup.set_defaults(func=_cmd_backup)

    verify = sub.add_parser("verify", help="verify a snapshot against its manifest")
    verify.add_argument("--backup-path", required=True, help="the snapshot directory")
    verify.set_defaults(func=_cmd_verify)

    restore = sub.add_parser("restore-check",
                             help="dry-run a restore (never writes; refuses non-empty target)")
    restore.add_argument("--backup-path", required=True, help="the snapshot directory")
    restore.add_argument("--target-dir", required=True, help="the restore target")
    restore.set_defaults(func=_cmd_restore_check)

    env = sub.add_parser("env", help="env var presence labels + secrets policy (no values)")
    env.set_defaults(func=_cmd_env)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    print(BANNER)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
