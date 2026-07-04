"""IMPLEMENTATION-014D — the Technical Regime sensor agent + the local price-history adapter.

Per the accepted alpha-chain discipline: TECHNICAL STATES ARE LABELS, NEVER TRADE SIGNALS.
The agent emits AgentFinding ONLY (discipline ``technical_regime``, reusing the built-in
``tattva.technical_regime`` descriptor) with direction labels only -- no buy / sell / entry
/ exit / target / stop language anywhere (regex-swept below). The adapter emits
RealityEvents ONLY at ``convenience`` authority from LOCAL files; missing / malformed /
stale input becomes a VISIBLE gap, never a fabricated value. The whole suite is offline;
the DEFAULT run_pulse path stays byte-identical (the new sensor runs only when
technical_regime events exist).
"""
import ast
import os
import re
import socket
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh import labels as _labels
from reality_mesh.adapters import (
    LOCAL_PRICE_HISTORY_DESCRIPTOR,
    LOCAL_PRICE_HISTORY_DISCIPLINES,
    PRICE_HISTORY_FILE_SUFFIX,
    PRICE_HISTORY_INDICATOR_UNITS,
    LocalPriceHistoryAdapter,
    SourceAdapterResult,
    source_health_from_result,
)
from reality_mesh.agents import TATTVA_FINDING_SUBTYPES
from reality_mesh.models import AgentFinding, RealityEvent
from reality_mesh.pulse import PulseResult, run_pulse
from reality_mesh.registry import build_default_registry
from reality_mesh.sensors import (
    TECHNICAL_REGIME_FINDING_TYPES,
    TECHNICAL_REGIME_SUBAGENTS,
    TECHNICAL_SUBAGENT_REQUIRED_KEYS,
    TechnicalRegimeAgent,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "src", "reality_mesh")
_DATA_BASE = os.path.join(_HERE, "fixtures", "reality_mesh", "local_price_history")
_VALID_DIR = os.path.join(_DATA_BASE, "valid")
_STALE_DIR = os.path.join(_DATA_BASE, "stale")
_MALFORMED_DIR = os.path.join(_DATA_BASE, "malformed")
_MISSING_DIR = os.path.join(_DATA_BASE, "missing")

_WATCHLIST = "IREN,AAOI,AMBA,SERV"
_THEMES = "physical-ai,robotics"
_NOW = "2026-06-29T14:00:00Z"

# Trade-language tokens that may NEVER appear in ANY finding field: a technical state is a
# LABEL informing Investment Diligence timing, never a trade instruction.
_TRADE_TOKEN_RE = re.compile(
    r"\b(buy|buys|buying|sell|sells|selling|entry|entries|exit|exits|target|targets|"
    r"stop|stops|stop-loss|order|orders|position|accumulate|trim|hold)\b",
    re.IGNORECASE)


def _agent_findings(data_dir, watchlist=("IREN",)):
    events, _ = LocalPriceHistoryAdapter(data_dir).fetch_checked(
        watchlist=watchlist, themes=(), now=_NOW)
    return TechnicalRegimeAgent().run_checked(None, events)


def _by_type(findings, finding_type, ticker=None):
    out = [f for f in findings if f.finding_type == finding_type]
    if ticker is not None:
        out = [f for f in out if ticker in f.affected_companies]
    return out


def _all_strings_of(finding):
    """Every string value carried by a finding (scalar fields + tuple elements)."""
    values = []
    for name in finding.__dataclass_fields__:
        value = getattr(finding, name)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, tuple):
            values.extend(str(v) for v in value)
    return values


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# 1. Identity: the built-in descriptor is reused; six subagents; emit contract  #
# --------------------------------------------------------------------------- #
class AgentIdentityTests(unittest.TestCase):
    def test_agent_reuses_the_builtin_descriptor(self):
        agent = TechnicalRegimeAgent()
        registry = build_default_registry()
        self.assertIs(agent.descriptor, registry.get("tattva.technical_regime"))
        self.assertEqual(agent.descriptor.discipline, "technical_regime")
        self.assertEqual(agent.descriptor.layer, "reality_intelligence")

    def test_descriptor_emits_technical_regime_finding_only(self):
        desc = TechnicalRegimeAgent().descriptor
        self.assertEqual(set(desc.emits), {"AgentFinding", "TechnicalRegimeFinding"})
        self.assertIn("TechnicalRegimeFinding", TATTVA_FINDING_SUBTYPES)

    def test_six_structural_subagents_match_the_registry(self):
        desc = TechnicalRegimeAgent().descriptor
        self.assertEqual(desc.subagents, TECHNICAL_REGIME_SUBAGENTS)
        self.assertEqual(
            TECHNICAL_REGIME_SUBAGENTS,
            ("Compression", "Breakout", "EMA Stack", "VWAP", "Failure/Reversal",
             "Overextension"))
        self.assertEqual(set(TECHNICAL_SUBAGENT_REQUIRED_KEYS),
                         set(TECHNICAL_REGIME_SUBAGENTS))

    def test_finding_types_are_labels_with_closed_directions(self):
        for finding_type in TECHNICAL_REGIME_FINDING_TYPES:
            self.assertIsNone(_TRADE_TOKEN_RE.search(finding_type), finding_type)


# --------------------------------------------------------------------------- #
# 2. The agent: AgentFinding-only labels from price-history readings            #
# --------------------------------------------------------------------------- #
class AgentFindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings = _agent_findings(
            _VALID_DIR, watchlist=("IREN", "AAOI", "AMBA", "SERV"))

    def test_emits_agent_findings_only_in_discipline(self):
        self.assertTrue(self.findings)
        for f in self.findings:
            self.assertIsInstance(f, AgentFinding)
            self.assertEqual(f.discipline, "technical_regime")
            self.assertEqual(f.agent_id, "tattva.technical_regime")
            self.assertIn(f.finding_type, TECHNICAL_REGIME_FINDING_TYPES)

    def test_breakout_fixture_yields_breakout_confirmed_improving(self):
        found = _by_type(self.findings, "breakout_confirmed", "IREN")
        self.assertEqual(len(found), 1)
        f = found[0]
        self.assertEqual(f.direction_label, "improving")
        self.assertEqual(f.urgency_label, "elevated")
        self.assertEqual(f.magnitude_label, "major")    # >= 1.5x volume expansion
        self.assertIn("breakout confirmed", f.finding_summary)
        self.assertIn("expanding volume", f.finding_summary)

    def test_ema_broken_fixture_yields_deteriorating(self):
        found = _by_type(self.findings, "ema_stack_broken", "AAOI")
        self.assertEqual(len(found), 1)
        f = found[0]
        self.assertEqual(f.direction_label, "deteriorating")
        self.assertEqual(f.magnitude_label, "major")    # fully inverted stack
        self.assertIn("8>21>50>200", f.finding_summary)
        loss = _by_type(self.findings, "vwap_loss", "AAOI")
        self.assertEqual(len(loss), 1)
        self.assertEqual(loss[0].direction_label, "deteriorating")

    def test_compression_fixture_yields_neutral_with_elevated_urgency(self):
        found = _by_type(self.findings, "compression_forming", "AMBA")
        self.assertEqual(len(found), 1)
        f = found[0]
        self.assertEqual(f.direction_label, "neutral")
        self.assertEqual(f.urgency_label, "elevated")
        self.assertIn("either direction", f.finding_summary)

    def test_aligned_stack_and_vwap_reclaim_are_improving(self):
        aligned = _by_type(self.findings, "ema_stack_aligned", "IREN")
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0].direction_label, "improving")
        reclaim = _by_type(self.findings, "vwap_reclaim", "IREN")
        self.assertEqual(len(reclaim), 1)
        self.assertEqual(reclaim[0].direction_label, "improving")

    def test_failed_breakout_is_deteriorating(self):
        # SERV (bars-derived): pushed above the prior range high, closed back below it.
        found = _by_type(self.findings, "breakout_failed", "SERV")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction_label, "deteriorating")
        self.assertIn("closed back below", found[0].finding_summary)

    def test_every_label_is_closed_vocabulary(self):
        for f in self.findings:
            self.assertIn(f.direction_label, _labels.DIRECTION_LABELS)
            self.assertIn(f.magnitude_label, _labels.MAGNITUDE_LABELS)
            self.assertIn(f.urgency_label, _labels.URGENCY_LABELS)
            self.assertIn(f.confidence_label, _labels.CONFIDENCE_LABELS)
            self.assertIn(f.freshness_label, _labels.FRESHNESS_LABELS)
            self.assertEqual(f.source_authority_summary, "convenience")
            self.assertEqual(f.half_life, "days")
            self.assertEqual(f.routing_targets, ("TattvaSignalFusion",))

    def test_findings_trace_to_adapter_events(self):
        for f in self.findings:
            self.assertTrue(f.input_events)
            for ev_id in f.input_events:
                self.assertTrue(ev_id.startswith("local.technical_regime."), ev_id)
            self.assertTrue(f.source_refs or f.evidence_refs)

    def test_no_trade_language_in_any_finding_field(self):
        # The gate: technical states are LABELS. Sweep EVERY string field of every finding
        # produced from every fixture set (valid + stale + missing indicators).
        all_findings = list(self.findings)
        all_findings.extend(_agent_findings(_STALE_DIR))
        all_findings.extend(_agent_findings(_MISSING_DIR))
        self.assertTrue(all_findings)
        for f in all_findings:
            for text in _all_strings_of(f):
                match = _TRADE_TOKEN_RE.search(text)
                self.assertIsNone(
                    match, "trade token {0!r} leaked into finding field: {1!r}".format(
                        match.group(0) if match else "", text))

    def test_stale_input_yields_stale_finding_plus_gap(self):
        findings = _agent_findings(_STALE_DIR)
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f.freshness_label, "stale")   # preserved, never dropped
            self.assertTrue(
                any("stale price-history data preserved (not dropped)" in g
                    for g in f.data_gaps), f.data_gaps)

    def test_missing_indicator_is_a_gap_never_computed(self):
        # The 'missing' fixture omits ema200 / vwap / pct_above_ema21 for IREN.
        findings = _agent_findings(_MISSING_DIR)
        self.assertTrue(findings)
        types = {f.finding_type for f in findings}
        for absent in ("ema_stack_aligned", "ema_stack_broken", "vwap_reclaim",
                       "vwap_loss", "overextension"):
            self.assertNotIn(absent, types)                 # never computed from nothing
        gaps = " | ".join(g for f in findings for g in f.data_gaps)
        self.assertIn("EMA Stack subagent has no reading", gaps)
        self.assertIn("VWAP subagent has no reading", gaps)
        self.assertIn("Overextension subagent has no reading", gaps)
        self.assertIn("never computed from nothing", gaps)

    def test_ticker_with_no_reading_at_all_yields_explicit_incomplete_finding(self):
        event = RealityEvent(
            event_id="local.technical_regime.zzzz.deadbeef",
            timestamp=_NOW, source_id="local_file.price_history.zzzz",
            source_type="local_price_history_file", source_authority="convenience",
            claim_status="inferred", raw_payload_ref="localfile:x#sha256=0",
            discipline="technical_regime", event_type="price_history_reading",
            affected_companies=("ZZZZ",), source_refs=("localfile:x#sha256=0",))
        findings = TechnicalRegimeAgent().run_checked(None, (event,))
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.finding_type, "technical_read_incomplete")
        self.assertEqual(f.direction_label, "neutral")
        self.assertEqual(len(f.data_gaps), len(TECHNICAL_REGIME_SUBAGENTS))

    def test_unscoped_event_is_surfaced_not_guessed(self):
        event = RealityEvent(
            event_id="local.technical_regime.unscoped.1",
            timestamp=_NOW, source_id="local_file.price_history",
            source_type="local_price_history_file", source_authority="convenience",
            claim_status="inferred", raw_payload_ref="localfile:x#sha256=0",
            discipline="technical_regime", event_type="price_history_reading",
            numeric_values=(("close", 10.0, "usd"),),
            source_refs=("localfile:x#sha256=0",))
        findings = TechnicalRegimeAgent().run_checked(None, (event,))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].finding_type, "technical_read_incomplete")
        self.assertTrue(any("no ticker" in g for g in findings[0].data_gaps))

    def test_out_of_discipline_events_are_ignored(self):
        event = RealityEvent(
            event_id="ev.other", timestamp=_NOW, source_id="s", source_type="t",
            source_authority="convenience", claim_status="inferred",
            raw_payload_ref="localfile:y#sha256=1", discipline="market_regime",
            event_type="index_breadth_reading", source_refs=("localfile:y#sha256=1",),
            numeric_values=(("pct_above_200dma", 30, "percent"),))
        self.assertEqual(TechnicalRegimeAgent().run_checked(None, (event,)), ())

    def test_run_is_deterministic(self):
        again = _agent_findings(_VALID_DIR, watchlist=("IREN", "AAOI", "AMBA", "SERV"))
        self.assertEqual(self.findings, again)


# --------------------------------------------------------------------------- #
# 3. The adapter: LOCAL files -> RealityEvents ONLY at convenience authority     #
# --------------------------------------------------------------------------- #
class LocalPriceHistoryAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = LocalPriceHistoryAdapter(_VALID_DIR)
        cls.events, cls.result = cls.adapter.fetch_checked(
            watchlist=("IREN", "AAOI", "AMBA", "SERV"), themes=(), now=_NOW)

    def test_descriptor_declares_the_contract(self):
        d = self.adapter.descriptor
        self.assertIs(d, LOCAL_PRICE_HISTORY_DESCRIPTOR)
        self.assertFalse(d.network_required)                 # LOCAL FILES ONLY
        self.assertEqual(d.source_authority, "convenience")  # operator-downloaded OHLCV
        self.assertEqual(d.credential_requirements, ())      # no credential exists to need
        self.assertEqual(d.outputs, ("price_history_reading",))
        self.assertEqual(set(d.failure_modes), {"source_unavailable", "parse_error"})
        self.assertEqual(self.adapter.covered_disciplines, ("technical_regime",))
        self.assertEqual(LOCAL_PRICE_HISTORY_DISCIPLINES, ("technical_regime",))

    def test_emits_reality_events_only_with_authority_and_provenance(self):
        self.assertEqual(self.result.status, "success")
        self.assertEqual(self.result.source_health, "healthy")
        self.assertEqual(self.result.credentials_status, "not_required")
        self.assertEqual(self.result.rate_limit_status, "ok")
        self.assertEqual(len(self.events), 4)                # one event per ticker file
        for ev in self.events:
            self.assertIsInstance(ev, RealityEvent)
            self.assertNotIsInstance(ev, AgentFinding)
            self.assertEqual(ev.discipline, "technical_regime")
            self.assertEqual(ev.event_type, "price_history_reading")
            self.assertEqual(ev.source_authority, "convenience")
            self.assertEqual(ev.claim_status, "inferred")    # derived, never verified_fact
            self.assertTrue(ev.raw_payload_ref.startswith("localfile:"))
            self.assertIn("#sha256=", ev.raw_payload_ref)
            self.assertTrue(ev.source_refs)
            self.assertEqual(len(ev.affected_companies), 1)

    def test_numeric_values_carry_units(self):
        for ev in self.events:
            self.assertTrue(ev.numeric_values)
            for name, value, unit in ev.numeric_values:
                self.assertIn(name, PRICE_HISTORY_INDICATOR_UNITS)
                self.assertEqual(unit, PRICE_HISTORY_INDICATOR_UNITS[name])
                self.assertIsInstance(value, float)

    def test_self_certified_canonical_is_downgraded_visibly(self):
        # the AAOI file deliberately claims 'canonical'
        self.assertTrue(any("downgraded source_authority 'canonical'" in w
                            for w in self.result.warnings))
        self.assertFalse(any(ev.source_authority == "canonical" for ev in self.events))

    def test_daily_bars_are_derived_with_honest_insufficiency_gaps(self):
        serv = next(ev for ev in self.events if ev.affected_companies == ("SERV",))
        readings = {name: value for name, value, _unit in serv.numeric_values}
        self.assertEqual(readings["close"], 12.9)            # last bar close
        self.assertEqual(readings["recent_volume"], 2000000.0)
        self.assertEqual(readings["avg_volume"], 1000000.0)  # mean of the 20 prior bars
        for present in ("ema8", "ema21", "vwap", "range_high", "range_pct",
                        "pct_above_ema21", "recent_high"):
            self.assertIn(present, readings)
        for absent in ("ema50", "ema200"):                   # 30 bars cannot derive these
            self.assertNotIn(absent, readings)
        gaps = " ".join(serv.data_gaps)
        self.assertIn("insufficient price history for ema200", gaps)
        self.assertIn("insufficient price history for ema50", gaps)
        self.assertIn("never fabricated", gaps)
        # the derivation gaps stay visible on the run result too
        self.assertTrue(any("ema200" in g for g in self.result.data_gaps))

    def test_ids_are_deterministic_from_content(self):
        events2, result2 = LocalPriceHistoryAdapter(_VALID_DIR).fetch_checked(
            watchlist=("IREN", "AAOI", "AMBA", "SERV"), themes=(), now=_NOW)
        self.assertEqual([e.event_id for e in self.events],
                         [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        for ev in self.events:
            self.assertRegex(ev.event_id,
                             r"^local\.technical_regime\.[a-z0-9]+\.[0-9a-f]{12}$")

    def test_missing_watchlist_ticker_is_a_visible_gap_not_a_crash(self):
        events, result = LocalPriceHistoryAdapter(_MISSING_DIR).fetch_checked(
            watchlist=("IREN", "OUST"), themes=(), now=_NOW)
        self.assertEqual(result.status, "partial")           # IREN delivered
        self.assertEqual(result.source_health, "degraded")
        self.assertEqual(len(events), 1)
        gaps = " ".join(result.data_gaps)
        self.assertIn("OUST" + PRICE_HISTORY_FILE_SUFFIX, gaps)   # the gap NAMES the file
        self.assertIn("never fabricated", gaps)
        self.assertIn("no silent demo fallback", gaps)

    def test_missing_data_dir_is_failed_with_gaps(self):
        events, result = LocalPriceHistoryAdapter(
            os.path.join(_DATA_BASE, "does_not_exist")).fetch_checked(
            watchlist=("IREN", "OUST"), themes=(), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertTrue(any("source_unavailable" in e for e in result.errors))
        self.assertEqual(len(result.data_gaps), 2)           # one visible gap per ticker

    def test_malformed_file_is_failed_with_parse_error(self):
        events, result = LocalPriceHistoryAdapter(_MALFORMED_DIR).fetch_checked(
            watchlist=("IREN",), themes=(), now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(any(
            e.startswith("parse_error: IREN" + PRICE_HISTORY_FILE_SUFFIX)
            for e in result.errors))
        self.assertTrue(any("malformed" in g and "nothing fabricated" in g
                            for g in result.data_gaps))

    def test_stale_as_of_marks_the_event_stale_preserved_not_dropped(self):
        events, result = LocalPriceHistoryAdapter(_STALE_DIR).fetch_checked(
            watchlist=("IREN",), themes=(), now=_NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].freshness_label, "stale")
        self.assertTrue(any("stale as_of" in w and "never dropped" in w
                            for w in result.warnings))

    def test_result_feeds_a_real_source_health_record(self):
        record = source_health_from_result(self.result, now=_NOW)
        self.assertEqual(record.source_id, "local_price_history")
        self.assertEqual(record.last_status, "healthy")
        self.assertFalse(record.is_failed)
        _, failed = LocalPriceHistoryAdapter(_MALFORMED_DIR).fetch_checked(now=_NOW)
        self.assertTrue(source_health_from_result(failed, now=_NOW).is_failed)

    def test_empty_data_dir_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            LocalPriceHistoryAdapter("")


# --------------------------------------------------------------------------- #
# 4. End to end: adapter -> pulse -> technical findings -> fusion -> signals     #
# --------------------------------------------------------------------------- #
class PulseEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(LocalPriceHistoryAdapter(_VALID_DIR),))

    def test_technical_regime_agent_ran_and_produced_findings(self):
        runs = [a for a in self.r.agent_runs if a.agent_id == "tattva.technical_regime"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "ok")
        self.assertEqual(runs[0].events_seen, 4)
        found = [f for f in self.r.findings if f.discipline == "technical_regime"]
        self.assertTrue(found)
        for f in found:
            for ev_id in f.input_events:
                self.assertTrue(ev_id.startswith("local."), ev_id)

    def test_findings_fused_into_technical_regime_signals(self):
        signals = [s for s in self.r.signals if s.discipline == "technical_regime"]
        self.assertTrue(signals)
        for s in signals:
            self.assertEqual(self.r.authority_by_signal.get(s.signal_id), "convenience")

    def test_other_disciplines_still_come_from_fixtures(self):
        for discipline in ("market_regime", "sector_rotation", "theme_rotation",
                           "news_filings", "narrative"):
            self.assertTrue(any(f.discipline == discipline for f in self.r.findings),
                            discipline)

    def test_adapter_result_returned_on_pulse(self):
        self.assertEqual(len(self.r.adapter_results), 1)
        result = self.r.adapter_results[0]
        self.assertIsInstance(result, SourceAdapterResult)
        self.assertEqual(result.adapter_id, "local_price_history")
        self.assertEqual(result.status, "success")

    def test_failed_source_in_pulse_is_a_gap_never_a_fixture_fallback(self):
        r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                      adapters=(LocalPriceHistoryAdapter(_MALFORMED_DIR),))
        # nothing fabricated: no technical events -> the conditional agent did not run
        self.assertFalse(any(f.discipline == "technical_regime" for f in r.findings))
        self.assertFalse(any(a.agent_id == "tattva.technical_regime"
                             for a in r.agent_runs))
        self.assertTrue(any("malformed" in g and "nothing fabricated" in g
                            for g in r.data_gaps))
        self.assertEqual(r.adapter_results[0].status, "failed")

    def test_pulse_with_adapter_is_deterministic(self):
        a = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                      adapters=(LocalPriceHistoryAdapter(_VALID_DIR),))
        b = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                      adapters=(LocalPriceHistoryAdapter(_VALID_DIR),))
        self.assertEqual(a, b)

    def test_no_trade_language_anywhere_in_the_pulse_technical_output(self):
        for f in self.r.findings:
            if f.discipline != "technical_regime":
                continue
            for text in _all_strings_of(f):
                self.assertIsNone(_TRADE_TOKEN_RE.search(text), text)


# --------------------------------------------------------------------------- #
# 5. The DEFAULT pulse stays byte-identical (the sensor is event-gated)          #
# --------------------------------------------------------------------------- #
class DefaultPulseUnchangedTests(unittest.TestCase):
    def test_default_pulse_is_byte_identical_and_has_no_technical_agent_run(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        explicit_none = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                                  data_dir=None, adapters=None)
        self.assertEqual(base, explicit_none)               # every field, byte for byte
        self.assertIsInstance(base, PulseResult)
        # The bundled fixtures carry no technical_regime events, so the new sensor does
        # NOT join the default agent set: agent_runs stays the original five, and no
        # technical finding / gap / signal appears anywhere.
        self.assertEqual(len(base.agent_runs), 5)
        self.assertEqual(
            [a.agent_id for a in base.agent_runs],
            ["tattva.market_regime", "tattva.sector_rotation", "tattva.theme_rotation",
             "tattva.news_filings", "tattva.narrative"])
        self.assertFalse(any(f.discipline == "technical_regime" for f in base.findings))
        self.assertFalse(any(s.discipline == "technical_regime" for s in base.signals))
        self.assertFalse(any("technical" in g.lower() for g in base.data_gaps))
        self.assertEqual(base.adapter_results, ())

    def test_default_pulse_is_deterministic_run_to_run(self):
        a = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        b = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        self.assertEqual(a, b)


# --------------------------------------------------------------------------- #
# 6. Guardrails: offline; AST-clean; no scheduler / broker / score / wall-clock  #
# --------------------------------------------------------------------------- #
class GuardrailTests(unittest.TestCase):
    _NEW_FILES = (
        os.path.join(_SRC, "sensors", "technical_regime.py"),
        os.path.join(_SRC, "adapters", "local_price_history.py"),
    )
    _BANNED_IMPORT_ROOTS = (
        "socket", "requests", "urllib", "http", "sched", "schedule", "apscheduler",
        "crontab", "asyncio", "threading", "multiprocessing", "subprocess", "smtplib",
        "ftplib", "socketserver", "telnetlib", "websocket", "websockets", "aiohttp",
        "httpx", "broker", "signal",
    )

    def test_no_network_scheduler_or_broker_import(self):
        for path in self._NEW_FILES:
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
        for path in self._NEW_FILES:
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                     "banned fn name {0!r} in {1}".format(node.name, path))

    def test_no_scheduler_loop_or_wall_clock_construct(self):
        for path in self._NEW_FILES:
            low = _read(path).lower()
            for token in ("while true", "run_forever", "serve_forever", "start_polling",
                          "schedule.every", "set_interval", "datetime.now(", "utcnow(",
                          "time.time("):
                self.assertNotIn(token, low,
                                 "forbidden construct {0!r} in {1}".format(token, path))

    def test_offline_socket_kill_switch(self):
        orig = socket.socket.connect

        def _block(*a, **k):
            raise AssertionError("network blocked: 014D must be fully offline")

        socket.socket.connect = _block
        try:
            events, result = LocalPriceHistoryAdapter(_VALID_DIR).fetch_checked(now=_NOW)
            self.assertEqual(result.status, "success")
            findings = TechnicalRegimeAgent().run_checked(None, events)
            self.assertTrue(findings)
            r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(LocalPriceHistoryAdapter(_VALID_DIR),))
            self.assertTrue(any(f.discipline == "technical_regime" for f in r.findings))
            run_pulse(_WATCHLIST, _THEMES, now=_NOW)          # default path offline too
        finally:
            socket.socket.connect = orig

    def test_no_secret_shaped_content_in_results(self):
        _, result = LocalPriceHistoryAdapter(_VALID_DIR).fetch_checked(now=_NOW)
        blob = " ".join(result.warnings + result.errors + result.data_gaps).lower()
        for bad in ("api_key", "apikey", "password", "secret_key"):
            self.assertNotIn(bad, blob)


if __name__ == "__main__":
    unittest.main()
