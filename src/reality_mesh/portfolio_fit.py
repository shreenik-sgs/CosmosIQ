"""The Portfolio Fit / Sizing Guardrail Gate -- PortfolioFit (IMPLEMENTATION-022D).

A stock-pick report must include PORTFOLIO FIT + SIZING. This module provides the typed
:class:`PortfolioFit` and the :func:`portfolio_fit_acceptable` verdict that the 022B recommendation
gate 12 (``portfolio_fit_acceptable``) consumes. It sits ABOVE the 018A read-only Portfolio
Intelligence (:mod:`reality_mesh.portfolio`) and turns "what am I already exposed to, how
concentrated / correlated / liquid is it" into a categorical PORTFOLIO-FIT state plus a qualitative
SIZING GUARDRAIL for MANUAL REVIEW -- never a share count, never a dollar amount, never an order.

Non-negotiable discipline baked into the shape:

* **Labels / ranges only -- NO numeric position size, NO order / execution control, NO score /
  rank.** The sizing guardrail is a LABEL from a closed vocabulary
  (``starter position only`` / ``small position`` / ``normal risk budget`` /
  ``reduced due to volatility`` / ``avoid due to concentration`` / ``watch only``), NEVER a share
  count or a dollar figure dressed as an instruction. No buy / sell / order / submit / rebalance.

* **Concentration / liquidity / correlation risk REDUCES or BLOCKS -- never silently ignored.**
  Concentration above the 018 thresholds -> ``concentration_risk`` (or
  ``avoid_due_to_portfolio_risk`` when ``dominant``) and the sizing is reduced / avoid. Elevated
  correlation or rotation-misalignment -> ``correlation_risk``; a thin liquidity signal ->
  ``liquidity_risk``. Each of these makes :func:`portfolio_fit_acceptable` refuse the pick.

* **Insufficient portfolio data prevents production-grade sizing.** With NO holdings recorded the
  state is ``insufficient_portfolio_data`` + a visible gap + sizing ``watch only`` -- an honest
  absence, never invented exposure. :func:`portfolio_fit_acceptable(..., production=True)` refuses
  it: an actionable production pick can NOT be built on ``insufficient_portfolio_data``.

* **No fabrication.** Absent portfolio data -> ``insufficient_portfolio_data`` + a gap, never an
  invented band or exposure. The concentration / theme / correlation bands are REUSED verbatim
  from the 018 engine (``minimal`` / ``moderate`` / ``elevated`` / ``dominant``) -- this module
  never recomputes a weight or a ratio.

* **A FIXTURE-only fit can NEVER be production-actionable.** ``source_mode == "fixture"`` is fine
  for shadow / demo but :func:`portfolio_fit_acceptable(..., production=True)` rejects it.

Deterministic (injected ``now``, no wall-clock), stdlib-only, Python 3.9, OFFLINE. No network /
scheduler / broker on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Optional, Tuple

from .portfolio import (
    BAND_UNKNOWN,
    CONCENTRATION_BANDS,
    ConcentrationView,
    PairCorrelationView,
    PortfolioHoldings,
    RotationAlignmentView,
    build_concentration,
    build_correlation_labels,
    build_rotation_alignment,
    compare_candidate,
    load_holdings,
)
from .technical_timing import SOURCE_MODES
from .validation import assert_no_trade_fields

__all__ = [
    "PORTFOLIO_FIT_STATES",
    "PORTFOLIO_FIT_STATE_LABELS",
    "SIZING_GUARDRAIL_LABELS",
    "RISK_BANDS",
    "DATA_AVAILABILITY_STATES",
    "SOURCE_MODES",
    "PortfolioFit",
    "assess_portfolio_fit",
    "portfolio_fit_acceptable",
    "portfolio_fit_id_for",
]


# --------------------------------------------------------------------------- #
# Closed vocabularies                                                           #
# --------------------------------------------------------------------------- #

# The CLOSED set of portfolio-fit states. ``acceptable`` is the ONLY state that gate 12 may pass;
# every risk state reduces / blocks; ``insufficient_portfolio_data`` is the honest no-holdings
# state that can NEVER be a production pick.
PORTFOLIO_FIT_STATES: Tuple[str, ...] = (
    "acceptable",
    "concentration_risk",
    "liquidity_risk",
    "correlation_risk",
    "insufficient_portfolio_data",
    "avoid_due_to_portfolio_risk",
)

# Display labels (informational; NOT a stored field). Qualitative, never a score.
PORTFOLIO_FIT_STATE_LABELS = {
    "acceptable": "Acceptable Portfolio Fit",
    "concentration_risk": "Concentration Risk",
    "liquidity_risk": "Liquidity Risk",
    "correlation_risk": "Correlation Risk",
    "insufficient_portfolio_data": "Insufficient Portfolio Data",
    "avoid_due_to_portfolio_risk": "Avoid — Portfolio Risk",  # em-dash U+2014
}

# The CLOSED sizing-guardrail vocabulary. Every value is a LABEL / qualitative range -- never a
# share count, never a dollar amount, never an order instruction.
SIZING_GUARDRAIL_LABELS: Tuple[str, ...] = (
    "starter position only",
    "small position",
    "normal risk budget",
    "reduced due to volatility",
    "avoid due to concentration",
    "watch only",
)

# The risk-BAND vocabulary: REUSED verbatim from the 018 engine (never recomputed here). ``unknown``
# is the honest band when the underlying weight cannot be measured.
RISK_BANDS: Tuple[str, ...] = tuple(CONCENTRATION_BANDS) + (BAND_UNKNOWN,)
_BAND_ORDER = {band: index for index, band in enumerate(CONCENTRATION_BANDS)}

# Whether the operator's portfolio data is present enough to size against, or honestly insufficient.
DATA_AVAILABILITY_STATES: Tuple[str, ...] = ("present", "insufficient")

# The sizing labels that mean "reduced or avoid" -- a risk state must land on one of these.
_REDUCE_OR_AVOID = ("reduced due to volatility", "avoid due to concentration")

# Liquidity signal tokens that read as THIN (a liquidity risk) or ADEQUATE.
_THIN_LIQUIDITY = ("thin", "illiquid", "low", "poor", "shallow")
_ADEQUATE_LIQUIDITY = ("adequate", "deep", "ample", "ok", "liquid", "high")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _worse_band(a: str, b: str) -> str:
    """The stronger (worse) of two concentration bands; ``unknown`` never overrides a real band."""
    if a not in _BAND_ORDER:
        return b if b in _BAND_ORDER else BAND_UNKNOWN
    if b not in _BAND_ORDER:
        return a
    return a if _BAND_ORDER[a] >= _BAND_ORDER[b] else b


# --------------------------------------------------------------------------- #
# The typed contract                                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PortfolioFit:
    """A frozen, label-only PORTFOLIO-FIT + SIZING GUARDRAIL for MANUAL REVIEW.

    Categorical fit state + reused 018 risk BANDS + a qualitative SIZING LABEL + plain reasons
    ONLY. There is NO numeric position size, NO score / rank, and NO order / execution field.
    Absent portfolio data yields ``insufficient_portfolio_data`` + a visible ``data_gaps`` note --
    exposure is NEVER fabricated.
    """

    ticker: str = ""                            # REQUIRED
    run_id: str = ""                            # REQUIRED -- the producing run
    generated_at: str = ""                      # REQUIRED -- injected timestamp (no wall-clock)

    # -- the verdict -- #
    fit_state: str = ""                         # REQUIRED, closed: PORTFOLIO_FIT_STATES
    fit_reason: str = ""                        # REQUIRED, plain-English

    # -- reused 018 risk BANDS (never recomputed; "" only when genuinely unset) -- #
    risk_budget_label: str = ""                 # the overall risk band consumed
    concentration_risk_label: str = ""          # 018 position / theme band
    liquidity_risk_label: str = ""              # thin -> elevated band
    correlation_risk_label: str = ""            # co-exposure / rotation band

    # -- the sizing guardrail (a LABEL, never a number) -- #
    sizing_guardrail_label: str = ""            # REQUIRED, closed: SIZING_GUARDRAIL_LABELS

    data_availability: str = ""                 # REQUIRED, closed: DATA_AVAILABILITY_STATES
    source_mode: str = ""                       # closed: SOURCE_MODES ("" = unset)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("ticker", "run_id", "generated_at", "fit_state", "fit_reason",
                     "sizing_guardrail_label", "data_availability"):
            if not _clean(getattr(self, name, "")):
                raise ValueError(
                    "PortfolioFit.{0} is required and must be non-empty".format(name))
        if self.fit_state not in PORTFOLIO_FIT_STATES:
            raise ValueError(
                "PortfolioFit.fit_state {0!r} invalid (allowed: {1})".format(
                    self.fit_state, list(PORTFOLIO_FIT_STATES)))
        if self.sizing_guardrail_label not in SIZING_GUARDRAIL_LABELS:
            raise ValueError(
                "PortfolioFit.sizing_guardrail_label {0!r} invalid (allowed: {1})".format(
                    self.sizing_guardrail_label, list(SIZING_GUARDRAIL_LABELS)))
        if self.data_availability not in DATA_AVAILABILITY_STATES:
            raise ValueError(
                "PortfolioFit.data_availability {0!r} invalid (allowed: {1})".format(
                    self.data_availability, list(DATA_AVAILABILITY_STATES)))
        for name in ("risk_budget_label", "concentration_risk_label",
                     "liquidity_risk_label", "correlation_risk_label"):
            value = getattr(self, name)
            if value and value not in RISK_BANDS:
                raise ValueError(
                    "PortfolioFit.{0} {1!r} is not a reused 018 band (allowed: {2})".format(
                        name, value, list(RISK_BANDS)))
        if self.source_mode and self.source_mode not in SOURCE_MODES:
            raise ValueError(
                "PortfolioFit.source_mode {0!r} invalid (allowed: {1})".format(
                    self.source_mode, list(SOURCE_MODES)))
        # A portfolio record stores labels / text / bools / tuples-of-str ONLY -- never a numeric
        # size (no scalar number, and no number smuggled inside a tuple like data_gaps).
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                raise ValueError(
                    "PortfolioFit.{0} is numeric -- sizing is a LABEL, never a share count "
                    "or dollar amount".format(f.name))
            if isinstance(value, tuple):
                for element in value:
                    if isinstance(element, (int, float)) and not isinstance(element, bool):
                        raise ValueError(
                            "PortfolioFit.{0} contains a number -- portfolio-fit output carries "
                            "labels / text only, never a numeric size".format(f.name))

    # -- introspection (properties, never stored fields) -------------------- #
    @property
    def fit_state_label(self) -> str:
        return PORTFOLIO_FIT_STATE_LABELS.get(self.fit_state, "")

    @property
    def is_acceptable_fit(self) -> bool:
        return self.fit_state == "acceptable"

    @property
    def has_portfolio_data(self) -> bool:
        return self.data_availability == "present"

    @property
    def is_fixture_sourced(self) -> bool:
        return self.source_mode == "fixture"

    @property
    def reduces_or_blocks(self) -> bool:
        """True when a risk state reduces / blocks the pick (concentration / liquidity / etc.)."""
        return self.fit_state in (
            "concentration_risk", "liquidity_risk", "correlation_risk",
            "avoid_due_to_portfolio_risk", "insufficient_portfolio_data")


# The portfolio-fit contract (for registry / test introspection). Trade/score-clean.
PORTFOLIO_FIT_MODELS = (PortfolioFit,)


# --------------------------------------------------------------------------- #
# Deterministic id                                                              #
# --------------------------------------------------------------------------- #
def portfolio_fit_id_for(run_id: str, ticker: str) -> str:
    """A deterministic fit ref from the run + ticker (no wall-clock, order-stable)."""
    return "pf:{0}:{1}".format(_clean(run_id), _clean(ticker).upper())


# --------------------------------------------------------------------------- #
# 018-engine resolution (REUSE the bands; never recompute a weight)             #
# --------------------------------------------------------------------------- #
def _resolve_concentration_band(
    ticker: str,
    concentration: Tuple[ConcentrationView, ...],
    candidate_exposure: str,
    candidate_comparison: Any,
) -> Tuple[str, Tuple[str, ...]]:
    """The candidate's concentration band, REUSED from 018 (never recomputed here)."""
    override = _clean(candidate_exposure)
    if override:
        if override not in RISK_BANDS:
            raise ValueError("candidate_exposure {0!r} is not an 018 band".format(override))
        return override, ()
    for view in concentration or ():
        if _clean(view.ticker).upper() == ticker:
            return view.weight_band, tuple(view.data_gaps)
    if candidate_comparison is not None:
        label = _clean(getattr(candidate_comparison, "comparison_label", ""))
        if label == "adds_concentration":
            # Already-held / same-theme addition -> it concentrates the existing exposure.
            return "elevated", tuple(getattr(candidate_comparison, "data_gaps", ()) or ())
        if label in ("new_theme", "diversifies"):
            return "minimal", ()
        if label == "no_theme_signal":
            return BAND_UNKNOWN, tuple(getattr(candidate_comparison, "data_gaps", ()) or ())
    return BAND_UNKNOWN, ()


def _resolve_correlation_band(
    ticker: str,
    correlation: Tuple[PairCorrelationView, ...],
    rotation: Tuple[RotationAlignmentView, ...],
) -> Tuple[str, bool]:
    """(correlation band, rotation-against) for the candidate vs the recorded book (018 labels)."""
    band = "minimal"
    saw = False
    for view in correlation or ():
        if ticker in (_clean(view.ticker_a).upper(), _clean(view.ticker_b).upper()):
            saw = True
            if view.correlation_label == "co_exposed":
                band = _worse_band(band, "elevated")
            elif view.correlation_label == "partially_co_exposed":
                band = _worse_band(band, "moderate")
    against = any(
        _clean(view.ticker).upper() == ticker and view.alignment_label == "against"
        for view in (rotation or ()))
    if not saw and not against:
        band = "minimal"
    return band, against


def _resolve_liquidity_band(
    ticker: str, liquidity_signal: str, holdings: Optional[PortfolioHoldings],
) -> Tuple[str, bool]:
    """(liquidity band, is-thin) from an explicit signal or the operator's recorded liquidity note."""
    signal = _clean(liquidity_signal).lower()
    if not signal and holdings is not None:
        for position in holdings.positions:
            if _clean(position.ticker).upper() == ticker:
                signal = _clean(position.liquidity_note).lower()
                break
    if any(token in signal for token in _THIN_LIQUIDITY):
        return "elevated", True
    if any(token in signal for token in _ADEQUATE_LIQUIDITY):
        return "minimal", False
    return BAND_UNKNOWN, False


def _load_from_store(store_dir: str, ticker: str):
    """Load holdings + the 018 views from a persisted store (offline, local files only)."""
    holdings, reason = load_holdings(store_dir)
    if holdings is None or not holdings.positions:
        return None, (), (), (), None, (reason or "no holdings recorded")
    concentration = build_concentration(store_dir)
    correlation = build_correlation_labels(store_dir)
    rotation = build_rotation_alignment(store_dir)
    try:
        comparison = compare_candidate(store_dir, ticker)
    except ValueError:
        comparison = None
    return holdings, concentration, correlation, rotation, comparison, ""


# --------------------------------------------------------------------------- #
# The assessor                                                                  #
# --------------------------------------------------------------------------- #
def assess_portfolio_fit(
    ticker: str,
    *,
    run_id: str,
    now: str,
    store_dir: str = "",
    holdings: Optional[PortfolioHoldings] = None,
    concentration: Tuple[ConcentrationView, ...] = (),
    correlation: Tuple[PairCorrelationView, ...] = (),
    rotation: Tuple[RotationAlignmentView, ...] = (),
    candidate_comparison: Any = None,
    candidate_exposure: str = "",
    liquidity_signal: str = "",
    source_mode: str = "",
    data_gaps: Tuple[str, ...] = (),
) -> PortfolioFit:
    """Derive a :class:`PortfolioFit` from the 018 read-only Portfolio Intelligence.

    Derivation (deterministic; REUSES the 018 bands; NEVER fabricates exposure):

    * **No holdings recorded** -> ``insufficient_portfolio_data`` + a visible ``data_gaps`` note +
      sizing ``watch only`` (an honest absence, never invented exposure). This can NOT be a
      production pick.
    * **Concentration above the 018 thresholds** -> ``concentration_risk`` (sizing reduced), or
      ``avoid_due_to_portfolio_risk`` when the band is ``dominant`` (sizing avoid).
    * **A thin liquidity signal** -> ``liquidity_risk`` (sizing small position).
    * **Elevated correlation / rotation-misalignment** -> ``correlation_risk`` (sizing reduced).
    * **A clean fit within the risk budget** -> ``acceptable`` + a starter / small / normal sizing
      label appropriate to the (minimal / moderate) concentration and whether it is already held.

    ``store_dir`` (when given and no ``holdings``/views are injected) loads the recorded holdings
    and the 018 views via the read-only engine. ``now`` is injected. ``candidate_exposure`` is an
    optional explicit 018 band override for the candidate. FIXTURE / production gating for
    ACCEPTABILITY is applied by :func:`portfolio_fit_acceptable`, not here.
    """
    if not _clean(ticker):
        raise ValueError("assess_portfolio_fit requires a non-empty ticker")
    if not _clean(run_id):
        raise ValueError("assess_portfolio_fit requires a non-empty run_id")

    symbol = _clean(ticker).upper()
    mode = _clean(source_mode)
    extra_gaps = tuple(_clean(g) for g in (data_gaps or ()) if _clean(g))

    # 1. Resolve holdings + views. A store_dir loads them via the 018 engine; otherwise use the
    #    injected 018 view objects directly (the same read-only engine outputs).
    load_reason = ""
    if holdings is None and not concentration and not correlation and not rotation \
            and candidate_comparison is None and _clean(store_dir):
        (holdings, concentration, correlation, rotation, candidate_comparison,
         load_reason) = _load_from_store(store_dir, symbol)

    held = holdings is not None and bool(getattr(holdings, "positions", ()))

    def _build(*, fit_state: str, fit_reason: str, sizing: str, availability: str,
               risk_budget: str, conc: str, liq: str, corr: str,
               gaps: Tuple[str, ...] = ()) -> PortfolioFit:
        merged = tuple(dict.fromkeys(extra_gaps + tuple(_clean(g) for g in gaps if _clean(g))))
        return PortfolioFit(
            ticker=symbol, run_id=_clean(run_id), generated_at=str(now),
            fit_state=fit_state, fit_reason=fit_reason,
            risk_budget_label=risk_budget, concentration_risk_label=conc,
            liquidity_risk_label=liq, correlation_risk_label=corr,
            sizing_guardrail_label=sizing, data_availability=availability,
            source_mode=mode, data_gaps=merged)

    # 2. No holdings recorded -> insufficient (honest absence, never invented exposure).
    if not held:
        gap = ("no holdings recorded for portfolio-fit on {0}: {1} -- portfolio fit CANNOT be "
               "assessed, so no production-grade sizing is possible; exposure is never invented"
               .format(symbol, load_reason or "the operator has recorded no holdings statement"))
        return _build(
            fit_state="insufficient_portfolio_data",
            fit_reason=("portfolio fit is INSUFFICIENT for {0}: {1}".format(symbol, gap)),
            sizing="watch only", availability="insufficient",
            risk_budget=BAND_UNKNOWN, conc=BAND_UNKNOWN, liq=BAND_UNKNOWN, corr=BAND_UNKNOWN,
            gaps=(gap,))

    # 3. Resolve the reused 018 risk bands for this candidate.
    conc_band, conc_gaps = _resolve_concentration_band(
        symbol, concentration, candidate_exposure, candidate_comparison)
    corr_band, rotation_against = _resolve_correlation_band(symbol, correlation, rotation)
    liq_band, liquidity_thin = _resolve_liquidity_band(symbol, liquidity_signal, holdings)
    risk_budget = _worse_band(_worse_band(conc_band, corr_band), liq_band)

    # 4. Concentration DOMINANT -> avoid; ELEVATED -> concentration_risk (reduces / blocks).
    if conc_band == "dominant":
        return _build(
            fit_state="avoid_due_to_portfolio_risk",
            fit_reason=("AVOID on portfolio risk for {0}: the recorded exposure is already "
                        "DOMINANT (018 band) -- adding here breaches the concentration budget"
                        .format(symbol)),
            sizing="avoid due to concentration", availability="present",
            risk_budget=risk_budget, conc=conc_band, liq=liq_band, corr=corr_band, gaps=conc_gaps)
    if conc_band == "elevated":
        return _build(
            fit_state="concentration_risk",
            fit_reason=("CONCENTRATION RISK for {0}: the exposure is ELEVATED (018 band, above the "
                        "published position/theme thresholds) -- size must be reduced".format(symbol)),
            sizing="reduced due to volatility", availability="present",
            risk_budget=risk_budget, conc=conc_band, liq=liq_band, corr=corr_band, gaps=conc_gaps)

    # 5. A thin liquidity signal -> liquidity_risk (reduces / blocks).
    if liquidity_thin:
        return _build(
            fit_state="liquidity_risk",
            fit_reason=("LIQUIDITY RISK for {0}: the recorded liquidity signal reads THIN -- a "
                        "smaller position is warranted and the pick is not clean".format(symbol)),
            sizing="small position", availability="present",
            risk_budget=risk_budget, conc=conc_band, liq=liq_band, corr=corr_band, gaps=conc_gaps)

    # 6. Elevated correlation / rotation-against -> correlation_risk (reduces / blocks).
    if corr_band in ("elevated", "dominant") or rotation_against:
        why = "co-exposed with the recorded book (018 shared-theme label)"
        if rotation_against:
            why = "the mapped theme's latest persisted pulse rotates AGAINST the holder"
        return _build(
            fit_state="correlation_risk",
            fit_reason=("CORRELATION RISK for {0}: {1} -- size must be reduced".format(symbol, why)),
            sizing="reduced due to volatility", availability="present",
            risk_budget=risk_budget, conc=conc_band, liq=liq_band, corr=corr_band, gaps=conc_gaps)

    # 7. A clean fit within the risk budget -> acceptable + starter / small / normal sizing.
    already_recorded = bool(getattr(candidate_comparison, "already_recorded", False)) or any(
        _clean(v.ticker).upper() == symbol for v in (concentration or ()))
    if conc_band == "moderate":
        sizing = "starter position only"
    elif already_recorded:
        sizing = "small position"
    else:
        sizing = "normal risk budget"
    gaps: Tuple[str, ...] = ()
    if conc_band == BAND_UNKNOWN:
        gaps = ("the candidate's concentration band is honestly unknown (no weighable mapping) -- "
                "sizing stays conservative; no exposure is invented",)
        sizing = "starter position only"
    return _build(
        fit_state="acceptable",
        fit_reason=("ACCEPTABLE portfolio fit for {0}: exposure is within the risk budget "
                    "(concentration {1}, correlation {2}, liquidity {3}) -- {4} sizing for MANUAL "
                    "REVIEW".format(symbol, conc_band, corr_band, liq_band, sizing)),
        sizing=sizing, availability="present",
        risk_budget=risk_budget, conc=conc_band, liq=liq_band, corr=corr_band, gaps=conc_gaps + gaps)


# --------------------------------------------------------------------------- #
# The verdict 022B gate 12 consumes                                             #
# --------------------------------------------------------------------------- #
def portfolio_fit_acceptable(
    fit: Optional[PortfolioFit], *, production: bool = False,
) -> Tuple[bool, str]:
    """Whether a portfolio fit is ACCEPTABLE for gate 12 -- ``(ok, reason)``.

    ``True`` ONLY when ``fit_state == "acceptable"`` AND ``data_availability`` is ``present`` AND
    (not ``production`` OR ``source_mode`` is not a fixture). Every other case is ``False`` with
    the EXACT reason:

    * no fit -> False;
    * ``concentration_risk`` / ``avoid_due_to_portfolio_risk`` -> False (concentration reduces /
      blocks the pick);
    * ``liquidity_risk`` -> False; ``correlation_risk`` -> False;
    * ``insufficient_portfolio_data`` -> False (no holdings -> no production-grade sizing);
    * a fixture-sourced fit under ``production=True`` -> False (fixture is shadow / demo only).
    """
    if fit is None:
        return False, ("no PortfolioFit supplied -- a recommendation cannot be actionable without "
                       "an assessed portfolio fit + sizing guardrail")
    if not isinstance(fit, PortfolioFit):
        return False, "supplied portfolio object is not a PortfolioFit"

    state = fit.fit_state
    if state != "acceptable":
        if state == "avoid_due_to_portfolio_risk":
            return False, ("avoid_due_to_portfolio_risk: the recorded exposure is DOMINANT -- "
                           "concentration blocks the pick")
        if state == "concentration_risk":
            return False, ("concentration_risk: exposure is ELEVATED above the 018 thresholds -- "
                           "concentration reduces / blocks the pick")
        if state == "liquidity_risk":
            return False, ("liquidity_risk: the liquidity signal reads thin -- liquidity risk "
                           "reduces / blocks the pick")
        if state == "correlation_risk":
            return False, ("correlation_risk: co-exposure / rotation-misalignment with the book -- "
                           "correlation reduces / blocks the pick")
        if state == "insufficient_portfolio_data":
            return False, ("insufficient_portfolio_data: no holdings recorded -- an actionable "
                           "production pick can NOT be built on insufficient portfolio data")
        return False, ("fit_state {0!r} is not 'acceptable' -- portfolio fit is not clean".format(
            state))

    if not fit.has_portfolio_data:
        return False, ("portfolio data is {0!r} (not present) -- production-grade sizing requires "
                       "recorded holdings".format(fit.data_availability or "missing"))

    if production and fit.is_fixture_sourced:
        return False, ("fixture-sourced portfolio fit cannot be PRODUCTION-actionable -- a fixture "
                       "fit is fine for shadow / demo only, never a production pick")

    return True, ("acceptable portfolio fit within the risk budget on {0} data; sizing guardrail "
                  "{1!r}".format(fit.source_mode or "source-backed", fit.sizing_guardrail_label))


# --------------------------------------------------------------------------- #
# Construction-time guard: the fit may carry NO trade / score / order field.      #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(PortfolioFit)

# Belt-and-braces: no stored field name may carry a numeric-verdict or order/execution token.
for _f in fields(PortfolioFit):
    _low = _f.name.lower()
    for _tok in ("score", "rank", "rating", "target", "submit", "rebalance",
                 "shares", "quantity", "amount", "notional", "dollar"):
        assert _tok not in _low, "forbidden field token {0!r} on PortfolioFit".format(_f.name)
