"""IMPLEMENTATION-012B -- Agent Registry + SensorAgent interface + Buddhi Router.

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE against in-process constructions -- no
fixture endpoint, no network, no scheduler, no broker. It proves the ARCHITECTURE_CONTRACT_012
invariants the gate enforces for the agent layer (TEST_MATRIX_012 §B + global guardrails §I):

* A. AgentDescriptor -- valid construct; duplicate agent_id rejected (registry); invalid
  layer/discipline rejected; missing forbidden output merged/enforced; X/social defaults to
  weak/narrative/rumor and may not declare a verified_fact/canonical source.
* B. AgentRegistry -- built-in AGENT_MAP descriptors load (26); list_by_layer /
  list_by_discipline / lookup work; duplicate registration rejected.
* C. SensorAgent -- a dummy consumes RealityEvent -> emits AgentFinding only; it cannot emit a
  RealitySignal / InvestmentThesis / CapitalCandidate / PersonalizedAction /
  ManualExecutionPreview (run_checked rejects).
* D. BuddhiRouter -- macro RealityEvent -> macro_regime descriptor; X/social event ->
  x_social_narrative descriptor; a finding is wrapped in a HandoffEnvelope with correct
  from_layer/to_layer/payload_type; forbidden_downstream_uses include the four; authority /
  freshness / conflict / data-gap summaries preserved.
* E. Boundary -- IllegalTradeAgent rejected; IllegalLayerJumpAgent rejected; a Tattva agent
  cannot declare a Nivesha output; an X/social descriptor cannot declare a verified_fact
  source; AST -- no scheduler/broker/network import + no `def *score`/`*rank` in reality_mesh;
  demo default byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import unittest
from dataclasses import dataclass, field

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import agents as A
from reality_mesh import models as M
from reality_mesh import registry as R
from reality_mesh import router as RT

_PKG_DIR = os.path.join(_SRC, "reality_mesh")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# --------------------------------------------------------------------------- #
# Fixture / dummy agents (test-only -- NOT shipped in src)                      #
# --------------------------------------------------------------------------- #
def _macro_descriptor():
    return A.AgentDescriptor(
        agent_id="tattva.macro_regime", agent_name="Macro Regime", layer="Tattva",
        discipline="macro_regime", agent_type="sensor", consumes=("RealityEvent",),
        emits=("AgentFinding", "MacroRegimeFinding"), allowed_downstream_layers=("Tattva",),
        description="dummy macro sensor")


def _macro_event(event_id="E1"):
    return M.RealityEvent(
        event_id=event_id, timestamp="2026-06-29T00:00:00Z", source_id="src.fred",
        source_type="macro_series", source_authority="convenience",
        claim_status="inferred", discipline="macro_regime", event_type="rates_update",
        evidence_refs=("ex1",), source_refs=("fred:DGS10",),
        confidence_label="moderate", freshness_label="fresh", half_life="days",
        conflicts=("c1",), data_gaps=("g1",))


def _social_event(event_id="X1"):
    return M.RealityEvent(
        event_id=event_id, timestamp="2026-06-29T00:00:00Z", source_id="src.x",
        source_type="x_social", discipline="narrative", event_type="narrative_spike",
        evidence_refs=("ex1",), freshness_label="fresh", data_gaps=("g1",))


class DummyMacroAgent(A.SensorAgent):
    """Emits a valid MacroRegimeFinding (an AgentFinding) from macro RealityEvents."""

    @property
    def descriptor(self):
        return _macro_descriptor()

    def run(self, context, events):
        return (M.AgentFinding(
            finding_id="F.macro", agent_id="tattva.macro_regime", agent_layer="Tattva",
            agent_name="Macro Regime", discipline="macro_regime",
            input_events=tuple(e.event_id for e in events),
            finding_type="MacroRegimeFinding", finding_summary="liquidity tightening",
            direction_label="deteriorating", magnitude_label="moderate",
            urgency_label="elevated", confidence_label="moderate", freshness_label="fresh",
            half_life="days", source_authority_summary="convenience",
            corroboration_status="uncorroborated", contradiction_status="unopposed",
            evidence_refs=("ex1",), data_gaps=("g1",),
            routing_targets=("TattvaSignalFusion",)),)


class DummyNarrativeAgent(A.SensorAgent):
    """X/social sensor: emits a weak NarrativeFinding at rumor authority."""

    @property
    def descriptor(self):
        return A.AgentDescriptor(
            agent_id="tattva.narrative", agent_name="Narrative", layer="Tattva",
            discipline="narrative", agent_type="sensor", consumes=("RealityEvent",),
            emits=("AgentFinding", "NarrativeFinding"),
            allowed_downstream_layers=("Tattva",),
            requires_human_review_by_default=True, description="dummy X/social sensor")

    def run(self, context, events):
        return (M.AgentFinding(
            finding_id="F.narr", agent_id="tattva.narrative", agent_layer="Tattva",
            agent_name="Narrative", discipline="narrative",
            input_events=tuple(e.event_id for e in events),
            finding_type="NarrativeFinding", finding_summary="attention spike (weak)",
            direction_label="rising", magnitude_label="minor", urgency_label="watch",
            confidence_label="low", freshness_label="fresh",
            source_authority_summary="rumor", corroboration_status="uncorroborated",
            evidence_refs=("ex1",), data_gaps=("g1",),
            routing_targets=("TattvaSignalFusion",)),)


@dataclass(frozen=True)
class _BrokerTicket:
    """A non-finding output carrying a trade/broker field -- must be rejected structurally."""
    ticket_id: str = "T1"
    broker_order_id: str = "abc"
    data_gaps: tuple = field(default_factory=tuple)


class IllegalTradeAgent(A.SensorAgent):
    """Tries to emit an output carrying a trade/broker field."""

    @property
    def descriptor(self):
        return _macro_descriptor()

    def run(self, context, events):
        return (_BrokerTicket(),)


class IllegalLayerJumpAgent(A.SensorAgent):
    """A Tattva agent whose run tries to emit an OpportunityHypothesisPacket (a layer jump)."""

    @property
    def descriptor(self):
        return _macro_descriptor()

    def run(self, context, events):
        return (M.OpportunityHypothesisPacket(
            hypothesis_id="O.bad", opportunity_summary="illegal jump"),)


# =========================================================================== #
# A. AgentDescriptor                                                          #
# =========================================================================== #
class DescriptorTests(unittest.TestCase):
    def test_valid_descriptor_constructs(self):
        d = _macro_descriptor()
        self.assertEqual(d.agent_id, "tattva.macro_regime")
        self.assertEqual(d.layer, "Tattva")
        self.assertEqual(d.discipline, "macro_regime")
        self.assertIn("MacroRegimeFinding", d.emits)

    def test_empty_agent_id_rejected(self):
        with self.assertRaises(ValueError):
            A.AgentDescriptor(agent_id="", layer="Tattva", discipline="macro_regime",
                              emits=("AgentFinding",))

    def test_invalid_layer_rejected(self):
        with self.assertRaises(ValueError):
            A.AgentDescriptor(agent_id="x.y", layer="Olympus", discipline="macro_regime",
                              emits=("AgentFinding",))

    def test_invalid_discipline_rejected(self):
        with self.assertRaises(ValueError):
            A.AgentDescriptor(agent_id="x.y", layer="Tattva", discipline="astrology",
                              emits=("AgentFinding",))

    def test_missing_forbidden_output_merged(self):
        # A descriptor built with an empty forbidden_outputs still ends up with the four.
        d = A.AgentDescriptor(
            agent_id="x.y", layer="Tattva", discipline="macro_regime",
            emits=("AgentFinding",), forbidden_outputs=())
        for out in A.MANDATORY_FORBIDDEN_OUTPUTS:
            self.assertIn(out, d.forbidden_outputs)
        # a caller-supplied forbidden set is preserved AND the four are merged in
        d2 = A.AgentDescriptor(
            agent_id="x.z", layer="Tattva", discipline="macro_regime",
            emits=("AgentFinding",), forbidden_outputs=("custom_forbidden",))
        self.assertIn("custom_forbidden", d2.forbidden_outputs)
        for out in A.MANDATORY_FORBIDDEN_OUTPUTS:
            self.assertIn(out, d2.forbidden_outputs)

    def test_validate_descriptor_enforces_forbidden(self):
        A.validate_descriptor(_macro_descriptor())   # valid, no raise

    def test_xsocial_defaults_to_weak_narrative_rumor(self):
        d = A.AgentDescriptor(
            agent_id="tattva.narrative", layer="Tattva", discipline="narrative",
            agent_type="sensor", emits=("AgentFinding", "NarrativeFinding"))
        # allowed_sources default to weak/narrative/rumor
        self.assertEqual(d.allowed_sources, ("rumor", "social"))

    def test_xsocial_cannot_declare_verified_or_canonical_source(self):
        for banned in ("verified_fact", "canonical"):
            with self.assertRaises(ValueError):
                A.AgentDescriptor(
                    agent_id="tattva.narrative", layer="Tattva", discipline="narrative",
                    emits=("AgentFinding",), allowed_sources=(banned,))

    def test_descriptor_may_not_declare_broker_or_score_output(self):
        for bad in ("broker_order", "buy_sell_recommendation", "auto_execute",
                    "hidden_score", "investability_score", "submit_order"):
            with self.assertRaises(ValueError):
                A.AgentDescriptor(agent_id="x.y", layer="Tattva", discipline="macro_regime",
                                  emits=(bad,))


# =========================================================================== #
# B. AgentRegistry                                                            #
# =========================================================================== #
class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.reg = rm.build_default_registry()

    def test_builtin_descriptors_load(self):
        self.assertEqual(len(self.reg), 26)
        self.assertEqual(len(self.reg.list_by_layer("Adhara")), 6)
        self.assertEqual(len(self.reg.list_by_layer("Buddhi")), 6)
        self.assertEqual(len(self.reg.list_by_layer("Tattva")), 14)

    def test_every_agent_has_stable_id_one_layer_one_discipline_typed_emit(self):
        seen = set()
        for d in self.reg.descriptors():
            self.assertTrue(d.agent_id)
            self.assertNotIn(d.agent_id, seen)          # stable + unique
            seen.add(d.agent_id)
            self.assertIn(d.layer, rm.LAYERS)            # exactly one (valid) layer
            self.assertTrue(rm.is_member(rm.DISCIPLINES, d.discipline))
            self.assertTrue(d.emits)                     # typed emit contract

    def test_lookup_and_list_by_discipline(self):
        macro = self.reg.get("tattva.macro_regime")
        self.assertEqual(macro.discipline, "macro_regime")
        by_disc = self.reg.list_by_discipline("narrative")
        self.assertEqual([d.agent_id for d in by_disc], ["tattva.narrative"])
        with self.assertRaises(KeyError):
            self.reg.get("tattva.nonexistent")

    def test_duplicate_registration_rejected(self):
        with self.assertRaises(ValueError):
            self.reg.register(self.reg.get("tattva.macro_regime"))

    def test_every_tattva_agent_emits_only_agentfinding_subtypes(self):
        # B2: a Tattva discipline agent's declared emits are AgentFinding (+ its subtype) ONLY.
        allowed = A.LAYER_ALLOWED_EMITS["Tattva"]
        for d in self.reg.list_by_layer("Tattva"):
            for out in d.emits:
                self.assertIn(out, allowed)
            # never a cross-layer packet / order / thesis
            for forbidden in ("OpportunityHypothesisPacket", "InvestmentThesis",
                              "CapitalCandidate", "PersonalizedAction", "ManualExecutionPreview"):
                self.assertNotIn(forbidden, d.emits)


# =========================================================================== #
# C. SensorAgent                                                              #
# =========================================================================== #
class SensorAgentTests(unittest.TestCase):
    def test_dummy_consumes_event_emits_finding(self):
        agent = DummyMacroAgent()
        findings = agent.run_checked(None, (_macro_event(),))
        self.assertEqual(len(findings), 1)
        self.assertIsInstance(findings[0], M.AgentFinding)
        self.assertEqual(findings[0].discipline, "macro_regime")

    def test_narrative_agent_emits_weak_rumor_finding(self):
        agent = DummyNarrativeAgent()
        findings = agent.run_checked(None, (_social_event(),))
        self.assertEqual(findings[0].source_authority_summary, "rumor")
        self.assertEqual(findings[0].confidence_label, "low")

    def test_run_checked_rejects_non_reality_event_input(self):
        agent = DummyMacroAgent()
        with self.assertRaises(TypeError):
            agent.run_checked(None, ("not-an-event",))

    def test_agent_cannot_emit_non_finding_packets(self):
        # An agent that returns any of these downstream/cross-layer objects is rejected.
        class _JumpAgent(A.SensorAgent):
            def __init__(self, obj):
                self._obj = obj

            @property
            def descriptor(self):
                return _macro_descriptor()

            def run(self, context, events):
                return (self._obj,)

        for obj in (
            M.RealitySignal(signal_id="S1"),
            M.OpportunityHypothesisPacket(hypothesis_id="O1"),
            M.ThemePulse(theme_pulse_id="P1"),
            M.DiligenceInputBundle(ticker="T"),
        ):
            with self.assertRaises(ValueError):
                _JumpAgent(obj).run_checked(None, (_macro_event(),))

    def test_out_of_discipline_finding_rejected(self):
        class _WrongDisc(A.SensorAgent):
            @property
            def descriptor(self):
                return _macro_descriptor()   # macro_regime

            def run(self, context, events):
                return (M.AgentFinding(
                    finding_id="F", agent_id="tattva.macro_regime", agent_layer="Tattva",
                    discipline="options_flow", evidence_refs=("e",)),)

        with self.assertRaises(ValueError):
            _WrongDisc().run_checked(None, (_macro_event(),))


# =========================================================================== #
# D. BuddhiRouter                                                             #
# =========================================================================== #
class RouterTests(unittest.TestCase):
    def setUp(self):
        self.reg = rm.build_default_registry()
        self.router = rm.BuddhiRouter(self.reg)

    def test_macro_event_routes_to_macro_regime_descriptor(self):
        matches = self.router.route_event(_macro_event())
        self.assertEqual([d.agent_id for d in matches], ["tattva.macro_regime"])

    def test_social_event_routes_to_narrative_descriptor(self):
        matches = self.router.route_event(_social_event())
        self.assertEqual([d.agent_id for d in matches], ["tattva.narrative"])
        # a bare social source_type also routes to narrative even without the discipline set
        evt = M.RealityEvent(event_id="X9", source_type="twitter")
        self.assertEqual(
            [d.agent_id for d in self.router.route_event(evt)], ["tattva.narrative"])

    def test_finding_wrapped_into_envelope_with_correct_routing(self):
        finding = DummyMacroAgent().run_checked(None, (_macro_event(),))[0]
        env = self.router.route_finding(finding)
        self.assertEqual(env.from_layer, "Tattva")
        self.assertEqual(env.to_layer, "Tattva")
        self.assertEqual(env.to_synthesizer, "TattvaSignalFusion")
        self.assertEqual(env.payload_type, "AgentFinding")
        self.assertEqual(env.payload_ids, ("F.macro",))
        self.assertIn("fuse", env.allowed_downstream_uses)

    def test_envelope_forbidden_uses_include_the_four(self):
        finding = DummyMacroAgent().run_checked(None, (_macro_event(),))[0]
        env = self.router.route_finding(finding)
        for use in ("broker_order", "auto_execute", "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, env.forbidden_downstream_uses)
        rm.validate_envelope(env)

    def test_router_preserves_authority_freshness_conflict_gap_summaries(self):
        finding = DummyMacroAgent().run_checked(None, (_macro_event(),))[0]
        env = self.router.route_finding(finding)
        self.assertEqual(env.authority_summary, "convenience")
        self.assertEqual(env.freshness_summary, "fresh")
        self.assertIn("g1", env.data_gap_summary)   # data gap preserved, not dropped

    def test_router_reflects_requires_human_review_from_descriptor(self):
        finding = DummyNarrativeAgent().run_checked(None, (_social_event(),))[0]
        env = self.router.route_finding(finding)
        self.assertTrue(env.requires_human_review)   # narrative default is review-required

    def test_router_does_not_synthesize(self):
        # route_finding wraps exactly one finding into exactly one payload id -- no fusion.
        finding = DummyMacroAgent().run_checked(None, (_macro_event(),))[0]
        env = self.router.route_finding(finding)
        self.assertEqual(len(env.payload_ids), 1)
        with self.assertRaises(TypeError):
            self.router.route_finding(M.RealitySignal(signal_id="S1"))


# =========================================================================== #
# E. Boundary                                                                 #
# =========================================================================== #
class BoundaryTests(unittest.TestCase):
    def test_illegal_trade_agent_rejected(self):
        with self.assertRaises(AssertionError):
            IllegalTradeAgent().run_checked(None, (_macro_event(),))

    def test_illegal_layer_jump_agent_rejected_by_run_checked(self):
        with self.assertRaises(ValueError):
            IllegalLayerJumpAgent().run_checked(None, (_macro_event(),))

    def test_illegal_layer_jump_rejected_at_descriptor_construction(self):
        # A Tattva descriptor that DECLARES a cross-layer emit is rejected on construction.
        for bad in ("OpportunityHypothesisPacket", "InvestmentThesis", "ThemePulse",
                    "RealitySignal", "PersonalizedAction", "ManualExecutionPreview"):
            with self.assertRaises(ValueError):
                A.AgentDescriptor(agent_id="tattva.bad", layer="Tattva",
                                  discipline="macro_regime", emits=("AgentFinding", bad))

    def test_tattva_agent_cannot_declare_nivesha_output(self):
        for nivesha_out in ("CapitalCandidate", "InvestmentThesis", "ValuationAssessment"):
            with self.assertRaises(ValueError):
                A.AgentDescriptor(agent_id="tattva.x", layer="Tattva",
                                  discipline="financial_inflection",
                                  emits=("AgentFinding", nivesha_out))

    def test_kriya_cannot_declare_broker_or_auto_execute(self):
        for bad in ("broker_order", "auto_execute"):
            with self.assertRaises(ValueError):
                A.AgentDescriptor(agent_id="kriya.bad", layer="Kriya",
                                  discipline="", agent_type="execution_preview",
                                  emits=("ManualExecutionPreview", bad))
        # a legitimate Kriya preview descriptor is fine
        ok = A.AgentDescriptor(agent_id="kriya.manual_ticket", layer="Kriya", discipline="",
                               agent_type="execution_preview",
                               emits=("ManualExecutionIntent", "ManualExecutionPreview"))
        self.assertIn("ManualExecutionPreview", ok.emits)

    def test_no_agent_may_emit_buy_sell_order_or_hidden_score(self):
        for bad in ("buy_signal", "sell_order", "place_order_intent", "hidden_score",
                    "investability_score", "rank_output"):
            with self.assertRaises(ValueError):
                A.AgentDescriptor(agent_id="tattva.x", layer="Tattva",
                                  discipline="macro_regime", emits=(bad,))

    # -- AST / offline / determinism guards ------------------------------- #
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "selenium", "scrapy", "lxml", "websocket", "websockets"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal"}

    def _new_py_files(self):
        return [os.path.join(_PKG_DIR, f) for f in ("agents.py", "registry.py", "router.py")]

    def test_new_modules_import_no_network_scheduler_or_broker(self):
        for path in self._new_py_files():
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
                self.assertNotIn(m, self._FORBIDDEN, "{0} imports forbidden {1}".format(path, m))

    def test_new_modules_define_no_scoring_or_ranking_function(self):
        for path in self._new_py_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    low = node.name.lower()
                    for tok in ("score", "rank", "rating"):
                        self.assertNotIn(tok, low, "{0}: {1}".format(path, node.name))

    def test_new_modules_have_no_broker_or_order_affordance(self):
        blob = ""
        for path in self._new_py_files():
            with open(path, encoding="utf-8") as fh:
                blob += fh.read().lower()
        for banned in ("place_order", "submit_order", "execute_trade",
                       "schedule.every", "cron", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_registry_and_router_are_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            reg = rm.build_default_registry()
            router = rm.BuddhiRouter(reg)
            finding = DummyMacroAgent().run_checked(None, (_macro_event(),))[0]
            env = router.route_finding(finding)
        finally:
            socket.socket = real
        self.assertEqual(env.to_synthesizer, "TattvaSignalFusion")

    def test_builds_are_deterministic(self):
        a = rm.build_default_registry()
        b = rm.build_default_registry()
        self.assertEqual([repr(d) for d in a.descriptors()],
                         [repr(d) for d in b.descriptors()])


# =========================================================================== #
# E (cont). Existing behaviour unaffected -- demo default byte-identical        #
# =========================================================================== #
class ExistingBehaviourTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_agents_a_")
        d2 = tempfile.mkdtemp(prefix="rm_agents_b_")
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
