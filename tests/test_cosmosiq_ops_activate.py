"""IMPLEMENTATION-021C -- the Production 24x7 activation FLOW + sign-off reader. OFFLINE.

THE SAFETY TESTS. They prove production is UNFLIPPABLE without genuine, complete evidence:

* the STRICT ``read_operator_signoff`` reader accepts ONLY a fully-filled PRODUCTION approval and
  rejects a missing file, a CONTINUE_SHADOW sign-off, an unchecked acknowledgement, a missing
  name / timestamp, and a malformed file (never raising);
* ``activate`` REFUSES in the current repo state (no sign-off; the two live items unmet);
* THE KEY TEST: a fully-valid PRODUCTION sign-off but the live items still open -> STILL REFUSED
  (the sign-off is necessary, not sufficient -- code cannot clear the live/shadow items);
* the path is reachable ONLY with complete evidence: every machine + manual item satisfied AND a
  valid sign-off -> activate flips to PRODUCTION_24X7; the marker is written; the banner carries
  NO trade control;
* ``rollback`` steps PRODUCTION -> SHADOW -> MANUAL -> OFF, records a trigger, refuses an upgrade;
* everything is offline (a socket kill-switch armed), deterministic, no secret, no trade token,
  and NO test (nor the code) ever creates ``reports/OPERATOR_SIGNOFF_020J.md``.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest

from cosmosiq_ops.activate import (
    SERVICE_MODE_MARKER,
    format_activation_report,
    format_rollback_report,
    read_current_mode,
    run_activation,
    run_rollback,
)
from cosmosiq_ops.ci_gate import TRADE_WORD_RE, check_demo_build_byte_identical
from cosmosiq_service.activation import (
    SIGNOFF_PRODUCTION_MODE,
    build_activation_checklist,
    read_operator_signoff,
)
from cosmosiq_service.activation import CheckResult

_NOW = "2026-06-29T00:00:00Z"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAL_SIGNOFF = os.path.join(_REPO_ROOT, "reports", "OPERATOR_SIGNOFF_020J.md")

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: the 021C activation flow must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #
def _signoff_text(*, mode=SIGNOFF_PRODUCTION_MODE, name="Jane Operator",
                  timestamp="2026-06-29T00:00:00Z", acks=(True, True, True, True)):
    ack_lines = "\n".join(
        "- [{0}] **Acknowledgement {1}** accepted".format("x" if ok else " ", i + 1)
        for i, ok in enumerate(acks))
    return (
        "# Operator Signoff\n\n"
        "## Signoff record\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        "| Operator name | {name} |\n"
        "| Timestamp (RFC3339) | {ts} |\n"
        "| Approved mode | `{mode}` |\n\n"
        "## Acknowledgements\n\n"
        "{acks}\n"
    ).format(name=name, ts=timestamp, mode=mode, acks=ack_lines)


def _write_signoff(dir_path, **kwargs):
    path = os.path.join(dir_path, "signoff.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_signoff_text(**kwargs))
    return path


def _all_pass_checks(exclude=()):
    """Synthetic checks marking EVERY checklist item satisfied (minus ``exclude``)."""
    return {item.id: CheckResult(item.id, "pass", ("synthetic complete evidence",))
            for item in build_activation_checklist().items if item.id not in set(exclude)}


# --------------------------------------------------------------------------- #
# read_operator_signoff -- the strict reader                                    #
# --------------------------------------------------------------------------- #
class SignoffReaderTests(unittest.TestCase):
    def test_missing_file_returns_none(self):
        self.assertIsNone(read_operator_signoff("/no/such/signoff/file.md"))

    def test_valid_production_signoff_parses(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_signoff(d)
            approval = read_operator_signoff(path)
        self.assertIsNotNone(approval)
        self.assertEqual(approval.approved_by, "Jane Operator")
        self.assertEqual(approval.approved_at, "2026-06-29T00:00:00Z")
        self.assertEqual(approval.target_mode, "production_24x7")

    def test_continue_shadow_signoff_is_not_a_production_approval(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_signoff(d, mode="CONTINUE_SHADOW_24X7")
            self.assertIsNone(read_operator_signoff(path))

    def test_template_with_both_tokens_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_signoff(
                d, mode="CONTINUE_SHADOW_24X7` **or** `PRODUCTION_24X7_APPROVED")
            self.assertIsNone(read_operator_signoff(path))

    def test_unchecked_acknowledgement_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_signoff(d, acks=(True, True, False, True))
            self.assertIsNone(read_operator_signoff(path))

    def test_missing_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_signoff(d, name="")
            self.assertIsNone(read_operator_signoff(path))

    def test_placeholder_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_signoff(d, name="<operator name>")
            self.assertIsNone(read_operator_signoff(path))

    def test_missing_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_signoff(d, timestamp="")
            self.assertIsNone(read_operator_signoff(path))

    def test_malformed_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_signoff(d, timestamp="last Tuesday")
            self.assertIsNone(read_operator_signoff(path))

    def test_malformed_file_returns_none_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "garbage.md")
            with open(path, "wb") as fh:
                fh.write(b"\x00\x01 not a signoff \xff at all | | |")
            self.assertIsNone(read_operator_signoff(path))

    def test_directory_path_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(read_operator_signoff(d))


# --------------------------------------------------------------------------- #
# activate -- the refusal cases (nothing written)                               #
# --------------------------------------------------------------------------- #
class ActivateRefusalTests(unittest.TestCase):
    def _assert_nothing_flipped(self, work_dir, outcome):
        self.assertFalse(outcome.activated)
        self.assertEqual(outcome.marker_path, "")
        marker = os.path.join(work_dir, "store", SERVICE_MODE_MARKER)
        self.assertFalse(os.path.exists(marker), "a mode marker must NOT be written on refusal")
        self.assertIsNot(read_current_mode(os.path.join(work_dir, "store")).value,
                         "production_24x7")

    def test_no_signoff_refuses_current_state_real_path(self):
        # The CURRENT repo state: no sign-off, live items unmet -> REFUSED (the real prod-check).
        with tempfile.TemporaryDirectory() as work:
            outcome = run_activation(work, now=_NOW,
                                     signoff_path=os.path.join(work, "does_not_exist.md"),
                                     repo_root=_REPO_ROOT, quick=True)
            self.assertEqual(outcome.verdict, "shadow_24x7_only")
            self.assertEqual(outcome.blocking_failures, ())
            for item in ("live_source_health", "operator_shadow_validation"):
                self.assertIn(item, outcome.manual_review_items)
            self.assertFalse(outcome.signoff_present)
            self.assertFalse(outcome.signoff_valid)
            self._assert_nothing_flipped(work, outcome)

    def test_continue_shadow_signoff_refuses(self):
        with tempfile.TemporaryDirectory() as work:
            signoff = _write_signoff(work, mode="CONTINUE_SHADOW_24X7")
            outcome = run_activation(work, now=_NOW, signoff_path=signoff,
                                     checks=_all_pass_checks())
            self.assertFalse(outcome.signoff_valid)
            self.assertTrue(outcome.signoff_present)
            self._assert_nothing_flipped(work, outcome)

    def test_unchecked_ack_signoff_refuses(self):
        with tempfile.TemporaryDirectory() as work:
            signoff = _write_signoff(work, acks=(True, False, True, True))
            outcome = run_activation(work, now=_NOW, signoff_path=signoff,
                                     checks=_all_pass_checks())
            self.assertFalse(outcome.signoff_valid)
            self._assert_nothing_flipped(work, outcome)

    def test_missing_timestamp_signoff_refuses(self):
        with tempfile.TemporaryDirectory() as work:
            signoff = _write_signoff(work, timestamp="")
            outcome = run_activation(work, now=_NOW, signoff_path=signoff,
                                     checks=_all_pass_checks())
            self._assert_nothing_flipped(work, outcome)

    def test_the_key_test_valid_signoff_but_open_live_items_still_refuses(self):
        # THE KEY TEST: a fully-valid PRODUCTION sign-off, but the two live items are STILL
        # manual_review -> activate STILL REFUSES. The sign-off is necessary but NOT sufficient;
        # code cannot clear live_source_health / operator_shadow_validation.
        with tempfile.TemporaryDirectory() as work:
            signoff = _write_signoff(work)
            self.assertIsNotNone(read_operator_signoff(signoff))     # the sign-off IS valid
            checks = _all_pass_checks(
                exclude=("live_source_health", "operator_shadow_validation"))
            outcome = run_activation(work, now=_NOW, signoff_path=signoff, checks=checks)
            self.assertTrue(outcome.signoff_valid)                   # approval recorded...
            self.assertFalse(outcome.activated)                      # ...yet production REFUSED
            self.assertEqual(
                set(outcome.manual_review_items),
                {"live_source_health", "operator_shadow_validation"})
            self.assertEqual(outcome.blocking_failures, ())
            self._assert_nothing_flipped(work, outcome)


# --------------------------------------------------------------------------- #
# activate -- reachable ONLY with complete evidence                             #
# --------------------------------------------------------------------------- #
class ActivateReachableTests(unittest.TestCase):
    def test_fully_cleared_hypothetical_flips_to_production(self):
        with tempfile.TemporaryDirectory() as work:
            signoff = _write_signoff(work)
            outcome = run_activation(work, now=_NOW, signoff_path=signoff,
                                     checks=_all_pass_checks())
            self.assertTrue(outcome.activated)
            self.assertEqual(outcome.verdict, "production_24x7_approved")
            self.assertEqual(outcome.target_mode, "production_24x7")
            # the sanctioned mode marker was written and the service honours PRODUCTION_24X7
            marker = os.path.join(work, "store", SERVICE_MODE_MARKER)
            self.assertTrue(os.path.exists(marker))
            self.assertEqual(read_current_mode(os.path.join(work, "store")).value,
                             "production_24x7")
            # the banner has NO trade control and keeps the permanent guarantees
            self.assertIn("Mode: PRODUCTION_24X7", outcome.banner)
            self.assertIn("Broker: Disabled", outcome.banner)
            self.assertIn("Execution: Manual Review Only", outcome.banner)
            self.assertIn("Alert Delivery: On", outcome.banner)
            self.assertIsNone(TRADE_WORD_RE.search(outcome.banner))

    def test_activated_marker_and_report_carry_no_trade_or_secret_token(self):
        with tempfile.TemporaryDirectory() as work:
            signoff = _write_signoff(work)
            outcome = run_activation(work, now=_NOW, signoff_path=signoff,
                                     checks=_all_pass_checks())
            marker = os.path.join(work, "store", SERVICE_MODE_MARKER)
            with open(marker, encoding="utf-8") as fh:
                marker_text = fh.read()
            report_text = format_activation_report(outcome)
            for blob in (marker_text, report_text, outcome.banner):
                self.assertIsNone(TRADE_WORD_RE.search(blob))
                lowered = blob.lower()
                for tok in ("sk-", "api_key", "secret", "password", "bearer "):
                    self.assertNotIn(tok, lowered)

    def test_activation_is_deterministic(self):
        markers = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as work:
                signoff = _write_signoff(work)
                run_activation(work, now=_NOW, signoff_path=signoff, checks=_all_pass_checks())
                with open(os.path.join(work, "store", SERVICE_MODE_MARKER),
                          encoding="utf-8") as fh:
                    markers.append(fh.read())
        self.assertEqual(markers[0], markers[1])


# --------------------------------------------------------------------------- #
# rollback -- always downgrades; refuses an upgrade                             #
# --------------------------------------------------------------------------- #
class RollbackTests(unittest.TestCase):
    def _activate(self, work):
        signoff = _write_signoff(work)
        run_activation(work, now=_NOW, signoff_path=signoff, checks=_all_pass_checks())

    def test_rollback_steps_production_to_shadow_to_manual_to_off(self):
        with tempfile.TemporaryDirectory() as work:
            self._activate(work)
            store = os.path.join(work, "store")
            for target, expect in (("SHADOW_24X7", "shadow_24x7"),
                                   ("MANUAL", "manual"), ("OFF", "off")):
                outcome = run_rollback(work, to=target, now=_NOW, trigger="operator_manual")
                self.assertTrue(outcome.allowed)
                self.assertTrue(outcome.applied)
                self.assertEqual(outcome.trigger, "operator_manual")
                self.assertTrue(outcome.trigger_description)
                self.assertEqual(read_current_mode(store).value, expect)

    def test_rollback_records_a_safety_trigger(self):
        with tempfile.TemporaryDirectory() as work:
            self._activate(work)
            outcome = run_rollback(work, to="OFF", now=_NOW, trigger="secret_leakage")
            self.assertTrue(outcome.applied)
            self.assertEqual(outcome.trigger, "secret_leakage")
            marker = os.path.join(work, "store", SERVICE_MODE_MARKER)
            with open(marker, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data.get("rollback_trigger"), "secret_leakage")

    def test_rollback_refuses_an_upgrade(self):
        with tempfile.TemporaryDirectory() as work:
            # start at SHADOW, then try to "roll back" UP to PRODUCTION -> refused, unchanged
            self._activate(work)
            run_rollback(work, to="SHADOW_24X7", now=_NOW)
            store = os.path.join(work, "store")
            outcome = run_rollback(work, to="PRODUCTION_24X7", now=_NOW)
            self.assertFalse(outcome.allowed)
            self.assertFalse(outcome.applied)
            self.assertEqual(read_current_mode(store).value, "shadow_24x7")

    def test_rollback_rejects_unknown_trigger(self):
        with tempfile.TemporaryDirectory() as work:
            self._activate(work)
            outcome = run_rollback(work, to="OFF", now=_NOW, trigger="totally_made_up")
            self.assertFalse(outcome.allowed)
            self.assertFalse(outcome.applied)
            self.assertEqual(read_current_mode(os.path.join(work, "store")).value,
                             "production_24x7")


# --------------------------------------------------------------------------- #
# Global guarantees                                                             #
# --------------------------------------------------------------------------- #
class GuaranteeTests(unittest.TestCase):
    def test_demo_build_byte_identical(self):
        self.assertEqual(check_demo_build_byte_identical().status, "pass")

    def test_no_test_or_code_creates_the_real_signoff_file(self):
        # The real production sign-off is the operator's act alone -- never created by 021C.
        self.assertFalse(os.path.exists(_REAL_SIGNOFF),
                         "reports/OPERATOR_SIGNOFF_020J.md must NOT exist / be created")

    def test_rollback_report_and_activation_report_render(self):
        with tempfile.TemporaryDirectory() as work:
            outcome = run_activation(work, now=_NOW,
                                     signoff_path=os.path.join(work, "nope.md"),
                                     checks=_all_pass_checks(
                                         exclude=("live_source_health",
                                                  "operator_shadow_validation",
                                                  "operator_signoff")))
            text = format_activation_report(outcome)
            self.assertIn("REFUSED", text)
            self.assertIn("no operator sign-off file found", text)
            roll = run_rollback(work, to="OFF", now=_NOW)
            self.assertIn("rollback", format_rollback_report(roll).lower())


if __name__ == "__main__":
    unittest.main()
