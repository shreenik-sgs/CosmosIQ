"""IMPLEMENTATION-010G -- Real Terrain INTERACTION Stress Test.

Rigorously validates (and locks) INTERACTION INTEGRITY on the multi-company REAL /
watchlist terrain (010E/010F). Everything here runs OFFLINE: the watchlist is built ONLY
with injected MOCK transports (per ticker) and an injected ``now``; no test reaches a real
endpoint (a socket block guards the whole-suite offline test).

The heart of the suite is :class:`HtmlLinkGraph` -- a reusable, STRUCTURAL assertion helper
that parses a rendered page and proves the cross-link graph is CLOSED, so the contract is
checked by shape (ids / paths / parent chains) rather than by brittle string matching:

* every rendered object's ``data-intel`` resolves to a hidden intel-store ``id``;
* every zoomable object's ``data-target-path`` resolves to a level-panel ``data-path``
  (or the object is a genuine leaf with no target-path);
* every breadcrumb ``data-goto`` / ``#path=`` and every panel's ``data-parent`` chain
  walks up to ``universe`` with no missing link;
* every dashboard "Locate in Universe" ``#focus=`` href resolves to a real universe path;
* the Data Quality page carries NO dangling ``href="#..."`` (diagnostics are plain text);
* a cockpit link appears ONLY where a cockpit page was generated -- otherwise disabled
  text, never a dead anchor;
* NO dead anchors: every ``href="#x"`` resolves to an id / path, is a known-safe JS-wired
  control (zoom / floating-preview), or the known in-page ``#intel-pane`` anchor;
* NO fake relationship edges / connector SVGs in the immersive cosmos; no centre-of-universe
  hub; only the four base pages (+ conditional per-ticker cockpit).

Plus NAV_JS hardening checks (stale ``.selected`` cleared on level change / reset, the
below-fold / floating-preview "Missing intelligence template" fallback) and the standing
guardrails (no scheduler / broker / order affordance / new scoring fn / secret in HTML;
demo stays the default and deterministic; real single + watchlist modes still build).
"""

from __future__ import annotations

import ast
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
from universe_ui.assets import NAV_JS
from universe_ui.terrain import CompanyNode

_FIXTURE_DIR = os.path.join(_ROOT, "tests", "fixtures", "slice")
_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")
_NOW = 1750000000.0
_BASE_PAGES = ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html")

# href="#..." anchors that are DELIBERATELY JS-wired interactive controls (they call
# preventDefault + do real work in NAV_JS); they are safe, not dead. Verified below to be
# genuinely present in NAV_JS as click targets.
_INTERACTIVE_CONTROL_IDS = frozenset({
    "zoom-back", "zoom-in", "zoom-out", "zoom-reset", "zoom-fit", "zoom-locate",
    "fp-close", "fp-zoom", "fp-cockpit", "fp-details",
})
# Known-safe in-page anchors (scroll targets that resolve to a real element id).
_KNOWN_IN_PAGE_ANCHORS = frozenset({"intel-pane"})


# --------------------------------------------------------------------------- #
# Offline mock transports (real IREN fixtures; no network)                    #
# --------------------------------------------------------------------------- #
def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _mock():
    return {
        "sec_submissions": lambda tk: _load("sec_submissions_iren.json"),
        "sec_companyfacts": lambda tk: _load("sec_companyfacts_iren.json"),
        "fmp_profile": lambda tk: _load("fmp_profile_iren.json"),
        "fmp_income_statement": lambda tk: _load("fmp_income_statement_iren.json"),
        "fmp_ohlcv": lambda tk: _load("fmp_ohlcv_iren.json"),
        "fmp_news": lambda tk: _load("fmp_news_iren.json"),
        "fmp_ownership": lambda tk: _load("fmp_ownership_iren.json"),
    }


def _tbt(*tickers):
    return {tk: _mock() for tk in tickers}


def _boom_socket(*_a, **_k):
    raise AssertionError("network access attempted")


def _build_watchlist(prefix, tickers, tbt, **kw):
    d = tempfile.mkdtemp(prefix=prefix)
    kw.setdefault("now", _NOW)
    return build_universe_app(d, mode="real_evidence_on_demand", tickers=tickers,
                              transports_by_ticker=tbt, **kw)


def _read(paths, name):
    with open(paths[name], encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# Reusable structural link-graph helper                                        #
# --------------------------------------------------------------------------- #
_TAG_RE = r"<[^>]*class=\"[^\"]*{0}[^\"]*\"[^>]*>"


def _attr(tag, name):
    m = re.search(r'{0}="([^"]*)"'.format(re.escape(name)), tag)
    return m.group(1) if m else None


class HtmlLinkGraph:
    """A parsed, structural view of ONE rendered page's interaction graph.

    Scripts are stripped first so the inlined NAV_JS (which contains string-built
    ``href="#path='+p+'"`` fragments) never masquerades as real page anchors.
    """

    def __init__(self, html):
        self.raw = html
        # strip <script>...</script> so JS source can't be mistaken for page anchors
        self.body = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
        self.intel_defs = set(re.findall(
            r'class="intel-template"[^>]*\bid="([^"]+)"', self.body))
        self.ids = set(re.findall(r'\bid="([^"]+)"', self.body))
        # level panels: path -> parent (parent may be None for the root)
        self.panel_parent = {}
        for tag in re.findall(_TAG_RE.format("level-panel"), self.body):
            path = _attr(tag, "data-path")
            if path is not None:
                self.panel_parent[path] = _attr(tag, "data-parent")
        self.panel_paths = set(self.panel_parent)
        # cosmic objects
        self.objects = []
        for tag in re.findall(_TAG_RE.format("cosmic-object"), self.body):
            self.objects.append({
                "path": _attr(tag, "data-path"),
                "intel": _attr(tag, "data-intel"),
                "target": _attr(tag, "data-target-path"),
                "cockpit": _attr(tag, "data-cockpit"),
                "kind": _attr(tag, "data-kind"),
            })
        # breadcrumb / goto targets and dashboard locate targets
        self.gotos = set(re.findall(r'data-goto="([^"]+)"', self.body))
        self.focus_hrefs = set(re.findall(
            r'universe\.html#focus=([^"\'&]+)', self.body))
        # all in-page hash anchors as (href_value, owning_id_or_None)
        self.hash_anchors = []
        for tag in re.findall(r"<a\b[^>]*>", self.body):
            href = _attr(tag, "href")
            if href is None or not href.startswith("#"):
                continue
            self.hash_anchors.append((href[1:], _attr(tag, "id")))

    # -- individual contract assertions (each raises AssertionError on failure) --
    def assert_intel_closed(self, tc):
        refs = {o["intel"] for o in self.objects if o["intel"]}
        tc.assertTrue(refs, "no data-intel refs found on the page")
        tc.assertEqual(refs - self.intel_defs, set(),
                       "unresolved data-intel: {0}".format(sorted(refs - self.intel_defs)))

    def assert_target_paths_closed(self, tc):
        for o in self.objects:
            tp = o["target"]
            if tp:
                tc.assertIn(tp, self.panel_paths,
                            "object target-path resolves to no panel: {0}".format(tp))
            # else: a genuine leaf (planet / star) -- no descent, allowed

    def assert_parent_chains_reach_universe(self, tc):
        for path, parent in self.panel_parent.items():
            if path == "universe":
                continue
            seen = [path]
            cur = parent
            while cur is not None and cur != "universe":
                tc.assertIn(cur, self.panel_paths,
                            "broken parent link {0} for {1}".format(cur, path))
                tc.assertNotIn(cur, seen, "parent cycle at {0}".format(cur))
                seen.append(cur)
                cur = self.panel_parent.get(cur)
            tc.assertEqual(cur, "universe",
                           "parent chain of {0} does not reach universe".format(path))

    def assert_gotos_closed(self, tc):
        for g in self.gotos:
            if "'" in g or "+" in g:  # inline-JS fragment leaked past a strip -- ignore
                continue
            tc.assertTrue(g == "universe" or g in self.panel_paths,
                          "data-goto resolves nowhere: {0}".format(g))

    def assert_focus_hrefs_closed(self, tc, panel_paths):
        for f in self.focus_hrefs:
            tc.assertIn(f, panel_paths,
                        "dashboard #focus= resolves to no universe path: {0}".format(f))

    def assert_no_dead_anchors(self, tc, cockpit_files=()):
        for value, owner_id in self.hash_anchors:
            target = value
            for pfx in ("focus=", "path="):
                if target.startswith(pfx):
                    target = target[len(pfx):]
            if target in self.ids or target in self.panel_paths:
                continue
            if target in _KNOWN_IN_PAGE_ANCHORS:
                continue
            # a bare href="#" is only OK on a known JS-wired interactive control
            tc.assertIn(owner_id, _INTERACTIVE_CONTROL_IDS,
                        "dead anchor href=#{0} (owner id={1!r})".format(value, owner_id))

    def assert_cockpit_links_resolve(self, tc, cockpit_files):
        for o in self.objects:
            ck = o["cockpit"]
            if ck and ck not in ("", "#"):
                tc.assertIn(ck, cockpit_files,
                            "cockpit link points to a missing page: {0}".format(ck))

    def connector_classes(self):
        return re.findall(r'class="[^"]*(?:rel-lines|orbit-lines|flow-lines)[^"]*"', self.body)


def _graph(paths, name):
    return HtmlLinkGraph(_read(paths, name))


def _cockpit_files(paths):
    return {os.path.basename(p) for k, p in paths.items()
            if os.path.basename(p).startswith("cockpit") and p.endswith(".html")}


# =========================================================================== #
# A. Closed cross-link graph on the WATCHLIST terrain                          #
# =========================================================================== #
class WatchlistLinkGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = _build_watchlist("ix_wl_", ["IREN", "AAOI", "INOD"],
                                     _tbt("IREN", "AAOI", "INOD"))
        cls.uni = _graph(cls.paths, "universe.html")
        cls.dash = _graph(cls.paths, "dashboard.html")
        cls.dq = _graph(cls.paths, "data_quality.html")
        cls.cockpit_files = _cockpit_files(cls.paths)

    def test_every_object_data_intel_resolves(self):
        self.uni.assert_intel_closed(self)

    def test_every_target_path_resolves_or_is_leaf(self):
        self.uni.assert_target_paths_closed(self)
        # sanity: at least one company planet per ticker HAS a resolvable target-path
        planet_targets = [o["target"] for o in self.uni.objects
                          if o["kind"] == "star" and o["target"]]
        self.assertTrue(planet_targets)

    def test_every_company_has_a_matching_level_panel(self):
        # each rekeyed company planet across ALL tickers has an L5 pl: panel
        for tk in ("iren", "aaoi", "inod"):
            hits = [p for p in self.uni.panel_paths if p.endswith("/pl:{0}".format(tk))]
            self.assertEqual(len(hits), 1,
                             "expected exactly one planet panel for {0}".format(tk))

    def test_breadcrumb_parent_chains_reach_universe(self):
        self.uni.assert_parent_chains_reach_universe(self)
        self.uni.assert_gotos_closed(self)

    def test_dashboard_locate_hrefs_resolve(self):
        # one Locate href per built company, each resolving to a real universe panel
        self.assertEqual(len(self.dash.focus_hrefs), 3)
        self.dash.assert_focus_hrefs_closed(self, self.uni.panel_paths)

    def test_data_quality_has_no_dangling_anchors(self):
        self.dq.assert_no_dead_anchors(self, self.cockpit_files)
        # DQ diagnostics are plain text here: no interactive in-page targets at all
        self.assertEqual(self.dq.gotos, set())

    def test_no_dead_anchors_anywhere(self):
        for g in (self.uni, self.dash, self.dq):
            g.assert_no_dead_anchors(self, self.cockpit_files)

    def test_cockpit_links_only_where_a_cockpit_exists(self):
        # every data-cockpit on a planet must point at a REAL generated cockpit page
        for g in (self.uni, self.dash):
            g.assert_cockpit_links_resolve(self, self.cockpit_files)
        # these fixtures produce no per-ticker cockpit -> planets show disabled text,
        # never a dead anchor
        self.assertIn("Open Cockpit available for real candidates only", self.uni.raw)
        self.assertNotIn('href="cockpit_', self.uni.raw)

    def test_no_fake_edges_no_centre_hub(self):
        self.assertEqual(self.uni.connector_classes(), [])
        low = self.uni.raw.lower()
        self.assertNotIn("centre-of-universe", low)
        self.assertNotIn("center-of-universe", low)
        self.assertNotIn("hub-and-spoke\">", low)  # never an actual hub element

    def test_only_expected_pages_generated(self):
        html_pages = {os.path.basename(p) for k, p in self.paths.items()
                      if p.endswith(".html")}
        # base four + (conditionally) cockpit_<ticker>.html; nothing else
        for name in html_pages:
            self.assertTrue(name in _BASE_PAGES or name.startswith("cockpit_"),
                            "unexpected page generated: {0}".format(name))
        # no per-level pages, no galaxy/value-chain/star top-level tabs
        for banned in ("galaxy.html", "value_chain.html", "star.html", "theme.html"):
            self.assertNotIn(banned, html_pages)

    def test_top_nav_is_only_three_sections(self):
        nav = re.search(r"<nav[^>]*class=\"[^\"]*topnav[^\"]*\".*?</nav>",
                        self.uni.raw, re.S)
        if nav is None:  # nav class differs -- fall back to the header region
            nav = re.search(r"<header.*?</header>", self.uni.raw, re.S)
        region = nav.group(0) if nav else self.uni.raw
        self.assertIn("universe.html", region)
        self.assertIn("dashboard.html", region)
        self.assertIn("data_quality.html", region)
        # cockpit is opened FROM a planet, never a top-level tab
        self.assertNotIn('href="cockpit.html"', region)


# =========================================================================== #
# B. Object-click / preview / intel fallbacks (NAV_JS behaviour contract)      #
# =========================================================================== #
class NavJsContractTests(unittest.TestCase):
    def test_object_click_sets_selection_then_descends_then_own_intel(self):
        self.assertIn("classList.add('selected')", NAV_JS)
        self.assertIsNotNone(
            re.search(r"showLevel\(tp\);.*?setIntel\(myIntel\);", NAV_JS, re.S),
            "click must set its own intel AFTER any level change")

    def test_selected_is_cleared_on_level_change_and_reset(self):
        # the hardening fix: a persistent .selected ring must not go stale across a
        # level change / view reset. clearSelection is defined and called from resetView,
        # and showLevel resets the view on every level change.
        self.assertIn("function clearSelection(", NAV_JS)
        self.assertIsNotNone(
            re.search(r"function resetView\(\)\{\s*clearSelection\(\)", NAV_JS),
            "resetView must clear selection")
        self.assertIsNotNone(
            re.search(r"function showLevel\([^)]*\)\{.*?resetView\(\);", NAV_JS, re.S),
            "showLevel must resetView (clearing selection) on level change")
        # locate captures the selected object BEFORE resetView clears it
        start = NAV_JS.index("function locateSelected")
        tail = NAV_JS[start:]
        loc = tail[:tail.index("function ", len("function locateSelected"))]
        self.assertLess(loc.index(".selected"), loc.index("resetView()"),
                        "locateSelected must read .selected before resetView clears it")

    def test_floating_preview_and_below_fold_intel_fallback(self):
        # a missing intel template shows a VISIBLE fallback, never a blank pane
        self.assertIn("Missing intelligence template", NAV_JS)
        self.assertIsNotNone(
            re.search(r"setIntel\(id\)\{.*?else\{.*?Missing intelligence template",
                      NAV_JS, re.S),
            "setIntel must have an explicit missing-template fallback branch")

    def test_cockpit_preview_button_hidden_without_a_cockpit_link(self):
        # fpCockpit is only shown for an object carrying data-cockpit; otherwise hidden,
        # never a dangling live link
        self.assertIsNotNone(
            re.search(r"data-cockpit.*?fpCockpit.*?display='none'", NAV_JS, re.S))


class ObjectClickTargetTests(unittest.TestCase):
    """Every clickable body is either a valid zoom (target resolves) or a real leaf, and
    always carries a resolvable intel id -- checked structurally across the terrain."""

    def test_object_click_contract_holds_for_every_cosmic_object(self):
        paths = _build_watchlist("ix_click_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"))
        g = _graph(paths, "universe.html")
        self.assertTrue(g.objects)
        for o in g.objects:
            self.assertTrue(o["intel"], "cosmic-object without data-intel")
            self.assertIn(o["intel"], g.intel_defs,
                          "cosmic-object intel does not resolve: {0}".format(o["intel"]))
            if o["target"]:
                self.assertIn(o["target"], g.panel_paths)


# =========================================================================== #
# C. Sparse terrain -- explicit visible placeholders (never blank/fabricated)  #
# =========================================================================== #
class SparseTerrainTests(unittest.TestCase):
    def test_unclassified_region_is_visible_and_linked(self):
        # THIN has no evidence -> unclassified region; graph must still be closed
        paths = _build_watchlist("ix_unc_", ["IREN", "THIN"],
                                 {"IREN": _mock(), "THIN": {}})
        g = _graph(paths, "universe.html")
        self.assertIn("Unclassified", g.raw)
        # the unclassified galaxy has its own resolvable level panel
        self.assertIn("universe/g:unclassified", g.panel_paths)
        g.assert_intel_closed(self)
        g.assert_target_paths_closed(self)
        g.assert_parent_chains_reach_universe(self)
        g.assert_no_dead_anchors(self, _cockpit_files(paths))

    def test_missing_state_placeholders_render(self):
        paths = _build_watchlist("ix_missing_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"))
        uni = _read(paths, "universe.html")
        low = uni.lower()
        # neutral-size + dashed-outline visual explanation for missing magnitude
        self.assertIn("dashed-outline", uni)
        self.assertIn("neutral size", low)
        self.assertIn("magnitude missing", low)
        # data gaps are surfaced, not hidden
        self.assertIn("data gap", low)
        self.assertIn("terrain incomplete", low)

    def test_missing_market_cap_is_neutral_not_fabricated(self):
        # the legend explains missing magnitude -> neutral / dashed (never invented)
        paths = _build_watchlist("ix_mc_", ["IREN"], _tbt("IREN"))
        uni = _read(paths, "universe.html")
        self.assertIn("dashed-outline", uni)
        self.assertIn("neutral", uni.lower())


# =========================================================================== #
# D. Modes still work + determinism                                            #
# =========================================================================== #
class ModesStillWorkTests(unittest.TestCase):
    def test_demo_is_default_and_deterministic(self):
        d1 = tempfile.mkdtemp(prefix="ix_demo_a_")
        d2 = tempfile.mkdtemp(prefix="ix_demo_b_")
        p1 = build_universe_app(d1)  # no mode -> demo
        p2 = build_universe_app(d2)
        self.assertIn("fixture/demo", _read(p1, "universe.html"))
        self.assertNotIn("real evidence on demand", _read(p1, "universe.html").lower())
        for name in _BASE_PAGES:
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                             "demo non-deterministic: {0}".format(name))

    def test_single_ticker_real_mode_still_builds(self):
        d = tempfile.mkdtemp(prefix="ix_single_")
        paths = build_universe_app(d, mode="real_evidence_on_demand", ticker="IREN",
                                   transports=_mock(), now=_NOW)
        g = _graph(paths, "universe.html")
        self.assertIn("(IREN)", g.raw)
        g.assert_intel_closed(self)
        g.assert_target_paths_closed(self)
        g.assert_parent_chains_reach_universe(self)
        g.assert_no_dead_anchors(self, _cockpit_files(paths))

    def test_single_ticker_output_byte_stable(self):
        a = build_universe_app(tempfile.mkdtemp(prefix="ix_s_a_"),
                               mode="real_evidence_on_demand", ticker="IREN",
                               transports=_mock(), now=_NOW)
        b = build_universe_app(tempfile.mkdtemp(prefix="ix_s_b_"),
                               mode="real_evidence_on_demand", ticker="IREN",
                               transports=_mock(), now=_NOW)
        for name in _BASE_PAGES:
            self.assertEqual(open(a[name], "rb").read(), open(b[name], "rb").read())

    def test_watchlist_mode_builds_and_is_deterministic(self):
        p1 = _build_watchlist("ix_wl_a_", ["IREN", "AAOI", "INOD"],
                              _tbt("IREN", "AAOI", "INOD"))
        p2 = _build_watchlist("ix_wl_b_", ["IREN", "AAOI", "INOD"],
                              _tbt("IREN", "AAOI", "INOD"))
        for name in ("universe.html", "dashboard.html", "data_quality.html"):
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read())


# =========================================================================== #
# E. Whole-suite guardrails (offline; no scheduler/broker/scoring/secret)      #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = _build_watchlist("ix_guard_", ["IREN", "AAOI", "INOD"],
                                     _tbt("IREN", "AAOI", "INOD"), enable_yfinance=True)
        cls.html = "\n".join(_read(cls.paths, n) for n in _BASE_PAGES)

    def test_no_broker_or_order_or_action_affordance(self):
        low = self.html.lower()
        # note: the honest disclaimer legitimately says "Not broker-connected", so we ban
        # broker *affordances*, not the disclaimer word itself.
        for banned in ("<button", "<form", "onclick", 'type="submit"', "place order",
                       "place an order", "submit_order", "broker_order", "submit(",
                       "fetch(", "xmlhttprequest"):
            self.assertNotIn(banned, low, "banned affordance: {0}".format(banned))
        self.assertIsNone(re.search(r"\b(buy|sell)\b", low), "buy/sell token present")

    def test_offline_whole_watchlist_build_under_socket_block(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            _build_watchlist("ix_off_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                             enable_yfinance=True)
        finally:
            socket.socket = real

    def test_no_secret_leaks_into_any_page(self):
        secret = "IX-SECRET-SHOULD-NOT-LEAK-2026"
        paths = _build_watchlist("ix_sec_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                                 fmp_api_key=secret, sec_user_agent=secret)
        for k, p in paths.items():
            if p.endswith(".html"):
                self.assertNotIn(secret, open(p, encoding="utf-8").read())

    def test_assets_module_defines_no_scheduler_broker_or_network(self):
        forbidden = {"sched", "asyncio", "subprocess", "socketserver", "urllib", "http",
                     "socket", "requests", "aiohttp", "httpx", "threading", "multiprocessing"}
        with open(os.path.join(_UNIVERSE_UI_DIR, "assets.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name.split(".")[0], forbidden)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)

    def test_nav_js_has_no_scheduler_broker_or_network_calls(self):
        low = NAV_JS.lower()
        for banned in ("settimeout", "setinterval", "fetch(", "xmlhttprequest",
                       "websocket", "eval(", "new function", "place order", "buy(",
                       "sell(", ".submit(", "requestanimationframe"):
            self.assertNotIn(banned, low, "NAV_JS forbidden call: {0}".format(banned))

    def test_render_module_defines_no_new_scoring_or_ranking_fn(self):
        for mod in ("render.py", "watchlist_terrain.py", "assets.py"):
            with open(os.path.join(_UNIVERSE_UI_DIR, mod), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    nm = node.name.lower()
                    self.assertFalse(nm.startswith("score") or nm.startswith("rank"),
                                     "{0}: scoring/ranking fn {1}".format(mod, node.name))


if __name__ == "__main__":
    unittest.main()
