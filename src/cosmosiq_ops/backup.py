"""Backup / verify / restore for CosmosIQ JSONL stores (Phase 019). OFFLINE, local files only.

Retention policy (data, not prose): stores and snapshots are APPEND-ONLY artifacts.
"Aging out" a snapshot means MOVING its whole directory under ``<backup_dir>/archive/``
intact -- a store or snapshot line is never pruned, deleted, or rewritten.

Everything here is deterministic given the same inputs: the timestamp is injected
(``now``), file lists are sorted, and the manifest is ``sort_keys`` JSON.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

MANIFEST_FILENAME = "manifest.json"
MANIFEST_VERSION = "019.1"

# The operator-authored files/directories captured alongside every ``*.jsonl`` store.
# ("subscriptions" live INSIDE settings_store.jsonl -- captured by the .jsonl rule --
# but a standalone subscriptions file/dir is captured too if an operator ever adds one.)
OPERATOR_PATHS = ("portfolio", "diligence_inputs", "personal_profile.json",
                  "subscriptions", "subscriptions.json")

# Retention policy AS DATA (mirrored in docs/DEPLOYMENT_019.md).
ARCHIVE_POLICY: Dict[str, object] = {
    "default": "keep_all",
    "aged_out_snapshot": "archive_whole_directory",
    "mechanism": "move the snapshot directory under <backup_dir>/archive/ INTACT",
    "never": ("prune a line", "delete a line", "rewrite a line",
              "edit a store or snapshot in place"),
    "note": "an aged-out store is archived whole; append-only history is preserved forever",
}


@dataclass(frozen=True)
class SnapshotFileRecord:
    """One captured file: relative path + integrity facts."""

    path: str
    sha256: str
    size_bytes: int
    line_count: Optional[int]  # only for .jsonl files; None otherwise


@dataclass(frozen=True)
class SnapshotReport:
    """What one snapshot captured (paths relative to the snapshot directory)."""

    snapshot_path: str
    created_at: str
    files: Tuple[SnapshotFileRecord, ...] = field(default_factory=tuple)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_jsonl_lines(self) -> int:
        return sum(f.line_count or 0 for f in self.files)


@dataclass(frozen=True)
class VerifyReport:
    """Recomputed integrity vs the manifest. Any mismatch is NAMED, never summarized away."""

    backup_path: str
    files_checked: int
    mismatched: Tuple[str, ...] = field(default_factory=tuple)  # "path: expected X got Y"
    missing: Tuple[str, ...] = field(default_factory=tuple)     # in manifest, not on disk
    extra: Tuple[str, ...] = field(default_factory=tuple)       # on disk, not in manifest

    @property
    def ok(self) -> bool:
        return not (self.mismatched or self.missing or self.extra)


@dataclass(frozen=True)
class RestoreCheckReport:
    """Dry-run: what a restore WOULD do. Never touches the target."""

    backup_path: str
    target_dir: str
    target_state: str  # "missing" | "empty" | "non_empty"
    allowed: bool
    refusal_reason: str
    entries: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    # each entry: (relative path, action) with action in
    # ("would_create", "identical", "differs_from_target")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _line_count(path: str) -> int:
    with open(path, "rb") as handle:
        return len(handle.read().splitlines())


def _compact_instant(now: str) -> str:
    token = "".join(ch for ch in str(now) if ch.isalnum())
    if not token:
        raise ValueError("snapshot_store requires a non-empty injected 'now' instant")
    return token


def _capture_paths(store_dir: str) -> Tuple[str, ...]:
    """Sorted relative paths of everything a snapshot captures: every ``*.jsonl``
    anywhere under the store, plus the operator paths (files or whole directories)."""
    captured = set()
    operator_dirs = tuple(p for p in OPERATOR_PATHS
                          if os.path.isdir(os.path.join(store_dir, p)))
    for root, dirs, names in os.walk(store_dir):
        dirs.sort()
        rel_root = os.path.relpath(root, store_dir)
        rel_root = "" if rel_root == "." else rel_root
        top = rel_root.split(os.sep)[0] if rel_root else ""
        for name in sorted(names):
            rel = os.path.join(rel_root, name) if rel_root else name
            if name.endswith(".jsonl"):
                captured.add(rel)
            elif not rel_root and name in OPERATOR_PATHS:
                captured.add(rel)
            elif top and top in operator_dirs:
                captured.add(rel)
    return tuple(sorted(captured))


def snapshot_store(store_dir: str, backup_dir: str, *, now: str) -> SnapshotReport:
    """Copy the whole store into ``<backup_dir>/snapshot-<now>/`` + write a manifest.

    Captures every ``*.jsonl`` (the append-only stores) plus the operator files
    (:data:`OPERATOR_PATHS`). Refuses to reuse an existing snapshot directory --
    a snapshot, once written, is never rewritten.
    """
    if not os.path.isdir(store_dir):
        raise ValueError("snapshot_store: store directory does not exist: "
                         + os.path.basename(str(store_dir)))
    snapshot_name = "snapshot-" + _compact_instant(now)
    snapshot_path = os.path.join(backup_dir, snapshot_name)
    if os.path.exists(snapshot_path):
        raise ValueError("snapshot_store: refusing to overwrite existing snapshot "
                         + snapshot_name)
    os.makedirs(snapshot_path)

    records = []
    for rel in _capture_paths(store_dir):
        src = os.path.join(store_dir, rel)
        dst = os.path.join(snapshot_path, rel)
        os.makedirs(os.path.dirname(dst) or snapshot_path, exist_ok=True)
        shutil.copyfile(src, dst)
        records.append(SnapshotFileRecord(
            path=rel.replace(os.sep, "/"),
            sha256=_sha256(src),
            size_bytes=os.path.getsize(src),
            line_count=_line_count(src) if rel.endswith(".jsonl") else None))

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": str(now),
        "files": [{"path": r.path, "sha256": r.sha256, "size_bytes": r.size_bytes,
                   "line_count": r.line_count} for r in records],
    }
    with open(os.path.join(snapshot_path, MANIFEST_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return SnapshotReport(snapshot_path=snapshot_path, created_at=str(now),
                          files=tuple(records))


def _load_manifest(backup_path: str) -> Dict[str, object]:
    manifest_path = os.path.join(backup_path, MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        raise ValueError("no manifest.json found in backup: "
                         + os.path.basename(str(backup_path)))
    with open(manifest_path, encoding="utf-8") as fh:
        return json.load(fh)


def verify_snapshot(backup_path: str) -> VerifyReport:
    """Recompute every file's sha256 + line count against the manifest.

    Any divergence is NAMED file-by-file: hash mismatches, missing files, and
    extra files that the manifest never recorded.
    """
    manifest = _load_manifest(backup_path)
    entries = list(manifest.get("files", []))
    mismatched, missing = [], []
    manifest_paths = set()
    for entry in entries:
        rel = str(entry["path"])
        manifest_paths.add(rel)
        actual_path = os.path.join(backup_path, rel.replace("/", os.sep))
        if not os.path.isfile(actual_path):
            missing.append(rel)
            continue
        actual_sha = _sha256(actual_path)
        if actual_sha != entry["sha256"]:
            mismatched.append("{0}: sha256 mismatch -- manifest {1} actual {2}".format(
                rel, str(entry["sha256"])[:12], actual_sha[:12]))
            continue
        if rel.endswith(".jsonl"):
            actual_lines = _line_count(actual_path)
            if actual_lines != entry.get("line_count"):
                mismatched.append("{0}: line count mismatch -- manifest {1} actual {2}"
                                  .format(rel, entry.get("line_count"), actual_lines))

    extra = []
    for root, dirs, names in os.walk(backup_path):
        dirs.sort()
        for name in sorted(names):
            rel = os.path.relpath(os.path.join(root, name), backup_path)
            rel = rel.replace(os.sep, "/")
            if rel != MANIFEST_FILENAME and rel not in manifest_paths:
                extra.append(rel)

    return VerifyReport(backup_path=backup_path, files_checked=len(entries),
                        mismatched=tuple(mismatched), missing=tuple(missing),
                        extra=tuple(sorted(extra)))


def _target_state(target_dir: str) -> str:
    if not os.path.exists(target_dir):
        return "missing"
    if os.path.isdir(target_dir) and not os.listdir(target_dir):
        return "empty"
    return "non_empty"


def restore_check(backup_path: str, target_dir: str) -> RestoreCheckReport:
    """Dry-run diff of a restore. NEVER writes anything.

    A restore is only allowed into a missing or empty target directory: an existing
    non-empty store is NEVER overwritten (copy the backup elsewhere and inspect it
    instead). The report lists, per manifest file, what a restore would do.
    """
    manifest = _load_manifest(backup_path)
    state = _target_state(target_dir)
    entries = []
    for entry in manifest.get("files", []):
        rel = str(entry["path"])
        target_file = os.path.join(target_dir, rel.replace("/", os.sep))
        if not os.path.isfile(target_file):
            entries.append((rel, "would_create"))
        elif _sha256(target_file) == entry["sha256"]:
            entries.append((rel, "identical"))
        else:
            entries.append((rel, "differs_from_target"))
    allowed = state in ("missing", "empty")
    reason = "" if allowed else (
        "target directory is non-empty -- restore never overwrites an existing store; "
        "restore into a NEW directory instead")
    return RestoreCheckReport(backup_path=backup_path, target_dir=target_dir,
                              target_state=state, allowed=allowed,
                              refusal_reason=reason, entries=tuple(entries))


def restore_snapshot(backup_path: str, target_dir: str) -> Tuple[str, ...]:
    """Copy a VERIFIED snapshot into an empty/new directory. Refuses everything else.

    Returns the relative paths restored. Raises ``ValueError`` when the snapshot fails
    verification or the target is non-empty (the append-only store on disk is never
    overwritten in place).
    """
    verify = verify_snapshot(backup_path)
    if not verify.ok:
        raise ValueError("restore refused: snapshot failed verification: "
                         + "; ".join(verify.mismatched + verify.missing + verify.extra))
    check = restore_check(backup_path, target_dir)
    if not check.allowed:
        raise ValueError("restore refused: " + check.refusal_reason)
    os.makedirs(target_dir, exist_ok=True)
    restored = []
    for rel, _action in check.entries:
        src = os.path.join(backup_path, rel.replace("/", os.sep))
        dst = os.path.join(target_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst) or target_dir, exist_ok=True)
        shutil.copyfile(src, dst)
        restored.append(rel)
    return tuple(restored)


def archive_snapshot(backup_dir: str, snapshot_name: str) -> str:
    """Age out ONE snapshot by MOVING its whole directory under ``archive/`` -- intact.

    This is the only sanctioned retention mechanism (:data:`ARCHIVE_POLICY`): nothing
    inside the snapshot is edited, pruned, or rewritten. Returns the new path.
    """
    src = os.path.join(backup_dir, snapshot_name)
    if not os.path.isdir(src):
        raise ValueError("archive_snapshot: no such snapshot: " + str(snapshot_name))
    archive_root = os.path.join(backup_dir, "archive")
    os.makedirs(archive_root, exist_ok=True)
    dst = os.path.join(archive_root, snapshot_name)
    if os.path.exists(dst):
        raise ValueError("archive_snapshot: archive already holds " + str(snapshot_name))
    os.rename(src, dst)
    return dst
