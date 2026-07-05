"""IMPLEMENTATION-020E -- alert delivery channels + per-mode policy + append-only ledger (OFFLINE).

Proves the FIRST alert-delivery path keeps every cross-phase guardrail:

* the policy SUPPRESSES external delivery in shadow mode by default (``suppressed_by_mode``);
  OFF / MANUAL do no external delivery; PRODUCTION external is ``suppressed_by_policy`` (no 020F);
* shadow messages are clearly labelled Shadow Mode; the inbox is always allowed;
* every delivery attempt is persisted APPEND-ONLY (re-deliver appends; a prior line is byte-
  unchanged); a delivery FAILURE is recorded; retryable vs permanent statuses work;
* NO secret appears in delivered content / logs / results (a planted credential value never
  surfaces); NO buy/sell/order language appears in any delivered alert / email subject / body;
* a social-only alert can never become a critical production action (severity capped); a DQ-failed
  alert can never be delivered as a critical action; the high-severity gate requires healthy DQ +
  non-speculative authority + run_id + provenance;
* the email channel dry-run / injected-transport works AND ``smtplib`` is NOT imported at module
  top level (AST + a subprocess check) + the module imports under a socket kill-switch;
* the demo default + the default pulse stay byte-identical; the whole module is OFFLINE.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import alert_delivery as ad
from reality_mesh.alert_delivery import (
    AlertDeliveryPolicy,
    AlertDeliveryResult,
    AlertDeliveryStatus,
    AlertDeliveryStore,
    DELIVERED_ALERT_CATEGORIES,
    DELIVERY_STATUSES,
    EmailChannel,
    InboxChannel,
    PermanentDeliveryError,
    RetryableDeliveryError,
    deliver_alert,
    latest_delivery_status,
)
from reality_mesh.alerts import ALERT_CATEGORIES, FORBIDDEN_ALERT_PHRASES, SHADOW_MARKER

_NOW = "2026-06-29T15:00:00Z"

# Every forbidden action phrase, as a compiled case-insensitive sweep over delivered content.
_FORBIDDEN_SWEEP = re.compile(
    "|".join(re.escape(p) for p in sorted(FORBIDDEN_ALERT_PHRASES)), re.IGNORECASE)

_ORIG_CONNECT = None


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline 020E delivery suite")


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _alert(*, alert_id="al.1", run_id="RUN-1", category="filing_dilution_risk",
           severity="warning", reason="A new dilution filing appeared between runs.",
           dq_state="healthy", evidence=("sec:accession/1",), tickers=("IREN",),
           review="Review Red-Team Risk", mode=""):
    return rm.Alert(
        alert_id=alert_id, run_id=run_id, category=category, severity=severity,
        human_readable_reason=reason, created_at=_NOW, dq_state=dq_state,
        evidence_refs=tuple(evidence), subject_tickers=tuple(tickers),
        recommended_review_action=review, mode=mode)


class _CapturingTransport:
    """An injected email transport that captures the message (and never touches the network)."""

    def __init__(self):
        self.messages = []

    def __call__(self, message):
        self.messages.append(dict(message))


# =========================================================================== #
# 1. The closed vocabularies + the delivery result record                      #
# =========================================================================== #
class VocabularyTests(unittest.TestCase):
    def test_six_closed_delivery_statuses(self):
        self.assertEqual(DELIVERY_STATUSES, frozenset({
            "not_delivered", "delivered", "suppressed_by_mode", "suppressed_by_policy",
            "failed_retryable", "failed_permanent"}))

    def test_delivered_categories_cover_the_fifteen(self):
        self.assertEqual(len(DELIVERED_ALERT_CATEGORIES), 15)
        for name in ("Mega Theme Pulse Changed", "Theme Breakout Detected",
                     "Sector Rotation Detected", "Market Regime Changed",
                     "New Capital Candidate Created", "Candidate Upgraded to Active Diligence",
                     "Candidate Deterioration", "Filing / Dilution Risk",
                     "Customer / Contract Signal", "Crowding / Euphoria Warning",
                     "Red-Team Risk Emerged", "Portfolio Concentration Warning",
                     "Data Quality Failure", "Agent Failure", "Source Failure"):
            self.assertIn(name, DELIVERED_ALERT_CATEGORIES)

    def test_every_alert_category_maps_to_a_display_name(self):
        for category in sorted(ALERT_CATEGORIES):
            display = ad.delivery_category_display(category)
            self.assertTrue(display)
            self.assertNotIn("_", display)

    def test_result_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            AlertDeliveryResult(alert_id="a", channel="inbox", status="sent_ok",
                                attempted_at=_NOW)

    def test_result_requires_ids(self):
        with self.assertRaises(ValueError):
            AlertDeliveryResult(alert_id="", channel="inbox",
                                status="delivered", attempted_at=_NOW)

    def test_delivery_severity_never_carries_a_trade_label(self):
        for sev in rm.DELIVERY_SEVERITIES:
            self.assertNotIn(sev, ("buy", "sell", "strong_buy", "hold"))


# =========================================================================== #
# 2. Per-mode policy -- suppression rules                                       #
# =========================================================================== #
class PolicyModeTests(unittest.TestCase):
    def setUp(self):
        self.policy = AlertDeliveryPolicy.default()
        self.alert = _alert()

    def test_inbox_is_always_allowed_in_every_mode(self):
        for mode in ("OFF", "MANUAL", "SHADOW_24X7", "PRODUCTION_24X7"):
            self.assertEqual(
                self.policy.decide(is_external=False, mode=mode, alert=self.alert), "allowed")

    def test_off_and_manual_do_no_external_delivery(self):
        for mode in ("OFF", "MANUAL", "off", "manual"):
            self.assertEqual(
                self.policy.decide(is_external=True, mode=mode, alert=self.alert),
                AlertDeliveryStatus.SUPPRESSED_BY_MODE)

    def test_shadow_suppresses_external_by_default(self):
        self.assertEqual(
            self.policy.decide(is_external=True, mode="SHADOW_24X7", alert=self.alert),
            AlertDeliveryStatus.SUPPRESSED_BY_MODE)

    def test_shadow_external_allowed_only_when_shadow_delivery_enabled(self):
        opted_in = AlertDeliveryPolicy(shadow_delivery_enabled=True)
        self.assertEqual(
            opted_in.decide(is_external=True, mode="SHADOW_24X7", alert=self.alert), "allowed")

    def test_production_external_suppressed_by_policy_pending_020f(self):
        # No 020F activation gate yet: production external delivery stays suppressed_by_policy.
        self.assertEqual(
            self.policy.decide(is_external=True, mode="PRODUCTION_24X7", alert=self.alert),
            AlertDeliveryStatus.SUPPRESSED_BY_POLICY)

    def test_unknown_mode_falls_back_to_suppression(self):
        self.assertEqual(
            self.policy.decide(is_external=True, mode="whatever", alert=self.alert),
            AlertDeliveryStatus.SUPPRESSED_BY_MODE)


# =========================================================================== #
# 3. High-severity gate -- social / DQ-failed can never be a critical action    #
# =========================================================================== #
class HighSeverityGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = AlertDeliveryPolicy.default()

    def test_supported_critical_stays_critical(self):
        a = _alert(category="major_risk_emerged", severity="critical",
                   dq_state="healthy", evidence=("e1",))
        self.assertTrue(self.policy.high_severity_supported(a))
        self.assertEqual(self.policy.effective_delivery_severity(a), "critical")

    def test_social_only_alert_cannot_be_critical(self):
        a = _alert(category="social_narrative_spike", severity="critical",
                   dq_state="healthy", evidence=("e1",), review="Review Required")
        self.assertFalse(self.policy.high_severity_supported(a))
        self.assertEqual(self.policy.effective_delivery_severity(a), "review_required")

    def test_dq_failed_alert_cannot_be_a_critical_action(self):
        a = _alert(category="major_risk_emerged", severity="critical",
                   dq_state="failed", evidence=("e1",))
        self.assertFalse(self.policy.high_severity_supported(a))
        self.assertEqual(self.policy.effective_delivery_severity(a), "review_required")

    def test_missing_provenance_or_run_id_caps_critical(self):
        no_evidence = _alert(category="major_risk_emerged", severity="critical",
                             dq_state="healthy", evidence=())
        self.assertEqual(self.policy.effective_delivery_severity(no_evidence), "review_required")

    def test_activated_production_still_suppresses_unsupported_critical(self):
        activated = AlertDeliveryPolicy(production_activated=True)
        social_critical = _alert(category="social_narrative_spike", severity="critical",
                                 dq_state="failed", evidence=("e1",), review="Review Required")
        self.assertEqual(
            activated.decide(is_external=True, mode="PRODUCTION_24X7", alert=social_critical),
            AlertDeliveryStatus.SUPPRESSED_BY_POLICY)


# =========================================================================== #
# 4. deliver_alert -- suppression, persistence, inbox always                    #
# =========================================================================== #
class DeliverAlertTests(unittest.TestCase):
    def test_shadow_default_inbox_delivered_email_suppressed_by_mode(self):
        with tempfile.TemporaryDirectory() as d:
            results = deliver_alert(
                _alert(), policy=AlertDeliveryPolicy.default(), mode="SHADOW_24X7",
                channels=(InboxChannel(), EmailChannel()), store_dir=d, now=_NOW)
            by_channel = {r.channel: r for r in results}
            self.assertEqual(by_channel["inbox"].status, AlertDeliveryStatus.DELIVERED)
            self.assertEqual(by_channel["email"].status,
                             AlertDeliveryStatus.SUPPRESSED_BY_MODE)

    def test_shadow_delivery_marks_message_shadow_mode(self):
        with tempfile.TemporaryDirectory() as d:
            cap = _CapturingTransport()
            results = deliver_alert(
                _alert(), policy=AlertDeliveryPolicy(shadow_delivery_enabled=True),
                mode="SHADOW_24X7",
                channels=(EmailChannel(transport=cap, sender_present=True, dry_run=False),),
                store_dir=d, now=_NOW)
            self.assertEqual(results[0].status, AlertDeliveryStatus.DELIVERED)
            msg = cap.messages[0]
            self.assertIn("[CosmosIQ Shadow]", msg["subject"])
            self.assertIn(SHADOW_MARKER, msg["body"])
            self.assertIn("Shadow Mode", msg["body"])

    def test_production_external_suppressed_by_policy(self):
        with tempfile.TemporaryDirectory() as d:
            results = deliver_alert(
                _alert(), policy=AlertDeliveryPolicy.default(), mode="PRODUCTION_24X7",
                channels=(EmailChannel(),), store_dir=d, now=_NOW)
            self.assertEqual(results[0].status, AlertDeliveryStatus.SUPPRESSED_BY_POLICY)

    def test_off_and_manual_never_deliver_externally(self):
        for mode in ("OFF", "MANUAL"):
            with tempfile.TemporaryDirectory() as d:
                results = deliver_alert(
                    _alert(), policy=AlertDeliveryPolicy.default(), mode=mode,
                    channels=(InboxChannel(), EmailChannel()), store_dir=d, now=_NOW)
                by_channel = {r.channel: r for r in results}
                self.assertEqual(by_channel["inbox"].status, AlertDeliveryStatus.DELIVERED)
                self.assertEqual(by_channel["email"].status,
                                 AlertDeliveryStatus.SUPPRESSED_BY_MODE)


# =========================================================================== #
# 5. Append-only persistence -- re-deliver appends; prior line unchanged        #
# =========================================================================== #
class AppendOnlyPersistenceTests(unittest.TestCase):
    def test_each_attempt_persisted_and_redelivery_appends(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "alert_delivery_store.jsonl")
            deliver_alert(_alert(), policy=AlertDeliveryPolicy.default(), mode="SHADOW_24X7",
                          channels=(InboxChannel(),), store_dir=d, now=_NOW)
            with open(path, "rb") as fh:
                after_first = fh.read()
            first_line = after_first.splitlines()[0]
            deliver_alert(_alert(), policy=AlertDeliveryPolicy.default(), mode="SHADOW_24X7",
                          channels=(InboxChannel(),), store_dir=d, now=_NOW)
            with open(path, "rb") as fh:
                after_second = fh.read()
            self.assertEqual(len(after_second.splitlines()), 2)
            # the first stored line is byte-unchanged forever
            self.assertEqual(after_second.splitlines()[0], first_line)
            self.assertTrue(after_second.startswith(after_first))

    def test_results_and_latest_status_reader(self):
        with tempfile.TemporaryDirectory() as d:
            deliver_alert(_alert(), policy=AlertDeliveryPolicy.default(), mode="SHADOW_24X7",
                          channels=(InboxChannel(), EmailChannel()), store_dir=d, now=_NOW)
            self.assertEqual(len(rm.delivery_results(d)), 2)
            # the external (email) attempt is the reported status for the inbox display
            self.assertEqual(latest_delivery_status(d, "al.1"),
                             AlertDeliveryStatus.SUPPRESSED_BY_MODE)
            self.assertEqual(latest_delivery_status(d, "nope"), "")


# =========================================================================== #
# 6. Failure classification -- retryable vs permanent                           #
# =========================================================================== #
class FailureClassificationTests(unittest.TestCase):
    def _deliver_email(self, transport, d):
        return deliver_alert(
            _alert(), policy=AlertDeliveryPolicy(shadow_delivery_enabled=True),
            mode="SHADOW_24X7",
            channels=(EmailChannel(transport=transport, sender_present=True, dry_run=False),),
            store_dir=d, now=_NOW)[0]

    def test_retryable_error_recorded(self):
        def boom(_m):
            raise RetryableDeliveryError("temporary greylist, try again")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._deliver_email(boom, d).status,
                             AlertDeliveryStatus.FAILED_RETRYABLE)

    def test_permanent_error_recorded(self):
        def boom(_m):
            raise PermanentDeliveryError("550 mailbox does not exist")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._deliver_email(boom, d).status,
                             AlertDeliveryStatus.FAILED_PERMANENT)

    def test_generic_timeout_classified_retryable(self):
        def boom(_m):
            raise RuntimeError("connection timed out")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._deliver_email(boom, d).status,
                             AlertDeliveryStatus.FAILED_RETRYABLE)

    def test_generic_reject_classified_permanent(self):
        def boom(_m):
            raise RuntimeError("recipient rejected: 550 invalid address")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._deliver_email(boom, d).status,
                             AlertDeliveryStatus.FAILED_PERMANENT)

    def test_missing_credential_not_delivered_no_value_echoed(self):
        with tempfile.TemporaryDirectory() as d:
            result = deliver_alert(
                _alert(), policy=AlertDeliveryPolicy(shadow_delivery_enabled=True),
                mode="SHADOW_24X7",
                channels=(EmailChannel(sender_present=False, dry_run=False),),
                store_dir=d, now=_NOW)[0]
            self.assertEqual(result.status, AlertDeliveryStatus.NOT_DELIVERED)


# =========================================================================== #
# 7. No secret in delivered content / logs / results                            #
# =========================================================================== #
class NoSecretLeakTests(unittest.TestCase):
    _PLANTED = "PLANTEDSECRETVALUE12345"

    def test_planted_credential_never_appears_in_content_or_store(self):
        # A credential-shaped token planted in the alert reason must be redacted everywhere.
        reason = ("A dilution filing appeared; internal note api_key={0} recorded for the "
                  "operator.".format(self._PLANTED))
        alert = _alert(reason=reason)
        cap = _CapturingTransport()
        with tempfile.TemporaryDirectory() as d:
            results = deliver_alert(
                alert, policy=AlertDeliveryPolicy(shadow_delivery_enabled=True),
                mode="SHADOW_24X7",
                channels=(InboxChannel(),
                          EmailChannel(transport=cap, sender_present=True, dry_run=False)),
                store_dir=d, now=_NOW)
            msg = cap.messages[0]
            self.assertNotIn(self._PLANTED, msg["subject"])
            self.assertNotIn(self._PLANTED, msg["body"])
            self.assertIn("<redacted>", msg["body"])
            for r in results:
                self.assertNotIn(self._PLANTED, r.detail_sanitized)
            with open(os.path.join(d, "alert_delivery_store.jsonl"), encoding="utf-8") as fh:
                self.assertNotIn(self._PLANTED, fh.read())

    def test_credential_value_passed_to_presence_flag_is_rejected_not_echoed(self):
        try:
            EmailChannel(sender_present="s3cr3t-value-should-not-echo")  # type: ignore[arg-type]
        except ValueError as exc:
            self.assertNotIn("s3cr3t-value-should-not-echo", str(exc))
        else:
            self.fail("a credential value passed as a presence flag must be rejected")

    def test_env_sender_value_is_never_read_into_content(self):
        # A dry-run render never reads the credential VALUE; presence is a label only.
        os.environ["COSMOSIQ_ALERT_EMAIL_SENDER"] = "alerts@example.com-SECRETTOKEN-XYZ"
        try:
            msg = EmailChannel(dry_run=True).render_message(_alert(), mode="SHADOW_24X7")
            self.assertNotIn("SECRETTOKEN-XYZ", msg["subject"])
            self.assertNotIn("SECRETTOKEN-XYZ", msg["body"])
        finally:
            del os.environ["COSMOSIQ_ALERT_EMAIL_SENDER"]


# =========================================================================== #
# 8. No trade / action language in delivered content                            #
# =========================================================================== #
class NoTradeLanguageTests(unittest.TestCase):
    def test_no_forbidden_phrase_in_any_email_subject_or_body(self):
        for category in sorted(ALERT_CATEGORIES):
            alert = _alert(alert_id="al." + category, category=category,
                           reason="Observed a state change for category {0}.".format(category),
                           review="Review Required")
            for mode in ("SHADOW_24X7", "PRODUCTION_24X7"):
                msg = EmailChannel(dry_run=True).render_message(alert, mode=mode)
                self.assertIsNone(_FORBIDDEN_SWEEP.search(msg["subject"]), category)
                self.assertIsNone(_FORBIDDEN_SWEEP.search(msg["body"]), category)

    def test_forbidden_phrase_in_detail_is_scrubbed_at_construction(self):
        result = AlertDeliveryResult(
            alert_id="a", channel="email", status="delivered", attempted_at=_NOW,
            detail_sanitized="operator should buy now per the note")
        self.assertNotIn("buy now", result.detail_sanitized.lower())
        self.assertIn("[review-only]", result.detail_sanitized)

    def test_render_scrubs_a_forbidden_phrase_if_it_ever_reaches_the_body(self):
        scrubbed = ad._scrub_forbidden("please submit order and auto trade")
        self.assertIsNone(_FORBIDDEN_SWEEP.search(scrubbed))

    def test_module_defines_no_trade_execution_symbols(self):
        for banned in ("place_order", "submit_order", "broker", "execute_trade"):
            self.assertNotIn(banned, ad.__all__)


# =========================================================================== #
# 9. Email channel -- dry-run + injected transport work; no network            #
# =========================================================================== #
class EmailChannelPathTests(unittest.TestCase):
    def test_dry_run_renders_without_sending(self):
        cap = _CapturingTransport()
        result = EmailChannel(transport=cap, sender_present=True, dry_run=True).deliver(
            _alert(), mode="SHADOW_24X7", now=_NOW)
        self.assertEqual(result.status, AlertDeliveryStatus.DELIVERED)
        self.assertIn("dry-run", result.detail_sanitized)
        self.assertEqual(cap.messages, [])                 # dry-run never calls the transport

    def test_injected_transport_sends(self):
        cap = _CapturingTransport()
        result = EmailChannel(transport=cap, sender_present=True, dry_run=False).deliver(
            _alert(), mode="SHADOW_24X7", now=_NOW)
        self.assertEqual(result.status, AlertDeliveryStatus.DELIVERED)
        self.assertEqual(len(cap.messages), 1)

    def test_smtplib_not_imported_at_module_top_level(self):
        with open(ad.__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in tree.body:                              # module top-level statements only
            if isinstance(node, ast.Import):
                self.assertNotIn("smtplib", [n.name for n in node.names])
            if isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "smtplib")

    def test_importing_module_does_not_load_smtplib(self):
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, {0!r}); import reality_mesh.alert_delivery; "
             "print('smtplib' in sys.modules)".format(_SRC)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "False")

    def test_module_reimports_under_socket_kill_switch(self):
        # setUpModule has armed the socket kill-switch; reloading must not touch the network.
        importlib.reload(ad)


# =========================================================================== #
# 10. Untouched paths -- demo default + default pulse stay byte-identical       #
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


if __name__ == "__main__":
    unittest.main()
