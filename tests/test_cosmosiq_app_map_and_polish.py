"""UX-5 -- the Map tab (the immersive Universe Canvas framed READ-ONLY as a VIEW), the completed
How It Works + Evidence & Trust tabs, and the final cockpit coherence pass. Tested OFFLINE through
the pure dispatcher only (no server, no socket, no clock).

Covers, per the UX-5 scope:

* ``/map`` frames the generated Universe Canvas when present (an <iframe> + a direct link to
  ``/map/canvas`` + the compact celestial legend), and shows the honest build-command empty state
  when absent -- never a fabricated star-field, never a dead link. ``/map/canvas`` serves the
  generated ``universe.html`` bytes VERBATIM (200, text/html) and the Map never rewrites or
  duplicates the canvas.
* ``/how-it-works`` explains the WHOLE real loop (current evidence -> signals -> theme pulses ->
  opportunities -> capital recommendation -> YOU act in your own brokerage -> you log the fill
  (record-only) -> portfolio intelligence + learning), states the guardrails plainly, and links
  every stage to its tab.
* ``/evidence`` is a real trust surface: the latest run DQ gate + gaps, source health, agent
  health, the source-authority ladder, a determinism note, and the honest shadow-only / Manual
  Review posture -- with an honest empty state when there are no runs.
* the final coherence pass: all EIGHT tabs render 200, full-width + scrollable, carry the quiet
  honest chip, have ZERO trade affordance (strict word-boundary sweep), no score / rank token, no
  secret value, no default-store fixture leak; a trade-like route -> 403; and the ci_gate-level
  trade / secret regexes find nothing on any tab.
* determinism (same store + now -> byte-identical) and the untouched paths (universe_ui demo build
  + reality_mesh default pulse) stay byte-identical.
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

from cosmosiq_app.api import EXECUTION_REFUSAL, dispatch
from cosmosiq_app.app_assets import APP_CSS
from cosmosiq_app import pages as P

_NOW1 = "2026-06-29T00:00:00Z"
_NOW2 = "2026-06-30T00:00:00Z"

# The eight primary tabs (the final coherence-pass surface).
_TAB_PATHS = ("/", "/opportunities", "/research", "/portfolio", "/journal",
              "/evidence", "/how-it-works", "/map")

_FIXTURE_TICKERS = ("IREN", "NVDA", "AAPL", "TSLA", "AAOI", "AMBA", "META")

# Strict word-boundary trade verbs -- ZERO may appear on any cockpit page.
_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
# Score-like tokens -- ZERO may appear (labels + ranges + counts only).
_SCORE_TOKENS = ("score", "rank", "rating", "investab")
_LIVE_WORD = re.compile(r"\blive\b", re.IGNORECASE)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN"),
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline UX-5 tests")


_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _call(store_dir, method, path, body=None, query=None, now=""):
    return dispatch({"method": method, "path": path, "query": query or {}, "body": body},
                    store_dir=store_dir, now=now)


def _get(store_dir, path):
    return _call(store_dir, "GET", path)["body"]


def _seed(store_dir, run_id, now):
    r = dispatch(
        {"method": "POST", "path": "/api/pulse", "query": {},
         "body": {"watchlist": ["IREN", "NVDA"], "themes": ["physical_ai", "robotics"],
                  "now": now, "run_id": run_id}},
        store_dir=store_dir)
    assert r["status"] == 200, r
    return r


# =========================================================================== #
# 1. The Map tab -- the immersive Universe Canvas framed READ-ONLY             #
# =========================================================================== #
class MapPresentTests(unittest.TestCase):
    """The generated canvas EXISTS (the repo's generated/universe_ui/universe.html)."""

    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="ux5_map_present_")
        # Sanity: the default resolution points at the real, present canvas.
        self.assertTrue(P.generated_canvas_present())

    def test_map_frames_the_canvas_and_links_to_map_canvas(self):
        html = _get(self.store, "/map")
        self.assertIn('src="/map/canvas"', html)          # the iframe frames it
        self.assertIn('class="canvas-frame"', html)
        self.assertIn('href="/map/canvas"', html)         # a direct "open" link too

    def test_map_shows_the_celestial_legend(self):
        html = _get(self.store, "/map")
        for pair in ("Galaxy = Mega Theme", "Planet = Company", "Star = Bottleneck",
                     "Comet = Catalyst", "Black Hole = Risk"):
            self.assertIn(pair, html, pair)

    def test_map_canvas_serves_the_generated_bytes_verbatim(self):
        resp = _call(self.store, "GET", "/map/canvas")
        self.assertEqual(resp["status"], 200)
        self.assertTrue(resp["headers"]["Content-Type"].startswith("text/html"))
        with open(P.generated_canvas_path(), encoding="utf-8") as fh:
            expected = fh.read()
        self.assertEqual(resp["body"], expected)          # AS-IS, never rewritten

    def test_map_view_does_not_inline_or_duplicate_the_canvas(self):
        # The /map page frames the canvas by REFERENCE (iframe src); it must not inline the
        # whole (large) generated document into itself.
        canvas = _get(self.store, "/map/canvas")
        page = _get(self.store, "/map")
        self.assertLess(len(page), len(canvas))           # the page is a light frame
        # a distinctive chunk of the canvas body is NOT copied into the map page
        needle = canvas[len(canvas) // 2: len(canvas) // 2 + 200]
        self.assertNotIn(needle, page)


class MapAbsentTests(unittest.TestCase):
    """No canvas generated (COSMOSIQ_CANVAS_DIR points at an empty temp dir)."""

    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="ux5_map_absent_")
        self.empty_canvas = tempfile.mkdtemp(prefix="ux5_no_canvas_")
        self._prev = os.environ.get(P.GENERATED_CANVAS_ENV)
        os.environ[P.GENERATED_CANVAS_ENV] = self.empty_canvas

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(P.GENERATED_CANVAS_ENV, None)
        else:
            os.environ[P.GENERATED_CANVAS_ENV] = self._prev

    def test_map_shows_the_honest_build_command_empty_state(self):
        self.assertFalse(P.generated_canvas_present())
        html = _get(self.store, "/map")
        self.assertIn("PYTHONPATH=src python3 -m universe_ui --out generated/universe_ui", html)
        self.assertIn("read-only intelligence map", html)
        self.assertNotIn('class="canvas-frame"', html)    # no fabricated frame
        # still self-explanatory: the legend is shown even in the empty state
        self.assertIn("Galaxy = Mega Theme", html)

    def test_map_canvas_is_404_when_absent(self):
        self.assertEqual(_call(self.store, "GET", "/map/canvas")["status"], 404)


# =========================================================================== #
# 2. How It Works -- the WHOLE real loop, plainly, linked to the tabs         #
# =========================================================================== #
class HowItWorksTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="ux5_hiw_")
        self.html = _get(self.store, "/how-it-works")

    def test_explains_the_full_loop_including_your_action_and_the_ledger(self):
        low = self.html.lower()
        self.assertIn("evidence", low)
        self.assertIn("signals", low)
        self.assertIn("theme pulses", low)
        self.assertIn("opportunities", low)
        self.assertIn("recommendation", low)
        self.assertIn("you act", low)                     # YOUR action stage
        self.assertIn("your own brokerage", low)
        self.assertIn("record-only", low)                 # the record-only Portfolio ledger
        self.assertIn("portfolio ledger", low)
        self.assertIn("learning", low)

    def test_states_the_guardrails_plainly(self):
        self.assertIn("Manual Review Only", self.html)
        self.assertIn("No brokerage connection", self.html)
        self.assertIn("automated trading", self.html)
        self.assertIn("Plain labels", self.html)          # labels, not hidden numbers
        self.assertIn("Evidence-cited", self.html)

    def test_links_each_stage_to_its_tab(self):
        for href in ('href="/evidence"', 'href="/research"', 'href="/opportunities"',
                     'href="/portfolio"', 'href="/journal"'):
            self.assertIn(href, self.html, href)


# =========================================================================== #
# 3. Evidence & Trust -- the trust / data-quality surface                     #
# =========================================================================== #
class EvidenceTests(unittest.TestCase):
    def test_empty_state_is_honest_but_still_a_trust_surface(self):
        store = tempfile.mkdtemp(prefix="ux5_ev_empty_")
        html = _get(store, "/evidence")
        # the static trust scaffolding is present even with no runs ...
        self.assertIn("Source-authority ladder", html)
        self.assertIn("SEC filing", html)
        self.assertIn("never canonical", html)            # manual is never canonical
        self.assertIn("Manual Review Only", html)
        self.assertIn("Shadow-only", html)
        # ... and the run-level snapshot is an honest empty state
        self.assertIn("No persisted runs yet", html)

    def test_seeded_surface_shows_dq_gate_agent_health_and_gaps(self):
        store = tempfile.mkdtemp(prefix="ux5_ev_seeded_")
        _seed(store, "RUN-EV-1", _NOW1)
        html = _get(store, "/evidence")
        self.assertIn("Data-quality gate", html)
        self.assertIn("Agent health", html)
        self.assertIn("Data gaps", html)
        self.assertIn("Source health", html)
        self.assertIn("Source-authority ladder", html)
        self.assertIn("Replay", html)                     # determinism / replay note
        self.assertIn('href="/replay/RUN-EV-1"', html)


# =========================================================================== #
# 4. Final coherence pass -- every one of the 8 tabs, honest guardrails hold   #
# =========================================================================== #
class CoherenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty = tempfile.mkdtemp(prefix="ux5_empty_")
        cls.seeded = tempfile.mkdtemp(prefix="ux5_seeded_")
        _seed(cls.seeded, "RUN-COH-1", _NOW1)
        cls.empty_pages = {p: _get(cls.empty, p) for p in _TAB_PATHS}
        cls.seeded_pages = {p: _get(cls.seeded, p) for p in _TAB_PATHS}
        cls.all_pages = list(cls.empty_pages.items()) + list(cls.seeded_pages.items())

    def test_all_eight_tabs_render_200_html(self):
        for path in _TAB_PATHS:
            r = _call(self.seeded, "GET", path)
            self.assertEqual(r["status"], 200, path)
            self.assertTrue(r["headers"]["Content-Type"].startswith("text/html"), path)

    def test_full_width_scrollable_shell_and_quiet_honest_chip(self):
        # full-width CSS + no overflow lock (scrolls naturally)
        self.assertRegex(APP_CSS, r"\.wrap\{[^}]*width:100%")
        self.assertNotIn("overflow:hidden", APP_CSS)
        for path, html in self.all_pages:
            self.assertIn('<div class="wrap">', html, path)   # full-width content area
            self.assertIn('<nav class="tabs">', html, path)   # the 8-tab nav
            self.assertIn('class="chip"', html, path)         # the quiet honest chip
            self.assertIn("Manual Review", html, path)

    def test_each_tab_marks_exactly_its_own_tab_active(self):
        for path in _TAB_PATHS:
            html = _get(self.seeded, path)
            self.assertIn('class="navlink here" href="{0}"'.format(path), html, path)
            self.assertEqual(html.count('class="navlink here"'), 1, path)

    def test_zero_trade_affordance_on_any_tab(self):
        for path, html in self.all_pages:
            self.assertEqual(_TRADE_WORD.findall(html), [], "trade verb on {0}".format(path))

    def test_zero_score_rank_rating_tokens_on_any_tab(self):
        for path, html in self.all_pages:
            low = html.lower()
            for token in _SCORE_TOKENS:
                self.assertNotIn(token, low, "score token {0!r} on {1}".format(token, path))

    def test_no_live_overclaim_on_the_default_ui(self):
        for path, html in self.empty_pages.items():
            self.assertIsNone(_LIVE_WORD.search(html), path)

    def test_no_secret_value_on_any_tab(self):
        for path, html in self.all_pages:
            for pattern in _SECRET_VALUE_PATTERNS:
                self.assertIsNone(pattern.search(html), path)

    def test_no_fixture_ticker_in_the_default_empty_store_ui(self):
        for path, html in self.empty_pages.items():
            for ticker in _FIXTURE_TICKERS:
                self.assertNotRegex(html, r"\b{0}\b".format(ticker),
                                    "{0} leaked into default {1}".format(ticker, path))

    def test_trade_like_routes_are_403(self):
        for path in ("/api/orders", "/api/buy", "/api/trade", "/api/execution/submit",
                     "/map/buy", "/opportunities/sell"):
            r = _call(self.empty, "GET", path, body={"ticker": "IREN"})
            self.assertEqual(r["status"], 403, path)
            self.assertEqual(r["body"]["error"], EXECUTION_REFUSAL)

    def test_ci_gate_level_trade_and_secret_regexes_find_nothing(self):
        # the standing ci_gate guardrail regexes must also come up clean on every tab
        from cosmosiq_ops.ci_gate import SECRET_VALUE_PATTERNS, TRADE_WORD_RE
        for path, html in self.all_pages:
            self.assertIsNone(TRADE_WORD_RE.search(html), "ci_gate trade regex on {0}".format(path))
            for pattern in SECRET_VALUE_PATTERNS:
                self.assertIsNone(pattern.search(html), "ci_gate secret on {0}".format(path))


# =========================================================================== #
# 5. Determinism + the untouched paths stay byte-identical                    #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_pages_render_byte_identically_for_identical_requests(self):
        with tempfile.TemporaryDirectory() as d:
            _seed(d, "RUN-DET-5", _NOW1)
            for path in _TAB_PATHS + ("/map/canvas",):
                a = _call(d, "GET", path, now=_NOW2)
                b = _call(d, "GET", path, now=_NOW2)
                self.assertEqual(json.dumps(a, sort_keys=True),
                                 json.dumps(b, sort_keys=True), path)

    def test_universe_ui_demo_build_byte_identical(self):
        from universe_ui.app import build_universe_app
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                with open(a[name], "rb") as fa, open(b[name], "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(), name)

    def test_reality_mesh_default_pulse_byte_identical(self):
        import reality_mesh as rm
        first = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW1)
        again = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW1)
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
