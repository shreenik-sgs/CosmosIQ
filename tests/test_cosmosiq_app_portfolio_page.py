"""IMPLEMENTATION-UX-3 -- the Portfolio page + the "Log an executed fill" form.

Dispatcher-only, OFFLINE (the whole module runs under a socket kill-switch; no
server, no socket, no wall clock). This surfaces the UX-2 manual position ledger
in the cockpit and adds a SANCTIONED operator form to LOG a fill the operator
already executed at their OWN brokerage. Proven here:

* the ledger holdings table renders from ``compute_holdings`` -- net quantity,
  average cost basis, concentration BAND (never a score), linked recommendation,
  last fill date -- plus the honest empty state when nothing is recorded;
* ``POST /api/portfolio/record-fill`` with a valid fill records it (append-only)
  and REDIRECTS (303) to ``/portfolio``; a second bought fill updates the average
  and a sold fill reduces the net; a bad input re-renders with an honest error and
  writes NOTHING; it is RECORD-ONLY (no broker, no order submission, no network);
* copy discipline: PAST-TENSE ``Bought`` / ``Sold`` (never a ``Buy`` / ``Sell``
  button), the submit button ``Record this fill``, and the honest disclaimer
  (never connects to a brokerage / never places orders);
* zero trade affordance on the page (strict word-boundary sweep AND the accepted
  ci-gate action-phrase sweep both find NONE); a real order route -> 403;
* the prod_check ``no_trade_control`` scan STILL passes with the page live;
* concentration is BANDS not scores; no hidden score / rank; no secret; no default
  fixture ticker on the empty-store page (a logged ticker legitimately appears
  after the operator logs it);
* deterministic render; the retained 018A statement sections still render; the
  universe_ui demo + the reality_mesh default pulse stay byte-identical; offline.
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
from cosmosiq_app.api import dispatch, EXECUTION_REFUSAL
from cosmosiq_ops.ci_gate import TRADE_WORD_RE
from cosmosiq_ops.prod_check import _scan_no_trade_control

_NOW = "2026-06-29T00:00:00Z"
_RUN = "RUN-UX3-1"

# The strict per-tab affordance sweep (identical to the standing cockpit-shell list):
# ZERO of these word-boundary trade verbs may appear on the portfolio surface.
_STRICT_TRADE = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
_SCORE_TOKENS = ("score", "rank", "rating", "investab")
_CRED_TOKENS = tuple(rm.CREDENTIAL_KEY_TOKENS)
_FIXTURE_TICKERS = ("IREN", "NVDA", "AAOI")

_ORIG_CONNECT = None


def _boom(*a, **k):
    raise AssertionError("network access attempted during offline UX-3 portfolio tests")


def _call(store_dir, method, path, body=None):
    return dispatch({"method": method, "path": path, "query": {}, "body": body},
                    store_dir=store_dir, now=_NOW)


def _seed_pulse(store_dir):
    r = _call(store_dir, "POST", "/api/pulse",
              body={"watchlist": ["ABC", "XYZ"], "themes": ["physical_ai"],
                    "now": _NOW, "run_id": _RUN})
    assert r["status"] == 200, r


def _fill(store_dir, **fields):
    fields.setdefault("at", _NOW)
    return _call(store_dir, "POST", "/api/portfolio/record-fill", body=fields)


def _ledger_lines(store_dir):
    path = os.path.join(store_dir, "position_ledger.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, "rb") as fh:
        return [ln for ln in fh.read().split(b"\n") if ln.strip()]


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


# =========================================================================== #
# 1. The ledger holdings table + empty state                                   #
# =========================================================================== #
class LedgerHoldingsTests(unittest.TestCase):
    def test_empty_store_shows_honest_empty_state_and_the_form(self):
        with tempfile.TemporaryDirectory() as d:
            r = _call(d, "GET", "/portfolio")
            self.assertEqual(r["status"], 200)
            self.assertTrue(r["headers"]["Content-Type"].startswith("text/html"))
            html = r["body"]
            self.assertIn("No positions recorded yet", html)
            self.assertIn("log the fill below", html)
            # the sanctioned log-fill form is present and posts to the record route
            self.assertIn('action="/api/portfolio/record-fill"', html)
            self.assertIn("Record this fill", html)

    def test_a_bought_fill_records_and_shows_net_and_average_cost(self):
        with tempfile.TemporaryDirectory() as d:
            r = _fill(d, ticker="ABC", side="bought", quantity="100",
                      price="10.50", trade_date="2026-01-05")
            self.assertIn(r["status"], (302, 303))
            self.assertEqual(r["headers"]["Location"], "/portfolio")
            html = _call(d, "GET", "/portfolio")["body"]
            self.assertIn("ABC", html)
            self.assertIn(">100<", html)           # net quantity
            self.assertIn("10.50", html)           # average cost basis
            self.assertIn("2026-01-05", html)      # last fill date

    def test_second_bought_updates_the_average_and_a_sold_reduces_net(self):
        with tempfile.TemporaryDirectory() as d:
            _fill(d, ticker="ABC", side="bought", quantity="100",
                  price="10.50", trade_date="2026-01-05")
            _fill(d, ticker="ABC", side="bought", quantity="100",
                  price="20.50", trade_date="2026-01-06")
            html = _call(d, "GET", "/portfolio")["body"]
            self.assertIn("15.50", html)           # (1050 + 2050) / 200
            self.assertIn(">200<", html)           # net after two buys
            _fill(d, ticker="ABC", side="sold", quantity="50",
                  price="25", trade_date="2026-01-07")
            html2 = _call(d, "GET", "/portfolio")["body"]
            self.assertIn(">150<", html2)          # sold reduces the net
            self.assertIn("15.50", html2)          # avg cost basis unchanged by a sale

    def test_concentration_is_a_band_never_a_score(self):
        with tempfile.TemporaryDirectory() as d:
            _fill(d, ticker="ABC", side="bought", quantity="100",
                  price="100", trade_date="2026-01-05")
            _fill(d, ticker="XYZ", side="bought", quantity="1",
                  price="1", trade_date="2026-01-05")
            html = _call(d, "GET", "/portfolio")["body"]
            self.assertIn("Concentration band", html)
            self.assertIn(">dominant<", html)      # ABC dwarfs the total
            self.assertIn(">minimal<", html)       # XYZ is a sliver
            # the thresholds are named as DATA; no computed ratio leaks
            self.assertIn("moderate at 5.0%, elevated at 10.0%, dominant at 20.0%", html)
            for token in _SCORE_TOKENS:
                self.assertNotIn(token, html.lower(), token)

    def test_linked_recommendation_and_recent_fills_render(self):
        with tempfile.TemporaryDirectory() as d:
            _fill(d, ticker="ABC", side="bought", quantity="10", price="5",
                  trade_date="2026-01-04", recommendation_ref="cand:ABC:001",
                  note="acted on the published thesis")
            html = _call(d, "GET", "/portfolio")["body"]
            self.assertIn("cand:ABC:001", html)              # linked recommendation
            self.assertIn("Recent fills you logged", html)
            self.assertIn("acted on the published thesis", html)


# =========================================================================== #
# 2. The record-fill route: record-only, validation, append-only, offline      #
# =========================================================================== #
class RecordFillRouteTests(unittest.TestCase):
    def test_valid_fill_redirects_to_portfolio(self):
        with tempfile.TemporaryDirectory() as d:
            r = _fill(d, ticker="ABC", side="bought", quantity="10",
                      price="5", trade_date="2026-01-04")
            self.assertIn(r["status"], (302, 303))
            self.assertEqual(r["headers"]["Location"], "/portfolio")
            self.assertEqual(len(_ledger_lines(d)), 1)       # exactly one line written

    def test_bad_quantity_rerenders_with_honest_error_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            r = _fill(d, ticker="ABC", side="bought", quantity="oops",
                      price="5", trade_date="2026-01-04")
            self.assertEqual(r["status"], 400)
            self.assertIn("Could not record that fill", r["body"])
            self.assertIn("quantity", r["body"])
            self.assertEqual(_ledger_lines(d), [])           # nothing persisted

    def test_missing_ticker_and_invalid_side_are_refused_without_crash(self):
        with tempfile.TemporaryDirectory() as d:
            r1 = _fill(d, ticker="", side="bought", quantity="1",
                       price="5", trade_date="2026-01-04")
            self.assertEqual(r1["status"], 400)
            self.assertIn("ticker is required", r1["body"])
            r2 = _fill(d, ticker="ABC", side="buy", quantity="1",
                       price="5", trade_date="2026-01-04")
            self.assertEqual(r2["status"], 400)
            self.assertIn("PAST TENSE", r2["body"])
            self.assertEqual(_ledger_lines(d), [])

    def test_get_on_the_record_route_is_405(self):
        with tempfile.TemporaryDirectory() as d:
            r = _call(d, "GET", "/api/portfolio/record-fill")
            self.assertEqual(r["status"], 405)

    def test_append_only_prior_line_is_byte_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            _fill(d, ticker="ABC", side="bought", quantity="10", price="5",
                  trade_date="2026-01-04")
            first = _ledger_lines(d)
            self.assertEqual(len(first), 1)
            # a correction / follow-on is a NEW line; the prior line never mutates
            _fill(d, ticker="ABC", side="sold", quantity="4", price="6",
                  trade_date="2026-01-05")
            second = _ledger_lines(d)
            self.assertEqual(len(second), 2)
            self.assertEqual(second[0], first[0])            # line 1 unchanged, byte-for-byte

    def test_recording_the_identical_fill_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            _fill(d, ticker="ABC", side="bought", quantity="10", price="5",
                  trade_date="2026-01-04")
            _fill(d, ticker="ABC", side="bought", quantity="10", price="5",
                  trade_date="2026-01-04")
            self.assertEqual(len(_ledger_lines(d)), 1)       # no duplicate line

    def test_a_real_order_route_stays_403(self):
        with tempfile.TemporaryDirectory() as d:
            for path in ("/api/orders", "/api/execution/submit", "/api/portfolio/order",
                         "/api/buy"):
                r = _call(d, "GET", path, body={"ticker": "ABC"})
                self.assertEqual(r["status"], 403, path)
                self.assertEqual(r["body"]["error"], EXECUTION_REFUSAL, path)

    def test_the_post_makes_no_network_or_broker_call(self):
        # The whole module runs under the socket kill-switch; a successful record
        # proves record_fill reached only a local file (a broker/network call would
        # have raised).
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()
        with tempfile.TemporaryDirectory() as d:
            r = _fill(d, ticker="ABC", side="bought", quantity="10", price="5",
                      trade_date="2026-01-04")
            self.assertIn(r["status"], (302, 303))


# =========================================================================== #
# 3. Copy discipline: past-tense side, "Record this fill", the disclaimer       #
# =========================================================================== #
class CopyDisciplineTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ux3_copy_")
        self.html = _call(self.d, "GET", "/portfolio")["body"]

    def test_side_control_is_past_tense_not_buy_sell_buttons(self):
        self.assertIn('value="bought"', self.html)
        self.assertIn('value="sold"', self.html)
        self.assertIn("Bought</label>", self.html)
        self.assertIn("Sold</label>", self.html)
        # never an imperative Buy / Sell button or an order-submission control
        self.assertNotIn("Buy</button>", self.html)
        self.assertNotIn("Sell</button>", self.html)
        self.assertNotIn("Submit order", self.html)
        self.assertNotIn("Place trade", self.html)
        self.assertNotIn('type="submit"', self.html)

    def test_submit_button_is_record_this_fill(self):
        self.assertIn("<button>Record this fill</button>", self.html)

    def test_the_honest_disclaimer_is_present(self):
        low = self.html.lower()
        self.assertIn("never connects to a brokerage", low)
        self.assertIn("never places orders", low)
        self.assertIn("brokerage", low)


# =========================================================================== #
# 4. Affordance sweeps + the prod_check no_trade_control scan                   #
# =========================================================================== #
class AffordanceSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty = tempfile.mkdtemp(prefix="ux3_sweep_empty_")
        cls.full = tempfile.mkdtemp(prefix="ux3_sweep_full_")
        _seed_pulse(cls.full)
        _fill(cls.full, ticker="ABC", side="bought", quantity="100", price="10.50",
              trade_date="2026-01-05")
        _fill(cls.full, ticker="ABC", side="sold", quantity="30", price="12",
              trade_date="2026-01-06")
        _fill(cls.full, ticker="XYZ", side="bought", quantity="5", price="2",
              trade_date="2026-01-04", recommendation_ref="cand:XYZ:001")
        cls.pages = {
            "empty": _call(cls.empty, "GET", "/portfolio")["body"],
            "full": _call(cls.full, "GET", "/portfolio")["body"],
            "error": _call(cls.full, "POST", "/api/portfolio/record-fill",
                           body={"ticker": "ABC", "side": "bought", "quantity": "bad",
                                 "price": "1", "trade_date": "2026-01-09",
                                 "at": _NOW})["body"],
        }

    def test_strict_word_boundary_sweep_finds_no_trade_verb(self):
        for name, html in self.pages.items():
            self.assertEqual(_STRICT_TRADE.findall(html), [],
                             "{0}: {1}".format(name, _STRICT_TRADE.findall(html)))

    def test_accepted_ci_gate_action_phrase_sweep_finds_none(self):
        for name, html in self.pages.items():
            self.assertEqual(TRADE_WORD_RE.findall(html), [],
                             "{0}: {1}".format(name, TRADE_WORD_RE.findall(html)))

    def test_prod_check_no_trade_control_still_passes_with_the_page_live(self):
        result = _scan_no_trade_control(_ROOT, _NOW)
        self.assertEqual(result.status, "pass", result.details)

    def test_exactly_one_sanctioned_form_and_no_type_submit(self):
        for name, html in self.pages.items():
            self.assertEqual(html.count('<form class="op-form"'), 1, name)
            self.assertNotIn('type="submit"', html, name)


# =========================================================================== #
# 5. Hygiene: no score / secret / default fixture leak                          #
# =========================================================================== #
class HygieneTests(unittest.TestCase):
    def test_no_score_rank_or_secret_tokens_on_the_populated_page(self):
        with tempfile.TemporaryDirectory() as d:
            _fill(d, ticker="ABC", side="bought", quantity="100", price="10.50",
                  trade_date="2026-01-05")
            low = _call(d, "GET", "/portfolio")["body"].lower()
            for token in _SCORE_TOKENS:
                self.assertNotIn(token, low, token)
            for token in _CRED_TOKENS:
                self.assertNotIn(token, low, token)
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{8,}", low))

    def test_default_empty_store_page_has_no_fixture_ticker(self):
        with tempfile.TemporaryDirectory() as d:
            html = _call(d, "GET", "/portfolio")["body"]
            for ticker in _FIXTURE_TICKERS:
                self.assertFalse(re.search(r"\b" + ticker + r"\b", html),
                                 "fixture ticker {0} leaked into the default page".format(ticker))

    def test_a_logged_ticker_legitimately_appears_after_the_operator_logs_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertNotIn("ABC", _call(d, "GET", "/portfolio")["body"])
            _fill(d, ticker="ABC", side="bought", quantity="1", price="1",
                  trade_date="2026-01-05")
            self.assertIn("ABC", _call(d, "GET", "/portfolio")["body"])   # operator data, not a leak


# =========================================================================== #
# 6. Determinism, read-only render, retained sections, untouched paths          #
# =========================================================================== #
class DisciplineTests(unittest.TestCase):
    def test_render_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            _fill(d, ticker="ABC", side="bought", quantity="10", price="5",
                  trade_date="2026-01-04")
            self.assertEqual(_call(d, "GET", "/portfolio")["body"],
                             _call(d, "GET", "/portfolio")["body"])

    def test_rendering_mutates_no_stored_byte(self):
        with tempfile.TemporaryDirectory() as d:
            _fill(d, ticker="ABC", side="bought", quantity="10", price="5",
                  trade_date="2026-01-04")
            before = _ledger_lines(d)
            _call(d, "GET", "/portfolio")
            _call(d, "GET", "/portfolio")
            self.assertEqual(_ledger_lines(d), before)

    def test_retained_018a_statement_sections_still_render(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_pulse(d)
            base = os.path.join(d, "portfolio")
            os.makedirs(base, exist_ok=True)
            with open(os.path.join(base, "holdings.json"), "w", encoding="utf-8") as fh:
                json.dump({"as_of": "2026-06-30T00:00:00Z",
                           "positions": [{"ticker": "ABC", "quantity": 100,
                                          "cost_basis": 15.0}]}, fh)
            html = _call(d, "GET", "/portfolio")["body"]
            for heading in ("Recorded holdings", "Exposure by theme",
                            "Concentration bands", "Rotation alignment",
                            "Risk budget and sizing guardrails"):
                self.assertIn(heading, html, heading)

    def test_universe_ui_demo_stays_byte_identical(self):
        from universe_ui.app import build_universe_app
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                with open(a[name], "rb") as fa, open(b[name], "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(), name)

    def test_reality_mesh_default_pulse_stays_byte_identical(self):
        first = rm.run_pulse(["ABC", "XYZ"], ["physical_ai"], now=_NOW)
        again = rm.run_pulse(["ABC", "XYZ"], ["physical_ai"], now=_NOW)
        self.assertEqual([s.signal_id for s in first.signals],
                         [s.signal_id for s in again.signals])
        self.assertEqual(first.theme_pulses, again.theme_pulses)

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
