"""Financial Modeling Prep (FMP) parsing adapter -- fixture-backed, NO network.

FMP is the MVP paid *convenience* API. Its authority is ``convenience`` (via
``authority_for_source_class`` for ``paid_api`` / ``market_data``) -- it is NOT
canonical. A canonical SEC filing ALWAYS wins a conflict against an FMP row
(see ``conflict.resolve_conflicts``): FMP fills a gap SEC leaves, it never
overwrites SEC. This module mirrors ``sec_edgar.py``: it turns already-loaded
FMP-shaped ``dict`` / ``list`` payloads into evidence records.

Discipline (matches the 009A layer):

* NO network access, NO secrets, NO API keys, and NO network import anywhere
  (top-level OR nested / lazy). The parsers take already-loaded JSON (a test
  loads a local fixture via ``open()``; a live client would inject the fetched
  payload). See ``fmp_client.py`` for the optional, dependency-injected live
  interface that is NOT exercised by default tests.
* NO investment judgement and NO scoring. Output stays evidence records only.
  It does NOT infer moat / TAM / thesis from profile text, does NOT compute
  EMA / VWAP / technical conclusions from OHLCV, and does NOT infer
  crowding / obviousness from ownership. Downstream ``map_to_observation`` turns
  a *supported* record into a Tattva Observation and nothing else.
* Only records whose category has an existing Tattva signal vocabulary are
  mapped (financial reports, news / press releases). OHLCV, profile, and
  ownership have NO Tattva vocabulary and are kept as evidence with mapping
  explicitly DEFERRED (``map_fmp_record`` raises for them -- never a silent map).
* Absent fields become explicit warnings / errors -- never fabricated values.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .source_model import EvidenceSource, authority_for_source_class
from .evidence_records import (
    NormalizedEvidenceRecord,
    make_raw_evidence_record,
    make_normalized_evidence_record,
)
from .adapters import AdapterResult
from .mapper import map_to_observation


FMP_SOURCE_NAME = "FMP"
FMP_PROVIDER = "FMP"

# Convenience-grade evidence: useful and broad, but never canonical.
_FMP_EVIDENCE_QUALITY = 0.6
_FMP_CONFIDENCE = 0.6


def fmp_source(
    source_class: str = "paid_api",
    source_ref: str = "",
    as_of: str = "",
    retrieved_at: str = "",
) -> EvidenceSource:
    """Build the convenience ``EvidenceSource`` for an FMP record.

    ``source_class`` defaults to ``paid_api``; pass ``market_data`` for OHLCV.
    Both resolve to the ``convenience`` authority via ``authority_for_source_class``
    -- FMP is never canonical.
    """
    authority = authority_for_source_class(source_class)
    return EvidenceSource(
        source_name=FMP_SOURCE_NAME,
        source_authority=authority,
        source_class=source_class,
        source_ref=source_ref,
        provider=FMP_PROVIDER,
        retrieved_at=retrieved_at,
        as_of=as_of,
    )


def _as_list(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return list(payload)
    return [payload]


# --------------------------------------------------------------------------- #
# Company profile.                                                             #
# --------------------------------------------------------------------------- #

# Descriptive profile fields we carry verbatim. We copy facts; we do NOT infer
# moat / TAM / thesis from the free-text description.
_PROFILE_FIELDS = (
    ("symbol", "symbol"),
    ("companyName", "company_name"),
    ("exchange", "exchange"),
    ("sector", "sector"),
    ("industry", "industry"),
    ("mktCap", "market_cap"),
    ("sharesOutstanding", "shares_outstanding"),
    ("website", "website"),
    ("description", "description"),
)


def parse_fmp_profile(
    profile_json: Any,
    *,
    now: float,
    retrieved_at: str = "",
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse an FMP ``profile`` payload (a list of company dicts) into one
    convenience ``fmp_profile`` record per company.

    Descriptive fields present in the payload are carried verbatim; nothing is
    inferred from the description text. Mapping to a Tattva Observation is
    DEFERRED (Tattva has no company-profile signal vocabulary).
    """
    items = _as_list(profile_json)
    warnings: List[str] = []
    errors: List[str] = []

    if not items:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty FMP profile payload",),
            complete=False,
        )

    records = []
    for entry in items:
        entry = dict(entry or {})
        symbol = str(entry.get("symbol", "") or "")
        subject = str(entry.get("companyName", "") or "") or symbol
        if not symbol:
            warnings.append("FMP profile entry missing 'symbol'")

        extracted: Dict[str, Any] = {}
        for src_key, field in _PROFILE_FIELDS:
            if entry.get(src_key) is not None:
                extracted[field] = entry.get(src_key)
        for src_key, field in _PROFILE_FIELDS:
            if field not in extracted:
                warnings.append(
                    "FMP profile missing '{0}' for {1}".format(src_key, symbol or subject)
                )

        source = fmp_source(source_class="paid_api", source_ref="", retrieved_at=retrieved_at)
        raw = make_raw_evidence_record(
            source,
            subject=subject or symbol,
            ticker=symbol,
            raw_type="fmp_profile",
            raw_payload=entry,
            retrieved_at=retrieved_at,
            as_of="",
            actor=actor,
            now=now,
        )
        normalized = make_normalized_evidence_record(
            raw,
            normalized_type="fmp_profile",
            extracted_fields=extracted,
            evidence_quality=_FMP_EVIDENCE_QUALITY,
            confidence=_FMP_CONFIDENCE,
            warnings=(),
            actor=actor,
            now=now,
        )
        records.append(normalized)

    return AdapterResult(
        source=fmp_source(retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=bool(records),
    )


# --------------------------------------------------------------------------- #
# Financial statements (income / balance / cash-flow style rows).             #
# --------------------------------------------------------------------------- #

# FMP source key -> canonical financial_metric field. Ordered; when two source
# keys map to one field (debt, shares_outstanding) the first PRESENT wins so a
# field yields exactly one record.
_INCOME_FIELD_MAP = (
    ("revenue", "revenue"),
    ("grossProfit", "gross_profit"),
    ("operatingIncome", "operating_income"),
    ("netIncome", "net_income"),
    ("cashAndCashEquivalents", "cash"),
    ("totalDebt", "debt"),
    ("totalLiabilities", "debt"),
    ("weightedAverageShsOut", "shares_outstanding"),
    ("sharesOutstanding", "shares_outstanding"),
    ("operatingCashFlow", "operating_cash_flow"),
    ("capitalExpenditure", "capex"),
    ("grossProfitRatio", "gross_margin"),
    ("operatingIncomeRatio", "operating_margin"),
)

# Fields expressed as a share count / a ratio rather than a currency amount.
_SHARE_FIELDS = frozenset({"shares_outstanding"})
_RATIO_FIELDS = frozenset({"gross_margin", "operating_margin"})


def _metric_unit(field: str) -> str:
    if field in _RATIO_FIELDS:
        return "ratio"
    if field in _SHARE_FIELDS:
        return "shares"
    return "USD"


def parse_fmp_income_statement(
    statements_json: Any,
    *,
    now: float,
    retrieved_at: str = "",
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse an FMP financial-statement payload (a list of period dicts) into
    canonical-shaped convenience financial records.

    Periods are sorted by ``date``; the latest becomes ``metric_value`` and the
    prior period (if >= 2) ``prior_value`` -- no fabrication when only one period
    exists. For each mapped metric PRESENT in the latest period one record is
    emitted with ``normalized_type = "fmp_financial_<field>"`` (contains
    "financial" so the mapper routes it to ``financial_report``). Absent metrics
    become warnings, not records.
    """
    periods = _as_list(statements_json)
    warnings: List[str] = []
    errors: List[str] = []

    if not periods:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty FMP financial-statement payload",),
            complete=False,
        )

    ordered = sorted((dict(p or {}) for p in periods), key=lambda p: str(p.get("date", "")))
    latest = ordered[-1]
    prior = ordered[-2] if len(ordered) >= 2 else None
    if prior is None:
        warnings.append(
            "FMP financials have one period; prior_value left unset (not fabricated)"
        )

    symbol = str(latest.get("symbol", "") or "")
    subject = symbol or str(latest.get("date", "") or "")
    period_end = str(latest.get("date", "") or "")

    records = []
    produced_fields = set()
    for src_key, field in _INCOME_FIELD_MAP:
        if field in produced_fields:
            continue
        if latest.get(src_key) is None:
            continue
        produced_fields.add(field)

        metric_value = latest.get(src_key)
        prior_value = prior.get(src_key) if prior is not None else None
        unit = _metric_unit(field)

        extracted: Dict[str, Any] = {
            "financial_metric": field,
            "metric_value": metric_value,
            "metric_unit": unit,
            "period_end": period_end,
            "source_key": src_key,
        }
        if prior_value is not None:
            extracted["prior_value"] = prior_value

        source = fmp_source(
            source_class="paid_api",
            source_ref="",
            as_of=period_end,
            retrieved_at=retrieved_at,
        )
        raw = make_raw_evidence_record(
            source,
            subject=subject,
            ticker=symbol,
            raw_type="fmp_financial:{0}".format(field),
            raw_payload={
                "date": period_end,
                "symbol": symbol,
                "source_key": src_key,
                "metric_value": metric_value,
                "prior_value": prior_value,
            },
            retrieved_at=retrieved_at,
            as_of=period_end,
            actor=actor,
            now=now,
        )
        normalized = make_normalized_evidence_record(
            raw,
            normalized_type="fmp_financial_{0}".format(field),
            extracted_fields=extracted,
            event_date=period_end,
            period_end=period_end,
            evidence_quality=_FMP_EVIDENCE_QUALITY,
            confidence=_FMP_CONFIDENCE,
            warnings=(),
            actor=actor,
            now=now,
        )
        records.append(normalized)

    for _src_key, field in _INCOME_FIELD_MAP:
        if field not in produced_fields:
            warnings.append(
                "FMP financials: metric {0!r} absent; no record emitted".format(field)
            )

    if not records:
        errors.append("no mappable FMP financial metrics present")

    return AdapterResult(
        source=fmp_source(retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=bool(records),
    )


# --------------------------------------------------------------------------- #
# OHLCV price bars (market_data).                                             #
# --------------------------------------------------------------------------- #

_OHLCV_FIELDS = (
    ("open", "open"),
    ("high", "high"),
    ("low", "low"),
    ("close", "close"),
    ("adjClose", "adj_close"),
    ("volume", "volume"),
)


def parse_fmp_ohlcv(
    ohlcv_json: Any,
    *,
    now: float,
    retrieved_at: str = "",
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse an FMP historical-price payload into one convenience ``fmp_ohlcv``
    record per bar (raw evidence only -- NO EMA / VWAP / technical conclusions).

    Accepts ``{"symbol": ..., "historical": [bar, ...]}`` or a bare list of bars.
    ``source_class`` is ``market_data`` (-> convenience). Mapping to a Tattva
    Observation is DEFERRED (Tattva has no raw-price signal vocabulary).
    """
    warnings: List[str] = []
    errors: List[str] = []

    symbol = ""
    if isinstance(ohlcv_json, dict):
        symbol = str(ohlcv_json.get("symbol", "") or "")
        bars = _as_list(ohlcv_json.get("historical"))
    else:
        bars = _as_list(ohlcv_json)

    if not bars:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty FMP OHLCV payload",),
            complete=False,
        )

    records = []
    for bar in bars:
        bar = dict(bar or {})
        date = str(bar.get("date", "") or "")
        bar_symbol = str(bar.get("symbol", "") or "") or symbol
        if not date:
            warnings.append("FMP OHLCV bar missing 'date'")

        extracted: Dict[str, Any] = {"ticker": bar_symbol, "date": date}
        for src_key, field in _OHLCV_FIELDS:
            if bar.get(src_key) is not None:
                extracted[field] = bar.get(src_key)
            elif src_key != "adjClose":
                warnings.append(
                    "FMP OHLCV bar {0} missing '{1}'".format(date or "?", src_key)
                )

        source = fmp_source(
            source_class="market_data",
            source_ref="",
            as_of=date,
            retrieved_at=retrieved_at,
        )
        raw = make_raw_evidence_record(
            source,
            subject=bar_symbol or date,
            ticker=bar_symbol,
            raw_type="fmp_ohlcv",
            raw_payload=bar,
            retrieved_at=retrieved_at,
            as_of=date,
            actor=actor,
            now=now,
        )
        normalized = make_normalized_evidence_record(
            raw,
            normalized_type="fmp_ohlcv",
            extracted_fields=extracted,
            event_date=date,
            period_end=date,
            evidence_quality=_FMP_EVIDENCE_QUALITY,
            confidence=_FMP_CONFIDENCE,
            warnings=(),
            actor=actor,
            now=now,
        )
        records.append(normalized)

    return AdapterResult(
        source=fmp_source(source_class="market_data", retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=bool(records),
    )


# --------------------------------------------------------------------------- #
# News / press releases.                                                      #
# --------------------------------------------------------------------------- #

# Conservative title keyword -> (catalyst_type, expected_direction). Direction is
# left None where the keyword alone does not settle a direction (e.g. guidance).
_NEWS_KEYWORDS = (
    ("contract", "contract_win", "positive"),
    ("partnership", "strategic_partnership", "positive"),
    ("offering", "capital_structure", "negative"),
    ("guidance", "management_guidance", None),
    ("award", "award", "positive"),
    ("energiz", "operational_milestone", "positive"),
)


def _classify_news_catalyst(entry: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Derive (catalyst_type, expected_direction) ONLY from explicit metadata or a
    conservative title-keyword match. Otherwise both stay None (never inferred)."""
    catalyst_type = entry.get("catalyst_type")
    expected_direction = entry.get("expected_direction")
    if catalyst_type is not None or expected_direction is not None:
        return catalyst_type, expected_direction
    title = str(entry.get("title", "") or "").lower()
    for keyword, ctype, direction in _NEWS_KEYWORDS:
        if keyword in title:
            return ctype, direction
    return None, None


def _is_press_release(entry: Dict[str, Any]) -> bool:
    """True only when the payload EXPLICITLY marks the item a press release."""
    marker = str(entry.get("type", "") or entry.get("category", "") or "").lower()
    return "press_release" in marker or "press release" in marker


def parse_fmp_news(
    news_json: Any,
    *,
    now: float,
    retrieved_at: str = "",
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse an FMP news / press-release payload into convenience records.

    Each item -> a ``fmp_news`` record (paid_api; the mapper routes it to
    ``news_excerpt``) unless the item is EXPLICITLY marked a press release, in
    which case ``normalized_type="fmp_press_release"`` (routes to
    ``press_release``) while the source stays convenience. A ``catalyst_type`` /
    ``expected_direction`` is set only from explicit metadata or a conservative
    title keyword; otherwise left unset. No opportunity / thesis is created.
    """
    items = _as_list(news_json)
    warnings: List[str] = []
    errors: List[str] = []

    if not items:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty FMP news payload",),
            complete=False,
        )

    records = []
    for entry in items:
        entry = dict(entry or {})
        symbol = str(entry.get("symbol", "") or "")
        title = str(entry.get("title", "") or "")
        published = str(entry.get("publishedDate", "") or "")
        site = str(entry.get("site", "") or "")
        url = str(entry.get("url", "") or "")
        text = str(entry.get("text", "") or "")

        if not title:
            warnings.append("FMP news item missing 'title'")
        if not published:
            warnings.append("FMP news item ({0}) missing 'publishedDate'".format(title or "?"))

        is_pr = _is_press_release(entry)
        normalized_type = "fmp_press_release" if is_pr else "fmp_news"
        catalyst_type, expected_direction = _classify_news_catalyst(entry)

        extracted: Dict[str, Any] = {
            "ticker": symbol,
            "title": title,
            "excerpt": text or title,
            "site": site,
            "url": url,
            "published_date": published,
        }
        if catalyst_type is not None:
            extracted["catalyst_type"] = catalyst_type
        if expected_direction is not None:
            extracted["expected_direction"] = expected_direction

        source = fmp_source(
            source_class="paid_api",
            source_ref=url,
            as_of=published,
            retrieved_at=retrieved_at,
        )
        raw = make_raw_evidence_record(
            source,
            subject=symbol or title,
            ticker=symbol,
            raw_type=normalized_type,
            raw_payload=entry,
            retrieved_at=retrieved_at,
            as_of=published,
            actor=actor,
            now=now,
        )
        normalized = make_normalized_evidence_record(
            raw,
            normalized_type=normalized_type,
            extracted_fields=extracted,
            event_date=published,
            evidence_quality=_FMP_EVIDENCE_QUALITY,
            confidence=_FMP_CONFIDENCE,
            warnings=(),
            actor=actor,
            now=now,
        )
        records.append(normalized)

    return AdapterResult(
        source=fmp_source(retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=bool(records),
    )


# --------------------------------------------------------------------------- #
# Ownership (recognition evidence only).                                      #
# --------------------------------------------------------------------------- #

def parse_fmp_ownership(
    ownership_json: Any,
    *,
    now: float,
    retrieved_at: str = "",
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse an FMP ownership payload into convenience ``fmp_ownership`` records
    (recognition EVIDENCE only -- NO crowding / obviousness inference).

    Accepts a bare list ``[{holder, shares, dateReported, ownershipPercent?}]``
    or ``{"symbol": ..., "ownership": [...]}``. Mapping to a Tattva Observation is
    DEFERRED (Tattva has no ownership signal vocabulary).
    """
    warnings: List[str] = []
    errors: List[str] = []

    symbol = ""
    if isinstance(ownership_json, dict):
        symbol = str(ownership_json.get("symbol", "") or "")
        holders = _as_list(
            ownership_json.get("ownership")
            or ownership_json.get("holders")
            or ownership_json.get("institutionalOwnershipList")
        )
    else:
        holders = _as_list(ownership_json)

    if not holders:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty FMP ownership payload",),
            complete=False,
        )

    records = []
    for entry in holders:
        entry = dict(entry or {})
        holder = str(entry.get("holder", "") or "")
        if not holder:
            warnings.append("FMP ownership entry missing 'holder'")

        extracted: Dict[str, Any] = {"ticker": symbol, "holder": holder}
        if entry.get("shares") is not None:
            extracted["shares"] = entry.get("shares")
        else:
            warnings.append("FMP ownership entry ({0}) missing 'shares'".format(holder or "?"))
        if entry.get("dateReported") is not None:
            extracted["date_reported"] = entry.get("dateReported")
        if entry.get("ownershipPercent") is not None:
            extracted["ownership_percent"] = entry.get("ownershipPercent")

        source = fmp_source(source_class="paid_api", retrieved_at=retrieved_at)
        raw = make_raw_evidence_record(
            source,
            subject=symbol or holder,
            ticker=symbol,
            raw_type="fmp_ownership",
            raw_payload=entry,
            retrieved_at=retrieved_at,
            as_of=str(entry.get("dateReported", "") or ""),
            actor=actor,
            now=now,
        )
        normalized = make_normalized_evidence_record(
            raw,
            normalized_type="fmp_ownership",
            extracted_fields=extracted,
            event_date=str(entry.get("dateReported", "") or ""),
            evidence_quality=_FMP_EVIDENCE_QUALITY,
            confidence=_FMP_CONFIDENCE,
            warnings=(),
            actor=actor,
            now=now,
        )
        records.append(normalized)

    return AdapterResult(
        source=fmp_source(retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=bool(records),
    )


# --------------------------------------------------------------------------- #
# Mapping to Tattva: supported vs DEFERRED.                                    #
# --------------------------------------------------------------------------- #

# normalized_type -> reason mapping is DEFERRED. These categories have NO Tattva
# signal vocabulary; forcing a map would fabricate a spurious signal or require
# alpha changes, so we keep them as evidence and refuse to map (never silently).
_DEFERRED_MAPPINGS = {
    "fmp_ohlcv": "Tattva has no raw price/OHLCV signal vocabulary",
    "fmp_profile": "Tattva has no company-profile signal vocabulary",
    "fmp_ownership": "Tattva has no ownership signal vocabulary",
}


class MappingDeferredError(Exception):
    """Raised when an FMP record's category has no Tattva vocabulary to map into."""


def mapping_deferred_reason(record: NormalizedEvidenceRecord) -> Optional[str]:
    """Return the deferral reason for a record whose mapping is DEFERRED, else None.

    A non-None result means ``map_fmp_record`` will refuse to map it.
    """
    return _DEFERRED_MAPPINGS.get(str(record.normalized_type or ""))


def map_fmp_record(
    record: NormalizedEvidenceRecord,
    *,
    domain: str,
    actor: str = "evidence-ingestion",
    now: float,
) -> Tuple[Any, Tuple[str, ...]]:
    """Map a SUPPORTED FMP record to a Tattva Observation (financial / news /
    press release). For a DEFERRED category (OHLCV / profile / ownership) raise
    ``MappingDeferredError`` -- never a silent or forced map.
    """
    reason = mapping_deferred_reason(record)
    if reason is not None:
        raise MappingDeferredError(
            "mapping deferred for normalized_type={0!r}: {1}".format(
                record.normalized_type, reason
            )
        )
    return map_to_observation(record, domain=domain, actor=actor, now=now)
