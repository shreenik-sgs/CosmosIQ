"""IMPLEMENTATION-004B -- the Nivesha / Prometheus alpha diligence gauntlet.

Drives an Opportunity Hypothesis (built for real via Tattva + Sphurana) plus
hand-fed DiligenceInputs through the eleven-stage gauntlet and asserts the gating,
the per-stage rules, the boundary (no trade / allocation / order leakage), and the
preserved provenance chain Observation -> IA -> OH -> Thesis.
"""

from __future__ import annotations

import os as _os, sys as _sys
_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import copy
import dataclasses
import unittest

from reality_intelligence.source_observation import make_source_observation
from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis

from prometheus.diligence_inputs import CandidateInput, DiligenceInputs
from prometheus.investment_thesis import generate_investment_thesis, InvestmentThesis
from prometheus.pattern_matching import analyze_pattern_matching
from prometheus.theme_context import analyze_theme_context
from prometheus.value_chain import analyze_value_chain
from prometheus.bottleneck import analyze_bottleneck
from prometheus.winner_mapping import analyze_winner_mapping
from prometheus.financial_inflection import analyze_financial_inflection
from prometheus.market_recognition import analyze_market_recognition
from prometheus.asymmetry import analyze_asymmetry
from prometheus.technical_inflection import analyze_technical_inflection
from prometheus.repricing_trigger import analyze_repricing_trigger

DOMAIN = "ai-infrastructure"


# --------------------------------------------------------------------------- #
# Observation builders (real source material -> Tattva infers signals).
# --------------------------------------------------------------------------- #

def _readiness_up(now=0.0):
    return make_source_observation(
        source_type="earnings_excerpt", domain=DOMAIN, entity="IREN",
        excerpt="contracted power capacity expanded quarter over quarter",
        signal_type_hint="readiness", metric_name="contracted_power_capacity_mw",
        metric_value=240.0, prior_value=200.0, metric_unit="MW", as_of="2026-Q1", now=now)


def _adoption_up(now=0.0):
    return make_source_observation(
        source_type="news_excerpt", domain=DOMAIN, entity="IREN",
        excerpt="hyperscaler adoption of power-secured colocation is accelerating",
        observed_change="up", as_of="2026-06", now=now)


def _constraint_weak(now=0.0):
    return make_source_observation(
        source_type="capacity_power_demand_signal", domain=DOMAIN, entity="IREN",
        excerpt="available grid power is tightening as a binding constraint",
        observed_change="down", novelty="high", source_reliability="moderate",
        as_of="2026-06", now=now)


def _recognition_up(now=0.0):
    return make_source_observation(
        source_type="news_excerpt", domain=DOMAIN, entity="IREN",
        excerpt="the data-center power theme is now widely covered by the market",
        signal_type_hint="market_recognition", observed_change="up", as_of="2026-06", now=now)


def _confirmed_catalyst(now=0.0):
    return make_source_observation(
        source_type="contract_win", domain=DOMAIN, entity="IREN",
        excerpt="a multi-year power-capacity reservation was signed and announced",
        catalyst_type="capacity_reservation", catalyst_status="confirmed",
        expected_direction="positive", affected_value_chain_node="power/energy",
        expected_timing_window="next 2 quarters", as_of="2026-06", now=now)


def _rumored_catalyst(now=0.0):
    return make_source_observation(
        source_type="news_excerpt", domain=DOMAIN, entity="IREN",
        excerpt="unconfirmed chatter of a possible large power-capacity reservation",
        catalyst_type="capacity_reservation", catalyst_status="speculative_rumor",
        expected_direction="positive", affected_value_chain_node="power/energy",
        as_of="2026-06", now=now)


def _oh(observations, now=0.0):
    ia = generate_intelligence_assessment(observations, domain=DOMAIN, now=now)
    return generate_opportunity_hypothesis([ia], domain=DOMAIN, now=now)


def _alpha_oh(now=0.0):
    return _oh([_readiness_up(now), _adoption_up(now), _constraint_weak(now),
               _confirmed_catalyst(now)], now=now)


def _rumor_oh(now=0.0):
    return _oh([_readiness_up(now), _adoption_up(now), _constraint_weak(now),
               _rumored_catalyst(now)], now=now)


def _crowded_oh(now=0.0):
    return _oh([_readiness_up(now), _adoption_up(now), _recognition_up(now)], now=now)


def _no_bottleneck_oh(now=0.0):
    # readiness + adoption converge but no tightening constraint -> not bottleneck-driven.
    return _oh([_readiness_up(now), _adoption_up(now)], now=now)


# --------------------------------------------------------------------------- #
# Candidate builders.
# --------------------------------------------------------------------------- #

def _alpha_candidate(**overrides):
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
        float_shares=180_000_000.0,
        valuation_multiple=8.0, valuation_reflects_story=False,
        bear_price=8.00, base_price=14.00, bull_price=22.00, extreme_bull_price=35.00,
        ema9=10.10, ema20=9.70, ema50=9.00, ema200=7.50, ema_slopes_up=True,
        relative_strength=0.35, vwap=9.95,
        breakout_level=9.80, invalidation_level=9.00, price_above_breakout=True,
        base_duration_days=55, volatility_contracting=True,
        volume_recent=1_800_000.0, volume_avg=1_100_000.0,
    )
    base.update(overrides)
    return CandidateInput(**base)


def _inputs(candidate, **kw):
    return DiligenceInputs(domain=DOMAIN, candidates=(candidate,), **kw)


def _thesis(oh, candidate, now=0.0):
    return generate_investment_thesis(oh, _inputs(candidate), now=now)


# --------------------------------------------------------------------------- #


class TestNiveshaDiligence(unittest.TestCase):

    # --- preconditions -----------------------------------------------------
    def test_opportunity_requires_diligence_before_thesis(self):
        oh = _alpha_oh()
        with self.assertRaises(ValueError):
            generate_investment_thesis(oh, DiligenceInputs(domain=DOMAIN, candidates=()), now=0)
        with self.assertRaises(ValueError):
            generate_investment_thesis(oh, None, now=0)

    # --- A. pattern matching ----------------------------------------------
    def test_historical_pattern_match_success(self):
        oh = _alpha_oh()
        res = analyze_pattern_matching(oh, _inputs(_alpha_candidate()))
        self.assertTrue(res.matched_archetypes)
        self.assertFalse(res.bubble_flag)
        self.assertGreaterEqual(res.pattern_quality, 0.5)
        names = {m.name for m in res.matched_archetypes}
        self.assertIn("bottleneck_capacity_owner", names)

    def test_bubble_pattern_penalizes_thesis(self):
        oh = _crowded_oh()
        self.assertIn(oh.theme_maturity, ("crowded", "euphoric"))
        # thin financials: declining revenue / margin -> no inflection.
        thin = _alpha_candidate(revenue=90.0, prior_revenue=120.0,
                                gross_margin=0.30, prior_gross_margin=0.36,
                                guidance="cut", valuation_reflects_story=True,
                                institutional_ownership=0.7, analyst_coverage=30)
        res = analyze_pattern_matching(oh, _inputs(thin))
        self.assertTrue(res.bubble_flag)
        t = _thesis(oh, thin)
        self.assertEqual(t.investability_assessment, "not_investable")
        self.assertLessEqual(t.thesis_confidence, 0.3)

    # --- C. value chain ----------------------------------------------------
    def test_value_chain_graph_identifies_economic_capture_node(self):
        vc = analyze_value_chain(_alpha_oh())
        self.assertIsNotNone(vc.capture_node)
        self.assertEqual(vc.capture_node.tier, 1)
        self.assertEqual(vc.capture_role, "secured-power capacity owner")
        self.assertTrue(vc.capture_node.choke_point)
        self.assertGreaterEqual(vc.value_chain_capture, 0.8)
        tier1 = [n.economic_leverage_score for n in vc.nodes if n.tier == 1]
        self.assertEqual(vc.value_chain_capture, max(tier1))

    # --- D. bottleneck -----------------------------------------------------
    def test_bottleneck_analysis_identifies_critical_constraint(self):
        b = analyze_bottleneck(_alpha_oh())
        self.assertEqual(b.bottleneck_type, "secured_power_capacity")
        self.assertGreaterEqual(b.severity, 0.8)
        self.assertGreater(b.bottleneck_leverage, 0.0)
        self.assertIn("secured-power capacity owners", b.direct_beneficiaries)

    # --- E. winner mapping -------------------------------------------------
    def test_winner_mapping_requires_value_chain_role(self):
        oh = _alpha_oh()
        with_role = _alpha_candidate(name="A", ticker="A")
        without_role = _alpha_candidate(name="B", ticker="B", value_chain_role="")
        inputs = DiligenceInputs(domain=DOMAIN, candidates=(with_role, without_role))
        res = analyze_winner_mapping(oh, inputs, analyze_bottleneck(oh), analyze_value_chain(oh))
        by_ticker = {w.ticker: w for w in res.winners}
        self.assertGreater(by_ticker["A"].winner_score, by_ticker["B"].winner_score)
        self.assertAlmostEqual(by_ticker["B"].exposure_directness, 0.10, places=2)
        self.assertEqual(res.best_winner.ticker, "A")

    def test_security_mapping_follows_winner_mapping(self):
        t = _thesis(_alpha_oh(), _alpha_candidate())
        self.assertEqual(t.security_or_instrument_mapping, "IREN")
        # the mapping is the TOP winner's ticker, computed after scoring.
        self.assertEqual(t.security_or_instrument_mapping, t.winner_mapping[0].ticker)

    # --- F. financial inflection ------------------------------------------
    def test_financial_inflection_affects_thesis_confidence(self):
        oh = _alpha_oh()
        strong = _thesis(oh, _alpha_candidate())
        weak = _thesis(oh, _alpha_candidate(revenue=205.0, prior_revenue=200.0,
                                            gross_margin=0.48, prior_gross_margin=0.48,
                                            guidance="cut"))
        self.assertGreater(
            strong.financial_inflection_summary.financial_inflection_score,
            weak.financial_inflection_summary.financial_inflection_score)
        self.assertGreater(strong.thesis_confidence, weak.thesis_confidence)

    def test_dilution_risk_penalizes_financial_inflection(self):
        clean = analyze_financial_inflection(_alpha_candidate(dilution_risk="none",
                                                              convertible_debt=False))
        diluted = analyze_financial_inflection(_alpha_candidate(dilution_risk="high",
                                                                shelf_registration=True,
                                                                atm_facility=True))
        self.assertGreater(clean.financial_inflection_score, diluted.financial_inflection_score)

    # --- G. market recognition --------------------------------------------
    def test_market_recognition_hidden_supports_alpha(self):
        m = analyze_market_recognition(_alpha_oh(), _alpha_candidate())
        self.assertIn(m.recognition_stage, ("hidden", "early_recognition"))
        self.assertGreaterEqual(m.market_recognition_score, 0.7)

    def test_crowded_market_penalizes_before_obvious(self):
        crowded_cand = _alpha_candidate(analyst_coverage=30, institutional_ownership=0.85,
                                        valuation_reflects_story=True)
        m = analyze_market_recognition(_crowded_oh(), crowded_cand)
        self.assertIn(m.recognition_stage, ("crowded", "euphoric_bubble_risk"))
        self.assertLessEqual(m.market_recognition_score, 0.3)

    # --- H. asymmetry ------------------------------------------------------
    def test_asymmetry_requires_upside_and_downside(self):
        no_bull = analyze_asymmetry(_alpha_candidate(bull_price=None))
        no_bear = analyze_asymmetry(_alpha_candidate(bear_price=None))
        self.assertEqual(no_bull.asymmetry_label, "undetermined")
        self.assertEqual(no_bear.asymmetry_label, "undetermined")
        full = analyze_asymmetry(_alpha_candidate())
        self.assertIn(full.asymmetry_label, ("balanced", "favorable", "exceptional"))

    def test_good_company_bad_stock_case_is_blocked(self):
        # great fundamentals, ugly payoff (priced for perfection).
        cand = _alpha_candidate(bear_price=7.00, base_price=10.10, bull_price=10.30,
                                valuation_reflects_story=True)
        t = _thesis(_alpha_oh(), cand)
        self.assertEqual(t.asymmetry_summary.asymmetry_label, "poor")
        self.assertGreater(t.financial_inflection_summary.financial_inflection_score, 0.7)
        self.assertEqual(t.investability_assessment, "not_investable")

    def test_high_growth_poor_asymmetry_case_is_blocked(self):
        cand = _alpha_candidate(current_price=100.0, revenue=300.0, prior_revenue=100.0,
                                bear_price=40.0, base_price=110.0, bull_price=130.0)
        t = _thesis(_alpha_oh(), cand)
        self.assertGreater(t.asymmetry_summary.downside_risk, 0.5)
        self.assertEqual(t.asymmetry_summary.asymmetry_label, "poor")
        self.assertEqual(t.investability_assessment, "not_investable")

    # --- I. red team -------------------------------------------------------
    def test_red_team_failure_blocks_thesis(self):
        # severe dilution is a critical red-team failure.
        cand = _alpha_candidate(dilution_risk="high", shelf_registration=True,
                                atm_facility=True)
        t = _thesis(_alpha_oh(), cand)
        self.assertEqual(t.red_team_summary.red_team_verdict, "fail")
        self.assertEqual(t.investability_assessment, "not_investable")
        self.assertTrue(t.red_team_summary.false_positive_label)

    # --- K. repricing trigger ---------------------------------------------
    def test_confirmed_contract_catalyst_increases_repricing_trigger_score(self):
        confirmed = _thesis(_alpha_oh(), _alpha_candidate())
        rumor = _thesis(_rumor_oh(), _alpha_candidate())
        self.assertGreater(confirmed.repricing_trigger_summary.catalyst_score,
                           rumor.repricing_trigger_summary.catalyst_score)
        self.assertGreater(confirmed.repricing_trigger_summary.repricing_probability,
                           rumor.repricing_trigger_summary.repricing_probability)

    def test_speculative_rumor_does_not_raise_repricing_probability_materially(self):
        confirmed = _thesis(_alpha_oh(), _alpha_candidate())
        rumor = _thesis(_rumor_oh(), _alpha_candidate())
        self.assertLessEqual(rumor.repricing_trigger_summary.catalyst_score, 0.1)
        self.assertFalse(rumor.repricing_trigger_summary.gate_passed)
        self.assertGreaterEqual(
            confirmed.repricing_trigger_summary.repricing_probability
            - rumor.repricing_trigger_summary.repricing_probability, 0.3)

    def test_repricing_trigger_requires_catalyst_financial_asymmetry_and_technical_confirmation(self):
        oh = _alpha_oh()
        full = analyze_repricing_trigger(
            oh, _alpha_candidate(),
            analyze_financial_inflection(_alpha_candidate()),
            analyze_market_recognition(oh, _alpha_candidate()),
            analyze_asymmetry(_alpha_candidate()),
            analyze_technical_inflection(_alpha_candidate()),
            analyze_bottleneck(oh))
        self.assertTrue(full.gate_passed)
        # drop technical confirmation (no volume / not stacked) -> gate fails.
        weak_chart = _alpha_candidate(volume_recent=900_000.0, ema9=8.0)
        broken = analyze_repricing_trigger(
            oh, weak_chart,
            analyze_financial_inflection(weak_chart),
            analyze_market_recognition(oh, weak_chart),
            analyze_asymmetry(weak_chart),
            analyze_technical_inflection(weak_chart),
            analyze_bottleneck(oh))
        self.assertFalse(broken.gate_passed)
        self.assertGreaterEqual(full.repricing_probability - broken.repricing_probability, 0.3)

    # --- J. technical inflection -------------------------------------------
    def test_EMA_stack_up_detected(self):
        r = analyze_technical_inflection(_alpha_candidate())
        self.assertEqual(r.ema_stack_status, "stacked_up")

    def test_EMA_stack_requires_9_above_20_above_50_above_200(self):
        # 9 below 20 breaks the stack.
        r = analyze_technical_inflection(_alpha_candidate(ema9=9.50))
        self.assertEqual(r.ema_stack_status, "not_stacked")
        # 50 below 200 also breaks it.
        r2 = analyze_technical_inflection(_alpha_candidate(ema50=7.00))
        self.assertEqual(r2.ema_stack_status, "not_stacked")

    def test_EMA_slope_alignment_required(self):
        r = analyze_technical_inflection(_alpha_candidate(ema_slopes_up=False))
        self.assertFalse(r.trend_alignment)
        self.assertTrue(analyze_technical_inflection(_alpha_candidate()).trend_alignment)

    def test_compression_breakout_detected(self):
        r = analyze_technical_inflection(_alpha_candidate())
        self.assertEqual(r.compression_breakout_status, "breakout_confirmed")
        self.assertTrue(r.breakout)

    def test_volume_confirmation_required(self):
        ok = analyze_technical_inflection(_alpha_candidate())
        self.assertTrue(ok.volume_confirmation)
        self.assertTrue(ok.technical_confirmation)
        low_vol = analyze_technical_inflection(_alpha_candidate(volume_recent=1_000_000.0))
        self.assertFalse(low_vol.volume_confirmation)
        self.assertFalse(low_vol.technical_confirmation)

    def test_failed_breakout_penalizes_timing(self):
        failed = analyze_technical_inflection(_alpha_candidate(price_above_breakout=False))
        ok = analyze_technical_inflection(_alpha_candidate())
        self.assertTrue(failed.failed_breakout_risk)
        self.assertEqual(failed.timing_quality, "failed_breakout_risk")
        self.assertLess(failed.technical_setup_score, ok.technical_setup_score)
        self.assertFalse(failed.technical_confirmation)

    def test_dilution_overhang_penalizes_breakout_quality(self):
        clean = analyze_technical_inflection(_alpha_candidate(dilution_risk="none"))
        overhang = analyze_technical_inflection(_alpha_candidate(dilution_risk="high",
                                                                shelf_registration=True))
        self.assertGreater(overhang.dilution_overhang_penalty, 0.0)
        self.assertLess(overhang.technical_setup_score, clean.technical_setup_score)

    def test_technical_trigger_does_not_create_order(self):
        r = analyze_technical_inflection(_alpha_candidate())
        for attr in ("order", "ticket", "trade", "side", "quantity", "broker_order_id"):
            self.assertFalse(hasattr(r, attr))

    # --- action-readiness gating ------------------------------------------
    def test_strong_thesis_without_technical_confirmation_is_not_action_ready(self):
        # strong fundamentals/asymmetry but the chart does not confirm.
        cand = _alpha_candidate(ema9=8.0, volume_recent=900_000.0, price_above_breakout=False)
        t = _thesis(_alpha_oh(), cand)
        self.assertGreaterEqual(t.base_score, 0.5)
        self.assertFalse(t.technical_inflection_summary.technical_confirmation)
        self.assertEqual(t.investability_assessment, "thesis_worthy")
        self.assertFalse(t.action_ready)

    def test_weak_thesis_with_strong_chart_is_not_action_ready(self):
        # no bottleneck -> value-chain capture and bottleneck leverage are ~0,
        # so the thesis base is weak even though the chart is a clean breakout.
        oh = _no_bottleneck_oh()
        self.assertFalse(oh.bottleneck_driven)
        cand = _alpha_candidate(revenue=110.0, prior_revenue=100.0,
                                gross_margin=0.48, prior_gross_margin=0.48,
                                guidance="inline", bear_price=8.5, base_price=11.0,
                                bull_price=13.0)
        t = _thesis(oh, cand)
        self.assertTrue(t.technical_inflection_summary.technical_confirmation)
        self.assertLess(t.base_score, 0.5)
        self.assertEqual(t.investability_assessment, "watch")
        self.assertFalse(t.action_ready)

    # --- boundary ----------------------------------------------------------
    def test_investment_thesis_has_no_buy_sell_hold_enter_exit_allocation_order_leakage(self):
        t = _thesis(_alpha_oh(), _alpha_candidate())
        blob = " ".join([
            t.thesis_summary, t.investability_assessment,
            t.security_or_instrument_mapping, t.thesis_time_horizon,
            " ".join(t.key_drivers), " ".join(t.key_risks),
            " ".join(t.invalidation_conditions), " ".join(t.monitoring_signals),
        ]).lower()
        for term in ("buy", "sell", " hold", "enter ", "exit ", "trim", " add ",
                     "rotate", "allocat", "position size", "order", "trade ticket",
                     "manual execution", "ticket"):
            self.assertNotIn(term, blob, msg="leaked forbidden term: {0}".format(term))
        fields = set(InvestmentThesis.__dataclass_fields__.keys())
        for f in ("intended_allocation", "position_size", "allocation", "side",
                  "quantity", "order"):
            self.assertNotIn(f, fields)
        # Nivesha MAY name the security/ticker mapping and say "action-ready".
        self.assertEqual(t.security_or_instrument_mapping, "IREN")

    # --- provenance / immutability ----------------------------------------
    def test_provenance_chain_preserved_from_observations_to_thesis(self):
        observations = [_readiness_up(), _adoption_up(), _constraint_weak(),
                        _confirmed_catalyst()]
        ia = generate_intelligence_assessment(observations, domain=DOMAIN, now=0)
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        t = _thesis(oh, _alpha_candidate())
        self.assertIn(oh.id, {r.object_id for r in t.provenance.sources})
        self.assertEqual(t.opportunity_id, oh.id)
        self.assertEqual(t.triggering_assessment_ids, oh.triggering_assessment_ids)
        self.assertEqual(set(t.upstream_observation_ids), set(oh.upstream_observation_ids))
        self.assertEqual(set(oh.upstream_observation_ids), set(ia.grounding_observation_ids))
        self.assertEqual(set(ia.grounding_observation_ids), {o.id for o in observations})

    def test_no_upstream_mutation(self):
        oh = _alpha_oh()
        cand = _alpha_candidate()
        inputs = _inputs(cand)
        oh_snap = copy.deepcopy(oh)
        inputs_snap = copy.deepcopy(inputs)
        generate_investment_thesis(oh, inputs, now=0)
        self.assertEqual(oh, oh_snap)
        self.assertEqual(inputs, inputs_snap)


if __name__ == "__main__":
    unittest.main()
