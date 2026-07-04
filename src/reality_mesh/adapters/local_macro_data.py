"""The LOCAL-FILE-BACKED macro-readings adapter (IMPLEMENTATION-014F).

:class:`LocalMacroDataAdapter` reads ONE operator-supplied local JSON file,
``data_dir/macro_readings.json`` (an ``as_of`` timestamp plus a list of NAMED readings, each
carrying an explicit unit), and emits :class:`~reality_mesh.models.RealityEvent`s for the
``macro_regime`` discipline -- the events the Macro Regime sensor (Phase-014 priority #11)
consumes. Onboarding stage 2 of SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §4: LOCAL FILES ONLY.
There is NO network path, NO credential (``credentials_status="not_required"``), and NO rate
limit (a filesystem read is ``ok`` by construction).

HONEST BY CONSTRUCTION (contract §3):

* ``source_authority="convenience"`` on every record -- operator-downloaded macro data can
  never self-certify a stronger tier (there is no authority field in the file to launder).
* every reading is an observed macro datum stamped ``claim_status="inferred"`` -- a derived
  market-wide observation, never a ``verified_fact``.
* **watchlist scoping is NOT APPLICABLE**: macro readings are MARKET-WIDE, so the adapter
  never filters (or fabricates) per-ticker macro data -- a non-empty watchlist yields a
  visible warning stating exactly that. A reading MAY carry an optional ``themes`` list;
  where present it is honoured onto the event's ``affected_themes`` (theme scoping honoured
  where present, never invented).
* a reading WITHOUT a unit is NOT emitted as a number (a bare number is not a reading): the
  entry is rejected as a visible ``parse_error`` -- never a fabricated unit;
* a MISSING file -> ``failed`` result + an explicit data gap NAMING the file; a MALFORMED
  file -> ``failed`` + a ``parse_error`` naming it -- never a crash, never a fabricated
  value, never a silent fall-back to demo fixtures;
* a STALE ``as_of`` (older than :data:`MACRO_STALE_AFTER_HOURS` versus the injected ``now``)
  marks every event stale (preserved, never dropped, never silently refreshed);
* every event carries a content-derived ``raw_payload_ref`` (``localfile:<name>#sha256=...``).

Deterministic, stdlib-only, Python 3.9, OFFLINE. Ids are content-derived; ``now`` is an
injected string (no wall-clock anywhere). No scheduler / broker / trading / scoring.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from typing import Any, Dict, List, Tuple

from ..models import RealityEvent
from .base import (
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
)
# Reuse the audited 014A ISO parser -- timestamp parsing rules live in exactly one place.
from .local_market_data import _parse_iso

__all__ = [
    "LOCAL_MACRO_DATA_ADAPTER_ID",
    "LOCAL_MACRO_DATA_DESCRIPTOR",
    "LOCAL_MACRO_DATA_DISCIPLINES",
    "MACRO_READINGS_FILENAME",
    "MACRO_STALE_AFTER_HOURS",
    "LocalMacroDataAdapter",
]

LOCAL_MACRO_DATA_ADAPTER_ID = "local_macro_data"

# The single discipline this adapter is the source for (Phase-014 priority #11).
LOCAL_MACRO_DATA_DISCIPLINES: Tuple[str, ...] = ("macro_regime",)

# The one operator-supplied file read from ``data_dir``.
MACRO_READINGS_FILENAME = "macro_readings.json"

# A file whose ``as_of`` is older than this (versus the injected ``now``) has ALL its events
# marked stale. 48h: macro readings older than two days are not a current regime read.
MACRO_STALE_AFTER_HOURS = 48

# The adapter's frozen contract declaration (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1).
LOCAL_MACRO_DATA_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=LOCAL_MACRO_DATA_ADAPTER_ID,
    source_name="Local operator macro-readings file",
    source_type="macro_data",
    source_authority="convenience",         # operator-downloaded macro data
    credential_requirements=(),             # local files: NO credential (env or otherwise)
    network_required=False,                 # LOCAL FILES ONLY -- no network path exists here
    rate_limit_policy="not_applicable: local filesystem read, no remote quota",
    outputs=("macro_reading",),
    claim_status_rules=(
        "macro reading -> observed fact text stamped claim_status=inferred (a derived "
        "market-wide observation, never verified_fact)",
        "source_authority=convenience assigned immediately on every record: an "
        "operator-downloaded local file cannot self-certify a stronger tier",
        "a reading without a unit is not emitted as a number (a bare number is not a "
        "reading) -- visible parse_error, never a fabricated unit",
        "watchlist scoping not applicable: macro readings are market-wide and are never "
        "filtered or fabricated per ticker; a reading's optional themes list is honoured "
        "onto affected_themes where present",
    ),
    failure_modes=("source_unavailable", "parse_error"),
    description="Operator-supplied local macro_readings.json (rates, yield curve, dollar, "
                "credit spreads, inflation/jobs surprises, liquidity proxy, VIX) feeding "
                "the Macro Regime agent. Offline; no scheduler; no broker; labels not "
                "scores.",
)


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _sha12(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


def _is_stale(as_of: str, now: str) -> bool:
    """True iff ``as_of`` is more than MACRO_STALE_AFTER_HOURS older than ``now``.

    Deterministic: purely a comparison of the two injected strings -- no wall-clock. An
    absent / unparsable timestamp on either side reads False (the caller surfaces a warning
    for an unparsable ``as_of`` -- staleness is never guessed).
    """
    as_of_dt = _parse_iso(as_of)
    now_dt = _parse_iso(now)
    if as_of_dt is None or now_dt is None:
        return False
    return (now_dt - as_of_dt) > _dt.timedelta(hours=MACRO_STALE_AFTER_HOURS)


# --------------------------------------------------------------------------- #
# LocalMacroDataAdapter                                                         #
# --------------------------------------------------------------------------- #
class LocalMacroDataAdapter(SourceAdapter):
    """Operator-supplied LOCAL macro-readings file -> RealityEvents. Offline; honest gaps.

    ``data_dir/macro_readings.json`` holds ``{"as_of": "...", "readings": [{"name": ...,
    "value": ..., "unit": ..., "observed": optional text, "themes": optional list}, ...]}``.
    Every reading is a market-wide ``inferred`` observation at ``convenience`` authority.
    """

    def __init__(self, data_dir: str) -> None:
        if not isinstance(data_dir, str) or data_dir.strip() == "":
            raise ValueError("LocalMacroDataAdapter requires a non-empty data_dir")
        self._data_dir = data_dir

    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return LOCAL_MACRO_DATA_DESCRIPTOR

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        """The discipline this adapter sources. A consumer takes it from the adapter ONLY --
        a missing/failed file stays a visible gap, never a fixture fallback."""
        return LOCAL_MACRO_DATA_DISCIPLINES

    # -- fetch ---------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Read ``data_dir/macro_readings.json`` into RealityEvents plus an honest result.

        Deterministic + offline: reads the local filesystem only. A missing / malformed file
        becomes an explicit error/gap NAMING it -- never a crash, never a fabricated value,
        never a silent demo fallback. Watchlist scoping is not applicable (market-wide).
        """
        events: List[RealityEvent] = []
        refs: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        gaps: List[str] = []
        parse_failed = False

        if watchlist:
            warnings.append(
                "watchlist scoping not applicable: macro readings are market-wide (they "
                "apply to every ticker) -- nothing filtered, nothing fabricated per ticker")

        path = os.path.join(self._data_dir, MACRO_READINGS_FILENAME)
        if not os.path.isfile(path):
            errors.append("source_unavailable: macro-readings file not found: {0}".format(path))
            gaps.append(
                "missing local macro-readings file {0}: discipline macro_regime has NO "
                "source coverage this run -- visible gap, never fabricated, no silent demo "
                "fallback".format(MACRO_READINGS_FILENAME))
            return (), self._result("failed", refs, events, warnings, errors, gaps, now)

        with open(path, "rb") as fh:
            raw = fh.read()
        ref = "localfile:{0}#sha256={1}".format(
            MACRO_READINGS_FILENAME, hashlib.sha256(raw).hexdigest()[:16])
        refs.append(ref)

        try:
            doc = json.loads(raw.decode("utf-8"))
            if not isinstance(doc, dict):
                raise ValueError("macro_readings.json must be a JSON object")
            readings = doc.get("readings")
            if not isinstance(readings, list):
                raise ValueError("macro_readings.json must carry a 'readings' list")
        except Exception as exc:  # malformed file -> parse_error, NEVER fabricated events
            errors.append("parse_error: {0}: {1}: {2}".format(
                MACRO_READINGS_FILENAME, type(exc).__name__, exc))
            gaps.append(
                "malformed local macro-readings file {0} (parse_error): discipline "
                "macro_regime has NO source coverage this run -- visible gap, nothing "
                "fabricated".format(MACRO_READINGS_FILENAME))
            return (), self._result("failed", refs, events, warnings, errors, gaps, now)

        as_of = str(doc.get("as_of", "") or "")
        if as_of and now and _parse_iso(as_of) is None:
            warnings.append(
                "unparsable as_of {0!r} in {1}: staleness cannot be assessed -- surfaced, "
                "not guessed".format(as_of, MACRO_READINGS_FILENAME))
        stale = _is_stale(as_of, now)
        if stale:
            warnings.append(
                "stale as_of {0} in {1} (now {2}, threshold {3}h): all its events marked "
                "stale -- preserved, never dropped, never silently refreshed".format(
                    as_of, MACRO_READINGS_FILENAME, now, MACRO_STALE_AFTER_HOURS))

        for index, entry in enumerate(readings):
            event, reason = self._reading_event(entry, index, ref, as_of, now, stale)
            if event is not None:
                events.append(event)
            else:
                parse_failed = True
                errors.append("parse_error: {0} readings[{1}]: {2}".format(
                    MACRO_READINGS_FILENAME, index, reason))
                gaps.append(
                    "invalid macro reading readings[{0}] in {1} rejected (parse_error: {2}) "
                    "-- surfaced, never silently repaired, never a fabricated value".format(
                        index, MACRO_READINGS_FILENAME, reason))

        if parse_failed:
            status = "failed" if not events else "partial"
        elif not events:
            status = "partial"
            gaps.append(
                "local macro-readings file {0} delivered no events -- visible gap, nothing "
                "fabricated".format(MACRO_READINGS_FILENAME))
        else:
            status = "success"

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, now)

    # -- builders ----------------------------------------------------------- #
    def _reading_event(self, entry: Any, index: int, ref: str, as_of: str, now: str,
                       stale: bool):
        """One named-reading entry -> ``(RealityEvent, "")`` or ``(None, reason)``."""
        if not isinstance(entry, dict):
            return None, "entry must be a JSON object"
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            return None, "missing reading name"
        name = name.strip()
        value = entry.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, "reading {0!r} has non-numeric value {1!r}".format(name, value)
        unit = entry.get("unit")
        if not isinstance(unit, str) or not unit.strip():
            # A bare number is not a reading: no unit is ever invented.
            return None, ("reading {0!r} has no unit: the number is not emitted as a "
                          "reading -- nothing fabricated".format(name))
        unit = unit.strip()

        observed = entry.get("observed")
        if not isinstance(observed, str) or not observed.strip():
            observed = "macro reading {0}: {1} {2} (market-wide)".format(name, value, unit)
        themes = entry.get("themes")
        theme_tuple: Tuple[str, ...] = ()
        if isinstance(themes, list):
            theme_tuple = tuple(
                str(t).strip() for t in themes if isinstance(t, str) and str(t).strip())

        return RealityEvent(
            event_id="local.macro_regime.{0}.{1}".format(
                _slug(name), _sha12(name, value, unit, as_of)),
            timestamp=as_of or now,
            source_id="local_file.macro_regime",
            source_type="local_macro_data_file",
            source_authority="convenience",     # operator file: never self-certified higher
            claim_status="inferred",            # derived observation, never verified_fact
            raw_payload_ref=ref,
            discipline="macro_regime",
            event_type="macro_reading",
            affected_themes=theme_tuple,        # theme scoping honoured where present
            observed_fact=observed.strip(),
            numeric_values=((name, float(value), unit),),
            source_refs=(ref,),
            confidence_label="moderate",
            freshness_label="stale" if stale else "recent",
            half_life="days",
        ), ""

    def _result(self, status: str, refs: List[str], events: List[RealityEvent],
                warnings: List[str], errors: List[str], gaps: List[str],
                now: str) -> SourceAdapterResult:
        health = {"success": "healthy", "partial": "degraded", "failed": "failed"}[status]
        run_id = deterministic_adapter_run_id(
            LOCAL_MACRO_DATA_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=LOCAL_MACRO_DATA_ADAPTER_ID,
            run_id=run_id,
            status=status,
            raw_payload_refs=tuple(dict.fromkeys(refs)),
            events_created=len(events),
            warnings=tuple(dict.fromkeys(warnings)),
            errors=tuple(dict.fromkeys(errors)),
            data_gaps=tuple(dict.fromkeys(gaps)),
            credentials_status="not_required",   # local files: no credential exists to check
            rate_limit_status="ok",              # a local filesystem read cannot be throttled
            source_health=health)
