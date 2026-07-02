"""The Market Regime sensor agent for the Reality Mesh (IMPLEMENTATION-012D).

The FIRST real Tattva sensor. :class:`MarketRegimeAgent` reads FIXTURE-backed market / index /
breadth / volatility :class:`~reality_mesh.models.RealityEvent`s and produces
``MarketRegimeFinding``s (each an :class:`~reality_mesh.models.AgentFinding` in the
``market_regime`` discipline). It reuses the built-in ``tattva.market_regime`` descriptor
(AGENT_MAP_012 §3.3) and passes :meth:`~reality_mesh.agents.SensorAgent.run_checked`.

FIXTURE / MOCK ONLY. The agent NEVER fetches live data, opens a socket, schedules, streams, or
touches a broker (there is no such affordance in this module). It emits qualitative LABELS only:
a ``direction_label`` / ``magnitude_label`` / ``urgency_label`` / ``confidence_label`` /
``freshness_label`` drawn from the closed vocabularies in :mod:`reality_mesh.labels` -- never a
number, score, rank, buy/sell/hold, order, or thesis.

FIVE SUBAGENTS (represented structurally, AGENT_MAP_012 §3.3) roll into the finding set:

* **Index Breadth** -- % of the index above its long trend -> breadth improving / deteriorating.
* **Advance/Decline** -- advancers vs decliners -> participation tilt (feeds the overall regime).
* **Distribution Day** -- institutional-selling day count -> distribution pressure.
* **Volatility Regime** -- volatility level -> volatility expansion (a stress signal).
* **Small-Cap Risk Appetite** -- small-cap relative strength -> risk-on / risk-off appetite.

FINDING TYPES emitted: ``market_pullback`` · ``risk_on`` · ``risk_off`` ·
``breadth_deterioration`` · ``breadth_improvement`` · ``volatility_expansion`` ·
``small_cap_risk_appetite`` · ``distribution_pressure``. Each maps to a ``direction_label``:
``risk_on`` / ``breadth_improvement`` -> ``improving``; ``risk_off`` / ``market_pullback`` /
``breadth_deterioration`` / ``distribution_pressure`` / ``volatility_expansion`` ->
``deteriorating``; ``small_cap_risk_appetite`` follows its appetite reading.

HONEST GAPS. A STALE input marks the finding ``freshness_label="stale"`` (never dropped) and
records a data gap; a MISSING breadth or volatility input becomes an explicit ``data_gaps`` note
-- never a fabricated value.

Deterministic, stdlib-only, Python 3.9. No network on import; ids are content-derived; every
timestamp / ``now`` is an injected string (no wall-clock).
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

from .. import labels as _labels
from ..agents import SensorAgent
from ..models import AgentFinding, RealityEvent
from ..registry import DEFAULT_DESCRIPTORS

# --------------------------------------------------------------------------- #
# Identity -- reuse the built-in tattva.market_regime descriptor (AGENT_MAP_012). #
# --------------------------------------------------------------------------- #
_AGENT_ID = "tattva.market_regime"
_DISCIPLINE = "market_regime"

# The five discipline-scoped subagents (AGENT_MAP_012 §3.3), verbatim.
MARKET_REGIME_SUBAGENTS: Tuple[str, ...] = (
    "Index Breadth",
    "Advance/Decline",
    "Distribution Day",
    "Volatility Regime",
    "Small-Cap Risk Appetite",
)

# The finding types this agent may produce (descriptive, NOT numbers). Each is an AgentFinding
# whose structural subtype is ``MarketRegimeFinding``.
MARKET_REGIME_FINDING_TYPES: Tuple[str, ...] = (
    "market_pullback",
    "risk_on",
    "risk_off",
    "breadth_deterioration",
    "breadth_improvement",
    "volatility_expansion",
    "small_cap_risk_appetite",
    "distribution_pressure",
)

# finding_type -> direction_label (closed DIRECTION_LABELS). small_cap follows its reading and so
# is resolved at runtime, not here.
_TYPE_DIRECTION: Dict[str, str] = {
    "risk_on": "improving",
    "breadth_improvement": "improving",
    "risk_off": "deteriorating",
    "market_pullback": "deteriorating",
    "breadth_deterioration": "deteriorating",
    "distribution_pressure": "deteriorating",
    "volatility_expansion": "deteriorating",
}

# Subagent-input keys expected in an event's numeric_values (raw observations -> the agent maps
# them to LABELS; the finding itself carries no number).
_KEY_BREADTH = "pct_above_200dma"
_KEY_ADV_DECL = "adv_decl_ratio"
_KEY_DISTRIBUTION = "distribution_day_count"
_KEY_VOLATILITY = "vix_level"
_KEY_SMALL_CAP = "small_cap_relative_strength"

# Freshness ordering (stalest first) for a conservative roll-up; stale/expired are surfaced.
_FRESHNESS_STALE = ("stale", "expired")
_FRESHNESS_REAL_ORDER = ("expired", "stale", "aging", "recent", "fresh")
_CONFIDENCE_ORDER = ("missing", "unknown", "very_low", "low", "moderate", "high", "very_high")


# --------------------------------------------------------------------------- #
# Fixture loader (offline; JSON -> RealityEvent). NO network.                   #
# --------------------------------------------------------------------------- #
def events_from_fixture(source) -> Tuple[RealityEvent, ...]:
    """Load a deterministic JSON fixture into a tuple of :class:`RealityEvent`s (OFFLINE).

    ``source`` is a path to a JSON file (``{"events": [ ... ]}`` or a bare list) or an already
    parsed ``dict`` / ``list``. Reads the local filesystem only -- no network, no scheduler.
    """
    if isinstance(source, (dict, list)):
        payload = source
    else:
        with open(source, encoding="utf-8") as fh:
            payload = json.load(fh)
    records = payload["events"] if isinstance(payload, dict) else payload
    return tuple(_event_from_record(rec) for rec in records)


_TUPLE_FIELDS = (
    "affected_companies", "affected_themes", "affected_sectors", "affected_value_chains",
    "text_excerpt_refs", "evidence_refs", "source_refs", "conflicts", "data_gaps",
)


def _event_from_record(rec: Dict) -> RealityEvent:
    kw = dict(rec)
    for name in _TUPLE_FIELDS:
        if name in kw and kw[name] is not None:
            kw[name] = tuple(kw[name])
    if "numeric_values" in kw and kw["numeric_values"] is not None:
        kw["numeric_values"] = tuple(tuple(nv) for nv in kw["numeric_values"])
    return RealityEvent(**kw)


# --------------------------------------------------------------------------- #
# Small pure helpers (labels / rollup, NO numeric output on any finding).       #
# --------------------------------------------------------------------------- #
def _num_by_key(event: RealityEvent, key: str) -> Optional[float]:
    """Return the numeric reading named ``key`` on ``event`` (else the first numeric, else None)."""
    for name, value, _unit in event.numeric_values:
        if name == key:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    for _name, value, _unit in event.numeric_values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _subagent_of(event: RealityEvent) -> str:
    """Classify which subagent an event feeds (by event_type token). '' if none."""
    et = (event.event_type or "").lower()
    if "breadth" in et or "index" in et:
        return "Index Breadth"
    if "advance" in et or "adv_decl" in et or "a/d" in et:
        return "Advance/Decline"
    if "distribution" in et:
        return "Distribution Day"
    if "volatility" in et or "vix" in et:
        return "Volatility Regime"
    if "small_cap" in et or "risk_appetite" in et:
        return "Small-Cap Risk Appetite"
    return ""


def _weakest_freshness(events: Tuple[RealityEvent, ...]) -> str:
    """The stalest real freshness label among ``events`` (missing if none real)."""
    present = [e.freshness_label for e in events if e.freshness_label in _FRESHNESS_REAL_ORDER]
    if not present:
        return "missing"
    return min(present, key=lambda v: _FRESHNESS_REAL_ORDER.index(v))


def _weakest_confidence(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.confidence_label for e in events
               if e.confidence_label not in ("", "missing")]
    if not present:
        return "moderate"
    return min(present, key=lambda v: _CONFIDENCE_ORDER.index(v)
               if v in _CONFIDENCE_ORDER else len(_CONFIDENCE_ORDER))


def _best_authority(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.source_authority for e in events if e.source_authority]
    if not present:
        return "convenience"
    return max(present, key=_labels.authority_rank)


def _stale_note(events: Tuple[RealityEvent, ...]) -> Optional[str]:
    stale_ids = sorted(e.event_id for e in events if e.freshness_label in _FRESHNESS_STALE)
    if stale_ids:
        return "stale market data preserved (not dropped): {0}".format(", ".join(stale_ids))
    return None


# --------------------------------------------------------------------------- #
# Internal subagent verdict (NOT an output object -- a plain tuple).            #
# --------------------------------------------------------------------------- #
class _Reading:
    """One subagent's interpretation of its input event(s). Pure data, never emitted."""

    __slots__ = ("subagent", "finding_type", "direction", "magnitude", "urgency",
                 "summary", "events")

    def __init__(self, subagent, finding_type, direction, magnitude, urgency, summary, events):
        self.subagent = subagent
        self.finding_type = finding_type
        self.direction = direction
        self.magnitude = magnitude
        self.urgency = urgency
        self.summary = summary
        self.events = events


# --------------------------------------------------------------------------- #
# MarketRegimeAgent                                                            #
# --------------------------------------------------------------------------- #
class MarketRegimeAgent(SensorAgent):
    """FIXTURE-backed Tattva Market Regime sensor. Emits ``MarketRegimeFinding``s (labels only)."""

    _AGENT_NAME = "Market Regime"

    def __init__(self) -> None:
        # Reuse the built-in tattva.market_regime descriptor (agent_id / discipline / emit
        # contract) rather than hand-rolling one -- single source of identity.
        self._descriptor = next(
            d for d in DEFAULT_DESCRIPTORS if d.agent_id == _AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    # -- run ------------------------------------------------------------- #
    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Interpret market/index/breadth/volatility events into MarketRegimeFindings.

        Deterministic + offline: reads only the injected ``events`` (from fixtures), classifies
        each into its subagent, and emits one finding per triggered subagent plus an overall
        regime finding. Missing breadth/volatility -> explicit data gap; stale input -> the
        finding is marked stale (never dropped).
        """
        # Only market_regime-discipline events (or events that clearly feed a subagent) are ours.
        mine = tuple(
            e for e in events
            if e.discipline == _DISCIPLINE or _subagent_of(e) != "")

        buckets: Dict[str, List[RealityEvent]] = {name: [] for name in MARKET_REGIME_SUBAGENTS}
        for e in mine:
            sub = _subagent_of(e)
            if sub:
                buckets[sub].append(e)

        readings: List[_Reading] = []
        readings.extend(self._read_breadth(tuple(buckets["Index Breadth"])) or [])
        readings.extend(self._read_distribution(tuple(buckets["Distribution Day"])) or [])
        readings.extend(self._read_volatility(tuple(buckets["Volatility Regime"])) or [])
        readings.extend(self._read_small_cap(tuple(buckets["Small-Cap Risk Appetite"])) or [])
        adv_decl_tilt = self._advance_decline_tilt(tuple(buckets["Advance/Decline"]))

        # Required-input gaps: breadth + volatility are core to a regime read (never invented).
        aggregate_gaps: List[str] = []
        if not buckets["Index Breadth"]:
            aggregate_gaps.append(
                "missing breadth input: Index Breadth subagent has no data (regime read partial)")
        if not buckets["Volatility Regime"]:
            aggregate_gaps.append(
                "missing volatility input: Volatility Regime subagent has no data")

        findings: List[AgentFinding] = [self._finding_from_reading(r) for r in readings]

        overall = self._overall_finding(readings, adv_decl_tilt, mine, aggregate_gaps)
        if overall is not None:
            findings.append(overall)
        elif aggregate_gaps and findings:
            # No tilt but real gaps exist and we have at least one subagent finding: surface the
            # gaps on an explicit overall finding so a missing input is never silently swallowed.
            findings.append(self._gap_only_finding(mine, aggregate_gaps))

        return tuple(findings)

    # -- subagent readers ------------------------------------------------- #
    def _read_breadth(self, evs: Tuple[RealityEvent, ...]) -> List[_Reading]:
        if not evs:
            return []
        v = _num_by_key(evs[0], _KEY_BREADTH)
        if v is None:
            return []
        if v <= 40:
            mag = "extreme" if v <= 25 else ("major" if v <= 35 else "moderate")
            return [_Reading("Index Breadth", "breadth_deterioration", "deteriorating", mag,
                             "elevated", "breadth deteriorating: {0}% above 200DMA".format(v),
                             evs)]
        if v >= 60:
            mag = "major" if v >= 75 else "moderate"
            return [_Reading("Index Breadth", "breadth_improvement", "improving", mag, "watch",
                             "breadth improving: {0}% above 200DMA".format(v), evs)]
        return []

    def _read_distribution(self, evs: Tuple[RealityEvent, ...]) -> List[_Reading]:
        if not evs:
            return []
        v = _num_by_key(evs[0], _KEY_DISTRIBUTION)
        if v is None or v < 5:
            return []
        mag = "major" if v >= 8 else "moderate"
        return [_Reading("Distribution Day", "distribution_pressure", "deteriorating", mag,
                         "elevated", "distribution pressure: {0} distribution days".format(int(v)),
                         evs)]

    def _read_volatility(self, evs: Tuple[RealityEvent, ...]) -> List[_Reading]:
        if not evs:
            return []
        v = _num_by_key(evs[0], _KEY_VOLATILITY)
        if v is None or v < 25:
            return []
        mag = "extreme" if v >= 35 else ("major" if v >= 30 else "moderate")
        urg = "high" if v >= 35 else "elevated"
        return [_Reading("Volatility Regime", "volatility_expansion", "deteriorating", mag, urg,
                         "volatility expansion: level {0}".format(v), evs)]

    def _read_small_cap(self, evs: Tuple[RealityEvent, ...]) -> List[_Reading]:
        if not evs:
            return []
        v = _num_by_key(evs[0], _KEY_SMALL_CAP)
        if v is None:
            return []
        if v >= 1.0:
            return [_Reading("Small-Cap Risk Appetite", "small_cap_risk_appetite", "improving",
                             "moderate", "watch",
                             "small-cap risk appetite ON (rel strength {0})".format(v), evs)]
        if v <= -1.0:
            return [_Reading("Small-Cap Risk Appetite", "small_cap_risk_appetite", "deteriorating",
                             "moderate", "watch",
                             "small-cap risk appetite OFF (rel strength {0})".format(v), evs)]
        return []

    def _advance_decline_tilt(self, evs: Tuple[RealityEvent, ...]) -> int:
        """Advance/Decline participation tilt: +1 improving, -1 deteriorating, 0 neutral/absent."""
        if not evs:
            return 0
        v = _num_by_key(evs[0], _KEY_ADV_DECL)
        if v is None:
            return 0
        if v >= 1.5:
            return 1
        if v <= 0.6:
            return -1
        return 0

    # -- finding builders ------------------------------------------------- #
    def _finding_from_reading(self, r: _Reading) -> AgentFinding:
        direction = _TYPE_DIRECTION.get(r.finding_type, r.direction)
        gaps: List[str] = []
        note = _stale_note(r.events)
        if note:
            gaps.append(note)
        freshness = _weakest_freshness(r.events)
        return self._build_finding(
            finding_type=r.finding_type, direction=direction, magnitude=r.magnitude,
            urgency=r.urgency, summary=r.summary, events=r.events, freshness=freshness,
            corroboration="uncorroborated", gaps=gaps)

    def _overall_finding(self, readings, adv_decl_tilt, events, aggregate_gaps):
        deteriorating = [r for r in readings if r.direction == "deteriorating"]
        improving = [r for r in readings if r.direction == "improving"]
        det = len(deteriorating) + (1 if adv_decl_tilt < 0 else 0)
        imp = len(improving) + (1 if adv_decl_tilt > 0 else 0)

        has_breadth_det = any(r.finding_type == "breadth_deterioration" for r in readings)
        has_pressure = any(
            r.finding_type in ("distribution_pressure", "volatility_expansion") for r in readings)

        if has_breadth_det and has_pressure:
            finding_type, direction = "market_pullback", "deteriorating"
        elif det > imp:
            finding_type, direction = "risk_off", "deteriorating"
        elif imp > det:
            finding_type, direction = "risk_on", "improving"
        else:
            return None

        contributing = tuple(events)
        gaps = list(aggregate_gaps)
        note = _stale_note(contributing)
        if note:
            gaps.append(note)
        # >=2 independent subagents agreeing on the tilt -> internally corroborated across subagents.
        agree = deteriorating if direction == "deteriorating" else improving
        corroboration = "corroborated" if len(agree) >= 2 else "uncorroborated"
        magnitude = "major" if len(agree) >= 3 else ("moderate" if len(agree) >= 1 else "minor")
        urgency = "elevated" if (finding_type in ("market_pullback", "risk_off")) else "watch"
        summary = "{0}: {1} deteriorating / {2} improving subagent signal(s)".format(
            finding_type, det, imp)
        return self._build_finding(
            finding_type=finding_type, direction=direction, magnitude=magnitude, urgency=urgency,
            summary=summary, events=contributing, freshness=_weakest_freshness(contributing),
            corroboration=corroboration, gaps=gaps)

    def _gap_only_finding(self, events, aggregate_gaps):
        return self._build_finding(
            finding_type="risk_off", direction="neutral", magnitude="minor", urgency="watch",
            summary="market regime read incomplete: {0} gap(s)".format(len(aggregate_gaps)),
            events=tuple(events), freshness=_weakest_freshness(tuple(events)),
            corroboration="uncorroborated", gaps=list(aggregate_gaps))

    def _build_finding(self, finding_type, direction, magnitude, urgency, summary, events,
                       freshness, corroboration, gaps) -> AgentFinding:
        evs = tuple(events)
        evidence_refs: Tuple[str, ...] = tuple(sorted({
            r for e in evs for r in e.evidence_refs}))
        source_refs: Tuple[str, ...] = tuple(sorted({
            r for e in evs for r in e.source_refs}))
        conflicts: Tuple[str, ...] = tuple(sorted({c for e in evs for c in e.conflicts}))
        inherited_gaps = sorted({g for e in evs for g in e.data_gaps})
        data_gaps = tuple(dict.fromkeys(list(gaps) + inherited_gaps))
        return AgentFinding(
            finding_id="finding.market_regime.{0}".format(finding_type),
            agent_id=_AGENT_ID,
            agent_layer="Tattva",
            agent_name=self._AGENT_NAME,
            discipline=_DISCIPLINE,
            input_events=tuple(e.event_id for e in evs),
            finding_type=finding_type,
            finding_summary=summary,
            direction_label=direction,
            magnitude_label=magnitude,
            urgency_label=urgency,
            confidence_label=_weakest_confidence(evs),
            freshness_label=freshness,
            half_life="days",
            source_authority_summary=_best_authority(evs),
            corroboration_status=corroboration,
            contradiction_status="unopposed",
            evidence_refs=evidence_refs,
            source_refs=source_refs,
            conflicts=conflicts,
            data_gaps=data_gaps,
            routing_targets=("TattvaSignalFusion",),
        )
