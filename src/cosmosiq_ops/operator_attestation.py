"""GO-LIVE PL-2 -- evidence-backed operator attestation for the two unclearable 020F items.

Two activation preconditions cannot be machine-verified OFFLINE and therefore stay
``manual_review_required`` (BLOCKING) in :mod:`cosmosiq_service.activation`:

* ``live_source_health`` -- a REAL live-source-health fetch confirms the sources are reachable
  and fresh;
* ``operator_shadow_validation`` -- a completed operator SHADOW-validation run (020D) is reviewed.

This module lets an OPERATOR ATTEST that they reviewed the REAL persisted evidence for each --
and, crucially, lets a VERIFIER INDEPENDENTLY confirm that real, persisted evidence actually backs
the attestation before either item is allowed to clear. The honesty invariant is unforgiving and
mirrors the acceptance discipline of :mod:`reality_mesh.investment_diligence` /
:mod:`reality_mesh.accepted_universe`:

* an attestation is the OPERATOR's decision, NEVER a data claim -- nothing auto-attests, no field
  is auto-filled; ``reviewed_by`` is REQUIRED;
* an attestation NEVER clears an item on its own. The verifier RE-READS the persisted store (the
  real run + its persisted events + timestamps) and confirms the evidence -- NOT the attestation's
  word. A LiveSourceHealthAttestation naming a non-existent / unhealthy / stale run, or a
  ShadowValidationAttestation with too few runs / too short a window / a missing referenced run,
  leaves the item ``manual_review_required`` (BLOCKING). Only real, independently-confirmed
  evidence yields a PASS;
* the store is APPEND-ONLY (correction-not-mutation): a CORRECTION is a NEW record referencing
  ``correction_of``; the original line is byte-unchanged forever;
* there is NO score / rank / rating and NO buy / sell / order / broker / trade field anywhere
  (``assert_no_trade_fields``-clean); no secret is read or persisted.

Clearing these two items does NOT promote to production. Production ALSO requires the (untouched)
``read_operator_signoff`` file-approval and a valid recorded operator approval, exactly as before.
With NO attestations recorded (the default OFFLINE posture) both items stay BLOCKING and prod-check
still REFUSES production and lands shadow -- byte-unchanged from before this module existed.

Deterministic (content-derived ids; every ``now`` is injected; the freshness / window checks read
the PERSISTED run timestamps, never a wall clock), OFFLINE, stdlib-only, Python 3.9. No network on
import.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from cosmosiq_service.activation import ChecklistStatus
from reality_mesh.adapters.fmp_live import FMP_LIVE_ADAPTER_ID
from reality_mesh.adapters.sec_edgar_live import SEC_EDGAR_LIVE_ADAPTER_ID
from reality_mesh.stores import AppendOnlyStore, EventStore, RunStore
from reality_mesh.validation import assert_no_trade_fields

__all__ = [
    "LIVE_SOURCE_HEALTH_ATTESTATION_SCHEMA",
    "SHADOW_VALIDATION_ATTESTATION_SCHEMA",
    "LIVE_SOURCE_HEALTH_ITEM",
    "SHADOW_VALIDATION_ITEM",
    "SHADOW_MIN_RUNS",
    "SHADOW_MIN_DAYS",
    "DEFAULT_LIVE_SOURCE_MIN_FRESHNESS",
    "LIVE_SOURCE_EVIDENCE",
    "LIVE_SOURCE_ADAPTER_IDS",
    "AttestationCheckResult",
    "LiveSourceHealthAttestation",
    "ShadowValidationAttestation",
    "OperatorAttestationStore",
    "attestation_id_for",
    "record_live_source_health_attestation",
    "record_shadow_validation_attestation",
    "latest_live_source_health_attestation",
    "latest_shadow_validation_attestation",
    "verify_live_source_health",
    "verify_shadow_validation",
    "attestation_activation_status",
]

# The two schema tokens double as the store's record-type discriminator (one JSONL, two shapes).
LIVE_SOURCE_HEALTH_ATTESTATION_SCHEMA = "live-source-health-attestation.1"
SHADOW_VALIDATION_ATTESTATION_SCHEMA = "shadow-validation-attestation.1"

# The 020F checklist item ids these attestations may clear (and NOTHING else).
LIVE_SOURCE_HEALTH_ITEM = "live_source_health"
SHADOW_VALIDATION_ITEM = "operator_shadow_validation"

# DEFENSIBLE named defaults for a genuine shadow / paper observation window. The operator may pass
# STRICTER values; the verifier never goes below "real evidence backs it".
#   * >= 3 DISTINCT persisted runs (a single refresh is not a window), and
#   * spanning >= 2 DISTINCT calendar days (a window is not one afternoon of ticks).
SHADOW_MIN_RUNS = 3
SHADOW_MIN_DAYS = 2

# A reviewed live run must be no older than this vs the injected ``now`` to count as "fresh".
DEFAULT_LIVE_SOURCE_MIN_FRESHNESS = timedelta(hours=48)

# adapter_id -> (the event source_id, the source_authority) a REAL live run of that source stamps
# on its PERSISTED events (see reality_mesh.adapters.*_live + reality_mesh.live_pulse). This is the
# independent, re-readable evidence the verifier confirms: it re-reads the EventStore and requires
# a real persisted event carrying exactly this (source_id, authority) before a source counts as
# healthy -- the attestation's own word is never trusted.
LIVE_SOURCE_EVIDENCE: Dict[str, Tuple[str, str]] = {
    SEC_EDGAR_LIVE_ADAPTER_ID: ("sec.edgar", "canonical"),      # SEC filings -> canonical tier
    FMP_LIVE_ADAPTER_ID: ("fmp.live", "convenience"),           # FMP financials -> convenience tier
}
LIVE_SOURCE_ADAPTER_IDS: Tuple[str, ...] = tuple(LIVE_SOURCE_EVIDENCE)


# --------------------------------------------------------------------------- #
# The check-result shape handed to evaluate_activation (duck-types CheckResult) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AttestationCheckResult:
    """One verifier outcome -- a name, a closed status, honest details, an evidence path.

    Duck-types :class:`cosmosiq_service.activation.CheckResult` (``evaluate_activation`` reads only
    ``.status`` / ``.details`` / ``.evidence_path``). ``status`` is ``pass`` ONLY when real,
    independently-confirmed persisted evidence backs the attestation; otherwise it is
    ``manual_review_required`` (BLOCKING) with an honest reason.
    """

    name: str
    status: str
    details: Tuple[str, ...] = field(default_factory=tuple)
    evidence_path: str = ""


# --------------------------------------------------------------------------- #
# The two operator-attributed, append-only attestation records                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LiveSourceHealthAttestation:
    """One OPERATOR attestation that they reviewed a REAL live run's source health.

    ``run_id`` is the REAL persisted live run reviewed; ``sources_reviewed`` are the live adapter
    ids (+ implied statuses) the operator confirms healthy; ``reviewed_by`` (REQUIRED) is the
    operator; ``reviewed_at`` is the injected instant. It records a CLAIM -- the verifier
    independently re-reads the persisted run/events to confirm it. NO score / trade field.
    """

    attestation_id: str = ""
    run_id: str = ""
    sources_reviewed: Tuple[str, ...] = field(default_factory=tuple)
    reviewed_by: str = ""
    reviewed_at: str = ""
    statement: str = ""
    schema_version: str = LIVE_SOURCE_HEALTH_ATTESTATION_SCHEMA
    correction_of: str = ""

    def __post_init__(self) -> None:
        for name in ("attestation_id", "run_id", "reviewed_by", "reviewed_at"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "LiveSourceHealthAttestation.{0} is required and must be non-empty -- an "
                    "attestation names the REAL run reviewed and the operator who reviewed it; "
                    "nothing is auto-filled".format(name))
        if not tuple(s for s in (self.sources_reviewed or ()) if str(s or "").strip()):
            raise ValueError(
                "LiveSourceHealthAttestation.sources_reviewed is required and must be non-empty "
                "-- the operator names which live sources they confirm healthy")


@dataclass(frozen=True)
class ShadowValidationAttestation:
    """One OPERATOR attestation that they reviewed a REAL shadow / paper observation window.

    The window is named EITHER by ``window_run_ids`` (the REAL persisted runs reviewed) OR by
    (``window_start``, ``window_end``); at least one form is REQUIRED. ``reviewed_by`` (REQUIRED)
    is the operator; ``reviewed_at`` is the injected instant. The verifier independently confirms
    the runs are REAL persisted runs forming a genuine window. NO score / trade field.
    """

    attestation_id: str = ""
    window_run_ids: Tuple[str, ...] = field(default_factory=tuple)
    window_start: str = ""
    window_end: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
    statement: str = ""
    schema_version: str = SHADOW_VALIDATION_ATTESTATION_SCHEMA
    correction_of: str = ""

    def __post_init__(self) -> None:
        for name in ("attestation_id", "reviewed_by", "reviewed_at"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "ShadowValidationAttestation.{0} is required and must be non-empty -- an "
                    "attestation names the operator who reviewed the window; nothing is "
                    "auto-filled".format(name))
        has_runs = bool(tuple(r for r in (self.window_run_ids or ()) if str(r or "").strip()))
        has_window = bool(str(self.window_start or "").strip()
                          and str(self.window_end or "").strip())
        if not has_runs and not has_window:
            raise ValueError(
                "ShadowValidationAttestation requires a window: either window_run_ids (the REAL "
                "persisted runs reviewed) OR both window_start and window_end")


# --------------------------------------------------------------------------- #
# Deterministic content-derived id                                              #
# --------------------------------------------------------------------------- #
def attestation_id_for(kind: str, *, subject: str, reviewed_by: str, reviewed_at: str,
                       statement: str = "", correction_of: str = "") -> str:
    """A deterministic, content-derived attestation id (no wall-clock, order-stable).

    ``kind`` is the short attestation kind (``live-source-health`` / ``shadow-validation``);
    ``subject`` folds in what was reviewed (the run id / the window). A byte-identical re-record is
    idempotent by id; a later CORRECTION (different ``correction_of``) never collides.
    """
    token = "\x1f".join([
        str(kind or "").strip(),
        str(subject or "").strip(),
        str(reviewed_by or "").strip(),
        str(reviewed_at or "").strip(),
        str(statement or "").strip(),
        str(correction_of or "").strip(),
    ])
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return "attest:{0}:{1}".format(str(kind or "").strip(), digest)


# --------------------------------------------------------------------------- #
# APPEND-ONLY store (correction-not-mutation), one JSONL for both shapes         #
# --------------------------------------------------------------------------- #
class OperatorAttestationStore(AppendOnlyStore):
    """The append-only log of operator attestations -> ``operator_attestations.jsonl``.

    Composes :class:`~reality_mesh.stores.AppendOnlyStore`: NO update / delete / in-place mutation,
    and the base's credential / trade-field write refusal applies. Holds BOTH attestation shapes in
    one log; :meth:`_reconstruct` dispatches on the payload ``schema_version``. A CORRECTION is a
    NEW record whose ``correction_of`` references the superseded id -- the original line is
    byte-unchanged forever.
    """

    filename = "operator_attestations.jsonl"
    record_cls = None          # heterogeneous log; reconstruct dispatches on schema_version
    id_field = "attestation_id"
    timestamp_field = "reviewed_at"

    _TYPE_BY_SCHEMA = {
        LIVE_SOURCE_HEALTH_ATTESTATION_SCHEMA: LiveSourceHealthAttestation,
        SHADOW_VALIDATION_ATTESTATION_SCHEMA: ShadowValidationAttestation,
    }

    def _reconstruct(self, record):
        payload = {
            key: (tuple(value) if isinstance(value, list) else value)
            for key, value in dict(record.get("payload", {})).items()}
        cls = self._TYPE_BY_SCHEMA.get(payload.get("schema_version"))
        if cls is None:
            return payload
        return cls(**payload)

    def record(self, attestation) -> str:
        """Append ONE attestation append-only; idempotent when byte-identical already present."""
        if attestation in self.read_all():
            return attestation.attestation_id
        return self.append(attestation)

    def live_source_health_records(self) -> Tuple[LiveSourceHealthAttestation, ...]:
        return tuple(r for r in self.read_all()
                     if isinstance(r, LiveSourceHealthAttestation))

    def shadow_validation_records(self) -> Tuple[ShadowValidationAttestation, ...]:
        return tuple(r for r in self.read_all()
                     if isinstance(r, ShadowValidationAttestation))


def _latest_live(records: Tuple[LiveSourceHealthAttestation, ...]):
    superseded = {str(r.correction_of).strip() for r in records if str(r.correction_of).strip()}
    live = [r for r in records if r.attestation_id not in superseded]
    return live[-1] if live else None


def latest_live_source_health_attestation(store_dir: str):
    """The newest NON-SUPERSEDED :class:`LiveSourceHealthAttestation`, or None."""
    return _latest_live(OperatorAttestationStore(store_dir).live_source_health_records())


def latest_shadow_validation_attestation(store_dir: str):
    """The newest NON-SUPERSEDED :class:`ShadowValidationAttestation`, or None."""
    records = OperatorAttestationStore(store_dir).shadow_validation_records()
    superseded = {str(r.correction_of).strip() for r in records if str(r.correction_of).strip()}
    live = [r for r in records if r.attestation_id not in superseded]
    return live[-1] if live else None


# --------------------------------------------------------------------------- #
# The producers -- validate the referenced run(s) exist BEFORE writing           #
# --------------------------------------------------------------------------- #
def _norm_seq(values) -> Tuple[str, ...]:
    return tuple(str(v or "").strip() for v in (values or ()) if str(v or "").strip())


def record_live_source_health_attestation(
        store_dir: str, *, run_id: str, sources_reviewed, reviewed_by: str, reviewed_at: str,
        statement: str = "", correction_of: str = "") -> LiveSourceHealthAttestation:
    """RECORD one operator live-source-health attestation append-only. Refuses an unreal run.

    VALIDATES before persisting (raising ``ValueError`` -- nothing written -- on a gap): a non-empty
    ``store_dir`` / ``reviewed_by`` / ``reviewed_at`` / ``run_id``; ``run_id`` names a REAL
    persisted run in the RunStore (an attestation may not name a run that does not exist);
    ``correction_of`` (if given) references an existing persisted attestation. The verifier -- NOT
    this producer -- independently confirms the sources actually reported healthy + fresh.
    """
    if not str(store_dir or "").strip():
        raise ValueError("record_live_source_health_attestation requires a non-empty store_dir")
    run = str(run_id or "").strip()
    reviewer = str(reviewed_by or "").strip()
    reviewed = str(reviewed_at or "").strip()
    sources = _norm_seq(sources_reviewed)
    correction = str(correction_of or "").strip()
    if not reviewer:
        raise ValueError(
            "reviewed_by is required -- an attestation names the operator who reviewed the run; "
            "nothing attests on its own")
    if not reviewed:
        raise ValueError(
            "reviewed_at is required (an injected instant) -- it is never a wall-clock read")
    if not run:
        raise ValueError("run_id is required -- the REAL live run reviewed")
    if not sources:
        raise ValueError("at least one reviewed source is required (e.g. {0})".format(
            ", ".join(LIVE_SOURCE_ADAPTER_IDS)))
    if not RunStore(store_dir).query(run_id=run):
        raise ValueError(
            "refusing to attest: run_id {0!r} is NOT a persisted run in this store -- an "
            "attestation may never name a run that does not exist. Nothing written.".format(run))
    if correction and correction not in {
            r.attestation_id
            for r in OperatorAttestationStore(store_dir).live_source_health_records()}:
        raise ValueError(
            "correction_of {0!r} references no persisted live-source-health attestation -- a "
            "correction supersedes a REAL prior record. Nothing written.".format(correction))

    attestation = LiveSourceHealthAttestation(
        attestation_id=attestation_id_for(
            "live-source-health", subject="{0}|{1}".format(run, ",".join(sources)),
            reviewed_by=reviewer, reviewed_at=reviewed, statement=statement,
            correction_of=correction),
        run_id=run, sources_reviewed=sources, reviewed_by=reviewer, reviewed_at=reviewed,
        statement=str(statement or "").strip(), correction_of=correction)
    OperatorAttestationStore(store_dir).record(attestation)
    return attestation


def record_shadow_validation_attestation(
        store_dir: str, *, reviewed_by: str, reviewed_at: str, window_run_ids=(),
        window_start: str = "", window_end: str = "", statement: str = "",
        correction_of: str = "") -> ShadowValidationAttestation:
    """RECORD one operator shadow-validation attestation append-only. Refuses an unreal window.

    VALIDATES before persisting (raising ``ValueError`` -- nothing written): non-empty
    ``store_dir`` / ``reviewed_by`` / ``reviewed_at``; a window given as ``window_run_ids`` (each a
    REAL persisted run) OR (``window_start``, ``window_end``) that at least one persisted run falls
    in; ``correction_of`` (if given) references an existing persisted attestation. The verifier
    independently confirms the window is genuine (enough distinct runs over enough distinct days).
    """
    if not str(store_dir or "").strip():
        raise ValueError("record_shadow_validation_attestation requires a non-empty store_dir")
    reviewer = str(reviewed_by or "").strip()
    reviewed = str(reviewed_at or "").strip()
    run_ids = _norm_seq(window_run_ids)
    start = str(window_start or "").strip()
    end = str(window_end or "").strip()
    correction = str(correction_of or "").strip()
    if not reviewer:
        raise ValueError(
            "reviewed_by is required -- an attestation names the operator who reviewed the "
            "window; nothing attests on its own")
    if not reviewed:
        raise ValueError(
            "reviewed_at is required (an injected instant) -- it is never a wall-clock read")

    store = RunStore(store_dir)
    if run_ids:
        missing = tuple(rid for rid in run_ids if not store.query(run_id=rid))
        if missing:
            raise ValueError(
                "refusing to attest: run_id(s) {0} are NOT persisted runs in this store -- an "
                "attestation may never name a run that does not exist. Nothing written.".format(
                    ", ".join(missing)))
    elif start and end:
        if not store.query(window=(start, end)):
            raise ValueError(
                "refusing to attest: no persisted run falls in the window {0}..{1} -- an "
                "attestation may not name an empty window. Nothing written.".format(start, end))
    else:
        raise ValueError(
            "a window is required: either window_run_ids (the REAL persisted runs reviewed) OR "
            "both window_start and window_end")
    if correction and correction not in {
            r.attestation_id
            for r in OperatorAttestationStore(store_dir).shadow_validation_records()}:
        raise ValueError(
            "correction_of {0!r} references no persisted shadow-validation attestation -- a "
            "correction supersedes a REAL prior record. Nothing written.".format(correction))

    subject = "runs:{0}".format(",".join(run_ids)) if run_ids else "window:{0}..{1}".format(
        start, end)
    attestation = ShadowValidationAttestation(
        attestation_id=attestation_id_for(
            "shadow-validation", subject=subject, reviewed_by=reviewer, reviewed_at=reviewed,
            statement=statement, correction_of=correction),
        window_run_ids=run_ids, window_start=start, window_end=end,
        reviewed_by=reviewer, reviewed_at=reviewed,
        statement=str(statement or "").strip(), correction_of=correction)
    OperatorAttestationStore(store_dir).record(attestation)
    return attestation


# --------------------------------------------------------------------------- #
# Timestamp helpers (parse the PERSISTED / injected instants; never a wall clock)#
# --------------------------------------------------------------------------- #
def _parse_instant(text: str) -> Optional[datetime]:
    """Parse an RFC3339-ish instant to a ``datetime``, or None (a parse fault is an honest gap)."""
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _calendar_day(text: str) -> str:
    """The DISTINCT calendar-day key for an instant (the parsed UTC date, else the YYYY-MM-DD)."""
    parsed = _parse_instant(text)
    if parsed is not None:
        return parsed.date().isoformat()
    raw = str(text or "").strip()
    return raw[:10] if len(raw) >= 10 else ""


# --------------------------------------------------------------------------- #
# Independent re-read of the PERSISTED evidence (the honesty core)               #
# --------------------------------------------------------------------------- #
def _independently_healthy_live_sources(store_dir: str, run_id: str) -> Dict[str, int]:
    """RE-READ the persisted EventStore for ``run_id``; the live sources it PROVES reported.

    An adapter counts as healthy ONLY when the persisted event_store holds >= 1 real event carrying
    exactly its expected (source_id, source_authority) -- the attestation's word is never trusted.
    Returns ``{adapter_id: event_count}`` for every source independently confirmed.
    """
    events = EventStore(store_dir).query(run_id=run_id)
    confirmed: Dict[str, int] = {}
    for adapter_id, (source_id, authority) in LIVE_SOURCE_EVIDENCE.items():
        count = sum(1 for event in events
                    if str(getattr(event, "source_id", "")) == source_id
                    and str(getattr(event, "source_authority", "")) == authority)
        if count:
            confirmed[adapter_id] = count
    return confirmed


def _manual(item_id: str, reason: str) -> AttestationCheckResult:
    return AttestationCheckResult(item_id, ChecklistStatus.MANUAL_REVIEW_REQUIRED, (reason,))


# --------------------------------------------------------------------------- #
# The verifiers -- PASS only on real, independently-confirmed persisted evidence #
# --------------------------------------------------------------------------- #
def verify_live_source_health(store_dir: str, *, now: str,
                              min_freshness: timedelta = DEFAULT_LIVE_SOURCE_MIN_FRESHNESS
                              ) -> AttestationCheckResult:
    """INDEPENDENTLY verify the latest live-source-health attestation against persisted evidence.

    PASSES ONLY when: a latest attestation exists with ``reviewed_by`` set; its ``run_id`` is a REAL
    persisted run; RE-READING that run's persisted events proves every attested source actually
    reported healthy (a real event with the source's expected (source_id, authority)); and the run
    is FRESH (age <= ``min_freshness`` vs the injected ``now``). Any gap -- no attestation / missing
    run / unhealthy or unbacked source / stale / unparseable instant -> ``manual_review_required``
    (BLOCKING), never a pass. Deterministic: ``now`` is injected; the run's own persisted
    ``started_at`` drives freshness (no wall clock).
    """
    if not str(now).strip():
        raise ValueError("verify_live_source_health requires an injected 'now' instant")
    attestation = latest_live_source_health_attestation(store_dir)
    if attestation is None:
        return _manual(
            LIVE_SOURCE_HEALTH_ITEM,
            "no LiveSourceHealthAttestation recorded -- live_source_health cannot be cleared from "
            "code and stays manual_review_required (blocking).")
    if not str(attestation.reviewed_by).strip():
        return _manual(
            LIVE_SOURCE_HEALTH_ITEM,
            "the attestation has no reviewed_by operator -- refusing (blocking).")

    runs = RunStore(store_dir).query(run_id=attestation.run_id)
    if not runs:
        return _manual(
            LIVE_SOURCE_HEALTH_ITEM,
            "attestation names run_id {0!r}, which is NOT a persisted run -- refusing to clear on "
            "the attestation's word (blocking).".format(attestation.run_id))
    run = runs[-1]

    confirmed = _independently_healthy_live_sources(store_dir, attestation.run_id)
    if not confirmed:
        return _manual(
            LIVE_SOURCE_HEALTH_ITEM,
            "run {0!r} persisted NO real live-source events -- no live source independently "
            "reported healthy; refusing (blocking).".format(attestation.run_id))
    attested = _norm_seq(attestation.sources_reviewed)
    unbacked = tuple(s for s in attested if s not in confirmed)
    if unbacked:
        return _manual(
            LIVE_SOURCE_HEALTH_ITEM,
            "attested source(s) {0} are NOT backed by real persisted healthy evidence in run "
            "{1!r} (confirmed healthy: {2}) -- refusing (blocking).".format(
                ", ".join(unbacked), attestation.run_id,
                ", ".join(sorted(confirmed)) or "none"))

    run_dt = _parse_instant(getattr(run, "started_at", ""))
    now_dt = _parse_instant(now)
    if run_dt is None or now_dt is None:
        return _manual(
            LIVE_SOURCE_HEALTH_ITEM,
            "could not parse the run/now instant to check freshness -- refusing (blocking).")
    age = now_dt - run_dt
    if age > min_freshness:
        return _manual(
            LIVE_SOURCE_HEALTH_ITEM,
            "the reviewed live run {0!r} is STALE (age {1} exceeds min freshness {2}) -- refusing "
            "(blocking).".format(attestation.run_id, age, min_freshness))

    detail = ("live_source_health CLEARED by evidence-backed attestation {0} (reviewed_by {1}): "
              "run {2!r} is a real persisted run whose live source(s) {3} independently reported "
              "healthy in the persisted event store, and it is fresh (age {4} <= {5}).".format(
                  attestation.attestation_id, attestation.reviewed_by, attestation.run_id,
                  ", ".join("{0}({1} ev)".format(k, confirmed[k]) for k in sorted(confirmed)),
                  age, min_freshness))
    return AttestationCheckResult(
        LIVE_SOURCE_HEALTH_ITEM, ChecklistStatus.PASS, (detail,),
        evidence_path=OperatorAttestationStore(store_dir).path)


def verify_shadow_validation(store_dir: str, *, now: str, min_runs: int = SHADOW_MIN_RUNS,
                             min_days: int = SHADOW_MIN_DAYS) -> AttestationCheckResult:
    """INDEPENDENTLY verify the latest shadow-validation attestation against persisted evidence.

    PASSES ONLY when: a latest attestation exists with ``reviewed_by`` set; the referenced runs
    (``window_run_ids``, or every run in the ``window_start``..``window_end`` range) are REAL
    persisted runs; they form a genuine window -- >= ``min_runs`` DISTINCT runs spanning >=
    ``min_days`` DISTINCT calendar days (from the runs' persisted timestamps). Too few runs / too
    short a span / a missing referenced run / no attestation -> ``manual_review_required``
    (BLOCKING), never a pass. Deterministic: the window is measured from PERSISTED run timestamps,
    never a wall clock (``now`` is accepted for interface symmetry / determinism).
    """
    if not str(now).strip():
        raise ValueError("verify_shadow_validation requires an injected 'now' instant")
    attestation = latest_shadow_validation_attestation(store_dir)
    if attestation is None:
        return _manual(
            SHADOW_VALIDATION_ITEM,
            "no ShadowValidationAttestation recorded -- operator_shadow_validation cannot be "
            "cleared from code and stays manual_review_required (blocking).")
    if not str(attestation.reviewed_by).strip():
        return _manual(
            SHADOW_VALIDATION_ITEM,
            "the attestation has no reviewed_by operator -- refusing (blocking).")

    store = RunStore(store_dir)
    resolved: List[object] = []
    run_ids = _norm_seq(attestation.window_run_ids)
    if run_ids:
        missing: List[str] = []
        for run_id in run_ids:
            found = store.query(run_id=run_id)
            if found:
                resolved.append(found[-1])
            else:
                missing.append(run_id)
        if missing:
            return _manual(
                SHADOW_VALIDATION_ITEM,
                "attestation references run_id(s) {0} that are NOT persisted runs -- refusing to "
                "clear on the attestation's word (blocking).".format(", ".join(missing)))
    else:
        resolved = list(store.query(window=(attestation.window_start, attestation.window_end)))
        if not resolved:
            return _manual(
                SHADOW_VALIDATION_ITEM,
                "no persisted run falls in the attested window {0}..{1} -- refusing "
                "(blocking).".format(attestation.window_start, attestation.window_end))

    distinct_run_ids = {str(getattr(r, "run_id", "")) for r in resolved if getattr(r, "run_id", "")}
    if len(distinct_run_ids) < min_runs:
        return _manual(
            SHADOW_VALIDATION_ITEM,
            "only {0} distinct persisted run(s) in the reviewed window; a genuine window needs >= "
            "{1} -- refusing (blocking).".format(len(distinct_run_ids), min_runs))

    days = {d for d in (_calendar_day(getattr(r, "started_at", "")) for r in resolved) if d}
    if len(days) < min_days:
        return _manual(
            SHADOW_VALIDATION_ITEM,
            "the reviewed runs span only {0} distinct calendar day(s); a genuine window needs >= "
            "{1} -- refusing (blocking).".format(len(days), min_days))

    detail = ("operator_shadow_validation CLEARED by evidence-backed attestation {0} (reviewed_by "
              "{1}): {2} distinct persisted runs spanning {3} distinct calendar days ({4}) meet "
              "the >= {5} runs / >= {6} days window bar -- a genuine paper/observation window."
              .format(attestation.attestation_id, attestation.reviewed_by, len(distinct_run_ids),
                      len(days), ", ".join(sorted(days)), min_runs, min_days))
    return AttestationCheckResult(
        SHADOW_VALIDATION_ITEM, ChecklistStatus.PASS, (detail,),
        evidence_path=OperatorAttestationStore(store_dir).path)


# --------------------------------------------------------------------------- #
# A read-only status surface (no trade affordance; labels + reasons only)        #
# --------------------------------------------------------------------------- #
def attestation_activation_status(store_dir: str, *, now: str
                                  ) -> Tuple[AttestationCheckResult, AttestationCheckResult]:
    """The read-only verified status of the two attestation-clearable items, ``(live, shadow)``.

    A cockpit / ops surface can render each item's status + honest reason. It is READ-ONLY: it runs
    the verifiers, clears nothing, and carries NO trade / order affordance.
    """
    return (verify_live_source_health(store_dir, now=now),
            verify_shadow_validation(store_dir, now=now))


# --------------------------------------------------------------------------- #
# Construction-time guards: the contracts carry NO trade / score field           #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(LiveSourceHealthAttestation)
assert_no_trade_fields(ShadowValidationAttestation)
assert_no_trade_fields(AttestationCheckResult)
