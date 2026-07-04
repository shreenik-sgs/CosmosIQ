"""IMPLEMENTATION-015A -- PulseScheduler CORE (cadence + calendar + state + throttle/backoff).

Phase 015 is the FIRST phase in which a scheduler is permitted (SPEC-013 §D; unlocked by the
master production authorization now that the 013 runtime / persistence / replay / observability
/ data-quality gates exist -- see ADR-CANDIDATE-015_SCHEDULED_PULSE_UNLOCK.md). This suite
proves the 015A discipline:

* cadence policies are closed-validated DATA (sub-minute cadence rejected; interval >= floor);
* the market-hours calendar is pure string/date math over an injected ``now`` (weekday session
  open; weekends / after-hours / holidays closed);
* ``due_policies`` is a PURE tick decision (interval elapsed AND market hours AND not paused /
  backed-off / throttled) -- it runs nothing;
* ``record_run`` success resets failures/backoff; failure sets DETERMINISTIC exponential
  backoff (now + min(2**failures * interval, 24h), no jitter, no randomness);
* pause / resume (per-policy and global) and the global max_runs_per_hour throttle work;
* every transition returns a NEW frozen object -- originals byte-unchanged;
* serialization round-trips through plain deterministic dicts (JSONL-friendly);
* NO daemon construct exists: the module imports no scheduler/daemon/network/process module,
  contains no while-loop / async / timed-wait call, defines nothing that references trading
  or an execution affordance, and never reads the wall clock;
* the existing repo-wide guards still hold with scheduler.py present, and the demo default +
  default pulse remain byte-identical (untouched paths).

Entirely OFFLINE and deterministic: injected ``now`` ISO strings everywhere; a socket
kill-switch guards the whole module.
"""

from __future__ import annotations

import ast
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import scheduler as SC

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_SCHEDULER_PY = os.path.join(_PKG_DIR, "scheduler.py")

# A Monday. 15:00 UTC is inside the default 14:30-21:00 UTC session.
_MONDAY_OPEN = "2026-06-29T15:00:00Z"
_MONDAY_PREOPEN = "2026-06-29T14:29:00Z"
_MONDAY_AT_OPEN = "2026-06-29T14:30:00Z"
_MONDAY_AT_CLOSE = "2026-06-29T21:00:00Z"
_MONDAY_NIGHT = "2026-06-29T02:00:00Z"
_SATURDAY = "2026-06-27T15:00:00Z"
_SUNDAY = "2026-06-28T15:00:00Z"
_FRIDAY_HOLIDAY = "2026-07-03T15:00:00Z"

# The same repo-wide ban lists the 012/013 guards enforce (kept in sync by the tests they
# live in; re-asserted here over scheduler.py specifically).
_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "asyncio", "threading", "multiprocessing",
                        "subprocess", "smtplib", "ftplib", "socketserver", "broker",
                        "signal", "time", "random", "select", "selectors", "queue")
_BANNED_CALL_NAMES = ("sleep", "run_forever", "serve_forever", "start_polling", "Thread",
                      "Timer", "Process", "fork", "spawn", "run_in_executor", "setdaemon")
# Word-level execution/trading vocabulary -- the scheduler core may not even MENTION it.
_EXECUTION_WORDS = ("buy", "sell", "hold", "order", "orders", "trade", "trades", "trading",
                    "broker", "execute", "execution", "rebalance", "rebalancing", "position",
                    "alert", "alerts")
_WALL_CLOCK_TOKENS = ("time.time(", "datetime.now(", "datetime.utcnow(", "utcnow(",
                      "time.monotonic(", "perf_counter(")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline scheduler suite")


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


def _one_policy_schedule(interval=5, floor=1, market_hours_only=False,
                         max_runs_per_hour=60):
    policy = SC.CadencePolicy(
        policy_id="cadence.test", discipline_or_adapter="market_regime",
        interval_minutes=interval, market_hours_only=market_hours_only,
        min_interval_minutes=floor)
    return SC.PulseSchedule(
        policies=(policy,),
        states=(SC.ScheduleState(policy_id="cadence.test"),),
        max_runs_per_hour=max_runs_per_hour)


# =========================================================================== #
# 1. CadencePolicy -- closed validation + the accepted defaults as DATA        #
# =========================================================================== #
class CadencePolicyTests(unittest.TestCase):
    def test_valid_policy_constructs_frozen(self):
        p = SC.CadencePolicy(policy_id="cadence.x", discipline_or_adapter="market_regime",
                             interval_minutes=15, min_interval_minutes=5)
        with self.assertRaises(FrozenInstanceError):
            p.interval_minutes = 1  # type: ignore[misc]

    def test_sub_minute_cadence_rejected(self):
        for bad_floor in (0, -1):
            with self.assertRaises(ValueError):
                SC.CadencePolicy(policy_id="cadence.x", discipline_or_adapter="d",
                                 interval_minutes=5, min_interval_minutes=bad_floor)

    def test_interval_below_floor_rejected(self):
        with self.assertRaises(ValueError):
            SC.CadencePolicy(policy_id="cadence.x", discipline_or_adapter="d",
                             interval_minutes=4, min_interval_minutes=5)

    def test_required_ids_and_integer_minutes(self):
        with self.assertRaises(ValueError):
            SC.CadencePolicy(policy_id="", discipline_or_adapter="d", interval_minutes=5)
        with self.assertRaises(ValueError):
            SC.CadencePolicy(policy_id="p", discipline_or_adapter="  ", interval_minutes=5)
        with self.assertRaises(ValueError):
            SC.CadencePolicy(policy_id="p", discipline_or_adapter="d",
                             interval_minutes=5.5)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            SC.CadencePolicy(policy_id="p", discipline_or_adapter="d",
                             interval_minutes=True)  # type: ignore[arg-type]

    def test_default_policies_are_the_accepted_cadence_bands(self):
        by_id = {p.policy_id: p for p in SC.DEFAULT_CADENCE_POLICIES}
        self.assertEqual(len(by_id), len(SC.DEFAULT_CADENCE_POLICIES))  # unique ids
        # social / news: 1-5 min, active themes only, not market-hours-bound
        for pid in ("cadence.social_narrative", "cadence.news_filings"):
            p = by_id[pid]
            self.assertEqual((p.min_interval_minutes, p.interval_minutes), (1, 5))
            self.assertIn("active_themes", p.active_only_for)
            self.assertFalse(p.market_hours_only)
        # market / sector / theme rotation: 5-15 min, market hours only
        for pid in ("cadence.market_regime", "cadence.sector_rotation",
                    "cadence.theme_rotation"):
            p = by_id[pid]
            self.assertEqual((p.min_interval_minutes, p.interval_minutes), (5, 15))
            self.assertTrue(p.market_hours_only)
        # technical: 1-15 min, market hours only
        p = by_id["cadence.technical_regime"]
        self.assertEqual((p.min_interval_minutes, p.interval_minutes), (1, 15))
        self.assertTrue(p.market_hours_only)
        # SEC hourly; IR/transcripts daily; macro hourly-band
        self.assertEqual(by_id["cadence.sec_filings"].interval_minutes, 60)
        self.assertEqual(by_id["cadence.company_documents"].interval_minutes,
                         SC.MINUTES_PER_DAY)
        self.assertEqual(by_id["cadence.macro_regime"].interval_minutes, 60)
        # learning daily / weekly
        self.assertEqual(by_id["cadence.learning_daily"].interval_minutes,
                         SC.MINUTES_PER_DAY)
        self.assertEqual(by_id["cadence.learning_weekly"].interval_minutes,
                         SC.MINUTES_PER_WEEK)
        # every default validates its own floor rule
        for p in SC.DEFAULT_CADENCE_POLICIES:
            self.assertGreaterEqual(p.interval_minutes, p.min_interval_minutes)
            self.assertGreaterEqual(p.min_interval_minutes, 1)


# =========================================================================== #
# 2. MarketHoursCalendar -- pure injected-now session math                     #
# =========================================================================== #
class MarketHoursCalendarTests(unittest.TestCase):
    def test_weekday_session_open(self):
        cal = SC.DEFAULT_MARKET_HOURS
        self.assertTrue(cal.is_market_open(_MONDAY_OPEN))
        self.assertTrue(cal.is_market_open(_MONDAY_AT_OPEN))        # open inclusive

    def test_weekday_outside_session_closed(self):
        cal = SC.DEFAULT_MARKET_HOURS
        self.assertFalse(cal.is_market_open(_MONDAY_PREOPEN))
        self.assertFalse(cal.is_market_open(_MONDAY_AT_CLOSE))      # close exclusive
        self.assertFalse(cal.is_market_open(_MONDAY_NIGHT))

    def test_weekend_closed(self):
        cal = SC.DEFAULT_MARKET_HOURS
        self.assertFalse(cal.is_market_open(_SATURDAY))
        self.assertFalse(cal.is_market_open(_SUNDAY))

    def test_holiday_closed(self):
        cal = SC.MarketHoursCalendar(holidays=("2026-07-03",))
        self.assertFalse(cal.is_market_open(_FRIDAY_HOLIDAY))
        self.assertTrue(SC.DEFAULT_MARKET_HOURS.is_market_open(_FRIDAY_HOLIDAY))
        self.assertEqual(SC.DEFAULT_MARKET_HOURS.holidays, ())      # empty by default

    def test_configurable_open_close(self):
        cal = SC.MarketHoursCalendar(open_utc="08:00", close_utc="16:30")
        self.assertTrue(cal.is_market_open("2026-06-29T08:00:00Z"))
        self.assertFalse(cal.is_market_open("2026-06-29T16:30:00Z"))

    def test_invalid_calendar_rejected(self):
        with self.assertRaises(ValueError):
            SC.MarketHoursCalendar(open_utc="21:00", close_utc="14:30")   # inverted
        with self.assertRaises(ValueError):
            SC.MarketHoursCalendar(open_utc="2430")                       # not HH:MM
        with self.assertRaises(ValueError):
            SC.MarketHoursCalendar(holidays=("July 4",))                  # not YYYY-MM-DD

    def test_bad_now_rejected_never_guessed(self):
        with self.assertRaises(ValueError):
            SC.DEFAULT_MARKET_HOURS.is_market_open("")
        with self.assertRaises(ValueError):
            SC.DEFAULT_MARKET_HOURS.is_market_open("not-a-timestamp")


# =========================================================================== #
# 3. due_policies -- the pure tick decision                                    #
# =========================================================================== #
class DuePoliciesTests(unittest.TestCase):
    def test_never_run_policy_is_immediately_due(self):
        sched = _one_policy_schedule()
        self.assertEqual(SC.due_policies(sched, _MONDAY_OPEN), ("cadence.test",))

    def test_not_due_before_interval_due_after(self):
        sched = SC.record_run(_one_policy_schedule(interval=5), "cadence.test",
                              "2026-06-29T15:00:00Z", True)
        self.assertEqual(SC.due_policies(sched, "2026-06-29T15:04:00Z"), ())
        self.assertEqual(SC.due_policies(sched, "2026-06-29T15:05:00Z"),
                         ("cadence.test",))

    def test_market_hours_only_respected(self):
        sched = _one_policy_schedule(market_hours_only=True)
        self.assertEqual(SC.due_policies(sched, _MONDAY_OPEN), ("cadence.test",))
        for closed_now in (_MONDAY_NIGHT, _SATURDAY, _SUNDAY):
            self.assertEqual(SC.due_policies(sched, closed_now), ())
        # injectable holiday calendar closes it too
        cal = SC.MarketHoursCalendar(holidays=("2026-06-29",))
        self.assertEqual(SC.due_policies(sched, _MONDAY_OPEN, calendar=cal), ())

    def test_paused_policy_never_due(self):
        sched = SC.pause(_one_policy_schedule(), "cadence.test", _MONDAY_OPEN)
        self.assertEqual(SC.due_policies(sched, _MONDAY_OPEN), ())
        resumed = SC.resume(sched, "cadence.test", _MONDAY_OPEN)
        self.assertEqual(SC.due_policies(resumed, _MONDAY_OPEN), ("cadence.test",))

    def test_paused_all_nothing_due(self):
        sched = SC.pause(SC.build_default_schedule(), SC.ALL_POLICIES, _MONDAY_OPEN)
        self.assertTrue(sched.paused_all)
        self.assertEqual(SC.due_policies(sched, _MONDAY_OPEN), ())
        resumed = SC.resume(sched, SC.ALL_POLICIES, _MONDAY_OPEN)
        self.assertFalse(resumed.paused_all)
        self.assertTrue(SC.due_policies(resumed, _MONDAY_OPEN))

    def test_backoff_blocks_until_backoff_until(self):
        sched = SC.record_run(_one_policy_schedule(interval=5), "cadence.test",
                              "2026-06-29T15:00:00Z", False)
        state = SC.state_for(sched, "cadence.test")
        self.assertEqual(state.backoff_until, "2026-06-29T15:10:00Z")  # 2**1 * 5 min
        # interval (5m) has elapsed at 15:09 but backoff still blocks
        self.assertEqual(SC.due_policies(sched, "2026-06-29T15:09:00Z"), ())
        self.assertEqual(SC.due_policies(sched, "2026-06-29T15:10:00Z"),
                         ("cadence.test",))

    def test_throttle_blocks_past_max_runs_per_hour(self):
        sched = _one_policy_schedule(interval=1, max_runs_per_hour=3)
        for minute in (0, 1, 2):
            now = "2026-06-29T15:0{0}:00Z".format(minute)
            self.assertFalse(SC.throttled(sched, now))
            sched = SC.record_run(sched, "cadence.test", now, True)
        self.assertTrue(SC.throttled(sched, "2026-06-29T15:03:00Z"))
        self.assertEqual(SC.due_policies(sched, "2026-06-29T15:03:00Z"), ())
        # the window expires 60 minutes after it opened -> runnable again
        self.assertFalse(SC.throttled(sched, "2026-06-29T16:00:00Z"))
        self.assertEqual(SC.due_policies(sched, "2026-06-29T16:00:00Z"),
                         ("cadence.test",))

    def test_default_schedule_multi_policy_decision(self):
        sched = SC.build_default_schedule()
        due = SC.due_policies(sched, _MONDAY_OPEN)
        self.assertEqual(sorted(due), sorted(p.policy_id for p in
                                             SC.DEFAULT_CADENCE_POLICIES))
        # off-hours: market-hours-only policies drop out; the rest stay due
        off_hours = set(SC.due_policies(sched, _MONDAY_NIGHT))
        self.assertNotIn("cadence.market_regime", off_hours)
        self.assertNotIn("cadence.technical_regime", off_hours)
        self.assertIn("cadence.social_narrative", off_hours)
        self.assertIn("cadence.sec_filings", off_hours)

    def test_unknown_policy_rejected(self):
        sched = _one_policy_schedule()
        with self.assertRaises(ValueError):
            SC.state_for(sched, "cadence.nope")
        with self.assertRaises(ValueError):
            SC.record_run(sched, "cadence.nope", _MONDAY_OPEN, True)
        with self.assertRaises(ValueError):
            SC.pause(sched, "cadence.nope", _MONDAY_OPEN)


# =========================================================================== #
# 4. record_run -- success resets; failure backs off exponentially             #
# =========================================================================== #
class RecordRunTests(unittest.TestCase):
    def test_success_resets_failures_and_backoff(self):
        sched = _one_policy_schedule(interval=5)
        sched = SC.record_run(sched, "cadence.test", "2026-06-29T15:00:00Z", False)
        sched = SC.record_run(sched, "cadence.test", "2026-06-29T15:10:00Z", True)
        state = SC.state_for(sched, "cadence.test")
        self.assertEqual(state.consecutive_failures, 0)
        self.assertEqual(state.backoff_until, "")
        self.assertEqual(state.last_run_at, "2026-06-29T15:10:00Z")

    def test_failure_backoff_is_exponential_and_capped(self):
        sched = _one_policy_schedule(interval=5)
        expectations = (
            ("2026-06-29T15:00:00Z", 1, "2026-06-29T15:10:00Z"),   # 2**1*5 = 10m
            ("2026-06-29T15:10:00Z", 2, "2026-06-29T15:30:00Z"),   # 2**2*5 = 20m
            ("2026-06-29T15:30:00Z", 3, "2026-06-29T16:10:00Z"),   # 2**3*5 = 40m
        )
        for now, failures, until in expectations:
            sched = SC.record_run(sched, "cadence.test", now, False)
            state = SC.state_for(sched, "cadence.test")
            self.assertEqual(state.consecutive_failures, failures)
            self.assertEqual(state.backoff_until, until)
        # a long-interval policy hits the 24h cap on the FIRST failure
        daily = _one_policy_schedule(interval=SC.MINUTES_PER_DAY, floor=60)
        daily = SC.record_run(daily, "cadence.test", "2026-06-29T15:00:00Z", False)
        self.assertEqual(SC.state_for(daily, "cadence.test").backoff_until,
                         "2026-06-30T15:00:00Z")                    # capped at 24h

    def test_backoff_is_deterministic_no_jitter(self):
        a = SC.record_run(_one_policy_schedule(), "cadence.test",
                          "2026-06-29T15:00:00Z", False)
        b = SC.record_run(_one_policy_schedule(), "cadence.test",
                          "2026-06-29T15:00:00Z", False)
        self.assertEqual(SC.state_for(a, "cadence.test"),
                         SC.state_for(b, "cadence.test"))
        self.assertEqual(repr(a), repr(b))

    def test_throttle_window_reuse_and_restart(self):
        sched = _one_policy_schedule(interval=1)
        sched = SC.record_run(sched, "cadence.test", "2026-06-29T15:00:00Z", True)
        sched = SC.record_run(sched, "cadence.test", "2026-06-29T15:30:00Z", True)
        state = SC.state_for(sched, "cadence.test")
        self.assertEqual((state.window_started_at, state.runs_in_window),
                         ("2026-06-29T15:00:00Z", 2))               # window reused
        sched = SC.record_run(sched, "cadence.test", "2026-06-29T16:00:00Z", True)
        state = SC.state_for(sched, "cadence.test")
        self.assertEqual((state.window_started_at, state.runs_in_window),
                         ("2026-06-29T16:00:00Z", 1))               # window restarted


# =========================================================================== #
# 5. Frozen / append-style -- every transition is a NEW object                 #
# =========================================================================== #
class FrozenTransitionTests(unittest.TestCase):
    def test_states_are_frozen(self):
        state = SC.ScheduleState(policy_id="cadence.test")
        with self.assertRaises(FrozenInstanceError):
            state.paused = True  # type: ignore[misc]
        sched = _one_policy_schedule()
        with self.assertRaises(FrozenInstanceError):
            sched.paused_all = True  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            SC.DEFAULT_MARKET_HOURS.open_utc = "00:00"  # type: ignore[misc]

    def test_transitions_return_new_objects_originals_unchanged(self):
        original = _one_policy_schedule()
        before = repr(original)
        after_run = SC.record_run(original, "cadence.test", _MONDAY_OPEN, False)
        after_pause = SC.pause(original, "cadence.test", _MONDAY_OPEN)
        after_all = SC.pause(original, SC.ALL_POLICIES, _MONDAY_OPEN)
        for changed in (after_run, after_pause, after_all):
            self.assertIsNot(changed, original)
            self.assertNotEqual(repr(changed), before)
        self.assertEqual(repr(original), before)   # the input was NEVER mutated
        self.assertEqual(SC.state_for(original, "cadence.test").consecutive_failures, 0)

    def test_schedule_closed_validation(self):
        policy = SC.CadencePolicy(policy_id="p1", discipline_or_adapter="d",
                                  interval_minutes=5)
        with self.assertRaises(ValueError):
            SC.PulseSchedule(policies=(policy, policy))               # duplicate policy
        with self.assertRaises(ValueError):
            SC.PulseSchedule(policies=(policy,),
                             states=(SC.ScheduleState(policy_id="ghost"),))
        with self.assertRaises(ValueError):
            SC.PulseSchedule(policies=(policy,), max_runs_per_hour=0)
        with self.assertRaises(ValueError):
            SC.ScheduleState(policy_id="p1", consecutive_failures=-1)


# =========================================================================== #
# 6. Serialization -- deterministic plain dicts, round-trip stable             #
# =========================================================================== #
class SerializationTests(unittest.TestCase):
    def test_schedule_round_trip(self):
        sched = SC.build_default_schedule(max_runs_per_hour=30)
        sched = SC.record_run(sched, "cadence.market_regime", _MONDAY_OPEN, False)
        sched = SC.pause(sched, "cadence.social_narrative", _MONDAY_OPEN)
        data = SC.schedule_to_dict(sched)
        again = SC.schedule_from_dict(data)
        self.assertEqual(SC.schedule_to_dict(again), data)
        # behavior parity, not just shape parity
        self.assertEqual(sorted(SC.due_policies(sched, _MONDAY_OPEN)),
                         sorted(SC.due_policies(again, _MONDAY_OPEN)))
        self.assertEqual(again.max_runs_per_hour, 30)

    def test_dict_form_is_jsonl_friendly_and_byte_stable(self):
        sched = SC.build_default_schedule()
        line1 = json.dumps(SC.schedule_to_dict(sched), sort_keys=True,
                           separators=(",", ":"))
        line2 = json.dumps(SC.schedule_to_dict(SC.build_default_schedule()),
                           sort_keys=True, separators=(",", ":"))
        self.assertEqual(line1, line2)                              # byte-stable
        parsed = json.loads(line1)
        self.assertEqual([p["policy_id"] for p in parsed["policies"]],
                         sorted(p["policy_id"] for p in parsed["policies"]))

    def test_policy_state_calendar_round_trips(self):
        for policy in SC.DEFAULT_CADENCE_POLICIES:
            self.assertEqual(SC.policy_from_dict(SC.policy_to_dict(policy)), policy)
        state = SC.ScheduleState(policy_id="p", last_run_at=_MONDAY_OPEN,
                                 consecutive_failures=2, paused=True,
                                 backoff_until="2026-06-29T16:00:00Z",
                                 runs_in_window=3, window_started_at=_MONDAY_OPEN)
        self.assertEqual(SC.state_from_dict(SC.state_to_dict(state)), state)
        cal = SC.MarketHoursCalendar(open_utc="13:30", close_utc="20:00",
                                     holidays=("2026-12-25",))
        self.assertEqual(SC.calendar_from_dict(SC.calendar_to_dict(cal)), cal)


# =========================================================================== #
# 7. Determinism -- same injected inputs, same outputs, always                 #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_same_inputs_same_outputs(self):
        for now in (_MONDAY_OPEN, _MONDAY_NIGHT, _SATURDAY):
            a = SC.due_policies(SC.build_default_schedule(), now)
            b = SC.due_policies(SC.build_default_schedule(), now)
            self.assertEqual(a, b)
        a = SC.record_run(SC.build_default_schedule(), "cadence.sec_filings",
                          _MONDAY_OPEN, False)
        b = SC.record_run(SC.build_default_schedule(), "cadence.sec_filings",
                          _MONDAY_OPEN, False)
        self.assertEqual(repr(a), repr(b))

    def test_iso_offset_form_normalizes_identically(self):
        z = SC.record_run(_one_policy_schedule(), "cadence.test",
                          "2026-06-29T15:00:00Z", True)
        offset = SC.record_run(_one_policy_schedule(), "cadence.test",
                               "2026-06-29T15:00:00+00:00", True)
        self.assertEqual(repr(z), repr(offset))


# =========================================================================== #
# 8. NO daemon constructs / no execution reference / repo guards intact        #
# =========================================================================== #
class NoDaemonGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = _read(_SCHEDULER_PY)
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
                        "banned import {0!r} in scheduler.py".format(name))

    def test_no_loop_async_or_timed_wait_construct(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in scheduler.py")
            self.assertNotIsInstance(node, ast.AsyncFunctionDef)
            self.assertNotIsInstance(node, ast.Await)
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotIn(called, _BANNED_CALL_NAMES,
                                 "daemon-style call {0!r} in scheduler.py".format(called))

    def test_import_has_no_side_effect_beyond_data(self):
        # Top-level statements are imports, constants, dataclasses, and function defs --
        # nothing that could START anything.
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
                              "execution-adjacent word {0!r} in scheduler.py".format(word))

    def test_no_wall_clock_or_randomness(self):
        for token in _WALL_CLOCK_TOKENS:
            self.assertNotIn(token, self.source, "wall-clock call {0!r}".format(token))
        self.assertIsNone(re.search(r"\brandom\b|\brandint\b|\buuid\b", self.source.lower()))

    def test_no_function_named_like_a_metric(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNone(re.search(r"(score|rank|rating)", node.name.lower()),
                                  "banned fn name {0!r}".format(node.name))

    def test_repo_wide_import_guard_still_holds_with_scheduler_present(self):
        # The exact production-e2e sweep (§I): EVERY reality_mesh file, scheduler.py included.
        prod_banned = ("socket", "requests", "urllib", "http", "sched", "schedule",
                       "apscheduler", "crontab", "asyncio", "threading", "multiprocessing",
                       "subprocess", "smtplib", "ftplib", "socketserver", "broker")
        py_files = []
        for base, _dirs, names in os.walk(_PKG_DIR):
            py_files.extend(os.path.join(base, n) for n in names if n.endswith(".py"))
        self.assertIn(_SCHEDULER_PY, py_files)
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

    def test_reserved_trigger_types_still_rejected(self):
        # 015A DECIDES only; 015B unlocked 'scheduled' (with its explicit-start runner, per
        # ADR-CANDIDATE-015 -- see test_reality_mesh_orchestrator.py). 'streaming' stays
        # RESERVED and rejected.
        with self.assertRaises(ValueError):
            rm.PulseRun(run_id="X", trigger_type="streaming")
        self.assertEqual(
            rm.PulseRun(run_id="X", trigger_type="scheduled").trigger_type, "scheduled")


# =========================================================================== #
# 9. Untouched paths -- demo default + default pulse stay byte-identical       #
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
