"""IMPLEMENTATION-012C -- Tattva Signal Fusion Synthesizer (the FIRST synthesizer).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE against in-process constructions -- no
fixture endpoint, no network, no scheduler, no broker. It proves the ARCHITECTURE_CONTRACT_012
§D synthesizer-integrity invariants the gate enforces (TEST_MATRIX_012 §C + global guardrails
§I):

* C1 -- findings + events fuse into RealitySignal(s) / SignalCluster(s); NO thesis / hypothesis
  / buy-sell / rank / score produced.
* C2 -- contradictions preserved: a contradicting finding is NOT averaged away; both sides stay
  in ``source_findings``, ``contradiction_status="contradicted"``, the clash is in ``conflicts``.
* C3 -- weak stays weak: a lone finding is uncorroborated; >=2 independent findings that agree
  are marked ``corroborated``.
* C4 -- half-life / freshness applied: a stale finding marks the signal stale (not dropped).
* C5 -- X/social (rumor) never becomes verified/high on its own; corroboration by a NON-social
  finding improves ``corroboration_status`` but MUST NOT change authority (rumor stays rumor).
* Envelope -- the Fusion -> Sphurana HandoffEnvelope carries the four forbidden defaults +
  preserved authority / freshness / conflict / data-gap summaries.
* Guardrails -- data gaps preserved end-to-end; no score/rank/trade field on any output; whole
  suite offline under a socket kill-switch; no net/scheduler/broker import + no `def *score`/
  `*rank` (AST over reality_mesh); demo default byte-identical.
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
from reality_mesh import fusion as FU
from reality_mesh import models as M
from reality_mesh import validation as V

_PKG_DIR = os.path.join(_SRC, "reality_mesh")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# --------------------------------------------------------------------------- #
# Finding builders (test-only fixtures -- NOT shipped in src)                   #
# --------------------------------------------------------------------------- #
def _finding(finding_id, agent_id, discipline, **kw):
    base = dict(
        agent_layer="reality_intelligence", agent_name=agent_id,
        finding_type="{0}Finding".format(discipline),
        confidence_label="moderate", freshness_label="fresh", half_life="days",
        evidence_refs=("ev.{0}".format(finding_id),),
        source_refs=("src.{0}".format(finding_id),),
        routing_targets=("SignalFusion",))
    base.update(kw)
    return M.AgentFinding(
        finding_id=finding_id, agent_id=agent_id, discipline=discipline, **base)


def _macro(fid, agent, **kw):
    defaults = dict(affected_companies=("AAPL",), direction_label="deteriorating",
                    magnitude_label="moderate", source_authority_summary="convenience")
    defaults.update(kw)
    return _finding(fid, agent, "macro_regime", **defaults)


def _social(fid, agent="tattva.narrative", company="IREN", **kw):
    defaults = dict(affected_companies=(company,), direction_label="rising",
                    magnitude_label="minor", source_authority_summary="rumor")
    defaults.update(kw)
    return _finding(fid, agent, "narrative", **defaults)


# =========================================================================== #
# C1 -- findings + events -> RealitySignal / SignalCluster (no thesis/rank)     #
# =========================================================================== #
class FuseIntoSignalTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_multiple_findings_combine_into_one_signal(self):
        a = _macro("F1", "tattva.macro_regime", data_gaps=("g1",))
        b = _macro("F2", "tattva.market_regime", magnitude_label="minor",
                   confidence_label="low")
        res = self.fuser.fuse((), (a, b))
        self.assertEqual(len(res.signals), 1)
        sig = res.signals[0]
        self.assertIsInstance(sig, M.RealitySignal)
        # both findings fused into the one signal (nothing dropped)
        self.assertEqual(sig.source_findings, ("F1", "F2"))
        self.assertEqual(sig.discipline, "macro_regime")
        # evidence + gaps preserved end-to-end
        self.assertIn("ev.F1", sig.evidence_refs)
        self.assertIn("ev.F2", sig.evidence_refs)
        self.assertIn("g1", sig.data_gaps)

    def test_fuse_returns_unpackable_result_with_envelope(self):
        res = self.fuser.fuse((), (_macro("F1", "a1"),))
        signals, clusters, envelope = res          # FusionResult is iterable
        self.assertEqual(signals, res.signals)
        self.assertEqual(clusters, res.clusters)
        self.assertIsInstance(envelope, M.HandoffEnvelope)

    def test_related_findings_cluster_into_signalcluster(self):
        t1 = _finding("T1", "a1", "theme_rotation", affected_themes=("AI",),
                      affected_companies=("NVDA",), direction_label="rising")
        t2 = _finding("T2", "a2", "sector_rotation", affected_themes=("AI",),
                      affected_companies=("AMD",), direction_label="rising")
        res = self.fuser.fuse((), (t1, t2))
        self.assertEqual(len(res.clusters), 1)
        cluster = res.clusters[0]
        self.assertIsInstance(cluster, M.SignalCluster)
        self.assertEqual(cluster.theme, "AI")
        self.assertEqual(len(cluster.signals), 2)
        self.assertIn("NVDA", cluster.companies)
        self.assertIn("AMD", cluster.companies)

    def test_no_thesis_hypothesis_or_packet_produced(self):
        res = self.fuser.fuse((), (_macro("F1", "a1"),))
        for out in list(res.signals) + list(res.clusters):
            self.assertNotIsInstance(out, M.OpportunityHypothesisPacket)
            self.assertNotIsInstance(out, M.ThemePulse)
            self.assertNotIsInstance(out, M.DiligenceInputBundle)


# =========================================================================== #
# C2 -- contradictions preserved (NOT averaged away)                           #
# =========================================================================== #
class ContradictionTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_contradicting_findings_preserved_not_averaged(self):
        up = _finding("P1", "a1", "financial_inflection", affected_companies=("TSLA",),
                      direction_label="improving", magnitude_label="major",
                      confidence_label="high")
        down = _finding("P2", "a2", "financial_inflection", affected_companies=("TSLA",),
                        direction_label="deteriorating", magnitude_label="moderate",
                        confidence_label="high")
        res = self.fuser.fuse((), (up, down))
        self.assertEqual(len(res.signals), 1)
        sig = res.signals[0]
        # BOTH sides preserved -- neither dropped, no bland average
        self.assertEqual(sig.source_findings, ("P1", "P2"))
        self.assertEqual(sig.contradiction_status, "contradicted")
        self.assertEqual(sig.direction_label, "mixed")
        # the clash is surfaced in conflicts and names both findings
        joined = " ".join(sig.conflicts)
        self.assertIn("contradiction", joined.lower())
        self.assertIn("P1", joined)
        self.assertIn("P2", joined)
        # contradiction caps confidence (never upgraded through a clash)
        self.assertIn(sig.confidence_label, ("very_low", "low"))


# =========================================================================== #
# C3 -- weak stays weak; corroboration marks corroborated                      #
# =========================================================================== #
class CorroborationTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_lone_finding_is_uncorroborated(self):
        res = self.fuser.fuse((), (_macro("F1", "a1"),))
        self.assertEqual(res.signals[0].corroboration_status, "uncorroborated")

    def test_two_independent_agreeing_findings_corroborated(self):
        a = _macro("F1", "tattva.macro_regime")
        b = _macro("F2", "tattva.market_regime")   # different agent -> independent
        res = self.fuser.fuse((), (a, b))
        self.assertEqual(res.signals[0].corroboration_status, "corroborated")

    def test_same_agent_repeats_do_not_corroborate(self):
        a = _macro("F1", "tattva.macro_regime")
        b = _macro("F2", "tattva.macro_regime")   # SAME agent -> not independent
        res = self.fuser.fuse((), (a, b))
        self.assertEqual(res.signals[0].corroboration_status, "uncorroborated")

    def test_weak_signal_not_upgraded_without_corroboration(self):
        # a lone low-confidence finding stays low (no silent upgrade)
        low = _macro("F1", "a1", confidence_label="low")
        res = self.fuser.fuse((), (low,))
        self.assertEqual(res.signals[0].confidence_label, "low")
        self.assertEqual(res.signals[0].corroboration_status, "uncorroborated")


# =========================================================================== #
# C4 -- freshness / half-life applied; stale marked not dropped                #
# =========================================================================== #
class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_stale_finding_marks_signal_stale_not_dropped(self):
        fresh = _finding("A1", "a1", "technical_regime", affected_companies=("NVDA",),
                         direction_label="rising", freshness_label="fresh")
        stale = _finding("A2", "a2", "technical_regime", affected_companies=("NVDA",),
                         direction_label="rising", freshness_label="stale")
        res = self.fuser.fuse((), (fresh, stale))
        sig = res.signals[0]
        # stalest freshness surfaced; stale finding preserved (not silently dropped)
        self.assertEqual(sig.freshness_label, "stale")
        self.assertIn("A2", sig.source_findings)
        self.assertTrue(any("stale" in g.lower() for g in sig.data_gaps))

    def test_half_life_rolled_to_shortest(self):
        a = _finding("H1", "a1", "macro_regime", affected_companies=("AAPL",),
                     direction_label="rising", half_life="weeks")
        b = _finding("H2", "a2", "macro_regime", affected_companies=("AAPL",),
                     direction_label="rising", half_life="hours")
        res = self.fuser.fuse((), (a, b))
        self.assertEqual(res.signals[0].half_life, "hours")


# =========================================================================== #
# C5 -- X/social stays weak; rumor never verified; corroboration != authority  #
# =========================================================================== #
class SocialSignalTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_social_only_signal_stays_weak_and_uncorroborated(self):
        res = self.fuser.fuse((), (_social("X1", confidence_label="moderate"),))
        sig = res.signals[0]
        self.assertEqual(sig.discipline, "narrative")
        self.assertEqual(sig.corroboration_status, "uncorroborated")
        # a lone social claim is capped weak even if the finding claimed 'moderate'
        self.assertIn(sig.confidence_label, ("very_low", "low"))
        # authority stays rumor -- never lifted to a verified/fact tier
        self.assertEqual(res.authority_by_signal[sig.signal_id], "rumor")
        # the weakness is stated as an explicit gap (missing corroboration not hidden)
        self.assertTrue(any("rumor" in g.lower() for g in sig.data_gaps))

    def test_social_signal_has_no_verified_fact_claim_field(self):
        # structural: a RealitySignal carries NO claim_status/authority field to smuggle a fact
        res = self.fuser.fuse((), (_social("X1"),))
        names = {f for f in res.signals[0].__dataclass_fields__}
        self.assertNotIn("claim_status", names)
        self.assertNotIn("source_authority", names)

    def test_nonsocial_corroboration_improves_status_but_not_authority(self):
        soc = _social("X1", company="IREN", confidence_label="low")
        news = _finding("N1", "tattva.news_filings", "news_filings",
                        affected_companies=("IREN",), direction_label="rising",
                        magnitude_label="moderate", source_authority_summary="primary")
        res = self.fuser.fuse((), (soc, news))
        narr = [s for s in res.signals if s.discipline == "narrative"][0]
        # corroboration_status improved by the independent non-social finding ...
        self.assertEqual(narr.corroboration_status, "corroborated")
        # ... but authority MUST stay rumor (rumor stays rumor)
        self.assertEqual(res.authority_by_signal[narr.signal_id], "rumor")
        # ... and confidence is still bounded (never high off a corroborated rumor)
        self.assertNotIn(narr.confidence_label, ("high", "very_high"))

    def test_social_corroborated_only_by_other_social_stays_partial(self):
        s1 = _social("X1", agent="tattva.narrative", company="IREN")
        s2 = _social("X2", agent="tattva.narrative_promoter", company="IREN")
        res = self.fuser.fuse((), (s1, s2))
        narr = [s for s in res.signals if s.discipline == "narrative"][0]
        # two social sources are NOT full corroboration (rumor echoing rumor)
        self.assertEqual(narr.corroboration_status, "partially_corroborated")
        self.assertEqual(res.authority_by_signal[narr.signal_id], "rumor")


# =========================================================================== #
# Envelope -- Fusion -> Sphurana                                               #
# =========================================================================== #
class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_envelope_addressed_to_sphurana_as_tattva_signal_packet(self):
        res = self.fuser.fuse((), (_macro("F1", "a1"),), now="2026-06-29T00:00:00Z")
        env = res.envelope
        self.assertEqual(env.from_layer, "reality_intelligence")
        self.assertEqual(env.to_layer, "opportunity_discovery")
        self.assertEqual(env.payload_type, "TattvaSignalPacket")
        self.assertIn("hypothesize", env.allowed_downstream_uses)
        self.assertIn(res.signals[0].signal_id, env.payload_ids)

    def test_envelope_carries_four_forbidden_defaults(self):
        res = self.fuser.fuse((), (_macro("F1", "a1"),))
        for use in ("broker_order", "auto_execute",
                    "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, res.envelope.forbidden_downstream_uses)
        rm.validate_envelope(res.envelope)

    def test_envelope_preserves_authority_freshness_conflict_gap_summaries(self):
        a = _macro("F1", "a1", data_gaps=("gapX",))
        b = _finding("F2", "a2", "macro_regime", affected_companies=("AAPL",),
                     direction_label="improving", source_authority_summary="primary")
        res = self.fuser.fuse((), (a, b))
        env = res.envelope
        # best authority rolled up (primary > convenience)
        self.assertEqual(env.authority_summary, "primary")
        self.assertIn("gapX", env.data_gap_summary)          # data gap preserved
        self.assertIn("contradiction", env.conflict_summary.lower())  # conflict preserved

    def test_envelope_folds_in_supplied_conflict_records(self):
        res = self.fuser.fuse(
            (), (_macro("F1", "a1"),),
            conflict_records=("adhara: DGS10 value mismatch across sources",))
        self.assertIn("DGS10", res.envelope.conflict_summary)

    def test_social_signal_flags_human_review(self):
        res = self.fuser.fuse((), (_social("X1"),))
        self.assertTrue(res.envelope.requires_human_review)


# =========================================================================== #
# No score / rank / trade field on ANY output                                  #
# =========================================================================== #
class NoScoreRankTradeTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_outputs_carry_no_trade_or_score_field(self):
        t1 = _finding("T1", "a1", "theme_rotation", affected_themes=("AI",),
                      affected_companies=("NVDA",), direction_label="rising")
        t2 = _finding("T2", "a2", "sector_rotation", affected_themes=("AI",),
                      affected_companies=("AMD",), direction_label="rising")
        res = self.fuser.fuse((), (t1, t2))
        for out in list(res.signals) + list(res.clusters) + [res.envelope]:
            V.assert_no_trade_fields(out)      # reuses the 012A guard
            for name in out.__dataclass_fields__:
                low = name.lower()
                for banned in ("score", "rank", "rating", "buy", "sell",
                               "hold", "order", "trade", "broker"):
                    self.assertNotIn(banned, low)


# =========================================================================== #
# Determinism                                                                  #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_fusion_is_order_independent_and_byte_stable(self):
        a = _macro("F1", "a1")
        b = _finding("F2", "a2", "macro_regime", affected_companies=("AAPL",),
                     direction_label="deteriorating")
        r1 = self.fuser.fuse((), (a, b), now="2026-06-29T00:00:00Z")
        r2 = self.fuser.fuse((), (b, a), now="2026-06-29T00:00:00Z")
        self.assertEqual([repr(s) for s in r1.signals], [repr(s) for s in r2.signals])
        self.assertEqual(r1.envelope.envelope_id, r2.envelope.envelope_id)

    def test_envelope_id_has_no_wall_clock(self):
        # id is content-derived from payload ids + injected now, never time.time()
        r1 = self.fuser.fuse((), (_macro("F1", "a1"),), now="")
        r2 = self.fuser.fuse((), (_macro("F1", "a1"),), now="")
        self.assertEqual(r1.envelope.envelope_id, r2.envelope.envelope_id)


# =========================================================================== #
# Offline / AST / demo guardrails                                              #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "selenium", "scrapy", "lxml", "websocket", "websockets"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal"}

    def _pkg_py_files(self):
        return [
            os.path.join(_PKG_DIR, f)
            for f in sorted(os.listdir(_PKG_DIR)) if f.endswith(".py")]

    def test_reality_mesh_imports_no_network_scheduler_or_broker(self):
        for path in self._pkg_py_files():
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

    def test_reality_mesh_defines_no_scoring_or_ranking_function(self):
        for path in self._pkg_py_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    low = node.name.lower()
                    for tok in ("score", "rank", "rating"):
                        self.assertNotIn(tok, low, "{0}: {1}".format(path, node.name))

    def test_fusion_has_no_broker_or_order_affordance(self):
        with open(os.path.join(_PKG_DIR, "fusion.py"), encoding="utf-8") as fh:
            blob = fh.read().lower()
        for banned in ("place_order", "submit_order", "execute_trade",
                       "schedule.every", "cron", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_fusion_runs_offline_under_socket_killswitch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            fuser = rm.TattvaSignalFusionSynthesizer()
            res = fuser.fuse((), (_macro("F1", "a1"), _macro("F2", "a2")))
        finally:
            socket.socket = real
        self.assertEqual(res.envelope.to_layer, "opportunity_discovery")

    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_fusion_a_")
        d2 = tempfile.mkdtemp(prefix="rm_fusion_b_")
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
