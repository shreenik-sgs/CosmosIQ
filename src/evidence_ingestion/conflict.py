"""Conflict resolver -- when two sources disagree, the higher authority wins.

Arbitration is FAMILY-SCOPED and PERIOD-AWARE. For each record we derive a
``conflict_key`` from its evidence FAMILY (not by blindly iterating every extracted
field), so only records describing the SAME underlying fact ever compete:

* **Financial fact** (record carries ``financial_metric``): key =
  ``(subject, "financial_fact", financial_metric, period_end, unit)`` with
  ``period_end = rec.period_end or rec.event_date or ""`` and
  ``unit = extracted_fields["metric_unit"] or ""``; the arbitrated value is
  ``metric_value``. This makes SEC ``sec_xbrl_revenue`` and FMP
  ``fmp_financial_revenue`` conflict for the SAME period/unit -- but SEC annual
  (period_end A) and FMP quarterly (period_end Q) do NOT collide (different key),
  so we never invent a FALSE cross-period conflict. ``shares_outstanding`` is just
  another ``financial_metric`` in this family.
* **Market data / OHLCV** (``source_class == "market_data"`` or ``"ohlcv"`` in the
  normalized_type): one entry per bar field, key =
  ``(ticker, "market_data", date, field)``. OHLCV NEVER arbitrates against a
  financial filing (different family / key).
* **News / catalyst** (news / press_release): key =
  ``(subject, "news", normalized_type, event_date, title_or_url)`` and the value
  is that same distinguishing marker, so distinct events stay distinct and are
  never numerically "resolved" against each other.
* **Filing event** (8-K / S-3 / 10-* metadata, no ``financial_metric``): the key
  includes ``normalized_type``, ``event_date`` and ``accession`` so unrelated
  filings never collapse into a spurious conflict.
* **Generic fallback** (no family match): ``(subject, normalized_type, field)`` per
  field -- unchanged legacy behavior.

Within a key, the value from the highest ``authority_rank`` wins -- canonical(6) >
convenience(4) > fallback(2) -- so a canonical SEC filing beats a convenience FMP
row, and a yfinance fallback can never overwrite FMP or SEC. A disagreement emits a
warning naming BOTH source identities AND authorities. Equal values are not a
conflict. This performs NO investment judgement -- only trust arbitration over
evidence.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Tuple

from .source_model import authority_rank
from .evidence_records import NormalizedEvidenceRecord


# OHLCV bar fields arbitrated within the market-data family.
_OHLCV_FIELDS = ("open", "high", "low", "close", "adj_close", "volume")


def _record_entries(
    rec: NormalizedEvidenceRecord,
) -> Iterator[Tuple[Tuple[Any, ...], Any]]:
    """Yield ``(conflict_key, value)`` pairs for one record, chosen by FAMILY.

    Most records yield a single entry; a market-data bar yields one per price
    field. The family dispatch is deliberate (not a blind field sweep) so records
    only ever compete when they describe the same underlying fact.
    """
    fields: Dict[str, Any] = dict(rec.extracted_fields or {})
    subject = rec.subject
    nt = str(rec.normalized_type or "")
    sc = str(rec.source_class or "")

    # 1. Financial fact -- arbitrate the metric_value for a metric/period/unit.
    if fields.get("financial_metric"):
        financial_metric = fields.get("financial_metric")
        period_end = rec.period_end or rec.event_date or ""
        unit = fields.get("metric_unit") or ""
        yield (subject, "financial_fact", financial_metric, period_end, unit), fields.get(
            "metric_value"
        )
        return

    # 2. Market data / OHLCV -- one entry per price field, scoped to ticker+date.
    if sc == "market_data" or "ohlcv" in nt.lower():
        ticker = rec.ticker or subject
        date = fields.get("date") or rec.event_date or rec.period_end or ""
        for f in _OHLCV_FIELDS:
            if f in fields:
                yield (ticker, "market_data", date, f), fields.get(f)
        return

    # 3. News / catalyst -- keep distinct events distinct; not numerically resolved.
    if "news" in nt.lower() or "press_release" in nt.lower() or sc == "press_release":
        event_date = rec.event_date or fields.get("published_date") or ""
        title_or_url = fields.get("title") or fields.get("url") or nt
        yield (subject, "news", nt, event_date, title_or_url), title_or_url
        return

    # 4. Filing event (official filing / regulatory metadata, no financial_metric).
    if sc in ("official_filing", "regulatory"):
        event_date = rec.event_date or rec.period_end or ""
        accession = fields.get("accession") or ""
        for field, value in fields.items():
            yield (subject, "filing", nt, event_date, accession, field), value
        return

    # 5. Generic fallback -- unchanged legacy behavior.
    for field, value in fields.items():
        yield (subject, nt, field), value


def resolve_conflicts(
    normalized_records: Tuple[NormalizedEvidenceRecord, ...],
) -> Tuple[Dict[Tuple[Any, ...], Any], Tuple[str, ...]]:
    """Resolve conflicts across records by source authority, family-scoped.

    Returns ``(resolved, conflict_warnings)`` where ``resolved`` maps each
    family-scoped ``conflict_key`` (see module docstring) to the winning value.
    Only records that share a ``conflict_key`` compete; the highest
    ``authority_rank`` wins and a disagreement warns, naming both source
    identities and both authorities.
    """
    records = list(normalized_records)

    grouped: Dict[Tuple[Any, ...], List[Tuple[Any, NormalizedEvidenceRecord]]] = {}
    for rec in records:
        for key, value in _record_entries(rec):
            grouped.setdefault(key, []).append((value, rec))

    resolved: Dict[Tuple[Any, ...], Any] = {}
    warnings: List[str] = []

    for key, entries in grouped.items():
        # Winner = highest authority rank; ties keep first-seen.
        winner_value, winner_rec = max(
            entries, key=lambda vr: authority_rank(vr[1].source_authority)
        )
        resolved[key] = winner_value

        for value, rec in entries:
            if rec is winner_rec:
                continue
            if value != winner_value:
                warnings.append(
                    "conflict on {0}: kept {1!r} from {2} ({3}) over "
                    "{4!r} from {5} ({6})".format(
                        "/".join(str(k) for k in key),
                        winner_value,
                        winner_rec.source.source_name if winner_rec.source else "?",
                        winner_rec.source_authority,
                        value,
                        rec.source.source_name if rec.source else "?",
                        rec.source_authority,
                    )
                )

    return resolved, tuple(warnings)


def winning_records(
    normalized_records: Tuple[NormalizedEvidenceRecord, ...],
) -> Dict[Tuple[Any, ...], NormalizedEvidenceRecord]:
    """Return, per ``conflict_key``, the highest-authority winning RECORD.

    This is an ADDITIVE convenience over the exact same family-scoped
    ``_record_entries`` keys and ``authority_rank`` ordering that
    ``resolve_conflicts`` uses. Where ``resolve_conflicts`` resolves the winning
    *value* per key, this resolves the winning *record* per key, so a caller (the
    ingestion vertical slice) can map ONLY the winning record for each semantic
    fact and treat the losers as overridden evidence.

    Ties (equal authority) keep first-seen order -- ``max`` returns the first
    maximal element and ``normalized_records`` is iterated in order. The behaviour
    of ``resolve_conflicts`` and ``_record_entries`` is unchanged; this reads them,
    it does not alter them.
    """
    records = list(normalized_records)

    grouped: Dict[Tuple[Any, ...], List[NormalizedEvidenceRecord]] = {}
    for rec in records:
        for key, _value in _record_entries(rec):
            grouped.setdefault(key, []).append(rec)

    winners: Dict[Tuple[Any, ...], NormalizedEvidenceRecord] = {}
    for key, recs in grouped.items():
        winners[key] = max(recs, key=lambda r: authority_rank(r.source_authority))
    return winners
