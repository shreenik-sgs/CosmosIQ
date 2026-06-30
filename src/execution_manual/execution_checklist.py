"""Manual Execution Checklist -- the Actuation Gate, performed by the user.

This is the sole path to a trade (EXEC-002 AR-2011). ``revalidate`` runs the
pre-placement checks; if anything material changed the ticket returns to preview
rather than placement (AR-2008). ``confirm`` binds a confirmation to a preview
hash only if it still matches (AR-2009/2010). ``place_order`` records the manual
placement (broker_order_id + placed_at).
"""

from __future__ import annotations

from dataclasses import dataclass, replace, field
from typing import Tuple, Optional

from eios_core.versioning import bump
from .manual_trade_ticket import (
    ManualTradeTicket,
    compute_preview_hash,
    preview_params_of,
)

# Defaults from manual_execution_checklist.md.
DEFAULT_PREVIEW_TTL = 120.0          # seconds
DEFAULT_MARKET_MOVE_TOLERANCE = 0.005  # 0.5%

_PLACED_STATES = frozenset({"placed", "recorded", "reconciled"})


@dataclass(frozen=True)
class Thresholds:
    preview_ttl: float = DEFAULT_PREVIEW_TTL
    market_move_tolerance: float = DEFAULT_MARKET_MOVE_TOLERANCE


@dataclass(frozen=True)
class Result:
    status: str  # "ok" | "return_to_preview"
    reasons: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _ok() -> Result:
    return Result(status="ok", reasons=())


def _return_to_preview(reasons) -> Result:
    return Result(status="return_to_preview", reasons=tuple(reasons))


def revalidate(ticket: ManualTradeTicket, now, current_price, ctx=None, thresholds=None) -> Result:
    """Run the pre-placement checklist.

    Returns ``Result(status="ok")`` only if every gate passes; otherwise
    ``Result(status="return_to_preview", reasons=[...])``.

    ``ctx`` supplies the operational facts the gate validates (it does NOT
    re-decide the investment): ``action_current``, ``account_ok``, ``tradable``,
    ``market_open``, ``execution_enabled``.
    """
    ctx = ctx or {}
    thresholds = thresholds or Thresholds()
    reasons = []

    # 1. Idempotency -- not already placed.
    if ticket.state in _PLACED_STATES or ticket.broker_order_id is not None:
        reasons.append("already_placed")

    # 2. Action current.
    if not ctx.get("action_current", True):
        reasons.append("action_not_current")

    # 3. Preview fresh.
    if ticket.preview_timestamp is None:
        reasons.append("no_preview")
    elif (float(now) - float(ticket.preview_timestamp)) > thresholds.preview_ttl:
        reasons.append("preview_stale")

    # 4. Confirmation binds preview -- order params unchanged since preview.
    recomputed = compute_preview_hash(preview_params_of(ticket))
    if recomputed != ticket.preview_hash:
        reasons.append("preview_params_changed")
    if ticket.confirmation is not None and ticket.confirmation != ticket.preview_hash:
        reasons.append("confirmation_unbound")

    # 5. Market moved?
    preview_price = ticket.preview_price
    if preview_price <= 0:
        reasons.append("no_preview_price")
    else:
        move = abs(float(current_price) - preview_price) / preview_price
        if move > thresholds.market_move_tolerance:
            reasons.append("market_moved")

    # 6. Account checks.
    if not ctx.get("account_ok", True):
        reasons.append("account_insufficient")

    # 7. Instrument tradable.
    if not ctx.get("tradable", True):
        reasons.append("instrument_not_tradable")

    # 8. Market hours.
    if not ctx.get("market_open", True):
        reasons.append("market_closed")

    # 9. Not disabled (kill switch).
    if not ctx.get("execution_enabled", True):
        reasons.append("execution_disabled")

    if reasons:
        return _return_to_preview(reasons)
    return _ok()


def confirm(ticket: ManualTradeTicket, preview_hash: str) -> ManualTradeTicket:
    """Bind a confirmation to a preview. Succeeds only if ``preview_hash``
    matches the ticket's current ``preview_hash`` (EXEC-002 AR-2009/2010);
    otherwise the confirmation is rejected.
    """
    if preview_hash != ticket.preview_hash:
        raise ValueError("confirmation rejected: preview hash does not bind")
    return replace(
        ticket,
        confirmation=preview_hash,
        state="confirmed",
        version=bump(ticket.version),
    )


def place_order(registry, ticket: ManualTradeTicket, broker_order_id: str, placed_at) -> ManualTradeTicket:
    """Record that the user placed the order manually in their broker platform.

    This is the only "actuation": it records facts (broker_order_id, placed_at),
    it does not submit anything. Requires a confirmed ticket.
    """
    if ticket.state != "confirmed" or ticket.confirmation is None:
        raise ValueError("cannot place: ticket is not confirmed")
    placed = replace(
        ticket,
        broker_order_id=broker_order_id,
        placed_at=float(placed_at),
        state="placed",
        version=bump(ticket.version),
    )
    registry[placed.id] = placed
    return placed


def mark_recorded(registry, ticket: ManualTradeTicket) -> ManualTradeTicket:
    updated = replace(ticket, state="recorded", version=bump(ticket.version))
    registry[updated.id] = updated
    return updated


def mark_reconciled(registry, ticket: ManualTradeTicket) -> ManualTradeTicket:
    updated = replace(ticket, state="reconciled", version=bump(ticket.version))
    registry[updated.id] = updated
    return updated
