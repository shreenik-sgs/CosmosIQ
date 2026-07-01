"""SEC EDGAR / data.sec.gov parsing adapter -- fixture-backed, NO network.

This module turns SEC-shaped JSON -- the ``submissions`` document and the
``companyfacts`` (XBRL) document served by data.sec.gov -- into CANONICAL
evidence records (``official_filing`` -> ``canonical``) behind the accepted
IMPLEMENTATION-009A ingestion contracts. It classifies filing types, and
conservatively flags shelf / ATM / offering *dilution* from filing metadata and
content patterns.

Discipline (matches the 009A layer):

* It performs NO network access, reads NO secrets, holds NO API keys, and has
  NO top-level network import. The parsers take already-loaded ``dict`` input
  (a test loads a local fixture via ``open()``; a live client would inject the
  fetched JSON). See ``sec_client.py`` for the optional, dependency-injected
  live client that is NOT exercised by default tests.
* It makes NO investment judgement and produces NO scoring. Output stays
  evidence records only; downstream ``map_to_observation`` turns them into
  Tattva Observations and nothing else.
* Absent fields become explicit warnings/errors -- never fabricated values.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .source_model import EvidenceSource, authority_for_source_class
from .evidence_records import (
    make_raw_evidence_record,
    make_normalized_evidence_record,
)
from .adapters import AdapterResult


SEC_SOURCE_NAME = "SEC EDGAR"
SEC_PROVIDER = "SEC EDGAR / data.sec.gov"

# High evidence quality: official filings are the canonical primary source.
_SEC_EVIDENCE_QUALITY = 0.9
_SEC_CONFIDENCE = 0.9


def sec_source(
    source_class: str = "official_filing",
    source_ref: str = "",
    as_of: str = "",
    retrieved_at: str = "",
) -> EvidenceSource:
    """Build the canonical ``EvidenceSource`` for an SEC EDGAR record.

    ``source_class`` defaults to ``official_filing`` (-> canonical). Pass
    ``regulatory`` only for a clearly regulatory form; both classes resolve to
    the ``canonical`` authority via ``authority_for_source_class``.
    """
    authority = authority_for_source_class(source_class)
    return EvidenceSource(
        source_name=SEC_SOURCE_NAME,
        source_authority=authority,
        source_class=source_class,
        source_ref=source_ref,
        provider=SEC_PROVIDER,
        retrieved_at=retrieved_at,
        as_of=as_of,
    )


# --------------------------------------------------------------------------- #
# Filing-type classification.                                                  #
# --------------------------------------------------------------------------- #

def classify_form(form: str) -> str:
    """Map an SEC form type to a normalized_type token embedding the form.

    The returned token keeps the discriminating substring (``10-k`` / ``10-q`` /
    ``8-k`` / ``s-3`` / ``424b``) so the mapper's ``_pick_source_type`` routes it
    to the right Tattva source_type without this module reasoning about intent.
    """
    f = str(form or "").strip().upper()
    if f in ("10-K", "10-K/A"):
        return "sec_10-k"
    if f in ("10-Q", "10-Q/A"):
        return "sec_10-q"
    if f in ("8-K", "8-K/A"):
        return "sec_8-k"
    if f in ("S-3", "S-3/A", "S-3ASR"):
        return "sec_s-3"
    if f.startswith("424B") or f == "PROSPECTUS":
        return "sec_424b"
    if f in ("3", "4", "5"):
        return "sec_insider_form"
    if f.startswith("13F"):
        return "sec_13f"
    return "sec_filing_other"


# Content/metadata patterns that conservatively indicate a dilutive offering.
_OFFERING_PATTERNS = (
    "at-the-market",
    "atm",
    "shelf",
    "offering",
    "prospectus supplement",
    "dilut",
)


def detect_offering_flags(form: str, description: str = "", items: str = "") -> Dict[str, Any]:
    """Conservatively flag a shelf / ATM / offering (dilutive) filing.

    Returns ``{"offering_flag": True, "expected_direction": "negative"}`` when the
    form is an ``S-3`` / ``424B*`` registration OR the description/items text
    contains an offering pattern. Otherwise returns ``{}``.

    This is a *metadata / content-pattern* flag -- a match on the form type or on
    a fixed keyword list in the primary-document description or 8-K item text. It
    is NOT NLP and forms no view on magnitude; it only marks that the filing
    metadata is consistent with a dilutive capital-raise so the downstream
    Observation carries a conservative negative expected_direction hint.
    """
    f = str(form or "").strip().upper()
    text = "{0} {1}".format(str(description or ""), str(items or "")).lower()

    form_is_offering = f in ("S-3", "S-3/A", "S-3ASR") or f.startswith("424B")
    text_is_offering = any(p in text for p in _OFFERING_PATTERNS)

    if form_is_offering or text_is_offering:
        return {"offering_flag": True, "expected_direction": "negative"}
    return {}


# Forms treated as clearly "regulatory" (ownership / institutional reporting)
# rather than the issuer's own disclosure. Everything else -> official_filing.
_REGULATORY_FORMS = frozenset({"3", "4", "5"})
_REGULATORY_PREFIXES = ("13F", "SC 13")


def _source_class_for_form(form: str) -> str:
    f = str(form or "").strip().upper()
    if f in _REGULATORY_FORMS or any(f.startswith(p) for p in _REGULATORY_PREFIXES):
        return "regulatory"
    return "official_filing"


# 8-K item numbers -> a coarse catalyst_type hint (no scoring, just a label).
_ITEM_CATALYST_HINTS = (
    ("1.01", "material_agreement"),
    ("1.02", "agreement_termination"),
    ("2.01", "acquisition_or_disposition"),
    ("2.02", "results_of_operations"),
    ("5.02", "management_change"),
    ("7.01", "regulation_fd_disclosure"),
    ("8.01", "other_event"),
)


def _catalyst_type_for_items(items: str) -> Optional[str]:
    text = str(items or "")
    for code, label in _ITEM_CATALYST_HINTS:
        if code in text:
            return label
    return None


def _filing_url(cik: str, accession: str, primary_document: str) -> str:
    """Derive the canonical EDGAR document URL (a label; never fetched here)."""
    if not accession:
        return ""
    acc_nodash = accession.replace("-", "")
    cik_int = str(cik or "").lstrip("0") or "0"
    base = "https://www.sec.gov/Archives/edgar/data/{0}/{1}".format(cik_int, acc_nodash)
    if primary_document:
        return "{0}/{1}".format(base, primary_document)
    return base


def parse_sec_submissions(
    submissions_json: Dict[str, Any],
    *,
    now: float,
    retrieved_at: str = "",
    forms: Tuple[str, ...] = (),
    fields: Tuple[str, ...] = (),
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse a data.sec.gov ``submissions`` document into canonical records.

    Reads top-level ``cik`` / ``name`` / ``tickers`` and ``filings.recent`` with
    its PARALLEL arrays (``accessionNumber`` / ``form`` / ``filingDate`` /
    ``reportDate`` / ``primaryDocument`` / ``primaryDocDescription`` / ``items``).
    One RawEvidenceRecord + NormalizedEvidenceRecord is built per filing index.

    Missing top-level fields or an empty document produce an ``errors`` entry
    (never silent). ``forms`` / ``fields``, if given, request a coverage check:
    if a requested form or extracted field is absent the result is
    ``complete=False`` with a coverage warning.
    """
    doc = dict(submissions_json or {})
    warnings: List[str] = []
    errors: List[str] = []

    if not doc:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty SEC submissions document",),
            complete=False,
        )

    name = doc.get("name", "")
    cik = str(doc.get("cik", "") or "")
    tickers = doc.get("tickers") or []
    ticker = tickers[0] if tickers else ""

    if not name:
        warnings.append("SEC submissions missing 'name'")
    if not cik:
        warnings.append("SEC submissions missing 'cik'")
    if not ticker:
        warnings.append("SEC submissions missing 'tickers'")

    recent = ((doc.get("filings") or {}).get("recent")) or {}
    accession = recent.get("accessionNumber") or []
    form_arr = recent.get("form") or []
    filing_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    primary_docs = recent.get("primaryDocument") or []
    primary_descs = recent.get("primaryDocDescription") or []
    items_arr = recent.get("items") or []

    if not form_arr:
        errors.append("SEC submissions has no filings.recent.form entries")
        return AdapterResult(
            source=sec_source(retrieved_at=retrieved_at),
            records=(),
            warnings=tuple(warnings),
            errors=tuple(errors),
            complete=False,
        )

    def _at(arr: List[Any], i: int) -> Any:
        return arr[i] if i < len(arr) else None

    records = []
    for i in range(len(form_arr)):
        form = form_arr[i]
        acc = _at(accession, i) or ""
        filing_date = _at(filing_dates, i) or ""
        report_date = _at(report_dates, i) or ""
        primary_document = _at(primary_docs, i) or ""
        primary_desc = _at(primary_descs, i) or ""
        items = _at(items_arr, i) or ""

        if not filing_date:
            warnings.append(
                "filing {0} ({1}) missing filingDate".format(i, form)
            )

        source_class = _source_class_for_form(form)
        source_ref = _filing_url(cik, acc, primary_document)
        source = sec_source(
            source_class=source_class,
            source_ref=source_ref,
            as_of=filing_date,
            retrieved_at=retrieved_at,
        )

        raw = make_raw_evidence_record(
            source,
            subject=name or cik or acc,
            ticker=ticker,
            cik=cik,
            raw_type=str(form),
            raw_payload={
                "accessionNumber": acc,
                "form": form,
                "filingDate": filing_date,
                "reportDate": report_date,
                "primaryDocument": primary_document,
                "primaryDocDescription": primary_desc,
                "items": items,
            },
            retrieved_at=retrieved_at,
            as_of=filing_date,
            actor=actor,
            now=now,
        )

        extracted: Dict[str, Any] = {
            "form": form,
            "accession": acc,
            "primary_document": primary_document,
        }
        if source_ref:
            extracted["source_ref"] = source_ref
        # Conservative dilution flag from metadata / content patterns.
        extracted.update(detect_offering_flags(form, primary_desc, items))
        # For an 8-K, add a coarse catalyst_type hint from the item numbers.
        if classify_form(form) == "sec_8-k":
            ct = _catalyst_type_for_items(items)
            if ct is not None:
                extracted["catalyst_type"] = ct

        normalized = make_normalized_evidence_record(
            raw,
            normalized_type=classify_form(form),
            extracted_fields=extracted,
            event_date=filing_date,
            period_end=report_date,
            evidence_quality=_SEC_EVIDENCE_QUALITY,
            confidence=_SEC_CONFIDENCE,
            warnings=(),
            actor=actor,
            now=now,
        )
        records.append(normalized)

    complete = True
    present_forms = {str(f).strip().upper() for f in form_arr}
    for want in forms:
        if str(want).strip().upper() not in present_forms:
            complete = False
            warnings.append(
                "coverage: requested form {0!r} absent from submissions".format(want)
            )
    for want in fields:
        if not any(want in r.extracted_fields for r in records):
            complete = False
            warnings.append(
                "coverage: requested field {0!r} absent from all filings".format(want)
            )

    return AdapterResult(
        source=sec_source(retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=complete,
    )


# --------------------------------------------------------------------------- #
# companyfacts (XBRL) parsing.                                                 #
# --------------------------------------------------------------------------- #

# us-gaap taxonomy tag -> the canonical financial_metric field. ONLY these are
# parsed; a tag absent from the document is never invented.
_XBRL_TAG_TO_FIELD = (
    ("Revenues", "revenue"),
    ("RevenueFromContractWithCustomerExcludingAssessedTax", "revenue"),
    ("GrossProfit", "gross_profit"),
    ("OperatingIncomeLoss", "operating_income"),
    ("NetIncomeLoss", "net_income"),
    ("CashAndCashEquivalentsAtCarryingValue", "cash"),
    ("Liabilities", "debt"),
    ("LongTermDebtNoncurrent", "debt"),
    ("CommonStockSharesOutstanding", "shares_outstanding"),
    ("EntityCommonStockSharesOutstanding", "shares_outstanding"),
    ("PaymentsToAcquirePropertyPlantAndEquipment", "capex"),
    ("NetCashProvidedByUsedInOperatingActivities", "operating_cash_flow"),
)


def parse_sec_companyfacts(
    companyfacts_json: Dict[str, Any],
    *,
    now: float,
    retrieved_at: str = "",
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse a data.sec.gov ``companyfacts`` (XBRL) document into canonical records.

    Reads ``cik`` / ``entityName`` and ``facts["us-gaap"][TAG]["units"][UNIT]``,
    a list of period entries ``{start, end, val, accn, form, filed, fy, fp}``.
    Only the tags in ``_XBRL_TAG_TO_FIELD`` are parsed (absent tags are never
    invented). For each parsed fact the period entries are sorted by ``end``, the
    latest becomes ``metric_value`` and the prior period (if >= 2 entries)
    ``prior_value`` -- no fabrication when only one period exists.
    """
    doc = dict(companyfacts_json or {})
    warnings: List[str] = []
    errors: List[str] = []

    if not doc:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty SEC companyfacts document",),
            complete=False,
        )

    name = doc.get("entityName", "")
    cik = str(doc.get("cik", "") or "")
    if not name:
        warnings.append("SEC companyfacts missing 'entityName'")
    if not cik:
        warnings.append("SEC companyfacts missing 'cik'")

    us_gaap = ((doc.get("facts") or {}).get("us-gaap")) or {}
    if not us_gaap:
        errors.append("SEC companyfacts has no facts['us-gaap'] section")
        return AdapterResult(
            source=sec_source(retrieved_at=retrieved_at),
            records=(),
            warnings=tuple(warnings),
            errors=tuple(errors),
            complete=False,
        )

    records = []
    for tag, field_name in _XBRL_TAG_TO_FIELD:
        tag_block = us_gaap.get(tag)
        if not tag_block:
            warnings.append("XBRL tag {0!r} absent from companyfacts".format(tag))
            continue
        units = tag_block.get("units") or {}
        if not units:
            warnings.append("XBRL tag {0!r} has no units".format(tag))
            continue

        # Deterministic unit selection: sorted unit key order.
        for unit in sorted(units.keys()):
            entries = units.get(unit) or []
            if not entries:
                warnings.append(
                    "XBRL tag {0!r} unit {1!r} has no periods".format(tag, unit)
                )
                continue

            # Sort by end date (deterministic); latest last.
            ordered = sorted(entries, key=lambda e: str(e.get("end", "")))
            latest = ordered[-1]
            metric_value = latest.get("val")
            prior_value = ordered[-2].get("val") if len(ordered) >= 2 else None
            if prior_value is None and len(ordered) < 2:
                warnings.append(
                    "XBRL tag {0!r} unit {1!r} has one period; prior_value left "
                    "unset (not fabricated)".format(tag, unit)
                )

            form = latest.get("form", "")
            accn = latest.get("accn", "")
            period_start = latest.get("start", "")
            period_end = latest.get("end", "")
            filed = latest.get("filed", "")

            source = sec_source(
                source_class="official_filing",
                source_ref=accn,
                as_of=filed,
                retrieved_at=retrieved_at,
            )

            raw = make_raw_evidence_record(
                source,
                subject=name or cik,
                ticker="",
                cik=cik,
                raw_type="companyfacts:{0}".format(tag),
                raw_payload={
                    "tag": tag,
                    "unit": unit,
                    "latest": dict(latest),
                    "prior": dict(ordered[-2]) if len(ordered) >= 2 else {},
                },
                retrieved_at=retrieved_at,
                as_of=filed,
                actor=actor,
                now=now,
            )

            extracted: Dict[str, Any] = {
                "financial_metric": field_name,
                "metric_value": metric_value,
                "metric_unit": unit,
                "taxonomy_tag": tag,
                "period_start": period_start,
                "period_end": period_end,
                "accession": accn,
                "form": form,
            }
            if prior_value is not None:
                extracted["prior_value"] = prior_value

            normalized = make_normalized_evidence_record(
                raw,
                normalized_type="sec_xbrl_{0}".format(field_name),
                extracted_fields=extracted,
                event_date=filed,
                period_end=period_end,
                evidence_quality=_SEC_EVIDENCE_QUALITY,
                confidence=_SEC_CONFIDENCE,
                warnings=(),
                actor=actor,
                now=now,
            )
            records.append(normalized)

    if not records:
        errors.append("no requested XBRL tags present in companyfacts")

    return AdapterResult(
        source=sec_source(retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=bool(records),
    )
