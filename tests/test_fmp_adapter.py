"""Tests for the FMP parsing adapter (IMPLEMENTATION-009C).

Fixture-based only -- NO network, NO API keys / secrets, NO investment reasoning.
Local FMP-shaped JSON fixtures are loaded via ``open()`` (never fetched) and parsed
into CONVENIENCE evidence records. FMP is the paid MVP convenience API: its
authority is ``convenience`` and a canonical SEC filing ALWAYS wins a conflict.
Supported categories (financials, news / press releases) map to Tattva Observations
ONLY; OHLCV / profile / ownership mapping is DEFERRED (no Tattva vocabulary). The
optional live client is never exercised with a real transport / key.
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
    sec_source,
    FMP_PROVIDER,
    FMP_SOURCE_NAME,
    fmp_source,
    parse_fmp_profile,
    parse_fmp_income_statement,
    parse_fmp_ohlcv,
    parse_fmp_news,
    parse_fmp_ownership,
    map_fmp_record,
    mapping_deferred_reason,
    MappingDeferredError,
    FmpClient,
)

# Reasoning-conclusion object types the mapper must NEVER produce.
from genesis.opportunity_hypothesis import OpportunityHypothesis
from prometheus.investment_thesis import InvestmentThesis
from prometheus.investment_action import InvestmentAction
from personal_cio.personalized_action import PersonalizedAction
from execution_manual.manual_execution_intent import ManualExecutionIntent


_FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "fmp")


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r") as fh:
        return json.load(fh)


def _profile():
    return _load("profile_iren.json")


def _income():
    return _load("income_statement_iren.json")


def _ohlcv():
    return _load("historical_ohlcv_iren.json")


def _news():
    return _load("news_iren.json")


def _ownership():
    return _load("ownership_iren.json")


def _by_type(records, normalized_type):
    for r in records:
        if r.normalized_type == normalized_type:
            return r
    raise AssertionError("no record with normalized_type {0!r}".format(normalized_type))


# --------------------------------------------------------------------------- #
# Parsing + determinism.                                                       #
# --------------------------------------------------------------------------- #

class ParsingDeterminismTests(unittest.TestCase):
    def test_profile_parses_deterministically(self):
        r1 = parse_fmp_profile(_profile(), now=0)
        r2 = parse_fmp_profile(_profile(), now=0)
        self.assertTrue(r1.records)
        self.assertEqual([r.id for r in r1.records], [r.id for r in r2.records])

    def test_income_statement_parses_deterministically(self):
        r1 = parse_fmp_income_statement(_income(), now=0)
        r2 = parse_fmp_income_statement(_income(), now=0)
        self.assertTrue(r1.records)
        self.assertEqual([r.id for r in r1.records], [r.id for r in r2.records])

    def test_ohlcv_parses_deterministically(self):
        r1 = parse_fmp_ohlcv(_ohlcv(), now=0)
        r2 = parse_fmp_ohlcv(_ohlcv(), now=0)
        self.assertEqual(len(r1.records), 3)
        self.assertEqual([r.id for r in r1.records], [r.id for r in r2.records])

    def test_news_parses_deterministically(self):
        r1 = parse_fmp_news(_news(), now=0)
        r2 = parse_fmp_news(_news(), now=0)
        self.assertTrue(r1.records)
        self.assertEqual([r.id for r in r1.records], [r.id for r in r2.records])


# --------------------------------------------------------------------------- #
# Convenience authority / class / provider + latest-vs-prior.                  #
# --------------------------------------------------------------------------- #

class AuthorityTests(unittest.TestCase):
    def test_fmp_records_are_convenience_paid_api(self):
        for res in (
            parse_fmp_profile(_profile(), now=0),
            parse_fmp_income_statement(_income(), now=0),
            parse_fmp_news(_news(), now=0),
            parse_fmp_ownership(_ownership(), now=0),
        ):
            for rec in res.records:
                self.assertEqual(rec.source_authority, "convenience")
                self.assertEqual(rec.source_class, "paid_api")
                self.assertEqual(rec.source.provider, FMP_PROVIDER)
                self.assertEqual(rec.source.source_name, FMP_SOURCE_NAME)

    def test_ohlcv_records_are_market_data_convenience(self):
        res = parse_fmp_ohlcv(_ohlcv(), now=0)
        for rec in res.records:
            self.assertEqual(rec.source_class, "market_data")
            self.assertEqual(rec.source_authority, "convenience")
            self.assertEqual(rec.source.provider, FMP_PROVIDER)

    def test_income_latest_period_is_metric_value_prior_is_prior(self):
        res = parse_fmp_income_statement(_income(), now=0)
        rev = _by_type(res.records, "fmp_financial_revenue")
        # Latest period (2026-03-31) -> metric_value; prior (2025-12-31) -> prior_value.
        self.assertEqual(rev.extracted_fields["metric_value"], 118000000)
        self.assertEqual(rev.extracted_fields["prior_value"], 99000000)
        self.assertEqual(rev.extracted_fields["financial_metric"], "revenue")
        self.assertEqual(rev.period_end, "2026-03-31")

    def test_income_margin_ratio_normalized(self):
        res = parse_fmp_income_statement(_income(), now=0)
        gm = _by_type(res.records, "fmp_financial_gross_margin")
        self.assertEqual(gm.extracted_fields["financial_metric"], "gross_margin")
        self.assertEqual(gm.extracted_fields["metric_unit"], "ratio")

    def test_single_period_income_has_no_fabricated_prior(self):
        one = [dict(_income()[0])]
        res = parse_fmp_income_statement(one, now=0)
        rev = _by_type(res.records, "fmp_financial_revenue")
        self.assertEqual(rev.extracted_fields["metric_value"], 118000000)
        self.assertNotIn("prior_value", rev.extracted_fields)
        self.assertTrue(any("one period" in w for w in res.warnings))


# --------------------------------------------------------------------------- #
# Missing-field discipline + provenance.                                       #
# --------------------------------------------------------------------------- #

class MissingFieldTests(unittest.TestCase):
    def test_missing_income_metrics_warn_not_fabricated(self):
        res = parse_fmp_income_statement(_income(), now=0)
        joined = " ".join(res.warnings)
        # cash / debt / capex absent from the fixture -> warnings, no records.
        self.assertIn("cash", joined)
        self.assertIn("debt", joined)
        self.assertFalse(any(r.normalized_type == "fmp_financial_cash" for r in res.records))

    def test_missing_profile_field_warns(self):
        stripped = [dict(_profile()[0])]
        del stripped[0]["website"]
        res = parse_fmp_profile(stripped, now=0)
        self.assertTrue(any("website" in w for w in res.warnings))
        rec = res.records[0]
        self.assertNotIn("website", rec.extracted_fields)

    def test_empty_inputs_produce_errors_not_silence(self):
        for parser, payload in (
            (parse_fmp_profile, []),
            (parse_fmp_income_statement, []),
            (parse_fmp_ohlcv, []),
            (parse_fmp_news, []),
            (parse_fmp_ownership, []),
        ):
            res = parser(payload, now=0)
            self.assertFalse(res.records)
            self.assertTrue(res.errors)
            self.assertFalse(res.complete)

    def test_normalized_records_bind_their_raw(self):
        for res in (
            parse_fmp_income_statement(_income(), now=0),
            parse_fmp_news(_news(), now=0),
            parse_fmp_ohlcv(_ohlcv(), now=0),
        ):
            for rec in res.records:
                kinds = [r.kind for r in rec.provenance.sources]
                self.assertIn("RawEvidenceRecord", kinds)
                self.assertIsNotNone(rec.source_record_ref)


# --------------------------------------------------------------------------- #
# Mapper: supported FMP records -> Tattva Observations ONLY.                   #
# --------------------------------------------------------------------------- #

class MapperTests(unittest.TestCase):
    def _assert_observation_only(self, obs):
        self.assertIsInstance(obs, Observation)
        self.assertNotIsInstance(obs, OpportunityHypothesis)
        self.assertNotIsInstance(obs, InvestmentThesis)
        self.assertNotIsInstance(obs, InvestmentAction)
        self.assertNotIsInstance(obs, PersonalizedAction)
        self.assertNotIsInstance(obs, ManualExecutionIntent)

    def test_fmp_financial_maps_to_financial_report_observation(self):
        res = parse_fmp_income_statement(_income(), now=0)
        rev = _by_type(res.records, "fmp_financial_revenue")
        obs, _ = map_fmp_record(rev, domain="ai-infrastructure", now=0)
        self._assert_observation_only(obs)
        self.assertEqual(obs.content["source_type"], "financial_report")
        self.assertEqual(obs.content["source_authority"], "convenience")
        self.assertEqual(obs.content["source_reliability"], "moderate")

    def test_fmp_news_maps_to_news_excerpt_probable(self):
        res = parse_fmp_news(_news(), now=0)
        # The contract press-release item carries a catalyst; classified as a PR.
        pr = _by_type(res.records, "fmp_press_release")
        obs, _ = map_fmp_record(pr, domain="ai-infrastructure", now=0)
        self._assert_observation_only(obs)
        self.assertEqual(obs.content["source_type"], "press_release")
        self.assertEqual(obs.content["catalyst_status"], "probable")

        # A plain news item (no PR marker) routes to news_excerpt.
        news = _by_type(res.records, "fmp_news")
        obs2, _ = map_fmp_record(news, domain="ai-infrastructure", now=0)
        self._assert_observation_only(obs2)
        self.assertEqual(obs2.content["source_type"], "news_excerpt")

    def test_fmp_news_catalyst_only_from_keyword_or_metadata(self):
        res = parse_fmp_news(_news(), now=0)
        pr = _by_type(res.records, "fmp_press_release")
        # "contract" keyword -> conservative catalyst_type + positive direction.
        self.assertEqual(pr.extracted_fields.get("catalyst_type"), "contract_win")
        self.assertEqual(pr.extracted_fields.get("expected_direction"), "positive")
        # The plain operational-update item has no keyword -> no catalyst fields.
        news = _by_type(res.records, "fmp_news")
        self.assertNotIn("catalyst_type", news.extracted_fields)
        self.assertNotIn("expected_direction", news.extracted_fields)


# --------------------------------------------------------------------------- #
# Deferred mapping: OHLCV / profile / ownership are NOT forced.                #
# --------------------------------------------------------------------------- #

class DeferredMappingTests(unittest.TestCase):
    def test_ohlcv_mapping_is_deferred(self):
        rec = parse_fmp_ohlcv(_ohlcv(), now=0).records[0]
        self.assertIsNotNone(mapping_deferred_reason(rec))
        with self.assertRaises(MappingDeferredError):
            map_fmp_record(rec, domain="ai-infrastructure", now=0)

    def test_profile_mapping_is_deferred(self):
        rec = parse_fmp_profile(_profile(), now=0).records[0]
        self.assertIsNotNone(mapping_deferred_reason(rec))
        with self.assertRaises(MappingDeferredError):
            map_fmp_record(rec, domain="ai-infrastructure", now=0)

    def test_ownership_mapping_is_deferred(self):
        rec = parse_fmp_ownership(_ownership(), now=0).records[0]
        self.assertIsNotNone(mapping_deferred_reason(rec))
        with self.assertRaises(MappingDeferredError):
            map_fmp_record(rec, domain="ai-infrastructure", now=0)

    def test_supported_records_are_not_deferred(self):
        rev = _by_type(parse_fmp_income_statement(_income(), now=0).records, "fmp_financial_revenue")
        news = parse_fmp_news(_news(), now=0).records[0]
        self.assertIsNone(mapping_deferred_reason(rev))
        self.assertIsNone(mapping_deferred_reason(news))


# --------------------------------------------------------------------------- #
# Conflict: canonical SEC beats convenience FMP; FMP fills gaps only.          #
# --------------------------------------------------------------------------- #

class ConflictTests(unittest.TestCase):
    """Family-scoped, PERIOD-AWARE cross-source arbitration with REALISTIC shapes.

    SEC and FMP deliberately carry DIFFERENT normalized_types (``sec_xbrl_*`` vs
    ``fmp_financial_*``) for the SAME ``financial_metric`` -- exactly what the real
    adapters emit. FMP records are the REAL output of ``parse_fmp_income_statement``
    (revenue in USD @ period_end 2026-03-31; shares in "shares"). The resolver keys
    on ``(subject, "financial_fact", metric, period_end, unit)`` so same-period facts
    arbitrate (canonical wins) while different periods never falsely conflict.
    """

    _PERIOD = "2026-03-31"  # the latest period in the FMP income fixture

    def _fmp(self, financial_metric):
        # REAL adapter output; subject is the FMP symbol ("IREN").
        return _by_type(
            parse_fmp_income_statement(_income(), now=0).records,
            "fmp_financial_{0}".format(financial_metric),
        )

    def _sec_financial(self, subject, sec_normalized_type, metric, value, unit, period_end):
        # Canonical SEC-style financial record: a DIFFERENT normalized_type
        # (sec_xbrl_*) but SAME metric/period/unit as the FMP record it competes with.
        raw = make_raw_evidence_record(
            sec_source(source_class="official_filing", source_ref="accn"),
            subject=subject, ticker="IREN", raw_type="companyfacts",
            raw_payload={metric: value}, retrieved_at="t", as_of="d", now=0,
        )
        return make_normalized_evidence_record(
            raw, normalized_type=sec_normalized_type,
            extracted_fields={"financial_metric": metric, "metric_value": value, "metric_unit": unit},
            period_end=period_end, evidence_quality=0.9, confidence=0.9, now=0,
        )

    def _fallback_financial(self, subject, metric, value, unit, period_end):
        # A yfinance FALLBACK record sharing the same financial key.
        src = EvidenceSource(
            source_name="yfinance", source_authority="fallback",
            source_class="free_api", provider="yfinance",
        )
        raw = make_raw_evidence_record(
            src, subject=subject, ticker="IREN", raw_type="history",
            raw_payload={metric: value}, retrieved_at="t", as_of="d", now=0,
        )
        return make_normalized_evidence_record(
            raw, normalized_type="yf_history_{0}".format(metric),
            extracted_fields={"financial_metric": metric, "metric_value": value, "metric_unit": unit},
            period_end=period_end, evidence_quality=0.4, confidence=0.4, now=0,
        )

    # Case 1 -- SEC beats FMP, SAME period, DIFFERING normalized_types.
    def test_sec_canonical_revenue_beats_fmp_convenience(self):
        fmp = self._fmp("revenue")  # fmp_financial_revenue, USD, 118M, 2026-03-31
        sec = self._sec_financial(
            fmp.subject, "sec_xbrl_revenue", "revenue", 120000000, "USD", self._PERIOD
        )
        self.assertNotEqual(sec.normalized_type, fmp.normalized_type)  # realistic
        resolved, warns = resolve_conflicts((sec, fmp))
        key = (fmp.subject, "financial_fact", "revenue", self._PERIOD, "USD")
        self.assertEqual(resolved[key], 120000000)  # SEC canonical wins
        self.assertTrue(any("conflict" in w for w in warns))
        self.assertEqual(fmp.source_authority, "convenience")  # FMP stays convenience

    # Case 6 -- the warning names BOTH sources AND BOTH authorities.
    def test_conflict_warning_names_both_sources_and_authorities(self):
        fmp = self._fmp("revenue")
        sec = self._sec_financial(
            fmp.subject, "sec_xbrl_revenue", "revenue", 120000000, "USD", self._PERIOD
        )
        _, warns = resolve_conflicts((sec, fmp))
        self.assertTrue(warns)
        w = warns[0]
        self.assertIn("SEC EDGAR", w)
        self.assertIn("FMP", w)
        self.assertIn("canonical", w)
        self.assertIn("convenience", w)

    # Case 2 -- NO false conflict across different periods; BOTH retained.
    def test_no_false_conflict_across_periods(self):
        fmp = self._fmp("revenue")  # quarterly, period_end 2026-03-31, 118M
        sec_annual = self._sec_financial(
            fmp.subject, "sec_xbrl_revenue", "revenue", 200000000, "USD", "2025-12-31"
        )
        resolved, warns = resolve_conflicts((sec_annual, fmp))
        q_key = (fmp.subject, "financial_fact", "revenue", "2026-03-31", "USD")
        a_key = (fmp.subject, "financial_fact", "revenue", "2025-12-31", "USD")
        self.assertEqual(resolved[q_key], 118000000)   # FMP quarterly retained
        self.assertEqual(resolved[a_key], 200000000)   # SEC annual retained
        self.assertEqual(warns, ())                    # different period -> no conflict

    # Case 3 -- shares_outstanding: SEC beats FMP for the SAME date/unit.
    def test_sec_canonical_shares_beats_fmp_convenience(self):
        fmp = self._fmp("shares_outstanding")  # 209M, unit "shares"
        sec = self._sec_financial(
            fmp.subject, "sec_xbrl_shares_outstanding", "shares_outstanding",
            210000000, "shares", self._PERIOD,
        )
        self.assertNotEqual(sec.normalized_type, fmp.normalized_type)
        resolved, warns = resolve_conflicts((sec, fmp))
        key = (fmp.subject, "financial_fact", "shares_outstanding", self._PERIOD, "shares")
        self.assertEqual(resolved[key], 210000000)  # SEC canonical wins
        self.assertTrue(any("conflict" in w for w in warns))

    # Case 4 -- FMP fills a gap when no canonical record exists.
    def test_fmp_fills_field_when_sec_absent(self):
        fmp = self._fmp("revenue")
        resolved, warns = resolve_conflicts((fmp,))
        key = (fmp.subject, "financial_fact", "revenue", self._PERIOD, "USD")
        self.assertEqual(resolved[key], 118000000)
        self.assertEqual(warns, ())
        self.assertEqual(fmp.source_authority, "convenience")

    # Case 5 -- yfinance fallback can never overwrite FMP convenience or SEC canonical.
    def test_fallback_cannot_overwrite_convenience_or_canonical(self):
        fmp = self._fmp("revenue")  # convenience, 118M
        yf = self._fallback_financial(fmp.subject, "revenue", 111000000, "USD", self._PERIOD)
        key = (fmp.subject, "financial_fact", "revenue", self._PERIOD, "USD")

        # Fallback vs convenience -> FMP convenience wins.
        resolved, warns = resolve_conflicts((fmp, yf))
        self.assertEqual(resolved[key], 118000000)
        self.assertTrue(any("conflict" in w for w in warns))

        # Fallback + convenience + canonical -> SEC canonical wins.
        sec = self._sec_financial(
            fmp.subject, "sec_xbrl_revenue", "revenue", 120000000, "USD", self._PERIOD
        )
        resolved2, _ = resolve_conflicts((yf, fmp, sec))
        self.assertEqual(resolved2[key], 120000000)

    # Order-independence: canonical wins regardless of tuple order.
    def test_fmp_never_overwrites_canonical(self):
        fmp = self._fmp("revenue")  # 118M
        sec = self._sec_financial(
            fmp.subject, "sec_xbrl_revenue", "revenue", 120000000, "USD", self._PERIOD
        )
        resolved, _ = resolve_conflicts((fmp, sec))  # order should not matter
        key = (fmp.subject, "financial_fact", "revenue", self._PERIOD, "USD")
        self.assertEqual(resolved[key], 120000000)  # canonical wins regardless of order


# --------------------------------------------------------------------------- #
# Live client: inert, requires api_key AND transport, never hits the wire.     #
# --------------------------------------------------------------------------- #

class LiveClientTests(unittest.TestCase):
    def test_fmp_client_requires_api_key(self):
        calls = []

        def transport(url, params):  # should never be called
            calls.append(url)
            return b"[]"

        client = FmpClient(api_key=None, transport=transport)
        self.assertIsNone(client.api_key)
        for fetch in (client.fetch_profile, client.fetch_income_statement, client.fetch_historical):
            with self.assertRaises(ValueError):
                fetch("IREN")
        self.assertEqual(calls, [])  # transport never reached

    def test_fmp_client_requires_transport(self):
        # With a key but no transport, a fetch still raises before any network.
        client = FmpClient(api_key="runtime-key", transport=None)
        with self.assertRaises(ValueError):
            client.fetch_profile("IREN")

    def test_default_fmp_client_cannot_reach_wire(self):
        default_client = FmpClient()
        self.assertIsNone(default_client.api_key)
        with self.assertRaises(ValueError):
            default_client.fetch_income_statement("IREN")

    def test_fmp_client_uses_injected_transport_only(self):
        seen = []

        def fake_transport(url, params):
            seen.append((url, dict(params)))
            return b"[]"

        client = FmpClient(api_key="runtime-key", transport=fake_transport)
        out = client.fetch_profile("IREN")
        self.assertEqual(out, b"[]")
        self.assertEqual(len(seen), 1)
        url, params = seen[0]
        self.assertIn("financialmodelingprep.com", url)
        self.assertIn("IREN", url)
        self.assertEqual(params["apikey"], "runtime-key")


# --------------------------------------------------------------------------- #
# Static guards over the FMP modules.                                         #
# --------------------------------------------------------------------------- #

_PKG_DIR = os.path.join(_SRC, "evidence_ingestion")
_FMP_MODULES = ("fmp.py", "fmp_client.py")


def _fmp_sources():
    for name in _FMP_MODULES:
        with open(os.path.join(_PKG_DIR, name), "r") as fh:
            yield name, fh.read()


class GuardTests(unittest.TestCase):
    def test_no_top_level_or_hidden_network_import(self):
        # ast.walk visits Import / ImportFrom nodes at ANY nesting depth, so this
        # also catches a lazy/nested import inside a function body.
        banned = {"requests", "urllib", "http", "socket", "aiohttp", "httpx", "importlib"}
        for name, src in _fmp_sources():
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        top = a.name.split(".")[0]
                        self.assertNotIn(top, banned, "{0} imports {1}".format(name, top))
                elif isinstance(node, ast.ImportFrom):
                    top = (node.module or "").split(".")[0]
                    self.assertNotIn(top, banned, "{0} imports {1}".format(name, top))

    def test_no_secret_env_or_literal_key(self):
        # The FMP client legitimately takes an ``api_key`` PARAMETER / attribute
        # (an explicit runtime value). So this guard does NOT ban the identifier;
        # it precisely flags (a) any environment / secret LOOKUP, and (b) any
        # LITERAL string secret VALUE assigned to a secret-named target or used as
        # a secret-named parameter default -- never obscuring code to dodge it.
        secret_names = ("api_key", "apikey", "secret", "token", "password", "access_key")
        for name, src in _fmp_sources():
            self.assertNotIn("os.environ", src, "{0} reads os.environ".format(name))
            self.assertNotIn("shreenik", src.lower(), "{0} hardcodes personal email".format(name))
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotEqual(node.attr, "environ", "{0} reads os.environ".format(name))
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, ("getenv",), "{0} calls getenv".format(name))
                # AST-level ``getenv(...)`` / ``getattr(os, ...)`` bypass detection
                # (matches real calls, not prose in a docstring).
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "getenv":
                        self.fail("{0} calls getenv".format(name))
                    if isinstance(fn, ast.Attribute) and fn.attr == "getenv":
                        self.fail("{0} calls os.getenv".format(name))
                    if isinstance(fn, ast.Name) and fn.id == "getattr" and node.args:
                        first = node.args[0]
                        self.assertFalse(
                            isinstance(first, ast.Name) and first.id == "os",
                            "{0} uses getattr(os, ...)".format(name),
                        )
                # (a) LITERAL secret value assigned to a secret-named target.
                if isinstance(node, ast.Assign):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and node.value.value:
                        for tgt in node.targets:
                            tname = ""
                            if isinstance(tgt, ast.Name):
                                tname = tgt.id.lower()
                            elif isinstance(tgt, ast.Attribute):
                                tname = tgt.attr.lower()
                            for s in secret_names:
                                self.assertNotIn(
                                    s, tname,
                                    "{0} assigns a literal string to secret-like {1}".format(name, tname),
                                )
                # (b) LITERAL secret value as a secret-named parameter default.
                if isinstance(node, (ast.FunctionDef,)):
                    args = node.args
                    defaults = list(args.defaults)
                    pos = args.args[len(args.args) - len(defaults):] if defaults else []
                    for arg, default in zip(pos, defaults):
                        if isinstance(default, ast.Constant) and isinstance(default.value, str) and default.value:
                            aname = arg.arg.lower()
                            for s in secret_names:
                                self.assertNotIn(
                                    s, aname,
                                    "{0} defaults secret-like param {1} to a literal".format(name, aname),
                                )

    def test_no_email_or_secret_in_fixtures(self):
        for fname in os.listdir(_FIXTURE_DIR):
            with open(os.path.join(_FIXTURE_DIR, fname), "r") as fh:
                blob = fh.read().lower()
            self.assertNotIn("shreenik", blob)
            self.assertNotIn("api_key", blob)
            self.assertNotIn("secret", blob)


if __name__ == "__main__":
    unittest.main()
