"""LOCAL-FILE-BACKED price-history adapter (IMPLEMENTATION-014D, Phase-014 priority #8).

:class:`LocalPriceHistoryAdapter` reads OPERATOR-SUPPLIED local JSON files named
``<TICKER>_price_history.json`` from a ``data_dir`` and emits ONE per-ticker
``price_history_reading`` :class:`~reality_mesh.models.RealityEvent` (discipline
``technical_regime``) feeding the Technical Regime sensor agent. A file carries an
``as_of`` plus EITHER precomputed indicator readings (``indicators``: close, ema8/21/50/200,
vwap, recent/avg volume, range/recent high, range_pct, pct_above_ema21) OR a list of daily
``bars`` (date/open/high/low/close/volume) from which the adapter derives the same readings
deterministically -- an underivable indicator (insufficient history) is an explicit gap,
never a fabricated value.

LOCAL FILES ONLY (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §4 stage 2): there is NO network
path, NO credential (``credentials_status="not_required"``), and NO rate limit (a
filesystem read is ``ok`` by construction). NO scheduler, NO broker, NO score.

HONEST BY CONSTRUCTION (contract §3):

* ``source_authority="convenience"`` -- operator-downloaded OHLCV/indicator data. Assigned
  immediately; a file claiming a STRONGER tier (canonical/primary) is downgraded to
  ``convenience`` with a visible warning (an operator file cannot self-certify canonical).
* readings are recorded as observed facts stamped ``claim_status="inferred"`` -- a derived
  market observation, never a ``verified_fact``.
* a MISSING file for a requested watchlist ticker -> ``partial``/``failed`` result + an
  explicit data gap NAMING the file -- never a fabricated value, never a demo fallback;
* a MALFORMED file -> ``failed`` result + a ``parse_error`` error naming the file;
* a STALE ``as_of`` (older than :data:`PRICE_HISTORY_STALE_AFTER_HOURS` versus the injected
  ``now``) -> the ticker's event is marked ``freshness_label="stale"`` (preserved, never
  dropped, never silently refreshed);
* every event carries a content-derived ``raw_payload_ref``
  (``localfile:<name>#sha256=...``) pointing at the exact bytes read.

Deterministic, stdlib-only, Python 3.9, OFFLINE. Ids are content-derived; ``now`` is an
injected string (no wall-clock anywhere).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from typing import Dict, List, Optional, Tuple

from .. import labels as _labels
from ..models import RealityEvent
from .base import (
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
)

__all__ = [
    "LOCAL_PRICE_HISTORY_ADAPTER_ID",
    "LOCAL_PRICE_HISTORY_DESCRIPTOR",
    "LOCAL_PRICE_HISTORY_DISCIPLINES",
    "PRICE_HISTORY_FILE_SUFFIX",
    "PRICE_HISTORY_INDICATOR_UNITS",
    "PRICE_HISTORY_STALE_AFTER_HOURS",
    "LocalPriceHistoryAdapter",
]

LOCAL_PRICE_HISTORY_ADAPTER_ID = "local_price_history"

# The one discipline this adapter is the source for (Phase-014 priority #8).
LOCAL_PRICE_HISTORY_DISCIPLINES: Tuple[str, ...] = ("technical_regime",)

# The operator file naming convention: one file per ticker.
PRICE_HISTORY_FILE_SUFFIX = "_price_history.json"

# A file whose ``as_of`` is older than this (versus the injected ``now``) has its event
# marked stale. 72h: tolerant of a weekend, but a week-old chart is not a current read.
PRICE_HISTORY_STALE_AFTER_HOURS = 72

# The precomputed indicator readings an operator file may carry (name -> unit). Every
# emitted numeric value carries its unit; an unknown indicator key is a visible warning.
PRICE_HISTORY_INDICATOR_UNITS: Dict[str, str] = {
    "close": "usd",
    "ema8": "usd",
    "ema21": "usd",
    "ema50": "usd",
    "ema200": "usd",
    "vwap": "usd",
    "recent_volume": "shares",
    "avg_volume": "shares",
    "range_high": "usd",
    "recent_high": "usd",
    "range_pct": "percent",
    "pct_above_ema21": "percent",
}

# Bars-derivation lookbacks (deterministic; documented, never guessed at runtime).
_EMA_PERIODS = {"ema8": 8, "ema21": 21, "ema50": 50, "ema200": 200}
_VWAP_LOOKBACK = 20        # VWAP over the last 20 bars (typical price, volume-weighted)
_AVG_VOLUME_LOOKBACK = 20  # average volume over the 20 bars BEFORE the latest bar
_RANGE_LOOKBACK = 15       # the prior base: 15 bars before the latest bar
_RECENT_HIGH_LOOKBACK = 3  # the recent push: max high of the last 3 bars

# The adapter's frozen contract declaration (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1).
LOCAL_PRICE_HISTORY_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=LOCAL_PRICE_HISTORY_ADAPTER_ID,
    source_name="Local operator price-history files",
    source_type="price_history",
    source_authority="convenience",         # operator-downloaded OHLCV/indicator data
    credential_requirements=(),             # local files: NO credential (env or otherwise)
    network_required=False,                 # LOCAL FILES ONLY -- no network path exists here
    rate_limit_policy="not_applicable: local filesystem read, no remote quota",
    outputs=("price_history_reading",),
    claim_status_rules=(
        "price-history reading -> observed fact text stamped claim_status=inferred (a "
        "derived market observation, never verified_fact)",
        "source_authority=convenience assigned immediately; a file claiming "
        "canonical/primary is downgraded to convenience with a visible warning",
    ),
    failure_modes=("source_unavailable", "parse_error"),
    description="Operator-supplied local per-ticker price-history files feeding the "
                "Technical Regime agent. Offline; no scheduler; no broker; labels not "
                "trade signals.",
)


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _parse_iso(value: str) -> Optional[_dt.datetime]:
    """Parse an ISO-8601 timestamp string (``Z`` accepted). None if unparsable. UTC-normalised."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def _is_stale(as_of: str, now: str) -> bool:
    """True iff ``as_of`` is more than the stale threshold older than the injected ``now``."""
    as_of_dt = _parse_iso(as_of)
    now_dt = _parse_iso(now)
    if as_of_dt is None or now_dt is None:
        return False
    return (now_dt - as_of_dt) > _dt.timedelta(hours=PRICE_HISTORY_STALE_AFTER_HOURS)


def _as_float(value, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{0} must be numeric, got {1!r}".format(context, value))
    return float(value)


def _ema(closes: List[float], period: int) -> float:
    """Standard EMA: seeded with the SMA of the first ``period`` closes, then recursive."""
    seed = sum(closes[:period]) / period
    k = 2.0 / (period + 1)
    value = seed
    for close in closes[period:]:
        value = close * k + value * (1 - k)
    return round(value, 4)


def _indicators_from_bars(bars: List[Dict], ticker: str,
                          gaps: List[str]) -> Dict[str, float]:
    """Derive the indicator readings from daily bars. Deterministic; underivable -> gap.

    Each bar must carry numeric ``high`` / ``low`` / ``close`` / ``volume`` (raises on a
    malformed bar -- handled by the caller as a parse error). An indicator whose lookback
    exceeds the available history is OMITTED with an explicit gap -- never fabricated.
    """
    if not bars:
        raise ValueError("bars list is empty")
    highs, lows, closes, volumes = [], [], [], []
    for index, bar in enumerate(bars):
        if not isinstance(bar, dict):
            raise ValueError("bar {0} must be a JSON object".format(index))
        highs.append(_as_float(bar.get("high"), "bar {0} high".format(index)))
        lows.append(_as_float(bar.get("low"), "bar {0} low".format(index)))
        closes.append(_as_float(bar.get("close"), "bar {0} close".format(index)))
        volumes.append(_as_float(bar.get("volume"), "bar {0} volume".format(index)))

    readings: Dict[str, float] = {
        "close": closes[-1],
        "recent_volume": volumes[-1],
        "recent_high": max(highs[-_RECENT_HIGH_LOOKBACK:]),
    }

    def _gap(key: str, need: int) -> None:
        gaps.append(
            "insufficient price history for {0} for {1} ({2} bars < {3} required): "
            "indicator omitted -- gap, never fabricated".format(
                key, ticker, len(bars), need))

    for key, period in sorted(_EMA_PERIODS.items()):
        if len(closes) >= period:
            readings[key] = _ema(closes, period)
        else:
            _gap(key, period)

    if len(volumes) >= _AVG_VOLUME_LOOKBACK + 1:
        prior = volumes[-(_AVG_VOLUME_LOOKBACK + 1):-1]
        readings["avg_volume"] = round(sum(prior) / len(prior), 2)
    else:
        _gap("avg_volume", _AVG_VOLUME_LOOKBACK + 1)

    if len(bars) >= _RANGE_LOOKBACK + 1:
        window_high = max(highs[-(_RANGE_LOOKBACK + 1):-1])
        window_low = min(lows[-(_RANGE_LOOKBACK + 1):-1])
        readings["range_high"] = window_high
        if window_low > 0:
            readings["range_pct"] = round(
                (window_high - window_low) / window_low * 100.0, 2)
        else:
            _gap("range_pct", _RANGE_LOOKBACK + 1)
    else:
        _gap("range_high", _RANGE_LOOKBACK + 1)
        _gap("range_pct", _RANGE_LOOKBACK + 1)

    if len(bars) >= _VWAP_LOOKBACK:
        weighted = 0.0
        volume_sum = 0.0
        for h, l, c, v in zip(highs[-_VWAP_LOOKBACK:], lows[-_VWAP_LOOKBACK:],
                              closes[-_VWAP_LOOKBACK:], volumes[-_VWAP_LOOKBACK:]):
            weighted += ((h + l + c) / 3.0) * v
            volume_sum += v
        if volume_sum > 0:
            readings["vwap"] = round(weighted / volume_sum, 4)
        else:
            _gap("vwap", _VWAP_LOOKBACK)
    else:
        _gap("vwap", _VWAP_LOOKBACK)

    if "ema21" in readings and readings["ema21"] > 0:
        readings["pct_above_ema21"] = round(
            (readings["close"] - readings["ema21"]) / readings["ema21"] * 100.0, 2)
    else:
        _gap("pct_above_ema21", _EMA_PERIODS["ema21"])

    return readings


# --------------------------------------------------------------------------- #
# LocalPriceHistoryAdapter                                                      #
# --------------------------------------------------------------------------- #
class LocalPriceHistoryAdapter(SourceAdapter):
    """Operator-supplied LOCAL per-ticker price-history files -> RealityEvents. Offline."""

    def __init__(self, data_dir: str) -> None:
        if not isinstance(data_dir, str) or data_dir.strip() == "":
            raise ValueError("LocalPriceHistoryAdapter requires a non-empty data_dir")
        self._data_dir = data_dir

    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return LOCAL_PRICE_HISTORY_DESCRIPTOR

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        """The one discipline this adapter sources. A consumer takes technical_regime
        events from the adapter ONLY -- a missing/failed file stays a visible gap."""
        return LOCAL_PRICE_HISTORY_DISCIPLINES

    # -- fetch ------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Read every ``<TICKER>_price_history.json`` under ``data_dir``. OFFLINE.

        A requested watchlist ticker with no file, a missing directory, or a malformed
        file becomes an explicit error/gap on the result -- never a crash, never a
        fabricated value, never demo data.
        """
        gaps: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        refs: List[str] = []
        events: List[RealityEvent] = []
        parse_failed = False

        watch = tuple(str(t).strip().upper() for t in (watchlist or ()) if str(t).strip())

        if not os.path.isdir(self._data_dir):
            errors.append(
                "source_unavailable: data_dir not found: {0}".format(self._data_dir))
            if watch:
                for ticker in watch:
                    gaps.append(self._missing_gap(ticker))
            else:
                gaps.append(
                    "no local price-history directory {0}: discipline technical_regime "
                    "has NO source coverage this run -- visible gap, never fabricated, "
                    "no silent demo fallback".format(self._data_dir))
            return (), self._result("failed", refs, events, warnings, errors, gaps, now)

        names = sorted(
            n for n in os.listdir(self._data_dir)
            if n.endswith(PRICE_HISTORY_FILE_SUFFIX))
        tickers_seen: List[str] = []

        for name in names:
            ticker = name[:-len(PRICE_HISTORY_FILE_SUFFIX)].upper()
            if watch and ticker not in watch:
                # Watchlist scope: an unrequested local file is NOT emitted -- the pulse's
                # explicit watchlist bounds what flows in (no scope leak). The file stays on
                # disk for a future run that requests its ticker.
                continue
            path = os.path.join(self._data_dir, name)
            with open(path, "rb") as fh:
                raw = fh.read()
            ref = "localfile:{0}#sha256={1}".format(
                name, hashlib.sha256(raw).hexdigest()[:16])
            refs.append(ref)

            try:
                event = self._event_from_file(
                    raw, name=name, ticker=ticker, ref=ref, now=now, warnings=warnings)
            except Exception as exc:  # malformed file -> parse_error, NEVER fabricated
                parse_failed = True
                errors.append("parse_error: {0}: {1}: {2}".format(
                    name, type(exc).__name__, exc))
                gaps.append(
                    "malformed local price-history file {0} (parse_error): ticker {1} has "
                    "NO technical_regime coverage this run -- visible gap, nothing "
                    "fabricated".format(name, ticker))
                continue

            events.append(event)
            gaps.extend(event.data_gaps)          # derivation gaps stay visible on the run
            tickers_seen.append(ticker)

        files_missing = 0
        for ticker in watch:
            if ticker not in tickers_seen:
                files_missing += 1
                gaps.append(self._missing_gap(ticker))

        if parse_failed:
            status = "failed"
        elif files_missing and events:
            status = "partial"
        elif files_missing:
            status = "failed"
        elif not events:
            status = "partial"
            gaps.append(
                "no local price-history files (*{0}) under {1} delivered any events -- "
                "visible gap, nothing fabricated".format(
                    PRICE_HISTORY_FILE_SUFFIX, self._data_dir))
        else:
            status = "success"

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, now)

    # -- builders ----------------------------------------------------------- #
    @staticmethod
    def _missing_gap(ticker: str) -> str:
        return ("missing local price-history file {0}{1}: watchlist ticker {0} has NO "
                "technical_regime coverage this run -- visible gap, never fabricated, no "
                "silent demo fallback".format(ticker, PRICE_HISTORY_FILE_SUFFIX))

    def _result(self, status, refs, events, warnings, errors, gaps,
                now: str) -> SourceAdapterResult:
        health = {"success": "healthy", "partial": "degraded", "failed": "failed"}[status]
        run_id = deterministic_adapter_run_id(
            LOCAL_PRICE_HISTORY_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=LOCAL_PRICE_HISTORY_ADAPTER_ID,
            run_id=run_id,
            status=status,
            raw_payload_refs=tuple(refs),
            events_created=len(events),
            warnings=tuple(dict.fromkeys(warnings)),
            errors=tuple(errors),
            data_gaps=tuple(dict.fromkeys(gaps)),
            credentials_status="not_required",   # local files: no credential exists to check
            rate_limit_status="ok",              # a local filesystem read cannot be throttled
            source_health=health)

    def _event_from_file(self, raw: bytes, *, name: str, ticker: str, ref: str,
                         now: str, warnings: List[str]) -> RealityEvent:
        """One provenance-stamped per-ticker price_history_reading event from one file.

        Raises for a malformed file (handled by the caller as a parse error). Never
        invents a reading: an underivable indicator is an explicit gap on the event.
        """
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("price-history file must be a JSON object")
        as_of = str(payload.get("as_of", "") or "")
        declared = str(payload.get("ticker", "") or "").strip().upper()
        if declared and declared != ticker:
            warnings.append(
                "ticker {0!r} declared inside {1} does not match the filename ticker "
                "{2!r}: the filename wins -- surfaced, not guessed".format(
                    declared, name, ticker))

        derivation_gaps: List[str] = []
        indicators = payload.get("indicators")
        bars = payload.get("bars")
        if isinstance(indicators, dict) and indicators:
            readings: Dict[str, float] = {}
            for key in sorted(indicators):
                if key not in PRICE_HISTORY_INDICATOR_UNITS:
                    warnings.append(
                        "unrecognised indicator {0!r} in {1} ignored (known: {2})".format(
                            key, name, ", ".join(sorted(PRICE_HISTORY_INDICATOR_UNITS))))
                    continue
                readings[key] = _as_float(
                    indicators[key], "indicator {0!r} in {1}".format(key, name))
        elif isinstance(bars, list) and bars:
            readings = _indicators_from_bars(bars, ticker, derivation_gaps)
        else:
            raise ValueError(
                "price-history file must carry a non-empty 'indicators' object or a "
                "non-empty 'bars' list")
        if not readings:
            raise ValueError("price-history file carries no recognised indicator reading")

        stale = _is_stale(as_of, now)
        if as_of and now and _parse_iso(as_of) is None:
            warnings.append(
                "unparsable as_of {0!r} in {1}: staleness cannot be assessed -- surfaced, "
                "not guessed".format(as_of, name))
        if stale:
            warnings.append(
                "stale as_of {0} in {1} (now {2}, threshold {3}h): its event marked stale "
                "-- preserved, never dropped, never silently refreshed".format(
                    as_of, name, now, PRICE_HISTORY_STALE_AFTER_HOURS))

        # Authority: an operator file cannot self-certify a tier stronger than convenience.
        authority = str(payload.get("source_authority", "") or "")
        if authority == "":
            authority = "convenience"
        elif (authority in _labels.SOURCE_AUTHORITIES
              and _labels.authority_rank(authority)
              > _labels.authority_rank("convenience")):
            warnings.append(
                "downgraded source_authority {0!r} -> 'convenience' for {1}: an "
                "operator-downloaded local price-history file cannot self-certify "
                "{0!r}".format(authority, name))
            authority = "convenience"
        elif authority not in _labels.SOURCE_AUTHORITIES:
            raise ValueError(
                "unknown source_authority {0!r} in {1}".format(authority, name))

        numeric_values = tuple(
            (key, readings[key], PRICE_HISTORY_INDICATOR_UNITS[key])
            for key in sorted(readings))
        digest = hashlib.sha256(
            json.dumps({"ticker": ticker, "as_of": as_of, "readings": readings},
                       sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]

        if stale:
            freshness = "stale"
        elif _parse_iso(as_of) is not None:
            freshness = "recent"
        else:
            freshness = ""                        # unknown as_of -> explicit gap sentinel

        return RealityEvent(
            event_id="local.technical_regime.{0}.{1}".format(ticker.lower(), digest),
            timestamp=as_of or now,
            source_id="local_file.price_history.{0}".format(ticker.lower()),
            source_type="local_price_history_file",
            source_authority=authority,
            claim_status="inferred",              # derived market observation, never verified
            raw_payload_ref=ref,
            discipline="technical_regime",
            event_type="price_history_reading",
            affected_companies=(ticker,),
            observed_fact="per-ticker price-history indicator readings for {0} (operator "
                          "download; precomputed or bar-derived)".format(ticker),
            numeric_values=numeric_values,
            source_refs=(ref,),
            confidence_label="moderate",
            freshness_label=freshness,
            half_life="days",
            data_gaps=tuple(derivation_gaps),
        )
