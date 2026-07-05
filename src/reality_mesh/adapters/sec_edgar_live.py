"""The FIRST production LIVE source adapter -- SEC EDGAR company filings (IMPLEMENTATION-020B).

:class:`SecEdgarLiveAdapter` is the first adapter that may ingest LIVE / CURRENT external data
with full provenance, freshness, source health, rate limiting, replay compatibility and Trust /
Data-Quality visibility. It reads the public ``data.sec.gov`` submissions document per company
and normalises each recent filing's METADATA into a :class:`~reality_mesh.models.RealityEvent`
in the ``news_filings`` discipline -- per ``SOURCE_ADAPTER_PRODUCTION_CONTRACT_013``.

AUTHORITY, ASSIGNED IMMEDIATELY PER RECORD (contract §3 -- never promoted, never laundered):

* An SEC filing metadata FACT (the filing exists, on that date, of that form, at that accession)
  is ``source_authority="canonical"`` (regulatory primary source) + ``claim_status=
  "verified_fact"`` (the filing-fact). Even so, an SEC filing NEVER auto-creates an investment
  conclusion -- it is a high-authority EVENT a downstream agent MAY interpret, nothing more.
* A convenience / provider datum (FMP, etc.) can NEVER outrank an SEC filing: the authority
  ladder (``canonical`` > ``convenience``) is preserved verbatim from
  ``evidence_ingestion.source_model``.

CREDENTIALS ARE PRESENCE LABELS ONLY. SEC fair-access requires a descriptive ``User-Agent``
(a contact identity, not a secret). The descriptor names the required env var
(``SEC_USER_AGENT``); this constructor accepts a PRESENCE flag only -- a value-shaped argument
is rejected and never stored or echoed. A missing credential SKIPS the fetch with a
``credentials_missing`` health label + a visible gap NAMING the env var -- never a crash,
never a leak, never a silent fixture/demo fallback.

NO NETWORK ON IMPORT. This module imports NO network library at top level. The DEFAULT real
transport is built lazily INSIDE :meth:`SecEdgarLiveAdapter._default_transport` from
``evidence_ingestion.live_transport`` (whose ``urllib`` is itself function-local). The whole
test suite runs OFFLINE under a socket kill-switch and NEVER exercises the real network path:
tests inject a mock ``transport`` bundle. A LIVE fetch reaches the wire ONLY when an operator
runs the adapter with a wired transport + a supplied ``SEC_USER_AGENT``.

FAILURE -> VISIBLE GAP, OTHER TICKERS CONTINUE. An HTTP 429/403 (or rate-limit-shaped error)
is captured as ``rate_limited`` (``rate_limit_status="throttled"``, honoured, NEVER retried
inside a pulse); any other transport failure / timeout is ``source_unavailable``; a malformed
payload is a ``parse_error``. Each failure names its ticker in ``errors`` + ``data_gaps`` and
the remaining tickers still deliver (a ``partial`` result) -- nothing fabricated. An unknown
ticker (no CIK) is a NAMED gap, never a guessed CIK. A rate-limit-conscious spacing limiter
(SEC <= 10 req/s) paces the real transport.

Deterministic, stdlib-only, Python 3.9, OFFLINE tests. Ids and ``raw_payload_ref``s are
content-derived (sha256); ``now`` is an injected string (no wall-clock in any id path).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Tuple

# Reuse the audited 009B SEC form classifier + the conservative dilutive-offering flag --
# parsing rules live in exactly one place. NO network import here (classify_form is pure).
from evidence_ingestion.sec_edgar import classify_form, detect_offering_flags

from ..models import RealityEvent
from .base import (
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
)

__all__ = [
    "SEC_EDGAR_LIVE_ADAPTER_ID",
    "SEC_EDGAR_LIVE_DESCRIPTOR",
    "SEC_EDGAR_LIVE_DISCIPLINES",
    "SEC_EDGAR_LIVE_TRANSPORT_KEYS",
    "SEC_EDGAR_LIVE_EVENT_TYPES",
    "SEC_EDGAR_LIVE_RISK_EVENT_TYPES",
    "SEC_EDGAR_LIVE_MINIMUM_FORMS",
    "SEC_EDGAR_LIVE_FULL_BODY_FOLLOWUP_GAP",
    "SecEdgarLiveAdapter",
]

SEC_EDGAR_LIVE_ADAPTER_ID = "evidence.sec_edgar_live"

# The single discipline this adapter is the source for. A pulse takes news_filings from this
# adapter ONLY when it runs -- a failed / skipped source stays a VISIBLE gap and is never
# silently backfilled from the bundled fixtures.
SEC_EDGAR_LIVE_DISCIPLINES: Tuple[str, ...] = ("news_filings",)

# The injected transport bundle keys: a ticker->CIK map fetch and a per-CIK submissions fetch.
SEC_EDGAR_LIVE_TRANSPORT_KEYS: Tuple[str, ...] = ("company_tickers", "submissions")

# Minimum useful forms this live adapter normalises into events (metadata-first). Forms
# outside this set (13F, and other reporting boilerplate) are not news_filings catalysts and
# are not emitted -- selection per the descriptor, not a failure.
SEC_EDGAR_LIVE_MINIMUM_FORMS: Tuple[str, ...] = (
    "10-K", "10-Q", "8-K", "S-1", "S-3", "424B", "DEF 14A", "SC 13D", "SC 13G", "4")

# The honest follow-up note: 020B is METADATA-FIRST. Full filing-body parsing (exact offering
# size, going-concern language, restatement detail, risk-factor diffs) is a documented
# follow-up; where a number is not in the submissions metadata it becomes a per-event data
# gap, never a fabricated value.
SEC_EDGAR_LIVE_FULL_BODY_FOLLOWUP_GAP = (
    "metadata-first (020B): full SEC filing-body parsing (exact offering size, going-concern "
    "language, restatement / risk-factor detail) is a documented follow-up -- a figure absent "
    "from the submissions metadata is left as a gap, never fabricated")

# form-classifier token -> (event_type, observed-fact wording, half_life). Risk-sensitive
# forms carry a LABELLED event_type + a risk word in the wording (never a score/number).
_FORM_EVENT: Dict[str, Tuple[str, str, str]] = {
    "sec_10-k": ("sec_10-k_annual_report", "annual report (10-K)", "quarters"),
    "sec_10-q": ("sec_10-q_quarterly_report", "quarterly report (10-Q)", "quarters"),
    "sec_s-1": ("sec_s-1_registration",
                "S-1 registration statement -- equity issuance / dilution risk", "months"),
    "sec_s-3": ("sec_s-3_shelf_registration",
                "S-3 shelf registration -- dilution risk (shelf / ATM capacity)", "weeks"),
    "sec_424b": ("sec_424b_prospectus_offering",
                 "424B prospectus / takedown -- dilution risk (registered offering)", "weeks"),
    "sec_def_14a": ("sec_def_14a_proxy_statement", "DEF 14A proxy statement", "months"),
    "sec_13d": ("sec_13d_activist_position",
                "SC 13D activist / >5% beneficial ownership position", "months"),
    "sec_13g": ("sec_13g_passive_position",
                "SC 13G passive >5% beneficial ownership position", "months"),
    "sec_insider_form": ("sec_form_4_insider_transaction",
                         "insider Form 4 transaction -- insider sale / purchase reported",
                         "weeks"),
}

# 8-K item number -> (event_type, wording). Item 1.01 deliberately says "material definitive
# contract / agreement" so the downstream News/Filings Contract Announcement subagent
# recognises a filed material agreement.
_8K_ITEM_EVENT: Tuple[Tuple[str, str, str], ...] = (
    ("1.01", "sec_8-k_material_agreement",
     "a material definitive contract / agreement (Item 1.01)"),
    ("1.02", "sec_8-k_material_agreement",
     "termination of a material definitive agreement (Item 1.02)"),
    ("2.02", "sec_8-k_results_of_operations",
     "results of operations -- guidance change risk (Item 2.02)"),
    ("3.02", "sec_8-k_material_event",
     "unregistered sale of equity securities -- dilution risk (Item 3.02)"),
    ("4.02", "sec_8-k_restatement",
     "non-reliance on previously issued financials -- restatement risk (Item 4.02)"),
    ("5.02", "sec_8-k_management_change",
     "departure / appointment of a director or officer (Item 5.02)"),
)
_8K_DEFAULT = ("sec_8-k_material_event", "a material event")

# The full closed set of event_types this adapter may emit (declared on the descriptor).
SEC_EDGAR_LIVE_EVENT_TYPES: Tuple[str, ...] = (
    "sec_10-k_annual_report",
    "sec_10-q_quarterly_report",
    "sec_8-k_material_event",
    "sec_8-k_material_agreement",
    "sec_8-k_results_of_operations",
    "sec_8-k_restatement",
    "sec_8-k_management_change",
    "sec_s-1_registration",
    "sec_s-3_shelf_registration",
    "sec_424b_prospectus_offering",
    "sec_def_14a_proxy_statement",
    "sec_13d_activist_position",
    "sec_13g_passive_position",
    "sec_form_4_insider_transaction",
)

# The subset that carries a risk-sensitive label (VISIBLE dilution / restatement / guidance /
# insider risk derivable from metadata).
SEC_EDGAR_LIVE_RISK_EVENT_TYPES: Tuple[str, ...] = (
    "sec_s-1_registration",
    "sec_s-3_shelf_registration",
    "sec_424b_prospectus_offering",
    "sec_8-k_results_of_operations",
    "sec_8-k_restatement",
    "sec_form_4_insider_transaction",
)

# Error-text shapes recognised as a RATE LIMIT / access throttle (vs a generic failure). SEC
# returns 403 for a missing/blocked User-Agent and 429 when over the fair-access rate -- both
# are honoured as rate_limited (captured, never retried in-pulse).
_RATE_LIMIT_TOKENS = (
    "429", "403", "rate limit", "rate-limit", "ratelimit", "too many requests",
    "forbidden", "throttle",
)

# Conservative SEC fair-access ceiling: <= 10 requests/second. The limiter paces BELOW it.
_MAX_REQUESTS_PER_SECOND = 8.0


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


def _pad_cik(cik: object) -> str:
    digits = "".join(ch for ch in str(cik or "") if ch.isdigit())
    return digits.zfill(10) if digits else ""


def _classify_live_form(form: str) -> str:
    """Classify a form into an emit token, reusing 009B ``classify_form`` where it fits and
    extending it for the additional live forms (S-1 / DEF 14A / SC 13D / SC 13G)."""
    kind = classify_form(form)
    if kind in _FORM_EVENT or kind == "sec_8-k":
        return kind
    f = str(form or "").strip().upper()
    if f in ("S-1", "S-1/A"):
        return "sec_s-1"
    if f in ("DEF 14A", "DEFA14A", "DEF14A", "DEFM14A"):
        return "sec_def_14a"
    if f.startswith("SC 13D") or f == "SC 13D/A":
        return "sec_13d"
    if f.startswith("SC 13G") or f == "SC 13G/A":
        return "sec_13g"
    return ""   # not a declared output of this adapter


def _edgar_doc_url(cik: str, accession: str, primary_document: str) -> str:
    """The canonical EDGAR document URL (a label; never fetched here)."""
    if not accession:
        return ""
    acc_nodash = accession.replace("-", "")
    cik_int = str(cik or "").lstrip("0") or "0"
    base = "https://www.sec.gov/Archives/edgar/data/{0}/{1}".format(cik_int, acc_nodash)
    return "{0}/{1}".format(base, primary_document) if primary_document else base


def _days_between(filing_date: str, now: str) -> Optional[int]:
    """Whole days from ``filing_date`` (YYYY-MM-DD) to ``now`` (ISO). None if unparseable."""
    def _ordinal(text: str) -> Optional[int]:
        head = str(text or "")[:10]
        parts = head.split("-")
        if len(parts) != 3:
            return None
        try:
            y, m, d = (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
        # A pure-stdlib date ordinal (no wall-clock; deterministic from the two strings).
        import datetime
        try:
            return datetime.date(y, m, d).toordinal()
        except ValueError:
            return None

    a = _ordinal(filing_date)
    b = _ordinal(now)
    if a is None or b is None:
        return None
    return b - a


def _freshness_from_age(filing_date: str, now: str) -> str:
    """A freshness LABEL from the filing date vs the injected ``now`` (never a number)."""
    days = _days_between(filing_date, now)
    if days is None:
        return "unknown"
    if days < 0:
        return "unknown"          # a future-dated filing: honestly not classified
    if days <= 7:
        return "fresh"
    if days <= 30:
        return "recent"
    if days <= 90:
        return "aging"
    if days <= 365:
        return "stale"
    return "expired"


# --------------------------------------------------------------------------- #
# Rate-limit-conscious spacing limiter (SEC fair access <= 10 req/s).           #
# --------------------------------------------------------------------------- #
class _SpacingLimiter:
    """A minimal deterministic request-spacing limiter (paces the REAL transport).

    ``acquire`` enforces a minimum interval between successive requests. It affects TIMING
    only -- never the OUTPUT (ids / values / run_id are content-derived, ``now`` injected) --
    so it is safe under the offline test kill-switch. ``time`` is imported lazily; a test may
    swap ``_sleep`` / ``_monotonic`` to avoid any real sleep.
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
    """The ``fetch_checked`` boundary for the live adapter with the base network refusal
    disarmed.

    020B IS the production network path (the LAST onboarding stage of the contract's §4
    sequence, now implemented). No ambient import-time network is possible: the real
    transport is function-local and tests inject a mock. So this view re-runs the base
    boundary with the SAME descriptor except ``network_required=False`` (the blanket refusal
    is disarmed); every OTHER check -- RealityEvents only, authority / raw-ref / provenance
    per event, honest counts, failure -> gap -- still runs unchanged.
    """

    def __init__(self, outer: "SecEdgarLiveAdapter",
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
SEC_EDGAR_LIVE_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=SEC_EDGAR_LIVE_ADAPTER_ID,
    source_name="SEC EDGAR live company filings (data.sec.gov)",
    source_type="filing",
    source_authority="canonical",           # SEC regulatory primary source
    credential_requirements=("SEC_USER_AGENT",),   # env var NAME only, never a value
    network_required=True,                  # 020B is the FIRST production live network path
    rate_limit_policy=(
        "SEC fair-access guidance (<= 10 requests/second with a declared User-Agent) is "
        "honoured by a conservative in-adapter spacing limiter; an HTTP 429 / 403 (or "
        "rate-limit-shaped response) is surfaced as rate_limited (rate_limit_status="
        "throttled), never retried inside a pulse, never hidden"),
    outputs=SEC_EDGAR_LIVE_EVENT_TYPES,
    claim_status_rules=(
        "SEC filing metadata fact (recent filing of a given form / accession / date from the "
        "data.sec.gov submissions document) -> source_authority=canonical + claim_status="
        "verified_fact -- the filing-fact (the regulatory record exists and states the fact)",
        "an SEC filing NEVER auto-creates an investment conclusion: it is a high-authority "
        "EVENT a downstream agent MAY interpret, never a signal / thesis / trade",
        "authority is assigned immediately PER RECORD and is preserved: a convenience / "
        "provider datum (FMP etc.) can never outrank an SEC filing (canonical > convenience)",
        "risk-sensitive events are VISIBLE where derivable from METADATA (S-3 / 424B / S-1 -> "
        "dilution risk; 8-K Item 2.02 -> guidance change; 8-K Item 4.02 -> restatement; Form "
        "4 -> insider sale) -- full-body parsing is a documented follow-up, never fabricated",
    ),
    failure_modes=(
        "credentials_missing", "rate_limited", "source_unavailable", "parse_error"),
    description=(
        "SEC EDGAR live company-filings adapter -- the first production LIVE source. Reads the "
        "public data.sec.gov submissions document per ticker via an injectable transport (the "
        "default real transport is built lazily from evidence_ingestion.live_transport; no "
        "network on import), normalises each recent filing's METADATA into a canonical "
        "news_filings RealityEvent with provenance + freshness, and turns every fetch failure "
        "into a VISIBLE gap. Labels not numbers; no scheduler / broker / trading / scoring."),
)


# --------------------------------------------------------------------------- #
# SecEdgarLiveAdapter                                                          #
# --------------------------------------------------------------------------- #
class SecEdgarLiveAdapter(SourceAdapter):
    """SEC EDGAR live filings -> canonical news_filings RealityEvents. Honest gaps; no fixture
    fallback.

    ``transport`` is an INJECTABLE dict of endpoint callables: ``"company_tickers"`` ->
    ``fetch() -> ticker->CIK map`` and ``"submissions"`` -> ``fetch(cik) -> submissions doc``.
    When ``transport`` is ``None`` the DEFAULT real transport is built lazily inside
    :meth:`_default_transport` (from ``evidence_ingestion.live_transport``; import-time is
    network-free). ``sec_user_agent_present`` is a PRESENCE flag only (True / False /
    None=infer from wiring); a credential VALUE passed by mistake is rejected without being
    stored or echoed. ``cik_map`` optionally supplies configured ticker->CIK entries (a lookup
    that avoids the company_tickers fetch); an unknown ticker is a NAMED gap, never a guess.
    """

    def __init__(self, transport: Optional[Dict[str, Any]] = None, *,
                 sec_user_agent_present: Optional[bool] = None,
                 cik_map: Optional[Dict[str, Any]] = None,
                 timeout_s: float = 20.0, max_retries: int = 2) -> None:
        if transport is not None:
            if not isinstance(transport, dict):
                raise ValueError(
                    "SecEdgarLiveAdapter transport must be a dict of endpoint callables "
                    "(keys: 'company_tickers' / 'submissions')")
            for key, fetch in transport.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(
                        "SecEdgarLiveAdapter transport keys must be non-empty endpoint names "
                        "(e.g. 'submissions')")
                if not callable(fetch):
                    raise ValueError(
                        "SecEdgarLiveAdapter transport[{0!r}] must be a callable "
                        "fetch (the injected transport shape)".format(key))
        if (sec_user_agent_present is not None
                and not isinstance(sec_user_agent_present, bool)):
            # NEVER echo the offending argument: it may BE the credential value.
            raise ValueError(
                "SecEdgarLiveAdapter.sec_user_agent_present is a PRESENCE flag "
                "(True/False/None) -- never pass the credential value; the argument was "
                "rejected and has not been stored")
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise ValueError("SecEdgarLiveAdapter.timeout_s must be a number of seconds")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("SecEdgarLiveAdapter.max_retries must be a non-negative int")

        self._transport = dict(transport) if transport is not None else None
        self._sec_present = sec_user_agent_present
        self._cik_map = self._normalise_cik_map(cik_map)
        self._timeout_s = float(timeout_s)
        self._max_retries = int(max_retries)
        self._limiter = _SpacingLimiter()
        self._boundary = _TransportBoundary(
            self, replace(SEC_EDGAR_LIVE_DESCRIPTOR, network_required=False))

    @staticmethod
    def _normalise_cik_map(cik_map: Optional[Dict[str, Any]]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for ticker, cik in dict(cik_map or {}).items():
            tk = str(ticker).strip().upper()
            padded = _pad_cik(cik)
            if tk and padded:
                out[tk] = padded
        return out

    # -- identity ----------------------------------------------------------- #
    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return SEC_EDGAR_LIVE_DESCRIPTOR

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        return SEC_EDGAR_LIVE_DISCIPLINES

    def __repr__(self) -> str:  # presence labels only -- a credential value never exists here
        wired = sorted(self._transport) if self._transport is not None else "default_real"
        return ("SecEdgarLiveAdapter(transport={0}, sec_user_agent_present={1}, "
                "cik_map_tickers={2})".format(
                    wired, self._sec_present, sorted(self._cik_map)))

    # -- the transport gate over fetch_checked ------------------------------ #
    def fetch_checked(self, *, watchlist=(), themes=(),
                      now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Fetch with the 013 boundary enforced. 020B is the production network path, so the
        base blanket network refusal is disarmed; every other contract check still runs. In
        tests a mock transport is injected and the real path is never reached; in production a
        wired transport + a supplied User-Agent reach the wire lazily."""
        return self._boundary.fetch_checked(watchlist=watchlist, themes=themes, now=now)

    # -- the DEFAULT real transport, built lazily (NO network on import) ----- #
    def _default_transport(self) -> Optional[Dict[str, Any]]:
        """Build the real SEC transport lazily. Returns ``None`` when the SEC_USER_AGENT env
        var is absent (a credentials gap for the caller -- never a crash, never a leak). The
        value transits only into the transport builder and is never stored / logged / echoed.
        NEVER exercised by the offline test suite."""
        import os  # lazy; NOT a network import
        from evidence_ingestion.live_transport import sec_live_transport  # lazy boundary
        user_agent = os.environ.get("SEC_USER_AGENT", "")
        if not user_agent:
            return None
        return sec_live_transport(user_agent, timeout=self._timeout_s)

    # -- fetch --------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Pull each ticker's recent filings via the transport into canonical RealityEvents +
        an honest result. Deterministic; a mock transport keeps it OFFLINE. A missing
        credential skips with a visible gap; a raising transport is captured as rate_limited /
        source_unavailable and the OTHER tickers continue (partial); a malformed payload is a
        parse_error; an unknown ticker is a named gap. Never fabricates; never falls back to
        fixture/demo data."""
        state = {"rate_limited": False, "unavailable": False, "parse_failed": False}
        events: List[RealityEvent] = []
        refs: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        gaps: List[str] = []

        tickers = _normalise_tickers(watchlist)
        if not tickers:
            gaps.append(
                "empty watchlist: the SEC EDGAR live adapter fetches per ticker and was given "
                "none -- nothing fetched, nothing fabricated")
            return (), self._result("skipped", refs, events, warnings, errors, gaps, state, now)

        # Credentials as a PRESENCE label -- never a value. A false flag SKIPS the fetch.
        if self._sec_present is False:
            gaps.append(
                "SEC_USER_AGENT missing (presence flag false): SEC EDGAR live fetch skipped "
                "this pulse -- filings have NO coverage; visible gap (credentials_missing), "
                "nothing fabricated, no silent fixture/demo fallback")
            return (), self._result("skipped", refs, events, warnings, errors, gaps, state, now)

        transport = self._transport
        if transport is None:
            transport = self._default_transport()
            if transport is None:
                gaps.append(
                    "SEC_USER_AGENT missing (no value available to build the live transport): "
                    "SEC EDGAR live fetch skipped this pulse -- visible gap "
                    "(credentials_missing), nothing fabricated, no silent fixture/demo "
                    "fallback")
                return (), self._result(
                    "skipped", refs, events, warnings, errors, gaps, state, now)

        tickers_map: Optional[Dict[str, str]] = None    # lazily-fetched company_tickers map
        for ticker in tickers:
            cik, tickers_map = self._resolve_cik(
                ticker, transport, tickers_map, errors, gaps, state)
            if not cik:
                continue
            payload = self._call(transport, "submissions", cik, ticker, errors, gaps, state)
            if payload is None:
                continue
            events.extend(self._filing_events(
                ticker, cik, payload, refs, errors, gaps, state, now))

        problems = state["rate_limited"] or state["unavailable"] or state["parse_failed"]
        if events:
            status = "partial" if problems else "success"
        elif problems:
            status = "failed"
        else:
            status = "partial"
            gaps.append(
                "SEC EDGAR live delivered no filing events for {0} -- visible gap, nothing "
                "fabricated (unknown tickers / no catalyst forms)".format(", ".join(tickers)))

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, state, now)

    # -- CIK resolution (configured map first, then a company_tickers lookup) -- #
    def _resolve_cik(self, ticker: str, transport: Dict[str, Any],
                     tickers_map: Optional[Dict[str, str]], errors: List[str],
                     gaps: List[str],
                     state: Dict[str, bool]) -> Tuple[str, Optional[Dict[str, str]]]:
        if ticker in self._cik_map:
            return self._cik_map[ticker], tickers_map
        if tickers_map is None:
            if "company_tickers" not in transport:
                gaps.append(
                    "cannot resolve CIK for {0}: no cik_map entry and no company_tickers "
                    "transport wired -- visible gap, CIK never guessed".format(ticker))
                return "", tickers_map
            payload = self._call(
                transport, "company_tickers", None, ticker, errors, gaps, state)
            if payload is None:
                return "", tickers_map      # failure already recorded as a gap
            try:
                tickers_map = self._parse_company_tickers(payload)
            except Exception as exc:        # noqa: BLE001 -- malformed -> visible parse gap
                state["parse_failed"] = True
                errors.append("parse_error: company_tickers: {0}: {1}".format(
                    type(exc).__name__, exc))
                gaps.append(
                    "malformed SEC company_tickers payload (parse_error): CIK resolution has "
                    "NO coverage this pulse -- visible gap, nothing fabricated")
                return "", {}
        cik = tickers_map.get(ticker, "")
        if not cik:
            gaps.append(
                "unknown ticker {0}: no CIK found in the SEC company_tickers map -- visible "
                "gap, CIK never guessed, nothing fabricated".format(ticker))
        return cik, tickers_map

    @staticmethod
    def _parse_company_tickers(payload: Any) -> Dict[str, str]:
        """Zip the SEC company_tickers.json map (dict-of-rows or list-of-rows) into
        ticker->padded-CIK. Raises on a malformed payload."""
        rows: List[Any]
        if isinstance(payload, dict):
            rows = list(payload.values())
        elif isinstance(payload, list):
            rows = list(payload)
        else:
            raise ValueError("company_tickers payload must be a JSON object or list")
        out: Dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker", "") or "").strip().upper()
            cik = _pad_cik(row.get("cik_str", row.get("cik", "")))
            if ticker and cik and ticker not in out:
                out[ticker] = cik
        if not out:
            raise ValueError("company_tickers payload carried no ticker/CIK rows")
        return out

    # -- one guarded, rate-limit-conscious transport call --------------------- #
    def _call(self, transport: Dict[str, Any], key: str, arg: Optional[str],
              ticker: str, errors: List[str], gaps: List[str],
              state: Dict[str, bool]) -> Any:
        fetch = transport.get(key)
        if fetch is None:
            gaps.append(
                "transport {0} not wired: its payloads are missing this pulse -- visible gap, "
                "nothing fabricated".format(key))
            return None
        self._limiter.acquire()     # pace below SEC's fair-access ceiling (real path)
        try:
            return fetch() if arg is None else fetch(arg)
        except Exception as exc:    # noqa: BLE001 -- failure becomes a gap, never a crash
            reason = "{0}: {1}".format(type(exc).__name__, exc)
            label = ticker if arg is None else "{0} (CIK {1})".format(ticker, arg)
            if _is_rate_limit_error(exc):
                state["rate_limited"] = True
                errors.append("rate_limited: {0} {1}: {2}".format(key, ticker, reason))
                gaps.append(
                    "rate limit / access throttle (HTTP 429/403) hit on {0} for {1}: payload "
                    "missing this pulse -- limit honoured (NOT retried in-pulse); visible gap, "
                    "nothing fabricated".format(key, label))
            else:
                state["unavailable"] = True
                errors.append("source_unavailable: {0} {1}: {2}".format(key, ticker, reason))
                gaps.append(
                    "source {0} unavailable / timed out for {1}: payload missing this pulse -- "
                    "visible gap, nothing fabricated, no silent fixture/demo fallback".format(
                        key, label))
            return None

    # -- submissions -> canonical filing-fact events -------------------------- #
    def _filing_events(self, ticker: str, cik: str, payload: Any, refs: List[str],
                       errors: List[str], gaps: List[str], state: Dict[str, bool],
                       now: str) -> List[RealityEvent]:
        ref = _payload_ref("sec_submissions", ticker, payload)
        refs.append(ref)
        try:
            filings = _filings_from_submissions(payload)
        except Exception as exc:            # noqa: BLE001 -- malformed -> visible parse gap
            state["parse_failed"] = True
            errors.append("parse_error: submissions {0}: {1}: {2}".format(
                ticker, type(exc).__name__, exc))
            gaps.append(
                "malformed SEC submissions payload for {0} (parse_error): canonical filing "
                "facts have NO coverage for {0} this pulse -- visible gap, nothing "
                "fabricated".format(ticker))
            return []

        doc_cik = _pad_cik(payload.get("cik")) if isinstance(payload, dict) else ""
        effective_cik = doc_cik or cik
        out: List[RealityEvent] = []
        for filing in filings:
            kind = _classify_live_form(filing["form"])
            if kind not in _FORM_EVENT and kind != "sec_8-k":
                continue        # 13F / other: not a declared output of this adapter
            out.append(self._filing_event(
                ticker, effective_cik, filing, kind, ref, now, gaps))
        if not out:
            gaps.append(
                "SEC submissions for {0} carried no minimum-useful filings (10-K/10-Q/8-K/"
                "S-1/S-3/424B/DEF 14A/13D/13G/Form 4): no filing-fact events this pulse -- "
                "honest absence, nothing fabricated".format(ticker))
        return out

    def _filing_event(self, ticker: str, cik: str, filing: Dict[str, str], kind: str,
                      ref: str, now: str, gaps: List[str]) -> RealityEvent:
        form = filing["form"]
        accession = filing["accession"]
        items = filing["items"]
        desc = filing["primary_desc"]
        filing_date = filing["filing_date"]

        if kind == "sec_8-k":
            event_type, wording = _8K_DEFAULT
            for code, etype, ewording in _8K_ITEM_EVENT:
                if code in items:
                    event_type, wording = etype, ewording
                    break
            fact = "{0} filed an 8-K disclosing {1}".format(ticker, wording)
            half_life = "weeks"
        else:
            event_type, wording, half_life = _FORM_EVENT[kind]
            fact = "{0} filed {1}: {2}".format(ticker, form, wording)
            # A dilutive S-3 / 424B / S-1 -> conservatively confirm the dilution wording.
            if detect_offering_flags(form, desc, items) and "dilution" not in fact.lower():
                fact += " (dilutive offering risk)"

        # Metadata-first: an offering size is NOT in the submissions metadata -- a per-event
        # gap, never a fabricated number.
        event_gaps: List[str] = []
        if event_type in ("sec_s-1_registration", "sec_s-3_shelf_registration",
                          "sec_424b_prospectus_offering"):
            event_gaps.append(
                "offering size not present in SEC submissions metadata for {0} {1} -- left "
                "absent (metadata-first), never fabricated".format(ticker, form))
            event_gaps.append(SEC_EDGAR_LIVE_FULL_BODY_FOLLOWUP_GAP)

        doc_url = _edgar_doc_url(cik, accession, filing["primary_document"])
        slug = kind.replace("sec_", "").replace("-", "").replace(" ", "_") or "filing"
        text_excerpt = (doc_url,) if doc_url else ()
        # Provenance: accession + document URL + CIK all travel on the event's refs.
        source_refs = tuple(dict.fromkeys(
            r for r in (
                "sec:accession/{0}".format(accession) if accession else "",
                "sec:cik/{0}".format(cik) if cik else "",
                doc_url,
                ref,
            ) if r))
        evidence_refs = tuple(dict.fromkeys(
            r for r in (doc_url, "sec:edgar/{0}/{1}/{2}".format(ticker, form, accession)) if r))
        return RealityEvent(
            event_id="seclive.{0}.{1}.{2}".format(
                ticker.lower(), slug, _sha12(ticker, form, accession)),
            timestamp=filing_date or now,
            source_id="sec.edgar",
            source_type=kind,
            source_authority="canonical",       # SEC filing fact: assigned immediately
            claim_status="verified_fact",        # the filing exists and states the fact
            raw_payload_ref=ref,
            discipline="news_filings",
            event_type=event_type,
            affected_companies=(ticker,),
            observed_fact=fact,
            text_excerpt_refs=text_excerpt,
            evidence_refs=evidence_refs,
            source_refs=source_refs,
            confidence_label="high",
            freshness_label=_freshness_from_age(filing_date, now),
            half_life=half_life,
            data_gaps=tuple(event_gaps),
        )

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
            SEC_EDGAR_LIVE_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=SEC_EDGAR_LIVE_ADAPTER_ID,
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


# --------------------------------------------------------------------------- #
# Payload shape helper (raises on a malformed payload -> parse_error upstream)   #
# --------------------------------------------------------------------------- #
def _filings_from_submissions(payload: Any) -> List[Dict[str, str]]:
    """Zip the parallel ``filings.recent`` arrays of a data.sec.gov submissions document into
    one dict per filing. Raises ``ValueError`` on a malformed payload."""
    if not isinstance(payload, dict):
        raise ValueError("SEC submissions payload must be a JSON object")
    recent = ((payload.get("filings") or {}).get("recent")) or {}
    forms = recent.get("form")
    if not isinstance(forms, list) or not forms:
        raise ValueError("SEC submissions payload has no filings.recent.form list")

    def _at(name: str, i: int) -> str:
        arr = recent.get(name) or []
        return str(arr[i]) if isinstance(arr, list) and i < len(arr) and arr[i] else ""

    return [
        {
            "form": str(forms[i]),
            "accession": _at("accessionNumber", i),
            "filing_date": _at("filingDate", i),
            "primary_document": _at("primaryDocument", i),
            "primary_desc": _at("primaryDocDescription", i),
            "items": _at("items", i),
        }
        for i in range(len(forms))
    ]
