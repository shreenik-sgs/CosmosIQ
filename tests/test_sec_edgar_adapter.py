"""Tests for the SEC EDGAR / data.sec.gov adapter (IMPLEMENTATION-009B).

Fixture-based only -- NO network, NO API keys/secrets, NO investment reasoning.
Local SEC-shaped JSON fixtures are loaded via ``open()`` (never fetched) and
parsed into CANONICAL evidence records, which map to Tattva Observations ONLY.
The optional live client is never exercised with a real transport / User-Agent.
"""

import ast
import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from eios_core.canonical_objects import Observation

from evidence_ingestion import (
    NormalizedEvidenceRecord,
    make_raw_evidence_record,
    make_normalized_evidence_record,
    EvidenceSource,
    map_to_observation,
    resolve_conflicts,
    SEC_PROVIDER,
    SEC_SOURCE_NAME,
    sec_source,
    classify_form,
    detect_offering_flags,
    parse_sec_submissions,
    parse_sec_companyfacts,
    SecEdgarClient,
)

# Reasoning-conclusion object types the mapper must NEVER produce.
from genesis.opportunity_hypothesis import OpportunityHypothesis
from prometheus.investment_thesis import InvestmentThesis
from prometheus.investment_action import InvestmentAction
from personal_cio.personalized_action import PersonalizedAction
from execution_manual.manual_execution_intent import ManualExecutionIntent


_FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sec")


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r") as fh:
        return json.load(fh)


def _submissions():
    return _load("submissions_iren.json")


def _companyfacts():
    return _load("companyfacts_iren.json")


def _by_type(records, normalized_type):
    for r in records:
        if r.normalized_type == normalized_type:
            return r
    raise AssertionError("no record with normalized_type {0!r}".format(normalized_type))


# --------------------------------------------------------------------------- #
# Parsing + determinism.                                                       #
# --------------------------------------------------------------------------- #

class SubmissionsParsingTests(unittest.TestCase):
    def test_sec_adapter_parses_submissions_fixture_deterministically(self):
        r1 = parse_sec_submissions(_submissions(), now=0)
        r2 = parse_sec_submissions(_submissions(), now=0)
        self.assertTrue(r1.records)
        self.assertEqual(
            [r.id for r in r1.records], [r.id for r in r2.records]
        )

    def test_sec_adapter_parses_companyfacts_fixture_deterministically(self):
        r1 = parse_sec_companyfacts(_companyfacts(), now=0)
        r2 = parse_sec_companyfacts(_companyfacts(), now=0)
        self.assertTrue(r1.records)
        self.assertEqual(
            [r.id for r in r1.records], [r.id for r in r2.records]
        )

    def test_sec_filing_records_are_canonical(self):
        res = parse_sec_submissions(_submissions(), now=0)
        for rec in res.records:
            self.assertEqual(rec.source_authority, "canonical")
            self.assertEqual(rec.source_class, "official_filing")
            self.assertEqual(rec.source.provider, SEC_PROVIDER)
            self.assertEqual(rec.source.source_name, SEC_SOURCE_NAME)
            # provenance binds a RawEvidenceRecord (Raw is canonical too).
            kinds = [r.kind for r in rec.provenance.sources]
            self.assertIn("RawEvidenceRecord", kinds)


class CompanyFactsParsingTests(unittest.TestCase):
    def test_sec_xbrl_facts_become_canonical_normalized_records(self):
        res = parse_sec_companyfacts(_companyfacts(), now=0)
        rev = _by_type(res.records, "sec_xbrl_revenue")
        self.assertEqual(rev.source_authority, "canonical")
        self.assertEqual(rev.source_class, "official_filing")
        self.assertEqual(rev.source.provider, SEC_PROVIDER)
        f = rev.extracted_fields
        self.assertEqual(f["financial_metric"], "revenue")
        self.assertEqual(f["metric_value"], 120000000)   # latest period
        self.assertEqual(f["prior_value"], 100000000)    # prior period
        self.assertEqual(f["metric_unit"], "USD")
        self.assertEqual(f["taxonomy_tag"], "Revenues")

    def test_single_period_tag_has_no_fabricated_prior(self):
        res = parse_sec_companyfacts(_companyfacts(), now=0)
        ni = _by_type(res.records, "sec_xbrl_net_income")
        self.assertEqual(ni.extracted_fields["metric_value"], 15000000)
        self.assertNotIn("prior_value", ni.extracted_fields)  # only one period


# --------------------------------------------------------------------------- #
# Classification + offering detection.                                         #
# --------------------------------------------------------------------------- #

class ClassificationTests(unittest.TestCase):
    def test_form_classification_works(self):
        self.assertEqual(classify_form("10-K"), "sec_10-k")
        self.assertEqual(classify_form("10-K/A"), "sec_10-k")
        self.assertEqual(classify_form("10-Q"), "sec_10-q")
        self.assertEqual(classify_form("8-K"), "sec_8-k")
        self.assertEqual(classify_form("S-3"), "sec_s-3")
        self.assertEqual(classify_form("S-3/A"), "sec_s-3")
        self.assertEqual(classify_form("424B5"), "sec_424b")
        self.assertEqual(classify_form("3"), "sec_insider_form")
        self.assertEqual(classify_form("13F-HR"), "sec_13f")
        self.assertEqual(classify_form("SC 13D"), "sec_filing_other")

    def test_offering_shelf_atm_indicator_conservative(self):
        res = parse_sec_submissions(_submissions(), now=0)
        s3 = _by_type(res.records, "sec_s-3")
        self.assertTrue(s3.extracted_fields.get("offering_flag"))
        self.assertEqual(s3.extracted_fields.get("expected_direction"), "negative")

        # An ordinary 10-Q carries no offering flag.
        tenq = _by_type(res.records, "sec_10-q")
        self.assertNotIn("offering_flag", tenq.extracted_fields)
        self.assertNotIn("expected_direction", tenq.extracted_fields)

    def test_detect_offering_flags_patterns(self):
        # Form-based.
        self.assertEqual(
            detect_offering_flags("S-3"), {"offering_flag": True, "expected_direction": "negative"}
        )
        self.assertEqual(
            detect_offering_flags("424B5"), {"offering_flag": True, "expected_direction": "negative"}
        )
        # Content-based on a non-offering form.
        self.assertEqual(
            detect_offering_flags("8-K", description="at-the-market program"),
            {"offering_flag": True, "expected_direction": "negative"},
        )
        self.assertEqual(
            detect_offering_flags("8-K", items="dilutive shelf takedown"),
            {"offering_flag": True, "expected_direction": "negative"},
        )
        # Ordinary filing: no flag.
        self.assertEqual(detect_offering_flags("10-Q", description="quarterly report"), {})


# --------------------------------------------------------------------------- #
# Missing-field discipline.                                                    #
# --------------------------------------------------------------------------- #

class MissingFieldTests(unittest.TestCase):
    def test_missing_sec_fields_produce_warnings_not_fabricated(self):
        # Submissions missing name/cik/tickers and a filingDate.
        doc = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000000000-26-000001"],
                    "form": ["8-K"],
                    "filingDate": [""],
                    "reportDate": [""],
                    "primaryDocument": ["x.htm"],
                    "primaryDocDescription": ["FORM 8-K"],
                    "items": [""],
                }
            }
        }
        res = parse_sec_submissions(doc, now=0)
        self.assertTrue(res.records)
        joined = " ".join(res.warnings)
        self.assertIn("name", joined)
        self.assertIn("cik", joined)
        self.assertIn("tickers", joined)
        self.assertIn("filingDate", joined)
        # No fabricated subject/ticker beyond what is derivable.
        rec = res.records[0]
        self.assertEqual(rec.ticker, "")

    def test_empty_submissions_produces_error_not_silence(self):
        res = parse_sec_submissions({}, now=0)
        self.assertFalse(res.records)
        self.assertTrue(res.errors)
        self.assertFalse(res.complete)

    def test_empty_companyfacts_produces_error_not_silence(self):
        res = parse_sec_companyfacts({}, now=0)
        self.assertFalse(res.records)
        self.assertTrue(res.errors)
        self.assertFalse(res.complete)

    def test_absent_requested_form_marks_incomplete(self):
        res = parse_sec_submissions(_submissions(), now=0, forms=("10-K",))
        self.assertFalse(res.complete)
        self.assertTrue(any("coverage" in w for w in res.warnings))

    def test_absent_xbrl_tag_warns(self):
        res = parse_sec_companyfacts(_companyfacts(), now=0)
        # GrossProfit is absent from the fixture -> a warning, not a record.
        self.assertTrue(any("GrossProfit" in w for w in res.warnings))
        self.assertFalse(
            any(r.normalized_type == "sec_xbrl_gross_profit" for r in res.records)
        )


# --------------------------------------------------------------------------- #
# Mapper: SEC records -> Tattva Observations ONLY.                             #
# --------------------------------------------------------------------------- #

class MapperTests(unittest.TestCase):
    def test_sec_normalized_maps_to_observation_only(self):
        sub = parse_sec_submissions(_submissions(), now=0)
        facts = parse_sec_companyfacts(_companyfacts(), now=0)

        s3 = _by_type(sub.records, "sec_s-3")
        eightk = _by_type(sub.records, "sec_8-k")
        rev = _by_type(facts.records, "sec_xbrl_revenue")

        for rec, expected_type in (
            (s3, "capital_structure_event"),
            (eightk, "contract_win"),
            (rev, "financial_report"),
        ):
            obs, _ = map_to_observation(rec, domain="ai-infrastructure", now=0)
            self.assertIsInstance(obs, Observation)
            self.assertNotIsInstance(obs, OpportunityHypothesis)
            self.assertNotIsInstance(obs, InvestmentThesis)
            self.assertNotIsInstance(obs, InvestmentAction)
            self.assertNotIsInstance(obs, PersonalizedAction)
            self.assertNotIsInstance(obs, ManualExecutionIntent)
            self.assertEqual(obs.content["source_type"], expected_type)

    def test_sec_observations_carry_canonical_authority(self):
        res = parse_sec_submissions(_submissions(), now=0)
        for rec in res.records:
            obs, _ = map_to_observation(rec, domain="ai-infrastructure", now=0)
            self.assertEqual(obs.content["source_authority"], "canonical")
            self.assertEqual(obs.content["source_reliability"], "high")

    def test_offering_observation_carries_negative_direction(self):
        res = parse_sec_submissions(_submissions(), now=0)
        s3 = _by_type(res.records, "sec_s-3")
        obs, _ = map_to_observation(s3, domain="ai-infrastructure", now=0)
        self.assertEqual(obs.content["expected_direction"], "negative")


# --------------------------------------------------------------------------- #
# Conflict: canonical SEC beats convenience FMP / fallback yfinance.           #
# --------------------------------------------------------------------------- #

class ConflictTests(unittest.TestCase):
    def _sec_revenue(self):
        return _by_type(parse_sec_companyfacts(_companyfacts(), now=0).records, "sec_xbrl_revenue")

    def _convenience_record(self, source_name, source_class, value, normalized_type, subject):
        src = EvidenceSource(
            source_name=source_name,
            source_authority={"paid_api": "convenience", "free_api": "fallback"}[source_class],
            source_class=source_class,
            provider=source_name,
        )
        raw = make_raw_evidence_record(
            src, subject=subject, ticker="IREN", raw_type="quote",
            raw_payload={"revenue": value}, retrieved_at="t", as_of="d", now=0,
        )
        return make_normalized_evidence_record(
            raw, normalized_type=normalized_type,
            extracted_fields={"financial_metric": "revenue", "metric_value": value},
            period_end="2026-03-31", evidence_quality=0.6, confidence=0.6, now=0,
        )

    def test_sec_canonical_beats_fmp_convenience_conflict(self):
        sec = self._sec_revenue()
        fmp = self._convenience_record(
            "Financial Modeling Prep", "paid_api", 118000000,
            sec.normalized_type, sec.subject,
        )
        resolved, warns = resolve_conflicts((sec, fmp))
        key = (sec.subject, sec.normalized_type, "metric_value")
        self.assertEqual(resolved[key], 120000000)  # SEC canonical wins
        self.assertTrue(warns)
        self.assertTrue(any("conflict" in w for w in warns))

        # SEC is not overwritten by a fallback/yfinance record either.
        yf = self._convenience_record(
            "yfinance", "free_api", 111000000, sec.normalized_type, sec.subject,
        )
        resolved2, _ = resolve_conflicts((sec, fmp, yf))
        self.assertEqual(resolved2[key], 120000000)


# --------------------------------------------------------------------------- #
# Live client: inert, requires User-Agent, never hits the wire in tests.       #
# --------------------------------------------------------------------------- #

class LiveClientTests(unittest.TestCase):
    def test_sec_client_requires_user_agent(self):
        # No user_agent -> a live fetch raises BEFORE any transport is invoked.
        # (The client reads no environment variable; user_agent is None as passed.)
        calls = []

        def transport(url, headers):  # should never be called
            calls.append(url)
            return b"{}"

        client = SecEdgarClient(user_agent=None, transport=transport)
        self.assertIsNone(client.user_agent)
        with self.assertRaises(ValueError):
            client.fetch_submissions("0001878848")
        with self.assertRaises(ValueError):
            client.fetch_companyfacts("0001878848")
        self.assertEqual(calls, [])  # transport never reached

    def test_sec_client_not_exercised_by_default(self):
        # With an injected fake transport + explicit UA, the client uses ONLY the
        # injected callable -- no network. No default test constructs a real one.
        seen = []

        def fake_transport(url, headers):
            seen.append((url, dict(headers)))
            return b"{}"

        client = SecEdgarClient(user_agent="test-agent contact@example.invalid", transport=fake_transport)
        out = client.fetch_submissions("0001878848")
        self.assertEqual(out, b"{}")
        self.assertEqual(len(seen), 1)
        url, headers = seen[0]
        self.assertIn("data.sec.gov", url)
        self.assertIn("CIK0001878848", url)
        self.assertEqual(headers["User-Agent"], "test-agent contact@example.invalid")

    def test_no_network_call_in_tests(self):
        # Behavioural meta-guard: the DEFAULT client has no User-Agent and no
        # transport, so it cannot reach the wire -- a live fetch raises ValueError.
        # The client contains no network code at all (transport is injected), so
        # nothing in the default test run can issue a real request.
        default_client = SecEdgarClient()
        self.assertIsNone(default_client.user_agent)
        with self.assertRaises(ValueError):
            default_client.fetch_submissions("0001878848")
        with self.assertRaises(ValueError):
            default_client.fetch_companyfacts("0001878848")


# --------------------------------------------------------------------------- #
# Static guards over the SEC modules.                                          #
# --------------------------------------------------------------------------- #

_PKG_DIR = os.path.join(_SRC, "evidence_ingestion")
_SEC_MODULES = ("sec_edgar.py", "sec_client.py")


def _sec_sources():
    for name in _SEC_MODULES:
        with open(os.path.join(_PKG_DIR, name), "r") as fh:
            yield name, fh.read()


class GuardTests(unittest.TestCase):
    def test_no_top_level_or_static_network_import(self):
        banned = {"requests", "urllib", "http", "socket", "aiohttp", "httpx"}
        for name, src in _sec_sources():
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        top = a.name.split(".")[0]
                        self.assertNotIn(top, banned, "{0} imports {1}".format(name, top))
                elif isinstance(node, ast.ImportFrom):
                    top = (node.module or "").split(".")[0]
                    self.assertNotIn(top, banned, "{0} imports {1}".format(name, top))

    def test_no_secret_or_api_key(self):
        banned_ids = ("api_key", "apikey", "secret", "token", "password", "access_key")
        for name, src in _sec_sources():
            # No literal environ/getenv access, no hardcoded personal email.
            low = src.lower()
            self.assertNotIn("os.environ", src, "{0} reads os.environ".format(name))
            self.assertNotIn("getenv", low, "{0} calls getenv".format(name))
            self.assertNotIn("shreenik", low, "{0} hardcodes personal email".format(name))
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotEqual(
                        node.attr, "environ", "{0} reads os.environ".format(name)
                    )
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, ("getenv",), "{0} calls getenv".format(name))
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            tlow = tgt.id.lower()
                            for b in banned_ids:
                                self.assertNotIn(
                                    b, tlow, "{0} assigns secret-like {1}".format(name, tgt.id)
                                )

    def test_no_email_or_secret_in_fixtures(self):
        for name in os.listdir(_FIXTURE_DIR):
            with open(os.path.join(_FIXTURE_DIR, name), "r") as fh:
                blob = fh.read().lower()
            self.assertNotIn("shreenik", blob)
            self.assertNotIn("api_key", blob)
            self.assertNotIn("secret", blob)


if __name__ == "__main__":
    unittest.main()
