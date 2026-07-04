"""IMPLEMENTATION-010E -- Multi-Ticker / Watchlist Real Terrain.

Everything here runs OFFLINE. The watchlist builder is exercised ONLY with injected MOCK
transports (per ticker); no test reaches a real endpoint. The suite proves the 010D
security/honesty invariants still hold once real mode spans a small explicit watchlist:

* one merged, sparse ``real_evidence_on_demand`` terrain (never the default; demo stays);
* per-ticker ISOLATION -- a failing ticker is recorded (visible), never silently dropped,
  and never aborts the run; the run fails only if ALL tickers fail;
* no fake centre / hub -- ``validate()`` clean, ``relationship_edges`` empty; same-theme
  companies co-locate, weak-theme companies fall under an explicit ``unclassified`` region;
* no scheduler / broker / order affordance / new scoring fn / secret in HTML;
* deterministic with mock transports + injected ``now``.
"""

from __future__ import annotations

import ast
import contextlib
import io
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

from universe_ui.app import build_universe_app
from universe_ui.terrain import CompanyNode, GalaxyNode
from universe_ui.watchlist_terrain import (
    MAX_WATCHLIST_TICKERS,
    build_real_evidence_watchlist_terrain,
    normalize_tickers,
)
import universe_ui.__main__ as ui_main

_FIXTURE_DIR = os.path.join(_ROOT, "tests", "fixtures", "slice")
_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")
_NOW = 1750000000.0
_PAGES = (
    "universe.html", "dashboard.html", "capital_candidates.html", "cockpit.html",
    "data_quality.html", "reality_mesh.html", "portfolio_intelligence.html",
)

_DEMO_GALAXIES = (
    "Data Centers", "Semiconductors", "Power & Grid", "Optics & Networking",
    "Nuclear & Energy", "Physical AI", "Robotics", "Space & Defense",
)


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _mock():
    """A MOCK transport bundle returning the real IREN fixtures (fully offline)."""
    return {
        "sec_submissions": lambda tk: _load("sec_submissions_iren.json"),
        "sec_companyfacts": lambda tk: _load("sec_companyfacts_iren.json"),
        "fmp_profile": lambda tk: _load("fmp_profile_iren.json"),
        "fmp_income_statement": lambda tk: _load("fmp_income_statement_iren.json"),
        "fmp_ohlcv": lambda tk: _load("fmp_ohlcv_iren.json"),
        "fmp_news": lambda tk: _load("fmp_news_iren.json"),
        "fmp_ownership": lambda tk: _load("fmp_ownership_iren.json"),
    }


class _BrokenTransports:
    """A transport bundle that fails on access -- simulates a ticker whose fetch blows up
    (e.g. CIK-mapping / source failure). The watchlist must ISOLATE and RECORD it."""

    def get(self, *_a, **_k):
        raise RuntimeError("transport bundle unavailable (simulated fetch failure)")


def _tbt(*tickers):
    return {tk: _mock() for tk in tickers}


def _boom_socket(*_a, **_k):
    raise AssertionError("network access attempted")


def _companies(terrain):
    return [n for _i, n in terrain.all_nodes() if isinstance(n, CompanyNode)]


def _build_pages(tmpprefix, tickers, tbt, **kw):
    d = tempfile.mkdtemp(prefix=tmpprefix)
    kw.setdefault("now", _NOW)
    paths = build_universe_app(d, mode="real_evidence_on_demand", tickers=tickers,
                               transports_by_ticker=tbt, **kw)
    return paths


def _read(paths, name):
    with open(paths[name], encoding="utf-8") as fh:
        return fh.read()


# =========================================================================== #
# A. CLI / app routing                                                         #
# =========================================================================== #
class CliTests(unittest.TestCase):
    def setUp(self):
        # Patch the network/credential + build seams so CLI wiring is exercised offline.
        self._orig_build = ui_main.build_universe_app
        self._calls = []

        def _fake_build(out, **kw):
            self._calls.append(kw)
            paths = {name: os.path.join(out, name) for name in _PAGES}
            paths["assets/universe.css"] = "css"
            paths["assets/universe.js"] = "js"
            return paths

        ui_main.build_universe_app = _fake_build
        import runtime.live_evidence_run as ler
        self._orig_resolve = ler.resolve_live_credentials
        self._orig_presence = ler.credential_presence
        ler.resolve_live_credentials = lambda: (None, None)
        ler.credential_presence = lambda: {"sec_user_agent_present": False,
                                           "fmp_api_key_present": False}
        self._ler = ler

    def tearDown(self):
        ui_main.build_universe_app = self._orig_build
        self._ler.resolve_live_credentials = self._orig_resolve
        self._ler.credential_presence = self._orig_presence

    @staticmethod
    def _main(argv):
        """Run the CLI with stdout captured (keeps test output clean)."""
        with contextlib.redirect_stdout(io.StringIO()):
            return ui_main.main(argv)

    def test_single_ticker_still_works(self):
        rc = self._main(["--mode", "real_evidence_on_demand", "--ticker", "iren",
                           "--out", tempfile.mkdtemp()])
        self.assertEqual(rc, 0)
        self.assertEqual(self._calls[-1].get("ticker"), "IREN")
        self.assertNotIn("tickers", self._calls[-1])

    def test_tickers_multi_works_and_dedupes(self):
        rc = self._main(["--mode", "real_evidence_on_demand",
                           "--tickers", "iren, aaoi ,IREN,, inod", "--out", tempfile.mkdtemp()])
        self.assertEqual(rc, 0)
        self.assertEqual(self._calls[-1].get("tickers"), ["IREN", "AAOI", "INOD"])
        self.assertNotIn("ticker", self._calls[-1])

    def test_empty_tickers_fails_clearly(self):
        with self.assertRaises(SystemExit):
            self._main(["--mode", "real_evidence_on_demand", "--tickers", "  ,  ",
                          "--out", tempfile.mkdtemp()])

    def test_real_mode_requires_ticker_or_tickers(self):
        with self.assertRaises(SystemExit):
            self._main(["--mode", "real_evidence_on_demand", "--out", tempfile.mkdtemp()])

    def test_demo_remains_default(self):
        # Not patched away: the real demo build (no network) stays the default.
        ui_main.build_universe_app = self._orig_build
        d = tempfile.mkdtemp()
        rc = self._main(["--out", d])
        self.assertEqual(rc, 0)
        html = open(os.path.join(d, "universe.html"), encoding="utf-8").read()
        self.assertIn("fixture/demo", html)
        self.assertNotIn("real evidence on demand", html.lower())


class AppRoutingTests(unittest.TestCase):
    def test_app_demo_is_default(self):
        d = tempfile.mkdtemp(prefix="wl_demo_")
        paths = build_universe_app(d)  # no mode
        html = _read(paths, "universe.html")
        self.assertIn("fixture/demo", html)

    def test_app_empty_watchlist_errors(self):
        with self.assertRaises(ValueError):
            build_universe_app(tempfile.mkdtemp(), mode="real_evidence_on_demand",
                               tickers=[], transports_by_ticker={})

    def test_failing_ticker_is_visible_not_dropped(self):
        tbt = {"IREN": _mock(), "BADX": _BrokenTransports(), "INOD": _mock()}
        paths = _build_pages("wl_fail_", ["IREN", "BADX", "INOD"], tbt)
        dq = _read(paths, "data_quality.html")
        self.assertIn("BADX", dq)
        self.assertIn("failed", dq.lower())
        # the two good tickers still built
        uni = _read(paths, "universe.html")
        self.assertIn("IREN", uni)
        self.assertIn("INOD", uni)


# =========================================================================== #
# B. Builder (mock transports_by_ticker)                                       #
# =========================================================================== #
class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.terrain, self.summary = build_real_evidence_watchlist_terrain(
            ["IREN", "AAOI", "INOD"], transports_by_ticker=_tbt("IREN", "AAOI", "INOD"),
            now=_NOW)

    def test_returns_one_universe_terrain(self):
        self.assertEqual(self.terrain.mode, "real_evidence_on_demand")
        # same-theme (all ai-infrastructure) -> ONE galaxy
        self.assertEqual(len(self.terrain.galaxies), 1)
        self.assertEqual(self.terrain.galaxies[0].id, "ai-infrastructure")

    def test_all_successful_tickers_are_company_nodes(self):
        tickers = {c.ticker for c in _companies(self.terrain)}
        self.assertEqual(tickers, {"IREN", "AAOI", "INOD"})

    def test_globally_unique_node_ids(self):
        # data-intel-bearing structural nodes (value chains, bottlenecks, planets) must be
        # unique across tickers so every reference resolves.
        from universe_ui.terrain import (BottleneckNode, ValueChainNode)
        struct = [nid for nid, n in self.terrain.all_nodes()
                  if isinstance(n, (CompanyNode, ValueChainNode, BottleneckNode)) and nid]
        self.assertEqual(len(struct), len(set(struct)))

    def test_no_centre_hub_and_validates(self):
        self.assertEqual(self.terrain.validate(), ())
        self.assertEqual(self.terrain.relationship_edges, ())

    def test_no_demo_galaxies_leaked(self):
        names = " ".join(g.name for g in self.terrain.galaxies)
        for demo in _DEMO_GALAXIES:
            self.assertNotIn(demo, names)

    def test_source_counts_and_provenance_preserved_per_ticker(self):
        built = [r for r in self.summary.records if r.status == "built"]
        self.assertEqual(len(built), 3)
        for r in built:
            self.assertGreater(r.canonical, 0)
            self.assertTrue(r.provenance_refs)
        # merged coverage is the sum
        self.assertEqual(self.terrain.source_coverage.get("canonical"),
                         sum(r.canonical for r in built))

    def test_failed_ticker_recorded_run_continues(self):
        terrain, summary = build_real_evidence_watchlist_terrain(
            ["IREN", "BADX"], transports_by_ticker={"IREN": _mock(),
                                                    "BADX": _BrokenTransports()}, now=_NOW)
        self.assertEqual(summary.succeeded_count, 1)
        self.assertEqual(summary.failed_count, 1)
        bad = [r for r in summary.records if r.ticker == "BADX"][0]
        self.assertEqual(bad.status, "failed")
        self.assertTrue(bad.reason)
        self.assertEqual([c.ticker for c in _companies(terrain)], ["IREN"])

    def test_run_fails_only_if_all_fail(self):
        with self.assertRaises(ValueError):
            build_real_evidence_watchlist_terrain(
                ["BADX", "BADY"], transports_by_ticker={"BADX": _BrokenTransports(),
                                                        "BADY": _BrokenTransports()})

    def test_weak_theme_goes_to_unclassified_region(self):
        terrain, _s = build_real_evidence_watchlist_terrain(
            ["IREN", "THIN"], transports_by_ticker={"IREN": _mock(), "THIN": {}}, now=_NOW)
        ids = {g.id for g in terrain.galaxies}
        self.assertIn("unclassified", ids)
        self.assertIn("ai-infrastructure", ids)
        self.assertEqual(terrain.validate(), ())

    def test_empty_and_oversize_lists_error(self):
        with self.assertRaises(ValueError):
            build_real_evidence_watchlist_terrain("  ,  ", transports_by_ticker={})
        with self.assertRaises(ValueError):
            build_real_evidence_watchlist_terrain(
                ["T{0}".format(i) for i in range(MAX_WATCHLIST_TICKERS + 1)],
                transports_by_ticker={})

    def test_normalize_tickers(self):
        self.assertEqual(normalize_tickers("iren,aaoi,IREN"), ("IREN", "AAOI"))
        self.assertEqual(normalize_tickers(["  inod ", "inod", ""]), ("INOD",))
        self.assertEqual(normalize_tickers(None), ())


# =========================================================================== #
# C. Data Quality                                                              #
# =========================================================================== #
class DataQualityTests(unittest.TestCase):
    def test_overall_and_per_ticker_and_gaps_render(self):
        paths = _build_pages("wl_dq_", ["IREN", "AAOI", "INOD"],
                             _tbt("IREN", "AAOI", "INOD"))
        dq = _read(paths, "data_quality.html")
        self.assertIn("Watchlist run — overall", dq)
        self.assertIn("Per-ticker source status", dq)
        self.assertIn("Failures &amp; credential / data gaps", dq)
        for tk in ("IREN", "AAOI", "INOD"):
            self.assertIn(tk, dq)

    def test_missing_fmp_key_visible_without_leak(self):
        # transports_by_ticker=None per ticker -> the live bundle is built with NO creds
        # (wires nothing, so no network) and records credentials_missing. No key is passed,
        # so none can leak; the gap must still be VISIBLE and no "apikey" surfaces.
        d = tempfile.mkdtemp(prefix="wl_leak_")
        real = socket.socket
        socket.socket = _boom_socket
        try:
            paths = build_universe_app(
                d, mode="real_evidence_on_demand", tickers=["IREN", "AAOI"],
                transports_by_ticker={"IREN": None, "AAOI": None},
                sec_user_agent=None, fmp_api_key=None, now=_NOW)
        finally:
            socket.socket = real
        dq = _read(paths, "data_quality.html")
        self.assertIn("FMP key missing", dq)
        self.assertIn("SEC User-Agent missing", dq)
        for name in _PAGES:
            self.assertNotIn("apikey", _read(paths, name).lower())

    def test_yfinance_deferred_visible(self):
        paths = _build_pages("wl_yf_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"))
        dq = _read(paths, "data_quality.html")
        self.assertIn("deferred", dq.lower())

    def test_conflicts_and_overridden_visible_when_present(self):
        # yfinance enabled -> SEC canonical overrides FMP convenience facts -> overridden
        # facts are aggregated across tickers and surfaced (not hidden).
        terrain, summary = build_real_evidence_watchlist_terrain(
            ["IREN", "AAOI"], transports_by_ticker=_tbt("IREN", "AAOI"),
            enable_yfinance=True, now=_NOW)
        self.assertTrue(summary.overridden_facts, "expected overridden facts across tickers")
        d = tempfile.mkdtemp(prefix="wl_conf_")
        paths = build_universe_app(
            d, mode="real_evidence_on_demand", tickers=["IREN", "AAOI"],
            transports_by_ticker=_tbt("IREN", "AAOI"), enable_yfinance=True, now=_NOW)
        dq = _read(paths, "data_quality.html")
        self.assertIn("Overridden facts", dq)
        self.assertNotIn("none overridden", dq)  # the list is populated, not empty


# =========================================================================== #
# D. Renderer                                                                  #
# =========================================================================== #
class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = _build_pages("wl_render_", ["IREN", "AAOI", "INOD"],
                                 _tbt("IREN", "AAOI", "INOD"))
        cls.uni = _read(cls.paths, "universe.html")
        cls.dash = _read(cls.paths, "dashboard.html")

    def test_universe_renders_multiple_companies(self):
        self.assertGreater(self.uni.count("k-planet"), 0)
        for tk in ("IREN", "AAOI", "INOD"):
            self.assertIn("({0})".format(tk), self.uni)

    def test_every_data_intel_resolves(self):
        refs = set(re.findall(r'data-intel="([^"]+)"', self.uni))
        defs = set(re.findall(r'class="intel-template" id="([^"]+)"', self.uni))
        self.assertTrue(refs)
        self.assertEqual(refs - defs, set())

    def test_floating_preview_resolves_for_each_company(self):
        defs = set(re.findall(r'class="intel-template" id="([^"]+)"', self.uni))
        for tk in ("iren", "aaoi", "inod"):
            self.assertIn("intel-pl-ai-infrastructure-{0}".format(tk), defs)

    def test_dashboard_renders_a_card_per_company(self):
        self.assertEqual(self.dash.count('class="card'), 3)

    def test_sparse_watchlist_notice_appears(self):
        self.assertIn("terrain incomplete", self.uni.lower())
        self.assertIn("requested / ", self.uni)  # run summary in the status strip

    def test_unclassified_notice_when_present(self):
        paths = _build_pages("wl_unc_", ["IREN", "THIN"],
                             {"IREN": _mock(), "THIN": {}})
        uni = _read(paths, "universe.html")
        self.assertIn("Unclassified", uni)


# =========================================================================== #
# E. Guardrails                                                                #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = _build_pages("wl_guard_", ["IREN", "AAOI", "INOD"],
                                 _tbt("IREN", "AAOI", "INOD"), enable_yfinance=True)
        cls.html = "\n".join(_read(cls.paths, name) for name in _PAGES)

    def test_no_action_or_broker_affordance(self):
        low = self.html.lower()
        for banned in ("<button", "<form", "onclick", 'type="submit"', "place order",
                       "place an order", "fetch(", "xmlhttprequest", "submit("):
            self.assertNotIn(banned, low, "banned affordance: {0}".format(banned))
        self.assertIsNone(re.search(r"\b(buy|sell)\b", low), "buy/sell token present")

    def test_no_forbidden_marketing_wording(self):
        low = self.html.lower()
        for banned in ("fully live", "automated", "production ranking", "trade-ready",
                       "real-time", "real time"):
            self.assertNotIn(banned, low, "forbidden wording: {0}".format(banned))

    def test_visible_manual_only_banner_with_counts(self):
        self.assertIn("Manual Refresh Only", self.html)
        self.assertIn("Scheduler: Off", self.html)
        self.assertIn("Broker: Disabled", self.html)
        self.assertIn("requested / ", self.html)
        self.assertIn("built / ", self.html)

    def test_deterministic_with_mocks_and_now(self):
        p1 = _build_pages("wl_det_a_", ["IREN", "AAOI", "INOD"],
                          _tbt("IREN", "AAOI", "INOD"))
        p2 = _build_pages("wl_det_b_", ["IREN", "AAOI", "INOD"],
                          _tbt("IREN", "AAOI", "INOD"))
        for name in ("universe.html", "dashboard.html", "data_quality.html"):
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                             "non-deterministic: {0}".format(name))

    def test_whole_watchlist_build_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            _build_pages("wl_off_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                         enable_yfinance=True)
        finally:
            socket.socket = real

    def test_no_secret_in_html(self):
        secret = "SEC-UA-AND-FMP-SHOULD-NOT-LEAK-42"
        paths = _build_pages("wl_nosec_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                             fmp_api_key=secret, sec_user_agent=secret)
        for name in _PAGES:
            self.assertNotIn(secret, _read(paths, name))

    def test_watchlist_module_no_scheduler_or_broker_or_network_imports(self):
        forbidden = {"sched", "asyncio", "subprocess", "socketserver", "urllib", "http",
                     "socket", "requests", "aiohttp", "httpx"}
        tree = ast.parse(open(os.path.join(_UNIVERSE_UI_DIR, "watchlist_terrain.py"),
                              encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name.split(".")[0], forbidden)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)

    def test_watchlist_module_defines_no_new_scoring_function(self):
        tree = ast.parse(open(os.path.join(_UNIVERSE_UI_DIR, "watchlist_terrain.py"),
                              encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertNotIn("score", node.name.lower())

    def test_no_order_words_in_watchlist_source(self):
        src = open(os.path.join(_UNIVERSE_UI_DIR, "watchlist_terrain.py"),
                   encoding="utf-8").read().lower()
        for banned in ("place order", "submit_order", "broker_order", "buy(", "sell("):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
