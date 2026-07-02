"""011F: the ``--enrich`` CLI flag makes the enriched real path first-class.

Offline: ``build_universe_app`` is monkeypatched to capture kwargs (no build, no network).
"""

from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from universe_ui import __main__ as ui_main
from universe_ui.app import PAGE_ORDER


def _fake_paths(out):
    paths = {name: os.path.join(out, name) for name in PAGE_ORDER}
    paths["assets/universe.css"] = os.path.join(out, "assets/universe.css")
    paths["assets/universe.js"] = os.path.join(out, "assets/universe.js")
    return paths


class CliEnrichFlagTests(unittest.TestCase):
    def _run(self, argv):
        captured = {}

        def fake_build(out, **kw):
            captured.update(kw)
            captured["_out"] = out
            return _fake_paths(out)

        orig = ui_main.build_universe_app
        ui_main.build_universe_app = fake_build
        try:
            rc = ui_main.main(argv)
        finally:
            ui_main.build_universe_app = orig
        self.assertEqual(rc, 0)
        return captured

    def test_enrich_flag_wires_enrich_true(self):
        cap = self._run(["--mode", "real_evidence_on_demand", "--ticker", "IREN",
                         "--enrich", "--out", "/tmp/_enrich"])
        self.assertTrue(cap.get("enrich"), "--enrich must pass enrich=True to the builder")
        self.assertEqual(cap.get("mode"), "real_evidence_on_demand")

    def test_default_real_is_unenriched(self):
        cap = self._run(["--mode", "real_evidence_on_demand", "--ticker", "IREN",
                         "--out", "/tmp/_plain"])
        self.assertFalse(cap.get("enrich"), "default real mode must be unenriched (honest sparse)")

    def test_enrich_flag_on_watchlist(self):
        cap = self._run(["--mode", "real_evidence_on_demand", "--tickers", "IREN,AAOI,INOD",
                         "--enrich", "--out", "/tmp/_wl"])
        self.assertTrue(cap.get("enrich"))
        self.assertEqual(list(cap.get("tickers")), ["IREN", "AAOI", "INOD"])

    def test_demo_default_passes_no_enrich(self):
        cap = self._run(["--out", "/tmp/_demo"])  # demo (default)
        self.assertEqual(cap.get("mode"), "demo")
        self.assertNotIn("enrich", cap)  # demo path forwards no build kwargs -> byte-identical


if __name__ == "__main__":
    unittest.main()
