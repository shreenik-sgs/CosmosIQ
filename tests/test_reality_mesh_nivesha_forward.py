"""IMPLEMENTATION-012I -- Nivesha Forward Scenario Engine / adapter (INPUT SIDECAR).

Proves the forward-scenario objects are evidence-backed INPUTS, not a thesis/decision, and
that the sidecar adapter maps ONLY evidence-established forward inputs into Nivesha's bare
``DiligenceInputs`` while keeping ALL provenance in the returned sidecar. Covers
TEST_MATRIX_012 §F (F1/F2/F3) plus the global guardrails (§I):

* an NRE / design-win fixture creates a ForwardScenarioInput; base/upside/downside/delay/
  dilution/failure cases are assembled from evidence-backed inputs only (F1);
* a missing production-ramp assumption creates a DATA GAP, never a fabricated value;
* company guidance stays ``company_claim`` (never ``verified_fact``); a manual assumption
  stays ``manual`` / analyst (never canonical); a ``target_price`` without a source/manual
  label is REJECTED; a target price is NEVER laundered into a Nivesha price field;
* the packet is handed to Nivesha as an INPUT sidecar and Nivesha's accepted gauntlet runs
  UNCHANGED -- insufficient inputs give an honest LIMITED thesis, not a padded one (F2);
* the adapter creates NO new score / rank / thesis / buy-sell; red-team / timing survive as
  labels (F3); no object carries a trade field;
* the whole path is OFFLINE (socket kill-switch); the module imports no net/scheduler/broker
  and defines no ``*score`` / ``*rank`` function (AST); ``src/prometheus/*`` is byte-unchanged
  (git-assert 0 files); demo default byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from dataclasses import fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from reality_intelligence.source_observation import make_source_observation
from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis

from prometheus.diligence_inputs import CandidateInput, DiligenceInputs
from prometheus.investment_thesis import generate_investment_thesis

from reality_mesh.models import OpportunityHypothesisPacket
from reality_mesh import nivesha_forward as nf
from reality_mesh.nivesha_forward import (
    ForwardScenarioInput,
    ForwardScenarioCase,
    ForwardScenarioPacket,
    ForwardMappedField,
    ForwardSidecarMapping,
    FORWARD_INPUT_NAMES,
    SCENARIO_LABELS,
    build_forward_scenario_packet,
    to_nivesha_forward_sidecar,
    run_nivesha_thesis_on_forward_sidecar,
)
from reality_mesh.validation import assert_no_trade_fields

_DOMAIN = "ai-infrastructure"
_NOW = 0.0
_MODULE_FILE = os.path.join(_SRC, "reality_mesh", "nivesha_forward.py")


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


def _hypothesis():
    return OpportunityHypothesisPacket(
        hypothesis_id="OH-IREN-1",
        opportunity_summary="secured-power capacity owner benefits from grid-power bottleneck",
        beneficiary_candidates=("IREN",),
        evidence_refs=("mesh-signal-ref",),
        supporting_evidence_refs=("IREN contract-win",),
        source_refs=("SEC 8-K (IREN)",),
        confidence_label="moderate")


def _nre():
    return ForwardScenarioInput(
        name="nre_revenue", value_or_label=50.0, source_authority="primary",
        claim_status="company_claim", evidence_refs=("IREN deck",), is_company_guidance=True)


def _design_win():
    return ForwardScenarioInput(
        name="design_wins", value_or_label="3 tier-1 hyperscaler design wins",
        source_authority="primary", claim_status="company_claim",
        evidence_refs=("IREN deck",), is_company_guidance=True)


def _backlog(value=900.0):
    return ForwardScenarioInput(
        name="backlog", value_or_label=value, source_authority="canonical",
        claim_status="verified_fact", evidence_refs=("SEC 10-K (IREN)",))


def _dilution(label="low", **kw):
    return ForwardScenarioInput(name="dilution_risk", value_or_label=label, **kw)


def _consistent_packet():
    """A base case whose backlog + dilution MATCH the alpha candidate, so overlaying is a
    numeric no-op -- isolating the proof that the adapter injects no padding."""
    base = (_nre(), _design_win(), _backlog(900.0),
            _dilution("low", source_authority="primary", claim_status="company_claim",
                      evidence_refs=("IREN deck",), is_company_guidance=True))
    return build_forward_scenario_packet(
        ticker="IREN", hypothesis=_hypothesis(), inputs={"base": base})


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# =========================================================================== #
# A. Forward inputs / cases assembled from evidence-backed inputs only (F1)     #
# =========================================================================== #
class ForwardInputTests(unittest.TestCase):
    def test_nre_and_design_win_fixture_create_forward_inputs(self):
        nre = _nre()
        self.assertEqual(nre.name, "nre_revenue")
        self.assertIn("nre_revenue", FORWARD_INPUT_NAMES)
        self.assertTrue(nre.present)
        self.assertEqual(_design_win().name, "design_wins")

    def test_packet_assembles_all_scenario_cases(self):
        pkt = _consistent_packet()
        self.assertEqual(pkt.scenario_labels(), SCENARIO_LABELS)
        self.assertEqual(
            set(SCENARIO_LABELS),
            {"base", "upside", "downside", "delay", "dilution", "failure"})
        base = pkt.case("base")
        self.assertIn("nre_revenue", base.input_names())
        self.assertIn("design_wins", base.input_names())

    def test_only_evidence_backed_inputs_are_in_a_case(self):
        # a case only contains the inputs genuinely supplied -- nothing invented.
        pkt = _consistent_packet()
        upside = pkt.case("upside")
        self.assertEqual(upside.inputs, ())  # no upside evidence supplied -> empty, not padded
        self.assertTrue(upside.data_gaps)     # ...and every expected assumption is a gap

    def test_packet_preserves_evidence_refs_and_provenance(self):
        pkt = _consistent_packet()
        self.assertIn("mesh-signal-ref", pkt.evidence_refs)
        self.assertIn("IREN deck", pkt.evidence_refs)
        self.assertIn("SEC 8-K (IREN)", pkt.source_refs)
        self.assertEqual(pkt.hypothesis_ref, "OH-IREN-1")


# =========================================================================== #
# B. Missing assumption -> DATA GAP, never fabricated                          #
# =========================================================================== #
class GapTests(unittest.TestCase):
    def test_missing_production_ramp_is_a_gap_not_a_value(self):
        pkt = _consistent_packet()
        base = pkt.case("base")
        # production_ramp was never supplied -> it is an explicit gap, not fabricated.
        self.assertNotIn("production_ramp", base.input_names())
        self.assertTrue(any("production_ramp" in g for g in base.data_gaps))
        # and it rolls up onto the packet.
        self.assertTrue(any("production_ramp" in g for g in pkt.data_gaps))

    def test_empty_packet_gaps_everything_and_maps_nothing(self):
        pkt = build_forward_scenario_packet(ticker="AAOI")
        di, mapping = to_nivesha_forward_sidecar(pkt)
        c = di.candidates[0]
        self.assertEqual(c.ticker, "AAOI")
        self.assertIsNone(c.backlog)              # nothing fabricated
        self.assertEqual(c.dilution_risk, "none")  # Nivesha's own absent default
        self.assertEqual(mapping.mapped_fields, ())
        joined = " ".join(mapping.gaps)
        for name in ("nre_revenue", "design_wins", "production_ramp", "backlog",
                     "future_gross_margin", "dilution_risk"):
            self.assertIn(name, joined)

    def test_adapter_gaps_list_every_unestablished_assumption(self):
        # only backlog established -> every OTHER expected assumption is a gap.
        pkt = build_forward_scenario_packet(ticker="IREN", inputs={"base": (_backlog(),)})
        _di, mapping = to_nivesha_forward_sidecar(pkt)
        gap_blob = " ".join(mapping.gaps)
        for name in ("nre_revenue", "design_wins", "pre_production_contracts",
                     "production_ramp", "pipeline_conversion", "capacity_expansion",
                     "future_gross_margin", "operating_leverage", "future_share_count"):
            self.assertIn(name, gap_blob)
        # backlog was established -> it is NOT listed as an absent gap.
        self.assertFalse(any(g.startswith("backlog: absent") for g in mapping.gaps))


# =========================================================================== #
# C. Manual stays manual; guidance stays company_claim; target_price guarded    #
# =========================================================================== #
class AuthorityDisciplineTests(unittest.TestCase):
    def test_company_guidance_stays_company_claim_never_verified_fact(self):
        nre = _nre()
        self.assertEqual(nre.claim_status, "company_claim")
        self.assertNotEqual(nre.claim_status, "verified_fact")
        with self.assertRaises(ValueError):
            ForwardScenarioInput(
                name="nre_revenue", value_or_label=50.0, is_company_guidance=True,
                claim_status="verified_fact")

    def test_manual_assumption_stays_manual_never_canonical(self):
        man = _dilution("moderate", is_manual=True, evidence_refs=("analyst note",))
        self.assertEqual(man.source_authority, "manual")
        self.assertEqual(man.claim_status, "manual")
        self.assertNotEqual(man.source_authority, "canonical")
        # a manual assumption may never be stamped canonical.
        with self.assertRaises(ValueError):
            ForwardScenarioInput(
                name="dilution_risk", value_or_label="high", is_manual=True,
                source_authority="canonical")

    def test_manual_datum_marked_canonical_is_rejected(self):
        with self.assertRaises(ValueError):
            ForwardScenarioInput(
                name="future_gross_margin", value_or_label=0.6,
                source_authority="canonical", claim_status="manual")

    def test_target_price_without_source_or_manual_label_is_rejected(self):
        with self.assertRaises(ValueError):
            ForwardScenarioInput(name="target_price", value_or_label=25.0)
        # a rumor-authority "source" does not count as source-backed.
        with self.assertRaises(ValueError):
            ForwardScenarioInput(
                name="target_price", value_or_label=25.0, source_authority="rumor",
                evidence_refs=("some tweet",))

    def test_target_price_with_manual_or_source_label_is_accepted(self):
        manual_tp = ForwardScenarioInput(
            name="target_price", value_or_label=25.0, is_manual=True)
        self.assertEqual(manual_tp.claim_status, "manual")
        sourced_tp = ForwardScenarioInput(
            name="target_price", value_or_label=25.0, source_authority="primary",
            claim_status="analyst_estimate", evidence_refs=("analyst report",))
        self.assertTrue(sourced_tp.present)

    def test_mapped_field_provenance_preserved_and_not_laundered(self):
        pkt = _consistent_packet()
        _di, mapping = to_nivesha_forward_sidecar(pkt)
        by_field = {f.candidate_field: f for f in mapping.mapped_fields}
        self.assertEqual(by_field["backlog"].authority, "canonical")
        self.assertEqual(by_field["backlog"].claim_status, "verified_fact")
        self.assertEqual(by_field["dilution_risk"].claim_status, "company_claim")
        for f in mapping.mapped_fields:
            self.assertTrue(f.evidence_refs, "missing evidence_refs on {0}".format(f.candidate_field))

    def test_target_price_is_never_pushed_into_a_nivesha_price_field(self):
        tp = ForwardScenarioInput(
            name="target_price", value_or_label=25.0, is_manual=True)
        pkt = build_forward_scenario_packet(
            ticker="IREN", inputs={"base": (tp, _backlog())})
        di, mapping = to_nivesha_forward_sidecar(pkt)
        c = di.candidates[0]
        # no target price laundered into ANY Nivesha price field.
        for pf in ("bear_price", "base_price", "bull_price", "extreme_bull_price",
                   "current_price"):
            self.assertIsNone(getattr(c, pf), "{0} was laundered from target_price".format(pf))
        # target_price never appears as a mapped candidate field.
        self.assertFalse(any(f.candidate_field.endswith("price")
                             for f in mapping.mapped_fields))
        self.assertTrue(any("target_price" in g for g in mapping.gaps))


# =========================================================================== #
# D. Sidecar adapter: Nivesha inputs bare, provenance in the sidecar            #
# =========================================================================== #
class SidecarTests(unittest.TestCase):
    def test_returns_diligence_inputs_and_sidecar_mapping(self):
        di, mapping = to_nivesha_forward_sidecar(_consistent_packet())
        self.assertIsInstance(di, DiligenceInputs)
        self.assertIsInstance(mapping, ForwardSidecarMapping)
        self.assertEqual(len(di.candidates), 1)
        self.assertEqual(di.candidates[0].ticker, "IREN")

    def test_only_mappable_forward_inputs_reach_nivesha_bare_inputs(self):
        di, _m = to_nivesha_forward_sidecar(_consistent_packet())
        c = di.candidates[0]
        # backlog + dilution_risk have an honest home and are mapped...
        self.assertEqual(c.backlog, 900.0)
        self.assertEqual(c.dilution_risk, "low")
        # ...but NRE / design wins / margin projections are NOT laundered onto the candidate.
        self.assertIsNone(c.revenue)
        self.assertIsNone(c.gross_margin)
        self.assertIsNone(c.current_price)

    def test_provenance_stays_in_sidecar_not_in_bare_inputs(self):
        _di, mapping = to_nivesha_forward_sidecar(_consistent_packet())
        # the bare candidate carries NO authority/claim/evidence slot; the sidecar does.
        self.assertTrue(mapping.mapped_fields)
        self.assertIn("mesh-signal-ref", mapping.preserved_evidence_refs)
        self.assertTrue(mapping.preserved_data_gaps)
        self.assertEqual(mapping.scenario_labels, SCENARIO_LABELS)

    def test_base_inputs_are_not_mutated(self):
        import copy
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        snap = copy.deepcopy(base)
        to_nivesha_forward_sidecar(_consistent_packet(), base_inputs=base)
        self.assertEqual(base, snap)


# =========================================================================== #
# E. Nivesha semantics UNCHANGED: sidecar in, honest (not padded) thesis out    #
# =========================================================================== #
class SemanticsPreservedTests(unittest.TestCase):
    def test_helper_equals_calling_nivesha_directly_on_same_adapted_inputs(self):
        oh = _alpha_oh()
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        di, _m = to_nivesha_forward_sidecar(_consistent_packet(), base_inputs=base)
        t_helper, _mp = run_nivesha_thesis_on_forward_sidecar(
            oh, _consistent_packet(), base_inputs=base, now=_NOW)
        t_direct = generate_investment_thesis(oh, di, now=_NOW)
        self.assertEqual(t_helper, t_direct)

    def test_consistent_forward_overlay_adds_no_padding(self):
        oh = _alpha_oh()
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        di, _m = to_nivesha_forward_sidecar(_consistent_packet(), base_inputs=base)
        t_adapter = generate_investment_thesis(oh, di, now=_NOW)
        t_base = generate_investment_thesis(oh, base, now=_NOW)
        # the forward sidecar overlaid backlog/dilution identically -> IDENTICAL thesis.
        self.assertEqual(t_adapter, t_base)
        self.assertEqual(t_adapter.investability_assessment,
                         "thesis_worthy_timing_confirmed")

    def test_insufficient_inputs_yield_honest_limited_thesis_not_padded(self):
        oh = _alpha_oh()
        pkt = _consistent_packet()
        di, mapping = to_nivesha_forward_sidecar(pkt)   # NO operator base -> thin inputs
        t = generate_investment_thesis(oh, di, now=_NOW)
        # Nivesha's own honest gated outcome of thin inputs -- NOT padded to timing-confirmed.
        self.assertNotEqual(t.investability_assessment, "thesis_worthy_timing_confirmed")
        self.assertFalse(t.timing_confirmation)
        self.assertEqual(t.asymmetry_summary.asymmetry_label, "undetermined")
        # the reason is visible as adapter gaps, not hidden.
        self.assertTrue(any("future_gross_margin" in g for g in mapping.gaps))

    def test_prometheus_reasoning_object_is_the_accepted_one(self):
        # the thesis type + gauntlet fields come straight from prometheus, unchanged.
        oh = _alpha_oh()
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        t, _m = run_nivesha_thesis_on_forward_sidecar(
            oh, _consistent_packet(), base_inputs=base, now=_NOW)
        # red-team + timing survive as Nivesha's own labelled fields (F3).
        self.assertTrue(hasattr(t, "timing_confirmation"))
        self.assertTrue(hasattr(t, "asymmetry_summary"))
        self.assertIsInstance(t.timing_confirmation, bool)


# =========================================================================== #
# F. No score/rank/thesis/trade created by the adapter (F3 discipline)          #
# =========================================================================== #
class NoDecisionSurfaceTests(unittest.TestCase):
    _BANNED_FN = ("score", "rank", "rating", "buy", "sell", "thesis_strength")

    def test_module_defines_no_score_rank_or_thesis_function(self):
        tree = ast.parse(_read(_MODULE_FILE))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in self._BANNED_FN:
                    self.assertNotIn(tok, low, "banned fn token {0}: {1}".format(tok, node.name))
                if "thesis" in low:
                    # the ONLY function naming 'thesis' is the thin Nivesha runner.
                    self.assertEqual(node.name, "run_nivesha_thesis_on_forward_sidecar")

    def test_forward_objects_carry_no_trade_or_score_field(self):
        for cls in (ForwardScenarioInput, ForwardScenarioCase, ForwardScenarioPacket,
                    ForwardMappedField, ForwardSidecarMapping):
            assert_no_trade_fields(cls)
            for f in fields(cls):
                for tok in ("buy", "sell", "hold", "order", "trade", "score", "rank",
                            "rating", "verdict", "investab", "position", "allocat"):
                    self.assertNotIn(tok, f.name.lower(),
                                     "banned field {0} on {1}".format(f.name, cls.__name__))

    def test_adapter_return_has_no_investability_or_strength_attribute(self):
        di, mapping = to_nivesha_forward_sidecar(_consistent_packet())
        for bad in ("investability", "thesis", "strength", "score", "rank", "verdict",
                    "recommendation", "buy", "sell", "hold", "target_price"):
            self.assertFalse(hasattr(mapping, bad), "sidecar must not expose {0}".format(bad))
            self.assertFalse(hasattr(di, bad))

    def test_module_source_names_no_broker_or_order_affordance(self):
        blob = _read(_MODULE_FILE).lower()
        for banned in ("place_order", "submit_order", "broker.", "execute_trade",
                       "buy(", "sell(", "schedule.every", "cron"):
            self.assertNotIn(banned, blob)


# =========================================================================== #
# G. Offline + prometheus untouched (global guardrails §I)                      #
# =========================================================================== #
class OfflineAndImmutabilityTests(unittest.TestCase):
    def test_forward_path_is_offline(self):
        oh = _alpha_oh()
        base = DiligenceInputs(domain=_DOMAIN, candidates=(_alpha_candidate(),))
        real = socket.socket
        socket.socket = _boom_socket
        try:
            di, _m = to_nivesha_forward_sidecar(_consistent_packet(), base_inputs=base)
            t, _mp = run_nivesha_thesis_on_forward_sidecar(
                oh, _consistent_packet(), base_inputs=base, now=_NOW)
        finally:
            socket.socket = real
        self.assertEqual(di.candidates[0].ticker, "IREN")
        self.assertEqual(t.investability_assessment, "thesis_worthy_timing_confirmed")

    def test_module_imports_no_network_or_scheduler_or_broker(self):
        net = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
               "bs4", "selenium", "scrapy", "lxml", "sched", "asyncio", "subprocess",
               "threading", "multiprocessing", "smtplib", "ftplib", "signal", "os"}
        tree = ast.parse(_read(_MODULE_FILE))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods = [(node.module or "").split(".")[0]]
            for m in mods:
                self.assertNotIn(m, net, "module imports forbidden module {0}".format(m))

    def test_module_top_level_imports_only_prometheus_input_types(self):
        tree = ast.parse(_read(_MODULE_FILE))
        top_level_prom = []
        for node in tree.body:  # module-scope statements only
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("prometheus"):
                top_level_prom.append(node.module)
        self.assertEqual(top_level_prom, ["prometheus.diligence_inputs"])

    def test_no_prometheus_source_file_modified(self):
        res = subprocess.run(
            ["git", "status", "--porcelain", "--", "src/prometheus"],
            cwd=_ROOT, capture_output=True, text=True)
        self.assertEqual(res.stdout.strip(), "",
                         "prometheus/ must be untouched, got: {0}".format(res.stdout))

    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_nf_a_")
        d2 = tempfile.mkdtemp(prefix="rm_nf_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            with open(p1[name], "rb") as fa, open(p2[name], "rb") as fb:
                self.assertEqual(
                    fa.read(), fb.read(), "demo not byte-identical: {0}".format(name))


if __name__ == "__main__":
    unittest.main()
