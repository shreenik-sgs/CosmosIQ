"""IMPLEMENTATION-011C -- Terrain / Data-Quality / cockpit enrichment expansion.

Everything here runs OFFLINE. The 011A/B diligence enrichment is wired MORE COMPLETELY
through the real single + watchlist pipeline (never demo): a source-backed
``DiligenceEnrichmentBundle`` is constructed per ticker FROM that ticker's already-fetched
SEC/FMP payloads (no new fetch) and overlaid onto the terrain, the Data-Quality panel, the
CIO dashboard cards and the cockpit PAGE wrapper. This suite proves the discipline the gate
requires:

* market cap -> CompanyNode magnitude + ``size_basis`` via the EXISTING ``visual_size``
  helper (un-dashed when present, dashed gap when absent) -- no new metric;
* TAM feeds theme / value-chain magnitude ONLY when source-backed; a manual TAM stays
  manual (never canonical); value-chain layers / bottleneck severity+duration populate ONLY
  when a fixture supplies them, else an honest gap;
* company IR -> catalyst / risk / evidence cards ONLY when source-backed (company_claim
  marked); leadership -> diagnostic evidence only (never a rank/score);
* Data Quality + CIO dashboard show per-company enrichment coverage / gaps (data-sourcing
  actions only, never a trade); the cockpit page shows a READ-ONLY enrichment note with NO
  trade action and ``broker_order_id`` None;
* the watchlist still merges into one closed-graph terrain (no centre; every data-intel
  resolves; no dead anchors); demo stays byte-identical; no new score/rank fn; offline.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import re
import socket
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
_TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (_SRC, _TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json

from universe_ui.app import build_universe_app
from universe_ui.real_terrain import build_real_evidence_terrain_for_ticker
from universe_ui.terrain import (
    BottleneckNode,
    CatalystNode,
    CompanyNode,
    GalaxyNode,
    RiskNode,
    ThemeNode,
    ValueChainLayer,
    ValueChainNode,
)
from universe_ui.view_models import (
    CandidateCardView,
    PlanetCandidateView,
    visual_size,
)
from diligence_enrichment import build_diligence_enrichment_bundle
from diligence_enrichment.source_contract import manual_is_not_canonical

from test_terrain_interaction import HtmlLinkGraph  # reused 010G structural helper

_FIXTURE_DIR = os.path.join(_ROOT, "tests", "fixtures", "slice")
_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")
_NOW = 1750000000.0
_PAGES = ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html")

_MANUAL_TAM = {"amount": 5.0e10, "market": "AI data-center hosting",
               "methodology": "top-down analyst view", "source": "analyst note 2026"}
_VC_FIX = {
    "category": "investor_presentation", "chain_name": "AI compute hosting",
    "source_refs": ["IREN investor deck Q2-2026"],
    "layers": [
        {"label": "Power / grid", "sequence": 0, "companies": ["IREN"],
         "suppliers": ["grid operator"], "bottleneck_exposure": "direct"},
        {"label": "Compute hosting", "sequence": 1, "companies": ["IREN"],
         "customers": ["AI labs"]},
    ],
    "suppliers": ["grid operator"], "customers": ["AI labs"]}
_BN_FIX = {
    "category": "investor_presentation", "name": "Secured grid power",
    "bottleneck_type": "power_capacity", "severity": "acute",
    "expected_duration": "multi_year", "constrained_resource": "interconnect / power",
    "source_refs": ["IREN investor deck Q2-2026"]}
_IR_FIX = {
    "investor_presentation_refs": ["IREN Q2-2026 deck"],
    "earnings_transcript_refs": ["IREN Q2-2026 call"],
    "guidance_statements": ["management targets 2GW contracted by 2027"],
    "disclosed_catalysts": ["new hosting contract signed"],
    "disclosed_risks": ["power interconnect delay"]}
_LEAD_FIX = {"members": [{"name": "Jane Doe", "role": "CEO", "since": "2019"}],
             "tenure_note": "founder-led", "source_refs": ["IREN IR site"]}


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _mock(*, with_profile=True, with_sec=True):
    """A MOCK transport bundle returning the real IREN fixtures (fully offline)."""
    t = {
        "sec_submissions": lambda tk: _load("sec_submissions_iren.json"),
        "sec_companyfacts": lambda tk: _load("sec_companyfacts_iren.json"),
        "fmp_profile": lambda tk: _load("fmp_profile_iren.json"),
        "fmp_income_statement": lambda tk: _load("fmp_income_statement_iren.json"),
        "fmp_ohlcv": lambda tk: _load("fmp_ohlcv_iren.json"),
        "fmp_news": lambda tk: _load("fmp_news_iren.json"),
        "fmp_ownership": lambda tk: _load("fmp_ownership_iren.json"),
    }
    if not with_profile:
        t.pop("fmp_profile")
    if not with_sec:
        t.pop("sec_companyfacts")
        t.pop("sec_submissions")
    return t


def _tbt(*tickers):
    return {tk: _mock() for tk in tickers}


def _boom_socket(*_a, **_k):
    raise AssertionError("network access attempted")


def _terrain(**enr_kw):
    """Real single IREN terrain built WITH enrichment auto-constructed from payloads."""
    return build_real_evidence_terrain_for_ticker(
        "IREN", transports=_mock(), enrich=True, now=_NOW, **enr_kw)


def _nodes(terrain, kind):
    return [n for _i, n in terrain.all_nodes() if isinstance(n, kind)]


def _read(paths, name):
    with open(paths[name], encoding="utf-8") as fh:
        return fh.read()


# =========================================================================== #
# A. CompanyNode magnitude + size_basis (rows 8, 15)                           #
# =========================================================================== #
class CompanyMagnitudeTests(unittest.TestCase):
    def test_market_cap_sizes_company_and_size_basis_undashed(self):
        terrain, _ = _terrain()
        co = _nodes(terrain, CompanyNode)[0]
        self.assertEqual(co.market_cap, 4200000000.0)          # FMP mktCap, sourced
        enc = co.visual_encoding
        self.assertIn("market_cap", enc.size_basis)
        self.assertIn("convenience", enc.size_basis)            # authority stamped
        self.assertFalse(enc.dashed_outline)                    # present -> un-dashed
        self.assertEqual(enc.size_value, visual_size(4200000000.0, "planet"))

    def test_missing_market_cap_stays_dashed_gap_with_data_action(self):
        # drop the FMP profile -> no market cap sourced -> honest dashed gap + data action
        terrain, status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(with_profile=False), enrich=True, now=_NOW)
        co = _nodes(terrain, CompanyNode)[0]
        self.assertIsNone(co.market_cap)
        self.assertTrue(co.visual_encoding.dashed_outline)
        self.assertEqual(co.visual_encoding.size_value, visual_size(None, "planet"))
        joined = " ".join(terrain.data_gaps).lower()
        self.assertIn("market cap not surfaced", joined)
        # the coverage panel emits a data-sourcing action for the missing metric
        enr = status["enrichment"]
        self.assertFalse(enr.has_market_cap())

    def test_size_is_magnitude_only_never_a_score(self):
        terrain, _ = _terrain()
        co = _nodes(terrain, CompanyNode)[0]
        # size == the pure visual_size projection of the magnitude; nothing else feeds it
        self.assertEqual(co.visual_encoding.size_value,
                         visual_size(co.market_cap, "planet"))


# =========================================================================== #
# B. TAM / value-chain / bottleneck -- source-backed ONLY (rows 16, 17, 18)    #
# =========================================================================== #
class SourceBackedMagnitudeTests(unittest.TestCase):
    def test_tam_feeds_theme_and_value_chain_only_when_sourced_manual_not_canonical(self):
        terrain, _ = _terrain(manual_tam=_MANUAL_TAM)
        gx = _nodes(terrain, GalaxyNode)[0]
        vc = _nodes(terrain, ValueChainNode)[0]
        self.assertEqual(gx.economic_magnitude, 5.0e10)
        self.assertEqual(gx.visual_encoding.size_value, visual_size(5.0e10, "galaxy"))
        self.assertEqual(vc.revenue_pool_or_tam, 5.0e10)
        self.assertEqual(vc.visual_encoding.size_value, visual_size(5.0e10, "solar_system"))
        # a MANUAL TAM is shown manual and asserted never canonical
        self.assertIn("manual", gx.visual_encoding.size_basis.lower())
        self.assertNotIn("canonical", gx.visual_encoding.size_basis.lower()
                         .replace("not canonical", ""))
        self.assertTrue(manual_is_not_canonical())

    def test_no_tam_leaves_theme_and_value_chain_dashed_gap(self):
        terrain, _ = _terrain()  # no manual_tam supplied
        gx = _nodes(terrain, GalaxyNode)[0]
        vc = _nodes(terrain, ValueChainNode)[0]
        self.assertIsNone(gx.economic_magnitude)
        self.assertTrue(gx.visual_encoding.dashed_outline)
        self.assertIsNone(vc.revenue_pool_or_tam)
        self.assertTrue(vc.visual_encoding.dashed_outline)
        self.assertIn("tam", " ".join(vc.data_gaps).lower())

    def test_value_chain_layers_populate_only_when_sourced(self):
        with_vc, _ = _terrain(value_chain_fixture=_VC_FIX)
        self.assertEqual([l.label for l in _nodes(with_vc, ValueChainLayer)],
                         ["Power / grid", "Compute hosting"])
        without, _ = _terrain()
        self.assertEqual(_nodes(without, ValueChainLayer), [])
        self.assertIn("supplier", " ".join(without.data_gaps).lower())

    def test_bottleneck_severity_duration_populate_only_when_sourced(self):
        with_bn, _ = _terrain(bottleneck_fixture=_BN_FIX)
        bn = _nodes(with_bn, BottleneckNode)[0]
        self.assertEqual(bn.severity, "acute")
        self.assertEqual(bn.expected_duration, "multi_year")
        self.assertFalse(bn.visual_encoding.dashed_outline)
        without, _ = _terrain()
        bn2 = _nodes(without, BottleneckNode)[0]
        self.assertEqual(bn2.severity, "")
        self.assertTrue(bn2.visual_encoding.dashed_outline)
        self.assertTrue(bn2.data_gaps)


# =========================================================================== #
# C. Company IR -> cards; leadership -> diagnostics only (rows 19, 21)         #
# =========================================================================== #
class IRAndLeadershipTests(unittest.TestCase):
    def test_ir_becomes_catalyst_and_risk_cards_marked_company_claim(self):
        terrain, _ = _terrain(ir_fixture=_IR_FIX)
        cats = [c for c in _nodes(terrain, CatalystNode)
                if "company_claim" in c.description]
        risks = [r for r in _nodes(terrain, RiskNode)
                 if "company_claim" in r.description]
        self.assertTrue(any("new hosting contract" in c.description for c in cats))
        self.assertTrue(any("2GW" in c.description for c in cats))      # guidance
        self.assertTrue(any("interconnect delay" in r.description for r in risks))
        # every IR-derived card is a company_claim, never presented as a verified fact
        for c in cats:
            self.assertIn("company_claim", c.description)
            self.assertNotIn("verified_fact", c.description)

    def test_no_ir_means_no_cards_but_an_honest_gap(self):
        terrain, status = _terrain()  # no ir fixture
        ir_cards = [c for c in _nodes(terrain, CatalystNode)
                    if "company_claim" in c.description]
        self.assertEqual(ir_cards, [])
        self.assertFalse(status["enrichment"].ir.present)

    def test_leadership_is_diagnostic_evidence_only_never_a_rank(self):
        terrain, status = _terrain(leadership_fixture=_LEAD_FIX)
        enr = status["enrichment"]
        self.assertTrue(enr.leadership.present)
        # leadership creates NO catalyst / risk / bottleneck node -- diagnostics only
        for c in _nodes(terrain, CatalystNode):
            self.assertNotIn("Jane Doe", c.description)
        for r in _nodes(terrain, RiskNode):
            self.assertNotIn("Jane Doe", r.description)


# =========================================================================== #
# D. Data Quality + CIO dashboard per-company coverage (rows 23, 24)           #
# =========================================================================== #
class DataQualityAndDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        enr = build_diligence_enrichment_bundle(
            "IREN", sec_facts=_load("sec_companyfacts_iren.json"),
            fmp_profile=_load("fmp_profile_iren.json"),
            fmp_income=_load("fmp_income_statement_iren.json"),
            manual_tam=_MANUAL_TAM, value_chain_fixture=_VC_FIX,
            bottleneck_fixture=_BN_FIX, ir_fixture=_IR_FIX,
            leadership_fixture=_LEAD_FIX, now=_NOW)
        cls.d = tempfile.mkdtemp(prefix="enr011c_")
        cls.paths = build_universe_app(
            cls.d, mode="real_evidence_on_demand", ticker="IREN",
            transports=_mock(), enrichment=enr, now=_NOW)
        cls.dq = _read(cls.paths, "data_quality.html")
        cls.dash = _read(cls.paths, "dashboard.html")

    def test_data_quality_shows_enrichment_coverage_and_authority(self):
        self.assertIn("Diligence-enrichment coverage", self.dq)
        for area in ("market cap", "TAM", "value chain", "bottleneck",
                     "company IR", "leadership"):
            self.assertIn(area, self.dq)
        self.assertIn("convenience", self.dq)      # market cap authority
        self.assertIn("manual", self.dq)           # TAM authority
        self.assertIn("company_claim", self.dq)    # IR claim status

    def test_dashboard_card_shows_per_company_enrichment(self):
        self.assertIn("Diligence enrichment", self.dash)
        self.assertIn("Source-backed facts", self.dash)
        self.assertIn("sector:", self.dash)                       # profile fact
        self.assertIn("diagnostic evidence only", self.dash)      # leadership
        # keeps the navigation affordances; no trade affordance
        self.assertIn("Locate in Universe", self.dash)
        self.assertIn("Open Cockpit", self.dash)

    def test_no_trade_or_score_wording_in_enrichment_surfaces(self):
        for html in (self.dq, self.dash):
            low = html.lower()
            self.assertIsNone(re.search(r"\b(buy|sell)\b", low))
            for banned in ("place order", "submit order", "trade now", "broker_order_id="):
                self.assertNotIn(banned, low)

    def test_no_secret_leaks(self):
        self.assertNotIn("apikey", self.dq.lower())


# =========================================================================== #
# E. Cockpit page enrichment note -- read-only, no trade action (row 25)       #
# =========================================================================== #
class CockpitEnrichmentNoteTests(unittest.TestCase):
    def test_single_cockpit_shows_readonly_enrichment_note_no_trade(self):
        d = tempfile.mkdtemp(prefix="enr011c_ck_")
        paths = build_universe_app(
            d, mode="real_evidence_on_demand", ticker="IREN",
            transports=_mock(), enrich=True, now=_NOW)
        ck = _read(paths, "cockpit.html")
        self.assertIn("Diligence enrichment (read-only evidence)", ck)
        self.assertIn("broker record: none", ck.lower())
        low = ck.lower()
        self.assertIsNone(re.search(r"\b(buy|sell)\b", low))
        for banned in ("<button", "<form", "onclick", 'type="submit"', "place order"):
            self.assertNotIn(banned, low)

    def test_cockpit_note_absent_without_enrichment(self):
        d = tempfile.mkdtemp(prefix="enr011c_ck2_")
        paths = build_universe_app(
            d, mode="real_evidence_on_demand", ticker="IREN",
            transports=_mock(), now=_NOW)  # enrich defaults off, no bundle
        ck = _read(paths, "cockpit.html")
        self.assertNotIn("Diligence enrichment (read-only evidence)", ck)


# =========================================================================== #
# F. Watchlist merge stays a closed graph (rows 13, 14, 26, 27)               #
# =========================================================================== #
class WatchlistEnrichmentGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="enr011c_wl_")
        cls.paths = build_universe_app(
            cls.d, mode="real_evidence_on_demand",
            transports_by_ticker=_tbt("IREN", "AAOI", "INOD"), enrich=True, now=_NOW)
        cls.uni = HtmlLinkGraph(_read(cls.paths, "universe.html"))
        cls.dq = _read(cls.paths, "data_quality.html")

    def test_merged_terrain_has_multiple_companies_no_centre(self):
        # three co-located company planets, one merged theme, no centre / fake edges
        planets = [p for p in self.uni.panel_paths if "/pl:" in p]
        self.assertGreaterEqual(len(planets), 3)
        self.assertEqual(self.uni.connector_classes(), [])  # no invented centre/hub lines

    def test_every_data_intel_resolves_and_no_dead_anchors(self):
        self.uni.assert_intel_closed(self)
        self.uni.assert_target_paths_closed(self)
        self.uni.assert_no_dead_anchors(self)

    def test_per_ticker_enrichment_coverage_rendered(self):
        self.assertIn("Diligence-enrichment coverage", self.dq)
        for tk in ("IREN", "AAOI", "INOD"):
            self.assertIn(tk, self.dq)


# =========================================================================== #
# G. Guardrails: no new score/rank; optional/injectable; demo byte-identical;  #
#    offline (rows 32, 33, 34, 35)                                            #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _CHANGED = ("terrain_adapters.py", "real_terrain.py", "watchlist_terrain.py",
                "view_models.py", "render.py", "app.py")

    def test_no_new_score_rank_rating_function(self):
        for fn in self._CHANGED:
            tree = ast.parse(open(os.path.join(_UNIVERSE_UI_DIR, fn),
                                  encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    low = node.name.lower()
                    for banned in ("score", "rank", "rating"):
                        self.assertNotIn(banned, low,
                                         "{0}: {1}".format(fn, node.name))

    def test_no_numeric_investability_field_on_view_models(self):
        # No field is a score / rank / rating; a pre-existing ``investability_label`` is a
        # STRING label (allowed) but there is no numeric investability metric.
        for cls in (CandidateCardView, PlanetCandidateView):
            for f in dataclasses.fields(cls):
                low = f.name.lower()
                for banned in ("score", "rank", "rating"):
                    self.assertNotIn(banned, low, "{0}.{1}".format(cls.__name__, f.name))
                if "investab" in low:
                    self.assertEqual(f.type, "str",
                                     "investability field must be a label: {0}".format(f.name))
            # the new enrichment fields are label containers (tuples / str), never numbers
            for name, typ in (("enrichment_context", "Tuple[str, ...]"),
                              ("enrichment_coverage_line", "str"),
                              ("enrichment_gaps", "Tuple[str, ...]")):
                self.assertIn(name, cls.__dataclass_fields__)
                self.assertEqual(cls.__dataclass_fields__[name].type, typ)

    def test_demo_default_byte_identical_and_no_enrichment(self):
        d1 = tempfile.mkdtemp(prefix="enr011c_demo_a_")
        d2 = tempfile.mkdtemp(prefix="enr011c_demo_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in _PAGES:
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                             "demo not byte-identical: {0}".format(name))
        self.assertNotIn("Diligence-enrichment coverage",
                         _read(p1, "data_quality.html"))

    def test_real_single_and_watchlist_still_build_with_enrichment(self):
        d1 = tempfile.mkdtemp(prefix="enr011c_s_")
        p1 = build_universe_app(d1, mode="real_evidence_on_demand", ticker="IREN",
                                transports=_mock(), enrich=True, now=_NOW)
        self.assertTrue(os.path.exists(p1["universe.html"]))
        d2 = tempfile.mkdtemp(prefix="enr011c_w_")
        p2 = build_universe_app(d2, mode="real_evidence_on_demand",
                                transports_by_ticker=_tbt("IREN", "AAOI"),
                                enrich=True, now=_NOW)
        self.assertTrue(os.path.exists(p2["universe.html"]))

    def test_deterministic_enriched_real_build(self):
        d1 = tempfile.mkdtemp(prefix="enr011c_d1_")
        d2 = tempfile.mkdtemp(prefix="enr011c_d2_")
        p1 = build_universe_app(d1, mode="real_evidence_on_demand", ticker="IREN",
                                transports=_mock(), enrich=True, now=_NOW)
        p2 = build_universe_app(d2, mode="real_evidence_on_demand", ticker="IREN",
                                transports=_mock(), enrich=True, now=_NOW)
        for name in ("universe.html", "dashboard.html", "data_quality.html"):
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                             "non-deterministic: {0}".format(name))

    def test_enriched_build_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            d = tempfile.mkdtemp(prefix="enr011c_off_")
            build_universe_app(d, mode="real_evidence_on_demand", ticker="IREN",
                               transports=_mock(), enrich=True, now=_NOW)
        finally:
            socket.socket = real


if __name__ == "__main__":
    unittest.main()
