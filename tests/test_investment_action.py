from __future__ import annotations

import os as _os, sys as _sys
_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import copy
import dataclasses
import unittest

from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis
from prometheus.diligence_inputs import CandidateInput, DiligenceInputs
from prometheus.investment_thesis import generate_investment_thesis, InvestmentThesis
from prometheus.investment_action import (
    generate_investment_action,
    InvestmentAction,
)
from execution_manual.manual_execution_intent import ManualExecutionIntent
from prometheus.position_lifecycle import PositionContext
from runtime.vertical_slice_runner import (
    iren_source_observations,
    iren_diligence_inputs,
    run_iren_slice,
)

DOMAIN = "ai-infrastructure"
NOW = 1_700_000_000.0

_FORBIDDEN = (
    "buy", "sell", " hold", "order", "broker", "trade ticket", "limit price",
    "market order", "stop order", "shares to buy", "option contracts",
    "allocation amount", "position size", "execute", "submit",
)
_CANDIDATE_VOCAB = (
    "enter_candidate", "add_candidate", "trim_candidate", "exit_candidate",
    "rotate_candidate", "wait", "monitor", "avoid", "candidate", "timing",
    "lifecycle",
)


def _hypothesis(now=NOW):
    obs = iren_source_observations(now)
    ia = generate_intelligence_assessment(obs, domain=DOMAIN, actor="t", now=now)
    return generate_opportunity_hypothesis([ia], domain=DOMAIN, actor="t", now=now)


def _base_candidate():
    return iren_diligence_inputs().candidates[0]


def _thesis_from(candidate, now=NOW):
    oh = _hypothesis(now)
    di = DiligenceInputs(domain=DOMAIN, candidates=(candidate,))
    return generate_investment_thesis(oh, di, actor="prometheus", now=now)


def _base_thesis(now=NOW):
    return generate_investment_thesis(_hypothesis(now), iren_diligence_inputs(),
                                      actor="prometheus", now=now)


def _weak_chart_thesis():
    # Strong thesis, but the chart does not confirm (volume fails) -> thesis_worthy.
    c = dataclasses.replace(_base_candidate(), volume_recent=900_000.0)
    return _thesis_from(c)


def _watch_thesis():
    # Weak fundamental inflection (< 0.40) -> watch downgrade; chart stays strong.
    # (A barely-positive inflection with inline guidance, not a decline -- a decline
    # would trip the bubble archetype and push the thesis to not_investable.)
    c = dataclasses.replace(
        _base_candidate(),
        revenue=210.0, prior_revenue=200.0,
        gross_margin=0.50, prior_gross_margin=0.50,
        guidance="inline",
    )
    return _thesis_from(c)


def _poor_asymmetry_thesis():
    # Tiny upside vs real downside -> poor asymmetry -> not_investable.
    c = dataclasses.replace(_base_candidate(), bull_price=10.50, extreme_bull_price=11.0)
    return _thesis_from(c)


def _severe_dilution_thesis():
    # High dilution -> red-team FAIL (without poor asymmetry) -> not_investable.
    c = dataclasses.replace(_base_candidate(), dilution_risk="high")
    return _thesis_from(c)


class TestInvestmentAction(unittest.TestCase):
    # --- validation ---------------------------------------------------------
    def test_investment_action_requires_investment_thesis(self):
        with self.assertRaises(ValueError):
            generate_investment_action(object(), now=NOW)
        with self.assertRaises(ValueError):
            generate_investment_action(_hypothesis(), now=NOW)

    # --- thesis-level decision rules ---------------------------------------
    def test_not_investable_thesis_becomes_avoid_or_monitor(self):
        action = generate_investment_action(_poor_asymmetry_thesis(), now=NOW)
        self.assertEqual(action.source_thesis_components["investability"], "not_investable")
        self.assertIn(action.action_type, ("avoid", "monitor"))
        self.assertNotEqual(action.action_type, "enter_candidate")

    def test_watch_thesis_becomes_monitor_or_wait(self):
        t = _watch_thesis()
        self.assertEqual(t.investability_assessment, "watch")
        action = generate_investment_action(t, now=NOW)
        self.assertIn(action.action_type, ("monitor", "wait"))
        self.assertNotEqual(action.action_type, "enter_candidate")

    def test_thesis_worthy_without_timing_confirmation_becomes_wait(self):
        t = _weak_chart_thesis()
        self.assertEqual(t.investability_assessment, "thesis_worthy")
        self.assertFalse(t.timing_confirmation)
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(action.action_type, "wait")
        self.assertEqual(action.action_status, "thesis_worthy_wait")

    def test_thesis_worthy_timing_confirmed_becomes_enter_candidate(self):
        t = _base_thesis()
        self.assertEqual(t.investability_assessment, "thesis_worthy_timing_confirmed")
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(action.action_type, "enter_candidate")
        self.assertEqual(action.action_status, "timing_confirmed_candidate")
        self.assertEqual(action.urgency, "high")

    def test_strong_chart_weak_thesis_does_not_become_enter_candidate(self):
        # The watch thesis keeps a strong, confirming chart but a weak thesis.
        t = _watch_thesis()
        self.assertTrue(t.technical_inflection_summary.technical_confirmation)
        action = generate_investment_action(t, now=NOW)
        self.assertNotEqual(action.action_type, "enter_candidate")

    def test_poor_asymmetry_blocks_enter_candidate(self):
        t = _poor_asymmetry_thesis()
        self.assertEqual(t.asymmetry_summary.asymmetry_label, "poor")
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(action.action_type, "avoid")
        self.assertIn("poor risk/reward asymmetry", action.blocking_conditions)

    def test_red_team_fail_blocks_enter_candidate(self):
        t = _severe_dilution_thesis()
        self.assertEqual(t.red_team_summary.red_team_verdict, "fail")
        self.assertNotEqual(t.asymmetry_summary.asymmetry_label, "poor")
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(action.action_type, "avoid")
        self.assertIn("red-team verdict: fail", action.blocking_conditions)

    def test_severe_dilution_blocks_or_downgrades_action(self):
        action = generate_investment_action(_severe_dilution_thesis(), now=NOW)
        self.assertIn(action.action_type, ("avoid", "monitor", "trim_candidate", "exit_candidate"))
        self.assertNotEqual(action.action_type, "enter_candidate")

    # --- position-context decision rules -----------------------------------
    def test_invalidation_trigger_creates_invalidated_or_exit_candidate(self):
        ctx = PositionContext(has_position=True, invalidation_triggered=True)
        action = generate_investment_action(_base_thesis(), position_context=ctx, now=NOW)
        self.assertIn(action.action_type, ("exit_candidate", "avoid"))
        self.assertEqual(action.action_status, "invalidated")
        self.assertEqual(action.lifecycle_state, "invalidated")

    def test_no_position_context_prevents_add_trim_exit(self):
        action = generate_investment_action(_base_thesis(), now=NOW)
        self.assertEqual(action.action_type, "enter_candidate")
        for forbidden in ("add_candidate", "trim_candidate", "exit_candidate", "rotate_candidate"):
            self.assertNotEqual(action.action_type, forbidden)

    def test_existing_position_context_allows_add_trim_exit_candidates(self):
        improving = PositionContext(has_position=True, thesis_direction="improving")
        add = generate_investment_action(_base_thesis(), position_context=improving, now=NOW)
        self.assertEqual(add.action_type, "add_candidate")

        held = PositionContext(has_position=True)
        exit_action = generate_investment_action(_severe_dilution_thesis(),
                                                 position_context=held, now=NOW)
        self.assertEqual(exit_action.action_type, "exit_candidate")
        self.assertEqual(exit_action.action_status, "risk_reduction_candidate")

        trim = generate_investment_action(_watch_thesis(), position_context=held, now=NOW)
        self.assertEqual(trim.action_type, "trim_candidate")

    def test_rotation_requires_comparative_thesis(self):
        held = PositionContext(has_position=True, thesis_direction="stable")
        current = _weak_chart_thesis()  # thesis_worthy, not deteriorating, not confirmed
        superior = _base_thesis()       # confirmed + higher confidence

        with_comp = generate_investment_action(
            current, position_context=held, comparative_thesis=superior, now=NOW)
        self.assertEqual(with_comp.action_type, "rotate_candidate")

        without_comp = generate_investment_action(current, position_context=held, now=NOW)
        self.assertNotEqual(without_comp.action_type, "rotate_candidate")

    # --- provenance / immutability -----------------------------------------
    def test_action_preserves_thesis_provenance(self):
        t = _base_thesis()
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(action.source_thesis_id, t.id)
        self.assertEqual(action.source_thesis_version, t.version)
        self.assertIn(t.id, {r.object_id for r in action.provenance.sources})
        ref = next(r for r in action.provenance.sources if r.object_id == t.id)
        self.assertEqual(ref.version, t.version)

    def test_action_preserves_upstream_observation_ids(self):
        t = _base_thesis()
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(set(action.upstream_observation_ids), set(t.upstream_observation_ids))
        self.assertTrue(action.upstream_observation_ids)

    def test_action_does_not_mutate_thesis(self):
        t = _base_thesis()
        snapshot = copy.deepcopy(t)
        generate_investment_action(t, now=NOW)
        generate_investment_action(t, position_context=PositionContext(has_position=True),
                                   now=NOW)
        self.assertEqual(t, snapshot)

    # --- boundary purity ----------------------------------------------------
    def test_action_has_no_broker_order_trade_ticket_fields(self):
        fields = set(InvestmentAction.__dataclass_fields__.keys())
        for bad in ("broker", "broker_order_id", "order", "order_type", "ticket",
                    "side", "quantity", "limit_price", "stop_price"):
            self.assertNotIn(bad, fields)

    def test_action_has_no_allocation_or_position_size_fields(self):
        fields = set(InvestmentAction.__dataclass_fields__.keys())
        for bad in ("intended_allocation", "allocation", "position_size", "quantity", "size"):
            self.assertNotIn(bad, fields)

    def test_action_does_not_modify_kriya(self):
        # No Investment Action / position-lifecycle module imports the execution
        # (Kriya) layer -- the action is cognition, never actuation.
        import prometheus.investment_action as ia_mod
        import prometheus.position_lifecycle as pl_mod
        for mod in (ia_mod, pl_mod):
            with open(mod.__file__) as fh:
                src = fh.read().lower()
            self.assertNotIn("import execution_manual", src)
            self.assertNotIn("from execution_manual", src)

    def test_action_text_has_no_order_or_allocation_leakage(self):
        # Build actions across several scenarios and check every synthesised field.
        held = PositionContext(has_position=True, thesis_direction="improving")
        actions = [
            generate_investment_action(_base_thesis(), now=NOW),
            generate_investment_action(_weak_chart_thesis(), now=NOW),
            generate_investment_action(_watch_thesis(), now=NOW),
            generate_investment_action(_poor_asymmetry_thesis(), now=NOW),
            generate_investment_action(_severe_dilution_thesis(), now=NOW),
            generate_investment_action(_base_thesis(), position_context=held, now=NOW),
        ]
        for action in actions:
            blob = " ".join([
                action.action_rationale, action.action_type, action.action_status,
                action.lifecycle_state, action.security_or_instrument_mapping,
                " ".join(action.required_conditions), " ".join(action.blocking_conditions),
                " ".join(action.invalidation_conditions), " ".join(action.monitoring_signals),
                " ".join(action.review_triggers),
            ]).lower()
            for term in _FORBIDDEN:
                self.assertNotIn(term, blob,
                                 msg="leaked forbidden term {0!r} in {1}".format(
                                     term, action.action_type))

    def test_action_may_carry_candidate_vocabulary(self):
        action = generate_investment_action(_base_thesis(), now=NOW)
        blob = " ".join([action.action_rationale, action.action_type,
                         action.lifecycle_state]).lower()
        self.assertTrue(any(v in blob for v in _CANDIDATE_VOCAB))

    # --- slice integration --------------------------------------------------
    def test_vertical_slice_iren_generates_real_investment_action(self):
        r = run_iren_slice()
        self.assertIsInstance(r.action, InvestmentAction)
        self.assertNotIsInstance(r.action, ManualExecutionIntent)
        self.assertEqual(r.action.action_type, "enter_candidate")
        self.assertEqual(r.action.action_status, "timing_confirmed_candidate")
        self.assertEqual(r.action.source_thesis_id, r.thesis.id)
        self.assertEqual(r.action.security_or_instrument_mapping, "IREN")
        # The real action carries no allocation; the slice still threads a ticket.
        self.assertNotIn("intended_allocation", InvestmentAction.__dataclass_fields__)
        self.assertEqual(r.ticket_preview1.quantity, 200)


if __name__ == "__main__":
    unittest.main()
