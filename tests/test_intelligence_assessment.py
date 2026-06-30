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
)

# Investment-decision language that must never appear in an assessment's own text.
_FORBIDDEN = ("investment", "buy", "sell", "allocat", "trade", "portfolio",
              "opportunity", "thesis", "valuation", "price target")


def _obs(now=0.0, source_type="earnings_excerpt", entity="IREN", polarity="supportive",
         strength=1.0, excerpt="contracted data-center power capacity increased"):
    return make_source_observation(
        source_type=source_type, domain="ai-infrastructure", entity=entity,
        excerpt=excerpt, polarity=polarity, signal_strength=strength,
        as_of="2026-Q1", source_ref="test", actor="analyst", now=now,
    )


class TestIntelligenceAssessment(unittest.TestCase):

    def test_observation_to_intelligence_assessment_success(self):
        obs = [
            _obs(polarity="supportive"),
            _obs(source_type="infrastructure_milestone", polarity="supportive",
                 excerpt="additional megawatts energized at the Texas site"),
        ]
        ia = generate_intelligence_assessment(
            obs, domain="ai-infrastructure", assessment_type="capacity_economics", now=0)
        self.assertIsInstance(ia, IntelligenceAssessment)
        self.assertEqual(ia.domain, "ai-infrastructure")
        self.assertEqual(ia.assessment_type, "capacity_economics")
        self.assertIn("improving", ia.current_assessment)  # two supportive signals
        self.assertIn(ia.significance, ("low", "moderate", "high"))
        self.assertGreater(ia.confidence, 0.0)
        self.assertEqual(len(ia.grounding_observation_ids), 2)

    def test_missing_observation_rejected(self):
        with self.assertRaises(ValueError):
            generate_intelligence_assessment([], domain="ai-infrastructure", now=0)

    def test_provenance_binding_preserved(self):
        o1 = _obs()
        o2 = _obs(source_type="news_excerpt", excerpt="grid power constraint tightening")
        ia = generate_intelligence_assessment([o1, o2], domain="ai-infrastructure", now=0)
        bound = {ref.object_id for ref in ia.provenance.sources}
        self.assertEqual(bound, {o1.id, o2.id})
        self.assertEqual(set(ia.grounding_observation_ids), {o1.id, o2.id})
        self.assertEqual(ia.provenance.actor, "reality-intelligence")

    def test_observation_version_binding_preserved(self):
        o = _obs()
        ia = generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        ref = ia.provenance.sources[0]
        self.assertEqual(ref.object_id, o.id)
        self.assertEqual(ref.version, o.version)  # exact version bound, not just id

    def test_no_upstream_mutation(self):
        o = _obs()
        snapshot = copy.deepcopy(o)
        generate_intelligence_assessment([o], domain="ai-infrastructure", now=0)
        self.assertEqual(o, snapshot)
        self.assertEqual(o.content["excerpt"], snapshot.content["excerpt"])

    def test_no_opportunity_or_investment_leakage(self):
        # A source whose RAW excerpt carries explicit investment language...
        leaky = _obs(
            source_type="analyst_note_excerpt", polarity="contradictory", strength=0.6,
            excerpt=("analysts reiterate a buy rating and raise the price target; "
                     "an attractive investment opportunity for the portfolio"),
        )
        clean = _obs(polarity="supportive")
        ia = generate_intelligence_assessment([clean, leaky], domain="ai-infrastructure", now=0)

        # ...must not leak into the assessment's own synthesised text.
        blob = " ".join([
            ia.assessment_type, ia.domain, ia.current_assessment, ia.significance,
            " ".join(ia.contradictions), " ".join(ia.uncertainty),
        ]).lower()
        for term in _FORBIDDEN:
            self.assertNotIn(term, blob, msg="leaked investment term: {0}".format(term))

        # The object itself carries no opportunity/thesis/action/recommendation field.
        fields = set(IntelligenceAssessment.__dataclass_fields__.keys())
        for forbidden_field in ("opportunity", "thesis", "action", "recommendation",
                                "allocation", "trade", "buy", "sell"):
            self.assertNotIn(forbidden_field, fields)


if __name__ == "__main__":
    unittest.main()
