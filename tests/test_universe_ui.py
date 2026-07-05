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
from universe_ui.render import render_capital_candidates
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
    CIODashboardView,
    MIN_PX,
    MAX_PX,
    DEFAULT_PX,
)
from universe_ui.demo_universe import DemoPlanet, build_demo_universe

# Top-level product sections. Galaxy / value-chain / bottleneck are zoom LEVELS
# inside universe.html, not separate pages.
_PAGES = (
    "universe.html", "dashboard.html", "capital_candidates.html", "cockpit.html",
    "data_quality.html", "reality_mesh.html", "portfolio_intelligence.html",
)

# Pages that must NOT exist as separate primary pages any more.
_REMOVED_PAGES = ("galaxy.html", "solar_system.html", "star.html")

_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")

_STRIP_TOKENS = (
    "Mode: Demo Fixture",
    "Live Data: Off",
    "Scheduler: Off",
    "Broker: Disabled",
    "Execution: Manual Review Only",
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

    # --- four top-level artifacts produced --------------------------------
    def test_all_pages_and_assets_written(self):
        for name in _PAGES:
            self.assertTrue(os.path.isfile(self.paths[name]), name)
        self.assertEqual(tuple(PAGE_ORDER), _PAGES)
        self.assertTrue(os.path.isfile(self.paths["assets/universe.css"]))
        self.assertTrue(os.path.isfile(self.paths["assets/universe.js"]))
        self.assertTrue(os.path.isfile(self.paths["assets/cosmosiq.css"]))
        self.assertTrue(os.path.isfile(self.paths["assets/universe_canvas.css"]))
        self.assertTrue(os.path.isfile(self.paths["assets/universe_canvas.js"]))
        with open(self.paths["assets/cosmosiq.css"], encoding="utf-8") as fh:
            shell_css = fh.read()
        with open(self.paths["assets/universe_canvas.css"], encoding="utf-8") as fh:
            canvas_css = fh.read()
        self.assertIn(".command-bar", shell_css)
        self.assertIn(".status-strip", shell_css)
        self.assertIn(".viewport", canvas_css)
        self.assertIn(".cosmic-object", canvas_css)
        self.assertNotIn(".cosmic-object", shell_css)

    # --- galaxy / value-chain / star are NOT separate primary pages -------
    def test_entity_pages_are_not_top_level(self):
        for name in _REMOVED_PAGES:
            self.assertNotIn(name, self.paths)
            self.assertFalse(os.path.isfile(os.path.join(self._tmp, name)),
                             "{0} should not be generated".format(name))
        # The top nav lists the production product surfaces.
        for page, h in self.html.items():
            if page == "cockpit.html":
                continue  # cockpit has its own back-strip, checked separately
            navbar = h.split('<div class="wrap">')[0]
            for name in _REMOVED_PAGES:
                self.assertNotIn('href="{0}"'.format(name), navbar,
                                 "{0} nav lists {1}".format(page, name))
            for fname in _PAGES:
                self.assertIn('href="{0}"'.format(fname), navbar)

    # --- persistent status strip on EVERY page ----------------------------
    def test_every_page_has_status_strip(self):
        for name, h in self.html.items():
            for token in _STRIP_TOKENS:
                self.assertIn(token, h, "{0} missing status token: {1}".format(name, token))

    # --- dashboard: live data off, no master score ------------------------
    def test_dashboard_no_master_score_no_live_ranking(self):
        d = self.html["dashboard.html"]
        self.assertIn("Live Data: Off", d)
        self.assertNotIn("master score", d.lower())
        self.assertIn("CosmosIQ Capital", d)

    def test_no_new_master_score_field_anywhere(self):
        self.assertNotIn("master score", self.all_html.lower())

    def test_cosmosiq_public_naming_and_retired_terms_absent(self):
        generated = self.all_html
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            generated += "\n" + fh.read()
        with open(self.paths["assets/universe.js"], encoding="utf-8") as fh:
            generated += "\n" + fh.read()
        for required in ("CosmosIQ", "Universal Intelligence OS", "Universe Canvas",
                         "CosmosIQ Capital", "Trust &amp; Data Quality",
                         "Foundation Layer", "Intelligence Governance Layer",
                         "Reality Intelligence Layer", "Signal Fusion",
                         "Opportunity Discovery Layer", "Investment Diligence Layer",
                         "Portfolio Intelligence Layer", "Execution Preview Layer",
                         "Learning &amp; Feedback Layer"):
            self.assertIn(required, generated)
        for retired in ("SUDARSHAN", "Sudarshan", "Adhāra", "Adhara", "Buddhi",
                        "Tattva", "Sphurana", "Nivesha", "Saarathi", "Kriya",
                        "Anubhava", "Alpha Decision Cockpit"):
            self.assertNotIn(retired, generated)

    def test_generated_artifacts_no_action_or_hidden_scoring_language(self):
        generated = self.all_html
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            generated += "\n" + fh.read()
        with open(self.paths["assets/universe.js"], encoding="utf-8") as fh:
            generated += "\n" + fh.read()
        low = generated.lower()
        for banned in ("<button", "<form", "onclick", "type=\"submit\"",
                       "broker automation", "not enabled"):
            self.assertNotIn(banned, low)
        self.assertIsNone(re.search(r"\b(buy|sell|submit|order|score|rank|ranking)\b", low))

    def test_generated_links_and_focus_anchors_resolve(self):
        for page, h in self.html.items():
            ids = set(re.findall(r'id="([^"]+)"', h))
            paths = set(re.findall(r'data-path="([^"]+)"', h))
            for href in re.findall(r'href="([^"]+)"', h):
                if "+" in href:
                    continue
                if href == "#":
                    continue
                if href.startswith("#"):
                    frag = href[1:]
                    if frag.startswith("path="):
                        self.assertIn(frag.split("=", 1)[1], paths, (page, href))
                    elif frag:
                        self.assertIn(frag, ids, (page, href))
                    continue
                if href.startswith("http"):
                    continue
                fname, _, frag = href.partition("#")
                self.assertIn(fname, self.paths, (page, href))
                if frag.startswith("focus="):
                    target_paths = set(re.findall(r'data-path="([^"]+)"', self.html[fname]))
                    self.assertIn(frag.split("=", 1)[1], target_paths, (page, href))

    # --- ticker/security mapping only AFTER value-chain/winner -------------
    def test_ticker_mapping_carries_after_value_chain_qualifier(self):
        # The qualifier appears at the value-chain zoom level inside the one universe
        # page -- never as the entry point.
        u = self.html["universe.html"].lower()
        self.assertIn("derived after value-chain", u)
        self.assertIn("never the entry point", u)

    # --- data gaps / conflicts / authority badges render ------------------
    def test_data_gaps_and_conflicts_and_authority_badges(self):
        dq = self.html["data_quality.html"]
        self.assertIn("Default demo mode contains no real ticker candidate", dq)
        self.assertIn("No active-run company", dq)
        self.assertIn("no conflicts", dq)
        self.assertIn("demo terrain only: no active run candidate provenance", dq)
        # source-authority hierarchy + counts
        self.assertIn("SEC EDGAR", dq)
        self.assertIn("FMP", dq)
        self.assertIn("yfinance fallback", dq)
        # gaps + missing-data visible at the zoom levels inside the one universe page
        u = self.html["universe.html"]
        self.assertIn("Data gaps", u)
        self.assertIn("Missing", u)
        self.assertIn("demo terrain — no live sources", u)

    # --- cockpit page via the ACCEPTED renderer ---------------------------
    def test_cockpit_page_defaults_to_neutral_empty_state(self):
        c = self.html["cockpit.html"]
        self.assertIn("Company Cockpit", c)
        self.assertIn("No company selected.", c)
        self.assertIn("Select a Planet / Company", c)
        self.assertNotIn("IREN", c)
        self.assertNotIn("<!-- BEGIN-SECTION:", c)
        for token in _STRIP_TOKENS:
            self.assertIn(token, c)

    def test_production_tabs_are_visible(self):
        for page, h in self.html.items():
            if page == "cockpit.html":
                continue
            for label in ("Universe Canvas", "CosmosIQ Capital", "Capital Candidates",
                          "Company Cockpit", "Trust &amp; Data Quality", "Reality Mesh",
                          "Portfolio Intelligence"):
                self.assertIn(label, h, "{0} missing tab {1}".format(page, label))

    def test_capital_candidates_surface(self):
        cc = self.html["capital_candidates.html"]
        self.assertIn("<h1>Capital Candidates</h1>", cc)
        self.assertIn("No Capital Candidates are available for this run.", cc)
        for term in ("Investment Thesis", "Forward Scenario", "Portfolio Fit",
                     "Sizing Guardrails", "Manual Execution Preview"):
            self.assertIn(term, cc)
        self.assertNotIn("<tr><td>", cc)

    def test_capital_candidates_has_no_trade_controls_or_hidden_fields(self):
        low = self.html["capital_candidates.html"].lower()
        for bad in ("<button", "<form", "onclick", "type=\"submit\"",
                    "strong buy", "hold recommendation", "submit order",
                    "place order", "trade now", "auto trade", "auto rebalance",
                    "broker submit", "alpha score", "ranked picks"):
            self.assertNotIn(bad, low)
        self.assertIsNone(re.search(r"\b(buy|sell|submit|order|score|rank|ranking)\b", low))

    def test_candidate_rows_link_to_company_cockpit(self):
        cc = self.html["capital_candidates.html"]
        self.assertIn('href="cockpit.html"', cc)
        self.assertIn("No Capital Candidates are available for this run.", cc)
        self.assertIn('href="capital_candidates.html"', self.html["dashboard.html"])

    def test_capital_candidates_empty_state_renders(self):
        empty = CIODashboardView(
            banner="empty", buckets=(), total_candidates=0, real_candidate_count=0)
        html = render_capital_candidates(empty)
        self.assertIn("No Capital Candidates are available for this run.", html)
        self.assertIn("Run a pulse, add watchlist tickers, or enable the required source adapters.", html)

    def test_trust_and_reality_mesh_show_candidate_evidence_and_agents(self):
        dq = self.html["data_quality.html"]
        mesh = self.html["reality_mesh.html"]
        self.assertIn("Capital Candidate Evidence", dq)
        self.assertIn("No Capital Candidates are available for this run.", dq)
        self.assertIn("Agent Registry", mesh)
        self.assertIn("Candidate Contributions", mesh)
        self.assertIn("Evidence Ingestion", mesh)

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
        # Navigation JS is externalized so generated HTML does not carry a large inline blob.
        self.assertIn('src="assets/universe_canvas.js"', self.all_html)
        scripts = re.findall(r"<script>(.*?)</script>", self.all_html, re.DOTALL)
        self.assertEqual(scripts, [])
        with open(self.paths["assets/universe_canvas.js"], encoding="utf-8") as fh:
            scripts = [fh.read()]
        for s in scripts:
            low = s.lower()
            for banned in ("fetch(", "xmlhttprequest", "websocket", "eventsource",
                           "importscripts", ".submit(", "sendbeacon", "new image("):
                self.assertNotIn(banned, low, "script contains banned call: {0}".format(banned))

    def test_public_generated_output_has_clean_asset_boundaries(self):
        self.assertIn('href="assets/cosmosiq.css"', self.html["universe.html"])
        self.assertIn('href="assets/universe_canvas.css"', self.html["universe.html"])
        self.assertIn('src="assets/universe_canvas.js"', self.html["universe.html"])
        public = self.all_html
        for asset in ("assets/cosmosiq.css", "assets/universe_canvas.css",
                      "assets/universe_canvas.js", "assets/universe.css",
                      "assets/universe.js"):
            with open(self.paths[asset], encoding="utf-8") as fh:
                public += "\n" + fh.read()
        for old in ("EIOS layer map", "010A", "010B", "010C", "Sudarshan"):
            self.assertNotIn(old, public)

    # --- multiple galaxies, no real ticker in default demo ----------------
    def test_multiple_galaxies_no_real_default_candidate(self):
        self.assertGreaterEqual(len(self.view.clusters), 5)
        self.assertNotEqual(self.view.clusters[0].theme_name, "AI Infrastructure")
        real = [p for t in self.view.themes for p in t.planets if p.is_real]
        self.assertEqual(real, [])
        self.assertEqual(self.view.dashboard.total_candidates, 0)

    def test_default_product_ui_has_no_fixture_ticker_leakage(self):
        public = self.all_html
        for bad in ("IREN", "Iris Energy", "IREN Limited", "AAOI", "AMBA", "OUST",
                    "NVDA", "GRIDX", "LOADX", "FUELX", "SMRX", "COOLX", "BLDX",
                    "OPTX", "PKGX", "HBMX", "MEGAX", "SMALLX", "NEOX", "HOSTX",
                    "EDGEX", "ACTX", "ORBX"):
            self.assertNotIn(bad, public)
        self.assertIn("Synthetic Neocloud Operator", public)
        self.assertIn("Demo Neocloud Operator", public)

    def test_explicit_evidence_fixture_can_render_historical_iren_slice(self):
        tmp = tempfile.mkdtemp(prefix="uui_evidence_")
        paths = build_universe_app(tmp, mode="evidence_ingested_fixture")
        with open(paths["universe.html"], encoding="utf-8") as fh:
            universe = fh.read()
        with open(paths["capital_candidates.html"], encoding="utf-8") as fh:
            candidates = fh.read()
        with open(paths["cockpit.html"], encoding="utf-8") as fh:
            cockpit = fh.read()
        self.assertIn("IREN", universe)
        self.assertIn("IREN", candidates)
        self.assertIn("<!-- BEGIN-SECTION:", cockpit)
        self.assertIn("evidence_ingested_fixture", universe)

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


class ZoomableUniverseTests(unittest.TestCase):
    """The Economic Universe is ONE two-pane zoomable page (010A-R)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="universe_zoom_")
        cls.paths = _build(cls._tmp)
        with open(cls.paths["universe.html"], encoding="utf-8") as fh:
            cls.u = fh.read()
        with open(cls.paths["dashboard.html"], encoding="utf-8") as fh:
            cls.d = fh.read()
        cls.slice = load_iren_slice()
        cls.view = build_economic_universe_view(cls.slice)

    # --- two distinct panes in ONE page -----------------------------------
    def test_two_pane_regions_present(self):
        self.assertIn('id="top-canvas"', self.u)      # dominant interactive canvas
        self.assertIn('id="intel-pane"', self.u)      # dynamic bottom intelligence pane
        self.assertIn('id="intel-body"', self.u)

    # --- all zoom levels embedded as level-panels in the ONE page ---------
    def test_all_zoom_levels_present_in_one_page(self):
        for level in range(0, 6):
            self.assertIn('data-level="{0}"'.format(level), self.u,
                          "missing zoom level {0}".format(level))
        for kind in ("galaxy", "theme", "value_chain", "star", "planet", "moon"):
            self.assertIn('data-kind="{0}"'.format(kind), self.u,
                          "missing cosmic-object kind {0}".format(kind))

    # --- breadcrumb + zoom-in objects + zoom-out/back control -------------
    def test_breadcrumb_and_zoom_controls_render(self):
        self.assertIn('id="breadcrumb"', self.u)
        self.assertIn("data-crumb=", self.u)               # per-level breadcrumb labels
        self.assertIn('id="zoom-back"', self.u)            # zoom-out / back control
        self.assertIn("data-target-path=", self.u)         # zoom-in affordance on objects
        self.assertIn("data-parent=", self.u)              # back walks the parent chain

    # --- each object type has a bottom-pane intelligence template ---------
    def test_each_object_type_has_intel_template(self):
        # The intel templates carry per-type headings.
        for marker in ("Universe Canvas — Intelligence Briefing", "Mega Theme / Galaxy",
                       "Theme / Milky Way", "Value Chain / Solar System",
                       "Bottleneck / Star", "Stock / Planet",
                       "Supplier or Customer / Moon"):
            self.assertIn(marker, self.u, "missing intel template: {0}".format(marker))
        self.assertIn('class="intel-template"', self.u)

    def _top_canvas(self):
        """The top-canvas region only (excludes the bottom intelligence pane)."""
        return self.u.split('id="top-canvas"')[1].split('id="intel-pane"')[0]

    # --- the TOP CANVAS shows ONLY luminous bodies (no tables/captions/intel) --
    def test_top_canvas_shows_only_bodies_no_text_blocks(self):
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            css = fh.read()
        # intel templates are hidden data carriers, never shown
        self.assertIn(".intel-template{display:none !important}", css)
        # no visible captions / tables / headings / diagrams inside the canvas
        top = self._top_canvas()
        self.assertNotIn('class="scene-caption"', self.u)
        self.assertNotIn("<table", top)
        self.assertNotIn("<h2", top)              # no leaked level captions/intel headings
        # (the floating preview legitimately carries an <h3 class="fp-title">; the
        #  economic scene itself still carries no leaked intel tables/diagrams)
        self.assertNotIn("flow-diagram", top)
        self.assertNotIn("gap-box", top)
        self.assertNotIn("intel-template", top)   # intel lives in the hidden store
        # scene-bodies carry no tables either
        for block in re.findall(r'<div class="scene-bodies">.*?</section>', top, re.DOTALL):
            self.assertNotIn("<table", block)
        # but bodies + their name labels ARE present
        self.assertIn('class="cosmic-object', top)
        self.assertIn('class="body-label"', top)

    # --- bottom-pane wiring: object/level -> #intel-body via data-intel + store -
    def test_bottom_pane_wiring_is_correct(self):
        with open(self.paths["assets/universe.js"], encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("getElementById('intel-body')", js)
        self.assertIn("getAttribute('data-intel')", js)
        # the buggy stale ids must be gone
        for stale in ("detail-body", "level-detail", "object-detail"):
            self.assertNotIn(stale, js)
        # a hidden intel store exists; a synthetic planet points at its blob, and
        # that blob holds the company table -> clicking fills the bottom pane.
        self.assertIn('class="intel-store"', self.u)
        m = re.search(r'data-kind="planet"[^>]*data-path="[^"]*pl:synthetic-neocloud-operator"[^>]*'
                      r'data-intel="([^"]+)"', self.u)
        self.assertIsNotNone(m, "synthetic planet body has no data-intel hook")
        blob_id = m.group(1)
        blob = re.search(
            r'<div class="intel-template" id="{0}">(.*?)</div>\s*'
            r'(?:<div class="intel-template"|</div>\s*</div>\s*</body)'.format(re.escape(blob_id)),
            self.u, re.DOTALL)
        self.assertIsNotNone(blob, "no intel blob for synthetic planet")
        self.assertIn("Demo Neocloud Operator", blob.group(1))
        self.assertIn("<table", blob.group(1))    # the company detail table

    # --- continuous ZOOM + PAN on the canvas (Google-Earth feel) ----------
    def test_zoom_and_pan_controls_present(self):
        # a transform layer wraps the bodies at every level
        self.assertIn('<div class="scene-bodies"><div class="scene-transform">', self.u)
        # +/- and reset controls (anchors, never <button>)
        for cid in ("zoom-in", "zoom-out", "zoom-reset", "zoom-back"):
            self.assertIn('id="{0}"'.format(cid), self.u)
        with open(self.paths["assets/universe.js"], encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("'wheel'", js)          # wheel zoom
        self.assertIn("scale", js)            # scale transform
        self.assertIn("'pointermove'", js)    # drag to pan
        self.assertIn("view.tx", js)          # translate/pan state
        self.assertIn("scene-transform", js)  # applied to the active level

    # --- bottom pane has diagram/table sections for value-chain + star ----
    def test_bottom_pane_has_diagrams(self):
        self.assertIn("flow-diagram", self.u)          # value-chain flow diagram
        self.assertIn("bottleneck-diagram", self.u)    # bottleneck explanation diagram

    # --- bottom pane surfaces data gaps AND source-authority badges -------
    def test_bottom_pane_shows_gaps_and_authority(self):
        self.assertIn("demo terrain — no live sources", self.u)
        self.assertIn("Data gaps", self.u)             # gaps never hidden

    # --- default dashboard has no candidate locate links ------------------
    def test_dashboard_has_no_default_candidate_locate_links(self):
        hrefs = re.findall(r'href="(universe\.html#focus=[^"]+)"', self.d)
        self.assertEqual(hrefs, [])
        self.assertIn("0 companies are surfaced", self.d)

    # --- the planet template does not expose a default cockpit link --------
    def test_planet_template_has_no_default_cockpit_link(self):
        self.assertIn("Company Cockpit appears only for active-run Capital Candidates", self.u)
        self.assertNotIn('data-cockpit="cockpit.html"', self.u)

    # --- the top canvas is an immersive CSS deep-space scene (no star-div flood) -
    def test_top_canvas_is_a_css_space_scene(self):
        # the hundreds of star divs are GONE; the backdrop is telescopic CSS layers
        self.assertLess(self.u.count('class="star '), 10)
        self.assertIn('class="sky-bg"', self.u)       # parallax deep-field wrapper
        self.assertIn('class="space-glow"', self.u)   # galactic glow (CSS)
        # three tiled star layers (far/mid/near) for depth + a dust lane
        self.assertIn('class="star-far"', self.u)
        self.assertIn('class="star-near"', self.u)
        self.assertIn('class="dust-lane"', self.u)
        self.assertIn('class="nebula', self.u)        # nebula wash
        self.assertIn('class="vignette"', self.u)     # vignette
        self.assertNotIn("object-grid", self.u)       # not a card grid
        self.assertIn('class="scene-bodies"', self.u)

    # --- no visible connector graph in the immersive canvas ----------------
    def test_no_visible_connector_lines_in_canvas(self):
        top = self._top_canvas()
        for cls in ("rel-lines", "orbit-lines", "flow-lines"):
            self.assertNotIn(cls, top)
        self.assertNotIn("<line ", top)
        self.assertNotIn("<polygon", top)

    # --- a compact collapsible LEGEND card exists -------------------------
    def test_legend_card_present(self):
        self.assertIn('class="legend"', self.u)
        self.assertIn('data-collapse-target="legend-body"', self.u)
        low = self.u.lower()
        for key in ("magnitude", "heat", "exposure", "catalyst", "evidence"):
            self.assertIn(key, low, "legend missing mapping term {0}".format(key))

    # --- polished states: hover preview chip + persistent selected state ---
    def test_object_states_present(self):
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn('class="body-tip"', self.u)          # hover preview chip
        self.assertIn(".cosmic-object:hover .body-tip", css)
        self.assertIn(".cosmic-object.selected", css)      # persistent selected ring
        with open(self.paths["assets/universe.js"], encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("classList.add('selected')", js)     # JS applies selection

    # --- bottom pane is an executive BRIEFING (sectioned cards) -----------
    def test_bottom_pane_is_executive_briefing(self):
        self.assertIn('class="brief-header"', self.u)
        self.assertIn('class="brief-card', self.u)
        self.assertIn("Executive summary", self.u)
        self.assertIn("Why now", self.u)
        self.assertIn("Provenance", self.u)                # planet briefing provenance
        self.assertIn("cockpit-cta", self.u)               # prominent Open Cockpit CTA
        self.assertIn('class="timeline"', self.u)          # catalyst timeline chips

    # === 010A-S2: seven UX cleanups ======================================

    # 1. each zoom level is visually differentiated by a level class
    def test_levels_visually_differentiated(self):
        for cls in ("level-universe", "level-galaxy", "level-theme",
                    "level-valuechain", "level-star", "level-planet"):
            self.assertIn(cls, self.u, "missing level class {0}".format(cls))
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".scene-layer::before", css)         # per-level accent rail

    # 2. Mega Theme Galaxies use the infinity / galaxy-band visual; Themes are clouds
    def test_mega_theme_galaxy_is_milkyway_band_and_theme_is_cloud(self):
        self.assertRegex(
            self.u,
            r'class="cosmic-object k-galaxy body-milkyway[^"]*"[^>]*data-kind="galaxy"',
            "Mega Theme / Galaxy must use the infinity-like galaxy-band body")
        self.assertRegex(
            self.u,
            r'class="cosmic-object k-theme body-themecloud[^"]*"[^>]*data-kind="theme"',
            "Theme / Milky Way must use a distinct concentrated cloud body")
        self.assertIn('data-kind="theme"', self.u)
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".body-milkyway .body", css)
        self.assertIn(".body-themecloud .body", css)
        self.assertIn(".glow-1 .image-body,.glow-2 .image-body,.glow-3 .image-body", css)
        self.assertIn("box-shadow:none!important;outline:none!important", css)

    def test_celestial_images_are_type_mapped(self):
        expected = (
            ("galaxy", "mega-theme-galaxy.svg"),
            ("theme", "theme-milky-way.svg"),
            ("value_chain", "value-chain-solar-system.svg"),
            ("star", "bottleneck-star.svg"),
            ("planet", "stock-planet.svg"),
            ("moon", "supplier-customer-moon.svg"),
        )
        for kind, asset in expected:
            pattern = (
                r'data-kind="{kind}"[^>]*>.*?'
                r'<img class="celestial-img" src="assets/celestial/{asset}"'
            ).format(kind=re.escape(kind), asset=re.escape(asset))
            self.assertRegex(self.u, pattern, "wrong celestial image for {0}".format(kind))
            self.assertIn("assets/celestial/{0}".format(asset), self.paths)
            self.assertTrue(os.path.exists(self.paths["assets/celestial/{0}".format(asset)]))
        self.assertRegex(
            self.u,
            r'k-galaxy body-milkyway[^"]*"[^>]*data-kind="galaxy"[^>]*>.*?'
            r'class="body image-body" style="width:[2-9][0-9]{2}px;height:[0-9]{2,3}px"'
            r' data-visual-size="[0-9]+"',
            "Mega Theme Galaxies must render as wide infinity images")

    # 3. value-chain level = local system without connector lines
    def test_value_chain_local_system_without_flow_lines(self):
        self.assertNotIn("flow-lines", self.u)
        # bodies still lay left->right as a local system (multiple distinct left% positions)
        lefts = re.findall(r'style="left:([0-9.]+)%;top:66\.\d+%"', self.u) \
            + re.findall(r'style="left:([0-9.]+)%;top:69\.\d+%"', self.u) \
            + re.findall(r'style="left:([0-9.]+)%;top:62\.\d+%"', self.u)
        self.assertGreaterEqual(len(set(lefts)), 3, "value-chain not laid out as a flow")

    # 4. bottleneck star is central + dominant, losers separated
    def test_bottleneck_central_and_dominant(self):
        self.assertIn("bottleneck-central", self.u)
        self.assertIn("scarce node", self.u)               # dominance marker label
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".bottleneck-central .body", css)    # stronger glow/rays
        # a red-shadowed (loser) planet is pushed to the separated right edge (85%)
        self.assertIn('redshadow', self.u)
        self.assertIn('style="left:85.00%', self.u)

    # 5. candidate planet hover summary carries the required existing fields
    def test_planet_hover_summary_fields(self):
        i = self.u.find("Demo Neocloud Operator")
        self.assertGreater(i, 0, "synthetic planet preview chip not found")
        seg = self.u[i:i + 1600]
        for field in ("mega theme / galaxy", "value-chain role", "candidate bucket",
                      "top reason", "top risk", "market cap"):
            self.assertIn(field, seg, "planet hover missing {0}".format(field))
        self.assertIn("AI Infrastructure", seg)

    # 6. every briefing OPENS with the five-line executive header
    def test_exec_header_five_frames(self):
        self.assertIn('class="exec-header"', self.u)
        for frame in ("What this is", "Why it matters", "Where the alpha could be",
                      "What could go wrong", "What to inspect next"):
            self.assertIn(frame, self.u, "missing exec frame {0}".format(frame))
        # the exec header precedes the diagrams/tables in a briefing blob
        blob = self.u.split('id="intel-universe">')[1].split("</div>")[0] \
            if 'id="intel-universe">' in self.u else self.u
        self.assertIn("exec-header", self.u.split('id="intel-universe">')[1][:400])

    # 7. legend explains all EIGHT visual channels
    def test_legend_lists_eight_channels(self):
        low = self.u.lower()
        for term in ("economic magnitude", "signal convergence", "status / risk",
                     "economic / exposure neighborhood", "catalyst / crowding",
                     "red-team / dilution / insolvency", "evidence quality",
                     "missing data"):
            self.assertIn(term, low, "legend missing channel: {0}".format(term))
        self.assertIn("celestial metaphor only", low)

    # --- design system + FULL-SCREEN layout -------------------------------
    def test_design_system_and_layout(self):
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("backdrop-filter:blur", css)         # glassmorphism
        self.assertIn("--mono:", css)                      # monospace stack for numbers
        self.assertIn(".micro{", css)                      # uppercase micro-labels
        # 010A-SKY: the page SCROLLS (no overflow lock); the HERO is the first screen
        self.assertIn("body.sky{min-height:100vh", css)
        self.assertNotIn("body.fullscreen{height:100vh", css)  # split-pane lock removed
        # the universe HERO is sized to the first viewport minus the header chrome ...
        self.assertIn(".universe-hero{position:relative", css)
        self.assertIn("height:calc(100vh - 92px)", css)
        self.assertIn(".universe-hero .top-canvas .viewport{height:100%}", css)
        # ... and the intelligence pane sits BELOW the fold (full width, natural flow)
        self.assertIn(".intel-section{", css)

    # --- the universe page is a full-screen telescope HERO + below-fold pane -
    def test_universe_page_is_full_screen(self):
        # 010A-SKY: scrollable page (no overflow lock), hero-first, intel below
        self.assertIn('<body class="sky">', self.u)
        self.assertNotIn('<body class="fullscreen">', self.u)
        self.assertIn('class="universe-hero"', self.u)     # full-viewport hero canvas
        self.assertIn('universe-app', self.u)              # full-width 100vw shell
        # the intelligence pane is BELOW the hero (its own section), not a split pane
        self.assertIn('class="intel-pane intel-section"', self.u)
        hero = self.u.split('class="universe-hero"')[1].split('id="intel-pane"')[0]
        self.assertIn('id="top-canvas"', hero)             # the canvas is inside the hero
        self.assertNotIn('class="wrap"', self.u)           # no 1200px document width
        self.assertNotIn("<h1>Economic Universe</h1>", self.u)  # big intro trimmed
        self.assertNotIn('class="canvas-note"', self.u)    # overlay note removed
        # a floating selected-object preview lives inside the universe hero, but is
        # HIDDEN by default -- it only appears once the user clicks an object
        self.assertIn('class="floating-preview dismissed"', self.u)
        self.assertIn('id="floating-preview"', self.u)
        self.assertIn('id="fp-details"', self.u)           # "View details below" target
        self.assertIn('href="#intel-pane"', self.u)
        # status strip + 3-item command bar are still present above the canvas
        self.assertIn('class="status-strip"', self.u)
        self.assertIn('class="command-bar"', self.u)
        # dashboard / data-quality stay document-style (their own width + scroll)
        with open(self.paths["dashboard.html"], encoding="utf-8") as fh:
            dash = fh.read()
        self.assertIn('class="wrap"', dash)
        self.assertNotIn('<body class="sky">', dash)

    def test_objects_are_positioned_luminous_bodies(self):
        for cls in ("body-milkyway", "body-themecloud", "body-planet",
                    "body-star", "body-nebula", "body-moon"):
            self.assertIn(cls, self.u, "missing luminous body class {0}".format(cls))
        # bodies are absolutely positioned in space (inline left%/top%)
        self.assertIsNotNone(
            re.search(r'class="cosmic-object[^"]*" style="left:[0-9.]+%;top:[0-9.]+%"', self.u),
            "cosmic objects are not absolutely positioned in the scene")
        # the body diameter is driven by the magnitude-derived visual size
        self.assertIn('class="body image-body" style="width:', self.u)
        # positioned bodies still drive zoom + intel pane
        self.assertIn("data-target-path=", self.u)
        self.assertIn('class="intel-template"', self.u)

    def test_scene_is_deterministic(self):
        # starfield + positions come from fixed seeds, so a second build matches.
        tmp = tempfile.mkdtemp(prefix="universe_scene2_")
        paths = _build(tmp)
        with open(paths["universe.html"], encoding="utf-8") as fh:
            u2 = fh.read()
        self.assertEqual(self.u, u2)

    # --- deep-link + hierarchy powered by navigation-only JS --------------
    def test_zoom_js_is_navigation_only(self):
        with open(self.paths["assets/universe.js"], encoding="utf-8") as fh:
            js = fh.read().lower()
        self.assertIn("addeventlistener", js)
        self.assertIn("focus", js)                      # deep-link focus handler
        for banned in ("fetch(", "xmlhttprequest", "websocket", ".submit(",
                       "document.write", "eval("):
            self.assertNotIn(banned, js, "zoom JS contains banned call: {0}".format(banned))


class VisualSizeEncodingTests(unittest.TestCase):
    """Size = economic magnitude via a bounded log scale, DECOUPLED from ranking."""

    @classmethod
    def setUpClass(cls):
        cls.slice = load_iren_slice()
        cls.view = build_economic_universe_view(cls.slice)
        cls.planets = {p.ticker: p for t in cls.view.themes for p in t.planets}
        cls.clusters = {c.theme_name: c for c in cls.view.clusters}

    def _bucket_of(self, ticker):
        p = self.planets[ticker]
        return [b.name for b in self.view.dashboard.buckets
                if any(c.ticker == p.ticker for c in b.cards)]

    # --- planet size derived from market_cap, monotonic & bounded ---------
    def test_planet_size_from_market_cap_monotonic(self):
        small = visual_size(9.0e8, "planet")
        mid = visual_size(1.0e11, "planet")
        mega = visual_size(3.4e12, "planet")  # NVIDIA-scale
        self.assertLess(small, mid)
        self.assertLess(mid, mega)
        self.assertGreaterEqual(small, MIN_PX)
        self.assertLessEqual(mega, MAX_PX)
        self.assertGreater(
            self.planets["Synthetic Accelerator Vendor"].visual_size_px,
            self.planets["Synthetic Scarce Component Supplier"].visual_size_px)

    # --- galaxy size derived from theme_tam -------------------------------
    def test_galaxy_size_from_theme_tam(self):
        big = self.clusters["Data Centers"]        # theme_tam 1.2e12
        small = self.clusters["Optics & Networking"]  # theme_tam 2.5e11
        self.assertGreater(big.visual_size_px, small.visual_size_px)
        self.assertEqual(big.visual_size_px, visual_size(big.theme_tam, "galaxy"))

    # --- missing magnitude -> neutral size + data-gap marker + dashed -----
    def test_missing_magnitude_uses_default_and_gap_marker(self):
        actuator = self.planets["Synthetic Actuator Supplier"]  # market_cap None
        self.assertTrue(actuator.magnitude_missing)
        self.assertEqual(actuator.visual_size_px, DEFAULT_PX)
        phai = self.clusters["Physical AI"]          # theme_tam None
        self.assertTrue(phai.magnitude_missing)
        self.assertEqual(phai.visual_size_px, DEFAULT_PX)
        # the dashed outline + gap marker are rendered on the page
        tmp = tempfile.mkdtemp(prefix="uui_gap_")
        paths = _build(tmp)
        with open(paths["universe.html"], encoding="utf-8") as fh:
            uni = fh.read()
        self.assertIn("magnitude missing", uni.lower())
        self.assertIn("dashed", uni.lower())

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
        mega = self.planets["Synthetic Accelerator Vendor"]    # large size, weak status
        small = self.planets["Synthetic Scarce Component Supplier"]  # small size, strong status
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
        self.assertEqual(self.view.dashboard.total_candidates, 0)
        self.assertEqual(self._bucket_of("Synthetic Accelerator Vendor"), [])

    # --- raw magnitude appears in the card details ------------------------
    def test_raw_magnitude_visible_in_details(self):
        tmp = tempfile.mkdtemp(prefix="uui_raw_")
        paths = _build(tmp)
        with open(paths["dashboard.html"], encoding="utf-8") as fh:
            dash = fh.read()
        with open(paths["universe.html"], encoding="utf-8") as fh:
            uni = fh.read()
        self.assertIn("market cap", uni)              # raw label present
        self.assertIn("$3.40T", uni)                  # synthetic accelerator raw market cap
        self.assertIn("mega-theme TAM (DEMO)", uni)   # galaxy raw TAM label


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


class UniverseCenterFixTests(unittest.TestCase):
    """010A-FIX: no false 'centre of the universe'; no visible graph lines; full-width shell;
    reliable bottom pane; pan/zoom/fit/locate."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="universe_fix_")
        cls.paths = _build(cls._tmp)
        with open(cls.paths["universe.html"], encoding="utf-8") as fh:
            cls.u = fh.read()
        with open(cls.paths["dashboard.html"], encoding="utf-8") as fh:
            cls.d = fh.read()
        with open(os.path.join(cls._tmp, "assets", "universe.css"), encoding="utf-8") as fh:
            cls.css = fh.read()
        with open(os.path.join(cls._tmp, "assets", "universe.js"), encoding="utf-8") as fh:
            cls.js = fh.read()
        with open(os.path.join(cls._tmp, "assets", "universe.js"), encoding="utf-8") as fh:
            cls.js = fh.read()
        cls.view = build_economic_universe_view(load_iren_slice())

    def _l0(self):
        m = re.search(r'data-level="0"[^>]*>(.*?)</section>', self.u, re.S)
        self.assertIsNotNone(m, "no L0 universe panel")
        return m.group(1)

    def test_universe_level_has_no_hub_and_spoke(self):
        l0 = self._l0()
        # no visible connector graph at the Universe level
        self.assertNotIn('class="orbit-lines"', l0)
        self.assertNotIn('class="rel-lines"', l0)
        self.assertNotIn("<line ", l0)
        self.assertNotIn('x2="50.00" y2="47.00"', l0)

    def test_relationships_move_to_briefing_not_canvas_lines(self):
        l0 = self._l0()
        self.assertEqual(l0.count("<line "), 0)
        self.assertIn("Related domains", self.u)
        self.assertIn("AI Infrastructure depends on / relates to Power &amp; Grid", self.u)
        self.assertNotIn("Robotics ↔ Nuclear", self.u)
        self.assertNotIn("Nuclear &amp; Energy ↔ Robotics", self.u)

    def test_deeper_levels_also_have_no_connector_lines(self):
        for cls in ("orbit-lines", "rel-lines", "flow-lines"):
            self.assertNotIn(cls, self.u)

    def test_celestial_objects_are_clickable_and_focusable(self):
        for kind in ("galaxy", "theme", "value_chain", "star", "planet", "moon"):
            self.assertRegex(
                self.u,
                r'role="button" tabindex="0" aria-label="[^"]*" '
                r'data-kind="{0}"'.format(kind),
                "missing focusable clickable object kind {0}".format(kind))
        self.assertIn("data-target-path=", self.u)
        self.assertIn("data-intel=", self.u)
        self.assertIn("addEventListener('keydown'", self.js)

    def test_full_width_universe_app_shell(self):
        self.assertIn("universe-app", self.u)
        self.assertNotIn('class="wrap"', self.u)                 # not a 1200px document
        self.assertIn(".universe-app{width:100vw;max-width:none}", self.css)
        self.assertIn('class="wrap"', self.d)                    # dashboard stays document-style

    def test_pan_zoom_fit_locate_controls(self):
        for cid in ('id="zoom-in"', 'id="zoom-out"', 'id="zoom-reset"',
                    'id="zoom-fit"', 'id="zoom-locate"'):
            self.assertIn(cid, self.u)
        self.assertIn("fitToAll", self.js)
        self.assertIn("locateSelected", self.js)
        self.assertIn("wheel", self.js)

    def test_every_data_intel_resolves_to_a_template(self):
        ids = set(re.findall(r'id="(intel-[^"]+)"', self.u))
        refs = set(re.findall(r'data-intel="(intel-[^"]+)"', self.u))
        self.assertTrue(refs, "no data-intel hooks found")
        self.assertEqual(refs - ids, set(),
                         "unresolved data-intel: {0}".format(sorted(refs - ids)))

    def test_bottom_pane_reliability(self):
        # visible fallback instead of a blank/silent pane
        self.assertIn("Missing intelligence template:", self.js)
        # the clicked object's OWN intel wins -- set AFTER any level change
        self.assertIsNotNone(
            re.search(r"showLevel\(tp\);.*?setIntel\(myIntel\);", self.js, re.S),
            "object click must set its own intel after showLevel (no level overwrite)")


class TelescopeSkyTests(unittest.TestCase):
    """010A-SKY: full-screen telescope HERO first; intel pane below the fold; a
    floating selected-object preview inside the universe; page scrolls naturally."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="universe_sky_")
        cls.paths = _build(cls._tmp)
        with open(cls.paths["universe.html"], encoding="utf-8") as fh:
            cls.u = fh.read()
        with open(os.path.join(cls._tmp, "assets", "universe.css"), encoding="utf-8") as fh:
            cls.css = fh.read()
        with open(os.path.join(cls._tmp, "assets", "universe.js"), encoding="utf-8") as fh:
            cls.js = fh.read()

    def test_hero_is_the_first_viewport(self):
        self.assertIn('class="universe-hero"', self.u)
        self.assertIn(".universe-hero{position:relative", self.css)
        self.assertIn("height:calc(100vh - 92px)", self.css)   # viewport-based, dominant
        self.assertIn("min-height:560px", self.css)            # responsive fallback
        self.assertIn(".universe-hero .top-canvas .viewport{height:100%}", self.css)

    def test_page_scrolls_no_overflow_lock(self):
        self.assertIn("body.sky{min-height:100vh", self.css)
        # the old split-pane 100vh/overflow:hidden lock is gone
        self.assertNotIn("body.fullscreen{height:100vh;max-height:100vh;overflow:hidden",
                         self.css)

    def test_intel_pane_is_below_the_hero(self):
        # order in the document: hero BEFORE the intelligence section
        self.assertLess(self.u.index('class="universe-hero"'),
                        self.u.index('id="intel-pane"'))
        self.assertIn('class="intel-pane intel-section"', self.u)
        # the intel pane is NOT inside the hero (its own below-fold section)
        hero = self.u.split('class="universe-hero"')[1].split("</section>")[0]
        self.assertNotIn('id="intel-pane"', hero)

    def test_floating_preview_present_and_wired(self):
        for hook in ('id="floating-preview"', 'id="fp-title"', 'id="fp-type"',
                     'id="fp-body"', 'id="fp-zoom"', 'id="fp-details"', 'id="fp-close"'):
            self.assertIn(hook, self.u)
        # JS defines updatePreview and calls it on object click
        self.assertIn("function updatePreview(", self.js)
        self.assertIn("updatePreview(this)", self.js)
        # "View details below" scrolls to the below-fold pane
        self.assertIn('href="#intel-pane"', self.u)
        self.assertIn("scrollIntoView", self.js)

    def test_object_click_updates_both_preview_and_below_fold_pane(self):
        # the same click updates the floating preview AND #intel-body (via setIntel)
        m = re.search(r"updatePreview\(this\);.*?zoomToObject\(this,2\.25\);.*?setIntel\(myIntel\);",
                      self.js, re.S)
        self.assertIsNotNone(m, "object click must zoom selected body + update below-fold pane")

    def test_background_and_objects_pan_together_in_flat_field(self):
        # the deep-field background and plotted objects share the same flat pan/zoom,
        # so galaxies do not drift away from the universe when the user moves it.
        self.assertIn(".sky-bg", self.css)
        self.assertIn("skybg.style.transform='translate('+view.tx", self.js)
        self.assertNotIn("skybg.style.transform='none'", self.js)
        self.assertNotIn("projectGlobeObjects", self.js)
        self.assertNotIn("view.lon", self.js)
        self.assertNotIn("view.lat", self.js)
        self.assertNotIn("globeRadius", self.js)
        self.assertNotIn("viewport.style.setProperty('--globe-radius'", self.js)
        self.assertNotIn("setProperty('--globe-diameter'", self.js)
        self.assertNotIn("rearFade=clamp(0.38", self.js)
        self.assertIn("view.tx+=dx", self.js)
        self.assertIn("view.ty+=dy", self.js)
        self.assertNotIn("pointerEvents=back?'none'", self.js)
        self.assertNotIn(".viewport::before", self.css)
        self.assertNotIn("--globe-diameter", self.css)
        self.assertNotIn("--globe-shade", self.css)
        self.assertNotIn("--globe-radius", self.css)
        self.assertNotIn("clip-path:circle", self.css)
        self.assertIn(".universe-hero .vignette{box-shadow:inset", self.css)
        self.assertNotIn("rgba(43,116,210,.2)", self.css)
        self.assertNotRegex(self.css, r"\.sky-bg\{[^}]*background:")
        self.assertIn(".scene-layer{position:absolute;inset:0;z-index:8", self.css)
        self.assertNotIn(".viewport .scene-transform{width:100%!important", self.css)
        self.assertIn(".level-universe .scene-transform{width:172%;height:138%;left:-36%;top:-18%}", self.css)
        self.assertIn("linear-gradient(180deg,#050713,#010208 80%)", self.css)
        self.assertNotIn(".viewport{background:#000}", self.css)
        self.assertNotIn(".sky-bg{display:none}", self.css)


class TelescopeVisualAssetTests(unittest.TestCase):
    """010A-SKY-VISUAL: a LOCAL, deterministic deep-space asset upgrades the sky;
    the accepted SKY layout + semantic lines + no-centre are all preserved."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="universe_visual_")
        cls.paths = _build(cls._tmp)
        with open(cls.paths["universe.html"], encoding="utf-8") as fh:
            cls.u = fh.read()
        cls.svg_path = os.path.join(cls._tmp, "assets", "deep_space_background.svg")
        with open(cls.svg_path, encoding="utf-8") as fh:
            cls.svg = fh.read()
        with open(os.path.join(cls._tmp, "assets", "universe.css"), encoding="utf-8") as fh:
            cls.css = fh.read()
        with open(os.path.join(cls._tmp, "assets", "universe.js"), encoding="utf-8") as fh:
            cls.js = fh.read()

    def test_local_deep_space_asset_written_and_referenced(self):
        self.assertIn("assets/deep_space_background.svg", self.paths)
        self.assertTrue(os.path.isfile(self.svg_path))
        self.assertIn("deep_space_background.svg", self.css)   # referenced as a bg image
        self.assertIn('class="deep-space-bg"', self.u)         # base layer in the hero

    def test_asset_is_a_rich_deterministic_svg(self):
        import xml.dom.minidom as minidom
        minidom.parseString(self.svg)                          # valid XML
        self.assertGreater(self.svg.count("<circle"), 900)     # dense star field
        self.assertIn("<ellipse", self.svg)                    # nebula clouds / dust
        self.assertIn("<path", self.svg)                       # dust lanes only
        self.assertIn("url(#nVio)", self.svg)                  # nebula gradient fills
        self.assertNotIn("url(#galaxy)", self.svg)             # no unnamed galaxy art
        self.assertNotIn('id="galaxy"', self.svg)
        self.assertNotIn('stroke="#fff2cf"', self.svg)
        self.assertNotIn('stroke="#b9a8ff"', self.svg)
        self.assertIn('filter id="soft"', self.svg)            # blur/bloom
        self.assertIn('filter id="wideSoft"', self.svg)        # broad telescope bloom
        # deterministic across builds
        other = tempfile.mkdtemp(prefix="universe_visual2_")
        p2 = _build(other)
        with open(p2["assets/deep_space_background.svg"], encoding="utf-8") as fh:
            self.assertEqual(self.svg, fh.read())

    def test_asset_is_local_only_no_network_no_runtime_gen(self):
        # no remote image / href / fetchable url (the w3 SVG namespace is not a fetch)
        remote = re.findall(r'(?:href|xlink:href|src)="https?://[^"]+"', self.svg)
        self.assertEqual(remote, [], "asset must not reference a remote resource")
        self.assertNotIn("<image", self.svg)                   # no embedded raster/remote image
        self.assertNotIn("<script", self.svg)                  # no runtime generation in the asset
        # the app pages introduce no fetchable http(s) resource either
        page_remote = re.findall(r'(?:href|src)="https?://[^"]+"', self.u)
        self.assertEqual(page_remote, [])

    def test_sky_layout_and_clean_cosmos_semantics(self):
        # SKY layout preserved (no split-pane regression)
        self.assertIn('<body class="sky">', self.u)
        self.assertIn('class="universe-hero"', self.u)
        self.assertIn('class="intel-pane intel-section"', self.u)
        self.assertLess(self.u.index('class="universe-hero"'), self.u.index('id="intel-pane"'))
        self.assertIn('id="floating-preview"', self.u)
        # no relationship-line SVGs; relationship meaning lives in the briefing
        l0 = re.search(r'data-level="0"[^>]*>(.*?)</section>', self.u, re.S).group(1)
        self.assertNotIn('class="rel-lines"', l0)
        self.assertNotIn('class="orbit-lines"', l0)
        self.assertIn("Related domains", self.u)
        # object visual encoding still exists
        for cls in ("body-milkyway", "body-themecloud", "body-star", "body-planet"):
            self.assertIn(cls, self.u)

    def test_premium_universe_canvas_interaction_hooks(self):
        for token in ("CosmosIQ", "Reality Mesh"):
            self.assertIn(token, self.u)
        for token in ("You are here", "cosmos-twinkle",
                      "focus-pulse", "prefers-reduced-motion"):
            self.assertIn(token, self.css)
        for token in ("pulseObject", "keydown", "fitToAll", "locateSelected", "zoomToObject",
                      "ArrowLeft", "ArrowRight"):
            self.assertIn(token, self.js)
        for row in ("object type", "signal state", "evidence quality",
                    "source authority", "data gaps", "risk flags"):
            self.assertIn(row, self.u)

    def test_no_affordance_or_scoring_regression(self):
        low = self.u.lower()
        for bad in ("<button", "<form", "onclick", "type=\"submit\"", "place order",
                    " buy ", " sell ", "fetch(", "master score"):
            self.assertNotIn(bad, low)


class VisualReferenceAlignmentTests(unittest.TestCase):
    """010A-SKY-VISUAL-REF: Data Quality control panel, corrected EIOS labels, executive
    dashboard cards, and a cockpit action on the floating preview."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="universe_ref_")
        cls.paths = _build(cls._tmp)
        with open(cls.paths["data_quality.html"], encoding="utf-8") as fh:
            cls.dq = fh.read()
        with open(cls.paths["dashboard.html"], encoding="utf-8") as fh:
            cls.dash = fh.read()
        with open(cls.paths["universe.html"], encoding="utf-8") as fh:
            cls.u = fh.read()

    def test_data_quality_has_source_hierarchy_pipeline(self):
        self.assertIn('class="dq-pipeline"', self.dq)
        for src in ("SEC EDGAR", "FMP", "yfinance", "manual / other"):
            self.assertIn(src, self.dq)

    def test_data_quality_has_authority_matrix(self):
        self.assertIn('class="chain matrix"', self.dq)
        for col in ("source", "authority", "coverage", "conflicts",
                    "overridden", "data gaps", "red-team"):
            self.assertIn(col, self.dq)
        self.assertIn('class="cov-bar"', self.dq)          # coverage bars

    def test_data_quality_has_quality_summary_cards(self):
        self.assertIn('class="stat-grid"', self.dq)
        self.assertIn('class="stat-card', self.dq)
        for label in ("canonical records", "convenience records", "fallback records",
                      "factual observations", "signal observations", "conflicts",
                      "data gaps", "stale / missing sources"):
            self.assertIn(label, self.dq)

    def test_corrected_eios_labels_present(self):
        self.assertIn('class="layer-map', self.dq)
        for label in ("Foundation Layer", "Intelligence Governance Layer",
                      "Reality Intelligence Layer", "Signal Fusion",
                      "Opportunity Discovery Layer", "Investment Diligence Layer",
                      "Portfolio Intelligence Layer", "Execution Preview Layer",
                      "Learning &amp; Feedback Layer"):
            self.assertIn(label, self.dq)
        for retired in ("Adhāra", "Adhara", "Buddhi", "Tattva", "Sphurana",
                        "Nivesha", "Saarathi", "Kriya", "Anubhava"):
            self.assertNotIn(retired, self.dq)

    def test_dashboard_executive_candidate_cards(self):
        self.assertIn("no active-run Capital Candidates", self.dash)
        self.assertIn("0 companies are surfaced", self.dash)
        self.assertIn("CosmosIQ Capital", self.dash)
        for bad in ("<button", "<form", " buy ", " sell "):
            self.assertNotIn(bad, self.dash.lower())

    def test_floating_preview_hides_cockpit_without_active_candidate(self):
        self.assertIn('id="fp-cockpit"', self.u)           # Open-cockpit button
        self.assertNotIn('data-cockpit="cockpit.html"', self.u)
