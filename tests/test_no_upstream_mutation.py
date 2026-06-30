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
from reality_intelligence.intelligence_assessment import make_intelligence_assessment
from genesis.opportunity_hypothesis import make_opportunity_hypothesis
from prometheus.investment_thesis import make_investment_thesis
from prometheus.investment_action import make_investment_action


class TestNoUpstreamMutation(unittest.TestCase):
    def test_frozen_objects_reject_mutation(self):
        obs = Observation(id="OBS-1", provenance=Provenance(created_at=iso_from_epoch(0), actor="t"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            obs.id = "OBS-2"  # type: ignore[misc]

    def test_constructing_downstream_does_not_mutate_upstream(self):
        obs = Observation(
            id="OBS-1",
            version=1,
            provenance=Provenance(created_at=iso_from_epoch(0), actor="t"),
            content={"x": 1},
        )
        obs_snapshot = copy.deepcopy(obs)

        ia = make_intelligence_assessment([obs], "S", "a", actor="t", now=0)
        ia_snapshot = copy.deepcopy(ia)
        oph = make_opportunity_hypothesis(ia, "S", "h", actor="t", now=0)
        thesis = make_investment_thesis(oph, "IREN", 2000.0, actor="t", now=0)
        make_investment_action(thesis, "enter", actor="t", now=0)

        # Upstream objects are unchanged after downstream construction.
        self.assertEqual(obs, obs_snapshot)
        self.assertEqual(ia, ia_snapshot)
        self.assertEqual(obs.content, {"x": 1})


if __name__ == "__main__":
    unittest.main()
