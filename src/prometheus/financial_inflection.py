"""Stage F -- Financial inflection probability.

Estimates the probability that the mapped winner is at (or entering) a genuine
fundamental inflection: accelerating revenue, expanding margin, raised guidance.
Capital-structure rot -- dilution, shelf/ATM/convertible overhang, thin cash
runway -- SUBTRACTS from the probability, because a real inflection financed by
selling the future is a weaker edge. Dilution must lower this score.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import clamp, sign, safe_ratio

_GUIDANCE_ADJ = {"raise": 0.15, "inline": 0.0, "cut": -0.15}
_DILUTION_PENALTY = {"none": 0.0, "low": 0.05, "moderate": 0.15, "high": 0.30}


@dataclass(frozen=True)
class FinancialInflectionResult:
    revenue_inflection: float = 0.0
    margin_expansion: float = 0.0
    guidance_adjustment: float = 0.0
    dilution_penalty: float = 0.0
    financing_penalty: float = 0.0
    financial_inflection_probability: float = 0.0
    financial_inflection_score: float = 0.0
    notes: tuple = ()


def _financing_penalty(c) -> float:
    penalty = 0.0
    if c.fcf is not None and c.fcf < 0 and c.cash is not None:
        runway = safe_ratio(c.cash, abs(c.fcf))
        if runway < 1.0:
            penalty += 0.15
        elif runway < 2.0:
            penalty += 0.08
    return clamp(penalty, 0.0, 0.30)


def analyze_financial_inflection(candidate) -> FinancialInflectionResult:
    c = candidate
    if c is None:
        return FinancialInflectionResult()

    if c.revenue is not None and c.prior_revenue is not None:
        rev_infl = safe_ratio(c.revenue - c.prior_revenue, c.prior_revenue)
    else:
        rev_infl = 0.0

    if c.gross_margin is not None and c.prior_gross_margin is not None:
        margin_exp = c.gross_margin - c.prior_gross_margin
    else:
        margin_exp = 0.0

    guidance_adj = _GUIDANCE_ADJ.get(c.guidance, 0.0)
    dilution_penalty = _DILUTION_PENALTY.get(c.dilution_risk, 0.0)
    dilution_penalty += 0.03 * (int(c.shelf_registration) + int(c.atm_facility)
                                + int(c.convertible_debt))
    financing_penalty = _financing_penalty(c)

    prob = clamp(
        0.40
        + 0.30 * sign(rev_infl) * min(1.0, abs(rev_infl) / 0.30)
        + 0.20 * sign(margin_exp)
        + guidance_adj
        - dilution_penalty
        - financing_penalty,
        0.0, 0.99,
    )

    notes = []
    if dilution_penalty > 0:
        notes.append("dilution / capital-structure overhang reduced the probability")
    if financing_penalty > 0:
        notes.append("thin cash runway reduced the probability")

    return FinancialInflectionResult(
        revenue_inflection=round(rev_infl, 4),
        margin_expansion=round(margin_exp, 4),
        guidance_adjustment=round(guidance_adj, 4),
        dilution_penalty=round(dilution_penalty, 4),
        financing_penalty=round(financing_penalty, 4),
        financial_inflection_probability=round(prob, 4),
        financial_inflection_score=round(prob, 4),
        notes=tuple(notes),
    )
