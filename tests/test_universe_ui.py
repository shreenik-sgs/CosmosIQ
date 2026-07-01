"""Tests for the IMPLEMENTATION-010A Sudarshan "Economic Universe" static UI.

A runnable LOCAL static-HTML/CSS product UI over the existing EIOS pipeline. These
tests prove it is a pure READ-ONLY PROJECTION + presentation layer:

* seven cross-linked static pages (A universe / B galaxy / C solar_system / D star /
  E cockpit / F dashboard / G data_quality) build deterministically to a tempdir;
* every page carries the fixture/demo + live-not-enabled + scheduler-not-enabled +
  broker-disabled + manual-review status strip;
* the dashboard says "live ranking not enabled" and defines NO new "master score";
* ticker/security mapping appears only WITH an "after value-chain/winner" qualifier;
* data gaps, conflict warnings and source-authority badges render;
* the IREN cockpit page is the ACCEPTED ``render_cockpit_html`` output (panel markers);
* the whole app has NO button/form/onclick/submit/place-order/buy/sell affordance and
  NO fetch/XHR/live call;
* multiple galaxies (>=5), NOT IREN-first, IREN is one planet;
* output is deterministic (two builds byte-identical);
* the ``universe_ui`` modules import no scheduler/network module and define no new
  scoring function;
* visual object SIZE encodes economic magnitude via a bounded log scale that is fully
  DECOUPLED from ranking / bucketing / heat.

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

from universe_ui.app import build_universe_app, PAGE_ORDER
from universe_ui.iren_slice import load_iren_slice
from universe_ui.view_models import (
    build_economic_universe_view,
    visual_size,
    glow_level,
    assign_buckets,
    _card_from_planet,
    _planet_view,
    BUCKET_HIGHEST_CONVICTION,
    BUCKET_TIMING_CONFIRMED,
    MIN_PX,
    MAX_PX,
    DEFAULT_PX,
)
from universe_ui.demo_universe import DemoPlanet, build_demo_universe

_PAGES = ("universe.html", "galaxy.html", "solar_system.html", "star.html",
          "cockpit.html", "dashboard.html", "data_quality.html")

_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")

_STRIP_TOKENS = (
    "Mode: fixture/demo",
    "Live data: not enabled",
    "Scheduler: not enabled",
    "Broker automation: disabled",
    "Manual review required",
)


def _build(out_dir):
    return build_universe_app(out_dir)


class UniverseUIBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="universe_ui_")
        cls.paths = _build(cls._tmp)
        cls.html = {}
        for name in _PAGES:
            with open(cls.paths[name], "r", encoding="utf-8") as fh:
                cls.html[name] = fh.read()
        cls.all_html = "\n".join(cls.html.values())
        cls.slice = load_iren_slice()
        cls.view = build_economic_universe_view(cls.slice)

    # --- A-G: all seven pages produced ------------------------------------
    def test_all_seven_pages_and_assets_written(self):
        for name in _PAGES:
            self.assertTrue(os.path.isfile(self.paths[name]), name)
        self.assertEqual(tuple(PAGE_ORDER), _PAGES)
        self.assertTrue(os.path.isfile(self.paths["assets/universe.css"]))
        self.assertTrue(os.path.isfile(self.paths["assets/universe.js"]))

    # --- persistent status strip on EVERY page ----------------------------
    def test_every_page_has_status_strip(self):
        for name, h in self.html.items():
            for token in _STRIP_TOKENS:
                self.assertIn(token, h, "{0} missing status token: {1}".format(name, token))

    # --- dashboard: live ranking off, no master score ---------------------
    def test_dashboard_no_master_score_no_live_ranking(self):
        d = self.html["dashboard.html"]
        self.assertIn("live ranking not enabled", d.lower())
        self.assertNotIn("master score", d.lower())
        self.assertIn("Demo candidate dashboard", d)

    def test_no_new_master_score_field_anywhere(self):
        self.assertNotIn("master score", self.all_html.lower())

    # --- ticker/security mapping only AFTER value-chain/winner -------------
    def test_ticker_mapping_carries_after_value_chain_qualifier(self):
        # The qualifier text is present on the value-chain and candidate views.
        self.assertIn("derived after value-chain", self.html["solar_system.html"].lower())
        self.assertIn("derived after value-chain", self.html["dashboard.html"].lower())
        # And the qualifier explicitly marks it as NOT the entry point.
        self.assertIn("never the entry point", self.html["solar_system.html"].lower())

    # --- data gaps / conflicts / authority badges render ------------------
    def test_data_gaps_and_conflicts_and_authority_badges(self):
        dq = self.html["data_quality.html"]
        # conflict warnings from the real slice
        self.assertIn("conflict on IREN", dq)
        # data gaps from the real slice
        self.assertIn("coverage_gap", dq)
        # source-authority hierarchy + counts
        self.assertIn("SEC canonical", dq)
        self.assertIn("FMP convenience", dq)
        self.assertIn("yfinance fallback", dq)
        # gaps visible on galaxy + solar pages too
        self.assertIn("Data gaps", self.html["galaxy.html"])
        self.assertIn("Missing data", self.html["solar_system.html"])
        # source-authority badges on the IREN dashboard card
        self.assertIn("SEC canonical", self.html["dashboard.html"])

    # --- cockpit page via the ACCEPTED renderer ---------------------------
    def test_cockpit_page_uses_accepted_renderer_markers(self):
        c = self.html["cockpit.html"]
        self.assertIn("<!-- BEGIN-SECTION:", c)
        self.assertIn('id="panel-', c)
        self.assertIn("Alpha Decision Cockpit", c)
        # wrapped with the status strip (still the accepted doc underneath)
        for token in _STRIP_TOKENS:
            self.assertIn(token, c)

    # --- NO action affordance anywhere ------------------------------------
    def test_no_action_or_execution_affordance(self):
        low = self.all_html.lower()
        for banned in ("<button", "<form", "onclick", 'type="submit"',
                       "place order", "place an order", "fetch(", "xmlhttprequest",
                       "submit("):
            self.assertNotIn(banned, low, "banned affordance present: {0}".format(banned))
        # no buy/sell affordance words as standalone tokens
        self.assertIsNone(re.search(r"\b(buy|sell)\b", low),
                          "buy/sell token present in generated HTML")
        # no live/network script call
        self.assertNotIn("http://", low.replace("http://www.w3.org", ""))

    def test_scripts_are_navigation_only(self):
        # Every <script> block must not contain a network/live/order call.
        scripts = re.findall(r"<script>(.*?)</script>", self.all_html, re.DOTALL)
        self.assertTrue(scripts, "expected navigation JS present")
        for s in scripts:
            low = s.lower()
            for banned in ("fetch(", "xmlhttprequest", "websocket", "eventsource",
                           "importscripts", ".submit(", "sendbeacon", "new image("):
                self.assertNotIn(banned, low, "script contains banned call: {0}".format(banned))

    # --- multiple galaxies, NOT IREN-first, IREN is one planet ------------
    def test_multiple_galaxies_not_iren_first(self):
        self.assertGreaterEqual(len(self.view.clusters), 5)
        self.assertNotEqual(self.view.clusters[0].theme_name, "AI Infrastructure")
        # IREN is exactly one real planet across the whole terrain.
        real = [p for t in self.view.themes for p in t.planets if p.is_real]
        self.assertEqual(len(real), 1)
        self.assertEqual(real[0].ticker, "IREN")
        self.assertEqual(real[0].galaxy_name, "AI Infrastructure")

    def test_iren_statuses_come_from_real_slice(self):
        real = [p for t in self.view.themes for p in t.planets if p.is_real][0]
        thesis = self.slice.investment_thesis
        self.assertEqual(real.investability_label, thesis.investability_assessment)
        self.assertTrue(real.provenance_available)
        # IREN's real red-team 'concern' verdict places it in the cross-cut alerts.
        card = _card_from_planet(real)
        self.assertIn("Red-Team Alerts", card.cross_cut_buckets)

    # --- deterministic output ---------------------------------------------
    def test_two_builds_byte_identical(self):
        d1 = tempfile.mkdtemp(prefix="uui_a_")
        d2 = tempfile.mkdtemp(prefix="uui_b_")
        p1 = _build(d1)
        p2 = _build(d2)
        for name in _PAGES:
            with open(p1[name], "rb") as f1, open(p2[name], "rb") as f2:
                self.assertEqual(f1.read(), f2.read(), "non-deterministic page: {0}".format(name))

    # --- buckets come only from EXISTING statuses -------------------------
    def test_buckets_map_from_existing_statuses(self):
        # thesis_worthy_timing_confirmed -> Timing-Confirmed
        primary, _ = assign_buckets(
            investability_label="thesis_worthy_timing_confirmed",
            timing_label="timing confirmed", red_team_label="pass",
            recommendation_label="suitable_candidate", catalyst_label="",
            capital_structure_risk=False, data_quality="high", evidence_count=9)
        self.assertEqual(primary, BUCKET_TIMING_CONFIRMED)
        # blocked_for_user / red-team fail -> Blocked/Avoid
        primary, cross = assign_buckets(
            investability_label="watch", timing_label="timing not confirmed",
            red_team_label="fail", recommendation_label="blocked_for_user",
            catalyst_label="", capital_structure_risk=True, data_quality="low",
            evidence_count=2)
        self.assertEqual(primary, "Blocked/Avoid")
        self.assertIn("Red-Team Alerts", cross)


class VisualSizeEncodingTests(unittest.TestCase):
    """Size = economic magnitude via a bounded log scale, DECOUPLED from ranking."""

    @classmethod
    def setUpClass(cls):
        cls.slice = load_iren_slice()
        cls.view = build_economic_universe_view(cls.slice)
        cls.cards = {c.ticker: c
                     for b in cls.view.dashboard.buckets for c in b.cards}
        cls.clusters = {c.theme_name: c for c in cls.view.clusters}

    def _bucket_of(self, ticker):
        return [b.name for b in self.view.dashboard.buckets
                if any(c.ticker == ticker for c in b.cards)]

    # --- planet size derived from market_cap, monotonic & bounded ---------
    def test_planet_size_from_market_cap_monotonic(self):
        small = visual_size(9.0e8, "planet")
        mid = visual_size(1.0e11, "planet")
        mega = visual_size(3.4e12, "planet")  # NVIDIA-scale
        self.assertLess(small, mid)
        self.assertLess(mid, mega)
        self.assertGreaterEqual(small, MIN_PX)
        self.assertLessEqual(mega, MAX_PX)
        # NVIDIA-scale planet is drawn larger than a small-cap planet.
        self.assertGreater(self.cards["(demo) MEGAX"].visual_size_px,
                           self.cards["(demo) SMALLX"].visual_size_px)

    # --- galaxy size derived from theme_tam -------------------------------
    def test_galaxy_size_from_theme_tam(self):
        big = self.clusters["Data Centers"]        # theme_tam 1.2e12
        small = self.clusters["Optics & Networking"]  # theme_tam 2.5e11
        self.assertGreater(big.visual_size_px, small.visual_size_px)
        self.assertEqual(big.visual_size_px, visual_size(big.theme_tam, "galaxy"))

    # --- missing magnitude -> neutral size + data-gap marker + dashed -----
    def test_missing_magnitude_uses_default_and_gap_marker(self):
        actx = self.cards["(demo) ACTX"]            # market_cap None
        self.assertTrue(actx.magnitude_missing)
        self.assertEqual(actx.visual_size_px, DEFAULT_PX)
        phai = self.clusters["Physical AI"]          # theme_tam None
        self.assertTrue(phai.magnitude_missing)
        self.assertEqual(phai.visual_size_px, DEFAULT_PX)
        # the dashed outline + gap marker are rendered on the page
        tmp = tempfile.mkdtemp(prefix="uui_gap_")
        paths = _build(tmp)
        with open(paths["dashboard.html"], encoding="utf-8") as fh:
            dash = fh.read()
        self.assertIn("magnitude missing", dash.lower())
        self.assertIn("dashed", dash.lower())

    # --- size does NOT affect ranking / bucket / ordering -----------------
    def test_size_does_not_affect_bucket_or_ordering(self):
        g = build_demo_universe().galaxies[0]
        common = dict(value_chain_role="role", proximity_to_bottleneck="at the bottleneck",
                      investability_label="watch", recommendation_label="monitor_only",
                      evidence_count=5, data_quality="medium")
        big = DemoPlanet("AAA", "Big", market_cap=3.0e12, **common)
        small = DemoPlanet("BBB", "Small", market_cap=1.0e9, **common)
        cb = _card_from_planet(_planet_view(g, big, None))
        cs = _card_from_planet(_planet_view(g, small, None))
        # identical alpha statuses -> same bucket + same ordering key ...
        self.assertEqual(cb.primary_bucket, cs.primary_bucket)
        self.assertEqual(cb.cross_cut_buckets, cs.cross_cut_buckets)
        self.assertEqual(cb.ordering_value, cs.ordering_value)
        # ... despite very different visual size.
        self.assertNotEqual(cb.visual_size_px, cs.visual_size_px)

    # --- brightness/heat is separate from size ----------------------------
    def test_brightness_separate_from_size(self):
        mega = self.cards["(demo) MEGAX"]    # large size, weak status
        small = self.cards["(demo) SMALLX"]  # small size, strong status
        self.assertGreater(mega.visual_size_px, small.visual_size_px)   # size: mega bigger
        self.assertGreater(small.glow_level, mega.glow_level)           # glow: small brighter
        # glow is a pure function of status, independent of market_cap
        self.assertEqual(
            small.glow_level,
            glow_level(investability_label=small.investability_label,
                       timing_label=small.timing_label,
                       recommendation_label=small.recommendation_label))

    # --- a large existing company does NOT auto-become a top candidate ----
    def test_megacap_weak_status_not_top_candidate(self):
        buckets = self._bucket_of("(demo) MEGAX")
        self.assertNotIn(BUCKET_HIGHEST_CONVICTION, buckets)
        self.assertNotIn(BUCKET_TIMING_CONFIRMED, buckets)
        self.assertIn("Early Watchlist", buckets)

    # --- raw magnitude appears in the card details ------------------------
    def test_raw_magnitude_visible_in_details(self):
        tmp = tempfile.mkdtemp(prefix="uui_raw_")
        paths = _build(tmp)
        with open(paths["dashboard.html"], encoding="utf-8") as fh:
            dash = fh.read()
        with open(paths["universe.html"], encoding="utf-8") as fh:
            uni = fh.read()
        self.assertIn("market cap (DEMO)", dash)      # raw label present
        self.assertIn("$3.40T", dash)                 # MEGAX raw market cap
        self.assertIn("theme TAM (DEMO)", uni)        # galaxy raw TAM label


class UniverseUISafetyGuardTests(unittest.TestCase):
    """Static (AST/source) guards: no scheduler/network module, no new scoring fn."""

    def _module_files(self):
        return [os.path.join(_UNIVERSE_UI_DIR, f)
                for f in sorted(os.listdir(_UNIVERSE_UI_DIR)) if f.endswith(".py")]

    def test_no_scheduler_or_network_imports(self):
        forbidden = {"requests", "urllib", "http", "socket", "sched",
                     "asyncio", "subprocess", "aiohttp", "httpx"}
        for path in self._module_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        self.assertNotIn(root, forbidden,
                                         "{0} imports forbidden {1}".format(path, root))
                elif isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".")[0]
                    self.assertNotIn(root, forbidden,
                                     "{0} imports-from forbidden {1}".format(path, root))

    def test_no_env_or_secret_access(self):
        # AST-based so docstrings that MENTION os.environ/os.getenv don't false-positive.
        for path in self._module_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if (isinstance(node.value, ast.Name) and node.value.id == "os"
                            and node.attr in ("environ", "getenv")):
                        self.fail("{0} accesses os.{1}".format(path, node.attr))
                    self.assertNotIn("secret", node.attr.lower(),
                                     "{0} accesses a secret attribute".format(path))
                if isinstance(node, ast.Name):
                    self.assertNotIn("getenv", node.id.lower(),
                                     "{0} references getenv".format(path))

    def test_defines_no_new_scoring_function(self):
        for path in self._module_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertNotIn("score", node.name.lower(),
                                     "{0} defines scoring fn {1}".format(path, node.name))

    def test_visual_size_is_pure_bounded_helper(self):
        # It is a formatter: bounded, deterministic, and never negative-going.
        self.assertEqual(visual_size(None), DEFAULT_PX)
        self.assertEqual(visual_size(0), DEFAULT_PX)
        self.assertEqual(visual_size(-5), DEFAULT_PX)
        self.assertGreaterEqual(visual_size(1e6, "planet"), MIN_PX)
        self.assertLessEqual(visual_size(1e15, "planet"), MAX_PX)


if __name__ == "__main__":
    unittest.main()
