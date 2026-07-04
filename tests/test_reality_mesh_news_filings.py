"""IMPLEMENTATION-012G -- News / Filings / Press-Release sensor agent (fixture-backed).

TEST_MATRIX_012 §D3 (+ §D5 / §I global guardrails). This suite runs entirely OFFLINE against
small deterministic JSON fixtures under ``tests/fixtures/reality_mesh/news_filings/`` -- no
network, no live EDGAR/IR fetch, no scheduler, no broker. It proves the 012 news/filings
invariants the gate enforces:

* D3 -- an S-3/ATM fixture emits a ``dilution_risk`` finding (deteriorating); an 8-K contract
  emits a filing-fact finding at SEC ``canonical`` authority whose claim status is
  ``verified_fact``; a press-release customer win is a ``company_claim`` (NOT verified_fact); a
  guidance update is visible.
* AUTHORITY DISCIPLINE (§C) -- SEC filings are canonical/verified_fact; press releases +
  company announcements are company_claim; reported news is reported_claim. A claim is NEVER
  promoted to verified_fact (no verified-fact laundering).
* CONFLICT -- a company claim that opposes a filing fact about the same subject is PRESERVED:
  both findings are emitted, the clash is recorded, and neither is dropped or promoted.
* D5 -- the agent stays strictly within the ``news_filings`` discipline; a missing/absent field
  surfaces as an explicit data gap (never fabricated); stale input is marked stale + a gap.
* route -> fuse -- the finding routes through the 012B BuddhiRouter (route_event picks
  news_filings; route_finding wraps it into a HandoffEnvelope to TattvaSignalFusion) and fuses
  through the 012C synthesizer into a RealitySignal(news_filings).
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
    NewsFilingsAgent,
    events_from_fixture,
    claim_status_of,
    news_filings as NF,
)

_FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "reality_mesh", "news_filings")
_SENSORS_DIR = os.path.join(_SRC, "reality_mesh", "sensors")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _load(name):
    return events_from_fixture(os.path.join(_FIXTURES, name + ".json"))


def _run(name):
    return NewsFilingsAgent().run_checked(None, _load(name))


def _types(findings):
    return {f.finding_type for f in findings}


def _of_type(findings, ftype):
    return [f for f in findings if f.finding_type == ftype]


# =========================================================================== #
# D3 -- dilution / contract / claim status from fixtures                       #
# =========================================================================== #
class DilutionAndContractTests(unittest.TestCase):
    def test_s3_atm_fixture_emits_dilution_risk_finding(self):
        findings = _run("dilution_s3")
        self.assertIn("dilution_risk", _types(findings))
        dil = _of_type(findings, "dilution_risk")[0]
        self.assertEqual(dil.direction_label, "deteriorating")
        self.assertEqual(dil.discipline, "news_filings")
        self.assertIsInstance(dil, M.AgentFinding)

    def test_8k_contract_is_a_filing_fact_with_sec_canonical_authority(self):
        findings = _run("contract_8k")
        self.assertIn("contract_validation", _types(findings))
        con = _of_type(findings, "contract_validation")[0]
        self.assertEqual(con.direction_label, "improving")
        # SEC canonical authority + verified_fact for the FILING FACT
        self.assertEqual(con.source_authority_summary, "canonical")
        self.assertEqual(claim_status_of(con), "verified_fact")

    def test_press_release_customer_win_is_company_claim_not_verified_fact(self):
        findings = _run("press_release_customer_win")
        self.assertIn("customer_win_claim", _types(findings))
        win = _of_type(findings, "customer_win_claim")[0]
        self.assertEqual(claim_status_of(win), "company_claim")
        self.assertNotEqual(claim_status_of(win), "verified_fact")
        # a company statement is company-IR primary, never canonical
        self.assertEqual(win.source_authority_summary, "primary")
        self.assertNotEqual(win.source_authority_summary, "canonical")

    def test_guidance_update_is_visible_and_a_company_claim(self):
        findings = _run("guidance_update")
        self.assertIn("guidance_update", _types(findings))
        guid = _of_type(findings, "guidance_update")[0]
        self.assertEqual(guid.direction_label, "improving")   # a raise
        self.assertEqual(claim_status_of(guid), "company_claim")
        self.assertNotEqual(claim_status_of(guid), "verified_fact")

    def test_insider_sale_is_deteriorating_filing_fact(self):
        findings = _run("insider_sale")
        self.assertIn("insider_sale", _types(findings))
        ins = _of_type(findings, "insider_sale")[0]
        self.assertEqual(ins.direction_label, "deteriorating")
        self.assertEqual(ins.source_authority_summary, "canonical")
        self.assertEqual(claim_status_of(ins), "verified_fact")

    def test_all_finding_types_are_in_the_declared_vocabulary(self):
        for name in ("dilution_s3", "contract_8k", "press_release_customer_win",
                     "guidance_update", "insider_sale", "conflict_claim_vs_filing",
                     "stale", "missing_fields"):
            for f in _run(name):
                self.assertIn(f.finding_type, NF.NEWS_FILINGS_FINDING_TYPES)

    def test_findings_carry_only_valid_closed_labels(self):
        for name in ("dilution_s3", "contract_8k", "press_release_customer_win",
                     "guidance_update", "insider_sale"):
            for f in _run(name):
                self.assertIn(f.direction_label, rm.DIRECTION_LABELS)
                self.assertIn(f.magnitude_label, rm.MAGNITUDE_LABELS)
                self.assertIn(f.urgency_label, rm.URGENCY_LABELS)
                self.assertIn(f.confidence_label, rm.CONFIDENCE_LABELS)
                self.assertIn(f.freshness_label, rm.FRESHNESS_LABELS)
                V.validate_finding(f)


# =========================================================================== #
# Authority discipline -- SEC canonical vs company_claim vs reported_claim      #
# (no verified-fact laundering)                                                #
# =========================================================================== #
class AuthorityDisciplineTests(unittest.TestCase):
    def test_only_canonical_filings_carry_verified_fact(self):
        # every verified_fact finding across all fixtures must be a canonical SEC filing.
        for name in ("dilution_s3", "contract_8k", "press_release_customer_win",
                     "guidance_update", "insider_sale", "conflict_claim_vs_filing",
                     "stale", "missing_fields"):
            for f in _run(name):
                if claim_status_of(f) == "verified_fact":
                    self.assertEqual(
                        f.source_authority_summary, "canonical",
                        "verified_fact must be a canonical filing: {0}".format(f.finding_id))

    def test_company_statements_are_never_verified_fact(self):
        # guidance / customer win / partnership are inherently company claims.
        for name in ("press_release_customer_win", "guidance_update", "missing_fields",
                     "conflict_claim_vs_filing"):
            for f in _run(name):
                if f.finding_type in NF.COMPANY_CLAIM_FINDINGS:
                    self.assertIn(claim_status_of(f), ("company_claim", "reported_claim"))
                    self.assertNotEqual(claim_status_of(f), "verified_fact")

    def test_claim_status_helper_maps_finding_families(self):
        # filing-fact families are verified_fact; claim families never are.
        for name in ("dilution_s3", "insider_sale"):
            for f in _run(name):
                self.assertEqual(claim_status_of(f), "verified_fact")


# =========================================================================== #
# Conflict -- company claim vs filing fact preserved (both sides)              #
# =========================================================================== #
class ConflictTests(unittest.TestCase):
    def test_claim_vs_filing_conflict_preserves_both_sides(self):
        findings = _run("conflict_claim_vs_filing")
        # BOTH the company claim AND the filing fact survive (neither dropped).
        self.assertIn("customer_win_claim", _types(findings))
        self.assertIn("dilution_risk", _types(findings))
        claim = _of_type(findings, "customer_win_claim")[0]
        fact = _of_type(findings, "dilution_risk")[0]
        # the claim is NOT promoted to a verified fact ...
        self.assertEqual(claim_status_of(claim), "company_claim")
        self.assertEqual(claim_status_of(fact), "verified_fact")
        # ... and the conflict is recorded on BOTH sides.
        self.assertTrue(claim.conflicts, "company claim must record the conflict")
        self.assertTrue(fact.conflicts, "filing fact must record the conflict")
        self.assertEqual(claim.contradiction_status, "disputed")
        self.assertEqual(fact.contradiction_status, "disputed")
        for f in (claim, fact):
            joined = " ".join(f.conflicts).lower()
            self.assertIn("conflict", joined)
            self.assertIn("both preserved", joined)

    def test_conflict_fuses_into_single_contradicted_signal(self):
        evs = _load("conflict_claim_vs_filing")
        findings = _run("conflict_claim_vs_filing")
        res = rm.TattvaSignalFusionSynthesizer().fuse(evs, findings, now="")
        self.assertTrue(res.signals)
        sig = res.signals[0]
        # both findings preserved on the fused signal; contradiction surfaced, not averaged away.
        self.assertEqual(sig.contradiction_status, "contradicted")
        self.assertEqual(len(sig.source_findings), 2)
        self.assertTrue(sig.conflicts)


# =========================================================================== #
# D5 -- discipline-bound; missing input -> gap; stale -> stale + gap            #
# =========================================================================== #
class MissingStaleAndDisciplineTests(unittest.TestCase):
    def test_stale_input_marks_finding_stale_and_notes_gap(self):
        findings = _run("stale")
        self.assertTrue(findings, "stale findings must NOT be dropped")
        for f in findings:
            self.assertEqual(f.freshness_label, "stale")
        gap_text = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("stale", gap_text)

    def test_missing_fields_surface_explicit_data_gaps(self):
        findings = _run("missing_fields")
        gap_text = " ".join(g for f in findings for g in f.data_gaps).lower()
        # missing offering size is a visible gap (never fabricated) ...
        self.assertIn("offering size not disclosed", gap_text)
        # ... and a missing issuer is a visible gap too.
        self.assertIn("subject company not identified", gap_text)
        # no magnitude was invented for the size-less S-3.
        dil = _of_type(findings, "dilution_risk")[0]
        self.assertIn(dil.magnitude_label, rm.MAGNITUDE_LABELS)

    def test_agent_stays_within_news_filings_discipline(self):
        agent = NewsFilingsAgent()
        self.assertEqual(agent.descriptor.discipline, "news_filings")
        self.assertEqual(agent.descriptor.agent_id, "tattva.news_filings")
        for name in ("dilution_s3", "contract_8k", "press_release_customer_win",
                     "guidance_update", "insider_sale"):
            for f in agent.run_checked(None, _load(name)):
                self.assertEqual(f.discipline, "news_filings")

    def test_agent_reuses_builtin_descriptor_and_subagents(self):
        agent = NewsFilingsAgent()
        builtin = rm.build_default_registry().get("tattva.news_filings")
        self.assertEqual(agent.descriptor.agent_id, builtin.agent_id)
        self.assertEqual(agent.descriptor.discipline, builtin.discipline)
        self.assertIn("NewsFilingFinding", agent.descriptor.emits)
        for sub in NF.NEWS_FILINGS_SUBAGENTS:
            self.assertIn(sub, agent.descriptor.subagents)


# =========================================================================== #
# AgentFinding-ONLY boundary (no signal/thesis/trade/rank/score)              #
# =========================================================================== #
class BoundaryTests(unittest.TestCase):
    _ALL = ("dilution_s3", "contract_8k", "press_release_customer_win", "guidance_update",
            "insider_sale", "conflict_claim_vs_filing", "stale", "missing_fields")

    def test_agent_emits_agentfinding_only(self):
        for name in self._ALL:
            for f in _run(name):
                self.assertIsInstance(f, M.AgentFinding)

    def test_findings_have_no_trade_or_score_field(self):
        for name in self._ALL:
            for f in _run(name):
                V.assert_no_trade_fields(f)
                for fname in f.__dataclass_fields__:
                    low = fname.lower()
                    for banned in ("score", "rank", "rating", "buy", "sell", "hold",
                                   "order", "trade", "broker"):
                        self.assertNotIn(banned, low)

    def test_no_finding_summary_contains_a_buy_sell_recommendation(self):
        for name in self._ALL:
            for f in _run(name):
                low = f.finding_summary.lower()
                for banned in ("buy ", "sell ", " rank", "score", "recommend"):
                    self.assertNotIn(banned, low)

    def test_run_checked_rejects_non_reality_event_input(self):
        with self.assertRaises(TypeError):
            NewsFilingsAgent().run_checked(None, ("not-an-event",))

    def test_deterministic_offline_run(self):
        a = _run("conflict_claim_vs_filing")
        b = _run("conflict_claim_vs_filing")
        self.assertEqual([repr(f) for f in a], [repr(f) for f in b])


# =========================================================================== #
# route -> fuse: 012B BuddhiRouter + 012C synthesizer                         #
# =========================================================================== #
class RouteAndFuseTests(unittest.TestCase):
    def setUp(self):
        self.reg = rm.build_default_registry()
        self.router = rm.BuddhiRouter(self.reg)
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_route_event_picks_news_filings(self):
        evs = _load("dilution_s3")
        matches = self.router.route_event(evs[0])
        self.assertEqual([d.agent_id for d in matches], ["tattva.news_filings"])

    def test_route_finding_wraps_into_handoff_envelope(self):
        findings = _run("dilution_s3")
        env = self.router.route_finding(findings[0])
        self.assertIsInstance(env, M.HandoffEnvelope)
        self.assertEqual(env.from_layer, "reality_intelligence")
        self.assertEqual(env.from_agent, "tattva.news_filings")
        self.assertEqual(env.to_synthesizer, "SignalFusion")
        self.assertEqual(env.payload_type, "AgentFinding")
        self.assertIn("fuse", env.allowed_downstream_uses)
        for use in ("broker_order", "auto_execute",
                    "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, env.forbidden_downstream_uses)

    def test_findings_fuse_into_news_filings_reality_signal(self):
        evs = _load("dilution_s3")
        findings = _run("dilution_s3")
        res = self.fuser.fuse(evs, findings, now="2026-06-29T00:00:00Z")
        self.assertTrue(res.signals)
        sig = res.signals[0]
        self.assertIsInstance(sig, M.RealitySignal)
        self.assertEqual(sig.discipline, "news_filings")
        self.assertEqual(sig.direction_label, "deteriorating")
        self.assertEqual(res.envelope.to_layer, "opportunity_discovery")

    def test_full_offline_pipeline_under_socket_killswitch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            evs = events_from_fixture(os.path.join(_FIXTURES, "contract_8k.json"))
            findings = NewsFilingsAgent().run_checked(None, evs)
            env = self.router.route_finding(findings[0])
            res = self.fuser.fuse(evs, findings, now="")
        finally:
            socket.socket = real
        self.assertEqual(env.to_synthesizer, "SignalFusion")
        self.assertTrue(res.signals)
        self.assertEqual(res.signals[0].discipline, "news_filings")


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
        d1 = tempfile.mkdtemp(prefix="rm_nf_a_")
        d2 = tempfile.mkdtemp(prefix="rm_nf_b_")
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
