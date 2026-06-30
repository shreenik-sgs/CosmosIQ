"""Genesis -- the Opportunity (reasoning object).

MINIMAL placeholder. An Opportunity is a confirmed candidate worth pursuing; in
this slice it is a thin data model bound to its grounding.
"""

from __future__ import annotations

from dataclasses import dataclass

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance


@dataclass(frozen=True)
class Opportunity(ReasoningObject):
    subject: str = ""
    description: str = ""


def make_opportunity(hypothesis, description, actor, now):
    sources = (hypothesis.ref("OpportunityHypothesis"),)
    oid = stable_id("OPP", hypothesis.id, description)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return Opportunity(
        id=oid,
        version=1,
        provenance=prov,
        subject=getattr(hypothesis, "subject", ""),
        description=description,
    )
