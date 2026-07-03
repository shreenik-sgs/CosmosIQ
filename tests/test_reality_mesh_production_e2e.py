"""IMPLEMENTATION-013G — operator docs + the production-hardening E2E (TEST_MATRIX_013 §I + full chain).

The FINAL Phase-013 slice: the complete offline production chain proven end to end —

    run_pulse -> persist_and_summarize -> append-only stores populated (schema_version on every
    record) -> verification replay (deterministic_match=True) -> gate run (no hard fail on a
    clean pulse) -> health roll-ups -> observability panel -> build_universe_app Data-Quality
    page (pulse + observability panels, closed link graph)

plus a FAILURE-INJECTED variant (a raising agent is isolated -> failed result + gap; the run
still yields RunHealthSummary + DataQualityRunSummary = degraded, honestly rendered), a
TAMPERED-store variant (a mutated persisted record -> deterministic_match=False, the divergence
named and surfaced, the replayability gate FAILS), the append-only re-assert (store bytes are
byte-unchanged by any replay), the §I guardrail re-asserts (no scheduler / broker / network
import anywhere in reality_mesh; no affordance / secret / Sanskrit term in the rendered page;
demo default byte-identical; trigger_type manual-only), and the docs-check that the
OPERATOR_GUIDE_013 command actually builds offline (mirrors the 012 e2e's guide check).

The ENTIRE module runs under a socket kill-switch installed in setUpModule — every pulse,
persist, replay, gate run, render, and CLI invocation here is proven offline. Deterministic:
injected ``now``, caller-supplied run ids, temp-dir JSONL stores, no wall-clock anywhere.
MANUAL / ON-DEMAND ONLY — no scheduler, no daemon, no streaming, no broker, no order, no score.
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling test modules import

import reality_mesh as rm
from reality_mesh import labels as L
from reality_mesh import stores as S
from reality_mesh.gates import DataQualityGateResult, DataQualityGateRunner
from reality_mesh.health import AgentHealthMonitor, SourceHealthRecord
from reality_mesh.ledger import AgentRunLedger
from reality_mesh.pulse_persistence import agent_results_from_pulse, persist_and_summarize
from reality_mesh.render_adapters import build_run_observability_panel
from reality_mesh.runtime import PulseRun
from cosmosiq_pulse import main as cosmosiq_main
from universe_ui.app import build_universe_app

# Reuse the 010G closed-graph checker (the 012J / 013F pattern).
from test_terrain_interaction import HtmlLinkGraph, _cockpit_files  # type: ignore

_MESH_DIR = os.path.join(_SRC, "reality_mesh")
_GUIDE = os.path.join(_ROOT, "docs", "OPERATOR_GUIDE_013.md")

_NOW = "2026-06-29T00:00:00Z"
_RUN_ID = "RUN-013G"

# English-only surface: no Sanskrit layer term may reach a rendered page. ("tattva" appears in
# the operator guide ONLY inside the deprecated `tattva_pulse` alias mention — checked separately.)
_SANSKRIT = ("tattva", "sphurana", "buddhi", "adhara", "nivesha", "kriya",
             "anubhava", "saarathi", "sankalpa")
_FORBIDDEN_PAGE_TOKENS = ("<button", "<form", "onclick", 'type="submit"', "place order",
                          "api_key", "apikey", "sk-", "secret", "password")

# Module roots whose import anywhere in reality_mesh would mean a scheduler / daemon / streaming
# / network / broker capability crept in (TEST_MATRIX_013 §I1/§I2/§I6).
_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "crontab", "asyncio", "threading", "multiprocessing",
                        "subprocess", "smtplib", "ftplib", "socketserver", "broker")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline production E2E")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _snapshot_bytes(store_dir):
    out = {}
    for name in sorted(os.listdir(store_dir)):
        with open(os.path.join(store_dir, name), "rb") as fh:
            out[name] = fh.read()
    return out


def _harness(store_dir):
    return rm.ReplayHarness(S.EventStore(store_dir), S.FindingStore(store_dir),
                            S.SignalStore(store_dir), S.ThemePulseStore(store_dir),
                            S.RunStore(store_dir))


def _gate_run(store_dir, pulse, replay):
    """Re-run the eleven production gates over the PERSISTED records of a run."""
    return DataQualityGateRunner().run(
        signals=S.SignalStore(store_dir).query(run_id=_RUN_ID),
        findings=S.FindingStore(store_dir).query(run_id=_RUN_ID),
        events=S.EventStore(store_dir).query(run_id=_RUN_ID),
        records=S.ThemePulseStore(store_dir).query(run_id=_RUN_ID),
        authority_by_signal=dict(pulse.authority_by_signal or {}),
        run_mode="pulse",
        replay_results=(replay,))


# --------------------------------------------------------------------------- #
# Module fixture: the WHOLE chain, built ONCE, entirely under the kill-switch   #
# --------------------------------------------------------------------------- #
_STATE = {}
_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket

    pulse = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW)
    store_dir = tempfile.mkdtemp(prefix="prod_013g_store_")
    pulse_run, replay, panel = persist_and_summarize(
        pulse, store_dir=store_dir, run_id=_RUN_ID, now=_NOW)

    out_dir = tempfile.mkdtemp(prefix="prod_013g_pages_")
    paths = build_universe_app(
        out_dir, mode="demo",
        pulse_signals=pulse.signals, signal_clusters=pulse.clusters,
        theme_pulses=pulse.theme_pulses,
        pulse_authority_by_signal=pulse.authority_by_signal,
        run_observability_html=panel)

    _STATE.update(
        pulse=pulse, store_dir=store_dir, pulse_run=pulse_run, replay=replay,
        panel=panel, paths=paths, dq_html=_read(paths["data_quality.html"]))


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


# =========================================================================== #
# 1. The full production chain, end to end (clean pulse)                       #
# =========================================================================== #
class ProductionChainTests(unittest.TestCase):
    def test_all_stores_populated(self):
        d = _STATE["store_dir"]
        for name in ("run_store.jsonl", "event_store.jsonl", "finding_store.jsonl",
                     "signal_store.jsonl", "theme_pulse_store.jsonl",
                     "data_quality_store.jsonl", "agent_run_ledger.jsonl"):
            path = os.path.join(d, name)
            self.assertTrue(os.path.isfile(path), "missing store {0}".format(name))
            self.assertGreater(os.path.getsize(path), 0, "empty store {0}".format(name))
        runs = S.RunStore(d).query(run_id=_RUN_ID)
        self.assertEqual([r.run_id for r in runs], [_RUN_ID])
        self.assertGreater(len(S.SignalStore(d).query(run_id=_RUN_ID)), 0)
        self.assertGreater(len(S.ThemePulseStore(d).query(run_id=_RUN_ID)), 0)
        # one ledger result per sensor agent of the pulse
        self.assertEqual(len(AgentRunLedger(d).results_for_run(_RUN_ID)),
                         len(_STATE["pulse"].agent_runs))
        # the eleven gate verdicts + the overall roll-up landed in the DataQualityStore
        self.assertGreaterEqual(len(S.DataQualityStore(d).query(run_id=_RUN_ID)), 12)

    def test_schema_version_on_every_persisted_record(self):
        d = _STATE["store_dir"]
        checked = 0
        for name in sorted(os.listdir(d)):
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        rec = json.loads(line)
                        self.assertEqual(rec.get("schema_version"), S.SCHEMA_VERSION,
                                         "record without schema_version in {0}".format(name))
                        self.assertTrue(rec.get("record_id"),
                                        "record without record_id in {0}".format(name))
                        checked += 1
        self.assertGreater(checked, 10)

    def test_verification_replay_deterministic_match(self):
        self.assertTrue(_STATE["replay"].deterministic_match)
        self.assertEqual(_STATE["replay"].differences, ())
        self.assertEqual(_STATE["replay"].source_run_id, _RUN_ID)
        # a FRESH harness over the same stores reproduces the run too
        again = _harness(_STATE["store_dir"]).replay(rm.ReplayRequest(run_id=_RUN_ID), now=_NOW)
        self.assertTrue(again.deterministic_match)
        self.assertEqual(again.differences, ())

    def test_gate_run_no_hard_fail_on_a_clean_pulse(self):
        results, overall = _gate_run(_STATE["store_dir"], _STATE["pulse"], _STATE["replay"])
        self.assertEqual(len(results), 11)
        self.assertEqual([r.category for r in results if r.status == "fail"], [])
        # honest weak-social signals in the fixture pulse -> a WARN, so overall reads degraded
        self.assertIn(overall, ("healthy", "degraded"))
        by_cat = {r.category: r for r in results}
        self.assertEqual(by_cat["replayability"].status, "pass")
        self.assertEqual(by_cat["scheduler_broker_trading_guardrail"].status, "pass")
        self.assertEqual(by_cat["social_weak_signal"].status, "warn")  # surfaced, not hidden

    def test_health_rollups_from_the_persisted_run(self):
        results = agent_results_from_pulse(_STATE["pulse"], run_id=_RUN_ID, now=_NOW)
        monitor = AgentHealthMonitor()
        run_health = monitor.build_run_health_summary(
            _RUN_ID, results, gaps=_STATE["pulse"].data_gaps)
        dq = monitor.build_data_quality_summary(
            _RUN_ID, results, gaps=_STATE["pulse"].data_gaps)
        self.assertEqual(run_health.overall_status, "healthy")  # every sensor ran clean
        self.assertEqual(run_health.agents_failed, 0)
        self.assertEqual(run_health.agents_blocked, 0)
        self.assertEqual(dq.status, "healthy")
        self.assertEqual(len(monitor.roll_agent_health(results)), len(results))

    def test_observability_panel_renders(self):
        panel = _STATE["panel"]
        self.assertIn("Run observability", panel)
        self.assertIn(_RUN_ID, panel)
        self.assertIn("replayable · deterministic_match: True", panel)
        self.assertIn("manual pulse · not scheduled", panel)

    def test_dq_page_carries_both_panels_with_closed_link_graph(self):
        dq = _STATE["dq_html"]
        self.assertIn("Manual pulse — reality signals", dq)          # the 012J evidence panel
        self.assertIn("Run observability — persisted pulse", dq)     # the 013F panel
        HtmlLinkGraph(dq).assert_no_dead_anchors(self, _cockpit_files(_STATE["paths"]))

    def test_correction_is_a_new_audit_record_never_a_mutation(self):
        d = _STATE["store_dir"]
        dq_store_path = os.path.join(d, "data_quality_store.jsonl")
        with open(dq_store_path, "rb") as fh:
            before = fh.read()
        target = S.DataQualityStore(d).read_records()[0]["record_id"]
        audit = S.AuditStore(d)
        audit.append_correction(
            audit_id="audit.corr.1", corrects=target, run_id=_RUN_ID, actor="human",
            at=_NOW, reason="operator annotation -- supersedes, never edits")
        with open(dq_store_path, "rb") as fh:
            self.assertEqual(fh.read(), before)  # the corrected store is byte-unchanged
        corrections = [a for a in audit.query(run_id=_RUN_ID) if a.is_correction]
        self.assertEqual([a.corrects for a in corrections], [target])


# =========================================================================== #
# 2. FAILURE-INJECTED variant: an isolated crash, a degraded-but-honest run    #
# =========================================================================== #
def _event(event_id="E1"):
    return rm.RealityEvent(
        event_id=event_id, timestamp=_NOW, source_id="src.sec",
        source_type="sec_filing", source_authority="canonical",
        claim_status="verified_fact", discipline="market_regime", event_type="8-K",
        affected_companies=("IREN",), affected_themes=("physical_ai",),
        evidence_refs=("ex1",), source_refs=("sec:0001",),
        confidence_label="high", freshness_label="fresh", half_life="days")


def _finding(finding_id="F1"):
    return rm.AgentFinding(
        finding_id=finding_id, agent_id="a.ok", agent_layer="reality_intelligence",
        agent_name="ok", discipline="market_regime", input_events=("E1",),
        finding_type="AgentFinding", affected_companies=("IREN",),
        affected_themes=("physical_ai",), direction_label="stable",
        magnitude_label="minor", confidence_label="moderate", freshness_label="recent",
        half_life="days", source_authority_summary="canonical",
        evidence_refs=("ex1",), routing_targets=("SignalFusion",))


class _FakeAgent(rm.SensorAgent):
    def __init__(self, agent_id, behaviour):
        self._agent_id = agent_id
        self._behaviour = behaviour

    @property
    def descriptor(self):
        return rm.AgentDescriptor(
            agent_id=self._agent_id, layer="reality_intelligence",
            discipline="market_regime", agent_type="sensor", emits=("AgentFinding",))

    def run(self, context, events):
        return self._behaviour(context, events)


class FailureInjectedRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def _boom(context, events):
            raise RuntimeError("injected fixture parse failure")

        ok = _FakeAgent("a.ok", lambda context, events: (_finding("F1"),))
        boom = _FakeAgent("a.boom", _boom)
        items = [
            (rm.AgentRunContext(run_id="RUN-INJ", agent_id="a.ok",
                                input_event_ids=("E1",)), (_event(),)),
            (rm.AgentRunContext(run_id="RUN-INJ", agent_id="a.boom",
                                input_event_ids=("E1",)), (_event(),)),
        ]
        cls.results = rm.run_agents_isolated([ok, boom], items, now=_NOW)

        cls.store_dir = tempfile.mkdtemp(prefix="prod_013g_inj_")
        ledger = AgentRunLedger(cls.store_dir)
        for r in cls.results:
            ledger.append_result(r)

        monitor = AgentHealthMonitor()
        source = SourceHealthRecord(source_id="local_fixture", last_status="healthy",
                                    credentials_status="present", rate_limit_status="ok",
                                    last_success_at=_NOW)
        cls.run_health = monitor.build_run_health_summary(
            "RUN-INJ", cls.results, sources=(source,))
        cls.dq_summary = monitor.build_data_quality_summary(
            "RUN-INJ", cls.results, sources=(source,))
        cls.panel = build_run_observability_panel(
            run_health=cls.run_health, dq_summary=cls.dq_summary,
            agent_health=monitor.roll_agent_health(cls.results),
            source_health=(source,),
            gate_results=(DataQualityGateResult(category="source_authority", status="pass"),))

    def test_raising_agent_isolated_not_a_crash(self):
        by_agent = {r.agent_id: r for r in self.results}
        self.assertEqual(len(self.results), 2)          # every agent produced a result
        self.assertEqual(by_agent["a.ok"].status, "success")
        failed = by_agent["a.boom"]
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.health_status, "failed")
        self.assertEqual(failed.finding_ids, ())        # nothing fabricated
        self.assertTrue(failed.data_gaps)               # a VISIBLE gap
        self.assertTrue(any("RuntimeError" in e for e in failed.errors))

    def test_degraded_run_still_yields_both_summaries(self):
        self.assertEqual(self.run_health.overall_status, "degraded")
        self.assertEqual(self.run_health.agents_failed, 1)
        self.assertEqual(self.run_health.agents_run, 1)
        self.assertGreaterEqual(self.run_health.data_gap_count, 1)
        self.assertEqual(self.dq_summary.status, "degraded")  # honest, never hidden

    def test_failed_results_logged_to_the_ledger(self):
        logged = AgentRunLedger(self.store_dir).results_for_run("RUN-INJ")
        self.assertEqual({r.agent_id: r.status for r in logged},
                         {"a.ok": "success", "a.boom": "failed"})

    def test_panel_shows_the_degraded_run_honestly(self):
        self.assertIn("Run observability", self.panel)
        self.assertIn(">degraded<", self.panel)
        self.assertIn("a.boom", self.panel)
        self.assertIn(">failed<", self.panel)


# =========================================================================== #
# 3. TAMPERED-store variant: a divergence is SURFACED, never a silent pass     #
# =========================================================================== #
class TamperedStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store_dir = tempfile.mkdtemp(prefix="prod_013g_tamper_")
        pulse = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW)
        cls.pulse = pulse
        cls.clean_run, clean_replay, _ = persist_and_summarize(
            pulse, store_dir=cls.store_dir, run_id=_RUN_ID, now=_NOW)
        assert clean_replay.deterministic_match

        # Tamper ONE persisted signal field (to a DIFFERENT valid label -- a plausible edit).
        path = os.path.join(cls.store_dir, "signal_store.jsonl")
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        record = json.loads(lines[0])
        original = record["payload"]["direction_label"]
        record["payload"]["direction_label"] = next(
            lab for lab in sorted(L.DIRECTION_LABELS) if lab != original)
        lines[0] = json.dumps(record, sort_keys=True, separators=(",", ":"))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

        cls.replay = _harness(cls.store_dir).replay(rm.ReplayRequest(run_id=_RUN_ID), now=_NOW)

    def test_tampered_history_fails_deterministic_match(self):
        self.assertFalse(self.replay.deterministic_match)
        self.assertTrue(self.replay.differences)
        self.assertTrue(any("direction_label" in d for d in self.replay.differences),
                        "the divergent field must be NAMED in differences")

    def test_replayability_gate_hard_fails_and_rolls_the_run(self):
        runner = DataQualityGateRunner()
        gate = runner.check_replayability((self.replay,))
        self.assertEqual(gate.status, "fail")
        results, overall = _gate_run(self.store_dir, self.pulse, self.replay)
        self.assertIn("replayability", [r.category for r in results if r.status == "fail"])
        self.assertEqual(overall, "failed")  # worst gate verdict, not a policy block

    def test_divergence_surfaced_on_the_panel(self):
        panel = build_run_observability_panel(replay_result=self.replay)
        self.assertIn("replayable · deterministic_match: False", panel)
        self.assertIn("{0} difference(s)".format(len(self.replay.differences)), panel)


# =========================================================================== #
# 4. Append-only re-assert: replay NEVER changes a stored byte                 #
# =========================================================================== #
class AppendOnlyReplayTests(unittest.TestCase):
    def test_store_bytes_unchanged_by_replays(self):
        with tempfile.TemporaryDirectory() as d:
            pulse = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW)
            persist_and_summarize(pulse, store_dir=d, run_id="RUN-RO", now=_NOW)
            before = _snapshot_bytes(d)
            harness = _harness(d)
            harness.replay(rm.ReplayRequest(run_id="RUN-RO"), now=_NOW)
            harness.replay(rm.ReplayRequest(ticker="IREN"), now=_NOW)
            harness.replay(rm.ReplayRequest(theme="physical_ai"), now=_NOW)
            self.assertEqual(before, _snapshot_bytes(d))

    def test_stores_expose_no_mutating_method(self):
        for cls in S.STORE_CLASSES + (AgentRunLedger,):
            for banned in ("update", "delete", "remove", "overwrite", "__setitem__",
                           "__delitem__", "truncate"):
                self.assertFalse(hasattr(cls, banned) and callable(getattr(cls, banned, None))
                                 and banned in vars(cls),
                                 "{0} exposes mutating {1}".format(cls.__name__, banned))


# =========================================================================== #
# 5. §I guardrail re-asserts (offline, manual-only, no affordance / secret)    #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    def test_socket_kill_switch_is_active_for_this_module(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()

    def test_no_scheduler_broker_or_network_import_across_reality_mesh(self):
        py_files = []
        for base, _dirs, names in os.walk(_MESH_DIR):
            py_files.extend(os.path.join(base, n) for n in names if n.endswith(".py"))
        self.assertGreaterEqual(len(py_files), 20)  # the whole package, incl. sensors + 013 files
        for path in sorted(py_files):
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                for name in names:
                    for banned in _BANNED_IMPORT_ROOTS:
                        self.assertFalse(
                            name == banned or name.startswith(banned + "."),
                            "banned import {0!r} in {1}".format(name, path))

    def test_rendered_page_has_no_affordance_secret_or_sanskrit(self):
        low = _STATE["dq_html"].lower()
        for bad in _FORBIDDEN_PAGE_TOKENS:
            self.assertNotIn(bad, low, "forbidden token in DQ page: {0}".format(bad))
        for term in _SANSKRIT:
            self.assertNotIn(term, low, "Sanskrit term in rendered page: {0}".format(term))
        self.assertNotRegex(low, r"\bsk-[a-z0-9]{6}")

    def test_no_trade_verb_or_hidden_metric_in_page_data(self):
        data_only = re.sub(r'<p class="note">.*?</p>', "", _STATE["dq_html"].lower(), flags=re.S)
        self.assertNotRegex(data_only,
                            r"\b(buy|sell|hold|submit|top pick|strong buy|price target)\b")
        self.assertNotRegex(data_only, r"\b(investability|score:|rank #|rating:)\b")
        self.assertNotRegex(data_only, r"\b(always[- ]on|real[- ]time|streaming|24/7|live feed)\b")

    def test_demo_default_byte_identical(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                self.assertEqual(_read(a[name]), _read(b[name]),
                                 "demo default drifted for {0}".format(name))
            self.assertNotIn("Run observability", _read(a["data_quality.html"]))

    def test_trigger_type_is_manual_only(self):
        for reserved in ("scheduled", "streaming"):
            with self.assertRaises(ValueError):
                PulseRun(run_id="X", trigger_type=reserved)
        self.assertEqual(_STATE["pulse_run"].trigger_type, "manual")
        persisted = S.RunStore(_STATE["store_dir"]).query(run_id=_RUN_ID)
        self.assertEqual([r.trigger_type for r in persisted], ["manual"])

    def test_no_secret_or_score_key_in_any_persisted_line(self):
        for name in sorted(os.listdir(_STATE["store_dir"])):
            with open(os.path.join(_STATE["store_dir"], name), encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    for key in _all_keys(json.loads(line)):
                        low = key.lower()
                        for token in S.CREDENTIAL_KEY_TOKENS + S.FORBIDDEN_FIELD_TOKENS:
                            self.assertNotIn(token, low,
                                             "banned key {0!r} persisted in {1}".format(key, name))


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            for sub in _all_keys(v):
                yield sub
    elif isinstance(obj, list):
        for v in obj:
            for sub in _all_keys(v):
                yield sub


# =========================================================================== #
# 6. Operator docs: the OPERATOR_GUIDE_013 command actually builds, OFFLINE    #
# =========================================================================== #
class OperatorGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _read(_GUIDE)
        cls.low = cls.text.lower()
        # markdown wraps lines; phrase checks run against whitespace-normalized text
        cls.norm = re.sub(r"\s+", " ", cls.text)
        cls.norm_low = cls.norm.lower()

    def test_guide_documents_the_production_workflow(self):
        for token in ("cosmosiq_pulse", "--watchlist", "--themes", "--out", "--persist-dir",
                      "deterministic_match", "append-only", "ReplayHarness", "ReplayRequest",
                      "RunHealthSummary", "DataQualityRunSummary", "DataQualityGateRunner"):
            self.assertIn(token, self.text, "guide missing {0!r}".format(token))
        # the append-only stores + correction discipline are all named
        for store in ("run_store.jsonl", "event_store.jsonl", "finding_store.jsonl",
                      "signal_store.jsonl", "theme_pulse_store.jsonl",
                      "data_quality_store.jsonl", "agent_run_ledger.jsonl",
                      "audit_store.jsonl"):
            self.assertIn(store, self.text, "guide missing store {0!r}".format(store))
        self.assertIn("correction is a NEW record", self.text)

    def test_guide_states_the_hard_fail_list_and_failure_isolation(self):
        for phrase in ("verified_fact", "canonical", "hidden `score`",
                       "silent demo fallback", "network call at module import",
                       "scheduler / daemon / broker"):
            self.assertIn(phrase, self.norm, "guide missing hard-fail item {0!r}".format(phrase))
        self.assertIn("One failed agent or source never crashes a run", self.norm)
        self.assertIn("degraded", self.low)

    def test_guide_states_deferred_and_forbidden_items_explicitly(self):
        # scheduler -> Phase 015 + a new ADR; execution -> manual preview only, expansion
        # approval-gated (Phase 020+); live X -> weak-signal-only, Phase 014, LAST.
        self.assertIn("Phase 015", self.text)
        self.assertIn("requires a new ADR", self.text)
        self.assertIn("manual execution preview only", self.text)
        self.assertIn("Phase 020+", self.text)
        self.assertIn("approval-gated", self.text)
        self.assertIn("Phase 014", self.text)
        self.assertIn("weak-signal-only", self.text)
        self.assertRegex(self.text, r"X/social comes LAST")

    def test_guide_uses_english_terminology_only(self):
        for term in _SANSKRIT:
            if term == "tattva":
                continue  # allowed ONLY inside the deprecated `tattva_pulse` alias mention
            self.assertNotIn(term, self.low, "Sanskrit term in guide: {0}".format(term))
        hits = list(re.finditer("tattva", self.norm_low))
        self.assertTrue(hits, "the guide must name the deprecated tattva_pulse alias once")
        for m in hits:
            self.assertEqual(self.norm_low[m.start():m.start() + len("tattva_pulse")],
                             "tattva_pulse",
                             "'tattva' outside the tattva_pulse alias token")
            window = self.norm_low[m.start():m.start() + 200]
            self.assertTrue("deprecated" in window or "alias" in window,
                            "tattva_pulse may appear only as the deprecated alias: "
                            "{0!r}".format(window))
        self.assertIn("manual", self.low)
        self.assertIn("on-demand", self.low)

    def test_documented_command_actually_builds_offline(self):
        # The exact section-1 command (module-level socket kill-switch proves it is offline).
        self.assertIn("python3 -m cosmosiq_pulse", self.text)
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as store:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cosmosiq_main([
                    "--watchlist", "IREN,AAOI,AMBA,OUST",
                    "--themes", "physical-ai,robotics,ai-power",
                    "--out", out, "--persist-dir", store])
            self.assertEqual(rc, 0)
            log = buf.getvalue()
            self.assertIn("manual pulse", log.lower())
            self.assertIn("run persisted · replayable (deterministic_match: True)", log)
            for name in ("universe.html", "data_quality.html", "pulse_summary.json"):
                self.assertTrue(os.path.isfile(os.path.join(out, name)),
                                "missing output {0}".format(name))
            for name in ("run_store.jsonl", "agent_run_ledger.jsonl",
                         "data_quality_store.jsonl"):
                self.assertTrue(os.path.isfile(os.path.join(store, name)),
                                "missing persisted store {0}".format(name))
            self.assertIn("Run observability",
                          _read(os.path.join(out, "data_quality.html")))


if __name__ == "__main__":
    unittest.main()
