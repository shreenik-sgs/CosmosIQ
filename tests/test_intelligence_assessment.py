from __future__ import annotations

import os as _os, sys as _sys
_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import copy
import unittest

from reality_intelligence.source_observation import make_source_observation
from reality_intelligence.intelligence_assessment import (
    generate_intelligence_assessment,
    IntelligenceAssessment,
    RealitySignal,
    SIGNAL_TYPES,
)

# Investment-decision language that must never appear in an assessment's own text.
_FORBIDDEN = ("investment", "buy", "sell", "allocat", "trade", "portfolio",
              "opportunity", "thesis", "valuation", "price target", "stock", "position")


def _obs(now=0.0, source_type="earnings_excerpt", entity="IREN",
         excerpt="domain reality reading", **kw):
    return make_source_observation(
        source_type=source_type, domain="ai-infrastructure", entity=entity,
        excerpt=excerpt, as_of="2026-Q1", source_ref="test", actor="analyst",
        now=now, **kw)


class TestIntelligenceAssessment(unittest.TestCase):

    # --- inference -------------------------------------------------------------
    def test_typed_signal_extraction_from_structured_observation(self):
        # A metric that rose 240 vs prior 200 -> an inferred *improving* readiness
        # signal whose strength is COMPUTED (not hand-fed) and whose evidence
        # quality is a distinct dimension.
        o = _obs(signal_type_hint="readiness", metric_value=240.0, prior_value=200.0,
                 excerpt="contracted power capacity rose")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertEqual(len(ia.signals), 1)
        s = ia.signals[0]
        self.assertIsInstance(s, RealitySignal)
        self.assertIn(s.signal_type, SIGNAL_TYPES)
        self.assertEqual(s.signal_type, "readiness")
        self.assertEqual(s.direction, "improving")
        self.assertAlmostEqual(s.strength, 0.4, places=4)   # 0.6 * min(1, 0.20/0.30)
        self.assertEqual(s.evidence_quality, 0.5)            # distinct from strength
        self.assertEqual(s.supporting_evidence_ids, (o.id,))
        self.assertEqual(ia.direction, "improving")

    def test_weak_signal_high_novelty_low_corroboration_is_surfaced(self):
        # A highly novel, only-moderately-reliable, uncorroborated deterioration is
        # a WEAK signal -- it must be surfaced, never dropped.
        o = _obs(source_type="capacity_power_demand_signal",
                 observed_change="down", novelty="high", source_reliability="moderate",
                 excerpt="grid power tightening")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertEqual(len(ia.weak_signals), 1)
        weak = ia.weak_signals[0]
        self.assertTrue(weak.is_weak)
        self.assertIn(weak, ia.signals)
        self.assertGreaterEqual(weak.novelty, 0.7)
        self.assertLessEqual(weak.strength, 0.45)

    def test_contradiction_between_signals_lowers_confidence(self):
        improving_a = _obs(signal_type_hint="readiness", observed_change="up",
                           excerpt="readiness up A")
        improving_b = _obs(signal_type_hint="readiness", observed_change="up",
                           excerpt="readiness up B")
        deteriorating = _obs(source_type="analyst_note_excerpt", observed_change="down",
                             excerpt="economic reading down")
        ia_clean = generate_intelligence_assessment(
            [improving_a, improving_b], domain="ai-infrastructure", now=0)
        ia_contra = generate_intelligence_assessment(
            [improving_a, improving_b, deteriorating], domain="ai-infrastructure", now=0)
        self.assertTrue(ia_contra.contradictions)
        self.assertFalse(ia_clean.contradictions)
        self.assertLess(ia_contra.confidence, ia_clean.confidence)

    def test_constraint_indicator_detected(self):
        o = _obs(source_type="capacity_power_demand_signal", observed_change="down",
                 excerpt="grid power is the binding constraint")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertTrue(ia.constraint_indicators)
        self.assertIn("constraint", ia.constraint_indicators[0])

    def test_readiness_indicator_detected(self):
        o = _obs(source_type="infrastructure_milestone", observed_change="up",
                 excerpt="megawatts energized")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertTrue(ia.readiness_indicators)
        self.assertIn("readiness", ia.readiness_indicators[0])

    def test_adoption_indicator_detected(self):
        o = _obs(source_type="news_excerpt", observed_change="up",
                 excerpt="adoption broadening")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertTrue(ia.adoption_indicators)
        self.assertIn("adoption", ia.adoption_indicators[0])

    def test_economic_inflection_indicator_detected(self):
        o = _obs(source_type="earnings_excerpt", observed_change="up",
                 excerpt="revenue inflecting")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertTrue(ia.economic_inflection_indicators)
        self.assertIn("economic_inflection", ia.economic_inflection_indicators[0])

    def test_evidence_quality_affects_confidence(self):
        # Same structured move; only the source reliability differs.
        high = _obs(signal_type_hint="readiness", metric_value=240.0, prior_value=200.0,
                    source_reliability="high", excerpt="capacity rose (reliable)")
        low = _obs(signal_type_hint="readiness", metric_value=240.0, prior_value=200.0,
                   source_reliability="low", excerpt="capacity rose (weakly sourced)")
        ia_high = generate_intelligence_assessment([high], domain="ai-infrastructure", now=0)
        ia_low = generate_intelligence_assessment([low], domain="ai-infrastructure", now=0)
        self.assertLess(ia_low.confidence, ia_high.confidence)

    def test_novelty_does_not_equal_confidence(self):
        # A high-novelty WEAK signal yields high novelty but NOT high confidence.
        o = _obs(source_type="capacity_power_demand_signal", observed_change="down",
                 novelty="high", source_reliability="moderate", excerpt="novel constraint")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertGreaterEqual(ia.signal_novelty, 0.7)   # high novelty
        self.assertLess(ia.confidence, 0.5)               # but not high confidence
        self.assertNotEqual(ia.signal_novelty, ia.confidence)
        self.assertTrue(ia.weak_signals)

    # --- boundary --------------------------------------------------------------
    def test_no_opportunity_or_investment_language_leaks(self):
        # A source whose RAW excerpt carries explicit investment language...
        leaky = _obs(
            source_type="analyst_note_excerpt", observed_change="down",
            excerpt="reading down",
            raw_excerpt=("analysts reiterate a buy rating and raise the price target; "
                         "an attractive investment opportunity for the portfolio"),
        )
        clean = _obs(signal_type_hint="readiness", observed_change="up", excerpt="capacity up")
        ia = generate_intelligence_assessment([clean, leaky], domain="ai-infrastructure", now=0)
        blob = " ".join([
            ia.assessment_type, ia.domain, ia.current_assessment, ia.significance,
            ia.domain_reality_change,
            " ".join(ia.constraint_indicators), " ".join(ia.readiness_indicators),
            " ".join(ia.adoption_indicators), " ".join(ia.economic_inflection_indicators),
            " ".join(ia.contradictions), " ".join(ia.uncertainty),
        ]).lower()
        for term in _FORBIDDEN:
            self.assertNotIn(term, blob, msg="leaked investment term: {0}".format(term))
        fields = set(IntelligenceAssessment.__dataclass_fields__.keys())
        for forbidden_field in ("opportunity", "thesis", "action", "recommendation",
                                "allocation", "trade", "buy", "sell"):
            self.assertNotIn(forbidden_field, fields)

    # --- catalyst / financial-report / capital-structure inference -------------
    def test_catalyst_observation_becomes_typed_signal(self):
        o = _obs(source_type="customer_announcement", catalyst_type="customer_win",
                 catalyst_status="probable", expected_direction="positive",
                 expected_timing_window="next two quarters",
                 affected_value_chain_node="data-center capacity",
                 excerpt="a hyperscaler customer commitment is taking shape")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertEqual(ia.signals[0].signal_type, "catalyst")
        self.assertTrue(ia.catalysts)
        self.assertEqual(ia.catalysts[0]["catalyst_type"], "customer_win")
        self.assertTrue(ia.catalyst_indicators)

    def test_imminent_contract_catalyst_becomes_positive_catalyst_signal(self):
        o = _obs(source_type="contract_win", catalyst_type="contract_win",
                 expected_direction="positive", catalyst_status="confirmed",
                 expected_timing_window="imminent",
                 excerpt="multi-year capacity contract signed")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        s = ia.signals[0]
        self.assertEqual(s.signal_type, "catalyst")
        self.assertEqual(s.direction, "improving")
        self.assertFalse(s.monitoring_only)
        self.assertEqual(ia.direction, "improving")

    def test_speculative_rumor_does_not_raise_confidence(self):
        # ADVERSARIAL: a relabeler that just trusts catalyst_status would let a rumor
        # carry the same confidence as a confirmed event. The status-weight discipline
        # must keep the rumor's confidence strictly lower, and flag it monitoring-only.
        confirmed = _obs(source_type="contract_win", catalyst_type="contract_win",
                         expected_direction="positive", catalyst_status="confirmed",
                         excerpt="contract win confirmed")
        rumor = _obs(source_type="press_release", catalyst_type="contract_win",
                     expected_direction="positive", catalyst_status="speculative_rumor",
                     excerpt="unverified chatter about a contract win")
        ia_conf = generate_intelligence_assessment([confirmed], domain="ai-infrastructure", now=0)
        ia_rumor = generate_intelligence_assessment([rumor], domain="ai-infrastructure", now=0)
        self.assertLess(ia_rumor.confidence, ia_conf.confidence)
        self.assertTrue(ia_rumor.signals[0].monitoring_only)
        self.assertTrue(ia_rumor.monitoring_signals)
        self.assertFalse(ia_conf.signals[0].monitoring_only)

    def test_financial_report_extracts_economic_inflection(self):
        o = _obs(source_type="financial_report", financial_metric="revenue",
                 metric_value=120.0, prior_value=100.0, excerpt="revenue grew")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        s = ia.signals[0]
        self.assertEqual(s.signal_type, "economic_inflection")
        self.assertEqual(s.direction, "improving")
        self.assertTrue(ia.economic_inflection_indicators)

    def test_guidance_raise_increases_economic_inflection_signal(self):
        raise_ = _obs(source_type="management_guidance", financial_metric="guidance",
                      metric_value=115.0, prior_value=100.0, excerpt="guidance raised")
        cut = _obs(source_type="management_guidance", financial_metric="guidance",
                   metric_value=85.0, prior_value=100.0, excerpt="guidance cut")
        ia_raise = generate_intelligence_assessment([raise_], domain="ai-infrastructure", now=0)
        ia_cut = generate_intelligence_assessment([cut], domain="ai-infrastructure", now=0)
        self.assertEqual(ia_raise.signals[0].signal_type, "economic_inflection")
        self.assertEqual(ia_raise.signals[0].direction, "improving")
        self.assertEqual(ia_cut.signals[0].direction, "deteriorating")

    def test_dilution_risk_becomes_capital_structure_risk_signal(self):
        # ADVERSARIAL: a negative capital-structure event is NOT a generic adoption
        # signal -- it must type as capital_structure_risk and read as deteriorating.
        by_metric = _obs(source_type="financial_report", financial_metric="dilution_risk",
                         excerpt="dilution risk flagged")
        by_catalyst = _obs(source_type="capital_structure_event", catalyst_type="stock_offering",
                           expected_direction="negative", excerpt="priced an equity offering")
        for ia in (generate_intelligence_assessment([by_metric], domain="ai-infrastructure", now=0),
                   generate_intelligence_assessment([by_catalyst], domain="ai-infrastructure", now=0)):
            self.assertEqual(ia.signals[0].signal_type, "capital_structure_risk")
            self.assertEqual(ia.signals[0].direction, "deteriorating")
            self.assertTrue(ia.capital_structure_risks)
            self.assertTrue(ia.capital_structure_risk_indicators)
        ia_cat = generate_intelligence_assessment([by_catalyst], domain="ai-infrastructure", now=0)
        self.assertTrue(ia_cat.capital_structure_risks[0]["dilution_flag"])

    def test_shelf_registration_increases_dilution_risk(self):
        o = _obs(source_type="sec_filing", catalyst_type="shelf_registration",
                 expected_direction="negative", excerpt="filed a shelf registration")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertEqual(ia.signals[0].signal_type, "capital_structure_risk")
        self.assertTrue(ia.capital_structure_risks)
        self.assertTrue(ia.capital_structure_risks[0]["dilution_flag"])

    def test_evidence_quality_affects_catalyst_confidence(self):
        # Same confirmed catalyst; only the source reliability differs.
        high = _obs(source_type="contract_win", catalyst_type="contract_win",
                    expected_direction="positive", catalyst_status="confirmed",
                    source_reliability="high", excerpt="reliable contract win")
        low = _obs(source_type="contract_win", catalyst_type="contract_win",
                   expected_direction="positive", catalyst_status="confirmed",
                   source_reliability="low", excerpt="weakly-sourced contract win")
        ia_high = generate_intelligence_assessment([high], domain="ai-infrastructure", now=0)
        ia_low = generate_intelligence_assessment([low], domain="ai-infrastructure", now=0)
        self.assertLess(ia_low.confidence, ia_high.confidence)

    # --- factual-only observations: grounding, but NEVER a signal --------------
    def _factual(self, source_type, now=0.0, **factual_fields):
        return make_source_observation(
            source_type=source_type, domain="ai-infrastructure", entity="IREN",
            excerpt="{0} reported for IREN on 2026-06-26".format(source_type),
            as_of="2026-06-26", source_ref="test", actor="analyst", now=now,
            factual_fields=factual_fields,
        )

    def test_factual_observation_produces_no_signal(self):
        # An OHLCV bar and a company profile are raw facts -- neither yields a
        # RealitySignal, so an IA over them alone has ZERO signals.
        ohlcv = self._factual("ohlcv_bar", open=20.0, high=21.5, low=19.9,
                              close=21.10, volume=15200000)
        profile = self._factual("company_profile_observation", sector="Technology",
                                industry="Data Center Infrastructure")
        ia = generate_intelligence_assessment([ohlcv, profile],
                                              domain="ai-infrastructure", now=0)
        self.assertEqual(len(ia.signals), 0)
        # they ARE recorded as grounding + factual audit ids.
        self.assertEqual(set(ia.grounding_observation_ids), {ohlcv.id, profile.id})
        self.assertEqual(set(ia.factual_observation_ids), {ohlcv.id, profile.id})

    def test_factual_observations_add_grounding_but_not_signal(self):
        # THE load-bearing invariant: an IA over {a real signal obs} + {OHLCV/profile
        # factual obs} has the SAME signals / direction / significance / confidence as
        # over the real observation ALONE. Facts add grounding, never inference.
        real = _obs(source_type="financial_report", financial_metric="revenue",
                    metric_value=120.0, prior_value=100.0, source_reliability="high",
                    excerpt="revenue grew")
        ohlcv = self._factual("ohlcv_bar", open=20.0, high=21.5, low=19.9,
                              close=21.10, volume=15200000)
        profile = self._factual("company_profile_observation", sector="Technology")
        ownership = self._factual("ownership_observation", holder="Vanguard",
                                  shares=1000000)

        ia_real = generate_intelligence_assessment([real], domain="ai-infrastructure", now=0)
        ia_both = generate_intelligence_assessment(
            [real, ohlcv, profile, ownership], domain="ai-infrastructure", now=0)

        self.assertEqual([s.signal_id for s in ia_real.signals],
                         [s.signal_id for s in ia_both.signals])
        self.assertEqual(ia_real.direction, ia_both.direction)
        self.assertEqual(ia_real.significance, ia_both.significance)
        self.assertEqual(ia_real.confidence, ia_both.confidence)
        self.assertEqual(ia_real.signal_novelty, ia_both.signal_novelty)
        self.assertEqual(ia_real.evidence_quality, ia_both.evidence_quality)
        # the factual observations still count as grounding.
        for o in (ohlcv, profile, ownership):
            self.assertIn(o.id, ia_both.grounding_observation_ids)
            self.assertNotIn(o.id, [sid for s in ia_both.signals
                                    for sid in s.supporting_evidence_ids])

    def test_factual_only_ia_carries_no_technical_or_investment_language(self):
        # An IA built purely from factual observations synthesises NO EMA / VWAP /
        # breakout / timing / relative-strength / accumulation / crowding text and NO
        # investment conclusion.
        ohlcv = self._factual("ohlcv_bar", open=20.0, high=21.5, low=19.9, close=21.10)
        quote = self._factual("quote_snapshot", current_price=21.10, previous_close=20.05)
        ia = generate_intelligence_assessment([ohlcv, quote],
                                              domain="ai-infrastructure", now=0)
        blob = " ".join([
            ia.current_assessment, ia.domain_reality_change,
            " ".join(ia.uncertainty), ia.assessment_type,
        ]).lower()
        for banned in ("ema", "vwap", "breakout", "compression", "relative strength",
                       "accumulation", "crowding", "under-recognition", "momentum",
                       "slope", "timing", "buy", "sell", "obviousness"):
            self.assertNotIn(banned, blob)
        for term in _FORBIDDEN:
            self.assertNotIn(term, blob)

    # --- invariants (kept) -----------------------------------------------------
    def test_missing_observation_rejected(self):
        with self.assertRaises(ValueError):
            generate_intelligence_assessment([], domain="ai-infrastructure", now=0)

    def test_provenance_binding_preserved(self):
        o1 = _obs(observed_change="up", excerpt="reading one")
        o2 = _obs(source_type="news_excerpt", observed_change="down", excerpt="reading two")
        ia = generate_intelligence_assessment([o1, o2], domain="ai-infrastructure", now=0)
        bound = {ref.object_id for ref in ia.provenance.sources}
        self.assertEqual(bound, {o1.id, o2.id})
        self.assertEqual(set(ia.grounding_observation_ids), {o1.id, o2.id})
        self.assertEqual(ia.provenance.actor, "reality-intelligence")

    def test_observation_version_binding_preserved(self):
        o = _obs(observed_change="up")
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        ref = ia.provenance.sources[0]
        self.assertEqual(ref.object_id, o.id)
        self.assertEqual(ref.version, o.version)  # exact version bound, not just id

    def test_no_upstream_mutation(self):
        o = _obs(observed_change="up")
        snapshot = copy.deepcopy(o)
        generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertEqual(o, snapshot)
        self.assertEqual(o.content["excerpt"], snapshot.content["excerpt"])


if __name__ == "__main__":
    unittest.main()
