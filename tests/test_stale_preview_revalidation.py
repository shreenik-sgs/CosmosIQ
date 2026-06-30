from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import unittest

from execution_manual.manual_trade_ticket import create_or_get_ticket
from execution_manual.execution_checklist import Thresholds, revalidate
from _real_chain import real_adapter


def _ticket(now=0, price=10.0):
    adapter = real_adapter()
    params = {"order_type": "limit", "limit_price": price, "venue": "IBKR", "price": price}
    return create_or_get_ticket({}, adapter, adapter, params, now=now)


class TestStalePreviewRevalidation(unittest.TestCase):
    def setUp(self):
        self.thresholds = Thresholds(preview_ttl=120.0, market_move_tolerance=0.005)
        self.ticket = _ticket(now=0.0, price=10.0)

    def test_fresh_and_within_tolerance_is_ok(self):
        result = revalidate(self.ticket, now=10.0, current_price=10.0, thresholds=self.thresholds)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "ok")

    def test_old_preview_returns_to_preview(self):
        result = revalidate(self.ticket, now=300.0, current_price=10.0, thresholds=self.thresholds)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "return_to_preview")
        self.assertIn("preview_stale", result.reasons)

    def test_market_move_beyond_tolerance_returns_to_preview(self):
        result = revalidate(self.ticket, now=10.0, current_price=10.40, thresholds=self.thresholds)
        self.assertFalse(result.ok)
        self.assertIn("market_moved", result.reasons)

    def test_small_move_within_tolerance_is_ok(self):
        # 0.3% move, under the 0.5% tolerance.
        result = revalidate(self.ticket, now=10.0, current_price=10.03, thresholds=self.thresholds)
        self.assertTrue(result.ok)

    def test_disabled_execution_returns_to_preview(self):
        result = revalidate(
            self.ticket, now=10.0, current_price=10.0,
            ctx={"execution_enabled": False}, thresholds=self.thresholds,
        )
        self.assertFalse(result.ok)
        self.assertIn("execution_disabled", result.reasons)


if __name__ == "__main__":
    unittest.main()
