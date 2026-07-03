"""IMPLEMENTATION-014A — the source-adapter runtime + the local market-data adapter (OFFLINE).

Per SOURCE_ADAPTER_PRODUCTION_CONTRACT_013: adapters emit RealityEvents ONLY (never an
AgentFinding); source authority is explicit and assigned immediately; raw payload refs are
preserved; a source failure becomes a VISIBLE gap/health record -- never a crash, never a
fabricated value, never a silent demo fallback; credentials are env-only presence LABELS
(this slice needs NONE -- local files only); there is NO production network path in this
slice. The whole suite is offline; the default run_pulse path stays byte-identical.
"""
import ast
import io
import os
import re
import socket
import sys
import tempfile
import unittest
from dataclasses import fields as dc_fields

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh import labels as _labels
from reality_mesh.adapters import (
    ADAPTER_CREDENTIALS_STATUSES,
    ADAPTER_FAILURE_MODES,
    ADAPTER_RATE_LIMIT_STATUSES,
    ADAPTER_RESULT_STATUSES,
    ADAPTER_SOURCE_HEALTH_LABELS,
    LOCAL_MARKET_DATA_DESCRIPTOR,
    LOCAL_MARKET_DATA_DISCIPLINES,
    LOCAL_MARKET_DATA_FILES,
    LocalMarketDataAdapter,
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
    source_health_from_result,
)
from reality_mesh.health import SourceHealthRecord
from reality_mesh.models import AgentFinding, RealityEvent
from reality_mesh.pulse import PulseResult, run_pulse
from reality_mesh.validation import TRADE_FIELD_TOKENS, assert_no_trade_fields

_HERE = os.path.dirname(os.path.abspath(__file__))
_ADAPTERS_DIR = os.path.join(_HERE, "..", "src", "reality_mesh", "adapters")
_DATA_BASE = os.path.join(_HERE, "fixtures", "reality_mesh", "local_market_data")
_VALID_DIR = os.path.join(_DATA_BASE, "valid")
_STALE_DIR = os.path.join(_DATA_BASE, "stale")
_MALFORMED_DIR = os.path.join(_DATA_BASE, "malformed")
_MISSING_DIR = os.path.join(_DATA_BASE, "missing")

_WATCHLIST = "IREN,AAOI,AMBA,OUST"
_THEMES = "physical-ai,robotics"
_NOW = "2026-06-29T14:00:00Z"


def _descriptor(**overrides):
    kw = dict(
        adapter_id="test_adapter",
        source_name="Test source",
        source_type="market_data",
        source_authority="convenience",
        credential_requirements=(),
        network_required=False,
        rate_limit_policy="not_applicable: test",
        outputs=("index_breadth_reading",),
        claim_status_rules=("market reading -> claim_status=inferred",),
        failure_modes=("source_unavailable", "parse_error"),
    )
    kw.update(overrides)
    return SourceAdapterDescriptor(**kw)


def _result(**overrides):
    kw = dict(
        adapter_id="test_adapter",
        run_id="adapterrun.test_adapter.abc",
        status="success",
        events_created=0,
        credentials_status="not_required",
        rate_limit_status="ok",
        source_health="healthy",
    )
    kw.update(overrides)
    return SourceAdapterResult(**kw)


def _event(**overrides):
    kw = dict(
        event_id="ev.test",
        timestamp=_NOW,
        source_id="test.source",
        source_type="index_breadth_series",
        source_authority="convenience",
        claim_status="inferred",
        raw_payload_ref="localfile:test.json#sha256=deadbeef",
        discipline="market_regime",
        event_type="index_breadth_reading",
        source_refs=("localfile:test.json#sha256=deadbeef",),
    )
    kw.update(overrides)
    return RealityEvent(**kw)


class _StubAdapter(SourceAdapter):
    """A minimal test adapter returning whatever it was given (to probe fetch_checked)."""

    def __init__(self, outputs=(), result=None, descriptor=None, exc=None):
        self._outputs = tuple(outputs)
        self._result = result
        self._descriptor = descriptor or _descriptor()
        self._exc = exc

    @property
    def descriptor(self):
        return self._descriptor

    def fetch_events(self, *, watchlist=(), themes=(), now=""):
        if self._exc is not None:
            raise self._exc
        result = self._result or _result(events_created=len(self._outputs))
        return self._outputs, result


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# 1. Descriptor / Result construct + validate; label-only, no trade/score field #
# --------------------------------------------------------------------------- #
class DescriptorResultTests(unittest.TestCase):
    def test_descriptor_constructs_and_is_frozen(self):
        d = _descriptor()
        self.assertEqual(d.source_authority, "convenience")
        with self.assertRaises(Exception):
            d.adapter_id = "tampered"

    def test_descriptor_requires_nonempty_authority_assigned_immediately(self):
        with self.assertRaises(ValueError):
            _descriptor(source_authority="")
        with self.assertRaises(ValueError):
            _descriptor(source_authority="gospel")

    def test_credential_requirements_are_env_var_names_only(self):
        d = _descriptor(credential_requirements=("FMP_API_KEY",))
        self.assertEqual(d.credential_requirements, ("FMP_API_KEY",))
        for value_like in ("FMP_API_KEY=abc123", "sk-abc123", "fmp key", "", "lower_case"):
            with self.assertRaises(ValueError, msg=value_like):
                _descriptor(credential_requirements=(value_like,))

    def test_network_required_must_be_a_real_bool(self):
        with self.assertRaises(ValueError):
            _descriptor(network_required=1)
        with self.assertRaises(ValueError):
            _descriptor(network_required="no")

    def test_outputs_required_and_trade_score_tokens_rejected(self):
        with self.assertRaises(ValueError):
            _descriptor(outputs=())
        for bad in ("composite_score_feed", "buy_signal_reading", "sector_rank_series"):
            with self.assertRaises(ValueError, msg=bad):
                _descriptor(outputs=(bad,))

    def test_claim_status_rules_required(self):
        with self.assertRaises(ValueError):
            _descriptor(claim_status_rules=())

    def test_failure_modes_closed(self):
        with self.assertRaises(ValueError):
            _descriptor(failure_modes=("silent_demo_fallback",))
        self.assertEqual(
            ADAPTER_FAILURE_MODES,
            frozenset({"credentials_missing", "rate_limited", "source_unavailable",
                       "parse_error"}))

    def test_result_constructs_with_closed_labels(self):
        r = _result(status="partial", source_health="degraded",
                    data_gaps=("missing file x.json -- visible gap",))
        self.assertEqual(r.credentials_status, "not_required")
        self.assertIn(r.status, ADAPTER_RESULT_STATUSES)
        self.assertIn(r.rate_limit_status, ADAPTER_RATE_LIMIT_STATUSES)
        self.assertIn(r.source_health, ADAPTER_SOURCE_HEALTH_LABELS)

    def test_result_rejects_out_of_vocab_labels(self):
        with self.assertRaises(ValueError):
            _result(status="mostly_fine")
        with self.assertRaises(ValueError):
            _result(credentials_status="hunter2")   # a value, not a presence label
        with self.assertRaises(ValueError):
            _result(rate_limit_status="slow")
        with self.assertRaises(ValueError):
            _result(source_health="okish")

    def test_result_events_created_is_an_honest_volume_count(self):
        with self.assertRaises(ValueError):
            _result(events_created=-1)
        with self.assertRaises(ValueError):
            _result(events_created="4")
        with self.assertRaises(ValueError):
            _result(events_created=True)

    def test_failed_or_skipped_result_must_be_visible(self):
        # a failed/skipped result with NO error and NO gap would be a silent failure
        with self.assertRaises(ValueError):
            _result(status="failed", source_health="failed")
        r = _result(status="failed", source_health="failed",
                    errors=("source_failure: boom",),
                    data_gaps=("source failed -- visible gap",))
        self.assertEqual(r.status, "failed")

    def test_no_trade_or_score_field_on_either_class(self):
        assert_no_trade_fields(SourceAdapterDescriptor)   # raises if violated
        assert_no_trade_fields(SourceAdapterResult)
        for cls in (SourceAdapterDescriptor, SourceAdapterResult):
            for f in dc_fields(cls):
                for token in TRADE_FIELD_TOKENS:
                    self.assertNotIn(token, f.name.lower(),
                                     "{0}.{1}".format(cls.__name__, f.name))

    def test_source_health_labels_are_health_states(self):
        self.assertTrue(ADAPTER_SOURCE_HEALTH_LABELS <= _labels.HEALTH_STATES)
        self.assertEqual(ADAPTER_CREDENTIALS_STATUSES,
                         frozenset({"present", "missing", "not_required"}))

    def test_deterministic_run_id_is_content_derived(self):
        a = deterministic_adapter_run_id("x", (_NOW, "ref1"))
        b = deterministic_adapter_run_id("x", (_NOW, "ref1"))
        c = deterministic_adapter_run_id("x", (_NOW, "ref2"))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("adapterrun.x."))


# --------------------------------------------------------------------------- #
# 2. fetch_checked -- the boundary: RealityEvents ONLY; failure -> gap, no crash #
# --------------------------------------------------------------------------- #
class FetchCheckedTests(unittest.TestCase):
    def test_adapter_returning_a_finding_is_rejected(self):
        finding = AgentFinding(finding_id="f.bad", agent_id="a.bad")
        with self.assertRaises(ValueError) as ctx:
            _StubAdapter(outputs=(finding,)).fetch_checked(now=_NOW)
        self.assertIn("RealityEvent ONLY", str(ctx.exception))

    def test_adapter_returning_a_plain_dict_is_rejected(self):
        with self.assertRaises(ValueError):
            _StubAdapter(outputs=({"event_id": "x"},)).fetch_checked(now=_NOW)

    def test_event_without_source_authority_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _StubAdapter(outputs=(_event(source_authority=""),)).fetch_checked(now=_NOW)
        self.assertIn("source_authority", str(ctx.exception))

    def test_event_without_raw_payload_ref_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _StubAdapter(outputs=(_event(raw_payload_ref=""),)).fetch_checked(now=_NOW)
        self.assertIn("raw_payload_ref", str(ctx.exception))

    def test_event_without_any_evidence_or_source_ref_rejected(self):
        bad = _event(source_refs=(), evidence_refs=())
        with self.assertRaises(ValueError) as ctx:
            _StubAdapter(outputs=(bad,)).fetch_checked(now=_NOW)
        self.assertIn("provenance", str(ctx.exception))

    def test_valid_events_pass_through(self):
        events, result = _StubAdapter(outputs=(_event(),)).fetch_checked(now=_NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(result.status, "success")

    def test_dishonest_events_created_count_rejected(self):
        result = _result(events_created=5)   # but only one event returned
        with self.assertRaises(ValueError):
            _StubAdapter(outputs=(_event(),), result=result).fetch_checked(now=_NOW)

    def test_exception_becomes_failed_result_and_gap_never_propagates(self):
        adapter = _StubAdapter(exc=RuntimeError("disk exploded"))
        events, result = adapter.fetch_checked(now=_NOW)   # must NOT raise
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(any("disk exploded" in e for e in result.errors))
        self.assertTrue(any("visible gap" in g and "fabricated" in g
                            for g in result.data_gaps))
        self.assertTrue(any("demo fallback" in g for g in result.data_gaps))

    def test_network_required_adapter_is_refused_in_this_slice(self):
        adapter = _StubAdapter(outputs=(_event(),),
                               descriptor=_descriptor(network_required=True))
        events, result = adapter.fetch_checked(now=_NOW)   # refused, not fetched
        self.assertEqual(events, ())
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.source_health, "source_unavailable")
        self.assertTrue(any("network" in g.lower() for g in result.data_gaps))


# --------------------------------------------------------------------------- #
# 3. LocalMarketDataAdapter -- the first local-file-backed adapter               #
# --------------------------------------------------------------------------- #
class LocalMarketDataAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = LocalMarketDataAdapter(_VALID_DIR)
        cls.events, cls.result = cls.adapter.fetch_checked(
            watchlist=("IREN",), themes=("physical-ai",), now=_NOW)

    def test_descriptor_declares_the_contract(self):
        d = self.adapter.descriptor
        self.assertIs(d, LOCAL_MARKET_DATA_DESCRIPTOR)
        self.assertFalse(d.network_required)                 # LOCAL FILES ONLY
        self.assertEqual(d.source_authority, "convenience")  # operator-downloaded data
        self.assertEqual(d.credential_requirements, ())      # this slice needs NO credential
        self.assertEqual(set(d.failure_modes), {"source_unavailable", "parse_error"})
        self.assertTrue(any("inferred" in rule for rule in d.claim_status_rules))

    def test_covered_disciplines_are_the_three_priority_agents(self):
        self.assertEqual(self.adapter.covered_disciplines,
                         ("market_regime", "sector_rotation", "theme_rotation"))
        self.assertEqual(LOCAL_MARKET_DATA_DISCIPLINES, self.adapter.covered_disciplines)
        self.assertEqual(LOCAL_MARKET_DATA_FILES,
                         ("market_regime.json", "sector_rotation.json",
                          "theme_rotation.json"))

    def test_valid_set_succeeds_with_healthy_result(self):
        self.assertEqual(self.result.status, "success")
        self.assertEqual(self.result.source_health, "healthy")
        self.assertEqual(self.result.credentials_status, "not_required")
        self.assertEqual(self.result.rate_limit_status, "ok")
        self.assertEqual(self.result.events_created, len(self.events))
        self.assertEqual(len(self.result.raw_payload_refs), 3)

    def test_every_event_carries_authority_raw_ref_and_provenance(self):
        self.assertTrue(self.events)
        for ev in self.events:
            self.assertIsInstance(ev, RealityEvent)
            self.assertEqual(ev.source_authority, "convenience")
            self.assertTrue(ev.raw_payload_ref.startswith("localfile:"))
            self.assertIn("#sha256=", ev.raw_payload_ref)
            self.assertTrue(ev.evidence_refs or ev.source_refs)
            self.assertIn(ev.discipline, LOCAL_MARKET_DATA_DISCIPLINES)

    def test_claim_status_is_inferred_never_verified_fact(self):
        for ev in self.events:
            self.assertEqual(ev.claim_status, "inferred")

    def test_stronger_self_certified_authority_is_downgraded_visibly(self):
        # the sector file deliberately claims 'canonical' on one record
        self.assertTrue(any("downgraded source_authority 'canonical'" in w
                            for w in self.result.warnings))
        self.assertFalse(any(e.source_authority == "canonical" for e in self.events))

    def test_ids_are_deterministic_from_content(self):
        events2, result2 = LocalMarketDataAdapter(_VALID_DIR).fetch_checked(
            watchlist=("IREN",), themes=("physical-ai",), now=_NOW)
        self.assertEqual([e.event_id for e in self.events],
                         [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        # records without an event_id got a content-derived local.<discipline>.<sha> id
        derived = [e.event_id for e in self.events
                   if re.match(r"^local\.theme_rotation\.[0-9a-f]{12}$", e.event_id)]
        self.assertGreaterEqual(len(derived), 3)

    def test_missing_file_is_a_visible_gap_not_a_crash(self):
        events, result = LocalMarketDataAdapter(_MISSING_DIR).fetch_checked(now=_NOW)
        self.assertEqual(result.status, "partial")            # market_regime delivered
        self.assertEqual(result.source_health, "degraded")
        self.assertTrue(events)                               # what exists is delivered
        gaps = " ".join(result.data_gaps)
        self.assertIn("sector_rotation.json", gaps)           # the gap NAMES the file
        self.assertIn("theme_rotation.json", gaps)
        self.assertIn("never fabricated", gaps)
        self.assertIn("no silent demo fallback", gaps)
        # nothing was invented for the uncovered disciplines
        self.assertEqual({e.discipline for e in events}, {"market_regime"})

    def test_missing_data_dir_is_failed_with_gaps_per_file(self):
        events, result = LocalMarketDataAdapter(
            os.path.join(_DATA_BASE, "does_not_exist")).fetch_checked(now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertTrue(any("source_unavailable" in e for e in result.errors))
        self.assertEqual(len(result.data_gaps), 3)            # one visible gap per file

    def test_malformed_file_is_failed_with_parse_error(self):
        events, result = LocalMarketDataAdapter(_MALFORMED_DIR).fetch_checked(now=_NOW)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(any(e.startswith("parse_error: market_regime.json")
                            for e in result.errors))
        self.assertTrue(any("malformed" in g and "market_regime.json" in g
                            for g in result.data_gaps))
        # the good files' events are still delivered (surfaced, not hidden) -- but nothing
        # was fabricated for the malformed one
        self.assertFalse(any(e.discipline == "market_regime" for e in events))

    def test_stale_as_of_marks_events_stale_preserved_not_dropped(self):
        events, result = LocalMarketDataAdapter(_STALE_DIR).fetch_checked(now=_NOW)
        self.assertTrue(events)
        for ev in events:
            self.assertEqual(ev.freshness_label, "stale")
        self.assertTrue(any("stale as_of" in w and "marked" in w
                            for w in result.warnings))

    def test_csv_file_is_read_with_the_same_discipline_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "market_regime.csv"), "w", encoding="utf-8") as fh:
                fh.write("event_id,timestamp,event_type,observed_fact,metric,value,unit,"
                         "freshness_label,confidence_label,half_life,as_of\n")
                fh.write("local.csv.breadth,2026-06-29T13:30:00Z,index_breadth_reading,"
                         "pct above 200dma,pct_above_200dma,30,percent,fresh,moderate,days,"
                         "2026-06-29T13:30:00Z\n")
            events, result = LocalMarketDataAdapter(d).fetch_checked(now=_NOW)
            self.assertEqual(result.status, "partial")        # the other two files missing
            self.assertEqual(len(events), 1)
            ev = events[0]
            self.assertEqual(ev.discipline, "market_regime")
            self.assertEqual(ev.source_authority, "convenience")
            self.assertEqual(ev.numeric_values, (("pct_above_200dma", 30.0, "percent"),))
            self.assertTrue(ev.raw_payload_ref.startswith("localfile:market_regime.csv"))

    def test_source_health_record_surfaces_from_the_result(self):
        record = source_health_from_result(self.result, now=_NOW)
        self.assertIsInstance(record, SourceHealthRecord)
        self.assertEqual(record.source_id, "local_market_data")
        self.assertEqual(record.last_status, "healthy")
        self.assertEqual(record.credentials_status, "")       # not_required -> explicit gap
        self.assertEqual(record.last_success_at, _NOW)
        self.assertFalse(record.is_failed)
        # and a failed fetch maps to a VISIBLE failed record with a reason
        _, failed = LocalMarketDataAdapter(_MALFORMED_DIR).fetch_checked(now=_NOW)
        failed_record = source_health_from_result(failed, now=_NOW)
        self.assertTrue(failed_record.is_failed)
        self.assertEqual(failed_record.last_failure_at, _NOW)
        self.assertIn("parse_error", failed_record.unavailable_reason)


# --------------------------------------------------------------------------- #
# 4. The three agents consume adapter events -> findings -> fuse -> pulse E2E   #
# --------------------------------------------------------------------------- #
class AdapterPulseEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW, data_dir=_VALID_DIR)

    def test_three_priority_agents_produced_findings_from_adapter_events(self):
        for discipline in ("market_regime", "sector_rotation", "theme_rotation"):
            found = [f for f in self.r.findings if f.discipline == discipline]
            self.assertTrue(found, "expected a {0} finding".format(discipline))
            for f in found:
                # every input event of these findings came from the adapter, not fixtures
                for ev_id in f.input_events:
                    self.assertTrue(ev_id.startswith("local."),
                                    "fixture event {0!r} leaked into {1}".format(
                                        ev_id, discipline))

    def test_fusion_and_theme_pulses_ran_on_adapter_events(self):
        self.assertTrue(any(s.discipline in ("sector_rotation", "theme_rotation",
                                             "market_regime", "cross_discipline")
                            for s in self.r.signals))
        by_name = {p.theme_name: p for p in self.r.theme_pulses}
        self.assertIn("physical-ai", by_name)
        self.assertEqual(by_name["physical-ai"].state, "Broadening")

    def test_uncovered_disciplines_still_come_from_fixtures(self):
        # news/filings + X/social are NOT covered by this adapter; fixtures still feed them
        self.assertTrue(any(f.discipline == "news_filings" for f in self.r.findings))
        self.assertTrue(any(f.discipline == "narrative" for f in self.r.findings))

    def test_adapter_results_returned_on_pulse_result(self):
        self.assertEqual(len(self.r.adapter_results), 1)
        result = self.r.adapter_results[0]
        self.assertIsInstance(result, SourceAdapterResult)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.credentials_status, "not_required")
        # ... and it feeds a real SourceHealthRecord (013F consumes these)
        record = source_health_from_result(result, now=_NOW)
        self.assertEqual(record.last_status, "healthy")

    def test_missing_source_file_in_pulse_is_a_gap_never_fixture_fallback(self):
        r = run_pulse(_WATCHLIST, _THEMES, now=_NOW, data_dir=_MISSING_DIR)
        # no crash; market regime delivered from the adapter's one file
        self.assertTrue(any(f.discipline == "market_regime" for f in r.findings))
        # the covered-but-missing disciplines are NOT silently backfilled from fixtures
        self.assertFalse(any(f.discipline in ("sector_rotation", "theme_rotation")
                             for f in r.findings))
        gaps = " ".join(r.data_gaps)
        self.assertIn("sector_rotation.json", gaps)
        self.assertIn("theme_rotation.json", gaps)
        self.assertEqual(r.adapter_results[0].status, "partial")

    def test_stale_source_files_surface_as_stale_findings(self):
        r = run_pulse(_WATCHLIST, _THEMES, now=_NOW, data_dir=_STALE_DIR)
        stale = [f for f in r.findings
                 if f.discipline in LOCAL_MARKET_DATA_DISCIPLINES
                 and f.freshness_label == "stale"]
        self.assertTrue(stale, "stale adapter events must yield stale-labelled findings")
        self.assertTrue(any("stale" in g.lower() for g in
                            [g for f in stale for g in f.data_gaps]))

    def test_explicit_adapters_argument_works_too(self):
        r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                      adapters=(LocalMarketDataAdapter(_VALID_DIR),))
        self.assertEqual(len(r.adapter_results), 1)
        self.assertEqual(r.adapter_results[0].status, "success")

    def test_pulse_is_deterministic_with_a_data_dir(self):
        a = run_pulse(_WATCHLIST, _THEMES, now=_NOW, data_dir=_VALID_DIR)
        b = run_pulse(_WATCHLIST, _THEMES, now=_NOW, data_dir=_VALID_DIR)
        self.assertEqual(a, b)


# --------------------------------------------------------------------------- #
# 5. Default path byte-identical; opt-in only                                   #
# --------------------------------------------------------------------------- #
class DefaultPathUnchangedTests(unittest.TestCase):
    def test_run_pulse_default_path_is_byte_identical(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        explicit_none = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                                  data_dir=None, adapters=None)
        self.assertEqual(base, explicit_none)                # every field, byte for byte
        self.assertEqual(base.adapter_results, ())           # the new field stays empty
        self.assertIsInstance(base, PulseResult)

    def test_default_pulse_still_reads_fixture_market_regime(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        mr = [f for f in base.findings if f.discipline == "market_regime"]
        self.assertTrue(mr)
        self.assertTrue(all(ev.startswith("pulse.") for f in mr for ev in f.input_events),
                        "the default path must keep consuming the bundled pulse fixtures")


# --------------------------------------------------------------------------- #
# 6. Guardrails: offline; no net/scheduler/broker import; no score/rank def     #
# --------------------------------------------------------------------------- #
class GuardrailTests(unittest.TestCase):
    _BANNED_IMPORT_ROOTS = (
        "socket", "requests", "urllib", "http", "sched", "schedule", "apscheduler",
        "crontab", "asyncio", "threading", "multiprocessing", "subprocess", "smtplib",
        "ftplib", "socketserver", "telnetlib", "websocket", "websockets", "aiohttp",
        "httpx", "broker", "signal",
    )

    def _adapter_files(self):
        return sorted(
            os.path.join(_ADAPTERS_DIR, n) for n in os.listdir(_ADAPTERS_DIR)
            if n.endswith(".py"))

    def test_no_network_scheduler_or_broker_import_in_adapters(self):
        paths = self._adapter_files()
        self.assertGreaterEqual(len(paths), 3)   # __init__ + base + local_market_data
        for path in paths:
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                for name in names:
                    for banned in self._BANNED_IMPORT_ROOTS:
                        self.assertFalse(
                            name == banned or name.startswith(banned + "."),
                            "banned import {0!r} in {1}".format(name, path))

    def test_no_score_rank_or_rating_function_defs(self):
        for path in self._adapter_files():
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                     "banned fn name {0!r} in {1}".format(node.name, path))

    def test_no_scheduler_loop_or_wall_clock_construct(self):
        for path in self._adapter_files():
            low = _read(path).lower()
            for token in ("while true", "run_forever", "serve_forever", "start_polling",
                          "schedule.every", "set_interval", "datetime.now(", "utcnow(",
                          "time.time("):
                self.assertNotIn(token, low,
                                 "forbidden construct {0!r} in {1}".format(token, path))

    def test_network_required_false_on_the_local_adapter(self):
        self.assertFalse(LOCAL_MARKET_DATA_DESCRIPTOR.network_required)

    def test_offline_socket_kill_switch(self):
        orig = socket.socket.connect

        def _block(*a, **k):
            raise AssertionError("network blocked: adapters must be fully offline")

        socket.socket.connect = _block
        try:
            events, result = LocalMarketDataAdapter(_VALID_DIR).fetch_checked(now=_NOW)
            self.assertEqual(result.status, "success")
            r = run_pulse(_WATCHLIST, _THEMES, now=_NOW, data_dir=_VALID_DIR)
            self.assertTrue(r.findings)
            run_pulse(_WATCHLIST, _THEMES, now=_NOW)          # default path offline too
        finally:
            socket.socket.connect = orig

    def test_no_secret_shaped_content_in_results(self):
        _, result = LocalMarketDataAdapter(_VALID_DIR).fetch_checked(now=_NOW)
        blob = " ".join(result.warnings + result.errors + result.data_gaps).lower()
        for bad in ("api_key", "apikey", "password", "secret_key"):
            self.assertNotIn(bad, blob)
        self.assertNotRegex(blob, r"\bsk-[a-z0-9]{6}")


if __name__ == "__main__":
    unittest.main()
