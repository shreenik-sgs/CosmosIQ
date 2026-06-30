"""Prometheus -- the Investment Thesis (reasoning object).

Carries the Security / Instrument Mapping (``instrument``), the Capital
Allocation Recommendation (``intended_allocation``), and timing. Per the schema,
the instrument is chosen *here*, not in Execution. MINIMAL placeholder logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance


@dataclass(frozen=True)
class InvestmentThesis(ReasoningObject):
    subject: str = ""
    instrument: str = ""
    direction: str = "long"
    intended_allocation: float = 0.0
    timing: str = "now"
    rationale: str = ""


def make_investment_thesis(
    hypothesis,
    instrument,
    intended_allocation,
    actor,
    now,
    direction="long",
    timing="now",
    rationale="",
):
    sources = (hypothesis.ref("OpportunityHypothesis"),)
    oid = stable_id("THS", hypothesis.id, instrument, str(intended_allocation))
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return InvestmentThesis(
        id=oid,
        version=1,
        provenance=prov,
        subject=getattr(hypothesis, "subject", instrument),
        instrument=instrument,
        direction=direction,
        intended_allocation=float(intended_allocation),
        timing=timing,
        rationale=rationale,
    )
