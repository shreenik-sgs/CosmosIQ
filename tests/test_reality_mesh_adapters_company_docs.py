"""IMPLEMENTATION-014C — the Company IR / investor-presentation + earnings-transcript
LOCAL-FILE adapter (OFFLINE).

Per SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 ("company IR = company_claim unless independently
verified"): the adapter emits RealityEvents ONLY; EVERYTHING a company says about itself
(deck claims, guidance, TAM statements, customer/supplier/leadership mentions, prepared
remarks, company Q&A answers) is claim_status=company_claim -- NEVER verified_fact -- at
source_authority=primary -- NEVER canonical; an analyst's transcript content is
reported_claim / analyst_estimate; a TAM statement carries the explicit "company-stated TAM
-- not independently verified" gap; numeric guidance carries units (a unit-less figure is a
gap, never a fabricated unit); a missing/malformed/stale file is a visible gap /
parse_error / stale label, never fabrication or a silent fallback. LOCAL FILES ONLY:
network_required=False, credentials not_required. The whole suite is offline; the default
run_pulse path stays byte-identical.
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
    COMPANY_DOCUMENTS_ADAPTER_ID,
    COMPANY_DOCUMENTS_DESCRIPTOR,
    COMPANY_DOCUMENTS_DISCIPLINES,
    DESCRIPTOR_ONLY_CONSUMER_GAPS,
    DOCUMENT_STALE_AFTER_DAYS,
    IR_DECK_FILENAMES,
    TAM_NOT_INDEPENDENTLY_VERIFIED_GAP,
    TRANSCRIPT_FILE_PREFIX,
    CompanyDocumentsAdapter,
    SourceAdapterResult,
    source_health_from_result,
)
from reality_mesh.models import RealityEvent
from reality_mesh.pulse import run_pulse
from reality_mesh.sensors.news_filings import claim_status_of

_HERE = os.path.dirname(os.path.abspath(__file__))
_COMPANY_DOCUMENTS_PY = os.path.join(
    _HERE, "..", "src", "reality_mesh", "adapters", "company_documents.py")
_FIXTURE_BASE = os.path.join(_HERE, "fixtures", "reality_mesh", "company_documents")

_VALID_DIR = os.path.join(_FIXTURE_BASE, "valid")
_STALE_DIR = os.path.join(_FIXTURE_BASE, "stale")
_MALFORMED_DIR = os.path.join(_FIXTURE_BASE, "malformed")
_EMPTY_DIR = os.path.join(_FIXTURE_BASE, "empty")
_ALL_VARIANT_DIRS = (_VALID_DIR, _STALE_DIR, _MALFORMED_DIR, _EMPTY_DIR)

_WATCHLIST = "IREN"
_THEMES = "physical-ai,robotics"
_NOW = "2026-07-01T14:00:00Z"


def _fetch(data_dir, watchlist=("IREN",), now=_NOW):
    return CompanyDocumentsAdapter(data_dir).fetch_checked(
        watchlist=watchlist, themes=("physical-ai",), now=now)


def _all_variant_events():
    """Every event the adapter emits across ALL bundled fixture variants."""
    events = []
    for data_dir in _ALL_VARIANT_DIRS:
        got, _result = _fetch(data_dir)
        events.extend(got)
    return events


# --------------------------------------------------------------------------- #
# 1. Descriptor: the contract declaration                                       #
# --------------------------------------------------------------------------- #
class DescriptorTests(unittest.TestCase):
    def test_identity_and_disciplines(self):
        d = COMPANY_DOCUMENTS_DESCRIPTOR
        self.assertEqual(d.adapter_id, "evidence.company_documents")
        self.assertEqual(COMPANY_DOCUMENTS_ADAPTER_ID, "evidence.company_documents")
        self.assertEqual(
            COMPANY_DOCUMENTS_DISCIPLINES,
            ("news_filings", "customer_evidence", "supplier_evidence",
             "leadership_evidence"))
        self.assertEqual(CompanyDocumentsAdapter("x").covered_disciplines,
                         COMPANY_DOCUMENTS_DISCIPLINES)

    def test_local_files_only_no_network_no_credentials(self):
        d = COMPANY_DOCUMENTS_DESCRIPTOR
        self.assertFalse(d.network_required)            # LOCAL FILES ONLY
        self.assertEqual(d.credential_requirements, ())  # no credential exists to require
        self.assertIn("local filesystem", d.rate_limit_policy)

    def test_authority_is_primary_never_canonical(self):
        self.assertEqual(COMPANY_DOCUMENTS_DESCRIPTOR.source_authority, "primary")
        rules = " ".join(COMPANY_DOCUMENTS_DESCRIPTOR.claim_status_rules).lower()
        self.assertIn("company_claim", rules)
        self.assertIn("never a verified_fact", rules)
        self.assertIn("never promoted to canonical", rules)
        self.assertIn("reported_claim", rules)
        self.assertIn("company-stated tam", rules)

    def test_declared_outputs_and_failure_modes(self):
        d = COMPANY_DOCUMENTS_DESCRIPTOR
        self.assertEqual(set(d.outputs), {
            "ir_deck_claim", "guidance_statement", "transcript_remark",
            "transcript_qa", "customer_mention", "supplier_mention",
            "leadership_statement"})
        self.assertEqual(set(d.failure_modes), {"source_unavailable", "parse_error"})

    def test_file_layout_constants(self):
        self.assertEqual(IR_DECK_FILENAMES, ("ir_deck.json", "investor_presentation.json"))
        self.assertEqual(TRANSCRIPT_FILE_PREFIX, "transcript_")
        self.assertGreater(DOCUMENT_STALE_AFTER_DAYS, 0)

    def test_constructor_rejects_empty_data_dir(self):
        with self.assertRaises(ValueError):
            CompanyDocumentsAdapter("")


# --------------------------------------------------------------------------- #
# 2. THE rule: company statements are company_claim, primary -- across ALL      #
#    fixtures, never verified_fact, never canonical                             #
# --------------------------------------------------------------------------- #
class CompanyClaimDisciplineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.result = _fetch(_VALID_DIR)
        cls.by_type = {}
        for ev in cls.events:
            cls.by_type.setdefault(ev.event_type, []).append(ev)

    def test_reality_events_only_with_full_provenance(self):
        self.assertTrue(self.events)
        self.assertEqual(self.result.status, "success")
        self.assertEqual(self.result.source_health, "healthy")
        self.assertEqual(self.result.events_created, len(self.events))
        for ev in self.events:
            self.assertIsInstance(ev, RealityEvent)
            self.assertIn("#sha256=", ev.raw_payload_ref)   # content-derived raw ref
            self.assertTrue(ev.text_excerpt_refs)           # points at the source section
            self.assertTrue(ev.evidence_refs or ev.source_refs)
            self.assertEqual(ev.affected_companies, ("IREN",))

    def test_every_company_statement_is_company_claim_never_verified_all_fixtures(self):
        # THE gate: sweep EVERY event from EVERY bundled fixture variant. No path in the
        # adapter may stamp verified_fact, and everything the company says is company_claim.
        events = _all_variant_events()
        self.assertTrue(events)
        for ev in events:
            self.assertNotEqual(ev.claim_status, "verified_fact", ev.event_id)
            if ev.company_claim:                      # the company's own words, marked
                self.assertEqual(ev.claim_status, "company_claim", ev.event_id)
            if ev.claim_status == "company_claim":    # ... and vice versa
                self.assertTrue(ev.company_claim, ev.event_id)

    def test_authority_is_primary_never_canonical_all_fixtures(self):
        for ev in _all_variant_events():
            self.assertEqual(ev.source_authority, "primary", ev.event_id)
            self.assertNotEqual(ev.source_authority, "canonical", ev.event_id)

    def test_ir_deck_claims_are_company_claims(self):
        decks = self.by_type["ir_deck_claim"]
        self.assertGreaterEqual(len(decks), 3)        # 2 claims + the TAM statement
        for ev in decks:
            self.assertEqual(ev.claim_status, "company_claim")
            self.assertTrue(ev.company_claim)
            self.assertEqual(ev.source_type, "company_ir_deck")
            self.assertEqual(ev.discipline, "news_filings")

    def test_tam_statement_carries_the_not_independently_verified_gap(self):
        tam = [ev for ev in self.by_type["ir_deck_claim"]
               if TAM_NOT_INDEPENDENTLY_VERIFIED_GAP in ev.data_gaps]
        self.assertEqual(len(tam), 1)
        ev = tam[0]
        self.assertIn("company-stated TAM -- not independently verified",
                      TAM_NOT_INDEPENDENTLY_VERIFIED_GAP)
        self.assertEqual(ev.claim_status, "company_claim")   # a claim, with the gap
        # the company's figure travels labelled as the company's, with its unit
        self.assertIn(("company_stated_tam", 1000000000000, "usd"), ev.numeric_values)

    def test_guidance_carries_numeric_values_with_units_as_company_claim(self):
        guidance = self.by_type["guidance_statement"]
        self.assertEqual(len(guidance), 1)
        ev = guidance[0]
        self.assertEqual(ev.claim_status, "company_claim")
        self.assertTrue(ev.company_claim)
        self.assertEqual(ev.numeric_values, (("revenue_fy2026_usd", 500000000, "usd"),))
        for _name, _value, unit in ev.numeric_values:
            self.assertTrue(unit)                     # a number never travels unit-less

    def test_transcript_speaker_role_mapping(self):
        remarks = self.by_type["transcript_remark"]
        self.assertEqual(len(remarks), 2)             # Co-CEO + CFO prepared remarks
        for ev in remarks:                            # company speakers -> company_claim
            self.assertEqual(ev.claim_status, "company_claim")
            self.assertTrue(ev.company_claim)
            self.assertEqual(ev.source_type, "earnings_transcript")
        qa = self.by_type["transcript_qa"]
        self.assertEqual(len(qa), 3)
        by_claim = {}
        for ev in qa:
            by_claim.setdefault(ev.claim_status, []).append(ev)
        # the Co-CEO's ANSWER is the company speaking
        self.assertEqual(len(by_claim["company_claim"]), 1)
        self.assertIn("answer", by_claim["company_claim"][0].observed_fact)
        # the analyst's QUESTION and the unknown-role operator are NOT the company
        self.assertEqual(len(by_claim["reported_claim"]), 2)
        for ev in by_claim["reported_claim"]:
            self.assertEqual(ev.company_claim, "")    # never marked as the company's words

    def test_unknown_speaker_role_is_reported_with_a_visible_gap(self):
        operator = [ev for ev in self.by_type["transcript_qa"]
                    if "operator" in ev.observed_fact.lower()]
        self.assertEqual(len(operator), 1)
        self.assertEqual(operator[0].claim_status, "reported_claim")
        self.assertTrue(any("not recognised as the company" in g
                            for g in operator[0].data_gaps))

    def test_customer_supplier_leadership_mentions_route_to_their_disciplines(self):
        for event_type, discipline in (
                ("customer_mention", "customer_evidence"),
                ("supplier_mention", "supplier_evidence"),
                ("leadership_statement", "leadership_evidence")):
            got = self.by_type[event_type]
            self.assertTrue(got, event_type)
            for ev in got:
                self.assertEqual(ev.discipline, discipline)
                self.assertEqual(ev.claim_status, "company_claim")
                self.assertTrue(ev.company_claim)

    def test_descriptor_only_consumer_gaps_recorded(self):
        # customer/supplier/leadership evidence have descriptors but NO sensor yet: the
        # delivery is honest evidence-without-interpretation, named per discipline.
        for discipline in ("customer_evidence", "supplier_evidence",
                           "leadership_evidence"):
            gap = DESCRIPTOR_ONLY_CONSUMER_GAPS[discipline]
            self.assertIn("descriptor-only", gap)
            self.assertIn(gap, self.result.data_gaps)

    def test_credentials_not_required_and_rate_limit_ok(self):
        self.assertEqual(self.result.credentials_status, "not_required")
        self.assertEqual(self.result.rate_limit_status, "ok")
        record = source_health_from_result(self.result, now=_NOW)
        self.assertEqual(record.last_status, "healthy")
        self.assertEqual(record.credentials_status, "")   # the honest no-credential sentinel

    def test_deterministic_ids_and_run_id(self):
        events2, result2 = _fetch(_VALID_DIR)
        self.assertEqual([e.event_id for e in self.events],
                         [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        self.assertTrue(self.result.run_id.startswith(
            "adapterrun.evidence.company_documents."))


# --------------------------------------------------------------------------- #
# 3. Staleness + the analyst-estimate path (the stale fixture variant)          #
# --------------------------------------------------------------------------- #
class StaleDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.result = _fetch(_STALE_DIR)

    def test_stale_as_of_marks_every_event_stale_and_is_surfaced(self):
        self.assertTrue(self.events)
        for ev in self.events:
            self.assertEqual(ev.freshness_label, "stale", ev.event_id)
        stale_warnings = [w for w in self.result.warnings if "stale as_of" in w]
        self.assertEqual(len(stale_warnings), 2)      # the deck AND the transcript
        for w in stale_warnings:
            self.assertIn("never dropped", w)
        # stale is preserved and visible -- NOT a failure and NOT silently refreshed
        self.assertEqual(self.result.status, "success")

    def test_analyst_estimate_entry_is_analyst_estimate_never_company(self):
        estimates = [ev for ev in self.events if ev.claim_status == "analyst_estimate"]
        self.assertEqual(len(estimates), 1)
        self.assertEqual(estimates[0].event_type, "transcript_qa")
        self.assertEqual(estimates[0].company_claim, "")

    def test_unit_less_guidance_figure_is_a_gap_not_a_number(self):
        guidance = [ev for ev in self.events if ev.event_type == "guidance_statement"]
        self.assertEqual(len(guidance), 1)
        ev = guidance[0]
        self.assertEqual(ev.numeric_values, ())       # the bare 23000 was NOT emitted
        self.assertTrue(any("has no unit" in g and "nothing fabricated" in g
                            for g in ev.data_gaps))
        self.assertEqual(ev.claim_status, "company_claim")   # the statement still flows

    def test_tam_statement_without_a_figure_still_carries_the_tam_gap(self):
        tam = [ev for ev in self.events
               if TAM_NOT_INDEPENDENTLY_VERIFIED_GAP in ev.data_gaps]
        self.assertEqual(len(tam), 1)
        self.assertEqual(tam[0].numeric_values, ())   # no figure given, none invented


# --------------------------------------------------------------------------- #
# 4. Failure -> visible gap / parse_error; never a crash, never fabrication     #
# --------------------------------------------------------------------------- #
class FailureCaptureTests(unittest.TestCase):
    def test_missing_data_dir_is_a_failed_result_naming_it(self):
        events, result = _fetch(os.path.join(_FIXTURE_BASE, "does_not_exist"))
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(any(e.startswith("source_unavailable: data_dir not found")
                            for e in result.errors))
        self.assertTrue(any("IREN" in g and "no silent demo fallback" in g
                            for g in result.data_gaps))

    def test_missing_ticker_dir_is_a_gap_not_a_crash_others_continue(self):
        events, result = _fetch(_VALID_DIR, watchlist=("IREN", "GHOST"))
        self.assertEqual(result.status, "partial")    # IREN still delivered
        self.assertTrue(any("GHOST" in g and "missing ticker directory" in g
                            for g in result.data_gaps))
        self.assertTrue(any(e.affected_companies == ("IREN",) for e in events))
        self.assertFalse(any(e.affected_companies == ("GHOST",) for e in events))

    def test_missing_ticker_dir_alone_is_a_failed_result(self):
        events, result = _fetch(_VALID_DIR, watchlist=("GHOST",))
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertTrue(any("GHOST" in g for g in result.data_gaps))

    def test_empty_ticker_dir_yields_gaps_naming_each_expected_document(self):
        events, result = _fetch(_EMPTY_DIR)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        gaps = " ".join(result.data_gaps)
        self.assertIn("ir_deck.json / investor_presentation.json", gaps)
        self.assertIn("transcript_<period>.json", gaps)
        self.assertIn("never fabricated", gaps)

    def test_malformed_deck_is_a_parse_error_and_the_transcript_still_delivers(self):
        events, result = _fetch(_MALFORMED_DIR)
        self.assertEqual(result.status, "partial")    # isolated, not a total failure
        self.assertTrue(any(e.startswith("parse_error: IREN/ir_deck.json")
                            for e in result.errors))
        self.assertTrue(any("parse_error" in g and "nothing fabricated" in g
                            for g in result.data_gaps))
        # no deck event was invented; the valid transcript remark still flowed
        self.assertFalse(any(e.source_type == "company_ir_deck" for e in events))
        self.assertTrue(any(e.event_type == "transcript_remark" for e in events))

    def test_invalid_entry_is_rejected_per_entry_not_silently_repaired(self):
        _events, result = _fetch(_MALFORMED_DIR)
        self.assertTrue(any(
            e.startswith("parse_error: IREN/transcript_2026Q1.json prepared_remarks[1]")
            for e in result.errors))
        self.assertTrue(any("never silently repaired" in g for g in result.data_gaps))

    def test_empty_watchlist_is_a_skipped_result_with_gap(self):
        events, result = _fetch(_VALID_DIR, watchlist=())
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertTrue(any("empty watchlist" in g for g in result.data_gaps))

    def test_failed_result_still_maps_onto_a_real_health_record(self):
        _events, result = _fetch(os.path.join(_FIXTURE_BASE, "does_not_exist"))
        self.assertIsInstance(result, SourceAdapterResult)
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "failed")
        self.assertTrue(record.unavailable_reason)


# --------------------------------------------------------------------------- #
# 5. Offline + no scheduler/broker/score, by construction                       #
# --------------------------------------------------------------------------- #
class OfflineAndBannedImportTests(unittest.TestCase):
    def _tree(self):
        with open(_COMPANY_DOCUMENTS_PY, encoding="utf-8") as fh:
            return ast.parse(fh.read())

    def test_module_imports_no_network_or_scheduler_module_anywhere(self):
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx",
                  "websocket", "websockets", "ftplib", "smtplib", "telnetlib",
                  "sched", "apscheduler", "schedule", "celery", "crontab",
                  "threading", "asyncio", "subprocess")
        for node in ast.walk(self._tree()):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for root in banned:
                    self.assertFalse(
                        name == root or name.startswith(root + "."),
                        "banned import {0!r} in company_documents.py".format(name))

    def test_no_score_rank_rating_or_broker_function_defs(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(
                    re.search(r"(score|rank|rating|broker|order|trade)", node.name),
                    "banned fn name {0!r}".format(node.name))

    def test_no_verified_fact_literal_can_be_stamped_by_this_adapter(self):
        # the module never even contains the token as a stampable value: everything a
        # company says is a claim, so no code path can assign verified_fact.
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotEqual(node.value, "verified_fact")

    def test_offline_under_socket_kill_switch(self):
        orig = socket.socket.connect

        def _block(*_a, **_k):
            raise AssertionError(
                "network blocked: the company-documents adapter must run fully offline")

        socket.socket.connect = _block
        try:
            _events, result = _fetch(_VALID_DIR)
            self.assertEqual(result.status, "success")
            r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(CompanyDocumentsAdapter(_VALID_DIR),))
            self.assertTrue(r.findings)
            run_pulse(_WATCHLIST, _THEMES, now=_NOW)   # default path offline too
        finally:
            socket.socket.connect = orig


# --------------------------------------------------------------------------- #
# 6. End to end: adapter -> run_pulse -> news_filings findings + honest gaps    #
# --------------------------------------------------------------------------- #
class CompanyDocsPulseEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(CompanyDocumentsAdapter(_VALID_DIR),))

    def test_news_filings_findings_come_from_adapter_events_only(self):
        nf = [f for f in self.r.findings if f.discipline == "news_filings"]
        self.assertTrue(nf)
        for f in nf:
            for ev_id in f.input_events:
                self.assertTrue(ev_id.startswith("companydocs."),
                                "fixture event {0!r} leaked into news_filings".format(
                                    ev_id))

    def test_every_company_document_finding_is_a_claim_never_verified(self):
        nf = [f for f in self.r.findings if f.discipline == "news_filings"]
        self.assertTrue(nf)
        for f in nf:
            self.assertNotEqual(claim_status_of(f), "verified_fact", f.finding_id)
            self.assertNotEqual(f.source_authority_summary, "canonical", f.finding_id)

    def test_deck_customer_win_and_guidance_findings_stay_company_claims(self):
        wins = [f for f in self.r.findings if f.finding_type == "customer_win_claim"]
        self.assertTrue(wins)
        guid = [f for f in self.r.findings if f.finding_type == "guidance_update"]
        self.assertTrue(guid)
        for f in wins + guid:
            self.assertEqual(claim_status_of(f), "company_claim")
            self.assertEqual(f.source_authority_summary, "primary")
            self.assertEqual(f.corroboration_status, "uncorroborated")

    def test_former_descriptor_only_consumers_now_produce_findings_not_gaps(self):
        # 014F: the customer / supplier / leadership evidence sensors are IMPLEMENTED --
        # the 014C delivery is now interpreted into real findings, so the adapter's
        # "descriptor-only" gap is satisfied (the sensor ran) and no longer carried on
        # the pulse roll-up. The adapter itself still records the gap (it is frozen);
        # the adapter-level assertion lives in test_descriptor_only_consumer_gaps_recorded.
        for discipline in ("customer_evidence", "supplier_evidence",
                           "leadership_evidence"):
            self.assertTrue(any(f.discipline == discipline for f in self.r.findings),
                            discipline)
            self.assertNotIn(DESCRIPTOR_ONLY_CONSUMER_GAPS[discipline], self.r.data_gaps)

    def test_adapter_result_surfaces_on_the_pulse(self):
        self.assertEqual(len(self.r.adapter_results), 1)
        result = self.r.adapter_results[0]
        self.assertEqual(result.adapter_id, COMPANY_DOCUMENTS_ADAPTER_ID)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.credentials_status, "not_required")
        self.assertIn("IREN", self.r.covered_companies)

    def test_fusion_produced_signals_from_the_adapter_findings(self):
        self.assertTrue(self.r.signals)
        self.assertTrue(any(
            src.startswith("finding.news_filings.")
            for s in self.r.signals for src in s.source_findings))

    def test_uncovered_disciplines_still_come_from_fixtures(self):
        self.assertTrue(any(f.discipline == "market_regime" for f in self.r.findings))
        self.assertTrue(any(f.discipline == "narrative" for f in self.r.findings))

    def test_failed_source_stays_a_visible_gap_in_the_pulse_never_backfilled(self):
        r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                      adapters=(CompanyDocumentsAdapter(
                          os.path.join(_FIXTURE_BASE, "does_not_exist")),))
        # covered disciplines come from the adapter ONLY: no news_filings finding is
        # silently rebuilt from the bundled fixtures when the source failed.
        self.assertFalse(any(f.discipline == "news_filings" for f in r.findings))
        self.assertEqual(r.adapter_results[0].status, "failed")
        self.assertTrue(any("missing company-documents directory" in g
                            for g in r.data_gaps))

    def test_pulse_with_the_company_documents_adapter_is_deterministic(self):
        again = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(CompanyDocumentsAdapter(_VALID_DIR),))
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
        # the default (demo) path keeps consuming the bundled news_filings fixtures
        nf = [f for f in base.findings if f.discipline == "news_filings"]
        self.assertTrue(nf)
        self.assertTrue(all(ev.startswith("pulse.")
                            for f in nf for ev in f.input_events))


if __name__ == "__main__":
    unittest.main()
