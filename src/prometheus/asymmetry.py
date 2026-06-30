"""Stage H -- Risk/reward asymmetry.

Frames the trade as a payoff, not a story: how far down to the bear case versus
how far up to the bull case, probability-weighted. Dilution risk LOWERS the bear
price (a diluted downside is worse), excessive downside (> 50%) cannot be labelled
"exceptional", and a poor (ratio < 1) asymmetry is a hard gate downstream. The
gauntlet refuses an attractive narrative with an ugly payoff.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import clamp, safe_ratio

_DILUTION_BEAR_HAIRCUT = {"none": 0.0, "low": 0.03, "moderate": 0.08, "high": 0.15}


@dataclass(frozen=True)
class AsymmetryResult:
    downside_risk: float = 0.0
    upside_potential: float = 0.0
    upside_downside_ratio: float = 0.0
    prob_weighted_ev: float = 0.0
    asymmetry_score: float = 0.0
    asymmetry_label: str = "undetermined"
    effective_bear_price: float = 0.0
    notes: tuple = ()


def analyze_asymmetry(candidate, scenario_probabilities=(0.25, 0.5, 0.25)) -> AsymmetryResult:
    c = candidate
    if c is None or c.current_price is None or c.bear_price is None or c.bull_price is None:
        # asymmetry REQUIRES both an upside and a downside anchor.
        return AsymmetryResult(asymmetry_label="undetermined", asymmetry_score=0.0,
                               notes=("missing bear/bull/current price -- asymmetry undetermined",))

    current = float(c.current_price)
    if current <= 0:
        return AsymmetryResult(asymmetry_label="undetermined", asymmetry_score=0.0,
                               notes=("non-positive current price",))

    # Dilution worsens the realistic downside: haircut the bear price.
    haircut = _DILUTION_BEAR_HAIRCUT.get(c.dilution_risk, 0.0)
    haircut += 0.02 * (int(c.shelf_registration) + int(c.atm_facility) + int(c.convertible_debt))
    effective_bear = float(c.bear_price) * (1.0 - clamp(haircut, 0.0, 0.5))

    base = float(c.base_price) if c.base_price is not None else current
    bull = float(c.bull_price)

    downside_risk = clamp((current - effective_bear) / current, 0.0, 1.0)
    upside_potential = max((bull - current) / current, 0.0)
    ratio = safe_ratio(upside_potential, downside_risk)

    p_bear, p_base, p_bull = scenario_probabilities
    r_bear = (effective_bear - current) / current
    r_base = (base - current) / current
    r_bull = (bull - current) / current
    ev = p_bear * r_bear + p_base * r_base + p_bull * r_bull

    score = clamp(0.5 * min(1.0, ratio / 4.0) + 0.5 * clamp(0.5 + ev))

    if ratio < 1.0:
        label = "poor"
    elif ratio < 2.0:
        label = "balanced"
    elif ratio <= 4.0:
        label = "favorable"
    else:
        # "exceptional" requires the downside to be contained (<= 50%).
        label = "exceptional" if downside_risk <= 0.50 else "favorable"

    notes = []
    if downside_risk > 0.50:
        notes.append("downside exceeds 50% -- capped below 'exceptional'")
    if haircut > 0:
        notes.append("dilution risk haircut the bear case, worsening the downside")

    return AsymmetryResult(
        downside_risk=round(downside_risk, 4),
        upside_potential=round(upside_potential, 4),
        upside_downside_ratio=round(ratio, 4),
        prob_weighted_ev=round(ev, 4),
        asymmetry_score=round(score, 4),
        asymmetry_label=label,
        effective_bear_price=round(effective_bear, 4),
        notes=tuple(notes),
    )
