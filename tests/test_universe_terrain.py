"""Tests for IMPLEMENTATION-010B -- the Metadata / Knowledge Terrain layer.

The terrain is a formal, typed metadata model (:mod:`universe_ui.terrain`) that is the
SOURCE OF TRUTH for the Economic Universe UI. These tests prove:

A. the model -- every node type + UniverseTerrain is constructable, and VisualEncoding
   separates the size / glow / color / opacity / halo / red_shadow / dashed / orbit
   channels into distinct, independent fields;
B. the demo terrain -- the expected galaxies with themes / value-chains / bottlenecks /
   company planets / dependency moons / semantic edges; ``validate()`` passes; there is
   NO centre-of-universe relationship and every edge endpoint resolves to a real node id;
C. the renderer -- universe.html is projected FROM the terrain (``view.terrain`` present);
   object ids in the HTML come from terrain node ids; every ``data-intel`` resolves;
   visual-encoding, source badges and data gaps derive from terrain; the floating
   preview, dashboard cards and Data Quality panel derive from terrain;
D. guardrails -- no action/execution affordance; no scheduler/network/secret import; no
   new ``*score`` function; deterministic; size stays decoupled from ranking.

Deterministic, stdlib-only, Python 3.9.
"""

from __future__ import annotations

import ast
import html
import os
import re
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from universe_ui.app import build_universe_app
from universe_ui.iren_slice import load_iren_slice
from universe_ui.view_models import build_economic_universe_view
from universe_ui.demo_terrain import build_demo_terrain
from universe_ui import terrain_adapters
from universe_ui.terrain import (
    BottleneckNode,
    CatalystNode,
    CompanyNode,
    DependencyNode,
    GalaxyNode,
    RelationshipEdge,
    RiskNode,
    ThemeNode,
    UniverseTerrain,
    ValueChainLayer,
    ValueChainNode,
    VisualEncoding,
)

_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")

_EXPECTED_GALAXIES = (
    "AI Infrastructure", "Data Centers", "Semiconductors", "Power & Grid",
    "Optics & Networking", "Nuclear & Energy", "Physical AI", "Robotics",
    "Space & Defense",
)


def _all_company_nodes(terrain):
    out = []
    for _id, node in terrain.all_nodes():
        if isinstance(node, CompanyNode):
            out.append(node)
    return out


def _company_by_ticker(terrain, ticker):
    for c in _all_company_nodes(terrain):
        if c.ticker == ticker:
            return c
    return None


# =========================================================================== #
# A. Model                                                                     #
# =========================================================================== #
class TerrainModelTests(unittest.TestCase):
    def test_every_node_type_is_constructable(self):
        enc = VisualEncoding(size_value=42, glow_level=2)
        cat = CatalystNode(id="cat-1", description="ramp", status="confirmed")
        risk = RiskNode(id="risk-1", description="dilution", severity="high")
        dep = DependencyNode(id="dep-1", name="supplier", tier="upstream")
        layer = ValueChainLayer(id="lay-1", label="upstream", order=0)
        bn = BottleneckNode(id="bn-1", name="packaging", severity="high")
        co = CompanyNode(id="pl-1", ticker="XYZ", company_name="Demo",
                         catalysts=(cat,), visual_encoding=enc)
        vc = ValueChainNode(id="vc-1", name="chain", flow_layers=(layer,),
                            bottlenecks=(bn,), companies=(co,), dependencies=(dep,))
        theme = ThemeNode(id="th-1", name="theme", value_chains=(vc,),
                          candidate_planets=(co,), catalysts=(cat,), red_team_risks=(risk,))
        galaxy = GalaxyNode(id="g-1", name="Galaxy", themes=(theme,), risks=(risk,),
                            catalysts=(cat,))
        edge = RelationshipEdge(id="e-1", source_id="g-1", target_id="g-1")
        terrain = UniverseTerrain(galaxies=(galaxy,), relationship_edges=(edge,))
        # all constructed and reachable
        self.assertEqual(co.catalysts[0].status, "confirmed")
        self.assertIn("g-1", terrain.node_ids())
        self.assertTrue(any(isinstance(n, CompanyNode) for _i, n in terrain.all_nodes()))

    def test_visual_encoding_separates_all_channels(self):
        # size is DECOUPLED from glow/color/opacity/halo/red_shadow/dashed/orbit:
        # a large object can be dim, a small object bright.
        enc = VisualEncoding(
            size_value=120, size_basis="market_cap", glow_level=1, glow_basis="status",
            color_class="ev-low", opacity_level="low", opacity_basis="evidence",
            halo_type="catalyst", halo_basis="catalyst", red_shadow=True,
            dashed_outline=True, orbit_distance=3.0, orbit_distance_basis="directness")
        # every channel is its own field with its own value
        self.assertEqual(enc.size_value, 120)
        self.assertEqual(enc.glow_level, 1)          # big but dim -> size != glow
        self.assertEqual(enc.color_class, "ev-low")
        self.assertEqual(enc.opacity_level, "low")
        self.assertEqual(enc.halo_type, "catalyst")
        self.assertTrue(enc.red_shadow)
        self.assertTrue(enc.dashed_outline)
        self.assertEqual(enc.orbit_distance, 3.0)
        # the fields are genuinely distinct attributes (no aliasing)
        names = set(VisualEncoding.__dataclass_fields__)
        for f in ("size_value", "glow_level", "color_class", "opacity_level",
                  "halo_type", "red_shadow", "dashed_outline", "orbit_distance"):
            self.assertIn(f, names)

    def test_validate_flags_unresolved_edge_and_centre(self):
        galaxy = GalaxyNode(id="g-1", name="G")
        bad = UniverseTerrain(
            galaxies=(galaxy,),
            relationship_edges=(RelationshipEdge(id="e", source_id="g-1", target_id="ghost"),))
        self.assertTrue(bad.validate())  # non-empty -> a warning
        with self.assertRaises(ValueError):
            bad.validate(strict=True)
        centre = UniverseTerrain(
            galaxies=(galaxy,),
            relationship_edges=(RelationshipEdge(id="e", source_id="g-1",
                                                 target_id="centre"),))
        self.assertTrue(any("centre" in w.lower() or "resolve" in w.lower()
                            for w in centre.validate()))


# =========================================================================== #
# B. Demo terrain                                                              #
# =========================================================================== #
class DemoTerrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slice = load_iren_slice()
        cls.terrain = build_demo_terrain(cls.slice)

    def test_expected_galaxies_present(self):
        names = {g.name for g in self.terrain.galaxies}
        for expected in _EXPECTED_GALAXIES:
            self.assertIn(expected, names, "missing galaxy {0}".format(expected))
        self.assertEqual(len(self.terrain.galaxies), 9)

    def test_structure_themes_valuechains_bottlenecks_planets_moons_edges(self):
        t = self.terrain
        themes = [th for g in t.galaxies for th in g.themes]
        vcs = [vc for th in themes for vc in th.value_chains]
        bns = [bn for vc in vcs for bn in vc.bottlenecks]
        planets = _all_company_nodes(t)
        moons = [n for _i, n in t.all_nodes() if isinstance(n, DependencyNode)]
        self.assertTrue(themes and vcs and bns and planets and moons)
        self.assertTrue(t.relationship_edges)
        # the one real anchor is IREN
        real = [c for c in planets if c.is_real]
        self.assertEqual([c.ticker for c in real], ["IREN"])

    def test_validate_passes_clean(self):
        self.assertEqual(self.terrain.validate(), ())

    def test_no_centre_and_all_edges_resolve(self):
        ids = self.terrain.node_ids()
        self.assertTrue(self.terrain.relationship_edges)
        for e in self.terrain.relationship_edges:
            self.assertIn(e.source_id, ids, "unresolved edge source {0}".format(e.source_id))
            self.assertIn(e.target_id, ids, "unresolved edge target {0}".format(e.target_id))
            self.assertNotEqual(e.source_id, e.target_id)
            # no endpoint is an artificial centre node (whole-id check)
            self.assertNotIn(e.source_id, ("centre", "center", "hub", "universe", "root"))
            self.assertNotIn(e.target_id, ("centre", "center", "hub", "universe", "root"))
        # a known related pair exists; an unrelated pair does not
        pairs = {(e.source_id, e.target_id) for e in self.terrain.relationship_edges}
        self.assertIn(("ai-infrastructure", "power-grid"), pairs)
        self.assertNotIn(("robotics", "nuclear-energy"), pairs)

    def test_node_ids_match_render_scheme(self):
        # galaxy id = slug; planet id = universe zoom-path; moon id = demo node id
        gids = {g.id for g in self.terrain.galaxies}
        self.assertIn("power-grid", gids)
        self.assertIn("ai-infrastructure", gids)
        iren = _company_by_ticker(self.terrain, "IREN")
        self.assertIsNotNone(iren)
        self.assertTrue(iren.id.startswith("universe/g:ai-infrastructure"))
        self.assertTrue(iren.id.endswith("pl:iren"))

    def test_catalysts_and_risks_are_typed_nodes(self):
        cats = [n for _i, n in self.terrain.all_nodes() if isinstance(n, CatalystNode)]
        risks = [n for _i, n in self.terrain.all_nodes() if isinstance(n, RiskNode)]
        self.assertTrue(cats, "expected CatalystNodes")
        self.assertTrue(risks, "expected RiskNodes")
        # a rumor catalyst is classified as speculative_rumor (confirmed-vs-rumor)
        self.assertTrue(any(c.status == "speculative_rumor" for c in cats))
        self.assertTrue(any(c.status == "confirmed" for c in cats))

    def test_value_chain_layers_are_ordered(self):
        for g in self.terrain.galaxies:
            for th in g.themes:
                for vc in th.value_chains:
                    orders = [layer.order for layer in vc.flow_layers]
                    self.assertEqual(orders, sorted(orders))

    def test_deterministic_terrain(self):
        t2 = build_demo_terrain(self.slice)
        self.assertEqual(self.terrain, t2)


# =========================================================================== #
# C. Renderer projects FROM terrain                                            #
# =========================================================================== #
class RendererFromTerrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="terrain_ui_")
        cls.paths = build_universe_app(cls._tmp)
        cls.html = {}
        for name in ("universe.html", "dashboard.html", "data_quality.html"):
            with open(cls.paths[name], encoding="utf-8") as fh:
                cls.html[name] = fh.read()
        cls.slice = load_iren_slice()
        cls.view = build_economic_universe_view(cls.slice)
        cls.terrain = cls.view.terrain

    def test_view_carries_terrain(self):
        self.assertIsInstance(self.terrain, UniverseTerrain)
        self.assertEqual(self.terrain.validate(), ())

    def test_object_ids_in_html_come_from_terrain(self):
        u = self.html["universe.html"]
        # galaxy ids -> intel-g-<slug> and data-path g:<slug>
        for g in self.terrain.galaxies:
            self.assertIn('id="intel-g-{0}"'.format(g.id), u)
            self.assertIn("g:{0}".format(g.id), u)
        # the IREN planet id (a terrain node id) is the data-path in the HTML
        iren = _company_by_ticker(self.terrain, "IREN")
        self.assertIn('data-path="{0}"'.format(iren.id), u)

    def test_every_data_intel_resolves(self):
        u = self.html["universe.html"]
        ids = set(re.findall(r'id="(intel-[^"]+)"', u))
        refs = set(re.findall(r'data-intel="(intel-[^"]+)"', u))
        self.assertTrue(refs)
        self.assertEqual(refs - ids, set())

    def test_visual_encoding_derives_from_terrain(self):
        # cluster + planet visual sizes / glow in the view equal the terrain encodings
        gnode = {g.id: g for g in self.terrain.galaxies}
        for c in self.view.clusters:
            self.assertEqual(c.visual_size_px, gnode[c.slug].visual_encoding.size_value)
        iren_planet = [p for t in self.view.themes for p in t.planets if p.is_real][0]
        iren_node = _company_by_ticker(self.terrain, "IREN")
        self.assertEqual(iren_planet.visual_size_px, iren_node.visual_encoding.size_value)
        self.assertEqual(iren_planet.glow_level, iren_node.visual_encoding.glow_level)

    def test_source_badges_derive_from_terrain(self):
        iren_node = _company_by_ticker(self.terrain, "IREN")
        iren_planet = [p for t in self.view.themes for p in t.planets if p.is_real][0]
        self.assertEqual(iren_planet.source_authority_badges, iren_node.source_refs)
        # and those exact badges render on the page
        for badge in iren_node.source_refs:
            self.assertIn(badge, self.html["universe.html"])

    def test_data_gaps_and_data_quality_derive_from_terrain(self):
        dq = self.html["data_quality.html"]
        # data gaps come from terrain.data_gaps
        self.assertTrue(self.terrain.data_gaps)
        for gap in self.terrain.data_gaps:
            self.assertIn(html.escape(gap), dq)   # gaps render HTML-escaped
        # source-coverage counts come from terrain.source_coverage
        cov = self.terrain.source_coverage
        self.assertEqual(self.view.data_quality.canonical_count, cov["canonical"])
        self.assertEqual(self.view.data_quality.convenience_count, cov["convenience"])
        self.assertEqual(self.view.data_quality.fallback_count, cov["fallback"])
        # provenance chain comes from terrain.provenance_refs
        self.assertEqual(self.view.data_quality.provenance_chain,
                         tuple(self.terrain.provenance_refs))

    def test_dashboard_and_preview_derive_from_terrain(self):
        dash = self.html["dashboard.html"]
        # every dashboard candidate ticker is a terrain company node
        tickers = {c.ticker for c in _all_company_nodes(self.terrain)}
        for b in self.view.dashboard.buckets:
            for card in b.cards:
                self.assertIn(card.ticker, tickers)
        self.assertIn("Demo candidate dashboard", dash)
        # floating preview + cockpit action present in the universe page
        u = self.html["universe.html"]
        self.assertIn('id="floating-preview"', u)
        self.assertIn('id="fp-cockpit"', u)

    def test_semantic_edges_from_terrain_no_centre(self):
        # the view edges are exactly the terrain relationship edges
        self.assertEqual(len(self.view.edges), len(self.terrain.relationship_edges))
        l0 = re.search(r'data-level="0"[^>]*>(.*?)</section>',
                       self.html["universe.html"], re.S).group(1)
        self.assertIn('class="rel-lines"', l0)
        self.assertNotIn('class="orbit-lines"', l0)   # no hub-and-spoke at L0
        self.assertNotIn('x2="50.00" y2="47.00"', l0)  # no artificial centre


# =========================================================================== #
# D. Guardrails                                                                #
# =========================================================================== #
class TerrainGuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="terrain_guard_")
        cls.paths = build_universe_app(cls._tmp)
        cls.all_html = ""
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            with open(cls.paths[name], encoding="utf-8") as fh:
                cls.all_html += fh.read() + "\n"

    def _new_module_files(self):
        return [os.path.join(_UNIVERSE_UI_DIR, f)
                for f in ("terrain.py", "demo_terrain.py", "terrain_adapters.py")]

    def test_no_action_or_execution_affordance(self):
        low = self.all_html.lower()
        for banned in ("<button", "<form", "onclick", 'type="submit"', "place order",
                       "fetch(", "xmlhttprequest", "submit("):
            self.assertNotIn(banned, low, "banned affordance: {0}".format(banned))
        self.assertIsNone(re.search(r"\b(buy|sell)\b", low))

    def test_no_scheduler_network_or_secret_imports(self):
        forbidden = {"requests", "urllib", "http", "socket", "sched", "asyncio",
                     "subprocess", "aiohttp", "httpx"}
        for path in self._new_module_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)
                if isinstance(node, ast.Attribute):
                    if (isinstance(node.value, ast.Name) and node.value.id == "os"):
                        self.assertNotIn(node.attr, ("environ", "getenv"))
                    self.assertNotIn("secret", node.attr.lower())

    def test_defines_no_new_scoring_function(self):
        for path in self._new_module_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertNotIn("score", node.name.lower())

    def test_two_builds_byte_identical(self):
        d1 = tempfile.mkdtemp(prefix="terrain_a_")
        d2 = tempfile.mkdtemp(prefix="terrain_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            with open(p1[name], "rb") as f1, open(p2[name], "rb") as f2:
                self.assertEqual(f1.read(), f2.read(), "non-deterministic: {0}".format(name))

    def test_size_decoupled_from_ranking_in_terrain(self):
        terrain = build_demo_terrain(load_iren_slice())
        mega = _company_by_ticker(terrain, "(demo) MEGAX")   # big cap, weak status
        small = _company_by_ticker(terrain, "(demo) SMALLX")  # small cap, strong status
        self.assertIsNotNone(mega)
        self.assertIsNotNone(small)
        # size follows magnitude ...
        self.assertGreater(mega.visual_encoding.size_value, small.visual_encoding.size_value)
        # ... but glow (status heat) is INVERTED vs size -> decoupled
        self.assertGreater(small.visual_encoding.glow_level, mega.visual_encoding.glow_level)

    def test_adapters_are_pure_and_prepare_terrain(self):
        # the staged adapters map without touching live data or upstream objects
        terrain = terrain_adapters.terrain_from_slice(load_iren_slice())
        self.assertIsInstance(terrain, UniverseTerrain)
        self.assertEqual(terrain.validate(), ())
        # a thesis-shaped dict maps into a CompanyNode with no new score
        node = terrain_adapters.company_node_from_thesis(
            {"investability_assessment": "thesis_worthy", "timing_confirmation": True},
            node_id="pl-x", ticker="ZZZ", market_cap=1.0e10)
        self.assertIsInstance(node, CompanyNode)
        self.assertEqual(node.thesis_status, "thesis_worthy")
        self.assertGreater(node.visual_encoding.size_value, 0)


if __name__ == "__main__":
    unittest.main()
