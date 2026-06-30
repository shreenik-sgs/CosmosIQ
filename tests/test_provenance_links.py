from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import unittest

from _real_chain import real_chain


class TestProvenanceLinks(unittest.TestCase):
    def _has_source(self, downstream, upstream):
        for ref in downstream.provenance.sources:
            if ref.object_id == upstream.id and ref.version == upstream.version:
                return True
        return False

    def test_each_downstream_binds_its_upstream_by_id_and_version(self):
        c = real_chain()
        obs, ia, oph = c["observation"], c["assessment"], c["hypothesis"]
        thesis, action = c["thesis"], c["action"]
        profile, psa = c["profile"], c["personalized"]
        # Observation -> Assessment -> Opportunity -> Thesis -> Action ->
        # PersonalizedAction (Saarathi), each bound by (id, version).
        self.assertTrue(self._has_source(ia, obs))
        self.assertTrue(self._has_source(oph, ia))
        self.assertTrue(self._has_source(thesis, oph))
        self.assertTrue(self._has_source(action, thesis))
        self.assertTrue(self._has_source(psa, action))
        self.assertTrue(self._has_source(psa, thesis))
        self.assertTrue(self._has_source(psa, profile))
        self.assertTrue(self._has_source(psa, c["portfolio"]))

    def test_sources_are_versioned_refs(self):
        ia = real_chain()["assessment"]
        self.assertTrue(len(ia.provenance.sources) >= 1)
        for ref in ia.provenance.sources:
            self.assertTrue(ref.object_id)
            self.assertIsInstance(ref.version, int)


if __name__ == "__main__":
    unittest.main()
