"""IMPLEMENTATION-012E -- Sector Rotation + Theme Rotation sensor agents, TEST_MATRIX_012 D2/D5.

Two more real Tattva sensors. This suite runs entirely OFFLINE against small deterministic JSON
fixtures under ``tests/fixtures/reality_mesh/rotation/`` -- no network, no live market fetch, no
scheduler, no broker. It proves the 012E sensor invariants the gate enforces:

* D2 -- a Physical AI fixture emits a ThemeRotationFinding rotating INTO the basket (ignition +
  broadening); a semis fixture emits rotation_out_of_sector; theme movement / ignition / breadth /
  exhaustion are LABELS only, never a trade / score / rank.
* broadening vs narrow -- a MULTI-member breadth move -> theme_broadening; a one-stock move ->
  ignition but NEVER broadening.
* crowding -- excessive price / narrative breadth -> theme_crowding.
* missing basket members -> explicit data gaps (never fabricated); the theme basket composition
  is EXPLICIT on the finding.
* the institutional-flow figure is ALWAYS a labelled PROXY (flow_proxy), never verified
  institutional flow; a missing flow input is an explicit gap.
* stale input -> the finding is marked ``freshness_label="stale"`` (never dropped) + a gap.
* D5 -- each agent stays strictly within its discipline (run_checked); missing input -> gap.
* route -> fuse -- a rotation finding routes through the 012B BuddhiRouter and fuses (with a
  market-regime finding) through the 012C synthesizer into RealitySignals.
* guardrails -- AgentFinding-only; NO stock-first ranking / no score/rank/trade field; no
  net/scheduler/broker import + no ``def *score``/``*rank`` in the sensors package (AST); whole
  suite offline under a socket kill-switch; demo default byte-identical.
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
from reality_mesh.sensors import (
    SectorRotationAgent,
    ThemeRotationAgent,
    events_from_fixture,
    rotation as ROT,
)
from reality_mesh.sensors import MarketRegimeAgent

_FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "reality_mesh", "rotation")
_MR_FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "reality_mesh", "market_regime")
_SENSORS_DIR = os.path.join(_SRC, "reality_mesh", "sensors")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _load(name):
    return events_from_fixture(os.path.join(_FIXTURES, name + ".json"))


def _sector(name):
    return SectorRotationAgent().run_checked(None, _load(name))


def _theme(name):
    return ThemeRotationAgent().run_checked(None, _load(name))


def _types(findings):
    return {f.finding_type for f in findings}


# =========================================================================== #
# D2 -- Sector rotation: into / out / leadership / exhaustion                  #
# =========================================================================== #
class SectorRotationDirectionTests(unittest.TestCase):
    def test_rotation_into_sector_is_improving(self):
        findings = _sector("sector_rotation_into")
        self.assertTrue(findings)
        self.assertIn("rotation_into_sector", _types(findings))
        into = [f for f in findings if f.finding_type == "rotation_into_sector"][0]
        self.assertEqual(into.direction_label, "improving")
        self.assertIn("Energy", into.affected_sectors)
        for f in findings:
            self.assertEqual(f.discipline, "sector_rotation")
            self.assertIsInstance(f, M.AgentFinding)

    def test_rotation_out_of_semis_is_deteriorating(self):
        findings = _sector("sector_rotation_out_semis")
        self.assertIn("rotation_out_of_sector", _types(findings))
        out = [f for f in findings if f.finding_type == "rotation_out_of_sector"][0]
        self.assertEqual(out.direction_label, "deteriorating")
        self.assertIn("Semiconductors", out.affected_sectors)
        # NOT read as rotation-in
        self.assertNotIn("rotation_into_sector", _types(findings))

    def test_sector_leadership_change_reverses(self):
        findings = _sector("sector_leadership_change")
        self.assertIn("sector_leadership_change", _types(findings))
        lead = [f for f in findings if f.finding_type == "sector_leadership_change"][0]
        self.assertEqual(lead.direction_label, "reversing")

    def test_sector_exhaustion_decelerates_and_suppresses_rotation_in(self):
        findings = _sector("sector_exhaustion")
        self.assertIn("sector_exhaustion", _types(findings))
        exh = [f for f in findings if f.finding_type == "sector_exhaustion"][0]
        self.assertEqual(exh.direction_label, "decelerating")
        # high RS but exhausted must NOT double-count as fresh rotation-in
        self.assertNotIn("rotation_into_sector", _types(findings))

    def test_sector_finding_types_in_vocabulary_and_valid_labels(self):
        for name in ("sector_rotation_into", "sector_rotation_out_semis",
                     "sector_leadership_change", "sector_exhaustion"):
            for f in _sector(name):
                self.assertIn(f.finding_type, ROT.SECTOR_ROTATION_FINDING_TYPES)
                self.assertIn(f.direction_label, rm.DIRECTION_LABELS)
                self.assertIn(f.magnitude_label, rm.MAGNITUDE_LABELS)
                self.assertIn(f.urgency_label, rm.URGENCY_LABELS)
                self.assertIn(f.confidence_label, rm.CONFIDENCE_LABELS)
                self.assertIn(f.freshness_label, rm.FRESHNESS_LABELS)
                V.validate_finding(f)


# =========================================================================== #
# Institutional flow is ALWAYS a labelled proxy (never verified flow)          #
# =========================================================================== #
class FlowProxyTests(unittest.TestCase):
    def test_flow_figure_labelled_proxy_not_verified(self):
        findings = _sector("sector_rotation_into")
        blob = " ".join(f.finding_summary for f in findings).lower()
        self.assertIn("proxy", blob)
        self.assertIn("not verified institutional flow", blob)
        # the labelled-proxy caveat is preserved as an explicit note on the finding
        gap_blob = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("proxy", gap_blob)

    def test_no_finding_presents_verified_institutional_flow(self):
        for name in ("sector_rotation_into", "sector_rotation_out_semis",
                     "sector_leadership_change", "sector_exhaustion"):
            for f in _sector(name):
                text = (f.finding_summary + " " + " ".join(f.data_gaps)).lower()
                self.assertNotIn("verified institutional flow (confirmed)", text)
                # any mention of institutional flow is qualified as a proxy
                if "institutional flow" in text:
                    self.assertIn("proxy", text)

    def test_missing_flow_is_explicit_gap_not_fabricated(self):
        findings = _sector("sector_missing_flow")
        self.assertTrue(findings)
        gap_blob = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("institutional flow proxy missing", gap_blob)
        # still a valid rotation-in read despite the absent flow
        self.assertIn("rotation_into_sector", _types(findings))


# =========================================================================== #
# D2 -- Theme rotation: ignition / broadening / crowding / exhaustion          #
# =========================================================================== #
class ThemeRotationTests(unittest.TestCase):
    def test_rotation_into_physical_ai_basket(self):
        findings = _theme("theme_into_physical_ai")
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f.discipline, "theme_rotation")
            self.assertIn("physical_ai", f.affected_themes)
        # rotation INTO the basket == ignition; multi-member == broadening
        self.assertIn("theme_ignition", _types(findings))
        self.assertIn("theme_broadening", _types(findings))
        ig = [f for f in findings if f.finding_type == "theme_ignition"][0]
        self.assertEqual(ig.direction_label, "accelerating")

    def test_theme_basket_composition_is_explicit_on_finding(self):
        findings = _theme("theme_into_physical_ai")
        for f in findings:
            # the explicit basket members ride on the finding (never hidden)
            self.assertEqual(
                set(f.affected_companies), {"TSLA", "NVDA", "ISRG", "SYM", "TER"})

    def test_theme_finding_types_in_vocabulary_and_valid_labels(self):
        for name in ("theme_into_physical_ai", "theme_narrow", "theme_crowding",
                     "theme_missing_member"):
            for f in _theme(name):
                self.assertIn(f.finding_type, ROT.THEME_ROTATION_FINDING_TYPES)
                self.assertIn(f.direction_label, rm.DIRECTION_LABELS)
                self.assertIn(f.magnitude_label, rm.MAGNITUDE_LABELS)
                self.assertIn(f.urgency_label, rm.URGENCY_LABELS)
                V.validate_finding(f)


# =========================================================================== #
# Broadening vs narrow -- multi-member -> broadening; one-stock -> NOT          #
# =========================================================================== #
class BroadeningVsNarrowTests(unittest.TestCase):
    def test_multi_member_move_reads_as_broadening(self):
        findings = _theme("theme_into_physical_ai")
        self.assertIn("theme_broadening", _types(findings))
        br = [f for f in findings if f.finding_type == "theme_broadening"][0]
        self.assertEqual(br.direction_label, "improving")

    def test_one_stock_move_is_not_broadening(self):
        findings = _theme("theme_narrow")
        # a single participating member is (at most) ignition, never broadening
        self.assertNotIn("theme_broadening", _types(findings))
        self.assertIn("theme_ignition", _types(findings))

    def test_broadening_threshold_requires_multiple_members(self):
        self.assertGreaterEqual(ROT.BROADENING_MIN_MEMBERS, 2)


# =========================================================================== #
# Crowding fires when price / narrative breadth excessive                      #
# =========================================================================== #
class CrowdingTests(unittest.TestCase):
    def test_crowding_fires_on_excessive_breadth(self):
        findings = _theme("theme_crowding")
        self.assertIn("theme_crowding", _types(findings))
        cr = [f for f in findings if f.finding_type == "theme_crowding"][0]
        self.assertEqual(cr.direction_label, "reversing")
        self.assertIn(cr.magnitude_label, ("major", "extreme"))

    def test_non_crowded_theme_does_not_fire_crowding(self):
        self.assertNotIn("theme_crowding", _types(_theme("theme_into_physical_ai")))
        self.assertNotIn("theme_crowding", _types(_theme("theme_narrow")))


# =========================================================================== #
# Missing basket members -> explicit data gaps (never fabricated)              #
# =========================================================================== #
class MissingBasketMemberTests(unittest.TestCase):
    def test_missing_members_surface_as_data_gaps(self):
        findings = _theme("theme_missing_member")
        self.assertTrue(findings)
        gap_blob = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("basket incomplete", gap_blob)
        # the two absent declared members are named, not invented
        self.assertIn("tln", gap_blob)
        self.assertIn("oklo", gap_blob)
        # the declared basket is still explicit on the finding
        for f in findings:
            self.assertEqual(
                set(f.affected_companies), {"VRT", "GEV", "CEG", "TLN", "OKLO"})

    def test_present_members_never_fabricated_into_participation(self):
        findings = _theme("theme_missing_member")
        # only 2 of the 3 present members advance -> not enough for broadening
        self.assertNotIn("theme_broadening", _types(findings))


# =========================================================================== #
# Stale input -> finding marked stale, not dropped                            #
# =========================================================================== #
class StaleTests(unittest.TestCase):
    def test_sector_stale_input_marks_finding_stale_and_notes_gap(self):
        findings = _sector("sector_stale")
        self.assertTrue(findings, "stale findings must NOT be dropped")
        for f in findings:
            self.assertEqual(f.freshness_label, "stale")
        gap_blob = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("stale", gap_blob)

    def test_theme_stale_input_marks_finding_stale_and_notes_gap(self):
        findings = _theme("theme_stale")
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f.freshness_label, "stale")
        gap_blob = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("stale", gap_blob)


# =========================================================================== #
# D5 -- discipline bound; reuse built-in descriptors                          #
# =========================================================================== #
class DisciplineTests(unittest.TestCase):
    def test_sector_agent_stays_within_discipline_and_reuses_descriptor(self):
        agent = SectorRotationAgent()
        self.assertEqual(agent.descriptor.discipline, "sector_rotation")
        self.assertEqual(agent.descriptor.agent_id, "tattva.sector_rotation")
        builtin = rm.build_default_registry().get("tattva.sector_rotation")
        self.assertEqual(agent.descriptor.agent_id, builtin.agent_id)
        self.assertIn("SectorRotationFinding", agent.descriptor.emits)
        for sub in ROT.SECTOR_ROTATION_SUBAGENTS:
            self.assertIn(sub, agent.descriptor.subagents)
        for f in agent.run_checked(None, _load("sector_rotation_into")):
            self.assertEqual(f.discipline, "sector_rotation")

    def test_theme_agent_stays_within_discipline_and_reuses_descriptor(self):
        agent = ThemeRotationAgent()
        self.assertEqual(agent.descriptor.discipline, "theme_rotation")
        self.assertEqual(agent.descriptor.agent_id, "tattva.theme_rotation")
        builtin = rm.build_default_registry().get("tattva.theme_rotation")
        self.assertEqual(agent.descriptor.agent_id, builtin.agent_id)
        self.assertIn("ThemeRotationFinding", agent.descriptor.emits)
        for sub in ROT.THEME_ROTATION_SUBAGENTS:
            self.assertIn(sub, agent.descriptor.subagents)
        for f in agent.run_checked(None, _load("theme_crowding")):
            self.assertEqual(f.discipline, "theme_rotation")

    def test_run_checked_rejects_non_reality_event_input(self):
        with self.assertRaises(TypeError):
            SectorRotationAgent().run_checked(None, ("not-an-event",))
        with self.assertRaises(TypeError):
            ThemeRotationAgent().run_checked(None, ("not-an-event",))


# =========================================================================== #
# AgentFinding-ONLY / no stock-first ranking / no score/rank/trade field       #
# =========================================================================== #
class BoundaryTests(unittest.TestCase):
    _ALL_SECTOR = ("sector_rotation_into", "sector_rotation_out_semis",
                   "sector_leadership_change", "sector_exhaustion",
                   "sector_missing_flow", "sector_stale")
    _ALL_THEME = ("theme_into_physical_ai", "theme_narrow", "theme_crowding",
                  "theme_missing_member", "theme_stale")

    def test_agents_emit_agentfinding_only(self):
        for name in self._ALL_SECTOR:
            for f in _sector(name):
                self.assertIsInstance(f, M.AgentFinding)
        for name in self._ALL_THEME:
            for f in _theme(name):
                self.assertIsInstance(f, M.AgentFinding)

    def test_findings_have_no_trade_or_score_field(self):
        every = [f for n in self._ALL_SECTOR for f in _sector(n)]
        every += [f for n in self._ALL_THEME for f in _theme(n)]
        for f in every:
            V.assert_no_trade_fields(f)
            for name_ in f.__dataclass_fields__:
                low = name_.lower()
                for banned in ("score", "rank", "rating", "buy", "sell", "hold",
                               "order", "trade", "broker"):
                    self.assertNotIn(banned, low)

    def test_no_stock_first_ranking(self):
        # A rotation finding is scoped to a sector/theme (not a ranked stock list): sector
        # findings carry NO stock, and theme findings carry the WHOLE explicit basket (multiple
        # members, not a single top pick), so there is no stock-first ordinal ranking.
        for f in _sector("sector_rotation_into"):
            self.assertEqual(f.affected_companies, ())
            self.assertTrue(f.affected_sectors)
        for f in _theme("theme_into_physical_ai"):
            self.assertGreater(len(f.affected_companies), 1)
            self.assertTrue(f.affected_themes)

    def test_deterministic_offline_run(self):
        a = _theme("theme_into_physical_ai")
        b = _theme("theme_into_physical_ai")
        self.assertEqual([repr(f) for f in a], [repr(f) for f in b])
        c = _sector("sector_rotation_into")
        d = _sector("sector_rotation_into")
        self.assertEqual([repr(f) for f in c], [repr(f) for f in d])


# =========================================================================== #
# route -> fuse: 012B BuddhiRouter + 012C synthesizer                         #
# =========================================================================== #
class RouteAndFuseTests(unittest.TestCase):
    def setUp(self):
        self.reg = rm.build_default_registry()
        self.router = rm.BuddhiRouter(self.reg)
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_route_event_picks_sector_rotation(self):
        evs = _load("sector_rotation_into")
        matches = self.router.route_event(evs[0])
        self.assertIn("tattva.sector_rotation", [d.agent_id for d in matches])

    def test_route_finding_wraps_into_handoff_envelope(self):
        findings = _sector("sector_rotation_into")
        env = self.router.route_finding(findings[0])
        self.assertIsInstance(env, M.HandoffEnvelope)
        self.assertEqual(env.from_layer, "reality_intelligence")
        self.assertEqual(env.from_agent, "tattva.sector_rotation")
        self.assertEqual(env.to_synthesizer, "SignalFusion")
        self.assertEqual(env.payload_type, "AgentFinding")
        self.assertIn("fuse", env.allowed_downstream_uses)
        for use in ("broker_order", "auto_execute",
                    "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, env.forbidden_downstream_uses)

    def test_rotation_fuses_with_market_regime_into_reality_signals(self):
        # route both findings through the router first, then fuse through the synthesizer
        sector_findings = _sector("sector_rotation_out_semis")
        mr_findings = MarketRegimeAgent().run_checked(
            None, events_from_fixture(os.path.join(_MR_FIXTURES, "risk_off.json")))
        for f in list(sector_findings) + list(mr_findings):
            env = self.router.route_finding(f)
            self.assertEqual(env.to_synthesizer, "SignalFusion")

        sector_events = _load("sector_rotation_out_semis")
        mr_events = events_from_fixture(os.path.join(_MR_FIXTURES, "risk_off.json"))
        res = self.fuser.fuse(
            tuple(sector_events) + tuple(mr_events),
            tuple(sector_findings) + tuple(mr_findings),
            now="2026-06-29T00:00:00Z")
        self.assertTrue(res.signals)
        disciplines = {s.discipline for s in res.signals}
        self.assertIn("sector_rotation", disciplines)
        self.assertIn("market_regime", disciplines)
        for s in res.signals:
            self.assertIsInstance(s, M.RealitySignal)
        self.assertEqual(res.envelope.to_layer, "opportunity_discovery")

    def test_theme_fuses_into_reality_signal(self):
        evs = _load("theme_into_physical_ai")
        findings = _theme("theme_into_physical_ai")
        res = self.fuser.fuse(evs, findings, now="2026-06-29T00:00:00Z")
        self.assertTrue(res.signals)
        self.assertIn("theme_rotation", {s.discipline for s in res.signals})

    def test_full_offline_pipeline_under_socket_killswitch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            evs = _load("sector_rotation_into")
            findings = SectorRotationAgent().run_checked(None, evs)
            env = self.router.route_finding(findings[0])
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
        d1 = tempfile.mkdtemp(prefix="rm_rot_a_")
        d2 = tempfile.mkdtemp(prefix="rm_rot_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))
        with open(p1["universe.html"], encoding="utf-8") as fh:
            self.assertNotIn("reality_mesh", fh.read())


if __name__ == "__main__":
    unittest.main()
