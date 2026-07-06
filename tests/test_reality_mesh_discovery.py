"""IMPLEMENTATION-021E -- the Candidate Discovery Engine (reality_mesh layer).

INFRASTRUCTURE ONLY. Runs entirely OFFLINE -- no network, no scheduler, no broker, no live
endpoint. Proves the 021E discipline: the Theme Graph (021D-graph) + live-source evidence flag
companies WORTHY OF DILIGENCE as a :class:`DiscoveryCandidate` -- which is NOT a recommendation,
NOT a buy, and confers NO capital standing.

* company graph membership ALONE creates NO CapitalCandidate (states stay monitor_only /
  blocked_insufficient_evidence; the publication log stays empty);
* an SEC filing ALONE / an FMP row ALONE creates NO recommendation (a DiscoveryCandidate at most,
  no CapitalCandidate, no ``recommendation`` field);
* a DiscoveryCandidate can be ``monitor_only`` or a ``blocked_*`` state WITH an exact reason;
* ``trigger_diligence_input`` records a diligence INPUT and does NOT publish -- CapitalCandidate
  publication STILL requires the full 020A gate (provenance + healthy DQ);
* a social / rumor-only or DQ-failed basis can NEVER be a ``diligence_candidate``;
* NO hidden score / rank field; NO buy / sell / order / submit control / field; deterministic;
  offline under a socket kill-switch; AST clean; the demo + default pulse stay byte-identical.
"""

from __future__ import annotations

import ast
import os
import re
import socket
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh.capital_candidate import publish_candidates_for_run
from reality_mesh.discovery import (
    BLOCKED_DISCOVERY_STATES,
    DISCOVERY_STATES,
    FACTOR_FLAGS,
    DiscoveryCandidate,
    discover_candidates,
    discovery_id_for,
    trigger_diligence_input,
)
from reality_mesh.models import AgentFinding, RealityEvent, RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import RunStore, SignalStore
from reality_mesh.theme_graph import RiskNode, build_seed_theme_graph

_DISCOVERY_PY = os.path.join(_SRC, "reality_mesh", "discovery.py")
_NOW = "2026-07-06T12:00:00Z"

# A canonical SEC financial-inflection filing event for a monitored graph ticker.
_SEC_EVENT = RealityEvent(
    event_id="E-sec-1", timestamp=_NOW, source_id="src.sec", source_type="sec_filing",
    source_authority="canonical", claim_status="verified_fact", discipline="news_filings",
    event_type="sec_8-k_results_of_operations", affected_companies=("NVDA",),
    source_refs=("sec:0001",), evidence_refs=("ex-sec-1",))

# A commercial-provider FMP snapshot row (convenience / reported_claim -- non-social).
_FMP_EVENT = RealityEvent(
    event_id="E-fmp-1", timestamp=_NOW, source_id="src.fmp", source_type="fmp_financial_data",
    source_authority="convenience", claim_status="reported_claim", discipline="financial_inflection",
    event_type="fmp_income_statement_snapshot", affected_companies=("NVDA",),
    source_refs=("fmp:0001",))

# A social / rumor-tier event (X/social narrative -- never real corroboration).
_SOCIAL_EVENT = RealityEvent(
    event_id="E-soc-1", timestamp=_NOW, source_type="twitter", discipline="narrative",
    affected_companies=("NVDA",), source_refs=("x:0001",))


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _nvda(cands):
    return next(c for c in cands if c.ticker == "NVDA")


# =========================================================================== #
# A. Construction / model shape                                               #
# =========================================================================== #
class ConstructionTests(unittest.TestCase):
    def test_builds_with_required_ids_and_defaults(self):
        c = DiscoveryCandidate(discovery_id="disc:R:NVDA", run_id="R", ticker="NVDA")
        self.assertEqual(c.discovery_state, "monitor_only")
        self.assertEqual(c.factor_flags, ())
        self.assertEqual(c.source_refs, ())

    def test_is_frozen(self):
        c = DiscoveryCandidate(discovery_id="d", run_id="R", ticker="NVDA")
        with self.assertRaises(FrozenInstanceError):
            c.ticker = "MUTATED"

    def test_empty_required_id_rejected(self):
        for build in (
            lambda: DiscoveryCandidate(discovery_id="", run_id="R", ticker="T"),
            lambda: DiscoveryCandidate(discovery_id="d", run_id="", ticker="T"),
            lambda: DiscoveryCandidate(discovery_id="d", run_id="R", ticker=""),
        ):
            with self.assertRaises(ValueError):
                build()

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError):
            DiscoveryCandidate(discovery_id="d", run_id="R", ticker="T",
                               discovery_state="strong_buy")

    def test_invalid_factor_flag_rejected(self):
        with self.assertRaises(ValueError):
            DiscoveryCandidate(discovery_id="d", run_id="R", ticker="T",
                               factor_flags=("theme_relevant", "buy_now"))

    def test_invalid_dq_state_rejected(self):
        with self.assertRaises(ValueError):
            DiscoveryCandidate(discovery_id="d", run_id="R", ticker="T",
                               trust_data_quality_state="great")

    def test_state_and_flag_vocabularies_are_closed_and_expected(self):
        self.assertEqual(set(DISCOVERY_STATES), {
            "monitor_only", "diligence_candidate", "blocked_insufficient_evidence",
            "blocked_dq_failed", "blocked_risk_too_high"})
        self.assertEqual(set(BLOCKED_DISCOVERY_STATES), {
            "blocked_insufficient_evidence", "blocked_dq_failed", "blocked_risk_too_high"})
        # every documented factor label is present, none is a score/rank word
        for expected in ("theme_relevant", "bottleneck_exposed", "financial_inflection_hint",
                         "revenue_acceleration", "margin_expansion", "capex_capacity_signal",
                         "customer_contract_signal", "dilution_liquidity_risk", "valuation_stretch",
                         "technical_setup_available", "red_team_risk", "data_gap"):
            self.assertIn(expected, FACTOR_FLAGS)


# =========================================================================== #
# B. Graph membership ALONE creates no CapitalCandidate / recommendation       #
# =========================================================================== #
class MembershipAloneTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_seed_theme_graph()
        self.store = tempfile.mkdtemp(prefix="disc_membership_")

    def test_membership_only_never_diligence_and_publishes_nothing(self):
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW)
        self.assertTrue(cands)
        # bare graph membership is NEVER worth diligence
        for c in cands:
            self.assertNotEqual(c.discovery_state, "diligence_candidate")
            self.assertIn(c.discovery_state,
                          ("monitor_only", "blocked_insufficient_evidence"))
        # discovery NEVER writes a CapitalCandidate
        self.assertEqual(rm.published_candidates(self.store), ())

    def test_membership_candidate_carries_no_recommendation_field(self):
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW)
        c = _nvda(cands)
        self.assertFalse(hasattr(c, "recommendation"))
        self.assertFalse(hasattr(c, "action"))
        # membership flags are present but they are labels, not a verdict
        self.assertIn("theme_relevant", c.factor_flags)
        self.assertTrue(c.theme_refs)


# =========================================================================== #
# C. An SEC filing ALONE / an FMP row ALONE -> DiscoveryCandidate at most       #
# =========================================================================== #
class LoneEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_seed_theme_graph()
        self.store = tempfile.mkdtemp(prefix="disc_lone_")

    def test_sec_filing_alone_is_a_discovery_candidate_no_capital_candidate(self):
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(_SEC_EVENT,))
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "diligence_candidate")
        self.assertIn("financial_inflection_hint", c.factor_flags)
        self.assertIn("sec:0001", c.source_refs)
        # NO recommendation field, and NO CapitalCandidate was created.
        self.assertFalse(hasattr(c, "recommendation"))
        self.assertEqual(rm.published_candidates(self.store), ())

    def test_fmp_row_alone_is_a_discovery_candidate_no_recommendation(self):
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(_FMP_EVENT,))
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "diligence_candidate")
        self.assertIn("financial_inflection_hint", c.factor_flags)
        self.assertFalse(hasattr(c, "recommendation"))
        self.assertEqual(rm.published_candidates(self.store), ())


# =========================================================================== #
# D. The categorical states + exact reasons                                    #
# =========================================================================== #
class StateDerivationTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_seed_theme_graph()

    def test_monitor_only_for_social_rumor_only_basis(self):
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(_SOCIAL_EVENT,))
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "monitor_only")
        self.assertTrue(any("social" in r.lower() for r in c.reasons))

    def test_monitor_only_when_evidence_is_off_the_map(self):
        # real evidence but the ticker is NOT on the graph -> monitored, not a diligence candidate
        ev = RealityEvent(event_id="Eoff", source_type="sec_filing", source_authority="canonical",
                          claim_status="verified_fact", discipline="news_filings",
                          event_type="sec_8-k_results_of_operations", affected_companies=("ZZZZ",),
                          source_refs=("sec:z",))
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(ev,),
                                    watchlist=("ZZZZ",))
        self.assertEqual(cands[0].discovery_state, "monitor_only")

    def test_blocked_insufficient_evidence_with_reason(self):
        # a watchlist ticker with no graph connection AND no evidence
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, watchlist=("QQQQ",))
        c = cands[0]
        self.assertEqual(c.discovery_state, "blocked_insufficient_evidence")
        self.assertIn("data_gap", c.factor_flags)
        self.assertTrue(any("insufficient evidence" in r.lower() for r in c.reasons))

    def test_blocked_dq_failed_with_reason(self):
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(_SEC_EVENT,),
                                    dq_state="failed")
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "blocked_dq_failed")
        self.assertEqual(c.trust_data_quality_state, "failed")
        self.assertTrue(any("data quality is failed" in r.lower() for r in c.reasons))

    def test_blocked_by_policy_dq_maps_to_failed(self):
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(_SEC_EVENT,),
                                    dq_state="blocked_by_policy")
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "blocked_dq_failed")
        self.assertEqual(c.trust_data_quality_state, "failed")

    def test_blocked_risk_too_high_with_reason(self):
        killer = RiskNode(risk_id="rk-killer", description="thesis killer: fraud probe",
                          severity_label="severe", theme_or_company_ref="NVDA")
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(_SEC_EVENT,),
                                    risk_nodes=(killer,))
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "blocked_risk_too_high")
        self.assertIn("red_team_risk", c.factor_flags)
        self.assertTrue(any("thesis-killer" in r.lower() or "risk too" in r.lower()
                            for r in c.reasons))

    def test_diligence_candidate_needs_connection_and_real_evidence(self):
        # a fused real signal for a connected ticker -> worth diligence
        sig = RealitySignal(signal_id="sig-1", signal_type="fused", discipline="cross_discipline",
                            affected_companies=("NVDA",), source_refs=("sig:1",))
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, signals=(sig,))
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "diligence_candidate")
        self.assertTrue(c.is_diligence_candidate)

    def test_richer_factor_flags_from_findings(self):
        findings = (
            AgentFinding(finding_id="f1", agent_id="tattva.financial_inflection",
                         discipline="financial_inflection", finding_type="revenue_acceleration",
                         direction_label="accelerating", affected_companies=("NVDA",),
                         source_authority_summary="canonical", evidence_refs=("ev1",)),
            AgentFinding(finding_id="f2", agent_id="tattva.financial_inflection",
                         discipline="financial_inflection", finding_type="margin_inflection",
                         direction_label="improving", affected_companies=("NVDA",),
                         evidence_refs=("ev2",)),
        )
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, findings=findings)
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "diligence_candidate")
        self.assertIn("revenue_acceleration", c.factor_flags)
        self.assertIn("margin_expansion", c.factor_flags)
        # flags are ordered canonically (no ranking implied)
        idx = [FACTOR_FLAGS.index(f) for f in c.factor_flags]
        self.assertEqual(idx, sorted(idx))


# =========================================================================== #
# E. Social / DQ-failed can never reach diligence_candidate                    #
# =========================================================================== #
class NeverPromoteWeakBasisTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_seed_theme_graph()

    def test_social_only_never_diligence_candidate(self):
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(_SOCIAL_EVENT,))
        self.assertNotEqual(_nvda(cands).discovery_state, "diligence_candidate")

    def test_dq_failed_never_diligence_candidate_even_with_full_evidence(self):
        sig = RealitySignal(signal_id="sig-1", signal_type="fused", discipline="cross_discipline",
                            affected_companies=("NVDA",), source_refs=("sig:1",))
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW, events=(_SEC_EVENT,),
                                    signals=(sig,), dq_state="failed")
        self.assertEqual(_nvda(cands).discovery_state, "blocked_dq_failed")

    def test_social_plus_real_still_evaluates_on_real_only(self):
        # a social event ALONGSIDE a real SEC filing -> the real evidence corroborates; the
        # social one is surfaced but never the driver.
        cands = discover_candidates(self.graph, run_id="R1", now=_NOW,
                                    events=(_SEC_EVENT, _SOCIAL_EVENT))
        c = _nvda(cands)
        self.assertEqual(c.discovery_state, "diligence_candidate")
        self.assertIn("x:0001", c.source_refs)     # social ref preserved, not hidden


# =========================================================================== #
# F. Diligence handoff -- records an INPUT, 020A still gates publication         #
# =========================================================================== #
class DiligenceHandoffTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_seed_theme_graph()
        self.store = tempfile.mkdtemp(prefix="disc_handoff_")

    def _diligence_candidate(self):
        cands = discover_candidates(self.graph, run_id="RUN-A", now=_NOW, events=(_SEC_EVENT,))
        return _nvda(cands)

    def test_trigger_records_input_but_does_not_publish(self):
        cand = self._diligence_candidate()
        path = trigger_diligence_input(cand, store_dir=self.store)
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(path.endswith(os.path.join("diligence_inputs", "NVDA.json")))
        import json
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        self.assertEqual(rec["ticker"], "NVDA")
        self.assertFalse(rec["publishes_capital_candidate"])
        self.assertTrue(rec["requires_020a_publish_gate"])
        # NO CapitalCandidate was published by the trigger.
        self.assertEqual(rm.published_candidates(self.store), ())

    def test_trigger_refuses_non_diligence_candidate(self):
        cands = discover_candidates(self.graph, run_id="RUN-A", now=_NOW, events=(_SOCIAL_EVENT,))
        with self.assertRaises(ValueError):
            trigger_diligence_input(_nvda(cands), store_dir=self.store)

    def test_publication_still_requires_full_020a_gate(self):
        # Seed a REAL 020A run + a fused signal for NVDA.
        RunStore(self.store).append(
            PulseRun(run_id="RUN-A", started_at="2026-07-06T10:00:00",
                     completed_at="2026-07-06T10:00:05", mode="pulse", trigger_type="manual",
                     watchlist=("NVDA",), themes=("ai-accelerators",),
                     data_quality_status="healthy"),
            run_id="RUN-A", timestamp="2026-07-06T10:00:05")
        SignalStore(self.store).append(
            RealitySignal(signal_id="sig-nvda-0", signal_type="fused",
                          affected_companies=("NVDA",)),
            run_id="RUN-A", timestamp="2026-07-06T10:00:05")

        # record the discovery diligence input (does NOT publish)
        trigger_diligence_input(self._diligence_candidate(), store_dir=self.store)
        self.assertEqual(rm.published_candidates(self.store), ())

        # publish WITH provenance but WITHOUT the diligence thesis -> blocked on diligence: a
        # discovery input never substitutes for the 020A diligence gate.
        pub = publish_candidates_for_run(
            self.store, "RUN-A", tickers=("NVDA",), now=_NOW,
            diligence_by_ticker={"NVDA": {"opportunity_hypothesis_ref": "OPH-1"}})
        self.assertFalse(pub[0].is_eligible)
        self.assertEqual(pub[0].candidate_state, "ineligible_missing_diligence")
        self.assertEqual(rm.eligible_candidates(self.store), ())

        # only WITH full provenance + diligence + healthy DQ does 020A publish an eligible one
        pub2 = publish_candidates_for_run(
            self.store, "RUN-A", tickers=("NVDA",), now=_NOW,
            diligence_by_ticker={"NVDA": {"opportunity_hypothesis_ref": "OPH-1",
                                          "investment_diligence_ref": "THS-1",
                                          "forward_scenario_state": "present"}})
        self.assertTrue(pub2[0].is_eligible)
        self.assertEqual([c.ticker for c in rm.eligible_candidates(self.store)], ["NVDA"])


# =========================================================================== #
# G. No score/rank/trade field; deterministic; offline; AST-clean; demo stable  #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "ftplib", "smtplib", "selenium", "scrapy", "websocket", "websockets", "pycurl"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "signal", "smtplib", "ftplib"}

    @staticmethod
    def _read():
        with open(_DISCOVERY_PY, encoding="utf-8") as fh:
            return fh.read()

    def test_no_score_rank_trade_field_on_the_model(self):
        rm.assert_no_trade_fields(DiscoveryCandidate)
        for f in fields(DiscoveryCandidate):
            low = f.name.lower()
            for tok in ("buy", "sell", "hold", "order", "submit", "trade", "broker", "execution",
                        "score", "rank", "rating", "investab", "sizing", "recommend"):
                self.assertNotIn(tok, low, "{0} exposes {1!r}".format(f.name, tok))

    def test_no_score_or_rank_substring_anywhere_in_field_names(self):
        blob = " ".join(f.name for f in fields(DiscoveryCandidate))
        self.assertIsNone(re.search(r"score|rank|rating|investab", blob.lower()))

    def test_imports_no_network_scheduler_broker(self):
        tree = ast.parse(self._read())
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.append((node.module or "").split(".")[0])
        for m in mods:
            self.assertNotIn(m, self._NET, "imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "imports forbidden {0}".format(m))

    def test_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "defines {0}".format(node.name))

    def test_source_has_no_broker_scheduler_or_wall_clock_token(self):
        blob = self._read().lower()
        for tok in ("place_order", "submit_order", "broker.submit", "execute_trade",
                    "schedule.every", "cron", "time.time(", "datetime.now(", "datetime.utcnow("):
            self.assertNotIn(tok, blob, "forbidden token {0}".format(tok))

    def test_deterministic_same_inputs_same_output(self):
        graph = build_seed_theme_graph()
        a = discover_candidates(graph, run_id="R1", now=_NOW, events=(_SEC_EVENT,))
        b = discover_candidates(graph, run_id="R1", now=_NOW, events=(_SEC_EVENT,))
        self.assertEqual([repr(x) for x in a], [repr(x) for x in b])
        self.assertEqual(discovery_id_for("R1", "nvda"), "disc:R1:NVDA")

    def test_discover_is_offline_under_socket_kill_switch(self):
        graph = build_seed_theme_graph()
        real = socket.socket
        socket.socket = _boom_socket
        try:
            cands = discover_candidates(graph, run_id="R1", now=_NOW, events=(_SEC_EVENT,))
            store = tempfile.mkdtemp(prefix="disc_offline_")
            trigger_diligence_input(_nvda(cands), store_dir=store)
        finally:
            socket.socket = real
        self.assertTrue(cands)

    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="disc_demo_a_")
        d2 = tempfile.mkdtemp(prefix="disc_demo_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))


if __name__ == "__main__":
    unittest.main()
