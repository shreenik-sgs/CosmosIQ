"""IMPLEMENTATION-023J -- the FINAL production deployment readiness gate. OFFLINE.

Proves the capstone (:mod:`cosmosiq_ops.deployment_readiness`) is HONEST and REAL -- it composes
every accepted gate, refuses production, and lands the honest verdict:

* the readiness report is produced; ``production_mode_allowed`` + ``recommendation_mode_allowed``
  are BOTH False in an honest OFFLINE run;
* the overall verdict is ``shadow deployment ready only`` (NOT production-ready), with
  ``operator_signoff`` + ``live_source_health`` + ``operator_shadow_validation`` in the outstanding
  manual items;
* every offline-runnable gate (CI, security audit, backup/restore, deployment smoke, replay,
  alert-delivery, UI smoke, runbook-review) PASSES;
* the report is NOT marked production-ready; the CLI exits NON-ZERO (safe default);
* a fully-cleared HYPOTHETICAL (inject production_mode_allowed True + a recorded sign-off) DOES
  yield ``production deployment ready`` -- proving the path exists -- but the REAL run does not;
* NO secret value appears in the rendered report; NO score / trade field exists on any shape;
* deterministic run-to-run; offline (a socket kill-switch armed); demo + default pulse
  byte-identical.
"""

from __future__ import annotations

import os
import socket
import tempfile
import unittest

from cosmosiq_ops import __main__ as ops_main
from cosmosiq_ops.ci_gate import check_demo_build_byte_identical
from cosmosiq_ops.security_audit import scan_text_for_secret_values
from cosmosiq_ops.deployment_readiness import (
    VERDICT_PRODUCTION_READY,
    VERDICT_SHADOW_READY_ONLY,
    DeploymentReadinessReport,
    GateResult,
    render_deployment_readiness,
    run_deployment_readiness,
)
from cosmosiq_service.activation import (
    CheckResult,
    ChecklistStatus,
    OperatorApproval,
)
from cosmosiq_service.service import ServiceMode
from reality_mesh.validation import assert_no_trade_fields

_NOW = "2026-07-06T00:00:00Z"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ORIG_CONNECT = None


def setUpModule():
    # Arm a socket kill-switch: the whole 023J readiness gate MUST run fully offline.
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: deployment readiness must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _valid_approval() -> OperatorApproval:
    return OperatorApproval(
        approved_by="J. Operator", approved_at=_NOW,
        target_mode=ServiceMode.PRODUCTION_24X7.value,
        statement="operator production sign-off (hypothetical)")


def _cleared_manual_checks():
    """The extra prod-check results that ATTEST the three manual items (the hypothetical)."""
    def _p(name):
        return CheckResult(name, ChecklistStatus.PASS, ("attested by operator sign-off",))
    return {
        "live_source_health": _p("live_source_health"),
        "operator_shadow_validation": _p("operator_shadow_validation"),
        "operator_signoff": _p("operator_signoff"),
    }


class HonestOfflineVerdictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.report = run_deployment_readiness(
            _REPO_ROOT, cls._tmp.name, now=_NOW, quick=True)
        cls.rendered = render_deployment_readiness(cls.report)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_report_is_produced(self):
        self.assertIsInstance(self.report, DeploymentReadinessReport)
        self.assertTrue(self.report.gates)
        self.assertTrue(self.report.readiness_checklist)
        self.assertEqual(self.report.environment_profile, "test_offline")

    def test_both_mode_flags_false_offline(self):
        self.assertFalse(self.report.production_mode_allowed)
        self.assertFalse(self.report.recommendation_mode_allowed)
        self.assertFalse(self.report.signoff_recorded)

    def test_overall_verdict_is_shadow_ready_only(self):
        self.assertEqual(self.report.overall_verdict, VERDICT_SHADOW_READY_ONLY)
        self.assertFalse(self.report.production_deployment_ready)
        self.assertTrue(self.report.shadow_deployment_ready)

    def test_outstanding_manual_items(self):
        # the three honest outstanding items must all be in the manual/outstanding list.
        for item in ("operator_signoff", "live_source_health", "operator_shadow_validation"):
            self.assertIn(item, self.report.manual_review_items,
                          "{0} must be an outstanding manual item".format(item))
        # no machine gate failed.
        self.assertEqual(self.report.blocking_failures, ())

    def test_offline_gates_all_pass(self):
        by_id = {g.id: g for g in self.report.gates}
        offline = (
            "full_suite_ci_gate", "prod_check_023G", "security_audit_023H",
            "backup_restore_smoke_023F", "deployment_smoke_019A", "replay_deterministic_013C",
            "alert_delivery_020E", "ui_smoke_016", "operator_runbook_review_023I")
        for gate_id in offline:
            self.assertEqual(by_id[gate_id].status, "pass",
                             "{0}: {1}".format(gate_id, by_id[gate_id].notes))
        # the ONE gate that cannot run offline is honestly manual -- never a fabricated pass.
        self.assertEqual(by_id["shadow_live_source_health"].status, "manual_review_required")

    def test_ui_smoke_all_routes_200(self):
        ui = next(g for g in self.report.gates if g.id == "ui_smoke_016")
        self.assertEqual(ui.status, "pass")
        self.assertIn("6/6 routes 200", ui.notes)

    def test_health_visible(self):
        # source / agent / DQ / replay are aggregated and VISIBLE in the snapshot.
        snap = self.report.health_snapshot
        self.assertIn("status", snap)
        self.assertIn("dq_gate_overall_worst", snap)
        self.assertTrue(snap.get("replay_deterministic_match"))

    def test_report_not_marked_production_ready(self):
        self.assertNotIn(VERDICT_PRODUCTION_READY, self.rendered.split("\n")[2])
        self.assertIn("SHADOW DEPLOYMENT READY ONLY", self.rendered)
        self.assertIn("production_mode_allowed: **false**", self.rendered)
        self.assertIn("recommendation_mode_allowed: **false**", self.rendered)

    def test_no_secret_in_report(self):
        self.assertEqual(scan_text_for_secret_values(self.rendered), ())
        # no credential value leaks (the synthetic audit-probe shapes must never appear here).
        self.assertNotIn("AKIA", self.rendered)
        self.assertNotIn("sk-", self.rendered)

    def test_no_score_or_trade_field_on_shapes(self):
        assert_no_trade_fields(GateResult)
        assert_no_trade_fields(DeploymentReadinessReport)
        for g in tuple(self.report.gates) + tuple(self.report.readiness_checklist):
            assert_no_trade_fields(g)

    def test_known_limitations_are_honest(self):
        joined = " ".join(self.report.known_limitations).lower()
        self.assertIn("live_source_health", joined)
        self.assertIn("operator_signoff", joined)
        self.assertIn("no broker", joined)


class HypotheticalProductionReadyTests(unittest.TestCase):
    def test_fully_cleared_evidence_yields_production_ready(self):
        with tempfile.TemporaryDirectory() as w:
            report = run_deployment_readiness(
                _REPO_ROOT, w, now=_NOW, quick=True,
                operator_approval=_valid_approval(),
                extra_checks=_cleared_manual_checks())
        # WITH complete evidence the reachable path is taken -- proving it exists.
        self.assertTrue(report.production_mode_allowed)
        self.assertTrue(report.signoff_recorded)
        self.assertEqual(report.overall_verdict, VERDICT_PRODUCTION_READY)
        self.assertTrue(report.production_deployment_ready)
        self.assertEqual(report.blocking_failures, ())
        rendered = render_deployment_readiness(report)
        self.assertIn("PRODUCTION DEPLOYMENT READY", rendered)

    def test_real_run_does_not_take_the_path(self):
        with tempfile.TemporaryDirectory() as w:
            report = run_deployment_readiness(_REPO_ROOT, w, now=_NOW, quick=True)
        self.assertFalse(report.production_deployment_ready)
        self.assertEqual(report.overall_verdict, VERDICT_SHADOW_READY_ONLY)


class DeterminismAndCliTests(unittest.TestCase):
    def test_deterministic_render(self):
        with tempfile.TemporaryDirectory() as w1:
            r1 = render_deployment_readiness(
                run_deployment_readiness(_REPO_ROOT, w1, now=_NOW, quick=True))
        with tempfile.TemporaryDirectory() as w2:
            r2 = render_deployment_readiness(
                run_deployment_readiness(_REPO_ROOT, w2, now=_NOW, quick=True))
        self.assertEqual(r1, r2)

    def test_cli_exits_non_zero_not_production_ready(self):
        with tempfile.TemporaryDirectory() as w:
            code = ops_main.main(
                ["readiness", "--work-dir", w, "--repo-root", _REPO_ROOT,
                 "--now", _NOW, "--quick"])
        self.assertEqual(code, 1)

    def test_cli_writes_report_out(self):
        with tempfile.TemporaryDirectory() as w:
            out = os.path.join(w, "readiness.md")
            code = ops_main.main(
                ["readiness", "--work-dir", w, "--repo-root", _REPO_ROOT,
                 "--now", _NOW, "--quick", "--report-out", out])
            self.assertEqual(code, 1)
            self.assertTrue(os.path.isfile(out))
            with open(out, encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("COSMOSIQ PRODUCTION DEPLOYMENT READINESS REPORT", text)
        self.assertIn("SHADOW DEPLOYMENT READY ONLY", text)

    def test_demo_and_default_pulse_byte_identical(self):
        result = check_demo_build_byte_identical()
        self.assertEqual(result.status, "pass", result.details)

    def test_runs_under_socket_kill_switch(self):
        # setUpModule armed the kill-switch; the whole gate still completes offline.
        with tempfile.TemporaryDirectory() as w:
            report = run_deployment_readiness(_REPO_ROOT, w, now=_NOW, quick=True)
        self.assertEqual(report.overall_verdict, VERDICT_SHADOW_READY_ONLY)


if __name__ == "__main__":
    unittest.main()
