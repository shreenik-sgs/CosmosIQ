"""IMPLEMENTATION-014E — the X/Social LOCAL-EXPORT adapter (OFFLINE, strict weak-signal only).

Per SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 + ARCHITECTURE_CONTRACT_012 §C (X/social can
never confirm a fact): the adapter reads OPERATOR-DOWNLOADED local export files ONLY -- NO
live X, NO API, NO scraping, NO credentials (network_required=False, credentials
not_required); EVERY event is source_authority=rumor and its claim_status can never be the
verified/canonical status (the module contains no such stampable literal -- the 014C
technique); the account type flavours the claim only (company_official -> company_claim,
journalist -> reported_claim, expert/unknown -> rumor); bot/promoter risk passes through
VISIBLY (numeric_values + conflict + gap at >= 50%); watchlist/theme SCOPE is enforced (an
unrequested export entry is skipped; a requested subject with no coverage is a NAMED gap);
missing/malformed/stale -> visible gaps per the 014A pattern. End to end the 012H
SocialNarrativeAgent consumes the events unchanged, fusion keeps social weak (rumor
authority), and a social-only theme reads Data insufficient in Sphurana. The whole suite is
offline; the default run_pulse path stays byte-identical.
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
    PROMOTER_BOT_RISK_VISIBLE_PCT,
    SOCIAL_EXPORT_ACCOUNT_TYPES,
    SOCIAL_EXPORT_FILE_PREFIX,
    SOCIAL_EXPORT_STALE_AFTER_HOURS,
    SOCIAL_EXPORTS_ADAPTER_ID,
    SOCIAL_EXPORTS_DESCRIPTOR,
    SOCIAL_EXPORTS_DISCIPLINES,
    SocialExportsAdapter,
    SourceAdapterResult,
    source_health_from_result,
)
from reality_mesh.models import RealityEvent
from reality_mesh.pulse import run_pulse
from reality_mesh.sensors.news_filings import claim_status_of
from reality_mesh.sensors.social_narrative import assert_narrative_not_verified
from reality_mesh.validation import assert_social_not_verified

_HERE = os.path.dirname(os.path.abspath(__file__))
_SOCIAL_EXPORTS_PY = os.path.join(
    _HERE, "..", "src", "reality_mesh", "adapters", "social_exports.py")
_FIXTURE_BASE = os.path.join(_HERE, "fixtures", "reality_mesh", "social_exports")

_VALID_DIR = os.path.join(_FIXTURE_BASE, "valid")
_STALE_DIR = os.path.join(_FIXTURE_BASE, "stale")
_MALFORMED_DIR = os.path.join(_FIXTURE_BASE, "malformed")
_ALL_VARIANT_DIRS = (_VALID_DIR, _STALE_DIR, _MALFORMED_DIR)

_WATCHLIST = "IREN"
_THEMES = "physical-ai,quantum-networking"
_NOW = "2026-07-02T14:00:00Z"

# The one status a social source may never stamp -- built at runtime so THIS test can name
# it without the adapter module ever containing it as a literal.
_FORBIDDEN_CLAIM = "verified" + "_fact"


def _fetch(data_dir, watchlist=("IREN",),
           themes=("physical-ai", "quantum-networking"), now=_NOW):
    return SocialExportsAdapter(data_dir).fetch_checked(
        watchlist=watchlist, themes=themes, now=now)


def _all_variant_events():
    """Every event the adapter emits across ALL bundled fixture variants."""
    events = []
    for data_dir in _ALL_VARIANT_DIRS:
        got, _result = _fetch(data_dir)
        events.extend(got)
    return events


# --------------------------------------------------------------------------- #
# 1. Descriptor: the contract declaration (strictest adapter)                   #
# --------------------------------------------------------------------------- #
class DescriptorTests(unittest.TestCase):
    def test_identity_and_disciplines(self):
        d = SOCIAL_EXPORTS_DESCRIPTOR
        self.assertEqual(d.adapter_id, "narrative.social_exports")
        self.assertEqual(SOCIAL_EXPORTS_ADAPTER_ID, "narrative.social_exports")
        self.assertEqual(SOCIAL_EXPORTS_DISCIPLINES, ("narrative",))
        self.assertEqual(SocialExportsAdapter("x").covered_disciplines, ("narrative",))

    def test_no_live_x_no_network_no_credentials(self):
        d = SOCIAL_EXPORTS_DESCRIPTOR
        self.assertFalse(d.network_required)             # NO live X -- local exports only
        self.assertEqual(d.credential_requirements, ())  # NO credential exists to require
        self.assertIn("local filesystem", d.rate_limit_policy)
        self.assertIn("operator-downloaded", d.source_name.lower())

    def test_authority_is_rumor_always(self):
        d = SOCIAL_EXPORTS_DESCRIPTOR
        self.assertEqual(d.source_authority, "rumor")
        rules = " ".join(d.claim_status_rules).lower()
        self.assertIn("rumor stays rumor", rules)
        self.assertIn("company_claim", rules)
        self.assertIn("reported_claim", rules)
        self.assertIn("never canonical", rules)
        self.assertIn("scope enforced", rules)
        self.assertIn("promoter-risk", rules)

    def test_declared_outputs_and_failure_modes(self):
        d = SOCIAL_EXPORTS_DESCRIPTOR
        self.assertEqual(set(d.outputs), {
            "social_mention_spike", "theme_mention_spike", "company_account_claim",
            "journalist_account_report", "expert_account_post"})
        self.assertEqual(set(d.failure_modes), {"source_unavailable", "parse_error"})

    def test_file_layout_and_threshold_constants(self):
        self.assertEqual(SOCIAL_EXPORT_FILE_PREFIX, "social_export_")
        self.assertGreater(SOCIAL_EXPORT_STALE_AFTER_HOURS, 0)
        self.assertEqual(PROMOTER_BOT_RISK_VISIBLE_PCT, 50)
        self.assertEqual(SOCIAL_EXPORT_ACCOUNT_TYPES,
                         ("company_official", "journalist", "expert", "unknown"))

    def test_constructor_rejects_empty_data_dir(self):
        with self.assertRaises(ValueError):
            SocialExportsAdapter("")


# --------------------------------------------------------------------------- #
# 2. THE rule: rumor authority ALWAYS; claim never verified -- across ALL        #
#    fixtures; account type flavours the claim only                             #
# --------------------------------------------------------------------------- #
class RumorAlwaysTests(unittest.TestCase):
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
            self.assertEqual(ev.discipline, "narrative")
            self.assertEqual(ev.source_type, "social_export")
            self.assertIn("#sha256=", ev.raw_payload_ref)   # content-derived raw ref
            self.assertTrue(ev.text_excerpt_refs)           # points at posts[<i>]
            self.assertTrue(ev.evidence_refs or ev.source_refs)

    def test_every_event_is_rumor_authority_never_verified_all_fixtures(self):
        # THE gate: sweep EVERY event from EVERY bundled fixture variant. Authority is
        # rumor on every record; no claim status is ever the verified/canonical one; and
        # every event passes the accepted event-side social guard unchanged.
        events = _all_variant_events()
        self.assertTrue(events)
        for ev in events:
            self.assertEqual(ev.source_authority, "rumor", ev.event_id)
            self.assertNotEqual(ev.claim_status, _FORBIDDEN_CLAIM, ev.event_id)
            self.assertNotEqual(ev.claim_status, "canonical", ev.event_id)
            self.assertIn(ev.claim_status,
                          ("rumor", "company_claim", "reported_claim"), ev.event_id)
            assert_social_not_verified(ev)                  # reused accepted guard

    def test_company_official_account_is_company_claim_never_verified(self):
        posts = self.by_type["company_account_claim"]
        self.assertEqual(len(posts), 1)
        ev = posts[0]
        self.assertEqual(ev.claim_status, "company_claim")
        self.assertNotEqual(ev.claim_status, _FORBIDDEN_CLAIM)
        self.assertEqual(ev.source_authority, "rumor")      # flavour, NOT a promotion
        self.assertTrue(ev.company_claim)                   # the company's words, marked
        self.assertIn("official company account", ev.observed_fact)

    def test_journalist_account_is_reported_claim(self):
        posts = self.by_type["journalist_account_report"]
        self.assertEqual(len(posts), 1)
        ev = posts[0]
        self.assertEqual(ev.claim_status, "reported_claim")
        self.assertEqual(ev.source_authority, "rumor")
        self.assertEqual(ev.company_claim, "")              # never the company's words

    def test_expert_and_unknown_accounts_stay_rumor(self):
        for event_type in ("expert_account_post", "social_mention_spike",
                           "theme_mention_spike"):
            for ev in self.by_type[event_type]:
                self.assertEqual(ev.claim_status, "rumor", ev.event_id)
                self.assertEqual(ev.company_claim, "", ev.event_id)

    def test_unrecognised_author_type_is_treated_as_unknown_with_a_visible_note(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "social_export_2026-07-02.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"as_of": _NOW, "posts": [{
                    "text": "IREN ceo said we crushed it",
                    "author_handle": "@self_certified",
                    "author_type": "totally_trustworthy_insider",
                    "tickers": ["IREN"], "themes": [],
                    "posted_at": _NOW}]}, fh)
            events, _result = _fetch(d, themes=())
            self.assertEqual(len(events), 1)
            ev = events[0]
            self.assertEqual(ev.claim_status, "rumor")      # never assumed upward
            self.assertEqual(ev.source_authority, "rumor")
            self.assertTrue(any("not recognised" in g and "never assumed upward" in g
                                for g in ev.data_gaps))

    def test_deterministic_ids_and_run_id(self):
        events2, result2 = _fetch(_VALID_DIR)
        self.assertEqual([e.event_id for e in self.events],
                         [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        self.assertTrue(self.result.run_id.startswith(
            "adapterrun.narrative.social_exports."))

    def test_credentials_not_required_and_rate_limit_ok(self):
        self.assertEqual(self.result.credentials_status, "not_required")
        self.assertEqual(self.result.rate_limit_status, "ok")
        record = source_health_from_result(self.result, now=_NOW)
        self.assertEqual(record.last_status, "healthy")
        self.assertEqual(record.credentials_status, "")   # the honest no-credential sentinel


# --------------------------------------------------------------------------- #
# 3. Bot / promoter risk passes through VISIBLY                                 #
# --------------------------------------------------------------------------- #
class BotRiskVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.result = _fetch(_VALID_DIR)
        cls.promoter = [ev for ev in cls.events
                        if any(n == "bot_risk_pct" and v >= PROMOTER_BOT_RISK_VISIBLE_PCT
                               for n, v, _u in ev.numeric_values)]

    def test_high_bot_risk_rides_in_numeric_values_with_unit(self):
        self.assertEqual(len(self.promoter), 1)
        self.assertIn(("bot_risk_pct", 87, "pct"), self.promoter[0].numeric_values)

    def test_high_bot_risk_is_visible_in_conflict_gap_and_observed_fact(self):
        ev = self.promoter[0]
        self.assertTrue(any("PROMOTER/BOT RISK" in c and "never silently filtered" in c
                            for c in ev.conflicts))
        self.assertTrue(any("promoter/bot risk" in g and "suspect" in g
                            for g in ev.data_gaps))
        self.assertIn("PROMOTER/BOT RISK (87% bot-risk)", ev.observed_fact)
        self.assertEqual(ev.confidence_label, "very_low")
        # visible -- and still rumor, still never a fact
        self.assertEqual(ev.source_authority, "rumor")
        self.assertEqual(ev.claim_status, "rumor")

    def test_low_bot_risk_still_passes_through_without_the_promoter_flag(self):
        low = [ev for ev in self.events if ev not in self.promoter
               and any(n == "bot_risk_pct" for n, _v, _u in ev.numeric_values)]
        self.assertTrue(low)
        for ev in low:
            self.assertFalse(ev.conflicts, ev.event_id)     # no promoter conflict invented
            self.assertNotIn("PROMOTER/BOT RISK", ev.observed_fact)

    def test_mention_and_follower_metadata_carry_units(self):
        spike = [ev for ev in self.events
                 if ev.event_type == "social_mention_spike"
                 and ev not in self.promoter][0]
        names = {n: (v, u) for n, v, u in spike.numeric_values}
        self.assertEqual(names["mention_count"], (5200, "count"))
        self.assertEqual(names["mention_velocity_zscore"], (3.6, "zscore"))
        self.assertEqual(names["unique_authors"], (1400, "count"))
        self.assertEqual(names["follower_count"], (3200, "count"))


# --------------------------------------------------------------------------- #
# 4. Watchlist / theme SCOPE enforced (the 014D rule)                           #
# --------------------------------------------------------------------------- #
class ScopeEnforcementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.result = _fetch(_VALID_DIR)

    def test_unrequested_ticker_entries_are_not_emitted(self):
        # The fixture carries a ZZTOP-only post; ZZTOP was not requested -> skipped.
        for ev in self.events:
            self.assertNotIn("ZZTOP", ev.affected_companies, ev.event_id)
        self.assertFalse(any("smallcap_sniper" in ev.observed_fact
                             for ev in self.events))

    def test_unrequested_theme_entries_are_not_emitted(self):
        # The fixture carries a metaverse-land post; that theme was not requested.
        for ev in self.events:
            for theme in ev.affected_themes:
                self.assertNotIn("metaverse", theme.lower(), ev.event_id)

    def test_mixed_post_is_scoped_to_the_requested_ticker_only(self):
        # The journalist post lists IREN AND ZZTOP: only the requested ticker flows.
        posts = [ev for ev in self.events
                 if ev.event_type == "journalist_account_report"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].affected_companies, ("IREN",))

    def test_requesting_the_ticker_admits_its_entries(self):
        events, _result = _fetch(_VALID_DIR, watchlist=("IREN", "ZZTOP"))
        self.assertTrue(any(ev.affected_companies == ("ZZTOP",) for ev in events))

    def test_requested_ticker_with_no_coverage_is_a_named_gap(self):
        events, result = _fetch(_VALID_DIR, watchlist=("IREN", "GHOST"))
        self.assertEqual(result.status, "partial")          # IREN still delivered
        self.assertTrue(any("GHOST" in g and "NO social-export" in g
                            and "no silent demo fallback" in g
                            for g in result.data_gaps))
        self.assertTrue(events)

    def test_requested_theme_with_no_coverage_is_a_named_gap(self):
        _events, result = _fetch(
            _VALID_DIR, themes=("physical-ai", "fusion-power"))
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("'fusion-power'" in g and "NO social-export" in g
                            for g in result.data_gaps))

    def test_theme_matching_is_spelling_tolerant(self):
        # requested 'quantum-networking' matches the export's 'Quantum Networking'.
        theme_events = [ev for ev in self.events
                        if ev.event_type == "theme_mention_spike"]
        self.assertEqual(len(theme_events), 1)
        self.assertEqual(theme_events[0].affected_themes, ("Quantum Networking",))

    def test_empty_scope_is_a_skipped_result_with_gap(self):
        events, result = _fetch(_VALID_DIR, watchlist=(), themes=())
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertTrue(any("no scope" in g for g in result.data_gaps))


# --------------------------------------------------------------------------- #
# 5. Staleness -- preserved and visible, never dropped or refreshed             #
# --------------------------------------------------------------------------- #
class StaleExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.result = _fetch(_STALE_DIR, themes=())

    def test_stale_posted_at_marks_every_event_stale(self):
        self.assertEqual(len(self.events), 2)
        for ev in self.events:
            self.assertEqual(ev.freshness_label, "stale", ev.event_id)
        stale_warnings = [w for w in self.result.warnings if "stale post" in w]
        self.assertEqual(len(stale_warnings), 2)
        for w in stale_warnings:
            self.assertIn("never dropped", w)
        # stale is preserved and visible -- NOT a failure and NOT silently refreshed
        self.assertEqual(self.result.status, "success")

    def test_missing_posted_at_falls_back_to_the_file_as_of(self):
        # posts[1] has no posted_at; the file's as_of (2026-05-01) makes it stale too,
        # and its timestamp carries the as_of rather than an invented time.
        spike = [ev for ev in self.events
                 if ev.event_type == "social_mention_spike"]
        self.assertEqual(len(spike), 1)
        self.assertEqual(spike[0].timestamp, "2026-05-01T12:00:00Z")
        self.assertEqual(spike[0].freshness_label, "stale")

    def test_stale_events_are_still_rumor_and_never_verified(self):
        for ev in self.events:
            self.assertEqual(ev.source_authority, "rumor")
            self.assertNotEqual(ev.claim_status, _FORBIDDEN_CLAIM)


# --------------------------------------------------------------------------- #
# 6. Failure -> visible gap / parse_error; never a crash, never fabrication     #
# --------------------------------------------------------------------------- #
class FailureCaptureTests(unittest.TestCase):
    def test_missing_data_dir_is_a_failed_result_naming_every_requested_subject(self):
        events, result = _fetch(os.path.join(_FIXTURE_BASE, "does_not_exist"))
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(any(e.startswith("source_unavailable: data_dir not found")
                            for e in result.errors))
        gaps = " ".join(result.data_gaps)
        self.assertIn("IREN", gaps)
        self.assertIn("'physical-ai'", gaps)
        self.assertIn("'quantum-networking'", gaps)
        self.assertIn("no silent demo fallback", gaps)

    def test_no_export_files_is_a_failed_result_with_named_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            events, result = _fetch(d)
            self.assertEqual(events, ())
            self.assertEqual(result.status, "failed")
            self.assertTrue(any("no social export files" in g
                                and SOCIAL_EXPORT_FILE_PREFIX in g
                                for g in result.data_gaps))
            self.assertTrue(any("IREN" in g for g in result.data_gaps))

    def test_malformed_file_is_a_parse_error_and_the_valid_file_still_delivers(self):
        events, result = _fetch(_MALFORMED_DIR, themes=())
        self.assertEqual(result.status, "partial")          # isolated, not a total failure
        self.assertTrue(any(
            e.startswith("parse_error: social_export_2026-07-01.json")
            for e in result.errors))
        self.assertTrue(any("malformed social export file" in g
                            and "nothing fabricated" in g for g in result.data_gaps))
        # the valid companion file still flowed
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "journalist_account_report")

    def test_invalid_entries_are_rejected_per_entry_not_silently_repaired(self):
        _events, result = _fetch(_MALFORMED_DIR, themes=())
        for index, reason in ((1, "missing post text"), (2, "post must be a JSON object"),
                              (3, "follower_count must be numeric")):
            self.assertTrue(any(
                e.startswith("parse_error: social_export_2026-07-02.json posts[{0}]".format(
                    index)) and reason in e
                for e in result.errors), reason)
        self.assertTrue(any("never silently repaired" in g for g in result.data_gaps))

    def test_failed_result_still_maps_onto_a_real_health_record(self):
        _events, result = _fetch(os.path.join(_FIXTURE_BASE, "does_not_exist"))
        self.assertIsInstance(result, SourceAdapterResult)
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "failed")
        self.assertTrue(record.unavailable_reason)


# --------------------------------------------------------------------------- #
# 7. Offline + no live X / scheduler / broker / score, by construction          #
# --------------------------------------------------------------------------- #
class OfflineAndBannedImportTests(unittest.TestCase):
    def _tree(self):
        with open(_SOCIAL_EXPORTS_PY, encoding="utf-8") as fh:
            return ast.parse(fh.read())

    def test_module_imports_no_network_or_scheduler_module_anywhere(self):
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx",
                  "websocket", "websockets", "ftplib", "smtplib", "telnetlib",
                  "sched", "apscheduler", "schedule", "celery", "crontab",
                  "threading", "asyncio", "subprocess", "tweepy", "twython")
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
                        "banned import {0!r} in social_exports.py".format(name))

    def test_no_score_rank_rating_or_broker_function_defs(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(
                    re.search(r"(score|rank|rating|broker|order|trade)", node.name),
                    "banned fn name {0!r}".format(node.name))

    def test_no_verified_fact_literal_can_be_stamped_by_this_adapter(self):
        # the 014C technique: the module never even contains the token as a stampable
        # value, so no code path can assign the verified claim status.
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotEqual(node.value, _FORBIDDEN_CLAIM)
                self.assertNotIn(_FORBIDDEN_CLAIM, node.value)

    def test_no_url_or_api_endpoint_literal_in_the_module(self):
        # NO live X: no http(s) endpoint, no API host, no x.com/twitter URL anywhere.
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.lower()
                self.assertNotIn("http://", low)
                self.assertNotIn("https://", low)
                self.assertNotIn("api.twitter", low)
                self.assertNotIn("api.x.com", low)

    def test_offline_under_socket_kill_switch(self):
        orig = socket.socket.connect

        def _block(*_a, **_k):
            raise AssertionError(
                "network blocked: the social-exports adapter must run fully offline")

        socket.socket.connect = _block
        try:
            _events, result = _fetch(_VALID_DIR)
            self.assertEqual(result.status, "success")
            r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SocialExportsAdapter(_VALID_DIR),))
            self.assertTrue(r.findings)
            run_pulse(_WATCHLIST, _THEMES, now=_NOW)   # default path offline too
        finally:
            socket.socket.connect = orig


# --------------------------------------------------------------------------- #
# 8. End to end: adapter -> pulse -> 012H narrative findings -> fusion ->        #
#    Sphurana (social stays weak everywhere)                                    #
# --------------------------------------------------------------------------- #
class SocialExportsPulseEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SocialExportsAdapter(_VALID_DIR),))
        cls.narrative = [f for f in cls.r.findings if f.discipline == "narrative"]

    def test_narrative_findings_come_from_adapter_events_only(self):
        self.assertTrue(self.narrative)
        for f in self.narrative:
            for ev_id in f.input_events:
                self.assertTrue(ev_id.startswith("socialexport."),
                                "fixture event {0!r} leaked into narrative".format(ev_id))

    def test_every_narrative_finding_is_rumor_and_never_verified(self):
        for f in self.narrative:
            assert_narrative_not_verified(f)     # reused accepted finding-side guard
            self.assertEqual(f.source_authority_summary, "rumor", f.finding_id)
            self.assertNotEqual(claim_status_of(f), _FORBIDDEN_CLAIM, f.finding_id)
            self.assertNotEqual(claim_status_of(f), "canonical", f.finding_id)

    def test_account_flavours_survive_into_the_012h_findings_unchanged(self):
        by_type = {}
        for f in self.narrative:
            by_type.setdefault(f.finding_type, []).append(f)
        self.assertEqual(claim_status_of(by_type["CompanyClaimFinding"][0]),
                         "company_claim")
        journalist = [f for f in by_type["NarrativeFinding"]
                      if claim_status_of(f) == "reported_claim"]
        self.assertTrue(journalist)
        self.assertIn("ExpertNarrativeFinding", by_type)
        self.assertIn("ThemeNarrativeVelocityFinding", by_type)

    def test_promoter_risk_stays_visible_in_the_finding(self):
        risky = [f for f in self.narrative if f.finding_type == "PromotionRiskFinding"]
        self.assertEqual(len(risky), 1)
        f = risky[0]
        self.assertTrue(any("PROMOTER/BOT RISK" in c for c in f.conflicts))
        self.assertEqual(f.confidence_label, "very_low")

    def test_fusion_keeps_social_weak_rumor_authority_on_every_narrative_signal(self):
        soc = [s for s in self.r.signals if s.discipline == "narrative"]
        self.assertTrue(soc)
        for s in soc:
            # corroboration may be lifted by NON-social agreement, but the authority is
            # NEVER lifted: rumor stays rumor on every social signal.
            self.assertEqual(self.r.authority_by_signal.get(s.signal_id), "rumor",
                             s.signal_id)

    def test_social_only_theme_reads_data_insufficient_in_sphurana(self):
        norm = {re.sub(r"[^a-z0-9]", "", p.theme_name.lower()): p
                for p in self.r.theme_pulses}
        pulse = norm.get("quantumnetworking")
        self.assertIsNotNone(pulse, "expected a theme pulse for the social-only theme")
        self.assertEqual(pulse.state, "Data insufficient")   # reused accepted invariant
        self.assertNotEqual(pulse.state, "Igniting")
        self.assertIn(pulse.confidence_label, ("missing", "very_low", "low"))
        soc_signals = [s.signal_id for s in self.r.signals
                       if s.discipline == "narrative"
                       and "quantum" in " ".join(s.affected_themes).lower()]
        self.assertTrue(soc_signals)
        for sid in soc_signals:
            self.assertEqual(self.r.corroboration_by_signal.get(sid), "uncorroborated")

    def test_adapter_result_surfaces_on_the_pulse(self):
        self.assertEqual(len(self.r.adapter_results), 1)
        result = self.r.adapter_results[0]
        self.assertEqual(result.adapter_id, SOCIAL_EXPORTS_ADAPTER_ID)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.credentials_status, "not_required")
        self.assertIn("IREN", self.r.covered_companies)

    def test_failed_source_stays_a_visible_gap_never_backfilled_from_fixtures(self):
        r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                      adapters=(SocialExportsAdapter(
                          os.path.join(_FIXTURE_BASE, "does_not_exist")),))
        # covered disciplines come from the adapter ONLY: no narrative finding is
        # silently rebuilt from the bundled fixtures when the source failed.
        self.assertFalse(any(f.discipline == "narrative" for f in r.findings))
        self.assertEqual(r.adapter_results[0].status, "failed")
        self.assertTrue(any("NO social-export" in g for g in r.data_gaps))

    def test_pulse_with_the_social_exports_adapter_is_deterministic(self):
        again = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(SocialExportsAdapter(_VALID_DIR),))
        self.assertEqual(self.r, again)


# --------------------------------------------------------------------------- #
# 9. Default (demo) path byte-identical; opt-in only                            #
# --------------------------------------------------------------------------- #
class DefaultPathUnchangedTests(unittest.TestCase):
    def test_default_pulse_stays_byte_identical(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        explicit_none = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                                  data_dir=None, adapters=None)
        self.assertEqual(base, explicit_none)             # every field, byte for byte
        self.assertEqual(base.adapter_results, ())
        # the default (demo) path keeps consuming the bundled narrative fixtures
        narr = [f for f in base.findings if f.discipline == "narrative"]
        self.assertTrue(narr)
        self.assertTrue(all(ev.startswith("pulse.")
                            for f in narr for ev in f.input_events))


if __name__ == "__main__":
    unittest.main()
