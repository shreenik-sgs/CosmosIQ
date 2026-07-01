"""Evidence records -- the provenance-bearing canonical objects of ingestion.

Two record kinds sit strictly *below* the Tattva Observation:

* ``RawEvidenceRecord`` -- the content-addressed capture of one raw payload from
  a source (a filing dict, an API row). Its ``checksum`` (== its id) is a
  deterministic hash of the source + type + subject + payload, so the same bytes
  always yield the same record id.
* ``NormalizedEvidenceRecord`` -- the cleaned, field-extracted view of a raw
  record. It binds the raw record via ``provenance.sources`` and carries the
  source authority/class forward so downstream conflict resolution and the
  observation mapper can reason about trust without re-deriving it.

Neither record makes an investment judgement. They are evidence, not assessment.
Both are frozen ``CanonicalObject`` subclasses; construction never mutates an
upstream object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from eios_core.canonical_objects import CanonicalObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

from .source_model import EvidenceSource


@dataclass(frozen=True)
class RawEvidenceRecord(CanonicalObject):
    """Content-addressed capture of one raw payload from a source."""

    source: Optional[EvidenceSource] = None
    subject: str = ""
    ticker: str = ""
    cik: str = ""
    raw_type: str = ""
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    payload_ref: str = ""
    retrieved_at: str = ""
    as_of: str = ""
    checksum: str = ""

    @property
    def record_id(self) -> str:
        return self.id


@dataclass(frozen=True)
class NormalizedEvidenceRecord(CanonicalObject):
    """Cleaned, field-extracted view of a raw record, binding it via provenance."""

    source: Optional[EvidenceSource] = None
    source_record_ref: Any = None
    normalized_type: str = ""
    subject: str = ""
    ticker: str = ""
    cik: str = ""
    event_date: str = ""
    period_end: str = ""
    extracted_fields: Dict[str, Any] = field(default_factory=dict)
    evidence_quality: float = 0.0
    source_authority: str = ""
    source_class: str = ""
    confidence: float = 0.0
    warnings: Tuple[str, ...] = ()

    @property
    def record_id(self) -> str:
        return self.id


def make_raw_evidence_record(
    source: EvidenceSource,
    *,
    subject: str,
    ticker: str = "",
    cik: str = "",
    raw_type: str,
    raw_payload: Optional[Dict[str, Any]] = None,
    payload_ref: str = "",
    retrieved_at: str,
    as_of: str,
    actor: str = "evidence-ingestion",
    now: float,
) -> RawEvidenceRecord:
    """Build a content-addressed ``RawEvidenceRecord`` from a source payload.

    The id/checksum is a deterministic hash over the source name, raw type,
    subject, and the sorted payload items -- identical bytes yield an identical
    id (supporting deterministic replay); different payloads yield different ids.
    """
    payload = dict(raw_payload or {})
    checksum = stable_id(
        "RAW",
        source.source_name,
        raw_type,
        subject,
        str(sorted(payload.items())),
    )
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=())
    return RawEvidenceRecord(
        id=checksum,
        version=1,
        provenance=prov,
        source=source,
        subject=subject,
        ticker=ticker,
        cik=cik,
        raw_type=raw_type,
        raw_payload=payload,
        payload_ref=payload_ref,
        retrieved_at=retrieved_at,
        as_of=as_of,
        checksum=checksum,
    )


def make_normalized_evidence_record(
    raw_record: RawEvidenceRecord,
    *,
    normalized_type: str,
    extracted_fields: Dict[str, Any],
    event_date: str = "",
    period_end: str = "",
    evidence_quality: float,
    confidence: float,
    warnings: Tuple[str, ...] = (),
    actor: str = "evidence-ingestion",
    now: float,
) -> NormalizedEvidenceRecord:
    """Normalise a raw record, carrying its source authority/class forward and
    binding the raw record via ``provenance.sources``.
    """
    src = raw_record.source
    prov = make_provenance(
        actor=actor,
        created_at=iso_from_epoch(now),
        sources=(raw_record.ref("RawEvidenceRecord"),),
    )
    nid = stable_id("NORM", raw_record.id, normalized_type)
    return NormalizedEvidenceRecord(
        id=nid,
        version=1,
        provenance=prov,
        source=src,
        source_record_ref=raw_record.ref("RawEvidenceRecord"),
        normalized_type=normalized_type,
        subject=raw_record.subject,
        ticker=raw_record.ticker,
        cik=raw_record.cik,
        event_date=event_date,
        period_end=period_end,
        extracted_fields=dict(extracted_fields),
        evidence_quality=float(evidence_quality),
        source_authority=src.source_authority if src else "",
        source_class=src.source_class if src else "",
        confidence=float(confidence),
        warnings=tuple(warnings),
    )
