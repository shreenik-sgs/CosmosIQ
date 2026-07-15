"""DILIGENCE-LINEAGE (slice 2) -- the Opportunities diligence-review form + /api/diligence/accept.

Exercised through :func:`cosmosiq_app.api.dispatch` ALONE under a socket kill-switch -- no server,
no port, no wall clock. Proves the cockpit exposes ONE sanctioned, operator-authored form and the
endpoint records ONLY a real, evidence-grounded, operator-accepted thesis:

* a candidate at ``ineligible_missing_diligence`` (real hypothesis) shows the SANCTIONED
  'Record your diligence review' form -- honest copy (operator authors + accepts; CosmosIQ records,
  never generates), NO trade / order / broker word or control, NO score / rank / rating token;
* POSTing a ``thesis_supported`` review -> 303 back to /opportunities, after which the candidate
  reads ``eligible`` with the real diligence ref;
* POSTing bad input (unresolved evidence / no name / free-string hypothesis) -> 400 + honest error,
  and NOTHING is written; a trade-like route is refused 403;
* the empty store shows no form (nothing to review); GET is read-only. Deterministic + offline.
"""

from __future__ import annotations

import os
import re
import socket
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cosmosiq_app import dispatch
from reality_mesh.investment_diligence import InvestmentDiligenceStore
from reality_mesh.models import RealityEvent, RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import EventStore, RunStore, SignalStore

_NOW = "2026-07-06T12:00:00Z"
_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
_SCORE_TOKENS = ("score", "rank", "rating", "investab")

_COHR_SIGNAL = RealitySignal(
    signal_id="sig-cohr-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("COHR",), affected_themes=("optics",), direction_label="improving",
    magnitude_label="major", confidence_label="high", corroboration_status="corroborated",
    evidence_refs=("ev-cohr-1",), source_refs=("sec:cohr:0001",))
_COHR_EVENT = RealityEvent(
    event_id="E-cohr-1", timestamp=_NOW, source_id="src.sec", source_type="sec_filing",
    source_authority="canonical", claim_status="verified_fact", discipline="news_filings",
    event_type="sec_8-k_results_of_operations", affected_companies=("COHR",),
    source_refs=("sec:cohr:0001",), evidence_refs=("ev-cohr-1",))


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net blocked"))


def tearDownModule():
    socket.socket.connect = _ORIG


def _seed(store):
    RunStore(store).append(
        PulseRun(run_id="RUN-O", started_at="2026-07-06T10:00:00",
                 completed_at="2026-07-06T10:00:05", mode="pulse", trigger_type="manual",
                 watchlist=("COHR",), themes=("optical-networking",),
                 data_quality_status="healthy"),
        run_id="RUN-O", timestamp="2026-07-06T10:00:05")
    SignalStore(store).append(_COHR_SIGNAL, run_id="RUN-O", timestamp="2026-07-06T10:00:05")
    EventStore(store).append(_COHR_EVENT, run_id="RUN-O", timestamp="2026-07-06T10:00:05")


def _get(store, path):
    return dispatch({"method": "GET", "path": path, "query": {}, "body": {}},
                    store_dir=store, now=_NOW)


def _post(store, path, body):
    return dispatch({"method": "POST", "path": path, "query": {}, "body": body},
                    store_dir=store, now=_NOW)


class FormTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="dilform_")
        _seed(self.store)
        self.html = _get(self.store, "/opportunities")["body"]

    def test_form_is_present_and_sanctioned(self):
        self.assertIn('action="/api/diligence/accept"', self.html)
        self.assertIn("Record diligence review", self.html)

    def test_copy_makes_operator_authorship_explicit(self):
        self.assertIn("YOU author and accept", self.html)
        self.assertIn("never generates", self.html)
        self.assertIn("research conclusion", self.html)

    def test_no_trade_word_or_control_in_the_form(self):
        self.assertEqual(_TRADE_WORD.findall(self.html), [])
        self.assertNotIn('action="/api/orders"', self.html)

    def test_no_score_token(self):
        low = self.html.lower()
        for token in _SCORE_TOKENS:
            self.assertNotIn(token, low, token)

    def test_empty_store_shows_no_form(self):
        empty = tempfile.mkdtemp(prefix="dilform_empty_")
        html = _get(empty, "/opportunities")["body"]
        self.assertNotIn("/api/diligence/accept", html)


class AcceptEndpointTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="dilaccept_")
        _seed(self.store)

    def _hyp(self):
        html = _get(self.store, "/opportunities")["body"]
        self.assertIn("hyp.optics", html)
        return "hyp.optics"

    def test_supporting_thesis_redirects_and_makes_eligible(self):
        r = _post(self.store, "/api/diligence/accept", {
            "ticker": "COHR", "run_id": "RUN-O", "opportunity_hypothesis_ref": self._hyp(),
            "verdict": "thesis_supported", "thesis": "Optics demand real.",
            "key_risks": "valuation", "evidence_refs": "sig-cohr-1, ev-cohr-1",
            "accepted_by": "operator:sgs", "now": _NOW})
        self.assertEqual(r["status"], 303)
        self.assertEqual(r["headers"]["Location"], "/opportunities")
        self.assertEqual(len(InvestmentDiligenceStore(self.store).read_all()), 1)
        html = _get(self.store, "/opportunities")["body"]
        self.assertIn("eligible", html)
        self.assertIn("idil:COHR:", html)

    def test_bad_input_is_400_and_writes_nothing(self):
        r = _post(self.store, "/api/diligence/accept", {
            "ticker": "COHR", "run_id": "RUN-O", "opportunity_hypothesis_ref": self._hyp(),
            "verdict": "thesis_supported", "thesis": "x", "evidence_refs": "bogus-ref",
            "accepted_by": "op", "now": _NOW})
        self.assertEqual(r["status"], 400)
        self.assertIn("Could not record", r["body"])
        self.assertEqual(InvestmentDiligenceStore(self.store).read_all(), ())

    def test_missing_name_is_refused(self):
        r = _post(self.store, "/api/diligence/accept", {
            "ticker": "COHR", "run_id": "RUN-O", "opportunity_hypothesis_ref": self._hyp(),
            "verdict": "thesis_supported", "thesis": "x", "evidence_refs": "sig-cohr-1",
            "accepted_by": "", "now": _NOW})
        self.assertEqual(r["status"], 400)
        self.assertEqual(InvestmentDiligenceStore(self.store).read_all(), ())

    def test_free_string_hypothesis_is_refused(self):
        r = _post(self.store, "/api/diligence/accept", {
            "ticker": "COHR", "run_id": "RUN-O", "opportunity_hypothesis_ref": "hyp.fake",
            "verdict": "thesis_supported", "thesis": "x", "evidence_refs": "sig-cohr-1",
            "accepted_by": "op", "now": _NOW})
        self.assertEqual(r["status"], 400)
        self.assertEqual(InvestmentDiligenceStore(self.store).read_all(), ())

    def test_rejected_thesis_stays_ineligible(self):
        _post(self.store, "/api/diligence/accept", {
            "ticker": "COHR", "run_id": "RUN-O", "opportunity_hypothesis_ref": self._hyp(),
            "verdict": "thesis_rejected", "thesis": "no", "evidence_refs": "sig-cohr-1",
            "accepted_by": "op", "now": _NOW})
        html = _get(self.store, "/opportunities")["body"]
        self.assertIn("missing diligence reference", html)

    def test_a_trade_like_diligence_route_is_403(self):
        r = _post(self.store, "/api/diligence/buy", {"ticker": "COHR"})
        self.assertEqual(r["status"], 403)

    def test_get_is_read_only_no_write(self):
        _get(self.store, "/opportunities")
        self.assertEqual(InvestmentDiligenceStore(self.store).read_all(), ())


if __name__ == "__main__":
    unittest.main()
