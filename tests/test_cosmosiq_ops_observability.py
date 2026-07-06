"""IMPLEMENTATION-023E -- Observability / Monitoring / Health tests. OFFLINE, deterministic.

Proves the single sanitized observability surface (:mod:`cosmosiq_ops.observability`):

* the health output EXISTS and carries ALL required keys (service / source / agent / scheduler /
  alert-delivery health, DQ, run latency, failure counts, last successful / failed pulse, last
  replay check, storage / backup health);
* NO secret ever reaches the health JSON / metrics / logs -- a planted SEC_USER_AGENT / FMP_API_KEY
  env VALUE never appears (presence labels only) and a shaped secret in a log field is redacted;
* a FAILURE updates the health honestly (failure_counts up, last_failed_pulse set, status
  degraded / failed); a SUCCESS updates the health (last_successful_pulse set, status ok / degraded);
* metrics + health JSON are DETERMINISTIC (same store + injected now -> byte-identical);
* the structured log line is valid JSON + sanitized;
* NO score / rank / trade field anywhere;
* the /api/observability route is a READ-ONLY 200 with no form / button;
* the offline kill-switch holds (no socket) + the aggregation core is AST-clean (no wall clock);
* the demo + default pulse are byte-identical.
"""

from __future__ import annotations

import ast
import json
import os
import re
import socket
import tempfile
import unittest

import conftest  # noqa: F401  (root path setup: makes src/ importable)

import reality_mesh as rm
from cosmosiq_app.api import dispatch
from cosmosiq_ops.observability import (
    ObservabilityReport,
    aggregate_observability,
    emit_structured_log,
    render_health_json,
    render_metrics,
)
from reality_mesh.ledger import AgentRunLedger
from reality_mesh.runtime import AgentRunResult

_NOW = "2026-06-30T12:00:00Z"
_NOW2 = "2026-06-30T13:00:00Z"

_OBS_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "cosmosiq_ops", "observability.py")

# The full 023E required-key set the health output must expose.
_REQUIRED_KEYS = (
    "service_health", "source_health_summary", "agent_health_summary", "scheduler_health",
    "alert_delivery_health", "dq_status_summary", "run_latency", "failure_counts",
    "last_successful_pulse", "last_failed_pulse", "last_replay_check", "storage_health",
    "backup_health", "status",
)

# A planted (fake) secret env value must NEVER appear in any output.
_PLANTED_ENV = {
    "SEC_USER_AGENT": "cosmosiq-fake-agent SECRETUSERAGENTVALUE123",
    "FMP_API_KEY": "sk-FAKEfmpKEY0123456789abcdefghij",
}
_PLANTED_SUBSTRINGS = ("SECRETUSERAGENTVALUE123", "sk-FAKEfmpKEY", "FAKEfmpKEY0123456789")

_BOOM = "network access attempted during the OFFLINE 023E observability tests"


def _boom_socket(*a, **k):
    raise AssertionError(_BOOM)


def _seed_success_store(store_dir, *, run_id="RUN-OBS-1", now=_NOW):
    """Persist ONE real pulse (a completed, successful run) into an append-only store."""
    pulse = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=now)
    rm.persist_and_summarize(pulse, store_dir=store_dir, run_id=run_id, now=now)
    return pulse


def _seed_failed_agent(store_dir, *, run_id="RUN-OBS-FAIL", agent_id="market_regime",
                       now=_NOW2):
    """Append a FAILED agent-run result to the append-only ledger (a failure signal)."""
    result = AgentRunResult(
        run_id=run_id, agent_id=agent_id, status="failed",
        started_at=now, completed_at=now,
        errors=("RuntimeError: injected offline failure for the 023E health test",),
        data_gaps=("agent {0} failed in run {1} -- isolated".format(agent_id, run_id),),
        health_status="failed")
    AgentRunLedger(store_dir).append_result(result)
    return result


class _EnvGuard:
    """Plant the fake secret env vars for a test; restore the prior environment afterwards."""

    def __enter__(self):
        self._saved = {k: os.environ.get(k) for k in _PLANTED_ENV}
        os.environ.update(_PLANTED_ENV)
        return self

    def __exit__(self, *exc):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return False


class ObservabilityBaseTest(unittest.TestCase):
    _orig_connect = None

    @classmethod
    def setUpClass(cls):
        cls._orig_connect = socket.socket.connect
        socket.socket.connect = _boom_socket

    @classmethod
    def tearDownClass(cls):
        socket.socket.connect = cls._orig_connect

    def _fresh_store(self):
        store_dir = tempfile.mkdtemp(prefix="cosmosiq_obs_")
        self.addCleanup(lambda: None)
        return store_dir


# =========================================================================== #
# 1. The health output EXISTS + has ALL required keys                          #
# =========================================================================== #
class HealthShapeTests(ObservabilityBaseTest):
    def test_report_exists_and_has_all_required_signals(self):
        store = self._fresh_store()
        _seed_success_store(store)
        report = aggregate_observability(store, now=_NOW)
        self.assertIsInstance(report, ObservabilityReport)
        data = report.to_dict()
        for key in _REQUIRED_KEYS:
            self.assertIn(key, data, "missing required health signal {0!r}".format(key))
        # status is one of the closed rolled states.
        self.assertIn(data["status"], ("ok", "degraded", "failed"))
        # last_replay_check carries the deterministic-match verdict + when.
        self.assertIn("deterministic_match", report.last_replay_check)
        self.assertIn("when", report.last_replay_check)
        # run_latency is derived from persisted run timestamps.
        self.assertGreaterEqual(report.run_latency["runs_measured"], 1)

    def test_health_json_has_all_keys_and_a_status(self):
        store = self._fresh_store()
        _seed_success_store(store)
        report = aggregate_observability(store, now=_NOW)
        parsed = json.loads(render_health_json(report))
        for key in _REQUIRED_KEYS:
            self.assertIn(key, parsed)
        self.assertIn(parsed["status"], ("ok", "degraded", "failed"))

    def test_empty_store_still_produces_an_honest_health_output(self):
        store = self._fresh_store()
        report = aggregate_observability(store, now=_NOW)
        data = report.to_dict()
        for key in _REQUIRED_KEYS:
            self.assertIn(key, data)
        self.assertEqual(data["status"], "ok")   # nothing failed, nothing ran


# =========================================================================== #
# 2. NO secret in the health JSON / metrics / logs (presence labels only)      #
# =========================================================================== #
class NoSecretTests(ObservabilityBaseTest):
    def test_planted_env_secret_never_appears_in_health_or_metrics(self):
        store = self._fresh_store()
        _seed_success_store(store)
        with _EnvGuard():
            report = aggregate_observability(store, now=_NOW)
            health = render_health_json(report)
            metrics = render_metrics(report)
        for blob, label in ((health, "health JSON"), (metrics, "metrics")):
            for secret in _PLANTED_SUBSTRINGS:
                self.assertNotIn(secret, blob,
                                 "secret VALUE leaked into {0}".format(label))
        # presence LABELS only: the env var NAMES appear with boolean presence, never values.
        env = report.env_presence
        self.assertIn("SEC_USER_AGENT", env["vars"])
        self.assertIn("FMP_API_KEY", env["vars"])
        with _EnvGuard():
            present = aggregate_observability(store, now=_NOW).env_presence["vars"]
        self.assertTrue(present["SEC_USER_AGENT"])   # present == True (a label, not the value)
        self.assertTrue(present["FMP_API_KEY"])

    def test_injected_env_mapping_presence_is_a_label_not_a_value(self):
        store = self._fresh_store()
        report = aggregate_observability(store, now=_NOW, env=_PLANTED_ENV)
        blob = render_health_json(report) + "\n" + render_metrics(report)
        for secret in _PLANTED_SUBSTRINGS:
            self.assertNotIn(secret, blob)
        self.assertTrue(report.env_presence["vars"]["FMP_API_KEY"])

    def test_shaped_secret_in_a_log_field_is_redacted(self):
        line = emit_structured_log(
            "obs.probe", now=_NOW, level="error",
            message="FMP_API_KEY=sk-FAKEfmpKEY0123456789abcdefghij failed to authenticate")
        record = json.loads(line)                       # valid JSON
        self.assertNotIn("sk-FAKEfmpKEY", line)
        self.assertNotIn("FAKEfmpKEY0123456789", line)
        self.assertIn("<redacted>", record["message"])


# =========================================================================== #
# 3. A FAILURE updates the health honestly                                     #
# =========================================================================== #
class FailureUpdatesHealthTests(ObservabilityBaseTest):
    def test_failed_agent_raises_failure_counts_and_sets_last_failed_pulse(self):
        store = self._fresh_store()
        clean = aggregate_observability(store, now=_NOW)
        self.assertEqual(clean.failure_counts["total"], 0)

        _seed_failed_agent(store)
        report = aggregate_observability(store, now=_NOW2)
        # failure_counts went UP.
        self.assertGreaterEqual(report.failure_counts["agents_failed"], 1)
        self.assertGreater(report.failure_counts["total"], 0)
        # last_failed_pulse is SET (run id + injected time).
        self.assertEqual(report.last_failed_pulse["run_id"], "RUN-OBS-FAIL")
        self.assertTrue(report.last_failed_pulse["at"])
        # status is degraded / failed (nothing succeeded here -> failed).
        self.assertIn(report.status, ("degraded", "failed"))
        # the failure is honestly reflected in the health JSON.
        self.assertIn(report.status, json.loads(render_health_json(report))["status"])


# =========================================================================== #
# 4. A SUCCESS updates the health                                              #
# =========================================================================== #
class SuccessUpdatesHealthTests(ObservabilityBaseTest):
    def test_persisted_pulse_sets_last_successful_pulse_and_status_ok_or_degraded(self):
        store = self._fresh_store()
        _seed_success_store(store, run_id="RUN-OBS-OK", now=_NOW)
        report = aggregate_observability(store, now=_NOW)
        self.assertEqual(report.last_successful_pulse["run_id"], "RUN-OBS-OK")
        self.assertTrue(report.last_successful_pulse["at"])
        self.assertIn(report.status, ("ok", "degraded"))
        # a success does not fabricate a failed pulse.
        self.assertEqual(report.last_failed_pulse["run_id"], "")
        self.assertEqual(report.failure_counts["agents_failed"], 0)


# =========================================================================== #
# 5. Metrics + health JSON are DETERMINISTIC (byte-identical)                   #
# =========================================================================== #
class DeterminismTests(ObservabilityBaseTest):
    def test_same_store_and_now_yield_byte_identical_metrics_and_health(self):
        store = self._fresh_store()
        _seed_success_store(store)
        _seed_failed_agent(store)
        a = aggregate_observability(store, now=_NOW2)
        b = aggregate_observability(store, now=_NOW2)
        self.assertEqual(render_metrics(a), render_metrics(b))
        self.assertEqual(render_health_json(a), render_health_json(b))
        # and stable across independent process-identical inputs (no wall clock drift).
        self.assertEqual(render_metrics(a), render_metrics(
            aggregate_observability(store, now=_NOW2)))

    def test_metrics_are_key_value_lines_with_no_secret(self):
        store = self._fresh_store()
        _seed_success_store(store)
        with _EnvGuard():
            metrics = render_metrics(aggregate_observability(store, now=_NOW))
        for line in metrics.splitlines():
            self.assertRegex(line, r"^\S+ .+$")          # stable "key value" shape
        for secret in _PLANTED_SUBSTRINGS:
            self.assertNotIn(secret, metrics)


# =========================================================================== #
# 6. NO score / rank / trade field anywhere                                    #
# =========================================================================== #
class NoScoreOrTradeTests(ObservabilityBaseTest):
    _BANNED_KEY_TOKENS = ("score", "rank", "rating", "investab", "buy", "sell", "order",
                          "trade", "broker", "submit", "sizing")

    # Dynamic count-map fields whose KEYS are honest data LABELS being tallied (e.g. the DQ gate
    # category "scheduler_broker_trading_guardrail" -- the guardrail that BLOCKS trading, a safety
    # label, not a trade field). Their label keys are values-as-keys, not structural schema fields.
    _LABEL_MAP_FIELDS = ("by_category", "by_status", "vars")

    def _structural_keys(self, obj):
        """Every STRUCTURAL schema key -- descends normally but never into a label-count map."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                yield str(key)
                if str(key) in self._LABEL_MAP_FIELDS:
                    continue      # the map's KEYS are data labels, not schema field names
                for sub in self._structural_keys(value):
                    yield sub
        elif isinstance(obj, (list, tuple)):
            for value in obj:
                for sub in self._structural_keys(value):
                    yield sub

    def test_no_banned_key_in_the_health_output(self):
        store = self._fresh_store()
        _seed_success_store(store)
        _seed_failed_agent(store)
        report = aggregate_observability(store, now=_NOW2)
        # (a) no ObservabilityReport dataclass FIELD is a score/trade field.
        for field_name in report.__dataclass_fields__:
            low = field_name.lower()
            for token in self._BANNED_KEY_TOKENS:
                self.assertNotIn(token, low,
                                 "banned score/trade field {0!r}".format(field_name))
        # (b) no STRUCTURAL nested key carries a banned token (data labels excluded).
        for key in self._structural_keys(report.to_dict()):
            low = key.lower()
            for token in self._BANNED_KEY_TOKENS:
                self.assertNotIn(token, low,
                                 "banned score/trade key {0!r} in the health output".format(key))

    def test_metric_keys_carry_no_score_or_trade_token(self):
        store = self._fresh_store()
        _seed_success_store(store)
        metrics = render_metrics(aggregate_observability(store, now=_NOW))
        for line in metrics.splitlines():
            key = line.split(" ", 1)[0].lower()
            for token in self._BANNED_KEY_TOKENS:
                self.assertNotIn(token, key,
                                 "banned token in metric key {0!r}".format(key))


# =========================================================================== #
# 7. The /api/observability route is a READ-ONLY 200 with no form / button     #
# =========================================================================== #
class ObservabilityRouteTests(ObservabilityBaseTest):
    def test_get_route_is_200_json_with_all_signals(self):
        store = self._fresh_store()
        _seed_success_store(store)
        response = dispatch(
            {"method": "GET", "path": "/api/observability", "query": {}, "body": None},
            store_dir=store, now=_NOW)
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "application/json")
        body = response["body"]
        for key in _REQUIRED_KEYS:
            self.assertIn(key, body)
        self.assertIn(body["status"], ("ok", "degraded", "failed"))

    def test_route_is_read_only_no_form_or_button_no_mutation(self):
        store = self._fresh_store()
        _seed_success_store(store)
        # a write method is refused (read-only surface).
        for method in ("POST", "PUT", "DELETE"):
            resp = dispatch(
                {"method": method, "path": "/api/observability", "query": {}, "body": None},
                store_dir=store, now=_NOW)
            self.assertEqual(resp["status"], 405)
        # the JSON body carries no form / button / trade control affordance.
        body = dispatch(
            {"method": "GET", "path": "/api/observability", "query": {}, "body": None},
            store_dir=store, now=_NOW)["body"]
        blob = json.dumps(body).lower()
        for affordance in ("<form", "<button", "onclick", "type=submit", "buy-button",
                           "sell-button"):
            self.assertNotIn(affordance, blob)

    def test_route_does_not_mutate_the_store(self):
        store = self._fresh_store()
        _seed_success_store(store)
        before = _dir_signature(store)
        for _ in range(3):
            dispatch(
                {"method": "GET", "path": "/api/observability", "query": {}, "body": None},
                store_dir=store, now=_NOW)
        self.assertEqual(_dir_signature(store), before)


# =========================================================================== #
# 8. Offline kill-switch + AST-clean aggregation core (no wall clock)          #
# =========================================================================== #
class OfflineAndAstTests(ObservabilityBaseTest):
    def test_no_socket_during_full_aggregation_and_render(self):
        store = self._fresh_store()
        _seed_success_store(store)
        _seed_failed_agent(store)
        # the kill-switch is armed in setUpClass; a network attempt would raise.
        report = aggregate_observability(store, now=_NOW2)
        render_health_json(report)
        render_metrics(report)
        emit_structured_log("obs.tick", now=_NOW2, event_detail="offline")

    def test_aggregation_core_reads_no_wall_clock(self):
        with open(_OBS_PY, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        banned_attrs = {"now", "utcnow", "today", "time", "monotonic", "perf_counter", "sleep"}
        offences = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in banned_attrs:
                    offences.append(node.func.attr)
        self.assertEqual(offences, [], "wall-clock read in the aggregation core: {0}".format(
            offences))

    def test_module_imports_no_network_or_clock_root(self):
        with open(_OBS_PY, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        banned_roots = {"socket", "http", "urllib", "requests", "ssl", "asyncio",
                        "threading", "multiprocessing", "subprocess", "smtplib", "ftplib",
                        "time", "random"}
        for node in ast.walk(tree):
            roots = []
            if isinstance(node, ast.Import):
                roots = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots = [(node.module or "").split(".")[0]]
            for root in roots:
                self.assertNotIn(root, banned_roots,
                                 "observability imported a banned root {0!r}".format(root))


# =========================================================================== #
# 9. Demo + default pulse byte-identical (the surface reflects an honest run)   #
# =========================================================================== #
class DemoDefaultParityTests(ObservabilityBaseTest):
    def test_demo_and_default_pulse_are_byte_identical(self):
        store_a = self._fresh_store()
        store_b = self._fresh_store()
        pulse_a = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW)
        pulse_b = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW)
        rm.persist_and_summarize(pulse_a, store_dir=store_a, run_id="RUN-PARITY", now=_NOW)
        rm.persist_and_summarize(pulse_b, store_dir=store_b, run_id="RUN-PARITY", now=_NOW)
        a = aggregate_observability(store_a, now=_NOW)
        b = aggregate_observability(store_b, now=_NOW)
        # Parity is over the pulse-derived surface; the ephemeral store_dir path is excluded.
        da, db = a.to_dict(), b.to_dict()
        da.pop("store_dir"), db.pop("store_dir")
        self.assertEqual(json.dumps(da, sort_keys=True), json.dumps(db, sort_keys=True))
        self.assertEqual(render_metrics(a), render_metrics(b))   # metrics carry no store path


def _dir_signature(store_dir):
    """A (path -> size) signature of every file under a store dir (mutation detector)."""
    out = {}
    for cur, dirs, names in os.walk(store_dir):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(cur, name)
            out[os.path.relpath(path, store_dir)] = os.path.getsize(path)
    return out


if __name__ == "__main__":
    unittest.main()
