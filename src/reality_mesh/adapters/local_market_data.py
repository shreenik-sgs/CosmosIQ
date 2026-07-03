"""The FIRST production source adapter: LOCAL-FILE-BACKED market data (IMPLEMENTATION-014A).

:class:`LocalMarketDataAdapter` reads OPERATOR-SUPPLIED local JSON/CSV files from a
``data_dir`` and emits :class:`~reality_mesh.models.RealityEvent`s for the three market-data
disciplines the Phase-014 priority agents consume: ``market_regime.json``,
``sector_rotation.json``, ``theme_rotation.json`` (a ``.csv`` sibling of each is accepted).
The JSON files use the SAME event shape as the bundled pulse fixtures, so the Market Regime /
Sector Rotation / Theme Rotation agents consume the events unchanged.

This is onboarding stage 2 of SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §4 (a manual/on-demand
adapter behind an explicit pulse; no scheduler): LOCAL FILES ONLY. There is NO network path,
NO credential (``credentials_status="not_required"``), and NO rate limit (a filesystem read is
``ok`` by construction).

HONEST BY CONSTRUCTION (contract §3):

* ``source_authority="convenience"`` -- operator-downloaded market data. Assigned immediately
  when a record omits it; a record claiming a STRONGER tier (canonical/primary) is downgraded
  to ``convenience`` with a visible warning (an operator file cannot self-certify canonical).
* market readings are recorded as observed facts (``observed_fact`` text) stamped
  ``claim_status="inferred"`` -- a derived market observation, never a ``verified_fact``.
* a MISSING file -> ``partial``/``failed`` result + an explicit data gap NAMING the file --
  never a fabricated value, never a silent fall-back to demo fixtures;
* a MALFORMED file -> ``failed`` result + a ``parse_error`` error naming the file;
* a STALE ``as_of`` in a file (older than :data:`STALE_AFTER_HOURS` versus the injected
  ``now``) -> every event from that file is marked ``freshness_label="stale"`` (preserved,
  never dropped, never silently refreshed);
* every event carries a content-derived ``raw_payload_ref`` (``localfile:<name>#sha256=...``)
  pointing at the exact bytes read -- raw payloads are referenced before interpretation.

Deterministic, stdlib-only, Python 3.9, OFFLINE. Ids are content-derived; ``now`` is an
injected string (no wall-clock anywhere).
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
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
    "LOCAL_MARKET_DATA_ADAPTER_ID",
    "LOCAL_MARKET_DATA_DESCRIPTOR",
    "LOCAL_MARKET_DATA_DISCIPLINES",
    "LOCAL_MARKET_DATA_FILES",
    "STALE_AFTER_HOURS",
    "LocalMarketDataAdapter",
]

LOCAL_MARKET_DATA_ADAPTER_ID = "local_market_data"

# The three disciplines this adapter is the source for (Phase-014 priorities #1-#3). The file
# stem IS the discipline: one operator file per discipline.
LOCAL_MARKET_DATA_DISCIPLINES: Tuple[str, ...] = (
    "market_regime",
    "sector_rotation",
    "theme_rotation",
)

# The operator-supplied files read from ``data_dir`` (canonical JSON names; a ``.csv`` sibling
# of the same stem is accepted where a JSON file is absent).
LOCAL_MARKET_DATA_FILES: Tuple[str, ...] = tuple(
    "{0}.json".format(d) for d in LOCAL_MARKET_DATA_DISCIPLINES)

# A file whose ``as_of`` is older than this (versus the injected ``now``) has ALL its events
# marked stale. 48h: market readings older than two days are not a current regime read.
STALE_AFTER_HOURS = 48

# The adapter's frozen contract declaration (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1).
LOCAL_MARKET_DATA_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=LOCAL_MARKET_DATA_ADAPTER_ID,
    source_name="Local operator market-data files",
    source_type="market_data",
    source_authority="convenience",         # operator-downloaded market data
    credential_requirements=(),             # local files: NO credential (env or otherwise)
    network_required=False,                 # LOCAL FILES ONLY -- no network path exists here
    rate_limit_policy="not_applicable: local filesystem read, no remote quota",
    outputs=(
        "index_breadth_reading",
        "advance_decline_reading",
        "distribution_day_reading",
        "volatility_regime_reading",
        "small_cap_risk_appetite_reading",
        "sector_relative_strength_reading",
        "industry_group_breadth_reading",
        "volume_expansion_reading",
        "sector_flow_proxy_reading",
        "theme_basket_builder",
        "theme_relative_strength_reading",
        "theme_member_reading",
    ),
    claim_status_rules=(
        "market reading -> observed fact text stamped claim_status=inferred (a derived "
        "market observation, never verified_fact)",
        "source_authority=convenience assigned immediately when a record omits it; a record "
        "claiming canonical/primary is downgraded to convenience with a visible warning",
    ),
    failure_modes=("source_unavailable", "parse_error"),
    description="Operator-supplied local JSON/CSV market-data files feeding the Market "
                "Regime / Sector Rotation / Theme Rotation agents. Offline; no scheduler; "
                "no broker; labels not scores.",
)

# Tuple-typed RealityEvent fields a JSON record may carry as lists (fixture shape).
_TUPLE_FIELDS = (
    "affected_companies", "affected_themes", "affected_sectors", "affected_value_chains",
    "text_excerpt_refs", "evidence_refs", "source_refs", "conflicts", "data_gaps",
)

# CSV columns that hold pipe-separated lists.
_CSV_LIST_COLUMNS = ("affected_companies", "affected_sectors", "affected_themes",
                     "evidence_refs", "source_refs")


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
    """True iff ``as_of`` is more than STALE_AFTER_HOURS older than the injected ``now``.

    Deterministic: purely a comparison of the two injected strings -- no wall-clock. An
    absent / unparsable timestamp on either side reads False (the caller surfaces a warning
    for an unparsable ``as_of`` -- staleness is never guessed).
    """
    as_of_dt = _parse_iso(as_of)
    now_dt = _parse_iso(now)
    if as_of_dt is None or now_dt is None:
        return False
    return (now_dt - as_of_dt) > _dt.timedelta(hours=STALE_AFTER_HOURS)


def _records_from_json(text: str) -> Tuple[List[Dict], str]:
    """Parse a JSON market-data file into ``(records, as_of)``. Raises on a malformed file."""
    payload = json.loads(text)
    if isinstance(payload, dict):
        records = payload.get("events")
        if not isinstance(records, list):
            raise ValueError("JSON market-data file must carry an 'events' list")
        as_of = str(payload.get("as_of", "") or "")
    elif isinstance(payload, list):
        records, as_of = payload, ""
    else:
        raise ValueError("JSON market-data file must be an object or a list of events")
    for rec in records:
        if not isinstance(rec, dict):
            raise ValueError("every event record must be a JSON object")
    return list(records), as_of


def _records_from_csv(text: str) -> Tuple[List[Dict], str]:
    """Parse a CSV market-data file into ``(records, as_of)``. Raises on a malformed file.

    One row = one reading. Recognised columns: ``event_id`` / ``timestamp`` / ``event_type``
    / ``observed_fact`` / ``metric`` / ``value`` / ``unit`` / ``freshness_label`` /
    ``confidence_label`` / ``half_life`` / ``as_of`` plus the pipe-separated list columns
    (``affected_companies`` / ``affected_sectors`` / ``affected_themes`` / ``evidence_refs``
    / ``source_refs``). ``metric``/``value``/``unit`` become one ``numeric_values`` entry.
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV market-data file has no header row")
    records: List[Dict] = []
    as_of = ""
    for row in reader:
        rec = {k: (v or "").strip() for k, v in row.items() if k}
        as_of = rec.pop("as_of", "") or as_of
        metric = rec.pop("metric", "")
        value = rec.pop("value", "")
        unit = rec.pop("unit", "")
        if metric:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                raise ValueError(
                    "CSV row metric {0!r} has non-numeric value {1!r}".format(metric, value))
            rec["numeric_values"] = [[metric, numeric, unit]]
        for name in _CSV_LIST_COLUMNS:
            raw = rec.get(name, "")
            if raw:
                rec[name] = [tk.strip() for tk in raw.split("|") if tk.strip()]
            elif name in rec:
                del rec[name]
        rec = {k: v for k, v in rec.items() if v != ""}
        records.append(rec)
    return records, as_of


# --------------------------------------------------------------------------- #
# LocalMarketDataAdapter                                                       #
# --------------------------------------------------------------------------- #
class LocalMarketDataAdapter(SourceAdapter):
    """Operator-supplied LOCAL market-data files -> RealityEvents. Offline; honest gaps."""

    def __init__(self, data_dir: str) -> None:
        if not isinstance(data_dir, str) or data_dir.strip() == "":
            raise ValueError("LocalMarketDataAdapter requires a non-empty data_dir")
        self._data_dir = data_dir

    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return LOCAL_MARKET_DATA_DESCRIPTOR

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        """The three disciplines this adapter sources. A consumer takes these from the adapter
        ONLY -- a missing/failed file stays a visible gap, never a fixture fallback."""
        return LOCAL_MARKET_DATA_DISCIPLINES

    # -- fetch ------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Read the operator files under ``data_dir`` into RealityEvents + an honest result.

        Deterministic + offline: reads the local filesystem only. A missing file / directory
        or a malformed file becomes an explicit error/gap on the result -- never a crash,
        never a fabricated value, never demo data.
        """
        gaps: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        refs: List[str] = []
        events: List[RealityEvent] = []
        parse_failed = False
        files_missing = 0

        if not os.path.isdir(self._data_dir):
            errors.append(
                "source_unavailable: data_dir not found: {0}".format(self._data_dir))
            for name in LOCAL_MARKET_DATA_FILES:
                gaps.append(self._missing_gap(name))
            return (), self._result("failed", refs, events, warnings, errors, gaps, now)

        for discipline in LOCAL_MARKET_DATA_DISCIPLINES:
            json_name = "{0}.json".format(discipline)
            csv_name = "{0}.csv".format(discipline)
            json_path = os.path.join(self._data_dir, json_name)
            csv_path = os.path.join(self._data_dir, csv_name)
            if os.path.isfile(json_path):
                path, parser = json_path, _records_from_json
            elif os.path.isfile(csv_path):
                path, parser = csv_path, _records_from_csv
            else:
                files_missing += 1
                gaps.append(self._missing_gap(json_name))
                continue

            name = os.path.basename(path)
            with open(path, "rb") as fh:
                raw = fh.read()
            ref = "localfile:{0}#sha256={1}".format(
                name, hashlib.sha256(raw).hexdigest()[:16])
            refs.append(ref)

            try:
                records, as_of = parser(raw.decode("utf-8"))
            except Exception as exc:  # malformed file -> parse_error, NEVER fabricated events
                parse_failed = True
                errors.append("parse_error: {0}: {1}: {2}".format(
                    name, type(exc).__name__, exc))
                gaps.append(
                    "malformed local market-data file {0} (parse_error): discipline {1} has "
                    "NO source coverage this run -- visible gap, nothing fabricated".format(
                        name, discipline))
                continue

            stale = _is_stale(as_of, now)
            if as_of and now and _parse_iso(as_of) is None:
                warnings.append(
                    "unparsable as_of {0!r} in {1}: staleness cannot be assessed -- surfaced, "
                    "not guessed".format(as_of, name))
            if stale:
                warnings.append(
                    "stale as_of {0} in {1} (now {2}, threshold {3}h): all its events marked "
                    "stale -- preserved, never dropped, never silently refreshed".format(
                        as_of, name, now, STALE_AFTER_HOURS))

            for index, record in enumerate(records):
                try:
                    events.append(self._event_from_record(
                        record, discipline=discipline, ref=ref, as_of=as_of, now=now,
                        stale=stale, warnings=warnings))
                except Exception as exc:  # an invalid record is a parse error, not a crash
                    parse_failed = True
                    errors.append("parse_error: {0} record {1}: {2}: {3}".format(
                        name, index, type(exc).__name__, exc))
                    gaps.append(
                        "invalid record {0} in {1} rejected (parse_error) -- surfaced, never "
                        "silently repaired".format(index, name))

        if parse_failed:
            status = "failed"
        elif files_missing and events:
            status = "partial"
        elif files_missing:
            status = "failed"
        elif not events:
            status = "partial"
            gaps.append(
                "local market-data files under {0} delivered no events -- visible gap, "
                "nothing fabricated".format(self._data_dir))
        else:
            status = "success"

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, now)

    # -- builders ----------------------------------------------------------- #
    @staticmethod
    def _missing_gap(name: str) -> str:
        discipline = os.path.splitext(name)[0]
        return ("missing local market-data file {0} (no .json/.csv): discipline {1} has NO "
                "source coverage this run -- visible gap, never fabricated, no silent demo "
                "fallback".format(name, discipline))

    def _result(self, status, refs, events, warnings, errors, gaps,
                now: str) -> SourceAdapterResult:
        health = {"success": "healthy", "partial": "degraded", "failed": "failed"}[status]
        run_id = deterministic_adapter_run_id(
            LOCAL_MARKET_DATA_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=LOCAL_MARKET_DATA_ADAPTER_ID,
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

    def _event_from_record(self, record: Dict, *, discipline: str, ref: str, as_of: str,
                           now: str, stale: bool, warnings: List[str]) -> RealityEvent:
        """One defaulted, provenance-stamped RealityEvent from one operator record.

        Fills the contract-mandated fields the operator file may omit (authority, claim
        status, raw payload ref, source refs, ids) -- deterministically, never inventing a
        reading. Raises for an invalid record (handled by the caller as a parse error).
        """
        kw = {k: v for k, v in record.items() if not str(k).startswith("_")}
        for name in _TUPLE_FIELDS:
            if name in kw and kw[name] is not None:
                kw[name] = tuple(kw[name])
        if kw.get("numeric_values") is not None:
            kw["numeric_values"] = tuple(tuple(nv) for nv in kw.get("numeric_values", ()))

        kw.setdefault("discipline", discipline)
        if not kw["discipline"]:
            kw["discipline"] = discipline
        if not kw.get("source_id"):
            kw["source_id"] = "local_file.{0}".format(discipline)
        if not kw.get("source_type"):
            kw["source_type"] = "local_market_data_file"

        # Authority: explicit + assigned immediately; an operator file cannot self-certify a
        # tier stronger than convenience.
        authority = kw.get("source_authority", "") or ""
        if authority == "":
            authority = "convenience"
        elif (authority in _labels.SOURCE_AUTHORITIES
              and _labels.authority_rank(authority)
              > _labels.authority_rank("convenience")):
            warnings.append(
                "downgraded source_authority {0!r} -> 'convenience' for record {1!r}: an "
                "operator-downloaded local file cannot self-certify {0!r}".format(
                    authority, kw.get("event_id", "")))
            authority = "convenience"
        kw["source_authority"] = authority

        # Market readings are observed facts stamped as derived observations, never verified.
        if not kw.get("claim_status"):
            kw["claim_status"] = "inferred"

        # Raw payload ref: the exact bytes read (a pointer, never inlined).
        if not kw.get("raw_payload_ref"):
            kw["raw_payload_ref"] = ref
        # Provenance refs: at least the file ref itself.
        if not kw.get("evidence_refs") and not kw.get("source_refs"):
            kw["source_refs"] = (ref,)

        # Deterministic content-derived id when the record has none.
        if not kw.get("event_id"):
            digest = hashlib.sha256(
                json.dumps(record, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:12]
            kw["event_id"] = "local.{0}.{1}".format(discipline, digest)
        if not kw.get("timestamp"):
            kw["timestamp"] = as_of or now

        # A stale file marks its events stale (preserved, never dropped, never refreshed).
        if stale and kw.get("freshness_label", "") not in ("stale", "expired"):
            kw["freshness_label"] = "stale"

        return RealityEvent(**kw)
