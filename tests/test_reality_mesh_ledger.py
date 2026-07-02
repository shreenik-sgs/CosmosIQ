"""IMPLEMENTATION-013D -- AgentRunLedger + the failure-isolating agent runner (Phase-013).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE against temp-dir JSONL ledgers -- no
network, no scheduler, no broker, no live endpoint. It proves the OBSERVABILITY_CONTRACT_013 §4
failure-isolation rules + RUNTIME_CONTRACT_013 §3 the gate enforces (TEST_MATRIX_013 §D1-D5 +
the global guardrails §I):

* D1 -- an agent run is LOGGED to the AgentRunLedger (append + results_for_run / results_for_agent);
* D2 -- **one failed agent (raises) does NOT crash a batch** -- run_agents_isolated returns a
  ``failed`` AgentRunResult + a data gap and the other agents still run;
* D3 -- a timeout is recorded (status / health reflect it, no crash);
* D4 -- a skipped agent is recorded (status="skipped");
* D5 -- a policy-blocked output is recorded (status="blocked_by_policy");
* I  -- the ledger is append-only (no update / delete; reuses the 013B base); no secret survives
  into any ledger record; no score / rank / trade field on the AgentRunResult; ledger.py imports
  no network / scheduler / broker module + defines no ``*score`` / ``*rank`` function (AST guards);
  the whole suite builds under a socket kill-switch; timestamps are injected.
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
from reality_mesh import ledger as LG

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_LEDGER_PY = os.path.join(_PKG_DIR, "ledger.py")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _tmp():
    return tempfile.mkdtemp(prefix="rm_ledger_")


# --------------------------------------------------------------------------- #
# Fixtures: a configurable fake sensor agent + a bundled event                  #
# --------------------------------------------------------------------------- #
def _event(event_id="E1", discipline="market_regime"):
    return rm.RealityEvent(
        event_id=event_id, timestamp="2026-06-29T00:00:00Z", source_id="src.sec",
        source_type="sec_filing", source_authority="canonical",
        claim_status="verified_fact", discipline=discipline, event_type="8-K",
        affected_companies=("IREN",), affected_themes=("physical_ai",),
        evidence_refs=("ex1",), source_refs=("sec:0001",),
        confidence_label="high", freshness_label="fresh", half_life="days")


def _finding(finding_id="F1", discipline="market_regime"):
    return rm.AgentFinding(
        finding_id=finding_id, agent_id="a", agent_layer="Tattva", agent_name="n",
        discipline=discipline, input_events=("E1",), finding_type="AgentFinding",
        affected_companies=("IREN",), affected_themes=("physical_ai",),
        direction_label="stable", magnitude_label="minor", confidence_label="moderate",
        freshness_label="recent", half_life="days", source_authority_summary="canonical",
        evidence_refs=("ex1",), data_gaps=(), routing_targets=("TattvaSignalFusion",))


class _FakeAgent(rm.SensorAgent):
    """A fake sensor whose ``run`` behaviour (return findings / raise) is injected."""

    def __init__(self, agent_id, behaviour, discipline="market_regime"):
        self._agent_id = agent_id
        self._behaviour = behaviour
        self._discipline = discipline

    @property
    def descriptor(self):
        return rm.AgentDescriptor(
            agent_id=self._agent_id, layer="Tattva", discipline=self._discipline,
            agent_type="sensor", emits=("AgentFinding",))

    def run(self, context, events):
        return self._behaviour(context, events)


def _raise(exc):
    def _run(context, events):
        raise exc
    return _run


def _return(*findings):
    def _run(context, events):
        return tuple(findings)
    return _run


def _ctx(agent_id, run_id="RUN1"):
    return rm.AgentRunContext(run_id=run_id, agent_id=agent_id, input_event_ids=("E1",))


# =========================================================================== #
# D1. An agent run is logged to the AgentRunLedger                             #
# =========================================================================== #
class LedgerLoggingTests(unittest.TestCase):
    def test_append_result_and_query_by_run_and_agent(self):
        led = rm.AgentRunLedger(_tmp())
        agent = _FakeAgent("a.ok", _return(_finding("F1")))
        result = rm.run_agent_isolated(agent, _ctx("a.ok"), (_event(),), now="t1")
        rid = led.append_result(result)
        self.assertEqual(rid, "RUN1:a.ok")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.finding_ids, ("F1",))

        self.assertEqual(led.results_for_run("RUN1"), (result,))
        self.assertEqual(led.results_for_agent("a.ok"), (result,))
        self.assertEqual(led.results_for_run("OTHER"), ())

    def test_ledger_reconstructs_result_equal(self):
        led = rm.AgentRunLedger(_tmp())
        result = rm.run_agent_isolated(
            _FakeAgent("a.ok", _return(_finding("F1"))), _ctx("a.ok"), (_event(),), now="t1")
        led.append_result(result)
        self.assertEqual(led.read_all(), (result,))

    def test_ledger_is_a_store_subclass_with_schema_envelope(self):
        self.assertTrue(issubclass(rm.AgentRunLedger, rm.AppendOnlyStore))
        led = rm.AgentRunLedger(_tmp())
        led.append_result(rm.run_agent_isolated(
            _FakeAgent("a.ok", _return()), _ctx("a.ok"), (_event(),), now="t1"))
        rec = led.read_records()[0]
        self.assertEqual(rec["schema_version"], rm.SCHEMA_VERSION)
        self.assertEqual(rec["run_id"], "RUN1")
        self.assertEqual(rec["record_type"], "AgentRunResult")
        self.assertEqual(rec["timestamp"], "t1")

    def test_run_id_from_string_context_and_descriptor(self):
        # A bare run_id string may stand in for a context (agent_id from the descriptor).
        result = rm.run_agent_isolated(
            _FakeAgent("a.ok", _return(_finding("F1"))), "RUN9", (_event(),), now="t2")
        self.assertEqual(result.run_id, "RUN9")
        self.assertEqual(result.agent_id, "a.ok")
        self.assertEqual(result.status, "success")


# =========================================================================== #
# D2. One failed agent does NOT crash the batch (failure isolated)            #
# =========================================================================== #
class FailureIsolationTests(unittest.TestCase):
    def _batch(self):
        ok1 = _FakeAgent("a.ok1", _return(_finding("F1")))
        boom = _FakeAgent("a.boom", _raise(RuntimeError("kaboom internal detail")))
        ok2 = _FakeAgent("a.ok2", _return(_finding("F2")))
        agents = [ok1, boom, ok2]
        items = [(_ctx("a.ok1"), (_event(),)),
                 (_ctx("a.boom"), (_event(),)),
                 (_ctx("a.ok2"), (_event(),))]
        return agents, items

    def test_one_failed_agent_does_not_abort_the_batch(self):
        agents, items = self._batch()
        results = rm.run_agents_isolated(agents, items, now="t1")
        self.assertEqual(len(results), 3)  # every agent produced a result
        by_agent = {r.agent_id: r for r in results}
        self.assertEqual(by_agent["a.ok1"].status, "success")
        self.assertEqual(by_agent["a.ok2"].status, "success")  # ran AFTER the failure
        failed = by_agent["a.boom"]
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.health_status, "failed")

    def test_failed_agent_produces_a_data_gap_and_error_note(self):
        agents, items = self._batch()
        failed = {r.agent_id: r for r in rm.run_agents_isolated(agents, items, now="t1")}["a.boom"]
        self.assertTrue(failed.data_gaps)          # a data gap, not a fabricated value
        self.assertTrue(failed.errors)             # a safe error note
        self.assertIn("RuntimeError", failed.errors[0])
        self.assertEqual(failed.finding_ids, ())   # nothing fabricated

    def test_run_agent_isolated_never_propagates(self):
        # Directly: the runner swallows the exception and returns a result.
        result = rm.run_agent_isolated(
            _FakeAgent("a.boom", _raise(ValueError("some internal boom"))),
            _ctx("a.boom"), (_event(),), now="t1")
        self.assertEqual(result.status, "failed")

    def test_batch_via_mapping_keyed_by_agent(self):
        ok = _FakeAgent("a.ok", _return(_finding("F1")))
        boom = _FakeAgent("a.boom", _raise(RuntimeError("boom")))
        mapping = {ok: (_ctx("a.ok"), (_event(),)), boom: (_ctx("a.boom"), (_event(),))}
        results = rm.run_agents_isolated([ok, boom], mapping, now="t1")
        self.assertEqual({r.agent_id: r.status for r in results},
                         {"a.ok": "success", "a.boom": "failed"})

    def test_degraded_batch_still_logs_every_result_to_the_ledger(self):
        led = rm.AgentRunLedger(_tmp())
        agents, items = self._batch()
        for r in rm.run_agents_isolated(agents, items, now="t1"):
            led.append_result(r)
        self.assertEqual(len(led.results_for_run("RUN1")), 3)


# =========================================================================== #
# D3. A timeout is recorded (not a crash)                                     #
# =========================================================================== #
class TimeoutTests(unittest.TestCase):
    def test_timeout_recorded_not_raised(self):
        result = rm.run_agent_isolated(
            _FakeAgent("a.slow", _raise(TimeoutError("soft budget exceeded"))),
            _ctx("a.slow"), (_event(),), now="t1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.health_status, "failed")
        self.assertTrue(any("timeout" in e.lower() for e in result.errors))
        self.assertTrue(result.data_gaps)

    def test_timeout_in_a_batch_isolated(self):
        agents = [_FakeAgent("a.ok", _return(_finding("F1"))),
                  _FakeAgent("a.slow", _raise(TimeoutError("timed out")))]
        items = [(_ctx("a.ok"), (_event(),)), (_ctx("a.slow"), (_event(),))]
        results = {r.agent_id: r for r in rm.run_agents_isolated(agents, items, now="t1")}
        self.assertEqual(results["a.ok"].status, "success")
        self.assertEqual(results["a.slow"].status, "failed")


# =========================================================================== #
# D4. A skipped agent is recorded                                            #
# =========================================================================== #
class SkipTests(unittest.TestCase):
    def test_skipped_agent_recorded(self):
        result = rm.run_agent_isolated(
            _FakeAgent("a.skip", _raise(rm.SkipAgent("no matching events in scope"))),
            _ctx("a.skip"), (), now="t1")
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.finding_ids, ())
        self.assertTrue(result.data_gaps)          # an honest coverage gap
        self.assertEqual(result.health_status, "healthy")   # a skip is not a malfunction

    def test_skip_does_not_count_as_a_failure(self):
        agents = [_FakeAgent("a.skip", _raise(rm.SkipAgent("nothing"))),
                  _FakeAgent("a.ok", _return(_finding("F1")))]
        items = [(_ctx("a.skip"), ()), (_ctx("a.ok"), (_event(),))]
        results = {r.agent_id: r.status for r in rm.run_agents_isolated(agents, items, now="t1")}
        self.assertEqual(results, {"a.skip": "skipped", "a.ok": "success"})


# =========================================================================== #
# D5. A policy-blocked output is recorded (blocked_by_policy)                 #
# =========================================================================== #
class PolicyBlockTests(unittest.TestCase):
    def test_explicit_policy_block_recorded(self):
        result = rm.run_agent_isolated(
            _FakeAgent("a.pol", _raise(rm.PolicyBlock("forbidden output refused"))),
            _ctx("a.pol"), (_event(),), now="t1")
        self.assertEqual(result.status, "blocked_by_policy")
        self.assertEqual(result.health_status, "blocked_by_policy")
        self.assertTrue(result.data_gaps)

    def test_run_checked_forbidden_output_becomes_blocked_by_policy(self):
        # An agent that emits a non-AgentFinding -> run_checked refuses -> blocked_by_policy.
        result = rm.run_agent_isolated(
            _FakeAgent("a.pol", _return("not a finding")),
            _ctx("a.pol"), (_event(),), now="t1")
        self.assertEqual(result.status, "blocked_by_policy")

    def test_trade_field_output_becomes_blocked_by_policy(self):
        # A dataclass carrying a trade/score field -> assert_no_trade_fields -> blocked_by_policy.
        from dataclasses import dataclass as _dc

        @_dc(frozen=True)
        class _Bad:
            finding_id: str = "B1"
            buy_signal: str = "yes"

        result = rm.run_agent_isolated(
            _FakeAgent("a.pol", _return(_Bad())), _ctx("a.pol"), (_event(),), now="t1")
        self.assertEqual(result.status, "blocked_by_policy")

    def test_out_of_discipline_finding_becomes_blocked_by_policy(self):
        result = rm.run_agent_isolated(
            _FakeAgent("a.pol", _return(_finding("F1", discipline="narrative"))),
            _ctx("a.pol"), (_event(),), now="t1")
        self.assertEqual(result.status, "blocked_by_policy")

    def test_generic_valueerror_is_failed_not_blocked(self):
        # A plain internal ValueError (no policy token) is a FAILURE, not a policy block.
        result = rm.run_agent_isolated(
            _FakeAgent("a.boom", _raise(ValueError("division messed up"))),
            _ctx("a.boom"), (_event(),), now="t1")
        self.assertEqual(result.status, "failed")

    def test_blocked_result_logs_to_ledger(self):
        led = rm.AgentRunLedger(_tmp())
        result = rm.run_agent_isolated(
            _FakeAgent("a.pol", _raise(rm.PolicyBlock("refused"))),
            _ctx("a.pol"), (_event(),), now="t1")
        led.append_result(result)
        got = led.results_for_agent("a.pol")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].status, "blocked_by_policy")


# =========================================================================== #
# I. Append-only ledger; no secret; no score/trade field                      #
# =========================================================================== #
class LedgerAppendOnlyTests(unittest.TestCase):
    def test_ledger_exposes_no_mutation_method(self):
        for banned in ("update", "delete", "remove", "__setitem__", "__delitem__",
                       "overwrite", "edit", "mutate"):
            self.assertFalse(hasattr(rm.AgentRunLedger, banned),
                             "AgentRunLedger must not expose {0}".format(banned))

    def test_previously_read_line_byte_unchanged_after_more_appends(self):
        led = rm.AgentRunLedger(_tmp())
        led.append_result(rm.run_agent_isolated(
            _FakeAgent("a.ok", _return(_finding("F1"))), _ctx("a.ok"), (_event(),), now="t1"))
        with open(led.path, "rb") as fh:
            first_line = fh.readlines()[0]
        led.append_result(rm.run_agent_isolated(
            _FakeAgent("a.boom", _raise(RuntimeError("boom"))), _ctx("a.boom", run_id="RUN2"),
            (_event(),), now="t2"))
        with open(led.path, "rb") as fh:
            lines = fh.readlines()
        self.assertEqual(lines[0], first_line)
        self.assertEqual(len(lines), 2)

    def test_no_secret_survives_into_a_ledger_record(self):
        # An agent crash whose message embeds a credential-like token is redacted before storage.
        secret = "api_key=sk-supersecret-DO-NOT-LEAK-123"
        result = rm.run_agent_isolated(
            _FakeAgent("a.boom", _raise(RuntimeError("connection failed with " + secret))),
            _ctx("a.boom"), (_event(),), now="t1")
        self.assertNotIn("sk-supersecret", " ".join(result.errors))
        self.assertNotIn("sk-supersecret", " ".join(result.data_gaps))
        led = rm.AgentRunLedger(_tmp())
        led.append_result(result)
        with open(led.path, encoding="utf-8") as fh:
            blob = fh.read()
        self.assertNotIn("sk-supersecret", blob)
        self.assertNotIn("api_key=sk", blob)

    def test_credential_keyed_record_rejected_by_the_store(self):
        led = rm.AgentRunLedger(_tmp())
        with self.assertRaises(ValueError):
            led.append({"run_id": "R", "agent_id": "a", "api_key": "shhh"}, record_id="R:a")
        self.assertEqual(led.read_records(), ())

    def test_result_record_class_has_no_trade_or_score_field(self):
        for f in fields(rm.AgentRunResult):
            low = f.name.lower()
            for tok in ("buy", "sell", "hold", "order", "trade", "broker", "score", "rank",
                        "rating"):
                self.assertNotIn(tok, low, "AgentRunResult.{0}".format(f.name))
        rm.assert_no_trade_fields(rm.AgentRunResult)


# =========================================================================== #
# I. Guardrails -- AST, offline, deterministic                                #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "selenium", "scrapy", "lxml", "mechanize", "pycurl",
            "websocket", "websockets"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal"}

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _imported_modules(self, tree):
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    mods.append((node.module or "").split(".")[0])
        return mods

    def test_ledger_imports_no_network_scheduler_or_broker(self):
        tree = ast.parse(self._read(_LEDGER_PY))
        for m in self._imported_modules(tree):
            self.assertNotIn(m, self._NET, "ledger imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "ledger imports forbidden {0}".format(m))

    def test_ledger_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_LEDGER_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "ledger defines {0}".format(node.name))

    def test_ledger_source_has_no_broker_scheduler_or_order_affordance(self):
        blob = self._read(_LEDGER_PY).lower()
        for banned in ("place_order", "submit_order", "execute_trade",
                       "schedule.every", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_no_wall_clock_in_ledger(self):
        blob = self._read(_LEDGER_PY)
        for banned in ("time.time(", "datetime.now(", "datetime.utcnow(", "time.monotonic("):
            self.assertNotIn(banned, blob, "wall-clock call: {0}".format(banned))

    def test_isolating_runner_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            result = rm.run_agent_isolated(
                _FakeAgent("a.ok", _return(_finding("F1"))), _ctx("a.ok"), (_event(),), now="t1")
            led = rm.AgentRunLedger(_tmp())
            led.append_result(result)
            got = led.read_all()
        finally:
            socket.socket = real
        self.assertEqual(got, (result,))

    def test_deterministic_byte_identical_ledger(self):
        d1, d2 = _tmp(), _tmp()
        a = rm.AgentRunLedger(d1)
        b = rm.AgentRunLedger(d2)
        for led in (a, b):
            for aid in ("a.ok", "a.boom"):
                beh = _return(_finding("F1")) if aid == "a.ok" else _raise(RuntimeError("boom"))
                led.append_result(rm.run_agent_isolated(
                    _FakeAgent(aid, beh), _ctx(aid), (_event(),), now="t1"))
        with open(a.path, "rb") as fa, open(b.path, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())


if __name__ == "__main__":
    unittest.main()
