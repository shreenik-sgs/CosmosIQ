"""UNIVERSE-DISCOVERY UD-4 -- the '/api/universe/run' cockpit action (OFFLINE).

The SANCTIONED "Run analysis on my accepted universe" operator action: the accepted universe (UD-3)
becomes the watchlist + DYNAMIC theme graph; it refreshes evidence (credential-gated -- honest gaps
if unconfigured) then recomputes the honest diligence lineage over the dynamic graph and shows each
ticker's state. Runs entirely OFFLINE under a socket kill-switch (no credential in env -> no source
configured -> no network attempted). Proves:

* the Universe page carries the sanctioned run action (posts to /api/universe/run) and stays clean
  of any trade verb / score token;
* an EMPTY accepted universe -> an honest no-op note (200), nothing fetched or computed;
* an accepted universe with NO credential configured -> an honest "not configured" note (200),
  nothing fabricated, no eligible candidate;
* a trade-like universe route (/api/universe/order|buy|trade) is refused 403; GET is 405.
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
from reality_mesh import accept_universe_entry

_NOW = "2026-07-15T12:00:00Z"
_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
_SCORE_TOKENS = ("score", "rank", "rating", "investab")


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("network blocked in the offline UD-4 cockpit tests"))


def tearDownModule():
    socket.socket.connect = _ORIG


def _get(store, path):
    return dispatch({"method": "GET", "path": path, "query": {}, "body": {}},
                    store_dir=store, now=_NOW)


def _post(store, path, body):
    return dispatch({"method": "POST", "path": path, "query": {}, "body": body},
                    store_dir=store, now=_NOW)


def _accept(store, ticker, theme_id, theme_label):
    accept_universe_entry(
        store, ticker=ticker, theme_id=theme_id, theme_label=theme_label,
        accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
        grounding_refs=("sec:fts/0001-26-1",))


# =========================================================================== #
# A. The page carries the sanctioned run action, hygienic                       #
# =========================================================================== #
class PageActionTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="ud4_page_")
        self.html = _get(self.store, "/universe")["body"]

    def test_run_action_is_present_and_posts_to_the_sanctioned_route(self):
        self.assertIn('action="/api/universe/run"', self.html)
        self.assertIn("Run analysis on my accepted universe", self.html)

    def test_copy_makes_operator_and_honest_gaps_explicit(self):
        self.assertIn("YOU choose to analyse your accepted universe", self.html)
        self.assertIn("credential-gated", self.html)
        self.assertIn("no market action is taken", self.html)

    def test_page_has_no_trade_word_or_score_token(self):
        self.assertEqual(_TRADE_WORD.findall(self.html), [])
        low = self.html.lower()
        for token in _SCORE_TOKENS:
            self.assertNotIn(token, low)


# =========================================================================== #
# B. Running the analysis -- honest, credential-gated, nothing fabricated        #
# =========================================================================== #
class RunActionTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="ud4_run_")

    def test_empty_universe_is_an_honest_no_op(self):
        r = _post(self.store, "/api/universe/run", {})
        self.assertEqual(r["status"], 200)
        self.assertIn("accepted universe is empty", r["body"])

    def test_accepted_but_unconfigured_is_an_honest_gap_no_eligible(self):
        _accept(self.store, "COHR", "optics", "Datacenter Optics")
        r = _post(self.store, "/api/universe/run", {})
        self.assertEqual(r["status"], 200)
        self.assertIn("No external sources configured", r["body"])
        # honest gap: nothing fetched, no eligible candidate fabricated, no trade verb.
        self.assertEqual(_TRADE_WORD.findall(r["body"]), [])
        self.assertNotIn("ELIGIBLE", r["body"])

    def test_bad_body_is_400(self):
        r = _post(self.store, "/api/universe/run", "not-a-dict")
        self.assertEqual(r["status"], 400)

    def test_get_is_read_only(self):
        self.assertEqual(_get(self.store, "/api/universe/run")["status"], 405)

    def test_a_trade_like_universe_route_is_403(self):
        for path in ("/api/universe/order", "/api/universe/buy", "/api/universe/trade"):
            r = _post(self.store, path, {"ticker": "IREN"})
            self.assertEqual(r["status"], 403, path)


if __name__ == "__main__":
    unittest.main()
