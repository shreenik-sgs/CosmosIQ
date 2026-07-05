"""IMPLEMENTATION-020F -- the Production 24x7 Activation Gate CORE. OFFLINE, deterministic.

Proves the gate is genuinely UNFAKEABLE: production_mode_allowed cannot be True with any blocking
checklist failure, without every precondition, or without an explicit valid operator approval.
The manual items (live source health, operator shadow validation, operator sign-off) block an
honest OFFLINE evaluation, so it lands at "shadow 24x7 only". The promotion state machine refuses
any auto / unapproved jump to production; rollback always downgrades.

Every path is offline (a socket kill-switch is armed for the whole module) and deterministic
(``now`` is injected).
"""

from __future__ import annotations

import socket
import unittest

from cosmosiq_service.activation import (
    ChecklistItem,
    ChecklistStatus,
    OperatorApproval,
    Verdict,
    CheckResult,
    build_activation_checklist,
    can_enter_production,
    evaluate_activation,
    is_valid_approval,
    promote,
    rollback,
    ROLLBACK_TRIGGERS,
    SECTIONS,
)
from cosmosiq_service.service import ServiceMode, can_enter_production_continuous, ServiceConfig

_NOW = "2026-06-29T00:00:00Z"

# The three items that CANNOT be machine-verified OFFLINE (manual, blocking).
_MANUAL_ITEMS = ("live_source_health", "operator_shadow_validation", "operator_signoff")

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: the 020F activation gate must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _valid_approval():
    return OperatorApproval(approved_by="operator", approved_at=_NOW,
                            target_mode="production_24x7",
                            statement="I approve PRODUCTION_24X7 activation.")


def _machine_pass_checks():
    """Every MACHINE item marked pass (the manual items are left to default)."""
    checklist = build_activation_checklist()
    manual = set(_MANUAL_ITEMS)
    return {item.id: CheckResult(item.id, ChecklistStatus.PASS, ("ok",))
            for item in checklist.items if item.id not in manual}


def _all_pass_checks():
    """Every item pass -- including the manual items (evidence recorded)."""
    checks = _machine_pass_checks()
    for item_id in _MANUAL_ITEMS:
        checks[item_id] = CheckResult(item_id, ChecklistStatus.PASS, ("recorded",))
    return checks


def _fully_allowed_report():
    return evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                               checks=_all_pass_checks())


class ChecklistShapeTests(unittest.TestCase):
    def test_eleven_sections_and_all_items_blocking(self):
        self.assertEqual(len(SECTIONS), 11)
        checklist = build_activation_checklist()
        self.assertEqual(checklist.sections, SECTIONS)
        # every section carries at least one item; every 020F item is blocking.
        for section in SECTIONS:
            self.assertTrue(checklist.for_section(section), "empty section: " + section)
        self.assertTrue(all(i.blocking for i in checklist.items))

    def test_checklist_item_status_vocabulary_is_closed(self):
        with self.assertRaises(ValueError):
            ChecklistItem(id="x", section="Build/Test", description="d", status="green")
        with self.assertRaises(ValueError):
            ChecklistItem(id="x", section="Not A Section", description="d")


class VerdictRuleTests(unittest.TestCase):
    def test_fully_allowed_when_every_item_passes_and_approved(self):
        report = _fully_allowed_report()
        self.assertTrue(report.production_mode_allowed)
        self.assertEqual(report.verdict, Verdict.PRODUCTION_APPROVED)
        self.assertEqual(report.blocking_failures, ())
        self.assertEqual(report.manual_review_items, ())
        self.assertTrue(report.evidence_paths)

    def test_cannot_enable_with_a_blocking_checklist_failure(self):
        checks = _all_pass_checks()
        checks["secret_scan"] = CheckResult("secret_scan", ChecklistStatus.FAIL, ("planted",))
        report = evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                                     checks=checks)
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("secret_scan", report.blocking_failures)
        self.assertEqual(report.verdict, Verdict.BLOCKED)

    def test_cannot_enable_without_candidate_publication(self):
        checks = _all_pass_checks()
        checks["candidate_publication"] = CheckResult(
            "candidate_publication", ChecklistStatus.FAIL, ("no publication",))
        report = evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                                     checks=checks)
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("candidate_publication", report.blocking_failures)

    def test_cannot_enable_without_live_source_health(self):
        # every machine item passes + a valid approval, but live_source_health stays manual.
        checks = _machine_pass_checks()
        checks["operator_shadow_validation"] = CheckResult(
            "operator_shadow_validation", ChecklistStatus.PASS, ("recorded",))
        checks["operator_signoff"] = CheckResult(
            "operator_signoff", ChecklistStatus.PASS, ("recorded",))
        report = evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                                     checks=checks)
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("live_source_health", report.manual_review_items)

    def test_cannot_enable_without_service_wrapper_health(self):
        checks = _all_pass_checks()
        checks["service_wrapper_health"] = CheckResult(
            "service_wrapper_health", ChecklistStatus.FAIL, ("no health",))
        self.assertFalse(evaluate_activation(
            "store", now=_NOW, operator_approval=_valid_approval(),
            checks=checks).production_mode_allowed)

    def test_cannot_enable_without_dq_gate_success(self):
        checks = _all_pass_checks()
        checks["dq_gate_pass"] = CheckResult("dq_gate_pass", ChecklistStatus.FAIL, ("hard fail",))
        self.assertFalse(evaluate_activation(
            "store", now=_NOW, operator_approval=_valid_approval(),
            checks=checks).production_mode_allowed)

    def test_cannot_enable_without_replay_success(self):
        checks = _all_pass_checks()
        checks["replay_deterministic"] = CheckResult(
            "replay_deterministic", ChecklistStatus.FAIL, ("drift",))
        self.assertFalse(evaluate_activation(
            "store", now=_NOW, operator_approval=_valid_approval(),
            checks=checks).production_mode_allowed)

    def test_cannot_enable_without_alert_safety(self):
        checks = _all_pass_checks()
        checks["alert_safety_policy"] = CheckResult(
            "alert_safety_policy", ChecklistStatus.FAIL, ("escalation open",))
        self.assertFalse(evaluate_activation(
            "store", now=_NOW, operator_approval=_valid_approval(),
            checks=checks).production_mode_allowed)

    def test_cannot_enable_with_fixture_ticker_leakage(self):
        checks = _all_pass_checks()
        checks["fixture_leakage"] = CheckResult(
            "fixture_leakage", ChecklistStatus.FAIL, ("page /: fixture-ticker leakage 'IREN'",))
        report = evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                                     checks=checks)
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("fixture_leakage", report.blocking_failures)

    def test_cannot_enable_with_a_trade_control(self):
        checks = _all_pass_checks()
        checks["no_trade_control"] = CheckResult(
            "no_trade_control", ChecklistStatus.FAIL, ("page /: trade-affordance token 'BUY'",))
        report = evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                                     checks=checks)
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("no_trade_control", report.blocking_failures)

    def test_cannot_enable_with_a_hidden_score(self):
        checks = _all_pass_checks()
        checks["no_hidden_score"] = CheckResult(
            "no_hidden_score", ChecklistStatus.FAIL, ("hidden-score function 'compute_score'",))
        report = evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                                     checks=checks)
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("no_hidden_score", report.blocking_failures)

    def test_production_requires_explicit_operator_approval(self):
        # every item passes, but NO approval -> refused.
        report_no = evaluate_activation("store", now=_NOW, operator_approval=None,
                                        checks=_all_pass_checks())
        self.assertFalse(report_no.production_mode_allowed)
        self.assertEqual(report_no.verdict, Verdict.AWAITING_APPROVAL)
        self.assertFalse(report_no.operator_approval_valid)
        # the same everything WITH a valid approval -> allowed.
        report_yes = evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                                         checks=_all_pass_checks())
        self.assertTrue(report_yes.production_mode_allowed)

    def test_honest_offline_evaluation_lands_shadow_only(self):
        # machine all pass, manual items left to default -> refused at shadow_24x7_only.
        report = evaluate_activation("store", now=_NOW, operator_approval=_valid_approval(),
                                     checks=_machine_pass_checks())
        self.assertFalse(report.production_mode_allowed)
        self.assertEqual(report.verdict, Verdict.SHADOW_ONLY)
        self.assertEqual(report.blocking_failures, ())
        self.assertIn("live_source_health", report.manual_review_items)
        self.assertIn("operator_shadow_validation", report.manual_review_items)

    def test_bare_evaluation_refuses_everything(self):
        # no checks at all -> every machine item is pending (manual_review) -> refused.
        report = evaluate_activation("store", now=_NOW)
        self.assertFalse(report.production_mode_allowed)
        self.assertGreater(len(report.manual_review_items), 3)


class ApprovalTests(unittest.TestCase):
    def test_valid_and_invalid_approvals(self):
        self.assertTrue(is_valid_approval(_valid_approval()))
        self.assertFalse(is_valid_approval(None))
        self.assertFalse(is_valid_approval(OperatorApproval(approved_by="", approved_at=_NOW)))
        self.assertFalse(is_valid_approval(OperatorApproval(approved_by="op", approved_at="")))
        self.assertFalse(is_valid_approval(
            OperatorApproval(approved_by="op", approved_at=_NOW, target_mode="shadow_24x7")))


class PromotionTests(unittest.TestCase):
    def test_off_and_manual_to_shadow_allowed_freely(self):
        self.assertTrue(promote(ServiceMode.OFF, ServiceMode.SHADOW_24X7).allowed)
        self.assertTrue(promote(ServiceMode.MANUAL, ServiceMode.SHADOW_24X7).allowed)
        self.assertTrue(promote(ServiceMode.OFF, ServiceMode.MANUAL).allowed)

    def test_direct_jump_to_production_refused(self):
        d = promote(ServiceMode.OFF, ServiceMode.PRODUCTION_24X7,
                    report=_fully_allowed_report(), operator_approval=_valid_approval())
        self.assertFalse(d.allowed)

    def test_shadow_to_production_refused_without_report_or_approval(self):
        # no report / no approval
        self.assertFalse(promote(ServiceMode.SHADOW_24X7, ServiceMode.PRODUCTION_24X7,
                                 report=None, operator_approval=None).allowed)
        # allowing report but no approval
        self.assertFalse(promote(ServiceMode.SHADOW_24X7, ServiceMode.PRODUCTION_24X7,
                                 report=_fully_allowed_report(), operator_approval=None).allowed)
        # approval but a non-allowing report
        shadow_report = evaluate_activation("store", now=_NOW, checks=_machine_pass_checks())
        d = promote(ServiceMode.SHADOW_24X7, ServiceMode.PRODUCTION_24X7,
                    report=shadow_report, operator_approval=_valid_approval())
        self.assertFalse(d.allowed)
        self.assertTrue(d.blocking_reasons)

    def test_shadow_to_production_allowed_when_report_allows_and_approved(self):
        d = promote(ServiceMode.SHADOW_24X7, ServiceMode.PRODUCTION_24X7,
                    report=_fully_allowed_report(), operator_approval=_valid_approval())
        self.assertTrue(d.allowed)
        self.assertEqual(d.to_mode, "production_24x7")

    def test_promote_refuses_a_downgrade(self):
        self.assertFalse(promote(ServiceMode.PRODUCTION_24X7, ServiceMode.SHADOW_24X7).allowed)


class RollbackTests(unittest.TestCase):
    def test_rollback_downgrades_production_to_shadow_to_manual_to_off(self):
        self.assertTrue(rollback(ServiceMode.PRODUCTION_24X7, ServiceMode.SHADOW_24X7).allowed)
        self.assertTrue(rollback(ServiceMode.SHADOW_24X7, ServiceMode.MANUAL).allowed)
        self.assertTrue(rollback(ServiceMode.MANUAL, ServiceMode.OFF).allowed)
        # a multi-rung drop straight to OFF is allowed too.
        self.assertTrue(rollback(ServiceMode.PRODUCTION_24X7, ServiceMode.OFF).allowed)

    def test_rollback_refuses_an_upgrade(self):
        self.assertFalse(rollback(ServiceMode.OFF, ServiceMode.PRODUCTION_24X7).allowed)

    def test_rollback_triggers_are_named_with_downgrade_targets(self):
        for key in ("source_failure_spike", "agent_failure_spike", "dq_hard_fail_spike",
                    "false_positive_spike", "delivery_failure", "candidate_eligibility_bug",
                    "fixture_leakage", "secret_leakage", "unexpected_trading_control",
                    "operator_manual"):
            self.assertIn(key, ROLLBACK_TRIGGERS)
        # the hygiene/safety breaches drop all the way to OFF.
        for key in ("secret_leakage", "fixture_leakage", "unexpected_trading_control"):
            self.assertIs(ROLLBACK_TRIGGERS[key][1], ServiceMode.OFF)


class CanEnterProductionTests(unittest.TestCase):
    def test_offline_call_is_false(self):
        self.assertFalse(can_enter_production(
            "store", operator_approval=_valid_approval(), now=_NOW))

    def test_true_only_when_everything_satisfied_and_approved(self):
        self.assertTrue(can_enter_production(
            "store", operator_approval=_valid_approval(), now=_NOW, checks=_all_pass_checks()))
        # remove the approval -> False even with everything passing.
        self.assertFalse(can_enter_production(
            "store", operator_approval=None, now=_NOW, checks=_all_pass_checks()))

    def test_service_wrapper_refuses_production_offline_with_reasons(self):
        config = ServiceConfig(mode=ServiceMode.PRODUCTION_24X7, store_dir="store")
        allowed, reasons = can_enter_production_continuous(
            config, operator_approval=_valid_approval(), now=_NOW)
        self.assertFalse(allowed)
        self.assertTrue(reasons)

    def test_service_wrapper_allows_when_gate_allows(self):
        config = ServiceConfig(mode=ServiceMode.PRODUCTION_24X7, store_dir="store")
        allowed, reasons = can_enter_production_continuous(
            config, operator_approval=_valid_approval(), now=_NOW, checks=_all_pass_checks())
        self.assertTrue(allowed)
        self.assertEqual(reasons, ())


if __name__ == "__main__":
    unittest.main()
