"""IMPLEMENTATION-015B -- PulseOrchestrator: explicit-start runner + scheduled-trigger unlock.

015A shipped the cadence CORE (data + the pure ``due_policies`` decision); this suite proves
the 015B slice that ACTS on it -- still never a daemon (ADR-CANDIDATE-015):

* the reserved ``scheduled`` trigger type is UNLOCKED (a PulseRun constructs, and every
  scheduled run carries the policy_id that scheduled it via ``scheduled_by_policy:<id>`` in
  ``generated_outputs`` + an audit attribution) while ``streaming`` stays RESERVED/rejected;
* ``run_due_pulses`` is ONE synchronous tick: due policies resolve through watchlist/theme
  Subscriptions to a pulse scope; each pulse runs the FULL 013 chain (append-only stores,
  agent-run ledger, health roll-ups, data-quality gates, deterministic verification replay);
  outcomes land back in the schedule via ``record_run``; the schedule state itself persists
  append-style (JSONL journal lines are never mutated; reload -> the same state);
* failure isolation: one failing policy's pulse backs THAT policy off (visible in the ledger +
  data-quality records) and never aborts the tick -- other due policies still run;
* throttle / backoff / market-closed / paused / interval / no-subscription are all honored and
  NAMED as skip reasons; a due policy with no subscription is a visible note, not an error;
* the opt-in CLI flag ``--scheduled-tick`` runs exactly ONE tick offline and exits (rc 0,
  reasons printed); the default CLI without the flag stays byte-identical;
* NO daemon construct exists in orchestrator.py (no while-loop / async / timed wait / thread /
  process; no banned import; import has no side effect; no wall clock; no execution word), the
  repo-wide import guards still hold with the module present, and the demo default + default
  pulse remain byte-identical.

Entirely OFFLINE and deterministic: injected ``now`` ISO strings everywhere; a socket
kill-switch guards the whole module.
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import labels as L
from reality_mesh import scheduler as SC
from reality_mesh import stores as S
from reality_mesh.ledger import AgentRunLedger
from reality_mesh.orchestrator import (
    ORCHESTRATOR_ACTOR,
    SCHEDULED_BY_POLICY_PREFIX,
    PulseOrchestrator,
    ScheduleStateStore,
    Subscription,
    TickResult,
    append_schedule_state,
    load_schedule_state,
    run_due_pulses,
    scheduled_policy_for,
    subscription_from_dict,
    subscription_to_dict,
)
from reality_mesh.replay import ReplayHarness
from reality_mesh.runtime import PulseRun, ReplayRequest
from tattva_pulse.__main__ import main as pulse_cli_main

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_ORCHESTRATOR_PY = os.path.join(_PKG_DIR, "orchestrator.py")

# A Monday. 15:00 UTC is inside the default 14:30-21:00 UTC session.
_NOW = "2026-06-29T15:00:00Z"
_SATURDAY = "2026-06-27T15:00:00Z"

# The same ban lists the 012/013/015A guards enforce, re-asserted over orchestrator.py.
_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "asyncio", "threading", "multiprocessing",
                        "subprocess", "smtplib", "ftplib", "socketserver", "broker",
                        "signal", "time", "random", "select", "selectors", "queue")
_BANNED_CALL_NAMES = ("sleep", "run_forever", "serve_forever", "start_polling", "Thread",
                      "Timer", "Process", "fork", "spawn", "run_in_executor", "setdaemon")
_EXECUTION_WORDS = ("buy", "sell", "hold", "order", "orders", "trade", "trades", "trading",
                    "broker", "execute", "execution", "rebalance", "rebalancing", "position",
                    "alert", "alerts")
_WALL_CLOCK_TOKENS = ("time.time(", "datetime.now(", "datetime.utcnow(", "utcnow(",
                      "time.monotonic(", "perf_counter(")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline orchestrator suite")


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


def _policy(pid="cadence.test", interval=5, market_hours_only=False, floor=1):
    return SC.CadencePolicy(
        policy_id=pid, discipline_or_adapter="news_filings",
        interval_minutes=interval, market_hours_only=market_hours_only,
        min_interval_minutes=floor)


def _schedule(policies, max_runs_per_hour=60):
    return SC.PulseSchedule(
        policies=tuple(policies),
        states=tuple(SC.ScheduleState(policy_id=p.policy_id) for p in policies),
        max_runs_per_hour=max_runs_per_hour)


def _sub(sid="sub.core", policy_ids=("cadence.test",), data_dir="", adapter_refs=()):
    return Subscription(
        subscription_id=sid, watchlist=("IREN", "NVDA"),
        themes=("physical_ai", "robotics"), policy_ids=tuple(policy_ids),
        data_dir=data_dir, adapter_refs=tuple(adapter_refs))


# =========================================================================== #
# 1. The trigger unlock -- scheduled constructs (with attribution);           #
#    streaming stays rejected                                                 #
# =========================================================================== #
class TriggerUnlockTests(unittest.TestCase):
    def test_scheduled_now_constructs_a_pulse_run(self):
        run = PulseRun(run_id="R", trigger_type="scheduled",
                       generated_outputs=(SCHEDULED_BY_POLICY_PREFIX + "cadence.test",))
        self.assertEqual(run.trigger_type, "scheduled")
        self.assertEqual(scheduled_policy_for(run), "cadence.test")

    def test_streaming_still_reserved_and_rejected(self):
        try:
            PulseRun(run_id="R", trigger_type="streaming")
            self.fail("expected ValueError")
        except ValueError as exc:
            self.assertIn("RESERVED", str(exc))

    def test_vocabularies_reflect_the_015b_unlock(self):
        self.assertEqual(L.ALLOWED_TRIGGER_TYPES, frozenset({"manual", "scheduled"}))
        self.assertEqual(L.RESERVED_TRIGGER_TYPES, frozenset({"streaming"}))
        self.assertTrue(L.is_trigger_type("scheduled"))
        self.assertFalse(L.is_reserved_trigger_type("scheduled"))
        self.assertTrue(L.is_reserved_trigger_type("streaming"))

    def test_unknown_trigger_still_rejected(self):
        with self.assertRaises(ValueError):
            PulseRun(run_id="R", trigger_type="cron")

    def test_attribution_reader_returns_gap_for_manual(self):
        self.assertEqual(scheduled_policy_for(PulseRun(run_id="R")), "")


# =========================================================================== #
# 2. One tick, one due policy, one subscription -> a persisted scheduled run  #
#    through the FULL 013 chain                                               #
# =========================================================================== #
class OneTickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store_dir = cls.tmp.name
        cls.schedule = _schedule((_policy(),))
        cls.result = run_due_pulses(
            cls.schedule, now=_NOW, store_dir=cls.store_dir,
            subscriptions=(_sub(),), max_pulses=3)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_one_scheduled_pulse_run_returned_with_attribution(self):
        self.assertEqual(len(self.result.pulse_runs), 1)
        run = self.result.pulse_runs[0]
        self.assertEqual(run.trigger_type, "scheduled")
        self.assertEqual(scheduled_policy_for(run), "cadence.test")
        self.assertIn(SCHEDULED_BY_POLICY_PREFIX + "cadence.test", run.generated_outputs)
        self.assertEqual(run.run_id, "sched.cadence.test.20260629T150000Z")  # deterministic

    def test_result_unpacks_as_schedule_and_runs(self):
        new_schedule, runs = self.result
        self.assertIsInstance(new_schedule, SC.PulseSchedule)
        self.assertEqual(runs, self.result.pulse_runs)

    def test_stores_populated_through_the_013_chain(self):
        run_id = self.result.pulse_runs[0].run_id
        self.assertTrue(S.EventStore(self.store_dir).query(run_id=run_id))
        self.assertTrue(S.FindingStore(self.store_dir).query(run_id=run_id))
        self.assertTrue(S.SignalStore(self.store_dir).query(run_id=run_id))
        self.assertTrue(S.ThemePulseStore(self.store_dir).query(run_id=run_id))
        # gates ran and their verdicts persisted (incl. the overall roll-up)
        dq = S.DataQualityStore(self.store_dir).query(run_id=run_id)
        self.assertIn("gate_overall", {r.category for r in dq})
        # health rolled: one ledger result per sensor agent of the pulse
        self.assertTrue(AgentRunLedger(self.store_dir).results_for_run(run_id))

    def test_run_record_superseded_append_only_with_audit_correction(self):
        run_id = self.result.pulse_runs[0].run_id
        persisted = S.RunStore(self.store_dir).query(run_id=run_id)
        # the original manual spine line is byte-unchanged; the scheduled record is a NEW line
        self.assertEqual([r.trigger_type for r in persisted], ["manual", "scheduled"])
        self.assertEqual(scheduled_policy_for(persisted[-1]), "cadence.test")
        corrections = S.AuditStore(self.store_dir).query(run_id=run_id, action="correction")
        self.assertEqual(len(corrections), 1)
        self.assertEqual(corrections[0].corrects, run_id)
        self.assertEqual(corrections[0].actor, ORCHESTRATOR_ACTOR)
        self.assertIn(SCHEDULED_BY_POLICY_PREFIX + "cadence.test", corrections[0].note)

    def test_replay_is_deterministic_read_only(self):
        run_id = self.result.pulse_runs[0].run_id
        harness = ReplayHarness(
            S.EventStore(self.store_dir), S.FindingStore(self.store_dir),
            S.SignalStore(self.store_dir), S.ThemePulseStore(self.store_dir),
            S.RunStore(self.store_dir))
        replayed = harness.replay(ReplayRequest(run_id=run_id), now=_NOW)
        self.assertTrue(replayed.deterministic_match, replayed.differences)
        self.assertIn("deterministic_match=True", " ".join(self.result.ran))

    def test_record_run_updated_last_run_at_advanced(self):
        state = SC.state_for(self.result.schedule, "cadence.test")
        self.assertEqual(state.last_run_at, _NOW)
        self.assertEqual(state.consecutive_failures, 0)
        self.assertEqual(state.backoff_until, "")
        # the INPUT schedule was never mutated (frozen, append-style)
        self.assertEqual(SC.state_for(self.schedule, "cadence.test").last_run_at, "")

    def test_second_tick_immediately_after_runs_nothing(self):
        second = run_due_pulses(
            self.result.schedule, now="2026-06-29T15:01:00Z", store_dir=self.store_dir,
            subscriptions=(_sub(),), max_pulses=3)
        self.assertEqual(second.pulse_runs, ())
        self.assertEqual(second.ran, ())
        self.assertTrue(any("interval not elapsed" in reason for reason in second.skipped),
                        second.skipped)

    def test_orchestrator_class_delegates_to_the_same_tick(self):
        with tempfile.TemporaryDirectory() as d:
            orch = PulseOrchestrator(store_dir=d, subscriptions=(_sub(),))
            result = orch.tick(_schedule((_policy(),)), now=_NOW, max_pulses=2)
            self.assertEqual(len(result.pulse_runs), 1)
            self.assertEqual(result.pulse_runs[0].trigger_type, "scheduled")


# =========================================================================== #
# 3. Failure isolation -- a failing pulse backs off; other due policies run   #
# =========================================================================== #
class FailureIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store_dir = cls.tmp.name
        cls.bad_dir = os.path.join(cls.store_dir, "no_such_market_data")
        cls.schedule = _schedule((_policy("cadence.fail"), _policy("cadence.ok")))
        cls.result = run_due_pulses(
            cls.schedule, now=_NOW, store_dir=cls.store_dir,
            subscriptions=(
                _sub("sub.fail", policy_ids=("cadence.fail",), data_dir=cls.bad_dir),
                _sub("sub.ok", policy_ids=("cadence.ok",)),
            ),
            max_pulses=5)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_failing_policy_backed_off_and_named(self):
        state = SC.state_for(self.result.schedule, "cadence.fail")
        self.assertEqual(state.consecutive_failures, 1)
        self.assertEqual(state.backoff_until, "2026-06-29T15:10:00Z")   # 2**1 * 5m
        self.assertTrue(any("cadence.fail" in line and "backoff" in line
                            for line in self.result.failed), self.result.failed)

    def test_other_due_policy_still_ran(self):
        self.assertEqual([scheduled_policy_for(r) for r in self.result.pulse_runs],
                         ["cadence.ok"])
        self.assertEqual(SC.state_for(self.result.schedule, "cadence.ok").last_run_at, _NOW)

    def test_failure_lands_in_health_records_not_hidden(self):
        failed_run_id = "sched.cadence.fail.20260629T150000Z"
        results = AgentRunLedger(self.store_dir).results_for_run(failed_run_id)
        self.assertEqual([r.status for r in results], ["failed"])
        self.assertEqual(results[0].agent_id, ORCHESTRATOR_ACTOR)
        self.assertEqual(results[0].health_status, "failed")
        dq = S.DataQualityStore(self.store_dir).query(run_id=failed_run_id)
        self.assertEqual([r.status for r in dq], ["failed"])
        self.assertEqual([r.category for r in dq], ["source_failure"])
        # nothing was persisted as a run for the failure (no fabricated spine record)
        self.assertEqual(S.RunStore(self.store_dir).query(run_id=failed_run_id), ())

    def test_backoff_blocks_the_next_tick_with_a_named_reason(self):
        nxt = run_due_pulses(
            self.result.schedule, now="2026-06-29T15:06:00Z", store_dir=self.store_dir,
            subscriptions=(_sub("sub.fail", policy_ids=("cadence.fail",)),), max_pulses=5)
        self.assertEqual(nxt.pulse_runs, ())
        self.assertTrue(any("cadence.fail" in r and "backoff" in r for r in nxt.skipped),
                        nxt.skipped)


# =========================================================================== #
# 4. Throttle / paused / market-closed / no-subscription -- honored + named   #
# =========================================================================== #
class SkipReasonTests(unittest.TestCase):
    def test_throttle_honored_across_a_tick(self):
        # max_runs_per_hour=1: the FIRST due policy runs, the second is throttled mid-tick.
        schedule = _schedule((_policy("cadence.a"), _policy("cadence.b")),
                             max_runs_per_hour=1)
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(
                schedule, now=_NOW, store_dir=d,
                subscriptions=(_sub("sub.ab", policy_ids=("cadence.a", "cadence.b")),),
                max_pulses=5)
            self.assertEqual([scheduled_policy_for(r) for r in result.pulse_runs],
                             ["cadence.a"])
            self.assertTrue(any("cadence.b" in r and "throttled" in r
                                for r in result.skipped), result.skipped)

    def test_already_throttled_schedule_runs_nothing(self):
        schedule = SC.record_run(
            _schedule((_policy("cadence.a", interval=1),), max_runs_per_hour=1),
            "cadence.a", "2026-06-29T14:30:00Z", True)
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(schedule, now=_NOW, store_dir=d,
                                    subscriptions=(_sub(policy_ids=("cadence.a",)),))
            self.assertEqual(result.pulse_runs, ())
            self.assertTrue(any("throttled" in r for r in result.skipped), result.skipped)

    def test_paused_schedule_runs_nothing_and_says_why(self):
        schedule = SC.pause(_schedule((_policy(),)), SC.ALL_POLICIES, _NOW)
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(schedule, now=_NOW, store_dir=d,
                                    subscriptions=(_sub(),))
            self.assertEqual(result.pulse_runs, ())
            self.assertTrue(any("paused" in n for n in result.notes), result.notes)
            self.assertTrue(all("paused" in r for r in result.skipped), result.skipped)

    def test_individually_paused_policy_named(self):
        schedule = SC.pause(_schedule((_policy(),)), "cadence.test", _NOW)
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(schedule, now=_NOW, store_dir=d,
                                    subscriptions=(_sub(),))
            self.assertEqual(result.pulse_runs, ())
            self.assertTrue(any("policy paused" in r for r in result.skipped),
                            result.skipped)

    def test_market_closed_skips_market_hours_only_policies_with_reason(self):
        schedule = _schedule((_policy(market_hours_only=True),))
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(schedule, now=_SATURDAY, store_dir=d,
                                    subscriptions=(_sub(),))
            self.assertEqual(result.pulse_runs, ())
            self.assertTrue(any("market closed" in r for r in result.skipped),
                            result.skipped)

    def test_no_subscription_is_a_visible_note_not_an_error(self):
        schedule = _schedule((_policy(),))
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(schedule, now=_NOW, store_dir=d, subscriptions=())
            self.assertEqual(result.pulse_runs, ())
            self.assertTrue(any("no subscription" in n for n in result.notes),
                            result.notes)
            # nothing ran -> the policy's schedule state did NOT advance
            self.assertEqual(SC.state_for(result.schedule, "cadence.test").last_run_at, "")

    def test_max_pulses_bounds_one_tick(self):
        schedule = _schedule((_policy("cadence.a"), _policy("cadence.b")))
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(
                schedule, now=_NOW, store_dir=d,
                subscriptions=(_sub("sub.ab", policy_ids=("cadence.a", "cadence.b")),),
                max_pulses=1)
            self.assertEqual(len(result.pulse_runs), 1)
            self.assertTrue(any("max_pulses" in r for r in result.skipped), result.skipped)

    def test_bad_inputs_rejected(self):
        schedule = _schedule((_policy(),))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run_due_pulses(schedule, now="not-a-timestamp", store_dir=d)
            with self.assertRaises(ValueError):
                run_due_pulses(schedule, now=_NOW, store_dir=d, max_pulses=0)
            with self.assertRaises(ValueError):
                run_due_pulses(schedule, now=_NOW, store_dir="  ")


# =========================================================================== #
# 5. The schedule-state journal -- append-style, never mutated, reloadable    #
# =========================================================================== #
class ScheduleJournalTests(unittest.TestCase):
    def test_journal_appends_per_tick_and_lines_never_mutate(self):
        schedule = _schedule((_policy(),))
        with tempfile.TemporaryDirectory() as d:
            first = run_due_pulses(schedule, now=_NOW, store_dir=d,
                                   subscriptions=(_sub(),), max_pulses=2)
            journal_path = os.path.join(d, "schedule_state_store.jsonl")
            first_lines = _read(journal_path).splitlines()
            self.assertEqual(len(first_lines), 1)
            run_due_pulses(first.schedule, now="2026-06-29T15:05:00Z", store_dir=d,
                           subscriptions=(_sub(),), max_pulses=2)
            second_lines = _read(journal_path).splitlines()
            self.assertEqual(len(second_lines), 2)
            self.assertEqual(second_lines[0], first_lines[0])    # byte-unchanged forever
            records = ScheduleStateStore(d).read_records()
            self.assertEqual([r["record_id"] for r in records],
                             ["schedule-state-000001", "schedule-state-000002"])

    def test_reload_yields_the_same_state(self):
        schedule = _schedule((_policy(),))
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(schedule, now=_NOW, store_dir=d,
                                    subscriptions=(_sub(),), max_pulses=2)
            reloaded = load_schedule_state(d)
            self.assertIsNotNone(reloaded)
            self.assertEqual(SC.schedule_to_dict(reloaded),
                             SC.schedule_to_dict(result.schedule))
            # behavior parity, not just shape parity
            self.assertEqual(
                sorted(SC.due_policies(reloaded, "2026-06-29T15:05:00Z")),
                sorted(SC.due_policies(result.schedule, "2026-06-29T15:05:00Z")))

    def test_empty_journal_loads_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(load_schedule_state(d))

    def test_manual_append_is_also_append_style(self):
        schedule = _schedule((_policy(),))
        with tempfile.TemporaryDirectory() as d:
            append_schedule_state(d, schedule, now=_NOW, note="initial")
            paused = SC.pause(schedule, SC.ALL_POLICIES, _NOW)
            append_schedule_state(d, paused, now=_NOW, note="paused by operator")
            records = ScheduleStateStore(d).read_records()
            self.assertEqual(len(records), 2)
            self.assertFalse(records[0]["payload"]["schedule"]["paused_all"])
            self.assertTrue(records[1]["payload"]["schedule"]["paused_all"])
            self.assertTrue(load_schedule_state(d).paused_all)


# =========================================================================== #
# 6. Subscription -- closed validation + deterministic round-trip             #
# =========================================================================== #
class SubscriptionTests(unittest.TestCase):
    def test_valid_subscription_constructs_frozen(self):
        sub = _sub()
        with self.assertRaises(FrozenInstanceError):
            sub.data_dir = "/elsewhere"  # type: ignore[misc]

    def test_required_fields_rejected_when_empty(self):
        with self.assertRaises(ValueError):
            Subscription(subscription_id="", watchlist=("IREN",), themes=("ai",))
        with self.assertRaises(ValueError):
            Subscription(subscription_id="s", watchlist=(), themes=("ai",))
        with self.assertRaises(ValueError):
            Subscription(subscription_id="s", watchlist=("IREN",), themes=())
        with self.assertRaises(ValueError):
            Subscription(subscription_id="s", watchlist=("IREN", " "), themes=("ai",))
        with self.assertRaises(ValueError):
            Subscription(subscription_id="s", watchlist=("IREN",), themes=("ai",),
                         policy_ids=("", "cadence.x"))

    def test_round_trip(self):
        sub = _sub(adapter_refs=("local_market_data",), data_dir="/tmp/market")
        self.assertEqual(subscription_from_dict(subscription_to_dict(sub)), sub)

    def test_unresolvable_adapter_ref_is_an_honest_failure(self):
        schedule = _schedule((_policy(),))
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(
                schedule, now=_NOW, store_dir=d,
                subscriptions=(_sub(adapter_refs=("ghost_adapter",)),))
            self.assertEqual(result.pulse_runs, ())
            self.assertTrue(any("ghost_adapter" in line for line in result.failed),
                            result.failed)
            self.assertEqual(
                SC.state_for(result.schedule, "cadence.test").consecutive_failures, 1)


# =========================================================================== #
# 7. CLI -- one opt-in tick, then exit; default CLI byte-identical            #
# =========================================================================== #
class CliTests(unittest.TestCase):
    def _write_subscriptions(self, base_dir):
        path = os.path.join(base_dir, "subscriptions.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "subscriptions": [{
                    "subscription_id": "sub.core",
                    "watchlist": ["IREN", "NVDA"],
                    "themes": ["physical_ai", "robotics"],
                    "policy_ids": ["cadence.news_filings"],
                }],
                "max_runs_per_hour": 60,
            }, fh)
        return path

    def test_scheduled_tick_runs_one_tick_offline_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            subs = self._write_subscriptions(d)
            store = os.path.join(d, "store")
            out = io.StringIO()
            with redirect_stdout(out):
                rc = pulse_cli_main([
                    "--scheduled-tick", "--persist-dir", store,
                    "--tick-now", "2026-06-29T00:00:00Z",   # Monday 00:00 UTC: market closed
                    "--subscriptions", subs])
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("ONE scheduled tick", text)
            self.assertIn("not a daemon", text)
            self.assertIn("ran (1):", text)
            self.assertIn("cadence.news_filings: ran pulse", text)
            self.assertIn("deterministic_match=True", text)
            self.assertIn("market closed", text)             # market-hours-only named
            self.assertIn("no subscription references this policy", text)
            self.assertIn("skipped", text)
            self.assertIn("One tick only -- exiting", text)
            # the tick persisted through the full chain + journaled the schedule state
            self.assertTrue(os.path.isfile(os.path.join(store, "run_store.jsonl")))
            self.assertTrue(os.path.isfile(
                os.path.join(store, "schedule_state_store.jsonl")))

    def test_second_cli_tick_resumes_the_journal_and_runs_nothing_new(self):
        with tempfile.TemporaryDirectory() as d:
            subs = self._write_subscriptions(d)
            store = os.path.join(d, "store")
            with redirect_stdout(io.StringIO()):
                pulse_cli_main(["--scheduled-tick", "--persist-dir", store,
                                "--tick-now", "2026-06-29T00:00:00Z",
                                "--subscriptions", subs])
            out = io.StringIO()
            with redirect_stdout(out):
                rc = pulse_cli_main(["--scheduled-tick", "--persist-dir", store,
                                     "--tick-now", "2026-06-29T00:01:00Z",
                                     "--subscriptions", subs])
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("resumed from journal", text)
            self.assertIn("ran (0):", text)
            self.assertIn("interval not elapsed", text)

    def test_flag_requires_its_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            subs = self._write_subscriptions(d)
            for argv in (
                ["--scheduled-tick", "--tick-now", _NOW, "--subscriptions", subs],
                ["--scheduled-tick", "--persist-dir", os.path.join(d, "s"),
                 "--subscriptions", subs],
                ["--scheduled-tick", "--persist-dir", os.path.join(d, "s"),
                 "--tick-now", _NOW],
            ):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as ctx:
                        pulse_cli_main(argv)
                self.assertNotEqual(ctx.exception.code, 0)

    def test_default_cli_without_the_flag_is_byte_identical(self):
        outputs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                out_dir = os.path.join(d, "out")
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = pulse_cli_main(["--watchlist", "IREN,NVDA",
                                         "--themes", "physical_ai,robotics",
                                         "--out", out_dir])
                self.assertEqual(rc, 0)
                pages = {}
                for base, _dirs, names in os.walk(out_dir):
                    for name in sorted(names):
                        path = os.path.join(base, name)
                        with open(path, "rb") as fh:
                            pages[os.path.relpath(path, out_dir)] = fh.read()
                outputs.append((buf.getvalue().replace(out_dir, "<out>"), pages))
        self.assertEqual(outputs[0][0], outputs[1][0])       # stdout byte-identical
        self.assertEqual(sorted(outputs[0][1]), sorted(outputs[1][1]))
        for name in outputs[0][1]:
            self.assertEqual(outputs[0][1][name], outputs[1][1][name],
                             "default CLI output drifted for {0}".format(name))
        # and the default path never mentions the opt-in tick
        self.assertNotIn("scheduled tick", outputs[0][0].lower())


# =========================================================================== #
# 8. NO daemon constructs / no execution reference / repo guards intact       #
# =========================================================================== #
class NoDaemonGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = _read(_ORCHESTRATOR_PY)
        cls.tree = ast.parse(cls.source)

    def test_no_banned_module_import(self):
        for node in ast.walk(self.tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for banned in _BANNED_IMPORT_ROOTS:
                    self.assertFalse(
                        name == banned or name.startswith(banned + "."),
                        "banned import {0!r} in orchestrator.py".format(name))

    def test_no_loop_async_or_timed_wait_construct(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in orchestrator.py")
            self.assertNotIsInstance(node, ast.AsyncFunctionDef)
            self.assertNotIsInstance(node, ast.Await)
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotIn(called, _BANNED_CALL_NAMES,
                                 "daemon-style call {0!r} in orchestrator.py".format(called))

    def test_import_has_no_side_effect_beyond_definitions(self):
        allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr,
                   ast.FunctionDef, ast.ClassDef)
        for node in self.tree.body:
            self.assertIsInstance(node, allowed)
            if isinstance(node, ast.Expr):      # only the docstring
                self.assertIsInstance(node.value, ast.Constant)

    def test_no_execution_or_trading_word_anywhere(self):
        low = self.source.lower()
        for word in _EXECUTION_WORDS:
            self.assertIsNone(re.search(r"\b{0}\b".format(word), low),
                              "execution-adjacent word {0!r} in orchestrator.py".format(word))

    def test_no_wall_clock_or_randomness(self):
        for token in _WALL_CLOCK_TOKENS:
            self.assertNotIn(token, self.source, "wall-clock call {0!r}".format(token))
        self.assertIsNone(re.search(r"\brandom\b|\brandint\b|\buuid\b", self.source.lower()))

    def test_repo_wide_import_guard_still_holds_with_orchestrator_present(self):
        prod_banned = ("socket", "requests", "urllib", "http", "sched", "schedule",
                       "apscheduler", "crontab", "asyncio", "threading", "multiprocessing",
                       "subprocess", "smtplib", "ftplib", "socketserver", "broker")
        py_files = []
        for base, _dirs, names in os.walk(_PKG_DIR):
            py_files.extend(os.path.join(base, n) for n in names if n.endswith(".py"))
        self.assertIn(_ORCHESTRATOR_PY, py_files)
        for path in sorted(py_files):
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                for name in names:
                    for banned in prod_banned:
                        self.assertFalse(
                            name == banned or name.startswith(banned + "."),
                            "banned import {0!r} in {1}".format(name, path))

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()

    def test_exports_are_additive_on_the_package(self):
        for name in ("Subscription", "TickResult", "PulseOrchestrator", "run_due_pulses",
                     "scheduled_policy_for", "load_schedule_state", "append_schedule_state",
                     "ScheduleStateStore"):
            self.assertTrue(hasattr(rm, name), "reality_mesh.{0} missing".format(name))


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
        now = "2026-06-29T00:00:00Z"
        a = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=now)
        b = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=now)
        self.assertEqual(repr(a.signals), repr(b.signals))
        self.assertEqual(repr(a.theme_pulses), repr(b.theme_pulses))
        self.assertEqual(repr(a.clusters), repr(b.clusters))


if __name__ == "__main__":
    unittest.main()
