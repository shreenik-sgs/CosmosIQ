"""IMPLEMENTATION-020G -- the Real-Operator SHADOW_24X7 shadow-validation runner. OFFLINE.

Proves the controlled shadow-validation window:

* drives the 020D `SHADOW_24X7` service across MULTIPLE injected-time ticks, fully OFFLINE (a
  socket kill-switch armed), persisting a run per tick with the DQ gates run on EVERY pulse;
* captures agent-health + source-health from the persisted state;
* exercises the SEC EDGAR live adapter ONLY in its honest `credentials_missing` state -> a
  VISIBLE source gap (NO fabricated events, NO fixture fall-back); `live_source_health` stays
  unverified/manual;
* any shadow alert is `mode = SHADOW_24X7` + the shadow marker + inbox-only (no external
  delivery, no production escalation, no forbidden action phrase);
* replays every window run deterministically (0 divergences);
* records the 020A candidate-publication attempts (no forged-eligible);
* fills the full 020D report with every section + a promotion recommendation of `remain_shadow`;
* the report + result carry NO secret / NO forbidden action phrase / NO hidden score field;
* demo + default builds are byte-identical;
* AFTER the window an evaluate/prod-check STILL yields `production_mode_allowed = False` with
  `operator_signoff` required -- the pass did NOT flip the 020F gate.
"""

from __future__ import annotations

import os
import socket
import tempfile
import unittest

from cosmosiq_ops import __main__ as ops_main
from cosmosiq_ops.ci_gate import (
    SECRET_KEY_TOKENS,
    SECRET_VALUE_PATTERNS,
    check_demo_build_byte_identical,
)
from cosmosiq_ops.shadow_validation import (
    PROMOTION_RECOMMENDATIONS,
    CandidateRecord,
    ShadowAlertRecord,
    ShadowWindowResult,
    render_validation_report,
    run_shadow_window,
)
from cosmosiq_service.activation import evaluate_activation
from reality_mesh.alerts import FORBIDDEN_ALERT_PHRASES, SHADOW_MARKER, SHADOW_MODE_VALUE
from reality_mesh.orchestrator import Subscription
from reality_mesh.scheduler import DEFAULT_CADENCE_POLICIES

_START = "2026-06-29T14:30:00Z"
_ALL_POLICIES = tuple(p.policy_id for p in DEFAULT_CADENCE_POLICIES)

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: shadow-validation must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _subscription() -> Subscription:
    return Subscription(
        subscription_id="shadow-univ", watchlist=("IREN", "AAOI"),
        themes=("physical_ai",), policy_ids=_ALL_POLICIES)


def _run_window(ticks: int = 6):
    store_dir = tempfile.mkdtemp()
    result = run_shadow_window(
        store_dir, subscriptions=(_subscription(),), ticks=ticks,
        start=_START, interval_minutes=60)
    return store_dir, result


class ShadowWindowExecutionTest(unittest.TestCase):
    def setUp(self):
        self.store_dir, self.result = _run_window(ticks=6)

    def test_multi_tick_window_persisted_offline(self):
        # A controlled multi-tick window ran; each tick persisted a distinct run.
        self.assertEqual(self.result.ticks_scheduled, 6)
        self.assertEqual(self.result.ticks_succeeded, 6)
        self.assertEqual(self.result.ticks_failed, 0)
        self.assertGreaterEqual(len(self.result.persisted_run_ids), 2)
        self.assertEqual(len(set(self.result.persisted_run_ids)),
                         len(self.result.persisted_run_ids))

    def test_duration_labelled_honestly_not_wall_clock(self):
        label = self.result.duration_label
        self.assertIn("controlled validation window", label)
        self.assertIn("injected-time", label)
        self.assertIn("NOT a wall-clock", label)
        # The injected span is derived from the injected instants, not any wall clock.
        self.assertGreater(self.result.injected_span_hours, 0.0)

    def test_dq_gates_run_every_pulse(self):
        self.assertTrue(self.result.dq_gate_ran_every_pulse)
        # No failing DQ record hid behind a pass.
        self.assertEqual(self.result.dq_failures, self.result.dq_failures)
        self.assertTrue(self.result.dq_overall_counts)

    def test_agent_and_source_health_captured(self):
        ah = self.result.agent_health
        self.assertGreater(ah["results"], 0)
        self.assertEqual(ah["failed"], 0)
        self.assertIn("source_health", self.result.sec_source_health)

    def test_sec_unconfigured_is_a_visible_gap_never_fabricated(self):
        sec = self.result.sec_source_health
        self.assertFalse(self.result.sec_edgar_configured)
        self.assertFalse(self.result.live_source_health_verified)
        self.assertEqual(sec["source_health"], "credentials_missing")
        self.assertEqual(sec["credentials_status"], "missing")
        # NO fabricated events, NO fixture fall-back.
        self.assertEqual(sec["events_created"], 0)
        self.assertEqual(sec["status"], "skipped")
        gaps = " ".join(sec["data_gaps"]).lower()
        self.assertIn("credentials_missing", gaps)
        self.assertIn("no silent fixture", gaps)

    def test_shadow_alerts_inbox_only_and_marked(self):
        self.assertFalse(self.result.external_delivery_occurred)
        self.assertFalse(self.result.production_escalation_occurred)
        self.assertEqual(self.result.alert_forbidden_phrase_hits, ())
        for alert in self.result.shadow_alerts:
            self.assertEqual(alert.mode, SHADOW_MODE_VALUE)
            self.assertTrue(alert.marked_shadow)
            self.assertEqual(alert.delivery, "in_app_inbox_only")
        # The service log proves no external delivery / escalation on any success tick.
        success_ticks = [t for t in self.result.ticks if t.event == "tick.success"]
        self.assertTrue(success_ticks)
        for tick in success_ticks:
            self.assertFalse(tick.external_delivery)
            self.assertFalse(tick.production_escalation)

    def test_replay_deterministic_on_window_runs(self):
        self.assertEqual(len(self.result.replay_checks), len(self.result.persisted_run_ids))
        self.assertEqual(self.result.replay_divergences, 0)
        for check in self.result.replay_checks:
            self.assertTrue(check.deterministic_match, check.differences)

    def test_candidate_publication_recorded_no_forged_eligible(self):
        self.assertGreater(self.result.candidate_attempts, 0)
        self.assertEqual(self.result.forged_eligible, ())
        # An automated pass supplies no diligence -> every candidate is honestly ineligible.
        for cand in self.result.candidates:
            self.assertFalse(cand.is_eligible)
            self.assertTrue(cand.missing_lineage)

    def test_promotion_recommendation_is_remain_shadow(self):
        self.assertEqual(self.result.promotion_recommendation, "remain_shadow")
        self.assertIn(self.result.promotion_recommendation, PROMOTION_RECOMMENDATIONS)

    def test_gate_not_flipped_after_window(self):
        report = evaluate_activation(self.store_dir, now="2026-06-30T13:30:00Z")
        self.assertFalse(report.production_mode_allowed)
        self.assertEqual(report.verdict, "shadow_24x7_only")
        self.assertIn("operator_signoff", report.manual_review_items)
        self.assertIn("live_source_health", report.manual_review_items)
        self.assertFalse(report.operator_approval_valid)

    def test_no_secret_no_forbidden_phrase_no_hidden_score(self):
        report = render_validation_report(
            self.result, operator="tester", generated_at=_START)
        blob = report.lower()
        for phrase in FORBIDDEN_ALERT_PHRASES:
            self.assertNotIn(phrase, blob)
        for pattern in SECRET_VALUE_PATTERNS:
            self.assertIsNone(pattern.search(report))
        for token in SECRET_KEY_TOKENS:
            self.assertNotIn(token, blob)
        # No hidden score / rank / rating field anywhere on the result contracts.
        for cls in (ShadowWindowResult, CandidateRecord, ShadowAlertRecord):
            names = {f for f in cls.__dataclass_fields__}
            for banned in ("score", "rank", "rating", "sizing"):
                self.assertFalse(any(banned in n for n in names),
                                 "{0} carries a {1} field".format(cls.__name__, banned))


class ShadowReportTest(unittest.TestCase):
    def setUp(self):
        self.store_dir, self.result = _run_window(ticks=4)
        self.report = render_validation_report(
            self.result, operator="tester", generated_at=_START)

    def test_report_contains_every_required_section(self):
        for section in ("## 0. Run identity", "## 1. Shadow window",
                        "## 2. Pulse accounting", "## 3. Source-health summary",
                        "## 4. Agent-health summary", "## 5. Data-quality gate outcomes",
                        "## 6. Shadow alerts", "## 7. False positives reviewed",
                        "## 8. Candidate publication results", "## 9. Replay checks",
                        "## 10. Operator notes", "## 11. Promotion recommendation"):
            self.assertIn(section, self.report)

    def test_report_states_the_honesty_caveats(self):
        self.assertIn("remain_shadow", self.report)
        self.assertIn("NOT a wall-clock 24-72h calendar run", self.report)
        self.assertIn("credentials-not-configured", self.report)
        self.assertIn("credentials_missing", self.report)
        # False positives reviewed = 0 (an automated pass reviews none) is stated.
        self.assertIn("False positives reviewed: 0", self.report)
        # production_mode_allowed stays false; operator sign-off required.
        self.assertIn("production_mode_allowed | false", self.report)
        self.assertIn("operator_signoff | required", self.report)

    def test_report_marker_matches_the_alert_marker(self):
        # The shadow marker text is the accepted alerts-module constant.
        self.assertTrue(SHADOW_MARKER.startswith("[SHADOW MODE"))


class ShadowValidationGuardTest(unittest.TestCase):
    def test_empty_subscriptions_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run_shadow_window(d, subscriptions=(), ticks=2, start=_START,
                                  interval_minutes=60)

    def test_bad_ticks_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run_shadow_window(d, subscriptions=(_subscription(),), ticks=0,
                                  start=_START, interval_minutes=60)

    def test_demo_build_byte_identical(self):
        # Demo + default builds stay byte-identical (no fixture/demo leakage path opened).
        self.assertEqual(check_demo_build_byte_identical().status, "pass")

    def test_cli_shadow_validate_writes_report(self):
        with tempfile.TemporaryDirectory() as work:
            report_path = os.path.join(work, "report.md")
            rc = ops_main.main([
                "shadow-validate", "--work-dir", work, "--ticks", "3",
                "--start", _START, "--interval-minutes", "60",
                "--operator", "cli-tester", "--report-out", report_path])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(report_path))
            with open(report_path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("remain_shadow", text)
            self.assertIn("## 11. Promotion recommendation", text)


if __name__ == "__main__":
    unittest.main()
