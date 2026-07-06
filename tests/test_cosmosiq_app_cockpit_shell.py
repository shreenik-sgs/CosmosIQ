"""UX-1 -- the CosmosIQ functional cockpit SHELL: full-width + scrollable layout, an 8-tab
top nav, a quiet honest status chip, and a Dashboard home. Tested OFFLINE through the pure
dispatcher only (no server, no socket, no port) under a socket kill-switch.

What this slice proves:

* the eight primary tabs render with their plain-language names + correct hrefs, the current
  tab is marked active, and every OLD route (``/candidates`` -> Opportunities, ``/themes``,
  ``/runs``, ``/alerts``, ``/settings``, ``/companies/<t>``) still resolves so nothing breaks;
* the layout CSS is FULL-WIDTH (no narrow ``max-width:1100px`` centring; the content rule is
  ``width:100%``) and the document SCROLLS naturally (no ``overflow:hidden`` on html/body);
* the status chip is present, COMPACT, and HONEST -- it carries "Manual Review", never claims
  live / production on an empty store, and preserves the full Broker-Disabled + Manual-Review-
  Only honesty in its tooltip / details when a service ran;
* the Dashboard renders honest empty states (no positions -> honest line; no runs -> honest
  line) and a read-only overview with NO trade control;
* the permanent guardrails hold across ALL tabs: zero trade affordances, a trade-like route ->
  403, zero score/rank, no fixture ticker in the default (empty-store) UI, no secret value;
* determinism (same store + same now -> byte-identical bodies) and the untouched paths
  (universe_ui demo build + reality_mesh default pulse) stay byte-identical.
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

from reality_mesh import stores as S
from cosmosiq_app.api import EXECUTION_REFUSAL, dispatch
from cosmosiq_app.app_assets import APP_CSS
from cosmosiq_app.pages import service_mode_indicator

_NOW1 = "2026-06-29T00:00:00Z"
_NOW2 = "2026-06-30T00:00:00Z"

# The eight primary tabs, exactly as the operator will read them.
_TABS = (
    ("Dashboard", "/"),
    ("Opportunities", "/opportunities"),
    ("Company Research", "/research"),
    ("Portfolio", "/portfolio"),
    ("Journal &amp; Learning", "/journal"),
    ("Evidence &amp; Trust", "/evidence"),
    ("How It Works", "/how-it-works"),
    ("Map", "/map"),
)
_TAB_PATHS = tuple(href for _label, href in _TABS)

# Every shell GET page (the 8 tabs + the utility surfaces that must stay reachable).
_SHELL_PATHS = _TAB_PATHS + ("/runs", "/themes", "/alerts", "/settings")

_FIXTURE_TICKERS = ("IREN", "NVDA", "AAPL", "TSLA", "AAOI", "AMBA", "META")

# Word-boundary trade verbs -- ZERO may appear on any cockpit page.
_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
# Score-like tokens -- ZERO may appear (labels + ranges + counts only).
_SCORE_TOKENS = ("score", "rank", "rating", "investab")
# Live / production over-claims -- ZERO on the default empty store.
_LIVE_CLAIMS = ("real-time", "real time", "realtime", "streaming", "always-on", "24/7",
                "autonomous")
_LIVE_WORD = re.compile(r"\blive\b", re.IGNORECASE)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN"),
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline UX-1 shell tests")


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


def _write_health(store_dir, mode):
    health = {"service_mode": mode,
              "source_health_summary": {"coverage_records": 3, "failed_source_records": 0}}
    with open(os.path.join(store_dir, "service_health.json"), "w", encoding="utf-8") as fh:
        json.dump(health, fh)


# =========================================================================== #
# 1. The eight-tab nav: names, hrefs, active marking, old-route survival        #
# =========================================================================== #
class NavTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="ux1_nav_")
        _seed(self.store, "RUN-NAV-1", _NOW1)

    def test_all_eight_tabs_render_with_names_and_hrefs(self):
        html = _get(self.store, "/")
        for label, href in _TABS:
            self.assertIn('href="{0}"'.format(href), html, href)
            self.assertIn(label, html, label)

    def test_current_tab_is_marked_active(self):
        # each tab page marks exactly its own tab `here`
        cases = (("/", "/"), ("/opportunities", "/opportunities"),
                 ("/research", "/research"), ("/portfolio", "/portfolio"),
                 ("/journal", "/journal"), ("/evidence", "/evidence"),
                 ("/how-it-works", "/how-it-works"), ("/map", "/map"))
        for path, active_href in cases:
            html = _get(self.store, path)
            self.assertIn('class="navlink here" href="{0}"'.format(active_href), html, path)
            # exactly one tab is active
            self.assertEqual(html.count('class="navlink here"'), 1, path)

    def test_old_routes_map_their_deep_pages_to_a_sensible_active_tab(self):
        # /candidates -> Opportunities; /themes -> Company Research; /runs -> Evidence & Trust
        self.assertIn('class="navlink here" href="/opportunities"',
                      _get(self.store, "/candidates"))
        self.assertIn('class="navlink here" href="/research"', _get(self.store, "/themes"))
        self.assertIn('class="navlink here" href="/evidence"', _get(self.store, "/runs"))

    def test_all_old_and_new_routes_still_resolve_200(self):
        for path in _SHELL_PATHS + ("/candidates", "/companies/IREN", "/candidates/IREN"):
            r = _call(self.store, "GET", path)
            self.assertEqual(r["status"], 200, path)
            self.assertTrue(r["headers"]["Content-Type"].startswith("text/html"), path)

    def test_opportunities_is_the_candidate_surface(self):
        opp = _get(self.store, "/opportunities")
        cand = _get(self.store, "/candidates")
        self.assertIn("Capital Candidates", opp)
        self.assertIn("Capital Candidates", cand)

    def test_utility_row_keeps_operator_surfaces_reachable(self):
        html = _get(self.store, "/")
        for href in ('href="/runs"', 'href="/themes"', 'href="/alerts"', 'href="/settings"'):
            self.assertIn(href, html, href)


# =========================================================================== #
# 2. Full-width + scrollable layout                                            #
# =========================================================================== #
class LayoutTests(unittest.TestCase):
    def test_css_is_full_width_not_a_narrow_centered_column(self):
        self.assertNotIn("max-width:1100px", APP_CSS)   # the old narrow container is gone
        self.assertIn("width:100%", APP_CSS)
        # the content rule spans the full width
        self.assertRegex(APP_CSS, r"\.wrap\{[^}]*width:100%")

    def test_document_scrolls_naturally_no_overflow_lock(self):
        self.assertNotIn("overflow:hidden", APP_CSS)    # nothing locks the viewport
        self.assertNotIn("position:fixed", APP_CSS)     # no fixed-viewport shell

    def test_served_page_uses_the_full_width_wrap_and_tab_nav(self):
        with tempfile.TemporaryDirectory() as d:
            html = _get(d, "/")
            self.assertIn('<nav class="tabs">', html)
            self.assertIn('<div class="wrap">', html)
            self.assertTrue(html.startswith("<!doctype html>"))


# =========================================================================== #
# 3. The quiet honest status chip                                              #
# =========================================================================== #
class StatusChipTests(unittest.TestCase):
    def test_chip_is_present_compact_and_honest_on_empty_store(self):
        with tempfile.TemporaryDirectory() as d:
            html = _get(d, "/")
            self.assertIn('class="chip"', html)
            self.assertIn("Manual Review", html)
            # honest offline posture -- never a live / production claim on an empty store
            self.assertEqual(service_mode_indicator(d), "")
            self.assertIn("offline", html)
            self.assertNotIn("SHADOW_24X7", html)
            self.assertNotIn("PRODUCTION_24X7", html)
            self.assertNotIn("Production 24x7", html)
            self.assertIsNone(_LIVE_WORD.search(html))

    def test_chip_preserves_full_broker_and_manual_review_honesty_when_a_service_ran(self):
        with tempfile.TemporaryDirectory() as d:
            S.RunStore(d)  # store dir exists
            _write_health(d, "shadow_24x7")
            html = _get(d, "/")
            # the compact chip still carries the FULL honest line (tooltip + details):
            self.assertIn("Broker: Disabled", html)
            self.assertIn("Execution: Manual Review Only", html)
            self.assertIn('class="chip"', html)
            # ...and the full verbatim shadow line is preserved somewhere on the page
            self.assertIn("Mode: SHADOW_24X7", html)

    def test_chip_is_compact_the_verbose_strip_is_gone_from_the_header_bar(self):
        with tempfile.TemporaryDirectory() as d:
            html = _get(d, "/")
            # the old verbose inline "mode-indicator" strip element is retired
            self.assertNotIn('class="mode-indicator"', html)


# =========================================================================== #
# 4. The Dashboard home: overview + honest empty states, read-only             #
# =========================================================================== #
class DashboardTests(unittest.TestCase):
    def test_empty_store_dashboard_has_honest_empty_states(self):
        with tempfile.TemporaryDirectory() as d:
            html = _get(d, "/")
            self.assertIn("Dashboard", html)
            self.assertIn("Overview", html)
            self.assertIn("No positions recorded yet", html)     # portfolio empty state
            self.assertIn("No persisted runs yet", html)         # latest-run empty state
            self.assertIn("No alerts in this store yet", html)   # alerts empty state

    def test_dashboard_overview_counts_render_and_link_to_tabs(self):
        with tempfile.TemporaryDirectory() as d:
            _seed(d, "RUN-DASH-1", _NOW1)
            html = _get(d, "/")
            for label in ("Opportunities", "Blocked candidates", "Open alerts", "Pulse runs"):
                self.assertIn(label, html, label)
            self.assertIn('class="metric"', html)
            self.assertIn('href="/opportunities"', html)

    def test_dashboard_shows_a_portfolio_snapshot_when_holdings_exist(self):
        with tempfile.TemporaryDirectory() as d:
            _seed(d, "RUN-DASH-2", _NOW1)
            holdings = {"as_of": _NOW1,
                        "positions": [{"ticker": "IREN", "quantity": "100"}]}
            path = os.path.join(d, S.HOLDINGS_RELPATH) if hasattr(S, "HOLDINGS_RELPATH") \
                else os.path.join(d, "portfolio", "holdings.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(holdings, fh)
            html = _get(d, "/")
            self.assertIn("Portfolio snapshot", html)
            self.assertIn("Positions recorded", html)
            self.assertNotIn("No positions recorded yet", html)

    def test_dashboard_has_no_trade_control(self):
        with tempfile.TemporaryDirectory() as d:
            _seed(d, "RUN-DASH-3", _NOW1)
            html = _get(d, "/")
            self.assertEqual(_TRADE_WORD.findall(html), [])
            # the only form on the dashboard is the sanctioned manual-pulse operator action
            self.assertEqual(html.count('<form class="op-form"'),
                             html.count("OPERATOR action"))


# =========================================================================== #
# 5. Guardrails hold across ALL tabs                                          #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty = tempfile.mkdtemp(prefix="ux1_guard_empty_")
        cls.seeded = tempfile.mkdtemp(prefix="ux1_guard_seeded_")
        _seed(cls.seeded, "RUN-GUARD-1", _NOW1)
        cls.empty_pages = {p: _get(cls.empty, p) for p in _SHELL_PATHS}
        cls.seeded_pages = {p: _get(cls.seeded, p) for p in _SHELL_PATHS}

    def test_zero_trade_affordances_on_any_tab(self):
        for path, html in list(self.empty_pages.items()) + list(self.seeded_pages.items()):
            self.assertEqual(_TRADE_WORD.findall(html), [],
                             "trade verb on {0}".format(path))

    def test_a_trade_like_route_is_403(self):
        for path in ("/api/orders", "/api/buy", "/api/trade", "/api/execution/submit",
                     "/opportunities/buy"):
            r = _call(self.empty, "GET", path, body={"ticker": "IREN"})
            self.assertEqual(r["status"], 403, path)
            self.assertEqual(r["body"]["error"], EXECUTION_REFUSAL)

    def test_zero_score_rank_rating_tokens_on_any_tab(self):
        for path, html in list(self.empty_pages.items()) + list(self.seeded_pages.items()):
            low = html.lower()
            for token in _SCORE_TOKENS:
                self.assertNotIn(token, low, "score token {0!r} on {1}".format(token, path))

    def test_no_fixture_ticker_in_the_default_empty_store_ui(self):
        for path, html in self.empty_pages.items():
            for ticker in _FIXTURE_TICKERS:
                self.assertNotRegex(html, r"\b{0}\b".format(ticker),
                                    "{0} leaked into default {1}".format(ticker, path))

    def test_no_secret_value_on_any_tab(self):
        for path, html in list(self.empty_pages.items()) + list(self.seeded_pages.items()):
            for pattern in _SECRET_VALUE_PATTERNS:
                self.assertIsNone(pattern.search(html), path)

    def test_no_live_or_production_overclaim_on_the_default_ui(self):
        for path, html in self.empty_pages.items():
            low = html.lower()
            for claim in _LIVE_CLAIMS:
                self.assertNotIn(claim, low, "{0!r} on {1}".format(claim, path))
            self.assertIsNone(_LIVE_WORD.search(html), path)


# =========================================================================== #
# 6. Determinism: same store + same now -> byte-identical bodies              #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_pages_render_byte_identically_for_identical_requests(self):
        with tempfile.TemporaryDirectory() as d:
            _seed(d, "RUN-DET-1", _NOW1)
            for path in _SHELL_PATHS:
                a = _call(d, "GET", path, now=_NOW2)
                b = _call(d, "GET", path, now=_NOW2)
                self.assertEqual(json.dumps(a, sort_keys=True),
                                 json.dumps(b, sort_keys=True), path)


# =========================================================================== #
# 7. Untouched paths stay byte-identical (universe_ui demo + reality_mesh)      #
# =========================================================================== #
class UntouchedPathsTests(unittest.TestCase):
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
