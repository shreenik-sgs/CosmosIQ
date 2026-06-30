"""Personal CIO -- the Personal Investment Profile (reasoning object).

MINIMAL placeholder. Holds the person's account, risk tolerance, and
constraints used to personalise an action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance


@dataclass(frozen=True)
class PersonalInvestmentProfile(ReasoningObject):
    account: str = ""
    risk_tolerance: str = "moderate"
    constraints: Tuple[str, ...] = field(default_factory=tuple)


def make_personal_investment_profile(account, actor, now, risk_tolerance="moderate", constraints=()):
    oid = stable_id("PIP", account, risk_tolerance)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=())
    return PersonalInvestmentProfile(
        id=oid,
        version=1,
        provenance=prov,
        account=account,
        risk_tolerance=risk_tolerance,
        constraints=tuple(constraints),
    )
