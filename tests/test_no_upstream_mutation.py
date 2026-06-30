from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import copy
import dataclasses
import unittest

from eios_core.canonical_objects import Observation
from eios_core.provenance import Provenance
from eios_core.ids import iso_from_epoch
from prometheus.investment_action import generate_investment_action
from personal_cio.personalized_action import generate_personalized_action
from _real_chain import real_chain


class TestNoUpstreamMutation(unittest.TestCase):
    def test_frozen_objects_reject_mutation(self):
        obs = Observation(id="OBS-1", provenance=Provenance(created_at=iso_from_epoch(0), actor="t"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            obs.id = "OBS-2"  # type: ignore[misc]

    def test_constructing_downstream_does_not_mutate_upstream(self):
        c = real_chain()
        thesis, action = c["thesis"], c["action"]
        profile, portfolio = c["profile"], c["portfolio"]
        ia_snapshot = copy.deepcopy(c["assessment"])
        thesis_snapshot = copy.deepcopy(thesis)
        action_snapshot = copy.deepcopy(action)

        # Re-deriving downstream objects must not mutate any upstream object.
        generate_investment_action(thesis, actor="t", now=0)
        generate_personalized_action(thesis, action, profile, portfolio, actor="t", now=0)

        self.assertEqual(c["assessment"], ia_snapshot)
        self.assertEqual(thesis, thesis_snapshot)
        self.assertEqual(action, action_snapshot)


if __name__ == "__main__":
    unittest.main()
