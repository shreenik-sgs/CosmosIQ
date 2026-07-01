"""Optional live SEC EDGAR client -- an inert INTERFACE, not a network implementation.

009B ships the client's orchestration only: it builds the data.sec.gov URLs, sets
the SEC-required User-Agent header, calls a rate-limit hook, and fails loudly when
misconfigured. It contains NO network code and NO environment/secret access:

* No network import anywhere (top-level or nested). The HTTP transport is a
  dependency-injected callable ``transport(url, headers) -> bytes/str``; wiring a
  real urllib/requests transport is deferred to a later live-runner milestone.
  Without an injected transport the client cannot reach the wire.
* SEC's fair-access policy requires a descriptive User-Agent (a contact identity,
  NOT a credential). It is supplied via the constructor argument; the client holds
  no key/token/secret and reads no environment variable or hardcoded email. If it
  is falsy when a live fetch is attempted the client fails LOUDLY with ValueError
  rather than issuing an unidentified request.
* Rate-limit/backoff is a stubbed no-op hook, not a production implementation.

Parsing of whatever a transport returns lives in ``sec_edgar.py`` and needs no
network -- so the entire default test run is network-free by construction.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"

_MISSING_UA_MSG = (
    "SEC requires a configurable User-Agent (pass user_agent= to SecEdgarClient)"
)
_NO_TRANSPORT_MSG = (
    "SecEdgarClient has no transport: inject transport(url, headers) to enable a "
    "live fetch (009B ships the interface only; live HTTP is wired in a later step)"
)


def _pad_cik(cik: Any) -> str:
    """Normalise a CIK to the zero-padded 10-digit form data.sec.gov expects."""
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    return digits.zfill(10)


def _noop_rate_limit_hook(url: str) -> None:
    """Stubbed rate-limit/backoff hook. A production client would sleep/backoff here
    per SEC's fair-access policy; the default is intentionally a no-op."""
    return None


class SecEdgarClient:
    """Optional live-fetch INTERFACE for data.sec.gov -- inert unless given a transport.

    Supply ``user_agent`` (SEC fair-access requires a descriptive contact string) and
    a ``transport`` callable to enable live fetches. With neither, the client cannot
    reach the network and any fetch raises ValueError.
    """

    def __init__(
        self,
        user_agent: Optional[str] = None,
        transport: Optional[Callable[[str, dict], Any]] = None,
        rate_limit_hook: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.user_agent = user_agent
        self._transport = transport
        self._rate_limit_hook = rate_limit_hook or _noop_rate_limit_hook

    def _headers(self) -> dict:
        if not self.user_agent:
            raise ValueError(_MISSING_UA_MSG)
        return {"User-Agent": self.user_agent, "Accept-Encoding": "identity"}

    def _get(self, url: str) -> Any:
        headers = self._headers()  # raises if user_agent falsy -- fail clearly first
        if self._transport is None:
            raise ValueError(_NO_TRANSPORT_MSG)
        self._rate_limit_hook(url)
        return self._transport(url, headers)

    def fetch_submissions(self, cik: Any) -> Any:
        """Fetch the raw submissions document for ``cik`` via the injected transport."""
        return self._get(_SUBMISSIONS_URL.format(cik10=_pad_cik(cik)))

    def fetch_companyfacts(self, cik: Any) -> Any:
        """Fetch the raw companyfacts (XBRL) document for ``cik``."""
        return self._get(_COMPANYFACTS_URL.format(cik10=_pad_cik(cik)))
