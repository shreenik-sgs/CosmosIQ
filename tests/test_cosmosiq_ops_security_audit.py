"""IMPLEMENTATION-023H -- the SECURITY / COMPLIANCE / AUDIT pass. OFFLINE.

Proves the pre-deployment guardrail battery (:mod:`cosmosiq_ops.security_audit`) is HONEST and
REAL -- it composes the already-accepted scans, reports each category's true pass/fail, catches a
planted issue, and never leaks a secret:

* the audit PASSES on the current repo -- every category passes, overall ``passed`` True;
* the secret scan is REAL: no secret value in the CosmosIQ source / rendered output, AND a PLANTED
  secret in a temp artifact IS detected (not a rubber stamp);
* the guardrail scan passes: no-trade-control / no-hidden-score / no-network-on-import /
  no-social-laundering / no-manual-canonical all pass;
* the audit is HONEST: an injected synthetic finding flips its category to FAILED and the CLI would
  exit NON-ZERO;
* dependencies_reviewed finds ZERO third-party runtime deps (stdlib-only);
* logs / errors are sanitized (a planted secret is redacted through sanitize / log / health paths);
* NO secret value appears in the rendered audit report;
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
from cosmosiq_ops.security_audit import (
    AUDIT_PACKAGES,
    SecurityAuditCategory,
    SecurityAuditReport,
    render_security_audit,
    run_security_audit,
    scan_text_for_secret_values,
)

_NOW = "2026-06-29T00:00:00Z"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ORIG_CONNECT = None


def setUpModule():
    # Arm a socket kill-switch: the whole 023H audit MUST run fully offline.
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: 023H security audit must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


class SecurityAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One audit over the real repo, reused across assertions (offline, deterministic).
        cls.report = run_security_audit(_REPO_ROOT, now=_NOW)
        cls.rendered = render_security_audit(cls.report)

    # -- the audit passes on the current repo --------------------------------- #
    def test_audit_passes_on_repo(self):
        self.assertTrue(self.report.passed,
                        "audit failed: " + ", ".join(self.report.categories_failed))
        for cat in self.report.categories:
            self.assertTrue(cat.passed, "category {0} failed: {1}".format(cat.id, cat.findings))

    def test_every_expected_category_present(self):
        expected = {
            "no_secrets_in_repo_or_output", "no_network_on_import", "no_broker_execution",
            "no_trade_controls", "no_hidden_score_rank", "no_social_verified_fact_laundering",
            "no_manual_canonical_laundering", "no_unsafe_default_production",
            "no_fixture_demo_production_leakage", "dependencies_reviewed",
            "logs_and_errors_sanitized", "file_permissions_sane",
        }
        self.assertEqual({c.id for c in self.report.categories}, expected)

    # -- secret scan is real: no secret in repo/output; a PLANTED secret IS caught -- #
    def test_no_secret_in_source_or_output(self):
        self.assertTrue(self.report.category("no_secrets_in_repo_or_output").passed)
        self.assertEqual(self.report.category("no_secrets_in_repo_or_output").findings, ())

    def test_planted_secret_is_detected(self):
        # A rubber-stamp scan would find nothing. Prove the scan REALLY fires on a planted secret.
        planted_aws = "AKIA" + "IOSFODNN7EXAMPLE"
        planted_openai = "sk-" + "B" * 24
        self.assertTrue(scan_text_for_secret_values(planted_aws),
                        "the secret scan failed to detect a planted AWS-shaped key")
        self.assertTrue(scan_text_for_secret_values(planted_openai),
                        "the secret scan failed to detect a planted OpenAI-shaped token")
        # ... and stays quiet on a clean, non-secret string.
        self.assertEqual(scan_text_for_secret_values("a perfectly ordinary sentence"), ())

    def test_planted_secret_in_temp_artifact_is_detected(self):
        # Write a secret into a temp artifact and prove the scan detects it there too.
        planted = "AKIA" + "1234567890ABCDEF"
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "leaked.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("credential dump: " + planted + "\n")
            with open(path, encoding="utf-8") as fh:
                self.assertTrue(scan_text_for_secret_values(fh.read()))

    # -- the guardrail scan passes -------------------------------------------- #
    def test_guardrail_categories_pass(self):
        for cid in ("no_trade_controls", "no_hidden_score_rank", "no_network_on_import",
                    "no_broker_execution", "no_social_verified_fact_laundering",
                    "no_manual_canonical_laundering"):
            self.assertTrue(self.report.category(cid).passed, cid + " should pass")

    def test_laundering_categories_assert_via_gate_not_grep(self):
        # The caveats must show the gate REJECTED a constructed laundering record (a real assertion).
        social = self.report.category("no_social_verified_fact_laundering")
        manual = self.report.category("no_manual_canonical_laundering")
        self.assertTrue(any("HARD-fail" in c or "hard" in c.lower() for c in social.caveats))
        self.assertTrue(any("canonical" in c for c in manual.caveats))

    # -- honesty: an injected synthetic finding flips the category + CLI exit --- #
    def test_injected_finding_makes_category_fail(self):
        injected = run_security_audit(
            _REPO_ROOT, now=_NOW,
            inject={"no_broker_execution": ("SYNTHETIC audit finding for the honesty test",)})
        self.assertFalse(injected.passed)
        self.assertFalse(injected.category("no_broker_execution").passed)
        self.assertIn("no_broker_execution", injected.categories_failed)
        self.assertIn("SYNTHETIC audit finding for the honesty test",
                      injected.category("no_broker_execution").findings)
        # The finding is not hidden -- it appears in the rendered report as a FAIL.
        text = render_security_audit(injected)
        self.assertIn("SYNTHETIC audit finding", text)
        self.assertIn("**Verdict:** FAIL", text)

    def test_cli_exits_nonzero_on_failure(self):
        # A failing report must drive the CLI to a non-zero exit (an honest deployment gate).
        failing = SecurityAuditReport(
            repo_root=_REPO_ROOT, generated_at=_NOW,
            categories=(SecurityAuditCategory("no_broker_execution", False, ("planted",)),))
        orig = ops_main.run_prod_check  # unrelated; keep a handle to prove no accidental shadowing

        import cosmosiq_ops.security_audit as sa
        real = sa.run_security_audit
        try:
            sa.run_security_audit = lambda *a, **k: failing
            rc = ops_main.main(["security-audit", "--now", _NOW])
        finally:
            sa.run_security_audit = real
        self.assertEqual(rc, 1)
        self.assertIs(ops_main.run_prod_check, orig)

    def test_cli_exits_zero_on_clean_repo(self):
        rc = ops_main.main(["security-audit", "--now", _NOW])
        self.assertEqual(rc, 0)

    # -- dependencies reviewed: stdlib-only ----------------------------------- #
    def test_dependencies_reviewed_zero_third_party(self):
        dep = self.report.category("dependencies_reviewed")
        self.assertTrue(dep.passed)
        self.assertEqual(dep.findings, ())
        self.assertTrue(any("none (stdlib-only)" in c for c in dep.caveats),
                        "dependencies caveats: " + repr(dep.caveats))

    # -- logs / errors sanitized ---------------------------------------------- #
    def test_logs_and_errors_sanitized(self):
        self.assertTrue(self.report.category("logs_and_errors_sanitized").passed)

    def test_sanitizer_actually_redacts_a_planted_secret(self):
        # Independently prove the composed sanitize path redacts a planted secret VALUE.
        from cosmosiq_service.service import sanitize
        from cosmosiq_ops.observability import emit_structured_log
        secret = "AKIA" + "IOSFODNN7EXAMPLE"
        self.assertNotIn(secret, str(sanitize("note=" + secret)))
        line = emit_structured_log("probe", now=_NOW, region_key=secret)
        self.assertNotIn(secret, line)

    # -- no secret value in the rendered audit report ------------------------- #
    def test_no_secret_in_audit_report(self):
        self.assertEqual(scan_text_for_secret_values(self.rendered), ())
        # nor the AWS/OpenAI synthetic shapes used inside the sanitizer probe.
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", self.rendered)
        self.assertNotIn("sk-AAAAAAAA", self.rendered)

    # -- determinism ---------------------------------------------------------- #
    def test_deterministic(self):
        again = run_security_audit(_REPO_ROOT, now=_NOW)
        self.assertEqual(render_security_audit(again), self.rendered)
        self.assertEqual(again.categories_failed, self.report.categories_failed)

    # -- offline kill-switch (armed at module scope) -------------------------- #
    def test_runs_under_socket_kill_switch(self):
        # setUpModule armed the kill-switch; this run must still complete offline.
        report = run_security_audit(_REPO_ROOT, now=_NOW)
        self.assertTrue(report.passed)

    # -- demo + default pulse byte-identical ---------------------------------- #
    def test_demo_and_default_pulse_byte_identical(self):
        result = check_demo_build_byte_identical()
        self.assertEqual(result.status, "pass", result.details)

    # -- swept the CosmosIQ packages, not the UI-owned surface ---------------- #
    def test_scopes_cosmosiq_packages_only(self):
        self.assertEqual(
            AUDIT_PACKAGES,
            ("reality_mesh", "cosmosiq_app", "cosmosiq_ops", "cosmosiq_service", "cosmosiq_pulse"))
        self.assertNotIn("universe_ui", AUDIT_PACKAGES)


if __name__ == "__main__":
    unittest.main()
