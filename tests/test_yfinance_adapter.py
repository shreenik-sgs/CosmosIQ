"""Tests for the yfinance FALLBACK parsing adapter (IMPLEMENTATION-009D).

Fixture-based only -- NO network, NO yfinance-package import, NO API keys / secrets,
NO investment reasoning. Local yfinance-shaped JSON fixtures are loaded via ``open()``
(never fetched, never through the yfinance package) and parsed into FALLBACK evidence
records. yfinance is a free prototype / fallback / sanity-check source: its authority
is ``fallback`` (the lowest above rumor). It NEVER overwrites a SEC canonical fact or
an FMP convenience row -- it only ever fills a gap both leave. yfinance has NO Tattva
signal vocabulary, so ALL its mappings are DEFERRED: it produces evidence records only,
never an Observation. The optional live client is never exercised with a real source.
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
    resolve_conflicts,
    sec_source,
    parse_fmp_ohlcv,
    MappingDeferredError,
    YF_PROVIDER,
    YF_SOURCE_NAME,
    YF_RESEARCH_NOTE,
    yf_source,
    parse_yfinance_history,
    parse_yfinance_quote,
    map_yfinance_record,
    yf_mapping_deferred_reason,
    YFinanceClient,
)

# Reasoning-conclusion object types yfinance must NEVER produce.
from genesis.opportunity_hypothesis import OpportunityHypothesis
from prometheus.investment_thesis import InvestmentThesis
from prometheus.investment_action import InvestmentAction
from personal_cio.personalized_action import PersonalizedAction
from execution_manual.manual_execution_intent import ManualExecutionIntent


_FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "yfinance")


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r") as fh:
        return json.load(fh)


def _history():
    return _load("history_iren.json")


def _quote():
    return _load("quote_iren.json")


def _by_type(records, normalized_type):
    for r in records:
        if r.normalized_type == normalized_type:
            return r
    raise AssertionError("no record with normalized_type {0!r}".format(normalized_type))


def _bar_for_date(records, date):
    for r in records:
        if r.normalized_type == "yf_ohlcv" and r.extracted_fields.get("date") == date:
            return r
    raise AssertionError("no yf_ohlcv bar for {0}".format(date))


# --------------------------------------------------------------------------- #
# Parsing + determinism.                                                       #
# --------------------------------------------------------------------------- #

class ParsingDeterminismTests(unittest.TestCase):
    def test_history_parses_deterministically(self):
        r1 = parse_yfinance_history(_history(), now=0)
        r2 = parse_yfinance_history(_history(), now=0)
        self.assertEqual(len(r1.records), 3)
        self.assertEqual([r.id for r in r1.records], [r.id for r in r2.records])

    def test_quote_parses_deterministically(self):
        r1 = parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31")
        r2 = parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31")
        self.assertTrue(r1.records)
        self.assertEqual([r.id for r in r1.records], [r.id for r in r2.records])

    def test_history_adj_close_dividends_splits_parsed(self):
        recs = parse_yfinance_history(_history(), now=0).records
        # Adj Close present on the latest bar.
        latest = _bar_for_date(recs, "2026-06-26")
        self.assertEqual(latest.extracted_fields["adj_close"], 21.10)
        self.assertEqual(latest.extracted_fields["dividends"], 0.15)
        self.assertEqual(latest.extracted_fields["close"], 21.10)
        self.assertEqual(latest.extracted_fields["volume"], 15200000)
        # A stock-split row is carried verbatim.
        split_bar = _bar_for_date(recs, "2026-06-24")
        self.assertEqual(split_bar.extracted_fields["stock_splits"], 2.0)

    def test_quote_profile_fields_parsed(self):
        recs = parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31").records
        q = _by_type(recs, "yf_quote")
        f = q.extracted_fields
        self.assertEqual(f["current_price"], 21.10)
        self.assertEqual(f["previous_close"], 20.05)
        self.assertEqual(f["market_cap"], 4200000000)
        self.assertEqual(f["sector"], "Technology")
        self.assertEqual(f["industry"], "Data Center Infrastructure")
        self.assertEqual(f["currency"], "USD")
        self.assertEqual(f["exchange"], "NASDAQ")
        # NO inferred moat / TAM / thesis / quality / crowding / recognition.
        for banned in ("moat", "tam", "thesis", "quality", "crowding", "recognition", "signal"):
            self.assertNotIn(banned, f)

    def test_quote_emits_shares_outstanding_financial_fact(self):
        recs = parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31").records
        sh = _by_type(recs, "yf_quote_shares_outstanding")
        self.assertEqual(sh.extracted_fields["financial_metric"], "shares_outstanding")
        self.assertEqual(sh.extracted_fields["metric_value"], 210000000)
        self.assertEqual(sh.extracted_fields["metric_unit"], "shares")
        self.assertEqual(sh.period_end, "2026-03-31")


# --------------------------------------------------------------------------- #
# Fallback authority / class / provider / research-only note.                  #
# --------------------------------------------------------------------------- #

class AuthorityTests(unittest.TestCase):
    def test_ohlcv_records_are_market_data_fallback(self):
        res = parse_yfinance_history(_history(), now=0)
        self.assertTrue(res.records)
        for rec in res.records:
            self.assertEqual(rec.source_authority, "fallback")
            self.assertEqual(rec.source_class, "market_data")
            self.assertEqual(rec.source.provider, YF_PROVIDER)
            self.assertEqual(rec.source.source_name, YF_SOURCE_NAME)
            self.assertEqual(rec.source.license_note, YF_RESEARCH_NOTE)

    def test_quote_records_are_free_api_fallback(self):
        res = parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31")
        self.assertTrue(res.records)
        for rec in res.records:
            self.assertEqual(rec.source_authority, "fallback")
            self.assertEqual(rec.source_class, "free_api")
            self.assertEqual(rec.source.provider, YF_PROVIDER)
            self.assertIn("research", rec.source.license_note.lower())

    def test_source_builder_pins_fallback_even_for_market_data(self):
        # market_data alone would default to convenience; yfinance pins fallback.
        self.assertEqual(yf_source(source_class="market_data").source_authority, "fallback")
        self.assertEqual(yf_source(source_class="free_api").source_authority, "fallback")


# --------------------------------------------------------------------------- #
# Missing-field discipline + provenance.                                       #
# --------------------------------------------------------------------------- #

class MissingFieldTests(unittest.TestCase):
    def test_missing_ohlcv_field_warns_not_fabricated(self):
        payload = _history()
        del payload["IREN"]["history"][0]["Open"]
        res = parse_yfinance_history(payload, now=0)
        self.assertTrue(any("Open" in w for w in res.warnings))
        self.assertFalse(res.complete)
        bar = _bar_for_date(res.records, "2026-06-24")
        self.assertNotIn("open", bar.extracted_fields)  # not fabricated

    def test_missing_shares_outstanding_warns_no_record(self):
        info = dict(_quote())
        del info["sharesOutstanding"]
        res = parse_yfinance_quote(info, now=0, as_of="2026-03-31")
        self.assertTrue(any("sharesOutstanding" in w for w in res.warnings))
        self.assertFalse(any(r.normalized_type == "yf_quote_shares_outstanding" for r in res.records))
        # The descriptive quote record is still produced.
        self.assertTrue(any(r.normalized_type == "yf_quote" for r in res.records))

    def test_empty_inputs_produce_errors_not_silence(self):
        for parser, payload in (
            (parse_yfinance_history, []),
            (parse_yfinance_history, {}),
            (parse_yfinance_quote, {}),
            (parse_yfinance_quote, None),
        ):
            res = parser(payload, now=0)
            self.assertFalse(res.records)
            self.assertTrue(res.errors)
            self.assertFalse(res.complete)

    def test_normalized_records_bind_their_raw(self):
        for res in (
            parse_yfinance_history(_history(), now=0),
            parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31"),
        ):
            for rec in res.records:
                kinds = [r.kind for r in rec.provenance.sources]
                self.assertIn("RawEvidenceRecord", kinds)
                self.assertIsNotNone(rec.source_record_ref)


# --------------------------------------------------------------------------- #
# Factual mapping (009F): yfinance maps to NEUTRAL FACTUAL Observations,        #
# stays FALLBACK, and adds NO confidence -- never a signal.                     #
# --------------------------------------------------------------------------- #

_BANNED_INFERENCE = (
    "ema", "vwap", "breakout", "compression", "relative_strength", "rsi", "macd",
    "slope", "trend", "momentum", "accumulation", "crowding", "under_recognition",
    "obviousness", "sponsorship", "moat", "tam", "thesis", "signal", "buy", "sell",
)


def _assert_no_inference(testcase, obs):
    # No catalyst / direction / change was inferred onto a factual observation.
    for k in ("catalyst_type", "catalyst_status", "expected_direction",
              "observed_change"):
        testcase.assertIsNone(obs.content.get(k))
    # The carried raw facts + the neutral excerpt contain NO technical / market-
    # recognition / investment term (structural schema keys are not inspected).
    ff = obs.content.get("factual_fields") or {}
    blob = " ".join(str(k).lower() for k in ff.keys())
    blob += " " + " ".join(str(v).lower() for v in ff.values())
    blob += " " + str(obs.content.get("excerpt", "")).lower()
    for banned in _BANNED_INFERENCE:
        testcase.assertNotIn(banned, blob)


class FactualMappingTests(unittest.TestCase):
    def test_ohlcv_maps_to_factual_ohlcv_bar_fallback(self):
        rec = parse_yfinance_history(_history(), now=0).records[0]
        self.assertIsNone(yf_mapping_deferred_reason(rec))  # no longer deferred
        obs, _ = map_yfinance_record(rec, domain="ai-infrastructure", now=0)
        self.assertIsInstance(obs, Observation)
        self.assertEqual(obs.content["source_type"], "ohlcv_bar")
        # yfinance factual observations stay FALLBACK / low reliability.
        self.assertEqual(obs.content["source_authority"], "fallback")
        self.assertEqual(obs.content["source_reliability"], "low")
        _assert_no_inference(self, obs)

    def test_quote_maps_to_factual_quote_snapshot(self):
        rec = _by_type(parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31").records,
                       "yf_quote")
        self.assertIsNone(yf_mapping_deferred_reason(rec))
        obs, _ = map_yfinance_record(rec, domain="ai-infrastructure", now=0)
        self.assertEqual(obs.content["source_type"], "quote_snapshot")
        self.assertEqual(obs.content["source_authority"], "fallback")
        ff = obs.content["factual_fields"]
        self.assertEqual(ff["current_price"], 21.10)
        self.assertEqual(ff["previous_close"], 20.05)
        _assert_no_inference(self, obs)

    def test_shares_outstanding_maps_to_factual_share_count(self):
        rec = _by_type(parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31").records,
                       "yf_quote_shares_outstanding")
        obs, _ = map_yfinance_record(rec, domain="ai-infrastructure", now=0)
        self.assertEqual(obs.content["source_type"], "shares_outstanding_observation")
        # financial_metric retained so cross-source arbitration still ranks SEC/FMP over yf.
        self.assertEqual(obs.content["financial_metric"], "shares_outstanding")
        self.assertEqual(obs.content["source_authority"], "fallback")
        _assert_no_inference(self, obs)

    def test_yfinance_factual_observation_adds_no_confidence(self):
        # A real (SEC-style) signal observation alone vs the same PLUS a yfinance
        # factual observation: identical signals / direction / significance / confidence.
        from reality_intelligence.source_observation import make_source_observation
        from reality_intelligence.intelligence_assessment import (
            generate_intelligence_assessment,
        )
        real = make_source_observation(
            source_type="financial_report", domain="ai-infrastructure", entity="IREN",
            excerpt="revenue grew", as_of="2026-03-31", financial_metric="revenue",
            metric_value=120.0, prior_value=100.0, source_reliability="high",
            actor="analyst", now=0,
        )
        yf_ohlcv = parse_yfinance_history(_history(), now=0).records[0]
        factual, _ = map_yfinance_record(yf_ohlcv, domain="ai-infrastructure", now=0)
        ia_real = generate_intelligence_assessment([real], domain="ai-infrastructure", now=0)
        ia_both = generate_intelligence_assessment([real, factual], domain="ai-infrastructure", now=0)
        self.assertEqual(len(ia_real.signals), len(ia_both.signals))
        self.assertEqual(ia_real.direction, ia_both.direction)
        self.assertEqual(ia_real.significance, ia_both.significance)
        self.assertEqual(ia_real.confidence, ia_both.confidence)
        # the factual observation IS recorded as grounding, just carries no signal.
        self.assertIn(factual.id, ia_both.grounding_observation_ids)
        self.assertIn(factual.id, ia_both.factual_observation_ids)

    def test_yfinance_parser_output_is_evidence_records(self):
        # The PARSER still yields evidence records (mapping to Observations is a
        # separate downstream step).
        recs = list(parse_yfinance_history(_history(), now=0).records)
        recs += list(parse_yfinance_quote(_quote(), now=0, as_of="2026-03-31").records)
        for rec in recs:
            self.assertIsInstance(rec, NormalizedEvidenceRecord)
            self.assertNotIsInstance(rec, Observation)
            self.assertNotIsInstance(rec, OpportunityHypothesis)
            self.assertNotIsInstance(rec, InvestmentThesis)
            self.assertNotIsInstance(rec, InvestmentAction)
            self.assertNotIsInstance(rec, PersonalizedAction)
            self.assertNotIsInstance(rec, ManualExecutionIntent)


# --------------------------------------------------------------------------- #
# Conflict: yfinance fallback ALWAYS loses; fills gaps only.                    #
# --------------------------------------------------------------------------- #

class ConflictTests(unittest.TestCase):
    """Family-scoped, period-aware arbitration with REALISTIC differing shapes.

    yfinance carries its own normalized_types (``yf_ohlcv`` / ``yf_quote_shares_
    outstanding``) -- never identical to SEC (``sec_xbrl_*``) or FMP (``fmp_ohlcv`` /
    ``fmp_financial_*``). It is fallback authority, so it loses every arbitration and
    only fills a gap SEC and FMP both leave.
    """

    _PERIOD = "2026-03-31"

    def _yf_shares(self, value=210000000, period_end=None):
        info = dict(_quote())
        info["sharesOutstanding"] = value
        recs = parse_yfinance_quote(
            info, now=0, as_of=period_end if period_end is not None else self._PERIOD
        ).records
        return _by_type(recs, "yf_quote_shares_outstanding")

    def _sec_shares(self, subject, value, period_end):
        raw = make_raw_evidence_record(
            sec_source(source_class="official_filing", source_ref="accn"),
            subject=subject, ticker="IREN", raw_type="companyfacts",
            raw_payload={"shares_outstanding": value}, retrieved_at="t", as_of="d", now=0,
        )
        return make_normalized_evidence_record(
            raw, normalized_type="sec_xbrl_shares_outstanding",
            extracted_fields={
                "financial_metric": "shares_outstanding",
                "metric_value": value, "metric_unit": "shares",
            },
            period_end=period_end, evidence_quality=0.9, confidence=0.9, now=0,
        )

    def _yf_bar(self, date):
        return _bar_for_date(parse_yfinance_history(_history(), now=0).records, date)

    def _fmp_bar(self, date, close):
        payload = {"symbol": "IREN", "historical": [{
            "date": date, "open": 1.0, "high": 2.0, "low": 0.5,
            "close": close, "adjClose": close, "volume": 100,
        }]}
        return parse_fmp_ohlcv(payload, now=0).records[0]

    # Case 1 -- SEC canonical shares beats yfinance fallback (same period/unit).
    def test_sec_canonical_shares_beats_yfinance_fallback(self):
        yf = self._yf_shares(210000000)
        sec = self._sec_shares(yf.subject, 209000000, self._PERIOD)
        self.assertNotEqual(sec.normalized_type, yf.normalized_type)  # realistic
        resolved, warns = resolve_conflicts((yf, sec))
        key = (yf.subject, "financial_fact", "shares_outstanding", self._PERIOD, "shares")
        self.assertEqual(resolved[key], 209000000)  # SEC canonical wins
        self.assertTrue(any("conflict" in w for w in warns))
        self.assertEqual(yf.source_authority, "fallback")

    # Case 2 -- FMP convenience OHLCV beats yfinance fallback OHLCV (same ticker/date/field).
    def test_fmp_ohlcv_beats_yfinance_ohlcv(self):
        yf = self._yf_bar("2026-06-26")     # yf_ohlcv, close 21.10, fallback
        fmp = self._fmp_bar("2026-06-26", 99.99)  # fmp_ohlcv, close 99.99, convenience
        self.assertNotEqual(yf.normalized_type, fmp.normalized_type)
        resolved, warns = resolve_conflicts((yf, fmp))
        key = ("IREN", "market_data", "2026-06-26", "close")
        self.assertEqual(resolved[key], 99.99)  # FMP convenience wins
        self.assertTrue(any("conflict" in w for w in warns))

    # Case 3 -- yfinance fills a gap when SEC and FMP are absent.
    def test_yfinance_fills_gap_when_sec_and_fmp_absent(self):
        yf = self._yf_shares(210000000)
        resolved, warns = resolve_conflicts((yf,))
        key = (yf.subject, "financial_fact", "shares_outstanding", self._PERIOD, "shares")
        self.assertEqual(resolved[key], 210000000)
        self.assertEqual(warns, ())

        yf_bar = self._yf_bar("2026-06-26")
        resolved2, warns2 = resolve_conflicts((yf_bar,))
        self.assertEqual(resolved2[("IREN", "market_data", "2026-06-26", "close")], 21.10)
        self.assertEqual(warns2, ())

    # Case 4 -- yfinance OHLCV does NOT conflict with a SEC filing fact (different families).
    def test_yfinance_ohlcv_does_not_conflict_with_sec_financial(self):
        yf_bar = self._yf_bar("2026-06-26")
        sec = self._sec_shares("IREN", 209000000, self._PERIOD)
        resolved, warns = resolve_conflicts((yf_bar, sec))
        self.assertEqual(warns, ())  # different family / key -> no conflict
        self.assertIn(("IREN", "market_data", "2026-06-26", "close"), resolved)
        self.assertIn(("IREN", "financial_fact", "shares_outstanding", self._PERIOD, "shares"), resolved)

    # Case 5 -- different periods never falsely conflict; both retained.
    def test_no_false_conflict_across_periods(self):
        yf_q = self._yf_shares(210000000, period_end="2026-03-31")
        sec_a = self._sec_shares(yf_q.subject, 300000000, "2025-12-31")
        resolved, warns = resolve_conflicts((yf_q, sec_a))
        q_key = (yf_q.subject, "financial_fact", "shares_outstanding", "2026-03-31", "shares")
        a_key = (yf_q.subject, "financial_fact", "shares_outstanding", "2025-12-31", "shares")
        self.assertEqual(resolved[q_key], 210000000)  # yfinance quarterly retained
        self.assertEqual(resolved[a_key], 300000000)  # SEC annual retained
        self.assertEqual(warns, ())

    # Case 6 -- the warning names BOTH source identities AND authorities.
    def test_conflict_warning_names_both_sources_and_authorities(self):
        yf = self._yf_shares(210000000)
        sec = self._sec_shares(yf.subject, 209000000, self._PERIOD)
        _, warns = resolve_conflicts((yf, sec))
        self.assertTrue(warns)
        w = warns[0]
        self.assertIn("SEC EDGAR", w)
        self.assertIn(YF_SOURCE_NAME, w)
        self.assertIn("canonical", w)
        self.assertIn("fallback", w)


# --------------------------------------------------------------------------- #
# Live client: inert, requires an injected source, never hits the wire.        #
# --------------------------------------------------------------------------- #

class LiveClientTests(unittest.TestCase):
    def test_default_client_cannot_reach_wire(self):
        client = YFinanceClient()
        for fetch in (client.fetch_history, client.fetch_quote):
            with self.assertRaises(ValueError):
                fetch("IREN")

    def test_client_delegates_to_injected_transport(self):
        seen = []

        def transport(symbol, kind):
            seen.append((symbol, kind))
            return {"ok": True}

        client = YFinanceClient(transport=transport)
        self.assertEqual(client.fetch_history("IREN"), {"ok": True})
        self.assertEqual(client.fetch_quote("IREN"), {"ok": True})
        self.assertEqual(seen, [("IREN", "history"), ("IREN", "quote")])

    def test_client_delegates_to_injected_ticker_client(self):
        class FakeTicker:
            def history(self, symbol):
                return {"h": symbol}

            def quote(self, symbol):
                return {"q": symbol}

        client = YFinanceClient(ticker_client=FakeTicker())
        self.assertEqual(client.fetch_history("IREN"), {"h": "IREN"})
        self.assertEqual(client.fetch_quote("IREN"), {"q": "IREN"})


# --------------------------------------------------------------------------- #
# Static guards over the yfinance modules.                                    #
# --------------------------------------------------------------------------- #

_PKG_DIR = os.path.join(_SRC, "evidence_ingestion")
_YF_MODULES = ("yfinance_adapter.py", "yfinance_client.py")


def _yf_sources():
    for name in _YF_MODULES:
        with open(os.path.join(_PKG_DIR, name), "r") as fh:
            yield name, fh.read()


class GuardTests(unittest.TestCase):
    def test_no_network_or_yfinance_package_import(self):
        # ast.walk visits Import / ImportFrom at ANY depth (also lazy/nested). The
        # real ``yfinance`` package is banned outright -- tests use synthetic fixtures.
        banned = {
            "requests", "urllib", "http", "socket", "aiohttp", "httpx",
            "importlib", "yfinance",
        }
        for name, src in _yf_sources():
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
        secret_names = ("api_key", "apikey", "secret", "token", "password", "access_key")
        for name, src in _yf_sources():
            self.assertNotIn("os.environ", src, "{0} reads os.environ".format(name))
            self.assertNotIn("shreenik", src.lower(), "{0} hardcodes personal email".format(name))
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotEqual(node.attr, "environ", "{0} reads os.environ".format(name))
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, ("getenv",), "{0} calls getenv".format(name))
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

    def test_no_technical_signal_computation_in_adapter(self):
        # Raw bars only -- the adapter must not compute EMA / VWAP / signals etc.
        # Guard that such names never appear as an assignment target (a computed field);
        # they live only in the "we do NOT compute" disclaimer prose.
        with open(os.path.join(_PKG_DIR, "yfinance_adapter.py"), "r") as fh:
            tree = ast.parse(fh.read())
        computed_targets = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        computed_targets.add(tgt.id.lower())
        for banned in ("ema", "vwap", "breakout", "compression", "rsi", "macd", "signal_strength"):
            self.assertNotIn(banned, computed_targets)

    def test_no_email_or_secret_in_fixtures(self):
        for fname in os.listdir(_FIXTURE_DIR):
            with open(os.path.join(_FIXTURE_DIR, fname), "r") as fh:
                blob = fh.read().lower()
            self.assertNotIn("shreenik", blob)
            self.assertNotIn("api_key", blob)
            self.assertNotIn("secret", blob)


if __name__ == "__main__":
    unittest.main()
