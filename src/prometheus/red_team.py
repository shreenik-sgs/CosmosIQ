"""Stage I -- Red team (adversarial pre-mortem).

Before a thesis is allowed to stand, it must survive a fixed battery of "how does
this lose money" challenges, each derived from the prior stages. A critical
failure -- a bubble analog, a poor payoff, no credible winner, or severe dilution
-- fails the whole verdict and labels the thesis a false positive. Lesser worries
mark it conditional. This is where the gauntlet tries hardest to kill its own idea.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from ._common import clamp

# verdicts
PASS, CONCERN, FAIL = "pass", "concern", "fail"


def severe_dilution(candidate) -> bool:
    if candidate is None:
        return False
    if candidate.dilution_risk == "high":
        return True
    if candidate.dilution_risk == "moderate" and (
            candidate.shelf_registration or candidate.atm_facility or candidate.convertible_debt):
        return True
    return False


@dataclass(frozen=True)
class RedTeamCheck:
    check: str
    verdict: str
    rationale: str


@dataclass(frozen=True)
class RedTeamResult:
    checks: Tuple[RedTeamCheck, ...] = field(default_factory=tuple)
    red_team_verdict: str = PASS
    confidence_haircut: float = 0.0
    false_positive_label: str = ""


def _oh_is_rumor_driven(oh) -> bool:
    blob = " ".join(oh.monitoring_signals).lower()
    return ("rumour" in blob or "rumor" in blob) and "catalyst" in blob


def _oh_has_confirmed_catalyst(oh) -> bool:
    return "confirmed/probable positive catalyst" in (oh.why_now or "").lower()


def analyze_red_team(opportunity_hypothesis, pattern_result, bottleneck_result,
                     winner_result, financial_result, market_result, asymmetry_result,
                     technical_result, top_candidate) -> RedTeamResult:
    oh = opportunity_hypothesis
    checks = []

    def add(name, verdict, rationale):
        checks.append(RedTeamCheck(check=name, verdict=verdict, rationale=rationale))

    # 1. the bottleneck resolves before the market reprices it
    if bottleneck_result.resolution_risk >= 0.5:
        add("bottleneck_resolves_soon", CONCERN,
            "the constraint may resolve before it is repriced")
    else:
        add("bottleneck_resolves_soon", PASS,
            "the constraint is durable and hard to resolve")

    # 2. the company fails to capture the value
    if winner_result.no_credible_winner:
        add("company_fails_to_capture", FAIL,
            "no candidate clears the winner gate -- capture is unproven")
    elif winner_result.best_winner_score < 0.55:
        add("company_fails_to_capture", CONCERN,
            "the winner's capture position is only moderate")
    else:
        add("company_fails_to_capture", PASS,
            "the mapped winner is well positioned to capture the value")

    # 3. dilution destroys the upside
    if severe_dilution(top_candidate):
        add("dilution_destroys_upside", FAIL,
            "severe dilution / capital-structure overhang erodes the upside")
    elif top_candidate is not None and top_candidate.dilution_risk in ("moderate", "high"):
        add("dilution_destroys_upside", CONCERN,
            "dilution risk is non-trivial and weighs on the payoff")
    else:
        add("dilution_destroys_upside", PASS, "dilution risk is contained")

    # 4. the valuation already prices the upside
    if market_result.recognition_stage in ("crowded", "euphoric_bubble_risk") \
            and asymmetry_result.asymmetry_label in ("poor", "balanced"):
        add("valuation_prices_in_upside", FAIL,
            "the crowd is in and the payoff is no longer asymmetric")
    elif market_result.recognition_stage in ("crowded", "euphoric_bubble_risk"):
        add("valuation_prices_in_upside", CONCERN,
            "recognition is late -- much of the move may be priced")
    else:
        add("valuation_prices_in_upside", PASS,
            "the opportunity is not yet fully recognised")

    # 5. the theme is too crowded
    if oh.theme_maturity == "euphoric":
        add("theme_too_crowded", FAIL, "the theme is euphoric -- this is late-cycle distribution")
    elif oh.theme_maturity == "crowded":
        add("theme_too_crowded", CONCERN, "the theme is already crowded")
    else:
        add("theme_too_crowded", PASS, "the theme is early enough")

    # 6. this rhymes with a historical bubble
    if pattern_result.bubble_flag:
        add("bubble_analog", FAIL,
            "the setup matches a late-cycle euphoria / bubble archetype")
    else:
        add("bubble_analog", PASS, "no bubble archetype matched")

    # 7. the catalyst never materialises
    if _oh_is_rumor_driven(oh) and not _oh_has_confirmed_catalyst(oh):
        add("catalyst_doesnt_materialize", CONCERN,
            "the thesis leans on an unconfirmed / rumoured catalyst")
    else:
        add("catalyst_doesnt_materialize", PASS,
            "the catalyst is confirmable or not load-bearing")

    # 8. the financial inflection fails to show up
    if financial_result.financial_inflection_score < 0.40:
        add("financial_inflection_fails", CONCERN,
            "the fundamental inflection is weak or unproven")
    else:
        add("financial_inflection_fails", PASS, "a fundamental inflection is plausible")

    # 9. the technical breakout fails
    if technical_result.failed_breakout_risk or not technical_result.technical_confirmation:
        add("technical_breakout_fails", CONCERN,
            "the chart does not confirm the timing")
    else:
        add("technical_breakout_fails", PASS, "the chart confirms the timing")

    # --- verdict ---
    critical_fail = (
        pattern_result.bubble_flag
        or asymmetry_result.asymmetry_label == "poor"
        or winner_result.no_credible_winner
        or severe_dilution(top_candidate)
    )
    n_fail = sum(1 for ch in checks if ch.verdict == FAIL)
    n_concern = sum(1 for ch in checks if ch.verdict == CONCERN)

    if critical_fail or n_fail > 0:
        verdict = FAIL
    elif n_concern > 0:
        verdict = CONCERN  # "conditional"
    else:
        verdict = PASS

    haircut = clamp(0.20 * n_fail + 0.05 * n_concern, 0.0, 0.6)
    label = ""
    if verdict == FAIL:
        label = "likely_false_positive"

    return RedTeamResult(
        checks=tuple(checks),
        red_team_verdict=verdict,
        confidence_haircut=round(haircut, 4),
        false_positive_label=label,
    )
