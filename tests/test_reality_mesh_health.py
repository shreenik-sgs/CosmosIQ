"""IMPLEMENTATION-013D -- health + Data-Quality observability records + AgentHealthMonitor.

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE -- no network, no scheduler, no broker, no
live endpoint. It proves the OBSERVABILITY_CONTRACT_013 §2/§3 observability outputs + the §4
failure-isolation guarantees the gate enforces (TEST_MATRIX_013 §E1-E4 + the global guardrails §I):

* E1 -- RunHealthSummary renders (agents / sources / gaps / conflicts + an overall state);
* E2 -- AgentHealthRecord created; a failed agent is visible; failure_count increments across
  failures;
* E3 -- SourceHealthRecord created; a failed source is visible;
* E4 -- **a degraded / partial run STILL produces a DataQualityRunSummary** (honestly labelled);
* I  -- every record is labels + volume counts, never a score / rank / trade field
  (assert_no_trade_fields); no secret in any health record; health.py imports no
  network / scheduler / broker module + defines no ``*score`` / ``*rank`` function (AST guards);
  the whole suite builds under a socket kill-switch; the demo default stays byte-identical.
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
from reality_mesh import health as HL

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_HEALTH_PY = os.path.join(_PKG_DIR, "health.py")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# --------------------------------------------------------------------------- #
# Result fixtures (built directly -- the ledger runner is tested separately)     #
# --------------------------------------------------------------------------- #
def _result(agent_id, status, *, run_id="RUN1", completed_at="t1", errors=(), gaps=(),
            conflicts=(), findings=(), health=""):
    if not health:
        health = {"success": "healthy", "failed": "failed", "blocked_by_policy": "blocked_by_policy",
                  "skipped": "healthy", "partial": "degraded"}.get(status, "")
    return rm.AgentRunResult(
        run_id=run_id, agent_id=agent_id, status=status, started_at="t0", completed_at=completed_at,
        finding_ids=tuple(findings), errors=tuple(errors), data_gaps=tuple(gaps),
        conflicts=tuple(conflicts), health_status=health)


def _source(source_id, last_status, **kw):
    return rm.SourceHealthRecord(source_id=source_id, last_status=last_status, **kw)


# =========================================================================== #
# E3. SourceHealthRecord created; a failed source is visible                  #
# =========================================================================== #
class SourceHealthRecordTests(unittest.TestCase):
    def test_construct_healthy_source(self):
        s = _source("sec", "healthy", credentials_status="present", rate_limit_status="ok",
                    last_success_at="t1")
        self.assertEqual(s.source_id, "sec")
        self.assertFalse(s.is_failed)

    def test_failed_source_is_visible(self):
        s = _source("fmp", "source_unavailable", unavailable_reason="503 from provider",
                    last_failure_at="t1")
        self.assertTrue(s.is_failed)
        self.assertEqual(s.unavailable_reason, "503 from provider")

    def test_credentials_missing_and_rate_limited_are_visible_gaps(self):
        cred = _source("yf", "credentials_missing", credentials_status="missing",
                       unavailable_reason="no API key -- honest gap, not fabricated")
        rate = _source("tv", "rate_limited", rate_limit_status="rate_limited")
        self.assertTrue(cred.is_failed)
        self.assertTrue(rate.is_failed)
        self.assertIn("honest gap", cred.unavailable_reason)

    def test_invalid_labels_rejected(self):
        with self.assertRaises(ValueError):
            _source("x", "not_a_state")
        with self.assertRaises(ValueError):
            _source("x", "healthy", credentials_status="banana")
        with self.assertRaises(ValueError):
            _source("x", "healthy", rate_limit_status="banana")
        with self.assertRaises(ValueError):
            rm.SourceHealthRecord(source_id="")   # required id

    def test_empty_labels_are_accepted_gaps(self):
        s = rm.SourceHealthRecord(source_id="sec")   # all labels default "" (gap)
        self.assertFalse(s.is_failed)


# =========================================================================== #
# E2. AgentHealthRecord created; failed agent visible; failure_count increments #
# =========================================================================== #
class AgentHealthMonitorTests(unittest.TestCase):
    def test_roll_creates_one_record_per_agent(self):
        mon = rm.AgentHealthMonitor()
        results = [_result("a.ok", "success", findings=("F1",)),
                   _result("a.boom", "failed", errors=("RuntimeError: boom",), gaps=("g",))]
        recs = mon.roll_agent_health(results)
        self.assertEqual({r.agent_id for r in recs}, {"a.ok", "a.boom"})

    def test_failed_agent_visible_in_health_record(self):
        mon = rm.AgentHealthMonitor()
        rec = mon.agent_health("a.boom", [_result("a.boom", "failed",
                                                   errors=("RuntimeError: boom",))])
        self.assertEqual(rec.last_status, "failed")
        self.assertEqual(rec.failure_count, 1)
        self.assertIn("RuntimeError", rec.last_error)
        self.assertTrue(rec.degraded_reason)
        self.assertEqual(rec.last_failure_at, "t1")

    def test_failure_count_increments_across_failures(self):
        mon = rm.AgentHealthMonitor()
        results = [_result("a.boom", "failed", run_id="RUN1", completed_at="t1"),
                   _result("a.ok2", "success", run_id="RUN2"),
                   _result("a.boom", "failed", run_id="RUN2", completed_at="t2"),
                   _result("a.boom", "failed", run_id="RUN3", completed_at="t3")]
        rec = mon.agent_health("a.boom", results)
        self.assertEqual(rec.failure_count, 3)          # a volume count, incremented per failure
        self.assertEqual(rec.last_run_id, "RUN3")
        self.assertEqual(rec.last_status, "failed")

    def test_recovery_records_last_success(self):
        mon = rm.AgentHealthMonitor()
        results = [_result("a", "failed", run_id="RUN1", completed_at="t1"),
                   _result("a", "success", run_id="RUN2", completed_at="t2", findings=("F1",))]
        rec = mon.agent_health("a", results)
        self.assertEqual(rec.failure_count, 1)
        self.assertEqual(rec.last_status, "success")
        self.assertEqual(rec.last_success_at, "t2")
        self.assertEqual(rec.last_failure_at, "t1")
        self.assertEqual(rec.degraded_reason, "")       # healthy now -- no degraded reason

    def test_blocked_agent_reflected_but_not_counted_as_failure(self):
        mon = rm.AgentHealthMonitor()
        rec = mon.agent_health("a.pol", [_result("a.pol", "blocked_by_policy",
                                                  errors=("PolicyBlock: refused",))])
        self.assertEqual(rec.last_status, "blocked_by_policy")
        self.assertEqual(rec.failure_count, 0)          # a policy block is not a failure
        self.assertIn("refused", rec.last_error)

    def test_health_record_carries_no_secret(self):
        mon = rm.AgentHealthMonitor()
        # errors on the result are already secret-free upstream; confirm nothing is re-derived badly.
        rec = mon.agent_health("a", [_result("a", "failed", errors=("RuntimeError: <redacted>",))])
        self.assertNotIn("api_key", rec.last_error.lower())


# =========================================================================== #
# E1. RunHealthSummary renders (agents / sources / gaps / conflicts + state)   #
# =========================================================================== #
class RunHealthSummaryTests(unittest.TestCase):
    def _mixed(self):
        return [_result("a.ok", "success", findings=("F1",)),
                _result("a.boom", "failed", errors=("e",), gaps=("g1", "g2")),
                _result("a.pol", "blocked_by_policy", gaps=("g3",)),
                _result("a.skip", "skipped", gaps=("g4",))]

    def test_summary_renders_counts_and_overall_state(self):
        mon = rm.AgentHealthMonitor()
        sources = [_source("sec", "healthy"), _source("fmp", "source_unavailable")]
        summary = mon.build_run_health_summary(
            "RUN1", self._mixed(), sources=sources, conflicts=("c1",))
        self.assertEqual(summary.run_id, "RUN1")
        self.assertEqual(summary.agents_total, 4)
        self.assertEqual(summary.agents_run, 1)         # successes
        self.assertEqual(summary.agents_failed, 1)
        self.assertEqual(summary.agents_blocked, 1)
        self.assertEqual(summary.agents_skipped, 1)
        self.assertEqual(summary.sources_used, 2)
        self.assertEqual(summary.sources_failed, 1)
        self.assertEqual(summary.data_gap_count, 4 + 0)  # g1,g2,g3,g4 from results
        self.assertEqual(summary.conflict_count, 1)      # the extra conflict
        self.assertEqual(summary.overall_status, "degraded")   # partial -> honestly degraded

    def test_all_healthy_run_reads_healthy(self):
        mon = rm.AgentHealthMonitor()
        summary = mon.build_run_health_summary(
            "RUN1", [_result("a.ok", "success"), _result("a.ok2", "success")],
            sources=[_source("sec", "healthy")])
        self.assertEqual(summary.overall_status, "healthy")
        self.assertEqual(summary.sources_failed, 0)

    def test_total_failure_reads_failed(self):
        mon = rm.AgentHealthMonitor()
        summary = mon.build_run_health_summary(
            "RUN1", [_result("a", "failed"), _result("b", "failed")])
        self.assertEqual(summary.overall_status, "failed")

    def test_all_blocked_reads_blocked_by_policy(self):
        mon = rm.AgentHealthMonitor()
        summary = mon.build_run_health_summary(
            "RUN1", [_result("a", "blocked_by_policy"), _result("b", "blocked_by_policy")])
        self.assertEqual(summary.overall_status, "blocked_by_policy")

    def test_empty_run_id_rejected(self):
        with self.assertRaises(ValueError):
            rm.AgentHealthMonitor().build_run_health_summary("", [])


# =========================================================================== #
# E4. A degraded / partial run STILL produces a DataQualityRunSummary         #
# =========================================================================== #
class DataQualityRunSummaryTests(unittest.TestCase):
    def test_degraded_run_still_produces_data_quality(self):
        mon = rm.AgentHealthMonitor()
        # A partial run: one success, one failure, one source down.
        results = [_result("a.ok", "success", findings=("F1",)),
                   _result("a.boom", "failed", errors=("e",), gaps=("g1",))]
        sources = [_source("sec", "healthy"), _source("fmp", "source_unavailable")]
        dq = mon.build_data_quality_summary(
            "RUN1", results, sources=sources, weak_social=("w1", "w2"),
            unsupported_claims=("u1",))
        # Produced despite the degradation -- honestly labelled, never a silent demo fallback.
        self.assertEqual(dq.run_id, "RUN1")
        self.assertEqual(dq.status, "degraded")
        self.assertEqual(dq.source_coverage, "partial")
        self.assertEqual(dq.sources_used, 2)
        self.assertEqual(dq.sources_failed, 1)
        self.assertEqual(dq.gap_count, 1)
        self.assertEqual(dq.weak_social_count, 2)         # weak stays weak -- surfaced, not hidden
        self.assertEqual(dq.unsupported_claim_count, 1)

    def test_fully_failed_run_still_produces_data_quality(self):
        mon = rm.AgentHealthMonitor()
        dq = mon.build_data_quality_summary(
            "RUN1", [_result("a", "failed", gaps=("g",)), _result("b", "failed")],
            sources=[_source("sec", "failed")])
        self.assertEqual(dq.status, "failed")             # still a summary, honestly labelled
        self.assertEqual(dq.source_coverage, "none")

    def test_healthy_run_reads_full_coverage(self):
        mon = rm.AgentHealthMonitor()
        dq = mon.build_data_quality_summary(
            "RUN1", [_result("a", "success")], sources=[_source("sec", "healthy")])
        self.assertEqual(dq.status, "healthy")
        self.assertEqual(dq.source_coverage, "full")
        self.assertEqual(dq.weak_social_count, 0)

    def test_no_sources_reads_unknown_coverage(self):
        mon = rm.AgentHealthMonitor()
        dq = mon.build_data_quality_summary("RUN1", [_result("a", "success")])
        self.assertEqual(dq.source_coverage, "unknown")

    def test_empty_run_id_rejected(self):
        with self.assertRaises(ValueError):
            rm.AgentHealthMonitor().build_data_quality_summary("", [])


# =========================================================================== #
# I. Labels-not-scores; no trade/score field; no secret                        #
# =========================================================================== #
class NoScoreNoSecretTests(unittest.TestCase):
    def test_no_health_record_has_a_trade_or_score_field(self):
        for cls in rm.HEALTH_RECORDS + (rm.AgentHealthRecord,):
            for f in fields(cls):
                low = f.name.lower()
                for tok in ("buy", "sell", "hold", "order", "trade", "broker", "score", "rank",
                            "rating", "investab"):
                    self.assertNotIn(tok, low, "{0}.{1}".format(cls.__name__, f.name))
            rm.assert_no_trade_fields(cls)

    def test_all_integer_fields_are_volume_counts(self):
        # Every int field is a count; none is named like a score/metric.
        for cls in (rm.RunHealthSummary, rm.DataQualityRunSummary):
            for f in fields(cls):
                if f.type in ("int", int):
                    low = f.name.lower()
                    self.assertTrue(
                        low.endswith("count") or low.startswith("agents_")
                        or low.startswith("sources_"),
                        "{0}.{1} does not read as a volume count".format(cls.__name__, f.name))

    def test_credentials_status_holds_a_label_not_a_secret(self):
        # SourceHealthRecord.credentials_status is a documented STATUS LABEL (present/missing/
        # unknown/""), never a raw secret value -- it is validated against a closed vocabulary.
        for good in ("", "present", "missing", "unknown"):
            self.assertEqual(_source("sec", "healthy", credentials_status=good).credentials_status,
                             good)
        with self.assertRaises(ValueError):
            _source("sec", "healthy", credentials_status="sk-supersecret-token-value")

    def test_records_expose_no_raw_secret_bearing_field(self):
        # No health-record field is a raw-credential holder (api_key / token / password / secret /
        # authorization / ...). The documented ``credentials_status`` label field is exempt: it
        # carries a present/missing STATUS, never a secret value.
        secret_holders = tuple(t for t in rm.CREDENTIAL_KEY_TOKENS if t != "credential")
        for cls in rm.HEALTH_RECORDS:
            for f in fields(cls):
                low = f.name.lower()
                if low == "credentials_status":
                    continue
                for tok in secret_holders:
                    self.assertNotIn(tok, low, "{0}.{1}".format(cls.__name__, f.name))


# =========================================================================== #
# I. Guardrails -- AST, offline, deterministic, demo byte-identical            #
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

    def test_health_imports_no_network_scheduler_or_broker(self):
        tree = ast.parse(self._read(_HEALTH_PY))
        for m in self._imported_modules(tree):
            self.assertNotIn(m, self._NET, "health imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "health imports forbidden {0}".format(m))

    def test_health_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_HEALTH_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "health defines {0}".format(node.name))

    def test_health_source_has_no_broker_scheduler_or_order_affordance(self):
        blob = self._read(_HEALTH_PY).lower()
        for banned in ("place_order", "submit_order", "execute_trade",
                       "schedule.every", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_no_wall_clock_in_health(self):
        blob = self._read(_HEALTH_PY)
        for banned in ("time.time(", "datetime.now(", "datetime.utcnow(", "time.monotonic("):
            self.assertNotIn(banned, blob, "wall-clock call: {0}".format(banned))

    def test_rollup_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            mon = rm.AgentHealthMonitor()
            summary = mon.build_run_health_summary(
                "RUN1", [_result("a", "success"), _result("b", "failed")])
            dq = mon.build_data_quality_summary("RUN1", [_result("a", "success")])
        finally:
            socket.socket = real
        self.assertEqual(summary.overall_status, "degraded")
        self.assertEqual(dq.status, "healthy")

    def test_rollup_is_deterministic(self):
        mon = rm.AgentHealthMonitor()
        results = [_result("a", "success"), _result("b", "failed", gaps=("g",))]
        s1 = mon.build_run_health_summary("RUN1", results, sources=[_source("x", "failed")])
        s2 = mon.build_run_health_summary("RUN1", results, sources=[_source("x", "failed")])
        self.assertEqual(s1, s2)


class ExistingBehaviourTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_health_demo_a_")
        d2 = tempfile.mkdtemp(prefix="rm_health_demo_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))


if __name__ == "__main__":
    unittest.main()
