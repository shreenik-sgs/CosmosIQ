"""IMPLEMENTATION-012F -- Sphurana Theme Pulse Synthesizer (the SECOND synthesizer).

OPPORTUNITY-GENERATION discipline. This suite runs entirely OFFLINE against in-process
constructions -- no fixture endpoint, no network, no scheduler, no broker. It proves the
ARCHITECTURE_CONTRACT_012 §A/§E/§F + TEST_MATRIX_012 §E invariants the gate enforces:

* E1 -- SignalClusters / RealitySignals -> ThemePulse with a valid CLOSED `state`
  (Dormant..Data insufficient); a Physical-AI cluster with rotation + building breadth reads
  Warming/Igniting.
* narrow -- a narrow one-stock move must NOT read as Broadening.
* social -- a social-only narrative theme reads weak / Conflicted / Data insufficient, NEVER a
  high-confidence Igniting.
* E2 -- a market risk-off contradiction is PRESERVED on the pulse (both sides) -> Conflicted.
* E3 -- the OpportunityHypothesisPacket always carries required_diligence_questions +
  supporting/contradicting evidence refs; NO InvestmentThesis / Nivesha output / final decision.
* Guardrails -- NO trade/score/rank field on any output; the Sphurana->Nivesha envelope carries
  the four forbidden defaults; whole suite offline under a socket kill-switch; AST over
  reality_mesh (no net/scheduler/broker import + no `def *score`/`*rank`); demo byte-identical.
* Optionally -- fusion -> sphurana end-to-end (rotation findings -> fuse -> clusters -> pulse).
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
from reality_mesh import sphurana as SP
from reality_mesh import validation as V

_PKG_DIR = os.path.join(_SRC, "reality_mesh")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# --------------------------------------------------------------------------- #
# Signal / cluster builders (test-only fixtures -- NOT shipped in src)          #
# --------------------------------------------------------------------------- #
def _signal(sid, discipline, direction, *, themes=(), sectors=(), companies=(),
            magnitude="moderate", confidence="moderate", freshness="fresh",
            corroboration="uncorroborated", contradiction="unopposed", **kw):
    base = dict(
        signal_id=sid,
        signal_type="{0}_fused_signal".format(discipline),
        discipline=discipline,
        affected_themes=tuple(themes),
        affected_sectors=tuple(sectors),
        affected_companies=tuple(companies),
        direction_label=direction,
        magnitude_label=magnitude,
        confidence_label=confidence,
        freshness_label=freshness,
        corroboration_status=corroboration,
        contradiction_status=contradiction,
        evidence_refs=("ev.{0}".format(sid),),
        source_refs=("src.{0}".format(sid),),
        routing_targets=("Sphurana",),
    )
    base.update(kw)
    return M.RealitySignal(**base)


def _cluster(cid, *, theme="", sector="", companies=(), signals=(),
             breadth="moderate", crowding="unknown", momentum="improving",
             conflict="negligible", confidence="moderate", freshness="fresh", **kw):
    base = dict(
        cluster_id=cid,
        cluster_type="theme" if theme else ("sector" if sector else "value_chain"),
        theme=theme, sector=sector,
        companies=tuple(companies), signals=tuple(signals),
        breadth_label=breadth, crowding_label=crowding, momentum_label=momentum,
        conflict_label=conflict, confidence_label=confidence, freshness_label=freshness,
        evidence_refs=("ev.{0}".format(cid),), source_refs=("src.{0}".format(cid),),
    )
    base.update(kw)
    return M.SignalCluster(**base)


# =========================================================================== #
# E1 -- clusters/signals -> ThemePulse with a valid state                       #
# =========================================================================== #
class ThemePulseStateTests(unittest.TestCase):
    def setUp(self):
        self.syn = rm.ThemePulseSynthesizer()

    def test_physical_ai_rotation_plus_breadth_reads_warming_or_igniting(self):
        # Two members rotating in with building (not-yet-broad) breadth.
        s1 = _signal("sig.theme_rotation.theme.physical-ai", "theme_rotation", "accelerating",
                     themes=("Physical AI",), companies=("NVDA",),
                     corroboration="corroborated")
        s2 = _signal("sig.sector_rotation.theme.physical-ai", "sector_rotation", "improving",
                     themes=("Physical AI",), companies=("TSLA",))
        cl = _cluster("cluster.theme.physical-ai", theme="Physical AI",
                      companies=("NVDA", "TSLA"), signals=(s1.signal_id, s2.signal_id),
                      breadth="moderate", momentum="improving")
        res = self.syn.synthesize((cl,), (s1, s2))
        self.assertEqual(len(res.theme_pulses), 1)
        pulse = res.theme_pulses[0]
        self.assertIsInstance(pulse, M.ThemePulse)
        self.assertIn(pulse.state, ("Warming", "Igniting"))
        self.assertIn(pulse.state, rm.THEME_PULSE_STATES)
        # both members surfaced as beneficiary candidates (unranked)
        self.assertIn("NVDA", pulse.beneficiary_candidates)
        self.assertIn("TSLA", pulse.beneficiary_candidates)
        # evidence preserved end-to-end
        self.assertIn("ev.sig.theme_rotation.theme.physical-ai", pulse.evidence_refs)

    def test_state_is_always_from_closed_vocabulary(self):
        s = _signal("sig.x", "theme_rotation", "improving", themes=("AI",), companies=("NVDA",))
        res = self.syn.synthesize((), (s,))
        for pulse in res.theme_pulses:
            self.assertIn(pulse.state, rm.THEME_PULSE_STATES)

    def test_no_activity_reads_dormant_and_makes_no_hypothesis(self):
        # A theme with only a neutral/stable signal -> nothing to hypothesize.
        s = _signal("sig.n", "theme_rotation", "stable", themes=("Dormantia",),
                    companies=("ABC",), confidence="low")
        res = self.syn.synthesize((), (s,))
        self.assertEqual(res.theme_pulses[0].state, "Dormant")
        self.assertEqual(res.hypotheses, ())


# =========================================================================== #
# narrow -- a one-stock move is NOT Broadening                                  #
# =========================================================================== #
class NarrowNotBroadeningTests(unittest.TestCase):
    def setUp(self):
        self.syn = rm.ThemePulseSynthesizer()

    def test_single_stock_move_does_not_read_as_broadening(self):
        s = _signal("sig.solo", "theme_rotation", "accelerating", themes=("Robotaxi",),
                    companies=("TSLA",), magnitude="major", confidence="moderate")
        res = self.syn.synthesize((), (s,))
        pulse = res.theme_pulses[0]
        self.assertNotEqual(pulse.state, "Broadening")
        self.assertIn(pulse.state, ("Warming", "Igniting"))
        # the narrowness is stated as an explicit, visible gap (not hidden)
        self.assertTrue(any("narrow move" in g.lower() for g in pulse.data_gaps))

    def test_broad_move_across_many_members_reads_broadening(self):
        sigs = tuple(
            _signal("sig.{0}".format(t), "theme_rotation", "improving", themes=("AI",),
                    companies=(t,)) for t in ("NVDA", "AMD", "AVGO", "TSM"))
        cl = _cluster("cluster.theme.ai", theme="AI",
                      companies=("NVDA", "AMD", "AVGO", "TSM"),
                      signals=tuple(s.signal_id for s in sigs),
                      breadth="major", momentum="improving")
        res = self.syn.synthesize((cl,), sigs)
        self.assertEqual(res.theme_pulses[0].state, "Broadening")


# =========================================================================== #
# social -- social-only narrative never a confident ignition                    #
# =========================================================================== #
class SocialOnlyTests(unittest.TestCase):
    def setUp(self):
        self.syn = rm.ThemePulseSynthesizer()

    def test_social_only_narrative_is_weak_not_high_confidence_ignition(self):
        # Even a 'high'-claimed social narrative stays weak.
        s = _signal("sig.narrative.theme.meme", "narrative", "rising", themes=("MemeCoinCo",),
                    companies=("MEME",), confidence="high", magnitude="major")
        res = self.syn.synthesize((), (s,))
        pulse = res.theme_pulses[0]
        self.assertIn(pulse.state, ("Data insufficient", "Conflicted", "Warming"))
        self.assertNotEqual(pulse.state, "Igniting")
        self.assertNotEqual(pulse.state, "Broadening")
        # confidence capped weak; social gap explicit
        self.assertIn(pulse.confidence_label, ("missing", "very_low", "low"))
        self.assertTrue(any("social-only" in g.lower() for g in pulse.data_gaps))

    def test_social_theme_reads_data_insufficient(self):
        s = _signal("sig.narrative.theme.rumor", "narrative", "rising", themes=("Rumorville",),
                    companies=("RUM",), confidence="low")
        res = self.syn.synthesize((), (s,))
        self.assertEqual(res.theme_pulses[0].state, "Data insufficient")


# =========================================================================== #
# E2 -- market risk-off contradiction preserved (both sides) -> Conflicted       #
# =========================================================================== #
class ContradictionPreservedTests(unittest.TestCase):
    def setUp(self):
        self.syn = rm.ThemePulseSynthesizer()

    def test_market_risk_off_contradiction_preserved_and_conflicts_pulse(self):
        theme_up = _signal("sig.theme_rotation.theme.ai", "theme_rotation", "accelerating",
                           themes=("AI",), companies=("NVDA",), confidence="moderate")
        risk_off = _signal("sig.market_regime.risk-off", "market_regime", "deteriorating",
                           magnitude="major", confidence="high")
        res = self.syn.synthesize((), (theme_up, risk_off))
        # only ONE theme pulse (market_regime signal is a market-wide overlay, not its own theme)
        self.assertEqual(len(res.theme_pulses), 1)
        pulse = res.theme_pulses[0]
        self.assertEqual(pulse.state, "Conflicted")
        # BOTH sides preserved -- neither dropped, no bland average
        self.assertIn("sig.theme_rotation.theme.ai", pulse.supporting_signals)
        self.assertIn("sig.market_regime.risk-off", pulse.contradicting_signals)
        self.assertEqual(pulse.rotation_label, "mixed")
        # the clash is surfaced in conflicts
        self.assertTrue(any("conflicted" in c.lower() for c in pulse.conflicts))

    def test_opposing_theme_signals_preserved_and_conflicted(self):
        up = _signal("sig.a", "theme_rotation", "improving", themes=("EV",), companies=("RIVN",))
        down = _signal("sig.b", "financial_inflection", "deteriorating", themes=("EV",),
                       companies=("RIVN",))
        res = self.syn.synthesize((), (up, down))
        pulse = res.theme_pulses[0]
        self.assertEqual(pulse.state, "Conflicted")
        self.assertIn("sig.a", pulse.supporting_signals)
        self.assertIn("sig.b", pulse.contradicting_signals)


# =========================================================================== #
# E3 -- OpportunityHypothesisPacket contents (diligence questions + refs)        #
# =========================================================================== #
class OpportunityHypothesisTests(unittest.TestCase):
    def setUp(self):
        self.syn = rm.ThemePulseSynthesizer()

    def _one_hypothesis(self):
        s1 = _signal("sig.1", "theme_rotation", "accelerating", themes=("AI",),
                     companies=("NVDA",), corroboration="corroborated")
        s2 = _signal("sig.2", "sector_rotation", "improving", themes=("AI",),
                     companies=("AMD",))
        res = self.syn.synthesize((), (s1, s2))
        self.assertEqual(len(res.hypotheses), 1)
        return res.hypotheses[0]

    def test_hypothesis_always_has_required_diligence_questions(self):
        hyp = self._one_hypothesis()
        self.assertIsInstance(hyp, M.OpportunityHypothesisPacket)
        self.assertTrue(hyp.required_diligence_questions)
        self.assertTrue(all(q.strip() for q in hyp.required_diligence_questions))

    def test_hypothesis_carries_summary_value_chain_and_bottleneck(self):
        hyp = self._one_hypothesis()
        self.assertTrue(hyp.opportunity_summary)
        self.assertTrue(hyp.value_chain_hypothesis)
        self.assertTrue(hyp.bottleneck_hypothesis)
        self.assertIn("TEST", hyp.opportunity_summary)   # for Nivesha to test, not a thesis

    def test_hypothesis_carries_candidates_not_a_ranked_pick_list(self):
        hyp = self._one_hypothesis()
        self.assertIn("NVDA", hyp.beneficiary_candidates)
        self.assertIn("AMD", hyp.beneficiary_candidates)
        # sorted -> a deterministic candidate SET, not a ranked pick order
        self.assertEqual(list(hyp.beneficiary_candidates), sorted(hyp.beneficiary_candidates))

    def test_hypothesis_preserves_both_sided_evidence(self):
        up = _signal("sig.up", "theme_rotation", "improving", themes=("EV",),
                     companies=("RIVN",))
        down = _signal("sig.down", "financial_inflection", "deteriorating", themes=("EV",),
                       companies=("RIVN",))
        res = self.syn.synthesize((), (up, down))
        hyp = res.hypotheses[0]
        self.assertIn("ev.sig.up", hyp.supporting_evidence_refs)
        self.assertIn("ev.sig.down", hyp.contradicting_evidence_refs)
        # the contradiction is echoed into a diligence question
        self.assertTrue(any("contradiction" in q.lower() for q in hyp.required_diligence_questions))

    def test_conflicted_and_social_pulses_still_produce_a_hypothesis_with_questions(self):
        soc = _signal("sig.soc", "narrative", "rising", themes=("Hype",), companies=("HYP",),
                      confidence="low")
        res = self.syn.synthesize((), (soc,))
        self.assertEqual(len(res.hypotheses), 1)
        hyp = res.hypotheses[0]
        self.assertTrue(hyp.required_diligence_questions)
        # a Data-insufficient theme asks what evidence is even needed first
        self.assertTrue(any("primary" in q.lower() or "evidence" in q.lower()
                            for q in hyp.required_diligence_questions))


# =========================================================================== #
# No Nivesha output / no InvestmentThesis / no decision produced                #
# =========================================================================== #
class NoDownstreamDecisionTests(unittest.TestCase):
    def setUp(self):
        self.syn = rm.ThemePulseSynthesizer()

    def test_only_pulses_and_hypotheses_produced_no_thesis_or_bundle(self):
        s = _signal("sig.1", "theme_rotation", "improving", themes=("AI",), companies=("NVDA",))
        res = self.syn.synthesize((), (s,))
        for out in list(res.theme_pulses) + list(res.hypotheses):
            self.assertNotIsInstance(out, M.DiligenceInputBundle)
            # a hypothesis is for Nivesha to TEST -- it is not a thesis object
            self.assertIn(type(out), (M.ThemePulse, M.OpportunityHypothesisPacket))
        # no attribute named or resembling an InvestmentThesis / decision exists anywhere
        self.assertFalse(hasattr(res, "investment_thesis"))
        self.assertFalse(hasattr(res, "thesis"))

    def test_no_trade_score_or_rank_field_on_any_output(self):
        s1 = _signal("sig.1", "theme_rotation", "improving", themes=("AI",), companies=("NVDA",))
        s2 = _signal("sig.2", "sector_rotation", "improving", themes=("AI",), companies=("AMD",))
        res = self.syn.synthesize((), (s1, s2))
        for out in list(res.theme_pulses) + list(res.hypotheses) + [res.envelope]:
            V.assert_no_trade_fields(out)      # reuses the 012A guard
            for name in out.__dataclass_fields__:
                low = name.lower()
                for banned in ("score", "rank", "rating", "buy", "sell",
                               "hold", "order", "trade", "broker"):
                    self.assertNotIn(banned, low)


# =========================================================================== #
# Envelope -- Sphurana -> Nivesha                                               #
# =========================================================================== #
class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.syn = rm.ThemePulseSynthesizer()

    def test_envelope_addressed_to_nivesha_as_opportunity_hypothesis_packet(self):
        s = _signal("sig.1", "theme_rotation", "improving", themes=("AI",), companies=("NVDA",))
        res = self.syn.synthesize((), (s,), now="2026-06-29T00:00:00Z")
        env = res.envelope
        self.assertEqual(env.from_layer, "Sphurana")
        self.assertEqual(env.to_layer, "Nivesha")
        self.assertEqual(env.payload_type, "OpportunityHypothesisPacket")
        self.assertIn("diligence-input", env.allowed_downstream_uses)
        self.assertIn("test", env.allowed_downstream_uses)
        self.assertTrue(env.requires_human_review)

    def test_envelope_carries_four_forbidden_defaults_and_decision_guards(self):
        s = _signal("sig.1", "theme_rotation", "improving", themes=("AI",), companies=("NVDA",))
        res = self.syn.synthesize((), (s,))
        for use in ("broker_order", "auto_execute",
                    "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, res.envelope.forbidden_downstream_uses)
        for use in ("final-decision", "size", "order"):
            self.assertIn(use, res.envelope.forbidden_downstream_uses)
        rm.validate_envelope(res.envelope)

    def test_envelope_preserves_conflict_and_gap_summaries(self):
        theme_up = _signal("sig.up", "theme_rotation", "accelerating", themes=("AI",),
                           companies=("NVDA",))
        risk_off = _signal("sig.market_regime.risk-off", "market_regime", "deteriorating",
                           magnitude="major")
        res = self.syn.synthesize((), (theme_up, risk_off))
        self.assertIn("conflicted", res.envelope.conflict_summary.lower())
        self.assertIn("narrow", res.envelope.data_gap_summary.lower())


# =========================================================================== #
# Determinism                                                                  #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def setUp(self):
        self.syn = rm.ThemePulseSynthesizer()

    def test_synthesis_is_order_independent_and_byte_stable(self):
        a = _signal("sig.a", "theme_rotation", "improving", themes=("AI",), companies=("NVDA",))
        b = _signal("sig.b", "sector_rotation", "improving", themes=("AI",), companies=("AMD",))
        r1 = self.syn.synthesize((), (a, b), now="2026-06-29T00:00:00Z")
        r2 = self.syn.synthesize((), (b, a), now="2026-06-29T00:00:00Z")
        self.assertEqual([repr(p) for p in r1.theme_pulses], [repr(p) for p in r2.theme_pulses])
        self.assertEqual([repr(h) for h in r1.hypotheses], [repr(h) for h in r2.hypotheses])
        self.assertEqual(r1.envelope.envelope_id, r2.envelope.envelope_id)

    def test_envelope_id_has_no_wall_clock(self):
        s = _signal("sig.1", "theme_rotation", "improving", themes=("AI",), companies=("NVDA",))
        r1 = self.syn.synthesize((), (s,), now="")
        r2 = self.syn.synthesize((), (s,), now="")
        self.assertEqual(r1.envelope.envelope_id, r2.envelope.envelope_id)


# =========================================================================== #
# fusion -> sphurana end-to-end (rotation findings -> fuse -> clusters -> pulse) #
# =========================================================================== #
class FusionToSphuranaTests(unittest.TestCase):
    def test_theme_rotation_findings_flow_through_fusion_into_a_pulse(self):
        def _finding(fid, agent, discipline, **kw):
            base = dict(
                agent_layer="Tattva", agent_name=agent,
                finding_type="{0}Finding".format(discipline),
                confidence_label="moderate", freshness_label="fresh", half_life="days",
                evidence_refs=("ev.{0}".format(fid),), source_refs=("src.{0}".format(fid),),
                routing_targets=("TattvaSignalFusion",))
            base.update(kw)
            return M.AgentFinding(finding_id=fid, agent_id=agent, discipline=discipline, **base)

        f1 = _finding("F1", "tattva.theme_rotation", "theme_rotation",
                      affected_themes=("Physical AI",), affected_companies=("NVDA",),
                      direction_label="accelerating", magnitude_label="moderate")
        f2 = _finding("F2", "tattva.sector_rotation", "sector_rotation",
                      affected_themes=("Physical AI",), affected_companies=("TSLA",),
                      direction_label="improving", magnitude_label="moderate")
        fuser = rm.TattvaSignalFusionSynthesizer()
        fused = fuser.fuse((), (f1, f2))
        self.assertTrue(fused.clusters)   # theme cluster formed

        syn = rm.ThemePulseSynthesizer()
        res = syn.synthesize(fused.clusters, fused.signals)
        self.assertEqual(len(res.theme_pulses), 1)
        pulse = res.theme_pulses[0]
        self.assertEqual(pulse.theme_name, "Physical AI")
        self.assertIn(pulse.state, ("Warming", "Igniting", "Broadening"))
        self.assertEqual(len(res.hypotheses), 1)
        self.assertTrue(res.hypotheses[0].required_diligence_questions)
        self.assertEqual(res.envelope.to_layer, "Nivesha")


# =========================================================================== #
# Offline / AST / demo guardrails                                              #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "selenium", "scrapy", "lxml", "websocket", "websockets"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal"}

    def test_sphurana_imports_no_network_scheduler_or_broker(self):
        with open(os.path.join(_PKG_DIR, "sphurana.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.append((node.module or "").split(".")[0])
        for m in mods:
            self.assertNotIn(m, self._NET, "sphurana imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "sphurana imports forbidden {0}".format(m))

    def test_sphurana_defines_no_scoring_or_ranking_function(self):
        with open(os.path.join(_PKG_DIR, "sphurana.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "sphurana: {0}".format(node.name))

    def test_sphurana_has_no_broker_thesis_or_order_affordance(self):
        with open(os.path.join(_PKG_DIR, "sphurana.py"), encoding="utf-8") as fh:
            blob = fh.read().lower()
        for banned in ("place_order", "submit_order", "execute_trade", "investmentthesis",
                       "schedule.every", "cron", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_sphurana_runs_offline_under_socket_killswitch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            syn = rm.ThemePulseSynthesizer()
            s = _signal("sig.1", "theme_rotation", "improving", themes=("AI",),
                        companies=("NVDA",))
            res = syn.synthesize((), (s,))
        finally:
            socket.socket = real
        self.assertEqual(res.envelope.to_layer, "Nivesha")

    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_sphurana_a_")
        d2 = tempfile.mkdtemp(prefix="rm_sphurana_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))


if __name__ == "__main__":
    unittest.main()
