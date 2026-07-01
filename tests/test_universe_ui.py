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

# Three top-level product sections + the cockpit (opened FROM a planet). Galaxy /
# value-chain / bottleneck are zoom LEVELS inside universe.html, not separate pages.
_PAGES = ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html")

# Pages that must NOT exist as separate primary pages any more.
_REMOVED_PAGES = ("galaxy.html", "solar_system.html", "star.html")

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

    # --- four top-level artifacts produced --------------------------------
    def test_all_pages_and_assets_written(self):
        for name in _PAGES:
            self.assertTrue(os.path.isfile(self.paths[name]), name)
        self.assertEqual(tuple(PAGE_ORDER), _PAGES)
        self.assertTrue(os.path.isfile(self.paths["assets/universe.css"]))
        self.assertTrue(os.path.isfile(self.paths["assets/universe.js"]))

    # --- galaxy / value-chain / star are NOT separate primary pages -------
    def test_entity_pages_are_not_top_level(self):
        for name in _REMOVED_PAGES:
            self.assertNotIn(name, self.paths)
            self.assertFalse(os.path.isfile(os.path.join(self._tmp, name)),
                             "{0} should not be generated".format(name))
        # The top nav must list only Universe / Dashboard / Data-Quality.
        for page, h in self.html.items():
            if page == "cockpit.html":
                continue  # cockpit has its own back-strip, checked separately
            navbar = h.split('<div class="wrap">')[0]
            for name in _REMOVED_PAGES:
                self.assertNotIn('href="{0}"'.format(name), navbar,
                                 "{0} nav lists {1}".format(page, name))
            self.assertIn('href="universe.html"', navbar)
            self.assertIn('href="dashboard.html"', navbar)
            self.assertIn('href="data_quality.html"', navbar)

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
        # The qualifier appears at the value-chain zoom level inside the one universe
        # page and on the candidate cards -- never as the entry point.
        u = self.html["universe.html"].lower()
        self.assertIn("derived after value-chain", u)
        self.assertIn("derived after value-chain", self.html["dashboard.html"].lower())
        self.assertIn("never the entry point", u)

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
        # gaps + missing-data visible at the zoom levels inside the one universe page
        u = self.html["universe.html"]
        self.assertIn("Data gaps", u)
        self.assertIn("Missing", u)
        # source-authority badges on the IREN dashboard card AND in the universe pane
        self.assertIn("SEC canonical", self.html["dashboard.html"])
        self.assertIn("SEC canonical", u)

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
        for marker in ("Universe — Intelligence Pane", "Galaxy / Megatrend",
                       "Milky Way / Theme", "Solar System / Value Chain",
                       "Bottleneck Star", "Planet / Company", "Moon / Supplier"):
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
        self.assertNotIn("<h2", top)
        self.assertNotIn("<h3", top)
        self.assertNotIn("<h4", top)
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
        # a hidden intel store exists; the IREN planet body points at its blob, and
        # that blob holds IREN's company table -> clicking fills the bottom pane.
        self.assertIn('class="intel-store"', self.u)
        m = re.search(r'data-kind="planet"[^>]*data-path="[^"]*pl:iren"[^>]*'
                      r'data-intel="([^"]+)"', self.u)
        self.assertIsNotNone(m, "IREN planet body has no data-intel hook")
        blob_id = m.group(1)
        blob = re.search(
            r'<div class="intel-template" id="{0}">(.*?)</div>\s*'
            r'(?:<div class="intel-template"|</div>\s*</div>\s*</body)'.format(re.escape(blob_id)),
            self.u, re.DOTALL)
        self.assertIsNotNone(blob, "no intel blob for IREN")
        self.assertIn("IREN", blob.group(1))
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
        self.assertIn("SEC canonical", self.u)         # source-authority coverage
        self.assertIn("Data gaps", self.u)             # gaps never hidden

    # --- dashboard Locate targets a planet path that exists in the canvas -
    def test_dashboard_locate_targets_universe_path(self):
        hrefs = re.findall(r'href="(universe\.html#focus=[^"]+)"', self.d)
        iren = [h for h in hrefs if "pl:iren" in h]
        self.assertTrue(iren, "no IREN Locate-in-Universe link on the dashboard")
        path = iren[0].split("#focus=")[1]
        # the focused path must exist as a level-panel in the one universe page
        self.assertIn('data-path="{0}"'.format(path), self.u)
        self.assertIn("Locate in Universe", self.d)

    # --- the planet template exposes the accepted cockpit link ------------
    def test_planet_template_exposes_cockpit_link(self):
        self.assertIn("Open Cockpit", self.d)
        self.assertIn('href="cockpit.html"', self.u)   # from the IREN planet template

    # --- the top canvas is an immersive CSS deep-space scene (no star-div flood) -
    def test_top_canvas_is_a_css_space_scene(self):
        # the hundreds of star divs are GONE; the backdrop is CSS layers
        self.assertLess(self.u.count('class="star '), 10)
        self.assertIn('class="space-glow"', self.u)   # galactic glow (CSS)
        self.assertIn('class="space-stars"', self.u)  # single tiled star texture (CSS)
        self.assertIn('class="nebula', self.u)        # nebula wash
        self.assertIn('class="vignette"', self.u)     # vignette
        self.assertNotIn("object-grid", self.u)       # not a card grid
        self.assertIn('class="scene-bodies"', self.u)

    # --- faint SVG relationship / orbit lines connect parent -> children ---
    def test_orbit_relationship_lines_present(self):
        self.assertIn('class="orbit-lines"', self.u)
        self.assertIn("<line ", self.u)               # actual connecting segments
        # orbit lines are inside the pan/zoom transform layer (move with bodies)
        self.assertIsNotNone(
            re.search(r'<div class="scene-transform">\s*<svg class="orbit-lines"', self.u))

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

    # 2. theme / Milky-Way is its own body kind, distinct from galaxy
    def test_theme_is_milkyway_body(self):
        self.assertIn("body-milkyway", self.u)
        self.assertIn('data-kind="theme"', self.u)
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".body-milkyway .body", css)
        self.assertIn(".body-galaxy .body", css)           # still distinct from galaxy

    # 3. value-chain level = a legible directional economic flow
    def test_value_chain_directional_flow(self):
        self.assertIn("flow-lines", self.u)                # directional connectors
        self.assertIn("<polygon", self.u)                  # flow arrowheads
        # flow bodies laid left->right (multiple distinct left% positions in a band)
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
        i = self.u.find("<b>(IREN)</b>")
        self.assertGreater(i, 0, "IREN preview chip not found")
        seg = self.u[i:i + 800]
        for field in ("theme/galaxy", "value-chain role", "candidate bucket",
                      "top reason", "top risk", "market cap"):
            self.assertIn(field, seg, "planet hover missing {0}".format(field))
        self.assertIn("Timing-Confirmed", seg)             # its EXISTING status bucket
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
                     "directness of exposure", "catalyst / crowding",
                     "red-team / dilution / insolvency", "evidence quality",
                     "missing data"):
            self.assertIn(term, low, "legend missing channel: {0}".format(term))

    # --- design system + FULL-SCREEN layout -------------------------------
    def test_design_system_and_layout(self):
        with open(self.paths["assets/universe.css"], encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("backdrop-filter:blur", css)         # glassmorphism
        self.assertIn("--mono:", css)                      # monospace stack for numbers
        self.assertIn(".micro{", css)                      # uppercase micro-labels
        # the Economic Universe page fills the screen with NO page scroll ...
        self.assertIn("body.fullscreen{height:100vh", css)
        self.assertIn("overflow:hidden", css)              # no page-level scroll
        self.assertIn("flex-direction:column", css)        # status -> nav -> panes column
        # ... the top canvas is dominant and grows, the viewport fills it ...
        self.assertIn(".fullscreen-main .top-canvas{flex:1 1", css)
        self.assertIn(".fullscreen-main .top-canvas .viewport{height:100%}", css)
        # ... and the bottom pane scrolls INTERNALLY (never the page)
        self.assertIn("overflow:auto", css)

    # --- the universe page is a full-bleed full-screen shell --------------
    def test_universe_page_is_full_screen(self):
        self.assertIn('<body class="fullscreen">', self.u)
        self.assertIn('fullscreen-main', self.u)
        self.assertIn('universe-app', self.u)     # full-width 100vw shell (010A-FIX)
        self.assertNotIn('class="wrap"', self.u)           # no 1200px document width
        self.assertNotIn("<h1>Economic Universe</h1>", self.u)  # big intro trimmed
        self.assertIn('class="canvas-note"', self.u)       # compact one-line note
        # status strip + 3-item command bar are still present above the canvas
        self.assertIn('class="status-strip"', self.u)
        self.assertIn('class="command-bar"', self.u)
        # dashboard / data-quality stay document-style (their own width + scroll)
        with open(self.paths["dashboard.html"], encoding="utf-8") as fh:
            dash = fh.read()
        self.assertIn('class="wrap"', dash)
        self.assertNotIn('<body class="fullscreen">', dash)

    def test_objects_are_positioned_luminous_bodies(self):
        for cls in ("body-galaxy", "body-planet", "body-star", "body-nebula", "body-moon"):
            self.assertIn(cls, self.u, "missing luminous body class {0}".format(cls))
        # bodies are absolutely positioned in space (inline left%/top%)
        self.assertIsNotNone(
            re.search(r'class="cosmic-object[^"]*" style="left:[0-9.]+%;top:[0-9.]+%"', self.u),
            "cosmic objects are not absolutely positioned in the scene")
        # the body diameter is driven by the magnitude-derived visual size
        self.assertIn('class="body" style="width:', self.u)
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


class UniverseCenterFixTests(unittest.TestCase):
    """010A-FIX: no false 'centre of the universe'; semantic edges; full-width shell;
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
        cls.view = build_economic_universe_view(load_iren_slice())

    def _l0(self):
        m = re.search(r'data-level="0"[^>]*>(.*?)</section>', self.u, re.S)
        self.assertIsNotNone(m, "no L0 universe panel")
        return m.group(1)

    def test_universe_level_has_no_hub_and_spoke(self):
        l0 = self._l0()
        # the centre-spoke SVG must NOT be at the Universe level; semantic edges instead
        self.assertNotIn('class="orbit-lines"', l0)
        self.assertIn('class="rel-lines"', l0)
        # endpoints must be varied -- a hub would share ONE common source coordinate
        x1s = re.findall(r'<line[^>]*x1="([0-9.]+)"', l0)
        self.assertGreater(len(set(x1s)), 1, "L0 lines share a common centre (hub-and-spoke)")
        # no line to the old artificial centre (50.00, 47.00)
        self.assertNotIn('x2="50.00" y2="47.00"', l0)

    def test_universe_lines_are_the_semantic_edges(self):
        l0 = self._l0()
        self.assertEqual(l0.count("<line "), len(self.view.edges),
                         "L0 must draw exactly one line per valid semantic edge")
        # a named related pair is present (HTML-escaped &); an unrelated pair is not
        self.assertIn("AI Infrastructure ↔ Power &amp; Grid", self.u)
        self.assertNotIn("Robotics ↔ Nuclear", self.u)
        self.assertNotIn("Nuclear &amp; Energy ↔ Robotics", self.u)

    def test_deeper_levels_keep_focus_lines(self):
        # the selected-object local focus IS allowed inside deeper levels
        self.assertIn('class="orbit-lines"', self.u)

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
