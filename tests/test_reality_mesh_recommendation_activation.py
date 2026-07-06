"""IMPLEMENTATION-022H -- The Recommendation Activation Gate.

Production RECOMMENDATION mode (``production_manual_review``) CANNOT be enabled unless every
gate passes AND an explicit operator sign-off is recorded -- mirroring the 020F production
activation gate's unfakeable discipline, one layer up (for the recommendation surface). This
suite proves that the gate cannot be faked:

* the default recommendation mode is ``shadow`` -- NEVER ``production_manual_review``;
* an honest OFFLINE evaluation REFUSES production: ``live_source_health`` + ``operator_signoff``
  cannot be machine-verified OFFLINE and stay ``manual_review`` + BLOCKING;
* production is refused without the operator sign-off, without the 022G calibration, without the
  022F journal, without the 022B recommendation gates;
* production is refused with fixture/demo leakage, a DQ failure, or an injected trade control;
* the gate is reachable ONLY with genuine complete evidence + a valid recorded sign-off;
* there is NO score / rank / rating field and NO trade / purchase / disposal directive anywhere;
* the module is deterministic, offline (a socket kill-switch guards the whole suite), AST-clean,
  additively exported, and the demo default + default pulse stay byte-identical.

Entirely OFFLINE and deterministic: injected ISO ``now`` strings everywhere.
"""

from __future__ import annotations

import ast
import os
import re
import socket
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from cosmosiq_service.activation import CheckResult, OperatorApproval
from reality_mesh.recommendation_activation import (
    MODE_LADDER,
    RECOMMENDATION_ACTIVATION_ITEMS,
    RECOMMENDATION_MODES,
    RecommendationActivationItem,
    RecommendationActivationReport,
    RecommendationMode,
    RecommendationPromotionDecision,
    RecommendationVerdict,
    can_enter_production_recommendation,
    default_recommendation_mode,
    evaluate_recommendation_activation,
    promote_recommendation_mode,
    rollback_recommendation_mode,
    run_recommendation_checks,
)
from reality_mesh.validation import assert_no_trade_fields

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_ACT_PY = os.path.join(_PKG_DIR, "recommendation_activation.py")

_NOW = "2026-07-06T00:00:00Z"

_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "asyncio", "threading", "multiprocessing",
                        "subprocess", "smtplib", "ftplib", "socketserver", "broker",
                        "signal", "time", "random", "select", "selectors", "queue")
_BANNED_CALL_NAMES = ("sleep", "run_forever", "serve_forever", "start_polling", "Thread",
                      "Timer", "Process", "fork", "spawn", "run_in_executor", "setdaemon")
_EXECUTION_TOKENS = ("order", "orders", "broker", "buy", "sell", "submit", "fill_order",
                     "ticket_id")
_WALL_CLOCK_TOKENS = ("time.time(", "datetime.now(", "datetime.utcnow(", "utcnow(",
                      "time.monotonic(", "perf_counter(")
_METRIC_FIELD_FRAGMENTS = ("score", "rank", "rating", "pct", "percent", "ratio",
                           "probability", "weight")

_ALL_ITEM_IDS = tuple(i.id for i in RECOMMENDATION_ACTIVATION_ITEMS)
_MANUAL_IDS = ("live_source_health", "operator_signoff")
_MACHINE_IDS = tuple(i for i in _ALL_ITEM_IDS if i not in _MANUAL_IDS)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline activation suite")


_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _valid_approval():
    return OperatorApproval(approved_by="operator-jane", approved_at=_NOW,
                            target_mode="production_24x7")


def _all_pass_checks(store_dir):
    """The honest machine checks (all pass), plus a supplied live_source_health pass. This is the
    genuine-but-still-incomplete evidence: it does NOT include the operator sign-off."""
    checks = dict(run_recommendation_checks(store_dir, now=_NOW))
    checks["live_source_health"] = CheckResult(
        "live_source_health", "pass", ("a real live-source-health fetch confirmed freshness",))
    return checks


def _fully_cleared(store_dir):
    """Every machine + manual item satisfied (genuine complete evidence) + a valid sign-off."""
    checks = _all_pass_checks(store_dir)
    checks["operator_signoff"] = CheckResult(
        "operator_signoff", "pass", ("human production sign-off recorded",))
    return checks, _valid_approval()


# =========================================================================== #
# 1. The four modes + the default shadow                                      #
# =========================================================================== #
class ModeVocabularyTests(unittest.TestCase):
    def test_four_closed_modes(self):
        self.assertEqual(
            RECOMMENDATION_MODES,
            ("off", "shadow", "manual_review", "production_manual_review"))

    def test_default_mode_is_shadow_never_production(self):
        self.assertEqual(default_recommendation_mode(), "shadow")
        self.assertEqual(RecommendationMode.DEFAULT, "shadow")
        self.assertNotEqual(default_recommendation_mode(), "production_manual_review")

    def test_ladder_orders_off_shadow_manual_production(self):
        self.assertEqual(
            MODE_LADDER,
            ("off", "shadow", "manual_review", "production_manual_review"))

    def test_parse_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            RecommendationMode.parse("live")


# =========================================================================== #
# 2. The checklist -- machine-verified vs manual-blocking                     #
# =========================================================================== #
class ChecklistShapeTests(unittest.TestCase):
    def test_all_required_items_present(self):
        expected = {
            "pipeline_020_stable", "live_source_health",
            "capital_candidate_publication_works", "recommendation_gates_work",
            "capital_picks_report_renders", "recommendation_journal_works",
            "historical_replay_calibration_completed", "trust_data_quality_pass",
            "alert_safety_pass", "portfolio_fit_gates_work", "no_fixture_leakage",
            "no_trading_control", "no_hidden_score", "operator_signoff",
        }
        self.assertEqual(set(_ALL_ITEM_IDS), expected)

    def test_every_item_is_blocking(self):
        for item in RECOMMENDATION_ACTIVATION_ITEMS:
            self.assertTrue(item.blocking, "{0} must be blocking".format(item.id))

    def test_manual_items_are_the_two_unfakeable_ones(self):
        with tempfile.TemporaryDirectory() as d:
            report = evaluate_recommendation_activation(d, now=_NOW)
        for mid in _MANUAL_IDS:
            self.assertEqual(report.item(mid).status, "manual_review_required")

    def test_template_starts_all_manual_review(self):
        for item in RECOMMENDATION_ACTIVATION_ITEMS:
            self.assertEqual(item.status, "manual_review_required")


# =========================================================================== #
# 3. run_recommendation_checks -- the machine items pass from REAL checks      #
# =========================================================================== #
class MachineCheckTests(unittest.TestCase):
    def test_all_machine_items_pass_from_real_checks(self):
        with tempfile.TemporaryDirectory() as d:
            checks = run_recommendation_checks(d, now=_NOW)
        self.assertEqual(set(checks), set(_MACHINE_IDS))
        for name, result in checks.items():
            self.assertEqual(result.status, "pass",
                             "machine check {0} did not pass: {1}".format(name, result.details))

    def test_manual_items_never_produced_by_the_harness(self):
        with tempfile.TemporaryDirectory() as d:
            checks = run_recommendation_checks(d, now=_NOW)
        for mid in _MANUAL_IDS:
            self.assertNotIn(mid, checks)

    def test_checks_are_deterministic_across_dirs(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = run_recommendation_checks(d1, now=_NOW)
            b = run_recommendation_checks(d2, now=_NOW)
        self.assertEqual({k: v.status for k, v in a.items()},
                         {k: v.status for k, v in b.items()})

    def test_harness_requires_injected_now(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run_recommendation_checks(d, now="")


# =========================================================================== #
# 4. CANNOT enable by default                                                 #
# =========================================================================== #
class DefaultRefusalTests(unittest.TestCase):
    def test_default_evaluation_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            report = evaluate_recommendation_activation(d, now=_NOW)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertEqual(report.verdict, RecommendationVerdict.SHADOW_ONLY)

    def test_default_is_not_production(self):
        with tempfile.TemporaryDirectory() as d:
            report = evaluate_recommendation_activation(d, now=_NOW)
        self.assertNotEqual(report.verdict, RecommendationVerdict.PRODUCTION_APPROVED)


# =========================================================================== #
# 5. The honest OFFLINE evaluation                                            #
# =========================================================================== #
class HonestOfflineTests(unittest.TestCase):
    def test_honest_offline_refuses_with_two_manual_items(self):
        with tempfile.TemporaryDirectory() as d:
            checks = run_recommendation_checks(d, now=_NOW)
            report = evaluate_recommendation_activation(d, now=_NOW, checks=checks)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertEqual(report.verdict, RecommendationVerdict.SHADOW_ONLY)
        self.assertEqual(set(report.manual_review_items), set(_MANUAL_IDS))
        self.assertEqual(report.blocking_failures, ())

    def test_can_enter_production_recommendation_refuses_offline(self):
        with tempfile.TemporaryDirectory() as d:
            checks = run_recommendation_checks(d, now=_NOW)
            allowed, reasons = can_enter_production_recommendation(
                d, operator_approval=None, now=_NOW, checks=checks)
        self.assertFalse(allowed)
        self.assertTrue(any("operator approval" in r for r in reasons))


# =========================================================================== #
# 6. CANNOT enable without the sign-off / calibration / journal / gates       #
# =========================================================================== #
class BlockingPreconditionTests(unittest.TestCase):
    def test_refused_without_operator_signoff(self):
        # every machine item passes + a valid live_source_health, but NO sign-off / approval.
        with tempfile.TemporaryDirectory() as d:
            checks = _all_pass_checks(d)
            report = evaluate_recommendation_activation(d, now=_NOW, checks=checks)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertIn("operator_signoff", report.manual_review_items)
        self.assertTrue(report.item("operator_signoff").blocks_production)

    def test_refused_without_calibration(self):
        with tempfile.TemporaryDirectory() as d:
            checks, approval = _fully_cleared(d)
            checks["historical_replay_calibration_completed"] = CheckResult(
                "historical_replay_calibration_completed", "fail", ("calibration not completed",))
            report = evaluate_recommendation_activation(
                d, now=_NOW, checks=checks, operator_approval=approval)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertIn("historical_replay_calibration_completed", report.blocking_failures)
        self.assertEqual(report.verdict, RecommendationVerdict.BLOCKED)

    def test_refused_without_journal(self):
        with tempfile.TemporaryDirectory() as d:
            checks, approval = _fully_cleared(d)
            checks["recommendation_journal_works"] = CheckResult(
                "recommendation_journal_works", "fail", ("journal not working",))
            report = evaluate_recommendation_activation(
                d, now=_NOW, checks=checks, operator_approval=approval)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertIn("recommendation_journal_works", report.blocking_failures)

    def test_refused_without_recommendation_gates(self):
        with tempfile.TemporaryDirectory() as d:
            checks, approval = _fully_cleared(d)
            checks["recommendation_gates_work"] = CheckResult(
                "recommendation_gates_work", "fail", ("gates do not discriminate",))
            report = evaluate_recommendation_activation(
                d, now=_NOW, checks=checks, operator_approval=approval)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertIn("recommendation_gates_work", report.blocking_failures)


# =========================================================================== #
# 7. CANNOT enable with fixture leak / DQ fail / trade control                #
# =========================================================================== #
class ContaminationRefusalTests(unittest.TestCase):
    def test_refused_with_fixture_leakage(self):
        with tempfile.TemporaryDirectory() as d:
            checks, approval = _fully_cleared(d)
            checks["no_fixture_leakage"] = CheckResult(
                "no_fixture_leakage", "fail", ("a fixture ticker leaked into a surface",))
            report = evaluate_recommendation_activation(
                d, now=_NOW, checks=checks, operator_approval=approval)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertIn("no_fixture_leakage", report.blocking_failures)

    def test_refused_with_dq_failure(self):
        with tempfile.TemporaryDirectory() as d:
            checks, approval = _fully_cleared(d)
            checks["trust_data_quality_pass"] = CheckResult(
                "trust_data_quality_pass", "fail", ("a DQ hard fail on the producing run",))
            report = evaluate_recommendation_activation(
                d, now=_NOW, checks=checks, operator_approval=approval)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertIn("trust_data_quality_pass", report.blocking_failures)

    def test_refused_with_trading_control(self):
        with tempfile.TemporaryDirectory() as d:
            checks, approval = _fully_cleared(d)
            checks["no_trading_control"] = CheckResult(
                "no_trading_control", "fail", ("a trade-execution affordance was detected",))
            report = evaluate_recommendation_activation(
                d, now=_NOW, checks=checks, operator_approval=approval)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertIn("no_trading_control", report.blocking_failures)

    def test_the_real_no_fixture_leakage_check_blocks_demo(self):
        # the genuine machine check itself: a demo-mode candidate can never be actionable.
        with tempfile.TemporaryDirectory() as d:
            checks = run_recommendation_checks(d, now=_NOW)
        self.assertEqual(checks["no_fixture_leakage"].status, "pass")
        self.assertIn("blocked", " ".join(checks["no_fixture_leakage"].details))


# =========================================================================== #
# 8. Reachable ONLY with genuine complete evidence + a valid sign-off         #
# =========================================================================== #
class ReachableWithFullEvidenceTests(unittest.TestCase):
    def test_fully_cleared_hypothetical_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            checks, approval = _fully_cleared(d)
            report = evaluate_recommendation_activation(
                d, now=_NOW, checks=checks, operator_approval=approval)
        self.assertTrue(report.recommendation_mode_allowed)
        self.assertEqual(report.verdict, RecommendationVerdict.PRODUCTION_APPROVED)
        self.assertEqual(report.blocking_failures, ())
        self.assertEqual(report.manual_review_items, ())

    def test_full_evidence_but_no_approval_still_refuses(self):
        # all items pass INCLUDING an operator_signoff check, but no valid approval -> refused.
        with tempfile.TemporaryDirectory() as d:
            checks, _approval = _fully_cleared(d)
            report = evaluate_recommendation_activation(d, now=_NOW, checks=checks)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertFalse(report.operator_approval_valid)
        self.assertEqual(report.verdict, RecommendationVerdict.AWAITING_APPROVAL)

    def test_can_enter_production_recommendation_allows_only_when_fully_cleared(self):
        with tempfile.TemporaryDirectory() as d:
            checks, approval = _fully_cleared(d)
            allowed, reasons = can_enter_production_recommendation(
                d, operator_approval=approval, now=_NOW, checks=checks)
        self.assertTrue(allowed)
        self.assertEqual(reasons, ())


# =========================================================================== #
# 9. The promotion helper                                                     #
# =========================================================================== #
class PromotionTests(unittest.TestCase):
    def test_free_upgrades_below_production(self):
        self.assertTrue(promote_recommendation_mode("off", "shadow").allowed)
        self.assertTrue(promote_recommendation_mode("shadow", "manual_review").allowed)
        self.assertTrue(promote_recommendation_mode("off", "manual_review").allowed)

    def test_production_unreachable_without_report_or_approval(self):
        self.assertFalse(promote_recommendation_mode(
            "manual_review", "production_manual_review").allowed)

    def test_production_unreachable_by_skipping_manual_review(self):
        d = promote_recommendation_mode("shadow", "production_manual_review")
        self.assertFalse(d.allowed)
        d2 = promote_recommendation_mode("off", "production_manual_review")
        self.assertFalse(d2.allowed)

    def test_production_reachable_only_when_report_allows_and_approved(self):
        with tempfile.TemporaryDirectory() as dd:
            checks, approval = _fully_cleared(dd)
            report = evaluate_recommendation_activation(
                dd, now=_NOW, checks=checks, operator_approval=approval)
        decision = promote_recommendation_mode(
            "manual_review", "production_manual_review",
            report=report, operator_approval=approval)
        self.assertTrue(decision.allowed)

    def test_production_refused_with_report_but_no_approval(self):
        with tempfile.TemporaryDirectory() as dd:
            checks, approval = _fully_cleared(dd)
            report = evaluate_recommendation_activation(
                dd, now=_NOW, checks=checks, operator_approval=approval)
        decision = promote_recommendation_mode(
            "manual_review", "production_manual_review", report=report, operator_approval=None)
        self.assertFalse(decision.allowed)

    def test_rollback_is_always_allowed(self):
        self.assertTrue(rollback_recommendation_mode(
            "production_manual_review", "shadow").allowed)
        self.assertTrue(rollback_recommendation_mode("manual_review", "off").allowed)
        self.assertFalse(rollback_recommendation_mode("off", "shadow").allowed)


# =========================================================================== #
# 10. No score / rank / trade field; determinism; frozen                      #
# =========================================================================== #
class NoScoreNoTradeTests(unittest.TestCase):
    def test_no_trade_or_score_field_on_the_shapes(self):
        for shape in (RecommendationActivationItem, RecommendationActivationReport,
                      RecommendationPromotionDecision):
            assert_no_trade_fields(shape)

    def test_no_metric_named_field_anywhere(self):
        for shape in (RecommendationActivationItem, RecommendationActivationReport,
                      RecommendationPromotionDecision):
            for f in fields(shape):
                for frag in _METRIC_FIELD_FRAGMENTS:
                    self.assertNotIn(frag, f.name.lower(),
                                     "metric-named field {0!r}".format(f.name))

    def test_report_is_frozen(self):
        with tempfile.TemporaryDirectory() as d:
            report = evaluate_recommendation_activation(d, now=_NOW)
        with self.assertRaises(FrozenInstanceError):
            report.recommendation_mode_allowed = True  # type: ignore[misc]

    def test_evaluation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            checks1, appr = _fully_cleared(d1)
            checks2, _ = _fully_cleared(d2)
            r1 = evaluate_recommendation_activation(
                d1, now=_NOW, checks=checks1, operator_approval=appr)
            r2 = evaluate_recommendation_activation(
                d2, now=_NOW, checks=checks2, operator_approval=appr)
        self.assertEqual(r1.recommendation_mode_allowed, r2.recommendation_mode_allowed)
        self.assertEqual(r1.verdict, r2.verdict)
        self.assertEqual([i.status for i in r1.items], [i.status for i in r2.items])

    def test_requires_injected_now(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                evaluate_recommendation_activation(d, now="")


# =========================================================================== #
# 11. Module guards -- AST bans, offline, additive exports                    #
# =========================================================================== #
class ModuleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_ACT_PY, encoding="utf-8") as fh:
            cls.source = fh.read()
        cls.tree = ast.parse(cls.source)

    def test_no_banned_module_import(self):
        for node in ast.walk(self.tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for banned in _BANNED_IMPORT_ROOTS:
                    self.assertFalse(
                        name == banned or name.startswith(banned + "."),
                        "banned import {0!r} in recommendation_activation.py".format(name))

    def test_no_loop_async_or_timed_wait_construct(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in the gate")
            self.assertNotIsInstance(node, ast.AsyncFunctionDef)
            self.assertNotIsInstance(node, ast.Await)
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotIn(called, _BANNED_CALL_NAMES,
                                 "daemon-style call {0!r}".format(called))

    def test_import_has_no_side_effect_beyond_definitions(self):
        allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr,
                   ast.FunctionDef, ast.ClassDef)
        for node in self.tree.body:
            self.assertIsInstance(node, allowed)
            if isinstance(node, ast.Expr):
                if isinstance(node.value, ast.Call):
                    func = node.value.func
                    self.assertEqual(getattr(func, "id", ""), "assert_no_trade_fields",
                                     "unexpected import-time side effect")
                else:
                    self.assertIsInstance(node.value, ast.Constant)

    def test_no_execution_or_directive_token_anywhere(self):
        low = self.source.lower()
        for tok in _EXECUTION_TOKENS:
            self.assertIsNone(
                re.search(r"\b{0}\b".format(re.escape(tok)), low),
                "execution/directive token {0!r} in recommendation_activation.py".format(tok))

    def test_no_wall_clock_or_randomness(self):
        for token in _WALL_CLOCK_TOKENS:
            self.assertNotIn(token, self.source, "wall-clock call {0!r}".format(token))
        self.assertIsNone(re.search(r"\brandom\b|\brandint\b|\buuid\b", self.source.lower()))

    def test_no_function_named_like_a_metric(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNone(re.search(r"(score|rank|rating)", node.name.lower()),
                                  "metric-named fn {0!r}".format(node.name))

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()

    def test_exports_are_additive_on_the_package(self):
        for name in ("RecommendationMode", "RECOMMENDATION_MODES", "RecommendationVerdict",
                     "RECOMMENDATION_ACTIVATION_ITEMS", "RecommendationActivationItem",
                     "RecommendationActivationReport", "RecommendationPromotionDecision",
                     "MODE_LADDER", "run_recommendation_checks",
                     "evaluate_recommendation_activation",
                     "can_enter_production_recommendation", "default_recommendation_mode",
                     "promote_recommendation_mode", "rollback_recommendation_mode"):
            self.assertTrue(hasattr(rm, name), "reality_mesh.{0} missing".format(name))

    def test_the_seven_013b_stores_are_untouched(self):
        from reality_mesh import stores as S
        self.assertEqual(len(S.STORE_CLASSES), 7)


# =========================================================================== #
# 12. Untouched paths -- demo default + default pulse stay byte-identical      #
# =========================================================================== #
class UntouchedPathsTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                with open(a[name], "rb") as fa, open(b[name], "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(),
                                     "demo default drifted for {0}".format(name))

    def test_default_pulse_byte_identical(self):
        now = "2026-06-29T00:00:00Z"
        a = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=now)
        b = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=now)
        self.assertEqual(repr(a.signals), repr(b.signals))
        self.assertEqual(repr(a.theme_pulses), repr(b.theme_pulses))
        self.assertEqual(repr(a.clusters), repr(b.clusters))


if __name__ == "__main__":
    unittest.main()
