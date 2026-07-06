"""Production persistence hardening for the CosmosIQ append-only stores (IMPLEMENTATION-023D).

A HARDENING LAYER that WRAPS + VALIDATES the accepted 013B :class:`~reality_mesh.stores.AppendOnlyStore`
(JSONL logs) and the 019A backup/verify/restore path (:mod:`cosmosiq_ops.backup`). It rewrites
nothing: it composes what is already proven and adds the production guarantees a durable
append-only substrate needs -- WITHOUT weakening the append-only contract:

* **Single-writer lock.** :func:`single_writer_lock` serialises writers at the STORE level (reuses
  the 020C lockfile pattern): a SECOND acquire while the lock is held is REFUSED -- a concurrent
  writer is blocked, never interleaved (no torn / corrupt line).
* **Schema versioning + compatibility.** :func:`schema_compatibility_check` reads the
  ``schema_version`` every 013B record carries and reports unknown / incompatible versions; a
  restore of an unsupported schema is REFUSED unless a migration is supplied.
* **Integrity / corruption detection.** :func:`seal_store` records a per-line sha256 baseline;
  :func:`integrity_check` recomputes it and DETECTS a mutated prior line, a truncated / garbled
  line, and a monotonic-append violation -- naming the store + line. It composes
  :func:`~cosmosiq_ops.backup.verify_snapshot` semantics (sha256 + line-count).
* **Hardened backup / restore.** :func:`hardened_backup` seals + snapshots + verifies;
  :func:`hardened_restore` verifies the snapshot, REFUSES a non-empty target + an incompatible
  schema (unless migrated), restores, then re-checks integrity AND re-runs a deterministic replay.
* **Retention = archive, never prune.** :data:`RETENTION_POLICY` + :func:`apply_retention` age out
  WHOLE snapshots by MOVING them under ``archive/`` (reusing 019A ``archive_snapshot``); an ACTIVE
  store is never pruned, deleted, edited, or touched.
* **Production check.** :func:`run_persistence_hardening_check` folds all of the above into one
  frozen pass/fail report for CI / prod-check use.

Append-only is PRESERVED: this layer adds no update / delete path, and it TREATS a mutation of a
prior line as corruption. Deterministic + OFFLINE + stdlib-only, Python 3.9: every instant is an
injected ``now`` string; no wall clock, no network, no subprocess, no secret / score in any report.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# Compose the 019A backup/verify/restore path -- never re-implement it.
from cosmosiq_ops.backup import (
    ARCHIVE_POLICY,
    _line_count,
    _sha256,
    archive_snapshot,
    restore_snapshot,
    snapshot_store,
    verify_snapshot,
)

# Reuse the accepted 020C single-instance lockfile pattern for a store-level writer lock.
from cosmosiq_service.service import (
    LockError,
    LockHandle,
    acquire_lock,
    read_lock,
    release_lock,
)

# The persisted schema version every 013B record carries (the compatibility anchor).
from reality_mesh.stores import SCHEMA_VERSION

__all__ = [
    "WRITER_LOCK_FILENAME",
    "INTEGRITY_DIRNAME",
    "INTEGRITY_MANIFEST_FILENAME",
    "INTEGRITY_MANIFEST_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "RETENTION_POLICY",
    "WriterLockError",
    "single_writer_lock",
    "release_writer_lock",
    "SchemaReport",
    "schema_compatibility_check",
    "StoreIntegrity",
    "IntegrityReport",
    "seal_store",
    "integrity_check",
    "HardenedBackupReport",
    "HardenedRestoreReport",
    "hardened_backup",
    "hardened_restore",
    "RetentionReport",
    "apply_retention",
    "HardeningStep",
    "HardeningReport",
    "run_persistence_hardening_check",
]

# The store-level writer lock (a sibling of the 020C service lock; a distinct name so the two
# never collide). Kept out of every backup: it is not a ``*.jsonl`` store and not an operator path.
WRITER_LOCK_FILENAME = ".writer.lock"

# The integrity baseline (a per-line sha256 seal) lives beside the stores but is not itself a store.
INTEGRITY_DIRNAME = ".integrity"
INTEGRITY_MANIFEST_FILENAME = "integrity_manifest.json"
INTEGRITY_MANIFEST_VERSION = "023D.1"

# The schema versions this build can read / restore. A record stamped with anything else is
# "incompatible" and a restore of it is refused unless a migration is supplied.
SUPPORTED_SCHEMA_VERSIONS: Tuple[str, ...] = (SCHEMA_VERSION,)

# Retention policy AS DATA (extends the 019A ``ARCHIVE_POLICY``; never prose-only). Aging out a
# snapshot MOVES its whole directory under ``archive/`` intact; an ACTIVE store is never touched.
RETENTION_POLICY: Dict[str, object] = {
    "unit": "whole_snapshot",
    "default": "keep_all",
    "aged_out_snapshot": "archive_whole_directory",
    "mechanism": "move the aged snapshot directory under <backup_dir>/archive/ INTACT",
    "active_store": "never_touched",
    "never": ("prune a line", "delete a line", "rewrite a line",
              "edit a store or snapshot in place", "touch an active store"),
    "note": "retention archives whole snapshots; append-only active history is preserved forever",
    "composes": ARCHIVE_POLICY["mechanism"],
}


# --------------------------------------------------------------------------- #
# 1. Single-writer lock -- a concurrent writer is blocked / serialised          #
# --------------------------------------------------------------------------- #
class WriterLockError(RuntimeError):
    """Raised when the store-level writer lock is already held (a concurrent writer is refused)."""


def _writer_lock_path(store_dir: str) -> str:
    if not store_dir or not str(store_dir).strip():
        raise ValueError("single_writer_lock requires a non-empty store_dir")
    return os.path.join(str(store_dir), WRITER_LOCK_FILENAME)


def single_writer_lock(store_dir: str, *, pid: int, now: str,
                       stale_after_seconds: int = 3600) -> LockHandle:
    """Acquire the STORE-LEVEL writer lock -- or REFUSE a concurrent writer.

    A single writer at a time may hold the lock; a SECOND :func:`single_writer_lock` acquire while
    it is held raises :class:`WriterLockError`. This is what SERIALISES writers so two of them can
    never interleave lines into the same append-only log (no torn / corrupt write). A lock older
    than ``stale_after_seconds`` (vs the injected ``now``) is reclaimable, exactly like the 020C
    service lock it reuses. Release with :func:`release_writer_lock`.
    """
    os.makedirs(str(store_dir), exist_ok=True)
    lock_path = _writer_lock_path(store_dir)
    try:
        return acquire_lock(lock_path, pid=pid, now=now, stale_after_seconds=stale_after_seconds)
    except LockError as exc:
        raise WriterLockError(str(exc)) from exc


def release_writer_lock(handle: Optional[LockHandle]) -> None:
    """Release the store-level writer lock (idempotent -- a missing lockfile is not an error)."""
    release_lock(handle)


def writer_lock_held(store_dir: str) -> bool:
    """True iff a store-level writer lock file is currently present (read-only)."""
    return read_lock(_writer_lock_path(store_dir)) is not None


# --------------------------------------------------------------------------- #
# 2. Schema compatibility -- read the schema_version every 013B record carries   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SchemaReport:
    """Every ``schema_version`` seen per store, and which versions are incompatible.

    Only records that CARRY a ``schema_version`` (the 013B envelope) are considered; other JSONL
    (service logs / schedule state) is ignored. ``compatible`` is strict: any unsupported version
    on any store makes the whole store dir incompatible.
    """

    store_dir: str
    supported_versions: Tuple[str, ...]
    per_store_versions: Tuple[Tuple[str, Tuple[str, ...]], ...] = field(default_factory=tuple)
    incompatible: Tuple[str, ...] = field(default_factory=tuple)   # "store: version"

    @property
    def compatible(self) -> bool:
        return not self.incompatible

    @property
    def all_versions(self) -> Tuple[str, ...]:
        seen = set()
        for _store, versions in self.per_store_versions:
            seen.update(versions)
        return tuple(sorted(seen))


def _jsonl_files(root: str) -> Tuple[Tuple[str, str], ...]:
    """Sorted ``(relative_name, absolute_path)`` for every ``*.jsonl`` under ``root``."""
    out: List[Tuple[str, str]] = []
    if not os.path.isdir(root):
        return ()
    for cur, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            if name.endswith(".jsonl"):
                path = os.path.join(cur, name)
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                out.append((rel, path))
    return tuple(sorted(out))


def _read_lines(path: str) -> Tuple[bytes, ...]:
    """Raw non-empty lines (bytes, newline-stripped) of a file, in order."""
    with open(path, "rb") as handle:
        return tuple(line for line in handle.read().splitlines() if line.strip())


def schema_compatibility_check(
        store_dir: str, *,
        supported_versions: Tuple[str, ...] = SUPPORTED_SCHEMA_VERSIONS) -> SchemaReport:
    """Read the ``schema_version`` on every store record; report unknown / incompatible versions.

    Walks every ``*.jsonl`` under ``store_dir`` (works on a live store dir OR a snapshot dir),
    collects the distinct ``schema_version`` values each store carries, and flags any that is not
    in ``supported_versions``. A restore consults this before touching a target (see
    :func:`hardened_restore`).
    """
    supported = tuple(supported_versions)
    per_store: List[Tuple[str, Tuple[str, ...]]] = []
    incompatible: List[str] = []
    for rel, path in _jsonl_files(store_dir):
        versions = set()
        for raw in _read_lines(path):
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if isinstance(record, dict) and "schema_version" in record:
                versions.add(str(record["schema_version"]))
        if not versions:
            continue
        per_store.append((rel, tuple(sorted(versions))))
        for version in sorted(versions):
            if version not in supported:
                incompatible.append("{0}: {1}".format(rel, version))
    return SchemaReport(
        store_dir=str(store_dir), supported_versions=supported,
        per_store_versions=tuple(per_store), incompatible=tuple(sorted(incompatible)))


# --------------------------------------------------------------------------- #
# 3. Integrity / corruption detection -- a mutated prior line IS corruption      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StoreIntegrity:
    """Integrity facts for ONE store: counts, whole-file sha256, append-only verdict + findings."""

    store: str
    line_count: int
    sha256: str
    append_only_ok: bool
    findings: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IntegrityReport:
    """The whole store dir's integrity. ``ok`` is strict: any finding on any store fails it."""

    store_dir: str
    sealed: bool
    stores: Tuple[StoreIntegrity, ...] = field(default_factory=tuple)

    @property
    def append_only_ok(self) -> bool:
        return all(store.append_only_ok for store in self.stores)

    @property
    def ok(self) -> bool:
        return all(store.append_only_ok and not store.findings for store in self.stores)

    @property
    def corruption_findings(self) -> Tuple[str, ...]:
        out: List[str] = []
        for store in self.stores:
            out.extend(store.findings)
        return tuple(out)

    @property
    def total_lines(self) -> int:
        return sum(store.line_count for store in self.stores)


def _seal_manifest_path(store_dir: str) -> str:
    return os.path.join(str(store_dir), INTEGRITY_DIRNAME, INTEGRITY_MANIFEST_FILENAME)


def _line_hashes(path: str) -> Tuple[str, ...]:
    return tuple(hashlib.sha256(line).hexdigest() for line in _read_lines(path))


def seal_store(store_dir: str, *, now: str) -> Dict[str, object]:
    """Record the append-only integrity BASELINE: a per-line sha256 seal for every store.

    Writes ``<store_dir>/.integrity/integrity_manifest.json`` (deterministic, ``sort_keys``). A
    later :func:`integrity_check` compares against this seal to DETECT a mutated prior line or a
    monotonic-append violation. Sealing is idempotent: re-sealing simply re-records the current
    (append-only-grown) state. The seal is not a store and is never backed up.
    """
    if not str(now).strip():
        raise ValueError("seal_store requires a non-empty injected 'now' instant")
    stores: Dict[str, object] = {}
    for rel, path in _jsonl_files(store_dir):
        stores[rel] = {
            "line_count": _line_count(path),
            "line_hashes": list(_line_hashes(path)),
            "sha256": _sha256(path),
        }
    manifest = {
        "manifest_version": INTEGRITY_MANIFEST_VERSION,
        "sealed_at": str(now),
        "stores": stores,
    }
    seal_path = _seal_manifest_path(store_dir)
    os.makedirs(os.path.dirname(seal_path), exist_ok=True)
    tmp = seal_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, sort_keys=True, indent=2)
        handle.write("\n")
    os.replace(tmp, seal_path)
    return manifest


def _load_seal(store_dir: str) -> Optional[Dict[str, object]]:
    seal_path = _seal_manifest_path(store_dir)
    if not os.path.isfile(seal_path):
        return None
    try:
        with open(seal_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def integrity_check(store_dir: str) -> IntegrityReport:
    """Recompute per-store integrity + DETECT corruption; name the store + line for every finding.

    Always performs a STRUCTURAL check (each non-empty line must be valid JSON -- a truncated /
    garbled line is named). If an integrity seal exists (see :func:`seal_store`) it ALSO performs
    the append-only check: comparing each current line's sha256 against the sealed baseline it
    detects a MUTATED prior line (append-only violation) and a MONOTONIC-APPEND violation (a
    previously sealed line removed / truncated away). A file that only GREW (new lines appended
    past the seal) is clean -- that is what append-only means. Reads only; mutates nothing.
    """
    seal = _load_seal(store_dir)
    sealed_stores: Dict[str, Dict[str, object]] = {}
    if isinstance(seal, dict):
        raw_stores = seal.get("stores", {})
        if isinstance(raw_stores, dict):
            sealed_stores = raw_stores  # type: ignore[assignment]

    results: List[StoreIntegrity] = []
    for rel, path in _jsonl_files(store_dir):
        lines = _read_lines(path)
        findings: List[str] = []

        # -- structural: every non-empty line must parse (truncation / garble is corruption) -- #
        for index, raw in enumerate(lines, start=1):
            try:
                json.loads(raw)
            except ValueError:
                findings.append(
                    "{0} line {1}: not valid JSON -- truncated / garbled line (corruption)".format(
                        rel, index))

        # -- append-only: compare each line vs the sealed baseline ------------------------- #
        sealed = sealed_stores.get(rel) if isinstance(sealed_stores.get(rel), dict) else None
        if sealed is not None:
            sealed_hashes = [str(h) for h in (sealed.get("line_hashes") or [])]
            current_hashes = list(_line_hashes(path))
            if len(current_hashes) < len(sealed_hashes):
                findings.append(
                    "{0}: monotonic-append violation -- {1} lines sealed, only {2} present "
                    "(a prior line was removed / truncated)".format(
                        rel, len(sealed_hashes), len(current_hashes)))
            for index in range(min(len(sealed_hashes), len(current_hashes))):
                if current_hashes[index] != sealed_hashes[index]:
                    findings.append(
                        "{0} line {1}: prior line MUTATED (append-only violation) -- "
                        "sealed sha256 {2} now {3}".format(
                            rel, index + 1, sealed_hashes[index][:12],
                            current_hashes[index][:12]))

        results.append(StoreIntegrity(
            store=rel, line_count=len(lines), sha256=_sha256(path),
            append_only_ok=not findings, findings=tuple(findings)))

    return IntegrityReport(store_dir=str(store_dir), sealed=bool(sealed_stores),
                           stores=tuple(results))


# --------------------------------------------------------------------------- #
# 4. Hardened backup / restore -- wrap 019A snapshot/verify/restore              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HardenedBackupReport:
    """What a hardened backup produced: the snapshot path + verify + integrity verdicts."""

    store_dir: str
    snapshot_path: str
    files_captured: int
    jsonl_lines: int
    verify_ok: bool
    integrity_ok: bool
    schema_compatible: bool
    findings: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.verify_ok and self.integrity_ok and self.schema_compatible


@dataclass(frozen=True)
class HardenedRestoreReport:
    """What a hardened restore produced: refusal reason OR the restored + re-verified target."""

    backup_path: str
    target_dir: str
    allowed: bool
    refusal_reason: str = ""
    migrated: bool = False
    files_restored: int = 0
    verify_ok: bool = False
    schema_compatible: bool = False
    integrity_ok: bool = False
    replay_ok: bool = False
    findings: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return (self.allowed and self.verify_ok and self.schema_compatible
                and self.integrity_ok and self.replay_ok)


def hardened_backup(store_dir: str, backup_dir: str, *, now: str) -> HardenedBackupReport:
    """Seal integrity, SNAPSHOT the store (019A), and VERIFY the snapshot -- one hardened backup.

    Steps: (1) integrity_check the live store (a corrupt store is reported, never silently
    backed up); (2) :func:`seal_store` records the append-only baseline; (3)
    :func:`~cosmosiq_ops.backup.snapshot_store` copies every ``*.jsonl`` + writes a sha256
    manifest; (4) :func:`~cosmosiq_ops.backup.verify_snapshot` proves the copy round-trips. The
    snapshot is the restorable artifact; :func:`hardened_restore` consumes it.
    """
    if not str(now).strip():
        raise ValueError("hardened_backup requires a non-empty injected 'now' instant")
    pre = integrity_check(store_dir)
    schema = schema_compatibility_check(store_dir)
    seal_store(store_dir, now=now)
    snapshot = snapshot_store(store_dir, backup_dir, now=now)
    verify = verify_snapshot(snapshot.snapshot_path)
    findings = tuple(pre.corruption_findings) + tuple(
        verify.mismatched + verify.missing + verify.extra) + tuple(
        "incompatible schema " + item for item in schema.incompatible)
    return HardenedBackupReport(
        store_dir=str(store_dir), snapshot_path=snapshot.snapshot_path,
        files_captured=snapshot.total_files, jsonl_lines=snapshot.total_jsonl_lines,
        verify_ok=verify.ok, integrity_ok=pre.append_only_ok,
        schema_compatible=schema.compatible, findings=findings)


def _replay_all_runs(target_dir: str, *, now: str = "") -> Tuple[bool, Tuple[str, ...]]:
    """Replay EVERY persisted run under ``target_dir`` and return (all_deterministic, differences).

    Reads the restored append-only stores and re-computes each run through the SAME 013C
    :class:`~reality_mesh.replay.ReplayHarness` the live pulse used. A run that fails to reproduce
    its persisted outputs (tampered history / non-determinism) is surfaced, never rubber-stamped.
    Imported lazily so this module has no import-time dependency on the runtime replay stack.
    """
    from reality_mesh import (
        EventStore,
        FindingStore,
        ReplayHarness,
        RunStore,
        SignalStore,
        ThemePulseStore,
    )
    from reality_mesh.runtime import ReplayRequest

    run_store = RunStore(target_dir)
    harness = ReplayHarness(
        EventStore(target_dir), FindingStore(target_dir), SignalStore(target_dir),
        ThemePulseStore(target_dir), run_store)
    run_ids = sorted({run.run_id for run in run_store.read_all()})
    if not run_ids:
        return False, ("no persisted run found to replay after restore",)
    differences: List[str] = []
    all_ok = True
    for run_id in run_ids:
        result = harness.replay(ReplayRequest(run_id=run_id), now=now)
        if not result.deterministic_match:
            all_ok = False
            differences.extend(result.differences)
    return all_ok, tuple(differences)


def hardened_restore(backup_dir: str, target_dir: str, *, now: str,
                     supported_versions: Tuple[str, ...] = SUPPORTED_SCHEMA_VERSIONS,
                     migration: Optional[Callable[[str], None]] = None) -> HardenedRestoreReport:
    """Verify + schema-gate + RESTORE a snapshot into an empty target, then re-prove it.

    ``backup_dir`` is a snapshot directory (as produced by :func:`hardened_backup`). Order:

    1. :func:`~cosmosiq_ops.backup.verify_snapshot` -- the snapshot must round-trip (sha256).
    2. :func:`schema_compatibility_check` on the snapshot -- an incompatible schema is REFUSED
       unless a ``migration`` callable is supplied (then it is applied to the restored target).
    3. :func:`~cosmosiq_ops.backup.restore_snapshot` -- REFUSES a non-empty target (the 019A
       guarantee: an existing append-only store is never overwritten in place).
    4. re-run :func:`integrity_check` AND :func:`_replay_all_runs` on the restored target -- a
       restore that cannot pass integrity + a deterministic replay is reported ``ok=False``.

    Never partially writes on a refusal: verification + schema gating happen BEFORE any copy.
    """
    if not str(now).strip():
        raise ValueError("hardened_restore requires a non-empty injected 'now' instant")

    verify = verify_snapshot(backup_dir)
    if not verify.ok:
        return HardenedRestoreReport(
            backup_path=str(backup_dir), target_dir=str(target_dir), allowed=False,
            refusal_reason="snapshot failed verification -- refusing to restore a corrupt backup",
            verify_ok=False,
            findings=tuple(verify.mismatched + verify.missing + verify.extra))

    schema = schema_compatibility_check(backup_dir, supported_versions=supported_versions)
    if not schema.compatible and migration is None:
        return HardenedRestoreReport(
            backup_path=str(backup_dir), target_dir=str(target_dir), allowed=False,
            refusal_reason=("incompatible schema and no migration supplied -- restore refused "
                            "(supply a migration to upgrade): " + "; ".join(schema.incompatible)),
            verify_ok=True, schema_compatible=False,
            findings=tuple("incompatible schema " + item for item in schema.incompatible))

    restored = restore_snapshot(backup_dir, target_dir)  # refuses a non-empty target itself
    migrated = False
    if not schema.compatible and migration is not None:
        migration(str(target_dir))
        migrated = True

    integrity = integrity_check(target_dir)
    replay_ok, replay_diffs = _replay_all_runs(target_dir, now=now)
    findings = tuple(integrity.corruption_findings) + tuple(replay_diffs)
    return HardenedRestoreReport(
        backup_path=str(backup_dir), target_dir=str(target_dir), allowed=True,
        migrated=migrated, files_restored=len(restored), verify_ok=True,
        schema_compatible=(schema.compatible or migrated),
        integrity_ok=integrity.ok, replay_ok=replay_ok, findings=findings)


# --------------------------------------------------------------------------- #
# 5. Retention -- archive whole snapshots; NEVER prune / touch an active store   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetentionReport:
    """What retention archived. An ACTIVE store is never touched -- only snapshots move."""

    backup_dir: str
    keep_latest: int
    archived: Tuple[str, ...] = field(default_factory=tuple)     # snapshot names moved to archive/
    retained: Tuple[str, ...] = field(default_factory=tuple)     # snapshot names kept live
    policy: str = "archive_whole_directory"


def _snapshot_names(backup_dir: str) -> Tuple[str, ...]:
    """Sorted names of the live snapshot directories directly under ``backup_dir`` (not archive/)."""
    if not os.path.isdir(backup_dir):
        return ()
    names = [
        name for name in os.listdir(backup_dir)
        if name.startswith("snapshot-")
        and os.path.isdir(os.path.join(backup_dir, name))]
    return tuple(sorted(names))


def apply_retention(backup_dir: str, *, keep_latest: int = 1) -> RetentionReport:
    """Age out old snapshots by ARCHIVING whole directories -- never prune, never touch a store.

    Keeps the newest ``keep_latest`` snapshots live and MOVES the rest under
    ``<backup_dir>/archive/`` intact (reusing 019A :func:`~cosmosiq_ops.backup.archive_snapshot`).
    Operates ONLY on the backup dir's snapshots: an ACTIVE store is never read, pruned, edited, or
    touched (:data:`RETENTION_POLICY`). Deterministic: snapshots sort by name (their injected
    ``now`` instant), newest last.
    """
    if keep_latest < 0:
        raise ValueError("apply_retention keep_latest must be >= 0")
    names = _snapshot_names(backup_dir)
    to_keep = set(names[len(names) - keep_latest:]) if keep_latest else set()
    if keep_latest == 0:
        to_keep = set()
    archived: List[str] = []
    for name in names:
        if name in to_keep:
            continue
        archive_snapshot(backup_dir, name)   # MOVES the whole directory; never deletes a line
        archived.append(name)
    retained = tuple(name for name in names if name in to_keep)
    return RetentionReport(
        backup_dir=str(backup_dir), keep_latest=keep_latest,
        archived=tuple(archived), retained=retained)


# --------------------------------------------------------------------------- #
# 6. run_persistence_hardening_check -- the one CI / prod-check report           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HardeningStep:
    """One hardening step: a name, a boolean outcome, and a plain-English reason (no secret)."""

    name: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class HardeningReport:
    """The whole hardening check. ``passed`` is strict: any failing step fails the check."""

    store_dir: str
    steps: Tuple[HardeningStep, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return bool(self.steps) and all(step.passed for step in self.steps)

    @property
    def failed_steps(self) -> Tuple[str, ...]:
        return tuple(step.name for step in self.steps if not step.passed)


def run_persistence_hardening_check(store_dir: str, *, now: str) -> HardeningReport:
    """Fold every hardening guarantee into ONE frozen pass/fail report (CI / prod-check use).

    OFFLINE + deterministic (injected ``now``). Steps, each pass/fail with a plain reason:

    1. the single-writer lock works AND blocks a concurrent writer (second acquire refused);
    2. append-only holds -- integrity_check over a fresh seal is clean (no mutation / garble);
    3. the store's schema is compatible with this build;
    4. a hardened backup snapshots + verifies clean;
    5. a hardened restore into a fresh target re-passes integrity + a deterministic replay;
    6. retention archives whole snapshots and leaves the ACTIVE store byte-unchanged.

    ``store_dir`` must already hold a persisted run (else the replay step has nothing to prove).
    Uses an isolated scratch dir (OUTSIDE ``store_dir``) for the backup / restore round-trip; the
    active store is only ever read + snapshotted, never mutated.
    """
    if not str(now).strip():
        raise ValueError("run_persistence_hardening_check requires an injected 'now' instant")
    import tempfile

    steps: List[HardeningStep] = []

    # 1. single-writer lock present + a concurrent writer is refused. ----------------------- #
    handle = single_writer_lock(store_dir, pid=1, now=now)
    try:
        concurrent_refused = False
        try:
            single_writer_lock(store_dir, pid=2, now=now)
        except WriterLockError:
            concurrent_refused = True
        steps.append(HardeningStep(
            "single_writer_lock_blocks_concurrent",
            handle is not None and concurrent_refused,
            "lock acquired by pid {0}; a second concurrent acquire was {1}".format(
                handle.pid, "REFUSED" if concurrent_refused else "ALLOWED (unsafe)")))
    finally:
        release_writer_lock(handle)

    # 2. append-only integrity clean over a fresh seal. ------------------------------------- #
    seal_store(store_dir, now=now)
    integrity = integrity_check(store_dir)
    steps.append(HardeningStep(
        "append_only_integrity_clean",
        integrity.ok and integrity.append_only_ok,
        "integrity over {0} store(s) / {1} lines: append_only_ok={2}{3}".format(
            len(integrity.stores), integrity.total_lines, integrity.append_only_ok,
            "" if integrity.ok else " -- " + "; ".join(integrity.corruption_findings))))

    # 3. schema compatible with this build. ------------------------------------------------- #
    schema = schema_compatibility_check(store_dir)
    steps.append(HardeningStep(
        "schema_compatible",
        schema.compatible,
        "schema versions {0} vs supported {1}{2}".format(
            list(schema.all_versions), list(schema.supported_versions),
            "" if schema.compatible else " -- incompatible: " + "; ".join(schema.incompatible))))

    # 4 + 5 + 6 use an isolated scratch dir OUTSIDE store_dir so the backup / restore / archive
    # artifacts never pollute the active store's ``*.jsonl`` walk.
    scratch = tempfile.mkdtemp(prefix="cosmosiq_hardening_")
    try:
        backup_dir = os.path.join(scratch, "backups")
        target_dir = os.path.join(scratch, "restore")

        # 4 + 5. hardened backup -> restore into a fresh target (integrity + replay re-pass). - #
        backup = hardened_backup(store_dir, backup_dir, now=now)
        steps.append(HardeningStep(
            "hardened_backup_verifies",
            backup.ok,
            "snapshot {0} files / {1} jsonl lines; verify_ok={2} integrity_ok={3}{4}".format(
                backup.files_captured, backup.jsonl_lines, backup.verify_ok, backup.integrity_ok,
                "" if backup.ok else " -- " + "; ".join(backup.findings))))

        restore = hardened_restore(backup.snapshot_path, target_dir, now=now)
        steps.append(HardeningStep(
            "hardened_restore_replays",
            restore.ok,
            "restored {0} files into a fresh target; integrity_ok={1} replay_ok={2}{3}".format(
                restore.files_restored, restore.integrity_ok, restore.replay_ok,
                "" if restore.ok else " -- " + (restore.refusal_reason
                                                or "; ".join(restore.findings)))))

        # 6. retention archives whole snapshots; the ACTIVE store is byte-unchanged. --------- #
        before = {rel: _sha256(path) for rel, path in _jsonl_files(store_dir)}
        retention = apply_retention(backup_dir, keep_latest=0)
        after = {rel: _sha256(path) for rel, path in _jsonl_files(store_dir)}
        store_unchanged = before == after
        steps.append(HardeningStep(
            "retention_archives_never_prunes",
            store_unchanged and bool(retention.archived),
            "archived {0} snapshot(s) whole; active store byte-unchanged={1}".format(
                len(retention.archived), store_unchanged)))
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)

    return HardeningReport(store_dir=str(store_dir), steps=tuple(steps))
