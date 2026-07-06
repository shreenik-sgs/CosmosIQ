"""Operator-facing backup / restore / retention COMMANDS for the CosmosIQ stores (IMPLEMENTATION-023F).

A THIN operator wrapper that COMPOSES the already-accepted persistence stack -- it re-implements
NOTHING:

* the 019A backup path (:mod:`cosmosiq_ops.backup`): sha256 manifest, verify, restore-refuses-a-
  non-empty-target, archive-never-prune;
* the 023D persistence-hardening path (:mod:`cosmosiq_ops.persistence_hardening`):
  :func:`~cosmosiq_ops.persistence_hardening.hardened_backup` (seal + snapshot + verify),
  :func:`~cosmosiq_ops.persistence_hardening.hardened_restore` (verify -> schema-refusal-unless-
  migrated -> integrity + replay-after-restore), and
  :func:`~cosmosiq_ops.persistence_hardening.apply_retention` (archive whole snapshots, never touch
  an active store).

It folds those into FROZEN operator reports an operator (or CI) can gate on:

* :func:`backup`               -> :class:`BackupReport`        (manifest + per-file sha256 + status)
* :func:`restore`              -> :class:`RestoreReport`       (restored + replay_ok + integrity_ok)
* :func:`dry_run_restore`      -> :class:`RestoreReport`       (the PLAN; writes NOTHING)
* :func:`apply_retention_policy` -> RetentionReport            (archive-only; active store untouched)
* :func:`backup_health`        -> :class:`BackupHealthReport`  (latest snapshot health; no secret)

Deterministic + OFFLINE + stdlib-only, Python 3.9: every instant is an injected ``now`` string; no
wall clock, no network, no subprocess. No secret value and no score / trade field ever appears in a
report.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

# Compose the 019A backup path -- never re-implement it.
from cosmosiq_ops.backup import (
    MANIFEST_FILENAME,
    restore_check,
    verify_snapshot,
)

# Compose the 023D hardening path -- never re-implement it.
from cosmosiq_ops.persistence_hardening import (
    SUPPORTED_SCHEMA_VERSIONS,
    RetentionReport,
    apply_retention,
    hardened_backup,
    hardened_restore,
    schema_compatibility_check,
)

# Operator status vocabulary (matches the 023E observability tri-state; no secret / no score).
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_FAILED = "failed"

__all__ = [
    "STATUS_OK",
    "STATUS_DEGRADED",
    "STATUS_FAILED",
    "BackupFileRecord",
    "BackupReport",
    "RestoreReport",
    "BackupHealthReport",
    "RetentionReport",
    "backup",
    "restore",
    "dry_run_restore",
    "apply_retention_policy",
    "backup_health",
]


# --------------------------------------------------------------------------- #
# Report shapes -- frozen; no score / trade field                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BackupFileRecord:
    """One captured store file as recorded in the manifest: path + sha256 + line count."""

    path: str
    sha256: str
    line_count: Optional[int]   # only for .jsonl stores; None otherwise


@dataclass(frozen=True)
class BackupReport:
    """What an operator backup produced: the snapshot + its MANIFEST + per-file integrity + status."""

    store_dir: str
    backup_dir: str
    snapshot_path: str
    manifest_path: str
    files: Tuple[BackupFileRecord, ...] = field(default_factory=tuple)
    files_captured: int = 0
    jsonl_lines: int = 0
    verify_ok: bool = False
    integrity_ok: bool = False
    schema_compatible: bool = False
    status: str = STATUS_FAILED
    findings: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


@dataclass(frozen=True)
class RestoreReport:
    """What a restore (or a DRY-RUN restore) did or WOULD do. A dry-run writes nothing."""

    backup_path: str
    target_dir: str
    dry_run: bool
    allowed: bool
    target_state: str          # "missing" | "empty" | "non_empty"
    refusal_reason: str = ""
    migrated: bool = False
    plan: Tuple[str, ...] = field(default_factory=tuple)   # relative paths a restore would create
    files_restored: int = 0
    verify_ok: bool = False
    schema_compatible: bool = False
    integrity_ok: bool = False
    replay_ok: bool = False
    status: str = STATUS_FAILED
    findings: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        if self.dry_run:
            return self.allowed and self.verify_ok
        return (self.allowed and self.verify_ok and self.schema_compatible
                and self.integrity_ok and self.replay_ok)


@dataclass(frozen=True)
class BackupHealthReport:
    """The health of a backup directory: is the latest snapshot present, verified, schema-supported.

    Reports status only -- NO secret value, NO score / trade field.
    """

    backup_dir: str
    latest_snapshot: str = ""        # name of the newest live snapshot ("" if none)
    snapshot_count: int = 0
    last_backup_at: str = ""         # the newest snapshot's manifest ``created_at`` ("" if none)
    verify_ok: bool = False
    schema_supported: bool = False
    status: str = STATUS_FAILED
    findings: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


# --------------------------------------------------------------------------- #
# helpers (read-only)                                                           #
# --------------------------------------------------------------------------- #
def _manifest_records(snapshot_path: str) -> Tuple[BackupFileRecord, ...]:
    """Read the sha256 MANIFEST a snapshot carries and expose it as frozen per-file records."""
    manifest_path = os.path.join(snapshot_path, MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        return ()
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    records = []
    for entry in manifest.get("files", []):
        records.append(BackupFileRecord(
            path=str(entry["path"]), sha256=str(entry["sha256"]),
            line_count=entry.get("line_count")))
    return tuple(records)


def _live_snapshot_names(backup_dir: str) -> Tuple[str, ...]:
    """Sorted names of the live snapshot dirs directly under ``backup_dir`` (never archive/)."""
    if not os.path.isdir(backup_dir):
        return ()
    names = [name for name in os.listdir(backup_dir)
             if name.startswith("snapshot-")
             and os.path.isdir(os.path.join(backup_dir, name))]
    return tuple(sorted(names))


def _target_fingerprint(target_dir: str) -> Optional[Tuple[Tuple[str, int], ...]]:
    """A deterministic (relative-path, size) fingerprint of ``target_dir``, or ``None`` if missing.

    Used to PROVE a dry-run wrote nothing: the fingerprint before and after must be identical.
    """
    if not os.path.exists(target_dir):
        return None
    out = []
    for root, dirs, names in os.walk(target_dir):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, target_dir).replace(os.sep, "/")
            out.append((rel, os.path.getsize(path)))
    return tuple(sorted(out))


# --------------------------------------------------------------------------- #
# 1. backup                                                                     #
# --------------------------------------------------------------------------- #
def backup(store_dir: str, backup_dir: str, *, now: str) -> BackupReport:
    """Take a hardened operator backup: seal + snapshot + verify; report the MANIFEST + status.

    Composes :func:`~cosmosiq_ops.persistence_hardening.hardened_backup` (which seals the append-only
    integrity baseline, snapshots every ``*.jsonl`` store with a sha256 manifest via 019A
    :func:`~cosmosiq_ops.backup.snapshot_store`, then verifies the copy round-trips). The returned
    report names the manifest path, every captured file's sha256 + line count, and an ``ok /
    degraded / failed`` status. A failed verify -> ``failed``; a clean verify with an integrity or
    schema concern -> ``degraded``; all clean -> ``ok``.
    """
    result = hardened_backup(store_dir, backup_dir, now=now)
    records = _manifest_records(result.snapshot_path)
    manifest_path = os.path.join(result.snapshot_path, MANIFEST_FILENAME)
    if not result.verify_ok:
        status = STATUS_FAILED
    elif not (result.integrity_ok and result.schema_compatible):
        status = STATUS_DEGRADED
    else:
        status = STATUS_OK
    return BackupReport(
        store_dir=str(store_dir), backup_dir=str(backup_dir),
        snapshot_path=result.snapshot_path, manifest_path=manifest_path,
        files=records, files_captured=result.files_captured, jsonl_lines=result.jsonl_lines,
        verify_ok=result.verify_ok, integrity_ok=result.integrity_ok,
        schema_compatible=result.schema_compatible, status=status,
        findings=tuple(result.findings))


# --------------------------------------------------------------------------- #
# 2. restore                                                                    #
# --------------------------------------------------------------------------- #
def restore(backup_path: str, target_dir: str, *, now: str,
            supported_versions: Tuple[str, ...] = SUPPORTED_SCHEMA_VERSIONS,
            migration: Optional[Callable[[str], None]] = None) -> RestoreReport:
    """Restore a snapshot into an EMPTY target, then re-prove it (integrity + replay).

    Composes :func:`~cosmosiq_ops.persistence_hardening.hardened_restore`: verify the snapshot
    (sha256), REFUSE a non-empty target and an incompatible schema (unless a ``migration`` is
    supplied), restore, then re-run integrity + a deterministic replay against the restored store.
    Never writes on a refusal (verification + schema gating precede any copy).
    """
    check = restore_check(backup_path, target_dir)   # read-only: capture the plan + target state
    plan = tuple(rel for rel, _action in check.entries)
    if not check.allowed:
        # A non-empty target is REFUSED before any copy -- the 019A guarantee. Report it as a
        # frozen refusal (no exception) so the CLI can exit non-zero; nothing is written.
        return RestoreReport(
            backup_path=str(backup_path), target_dir=str(target_dir), dry_run=False,
            allowed=False, target_state=check.target_state,
            refusal_reason=check.refusal_reason, plan=plan, status=STATUS_FAILED,
            findings=(check.refusal_reason,))
    result = hardened_restore(backup_path, target_dir, now=now,
                              supported_versions=supported_versions, migration=migration)
    if not result.allowed:
        status = STATUS_FAILED
    elif result.ok:
        status = STATUS_OK
    else:
        status = STATUS_DEGRADED
    return RestoreReport(
        backup_path=str(backup_path), target_dir=str(target_dir), dry_run=False,
        allowed=result.allowed, target_state=check.target_state,
        refusal_reason=result.refusal_reason, migrated=result.migrated, plan=plan,
        files_restored=result.files_restored, verify_ok=result.verify_ok,
        schema_compatible=result.schema_compatible, integrity_ok=result.integrity_ok,
        replay_ok=result.replay_ok, status=status, findings=tuple(result.findings))


# --------------------------------------------------------------------------- #
# 3. dry_run_restore -- writes NOTHING                                          #
# --------------------------------------------------------------------------- #
def dry_run_restore(backup_path: str, target_dir: str, *, now: str,
                    supported_versions: Tuple[str, ...] = SUPPORTED_SCHEMA_VERSIONS
                    ) -> RestoreReport:
    """Report what a restore WOULD do -- and WRITE NOTHING (the target is left byte-untouched).

    Composes the read-only halves of the restore path: verify the snapshot,
    :func:`~cosmosiq_ops.persistence_hardening.schema_compatibility_check` the snapshot, and 019A
    :func:`~cosmosiq_ops.backup.restore_check` (which itself never writes). Returns the plan
    (target state, schema verdict, the file list a restore would create). ``now`` is accepted for a
    uniform signature; a dry-run runs no replay. This function asserts the target is untouched.
    """
    if not str(now).strip():
        raise ValueError("dry_run_restore requires a non-empty injected 'now' instant")
    before = _target_fingerprint(target_dir)

    verify = verify_snapshot(backup_path)
    schema = schema_compatibility_check(backup_path, supported_versions=supported_versions)
    check = restore_check(backup_path, target_dir)

    plan = tuple(rel for rel, _action in check.entries)
    allowed = verify.ok and check.allowed
    reasons = []
    if not verify.ok:
        reasons.append("snapshot failed verification -- a restore would refuse a corrupt backup")
    if not check.allowed:
        reasons.append(check.refusal_reason)
    if not schema.compatible:
        reasons.append("incompatible schema -- a restore would refuse unless a migration is "
                       "supplied: " + "; ".join(schema.incompatible))
    findings = tuple(verify.mismatched + verify.missing + verify.extra) + tuple(
        "incompatible schema " + item for item in schema.incompatible)
    if allowed and schema.compatible:
        status = STATUS_OK
    elif allowed:
        status = STATUS_DEGRADED     # would restore, but a migration is needed for the schema
    else:
        status = STATUS_FAILED       # a real restore would refuse

    report = RestoreReport(
        backup_path=str(backup_path), target_dir=str(target_dir), dry_run=True,
        allowed=allowed, target_state=check.target_state,
        refusal_reason="; ".join(r for r in reasons if r), migrated=False, plan=plan,
        files_restored=0, verify_ok=verify.ok, schema_compatible=schema.compatible,
        integrity_ok=False, replay_ok=False, status=status, findings=findings)

    # PROVE the dry-run wrote nothing: the target must be byte-for-byte as we found it.
    after = _target_fingerprint(target_dir)
    if before != after:
        raise AssertionError(
            "dry_run_restore must write NOTHING but the target changed: "
            + str(target_dir))
    return report


# --------------------------------------------------------------------------- #
# 4. retention -- archive whole snapshots; never touch an active store          #
# --------------------------------------------------------------------------- #
def apply_retention_policy(backup_dir: str, *, keep_latest: int, now: str) -> RetentionReport:
    """Age out old snapshots by ARCHIVING whole directories -- never prune, never touch a store.

    Composes 023D :func:`~cosmosiq_ops.persistence_hardening.apply_retention`: keep the newest
    ``keep_latest`` snapshots live and MOVE the rest under ``<backup_dir>/archive/`` intact. An
    ACTIVE store is never read, pruned, edited, or touched. ``now`` is accepted for a uniform
    operator signature; retention is deterministic on the snapshot names (their injected instants).
    """
    if not str(now).strip():
        raise ValueError("apply_retention_policy requires a non-empty injected 'now' instant")
    return apply_retention(backup_dir, keep_latest=keep_latest)


# --------------------------------------------------------------------------- #
# 5. backup_health -- status only, no secret                                    #
# --------------------------------------------------------------------------- #
def backup_health(backup_dir: str,
                  supported_versions: Tuple[str, ...] = SUPPORTED_SCHEMA_VERSIONS
                  ) -> BackupHealthReport:
    """Report the health of a backup directory: latest snapshot present? verifies? schema supported?

    Reads the newest live snapshot (highest name == latest injected instant), runs 019A
    :func:`~cosmosiq_ops.backup.verify_snapshot` and 023D
    :func:`~cosmosiq_ops.persistence_hardening.schema_compatibility_check` against it, and reads its
    manifest ``created_at`` as the last-backup marker. Status: ``failed`` if no snapshot or verify
    fails; ``degraded`` if it verifies but the schema is unsupported; ``ok`` otherwise. NO secret
    value and NO score / trade field is ever emitted.
    """
    names = _live_snapshot_names(backup_dir)
    if not names:
        return BackupHealthReport(
            backup_dir=str(backup_dir), snapshot_count=0, status=STATUS_FAILED,
            findings=("no snapshot found in backup dir -- nothing to restore from",))

    latest = names[-1]
    snapshot_path = os.path.join(backup_dir, latest)
    verify = verify_snapshot(snapshot_path)
    schema = schema_compatibility_check(snapshot_path, supported_versions=supported_versions)

    last_backup_at = ""
    manifest_path = os.path.join(snapshot_path, MANIFEST_FILENAME)
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as handle:
                last_backup_at = str(json.load(handle).get("created_at", ""))
        except (ValueError, OSError):
            last_backup_at = ""

    findings = tuple(verify.mismatched + verify.missing + verify.extra) + tuple(
        "incompatible schema " + item for item in schema.incompatible)
    if not verify.ok:
        status = STATUS_FAILED
    elif not schema.compatible:
        status = STATUS_DEGRADED
    else:
        status = STATUS_OK
    return BackupHealthReport(
        backup_dir=str(backup_dir), latest_snapshot=latest, snapshot_count=len(names),
        last_backup_at=last_backup_at, verify_ok=verify.ok,
        schema_supported=schema.compatible, status=status, findings=findings)
