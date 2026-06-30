"""Tests for the Infinite Canvas READ-ONLY read-model layer (IMPLEMENTATION-008A).

These tests prove the projection discipline INDEPENDENTLY of the implementation:

* the cockpit assembles end to end from the real slice;
* the views are read-only -- building them never mutates a source object;
* the views COPY scores, never recompute them (adversarial score-equality);
* missing data (TAM, market share, moat, scenario anchors, VWAP, ...) is flagged,
  never fabricated;
* every panel and the cockpit carry provenance back to their source objects;
* the personalized panel exposes a RANGE / max-exposure % only -- no exact size;
* positive / negative / speculative-rumor catalysts are kept separate, and a rumor
  raises no confidence value;
* the value-chain/players panel marks that security mapping FOLLOWS winners;
* the build is deterministic.
"""

from __future__ import annotations

import os as _os, sys as _sys
_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import copy
import unittest

from runtime.vertical_slice_runner import run_iren_slice
from reality_intelligence.source_observation import make_source_observation
from reality_intelligence.intelligence_assessment import generate_intelligence_assessment

from infinite_canvas import (
    from_slice,
    build_alpha_decision_cockpit_view,
    build_catalyst_panel,
    panel_field_names,
    SOURCE_CLASS_MANUAL,
)


class TestCanvasReadModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slice = run_iren_slice()
        cls.cockpit = from_slice(cls.slice)

    # --- assembly ----------------------------------------------------------- #
    def test_cockpit_assembles_end_to_end_from_slice(self):
        c = self.cockpit
        # the seven cognition panels are always present; personalized + manual too.
        self.assertEqual(len(c.panels), 9)
        for panel in c.panels:
            self.assertTrue(panel.panel_id)
        # subject is the thesis's security/instrument mapping, copied verbatim.
        self.assertEqual(c.subject, self.slice.thesis.security_or_instrument_mapping)
        self.assertTrue(c.subject)

    def test_every_panel_is_frozen(self):
        import dataclasses
        for panel in self.cockpit.panels:
            with self.assertRaises(dataclasses.FrozenInstanceError):
                panel.panel_id = "mutated"  # type: ignore[misc]

    def test_every_panel_labels_data_origin_manual(self):
        for panel in self.cockpit.panels:
            self.assertEqual(panel.source_class, SOURCE_CLASS_MANUAL)

    # --- read-only ---------------------------------------------------------- #
    def test_view_models_are_read_only_no_source_mutation(self):
        s = run_iren_slice()
        before = {
            "hypothesis": copy.deepcopy(s.hypothesis),
            "thesis": copy.deepcopy(s.thesis),
            "assessment": copy.deepcopy(s.assessment),
            "personalized_action": copy.deepcopy(s.personalized_action),
            "execution_intent": copy.deepcopy(s.execution_intent),
            "ticket_placed": copy.deepcopy(s.ticket_placed),
        }
        from_slice(s)
        for name, snapshot in before.items():
            self.assertEqual(getattr(s, name), snapshot,
                             "building the cockpit mutated the source {0}".format(name))

    # --- no recomputation (adversarial score-equality) ---------------------- #
    def test_view_does_not_recompute_scores(self):
        c = self.cockpit
        p = self.slice.personalized_action
        t = self.slice.thesis

        # personalized suitability is copied verbatim
        self.assertEqual(c.personalized_action.suitability_score, p.suitability_score)
        self.assertEqual(c.personalized_action.recommended_max_exposure_pct,
                         p.recommended_max_exposure_pct)
        self.assertEqual(c.personalized_action.suggested_sizing_range_pct,
                         tuple(p.suggested_sizing_range_pct))

        # a player's winner_score == the source WinnerScore (no re-scoring)
        winners = list(t.winner_mapping)
        self.assertTrue(winners)
        view_by_ticker = {pl.ticker: pl for pl in c.value_chain_bottleneck.players}
        for w in winners:
            self.assertIn(w.ticker, view_by_ticker)
            self.assertEqual(view_by_ticker[w.ticker].winner_score, w.winner_score)
            self.assertEqual(view_by_ticker[w.ticker].leadership_quality, w.leadership_quality)

        # scenario / technical / financial scores are copies of the thesis summaries
        self.assertEqual(c.scenario_asymmetry.asymmetry_score,
                         t.asymmetry_summary.asymmetry_score)
        self.assertEqual(c.scenario_asymmetry.upside_downside_ratio,
                         t.asymmetry_summary.upside_downside_ratio)
        self.assertEqual(c.technical_confirmation.technical_setup_score,
                         t.technical_inflection_summary.technical_setup_score)
        self.assertEqual(c.financial_inflection.financial_inflection_score,
                         t.financial_inflection_summary.financial_inflection_score)
        self.assertEqual(c.value_chain_bottleneck.bottleneck_leverage,
                         t.bottleneck_summary.bottleneck_leverage)

    def test_opportunity_panel_copies_oh_verbatim(self):
        oh = self.slice.hypothesis
        om = self.cockpit.opportunity_map
        self.assertEqual(om.theme, oh.theme)
        self.assertEqual(om.false_positive_risk, oh.false_positive_risk)
        self.assertEqual(om.bubble_hype_risk, oh.bubble_hype_risk)
        self.assertEqual(om.confidence, oh.confidence)
        self.assertEqual(om.evidence_quality, oh.evidence_strength)

    # --- honest missing data ------------------------------------------------ #
    def test_tam_and_share_are_missing_not_fabricated(self):
        sa = self.cockpit.scenario_asymmetry
        self.assertIsNone(sa.current_tam)
        self.assertIsNone(sa.implied_market_share)
        joined = " ".join(sa.missing_fields)
        self.assertIn("current_tam", joined)
        self.assertIn("implied_market_share", joined)
        # scenario anchors not carried on the thesis summary are missing, not invented
        self.assertIsNone(sa.bear_price)
        self.assertIsNone(sa.bull_price)
        self.assertIsNone(sa.extreme_bull_price)
        self.assertIn("extreme_bull_price", joined)

    def test_moat_and_supplier_depth_missing_not_fabricated(self):
        vcb = self.cockpit.value_chain_bottleneck
        joined = " ".join(vcb.missing_fields)
        self.assertIn("moat_details", joined)
        self.assertIn("supplier_of_supplier_depth", joined)

    def test_technical_vwap_overhead_missing_not_fabricated(self):
        tc = self.cockpit.technical_confirmation
        self.assertIsNone(tc.vwap)
        self.assertIsNone(tc.anchored_vwap)
        self.assertIsNone(tc.overhead_supply)
        joined = " ".join(tc.missing_fields)
        for name in ("vwap", "anchored_vwap", "overhead_supply"):
            self.assertIn(name, joined)

    def test_data_gaps_unions_missing_panels(self):
        gaps = " ".join(self.cockpit.data_gaps)
        self.assertIn("scenario_asymmetry.current_tam", gaps)
        self.assertIn("value_chain_bottleneck.moat_details", gaps)
        self.assertIn("technical_confirmation.vwap", gaps)

    # --- provenance --------------------------------------------------------- #
    def test_every_panel_carries_provenance(self):
        c = self.cockpit
        expected_id = {
            "opportunity_map": self.slice.hypothesis.id,
            "value_chain_bottleneck": self.slice.thesis.id,
            "catalyst": self.slice.assessment.id,
            "financial_inflection": self.slice.thesis.id,
            "scenario_asymmetry": self.slice.thesis.id,
            "technical_confirmation": self.slice.thesis.id,
            "red_team": self.slice.thesis.id,
            "personalized_action": self.slice.personalized_action.id,
            "manual_execution": self.slice.execution_intent.id,
        }
        for panel in c.panels:
            self.assertTrue(panel.provenance.sources,
                            "{0} has no provenance sources".format(panel.panel_id))
            ids = [r.object_id for r in panel.provenance.sources]
            self.assertIn(expected_id[panel.panel_id], ids)
            # cross-cutting source ids mirror the provenance refs
            self.assertEqual(set(panel.source_object_ids), set(ids))
            self.assertEqual(len(panel.source_object_versions), len(panel.source_object_ids))

    def test_provenance_chain_is_complete_observation_to_ticket(self):
        kinds = [r.kind for r in self.cockpit.provenance_chain]
        for kind in (
            "Observation", "IntelligenceAssessment", "OpportunityHypothesis",
            "InvestmentThesis", "InvestmentAction", "PersonalizedAction",
            "ManualExecutionIntent", "ManualTradeTicket",
        ):
            self.assertIn(kind, kinds, "provenance chain missing {0}".format(kind))
        # order: Observation first, Ticket last
        self.assertEqual(kinds[0], "Observation")
        self.assertEqual(kinds[-1], "ManualTradeTicket")
        # the chain points at the real objects
        ids = {r.kind: r.object_id for r in self.cockpit.provenance_chain}
        self.assertEqual(ids["InvestmentThesis"], self.slice.thesis.id)
        self.assertEqual(ids["ManualTradeTicket"], self.slice.ticket_placed.id)

    # --- boundary preserved ------------------------------------------------- #
    def test_personalized_panel_has_no_order_or_exact_size(self):
        names = " ".join(panel_field_names(self.cockpit.personalized_action)).lower()
        for forbidden in ("shares", "quantity", "broker", "order", "ticket",
                          "exact", "allocation_amount", "contract", "limit_price"):
            self.assertNotIn(forbidden, names,
                             "personalized panel must not expose {0!r}".format(forbidden))
        # only range / max-exposure percentages are present
        self.assertIn("recommended_max_exposure_pct",
                      panel_field_names(self.cockpit.personalized_action))
        self.assertIn("suggested_sizing_range_pct",
                      panel_field_names(self.cockpit.personalized_action))

    def test_manual_execution_panel_shows_user_size_and_is_manual_only(self):
        me = self.cockpit.manual_execution
        intent = self.slice.execution_intent
        # the user's explicit chosen size, copied from the ManualExecutionIntent
        self.assertEqual(me.user_selected_allocation_amount,
                         intent.user_selected_allocation_amount)
        self.assertEqual(me.execution_intent_id, intent.id)
        self.assertTrue(me.manual_execution_only)
        # broker_order_id is only a recorded value (manual placement), present from the ticket
        self.assertEqual(me.broker_order_id, self.slice.ticket_placed.broker_order_id)
        notes = " ".join(me.data_notes).lower()
        self.assertIn("manual", notes)

    def test_technical_panel_uses_timing_confirmation_language(self):
        names = panel_field_names(self.cockpit.technical_confirmation)
        self.assertIn("technical_timing_confirmation", names)
        # never an action-ready field
        joined = " ".join(names).lower()
        self.assertNotIn("action_ready", joined)
        self.assertNotIn("action-ready", joined)
        # the flag copies the source technical_confirmation
        self.assertEqual(self.cockpit.technical_confirmation.technical_timing_confirmation,
                         self.slice.thesis.technical_inflection_summary.technical_confirmation)

    def test_players_panel_marks_security_mapping_follows_winners(self):
        vcb = self.cockpit.value_chain_bottleneck
        self.assertTrue(vcb.security_mapping_follows_winners)
        self.assertEqual(vcb.security_or_instrument_mapping,
                         self.slice.thesis.security_or_instrument_mapping)
        self.assertTrue(any("FOLLOWS" in n.upper() for n in vcb.data_notes))

    # --- catalysts ---------------------------------------------------------- #
    def test_catalyst_view_keeps_positive_and_separates_rumor(self):
        # the IREN slice carries one confirmed positive catalyst, no rumour.
        cat = self.cockpit.catalyst
        self.assertTrue(cat.positive_catalysts)
        self.assertTrue(any(c.catalyst_status == "confirmed" for c in cat.positive_catalysts))
        # no confirmed catalyst leaked into the rumour bucket
        self.assertFalse(any(c.catalyst_status == "speculative_rumor"
                             for c in cat.positive_catalysts))

    def test_catalyst_view_separates_speculative_rumor_from_confirmed(self):
        # ADVERSARIAL: build an assessment with BOTH a confirmed positive catalyst and
        # a speculative rumour; the rumour must land in its own field, never merged,
        # and must not raise any confidence value on the panel.
        now = 1_700_000_000.0
        obs = (
            make_source_observation(
                source_type="contract_win", domain="ai-infrastructure", entity="IREN",
                excerpt="A multi-year contracted power-capacity reservation was signed.",
                catalyst_type="capacity_reservation", catalyst_status="confirmed",
                expected_direction="positive", affected_value_chain_node="power/energy",
                expected_timing_window="next 2 quarters", as_of="2026-06",
                source_ref="press release", actor="analyst", now=now,
            ),
            make_source_observation(
                source_type="press_release", domain="ai-infrastructure", entity="IREN",
                excerpt="Unconfirmed chatter of a possible additional hyperscaler deal.",
                catalyst_type="customer_announcement", catalyst_status="speculative_rumor",
                expected_direction="positive", as_of="2026-06",
                source_ref="rumour", actor="analyst", now=now,
            ),
        )
        ia = generate_intelligence_assessment(obs, domain="ai-infrastructure", now=now)
        panel = build_catalyst_panel(self.slice.thesis, ia)

        statuses_positive = {c.catalyst_status for c in panel.positive_catalysts}
        statuses_rumor = {c.catalyst_status for c in panel.speculative_rumors}
        self.assertIn("confirmed", statuses_positive)
        self.assertNotIn("speculative_rumor", statuses_positive)
        self.assertEqual(statuses_rumor, {"speculative_rumor"})

        # the rumour's evidence_quality is heavily discounted and never aggregated up.
        for c in panel.speculative_rumors:
            self.assertIsNotNone(c.evidence_quality)
            self.assertLessEqual(c.evidence_quality, 0.3)
        # the panel reports no inflated confidence number.
        self.assertIsNone(panel.confidence)

    def test_negative_catalysts_visible_when_present(self):
        # build an assessment carrying a dilution / capital-structure risk.
        now = 1_700_000_000.0
        obs = (
            make_source_observation(
                source_type="capital_structure_event", domain="ai-infrastructure",
                entity="IREN",
                excerpt="The company filed an ATM equity offering / shelf registration.",
                catalyst_type="atm_offering", catalyst_status="confirmed",
                expected_direction="negative", as_of="2026-06",
                source_ref="filing", actor="analyst", now=now,
            ),
        )
        ia = generate_intelligence_assessment(obs, domain="ai-infrastructure", now=now)
        panel = build_catalyst_panel(self.slice.thesis, ia)
        self.assertTrue(panel.negative_catalysts,
                        "negative catalysts must be surfaced, never hidden")
        self.assertTrue(any(c.dilution_flag for c in panel.negative_catalysts))

    # --- determinism -------------------------------------------------------- #
    def test_cockpit_is_deterministic(self):
        a = from_slice(run_iren_slice())
        b = from_slice(run_iren_slice())
        self.assertEqual(a, b)

    def test_builder_optional_panels_absent_when_sources_missing(self):
        c = build_alpha_decision_cockpit_view(
            opportunity_hypothesis=self.slice.hypothesis,
            investment_thesis=self.slice.thesis,
            intelligence_assessment=self.slice.assessment,
            observations=self.slice.observations,
        )
        self.assertIsNone(c.personalized_action)
        self.assertIsNone(c.manual_execution)
        self.assertEqual(len(c.panels), 7)


if __name__ == "__main__":
    unittest.main()
