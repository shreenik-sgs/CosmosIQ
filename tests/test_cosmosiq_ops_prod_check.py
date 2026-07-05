"""IMPLEMENTATION-020F -- the ``cosmosiq_ops prod-check`` production activation gate. OFFLINE.

Proves the offline prod-check:

* runs every machine check against the repo and lands the HONEST verdict
  ``production_mode_allowed = false`` / ``shadow_24x7_only`` (the manual items block);
* exits NON-ZERO when production is not allowed (the safe default);
* CATCHES an injected fixture-ticker leak, an injected trade control, and an injected
  hidden-score function -- each real scan fails on the planted artifact and blocks production;
* the 020B SEC adapter smoke, the scheduler dry-run, the service-wrapper health, the replay/DQ,
  the candidate publication, and the alert-safety checks all pass offline on the seeded store;
* the PRODUCTION service-mode indicator (when a PRODUCTION_24X7 health is present) renders the
  strip with Broker Disabled + Execution Manual Review Only and NEVER a trade control; an absent
  health still renders "" (byte-identical);
* demo + default builds are byte-identical; everything is offline (a socket kill-switch armed).
"""

from __future__ import annotations

import json
import os
import re
import socket
import tempfile
import unittest

from cosmosiq_ops import __main__ as ops_main
from cosmosiq_ops.ci_gate import check_no_score_rank_functions
from cosmosiq_ops.prod_check import (
    FIXTURE_TICKERS,
    _scan_fixture_leakage,
    _scan_no_trade_control,
    _sec_adapter_offline_smoke,
    _scheduler_dry_run,
    format_prod_check_report,
    run_prod_check,
)
from cosmosiq_app.pages import service_mode_indicator

_NOW = "2026-06-29T00:00:00Z"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: prod-check must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


class HonestOfflineVerdictTests(unittest.TestCase):
    def test_prod_check_refuses_production_and_lands_shadow_only(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        self.assertFalse(report.production_mode_allowed)
        self.assertEqual(report.verdict, "shadow_24x7_only")
        # the honest blockers are the three manual items; NO machine failure.
        self.assertEqual(report.blocking_failures, ())
        for item_id in ("live_source_health", "operator_shadow_validation", "operator_signoff"):
            self.assertIn(item_id, report.manual_review_items)
        self.assertTrue(report.evidence_paths)

    def test_all_machine_checks_pass_offline(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        by_id = {c.name: c for c in report.checks}
        for name in ("mode_state_machine", "no_auto_promotion", "sec_adapter_offline_smoke",
                     "scheduler_dry_run", "service_wrapper_health", "replay_deterministic",
                     "dq_gate_pass", "candidate_publication", "alert_safety_policy",
                     "no_trade_control", "fixture_leakage", "demo_byte_identical",
                     "secret_scan"):
            self.assertEqual(by_id[name].status, "pass",
                             "{0} should pass offline: {1}".format(name, by_id[name].details))

    def test_report_renders_and_is_honest(self):
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        text = format_prod_check_report(report)
        self.assertIn("PRODUCTION NOT ALLOWED", text)
        self.assertIn("production_mode_allowed = false", text)


class ExitCodeTests(unittest.TestCase):
    def test_prod_check_cli_exits_non_zero_when_not_allowed(self):
        with tempfile.TemporaryDirectory() as work:
            code = ops_main.main(["prod-check", "--work-dir", work,
                                  "--repo-root", _REPO_ROOT, "--now", _NOW, "--quick"])
        self.assertNotEqual(code, 0)


class InjectedViolationTests(unittest.TestCase):
    """Each real scan CATCHES a planted violation and (via prod-check) blocks production."""

    def _repo_with_planted_page(self, html):
        tmp = tempfile.mkdtemp()
        gen = os.path.join(tmp, "generated")
        os.makedirs(gen)
        with open(os.path.join(gen, "planted.html"), "w", encoding="utf-8") as fh:
            fh.write(html)
        return tmp

    def test_injected_fixture_ticker_leak_is_caught(self):
        ticker = FIXTURE_TICKERS[0]
        repo = self._repo_with_planted_page(
            "<html><body>watch {0} closely</body></html>".format(ticker))
        try:
            result = _scan_fixture_leakage(repo, _NOW)
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)
        self.assertEqual(result.status, "fail")
        self.assertTrue(any(ticker in d for d in result.details))

    def test_injected_trade_control_is_caught(self):
        repo = self._repo_with_planted_page(
            "<html><body><button>BUY now</button></body></html>")
        try:
            result = _scan_no_trade_control(repo, _NOW)
        finally:
            import shutil
            shutil.rmtree(repo, ignore_errors=True)
        self.assertEqual(result.status, "fail")

    def test_injected_hidden_score_function_is_caught(self):
        # plant a src package with a hidden-score function and sweep it.
        tmp = tempfile.mkdtemp()
        pkg = os.path.join(tmp, "src", "cosmosiq_app")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "leak.py"), "w", encoding="utf-8") as fh:
            fh.write("def compute_score(x):\n    return x * 2\n")
        try:
            result = check_no_score_rank_functions(tmp)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("compute_score" in d for d in result.details))

    def test_injected_violation_blocks_production_end_to_end(self):
        from cosmosiq_service.activation import CheckResult
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(
                work, _REPO_ROOT, now=_NOW, quick=True,
                extra_checks={"no_trade_control": CheckResult(
                    "no_trade_control", "fail", ("planted BUY control",))})
        self.assertFalse(report.production_mode_allowed)
        self.assertIn("no_trade_control", report.blocking_failures)


class ComponentCheckTests(unittest.TestCase):
    def test_sec_adapter_offline_smoke_passes_on_mock_transport(self):
        result = _sec_adapter_offline_smoke(_NOW)
        self.assertEqual(result.status, "pass")

    def test_scheduler_dry_run_is_one_tick(self):
        result = _scheduler_dry_run(_NOW)
        self.assertEqual(result.status, "pass")
        self.assertTrue(any("no loop" in d for d in result.details))


class ProductionIndicatorTests(unittest.TestCase):
    def test_production_health_renders_the_strip_without_a_trade_control(self):
        with tempfile.TemporaryDirectory() as store:
            with open(os.path.join(store, "service_health.json"), "w", encoding="utf-8") as fh:
                json.dump({"service_mode": "production_24x7",
                           "source_health_summary": {"coverage_records": 2,
                                                      "failed_source_records": 0}}, fh)
            indicator = service_mode_indicator(store)
        self.assertIn("Mode: PRODUCTION_24X7", indicator)
        self.assertIn("Broker: Disabled", indicator)
        self.assertIn("Execution: Manual Review Only", indicator)
        self.assertIn("Alert Delivery: On", indicator)
        # never a trade control anywhere in the strip.
        self.assertIsNone(re.search(r"\b(buy|sell)\b|place[\s_-]*order|submit[\s_-]*order",
                                    indicator, re.IGNORECASE))

    def test_absent_health_renders_empty_string(self):
        with tempfile.TemporaryDirectory() as store:
            self.assertEqual(service_mode_indicator(store), "")


class DeterminismTests(unittest.TestCase):
    def test_prod_check_is_deterministic_run_to_run(self):
        with tempfile.TemporaryDirectory() as w1, tempfile.TemporaryDirectory() as w2:
            r1 = run_prod_check(w1, _REPO_ROOT, now=_NOW, quick=True)
            r2 = run_prod_check(w2, _REPO_ROOT, now=_NOW, quick=True)
        self.assertEqual(r1.production_mode_allowed, r2.production_mode_allowed)
        self.assertEqual(r1.verdict, r2.verdict)
        self.assertEqual([c.status for c in r1.checks], [c.status for c in r2.checks])


if __name__ == "__main__":
    unittest.main()
