"""IMPLEMENTATION-023G -- the CI/CD PRODUCTION GATE. OFFLINE.

Hardens the ONE command that determines deployment readiness: ``cosmosiq_ops prod-check`` now also
runs the 022H recommendation-eligibility gate, the 023A deployment-config validation, and a 023F
backup/restore smoke, and emits BOTH honest verdicts -- ``production_mode_allowed`` (via the 020F
:func:`evaluate_activation`) and ``recommendation_mode_allowed`` (via the 022H
:func:`evaluate_recommendation_activation`).

Proves the gate is NOT weakened and stays unfakeable:

* prod-check REFUSES production (``production_mode_allowed=False``) in the honest OFFLINE state
  (no signoff) and lands ``shadow_24x7_only`` -- the manual items block;
* the NEW ``recommendation_mode_allowed`` is present + honest: ``False`` OFFLINE, reachable ONLY
  with the full 022H machine set + a cleared live-source-health + an explicit operator sign-off;
* the three new checks (recommendation_eligibility / deployment_config_valid / backup_restore_smoke)
  appear in the checklist and PASS offline (their machine parts);
* prod-check FAILS with an injected fixture-ticker leak, a missing source health, a DQ-gate
  failure, and a trading control -- each real scan / injected block keeps production False;
* prod-check PASSES production ONLY when every requirement passes AND a valid signoff exists;
* deterministic run-to-run; offline (a socket kill-switch armed); demo + default pulse
  byte-identical; and the accepted 020F/021C prod-check tests still pass (no regression).
"""

from __future__ import annotations

import os
import socket
import tempfile
import unittest

from cosmosiq_ops import __main__ as ops_main
from cosmosiq_ops.prod_check import (
    FIXTURE_TICKERS,
    _backup_restore_smoke,
    _deployment_config_valid,
    _recommendation_eligibility,
    format_prod_check_report,
    run_prod_check,
)
from cosmosiq_service.activation import CheckResult, OperatorApproval

_NOW = "2026-06-29T00:00:00Z"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The three 020F manual items that cannot be machine-verified OFFLINE.
_MANUAL_ITEMS = ("live_source_health", "operator_shadow_validation", "operator_signoff")

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: 023G prod-check must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _valid_approval():
    return OperatorApproval(approved_by="Operator Prime", approved_at=_NOW,
                            target_mode="production_24x7")


def _clear_020f_manual():
    """The extra_checks that clear the three 020F manual items (as 021C's signoff flow does)."""
    return {item: CheckResult(item, "pass", ("operator evidence recorded",))
            for item in _MANUAL_ITEMS}


def _clear_022h_live():
    """The extra recommendation check that clears the 022H manual live-source-health item."""
    return {"live_source_health": CheckResult(
        "live_source_health", "pass", ("live fetch confirmed reachable + fresh",))}


class HonestOfflineVerdictTests(unittest.TestCase):
    def test_prod_check_fails_without_signoff_current_state(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        # production refused, no signoff -> the honest safe default.
        self.assertFalse(report.production_mode_allowed)
        self.assertEqual(report.verdict, "shadow_24x7_only")
        self.assertEqual(report.blocking_failures, ())          # NO machine failure
        for item in _MANUAL_ITEMS:
            self.assertIn(item, report.manual_review_items)     # the manual items block

    def test_recommendation_mode_allowed_present_and_honest_offline(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        # the NEW verdict is present, is a real bool, and is honestly False offline.
        self.assertIsInstance(report.recommendation_mode_allowed, bool)
        self.assertFalse(report.recommendation_mode_allowed)
        self.assertEqual(report.recommendation_verdict, "shadow_only")
        # its honest blockers are the two 022H manual items; no machine failure.
        self.assertEqual(report.recommendation_blocking_failures, ())
        for item in ("live_source_health", "operator_signoff"):
            self.assertIn(item, report.recommendation_manual_review_items)

    def test_new_checks_present_and_pass_offline(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        by_id = {c.name: c for c in report.checks}
        for name in ("recommendation_eligibility", "deployment_config_valid",
                     "backup_restore_smoke"):
            self.assertIn(name, by_id, "{0} must appear in the checklist".format(name))
            self.assertEqual(by_id[name].status, "pass",
                             "{0} should pass offline: {1}".format(name, by_id[name].details))

    def test_report_renders_both_verdicts_and_is_honest(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        text = format_prod_check_report(report)
        self.assertIn("production_mode_allowed = false", text)
        self.assertIn("recommendation_mode_allowed = false", text)
        self.assertIn("PRODUCTION NOT ALLOWED", text)


class ComponentCheckTests(unittest.TestCase):
    def test_deployment_config_valid_passes_offline(self):
        result = _deployment_config_valid()
        self.assertEqual(result.status, "pass", result.details)

    def test_backup_restore_smoke_passes_offline(self):
        with tempfile.TemporaryDirectory() as work:
            result = _backup_restore_smoke(work, _NOW)
        self.assertEqual(result.status, "pass", result.details)
        # the smoke actually round-tripped through an empty target with replay-after-restore.
        self.assertTrue(any("replay=True" in d for d in result.details))

    def test_recommendation_eligibility_machine_checks_pass_but_mode_refused(self):
        with tempfile.TemporaryDirectory() as rec_store:
            result, report = _recommendation_eligibility(rec_store, _NOW)
        self.assertEqual(result.status, "pass")               # machine checks pass...
        self.assertFalse(report.recommendation_mode_allowed)  # ...but the mode stays refused
        self.assertEqual(report.verdict, "shadow_only")


class ExitCodeTests(unittest.TestCase):
    def test_prod_check_cli_exits_non_zero_when_production_not_allowed(self):
        with tempfile.TemporaryDirectory() as work:
            code = ops_main.main(["prod-check", "--work-dir", work,
                                  "--repo-root", _REPO_ROOT, "--now", _NOW, "--quick"])
        self.assertNotEqual(code, 0)


class InjectedFailureTests(unittest.TestCase):
    """The gate stays unfakeable: every injected violation keeps production False."""

    def test_fails_with_fixture_leakage(self):
        # plant a page leaking a real fixture ticker into a scratch repo root.
        ticker = FIXTURE_TICKERS[0]
        repo = tempfile.mkdtemp()
        gen = os.path.join(repo, "generated")
        os.makedirs(gen)
        with open(os.path.join(gen, "planted.html"), "w", encoding="utf-8") as fh:
            fh.write("<html><body>track {0} now</body></html>".format(ticker))
        try:
            with tempfile.TemporaryDirectory() as work:
                report = run_prod_check(work, repo, now=_NOW, quick=True,
                                        operator_approval=_valid_approval(),
                                        extra_checks=_clear_020f_manual())
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)
        # even with every manual item cleared + a valid approval, the leak fails the scan.
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("fixture_leakage", report.blocking_failures)

    def test_fails_with_missing_source_health(self):
        # live_source_health stays manual/blocking -> production refused (no override supplied).
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(
                work, _REPO_ROOT, now=_NOW, quick=True,
                operator_approval=_valid_approval(),
                # clear the OTHER two manual items but NOT live_source_health.
                extra_checks={i: CheckResult(i, "pass", ("cleared",))
                              for i in ("operator_shadow_validation", "operator_signoff")})
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("live_source_health", report.manual_review_items)

    def test_fails_with_dq_gate_failure(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(
                work, _REPO_ROOT, now=_NOW, quick=True,
                operator_approval=_valid_approval(),
                extra_checks=dict(_clear_020f_manual(),
                                  dq_gate_pass=CheckResult(
                                      "dq_gate_pass", "fail", ("injected DQ hard fail",))))
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("dq_gate_pass", report.blocking_failures)

    def test_fails_with_trading_control(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(
                work, _REPO_ROOT, now=_NOW, quick=True,
                operator_approval=_valid_approval(),
                extra_checks=dict(_clear_020f_manual(),
                                  no_trade_control=CheckResult(
                                      "no_trade_control", "fail",
                                      ("planted BUY / place-order affordance",))))
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("no_trade_control", report.blocking_failures)


class ReachableOnlyWithCompleteEvidenceTests(unittest.TestCase):
    def test_production_passes_only_with_all_requirements_and_signoff(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(
                work, _REPO_ROOT, now=_NOW, quick=True,
                operator_approval=_valid_approval(),
                extra_checks=_clear_020f_manual())
        self.assertTrue(report.production_mode_allowed)
        self.assertEqual(report.verdict, "production_24x7_approved")
        self.assertEqual(report.blocking_failures, ())
        self.assertEqual(report.manual_review_items, ())

    def test_production_still_refused_without_the_signoff_even_if_machine_clear(self):
        # clear the machine-side manual items but withhold the operator approval -> refused.
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(
                work, _REPO_ROOT, now=_NOW, quick=True,
                operator_approval=None,
                extra_checks={i: CheckResult(i, "pass", ("cleared",))
                              for i in ("live_source_health", "operator_shadow_validation")})
        self.assertFalse(report.production_mode_allowed)

    def test_recommendation_mode_reachable_only_with_full_022h_set_and_signoff(self):
        # the honest offline call refuses; only the full 022H machine set + live health + signoff
        # reaches recommendation_mode_allowed=True.
        with tempfile.TemporaryDirectory() as work:
            refused = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        self.assertFalse(refused.recommendation_mode_allowed)

        with tempfile.TemporaryDirectory() as work:
            allowed = run_prod_check(
                work, _REPO_ROOT, now=_NOW, quick=True,
                operator_approval=_valid_approval(),
                extra_checks=_clear_020f_manual(),
                extra_recommendation_checks=_clear_022h_live())
        self.assertTrue(allowed.recommendation_mode_allowed)
        self.assertEqual(allowed.recommendation_verdict, "production_manual_review_approved")


class SafetyPropertyTests(unittest.TestCase):
    def test_no_score_or_trade_control_via_folded_guards(self):
        # the honest safety property: the runtime no-trade-control + no-hidden-score guards pass,
        # and the report carries no score/rank/rating field on its own shape.
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        by_id = {c.name: c for c in report.checks}
        self.assertEqual(by_id["no_trade_control"].status, "pass")
        self.assertEqual(by_id["no_score_rank_functions"].status, "pass")
        # the report shape itself exposes only verdicts + labels -- no score/rank/buy/sell field.
        for banned in ("score", "rank", "rating", "buy", "sell", "order", "quantity", "price"):
            self.assertFalse(hasattr(report, banned),
                             "ProdCheckReport must not expose a {0!r} field".format(banned))

    def test_deterministic_run_to_run(self):
        with tempfile.TemporaryDirectory() as w1, tempfile.TemporaryDirectory() as w2:
            r1 = run_prod_check(w1, _REPO_ROOT, now=_NOW, quick=True)
            r2 = run_prod_check(w2, _REPO_ROOT, now=_NOW, quick=True)
        self.assertEqual(r1.production_mode_allowed, r2.production_mode_allowed)
        self.assertEqual(r1.recommendation_mode_allowed, r2.recommendation_mode_allowed)
        self.assertEqual(r1.verdict, r2.verdict)
        self.assertEqual(r1.recommendation_verdict, r2.recommendation_verdict)
        self.assertEqual([c.status for c in r1.checks], [c.status for c in r2.checks])

    def test_demo_and_default_pulse_byte_identical(self):
        # the demo build must be byte-identical to the default build (via the folded ci_gate check).
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        by_id = {c.name: c for c in report.checks}
        self.assertEqual(by_id["demo_byte_identical"].status, "pass",
                         by_id["demo_byte_identical"].details)


if __name__ == "__main__":
    unittest.main()
