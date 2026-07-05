"""IMPLEMENTATION-015C -- diff-based alerts, append-only inbox, operator controls, 015 docs.

The FINAL Phase-015 slice. This suite proves:

* an :class:`Alert` is a frozen OBSERVATION record: closed category + severity vocabularies
  (labels, never scores), a REQUIRED plain-English reason naming the evidence, and NO action
  field (``assert_no_trade_fields`` holds; no buy/sell/order/trade/broker/execute token in
  the module);
* alert generation is DIFF-BASED and deterministic: run A vs run B from the 013B stores --
  a theme-pulse state change, a regime direction flip, a new dilution finding, a narrative
  velocity spike, a crowding fire, a newly-failing data-quality check each alert with a
  plain-English reason; NO change -> NO alert (quiet); the FIRST run -> one baseline note,
  never a flood;
* the inbox is append-only (013B AppendOnlyStore): acknowledging APPENDS a new record
  referencing the alert_id -- the original alert line is byte-unchanged; unacked / acked are
  queryable;
* the 015B tick generates alerts end-to-end (alert hook after persist + record_run; a failed
  pulse yields one honest failure alert; alert-hook failure never fails the pulse);
* the opt-in inbox panel renders "" when empty, shows reasons + severity labels, and offers
  NOTHING clickable (no data-intel / href / button / anchor) and no trade token;
* the CLI operator controls are one-shot offline actions printed honestly (--list-alerts /
  --ack-alert / --pause-policy / --resume-policy), and the default CLI without the flags
  stays byte-identical;
* OPERATOR_GUIDE_015.md documents the workflow (operator-started cron/launchd calls the
  one-tick command; NO daemon ships), and its tick command actually builds offline;
* alerts.py carries no banned import / loop / sleep / execution token and no "verified_fact";
  the demo default + default pulse remain byte-identical.

Entirely OFFLINE and deterministic: injected ISO ``now`` strings everywhere; a socket
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
from dataclasses import FrozenInstanceError, fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import scheduler as SC
from reality_mesh import stores as S
from reality_mesh.alerts import (
    ALERT_CATEGORIES,
    ALERT_SEVERITIES,
    CATEGORY_SEVERITY,
    Alert,
    AlertAcknowledgment,
    AlertAcknowledgmentStore,
    AlertStore,
    acknowledge_alert,
    acknowledged_alert_ids,
    acknowledged_alerts,
    alerts_with_status,
    diff_persisted_runs,
    generate_alerts_for_run,
    previous_persisted_run_id,
    record_failed_pulse_alert,
    unacknowledged_alerts,
)
from reality_mesh.models import AgentFinding, RealitySignal, ThemePulse
from reality_mesh.orchestrator import Subscription, run_due_pulses
from reality_mesh.render_adapters import build_alert_inbox_panel
from reality_mesh.runtime import PulseRun
from reality_mesh.validation import assert_no_trade_fields
from cosmosiq_pulse import main as cosmosiq_main
from tattva_pulse.__main__ import main as pulse_cli_main

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_ALERTS_PY = os.path.join(_PKG_DIR, "alerts.py")
_GUIDE = os.path.join(_ROOT, "docs", "OPERATOR_GUIDE_015.md")

# A Monday inside the default 14:30-21:00 UTC session.
_NOW = "2026-06-29T15:00:00Z"
_EARLIER = "2026-06-29T14:00:00Z"

# The 015A/015B guard vocabulary, applied to alerts.py (minus the alert words themselves --
# this module IS the alert module; the execution/trading vocabulary stays fully banned).
_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "asyncio", "threading", "multiprocessing",
                        "subprocess", "smtplib", "ftplib", "socketserver", "broker",
                        "signal", "time", "random", "select", "selectors", "queue")
_BANNED_CALL_NAMES = ("sleep", "run_forever", "serve_forever", "start_polling", "Thread",
                      "Timer", "Process", "fork", "spawn", "run_in_executor", "setdaemon")
_EXECUTION_WORDS = ("buy", "sell", "hold", "order", "orders", "trade", "trades", "trading",
                    "broker", "execute", "execution", "rebalance", "rebalancing", "position")
_WALL_CLOCK_TOKENS = ("time.time(", "datetime.now(", "datetime.utcnow(", "utcnow(",
                      "time.monotonic(", "perf_counter(")

_SANSKRIT = ("sphurana", "buddhi", "adhara", "nivesha", "kriya")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline alerts suite")


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


def _alert(alert_id="alert.run-b.theme_pulse_changed.t", run_id="run-b",
           category="theme_pulse_changed", severity="notice",
           reason="Theme pulse for 'x' changed state from 'Warming' to 'Igniting'.",
           **kw):
    return Alert(alert_id=alert_id, run_id=run_id, category=category, severity=severity,
                 human_readable_reason=reason, created_at=kw.pop("created_at", _NOW), **kw)


def _seed_run(store_dir, run_id, ts, *, pulses=(), signals=(), findings=(), dq=()):
    """Persist one fabricated run (spine + records) into the 013B stores."""
    S.RunStore(store_dir).append(
        PulseRun(run_id=run_id, started_at=ts, completed_at=ts, mode="pulse"), timestamp=ts)
    for pulse in pulses:
        S.ThemePulseStore(store_dir).append(pulse, run_id=run_id, timestamp=ts)
    for signal in signals:
        S.SignalStore(store_dir).append(signal, run_id=run_id, timestamp=ts)
    for finding in findings:
        S.FindingStore(store_dir).append(finding, run_id=run_id, timestamp=ts)
    for record in dq:
        S.DataQualityStore(store_dir).append(record, run_id=run_id, timestamp=ts)


def _pulse(theme="physical-ai", state="Warming", crowding=""):
    return ThemePulse(theme_pulse_id="pulse.{0}".format(theme), theme_id=theme,
                      theme_name=theme, state=state, crowding_label=crowding)


def _signal(sid, discipline, direction, urgency="", magnitude=""):
    return RealitySignal(signal_id=sid, discipline=discipline, direction_label=direction,
                         urgency_label=urgency, magnitude_label=magnitude)


def _dq(run_id, category, status, summary=""):
    return S.DataQualityRecord(dq_id="dq.{0}.{1}".format(run_id, category), run_id=run_id,
                               category=category, status=status, summary=summary, at=_NOW)


# =========================================================================== #
# 1. The Alert record -- closed vocabularies, required reason, NO action field #
# =========================================================================== #
class AlertRecordTests(unittest.TestCase):
    def test_closed_category_vocabulary(self):
        self.assertEqual(ALERT_CATEGORIES, frozenset({
            "market_regime_changed", "sector_rotation_detected", "theme_pulse_changed",
            "filing_dilution_risk", "social_narrative_spike", "crowding_warning",
            "source_data_quality_failure", "thesis_deteriorated",
            "new_opportunity_hypothesis", "major_risk_emerged"}))
        with self.assertRaises(ValueError):
            _alert(category="price_target_hit")
        with self.assertRaises(ValueError):
            _alert(category="")

    def test_closed_severity_labels_not_scores(self):
        self.assertEqual(ALERT_SEVERITIES,
                         frozenset({"info", "notice", "warning", "critical"}))
        with self.assertRaises(ValueError):
            _alert(severity="9.5")
        with self.assertRaises(ValueError):
            _alert(severity="urgent")

    def test_every_category_has_a_valid_default_severity_label(self):
        self.assertEqual(set(CATEGORY_SEVERITY), set(ALERT_CATEGORIES))
        for severity in CATEGORY_SEVERITY.values():
            self.assertIn(severity, ALERT_SEVERITIES)

    def test_reason_is_required_plain_english(self):
        with self.assertRaises(ValueError):
            _alert(reason="")
        with self.assertRaises(ValueError):
            _alert(reason="   ")

    def test_required_ids_and_timestamp(self):
        with self.assertRaises(ValueError):
            _alert(alert_id="")
        with self.assertRaises(ValueError):
            _alert(run_id="")
        with self.assertRaises(ValueError):
            _alert(created_at="")

    def test_no_action_field_and_no_trade_field(self):
        names = {f.name for f in fields(Alert)}
        self.assertNotIn("action", names)
        assert_no_trade_fields(Alert)               # raises on any trade/score field name
        assert_no_trade_fields(AlertAcknowledgment)
        self.assertEqual(names, {
            "alert_id", "run_id", "category", "severity", "human_readable_reason",
            "subject_tickers", "subject_themes", "subject_refs", "evidence_refs",
            "created_at", "acknowledged",
            # 020D additive shadow fields (labels / refs -- never an action):
            "mode", "recommended_review_action", "dq_state", "candidate_ref"})

    def test_frozen_and_tuple_coerced(self):
        alert = _alert(subject_tickers=["IREN"], subject_themes=["physical-ai"])
        self.assertEqual(alert.subject_tickers, ("IREN",))
        self.assertEqual(alert.subject_themes, ("physical-ai",))
        with self.assertRaises(FrozenInstanceError):
            alert.severity = "critical"  # type: ignore[misc]

    def test_acknowledged_defaults_false_and_must_be_bool(self):
        self.assertFalse(_alert().acknowledged)
        with self.assertRaises(ValueError):
            _alert(acknowledged="yes")

    def test_acknowledgment_requires_its_ids(self):
        with self.assertRaises(ValueError):
            AlertAcknowledgment(ack_id="", alert_id="a")
        with self.assertRaises(ValueError):
            AlertAcknowledgment(ack_id="ack.a.001", alert_id="")


# =========================================================================== #
# 2. The append-only inbox -- ack is a NEW record; originals byte-unchanged   #
# =========================================================================== #
class AlertStoreTests(unittest.TestCase):
    def test_round_trip_and_query_axes(self):
        with tempfile.TemporaryDirectory() as d:
            store = AlertStore(d)
            alert = _alert(subject_tickers=("IREN",), subject_themes=("physical-ai",))
            store.append(alert, timestamp=_NOW)
            self.assertEqual(store.read_all(), (alert,))
            self.assertEqual(store.query(category="theme_pulse_changed"), (alert,))
            self.assertEqual(store.query(severity="notice"), (alert,))
            self.assertEqual(store.query(run_id="run-b"), (alert,))
            self.assertEqual(store.query(ticker="iren"), (alert,))
            self.assertEqual(store.query(theme="physical_ai"), (alert,))
            self.assertEqual(store.query(category="crowding_warning"), ())

    def test_no_mutation_surface(self):
        for name in ("update", "delete", "remove", "pop", "__setitem__", "__delitem__"):
            self.assertFalse(hasattr(AlertStore, name))
            self.assertFalse(hasattr(AlertAcknowledgmentStore, name))

    def test_credential_and_trade_keys_refused_at_write(self):
        with tempfile.TemporaryDirectory() as d:
            store = AlertStore(d)
            with self.assertRaises(ValueError):
                store.append({"alert_id": "x", "api_key": "sk-oops"}, timestamp=_NOW)
            with self.assertRaises(ValueError):
                store.append({"alert_id": "x", "order_size": 5}, timestamp=_NOW)

    def test_acknowledge_appends_new_record_original_byte_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            AlertStore(d).append(_alert(), timestamp=_NOW)
            alert_path = os.path.join(d, "alert_store.jsonl")
            before = _read(alert_path)
            ack_id = acknowledge_alert(d, _alert().alert_id, at="2026-06-29T15:10:00Z",
                                       note="seen")
            self.assertEqual(_read(alert_path), before)     # byte-unchanged forever
            acks = AlertAcknowledgmentStore(d).read_all()
            self.assertEqual(len(acks), 1)
            self.assertEqual(acks[0].ack_id, ack_id)
            self.assertEqual(acks[0].alert_id, _alert().alert_id)
            self.assertEqual(acks[0].acknowledged_by, "operator")
            # the stored alert payload STILL carries acknowledged=False (read-model join only)
            raw = json.loads(_read(alert_path).splitlines()[0])
            self.assertFalse(raw["payload"]["acknowledged"])

    def test_unacked_and_acked_queryable(self):
        with tempfile.TemporaryDirectory() as d:
            first = _alert(alert_id="alert.run-b.theme_pulse_changed.a")
            second = _alert(alert_id="alert.run-b.crowding_warning.b",
                            category="crowding_warning", severity="warning")
            store = AlertStore(d)
            store.append(first, timestamp=_NOW)
            store.append(second, timestamp=_NOW)
            acknowledge_alert(d, first.alert_id, at=_NOW)
            self.assertEqual(acknowledged_alert_ids(d), frozenset({first.alert_id}))
            self.assertEqual([a.alert_id for a in acknowledged_alerts(d)],
                             [first.alert_id])
            self.assertEqual([a.alert_id for a in unacknowledged_alerts(d)],
                             [second.alert_id])
            joined = {a.alert_id: a.acknowledged for a in alerts_with_status(d)}
            self.assertEqual(joined, {first.alert_id: True, second.alert_id: False})

    def test_unknown_alert_id_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                acknowledge_alert(d, "alert.ghost", at=_NOW)


# =========================================================================== #
# 3. The diff engine -- a CHANGE alerts; sameness is quiet; first run is a    #
#    baseline                                                                  #
# =========================================================================== #
class DiffEngineTests(unittest.TestCase):
    def _two_runs(self, d, a_kw, b_kw):
        _seed_run(d, "run-a", _EARLIER, **a_kw)
        _seed_run(d, "run-b", _NOW, **b_kw)
        return generate_alerts_for_run(d, "run-b", now=_NOW)

    def test_theme_pulse_state_change_alerts_with_plain_english_reason(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d, dict(pulses=(_pulse(state="Warming"),)),
                dict(pulses=(_pulse(state="Igniting"),)))
            self.assertEqual([a.category for a in result.alerts],
                             ["theme_pulse_changed"])
            alert = result.alerts[0]
            self.assertEqual(alert.severity, "notice")
            for token in ("physical-ai", "Warming", "Igniting", "run-a", "run-b"):
                self.assertIn(token, alert.human_readable_reason)
            self.assertIn("physical-ai", alert.subject_themes)
            self.assertIn("pulse.physical-ai", alert.subject_refs)
            self.assertEqual(alert.run_id, "run-b")

    def test_deteriorating_state_upgrades_to_warning(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d, dict(pulses=(_pulse(state="Crowded"),)),
                dict(pulses=(_pulse(state="Breaking down"),)))
            self.assertEqual(result.alerts[0].severity, "warning")

    def test_regime_direction_flip_alerts(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d,
                dict(signals=(_signal("sig.regime", "market_regime", "deteriorating"),)),
                dict(signals=(_signal("sig.regime", "market_regime", "improving"),)))
            self.assertEqual([a.category for a in result.alerts],
                             ["market_regime_changed"])
            reason = result.alerts[0].human_readable_reason
            for token in ("deteriorating", "improving", "sig.regime", "run-a", "run-b"):
                self.assertIn(token, reason)
            self.assertEqual(result.alerts[0].severity, "warning")

    def test_new_dilution_finding_alerts(self):
        with tempfile.TemporaryDirectory() as d:
            finding = AgentFinding(
                finding_id="finding.news_filings.dilution_risk.iren",
                agent_id="news_filings.sensor", finding_type="dilution_risk",
                affected_companies=("IREN",))
            result = self._two_runs(d, dict(findings=()), dict(findings=(finding,)))
            self.assertEqual([a.category for a in result.alerts],
                             ["filing_dilution_risk"])
            alert = result.alerts[0]
            self.assertEqual(alert.severity, "warning")
            self.assertIn("finding.news_filings.dilution_risk.iren",
                          alert.human_readable_reason)
            self.assertIn("IREN", alert.human_readable_reason)
            self.assertIn("IREN", alert.subject_tickers)

    def test_narrative_velocity_spike_alerts_and_names_weak_tier(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d,
                dict(signals=(_signal("sig.narr", "narrative", "accelerating",
                                      urgency="watch", magnitude="moderate"),)),
                dict(signals=(_signal("sig.narr", "narrative", "accelerating",
                                      urgency="high", magnitude="moderate"),)))
            self.assertEqual([a.category for a in result.alerts],
                             ["social_narrative_spike"])
            self.assertIn("corroboration", result.alerts[0].human_readable_reason)

    def test_crowding_fire_alerts(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d, dict(pulses=(_pulse(state="Broadening", crowding="moderate"),)),
                dict(pulses=(_pulse(state="Broadening", crowding="extreme"),)))
            self.assertEqual([a.category for a in result.alerts], ["crowding_warning"])
            self.assertIn("extreme", result.alerts[0].human_readable_reason)

    def test_newly_failing_gate_and_source_alert(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d, dict(dq=(_dq("run-a", "coverage", "pass"),)),
                dict(dq=(_dq("run-b", "coverage", "fail", "coverage gate FAILED"),
                         _dq("run-b", "source_failure", "failed", "source went dark"))))
            self.assertEqual([a.category for a in result.alerts],
                             ["source_data_quality_failure",
                              "source_data_quality_failure"])
            reasons = " | ".join(a.human_readable_reason for a in result.alerts)
            self.assertIn("coverage", reasons)
            self.assertIn("source_failure", reasons)
            for alert in result.alerts:
                self.assertEqual(alert.severity, "critical")

    def test_still_failing_gate_stays_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d, dict(dq=(_dq("run-a", "coverage", "fail"),)),
                dict(dq=(_dq("run-b", "coverage", "fail"),)))
            self.assertEqual(result.alerts, ())

    def test_no_change_means_no_alert(self):
        with tempfile.TemporaryDirectory() as d:
            same = dict(pulses=(_pulse(state="Warming"),),
                        signals=(_signal("sig.regime", "market_regime", "improving"),))
            result = self._two_runs(d, same, same)
            self.assertEqual(result.alerts, ())
            self.assertFalse(result.baseline)
            self.assertTrue(any("no state change" in n and "quiet" in n
                                for n in result.notes), result.notes)
            self.assertEqual(AlertStore(d).read_all(), ())

    def test_first_run_is_a_baseline_note_not_a_flood(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-a", _EARLIER,
                      pulses=(_pulse(state="Igniting"),),
                      signals=(_signal("sig.regime", "market_regime", "improving"),),
                      dq=(_dq("run-a", "coverage", "fail"),))
            result = generate_alerts_for_run(d, "run-a", now=_EARLIER)
            self.assertTrue(result.baseline)
            self.assertEqual(result.alerts, ())
            self.assertEqual(result.previous_run_id, "")
            self.assertTrue(any("baseline" in n for n in result.notes), result.notes)
            self.assertEqual(AlertStore(d).read_all(), ())

    def test_alerts_persist_append_only_and_regeneration_never_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d, dict(pulses=(_pulse(state="Warming"),)),
                dict(pulses=(_pulse(state="Igniting"),)))
            path = os.path.join(d, "alert_store.jsonl")
            before = _read(path)
            self.assertEqual(len(before.splitlines()), len(result.alerts))
            again = generate_alerts_for_run(d, "run-b", now=_NOW)
            self.assertEqual(_read(path), before)           # no duplicate lines
            self.assertEqual(again.alerts, result.alerts)
            self.assertTrue(any("already recorded" in n for n in again.notes))

    def test_deterministic_same_stores_same_bytes(self):
        outputs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                result = self._two_runs(
                    d,
                    dict(pulses=(_pulse(state="Warming"),),
                         signals=(_signal("sig.regime", "market_regime",
                                          "deteriorating"),)),
                    dict(pulses=(_pulse(state="Igniting"),),
                         signals=(_signal("sig.regime", "market_regime", "improving"),)))
                outputs.append((repr(result.alerts),
                                _read(os.path.join(d, "alert_store.jsonl"))))
        self.assertEqual(outputs[0], outputs[1])

    def test_previous_run_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(previous_persisted_run_id(d, "run-a"), "")
            _seed_run(d, "run-a", _EARLIER)
            _seed_run(d, "run-b", _NOW)
            self.assertEqual(previous_persisted_run_id(d, "run-a"), "")
            self.assertEqual(previous_persisted_run_id(d, "run-b"), "run-a")
            # an unpersisted (failed) run compares against the LATEST persisted run
            self.assertEqual(previous_persisted_run_id(d, "run-ghost"), "run-b")

    def test_diff_requires_both_run_ids(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                diff_persisted_runs(d, "", "run-b", now=_NOW)
            with self.assertRaises(ValueError):
                generate_alerts_for_run(d, "", now=_NOW)
            with self.assertRaises(ValueError):
                generate_alerts_for_run(d, "run-b", now="")


# =========================================================================== #
# 4. End-to-end: the 015B tick + the 015C alert hook                          #
# =========================================================================== #
def _policy(pid="cadence.test", interval=5):
    return SC.CadencePolicy(policy_id=pid, discipline_or_adapter="news_filings",
                            interval_minutes=interval, min_interval_minutes=1)


def _schedule(policies):
    return SC.PulseSchedule(
        policies=tuple(policies),
        states=tuple(SC.ScheduleState(policy_id=p.policy_id) for p in policies))


def _sub(sid="sub.core", policy_ids=("cadence.test",), data_dir=""):
    return Subscription(subscription_id=sid, watchlist=("IREN", "NVDA"),
                        themes=("physical-ai", "robotics"), policy_ids=tuple(policy_ids),
                        data_dir=data_dir)


class TickAlertHookTests(unittest.TestCase):
    def test_first_tick_is_a_baseline_no_alert_flood(self):
        with tempfile.TemporaryDirectory() as d:
            result = run_due_pulses(_schedule((_policy(),)), now=_NOW, store_dir=d,
                                    subscriptions=(_sub(),), max_pulses=2)
            self.assertEqual(len(result.pulse_runs), 1)
            self.assertEqual(result.alerts, ())
            self.assertTrue(any("baseline" in n for n in result.notes), result.notes)
            self.assertEqual(AlertStore(d).read_all(), ())

    def test_tick_generates_alerts_end_to_end_when_state_changed(self):
        with tempfile.TemporaryDirectory() as d:
            # fabricate the PREVIOUS persisted run with a different theme state + regime
            # direction than the pulse will produce, so the tick's diff observes changes.
            probe = rm.run_pulse(["IREN", "NVDA"], ["physical-ai", "robotics"], now=_NOW)
            target = next(p for p in probe.theme_pulses
                          if p.theme_id == "physical-ai")
            other_state = "Dormant" if target.state != "Dormant" else "Warming"
            _seed_run(
                d, "seed.run", _EARLIER,
                pulses=(ThemePulse(theme_pulse_id=target.theme_pulse_id,
                                   theme_id=target.theme_id,
                                   theme_name=target.theme_name, state=other_state),),
                signals=(_signal("sig.market-regime.discipline.market-regime",
                                 "market_regime", "deteriorating"),))
            result = run_due_pulses(_schedule((_policy(),)), now=_NOW, store_dir=d,
                                    subscriptions=(_sub(),), max_pulses=2)
            self.assertEqual(len(result.pulse_runs), 1)
            run_id = result.pulse_runs[0].run_id
            categories = {a.category for a in result.alerts}
            self.assertIn("theme_pulse_changed", categories)
            self.assertIn("market_regime_changed", categories)
            # persisted end-to-end into the append-only inbox, keyed to the tick's run
            stored = AlertStore(d).query(run_id=run_id)
            self.assertEqual(tuple(stored), result.alerts)
            for alert in result.alerts:
                self.assertTrue(alert.human_readable_reason.strip())
                self.assertIn(alert.severity, ALERT_SEVERITIES)
            self.assertTrue(any("state change" in n for n in result.notes), result.notes)

    def test_unchanged_second_tick_stays_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            first = run_due_pulses(_schedule((_policy(),)), now=_NOW, store_dir=d,
                                   subscriptions=(_sub(),), max_pulses=2)
            second = run_due_pulses(first.schedule, now="2026-06-29T15:06:00Z",
                                    store_dir=d, subscriptions=(_sub(),), max_pulses=2)
            self.assertEqual(len(second.pulse_runs), 1)
            self.assertEqual(second.alerts, ())
            self.assertTrue(any("no state change" in n for n in second.notes),
                            second.notes)

    def test_failed_pulse_yields_one_honest_failure_alert(self):
        with tempfile.TemporaryDirectory() as d:
            bad_dir = os.path.join(d, "no_such_data")
            result = run_due_pulses(
                _schedule((_policy("cadence.fail"),)), now=_NOW, store_dir=d,
                subscriptions=(_sub("sub.fail", policy_ids=("cadence.fail",),
                                    data_dir=bad_dir),))
            self.assertEqual(result.pulse_runs, ())
            self.assertEqual([a.category for a in result.alerts],
                             ["source_data_quality_failure"])
            alert = result.alerts[0]
            self.assertEqual(alert.severity, "critical")
            self.assertIn("cadence.fail", alert.human_readable_reason)
            self.assertIn("FAILED", alert.human_readable_reason)
            self.assertEqual(AlertStore(d).query(run_id=alert.run_id), (alert,))

    def test_failure_alert_helper_is_idempotent_per_run(self):
        with tempfile.TemporaryDirectory() as d:
            first = record_failed_pulse_alert(d, "run-x", policy_id="cadence.a",
                                              message="boom", now=_NOW)
            self.assertIsNotNone(first)
            self.assertIsNone(record_failed_pulse_alert(
                d, "run-x", policy_id="cadence.a", message="boom", now=_NOW))
            self.assertEqual(len(AlertStore(d).read_all()), 1)


# =========================================================================== #
# 5. The opt-in inbox panel -- nothing clickable, "" when empty               #
# =========================================================================== #
class InboxPanelTests(unittest.TestCase):
    def test_empty_input_renders_empty_string(self):
        self.assertEqual(build_alert_inbox_panel(), "")
        self.assertEqual(build_alert_inbox_panel(alerts=()), "")

    def test_reasons_and_severity_labels_visible(self):
        alert = _alert(subject_tickers=("IREN",))
        html = build_alert_inbox_panel(alerts=(alert,))
        self.assertIn("Alert inbox", html)
        self.assertIn(alert.human_readable_reason, html)
        self.assertIn("theme_pulse_changed", html)
        self.assertIn(">notice<", html)                     # a LABEL badge, not a number
        self.assertIn("IREN", html)
        self.assertIn(">open<", html)

    def test_acknowledged_status_shown_from_join(self):
        alert = _alert()
        html = build_alert_inbox_panel(alerts=(alert,),
                                       acknowledged_ids=(alert.alert_id,))
        self.assertIn(">acknowledged<", html)
        self.assertNotIn(">open<", html)

    def test_nothing_clickable_no_affordance_no_trade_token(self):
        alerts = (
            _alert(),
            _alert(alert_id="alert.run-b.source_data_quality_failure.x",
                   category="source_data_quality_failure", severity="critical",
                   reason="Data-quality check 'coverage' is failing in run run-b."),
        )
        html = build_alert_inbox_panel(alerts=alerts)
        low = html.lower()
        for forbidden in ("data-intel", "href", "<button", "onclick", "<a ", "<form",
                          "<input"):
            self.assertNotIn(forbidden, low, "clickable affordance {0!r}".format(forbidden))
        self.assertIsNone(re.search(
            r"\b(buy|sell|hold|submit|top pick|strong buy|price target)\b", low))
        self.assertIsNone(re.search(r"\b(investability|score:|rank #|rating:)\b", low))
        # acknowledgment is explicitly a CLI act, not a click
        self.assertIn("--ack-alert", html)

    def test_severities_render_as_labels_never_numbers(self):
        for severity in sorted(ALERT_SEVERITIES):
            html = build_alert_inbox_panel(alerts=(_alert(severity=severity),))
            self.assertIn(">{0}<".format(severity), html)
        self.assertIsNone(re.search(r"severity[^<]*\d", html))


# =========================================================================== #
# 6. CLI operator controls -- one-shot, offline, honest; default unchanged    #
# =========================================================================== #
class CliOperatorControlTests(unittest.TestCase):
    def _seed_inbox(self, d):
        _seed_run(d, "run-a", _EARLIER, pulses=(_pulse(state="Warming"),))
        _seed_run(d, "run-b", _NOW, pulses=(_pulse(state="Igniting"),))
        return generate_alerts_for_run(d, "run-b", now=_NOW).alerts

    def test_list_alerts_prints_reasons_one_shot_rc0(self):
        with tempfile.TemporaryDirectory() as d:
            alerts = self._seed_inbox(d)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = pulse_cli_main(["--list-alerts", "--persist-dir", d])
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("Alert inbox", text)
            self.assertIn(alerts[0].alert_id, text)
            self.assertIn(alerts[0].human_readable_reason, text)
            self.assertIn("1 open", text)
            self.assertIn("One-shot action -- exiting", text)

    def test_list_alerts_empty_inbox_is_honest(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = pulse_cli_main(["--list-alerts", "--persist-dir", d])
            self.assertEqual(rc, 0)
            self.assertIn("no alerts recorded", out.getvalue())

    def test_ack_alert_appends_new_record_original_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            alerts = self._seed_inbox(d)
            alert_path = os.path.join(d, "alert_store.jsonl")
            before = _read(alert_path)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = pulse_cli_main(["--ack-alert", alerts[0].alert_id,
                                     "--persist-dir", d,
                                     "--tick-now", "2026-06-29T15:10:00Z"])
            self.assertEqual(rc, 0)
            self.assertEqual(_read(alert_path), before)     # never edited
            self.assertEqual(acknowledged_alert_ids(d), frozenset({alerts[0].alert_id}))
            text = out.getvalue()
            self.assertIn("APPENDED", text)
            self.assertIn("byte-unchanged", text)
            # and the inbox now lists it as acknowledged
            out2 = io.StringIO()
            with redirect_stdout(out2):
                pulse_cli_main(["--list-alerts", "--persist-dir", d])
            self.assertIn("acknowledged", out2.getvalue())

    def test_ack_unknown_alert_fails_honestly(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    pulse_cli_main(["--ack-alert", "alert.ghost", "--persist-dir", d,
                                    "--tick-now", _NOW])
            self.assertNotEqual(ctx.exception.code, 0)

    def test_pause_and_resume_journal_the_schedule_state(self):
        from reality_mesh.orchestrator import ScheduleStateStore, load_schedule_state
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = pulse_cli_main(["--pause-policy", "all", "--persist-dir", d,
                                     "--tick-now", _NOW])
            self.assertEqual(rc, 0)
            self.assertTrue(load_schedule_state(d).paused_all)
            text = out.getvalue()
            self.assertIn("paused", text)
            self.assertIn("ALL policies", text)
            self.assertIn("Nothing runs by itself", text)
            journal = ScheduleStateStore(d).read_records()
            self.assertEqual(len(journal), 1)
            self.assertIn("operator paused policy all", journal[0]["payload"]["note"])
            # resume appends a SECOND line; the first stays byte-unchanged
            path = os.path.join(d, "schedule_state_store.jsonl")
            first_line = _read(path).splitlines()[0]
            with redirect_stdout(io.StringIO()):
                rc = pulse_cli_main(["--resume-policy", "all", "--persist-dir", d,
                                     "--tick-now", "2026-06-29T15:20:00Z"])
            self.assertEqual(rc, 0)
            lines = _read(path).splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0], first_line)
            self.assertFalse(load_schedule_state(d).paused_all)

    def test_pause_single_policy_and_backoff_honesty_on_resume(self):
        from reality_mesh.orchestrator import load_schedule_state
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                pulse_cli_main(["--pause-policy", "cadence.news_filings",
                                "--persist-dir", d, "--tick-now", _NOW])
            state = SC.state_for(load_schedule_state(d), "cadence.news_filings")
            self.assertTrue(state.paused)
            out = io.StringIO()
            with redirect_stdout(out):
                pulse_cli_main(["--resume-policy", "cadence.news_filings",
                                "--persist-dir", d, "--tick-now", _NOW])
            self.assertIn("failure backoff still applies", out.getvalue())
            self.assertFalse(SC.state_for(load_schedule_state(d),
                                          "cadence.news_filings").paused)

    def test_paused_schedule_blocks_the_next_tick(self):
        with tempfile.TemporaryDirectory() as d:
            subs = os.path.join(d, "subscriptions.json")
            with open(subs, "w", encoding="utf-8") as fh:
                json.dump({"subscriptions": [{
                    "subscription_id": "sub.core", "watchlist": ["IREN"],
                    "themes": ["physical-ai"],
                    "policy_ids": ["cadence.news_filings"]}]}, fh)
            with redirect_stdout(io.StringIO()):
                pulse_cli_main(["--pause-policy", "all", "--persist-dir", d,
                                "--tick-now", _NOW])
            out = io.StringIO()
            with redirect_stdout(out):
                rc = pulse_cli_main(["--scheduled-tick", "--persist-dir", d,
                                     "--tick-now", "2026-06-29T15:05:00Z",
                                     "--subscriptions", subs])
            self.assertEqual(rc, 0)
            self.assertIn("ran (0):", out.getvalue())
            self.assertIn("paused", out.getvalue())

    def test_unknown_policy_id_fails_honestly(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    pulse_cli_main(["--pause-policy", "cadence.ghost",
                                    "--persist-dir", d, "--tick-now", _NOW])
            self.assertNotEqual(ctx.exception.code, 0)

    def test_controls_require_their_inputs_and_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            for argv in (
                ["--list-alerts"],                              # no --persist-dir
                ["--pause-policy", "all", "--persist-dir", d],  # no --tick-now
                ["--resume-policy", "all", "--persist-dir", d],
                ["--ack-alert", "a", "--persist-dir", d],
                ["--pause-policy", "all", "--resume-policy", "all",
                 "--persist-dir", d, "--tick-now", _NOW],       # two controls at once
                ["--list-alerts", "--scheduled-tick", "--persist-dir", d],
            ):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as ctx:
                        pulse_cli_main(argv)
                self.assertNotEqual(ctx.exception.code, 0, argv)

    def test_default_cli_without_the_flags_is_byte_identical(self):
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
        self.assertEqual(outputs[0][0], outputs[1][0])
        self.assertEqual(sorted(outputs[0][1]), sorted(outputs[1][1]))
        for name in outputs[0][1]:
            self.assertEqual(outputs[0][1][name], outputs[1][1][name],
                             "default CLI output drifted for {0}".format(name))
        # the default path never mentions the 015C controls or the inbox
        low = outputs[0][0].lower()
        for token in ("alert", "pause", "resume", "acknowledg"):
            self.assertNotIn(token, low)


# =========================================================================== #
# 7. OPERATOR_GUIDE_015 -- documented, English, and the command builds offline #
# =========================================================================== #
class OperatorGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _read(_GUIDE)
        cls.low = cls.text.lower()
        cls.norm = re.sub(r"\s+", " ", cls.text)
        cls.norm_low = cls.norm.lower()

    def test_guide_documents_the_scheduled_tick_workflow_no_daemon(self):
        for token in ("cosmosiq_pulse", "--scheduled-tick", "--persist-dir", "--tick-now",
                      "--subscriptions", "cron", "launchd",
                      "schedule_state_store.jsonl"):
            self.assertIn(token, self.text, "guide missing {0!r}".format(token))
        self.assertIn("NO daemon", self.text)
        self.assertIn("operator", self.low)
        # the loop is the OPERATOR'S, never CosmosIQ's
        self.assertIn("owned by the operator", self.norm)

    def test_guide_documents_cadences_pause_resume(self):
        for token in ("cadence.social_narrative", "cadence.news_filings",
                      "cadence.market_regime", "max_runs_per_hour", "backoff",
                      "--pause-policy", "--resume-policy"):
            self.assertIn(token, self.text, "guide missing {0!r}".format(token))
        self.assertIn("Resume lifts the pause only", self.norm)

    def test_guide_documents_every_alert_category_and_the_ack_discipline(self):
        for category in sorted(ALERT_CATEGORIES):
            self.assertIn(category, self.text, "guide missing category " + category)
        for token in ("--list-alerts", "--ack-alert", "alert_store.jsonl",
                      "alert_ack_store.jsonl", "byte-unchanged", "append-only"):
            self.assertIn(token, self.text, "guide missing {0!r}".format(token))
        self.assertIn("OBSERVE", self.text)
        for severity in ("info", "notice", "warning", "critical"):
            self.assertIn(severity, self.low)
        self.assertIn("baseline", self.low)
        self.assertIn("quiet", self.low)

    def test_guide_states_the_still_forbidden_list(self):
        self.assertIn("auto-buy/sell", self.norm_low)
        self.assertIn("broker execution", self.norm_low)
        self.assertIn("auto-rebalance", self.norm_low)
        self.assertIn("streaming` stays reserved", self.norm_low)
        self.assertIn("manual execution preview only", self.norm_low)
        self.assertIn("Phase 020+", self.text)
        self.assertIn("approval-gated", self.text)
        self.assertIn("requires a new ADR", self.norm)

    def test_guide_uses_english_terminology_only(self):
        for term in _SANSKRIT:
            self.assertNotIn(term, self.low, "Sanskrit term in guide: {0}".format(term))
        # 'tattva' may appear ONLY inside the deprecated tattva_pulse alias mention
        for match in re.finditer("tattva", self.norm_low):
            self.assertEqual(
                self.norm_low[match.start():match.start() + len("tattva_pulse")],
                "tattva_pulse", "'tattva' outside the tattva_pulse alias token")
            window = self.norm_low[match.start():match.start() + 200]
            self.assertTrue("deprecated" in window or "alias" in window, window)

    def test_documented_tick_command_actually_builds_offline(self):
        self.assertIn("python3 -m cosmosiq_pulse", self.text)
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "pulse_store")
            subs = os.path.join(d, "subscriptions.json")
            with open(subs, "w", encoding="utf-8") as fh:
                json.dump({
                    "subscriptions": [{
                        "subscription_id": "sub.core",
                        "watchlist": ["IREN", "AAOI", "AMBA", "OUST"],
                        "themes": ["physical-ai", "robotics", "ai-power"],
                        "policy_ids": ["cadence.news_filings"],
                    }],
                    "max_runs_per_hour": 60,
                }, fh)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cosmosiq_main([
                    "--scheduled-tick", "--persist-dir", store,
                    "--tick-now", "2026-06-29T15:00:00Z", "--subscriptions", subs])
            self.assertEqual(rc, 0)
            log = buf.getvalue()
            self.assertIn("ONE scheduled tick", log)
            self.assertIn("not a daemon", log)
            self.assertIn("baseline", log)                  # first run: note, no flood
            self.assertIn("One tick only -- exiting", log)
            for name in ("run_store.jsonl", "schedule_state_store.jsonl"):
                self.assertTrue(os.path.isfile(os.path.join(store, name)),
                                "missing persisted store {0}".format(name))
            # and the follow-up controls from the guide run offline too
            with redirect_stdout(io.StringIO()):
                self.assertEqual(pulse_cli_main(
                    ["--list-alerts", "--persist-dir", store]), 0)


# =========================================================================== #
# 8. Guards -- alerts.py AST bans, no execution word, offline, additive        #
# =========================================================================== #
class AlertModuleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = _read(_ALERTS_PY)
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
                        "banned import {0!r} in alerts.py".format(name))

    def test_no_loop_async_or_timed_wait_construct(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in alerts.py")
            self.assertNotIsInstance(node, ast.AsyncFunctionDef)
            self.assertNotIsInstance(node, ast.Await)
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotIn(called, _BANNED_CALL_NAMES,
                                 "daemon-style call {0!r} in alerts.py".format(called))

    def test_import_has_no_side_effect_beyond_definitions(self):
        allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr,
                   ast.FunctionDef, ast.ClassDef)
        for node in self.tree.body:
            self.assertIsInstance(node, allowed)
            if isinstance(node, ast.Expr):      # only the docstring
                self.assertIsInstance(node.value, ast.Constant)

    def test_no_execution_or_trading_word_anywhere(self):
        # 020D: the FORBIDDEN_ALERT_PHRASES + RECOMMENDED_REVIEW_ACTIONS constants are the ONLY
        # place action language may appear -- they exist precisely to REJECT such language in
        # alerts. Strip those deliberate data guards, then the rest of alerts.py must be clean.
        from reality_mesh.alerts import (FORBIDDEN_ALERT_PHRASES,
                                         RECOMMENDED_REVIEW_ACTIONS)
        low = self.source.lower()
        for phrase in sorted(FORBIDDEN_ALERT_PHRASES | RECOMMENDED_REVIEW_ACTIONS,
                             key=len, reverse=True):
            low = low.replace(phrase.lower(), " ")
        for word in _EXECUTION_WORDS:
            self.assertIsNone(re.search(r"\b{0}\b".format(word), low),
                              "execution-adjacent word {0!r} in alerts.py".format(word))

    def test_no_verified_fact_claim_in_the_module(self):
        self.assertNotIn("verified_fact", self.source)

    def test_no_wall_clock_or_randomness(self):
        for token in _WALL_CLOCK_TOKENS:
            self.assertNotIn(token, self.source, "wall-clock call {0!r}".format(token))
        self.assertIsNone(re.search(r"\brandom\b|\brandint\b|\buuid\b",
                                    self.source.lower()))

    def test_no_function_named_like_a_metric(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNone(re.search(r"(score|rank|rating)", node.name.lower()),
                                  "banned fn name {0!r}".format(node.name))

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()

    def test_exports_are_additive_on_the_package(self):
        for name in ("Alert", "AlertAcknowledgment", "AlertStore",
                     "AlertAcknowledgmentStore", "AlertGenerationResult",
                     "ALERT_CATEGORIES", "ALERT_SEVERITIES", "generate_alerts_for_run",
                     "acknowledge_alert", "alerts_with_status", "unacknowledged_alerts",
                     "acknowledged_alerts", "build_alert_inbox_panel"):
            self.assertTrue(hasattr(rm, name), "reality_mesh.{0} missing".format(name))

    def test_the_seven_013b_stores_are_untouched(self):
        # the alert stores are ADDITIVE: the 013B spine still counts exactly seven.
        self.assertEqual(len(S.STORE_CLASSES), 7)
        self.assertNotIn(AlertStore, S.STORE_CLASSES)


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
