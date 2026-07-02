"""IMPLEMENTATION-012H -- X / Social Narrative sensor agent (fixture-backed, weak-signal only).

TEST_MATRIX_012 §D4 (+ §C5 / §D5 / §I global guardrails). This suite runs entirely OFFLINE
against small deterministic JSON fixtures under ``tests/fixtures/reality_mesh/social/`` -- NO
network, NO live X, NO scraping, NO credentials, no scheduler, no broker. It proves the STRICTEST
sensor's 012 invariants the gate enforces:

* D4 -- a mention spike -> ``NarrativeFinding``; a theme mention spike ->
  ``ThemeNarrativeVelocityFinding``; an unknown-account rumor -> ``RumorFinding`` (weak /
  low-confidence); an official company account -> ``company_claim`` (NOT verified_fact); a
  journalist -> ``reported_claim`` (NOT verified_fact); a bot/promoter -> ``PromotionRiskFinding``
  with the risk VISIBLE.
* §C5 authority discipline -- EVERY finding is ``rumor`` authority, NEVER ``verified_fact`` /
  ``canonical``. A social-ONLY theme spike routed -> fused -> Sphurana does NOT become a
  high-confidence ThemePulse (it yields ``Data insufficient`` / weak). Corroboration by a
  NON-social (news / market) finding improves ``corroboration_status`` but NEVER converts the
  social signal to a verified fact or lifts its authority: rumor stays rumor.
* §D5 -- the agent stays strictly within the ``narrative`` discipline; a missing/absent field
  surfaces as an explicit data gap (never fabricated); stale input is marked stale + a gap.
* guardrails -- AgentFinding-only; no buy/sell/score/rank field; no net/scheduler/broker import +
  no ``def *score``/``*rank`` in the sensors package (AST); whole suite offline under a socket
  kill-switch; demo default byte-identical.
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
    SocialNarrativeAgent,
    events_from_fixture,
    claim_status_of,
    assert_narrative_not_verified,
    social_narrative as SN,
)

_FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "reality_mesh", "social")
_SENSORS_DIR = os.path.join(_SRC, "reality_mesh", "sensors")

_ALL_FIXTURES = (
    "mention_spike", "theme_mention_spike", "unknown_account_rumor",
    "official_company_account", "journalist_account", "promoter_bot", "crowding",
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _load(name):
    return events_from_fixture(os.path.join(_FIXTURES, name + ".json"))


def _run(name):
    return SocialNarrativeAgent().run_checked(None, _load(name))


def _types(findings):
    return {f.finding_type for f in findings}


def _of_type(findings, ftype):
    return [f for f in findings if f.finding_type == ftype]


# =========================================================================== #
# D4 -- mention / theme / rumor / account / bot from fixtures                   #
# =========================================================================== #
class NarrativeFindingTypeTests(unittest.TestCase):
    def test_mention_spike_emits_narrative_finding(self):
        findings = _run("mention_spike")
        self.assertIn("NarrativeFinding", _types(findings))
        f = _of_type(findings, "NarrativeFinding")[0]
        self.assertEqual(f.discipline, "narrative")
        self.assertIn(f.direction_label, ("rising", "accelerating"))
        self.assertIsInstance(f, M.AgentFinding)
        # attention / velocity is a weak label, not a fact.
        self.assertIn(f.confidence_label, ("very_low", "low"))

    def test_theme_mention_spike_emits_theme_velocity_finding(self):
        findings = _run("theme_mention_spike")
        self.assertIn("ThemeNarrativeVelocityFinding", _types(findings))
        f = _of_type(findings, "ThemeNarrativeVelocityFinding")[0]
        self.assertEqual(f.affected_themes, ("AI Agents",))
        self.assertEqual(f.source_authority_summary, "rumor")

    def test_unknown_account_rumor_is_weak_rumor_finding(self):
        findings = _run("unknown_account_rumor")
        self.assertIn("RumorFinding", _types(findings))
        f = _of_type(findings, "RumorFinding")[0]
        self.assertEqual(claim_status_of(f), "rumor")
        self.assertEqual(f.confidence_label, "very_low")
        self.assertEqual(f.corroboration_status, "uncorroborated")

    def test_official_company_account_is_company_claim_not_verified_fact(self):
        findings = _run("official_company_account")
        self.assertIn("CompanyClaimFinding", _types(findings))
        f = _of_type(findings, "CompanyClaimFinding")[0]
        self.assertEqual(claim_status_of(f), "company_claim")
        self.assertNotEqual(claim_status_of(f), "verified_fact")
        # even the official company account on social is rumor authority (never canonical).
        self.assertEqual(f.source_authority_summary, "rumor")

    def test_journalist_account_is_reported_claim_not_verified_fact(self):
        findings = _run("journalist_account")
        f = findings[0]
        self.assertEqual(claim_status_of(f), "reported_claim")
        self.assertNotEqual(claim_status_of(f), "verified_fact")
        self.assertEqual(f.source_authority_summary, "rumor")

    def test_promoter_bot_emits_promotion_risk_with_visible_risk(self):
        findings = _run("promoter_bot")
        self.assertIn("PromotionRiskFinding", _types(findings))
        f = _of_type(findings, "PromotionRiskFinding")[0]
        # the promoter/bot risk must be VISIBLE: in the summary, conflicts, and data gaps.
        self.assertIn("bot", f.finding_summary.lower())
        joined_conf = " ".join(f.conflicts).lower()
        self.assertIn("promoter/bot risk", joined_conf)
        joined_gap = " ".join(f.data_gaps).lower()
        self.assertIn("promoter/bot risk", joined_gap)
        self.assertEqual(f.source_authority_summary, "rumor")

    def test_crowding_emits_crowding_finding(self):
        findings = _run("crowding")
        self.assertIn("CrowdingFinding", _types(findings))
        f = _of_type(findings, "CrowdingFinding")[0]
        self.assertEqual(f.source_authority_summary, "rumor")

    def test_all_finding_types_are_in_the_declared_vocabulary(self):
        for name in _ALL_FIXTURES:
            for f in _run(name):
                self.assertIn(f.finding_type, SN.SOCIAL_NARRATIVE_FINDING_TYPES)

    def test_findings_carry_only_valid_closed_labels(self):
        for name in _ALL_FIXTURES:
            for f in _run(name):
                self.assertIn(f.direction_label, rm.DIRECTION_LABELS)
                self.assertIn(f.magnitude_label, rm.MAGNITUDE_LABELS)
                self.assertIn(f.urgency_label, rm.URGENCY_LABELS)
                self.assertIn(f.confidence_label, rm.CONFIDENCE_LABELS)
                self.assertIn(f.freshness_label, rm.FRESHNESS_LABELS)
                V.validate_finding(f)


# =========================================================================== #
# §C5 authority discipline -- rumor ALWAYS; never verified_fact / canonical     #
# =========================================================================== #
class AuthorityDisciplineTests(unittest.TestCase):
    def test_every_finding_is_rumor_authority(self):
        for name in _ALL_FIXTURES:
            for f in _run(name):
                self.assertEqual(
                    f.source_authority_summary, "rumor",
                    "every social finding must be rumor authority: {0}".format(f.finding_id))

    def test_no_finding_is_ever_verified_fact_or_canonical(self):
        for name in _ALL_FIXTURES:
            for f in _run(name):
                self.assertNotEqual(claim_status_of(f), "verified_fact")
                self.assertNotEqual(claim_status_of(f), "canonical")
                self.assertNotEqual(f.source_authority_summary, "canonical")
                # the module-level finding guard agrees.
                assert_narrative_not_verified(f)

    def test_findings_default_weak_and_uncorroborated(self):
        for name in _ALL_FIXTURES:
            for f in _run(name):
                self.assertIn(f.confidence_label, ("missing", "very_low", "low"))
                self.assertEqual(f.corroboration_status, "uncorroborated")

    def test_account_claim_flavors_never_become_verified(self):
        # company_claim / reported_claim / expert_narrative / rumor -- none are verified_fact.
        flavor_by = {
            "official_company_account": "company_claim",
            "journalist_account": "reported_claim",
            "unknown_account_rumor": "rumor",
        }
        for name, flavor in flavor_by.items():
            f = _run(name)[0]
            self.assertEqual(claim_status_of(f), flavor)
            self.assertNotEqual(claim_status_of(f), "verified_fact")


# =========================================================================== #
# §C5 -- social stays weak end-to-end (fusion + sphurana Data-insufficient)     #
# =========================================================================== #
class SocialStaysWeakTests(unittest.TestCase):
    def setUp(self):
        self.fuser = rm.TattvaSignalFusionSynthesizer()
        self.sphurana = rm.ThemePulseSynthesizer()

    def test_social_only_theme_spike_does_not_become_high_confidence_pulse(self):
        evs = _load("theme_mention_spike")
        findings = _run("theme_mention_spike")
        res = self.fuser.fuse(evs, findings, now="")
        self.assertTrue(res.signals)
        sig = res.signals[0]
        # the fused signal keeps rumor authority + weak confidence.
        self.assertEqual(res.authority_by_signal[sig.signal_id], "rumor")
        self.assertIn(sig.confidence_label, ("missing", "very_low", "low"))
        # Sphurana: a social-only theme is Data insufficient (NOT a confident ignition).
        sph = self.sphurana.synthesize(res.clusters, res.signals, now="")
        self.assertTrue(sph.theme_pulses)
        pulse = sph.theme_pulses[0]
        self.assertEqual(pulse.state, "Data insufficient")
        self.assertNotEqual(pulse.state, "Igniting")
        self.assertNotEqual(pulse.state, "Broadening")
        self.assertIn(pulse.confidence_label, ("missing", "very_low", "low"))
        gap_text = " ".join(pulse.data_gaps).lower()
        self.assertIn("social-only", gap_text)

    def test_corroboration_by_non_social_lifts_status_not_authority(self):
        # a rising narrative mention on NOVA + a NON-social (canonical news) finding on NOVA.
        evs = _load("mention_spike")
        narrative = _run("mention_spike")
        news = M.AgentFinding(
            finding_id="finding.news_filings.contract.nova",
            agent_id="tattva.news_filings", agent_layer="Tattva", agent_name="News Filings",
            discipline="news_filings", input_events=("nf.nova",),
            finding_type="contract_validation",
            finding_summary="contract validated | claim_status=verified_fact",
            affected_companies=("NOVA",), direction_label="improving", magnitude_label="moderate",
            urgency_label="watch", confidence_label="moderate", freshness_label="fresh",
            half_life="weeks", source_authority_summary="canonical",
            corroboration_status="partially_corroborated", contradiction_status="unopposed",
            routing_targets=("TattvaSignalFusion",))
        res = self.fuser.fuse(evs, tuple(narrative) + (news,), now="")
        narr_sigs = [s for s in res.signals if s.discipline == "narrative"]
        self.assertTrue(narr_sigs)
        nsig = narr_sigs[0]
        # corroboration IMPROVES ...
        self.assertEqual(res.corroboration_by_signal[nsig.signal_id], "corroborated")
        # ... but the authority stays rumor (NOT lifted to canonical / a verified fact).
        self.assertEqual(res.authority_by_signal[nsig.signal_id], "rumor")
        self.assertNotEqual(res.authority_by_signal[nsig.signal_id], "canonical")
        # and confidence is still capped weak for a social signal.
        self.assertIn(nsig.confidence_label, ("missing", "very_low", "low", "moderate"))
        self.assertNotIn(nsig.confidence_label, ("high", "very_high"))


# =========================================================================== #
# §D5 -- discipline-bound; missing input -> gap; stale -> stale + gap           #
# =========================================================================== #
class MissingStaleAndDisciplineTests(unittest.TestCase):
    def test_missing_metadata_surfaces_explicit_data_gaps(self):
        # the rumor fixture carries no author breadth / velocity -> visible gaps, never faked.
        findings = _run("unknown_account_rumor")
        gap_text = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("uncorroborated", gap_text)
        # no confidence was invented above weak.
        self.assertEqual(findings[0].confidence_label, "very_low")

    def test_theme_spike_missing_author_breadth_is_a_gap(self):
        # inject a theme spike with no unique_authors -> explicit single-account-artefact gap.
        rec = {
            "event_id": "narr.theme.thin", "discipline": "narrative", "source_type": "x_social",
            "event_type": "theme_mention_spike", "affected_themes": ["Quantum"],
            "observed_fact": "theme mention spike for Quantum",
            "numeric_values": [["mention_count", 500, "count"]],
            "confidence_label": "low", "freshness_label": "fresh",
        }
        findings = SocialNarrativeAgent().run_checked(None, events_from_fixture([rec]))
        gap_text = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("unique-author breadth not disclosed", gap_text)

    def test_stale_input_marks_finding_stale_and_notes_gap(self):
        rec = {
            "event_id": "narr.stale.nova", "discipline": "narrative", "source_type": "x_social",
            "event_type": "social_mention_spike", "affected_companies": ["NOVA"],
            "observed_fact": "old mention spike for NOVA",
            "numeric_values": [["mention_velocity_zscore", 3.0, "zscore"],
                               ["unique_authors", 700, "count"]],
            "confidence_label": "low", "freshness_label": "stale",
        }
        findings = SocialNarrativeAgent().run_checked(None, events_from_fixture([rec]))
        self.assertTrue(findings, "stale findings must NOT be dropped")
        for f in findings:
            self.assertEqual(f.freshness_label, "stale")
        gap_text = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("stale", gap_text)

    def test_agent_stays_within_narrative_discipline(self):
        agent = SocialNarrativeAgent()
        self.assertEqual(agent.descriptor.discipline, "narrative")
        self.assertEqual(agent.descriptor.agent_id, "tattva.narrative")
        for name in _ALL_FIXTURES:
            for f in agent.run_checked(None, _load(name)):
                self.assertEqual(f.discipline, "narrative")

    def test_agent_reuses_builtin_narrative_descriptor(self):
        agent = SocialNarrativeAgent()
        builtin = rm.build_default_registry().get("tattva.narrative")
        self.assertEqual(agent.descriptor.agent_id, builtin.agent_id)
        self.assertEqual(agent.descriptor.discipline, builtin.discipline)
        self.assertIn("NarrativeFinding", agent.descriptor.emits)
        # the narrative descriptor defaults to rumor/social sources (never canonical/verified).
        self.assertNotIn("canonical", agent.descriptor.allowed_sources)
        self.assertNotIn("verified_fact", agent.descriptor.allowed_sources)
        self.assertTrue(agent.descriptor.requires_human_review_by_default)


# =========================================================================== #
# AgentFinding-ONLY boundary (no signal/thesis/trade/rank/score)              #
# =========================================================================== #
class BoundaryTests(unittest.TestCase):
    def test_agent_emits_agentfinding_only(self):
        for name in _ALL_FIXTURES:
            for f in _run(name):
                self.assertIsInstance(f, M.AgentFinding)

    def test_findings_have_no_trade_or_score_field(self):
        for name in _ALL_FIXTURES:
            for f in _run(name):
                V.assert_no_trade_fields(f)
                for fname in f.__dataclass_fields__:
                    low = fname.lower()
                    for banned in ("score", "rank", "rating", "buy", "sell", "hold",
                                   "order", "trade", "broker"):
                        self.assertNotIn(banned, low)

    def test_no_finding_summary_contains_a_buy_sell_recommendation(self):
        for name in _ALL_FIXTURES:
            for f in _run(name):
                low = f.finding_summary.lower()
                for banned in ("buy ", "sell ", " rank", "score", "recommend"):
                    self.assertNotIn(banned, low)

    def test_run_checked_rejects_non_reality_event_input(self):
        with self.assertRaises(TypeError):
            SocialNarrativeAgent().run_checked(None, ("not-an-event",))

    def test_deterministic_offline_run(self):
        a = _run("promoter_bot")
        b = _run("promoter_bot")
        self.assertEqual([repr(f) for f in a], [repr(f) for f in b])


# =========================================================================== #
# route -> fuse: 012B BuddhiRouter + 012C synthesizer                         #
# =========================================================================== #
class RouteAndFuseTests(unittest.TestCase):
    def setUp(self):
        self.reg = rm.build_default_registry()
        self.router = rm.BuddhiRouter(self.reg)
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_route_event_picks_narrative(self):
        evs = _load("mention_spike")
        matches = self.router.route_event(evs[0])
        self.assertEqual([d.agent_id for d in matches], ["tattva.narrative"])

    def test_route_finding_wraps_into_handoff_envelope_requiring_review(self):
        findings = _run("mention_spike")
        env = self.router.route_finding(findings[0])
        self.assertIsInstance(env, M.HandoffEnvelope)
        self.assertEqual(env.from_agent, "tattva.narrative")
        self.assertEqual(env.to_synthesizer, "TattvaSignalFusion")
        self.assertEqual(env.authority_summary, "rumor")
        # narrative findings default to requiring human review.
        self.assertTrue(env.requires_human_review)
        for use in ("broker_order", "auto_execute",
                    "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, env.forbidden_downstream_uses)

    def test_full_offline_pipeline_under_socket_killswitch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            evs = events_from_fixture(os.path.join(_FIXTURES, "theme_mention_spike.json"))
            findings = SocialNarrativeAgent().run_checked(None, evs)
            env = self.router.route_finding(findings[0])
            res = self.fuser.fuse(evs, findings, now="")
            sph = rm.ThemePulseSynthesizer().synthesize(res.clusters, res.signals, now="")
        finally:
            socket.socket = real
        self.assertEqual(env.to_synthesizer, "TattvaSignalFusion")
        self.assertTrue(res.signals)
        self.assertEqual(res.signals[0].discipline, "narrative")
        self.assertEqual(sph.theme_pulses[0].state, "Data insufficient")


# =========================================================================== #
# Guardrails -- AST offline / no scoring / no live-X affordance / demo         #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "selenium", "scrapy", "lxml", "websocket", "websockets", "tweepy",
            "praw", "snscrape"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal", "os", "netrc",
                  "keyring", "secrets"}

    def _sensor_py_files(self):
        return [
            os.path.join(_SENSORS_DIR, f)
            for f in sorted(os.listdir(_SENSORS_DIR)) if f.endswith(".py")]

    def test_sensors_import_no_network_scheduler_broker_or_credentials(self):
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

    def test_social_sensor_has_no_live_x_scraping_or_credential_affordance(self):
        # code-affordance tokens only (not prose words like "credentials"/"broker" in the
        # module docstring, which describe what the agent DOES NOT do).
        with open(os.path.join(_SENSORS_DIR, "social_narrative.py"), encoding="utf-8") as fh:
            blob = fh.read().lower()
        for banned in ("requests.get", "urlopen", "socket.socket", "http://", "https://",
                       "api_key", "bearer_token", "access_token", "oauth", "tweepy", "snscrape",
                       "getpass", "os.environ", "keyring", ".netrc", "schedule.every",
                       "place_order", "submit_order", "execute_trade", "broker_order",
                       "broker.submit"):
            self.assertNotIn(banned, blob, "banned live-X/credential token: {0}".format(banned))

    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_sn_a_")
        d2 = tempfile.mkdtemp(prefix="rm_sn_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            with open(p1[name], "rb") as fa, open(p2[name], "rb") as fb:
                self.assertEqual(
                    fa.read(), fb.read(), "demo not byte-identical: {0}".format(name))
        with open(p1["universe.html"], encoding="utf-8") as fh:
            self.assertNotIn("reality_mesh", fh.read())


if __name__ == "__main__":
    unittest.main()
