"""DILIGENCE-LINEAGE (slice 2) -- the headless ``cosmosiq_pulse accept-diligence`` CLI.

OFFLINE under a socket kill-switch. Proves the CLI RECORDS one operator-authored thesis (never
auto-accepts), advances a real supporting thesis to an eligible candidate, and honestly REFUSES a
bad acceptance (non-zero exit, nothing written).
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
from reality_mesh import run_diligence_lineage
from reality_mesh.investment_diligence import InvestmentDiligenceStore
from reality_mesh.models import RealityEvent, RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import EventStore, RunStore, SignalStore

_NOW = "2026-07-06T12:00:00Z"

_OKLO_POS = RealitySignal(
    signal_id="sig-oklo-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("OKLO",), direction_label="accelerating", magnitude_label="major",
    confidence_label="high", corroboration_status="corroborated", evidence_refs=("ev-oklo-1",),
    source_refs=("sec:oklo:0001",))
_OKLO_EVENT = RealityEvent(
    event_id="E-oklo-1", timestamp=_NOW, source_id="src.sec", source_type="sec_filing",
    source_authority="canonical", claim_status="verified_fact", discipline="news_filings",
    event_type="sec_8-k_results_of_operations", affected_companies=("OKLO",),
    source_refs=("sec:oklo:0001",), evidence_refs=("ev-oklo-1",))


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("network attempted during offline CLI test"))


def tearDownModule():
    socket.socket.connect = _ORIG


def _seed(store):
    RunStore(store).append(
        PulseRun(run_id="RUN-D", started_at="2026-07-06T10:00:00",
                 completed_at="2026-07-06T10:00:05", mode="pulse", trigger_type="manual",
                 watchlist=("OKLO",), themes=("nuclear",), data_quality_status="healthy"),
        run_id="RUN-D", timestamp="2026-07-06T10:00:05")
    SignalStore(store).append(_OKLO_POS, run_id="RUN-D", timestamp="2026-07-06T10:00:05")
    EventStore(store).append(_OKLO_EVENT, run_id="RUN-D", timestamp="2026-07-06T10:00:05")


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = pulse_main(argv)
    return code, buf.getvalue()


class AcceptDiligenceCliTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="cli_dil_")
        _seed(self.store)
        out = next(o for o in run_diligence_lineage(
            self.store, run_id="RUN-D", watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.hyp = out.opportunity_hypothesis_ref

    def _argv(self, **over):
        argv = ["accept-diligence", "--store-dir", self.store, "--ticker", "OKLO",
                "--run-id", "RUN-D", "--hypothesis-ref", self.hyp,
                "--verdict", "thesis_supported", "--thesis", "Corroborated.",
                "--evidence-refs", "sig-oklo-1,ev-oklo-1", "--accepted-by", "operator:sgs",
                "--now", _NOW]
        for flag, value in over.items():
            argv[argv.index("--" + flag.replace("_", "-")) + 1] = value
        return argv

    def test_records_a_supporting_thesis_and_reports_eligible(self):
        code, text = _run(self._argv())
        self.assertEqual(code, 0)
        self.assertIn("recorded diligence_id=idil:OKLO:", text)
        self.assertIn("now reads eligible", text)
        self.assertEqual(len(InvestmentDiligenceStore(self.store).read_all()), 1)
        out = next(o for o in run_diligence_lineage(
            self.store, run_id="RUN-D", watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.assertEqual(out.candidate_state, "eligible")

    def test_bad_acceptance_exits_nonzero_and_writes_nothing(self):
        code, text = _run(self._argv(evidence_refs="bogus-ref"))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", text)
        self.assertEqual(InvestmentDiligenceStore(self.store).read_all(), ())

    def test_rejected_verdict_is_recorded_but_not_eligible(self):
        code, text = _run(self._argv(verdict="thesis_rejected"))
        self.assertEqual(code, 0)
        self.assertIn("stays", text)
        out = next(o for o in run_diligence_lineage(
            self.store, run_id="RUN-D", watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.assertEqual(out.candidate_state, "ineligible_missing_diligence")


if __name__ == "__main__":
    unittest.main()
