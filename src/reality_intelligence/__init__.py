"""Reality Intelligence layer.

The first non-placeholder upstream layer: a deterministic Observation ->
Intelligence Assessment pipeline. ``source_observation`` defines the input format
for manually-supplied source material; ``intelligence_assessment`` synthesises a
purpose-free assessment from it.
"""

from __future__ import annotations

from .source_observation import (
    Observation,
    make_source_observation,
    SOURCE_TYPES,
    POLARITIES,
    OBSERVED_CHANGES,
    CATALYST_STATUSES,
    EXPECTED_DIRECTIONS,
)
from .intelligence_assessment import (
    IntelligenceAssessment,
    RealitySignal,
    SIGNAL_TYPES,
    generate_intelligence_assessment,
    make_intelligence_assessment,
    ALLOWED_ASSESSMENT_TYPES,
)

__all__ = [
    "Observation",
    "make_source_observation",
    "SOURCE_TYPES",
    "POLARITIES",
    "OBSERVED_CHANGES",
    "CATALYST_STATUSES",
    "EXPECTED_DIRECTIONS",
    "IntelligenceAssessment",
    "RealitySignal",
    "SIGNAL_TYPES",
    "generate_intelligence_assessment",
    "make_intelligence_assessment",
    "ALLOWED_ASSESSMENT_TYPES",
]
