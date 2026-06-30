from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import dataclasses
import unittest

from execution_manual.manual_trade_ticket import create_or_get_ticket
from _real_chain import real_intent


class TestManualTicketIdempotency(unittest.TestCase):
    def setUp(self):
        # The single ManualExecutionIntent (the user's chosen size) is the proper
        # Kriya input to create_or_get_ticket.
        self.intent = real_intent()
        self.params = {"order_type": "limit", "limit_price": 10.0, "venue": "IBKR", "price": 10.0}

    def test_same_action_version_yields_same_ticket(self):
        registry = {}
        t1 = create_or_get_ticket(registry, self.intent, self.params, now=0)
        t2 = create_or_get_ticket(registry, self.intent, self.params, now=999)
        self.assertEqual(t1.id, t2.id)
        self.assertIs(t1, t2)  # the exact same stored ticket, not a duplicate
        self.assertEqual(len(registry), 1)

    def test_ticket_id_is_derived_from_action_id_and_version(self):
        from eios_core.ids import stable_id

        registry = {}
        ticket = create_or_get_ticket(registry, self.intent, self.params, now=0)
        expected = stable_id(
            "TKT", self.intent.source_action_id,
            self.intent.source_personalized_action_version,
        )
        self.assertEqual(ticket.id, expected)

    def test_new_action_version_yields_new_ticket(self):
        registry = {}
        t1 = create_or_get_ticket(registry, self.intent, self.params, now=0)
        # A new upstream personalized-action version re-keys the ticket.
        intent_v2 = dataclasses.replace(self.intent, source_personalized_action_version=2)
        t2 = create_or_get_ticket(registry, intent_v2, self.params, now=0)
        self.assertNotEqual(t1.id, t2.id)
        self.assertEqual(len(registry), 2)


if __name__ == "__main__":
    unittest.main()
