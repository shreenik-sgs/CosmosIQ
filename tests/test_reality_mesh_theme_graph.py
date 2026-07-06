"""IMPLEMENTATION-021D-GRAPH -- the Theme / Value-Chain / Chokepoint Knowledge Graph.

The structured investment-intelligence MAP that powers the Universe Canvas + CosmosIQ Capital.
It is a MAP, never a recommendation. This suite runs entirely OFFLINE -- no network, no
scheduler, no broker, no live endpoint -- and proves:

* the 10 Mega Themes exist (galaxies), with Themes (milky ways) under them, Value Chains (solar
  systems) under Themes, Bottlenecks / Chokepoints (stars) under Value Chains, and companies
  (planets) linkable to bottlenecks; supplier / customer / dependency edges (moons) exist;
* the view-model renders the celestial hierarchy (Galaxy = Mega Theme labelled, etc.);
* **graph membership creates NO CapitalCandidate** -- build the seed, publish NOTHING, assert
  0 candidates; and a CompanyUniverseNode carries no candidate / recommendation / score field;
* **no company is "recommended" because it appears in the graph** -- assert_no_trade_fields on
  every model + a regex sweep of the render / view-model for recommend / score / rank / buy /
  sell / a trade affordance;
* the exact Monitored Company Universe label is present on EVERY company node + every planet row;
* NO fixture ticker leaks into the DEFAULT product UI (empty-store / , /runs, /candidates stay
  clean; the seed graph is NOT auto-rendered there);
* referential integrity (a dangling ref raises); determinism (build_seed twice equal);
* demo + default pulse byte-identical; offline under a socket kill-switch; AST clean (no net /
  scheduler / broker import; no ``*score`` / ``*rank`` function).
"""

from __future__ import annotations

import ast
import os
import re
import socket
import sys
import tempfile
import unittest
from dataclasses import fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import theme_graph as TG
from reality_mesh.theme_graph import (
    MONITORED_LABEL,
    Bottleneck,
    CatalystNode,
    Chokepoint,
    CompanyUniverseNode,
    MegaTheme,
    RiskNode,
    SupplierDependency,
    Theme,
    ThemeGraph,
    ValueChain,
    WeakSignalNode,
    build_seed_theme_graph,
)
from cosmosiq_app import theme_graph_view as TGV
from cosmosiq_app.theme_graph_view import hierarchy_view_model, render_graph_hierarchy

_TG_PY = os.path.join(_SRC, "reality_mesh", "theme_graph.py")
_TGV_PY = os.path.join(_SRC, "cosmosiq_app", "theme_graph_view.py")
_NOW = "2026-07-06T00:00:00Z"

# The exact 10 Mega Themes (galaxies) the first seed must carry.
_EXPECTED_MEGA = (
    "AI Infrastructure", "Physical AI", "Power & Grid", "Optical Networking",
    "Space & Defense", "Nuclear / Energy Security", "Cybersecurity", "Healthcare AI",
    "Robotics / Automation", "Supply Chain Resilience",
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# =========================================================================== #
# The models construct + validate                                             #
# =========================================================================== #
class ModelConstructionTests(unittest.TestCase):
    def test_required_ids_enforced(self):
        for ctor in (
            lambda: MegaTheme(mega_theme_id=""),
            lambda: Theme(theme_id="", mega_theme_ref="m"),
            lambda: Theme(theme_id="t", mega_theme_ref=""),
            lambda: ValueChain(value_chain_id="", theme_ref="t"),
            lambda: Bottleneck(bottleneck_id="", value_chain_ref="v"),
            lambda: CompanyUniverseNode(ticker=""),
            lambda: SupplierDependency(from_ticker="", to_ticker="B"),
            lambda: CatalystNode(catalyst_id="", theme_or_company_ref="x"),
            lambda: RiskNode(risk_id="", theme_or_company_ref="x"),
        ):
            with self.assertRaises(ValueError):
                ctor()

    def test_closed_label_vocabularies_enforced(self):
        with self.assertRaises(ValueError):
            CompanyUniverseNode(ticker="T", role_label="strong_buy")
        with self.assertRaises(ValueError):
            SupplierDependency(from_ticker="A", to_ticker="B", dependency_type="bogus")
        with self.assertRaises(ValueError):
            RiskNode(risk_id="r", theme_or_company_ref="x", severity_label="catastrophic")
        with self.assertRaises(ValueError):
            CatalystNode(catalyst_id="c", theme_or_company_ref="x",
                         expected_window_label="someday")

    def test_chokepoint_is_a_critical_bottleneck(self):
        c = Chokepoint(bottleneck_id="b", name="n", value_chain_ref="v")
        self.assertTrue(c.is_chokepoint)
        self.assertIsInstance(c, Bottleneck)
        self.assertFalse(Bottleneck(bottleneck_id="b", value_chain_ref="v").is_chokepoint)

    def test_company_node_monitored_label_is_mandatory_and_exact(self):
        c = CompanyUniverseNode(ticker="T")
        self.assertEqual(c.monitored_label, MONITORED_LABEL)
        with self.assertRaises(ValueError):
            CompanyUniverseNode(ticker="T", monitored_label="Top Pick")

    def test_monitored_label_text_is_the_exact_string(self):
        self.assertEqual(
            MONITORED_LABEL,
            "Monitored Company Universe -- Not a Capital Candidate unless the pipeline "
            "publishes it.")


# =========================================================================== #
# The seed graph: 10 mega themes + full nesting                                #
# =========================================================================== #
class SeedGraphTests(unittest.TestCase):
    def setUp(self):
        self.g = build_seed_theme_graph()

    def test_all_ten_mega_themes_exist(self):
        names = tuple(m.name for m in self.g.mega_themes)
        self.assertEqual(len(names), 10)
        for expected in _EXPECTED_MEGA:
            self.assertIn(expected, names)

    def test_each_mega_theme_carries_data_sources_needed(self):
        for m in self.g.mega_themes:
            self.assertTrue(m.data_sources_needed, "{0} has no data sources".format(m.name))

    def test_themes_exist_under_mega_themes(self):
        for m in self.g.mega_themes:
            self.assertTrue(self.g.themes_of(m.mega_theme_id),
                            "no theme under {0}".format(m.name))

    def test_value_chains_exist_under_themes(self):
        for t in self.g.themes:
            self.assertTrue(self.g.value_chains_of(t.theme_id),
                            "no value chain under {0}".format(t.name))

    def test_bottlenecks_exist_under_value_chains(self):
        for v in self.g.value_chains:
            self.assertTrue(self.g.bottlenecks_of(v.value_chain_id),
                            "no bottleneck under {0}".format(v.name))

    def test_at_least_one_chokepoint_seeded(self):
        self.assertTrue(any(b.is_chokepoint for b in self.g.bottlenecks))

    def test_companies_link_to_bottlenecks(self):
        # every seeded company links to at least one bottleneck that exists in the graph.
        bn_ids = {b.bottleneck_id for b in self.g.bottlenecks}
        linked = 0
        for c in self.g.companies:
            for ref in c.linked_bottleneck_refs:
                self.assertIn(ref, bn_ids)
                linked += 1
        self.assertGreater(linked, 0)
        # and companies_of() resolves them the other way.
        some_bn = next(b for b in self.g.bottlenecks if self.g.companies_of(b.bottleneck_id))
        self.assertTrue(self.g.companies_of(some_bn.bottleneck_id))

    def test_supplier_customer_dependency_links_exist(self):
        self.assertTrue(self.g.dependencies)
        types = {d.dependency_type for d in self.g.dependencies}
        self.assertTrue(types.issubset(set(rm.DEPENDENCY_TYPES)))
        # dependencies_of() finds edges touching a ticker.
        d0 = self.g.dependencies[0]
        self.assertIn(d0, self.g.dependencies_of(d0.from_ticker))
        self.assertIn(d0, self.g.dependencies_of(d0.to_ticker))

    def test_known_risks_and_catalysts_seeded(self):
        self.assertTrue(self.g.risks)
        self.assertTrue(self.g.catalysts)

    def test_accessors_scoped_correctly(self):
        m = self.g.mega_themes[0]
        for t in self.g.themes_of(m.mega_theme_id):
            self.assertEqual(t.mega_theme_ref, m.mega_theme_id)

    def test_deterministic_build(self):
        self.assertEqual(build_seed_theme_graph(), build_seed_theme_graph())


# =========================================================================== #
# Referential integrity                                                        #
# =========================================================================== #
class ReferentialIntegrityTests(unittest.TestCase):
    def test_dangling_theme_ref_raises(self):
        with self.assertRaises(ValueError):
            ThemeGraph(mega_themes=(MegaTheme(mega_theme_id="m"),),
                       themes=(Theme(theme_id="t", mega_theme_ref="NOPE"),))

    def test_dangling_value_chain_ref_raises(self):
        with self.assertRaises(ValueError):
            ThemeGraph(
                mega_themes=(MegaTheme(mega_theme_id="m"),),
                themes=(Theme(theme_id="t", mega_theme_ref="m"),),
                value_chains=(ValueChain(value_chain_id="v", theme_ref="NOPE"),))

    def test_dangling_bottleneck_ref_raises(self):
        with self.assertRaises(ValueError):
            ThemeGraph(
                mega_themes=(MegaTheme(mega_theme_id="m"),),
                themes=(Theme(theme_id="t", mega_theme_ref="m"),),
                value_chains=(ValueChain(value_chain_id="v", theme_ref="t"),),
                bottlenecks=(Bottleneck(bottleneck_id="b", value_chain_ref="NOPE"),))

    def test_dangling_company_bottleneck_ref_raises(self):
        with self.assertRaises(ValueError):
            ThemeGraph(companies=(CompanyUniverseNode(
                ticker="T", linked_bottleneck_refs=("NOPE",)),))

    def test_dangling_dependency_endpoint_raises(self):
        with self.assertRaises(ValueError):
            ThemeGraph(
                companies=(CompanyUniverseNode(ticker="A"),),
                dependencies=(SupplierDependency(
                    from_ticker="A", to_ticker="B", dependency_type="supplier"),))

    def test_dangling_catalyst_ref_raises(self):
        with self.assertRaises(ValueError):
            ThemeGraph(catalysts=(CatalystNode(
                catalyst_id="c", theme_or_company_ref="NOPE"),))

    def test_whole_seed_graph_is_referentially_intact(self):
        # building it (which validates in __post_init__) must not raise.
        self.assertIsInstance(build_seed_theme_graph(), ThemeGraph)


# =========================================================================== #
# The MAP is NOT a recommendation: no candidate, no score/rank/trade field      #
# =========================================================================== #
class NotARecommendationTests(unittest.TestCase):
    def test_every_graph_model_is_trade_and_score_clean(self):
        for model in TG.GRAPH_MODELS + (ThemeGraph,):
            rm.assert_no_trade_fields(model)

    def test_no_forbidden_token_in_any_model_field_name(self):
        for model in TG.GRAPH_MODELS + (ThemeGraph,):
            for f in fields(model):
                low = f.name.lower()
                for tok in ("buy", "sell", "hold", "order", "trade", "broker", "execution",
                            "score", "rank", "rating", "recommend", "verdict", "investab"):
                    self.assertNotIn(tok, low,
                                     "{0}.{1} exposes {2!r}".format(model.__name__, f.name, tok))

    def test_company_node_has_no_candidate_or_recommendation_field(self):
        # a monitored company node is a MAP placement: it carries no candidate/score/verdict.
        names = {f.name for f in fields(CompanyUniverseNode)}
        for forbidden in ("candidate", "candidate_state", "recommendation", "score", "rank",
                          "rating", "verdict", "is_eligible", "action"):
            self.assertNotIn(forbidden, names)

    def test_graph_membership_creates_no_capital_candidate(self):
        # build the seed graph, publish NOTHING -> the candidate store stays empty.
        from reality_mesh.capital_candidate import published_candidates, eligible_candidates
        store = tempfile.mkdtemp(prefix="tg_nocand_")
        g = build_seed_theme_graph()
        self.assertTrue(g.monitored_tickers)  # the graph HAS monitored tickers
        # ... yet no publish path was run, so there are zero candidates of any kind.
        self.assertEqual(published_candidates(store), ())
        self.assertEqual(eligible_candidates(store), ())

    def test_render_and_view_model_carry_no_recommendation_or_score(self):
        g = build_seed_theme_graph()
        rendered = render_graph_hierarchy(g)
        vm_blob = repr(hierarchy_view_model(g))
        for blob in (rendered, vm_blob):
            low = blob.lower()
            # whole-word sweep: the MAP never renders a recommendation / score / rank / rating
            # verdict (a substring like "operating" or "grade" is fine English).
            self.assertNotRegex(
                low, r"\b(recommend\w*|score\w*|ranked|ranking|rank|rating|investab\w*)\b")
            # no buy/sell verb and no order-placement affordance.
            self.assertNotRegex(low, r"\b(buy|sell)\b")
            self.assertNotRegex(low, r"place order|submit order|order now|buy/sell")

    def test_render_has_no_trade_control(self):
        rendered = render_graph_hierarchy(build_seed_theme_graph())
        self.assertNotIn("<button", rendered)
        self.assertNotIn("<form", rendered)


# =========================================================================== #
# The view-model renders the celestial hierarchy                               #
# =========================================================================== #
class ViewModelRenderTests(unittest.TestCase):
    def setUp(self):
        self.g = build_seed_theme_graph()
        self.rendered = render_graph_hierarchy(self.g)

    def test_all_celestial_levels_labelled(self):
        for phrase in (
            "Galaxy (Mega Theme)", "Milky Way (Theme)", "Solar System (Value Chain)",
            "Star (Bottleneck / Chokepoint)", "Planet (Company)",
            "Moon (Supplier / Customer / Dependency)", "Comet (Catalyst)",
            "Black Hole (Major Risk / Red-Team Hazard)",
        ):
            self.assertIn(phrase, self.rendered)

    def test_galaxy_equals_mega_theme_named(self):
        self.assertIn("Galaxy (Mega Theme): AI Infrastructure", self.rendered)

    def test_chokepoint_marked_distinctly(self):
        self.assertIn("Chokepoint", self.rendered)

    def test_every_company_row_carries_the_monitored_label(self):
        # each planet row is followed by the exact monitored label -- once per rendered company.
        planet_rows = [ln for ln in self.rendered.splitlines()
                       if "Planet (Company):" in ln]
        self.assertTrue(planet_rows)
        self.assertEqual(self.rendered.count(MONITORED_LABEL), len(planet_rows))

    def test_view_model_is_nested_and_carries_monitored_label(self):
        vm = hierarchy_view_model(self.g)
        self.assertEqual(vm["monitored_label"], MONITORED_LABEL)
        self.assertEqual(len(vm["galaxies"]), 10)
        for galaxy in vm["galaxies"]:
            self.assertEqual(galaxy["celestial"], "galaxy")
            for mw in galaxy["milky_ways"]:
                for ss in mw["solar_systems"]:
                    for star in ss["stars"]:
                        for planet in star["planets"]:
                            self.assertEqual(planet["monitored_label"], MONITORED_LABEL)

    def test_view_model_planets_have_no_score_or_verdict_key(self):
        vm = hierarchy_view_model(self.g)
        for galaxy in vm["galaxies"]:
            for mw in galaxy["milky_ways"]:
                for ss in mw["solar_systems"]:
                    for star in ss["stars"]:
                        for planet in star["planets"]:
                            for k in planet:
                                for tok in ("score", "rank", "recommend", "verdict", "buy",
                                            "sell"):
                                    self.assertNotIn(tok, k.lower())


# =========================================================================== #
# No fixture ticker leaks into the DEFAULT product UI                          #
# =========================================================================== #
def _dispatch(store, path):
    from cosmosiq_app import dispatch
    return dispatch({"method": "GET", "path": path, "query": {}, "body": {}},
                    store_dir=store, now=_NOW)


class DefaultUiNoLeakTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="tg_defaultui_")
        self.tickers = build_seed_theme_graph().monitored_tickers

    @staticmethod
    def _leaks(ticker, html):
        # word-boundary match so a coincidental substring ("MP" in "component") is not a leak;
        # a real leak renders the ticker as its own token.
        return re.search(r"\b" + re.escape(ticker) + r"\b", html) is not None

    def test_seed_tickers_absent_from_empty_store_pages(self):
        for path in ("/", "/runs"):
            html = _dispatch(self.store, path)["body"]
            for ticker in self.tickers:
                self.assertFalse(self._leaks(ticker, html),
                                 "{0} leaked into {1}".format(ticker, path))

    def test_candidates_list_is_empty_on_empty_store(self):
        html = _dispatch(self.store, "/candidates")["body"]
        for ticker in self.tickers:
            self.assertFalse(self._leaks(ticker, html))

    def test_candidate_cockpit_is_honest_not_seeded(self):
        # a monitored ticker with no persisted run -> honest "no run", never fabricated.
        html = _dispatch(self.store, "/candidates/NVDA")["body"]
        self.assertNotIn("ELIGIBLE -- full evidence lineage present", html)

    def test_default_pages_do_not_import_the_graph(self):
        # the graph view-model is opt-in reference data: the default page module must not
        # import it (so it can never auto-inject a ticker into the empty-store UI).
        pages_src = _read(os.path.join(_SRC, "cosmosiq_app", "pages.py"))
        api_src = _read(os.path.join(_SRC, "cosmosiq_app", "api.py"))
        for blob in (pages_src, api_src):
            self.assertNotIn("theme_graph", blob)


# =========================================================================== #
# Demo + default pulse byte-identical; offline; AST clean                       #
# =========================================================================== #
class DeterminismAndGuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "ftplib", "smtplib", "selenium", "scrapy", "websocket", "websockets", "pycurl"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "signal"}

    def test_demo_pulse_byte_identical(self):
        a = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        b = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        self.assertEqual(tuple(s.signal_id for s in a.signals),
                         tuple(s.signal_id for s in b.signals))
        self.assertEqual(tuple(f.finding_id for f in a.findings),
                         tuple(f.finding_id for f in b.findings))

    def test_build_seed_offline_under_socket_kill_switch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            g = build_seed_theme_graph()
            rendered = render_graph_hierarchy(g)
        finally:
            socket.socket = real
        self.assertEqual(len(g.mega_themes), 10)
        self.assertIn("Galaxy (Mega Theme)", rendered)

    def _imports(self, path):
        tree = ast.parse(_read(path))
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.append((node.module or "").split(".")[0])
        return mods

    def test_modules_import_no_network_scheduler_broker(self):
        for path in (_TG_PY, _TGV_PY):
            for m in self._imports(path):
                self.assertNotIn(m, self._NET, "{0} imports network {1}".format(path, m))
                self.assertNotIn(m, self._FORBIDDEN, "{0} imports {1}".format(path, m))

    def test_modules_define_no_scoring_or_ranking_function(self):
        for path in (_TG_PY, _TGV_PY):
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    low = node.name.lower()
                    for tok in ("score", "rank", "rating"):
                        self.assertNotIn(tok, low, "{0} defines {1}".format(path, node.name))

    def test_source_has_no_broker_or_wallclock_token(self):
        for path in (_TG_PY, _TGV_PY):
            blob = _read(path).lower()
            for tok in ("place_order", "submit_order", "broker.submit", "execute_trade",
                        "time.time(", "datetime.now("):
                self.assertNotIn(tok, blob, "{0} has {1}".format(path, tok))


if __name__ == "__main__":
    unittest.main()
