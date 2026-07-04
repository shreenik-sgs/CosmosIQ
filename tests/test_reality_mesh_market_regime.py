"""IMPLEMENTATION-012D -- Market Regime sensor agent (fixture-backed), TEST_MATRIX_012 D1 + D5.

The FIRST real Tattva sensor. This suite runs entirely OFFLINE against small deterministic JSON
fixtures under ``tests/fixtures/reality_mesh/market_regime/`` -- no network, no live market
fetch, no scheduler, no broker. It proves the 012 sensor invariants the gate enforces:

* D1 -- a risk-off fixture emits a MarketRegimeFinding with a deteriorating (negative) direction;
  a risk-on fixture emits improving; labels only, no trade / score / rank field.
* breadth deterioration is preserved as its OWN finding (never averaged into the aggregate).
* stale market data -> the finding is marked ``freshness_label="stale"`` (never dropped) + a gap.
* D5 -- a MISSING breadth input surfaces as an explicit data gap (never a fabricated value); the
  agent stays strictly within the ``market_regime`` discipline (run_checked).
* route -> fuse -- the finding routes through the 012B BuddhiRouter (route_event picks
  market_regime; route_finding wraps it into a HandoffEnvelope to TattvaSignalFusion) and fuses
  through the 012C synthesizer into a RealitySignal.
* guardrails -- AgentFinding-only; no net/scheduler/broker import + no ``def *score``/``*rank`` in
  the sensors package (AST); whole suite offline under a socket kill-switch; demo byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import models as M
from reality_mesh import validation as V
from reality_mesh.sensors import MarketRegimeAgent, events_from_fixture, market_regime as MR

_FIXTURES = os.path.join(
    _ROOT, "tests", "fixtures", "reality_mesh", "market_regime")
_SENSORS_DIR = os.path.join(_SRC, "reality_mesh", "sensors")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _load(name):
    return events_from_fixture(os.path.join(_FIXTURES, name + ".json"))


def _run(name):
    return MarketRegimeAgent().run_checked(None, _load(name))


def _types(findings):
    return {f.finding_type for f in findings}


# =========================================================================== #
# D1 -- regime direction from fixtures (risk-off deteriorating; risk-on improving) #
# =========================================================================== #
class RegimeDirectionTests(unittest.TestCase):
    def test_risk_off_fixture_emits_deteriorating_market_regime_finding(self):
        findings = _run("risk_off")
        self.assertTrue(findings)
        for f in findings:
            self.assertIsInstance(f, M.AgentFinding)
            self.assertEqual(f.discipline, "market_regime")
        deteriorating = [f for f in findings if f.direction_label == "deteriorating"]
        self.assertTrue(deteriorating, "risk-off must yield a deteriorating finding")
        # the broad-pullback aggregate is present and negative
        self.assertIn("market_pullback", _types(findings))
        pull = [f for f in findings if f.finding_type == "market_pullback"][0]
        self.assertEqual(pull.direction_label, "deteriorating")

    def test_risk_on_fixture_emits_improving_market_regime_finding(self):
        findings = _run("risk_on")
        self.assertTrue(findings)
        improving = [f for f in findings if f.direction_label == "improving"]
        self.assertTrue(improving, "risk-on must yield an improving finding")
        self.assertIn("risk_on", _types(findings))
        ron = [f for f in findings if f.finding_type == "risk_on"][0]
        self.assertEqual(ron.direction_label, "improving")
        self.assertIn("breadth_improvement", _types(findings))

    def test_all_finding_types_are_in_the_declared_vocabulary(self):
        for name in ("risk_off", "risk_on", "breadth_deterioration", "stale", "missing_breadth"):
            for f in _run(name):
                self.assertIn(f.finding_type, MR.MARKET_REGIME_FINDING_TYPES)

    def test_findings_carry_only_valid_closed_labels(self):
        for name in ("risk_off", "risk_on", "breadth_deterioration"):
            for f in _run(name):
                self.assertIn(f.direction_label, rm.DIRECTION_LABELS)
                self.assertIn(f.magnitude_label, rm.MAGNITUDE_LABELS)
                self.assertIn(f.urgency_label, rm.URGENCY_LABELS)
                self.assertIn(f.confidence_label, rm.CONFIDENCE_LABELS)
                self.assertIn(f.freshness_label, rm.FRESHNESS_LABELS)
                V.validate_finding(f)


# =========================================================================== #
# breadth deterioration preserved as its own finding                          #
# =========================================================================== #
class BreadthTests(unittest.TestCase):
    def test_breadth_deterioration_preserved_as_own_finding(self):
        findings = _run("breadth_deterioration")
        breadth = [f for f in findings if f.finding_type == "breadth_deterioration"]
        self.assertEqual(len(breadth), 1, "breadth deterioration must be its own finding")
        self.assertEqual(breadth[0].direction_label, "deteriorating")
        # it is NOT averaged away -- it survives alongside the aggregate regime finding
        self.assertGreaterEqual(len(findings), 2)

    def test_breadth_improvement_maps_to_improving(self):
        findings = _run("risk_on")
        breadth = [f for f in findings if f.finding_type == "breadth_improvement"][0]
        self.assertEqual(breadth.direction_label, "improving")


# =========================================================================== #
# stale input -> finding marked stale, not dropped                            #
# =========================================================================== #
class StaleTests(unittest.TestCase):
    def test_stale_input_marks_finding_stale_and_notes_gap(self):
        findings = _run("stale")
        self.assertTrue(findings, "stale findings must NOT be dropped")
        for f in findings:
            self.assertEqual(f.freshness_label, "stale")
        # the staleness is surfaced honestly as a data gap (never hidden)
        aggregate = [f for f in findings if f.finding_type in ("market_pullback", "risk_off")]
        self.assertTrue(aggregate)
        self.assertTrue(
            any("stale" in g.lower() for g in aggregate[0].data_gaps),
            "stale market data must be recorded as an explicit gap")


# =========================================================================== #
# missing input -> explicit data gap (never fabricated) + discipline bound     #
# =========================================================================== #
class MissingInputTests(unittest.TestCase):
    def test_missing_breadth_surfaces_explicit_data_gap(self):
        findings = _run("missing_breadth")
        # no breadth finding is invented ...
        self.assertNotIn("breadth_deterioration", _types(findings))
        self.assertNotIn("breadth_improvement", _types(findings))
        # ... and the absence is a visible gap on the aggregate finding
        gap_text = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("missing breadth", gap_text)

    def test_agent_stays_within_market_regime_discipline(self):
        agent = MarketRegimeAgent()
        self.assertEqual(agent.descriptor.discipline, "market_regime")
        self.assertEqual(agent.descriptor.agent_id, "tattva.market_regime")
        for name in ("risk_off", "risk_on", "missing_breadth"):
            for f in agent.run_checked(None, _load(name)):
                self.assertEqual(f.discipline, "market_regime")

    def test_agent_reuses_builtin_descriptor(self):
        agent = MarketRegimeAgent()
        builtin = rm.build_default_registry().get("tattva.market_regime")
        self.assertEqual(agent.descriptor.agent_id, builtin.agent_id)
        self.assertEqual(agent.descriptor.discipline, builtin.discipline)
        self.assertIn("MarketRegimeFinding", agent.descriptor.emits)
        # the five subagents are represented on the descriptor
        for sub in MR.MARKET_REGIME_SUBAGENTS:
            self.assertIn(sub, agent.descriptor.subagents)


# =========================================================================== #
# AgentFinding-ONLY boundary (no signal/thesis/trade/rank/score)              #
# =========================================================================== #
class BoundaryTests(unittest.TestCase):
    def test_agent_emits_agentfinding_only(self):
        for name in ("risk_off", "risk_on", "breadth_deterioration", "stale", "missing_breadth"):
            for f in _run(name):
                self.assertIsInstance(f, M.AgentFinding)

    def test_findings_have_no_trade_or_score_field(self):
        for name in ("risk_off", "risk_on"):
            for f in _run(name):
                V.assert_no_trade_fields(f)
                for name_ in f.__dataclass_fields__:
                    low = name_.lower()
                    for banned in ("score", "rank", "rating", "buy", "sell", "hold",
                                   "order", "trade", "broker"):
                        self.assertNotIn(banned, low)

    def test_run_checked_rejects_non_reality_event_input(self):
        with self.assertRaises(TypeError):
            MarketRegimeAgent().run_checked(None, ("not-an-event",))

    def test_deterministic_offline_run(self):
        a = _run("risk_off")
        b = _run("risk_off")
        self.assertEqual([repr(f) for f in a], [repr(f) for f in b])


# =========================================================================== #
# route -> fuse: 012B BuddhiRouter + 012C synthesizer                         #
# =========================================================================== #
class RouteAndFuseTests(unittest.TestCase):
    def setUp(self):
        self.reg = rm.build_default_registry()
        self.router = rm.BuddhiRouter(self.reg)
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_route_event_picks_market_regime(self):
        evs = _load("risk_off")
        matches = self.router.route_event(evs[0])
        self.assertEqual([d.agent_id for d in matches], ["tattva.market_regime"])

    def test_route_finding_wraps_into_handoff_envelope(self):
        findings = _run("risk_off")
        env = self.router.route_finding(findings[-1])
        self.assertIsInstance(env, M.HandoffEnvelope)
        self.assertEqual(env.from_layer, "reality_intelligence")
        self.assertEqual(env.from_agent, "tattva.market_regime")
        self.assertEqual(env.to_synthesizer, "SignalFusion")
        self.assertEqual(env.payload_type, "AgentFinding")
        self.assertIn("fuse", env.allowed_downstream_uses)
        for use in ("broker_order", "auto_execute",
                    "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, env.forbidden_downstream_uses)

    def test_findings_fuse_into_reality_signal(self):
        evs = _load("risk_off")
        findings = _run("risk_off")
        res = self.fuser.fuse(evs, findings, now="2026-06-29T00:00:00Z")
        self.assertTrue(res.signals)
        sig = res.signals[0]
        self.assertIsInstance(sig, M.RealitySignal)
        self.assertEqual(sig.discipline, "market_regime")
        self.assertEqual(sig.direction_label, "deteriorating")
        # the fusion envelope is addressed onward to Sphurana
        self.assertEqual(res.envelope.to_layer, "opportunity_discovery")

    def test_full_offline_pipeline_under_socket_killswitch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            evs = events_from_fixture(os.path.join(_FIXTURES, "risk_on.json"))
            findings = MarketRegimeAgent().run_checked(None, evs)
            env = self.router.route_finding(findings[-1])
            res = self.fuser.fuse(evs, findings, now="")
        finally:
            socket.socket = real
        self.assertEqual(env.to_synthesizer, "SignalFusion")
        self.assertTrue(res.signals)


# =========================================================================== #
# Guardrails -- AST offline / no scoring / demo byte-identical                 #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "selenium", "scrapy", "lxml", "websocket", "websockets"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal"}

    def _sensor_py_files(self):
        return [
            os.path.join(_SENSORS_DIR, f)
            for f in sorted(os.listdir(_SENSORS_DIR)) if f.endswith(".py")]

    def test_sensors_import_no_network_scheduler_or_broker(self):
        for path in self._sensor_py_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            mods = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods += [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    mods.append((node.module or "").split(".")[0])
            for m in mods:
                self.assertNotIn(m, self._NET, "{0} imports network {1}".format(path, m))
                self.assertNotIn(m, self._FORBIDDEN,
                                 "{0} imports forbidden {1}".format(path, m))

    def test_sensors_define_no_scoring_or_ranking_function(self):
        for path in self._sensor_py_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    low = node.name.lower()
                    for tok in ("score", "rank", "rating"):
                        self.assertNotIn(tok, low, "{0}: {1}".format(path, node.name))

    def test_sensors_have_no_broker_order_or_live_fetch_affordance(self):
        blob = ""
        for path in self._sensor_py_files():
            with open(path, encoding="utf-8") as fh:
                blob += fh.read().lower()
        for banned in ("place_order", "submit_order", "execute_trade", "schedule.every",
                       "cron", "broker.submit", "requests.get", "urlopen", "socket.socket"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_mr_a_")
        d2 = tempfile.mkdtemp(prefix="rm_mr_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))
        with open(p1["universe.html"], encoding="utf-8") as fh:
            self.assertIn("reality_mesh.html", fh.read())


if __name__ == "__main__":
    unittest.main()
