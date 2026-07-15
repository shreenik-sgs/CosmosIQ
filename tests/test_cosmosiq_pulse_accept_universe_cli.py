"""UNIVERSE-DISCOVERY UD-3 -- the headless ``cosmosiq_pulse accept-universe`` CLI.

OFFLINE under a socket kill-switch. Proves the CLI ACCEPTS one operator-attributed, GROUNDED ticker
into the universe (never auto-accepts), derives the honest authority, and REFUSES an ungrounded
acceptance (non-zero exit, nothing written).
"""

from __future__ import annotations

import io
import os
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cosmosiq_pulse.__main__ import main as pulse_main
from reality_mesh import accepted_universe
from reality_mesh.accepted_universe import AcceptedUniverseStore

_NOW = "2026-07-15T12:00:00Z"


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("network attempted during offline CLI test"))


def tearDownModule():
    socket.socket.connect = _ORIG


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = pulse_main(argv)
    return code, buf.getvalue()


class AcceptUniverseCliTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="univ_cli_")

    def test_sec_grounded_accept_succeeds_and_is_canonical(self):
        code, out = _run([
            "accept-universe", "--store-dir", self.store, "--ticker", "zzz",
            "--theme-id", "physical-ai", "--theme-label", "Physical AI",
            "--accepted-by", "operator:sgs", "--grounding-refs", "sec:cik/0000000001",
            "--now", _NOW])
        self.assertEqual(code, 0)
        self.assertIn("authority=canonical", out)
        entries = accepted_universe(self.store)
        self.assertEqual([e.ticker for e in entries], ["ZZZ"])
        self.assertEqual(entries[0].accepted_by, "operator:sgs")

    def test_operator_manual_accept_is_manual(self):
        code, out = _run([
            "accept-universe", "--store-dir", self.store, "--ticker", "niche",
            "--theme-id", "niche-theme", "--theme-label", "Niche theme",
            "--accepted-by", "operator:sgs", "--origin", "operator_manual",
            "--grounding-refs", "operator:my-primary-note", "--now", _NOW])
        self.assertEqual(code, 0)
        self.assertIn("authority=manual", out)

    def test_ungrounded_accept_is_refused_nonzero_nothing_written(self):
        # operator_manual with NO explicit evidence ref -> pure-validation refusal (offline).
        code, out = _run([
            "accept-universe", "--store-dir", self.store, "--ticker", "ghost",
            "--theme-id", "fad", "--theme-label", "Fad",
            "--accepted-by", "operator:sgs", "--origin", "operator_manual", "--now", _NOW])
        self.assertEqual(code, 1)
        self.assertIn("REFUSED (nothing written)", out)
        self.assertEqual(AcceptedUniverseStore(self.store).read_all(), ())

    def test_rejected_verdict_is_recorded_but_not_in_universe(self):
        code, _out = _run([
            "accept-universe", "--store-dir", self.store, "--ticker", "zzz",
            "--theme-id", "physical-ai", "--theme-label", "Physical AI",
            "--accepted-by", "operator:sgs", "--grounding-refs", "sec:cik/0000000001",
            "--verdict", "rejected", "--now", _NOW])
        self.assertEqual(code, 0)
        self.assertEqual(accepted_universe(self.store), ())
        self.assertEqual(len(AcceptedUniverseStore(self.store).read_all()), 1)


if __name__ == "__main__":
    unittest.main()
