"""IMPLEMENTATION-021B -- Financial Inflection sensor agent (SEC filing facts + local snapshots).

The one clearly-buildable deferred Tattva sensor, unlocked after SEC shadow validation
(020H/020I). This suite runs entirely OFFLINE against small deterministic JSON fixtures under
``tests/fixtures/reality_mesh/financial_inflection/`` -- no network, no live EDGAR/FMP fetch, no
scheduler, no broker. It proves the 021B invariants the gate enforces:

* SOURCE CONTRACT -- a 020B SEC filing EVENT (S-3 dilution / 8-K Item 2.02 guidance / Form 4
  insider) is CANONICAL + ``verified_fact`` + higher confidence; a LOCAL fundamental snapshot is
  ``company_claim`` (IR -> primary) or ``reported_claim`` (provider -> convenience) + lower
  confidence, marked not-verified.
* AUTHORITY LADDER (sacred) -- SEC canonical; IR company_claim; a provider ``provider_reported``
  (convenience) NEVER outranks a canonical SEC filing; a snapshot is NEVER canonical and NEVER a
  verified fact (no laundering).
* SOCIAL DISCIPLINE -- an X/social / rumor input NEVER drives a financial inflection: it is
  EXCLUDED (a non-verified ``financial_read_incomplete`` gap) -- never a ``verified_fact``, never
  a critical production-action.
* HONEST GAPS -- an ABSENT financial input is an explicit VISIBLE gap, never a fabricated number;
  a stale input is marked stale + a gap, never dropped.
* DQ + freshness -- the new findings pass through the 013E DataQualityGateRunner (the gate SEES
  them) and every finding carries a freshness label.
* ADDITIVE / OPT-IN -- the sensor gates on its own events; the default + demo pulse output stays
  byte-identical (the bundled fixtures trigger it NOT at all).
* route -> fuse -- a finding routes through the BuddhiRouter and fuses into a
  RealitySignal(financial_inflection).
* REGISTRY -- financial_inflection is now IMPLEMENTED (a backing agent registers + resolves).
* guardrails -- AgentFinding-only; no buy/sell/score/rank field; no net/scheduler/broker import +
  no ``def *score`` / ``*rank`` in the new module (AST); no secret; whole run offline under a
  socket kill-switch.
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
from reality_mesh import labels as L
from reality_mesh import models as M
from reality_mesh.agents import AgentDescriptor
from reality_mesh.gates import DataQualityGateRunner
from reality_mesh.sensors import (
    FinancialInflectionAgent,
    FINANCIAL_INFLECTION_FILING_EVENT_TYPES,
    FILING_FACT_INFLECTIONS,
    SNAPSHOT_INFLECTIONS,
    claim_status_of,
    events_from_fixture,
    has_financial_inflection_events,
)
from reality_mesh.sensors import financial_inflection as FI

_FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "reality_mesh", "financial_inflection")
_MODULE = os.path.join(_SRC, "reality_mesh", "sensors", "financial_inflection.py")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _load(*names):
    evs = []
    for name in names:
        evs.extend(events_from_fixture(os.path.join(_FIXTURES, name + ".json")))
    return tuple(evs)


def _run(*names):
    return FinancialInflectionAgent().run_checked(None, _load(*names))


def _types(findings):
    return {f.finding_type for f in findings}


def _of_type(findings, ftype):
    return [f for f in findings if f.finding_type == ftype]


# =========================================================================== #
# SEC filing FACTS -- canonical + verified_fact + higher confidence            #
# =========================================================================== #
class FilingFactTests(unittest.TestCase):
    def test_s3_filing_emits_canonical_verified_dilution_inflection(self):
        findings = _run("dilution_s3")
        dils = _of_type(findings, "dilution_inflection")
        self.assertEqual(len(dils), 1)
        f = dils[0]
        self.assertEqual(f.direction_label, "deteriorating")
        self.assertEqual(f.source_authority_summary, "canonical")
        self.assertEqual(claim_status_of(f), "verified_fact")
        self.assertEqual(f.confidence_label, "high")  # filing fact -> higher confidence
        # review_required-eligible: up to elevated urgency, never immediate/critical.
        self.assertEqual(f.urgency_label, "elevated")

    def test_8k_item202_cut_emits_deteriorating_guidance_inflection(self):
        findings = _run("guidance_8k_cut")
        g = _of_type(findings, "guidance_inflection")
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0].direction_label, "deteriorating")
        self.assertEqual(g[0].source_authority_summary, "canonical")
        self.assertEqual(claim_status_of(g[0]), "verified_fact")

    def test_form4_emits_canonical_insider_inflection(self):
        findings = _run("insider_form4")
        ins = _of_type(findings, "insider_inflection")
        self.assertEqual(len(ins), 1)
        self.assertEqual(ins[0].source_authority_summary, "canonical")
        self.assertEqual(claim_status_of(ins[0]), "verified_fact")

    def test_filing_fact_types_are_the_canonical_set(self):
        # Every filing-event type maps to a filing-fact finding type (not a snapshot type).
        for _sub, ftype in FINANCIAL_INFLECTION_FILING_EVENT_TYPES.values():
            self.assertIn(ftype, FILING_FACT_INFLECTIONS)


# =========================================================================== #
# LOCAL snapshots -- company_claim / provider, lower confidence, not-verified   #
# =========================================================================== #
class SnapshotTests(unittest.TestCase):
    def test_company_ir_snapshot_is_company_claim_primary_not_verified(self):
        findings = _run("snapshot_company_ir")
        self.assertIn("revenue_acceleration", _types(findings))
        for f in findings:
            self.assertEqual(f.source_authority_summary, "primary")
            self.assertEqual(claim_status_of(f), "company_claim")
            self.assertNotEqual(claim_status_of(f), "verified_fact")
            # lower confidence + explicitly not independently verified.
            self.assertIn(f.confidence_label, ("very_low", "low"))
            self.assertIn("not independently verified", f.finding_summary)

    def test_provider_snapshot_is_reported_claim_convenience(self):
        findings = _run("snapshot_provider")
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f.source_authority_summary, "convenience")
            self.assertEqual(claim_status_of(f), "reported_claim")
            self.assertNotEqual(claim_status_of(f), "verified_fact")

    def test_revenue_acceleration_reads_accelerating_direction(self):
        f = _of_type(_run("snapshot_company_ir"), "revenue_acceleration")[0]
        self.assertEqual(f.direction_label, "accelerating")

    def test_snapshot_types_never_verified_fact(self):
        findings = _run("snapshot_company_ir", "snapshot_provider")
        for f in findings:
            if f.finding_type in SNAPSHOT_INFLECTIONS:
                self.assertNotEqual(claim_status_of(f), "verified_fact")
                self.assertNotEqual(f.source_authority_summary, "canonical")


# =========================================================================== #
# AUTHORITY LADDER -- provider NEVER outranks SEC; no laundering                #
# =========================================================================== #
class AuthorityLadderTests(unittest.TestCase):
    def test_provider_never_outranks_sec_filing(self):
        # SEC dilution fact + provider snapshot for the SAME company in one read.
        findings = _run("dilution_s3", "snapshot_provider")
        sec = [f for f in findings if f.finding_type == "dilution_inflection"][0]
        prov = [f for f in findings if f.finding_type in SNAPSHOT_INFLECTIONS]
        self.assertTrue(prov)
        self.assertEqual(sec.source_authority_summary, "canonical")
        for f in prov:
            self.assertEqual(f.source_authority_summary, "convenience")
            # the sacred ladder: convenience ranks strictly below canonical.
            self.assertLess(
                L.authority_rank(f.source_authority_summary),
                L.authority_rank(sec.source_authority_summary))
        # neither side is promoted: the SEC fact stays verified_fact, the provider read stays a claim.
        self.assertEqual(claim_status_of(sec), "verified_fact")
        for f in prov:
            self.assertEqual(claim_status_of(f), "reported_claim")

    def test_sec_is_canonical_ir_is_company_claim_provider_is_reported(self):
        sec = _of_type(_run("dilution_s3"), "dilution_inflection")[0]
        ir = _run("snapshot_company_ir")[0]
        prov = _run("snapshot_provider")[0]
        self.assertEqual((sec.source_authority_summary, claim_status_of(sec)),
                         ("canonical", "verified_fact"))
        self.assertEqual((ir.source_authority_summary, claim_status_of(ir)),
                         ("primary", "company_claim"))
        self.assertEqual((prov.source_authority_summary, claim_status_of(prov)),
                         ("convenience", "reported_claim"))

    def test_a_snapshot_marked_canonical_is_capped_below_canonical(self):
        # A local snapshot event that (wrongly) claims canonical authority is NEVER accepted as
        # canonical by this sensor -- it is capped to primary and never a verified fact.
        ev = M.RealityEvent(
            event_id="fi.snap.bad", source_id="ir", source_type="company_ir",
            source_authority="canonical", claim_status="company_claim",
            discipline="financial_inflection", event_type="fundamental_snapshot",
            affected_companies=("IREN",), observed_fact="fundamentals",
            numeric_values=(("revenue_growth_delta_pct", 9, "pp"),),
            source_refs=("ir:IREN",), evidence_refs=("ex.ir.iren",),
            confidence_label="moderate", freshness_label="recent")
        findings = FinancialInflectionAgent().run_checked(None, (ev,))
        for f in findings:
            self.assertNotEqual(f.source_authority_summary, "canonical")
            self.assertNotEqual(claim_status_of(f), "verified_fact")


# =========================================================================== #
# SOCIAL / RUMOR -- excluded; never verified_fact; never critical              #
# =========================================================================== #
class SocialExclusionTests(unittest.TestCase):
    def test_social_input_never_drives_a_financial_inflection(self):
        findings = _run("snapshot_social_rumor")
        # the ONLY finding is the explicit exclusion gap -- never a real inflection.
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f.finding_type, "financial_read_incomplete")
            self.assertNotIn(f.finding_type, SNAPSHOT_INFLECTIONS)
            self.assertNotIn(f.finding_type, FILING_FACT_INFLECTIONS)

    def test_social_input_never_a_verified_fact(self):
        for f in _run("snapshot_social_rumor"):
            self.assertNotEqual(claim_status_of(f), "verified_fact")
            self.assertNotIn(f.source_authority_summary, ("canonical", "primary"))

    def test_social_input_never_reaches_a_critical_severity(self):
        # urgency stays a low watch -- never an elevated/high/immediate production-action.
        for f in _run("snapshot_social_rumor"):
            self.assertIn(f.urgency_label, ("none", "low", "watch"))

    def test_social_exclusion_is_visible_not_silent(self):
        gaps = " ".join(g for f in _run("snapshot_social_rumor") for g in f.data_gaps).lower()
        self.assertIn("excluded", gaps)
        self.assertIn("social", gaps)

    def test_social_finding_passes_the_dq_social_gate(self):
        # The DQ social-weak gate must NOT fail (no rumor laundered into a verified_fact).
        res = DataQualityGateRunner().check_social_weak_signal(_run("snapshot_social_rumor"))
        self.assertNotEqual(res.status, "fail")


# =========================================================================== #
# HONEST GAPS -- absent input -> visible gap, never a fabricated number         #
# =========================================================================== #
class GapAndStaleTests(unittest.TestCase):
    def test_absent_metric_surfaces_a_visible_gap_not_a_number(self):
        findings = _run("snapshot_absent_metric")
        self.assertEqual(_types(findings), {"financial_read_incomplete"})
        f = findings[0]
        gap = " ".join(f.data_gaps).lower()
        self.assertIn("no readable inflection metric", gap)
        self.assertIn("never a fabricated number", gap)
        # NO fabricated inflection: the incomplete read carries a neutral direction (no verdict).
        self.assertEqual(f.direction_label, "neutral")

    def test_no_snapshot_inflection_fabricated_when_metric_absent(self):
        findings = _run("snapshot_absent_metric")
        for f in findings:
            self.assertNotIn(f.finding_type, SNAPSHOT_INFLECTIONS)

    def test_stale_input_marked_stale_and_preserved(self):
        findings = _run("snapshot_stale")
        self.assertTrue(findings)
        self.assertTrue(any(f.freshness_label == "stale" for f in findings))
        gap = " ".join(g for f in findings for g in f.data_gaps).lower()
        self.assertIn("stale", gap)

    def test_every_finding_carries_a_freshness_label(self):
        findings = _run("dilution_s3", "snapshot_company_ir", "snapshot_provider")
        for f in findings:
            self.assertNotEqual(f.freshness_label, "")
            self.assertNotEqual(f.freshness_label, "missing")


# =========================================================================== #
# DQ gate + route/fuse                                                          #
# =========================================================================== #
class DataQualityAndRoutingTests(unittest.TestCase):
    def setUp(self):
        self.reg = rm.build_default_registry()
        self.router = rm.BuddhiRouter(self.reg)
        self.fuser = rm.TattvaSignalFusionSynthesizer()

    def test_dq_gate_sees_the_new_findings_and_they_pass(self):
        findings = _run("dilution_s3", "snapshot_company_ir", "snapshot_provider")
        results, overall = DataQualityGateRunner().run(findings=findings)
        self.assertTrue(results)
        # the gate SEES the findings and none fails -- honest, disciplined signals.
        self.assertEqual(overall, "healthy")

    def test_route_event_picks_financial_inflection_for_a_snapshot(self):
        evs = _load("snapshot_company_ir")
        matches = self.router.route_event(evs[0])
        self.assertEqual([d.agent_id for d in matches], ["tattva.financial_inflection"])

    def test_route_finding_wraps_into_handoff_envelope(self):
        f = _run("dilution_s3")[0]
        env = self.router.route_finding(f)
        self.assertIsInstance(env, M.HandoffEnvelope)
        self.assertEqual(env.from_agent, "tattva.financial_inflection")
        self.assertEqual(env.to_synthesizer, "SignalFusion")
        for use in ("broker_order", "auto_execute",
                    "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, env.forbidden_downstream_uses)

    def test_findings_fuse_into_financial_inflection_signal(self):
        evs = _load("dilution_s3")
        findings = _run("dilution_s3")
        res = self.fuser.fuse(evs, findings, now="2026-06-29T00:00:00Z")
        self.assertTrue(res.signals)
        self.assertEqual(res.signals[0].discipline, "financial_inflection")


# =========================================================================== #
# REGISTRY -- financial_inflection now IMPLEMENTED (backing agent resolves)     #
# =========================================================================== #
class RegistryTests(unittest.TestCase):
    def test_descriptor_discipline_is_financial_inflection(self):
        desc = rm.build_default_registry().get("tattva.financial_inflection")
        self.assertEqual(desc.discipline, "financial_inflection")
        self.assertEqual(FinancialInflectionAgent().descriptor.agent_id,
                         "tattva.financial_inflection")

    def test_registry_reports_financial_inflection_implemented(self):
        # descriptor-only -> implemented: a real backing agent now resolves for the descriptor,
        # and the descriptor it registers is the built-in tattva.financial_inflection contract.
        agent = FinancialInflectionAgent()
        self.assertEqual(agent.descriptor.agent_id, "tattva.financial_inflection")
        reg = rm.AgentRegistry()
        reg.register_agent(agent)
        resolved = reg.get_agent("tattva.financial_inflection")
        self.assertIsInstance(resolved, FinancialInflectionAgent)

    def test_sensor_is_wired_into_the_pulse(self):
        # implemented = wired: the sensor is one of the pulse's conditional sensor factories.
        from reality_mesh import pulse as P
        factories = [f for f, _gate in P._CONDITIONAL_SENSOR_AGENT_FACTORIES]
        self.assertIn(FinancialInflectionAgent, factories)

    def test_gate_function_matches_snapshot_and_filing_events(self):
        self.assertTrue(has_financial_inflection_events(_load("snapshot_company_ir")))
        self.assertTrue(has_financial_inflection_events(_load("dilution_s3")))
        self.assertFalse(has_financial_inflection_events(()))


# =========================================================================== #
# ADDITIVE / OPT-IN -- default + demo pulse byte-identical                      #
# =========================================================================== #
class AdditivePulseTests(unittest.TestCase):
    def test_financial_inflection_absent_from_default_pulse(self):
        from reality_mesh.pulse import run_pulse
        res = run_pulse("IREN,AAOI", "physical-ai", now="2026-06-29T00:00:00Z")
        disciplines = {r.discipline for r in res.agent_runs}
        self.assertNotIn("financial_inflection", disciplines)

    def test_default_pulse_byte_identical_run_to_run(self):
        from reality_mesh.pulse import run_pulse
        a = run_pulse("IREN,AAOI", "physical-ai", now="2026-06-29T00:00:00Z")
        b = run_pulse("IREN,AAOI", "physical-ai", now="2026-06-29T00:00:00Z")
        self.assertEqual([f.finding_id for f in a.findings],
                         [f.finding_id for f in b.findings])
        self.assertEqual([s.signal_id for s in a.signals],
                         [s.signal_id for s in b.signals])
        self.assertEqual(a.data_gaps, b.data_gaps)

    def test_sensor_joins_only_when_its_events_are_present(self):
        # Opt-in: the sensor runs additively when a financial_inflection fixture dir is supplied.
        from reality_mesh.pulse import run_pulse
        res = run_pulse("IREN,AAOI", "physical-ai", now="2026-06-29T00:00:00Z",
                        fixture_dir=_FIXTURES)
        disciplines = {r.discipline for r in res.agent_runs}
        self.assertIn("financial_inflection", disciplines)

    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_fi_a_")
        d2 = tempfile.mkdtemp(prefix="rm_fi_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))


# =========================================================================== #
# Boundary + guardrails -- AgentFinding-only, offline, AST, no secret           #
# =========================================================================== #
class BoundaryAndGuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "selenium", "scrapy", "lxml", "websocket", "websockets"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal"}

    def _module_source(self):
        with open(_MODULE, encoding="utf-8") as fh:
            return fh.read()

    def test_agent_emits_agentfinding_only(self):
        for f in _run("dilution_s3", "snapshot_company_ir"):
            self.assertIsInstance(f, M.AgentFinding)

    def test_findings_have_no_trade_or_score_field(self):
        for f in _run("dilution_s3", "snapshot_company_ir", "snapshot_provider"):
            for field_name in vars(f):
                for banned in ("score", "rank", "rating", "buy", "sell", "hold",
                               "order", "broker", "target_price"):
                    self.assertNotIn(banned, field_name.lower())

    def test_agent_stays_within_financial_inflection_discipline(self):
        for f in _run("dilution_s3", "snapshot_company_ir", "guidance_8k_cut",
                      "insider_form4", "snapshot_provider"):
            self.assertEqual(f.discipline, "financial_inflection")

    def test_run_checked_rejects_non_reality_event_input(self):
        with self.assertRaises((TypeError, ValueError)):
            FinancialInflectionAgent().run_checked(None, ("not-an-event",))

    def test_module_imports_no_network_scheduler_or_broker(self):
        tree = ast.parse(self._module_source())
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.append((node.module or "").split(".")[0])
        for m in mods:
            self.assertNotIn(m, self._NET, "imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "imports forbidden {0}".format(m))

    def test_module_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._module_source())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, node.name)

    def test_module_has_no_broker_live_fetch_or_secret(self):
        blob = self._module_source().lower()
        for banned in ("place_order", "submit_order", "execute_trade", "schedule.every",
                       "cron", "broker.submit", "requests.get", "urlopen", "socket.socket",
                       "api_key", "secret", "password", "bearer "):
            self.assertNotIn(banned, blob, "banned token: {0}".format(banned))

    def test_full_offline_pipeline_under_socket_killswitch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            evs = _load("dilution_s3", "snapshot_provider")
            findings = FinancialInflectionAgent().run_checked(None, evs)
            reg = rm.build_default_registry()
            env = rm.BuddhiRouter(reg).route_finding(findings[0])
            res = rm.TattvaSignalFusionSynthesizer().fuse(evs, findings, now="")
        finally:
            socket.socket = real
        self.assertEqual(env.to_synthesizer, "SignalFusion")
        self.assertTrue(res.signals)
        self.assertEqual(res.signals[0].discipline, "financial_inflection")


if __name__ == "__main__":
    unittest.main()
