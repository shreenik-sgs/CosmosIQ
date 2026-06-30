from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import dataclasses
import unittest

from eios_core.canonical_objects import Observation
from eios_core.provenance import Provenance
from reality_intelligence.intelligence_assessment import make_intelligence_assessment
from genesis.opportunity_hypothesis import make_opportunity_hypothesis
from prometheus.investment_thesis import make_investment_thesis
from prometheus.investment_action import make_manual_execution_intent
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.personalized_action import make_personalized_action
from execution_manual.manual_trade_ticket import create_or_get_ticket


def _action_and_psa():
    obs = Observation(id="OBS-1", provenance=Provenance(created_at="t", actor="t"))
    ia = make_intelligence_assessment([obs], "IREN", "a", actor="t", now=0)
    oph = make_opportunity_hypothesis(ia, "IREN", "h", actor="t", now=0)
    thesis = make_investment_thesis(oph, "IREN", 2000.0, actor="t", now=0)
    action = make_manual_execution_intent(
        thesis, instrument="IREN", intended_allocation=2000.0,
        side="buy", action_type="enter", timing="now", actor="t", now=0)
    profile = make_personal_investment_profile("ACCT", actor="t", now=0)
    psa = make_personalized_action(action, profile, actor="t", now=0)
    return action, psa


class TestManualTicketIdempotency(unittest.TestCase):
    def setUp(self):
        self.action, self.psa = _action_and_psa()
        self.params = {"order_type": "limit", "limit_price": 10.0, "venue": "IBKR", "price": 10.0}

    def test_same_action_version_yields_same_ticket(self):
        registry = {}
        t1 = create_or_get_ticket(registry, self.action, self.psa, self.params, now=0)
        t2 = create_or_get_ticket(registry, self.action, self.psa, self.params, now=999)
        self.assertEqual(t1.id, t2.id)
        self.assertIs(t1, t2)  # the exact same stored ticket, not a duplicate
        self.assertEqual(len(registry), 1)

    def test_ticket_id_is_derived_from_action_id_and_version(self):
        from eios_core.ids import stable_id

        registry = {}
        ticket = create_or_get_ticket(registry, self.action, self.psa, self.params, now=0)
        expected = stable_id("TKT", self.action.id, self.action.version)
        self.assertEqual(ticket.id, expected)

    def test_new_action_version_yields_new_ticket(self):
        registry = {}
        t1 = create_or_get_ticket(registry, self.action, self.psa, self.params, now=0)
        action_v2 = dataclasses.replace(self.action, version=2)
        t2 = create_or_get_ticket(registry, action_v2, self.psa, self.params, now=0)
        self.assertNotEqual(t1.id, t2.id)
        self.assertEqual(len(registry), 2)


if __name__ == "__main__":
    unittest.main()
