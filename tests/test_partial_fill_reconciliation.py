from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import unittest

from execution_manual.manual_trade_ticket import create_or_get_ticket
from execution_manual.execution_checklist import confirm, place_order, mark_recorded
from execution_manual.fill_record import make_fill, aggregate
from execution_manual.reconciliation import reconcile
from _real_chain import real_intent


def _placed_ticket(registry, price=10.40):
    intent = real_intent()
    params = {"order_type": "limit", "limit_price": price, "venue": "IBKR", "price": price}
    ticket = create_or_get_ticket(registry, intent, params, now=0)
    confirmed = confirm(ticket, ticket.preview_hash)
    registry[confirmed.id] = confirmed
    return place_order(registry, confirmed, "IBKR-99", placed_at=100.0)


class TestPartialFillReconciliation(unittest.TestCase):
    def test_full_fill_aggregation(self):
        registry = {}
        placed = _placed_ticket(registry)
        self.assertEqual(placed.quantity, 192)
        fills = [
            make_fill(placed, 100, 10.38, time=110.0, index=0),
            make_fill(placed, 92, 10.40, time=120.0, index=1),
        ]
        agg = aggregate(fills, placed.quantity)
        self.assertEqual(agg.cumulative_filled, 192)
        self.assertEqual(agg.remaining_quantity, 0)
        self.assertEqual(agg.outcome, "filled")
        self.assertAlmostEqual(agg.average_price, 10.39, places=2)

    def test_partial_fill_outcome(self):
        registry = {}
        placed = _placed_ticket(registry)
        fills = [make_fill(placed, 100, 10.38, time=110.0, index=0)]
        agg = aggregate(fills, placed.quantity, terminal=True)
        self.assertEqual(agg.outcome, "partially_filled")
        self.assertEqual(agg.remaining_quantity, 92)
        self.assertEqual(agg.remainder_status, "cancelled")

    def test_reconciliation_all_links_pass(self):
        registry = {}
        placed = _placed_ticket(registry)
        fills = [
            make_fill(placed, 100, 10.38, time=110.0, index=0),
            make_fill(placed, 92, 10.40, time=120.0, index=1),
        ]
        recorded = mark_recorded(registry, placed)
        broker_record = {"broker_order_id": "IBKR-99", "acknowledged": True, "filled_quantity": 192}
        expected = {"position_quantity": 192, "outcome_recorded": True}
        result = reconcile(recorded, fills, broker_record, expected)
        self.assertTrue(result.all_reconciled, msg=str(result.divergences()))
        self.assertEqual(len(result.links), 9)

    def test_reconciliation_detects_broker_id_divergence(self):
        registry = {}
        placed = _placed_ticket(registry)
        fills = [make_fill(placed, 192, 10.39, time=110.0, index=0)]
        broker_record = {"broker_order_id": "WRONG-ID", "acknowledged": True, "filled_quantity": 192}
        expected = {"position_quantity": 192, "outcome_recorded": True}
        result = reconcile(placed, fills, broker_record, expected)
        self.assertFalse(result.all_reconciled)
        diverged = {link.name for link in result.divergences()}
        self.assertIn("confirmation_to_placed", diverged)


if __name__ == "__main__":
    unittest.main()
