"""Stage E -- Winner / loser mapping.

Scores each hand-fed candidate on how well it is positioned to CAPTURE the value
the bottleneck creates. The score weights exposure directness, the bottleneck
leverage, margin-capture ability, pricing power, competitive position and
execution -- and SUBTRACTS financing/dilution, balance-sheet and customer-
concentration risk. The security/instrument mapping is the top winner's ticker,
computed only AFTER the candidates are scored (never assumed up front).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ._common import clamp, opt

# leadership_quality is an explicit PLACEHOLDER for the MVP -- we do not yet model
# management quality, so every candidate carries the same neutral 0.5.
LEADERSHIP_PLACEHOLDER = 0.5

# best winner_score must clear this for the thesis to have a credible winner.
WINNER_GATE = 0.40

_DILUTION_BASE = {"none": 0.0, "low": 0.25, "moderate": 0.60, "high": 0.90}
_EXPOSURE_BY_TIER = {1: 1.0, 2: 0.65, 3: 0.45, 4: 0.55}
_GUIDANCE_EXECUTION = {"raise": 0.80, "inline": 0.55, "cut": 0.30}


@dataclass(frozen=True)
class WinnerScore:
    name: str
    ticker: str
    value_chain_role: str
    tier: int
    winner_score: float
    exposure_directness: float
    margin_capture_ability: float
    pricing_power: float
    competitive_position: float
    execution_capability: float
    financing_dilution_risk: float
    balance_sheet_risk: float
    customer_concentration: float
    leadership_quality: float
    key_risks: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WinnerMappingResult:
    winners: Tuple[WinnerScore, ...] = field(default_factory=tuple)
    best_winner: Optional[WinnerScore] = None
    best_winner_score: float = 0.0
    security_or_instrument_mapping: str = ""
    no_credible_winner: bool = True


def _financing_dilution_risk(c) -> float:
    base = _DILUTION_BASE.get(c.dilution_risk, 0.25)
    extra = 0.10 * (int(c.shelf_registration) + int(c.atm_facility) + int(c.convertible_debt))
    return clamp(base + extra)


def _balance_sheet_risk(c) -> float:
    if c.cash is not None and c.debt is not None:
        denom = c.cash + c.debt
        if denom > 0:
            return clamp(c.debt / denom)
    if c.debt is not None and c.debt > 0 and (c.cash is None or c.cash == 0):
        return 0.7
    return 0.3


def _margin_capture_ability(c, capture_role) -> float:
    if c.gross_margin is not None:
        return clamp(c.gross_margin / 0.60)
    # fall back to the chain capture potential when margins are unknown
    return 0.5


def _exposure_directness(c, capture_role) -> float:
    if not c.value_chain_role:
        # winner mapping REQUIRES a value-chain role; without it exposure is nil.
        return 0.10
    base = _EXPOSURE_BY_TIER.get(c.tier, 0.30)
    role = c.value_chain_role.lower()
    cap = (capture_role or "").lower()
    if cap and (role in cap or cap in role):
        base = max(base, 0.95)
    return clamp(base)


def _pricing_power(c, value_chain) -> float:
    role = (c.value_chain_role or "").lower()
    for node in value_chain.nodes:
        if node.role.lower() in role or role in node.role.lower():
            return node.pricing_power
    return 0.5 if c.tier == 1 else 0.4


def _competitive_position(c) -> float:
    return {1: 0.65, 2: 0.50, 3: 0.40, 4: 0.45}.get(c.tier, 0.35)


def analyze_winner_mapping(opportunity_hypothesis, diligence_inputs, bottleneck_result,
                           value_chain_result) -> WinnerMappingResult:
    capture_role = value_chain_result.capture_role
    bottleneck_leverage = bottleneck_result.bottleneck_leverage
    winners = []
    for c in diligence_inputs.candidates:
        exposure = _exposure_directness(c, capture_role)
        margin_cap = _margin_capture_ability(c, capture_role)
        pricing = _pricing_power(c, value_chain_result)
        competitive = _competitive_position(c)
        execution = _GUIDANCE_EXECUTION.get(c.guidance, 0.50)
        dilution = _financing_dilution_risk(c)
        balance = _balance_sheet_risk(c)
        customer = 0.30  # PLACEHOLDER -- customer concentration not yet modelled

        score = clamp(
            0.25 * exposure
            + 0.20 * bottleneck_leverage
            + 0.20 * margin_cap
            + 0.15 * pricing
            + 0.10 * competitive
            + 0.10 * execution
            - 0.15 * dilution
            - 0.10 * balance
            - 0.10 * customer
        )

        risks = []
        if not c.value_chain_role:
            risks.append("no value-chain role specified -- exposure unverified")
        if dilution >= 0.6:
            risks.append("financing / dilution risk elevated")
        if balance >= 0.6:
            risks.append("balance-sheet leverage elevated")
        risks.append("leadership quality is a placeholder (not yet assessed)")

        winners.append(WinnerScore(
            name=c.name, ticker=c.ticker, value_chain_role=c.value_chain_role,
            tier=c.tier, winner_score=round(score, 4),
            exposure_directness=round(exposure, 4),
            margin_capture_ability=round(margin_cap, 4),
            pricing_power=round(pricing, 4),
            competitive_position=round(competitive, 4),
            execution_capability=round(execution, 4),
            financing_dilution_risk=round(dilution, 4),
            balance_sheet_risk=round(balance, 4),
            customer_concentration=round(customer, 4),
            leadership_quality=LEADERSHIP_PLACEHOLDER,
            key_risks=tuple(risks),
        ))

    winners.sort(key=lambda w: w.winner_score, reverse=True)
    best = winners[0] if winners else None
    best_score = best.winner_score if best else 0.0
    no_credible = best_score < WINNER_GATE
    # security/instrument mapping FOLLOWS the winner mapping (computed after scoring).
    mapping = "" if (best is None or no_credible) else best.ticker
    return WinnerMappingResult(
        winners=tuple(winners),
        best_winner=best,
        best_winner_score=best_score,
        security_or_instrument_mapping=mapping,
        no_credible_winner=no_credible,
    )
