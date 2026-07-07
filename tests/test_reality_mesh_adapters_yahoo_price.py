"""PROD-LIVE-2 -- the Yahoo Finance price-history FALLBACK adapter (OFFLINE, mocked transport).

A research-only, FALLBACK-tier price source that keeps technicals available when FMP is missing /
throttled. Per SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 and mirroring the accepted 020B/021A live
adapters: it emits RealityEvents ONLY; every Yahoo chart reading is fallback (research-only) +
reported_claim, assigned immediately per record and NEVER promoted -- it can never outrank FMP
(convenience) or SEC (canonical): fallback < convenience < canonical. No credential exists (Yahoo's
public chart needs no key). An HTTP 429 (or rate-limit-shaped error) is captured as rate_limited
and honoured (never retried); a timeout/other error is source_unavailable and OTHER tickers
continue; a malformed payload is a parse_error; an unknown/delisted ticker is a NAMED gap. NO
ambient network: every payload arrives through the injected mock transport (the real transport is
built lazily and NEVER exercised here); the whole suite runs under a socket kill-switch. A failed
fetch yields a GAP, never a fixture/demo fallback -- ZERO fabricated bars. The module imports only
stdlib + first-party src (NO yfinance / third-party), so dependencies_reviewed stays green. The
default run_pulse path stays byte-identical; the adapter is opt-in.
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
    YAHOO_FALLBACK_EVENT_NOTE,
    YAHOO_PRICE_LIVE_ADAPTER_ID,
    YAHOO_PRICE_LIVE_CLAIM_STATUS,
    YAHOO_PRICE_LIVE_DESCRIPTOR,
    YAHOO_PRICE_LIVE_DISCIPLINES,
    YAHOO_PRICE_LIVE_EVENT_TYPE,
    YAHOO_PRICE_LIVE_SOURCE_AUTHORITY,
    YAHOO_PRICE_LIVE_TRANSPORT_KEYS,
    SourceAdapterResult,
    YahooPriceLiveAdapter,
    source_health_from_result,
)
from reality_mesh.health import SourceHealthRecord
from reality_mesh.labels import authority_rank
from reality_mesh.models import RealityEvent
from reality_mesh.pulse import run_pulse
from reality_mesh.pulse_persistence import persist_and_summarize

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "src")
_MODULE_PY = os.path.join(_SRC, "reality_mesh", "adapters", "yahoo_price_live.py")
_TRANSPORT_PY = os.path.join(_SRC, "evidence_ingestion", "live_transport.py")
_YF_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "yahoo_price")

_WATCHLIST = "IREN,AAOI"
_THEMES = "physical-ai,robotics"
_NOW = "2026-07-05T14:00:00Z"

# The socket kill-switch stays armed for the WHOLE module (every path must be offline).
_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: the Yahoo price fallback adapter must run fully offline on the mock "
            "transport -- the real network path is never exercised in tests")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _load(name):
    with open(os.path.join(_YF_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def _chart_fetch(symbol):
    return _load("chart_{0}.json".format(str(symbol).strip().upper()))


def _transport(**overrides):
    """The injected Yahoo MOCK chart bundle (fully offline; fixture-backed)."""
    bundle = {"chart": _chart_fetch}
    bundle.update(overrides)
    return bundle


def _iren_fails(err):
    def _fetch(symbol):
        if str(symbol).strip().upper() == "IREN":
            return err(symbol)
        return _chart_fetch(symbol)
    return _fetch


def _raise_429(symbol):
    raise RuntimeError("HTTP 429 Too Many Requests (Yahoo throttled)")


def _raise_timeout(symbol):
    raise RuntimeError("connection timed out / reset by peer (simulated source failure)")


def _delisted(symbol):
    return _load("chart_DELISTED.json")


# --------------------------------------------------------------------------- #
# 1. Descriptor: the contract declaration                                       #
# --------------------------------------------------------------------------- #
class DescriptorTests(unittest.TestCase):
    def test_identity_authority_and_disciplines(self):
        d = YAHOO_PRICE_LIVE_DESCRIPTOR
        self.assertEqual(d.adapter_id, "price.yahoo_fallback")
        self.assertEqual(YAHOO_PRICE_LIVE_ADAPTER_ID, "price.yahoo_fallback")
        self.assertEqual(d.source_authority, "fallback")             # research-only fallback tier
        self.assertEqual(YAHOO_PRICE_LIVE_SOURCE_AUTHORITY, "fallback")
        self.assertEqual(YAHOO_PRICE_LIVE_CLAIM_STATUS, "reported_claim")
        self.assertEqual(d.source_type, "price_history")
        self.assertEqual(YAHOO_PRICE_LIVE_DISCIPLINES, ("technical_regime",))
        self.assertEqual(
            YahooPriceLiveAdapter(transport=_transport()).covered_disciplines,
            ("technical_regime",))

    def test_no_credential_required(self):
        self.assertEqual(YAHOO_PRICE_LIVE_DESCRIPTOR.credential_requirements, ())
        self.assertTrue(YAHOO_PRICE_LIVE_DESCRIPTOR.network_required)
        self.assertEqual(YAHOO_PRICE_LIVE_TRANSPORT_KEYS, ("chart",))

    def test_failure_modes_have_no_credentials_missing(self):
        # No credential exists -> credentials_missing is NOT a failure mode.
        self.assertEqual(set(YAHOO_PRICE_LIVE_DESCRIPTOR.failure_modes),
                         {"rate_limited", "source_unavailable", "parse_error"})

    def test_claim_rules_state_fallback_tier_and_never_outrank_fmp_sec(self):
        rules = " ".join(YAHOO_PRICE_LIVE_DESCRIPTOR.claim_status_rules).lower()
        self.assertIn("fallback", rules)
        self.assertIn("reported_claim", rules)
        self.assertIn("never canonical", rules)
        self.assertIn("never outrank", rules)
        self.assertIn("convenience", rules)
        self.assertIn("data quality", rules)

    def test_outputs_are_the_price_history_reading_type(self):
        self.assertEqual(YAHOO_PRICE_LIVE_DESCRIPTOR.outputs, (YAHOO_PRICE_LIVE_EVENT_TYPE,))
        self.assertEqual(YAHOO_PRICE_LIVE_EVENT_TYPE, "price_history_reading")


# --------------------------------------------------------------------------- #
# 2. Successful live-style fetch -> fallback price-history events with provenance #
# --------------------------------------------------------------------------- #
class SuccessfulFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = YahooPriceLiveAdapter(transport=_transport())
        cls.events, cls.result = cls.adapter.fetch_checked(
            watchlist=("IREN", "AAOI"), themes=("physical-ai",), now=_NOW)

    def test_reality_events_only_with_fallback_provenance(self):
        self.assertEqual(len(self.events), 2)
        self.assertEqual(self.result.status, "success")
        self.assertEqual(self.result.source_health, "healthy")
        self.assertEqual(self.result.credentials_status, "not_required")
        self.assertEqual(self.result.events_created, len(self.events))
        for ev in self.events:
            self.assertIsInstance(ev, RealityEvent)
            self.assertEqual(ev.source_authority, "fallback")        # research-only fallback tier
            self.assertEqual(ev.claim_status, "reported_claim")
            self.assertEqual(ev.discipline, "technical_regime")
            self.assertEqual(ev.event_type, "price_history_reading")
            self.assertNotEqual(ev.claim_status, "verified_fact")    # never a verified fact
            self.assertNotEqual(ev.source_authority, "canonical")
            self.assertNotEqual(ev.source_authority, "convenience")
            self.assertIn("#sha256=", ev.raw_payload_ref)            # content-derived raw ref
            self.assertTrue(ev.evidence_refs or ev.source_refs)
            self.assertEqual(ev.freshness_label, "fresh")            # latest bar 3 days before now
            self.assertIn(YAHOO_FALLBACK_EVENT_NOTE, ev.data_gaps)

    def test_numeric_values_are_derived_from_actual_bars(self):
        iren = next(e for e in self.events if e.affected_companies == ("IREN",))
        metrics = {name: value for name, value, _u in iren.numeric_values}
        # close is the LAST bar's actual close (17.0 in the deterministic uptrend fixture).
        self.assertEqual(metrics["close"], 17.0)
        # EMAs are derived from the real close series (uptrend -> ema8 > ema21).
        self.assertIn("ema8", metrics)
        self.assertIn("ema21", metrics)
        self.assertGreater(metrics["ema8"], metrics["ema21"])
        # every numeric value carries a unit tag
        for _name, _value, unit in iren.numeric_values:
            self.assertTrue(unit)

    def test_underivable_ema200_is_a_gap_never_fabricated(self):
        # a 6-month (~60-bar) window cannot derive a 200-EMA -> it is an explicit gap, not faked.
        iren = next(e for e in self.events if e.affected_companies == ("IREN",))
        names = {n for n, _v, _u in iren.numeric_values}
        self.assertNotIn("ema200", names)
        self.assertTrue(any("ema200" in g for g in iren.data_gaps))

    def test_event_carries_symbol_in_refs(self):
        iren = next(e for e in self.events if e.affected_companies == ("IREN",))
        refs = " ".join(iren.source_refs + iren.evidence_refs)
        self.assertIn("yahoo:chart/IREN", refs)
        self.assertIn("yahoo:symbol/IREN", refs)

    def test_source_health_record_is_produced(self):
        record = source_health_from_result(self.result, now=_NOW)
        self.assertIsInstance(record, SourceHealthRecord)
        self.assertEqual(record.source_id, YAHOO_PRICE_LIVE_ADAPTER_ID)
        self.assertEqual(record.last_status, "healthy")
        self.assertEqual(record.last_success_at, _NOW)

    def test_deterministic_ids_and_run_id(self):
        events2, result2 = YahooPriceLiveAdapter(transport=_transport()).fetch_checked(
            watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual([e.event_id for e in self.events], [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        self.assertTrue(self.result.run_id.startswith("adapterrun.price.yahoo_fallback."))
        self.assertTrue(all(e.event_id.startswith("yahoolive.") for e in self.events))


# --------------------------------------------------------------------------- #
# 3. Authority ladder: fallback < FMP convenience < SEC canonical                #
# --------------------------------------------------------------------------- #
class AuthorityLadderTests(unittest.TestCase):
    def test_fallback_below_convenience_below_canonical(self):
        self.assertLess(authority_rank("fallback"), authority_rank("convenience"))
        self.assertLess(authority_rank("convenience"), authority_rank("canonical"))
        self.assertLess(authority_rank(YAHOO_PRICE_LIVE_SOURCE_AUTHORITY),
                        authority_rank("convenience"))
        self.assertLess(authority_rank(YAHOO_PRICE_LIVE_SOURCE_AUTHORITY),
                        authority_rank("canonical"))

    def test_yahoo_events_never_outrank_fmp_or_sec(self):
        adapter = YahooPriceLiveAdapter(transport=_transport())
        events, _ = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertTrue(events)
        for e in events:
            self.assertEqual(e.source_authority, "fallback")
            self.assertLess(authority_rank(e.source_authority), authority_rank("convenience"))
            self.assertLess(authority_rank(e.source_authority), authority_rank("canonical"))
            self.assertNotEqual(e.claim_status, "verified_fact")

    def test_same_fact_conflict_keeps_the_higher_tier(self):
        # A conflict resolver that prefers the strictly-higher authority keeps FMP/SEC over Yahoo.
        yahoo = "fallback"
        for higher in ("convenience", "canonical"):
            winner = max((yahoo, higher), key=authority_rank)
            self.assertEqual(winner, higher)                         # Yahoo never wins the fact


# --------------------------------------------------------------------------- #
# 4. Failure capture: 429 / timeout / malformed / delisted -> visible gaps       #
# --------------------------------------------------------------------------- #
class FailureCaptureTests(unittest.TestCase):
    def test_http_429_is_rate_limited_and_other_tickers_continue(self):
        adapter = YahooPriceLiveAdapter(transport=_transport(chart=_iren_fails(_raise_429)))
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(result.status, "partial")                   # NOT a crash, NOT empty
        self.assertEqual(result.rate_limit_status, "throttled")
        self.assertEqual(result.source_health, "rate_limited")
        self.assertTrue(any(e.startswith("rate_limited: chart IREN") for e in result.errors))
        self.assertTrue(any("not retried" in g.lower() for g in result.data_gaps))
        # AAOI still delivered; IREN did not
        self.assertTrue(any(e.affected_companies == ("AAOI",) for e in events))
        self.assertFalse(any(e.affected_companies == ("IREN",) for e in events))

    def test_timeout_is_source_unavailable_gap_others_continue(self):
        adapter = YahooPriceLiveAdapter(transport=_transport(chart=_iren_fails(_raise_timeout)))
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(e.startswith("source_unavailable: chart IREN") for e in result.errors))
        self.assertTrue(any("IREN" in g and "unavailable" in g for g in result.data_gaps))
        self.assertTrue(any(e.affected_companies == ("AAOI",) for e in events))

    def test_malformed_payload_is_a_parse_error_gap(self):
        adapter = YahooPriceLiveAdapter(transport=_transport(chart=lambda s: 12345))
        events, result = adapter.fetch_checked(watchlist=("IREN",), now=_NOW)
        self.assertEqual(len(events), 0)
        self.assertEqual(result.status, "failed")
        self.assertTrue(any(e.startswith("parse_error: chart") for e in result.errors))
        self.assertTrue(any("parse_error" in g and "nothing fabricated" in g
                            for g in result.data_gaps))

    def test_unknown_delisted_ticker_is_a_named_gap(self):
        adapter = YahooPriceLiveAdapter(transport=_transport(chart=_delisted))
        events, result = adapter.fetch_checked(watchlist=("ZZZZ",), now=_NOW)
        self.assertEqual(len(events), 0)                             # ZERO fabricated bars
        self.assertTrue(any("ZZZZ" in g and ("delisted" in g.lower() or "no data" in g.lower())
                            for g in result.data_gaps))

    def test_empty_bars_response_is_a_named_gap_not_fabricated(self):
        adapter = YahooPriceLiveAdapter(
            transport=_transport(chart=lambda s: _load("chart_EMPTY.json")))
        events, result = adapter.fetch_checked(watchlist=("EMPTY",), now=_NOW)
        self.assertEqual(len(events), 0)
        self.assertTrue(any("no usable OHLCV" in g or "no data" in g.lower()
                            for g in result.data_gaps))

    def test_empty_watchlist_is_a_skipped_result_with_gap(self):
        adapter = YahooPriceLiveAdapter(transport=_transport())
        events, result = adapter.fetch_checked(watchlist=(), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertTrue(any("empty watchlist" in g for g in result.data_gaps))


# --------------------------------------------------------------------------- #
# 5. NO fixture fallback: a total outage is a gap, zero fabricated bars          #
# --------------------------------------------------------------------------- #
class NoFixtureFallbackTests(unittest.TestCase):
    def _all_fail(self, symbol):
        raise RuntimeError("connection timed out (simulated total Yahoo outage)")

    def test_all_fetches_failing_yields_zero_fabricated_events(self):
        adapter = YahooPriceLiveAdapter(transport={"chart": self._all_fail})
        events, result = adapter.fetch_checked(watchlist=("IREN", "AAOI"), now=_NOW)
        self.assertEqual(len(events), 0)                             # ZERO fabricated bars
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(result.data_gaps)
        self.assertFalse(any("fixture" in r for r in result.raw_payload_refs))


# --------------------------------------------------------------------------- #
# 6. No network on import; stdlib-only (no yfinance / third-party)               #
# --------------------------------------------------------------------------- #
class ModuleHygieneTests(unittest.TestCase):
    def _imported_roots(self, path):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        module_level, all_names = [], []
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            all_names.extend(names)
        for node in tree.body:                       # module top-level only
            if isinstance(node, ast.Import):
                module_level.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                module_level.append(node.module or "")
        return all_names, module_level

    def test_no_network_import_anywhere(self):
        all_names, _ = self._imported_roots(_MODULE_PY)
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx",
                  "websocket", "websockets", "ftplib", "smtplib", "telnetlib")
        for name in all_names:
            for root in banned:
                self.assertFalse(
                    name == root or name.startswith(root + "."),
                    "network import {0!r} in yahoo_price_live.py".format(name))

    def test_never_imports_yfinance_or_any_third_party(self):
        # Classify every ABSOLUTE import root against stdlib + the first-party src packages
        # (exactly like the 023H dependencies_reviewed audit, reusing its stdlib classifier so
        # this is Python-3.9 correct). NOTHING third-party -- above all, the yfinance PACKAGE is
        # never imported (we reimplement it with stdlib urllib).
        from cosmosiq_ops.security_audit import _is_stdlib_module
        all_names, _ = self._imported_roots(_MODULE_PY)
        first_party = set(os.listdir(_SRC))
        for name in all_names:
            root = name.split(".")[0]
            self.assertNotEqual(root, "yfinance", "the yfinance package must never be imported")
            is_stdlib = _is_stdlib_module(root) or root == "__future__"
            self.assertTrue(
                is_stdlib or root in first_party,
                "unexpected third-party import root {0!r} in yahoo_price_live.py".format(root))

    def test_real_transport_is_function_local(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("def _default_transport", source)
        self.assertIn(
            "from evidence_ingestion.live_transport import yahoo_chart_transport", source)

    def test_transport_helper_imports_no_network_at_top_level(self):
        _all_names, module_level = self._imported_roots(_TRANSPORT_PY)
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx")
        for name in module_level:
            for root in banned:
                self.assertFalse(
                    name == root or name.startswith(root + "."),
                    "top-level network import {0!r} in live_transport.py".format(name))

    def test_no_score_rank_or_rating_function_defs(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(re.search(r"(score|rank|rating|broker|_order|buy|sell)",
                                           node.name),
                                 "banned fn name {0!r}".format(node.name))


# --------------------------------------------------------------------------- #
# 7. dependencies_reviewed audit still reports zero third-party deps             #
# --------------------------------------------------------------------------- #
class DependenciesReviewedTests(unittest.TestCase):
    def test_security_audit_dependencies_reviewed_stays_green(self):
        from cosmosiq_ops.security_audit import _check_dependencies_reviewed
        repo_root = os.path.abspath(os.path.join(_HERE, ".."))
        category = _check_dependencies_reviewed(repo_root, _NOW)
        self.assertTrue(category.passed,
                        "dependencies_reviewed failed: {0}".format(category.findings))
        blob = " ".join(category.findings) + " " + " ".join(category.caveats)
        self.assertNotIn("yfinance", blob)


# --------------------------------------------------------------------------- #
# 8. End to end: mocked Yahoo adapter -> run_pulse -> technical_regime            #
# --------------------------------------------------------------------------- #
class LivePulseEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(YahooPriceLiveAdapter(transport=_transport()),))

    def test_technical_findings_come_from_live_yahoo_events(self):
        tr = [f for f in self.r.findings if f.discipline == "technical_regime"]
        self.assertTrue(tr)
        for f in tr:
            for ev_id in f.input_events:
                self.assertTrue(ev_id.startswith("yahoolive."),
                                "fixture event {0!r} leaked into technical_regime".format(ev_id))

    def test_technical_findings_stay_fallback_never_promoted(self):
        tr = [f for f in self.r.findings if f.discipline == "technical_regime"]
        self.assertTrue(tr)
        for f in tr:
            self.assertEqual(f.source_authority_summary, "fallback")
            self.assertNotEqual(f.source_authority_summary, "convenience")
            self.assertNotEqual(f.source_authority_summary, "canonical")

    def test_adapter_result_on_pulse_and_healthy(self):
        self.assertEqual(len(self.r.adapter_results), 1)
        result = self.r.adapter_results[0]
        self.assertIsInstance(result, SourceAdapterResult)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.adapter_id, YAHOO_PRICE_LIVE_ADAPTER_ID)
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "healthy")

    def test_pulse_with_the_live_adapter_is_deterministic(self):
        again = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(YahooPriceLiveAdapter(transport=_transport()),))
        self.assertEqual(self.r, again)


# --------------------------------------------------------------------------- #
# 9. Replay compatibility + default path byte-identical                          #
# --------------------------------------------------------------------------- #
class ReplayAndDefaultTests(unittest.TestCase):
    def test_persisted_live_pulse_replays_deterministically(self):
        pulse = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(YahooPriceLiveAdapter(transport=_transport()),))
        with tempfile.TemporaryDirectory() as store_dir:
            _pulse_run, replay, _panel = persist_and_summarize(
                pulse, store_dir=store_dir, run_id="RUN-YAHOOLIVE-PRODLIVE2", now=_NOW)
            self.assertTrue(replay.deterministic_match)
            self.assertGreater(pulse.events_loaded, 0)

    def test_default_pulse_stays_byte_identical(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        explicit_none = run_pulse(_WATCHLIST, _THEMES, now=_NOW, data_dir=None, adapters=None)
        self.assertEqual(base, explicit_none)                        # every field, byte for byte
        self.assertEqual(base.adapter_results, ())
        tr = [f for f in base.findings if f.discipline == "technical_regime"]
        self.assertTrue(all(not ev.startswith("yahoolive.")
                            for f in tr for ev in f.input_events))


# --------------------------------------------------------------------------- #
# 10. live_pulse opt-in: Yahoo joins credential-free (default set unchanged)      #
# --------------------------------------------------------------------------- #
class LivePulseWiringTests(unittest.TestCase):
    def test_default_build_live_adapters_has_no_yahoo(self):
        from reality_mesh.live_pulse import build_live_adapters
        adapters, notes = build_live_adapters(env={})
        self.assertEqual(adapters, ())                               # default byte-identical
        self.assertEqual(len(notes), 2)
        self.assertFalse(any("Yahoo" in n for n in notes))

    def test_opt_in_adds_credential_free_yahoo_fallback(self):
        from reality_mesh.live_pulse import build_live_adapters
        adapters, notes = build_live_adapters(env={}, include_price_fallback=True)
        self.assertEqual([type(a).__name__ for a in adapters], ["YahooPriceLiveAdapter"])
        self.assertTrue(any("Yahoo price fallback: configured" in n for n in notes))

    def test_opt_in_runs_price_fallback_with_no_credentials(self):
        from reality_mesh.live_pulse import run_live_pulse
        with tempfile.TemporaryDirectory() as store_dir:
            result = run_live_pulse(
                _WATCHLIST, _THEMES, store_dir=store_dir, now=_NOW,
                adapters=(YahooPriceLiveAdapter(transport=_transport()),),
                include_price_fallback=True)
        self.assertTrue(result.configured)
        self.assertTrue(result.persisted)
        by_id = {h.adapter_id: h for h in result.source_health}
        self.assertIn(YAHOO_PRICE_LIVE_ADAPTER_ID, by_id)
        self.assertEqual(by_id[YAHOO_PRICE_LIVE_ADAPTER_ID].authority, "fallback")
        self.assertEqual(by_id[YAHOO_PRICE_LIVE_ADAPTER_ID].credentials_status, "not_required")


if __name__ == "__main__":
    unittest.main()
