"""The FALLBACK-tier price-history LIVE source adapter -- Yahoo Finance (PROD-LIVE-2).

:class:`YahooPriceLiveAdapter` is a research-only PRICE-HISTORY fallback: when FMP (convenience)
is missing or throttled, this adapter still delivers per-ticker technical inputs (close / EMA /
VWAP / volume / range readings) so the Technical Regime sensor can read a chart. It calls Yahoo's
public chart API directly via an INJECTABLE transport and normalises each response into a
``price_history_reading`` :class:`~reality_mesh.models.RealityEvent` in the ``technical_regime``
discipline -- the SAME shape the 014D LOCAL price-history adapter emits, so the technical sensor
consumes it unchanged.

AUTHORITY -- THE FALLBACK TIER, BELOW FMP CONVENIENCE, ASSIGNED IMMEDIATELY PER RECORD:

* Yahoo price data is stamped ``source_authority="fallback"`` (research-only) +
  ``claim_status="reported_claim"`` (a third-party-reported chart read, never a verified fact).
* It can NEVER outrank FMP (convenience) OR SEC (canonical) for the same fact:
  ``authority_rank("fallback") < authority_rank("convenience") < authority_rank("canonical")``.
  On a same-fact price contradiction the higher tier wins authority; the Yahoo read is preserved
  as a fallback read routed to Trust / Data Quality -- never promoted, never canonical, never a
  ``verified_fact``.
* It is a PRICE-HISTORY fallback (for technicals) ONLY -- never a fundamentals / filings source.

NO CREDENTIAL. Yahoo's public chart endpoint needs no API key -- ``credential_requirements=()``.
There is nothing to leak; the presence-only discipline is preserved (no secret is ever read,
stored, logged, echoed, or rendered).

NO NETWORK ON IMPORT. This module imports NO network library at top level OR inside any function.
The DEFAULT real transport is built lazily inside :meth:`YahooPriceLiveAdapter._default_transport`
from ``evidence_ingestion.live_transport.yahoo_chart_transport`` (whose ``urllib`` is itself
function-local). The whole test suite runs OFFLINE under a socket kill-switch and NEVER exercises
the real network path: tests inject a mock ``transport``. This module imports ONLY stdlib +
``reality_mesh`` -- so the security audit's ``dependencies_reviewed`` stays green (zero third-party
runtime deps; the ``yfinance`` package is NEVER imported).

FAILURE -> VISIBLE GAP, OTHER TICKERS CONTINUE. A Yahoo HTTP 429 (or rate-limit-shaped error) is
captured as ``rate_limited`` (honoured, NEVER retried inside a pulse); any other transport failure
/ timeout is ``source_unavailable``; a malformed payload is a ``parse_error``. An unknown / delisted
ticker (Yahoo returns ``chart.result=null`` + an error, or an empty bar set) is a NAMED visible gap.
Each failure names its ticker and the remaining tickers still deliver (a ``partial`` result) --
nothing fabricated, never a fixture / demo fallback, ZERO fabricated bars.

Deterministic, stdlib-only, Python 3.9, OFFLINE tests. Ids and ``raw_payload_ref``s are
content-derived (sha256); ``now`` is an injected string (no wall-clock in any id path). Every
numeric value is DERIVED from the ACTUAL Yahoo bars (an underivable indicator -- e.g. a 200-EMA on
a 6-month window -- is an explicit gap, never a fabricated number). No scheduler / broker / trade /
score field exists anywhere.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import labels as _labels
from ..models import RealityEvent
from .base import (
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
)
from .local_price_history import (
    PRICE_HISTORY_INDICATOR_UNITS,
    _indicators_from_bars,
)

__all__ = [
    "YAHOO_PRICE_LIVE_ADAPTER_ID",
    "YAHOO_PRICE_LIVE_DESCRIPTOR",
    "YAHOO_PRICE_LIVE_DISCIPLINES",
    "YAHOO_PRICE_LIVE_TRANSPORT_KEYS",
    "YAHOO_PRICE_LIVE_EVENT_TYPE",
    "YAHOO_PRICE_LIVE_EVENT_TYPES",
    "YAHOO_PRICE_LIVE_SOURCE_AUTHORITY",
    "YAHOO_PRICE_LIVE_CLAIM_STATUS",
    "YAHOO_NEVER_OUTRANKS_FMP_SEC_NOTE",
    "YAHOO_FALLBACK_EVENT_NOTE",
    "YahooPriceLiveAdapter",
]

YAHOO_PRICE_LIVE_ADAPTER_ID = "price.yahoo_fallback"

# The single discipline this adapter is the source for -- the SAME discipline the 014D local
# price-history adapter feeds and the technical_regime sensor reads. A pulse takes
# technical_regime from this adapter ONLY when it runs; a failed / skipped source stays a
# VISIBLE gap and is never silently backfilled from fixtures.
YAHOO_PRICE_LIVE_DISCIPLINES: Tuple[str, ...] = ("technical_regime",)

# One injected transport key: the Yahoo chart endpoint. ``fetch(symbol) -> decoded chart JSON``.
YAHOO_PRICE_LIVE_TRANSPORT_KEYS: Tuple[str, ...] = ("chart",)

# Yahoo price data is the FALLBACK tier -- research-only, below FMP convenience and SEC canonical.
YAHOO_PRICE_LIVE_SOURCE_AUTHORITY = "fallback"      # the fallback / free-api tier of the ladder
YAHOO_PRICE_LIVE_CLAIM_STATUS = "reported_claim"    # a third-party-reported chart read (never verified)

# The one event_type this adapter emits -- reusing the 014D price-history reading shape so the
# technical_regime sensor consumes Yahoo events exactly as it consumes local price-history files.
YAHOO_PRICE_LIVE_EVENT_TYPE = "price_history_reading"
YAHOO_PRICE_LIVE_EVENT_TYPES: Tuple[str, ...] = (YAHOO_PRICE_LIVE_EVENT_TYPE,)

YAHOO_NEVER_OUTRANKS_FMP_SEC_NOTE = (
    "Yahoo price data is FALLBACK tier (research-only price history for technicals): it can NEVER "
    "outrank FMP (convenience) OR SEC (canonical) for the same fact "
    "(fallback < convenience < canonical); on a same-fact price contradiction the higher tier "
    "wins authority and the Yahoo read is preserved and routed to Trust / Data Quality -- never "
    "promoted, never canonical, never a verified fact")

YAHOO_FALLBACK_EVENT_NOTE = (
    "Yahoo Finance chart is a FALLBACK / research-only price-history read (fallback tier; "
    "reported_claim) -- price technicals only, never a fundamentals/filings source, never "
    "canonical, never a verified fact; below FMP convenience and SEC canonical")

# Error-text shapes recognised as a RATE LIMIT / throttle (vs a generic failure). Yahoo returns
# HTTP 429 when its public endpoint is throttled -- honoured as rate_limited (never retried).
_RATE_LIMIT_TOKENS = (
    "429", "rate limit", "rate-limit", "ratelimit", "too many requests", "throttle",
)

# Conservative Yahoo fair-use ceiling for the spacing limiter (a courtesy pace on the real path).
_MAX_REQUESTS_PER_SECOND = 4.0


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = "{0} {1}".format(type(exc).__name__, exc).lower()
    return any(token in text for token in _RATE_LIMIT_TOKENS)


def _sha12(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _payload_ref(ticker: str, payload: Any) -> str:
    """A content-derived pointer at the exact chart payload fetched (a ref, never inlined)."""
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return "raw:yahoo_chart/{0}#sha256={1}".format(ticker, digest)


def _normalise_tickers(watchlist) -> Tuple[str, ...]:
    """Strip / upper / dedupe (first-seen order); reject blank tokens."""
    raw = watchlist.split(",") if isinstance(watchlist, str) else list(watchlist or ())
    out: List[str] = []
    for token in raw:
        tk = str(token).strip().upper()
        if tk and tk not in out:
            out.append(tk)
    return tuple(out)


def _num_or_none(value) -> Optional[float]:
    """A finite float, or None (a null/absent Yahoo array cell -> honest absence, never faked)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / inf -> honest absence
        return None
    return out


def _epoch_to_date(epoch) -> str:
    """A YYYY-MM-DD date (UTC) from a Yahoo unix timestamp, or "" if unparseable."""
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        return ""
    try:
        return _dt.datetime.fromtimestamp(
            int(epoch), tz=_dt.timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OverflowError, OSError):
        return ""


def _days_between(as_of: str, now: str) -> Optional[int]:
    """Whole days from ``as_of`` (YYYY-MM-DD) to ``now`` (ISO). None if unparseable."""
    def _ordinal(text: str) -> Optional[int]:
        parts = str(text or "")[:10].split("-")
        if len(parts) != 3:
            return None
        try:
            return _dt.date(int(parts[0]), int(parts[1]), int(parts[2])).toordinal()
        except ValueError:
            return None

    a = _ordinal(as_of)
    b = _ordinal(now)
    if a is None or b is None:
        return None
    return b - a


def _freshness_from_age(as_of: str, now: str) -> str:
    """A freshness LABEL from the latest bar date vs the injected ``now`` (never a number)."""
    days = _days_between(as_of, now)
    if days is None or days < 0:
        return "unknown"
    if days <= 7:
        return "fresh"
    if days <= 45:
        return "recent"
    if days <= 120:
        return "aging"
    if days <= 400:
        return "stale"
    return "expired"


# --------------------------------------------------------------------------- #
# Rate-limit-conscious spacing limiter (paces the REAL transport).              #
# --------------------------------------------------------------------------- #
class _SpacingLimiter:
    """A minimal deterministic request-spacing limiter (paces the REAL transport).

    ``acquire`` enforces a minimum interval between successive requests. It affects TIMING only
    -- never the OUTPUT (ids / values / run_id are content-derived, ``now`` injected) -- so it is
    safe under the offline test kill-switch. ``time`` is imported lazily (NOT a network import).
    """

    __slots__ = ("_min_interval", "_last", "_monotonic", "_sleep", "calls")

    def __init__(self, max_per_second: float = _MAX_REQUESTS_PER_SECOND) -> None:
        self._min_interval = (1.0 / max_per_second) if max_per_second > 0 else 0.0
        self._last: Optional[float] = None
        self._monotonic: Optional[Callable[[], float]] = None
        self._sleep: Optional[Callable[[float], None]] = None
        self.calls = 0

    def acquire(self) -> None:
        self.calls += 1
        if self._min_interval <= 0:
            return
        monotonic = self._monotonic
        sleep = self._sleep
        if monotonic is None or sleep is None:
            import time  # lazy; NOT a network import
            monotonic = monotonic or time.monotonic
            sleep = sleep or time.sleep
        current = monotonic()
        if self._last is not None:
            wait = self._min_interval - (current - self._last)
            if wait > 0:
                sleep(wait)
                current = monotonic()
        self._last = current


# --------------------------------------------------------------------------- #
# The injected/real-transport fetch boundary                                    #
# --------------------------------------------------------------------------- #
class _TransportBoundary(SourceAdapter):
    """The ``fetch_checked`` boundary with the base network refusal disarmed.

    This IS a production network path (mirroring 020B/021A). No ambient import-time network is
    possible: the real transport is function-local and tests inject a mock. So this view re-runs
    the base boundary with the SAME descriptor except ``network_required=False`` (the blanket
    refusal is disarmed); every OTHER check -- RealityEvents only, authority / raw-ref /
    provenance per event, honest counts, failure -> gap -- still runs unchanged.
    """

    def __init__(self, outer: "YahooPriceLiveAdapter",
                 offline_descriptor: SourceAdapterDescriptor) -> None:
        self._outer = outer
        self._descriptor = offline_descriptor

    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return self._descriptor

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        return self._outer.covered_disciplines

    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        return self._outer.fetch_events(watchlist=watchlist, themes=themes, now=now)


# --------------------------------------------------------------------------- #
# The descriptor (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1)                     #
# --------------------------------------------------------------------------- #
YAHOO_PRICE_LIVE_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=YAHOO_PRICE_LIVE_ADAPTER_ID,
    source_name="Yahoo Finance chart API price-history fallback (query1.finance.yahoo.com)",
    source_type="price_history",
    source_authority=YAHOO_PRICE_LIVE_SOURCE_AUTHORITY,   # fallback (research-only) tier
    credential_requirements=(),                           # NONE -- Yahoo's public chart needs no key
    network_required=True,                                # a production live path (mock in tests)
    rate_limit_policy=(
        "Yahoo's public chart endpoint is paced by a conservative in-adapter spacing limiter; an "
        "HTTP 429 (or rate-limit-shaped response) is surfaced as rate_limited "
        "(rate_limit_status=throttled), never retried inside a pulse, never hidden"),
    outputs=YAHOO_PRICE_LIVE_EVENT_TYPES,
    claim_status_rules=(
        "every Yahoo chart reading -> source_authority=fallback (research-only) + "
        "claim_status=reported_claim -- NEVER canonical, NEVER convenience, NEVER a verified_fact",
        "Yahoo price data is a PRICE-HISTORY fallback for technicals only, never a "
        "fundamentals/filings source and never an investment conclusion",
        "authority is assigned immediately PER RECORD and preserved: a fallback read can NEVER "
        "outrank FMP (convenience) or SEC (canonical) -- fallback < convenience < canonical",
        "on a same-fact price contradiction the higher tier wins authority and the Yahoo read is "
        "preserved and routed to Trust / Data Quality -- never promoted, never canonical",
    ),
    failure_modes=("rate_limited", "source_unavailable", "parse_error"),
    description=(
        "Yahoo Finance chart-API price-history FALLBACK adapter (PROD-LIVE-2) -- a research-only "
        "price source that keeps technicals available when FMP is missing / throttled. Reads "
        "Yahoo's public chart endpoint per ticker via an injectable transport (the default real "
        "transport is built lazily from evidence_ingestion.live_transport.yahoo_chart_transport; "
        "no network on import, no credential), derives close/EMA/VWAP/volume/range readings from "
        "the ACTUAL bars into a fallback/reported_claim technical_regime RealityEvent with "
        "provenance + freshness, and turns every fetch failure into a VISIBLE gap. Research-only "
        "price context, never canonical, never outranks FMP or SEC. Labels not scores; no "
        "scheduler / broker / trading / scoring."),
)


# --------------------------------------------------------------------------- #
# YahooPriceLiveAdapter                                                         #
# --------------------------------------------------------------------------- #
class YahooPriceLiveAdapter(SourceAdapter):
    """Yahoo Finance chart -> fallback/reported_claim technical_regime price-history RealityEvents.

    Honest gaps; no fixture fallback; never outranks FMP or SEC.

    ``transport`` is an INJECTABLE dict with a single ``"chart"`` callable
    (``fetch(symbol) -> decoded chart JSON``). When ``transport`` is ``None`` the DEFAULT real
    transport is built lazily inside :meth:`_default_transport` (from
    ``evidence_ingestion.live_transport.yahoo_chart_transport``; import-time is network-free). No
    credential exists (Yahoo's public chart needs no key), so there is nothing to pass or leak.
    """

    def __init__(self, transport: Optional[Dict[str, Any]] = None, *,
                 timeout_s: float = 20.0, max_retries: int = 2) -> None:
        if transport is not None:
            if not isinstance(transport, dict):
                raise ValueError(
                    "YahooPriceLiveAdapter transport must be a dict with a 'chart' callable "
                    "(keys: {0})".format(", ".join(YAHOO_PRICE_LIVE_TRANSPORT_KEYS)))
            for key, fetch in transport.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(
                        "YahooPriceLiveAdapter transport keys must be non-empty endpoint names "
                        "(e.g. 'chart')")
                if not callable(fetch):
                    raise ValueError(
                        "YahooPriceLiveAdapter transport[{0!r}] must be a callable fetch (the "
                        "injected transport shape)".format(key))
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise ValueError("YahooPriceLiveAdapter.timeout_s must be a number of seconds")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("YahooPriceLiveAdapter.max_retries must be a non-negative int")

        self._transport = dict(transport) if transport is not None else None
        self._timeout_s = float(timeout_s)
        self._max_retries = int(max_retries)
        self._limiter = _SpacingLimiter()
        self._boundary = _TransportBoundary(
            self, replace(YAHOO_PRICE_LIVE_DESCRIPTOR, network_required=False))

    # -- identity ----------------------------------------------------------- #
    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return YAHOO_PRICE_LIVE_DESCRIPTOR

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        return YAHOO_PRICE_LIVE_DISCIPLINES

    def __repr__(self) -> str:  # no credential exists here -- presence-only discipline preserved
        wired = sorted(self._transport) if self._transport is not None else "default_real"
        return "YahooPriceLiveAdapter(transport={0})".format(wired)

    # -- the transport gate over fetch_checked ------------------------------ #
    def fetch_checked(self, *, watchlist=(), themes=(),
                      now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Fetch with the 013 boundary enforced. This is a production network path, so the base
        blanket network refusal is disarmed; every other contract check still runs. In tests a
        mock transport is injected and the real path is never reached; in production the real
        transport is built lazily (no credential needed)."""
        return self._boundary.fetch_checked(watchlist=watchlist, themes=themes, now=now)

    # -- the DEFAULT real transport, built lazily (NO network on import) ----- #
    def _default_transport(self) -> Dict[str, Any]:
        """Build the real Yahoo chart transport lazily. No credential is required (Yahoo's public
        chart endpoint needs no key), so this always returns a wired transport. ``urllib`` lives
        inside the transport builder. NEVER exercised by the offline test suite."""
        from evidence_ingestion.live_transport import yahoo_chart_transport  # lazy boundary
        return yahoo_chart_transport(timeout=self._timeout_s)

    # -- fetch --------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Pull each ticker's Yahoo chart via the transport into fallback price-history
        RealityEvents + an honest result. Deterministic; a mock transport keeps it OFFLINE. A
        raising transport is captured as rate_limited / source_unavailable and the OTHER tickers
        continue (partial); a malformed payload is a parse_error; an unknown/delisted/empty ticker
        is a NAMED gap. Never fabricates a bar; never falls back to fixture/demo data."""
        state = {"rate_limited": False, "unavailable": False, "parse_failed": False}
        events: List[RealityEvent] = []
        refs: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        gaps: List[str] = []

        tickers = _normalise_tickers(watchlist)
        if not tickers:
            gaps.append(
                "empty watchlist: the Yahoo price fallback fetches per ticker and was given none "
                "-- nothing fetched, nothing fabricated")
            return (), self._result("skipped", refs, events, warnings, errors, gaps, state, now)

        transport = self._transport
        if transport is None:
            transport = self._default_transport()

        for ticker in tickers:
            event = self._ticker_event(ticker, transport, refs, errors, gaps, state, now)
            if event is not None:
                events.append(event)

        problems = state["rate_limited"] or state["unavailable"] or state["parse_failed"]
        if events:
            status = "partial" if problems else "success"
        elif problems:
            status = "failed"
        else:
            status = "partial"
            gaps.append(
                "Yahoo price fallback delivered no price-history events for {0} -- visible gap, "
                "nothing fabricated (no chart data / empty payloads)".format(", ".join(tickers)))

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, state, now)

    # -- one ticker's chart -> a fallback price-history event ---------------- #
    def _ticker_event(self, ticker: str, transport: Dict[str, Any], refs: List[str],
                      errors: List[str], gaps: List[str], state: Dict[str, bool],
                      now: str) -> Optional[RealityEvent]:
        payload = self._call(transport, ticker, errors, gaps, state)
        if payload is None:
            return None
        ref = _payload_ref(ticker, payload)
        try:
            event = self._chart_event(ticker, payload, ref, now, gaps)
        except Exception as exc:            # noqa: BLE001 -- malformed -> visible parse gap
            state["parse_failed"] = True
            errors.append("parse_error: chart {0}: {1}: {2}".format(
                ticker, type(exc).__name__, exc))
            gaps.append(
                "malformed Yahoo chart payload for {0} (parse_error): price technicals have NO "
                "coverage for that ticker this pulse -- visible gap, nothing fabricated".format(
                    ticker))
            return None
        if event is None:
            return None
        refs.append(ref)
        return event

    # -- one guarded, rate-limit-conscious transport call --------------------- #
    def _call(self, transport: Dict[str, Any], ticker: str,
              errors: List[str], gaps: List[str], state: Dict[str, bool]) -> Any:
        fetch = transport.get("chart")
        if fetch is None:
            gaps.append(
                "Yahoo transport 'chart' not wired: price technicals are missing this pulse -- "
                "visible gap, nothing fabricated")
            return None
        self._limiter.acquire()     # pace the real path (a courtesy to Yahoo's public endpoint)
        try:
            return fetch(ticker)
        except Exception as exc:    # noqa: BLE001 -- failure becomes a gap, never a crash
            reason = "{0}: {1}".format(type(exc).__name__, exc)
            if _is_rate_limit_error(exc):
                state["rate_limited"] = True
                errors.append("rate_limited: chart {0}: {1}".format(ticker, reason))
                gaps.append(
                    "rate limit / throttle (HTTP 429) hit on Yahoo chart for {0}: price technicals "
                    "missing this pulse -- limit honoured (NOT retried in-pulse); visible gap, "
                    "nothing fabricated".format(ticker))
            else:
                state["unavailable"] = True
                errors.append("source_unavailable: chart {0}: {1}".format(ticker, reason))
                gaps.append(
                    "Yahoo chart unavailable / timed out for {0}: price technicals missing this "
                    "pulse -- visible gap, nothing fabricated, no silent fixture/demo "
                    "fallback".format(ticker))
            return None

    # -- the chart -> RealityEvent builder ----------------------------------- #
    def _chart_event(self, ticker: str, payload: Any, ref: str, now: str,
                     gaps: List[str]) -> Optional[RealityEvent]:
        """Parse one Yahoo chart payload into a fallback price-history event.

        Raises ``ValueError`` on a MALFORMED payload (handled by the caller as a parse_error). An
        unknown/delisted ticker (result null + error) or an empty bar set is a NAMED gap (returns
        None), never a fabricated reading.
        """
        if not isinstance(payload, dict):
            raise ValueError("Yahoo chart payload must be a JSON object")
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            raise ValueError("Yahoo chart payload missing a 'chart' object")

        error = chart.get("error")
        results = chart.get("result")
        if error or not results:
            desc = ""
            if isinstance(error, dict):
                desc = str(error.get("description") or error.get("code") or "")
            gaps.append(
                "Yahoo chart returned no data for {0}{1}: unknown / delisted ticker or empty "
                "result -- named visible gap, nothing fabricated".format(
                    ticker, (": " + desc) if desc else ""))
            return None

        if not isinstance(results, list) or not isinstance(results[0], dict):
            raise ValueError("Yahoo chart 'result' must be a non-empty array of objects")
        result0 = results[0]
        timestamps = result0.get("timestamp") or []
        indicators = result0.get("indicators")
        if not isinstance(indicators, dict):
            raise ValueError("Yahoo chart result missing an 'indicators' object")
        quote_series = indicators.get("quote") or []
        if not isinstance(timestamps, list) or not isinstance(quote_series, list):
            raise ValueError("Yahoo chart timestamp / quote series must be arrays")
        quote0 = quote_series[0] if (quote_series and isinstance(quote_series[0], dict)) else {}

        opens = quote0.get("open") or []
        highs = quote0.get("high") or []
        lows = quote0.get("low") or []
        closes = quote0.get("close") or []
        volumes = quote0.get("volume") or []
        for series in (opens, highs, lows, closes, volumes):
            if not isinstance(series, list):
                raise ValueError("Yahoo chart OHLCV series must be arrays")

        # Build only COMPLETE bars from the ACTUAL Yahoo arrays; a null/absent cell is skipped
        # (Yahoo emits null for a non-trading slot) -- never fabricated into a number.
        bars: List[Dict[str, float]] = []
        latest_ts = None
        count = min(len(timestamps), len(highs), len(lows), len(closes), len(volumes))
        for i in range(count):
            hi = _num_or_none(highs[i])
            lo = _num_or_none(lows[i])
            cl = _num_or_none(closes[i])
            vol = _num_or_none(volumes[i])
            if hi is None or lo is None or cl is None or vol is None:
                continue
            op = _num_or_none(opens[i]) if i < len(opens) else None
            bars.append({
                "open": op if op is not None else cl,
                "high": hi, "low": lo, "close": cl, "volume": vol,
            })
            latest_ts = timestamps[i]

        if not bars:
            gaps.append(
                "Yahoo chart carried no usable OHLCV bars for {0} -- named visible gap, nothing "
                "fabricated (every bar cell was null / missing)".format(ticker))
            return None

        as_of = _epoch_to_date(latest_ts)

        # Derive the indicator readings from the ACTUAL bars via the SAME 014D derivation the
        # local price-history adapter uses -- so the technical_regime sensor consumes Yahoo events
        # identically. An underivable indicator (insufficient history, e.g. a 200-EMA on a
        # 6-month window) is an explicit gap, NEVER a fabricated number.
        derivation_gaps: List[str] = []
        readings = _indicators_from_bars(bars, ticker, derivation_gaps)
        if not readings:
            raise ValueError("Yahoo chart yielded no derivable indicator reading")

        numeric_values = tuple(
            (key, readings[key], PRICE_HISTORY_INDICATOR_UNITS[key])
            for key in sorted(readings))
        digest = hashlib.sha256(
            json.dumps({"ticker": ticker, "as_of": as_of, "readings": readings},
                       sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
        freshness = _freshness_from_age(as_of, now) if as_of else "unknown"

        event_gaps = tuple(derivation_gaps) + (YAHOO_FALLBACK_EVENT_NOTE,)
        source_refs = (
            ref,
            "yahoo:chart/{0}".format(ticker),
            "yahoo:symbol/{0}".format(ticker),
        )
        return RealityEvent(
            event_id="yahoolive.technical_regime.{0}.{1}".format(ticker.lower(), digest),
            timestamp=as_of or now,
            source_id="yahoo.live.price_history.{0}".format(ticker.lower()),
            source_type="yahoo_price_history_chart",
            source_authority=YAHOO_PRICE_LIVE_SOURCE_AUTHORITY,   # fallback: assigned immediately
            claim_status=YAHOO_PRICE_LIVE_CLAIM_STATUS,           # reported_claim (never verified)
            raw_payload_ref=ref,
            discipline="technical_regime",
            event_type=YAHOO_PRICE_LIVE_EVENT_TYPE,
            affected_companies=(ticker,),
            observed_fact=(
                "Yahoo Finance fallback price-history indicator readings for {0} (research-only; "
                "chart-derived OHLCV)".format(ticker)),
            numeric_values=numeric_values,
            source_refs=source_refs,
            confidence_label="low",                               # fallback / research-only
            freshness_label=freshness,
            half_life="days",
            data_gaps=event_gaps,
        )

    # -- result builder -------------------------------------------------------- #
    def _result(self, status: str, refs: List[str], events: List[RealityEvent],
                warnings: List[str], errors: List[str], gaps: List[str],
                state: Dict[str, bool], now: str) -> SourceAdapterResult:
        if state["rate_limited"]:
            health = "rate_limited"
        elif status == "success":
            health = "healthy"
        elif status == "partial":
            health = "degraded"
        elif status == "skipped":
            health = "source_unavailable"
        else:
            health = "failed"
        run_id = deterministic_adapter_run_id(
            YAHOO_PRICE_LIVE_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=YAHOO_PRICE_LIVE_ADAPTER_ID,
            run_id=run_id,
            status=status,
            raw_payload_refs=tuple(dict.fromkeys(refs)),
            events_created=len(events),
            warnings=tuple(dict.fromkeys(warnings)),
            errors=tuple(dict.fromkeys(errors)),
            data_gaps=tuple(dict.fromkeys(gaps)),
            credentials_status="not_required",   # Yahoo's public chart needs no credential
            rate_limit_status="throttled" if state["rate_limited"] else "ok",
            source_health=health)
