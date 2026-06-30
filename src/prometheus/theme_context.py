"""Stage B -- Theme / capital-cycle context.

Maps the Opportunity Hypothesis's ``theme_maturity`` onto a capital-cycle stage
and a crowding level. The capital cycle is the alpha clock: money made deploying
into an UNDER-invested or EARLY theme is repriced; money deployed into an
OVER-invested or euphoric theme is the exit liquidity. ``is_early_enough`` is the
gate the rest of the gauntlet leans on.
"""

from __future__ import annotations

from dataclasses import dataclass

# theme_maturity -> capital cycle stage
_STAGE_BY_MATURITY = {
    "hidden": "under_invested",
    "emerging": "early_investment",
    "accelerating": "acceleration",
    "crowded": "over_invested",
    "euphoric": "bubble",
}

_CROWDING_BY_STAGE = {
    "under_invested": 0.10,
    "early_investment": 0.25,
    "acceleration": 0.50,
    "over_invested": 0.80,
    "bubble": 1.00,
}

_EARLY_STAGES = ("under_invested", "early_investment", "acceleration")


@dataclass(frozen=True)
class ThemeContextResult:
    theme: str = ""
    theme_maturity: str = ""
    capital_cycle_stage: str = ""
    crowding_level: float = 0.0
    is_early_enough: bool = False
    theme_context_score: float = 0.0
    megatrend_context: tuple = ()


def analyze_theme_context(opportunity_hypothesis) -> ThemeContextResult:
    oh = opportunity_hypothesis
    stage = _STAGE_BY_MATURITY.get(oh.theme_maturity, "early_investment")
    crowding = _CROWDING_BY_STAGE.get(stage, 0.5)
    is_early = stage in _EARLY_STAGES
    return ThemeContextResult(
        theme=oh.theme,
        theme_maturity=oh.theme_maturity,
        capital_cycle_stage=stage,
        crowding_level=round(crowding, 4),
        is_early_enough=is_early,
        theme_context_score=round(1.0 - crowding, 4),
        megatrend_context=tuple(oh.megatrend_context),
    )
