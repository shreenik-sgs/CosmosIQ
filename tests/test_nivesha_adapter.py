"""IMPLEMENTATION-011D -- Nivesha-ready INPUT adapter.

Proves the adapter maps a DiligenceEnrichmentBundle (011A/B/C) into the EXACT
``DiligenceInputs`` Nivesha consumes, WITHOUT changing Nivesha semantics and WITHOUT
fabricating anything. Covers TEST_MATRIX_011 row 9 (+ rows 2, 5, 7):

* only evidence-backed fields are mapped; ``source_refs`` + ``data_gaps`` are preserved;
* a missing area (no TAM / value-chain / bottleneck / leadership) stays an adapter GAP,
  never invented;
* manual / analyst inputs stay ``manual`` (never canonical); company statements stay
  ``company_claim``;
* the adapter defines NO ``*score`` / ``*rank`` function and no buy / sell / hold, and
  produces no thesis / strength;
* Nivesha semantics are unchanged -- the SAME adapted inputs give the SAME thesis as
  feeding Nivesha directly; a full-fixture input yields the accepted thesis, a thin input
  yields Nivesha's honest limited / blocked thesis (NOT a padded one);
* the whole path is OFFLINE (socket kill-switch) and NO prometheus source file is modified
  (git + AST proof).
"""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from reality_intelligence.source_observation import make_source_observation
from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis

from prometheus.diligence_inputs import CandidateInput, DiligenceInputs
from prometheus.investment_thesis import generate_investment_thesis

import diligence_enrichment as de
from diligence_enrichment import (
    build_diligence_enrichment_bundle,
    run_nivesha_thesis_on_enrichment,
    to_nivesha_diligence_inputs,
)
from diligence_enrichment.models import (
    DiligenceEnrichmentBundle,
    EnrichmentValue,
    MarketAndValuationSnapshot,
    ValueChainEvidenceProfile,
    ValueChainLayerEvidence,
)
from diligence_enrichment import nivesha_adapter as na

_DOMAIN = "ai-infrastructure"
_NOW = 0.0
_ADAPTER_FILE = os.path.join(_SRC, "diligence_enrichment", "nivesha_adapter.py")


# --------------------------------------------------------------------------- #
# Real upstream: build an Opportunity Hypothesis exactly as the pipeline does. #
# --------------------------------------------------------------------------- #
def _alpha_oh(now=_NOW):
    obs = [
        make_source_observation(
            source_type="earnings_excerpt", domain=_DOMAIN, entity="IREN",
            excerpt="contracted power capacity expanded quarter over quarter",
            signal_type_hint="readiness", metric_name="contracted_power_capacity_mw",
            metric_value=240.0, prior_value=200.0, metric_unit="MW", as_of="2026-Q1", now=now),
        make_source_observation(
            source_type="news_excerpt", domain=_DOMAIN, entity="IREN",
            excerpt="hyperscaler adoption of power-secured colocation is accelerating",
            observed_change="up", as_of="2026-06", now=now),
        make_source_observation(
            source_type="capacity_power_demand_signal", domain=_DOMAIN, entity="IREN",
            excerpt="available grid power is tightening as a binding constraint",
            observed_change="down", novelty="high", source_reliability="moderate",
            as_of="2026-06", now=now),
        make_source_observation(
            source_type="contract_win", domain=_DOMAIN, entity="IREN",
            excerpt="a multi-year power-capacity reservation was signed and announced",
            catalyst_type="capacity_reservation", catalyst_status="confirmed",
            expected_direction="positive", affected_value_chain_node="power/energy",
            expected_timing_window="next 2 quarters", as_of="2026-06", now=now),
    ]
    ia = generate_intelligence_assessment(obs, domain=_DOMAIN, now=now)
    return generate_opportunity_hypothesis([ia], domain=_DOMAIN, now=now)


def _alpha_candidate(**overrides):
    """The full hand-fed candidate Nivesha needs for a complete, accepted thesis."""
    base = dict(
        name="IREN", ticker="IREN",
        value_chain_role="secured-power capacity owner", tier=1,
        current_price=10.00, shares_outstanding=250_000_000.0,
        revenue=300.0, prior_revenue=200.0,
        gross_margin=0.55, prior_gross_margin=0.48,
        operating_margin=0.22, ebitda=120.0, fcf=-40.0, backlog=900.0,
        guidance="raise", capex=300.0, cash=400.0, debt=150.0,
        dilution_risk="low", convertible_debt=True,
        institutional_ownership=0.18, analyst_coverage=4, short_interest=0.07,
        float_shares=180_000_000.0, valuation_multiple=8.0,
        bear_price=8.00, base_price=14.00, bull_price=22.00, extreme_bull_price=35.00,
        ema9=10.10, ema20=9.70, ema50=9.00, ema200=7.50, ema_slopes_up=True,
        relative_strength=0.35, vwap=9.95, breakout_level=9.80, invalidation_level=9.00,
        price_above_breakout=True, base_duration_days=55, volatility_contracting=True,
        volume_recent=1_800_000.0, volume_avg=1_100_000.0,
    )
    base.update(overrides)
    return CandidateInput(**base)


def _ev(value, authority, claim_status):
    return EnrichmentValue(value=value, authority=authority, claim_status=claim_status,
                           source_refs=("evidence-ref",))


def _consistent_bundle():
    """A bundle whose financial magnitudes + value-chain role MATCH the alpha candidate,
    so overlaying it onto the operator base is numerically a no-op -- isolating the proof
    that the adapter injects no hidden padding."""
    mk = MarketAndValuationSnapshot(
        ticker="IREN",
        price=_ev(10.00, "convenience", "verified_fact"),
        shares_outstanding=_ev(250_000_000.0, "canonical", "verified_fact"),
        latest_revenue=_ev(300.0, "canonical", "verified_fact"),
        gross_margin=_ev(0.55, "convenience", "inferred"),
        op_margin=_ev(0.22, "convenience", "inferred"),
        cash=_ev(400.0, "convenience", "verified_fact"),
        debt=_ev(150.0, "convenience", "verified_fact"))
    vc = ValueChainEvidenceProfile(
        ticker="IREN", authority="primary", claim_status="company_claim",
        source_refs=("IREN deck",),
        layers=(ValueChainLayerEvidence(
            label="secured-power capacity owner", companies=("IREN",),
            authority="primary", claim_status="company_claim",
            source_refs=("IREN deck",)),))
    return DiligenceEnrichmentBundle(
        ticker="IREN", market=mk, value_chain=vc,
        data_gaps=("TAM not surfaced", "bottleneck evidence missing",
                   "leadership evidence missing"),
        provenance_refs=("SEC companyfacts fixture (IREN)",))


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# =========================================================================== #
# A. Evidence-only mapping + provenance preservation (row 9 core)              #
# =========================================================================== #
class MappingTests(unittest.TestCase):
    def test_returns_diligence_inputs_and_mapping_sidecar(self):
        di, mapping = to_nivesha_diligence_inputs(build_diligence_enrichment_bundle("IREN"))
        self.assertIsInstance(di, DiligenceInputs)
        self.assertIsInstance(mapping, na.NiveshaInputMapping)
        self.assertEqual(len(di.candidates), 1)
        self.assertEqual(di.candidates[0].ticker, "IREN")

    def test_only_evidence_backed_financials_are_mapped(self):
        b = build_diligence_enrichment_bundle(
            "IREN", sec_facts=_load("sec_companyfacts_iren.json"),
            fmp_profile=_load("fmp_profile_iren.json"),
            fmp_income=_load("fmp_income_statement_iren.json"))
        di, mapping = to_nivesha_diligence_inputs(b)
        c = di.candidates[0]
        # SEC canonical facts flow into the candidate...
        self.assertEqual(c.shares_outstanding, 210000000.0)
        self.assertEqual(c.revenue, 120000000.0)
        # ...FMP-derived margins flow in too (grossProfit / FMP revenue)...
        self.assertAlmostEqual(c.gross_margin, 60000000.0 / 118000000.0)
        # ...but nothing the fixtures never carried is invented.
        self.assertIsNone(c.bear_price)
        self.assertIsNone(c.bull_price)
        self.assertIsNone(c.ema9)
        self.assertIsNone(c.prior_revenue)
        self.assertEqual(c.value_chain_role, "")  # no value-chain evidence supplied

    def test_source_authority_preserved_on_each_mapped_field(self):
        b = build_diligence_enrichment_bundle(
            "IREN", sec_facts=_load("sec_companyfacts_iren.json"),
            fmp_profile=_load("fmp_profile_iren.json"),
            fmp_income=_load("fmp_income_statement_iren.json"))
        _di, mapping = to_nivesha_diligence_inputs(b)
        by_field = {f.candidate_field: f for f in mapping.mapped_fields}
        # SEC canonical stays canonical; FMP stays convenience -- never weakened/flattened.
        self.assertEqual(by_field["shares_outstanding"].authority, "canonical")
        self.assertEqual(by_field["shares_outstanding"].claim_status, "verified_fact")
        self.assertEqual(by_field["revenue"].authority, "canonical")
        self.assertEqual(by_field["gross_margin"].authority, "convenience")
        self.assertEqual(by_field["gross_margin"].claim_status, "inferred")
        # every mapped field carries its source_refs through.
        for f in mapping.mapped_fields:
            self.assertTrue(f.source_refs, "missing source_refs on {0}".format(f.candidate_field))

    def test_bundle_data_gaps_and_source_refs_preserved(self):
        b = _consistent_bundle()
        _di, mapping = to_nivesha_diligence_inputs(b)
        self.assertEqual(mapping.preserved_data_gaps, b.data_gaps)
        # provenance + per-area refs are carried through.
        self.assertIn("SEC companyfacts fixture (IREN)", mapping.preserved_source_refs)
        self.assertIn("IREN deck", mapping.preserved_source_refs)

    def test_value_chain_role_only_from_value_chain_evidence(self):
        # evidence naming IREN in a labelled layer -> role is mapped (evidence-backed).
        b = _consistent_bundle()
        di, mapping = to_nivesha_diligence_inputs(b)
        self.assertEqual(di.candidates[0].value_chain_role, "secured-power capacity owner")
        role_fields = [f for f in mapping.mapped_fields
                       if f.candidate_field == "value_chain_role"]
        self.assertEqual(len(role_fields), 1)
        self.assertEqual(role_fields[0].authority, "primary")
        self.assertEqual(role_fields[0].claim_status, "company_claim")


# =========================================================================== #
# B. Missing areas stay honest GAPS, never invented (rows 5, 7)                #
# =========================================================================== #
class GapTests(unittest.TestCase):
    def test_empty_bundle_maps_nothing_and_gaps_everything(self):
        di, mapping = to_nivesha_diligence_inputs(build_diligence_enrichment_bundle("AAOI"))
        c = di.candidates[0]
        self.assertEqual(c.ticker, "AAOI")
        # no numeric candidate field fabricated.
        for f in ("current_price", "revenue", "prior_revenue", "gross_margin",
                  "bear_price", "bull_price", "ema9", "cash", "debt"):
            self.assertIsNone(getattr(c, f), "{0} should be absent".format(f))
        self.assertEqual(c.value_chain_role, "")
        self.assertEqual(mapping.mapped_fields, ())
        joined = " ".join(mapping.gaps).lower()
        for area in ("value_chain_role", "current_price", "revenue", "bear_price",
                     "bull_price", "ema9", "dilution_risk"):
            self.assertIn(area.lower(), joined)

    def test_missing_tam_value_chain_bottleneck_leadership_are_gaps_not_invented(self):
        # only market financials supplied -> the qualitative areas stay absent.
        b = build_diligence_enrichment_bundle(
            "IREN", fmp_profile=_load("fmp_profile_iren.json"))
        di, mapping = to_nivesha_diligence_inputs(b)
        self.assertEqual(di.candidates[0].value_chain_role, "")  # no value-chain evidence
        self.assertFalse(b.tam_estimate.present)
        self.assertFalse(b.bottleneck.present)
        self.assertFalse(b.leadership.present)
        # the bundle's own area gaps ride along, and the adapter adds a value-chain gap.
        self.assertTrue(mapping.preserved_data_gaps)
        self.assertTrue(any("value_chain_role" in g for g in mapping.gaps))

    def test_dilution_default_none_is_recorded_as_a_gap_not_a_strong_value(self):
        # With no capital-structure evidence, dilution is NOT silently asserted 'none'
        # as an established fact -- it is flagged as unestablished.
        _di, mapping = to_nivesha_diligence_inputs(build_diligence_enrichment_bundle("IREN"))
        self.assertTrue(any(g.startswith("dilution_risk") for g in mapping.gaps))


# =========================================================================== #
# C. Manual stays manual; company statements stay company_claim (row 2, C)     #
# =========================================================================== #
class AuthorityDisciplineTests(unittest.TestCase):
    def test_operator_base_fields_stay_manual_never_canonical(self):
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        # a bundle that supplies NO financials -> the prices/EMAs come from the base.
        _di, mapping = to_nivesha_diligence_inputs(
            build_diligence_enrichment_bundle("IREN"), base_inputs=base)
        base_fields = [f for f in mapping.mapped_fields if f.authority == "manual"]
        self.assertTrue(base_fields)
        for f in base_fields:
            self.assertEqual(f.claim_status, "manual")
            self.assertNotEqual(f.authority, "canonical")
        # bear/bull/ema anchors are present as manual operator inputs.
        names = {f.candidate_field for f in base_fields}
        self.assertIn("bear_price", names)
        self.assertIn("bull_price", names)
        self.assertIn("ema9", names)

    def test_evidence_overlays_manual_for_the_same_field_evidence_outranks_manual(self):
        # base says revenue=300 (manual); SEC canonical says 120M -> canonical wins.
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        b = build_diligence_enrichment_bundle(
            "IREN", sec_facts=_load("sec_companyfacts_iren.json"))
        di, mapping = to_nivesha_diligence_inputs(b, base_inputs=base)
        self.assertEqual(di.candidates[0].revenue, 120000000.0)  # SEC canonical, not 300
        rev = [f for f in mapping.mapped_fields if f.candidate_field == "revenue"][0]
        self.assertEqual(rev.authority, "canonical")

    def test_company_statements_stay_company_claim(self):
        b = _consistent_bundle()
        _di, mapping = to_nivesha_diligence_inputs(b)
        role = [f for f in mapping.mapped_fields
                if f.candidate_field == "value_chain_role"][0]
        self.assertEqual(role.claim_status, "company_claim")
        self.assertNotEqual(role.claim_status, "verified_fact")


# =========================================================================== #
# D. Adapter creates NO thesis / score / rank / buy-sell (row 9 discipline)    #
# =========================================================================== #
class NoDecisionSurfaceTests(unittest.TestCase):
    _BANNED_FN = ("score", "rank", "rating", "buy", "sell", "thesis_strength")

    def test_adapter_module_defines_no_score_rank_or_thesis_function(self):
        tree = ast.parse(_read(_ADAPTER_FILE))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in self._BANNED_FN:
                    self.assertNotIn(tok, low, "banned fn token {0}: {1}".format(tok, node.name))
                # the ONLY function that names 'thesis' is the thin Nivesha runner, and it
                # returns Nivesha's thesis unchanged -- it never computes a strength.
                if "thesis" in low:
                    self.assertEqual(node.name, "run_nivesha_thesis_on_enrichment")

    def test_mapping_dataclasses_carry_no_decision_field(self):
        from dataclasses import fields
        banned = ("buy", "sell", "hold", "order", "trade", "score", "rank",
                  "rating", "allocat", "position", "size", "verdict", "investab")
        for cls in (na.MappedField, na.NiveshaInputMapping):
            for f in fields(cls):
                for tok in banned:
                    self.assertNotIn(tok, f.name.lower(),
                                     "banned field {0} on {1}".format(f.name, cls.__name__))

    def test_adapter_return_has_no_investability_or_strength_attribute(self):
        di, mapping = to_nivesha_diligence_inputs(_consistent_bundle())
        for bad in ("investability", "thesis", "strength", "score", "rank", "verdict",
                    "recommendation", "buy", "sell", "hold"):
            self.assertFalse(hasattr(mapping, bad),
                             "mapping must not expose {0}".format(bad))
            self.assertFalse(hasattr(di, bad))

    def test_adapter_source_names_no_broker_or_order_affordance(self):
        blob = _read(_ADAPTER_FILE).lower()
        for banned in ("place_order", "submit_order", "broker.", "execute_trade",
                       "buy(", "sell(", "generate_investment_thesis(oh"):
            self.assertNotIn(banned, blob)


# =========================================================================== #
# E. Nivesha semantics UNCHANGED: same inputs -> same thesis; no padding       #
# =========================================================================== #
class SemanticsPreservedTests(unittest.TestCase):
    def test_same_adapted_inputs_give_same_thesis_as_calling_nivesha_directly(self):
        oh = _alpha_oh()
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        di, _mapping = to_nivesha_diligence_inputs(_consistent_bundle(), base_inputs=base)
        # helper path == calling accepted Nivesha directly on the SAME adapted inputs.
        t_helper, _m = run_nivesha_thesis_on_enrichment(
            oh, _consistent_bundle(), base_inputs=base, now=_NOW)
        t_direct = generate_investment_thesis(oh, di, now=_NOW)
        self.assertEqual(t_helper, t_direct)

    def test_full_fixture_input_yields_the_accepted_thesis(self):
        oh = _alpha_oh()
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        di, _mapping = to_nivesha_diligence_inputs(_consistent_bundle(), base_inputs=base)
        t_adapter = generate_investment_thesis(oh, di, now=_NOW)
        # and it is IDENTICAL to feeding the operator base straight to Nivesha -- the
        # consistent evidence overlay adds no padding, only provenance.
        t_base = generate_investment_thesis(oh, base, now=_NOW)
        self.assertEqual(t_adapter.investability_assessment,
                         "thesis_worthy_timing_confirmed")
        self.assertEqual(t_adapter, t_base)

    def test_thin_input_yields_nivesha_honest_limited_thesis_not_padded(self):
        oh = _alpha_oh()
        di, mapping = to_nivesha_diligence_inputs(build_diligence_enrichment_bundle("IREN"))
        t = generate_investment_thesis(oh, di, now=_NOW)
        # the honest, gated outcome of thin inputs -- NOT padded up to timing-confirmed.
        self.assertNotEqual(t.investability_assessment, "thesis_worthy_timing_confirmed")
        self.assertFalse(t.timing_confirmation)
        self.assertEqual(t.asymmetry_summary.asymmetry_label, "undetermined")
        # the reason is visible as adapter gaps, not hidden.
        self.assertTrue(any("bear_price" in g for g in mapping.gaps))

    def test_adapter_does_not_mutate_base_inputs(self):
        import copy
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        snap = copy.deepcopy(base)
        to_nivesha_diligence_inputs(_consistent_bundle(), base_inputs=base)
        self.assertEqual(base, snap)


# =========================================================================== #
# F. Offline + prometheus untouched (row 9 enforcement)                        #
# =========================================================================== #
class OfflineAndImmutabilityTests(unittest.TestCase):
    def test_adapter_path_is_offline(self):
        oh = _alpha_oh()
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        real = socket.socket
        socket.socket = _boom_socket
        try:
            di, mapping = to_nivesha_diligence_inputs(_consistent_bundle(), base_inputs=base)
            t, _m = run_nivesha_thesis_on_enrichment(
                oh, _consistent_bundle(), base_inputs=base, now=_NOW)
        finally:
            socket.socket = real
        self.assertEqual(di.candidates[0].ticker, "IREN")
        self.assertEqual(t.investability_assessment, "thesis_worthy_timing_confirmed")

    def test_adapter_imports_no_network_or_scheduler(self):
        net = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
               "bs4", "selenium", "scrapy", "lxml", "sched", "asyncio", "subprocess",
               "threading", "multiprocessing", "smtplib", "ftplib"}
        tree = ast.parse(_read(_ADAPTER_FILE))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [(node.module or "").split(".")[0]]
            for m in mods:
                self.assertNotIn(m, net, "adapter imports forbidden module {0}".format(m))

    def test_no_prometheus_source_file_modified(self):
        # git proof: nothing under src/prometheus is changed by this build slice.
        res = subprocess.run(
            ["git", "status", "--porcelain", "--", "src/prometheus"],
            cwd=_ROOT, capture_output=True, text=True)
        self.assertEqual(res.stdout.strip(), "",
                         "prometheus/ must be untouched, got: {0}".format(res.stdout))

    def test_adapter_only_imports_prometheus_input_types_not_reasoning(self):
        # AST proof: at module load the adapter imports ONLY the input types; the reasoning
        # entrypoint is imported lazily inside the runner helper, never at module scope.
        tree = ast.parse(_read(_ADAPTER_FILE))
        top_level_prom = []
        for node in tree.body:  # module-scope statements only
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("prometheus"):
                top_level_prom.append(node.module)
        self.assertEqual(top_level_prom, ["prometheus.diligence_inputs"])


def _load(name):
    import json
    with open(os.path.join(_ROOT, "tests", "fixtures", "slice", name),
              "r", encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    unittest.main()
