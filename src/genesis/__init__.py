"""Genesis layer (minimal placeholder reasoning models)."""

from __future__ import annotations

from .opportunity import Opportunity, make_opportunity
from .opportunity_hypothesis import OpportunityHypothesis, make_opportunity_hypothesis

__all__ = [
    "Opportunity",
    "make_opportunity",
    "OpportunityHypothesis",
    "make_opportunity_hypothesis",
]
