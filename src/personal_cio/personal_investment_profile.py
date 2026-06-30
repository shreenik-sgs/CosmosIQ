"""Personal CIO (Saarathi) -- the Personal Investment Profile (reasoning object).

The frozen statement of ONE person's investing constraints and preferences: risk
tolerance, concentration / theme / drawdown / cash limits, time horizon,
liquidity needs, allowed and restricted instruments, and whether options /
leverage are permitted. The personalization layer reads it (alongside a
``PortfolioSnapshot``) to translate a governed ``InvestmentAction`` into a
suitability view and a sizing RANGE for this user -- never an order.

MVP / MANUAL: every field is supplied BY HAND. Nothing here is fetched. The
profile carries NO order, NO allocation amount, NO instruction -- it is the
person's standing risk policy, read but never re-decided downstream.

``make_personal_investment_profile`` stays backward-compatible with the earlier
minimal signature ``(account, actor, now, risk_tolerance=..., constraints=())``
so the existing slice / threading callers keep working; the richer fields default
to sensible MVP values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

RISK_TOLERANCES = frozenset({"conservative", "moderate", "aggressive", "asymmetric_growth"})
LIQUIDITY_REQUIREMENTS = frozenset({"low", "moderate", "high"})


@dataclass(frozen=True)
class PersonalInvestmentProfile(ReasoningObject):
    """One person's standing investing constraints and preferences (hand-fed).

    Percentages are numbers in 0..100 (e.g. ``8.0`` means 8% of the portfolio).
    """

    account: str = ""
    risk_tolerance: str = "moderate"  # conservative|moderate|aggressive|asymmetric_growth
    max_single_position_pct: float = 8.0
    max_theme_exposure_pct: float = 25.0
    max_drawdown_tolerance_pct: float = 20.0
    min_cash_reserve_pct: float = 10.0
    preferred_time_horizon: str = "multi_year"
    liquidity_requirement: str = "moderate"  # low|moderate|high
    allowed_instruments: Tuple[str, ...] = field(default_factory=tuple)
    restricted_instruments: Tuple[str, ...] = field(default_factory=tuple)
    tax_sensitivity: str = "unspecified"  # placeholder (MVP)
    options_allowed: bool = False
    leverage_allowed: bool = False
    concentration_preference: str = "diversified"
    manual_execution_required: bool = True
    user_notes: str = ""
    constraints: Tuple[str, ...] = field(default_factory=tuple)  # legacy free-form

    @property
    def profile_id(self) -> str:
        return self.id


def make_personal_investment_profile(
    account,
    actor,
    now,
    risk_tolerance="moderate",
    constraints=(),
    *,
    max_single_position_pct=8.0,
    max_theme_exposure_pct=25.0,
    max_drawdown_tolerance_pct=20.0,
    min_cash_reserve_pct=10.0,
    preferred_time_horizon="multi_year",
    liquidity_requirement="moderate",
    allowed_instruments=(),
    restricted_instruments=(),
    tax_sensitivity="unspecified",
    options_allowed=False,
    leverage_allowed=False,
    concentration_preference="diversified",
    manual_execution_required=True,
    user_notes="",
    **_ignored,
):
    """Build a ``PersonalInvestmentProfile``. Backward-compatible: ``account``,
    ``actor``, ``now`` (and the legacy ``risk_tolerance`` / ``constraints``) are
    accepted positionally; the richer fields are keyword-only with MVP defaults.
    """
    if risk_tolerance not in RISK_TOLERANCES:
        raise ValueError(
            "risk_tolerance must be one of {0}; got {1!r}".format(
                sorted(RISK_TOLERANCES), risk_tolerance
            )
        )
    oid = stable_id("PIP", account, risk_tolerance)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=())
    return PersonalInvestmentProfile(
        id=oid,
        version=1,
        provenance=prov,
        account=account,
        risk_tolerance=risk_tolerance,
        max_single_position_pct=float(max_single_position_pct),
        max_theme_exposure_pct=float(max_theme_exposure_pct),
        max_drawdown_tolerance_pct=float(max_drawdown_tolerance_pct),
        min_cash_reserve_pct=float(min_cash_reserve_pct),
        preferred_time_horizon=preferred_time_horizon,
        liquidity_requirement=liquidity_requirement,
        allowed_instruments=tuple(allowed_instruments),
        restricted_instruments=tuple(restricted_instruments),
        tax_sensitivity=tax_sensitivity,
        options_allowed=bool(options_allowed),
        leverage_allowed=bool(leverage_allowed),
        concentration_preference=concentration_preference,
        manual_execution_required=bool(manual_execution_required),
        user_notes=user_notes,
        constraints=tuple(constraints),
    )
