"""IMPLEMENTATION-011E -- End-to-End Integration Tests for the 011 Diligence-Research MVP.

Everything here runs OFFLINE and DETERMINISTICALLY (injected MOCK transports + an injected
``now``); no test reaches a real endpoint. This is the end-to-end matrix (TEST_MATRIX_011
rows 6, 9-36) proving BOTH honest paths through the SAME real single + watchlist pipeline:

* **A. Default / unenriched** (``enrich`` off): sparse & honest -- market cap / TAM /
  value-chain / bottleneck / IR / leadership all render as VISIBLE gaps + dashed/neutral
  encodings; nothing is fabricated; universe / dashboard / data-quality / cockpit build;
  every ``data-intel`` resolves; no dead anchors (reused 010G ``HtmlLinkGraph``); no demo
  galaxies leak; ``validate() == ()`` (no centre / edges); byte-identical build.
* **B. Enriched** (``enrich=True``): source-backed CompanyNode market cap + financials
  render with their authority PRESERVED (SEC canonical / FMP convenience / inferred
  margins); the Data-Quality enrichment-coverage panel + per-ticker gaps render; the cockpit
  shows a READ-ONLY enrichment note (broker order none, no trade action); TAM / value-chain /
  bottleneck / IR / leadership that are NOT source-backed STILL show as gaps; a manual TAM
  never becomes canonical; every ``data-intel`` resolves; no dead anchor / secret / new
  score-rank / buy-sell.
* **C. Scenario coverage** -- no-credentials, SEC-only, SEC+FMP (SEC wins overlap),
  multi-ticker watchlist, a failed ticker (recorded + visible, run continues), and each
  missing diligence area -> an explicit gap + a data-sourcing action (never a trade rec).
* **D. Full chain** (row 36) -- mock transports -> ingestion -> Tattva IA -> Sphurana OH ->
  diligence enrichment -> Nivesha (via the 011D ``to_nivesha_diligence_inputs`` +
  ``run_nivesha_thesis_on_enrichment``) -> Saarathi -> Kriya (manual execution PREVIEW;
  ``broker_order_id is None``) -> terrain -> render, single + watchlist. Thin evidence yields
  Nivesha's OWN limited / blocked thesis (never padded); a missing diligence input stops the
  chain at a VISIBLE gap; nothing is fabricated and no order is placed.
* **E. Global guardrails** (rows 28-35) -- whole suite offline under a socket block; no api
  key in any generated HTML; no ``.env`` / secret; no scheduler / broker; no
  buy/sell/order/submit affordance anywhere; no new ``def *score`` / ``*rank``; demo default
  byte-identical (and distinct from real); real single + watchlist still build; deterministic
  (two builds, same inputs + ``now``, byte-identical -- unenriched and enriched).

Structural assertions (link-graph / node / authority shape) are preferred over brittle
strings so the suite is not over-fitted.
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
_TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (_SRC, _TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from universe_ui.app import build_universe_app
from universe_ui.real_terrain import build_real_evidence_terrain_for_ticker
from universe_ui.terrain import (
    BottleneckNode,
    CatalystNode,
    CompanyNode,
    GalaxyNode,
    RiskNode,
    ValueChainLayer,
    ValueChainNode,
)
from universe_ui.view_models import visual_size

from diligence_enrichment import (
    build_diligence_enrichment_bundle,
    run_nivesha_thesis_on_enrichment,
    to_nivesha_diligence_inputs,
)
from diligence_enrichment.source_contract import manual_is_not_canonical

from prometheus.diligence_inputs import DiligenceInputs
from prometheus.investment_thesis import generate_investment_thesis
from runtime.vertical_slice_runner import iren_diligence_inputs
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.portfolio_snapshot import make_portfolio_snapshot

from test_terrain_interaction import HtmlLinkGraph  # reused 010G structural helper

_FIXTURE_DIR = os.path.join(_ROOT, "tests", "fixtures", "slice")
_UNIVERSE_UI_DIR = os.path.join(_SRC, "universe_ui")
_NOW = 1750000000.0
_PAGES = ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html")

_DEMO_GALAXIES = (
    "Data Centers", "Semiconductors", "Power & Grid", "Optics & Networking",
    "Nuclear & Energy", "Physical AI", "Robotics", "Space & Defense",
)

# Source-backed diligence fixtures used to prove the enriched path populates ONLY when
# evidence is supplied (and that a MANUAL TAM never becomes canonical).
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


# --------------------------------------------------------------------------- #
# Offline mock transports (real IREN fixtures; never a network call)          #
# --------------------------------------------------------------------------- #
def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _mock(*, with_sec=True, with_fmp=True):
    """A MOCK transport bundle returning the real IREN fixtures (fully offline).

    ``with_sec`` / ``with_fmp`` drop a source so the SEC-only / FMP-absent scenarios can be
    exercised without any network."""
    t = {
        "sec_submissions": lambda tk: _load("sec_submissions_iren.json"),
        "sec_companyfacts": lambda tk: _load("sec_companyfacts_iren.json"),
        "fmp_profile": lambda tk: _load("fmp_profile_iren.json"),
        "fmp_income_statement": lambda tk: _load("fmp_income_statement_iren.json"),
        "fmp_ohlcv": lambda tk: _load("fmp_ohlcv_iren.json"),
        "fmp_news": lambda tk: _load("fmp_news_iren.json"),
        "fmp_ownership": lambda tk: _load("fmp_ownership_iren.json"),
    }
    if not with_sec:
        t.pop("sec_submissions")
        t.pop("sec_companyfacts")
    if not with_fmp:
        for k in ("fmp_profile", "fmp_income_statement", "fmp_ohlcv", "fmp_news",
                  "fmp_ownership"):
            t.pop(k)
    return t


class _BrokenTransports:
    """A transport bundle that fails on access -- simulates a ticker whose fetch blows up.
    The watchlist must ISOLATE and RECORD it (visible), never silently drop it."""

    def get(self, *_a, **_k):
        raise RuntimeError("transport bundle unavailable (simulated fetch failure)")


def _tbt(*tickers, **mock_kw):
    return {tk: _mock(**mock_kw) for tk in tickers}


def _boom_socket(*_a, **_k):
    raise AssertionError("network access attempted")


def _read(paths, name):
    with open(paths[name], encoding="utf-8") as fh:
        return fh.read()


def _all_html(paths):
    return "\n".join(_read(paths, n) for n in _PAGES)


def _nodes(terrain, kind):
    return [n for _i, n in terrain.all_nodes() if isinstance(n, kind)]


def _companies(terrain):
    return _nodes(terrain, CompanyNode)


def _build_single(prefix, **kw):
    d = tempfile.mkdtemp(prefix=prefix)
    kw.setdefault("now", _NOW)
    return build_universe_app(d, mode="real_evidence_on_demand", ticker="IREN",
                              transports=_mock(), **kw)


def _build_watchlist(prefix, tickers, tbt, **kw):
    d = tempfile.mkdtemp(prefix=prefix)
    kw.setdefault("now", _NOW)
    return build_universe_app(d, mode="real_evidence_on_demand", tickers=tickers,
                              transports_by_ticker=tbt, **kw)


def _no_trade_affordance(tc, html):
    """Assert an HTML blob carries NO buy/sell/order/submit/broker affordance."""
    low = html.lower()
    for banned in ("<button", "<form", "onclick", 'type="submit"', "place order",
                   "place an order", "submit_order", "broker_order", "submit(",
                   "fetch(", "xmlhttprequest"):
        tc.assertNotIn(banned, low, "banned affordance: {0}".format(banned))
    tc.assertIsNone(re.search(r"\b(buy|sell)\b", low), "buy/sell token present")


# =========================================================================== #
# A. Default / UNENRICHED real + watchlist path -- honest & sparse            #
#    (rows 15-27, 33-35; unenriched half of 6/9-25)                           #
# =========================================================================== #
class DefaultUnenrichedPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.single = _build_single("e2e_A_s_")
        cls.wl = _build_watchlist("e2e_A_w_", ["IREN", "AAOI", "INOD"],
                                  _tbt("IREN", "AAOI", "INOD"))
        cls.uni = HtmlLinkGraph(_read(cls.single, "universe.html"))
        cls.wl_uni = HtmlLinkGraph(_read(cls.wl, "universe.html"))

    # -- terrain honesty (node level) --------------------------------------- #
    def test_market_cap_is_a_visible_dashed_gap_never_fabricated(self):
        terrain, _s = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), now=_NOW)  # enrich off (default)
        co = _companies(terrain)[0]
        self.assertIsNone(co.market_cap)                    # nothing invented
        self.assertTrue(co.visual_encoding.dashed_outline)  # dashed = missing magnitude
        self.assertEqual(co.visual_encoding.size_value, visual_size(None, "planet"))
        self.assertIn("market cap not surfaced", " ".join(terrain.data_gaps).lower())

    def test_tam_value_chain_bottleneck_leadership_all_gap_when_unenriched(self):
        terrain, _s = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), now=_NOW)
        gx = _nodes(terrain, GalaxyNode)[0]
        vc = _nodes(terrain, ValueChainNode)[0]
        self.assertIsNone(gx.economic_magnitude)          # no TAM invented
        self.assertTrue(gx.visual_encoding.dashed_outline)
        self.assertIsNone(vc.revenue_pool_or_tam)
        self.assertTrue(vc.visual_encoding.dashed_outline)
        self.assertEqual(_nodes(terrain, ValueChainLayer), [])  # no invented layers
        # IR-derived company_claim cards are absent when unenriched.
        self.assertEqual([c for c in _nodes(terrain, CatalystNode)
                          if "company_claim" in c.description], [])

    def test_all_four_pages_render_single_and_watchlist(self):
        for paths in (self.single, self.wl):
            for name in _PAGES:
                self.assertTrue(os.path.exists(paths[name]), name)

    def test_every_data_intel_resolves_no_dead_anchors_single_and_watchlist(self):
        for g in (self.uni, self.wl_uni):
            g.assert_intel_closed(self)
            g.assert_target_paths_closed(self)
            g.assert_parent_chains_reach_universe(self)
            g.assert_no_dead_anchors(self)

    def test_no_centre_no_edges_and_terrain_validates(self):
        terrain, _s = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), now=_NOW)
        self.assertEqual(terrain.validate(), ())
        self.assertEqual(terrain.relationship_edges, ())
        self.assertEqual(self.wl_uni.connector_classes(), [])

    def test_no_demo_galaxies_leak_into_real_build(self):
        blob = _all_html(self.single) + _all_html(self.wl)
        for demo in _DEMO_GALAXIES:
            self.assertNotIn(demo, blob, "demo galaxy leaked: {0}".format(demo))

    def test_data_quality_has_no_enrichment_panel_when_unenriched(self):
        # backward-compatible: the default real build carries no enrichment surface.
        self.assertNotIn("Diligence-enrichment coverage", _read(self.single, "data_quality.html"))
        self.assertNotIn("Diligence-enrichment coverage", _read(self.wl, "data_quality.html"))

    def test_unenriched_build_is_byte_identical_and_deterministic(self):
        a = _build_single("e2e_A_det_a_")
        b = _build_single("e2e_A_det_b_")
        for name in _PAGES:
            self.assertEqual(open(a[name], "rb").read(), open(b[name], "rb").read(),
                             "unenriched non-deterministic: {0}".format(name))

    def test_unenriched_differs_from_enriched_for_same_inputs(self):
        # the enrich switch is a real, visible difference (market cap is sourced) -- proving
        # A and B are genuinely distinct paths, not the same output.
        enriched = _build_single("e2e_A_vs_B_", enrich=True)
        self.assertNotEqual(open(self.single["universe.html"], "rb").read(),
                            open(enriched["universe.html"], "rb").read())
        self.assertNotIn("Diligence-enrichment coverage", _read(self.single, "data_quality.html"))
        self.assertIn("Diligence-enrichment coverage", _read(enriched, "data_quality.html"))

    def test_no_trade_affordance_or_secret_in_unenriched_build(self):
        _no_trade_affordance(self, _all_html(self.single) + _all_html(self.wl))


# =========================================================================== #
# B. ENRICHED real + watchlist path -- source-backed WITH gaps                #
#    (rows 6, 9-12, 15-25; enriched half)                                     #
# =========================================================================== #
class EnrichedPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.single = _build_single("e2e_B_s_", enrich=True)
        cls.wl = _build_watchlist("e2e_B_w_", ["IREN", "AAOI", "INOD"],
                                  _tbt("IREN", "AAOI", "INOD"), enrich=True)
        cls.uni = HtmlLinkGraph(_read(cls.single, "universe.html"))
        cls.wl_uni = HtmlLinkGraph(_read(cls.wl, "universe.html"))
        cls.dq = _read(cls.single, "data_quality.html")
        cls.wl_dq = _read(cls.wl, "data_quality.html")

    # -- source-backed magnitude + authority (node level) ------------------- #
    def test_market_cap_sourced_with_authority_and_undashed(self):
        terrain, _s = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), enrich=True, now=_NOW)
        co = _companies(terrain)[0]
        self.assertEqual(co.market_cap, 4200000000.0)                 # FMP mktCap, sourced
        enc = co.visual_encoding
        self.assertIn("market_cap", enc.size_basis)
        self.assertIn("convenience", enc.size_basis)                  # authority stamped
        self.assertFalse(enc.dashed_outline)                          # present -> un-dashed
        self.assertEqual(enc.size_value, visual_size(4200000000.0, "planet"))

    def test_financials_flow_to_nivesha_with_authority_preserved(self):
        # SEC canonical shares/revenue stay canonical; FMP-derived margins stay convenience.
        b = build_diligence_enrichment_bundle(
            "IREN", sec_facts=_load("sec_companyfacts_iren.json"),
            fmp_profile=_load("fmp_profile_iren.json"),
            fmp_income=_load("fmp_income_statement_iren.json"))
        _di, mapping = to_nivesha_diligence_inputs(b)
        by_field = {f.candidate_field: f for f in mapping.mapped_fields}
        self.assertEqual(by_field["shares_outstanding"].authority, "canonical")
        self.assertEqual(by_field["revenue"].authority, "canonical")
        self.assertEqual(by_field["gross_margin"].authority, "convenience")  # inferred margin
        self.assertEqual(by_field["gross_margin"].claim_status, "inferred")

    def test_data_quality_enrichment_coverage_and_per_ticker_gaps_render(self):
        self.assertIn("Diligence-enrichment coverage", self.dq)
        self.assertIn("convenience", self.dq)   # market cap authority surfaced
        self.assertIn("Diligence-enrichment coverage", self.wl_dq)
        for tk in ("IREN", "AAOI", "INOD"):
            self.assertIn(tk, self.wl_dq)

    def test_cockpit_shows_readonly_enrichment_note_broker_none_no_trade(self):
        ck = _read(self.single, "cockpit.html")
        self.assertIn("Diligence enrichment (read-only evidence)", ck)
        self.assertIn("broker record: none", ck.lower())
        _no_trade_affordance(self, ck)

    def test_unsupported_areas_still_gaps_source_backed_only(self):
        # enrich=True WITHOUT a source-backed TAM / value-chain / bottleneck / IR / leadership
        # keeps every one of them an honest gap -- enrichment adds evidence, not padding.
        terrain, status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), enrich=True, now=_NOW)
        enr = status["enrichment"]
        self.assertTrue(enr.has_market_cap())          # market cap IS source-backed
        self.assertFalse(enr.tam_estimate.present)     # ...but these are not
        self.assertFalse(enr.value_chain.present)
        self.assertFalse(enr.bottleneck.present)
        self.assertFalse(enr.ir.present)
        self.assertFalse(enr.leadership.present)
        gx = _nodes(terrain, GalaxyNode)[0]
        self.assertTrue(gx.visual_encoding.dashed_outline)     # TAM still dashed gap
        self.assertEqual(_nodes(terrain, ValueChainLayer), [])  # no layers invented
        low = " ".join(terrain.data_gaps).lower()
        self.assertIn("tam", low)
        self.assertIn("supplier", low)

    def test_manual_tam_is_shown_manual_never_canonical(self):
        terrain, _s = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), enrich=True, manual_tam=_MANUAL_TAM, now=_NOW)
        gx = _nodes(terrain, GalaxyNode)[0]
        self.assertEqual(gx.economic_magnitude, 5.0e10)   # manual TAM is used for magnitude
        basis = gx.visual_encoding.size_basis.lower()
        self.assertIn("manual", basis)
        self.assertNotIn("canonical", basis.replace("not canonical", ""))
        self.assertTrue(manual_is_not_canonical())

    def test_source_backed_areas_populate_only_when_evidence_supplied(self):
        # contrast: a fully-sourced bundle DOES populate value-chain layers + bottleneck.
        terrain, _s = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), enrich=True, value_chain_fixture=_VC_FIX,
            bottleneck_fixture=_BN_FIX, ir_fixture=_IR_FIX, now=_NOW)
        self.assertEqual([l.label for l in _nodes(terrain, ValueChainLayer)],
                         ["Power / grid", "Compute hosting"])
        bn = _nodes(terrain, BottleneckNode)[0]
        self.assertEqual(bn.severity, "acute")
        self.assertFalse(bn.visual_encoding.dashed_outline)
        cats = [c for c in _nodes(terrain, CatalystNode) if "company_claim" in c.description]
        self.assertTrue(any("new hosting contract" in c.description for c in cats))
        for c in cats:                                   # IR cards stay company_claim
            self.assertNotIn("verified_fact", c.description)

    def test_enriched_graph_closed_no_dead_anchors_no_secret(self):
        for g in (self.uni, self.wl_uni):
            g.assert_intel_closed(self)
            g.assert_target_paths_closed(self)
            g.assert_no_dead_anchors(self)
        _no_trade_affordance(self, _all_html(self.single) + _all_html(self.wl))
        for name in _PAGES:
            self.assertNotIn("apikey", _read(self.single, name).lower())

    def test_enriched_build_is_deterministic(self):
        a = _build_single("e2e_B_det_a_", enrich=True)
        b = _build_single("e2e_B_det_b_", enrich=True)
        for name in ("universe.html", "dashboard.html", "data_quality.html"):
            self.assertEqual(open(a[name], "rb").read(), open(b[name], "rb").read(),
                             "enriched non-deterministic: {0}".format(name))


# =========================================================================== #
# C. Scenario coverage -- credentials / source presence / failures / gaps     #
#    (rows 6, 10-14, 15-21)                                                   #
# =========================================================================== #
class ScenarioCoverageTests(unittest.TestCase):
    def test_no_credentials_single_visible_gap_no_leak_no_crash(self):
        # transports=None + no creds -> the live bundle wires nothing (no network) and records
        # credentials_missing; a killed socket proves nothing reached out.
        real = socket.socket
        socket.socket = _boom_socket
        try:
            terrain, status = build_real_evidence_terrain_for_ticker(
                "IREN", transports=None, sec_user_agent=None, fmp_api_key=None, now=_NOW)
        finally:
            socket.socket = real
        self.assertEqual(status["fmp"], "credentials_missing")
        self.assertEqual(status["sec"], "credentials_missing")
        joined = " ".join(terrain.data_gaps).lower()
        self.assertIn("fmp key missing", joined)
        self.assertIn("sec user-agent missing", joined)

    def test_no_credentials_watchlist_visible_gap_no_leak(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            paths = build_universe_app(
                tempfile.mkdtemp(prefix="e2e_C_noc_"), mode="real_evidence_on_demand",
                tickers=["IREN", "AAOI"], transports_by_ticker={"IREN": None, "AAOI": None},
                sec_user_agent=None, fmp_api_key=None, now=_NOW)
        finally:
            socket.socket = real
        dq = _read(paths, "data_quality.html")
        self.assertIn("FMP key missing", dq)
        self.assertIn("SEC User-Agent missing", dq)
        for name in _PAGES:
            self.assertNotIn("apikey", _read(paths, name).lower())

    def test_sec_only_fmp_absent_gaps_but_sec_canonical_populates(self):
        terrain, status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(with_fmp=False), enrich=True, now=_NOW)
        self.assertEqual(status["sec"], "fetched")
        self.assertEqual(status["fmp"], "unavailable")
        self.assertGreater(terrain.source_coverage.get("canonical", 0), 0)  # SEC canonical
        # FMP-only market cap is now a gap; nothing is invented for it.
        co = _companies(terrain)[0]
        self.assertIsNone(co.market_cap)
        self.assertTrue(co.visual_encoding.dashed_outline)

    def test_sec_plus_fmp_both_populate_and_sec_wins_overlap(self):
        terrain, status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), enable_yfinance=True, now=_NOW)
        res = status["slice_result"]
        overridden = res.provenance_chain["overridden_facts"]
        self.assertTrue(overridden, "expected FMP facts overridden by SEC")
        for f in overridden:
            self.assertEqual(f["source_authority"], "convenience")  # the loser is FMP
            self.assertIn("SEC", f["reason"])                       # SEC canonical wins
        self.assertGreater(terrain.source_coverage.get("canonical", 0), 0)

    def test_multi_ticker_watchlist_merges_three_companies_no_centre(self):
        paths = _build_watchlist("e2e_C_multi_", ["IREN", "AAOI", "INOD"],
                                 _tbt("IREN", "AAOI", "INOD"))
        g = HtmlLinkGraph(_read(paths, "universe.html"))
        planets = [p for p in g.panel_paths if "/pl:" in p]
        self.assertGreaterEqual(len(planets), 3)
        self.assertEqual(g.connector_classes(), [])   # merged, but no invented centre/hub edges

    def test_failed_ticker_recorded_visible_run_continues_not_dropped(self):
        tbt = {"IREN": _mock(), "BADX": _BrokenTransports(), "INOD": _mock()}
        paths = _build_watchlist("e2e_C_fail_", ["IREN", "BADX", "INOD"], tbt)
        dq = _read(paths, "data_quality.html")
        self.assertIn("BADX", dq)
        self.assertIn("failed", dq.lower())
        uni = _read(paths, "universe.html")
        self.assertIn("IREN", uni)     # the two good tickers still built
        self.assertIn("INOD", uni)

    def test_each_missing_area_is_an_explicit_gap_and_data_action_never_a_trade(self):
        # every unsupported diligence area surfaces as a data-sourcing gap in the coverage
        # panel -- and the panel carries NO trade recommendation.
        b = build_diligence_enrichment_bundle(
            "IREN", sec_facts=_load("sec_companyfacts_iren.json"),
            fmp_profile=_load("fmp_profile_iren.json"),
            fmp_income=_load("fmp_income_statement_iren.json"))  # market only; rest absent
        paths = build_universe_app(
            tempfile.mkdtemp(prefix="e2e_C_area_"), mode="real_evidence_on_demand",
            ticker="IREN", transports=_mock(), enrichment=b, now=_NOW)
        dq = _read(paths, "data_quality.html").lower()
        for area in ("tam", "value chain", "bottleneck", "company ir", "leadership",
                     "supplier"):
            self.assertIn(area, dq, "missing-area gap not surfaced: {0}".format(area))
        _no_trade_affordance(self, _read(paths, "data_quality.html"))
        # the adapter-level gaps confirm nothing is invented for those areas.
        _di, mapping = to_nivesha_diligence_inputs(b)
        self.assertEqual(mapping.mapped_fields and
                         [f for f in mapping.mapped_fields
                          if f.candidate_field == "value_chain_role"], [])


# =========================================================================== #
# D. Full chain (row 36): ingest -> IA -> OH -> enrich -> Nivesha -> Saarathi  #
#    -> Kriya preview -> terrain -> render; honest & gap-visible               #
# =========================================================================== #
class FullChainTests(unittest.TestCase):
    @classmethod
    def _full_single(cls, prefix, **kw):
        profile = make_personal_investment_profile("ACCT", actor="t", now=_NOW)
        portfolio = make_portfolio_snapshot(account="ACCT", actor="t", now=_NOW)
        return build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), enrich=True,
            diligence_inputs=iren_diligence_inputs(), profile=profile,
            portfolio=portfolio, user_selected_size=2000.0, now=_NOW, **kw)

    def test_every_stage_runs_and_kriya_is_a_manual_preview_only(self):
        terrain, status = self._full_single("e2e_D_full_")
        res = status["slice_result"]
        # Tattva -> Sphurana -> Nivesha -> Saarathi -> Kriya all present.
        self.assertIsNotNone(res.intelligence_assessment)        # Tattva IA
        self.assertIsNotNone(res.opportunity_hypothesis)         # Sphurana OH
        self.assertIsNotNone(res.investment_thesis)              # Nivesha
        self.assertIsNotNone(res.personalized_action)            # Saarathi
        self.assertIsNotNone(res.manual_execution_intent)
        ticket = res.manual_trade_ticket                         # Kriya PREVIEW
        self.assertIsNotNone(ticket)
        self.assertIsNone(ticket.broker_order_id)                # never placed
        self.assertEqual(ticket.state, "previewed")
        self.assertIsNotNone(res.cockpit_view)
        self.assertEqual(terrain.mode, "real_evidence_on_demand")

    def test_enrichment_to_nivesha_thin_evidence_yields_limited_thesis_not_padded(self):
        # the 011D handoff on the auto-built (thin) enrichment bundle -> Nivesha's own honest
        # limited/blocked thesis; NOT padded up to timing-confirmed.
        _terrain, status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), enrich=True, now=_NOW)
        bundle = status["enrichment"]
        oh = status["slice_result"].opportunity_hypothesis
        di, mapping = to_nivesha_diligence_inputs(bundle)
        thesis, _m = run_nivesha_thesis_on_enrichment(oh, bundle, now=_NOW)
        self.assertNotEqual(thesis.investability_assessment,
                            "thesis_worthy_timing_confirmed")
        self.assertFalse(thesis.timing_confirmation)
        self.assertEqual(thesis.asymmetry_summary.asymmetry_label, "undetermined")
        # the reason is VISIBLE as adapter gaps (missing price anchors), never hidden padding.
        self.assertTrue(any("bear_price" in g for g in mapping.gaps))
        # helper == calling Nivesha directly on the SAME adapted inputs (no drift).
        self.assertEqual(thesis, generate_investment_thesis(oh, di, now=_NOW))

    def test_full_chain_renders_and_has_no_order_affordance(self):
        d = tempfile.mkdtemp(prefix="e2e_D_render_")
        profile = make_personal_investment_profile("ACCT", actor="t", now=_NOW)
        portfolio = make_portfolio_snapshot(account="ACCT", actor="t", now=_NOW)
        paths = build_universe_app(
            d, mode="real_evidence_on_demand", ticker="IREN", transports=_mock(),
            enrich=True, diligence_inputs=iren_diligence_inputs(), profile=profile,
            portfolio=portfolio, user_selected_size=2000.0, now=_NOW)
        for name in _PAGES:
            self.assertTrue(os.path.exists(paths[name]))
        ck = _read(paths, "cockpit.html")
        self.assertIn("broker record: none", ck.lower())
        _no_trade_affordance(self, _all_html(paths))

    def test_chain_stops_at_a_visible_gap_when_diligence_input_missing(self):
        # no diligence inputs -> the chain STOPS at Nivesha with a visible gap; no thesis,
        # no Kriya ticket, nothing fabricated downstream.
        terrain, status = build_real_evidence_terrain_for_ticker(
            "IREN", transports=_mock(), enrich=True, now=_NOW)  # no diligence_inputs
        res = status["slice_result"]
        self.assertIsNotNone(res.opportunity_hypothesis)   # Sphurana still runs
        self.assertIsNone(res.investment_thesis)           # Nivesha gated off
        self.assertIsNone(res.manual_trade_ticket)         # no Kriya ticket
        gaps = " ".join(str(g).lower() for g in res.data_gaps)
        self.assertIn("thesis", gaps)
        self.assertIn("skipped", gaps)

    def test_full_chain_offline_and_watchlist_builds_with_no_broker_order(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            self._full_single("e2e_D_off_")
            paths = _build_watchlist("e2e_D_wl_", ["IREN", "AAOI", "INOD"],
                                     _tbt("IREN", "AAOI", "INOD"), enrich=True)
        finally:
            socket.socket = real
        # the watchlist path produces no ticket; where a slice has one it is a preview only.
        # (structurally: no order affordance anywhere, no broker order id leaked)
        _no_trade_affordance(self, _all_html(paths))
        self.assertNotIn("broker_order_id=", _all_html(paths).lower())


# =========================================================================== #
# E. Global guardrails (rows 28-35) -- re-run for the whole slice             #
# =========================================================================== #
class GlobalGuardrailTests(unittest.TestCase):
    def test_whole_e2e_build_runs_offline_under_a_socket_block(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            _build_single("e2e_E_off_s_", enrich=True)
            _build_watchlist("e2e_E_off_w_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                             enrich=True)
        finally:
            socket.socket = real

    def test_no_api_key_in_any_generated_html(self):
        secret = "E2E-SECRET-SHOULD-NOT-LEAK-2026"
        for enrich in (False, True):
            paths = _build_single("e2e_E_sec_", enrich=enrich, fmp_api_key=secret,
                                  sec_user_agent=secret)
            for name in _PAGES:
                html = _read(paths, name)
                self.assertNotIn(secret, html)
                self.assertNotIn("apikey", html.lower())

    def test_no_env_dotfile_or_secret_committed(self):
        # A real, gitignored .env in the working tree is EXPECTED once live sources
        # (SEC_USER_AGENT / FMP_API_KEY / ...) are configured; it cannot be committed.
        # The invariant is that no .env is COMMITTED (tracked by git) -- not that no
        # .env exists on disk.
        import subprocess
        try:
            out = subprocess.run(["git", "ls-files"], cwd=_ROOT,
                                  capture_output=True, text=True, timeout=30).stdout
        except Exception:  # pragma: no cover - git is present in this repo
            self.skipTest("git not available")
            return
        env_tracked = [p for p in out.splitlines()
                       if os.path.basename(p.strip()) == ".env"]
        self.assertEqual(env_tracked, [],
                         "a .env file is tracked by git: {0}".format(env_tracked))

    def test_no_buy_sell_order_submit_affordance_in_either_path(self):
        for enrich in (False, True):
            paths = _build_single("e2e_E_aff_s_", enrich=enrich)
            wl = _build_watchlist("e2e_E_aff_w_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                                  enrich=enrich)
            _no_trade_affordance(self, _all_html(paths) + _all_html(wl))

    def test_no_forbidden_marketing_wording(self):
        html = _all_html(_build_single("e2e_E_mkt_", enrich=True)).lower()
        for banned in ("fully live", "automated", "production ranking", "trade-ready",
                       "real-time", "real time"):
            self.assertNotIn(banned, html, "forbidden wording: {0}".format(banned))

    def test_this_e2e_suite_defines_no_new_investability_metric_function(self):
        # the 011E slice is TEST-only: it must introduce no product scoring/ranking surface.
        tree = ast.parse(open(os.path.abspath(__file__), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for banned in ("score", "rank", "rating"):
                    self.assertNotIn(banned, low, "banned fn: {0}".format(node.name))

    def test_no_scheduler_or_broker_module_touched_by_this_slice(self):
        # AST proof over the modules the E2E path drives: no scheduler / broker / automated
        # refresh import in the real-mode wiring exercised here.
        forbidden = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                     "multiprocessing"}
        for mod in ("app.py", "real_terrain.py", "watchlist_terrain.py"):
            tree = ast.parse(open(os.path.join(_UNIVERSE_UI_DIR, mod), encoding="utf-8").read())
            for node in ast.walk(tree):
                roots = []
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    roots = [(node.module or "").split(".")[0]]
                for r in roots:
                    self.assertNotIn(r, forbidden, "{0} imports {1}".format(mod, r))

    def test_demo_default_byte_identical_and_distinct_from_real(self):
        d1 = tempfile.mkdtemp(prefix="e2e_E_demo_a_")
        d2 = tempfile.mkdtemp(prefix="e2e_E_demo_b_")
        p1 = build_universe_app(d1)   # no mode -> demo default
        p2 = build_universe_app(d2)
        for name in _PAGES:
            self.assertEqual(open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                             "demo not byte-identical: {0}".format(name))
        self.assertIn("fixture/demo", _read(p1, "universe.html"))
        self.assertNotIn("Diligence-enrichment coverage", _read(p1, "data_quality.html"))
        # demo is DISTINCT from the real single build.
        real = _build_single("e2e_E_realcmp_")
        self.assertNotEqual(open(p1["universe.html"], "rb").read(),
                            open(real["universe.html"], "rb").read())

    def test_real_single_and_watchlist_still_build_both_modes(self):
        for enrich in (False, True):
            s = _build_single("e2e_E_single_", enrich=enrich)
            w = _build_watchlist("e2e_E_wl_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                                 enrich=enrich)
            self.assertTrue(os.path.exists(s["universe.html"]))
            self.assertTrue(os.path.exists(w["universe.html"]))

    def test_deterministic_both_paths_byte_identical(self):
        for enrich in (False, True):
            a = _build_single("e2e_E_det_a_", enrich=enrich)
            b = _build_single("e2e_E_det_b_", enrich=enrich)
            wa = _build_watchlist("e2e_E_wdet_a_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                                  enrich=enrich)
            wb = _build_watchlist("e2e_E_wdet_b_", ["IREN", "AAOI"], _tbt("IREN", "AAOI"),
                                  enrich=enrich)
            for name in ("universe.html", "dashboard.html", "data_quality.html"):
                self.assertEqual(open(a[name], "rb").read(), open(b[name], "rb").read(),
                                 "single non-deterministic ({0}): {1}".format(enrich, name))
                self.assertEqual(open(wa[name], "rb").read(), open(wb[name], "rb").read(),
                                 "watchlist non-deterministic ({0}): {1}".format(enrich, name))


if __name__ == "__main__":
    unittest.main()
