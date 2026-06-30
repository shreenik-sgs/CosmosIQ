from __future__ import annotations

import os as _os, sys as _sys
_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import copy
import unittest

from reality_intelligence.source_observation import make_source_observation
from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import (
    generate_opportunity_hypothesis,
    OpportunityHypothesis,
)

# Security / valuation / trade / allocation / action language that must never
# appear in an opportunity's synthesised text. (Genesis MAY say opportunity, theme,
# before-obvious, bottleneck, value-chain position, "secured-power capacity owners".)
_FORBIDDEN = ("buy", "sell", "hold", "target price", "price target", "allocat",
              "position size", "portfolio", "security", "ticker", "valuation", "$",
              "entry point", "exit point", "trade", "order", "action readiness",
              "action-ready", "repricing")

_RISK_RANK = {"low": 0, "moderate": 1, "high": 2}

DOMAIN = "ai-infrastructure"


# --------------------------------------------------------------------------- #
# Observation builders -- real source material from which Tattva infers signals.
# --------------------------------------------------------------------------- #

def _readiness_up(now=0.0, entity="IREN", mv=240.0, pv=200.0):
    return make_source_observation(
        source_type="earnings_excerpt", domain=DOMAIN, entity=entity,
        excerpt="contracted power capacity expanded quarter over quarter",
        signal_type_hint="readiness", metric_name="contracted_power_capacity_mw",
        metric_value=mv, prior_value=pv, metric_unit="MW", as_of="2026-Q1", now=now)


def _adoption_up(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="news_excerpt", domain=DOMAIN, entity=entity,
        excerpt="hyperscaler adoption of power-secured colocation is accelerating",
        observed_change="up", as_of="2026-06", now=now)


def _adoption_down(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="news_excerpt", domain=DOMAIN, entity=entity,
        excerpt="hyperscaler colocation demand is cooling off this quarter",
        observed_change="down", as_of="2026-06", now=now)


def _readiness_down(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="earnings_excerpt", domain=DOMAIN, entity=entity,
        excerpt="contracted power capacity slipped versus the prior quarter",
        signal_type_hint="readiness", metric_name="contracted_power_capacity_mw",
        metric_value=160.0, prior_value=200.0, metric_unit="MW", as_of="2026-Q2", now=now)


def _econ_up(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="earnings_excerpt", domain=DOMAIN, entity=entity,
        excerpt="revenue and operating leverage strengthening",
        financial_metric="revenue", metric_value=130.0, prior_value=100.0,
        as_of="2026-Q1", now=now)


def _constraint_tightening_weak(now=0.0, entity="IREN"):
    # A highly novel, only-moderately-reliable, uncorroborated deterioration ->
    # Tattva marks it a WEAK constraint (tightening) signal.
    return make_source_observation(
        source_type="capacity_power_demand_signal", domain=DOMAIN, entity=entity,
        excerpt="available grid power is tightening as a binding constraint",
        observed_change="down", novelty="high", source_reliability="moderate",
        as_of="2026-06", now=now)


def _constraint_easing(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="capacity_power_demand_signal", domain=DOMAIN, entity=entity,
        excerpt="grid power availability is loosening as new supply comes online",
        signal_type_hint="constraint", observed_change="up",
        as_of="2026-06", now=now)


def _recognition_up(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="news_excerpt", domain=DOMAIN, entity=entity,
        excerpt="the data-center power theme is now widely covered by the market",
        signal_type_hint="market_recognition", observed_change="up",
        as_of="2026-06", now=now)


def _confirmed_catalyst(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="contract_win", domain=DOMAIN, entity=entity,
        excerpt="a multi-year power-capacity reservation was signed and announced",
        catalyst_type="capacity_reservation", catalyst_status="confirmed",
        expected_direction="positive", affected_value_chain_node="power/energy",
        expected_timing_window="next 2 quarters", as_of="2026-06", now=now)


def _rumored_catalyst(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="news_excerpt", domain=DOMAIN, entity=entity,
        excerpt="unconfirmed chatter of a possible large power-capacity reservation",
        catalyst_type="capacity_reservation", catalyst_status="speculative_rumor",
        expected_direction="positive", affected_value_chain_node="power/energy",
        as_of="2026-06", now=now)


def _cap_structure_risk(now=0.0, entity="IREN"):
    return make_source_observation(
        source_type="sec_filing", domain=DOMAIN, entity=entity,
        excerpt="a shelf registration and at-the-market dilution facility were filed",
        financial_metric="dilution_risk", as_of="2026-06", now=now)


def _ia(observations, now=0.0, domain=DOMAIN):
    return generate_intelligence_assessment(observations, domain=domain, now=now)


# --------------------------------------------------------------------------- #


class TestOpportunityHypothesis(unittest.TestCase):

    # --- alpha reasoning ---------------------------------------------------

    def test_theme_forms_from_cross_domain_convergence(self):
        ia = _ia([_readiness_up(), _adoption_up(), _constraint_tightening_weak()])
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        self.assertIsInstance(oh, OpportunityHypothesis)
        self.assertTrue(oh.theme)
        self.assertEqual(oh.theme, "secured power capacity for AI infrastructure")
        # Several independent families converge (readiness + adoption + constraint).
        self.assertGreaterEqual(len(oh.cross_domain_convergence), 2)
        self.assertIn("readiness", oh.cross_domain_convergence)
        self.assertIn("constraint", oh.cross_domain_convergence)
        self.assertTrue(oh.megatrend_context)

    def test_single_signal_only_creates_monitoring_priority_not_high_confidence_opportunity(self):
        ia = _ia([_adoption_up()])  # one improving family only
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        self.assertLessEqual(len(oh.cross_domain_convergence), 1)
        # A single converging family is a low-confidence monitoring priority.
        self.assertLess(oh.confidence, 0.34)
        self.assertTrue(oh.monitoring_signals)
        # And it cannot be ranked a large/transformational opportunity.
        self.assertIn(oh.opportunity_magnitude, ("negligible", "small", "moderate"))

    def test_weak_signal_supports_before_obvious_timing(self):
        ia = _ia([_readiness_up(), _constraint_tightening_weak()])
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        self.assertGreaterEqual(len(ia.weak_signals), 1)
        self.assertEqual(oh.opportunity_timing, "before_obvious")
        self.assertIn("novel", oh.why_before_obvious.lower())

    def test_confirmed_catalyst_supports_why_now(self):
        ia_cat = _ia([_readiness_up(), _adoption_up(), _confirmed_catalyst()])
        ia_no = _ia([_readiness_up(), _adoption_up()])
        oh_cat = generate_opportunity_hypothesis([ia_cat], domain=DOMAIN, now=0)
        oh_no = generate_opportunity_hypothesis([ia_no], domain=DOMAIN, now=0)
        self.assertIn("catalyst", oh_cat.why_now.lower())
        # A confirmed positive catalyst raises why-now confidence.
        self.assertGreater(oh_cat.confidence, oh_no.confidence)

    def test_speculative_rumor_does_not_raise_opportunity_confidence_materially(self):
        # ADVERSARIAL: a rumour must not manufacture confidence.
        ia_base = _ia([_readiness_up(), _adoption_up()])
        ia_rumor = _ia([_readiness_up(), _adoption_up(), _rumored_catalyst()])
        oh_base = generate_opportunity_hypothesis([ia_base], domain=DOMAIN, now=0)
        oh_rumor = generate_opportunity_hypothesis([ia_rumor], domain=DOMAIN, now=0)
        self.assertLessEqual(oh_rumor.confidence, oh_base.confidence + 0.01)
        # The rumour is surfaced for monitoring only.
        joined = " ".join(oh_rumor.monitoring_signals).lower()
        self.assertIn("rumour", joined.replace("rumor", "rumour"))

    def test_capital_structure_risk_increases_false_positive_risk(self):
        # ADVERSARIAL: an upstream dilution risk makes the edge more likely a trap.
        ia_clean = _ia([_readiness_up(), _adoption_up(), _econ_up()])
        ia_risk = _ia([_readiness_up(), _adoption_up(), _econ_up(), _cap_structure_risk()])
        oh_clean = generate_opportunity_hypothesis([ia_clean], domain=DOMAIN, now=0)
        oh_risk = generate_opportunity_hypothesis([ia_risk], domain=DOMAIN, now=0)
        self.assertGreater(_RISK_RANK[oh_risk.false_positive_risk],
                           _RISK_RANK[oh_clean.false_positive_risk])

    def test_bottleneck_driven_opportunity_identifies_driving_constraint(self):
        ia = _ia([_readiness_up(), _adoption_up(), _constraint_tightening_weak()])
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        self.assertTrue(oh.bottleneck_driven)
        self.assertEqual(oh.driving_constraint, "power/energy")
        # The mechanism is the causal chain: tightening constraint into rising demand.
        self.assertIn("tightening", oh.opportunity_mechanism.lower())
        self.assertIn(oh.driving_constraint, oh.opportunity_mechanism)
        rels = {r["relation"]: r["target"] for r in oh.opportunity_graph_relationships}
        self.assertEqual(rels.get("driven_by"), "power/energy")

    def test_value_chain_position_identified_without_security_mapping(self):
        ia = _ia([_readiness_up(), _adoption_up(), _constraint_tightening_weak()])
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        self.assertEqual(oh.value_chain_position, "secured-power capacity owners")
        # The value-chain position is a structural role, never a security/ticker.
        self.assertNotIn(oh.value_chain_position, oh.entities)
        for term in ("ticker", "security", "$"):
            self.assertNotIn(term, oh.value_chain_position.lower())

    def test_crowded_theme_penalizes_before_obvious_score(self):
        # High market recognition -> the theme is crowded, NOT before-obvious.
        ia_crowded = _ia([_readiness_up(), _adoption_up(), _recognition_up()])
        ia_hidden = _ia([_readiness_up(), _constraint_tightening_weak()])
        oh_crowded = generate_opportunity_hypothesis([ia_crowded], domain=DOMAIN, now=0)
        oh_hidden = generate_opportunity_hypothesis([ia_hidden], domain=DOMAIN, now=0)
        self.assertEqual(oh_crowded.theme_maturity, "crowded")
        self.assertNotEqual(oh_crowded.opportunity_timing, "before_obvious")
        # The same families with LOW recognition stay before-obvious.
        self.assertEqual(oh_hidden.opportunity_timing, "before_obvious")

    def test_bubble_hype_risk_surfaces(self):
        ia_crowded = _ia([_readiness_up(), _adoption_up(), _recognition_up()])
        ia_quiet = _ia([_readiness_up(), _constraint_tightening_weak()])
        oh_crowded = generate_opportunity_hypothesis([ia_crowded], domain=DOMAIN, now=0)
        oh_quiet = generate_opportunity_hypothesis([ia_quiet], domain=DOMAIN, now=0)
        self.assertIn(oh_crowded.bubble_hype_risk, ("moderate", "high"))
        self.assertEqual(oh_quiet.bubble_hype_risk, "low")

    def test_contradictory_assessments_lower_opportunity_confidence(self):
        improving = _ia([_readiness_up(), _adoption_up()])
        # A second assessment in which the SAME demand families are deteriorating
        # (adoption cooling, readiness slipping) -- genuinely opposing, not a
        # tightening-constraint tailwind.
        deteriorating = _ia([_adoption_down(), _readiness_down()])
        self.assertEqual(deteriorating.direction, "deteriorating")
        oh_clean = generate_opportunity_hypothesis([improving], domain=DOMAIN, now=0)
        oh_mixed = generate_opportunity_hypothesis(
            [improving, deteriorating], domain=DOMAIN, now=0)
        self.assertLess(oh_mixed.confidence, oh_clean.confidence)

    def test_opportunity_hypothesis_has_no_security_valuation_trade_or_allocation_leakage(self):
        ia = _ia([_readiness_up(), _adoption_up(), _constraint_tightening_weak(),
                  _confirmed_catalyst()])
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        blob = " ".join([
            oh.theme, oh.opportunity_mechanism, oh.why_now, oh.why_before_obvious,
            oh.driving_constraint, oh.value_chain_position, oh.domain,
            oh.theme_maturity, oh.opportunity_timing, oh.opportunity_maturity,
            oh.opportunity_magnitude, oh.false_positive_risk, oh.bubble_hype_risk,
            " ".join(oh.megatrend_context), " ".join(oh.cross_domain_convergence),
            " ".join(oh.uncertainty), " ".join(oh.monitoring_signals),
            " ".join(str(r.get("target", "")) for r in oh.opportunity_graph_relationships),
        ]).lower()
        for term in _FORBIDDEN:
            self.assertNotIn(term, blob, msg="leaked forbidden term: {0}".format(term))
        # No thesis/security/instrument/allocation/order field on the object.
        fields = set(OpportunityHypothesis.__dataclass_fields__.keys())
        for f in ("thesis", "security", "instrument", "allocation", "position_size",
                  "order", "side", "quantity", "limit_price", "valuation"):
            self.assertNotIn(f, fields)
        # Genesis MAY name the value-chain position explicitly.
        self.assertIn("secured-power capacity owners", oh.value_chain_position)

    # --- invariants --------------------------------------------------------

    def test_missing_assessment_rejected(self):
        with self.assertRaises(ValueError):
            generate_opportunity_hypothesis([], domain=DOMAIN, now=0)

    def test_provenance_binding_preserved(self):
        ia = _ia([_readiness_up(), _adoption_up()])
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        self.assertIn(ia.id, {r.object_id for r in oh.provenance.sources})
        self.assertEqual(oh.triggering_assessment_ids, (ia.id,))
        # The chain is preserved hop by hop: OH -> IA -> Observation.
        self.assertEqual(set(oh.upstream_observation_ids), set(ia.grounding_observation_ids))

    def test_assessment_version_binding_preserved(self):
        ia = _ia([_readiness_up(), _adoption_up()])
        oh = generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        ref = oh.provenance.sources[0]
        self.assertEqual(ref.object_id, ia.id)
        self.assertEqual(ref.version, ia.version)
        self.assertEqual(oh.triggering_assessment_versions, (ia.version,))

    def test_no_upstream_mutation(self):
        ia = _ia([_readiness_up(), _adoption_up(), _constraint_tightening_weak()])
        snapshot = copy.deepcopy(ia)
        generate_opportunity_hypothesis([ia], domain=DOMAIN, now=0)
        self.assertEqual(ia, snapshot)


if __name__ == "__main__":
    unittest.main()
