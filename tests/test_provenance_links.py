from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import unittest

from eios_core.canonical_objects import Observation
from eios_core.provenance import Provenance
from eios_core.ids import iso_from_epoch
from reality_intelligence.intelligence_assessment import make_intelligence_assessment
from genesis.opportunity_hypothesis import make_opportunity_hypothesis
from prometheus.investment_thesis import make_investment_thesis
from prometheus.investment_action import make_investment_action
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.personalized_action import make_personalized_action


def _obs():
    return Observation(
        id="OBS-1",
        version=1,
        provenance=Provenance(created_at=iso_from_epoch(0), actor="t"),
        content={"x": 1},
    )


class TestProvenanceLinks(unittest.TestCase):
    def _chain(self):
        obs = _obs()
        ia = make_intelligence_assessment([obs], "S", "a", actor="t", now=0)
        oph = make_opportunity_hypothesis(ia, "S", "h", actor="t", now=0)
        thesis = make_investment_thesis(oph, "IREN", 2000.0, actor="t", now=0)
        action = make_investment_action(thesis, "enter", actor="t", now=0)
        profile = make_personal_investment_profile("ACCT", actor="t", now=0)
        psa = make_personalized_action(action, profile, actor="t", now=0)
        return obs, ia, oph, thesis, action, profile, psa

    def _has_source(self, downstream, upstream):
        for ref in downstream.provenance.sources:
            if ref.object_id == upstream.id and ref.version == upstream.version:
                return True
        return False

    def test_each_downstream_binds_its_upstream_by_id_and_version(self):
        obs, ia, oph, thesis, action, profile, psa = self._chain()
        self.assertTrue(self._has_source(ia, obs))
        self.assertTrue(self._has_source(oph, ia))
        self.assertTrue(self._has_source(thesis, oph))
        self.assertTrue(self._has_source(action, thesis))
        self.assertTrue(self._has_source(psa, action))
        self.assertTrue(self._has_source(psa, profile))

    def test_sources_are_versioned_refs(self):
        _, ia, _, _, _, _, _ = self._chain()
        self.assertTrue(len(ia.provenance.sources) >= 1)
        for ref in ia.provenance.sources:
            self.assertTrue(ref.object_id)
            self.assertIsInstance(ref.version, int)


if __name__ == "__main__":
    unittest.main()
