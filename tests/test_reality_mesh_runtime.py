"""IMPLEMENTATION-013A -- Reality Mesh runtime objects (Phase-013).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE against in-process constructions --
no fixture endpoint, no network, no scheduler, no broker. It proves the RUNTIME_CONTRACT_013
invariants the gate enforces for the manual/on-demand pulse runtime (TEST_MATRIX_013 §A1-A5 +
the global guardrails §I):

* A1 -- PulseRun / AgentRunContext / AgentRunResult / AgentHealthRecord / ReplayRequest /
  ReplayResult all construct, are frozen, and default cleanly;
* A2 -- PulseRun.trigger_type accepts ``manual`` and (since the 015B unlock per
  ADR-CANDIDATE-015) ``scheduled``, and REJECTS ``streaming`` (still RESERVED/DEFERRED);
* A3 -- AgentRunContext.network_allowed defaults False; there is NO broker_allowed(-true) field;
* A4 -- AgentRunResult.status is limited to {success,partial,failed,skipped,blocked_by_policy};
* A5 -- counts are integer VOLUMES; NO order/score/rank/rating/buy-sell field on ANY object;
* I  -- the runtime module imports no network/scheduler/broker module and defines no
  ``*score`` / ``*rank`` function (AST guards); the whole suite builds under a socket
  kill-switch; timestamps are injected (byte-identical); the demo default stays byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, dataclass, fields, is_dataclass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import labels as L
from reality_mesh import runtime as R

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_RUNTIME_PY = os.path.join(_PKG_DIR, "runtime.py")

# The six runtime objects this slice defines.
_THE_SIX = (
    R.PulseRun,
    R.AgentRunContext,
    R.AgentRunResult,
    R.AgentHealthRecord,
    R.ReplayRequest,
    R.ReplayResult,
)

# Field-name tokens forbidden on ANY runtime object (labels/volumes, not trades / metrics).
_BANNED_FIELD_TOKENS = (
    "buy", "sell", "hold", "order", "trade", "broker", "score", "rank", "rating",
    "investab",
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _one_of_each():
    """A fully-populated valid instance of every one of the 6 runtime objects."""
    return {
        "pulse_run": R.PulseRun(
            run_id="RUN1", started_at="2026-06-29T00:00:00Z",
            completed_at="2026-06-29T00:01:00Z", mode="pulse", trigger_type="manual",
            watchlist=("IREN",), themes=("physical_ai",),
            source_adapters_requested=("sec",), source_adapters_used=("sec",),
            agents_requested=("a1", "a2"), agents_run=("a1",), agents_failed=("a2",),
            events_created=3, findings_created=2, signals_created=1,
            theme_pulses_created=1, data_quality_status="degraded",
            generated_outputs=("generated/pulse/RUN1.json",),
            schema_version="013.1", runtime_version="013A"),
        "context": R.AgentRunContext(
            run_id="RUN1", agent_id="tattva.market_regime", mode="pulse",
            watchlist=("IREN",), themes=("physical_ai",), input_event_ids=("E1",),
            allowed_sources=("canonical", "primary"),
            started_at="2026-06-29T00:00:00Z", timeout_policy="soft_30s",
            fixture_mode=True, network_allowed=False),
        "result": R.AgentRunResult(
            run_id="RUN1", agent_id="tattva.market_regime", status="success",
            started_at="2026-06-29T00:00:00Z", completed_at="2026-06-29T00:00:05Z",
            input_event_ids=("E1",), finding_ids=("F1",),
            warnings=("w1",), errors=(), data_gaps=("g1",), conflicts=("c1",),
            health_status="healthy"),
        "health": R.AgentHealthRecord(
            agent_id="tattva.market_regime", last_run_id="RUN1", last_status="success",
            failure_count=0, last_error="", last_success_at="2026-06-29T00:00:05Z",
            last_failure_at="", degraded_reason=""),
        "replay_req": R.ReplayRequest(
            run_id="RUN1", ticker="IREN", theme="physical_ai",
            time_window=("2026-06-01T00:00:00Z", "2026-06-29T00:00:00Z"),
            source_filter=("sec",), agent_filter=("tattva.market_regime",),
            include_raw_payloads=True, include_generated_outputs=True),
        "replay_res": R.ReplayResult(
            replay_id="RP1", source_run_id="RUN1", events_replayed=3,
            findings_replayed=2, signals_replayed=1,
            outputs_reconstructed=("generated/pulse/RUN1.json",),
            differences=(), deterministic_match=True),
    }


# =========================================================================== #
# A1. Construction / frozen / defaults                                        #
# =========================================================================== #
class ConstructionTests(unittest.TestCase):
    def test_each_object_builds(self):
        objs = _one_of_each()
        self.assertEqual(len(objs), 6)
        for name, obj in objs.items():
            self.assertTrue(is_dataclass(obj), name)

    def test_minimal_construction_and_defaults(self):
        pr = R.PulseRun(run_id="R")
        self.assertEqual(pr.mode, "demo")            # demo stays the DEFAULT
        self.assertEqual(pr.trigger_type, "manual")  # manual-only default
        self.assertEqual(pr.events_created, 0)
        self.assertEqual(pr.watchlist, tuple())
        self.assertEqual(pr.data_quality_status, "")  # explicit gap, not fabricated

        ctx = R.AgentRunContext(run_id="R", agent_id="a")
        self.assertFalse(ctx.network_allowed)        # offline by default
        self.assertTrue(ctx.fixture_mode)

        R.AgentRunResult(run_id="R", agent_id="a")
        R.AgentHealthRecord(agent_id="a")
        R.ReplayRequest(run_id="R")
        R.ReplayResult(replay_id="RP", source_run_id="R")

    def test_objects_are_frozen(self):
        for obj in _one_of_each().values():
            first = fields(obj)[0].name
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, first, "mutated")

    def test_required_ids_rejected_when_empty(self):
        for build in (
            lambda: R.PulseRun(run_id=""),
            lambda: R.AgentRunContext(run_id="", agent_id="a"),
            lambda: R.AgentRunContext(run_id="R", agent_id=""),
            lambda: R.AgentRunResult(run_id="", agent_id="a"),
            lambda: R.AgentRunResult(run_id="R", agent_id=""),
            lambda: R.AgentHealthRecord(agent_id=""),
            lambda: R.ReplayResult(replay_id="", source_run_id="R"),
            lambda: R.ReplayResult(replay_id="RP", source_run_id=""),
            lambda: R.ReplayRequest(),   # unscoped replay rejected
        ):
            with self.assertRaises(ValueError):
                build()

    def test_replay_request_scoped_by_any_filter(self):
        R.ReplayRequest(run_id="R")
        R.ReplayRequest(ticker="IREN")
        R.ReplayRequest(theme="physical_ai")
        R.ReplayRequest(time_window=("a", "b"))

    def test_runtime_objects_registry(self):
        self.assertEqual(R.RUNTIME_OBJECTS, _THE_SIX)
        # exported from the package top-level (additive)
        for cls in _THE_SIX:
            self.assertIs(getattr(rm, cls.__name__), cls)


# =========================================================================== #
# A2. trigger_type manual/scheduled (015B unlock); streaming reserved ->      #
#     rejected                                                                #
# =========================================================================== #
class TriggerTypeTests(unittest.TestCase):
    def test_manual_accepted(self):
        self.assertEqual(R.PulseRun(run_id="R", trigger_type="manual").trigger_type, "manual")
        self.assertEqual(R.PulseRun(run_id="R").trigger_type, "manual")   # default

    def test_scheduled_accepted_since_015b(self):
        # Unlocked by IMPLEMENTATION-015B per ADR-CANDIDATE-015 (recorded only by the
        # explicitly-started orchestrator, with policy attribution -- see
        # test_reality_mesh_orchestrator.py).
        run = R.PulseRun(run_id="R", trigger_type="scheduled")
        self.assertEqual(run.trigger_type, "scheduled")

    def test_streaming_still_rejected(self):
        with self.assertRaises(ValueError):
            R.PulseRun(run_id="R", trigger_type="streaming")

    def test_reserved_error_message_is_clear(self):
        try:
            R.PulseRun(run_id="R", trigger_type="streaming")
            self.fail("expected ValueError")
        except ValueError as exc:
            self.assertIn("RESERVED", str(exc))

    def test_unknown_trigger_type_rejected(self):
        with self.assertRaises(ValueError):
            R.PulseRun(run_id="R", trigger_type="cron")

    def test_trigger_vocabularies(self):
        self.assertEqual(L.ALLOWED_TRIGGER_TYPES, frozenset({"manual", "scheduled"}))
        self.assertEqual(L.RESERVED_TRIGGER_TYPES, frozenset({"streaming"}))
        self.assertTrue(L.is_trigger_type("manual"))
        self.assertTrue(L.is_trigger_type("scheduled"))
        self.assertFalse(L.is_trigger_type("streaming"))
        self.assertTrue(L.is_reserved_trigger_type("streaming"))
        self.assertFalse(L.is_reserved_trigger_type("scheduled"))


# =========================================================================== #
# A3. offline-by-default; no broker_allowed; forbidden outputs merged          #
# =========================================================================== #
class ContextBoundaryTests(unittest.TestCase):
    def test_network_allowed_defaults_false(self):
        self.assertFalse(R.AgentRunContext(run_id="R", agent_id="a").network_allowed)

    def test_no_broker_allowed_field_exists(self):
        names = {f.name for f in fields(R.AgentRunContext)}
        self.assertNotIn("broker_allowed", names)
        # and no broker/order field on the context at all
        for name in names:
            for tok in ("broker", "order"):
                self.assertNotIn(tok, name.lower())

    def test_forbidden_outputs_always_include_the_four(self):
        ctx = R.AgentRunContext(run_id="R", agent_id="a")
        for use in ("broker_order", "auto_execute", "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, ctx.forbidden_outputs)
        # even a caller-supplied set gets the four merged in
        ctx2 = R.AgentRunContext(run_id="R", agent_id="a", forbidden_outputs=("order",))
        for use in L.DEFAULT_FORBIDDEN_DOWNSTREAM_USES:
            self.assertIn(use, ctx2.forbidden_outputs)

    def test_allowed_sources_must_be_authorities(self):
        R.AgentRunContext(run_id="R", agent_id="a", allowed_sources=("canonical", "rumor"))
        with self.assertRaises(ValueError):
            R.AgentRunContext(run_id="R", agent_id="a", allowed_sources=("supreme",))

    def test_forbidden_outputs_must_be_forbidden_uses(self):
        with self.assertRaises(ValueError):
            R.AgentRunContext(run_id="R", agent_id="a", forbidden_outputs=("nonsense",))


# =========================================================================== #
# A4. AgentRunResult.status closed vocabulary                                  #
# =========================================================================== #
class AgentRunStatusTests(unittest.TestCase):
    def test_all_five_statuses_accepted(self):
        for status in ("success", "partial", "failed", "skipped", "blocked_by_policy"):
            self.assertEqual(
                R.AgentRunResult(run_id="R", agent_id="a", status=status).status, status)

    def test_invalid_status_rejected(self):
        for bad in ("succeeded", "ok", "error", "0.9"):
            with self.assertRaises(ValueError):
                R.AgentRunResult(run_id="R", agent_id="a", status=bad)

    def test_status_vocabulary(self):
        self.assertEqual(
            L.AGENT_RUN_STATUSES,
            frozenset({"success", "partial", "failed", "skipped", "blocked_by_policy"}))

    def test_health_and_run_status_closed(self):
        R.AgentRunResult(run_id="R", agent_id="a", health_status="degraded")
        with self.assertRaises(ValueError):
            R.AgentRunResult(run_id="R", agent_id="a", health_status="fine")
        R.PulseRun(run_id="R", data_quality_status="blocked_by_policy")
        with self.assertRaises(ValueError):
            R.PulseRun(run_id="R", data_quality_status="great")
        with self.assertRaises(ValueError):
            R.PulseRun(run_id="R", mode="live")   # not a RUN_MODE


# =========================================================================== #
# A5. counts are volumes; NO trade/score/rank field on any runtime object      #
# =========================================================================== #
class NoTradeOrScoreTests(unittest.TestCase):
    def test_no_object_has_trade_or_score_field(self):
        for cls in _THE_SIX:
            for f in fields(cls):
                low = f.name.lower()
                for tok in _BANNED_FIELD_TOKENS:
                    self.assertNotIn(
                        tok, low,
                        "{0}.{1} contains banned token {2!r}".format(
                            cls.__name__, f.name, tok))
            # reuse the 012A structural guard shape
            R.assert_no_trade_fields(cls)

    def test_assert_no_trade_fields_catches_a_violation(self):
        @dataclass(frozen=True)
        class Sneaky:
            hidden_score: float = 0.0
        with self.assertRaises(AssertionError):
            R.assert_no_trade_fields(Sneaky)

    def test_count_fields_are_integer_volumes(self):
        pr = _one_of_each()["pulse_run"]
        for name in ("events_created", "findings_created", "signals_created",
                     "theme_pulses_created"):
            self.assertIsInstance(getattr(pr, name), int)
        self.assertIsInstance(_one_of_each()["health"].failure_count, int)
        rr = _one_of_each()["replay_res"]
        for name in ("events_replayed", "findings_replayed", "signals_replayed"):
            self.assertIsInstance(getattr(rr, name), int)

    def test_deterministic_match_is_bool(self):
        self.assertIsInstance(_one_of_each()["replay_res"].deterministic_match, bool)
        self.assertFalse(R.ReplayResult(replay_id="RP", source_run_id="R").deterministic_match)


# =========================================================================== #
# I. Guardrails -- AST, offline, deterministic, demo byte-identical             #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "beautifulsoup4", "selenium", "scrapy", "lxml", "mechanize", "pycurl",
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

    def test_runtime_imports_no_network_scheduler_or_broker(self):
        tree = ast.parse(self._read(_RUNTIME_PY))
        for m in self._imported_modules(tree):
            self.assertNotIn(m, self._NET, "runtime imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "runtime imports forbidden {0}".format(m))

    def test_runtime_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_RUNTIME_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "runtime defines {0}".format(node.name))

    def test_runtime_source_has_no_broker_scheduler_or_order_affordance(self):
        blob = self._read(_RUNTIME_PY).lower()
        for banned in ("place_order", "submit_order", "execute_trade",
                       "schedule.every", "cron", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_no_wall_clock_in_id_or_timestamp_path(self):
        blob = self._read(_RUNTIME_PY)
        for banned in ("time.time(", "datetime.now(", "datetime.utcnow(", "time.monotonic("):
            self.assertNotIn(banned, blob, "wall-clock call: {0}".format(banned))

    def test_construction_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            objs = _one_of_each()
        finally:
            socket.socket = real
        self.assertEqual(objs["pulse_run"].trigger_type, "manual")

    def test_builds_are_byte_identical_deterministic(self):
        a = _one_of_each()
        b = _one_of_each()
        for name in a:
            self.assertEqual(repr(a[name]), repr(b[name]), name)


# =========================================================================== #
# I (cont). Existing behaviour unaffected -- demo default byte-identical        #
# =========================================================================== #
class ExistingBehaviourTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_rt_a_")
        d2 = tempfile.mkdtemp(prefix="rm_rt_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))
        with open(p1["universe.html"], encoding="utf-8") as fh:
            self.assertNotIn("reality_mesh", fh.read())


if __name__ == "__main__":
    unittest.main()
