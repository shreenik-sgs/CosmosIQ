"""Stage G -- Market recognition stage.

Where is the crowd? Alpha is largest when the opportunity is still HIDDEN or only
early-recognised and smallest (or negative) once it is crowded or euphoric. The
stage is inferred from analyst coverage, institutional ownership, whether
valuation already reflects the story, short interest, and the OH's own theme
maturity. A crowded or euphoric reading is a downstream penalty / block.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import clamp, opt

_STAGE_SCORE = {
    "hidden": 0.90,
    "early_recognition": 0.75,
    "accelerating_recognition": 0.50,
    "crowded": 0.25,
    "euphoric_bubble_risk": 0.05,
}

_MATURITY_RECOGNITION = {
    "hidden": 0.05,
    "emerging": 0.20,
    "accelerating": 0.50,
    "crowded": 0.80,
    "euphoric": 0.95,
}


@dataclass(frozen=True)
class MarketRecognitionResult:
    recognition_stage: str = "hidden"
    recognition_level: float = 0.0
    market_recognition_score: float = 0.0
    analyst_coverage: int = 0
    institutional_ownership: float = 0.0
    valuation_reflects_story: bool = False
    notes: tuple = ()


def analyze_market_recognition(opportunity_hypothesis, candidate) -> MarketRecognitionResult:
    oh = opportunity_hypothesis
    c = candidate

    coverage = int(opt(getattr(c, "analyst_coverage", None), 0)) if c else 0
    inst = opt(getattr(c, "institutional_ownership", None), 0.0) if c else 0.0
    valn_story = bool(getattr(c, "valuation_reflects_story", False)) if c else False
    short_int = opt(getattr(c, "short_interest", None), 0.0) if c else 0.0

    coverage_norm = clamp(coverage / 20.0)
    theme_rec = _MATURITY_RECOGNITION.get(oh.theme_maturity, 0.30)

    recognition_level = clamp(
        0.30 * coverage_norm
        + 0.30 * inst
        + 0.20 * (1.0 if valn_story else 0.0)
        + 0.20 * theme_rec
    )

    # Euphoria: fully recognised AND the valuation already prices the story.
    euphoric = (oh.theme_maturity == "euphoric"
                or (recognition_level >= 0.80 and valn_story))
    if euphoric:
        stage = "euphoric_bubble_risk"
    elif recognition_level < 0.20:
        stage = "hidden"
    elif recognition_level < 0.40:
        stage = "early_recognition"
    elif recognition_level < 0.65:
        stage = "accelerating_recognition"
    else:
        stage = "crowded"

    score = _STAGE_SCORE[stage]
    notes = []
    if stage in ("crowded", "euphoric_bubble_risk"):
        notes.append("recognition is late -- the alpha window is largely gone")
    elif stage in ("hidden", "early_recognition"):
        notes.append("recognition is early -- the opportunity is still before-obvious")

    return MarketRecognitionResult(
        recognition_stage=stage,
        recognition_level=round(recognition_level, 4),
        market_recognition_score=round(score, 4),
        analyst_coverage=coverage,
        institutional_ownership=round(inst, 4),
        valuation_reflects_story=valn_story,
        notes=tuple(notes),
    )
