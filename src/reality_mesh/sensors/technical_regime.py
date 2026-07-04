"""The Technical Regime sensor agent for the Reality Mesh (IMPLEMENTATION-014D).

:class:`TechnicalRegimeAgent` reads per-ticker price-history
:class:`~reality_mesh.models.RealityEvent`s (precomputed indicator readings supplied by the
local price-history adapter -- NEVER raw OHLCV math beyond simple comparisons) and produces
``TechnicalRegimeFinding``s (each an :class:`~reality_mesh.models.AgentFinding` in the
``technical_regime`` discipline). It reuses the built-in ``tattva.technical_regime``
descriptor (AGENT_MAP_012 §3.3) and passes
:meth:`~reality_mesh.agents.SensorAgent.run_checked`.

TECHNICAL STATES ARE LABELS, NEVER TRADE SIGNALS. Every finding is a structural chart-state
LABEL (per the accepted alpha-chain discipline: technical inflection informs Investment
Diligence timing, it is NOT a trade instruction). No finding field carries buy / sell /
entry / exit / target / stop language -- direction labels only, drawn from the closed
vocabularies in :mod:`reality_mesh.labels`.

SIX SUBAGENTS (represented structurally, AGENT_MAP_012 §3.3) roll into the finding set:

* **Compression** -- narrowing trading range -> ``compression_forming``.
* **Breakout** -- close above the prior range on volume expansion -> ``breakout_confirmed``.
* **EMA Stack** -- the 8>21>50>200-style stack (the accepted ``technical_inflection``
  stacked/not-stacked vocabulary) -> ``ema_stack_aligned`` / ``ema_stack_broken``.
* **VWAP** -- close versus VWAP -> ``vwap_reclaim`` / ``vwap_loss``.
* **Failure/Reversal** -- a push above the prior range that closed back below ->
  ``breakout_failed``.
* **Overextension** -- distance stretched above the key (21-period) EMA -> ``overextension``.

DIRECTION LABELS: ``ema_stack_aligned`` / ``breakout_confirmed`` / ``vwap_reclaim`` ->
``improving``; ``ema_stack_broken`` / ``breakout_failed`` / ``vwap_loss`` /
``overextension`` -> ``deteriorating``; ``compression_forming`` -> ``neutral`` with
ELEVATED urgency (a coiled range resolves soon, in either direction).

HONEST GAPS. A STALE input marks the finding ``freshness_label="stale"`` (never dropped)
and records a data gap; a MISSING indicator becomes an explicit ``data_gaps`` note -- a
subagent reading is NEVER computed from nothing. A ticker whose gaps left no reading at all
yields an explicit ``technical_read_incomplete`` finding carrying those gaps.

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
    "TECHNICAL_REGIME_FINDING_TYPES",
    "TECHNICAL_REGIME_SUBAGENTS",
    "TECHNICAL_SUBAGENT_REQUIRED_KEYS",
    "COMPRESSION_MAX_RANGE_PCT",
    "OVEREXTENSION_MIN_PCT",
    "VOLUME_CONFIRM_MULT",
    "TechnicalRegimeAgent",
]

# --------------------------------------------------------------------------- #
# Identity -- reuse the built-in tattva.technical_regime descriptor.            #
# --------------------------------------------------------------------------- #
_AGENT_ID = "tattva.technical_regime"
_DISCIPLINE = "technical_regime"

# The six discipline-scoped subagents (AGENT_MAP_012 §3.3), verbatim from the registry.
TECHNICAL_REGIME_SUBAGENTS: Tuple[str, ...] = (
    "Compression",
    "Breakout",
    "EMA Stack",
    "VWAP",
    "Failure/Reversal",
    "Overextension",
)

# The finding types this agent may produce -- structural chart-state LABELS, never a trade.
# ``technical_read_incomplete`` is the explicit gap carrier for a ticker whose indicator
# gaps left no subagent reading at all.
TECHNICAL_REGIME_FINDING_TYPES: Tuple[str, ...] = (
    "compression_forming",
    "breakout_confirmed",
    "breakout_failed",
    "ema_stack_aligned",
    "ema_stack_broken",
    "vwap_reclaim",
    "vwap_loss",
    "overextension",
    "technical_read_incomplete",
)

# finding_type -> direction_label (closed DIRECTION_LABELS). Aligned/confirmed/reclaim ->
# improving; broken/failed/loss/overextension -> deteriorating; compression + the gap
# carrier -> neutral. Direction labels ONLY -- never an instruction to act.
_TYPE_DIRECTION: Dict[str, str] = {
    "breakout_confirmed": "improving",
    "ema_stack_aligned": "improving",
    "vwap_reclaim": "improving",
    "breakout_failed": "deteriorating",
    "ema_stack_broken": "deteriorating",
    "vwap_loss": "deteriorating",
    "overextension": "deteriorating",
    "compression_forming": "neutral",
    "technical_read_incomplete": "neutral",
}

# Precomputed indicator keys expected on a price-history event's numeric_values. The agent
# performs simple comparisons on these readings ONLY -- it never derives an indicator itself.
_KEY_CLOSE = "close"
_KEY_EMA8 = "ema8"
_KEY_EMA21 = "ema21"
_KEY_EMA50 = "ema50"
_KEY_EMA200 = "ema200"
_KEY_VWAP = "vwap"
_KEY_RECENT_VOLUME = "recent_volume"
_KEY_AVG_VOLUME = "avg_volume"
_KEY_RANGE_HIGH = "range_high"
_KEY_RECENT_HIGH = "recent_high"
_KEY_RANGE_PCT = "range_pct"
_KEY_PCT_ABOVE_EMA21 = "pct_above_ema21"

# subagent -> the precomputed readings it requires. A missing required reading is an
# explicit gap -- the subagent's verdict is NEVER computed from nothing.
TECHNICAL_SUBAGENT_REQUIRED_KEYS: Dict[str, Tuple[str, ...]] = {
    "Compression": (_KEY_RANGE_PCT,),
    "Breakout": (_KEY_CLOSE, _KEY_RANGE_HIGH, _KEY_RECENT_VOLUME, _KEY_AVG_VOLUME),
    "EMA Stack": (_KEY_EMA8, _KEY_EMA21, _KEY_EMA50, _KEY_EMA200),
    "VWAP": (_KEY_CLOSE, _KEY_VWAP),
    "Failure/Reversal": (_KEY_CLOSE, _KEY_RANGE_HIGH, _KEY_RECENT_HIGH),
    "Overextension": (_KEY_PCT_ABOVE_EMA21,),
}

# Thresholds (simple comparisons on precomputed readings). VOLUME_CONFIRM_MULT reuses the
# accepted prometheus.technical_inflection multiple (recent >= 1.2x average confirms).
VOLUME_CONFIRM_MULT = 1.20
COMPRESSION_MAX_RANGE_PCT = 6.0     # a base range this narrow (percent) is compression
COMPRESSION_TIGHT_RANGE_PCT = 3.0   # tighter coil -> moderate (else minor) magnitude
OVEREXTENSION_MIN_PCT = 25.0        # this far above the key EMA is stretched
VOLUME_STRONG_MULT = 1.50           # this much expansion -> a major breakout reading

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
        return "stale price-history data preserved (not dropped): {0}".format(
            ", ".join(stale_ids))
    return None


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


# --------------------------------------------------------------------------- #
# Internal subagent verdict (pure data, never emitted).                         #
# --------------------------------------------------------------------------- #
class _Reading:
    """One subagent's structural interpretation for one ticker. Never an output object."""

    __slots__ = ("finding_type", "magnitude", "urgency", "summary")

    def __init__(self, finding_type, magnitude, urgency, summary):
        self.finding_type = finding_type
        self.magnitude = magnitude
        self.urgency = urgency
        self.summary = summary


# --------------------------------------------------------------------------- #
# TechnicalRegimeAgent                                                          #
# --------------------------------------------------------------------------- #
class TechnicalRegimeAgent(SensorAgent):
    """Per-ticker Tattva Technical Regime sensor. Emits ``TechnicalRegimeFinding``s.

    Labels only: every finding is a structural chart-state label with a direction label --
    technical inflection informs Investment Diligence timing, it is NOT a trade instruction.
    """

    _AGENT_NAME = "Technical Regime"

    def __init__(self) -> None:
        # Reuse the built-in tattva.technical_regime descriptor (agent_id / discipline /
        # emit contract) rather than hand-rolling one -- single source of identity.
        self._descriptor = next(
            d for d in DEFAULT_DESCRIPTORS if d.agent_id == _AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    # -- run ------------------------------------------------------------- #
    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Interpret per-ticker price-history readings into TechnicalRegimeFindings.

        Deterministic + offline: reads only the injected ``events``, groups them by ticker,
        and runs the six structural subagents per ticker. A missing indicator becomes an
        explicit data gap (never a computed value); stale input marks the finding stale
        (never dropped). Findings are sorted by finding_id.
        """
        mine = tuple(e for e in events if e.discipline == _DISCIPLINE)

        by_ticker: Dict[str, List[RealityEvent]] = {}
        unscoped: List[RealityEvent] = []
        for event in mine:
            if event.affected_companies:
                for ticker in event.affected_companies:
                    by_ticker.setdefault(ticker, []).append(event)
            else:
                unscoped.append(event)

        findings: List[AgentFinding] = []
        for ticker in sorted(by_ticker):
            findings.extend(self._read_ticker(ticker, tuple(by_ticker[ticker])))

        if unscoped:
            gaps = [
                "price-history event {0} carries no ticker (affected_companies empty): "
                "reading not attributable -- gap, never guessed".format(e.event_id)
                for e in sorted(unscoped, key=lambda e: e.event_id)]
            findings.append(self._build_finding(
                ticker="unscoped", events=tuple(unscoped),
                reading=_Reading(
                    "technical_read_incomplete", "minor", "watch",
                    "technical regime read incomplete: {0} unattributable price-history "
                    "event(s)".format(len(unscoped))),
                gaps=gaps))

        return tuple(sorted(findings, key=lambda f: f.finding_id))

    # -- per-ticker read --------------------------------------------------- #
    def _read_ticker(self, ticker: str,
                     events: Tuple[RealityEvent, ...]) -> List[AgentFinding]:
        readings = _readings_of(events)

        # Missing-indicator gaps FIRST: a subagent with an absent required reading is an
        # explicit gap -- its verdict is never computed from nothing.
        gaps: List[str] = []
        available: List[str] = []
        for subagent in TECHNICAL_REGIME_SUBAGENTS:
            required = TECHNICAL_SUBAGENT_REQUIRED_KEYS[subagent]
            missing = sorted(k for k in required if k not in readings)
            if missing:
                gaps.append(
                    "missing indicator(s) {0} for {1}: {2} subagent has no reading -- gap, "
                    "never computed from nothing".format(
                        ", ".join(missing), ticker, subagent))
            else:
                available.append(subagent)

        verdicts: List[_Reading] = []
        if "Compression" in available:
            verdicts.extend(self._read_compression(ticker, readings))
        if "Breakout" in available:
            verdicts.extend(self._read_breakout(ticker, readings))
        if "EMA Stack" in available:
            verdicts.extend(self._read_ema_stack(ticker, readings))
        if "VWAP" in available:
            verdicts.extend(self._read_vwap(ticker, readings))
        if "Failure/Reversal" in available:
            verdicts.extend(self._read_failure(ticker, readings))
        if "Overextension" in available:
            verdicts.extend(self._read_overextension(ticker, readings))

        if not verdicts:
            # Nothing readable for this ticker: the gaps are surfaced on an explicit
            # incomplete-read finding, never silently swallowed.
            incomplete = _Reading(
                "technical_read_incomplete", "minor", "watch",
                "technical regime read incomplete for {0}: {1} gap(s), no subagent "
                "reading".format(ticker, len(gaps)))
            return [self._build_finding(ticker=ticker, events=events,
                                        reading=incomplete, gaps=gaps)]

        return [self._build_finding(ticker=ticker, events=events, reading=v, gaps=gaps)
                for v in verdicts]

    # -- subagent readers (simple comparisons on precomputed readings) ------ #
    def _read_compression(self, ticker, r) -> List[_Reading]:
        v = r[_KEY_RANGE_PCT]
        if v > COMPRESSION_MAX_RANGE_PCT:
            return []
        mag = "moderate" if v <= COMPRESSION_TIGHT_RANGE_PCT else "minor"
        return [_Reading(
            "compression_forming", mag, "elevated",
            "compression forming for {0}: trading range narrowed to {1}% of the base "
            "(a coiled range resolves soon, in either direction)".format(ticker, v))]

    def _read_breakout(self, ticker, r) -> List[_Reading]:
        volume_expanded = r[_KEY_RECENT_VOLUME] >= VOLUME_CONFIRM_MULT * r[_KEY_AVG_VOLUME]
        if not (r[_KEY_CLOSE] > r[_KEY_RANGE_HIGH] and volume_expanded):
            return []
        mag = ("major" if r[_KEY_RECENT_VOLUME] >= VOLUME_STRONG_MULT * r[_KEY_AVG_VOLUME]
               else "moderate")
        return [_Reading(
            "breakout_confirmed", mag, "elevated",
            "breakout confirmed for {0}: close above the prior range high on expanding "
            "volume (structural state label, not an instruction to act)".format(ticker))]

    def _read_ema_stack(self, ticker, r) -> List[_Reading]:
        if r[_KEY_EMA8] > r[_KEY_EMA21] > r[_KEY_EMA50] > r[_KEY_EMA200]:
            return [_Reading(
                "ema_stack_aligned", "moderate", "watch",
                "EMA stack aligned for {0}: the 8>21>50>200 structure is intact".format(
                    ticker))]
        fully_inverted = r[_KEY_EMA8] < r[_KEY_EMA21] < r[_KEY_EMA50] < r[_KEY_EMA200]
        mag = "major" if fully_inverted else "moderate"
        return [_Reading(
            "ema_stack_broken", mag, "elevated",
            "EMA stack broken for {0}: the 8>21>50>200 structure is not intact".format(
                ticker))]

    def _read_vwap(self, ticker, r) -> List[_Reading]:
        if r[_KEY_CLOSE] >= r[_KEY_VWAP]:
            return [_Reading(
                "vwap_reclaim", "minor", "watch",
                "VWAP reclaim for {0}: close is holding above the volume-weighted average "
                "price".format(ticker))]
        return [_Reading(
            "vwap_loss", "minor", "watch",
            "VWAP loss for {0}: close is below the volume-weighted average price".format(
                ticker))]

    def _read_failure(self, ticker, r) -> List[_Reading]:
        if not (r[_KEY_RECENT_HIGH] > r[_KEY_RANGE_HIGH]
                and r[_KEY_CLOSE] <= r[_KEY_RANGE_HIGH]):
            return []
        return [_Reading(
            "breakout_failed", "moderate", "elevated",
            "breakout failed for {0}: price pushed above the prior range high but closed "
            "back below it (reversal risk label)".format(ticker))]

    def _read_overextension(self, ticker, r) -> List[_Reading]:
        v = r[_KEY_PCT_ABOVE_EMA21]
        if v < OVEREXTENSION_MIN_PCT:
            return []
        mag = "extreme" if v >= 50 else ("major" if v >= 35 else "moderate")
        return [_Reading(
            "overextension", mag, "elevated",
            "overextension for {0}: price is {1}% above the 21-period EMA -- distance "
            "stretched versus its trend".format(ticker, v))]

    # -- finding builder ---------------------------------------------------- #
    def _build_finding(self, *, ticker: str, events: Tuple[RealityEvent, ...],
                       reading: _Reading, gaps: List[str]) -> AgentFinding:
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
        companies = tuple(sorted({c for e in evs for c in e.affected_companies}))
        themes = tuple(sorted({t for e in evs for t in e.affected_themes}))
        return AgentFinding(
            finding_id="finding.technical_regime.{0}.{1}".format(
                reading.finding_type, _slug(ticker)),
            agent_id=_AGENT_ID,
            agent_layer="reality_intelligence",
            agent_name=self._AGENT_NAME,
            discipline=_DISCIPLINE,
            input_events=tuple(e.event_id for e in evs),
            finding_type=reading.finding_type,
            finding_summary=reading.summary,
            affected_companies=companies,
            affected_themes=themes,
            direction_label=_TYPE_DIRECTION[reading.finding_type],
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
