"""The Macro Regime sensor agent for the Reality Mesh (IMPLEMENTATION-014F).

:class:`MacroRegimeAgent` reads market-wide macro-reading
:class:`~reality_mesh.models.RealityEvent`s (named readings supplied by the local
macro-data adapter: rates level + delta, the 2s10s curve, the dollar, credit spreads,
CPI / jobs surprises, a liquidity proxy, VIX) and produces ``MacroRegimeFinding``s (each an
:class:`~reality_mesh.models.AgentFinding` in the ``macro_regime`` discipline). It reuses
the built-in ``tattva.macro_regime`` descriptor (AGENT_MAP_012 §3.3) and passes
:meth:`~reality_mesh.agents.SensorAgent.run_checked`.

MACRO STATES ARE LABELS, NEVER TRADE SIGNALS. Every finding is a macro-condition LABEL with
a direction label drawn from the closed vocabularies in :mod:`reality_mesh.labels` -- never
a number, score, rank, or an instruction to act.

SEVEN SUBAGENTS (represented structurally, AGENT_MAP_012 §3.3) roll into the finding set:

* **Rates** -- policy-rate delta -> ``duration_pressure`` when rates step UP (an easing step
  feeds the risk-on tilt).
* **Yield Curve** -- the 2s10s spread -> ``curve_inversion`` / ``curve_steepening``.
* **Dollar** -- DXY change -> a risk-appetite tilt (a dollar spike tightens global
  conditions; a dollar slide loosens them).
* **Credit Spread** -- high-yield spread delta -> ``liquidity_tightening`` /
  ``liquidity_easing``; an extreme widening reads ``macro_shock``.
* **Inflation/Jobs Surprise** -- a hot CPI print or a big jobs miss -> ``macro_shock`` (a
  cool CPI surprise feeds the risk-on tilt).
* **Liquidity** -- net-liquidity proxy change -> ``liquidity_tightening`` /
  ``liquidity_easing``.
* **VIX/Volatility** -- the volatility level -> a risk-appetite tilt.

OVERALL REGIME: the subagent verdicts + tilts roll into ``risk_off_macro`` /
``risk_on_macro``. DIRECTION LABELS: easing / risk-on / steepening -> ``improving``;
tightening / shock / inversion / duration pressure / risk-off -> ``deteriorating``;
``macro_read_incomplete`` (the explicit gap carrier) -> ``neutral``.

HONEST GAPS. A MISSING named reading is an explicit ``data_gaps`` note (a subagent verdict
is NEVER computed from nothing); a STALE input marks the finding stale (never dropped). A
read with no verdict at all yields an explicit ``macro_read_incomplete`` finding carrying
the gaps.

Deterministic, stdlib-only, Python 3.9, OFFLINE. No network on import; ids are
content-derived; no wall-clock anywhere. No scheduler / broker / score.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .. import labels as _labels
from ..agents import SensorAgent
from ..models import AgentFinding, RealityEvent
from ..registry import DEFAULT_DESCRIPTORS

__all__ = [
    "MACRO_REGIME_FINDING_TYPES",
    "MACRO_REGIME_SUBAGENTS",
    "MACRO_SUBAGENT_REQUIRED_KEYS",
    "RATES_DELTA_BPS_MIN",
    "CREDIT_SPREAD_SHOCK_DELTA_BPS",
    "CPI_SURPRISE_SHOCK_PCT",
    "LIQUIDITY_CHANGE_PCT_MIN",
    "MacroRegimeAgent",
]

# --------------------------------------------------------------------------- #
# Identity -- reuse the built-in tattva.macro_regime descriptor.                #
# --------------------------------------------------------------------------- #
_AGENT_ID = "tattva.macro_regime"
_DISCIPLINE = "macro_regime"

# The seven discipline-scoped subagents (AGENT_MAP_012 §3.3), verbatim from the registry.
MACRO_REGIME_SUBAGENTS: Tuple[str, ...] = (
    "Rates",
    "Yield Curve",
    "Dollar",
    "Credit Spread",
    "Inflation/Jobs Surprise",
    "Liquidity",
    "VIX/Volatility",
)

# The finding types this agent may produce -- macro-condition LABELS, never a trade.
# ``macro_read_incomplete`` is the explicit gap carrier for a read with no verdict at all.
MACRO_REGIME_FINDING_TYPES: Tuple[str, ...] = (
    "liquidity_tightening",
    "liquidity_easing",
    "risk_on_macro",
    "risk_off_macro",
    "duration_pressure",
    "macro_shock",
    "curve_inversion",
    "curve_steepening",
    "macro_read_incomplete",
)

# finding_type -> direction_label (closed DIRECTION_LABELS). Easing / risk-on / steepening
# -> improving; tightening / shock / inversion / duration pressure / risk-off ->
# deteriorating. Direction labels ONLY -- never an instruction to act.
_TYPE_DIRECTION: Dict[str, str] = {
    "liquidity_easing": "improving",
    "risk_on_macro": "improving",
    "curve_steepening": "improving",
    "liquidity_tightening": "deteriorating",
    "risk_off_macro": "deteriorating",
    "duration_pressure": "deteriorating",
    "macro_shock": "deteriorating",
    "curve_inversion": "deteriorating",
    "macro_read_incomplete": "neutral",
}

# Named readings expected on macro events' numeric_values (supplied by the local macro-data
# adapter). The agent performs simple threshold comparisons ONLY -- it never derives a
# reading itself and never fabricates a missing one.
_KEY_POLICY_RATE_DELTA = "policy_rate_delta_bps"
_KEY_CURVE_2S10S = "curve_2s10s_bps"
_KEY_CURVE_DELTA = "curve_2s10s_delta_bps"
_KEY_DXY_CHANGE = "dxy_change_pct"
_KEY_CREDIT_DELTA = "credit_spread_delta_bps"
_KEY_CPI_SURPRISE = "cpi_surprise_pct"
_KEY_JOBS_SURPRISE = "jobs_surprise_thousands"
_KEY_LIQUIDITY_CHANGE = "net_liquidity_change_pct"
_KEY_VIX = "vix_level"

# subagent -> the named readings it requires. A missing required reading is an explicit
# gap -- the subagent's verdict is NEVER computed from nothing.
MACRO_SUBAGENT_REQUIRED_KEYS: Dict[str, Tuple[str, ...]] = {
    "Rates": (_KEY_POLICY_RATE_DELTA,),
    "Yield Curve": (_KEY_CURVE_2S10S,),
    "Dollar": (_KEY_DXY_CHANGE,),
    "Credit Spread": (_KEY_CREDIT_DELTA,),
    "Inflation/Jobs Surprise": (_KEY_CPI_SURPRISE,),
    "Liquidity": (_KEY_LIQUIDITY_CHANGE,),
    "VIX/Volatility": (_KEY_VIX,),
}

# Thresholds (simple comparisons on the supplied readings; labels come out, never numbers).
RATES_DELTA_BPS_MIN = 25.0          # one policy step: >= +25bps pressures duration
RATES_DELTA_MAJOR_BPS = 50.0
CURVE_INVERSION_MAJOR_BPS = -50.0
CURVE_INVERSION_EXTREME_BPS = -100.0
CURVE_STEEPENING_DELTA_BPS = 25.0
DXY_TILT_PCT = 2.0                  # a >=2% dollar move tilts global conditions
CREDIT_SPREAD_MOVE_BPS = 50.0       # widening/tightening this large is a liquidity read
CREDIT_SPREAD_SHOCK_DELTA_BPS = 100.0
CPI_SURPRISE_SHOCK_PCT = 0.3        # a CPI print this far above consensus is a shock
CPI_SURPRISE_MAJOR_PCT = 0.5
JOBS_MISS_SHOCK_THOUSANDS = -100.0  # a payrolls miss this large is a shock
LIQUIDITY_CHANGE_PCT_MIN = 2.0
LIQUIDITY_CHANGE_MAJOR_PCT = 5.0
VIX_ELEVATED = 25.0
VIX_CALM = 15.0

# Freshness / confidence ordering (weakest first) for a conservative roll-up.
_FRESHNESS_STALE = ("stale", "expired")
_FRESHNESS_REAL_ORDER = ("expired", "stale", "aging", "recent", "fresh")
_CONFIDENCE_ORDER = ("missing", "unknown", "very_low", "low", "moderate", "high", "very_high")


# --------------------------------------------------------------------------- #
# Small pure helpers (labels / rollup, NO numeric output on any finding).       #
# --------------------------------------------------------------------------- #
def _readings_of(events: Tuple[RealityEvent, ...]) -> Dict[str, float]:
    """Merge the named numeric readings of ``events`` (sorted order; first value wins)."""
    readings: Dict[str, float] = {}
    for event in sorted(events, key=lambda e: e.event_id):
        for name, value, _unit in event.numeric_values:
            if name in readings:
                continue
            try:
                readings[name] = float(value)
            except (TypeError, ValueError):
                continue
    return readings


def _weakest_freshness(events: Tuple[RealityEvent, ...]) -> str:
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
        return "stale macro data preserved (not dropped): {0}".format(", ".join(stale_ids))
    return None


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


# --------------------------------------------------------------------------- #
# Internal subagent verdict (pure data, never emitted).                         #
# --------------------------------------------------------------------------- #
class _Reading:
    """One subagent's macro interpretation. Pure data, never an output object."""

    __slots__ = ("subagent", "finding_type", "magnitude", "urgency", "summary")

    def __init__(self, subagent, finding_type, magnitude, urgency, summary):
        self.subagent = subagent
        self.finding_type = finding_type
        self.magnitude = magnitude
        self.urgency = urgency
        self.summary = summary

    @property
    def direction(self) -> str:
        return _TYPE_DIRECTION[self.finding_type]


# --------------------------------------------------------------------------- #
# MacroRegimeAgent                                                              #
# --------------------------------------------------------------------------- #
class MacroRegimeAgent(SensorAgent):
    """Market-wide Tattva Macro Regime sensor. Emits ``MacroRegimeFinding``s (labels only).

    Macro conditions are LABELS informing downstream layers -- never a trade instruction,
    never a score. Missing readings are explicit gaps; stale input stays visible.
    """

    _AGENT_NAME = "Macro Regime"

    def __init__(self) -> None:
        # Reuse the built-in tattva.macro_regime descriptor (agent_id / discipline / emit
        # contract) rather than hand-rolling one -- single source of identity.
        self._descriptor = next(
            d for d in DEFAULT_DESCRIPTORS if d.agent_id == _AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    # -- run ------------------------------------------------------------- #
    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Interpret market-wide macro readings into MacroRegimeFindings.

        Deterministic + offline: reads only the injected ``events``, merges their named
        readings, and runs the seven structural subagents over the merged read. A missing
        reading becomes an explicit data gap (never a computed value); stale input marks
        the finding stale (never dropped). Findings are sorted by finding_id.
        """
        mine = tuple(sorted(
            (e for e in events if e.discipline == _DISCIPLINE),
            key=lambda e: e.event_id))
        if not mine:
            return ()

        readings = _readings_of(mine)

        # Missing-reading gaps FIRST: a subagent with an absent required reading is an
        # explicit gap -- its verdict is never computed from nothing.
        gaps: List[str] = []
        available: List[str] = []
        for subagent in MACRO_REGIME_SUBAGENTS:
            required = MACRO_SUBAGENT_REQUIRED_KEYS[subagent]
            missing = sorted(k for k in required if k not in readings)
            if missing:
                gaps.append(
                    "missing macro reading(s) {0}: {1} subagent has no reading -- gap, "
                    "never computed from nothing".format(", ".join(missing), subagent))
            else:
                available.append(subagent)

        verdicts: List[_Reading] = []
        tilt = 0
        if "Rates" in available:
            v, t = self._read_rates(readings)
            verdicts.extend(v)
            tilt += t
        if "Yield Curve" in available:
            verdicts.extend(self._read_curve(readings))
        if "Dollar" in available:
            tilt += self._dollar_tilt(readings)
        if "Credit Spread" in available:
            verdicts.extend(self._read_credit(readings))
        if "Inflation/Jobs Surprise" in available:
            v, t = self._read_surprise(readings)
            verdicts.extend(v)
            tilt += t
        if "Liquidity" in available:
            verdicts.extend(self._read_liquidity(readings))
        if "VIX/Volatility" in available:
            tilt += self._vix_tilt(readings)

        findings: List[AgentFinding] = [
            self._build_finding(
                finding_type=v.finding_type, subagent=v.subagent, magnitude=v.magnitude,
                urgency=v.urgency, summary=v.summary, events=mine,
                corroboration="uncorroborated", gaps=[])
            for v in verdicts]

        overall = self._overall_finding(verdicts, tilt, mine, gaps)
        if overall is not None:
            findings.append(overall)
        elif gaps or not verdicts:
            # No overall tilt: real gaps (or an empty read) are surfaced on an explicit
            # incomplete-read finding, never silently swallowed.
            findings.append(self._build_finding(
                finding_type="macro_read_incomplete", subagent="", magnitude="minor",
                urgency="watch",
                summary="macro regime read incomplete: {0} gap(s), {1} subagent "
                        "verdict(s)".format(len(gaps), len(verdicts)),
                events=mine, corroboration="uncorroborated", gaps=gaps))

        return tuple(sorted(findings, key=lambda f: f.finding_id))

    # -- subagent readers (simple comparisons on the supplied readings) ------ #
    def _read_rates(self, r) -> Tuple[List[_Reading], int]:
        delta = r[_KEY_POLICY_RATE_DELTA]
        if delta >= RATES_DELTA_BPS_MIN:
            mag = "major" if delta >= RATES_DELTA_MAJOR_BPS else "moderate"
            return [_Reading(
                "Rates", "duration_pressure", mag, "elevated",
                "duration pressure: the policy rate stepped up {0}bps -- long-duration "
                "assets face higher discounting (macro condition label)".format(delta))], 0
        if delta <= -RATES_DELTA_BPS_MIN:
            return [], 1        # an easing step feeds the risk-on tilt (no own verdict)
        return [], 0

    def _read_curve(self, r) -> List[_Reading]:
        level = r[_KEY_CURVE_2S10S]
        if level < 0:
            if level <= CURVE_INVERSION_EXTREME_BPS:
                mag = "extreme"
            elif level <= CURVE_INVERSION_MAJOR_BPS:
                mag = "major"
            else:
                mag = "moderate"
            return [_Reading(
                "Yield Curve", "curve_inversion", mag, "elevated",
                "curve inversion: the 2s10s spread is {0}bps (below zero)".format(level))]
        delta = r.get(_KEY_CURVE_DELTA)
        if delta is not None and delta >= CURVE_STEEPENING_DELTA_BPS:
            return [_Reading(
                "Yield Curve", "curve_steepening", "moderate", "watch",
                "curve steepening: the 2s10s spread widened {0}bps to {1}bps (above "
                "zero)".format(delta, level))]
        return []

    def _dollar_tilt(self, r) -> int:
        change = r[_KEY_DXY_CHANGE]
        if change >= DXY_TILT_PCT:
            return -1           # a dollar spike tightens global conditions
        if change <= -DXY_TILT_PCT:
            return 1
        return 0

    def _read_credit(self, r) -> List[_Reading]:
        delta = r[_KEY_CREDIT_DELTA]
        if delta >= CREDIT_SPREAD_SHOCK_DELTA_BPS:
            return [_Reading(
                "Credit Spread", "macro_shock", "major", "high",
                "macro shock: high-yield credit spreads widened {0}bps -- credit stress "
                "reading".format(delta))]
        if delta >= CREDIT_SPREAD_MOVE_BPS:
            return [_Reading(
                "Credit Spread", "liquidity_tightening", "moderate", "elevated",
                "liquidity tightening: high-yield credit spreads widened {0}bps".format(
                    delta))]
        if delta <= -CREDIT_SPREAD_MOVE_BPS:
            return [_Reading(
                "Credit Spread", "liquidity_easing", "moderate", "watch",
                "liquidity easing: high-yield credit spreads narrowed {0}bps".format(
                    abs(delta)))]
        return []

    def _read_surprise(self, r) -> Tuple[List[_Reading], int]:
        cpi = r[_KEY_CPI_SURPRISE]
        jobs = r.get(_KEY_JOBS_SURPRISE)
        out: List[_Reading] = []
        tilt = 0
        if cpi >= CPI_SURPRISE_SHOCK_PCT:
            mag = "major" if cpi >= CPI_SURPRISE_MAJOR_PCT else "moderate"
            out.append(_Reading(
                "Inflation/Jobs Surprise", "macro_shock", mag, "high",
                "macro shock: CPI printed {0}pp above consensus (hot inflation "
                "surprise)".format(cpi)))
        elif cpi <= -CPI_SURPRISE_SHOCK_PCT:
            tilt += 1           # a cool CPI surprise loosens conditions (tilt only)
        if jobs is not None and jobs <= JOBS_MISS_SHOCK_THOUSANDS:
            out.append(_Reading(
                "Inflation/Jobs Surprise", "macro_shock", "moderate", "elevated",
                "macro shock: payrolls missed consensus by {0}k jobs".format(abs(jobs))))
        return out, tilt

    def _read_liquidity(self, r) -> List[_Reading]:
        change = r[_KEY_LIQUIDITY_CHANGE]
        if change <= -LIQUIDITY_CHANGE_PCT_MIN:
            mag = "major" if change <= -LIQUIDITY_CHANGE_MAJOR_PCT else "moderate"
            return [_Reading(
                "Liquidity", "liquidity_tightening", mag, "elevated",
                "liquidity tightening: the net-liquidity proxy contracted {0}%".format(
                    abs(change)))]
        if change >= LIQUIDITY_CHANGE_PCT_MIN:
            mag = "major" if change >= LIQUIDITY_CHANGE_MAJOR_PCT else "moderate"
            return [_Reading(
                "Liquidity", "liquidity_easing", mag, "watch",
                "liquidity easing: the net-liquidity proxy expanded {0}%".format(change))]
        return []

    def _vix_tilt(self, r) -> int:
        vix = r[_KEY_VIX]
        if vix >= VIX_ELEVATED:
            return -1
        if vix <= VIX_CALM:
            return 1
        return 0

    # -- overall regime roll-up --------------------------------------------- #
    def _overall_finding(self, verdicts: List[_Reading], tilt: int,
                         events: Tuple[RealityEvent, ...],
                         gaps: List[str]) -> Optional[AgentFinding]:
        deteriorating = [v for v in verdicts if v.direction == "deteriorating"]
        improving = [v for v in verdicts if v.direction == "improving"]
        det = len(deteriorating) + (1 if tilt < 0 else 0)
        imp = len(improving) + (1 if tilt > 0 else 0)
        if det > imp:
            finding_type = "risk_off_macro"
            agree = deteriorating
            urgency = "elevated"
        elif imp > det:
            finding_type = "risk_on_macro"
            agree = improving
            urgency = "watch"
        else:
            return None
        # >=2 independent subagents agreeing on the tilt -> internally corroborated.
        corroboration = "corroborated" if len(agree) >= 2 else "uncorroborated"
        magnitude = "major" if len(agree) >= 3 else ("moderate" if agree else "minor")
        summary = "{0}: {1} deteriorating / {2} improving macro signal(s) across the "\
            "seven subagents".format(finding_type, det, imp)
        return self._build_finding(
            finding_type=finding_type, subagent="", magnitude=magnitude, urgency=urgency,
            summary=summary, events=events, corroboration=corroboration, gaps=gaps)

    # -- finding builder ------------------------------------------------------ #
    def _build_finding(self, *, finding_type: str, subagent: str, magnitude: str,
                       urgency: str, summary: str, events: Tuple[RealityEvent, ...],
                       corroboration: str, gaps: List[str]) -> AgentFinding:
        evs = tuple(sorted(events, key=lambda e: e.event_id))
        all_gaps = list(gaps)
        note = _stale_note(evs)
        if note:
            all_gaps.append(note)
        inherited_gaps = sorted({g for e in evs for g in e.data_gaps})
        data_gaps = tuple(dict.fromkeys(all_gaps + inherited_gaps))
        evidence_refs = tuple(sorted({r for e in evs for r in e.evidence_refs}))
        source_refs = tuple(sorted({r for e in evs for r in e.source_refs}))
        conflicts = tuple(sorted({c for e in evs for c in e.conflicts}))
        themes = tuple(sorted({t for e in evs for t in e.affected_themes}))
        finding_id = "finding.macro_regime.{0}".format(finding_type)
        if subagent:
            finding_id += ".{0}".format(_slug(subagent))
        return AgentFinding(
            finding_id=finding_id,
            agent_id=_AGENT_ID,
            agent_layer="reality_intelligence",
            agent_name=self._AGENT_NAME,
            discipline=_DISCIPLINE,
            input_events=tuple(e.event_id for e in evs),
            finding_type=finding_type,
            finding_summary=summary,
            affected_themes=themes,
            direction_label=_TYPE_DIRECTION[finding_type],
            magnitude_label=magnitude,
            urgency_label=urgency,
            confidence_label=_weakest_confidence(evs),
            freshness_label=_weakest_freshness(evs),
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
