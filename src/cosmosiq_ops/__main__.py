"""``python3 -m cosmosiq_ops <command>`` -- the operator command line (Phase 019).

One argparse dispatch over the operator toolkit. Every command prints its report and exits
NON-ZERO on failure so a shell / CI pipeline can gate on it:

    python3 -m cosmosiq_ops ci-gate [--repo-root DIR] [--quick]
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
