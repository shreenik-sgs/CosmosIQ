"""IMPLEMENTATION-013F — pulse persistence + UI links (TEST_MATRIX_013 §H1–H4, §G1–G4 + globals).

Offline. A PERSISTED pulse run's metadata (run / agent / source health, gate results, replay
metadata) surfaces on the Trust & Data-Quality page as EVIDENCE + OBSERVABILITY — never a trade
action. The surface is ADDITIVE and opt-in: with nothing supplied the demo / real / enriched /
pulse output stays byte-identical. The new rendered elements introduce NO ``data-intel`` refs and
NO ``href="#..."`` anchors (the closed link graph stays trivially intact); no credential value,
no hidden metric, no Sanskrit layer terminology, no scheduler / broker / order affordance.
Degraded / failed agent + source states are shown honestly, never hidden; the replay metadata
proves ``deterministic_match`` on the persisted run.
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
from reality_mesh import stores as S
from reality_mesh.gates import DataQualityGateResult
from reality_mesh.health import AgentHealthMonitor, SourceHealthRecord
from reality_mesh.ledger import AgentRunLedger
from reality_mesh.pulse_persistence import (
    PULSE_FIXTURE_SOURCE_ID,
    agent_results_from_pulse,
    persist_and_summarize,
)
from reality_mesh.render_adapters import build_run_observability_panel
from reality_mesh.runtime import AgentRunResult, ReplayResult
from tattva_pulse.__main__ import main as pulse_cli_main
from universe_ui.app import build_universe_app

# Reuse the 010G closed-graph checker (the 012J pattern).
from test_terrain_interaction import HtmlLinkGraph, _cockpit_files  # type: ignore

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_NEW_FILES = (
    os.path.join(_PKG_DIR, "pulse_persistence.py"),
    os.path.join(_PKG_DIR, "render_adapters.py"),
)

_NOW = "2026-06-29T00:00:00Z"
_SANSKRIT = ("tattva", "sphurana", "buddhi", "adhara", "nivesha", "prometheus_sankalpa")
_FORBIDDEN_PAGE_TOKENS = ("<button", "<form", "onclick", 'type="submit"', "place order",
                          "api_key", "apikey", "sk-", "secret")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _pulse():
    return rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW)


def _read(paths, name):
    with open(paths[name], encoding="utf-8") as fh:
        return fh.read()


def _persisted(store_dir, run_id="RUN-013F"):
    return persist_and_summarize(_pulse(), store_dir=store_dir, run_id=run_id, now=_NOW)


def _result(agent_id, status, errors=(), gaps=(), health="healthy"):
    return AgentRunResult(run_id="RUN-DEG", agent_id=agent_id, status=status,
                          started_at=_NOW, completed_at=_NOW, errors=tuple(errors),
                          data_gaps=tuple(gaps), health_status=health)


# A degraded batch: one success, one FAILED, one policy-blocked (all must stay VISIBLE).
_DEGRADED_RESULTS = (
    _result("agent.alpha", "success"),
    _result("agent.beta", "failed", errors=("ValueError: fixture parse failure",),
            gaps=("agent agent.beta failed in run RUN-DEG -- isolated",), health="failed"),
    _result("agent.gamma", "blocked_by_policy",
            errors=("output refused: forbidden downstream use",),
            gaps=("agent agent.gamma blocked by policy",), health="blocked_by_policy"),
)

# A failed source: credentials missing + rate limited -- a VISIBLE gap (presence labels only).
_FAILED_SOURCE = SourceHealthRecord(
    source_id="sec_edgar", last_status="credentials_missing",
    credentials_status="missing", rate_limit_status="rate_limited",
    last_failure_at=_NOW,
    unavailable_reason="credential absent -- visible gap, not a crash and not a leak")
_OK_SOURCE = SourceHealthRecord(
    source_id="local_fixture", last_status="healthy", credentials_status="present",
    rate_limit_status="ok", last_success_at=_NOW)


def _degraded_panel():
    monitor = AgentHealthMonitor()
    run_health = monitor.build_run_health_summary(
        "RUN-DEG", _DEGRADED_RESULTS, sources=(_FAILED_SOURCE, _OK_SOURCE))
    dq_summary = monitor.build_data_quality_summary(
        "RUN-DEG", _DEGRADED_RESULTS, sources=(_FAILED_SOURCE, _OK_SOURCE))
    gates = (
        DataQualityGateResult(category="source_authority", status="pass"),
        DataQualityGateResult(category="freshness", status="warn",
                              findings=("1 input honestly labelled stale",)),
        DataQualityGateResult(category="replayability", status="fail",
                              findings=("replay diverged",)),
    )
    replay = ReplayResult(replay_id="replay.deadbeef", source_run_id="RUN-DEG",
                          deterministic_match=False, differences=("signal s1 diverged",))
    return build_run_observability_panel(
        run_health=run_health, dq_summary=dq_summary,
        agent_health=monitor.roll_agent_health(_DEGRADED_RESULTS),
        source_health=(_FAILED_SOURCE, _OK_SOURCE),
        gate_results=gates, replay_result=replay)


# =========================================================================== #
# §H1/§H2 -- a persisted fixture pulse renders run/agent/source health + replay #
# =========================================================================== #
class PersistedPulsePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store_dir = tempfile.mkdtemp(prefix="pp_013f_")
        cls.pulse_run, cls.replay, cls.html = _persisted(cls.store_dir)

    def test_run_metadata_visible(self):
        self.assertIn("Run metadata", self.html)
        self.assertIn("RUN-013F", self.html)
        self.assertIn("<td>pulse</td>", self.html)                       # mode
        self.assertIn("manual pulse · not scheduled", self.html)          # trigger wording
        self.assertIn(_NOW, self.html)                                    # started/completed
        self.assertIn("events {0}".format(self.pulse_run.events_created), self.html)
        self.assertIn("signals {0}".format(self.pulse_run.signals_created), self.html)
        self.assertIn(S.SCHEMA_VERSION, self.html)                        # schema version
        self.assertIn("013F", self.html)                                  # runtime version

    def test_agent_health_visible_with_english_layer_terms(self):
        self.assertIn("Agent health", self.html)
        # every sensor agent surfaces, with its legacy layer prefix normalized to English
        self.assertIn("reality_intelligence.market_regime", self.html)
        self.assertIn("reality_intelligence.news_filings", self.html)
        low = self.html.lower()
        for term in _SANSKRIT:
            self.assertNotIn(term, low, "Sanskrit term in output: {0}".format(term))

    def test_source_health_visible(self):
        self.assertIn("Source health", self.html)
        self.assertIn(PULSE_FIXTURE_SOURCE_ID, self.html)
        self.assertIn("healthy", self.html)
        # presence-only credentials label; never a credential value
        self.assertIn("presence label only", self.html)

    def test_gate_results_visible(self):
        self.assertIn("Data-quality gate results", self.html)
        self.assertIn("source_authority", self.html)
        self.assertIn("replayability", self.html)
        self.assertIn(">pass<", self.html)
        # the fixture pulse carries honest weak-social signals -> a WARN badge, surfaced
        self.assertIn(">warn<", self.html)

    def test_replay_metadata_visible_and_deterministic_match_true(self):
        self.assertTrue(self.replay.deterministic_match)
        self.assertEqual(self.replay.differences, ())
        self.assertIn("replayable · deterministic_match: True", self.html)
        self.assertIn("0 difference(s)", self.html)
        self.assertIn(self.replay.source_run_id, self.html)

    def test_run_and_agent_results_persisted(self):
        runs = S.RunStore(self.store_dir).query(run_id="RUN-013F")
        self.assertEqual([r.run_id for r in runs], ["RUN-013F"])
        self.assertEqual(runs[0].trigger_type, "manual")
        ledger = AgentRunLedger(self.store_dir).results_for_run("RUN-013F")
        self.assertEqual(len(ledger), 5)  # one result per sensor agent
        self.assertTrue(all(r.status in ("success", "skipped", "partial") for r in ledger))
        gate_records = S.DataQualityStore(self.store_dir).query(run_id="RUN-013F")
        self.assertGreaterEqual(len(gate_records), 12)  # 11 gates + the overall roll-up

    def test_persistence_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            run2, replay2, html2 = _persisted(d)
        self.assertEqual(self.html, html2)
        self.assertEqual(self.pulse_run, run2)
        self.assertEqual(self.replay.deterministic_match, replay2.deterministic_match)


# =========================================================================== #
# §H1/§G2/§G3 -- degraded / failed states are VISIBLE, never hidden             #
# =========================================================================== #
class DegradedRunPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _degraded_panel()

    def test_degraded_run_still_renders_the_panel(self):
        self.assertNotEqual(self.html, "")
        self.assertIn("Run observability", self.html)
        self.assertIn(">degraded<", self.html)  # honest overall label

    def test_failed_agent_visible(self):
        self.assertIn("agent.beta", self.html)
        self.assertIn(">failed<", self.html)
        self.assertIn("status=failed", self.html)      # degraded_reason carried through
        self.assertIn("<td>1</td>", self.html)         # failure_count volume

    def test_blocked_agent_visible(self):
        self.assertIn("agent.gamma", self.html)
        self.assertIn("blocked_by_policy", self.html)

    def test_failed_source_visible_with_presence_labels_only(self):
        self.assertIn("sec_edgar", self.html)
        self.assertIn("credentials_missing", self.html)
        self.assertIn(">missing<", self.html)          # credentials label (presence only)
        self.assertIn("rate_limited", self.html)       # §G3 rate-limit status captured
        self.assertIn("credential absent -- visible gap", self.html)
        self.assertIn(">present<", self.html)          # the healthy source's presence label

    def test_gate_fail_and_divergent_replay_visible(self):
        self.assertIn(">fail<", self.html)
        self.assertIn("replayable · deterministic_match: False", self.html)
        self.assertIn("1 difference(s)", self.html)
        self.assertIn("surfaced not hidden", self.html)


# =========================================================================== #
# §H4 + opt-in -- empty inputs, byte-identical demo, closed link graph          #
# =========================================================================== #
class AdditiveOptInTests(unittest.TestCase):
    def test_empty_inputs_render_nothing(self):
        self.assertEqual(build_run_observability_panel(), "")

    def test_demo_default_byte_identical(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2, \
                tempfile.TemporaryDirectory() as d3:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo", run_observability_html="")
            c = build_universe_app(d3, mode="demo")
            for name in a:
                self.assertEqual(_read(a, name), _read(b, name),
                                 "demo default drifted for {0}".format(name))
                self.assertEqual(_read(a, name), _read(c, name),
                                 "demo build not deterministic for {0}".format(name))

    def test_demo_default_has_no_observability_panel(self):
        with tempfile.TemporaryDirectory() as d:
            paths = build_universe_app(d, mode="demo")
            self.assertNotIn("Run observability", _read(paths, "data_quality.html"))


class UiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._store = tempfile.mkdtemp(prefix="pp_ui_013f_")
        cls._out = tempfile.mkdtemp(prefix="pp_ui_pages_")
        pulse = _pulse()
        cls.pulse_run, cls.replay, cls.panel = persist_and_summarize(
            pulse, store_dir=cls._store, run_id="RUN-013F", now=_NOW)
        cls.paths = build_universe_app(
            cls._out, mode="demo",
            pulse_signals=pulse.signals, signal_clusters=pulse.clusters,
            theme_pulses=pulse.theme_pulses,
            pulse_authority_by_signal=pulse.authority_by_signal,
            run_observability_html=cls.panel)
        cls.dq_html = _read(cls.paths, "data_quality.html")

    def test_panel_rendered_into_data_quality(self):
        self.assertIn("Run observability — persisted pulse", self.dq_html)
        self.assertIn("replayable · deterministic_match: True", self.dq_html)

    def test_panel_emits_no_intel_refs_and_no_anchors(self):
        # the EMITTED html (not a docstring): zero data-intel refs, zero href anchors
        self.assertNotIn("data-intel", self.panel)
        self.assertNotIn("href=", self.panel)

    def test_no_dead_anchors_with_panel(self):
        HtmlLinkGraph(self.dq_html).assert_no_dead_anchors(self, _cockpit_files(self.paths))

    def test_no_affordance_or_secret_token_in_page(self):
        low = self.dq_html.lower()
        for bad in _FORBIDDEN_PAGE_TOKENS:
            self.assertNotIn(bad, low, "forbidden token in DQ page: {0}".format(bad))

    def test_no_trade_verb_or_hidden_metric_in_panel_data(self):
        data_only = re.sub(r'<p class="note">.*?</p>', "", self.panel.lower(), flags=re.S)
        self.assertNotRegex(data_only,
                            r"\b(buy|sell|hold|submit|top pick|best stock|price target)\b")
        self.assertNotRegex(data_only, r"\b(investability|score:|rank #|rating:)\b")

    def test_no_always_on_claim_and_english_only(self):
        low = self.panel.lower()
        self.assertIn("manual pulse", low)
        self.assertNotRegex(low, r"\b(always[- ]on|real[- ]time|streaming|24/7|live feed)\b")
        for term in _SANSKRIT:
            self.assertNotIn(term, low, "Sanskrit term in output: {0}".format(term))


# =========================================================================== #
# CLI -- opt-in --persist-dir, default byte-identical, offline (§G1)            #
# =========================================================================== #
class CliPersistTests(unittest.TestCase):
    _ARGS = ["--watchlist", "IREN,NVDA", "--themes", "physical_ai,robotics"]

    def _run_cli(self, out_dir, extra=()):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = pulse_cli_main(self._ARGS + ["--out", out_dir] + list(extra))
        return rc, buf.getvalue()

    def test_persist_dir_flag_works_offline(self):
        orig = socket.socket.connect
        socket.socket.connect = _boom_socket
        try:
            with tempfile.TemporaryDirectory() as out, \
                    tempfile.TemporaryDirectory() as store:
                rc, text = self._run_cli(out, ["--persist-dir", store])
                self.assertEqual(rc, 0)
                self.assertIn("run persisted · replayable (deterministic_match: True)", text)
                self.assertTrue(os.path.isfile(os.path.join(store, "run_store.jsonl")))
                self.assertTrue(os.path.isfile(
                    os.path.join(store, "agent_run_ledger.jsonl")))
                with open(os.path.join(out, "data_quality.html"),
                          encoding="utf-8") as fh:
                    self.assertIn("Run observability", fh.read())
        finally:
            socket.socket.connect = orig

    def test_default_cli_byte_identical_without_flag(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            rc1, t1 = self._run_cli(d1)
            rc2, t2 = self._run_cli(d2)
            self.assertEqual((rc1, rc2), (0, 0))
            # the opt-out CLI mentions nothing about persistence and renders no new panel
            for text in (t1, t2):
                self.assertNotIn("persisted", text)
            self.assertEqual(t1.replace(d1, "@OUT@"), t2.replace(d2, "@OUT@"))
            for name in ("universe.html", "dashboard.html", "data_quality.html",
                         "cockpit.html", "pulse_summary.json"):
                with open(os.path.join(d1, name), encoding="utf-8") as fh:
                    a = fh.read()
                with open(os.path.join(d2, name), encoding="utf-8") as fh:
                    b = fh.read()
                self.assertEqual(a, b, "CLI default output drifted for {0}".format(name))
            with open(os.path.join(d1, "data_quality.html"), encoding="utf-8") as fh:
                self.assertNotIn("Run observability", fh.read())

    def test_persisted_summary_json_unchanged_by_flag(self):
        with tempfile.TemporaryDirectory() as plain, \
                tempfile.TemporaryDirectory() as persisted, \
                tempfile.TemporaryDirectory() as store:
            self._run_cli(plain)
            self._run_cli(persisted, ["--persist-dir", store])
            with open(os.path.join(plain, "pulse_summary.json"), encoding="utf-8") as fh:
                a = json.load(fh)
            with open(os.path.join(persisted, "pulse_summary.json"), encoding="utf-8") as fh:
                b = json.load(fh)
            self.assertEqual(a, b)


# =========================================================================== #
# Globals (§I) -- offline, AST guards, no scheduler / broker / metric            #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    def test_persist_and_summarize_runs_under_socket_kill_switch(self):
        orig = socket.socket.connect
        socket.socket.connect = _boom_socket
        try:
            with tempfile.TemporaryDirectory() as d:
                run, replay, html = _persisted(d, run_id="RUN-OFFLINE")
            self.assertTrue(replay.deterministic_match)
            self.assertIn("RUN-OFFLINE", html)
        finally:
            socket.socket.connect = orig

    def test_new_modules_import_no_network_scheduler_or_broker(self):
        banned = ("requests", "urllib", "socket", "http", "sched", "asyncio", "subprocess",
                  "threading", "multiprocessing", "broker")
        for path in _NEW_FILES:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mod = (getattr(node, "module", "") or "") + " ".join(
                        a.name for a in getattr(node, "names", []))
                    for b in banned:
                        self.assertNotIn(b, mod,
                                         "banned import in {0}: {1}".format(path, b))

    def test_new_modules_define_no_metric_function(self):
        for path in _NEW_FILES:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertFalse(re.search(r"(score|rank|rating)", node.name.lower()),
                                     "banned fn name in {0}: {1}".format(path, node.name))

    def test_agent_results_mapping_is_honest(self):
        pulse = _pulse()
        results = agent_results_from_pulse(pulse, run_id="RUN-MAP", now=_NOW)
        self.assertEqual(len(results), len(pulse.agent_runs))
        for res in results:
            self.assertIn(res.status, ("success", "skipped", "partial"))
            if res.status == "skipped":  # honest coverage absence carries a gap
                self.assertTrue(res.data_gaps)

    def test_stores_are_byte_unchanged_by_a_second_replay(self):
        with tempfile.TemporaryDirectory() as d:
            _persisted(d, run_id="RUN-RO")

            def _snapshot():
                out = {}
                for name in sorted(os.listdir(d)):
                    with open(os.path.join(d, name), "rb") as fh:
                        out[name] = fh.read()
                return out

            before = _snapshot()
            harness = rm.ReplayHarness(S.EventStore(d), S.FindingStore(d), S.SignalStore(d),
                                       S.ThemePulseStore(d), S.RunStore(d))
            harness.replay(rm.ReplayRequest(run_id="RUN-RO"), now=_NOW)
            self.assertEqual(before, _snapshot())


if __name__ == "__main__":
    unittest.main()
