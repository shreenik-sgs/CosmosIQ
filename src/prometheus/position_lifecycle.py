"""Prometheus -- Position lifecycle: the holding CONTEXT an Investment Action
reads, and the DERIVED position view (PROM-002).

``PositionContext`` is the (hand-fed, MVP) statement of whether a holding already
exists for the thesis, what lifecycle state it is in, whether an invalidation has
triggered, and which way the thesis is trending. The Investment Action layer reads
it to decide add / trim / exit / rotate vs a fresh entry candidate. The MVP
DEFAULT is no context -> no holdings assumed; the layer never invents user
holdings.

``PositionState`` is never stored on the ticket; it is computed from the actions
(intent + side) and the fills (reality). This is a pure function.
"""

from __future__ import annotations

from dataclasses import dataclass

# The lifecycle states an Investment Action / holding can occupy.
LIFECYCLE_STATES = frozenset({
    "no_position_candidate",
    "thesis_monitoring",
    "thesis_worthy_waiting_for_timing",
    "timing_confirmed_candidate",
    "active_position_monitoring",
    "add_candidate",
    "trim_candidate",
    "exit_candidate",
    "rotate_candidate",
    "invalidated",
    "avoided",
})

# Which way the thesis behind a holding is trending.
THESIS_DIRECTIONS = frozenset({"improving", "stable", "deteriorating"})


@dataclass(frozen=True)
class PositionContext:
    """Whether a holding exists for a thesis and how it is trending.

    Hand-fed for the MVP. The default -- no position, not invalidated, stable --
    means "no holdings assumed", so the Investment Action layer can only produce a
    fresh entry candidate / wait / monitor / avoid, never add / trim / exit /
    rotate (which all require an existing holding).
    """

    has_position: bool = False
    current_state: str = ""
    invalidation_triggered: bool = False
    thesis_direction: str = "stable"  # improving | stable | deteriorating


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
