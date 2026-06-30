"""Personal CIO (Saarathi) -- the Portfolio Snapshot (reasoning object).

A frozen, point-in-time view of ONE user's portfolio that the personalization
layer reads to size a candidate against the person's actual holdings, cash, and
concentration. It answers "what does this person already own, how much room and
cash is left, and how liquid is it?" -- never "what should they do".

MVP / MANUAL: every field here is supplied BY HAND. Nothing in this module (or
anywhere downstream of it) fetches positions, balances, or quotes from a broker
or custodian -- there is NO live account / broker / market-data access. The
snapshot is a researcher's (or the user's) structured statement of the portfolio
at ``as_of``. It carries NO order, NO trade, NO instruction -- it is pure state.

Frozen: the snapshot is read and never mutated; building a personalized view from
it can never change it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

LIQUIDITY_LEVELS = frozenset({"low", "moderate", "high"})


@dataclass(frozen=True)
class PortfolioSnapshot(ReasoningObject):
    """A hand-fed, point-in-time view of one user's portfolio.

    Percentages are expressed as numbers in 0..100 (e.g. ``8.0`` means 8%).
    Dollar values are in whatever single consistent currency the user records.
    """

    account: str = ""
    total_portfolio_value: float = 0.0
    available_cash: float = 0.0
    current_positions: Tuple[Any, ...] = field(default_factory=tuple)
    current_position_pct: Dict[str, float] = field(default_factory=dict)
    theme_exposures: Dict[str, float] = field(default_factory=dict)
    sector_exposures: Dict[str, float] = field(default_factory=dict)
    unrealized_gain_loss: float = 0.0  # placeholder (MVP)
    existing_exposure_to_candidate: float = 0.0  # % of portfolio already in the candidate
    existing_exposure_to_theme: float = 0.0      # % of portfolio already in the theme
    liquidity_constraints: str = "low"           # low | moderate | high
    open_risk_flags: Tuple[str, ...] = field(default_factory=tuple)
    as_of: str = ""


def make_portfolio_snapshot(
    account,
    actor,
    now,
    *,
    total_portfolio_value=100_000.0,
    available_cash=50_000.0,
    current_positions=(),
    current_position_pct=None,
    theme_exposures=None,
    sector_exposures=None,
    unrealized_gain_loss=0.0,
    existing_exposure_to_candidate=0.0,
    existing_exposure_to_theme=0.0,
    liquidity_constraints="low",
    open_risk_flags=(),
    **_ignored,
):
    """Build a hand-fed ``PortfolioSnapshot`` (MVP; no live broker/account fetch).

    Every value is supplied explicitly -- there is no autonomous data acquisition.
    """
    if liquidity_constraints not in LIQUIDITY_LEVELS:
        raise ValueError(
            "liquidity_constraints must be one of {0}; got {1!r}".format(
                sorted(LIQUIDITY_LEVELS), liquidity_constraints
            )
        )
    oid = stable_id("PFS", account, total_portfolio_value, available_cash)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=())
    return PortfolioSnapshot(
        id=oid,
        version=1,
        provenance=prov,
        account=account,
        total_portfolio_value=float(total_portfolio_value),
        available_cash=float(available_cash),
        current_positions=tuple(current_positions),
        current_position_pct=dict(current_position_pct or {}),
        theme_exposures=dict(theme_exposures or {}),
        sector_exposures=dict(sector_exposures or {}),
        unrealized_gain_loss=float(unrealized_gain_loss),
        existing_exposure_to_candidate=float(existing_exposure_to_candidate),
        existing_exposure_to_theme=float(existing_exposure_to_theme),
        liquidity_constraints=liquidity_constraints,
        open_risk_flags=tuple(open_risk_flags),
        as_of=iso_from_epoch(now),
    )
