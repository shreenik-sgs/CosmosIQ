"""Position Reconciliation -- full-chain reconciliation (EXEC-002 AR-2012/2013).

Walks the nine links from intended action to recorded outcome, marking each
``reconciled`` or ``divergent``. Links 4-5 are matched by ``broker_order_id``;
link 8 compares actual capital deployed against ``intended_allocation``.
Reconciliation is the authority that converts recorded action into trusted state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from .fill_record import aggregate


@dataclass(frozen=True)
class LinkResult:
    index: int
    name: str
    status: str  # "reconciled" | "divergent"
    detail: str = ""

    @property
    def reconciled(self) -> bool:
        return self.status == "reconciled"


@dataclass(frozen=True)
class ReconciliationResult:
    links: Tuple[LinkResult, ...] = field(default_factory=tuple)

    @property
    def all_reconciled(self) -> bool:
        return all(link.reconciled for link in self.links)

    def divergences(self):
        return tuple(link for link in self.links if not link.reconciled)


def _link(index, name, ok, detail=""):
    return LinkResult(index, name, "reconciled" if ok else "divergent", detail)


def reconcile(ticket, fills, broker_record, expected) -> ReconciliationResult:
    """Walk the reconciliation chain.

    ``broker_record``: ``{broker_order_id, acknowledged, filled_quantity}``.
    ``expected``: ``{position_quantity, outcome_recorded, capital_tolerance?}``.
    """
    agg = aggregate(fills, expected.get("position_quantity", ticket.quantity))
    actual_capital = sum(f.quantity * f.price for f in fills)
    broker_oid = broker_record.get("broker_order_id")

    # Tolerance for intended vs actual capital: whole-share rounding means up to
    # roughly one share of deviation is expected. Default to one share's price.
    if "capital_tolerance" in expected:
        capital_tol = expected["capital_tolerance"]
    elif fills:
        capital_tol = max(f.price for f in fills)
    else:
        capital_tol = 0.0

    links = []

    # 1. intended action <-> Order Intent (the ticket).
    links.append(_link(1, "intended_action_to_ticket", bool(ticket.investment_action_id)))

    # 2. Order Intent <-> Order Preview (parameters unchanged / preview exists).
    links.append(_link(2, "ticket_to_preview", bool(ticket.preview_hash)))

    # 3. Order Preview <-> User Confirmation (bound).
    links.append(
        _link(
            3,
            "preview_to_confirmation",
            ticket.confirmation is not None and ticket.confirmation == ticket.preview_hash,
        )
    )

    # 4. User Confirmation <-> what the user placed (broker_order_id).
    links.append(
        _link(
            4,
            "confirmation_to_placed",
            ticket.broker_order_id is not None and ticket.broker_order_id == broker_oid,
            "broker_order_id={0}".format(ticket.broker_order_id),
        )
    )

    # 5. what the user placed <-> broker acknowledgment / record.
    links.append(
        _link(
            5,
            "placed_to_broker_record",
            bool(broker_record.get("acknowledged"))
            and broker_oid == ticket.broker_order_id,
        )
    )

    # 6. broker acknowledgment <-> fills recorded.
    broker_filled = broker_record.get("filled_quantity", agg.cumulative_filled)
    links.append(
        _link(6, "broker_to_fills", broker_filled == agg.cumulative_filled)
    )

    # 7. fills <-> resulting position.
    links.append(
        _link(
            7,
            "fills_to_position",
            agg.cumulative_filled == expected.get("position_quantity", agg.cumulative_filled),
        )
    )

    # 8. resulting position <-> expected -- actual capital vs intended_allocation.
    capital_gap = abs(actual_capital - ticket.intended_allocation)
    links.append(
        _link(
            8,
            "capital_to_intended_allocation",
            capital_gap <= capital_tol,
            "intended={0} actual={1:.2f} gap={2:.2f} tol={3:.2f}".format(
                ticket.intended_allocation, actual_capital, capital_gap, capital_tol
            ),
        )
    )

    # 9. execution outcome <-> CIO / Prometheus records.
    links.append(
        _link(9, "outcome_to_records", bool(expected.get("outcome_recorded", True)))
    )

    return ReconciliationResult(links=tuple(links))
