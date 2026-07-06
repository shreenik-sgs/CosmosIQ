"""IMPLEMENTATION-023D -- production database / persistence hardening. OFFLINE, stdlib-only.

Proves the hardening layer (:mod:`cosmosiq_ops.persistence_hardening`) delivers the production
persistence guarantees WITHOUT weakening the append-only contract:

* **append-only is guaranteed** -- a mutation of a prior store line is DETECTED by
  ``integrity_check`` as corruption; the 013B ``AppendOnlyStore`` still exposes no update / delete;
* **a concurrent writer is blocked** -- a second ``single_writer_lock`` acquire while held is
  refused (writers are serialised, never interleaved);
* **backup restores cleanly** -- ``hardened_backup`` -> ``hardened_restore`` into an empty target
  reproduces the store byte-for-byte;
* **integrity check catches corruption** -- flipping a byte in a stored line is reported and the
  store + line are NAMED;
* **replay works after restore** -- persist -> backup -> restore -> ``ReplayHarness``
  ``deterministic_match`` is True;
* a restore REFUSES an incompatible schema unless a migration is supplied;
* retention ARCHIVES (never deletes) -- an active store is byte-unchanged after ``apply_retention``;
* no secret / no score-or-trade field in any report; deterministic; offline kill-switch; AST clean;
* the demo / default pulse persistence is byte-identical.

Everything here is offline: temp-dir stores, injected ``now``, no network, no live endpoint.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import tempfile
import unittest

import cosmosiq_ops
from cosmosiq_ops.persistence_hardening import (
    RETENTION_POLICY,
    SUPPORTED_SCHEMA_VERSIONS,
    WriterLockError,
    apply_retention,
    hardened_backup,
    hardened_restore,
    integrity_check,
    release_writer_lock,
    run_persistence_hardening_check,
    schema_compatibility_check,
    seal_store,
    single_writer_lock,
)

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
from reality_mesh.stores import SCHEMA_VERSION, AppendOnlyStore

_NOW = "2026-06-29T00:00:00Z"
_WATCHLIST = ["IREN", "NVDA"]
_THEMES = ["physical_ai", "robotics"]
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

# The secret / score-or-trade sentinels no report may ever contain.
_SECRET = "sk-ThisIsAFakeSecret-must-never-appear-a1b2c3"
_TRADE_TOKENS = ("buy", "sell", "order", "broker", "score", "rank", "rating")


def _seed_store(store_dir: str, *, run_id: str = "RUN-HARD-001") -> None:
    """Persist ONE deterministic pulse into the append-only stores under ``store_dir``."""
    pulse = run_pulse(list(_WATCHLIST), list(_THEMES), now=_NOW)
    harness = ReplayHarness(
        EventStore(store_dir), FindingStore(store_dir), SignalStore(store_dir),
        ThemePulseStore(store_dir), RunStore(store_dir))
    harness.persist_pulse(pulse, run_id=run_id, now=_NOW, runtime_version="023")


def _first_store_path(store_dir: str) -> str:
    return os.path.join(store_dir, "run_store.jsonl")


def _rb(path: str) -> bytes:
    """Whole-file bytes (closed handle -- keeps the suite ResourceWarning-clean)."""
    with open(path, "rb") as handle:
        return handle.read()


def _wb(path: str, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)


def _jsonl_bytes(store_dir: str):
    return {n: _rb(os.path.join(store_dir, n))
            for n in os.listdir(store_dir) if n.endswith(".jsonl")}


# --------------------------------------------------------------------------- #
# package export surface                                                        #
# --------------------------------------------------------------------------- #
class ExportTests(unittest.TestCase):
    def test_hardening_surface_is_exported(self):
        for name in ("single_writer_lock", "release_writer_lock", "schema_compatibility_check",
                     "integrity_check", "seal_store", "hardened_backup", "hardened_restore",
                     "apply_retention", "run_persistence_hardening_check", "RETENTION_POLICY",
                     "SUPPORTED_SCHEMA_VERSIONS", "WriterLockError"):
            self.assertTrue(hasattr(cosmosiq_ops, name), "missing export: " + name)


# --------------------------------------------------------------------------- #
# 1. append-only is guaranteed -- a mutated prior line is corruption            #
# --------------------------------------------------------------------------- #
class AppendOnlyGuaranteeTests(unittest.TestCase):
    def test_append_only_store_exposes_no_update_or_delete(self):
        # The hardening layer does not (and must not) add a mutation path to the store.
        for banned in ("update", "delete", "remove", "__setitem__", "__delitem__", "edit"):
            self.assertFalse(hasattr(AppendOnlyStore, banned),
                             "AppendOnlyStore must expose no {0!r} mutation API".format(banned))

    def test_mutation_of_a_prior_line_is_detected_as_corruption(self):
        with tempfile.TemporaryDirectory() as store:
            _seed_store(store)
            seal_store(store, now=_NOW)
            clean = integrity_check(store)
            self.assertTrue(clean.ok, clean.corruption_findings)
            self.assertTrue(clean.append_only_ok)

            # Mutate a value INSIDE a prior line so the JSON still parses -- only the seal
            # (per-line sha256) can catch this. This is the append-only violation.
            path = _first_store_path(store)
            lines = _rb(path).split(b"\n")
            self.assertIn(b"RUN-HARD-001", lines[0])
            lines[0] = lines[0].replace(b"RUN-HARD-001", b"RUN-TAMPER-9", 1)
            _wb(path, b"\n".join(lines))

            report = integrity_check(store)
            self.assertFalse(report.ok)
            self.assertFalse(report.append_only_ok)
            findings = " ".join(report.corruption_findings)
            self.assertIn("run_store.jsonl", findings)        # the store is NAMED
            self.assertIn("line 1", findings)                 # the line is NAMED
            self.assertIn("MUTATED", findings)

    def test_appending_new_lines_past_the_seal_stays_clean(self):
        # Append-only GROWTH is not corruption: new records added after a seal must verify clean.
        with tempfile.TemporaryDirectory() as store:
            _seed_store(store, run_id="RUN-A")
            seal_store(store, now=_NOW)
            _seed_store(store, run_id="RUN-B")               # append MORE history (append-only)
            report = integrity_check(store)
            self.assertTrue(report.ok, report.corruption_findings)
            self.assertTrue(report.append_only_ok)

    def test_monotonic_append_violation_is_detected(self):
        with tempfile.TemporaryDirectory() as store:
            _seed_store(store)
            seal_store(store, now=_NOW)
            path = _first_store_path(store)
            lines = [ln for ln in _rb(path).split(b"\n") if ln.strip()]
            _wb(path, b"\n".join(lines[:-1]) + b"\n")   # drop a sealed line
            report = integrity_check(store)
            self.assertFalse(report.append_only_ok)
            self.assertTrue(any("monotonic-append violation" in f
                                for f in report.corruption_findings))


# --------------------------------------------------------------------------- #
# 2. a concurrent writer is blocked / serialised                                #
# --------------------------------------------------------------------------- #
class SingleWriterLockTests(unittest.TestCase):
    def test_a_second_acquire_while_held_is_refused(self):
        with tempfile.TemporaryDirectory() as store:
            handle = single_writer_lock(store, pid=101, now=_NOW)
            try:
                with self.assertRaises(WriterLockError):
                    single_writer_lock(store, pid=202, now=_NOW)
            finally:
                release_writer_lock(handle)
            # once released, a writer can acquire again (serialised, not deadlocked).
            again = single_writer_lock(store, pid=303, now=_NOW)
            self.assertEqual(again.pid, 303)
            release_writer_lock(again)

    def test_a_stale_lock_is_reclaimable(self):
        with tempfile.TemporaryDirectory() as store:
            single_writer_lock(store, pid=1, now="2026-06-29T00:00:00Z", stale_after_seconds=60)
            reclaimed = single_writer_lock(
                store, pid=2, now="2026-06-29T02:00:00Z", stale_after_seconds=60)
            self.assertTrue(reclaimed.reclaimed_stale)
            release_writer_lock(reclaimed)


# --------------------------------------------------------------------------- #
# 3. backup restores cleanly (byte-for-byte)                                    #
# --------------------------------------------------------------------------- #
class BackupRestoreTests(unittest.TestCase):
    def test_hardened_backup_then_restore_reproduces_the_store_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            target = os.path.join(work, "restore")
            os.makedirs(store)
            _seed_store(store)

            backup = hardened_backup(store, backups, now=_NOW)
            self.assertTrue(backup.ok, backup.findings)
            self.assertTrue(backup.verify_ok)

            report = hardened_restore(backup.snapshot_path, target, now=_NOW)
            self.assertTrue(report.allowed, report.refusal_reason)
            self.assertTrue(report.ok, report.findings)

            names = sorted(n for n in os.listdir(store) if n.endswith(".jsonl"))
            self.assertTrue(names)
            for name in names:
                self.assertEqual(_rb(os.path.join(store, name)),
                                 _rb(os.path.join(target, name)),
                                 "restore drifted for {0}".format(name))

    def test_restore_refuses_a_non_empty_target(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            occupied = os.path.join(work, "target")
            os.makedirs(store)
            os.makedirs(occupied)
            _seed_store(store)
            _wb(os.path.join(occupied, "existing.jsonl"), b'{"kept":1}\n')
            backup = hardened_backup(store, backups, now=_NOW)
            with self.assertRaises(ValueError):
                hardened_restore(backup.snapshot_path, occupied, now=_NOW)
            # the pre-existing line is untouched (never overwritten in place).
            self.assertEqual(_rb(os.path.join(occupied, "existing.jsonl")), b'{"kept":1}\n')


# --------------------------------------------------------------------------- #
# 4. integrity check catches corruption (a flipped byte)                        #
# --------------------------------------------------------------------------- #
class IntegrityCorruptionTests(unittest.TestCase):
    def test_a_flipped_byte_is_reported_and_the_store_and_line_are_named(self):
        with tempfile.TemporaryDirectory() as store:
            _seed_store(store)
            seal_store(store, now=_NOW)
            path = _first_store_path(store)
            raw = bytearray(_rb(path))
            # flip one byte somewhere in the first line's payload.
            newline = raw.index(b"\n")
            flip_at = newline // 2
            raw[flip_at] ^= 0x20
            _wb(path, bytes(raw))

            report = integrity_check(store)
            self.assertFalse(report.ok)
            joined = " ".join(report.corruption_findings)
            self.assertIn("run_store.jsonl", joined)          # store NAMED
            self.assertIn("line 1", joined)                   # line NAMED

    def test_a_garbled_truncated_line_is_reported_even_without_a_seal(self):
        with tempfile.TemporaryDirectory() as store:
            _seed_store(store)
            path = _first_store_path(store)
            with open(path, "ab") as fh:
                fh.write(b'{"schema_version":"013.1","payload": TRUNCATED\n')  # invalid JSON
            report = integrity_check(store)          # no seal -> structural check still catches it
            self.assertFalse(report.ok)
            self.assertTrue(any("not valid JSON" in f for f in report.corruption_findings))


# --------------------------------------------------------------------------- #
# 5. replay works after restore                                                 #
# --------------------------------------------------------------------------- #
class ReplayAfterRestoreTests(unittest.TestCase):
    def test_replay_deterministic_match_after_restore(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            target = os.path.join(work, "restore")
            os.makedirs(store)
            _seed_store(store, run_id="RUN-REPLAY-1")

            backup = hardened_backup(store, backups, now=_NOW)
            report = hardened_restore(backup.snapshot_path, target, now=_NOW)
            self.assertTrue(report.replay_ok, report.findings)

            # independent replay against the RESTORED stores.
            harness = ReplayHarness(
                EventStore(target), FindingStore(target), SignalStore(target),
                ThemePulseStore(target), RunStore(target))
            result = harness.replay(ReplayRequest(run_id="RUN-REPLAY-1"), now=_NOW)
            self.assertTrue(result.deterministic_match,
                            "replay differences: {0}".format(result.differences))


# --------------------------------------------------------------------------- #
# 6. schema compatibility -- restore refuses an incompatible schema unless migrated #
# --------------------------------------------------------------------------- #
class SchemaCompatibilityTests(unittest.TestCase):
    def test_supported_versions_matches_the_store_schema(self):
        self.assertIn(SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS)

    def test_schema_check_flags_an_unknown_version(self):
        with tempfile.TemporaryDirectory() as store:
            _seed_store(store)
            report = schema_compatibility_check(store, supported_versions=("999.9",))
            self.assertFalse(report.compatible)
            self.assertTrue(report.incompatible)

    def test_restore_refuses_incompatible_schema_and_a_migration_lifts_it(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            os.makedirs(store)
            _seed_store(store)
            backup = hardened_backup(store, backups, now=_NOW)

            # treat the real schema as UNSUPPORTED for this build -> restore must refuse.
            refused = hardened_restore(
                backup.snapshot_path, os.path.join(work, "t1"),
                now=_NOW, supported_versions=("999.9",))
            self.assertFalse(refused.allowed)
            self.assertIn("incompatible schema", refused.refusal_reason)
            self.assertFalse(os.path.isdir(os.path.join(work, "t1")))   # nothing was written

            # a migration lifts the refusal; the restore then proceeds + re-verifies.
            calls = []
            report = hardened_restore(
                backup.snapshot_path, os.path.join(work, "t2"),
                now=_NOW, supported_versions=("999.9",),
                migration=lambda target: calls.append(target))
            self.assertTrue(report.allowed)
            self.assertTrue(report.migrated)
            self.assertEqual(len(calls), 1)
            self.assertTrue(report.ok, report.findings)


# --------------------------------------------------------------------------- #
# 7. retention archives (never deletes)                                         #
# --------------------------------------------------------------------------- #
class RetentionTests(unittest.TestCase):
    def test_apply_retention_archives_and_leaves_the_active_store_byte_unchanged(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            backups = os.path.join(work, "backups")
            os.makedirs(store)
            _seed_store(store)

            before = _jsonl_bytes(store)

            hardened_backup(store, backups, now="2026-06-29T00:00:00Z")
            hardened_backup(store, backups, now="2026-06-29T01:00:00Z")
            report = apply_retention(backups, keep_latest=1)

            self.assertEqual(len(report.archived), 1)            # oldest aged out
            self.assertEqual(len(report.retained), 1)            # newest kept live
            # the archived snapshot MOVED (still present under archive/), never deleted.
            archived_name = report.archived[0]
            self.assertTrue(os.path.isdir(os.path.join(backups, "archive", archived_name)))
            self.assertFalse(os.path.isdir(os.path.join(backups, archived_name)))

            # the ACTIVE store is byte-identical -- retention never touched it.
            after = _jsonl_bytes(store)
            self.assertEqual(before, after)

    def test_retention_policy_is_archive_never_prune(self):
        self.assertEqual(RETENTION_POLICY["aged_out_snapshot"], "archive_whole_directory")
        self.assertEqual(RETENTION_POLICY["active_store"], "never_touched")
        never = RETENTION_POLICY["never"]
        self.assertIn("prune a line", never)
        self.assertIn("touch an active store", never)


# --------------------------------------------------------------------------- #
# 8. the one CI / prod-check report                                             #
# --------------------------------------------------------------------------- #
class HardeningCheckTests(unittest.TestCase):
    def test_run_persistence_hardening_check_passes_on_a_seeded_store(self):
        with tempfile.TemporaryDirectory() as store:
            _seed_store(store)
            report = run_persistence_hardening_check(store, now=_NOW)
            self.assertTrue(report.passed, "failed: {0}".format(report.failed_steps))
            names = {step.name for step in report.steps}
            for expected in ("single_writer_lock_blocks_concurrent",
                             "append_only_integrity_clean", "schema_compatible",
                             "hardened_backup_verifies", "hardened_restore_replays",
                             "retention_archives_never_prunes"):
                self.assertIn(expected, names)

    def test_check_leaves_the_active_store_byte_unchanged(self):
        with tempfile.TemporaryDirectory() as store:
            _seed_store(store)
            before = _jsonl_bytes(store)
            run_persistence_hardening_check(store, now=_NOW)
            after = _jsonl_bytes(store)
            self.assertEqual(before, after)


# --------------------------------------------------------------------------- #
# 9. no secret / no score-or-trade field in any report                          #
# --------------------------------------------------------------------------- #
def _iter_report_strings(obj, seen=None):
    """Yield every string reachable inside a (possibly nested) frozen report / container."""
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
        return [
            schema_compatibility_check(store),
            seal_store(store, now=_NOW),
            integrity_check(store),
            hardened_backup(store, backups, now=_NOW),
            run_persistence_hardening_check(store, now=_NOW),
        ]

    def test_no_secret_value_appears_in_any_report(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            os.makedirs(store)
            _seed_store(store)
            # plant a secret in the environment; a hardening report must never surface a value.
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

    def test_no_score_or_trade_token_appears_in_any_report(self):
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            os.makedirs(store)
            _seed_store(store)
            reports = self._all_reports(store, os.path.join(work, "b"), os.path.join(work, "t"))
            for report in reports:
                for text in _iter_report_strings(report):
                    low = text.lower()
                    for token in _TRADE_TOKENS:
                        # allow paths/words that merely contain the token as a substring of an
                        # unrelated identifier is not expected here -- assert whole-word absence.
                        self.assertNotIn(" " + token + " ", " " + low + " ",
                                         "trade/score token {0!r} in report string {1!r}".format(
                                             token, text))


# --------------------------------------------------------------------------- #
# 10. deterministic + demo/default pulse byte-identical                         #
# --------------------------------------------------------------------------- #
class DeterminismTests(unittest.TestCase):
    def test_seeded_pulse_persistence_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _seed_store(a, run_id="RUN-DET-1")
            _seed_store(b, run_id="RUN-DET-1")
            names = sorted(n for n in os.listdir(a) if n.endswith(".jsonl"))
            self.assertTrue(names)
            for name in names:
                self.assertEqual(_rb(os.path.join(a, name)),
                                 _rb(os.path.join(b, name)),
                                 "pulse persistence drifted for {0}".format(name))

    def test_seal_and_integrity_are_deterministic(self):
        def _run(store):
            _seed_store(store, run_id="RUN-DET-2")
            seal_store(store, now=_NOW)
            report = integrity_check(store)
            return tuple((s.store, s.line_count, s.sha256) for s in report.stores)
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertEqual(_run(a), _run(b))

    def test_hardening_check_verdict_is_deterministic(self):
        def _verdict(store):
            _seed_store(store, run_id="RUN-DET-3")
            report = run_persistence_hardening_check(store, now=_NOW)
            return (report.passed, tuple(s.name for s in report.steps),
                    tuple(s.passed for s in report.steps))
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertEqual(_verdict(a), _verdict(b))


# --------------------------------------------------------------------------- #
# 11. offline kill-switch + AST clean (no network / subprocess in the module)   #
# --------------------------------------------------------------------------- #
class OfflineAstTests(unittest.TestCase):
    def _module_path(self):
        return os.path.join(_SRC, "cosmosiq_ops", "persistence_hardening.py")

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
        self.assertEqual(offending, [], "hardening module must be offline: {0}".format(offending))

    def test_module_reads_no_wall_clock(self):
        with open(self._module_path(), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        wall = ("now", "utcnow", "today", "monotonic", "perf_counter", "sleep")
        hits = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in wall):
                hits.append("{0}: .{1}()".format(node.lineno, node.func.attr))
        self.assertEqual(hits, [], "hardening module must read no wall clock: {0}".format(hits))


if __name__ == "__main__":
    unittest.main()
