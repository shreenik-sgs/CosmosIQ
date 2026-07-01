"""Optional live FMP client -- an inert INTERFACE, not a network implementation.

009C ships the client's orchestration only: it builds the financialmodelingprep.com
endpoint URLs, threads the caller-supplied API key through as a request parameter,
calls a rate-limit hook, and fails loudly when misconfigured. It contains NO network
code and NO environment / secret access:

* No network import anywhere (top-level or nested). The HTTP transport is a
  dependency-injected callable ``transport(url, params) -> bytes/str``; wiring a
  real urllib / requests transport is deferred to a later live-runner milestone.
  Without an injected transport the client cannot reach the wire.
* The FMP API key is an EXPLICIT runtime constructor argument. There is NO literal
  key anywhere, NO environment-variable read, and NO ``getattr(os, ...)`` / secret
  lookup. If ``api_key`` is falsy when a live fetch is attempted the client fails
  LOUDLY with ValueError rather than issuing an unauthenticated request -- before
  any network could be reached.
* Rate-limit / backoff is a stubbed no-op hook, not a production implementation.

Parsing of whatever a transport returns lives in ``fmp.py`` and needs no network --
so the entire default test run is network-free by construction. This interface is
never exercised by the default test suite.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


_PROFILE_URL = "https://financialmodelingprep.com/api/v3/profile/{symbol}"
_INCOME_URL = "https://financialmodelingprep.com/api/v3/income-statement/{symbol}"
_HISTORICAL_URL = "https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"

_MISSING_KEY_MSG = (
    "FmpClient has no api_key: pass api_key= (an explicit runtime argument) to "
    "enable a live fetch; the client reads no environment variable and holds no "
    "literal key"
)
_NO_TRANSPORT_MSG = (
    "FmpClient has no transport: inject transport(url, params) to enable a live "
    "fetch (009C ships the interface only; live HTTP is wired in a later step)"
)


def _noop_rate_limit_hook(url: str) -> None:
    """Stubbed rate-limit / backoff hook. A production client would sleep / backoff
    here per FMP's plan limits; the default is intentionally a no-op."""
    return None


class FmpClient:
    """Optional live-fetch INTERFACE for FMP -- inert unless given a key AND transport.

    Supply ``api_key`` (an explicit runtime argument) and a ``transport`` callable to
    enable live fetches. With either missing, the client cannot reach the network and
    any fetch raises ValueError.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        transport: Optional[Callable[[str, dict], Any]] = None,
        rate_limit_hook: Optional[Callable[[str], None]] = None,
    ) -> None:
        # api_key is a caller-provided runtime value -- NOT a literal, NOT read from
        # the environment. It may legitimately be None (the inert default).
        self.api_key = api_key
        self._transport = transport
        self._rate_limit_hook = rate_limit_hook or _noop_rate_limit_hook

    def _params(self) -> dict:
        if not self.api_key:
            raise ValueError(_MISSING_KEY_MSG)
        return {"apikey": self.api_key}

    def _get(self, url: str) -> Any:
        params = self._params()  # raises if api_key falsy -- fail clearly first
        if self._transport is None:
            raise ValueError(_NO_TRANSPORT_MSG)
        self._rate_limit_hook(url)
        return self._transport(url, params)

    def fetch_profile(self, symbol: str) -> Any:
        """Fetch the raw company profile for ``symbol`` via the injected transport."""
        return self._get(_PROFILE_URL.format(symbol=symbol))

    def fetch_income_statement(self, symbol: str) -> Any:
        """Fetch the raw income-statement series for ``symbol``."""
        return self._get(_INCOME_URL.format(symbol=symbol))

    def fetch_historical(self, symbol: str) -> Any:
        """Fetch the raw historical OHLCV series for ``symbol``."""
        return self._get(_HISTORICAL_URL.format(symbol=symbol))
