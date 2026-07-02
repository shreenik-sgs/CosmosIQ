"""Append-only local persistence stores for the Reality Mesh (IMPLEMENTATION-013B).

The durable, replayable substrate specified in ``PERSISTENCE_REPLAY_CONTRACT_013.md`` §1-§2.
These stores **PERSIST** the runtime records of a manual pulse -- they never conclude, score,
rank, or decide. A store is a plain local JSONL log (one JSON record per line); it is the
"append-natural, git-diffable" leaning the contract documents (§2).

HARD DISCIPLINE baked into the shape (PERSISTENCE_REPLAY_CONTRACT_013 §1/§2 +
SECURITY_POLICY_CONTRACT_013 §1/§2):

* **Append-only.** A store exposes ``append`` / ``read_all`` / ``query`` and NOTHING that
  mutates history -- there is NO ``update`` / ``delete`` / ``__setitem__`` method. A historical
  record, once written, is never edited or removed. A CORRECTION is a NEW record (an
  :class:`AuditRecord` written to :class:`AuditStore` that *references* the corrected id) --
  the original line is byte-unchanged forever.
* **Every record is keyed for replay.** Each stored line carries an envelope with ``run_id`` +
  a stable ``record_id`` + a ``timestamp`` + a ``schema_version`` around the typed ``payload``.
* **No secret ever persists.** ``append`` deep-scans the record and REJECTS any credential-like
  key (``api_key`` / ``token`` / ``password`` / ``secret`` / ``authorization`` / ...): a store
  can never write a raw credential to disk.
* **No score / rank / trade field ever persists.** ``append`` likewise rejects any key carrying a
  trade-decision or scoring token (``buy`` / ``sell`` / ``order`` / ``broker`` / ``score`` /
  ``rank`` / ``rating`` / ``investab`` / ...). Stores hold labels + volumes, never a metric.
* **Deterministic.** Every line is ``json.dumps(sort_keys=True)`` with injected timestamps (no
  wall-clock in any id / replay path); records are read back in append order. Same input + same
  injected ``now`` -> byte-identical JSONL.

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no daemon, no streaming, no
broker -- local files only. Nothing here reaches a live endpoint.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from . import labels as _labels
from .models import (
    AgentFinding,
    RealityEvent,
    RealitySignal,
    ThemePulse,
)
from .runtime import PulseRun

__all__ = [
    "SCHEMA_VERSION",
    "CREDENTIAL_KEY_TOKENS",
    "FORBIDDEN_FIELD_TOKENS",
    "DQ_STATUSES",
    "DataQualityRecord",
    "AuditRecord",
    "AppendOnlyStore",
    "RunStore",
    "EventStore",
    "FindingStore",
    "SignalStore",
    "ThemePulseStore",
    "DataQualityStore",
    "AuditStore",
    "STORE_CLASSES",
]

# The persisted schema version stamped on EVERY record envelope (bump on a shape change).
SCHEMA_VERSION = "013.1"

# Key-name tokens that mark a credential. A record key CONTAINING any of these (case-insensitive)
# is refused at write time -- a store must never persist a raw secret (SECURITY_POLICY §1).
CREDENTIAL_KEY_TOKENS: Tuple[str, ...] = (
    "api_key", "apikey", "api-key", "token", "password", "passwd", "secret",
    "authorization", "auth_token", "access_key", "private_key", "credential",
    "bearer", "session_key", "client_secret",
)

# Key-name tokens that mark a trade-decision / scoring field. A record key CONTAINING any of these
# is refused at write time -- stores hold labels + volumes, never a score / rank / order
# (PERSISTENCE_REPLAY_CONTRACT_013 §1; SECURITY_POLICY §2). Mirrors the 012 banned-field set.
FORBIDDEN_FIELD_TOKENS: Tuple[str, ...] = (
    "buy", "sell", "hold", "order", "trade", "broker", "score", "rank", "rating",
    "investab",
)

# Closed status vocabulary a Data-Quality diagnostic record may carry (run health + gate result).
DQ_STATUSES = frozenset(_labels.RUN_STATUSES | {"pass", "fail"})

# Query aliases: a friendly filter key -> the real payload field it resolves to.
_QUERY_ALIASES = {"agent": "agent_id", "subject": "subject_ref"}

_MISSING = object()


# --------------------------------------------------------------------------- #
# Typed diagnostic records with no existing dataclass (DQ + audit)              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DataQualityRecord:
    """One per-run Data-Quality diagnostic (coverage / gaps / conflicts / failure / gate).

    A diagnostic, never a score: ``status`` is a closed label and ``records`` are opaque refs
    / notes. No investability / rank field exists here.
    """

    dq_id: str = ""
    run_id: str = ""
    category: str = ""                      # coverage / gaps / conflicts / source_failure / policy
    status: str = ""                        # closed: DQ_STATUSES (health label or gate pass/fail)
    summary: str = ""
    records: Tuple[str, ...] = field(default_factory=tuple)   # refs / notes (no secrets)
    detail: str = ""
    at: str = ""                            # injected timestamp

    def __post_init__(self) -> None:
        _require_ids(self, ("dq_id",))
        if self.status and self.status not in DQ_STATUSES:
            raise ValueError(
                "DataQualityRecord.status {0!r} invalid (allowed: {1})".format(
                    self.status, sorted(DQ_STATUSES)))


@dataclass(frozen=True)
class AuditRecord:
    """One append-only audit-trail entry: who / what / when / (why).

    A CORRECTION is an AuditRecord with ``corrects`` set to the id of the record being
    superseded -- it REFERENCES, never mutates, the corrected record (:attr:`is_correction`).
    """

    audit_id: str = ""
    run_id: str = ""
    actor: str = ""                         # who (agent id / synthesizer / "human")
    action: str = ""                        # what (append / route / gate / correction / ...)
    subject_ref: str = ""                   # id of the record acted upon
    at: str = ""                            # when (injected timestamp)
    corrects: str = ""                      # id of a corrected record ("" if not a correction)
    reason: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        _require_ids(self, ("audit_id",))

    @property
    def is_correction(self) -> bool:
        """True iff this entry corrects (references) a prior record."""
        return bool(self.corrects.strip())


def _require_ids(obj, names: Tuple[str, ...]) -> None:
    """Raise ``ValueError`` if any named required-id field is empty/blank."""
    for name in names:
        value = getattr(obj, name, "")
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(
                "{0}.{1} is a required id and must be non-empty".format(
                    type(obj).__name__, name))


# --------------------------------------------------------------------------- #
# Deterministic (de)serialization helpers                                      #
# --------------------------------------------------------------------------- #
def _tuplify(value: Any) -> Any:
    """Recursively turn every JSON list back into a tuple (dicts recursed, scalars untouched).

    Round-trips a frozen dataclass exactly: ``asdict`` lowers ``Tuple`` fields (incl. tuples of
    tuples like ``numeric_values``) to lists; this restores them so a reconstructed object
    compares equal to the original.
    """
    if isinstance(value, list):
        return tuple(_tuplify(v) for v in value)
    if isinstance(value, dict):
        return {k: _tuplify(v) for k, v in value.items()}
    return value


def _payload_dict(item: Any) -> Dict[str, Any]:
    """Lower a frozen dataclass (or an already-plain dict) to a JSON-ready payload dict."""
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    if isinstance(item, dict):
        return dict(item)
    raise TypeError(
        "append expects a dataclass record or a dict, got {0}".format(type(item).__name__))


def _scan_bad_key(obj: Any, tokens: Tuple[str, ...]) -> Optional[str]:
    """Return the first (case-insensitive) key that CONTAINS any banned token, else ``None``.

    Deep-scans dict keys plus the elements of any nested list/tuple/dict value.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            low = str(key).lower()
            for token in tokens:
                if token in low:
                    return str(key)
            found = _scan_bad_key(value, tokens)
            if found is not None:
                return found
    elif isinstance(obj, (list, tuple)):
        for element in obj:
            found = _scan_bad_key(element, tokens)
            if found is not None:
                return found
    return None


# --------------------------------------------------------------------------- #
# The append-only base store                                                   #
# --------------------------------------------------------------------------- #
class AppendOnlyStore:
    """A JSONL-backed, append-only local store. NO update / delete / in-place mutation.

    Subclasses set :attr:`record_cls` (the frozen dataclass they round-trip), :attr:`id_field`
    (the natural stable id on that dataclass), and the query axes (:attr:`ticker_fields` /
    :attr:`theme_fields` / :attr:`timestamp_field`). The base handles the envelope, the
    credential / trade-field refusal, deterministic serialization, and read/query.
    """

    filename: str = "append_only_store.jsonl"
    record_cls: Optional[type] = None
    id_field: Optional[str] = None
    timestamp_field: Optional[str] = None
    ticker_fields: Tuple[str, ...] = ()
    theme_fields: Tuple[str, ...] = ()

    def __init__(self, store_dir: str, *, filename: Optional[str] = None) -> None:
        if not store_dir or not str(store_dir).strip():
            raise ValueError("AppendOnlyStore requires a non-empty store_dir")
        self.store_dir = str(store_dir)
        self.path = os.path.join(self.store_dir, filename or self.filename)
        os.makedirs(self.store_dir, exist_ok=True)

    @property
    def record_type(self) -> str:
        """The name persisted in the envelope's ``record_type`` field (for introspection)."""
        return self.record_cls.__name__ if self.record_cls is not None else "dict"

    # -- write ---------------------------------------------------------------- #
    def append(self, item: Any, *, run_id: str = "", timestamp: str = "",
               record_id: str = "") -> str:
        """Append ONE record and return its stable ``record_id``. Append-only -- never mutates.

        Assigns / preserves ``record_id`` + ``schema_version`` and wraps the payload in the
        replay envelope (``run_id`` / ``record_id`` / ``timestamp`` / ``schema_version``).
        REFUSES (``ValueError``) if any credential-like or trade/score key is present anywhere
        in the record -- a store never persists a secret or a score.
        """
        payload = _payload_dict(item)

        rid = record_id or (
            str(getattr(item, self.id_field, "")) if self.id_field else "") \
            or str(payload.get(self.id_field or "record_id", ""))
        if not rid.strip():
            raise ValueError(
                "{0}.append: could not resolve a stable record_id (pass record_id= or a "
                "record carrying {1!r})".format(type(self).__name__, self.id_field))

        resolved_run = run_id or str(getattr(item, "run_id", "")) or str(payload.get("run_id", ""))

        resolved_ts = timestamp
        if not resolved_ts and self.timestamp_field:
            resolved_ts = str(getattr(item, self.timestamp_field, "")) \
                or str(payload.get(self.timestamp_field, ""))

        record = {
            "schema_version": SCHEMA_VERSION,
            "record_id": rid,
            "run_id": resolved_run,
            "timestamp": resolved_ts,
            "record_type": self.record_type,
            "payload": payload,
        }

        bad_secret = _scan_bad_key(record, CREDENTIAL_KEY_TOKENS)
        if bad_secret is not None:
            raise ValueError(
                "refusing to persist a credential-like key {0!r} -- a store never writes a "
                "secret (scrub it before append)".format(bad_secret))
        bad_field = _scan_bad_key(record, FORBIDDEN_FIELD_TOKENS)
        if bad_field is not None:
            raise ValueError(
                "refusing to persist a trade/score key {0!r} -- stores hold labels + volumes, "
                "never a score / rank / order".format(bad_field))

        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return rid

    # -- read ----------------------------------------------------------------- #
    def read_records(self) -> Tuple[Dict[str, Any], ...]:
        """Every raw envelope record, in append order (empty tuple if the log does not exist)."""
        if not os.path.isfile(self.path):
            return ()
        out = []
        with open(self.path, encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if raw:
                    out.append(json.loads(raw))
        return tuple(out)

    def read_all(self) -> Tuple[Any, ...]:
        """Every record reconstructed to its typed object (in append order).

        For a store with a :attr:`record_cls`, a persisted object reconstructs EQUAL to the
        original (list -> tuple coercion + re-validation). A plain store yields payload dicts.
        """
        return tuple(self._reconstruct(rec) for rec in self.read_records())

    def query(self, **filters: Any) -> Tuple[Any, ...]:
        """Every record matching ALL filters, typed + in append order.

        Recognised filter keys: ``run_id`` (envelope), ``time_window`` / ``window`` (an inclusive
        ``(from, to)`` on the envelope timestamp), ``ticker`` (membership in this store's
        :attr:`ticker_fields`), ``theme`` (membership in :attr:`theme_fields`), plus any payload
        field by exact value / tuple membership (e.g. ``agent_id`` / ``discipline`` / ``state`` /
        ``category`` / ``status`` / ``subject_ref``; ``agent`` and ``subject`` are aliases).
        """
        return tuple(
            self._reconstruct(rec)
            for rec in self.read_records()
            if self._matches(rec, filters))

    # -- internal ------------------------------------------------------------- #
    def _reconstruct(self, record: Dict[str, Any]) -> Any:
        payload = _tuplify(record.get("payload", {}))
        if self.record_cls is None:
            return payload
        return self.record_cls(**payload)

    def _matches(self, record: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for key, val in filters.items():
            if key == "run_id":
                if record.get("run_id", "") != val:
                    return False
            elif key in ("time_window", "window"):
                lo, hi = val
                ts = record.get("timestamp", "")
                if not (lo <= ts <= hi):
                    return False
            elif key == "ticker":
                if not self._has_ticker(record, val):
                    return False
            elif key == "theme":
                if not self._has_theme(record, val):
                    return False
            else:
                if not self._field_matches(record, key, val):
                    return False
        return True

    def _field_matches(self, record: Dict[str, Any], key: str, val: Any) -> bool:
        payload = record.get("payload", {})
        target = key
        if key not in payload and key not in record:
            target = _QUERY_ALIASES.get(key, key)
        value = payload.get(target, record.get(target, _MISSING))
        if value is _MISSING:
            return False
        if isinstance(value, (list, tuple)):
            return val in value
        return value == val

    def _has_ticker(self, record: Dict[str, Any], val: str) -> bool:
        want = str(val).strip().upper()
        payload = record.get("payload", {})
        for name in self.ticker_fields:
            for candidate in _as_iterable(payload.get(name)):
                if str(candidate).strip().upper() == want:
                    return True
        return False

    def _has_theme(self, record: Dict[str, Any], val: str) -> bool:
        want = _norm_theme(val)
        payload = record.get("payload", {})
        for name in self.theme_fields:
            for candidate in _as_iterable(payload.get(name)):
                if _norm_theme(candidate) == want:
                    return True
        return False


def _as_iterable(value: Any) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return value
    return (value,)


def _norm_theme(text: Any) -> str:
    """Case / hyphen / underscore-insensitive theme token (mirrors pulse coverage matching)."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


# --------------------------------------------------------------------------- #
# Concrete stores (one JSONL log each; typed round-trip + query axes)          #
# --------------------------------------------------------------------------- #
class RunStore(AppendOnlyStore):
    """The spine: one :class:`~reality_mesh.runtime.PulseRun` per manual pulse.

    Query axis: ``run_id`` / ``time_window`` / ``mode`` (+ ``ticker`` over the watchlist,
    ``theme`` over the requested themes).
    """

    filename = "run_store.jsonl"
    record_cls = PulseRun
    id_field = "run_id"
    timestamp_field = "started_at"
    ticker_fields = ("watchlist",)
    theme_fields = ("themes",)


class EventStore(AppendOnlyStore):
    """:class:`~reality_mesh.models.RealityEvent`s -- the inputs agents saw.

    Query axes: ``run_id`` / ``ticker`` / ``theme`` / ``time_window`` (+ ``discipline``).
    """

    filename = "event_store.jsonl"
    record_cls = RealityEvent
    id_field = "event_id"
    timestamp_field = "timestamp"
    ticker_fields = ("affected_companies",)
    theme_fields = ("affected_themes",)


class FindingStore(AppendOnlyStore):
    """:class:`~reality_mesh.models.AgentFinding`s -- what each agent concluded in-discipline.

    Query axes: ``run_id`` / ``agent_id`` (alias ``agent``) / ``ticker`` / ``theme``.
    """

    filename = "finding_store.jsonl"
    record_cls = AgentFinding
    id_field = "finding_id"
    ticker_fields = ("affected_companies",)
    theme_fields = ("affected_themes",)


class SignalStore(AppendOnlyStore):
    """:class:`~reality_mesh.models.RealitySignal`s -- fused reality intelligence.

    Query axes: ``run_id`` / ``ticker`` / ``theme`` / ``discipline``.
    """

    filename = "signal_store.jsonl"
    record_cls = RealitySignal
    id_field = "signal_id"
    ticker_fields = ("affected_companies",)
    theme_fields = ("affected_themes",)


class ThemePulseStore(AppendOnlyStore):
    """:class:`~reality_mesh.models.ThemePulse`s -- theme state over runs (follow-through).

    Query axes: ``run_id`` / ``theme`` / ``state``.
    """

    filename = "theme_pulse_store.jsonl"
    record_cls = ThemePulse
    id_field = "theme_pulse_id"
    theme_fields = ("theme_id", "theme_name")


class DataQualityStore(AppendOnlyStore):
    """Per-run Data-Quality diagnostics (coverage / gaps / conflicts / failures / gate results).

    Query axes: ``run_id`` / ``category`` / ``status``.
    """

    filename = "data_quality_store.jsonl"
    record_cls = DataQualityRecord
    id_field = "dq_id"
    timestamp_field = "at"


class AuditStore(AppendOnlyStore):
    """The append-only audit trail: provenance + correction records.

    Query axes: ``run_id`` / ``subject_ref`` (alias ``subject``) / ``actor`` / ``action``.
    A correction is a NEW record referencing the corrected id -- see :meth:`append_correction`.
    """

    filename = "audit_store.jsonl"
    record_cls = AuditRecord
    id_field = "audit_id"
    timestamp_field = "at"

    def append_correction(self, *, audit_id: str, corrects: str, run_id: str = "",
                          actor: str = "", subject_ref: str = "", at: str = "",
                          reason: str = "", note: str = "") -> str:
        """Append a CORRECTION as a NEW audit record referencing ``corrects`` (never a mutation).

        The corrected record on disk is untouched; this superseding entry points at its id.
        """
        if not str(corrects).strip():
            raise ValueError("append_correction requires the corrected record id ('corrects')")
        record = AuditRecord(
            audit_id=audit_id, run_id=run_id, actor=actor, action="correction",
            subject_ref=subject_ref or corrects, at=at, corrects=corrects,
            reason=reason, note=note)
        return self.append(record, run_id=run_id, timestamp=at)


# The seven concrete stores (for registry / test introspection).
STORE_CLASSES = (
    RunStore,
    EventStore,
    FindingStore,
    SignalStore,
    ThemePulseStore,
    DataQualityStore,
    AuditStore,
)
