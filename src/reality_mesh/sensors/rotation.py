"""The Sector Rotation + Theme Rotation sensor agents for the Reality Mesh (IMPLEMENTATION-012E).

Two more real Tattva sensors, mirroring the 012D :mod:`reality_mesh.sensors.market_regime`
pattern (SensorAgent + fixture loader + ``run_checked`` + finding construction). Both read
FIXTURE-backed :class:`~reality_mesh.models.RealityEvent`s and produce
:class:`~reality_mesh.models.AgentFinding`s only:

* :class:`SectorRotationAgent` (``tattva.sector_rotation``, discipline ``sector_rotation``) --
  subagents **Sector ETF Relative Strength · Industry Group Breadth · Volume Expansion ·
  Institutional Flow Proxy**. Finding types: ``rotation_into_sector`` · ``rotation_out_of_sector``
  · ``sector_leadership_change`` · ``sector_exhaustion``. Any institutional-flow figure is ALWAYS
  presented as a labelled PROXY (``flow_proxy``) -- NEVER as verified institutional flow. A
  missing flow input is an explicit data gap, never fabricated.
* :class:`ThemeRotationAgent` (``tattva.theme_rotation``, discipline ``theme_rotation``) --
  subagents **Theme Basket Builder · Theme Relative Strength · Theme Breadth · Theme Momentum ·
  Theme Crowding**. Finding types: ``theme_ignition`` · ``theme_broadening`` · ``theme_exhaustion``
  · ``theme_crowding``. The theme basket COMPOSITION (the member tickers) is EXPLICIT in the
  input and carried on every finding; a declared basket member with no data is a data gap.
  ``theme_broadening`` requires breadth across MULTIPLE (>= 3) members -- a one-stock move reads
  as ignition, NEVER as broadening. ``theme_crowding`` fires when price / narrative breadth is
  excessive.

FIXTURE / MOCK ONLY. Neither agent fetches live data, opens a socket, schedules, streams, or
touches a broker (there is no such affordance in this module). Both emit qualitative LABELS only
(``direction_label`` / ``magnitude_label`` / ``urgency_label`` / ``confidence_label`` /
``freshness_label`` from :mod:`reality_mesh.labels`) -- never a number, score, rank, buy/sell/hold,
order, or thesis, and NO stock-first ranking. Stale input is marked ``stale`` (never dropped) and
recorded as a gap; missing input becomes an explicit ``data_gaps`` note, never a fabricated value.

Deterministic, stdlib-only, Python 3.9. No network on import; ids are content-derived; every
``now`` / timestamp is an injected string (no wall-clock).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .. import labels as _labels
from ..agents import SensorAgent
from ..models import AgentFinding, RealityEvent
from ..registry import DEFAULT_DESCRIPTORS
from .market_regime import events_from_fixture  # reuse the 012D offline JSON loader

# --------------------------------------------------------------------------- #
# Identity -- reuse the built-in descriptors (AGENT_MAP_012 §3.3).             #
# --------------------------------------------------------------------------- #
_SECTOR_AGENT_ID = "tattva.sector_rotation"
_SECTOR_DISCIPLINE = "sector_rotation"
_THEME_AGENT_ID = "tattva.theme_rotation"
_THEME_DISCIPLINE = "theme_rotation"

SECTOR_ROTATION_SUBAGENTS: Tuple[str, ...] = (
    "Sector ETF Relative Strength",
    "Industry Group Breadth",
    "Volume Expansion",
    "Institutional Flow Proxy",
)

THEME_ROTATION_SUBAGENTS: Tuple[str, ...] = (
    "Theme Basket Builder",
    "Theme Relative Strength",
    "Theme Breadth",
    "Theme Momentum",
    "Theme Crowding",
)

SECTOR_ROTATION_FINDING_TYPES: Tuple[str, ...] = (
    "rotation_into_sector",
    "rotation_out_of_sector",
    "sector_leadership_change",
    "sector_exhaustion",
)

THEME_ROTATION_FINDING_TYPES: Tuple[str, ...] = (
    "theme_ignition",
    "theme_broadening",
    "theme_exhaustion",
    "theme_crowding",
)

# finding_type -> direction_label (closed DIRECTION_LABELS).
_TYPE_DIRECTION: Dict[str, str] = {
    "rotation_into_sector": "improving",
    "rotation_out_of_sector": "deteriorating",
    "sector_leadership_change": "reversing",
    "sector_exhaustion": "decelerating",
    "theme_ignition": "accelerating",
    "theme_broadening": "improving",
    "theme_exhaustion": "decelerating",
    "theme_crowding": "reversing",
}

# The institutional-flow caveat, stamped on every sector finding that read a flow figure -- the
# flow is a PROXY only and is never presented as verified institutional flow.
FLOW_PROXY_CAVEAT = (
    "institutional flow shown as a PROXY (flow_proxy) only -- not verified institutional flow")
_FLOW_MISSING_GAP = (
    "institutional flow proxy missing (no flow_proxy input; not fabricated)")

# The minimum number of DISTINCT participating basket members required to call a move
# "broadening". Below this a move is (at most) a narrow ignition, never a broadening.
BROADENING_MIN_MEMBERS = 3

# Subagent-input numeric keys (raw observations -> the agent maps them to LABELS; the finding
# itself carries no number).
_K_SECTOR_RS = "sector_relative_strength"
_K_INDUSTRY_BREADTH = "industry_group_breadth"
_K_VOLUME = "volume_expansion_ratio"
_K_FLOW = "flow_proxy_zscore"
_K_LEADERSHIP = "leadership_change"
_K_SECTOR_EXHAUSTION = "sector_exhaustion_flag"

_K_THEME_RS = "theme_relative_strength"
_K_THEME_MOMENTUM = "theme_momentum"
_K_THEME_CROWDING = "theme_crowding_pressure"
_K_NARRATIVE_BREADTH = "narrative_breadth"
_K_BASKET_SIZE = "basket_expected_size"
_K_MEMBER_ADVANCING = "member_advancing"

_FRESHNESS_STALE = ("stale", "expired")
_FRESHNESS_REAL_ORDER = ("expired", "stale", "aging", "recent", "fresh")
_CONFIDENCE_ORDER = ("missing", "unknown", "very_low", "low", "moderate", "high", "very_high")


# --------------------------------------------------------------------------- #
# Small pure helpers (labels / rollup, NO numeric output on any finding).       #
# --------------------------------------------------------------------------- #
def _num_in(events: Tuple[RealityEvent, ...], key: str) -> Optional[float]:
    """First numeric reading named ``key`` across ``events`` (else None). No fabrication."""
    for event in events:
        for name, value, _unit in event.numeric_values:
            if name == key:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
    return None


def _weakest_freshness(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.freshness_label for e in events if e.freshness_label in _FRESHNESS_REAL_ORDER]
    if not present:
        return "missing"
    return min(present, key=lambda v: _FRESHNESS_REAL_ORDER.index(v))


def _weakest_confidence(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.confidence_label for e in events if e.confidence_label not in ("", "missing")]
    if not present:
        return "moderate"
    return min(present, key=lambda v: _CONFIDENCE_ORDER.index(v)
               if v in _CONFIDENCE_ORDER else len(_CONFIDENCE_ORDER))


def _best_authority(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.source_authority for e in events if e.source_authority]
    if not present:
        return "convenience"
    return max(present, key=_labels.authority_rank)


def _stale_note(events: Tuple[RealityEvent, ...], kind: str) -> Optional[str]:
    stale_ids = sorted(e.event_id for e in events if e.freshness_label in _FRESHNESS_STALE)
    if stale_ids:
        return "stale {0} data preserved (not dropped): {1}".format(
            kind, ", ".join(stale_ids))
    return None


class _Reading:
    """One subagent verdict. Pure data, never emitted."""

    __slots__ = ("finding_type", "direction", "magnitude", "urgency", "summary", "events",
                 "extra_gaps", "companies", "themes", "sectors")

    def __init__(self, finding_type, direction, magnitude, urgency, summary, events,
                 extra_gaps=None, companies=(), themes=(), sectors=()):
        self.finding_type = finding_type
        self.direction = direction
        self.magnitude = magnitude
        self.urgency = urgency
        self.summary = summary
        self.events = events
        self.extra_gaps = list(extra_gaps or [])
        self.companies = tuple(companies)
        self.themes = tuple(themes)
        self.sectors = tuple(sectors)


# --------------------------------------------------------------------------- #
# Shared finding construction                                                  #
# --------------------------------------------------------------------------- #
def _finding_from_reading(reading: _Reading, agent_id: str, agent_name: str, discipline: str,
                          subject_slug: str, stale_kind: str) -> AgentFinding:
    evs = tuple(reading.events)
    direction = _TYPE_DIRECTION.get(reading.finding_type, reading.direction)
    gaps: List[str] = list(reading.extra_gaps)
    note = _stale_note(evs, stale_kind)
    if note:
        gaps.append(note)
    evidence_refs = tuple(sorted({r for e in evs for r in e.evidence_refs}))
    source_refs = tuple(sorted({r for e in evs for r in e.source_refs}))
    conflicts = tuple(sorted({c for e in evs for c in e.conflicts}))
    inherited_gaps = sorted({g for e in evs for g in e.data_gaps})
    data_gaps = tuple(dict.fromkeys(list(gaps) + inherited_gaps))
    return AgentFinding(
        finding_id="finding.{0}.{1}.{2}".format(discipline, reading.finding_type, subject_slug),
        agent_id=agent_id,
        agent_layer="reality_intelligence",
        agent_name=agent_name,
        discipline=discipline,
        input_events=tuple(e.event_id for e in evs),
        finding_type=reading.finding_type,
        finding_summary=reading.summary,
        affected_companies=reading.companies,
        affected_themes=reading.themes,
        affected_sectors=reading.sectors,
        direction_label=direction,
        magnitude_label=reading.magnitude,
        urgency_label=reading.urgency,
        confidence_label=_weakest_confidence(evs),
        freshness_label=_weakest_freshness(evs),
        half_life="days",
        source_authority_summary=_best_authority(evs),
        corroboration_status="uncorroborated",
        contradiction_status="unopposed",
        evidence_refs=evidence_refs,
        source_refs=source_refs,
        conflicts=conflicts,
        data_gaps=data_gaps,
        routing_targets=("TattvaSignalFusion",),
    )


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


# --------------------------------------------------------------------------- #
# SectorRotationAgent                                                          #
# --------------------------------------------------------------------------- #
class SectorRotationAgent(SensorAgent):
    """FIXTURE-backed Tattva Sector Rotation sensor. Emits ``SectorRotationFinding``s (labels only).

    Groups sector-rotation events by their ``affected_sectors`` and, per sector, reads its four
    subagents from the event numeric_values: Sector ETF Relative Strength, Industry Group Breadth,
    Volume Expansion, and Institutional Flow Proxy. The flow figure is ALWAYS a labelled proxy;
    when it is absent that absence is an explicit gap. NO stock-first ranking, no score/rank.
    """

    _AGENT_NAME = "Sector Rotation"

    def __init__(self) -> None:
        self._descriptor = next(d for d in DEFAULT_DESCRIPTORS if d.agent_id == _SECTOR_AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        mine = tuple(e for e in events if e.discipline == _SECTOR_DISCIPLINE)
        by_sector: Dict[str, List[RealityEvent]] = {}
        for e in mine:
            for sector in (e.affected_sectors or ("__unscoped__",)):
                by_sector.setdefault(sector, []).append(e)

        findings: List[AgentFinding] = []
        for sector in sorted(by_sector):
            evs = tuple(by_sector[sector])
            for reading in self._read_sector(sector, evs):
                findings.append(_finding_from_reading(
                    reading, _SECTOR_AGENT_ID, self._AGENT_NAME, _SECTOR_DISCIPLINE,
                    _slug(sector), "sector"))
        return tuple(sorted(findings, key=lambda f: f.finding_id))

    def _read_sector(self, sector: str, evs: Tuple[RealityEvent, ...]) -> List[_Reading]:
        rs = _num_in(evs, _K_SECTOR_RS)
        breadth = _num_in(evs, _K_INDUSTRY_BREADTH)
        vol = _num_in(evs, _K_VOLUME)
        flow = _num_in(evs, _K_FLOW)
        leadership = _num_in(evs, _K_LEADERSHIP)
        exhaustion_flag = _num_in(evs, _K_SECTOR_EXHAUSTION)

        # Institutional Flow Proxy -- always a labelled proxy; missing flow is an explicit gap.
        flow_gaps: List[str] = []
        flow_phrase = ""
        if flow is None:
            flow_gaps.append(_FLOW_MISSING_GAP)
        else:
            flow_gaps.append(FLOW_PROXY_CAVEAT)
            flow_phrase = "; flow PROXY (flow_proxy) reads {0} -- not verified institutional flow".format(
                flow)

        sectors = (sector,) if sector != "__unscoped__" else ()
        readings: List[_Reading] = []

        # Sector leadership change (independent flag).
        if leadership is not None and leadership >= 1.0:
            readings.append(_Reading(
                "sector_leadership_change", "reversing", "moderate", "watch",
                "sector leadership rotating in {0} (relative strength {1}){2}".format(
                    sector, rs if rs is not None else "n/a", flow_phrase),
                evs, extra_gaps=flow_gaps, sectors=sectors))

        if rs is not None:
            if rs >= 1.0:
                exhausted = (
                    (exhaustion_flag is not None and exhaustion_flag >= 1.0)
                    or (breadth is not None and breadth <= 40)
                    or (vol is not None and vol < 1.0))
                if exhausted:
                    readings.append(_Reading(
                        "sector_exhaustion", "decelerating", "moderate", "elevated",
                        "sector exhaustion in {0}: relative strength {1} but narrow "
                        "participation / fading volume{2}".format(sector, rs, flow_phrase),
                        evs, extra_gaps=flow_gaps, sectors=sectors))
                else:
                    mag = "major" if rs >= 2.0 else "moderate"
                    confirm = " (broad participation)" if (breadth is not None and breadth >= 55) \
                        else (" (volume expanding)" if (vol is not None and vol >= 1.2) else "")
                    readings.append(_Reading(
                        "rotation_into_sector", "improving", mag, "watch",
                        "rotation INTO {0}: relative strength {1}{2}{3}".format(
                            sector, rs, confirm, flow_phrase),
                        evs, extra_gaps=flow_gaps, sectors=sectors))
            elif rs <= -1.0:
                mag = "major" if rs <= -2.0 else "moderate"
                readings.append(_Reading(
                    "rotation_out_of_sector", "deteriorating", mag, "elevated",
                    "rotation OUT of {0}: relative strength {1}{2}".format(
                        sector, rs, flow_phrase),
                    evs, extra_gaps=flow_gaps, sectors=sectors))
        return readings


# --------------------------------------------------------------------------- #
# ThemeRotationAgent                                                           #
# --------------------------------------------------------------------------- #
class ThemeRotationAgent(SensorAgent):
    """FIXTURE-backed Tattva Theme Rotation sensor. Emits ``ThemeRotationFinding``s (labels only).

    Groups theme-rotation events by ``affected_themes``. The Theme Basket Builder declares the
    EXPLICIT basket composition (member tickers) on the basket event's ``affected_companies``;
    that composition is carried onto every finding, and any declared member with no data becomes
    an explicit data gap (never fabricated). Breadth is counted from DISTINCT participating member
    records: ``theme_broadening`` requires >= ``BROADENING_MIN_MEMBERS`` participating members, so
    a one-stock move reads as ignition, never as broadening. ``theme_crowding`` fires when price /
    narrative breadth is excessive. NO stock-first ranking, no score/rank.
    """

    _AGENT_NAME = "Theme Rotation"

    def __init__(self) -> None:
        self._descriptor = next(d for d in DEFAULT_DESCRIPTORS if d.agent_id == _THEME_AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        mine = tuple(e for e in events if e.discipline == _THEME_DISCIPLINE)
        by_theme: Dict[str, List[RealityEvent]] = {}
        for e in mine:
            for theme in (e.affected_themes or ("__unscoped__",)):
                by_theme.setdefault(theme, []).append(e)

        findings: List[AgentFinding] = []
        for theme in sorted(by_theme):
            evs = tuple(by_theme[theme])
            for reading in self._read_theme(theme, evs):
                findings.append(_finding_from_reading(
                    reading, _THEME_AGENT_ID, self._AGENT_NAME, _THEME_DISCIPLINE,
                    _slug(theme), "theme"))
        return tuple(sorted(findings, key=lambda f: f.finding_id))

    def _read_theme(self, theme: str, evs: Tuple[RealityEvent, ...]) -> List[_Reading]:
        themes = (theme,) if theme != "__unscoped__" else ()

        # -- Theme Basket Builder: the EXPLICIT basket composition. -------------- #
        basket_events = tuple(e for e in evs if "basket" in (e.event_type or "").lower())
        declared: Tuple[str, ...] = tuple(dict.fromkeys(
            c for e in basket_events for c in e.affected_companies))
        expected_size = _num_in(evs, _K_BASKET_SIZE)

        member_events = tuple(e for e in evs if "member" in (e.event_type or "").lower())
        members_with_data: Tuple[str, ...] = tuple(dict.fromkeys(
            c for e in member_events for c in e.affected_companies))
        participating = tuple(dict.fromkeys(
            c for e in member_events for c in e.affected_companies
            if _num_in((e,), _K_MEMBER_ADVANCING) and _num_in((e,), _K_MEMBER_ADVANCING) >= 1.0))
        breadth_count = len(participating)

        basket_gaps: List[str] = []
        if not declared:
            basket_gaps.append(
                "theme basket composition not provided for {0} (explicit basket required)".format(
                    theme))
        else:
            missing = [m for m in declared if m not in members_with_data]
            if missing:
                basket_gaps.append(
                    "theme basket incomplete for {0}: {1} of {2} declared member(s) missing data "
                    "-- {3}".format(theme, len(missing), len(declared), ", ".join(missing)))
            if expected_size is not None and len(declared) < int(expected_size):
                basket_gaps.append(
                    "theme basket under-declared for {0}: {1} of {2} expected members listed".format(
                        theme, len(declared), int(expected_size)))

        basket_note = ""
        if declared:
            basket_note = "; basket [{0}]: {1} declared, {2} participating".format(
                theme, len(declared), breadth_count)

        rs = _num_in(evs, _K_THEME_RS)
        momentum = _num_in(evs, _K_THEME_MOMENTUM)
        crowding = _num_in(evs, _K_THEME_CROWDING)
        narrative = _num_in(evs, _K_NARRATIVE_BREADTH)

        readings: List[_Reading] = []

        def _reading(ftype, direction, mag, urg, summary):
            return _Reading(ftype, direction, mag, urg, summary + basket_note, evs,
                            extra_gaps=list(basket_gaps), companies=declared, themes=themes)

        # -- Theme ignition: relative strength rising with momentum (may be narrow). --- #
        if rs is not None and rs >= 1.0 and momentum is not None and momentum >= 0.5:
            readings.append(_reading(
                "theme_ignition", "accelerating", "moderate", "watch",
                "theme ignition in {0}: relative strength {1} accelerating (momentum {2})".format(
                    theme, rs, momentum)))

        # -- Theme broadening: breadth across MULTIPLE members (never a one-stock move). - #
        if breadth_count >= BROADENING_MIN_MEMBERS and rs is not None and rs >= 1.0:
            mag = "major" if breadth_count >= 5 else "moderate"
            readings.append(_reading(
                "theme_broadening", "improving", mag, "watch",
                "theme broadening in {0}: {1} distinct basket members participating".format(
                    theme, breadth_count)))

        # -- Theme crowding: price / narrative breadth excessive. ---------------------- #
        crowded = (crowding is not None and crowding >= 70) or (
            narrative is not None and narrative >= 70)
        if crowded:
            level = max(crowding or 0.0, narrative or 0.0)
            mag = "extreme" if level >= 85 else "major"
            readings.append(_reading(
                "theme_crowding", "reversing", mag, "elevated",
                "theme crowding in {0}: price/narrative breadth excessive "
                "(crowding {1}, narrative {2})".format(theme, crowding, narrative)))

        # -- Theme exhaustion: momentum decelerating. ---------------------------------- #
        if momentum is not None and momentum <= -0.5:
            readings.append(_reading(
                "theme_exhaustion", "decelerating", "moderate", "elevated",
                "theme exhaustion in {0}: momentum decelerating ({1})".format(theme, momentum)))

        # No finding fired but the basket has honest gaps: surface them so a missing member is
        # never silently swallowed.
        if not readings and basket_gaps:
            readings.append(_Reading(
                "theme_ignition", "neutral", "minor", "watch",
                "theme {0} read incomplete: basket gaps only".format(theme) + basket_note,
                evs, extra_gaps=list(basket_gaps), companies=declared, themes=themes))
        return readings
