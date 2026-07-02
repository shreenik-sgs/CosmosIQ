"""IMPLEMENTATION-011A -- Investment Diligence Input Enrichment Foundation.

Everything here runs OFFLINE. The enrichment layer is exercised ONLY with in-process
fixtures + injected MOCK transports; no test reaches a real endpoint. The suite proves the
discipline the spec gates:

* enrichment models are EVIDENCE, not decisions -- no buy / sell / hold / order / trade /
  score / rank / rating field anywhere;
* source authority stays explicit and is not weakened -- SEC canonical > FMP convenience >
  yfinance fallback > manual / analyst; a manual TAM stays ``manual`` (never canonical); a
  company statement stays ``company_claim`` (never ``verified_fact``);
* unsupported fields become explicit DATA GAPS, never invented values;
* the enrichment overlay feeds terrain magnitudes via the EXISTING ``visual_size`` helper
  (no new metric), leaves demo byte-identical, and keeps real single / watchlist builds green;
* no scheduler / broker / order / scraping / network import in the new package, and no
  network in tests (socket kill-switch).
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
from dataclasses import fields, is_dataclass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import diligence_enrichment as de
from diligence_enrichment import (
    build_diligence_enrichment_bundle,
    build_enrichment_coverage,
)
from diligence_enrichment import models as de_models
from diligence_enrichment.source_contract import (
    authority_for_category,
    claim_status_for_category,
    manual_is_not_canonical,
)
from evidence_ingestion.source_model import authority_rank

from universe_ui.app import build_universe_app
from universe_ui.real_terrain import build_real_evidence_terrain_for_ticker
from universe_ui.terrain import (
    BottleneckNode,
    CompanyNode,
    GalaxyNode,
    ValueChainLayer,
    ValueChainNode,
)
from universe_ui.view_models import build_economic_universe_view
from universe_ui.render import render_data_quality

_FIXTURE_DIR = os.path.join(_ROOT, "tests", "fixtures", "slice")
_PKG_DIR = os.path.join(_SRC, "diligence_enrichment")
_NOW = 1750000000.0

_BANNED_FIELD_TOKENS = ("buy", "sell", "hold", "order", "trade", "score", "rank", "rating")

_THE_EIGHT = (
    de_models.CompanyDiligenceProfile,
    de_models.MarketAndValuationSnapshot,
    de_models.TAMRevenuePoolEstimate,
    de_models.ValueChainEvidenceProfile,
    de_models.BottleneckEvidenceProfile,
    de_models.CompanyIREvidenceProfile,
    de_models.LeadershipEvidenceProfile,
    de_models.DiligenceEnrichmentBundle,
)

_HELPER_MODELS = (
    de_models.EnrichmentValue,
    de_models.ValueChainLayerEvidence,
    de_models.LeadershipMember,
)


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _mock_transports():
    return {
        "sec_submissions": lambda tk: _load("sec_submissions_iren.json"),
        "sec_companyfacts": lambda tk: _load("sec_companyfacts_iren.json"),
        "fmp_profile": lambda tk: _load("fmp_profile_iren.json"),
        "fmp_income_statement": lambda tk: _load("fmp_income_statement_iren.json"),
        "fmp_ohlcv": lambda tk: _load("fmp_ohlcv_iren.json"),
        "fmp_news": lambda tk: _load("fmp_news_iren.json"),
        "fmp_ownership": lambda tk: _load("fmp_ownership_iren.json"),
    }


def _full_bundle(ticker="IREN"):
    """A richly-populated bundle (every area sourced) for the terrain / DQ tests."""
    return build_diligence_enrichment_bundle(
        ticker,
        sec_facts=_load("sec_companyfacts_iren.json"),
        fmp_profile=_load("fmp_profile_iren.json"),
        fmp_income=_load("fmp_income_statement_iren.json"),
        manual_tam={"amount": 5.0e10, "market": "AI data-center hosting",
                    "methodology": "top-down analyst view", "source": "analyst note 2026"},
        value_chain_fixture={
            "category": "investor_presentation", "chain_name": "AI compute hosting",
            "source_refs": ["IREN investor deck Q2-2026"],
            "layers": [
                {"label": "Power / grid", "sequence": 0, "companies": ["IREN"],
                 "suppliers": ["grid operator"], "bottleneck_exposure": "direct"},
                {"label": "Compute hosting", "sequence": 1, "companies": ["IREN"],
                 "customers": ["AI labs"]},
            ],
            "suppliers": ["grid operator"], "customers": ["AI labs"]},
        bottleneck_fixture={
            "category": "investor_presentation", "name": "Secured grid power",
            "bottleneck_type": "power_capacity", "severity": "acute",
            "expected_duration": "multi_year", "constrained_resource": "interconnect / power",
            "source_refs": ["IREN investor deck Q2-2026"]},
        ir_fixture={
            "investor_presentation_refs": ["IREN Q2-2026 deck"],
            "earnings_transcript_refs": ["IREN Q2-2026 call"],
            "guidance_statements": ["management targets 2GW contracted by 2027"],
            "disclosed_catalysts": ["new hosting contract"],
            "disclosed_risks": ["power interconnect delay"]},
        leadership_fixture={
            "members": [{"name": "Jane Doe", "role": "CEO", "since": "2019"}],
            "tenure_note": "founder-led", "source_refs": ["IREN IR site"]},
        now=_NOW)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# =========================================================================== #
# A. Models -- shape + provenance + NO decision field                         #
# =========================================================================== #
class ModelTests(unittest.TestCase):
    def test_all_eight_construct_trivially(self):
        for cls in _THE_EIGHT:
            obj = cls()
            self.assertTrue(is_dataclass(obj))

    def test_bundle_exposes_all_eight_areas(self):
        b = de_models.DiligenceEnrichmentBundle()
        for attr, cls in (
            ("profile", de_models.CompanyDiligenceProfile),
            ("market", de_models.MarketAndValuationSnapshot),
            ("tam_estimate", de_models.TAMRevenuePoolEstimate),
            ("value_chain", de_models.ValueChainEvidenceProfile),
            ("bottleneck", de_models.BottleneckEvidenceProfile),
            ("ir", de_models.CompanyIREvidenceProfile),
            ("leadership", de_models.LeadershipEvidenceProfile),
        ):
            self.assertIsInstance(getattr(b, attr), cls)

    def test_source_authority_is_explicit(self):
        b = _full_bundle()
        self.assertEqual(b.market.shares_outstanding.authority, "canonical")  # SEC
        self.assertEqual(b.market.market_cap.authority, "convenience")        # FMP
        self.assertEqual(b.tam_estimate.amount.authority, "manual")           # manual
        self.assertTrue(all(a in ("canonical", "primary", "convenience", "fallback", "manual")
                            for a in b.source_coverage))

    def test_company_claim_distinguishable_from_verified_fact(self):
        b = _full_bundle()
        # a company guidance statement is a company_claim, not a verified fact
        self.assertTrue(b.ir.guidance_statements)
        for g in b.ir.guidance_statements:
            self.assertEqual(g.claim_status, "company_claim")
            self.assertNotEqual(g.claim_status, "verified_fact")
        # a SEC financial fact IS a verified fact
        self.assertEqual(b.market.latest_revenue.claim_status, "verified_fact")

    def test_missing_fields_become_data_gaps(self):
        b = build_diligence_enrichment_bundle("AAOI")  # nothing supplied
        self.assertEqual(b.enrichment_status, "empty")
        joined = " ".join(b.data_gaps).lower()
        for area in ("market cap", "tam", "value-chain", "bottleneck", "ir", "leadership"):
            self.assertIn(area, joined)
        # nothing invented: no numeric magnitude present
        self.assertIsNone(b.market_cap_value)
        self.assertIsNone(b.tam_value)

    def test_no_decision_or_score_field_on_any_model(self):
        for cls in _THE_EIGHT + _HELPER_MODELS:
            for f in fields(cls):
                low = f.name.lower()
                for tok in _BANNED_FIELD_TOKENS:
                    self.assertNotIn(
                        tok, low,
                        "banned token {0!r} in field {1}.{2}".format(tok, cls.__name__, f.name))

    def test_confidence_label_is_a_label_not_a_number(self):
        b = _full_bundle()
        self.assertIsInstance(b.enrichment_status, str)
        self.assertIsInstance(b.profile.confidence_label, str)


# =========================================================================== #
# B. Fixture mapping -- SEC / FMP populate; missing -> gap; manual != canonical #
# =========================================================================== #
class FixtureMappingTests(unittest.TestCase):
    def test_fmp_profile_populates_company_profile(self):
        b = build_diligence_enrichment_bundle(
            "IREN", fmp_profile=_load("fmp_profile_iren.json"))
        self.assertEqual(b.profile.company_name.value, "IREN")
        self.assertEqual(b.profile.sector.value, "Technology")
        self.assertEqual(b.profile.sector.authority, "convenience")

    def test_market_cap_from_fmp_convenience(self):
        b = build_diligence_enrichment_bundle(
            "IREN", fmp_profile=_load("fmp_profile_iren.json"))
        self.assertEqual(b.market_cap_value, 4200000000.0)
        self.assertEqual(b.market.market_cap.authority, "convenience")

    def test_shares_and_revenue_prefer_sec_canonical(self):
        b = build_diligence_enrichment_bundle(
            "IREN", sec_facts=_load("sec_companyfacts_iren.json"),
            fmp_profile=_load("fmp_profile_iren.json"),
            fmp_income=_load("fmp_income_statement_iren.json"))
        # SEC canonical wins for shares + revenue even though FMP also carries them
        self.assertEqual(b.market.shares_outstanding.authority, "canonical")
        self.assertEqual(b.market.shares_outstanding.value, 210000000.0)
        self.assertEqual(b.market.latest_revenue.authority, "canonical")
        self.assertEqual(b.market.latest_revenue.value, 120000000.0)

    def test_revenue_falls_back_to_fmp_when_no_sec(self):
        b = build_diligence_enrichment_bundle(
            "IREN", fmp_income=_load("fmp_income_statement_iren.json"))
        self.assertEqual(b.market.latest_revenue.authority, "convenience")
        self.assertEqual(b.market.latest_revenue.value, 118000000.0)  # latest by date

    def test_each_unsupplied_area_is_a_gap(self):
        # only market data supplied -> tam / value-chain / bottleneck / ir / leadership gaps
        b = build_diligence_enrichment_bundle(
            "IREN", fmp_profile=_load("fmp_profile_iren.json"))
        self.assertFalse(b.tam_estimate.present)
        self.assertFalse(b.value_chain.present)
        self.assertFalse(b.bottleneck.present)
        self.assertFalse(b.ir.present)
        self.assertFalse(b.leadership.present)
        joined = " ".join(b.data_gaps).lower()
        self.assertIn("tam", joined)
        self.assertIn("value-chain", joined)
        self.assertIn("bottleneck", joined)
        self.assertIn("leadership", joined)

    def test_manual_tam_stays_manual_never_canonical(self):
        b = build_diligence_enrichment_bundle("IREN", manual_tam=7.5e10)
        self.assertEqual(b.tam_estimate.estimate_type, "manual")
        self.assertEqual(b.tam_estimate.amount.authority, "manual")
        self.assertNotEqual(b.tam_estimate.amount.authority, "canonical")
        self.assertEqual(b.tam_estimate.amount.claim_status, "manual")
        self.assertTrue(manual_is_not_canonical())
        self.assertLess(authority_rank("manual"), authority_rank("canonical"))

    def test_manual_authority_cannot_be_marked_canonical(self):
        with self.assertRaises(ValueError):
            de.assert_manual_not_canonical("canonical", "analyst_estimate")

    def test_company_statement_marked_company_claim(self):
        v = de_models.EnrichmentValue(value="we expect 2GW by 2027", authority="primary")
        marked = de.mark_company_claim(v)
        self.assertEqual(marked.claim_status, "company_claim")
        self.assertNotEqual(marked.claim_status, "verified_fact")

    def test_source_contract_authority_order_preserved(self):
        self.assertEqual(authority_for_category("sec_filing"), "canonical")
        self.assertEqual(authority_for_category("fmp"), "convenience")
        self.assertEqual(authority_for_category("yfinance"), "fallback")
        self.assertEqual(authority_for_category("manual"), "manual")
        self.assertGreater(authority_rank("canonical"), authority_rank("convenience"))
        self.assertGreater(authority_rank("convenience"), authority_rank("fallback"))
        self.assertEqual(claim_status_for_category("company_ir"), "company_claim")


# =========================================================================== #
# C. Terrain integration (enrichment feeds magnitudes via existing helper)     #
# =========================================================================== #
class TerrainIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enr = _full_bundle()
        cls.terrain, cls.status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock_transports(), enrichment=cls.enr, now=_NOW)
        cls.baseline, _ = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock_transports(), now=_NOW)  # no enrichment

    def _nodes(self, kind):
        return [n for _i, n in self.terrain.all_nodes() if isinstance(n, kind)]

    def test_market_cap_feeds_company_magnitude_and_size_basis(self):
        co = self._nodes(CompanyNode)[0]
        self.assertEqual(co.market_cap, 4200000000.0)
        self.assertIn("market_cap", co.visual_encoding.size_basis)
        self.assertIn("convenience", co.visual_encoding.size_basis)
        self.assertFalse(co.visual_encoding.dashed_outline)
        # size is the magnitude projection via the existing visual_size helper
        from universe_ui.view_models import visual_size
        self.assertEqual(co.visual_encoding.size_value, visual_size(4200000000.0, "planet"))

    def test_tam_feeds_galaxy_theme_and_value_chain_magnitude(self):
        from universe_ui.view_models import visual_size
        gx = self._nodes(GalaxyNode)[0]
        self.assertEqual(gx.economic_magnitude, 5.0e10)
        self.assertEqual(gx.visual_encoding.size_value, visual_size(5.0e10, "galaxy"))
        vc = self._nodes(ValueChainNode)[0]
        self.assertEqual(vc.revenue_pool_or_tam, 5.0e10)
        self.assertEqual(vc.visual_encoding.size_value, visual_size(5.0e10, "solar_system"))

    def test_value_chain_layers_populate(self):
        layers = self._nodes(ValueChainLayer)
        self.assertEqual(len(layers), 2)
        self.assertEqual([l.label for l in layers], ["Power / grid", "Compute hosting"])

    def test_bottleneck_severity_and_duration_populate(self):
        bn = self._nodes(BottleneckNode)[0]
        self.assertEqual(bn.severity, "acute")
        self.assertEqual(bn.expected_duration, "multi_year")
        self.assertFalse(bn.visual_encoding.dashed_outline)

    def test_missing_enrichment_stays_a_visible_gap(self):
        # baseline (no enrichment) keeps the honest neutral placeholders
        co = [n for _i, n in self.baseline.all_nodes() if isinstance(n, CompanyNode)][0]
        self.assertIsNone(co.market_cap)
        self.assertTrue(co.visual_encoding.dashed_outline)
        joined = " ".join(self.baseline.data_gaps).lower()
        self.assertIn("market cap not surfaced", joined)

    def test_enrichment_free_real_build_is_unchanged(self):
        # threading enrichment=None must not perturb the pre-011A terrain
        again, _ = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock_transports(), now=_NOW)
        self.assertEqual(again.data_gaps, self.baseline.data_gaps)

    def test_terrain_validates_and_has_no_centre(self):
        self.assertEqual(self.terrain.validate(), ())
        self.assertEqual(self.terrain.relationship_edges, ())

    def test_every_data_intel_resolves(self):
        # the 010F diagnostics still resolve over the enriched terrain (no orphan ids)
        from universe_ui.terrain_diagnostics import (
            build_terrain_diagnostics, diagnostics_by_object_id, single_ticker_run_summary)
        summary = single_ticker_run_summary(
            self.terrain, self.status, self.status["slice_result"])
        diag = build_terrain_diagnostics(self.terrain, summary)
        ann = diagnostics_by_object_id(self.terrain, diag)
        self.assertTrue(diag.per_ticker)
        # every STRUCTURAL node (galaxy / theme / value-chain / bottleneck / company) that
        # 010F annotates must resolve to a diagnostic annotation on the enriched terrain.
        structural = (GalaxyNode, ValueChainNode, BottleneckNode, CompanyNode)
        from universe_ui.terrain import ThemeNode
        structural = structural + (ThemeNode,)
        for nid, node in self.terrain.all_nodes():
            if nid and isinstance(node, structural):
                self.assertIn(nid, ann, "unresolved node id: {0}".format(nid))


# =========================================================================== #
# D. Data Quality enrichment coverage                                          #
# =========================================================================== #
class DataQualityCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        enr = _full_bundle()
        terrain, status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock_transports(), enrichment=enr, now=_NOW)
        slice_result = status.pop("slice_result")
        view = build_economic_universe_view(
            slice_result, terrain=terrain, source_status=status,
            enrichment_bundles=[enr])
        cls.html = render_data_quality(view.data_quality)
        cls.dq = view.data_quality

    def test_coverage_object_present(self):
        self.assertIsNotNone(self.dq.enrichment_coverage)

    def test_coverage_table_renders(self):
        self.assertIn("Diligence-enrichment coverage", self.html)
        for area in ("market cap", "TAM", "value chain", "bottleneck",
                     "company IR", "leadership"):
            self.assertIn(area, self.html)

    def test_per_ticker_gaps_render(self):
        self.assertIn("Enrichment gaps", self.html)
        self.assertIn("IREN", self.html)

    def test_data_actions_render_and_are_data_only(self):
        self.assertIn("Recommended DATA actions", self.html)
        low = self.html.lower()
        self.assertIsNone(re.search(r"\b(buy|sell)\b", low), "buy/sell token in DQ html")
        for banned in ("place order", "submit order", "trade now"):
            self.assertNotIn(banned, low)

    def test_authority_and_claim_status_shown(self):
        self.assertIn("convenience", self.html)   # market cap authority
        self.assertIn("manual", self.html)         # TAM authority
        self.assertIn("company_claim", self.html)  # IR claim status

    def test_no_secret_in_html(self):
        self.assertNotIn("apikey", self.html.lower())

    def test_coverage_none_without_bundles(self):
        # a real build WITHOUT enrichment bundles -> no coverage object, panel omitted
        terrain, status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock_transports(), now=_NOW)
        slice_result = status.pop("slice_result")
        view = build_economic_universe_view(
            slice_result, terrain=terrain, source_status=status)
        self.assertIsNone(view.data_quality.enrichment_coverage)
        html = render_data_quality(view.data_quality)
        self.assertNotIn("Diligence-enrichment coverage", html)


# =========================================================================== #
# E. Guardrails                                                                #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "beautifulsoup4", "selenium", "scrapy", "lxml", "mechanize", "pycurl"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib"}

    def _py_files(self):
        return [os.path.join(_PKG_DIR, f) for f in sorted(os.listdir(_PKG_DIR))
                if f.endswith(".py")]

    def test_new_package_imports_no_network_or_scraping(self):
        for path in self._py_files():
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [(node.module or "").split(".")[0]]
                for m in mods:
                    self.assertNotIn(m, self._NET,
                                     "{0} imports network/scraping {1}".format(path, m))

    def test_new_package_imports_no_scheduler_or_broker(self):
        for path in self._py_files():
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [(node.module or "").split(".")[0]]
                for m in mods:
                    self.assertNotIn(m, self._FORBIDDEN,
                                     "{0} imports forbidden {1}".format(path, m))

    def test_new_package_defines_no_scoring_or_ranking_function(self):
        for path in self._py_files():
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    low = node.name.lower()
                    self.assertNotIn("score", low, "{0}: {1}".format(path, node.name))
                    self.assertNotIn("rank", low, "{0}: {1}".format(path, node.name))
                    self.assertNotIn("buy", low)
                    self.assertNotIn("sell", low)

    def test_no_broker_or_order_affordance_in_package_source(self):
        blob = ""
        for path in self._py_files():
            blob += open(path, encoding="utf-8").read().lower()
        for banned in ("place_order", "submit_order", "broker.", "execute_trade",
                       "schedule.every", "cron"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_enrichment_build_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            b = _full_bundle()
            build_enrichment_coverage([b])
        finally:
            socket.socket = real
        self.assertEqual(b.market.market_cap.authority, "convenience")

    def test_real_build_with_enrichment_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            enr = _full_bundle()
            d = tempfile.mkdtemp(prefix="enr_real_")
            build_universe_app(d, mode="real_evidence_on_demand", ticker="IREN",
                               transports=_mock_transports(), enrichment=enr, now=_NOW)
        finally:
            socket.socket = real

    def test_demo_default_is_byte_identical(self):
        d1 = tempfile.mkdtemp(prefix="enr_demo_a_")
        d2 = tempfile.mkdtemp(prefix="enr_demo_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                             "demo not byte-identical: {0}".format(name))
        # demo never shows the enrichment coverage panel
        self.assertNotIn("Diligence-enrichment coverage",
                         open(p1["data_quality.html"], encoding="utf-8").read())

    def test_real_single_and_watchlist_modes_still_build(self):
        d1 = tempfile.mkdtemp(prefix="enr_single_")
        p1 = build_universe_app(d1, mode="real_evidence_on_demand", ticker="IREN",
                                transports=_mock_transports(), now=_NOW)
        self.assertTrue(os.path.exists(p1["universe.html"]))
        d2 = tempfile.mkdtemp(prefix="enr_wl_")
        p2 = build_universe_app(
            d2, mode="real_evidence_on_demand",
            transports_by_ticker={"IREN": _mock_transports(), "AAOI": _mock_transports()},
            now=_NOW)
        self.assertTrue(os.path.exists(p2["universe.html"]))

    def test_no_secret_in_real_enriched_html(self):
        secret = "FMPKEY-SHOULD-NOT-LEAK-011A"
        enr = _full_bundle()
        d = tempfile.mkdtemp(prefix="enr_leak_")
        paths = build_universe_app(
            d, mode="real_evidence_on_demand", ticker="IREN",
            transports=_mock_transports(), fmp_api_key=secret, enrichment=enr, now=_NOW)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            html = open(paths[name], encoding="utf-8").read()
            self.assertNotIn(secret, html)
            self.assertNotIn("apikey", html.lower())


if __name__ == "__main__":
    unittest.main()
