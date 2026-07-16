"""REQ-GEN-019 -- Opportunity Prioritization (OFFLINE, pure).

GEN-001 requires this and it was never built: "Genesis SHALL continuously prioritize Opportunities
according to their expected significance." These tests hold it to the three sentences that bound
it:

* "Prioritization SHALL express relative significance, NOT investment recommendation" -- so no
  field here claims a return, and the record carries no score / rank / rating (asserted with the
  repo's own structural guard, not by eye);
* "Prioritization SHALL remain continuously re-evaluable as understanding evolves" -- so it is a
  pure function of the CURRENT pulses, storing no verdict that could go stale;
* the standing "no HIDDEN score" discipline -- so the order is reconstructible from the labels each
  opportunity carries, and an opportunity too thin to judge ABSTAINS rather than being ranked low.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from genesis.prioritization import (                       # noqa: E402
    SIGNIFICANCE_LABELS,
    PrioritizedOpportunity,
    prioritize,
    significance_of,
)
from reality_mesh.models import OpportunityHypothesisPacket, ThemePulse   # noqa: E402
from reality_mesh.validation import assert_no_trade_fields               # noqa: E402


def _pulse(i, **kw):
    d = dict(theme_pulse_id="tp-%s" % i, theme_id="t-%s" % i, theme_name="Theme %s" % i,
             state="Igniting", bottleneck_label="major", confidence_label="high",
             freshness_label="fresh", supporting_signals=("s1", "s2", "s3"))
    d.update(kw)
    return ThemePulse(**d)


def _packet(i, **kw):
    d = dict(hypothesis_id="h-%s" % i, theme_pulse="tp-%s" % i, opportunity_summary="x",
             confidence_label="high", beneficiary_candidates=("A", "B", "C", "D"),
             source_refs=("sec:1", "sec:2", "sec:3", "sec:4"),
             supporting_evidence_refs=("e1", "e2", "e3", "e4", "e5"))
    d.update(kw)
    return OpportunityHypothesisPacket(**d)


class ItExpressesSignificanceNotRecommendation(unittest.TestCase):
    def test_the_record_carries_no_score_rank_or_trade_field(self):
        # The structural guard the rest of the repo uses -- a field named *score*/*rank*/*rating*/
        # buy/sell/order could not survive this call.
        assert_no_trade_fields(PrioritizedOpportunity)

    def test_the_record_carries_no_position_or_return_field(self):
        names = set(PrioritizedOpportunity.__dataclass_fields__)
        for banned in ("position", "index", "expected_return", "upside", "multiple", "target"):
            self.assertNotIn(banned, names,
                             "a stored ordering/return field would make the judgment a fact")

    def test_the_verdict_vocabulary_is_closed(self):
        with self.assertRaises(ValueError):
            PrioritizedOpportunity(significance_label="excellent")


class ItAbstainsRatherThanGuessing(unittest.TestCase):
    def test_ungrounded_abstains(self):
        f = {"grounding": "ungrounded", "confidence": "high", "timing": "Igniting"}
        self.assertEqual(significance_of(f), "insufficient")

    def test_missing_confidence_abstains(self):
        f = {"grounding": "well_grounded", "confidence": "missing", "timing": "Igniting"}
        self.assertEqual(significance_of(f), "insufficient")

    def test_a_theme_with_nothing_to_say_abstains(self):
        f = {"grounding": "well_grounded", "confidence": "high", "timing": "Data insufficient"}
        self.assertEqual(significance_of(f), "insufficient")

    def test_an_abstention_is_placed_last_but_never_dropped(self):
        # What the system cannot yet judge is exactly what an operator most needs to see.
        pulses = [_pulse(1), _pulse(2, state="Data insufficient", confidence_label="missing")]
        packets = [_packet(1), _packet(2, confidence_label="missing", source_refs=(),
                                       supporting_evidence_refs=())]
        out = prioritize(pulses, packets)
        self.assertEqual(len(out), 2, "an abstention must stay visible")
        self.assertEqual(out[-1].theme_id, "t-2")
        self.assertEqual(out[-1].significance_label, "insufficient")

    def test_contested_evidence_can_never_be_decisive(self):
        f = {"magnitude": "extreme", "confidence": "very_high", "grounding": "well_grounded",
             "breadth": "broad", "timing": "Igniting", "uncertainty": "contested"}
        self.assertNotEqual(significance_of(f), "decisive")


class TheOrderIsExplainedNotHidden(unittest.TestCase):
    def test_a_stronger_opportunity_outranks_a_weaker_one(self):
        strong, weak = _pulse(1), _pulse(2, bottleneck_label="minor", confidence_label="low")
        out = prioritize([strong, weak],
                         [_packet(1), _packet(2, confidence_label="low",
                                              beneficiary_candidates=("A",),
                                              source_refs=("sec:1",),
                                              supporting_evidence_refs=())])
        self.assertEqual([o.theme_id for o in out], ["t-1", "t-2"])

    def test_every_placement_carries_the_factors_that_placed_it(self):
        out = prioritize([_pulse(1)], [_packet(1)])
        factors = out[0].factors
        for required in ("magnitude", "timing", "confidence", "breadth", "grounding",
                         "uncertainty"):
            self.assertIn(required, factors, "REQ-GEN-019's factor must be visible")
        self.assertTrue(out[0].why, "an order with no stated reason is a hidden score")

    def test_the_order_is_stable_not_incidental(self):
        pulses = [_pulse(1), _pulse(2), _pulse(3)]
        packets = [_packet(1), _packet(2), _packet(3)]
        first = [o.theme_id for o in prioritize(pulses, packets)]
        again = [o.theme_id for o in prioritize(list(reversed(pulses)), list(reversed(packets)))]
        self.assertEqual(first, again, "ties must break on theme_id, never on input order")


class ItStaysReEvaluable(unittest.TestCase):
    def test_it_is_a_pure_function_of_the_current_pulses(self):
        # Re-running against changed understanding must change the verdict -- nothing cached.
        before = prioritize([_pulse(1)], [_packet(1)])[0].significance_label
        after = prioritize([_pulse(1, bottleneck_label="negligible", confidence_label="very_low")],
                           [_packet(1, confidence_label="very_low",
                                    beneficiary_candidates=("A",), source_refs=("sec:1",),
                                    supporting_evidence_refs=())])[0].significance_label
        self.assertNotEqual(before, after)
        self.assertIn(before, SIGNIFICANCE_LABELS)
        self.assertIn(after, SIGNIFICANCE_LABELS)

    def test_a_packet_whose_pulse_is_absent_is_skipped_not_guessed(self):
        out = prioritize([], [_packet(9)])
        self.assertEqual(out, (), "a missing pulse is an honest gap, never an invented theme")


if __name__ == "__main__":
    unittest.main()
