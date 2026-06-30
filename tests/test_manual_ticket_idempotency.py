from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import dataclasses
import unittest

from execution_manual.manual_trade_ticket import create_or_get_ticket
from _real_chain import real_adapter


class TestManualTicketIdempotency(unittest.TestCase):
    def setUp(self):
        # The single labelled Kriya adapter is passed as BOTH the action and the
        # personalized args (its ref(kind) serves both).
        self.adapter = real_adapter()
        self.params = {"order_type": "limit", "limit_price": 10.0, "venue": "IBKR", "price": 10.0}

    def test_same_action_version_yields_same_ticket(self):
        registry = {}
        t1 = create_or_get_ticket(registry, self.adapter, self.adapter, self.params, now=0)
        t2 = create_or_get_ticket(registry, self.adapter, self.adapter, self.params, now=999)
        self.assertEqual(t1.id, t2.id)
        self.assertIs(t1, t2)  # the exact same stored ticket, not a duplicate
        self.assertEqual(len(registry), 1)

    def test_ticket_id_is_derived_from_action_id_and_version(self):
        from eios_core.ids import stable_id

        registry = {}
        ticket = create_or_get_ticket(registry, self.adapter, self.adapter, self.params, now=0)
        expected = stable_id("TKT", self.adapter.id, self.adapter.version)
        self.assertEqual(ticket.id, expected)

    def test_new_action_version_yields_new_ticket(self):
        registry = {}
        t1 = create_or_get_ticket(registry, self.adapter, self.adapter, self.params, now=0)
        adapter_v2 = dataclasses.replace(self.adapter, version=2)
        t2 = create_or_get_ticket(registry, adapter_v2, adapter_v2, self.params, now=0)
        self.assertNotEqual(t1.id, t2.id)
        self.assertEqual(len(registry), 2)


if __name__ == "__main__":
    unittest.main()
