from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import unittest

from eios_core.canonical_objects import Observation
from eios_core.provenance import Provenance
from reality_intelligence.intelligence_assessment import make_intelligence_assessment
from genesis.opportunity_hypothesis import make_opportunity_hypothesis
from prometheus.investment_thesis import make_investment_thesis
from prometheus.investment_action import make_investment_action
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.personalized_action import make_personalized_action
from execution_manual.manual_trade_ticket import create_or_get_ticket
from execution_manual.execution_checklist import Thresholds, revalidate


def _ticket(now=0, price=10.0):
    obs = Observation(id="OBS-1", provenance=Provenance(created_at="t", actor="t"))
    ia = make_intelligence_assessment([obs], "IREN", "a", actor="t", now=0)
    oph = make_opportunity_hypothesis(ia, "IREN", "h", actor="t", now=0)
    thesis = make_investment_thesis(oph, "IREN", 2000.0, actor="t", now=0)
    action = make_investment_action(thesis, "enter", actor="t", now=0)
    profile = make_personal_investment_profile("ACCT", actor="t", now=0)
    psa = make_personalized_action(action, profile, actor="t", now=0)
    params = {"order_type": "limit", "limit_price": price, "venue": "IBKR", "price": price}
    return create_or_get_ticket({}, action, psa, params, now=now)


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
