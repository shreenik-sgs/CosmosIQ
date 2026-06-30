"""Prometheus -- Position State as a DERIVED view (PROM-002).

Position State is never stored on the ticket; it is computed from the actions
(intent + side) and the fills (reality). This is a pure function.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionState:
    instrument: str
    quantity: int
    average_price: float
    status: str  # "open" | "flat"


def position_state(actions, fills) -> PositionState:
    """Derive the current position from actions and recorded fills.

    Buy-side actions add to the position, sell-side actions reduce it. The fills
    supply the realised quantities and prices.
    """
    instrument = ""
    side = "buy"
    if actions:
        instrument = getattr(actions[0], "instrument", "")
        side = getattr(actions[0], "side", "buy")
    elif fills:
        instrument = ""

    signed_qty = 0
    cost = 0.0
    filled = 0
    for f in fills:
        sign = 1 if side == "buy" else -1
        signed_qty += sign * f.quantity
        cost += f.quantity * f.price
        filled += f.quantity

    avg = (cost / filled) if filled else 0.0
    status = "open" if signed_qty != 0 else "flat"
    return PositionState(
        instrument=instrument,
        quantity=signed_qty,
        average_price=round(avg, 6),
        status=status,
    )
