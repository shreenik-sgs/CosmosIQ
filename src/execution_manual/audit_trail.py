"""Execution Audit Trail -- append-only log + deterministic replay.

The trail is sufficient to reconstruct any ticket and the whole session exactly.
The cardinal rule (EXEC-002 AR-2003/2024): **replay reconstructs, it never
re-actuates.** ``replay()`` reads entries and rebuilds state; it places no
orders, makes no calls, and creates no duplicate ticket. It is pure and
idempotent -- calling it twice yields identical state and has no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from eios_core.ids import stable_id

# Event types (execution_audit_trail_schema.md).
EVENT_TYPES = frozenset(
    {
        "queue_item_presented",
        "ticket_created",
        "previewed",
        "stale_detected",
        "returned_to_preview",
        "checklist_completed",
        "confirmed",
        "placed_by_user",
        "fill_recorded",
        "partial_fill",
        "expired",
        "cancelled",
        "rejected",
        "cancel_requested",
        "replace_requested",
        "indeterminate_marked",
        "reconciled",
        "divergence_found",
        "disabled",
        "override",
        "emergency_invoked",
    }
)


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    timestamp: float
    ticket_id: str
    event_type: str
    actor: str
    payload: Dict[str, Any] = field(default_factory=dict)
    grounding_versions: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayState:
    """The reconstructed end state of a replayed session."""

    tickets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    fills: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def __eq__(self, other):
        return (
            isinstance(other, ReplayState)
            and self.tickets == other.tickets
            and self.fills == other.fills
        )


class AuditTrail:
    """Append-only audit log. Entries are never edited or deleted."""

    def __init__(self):
        self._entries: List[AuditEntry] = []

    @property
    def entries(self) -> Tuple[AuditEntry, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, timestamp, ticket_id, event_type, actor, payload=None, grounding_versions=None) -> AuditEntry:
        index = len(self._entries)
        entry_id = stable_id("AUD", str(index), event_type, ticket_id or "", str(timestamp))
        entry = AuditEntry(
            entry_id=entry_id,
            timestamp=float(timestamp),
            ticket_id=ticket_id or "",
            event_type=event_type,
            actor=actor,
            payload=dict(payload or {}),
            grounding_versions=dict(grounding_versions or {}),
        )
        self._entries.append(entry)
        return entry

    def events_of(self, event_type) -> Tuple[AuditEntry, ...]:
        return tuple(e for e in self._entries if e.event_type == event_type)

    def has_event(self, event_type) -> bool:
        return any(e.event_type == event_type for e in self._entries)

    def replay(self) -> ReplayState:
        """Reconstruct session state from the audit trail.

        PURE: reads entries only. Never re-places an order, never mutates a
        ticket registry, never produces a duplicate ticket. Safe and idempotent
        to call any number of times.
        """
        tickets: Dict[str, Dict[str, Any]] = {}
        fills: List[Dict[str, Any]] = []

        def ensure(tid):
            if tid and tid not in tickets:
                tickets[tid] = {
                    "ticket_id": tid,
                    "state": "draft",
                    "broker_order_id": None,
                    "placed_at": None,
                    "quantity": 0,
                    "preview_hash": "",
                    "confirmation": None,
                }
            return tickets.get(tid)

        for entry in self._entries:
            tid = entry.ticket_id
            payload = entry.payload
            et = entry.event_type

            if et == "queue_item_presented":
                continue

            t = ensure(tid)
            if t is None:
                continue

            if et in ("ticket_created", "previewed", "returned_to_preview"):
                t["state"] = "previewed"
                if "quantity" in payload:
                    t["quantity"] = payload["quantity"]
                if "preview_hash" in payload:
                    t["preview_hash"] = payload["preview_hash"]
                t["confirmation"] = None
            elif et == "stale_detected":
                # observed only; no state change beyond what re-preview records
                pass
            elif et == "confirmed":
                t["state"] = "confirmed"
                t["confirmation"] = payload.get("preview_hash", t["preview_hash"])
            elif et == "placed_by_user":
                # Reconstruct the placement record -- DO NOT re-place anything.
                t["state"] = "placed"
                t["broker_order_id"] = payload.get("broker_order_id")
                t["placed_at"] = payload.get("placed_at")
            elif et in ("fill_recorded", "partial_fill"):
                fills.append(
                    {
                        "ticket_id": tid,
                        "quantity": payload.get("quantity"),
                        "price": payload.get("price"),
                        "time": payload.get("time"),
                    }
                )
                t["state"] = "recorded"
            elif et == "reconciled":
                t["state"] = "reconciled"
            elif et in ("expired", "cancelled", "rejected", "indeterminate_marked"):
                t["state"] = et.replace("_marked", "")

        return ReplayState(tickets=tickets, fills=tuple(fills))
