"""Personal CIO -- the Personalized Action (reasoning object).

Binds an InvestmentAction to a PersonalInvestmentProfile, carrying the
account-specific, personalised allocation and priority. This is the last
reasoning object before Execution; it is consumed by the gate, never re-decided.
"""

from __future__ import annotations

from dataclasses import dataclass

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance


@dataclass(frozen=True)
class PersonalizedAction(ReasoningObject):
    investment_action_id: str = ""
    investment_action_version: int = 1
    account: str = ""
    instrument: str = ""
    action_type: str = ""
    side: str = "buy"
    intended_allocation: float = 0.0
    priority: int = 0
    cio_decision_record_id: str = ""


def make_personalized_action(investment_action, profile, actor, now, priority=0, intended_allocation=None):
    sources = (
        investment_action.ref("InvestmentAction"),
        profile.ref("PersonalInvestmentProfile"),
    )
    alloc = (
        float(intended_allocation)
        if intended_allocation is not None
        else float(investment_action.intended_allocation)
    )
    oid = stable_id("PSA", investment_action.id, profile.id)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return PersonalizedAction(
        id=oid,
        version=1,
        provenance=prov,
        investment_action_id=investment_action.id,
        investment_action_version=investment_action.version,
        account=profile.account,
        instrument=investment_action.instrument,
        action_type=investment_action.action_type,
        side=investment_action.side,
        intended_allocation=alloc,
        priority=priority,
        cio_decision_record_id=oid,
    )
