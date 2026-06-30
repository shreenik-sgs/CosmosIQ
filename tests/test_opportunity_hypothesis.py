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

# Investment-decision language that must never appear in an opportunity's text.
_FORBIDDEN = ("buy", "sell", "hold", "target price", "allocat", "position size",
              "portfolio", "invest", "trade", "security selection", "entry point",
              "exit point", "thesis")


def _ia(now=0.0, polarity="supportive", conf=None, domain="ai-infrastructure",
        assessment_type="capacity_economics", entity="IREN"):
    # Vary the excerpt by polarity so distinct readings are distinct Observations
    # (the Observation id is content-addressed over the excerpt, not the polarity).
    obs = [
        make_source_observation(
            source_type="earnings_excerpt", domain=domain, entity=entity,
            excerpt="domain signal one ({0})".format(polarity), polarity=polarity,
            signal_strength=1.0, as_of="2026-Q1", now=now),
        make_source_observation(
            source_type="news_excerpt", domain=domain, entity=entity,
            excerpt="domain signal two ({0})".format(polarity), polarity=polarity,
            signal_strength=1.0, as_of="2026-Q1", now=now),
    ]
    return generate_intelligence_assessment(
        obs, domain=domain, assessment_type=assessment_type, now=now, confidence=conf)


class TestOpportunityHypothesis(unittest.TestCase):

    def test_intelligence_assessment_to_opportunity_success(self):
        ia = _ia(polarity="supportive")
        oh = generate_opportunity_hypothesis([ia], domain="ai-infrastructure", now=0)
        self.assertIsInstance(oh, OpportunityHypothesis)
        self.assertEqual(oh.domain, "ai-infrastructure")
        self.assertEqual(oh.opportunity_type, "capacity_expansion")
        self.assertIn("opportunity", oh.opportunity_summary)
        self.assertIn(oh.opportunity_magnitude,
                      ("negligible", "small", "moderate", "large", "transformational"))
        self.assertEqual(oh.timing_window, "emerging")
        self.assertGreater(oh.evidence_strength, 0.0)
        self.assertGreater(oh.confidence, 0.0)
        self.assertEqual(oh.triggering_assessment_ids, (ia.id,))

    def test_missing_intelligence_assessment_rejected(self):
        with self.assertRaises(ValueError):
            generate_opportunity_hypothesis([], domain="ai-infrastructure", now=0)

    def test_assessment_version_binding_preserved(self):
        ia = _ia(polarity="supportive")
        oh = generate_opportunity_hypothesis([ia], domain="ai-infrastructure", now=0)
        ref = oh.provenance.sources[0]
        self.assertEqual(ref.object_id, ia.id)
        self.assertEqual(ref.version, ia.version)
        self.assertEqual(oh.triggering_assessment_versions, (ia.version,))

    def test_provenance_chain_preserved_from_observations_to_opportunity(self):
        obs = make_source_observation(
            source_type="capacity_power_demand_signal", domain="ai-infrastructure",
            entity="IREN", excerpt="grid power is the binding constraint",
            polarity="supportive", as_of="2026-06", now=0)
        ia = generate_intelligence_assessment(
            [obs], domain="ai-infrastructure", assessment_type="constraint", now=0)
        oh = generate_opportunity_hypothesis([ia], domain="ai-infrastructure", now=0)
        # OH -> IA
        self.assertIn(ia.id, {r.object_id for r in oh.provenance.sources})
        # IA -> Observation (the chain is preserved hop by hop)
        self.assertIn(obs.id, {r.object_id for r in ia.provenance.sources})
        self.assertIn(obs.id, set(ia.grounding_observation_ids))

    def test_no_upstream_mutation(self):
        ia = _ia(polarity="supportive")
        snapshot = copy.deepcopy(ia)
        generate_opportunity_hypothesis([ia], domain="ai-infrastructure", now=0)
        self.assertEqual(ia, snapshot)

    def test_no_investment_thesis_or_trade_leakage(self):
        ia = _ia(polarity="supportive")
        oh = generate_opportunity_hypothesis([ia], domain="ai-infrastructure", now=0)
        blob = " ".join([
            oh.opportunity_type, oh.domain, oh.opportunity_summary, oh.opportunity_mechanism,
            oh.opportunity_magnitude, oh.timing_window, " ".join(oh.uncertainty),
        ]).lower()
        for term in _FORBIDDEN:
            self.assertNotIn(term, blob, msg="leaked investment term: {0}".format(term))
        # No thesis/security/instrument/allocation/position field on the object.
        fields = set(OpportunityHypothesis.__dataclass_fields__.keys())
        for f in ("thesis", "security", "instrument", "allocation", "position",
                  "order", "side", "quantity", "limit_price"):
            self.assertNotIn(f, fields)

    def test_contradictory_assessment_penalizes_confidence(self):
        improving = _ia(polarity="supportive", conf=0.6)     # direction improving
        contradictory = _ia(polarity="contradictory", conf=0.6)  # direction deteriorating
        oh_clean = generate_opportunity_hypothesis([improving], domain="ai-infrastructure", now=0)
        oh_mixed = generate_opportunity_hypothesis(
            [improving, contradictory], domain="ai-infrastructure", now=0)
        self.assertLess(oh_mixed.confidence, oh_clean.confidence)
        self.assertIn(contradictory.id, oh_mixed.contradictory_assessment_ids)
        self.assertNotIn(improving.id, oh_mixed.contradictory_assessment_ids)


if __name__ == "__main__":
    unittest.main()
