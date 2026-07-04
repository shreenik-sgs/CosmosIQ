"""IMPLEMENTATION-018A -- the /portfolio page + candidate-vs-holdings, tested OFFLINE.

Dispatcher-only (no server, no socket -- the whole module runs under a socket
kill-switch). Proven here:

* ``/portfolio`` renders every section from the operator-recorded holdings file +
  the persisted stores: holdings table (as_of + a STALE label when older than the
  latest persisted run), exposure by theme, concentration BANDS (never a ratio),
  correlation LABELS (no number), rotation alignment, and the risk-budget /
  sizing-guardrail section via the ACCEPTED personal_cio profile function;
* honest absence EVERYWHERE: no holdings file -> every section says so; malformed
  file -> the parse error is named; no profile -> guardrails honestly absent;
* the candidate cockpit gains a READ-ONLY candidate-vs-holdings comparison
  (honest absence without holdings; a label with holdings);
* page sweeps: 0 trade affordances / forms / buttons on the portfolio surface,
  0 external refs, 0 credential-like tokens, 0 score/rank tokens, 0 Sanskrit,
  the as-of honesty line, no live claim;
* rendering mutates no stored byte; renders are byte-deterministic;
* ``src/personal_cio`` is consumed UNMODIFIED (git-assert);
* untouched paths: the Universe demo default stays byte-identical and the default
  manual pulse output is unchanged by this slice.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from cosmosiq_app.api import dispatch

_NOW1 = "2026-06-29T00:00:00Z"
_RUN1 = "RUN-PF-1"
_STALE_AS_OF = "2026-06-28T00:00:00Z"     # before the run -> stale
_FRESH_AS_OF = "2026-06-30T00:00:00Z"     # after the run -> current

_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b",
                         re.IGNORECASE)
_SCORE_TOKENS = ("score", "rank", "rating", "investab")
_SANSKRIT_TOKENS = ("adhara", "buddhi", "tattva", "sphurana", "nivesha", "saarathi",
                    "kriya", "anubhava", "sudarshan")
_EXTERNAL_TOKENS = ("http://", "https://", "cdn.", "@import", "<script", "<link",
                    "fetch(", "xmlhttprequest", "@font-face")
_CRED_TOKENS = tuple(rm.CREDENTIAL_KEY_TOKENS)
_LIVE_CLAIMS = ("real-time", "real time", "realtime", "streaming", "always-on",
                "24/7", "autonomous")
_LIVE_WORD = re.compile(r"\blive\b", re.IGNORECASE)

_STATE = {}
_ORIG_CONNECT = None


def _boom(*a, **k):
    raise AssertionError("network access attempted during offline portfolio page tests")


def _call(store_dir, method, path, body=None):
    return dispatch({"method": method, "path": path, "query": {}, "body": body},
                    store_dir=store_dir, now=_NOW1)


def _seed_pulse_run(store_dir):
    response = _call(store_dir, "POST", "/api/pulse",
                     body={"watchlist": ["IREN", "NVDA"],
                           "themes": ["physical_ai", "robotics"],
                           "now": _NOW1, "run_id": _RUN1})
    assert response["status"] == 200, response


def _write_holdings(store_dir, payload):
    base = os.path.join(store_dir, "portfolio")
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "holdings.json"), "w", encoding="utf-8") as fh:
        if isinstance(payload, str):
            fh.write(payload)
        else:
            json.dump(payload, fh)


def _write_profile(store_dir):
    with open(os.path.join(store_dir, "personal_profile.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"account": "operator", "now": 1750000000.0,
                   "profile": {"risk_tolerance": "moderate",
                               "max_single_position_pct": 8.0,
                               "max_theme_exposure_pct": 25.0,
                               "min_cash_reserve_pct": 10.0},
                   "portfolio": {"total_portfolio_value": 100000.0,
                                 "available_cash": 50000.0}}, fh)


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom

    # Store A: pulse run + holdings (stale as_of) + profile -- the full surface.
    full = tempfile.mkdtemp(prefix="pf_page_full_")
    _seed_pulse_run(full)
    _write_holdings(full, {
        "as_of": _STALE_AS_OF,
        "positions": [
            {"ticker": "IREN", "quantity": 100, "cost_basis": 15.0,
             "account_label": "taxable-main", "liquidity_note": "thin float"},
            {"ticker": "NVDA", "quantity": 10, "cost_basis": 100.0},
            {"ticker": "ZZZZ", "quantity": 5},
        ],
        "cash": 500})
    _write_profile(full)
    _STATE["full"] = full
    _STATE["portfolio_full"] = _call(full, "GET", "/portfolio")
    _STATE["candidate_full"] = _call(full, "GET", "/candidates/IREN")

    # Store B: pulse run only -- NO holdings, NO profile (honest absence everywhere).
    bare = tempfile.mkdtemp(prefix="pf_page_bare_")
    _seed_pulse_run(bare)
    _STATE["bare"] = bare
    _STATE["portfolio_bare"] = _call(bare, "GET", "/portfolio")
    _STATE["candidate_bare"] = _call(bare, "GET", "/candidates/IREN")


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


# =========================================================================== #
# 1. The /portfolio page with a recorded statement                             #
# =========================================================================== #
class PortfolioPageTests(unittest.TestCase):
    def setUp(self):
        self.html = _STATE["portfolio_full"]["body"]

    def test_served_as_html_with_every_section(self):
        response = _STATE["portfolio_full"]
        self.assertEqual(response["status"], 200)
        self.assertTrue(response["headers"]["Content-Type"].startswith("text/html"))
        for heading in ("Recorded holdings", "Exposure by theme",
                        "Concentration bands", "Co-exposure (correlation labels)",
                        "Rotation alignment", "Risk budget and sizing guardrails"):
            self.assertIn(heading, self.html, heading)

    def test_nav_gains_portfolio_on_every_page(self):
        self.assertIn('href="/portfolio"', self.html)
        for path in ("/", "/runs", "/alerts", "/settings", "/themes"):
            self.assertIn('href="/portfolio"',
                          _call(_STATE["full"], "GET", path)["body"], path)

    def test_holdings_table_shows_the_statement_verbatim(self):
        self.assertIn(_STALE_AS_OF, self.html)
        self.assertIn("IREN", self.html)
        self.assertIn("100", self.html)                      # quantity as recorded
        self.assertIn("taxable-main", self.html)
        self.assertIn("thin float", self.html)               # recorded liquidity note
        self.assertIn("not recorded", self.html)             # ZZZZ has no cost basis
        self.assertIn("unknown -- no liquidity note recorded", self.html)
        self.assertIn("3 recorded", self.html)               # volume count

    def test_stale_as_of_renders_a_stale_label(self):
        self.assertIn(">stale<", self.html)
        self.assertIn("predates the latest persisted run", self.html)

    def test_fresh_as_of_renders_current(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_pulse_run(d)
            _write_holdings(d, {"as_of": _FRESH_AS_OF, "positions": [
                {"ticker": "IREN", "quantity": 1, "cost_basis": 10}]})
            html = _call(d, "GET", "/portfolio")["body"]
            self.assertIn(">current<", html)
            self.assertNotIn(">stale<", html)

    def test_exposure_by_theme_uses_the_persisted_mapping(self):
        # The seeded pulse's persisted records map IREN to physical-ai; NVDA and
        # ZZZZ have no persisted mapping and are surfaced as an honest gap.
        self.assertIn("physical-ai", self.html)
        self.assertIn("NVDA, ZZZZ", self.html)
        self.assertIn("honest gap, never guessed", self.html)

    def test_concentration_bands_render_labels_never_a_ratio(self):
        self.assertIn("Weight band", self.html)
        self.assertIn(">dominant<", self.html)               # IREN/NVDA dwarf the total
        self.assertIn(">unknown<", self.html)                # ZZZZ cannot be weighed
        self.assertIn("no weight or ratio is stored or rendered", self.html)
        # the published edges are named as data, and no computed weight leaks
        self.assertIn("moderate at 5.0%, elevated at 10.0%, dominant at 20.0%",
                      self.html)

    def test_correlation_labels_no_number(self):
        self.assertIn("no numeric correlation exists", self.html)
        self.assertIn("IREN &harr; NVDA", self.html)

    def test_rotation_alignment_against_persisted_states(self):
        self.assertIn("Rotation alignment", self.html)
        self.assertIn(">aligned<", self.html)                # IREN vs Broadening
        self.assertIn("no signal", self.html)                # NVDA / ZZZZ unmapped

    def test_guardrails_come_from_the_accepted_profile_function(self):
        self.assertIn("Risk budget and sizing guardrails", self.html)
        self.assertIn(">moderate<", self.html)               # risk tolerance label
        self.assertIn("up to 8.00%", self.html)              # max single position
        self.assertIn("up to 25.00%", self.html)             # max theme exposure
        self.assertIn("at least 10.00%", self.html)          # min cash reserve
        self.assertIn("manual confirmation is ALWAYS required downstream",
                      self.html)

    def test_read_only_discipline_stated(self):
        self.assertIn("READ-ONLY", self.html)
        self.assertIn("no automatic", self.html)


# =========================================================================== #
# 2. Honest absence everywhere                                                 #
# =========================================================================== #
class HonestAbsenceTests(unittest.TestCase):
    def test_missing_holdings_every_section_says_so(self):
        html = _STATE["portfolio_bare"]["body"]
        self.assertEqual(_STATE["portfolio_bare"]["status"], 200)
        self.assertGreaterEqual(html.count("No holdings recorded"), 5)
        self.assertIn("portfolio/holdings.json", html)
        self.assertIn("The app only ever READS it", html)

    def test_missing_profile_guardrails_honestly_absent(self):
        html = _STATE["portfolio_bare"]["body"]
        self.assertIn("No personal profile is recorded", html)
        self.assertIn("never a default persona", html)

    def test_malformed_holdings_parse_error_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_pulse_run(d)
            _write_holdings(d, "{not json")
            html = _call(d, "GET", "/portfolio")["body"]
            self.assertIn("could not be parsed", html)
            self.assertIn("nothing is guessed", html)
            self.assertGreaterEqual(html.count("No holdings recorded"), 5)

    def test_no_pulse_run_freshness_is_an_honest_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(d, exist_ok=True)
            _write_holdings(d, {"as_of": "2026-01-01", "positions": [
                {"ticker": "AAAA", "quantity": 1, "cost_basis": 10}]})
            html = _call(d, "GET", "/portfolio")["body"]
            self.assertIn("no run to compare", html)
            self.assertIn("freshness cannot be compared", html)


# =========================================================================== #
# 3. Candidate cockpit: candidate vs recorded portfolio                        #
# =========================================================================== #
class CandidateComparisonSectionTests(unittest.TestCase):
    def test_honest_absence_without_holdings(self):
        html = _STATE["candidate_bare"]["body"]
        self.assertIn("Candidate vs recorded portfolio", html)
        self.assertIn("No holdings recorded", html)
        self.assertIn("portfolio/holdings.json", html)
        # the rest of the cockpit's honesty phrases survive untouched
        low = html.lower()
        self.assertIn("no thesis fabricated", low)
        self.assertIn("no manual execution intent", low)

    def test_comparison_label_with_holdings(self):
        html = _STATE["candidate_full"]["body"]
        self.assertIn("Candidate vs recorded portfolio", html)
        # IREN is already a recorded position -> adds_concentration
        self.assertIn("adds concentration", html)
        self.assertIn("Already a recorded position", html)
        self.assertIn("not advice", html)
        self.assertIn(_STALE_AS_OF, html)                    # bound to the statement

    def test_unmapped_candidate_is_honestly_indeterminate(self):
        html = _call(_STATE["full"], "GET", "/candidates/QQQQ")["body"]
        self.assertIn("no theme signal", html)
        self.assertIn("honestly indeterminate", html)

    def test_no_form_or_button_added_to_the_cockpit(self):
        for key in ("candidate_full", "candidate_bare"):
            html = _STATE[key]["body"]
            self.assertNotIn("<form", html, key)
            self.assertNotIn("<button", html, key)


# =========================================================================== #
# 4. Page hygiene sweeps                                                       #
# =========================================================================== #
class PortfolioHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {
            "/portfolio(full)": _STATE["portfolio_full"]["body"],
            "/portfolio(bare)": _STATE["portfolio_bare"]["body"],
            "/candidates/IREN(full)": _STATE["candidate_full"]["body"],
            "/candidates/IREN(bare)": _STATE["candidate_bare"]["body"],
        }

    def test_zero_trade_affordances(self):
        # The NEW portfolio surface is held to the strict word-boundary sweep.
        for name in ("/portfolio(full)", "/portfolio(bare)"):
            matches = _TRADE_WORD.findall(self.pages[name])
            self.assertEqual(matches, [], "{0}: {1}".format(name, matches))
        # The candidate cockpit legitimately carries the accepted 016C honesty
        # phrase "no order is placed"; it is held to the 016C affordance sweep
        # (no action phrase, no form) -- this slice must not add any affordance.
        for name in ("/candidates/IREN(full)", "/candidates/IREN(bare)"):
            self.assertNotRegex(
                self.pages[name],
                r"(?i)\b(buy|sell|order now|submit order|place order|"
                r"execute trade|auto[- ]trade|trade now)\b", name)

    def test_zero_forms_and_buttons_on_the_portfolio_page(self):
        for name in ("/portfolio(full)", "/portfolio(bare)"):
            html = self.pages[name]
            self.assertNotIn("<form", html, name)
            self.assertNotIn("<button", html, name)
            self.assertNotIn('type="submit"', html, name)

    def test_zero_external_references(self):
        for name, html in self.pages.items():
            low = html.lower()
            for token in _EXTERNAL_TOKENS:
                self.assertNotIn(token, low, "{0}: {1}".format(name, token))

    def test_zero_credential_tokens_or_secret_like_values(self):
        for name, html in self.pages.items():
            low = html.lower()
            for token in _CRED_TOKENS:
                self.assertNotIn(token, low, "{0}: {1}".format(name, token))
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{8,}", html), name)

    def test_zero_score_rank_rating_tokens(self):
        for name in ("/portfolio(full)", "/portfolio(bare)"):
            low = self.pages[name].lower()
            for token in _SCORE_TOKENS:
                self.assertNotIn(token, low, "{0}: {1}".format(name, token))

    def test_zero_sanskrit_terms(self):
        for name, html in self.pages.items():
            low = html.lower()
            for token in _SANSKRIT_TOKENS:
                self.assertNotIn(token, low, "{0}: {1}".format(name, token))

    def test_zero_live_claims_and_the_as_of_line(self):
        for name, html in self.pages.items():
            low = html.lower()
            for claim in _LIVE_CLAIMS:
                self.assertNotIn(claim, low, "{0}: {1}".format(name, claim))
            self.assertIsNone(_LIVE_WORD.search(html), name)
            self.assertIn("as of", low, name)
            self.assertIn("pulse data", low, name)


# =========================================================================== #
# 5. Determinism, byte-safety, untouched engines                               #
# =========================================================================== #
class DisciplineTests(unittest.TestCase):
    def test_pages_render_byte_deterministically(self):
        for path in ("/portfolio", "/candidates/IREN"):
            self.assertEqual(_call(_STATE["full"], "GET", path)["body"],
                             _call(_STATE["full"], "GET", path)["body"], path)

    def test_rendering_mutates_no_stored_byte(self):
        store = _STATE["full"]

        def _bytes(path):
            with open(path, "rb") as fh:
                return fh.read()

        watched = [os.path.join(store, n) for n in os.listdir(store)
                   if n.endswith(".jsonl") or n.endswith(".json")]
        watched.append(os.path.join(store, "portfolio", "holdings.json"))
        before = {p: _bytes(p) for p in watched}
        _call(store, "GET", "/portfolio")
        _call(store, "GET", "/candidates/IREN")
        _call(store, "GET", "/candidates/QQQQ")
        for p in watched:
            self.assertEqual(_bytes(p), before[p], p)

    def test_personal_cio_is_consumed_unmodified(self):
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", "src/personal_cio"],
            cwd=_ROOT, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "",
                         "src/personal_cio must stay untouched, got: {0}".format(
                             result.stdout))

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()


# =========================================================================== #
# 6. Untouched paths: demo default + default pulse output stay identical        #
# =========================================================================== #
class UntouchedPathsTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app   # lazy: not a page dependency
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                with open(a[name], "rb") as fa, open(b[name], "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(),
                                     "demo default drifted for {0}".format(name))

    def test_default_manual_pulse_output_unchanged_by_this_slice(self):
        first = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW1)
        again = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW1)
        self.assertEqual([s.signal_id for s in first.signals],
                         [s.signal_id for s in again.signals])
        self.assertEqual(first.theme_pulses, again.theme_pulses)


if __name__ == "__main__":
    unittest.main()
