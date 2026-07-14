"""DILIGENCE-LINEAGE (slice 1) -- the /opportunities page surfaces each ticker's HONEST state.

Exercised through :func:`cosmosiq_app.api.dispatch` ALONE under a socket kill-switch -- no server,
no port, no wall clock. Proves the Opportunities tab renders the honest discovery -> candidate
lineage:

* a graph-connected, corroborated ticker (COHR) shows ``diligence_candidate`` +
  ``ineligible_missing_diligence`` + the EXACT missing link ("needs an accepted diligence
  thesis") + the real signals / hypothesis backing it -- and is NEVER shown eligible;
* a graph-unconnected ticker with no evidence shows ``blocked_insufficient_evidence`` honestly;
* the page carries NO trade affordance (no buy/sell/order button/form) and NO score / rank /
  rating token, no secret; on an EMPTY store no fixture ticker leaks and the verbatim
  Capital-Candidates empty state renders. Read-only, offline, deterministic.
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
from cosmosiq_app.cockpits import CANDIDATES_EMPTY_STATE
from reality_mesh.models import RealityEvent, RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import EventStore, RunStore, SignalStore

_NOW = "2026-07-06T12:00:00Z"
_FIXTURE_TICKERS = ("IREN", "NVDA", "AAPL", "TSLA", "AAOI", "AMBA", "META")
_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
_SCORE_TOKENS = ("score", "rank", "rating", "investab")
_SECRET_PATTERNS = (re.compile(r"sk-[A-Za-z0-9]{8,}"),
                    re.compile(r"AKIA[0-9A-Z]{16}"),
                    re.compile(r"-----BEGIN"))

_COHR_SIGNAL = RealitySignal(
    signal_id="sig-cohr-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("COHR",), affected_themes=("optics",),
    direction_label="improving", magnitude_label="major", confidence_label="high",
    corroboration_status="corroborated", evidence_refs=("ev-cohr-1",),
    source_refs=("sec:cohr:0001",))
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


def _get(store, path):
    return dispatch({"method": "GET", "path": path, "query": {}, "body": {}},
                    store_dir=store, now=_NOW)


def _seed(store):
    RunStore(store).append(
        PulseRun(run_id="RUN-O", started_at="2026-07-06T10:00:00",
                 completed_at="2026-07-06T10:00:05", mode="pulse", trigger_type="manual",
                 watchlist=("COHR", "IREN"), themes=("optical-networking",),
                 data_quality_status="healthy"),
        run_id="RUN-O", timestamp="2026-07-06T10:00:05")
    SignalStore(store).append(_COHR_SIGNAL, run_id="RUN-O", timestamp="2026-07-06T10:00:05")
    EventStore(store).append(_COHR_EVENT, run_id="RUN-O", timestamp="2026-07-06T10:00:05")


# =========================================================================== #
# A. Empty store: the candidate surface + no fixture leak                       #
# =========================================================================== #
class EmptyStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="opp_empty_")
        self.html = _get(self.store, "/opportunities")["body"]

    def test_is_the_capital_candidate_surface_with_verbatim_empty_state(self):
        self.assertIn("Capital Candidates", self.html)
        self.assertIn(CANDIDATES_EMPTY_STATE, self.html)

    def test_no_fixture_ticker_leaks_into_the_empty_page(self):
        for ticker in _FIXTURE_TICKERS:
            self.assertNotRegex(self.html, r"\b{0}\b".format(ticker), ticker)


# =========================================================================== #
# B. Seeded store: honest states + exact missing link, no trade/score/secret    #
# =========================================================================== #
class SeededStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="opp_seeded_")
        _seed(self.store)
        self.html = _get(self.store, "/opportunities")["body"]

    def test_renders_200(self):
        self.assertEqual(_get(self.store, "/opportunities")["status"], 200)

    def test_graph_connected_ticker_shows_diligence_and_missing_diligence(self):
        self.assertIn("diligence_candidate", self.html)          # raw discovery state token shown
        self.assertIn("missing diligence reference", self.html)  # honest candidate state
        self.assertIn("accepted diligence thesis", self.html)    # the exact missing link
        # its real backing refs are surfaced.
        self.assertIn("sig-cohr-1", self.html)
        self.assertIn("hyp.optics", self.html)

    def test_graph_unconnected_ticker_shows_blocked_insufficient_evidence(self):
        self.assertIn("blocked_insufficient_evidence", self.html)
        self.assertIn("not in the theme graph", self.html)

    def test_never_shows_a_ticker_as_eligible(self):
        self.assertNotIn("ELIGIBLE -- full evidence lineage present", self.html)

    def test_read_only_no_write_on_render(self):
        # opening the page must not publish anything (persist=False in the lineage recompute).
        store2 = os.path.join(self.store, "capital_candidate_store.jsonl")
        self.assertFalse(os.path.isfile(store2))
        self.assertFalse(os.path.isdir(os.path.join(self.store, "diligence_inputs")))

    def test_no_trade_affordance(self):
        low = self.html.lower()
        self.assertNotIn("<button", low)
        self.assertNotIn("<form", low)
        self.assertEqual(_TRADE_WORD.findall(self.html), [])

    def test_no_score_rank_rating_token(self):
        low = self.html.lower()
        for token in _SCORE_TOKENS:
            self.assertNotIn(token, low, token)

    def test_no_secret_value(self):
        for pattern in _SECRET_PATTERNS:
            self.assertIsNone(pattern.search(self.html))


if __name__ == "__main__":
    unittest.main()
