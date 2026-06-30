"""Genesis (Sphurana) layer.

A real, deterministic Intelligence Assessment -> Opportunity Hypothesis pipeline.
``Opportunity`` remains a thin downstream placeholder.
"""

from __future__ import annotations

from .opportunity import Opportunity, make_opportunity
from .opportunity_hypothesis import (
    OpportunityHypothesis,
    generate_opportunity_hypothesis,
    make_opportunity_hypothesis,
)

__all__ = [
    "Opportunity",
    "make_opportunity",
    "OpportunityHypothesis",
    "generate_opportunity_hypothesis",
    "make_opportunity_hypothesis",
]

# A deterministic alpha-reasoning Intelligence Assessment -> Opportunity Hypothesis
# pipeline. ``Opportunity`` remains a thin downstream placeholder.
