"""IMPLEMENTATION-020A -- the CapitalCandidate publication path (reality_mesh layer).

INFRASTRUCTURE ONLY. Runs entirely OFFLINE -- no network, no scheduler, no broker, no live
endpoint. Proves the OFFICIAL publish path: assess -> construct a typed CapitalCandidate ->
persist APPEND-ONLY (content-derived id, idempotent) -> run the 019B DQ gate -> the honest
eligible/blocked state.

* an eligible candidate persists ONLY with its FULL provenance (signals + hypothesis ref +
  diligence ref + a healthy producing run + run_id + mode);
* a candidate missing ANY required ref persists as ``ineligible_*`` WITH the exact reason
  (missing signals -> provenance; missing hypothesis -> provenance; missing diligence ->
  diligence; non-healthy DQ -> dq_failed / stale) -- nothing is hidden;
* a MISSING forward scenario is an explicit ``absent`` GAP, NOT a block -- a candidate with the
  other refs stays eligible and carries the gap;
* publication is APPEND-ONLY: re-publishing an unchanged candidate is byte-identical (the prior
  line is unchanged); a published set never rolls the run to ``blocked_by_policy``;
* the record carries NO buy/sell/order/submit/broker/score/rank field (introspection +
  ``assert_no_trade_fields``); the module imports no network/scheduler/broker and defines no
  ``*score`` / ``*rank`` function (AST); publication runs under a socket kill-switch.
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
from reality_mesh.capital_candidate import (
    CapitalCandidate,
    CapitalCandidateStore,
    publish_candidates_for_run,
)
from reality_mesh.gates import DataQualityGateRunner
from reality_mesh.models import RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import RunStore, SignalStore

_CC_PY = os.path.join(_SRC, "reality_mesh", "capital_candidate.py")
_NOW = "2026-07-04T12:00:00Z"
_FULL_DILIGENCE = {"opportunity_hypothesis_ref": "OPH-1",
                   "investment_diligence_ref": "THS-1",
                   "forward_scenario_state": "present"}


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _seed_run(store, *, dq="healthy", tickers=("IREN", "AAOI"),
              signal_for=("IREN",), run_id="RUN-A"):
    """One persisted, DQ-labelled run + a fused signal for each named ticker."""
    RunStore(store).append(
        PulseRun(run_id=run_id, started_at="2026-07-04T10:00:00",
                 completed_at="2026-07-04T10:00:05", mode="pulse", trigger_type="manual",
                 watchlist=tuple(tickers), themes=("physical-ai",),
                 data_quality_status=dq),
        run_id=run_id, timestamp="2026-07-04T10:00:05")
    for i, ticker in enumerate(signal_for):
        SignalStore(store).append(
            RealitySignal(signal_id="sig-{0}-{1}".format(ticker.lower(), i),
                          signal_type="fused", affected_companies=(ticker,)),
            run_id=run_id, timestamp="2026-07-04T10:00:05")
    return run_id


class EligibleOnlyWithFullProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="pub_020a_")

    def _publish(self, dilg, **run_kw):
        run_id = _seed_run(self.store, **run_kw)
        return publish_candidates_for_run(
            self.store, run_id, tickers=("IREN",), now=_NOW,
            diligence_by_ticker={"IREN": dilg})

    def test_full_lineage_publishes_one_eligible_with_provenance(self):
        pub = self._publish(_FULL_DILIGENCE)
        self.assertEqual(len(pub), 1)
        cand = pub[0]
        self.assertEqual(cand.candidate_state, "eligible")
        self.assertTrue(cand.is_eligible)
        # ONLY with full provenance: every required piece present.
        self.assertEqual(cand.missing_lineage(), ())
        self.assertTrue(cand.reality_signal_refs)
        self.assertEqual(cand.opportunity_hypothesis_ref, "OPH-1")
        self.assertEqual(cand.investment_diligence_ref, "THS-1")
        self.assertEqual(cand.trust_data_quality_state, "healthy")
        self.assertEqual(cand.run_id, "RUN-A")
        self.assertEqual(cand.mode, "pulse")
        self.assertTrue(cand.source_provenance)      # provenance summary populated
        # and it is the ONLY eligible one persisted.
        self.assertEqual([c.ticker for c in rm.eligible_candidates(self.store)], ["IREN"])
        self.assertEqual(rm.blocked_candidates(self.store), ())

    def test_missing_signals_blocked_missing_provenance(self):
        # no signal for IREN in this run -> no provenance.
        self._publish(_FULL_DILIGENCE, signal_for=())
        blocked = rm.blocked_candidates(self.store)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0].candidate_state, "ineligible_missing_provenance")
        self.assertIn("reality_signal_refs absent", blocked[0].basis)
        self.assertEqual(rm.eligible_candidates(self.store), ())

    def test_missing_hypothesis_blocked_missing_provenance(self):
        dilg = dict(_FULL_DILIGENCE); dilg["opportunity_hypothesis_ref"] = ""
        self._publish(dilg)
        blocked = rm.blocked_candidates(self.store)
        self.assertEqual(blocked[0].candidate_state, "ineligible_missing_provenance")
        self.assertIn("opportunity_hypothesis_ref absent", blocked[0].basis)

    def test_missing_diligence_blocked_missing_diligence(self):
        dilg = dict(_FULL_DILIGENCE); dilg["investment_diligence_ref"] = ""
        self._publish(dilg)
        blocked = rm.blocked_candidates(self.store)
        self.assertEqual(blocked[0].candidate_state, "ineligible_missing_diligence")
        self.assertIn("NO diligence reference", blocked[0].basis)

    def test_failed_dq_blocked_dq_failed(self):
        self._publish(_FULL_DILIGENCE, dq="failed")
        blocked = rm.blocked_candidates(self.store)
        self.assertEqual(blocked[0].candidate_state, "ineligible_dq_failed")
        self.assertIn("data quality is FAILED", blocked[0].basis)

    def test_degraded_dq_blocked_stale(self):
        self._publish(_FULL_DILIGENCE, dq="degraded")
        blocked = rm.blocked_candidates(self.store)
        self.assertEqual(blocked[0].candidate_state, "ineligible_stale")

    def test_blocked_by_policy_run_maps_to_dq_failed(self):
        self._publish(_FULL_DILIGENCE, dq="blocked_by_policy")
        blocked = rm.blocked_candidates(self.store)
        self.assertEqual(blocked[0].candidate_state, "ineligible_dq_failed")

    def test_missing_forward_scenario_is_a_gap_not_a_block(self):
        dilg = dict(_FULL_DILIGENCE); dilg["forward_scenario_state"] = ""
        pub = self._publish(dilg)
        cand = pub[0]
        # the forward scenario is ABSENT -- an explicit gap -- but the candidate is STILL eligible.
        self.assertEqual(cand.forward_scenario_state, "absent")
        self.assertTrue(cand.is_eligible)
        self.assertIn("forward:absent", cand.source_provenance)


class PersistenceAndScopeTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="pub_020a_persist_")
        self.run_id = _seed_run(self.store)

    def _publish_iren(self):
        return publish_candidates_for_run(
            self.store, self.run_id, tickers=("IREN",), now=_NOW,
            diligence_by_ticker={"IREN": _FULL_DILIGENCE})

    def test_publication_is_append_only_and_idempotent(self):
        self._publish_iren()
        path = os.path.join(self.store, "capital_candidate_store.jsonl")
        with open(path, "rb") as fh:
            first = fh.read()
        # re-publish the SAME candidate -> byte-identical file, prior line unchanged.
        self._publish_iren()
        with open(path, "rb") as fh:
            second = fh.read()
        self.assertEqual(first, second)
        self.assertEqual(first.decode("utf-8").count("\n"), 1)

    def test_whole_watchlist_scope_when_no_tickers_given(self):
        pub = publish_candidates_for_run(
            self.store, self.run_id, now=_NOW,
            diligence_by_ticker={"IREN": _FULL_DILIGENCE})
        self.assertEqual(sorted(c.ticker for c in pub), ["AAOI", "IREN"])
        # IREN eligible (full lineage), AAOI blocked (no signal -> no provenance).
        self.assertEqual([c.ticker for c in rm.eligible_candidates(self.store)], ["IREN"])
        self.assertEqual([c.ticker for c in rm.blocked_candidates(self.store)], ["AAOI"])

    def test_missing_run_raises(self):
        with self.assertRaises(ValueError):
            publish_candidates_for_run(self.store, "NOPE", now=_NOW)

    def test_query_helpers_scope_by_run(self):
        self._publish_iren()
        self.assertEqual(len(rm.published_candidates(self.store, self.run_id)), 1)
        self.assertEqual(rm.published_candidates(self.store, "OTHER"), ())


class GateAndGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="pub_020a_gate_")
        self.run_id = _seed_run(self.store)

    def test_published_set_never_rolls_run_to_blocked_by_policy(self):
        pub = publish_candidates_for_run(
            self.store, self.run_id, now=_NOW,
            diligence_by_ticker={"IREN": _FULL_DILIGENCE})
        _results, overall = DataQualityGateRunner().run(candidates=pub)
        self.assertIn(overall, ("healthy", "degraded"))
        self.assertNotEqual(overall, "blocked_by_policy")

    def test_no_trade_or_score_field_on_the_persisted_record(self):
        rm.assert_no_trade_fields(CapitalCandidate)
        for f in fields(CapitalCandidate):
            low = f.name.lower()
            for tok in ("buy", "sell", "order", "submit", "trade", "broker", "execution",
                        "score", "rank", "rating", "investab", "sizing"):
                self.assertNotIn(tok, low, "{0} exposes {1!r}".format(f.name, tok))

    def test_persisted_line_carries_no_score_or_order_key(self):
        publish_candidates_for_run(
            self.store, self.run_id, tickers=("IREN",), now=_NOW,
            diligence_by_ticker={"IREN": _FULL_DILIGENCE})
        with open(os.path.join(self.store, "capital_candidate_store.jsonl")) as fh:
            blob = fh.read().lower()
        for tok in ('"score"', '"rank"', '"order"', '"buy"', '"sell"', '"broker"'):
            self.assertNotIn(tok, blob)

    def test_store_round_trips_the_record_equal(self):
        pub = publish_candidates_for_run(
            self.store, self.run_id, tickers=("IREN",), now=_NOW,
            diligence_by_ticker={"IREN": _FULL_DILIGENCE})
        loaded = CapitalCandidateStore(self.store).read_all()
        self.assertEqual(loaded[-1], pub[0])

    def test_publish_is_offline_under_socket_kill_switch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            pub = publish_candidates_for_run(
                self.store, self.run_id, tickers=("IREN",), now=_NOW,
                diligence_by_ticker={"IREN": _FULL_DILIGENCE})
        finally:
            socket.socket = real
        self.assertTrue(pub[0].is_eligible)


class SourceGuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "ftplib", "smtplib", "selenium", "scrapy", "websocket", "websockets", "pycurl"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "signal"}

    @staticmethod
    def _read():
        with open(_CC_PY, encoding="utf-8") as fh:
            return fh.read()

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

    def test_source_has_no_broker_or_execution_token(self):
        blob = self._read().lower()
        for tok in ("place_order", "submit_order", "broker.submit", "execute_trade",
                    "time.time(", "datetime.now(", "schedule.every", "cron"):
            self.assertNotIn(tok, blob, "forbidden token {0}".format(tok))


if __name__ == "__main__":
    unittest.main()
