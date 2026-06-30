"""Prometheus (Nivesha) layer: gated alpha thesis, action, and derived position.

The Investment Thesis is produced by an eleven-stage alpha diligence gauntlet
(``generate_investment_thesis``) over an Opportunity Hypothesis + hand-fed
``DiligenceInputs``. The legacy ``make_investment_thesis`` is a TOY shim retained
only to thread pre-existing generic tests.
"""

from __future__ import annotations

from .investment_thesis import (
    InvestmentThesis,
    generate_investment_thesis,
    make_investment_thesis,
    INVESTABILITY_LEVELS,
)
from .diligence_inputs import CandidateInput, DiligenceInputs
from .pattern_matching import (
    analyze_pattern_matching, PatternMatchingResult, MatchedArchetype, ARCHETYPES,
)
from .theme_context import analyze_theme_context, ThemeContextResult
from .value_chain import analyze_value_chain, ValueChainResult, ValueChainNode
from .bottleneck import analyze_bottleneck, BottleneckResult
from .winner_mapping import analyze_winner_mapping, WinnerMappingResult, WinnerScore
from .financial_inflection import analyze_financial_inflection, FinancialInflectionResult
from .market_recognition import analyze_market_recognition, MarketRecognitionResult
from .asymmetry import analyze_asymmetry, AsymmetryResult
from .red_team import analyze_red_team, RedTeamResult, RedTeamCheck, severe_dilution
from .technical_inflection import analyze_technical_inflection, TechnicalInflectionResult
from .repricing_trigger import analyze_repricing_trigger, RepricingTriggerResult
from .investment_action import (
    InvestmentAction,
    generate_investment_action,
    ACTION_TYPES,
    ACTION_STATUSES,
    URGENCY_LEVELS,
    ManualExecutionIntent,
    make_manual_execution_intent,
)
from .position_lifecycle import (
    PositionState,
    position_state,
    PositionContext,
    LIFECYCLE_STATES,
    THESIS_DIRECTIONS,
)

__all__ = [
    "InvestmentThesis",
    "generate_investment_thesis",
    "make_investment_thesis",
    "INVESTABILITY_LEVELS",
    "CandidateInput",
    "DiligenceInputs",
    "analyze_pattern_matching", "PatternMatchingResult", "MatchedArchetype", "ARCHETYPES",
    "analyze_theme_context", "ThemeContextResult",
    "analyze_value_chain", "ValueChainResult", "ValueChainNode",
    "analyze_bottleneck", "BottleneckResult",
    "analyze_winner_mapping", "WinnerMappingResult", "WinnerScore",
    "analyze_financial_inflection", "FinancialInflectionResult",
    "analyze_market_recognition", "MarketRecognitionResult",
    "analyze_asymmetry", "AsymmetryResult",
    "analyze_red_team", "RedTeamResult", "RedTeamCheck", "severe_dilution",
    "analyze_technical_inflection", "TechnicalInflectionResult",
    "analyze_repricing_trigger", "RepricingTriggerResult",
    "InvestmentAction",
    "generate_investment_action",
    "ACTION_TYPES",
    "ACTION_STATUSES",
    "URGENCY_LEVELS",
    "ManualExecutionIntent",
    "make_manual_execution_intent",
    "PositionState",
    "position_state",
    "PositionContext",
    "LIFECYCLE_STATES",
    "THESIS_DIRECTIONS",
]
