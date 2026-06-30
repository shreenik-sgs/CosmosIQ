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
from prometheus.investment_action import make_investment_action
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.personalized_action import make_personalized_action
from execution_manual.manual_trade_ticket import (
    create_or_get_ticket,
    compute_preview_hash,
    preview_params_of,
)
from execution_manual.execution_checklist import confirm


def _ticket():
    obs = Observation(id="OBS-1", provenance=Provenance(created_at="t", actor="t"))
    ia = make_intelligence_assessment([obs], "IREN", "a", actor="t", now=0)
    oph = make_opportunity_hypothesis(ia, "IREN", "h", actor="t", now=0)
    thesis = make_investment_thesis(oph, "IREN", 2000.0, actor="t", now=0)
    action = make_investment_action(thesis, "enter", actor="t", now=0)
    profile = make_personal_investment_profile("ACCT", actor="t", now=0)
    psa = make_personalized_action(action, profile, actor="t", now=0)
    params = {"order_type": "limit", "limit_price": 10.0, "venue": "IBKR", "price": 10.0}
    return create_or_get_ticket({}, action, psa, params, now=0)


class TestConfirmationPreviewBinding(unittest.TestCase):
    def test_matching_hash_confirms(self):
        ticket = _ticket()
        confirmed = confirm(ticket, ticket.preview_hash)
        self.assertEqual(confirmed.state, "confirmed")
        self.assertEqual(confirmed.confirmation, ticket.preview_hash)

    def test_stale_or_wrong_hash_is_rejected(self):
        ticket = _ticket()
        with self.assertRaises(ValueError):
            confirm(ticket, "deadbeef" * 4)

    def test_changed_parameter_invalidates_confirmation(self):
        ticket = _ticket()
        # User changes the quantity but the ticket still carries the OLD preview
        # hash. The hash of the new params no longer binds.
        changed = dataclasses.replace(ticket, quantity=ticket.quantity + 5)
        new_hash = compute_preview_hash(preview_params_of(changed))
        self.assertNotEqual(new_hash, changed.preview_hash)
        with self.assertRaises(ValueError):
            confirm(changed, new_hash)

    def test_preview_hash_changes_with_parameters(self):
        ticket = _ticket()
        changed = dataclasses.replace(ticket, side="sell")
        self.assertNotEqual(
            compute_preview_hash(preview_params_of(ticket)),
            compute_preview_hash(preview_params_of(changed)),
        )


if __name__ == "__main__":
    unittest.main()
