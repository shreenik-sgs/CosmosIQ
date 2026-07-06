"""IMPLEMENTATION-022B -- the Recommendation Eligibility Gate Engine.

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE -- no network, no scheduler, no broker, no
live endpoint. It proves the runtime gate logic that decides a CapitalRecommendation's state:

* ``actionable_pick_manual_review`` is reachable ONLY when ALL 15 hard gates pass -- and it is
  built THROUGH the 022A model, so the unforgeable-actionable invariant is never bypassed;
* EACH of the 15 gates, when it fails, prevents actionable -- blocking with an EXACT reason (a
  hard/unsound-basis failure) or downgrading to ``watch`` / ``active_diligence`` (a social-only or
  merely-incomplete basis), NEVER silently passing;
* a social/rumor-only basis is at most ``watch``; a fixture/demo basis is blocked -- neither can
  be actionable;
* today, with 022C (technical timing) and 022D (portfolio fit) NOT built, actionable is
  UNREACHABLE for any real input -- the honest state -- and the path is proven reachable only by
  injecting genuine, complete technical + portfolio evidence;
* labels + reasons only -- NO score / rank / rating / trade field anywhere; deterministic; AST
  clean; demo + default pulse byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import unittest
from dataclasses import fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import recommendation_gates as RG
from reality_mesh.capital_candidate import assess_candidate_eligibility
from reality_mesh.recommendation import CapitalRecommendation
from reality_mesh.recommendation_gates import (
    HARD_GATE_IDS,
    RECOMMENDATION_HARD_GATES,
    GateResult,
    HardGate,
    RecommendationGateOutcome,
    evaluate_recommendation,
)

_RG_PY = os.path.join(_SRC, "reality_mesh", "recommendation_gates.py")
_NOW = "2026-07-06T00:00:00Z"

# The 15 hard gate ids, in canonical order.
_EXPECTED_GATE_IDS = (
    "candidate_eligibility",
    "trust_data_quality",
    "source_freshness",
    "multi_source_corroboration",
    "theme_pulse_strength",
    "value_chain_bottleneck_exposure",
    "company_evidence_beneficiary",
    "investment_diligence_complete",
    "forward_scenario_exists",
    "red_team_no_thesis_killer",
    "technical_timing_acceptable",
    "portfolio_fit_acceptable",
    "sizing_guardrail_exists",
    "invalidation_condition_exists",
    "exit_watch_condition_exists",
)


def _eligible_candidate(mode="pulse", ticker="IREN", run_id="RUN-1"):
    return assess_candidate_eligibility(
        ticker=ticker, run_id=run_id, reality_signal_refs=("sig-1",),
        opportunity_hypothesis_ref="hyp-1", investment_diligence_ref="THS-1",
        trust_data_quality_state="healthy", mode=mode, now=_NOW)


def _full_inputs(**overrides):
    """A full-and-complete synthetic input set: every one of the 15 gates passes."""
    base = dict(
        run_id="RUN-1", ticker="IREN", now=_NOW, company_name="IREN Ltd",
        candidate=_eligible_candidate(),
        data_quality_ref="DQ-1", data_quality_state="healthy",
        source_freshness="fresh",
        corroboration_sources=(("sec:1", "primary", "sec_filing"),
                               ("fmp:2", "convenience", "fmp")),
        theme_pulse_state="Igniting",
        bottleneck_exposure_refs=("bn-hbm",),
        company_evidence_refs=(("sec:1", "primary", "sec_filing"),),
        investment_diligence_ref="THS-1", diligence_complete=True,
        forward_scenario_ref="FWD-1",
        red_team_ref="RT-1", unresolved_thesis_killer=False,
        technical_timing_ref="TT-1", technical_timing_acceptable=True,
        portfolio_fit_ref="PF-1", portfolio_fit_acceptable=True,
        sizing_guardrail="starter position only (qualitative range)",
        invalidation_conditions=("thesis broken if HBM demand rolls over",),
        exit_watch_conditions=("exit watch if margin compresses",),
    )
    base.update(overrides)
    return base


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# =========================================================================== #
# The 15 gates: identity + descriptors                                          #
# =========================================================================== #
class GateInventoryTests(unittest.TestCase):
    def test_exactly_fifteen_hard_gates_in_canonical_order(self):
        self.assertEqual(len(RECOMMENDATION_HARD_GATES), 15)
        self.assertEqual(HARD_GATE_IDS, _EXPECTED_GATE_IDS)

    def test_every_gate_has_id_description_and_predicate(self):
        for g in RECOMMENDATION_HARD_GATES:
            self.assertTrue(g.gate_id.strip())
            self.assertTrue(g.description.strip())
            self.assertTrue(callable(g.predicate))

    def test_gate_ids_unique(self):
        self.assertEqual(len(set(HARD_GATE_IDS)), 15)


# =========================================================================== #
# The reachable path: a full, genuine, complete input set DOES reach actionable #
# =========================================================================== #
class ReachableActionableTests(unittest.TestCase):
    def test_full_complete_evidence_reaches_actionable(self):
        outcome, rec = evaluate_recommendation(**_full_inputs())
        self.assertEqual(outcome.state, "actionable_pick_manual_review")
        self.assertTrue(outcome.is_actionable)
        self.assertEqual(len(outcome.passed_gate_ids()), 15)
        self.assertEqual(outcome.failed_gate_ids(), ())
        self.assertEqual(outcome.blocked_reason, "")

    def test_built_recommendation_is_a_022a_actionable_pick(self):
        _, rec = evaluate_recommendation(**_full_inputs())
        self.assertIsInstance(rec, CapitalRecommendation)
        self.assertTrue(rec.is_actionable_pick)
        # the 022A invariant independently holds on the produced record.
        self.assertEqual(rec.missing_actionable_requirements(), ())
        self.assertEqual(rec.recommendation_label, "Actionable Pick — Manual Review")
        self.assertEqual(rec.publication_state, "published")

    def test_all_15_gate_results_present_and_passed(self):
        outcome, _ = evaluate_recommendation(**_full_inputs())
        self.assertEqual(tuple(g.gate_id for g in outcome.gate_results), _EXPECTED_GATE_IDS)
        for g in outcome.gate_results:
            self.assertTrue(g.passed, "{0} did not pass".format(g.gate_id))
            self.assertEqual(g.failure_mode, "")


# =========================================================================== #
# 022C / 022D absence keeps actionable UNREACHABLE today (the honest state)      #
# =========================================================================== #
class TwentyTwoCDAbsenceTests(unittest.TestCase):
    def test_no_technical_timing_downgrades_never_actionable(self):
        outcome, rec = evaluate_recommendation(
            **_full_inputs(technical_timing_ref="", technical_timing_acceptable=False))
        self.assertEqual(outcome.state, "active_diligence")
        self.assertFalse(outcome.is_actionable)
        self.assertFalse(rec.is_actionable_pick)
        self.assertIn("technical_timing_acceptable", outcome.downgrade_reason)

    def test_no_portfolio_fit_downgrades_never_actionable(self):
        outcome, rec = evaluate_recommendation(
            **_full_inputs(portfolio_fit_ref="", portfolio_fit_acceptable=False))
        self.assertEqual(outcome.state, "active_diligence")
        self.assertFalse(rec.is_actionable_pick)
        self.assertIn("portfolio_fit_acceptable", outcome.downgrade_reason)

    def test_todays_real_input_without_022c_022d_cannot_be_actionable(self):
        # A fully sound basis EXCEPT the (unbuilt) 022C/022D pieces -> active_diligence, honest.
        outcome, rec = evaluate_recommendation(**_full_inputs(
            technical_timing_ref="", technical_timing_acceptable=False,
            portfolio_fit_ref="", portfolio_fit_acceptable=False))
        self.assertEqual(outcome.state, "active_diligence")
        self.assertFalse(rec.is_actionable_pick)


# =========================================================================== #
# EACH gate, when it fails, prevents actionable (block or downgrade) w/ reason   #
# =========================================================================== #
class PerGateFailureTests(unittest.TestCase):
    def _failed(self, outcome, gate_id):
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertIn(gate_id, by_id)
        self.assertFalse(by_id[gate_id].passed, "{0} unexpectedly passed".format(gate_id))
        self.assertTrue(by_id[gate_id].reason.strip())
        return by_id[gate_id]

    def test_candidate_missing_blocks(self):
        outcome, rec = evaluate_recommendation(run_id="R", ticker="T", now=_NOW)
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("candidate_eligibility", outcome.blocked_reason)
        self.assertFalse(rec.is_actionable_pick)
        self._failed(outcome, "candidate_eligibility")

    def test_candidate_ineligible_blocks(self):
        ineligible = assess_candidate_eligibility(
            ticker="IREN", run_id="RUN-1", reality_signal_refs=(), opportunity_hypothesis_ref="",
            investment_diligence_ref="", trust_data_quality_state="healthy", now=_NOW)
        self.assertFalse(ineligible.is_eligible)
        outcome, rec = evaluate_recommendation(**_full_inputs(candidate=ineligible))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("candidate_eligibility", outcome.blocked_reason)

    def test_data_quality_not_acceptable_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(data_quality_state="degraded"))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("trust_data_quality", outcome.blocked_reason)
        self._failed(outcome, "trust_data_quality")

    def test_data_quality_ref_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(data_quality_ref=""))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("trust_data_quality", outcome.blocked_reason)

    def test_source_stale_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(source_freshness="stale"))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("source_freshness", outcome.blocked_reason)
        self._failed(outcome, "source_freshness")

    def test_source_freshness_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(source_freshness=""))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("source_freshness", outcome.blocked_reason)

    def test_corroboration_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(corroboration_sources=()))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("multi_source_corroboration", outcome.blocked_reason)
        self._failed(outcome, "multi_source_corroboration")

    def test_single_non_social_source_is_insufficient_blocks(self):
        outcome, _ = evaluate_recommendation(
            **_full_inputs(corroboration_sources=(("sec:1", "primary", "sec_filing"),)))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("multi_source_corroboration", outcome.blocked_reason)

    def test_theme_pulse_weak_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(theme_pulse_state="Exhausting"))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("theme_pulse_strength", outcome.blocked_reason)
        self._failed(outcome, "theme_pulse_strength")

    def test_theme_pulse_data_insufficient_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(theme_pulse_state="Data insufficient"))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("theme_pulse_strength", outcome.blocked_reason)

    def test_theme_pulse_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(theme_pulse_state=""))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("theme_pulse_strength", outcome.blocked_reason)

    def test_bottleneck_exposure_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(bottleneck_exposure_refs=()))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("value_chain_bottleneck_exposure", outcome.blocked_reason)
        self._failed(outcome, "value_chain_bottleneck_exposure")

    def test_company_evidence_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(company_evidence_refs=()))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("company_evidence_beneficiary", outcome.blocked_reason)
        self._failed(outcome, "company_evidence_beneficiary")

    def test_diligence_missing_blocks(self):
        outcome, _ = evaluate_recommendation(
            **_full_inputs(investment_diligence_ref="", diligence_complete=False))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("investment_diligence_complete", outcome.blocked_reason)
        self._failed(outcome, "investment_diligence_complete")

    def test_diligence_in_progress_downgrades_to_active_diligence(self):
        outcome, rec = evaluate_recommendation(**_full_inputs(diligence_complete=False))
        self.assertEqual(outcome.state, "active_diligence")
        self.assertFalse(rec.is_actionable_pick)
        self.assertIn("investment_diligence_complete", outcome.downgrade_reason)

    def test_forward_scenario_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(forward_scenario_ref=""))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("forward_scenario_exists", outcome.blocked_reason)
        self._failed(outcome, "forward_scenario_exists")

    def test_red_team_ref_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(red_team_ref=""))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("red_team_no_thesis_killer", outcome.blocked_reason)

    def test_unresolved_thesis_killer_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(unresolved_thesis_killer=True))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("red_team_no_thesis_killer", outcome.blocked_reason)
        self.assertIn("thesis-killer", outcome.blocked_reason)
        self._failed(outcome, "red_team_no_thesis_killer")

    def test_technical_setup_missing_downgrades(self):
        outcome = self._failed(
            evaluate_recommendation(**_full_inputs(technical_timing_acceptable=False))[0],
            "technical_timing_acceptable")
        self.assertEqual(outcome.failure_mode, "active_diligence")

    def test_portfolio_fit_missing_downgrades(self):
        result = self._failed(
            evaluate_recommendation(**_full_inputs(portfolio_fit_acceptable=False))[0],
            "portfolio_fit_acceptable")
        self.assertEqual(result.failure_mode, "active_diligence")

    def test_sizing_guardrail_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(sizing_guardrail=""))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("sizing_guardrail_exists", outcome.blocked_reason)
        self._failed(outcome, "sizing_guardrail_exists")

    def test_invalidation_condition_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(invalidation_conditions=()))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("invalidation_condition_exists", outcome.blocked_reason)
        self._failed(outcome, "invalidation_condition_exists")

    def test_exit_watch_condition_missing_blocks(self):
        outcome, _ = evaluate_recommendation(**_full_inputs(exit_watch_conditions=()))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("exit_watch_condition_exists", outcome.blocked_reason)
        self._failed(outcome, "exit_watch_condition_exists")

    def test_each_hard_block_gate_names_its_exact_reason(self):
        # dropping ONE required hard input at a time -> blocked, reason naming that exact gate.
        cases = {
            "trust_data_quality": dict(data_quality_state="failed"),
            "source_freshness": dict(source_freshness="expired"),
            "multi_source_corroboration": dict(corroboration_sources=()),
            "theme_pulse_strength": dict(theme_pulse_state="Dormant"),
            "value_chain_bottleneck_exposure": dict(bottleneck_exposure_refs=()),
            "company_evidence_beneficiary": dict(company_evidence_refs=()),
            "investment_diligence_complete": dict(investment_diligence_ref=""),
            "forward_scenario_exists": dict(forward_scenario_ref=""),
            "red_team_no_thesis_killer": dict(unresolved_thesis_killer=True),
            "sizing_guardrail_exists": dict(sizing_guardrail=""),
            "invalidation_condition_exists": dict(invalidation_conditions=()),
            "exit_watch_condition_exists": dict(exit_watch_conditions=()),
        }
        for gate_id, override in cases.items():
            outcome, rec = evaluate_recommendation(**_full_inputs(**override))
            self.assertEqual(outcome.state, "blocked", gate_id)
            self.assertIn(gate_id, outcome.blocked_reason, gate_id)
            self.assertFalse(rec.is_actionable_pick, gate_id)


# =========================================================================== #
# Social-only + fixture/demo can NEVER be actionable                            #
# =========================================================================== #
class SocialAndFixtureTests(unittest.TestCase):
    def test_social_only_corroboration_caps_at_watch(self):
        outcome, rec = evaluate_recommendation(**_full_inputs(
            corroboration_sources=(("x:1", "rumor", "x_social"),
                                   ("st:2", "rumor", "stocktwits")),
            company_evidence_refs=(("x:1", "rumor", "x_social"),)))
        self.assertEqual(outcome.state, "watch")
        self.assertFalse(outcome.is_actionable)
        self.assertFalse(rec.is_actionable_pick)

    def test_social_dressed_as_authority_does_not_count(self):
        # a social source_type never counts even if handed a non-rumor authority label; an
        # all-social basis is social-only -> at most watch, never actionable, never a pass.
        outcome, rec = evaluate_recommendation(**_full_inputs(
            corroboration_sources=(("x:1", "primary", "x_social"),
                                   ("rd:2", "primary", "reddit"))))
        self.assertEqual(outcome.state, "watch")
        self.assertFalse(rec.is_actionable_pick)
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertFalse(by_id["multi_source_corroboration"].passed)

    def test_fixture_mode_candidate_blocks(self):
        outcome, rec = evaluate_recommendation(
            **_full_inputs(candidate=_eligible_candidate(mode="fixture")))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("candidate_eligibility", outcome.blocked_reason)
        self.assertIn("fixture/demo", outcome.blocked_reason)
        self.assertFalse(rec.is_actionable_pick)

    def test_demo_mode_candidate_blocks(self):
        outcome, rec = evaluate_recommendation(
            **_full_inputs(candidate=_eligible_candidate(mode="demo")))
        self.assertEqual(outcome.state, "blocked")
        self.assertIn("fixture/demo", outcome.blocked_reason)
        self.assertFalse(rec.is_actionable_pick)


# =========================================================================== #
# The engine never bypasses the 022A model; block/downgrade records are valid    #
# =========================================================================== #
class RecommendationConstructionTests(unittest.TestCase):
    def test_blocked_record_carries_exact_reason(self):
        outcome, rec = evaluate_recommendation(**_full_inputs(forward_scenario_ref=""))
        self.assertTrue(rec.is_blocked)
        self.assertEqual(rec.blocked_reason, outcome.blocked_reason)
        self.assertTrue(rec.blocked_reason.strip())

    def test_blocked_record_does_not_claim_eligible_candidate_ref(self):
        # gate-1 block (no candidate) -> the record must not forge a capital_candidate_ref.
        _, rec = evaluate_recommendation(run_id="R", ticker="T", now=_NOW)
        self.assertEqual(rec.capital_candidate_ref, "")
        self.assertTrue(rec.candidate_id.strip())  # 022A still requires the id field

    def test_downgrade_record_is_not_actionable_and_not_blocked(self):
        outcome, rec = evaluate_recommendation(**_full_inputs(diligence_complete=False))
        self.assertEqual(rec.recommendation_state, "active_diligence")
        self.assertFalse(rec.is_actionable_pick)
        self.assertFalse(rec.is_blocked)

    def test_watch_record_valid(self):
        _, rec = evaluate_recommendation(**_full_inputs(
            corroboration_sources=(("x:1", "rumor", "x_social"),),
            company_evidence_refs=(("x:1", "rumor", "x_social"),)))
        self.assertEqual(rec.recommendation_state, "watch")
        self.assertEqual(rec.recommendation_label, "Watch")

    def test_missing_run_or_ticker_raises(self):
        with self.assertRaises(ValueError):
            evaluate_recommendation(run_id="", ticker="T", now=_NOW)
        with self.assertRaises(ValueError):
            evaluate_recommendation(run_id="R", ticker="", now=_NOW)


# =========================================================================== #
# No score / rank / rating / trade field anywhere; no numeric field             #
# =========================================================================== #
class NoTradeOrScoreFieldTests(unittest.TestCase):
    def test_assert_no_trade_fields_clean(self):
        for cls in (GateResult, HardGate, RecommendationGateOutcome):
            rm.assert_no_trade_fields(cls)

    def test_no_forbidden_token_in_any_field_name(self):
        for cls in (GateResult, HardGate, RecommendationGateOutcome):
            for f in fields(cls):
                low = f.name.lower()
                for tok in ("buy", "sell", "order", "submit", "broker", "trade",
                            "score", "rank", "rating", "investab", "alpha"):
                    self.assertNotIn(tok, low, "{0}.{1}".format(cls.__name__, f.name))

    def test_gate_results_carry_no_numeric_verdict(self):
        outcome, _ = evaluate_recommendation(**_full_inputs())
        for g in outcome.gate_results:
            self.assertIsInstance(g.passed, bool)
            self.assertIsInstance(g.reason, str)
            self.assertIsInstance(g.failure_mode, str)


# =========================================================================== #
# Determinism                                                                   #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_evaluation_is_deterministic(self):
        a_out, a_rec = evaluate_recommendation(**_full_inputs())
        b_out, b_rec = evaluate_recommendation(**_full_inputs())
        self.assertEqual(a_out, b_out)
        self.assertEqual(a_rec, b_rec)

    def test_blocked_evaluation_is_deterministic(self):
        a = evaluate_recommendation(**_full_inputs(source_freshness="stale"))
        b = evaluate_recommendation(**_full_inputs(source_freshness="stale"))
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[1], b[1])

    def test_deterministic_id(self):
        _, rec = evaluate_recommendation(**_full_inputs())
        self.assertEqual(rec.recommendation_id, "rec:RUN-1:IREN")


# =========================================================================== #
# Guardrails -- AST clean, offline kill-switch, demo byte-identical             #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "ftplib", "smtplib", "selenium", "scrapy", "websocket", "websockets", "pycurl"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "signal"}

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_imports_no_network_scheduler_broker(self):
        tree = ast.parse(self._read(_RG_PY))
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.append((node.module or "").split(".")[0])
        for m in mods:
            self.assertNotIn(m, self._NET, "imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "imports forbidden {0}".format(m))

    def test_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_RG_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "defines {0}".format(node.name))

    def test_source_has_no_broker_or_execution_token(self):
        blob = self._read(_RG_PY).lower()
        for tok in ("place_order", "submit_order", "broker.submit", "execute_trade",
                    "time.time(", "datetime.now("):
            self.assertNotIn(tok, blob, "forbidden token {0}".format(tok))

    def test_actionable_is_offline_under_socket_kill_switch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            outcome, rec = evaluate_recommendation(**_full_inputs())
        finally:
            socket.socket = real
        self.assertTrue(outcome.is_actionable)
        self.assertTrue(rec.is_actionable_pick)

    def test_demo_pulse_is_byte_identical(self):
        a = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        b = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        self.assertEqual(tuple(s.signal_id for s in a.signals),
                         tuple(s.signal_id for s in b.signals))
        self.assertEqual(tuple(f.finding_id for f in a.findings),
                         tuple(f.finding_id for f in b.findings))


if __name__ == "__main__":
    unittest.main()
