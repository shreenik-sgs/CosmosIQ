"""Manual Fill Record -- Fill = Observation (EXEC-001 AR-1911).

Each fill is an Observation of reality (a reasoning object), recorded after the
user places the trade. The aggregate is a DERIVED view, not a stored object
(EXEC-002 AR-2018/2021). Fills flow UP as evidence, never as purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from eios_core.canonical_objects import Observation
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance


@dataclass(frozen=True)
class Fill(Observation):
    ticket_id: str = ""
    quantity: int = 0
    price: float = 0.0
    time: Optional[float] = None
    source: str = "manual"


@dataclass(frozen=True)
class FillAggregate:
    cumulative_filled: int = 0
    remaining_quantity: int = 0
    average_price: float = 0.0
    outcome: str = "working"
    remainder_status: str = "working"


def make_fill(ticket, quantity, price, time, actor="user", source="manual", index=0):
    """Record one fill as an Observation bound to its ticket."""
    sources = (ticket.ref("ManualTradeTicket"),)
    fid = stable_id("FIL", ticket.id, str(index), str(quantity), str(price), str(time))
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(time), sources=sources)
    return Fill(
        id=fid,
        version=1,
        provenance=prov,
        content={"quantity": quantity, "price": price},
        ticket_id=ticket.id,
        quantity=int(quantity),
        price=float(price),
        time=float(time),
        source=source,
    )


def aggregate(fills, intended_quantity, terminal=True) -> FillAggregate:
    """Derive the aggregate view over a sequence of fills.

    ``terminal`` indicates the order's time-in-force has lapsed / the order is
    no longer working, which distinguishes a closed partial (remainder
    cancelled) from one still working.
    """
    cumulative = sum(f.quantity for f in fills)
    remaining = int(intended_quantity) - cumulative
    if cumulative > 0:
        avg = sum(f.quantity * f.price for f in fills) / cumulative
    else:
        avg = 0.0

    if cumulative <= 0:
        outcome = "working"
        remainder_status = "working"
    elif cumulative >= intended_quantity:
        outcome = "filled"
        remainder_status = "none"
    else:
        outcome = "partially_filled"
        remainder_status = "cancelled" if terminal else "working"

    return FillAggregate(
        cumulative_filled=cumulative,
        remaining_quantity=remaining,
        average_price=round(avg, 6),
        outcome=outcome,
        remainder_status=remainder_status,
    )
