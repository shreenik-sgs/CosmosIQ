"""yfinance FALLBACK parsing adapter -- fixture-backed, NO network.

yfinance / Yahoo Finance is a FREE prototype / fallback / sanity-check source. Its
authority is ``fallback`` -- the LOWEST rung above rumor. yfinance is NEVER canonical
and can NEVER overwrite a SEC filing (``canonical``) or an FMP convenience row
(``convenience``): in a conflict it always LOSES; it only ever FILLS a gap that SEC
and FMP both leave. This module mirrors ``fmp.py``: it turns already-loaded
yfinance-shaped ``dict`` / ``list`` payloads into fallback evidence records.

Discipline (matches the 009A layer, carrying forward the 009B/009C corrections):

* NO network access, NO secrets, NO API keys, and NO network import anywhere
  (top-level OR nested / lazy / importlib). The parsers take already-loaded JSON (a
  test loads a local fixture via ``open()``; a live client would inject the fetched
  payload). The real ``yfinance`` package is NEVER imported. See ``yfinance_client.py``
  for the optional, dependency-injected live interface that is NOT exercised by the
  default tests.
* NO investment judgement and NO scoring. Output stays evidence records only. It
  does NOT compute EMA / VWAP / breakout / compression / relative-strength / timing /
  signal from OHLCV (raw bars only), and does NOT infer moat / TAM / thesis / quality /
  crowding / recognition from any quote or profile field.
* yfinance data is raw price / quote / profile -- Tattva has NO signal vocabulary for
  any of it. So EVERY yfinance normalized_type has its mapping DEFERRED:
  ``map_yfinance_record`` always raises ``MappingDeferredError`` -- never a silent or
  forced map, never a spurious Tattva Observation. yfinance produces evidence only.
* Absent fields become explicit warnings / errors -- never fabricated values.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

from .source_model import EvidenceSource, authority_for_source_class
from .evidence_records import (
    NormalizedEvidenceRecord,
    make_raw_evidence_record,
    make_normalized_evidence_record,
)
from .adapters import AdapterResult
# Reuse the FMP deferral exception so the whole ingestion layer speaks one language.
from .fmp import MappingDeferredError


YF_SOURCE_NAME = "yfinance"
YF_PROVIDER = "yfinance / Yahoo Finance"

# Research-only disclaimer carried on every yfinance source. yfinance is a free
# prototype / sanity-check feed; it is never authoritative and never a fill for a
# SEC or FMP fact.
YF_RESEARCH_NOTE = (
    "yfinance / Yahoo Finance -- FREE prototype / fallback / sanity-check source; "
    "research use only; never canonical; never overwrites SEC or FMP"
)

# Fallback-grade evidence: the lowest useful tier above rumor.
_YF_EVIDENCE_QUALITY = 0.4
_YF_CONFIDENCE = 0.4


def yf_source(
    source_class: str = "market_data",
    source_ref: str = "",
    as_of: str = "",
    retrieved_at: str = "",
) -> EvidenceSource:
    """Build the FALLBACK ``EvidenceSource`` for a yfinance record.

    ``source_class`` is ``market_data`` for OHLCV and ``free_api`` for quote /
    profile. Regardless of class the authority is pinned to ``fallback`` (the
    ``free_api`` default via ``authority_for_source_class``) so yfinance stays below
    SEC (canonical) and FMP (convenience) even for OHLCV -- ``market_data`` alone
    would otherwise resolve to ``convenience``. Every source carries the
    research-only note in ``license_note``.
    """
    # free_api -> fallback; we apply that authority to yfinance uniformly.
    authority = authority_for_source_class("free_api")
    return EvidenceSource(
        source_name=YF_SOURCE_NAME,
        source_authority=authority,
        source_class=source_class,
        source_ref=source_ref,
        provider=YF_PROVIDER,
        retrieved_at=retrieved_at,
        as_of=as_of,
        license_note=YF_RESEARCH_NOTE,
    )


def _as_list(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return list(payload)
    return [payload]


# --------------------------------------------------------------------------- #
# OHLCV price history (market_data).                                          #
# --------------------------------------------------------------------------- #

# yfinance history() column -> canonical extracted field. These are REQUIRED per
# bar; an absent one becomes a warning (never a fabricated value).
_YF_OHLCV_REQUIRED = (
    ("Open", "open"),
    ("High", "high"),
    ("Low", "low"),
    ("Close", "close"),
    ("Volume", "volume"),
)

# Optional yfinance columns -- carried verbatim only when present.
_YF_OHLCV_OPTIONAL = (
    ("Adj Close", "adj_close"),
    ("Dividends", "dividends"),
    ("Stock Splits", "stock_splits"),
)


def _history_series(history_json: Any) -> Iterator[Tuple[str, List[Any]]]:
    """Yield ``(ticker, rows)`` pairs from a yfinance history payload.

    Accepts ``{"<TICKER>": {"history": [...]}}``, ``{"ticker": ..., "history": [...]}``,
    or a bare list of row dicts (ticker then taken per-row).
    """
    if isinstance(history_json, dict):
        if "history" in history_json:
            ticker = str(history_json.get("ticker", "") or "")
            yield ticker, _as_list(history_json.get("history"))
            return
        for key, val in history_json.items():
            if isinstance(val, dict):
                yield str(key), _as_list(val.get("history"))
            else:
                yield str(key), _as_list(val)
        return
    yield "", _as_list(history_json)


def parse_yfinance_history(
    history_json: Any,
    *,
    now: float,
    retrieved_at: str = "",
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse a yfinance ``history()`` payload into one fallback ``yf_ohlcv`` record
    per bar (raw evidence only -- NO EMA / VWAP / breakout / compression / RS /
    timing / signal computation).

    ``source_class`` is ``market_data`` but authority stays ``fallback``. Mapping to a
    Tattva Observation is DEFERRED (Tattva has no raw-price signal vocabulary).
    Optional columns (Adj Close / Dividends / Stock Splits) are carried only when
    present; a missing REQUIRED column becomes a warning.
    """
    warnings: List[str] = []
    errors: List[str] = []

    bars: List[Tuple[str, Dict[str, Any]]] = []
    for series_ticker, rows in _history_series(history_json):
        for row in rows:
            bars.append((series_ticker, dict(row or {})))

    if not bars:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty yfinance history payload",),
            complete=False,
        )

    records = []
    complete = True
    for series_ticker, bar in bars:
        date = str(bar.get("date", "") or bar.get("Date", "") or "")
        bar_ticker = str(bar.get("ticker", "") or "") or series_ticker
        if not date:
            warnings.append("yfinance history bar missing 'date'")

        extracted: Dict[str, Any] = {"ticker": bar_ticker, "date": date}
        for src_key, field in _YF_OHLCV_REQUIRED:
            if bar.get(src_key) is not None:
                extracted[field] = bar.get(src_key)
            else:
                complete = False
                warnings.append(
                    "yfinance history bar {0} missing '{1}'".format(date or "?", src_key)
                )
        for src_key, field in _YF_OHLCV_OPTIONAL:
            if bar.get(src_key) is not None:
                extracted[field] = bar.get(src_key)

        source = yf_source(
            source_class="market_data",
            source_ref="",
            as_of=date,
            retrieved_at=retrieved_at,
        )
        raw = make_raw_evidence_record(
            source,
            subject=bar_ticker or date,
            ticker=bar_ticker,
            raw_type="yf_ohlcv",
            raw_payload=bar,
            retrieved_at=retrieved_at,
            as_of=date,
            actor=actor,
            now=now,
        )
        normalized = make_normalized_evidence_record(
            raw,
            normalized_type="yf_ohlcv",
            extracted_fields=extracted,
            event_date=date,
            period_end=date,
            evidence_quality=_YF_EVIDENCE_QUALITY,
            confidence=_YF_CONFIDENCE,
            warnings=(),
            actor=actor,
            now=now,
        )
        records.append(normalized)

    return AdapterResult(
        source=yf_source(source_class="market_data", retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=complete and bool(records),
    )


# --------------------------------------------------------------------------- #
# Quote / profile (free_api).                                                 #
# --------------------------------------------------------------------------- #

# Descriptive yfinance ``info`` fields carried verbatim on the quote/profile record.
# We copy facts; we do NOT infer moat / TAM / thesis / quality / crowding /
# recognition from any of them.
_YF_QUOTE_FIELDS = (
    ("symbol", "symbol"),
    ("currentPrice", "current_price"),
    ("previousClose", "previous_close"),
    ("marketCap", "market_cap"),
    ("sector", "sector"),
    ("industry", "industry"),
    ("currency", "currency"),
    ("exchange", "exchange"),
)


def parse_yfinance_quote(
    info_json: Any,
    *,
    now: float,
    as_of: str = "",
    retrieved_at: str = "",
    actor: str = "evidence-ingestion",
) -> AdapterResult:
    """Parse a yfinance ``info`` dict into fallback evidence records.

    Emits up to two records:

    * a **financial_fact** record for ``sharesOutstanding``
      (``normalized_type="yf_quote_shares_outstanding"``, ``financial_metric=
      "shares_outstanding"``, ``metric_unit="shares"``, ``period_end=as_of``) so it
      participates in cross-source financial arbitration and LOSES to SEC/FMP; and
    * a descriptive quote/profile record (``normalized_type="yf_quote"``) carrying
      current_price / previous_close / market_cap / sector / industry / currency /
      exchange.

    Both are ``fallback`` authority. Nothing is inferred from any field. Mapping to a
    Tattva Observation is DEFERRED for both (Tattva has no quote/profile/share-count
    signal vocabulary). Absent fields become warnings, not fabricated values.
    """
    warnings: List[str] = []
    errors: List[str] = []

    if not isinstance(info_json, dict) or not info_json:
        return AdapterResult(
            source=None,
            records=(),
            warnings=(),
            errors=("empty or non-dict yfinance quote payload",),
            complete=False,
        )

    info = dict(info_json)
    symbol = str(info.get("symbol", "") or "")
    subject = symbol or str(info.get("shortName", "") or "")
    if not symbol:
        warnings.append("yfinance quote missing 'symbol'")

    records = []
    complete = True

    # 1. shares_outstanding -> a financial_fact record (arbitrates, loses to SEC/FMP).
    shares = info.get("sharesOutstanding")
    if shares is not None:
        extracted_sh: Dict[str, Any] = {
            "financial_metric": "shares_outstanding",
            "metric_value": shares,
            "metric_unit": "shares",
            "period_end": as_of,
        }
        source_sh = yf_source(
            source_class="free_api",
            source_ref="",
            as_of=as_of,
            retrieved_at=retrieved_at,
        )
        raw_sh = make_raw_evidence_record(
            source_sh,
            subject=subject or symbol,
            ticker=symbol,
            raw_type="yf_quote_shares_outstanding",
            raw_payload={"symbol": symbol, "sharesOutstanding": shares, "as_of": as_of},
            retrieved_at=retrieved_at,
            as_of=as_of,
            actor=actor,
            now=now,
        )
        norm_sh = make_normalized_evidence_record(
            raw_sh,
            normalized_type="yf_quote_shares_outstanding",
            extracted_fields=extracted_sh,
            event_date=as_of,
            period_end=as_of,
            evidence_quality=_YF_EVIDENCE_QUALITY,
            confidence=_YF_CONFIDENCE,
            warnings=(),
            actor=actor,
            now=now,
        )
        records.append(norm_sh)
    else:
        complete = False
        warnings.append("yfinance quote missing 'sharesOutstanding'; no shares record emitted")

    # 2. Descriptive quote / profile evidence record.
    extracted_q: Dict[str, Any] = {}
    for src_key, field in _YF_QUOTE_FIELDS:
        if info.get(src_key) is not None:
            extracted_q[field] = info.get(src_key)
    for src_key, field in _YF_QUOTE_FIELDS:
        if field not in extracted_q:
            warnings.append(
                "yfinance quote missing '{0}' for {1}".format(src_key, symbol or subject or "?")
            )

    source_q = yf_source(
        source_class="free_api",
        source_ref="",
        as_of=as_of,
        retrieved_at=retrieved_at,
    )
    raw_q = make_raw_evidence_record(
        source_q,
        subject=subject or symbol,
        ticker=symbol,
        raw_type="yf_quote",
        raw_payload=info,
        retrieved_at=retrieved_at,
        as_of=as_of,
        actor=actor,
        now=now,
    )
    norm_q = make_normalized_evidence_record(
        raw_q,
        normalized_type="yf_quote",
        extracted_fields=extracted_q,
        event_date=as_of,
        period_end=as_of,
        evidence_quality=_YF_EVIDENCE_QUALITY,
        confidence=_YF_CONFIDENCE,
        warnings=(),
        actor=actor,
        now=now,
    )
    records.append(norm_q)

    return AdapterResult(
        source=yf_source(source_class="free_api", retrieved_at=retrieved_at),
        records=tuple(records),
        warnings=tuple(warnings),
        errors=tuple(errors),
        complete=complete and bool(records),
    )


# --------------------------------------------------------------------------- #
# Mapping to Tattva: ALL DEFERRED.                                            #
# --------------------------------------------------------------------------- #

# Every yfinance normalized_type has its mapping DEFERRED: Tattva has no signal
# vocabulary for raw price / quote / profile / share counts, and yfinance is a
# fallback feed. Forcing a map would fabricate a spurious signal, so we keep
# yfinance as evidence and refuse to map (never silently, never a forced Observation).
_DEFERRED_MAPPINGS = {
    "yf_ohlcv": "Tattva has no raw price/OHLCV signal vocabulary",
    "yf_quote": "Tattva has no quote/profile signal vocabulary",
    "yf_quote_shares_outstanding": "Tattva has no raw share-count signal vocabulary",
    "yf_profile": "Tattva has no company-profile signal vocabulary",
}


def mapping_deferred_reason(record: NormalizedEvidenceRecord) -> Optional[str]:
    """Return the deferral reason for a yfinance record (all are DEFERRED), else None.

    A non-None result means ``map_yfinance_record`` will refuse to map it. Every
    yfinance normalized_type resolves to a reason here.
    """
    return _DEFERRED_MAPPINGS.get(str(record.normalized_type or ""))


def map_yfinance_record(
    record: NormalizedEvidenceRecord,
    *,
    domain: str,
    actor: str = "evidence-ingestion",
    now: float,
) -> Tuple[Any, Tuple[str, ...]]:
    """ALWAYS raise ``MappingDeferredError`` -- yfinance produces evidence only.

    yfinance data (raw price / quote / profile / share count) has NO Tattva signal
    vocabulary, so no yfinance record is ever mapped into an Observation. The
    signature mirrors ``map_fmp_record`` for a uniform ingestion interface, but there
    is no supported branch: yfinance yields NO Observations.
    """
    reason = mapping_deferred_reason(record) or (
        "yfinance is a fallback source with no Tattva signal vocabulary"
    )
    raise MappingDeferredError(
        "mapping deferred for normalized_type={0!r}: {1}".format(
            record.normalized_type, reason
        )
    )
