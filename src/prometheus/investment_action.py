"""Prometheus -- the Investment Action (a typed Decision / reasoning object).

An ``InvestmentAction`` is a Decision: a verdict the system has reached. It is
still cognition (ADR-0010) -- it forms the action but does not carry it out.
The side (buy/sell) is derived from the action_type so Execution does not
re-decide.
"""

from __future__ import annotations

from dataclasses import dataclass

from eios_core.canonical_objects import Decision
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

ACTION_TYPES = frozenset(
    {"enter", "hold", "add", "trim", "exit", "avoid", "wait", "rotate"}
)

# Which action types result in an actual trade (vs a recorded non-action).
TRADE_ACTIONS = frozenset({"enter", "add", "trim", "exit", "rotate"})

_BUY_ACTIONS = frozenset({"enter", "add"})
_SELL_ACTIONS = frozenset({"trim", "exit"})


def side_for_action(action_type: str) -> str:
    """Map an action_type to a trade side. ``rotate`` defaults to buy here."""
    if action_type in _SELL_ACTIONS:
        return "sell"
    return "buy"


@dataclass(frozen=True)
class InvestmentAction(Decision):
    action_type: str = "enter"
    instrument: str = ""
    side: str = "buy"
    intended_allocation: float = 0.0
    timing: str = "now"

    @property
    def is_trade(self) -> bool:
        return self.action_type in TRADE_ACTIONS


def make_investment_action(thesis, action_type, actor, now):
    if action_type not in ACTION_TYPES:
        raise ValueError("unknown action_type: {0}".format(action_type))
    sources = (thesis.ref("InvestmentThesis"),)
    oid = stable_id("IAC", thesis.id, action_type)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return InvestmentAction(
        id=oid,
        version=1,
        provenance=prov,
        content="{0} {1}".format(action_type, thesis.instrument),
        action_type=action_type,
        instrument=thesis.instrument,
        side=side_for_action(action_type),
        intended_allocation=thesis.intended_allocation,
        timing=thesis.timing,
    )
