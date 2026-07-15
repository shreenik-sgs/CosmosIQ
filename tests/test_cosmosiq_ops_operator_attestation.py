"""GO-LIVE PL-2 -- evidence-backed operator attestation for the two unclearable 020F items.

OFFLINE, deterministic. Proves the honesty core:

* an attestation NEVER clears an item on its own -- a verifier INDEPENDENTLY re-reads the REAL
  persisted store (run + events + timestamps) and confirms it. A missing / unhealthy / stale run,
  or a too-few / single-day / missing-run shadow window, stays manual_review_required (BLOCKING);
* a real persisted live run + a matching attestation -> a PASS CheckResult; a real >=3-run /
  >=2-day window + a matching attestation -> a PASS;
* prod-check with NO attestations is byte-identical to before (both items stay manual; production
  refused; lands shadow); with BOTH attested + a valid signoff/approval those two items clear and
  production_mode_allowed can be True;
* append-only + correction-not-mutation; the CLI refuses an unreal run; NO trade/score/secret;
  deterministic content ids; runs fully offline (a socket kill-switch is armed).
"""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh import run_live_pulse
from reality_mesh.adapters.fmp_live import FmpLiveAdapter
from reality_mesh.adapters.sec_edgar_live import SecEdgarLiveAdapter
from reality_mesh.stores import RunStore
from reality_mesh.validation import assert_no_trade_fields

import cosmosiq_ops.operator_attestation as oa
from cosmosiq_ops.operator_attestation import (
    LiveSourceHealthAttestation,
    OperatorAttestationStore,
    ShadowValidationAttestation,
    attestation_activation_status,
    latest_live_source_health_attestation,
    latest_shadow_validation_attestation,
    record_live_source_health_attestation,
    record_shadow_validation_attestation,
    verify_live_source_health,
    verify_shadow_validation,
)
from cosmosiq_service.activation import ChecklistStatus

_HERE = os.path.dirname(os.path.abspath(__file__))
_SEC_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "sec_edgar_live")
_FMP_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "fmp_live")
_REPO_ROOT = os.path.dirname(_HERE)
_NOW = "2026-06-29T15:00:00Z"

_CIK_TO_FIXTURE = {
    "0001878848": "sec_submissions_iren_live.json",
    "0000123456": "sec_submissions_aaoi_live.json",
}

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: attestation tests run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _load(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as fh:
        return json.load(fh)


def _sec_adapter():
    return SecEdgarLiveAdapter(
        transport={
            "company_tickers": lambda: _load(_SEC_DIR, "company_tickers.json"),
            "submissions": lambda cik: _load(_SEC_DIR, _CIK_TO_FIXTURE[str(cik).zfill(10)])},
        sec_user_agent_present=True)


def _fmp_fetch(prefix):
    return lambda symbol: _load(_FMP_DIR, "{0}_{1}.json".format(prefix, str(symbol).strip().upper()))


def _fmp_adapter():
    return FmpLiveAdapter(
        transport={
            "profile": _fmp_fetch("profile"), "income_statement": _fmp_fetch("income"),
            "balance_sheet": _fmp_fetch("balance"), "cash_flow": _fmp_fetch("cashflow"),
            "ratios": _fmp_fetch("ratios"), "quote": _fmp_fetch("quote")},
        fmp_api_key_present=True)


def _seed_live_run(store_dir, *, now, run_id, adapters=None):
    """Persist ONE real live run (SEC + FMP by default) into ``store_dir``; return its run_id."""
    result = run_live_pulse(
        "IREN,AAOI", "physical-ai,robotics", store_dir=store_dir, now=now, run_id=run_id,
        adapters=adapters if adapters is not None else [_sec_adapter(), _fmp_adapter()])
    assert result.persisted, "seed run must persist"
    return result.run_id


def _seed_window(store_dir, days, *, run_prefix="live-run"):
    """Seed one real live run per instant in ``days``; return the ordered run ids."""
    return [
        _seed_live_run(store_dir, now=day, run_id="{0}-{1}".format(run_prefix, i))
        for i, day in enumerate(days)]


_THREE_DAYS = ("2026-06-27T14:00:00Z", "2026-06-28T14:00:00Z", "2026-06-29T14:00:00Z")


# --------------------------------------------------------------------------- #
# 1. Models -- required fields, no trade/score field                            #
# --------------------------------------------------------------------------- #
class ModelTests(unittest.TestCase):
    def test_live_attestation_requires_reviewed_by_and_run(self):
        with self.assertRaises(ValueError):
            LiveSourceHealthAttestation(
                attestation_id="a", run_id="r", sources_reviewed=("evidence.sec_edgar_live",),
                reviewed_by="", reviewed_at=_NOW)             # empty reviewed_by
        with self.assertRaises(ValueError):
            LiveSourceHealthAttestation(
                attestation_id="a", run_id="", sources_reviewed=("evidence.sec_edgar_live",),
                reviewed_by="op", reviewed_at=_NOW)           # empty run_id
        with self.assertRaises(ValueError):
            LiveSourceHealthAttestation(
                attestation_id="a", run_id="r", sources_reviewed=(),
                reviewed_by="op", reviewed_at=_NOW)           # no sources

    def test_shadow_attestation_requires_a_window(self):
        with self.assertRaises(ValueError):
            ShadowValidationAttestation(
                attestation_id="a", reviewed_by="op", reviewed_at=_NOW)   # no window at all
        # a runs window OR a (start,end) window is accepted
        ShadowValidationAttestation(
            attestation_id="a", window_run_ids=("r1",), reviewed_by="op", reviewed_at=_NOW)
        ShadowValidationAttestation(
            attestation_id="a", window_start="2026-06-27T00:00:00Z",
            window_end="2026-06-29T00:00:00Z", reviewed_by="op", reviewed_at=_NOW)

    def test_no_trade_or_score_field(self):
        assert_no_trade_fields(LiveSourceHealthAttestation)
        assert_no_trade_fields(ShadowValidationAttestation)
        assert_no_trade_fields(oa.AttestationCheckResult)


# --------------------------------------------------------------------------- #
# 2. Append-only store + correction-not-mutation + latest readers               #
# --------------------------------------------------------------------------- #
class StoreTests(unittest.TestCase):
    def test_record_is_append_only_and_correction_supersedes(self):
        store_dir = tempfile.mkdtemp()
        run_id = _seed_live_run(store_dir, now=_NOW, run_id="live-a")
        first = record_live_source_health_attestation(
            store_dir, run_id=run_id, sources_reviewed=["evidence.sec_edgar_live"],
            reviewed_by="op", reviewed_at=_NOW, statement="first pass")
        # a CORRECTION is a NEW record referencing the prior id (never a mutation)
        corrected = record_live_source_health_attestation(
            store_dir, run_id=run_id,
            sources_reviewed=["evidence.sec_edgar_live", "evidence.fmp_live"],
            reviewed_by="op", reviewed_at="2026-06-29T16:00:00Z", statement="corrected",
            correction_of=first.attestation_id)
        raw = OperatorAttestationStore(store_dir).read_records()
        self.assertEqual(len(raw), 2, "both the original and the correction persist (append-only)")
        # the latest reader returns the correction, not the superseded original
        latest = latest_live_source_health_attestation(store_dir)
        self.assertEqual(latest.attestation_id, corrected.attestation_id)
        self.assertNotEqual(latest.attestation_id, first.attestation_id)

    def test_record_is_idempotent_when_byte_identical(self):
        store_dir = tempfile.mkdtemp()
        run_id = _seed_live_run(store_dir, now=_NOW, run_id="live-b")
        a = record_live_source_health_attestation(
            store_dir, run_id=run_id, sources_reviewed=["evidence.sec_edgar_live"],
            reviewed_by="op", reviewed_at=_NOW)
        b = record_live_source_health_attestation(
            store_dir, run_id=run_id, sources_reviewed=["evidence.sec_edgar_live"],
            reviewed_by="op", reviewed_at=_NOW)
        self.assertEqual(a.attestation_id, b.attestation_id)
        self.assertEqual(len(OperatorAttestationStore(store_dir).read_records()), 1)

    def test_persisted_file_has_no_trade_or_secret_token(self):
        store_dir = tempfile.mkdtemp()
        run_id = _seed_live_run(store_dir, now=_NOW, run_id="live-c")
        record_live_source_health_attestation(
            store_dir, run_id=run_id, sources_reviewed=["evidence.sec_edgar_live"],
            reviewed_by="op", reviewed_at=_NOW)
        with open(OperatorAttestationStore(store_dir).path, encoding="utf-8") as fh:
            blob = fh.read().lower()
        for token in ("api_key", "password", "secret", "\"score\"", "\"rank\"", "broker", "order"):
            self.assertNotIn(token, blob)

    def test_deterministic_content_id(self):
        self.assertEqual(
            oa.attestation_id_for("live-source-health", subject="r|s", reviewed_by="op",
                                  reviewed_at=_NOW),
            oa.attestation_id_for("live-source-health", subject="r|s", reviewed_by="op",
                                  reviewed_at=_NOW))


# --------------------------------------------------------------------------- #
# 3. verify_live_source_health -- pass ONLY on real, confirmed, fresh evidence   #
# --------------------------------------------------------------------------- #
class VerifyLiveSourceHealthTests(unittest.TestCase):
    def test_real_run_plus_attestation_passes(self):
        store_dir = tempfile.mkdtemp()
        run_id = _seed_live_run(store_dir, now="2026-06-29T14:00:00Z", run_id="live-ok")
        record_live_source_health_attestation(
            store_dir, run_id=run_id,
            sources_reviewed=["evidence.sec_edgar_live", "evidence.fmp_live"],
            reviewed_by="op", reviewed_at=_NOW)
        result = verify_live_source_health(store_dir, now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.PASS)
        self.assertTrue(result.evidence_path)

    def test_no_attestation_is_manual(self):
        result = verify_live_source_health(tempfile.mkdtemp(), now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)

    def test_missing_run_stays_blocking_even_with_an_attestation(self):
        # A bare attestation naming a non-existent run (written directly, bypassing the producer)
        # must NEVER clear -- the verifier re-reads the store and finds no such run.
        store_dir = tempfile.mkdtemp()
        OperatorAttestationStore(store_dir).record(LiveSourceHealthAttestation(
            attestation_id="attest:live-source-health:fake", run_id="NO-SUCH-RUN",
            sources_reviewed=("evidence.sec_edgar_live",), reviewed_by="op", reviewed_at=_NOW))
        result = verify_live_source_health(store_dir, now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)
        self.assertIn("not a persisted run", result.details[0].lower())

    def test_unhealthy_unbacked_source_stays_blocking(self):
        # A run that only ran SEC; attesting FMP healthy is unbacked by real persisted evidence.
        store_dir = tempfile.mkdtemp()
        run_id = _seed_live_run(store_dir, now="2026-06-29T14:00:00Z", run_id="sec-only",
                                adapters=[_sec_adapter()])
        record_live_source_health_attestation(
            store_dir, run_id=run_id, sources_reviewed=["evidence.fmp_live"],
            reviewed_by="op", reviewed_at=_NOW)
        result = verify_live_source_health(store_dir, now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)
        self.assertIn("not backed", result.details[0].lower())

    def test_stale_run_stays_blocking(self):
        store_dir = tempfile.mkdtemp()
        run_id = _seed_live_run(store_dir, now="2026-06-29T14:00:00Z", run_id="live-stale")
        record_live_source_health_attestation(
            store_dir, run_id=run_id, sources_reviewed=["evidence.sec_edgar_live"],
            reviewed_by="op", reviewed_at=_NOW)
        result = verify_live_source_health(store_dir, now="2026-08-01T00:00:00Z")  # weeks later
        self.assertEqual(result.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)
        self.assertIn("stale", result.details[0].lower())


# --------------------------------------------------------------------------- #
# 4. verify_shadow_validation -- pass ONLY on a genuine, real window             #
# --------------------------------------------------------------------------- #
class VerifyShadowValidationTests(unittest.TestCase):
    def test_genuine_window_passes(self):
        store_dir = tempfile.mkdtemp()
        rids = _seed_window(store_dir, _THREE_DAYS)
        record_shadow_validation_attestation(
            store_dir, window_run_ids=rids, reviewed_by="op", reviewed_at=_NOW)
        result = verify_shadow_validation(store_dir, now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.PASS)

    def test_no_attestation_is_manual(self):
        result = verify_shadow_validation(tempfile.mkdtemp(), now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)

    def test_too_few_runs_stays_blocking(self):
        store_dir = tempfile.mkdtemp()
        rid = _seed_live_run(store_dir, now="2026-06-27T00:00:00Z", run_id="one")
        record_shadow_validation_attestation(
            store_dir, window_run_ids=[rid], reviewed_by="op", reviewed_at=_NOW)
        result = verify_shadow_validation(store_dir, now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)
        self.assertIn("distinct persisted run", result.details[0].lower())

    def test_single_day_window_stays_blocking(self):
        store_dir = tempfile.mkdtemp()
        rids = _seed_window(
            store_dir, ("2026-06-27T01:00:00Z", "2026-06-27T02:00:00Z", "2026-06-27T03:00:00Z"))
        record_shadow_validation_attestation(
            store_dir, window_run_ids=rids, reviewed_by="op", reviewed_at=_NOW)
        result = verify_shadow_validation(store_dir, now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)
        self.assertIn("calendar day", result.details[0].lower())

    def test_missing_referenced_run_stays_blocking(self):
        # A bare attestation naming runs that were never persisted must NEVER clear.
        store_dir = tempfile.mkdtemp()
        OperatorAttestationStore(store_dir).record(ShadowValidationAttestation(
            attestation_id="attest:shadow-validation:fake",
            window_run_ids=("a", "b", "c"), reviewed_by="op", reviewed_at=_NOW))
        result = verify_shadow_validation(store_dir, now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)
        self.assertIn("not persisted runs", result.details[0].lower())


# --------------------------------------------------------------------------- #
# 5. Producers refuse an unreal run (validation-refuses-ungrounded)             #
# --------------------------------------------------------------------------- #
class ProducerRefusalTests(unittest.TestCase):
    def test_live_producer_refuses_nonexistent_run_and_writes_nothing(self):
        store_dir = tempfile.mkdtemp()
        with self.assertRaises(ValueError):
            record_live_source_health_attestation(
                store_dir, run_id="NOPE", sources_reviewed=["evidence.sec_edgar_live"],
                reviewed_by="op", reviewed_at=_NOW)
        self.assertEqual(OperatorAttestationStore(store_dir).read_records(), ())

    def test_shadow_producer_refuses_nonexistent_run(self):
        store_dir = tempfile.mkdtemp()
        _seed_live_run(store_dir, now=_NOW, run_id="real-1")
        with self.assertRaises(ValueError):
            record_shadow_validation_attestation(
                store_dir, window_run_ids=["real-1", "ghost-2"], reviewed_by="op",
                reviewed_at=_NOW)
        self.assertEqual(OperatorAttestationStore(store_dir).read_records(), ())


# --------------------------------------------------------------------------- #
# 6. prod-check wiring -- byte-identical without attestations; clears with both  #
# --------------------------------------------------------------------------- #
class ProdCheckWiringTests(unittest.TestCase):
    _DEFAULT_MANUAL_NOTE = "cannot be machine-verified OFFLINE -- manual review required"

    def test_no_attestations_is_byte_identical_and_refuses_production(self):
        from cosmosiq_ops.prod_check import run_prod_check
        with tempfile.TemporaryDirectory() as work:
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        self.assertFalse(report.production_mode_allowed)
        self.assertEqual(report.verdict, "shadow_24x7_only")
        for item_id in ("live_source_health", "operator_shadow_validation"):
            item = report.activation.item(item_id)
            self.assertEqual(item.status, ChecklistStatus.MANUAL_REVIEW_REQUIRED)
            self.assertEqual(item.notes, self._DEFAULT_MANUAL_NOTE,
                             "the item note must be byte-identical to the pre-PL-2 default")
            self.assertIn(item_id, report.manual_review_items)

    def test_both_attested_plus_signoff_and_approval_reaches_production_allowed(self):
        from cosmosiq_ops.prod_check import run_prod_check
        from cosmosiq_service.activation import CheckResult, OperatorApproval
        from cosmosiq_service.service import ServiceMode
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            os.makedirs(store)
            rids = _seed_window(store, _THREE_DAYS)
            record_live_source_health_attestation(
                store, run_id=rids[-1],
                sources_reviewed=["evidence.sec_edgar_live", "evidence.fmp_live"],
                reviewed_by="op", reviewed_at=_NOW)
            record_shadow_validation_attestation(
                store, window_run_ids=rids, reviewed_by="op", reviewed_at=_NOW)
            approval = OperatorApproval(
                approved_by="op", approved_at=_NOW,
                target_mode=ServiceMode.PRODUCTION_24X7.value)
            report = run_prod_check(
                work, _REPO_ROOT, now=_NOW, quick=True, operator_approval=approval,
                extra_checks={"operator_signoff": CheckResult(
                    "operator_signoff", "pass", ("operator signoff present (test)",))})
        self.assertTrue(report.production_mode_allowed)
        self.assertEqual(report.verdict, "production_24x7_approved")
        self.assertEqual(report.activation.item("live_source_health").status, ChecklistStatus.PASS)
        self.assertEqual(
            report.activation.item("operator_shadow_validation").status, ChecklistStatus.PASS)

    def test_bad_attestation_alone_never_clears_prod_check(self):
        # An attestation whose run does not exist is present but the verifier refuses it -- the
        # item stays blocking and production is still refused.
        from cosmosiq_ops.prod_check import run_prod_check
        with tempfile.TemporaryDirectory() as work:
            store = os.path.join(work, "store")
            os.makedirs(store)
            OperatorAttestationStore(store).record(LiveSourceHealthAttestation(
                attestation_id="attest:live-source-health:bogus", run_id="NOPE",
                sources_reviewed=("evidence.sec_edgar_live",), reviewed_by="op", reviewed_at=_NOW))
            report = run_prod_check(work, _REPO_ROOT, now=_NOW, quick=True)
        self.assertFalse(report.production_mode_allowed)
        self.assertEqual(
            report.activation.item("live_source_health").status,
            ChecklistStatus.MANUAL_REVIEW_REQUIRED)


# --------------------------------------------------------------------------- #
# 7. CLI -- records; refuses a bad run reference (non-zero, nothing written)     #
# --------------------------------------------------------------------------- #
class CliTests(unittest.TestCase):
    def _run_cli(self, argv):
        from cosmosiq_pulse.__main__ import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_attest_live_source_refuses_nonexistent_run(self):
        store_dir = tempfile.mkdtemp()
        code, out = self._run_cli([
            "attest-live-source", "--store-dir", store_dir, "--run-id", "GHOST",
            "--sources", "evidence.sec_edgar_live", "--reviewed-by", "op", "--now", _NOW])
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertEqual(OperatorAttestationStore(store_dir).read_records(), ())

    def test_attest_live_source_records_a_real_run(self):
        store_dir = tempfile.mkdtemp()
        run_id = _seed_live_run(store_dir, now=_NOW, run_id="cli-live")
        code, out = self._run_cli([
            "attest-live-source", "--store-dir", store_dir, "--run-id", run_id,
            "--sources", "evidence.sec_edgar_live,evidence.fmp_live",
            "--reviewed-by", "op", "--now", _NOW])
        self.assertEqual(code, 0)
        self.assertIn("recorded attestation_id=", out)
        self.assertIsNotNone(latest_live_source_health_attestation(store_dir))

    def test_attest_shadow_validation_records_and_status_surface(self):
        store_dir = tempfile.mkdtemp()
        rids = _seed_window(store_dir, _THREE_DAYS)
        code, _out = self._run_cli([
            "attest-shadow-validation", "--store-dir", store_dir,
            "--run-ids", ",".join(rids), "--reviewed-by", "op", "--now", _NOW])
        self.assertEqual(code, 0)
        # also record a live attestation so the read-only status surface shows both cleared
        record_live_source_health_attestation(
            store_dir, run_id=rids[-1],
            sources_reviewed=["evidence.sec_edgar_live", "evidence.fmp_live"],
            reviewed_by="op", reviewed_at=_NOW)
        live, shadow = attestation_activation_status(store_dir, now=_NOW)
        self.assertEqual(live.status, ChecklistStatus.PASS)
        self.assertEqual(shadow.status, ChecklistStatus.PASS)


if __name__ == "__main__":
    unittest.main()
