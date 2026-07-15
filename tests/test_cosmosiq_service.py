"""IMPLEMENTATION-020C -- the supervised operator service wrapper (OFFLINE).

Proves the 020C slice: a supervised, always-on-CAPABLE local operator service whose PURE core
CALLS the accepted 015B one-tick orchestrator (never bypasses it), driven here by an injected
``now`` and a single ``run_once`` per assertion -- the real supervised loop is NEVER run.

The 020C acceptance list, in order:

* the service starts in the OFF / MANUAL-safe posture; ``PRODUCTION_24X7`` is NOT the default;
* the single-instance lock prevents a duplicate service (a 2nd acquire while held is refused;
  a stale lock is reclaimable);
* ``run_once`` CALLS the scheduler / orchestrator -- a run persists through the FULL 013 chain
  (stores populated + the DQ gate ran + the run is replayable) -- it does NOT bypass DQ / replay;
* pause prevents scheduled ticks (a paused ``run_once`` runs nothing); resume allows them again;
* a failing tick updates health (``consecutive_failures``++, ``last_error_class`` +
  ``last_error_message_sanitized`` set, ``last_tick_failed_at``) + writes a structured, sanitized
  log line + applies deterministic backoff (escalating across repeated failures);
* a success updates health (``last_successful_run_id``, ``last_tick_completed_at``);
* logs are structured (parseable JSON) and sanitized -- a planted secret-shaped value never
  appears in the log or the health file;
* NO network on import; the CORE has no top-level net / loop (AST) -- only ``__main__`` has the
  loop + sleep; importing the package starts nothing;
* demo default + default pulse remain byte-identical.

Entirely OFFLINE and deterministic; a socket kill-switch guards the whole module.
"""

from __future__ import annotations

import ast
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import cosmosiq_service as CS
from cosmosiq_service import (
    DEFAULT_MODE,
    LockError,
    ServiceConfig,
    ServiceHealth,
    ServiceMode,
    acquire_lock,
    continuous_activation_gate,
    continuous_shadow_allowed,
    load_health,
    pause,
    read_lock,
    requires_activation_gate,
    resume,
    run_once,
    sanitize,
    service_status,
)
from reality_mesh import stores as S
from reality_mesh.ledger import AgentRunLedger
from reality_mesh.orchestrator import Subscription
from reality_mesh.replay import ReplayHarness
from reality_mesh.runtime import ReplayRequest

_PKG_DIR = os.path.join(_SRC, "cosmosiq_service")
_SERVICE_PY = os.path.join(_PKG_DIR, "service.py")
_INIT_PY = os.path.join(_PKG_DIR, "__init__.py")
_MAIN_PY = os.path.join(_PKG_DIR, "__main__.py")

# A Monday, 15:00 UTC -- inside the default 14:30-21:00 UTC session.
_NOW = "2026-06-29T15:00:00Z"

# A planted secret-shaped value used to prove nothing secret ever reaches a log / health file.
_PLANTED_SECRET = "sk-PLANTEDSECRETdoNotLeak0001"

_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "asyncio", "threading", "multiprocessing", "subprocess",
                        "smtplib", "ftplib", "socketserver", "time", "signal", "select")
_BANNED_CALL_NAMES = ("sleep", "run_forever", "serve_forever", "Thread", "Timer", "Process",
                      "fork", "spawn")
_WALL_CLOCK_TOKENS = ("time.time(", "datetime.now(", "datetime.utcnow(", "utcnow(",
                      "perf_counter(", "monotonic(")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline 020C service suite")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _sub(sid="sub.core", policy_ids=("cadence.news_filings",), adapter_refs=(), watchlist=("IREN", "NVDA")):
    return Subscription(
        subscription_id=sid, watchlist=tuple(watchlist), themes=("physical_ai", "robotics"),
        policy_ids=tuple(policy_ids), adapter_refs=tuple(adapter_refs))


def _config(store_dir, *, mode=ServiceMode.MANUAL, subscriptions=None, **kw):
    return ServiceConfig(
        mode=mode, store_dir=store_dir,
        subscriptions=(subscriptions if subscriptions is not None else (_sub(),)), **kw)


# =========================================================================== #
# 1. Modes -- default OFF / MANUAL-safe; PRODUCTION_24X7 is NOT the default    #
# =========================================================================== #
class ModeTests(unittest.TestCase):
    def test_default_mode_is_off_not_production(self):
        self.assertIs(DEFAULT_MODE, ServiceMode.OFF)
        self.assertIsNot(DEFAULT_MODE, ServiceMode.PRODUCTION_24X7)
        # a config with no mode given defaults OFF (the safe posture)
        with tempfile.TemporaryDirectory() as d:
            self.assertIs(ServiceConfig(store_dir=d).mode, ServiceMode.OFF)

    def test_all_four_modes_exist(self):
        self.assertEqual(
            {m.value for m in ServiceMode},
            {"off", "manual", "shadow_24x7", "production_24x7"})

    def test_production_continuous_requires_the_020f_gate(self):
        self.assertTrue(requires_activation_gate(ServiceMode.PRODUCTION_24X7))
        self.assertEqual(continuous_activation_gate(ServiceMode.PRODUCTION_24X7), "Phase-020F")

    def test_shadow_continuous_is_activated_by_020d(self):
        # IMPLEMENTATION-020D LIFTS the shadow-continuous gate: SHADOW_24X7 no longer requires
        # an activation gate (production continuous still does).
        self.assertFalse(requires_activation_gate(ServiceMode.SHADOW_24X7))
        self.assertEqual(continuous_activation_gate(ServiceMode.SHADOW_24X7), "")

    def test_off_and_manual_are_not_gated(self):
        self.assertFalse(requires_activation_gate(ServiceMode.OFF))
        self.assertFalse(requires_activation_gate(ServiceMode.MANUAL))

    def test_off_mode_run_once_runs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            health = run_once(_config(d, mode=ServiceMode.OFF), now=_NOW)
            self.assertEqual(health.service_mode, "off")
            self.assertEqual(health.last_successful_run_id, "")
            self.assertEqual(health.consecutive_failures, 0)
            # nothing persisted through the chain
            self.assertFalse(os.path.isfile(os.path.join(d, "run_store.jsonl")))

    def test_mode_parse_is_a_closed_vocabulary(self):
        self.assertIs(ServiceMode.parse("production_24x7"), ServiceMode.PRODUCTION_24X7)
        self.assertIs(ServiceMode.parse("MANUAL"), ServiceMode.MANUAL)
        with self.assertRaises(ValueError):
            ServiceMode.parse("cron_daemon")


# =========================================================================== #
# 2. Single-instance lock -- a duplicate service is refused; stale reclaimable #
# =========================================================================== #
class LockTests(unittest.TestCase):
    def test_second_acquire_while_held_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "service.lock")
            handle = acquire_lock(path, pid=100, now=_NOW)
            self.assertEqual(handle.pid, 100)
            self.assertFalse(handle.reclaimed_stale)
            with self.assertRaises(LockError):
                acquire_lock(path, pid=200, now=_NOW)     # a duplicate service refused
            self.assertEqual(read_lock(path)["pid"], 100)   # still the first holder

    def test_stale_lock_is_reclaimable(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "service.lock")
            acquire_lock(path, pid=100, now=_NOW)
            # two hours later, older than the 1h staleness policy -> reclaimable
            reclaimed = acquire_lock(path, pid=300, now="2026-06-29T17:00:01Z",
                                     stale_after_seconds=3600)
            self.assertTrue(reclaimed.reclaimed_stale)
            self.assertEqual(read_lock(path)["pid"], 300)

    def test_run_once_refuses_when_lock_already_held(self):
        with tempfile.TemporaryDirectory() as d:
            config = _config(d)
            acquire_lock(config.lock_path, pid=999, now=_NOW)   # a foreign holder
            health = run_once(config, now=_NOW, pid=1)
            self.assertEqual(health.lock_status, "held")
            self.assertEqual(health.last_successful_run_id, "")
            self.assertFalse(os.path.isfile(os.path.join(d, "run_store.jsonl")))

    def test_release_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "service.lock")
            handle = acquire_lock(path, pid=1, now=_NOW)
            CS.release_lock(handle)
            self.assertIsNone(read_lock(path))
            CS.release_lock(handle)         # second release is not an error


# =========================================================================== #
# 3. run_once CALLS the orchestrator -- persists through the FULL 013 chain    #
# =========================================================================== #
class RunOnceChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = cls.tmp.name
        cls.config = _config(cls.d, mode=ServiceMode.MANUAL)
        cls.health = run_once(cls.config, now=_NOW, pid=42)
        cls.run_id = cls.health.last_successful_run_id

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_success_updates_health(self):
        self.assertTrue(self.run_id.startswith("sched.cadence.news_filings."))
        self.assertEqual(self.health.last_tick_completed_at, _NOW)
        self.assertEqual(self.health.consecutive_failures, 0)
        self.assertEqual(self.health.last_error_class, "")
        self.assertEqual(self.health.service_mode, "manual")

    def test_stores_populated_through_the_chain(self):
        self.assertTrue(S.EventStore(self.d).query(run_id=self.run_id))
        self.assertTrue(S.FindingStore(self.d).query(run_id=self.run_id))
        self.assertTrue(S.SignalStore(self.d).query(run_id=self.run_id))
        self.assertTrue(S.RunStore(self.d).query(run_id=self.run_id))
        self.assertTrue(AgentRunLedger(self.d).results_for_run(self.run_id))

    def test_dq_gate_ran_not_bypassed(self):
        dq = S.DataQualityStore(self.d).query(run_id=self.run_id)
        self.assertIn("gate_overall", {r.category for r in dq})
        self.assertTrue(self.health.dq_status_summary.get("gate_ran"))

    def test_run_is_replayable_persistence_not_bypassed(self):
        harness = ReplayHarness(
            S.EventStore(self.d), S.FindingStore(self.d), S.SignalStore(self.d),
            S.ThemePulseStore(self.d), S.RunStore(self.d))
        replayed = harness.replay(ReplayRequest(run_id=self.run_id), now=_NOW)
        self.assertTrue(replayed.deterministic_match, replayed.differences)

    def test_health_summaries_are_counts_only(self):
        self.assertGreaterEqual(self.health.agent_health_summary.get("results", 0), 1)
        self.assertIn("records", self.health.dq_status_summary)
        self.assertIn("coverage_records", self.health.source_health_summary)

    def test_health_file_written_and_reloads(self):
        self.assertTrue(os.path.isfile(self.config.health_path))
        reloaded = load_health(self.config)
        self.assertEqual(reloaded.last_successful_run_id, self.run_id)

    def test_second_immediate_tick_is_idle_interval_not_elapsed(self):
        second = run_once(self.config, now="2026-06-29T15:00:30Z", pid=42)
        # interval has not elapsed -> nothing new ran, no new failure
        self.assertEqual(second.consecutive_failures, 0)
        self.assertEqual(second.last_successful_run_id, self.run_id)


# =========================================================================== #
# 4. pause prevents ticks; resume allows them                                 #
# =========================================================================== #
class PauseResumeTests(unittest.TestCase):
    def test_pause_stops_ticks_resume_allows_them(self):
        with tempfile.TemporaryDirectory() as d:
            config = _config(d, mode=ServiceMode.MANUAL)
            paused = pause(config, now=_NOW)
            self.assertTrue(paused.is_paused)
            # a paused service's run_once runs nothing
            after_pause = run_once(config, now="2026-06-29T15:05:00Z", pid=1)
            self.assertTrue(after_pause.is_paused)
            self.assertEqual(after_pause.last_successful_run_id, "")
            self.assertFalse(os.path.isfile(os.path.join(d, "run_store.jsonl")))
            # resume, then a tick runs again
            resumed = resume(config, now="2026-06-29T15:06:00Z")
            self.assertFalse(resumed.is_paused)
            after_resume = run_once(config, now="2026-06-29T15:07:00Z", pid=1)
            self.assertTrue(after_resume.last_successful_run_id.startswith("sched."))
            self.assertTrue(S.RunStore(d).query(run_id=after_resume.last_successful_run_id))


# =========================================================================== #
# 5. A failing tick -- health + structured sanitized log + escalating backoff #
# =========================================================================== #
class FailureAndBackoffTests(unittest.TestCase):
    def _failing_config(self, d):
        # An unresolvable adapter_ref (carrying a planted secret) is an honest pulse failure;
        # nothing is fixture-fallen-back-to.
        sub = _sub(adapter_refs=("api_key=" + _PLANTED_SECRET,))
        return _config(d, mode=ServiceMode.PRODUCTION_24X7, subscriptions=(sub,),
                       base_backoff_seconds=30, backoff_multiplier=2)

    def test_failing_tick_updates_health(self):
        with tempfile.TemporaryDirectory() as d:
            config = self._failing_config(d)
            health = run_once(config, now=_NOW, pid=1)
            self.assertEqual(health.consecutive_failures, 1)
            self.assertEqual(health.last_error_class, "ScheduledPulseFailure")
            self.assertEqual(health.last_tick_failed_at, _NOW)
            self.assertTrue(health.last_error_message_sanitized)
            self.assertEqual(health.last_successful_run_id, "")
            self.assertTrue(health.next_retry_at)          # backoff applied

    def test_repeated_failures_escalate_backoff(self):
        with tempfile.TemporaryDirectory() as d:
            config = self._failing_config(d)
            run_once(config, now=_NOW, pid=1)                        # failure 1 -> retry @ +30s
            # The service backoff (+30s) AND the per-policy scheduler backoff (news_filings
            # 5m interval -> 2**1*5 = 10m, until 15:10) must both elapse before the policy is
            # due again; a real second failure then escalates to failure 2 with a longer backoff.
            second = run_once(config, now="2026-06-29T15:10:01Z", pid=1)
            self.assertEqual(second.consecutive_failures, 2)
            # 2nd service backoff (30*2 = 60s) is strictly longer than the 1st (30s)
            self.assertEqual(second.next_retry_at, "2026-06-29T15:11:01Z")

    def test_backoff_skips_the_next_tick_without_counting_a_new_failure(self):
        with tempfile.TemporaryDirectory() as d:
            config = self._failing_config(d)
            run_once(config, now=_NOW, pid=1)                        # failure -> retry @ 15:00:30
            skipped = run_once(config, now="2026-06-29T15:00:10Z", pid=1)   # inside backoff
            self.assertEqual(skipped.consecutive_failures, 1)        # unchanged (not re-counted)

    def test_failure_does_not_bypass_the_health_records(self):
        with tempfile.TemporaryDirectory() as d:
            config = self._failing_config(d)
            health = run_once(config, now=_NOW, pid=1)
            failed_run_id = health.last_failed_run_id
            self.assertTrue(failed_run_id)
            # the orchestrator recorded the failure honestly (ledger + DQ), not papered over
            results = AgentRunLedger(d).results_for_run(failed_run_id)
            self.assertEqual([r.status for r in results], ["failed"])
            dq = S.DataQualityStore(d).query(run_id=failed_run_id)
            self.assertEqual([r.status for r in dq], ["failed"])
            # no fabricated spine run for a failed pulse
            self.assertEqual(S.RunStore(d).query(run_id=failed_run_id), ())


# =========================================================================== #
# 6. Logs are structured (JSON) and sanitized -- no secret in log OR health   #
# =========================================================================== #
class StructuredLogAndSecretTests(unittest.TestCase):
    def test_log_lines_are_parseable_json(self):
        with tempfile.TemporaryDirectory() as d:
            config = _config(d, mode=ServiceMode.MANUAL)
            run_once(config, now=_NOW, pid=1)
            run_once(config, now="2026-06-29T16:00:00Z", pid=1)
            lines = _read(config.log_path).splitlines()
            self.assertGreaterEqual(len(lines), 2)
            for line in lines:
                record = json.loads(line)          # every line is valid JSON
                self.assertIn("event", record)
                self.assertIn("ts", record)

    def test_planted_secret_never_appears_in_log_or_health(self):
        with tempfile.TemporaryDirectory() as d:
            sub = _sub(adapter_refs=("api_key=" + _PLANTED_SECRET,))
            config = _config(d, mode=ServiceMode.PRODUCTION_24X7, subscriptions=(sub,))
            run_once(config, now=_NOW, pid=1)
            log_text = _read(config.log_path)
            health_text = _read(config.health_path)
            self.assertNotIn(_PLANTED_SECRET, log_text)
            self.assertNotIn(_PLANTED_SECRET, health_text)
            self.assertIn("<redacted>", log_text)      # it WAS present and got redacted

    def test_sanitize_redacts_common_secret_shapes(self):
        self.assertNotIn("hunter2verysecret", sanitize("password=hunter2verysecret"))
        self.assertNotIn("sk-abc123def456", sanitize("token sk-abc123def456"))
        self.assertNotIn("AKIAEXAMPLE12345", sanitize("AKIAEXAMPLE12345"))
        # a plain run id / timestamp passes through unchanged
        self.assertEqual(sanitize("sched.cadence.news_filings.20260629T150000Z"),
                         "sched.cadence.news_filings.20260629T150000Z")

    def test_health_to_dict_is_json_serializable_and_sanitized(self):
        health = ServiceHealth(last_error_message_sanitized="token=" + _PLANTED_SECRET)
        text = json.dumps(health.to_dict(), sort_keys=True)
        self.assertNotIn(_PLANTED_SECRET, text)


# =========================================================================== #
# 7. status snapshot                                                          #
# =========================================================================== #
class StatusTests(unittest.TestCase):
    def test_status_reflects_mode_and_lock(self):
        with tempfile.TemporaryDirectory() as d:
            config = _config(d, mode=ServiceMode.MANUAL)
            status = service_status(config)
            self.assertEqual(status.service_mode, "manual")
            self.assertEqual(status.lock_status, "free")
            acquire_lock(config.lock_path, pid=7, now=_NOW)
            held = service_status(config)
            self.assertEqual(held.lock_status, "held")
            self.assertEqual(held.pid, 7)


# =========================================================================== #
# 8. No network / no loop on import; the CORE is loop-free (AST)              #
# =========================================================================== #
class ImportAndAstGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core_src = _read(_SERVICE_PY)
        cls.core_tree = ast.parse(cls.core_src)
        cls.init_tree = ast.parse(_read(_INIT_PY))
        cls.main_src = _read(_MAIN_PY)
        cls.main_tree = ast.parse(cls.main_src)

    def test_core_has_no_banned_import(self):
        for node in ast.walk(self.core_tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for banned in _BANNED_IMPORT_ROOTS:
                    self.assertFalse(
                        name == banned or name.startswith(banned + "."),
                        "banned import {0!r} in the CORE service.py".format(name))

    def test_core_has_no_loop_or_daemon_call(self):
        for node in ast.walk(self.core_tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in the CORE service.py")
            self.assertNotIsInstance(node, ast.AsyncFunctionDef)
            self.assertNotIsInstance(node, ast.Await)
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotIn(called, _BANNED_CALL_NAMES,
                                 "daemon-style call {0!r} in the CORE".format(called))

    def test_core_reads_no_wall_clock(self):
        for token in _WALL_CLOCK_TOKENS:
            self.assertNotIn(token, self.core_src, "wall-clock call {0!r} in the CORE".format(token))

    def test_core_import_is_side_effect_free(self):
        allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr,
                   ast.FunctionDef, ast.ClassDef)
        for node in self.core_tree.body:
            self.assertIsInstance(node, allowed)
            if isinstance(node, ast.Expr):
                self.assertIsInstance(node.value, ast.Constant)     # only the docstring

    def test_package_init_has_no_loop_or_sleep(self):
        for node in ast.walk(self.init_tree):
            self.assertNotIsInstance(node, ast.While)

    def test_the_loop_and_sleep_live_only_in_main(self):
        # the operator-started process IS allowed the loop + sleep
        self.assertTrue(any(isinstance(n, ast.While) for n in ast.walk(self.main_tree)),
                        "the supervised loop must live in __main__")
        self.assertIn("time.sleep(", self.main_src)

    def test_importing_the_package_starts_nothing(self):
        # no background thread was spawned by importing the package (main thread only)
        self.assertEqual(threading.active_count(), 1)
        # and importing bound no socket (the kill-switch would have fired on connect)
        import importlib
        importlib.reload(CS)     # re-import: still no side effect

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()


# =========================================================================== #
# 9. Untouched paths -- demo default + default pulse stay byte-identical      #
# =========================================================================== #
class UntouchedPathsTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                with open(a[name], "rb") as fa, open(b[name], "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(),
                                     "demo default drifted for {0}".format(name))

    def test_default_pulse_byte_identical(self):
        import reality_mesh as rm
        now = "2026-06-29T00:00:00Z"
        a = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=now)
        b = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=now)
        self.assertEqual(repr(a.signals), repr(b.signals))
        self.assertEqual(repr(a.theme_pulses), repr(b.theme_pulses))


# =========================================================================== #
# 10. The operator CLI shell (imported here only to exercise argparse dispatch) #
# =========================================================================== #
class CliShellTests(unittest.TestCase):
    def _main(self, argv):
        from cosmosiq_service.__main__ import main
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(argv)
        return rc, out.getvalue()

    def test_run_once_command_runs_one_tick(self):
        with tempfile.TemporaryDirectory() as d:
            subs = os.path.join(d, "subs.json")
            with open(subs, "w", encoding="utf-8") as fh:
                json.dump({"subscriptions": [{
                    "subscription_id": "sub.core", "watchlist": ["IREN", "NVDA"],
                    "themes": ["physical_ai", "robotics"],
                    "policy_ids": ["cadence.news_filings"]}]}, fh)
            store = os.path.join(d, "store")
            rc, text = self._main(["run-once", "--store-dir", store, "--mode", "manual",
                                   "--subscriptions", subs, "--now", _NOW])
            self.assertEqual(rc, 0)
            self.assertIn("one supervised tick", text.lower())
            self.assertIn("not a cloud daemon", text)
            self.assertIn("Phase-020F", text)          # honest banner names the gate
            self.assertTrue(os.path.isfile(os.path.join(store, "run_store.jsonl")))

    def test_start_refuses_production_continuous(self):
        with tempfile.TemporaryDirectory() as d:
            rc, text = self._main(["start", "--store-dir", os.path.join(d, "s"),
                                   "--mode", "production_24x7"])
            self.assertEqual(rc, 2)
            self.assertIn("REFUSED", text)
            self.assertIn("Phase-020F", text)

    def test_shadow_continuous_no_longer_gate_refused(self):
        # 020D lifts the shadow-continuous refusal at the gate level: `start --mode shadow_24x7`
        # would now enter the supervised loop, so it is not exercised here (it never returns).
        # The lift is proven at the gate/core level without touching the loop.
        self.assertFalse(requires_activation_gate(ServiceMode.SHADOW_24X7))
        self.assertEqual(continuous_activation_gate(ServiceMode.SHADOW_24X7), "")
        # production continuous stays refused.
        self.assertTrue(requires_activation_gate(ServiceMode.PRODUCTION_24X7))

    def test_start_off_runs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            rc, text = self._main(["start", "--store-dir", os.path.join(d, "s"), "--mode", "off"])
            self.assertEqual(rc, 0)
            self.assertIn("OFF", text)

    def test_status_command_prints_health(self):
        with tempfile.TemporaryDirectory() as d:
            rc, text = self._main(["status", "--store-dir", os.path.join(d, "s"),
                                   "--mode", "manual"])
            self.assertEqual(rc, 0)
            self.assertIn("service_mode", text)

    def test_pause_then_resume_via_cli(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "s")
            rc1, t1 = self._main(["pause", "--store-dir", store, "--mode", "manual", "--now", _NOW])
            rc2, t2 = self._main(["resume", "--store-dir", store, "--mode", "manual", "--now", _NOW])
            self.assertEqual((rc1, rc2), (0, 0))
            self.assertIn("paused", t1.lower())
            self.assertIn("resumed", t2.lower())


# =========================================================================== #
# 11. GO-LIVE PL-5 -- continuous SHADOW on an explicit operator opt-in         #
#     (default still refused; production always refused)                       #
# =========================================================================== #
class ContinuousShadowOptInPolicyTests(unittest.TestCase):
    def test_shadow_with_opt_in_is_allowed(self):
        self.assertTrue(
            continuous_shadow_allowed(ServiceMode.SHADOW_24X7, operator_opt_in=True))

    def test_shadow_without_opt_in_is_refused(self):
        self.assertFalse(
            continuous_shadow_allowed(ServiceMode.SHADOW_24X7, operator_opt_in=False))

    def test_production_is_never_allowed_even_with_opt_in(self):
        self.assertFalse(
            continuous_shadow_allowed(ServiceMode.PRODUCTION_24X7, operator_opt_in=True))
        self.assertFalse(
            continuous_shadow_allowed(ServiceMode.PRODUCTION_24X7, operator_opt_in=False))

    def test_off_and_manual_are_not_the_continuous_shadow_path(self):
        for mode in (ServiceMode.OFF, ServiceMode.MANUAL):
            for opt_in in (True, False):
                self.assertFalse(
                    continuous_shadow_allowed(mode, operator_opt_in=opt_in),
                    "{0} opt_in={1} must not be the continuous-shadow path".format(mode, opt_in))

    def test_helper_does_not_change_requires_activation_gate_for_production(self):
        # The PL-5 opt-in policy is orthogonal to the PRODUCTION activation gate.
        self.assertTrue(requires_activation_gate(ServiceMode.PRODUCTION_24X7))
        self.assertEqual(continuous_activation_gate(ServiceMode.PRODUCTION_24X7), "Phase-020F")


class SuperviseOptInGateTests(unittest.TestCase):
    """Exercise the loop-free pre-loop decision (NOT the while-loop)."""

    def _decision(self, mode, *, opt_in):
        from cosmosiq_service.__main__ import _pre_loop_decision
        with tempfile.TemporaryDirectory() as d:
            config = ServiceConfig(mode=mode, store_dir=os.path.join(d, "s"))
            return _pre_loop_decision(config, operator_opt_in_continuous_shadow=opt_in)

    def test_shadow_with_opt_in_does_not_early_refuse(self):
        # None => the guard permits entering the supervised loop (loop itself is not run here).
        self.assertIsNone(self._decision(ServiceMode.SHADOW_24X7, opt_in=True))

    def test_shadow_without_opt_in_is_refused_and_names_the_flag(self):
        decision = self._decision(ServiceMode.SHADOW_24X7, opt_in=False)
        self.assertIsNotNone(decision)
        code, message = decision
        self.assertEqual(code, 2)
        self.assertIn("--confirm-continuous-shadow", message)
        self.assertIn("REFUSED", message)
        # inbox-only posture is stated; no external delivery / broker / orders.
        for token in ("inbox-only", "external delivery", "broker", "orders"):
            self.assertIn(token, message)

    def test_production_with_opt_in_is_still_refused(self):
        decision = self._decision(ServiceMode.PRODUCTION_24X7, opt_in=True)
        self.assertIsNotNone(decision)
        code, message = decision
        self.assertEqual(code, 2)
        self.assertIn("Phase-020F", message)
        self.assertIn("REFUSED", message)

    def test_off_is_a_no_op_not_a_refusal(self):
        decision = self._decision(ServiceMode.OFF, opt_in=True)
        self.assertIsNotNone(decision)
        code, _message = decision
        self.assertEqual(code, 0)

    def test_manual_enters_the_loop_unchanged(self):
        self.assertIsNone(self._decision(ServiceMode.MANUAL, opt_in=False))


class SuperviseCliOptInTests(unittest.TestCase):
    def _main(self, argv):
        from cosmosiq_service.__main__ import main
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(argv)
        return rc, out.getvalue()

    def test_start_shadow_without_opt_in_is_refused(self):
        # The SAFE DEFAULT: `start --mode shadow_24x7` (no opt-in) refuses with exit 2 -- it never
        # enters the loop, so this call returns.
        with tempfile.TemporaryDirectory() as d:
            rc, text = self._main(["start", "--store-dir", os.path.join(d, "s"),
                                   "--mode", "shadow_24x7"])
            self.assertEqual(rc, 2)
            self.assertIn("REFUSED", text)
            self.assertIn("--confirm-continuous-shadow", text)

    def test_start_production_with_confirm_flag_is_still_refused(self):
        # No flag can start continuous production.
        with tempfile.TemporaryDirectory() as d:
            rc, text = self._main(["start", "--store-dir", os.path.join(d, "s"),
                                   "--mode", "production_24x7",
                                   "--confirm-continuous-shadow"])
            self.assertEqual(rc, 2)
            self.assertIn("REFUSED", text)
            self.assertIn("Phase-020F", text)

    def test_confirm_flag_exists_only_on_start(self):
        # The opt-in flag is a start-only concern; run-once does not accept it (argparse rejects it).
        from contextlib import redirect_stderr
        from cosmosiq_service.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), \
                    redirect_stderr(io.StringIO()):
                main(["run-once", "--store-dir", os.path.join(d, "s"),
                      "--mode", "manual", "--now", _NOW, "--confirm-continuous-shadow"])

    def test_no_trade_or_order_affordance_introduced(self):
        # PL-5 introduces NO broker / order / trade path anywhere in the shell.
        src = _read(_MAIN_PY).lower()
        for token in ("broker", "place_order", "submit_order", "send_order", "execute_trade"):
            self.assertNotIn("import " + token, src)
        # the loop-free gate must not touch a broker/order symbol
        self.assertNotIn("order(", src)


if __name__ == "__main__":
    unittest.main()
