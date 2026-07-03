"""Tests for IMPLEMENTATION-010C -- the Evidence-Ingested Terrain Builder.

``terrain_adapters.terrain_from_slice(...)`` now builds a REAL, sparse
:class:`UniverseTerrain` (mode ``evidence_ingested_fixture``) from the accepted 009G
evidence-alpha slice (IREN), and ``build_universe_app(out, mode="evidence_ingested_fixture")``
renders the whole UI from THAT terrain. These tests prove:

A. builder -- ``terrain_from_slice`` is no longer the demo terrain (mode is
   ``evidence_ingested_fixture``; not the 9 demo galaxies); an evidence-derived IREN
   CompanyNode carries thesis (Nivesha) / personalized (Saarathi, a RANGE) / manual
   (Kriya preview) state; data gaps + source coverage + provenance refs are preserved;
   ``validate()`` passes; there is no centre edge; VisualEncoding comes from the existing
   helpers and size stays decoupled from ranking;
B. IREN vertical slice -- the terrain builds from the accepted slice; IREN is a company
   node; a related theme (+ value-chain / bottleneck) appears; Data Quality reflects the
   fixture SEC/FMP/yfinance counts; conflicts + overridden facts stay visible; the cockpit
   link is present; NO trade / broker order appears;
C. renderer -- the evidence-mode build renders universe / dashboard / data_quality from
   the evidence terrain; every ``data-intel`` resolves; the floating preview carries
   evidence-derived fields; the missing-data placeholders + "terrain incomplete" notice
   are visible; the accepted SKY layout (body.sky hero + below-fold pane + no visible
   connector graph / centre hub) is preserved; the mode is shown as
   ``evidence_ingested_fixture`` (never live / demo);
D. guardrails -- no live network / API / secret import (AST); no scheduler; no broker; no
   buy/sell/order/submit affordance; no new ``*score`` function; no unrelated demo
   galaxies in evidence mode; deterministic (two evidence-mode builds are byte-identical);
   the full suite stays green.

Deterministic, stdlib-only, Python 3.9.
"""

from __future__ import annotations

import ast
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
from universe_ui import terrain_adapters
from universe_ui.terrain_adapters import (
    EvidenceTerrainBuildInput,
    build_input_from_evidence_slice,
    terrain_from_slice,
)
from universe_ui.view_models import build_economic_universe_view
from universe_ui.terrain import (
    BottleneckNode,
    CompanyNode,
    UniverseTerrain,
    ValueChainNode,
)

_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")

_DEMO_GALAXIES = (
    "Data Centers", "Semiconductors", "Power & Grid", "Optics & Networking",
    "Nuclear & Energy", "Physical AI", "Robotics", "Space & Defense",
)


def _companies(terrain):
    return [n for _i, n in terrain.all_nodes() if isinstance(n, CompanyNode)]


def _company(terrain, ticker):
    for c in _companies(terrain):
        if c.ticker == ticker:
            return c
    return None


# =========================================================================== #
# A. Builder                                                                   #
# =========================================================================== #
class EvidenceBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slice = load_iren_slice()
        cls.terrain = terrain_from_slice(cls.slice)

    def test_not_the_demo_terrain(self):
        self.assertIsInstance(self.terrain, UniverseTerrain)
        # honest mode label -- not demo, not live
        self.assertEqual(self.terrain.mode, "evidence_ingested_fixture")
        # ONE candidate galaxy, not the nine demo galaxies
        self.assertEqual(len(self.terrain.galaxies), 1)
        names = {g.name for g in self.terrain.galaxies}
        for demo in _DEMO_GALAXIES:
            self.assertNotIn(demo, names)
        # deterministic build id, no clock
        self.assertEqual(self.terrain.build_id, "evidence-terrain-iren")

    def test_build_input_captures_artifacts_without_mutation(self):
        bi = build_input_from_evidence_slice(self.slice)
        self.assertIsInstance(bi, EvidenceTerrainBuildInput)
        # the captured artifacts are the SAME objects the slice produced (read, not copied)
        self.assertIs(bi.investment_thesis, self.slice.investment_thesis)
        self.assertIs(bi.personalized_action, self.slice.personalized_action)
        self.assertIs(bi.ingestion_result, self.slice.ingestion_result)
        self.assertEqual(bi.subject, "IREN")
        self.assertEqual(bi.cockpit_link, "cockpit.html")

    def test_iren_company_node_is_evidence_derived(self):
        iren = _company(self.terrain, "IREN")
        self.assertIsNotNone(iren)
        self.assertTrue(iren.is_real)
        # Nivesha investability comes from the thesis
        self.assertEqual(iren.thesis_status,
                         self.slice.investment_thesis.investability_assessment)
        self.assertEqual(iren.timing_confirmation_status, "timing confirmed")
        # Saarathi personalized fit is a RANGE only -- carried, and the exact user amount
        # appears ONLY as the explicit Kriya preview (never an order).
        reasons = " ".join(iren.top_reasons)
        rng = self.slice.personalized_action.suggested_sizing_range_pct
        self.assertIn("sizing guardrail", reasons.lower())
        self.assertIn("{0:.2f}-{1:.2f}%".format(rng[0], rng[1]), reasons)
        self.assertIn("range only", reasons.lower())
        # Kriya = manual execution PREVIEW; ticket previewed; no broker order. The exact
        # user amount appears ONLY here (from the explicit ManualExecutionIntent).
        self.assertIn("preview", reasons.lower())
        self.assertIn("2,000", reasons)
        self.assertIn("broker order none", reasons.lower())
        self.assertIsNone(self.slice.manual_trade_ticket.broker_order_id)

    def test_data_gaps_coverage_provenance_preserved(self):
        t = self.terrain
        # explicit terrain-incompleteness gap (nothing fabricated)
        self.assertTrue(any(str(g).lower().startswith("terrain incomplete") for g in t.data_gaps))
        # real slice coverage gaps flow through
        self.assertTrue(any("coverage_gap" in str(g) for g in t.data_gaps))
        # ACTUAL source-authority + factual/signal counts (not invented)
        cov = t.source_coverage
        auth = self.slice.ingestion_result.authority_summary
        self.assertEqual(cov["canonical"], auth["canonical"])
        self.assertEqual(cov["convenience"], auth["convenience"])
        self.assertEqual(cov["fallback"], auth["fallback"])
        self.assertEqual(cov["signal"], len(self.slice.intelligence_assessment.signals))
        self.assertEqual(cov["factual"],
                         len(self.slice.intelligence_assessment.factual_observation_ids))
        # provenance preserves the originating reasoning-object ids
        prov = " ".join(t.provenance_refs)
        self.assertIn(self.slice.investment_thesis.id, prov)
        self.assertIn(self.slice.opportunity_hypothesis.id, prov)
        self.assertIn(self.slice.personalized_action.id, prov)

    def test_validate_passes_and_no_centre(self):
        self.assertEqual(self.terrain.validate(), ())
        # a single-theme terrain supports no cross-theme edges -> none invented, no centre
        self.assertEqual(self.terrain.relationship_edges, ())

    def test_visual_encoding_from_helpers_size_decoupled(self):
        from universe_ui.view_models import visual_size, glow_level, DEFAULT_PX
        iren = _company(self.terrain, "IREN")
        enc = iren.visual_encoding
        # market cap is NOT surfaced by the pipeline -> neutral size + dashed gap marker
        self.assertIsNone(iren.market_cap)
        self.assertEqual(enc.size_value, visual_size(None, "planet"))
        self.assertEqual(enc.size_value, DEFAULT_PX)
        self.assertTrue(enc.dashed_outline)
        # glow (status heat) is bright despite the neutral size -> decoupled from magnitude
        self.assertEqual(enc.glow_level, glow_level(
            investability_label=iren.thesis_status,
            timing_label=iren.timing_confirmation_status,
            recommendation_label=self.slice.personalized_action.recommendation_status))
        self.assertEqual(enc.glow_level, 3)
        # red-team concern -> red shadow, never suppressed
        self.assertTrue(enc.red_shadow)
        self.assertEqual(iren.red_team_status, "concern")


# =========================================================================== #
# B. IREN vertical slice                                                       #
# =========================================================================== #
class EvidenceVerticalSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slice = load_iren_slice()
        cls.terrain = terrain_from_slice(cls.slice)
        cls.view = build_economic_universe_view(cls.slice, terrain=cls.terrain)

    def test_iren_company_and_related_theme_appear(self):
        self.assertEqual(len(self.view.themes), 1)
        theme = self.view.themes[0]
        # IREN is a company/planet in the view
        self.assertEqual([p.ticker for p in theme.planets], ["IREN"])
        # a value chain + a (constraint-context) bottleneck appear
        self.assertTrue(theme.solar_systems)
        self.assertTrue(theme.stars)
        # the terrain carries a ValueChainNode + BottleneckNode
        vcs = [n for _i, n in self.terrain.all_nodes() if isinstance(n, ValueChainNode)]
        bns = [n for _i, n in self.terrain.all_nodes() if isinstance(n, BottleneckNode)]
        self.assertTrue(vcs and bns)

    def test_data_quality_reflects_fixture_counts(self):
        dq = self.view.data_quality
        auth = self.slice.ingestion_result.authority_summary
        self.assertEqual(dq.canonical_count, auth["canonical"])
        self.assertEqual(dq.convenience_count, auth["convenience"])
        self.assertEqual(dq.fallback_count, auth["fallback"])
        self.assertIn("evidence_ingested_fixture", dq.run_mode)
        self.assertFalse(dq.live_enabled)

    def test_conflicts_and_overridden_visible(self):
        dq = self.view.data_quality
        self.assertTrue(dq.conflict_warnings)
        self.assertTrue(any("conflict on IREN" in c for c in dq.conflict_warnings))
        self.assertTrue(dq.overridden_facts)
        self.assertTrue(any("overridden" in o.lower() for o in dq.overridden_facts))

    def test_cockpit_link_present_no_trade(self):
        iren = _company(self.terrain, "IREN")
        self.assertEqual(iren.cockpit_link, "cockpit.html")
        # the slice never confirms/places an order
        self.assertIsNone(self.slice.manual_trade_ticket.broker_order_id)
        self.assertEqual(self.slice.manual_trade_ticket.state, "previewed")


# =========================================================================== #
# C. Renderer (evidence-mode build)                                            #
# =========================================================================== #
class EvidenceRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="evidence_ui_")
        cls.paths = build_universe_app(cls._tmp, mode="evidence_ingested_fixture")
        cls.html = {}
        for name in ("universe.html", "dashboard.html", "data_quality.html"):
            with open(cls.paths[name], encoding="utf-8") as fh:
                cls.html[name] = fh.read()

    def test_pages_render_from_evidence_terrain(self):
        u = self.html["universe.html"]
        # the one evidence galaxy id is in the HTML; the demo galaxies are not
        self.assertIn('id="intel-g-ai-infrastructure"', u)
        for demo in _DEMO_GALAXIES:
            self.assertNotIn(demo, u)
        # the IREN planet (a terrain node id) is the data-path
        self.assertIn("pl:iren", u)

    def test_every_data_intel_resolves(self):
        u = self.html["universe.html"]
        ids = set(re.findall(r'id="(intel-[^"]+)"', u))
        refs = set(re.findall(r'data-intel="(intel-[^"]+)"', u))
        self.assertTrue(refs)
        self.assertEqual(refs - ids, set())

    def test_floating_preview_has_evidence_fields(self):
        u = self.html["universe.html"]
        self.assertIn('id="floating-preview"', u)
        self.assertIn('id="fp-cockpit"', u)
        # the IREN planet body carries its evidence-derived preview + a cockpit link
        m = re.search(r'data-kind="planet"[^>]*pl:iren[^>]*data-cockpit="cockpit\.html"', u)
        self.assertIsNotNone(m, "IREN planet body missing evidence cockpit hook")
        self.assertIn("IREN", u)
        self.assertIn("thesis_worthy_timing_confirmed", u)  # Nivesha status shown
        self.assertIn("SEC canonical", u)                    # source-authority badges

    def test_missing_data_placeholders_and_incomplete_notice(self):
        u = self.html["universe.html"]
        dq = self.html["data_quality.html"]
        # the "terrain incomplete" notice is visible on both pages
        self.assertIn("terrain incomplete", u.lower())
        self.assertIn("terrain incomplete", dq.lower())
        # missing-magnitude dashed placeholders are shown (nothing fabricated)
        self.assertIn("magnitude missing", u.lower())
        self.assertIn("Data gaps", u)

    def test_sky_layout_preserved_and_mode_is_evidence(self):
        u = self.html["universe.html"]
        self.assertIn('<body class="sky">', u)
        self.assertIn('class="universe-hero"', u)
        self.assertIn('class="intel-pane intel-section"', u)
        self.assertLess(u.index('class="universe-hero"'), u.index('id="intel-pane"'))
        # clean cosmos: no visible relationship-line / hub-and-spoke SVG at L0
        l0 = re.search(r'data-level="0"[^>]*>(.*?)</section>', u, re.S).group(1)
        self.assertNotIn('class="rel-lines"', l0)
        self.assertNotIn('class="orbit-lines"', l0)
        self.assertNotIn("<line ", l0)
        # mode is shown as the evidence fixture -- never live, never demo
        self.assertIn("Mode: Evidence Fixture", u)
        self.assertNotIn("Mode: Demo Fixture", u)
        self.assertNotIn("DEMO", u)


# =========================================================================== #
# D. Guardrails                                                                #
# =========================================================================== #
class EvidenceGuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="evidence_guard_")
        cls.paths = build_universe_app(cls._tmp, mode="evidence_ingested_fixture")
        cls.all_html = ""
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            with open(cls.paths[name], encoding="utf-8") as fh:
                cls.all_html += fh.read() + "\n"

    def _module_files(self):
        return [os.path.join(_UNIVERSE_UI_DIR, f)
                for f in ("terrain_adapters.py", "app.py", "render.py")]

    def test_no_action_or_broker_affordance(self):
        # NB: honest negations like "broker order none" are NOT affordances -- the banned
        # list targets real action/execution/network hooks, not the word "broker".
        low = self.all_html.lower()
        for banned in ("<button", "<form", "onclick", 'type="submit"', "place order",
                       "place an order", "fetch(", "xmlhttprequest", "submit("):
            self.assertNotIn(banned, low, "banned affordance: {0}".format(banned))
        self.assertIsNone(re.search(r"\b(buy|sell)\b", low), "buy/sell token present")
        # the ticket is a preview only: no broker order id anywhere
        self.assertNotIn('broker_order_id":"', low)

    def test_no_scheduler_network_or_secret_imports(self):
        forbidden = {"requests", "urllib", "http", "socket", "sched", "asyncio",
                     "subprocess", "aiohttp", "httpx"}
        for path in self._module_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], forbidden)
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name) and node.value.id == "os":
                        self.assertNotIn(node.attr, ("environ", "getenv"))
                    self.assertNotIn("secret", node.attr.lower())

    def test_defines_no_new_scoring_function(self):
        path = os.path.join(_UNIVERSE_UI_DIR, "terrain_adapters.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertNotIn("score", node.name.lower())

    def test_no_unrelated_demo_galaxies_in_evidence_mode(self):
        for demo in _DEMO_GALAXIES:
            self.assertNotIn(demo, self.all_html,
                             "demo galaxy leaked into evidence mode: {0}".format(demo))

    def test_two_evidence_builds_byte_identical(self):
        d1 = tempfile.mkdtemp(prefix="evidence_a_")
        d2 = tempfile.mkdtemp(prefix="evidence_b_")
        p1 = build_universe_app(d1, mode="evidence_ingested_fixture")
        p2 = build_universe_app(d2, mode="evidence_ingested_fixture")
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            with open(p1[name], "rb") as f1, open(p2[name], "rb") as f2:
                self.assertEqual(f1.read(), f2.read(), "non-deterministic: {0}".format(name))

    def test_demo_mode_still_default_and_unchanged(self):
        # the default build is still the demo universe (all existing tests rely on it)
        d = tempfile.mkdtemp(prefix="evidence_demo_")
        paths = build_universe_app(d)  # default mode="demo"
        with open(paths["universe.html"], encoding="utf-8") as fh:
            u = fh.read()
        self.assertIn("Mode: Demo Fixture", u)
        self.assertIn("AI Infrastructure", u)
        self.assertIn("Data Centers", u)


if __name__ == "__main__":
    unittest.main()
