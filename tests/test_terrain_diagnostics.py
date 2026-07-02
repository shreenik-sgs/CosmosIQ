"""IMPLEMENTATION-010F -- Real Data-Quality Hardening + Theme Classification Diagnostics.

Everything here runs OFFLINE with injected MOCK transports (per ticker); no test reaches a
real endpoint. The suite proves the 010F diagnostics are DATA-QUALITY / TRUST labels, NOT
alpha:

* the diagnostic models carry ONLY labels / strings / tuples / honest copied counts -- NO
  numeric investability score, NO ranking, NO new scoring function;
* diagnostics derive ENTIRELY from the existing terrain nodes + WatchlistRunSummary +
  VisualEncoding ``*_basis`` fields, and attach back to real terrain object ids;
* theme classification is auditable (direct / weak / fallback / missing / unclassified) and
  a weak classification is never upgraded;
* the Data-Quality dashboard renders overall health, a per-ticker diagnostic table,
  diagnostic cards, a DATA-SOURCING action list (never a trade instruction) and a
  visual-encoding explanation -- with no key / secret, no order / buy / sell affordance;
* demo stays the byte-identical default; real single + watchlist modes still build;
* the whole build runs under a socket block.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from types import SimpleNamespace

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from universe_ui.app import build_universe_app
from universe_ui.terrain import (
    BottleneckNode,
    CompanyNode,
    GalaxyNode,
    ThemeNode,
    UniverseTerrain,
    ValueChainNode,
)
from universe_ui.terrain_diagnostics import (
    LABELS,
    TerrainQualityDiagnostic,
    ThemeClassificationDiagnostic,
    TickerQualityDiagnostic,
    ValueChainDiagnostic,
    build_terrain_diagnostics,
    classify_theme_for_company,
    diagnostics_by_object_id,
    explain_visual_encoding,
    single_ticker_run_summary,
)
from universe_ui.watchlist_terrain import build_real_evidence_watchlist_terrain

_FIXTURE_DIR = os.path.join(_ROOT, "tests", "fixtures", "slice")
_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")
_NOW = 1750000000.0
_PAGES = ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html")
_MODELS = (TerrainQualityDiagnostic, TickerQualityDiagnostic,
           ThemeClassificationDiagnostic, ValueChainDiagnostic)


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
    """A transport bundle that fails on access (simulates a CIK / source failure)."""

    def get(self, *_a, **_k):
        raise RuntimeError("transport bundle unavailable (simulated fetch failure)")


def _tbt(*tickers):
    return {tk: _mock() for tk in tickers}


def _boom_socket(*_a, **_k):
    raise AssertionError("network access attempted")


def _build(tickers, tbt, **kw):
    kw.setdefault("now", _NOW)
    return build_real_evidence_watchlist_terrain(tickers, transports_by_ticker=tbt, **kw)


def _build_pages(prefix, tickers, tbt, **kw):
    d = tempfile.mkdtemp(prefix=prefix)
    kw.setdefault("now", _NOW)
    return build_universe_app(d, mode="real_evidence_on_demand", tickers=tickers,
                              transports_by_ticker=tbt, **kw)


def _read(paths, name):
    with open(paths[name], encoding="utf-8") as fh:
        return fh.read()


# --- a tiny hand-built real terrain, for isolated model / classify tests ------ #
def _mini_terrain():
    co = CompanyNode(id="pl:x", ticker="X", value_chain_id="vc", theme_id="gal",
                     market_cap=None)
    bn = BottleneckNode(id="st", value_chain_id="vc", data_gaps=("not quantified",))
    vc = ValueChainNode(id="vc", theme_id="gal", bottlenecks=(bn,),
                        data_gaps=("coverage absent",), revenue_pool_or_tam=None)
    th = ThemeNode(id="gal", galaxy_id="gal", value_chains=(vc,), candidate_planets=(co,))
    gal = GalaxyNode(id="gal", themes=(th,))
    return UniverseTerrain(
        mode="real_evidence_on_demand", galaxies=(gal,),
        source_coverage={"canonical": 2, "convenience": 1, "fallback": 0},
        provenance_refs=("p1",))


def _oh(theme="X theme", convergence=("a", "b")):
    return SimpleNamespace(theme=theme, domain="ai-infrastructure",
                           cross_domain_convergence=tuple(convergence),
                           megatrend_context=("m1",))


def _slice(oh):
    return SimpleNamespace(subject="X", conflict_warnings=(), deferred_records=(),
                           provenance_chain={}, opportunity_hypothesis=oh)


# =========================================================================== #
# A. Diagnostic models                                                         #
# =========================================================================== #
class ModelTests(unittest.TestCase):
    def test_each_model_constructable_with_defaults(self):
        for cls in _MODELS:
            inst = cls()
            self.assertTrue(dataclasses.is_dataclass(inst))

    def test_no_numeric_score_or_ranking_field(self):
        # No field is a scoring / ranking / rating metric; no field is a float.
        for cls in _MODELS:
            inst = cls()
            for f in dataclasses.fields(cls):
                low = f.name.lower()
                for banned in ("score", "rank", "rating", "investab"):
                    self.assertNotIn(banned, low, "{0}.{1}".format(cls.__name__, f.name))
                self.assertNotIsInstance(
                    getattr(inst, f.name), float,
                    "float field {0}.{1}".format(cls.__name__, f.name))

    def test_built_sample_has_no_float_field(self):
        terrain, summary = _build(["IREN", "AAOI"], _tbt("IREN", "AAOI"))
        diag = build_terrain_diagnostics(terrain, summary)
        objs = [diag] + list(diag.per_ticker)
        for d in diag.per_ticker:
            objs += [x for x in (d.theme_diagnostic, d.value_chain_diagnostic) if x]
        for o in objs:
            for f in dataclasses.fields(o):
                self.assertNotIsInstance(getattr(o, f.name), float,
                                         "{0}.{1}".format(type(o).__name__, f.name))

    def test_all_emitted_labels_are_in_the_vocabulary(self):
        terrain, summary = _build(["IREN", "THIN"], {"IREN": _mock(), "THIN": {}})
        diag = build_terrain_diagnostics(terrain, summary)
        # The 010F TRUST / COMPLETENESS labels are a closed vocabulary. (source_statuses
        # copy the pre-existing upstream fetch vocabulary -- fetched / unavailable / ... --
        # so they are intentionally excluded here.)
        labels = {diag.trust_level, diag.completeness_level}
        for d in diag.per_ticker:
            labels |= {d.terrain_status, d.theme_classification_status,
                       d.value_chain_status, d.bottleneck_status, d.catalyst_status,
                       d.red_team_status, d.cockpit_status, d.trust_label}
            if d.theme_diagnostic is not None:
                labels.add(d.theme_diagnostic.classification_confidence_label)
            if d.value_chain_diagnostic is not None:
                labels.add(d.value_chain_diagnostic.confidence_label)
        self.assertTrue(labels <= LABELS, "off-vocabulary labels: {0}".format(labels - LABELS))

    def test_diagnostics_attach_to_real_terrain_object_ids(self):
        terrain, summary = _build(["IREN", "AAOI", "INOD"], _tbt("IREN", "AAOI", "INOD"))
        diag = build_terrain_diagnostics(terrain, summary)
        ann = diagnostics_by_object_id(terrain, diag)
        company_ids = [nid for nid, n in terrain.all_nodes() if isinstance(n, CompanyNode)]
        self.assertTrue(company_ids)
        for cid in company_ids:
            self.assertIn(cid, ann)
            self.assertTrue(ann[cid])
        # galaxy + value-chain + bottleneck ids also resolve
        for nid, n in terrain.all_nodes():
            if isinstance(n, (GalaxyNode, ValueChainNode, BottleneckNode)) and nid:
                self.assertIn(nid, ann)

    def test_explain_visual_encoding_reads_basis_only(self):
        terrain, summary = _build(["IREN"], _tbt("IREN"))
        co = [n for _i, n in terrain.all_nodes() if isinstance(n, CompanyNode)][0]
        channels = dict(explain_visual_encoding(co))
        # dashed outline (missing market cap) + size basis are surfaced
        self.assertIn("dashed_outline", channels)
        self.assertIn("size", channels)
        self.assertIn("glow", channels)


# =========================================================================== #
# B. Watchlist diagnostics (mock transports, offline)                          #
# =========================================================================== #
class WatchlistDiagnosticTests(unittest.TestCase):
    def test_successful_ticker_is_built_with_trust_label(self):
        terrain, summary = _build(["IREN", "AAOI", "INOD"], _tbt("IREN", "AAOI", "INOD"))
        diag = build_terrain_diagnostics(terrain, summary)
        built = {d.ticker: d for d in diag.per_ticker if d.terrain_status == "built"}
        self.assertEqual(set(built), {"IREN", "AAOI", "INOD"})
        for d in built.values():
            self.assertIn(d.trust_label, ("sufficient", "partial", "weak",
                                          "needs_human_review"))
            self.assertGreater(d.canonical_coverage, 0)

    def test_failed_ticker_is_a_visible_failure_diagnostic(self):
        terrain, summary = _build(
            ["IREN", "BADX"], {"IREN": _mock(), "BADX": _BrokenTransports()})
        diag = build_terrain_diagnostics(terrain, summary)
        bad = [d for d in diag.per_ticker if d.ticker == "BADX"][0]
        self.assertEqual(bad.terrain_status, "failed")
        self.assertEqual(bad.trust_label, "source_failed")
        self.assertIn("BADX", diag.failed_tickers)
        self.assertTrue(any("resolve" in a.lower() for a in bad.data_actions))

    def test_unclassified_ticker_has_explicit_theme_diagnostic(self):
        terrain, summary = _build(["IREN", "THIN"], {"IREN": _mock(), "THIN": {}})
        diag = build_terrain_diagnostics(terrain, summary)
        thin = [d for d in diag.per_ticker if d.ticker == "THIN"][0]
        self.assertEqual(thin.theme_classification_status, "unclassified")
        td = thin.theme_diagnostic
        self.assertEqual(td.classification_confidence_label, "missing")
        self.assertIn("could not be inferred", td.why_unclassified)
        self.assertTrue(td.required_data_to_classify)

    def test_missing_value_chain_bottleneck_marketcap_tam_supplier_diagnostics(self):
        terrain, summary = _build(["IREN"], _tbt("IREN"))
        diag = build_terrain_diagnostics(terrain, summary)
        d = diag.per_ticker[0]
        self.assertIn(d.value_chain_status, ("weak", "missing"))
        self.assertIn(d.bottleneck_status, ("weak", "missing"))
        joined = " ".join(d.data_actions)
        self.assertIn("market-cap", joined)
        self.assertIn("TAM", joined)
        self.assertIn("supplier", joined)
        self.assertTrue(d.value_chain_diagnostic.missing_tam_or_revenue_pool)

    def test_missing_credentials_are_credential_diagnostics_without_leak(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            terrain, summary = build_real_evidence_watchlist_terrain(
                ["IREN"], transports_by_ticker={"IREN": None},
                sec_user_agent=None, fmp_api_key=None, now=_NOW)
        finally:
            socket.socket = real
        diag = build_terrain_diagnostics(terrain, summary)
        d = diag.per_ticker[0]
        statuses = dict(d.source_statuses)
        self.assertEqual(statuses["sec"], "credentials_missing")
        self.assertEqual(statuses["fmp"], "credentials_missing")
        self.assertEqual(d.trust_label, "weak")
        joined = " ".join(d.data_actions)
        self.assertIn("SEC_USER_AGENT", joined)
        self.assertIn("FMP_API_KEY", joined)

    def test_conflicts_and_overrides_surface_at_terrain_level(self):
        terrain, summary = _build(["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                                  enable_yfinance=True)
        diag = build_terrain_diagnostics(terrain, summary)
        self.assertTrue(diag.unresolved_conflicts)  # conflicts detected (resolved by authority)
        self.assertTrue(any("resolved by authority" in w for w in diag.warnings))
        self.assertTrue(any("overridden" in w for w in diag.warnings))

    def test_weak_classification_stays_weak_not_upgraded(self):
        # direct when convergence present; weak when convergence thin; missing when no OH.
        co = CompanyNode(id="pl:x", ticker="X")
        self.assertEqual(
            classify_theme_for_company(co, _slice(_oh(convergence=("a", "b"))), "gal")
            .classification_confidence_label, "direct")
        self.assertEqual(
            classify_theme_for_company(co, _slice(_oh(convergence=())), "gal")
            .classification_confidence_label, "weak")
        self.assertEqual(
            classify_theme_for_company(co, _slice(None), "gal")
            .classification_confidence_label, "missing")
        # and the builder does NOT upgrade a weak classification.
        terrain = _mini_terrain()
        summary = single_ticker_run_summary(
            terrain, {"ticker": "X", "sec": "fetched", "fmp": "fetched",
                      "yfinance": "deferred", "run_timestamp": "t"},
            _slice(_oh(convergence=())))
        diag = build_terrain_diagnostics(terrain, summary)
        self.assertEqual(diag.per_ticker[0].theme_classification_status, "weak")

    def test_completeness_is_partial_while_trust_can_be_sufficient(self):
        terrain, summary = _build(["IREN", "AAOI", "INOD"], _tbt("IREN", "AAOI", "INOD"))
        diag = build_terrain_diagnostics(terrain, summary)
        # value chain / bottleneck / TAM are placeholders -> completeness never "sufficient"
        self.assertEqual(diag.completeness_level, "partial")


# =========================================================================== #
# C. Renderer                                                                  #
# =========================================================================== #
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = _build_pages("dg_render_", ["IREN", "AAOI", "INOD"],
                                 _tbt("IREN", "AAOI", "INOD"))
        cls.dq = _read(cls.paths, "data_quality.html")

    def test_overall_terrain_health_renders(self):
        self.assertIn("Terrain health &amp; trust", self.dq)
        self.assertIn("TRUST level", self.dq)
        self.assertIn("COMPLETENESS level", self.dq)

    def test_per_ticker_diagnostic_table_renders(self):
        self.assertIn("Per-ticker diagnostics", self.dq)
        for col in ("theme", "value chain", "bottleneck", "cockpit", "trust"):
            self.assertIn("<th>{0}</th>".format(col), self.dq)
        for tk in ("IREN", "AAOI", "INOD"):
            self.assertIn(tk, self.dq)

    def test_diagnostic_cards_render(self):
        self.assertIn("Diagnostic cards", self.dq)
        low = self.dq.lower()
        self.assertIn("value chain", low)
        self.assertIn("bottleneck", low)

    def test_data_action_list_renders_data_actions_not_trades(self):
        self.assertIn("Data-sourcing actions per ticker", self.dq)
        self.assertIn("market-cap", self.dq)
        low = self.dq.lower()
        self.assertIsNone(re.search(r"\b(buy|sell)\b", low), "trade token in DQ")
        for banned in ("place order", "place an order", "submit_order", "broker_order"):
            self.assertNotIn(banned, low)

    def test_visual_encoding_explanations_render(self):
        self.assertIn("Visual encoding", self.dq)
        low = self.dq.lower()
        self.assertIn("dashed", low)

    def test_no_key_or_secret_in_html(self):
        secret = "DQ-SECRET-SHOULD-NOT-LEAK-77"
        paths = _build_pages("dg_sec_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                             fmp_api_key=secret, sec_user_agent=secret)
        for name in _PAGES:
            html = _read(paths, name)
            self.assertNotIn(secret, html)
            self.assertNotIn("apikey", html.lower())

    def test_single_real_mode_also_shows_diagnostics(self):
        d = tempfile.mkdtemp(prefix="dg_single_")
        paths = build_universe_app(d, mode="real_evidence_on_demand", ticker="IREN",
                                   transports=_mock(), now=_NOW)
        dq = _read(paths, "data_quality.html")
        self.assertIn("Terrain health &amp; trust", dq)
        self.assertIn("Per-ticker diagnostics", dq)


# =========================================================================== #
# D. Guardrails                                                                #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = _build_pages("dg_guard_", ["IREN", "AAOI", "INOD"],
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

    def test_module_defines_no_new_scoring_function(self):
        tree = ast.parse(open(os.path.join(_UNIVERSE_UI_DIR, "terrain_diagnostics.py"),
                              encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertNotIn("score", node.name.lower())

    def test_module_imports_no_scheduler_broker_or_network(self):
        forbidden = {"sched", "asyncio", "subprocess", "socketserver", "urllib", "http",
                     "socket", "requests", "aiohttp", "httpx"}
        tree = ast.parse(open(os.path.join(_UNIVERSE_UI_DIR, "terrain_diagnostics.py"),
                              encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name.split(".")[0], forbidden)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)

    def test_no_order_words_in_module_source(self):
        src = open(os.path.join(_UNIVERSE_UI_DIR, "terrain_diagnostics.py"),
                   encoding="utf-8").read().lower()
        for banned in ("place order", "submit_order", "broker_order", "buy(", "sell("):
            self.assertNotIn(banned, src)

    def test_demo_remains_byte_identical_default(self):
        d1 = tempfile.mkdtemp(prefix="dg_demo_a_")
        d2 = tempfile.mkdtemp(prefix="dg_demo_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html"):
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                             "demo not byte-identical: {0}".format(name))
        # and demo carries NO diagnostics section
        self.assertNotIn("Terrain health", _read(p1, "data_quality.html"))

    def test_real_single_and_watchlist_modes_still_build(self):
        d = tempfile.mkdtemp(prefix="dg_ok_")
        single = build_universe_app(d, mode="real_evidence_on_demand", ticker="IREN",
                                    transports=_mock(), now=_NOW)
        self.assertTrue(os.path.exists(single["data_quality.html"]))
        wl = _build_pages("dg_ok_wl_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"))
        self.assertTrue(os.path.exists(wl["data_quality.html"]))

    def test_every_data_intel_resolves(self):
        uni = _read(self.paths, "universe.html")
        refs = set(re.findall(r'data-intel="([^"]+)"', uni))
        defs = set(re.findall(r'class="intel-template" id="([^"]+)"', uni))
        self.assertTrue(refs)
        self.assertEqual(refs - defs, set())

    def test_terrain_validates_and_has_no_centre(self):
        terrain, _s = _build(["IREN", "AAOI", "INOD"], _tbt("IREN", "AAOI", "INOD"))
        self.assertEqual(terrain.validate(), ())
        self.assertEqual(terrain.relationship_edges, ())

    def test_whole_build_is_offline_under_socket_block(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            _build_pages("dg_off_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                         enable_yfinance=True)
        finally:
            socket.socket = real


if __name__ == "__main__":
    unittest.main()
