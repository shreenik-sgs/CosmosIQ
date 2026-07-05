"""IMPLEMENTATION-019A -- CosmosIQ operator toolkit (``cosmosiq_ops``). OFFLINE.

Proves the Phase-019 operator tooling honours every standing guardrail:

* the package imports cleanly (bare ``cosmosiq_ops.`` imports; no ``import cosmosiq_ops`` break);
* the CI gate's report structure is closed, and the gate CATCHES a planted trade-token / secret
  artifact (fed a bad html tree; ``status == "fail"`` and the finding is NAMED);
* a backup snapshot's manifest sha256 is correct, ``verify`` NAMES a tampered byte, and a restore
  REFUSES a non-empty target (the append-only store is never overwritten in place);
* the production smoke passes on a fresh work dir OFFLINE;
* the perf probe runs at small scale within its data-driven budgets (durations, never scores);
* the environment report carries env var NAMES + presence labels ONLY -- a set value never leaks;
* AST proof: wall-clock + subprocess appear ONLY under ``src/cosmosiq_ops`` (the runtime packages
  ``reality_mesh`` / ``cosmosiq_app`` are scanned clean, bar the one sanctioned server shell);
* the seeded pulse is deterministic -- demo / default persistence is byte-identical.

Everything here is offline: temp-dir stores, injected ``now``, no network, no live endpoint.
"""

from __future__ import annotations

import ast
import os
import tempfile
import unittest

import cosmosiq_ops
from cosmosiq_ops import backup as ops_backup
from cosmosiq_ops.backup import (
    restore_check,
    restore_snapshot,
    snapshot_store,
    verify_snapshot,
)
from cosmosiq_ops.ci_gate import (
    CheckResult,
    CiGateReport,
    check_generated_pages_clean,
)
from cosmosiq_ops.env_config import environment_report, format_env_report
from cosmosiq_ops.perf import run_perf_probe
from cosmosiq_ops.smoke import run_production_smoke

from reality_mesh import (
    EventStore,
    FindingStore,
    RunStore,
    SignalStore,
    ThemePulseStore,
    ReplayHarness,
    run_pulse,
)

_NOW = "2026-06-29T00:00:00Z"
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

# Mirror of the runtime-shell guardrail (kept local so the test proves it independently).
_SUBPROCESS_ROOTS = frozenset({"subprocess", "multiprocessing", "pty"})
_WALL_CLOCK_ATTRS = ("now", "utcnow", "today", "time", "monotonic", "perf_counter", "sleep")
_SANCTIONED_WALL_CLOCK = ("cosmosiq_app/server.py",)


# --------------------------------------------------------------------------- #
# package imports                                                              #
# --------------------------------------------------------------------------- #
class PackageImportTests(unittest.TestCase):
    def test_import_cosmosiq_ops_exposes_the_toolkit(self):
        for name in ("run_ci_gate", "run_production_smoke", "run_perf_probe",
                     "environment_report", "snapshot_store", "verify_snapshot",
                     "restore_check", "CiGateReport", "SmokeReport", "PerfReport",
                     "EnvReport", "ARCHIVE_POLICY"):
            self.assertTrue(hasattr(cosmosiq_ops, name), "missing export: " + name)


# --------------------------------------------------------------------------- #
# ci gate: structure + it catches a planted violation                          #
# --------------------------------------------------------------------------- #
class CiGateReportTests(unittest.TestCase):
    def test_report_passed_is_strict_over_check_statuses(self):
        clean = CiGateReport("root", False, (
            CheckResult("a", "pass"), CheckResult("b", "skipped")))
        self.assertTrue(clean.passed)
        self.assertEqual(clean.checks_failed, 0)
        dirty = CiGateReport("root", False, (
            CheckResult("a", "pass"), CheckResult("b", "fail", ("boom",))))
        self.assertFalse(dirty.passed)
        self.assertEqual(dirty.checks_failed, 1)

    def test_gate_catches_a_planted_trade_and_secret_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            gen = os.path.join(root, "generated")
            os.makedirs(gen)
            with open(os.path.join(gen, "planted.html"), "w", encoding="utf-8") as fh:
                fh.write("<html>please BUY this now; token sk-abcdefgh1234; "
                         "api_key here; adhara</html>")
            result = check_generated_pages_clean(root)
        self.assertEqual(result.status, "fail")
        joined = " ".join(result.details)
        self.assertIn("planted.html", joined)                 # the file is NAMED
        self.assertIn("trade-affordance", joined)
        self.assertTrue(any("secret-like" in d for d in result.details))

    def test_gate_passes_a_clean_tree(self):
        with tempfile.TemporaryDirectory() as root:
            result = check_generated_pages_clean(root)
        self.assertEqual(result.status, "pass")


# --------------------------------------------------------------------------- #
# backup / verify / restore                                                    #
# --------------------------------------------------------------------------- #
def _seed_store(store_dir: str) -> None:
    pulse = run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW)
    harness = ReplayHarness(
        EventStore(store_dir), FindingStore(store_dir), SignalStore(store_dir),
        ThemePulseStore(store_dir), RunStore(store_dir))
    harness.persist_pulse(pulse, run_id="RUN-BK-001", now=_NOW, runtime_version="019")


class BackupTests(unittest.TestCase):
    def test_manifest_sha256_matches_and_verify_is_clean(self):
        import hashlib
        with tempfile.TemporaryDirectory() as work:
            store, backups = os.path.join(work, "s"), os.path.join(work, "b")
            os.makedirs(store)
            _seed_store(store)
            report = snapshot_store(store, backups, now=_NOW)
            self.assertGreater(report.total_files, 0)
            for record in report.files:
                on_disk = os.path.join(report.snapshot_path, record.path.replace("/", os.sep))
                with open(on_disk, "rb") as fh:
                    expected = hashlib.sha256(fh.read()).hexdigest()
                self.assertEqual(record.sha256, expected, record.path)
            self.assertTrue(verify_snapshot(report.snapshot_path).ok)

    def test_verify_names_a_tampered_byte(self):
        with tempfile.TemporaryDirectory() as work:
            store, backups = os.path.join(work, "s"), os.path.join(work, "b")
            os.makedirs(store)
            _seed_store(store)
            report = snapshot_store(store, backups, now=_NOW)
            target = report.files[0].path.replace("/", os.sep)
            tampered_path = os.path.join(report.snapshot_path, target)
            with open(tampered_path, "ab") as fh:
                fh.write(b"x")                                 # flip the snapshot copy
            verify = verify_snapshot(report.snapshot_path)
            self.assertFalse(verify.ok)
            self.assertTrue(any(report.files[0].path in m for m in verify.mismatched),
                            "the tampered file must be NAMED in the mismatch list")

    def test_restore_refuses_a_non_empty_target(self):
        with tempfile.TemporaryDirectory() as work:
            store, backups = os.path.join(work, "s"), os.path.join(work, "b")
            os.makedirs(store)
            _seed_store(store)
            report = snapshot_store(store, backups, now=_NOW)
            occupied = os.path.join(work, "target")
            os.makedirs(occupied)
            with open(os.path.join(occupied, "existing.jsonl"), "w", encoding="utf-8") as fh:
                fh.write('{"kept":1}\n')
            check = restore_check(report.snapshot_path, occupied)
            self.assertFalse(check.allowed)
            self.assertEqual(check.target_state, "non_empty")
            with self.assertRaises(ValueError):
                restore_snapshot(report.snapshot_path, occupied)
            # the pre-existing store line is untouched (never overwritten in place).
            with open(os.path.join(occupied, "existing.jsonl"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), '{"kept":1}\n')

    def test_archive_policy_is_never_edit(self):
        never = ops_backup.ARCHIVE_POLICY["never"]
        self.assertIn("edit a store or snapshot in place", never)
        self.assertEqual(ops_backup.ARCHIVE_POLICY["aged_out_snapshot"],
                         "archive_whole_directory")


# --------------------------------------------------------------------------- #
# smoke                                                                         #
# --------------------------------------------------------------------------- #
class SmokeTests(unittest.TestCase):
    def test_smoke_passes_on_a_fresh_work_dir_offline(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_production_smoke(work, now=_NOW)
        self.assertTrue(report.passed,
                        "failed steps: {0}".format(report.failed_steps))
        names = {step.name for step in report.steps}
        self.assertIn("replay_deterministic", names)
        self.assertIn("gates_no_hard_fail", names)
        self.assertIn("page /portfolio", names)
        self.assertIn("alert_inbox_quiet_first_run", names)
        self.assertIn("backup_snapshot_verifies", names)


# --------------------------------------------------------------------------- #
# perf                                                                          #
# --------------------------------------------------------------------------- #
class PerfTests(unittest.TestCase):
    def test_perf_probe_within_budget_at_small_scale(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_perf_probe(work, now=_NOW, scale=5)
        self.assertEqual(report.scale, 5)
        self.assertTrue(report.within_budget,
                        "over budget: {0}".format(report.over_budget))
        for m in report.measurements:
            self.assertGreaterEqual(m.seconds, 0.0)


# --------------------------------------------------------------------------- #
# env report: presence labels only, never a value                              #
# --------------------------------------------------------------------------- #
class EnvReportTests(unittest.TestCase):
    def test_a_set_value_never_leaks_only_a_presence_label(self):
        secret = "SECRET-EDGAR-UA-should-never-appear-9f8e7d"
        previous = os.environ.get("SEC_USER_AGENT")
        os.environ["SEC_USER_AGENT"] = secret
        try:
            report = environment_report()
            rendered = format_env_report(report)
        finally:
            if previous is None:
                os.environ.pop("SEC_USER_AGENT", None)
            else:
                os.environ["SEC_USER_AGENT"] = previous
        sec = next(v for v in report.variables if v.name == "SEC_USER_AGENT")
        self.assertEqual(sec.presence, "present")
        self.assertNotIn(secret, rendered)
        for var in report.variables:
            self.assertNotIn(secret, var.name + var.presence + var.purpose)


# --------------------------------------------------------------------------- #
# AST confinement: wall-clock + subprocess ONLY under cosmosiq_ops             #
# --------------------------------------------------------------------------- #
def _py_files(package: str):
    base = os.path.join(_SRC, package)
    for root, dirs, names in os.walk(base):
        dirs.sort()
        for name in sorted(names):
            if name.endswith(".py"):
                rel = os.path.relpath(os.path.join(root, name), _SRC).replace(os.sep, "/")
                yield rel, os.path.join(root, name)


def _import_roots(tree):
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.append(node.module.split(".")[0])
    return roots


class ShellConfinementTests(unittest.TestCase):
    def test_runtime_packages_have_no_subprocess_and_no_wall_clock(self):
        subprocess_hits, wall_clock_hits = [], []
        for package in ("reality_mesh", "cosmosiq_app"):
            for rel, path in _py_files(package):
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                for root in _import_roots(tree):
                    if root in _SUBPROCESS_ROOTS:
                        subprocess_hits.append("{0}: import {1}".format(rel, root))
                if rel in _SANCTIONED_WALL_CLOCK:
                    continue
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Attribute)
                            and node.func.attr in _WALL_CLOCK_ATTRS):
                        wall_clock_hits.append("{0}:{1}: .{2}()".format(
                            rel, node.lineno, node.func.attr))
        self.assertEqual(subprocess_hits, [],
                         "runtime must be subprocess-free: {0}".format(subprocess_hits))
        self.assertEqual(wall_clock_hits, [],
                         "runtime must be wall-clock-free: {0}".format(wall_clock_hits))

    def test_the_confinement_lives_in_cosmosiq_ops(self):
        # The tooling that IS allowed the wall clock / subprocess actually uses them --
        # confinement means "only here", not "nowhere".
        ops = {rel: path for rel, path in _py_files("cosmosiq_ops")}
        with open(ops["cosmosiq_ops/perf.py"], encoding="utf-8") as fh:
            perf_src = fh.read()
        with open(ops["cosmosiq_ops/ci_gate.py"], encoding="utf-8") as fh:
            gate_src = fh.read()
        self.assertIn("perf_counter", perf_src)
        self.assertIn("import subprocess", gate_src)


# --------------------------------------------------------------------------- #
# determinism: demo / default pulse persistence is byte-identical               #
# --------------------------------------------------------------------------- #
class DeterminismTests(unittest.TestCase):
    def test_seeded_pulse_persistence_is_byte_identical(self):
        def _persist(store_dir):
            pulse = run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW)
            harness = ReplayHarness(
                EventStore(store_dir), FindingStore(store_dir), SignalStore(store_dir),
                ThemePulseStore(store_dir), RunStore(store_dir))
            harness.persist_pulse(pulse, run_id="RUN-DET-001", now=_NOW,
                                  runtime_version="019")
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _persist(a)
            _persist(b)
            names = sorted(n for n in os.listdir(a) if n.endswith(".jsonl"))
            self.assertTrue(names)
            for name in names:
                with open(os.path.join(a, name), "rb") as fa, \
                        open(os.path.join(b, name), "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(),
                                     "pulse persistence drifted for {0}".format(name))


if __name__ == "__main__":
    unittest.main()
