"""IMPLEMENTATION-016A -- the CosmosIQ backend API: a PURE dispatcher, tested fully OFFLINE.

Phase 016's first product slice: ``cosmosiq_app.api.dispatch`` -- a pure function from a plain
request dict to a plain response dict over the 013B/015 stores. These tests exercise the
DISPATCHER ONLY: no server, no socket, no port. The operator-started shell
(``cosmosiq_app/server.py``) is deliberately NEVER imported here -- its safety properties
(127.0.0.1 default, --allow-remote refusal, honest banner) are asserted by READING its source.

The whole module runs under a socket kill-switch installed in ``setUpModule`` -- every seeded
pulse, dispatch call, replay, and journal write below is proven offline. Deterministic:
injected ``now`` strings only (dispatch never reads a wall clock -- AST-proven), caller-supplied
run ids, temp-dir JSONL stores.

Guardrails re-asserted here: 403 (with the manual-preview refusal) on ANY trade-like route;
append-only alert-ack / schedule-journal / settings-journal writes (byte-unchanged priors);
no credential value and no score/rank key in any response; the reality_mesh package untouched
(its own guards run elsewhere in the suite); the demo default byte-identical.
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

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import stores as S
from cosmosiq_app.api import (
    APP_NAME,
    EXECUTION_REFUSAL,
    SettingsStore,
    TRADE_PATH_TOKENS,
    dispatch,
)

_APP_DIR = os.path.join(_SRC, "cosmosiq_app")
_API_PY = os.path.join(_APP_DIR, "api.py")
_SERVER_PY = os.path.join(_APP_DIR, "server.py")
_MAIN_PY = os.path.join(_APP_DIR, "__main__.py")

_NOW1 = "2026-06-29T00:00:00Z"
_NOW2 = "2026-06-30T00:00:00Z"
_NOW3 = "2026-07-01T00:00:00Z"
_RUN1 = "RUN-API-1"
_SEEDED_ALERT_ID = "alert.RUN-API-1.theme-pulse-changed.seeded"

# Key tokens no response may carry (credential-like keys + score/rank/trade keys).
_BANNED_KEY_TOKENS = tuple(S.CREDENTIAL_KEY_TOKENS) + tuple(S.FORBIDDEN_FIELD_TOKENS)

# Value patterns that would mean a credential VALUE leaked into a response.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]{8,}"),
)

# Module roots whose import in api.py would mean network / server / clock capability crept
# into the PURE dispatcher.
_API_BANNED_IMPORT_ROOTS = (
    "socket", "socketserver", "http", "urllib", "requests", "ssl", "select", "selectors",
    "sched", "schedule", "asyncio", "threading", "multiprocessing", "subprocess",
    "smtplib", "ftplib", "time", "datetime", "random", "uuid",
)

# Attribute calls that would mean the dispatcher read a wall clock.
_WALL_CLOCK_ATTRS = ("now", "utcnow", "today", "time", "monotonic", "perf_counter", "sleep")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline CosmosIQ API tests")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


_STATE = {}
_ORIG_CONNECT = None


def _call(method, path, body=None, query=None, now=""):
    return dispatch({"method": method, "path": path, "query": query or {}, "body": body},
                    store_dir=_STATE["store_dir"], now=now)


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket

    store_dir = tempfile.mkdtemp(prefix="cosmosiq_api_store_")
    _STATE["store_dir"] = store_dir

    # Seed run 1 via the existing 012K/013F helpers (the store the API serves).
    pulse = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW1)
    pulse_run, replay, _panel = rm.persist_and_summarize(
        pulse, store_dir=store_dir, run_id=_RUN1, now=_NOW1)
    _STATE.update(pulse=pulse, pulse_run=pulse_run, seed_replay=replay)

    # Seed ONE alert into the append-only inbox (the endpoints under test are the inbox
    # read + ack surfaces, not the 015C diff engine -- that has its own suite).
    alert = rm.Alert(
        alert_id=_SEEDED_ALERT_ID, run_id=_RUN1, category="theme_pulse_changed",
        severity="notice",
        human_readable_reason="Theme pulse for 'physical_ai' changed state between run "
                              "RUN-API-0 and run RUN-API-1; evidence: seeded test record.",
        subject_themes=("physical_ai",), subject_refs=("tp.seeded",), created_at=_NOW1)
    rm.AlertStore(store_dir).append(alert, timestamp=_NOW1)

    # Run 2 THROUGH the API itself: the manual-pulse workflow, offline under the kill-switch.
    response = _call("POST", "/api/pulse",
                     body={"watchlist": ["IREN", "NVDA"],
                           "themes": ["physical_ai", "robotics"], "now": _NOW2})
    assert response["status"] == 200, response
    _STATE["pulse_response"] = response
    _STATE["run2"] = response["body"]["run_id"]


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _all_keys(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            for sub in _all_keys(value):
                yield sub
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            for sub in _all_keys(value):
                yield sub


def _all_string_values(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            for sub in _all_string_values(value):
                yield sub
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            for sub in _all_string_values(value):
                yield sub
    elif isinstance(obj, str):
        yield obj


# =========================================================================== #
# 1. Health + run history                                                      #
# =========================================================================== #
class HealthAndRunsTests(unittest.TestCase):
    def test_health_ok_with_store_and_counts(self):
        response = _call("GET", "/api/health")
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "application/json")
        body = response["body"]
        self.assertEqual(body["app"], APP_NAME)
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["store_dir_present"])
        self.assertEqual(body["counts"]["runs"], 2)
        self.assertGreater(body["counts"]["signals"], 0)
        self.assertEqual(body["counts"]["alerts"], 1)

    def test_runs_listed_newest_first_with_trigger_mode_volumes(self):
        body = _call("GET", "/api/runs")["body"]
        self.assertEqual(body["count"], 2)
        run_ids = [r["run_id"] for r in body["runs"]]
        self.assertEqual(run_ids, [_STATE["run2"], _RUN1])   # newest first
        for run in body["runs"]:
            self.assertEqual(run["trigger_type"], "manual")
            self.assertEqual(run["mode"], "pulse")
            self.assertGreaterEqual(run["signals_created"], 1)   # a volume count, not a score

    def test_run_detail_returns_health_and_gate_records(self):
        body = _call("GET", "/api/runs/{0}".format(_RUN1))["body"]
        self.assertEqual(body["run"]["run_id"], _RUN1)
        self.assertEqual(body["run"]["started_at"], _NOW1)
        self.assertGreaterEqual(len(body["agent_results"]), 5)   # the ledger health records
        for result in body["agent_results"]:
            self.assertIn(result["status"], ("success", "skipped", "partial", "failed"))
            self.assertIn(result["health_status"], ("healthy", "degraded", "failed"))
        categories = {r["category"] for r in body["data_quality_records"]}
        self.assertIn("gate_overall", categories)
        self.assertIn("replayability", categories)               # the gate verdicts landed
        self.assertIn(body["gate_overall"], ("healthy", "degraded", "failed"))

    def test_unknown_run_is_404(self):
        response = _call("GET", "/api/runs/RUN-NOPE")
        self.assertEqual(response["status"], 404)
        self.assertIn("RUN-NOPE", response["body"]["error"])

    def test_dispatch_is_deterministic_for_identical_requests(self):
        first = _call("GET", "/api/runs")
        second = _call("GET", "/api/runs")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


# =========================================================================== #
# 2. Typed per-run record endpoints (labels only -- never a score)              #
# =========================================================================== #
class RunRecordEndpointTests(unittest.TestCase):
    def test_signals_are_typed_dicts_with_labels_and_no_score_key(self):
        body = _call("GET", "/api/runs/{0}/signals".format(_RUN1))["body"]
        self.assertGreater(body["count"], 0)
        for signal in body["signals"]:
            self.assertTrue(signal["signal_id"])
            self.assertIn("direction_label", signal)
            self.assertIn("confidence_label", signal)
            for key in _all_keys(signal):
                low = key.lower()
                for token in ("score", "rank", "rating", "investab"):
                    self.assertNotIn(token, low, "score-like key {0!r} in signal".format(key))

    def test_theme_pulses_carry_states_not_numbers(self):
        body = _call("GET", "/api/runs/{0}/theme_pulses".format(_RUN1))["body"]
        self.assertGreater(body["count"], 0)
        for pulse in body["theme_pulses"]:
            self.assertTrue(pulse["theme_pulse_id"])
            self.assertIn(pulse["state"], sorted(rm.THEME_PULSE_STATES))
            for key in _all_keys(pulse):
                low = key.lower()
                for token in ("score", "rank", "rating", "investab"):
                    self.assertNotIn(token, low)

    def test_findings_and_events_endpoints_return_the_persisted_records(self):
        findings = _call("GET", "/api/runs/{0}/findings".format(_RUN1))["body"]
        events = _call("GET", "/api/runs/{0}/events".format(_RUN1))["body"]
        self.assertGreater(findings["count"], 0)
        self.assertGreater(events["count"], 0)
        self.assertTrue(all(f["finding_id"] for f in findings["findings"]))
        self.assertTrue(all(e["event_id"] for e in events["events"]))
        # evidence preserved end to end: refs survive into the API surface
        self.assertTrue(any(e["evidence_refs"] for e in events["events"]))

    def test_record_endpoint_for_unknown_run_is_404(self):
        self.assertEqual(_call("GET", "/api/runs/RUN-NOPE/signals")["status"], 404)


# =========================================================================== #
# 3. Alert inbox: list + ack (append-only, byte-unchanged alert line)           #
# =========================================================================== #
class AlertEndpointTests(unittest.TestCase):
    def test_alert_inbox_lists_reasons(self):
        body = _call("GET", "/api/alerts", query={"status": "all"})["body"]
        self.assertEqual(body["count"], 1)
        alert = body["alerts"][0]
        self.assertEqual(alert["alert_id"], _SEEDED_ALERT_ID)
        self.assertIn("changed state", alert["human_readable_reason"])
        self.assertEqual(alert["severity"], "notice")            # a label, never a score

    def test_bad_status_filter_is_400(self):
        response = _call("GET", "/api/alerts", query={"status": "everything"})
        self.assertEqual(response["status"], 400)

    def test_ack_appends_and_the_alert_line_is_byte_unchanged(self):
        alert_path = os.path.join(_STATE["store_dir"], "alert_store.jsonl")
        before = _read_bytes(alert_path)

        unacked = _call("GET", "/api/alerts", query={"status": "unacked"})["body"]
        self.assertIn(_SEEDED_ALERT_ID, [a["alert_id"] for a in unacked["alerts"]])

        response = _call("POST", "/api/alerts/{0}/ack".format(_SEEDED_ALERT_ID),
                         body={"at": _NOW3, "acknowledged_by": "operator-test"})
        self.assertEqual(response["status"], 200)
        self.assertTrue(response["body"]["ack_id"])
        self.assertTrue(response["body"]["append_only"])

        # APPEND-ONLY: the alert's own stored line is byte-unchanged forever.
        self.assertEqual(_read_bytes(alert_path), before)
        acks = rm.AlertAcknowledgmentStore(_STATE["store_dir"]).read_all()
        self.assertEqual([a.alert_id for a in acks], [_SEEDED_ALERT_ID])
        self.assertEqual(acks[0].acknowledged_by, "operator-test")

        acked = _call("GET", "/api/alerts", query={"status": "acked"})["body"]
        self.assertIn(_SEEDED_ALERT_ID, [a["alert_id"] for a in acked["alerts"]])
        unacked_after = _call("GET", "/api/alerts", query={"status": "unacked"})["body"]
        self.assertNotIn(_SEEDED_ALERT_ID, [a["alert_id"] for a in unacked_after["alerts"]])

    def test_ack_of_unknown_alert_is_404_and_missing_at_is_400(self):
        response = _call("POST", "/api/alerts/alert.nope/ack", body={"at": _NOW3})
        self.assertEqual(response["status"], 404)
        response = _call("POST", "/api/alerts/{0}/ack".format(_SEEDED_ALERT_ID), body={})
        self.assertEqual(response["status"], 400)
        self.assertIn("at", response["body"]["error"])


# =========================================================================== #
# 4. Schedule state + pause/resume (journaled via the 015 fns)                  #
# =========================================================================== #
class ScheduleEndpointTests(unittest.TestCase):
    def test_schedule_state_carries_policies_states_and_throttle(self):
        body = _call("GET", "/api/schedule", query={"now": _NOW3})["body"]
        self.assertEqual(body["policy_count"], len(rm.DEFAULT_CADENCE_POLICIES))
        schedule = body["schedule"]
        policy_ids = [p["policy_id"] for p in schedule["policies"]]
        self.assertIn("cadence.news_filings", policy_ids)
        self.assertIn("max_runs_per_hour", schedule)
        self.assertFalse(body["throttled"])
        for state in schedule["states"]:
            self.assertIn("paused", state)
            self.assertIn("backoff_until", state)

    def test_pause_and_resume_are_journaled_append_style(self):
        journal_path = os.path.join(_STATE["store_dir"], "schedule_state_store.jsonl")
        lines_before = len(_read_bytes(journal_path).splitlines()) \
            if os.path.isfile(journal_path) else 0

        paused = _call("POST", "/api/schedule/pause",
                       body={"policy_id": "all", "at": _NOW3})
        self.assertEqual(paused["status"], 200)
        self.assertTrue(paused["body"]["paused_all"])
        self.assertTrue(paused["body"]["journaled_record_id"].startswith("schedule-state-"))
        self.assertTrue(_call("GET", "/api/schedule")["body"]["paused_all"])

        snapshot_mid = _read_bytes(journal_path)

        resumed = _call("POST", "/api/schedule/resume",
                        body={"policy_id": "all", "at": _NOW3})
        self.assertEqual(resumed["status"], 200)
        self.assertFalse(resumed["body"]["paused_all"])
        self.assertFalse(_call("GET", "/api/schedule")["body"]["paused_all"])

        # Journaled append-style via the 015 fns: new lines only, priors byte-unchanged.
        after = _read_bytes(journal_path)
        self.assertEqual(len(after.splitlines()), lines_before + 2)
        self.assertTrue(after.startswith(snapshot_mid))

    def test_single_policy_pause_resume_round_trip(self):
        paused = _call("POST", "/api/schedule/pause",
                       body={"policy_id": "cadence.news_filings", "at": _NOW3})
        self.assertEqual(paused["status"], 200)
        states = {s["policy_id"]: s for s in paused["body"]["schedule"]["states"]}
        self.assertTrue(states["cadence.news_filings"]["paused"])
        resumed = _call("POST", "/api/schedule/resume",
                        body={"policy_id": "cadence.news_filings", "at": _NOW3})
        states = {s["policy_id"]: s for s in resumed["body"]["schedule"]["states"]}
        self.assertFalse(states["cadence.news_filings"]["paused"])

    def test_unknown_policy_and_bad_body_are_400(self):
        response = _call("POST", "/api/schedule/pause",
                         body={"policy_id": "cadence.nope", "at": _NOW3})
        self.assertEqual(response["status"], 400)
        self.assertEqual(_call("POST", "/api/schedule/pause", body="nope")["status"], 400)
        self.assertEqual(_call("POST", "/api/schedule/pause", body={"at": _NOW3})["status"],
                         400)


# =========================================================================== #
# 5. The manual-pulse workflow (POST /api/pulse -- ran offline in setUpModule)  #
# =========================================================================== #
class PulseEndpointTests(unittest.TestCase):
    def test_manual_pulse_ran_and_returned_run_id_counts_gaps(self):
        body = _STATE["pulse_response"]["body"]
        self.assertEqual(body["run_id"], _STATE["run2"])
        self.assertEqual(body["trigger_type"], "manual")     # manual-only on this endpoint
        self.assertGreater(body["counts"]["signals"], 0)
        self.assertGreater(body["counts"]["events_loaded"], 0)
        self.assertIsInstance(body["gaps"], list)
        self.assertTrue(body["replay"]["deterministic_match"])
        self.assertEqual(body["replay"]["differences"], 0)

    def test_pulse_persisted_as_a_manual_run_in_history(self):
        runs = _call("GET", "/api/runs")["body"]["runs"]
        run2 = [r for r in runs if r["run_id"] == _STATE["run2"]][0]
        self.assertEqual(run2["trigger_type"], "manual")
        self.assertEqual(run2["started_at"], _NOW2)

    def test_pulse_without_an_injected_now_is_400(self):
        response = _call("POST", "/api/pulse",
                         body={"watchlist": ["IREN"], "themes": ["robotics"]})
        self.assertEqual(response["status"], 400)
        self.assertIn("now", response["body"]["error"])

    def test_pulse_with_empty_scope_or_bad_body_is_400(self):
        response = _call("POST", "/api/pulse",
                         body={"watchlist": [], "themes": ["robotics"], "now": _NOW3})
        self.assertEqual(response["status"], 400)
        self.assertEqual(_call("POST", "/api/pulse", body="notadict")["status"], 400)

    def test_duplicate_run_id_is_refused_append_only(self):
        response = _call("POST", "/api/pulse",
                         body={"watchlist": ["IREN"], "themes": ["robotics"],
                               "now": _NOW2})       # same instant -> same derived run_id
        self.assertEqual(response["status"], 409)
        self.assertIn("already persisted", response["body"]["error"])


# =========================================================================== #
# 6. Replay endpoint (deterministic_match proven through the API)               #
# =========================================================================== #
class ReplayEndpointTests(unittest.TestCase):
    def test_replay_of_a_persisted_run_matches_deterministically(self):
        for run_id in (_RUN1, _STATE["run2"]):
            body = _call("GET", "/api/replay/{0}".format(run_id))["body"]
            self.assertTrue(body["deterministic_match"], run_id)
            self.assertEqual(body["differences"], 0)
            self.assertEqual(body["difference_details"], [])
            self.assertGreater(body["counts"]["signals_replayed"], 0)

    def test_replay_of_unknown_run_is_404(self):
        self.assertEqual(_call("GET", "/api/replay/RUN-NOPE")["status"], 404)

    def test_replay_never_changes_a_stored_byte(self):
        store_dir = _STATE["store_dir"]
        names = ("run_store.jsonl", "signal_store.jsonl", "theme_pulse_store.jsonl",
                 "event_store.jsonl", "finding_store.jsonl")
        before = {n: _read_bytes(os.path.join(store_dir, n)) for n in names}
        _call("GET", "/api/replay/{0}".format(_RUN1))
        for name in names:
            self.assertEqual(_read_bytes(os.path.join(store_dir, name)), before[name],
                             "replay mutated {0}".format(name))


# =========================================================================== #
# 7. Settings journal (append-style, corrections-not-mutations)                 #
# =========================================================================== #
class SettingsEndpointTests(unittest.TestCase):
    def test_settings_put_get_journaled_append_style(self):
        settings_path = os.path.join(_STATE["store_dir"], SettingsStore.filename)

        initial = _call("GET", "/api/settings")["body"]
        self.assertEqual(initial["settings"],
                         {"watchlists": [], "themes": [], "subscriptions": []})
        self.assertEqual(initial["revision"], 0)

        first = _call("PUT", "/api/settings",
                      body={"watchlists": [{"name": "core",
                                            "tickers": ["IREN", "NVDA"]}],
                            "themes": ["physical_ai", "robotics"], "at": _NOW3})
        self.assertEqual(first["status"], 200)
        self.assertEqual(first["body"]["revision"], 1)
        snapshot_after_first = _read_bytes(settings_path)

        # A second PUT is a NEW snapshot line; the first line stays byte-unchanged.
        second = _call("PUT", "/api/settings",
                       body={"subscriptions": [{"subscription_id": "sub.core",
                                                "watchlist": ["IREN"],
                                                "themes": ["robotics"],
                                                "policy_ids": ["cadence.news_filings"]}],
                             "at": _NOW3})
        self.assertEqual(second["status"], 200)
        self.assertEqual(second["body"]["revision"], 2)
        after = _read_bytes(settings_path)
        self.assertTrue(after.startswith(snapshot_after_first))
        self.assertEqual(len(after.splitlines()), 2)

        # The latest snapshot merges: untouched axes carry forward, changed axes replace.
        current = _call("GET", "/api/settings")["body"]
        self.assertEqual(current["revision"], 2)
        self.assertEqual(current["settings"]["themes"], ["physical_ai", "robotics"])
        self.assertEqual(current["settings"]["watchlists"][0]["name"], "core")
        self.assertEqual(current["settings"]["subscriptions"][0]["subscription_id"],
                         "sub.core")

    def test_settings_put_refuses_bad_shapes_and_credential_keys(self):
        self.assertEqual(_call("PUT", "/api/settings", body="nope")["status"], 400)
        self.assertEqual(_call("PUT", "/api/settings", body={})["status"], 400)
        self.assertEqual(
            _call("PUT", "/api/settings", body={"themes": "not-a-list"})["status"], 400)
        self.assertEqual(
            _call("PUT", "/api/settings", body={"favorites": []})["status"], 400)
        # The 013B store scan refuses a credential-like key inside a settings value.
        response = _call("PUT", "/api/settings",
                         body={"subscriptions": [{"subscription_id": "sub.leak",
                                                  "api_key": "sk-should-never-persist"}],
                               "at": _NOW3})
        self.assertEqual(response["status"], 400)
        self.assertNotIn("sk-should-never-persist",
                         _read(os.path.join(_STATE["store_dir"], SettingsStore.filename)))


# =========================================================================== #
# 8. Coverage (the 26-descriptor registry, impl statuses as labels)             #
# =========================================================================== #
class CoverageEndpointTests(unittest.TestCase):
    def test_coverage_lists_the_26_descriptors_with_status_labels(self):
        body = _call("GET", "/api/coverage")["body"]
        self.assertEqual(body["total"], 26)
        self.assertEqual(len(body["agents"]), 26)
        self.assertEqual(body["implemented"] + body["descriptor_only"], 26)
        self.assertGreaterEqual(body["implemented"], 5)      # the pulse's sensor agents
        for agent in body["agents"]:
            self.assertIn(agent["implementation_status"],
                          ("implemented", "descriptor_only"))
            self.assertTrue(agent["agent_id"])
            self.assertIsInstance(agent["subagent_count"], int)   # a volume, not a score
        by_id = {a["agent_id"]: a for a in body["agents"]}
        self.assertEqual(by_id["tattva.market_regime"]["implementation_status"],
                         "implemented")
        self.assertEqual(by_id["tattva.options_flow"]["implementation_status"],
                         "descriptor_only")                   # honest: no impl exists yet


# =========================================================================== #
# 9. Routing guardrails: 404 / 400 / 403 -- and NO trading endpoint             #
# =========================================================================== #
class RoutingGuardrailTests(unittest.TestCase):
    def test_unknown_route_is_404_json(self):
        for path in ("/api/nope", "/nope", "/", "/api", "/api/runs/x/unknownkind"):
            response = _call("GET", path)
            self.assertEqual(response["status"], 404, path)
            self.assertIn("error", response["body"], path)

    def test_method_mismatch_is_405(self):
        self.assertEqual(_call("POST", "/api/health")["status"], 405)
        self.assertEqual(_call("GET", "/api/pulse")["status"], 405)
        self.assertEqual(_call("POST", "/api/settings")["status"], 405)

    def test_any_trade_like_route_is_403_with_the_manual_preview_refusal(self):
        for method in ("GET", "POST", "PUT"):
            for path in ("/api/orders", "/api/buy", "/api/sell", "/api/execute",
                         "/api/trade", "/api/broker", "/api/pulse/submit",
                         "/api/runs/RUN-API-1/orders", "/api/order/place",
                         "/api/execution/submit"):
                response = _call(method, path, body={"ticker": "IREN"})
                self.assertEqual(response["status"], 403, (method, path))
                self.assertEqual(response["body"]["error"], EXECUTION_REFUSAL)

    def test_trade_tokens_cover_the_forbidden_verbs(self):
        for token in ("buy", "sell", "order", "submit", "execute", "trade", "broker"):
            self.assertIn(token, TRADE_PATH_TOKENS)


# =========================================================================== #
# 10. Response hygiene: no credential value, no score/rank key, anywhere        #
# =========================================================================== #
class ResponseHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.responses = [
            _call("GET", "/api/health"),
            _call("GET", "/api/runs"),
            _call("GET", "/api/runs/{0}".format(_RUN1)),
            _call("GET", "/api/runs/{0}/signals".format(_RUN1)),
            _call("GET", "/api/runs/{0}/findings".format(_RUN1)),
            _call("GET", "/api/runs/{0}/events".format(_RUN1)),
            _call("GET", "/api/runs/{0}/theme_pulses".format(_RUN1)),
            _call("GET", "/api/alerts", query={"status": "all"}),
            _call("GET", "/api/schedule", query={"now": _NOW3}),
            _call("GET", "/api/replay/{0}".format(_RUN1)),
            _call("GET", "/api/settings"),
            _call("GET", "/api/coverage"),
            _STATE["pulse_response"],
        ]

    def test_every_response_is_json_able(self):
        for response in self.responses:
            json.dumps(response["body"], sort_keys=True)   # raises on a non-JSON-able body

    def test_no_credential_or_score_rank_key_in_any_response(self):
        for response in self.responses:
            for key in _all_keys(response["body"]):
                low = key.lower()
                for token in _BANNED_KEY_TOKENS:
                    self.assertNotIn(token, low,
                                     "banned key {0!r} in a response".format(key))

    def test_no_credential_like_value_in_any_response(self):
        for response in self.responses:
            for value in _all_string_values(response["body"]):
                for pattern in _SECRET_VALUE_PATTERNS:
                    self.assertIsNone(pattern.search(value),
                                      "credential-like value in a response: "
                                      "{0!r}".format(value[:80]))


# =========================================================================== #
# 11. The PURE dispatcher, proven by AST: no network, no clock, no loop         #
# =========================================================================== #
class PureDispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = _read(_API_PY)
        cls.tree = ast.parse(cls.source)

    def test_api_imports_no_network_server_or_clock_module(self):
        for node in ast.walk(self.tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for banned in _API_BANNED_IMPORT_ROOTS:
                    self.assertFalse(
                        name == banned or name.startswith(banned + "."),
                        "banned import {0!r} in api.py".format(name))

    def test_api_never_calls_a_wall_clock(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, _WALL_CLOCK_ATTRS,
                                 "wall-clock-like call .{0}() in api.py".format(
                                     node.func.attr))

    def test_api_has_no_loop_forever_construct(self):
        self.assertFalse(any(isinstance(n, ast.While) for n in ast.walk(self.tree)),
                         "a while loop crept into the pure dispatcher")
        self.assertNotIn("serve_forever", self.source)
        self.assertNotIn("run_forever", self.source)
        self.assertNotIn("Thread", self.source)

    def test_offline_kill_switch_is_active_for_this_module(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()


# =========================================================================== #
# 12. The server shell: safety asserted from SOURCE (never imported by tests)   #
# =========================================================================== #
class ServerShellSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_source = _read(_SERVER_PY)
        cls.main_source = _read(_MAIN_PY)

    def test_tests_never_import_the_server_shell(self):
        self.assertNotIn("cosmosiq_app.server", sys.modules)
        self.assertNotIn("cosmosiq_app.__main__", sys.modules)

    def test_binds_localhost_by_default(self):
        self.assertIn('DEFAULT_HOST = "127.0.0.1"', self.server_source)
        self.assertIn("default=DEFAULT_HOST", self.main_source)
        self.assertIn("refusing to bind non-local host", self.server_source)
        self.assertIn("--allow-remote", self.main_source)
        self.assertIn("WARNING: --allow-remote set", self.server_source)

    def test_operator_started_with_an_honest_banner(self):
        for token in ("local app", "operator-started", "no scheduler daemon", "no broker",
                      "read-only", "Ctrl-C", "no trading endpoint exists"):
            self.assertIn(token, self.server_source,
                          "banner/shell missing {0!r}".format(token))
        self.assertIn("--store-dir", self.main_source)
        # no always-on / autonomous wording anywhere in the shell
        low = (self.server_source + self.main_source).lower()
        for banned in ("always-on", "always on", "24/7", "streaming", "autonomous",
                       "real-time"):
            self.assertNotIn(banned, low, "forbidden wording {0!r}".format(banned))

    def test_wall_clock_only_at_the_shell_boundary(self):
        self.assertIn("wall_clock_now", self.server_source)
        self.assertIn("datetime.now(timezone.utc)", self.server_source)
        # ...and the serve loop lives HERE ONLY (api.py is proven loop-free above).
        self.assertIn("serve_forever", self.server_source)

    def test_reality_mesh_never_imports_the_app_package(self):
        mesh_dir = os.path.join(_SRC, "reality_mesh")
        for base, _dirs, names in os.walk(mesh_dir):
            for name in names:
                if name.endswith(".py"):
                    self.assertNotIn("cosmosiq_app",
                                     _read(os.path.join(base, name)),
                                     "reality_mesh must not know the app exists "
                                     "({0})".format(name))


# =========================================================================== #
# 13. Untouched paths: the demo default stays byte-identical                    #
# =========================================================================== #
class UntouchedPathsTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app   # lazy: not an API dependency
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                self.assertEqual(_read_bytes(a[name]), _read_bytes(b[name]),
                                 "demo default drifted for {0}".format(name))

    def test_default_manual_pulse_output_unchanged_by_the_api_slice(self):
        # The same seed pulse re-run yields identical signal ids -- the API layer added
        # nothing to (and changed nothing in) the 012K default pulse path.
        again = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW1)
        self.assertEqual([s.signal_id for s in again.signals],
                         [s.signal_id for s in _STATE["pulse"].signals])
        self.assertEqual(again.theme_pulses, _STATE["pulse"].theme_pulses)


if __name__ == "__main__":
    unittest.main()
