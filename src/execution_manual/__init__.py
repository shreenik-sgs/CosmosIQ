"""Manual execution layer -- the gated, auditable actuation passage (ADR-0010)."""

from __future__ import annotations

from .manual_trade_ticket import (
    ManualTradeTicket,
    STATES,
    compute_preview_hash,
    preview_params_of,
    derive_quantity,
    create_or_get_ticket,
    re_preview,
)
from .execution_checklist import (
    Thresholds,
    Result,
    revalidate,
    confirm,
    place_order,
    mark_recorded,
    mark_reconciled,
)
from .fill_record import Fill, FillAggregate, make_fill, aggregate
from .reconciliation import LinkResult, ReconciliationResult, reconcile
from .audit_trail import AuditEntry, AuditTrail, ReplayState, EVENT_TYPES

__all__ = [
    "ManualTradeTicket",
    "STATES",
    "compute_preview_hash",
    "preview_params_of",
    "derive_quantity",
    "create_or_get_ticket",
    "re_preview",
    "Thresholds",
    "Result",
    "revalidate",
    "confirm",
    "place_order",
    "mark_recorded",
    "mark_reconciled",
    "Fill",
    "FillAggregate",
    "make_fill",
    "aggregate",
    "LinkResult",
    "ReconciliationResult",
    "reconcile",
    "AuditEntry",
    "AuditTrail",
    "ReplayState",
    "EVENT_TYPES",
]
