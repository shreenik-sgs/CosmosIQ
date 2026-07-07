"""IMPLEMENTATION-021A -- the FMP (Financial Modeling Prep) live adapter (OFFLINE, mocked transport).

The SECOND production LIVE source adapter and the first COMMERCIAL provider. Per
SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 and mirroring the accepted 020B SEC EDGAR live adapter's
discipline exactly: it emits RealityEvents ONLY; every FMP datum is convenience (the
commercial_provider tier) + reported_claim (provider-reported), assigned immediately per record
and NEVER promoted -- a provider read can never outrank an SEC filing (canonical > convenience),
and on a same-fact SEC/FMP contradiction BOTH are preserved and routed to Trust / Data Quality.
Credentials are env-var NAMES + presence labels only (a missing FMP_API_KEY is a visible gap,
never a crash / leak; the key VALUE is never echoed / stored / rendered). An HTTP 429/403 (or
quota-shaped error) is captured as rate_limited and honoured (never retried in-pulse); a
timeout/other error is source_unavailable and OTHER tickers continue; a malformed payload is a
parse_error. NO ambient network: every payload arrives through the injected mock transport (the
real transport is built lazily and NEVER exercised here); the whole suite runs under a socket
kill-switch. A failed fetch yields a GAP, never a fixture/demo fallback -- zero fabricated
events. The default run_pulse path stays byte-identical; the adapter is opt-in.
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
    FMP_LIVE_ADAPTER_ID,
    FMP_LIVE_CLAIM_STATUS,
    FMP_LIVE_DESCRIPTOR,
    FMP_LIVE_DISCIPLINES,
    FMP_LIVE_EVENT_TYPES,
    FMP_LIVE_QUOTE_EVENT_TYPE,
    FMP_LIVE_SOURCE_AUTHORITY,
    FMP_LIVE_TRANSPORT_KEYS,
    FmpLiveAdapter,
    SecEdgarLiveAdapter,
    SourceAdapterResult,
    source_health_from_result,
)
from reality_mesh.health import SourceHealthRecord
from reality_mesh.labels import authority_rank
from reality_mesh.models import RealityEvent
from reality_mesh.pulse import run_pulse
from reality_mesh.pulse_persistence import persist_and_summarize
from reality_mesh.sensors.news_filings import claim_status_of

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PY = os.path.join(_HERE, "..", "src", "reality_mesh", "adapters", "fmp_live.py")
_FMP_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "fmp_live")
_SEC_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "sec_edgar_live")

_WATCHLIST = "IREN,AAOI"
_THEMES = "physical-ai,robotics"
_NOW = "2026-07-05T14:00:00Z"

_SEC_CIK_TO_FIXTURE = {
    "0001878848": "sec_submissions_iren_live.json",
    "0000123456": "sec_submissions_aaoi_live.json",
}

# A stand-in credential VALUE used ONLY to prove it never leaks (rejected at the constructor;
# must never appear in any event / result / repr / error / env-echo).
_FAKE_CREDENTIAL = "fmp-SECRETKEY-hunter2-000"

# The socket kill-switch stays armed for the WHOLE module (every path must be offline).
_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: the FMP live adapter must run fully offline on the mock transport "
            "-- the real network path is never exercised in tests")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _load(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as fh:
        return json.load(fh)


def _fmp_fetch(prefix):
    def _fetch(symbol):
        return _load(_FMP_DIR, "{0}_{1}.json".format(prefix, str(symbol).strip().upper()))
    return _fetch


def _fmp_transport(**overrides):
    """The injected per-endpoint FMP MOCK bundle (fully offline; fixture-backed)."""
    bundle = {
        "profile": _fmp_fetch("profile"),
        "income_statement": _fmp_fetch("income"),
        "balance_sheet": _fmp_fetch("balance"),
        "cash_flow": _fmp_fetch("cashflow"),
        "ratios": _fmp_fetch("ratios"),
        "quote": _fmp_fetch("quote"),
    }
    bundle.update(overrides)
    return bundle


def _sec_transport():
    def _submissions(cik):
        return _load(_SEC_DIR, _SEC_CIK_TO_FIXTURE[str(cik).zfill(10)])
    return {"company_tickers": lambda: _load(_SEC_DIR, "company_tickers.json"),
            "submissions": _submissions}


def _raise_429(symbol):
    raise RuntimeError("HTTP 429 Too Many Requests (FMP plan rate exceeded)")


def _raise_403(symbol):
    raise RuntimeError("HTTP 403 Forbidden (Limit Reach / invalid API key)")


def _raise_timeout(symbol):
    raise RuntimeError("connection timed out / reset by peer (simulated source failure)")


def _income_iren_fails(err):
    def _fetch(symbol):
        if str(symbol).strip().upper() == "IREN":
            return err(symbol)
        return _fmp_fetch("income")(symbol)
    return _fetch


def _blob(result):
    return " ".join(result.warnings + result.errors + result.data_gaps
                    + result.raw_payload_refs + (result.run_id,))


# --------------------------------------------------------------------------- #
# 1. Descriptor: the contract declaration                                       #
# --------------------------------------------------------------------------- #
class DescriptorTests(unittest.TestCase):
    def test_identity_authority_and_disciplines(self):
        d = FMP_LIVE_DESCRIPTOR
        self.assertEqual(d.adapter_id, "evidence.fmp_live")
        self.assertEqual(FMP_LIVE_ADAPTER_ID, "evidence.fmp_live")
        self.assertEqual(d.source_authority, "convenience")           # commercial_provider tier
        self.assertEqual(FMP_LIVE_SOURCE_AUTHORITY, "convenience")
        self.assertEqual(FMP_LIVE_CLAIM_STATUS, "reported_claim")     # provider_reported
        self.assertEqual(d.source_type, "financial_data")
        self.assertEqual(FMP_LIVE_DISCIPLINES, ("financial_inflection",))
        self.assertEqual(
            FmpLiveAdapter(transport=_fmp_transport()).covered_disciplines,
            ("financial_inflection",))

    def test_network_required_and_transport_keys(self):
        self.assertTrue(FMP_LIVE_DESCRIPTOR.network_required)
        self.assertEqual(FMP_LIVE_TRANSPORT_KEYS,
                         ("profile", "income_statement", "balance_sheet",
                          "cash_flow", "ratios", "quote"))

    def test_credential_requirements_are_env_var_names_only(self):
        creds = FMP_LIVE_DESCRIPTOR.credential_requirements
        self.assertEqual(creds, ("FMP_API_KEY",))
        for name in creds:
            self.assertRegex(name, r"^[A-Z][A-Z0-9_]*$")     # a NAME, never a value

    def test_all_four_failure_modes_declared(self):
        self.assertEqual(set(FMP_LIVE_DESCRIPTOR.failure_modes),
                         {"credentials_missing", "rate_limited", "source_unavailable",
                          "parse_error"})

    def test_rate_limit_policy_documents_429_403_quota_and_no_retry(self):
        policy = FMP_LIVE_DESCRIPTOR.rate_limit_policy.lower()
        self.assertIn("429", policy)
        self.assertIn("403", policy)
        self.assertIn("quota", policy)
        self.assertIn("never retried", policy)

    def test_claim_status_rules_state_provider_tier_and_never_outrank_sec(self):
        rules = " ".join(FMP_LIVE_DESCRIPTOR.claim_status_rules).lower()
        self.assertIn("convenience", rules)
        self.assertIn("reported_claim", rules)
        self.assertIn("never canonical", rules)
        self.assertIn("never outrank", rules)
        self.assertIn("data quality", rules)

    def test_outputs_are_the_declared_fmp_event_types(self):
        self.assertEqual(FMP_LIVE_DESCRIPTOR.outputs, FMP_LIVE_EVENT_TYPES)
        self.assertIn(FMP_LIVE_QUOTE_EVENT_TYPE, FMP_LIVE_EVENT_TYPES)


# --------------------------------------------------------------------------- #
# 2. Successful live-style fetch -> provider events with provenance              #
# --------------------------------------------------------------------------- #
class SuccessfulFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = FmpLiveAdapter(
            transport=_fmp_transport(), fmp_api_key_present=True)
        cls.events, cls.result = cls.adapter.fetch_checked(
            watchlist=("IREN",), themes=("physical-ai",), now=_NOW)

    def test_reality_events_only_with_provider_provenance(self):
        self.assertTrue(self.events)
        self.assertEqual(self.result.status, "success")
        self.assertEqual(self.result.events_created, len(self.events))
        for ev in self.events:
            self.assertIsInstance(ev, RealityEvent)
            self.assertEqual(ev.source_authority, "convenience")     # commercial_provider tier
            self.assertEqual(ev.claim_status, "reported_claim")      # provider_reported
            self.assertEqual(ev.discipline, "financial_inflection")
            self.assertNotEqual(ev.claim_status, "verified_fact")    # never a verified fact
            self.assertIn("#sha256=", ev.raw_payload_ref)            # content-derived raw ref
            self.assertTrue(ev.evidence_refs or ev.source_refs)
            self.assertIn(ev.freshness_label,
                          {"fresh", "recent", "aging", "stale", "expired", "unknown"})

    def test_profile_and_statement_events_present(self):
        by_type = {e.event_type: e for e in self.events}
        for etype in ("fmp_company_profile", "fmp_income_statement_snapshot",
                      "fmp_balance_sheet_snapshot", "fmp_cash_flow_snapshot",
                      "fmp_key_ratios_snapshot"):
            self.assertIn(etype, by_type)
        # quote is NOT emitted unless enable_quote=True
        self.assertNotIn(FMP_LIVE_QUOTE_EVENT_TYPE, by_type)

    def test_numeric_values_only_where_fmp_returned_them(self):
        inc = next(e for e in self.events
                   if e.event_type == "fmp_income_statement_snapshot")
        metrics = {name: value for name, value, _u in inc.numeric_values}
        self.assertEqual(metrics["revenue_usd"], 300000000.0)        # FMP-returned figure
        self.assertEqual(metrics["operating_margin_pct"], 20.0)      # FMP-returned ratio
        self.assertEqual(metrics["operating_margin_delta_pct"], 10.0)  # derived +10pp expansion

    def test_event_carries_endpoint_and_symbol_in_refs(self):
        inc = next(e for e in self.events
                   if e.event_type == "fmp_income_statement_snapshot")
        refs = " ".join(inc.source_refs + inc.evidence_refs)
        self.assertIn("fmp:endpoint/income_statement", refs)
        self.assertIn("fmp:symbol/IREN", refs)
        self.assertEqual(inc.timestamp, "2026-06-30")                # FMP period end
        self.assertEqual(inc.freshness_label, "fresh")               # 5 days before now

    def test_source_health_record_is_produced(self):
        record = source_health_from_result(self.result, now=_NOW)
        self.assertIsInstance(record, SourceHealthRecord)
        self.assertEqual(record.source_id, FMP_LIVE_ADAPTER_ID)
        self.assertEqual(record.last_status, "healthy")
        self.assertEqual(record.last_success_at, _NOW)

    def test_deterministic_ids_and_run_id(self):
        events2, result2 = FmpLiveAdapter(
            transport=_fmp_transport(), fmp_api_key_present=True).fetch_checked(
                watchlist=("IREN",), themes=("physical-ai",), now=_NOW)
        self.assertEqual([e.event_id for e in self.events],
                         [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        self.assertTrue(self.result.run_id.startswith("adapterrun.evidence.fmp_live."))
        self.assertTrue(all(e.event_id.startswith("fmplive.") for e in self.events))


# --------------------------------------------------------------------------- #
# 3. Credentials: presence labels only; missing -> visible gap, never a leak     #
# --------------------------------------------------------------------------- #
class CredentialTests(unittest.TestCase):
    def test_missing_fmp_api_key_skips_with_gap_no_crash(self):
        adapter = FmpLiveAdapter(
            transport=_fmp_transport(), fmp_api_key_present=False)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.source_health, "credentials_missing")
        self.assertEqual(result.credentials_status, "missing")   # a LABEL, never a value
        self.assertTrue(any("FMP_API_KEY" in g for g in result.data_gaps))
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "credentials_missing")
        self.assertEqual(record.credentials_status, "missing")

    def test_credential_value_passed_as_flag_is_rejected_and_never_echoed(self):
        with self.assertRaises(ValueError) as ctx:
            FmpLiveAdapter(transport=_fmp_transport(),
                           fmp_api_key_present=_FAKE_CREDENTIAL)
        message = str(ctx.exception)
        self.assertNotIn(_FAKE_CREDENTIAL, message)              # NEVER echoed back
        self.assertIn("PRESENCE flag", message)

    def test_no_credential_value_in_any_event_result_or_repr(self):
        # A fake key is present in the ENVIRONMENT; it must never surface in any output.
        prior = os.environ.get("FMP_API_KEY")
        os.environ["FMP_API_KEY"] = _FAKE_CREDENTIAL
        try:
            adapter = FmpLiveAdapter(
                transport=_fmp_transport(), fmp_api_key_present=True)
            events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        finally:
            if prior is None:
                os.environ.pop("FMP_API_KEY", None)
            else:
                os.environ["FMP_API_KEY"] = prior
        self.assertEqual(result.credentials_status, "present")   # a label only
        surfaces = [repr(adapter), repr(result), _blob(result)]
        surfaces.extend(repr(e) for e in events)
        for text in surfaces:
            low = text.lower()
            self.assertNotIn(_FAKE_CREDENTIAL.lower(), low)
            for bad in ("api_key=", "apikey=", "password", "secret_key", "fmp_api_key="):
                self.assertNotIn(bad, low)


# --------------------------------------------------------------------------- #
# 4. Failure capture: rate limit (429/403) / timeout / malformed -> gaps         #
# --------------------------------------------------------------------------- #
class FailureCaptureTests(unittest.TestCase):
    def test_http_429_is_rate_limited_and_other_tickers_continue(self):
        adapter = FmpLiveAdapter(
            transport=_fmp_transport(income_statement=_income_iren_fails(_raise_429)),
            fmp_api_key_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(result.status, "partial")          # NOT a crash, NOT empty
        self.assertEqual(result.rate_limit_status, "throttled")
        self.assertEqual(result.source_health, "rate_limited")
        self.assertTrue(any(e.startswith("rate_limited: income_statement IREN")
                            for e in result.errors))
        self.assertTrue(any("not retried" in g.lower() for g in result.data_gaps))
        # AAOI income still delivered; IREN income did not (its other endpoints still ran)
        self.assertTrue(any(e.affected_companies == ("AAOI",)
                            and e.event_type == "fmp_income_statement_snapshot"
                            for e in events))
        self.assertFalse(any(e.affected_companies == ("IREN",)
                             and e.event_type == "fmp_income_statement_snapshot"
                             for e in events))

    def test_http_403_quota_is_honoured_as_rate_limited(self):
        adapter = FmpLiveAdapter(
            transport=_fmp_transport(income_statement=_raise_403),
            fmp_api_key_present=True)
        _events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(result.rate_limit_status, "throttled")
        self.assertEqual(result.source_health, "rate_limited")

    def test_timeout_is_a_data_gap_partial_others_continue(self):
        adapter = FmpLiveAdapter(
            transport=_fmp_transport(income_statement=_income_iren_fails(_raise_timeout)),
            fmp_api_key_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(e.startswith("source_unavailable: income_statement IREN")
                            for e in result.errors))
        self.assertTrue(any("IREN" in g and "unavailable" in g for g in result.data_gaps))
        self.assertTrue(any(e.affected_companies == ("AAOI",) for e in events))

    def test_malformed_payload_is_a_parse_error_gap(self):
        adapter = FmpLiveAdapter(
            transport=_fmp_transport(income_statement=lambda s: 12345),  # not list/dict
            fmp_api_key_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertTrue(any(e.startswith("parse_error: income_statement") for e in result.errors))
        self.assertTrue(any("parse_error" in g and "nothing fabricated" in g
                            for g in result.data_gaps))
        # the OTHER IREN endpoints still delivered -> partial, not a crash
        self.assertTrue(events)

    def test_empty_watchlist_is_a_skipped_result_with_gap(self):
        adapter = FmpLiveAdapter(
            transport=_fmp_transport(), fmp_api_key_present=True)
        events, result = adapter.fetch_checked(watchlist=(), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertTrue(any("empty watchlist" in g for g in result.data_gaps))

    def test_single_period_delta_is_a_gap_never_fabricated(self):
        # one income period returned -> the period-over-period delta is NOT computable.
        adapter = FmpLiveAdapter(
            transport=_fmp_transport(
                income_statement=lambda s: _load(_FMP_DIR, "income_single_IREN.json")),
            fmp_api_key_present=True)
        events, _result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        inc = next(e for e in events if e.event_type == "fmp_income_statement_snapshot")
        names = {n for n, _v, _u in inc.numeric_values}
        self.assertNotIn("operating_margin_delta_pct", names)       # not fabricated
        self.assertTrue(any("not computable" in g for g in inc.data_gaps))


# --------------------------------------------------------------------------- #
# 5. NO fixture fallback in real mode: a failed fetch is a gap, not fixture data #
# --------------------------------------------------------------------------- #
class NoFixtureFallbackTests(unittest.TestCase):
    def _all_fail(self, symbol):
        raise RuntimeError("connection timed out (simulated total FMP outage)")

    def test_all_fetches_failing_yields_zero_fabricated_events(self):
        transport = {k: self._all_fail for k in FMP_LIVE_TRANSPORT_KEYS}
        adapter = FmpLiveAdapter(transport=transport, fmp_api_key_present=True)
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(len(events), 0)                    # ZERO fabricated events
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(result.data_gaps)
        self.assertFalse(any("fixture" in r for r in result.raw_payload_refs))


# --------------------------------------------------------------------------- #
# 6. No network on import; offline; no score/rank def names                      #
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
                        "network import {0!r} in fmp_live.py".format(name))

    def test_no_score_rank_or_rating_function_defs(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                 "banned fn name {0!r}".format(node.name))

    def test_real_transport_is_function_local(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("def _default_transport", source)
        self.assertIn("from evidence_ingestion.live_transport import fmp_live_transport", source)


# --------------------------------------------------------------------------- #
# 6b. Transport migration: /stable endpoints (v3 is RETIRED, HTTP 403)           #
# --------------------------------------------------------------------------- #
class StableEndpointMigrationTests(unittest.TestCase):
    """The live transport must build FMP's CURRENT /stable URLs (symbol as a QUERY param,
    apikey as a query param) -- never the RETIRED /api/v3/ path endpoints. This asserts the
    URL shape WITHOUT ever touching the wire (urllib stays inside _http_get, which we patch
    to a pure string collector; import is network-free)."""

    def _captured_urls(self):
        import evidence_ingestion.live_transport as lt
        seen = []

        def _fake_http_get(url, headers=None, timeout=20.0):
            seen.append(url)
            return "[]"

        orig = lt._http_get
        lt._http_get = _fake_http_get
        try:
            bundle = lt.fmp_live_transport("MOCK-KEY-never-logged", timeout=5.0)
            for key in ("profile", "income_statement", "balance_sheet",
                        "cash_flow", "ratios", "quote"):
                bundle[key]("iren")   # lowercase -> normalised to IREN in the URL
        finally:
            lt._http_get = orig
        return seen

    def test_urls_are_stable_not_v3_with_symbol_and_apikey_as_query(self):
        urls = self._captured_urls()
        self.assertEqual(len(urls), 6)
        for url in urls:
            self.assertIn("https://financialmodelingprep.com/stable/", url)
            self.assertNotIn("/api/v3/", url)         # the RETIRED (HTTP 403) surface
            self.assertIn("symbol=IREN", url)         # symbol is a QUERY param now
            self.assertNotIn("/IREN", url)            # never a path segment
            self.assertIn("apikey=MOCK-KEY-never-logged", url)
        joined = " ".join(urls)
        self.assertIn("/stable/profile?symbol=IREN", joined)
        self.assertIn("/stable/income-statement?symbol=IREN&limit=2", joined)
        self.assertIn("/stable/balance-sheet-statement?symbol=IREN&limit=2", joined)
        self.assertIn("/stable/cash-flow-statement?symbol=IREN&limit=2", joined)
        self.assertIn("/stable/ratios?symbol=IREN&limit=2", joined)
        self.assertIn("/stable/quote?symbol=IREN", joined)

    def test_transport_module_imports_no_network_at_top_level(self):
        path = os.path.join(_HERE, "..", "src", "evidence_ingestion", "live_transport.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx")
        for node in tree.body:          # MODULE top level only -- lazy fn-local urllib is fine
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for root in banned:
                    self.assertFalse(
                        name == root or name.startswith(root + "."),
                        "top-level network import {0!r} in live_transport.py".format(name))


# --------------------------------------------------------------------------- #
# 7. Quote endpoint is only CALLED when enable_quote=True                        #
# --------------------------------------------------------------------------- #
class QuoteGatingTests(unittest.TestCase):
    def test_quote_not_called_by_default(self):
        called = {"quote": 0}

        def _quote(symbol):
            called["quote"] += 1
            return _fmp_fetch("quote")(symbol)

        adapter = FmpLiveAdapter(
            transport=_fmp_transport(quote=_quote), fmp_api_key_present=True)  # enable_quote=False
        events, _result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(called["quote"], 0)                        # never CALLED
        self.assertFalse(any(e.event_type == FMP_LIVE_QUOTE_EVENT_TYPE for e in events))

    def test_quote_emitted_only_when_enabled(self):
        adapter = FmpLiveAdapter(
            transport=_fmp_transport(), fmp_api_key_present=True, enable_quote=True)
        events, _result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        quotes = [e for e in events if e.event_type == FMP_LIVE_QUOTE_EVENT_TYPE]
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].source_authority, "convenience")
        self.assertEqual(quotes[0].claim_status, "reported_claim")


# --------------------------------------------------------------------------- #
# 8. Authority ladder: FMP (convenience) can NEVER outrank SEC (canonical)        #
# --------------------------------------------------------------------------- #
class AuthorityLadderTests(unittest.TestCase):
    def test_fmp_provider_can_never_outrank_sec(self):
        # commercial_provider (convenience) strictly BELOW canonical (SEC).
        self.assertLess(authority_rank(FMP_LIVE_SOURCE_AUTHORITY), authority_rank("canonical"))
        adapter = FmpLiveAdapter(transport=_fmp_transport(), fmp_api_key_present=True)
        events, _ = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertTrue(events)
        self.assertTrue(all(e.source_authority == "convenience" for e in events))
        self.assertTrue(all(e.claim_status == "reported_claim" for e in events))

    def test_fmp_event_can_never_be_a_verified_fact(self):
        # even if a caller mislabels it, the model refuses a rumor->verified promotion; here we
        # assert the adapter never itself stamps canonical / verified_fact.
        adapter = FmpLiveAdapter(transport=_fmp_transport(), fmp_api_key_present=True)
        events, _ = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertFalse(any(e.source_authority == "canonical" for e in events))
        self.assertFalse(any(e.claim_status == "verified_fact" for e in events))


# --------------------------------------------------------------------------- #
# 9. End to end: mocked FMP adapter -> run_pulse -> financial_inflection          #
# --------------------------------------------------------------------------- #
class LivePulseEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(FmpLiveAdapter(
                              transport=_fmp_transport(), fmp_api_key_present=True),))

    def test_financial_inflection_findings_come_from_live_fmp_events(self):
        fi = [f for f in self.r.findings if f.discipline == "financial_inflection"]
        self.assertTrue(fi)
        for f in fi:
            for ev_id in f.input_events:
                self.assertTrue(ev_id.startswith("fmplive."),
                                "fixture event {0!r} leaked into financial_inflection".format(ev_id))

    def test_provider_findings_stay_reported_claim_and_convenience(self):
        fi = [f for f in self.r.findings if f.discipline == "financial_inflection"]
        self.assertTrue(fi)
        for f in fi:
            self.assertEqual(f.source_authority_summary, "convenience")
            self.assertNotEqual(f.source_authority_summary, "canonical")
            self.assertNotEqual(claim_status_of(f), "verified_fact")

    def test_adapter_result_is_on_the_pulse_and_healthy(self):
        self.assertEqual(len(self.r.adapter_results), 1)
        result = self.r.adapter_results[0]
        self.assertIsInstance(result, SourceAdapterResult)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.adapter_id, FMP_LIVE_ADAPTER_ID)
        self.assertIn("IREN", self.r.covered_companies)
        self.assertIn("AAOI", self.r.covered_companies)
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "healthy")

    def test_freshness_visible_on_events(self):
        result = self.r.adapter_results[0]
        self.assertEqual(result.source_health, "healthy")
        # a statement finding carries a real freshness label (not "missing")
        fi = [f for f in self.r.findings if f.discipline == "financial_inflection"]
        self.assertTrue(any(f.freshness_label in ("fresh", "recent", "aging", "stale", "expired")
                            for f in fi))

    def test_uncovered_disciplines_still_come_from_fixtures(self):
        self.assertTrue(any(f.discipline == "market_regime" for f in self.r.findings))
        self.assertTrue(any(f.discipline == "narrative" for f in self.r.findings))

    def test_pulse_with_the_live_adapter_is_deterministic(self):
        again = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(FmpLiveAdapter(
                              transport=_fmp_transport(), fmp_api_key_present=True),))
        self.assertEqual(self.r, again)


# --------------------------------------------------------------------------- #
# 10. SEC/FMP contradiction preserved -> routed to Data Quality (both kept)       #
# --------------------------------------------------------------------------- #
class ContradictionPreservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # BOTH live adapters run: SEC (canonical news_filings) + FMP (convenience financial).
        cls.r = run_pulse(
            _WATCHLIST, _THEMES, now=_NOW,
            adapters=(
                SecEdgarLiveAdapter(transport=_sec_transport(), sec_user_agent_present=True),
                FmpLiveAdapter(transport=_fmp_transport(), fmp_api_key_present=True)))

    def test_both_sec_and_fmp_findings_are_preserved_for_iren(self):
        fi = [f for f in self.r.findings
              if f.discipline == "financial_inflection" and f.affected_companies == ("IREN",)]
        canonical = [f for f in fi if f.source_authority_summary == "canonical"]
        convenience = [f for f in fi if f.source_authority_summary == "convenience"]
        self.assertTrue(canonical, "SEC canonical financial-inflection finding was dropped")
        self.assertTrue(convenience, "FMP provider financial-inflection finding was dropped")
        # provenance is intact: SEC from seclive.*, FMP from fmplive.*
        self.assertTrue(all(any(i.startswith("seclive.") for i in f.input_events)
                            for f in canonical))
        self.assertTrue(all(any(i.startswith("fmplive.") for i in f.input_events)
                            for f in convenience))

    def test_provider_read_never_overwrites_the_sec_filing_fact(self):
        # The FMP (convenience) read is preserved as a contradicting provider read; SEC
        # (canonical) wins authority and is NEVER overwritten (canonical > convenience).
        self.assertGreater(authority_rank("canonical"),
                           authority_rank(FMP_LIVE_SOURCE_AUTHORITY))
        conv = [f for f in self.r.findings
                if f.discipline == "financial_inflection"
                and f.source_authority_summary == "convenience"]
        # a provider finding is NEVER laundered up to canonical / verified_fact
        for f in conv:
            self.assertNotEqual(f.source_authority_summary, "canonical")
            self.assertNotEqual(claim_status_of(f), "verified_fact")

    def test_contradiction_is_surfaced_and_routed_to_data_quality(self):
        # The fusion layer KEEPS both sides: the IREN financial-inflection signal carries BOTH
        # a canonical and a convenience source finding and is marked contradicted (never averaged).
        sig = next((s for s in self.r.signals
                    if s.discipline == "financial_inflection"
                    and "IREN" in s.affected_companies), None)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.contradiction_status, "contradicted")
        auths = set()
        for fid in sig.source_findings:
            f = next((x for x in self.r.findings if x.finding_id == fid), None)
            if f is not None:
                auths.add(f.source_authority_summary)
        self.assertEqual(auths, {"canonical", "convenience"})       # both preserved
        # SEC wins the signal authority; FMP is preserved, not promoted.
        self.assertEqual(self.r.authority_by_signal.get(sig.signal_id), "canonical")

    def test_both_adapters_reported_on_the_pulse(self):
        ids = {res.adapter_id for res in self.r.adapter_results}
        self.assertEqual(ids, {"evidence.sec_edgar_live", "evidence.fmp_live"})
        self.assertTrue(all(res.status == "success" for res in self.r.adapter_results))


# --------------------------------------------------------------------------- #
# 11. Replay compatibility: persist + verification replay deterministic_match     #
# --------------------------------------------------------------------------- #
class ReplayCompatibilityTests(unittest.TestCase):
    def test_persisted_live_pulse_replays_deterministically(self):
        pulse = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(FmpLiveAdapter(
                              transport=_fmp_transport(), fmp_api_key_present=True),))
        with tempfile.TemporaryDirectory() as store_dir:
            _pulse_run, replay, _panel = persist_and_summarize(
                pulse, store_dir=store_dir, run_id="RUN-FMPLIVE-021A", now=_NOW)
            self.assertTrue(replay.deterministic_match)
            self.assertTrue(pulse.events_loaded > 0)


# --------------------------------------------------------------------------- #
# 12. Default path byte-identical; opt-in only                                   #
# --------------------------------------------------------------------------- #
class DefaultPathUnchangedTests(unittest.TestCase):
    def test_default_pulse_stays_byte_identical(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        explicit_none = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                                  data_dir=None, adapters=None)
        self.assertEqual(base, explicit_none)               # every field, byte for byte
        self.assertEqual(base.adapter_results, ())
        # the default path carries NO fmplive events
        fi = [f for f in base.findings if f.discipline == "financial_inflection"]
        self.assertTrue(all(not ev.startswith("fmplive.")
                            for f in fi for ev in f.input_events))


if __name__ == "__main__":
    unittest.main()
