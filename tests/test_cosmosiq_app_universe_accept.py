"""UNIVERSE-DISCOVERY UD-3 -- the Universe review surface + /api/universe/accept.

Exercised through :func:`cosmosiq_app.api.dispatch` ALONE under a socket kill-switch -- no server,
no port, no wall clock, no network. Proves the cockpit exposes the SANCTIONED operator
universe-acceptance surface and the endpoint records ONLY a GROUNDED, operator-accepted entry:

* the Universe page shows YOUR universe (grounded entries + authority + provenance), the UD-2 AI
  leads clearly labelled UNVERIFIED / must-be-grounded, and a sanctioned 'Accept into universe'
  form -- honest copy (operator accepts; CosmosIQ records; an AI suggestion is grounded against
  SEC / FMP first), NO trade / order / broker word or control, NO score / rank / rating token;
* POSTing a SEC-grounded acceptance -> 303 back to /universe, after which the ticker reads with the
  honest ``canonical`` authority; a screener ref -> ``convenience``;
* POSTing an UNGROUNDED / no-name input -> 400 + honest error, and NOTHING is written; a trade-like
  route is refused 403;
* the empty store shows an honest empty universe; GET is read-only. Deterministic + offline.
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

from cosmosiq_app import dispatch
from reality_mesh import accepted_universe
from reality_mesh.accepted_universe import AcceptedUniverseStore

_NOW = "2026-07-15T12:00:00Z"
_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
_SCORE_TOKENS = ("score", "rank", "rating", "investab")
_FIXTURE_TICKERS = ("IREN", "NVDA", "AAPL", "TSLA", "AAOI", "AMBA", "META")


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net blocked"))


def tearDownModule():
    socket.socket.connect = _ORIG


def _get(store, path):
    return dispatch({"method": "GET", "path": path, "query": {}, "body": {}},
                    store_dir=store, now=_NOW)


def _post(store, path, body):
    return dispatch({"method": "POST", "path": path, "query": {}, "body": body},
                    store_dir=store, now=_NOW)


def _accept_body(**over):
    body = {"ticker": "ZZZ", "theme_id": "physical-ai", "theme_label": "Physical AI",
            "accepted_by": "operator:sgs", "origin": "evidence_discovery",
            "grounding_refs": "sec:fts/0001-26-1, sec:cik/0000000001", "now": _NOW}
    body.update(over)
    return body


def _seed_ai_suggestion(store, theme="Edge robotics", tickers=("ACME", "WIDG")):
    """Write ONE UD-2 AI suggestion into the assistant-owned store (display-only)."""
    path = os.path.join(store, "universe_suggestions.jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "suggestion_id": "ai-univ-suggestion-000001",
            "ai_generated": True, "not_evidence": True,
            "source_authority": "ai_suggestion",
            "verification_status": "unverified_ai_suggestion",
            "label": "AI-generated -- not evidence, not a recommendation.",
            "theme": theme, "rationale": "an emerging lead to investigate",
            "candidate_tickers": list(tickers)}) + "\n")


# =========================================================================== #
# A. The page: sections, sanctioned form, honest copy, hygiene                  #
# =========================================================================== #
class PageTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="univ_page_")
        self.html = _get(self.store, "/universe")["body"]

    def test_page_renders_with_the_three_surfaces(self):
        self.assertEqual(_get(self.store, "/universe")["status"], 200)
        self.assertIn("Your universe", self.html)
        self.assertIn("AI research leads", self.html)
        self.assertIn('action="/api/universe/accept"', self.html)

    def test_empty_universe_is_honest(self):
        self.assertIn("No tickers accepted into your universe yet", self.html)

    def test_copy_makes_operator_and_grounding_explicit(self):
        self.assertIn("YOU accept", self.html)
        self.assertIn("never accepts on its own", self.html)
        self.assertIn("grounded against SEC / FMP first", self.html)

    def test_no_trade_word_or_score_token_on_the_page(self):
        self.assertEqual(_TRADE_WORD.findall(self.html), [])
        low = self.html.lower()
        for token in _SCORE_TOKENS:
            self.assertNotIn(token, low)

    def test_no_fixture_ticker_leaks_into_the_empty_page(self):
        for ticker in _FIXTURE_TICKERS:
            self.assertNotRegex(self.html, r"\b{0}\b".format(ticker))

    def test_universe_is_reachable_from_every_page_nav(self):
        self.assertIn('href="/universe"', _get(self.store, "/")["body"])


# =========================================================================== #
# B. Accepting a GROUNDED entry through the endpoint                             #
# =========================================================================== #
class AcceptEndpointTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="univ_accept_")

    def test_sec_grounded_accept_redirects_and_reads_canonical(self):
        r = _post(self.store, "/api/universe/accept", _accept_body())
        self.assertEqual(r["status"], 303)
        self.assertEqual(r["headers"]["Location"], "/universe")
        entries = accepted_universe(self.store)
        self.assertEqual([e.ticker for e in entries], ["ZZZ"])
        self.assertEqual(entries[0].source_authority, "canonical")
        html = _get(self.store, "/universe")["body"]
        self.assertIn("ZZZ", html)
        self.assertIn("canonical", html)

    def test_screener_grounded_accept_reads_convenience(self):
        r = _post(self.store, "/api/universe/accept", _accept_body(
            ticker="WWW", grounding_refs="fmp:screener/Technology/Semiconductors"))
        self.assertEqual(r["status"], 303)
        self.assertEqual(accepted_universe(self.store)[0].source_authority, "convenience")

    def test_operator_manual_accept_reads_manual(self):
        r = _post(self.store, "/api/universe/accept", _accept_body(
            ticker="NICHE", origin="operator_manual",
            grounding_refs="operator:my-primary-research-note"))
        self.assertEqual(r["status"], 303)
        self.assertEqual(accepted_universe(self.store)[0].source_authority, "manual")

    def test_ungrounded_operator_manual_is_400_and_writes_nothing(self):
        # operator_manual with NO explicit evidence ref -> pure-validation refusal (offline).
        r = _post(self.store, "/api/universe/accept", _accept_body(
            ticker="GHOST", origin="operator_manual", grounding_refs=""))
        self.assertEqual(r["status"], 400)
        self.assertIn("operator-supplied evidence ref", r["body"])
        self.assertEqual(AcceptedUniverseStore(self.store).read_all(), ())

    def test_no_name_is_400_and_writes_nothing(self):
        r = _post(self.store, "/api/universe/accept", _accept_body(accepted_by=""))
        self.assertEqual(r["status"], 400)
        self.assertEqual(AcceptedUniverseStore(self.store).read_all(), ())

    def test_bad_body_is_400(self):
        r = _post(self.store, "/api/universe/accept", "not-a-dict")
        self.assertEqual(r["status"], 400)

    def test_a_trade_like_universe_route_is_403(self):
        for path in ("/api/universe/order", "/api/universe/buy", "/api/universe/trade"):
            resp = _post(self.store, path, {"ticker": "ZZZ"})
            self.assertEqual(resp["status"], 403, path)

    def test_get_is_read_only(self):
        self.assertEqual(_get(self.store, "/api/universe/accept")["status"], 405)


# =========================================================================== #
# C. UD-2 AI leads: labelled UNVERIFIED, grounded-accept form, not auto-added   #
# =========================================================================== #
class AiLeadTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="univ_ai_")
        _seed_ai_suggestion(self.store)
        self.html = _get(self.store, "/universe")["body"]

    def test_ai_leads_are_labelled_unverified(self):
        self.assertIn("UNVERIFIED", self.html)
        self.assertIn("Edge robotics", self.html)
        self.assertIn("ACME", self.html)

    def test_each_ai_ticker_has_a_grounded_accept_form(self):
        self.assertIn('value="ai_suggestion_grounded"', self.html)
        self.assertIn("Ground &amp; accept ACME", self.html)

    def test_an_ai_suggestion_is_not_auto_added_to_the_universe(self):
        self.assertEqual(accepted_universe(self.store), ())   # display-only until grounded+accepted

    def test_ai_lead_page_has_no_trade_word_or_score_token(self):
        self.assertEqual(_TRADE_WORD.findall(self.html), [])
        low = self.html.lower()
        for token in _SCORE_TOKENS:
            self.assertNotIn(token, low)


if __name__ == "__main__":
    unittest.main()
