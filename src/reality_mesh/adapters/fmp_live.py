"""The SECOND production LIVE source adapter -- FMP (Financial Modeling Prep) (IMPLEMENTATION-021A).

:class:`FmpLiveAdapter` is the second adapter that may ingest LIVE / CURRENT external data with
full provenance, freshness, source health, rate limiting, replay compatibility and Trust /
Data-Quality visibility. It reads FMP's public REST endpoints per company (company profile,
income / balance-sheet / cash-flow statements, key ratios, and -- only when explicitly enabled
-- a live quote) via an INJECTABLE transport and normalises each into a
:class:`~reality_mesh.models.RealityEvent` in the ``financial_inflection`` discipline -- per
``SOURCE_ADAPTER_PRODUCTION_CONTRACT_013`` and mirroring the accepted 020B SEC EDGAR live
adapter's discipline exactly.

AUTHORITY, ASSIGNED IMMEDIATELY PER RECORD (contract §3 -- never promoted, never laundered):

* FMP is a COMMERCIAL PROVIDER -- financial / market CONTEXT, NEVER a canonical regulatory
  truth. Every FMP datum is stamped ``source_authority="convenience"`` (the ``commercial_provider``
  / convenience tier of the ladder) + ``claim_status="reported_claim"`` (the provider-reported
  claim label the vocab already uses -- 021B stamps provider fundamental snapshots the same way).
* FMP can NEVER outrank an SEC filing: the authority ladder (``canonical`` > ``convenience``) is
  preserved verbatim from ``evidence_ingestion.source_model``. When an FMP fact CONTRADICTS an
  SEC filing fact for the same ticker/metric, the fusion / conflict layer keeps BOTH (SEC
  canonical wins authority; the FMP read is preserved as a contradicting provider read routed to
  Trust / Data Quality) -- a provider number NEVER silently overwrites an SEC filing fact.
* An FMP figure is NEVER a ``verified_fact`` and NEVER ``canonical`` -- it is provider CONTEXT a
  downstream agent MAY interpret, never a signal / thesis / trade.

CREDENTIALS ARE PRESENCE LABELS ONLY. FMP requires an API key (a secret). The descriptor names
the required env var (``FMP_API_KEY``); this constructor accepts a PRESENCE flag only -- a
value-shaped argument is rejected and never stored or echoed. A missing credential SKIPS the
fetch with a ``credentials_missing`` health label + a visible gap NAMING the env var -- never a
crash, never a leak (the key VALUE is never printed / logged / rendered / stored -- presence
only), never a silent fixture/demo fallback.

NO NETWORK ON IMPORT. This module imports NO network library at top level. The DEFAULT real
transport is built lazily INSIDE :meth:`FmpLiveAdapter._default_transport` from
``evidence_ingestion.live_transport`` (whose ``urllib`` is itself function-local). The whole
test suite runs OFFLINE under a socket kill-switch and NEVER exercises the real network path:
tests inject a mock ``transport`` bundle. A LIVE fetch reaches the wire ONLY when an operator
runs the adapter with a wired transport + a supplied ``FMP_API_KEY``.

FAILURE -> VISIBLE GAP, OTHER TICKERS CONTINUE. An HTTP 429/403 (or rate-limit / quota-shaped
error) is captured as ``rate_limited`` (``rate_limit_status="throttled"``, honoured, NEVER
retried inside a pulse); any other transport failure / timeout is ``source_unavailable``; a
malformed payload is a ``parse_error``. Each failure names its ticker in ``errors`` +
``data_gaps`` and the remaining tickers still deliver (a ``partial`` result) -- nothing
fabricated. A rate-limit-conscious spacing limiter paces the real transport.

Deterministic, stdlib-only, Python 3.9, OFFLINE tests. Ids and ``raw_payload_ref``s are
content-derived (sha256); ``now`` is an injected string (no wall-clock in any id path). A
numeric value is emitted ONLY where FMP actually returned it (an absent figure is a visible
gap, never a fabricated number); the small set of period-over-period DELTAS are transparently
DERIVED from two FMP-reported consecutive periods and labelled provider-reported.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..models import RealityEvent
from .base import (
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
)

__all__ = [
    "FMP_LIVE_ADAPTER_ID",
    "FMP_LIVE_DESCRIPTOR",
    "FMP_LIVE_DISCIPLINES",
    "FMP_LIVE_TRANSPORT_KEYS",
    "FMP_LIVE_EVENT_TYPES",
    "FMP_LIVE_QUOTE_EVENT_TYPE",
    "FMP_LIVE_SOURCE_AUTHORITY",
    "FMP_LIVE_CLAIM_STATUS",
    "FMP_NEVER_OUTRANKS_SEC_NOTE",
    "FmpLiveAdapter",
]

FMP_LIVE_ADAPTER_ID = "evidence.fmp_live"

# The single discipline this adapter is the source for -- the SAME discipline the 021B Financial
# Inflection sensor reads. A pulse takes financial_inflection from this adapter ONLY when it runs;
# a failed / skipped source stays a VISIBLE gap and is never silently backfilled from fixtures.
FMP_LIVE_DISCIPLINES: Tuple[str, ...] = ("financial_inflection",)

# The injected transport bundle keys: one endpoint callable per FMP resource. ``quote`` is only
# CALLED when ``enable_quote=True`` (explicitly configured); it is declared here regardless.
FMP_LIVE_TRANSPORT_KEYS: Tuple[str, ...] = (
    "profile", "income_statement", "balance_sheet", "cash_flow", "ratios", "quote")

# FMP is the COMMERCIAL provider / convenience tier -- NEVER canonical, NEVER a verified fact.
FMP_LIVE_SOURCE_AUTHORITY = "convenience"        # the commercial_provider tier of the ladder
FMP_LIVE_CLAIM_STATUS = "reported_claim"         # provider_reported (the vocab's provider label)

FMP_NEVER_OUTRANKS_SEC_NOTE = (
    "FMP is a commercial provider (convenience tier): financial/market CONTEXT, never a "
    "canonical regulatory truth. A provider (convenience) read can NEVER outrank an SEC filing "
    "(canonical > convenience); on a same-fact contradiction BOTH are preserved and the "
    "contradiction is routed to Trust / Data Quality -- a provider number never overwrites SEC")

# Provider-derived deltas are transparently computed from two FMP-reported consecutive periods.
FMP_DERIVED_DELTA_NOTE = (
    "financial deltas derived from FMP-reported consecutive periods (provider-reported figures; "
    "not canonical, never a primary regulatory number, never fabricated)")

# The full closed set of event_types this adapter may emit (declared on the descriptor).
FMP_LIVE_QUOTE_EVENT_TYPE = "fmp_market_quote"
FMP_LIVE_EVENT_TYPES: Tuple[str, ...] = (
    "fmp_company_profile",
    "fmp_income_statement_snapshot",
    "fmp_balance_sheet_snapshot",
    "fmp_cash_flow_snapshot",
    "fmp_key_ratios_snapshot",
    FMP_LIVE_QUOTE_EVENT_TYPE,
)

# Error-text shapes recognised as a RATE LIMIT / quota / access throttle (vs a generic failure).
# FMP returns 429 over the plan rate, 403 for an invalid/blocked key, and a "Limit Reach"
# message when the daily quota is exhausted -- all honoured as rate_limited (never retried).
_RATE_LIMIT_TOKENS = (
    "429", "403", "rate limit", "rate-limit", "ratelimit", "too many requests",
    "forbidden", "throttle", "quota", "limit reach", "limit reached", "exceeded your",
)

# Conservative FMP fair-use ceiling for the spacing limiter (well below any paid plan rate).
_MAX_REQUESTS_PER_SECOND = 4.0


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = "{0} {1}".format(type(exc).__name__, exc).lower()
    return any(token in text for token in _RATE_LIMIT_TOKENS)


def _sha12(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _payload_ref(kind: str, key: str, payload: Any) -> str:
    """A content-derived pointer at the exact payload fetched (a ref, never inlined)."""
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return "raw:{0}/{1}#sha256={2}".format(kind, key, digest)


def _normalise_tickers(watchlist) -> Tuple[str, ...]:
    """Strip / upper / dedupe (first-seen order); reject blank tokens."""
    raw = watchlist.split(",") if isinstance(watchlist, str) else list(watchlist or ())
    out: List[str] = []
    for token in raw:
        tk = str(token).strip().upper()
        if tk and tk not in out:
            out.append(tk)
    return tuple(out)


def _as_rows(payload: Any) -> List[Dict[str, Any]]:
    """FMP returns a JSON array of rows (or, for a single object, a bare dict). Normalise to a
    list of dict rows. Raises ``ValueError`` on a payload that is neither."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("FMP payload must be a JSON array or object")


def _num(row: Dict[str, Any], key: str) -> Optional[float]:
    """A finite float FMP actually returned under ``key`` (else None -- never fabricated)."""
    if key not in row:
        return None
    value = row.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / inf -> honest absence
        return None
    return out


def _pct_change(latest: Optional[float], prior: Optional[float]) -> Optional[float]:
    """Period-over-period percent change (pp), or None when either period is absent / zero."""
    if latest is None or prior is None or prior == 0.0:
        return None
    return round((latest - prior) / abs(prior) * 100.0, 4)


def _pp_delta(latest: Optional[float], prior: Optional[float]) -> Optional[float]:
    """Percentage-point delta between two RATIOS (each a fraction), or None when either absent."""
    if latest is None or prior is None:
        return None
    return round((latest - prior) * 100.0, 4)


def _days_between(as_of: str, now: str) -> Optional[int]:
    """Whole days from ``as_of`` (YYYY-MM-DD) to ``now`` (ISO). None if unparseable."""
    def _ordinal(text: str) -> Optional[int]:
        head = str(text or "")[:10]
        parts = head.split("-")
        if len(parts) != 3:
            return None
        try:
            y, m, d = (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
        import datetime  # stdlib; deterministic from the two strings (no wall-clock)
        try:
            return datetime.date(y, m, d).toordinal()
        except ValueError:
            return None

    a = _ordinal(as_of)
    b = _ordinal(now)
    if a is None or b is None:
        return None
    return b - a


def _freshness_from_age(as_of: str, now: str) -> str:
    """A freshness LABEL from FMP's as-of date vs the injected ``now`` (never a number)."""
    days = _days_between(as_of, now)
    if days is None:
        return "unknown"
    if days < 0:
        return "unknown"          # a future-dated period: honestly not classified
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
    safe under the offline test kill-switch. ``time`` is imported lazily; a test may swap
    ``_sleep`` / ``_monotonic`` to avoid any real sleep.
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
    """The ``fetch_checked`` boundary for the live adapter with the base network refusal disarmed.

    021A IS a production network path (mirroring 020B). No ambient import-time network is
    possible: the real transport is function-local and tests inject a mock. So this view re-runs
    the base boundary with the SAME descriptor except ``network_required=False`` (the blanket
    refusal is disarmed); every OTHER check -- RealityEvents only, authority / raw-ref /
    provenance per event, honest counts, failure -> gap -- still runs unchanged.
    """

    def __init__(self, outer: "FmpLiveAdapter",
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
FMP_LIVE_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=FMP_LIVE_ADAPTER_ID,
    source_name="Financial Modeling Prep live financial data (financialmodelingprep.com)",
    source_type="financial_data",
    source_authority=FMP_LIVE_SOURCE_AUTHORITY,   # commercial provider = convenience tier
    credential_requirements=("FMP_API_KEY",),     # env var NAME only, never a value
    network_required=True,                        # 021A is the SECOND production live path
    rate_limit_policy=(
        "FMP plan rate / daily quota is honoured by a conservative in-adapter spacing limiter; "
        "an HTTP 429 / 403 (or quota / rate-limit-shaped response) is surfaced as rate_limited "
        "(rate_limit_status=throttled), never retried inside a pulse, never hidden"),
    outputs=FMP_LIVE_EVENT_TYPES,
    claim_status_rules=(
        "every FMP datum (profile / income / balance / cash-flow / ratios / quote) -> "
        "source_authority=convenience (the commercial_provider tier) + claim_status="
        "reported_claim (provider-reported) -- NEVER canonical, NEVER a verified_fact",
        "FMP is a commercial provider: financial / market CONTEXT, never a canonical regulatory "
        "truth and never an investment conclusion -- a high-context read a downstream agent MAY "
        "interpret, never a signal / thesis / trade",
        "authority is assigned immediately PER RECORD and is preserved: a provider (convenience) "
        "read can NEVER outrank an SEC filing (canonical > convenience)",
        "on a same-fact SEC/FMP contradiction BOTH sides are preserved (never averaged) and the "
        "contradiction is routed to Trust / Data Quality -- a provider number never overwrites "
        "an SEC filing fact",
    ),
    failure_modes=(
        "credentials_missing", "rate_limited", "source_unavailable", "parse_error"),
    description=(
        "FMP (Financial Modeling Prep) live financial-data adapter -- the SECOND production LIVE "
        "source and the first COMMERCIAL provider. Reads FMP's profile / statements / ratios / "
        "(opt-in) quote endpoints per ticker via an injectable transport (the default real "
        "transport is built lazily from evidence_ingestion.live_transport; no network on "
        "import), normalises each into a convenience/provider-reported financial_inflection "
        "RealityEvent with provenance + freshness, and turns every fetch failure into a VISIBLE "
        "gap. Provider CONTEXT, never canonical, never outranks SEC. Labels not scores; no "
        "scheduler / broker / trading / scoring."),
)


# --------------------------------------------------------------------------- #
# FmpLiveAdapter                                                               #
# --------------------------------------------------------------------------- #
class FmpLiveAdapter(SourceAdapter):
    """FMP live financial data -> convenience/provider-reported financial_inflection
    RealityEvents. Honest gaps; no fixture fallback; never outranks SEC.

    ``transport`` is an INJECTABLE dict of endpoint callables (keys in
    :data:`FMP_LIVE_TRANSPORT_KEYS`), each ``fetch(symbol) -> decoded payload``. When
    ``transport`` is ``None`` the DEFAULT real transport is built lazily inside
    :meth:`_default_transport` (from ``evidence_ingestion.live_transport``; import-time is
    network-free). ``fmp_api_key_present`` is a PRESENCE flag only (True / False / None=infer
    from wiring); a credential VALUE passed by mistake is rejected without being stored or
    echoed. ``enable_quote`` (default False) must be explicitly set for the live quote endpoint
    to be CALLED.
    """

    def __init__(self, transport: Optional[Dict[str, Any]] = None, *,
                 fmp_api_key_present: Optional[bool] = None,
                 timeout_s: float = 20.0, max_retries: int = 2,
                 enable_quote: bool = False) -> None:
        if transport is not None:
            if not isinstance(transport, dict):
                raise ValueError(
                    "FmpLiveAdapter transport must be a dict of endpoint callables "
                    "(keys: {0})".format(", ".join(FMP_LIVE_TRANSPORT_KEYS)))
            for key, fetch in transport.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(
                        "FmpLiveAdapter transport keys must be non-empty endpoint names "
                        "(e.g. 'profile')")
                if not callable(fetch):
                    raise ValueError(
                        "FmpLiveAdapter transport[{0!r}] must be a callable fetch (the injected "
                        "transport shape)".format(key))
        if (fmp_api_key_present is not None
                and not isinstance(fmp_api_key_present, bool)):
            # NEVER echo the offending argument: it may BE the credential value.
            raise ValueError(
                "FmpLiveAdapter.fmp_api_key_present is a PRESENCE flag (True/False/None) -- "
                "never pass the credential value; the argument was rejected and has not been "
                "stored")
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise ValueError("FmpLiveAdapter.timeout_s must be a number of seconds")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("FmpLiveAdapter.max_retries must be a non-negative int")
        if not isinstance(enable_quote, bool):
            raise ValueError("FmpLiveAdapter.enable_quote must be a bool")

        self._transport = dict(transport) if transport is not None else None
        self._fmp_present = fmp_api_key_present
        self._timeout_s = float(timeout_s)
        self._max_retries = int(max_retries)
        self._enable_quote = bool(enable_quote)
        self._limiter = _SpacingLimiter()
        self._boundary = _TransportBoundary(
            self, replace(FMP_LIVE_DESCRIPTOR, network_required=False))

    # -- identity ----------------------------------------------------------- #
    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return FMP_LIVE_DESCRIPTOR

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        return FMP_LIVE_DISCIPLINES

    def __repr__(self) -> str:  # presence labels only -- a credential value never exists here
        wired = sorted(self._transport) if self._transport is not None else "default_real"
        return ("FmpLiveAdapter(transport={0}, fmp_api_key_present={1}, "
                "enable_quote={2})".format(wired, self._fmp_present, self._enable_quote))

    # -- the transport gate over fetch_checked ------------------------------ #
    def fetch_checked(self, *, watchlist=(), themes=(),
                      now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Fetch with the 013 boundary enforced. 021A is a production network path, so the base
        blanket network refusal is disarmed; every other contract check still runs. In tests a
        mock transport is injected and the real path is never reached; in production a wired
        transport + a supplied API key reach the wire lazily."""
        return self._boundary.fetch_checked(watchlist=watchlist, themes=themes, now=now)

    # -- the DEFAULT real transport, built lazily (NO network on import) ----- #
    def _default_transport(self) -> Optional[Dict[str, Any]]:
        """Build the real FMP transport lazily. Returns ``None`` when the FMP_API_KEY env var is
        absent (a credentials gap for the caller -- never a crash, never a leak). The value
        transits only into the transport builder and is never stored / logged / echoed. NEVER
        exercised by the offline test suite."""
        import os  # lazy; NOT a network import
        from evidence_ingestion.live_transport import fmp_live_transport  # lazy boundary
        api_key = os.environ.get("FMP_API_KEY", "")
        if not api_key:
            return None
        return fmp_live_transport(api_key, timeout=self._timeout_s)

    # -- fetch --------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Pull each ticker's FMP resources via the transport into provider-reported
        RealityEvents + an honest result. Deterministic; a mock transport keeps it OFFLINE. A
        missing credential skips with a visible gap; a raising transport is captured as
        rate_limited / source_unavailable and the OTHER tickers continue (partial); a malformed
        payload is a parse_error. Never fabricates; never falls back to fixture/demo data."""
        state = {"rate_limited": False, "unavailable": False, "parse_failed": False}
        events: List[RealityEvent] = []
        refs: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        gaps: List[str] = []

        tickers = _normalise_tickers(watchlist)
        if not tickers:
            gaps.append(
                "empty watchlist: the FMP live adapter fetches per ticker and was given none -- "
                "nothing fetched, nothing fabricated")
            return (), self._result("skipped", refs, events, warnings, errors, gaps, state, now)

        # Credentials as a PRESENCE label -- never a value. A false flag SKIPS the fetch.
        if self._fmp_present is False:
            gaps.append(
                "FMP_API_KEY missing (presence flag false): FMP live fetch skipped this pulse -- "
                "financial context has NO coverage; visible gap (credentials_missing), nothing "
                "fabricated, no silent fixture/demo fallback")
            return (), self._result("skipped", refs, events, warnings, errors, gaps, state, now)

        transport = self._transport
        if transport is None:
            transport = self._default_transport()
            if transport is None:
                gaps.append(
                    "FMP_API_KEY missing (no value available to build the live transport): FMP "
                    "live fetch skipped this pulse -- visible gap (credentials_missing), nothing "
                    "fabricated, no silent fixture/demo fallback")
                return (), self._result(
                    "skipped", refs, events, warnings, errors, gaps, state, now)

        for ticker in tickers:
            events.extend(self._ticker_events(
                ticker, transport, refs, errors, gaps, state, now))

        problems = state["rate_limited"] or state["unavailable"] or state["parse_failed"]
        if events:
            status = "partial" if problems else "success"
        elif problems:
            status = "failed"
        else:
            status = "partial"
            gaps.append(
                "FMP live delivered no financial events for {0} -- visible gap, nothing "
                "fabricated (no FMP coverage / empty payloads)".format(", ".join(tickers)))

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, state, now)

    # -- one ticker's endpoints -> provider-reported events ------------------ #
    def _ticker_events(self, ticker: str, transport: Dict[str, Any], refs: List[str],
                       errors: List[str], gaps: List[str], state: Dict[str, bool],
                       now: str) -> List[RealityEvent]:
        out: List[RealityEvent] = []

        # (endpoint key, builder). ``quote`` is only CALLED when explicitly enabled.
        plan: Tuple[Tuple[str, Callable[..., Optional[RealityEvent]]], ...] = (
            ("profile", self._profile_event),
            ("income_statement", self._income_event),
            ("balance_sheet", self._balance_event),
            ("cash_flow", self._cashflow_event),
            ("ratios", self._ratios_event),
        )
        for key, builder in plan:
            payload = self._call(transport, key, ticker, errors, gaps, state)
            if payload is None:
                continue
            event = self._guarded_build(
                key, builder, ticker, payload, refs, errors, gaps, state, now)
            if event is not None:
                out.append(event)

        if self._enable_quote:
            payload = self._call(transport, "quote", ticker, errors, gaps, state)
            if payload is not None:
                event = self._guarded_build(
                    "quote", self._quote_event, ticker, payload, refs, errors, gaps, state, now)
                if event is not None:
                    out.append(event)
        return out

    def _guarded_build(self, key: str, builder, ticker: str, payload: Any, refs: List[str],
                       errors: List[str], gaps: List[str], state: Dict[str, bool],
                       now: str) -> Optional[RealityEvent]:
        ref = _payload_ref("fmp_{0}".format(key), ticker, payload)
        try:
            event = builder(ticker, payload, ref, now, gaps)
        except Exception as exc:            # noqa: BLE001 -- malformed -> visible parse gap
            state["parse_failed"] = True
            errors.append("parse_error: {0} {1}: {2}: {3}".format(
                key, ticker, type(exc).__name__, exc))
            gaps.append(
                "malformed FMP {0} payload for {1} (parse_error): provider context has NO "
                "coverage for that resource this pulse -- visible gap, nothing fabricated".format(
                    key, ticker))
            return None
        if event is None:
            return None
        refs.append(ref)
        return event

    # -- one guarded, rate-limit-conscious transport call --------------------- #
    def _call(self, transport: Dict[str, Any], key: str, ticker: str,
              errors: List[str], gaps: List[str], state: Dict[str, bool]) -> Any:
        fetch = transport.get(key)
        if fetch is None:
            gaps.append(
                "FMP transport {0} not wired: its payloads are missing this pulse -- visible "
                "gap, nothing fabricated".format(key))
            return None
        self._limiter.acquire()     # pace below FMP's plan rate (real path)
        try:
            return fetch(ticker)
        except Exception as exc:    # noqa: BLE001 -- failure becomes a gap, never a crash
            reason = "{0}: {1}".format(type(exc).__name__, exc)
            if _is_rate_limit_error(exc):
                state["rate_limited"] = True
                errors.append("rate_limited: {0} {1}: {2}".format(key, ticker, reason))
                gaps.append(
                    "rate limit / quota / access throttle (HTTP 429/403) hit on FMP {0} for {1}: "
                    "payload missing this pulse -- limit honoured (NOT retried in-pulse); visible "
                    "gap, nothing fabricated".format(key, ticker))
            else:
                state["unavailable"] = True
                errors.append("source_unavailable: {0} {1}: {2}".format(key, ticker, reason))
                gaps.append(
                    "FMP source {0} unavailable / timed out for {1}: payload missing this pulse "
                    "-- visible gap, nothing fabricated, no silent fixture/demo fallback".format(
                        key, ticker))
            return None

    # -- event builders (all convenience / provider-reported) ---------------- #
    def _event(self, ticker: str, event_type: str, slug: str, observed_fact: str,
               numeric_values: Tuple[Tuple[str, object, str], ...], as_of: str,
               endpoint: str, ref: str, now: str, half_life: str,
               event_gaps: Tuple[str, ...] = ()) -> RealityEvent:
        source_refs = tuple(dict.fromkeys(
            r for r in (
                "fmp:endpoint/{0}".format(endpoint),
                "fmp:symbol/{0}".format(ticker),
                ref,
            ) if r))
        evidence_refs = ("fmp:{0}/{1}".format(endpoint, ticker),)
        return RealityEvent(
            event_id="fmplive.{0}.{1}.{2}".format(
                ticker.lower(), slug, _sha12(ticker, event_type, as_of)),
            timestamp=as_of or now,
            source_id="fmp.live",
            source_type=event_type,
            source_authority=FMP_LIVE_SOURCE_AUTHORITY,   # convenience: assigned immediately
            claim_status=FMP_LIVE_CLAIM_STATUS,           # reported_claim (provider-reported)
            raw_payload_ref=ref,
            discipline="financial_inflection",
            event_type=event_type,
            affected_companies=(ticker,),
            observed_fact=observed_fact,
            numeric_values=numeric_values,
            evidence_refs=evidence_refs,
            source_refs=source_refs,
            confidence_label="low",                       # provider context, not verified
            freshness_label=_freshness_from_age(as_of, now),
            half_life=half_life,
            data_gaps=event_gaps,
        )

    def _profile_event(self, ticker: str, payload: Any, ref: str, now: str,
                       gaps: List[str]) -> Optional[RealityEvent]:
        rows = _as_rows(payload)
        if not rows:
            gaps.append("FMP profile for {0} carried no company row -- visible gap, nothing "
                        "fabricated".format(ticker))
            return None
        row = rows[0]
        name = str(row.get("companyName") or row.get("symbol") or ticker)
        sector = str(row.get("sector") or "").strip()
        industry = str(row.get("industry") or "").strip()
        nums: List[Tuple[str, object, str]] = []
        for key, metric, unit in (("mktCap", "market_cap_usd", "usd"),
                                   ("price", "price_usd", "usd")):
            value = _num(row, key)
            if value is not None:
                nums.append((metric, value, unit))
        descriptor = " -- ".join(p for p in (sector, industry) if p) or "profile"
        return self._event(
            ticker, "fmp_company_profile", "profile",
            "FMP company profile: {0} ({1})".format(name, descriptor),
            tuple(nums), "", "profile", ref, now, "quarters",
            event_gaps=("FMP company profile is provider reference context (convenience / "
                        "reported_claim) -- not a canonical filing, never a verified fact",))

    def _statement_rows(self, ticker: str, payload: Any, kind: str,
                        gaps: List[str]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]:
        rows = _as_rows(payload)
        if not rows:
            gaps.append("FMP {0} for {1} carried no period rows -- visible gap, nothing "
                        "fabricated".format(kind, ticker))
            return None, None, ""
        latest = rows[0]
        prior = rows[1] if len(rows) > 1 else None
        as_of = str(latest.get("date") or latest.get("fillingDate") or "")[:10]
        return latest, prior, as_of

    def _income_event(self, ticker: str, payload: Any, ref: str, now: str,
                      gaps: List[str]) -> Optional[RealityEvent]:
        latest, prior, as_of = self._statement_rows(ticker, payload, "income statement", gaps)
        if latest is None:
            return None
        nums: List[Tuple[str, object, str]] = []
        for key, metric, unit in (("revenue", "revenue_usd", "usd"),
                                   ("grossProfit", "gross_profit_usd", "usd"),
                                   ("operatingIncome", "operating_income_usd", "usd"),
                                   ("netIncome", "net_income_usd", "usd")):
            value = _num(latest, key)
            if value is not None:
                nums.append((metric, value, unit))
        # FMP-returned ratios (fractions) -> percent context figures.
        gm_l, gm_p = _num(latest, "grossProfitRatio"), _num(prior or {}, "grossProfitRatio")
        om_l, om_p = _num(latest, "operatingIncomeRatio"), _num(prior or {}, "operatingIncomeRatio")
        if gm_l is not None:
            nums.append(("gross_margin_pct", round(gm_l * 100.0, 4), "pct"))
        if om_l is not None:
            nums.append(("operating_margin_pct", round(om_l * 100.0, 4), "pct"))
        # Provider-derived period-over-period margin DELTAS (pp) -- sensor-readable inflections.
        event_gaps: List[str] = []
        gm_delta = _pp_delta(gm_l, gm_p)
        om_delta = _pp_delta(om_l, om_p)
        if gm_delta is not None:
            nums.append(("gross_margin_delta_pct", gm_delta, "pct"))
        if om_delta is not None:
            nums.append(("operating_margin_delta_pct", om_delta, "pct"))
        if gm_delta is not None or om_delta is not None:
            event_gaps.append(FMP_DERIVED_DELTA_NOTE)
        elif prior is None:
            event_gaps.append(
                "only one FMP income period returned for {0} -- period-over-period margin delta "
                "not computable (gap, never fabricated)".format(ticker))
        return self._event(
            ticker, "fmp_income_statement_snapshot", "income",
            "FMP income-statement snapshot for {0} (provider-reported)".format(ticker),
            tuple(nums), as_of, "income_statement", ref, now, "quarters",
            event_gaps=tuple(event_gaps))

    def _balance_event(self, ticker: str, payload: Any, ref: str, now: str,
                       gaps: List[str]) -> Optional[RealityEvent]:
        latest, prior, as_of = self._statement_rows(ticker, payload, "balance sheet", gaps)
        if latest is None:
            return None
        nums: List[Tuple[str, object, str]] = []
        for key, metric, unit in (("totalDebt", "total_debt_usd", "usd"),
                                   ("cashAndCashEquivalents", "cash_usd", "usd"),
                                   ("totalStockholdersEquity", "equity_usd", "usd")):
            value = _num(latest, key)
            if value is not None:
                nums.append((metric, value, unit))
        # net debt (provider-derived from FMP-returned totals) + its period-over-period change.
        def _net_debt(row: Optional[Dict[str, Any]]) -> Optional[float]:
            if row is None:
                return None
            debt = _num(row, "totalDebt")
            cash = _num(row, "cashAndCashEquivalents")
            if debt is None or cash is None:
                return None
            return debt - cash
        nd_l, nd_p = _net_debt(latest), _net_debt(prior)
        event_gaps: List[str] = []
        if nd_l is not None:
            nums.append(("net_debt_usd", round(nd_l, 4), "usd"))
        nd_change = _pct_change(nd_l, nd_p)
        if nd_change is not None:
            nums.append(("net_debt_change_pct", nd_change, "pct"))
            event_gaps.append(FMP_DERIVED_DELTA_NOTE)
        elif prior is None:
            event_gaps.append(
                "only one FMP balance-sheet period returned for {0} -- net-debt change not "
                "computable (gap, never fabricated)".format(ticker))
        return self._event(
            ticker, "fmp_balance_sheet_snapshot", "balance",
            "FMP balance-sheet snapshot for {0} (provider-reported)".format(ticker),
            tuple(nums), as_of, "balance_sheet", ref, now, "quarters",
            event_gaps=tuple(event_gaps))

    def _cashflow_event(self, ticker: str, payload: Any, ref: str, now: str,
                        gaps: List[str]) -> Optional[RealityEvent]:
        latest, prior, as_of = self._statement_rows(ticker, payload, "cash-flow statement", gaps)
        if latest is None:
            return None
        nums: List[Tuple[str, object, str]] = []
        for key, metric, unit in (("freeCashFlow", "free_cash_flow_usd", "usd"),
                                   ("operatingCashFlow", "operating_cash_flow_usd", "usd"),
                                   ("capitalExpenditure", "capex_usd", "usd")):
            value = _num(latest, key)
            if value is not None:
                nums.append((metric, value, unit))
        event_gaps: List[str] = []
        fcf_delta = _pct_change(_num(latest, "freeCashFlow"), _num(prior or {}, "freeCashFlow"))
        capex_change = _pct_change(
            _num(latest, "capitalExpenditure"), _num(prior or {}, "capitalExpenditure"))
        if fcf_delta is not None:
            nums.append(("fcf_delta_pct", fcf_delta, "pct"))
        if capex_change is not None:
            nums.append(("capex_change_pct", capex_change, "pct"))
        if fcf_delta is not None or capex_change is not None:
            event_gaps.append(FMP_DERIVED_DELTA_NOTE)
        elif prior is None:
            event_gaps.append(
                "only one FMP cash-flow period returned for {0} -- FCF / capex change not "
                "computable (gap, never fabricated)".format(ticker))
        return self._event(
            ticker, "fmp_cash_flow_snapshot", "cashflow",
            "FMP cash-flow snapshot for {0} (provider-reported)".format(ticker),
            tuple(nums), as_of, "cash_flow", ref, now, "quarters",
            event_gaps=tuple(event_gaps))

    def _ratios_event(self, ticker: str, payload: Any, ref: str, now: str,
                      gaps: List[str]) -> Optional[RealityEvent]:
        latest, _prior, as_of = self._statement_rows(ticker, payload, "ratios", gaps)
        if latest is None:
            return None
        nums: List[Tuple[str, object, str]] = []
        for key, metric, unit in (("currentRatio", "current_ratio", "ratio"),
                                   ("debtEquityRatio", "debt_equity_ratio", "ratio"),
                                   ("returnOnEquity", "return_on_equity_ratio", "ratio")):
            value = _num(latest, key)
            if value is not None:
                nums.append((metric, value, unit))
        return self._event(
            ticker, "fmp_key_ratios_snapshot", "ratios",
            "FMP key-ratios snapshot for {0} (provider-reported)".format(ticker),
            tuple(nums), as_of, "ratios", ref, now, "quarters",
            event_gaps=("FMP key ratios are provider context (convenience / reported_claim) -- "
                        "not a canonical filing, never a verified fact",))

    def _quote_event(self, ticker: str, payload: Any, ref: str, now: str,
                     gaps: List[str]) -> Optional[RealityEvent]:
        rows = _as_rows(payload)
        if not rows:
            gaps.append("FMP quote for {0} carried no row -- visible gap, nothing "
                        "fabricated".format(ticker))
            return None
        row = rows[0]
        nums: List[Tuple[str, object, str]] = []
        for key, metric, unit in (("price", "price_usd", "usd"),
                                   ("marketCap", "market_cap_usd", "usd"),
                                   ("volume", "volume_shares", "shares")):
            value = _num(row, key)
            if value is not None:
                nums.append((metric, value, unit))
        return self._event(
            ticker, FMP_LIVE_QUOTE_EVENT_TYPE, "quote",
            "FMP live quote for {0} (provider-reported market context)".format(ticker),
            tuple(nums), "", "quote", ref, now, "days",
            event_gaps=("FMP live quote is provider market context (convenience / "
                        "reported_claim) -- never a canonical fact, opt-in via enable_quote",))

    # -- result builder -------------------------------------------------------- #
    def _result(self, status: str, refs: List[str], events: List[RealityEvent],
                warnings: List[str], errors: List[str], gaps: List[str],
                state: Dict[str, bool], now: str) -> SourceAdapterResult:
        creds_missing = (status == "skipped"
                         and any("credentials_missing" in g for g in gaps))
        if creds_missing:
            health = "credentials_missing"
            credentials = "missing"
        elif state["rate_limited"]:
            health = "rate_limited"
            credentials = "present"
        elif status == "success":
            health = "healthy"
            credentials = "present"
        elif status == "partial":
            health = "degraded"
            credentials = "present"
        elif status == "skipped":
            health = "source_unavailable"
            credentials = "present"
        else:
            health = "failed"
            credentials = "present"
        run_id = deterministic_adapter_run_id(
            FMP_LIVE_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=FMP_LIVE_ADAPTER_ID,
            run_id=run_id,
            status=status,
            raw_payload_refs=tuple(dict.fromkeys(refs)),
            events_created=len(events),
            warnings=tuple(dict.fromkeys(warnings)),
            errors=tuple(dict.fromkeys(errors)),
            data_gaps=tuple(dict.fromkeys(gaps)),
            credentials_status=credentials,
            rate_limit_status="throttled" if state["rate_limited"] else "ok",
            source_health=health)
