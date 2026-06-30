"""Reality Intelligence -- the Intelligence Assessment (reasoning object).

MINIMAL: this is a placeholder reasoning model. It binds the Observations it was
derived from; the actual intelligence logic (synthesis, scoring, world-modelling)
is intentionally out of scope for this runtime slice.
"""

from __future__ import annotations

from dataclasses import dataclass

from eios_core.canonical_objects import ReasoningObject, Observation
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance


@dataclass(frozen=True)
class IntelligenceAssessment(ReasoningObject):
    subject: str = ""
    assessment: str = ""
    confidence: float = 0.0


def make_intelligence_assessment(observations, subject, assessment, actor, now, confidence=0.5):
    """Build an IntelligenceAssessment bound to the given Observations.

    ``now`` is explicit epoch-seconds (deterministic); it is not read from the
    clock.
    """
    sources = tuple(o.ref("Observation") for o in observations)
    oid = stable_id("IA", subject, assessment, *[s.object_id for s in sources])
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return IntelligenceAssessment(
        id=oid,
        version=1,
        provenance=prov,
        subject=subject,
        assessment=assessment,
        confidence=confidence,
    )
