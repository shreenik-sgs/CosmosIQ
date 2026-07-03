"""IMPLEMENTATION-014B — the SEC/FMP evidence source adapter (OFFLINE, mocked transports).

Per SOURCE_ADAPTER_PRODUCTION_CONTRACT_013: the adapter emits RealityEvents ONLY; source
authority is assigned immediately per the ladder (SEC filing fact -> canonical +
verified_fact; press release / company text -> company_claim; FMP -> convenience; never
promoted); credentials are env-var NAMES + presence labels only (a missing credential is a
visible gap + degraded result, never a crash or a leak); a raising transport is captured as
rate_limited / source_unavailable and other tickers continue; a malformed payload is a
parse_error gap. NO ambient network: every payload arrives through injected mock transports
(the 010D bundle shape); with NO transports the network_required refusal stands. The whole
suite is offline; the default run_pulse path stays byte-identical.
"""
import ast
import json
import os
import re
import socket
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh.adapters import (
    FINANCIAL_INFLECTION_CONSUMER_GAP,
    FMP_TRANSPORT_KEYS,
    SEC_FMP_EVIDENCE_ADAPTER_ID,
    SEC_FMP_EVIDENCE_DESCRIPTOR,
    SEC_FMP_EVIDENCE_DISCIPLINES,
    SEC_TRANSPORT_KEYS,
    SecFmpEvidenceAdapter,
    SourceAdapterResult,
    source_health_from_result,
)
from reality_mesh.models import RealityEvent
from reality_mesh.pulse import run_pulse
from reality_mesh.sensors.news_filings import claim_status_of

_HERE = os.path.dirname(os.path.abspath(__file__))
_EVIDENCE_SOURCES_PY = os.path.join(
    _HERE, "..", "src", "reality_mesh", "adapters", "evidence_sources.py")
_FIXTURE_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "evidence_sources")

_WATCHLIST = "IREN,AAOI"
_THEMES = "physical-ai,robotics"
_NOW = "2026-07-01T14:00:00Z"

# A stand-in credential VALUE used ONLY to prove it never leaks anywhere (it must be
# rejected at the constructor and must never appear in any event / result / repr / error).
_FAKE_CREDENTIAL = "sk-FAKEVALUE-hunter2-000"


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def _mock_transports(**overrides):
    """The 010D-shaped per-payload MOCK bundle (fully offline; fixture-backed)."""
    bundle = {
        "sec_submissions": lambda tk: _load("sec_submissions_iren.json"),
        "fmp_news": lambda tk: _load("fmp_news_iren.json"),
        "fmp_profile": lambda tk: _load("fmp_profile_iren.json"),
        "fmp_income_statement": lambda tk: _load("fmp_income_statement_iren.json"),
    }
    bundle.update(overrides)
    return bundle


def _raise_rate_limit(_tk):
    raise RuntimeError("HTTP 429 Too Many Requests (per-minute quota exceeded)")


def _raise_unavailable(_tk):
    raise RuntimeError("connection reset by peer (simulated source failure)")


def _blob(result):
    return " ".join(result.warnings + result.errors + result.data_gaps
                    + result.raw_payload_refs + (result.run_id,))


# --------------------------------------------------------------------------- #
# 1. Descriptor: the contract declaration                                       #
# --------------------------------------------------------------------------- #
class DescriptorTests(unittest.TestCase):
    def test_identity_and_disciplines(self):
        d = SEC_FMP_EVIDENCE_DESCRIPTOR
        self.assertEqual(d.adapter_id, "evidence.sec_fmp")
        self.assertEqual(SEC_FMP_EVIDENCE_ADAPTER_ID, "evidence.sec_fmp")
        self.assertEqual(SEC_FMP_EVIDENCE_DISCIPLINES,
                         ("news_filings", "financial_inflection"))
        self.assertEqual(SecFmpEvidenceAdapter().covered_disciplines,
                         SEC_FMP_EVIDENCE_DISCIPLINES)

    def test_network_required_and_transport_keys(self):
        self.assertTrue(SEC_FMP_EVIDENCE_DESCRIPTOR.network_required)
        self.assertEqual(SEC_TRANSPORT_KEYS, ("sec_submissions",))
        self.assertEqual(FMP_TRANSPORT_KEYS,
                         ("fmp_news", "fmp_profile", "fmp_income_statement"))

    def test_credential_requirements_are_env_var_names_only(self):
        creds = SEC_FMP_EVIDENCE_DESCRIPTOR.credential_requirements
        self.assertEqual(creds, ("SEC_USER_AGENT", "FMP_API_KEY"))
        for name in creds:
            self.assertRegex(name, r"^[A-Z][A-Z0-9_]*$")   # a NAME, never a value

    def test_all_four_failure_modes_declared(self):
        self.assertEqual(set(SEC_FMP_EVIDENCE_DESCRIPTOR.failure_modes),
                         {"credentials_missing", "rate_limited", "source_unavailable",
                          "parse_error"})

    def test_rate_limit_policy_documented(self):
        policy = SEC_FMP_EVIDENCE_DESCRIPTOR.rate_limit_policy.lower()
        self.assertIn("429", policy)
        self.assertIn("never retried", policy)

    def test_claim_status_rules_state_the_authority_ladder(self):
        rules = " ".join(SEC_FMP_EVIDENCE_DESCRIPTOR.claim_status_rules).lower()
        self.assertIn("canonical", rules)
        self.assertIn("verified_fact", rules)
        self.assertIn("company_claim", rules)
        self.assertIn("convenience", rules)
        self.assertIn("never promoted", rules)


# --------------------------------------------------------------------------- #
# 2. Authority mapping: canonical / company_claim / convenience, per record     #
# --------------------------------------------------------------------------- #
class AuthorityMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = SecFmpEvidenceAdapter(transports=_mock_transports())
        cls.events, cls.result = cls.adapter.fetch_checked(
            watchlist=("IREN",), themes=("physical-ai",), now=_NOW)

    def test_reality_events_only_with_full_provenance(self):
        self.assertTrue(self.events)
        self.assertEqual(self.result.status, "success")
        self.assertEqual(self.result.events_created, len(self.events))
        for ev in self.events:
            self.assertIsInstance(ev, RealityEvent)
            self.assertTrue(ev.source_authority)
            self.assertIn("#sha256=", ev.raw_payload_ref)   # content-derived raw ref
            self.assertTrue(ev.evidence_refs or ev.source_refs)

    def test_sec_filing_facts_are_canonical_verified(self):
        sec = [e for e in self.events if e.source_id == "sec.edgar"]
        self.assertTrue(sec)
        for ev in sec:
            self.assertEqual(ev.source_authority, "canonical")
            self.assertEqual(ev.claim_status, "verified_fact")
            self.assertEqual(ev.discipline, "news_filings")

    def test_dilutive_s3_and_8k_contract_events_emitted(self):
        types = {e.event_type for e in self.events}
        self.assertIn("sec_s-3_shelf_registration", types)
        self.assertIn("sec_8-k_material_event", types)
        s3 = next(e for e in self.events
                  if e.event_type == "sec_s-3_shelf_registration")
        self.assertIn("dilutive", s3.observed_fact)
        eightk = next(e for e in self.events
                      if e.event_type == "sec_8-k_material_event")
        self.assertIn("contract", eightk.observed_fact)      # Item 1.01 wording

    def test_non_catalyst_forms_are_not_emitted(self):
        # the fixture 10-Q is NOT a declared output of this adapter
        self.assertFalse(any("10-q" in e.event_type.lower() for e in self.events))

    def test_press_release_is_company_claim_never_verified(self):
        pr = [e for e in self.events if e.event_type == "press_release"]
        self.assertTrue(pr)
        for ev in pr:
            self.assertEqual(ev.claim_status, "company_claim")
            self.assertNotEqual(ev.claim_status, "verified_fact")
            self.assertNotEqual(ev.source_authority, "canonical")   # never promoted
            self.assertTrue(ev.company_claim)   # marked as the company's statement

    def test_reported_news_is_reported_claim(self):
        rep = [e for e in self.events if e.event_type == "reported_news_item"]
        self.assertTrue(rep)
        for ev in rep:
            self.assertEqual(ev.claim_status, "reported_claim")
            self.assertEqual(ev.source_authority, "convenience")

    def test_fmp_fundamental_snapshot_is_convenience_inferred_with_units(self):
        snaps = [e for e in self.events if e.event_type == "fundamental_snapshot"]
        self.assertEqual(len(snaps), 1)
        snap = snaps[0]
        self.assertEqual(snap.discipline, "financial_inflection")
        self.assertEqual(snap.source_authority, "convenience")
        self.assertEqual(snap.claim_status, "inferred")
        by_name = {name: (value, unit) for name, value, unit in snap.numeric_values}
        self.assertEqual(by_name["revenue_usd"], (118000000, "usd"))
        self.assertEqual(by_name["revenue_prior_usd"], (99000000, "usd"))
        self.assertEqual(by_name["shares_outstanding"], (210000000, "shares"))
        self.assertEqual(by_name["market_cap_usd"], (4200000000, "usd"))

    def test_no_fmp_sourced_event_is_ever_canonical(self):
        for ev in self.events:
            if ev.source_id.startswith("fmp"):
                self.assertNotEqual(ev.source_authority, "canonical", ev.event_id)
                self.assertNotEqual(ev.claim_status, "verified_fact", ev.event_id)

    def test_descriptor_only_financial_inflection_consumer_gap_recorded(self):
        self.assertIn(FINANCIAL_INFLECTION_CONSUMER_GAP, self.result.data_gaps)
        self.assertIn("descriptor-only", FINANCIAL_INFLECTION_CONSUMER_GAP)

    def test_deterministic_ids_and_run_id(self):
        events2, result2 = SecFmpEvidenceAdapter(
            transports=_mock_transports()).fetch_checked(
                watchlist=("IREN",), themes=("physical-ai",), now=_NOW)
        self.assertEqual([e.event_id for e in self.events],
                         [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        self.assertTrue(self.result.run_id.startswith("adapterrun.evidence.sec_fmp."))


# --------------------------------------------------------------------------- #
# 3. Credentials: presence labels only; missing -> visible gap, never a leak    #
# --------------------------------------------------------------------------- #
class CredentialTests(unittest.TestCase):
    def test_missing_sec_user_agent_skips_sec_with_gap_no_crash(self):
        adapter = SecFmpEvidenceAdapter(
            transports=_mock_transports(), sec_user_agent_present=False)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.status, "partial")            # FMP still delivered
        self.assertEqual(result.source_health, "credentials_missing")
        self.assertEqual(result.credentials_status, "missing")   # a LABEL, never a value
        self.assertTrue(any("SEC_USER_AGENT" in g for g in result.data_gaps))
        self.assertFalse(any(e.source_id == "sec.edgar" for e in events))
        self.assertTrue(any(e.source_id.startswith("fmp") for e in events))
        # the credentials gap surfaces on the 013D health record too
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "credentials_missing")
        self.assertEqual(record.credentials_status, "missing")

    def test_missing_fmp_api_key_skips_fmp_with_gap(self):
        adapter = SecFmpEvidenceAdapter(
            transports=_mock_transports(), fmp_api_key_present=False)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.status, "partial")            # SEC still delivered
        self.assertTrue(any("FMP_API_KEY" in g for g in result.data_gaps))
        self.assertFalse(any(e.source_id.startswith("fmp") for e in events))
        self.assertTrue(any(e.source_id == "sec.edgar" for e in events))

    def test_both_credentials_missing_is_a_skipped_result_with_gaps(self):
        adapter = SecFmpEvidenceAdapter(
            transports=_mock_transports(),
            sec_user_agent_present=False, fmp_api_key_present=False)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.source_health, "credentials_missing")
        gaps = " ".join(result.data_gaps)
        self.assertIn("SEC_USER_AGENT", gaps)
        self.assertIn("FMP_API_KEY", gaps)
        self.assertIn("nothing fabricated", gaps)

    def test_credential_value_passed_as_flag_is_rejected_and_never_echoed(self):
        for kw in ("sec_user_agent_present", "fmp_api_key_present"):
            with self.assertRaises(ValueError) as ctx:
                SecFmpEvidenceAdapter(transports=_mock_transports(),
                                      **{kw: _FAKE_CREDENTIAL})
            message = str(ctx.exception)
            self.assertNotIn(_FAKE_CREDENTIAL, message)       # NEVER echoed back
            self.assertIn("PRESENCE flag", message)

    def test_no_credential_value_in_any_event_result_or_repr(self):
        adapter = SecFmpEvidenceAdapter(
            transports=_mock_transports(), sec_user_agent_present=True,
            fmp_api_key_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.credentials_status, "present")   # a label only
        surfaces = [repr(adapter), repr(result), _blob(result)]
        surfaces.extend(repr(e) for e in events)
        for text in surfaces:
            low = text.lower()
            self.assertNotIn(_FAKE_CREDENTIAL.lower(), low)
            for bad in ("api_key=", "apikey=", "password", "secret_key"):
                self.assertNotIn(bad, low)
            self.assertNotRegex(low, r"\bsk-[a-z0-9]{6}")


# --------------------------------------------------------------------------- #
# 4. Failure capture: rate limit / unavailability / malformed -> gaps, partial  #
# --------------------------------------------------------------------------- #
class FailureCaptureTests(unittest.TestCase):
    def test_rate_limited_transport_is_captured_and_others_continue(self):
        adapter = SecFmpEvidenceAdapter(
            transports=_mock_transports(fmp_news=_raise_rate_limit))
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.status, "partial")            # NOT a crash, NOT empty
        self.assertEqual(result.rate_limit_status, "throttled")
        self.assertEqual(result.source_health, "rate_limited")
        self.assertTrue(any(e.startswith("rate_limited: fmp_news")
                            for e in result.errors))
        self.assertTrue(any("not retried" in g for g in result.data_gaps))
        # the OTHER payloads still delivered: filings + fundamentals present, news absent
        self.assertTrue(any(e.source_id == "sec.edgar" for e in events))
        self.assertTrue(any(e.event_type == "fundamental_snapshot" for e in events))
        self.assertFalse(any(e.event_type == "press_release" for e in events))

    def test_failing_ticker_is_isolated_and_named_others_continue(self):
        def _sec(tk):
            if tk == "BADX":
                raise RuntimeError("connection reset by peer (simulated)")
            return _load("sec_submissions_iren.json")

        adapter = SecFmpEvidenceAdapter(
            transports=_mock_transports(sec_submissions=_sec))
        events, result = adapter.fetch_checked(watchlist=("IREN", "BADX"), now=_NOW)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(e.startswith("source_unavailable: sec_submissions BADX")
                            for e in result.errors))
        self.assertTrue(any("BADX" in g for g in result.data_gaps))
        # IREN's SEC filings AND BADX's FMP payloads still delivered
        self.assertTrue(any(e.source_id == "sec.edgar"
                            and e.affected_companies == ("IREN",) for e in events))
        self.assertTrue(any(e.affected_companies == ("BADX",) for e in events))

    def test_malformed_payload_is_a_parse_error_gap(self):
        adapter = SecFmpEvidenceAdapter(transports=_mock_transports(
            fmp_income_statement=lambda tk: _load(
                "fmp_income_statement_malformed.json")))
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(e.startswith("parse_error: fmp_income_statement")
                            for e in result.errors))
        self.assertTrue(any("parse_error" in g and "nothing fabricated" in g
                            for g in result.data_gaps))
        # no income figure was invented; the snapshot (from the profile) carries none
        snap = next(e for e in events if e.event_type == "fundamental_snapshot")
        self.assertFalse(any(name.startswith("revenue")
                             for name, _v, _u in snap.numeric_values))

    def test_malformed_sec_submissions_is_a_parse_error_gap(self):
        adapter = SecFmpEvidenceAdapter(transports=_mock_transports(
            sec_submissions=lambda tk: {"filings": {}}))
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(e.startswith("parse_error: sec_submissions")
                            for e in result.errors))
        self.assertFalse(any(e.source_id == "sec.edgar" for e in events))
        self.assertTrue(any(e.source_id.startswith("fmp") for e in events))

    def test_all_transports_failing_is_a_failed_result_never_a_crash(self):
        adapter = SecFmpEvidenceAdapter(transports={
            "sec_submissions": _raise_unavailable,
            "fmp_news": _raise_unavailable,
            "fmp_profile": _raise_unavailable,
            "fmp_income_statement": _raise_unavailable,
        })
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(result.data_gaps)

    def test_empty_watchlist_is_a_skipped_result_with_gap(self):
        adapter = SecFmpEvidenceAdapter(transports=_mock_transports())
        events, result = adapter.fetch_checked(watchlist=(), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertTrue(any("empty watchlist" in g for g in result.data_gaps))


# --------------------------------------------------------------------------- #
# 5. No ambient network: no transports -> refused; transports must be callables #
# --------------------------------------------------------------------------- #
class NoAmbientNetworkTests(unittest.TestCase):
    def test_no_transports_and_network_required_is_refused_with_gap(self):
        adapter = SecFmpEvidenceAdapter()   # network_required=True, NOTHING injected
        events, result = adapter.fetch_checked(
            watchlist=("IREN",), themes=("physical-ai",), now=_NOW)
        self.assertEqual(events, ())        # nothing fetched -- no ambient network path
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.source_health, "source_unavailable")
        self.assertTrue(any("network" in g.lower() for g in result.data_gaps))
        self.assertTrue(any("LAST onboarding stage" in g for g in result.data_gaps))

    def test_non_callable_transport_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            SecFmpEvidenceAdapter(transports={"sec_submissions": "https://sec.gov"})
        with self.assertRaises(ValueError):
            SecFmpEvidenceAdapter(transports={"": lambda tk: {}})

    def test_module_imports_no_network_module_anywhere(self):
        with open(_EVIDENCE_SOURCES_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx",
                  "websocket", "websockets", "ftplib", "smtplib", "telnetlib")
        # module level AND inside every function: transports are injected, so this module
        # needs no network import at all (stricter than live_transport's lazy pattern).
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
                        "network import {0!r} in evidence_sources.py".format(name))

    def test_no_score_rank_or_rating_function_defs(self):
        with open(_EVIDENCE_SOURCES_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                 "banned fn name {0!r}".format(node.name))

    def test_offline_under_socket_kill_switch(self):
        orig = socket.socket.connect

        def _block(*_a, **_k):
            raise AssertionError(
                "network blocked: the SEC/FMP adapter must run fully offline on mocks")

        socket.socket.connect = _block
        try:
            events, result = SecFmpEvidenceAdapter(
                transports=_mock_transports()).fetch_checked(
                    watchlist=("IREN",), now=_NOW)
            self.assertEqual(result.status, "success")
            r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SecFmpEvidenceAdapter(
                              transports=_mock_transports()),))
            self.assertTrue(r.findings)
            run_pulse(_WATCHLIST, _THEMES, now=_NOW)   # default path offline too
        finally:
            socket.socket.connect = orig


# --------------------------------------------------------------------------- #
# 6. End to end: mocked adapter -> run_pulse -> findings -> fusion -> signals   #
# --------------------------------------------------------------------------- #
class EvidencePulseEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SecFmpEvidenceAdapter(
                              transports=_mock_transports()),))

    def test_news_filings_findings_come_from_adapter_events_only(self):
        nf = [f for f in self.r.findings if f.discipline == "news_filings"]
        self.assertTrue(nf)
        for f in nf:
            for ev_id in f.input_events:
                self.assertTrue(ev_id.startswith("secfmp."),
                                "fixture event {0!r} leaked into news_filings".format(
                                    ev_id))

    def test_filing_fact_findings_are_canonical_verified(self):
        dil = [f for f in self.r.findings if f.finding_type == "dilution_risk"]
        self.assertTrue(dil)
        for f in dil:
            self.assertEqual(f.source_authority_summary, "canonical")
            self.assertEqual(claim_status_of(f), "verified_fact")

    def test_customer_win_claim_stays_a_company_claim(self):
        wins = [f for f in self.r.findings if f.finding_type == "customer_win_claim"]
        self.assertTrue(wins)
        for f in wins:
            self.assertEqual(claim_status_of(f), "company_claim")
            self.assertNotEqual(f.source_authority_summary, "canonical")

    def test_claim_vs_filing_conflict_preserved_not_promoted(self):
        # the rosy PR customer win (improving) opposes the dilutive S-3 filing fact
        # (deteriorating) for the same subject: BOTH preserved, marked disputed.
        disputed = [f for f in self.r.findings
                    if f.discipline == "news_filings"
                    and f.contradiction_status == "disputed"]
        self.assertTrue(disputed)
        types = {f.finding_type for f in disputed}
        self.assertIn("dilution_risk", types)
        self.assertIn("customer_win_claim", types)

    def test_fusion_produced_signals_from_the_adapter_findings(self):
        self.assertTrue(self.r.signals)
        self.assertTrue(any(
            src.startswith("finding.news_filings.")
            for s in self.r.signals for src in s.source_findings))

    def test_financial_inflection_stays_descriptor_only_with_dq_gap(self):
        # no sensor exists for financial_inflection in this slice: NO finding fabricated,
        # and the pulse's Data-Quality roll-up carries the explicit consumer gap.
        self.assertFalse(any(f.discipline == "financial_inflection"
                             for f in self.r.findings))
        self.assertIn(FINANCIAL_INFLECTION_CONSUMER_GAP, self.r.data_gaps)

    def test_fundamental_snapshot_events_flow_as_evidence(self):
        result = self.r.adapter_results[0]
        self.assertIsInstance(result, SourceAdapterResult)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.adapter_id, SEC_FMP_EVIDENCE_ADAPTER_ID)
        # covered companies include the watchlist tickers the snapshots delivered
        self.assertIn("IREN", self.r.covered_companies)
        self.assertIn("AAOI", self.r.covered_companies)
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "healthy")

    def test_uncovered_disciplines_still_come_from_fixtures(self):
        self.assertTrue(any(f.discipline == "market_regime" for f in self.r.findings))
        self.assertTrue(any(f.discipline == "narrative" for f in self.r.findings))

    def test_pulse_with_the_evidence_adapter_is_deterministic(self):
        again = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SecFmpEvidenceAdapter(
                              transports=_mock_transports()),))
        self.assertEqual(self.r, again)


# --------------------------------------------------------------------------- #
# 7. Default path byte-identical; opt-in only                                   #
# --------------------------------------------------------------------------- #
class DefaultPathUnchangedTests(unittest.TestCase):
    def test_default_pulse_stays_byte_identical(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        explicit_none = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                                  data_dir=None, adapters=None)
        self.assertEqual(base, explicit_none)             # every field, byte for byte
        self.assertEqual(base.adapter_results, ())
        # the default path keeps consuming the bundled news_filings fixtures
        nf = [f for f in base.findings if f.discipline == "news_filings"]
        self.assertTrue(nf)
        self.assertTrue(all(ev.startswith("pulse.")
                            for f in nf for ev in f.input_events))


if __name__ == "__main__":
    unittest.main()
