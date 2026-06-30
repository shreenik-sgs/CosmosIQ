from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import unittest

from runtime.vertical_slice_runner import run_iren_slice
from reality_intelligence.source_observation import SOURCE_TYPES


class TestVerticalSliceIREN(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_iren_slice()

    def test_first_preview_quantity_about_200(self):
        # intended_allocation 2000 / limit 10.00 -> 200 shares.
        self.assertEqual(self.r.ticket_preview1.quantity, 200)
        self.assertEqual(self.r.ticket_preview1.order_type, "limit")
        self.assertEqual(self.r.ticket_preview1.instrument, "IREN")
        self.assertEqual(self.r.ticket_preview1.intended_allocation, 2000.0)

    def test_stale_revalidation_returns_to_preview(self):
        res = self.r.revalidate_stale
        self.assertEqual(res.status, "return_to_preview")
        self.assertIn("preview_stale", res.reasons)
        self.assertIn("market_moved", res.reasons)

    def test_re_preview_has_new_hash_and_requantified(self):
        p1, p2 = self.r.ticket_preview1, self.r.ticket_preview2
        self.assertEqual(p1.id, p2.id)  # same ticket id (idempotent identity)
        self.assertNotEqual(p1.preview_hash, p2.preview_hash)
        self.assertGreater(p2.version, p1.version)
        # 2000 / 10.40 -> 192 shares.
        self.assertEqual(p2.quantity, 192)
        self.assertAlmostEqual(p2.preview_price, 10.40, places=2)

    def test_fresh_revalidation_ok(self):
        self.assertTrue(self.r.revalidate_ok.ok)

    def test_confirmation_bound_to_new_preview_hash(self):
        confirmed = self.r.ticket_confirmed
        self.assertEqual(confirmed.state, "confirmed")
        self.assertEqual(confirmed.confirmation, self.r.ticket_preview2.preview_hash)

    def test_manual_placement_records_broker_order_id_and_time(self):
        placed = self.r.ticket_placed
        self.assertEqual(placed.state, "placed")
        self.assertEqual(placed.broker_order_id, "IBKR-12345")
        self.assertIsNotNone(placed.placed_at)

    def test_partial_then_full_fill_aggregates_to_filled(self):
        agg = self.r.aggregate
        self.assertEqual(agg.outcome, "filled")
        self.assertEqual(agg.cumulative_filled, 192)
        self.assertAlmostEqual(agg.average_price, 10.39, places=2)

    def test_reconciliation_passes_with_capital_within_tolerance(self):
        recon = self.r.reconciliation
        self.assertTrue(recon.all_reconciled, msg=str(recon.divergences()))
        link8 = next(l for l in recon.links if l.name == "capital_to_intended_allocation")
        self.assertTrue(link8.reconciled)
        # intended 2000 vs actual ~1994.88
        actual = sum(f.quantity * f.price for f in self.r.fills)
        self.assertAlmostEqual(actual, 1994.8, places=1)
        self.assertLess(abs(2000.0 - actual), 10.40)

    def test_audit_trail_contains_required_events(self):
        audit = self.r.audit_trail
        for event in ("stale_detected", "returned_to_preview", "placed_by_user",
                      "partial_fill", "fill_recorded", "reconciled"):
            self.assertTrue(audit.has_event(event), msg="missing event: {0}".format(event))
        placed_event = audit.events_of("placed_by_user")[0]
        self.assertEqual(placed_event.payload["broker_order_id"], "IBKR-12345")

    def test_feedback_observation_binds_ticket_and_fills(self):
        fb = self.r.feedback_observation
        source_ids = {ref.object_id for ref in fb.provenance.sources}
        self.assertIn(self.r.ticket_placed.id, source_ids)
        for f in self.r.fills:
            self.assertIn(f.id, source_ids)

    def test_replay_reconstructs_end_state_without_reactuating(self):
        audit = self.r.audit_trail
        tickets_before = len(self.r.registry)

        state1 = audit.replay()
        state2 = audit.replay()

        # Idempotent: two replays are identical.
        self.assertEqual(state1, state2)
        # No duplicate ticket created; replay does not touch the registry.
        self.assertEqual(len(state1.tickets), 1)
        self.assertEqual(len(self.r.registry), tickets_before)

        tid = self.r.ticket_placed.id
        reconstructed = state1.tickets[tid]
        self.assertEqual(reconstructed["state"], "reconciled")
        self.assertEqual(reconstructed["broker_order_id"], "IBKR-12345")
        self.assertEqual(len(state1.fills), 2)

    # --- IMPLEMENTATION-002: the slice begins from concrete Observations -------
    def test_slice_begins_with_concrete_observations(self):
        self.assertGreaterEqual(len(self.r.observations), 1)
        for o in self.r.observations:
            self.assertIsInstance(o.content, dict)
            self.assertIn(o.content.get("source_type"), SOURCE_TYPES)
        # The assessment is DERIVED from those Observations, not pre-baked.
        bound = {ref.object_id for ref in self.r.assessment.provenance.sources}
        self.assertEqual(bound, {o.id for o in self.r.observations})

    def test_assessment_is_inferred_from_observations(self):
        ia = self.r.assessment
        self.assertEqual(ia.domain, "ai-infrastructure")
        # The assessment INFERS typed signals from the structured observations...
        self.assertGreaterEqual(len(ia.signals), 1)
        # ...surfaces at least one weak signal (the novel, lightly-sourced constraint)...
        self.assertGreaterEqual(len(ia.weak_signals), 1)
        # ...detects a constraint OR readiness indicator...
        self.assertTrue(ia.constraint_indicators or ia.readiness_indicators)
        # ...and an adoption OR economic-inflection indicator...
        self.assertTrue(ia.adoption_indicators or ia.economic_inflection_indicators)
        # ...with exact version-bound provenance to the observations.
        self.assertEqual(len(ia.grounding_observation_ids), len(self.r.observations))
        for o in self.r.observations:
            ref = next(r for r in ia.provenance.sources if r.object_id == o.id)
            self.assertEqual(ref.version, o.version)

    def test_assessment_has_no_investment_leakage(self):
        ia = self.r.assessment
        blob = " ".join([
            ia.current_assessment, ia.domain_reality_change,
            " ".join(ia.constraint_indicators), " ".join(ia.readiness_indicators),
            " ".join(ia.adoption_indicators), " ".join(ia.economic_inflection_indicators),
            " ".join(ia.contradictions), " ".join(ia.uncertainty),
        ]).lower()
        for term in ("buy", "sell", "price target", "investment", "opportunity", "thesis"):
            self.assertNotIn(term, blob)

    # --- IMPLEMENTATION-003: Observation -> Assessment -> Opportunity ----------
    def test_vertical_slice_iren_starts_from_observations_and_generates_opportunity(self):
        # Begins from concrete Observations and a derived Assessment...
        self.assertGreaterEqual(len(self.r.observations), 1)
        self.assertEqual(self.r.assessment.domain, "ai-infrastructure")
        # ...and produces a real Opportunity Hypothesis bound to that Assessment.
        oh = self.r.hypothesis
        self.assertEqual(oh.domain, "ai-infrastructure")
        # The opportunity is REASONED from the enriched signals: a named theme,
        # an inferred timing, a bottleneck with its driving constraint and the
        # value-chain position it advantages -- never a relabelled score.
        self.assertEqual(oh.theme, "secured power capacity for AI infrastructure")
        self.assertIn(oh.theme_maturity,
                      ("hidden", "emerging", "accelerating", "crowded", "euphoric"))
        self.assertIn(oh.opportunity_timing,
                      ("before_obvious", "emerging", "recognized", "late"))
        self.assertTrue(oh.bottleneck_driven)
        self.assertEqual(oh.driving_constraint, "power/energy")
        self.assertEqual(oh.value_chain_position, "secured-power capacity owners")
        self.assertEqual(oh.triggering_assessment_ids, (self.r.assessment.id,))
        self.assertIn(self.r.assessment.id, {r.object_id for r in oh.provenance.sources})
        self.assertEqual(oh.triggering_assessment_versions, (self.r.assessment.version,))
        self.assertIn(oh.opportunity_magnitude,
                      ("small", "moderate", "large", "transformational"))
        self.assertGreater(oh.confidence, 0.0)
        # Genesis says WHAT is emerging and WHY, never HOW to invest.
        blob = " ".join([oh.theme, oh.opportunity_mechanism, oh.why_now,
                         oh.why_before_obvious, oh.value_chain_position,
                         " ".join(oh.uncertainty), " ".join(oh.monitoring_signals)]).lower()
        for term in ("buy", "sell", "allocat", "portfolio", "security", "ticker",
                     "valuation", "trade", "order", "position size", "$", "price target"):
            self.assertNotIn(term, blob)

    def test_vertical_slice_iren_generates_alpha_grade_opportunity_without_assessment_type_bridge(self):
        import inspect
        from runtime import vertical_slice_runner
        # The runner must NOT pass an assessment_type override into Reality
        # Intelligence -- the assessment type is INFERRED from the signals.
        src = inspect.getsource(vertical_slice_runner.run_iren_slice)
        self.assertNotIn("assessment_type=", src)
        # With the bridge removed, Tattva infers the type from the dominant signal.
        self.assertEqual(self.r.assessment.assessment_type, "readiness_timing")
        # The slice opportunity is alpha-grade: a theme, >=2 converging families,
        # an inferred timing, and a bottleneck with its driving constraint.
        oh = self.r.hypothesis
        self.assertTrue(oh.theme)
        self.assertGreaterEqual(len(oh.cross_domain_convergence), 2)
        self.assertIn(oh.opportunity_timing,
                      ("before_obvious", "emerging", "recognized", "late"))
        self.assertTrue(oh.bottleneck_driven)
        self.assertTrue(oh.driving_constraint)
        # No security / valuation / trade / allocation leakage in any synthesised text.
        blob = " ".join([oh.theme, oh.opportunity_mechanism, oh.why_now,
                         oh.why_before_obvious, oh.value_chain_position,
                         oh.driving_constraint, " ".join(oh.megatrend_context),
                         " ".join(oh.uncertainty), " ".join(oh.monitoring_signals)]).lower()
        for term in ("buy", "sell", "allocat", "portfolio", "security", "ticker",
                     "valuation", "trade", "order", "position size", "$"):
            self.assertNotIn(term, blob)


    # --- IMPLEMENTATION-004B: the slice thesis is an alpha-grade gated thesis ---
    def test_vertical_slice_iren_generates_alpha_grade_investment_thesis(self):
        t = self.r.thesis
        # The thesis is the GATED alpha thesis, not the toy placeholder.
        self.assertEqual(t.investability_assessment, "thesis_worthy_timing_confirmed")
        self.assertTrue(t.timing_confirmation)
        # Security/instrument mapping follows the winner mapping (top winner ticker).
        self.assertEqual(t.security_or_instrument_mapping, "IREN")
        self.assertEqual(t.winner_mapping[0].ticker, "IREN")
        # The gauntlet legs are all alpha-grade.
        self.assertEqual(t.asymmetry_summary.asymmetry_label, "exceptional")
        self.assertEqual(t.market_recognition_summary.recognition_stage, "hidden")
        self.assertTrue(t.technical_inflection_summary.technical_confirmation)
        self.assertEqual(t.technical_inflection_summary.ema_stack_status, "stacked_up")
        self.assertTrue(t.repricing_trigger_summary.gate_passed)
        self.assertNotEqual(t.red_team_summary.red_team_verdict, "fail")
        self.assertGreaterEqual(t.thesis_confidence, 0.5)
        # Provenance chain is preserved: Thesis -> OpportunityHypothesis -> ... -> Observations.
        self.assertIn(self.r.hypothesis.id, {r.object_id for r in t.provenance.sources})
        self.assertEqual(set(t.upstream_observation_ids),
                         set(self.r.hypothesis.upstream_observation_ids))

    def test_vertical_slice_thesis_has_no_trade_or_allocation_leakage(self):
        t = self.r.thesis
        blob = " ".join([
            t.thesis_summary, t.investability_assessment,
            t.security_or_instrument_mapping, t.thesis_time_horizon,
            " ".join(t.key_drivers), " ".join(t.key_risks),
            " ".join(t.invalidation_conditions), " ".join(t.monitoring_signals),
        ]).lower()
        for term in ("buy", "sell", " hold", "enter ", "exit ", "trim", " add ",
                     "rotate", "allocat", "position size", "order", "ticket"):
            self.assertNotIn(term, blob, msg="leaked forbidden term: {0}".format(term))
        # The thesis object carries no allocation / position-size field.
        fields = set(type(t).__dataclass_fields__.keys())
        for f in ("intended_allocation", "position_size", "allocation"):
            self.assertNotIn(f, fields)


if __name__ == "__main__":
    unittest.main()
