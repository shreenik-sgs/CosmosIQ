"""Source-adapter contracts -- fixture-backed stubs, NO network.

IMPORTANT: Live source clients (real SEC EDGAR / FMP / yfinance HTTP calls) are
OUT OF SCOPE for IMPLEMENTATION-009A. Every adapter here is a *fixture-backed
stub*: its data is dependency-injected as a plain ``fixtures`` dict at
construction time. There is NO network access, NO URL, NO API key, and NO secret
read anywhere in this module. The adapters exist to pin the *contract* -- how a
fetch turns injected data into normalized evidence records with the correct
default authority/class, and how partial coverage and unknown queries are
surfaced -- so a future live client can drop in behind the same interface.

A ``query`` is a plain dict, e.g.
``{"subject": "IREN-8K-2026Q2", "ticker": "IREN", "cik": "0001878848",
   "fields": ("contract_value", "counterparty")}``.
``fields`` (optional) lists the fields the caller needs; if the fixture lacks any
of them the result is marked ``complete=False`` with a coverage warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from eios_core.canonical_objects import CanonicalObject
from eios_core.ids import iso_from_epoch
from eios_core.provenance import make_provenance

from .source_model import EvidenceSource
from .evidence_records import (
    NormalizedEvidenceRecord,
    make_raw_evidence_record,
    make_normalized_evidence_record,
)


@dataclass(frozen=True)
class AdapterResult:
    """The outcome of one adapter fetch. ``complete=False`` means partial."""

    source: Optional[EvidenceSource] = None
    records: Tuple[NormalizedEvidenceRecord, ...] = ()
    warnings: Tuple[str, ...] = ()
    errors: Tuple[str, ...] = ()
    coverage_window: str = ""
    complete: bool = True
    provenance: Any = None


class SourceAdapter:
    """Abstract base for a source adapter.

    Live clients are OUT OF SCOPE for IMPLEMENTATION-009A -- concrete subclasses
    are fixture-backed stubs constructed with a dependency-injected ``fixtures``
    dict. Subclasses MUST NOT open sockets, issue HTTP requests, or read secrets.
    """

    # Overridden per provider.
    provider = ""
    source_class = ""

    def __init__(self, fixtures: Optional[Dict[str, Any]] = None) -> None:
        # Injected local data only -- never a network client, never a key.
        self.fixtures: Dict[str, Any] = dict(fixtures or {})

    def fetch(self, query: Dict[str, Any]) -> AdapterResult:
        raise NotImplementedError("SourceAdapter is abstract; use a concrete stub")


def _run_fetch(
    provider: str,
    source_class: str,
    fixtures: Dict[str, Any],
    query: Dict[str, Any],
    *,
    actor: str,
    now: float,
) -> AdapterResult:
    """Shared fixture-driven fetch logic used by every stub adapter."""
    from .source_model import authority_for_source_class

    authority = authority_for_source_class(source_class)
    created_at = iso_from_epoch(now)
    subject = query.get("subject", "")

    if not subject:
        prov = make_provenance(actor=actor, created_at=created_at, sources=())
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("query missing 'subject'",),
            coverage_window=query.get("coverage_window", ""),
            complete=False,
            provenance=prov,
        )

    fixture = fixtures.get(subject)
    if fixture is None:
        prov = make_provenance(actor=actor, created_at=created_at, sources=())
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=(
                "no fixture for subject '{0}' in {1} adapter".format(subject, provider),
            ),
            coverage_window=query.get("coverage_window", ""),
            complete=False,
            provenance=prov,
        )

    retrieved_at = fixture.get("retrieved_at", created_at)
    as_of = fixture.get("as_of", "")
    source = EvidenceSource(
        source_name=fixture.get("source_name", provider),
        source_authority=authority,
        source_class=source_class,
        source_ref=fixture.get("source_ref", ""),
        provider=provider,
        retrieved_at=retrieved_at,
        as_of=as_of,
        license_note=fixture.get("license_note", ""),
        reliability=fixture.get("reliability"),
    )

    raw = make_raw_evidence_record(
        source,
        subject=subject,
        ticker=query.get("ticker", fixture.get("ticker", "")),
        cik=query.get("cik", fixture.get("cik", "")),
        raw_type=fixture.get("raw_type", "unknown"),
        raw_payload=dict(fixture.get("payload", {})),
        retrieved_at=retrieved_at,
        as_of=as_of,
        actor=actor,
        now=now,
    )

    extracted = dict(fixture.get("extracted_fields", {}))

    # Partial-coverage detection: any requested field the fixture lacks.
    requested = tuple(query.get("fields", ()))
    missing = [f for f in requested if f not in extracted]
    warnings = []
    complete = True
    if missing:
        complete = False
        warnings.append(
            "partial coverage from {0}: missing fields {1} for subject '{2}'".format(
                provider, sorted(missing), subject
            )
        )

    normalized = make_normalized_evidence_record(
        raw,
        normalized_type=fixture.get("normalized_type", raw.raw_type),
        extracted_fields=extracted,
        event_date=fixture.get("event_date", ""),
        period_end=fixture.get("period_end", ""),
        evidence_quality=float(fixture.get("evidence_quality", 0.5)),
        confidence=float(fixture.get("confidence", 0.5)),
        warnings=tuple(warnings),
        actor=actor,
        now=now,
    )

    prov = make_provenance(
        actor=actor,
        created_at=created_at,
        sources=(normalized.ref("NormalizedEvidenceRecord"),),
    )
    return AdapterResult(
        source=source,
        records=(normalized,),
        warnings=tuple(warnings),
        errors=(),
        coverage_window=fixture.get("coverage_window", query.get("coverage_window", "")),
        complete=complete,
        provenance=prov,
    )


class SecEdgarAdapter(SourceAdapter):
    """Fixture-backed stub for SEC EDGAR (official_filing -> canonical)."""

    provider = "sec_edgar"
    source_class = "official_filing"

    def fetch(self, query: Dict[str, Any]) -> AdapterResult:
        now = float(query.get("now", 0.0))
        actor = query.get("actor", "evidence-ingestion")
        return _run_fetch(
            self.provider, self.source_class, self.fixtures, query, actor=actor, now=now
        )


class FmpAdapter(SourceAdapter):
    """Fixture-backed stub for Financial Modeling Prep (paid_api -> convenience)."""

    provider = "fmp"
    source_class = "paid_api"

    def fetch(self, query: Dict[str, Any]) -> AdapterResult:
        now = float(query.get("now", 0.0))
        actor = query.get("actor", "evidence-ingestion")
        return _run_fetch(
            self.provider, self.source_class, self.fixtures, query, actor=actor, now=now
        )


class YFinanceAdapter(SourceAdapter):
    """Fixture-backed stub for yfinance (free_api -> fallback)."""

    provider = "yfinance"
    source_class = "free_api"

    def fetch(self, query: Dict[str, Any]) -> AdapterResult:
        now = float(query.get("now", 0.0))
        actor = query.get("actor", "evidence-ingestion")
        return _run_fetch(
            self.provider, self.source_class, self.fixtures, query, actor=actor, now=now
        )
