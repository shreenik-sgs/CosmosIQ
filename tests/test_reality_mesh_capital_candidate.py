"""IMPLEMENTATION-019B -- typed CapitalCandidate contract + HARD eligibility gate.

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE -- no network, no scheduler, no broker, no
live endpoint. It proves the one invariant an audit found missing before 019 closeout: a "capital
candidate" is a TYPED object that CANNOT exist as ``eligible`` without its full evidence lineage.

* the CapitalCandidate contract constructs; ``eligible`` REQUIRES the full ref set
  (reality_signal_refs + opportunity_hypothesis_ref + investment_diligence_ref + healthy DQ) --
  each missing piece raising ValueError (eligibility is unforgeable at the type level);
* ``assess_candidate_eligibility`` returns the right ineligible_* state per missing piece, and
  ``eligible`` only when complete -- it never fabricates a ref to reach eligible;
* the contract carries NO score / rank / rating / investability / sizing / trade / order field
  (introspection + ``assert_no_trade_fields``);
* the ``check_capital_candidate`` gate FAILS a (forged) eligible-but-incomplete candidate and
  rolls the run to ``blocked_by_policy``; PASSES a properly-eligible one; skips when none;
* the capital-candidate cockpit shows ELIGIBLE only with full lineage, and the honest
  ineligibility reason otherwise (dispatcher-level + function-level, offline);
* determinism; an offline kill-switch; capital_candidate.py imports no network / scheduler /
  broker module and defines no ``*score`` / ``*rank`` function (AST); demo/default pulse +
  default gate run stay byte-identical (the gate appends only when candidates are supplied).
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import unittest
from dataclasses import fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import capital_candidate as CC
from reality_mesh import gates as G
from reality_mesh.capital_candidate import CapitalCandidate, assess_candidate_eligibility

_CC_PY = os.path.join(_SRC, "reality_mesh", "capital_candidate.py")
_NOW = "2026-07-04T00:00:00Z"

# The full, healthy lineage every ``eligible`` candidate must carry.
_FULL = dict(
    ticker="IREN", run_id="RUN-1",
    reality_signal_refs=("sig-1", "sig-2"),
    opportunity_hypothesis_ref="OPH-1",
    investment_diligence_ref="THS-1",
    forward_scenario_state="present",
    trust_data_quality_state="healthy",
    now=_NOW,
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# =========================================================================== #
# The contract constructs; eligible is UNFORGEABLE without the full lineage     #
# =========================================================================== #
class ContractConstructionTests(unittest.TestCase):
    def test_constructs_a_draft_candidate(self):
        c = CapitalCandidate(candidate_id="cc:R:T", ticker="T", run_id="R")
        self.assertEqual(c.candidate_state, "draft")
        self.assertFalse(c.is_eligible)

    def test_required_ids_must_be_non_empty(self):
        for bad in (dict(candidate_id="", ticker="T", run_id="R"),
                    dict(candidate_id="x", ticker="", run_id="R"),
                    dict(candidate_id="x", ticker="T", run_id="")):
            with self.assertRaises(ValueError):
                CapitalCandidate(**bad)

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError):
            CapitalCandidate(candidate_id="x", ticker="T", run_id="R",
                             candidate_state="bogus")

    def test_invalid_forward_and_dq_labels_rejected(self):
        with self.assertRaises(ValueError):
            CapitalCandidate(candidate_id="x", ticker="T", run_id="R",
                             forward_scenario_state="maybe")
        with self.assertRaises(ValueError):
            CapitalCandidate(candidate_id="x", ticker="T", run_id="R",
                             trust_data_quality_state="blocked_by_policy")

    def test_eligible_with_full_lineage_constructs(self):
        c = CapitalCandidate(
            candidate_id="cc:R:T", ticker="T", run_id="R",
            reality_signal_refs=("s1",), opportunity_hypothesis_ref="OPH",
            investment_diligence_ref="THS", trust_data_quality_state="healthy",
            candidate_state="eligible")
        self.assertTrue(c.is_eligible)
        self.assertEqual(c.missing_lineage(), ())

    # -- the core invariant: eligible impossible with ANY piece missing -------- #
    def _eligible_kwargs(self):
        return dict(candidate_id="cc:R:T", ticker="T", run_id="R",
                    reality_signal_refs=("s1",), opportunity_hypothesis_ref="OPH",
                    investment_diligence_ref="THS", trust_data_quality_state="healthy",
                    candidate_state="eligible")

    def test_eligible_without_signals_raises(self):
        kw = self._eligible_kwargs(); kw["reality_signal_refs"] = ()
        with self.assertRaises(ValueError):
            CapitalCandidate(**kw)

    def test_eligible_without_hypothesis_raises(self):
        kw = self._eligible_kwargs(); kw["opportunity_hypothesis_ref"] = ""
        with self.assertRaises(ValueError):
            CapitalCandidate(**kw)

    def test_eligible_without_diligence_raises(self):
        kw = self._eligible_kwargs(); kw["investment_diligence_ref"] = ""
        with self.assertRaises(ValueError):
            CapitalCandidate(**kw)

    def test_eligible_without_healthy_dq_raises(self):
        for dq in ("degraded", "failed", ""):
            kw = self._eligible_kwargs(); kw["trust_data_quality_state"] = dq
            with self.assertRaises(ValueError):
                CapitalCandidate(**kw)


# =========================================================================== #
# assess_candidate_eligibility -- the honest state per missing piece            #
# =========================================================================== #
class AssessEligibilityTests(unittest.TestCase):
    def test_full_healthy_lineage_is_eligible(self):
        c = assess_candidate_eligibility(**_FULL)
        self.assertEqual(c.candidate_state, "eligible")
        self.assertTrue(c.is_eligible)
        self.assertEqual(c.ticker, "IREN")
        self.assertEqual(c.candidate_id, "cc:RUN-1:IREN")
        self.assertIn("eligible", c.basis)

    def test_missing_signals_is_missing_provenance(self):
        kw = dict(_FULL); kw["reality_signal_refs"] = ()
        self.assertEqual(assess_candidate_eligibility(**kw).candidate_state,
                         "ineligible_missing_provenance")

    def test_missing_hypothesis_is_missing_provenance(self):
        kw = dict(_FULL); kw["opportunity_hypothesis_ref"] = ""
        self.assertEqual(assess_candidate_eligibility(**kw).candidate_state,
                         "ineligible_missing_provenance")

    def test_missing_diligence_is_missing_diligence(self):
        kw = dict(_FULL); kw["investment_diligence_ref"] = ""
        self.assertEqual(assess_candidate_eligibility(**kw).candidate_state,
                         "ineligible_missing_diligence")

    def test_failed_dq_is_dq_failed(self):
        kw = dict(_FULL); kw["trust_data_quality_state"] = "failed"
        self.assertEqual(assess_candidate_eligibility(**kw).candidate_state,
                         "ineligible_dq_failed")

    def test_degraded_dq_is_stale(self):
        kw = dict(_FULL); kw["trust_data_quality_state"] = "degraded"
        self.assertEqual(assess_candidate_eligibility(**kw).candidate_state,
                         "ineligible_stale")

    def test_unstated_dq_is_stale(self):
        kw = dict(_FULL); kw["trust_data_quality_state"] = ""
        self.assertEqual(assess_candidate_eligibility(**kw).candidate_state,
                         "ineligible_stale")

    def test_never_fabricates_a_ref_to_reach_eligible(self):
        # everything absent -> honest ineligible, and the returned record's own lineage is empty
        c = assess_candidate_eligibility(
            ticker="T", run_id="R", reality_signal_refs=(),
            opportunity_hypothesis_ref="", investment_diligence_ref="",
            forward_scenario_state="absent", trust_data_quality_state="", now=_NOW)
        self.assertFalse(c.is_eligible)
        self.assertEqual(c.reality_signal_refs, ())
        self.assertEqual(c.opportunity_hypothesis_ref, "")
        self.assertEqual(c.investment_diligence_ref, "")

    def test_blank_signal_refs_are_stripped(self):
        kw = dict(_FULL); kw["reality_signal_refs"] = ("", "  ")
        self.assertEqual(assess_candidate_eligibility(**kw).candidate_state,
                         "ineligible_missing_provenance")

    def test_deterministic(self):
        self.assertEqual(assess_candidate_eligibility(**_FULL),
                         assess_candidate_eligibility(**_FULL))


# =========================================================================== #
# No score / rank / rating / trade field anywhere on the contract               #
# =========================================================================== #
class NoTradeOrScoreFieldTests(unittest.TestCase):
    def test_assert_no_trade_fields_clean(self):
        rm.assert_no_trade_fields(CapitalCandidate)
        CC.assert_no_trade_fields  # module ran the guard at import

    def test_no_forbidden_token_in_any_field_name(self):
        for f in fields(CapitalCandidate):
            low = f.name.lower()
            for tok in ("buy", "sell", "hold", "order", "trade", "broker", "execution",
                        "score", "rank", "rating", "investab", "sizing"):
                self.assertNotIn(tok, low, "{0} exposes {1!r}".format(f.name, tok))

    def test_no_numeric_field_present(self):
        # a candidate is an eligibility+lineage record: refs + labels + strings only.
        c = assess_candidate_eligibility(**_FULL)
        for f in fields(CapitalCandidate):
            val = getattr(c, f.name)
            self.assertNotIsInstance(val, (int, float),
                                     "{0} carries a number".format(f.name))


# =========================================================================== #
# The gate: a forged eligible-but-incomplete candidate HARD-fails               #
# =========================================================================== #
class CapitalCandidateGateTests(unittest.TestCase):
    def _forged(self, **overrides):
        rec = {"candidate_id": "cc:R:T", "candidate_state": "eligible",
               "reality_signal_refs": ("s1",), "opportunity_hypothesis_ref": "OPH",
               "investment_diligence_ref": "THS", "trust_data_quality_state": "healthy"}
        rec.update(overrides)
        return rec

    def test_none_skips_and_passes(self):
        self.assertEqual(G.DataQualityGateRunner().check_capital_candidate([]).status, "pass")
        self.assertEqual(G.DataQualityGateRunner().check_capital_candidate().status, "pass")

    def test_properly_eligible_passes(self):
        c = assess_candidate_eligibility(**_FULL)
        res = G.DataQualityGateRunner().check_capital_candidate([c])
        self.assertEqual(res.status, "pass")
        self.assertEqual(res.category, "capital_candidate")

    def test_forged_eligible_missing_signals_fails(self):
        res = G.DataQualityGateRunner().check_capital_candidate(
            [self._forged(reality_signal_refs=())])
        self.assertEqual(res.status, "fail")
        self.assertIn("cc:R:T", res.subject_refs)

    def test_forged_eligible_missing_hypothesis_fails(self):
        self.assertEqual(G.DataQualityGateRunner().check_capital_candidate(
            [self._forged(opportunity_hypothesis_ref="")]).status, "fail")

    def test_forged_eligible_missing_diligence_fails(self):
        self.assertEqual(G.DataQualityGateRunner().check_capital_candidate(
            [self._forged(investment_diligence_ref="")]).status, "fail")

    def test_forged_eligible_off_failed_dq_fails(self):
        self.assertEqual(G.DataQualityGateRunner().check_capital_candidate(
            [self._forged(trust_data_quality_state="failed")]).status, "fail")

    def test_non_eligible_incomplete_candidate_is_not_flagged(self):
        # an honestly-ineligible candidate that is missing refs is NOT a violation.
        c = assess_candidate_eligibility(
            ticker="T", run_id="R", reality_signal_refs=(),
            opportunity_hypothesis_ref="", investment_diligence_ref="",
            forward_scenario_state="absent", trust_data_quality_state="failed", now=_NOW)
        self.assertEqual(G.DataQualityGateRunner().check_capital_candidate([c]).status, "pass")

    def test_forged_eligible_rolls_run_to_blocked_by_policy(self):
        _, overall = G.DataQualityGateRunner().run(
            candidates=[self._forged(investment_diligence_ref="")])
        self.assertEqual(overall, "blocked_by_policy")
        self.assertIn("capital_candidate", G.POLICY_OR_SECURITY_CATEGORIES)

    def test_proper_eligible_run_not_blocked(self):
        c = assess_candidate_eligibility(**_FULL)
        _, overall = G.DataQualityGateRunner().run(candidates=[c])
        self.assertIn(overall, ("healthy", "degraded"))


# =========================================================================== #
# run() default path byte-identical; the gate appends only with candidates      #
# =========================================================================== #
class DefaultRunByteIdenticalTests(unittest.TestCase):
    def test_default_run_still_eleven_categories(self):
        results, _ = G.DataQualityGateRunner().run()
        self.assertEqual(tuple(r.category for r in results), G.GATE_CATEGORIES)
        self.assertEqual(len(results), 11)

    def test_capital_candidate_not_in_the_core_eleven(self):
        self.assertNotIn("capital_candidate", G.GATE_CATEGORIES)

    def test_candidates_append_a_twelfth_result(self):
        c = assess_candidate_eligibility(**_FULL)
        results, _ = G.DataQualityGateRunner().run(candidates=[c])
        self.assertEqual(len(results), 12)
        self.assertEqual(results[-1].category, "capital_candidate")

    def test_default_run_is_byte_identical_across_calls(self):
        self.assertEqual(G.DataQualityGateRunner().run(), G.DataQualityGateRunner().run())

    def test_demo_pulse_is_byte_identical(self):
        a = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        b = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        self.assertEqual(tuple(s.signal_id for s in a.signals),
                         tuple(s.signal_id for s in b.signals))
        self.assertEqual(tuple(f.finding_id for f in a.findings),
                         tuple(f.finding_id for f in b.findings))


# =========================================================================== #
# Cockpit: ELIGIBLE only with full lineage; honest reason otherwise             #
# =========================================================================== #
def _dispatch(store, path, now=_NOW):
    from cosmosiq_app import dispatch
    return dispatch({"method": "GET", "path": path, "query": {}, "body": {}},
                    store_dir=store, now=now)


class _Thesis(object):
    """A minimal stand-in for the accepted engine's thesis output (id fields only)."""
    def __init__(self, opportunity_id, thesis_id):
        self.opportunity_id = opportunity_id
        self.thesis_id = thesis_id


class CandidateCockpitEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="cc_019b_")
        # one persisted, HEALTHY current run + a signal naming IREN in it.
        from reality_mesh.stores import RunStore, SignalStore
        from reality_mesh.runtime import PulseRun
        from reality_mesh.models import RealitySignal
        RunStore(self.store).append(
            PulseRun(run_id="RUN-A", started_at="2026-07-04T10:00:00",
                     completed_at="2026-07-04T10:00:05", mode="pulse",
                     trigger_type="manual", watchlist=("IREN",), themes=("physical-ai",),
                     data_quality_status="healthy"),
            run_id="RUN-A", timestamp="2026-07-04T10:00:05")
        SignalStore(self.store).append(
            RealitySignal(signal_id="sig-iren-1", signal_type="fused",
                          affected_companies=("IREN",)),
            run_id="RUN-A", timestamp="2026-07-04T10:00:05")

    def test_honest_ineligibility_without_diligence_via_dispatch(self):
        # no diligence inputs recorded -> no thesis -> honest INELIGIBLE, never eligible.
        html = _dispatch(self.store, "/candidates/IREN")["body"]
        self.assertIn("Capital-candidate eligibility", html)
        self.assertIn("INELIGIBLE", html)
        self.assertNotIn("ELIGIBLE -- full evidence lineage present", html)

    def test_eligible_shown_only_with_full_lineage(self):
        # a full, healthy lineage (seeded signal + a computed thesis) -> ELIGIBLE section.
        from cosmosiq_app.cockpits import _eligibility_section
        thesis = _Thesis(opportunity_id="OPH-42", thesis_id="THS-42")
        html = _eligibility_section(self.store, "IREN",
                                    {"forward_inputs": {"base": []}}, thesis)
        self.assertIn("ELIGIBLE -- full evidence lineage present", html)
        self.assertIn("sig-iren-1", html)
        self.assertIn("OPH-42", html)
        self.assertIn("THS-42", html)

    def test_missing_thesis_yields_ineligible_section(self):
        from cosmosiq_app.cockpits import _eligibility_section
        html = _eligibility_section(self.store, "IREN", None, None)
        self.assertIn("INELIGIBLE", html)
        self.assertNotIn("ELIGIBLE -- full evidence lineage present", html)

    def test_no_run_is_honest_not_fabricated(self):
        from cosmosiq_app.cockpits import _eligibility_section
        empty = tempfile.mkdtemp(prefix="cc_019b_empty_")
        html = _eligibility_section(empty, "IREN", None, _Thesis("OPH", "THS"))
        self.assertIn("No pulse run is persisted", html)

    def test_cockpit_shows_no_score_or_trade_affordance(self):
        html = _dispatch(self.store, "/candidates/IREN")["body"].lower()
        self.assertNotRegex(html, r'(?i)"score"|investability score|ranked')
        self.assertNotRegex(html, r"(?i)\b(buy|sell|order now|place order|submit order)\b")
        self.assertNotIn("<button", html)
        self.assertNotIn("<form", html)


# =========================================================================== #
# Guardrails -- AST clean, offline kill-switch, deterministic                    #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "ftplib", "smtplib", "selenium", "scrapy", "websocket", "websockets", "pycurl"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "signal"}

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_capital_candidate_imports_no_network_scheduler_broker(self):
        tree = ast.parse(self._read(_CC_PY))
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.append((node.module or "").split(".")[0])
        for m in mods:
            self.assertNotIn(m, self._NET, "imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "imports forbidden {0}".format(m))

    def test_capital_candidate_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_CC_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "defines {0}".format(node.name))

    def test_source_has_no_broker_or_execution_token(self):
        blob = self._read(_CC_PY).lower()
        for tok in ("place_order", "submit_order", "broker.submit", "execute_trade",
                    "time.time(", "datetime.now("):
            self.assertNotIn(tok, blob, "forbidden token {0}".format(tok))

    def test_assess_is_offline_under_socket_kill_switch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            c = assess_candidate_eligibility(**_FULL)
            _, overall = G.DataQualityGateRunner().run(candidates=[c])
        finally:
            socket.socket = real
        self.assertEqual(c.candidate_state, "eligible")
        self.assertIn(overall, ("healthy", "degraded"))


if __name__ == "__main__":
    unittest.main()
