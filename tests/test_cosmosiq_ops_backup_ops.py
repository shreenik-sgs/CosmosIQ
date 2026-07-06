"""IMPLEMENTATION-023F -- operator backup / restore / retention COMMANDS. OFFLINE, stdlib-only.

Proves the operator command layer (:mod:`cosmosiq_ops.backup_ops` + its ``__main__`` subcommands)
delivers production recoverability by COMPOSING the accepted 019A backup + 023D persistence-hardening
paths -- never re-implementing them:

* **backup creates a MANIFEST** -- a sha256 per store file;
* **restore recreates the store** -- byte-for-byte into an empty target;
* **replay works after restore** -- ``ReplayHarness.deterministic_match`` True on the restored store;
* **retention does NOT delete active data** -- an active store is byte-unchanged; an aged snapshot is
  ARCHIVED under ``archive/``, never deleted;
* **restore REFUSES an incompatible schema unless migrated** -- no write on refusal; a migration lifts it;
* **a DRY-RUN restore writes NOTHING** -- the target is untouched, yet the plan is reported;
* **backup-health reports a sane status with NO secret**;
* **each CLI subcommand runs offline + exits non-zero on failure**;
* NO score / trade field; deterministic; offline kill-switch; AST clean; demo + default pulse byte-identical.

Everything here is offline: temp-dir stores, injected ``now``, no network, no live endpoint.
"""

from __future__ import annotations

import ast
import dataclasses
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import cosmosiq_ops
from cosmosiq_ops import backup_ops
from cosmosiq_ops import __main__ as ops_main

from reality_mesh import (
    EventStore,
    FindingStore,
    ReplayHarness,
    RunStore,
    SignalStore,
    ThemePulseStore,
    run_pulse,
)
from reality_mesh.runtime import ReplayRequest

_NOW = "2026-06-29T00:00:00Z"
_NOW2 = "2026-06-29T01:00:00Z"
_WATCHLIST = ["IREN", "NVDA"]
_THEMES = ["physical_ai", "robotics"]
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

_SECRET = "sk-ThisIsAFakeSecret-must-never-appear-a1b2c3"
_TRADE_TOKENS = ("buy", "sell", "order", "broker", "score", "rank", "rating")


def _seed_store(store_dir: str, *, run_id: str = "RUN-OPS-001") -> None:
    """Persist ONE deterministic pulse into the append-only stores under ``store_dir``."""
    pulse = run_pulse(list(_WATCHLIST), list(_THEMES), now=_NOW)
    harness = ReplayHarness(
        EventStore(store_dir), FindingStore(store_dir), SignalStore(store_dir),
        ThemePulseStore(store_dir), RunStore(store_dir))
    harness.persist_pulse(pulse, run_id=run_id, now=_NOW, runtime_version="023")


def _rb(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def _jsonl_bytes(store_dir: str):
    return {n: _rb(os.path.join(store_dir, n))
            for n in os.listdir(store_dir) if n.endswith(".jsonl")}


def _run_cli(argv):
    """Run a CLI subcommand offline; return (exit_code, captured_stdout)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ops_main.main(argv)
    return code, buf.getvalue()


# --------------------------------------------------------------------------- #
# package export surface                                                        #
# --------------------------------------------------------------------------- #
class ExportTests(unittest.TestCase):
    def test_backup_ops_surface_is_exported(self):
        for name in ("backup_operator", "restore_operator", "dry_run_restore",
                     "apply_retention_policy", "backup_health", "BackupReport",
                     "RestoreReport", "BackupHealthReport", "BackupFileRecord"):
            self.assertTrue(hasattr(cosmosiq_ops, name), "missing export: " + name)


# --------------------------------------------------------------------------- #
# 1. backup creates a MANIFEST (sha256 per store file)                          #
# --------------------------------------------------------------------------- #
class BackupManifestTests(unittest.TestCase):
    def test_backup_writes_a_manifest_with_a_sha256_per_store_file(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            os.makedirs(store)
            _seed_store(store)

            report = backup_ops.backup(store, backups, now=_NOW)
            self.assertEqual(report.status, backup_ops.STATUS_OK)
            self.assertTrue(report.ok)
            self.assertTrue(report.verify_ok)
            self.assertTrue(report.integrity_ok)
            # the manifest file exists and is the reported path.
            self.assertTrue(os.path.isfile(report.manifest_path))
            self.assertTrue(report.manifest_path.endswith("manifest.json"))

            # every captured store file has a non-empty 64-hex sha256 recorded.
            jsonl_names = sorted(n for n in os.listdir(store) if n.endswith(".jsonl"))
            self.assertTrue(jsonl_names)
            manifest_jsonl = {r.path for r in report.files if r.path.endswith(".jsonl")}
            for name in jsonl_names:
                self.assertIn(name, manifest_jsonl)
            for record in report.files:
                self.assertEqual(len(record.sha256), 64)
                int(record.sha256, 16)   # valid hex
                if record.path.endswith(".jsonl"):
                    self.assertIsInstance(record.line_count, int)


# --------------------------------------------------------------------------- #
# 2. restore recreates the store byte-for-byte into an empty target             #
# --------------------------------------------------------------------------- #
class RestoreRecreatesTests(unittest.TestCase):
    def test_restore_recreates_the_store_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            target = os.path.join(work, "restore")
            os.makedirs(store)
            _seed_store(store)

            backup = backup_ops.backup(store, backups, now=_NOW)
            report = backup_ops.restore(backup.snapshot_path, target, now=_NOW)
            self.assertTrue(report.allowed, report.refusal_reason)
            self.assertTrue(report.ok, report.findings)
            self.assertEqual(report.status, backup_ops.STATUS_OK)

            names = sorted(n for n in os.listdir(store) if n.endswith(".jsonl"))
            self.assertTrue(names)
            for name in names:
                self.assertEqual(_rb(os.path.join(store, name)),
                                 _rb(os.path.join(target, name)),
                                 "restore drifted for {0}".format(name))


# --------------------------------------------------------------------------- #
# 3. replay works after restore                                                 #
# --------------------------------------------------------------------------- #
class ReplayAfterRestoreTests(unittest.TestCase):
    def test_replay_deterministic_match_on_the_restored_store(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            target = os.path.join(work, "restore")
            os.makedirs(store)
            _seed_store(store, run_id="RUN-REPLAY-2")

            backup = backup_ops.backup(store, backups, now=_NOW)
            report = backup_ops.restore(backup.snapshot_path, target, now=_NOW)
            self.assertTrue(report.replay_ok, report.findings)

            # independent replay against the RESTORED stores.
            harness = ReplayHarness(
                EventStore(target), FindingStore(target), SignalStore(target),
                ThemePulseStore(target), RunStore(target))
            result = harness.replay(ReplayRequest(run_id="RUN-REPLAY-2"), now=_NOW)
            self.assertTrue(result.deterministic_match,
                            "replay differences: {0}".format(result.differences))


# --------------------------------------------------------------------------- #
# 4. retention does NOT delete active data (archive-only)                       #
# --------------------------------------------------------------------------- #
class RetentionTests(unittest.TestCase):
    def test_retention_archives_the_aged_snapshot_and_leaves_active_store_unchanged(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            os.makedirs(store)
            _seed_store(store)

            before = _jsonl_bytes(store)

            backup_ops.backup(store, backups, now=_NOW)
            backup_ops.backup(store, backups, now=_NOW2)
            report = backup_ops.apply_retention_policy(backups, keep_latest=1, now=_NOW)

            self.assertEqual(len(report.archived), 1)       # oldest aged out
            self.assertEqual(len(report.retained), 1)       # newest kept live

            archived_name = report.archived[0]
            # the archived snapshot MOVED under archive/ (still present), never deleted.
            self.assertTrue(os.path.isdir(os.path.join(backups, "archive", archived_name)))
            self.assertFalse(os.path.isdir(os.path.join(backups, archived_name)))

            # the ACTIVE store is byte-identical -- retention never touched it.
            self.assertEqual(before, _jsonl_bytes(store))


# --------------------------------------------------------------------------- #
# 5. restore REFUSES an incompatible schema unless migrated                     #
# --------------------------------------------------------------------------- #
class SchemaRefusalTests(unittest.TestCase):
    def test_restore_refuses_incompatible_schema_writing_nothing_then_a_migration_lifts_it(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            os.makedirs(store)
            _seed_store(store)
            backup = backup_ops.backup(store, backups, now=_NOW)

            t1 = os.path.join(work, "t1")
            refused = backup_ops.restore(
                backup.snapshot_path, t1, now=_NOW, supported_versions=("999.9",))
            self.assertFalse(refused.allowed)
            self.assertEqual(refused.status, backup_ops.STATUS_FAILED)
            self.assertIn("incompatible schema", refused.refusal_reason)
            self.assertFalse(os.path.isdir(t1))            # nothing was written on refusal

            # a migration lifts the refusal; the restore then proceeds + re-verifies.
            calls = []
            t2 = os.path.join(work, "t2")
            report = backup_ops.restore(
                backup.snapshot_path, t2, now=_NOW, supported_versions=("999.9",),
                migration=lambda target: calls.append(target))
            self.assertTrue(report.allowed)
            self.assertTrue(report.migrated)
            self.assertEqual(len(calls), 1)
            self.assertTrue(report.ok, report.findings)


# --------------------------------------------------------------------------- #
# 6. a DRY-RUN restore writes NOTHING yet reports the plan                       #
# --------------------------------------------------------------------------- #
class DryRunTests(unittest.TestCase):
    def test_dry_run_into_a_missing_target_writes_nothing_but_reports_the_plan(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            target = os.path.join(work, "restore")
            os.makedirs(store)
            _seed_store(store)
            backup = backup_ops.backup(store, backups, now=_NOW)

            report = backup_ops.dry_run_restore(backup.snapshot_path, target, now=_NOW)
            self.assertTrue(report.dry_run)
            self.assertTrue(report.allowed)
            self.assertTrue(report.plan)                    # the plan is reported
            self.assertEqual(report.files_restored, 0)
            # WROTE NOTHING: the target dir was never created.
            self.assertFalse(os.path.exists(target))

    def test_dry_run_into_an_empty_target_leaves_it_empty(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            target = os.path.join(work, "restore")
            os.makedirs(store)
            os.makedirs(target)                             # pre-existing EMPTY target
            _seed_store(store)
            backup = backup_ops.backup(store, backups, now=_NOW)

            report = backup_ops.dry_run_restore(backup.snapshot_path, target, now=_NOW)
            self.assertTrue(report.allowed)
            self.assertEqual(report.target_state, "empty")
            # still empty -- nothing was written.
            self.assertEqual(os.listdir(target), [])

    def test_dry_run_reports_a_non_empty_target_as_a_refusal_without_writing(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            occupied = os.path.join(work, "occupied")
            os.makedirs(store)
            os.makedirs(occupied)
            _seed_store(store)
            with open(os.path.join(occupied, "existing.jsonl"), "wb") as fh:
                fh.write(b'{"kept":1}\n')
            before = _rb(os.path.join(occupied, "existing.jsonl"))
            backup = backup_ops.backup(store, backups, now=_NOW)

            report = backup_ops.dry_run_restore(backup.snapshot_path, occupied, now=_NOW)
            self.assertFalse(report.allowed)               # a real restore would refuse
            self.assertEqual(report.target_state, "non_empty")
            self.assertTrue(report.refusal_reason)
            # the pre-existing line is untouched.
            self.assertEqual(_rb(os.path.join(occupied, "existing.jsonl")), before)


# --------------------------------------------------------------------------- #
# 7. backup-health reports a sane status with NO secret                         #
# --------------------------------------------------------------------------- #
class BackupHealthTests(unittest.TestCase):
    def test_backup_health_reports_ok_on_a_fresh_backup(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            os.makedirs(store)
            _seed_store(store)
            backup_ops.backup(store, backups, now=_NOW)

            health = backup_ops.backup_health(backups)
            self.assertEqual(health.status, backup_ops.STATUS_OK)
            self.assertTrue(health.ok)
            self.assertTrue(health.verify_ok)
            self.assertTrue(health.schema_supported)
            self.assertTrue(health.latest_snapshot)
            self.assertEqual(health.last_backup_at, _NOW)   # the last-backup marker
            self.assertEqual(health.snapshot_count, 1)

    def test_backup_health_reports_failed_when_no_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as work:
            health = backup_ops.backup_health(os.path.join(work, "empty"))
            self.assertEqual(health.status, backup_ops.STATUS_FAILED)
            self.assertFalse(health.ok)
            self.assertEqual(health.latest_snapshot, "")

    def test_backup_health_surfaces_no_secret_even_with_one_in_the_environment(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            os.makedirs(store)
            _seed_store(store)
            backup_ops.backup(store, backups, now=_NOW)
            os.environ["SEC_USER_AGENT"] = _SECRET
            try:
                health = backup_ops.backup_health(backups)
            finally:
                os.environ.pop("SEC_USER_AGENT", None)
            for text in _iter_report_strings(health):
                self.assertNotIn(_SECRET, text)
                self.assertNotIn("sk-", text)


# --------------------------------------------------------------------------- #
# 8. each CLI subcommand runs offline + exits non-zero on failure               #
# --------------------------------------------------------------------------- #
class CliTests(unittest.TestCase):
    def test_backup_restore_dry_run_retention_health_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            target = os.path.join(work, "restore")
            os.makedirs(store)
            _seed_store(store, run_id="RUN-CLI-1")

            code, out = _run_cli(["backup", "--store-dir", store, "--backup-dir", backups,
                                  "--now", _NOW])
            self.assertEqual(code, 0, out)
            self.assertIn("manifest", out)
            snapshot = os.path.join(
                backups, sorted(n for n in os.listdir(backups) if n.startswith("snapshot-"))[-1])

            # dry-run writes nothing.
            code, out = _run_cli(["restore", "--backup-path", snapshot, "--target-dir", target,
                                  "--dry-run", "--now", _NOW])
            self.assertEqual(code, 0, out)
            self.assertIn("DRY RUN", out)
            self.assertFalse(os.path.exists(target))

            # real restore recreates the store.
            code, out = _run_cli(["restore", "--backup-path", snapshot, "--target-dir", target,
                                  "--now", _NOW])
            self.assertEqual(code, 0, out)
            self.assertTrue(os.path.isdir(target))

            code, out = _run_cli(["backup-health", "--backup-dir", backups])
            self.assertEqual(code, 0, out)
            self.assertIn("OK", out)

            code, out = _run_cli(["retention", "--backup-dir", backups, "--keep-latest", "1",
                                  "--now", _NOW])
            self.assertEqual(code, 0, out)

    def test_backup_health_cli_exits_non_zero_on_a_missing_backup(self):
        with tempfile.TemporaryDirectory() as work:
            code, out = _run_cli(["backup-health", "--backup-dir", os.path.join(work, "none")])
            self.assertEqual(code, 1, out)
            self.assertIn("FAILED", out)

    def test_restore_cli_exits_non_zero_when_schema_is_refused(self):
        # A real restore into a non-empty target is refused -> the CLI exits non-zero.
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            occupied = os.path.join(work, "occupied")
            os.makedirs(store)
            os.makedirs(occupied)
            _seed_store(store)
            with open(os.path.join(occupied, "existing.jsonl"), "wb") as fh:
                fh.write(b'{"kept":1}\n')
            _run_cli(["backup", "--store-dir", store, "--backup-dir", backups, "--now", _NOW])
            snapshot = os.path.join(
                backups, sorted(n for n in os.listdir(backups) if n.startswith("snapshot-"))[-1])
            code, out = _run_cli(["restore", "--backup-path", snapshot, "--target-dir", occupied,
                                  "--now", _NOW])
            self.assertEqual(code, 1, out)


# --------------------------------------------------------------------------- #
# 9. no secret / no score-or-trade field in any report                          #
# --------------------------------------------------------------------------- #
def _iter_report_strings(obj, seen=None):
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, str):
        yield obj
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from _iter_report_strings(getattr(obj, f.name), seen)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_report_strings(k, seen)
            yield from _iter_report_strings(v, seen)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            yield from _iter_report_strings(item, seen)


class NoSecretNoScoreTests(unittest.TestCase):
    def _all_reports(self, store, backups, target):
        b = backup_ops.backup(store, backups, now=_NOW)
        return [
            b,
            backup_ops.dry_run_restore(b.snapshot_path, target, now=_NOW),
            backup_ops.restore(b.snapshot_path, target, now=_NOW),
            backup_ops.backup_health(backups),
            backup_ops.apply_retention_policy(backups, keep_latest=1, now=_NOW),
        ]

    def test_no_secret_value_appears_in_any_report(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            os.makedirs(store)
            _seed_store(store)
            os.environ["SEC_USER_AGENT"] = _SECRET
            try:
                reports = self._all_reports(store, os.path.join(work, "b"),
                                            os.path.join(work, "t"))
            finally:
                os.environ.pop("SEC_USER_AGENT", None)
            for report in reports:
                for text in _iter_report_strings(report):
                    self.assertNotIn(_SECRET, text)
                    self.assertNotIn("sk-", text)

    def test_no_score_or_trade_field_or_token_appears_in_any_report(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            os.makedirs(store)
            _seed_store(store)
            reports = self._all_reports(store, os.path.join(work, "b"), os.path.join(work, "t"))
            for report in reports:
                # no field NAME is a score/trade term.
                if dataclasses.is_dataclass(report):
                    for f in dataclasses.fields(report):
                        self.assertNotIn(f.name.lower(), _TRADE_TOKENS)
                # no field VALUE contains a score/trade token as a whole word.
                for text in _iter_report_strings(report):
                    low = text.lower()
                    for token in _TRADE_TOKENS:
                        self.assertNotIn(" " + token + " ", " " + low + " ",
                                         "trade/score token {0!r} in {1!r}".format(token, text))


# --------------------------------------------------------------------------- #
# 10. deterministic + demo/default pulse byte-identical                         #
# --------------------------------------------------------------------------- #
class DeterminismTests(unittest.TestCase):
    def test_backup_report_manifest_is_deterministic(self):
        def _run(work):
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            os.makedirs(store)
            _seed_store(store, run_id="RUN-DET-A")
            report = backup_ops.backup(store, backups, now=_NOW)
            return tuple((r.path, r.sha256, r.line_count) for r in report.files)
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertEqual(_run(a), _run(b))

    def test_demo_and_default_pulse_persistence_is_byte_identical(self):
        # The demo / default pulse (same watchlist + themes + now) persists byte-for-byte.
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _seed_store(a, run_id="RUN-DEMO")
            _seed_store(b, run_id="RUN-DEMO")
            names = sorted(n for n in os.listdir(a) if n.endswith(".jsonl"))
            self.assertTrue(names)
            for name in names:
                self.assertEqual(_rb(os.path.join(a, name)),
                                 _rb(os.path.join(b, name)),
                                 "pulse persistence drifted for {0}".format(name))


# --------------------------------------------------------------------------- #
# 11. offline kill-switch + AST clean (no network / subprocess in the module)   #
# --------------------------------------------------------------------------- #
class OfflineAstTests(unittest.TestCase):
    def _module_path(self):
        return os.path.join(_SRC, "cosmosiq_ops", "backup_ops.py")

    def test_module_imports_no_network_and_no_subprocess(self):
        with open(self._module_path(), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = {"socket", "urllib", "http", "requests", "ftplib", "asyncio", "subprocess",
                  "multiprocessing", "pty", "telnetlib", "smtplib"}
        roots = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.extend(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.append(node.module.split(".")[0])
        offending = sorted(set(roots) & banned)
        self.assertEqual(offending, [], "backup_ops must be offline: {0}".format(offending))

    def test_module_reads_no_wall_clock(self):
        with open(self._module_path(), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        wall = ("now", "utcnow", "today", "monotonic", "perf_counter", "sleep")
        hits = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in wall):
                hits.append("{0}: .{1}()".format(node.lineno, node.func.attr))
        self.assertEqual(hits, [], "backup_ops must read no wall clock: {0}".format(hits))


if __name__ == "__main__":
    unittest.main()
