"""The Timing / Technical Setup Gate -- TechnicalTimingSetup (IMPLEMENTATION-022C).

A stock-pick report must include TIMING. This module provides the typed
:class:`TechnicalTimingSetup` and the :func:`technical_timing_acceptable` verdict that the
022B recommendation gate 11 (``technical_timing_acceptable``) consumes. It sits ABOVE the 014D
technical-regime sensor evidence (trend / EMA-stack / compression / breakout / volume /
relative-strength) and turns it into a categorical TIMING setup for MANUAL REVIEW -- never a
trade, never a price target, never a number.

Non-negotiable discipline baked into the shape:

* **Labels only -- NO score / rank / rating / numeric-target field.** The setup is categorical
  states + zone LABELS + plain reasons. Support / resistance / entry are qualitative zone
  LABELS or ranges, NEVER a precise price prediction dressed as certainty. ``risk_reward_label``
  is a LABEL (favorable / balanced / poor), never a number. No buy / sell / order / submit.

* **The system must NOT recommend chasing an extended move without an explicit risk warning.**
  ``extended_chase_risk`` can NEVER be an actionable setup -- it forces an explicit risk
  warning and :func:`technical_timing_acceptable` refuses it. ``breakdown_exit_review`` routes
  to exit review, never actionable.

* **Actionable REQUIRES freshness.** A stale / missing-freshness setup is never acceptable.

* **A FIXTURE-only setup can NEVER be production-actionable.** ``source_mode == "fixture"`` is
  fine for shadow / demo, but :func:`technical_timing_acceptable(..., production=True)` rejects
  it.

* **No fabrication.** Absent price / technical input -> a visible ``data_gaps`` note +
  ``not_ready`` state, NEVER an invented level or zone. A would-be actionable setup missing its
  support / entry / invalidation zones is DOWNGRADED with an explicit gap -- levels are never
  guessed.

Deterministic (injected ``now``, no wall-clock), stdlib-only, Python 3.9, OFFLINE. No network /
scheduler / broker on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Mapping, Optional, Tuple

from . import labels as _labels
from .validation import assert_no_trade_fields

__all__ = [
    "TECHNICAL_SETUP_STATES",
    "TECHNICAL_SETUP_STATE_LABELS",
    "RISK_REWARD_LABELS",
    "SOURCE_MODES",
    "FRESH_TIMING_LABELS",
    "TechnicalTimingSetup",
    "assess_technical_timing",
    "technical_timing_acceptable",
    "technical_timing_id_for",
]


# --------------------------------------------------------------------------- #
# Closed vocabularies                                                           #
# --------------------------------------------------------------------------- #

# The CLOSED set of timing-setup states. ``extended_chase_risk`` and ``breakdown_exit_review``
# are RISK states that can never be actionable; ``actionable_setup_manual_review`` is the only
# "surface it to a human as timed" state and still requires freshness + non-fixture-in-production
# to be ACCEPTABLE (see :func:`technical_timing_acceptable`).
TECHNICAL_SETUP_STATES: Tuple[str, ...] = (
    "not_ready",
    "watch_for_setup",
    "setup_forming",
    "actionable_setup_manual_review",
    "extended_chase_risk",
    "breakdown_exit_review",
)

# Display labels (informational; NOT a stored field). Qualitative, never a score.
TECHNICAL_SETUP_STATE_LABELS = {
    "not_ready": "Not Ready",
    "watch_for_setup": "Watch for Setup",
    "setup_forming": "Setup Forming",
    "actionable_setup_manual_review": "Actionable Setup — Manual Review",  # em-dash U+2014
    "extended_chase_risk": "Extended — Chase Risk",
    "breakdown_exit_review": "Breakdown — Exit Review",
}

# The risk/reward is a LABEL, never a number. "" = unset / not assessed.
RISK_REWARD_LABELS: Tuple[str, ...] = ("favorable", "balanced", "poor", "unknown")

# Where the technical evidence came from. ``fixture`` is fine for shadow/demo but never
# production-actionable. "" = unset.
SOURCE_MODES: Tuple[str, ...] = ("source-backed", "local-file", "fixture")

# The freshness labels under which a setup may be actionable (reuses the 012A freshness vocab).
FRESH_TIMING_LABELS: Tuple[str, ...] = ("fresh", "recent")


def _clean(value: Any) -> str:
    return str(value or "").strip()


# --------------------------------------------------------------------------- #
# The typed contract                                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TechnicalTimingSetup:
    """A frozen, label-only TIMING setup for MANUAL REVIEW derived from 014D technical evidence.

    Categorical states + zone LABELS + plain reasons ONLY. There is NO score / rank / rating /
    numeric price-target field; ``risk_reward_label`` is a LABEL, and support / resistance /
    entry zones are qualitative LABELS or ranges, never a precise price prediction. Absent input
    yields ``not_ready`` + a visible ``data_gaps`` note -- levels are NEVER fabricated.
    """

    ticker: str = ""                            # REQUIRED
    run_id: str = ""                            # REQUIRED -- the producing run
    generated_at: str = ""                      # REQUIRED -- injected timestamp (no wall-clock)

    # -- the six 014D technical-regime state readings (LABELS, never numbers) -- #
    trend_state: str = ""
    compression_state: str = ""
    breakout_state: str = ""
    volume_state: str = ""
    relative_strength_state: str = ""

    # -- zone LABELS / ranges (never invented; absent -> "" + a data gap) -- #
    support_zone: str = ""
    resistance_zone: str = ""
    entry_zone_label: str = ""
    invalidation_level_or_condition: str = ""
    risk_reward_label: str = ""                 # closed: RISK_REWARD_LABELS ("" = unset)

    # -- the verdict -- #
    setup_state: str = ""                       # REQUIRED, closed: TECHNICAL_SETUP_STATES
    setup_reason: str = ""                       # REQUIRED, plain-English

    data_freshness: str = ""                    # closed: FRESHNESS_LABELS ("" = missing)
    source_mode: str = ""                       # closed: SOURCE_MODES ("" = unset)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("ticker", "run_id", "generated_at", "setup_state", "setup_reason"):
            if not _clean(getattr(self, name, "")):
                raise ValueError(
                    "TechnicalTimingSetup.{0} is required and must be non-empty".format(name))
        if self.setup_state not in TECHNICAL_SETUP_STATES:
            raise ValueError(
                "TechnicalTimingSetup.setup_state {0!r} invalid (allowed: {1})".format(
                    self.setup_state, list(TECHNICAL_SETUP_STATES)))
        if self.risk_reward_label and self.risk_reward_label not in RISK_REWARD_LABELS:
            raise ValueError(
                "TechnicalTimingSetup.risk_reward_label {0!r} invalid (allowed: {1})".format(
                    self.risk_reward_label, list(RISK_REWARD_LABELS)))
        if self.source_mode and self.source_mode not in SOURCE_MODES:
            raise ValueError(
                "TechnicalTimingSetup.source_mode {0!r} invalid (allowed: {1})".format(
                    self.source_mode, list(SOURCE_MODES)))
        if self.data_freshness and not _labels.is_member(_labels.FRESHNESS_LABELS,
                                                         self.data_freshness):
            raise ValueError(
                "TechnicalTimingSetup.data_freshness {0!r} invalid (allowed: {1})".format(
                    self.data_freshness, sorted(_labels.FRESHNESS_LABELS)))

    # -- introspection (properties, never stored fields) -------------------- #
    @property
    def setup_state_label(self) -> str:
        return TECHNICAL_SETUP_STATE_LABELS.get(self.setup_state, "")

    @property
    def is_actionable_setup(self) -> bool:
        return self.setup_state == "actionable_setup_manual_review"

    @property
    def requires_risk_warning(self) -> bool:
        """True for an extended move -- chasing it is never actionable without a risk warning."""
        return self.setup_state == "extended_chase_risk"

    @property
    def routes_to_exit_review(self) -> bool:
        return self.setup_state == "breakdown_exit_review"

    @property
    def is_fresh(self) -> bool:
        return self.data_freshness in FRESH_TIMING_LABELS

    @property
    def is_fixture_sourced(self) -> bool:
        return self.source_mode == "fixture"


# The timing contract (for registry / test introspection). Trade/score-clean.
TECHNICAL_TIMING_MODELS = (TechnicalTimingSetup,)


# --------------------------------------------------------------------------- #
# Deterministic id                                                              #
# --------------------------------------------------------------------------- #
def technical_timing_id_for(run_id: str, ticker: str) -> str:
    """A deterministic setup ref from the run + ticker (no wall-clock, order-stable)."""
    return "tts:{0}:{1}".format(_clean(run_id), _clean(ticker).upper())


# --------------------------------------------------------------------------- #
# Evidence normalization -- accept a mapping OR a sequence of 014D findings      #
# --------------------------------------------------------------------------- #
_ZONE_KEYS = (
    "support_zone", "resistance_zone", "entry_zone_label",
    "invalidation_level_or_condition", "risk_reward_label",
)
_STATE_KEYS = (
    "trend_state", "compression_state", "breakout_state",
    "volume_state", "relative_strength_state",
)

# 014D finding_type -> the normalized state field + value it implies.
_FINDING_TO_STATE = {
    "ema_stack_aligned": ("trend_state", "ema_stack_aligned"),
    "ema_stack_broken": ("trend_state", "ema_stack_broken"),
    "compression_forming": ("compression_state", "compression_forming"),
    "breakout_confirmed": ("breakout_state", "breakout_confirmed"),
    "breakout_failed": ("breakout_state", "breakout_failed"),
    "vwap_reclaim": ("relative_strength_state", "vwap_reclaim"),
    "vwap_loss": ("relative_strength_state", "vwap_loss"),
}

_FRESHNESS_ORDER = ("expired", "stale", "aging", "recent", "fresh")


class _Evidence:
    """Normalized technical evidence (internal, never emitted)."""

    __slots__ = _STATE_KEYS + _ZONE_KEYS + (
        "overextended", "breakdown", "data_freshness", "gaps")

    def __init__(self) -> None:
        for name in _STATE_KEYS + _ZONE_KEYS:
            setattr(self, name, "")
        self.overextended = False
        self.breakdown = False
        self.data_freshness = ""
        self.gaps: Tuple[str, ...] = ()


def _coerce_evidence(evidence: Any) -> Optional[_Evidence]:
    """Normalize ``evidence`` into an :class:`_Evidence` (or ``None`` if genuinely absent)."""
    if evidence is None:
        return None
    ev = _Evidence()

    if isinstance(evidence, Mapping):
        for name in _STATE_KEYS + _ZONE_KEYS:
            if name in evidence:
                setattr(ev, name, _clean(evidence.get(name)))
        ev.overextended = bool(evidence.get("overextended", False))
        ev.breakdown = bool(evidence.get("breakdown", False))
        ev.data_freshness = _clean(evidence.get("data_freshness"))
        ev.gaps = tuple(_clean(g) for g in (evidence.get("data_gaps") or ()) if _clean(g))
        return ev

    # A sequence of 014D AgentFindings (technical_regime discipline): derive the states from the
    # finding_types. Zones are NOT present on a finding -> they stay absent (a gap, never guessed).
    seq = tuple(evidence)
    if not seq:
        return None
    gaps = []
    freshnesses = []
    for finding in seq:
        ftype = _clean(getattr(finding, "finding_type", ""))
        if ftype == "overextension":
            ev.overextended = True
        elif ftype in ("ema_stack_broken", "breakout_failed"):
            ev.breakdown = True
        mapped = _FINDING_TO_STATE.get(ftype)
        if mapped:
            field_name, value = mapped
            if not getattr(ev, field_name):
                setattr(ev, field_name, value)
        for g in getattr(finding, "data_gaps", ()) or ():
            if _clean(g):
                gaps.append(_clean(g))
        fresh = _clean(getattr(finding, "freshness_label", ""))
        if fresh in _FRESHNESS_ORDER:
            freshnesses.append(fresh)
    if freshnesses:
        ev.data_freshness = min(freshnesses, key=_FRESHNESS_ORDER.index)
    ev.gaps = tuple(dict.fromkeys(gaps))
    return ev


# --------------------------------------------------------------------------- #
# The assessor                                                                  #
# --------------------------------------------------------------------------- #
def _zones_present(ev: _Evidence) -> bool:
    """A tradeable setup needs an explicit support, entry, and invalidation -- never invented."""
    return bool(_clean(ev.support_zone) and _clean(ev.entry_zone_label)
                and _clean(ev.invalidation_level_or_condition))


def _build(ticker: str, run_id: str, now: str, *, setup_state: str, setup_reason: str,
           ev: Optional[_Evidence], data_freshness: str, source_mode: str,
           risk_reward: str, extra_gaps: Tuple[str, ...] = ()) -> TechnicalTimingSetup:
    gaps = tuple(dict.fromkeys((tuple(ev.gaps) if ev else ()) + tuple(extra_gaps)))
    return TechnicalTimingSetup(
        ticker=_clean(ticker).upper(), run_id=_clean(run_id), generated_at=str(now),
        trend_state=ev.trend_state if ev else "",
        compression_state=ev.compression_state if ev else "",
        breakout_state=ev.breakout_state if ev else "",
        volume_state=ev.volume_state if ev else "",
        relative_strength_state=ev.relative_strength_state if ev else "",
        support_zone=ev.support_zone if ev else "",
        resistance_zone=ev.resistance_zone if ev else "",
        entry_zone_label=ev.entry_zone_label if ev else "",
        invalidation_level_or_condition=ev.invalidation_level_or_condition if ev else "",
        risk_reward_label=risk_reward,
        setup_state=setup_state, setup_reason=setup_reason,
        data_freshness=data_freshness, source_mode=source_mode, data_gaps=gaps)


def assess_technical_timing(
    ticker: str,
    *,
    run_id: str,
    now: str,
    technical_evidence: Any = None,
    data_freshness: str = "",
    source_mode: str = "",
) -> TechnicalTimingSetup:
    """Derive a :class:`TechnicalTimingSetup` from 014D technical-regime evidence.

    Derivation (deterministic; never fabricates a level):

    * **Absent evidence** -> ``not_ready`` + a visible ``data_gaps`` note (no invented zones).
    * **A breakdown** (broken EMA stack / failed breakout / explicit breakdown) ->
      ``breakdown_exit_review`` -- routes to EXIT REVIEW, never an actionable entry.
    * **An over-extended move** -> ``extended_chase_risk`` -- carries an explicit risk warning;
      chasing it is never an actionable setup.
    * **A clean, constructive structure WITH explicit support / entry / invalidation zones** ->
      ``actionable_setup_manual_review``. If those zones are absent it is DOWNGRADED (never
      fabricated) to ``setup_forming`` / ``watch_for_setup`` with an explicit gap.
    * else ``setup_forming`` / ``watch_for_setup`` / ``not_ready`` per how constructive it is.

    ``now`` is injected. ``data_freshness`` / ``source_mode`` are passthrough labels; a missing
    ``data_freshness`` falls back to the evidence's own freshness. FRESHNESS gating for
    ACTIONABILITY is applied by :func:`technical_timing_acceptable`, not here.
    """
    if not _clean(ticker):
        raise ValueError("assess_technical_timing requires a non-empty ticker")
    if not _clean(run_id):
        raise ValueError("assess_technical_timing requires a non-empty run_id")

    ev = _coerce_evidence(technical_evidence)
    mode = _clean(source_mode)
    freshness = _clean(data_freshness) or (ev.data_freshness if ev else "")

    # 1. Absent evidence -> not_ready + a visible gap. NEVER an invented level.
    if ev is None:
        gap = ("no price / technical evidence supplied for {0}: timing cannot be assessed -- "
               "explicit gap, no level invented".format(_clean(ticker).upper()))
        return _build(ticker, run_id, now, setup_state="not_ready",
                      setup_reason="technical timing NOT READY: {0}".format(gap),
                      ev=None, data_freshness=freshness, source_mode=mode,
                      risk_reward="unknown", extra_gaps=(gap,))

    trend_up = ev.trend_state in ("ema_stack_aligned", "uptrend")
    breakout_ok = ev.breakout_state == "breakout_confirmed"
    compressing = ev.compression_state == "compression_forming"
    vol_expanding = ev.volume_state in ("expanding", "volume_expanding")
    rs_lagging = ev.relative_strength_state in ("lagging", "vwap_loss")

    # 2. A breakdown routes to EXIT REVIEW, never actionable (dominates chase risk).
    if ev.breakdown:
        return _build(ticker, run_id, now, setup_state="breakdown_exit_review",
                      setup_reason=(
                          "technical structure BROKEN DOWN for {0}: EMA stack broken / breakout "
                          "failed -- this routes to EXIT REVIEW, never an actionable entry".format(
                              _clean(ticker).upper())),
                      ev=ev, data_freshness=freshness, source_mode=mode, risk_reward="poor")

    # 3. An over-extended move is a CHASE RISK, never actionable without a risk warning.
    if ev.overextended:
        return _build(ticker, run_id, now, setup_state="extended_chase_risk",
                      setup_reason=(
                          "price EXTENDED above trend for {0}: this is a CHASE RISK, not an entry "
                          "-- chasing an extended move requires an explicit risk warning and is "
                          "NEVER an actionable setup".format(_clean(ticker).upper())),
                      ev=ev, data_freshness=freshness, source_mode=mode, risk_reward="poor")

    strong = trend_up and breakout_ok and vol_expanding and not rs_lagging
    constructive = trend_up and (breakout_ok or compressing)

    # 4. A clean, constructive, non-extended structure WITH explicit zones -> actionable.
    if strong and _zones_present(ev):
        return _build(ticker, run_id, now, setup_state="actionable_setup_manual_review",
                      setup_reason=(
                          "clean constructive setup for {0}: aligned trend + confirmed breakout on "
                          "expanding volume, with explicit support / entry / invalidation zones -- "
                          "actionable for MANUAL REVIEW (not extended, not broken down)".format(
                              _clean(ticker).upper())),
                      ev=ev, data_freshness=freshness, source_mode=mode, risk_reward="favorable")

    if strong and not _zones_present(ev):
        gap = ("actionable-quality structure for {0} but support / entry / invalidation zone is "
               "absent: DOWNGRADED to setup_forming -- levels are never fabricated".format(
                   _clean(ticker).upper()))
        return _build(ticker, run_id, now, setup_state="setup_forming",
                      setup_reason="constructive but zone-incomplete: {0}".format(gap),
                      ev=ev, data_freshness=freshness, source_mode=mode,
                      risk_reward="balanced", extra_gaps=(gap,))

    # 5. Constructive-but-not-yet-triggered / early -> forming or watch.
    if constructive:
        return _build(ticker, run_id, now, setup_state="setup_forming",
                      setup_reason=(
                          "setup FORMING for {0}: constructive trend with compression / early "
                          "breakout, not yet a clean triggered entry".format(
                              _clean(ticker).upper())),
                      ev=ev, data_freshness=freshness, source_mode=mode, risk_reward="balanced")

    if trend_up or compressing:
        return _build(ticker, run_id, now, setup_state="watch_for_setup",
                      setup_reason=(
                          "WATCH for a setup on {0}: some constructive structure but no trigger "
                          "yet -- monitor, do not act".format(_clean(ticker).upper())),
                      ev=ev, data_freshness=freshness, source_mode=mode, risk_reward="unknown")

    gap = ("no readable constructive structure for {0}: {1} -- NOT READY, no level invented".format(
        _clean(ticker).upper(),
        "no aligned trend / breakout / compression among the supplied readings"))
    return _build(ticker, run_id, now, setup_state="not_ready",
                  setup_reason="technical timing NOT READY: {0}".format(gap),
                  ev=ev, data_freshness=freshness, source_mode=mode,
                  risk_reward="unknown", extra_gaps=(gap,))


# --------------------------------------------------------------------------- #
# The verdict 022B gate 11 consumes                                             #
# --------------------------------------------------------------------------- #
def technical_timing_acceptable(
    setup: Optional[TechnicalTimingSetup], *, production: bool = False,
) -> Tuple[bool, str]:
    """Whether a timing setup is ACCEPTABLE for gate 11 -- ``(ok, reason)``.

    ``True`` ONLY when the setup_state is ``actionable_setup_manual_review`` AND the data is
    fresh / recent AND (not ``production`` OR the source is not a fixture). Every other case is
    ``False`` with the EXACT reason:

    * no setup -> False;
    * ``extended_chase_risk`` -> False (chasing an extended move is never actionable);
    * ``breakdown_exit_review`` -> False (routes to exit review);
    * a stale / missing-freshness setup -> False (a setup requires freshness);
    * a fixture-sourced setup under ``production=True`` -> False (fixture is shadow/demo only).
    """
    if setup is None:
        return False, ("no TechnicalTimingSetup supplied -- a recommendation cannot be actionable "
                       "without an assessed timing setup")
    if not isinstance(setup, TechnicalTimingSetup):
        return False, "supplied timing object is not a TechnicalTimingSetup"

    state = setup.setup_state
    if state != "actionable_setup_manual_review":
        if state == "extended_chase_risk":
            return False, ("extended_chase_risk: chasing an extended move is NEVER an actionable "
                           "setup without an explicit risk warning")
        if state == "breakdown_exit_review":
            return False, ("breakdown_exit_review: a technical breakdown routes to EXIT REVIEW, "
                           "never an actionable entry")
        return False, ("setup_state {0!r} is not actionable_setup_manual_review -- timing is not "
                       "actionable".format(state))

    if not setup.is_fresh:
        return False, ("technical timing is {0!r} (not fresh/recent) -- a setup REQUIRES fresh "
                       "data to be actionable".format(setup.data_freshness or "missing"))

    if production and setup.is_fixture_sourced:
        return False, ("fixture-sourced setup cannot be PRODUCTION-actionable -- a fixture setup "
                       "is fine for shadow / demo only, never a production pick")

    return True, ("actionable technical setup on fresh {0} data".format(
        setup.source_mode or "source-backed"))


# --------------------------------------------------------------------------- #
# Construction-time guard: the setup may carry NO trade / score field.           #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(TechnicalTimingSetup)

# Belt-and-braces: no stored field name may carry a numeric-verdict token.
for _f in fields(TechnicalTimingSetup):
    _low = _f.name.lower()
    for _tok in ("score", "rank", "rating", "target", "price_pred"):
        assert _tok not in _low, "forbidden numeric-verdict field {0!r}".format(_f.name)
