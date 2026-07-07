"""The ONE designated network boundary for evidence ingestion (IMPLEMENTATION-010D).

This module -- and ONLY this module in the whole ``evidence_ingestion`` package --
may reach the wire. Every network access here is:

* **Lazy.** ``urllib.request`` / ``urllib.parse`` are imported INSIDE the fetch
  functions, never at module top. Importing this module touches NO network and pulls
  in NO network library, so ``import evidence_ingestion.live_transport`` is inert.
* **Explicitly authorised.** Nothing here runs unless a caller (the on-demand real
  terrain builder, itself gated behind ``--mode real_evidence_on_demand``) calls one
  of these constructors and then invokes the returned callable. The inert 009B/C/D
  clients (``sec_client`` / ``fmp_client`` / ``yfinance_client``) never import this
  module; the demo and fixture code paths never import it either.
* **Credential-safe.** Credentials are EXPLICIT arguments (from env/config resolved
  by the CLI, never here): ``sec_http_transport`` REQUIRES a descriptive SEC
  User-Agent (a contact identity, NOT a secret) and raises ``ValueError`` when it is
  missing -- no hidden personal-info default. ``fmp_http_transport`` REQUIRES an API
  key. This module reads NO environment variable and holds NO literal key. It NEVER
  logs / prints a credential.

The transports produced here plug straight into the EXISTING inert clients
(``SecEdgarClient(user_agent, transport=...)`` etc.), so all URL construction,
User-Agent handling and rate-limit hooks stay in the audited 009B/C/D clients; this
module only supplies the actual HTTP fetch they were designed to receive.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional, Tuple

# data.sec.gov ticker -> CIK map (public, no key). Fetched lazily, once, per builder.
_SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
# data.sec.gov per-company submissions (recent filings) document (public, no key).
_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
# Financial Modeling Prep (FMP) live endpoints (COMMERCIAL provider -- requires an API key).
# FMP is the CONVENIENCE tier of the authority ladder: financial / market CONTEXT, NEVER a
# canonical regulatory truth, and it can never outrank SEC. The key is threaded through the
# query string exactly once and is NEVER logged / printed / stored here.
#
# FMP retired the legacy ``/api/v3/`` endpoints ("Legacy Endpoint : no longer supported",
# HTTP 403); the CURRENT surface is ``/stable`` with the symbol passed as the ``symbol``
# QUERY parameter (not a path segment). Every endpoint returns a JSON array of records.
_FMP_BASE = "https://financialmodelingprep.com/stable"
_FMP_ENDPOINT_PATHS = {
    "profile": "profile?symbol={symbol}",
    "income_statement": "income-statement?symbol={symbol}&limit=2",
    "balance_sheet": "balance-sheet-statement?symbol={symbol}&limit=2",
    "cash_flow": "cash-flow-statement?symbol={symbol}&limit=2",
    "ratios": "ratios?symbol={symbol}&limit=2",
    "quote": "quote?symbol={symbol}",
}

# Public Yahoo query endpoints (fallback / research-only OHLCV + quote; no key).
_YF_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
_YF_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range=1mo&interval=1d")
# The PRICE-HISTORY fallback chart endpoint used by the 021-series Yahoo price adapter
# (PROD-LIVE-2). Public, NO key: a FALLBACK-tier research-only OHLCV source, always below
# FMP convenience and SEC canonical. ``range`` / ``interval`` are query params.
_YF_CHART_HISTORY_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range={range}&interval={interval}")
# A descriptive (public) research User-Agent -- a courtesy identity, NOT a secret. Yahoo's
# public chart endpoint needs no key; a UA merely avoids a bare/blocked request.
_YF_CHART_USER_AGENT = (
    "CosmosIQ-research/1.0 (price-history fallback; research-only; contact: operator-set)")

_MISSING_UA_MSG = (
    "SEC requires a descriptive User-Agent (set SEC_USER_AGENT or pass "
    "sec_user_agent=); it is a contact identity, not a secret, and there is NO "
    "hidden default -- refusing to issue an unidentified request")
_MISSING_KEY_MSG = (
    "FMP requires an API key (set FMP_API_KEY or pass fmp_api_key=); this module "
    "reads no environment variable and holds no literal key")


def _http_get(url: str, headers: Optional[Dict[str, str]] = None,
              timeout: float = 20.0) -> str:
    """Lazy, minimal HTTP GET returning the decoded body. urllib is imported HERE."""
    import urllib.request  # LAZY -- import-time is network-free by construction.

    req = urllib.request.Request(url, headers=dict(headers or {}))
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - audited boundary
        raw = resp.read()
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw)


# --------------------------------------------------------------------------- #
# Per-source transport factories (each returns a client-shaped callable).      #
# --------------------------------------------------------------------------- #
def sec_http_transport(user_agent: str) -> Callable[[str, Dict[str, str]], str]:
    """Return a ``transport(url, headers) -> body`` for :class:`SecEdgarClient`.

    ``user_agent`` (a contact identity) is REQUIRED; a falsy value raises
    ``ValueError`` before any network is possible. urllib is imported lazily inside
    the returned closure.
    """
    if not user_agent:
        raise ValueError(_MISSING_UA_MSG)

    def _transport(url: str, headers: Dict[str, str]) -> str:
        return _http_get(url, headers=headers)

    return _transport


def sec_live_transport(
    user_agent: str, *, timeout: float = 20.0
) -> Dict[str, Callable[..., Any]]:
    """Build the SEC-only per-endpoint fetch bundle for the live filings adapter (020B).

    Returns a dict of two ``callable``s that the ``SecEdgarLiveAdapter`` injects:

    * ``"company_tickers"`` -> ``fetch() -> decoded ticker->CIK map`` (the public
      ``company_tickers.json``; no key);
    * ``"submissions"`` -> ``fetch(cik) -> decoded submissions document`` (the public
      ``data.sec.gov/submissions/CIK<cik>.json``; no key).

    ``user_agent`` (a contact identity, NOT a secret) is REQUIRED; a falsy value raises
    ``ValueError`` before any network is possible. ``urllib`` is imported lazily inside
    :func:`_http_get`, so importing this module remains network-free.
    """
    if not user_agent:
        raise ValueError(_MISSING_UA_MSG)
    headers = {"User-Agent": user_agent}

    def _company_tickers() -> Any:
        return json.loads(_http_get(_SEC_TICKER_MAP_URL, headers=headers, timeout=timeout))

    def _submissions(cik: str) -> Any:
        url = _SEC_SUBMISSIONS_URL.format(cik=str(cik).zfill(10))
        return json.loads(_http_get(url, headers=headers, timeout=timeout))

    return {"company_tickers": _company_tickers, "submissions": _submissions}


def fmp_live_transport(
    api_key: str, *, timeout: float = 20.0
) -> Dict[str, Callable[..., Any]]:
    """Build the FMP-only per-endpoint fetch bundle for the live financial adapter (021A).

    Returns a dict of ``callable``s the :class:`FmpLiveAdapter` injects, one per endpoint
    (``"profile"`` / ``"income_statement"`` / ``"balance_sheet"`` / ``"cash_flow"`` /
    ``"ratios"`` / ``"quote"``), each ``fetch(symbol) -> decoded JSON``.

    ``api_key`` is REQUIRED; a falsy value raises ``ValueError`` before any network is
    possible. FMP is a COMMERCIAL provider (the CONVENIENCE tier) -- financial / market
    CONTEXT, never a canonical regulatory truth. The key is threaded through the query string
    exactly once and is NEVER logged / printed / stored. ``urllib`` is imported lazily inside
    :func:`_http_get`, so importing this module remains network-free.
    """
    if not api_key:
        raise ValueError(_MISSING_KEY_MSG)

    def _make(path_template: str) -> Callable[[str], Any]:
        def _fetch(symbol: str) -> Any:
            path = path_template.format(symbol=str(symbol).strip().upper())
            sep = "&" if "?" in path else "?"
            url = "{0}/{1}{2}apikey={3}".format(_FMP_BASE, path, sep, api_key)
            return json.loads(_http_get(url, timeout=timeout))
        return _fetch

    return {key: _make(tmpl) for key, tmpl in _FMP_ENDPOINT_PATHS.items()}


def yahoo_chart_transport(
    *, timeout: float = 20.0, chart_range: str = "6mo", interval: str = "1d"
) -> Dict[str, Callable[..., Any]]:
    """Build the Yahoo-only chart fetch bundle for the FALLBACK price-history adapter (PROD-LIVE-2).

    Returns a dict with ONE callable the :class:`YahooPriceLiveAdapter` injects:

    * ``"chart"`` -> ``fetch(symbol) -> decoded chart JSON`` (Yahoo's public
      ``query1.finance.yahoo.com/v8/finance/chart/<SYMBOL>?range=6mo&interval=1d``; NO key).

    Yahoo price data is the FALLBACK tier of the authority ladder -- research-only OHLCV for
    technicals, strictly BELOW FMP convenience and SEC canonical, never a canonical/verified
    fact. NO credential is required or read (there is no key to leak). ``urllib`` is imported
    lazily inside :func:`_http_get`, so importing this module remains network-free.
    """
    headers = {"User-Agent": _YF_CHART_USER_AGENT}

    def _chart(symbol: str) -> Any:
        url = _YF_CHART_HISTORY_URL.format(
            symbol=str(symbol).strip().upper(), range=chart_range, interval=interval)
        return json.loads(_http_get(url, headers=headers, timeout=timeout))

    return {"chart": _chart}


def fmp_http_transport(api_key: str) -> Callable[[str, Dict[str, Any]], str]:
    """Return a ``transport(url, params) -> body`` for :class:`FmpClient`.

    ``api_key`` is REQUIRED; a falsy value raises ``ValueError`` before any network
    is possible. The key is threaded through the query string exactly as the client
    supplies it; it is never logged.
    """
    if not api_key:
        raise ValueError(_MISSING_KEY_MSG)

    def _transport(url: str, params: Dict[str, Any]) -> str:
        import urllib.parse  # LAZY

        query = urllib.parse.urlencode(dict(params or {}))
        full = url + ("&" if "?" in url else "?") + query if query else url
        return _http_get(full)

    return _transport


def yf_http_transport() -> Callable[[str, str], Any]:
    """Return a ``transport(symbol, kind) -> payload`` for :class:`YFinanceClient`.

    Fallback / research-only. Fetches a public Yahoo query endpoint (no key) and
    returns the decoded JSON payload. Yahoo's chart shape differs from the adapter's
    expected history shape, so this transport marks history as DEFERRED (returns a
    payload the adapter records as a gap) rather than fabricating OHLCV rows.
    """
    def _transport(symbol: str, kind: str) -> Any:
        if kind == "history":
            # A clean, narrow interface is provided, but reshaping Yahoo's chart
            # payload into the adapter's history schema is DEFERRED -- we never fake
            # rows. Return an empty-but-honest payload so the builder records a gap.
            return {str(symbol): {"history": []}}
        body = _http_get(_YF_QUOTE_URL.format(symbol=symbol))
        data = json.loads(body)
        results = (((data or {}).get("quoteResponse") or {}).get("result") or [])
        row = results[0] if results else {}
        return {
            "symbol": symbol,
            "currentPrice": row.get("regularMarketPrice"),
            "previousClose": row.get("regularMarketPreviousClose"),
            "marketCap": row.get("marketCap"),
            "sharesOutstanding": row.get("sharesOutstanding"),
            "currency": row.get("currency"),
            "exchange": row.get("fullExchangeName") or row.get("exchange"),
        }

    return _transport


# --------------------------------------------------------------------------- #
# CIK resolution + the payload-fetch bundle the builder injects.               #
# --------------------------------------------------------------------------- #
def _resolve_cik(ticker: str, user_agent: str) -> Optional[str]:
    """Resolve a ticker to its zero-padded 10-digit CIK via the public SEC map.

    Returns ``None`` (a data gap for the caller) when the ticker is not found. urllib
    is imported lazily inside ``_http_get``.
    """
    body = _http_get(_SEC_TICKER_MAP_URL, headers={"User-Agent": user_agent})
    table = json.loads(body)
    want = str(ticker).strip().upper()
    for row in (table.values() if isinstance(table, dict) else table):
        if str(row.get("ticker", "")).upper() == want:
            return str(row.get("cik_str", "")).zfill(10)
    return None


def _decode(payload: Any) -> Any:
    """Accept either a decoded object (mock) or a JSON string/bytes (real fetch)."""
    if isinstance(payload, (bytes, bytearray)):
        return json.loads(payload.decode("utf-8", "replace"))
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def build_live_transports(
    *,
    sec_user_agent: Optional[str] = None,
    fmp_api_key: Optional[str] = None,
    enable_yfinance: bool = False,
) -> Tuple[Dict[str, Callable[[str], Any]], Dict[str, str]]:
    """Build the per-payload fetch bundle + a per-source credential status map.

    The bundle maps a payload key (``sec_submissions`` / ``fmp_profile`` / ...) to a
    ``fetch(ticker) -> payload_or_None`` closure. Each closure lazily imports the
    inert client, injects the matching live transport, and returns the decoded
    payload. Sources whose credentials are absent are simply not wired and are
    reported in the status map (``credentials_missing`` / ``deferred``) so the builder
    surfaces an honest data gap instead of a silent skip or a crash-with-leak.
    """
    from .sec_client import SecEdgarClient
    from .fmp_client import FmpClient
    from .yfinance_client import YFinanceClient

    transports: Dict[str, Callable[[str], Any]] = {}
    status: Dict[str, str] = {}

    # --- SEC (canonical) ---------------------------------------------------- #
    if sec_user_agent:
        sec_client = SecEdgarClient(
            user_agent=sec_user_agent, transport=sec_http_transport(sec_user_agent))
        cik_cache: Dict[str, Optional[str]] = {}

        def _cik(ticker: str) -> Optional[str]:
            if ticker not in cik_cache:
                cik_cache[ticker] = _resolve_cik(ticker, sec_user_agent)
            return cik_cache[ticker]

        def _sec_submissions(ticker: str) -> Any:
            cik = _cik(ticker)
            if not cik:
                return None
            return _decode(sec_client.fetch_submissions(cik))

        def _sec_companyfacts(ticker: str) -> Any:
            cik = _cik(ticker)
            if not cik:
                return None
            return _decode(sec_client.fetch_companyfacts(cik))

        transports["sec_submissions"] = _sec_submissions
        transports["sec_companyfacts"] = _sec_companyfacts
        status["sec"] = "wired"
    else:
        status["sec"] = "credentials_missing"

    # --- FMP (convenience) -------------------------------------------------- #
    if fmp_api_key:
        fmp_client = FmpClient(
            api_key=fmp_api_key, transport=fmp_http_transport(fmp_api_key))

        def _fmp(kind: str) -> Callable[[str], Any]:
            def _fetch(ticker: str) -> Any:
                if kind == "profile":
                    return _decode(fmp_client.fetch_profile(ticker))
                if kind == "income":
                    return _decode(fmp_client.fetch_income_statement(ticker))
                return _decode(fmp_client.fetch_historical(ticker))
            return _fetch

        transports["fmp_profile"] = _fmp("profile")
        transports["fmp_income_statement"] = _fmp("income")
        transports["fmp_ohlcv"] = _fmp("historical")
        status["fmp"] = "wired"
    else:
        status["fmp"] = "credentials_missing"

    # --- yfinance (fallback / research-only) -------------------------------- #
    if enable_yfinance:
        yf_client = YFinanceClient(transport=yf_http_transport())

        def _yf_history(ticker: str) -> Any:
            return _decode(yf_client.fetch_history(ticker))

        def _yf_quote(ticker: str) -> Any:
            return _decode(yf_client.fetch_quote(ticker))

        transports["yf_history"] = _yf_history
        transports["yf_quote"] = _yf_quote
        status["yfinance"] = "wired"
    else:
        status["yfinance"] = "deferred"

    return transports, status
