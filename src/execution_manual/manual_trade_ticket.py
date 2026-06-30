"""Manual Trade Ticket -- the Order (the ONLY operational object, ADR-0010).

The ticket is the manual instance of the Order: its pre-actuation form (Order
Intent + Order Preview) plus the placement record the user fills in when they
place the trade in their broker platform. No broker adapter, no automated
submission -- "placing the trade" is recording ``broker_order_id`` + ``placed_at``.

Idempotency (EXEC-002 AR-2001/2002): the ticket id is
``stable_id("TKT", investment_action_id, investment_action_version)``, so the
same (Investment Action, version) always resolves to the SAME ticket -- created
at most once.

The ticket is a frozen dataclass; every state transition produces a new value
via ``dataclasses.replace`` with a bumped version, never an in-place edit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Optional, Dict

from eios_core.canonical_objects import OperationalObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.versioning import bump
from eios_core.provenance import make_provenance

# Ticket lifecycle states (manual_trade_ticket_schema.md).
STATES = frozenset(
    {
        "draft",
        "previewed",
        "confirmed",
        "placed",
        "recorded",
        "reconciled",
        "expired",
        "cancelled",
        "rejected",
        "indeterminate",
    }
)

# The order parameters whose change invalidates a preview/confirmation
# (EXEC-002 AR-2009). preview_hash is computed over exactly these.
PREVIEW_PARAM_FIELDS = (
    "instrument",
    "side",
    "quantity",
    "order_type",
    "limit_price",
    "stop_price",
    "time_in_force",
    "account",
    "estimated_cost",
    "venue",
)


@dataclass(frozen=True)
class ManualTradeTicket(OperationalObject):
    # grounding / identity
    queue_item_id: str = ""
    investment_action_id: str = ""
    investment_action_version: int = 1
    cio_decision_record_id: str = ""
    # order parameters (the previewed order)
    action_type: str = ""
    instrument: str = ""
    side: str = ""
    quantity: int = 0
    order_type: str = "market"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "day"
    account: str = ""
    estimated_cost: float = 0.0
    intended_allocation: float = 0.0
    venue: str = ""
    risk_warning: str = ""
    # preview & confirmation binding
    preview_hash: str = ""
    preview_timestamp: Optional[float] = None
    confirmation: Optional[str] = None
    # placement (recorded when the user places the order)
    broker_order_id: Optional[str] = None
    placed_at: Optional[float] = None
    # state
    state: str = "draft"

    @property
    def ticket_id(self) -> str:
        return self.id

    @property
    def preview_price(self) -> float:
        """The price implied by the preview (estimated_cost / quantity)."""
        if self.quantity:
            return self.estimated_cost / self.quantity
        return 0.0


def compute_preview_hash(params: Dict) -> str:
    """Deterministic hash over the order parameters shown to the user.

    Only ``PREVIEW_PARAM_FIELDS`` participate; any change to one of them yields a
    different hash and thus invalidates a prior confirmation.
    """
    items = []
    for key in PREVIEW_PARAM_FIELDS:
        items.append((key, params.get(key)))
    payload = repr(sorted(items, key=lambda kv: kv[0]))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def preview_params_of(ticket: ManualTradeTicket) -> Dict:
    """Extract the current preview parameters from a ticket."""
    return {field: getattr(ticket, field) for field in PREVIEW_PARAM_FIELDS}


def derive_quantity(intended_allocation: float, price: float, lot: int = 1) -> int:
    """Derive whole-share quantity so deployed capital approximates the
    intended allocation, rounded down to the lot size.
    """
    if price <= 0 or lot <= 0:
        return 0
    units = int((intended_allocation / price) // lot)
    return units * lot


def _build_preview(ticket: ManualTradeTicket, price: float, now: float, lot: int) -> ManualTradeTicket:
    """(Re)compute quantity, estimated cost, preview hash, and timestamp for a
    ticket at a given price/time. Clears any prior confirmation.
    """
    quantity = derive_quantity(ticket.intended_allocation, price, lot)
    estimated_cost = round(quantity * price, 6)
    previewed = replace(
        ticket,
        quantity=quantity,
        estimated_cost=estimated_cost,
        confirmation=None,
        state="previewed",
        preview_timestamp=float(now),
    )
    phash = compute_preview_hash(preview_params_of(previewed))
    return replace(previewed, preview_hash=phash)


def create_or_get_ticket(registry, investment_action, personalized_action, params, now, lot=1):
    """Create the ticket for an Investment Action, or return the existing one.

    Idempotent (EXEC-002 AR-2001): keyed by ``stable_id("TKT", ia_id, ia_version)``
    in ``registry``. A repeat request resolves to the same ticket, never a
    duplicate.

    ``params`` carries the externally-supplied order parameters:
    ``order_type``, ``limit_price``, ``stop_price``, ``time_in_force``,
    ``venue``, ``price`` (the live preview price), and optional
    ``queue_item_id`` / ``risk_warning``.
    """
    ticket_id = stable_id(
        "TKT", investment_action.id, investment_action.version
    )
    if ticket_id in registry:
        return registry[ticket_id]

    price = float(params["price"])
    sources = (
        investment_action.ref("InvestmentAction"),
        personalized_action.ref("PersonalizedAction"),
    )
    prov = make_provenance(
        actor=params.get("actor", "user"),
        created_at=iso_from_epoch(now),
        sources=sources,
    )
    draft = ManualTradeTicket(
        id=ticket_id,
        version=1,
        provenance=prov,
        queue_item_id=params.get("queue_item_id", ""),
        investment_action_id=investment_action.id,
        investment_action_version=investment_action.version,
        cio_decision_record_id=getattr(personalized_action, "cio_decision_record_id", ""),
        action_type=investment_action.action_type,
        instrument=investment_action.instrument,
        side=investment_action.side,
        order_type=params.get("order_type", "market"),
        limit_price=params.get("limit_price"),
        stop_price=params.get("stop_price"),
        time_in_force=params.get("time_in_force", "day"),
        account=personalized_action.account,
        intended_allocation=personalized_action.intended_allocation,
        venue=params.get("venue", ""),
        risk_warning=params.get("risk_warning", ""),
        state="draft",
    )
    previewed = _build_preview(draft, price, now, lot)
    registry[ticket_id] = previewed
    return previewed


def re_preview(registry, ticket, price, now, lot=1, limit_price=None):
    """Regenerate the preview at a new price/time (same ticket id, bumped
    version). Clears the prior confirmation and updates the registry.
    """
    base = ticket
    if limit_price is not None:
        base = replace(base, limit_price=limit_price)
    repriced = _build_preview(base, price, now, lot)
    repriced = replace(repriced, version=bump(ticket.version))
    registry[repriced.id] = repriced
    return repriced
