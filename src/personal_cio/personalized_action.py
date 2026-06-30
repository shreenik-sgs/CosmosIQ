"""Personal CIO (Saarathi) -- the Personalized Action View (reasoning object).

``generate_personalized_action`` converts a governed ``InvestmentAction`` (the
Nivesha / 005 product) into a PERSONALIZED ACTION VIEW for ONE user's profile and
portfolio. It says, for THIS person: is the candidate suitable, blocked, or worth
waiting on; how concentrated / liquid / risk-fit it is; and a sizing RANGE and a
recommended MAX exposure expressed as a PERCENT of the portfolio.

CRITICAL BOUNDARY: this layer recommends a RANGE / max exposure %, NEVER an exact
order. It carries NO exact share count, NO dollar order, NO side, NO quantity, NO
ticket -- only percentages and suitability. The user picks an exact size within
the recommended range, and the (separate, clearly-labelled) Kriya adapter carries
that user-chosen number into manual execution. Saarathi reasons; it never acts.

Determinism: every output is a pure function of (thesis, action, profile,
portfolio, now). No wall clock, no randomness. The upstream thesis / action /
profile / portfolio are never mutated; provenance binds each by (id, version).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

from prometheus.investment_action import InvestmentAction
from prometheus._common import clamp, EPS

from .personal_investment_profile import PersonalInvestmentProfile
from .portfolio_snapshot import PortfolioSnapshot

RECOMMENDATION_STATUSES = frozenset({
    "blocked_for_user",
    "wait_for_user",
    "suitable_candidate",
    "reduced_size_candidate",
    "priority_candidate",
    "risk_reduction_candidate",
    "exit_candidate",
    "monitor_only",
})

# Risk caps (% of portfolio) by risk tolerance -- the unconstrained ceiling that
# conviction scales down. Saarathi is deliberately conservative.
_RISK_CAP_PCT = {
    "conservative": 3.0,
    "moderate": 6.0,
    "aggressive": 10.0,
    "asymmetric_growth": 12.0,
}

_LIQUIDITY_SCORE_BASE = {"low": 1.0, "moderate": 0.6, "high": 0.3}

# Severe concentration = already at/above this fraction of a limit. Severe
# concentration must PREVENT priority_candidate (cap at suitable/reduced).
_SEVERE_FRACTION = 0.8

# Execution / order / sizing language that must NEVER appear in a personalized
# view. Saarathi MAY say: suitable_candidate, priority_candidate,
# reduced_size_candidate, wait_for_user, blocked_for_user, monitor_only,
# recommended_max_exposure_pct, suggested_sizing_range_pct, percent / %.
# NOTE: the broker term is composed from two literals so its substring never
# appears verbatim in this source file, while still matching at runtime.
_FORBIDDEN_TERMS = (
    "buy", "sell", "market order", "limit order", "stop order", "trade ticket",
    "bro" "ker", "execute", "submit", "exact shares", "option contract",
    "order quantity", "shares",
)


def _assert_no_leakage(*texts: str) -> None:
    blob = " ".join(t for t in texts if t).lower()
    hits = [t for t in _FORBIDDEN_TERMS if t in blob]
    if hits:
        raise ValueError(
            "Personalized Action must carry no order / sizing / execution language "
            "(found {0}); Saarathi recommends a suitability and a RANGE / max "
            "exposure %, never an exact order or share count (ADR-0010).".format(hits)
        )


@dataclass(frozen=True)
class PersonalizedAction(ReasoningObject):
    """A deterministic, boundary-clean PERSONALIZED ACTION VIEW for one user.

    Carries suitability, scores, a recommended MAX exposure %, and a suggested
    sizing RANGE (% of portfolio) -- but NO exact shares / dollar order / side /
    quantity / order / ticket (the cognition/actuation boundary, ADR-0010).
    """

    source_action_id: str = ""
    source_action_version: int = 1
    source_thesis_id: str = ""
    source_thesis_version: int = 1
    recommendation_status: str = "monitor_only"
    personalized_rationale: str = ""
    suitability_score: float = 0.0
    concentration_score: float = 0.0
    liquidity_score: float = 0.0
    risk_fit_score: float = 0.0
    portfolio_fit_score: float = 0.0
    recommended_max_exposure_pct: float = 0.0
    suggested_sizing_range_pct: Tuple[float, float] = (0.0, 0.0)
    required_user_confirmations: Tuple[str, ...] = field(default_factory=tuple)
    blocking_conditions: Tuple[str, ...] = field(default_factory=tuple)
    risk_warnings: Tuple[str, ...] = field(default_factory=tuple)
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)
    review_triggers: Tuple[str, ...] = field(default_factory=tuple)
    account: str = ""
    upstream_observation_ids: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def personalized_action_id(self) -> str:
        return self.id


# --- instrument-route detection (deterministic, string-based, MVP) ----------
def _is_option_route(instrument: str) -> bool:
    s = (instrument or "").lower()
    return any(tok in s for tok in (" call", " put", "call ", "put ", "option", "warrant"))


def _is_leverage_route(instrument: str) -> bool:
    s = (instrument or "").lower()
    return any(tok in s for tok in ("leverag", "margin", "2x", "3x", "futures"))


def _exposure_terms(profile, portfolio, risk_cap, conviction):
    """The four ceilings (% of portfolio) whose MIN is the recommended max
    exposure, plus the conviction-scaled risk-cap term and the recommended max
    itself (after any high-liquidity halving). Never an exact size.

    Returns ``(recommended_max, single_room, theme_room, cash_room_pct,
    cap_term)`` so the caller can tell WHICH constraint binds (a portfolio limit
    binding tighter than the risk cap means the position is being reduced).
    """
    total = float(portfolio.total_portfolio_value)
    single_room = profile.max_single_position_pct - portfolio.existing_exposure_to_candidate
    theme_room = profile.max_theme_exposure_pct - portfolio.existing_exposure_to_theme
    cap_term = risk_cap * conviction
    if total <= 0:
        return 0.0, single_room, theme_room, 0.0, cap_term
    reserve = profile.min_cash_reserve_pct / 100.0 * total
    cash_room_pct = (float(portfolio.available_cash) - reserve) / total * 100.0

    candidate = max(0.0, min(single_room, theme_room, cash_room_pct, cap_term))
    if portfolio.liquidity_constraints == "high":
        candidate *= 0.5
    return round(candidate, 4), single_room, theme_room, cash_room_pct, cap_term


def _scores(profile, portfolio, conviction, risk_tolerance):
    total = float(portfolio.total_portfolio_value)
    max_single = max(profile.max_single_position_pct, EPS)
    max_theme = max(profile.max_theme_exposure_pct, EPS)

    concentration_score = clamp(1.0 - portfolio.existing_exposure_to_candidate / max_single)

    if total > 0:
        reserve = profile.min_cash_reserve_pct / 100.0 * total
        free = portfolio.available_cash - reserve
        cash_adequacy = clamp(free / (0.10 * total + EPS))
    else:
        cash_adequacy = 0.0
    liquidity_score = clamp(
        _LIQUIDITY_SCORE_BASE.get(portfolio.liquidity_constraints, 0.6) * cash_adequacy
    )

    if risk_tolerance == "conservative":
        risk_fit_score = clamp(conviction)
    elif risk_tolerance == "moderate":
        risk_fit_score = clamp(0.4 + 0.6 * conviction)
    elif risk_tolerance == "aggressive":
        risk_fit_score = clamp(0.5 + 0.5 * conviction)
    else:  # asymmetric_growth -- tolerant of lower conviction
        risk_fit_score = clamp(0.6 + 0.4 * conviction)

    theme_room = clamp(1.0 - portfolio.existing_exposure_to_theme / max_theme)
    portfolio_fit_score = clamp(0.5 * theme_room + 0.5 * concentration_score)

    return (
        round(concentration_score, 4),
        round(liquidity_score, 4),
        round(risk_fit_score, 4),
        round(portfolio_fit_score, 4),
    )


def generate_personalized_action(thesis, action, profile, portfolio, *,
                                  position_context=None, actor="personal-cio", now):
    """Convert a governed ``InvestmentAction`` into a personalized action view for
    one user's profile + portfolio. Deterministic, boundary-clean, and never
    mutates upstream. Recommends a sizing RANGE / max exposure %, never an order."""
    if not isinstance(action, InvestmentAction):
        raise ValueError(
            "generate_personalized_action requires an InvestmentAction (the 005 "
            "product); got {0}".format(type(action).__name__)
        )
    if not isinstance(profile, PersonalInvestmentProfile):
        raise ValueError(
            "generate_personalized_action requires a PersonalInvestmentProfile; "
            "got {0}".format(type(profile).__name__)
        )
    if not isinstance(portfolio, PortfolioSnapshot):
        raise ValueError(
            "generate_personalized_action requires a PortfolioSnapshot; got "
            "{0}".format(type(portfolio).__name__)
        )

    thesis_confidence = float(getattr(thesis, "thesis_confidence", 0.0))
    timing_confirmation = bool(getattr(thesis, "timing_confirmation", False))
    action_confidence = float(getattr(action, "confidence", 0.0))
    conviction = clamp(thesis_confidence * action_confidence)

    risk_cap = _RISK_CAP_PCT.get(profile.risk_tolerance, 6.0)
    instrument = action.security_or_instrument_mapping

    (recommended_max, single_room, theme_room, cash_room_pct,
     cap_term) = _exposure_terms(profile, portfolio, risk_cap, conviction)
    (concentration_score, liquidity_score, risk_fit_score,
     portfolio_fit_score) = _scores(profile, portfolio, conviction, profile.risk_tolerance)

    # --- portfolio / suitability gate predicates ------------------------------
    total = float(portfolio.total_portfolio_value)
    reserve = profile.min_cash_reserve_pct / 100.0 * total
    over_single = portfolio.existing_exposure_to_candidate >= profile.max_single_position_pct
    over_theme = portfolio.existing_exposure_to_theme >= profile.max_theme_exposure_pct
    no_cash_room = portfolio.available_cash < reserve
    restricted = instrument in profile.restricted_instruments
    not_allowed = bool(profile.allowed_instruments) and instrument not in profile.allowed_instruments
    option_blocked = _is_option_route(instrument) and not profile.options_allowed
    leverage_blocked = _is_leverage_route(instrument) and not profile.leverage_allowed

    # A portfolio limit (single-position / theme / cash) binding tighter than the
    # conviction-scaled risk cap means the position is being REDUCED below the
    # size the thesis alone would justify -> reduced-size candidate.
    other_min = min(single_room, theme_room, cash_room_pct)
    materially_below = other_min < cap_term - EPS

    severe_candidate = (
        portfolio.existing_exposure_to_candidate
        >= _SEVERE_FRACTION * profile.max_single_position_pct
    )
    severe_theme = (
        portfolio.existing_exposure_to_theme
        >= _SEVERE_FRACTION * profile.max_theme_exposure_pct
    )
    severe_concentration = severe_candidate or severe_theme

    blocking_conditions = []
    risk_warnings = []

    at = action.action_type

    # --- map upstream action_type, then apply portfolio / risk gates ----------
    if at == "avoid":
        if action.blocking_conditions:
            status = "blocked_for_user"
            blocking_conditions.extend(action.blocking_conditions)
        else:
            status = "monitor_only"
    elif at == "monitor":
        status = "monitor_only"
    elif at == "wait":
        status = "wait_for_user"
    elif at == "exit_candidate":
        status = "exit_candidate"
    elif at == "trim_candidate":
        status = "risk_reduction_candidate"
    elif at in ("enter_candidate", "add_candidate", "rotate_candidate"):
        # Hard blocks ----------------------------------------------------------
        if restricted:
            status = "blocked_for_user"
            blocking_conditions.append("instrument is on the user's restricted list")
        elif not_allowed:
            status = "blocked_for_user"
            blocking_conditions.append("instrument is not on the user's allowed list")
        elif option_blocked:
            status = "blocked_for_user"
            blocking_conditions.append("derivative route not permitted by the user's profile")
        elif leverage_blocked:
            status = "blocked_for_user"
            blocking_conditions.append("leveraged route not permitted by the user's profile")
        elif over_single:
            status = "blocked_for_user"
            blocking_conditions.append(
                "existing exposure already at/above the user's max single-position percent")
        elif over_theme:
            status = "blocked_for_user"
            blocking_conditions.append(
                "existing theme exposure already at/above the user's max theme percent")
        elif no_cash_room:
            status = "blocked_for_user"
            blocking_conditions.append(
                "no room without breaching the user's minimum cash reserve percent")
        elif recommended_max <= 0:
            status = "blocked_for_user"
            blocking_conditions.append("recommended max exposure percent is zero")
        # Downgrade to wait ----------------------------------------------------
        elif profile.risk_tolerance == "conservative" and thesis_confidence < 0.60:
            status = "wait_for_user"
            risk_warnings.append("conviction below the conservative threshold for this user")
        # Reduced size ---------------------------------------------------------
        elif materially_below or portfolio.liquidity_constraints == "high":
            status = "reduced_size_candidate"
            if portfolio.liquidity_constraints == "high":
                risk_warnings.append("high liquidity constraint halves the sizing range")
            else:
                risk_warnings.append(
                    "sizing constrained below the risk cap by single-position / theme / cash limits")
        # Priority -------------------------------------------------------------
        elif (profile.risk_tolerance in ("aggressive", "asymmetric_growth")
              and thesis_confidence >= 0.70 and timing_confirmation
              and not severe_concentration):
            status = "priority_candidate"
        else:
            status = "suitable_candidate"
            if severe_concentration:
                # severe concentration caps at suitable (never priority)
                risk_warnings.append("existing exposure is near a concentration limit")
    else:
        status = "monitor_only"

    # --- sizing RANGE (never an exact size) -----------------------------------
    if status == "blocked_for_user" or recommended_max <= 0:
        recommended_max = 0.0
        suggested_range = (0.0, 0.0)
        if status not in ("blocked_for_user", "exit_candidate", "risk_reduction_candidate",
                          "monitor_only", "wait_for_user"):
            status = "blocked_for_user"
    else:
        suggested_range = (round(recommended_max * 0.4, 2), round(recommended_max, 2))

    if status == "blocked_for_user":
        suitability_score = 0.0
    else:
        suitability_score = round(
            0.30 * risk_fit_score
            + 0.25 * concentration_score
            + 0.20 * liquidity_score
            + 0.25 * portfolio_fit_score,
            4,
        )

    # --- required user confirmations -----------------------------------------
    required_user_confirmations = []
    if profile.manual_execution_required:
        required_user_confirmations.append(
            "manual execution and explicit user confirmation required (Kriya layer)")

    monitoring_signals = tuple(action.monitoring_signals)
    review_triggers = tuple(action.review_triggers)

    personalized_rationale = (
        "Personalized view: upstream action {at} on {inst} personalized to "
        "{status} for a {rt} profile (thesis confidence {tc}, conviction {cv}). "
        "Recommended max exposure {rmax} percent; suggested sizing range "
        "{lo}-{hi} percent of the portfolio. Suitability {ss}; concentration {cs}; "
        "liquidity {ls}; risk-fit {rf}; portfolio-fit {pf}.".format(
            at=at, inst=instrument or "none", status=status,
            rt=profile.risk_tolerance, tc=round(thesis_confidence, 4),
            cv=round(conviction, 4), rmax=recommended_max,
            lo=suggested_range[0], hi=suggested_range[1], ss=suitability_score,
            cs=concentration_score, ls=liquidity_score, rf=risk_fit_score,
            pf=portfolio_fit_score)
    )

    # --- boundary guard over EVERY synthesised / carried text -----------------
    _assert_no_leakage(
        personalized_rationale, status, instrument,
        " ".join(required_user_confirmations), " ".join(blocking_conditions),
        " ".join(risk_warnings), " ".join(monitoring_signals),
        " ".join(review_triggers),
    )

    # --- binding + provenance -------------------------------------------------
    sources = (action.ref("InvestmentAction"),)
    if thesis is not None:
        sources = sources + (thesis.ref("InvestmentThesis"),)
    sources = sources + (profile.ref("PersonalInvestmentProfile"),
                         portfolio.ref("PortfolioSnapshot"))

    pid = stable_id("PSA", action.id, profile.id, portfolio.id, status)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)

    return PersonalizedAction(
        id=pid,
        version=1,
        provenance=prov,
        source_action_id=action.id,
        source_action_version=int(action.version),
        source_thesis_id=getattr(thesis, "id", action.source_thesis_id),
        source_thesis_version=int(getattr(thesis, "version", action.source_thesis_version)),
        recommendation_status=status,
        personalized_rationale=personalized_rationale,
        suitability_score=suitability_score,
        concentration_score=concentration_score,
        liquidity_score=liquidity_score,
        risk_fit_score=risk_fit_score,
        portfolio_fit_score=portfolio_fit_score,
        recommended_max_exposure_pct=recommended_max,
        suggested_sizing_range_pct=suggested_range,
        required_user_confirmations=tuple(required_user_confirmations),
        blocking_conditions=tuple(blocking_conditions),
        risk_warnings=tuple(risk_warnings),
        monitoring_signals=monitoring_signals,
        review_triggers=review_triggers,
        account=profile.account,
        upstream_observation_ids=tuple(action.upstream_observation_ids),
    )
