"""Optional live yfinance client -- an inert INTERFACE, not a network implementation.

009D ships the client's orchestration only: it delegates a fetch to a caller-injected
``ticker_client`` or ``transport``, calls a rate-limit hook, and fails loudly when
misconfigured. It contains NO network code, NO import of the real ``yfinance``
package, and NO environment / secret access:

* NO network import anywhere (top-level or nested / importlib), and the real
  ``yfinance`` package is NEVER imported. The data source is a dependency-injected
  ``ticker_client`` (an object exposing ``history(symbol)`` / ``quote(symbol)``) OR a
  ``transport(symbol, kind) -> Any`` callable. Wiring a real yfinance / HTTP source
  is deferred to a later live-runner milestone. Without an injected client/transport
  the client cannot reach the wire.
* NO API key, NO literal secret, NO environment-variable read, NO ``getattr(os, ...)``
  or secret lookup (yfinance needs no key). If NEITHER a ticker_client NOR a transport
  is present when a fetch is attempted, the client fails LOUDLY with ValueError --
  before any access -- rather than silently returning nothing.
* Rate-limit / backoff is a stubbed no-op hook, not a production implementation.

Parsing of whatever a client/transport returns lives in ``yfinance_adapter.py`` and
needs no network -- so the entire default test run is network-free and does not depend
on the installed ``yfinance`` package. This interface is never exercised by the
default test suite.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


_NO_SOURCE_MSG = (
    "YFinanceClient has no data source: inject ticker_client (exposing "
    "history(symbol)/quote(symbol)) or transport(symbol, kind) to enable a live "
    "fetch. 009D ships the interface only; the real yfinance package is never "
    "imported and live fetching is wired in a later step."
)


def _noop_rate_limit_hook(symbol: str) -> None:
    """Stubbed rate-limit / backoff hook. A production client would sleep / backoff
    here per Yahoo's request limits; the default is intentionally a no-op."""
    return None


class YFinanceClient:
    """Optional live-fetch INTERFACE for yfinance -- inert unless given a source.

    Supply a ``ticker_client`` (an object with ``history(symbol)`` / ``quote(symbol)``)
    or a ``transport(symbol, kind)`` callable to enable live fetches. With NEITHER
    present, the client cannot reach the network and any fetch raises ValueError.
    """

    def __init__(
        self,
        ticker_client: Optional[Any] = None,
        transport: Optional[Callable[[str, str], Any]] = None,
        rate_limit_hook: Optional[Callable[[str], None]] = None,
    ) -> None:
        # Injected local sources only -- never the real yfinance package, never a
        # network client constructed here, never a key.
        self._ticker_client = ticker_client
        self._transport = transport
        self._rate_limit_hook = rate_limit_hook or _noop_rate_limit_hook

    def _fetch(self, symbol: str, kind: str) -> Any:
        # Fail LOUDLY before ANY access when nothing is injected.
        if self._ticker_client is None and self._transport is None:
            raise ValueError(_NO_SOURCE_MSG)
        self._rate_limit_hook(symbol)
        if self._transport is not None:
            return self._transport(symbol, kind)
        if kind == "history":
            return self._ticker_client.history(symbol)
        return self._ticker_client.quote(symbol)

    def fetch_history(self, symbol: str) -> Any:
        """Fetch the raw OHLCV history for ``symbol`` via the injected source."""
        return self._fetch(symbol, "history")

    def fetch_quote(self, symbol: str) -> Any:
        """Fetch the raw quote / info dict for ``symbol`` via the injected source."""
        return self._fetch(symbol, "quote")
