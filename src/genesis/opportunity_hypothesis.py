"""Genesis -- the Opportunity Hypothesis (reasoning object).

A candidate Opportunity, bound to the Intelligence Assessment that motivates it.
MINIMAL placeholder data model.
"""

from __future__ import annotations

from dataclasses import dataclass

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance


@dataclass(frozen=True)
class OpportunityHypothesis(ReasoningObject):
    subject: str = ""
    hypothesis: str = ""
    confidence: float = 0.0


def make_opportunity_hypothesis(assessment, subject, hypothesis, actor, now, confidence=0.5):
    sources = (assessment.ref("IntelligenceAssessment"),)
    oid = stable_id("OPH", assessment.id, subject, hypothesis)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return OpportunityHypothesis(
        id=oid,
        version=1,
        provenance=prov,
        subject=subject,
        hypothesis=hypothesis,
        confidence=confidence,
    )
