"""IMPLEMENTATION-010D -- On-Demand Real Evidence Terrain Loader.

Everything here runs OFFLINE. The real-mode builder is exercised ONLY with injected
MOCK transports (fake callables returning fixture dicts). No test reaches a real
endpoint. The suite proves the security/honesty invariants:

* no network on import (of any module, including the transport boundary);
* no network in tests (mock transports only; a socket kill-switch confirms it);
* no secret string in generated HTML; missing FMP key -> a visible data gap (not a
  leak, not a crash); SEC User-Agent required (clear error when absent);
* SEC canonical beats FMP/yfinance for the same financial fact; FMP OHLCV beats
  yfinance OHLCV; fallback records stay visibly fallback;
* no scheduler / broker / order affordance / new scoring fn / centre hub;
* deterministic real-mode build with mock transports + injected ``now``;
* the ONLY module importing urllib is the designated boundary, lazily.
"""

from __future__ import annotations

import ast
import importlib
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
from universe_ui.real_terrain import build_real_evidence_terrain_for_ticker
from universe_ui.terrain import CompanyNode, GalaxyNode
from evidence_ingestion import live_transport

_FIXTURE_DIR = os.path.join(_ROOT, "tests", "fixtures", "slice")
_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")
_EVIDENCE_DIR = os.path.join(_SRC, "evidence_ingestion")
_NOW = 1750000000.0

_DEMO_GALAXIES = (
    "Data Centers", "Semiconductors", "Power & Grid", "Optics & Networking",
    "Nuclear & Energy", "Physical AI", "Robotics", "Space & Defense",
)


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _full_mock_transports(*, with_yf=False):
    """MOCK transports returning the real IREN fixtures (fully offline)."""
    t = {
        "sec_submissions": lambda tk: _load("sec_submissions_iren.json"),
        "sec_companyfacts": lambda tk: _load("sec_companyfacts_iren.json"),
        "fmp_profile": lambda tk: _load("fmp_profile_iren.json"),
        "fmp_income_statement": lambda tk: _load("fmp_income_statement_iren.json"),
        "fmp_ohlcv": lambda tk: _load("fmp_ohlcv_iren.json"),
        "fmp_news": lambda tk: _load("fmp_news_iren.json"),
        "fmp_ownership": lambda tk: _load("fmp_ownership_iren.json"),
    }
    if with_yf:
        t["yf_history"] = lambda tk: _load("yf_history_iren.json")
        t["yf_quote"] = lambda tk: _load("yf_quote_iren.json")
    return t


def _build(**kw):
    kw.setdefault("now", _NOW)
    return build_real_evidence_terrain_for_ticker("IREN", **kw)


def _companies(terrain):
    return [n for _i, n in terrain.all_nodes() if isinstance(n, CompanyNode)]


# =========================================================================== #
# A. Modes                                                                     #
# =========================================================================== #
class ModeTests(unittest.TestCase):
    def test_demo_is_default_mode(self):
        d = tempfile.mkdtemp(prefix="rmode_demo_")
        paths = build_universe_app(d)  # no mode arg
        html = open(paths["universe.html"], encoding="utf-8").read()
        self.assertIn("fixture/demo", html)
        self.assertNotIn("real evidence on demand", html.lower())

    def test_evidence_ingested_fixture_still_works(self):
        d = tempfile.mkdtemp(prefix="rmode_ev_")
        paths = build_universe_app(d, mode="evidence_ingested_fixture")
        self.assertTrue(os.path.exists(paths["universe.html"]))

    def test_real_mode_exists_and_builds(self):
        terrain, status = _build(transports=_full_mock_transports())
        self.assertEqual(terrain.mode, "real_evidence_on_demand")
        self.assertEqual(status["mode_label"], "real_evidence_on_demand")

    def test_real_mode_requires_explicit_ticker(self):
        with self.assertRaises(ValueError):
            build_real_evidence_terrain_for_ticker("", transports=_full_mock_transports())
        with self.assertRaises(ValueError):
            build_universe_app(tempfile.mkdtemp(), mode="real_evidence_on_demand")

    def test_no_network_on_import(self):
        # Reload the boundary + builder with sockets disabled -- import must be inert.
        real_socket = socket.socket
        socket.socket = _boom_socket
        try:
            importlib.reload(importlib.import_module("evidence_ingestion.live_transport"))
            importlib.reload(importlib.import_module("universe_ui.real_terrain"))
        finally:
            socket.socket = real_socket


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# =========================================================================== #
# B. Network / secrets                                                         #
# =========================================================================== #
class NetworkSecretTests(unittest.TestCase):
    def test_whole_build_is_offline(self):
        # Kill sockets for the entire real-mode build with mock transports.
        real_socket = socket.socket
        socket.socket = _boom_socket
        try:
            d = tempfile.mkdtemp(prefix="roffline_")
            build_universe_app(d, mode="real_evidence_on_demand", ticker="IREN",
                               transports=_full_mock_transports(with_yf=True), now=_NOW)
        finally:
            socket.socket = real_socket

    def test_no_api_key_string_in_generated_html(self):
        # Even if a caller passed a key, it must never surface in the HTML.
        secret = "FMPKEY-SHOULD-NOT-LEAK-123456"
        d = tempfile.mkdtemp(prefix="rleak_")
        paths = build_universe_app(
            d, mode="real_evidence_on_demand", ticker="IREN",
            transports=_full_mock_transports(), fmp_api_key=secret, now=_NOW)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            html = open(paths[name], encoding="utf-8").read()
            self.assertNotIn(secret, html)
            self.assertNotIn("apikey", html.lower())

    def test_missing_fmp_key_is_visible_gap_not_crash(self):
        # transports=None + all creds absent -> build the live bundle (which wires
        # nothing, so no network) and record credentials_missing gaps.
        terrain, status = _build(transports=None, sec_user_agent=None, fmp_api_key=None)
        self.assertEqual(status["fmp"], "credentials_missing")
        joined = " ".join(terrain.data_gaps).lower()
        self.assertIn("fmp key missing", joined)

    def test_sec_user_agent_required_clear_error(self):
        with self.assertRaises(ValueError):
            live_transport.sec_http_transport("")
        with self.assertRaises(ValueError):
            live_transport.sec_http_transport(None)
        # And FMP likewise refuses an empty key.
        with self.assertRaises(ValueError):
            live_transport.fmp_http_transport("")

    def test_no_env_dotfile_or_secret_committed(self):
        for root, _dirs, files in os.walk(_ROOT):
            if os.sep + ".git" in root:
                continue
            for f in files:
                self.assertNotEqual(f, ".env", "a .env file is committed at {0}".format(root))


# =========================================================================== #
# C. Source authority (with conflicting SEC vs FMP vs yfinance facts)          #
# =========================================================================== #
class SourceAuthorityTests(unittest.TestCase):
    def test_sec_beats_fmp_for_same_financial_fact(self):
        terrain, status = _build(transports=_full_mock_transports(with_yf=True),
                                  enable_yfinance=True)
        res = status["slice_result"]
        overridden = res.provenance_chain["overridden_facts"]
        self.assertTrue(overridden, "expected FMP facts overridden by SEC")
        for f in overridden:
            self.assertEqual(f["source_authority"], "convenience")
            self.assertIn("SEC", f["reason"])
        # SEC canonical records are present and counted.
        self.assertGreater(terrain.source_coverage.get("canonical", 0), 0)

    def test_fmp_ohlcv_beats_yfinance_ohlcv(self):
        fmp_ohlcv = {"symbol": "IREN", "historical": [
            {"date": "2026-06-24", "open": 1, "high": 2, "low": 0.5, "close": 1.5,
             "adjClose": 1.5, "volume": 100}]}
        yf_history = {"IREN": {"history": [
            {"date": "2026-06-24", "Open": 9, "High": 9, "Low": 9, "Close": 9,
             "Adj Close": 9, "Volume": 9, "Dividends": 0.0, "Stock Splits": 0.0}]}}
        transports = {"fmp_ohlcv": lambda tk: fmp_ohlcv,
                      "yf_history": lambda tk: yf_history}
        _terrain, status = _build(transports=transports, enable_yfinance=True)
        warns = " ".join(status["slice_result"].conflict_warnings).lower()
        self.assertIn("from fmp", warns)
        self.assertIn("over", warns)
        self.assertIn("yfinance", warns)

    def test_fallback_records_stay_visibly_fallback(self):
        terrain, _status = _build(transports=_full_mock_transports(with_yf=True),
                                   enable_yfinance=True)
        self.assertGreater(terrain.source_coverage.get("fallback", 0), 0)


# =========================================================================== #
# D. Builder (mock transports)                                                 #
# =========================================================================== #
class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.terrain, self.status = _build(transports=_full_mock_transports())

    def test_builds_terrain_for_one_ticker(self):
        self.assertEqual(len(self.terrain.galaxies), 1)
        self.assertEqual(self.terrain.mode, "real_evidence_on_demand")

    def test_ticker_is_a_company_node(self):
        companies = _companies(self.terrain)
        self.assertTrue(any(c.ticker == "IREN" for c in companies))

    def test_source_counts_and_status_present(self):
        self.assertEqual(self.status["sec"], "fetched")
        self.assertEqual(self.status["fmp"], "fetched")
        self.assertEqual(self.status["yfinance"], "deferred")
        self.assertGreater(self.status["slice_result"].ingestion_result
                           .authority_summary.get("canonical", 0), 0)

    def test_missing_data_becomes_gaps(self):
        joined = " ".join(self.terrain.data_gaps).lower()
        self.assertIn("terrain incomplete", joined)
        self.assertIn("yfinance", joined)  # deferred source surfaced as a gap

    def test_no_unrelated_demo_galaxies(self):
        d = tempfile.mkdtemp(prefix="rnodemo_")
        paths = build_universe_app(d, mode="real_evidence_on_demand", ticker="IREN",
                                   transports=_full_mock_transports(), now=_NOW)
        blob = ""
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            blob += open(paths[name], encoding="utf-8").read()
        for demo in _DEMO_GALAXIES:
            self.assertNotIn(demo, blob, "demo galaxy leaked: {0}".format(demo))

    def test_yfinance_deferred_when_not_enabled(self):
        self.assertEqual(self.status["yfinance"], "deferred")


# =========================================================================== #
# E. Guardrails                                                                #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="rguard_")
        cls.paths = build_universe_app(
            cls.d, mode="real_evidence_on_demand", ticker="IREN",
            transports=_full_mock_transports(with_yf=True), enable_yfinance=True, now=_NOW)
        cls.html = ""
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            cls.html += open(cls.paths[name], encoding="utf-8").read() + "\n"

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

    def test_visible_manual_only_banner(self):
        self.assertIn("Manual Refresh Only", self.html)
        self.assertIn("Scheduler: Off", self.html)
        self.assertIn("Broker: Disabled", self.html)

    def test_terrain_has_no_centre_and_validates(self):
        terrain, _status = _build(transports=_full_mock_transports(with_yf=True),
                                   enable_yfinance=True)
        self.assertEqual(terrain.validate(), ())
        self.assertEqual(terrain.relationship_edges, ())

    def test_deterministic_real_build_with_mocks_and_now(self):
        d1 = tempfile.mkdtemp(prefix="rdet_a_")
        d2 = tempfile.mkdtemp(prefix="rdet_b_")
        p1 = build_universe_app(d1, mode="real_evidence_on_demand", ticker="IREN",
                                transports=_full_mock_transports(), now=_NOW)
        p2 = build_universe_app(d2, mode="real_evidence_on_demand", ticker="IREN",
                                transports=_full_mock_transports(), now=_NOW)
        for name in ("universe.html", "dashboard.html", "data_quality.html"):
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                             "non-deterministic: {0}".format(name))

    def test_no_scheduler_or_broker_import_in_new_modules(self):
        forbidden = {"sched", "asyncio", "subprocess", "socketserver"}
        for path in (os.path.join(_UNIVERSE_UI_DIR, "real_terrain.py"),
                     os.path.join(_EVIDENCE_DIR, "live_transport.py")):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertNotIn(a.name.split(".")[0], forbidden)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)

    def test_defines_no_new_scoring_function(self):
        for path in (os.path.join(_UNIVERSE_UI_DIR, "real_terrain.py"),
                     os.path.join(_EVIDENCE_DIR, "live_transport.py")):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertNotIn("score", node.name.lower())


# =========================================================================== #
# AST guard: the ONLY module reaching the network is the designated boundary   #
# =========================================================================== #
class NetworkBoundaryASTTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "socketserver"}

    def _py_files(self, dirpath):
        return [os.path.join(dirpath, f) for f in sorted(os.listdir(dirpath))
                if f.endswith(".py")]

    def _toplevel_roots(self, tree):
        roots = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                roots.add((node.module or "").split(".")[0])
        return roots

    def test_only_live_transport_imports_network_and_lazily(self):
        for path in self._py_files(_EVIDENCE_DIR):
            tree = ast.parse(open(path, encoding="utf-8").read())
            name = os.path.basename(path)
            if name == "live_transport.py":
                # network imported ONLY inside functions, never at module scope.
                self.assertFalse(self._toplevel_roots(tree) & self._NET,
                                 "boundary imports network at module scope")
                continue
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [(node.module or "").split(".")[0]]
                for m in mods:
                    self.assertNotIn(m, self._NET,
                                     "{0} imports network module {1}".format(name, m))

    def test_universe_ui_imports_no_network(self):
        for path in self._py_files(_UNIVERSE_UI_DIR):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [(node.module or "").split(".")[0]]
                for m in mods:
                    self.assertNotIn(m, self._NET,
                                     "{0} imports network {1}".format(path, m))

    def test_real_terrain_imports_boundary_lazily_only(self):
        tree = ast.parse(
            open(os.path.join(_UNIVERSE_UI_DIR, "real_terrain.py"), encoding="utf-8").read())
        def _mentions_boundary(node):
            if isinstance(node, ast.ImportFrom):
                if "live_transport" in (node.module or ""):
                    return True
                return any("live_transport" in a.name for a in node.names)
            if isinstance(node, ast.Import):
                return any("live_transport" in a.name for a in node.names)
            return False

        # live_transport must NOT be imported at module top level.
        for node in tree.body:
            self.assertFalse(_mentions_boundary(node),
                             "real_terrain imports the boundary at module scope")
        # It IS imported lazily inside a function.
        lazy = 0
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(fn):
                    if _mentions_boundary(node):
                        lazy += 1
        self.assertGreater(lazy, 0, "real_terrain never lazily imports the boundary")

    def test_evidence_ingestion_uses_no_environment(self):
        for path in self._py_files(_EVIDENCE_DIR):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotEqual(node.attr, "environ",
                                        "{0} reads os.environ".format(path))


if __name__ == "__main__":
    unittest.main()
