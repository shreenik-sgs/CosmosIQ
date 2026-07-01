"""Tests for the IMPLEMENTATION-009G evidence -> alpha end-to-end slice.

A deterministic, fixture-backed END-TO-END vertical slice that starts from the
evidence-ingestion layer (009E/F) and runs FORWARD through the EXISTING alpha
pipeline, proving that INGESTED evidence -- not hand-authored inputs -- drives the
whole reasoning chain:

    fixtures -> ingestion -> IntelligenceAssessment -> OpportunityHypothesis
    -> InvestmentThesis -> InvestmentAction -> PersonalizedAction
    -> ManualExecutionIntent -> ManualTradeTicket (preview) -> Cockpit.

The slice CALLS only existing constructors/runners; it adds no new alpha logic, no
new scoring, no formula changes. No network / live calls / keys / scheduler /
broker automation. Deterministic, stdlib-only, Python 3.9.
"""

from __future__ import annotations

import ast
import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from eios_core.canonical_objects import Observation

from runtime.evidence_alpha_slice_runner import (
    run_evidence_alpha_slice,
    EvidenceAlphaSliceResult,
)
from reality_intelligence.intelligence_assessment import (
    IntelligenceAssessment,
    generate_intelligence_assessment,
    FACTUAL_SOURCE_TYPES,
)
from genesis.opportunity_hypothesis import OpportunityHypothesis
from prometheus.investment_thesis import InvestmentThesis
from prometheus.investment_action import InvestmentAction
from personal_cio.personalized_action import PersonalizedAction
from execution_manual.manual_execution_intent import ManualExecutionIntent
from execution_manual.manual_trade_ticket import ManualTradeTicket
from infinite_canvas.cockpit import AlphaDecisionCockpitView

_FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "slice")
_RUNNER_MODULE = os.path.join(_SRC, "runtime", "evidence_alpha_slice_runner.py")

_NOW = 1750000000.0
_PERIOD = "2026-03-31"
_SHARED_OHLCV_DATE = "2026-06-26"


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r") as fh:
        return json.load(fh)


def _kwargs(**overrides):
    kw = dict(
        subject="IREN",
        domain="ai-infrastructure",
        sec_submissions=_load("sec_submissions_iren.json"),
        sec_companyfacts=_load("sec_companyfacts_iren.json"),
        fmp_income_statement=_load("fmp_income_statement_iren.json"),
        fmp_profile=_load("fmp_profile_iren.json"),
        fmp_ohlcv=_load("fmp_ohlcv_iren.json"),
        fmp_news=_load("fmp_news_iren.json"),
        fmp_ownership=_load("fmp_ownership_iren.json"),
        yf_history=_load("yf_history_iren.json"),
        yf_quote=_load("yf_quote_iren.json"),
        now=_NOW,
        yf_quote_as_of=_PERIOD,
    )
    kw.update(overrides)
    return kw


def _run(**overrides):
    return run_evidence_alpha_slice(**_kwargs(**overrides))


class EndToEndChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _run(render_html=True)

    # --- shape / determinism ------------------------------------------------
    def test_result_is_the_frozen_slice_result(self):
        self.assertIsInstance(self.r, EvidenceAlphaSliceResult)
        with self.assertRaises(Exception):
            self.r.subject = "OTHER"

    def test_deterministic_two_runs_identical_ids(self):
        a, b = _run(), _run()
        for attr in ("intelligence_assessment", "opportunity_hypothesis",
                     "investment_thesis", "investment_action",
                     "personalized_action", "manual_execution_intent",
                     "manual_trade_ticket"):
            self.assertEqual(getattr(a, attr).id, getattr(b, attr).id,
                             "non-deterministic id for {0}".format(attr))
        # observation ids stable too.
        self.assertEqual([o.id for o in a.observations], [o.id for o in b.observations])

    # --- full chain uses EXISTING constructor types -------------------------
    def test_full_chain_produced_by_existing_constructors(self):
        r = self.r
        self.assertIsInstance(r.intelligence_assessment, IntelligenceAssessment)
        self.assertIsInstance(r.opportunity_hypothesis, OpportunityHypothesis)
        self.assertIsInstance(r.investment_thesis, InvestmentThesis)
        self.assertIsInstance(r.investment_action, InvestmentAction)
        self.assertIsInstance(r.personalized_action, PersonalizedAction)
        self.assertIsInstance(r.manual_execution_intent, ManualExecutionIntent)
        self.assertIsInstance(r.manual_trade_ticket, ManualTradeTicket)
        self.assertIsInstance(r.cockpit_view, AlphaDecisionCockpitView)
        for o in r.observations:
            self.assertIsInstance(o, Observation)

    def test_chain_bindings_link_each_stage(self):
        r = self.r
        # IA -> OH
        self.assertIn(r.intelligence_assessment.id,
                      set(r.opportunity_hypothesis.triggering_assessment_ids))
        # OH -> Thesis
        self.assertEqual(r.investment_thesis.opportunity_id, r.opportunity_hypothesis.id)
        # Thesis -> Action
        self.assertEqual(r.investment_action.source_thesis_id, r.investment_thesis.id)
        # Action -> PersonalizedAction
        self.assertEqual(r.personalized_action.source_action_id, r.investment_action.id)
        # PersonalizedAction -> Intent
        self.assertEqual(r.manual_execution_intent.source_personalized_action_id,
                         r.personalized_action.id)
        # Intent -> Ticket
        self.assertEqual(r.manual_trade_ticket.cio_decision_record_id,
                         r.personalized_action.id)

    # --- explicit user size required ----------------------------------------
    def test_manual_intent_requires_explicit_user_size(self):
        with self.assertRaises(ValueError):
            _run(user_selected_allocation_amount=0.0)
        with self.assertRaises(ValueError):
            _run(user_selected_allocation_amount=-100.0)

    def test_user_size_flows_to_intent(self):
        r = _run(user_selected_allocation_amount=3500.0)
        self.assertEqual(r.manual_execution_intent.user_selected_allocation_amount, 3500.0)

    # --- ticket is preview-only, no broker automation -----------------------
    def test_ticket_is_preview_only_no_broker_automation(self):
        t = self.r.manual_trade_ticket
        self.assertEqual(t.state, "previewed")
        self.assertIsNone(t.broker_order_id)
        b = self.r.boundary_audit_summary
        self.assertTrue(b["manual_execution_only"])
        self.assertEqual(b["ticket_state"], "previewed")
        self.assertIsNone(b["broker_order_id"])
        self.assertTrue(b["no_broker_automation"])
        self.assertTrue(b["factual_partition_preserved"])
        self.assertEqual(b["source_hierarchy"], "SEC>FMP>yf")
        self.assertIsNone(b["stops_before"])

    # --- cockpit assembles from the evidence-driven chain -------------------
    def test_cockpit_assembles_from_chain(self):
        c = self.r.cockpit_view
        self.assertEqual(c.subject, self.r.investment_thesis.security_or_instrument_mapping)
        self.assertEqual(c.subject, self.r.subject)
        self.assertGreater(len(c.provenance_chain), 0)
        # all nine panels present (personalized + manual supplied).
        self.assertEqual(len(c.panels), 9)


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _run(render_html=True)

    def test_html_produced_when_requested(self):
        self.assertIsInstance(self.r.rendered_html, str)
        self.assertGreater(len(self.r.rendered_html), 0)

    def test_html_none_when_not_requested(self):
        r = _run(render_html=False)
        self.assertIsNone(r.rendered_html)

    def test_html_has_no_action_affordance(self):
        low = self.r.rendered_html.lower()
        for token in ("<button", "<form", "onclick", "submit", "<script",
                      "place order"):
            self.assertNotIn(token, low)
        self.assertNotIn("buy", low)
        self.assertNotIn("sell", low)


class SourceHierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _run()
        cls.ing = cls.r.ingestion_result

    def test_all_three_sources_contribute(self):
        a = self.ing.authority_summary
        self.assertGreater(a.get("canonical", 0), 0)    # SEC
        self.assertGreater(a.get("convenience", 0), 0)  # FMP
        self.assertGreater(a.get("fallback", 0), 0)     # yfinance
        cov = self.ing.source_coverage_summary
        for name in ("SEC EDGAR", "FMP", "yfinance"):
            self.assertIn(name, cov)
            self.assertGreater(cov[name]["records"], 0)
        self.assertGreater(cov["yfinance"]["observations"], 0)
        self.assertGreater(cov["SEC EDGAR"]["observations"], 0)
        self.assertGreater(cov["FMP"]["overridden"], 0)

    def test_sec_revenue_beats_fmp(self):
        key = ("IREN", "financial_fact", "revenue", _PERIOD, "USD")
        self.assertEqual(self.ing.resolved_facts[key], 120000000)  # SEC, not FMP
        rev_obs = [o for o in self.r.observations
                   if o.content.get("financial_metric") == "revenue"]
        self.assertEqual(len(rev_obs), 1)
        self.assertEqual(rev_obs[0].content.get("source_authority"), "canonical")

    def test_sec_shares_beat_fmp_and_yf(self):
        key = ("IREN", "financial_fact", "shares_outstanding", _PERIOD, "shares")
        self.assertEqual(self.ing.resolved_facts[key], 210000000)  # SEC canonical
        deferred_types = {rec.normalized_type for rec in self.r.deferred_records}
        self.assertIn("fmp_financial_shares_outstanding", deferred_types)
        self.assertIn("yf_quote_shares_outstanding", deferred_types)

    def test_fmp_ohlcv_beats_yf(self):
        key = ("IREN", "market_data", _SHARED_OHLCV_DATE, "close")
        self.assertEqual(self.ing.resolved_facts[key], 21.10)  # FMP convenience

    def test_yfinance_fills_only_true_gaps(self):
        gap_key = ("IREN", "market_data", "2026-06-24", "close")
        self.assertEqual(self.ing.resolved_facts[gap_key], 19.45)  # yf-only date

    def test_overridden_facts_visible_in_data_gaps_and_result(self):
        kinds = {g[0] for g in self.r.data_gaps}
        self.assertIn("overridden_financial_fact", kinds)
        overridden = self.r.provenance_chain["overridden_facts"]
        self.assertGreater(len(overridden), 0)
        for o in overridden:
            self.assertIn("overridden", o["reason"])

    def test_conflict_warnings_visible_in_result(self):
        self.assertGreater(len(self.r.conflict_warnings), 0)
        rev = [w for w in self.r.conflict_warnings if "financial_fact/revenue" in w]
        self.assertTrue(rev)
        self.assertIn("SEC EDGAR", rev[0])
        self.assertIn("FMP", rev[0])


class FactualVsSignalTests(unittest.TestCase):
    """Factual observations add grounding, never signal (009F discipline preserved)."""

    @classmethod
    def setUpClass(cls):
        cls.r = _run()

    def test_factual_observations_do_not_change_the_assessment(self):
        # Re-derive an IA over ONLY the signal-bearing observations (drop factual
        # OHLCV/profile/ownership/quote/share-count) using the EXISTING Tattva layer,
        # and prove the ingested IA over ALL observations is identical in signals,
        # direction, significance and confidence.
        obs_all = self.r.observations
        signal_obs = tuple(
            o for o in obs_all
            if o.content.get("source_type") not in FACTUAL_SOURCE_TYPES
        )
        self.assertLess(len(signal_obs), len(obs_all), "no factual obs present to test")
        ia_signal_only = generate_intelligence_assessment(
            signal_obs, domain="ai-infrastructure", actor="x", now=_NOW)
        ia_all = self.r.intelligence_assessment
        self.assertEqual(
            [(s.signal_type, s.direction) for s in ia_all.signals],
            [(s.signal_type, s.direction) for s in ia_signal_only.signals],
        )
        self.assertEqual(ia_all.direction, ia_signal_only.direction)
        self.assertEqual(ia_all.significance, ia_signal_only.significance)
        self.assertEqual(ia_all.confidence, ia_signal_only.confidence)

    def test_factual_observations_are_partitioned_not_signals(self):
        ia = self.r.intelligence_assessment
        # every factual observation is recorded as grounding-only, never a signal.
        factual_ids = {o.id for o in self.r.observations
                       if o.content.get("source_type") in FACTUAL_SOURCE_TYPES}
        self.assertTrue(factual_ids)
        self.assertEqual(set(ia.factual_observation_ids), factual_ids)

    def test_factual_only_input_creates_no_opportunity(self):
        # OHLCV-only ingestion -> factual observations, a signalless IA, and NO
        # opportunity hypothesis / thesis (facts alone do not create alpha).
        r = _run(
            sec_submissions=None, sec_companyfacts=None,
            fmp_income_statement=None, fmp_profile=None, fmp_news=None,
            fmp_ownership=None, yf_history=None, yf_quote=None,
        )
        self.assertIsNone(r.opportunity_hypothesis)
        self.assertIsNone(r.investment_thesis)
        self.assertIsNone(r.manual_trade_ticket)
        self.assertEqual(r.boundary_audit_summary["stops_before"], "opportunity_hypothesis")
        ia = r.intelligence_assessment
        if ia is not None:
            self.assertEqual(len(ia.signals), 0)

    def test_empty_input_stops_cleanly(self):
        r = run_evidence_alpha_slice(subject="IREN", domain="ai-infrastructure", now=_NOW)
        self.assertIsNone(r.intelligence_assessment)
        self.assertIsNone(r.opportunity_hypothesis)
        self.assertEqual(r.boundary_audit_summary["stops_before"], "opportunity_hypothesis")


class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _run(render_html=True)

    def test_source_traces_carry_authority_class_provider(self):
        traces = self.r.provenance_chain["source_traces"]
        self.assertGreater(len(traces), 0)
        seen_providers = set()
        for t in traces:
            self.assertTrue(t.source_name)
            self.assertTrue(t.source_authority)
            self.assertTrue(t.source_class)
            self.assertTrue(t.source_provider)
            self.assertTrue(t.raw_record_ref.object_id)
            self.assertEqual(t.raw_record_ref.kind, "RawEvidenceRecord")
            seen_providers.add(t.source_name)
        # SEC + FMP + yfinance all show up in the source-fixture -> observation trace.
        for name in ("SEC EDGAR", "FMP", "yfinance"):
            self.assertIn(name, seen_providers)

    def test_downstream_chain_traces_ia_to_ticket(self):
        stages = [d["stage"] for d in self.r.provenance_chain["downstream"]]
        self.assertEqual(stages, [
            "IntelligenceAssessment->OpportunityHypothesis",
            "OpportunityHypothesis->InvestmentThesis",
            "InvestmentThesis->InvestmentAction",
            "InvestmentAction->PersonalizedAction",
            "PersonalizedAction->ManualExecutionIntent",
            "ManualExecutionIntent->ManualTradeTicket",
        ])
        # every downstream link is bound to a real upstream id.
        for d in self.r.provenance_chain["downstream"]:
            self.assertTrue(all(d["bound_to"]))

    def test_full_source_fixture_to_cockpit_trace(self):
        # source (SEC/FMP/yf) -> raw -> normalized -> Observation -> IA is provable,
        r = self.r
        trace_obs_ids = {t.observation_id for t in r.provenance_chain["source_traces"]}
        self.assertEqual(trace_obs_ids, {o.id for o in r.observations})
        ia = r.intelligence_assessment
        # IA binds exactly the produced Observations.
        bound = {ref.object_id for ref in ia.provenance.sources}
        self.assertEqual(bound, {o.id for o in r.observations})
        # ... and the cockpit's own provenance chain is present + non-empty.
        self.assertGreater(len(r.provenance_chain["cockpit"]), 0)
        self.assertGreater(len(r.cockpit_view.provenance_chain), 0)


class StaticGuardTests(unittest.TestCase):
    """AST / grep guards: no network, no secrets, no scheduler; existing logic only."""

    @classmethod
    def setUpClass(cls):
        with open(_RUNNER_MODULE, "r") as fh:
            cls.src = fh.read()
        cls.tree = ast.parse(cls.src)

    def test_no_network_scheduler_or_process_imports(self):
        banned = {"requests", "urllib", "http", "socket", "aiohttp", "httpx",
                  "os", "subprocess", "sched", "asyncio", "threading",
                  "multiprocessing", "concurrent"}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name.split(".")[0], banned)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], banned)

    def test_no_secret_or_key_access(self):
        self.assertNotIn("os.environ", self.src)
        self.assertNotIn("getenv", self.src.lower())
        banned_ids = ("api_key", "apikey", "secret", "token", "password", "access_key")
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "environ")
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        for b in banned_ids:
                            self.assertNotIn(b, tgt.id.lower())

    def test_no_broker_place_fill_reconcile_calls(self):
        # The slice stops at ticket PREVIEW: it must not call the place/fill/
        # reconcile/confirm actuation functions.
        banned_calls = {"place_order", "make_fill", "reconcile", "confirm",
                        "mark_recorded", "mark_reconciled", "re_preview"}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                self.assertNotIn(name, banned_calls,
                                 "slice calls actuation function {0}".format(name))


if __name__ == "__main__":
    unittest.main()
