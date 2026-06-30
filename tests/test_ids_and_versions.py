from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import unittest

from eios_core.ids import stable_id, iso_from_epoch
from eios_core.versioning import initial, bump
from eios_core.canonical_objects import CanonicalObject, Observation
from eios_core.provenance import Provenance
from reality_intelligence.intelligence_assessment import make_intelligence_assessment


class TestIdsAndVersions(unittest.TestCase):
    def test_stable_id_is_deterministic(self):
        a = stable_id("TKT", "ia-1", 1)
        b = stable_id("TKT", "ia-1", 1)
        self.assertEqual(a, b)

    def test_stable_id_varies_with_inputs(self):
        self.assertNotEqual(stable_id("TKT", "ia-1", 1), stable_id("TKT", "ia-1", 2))
        self.assertNotEqual(stable_id("TKT", "ia-1", 1), stable_id("TKT", "ia-2", 1))

    def test_stable_id_has_prefix(self):
        self.assertTrue(stable_id("OBS", "x").startswith("OBS-"))

    def test_iso_from_epoch_is_deterministic_and_no_clock(self):
        self.assertEqual(iso_from_epoch(0), iso_from_epoch(0))
        self.assertTrue(iso_from_epoch(0).endswith("Z"))

    def test_version_helpers(self):
        self.assertEqual(initial(), 1)
        self.assertEqual(bump(1), 2)
        self.assertEqual(bump(bump(1)), 3)

    def test_canonical_object_has_id_version_provenance(self):
        obj = CanonicalObject(id="X-1")
        self.assertEqual(obj.id, "X-1")
        self.assertEqual(obj.version, 1)
        self.assertIsInstance(obj.provenance, Provenance)

    def test_every_built_object_carries_identity(self):
        obs = Observation(
            id=stable_id("OBS", "a"),
            provenance=Provenance(created_at=iso_from_epoch(0), actor="t"),
            content={"x": 1},
        )
        ia = make_intelligence_assessment([obs], "SUBJ", "assess", actor="t", now=0)
        for o in (obs, ia):
            self.assertIsInstance(o.id, str)
            self.assertTrue(o.id)
            self.assertIsInstance(o.version, int)
            self.assertEqual(o.version, 1)
            self.assertIsInstance(o.provenance, Provenance)
            self.assertTrue(o.provenance.created_at)

    def test_ref_carries_id_and_version(self):
        ia = make_intelligence_assessment(
            [Observation(id="OBS-1", provenance=Provenance(created_at="t", actor="t"))],
            "S", "a", actor="t", now=0,
        )
        ref = ia.ref()
        self.assertEqual(ref.object_id, ia.id)
        self.assertEqual(ref.version, ia.version)


if __name__ == "__main__":
    unittest.main()
