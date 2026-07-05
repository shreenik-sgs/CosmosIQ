"""IMPLEMENTATION-020B -- the SEC EDGAR live filings adapter (OFFLINE, mocked transport).

The FIRST production LIVE source adapter. Per SOURCE_ADAPTER_PRODUCTION_CONTRACT_013: it emits
RealityEvents ONLY; an SEC filing metadata fact is canonical + verified_fact (the filing-fact),
assigned immediately per record and never promoted (a convenience/FMP datum can never outrank
canonical); credentials are env-var NAMES + presence labels only (a missing SEC_USER_AGENT is a
visible gap, never a crash / leak); an HTTP 429/403 (or rate-limit-shaped error) is captured as
rate_limited and honoured (never retried in-pulse); a timeout/other error is source_unavailable
and OTHER tickers continue; a malformed payload is a parse_error; an unknown ticker is a NAMED
gap (CIK never guessed). NO ambient network: every payload arrives through the injected mock
transport (the real transport is built lazily and NEVER exercised here); the whole suite runs
under a socket kill-switch. A failed fetch yields a GAP, never a fixture/demo fallback -- zero
fabricated events. The default run_pulse path stays byte-identical.
"""
import ast
import json
import os
import re
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh.adapters import (
    SEC_EDGAR_LIVE_ADAPTER_ID,
    SEC_EDGAR_LIVE_DESCRIPTOR,
    SEC_EDGAR_LIVE_DISCIPLINES,
    SEC_EDGAR_LIVE_EVENT_TYPES,
    SEC_EDGAR_LIVE_RISK_EVENT_TYPES,
    SEC_EDGAR_LIVE_TRANSPORT_KEYS,
    SecEdgarLiveAdapter,
    SourceAdapterResult,
    source_health_from_result,
)
from reality_mesh.health import SourceHealthRecord
from reality_mesh.labels import authority_rank
from reality_mesh.models import RealityEvent
from reality_mesh.pulse import run_pulse
from reality_mesh.pulse_persistence import persist_and_summarize
from reality_mesh.sensors.news_filings import NewsFilingsAgent, claim_status_of

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PY = os.path.join(
    _HERE, "..", "src", "reality_mesh", "adapters", "sec_edgar_live.py")
_FIXTURE_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "sec_edgar_live")

_WATCHLIST = "IREN,AAOI"
_THEMES = "physical-ai,robotics"
_NOW = "2026-07-05T14:00:00Z"

_CIK_IREN = "0001878848"
_CIK_AAOI = "0000123456"
_CIK_TO_FIXTURE = {
    _CIK_IREN: "sec_submissions_iren_live.json",
    _CIK_AAOI: "sec_submissions_aaoi_live.json",
}

# A stand-in credential VALUE used ONLY to prove it never leaks (rejected at the constructor;
# must never appear in any event / result / repr / error).
_FAKE_CREDENTIAL = "sk-FAKEVALUE-hunter2-000"

# The socket kill-switch stays armed for the WHOLE module (every path must be offline).
_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: the SEC EDGAR live adapter must run fully offline on the mock "
            "transport -- the real network path is never exercised in tests")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def _company_tickers():
    return _load("company_tickers.json")


def _submissions(cik):
    name = _CIK_TO_FIXTURE.get(str(cik).zfill(10))
    if name is None:
        raise RuntimeError("no submissions fixture for CIK {0}".format(cik))
    return _load(name)


def _mock_transport(**overrides):
    """The injected per-endpoint MOCK bundle (fully offline; fixture-backed)."""
    bundle = {"company_tickers": _company_tickers, "submissions": _submissions}
    bundle.update(overrides)
    return bundle


def _raise_429(cik):
    raise RuntimeError("HTTP 429 Too Many Requests (SEC fair-access rate exceeded)")


def _raise_403(cik):
    raise RuntimeError("HTTP 403 Forbidden (declare a descriptive User-Agent)")


def _raise_timeout(cik):
    raise RuntimeError("connection timed out / reset by peer (simulated source failure)")


def _submissions_iren_fails(err):
    def _fetch(cik):
        if str(cik).zfill(10) == _CIK_IREN:
            return err(cik)
        return _submissions(cik)
    return _fetch


def _blob(result):
    return " ".join(result.warnings + result.errors + result.data_gaps
                    + result.raw_payload_refs + (result.run_id,))


# --------------------------------------------------------------------------- #
# 1. Descriptor: the contract declaration                                       #
# --------------------------------------------------------------------------- #
class DescriptorTests(unittest.TestCase):
    def test_identity_authority_and_disciplines(self):
        d = SEC_EDGAR_LIVE_DESCRIPTOR
        self.assertEqual(d.adapter_id, "evidence.sec_edgar_live")
        self.assertEqual(SEC_EDGAR_LIVE_ADAPTER_ID, "evidence.sec_edgar_live")
        self.assertEqual(d.source_authority, "canonical")
        self.assertEqual(d.source_type, "filing")
        self.assertEqual(SEC_EDGAR_LIVE_DISCIPLINES, ("news_filings",))
        self.assertEqual(SecEdgarLiveAdapter(transport=_mock_transport()).covered_disciplines,
                         ("news_filings",))

    def test_network_required_and_transport_keys(self):
        self.assertTrue(SEC_EDGAR_LIVE_DESCRIPTOR.network_required)
        self.assertEqual(SEC_EDGAR_LIVE_TRANSPORT_KEYS, ("company_tickers", "submissions"))

    def test_credential_requirements_are_env_var_names_only(self):
        creds = SEC_EDGAR_LIVE_DESCRIPTOR.credential_requirements
        self.assertEqual(creds, ("SEC_USER_AGENT",))
        for name in creds:
            self.assertRegex(name, r"^[A-Z][A-Z0-9_]*$")     # a NAME, never a value

    def test_all_four_failure_modes_declared(self):
        self.assertEqual(set(SEC_EDGAR_LIVE_DESCRIPTOR.failure_modes),
                         {"credentials_missing", "rate_limited", "source_unavailable",
                          "parse_error"})

    def test_rate_limit_policy_documents_429_403_and_no_retry(self):
        policy = SEC_EDGAR_LIVE_DESCRIPTOR.rate_limit_policy.lower()
        self.assertIn("429", policy)
        self.assertIn("403", policy)
        self.assertIn("never retried", policy)

    def test_claim_status_rules_state_the_authority_ladder(self):
        rules = " ".join(SEC_EDGAR_LIVE_DESCRIPTOR.claim_status_rules).lower()
        self.assertIn("canonical", rules)
        self.assertIn("verified_fact", rules)
        self.assertIn("never auto-creates an investment conclusion", rules)
        self.assertIn("never outrank", rules)

    def test_minimum_useful_forms_are_covered_by_outputs(self):
        # every risk-sensitive event type is a declared output
        for etype in SEC_EDGAR_LIVE_RISK_EVENT_TYPES:
            self.assertIn(etype, SEC_EDGAR_LIVE_EVENT_TYPES)
        self.assertEqual(SEC_EDGAR_LIVE_DESCRIPTOR.outputs, SEC_EDGAR_LIVE_EVENT_TYPES)


# --------------------------------------------------------------------------- #
# 2. Successful live-style fetch -> canonical filing-fact events w/ provenance   #
# --------------------------------------------------------------------------- #
class SuccessfulFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(), sec_user_agent_present=True)
        cls.events, cls.result = cls.adapter.fetch_checked(
            watchlist=("IREN",), themes=("physical-ai",), now=_NOW)

    def test_reality_events_only_with_full_provenance(self):
        self.assertTrue(self.events)
        self.assertEqual(self.result.status, "success")
        self.assertEqual(self.result.events_created, len(self.events))
        for ev in self.events:
            self.assertIsInstance(ev, RealityEvent)
            self.assertEqual(ev.source_authority, "canonical")
            self.assertEqual(ev.claim_status, "verified_fact")
            self.assertEqual(ev.discipline, "news_filings")
            self.assertIn("#sha256=", ev.raw_payload_ref)   # content-derived raw ref
            self.assertTrue(ev.evidence_refs or ev.source_refs)
            self.assertIn(ev.freshness_label,
                          {"fresh", "recent", "aging", "stale", "expired", "unknown"})

    def test_event_carries_accession_url_form_date_and_cik_in_refs(self):
        s3 = next(e for e in self.events
                  if e.event_type == "sec_s-3_shelf_registration")
        refs = " ".join(s3.source_refs + s3.evidence_refs + s3.text_excerpt_refs)
        self.assertIn("0001878848-26-000050", refs)         # accession number
        self.assertIn("https://www.sec.gov/Archives/edgar/data/1878848/", refs)  # doc URL
        self.assertIn("sec:cik/0001878848", refs)           # CIK
        self.assertIn("S-3", refs)                          # form type
        self.assertEqual(s3.timestamp, "2026-06-30")        # filing date is the timestamp
        self.assertEqual(s3.freshness_label, "fresh")       # 5 days before now

    def test_source_health_record_is_produced(self):
        record = source_health_from_result(self.result, now=_NOW)
        self.assertIsInstance(record, SourceHealthRecord)
        self.assertEqual(record.source_id, SEC_EDGAR_LIVE_ADAPTER_ID)
        self.assertEqual(record.last_status, "healthy")
        self.assertEqual(record.last_success_at, _NOW)

    def test_risk_sensitive_events_are_visible_and_labelled(self):
        by_type = {e.event_type: e for e in self.events}
        # dilution risk (S-3) is visible + labelled
        self.assertIn("sec_s-3_shelf_registration", by_type)
        self.assertIn("dilution", by_type["sec_s-3_shelf_registration"].observed_fact.lower())
        # 8-K Item 1.01 material definitive agreement
        self.assertIn("sec_8-k_material_agreement", by_type)
        self.assertIn("agreement", by_type["sec_8-k_material_agreement"].observed_fact.lower())
        # 8-K Item 2.02 guidance-change risk
        self.assertIn("sec_8-k_results_of_operations", by_type)
        # insider Form 4
        self.assertIn("sec_form_4_insider_transaction", by_type)
        self.assertIn("insider",
                      by_type["sec_form_4_insider_transaction"].observed_fact.lower())

    def test_offering_size_is_a_gap_never_fabricated(self):
        s3 = next(e for e in self.events
                  if e.event_type == "sec_s-3_shelf_registration")
        self.assertEqual(s3.numeric_values, ())                 # nothing fabricated
        self.assertTrue(any("offering size" in g for g in s3.data_gaps))
        self.assertTrue(any("metadata-first" in g for g in s3.data_gaps))

    def test_non_catalyst_forms_are_not_emitted(self):
        # the fixture 13F-HR is NOT a declared output of this adapter
        self.assertFalse(any("13f" in e.event_type.lower() for e in self.events))
        # but the minimum-useful forms ARE present
        types = {e.event_type for e in self.events}
        self.assertIn("sec_10-k_annual_report", types)
        self.assertIn("sec_def_14a_proxy_statement", types)
        self.assertIn("sec_13d_activist_position", types)

    def test_deterministic_ids_and_run_id(self):
        events2, result2 = SecEdgarLiveAdapter(
            transport=_mock_transport(), sec_user_agent_present=True).fetch_checked(
                watchlist=("IREN",), themes=("physical-ai",), now=_NOW)
        self.assertEqual([e.event_id for e in self.events],
                         [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        self.assertTrue(self.result.run_id.startswith(
            "adapterrun.evidence.sec_edgar_live."))
        self.assertTrue(all(e.event_id.startswith("seclive.") for e in self.events))


# --------------------------------------------------------------------------- #
# 3. CIK resolution: configured map, company_tickers lookup, unknown ticker     #
# --------------------------------------------------------------------------- #
class CikResolutionTests(unittest.TestCase):
    def test_cik_from_configured_map_without_company_tickers_transport(self):
        adapter = SecEdgarLiveAdapter(
            transport={"submissions": _submissions},      # NO company_tickers wired
            sec_user_agent_present=True, cik_map={"IREN": "1878848"})
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.status, "success")
        self.assertTrue(any(e.source_id == "sec.edgar" for e in events))

    def test_unknown_ticker_is_a_named_gap_never_guessed(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(), sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("ZZZZ",), now=_NOW)
        self.assertEqual(events, ())
        self.assertTrue(any("unknown ticker ZZZZ" in g and "never guessed" in g
                            for g in result.data_gaps))

    def test_no_cik_map_and_no_company_tickers_is_a_gap(self):
        adapter = SecEdgarLiveAdapter(
            transport={"submissions": _submissions}, sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(events, ())
        self.assertTrue(any("cannot resolve CIK" in g for g in result.data_gaps))


# --------------------------------------------------------------------------- #
# 4. Credentials: presence labels only; missing -> visible gap, never a leak     #
# --------------------------------------------------------------------------- #
class CredentialTests(unittest.TestCase):
    def test_missing_sec_user_agent_skips_with_gap_no_crash(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(), sec_user_agent_present=False)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.source_health, "credentials_missing")
        self.assertEqual(result.credentials_status, "missing")   # a LABEL, never a value
        self.assertTrue(any("SEC_USER_AGENT" in g for g in result.data_gaps))
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "credentials_missing")
        self.assertEqual(record.credentials_status, "missing")

    def test_credential_value_passed_as_flag_is_rejected_and_never_echoed(self):
        with self.assertRaises(ValueError) as ctx:
            SecEdgarLiveAdapter(transport=_mock_transport(),
                                sec_user_agent_present=_FAKE_CREDENTIAL)
        message = str(ctx.exception)
        self.assertNotIn(_FAKE_CREDENTIAL, message)              # NEVER echoed back
        self.assertIn("PRESENCE flag", message)

    def test_no_credential_value_in_any_event_result_or_repr(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(), sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.credentials_status, "present")   # a label only
        surfaces = [repr(adapter), repr(result), _blob(result)]
        surfaces.extend(repr(e) for e in events)
        for text in surfaces:
            low = text.lower()
            self.assertNotIn(_FAKE_CREDENTIAL.lower(), low)
            for bad in ("api_key=", "apikey=", "password", "secret_key", "sec_user_agent="):
                self.assertNotIn(bad, low)
            self.assertNotRegex(low, r"\bsk-[a-z0-9]{6}")


# --------------------------------------------------------------------------- #
# 5. Failure capture: rate limit (429/403) / timeout / malformed -> gaps         #
# --------------------------------------------------------------------------- #
class FailureCaptureTests(unittest.TestCase):
    def test_http_429_is_rate_limited_and_other_tickers_continue(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(submissions=_submissions_iren_fails(_raise_429)),
            sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(result.status, "partial")          # NOT a crash, NOT empty
        self.assertEqual(result.rate_limit_status, "throttled")
        self.assertEqual(result.source_health, "rate_limited")
        self.assertTrue(any(e.startswith("rate_limited: submissions IREN")
                            for e in result.errors))
        self.assertTrue(any("not retried" in g.lower() for g in result.data_gaps))
        # AAOI still delivered; IREN did not
        self.assertTrue(any(e.affected_companies == ("AAOI",) for e in events))
        self.assertFalse(any(e.affected_companies == ("IREN",) for e in events))

    def test_http_403_is_honoured_as_rate_limited(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(submissions=_raise_403),
            sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.rate_limit_status, "throttled")
        self.assertEqual(result.source_health, "rate_limited")

    def test_timeout_is_a_data_gap_partial_others_continue(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(submissions=_submissions_iren_fails(_raise_timeout)),
            sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(e.startswith("source_unavailable: submissions IREN")
                            for e in result.errors))
        self.assertTrue(any("IREN" in g and "unavailable" in g for g in result.data_gaps))
        self.assertTrue(any(e.affected_companies == ("AAOI",) for e in events))

    def test_malformed_submissions_is_a_parse_error_gap(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(submissions=lambda cik: {"filings": {}}),
            sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(events, ())
        self.assertTrue(any(e.startswith("parse_error: submissions") for e in result.errors))
        self.assertTrue(any("parse_error" in g and "nothing fabricated" in g
                            for g in result.data_gaps))

    def test_empty_watchlist_is_a_skipped_result_with_gap(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(), sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=(), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertTrue(any("empty watchlist" in g for g in result.data_gaps))


# --------------------------------------------------------------------------- #
# 6. NO fixture fallback in real mode: a failed fetch is a gap, not fixture data #
# --------------------------------------------------------------------------- #
class NoFixtureFallbackTests(unittest.TestCase):
    def test_all_fetches_failing_yields_zero_fabricated_events(self):
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(submissions=_raise_timeout),
            sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(len(events), 0)                    # ZERO fabricated events
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(result.data_gaps)
        self.assertFalse(any("fixture" in r for r in result.raw_payload_refs))


# --------------------------------------------------------------------------- #
# 7. No network on import; offline; no score/rank def names                      #
# --------------------------------------------------------------------------- #
class NoAmbientNetworkTests(unittest.TestCase):
    def test_module_imports_no_network_module_anywhere(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx",
                  "websocket", "websockets", "ftplib", "smtplib", "telnetlib")
        # module level AND inside every function: the real transport is DELEGATED to
        # evidence_ingestion.live_transport, so this module needs no network import at all.
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for root in banned:
                    self.assertFalse(
                        name == root or name.startswith(root + "."),
                        "network import {0!r} in sec_edgar_live.py".format(name))

    def test_no_score_rank_or_rating_function_defs(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                 "banned fn name {0!r}".format(node.name))

    def test_real_transport_is_function_local(self):
        # the default-real transport is built lazily inside a method, never at import
        with open(_MODULE_PY, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("def _default_transport", source)
        self.assertIn("from evidence_ingestion.live_transport import sec_live_transport", source)


# --------------------------------------------------------------------------- #
# 8. End to end: mocked live adapter -> run_pulse -> news_filings -> fusion       #
# --------------------------------------------------------------------------- #
class LivePulseEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SecEdgarLiveAdapter(
                              transport=_mock_transport(), sec_user_agent_present=True),))

    def test_news_filings_findings_come_from_live_events_only(self):
        nf = [f for f in self.r.findings if f.discipline == "news_filings"]
        self.assertTrue(nf)
        for f in nf:
            for ev_id in f.input_events:
                self.assertTrue(ev_id.startswith("seclive."),
                                "fixture event {0!r} leaked into news_filings".format(ev_id))

    def test_filing_fact_findings_are_canonical_verified(self):
        dil = [f for f in self.r.findings if f.finding_type == "dilution_risk"]
        self.assertTrue(dil)
        for f in dil:
            self.assertEqual(f.source_authority_summary, "canonical")
            self.assertEqual(claim_status_of(f), "verified_fact")

    def test_fusion_produced_signals_from_the_live_findings(self):
        self.assertTrue(self.r.signals)
        self.assertTrue(any(
            src.startswith("finding.news_filings.")
            for s in self.r.signals for src in s.source_findings))

    def test_adapter_result_is_on_the_pulse_and_healthy(self):
        self.assertEqual(len(self.r.adapter_results), 1)
        result = self.r.adapter_results[0]
        self.assertIsInstance(result, SourceAdapterResult)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.adapter_id, SEC_EDGAR_LIVE_ADAPTER_ID)
        self.assertIn("IREN", self.r.covered_companies)
        self.assertIn("AAOI", self.r.covered_companies)
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "healthy")

    def test_uncovered_disciplines_still_come_from_fixtures(self):
        self.assertTrue(any(f.discipline == "market_regime" for f in self.r.findings))
        self.assertTrue(any(f.discipline == "narrative" for f in self.r.findings))

    def test_pulse_with_the_live_adapter_is_deterministic(self):
        again = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SecEdgarLiveAdapter(
                              transport=_mock_transport(), sec_user_agent_present=True),))
        self.assertEqual(self.r, again)


# --------------------------------------------------------------------------- #
# 9. Replay compatibility: persist + verification replay deterministic_match     #
# --------------------------------------------------------------------------- #
class ReplayCompatibilityTests(unittest.TestCase):
    def test_persisted_live_pulse_replays_deterministically(self):
        pulse = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SecEdgarLiveAdapter(
                              transport=_mock_transport(), sec_user_agent_present=True),))
        with tempfile.TemporaryDirectory() as store_dir:
            pulse_run, replay, panel = persist_and_summarize(
                pulse, store_dir=store_dir, run_id="RUN-SECLIVE-020B", now=_NOW)
            self.assertTrue(replay.deterministic_match)
            # the persisted events round-trip: the live filing events are in the store
            self.assertTrue(pulse.events_loaded > 0)


# --------------------------------------------------------------------------- #
# 10. Regressions: authority ladder + no verified-fact laundering held           #
# --------------------------------------------------------------------------- #
class RegressionTests(unittest.TestCase):
    def test_fmp_provider_can_never_outrank_sec(self):
        # canonical (SEC) strictly outranks convenience (FMP / provider)
        self.assertGreater(authority_rank("canonical"), authority_rank("convenience"))
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(), sec_user_agent_present=True)
        events, _ = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertTrue(all(e.source_authority == "canonical" for e in events))

    def test_social_x_event_can_never_be_a_verified_fact(self):
        with self.assertRaises(ValueError):
            RealityEvent(event_id="soc.1", source_id="x", source_type="x_social",
                         source_authority="rumor", claim_status="verified_fact",
                         raw_payload_ref="raw:x", discipline="narrative",
                         event_type="tweet", evidence_refs=("u",))

    def test_company_press_release_can_never_become_a_verified_fact(self):
        pr = RealityEvent(
            event_id="pr.1", source_id="fmp.news", source_type="fmp_press_release",
            source_authority="convenience", claim_status="company_claim",
            raw_payload_ref="raw:pr", discipline="news_filings", event_type="press_release",
            affected_companies=("IREN",),
            observed_fact="press release: IREN announces a major customer win",
            evidence_refs=("u",), freshness_label="recent")
        findings = NewsFilingsAgent().run(None, (pr,))
        self.assertTrue(findings)
        for f in findings:
            self.assertNotEqual(claim_status_of(f), "verified_fact")
            self.assertNotEqual(f.source_authority_summary, "canonical")

    def test_fixture_data_cannot_be_emitted_in_a_real_mode_fetch(self):
        # a failed real-mode fetch yields a gap -- never a silent fixture/demo backfill
        adapter = SecEdgarLiveAdapter(
            transport=_mock_transport(submissions=_raise_timeout),
            sec_user_agent_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(events, ())
        self.assertNotEqual(result.status, "success")


# --------------------------------------------------------------------------- #
# 11. Default path byte-identical; opt-in only                                   #
# --------------------------------------------------------------------------- #
class DefaultPathUnchangedTests(unittest.TestCase):
    def test_default_pulse_stays_byte_identical(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        explicit_none = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                                  data_dir=None, adapters=None)
        self.assertEqual(base, explicit_none)               # every field, byte for byte
        self.assertEqual(base.adapter_results, ())
        # the default path keeps consuming the bundled news_filings fixtures (no seclive)
        nf = [f for f in base.findings if f.discipline == "news_filings"]
        self.assertTrue(nf)
        self.assertTrue(all(not ev.startswith("seclive.")
                            for f in nf for ev in f.input_events))


if __name__ == "__main__":
    unittest.main()
