from __future__ import annotations

import os as _os, sys as _sys
_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import glob
import unittest

from execution_manual.manual_execution_intent import (
    ManualExecutionIntent,
    make_manual_execution_intent,
)
from execution_manual.manual_trade_ticket import create_or_get_ticket
from prometheus.investment_action import InvestmentAction
from personal_cio.personalized_action import PersonalizedAction
from runtime.vertical_slice_runner import run_iren_slice
from _real_chain import real_chain, real_intent

NOW = 1_700_000_000.0
PARAMS = {"order_type": "limit", "limit_price": 10.0, "venue": "IBKR", "price": 10.0}


def _personalized(now=NOW):
    return real_chain(now=now)["personalized"]


class TestManualExecutionIntent(unittest.TestCase):
    # --- validation ---------------------------------------------------------
    def test_manual_execution_intent_requires_personalized_action(self):
        with self.assertRaises(ValueError):
            make_manual_execution_intent(
                None, selected_instrument="IREN",
                user_selected_allocation_amount=2000.0,
                execution_side="open_candidate", now=NOW,
            )
        with self.assertRaises(ValueError):
            make_manual_execution_intent(
                object(), selected_instrument="IREN",
                user_selected_allocation_amount=2000.0,
                execution_side="open_candidate", now=NOW,
            )

    def test_manual_execution_intent_requires_explicit_user_selected_size(self):
        p = _personalized()
        for bad in (None, 0.0, -50.0):
            with self.assertRaises(ValueError):
                make_manual_execution_intent(
                    p, selected_instrument="IREN",
                    user_selected_allocation_amount=bad,
                    execution_side="open_candidate", now=NOW,
                )

    def test_invalid_execution_side_rejected(self):
        p = _personalized()
        with self.assertRaises(ValueError):
            make_manual_execution_intent(
                p, selected_instrument="IREN",
                user_selected_allocation_amount=2000.0,
                execution_side="buy", now=NOW,
            )

    # --- the cognition/actuation boundary on SIZE ---------------------------
    def test_saarathi_recommends_range_but_does_not_choose_exact_size(self):
        fields = set(PersonalizedAction.__dataclass_fields__.keys())
        # Saarathi carries only range guidance...
        self.assertIn("suggested_sizing_range_pct", fields)
        self.assertIn("recommended_max_exposure_pct", fields)
        # ...and NO exact size field of any kind.
        for bad in ("user_selected_allocation_amount", "intended_allocation",
                    "allocation", "exact_shares", "dollar_amount", "quantity"):
            self.assertNotIn(bad, fields)

    def test_chosen_size_lives_only_in_execution_intent(self):
        intent = real_intent(user_selected_allocation_amount=2000.0)
        self.assertEqual(intent.user_selected_allocation_amount, 2000.0)
        # The chosen size exists ONLY on the intent, not upstream.
        self.assertNotIn("user_selected_allocation_amount",
                         InvestmentAction.__dataclass_fields__)
        self.assertNotIn("user_selected_allocation_amount",
                         PersonalizedAction.__dataclass_fields__)

    def test_investment_action_has_no_allocation_or_execution_fields(self):
        fields = set(InvestmentAction.__dataclass_fields__.keys())
        for bad in ("intended_allocation", "allocation", "position_size",
                    "user_selected_allocation_amount", "side", "quantity",
                    "order_type", "limit_price", "broker_order_id"):
            self.assertNotIn(bad, fields)

    def test_personalized_action_has_no_exact_allocation_or_order_fields(self):
        fields = set(PersonalizedAction.__dataclass_fields__.keys())
        for bad in ("intended_allocation", "allocation", "user_selected_allocation_amount",
                    "exact_shares", "dollar_amount", "quantity", "side", "order_type",
                    "limit_price", "broker_order_id"):
            self.assertNotIn(bad, fields)

    # --- the intent is NOT a broker order -----------------------------------
    def test_execution_intent_is_not_broker_order(self):
        fields = set(ManualExecutionIntent.__dataclass_fields__.keys())
        for bad in ("broker_order_id", "order_type", "limit_price", "stop_price", "venue"):
            self.assertNotIn(bad, fields)

    def test_execution_intent_requires_user_confirmation(self):
        intent = real_intent()
        self.assertTrue(intent.user_confirmation_required)

    def test_execution_intent_requires_stale_check(self):
        intent = real_intent()
        self.assertTrue(intent.stale_check_required)
        self.assertTrue(intent.preview_required)

    # --- Kriya consumes the intent and does NO reasoning --------------------
    def test_kriya_consumes_execution_intent_without_reasoning(self):
        intent = real_intent()
        ticket = create_or_get_ticket({}, intent, PARAMS, now=0)
        # Kriya builds an operational ticket straight from the intent.
        self.assertEqual(ticket.instrument, "IREN")
        self.assertEqual(ticket.side, "buy")
        self.assertEqual(ticket.intended_allocation, 2000.0)
        # No execution_manual module imports any reasoning layer.
        forbidden = ("reality_intelligence", "genesis", "prometheus", "personal_cio")
        exec_dir = _os.path.join(_SRC, "execution_manual")
        for path in glob.glob(_os.path.join(exec_dir, "*.py")):
            with open(path) as fh:
                src = fh.read()
            for layer in forbidden:
                self.assertNotIn("import " + layer, src,
                                 msg="{0} imports reasoning layer {1}".format(path, layer))
                self.assertNotIn("from " + layer, src,
                                 msg="{0} imports reasoning layer {1}".format(path, layer))

    def test_kriya_creates_manual_ticket_preview_only(self):
        intent = real_intent()
        ticket = create_or_get_ticket({}, intent, PARAMS, now=0)
        # A preview only -- never placed, no broker order recorded.
        self.assertEqual(ticket.state, "previewed")
        self.assertIsNone(ticket.broker_order_id)
        self.assertIsNone(ticket.placed_at)
        self.assertEqual(ticket.quantity, 200)  # 2000 / 10.0

    def test_no_broker_submission_added(self):
        # No broker adapter / network submission anywhere in the execution layer.
        forbidden = ("import requests", "import urllib", "import http",
                     "import socket", "submit_order", "place_order_api")
        exec_dir = _os.path.join(_SRC, "execution_manual")
        for path in glob.glob(_os.path.join(exec_dir, "*.py")):
            with open(path) as fh:
                src = fh.read()
            for token in forbidden:
                self.assertNotIn(token, src,
                                 msg="{0} contains {1!r}".format(path, token))

    # --- provenance ---------------------------------------------------------
    def test_provenance_preserved_to_execution_intent(self):
        c = real_chain()
        action, thesis = c["action"], c["thesis"]
        personalized = c["personalized"]
        intent = make_manual_execution_intent(
            personalized, selected_instrument="IREN",
            user_selected_allocation_amount=2000.0,
            execution_side="open_candidate", now=NOW,
        )
        # The intent binds the personalized action by (id, version)...
        ref = next(r for r in intent.provenance.sources
                   if r.object_id == personalized.id)
        self.assertEqual(ref.version, personalized.version)
        self.assertEqual(ref.kind, "PersonalizedAction")
        # ...and carries the chain back to action / thesis / observations.
        self.assertEqual(intent.source_personalized_action_id, personalized.id)
        self.assertEqual(intent.source_action_id, action.id)
        self.assertEqual(intent.source_thesis_id, thesis.id)
        self.assertEqual(set(intent.upstream_observation_ids),
                         set(personalized.upstream_observation_ids))
        self.assertTrue(intent.upstream_observation_ids)

    # --- slice integration --------------------------------------------------
    def test_vertical_slice_iren_threads_personalized_action_to_manual_execution_intent(self):
        r = run_iren_slice()
        self.assertIsInstance(r.execution_intent, ManualExecutionIntent)
        # Threaded downstream of the PersonalizedAction...
        self.assertEqual(r.execution_intent.source_personalized_action_id,
                         r.personalized_action.id)
        self.assertEqual(r.execution_intent.source_action_id, r.action.id)
        self.assertIn(r.personalized_action.id,
                      {ref.object_id for ref in r.execution_intent.provenance.sources})
        # ...carrying the user's explicit chosen size, and the ticket previews it.
        self.assertEqual(r.execution_intent.user_selected_allocation_amount, 2000.0)
        self.assertEqual(r.execution_intent.selected_instrument, "IREN")
        self.assertEqual(r.ticket_preview1.quantity, 200)


if __name__ == "__main__":
    unittest.main()
