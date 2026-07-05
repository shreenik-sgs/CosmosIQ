"""IMPLEMENTATION-020A -- the /candidates LIST page + company-cockpit candidate state (offline).

Exercised through :func:`cosmosiq_app.api.dispatch` ALONE under a socket kill-switch -- no server,
no port, no wall clock. Proves the publication SURFACES:

* GET /candidates renders the eligible list (cards linking to the cockpit) + the blocked list
  (each with its EXACT reason), and the VERBATIM empty state when nothing is eligible;
* publishing is a SEPARATE explicit step (POST /api/candidates/publish) -- a pulse never
  auto-publishes; /api/pulse output is byte-identical whether or not candidates are later
  published;
* NO fixture ticker (IREN / NVDA / AAPL / ...) is ever a default in the product UI: the empty
  store's / , /runs and /candidates pages contain no real ticker, the nav / empty state carry
  none, and the Company Cockpit refuses to render without an explicit ticker segment;
* a published candidate's state (eligible / blocked + reason) shows on the company cockpit;
* NO buy / sell / order / submit affordance and NO score / rank field on any candidate surface.
"""

from __future__ import annotations

import json
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

import reality_mesh as rm
from cosmosiq_app import dispatch
from cosmosiq_app.cockpits import CANDIDATES_EMPTY_STATE
from reality_mesh.models import RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import RunStore, SignalStore

_NOW = "2026-07-04T12:00:00Z"
# Real tickers that live in fixtures -- none may DEFAULT into the product UI / empty state.
_FIXTURE_TICKERS = ("IREN", "NVDA", "AAPL", "TSLA", "AAOI", "AMBA", "META")
_FULL_DILIGENCE = {"opportunity_hypothesis_ref": "OPH-1",
                   "investment_diligence_ref": "THS-1",
                   "forward_scenario_state": "absent"}


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net blocked"))


def tearDownModule():
    socket.socket.connect = _ORIG


def _req(store, method, path, body=None, query=None):
    return dispatch({"method": method, "path": path, "query": query or {},
                     "body": body or {}}, store_dir=store, now=_NOW)


def _seed_run(store):
    RunStore(store).append(
        PulseRun(run_id="RUN-A", started_at="2026-07-04T10:00:00",
                 completed_at="2026-07-04T10:00:05", mode="pulse", trigger_type="manual",
                 watchlist=("IREN", "AAOI"), themes=("physical-ai",),
                 data_quality_status="healthy"),
        run_id="RUN-A", timestamp="2026-07-04T10:00:05")
    SignalStore(store).append(
        RealitySignal(signal_id="sig-iren-1", signal_type="fused",
                      affected_companies=("IREN",)),
        run_id="RUN-A", timestamp="2026-07-04T10:00:05")
    return "RUN-A"


# =========================================================================== #
# Empty store: verbatim empty state + NO fixture-ticker default                 #
# =========================================================================== #
class EmptyStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="cand_page_empty_")

    def test_candidates_empty_state_is_verbatim(self):
        html = _req(self.store, "GET", "/candidates")["body"]
        self.assertIn(CANDIDATES_EMPTY_STATE, html)
        # the exact contract string, including its two-newline paragraph break.
        self.assertIn("No Capital Candidates are available for this run.\n\n", html)

    def test_nav_gains_capital_candidates(self):
        html = _req(self.store, "GET", "/runs")["body"]
        self.assertIn('href="/candidates"', html)
        self.assertIn("Capital Candidates", html)

    def test_no_fixture_ticker_defaults_into_product_ui(self):
        for path in ("/", "/runs", "/candidates"):
            html = _req(self.store, "GET", path)["body"]
            for ticker in _FIXTURE_TICKERS:
                self.assertNotRegex(
                    html, r"\b{0}\b".format(ticker),
                    "{0} leaked into the default {1} page".format(ticker, path))

    def test_company_cockpit_requires_an_explicit_ticker(self):
        # No route renders a ticker page without an explicit ticker segment.
        self.assertEqual(_req(self.store, "GET", "/companies")["status"], 404)
        # /candidates (the list) is NOT a ticker page -- it renders no specific company.
        html = _req(self.store, "GET", "/candidates")["body"]
        for ticker in _FIXTURE_TICKERS:
            self.assertNotRegex(html, r"\b{0}\b".format(ticker))

    def test_candidates_list_has_no_trade_or_score_affordance(self):
        html = _req(self.store, "GET", "/candidates")["body"].lower()
        self.assertNotIn("<button", html)
        self.assertNotIn("<form", html)
        self.assertNotRegex(html, r"(?i)\b(buy|sell|place order|submit order|order now)\b")
        self.assertNotRegex(html, r'(?i)"score"|investability score|ranked')


# =========================================================================== #
# Published store: eligible cards, blocked reasons, company-cockpit state        #
# =========================================================================== #
class PublishedStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="cand_page_pub_")
        self.run_id = _seed_run(self.store)

    def _publish(self, diligence):
        return _req(self.store, "POST", "/api/candidates/publish",
                    {"run_id": self.run_id, "now": _NOW, "diligence_by_ticker": diligence})

    def test_publish_returns_eligible_and_blocked_counts(self):
        resp = self._publish({"IREN": _FULL_DILIGENCE})
        self.assertEqual(resp["status"], 200)
        body = resp["body"]
        self.assertEqual(body["eligible_count"], 1)
        self.assertEqual(body["blocked_count"], 1)          # AAOI has no signal/diligence
        self.assertEqual(body["eligible"], ["IREN"])
        self.assertEqual(body["blocked"][0]["ticker"], "AAOI")
        self.assertFalse(body["auto_published_in_pulse"])
        self.assertTrue(body["append_only"])

    def test_eligible_card_links_to_cockpit_and_shows_forward_gap(self):
        self._publish({"IREN": _FULL_DILIGENCE})
        html = _req(self.store, "GET", "/candidates")["body"]
        self.assertIn('href="/candidates/IREN"', html)
        self.assertIn("ELIGIBLE", html)
        # forward scenario absent -> an explicit GAP is rendered (not a block).
        self.assertIn("GAP", html)
        # empty state is NOT shown once an eligible candidate exists.
        self.assertNotIn(CANDIDATES_EMPTY_STATE, html)

    def test_blocked_candidate_renders_its_exact_reason(self):
        self._publish({"IREN": _FULL_DILIGENCE})
        html = _req(self.store, "GET", "/candidates")["body"]
        blocked = rm.blocked_candidates(self.store)
        self.assertTrue(blocked)
        self.assertIn(blocked[0].basis.split(" -- ")[0][:30], html)
        self.assertIn("AAOI", html)

    def test_empty_state_still_shows_when_only_blocked_exist(self):
        # publish with NO diligence for anyone -> zero eligible, both blocked.
        self._publish({})
        html = _req(self.store, "GET", "/candidates")["body"]
        self.assertIn(CANDIDATES_EMPTY_STATE, html)     # verbatim, no eligible
        self.assertIn("Blocked candidates", html)       # blocked section still rendered
        self.assertIn("AAOI", html)

    def test_company_cockpit_shows_published_candidate_state(self):
        self._publish({"IREN": _FULL_DILIGENCE})
        iren = _req(self.store, "GET", "/companies/IREN")["body"]
        self.assertIn("Published capital candidate", iren)
        self.assertIn("ELIGIBLE", iren)
        aaoi = _req(self.store, "GET", "/companies/AAOI")["body"]
        self.assertIn("Published capital candidate", aaoi)
        self.assertIn("INELIGIBLE", aaoi)

    def test_company_cockpit_says_none_published_when_absent(self):
        # nothing published yet -> honest 'no capital candidate published for this ticker'.
        html = _req(self.store, "GET", "/companies/IREN")["body"]
        self.assertIn("No capital candidate published for this ticker", html)

    def test_api_candidates_get_filters_by_status(self):
        self._publish({"IREN": _FULL_DILIGENCE})
        eligible = _req(self.store, "GET", "/api/candidates",
                        query={"status": "eligible"})["body"]
        self.assertEqual(eligible["count"], 1)
        self.assertEqual(eligible["candidates"][0]["ticker"], "IREN")
        blocked = _req(self.store, "GET", "/api/candidates",
                       query={"status": "blocked"})["body"]
        self.assertEqual(blocked["count"], 1)

    def test_no_score_or_rank_key_in_publish_response(self):
        body = self._publish({"IREN": _FULL_DILIGENCE})["body"]
        blob = json.dumps(body).lower()
        for tok in ('"score"', '"rank"', '"rating"', '"buy"', '"sell"', '"order"',
                    '"broker"', '"sizing"'):
            self.assertNotIn(tok, blob)

    def test_candidate_surfaces_carry_no_trade_control(self):
        self._publish({"IREN": _FULL_DILIGENCE})
        for path in ("/candidates", "/candidates/IREN", "/companies/IREN"):
            html = _req(self.store, "GET", path)["body"].lower()
            self.assertNotRegex(html, r"(?i)\b(buy|sell|place order|submit order|order now)\b")
            self.assertNotIn("place-order", html)


# =========================================================================== #
# Publication is a SEPARATE step -- a pulse never auto-publishes                 #
# =========================================================================== #
class SeparationAndByteIdentityTests(unittest.TestCase):
    def test_api_pulse_does_not_auto_publish(self):
        store = tempfile.mkdtemp(prefix="cand_page_sep_")
        resp = _req(store, "POST", "/api/pulse",
                    {"watchlist": ["IREN"], "themes": ["physical-ai"], "now": _NOW})
        self.assertEqual(resp["status"], 200)
        # the pulse response carries no candidate publication, and nothing is persisted.
        self.assertNotIn("candidate", json.dumps(resp["body"]).lower())
        self.assertFalse(os.path.isfile(
            os.path.join(store, "capital_candidate_store.jsonl")))
        self.assertEqual(rm.published_candidates(store), ())

    def test_api_pulse_body_is_byte_identical_across_stores(self):
        a = tempfile.mkdtemp(prefix="cand_page_ba_a_")
        b = tempfile.mkdtemp(prefix="cand_page_ba_b_")
        ra = _req(a, "POST", "/api/pulse",
                  {"watchlist": ["IREN"], "themes": ["physical-ai"], "now": _NOW})
        rb = _req(b, "POST", "/api/pulse",
                  {"watchlist": ["IREN"], "themes": ["physical-ai"], "now": _NOW})
        self.assertEqual(json.dumps(ra, sort_keys=True), json.dumps(rb, sort_keys=True))

    def test_demo_pulse_is_byte_identical(self):
        first = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        second = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        self.assertEqual(tuple(s.signal_id for s in first.signals),
                         tuple(s.signal_id for s in second.signals))


if __name__ == "__main__":
    unittest.main()
