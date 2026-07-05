"""IMPLEMENTATION-020D -- Shadow 24x7 mode: continuous SHADOW operation, marked alerts.

The system runs continuously in SHADOW mode and generates alerts, but every shadow alert is
clearly marked NON-PRODUCTION and escalates to nothing: it lands in the in-app inbox only, with
NO external delivery and NO production escalation. This suite proves the 020D acceptance list:

* SHADOW_24X7 can be enabled EXPLICITLY and is NOT the default (the service starts OFF);
* the service runs a pulse in shadow through the FULL 013 chain (persists / gates / replays);
* DQ gates every shadow pulse; agent health + source health + run history update; replay works;
* alerts are generated AS SHADOW alerts (mode=SHADOW_24X7 + the shadow marker + a recommended
  review action + the run's dq_state + a candidate_ref when applicable);
* production delivery / escalation is DISABLED in shadow (inbox only; no external delivery);
* a shadow alert can NEVER carry buy/sell/order language (construction ValueError + a regex
  sweep over generated shadow alerts) and can NEVER bypass DQ (a social-only / DQ-failed run
  cannot yield a critical shadow alert);
* shadow mode can pause / resume; a source failure -> a visible source gap; an agent failure ->
  a visible agent-health issue; NO fixture fall-back in shadow;
* continuous PRODUCTION_24X7 stays refused; the module stays offline + AST-clean.

Entirely OFFLINE and deterministic: injected ISO ``now`` strings everywhere; a socket
kill-switch guards the whole module.
"""

from __future__ import annotations

import ast
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
from reality_mesh.alerts import (
    FORBIDDEN_ALERT_PHRASES,
    RECOMMENDED_REVIEW_ACTIONS,
    SHADOW_MARKER,
    SHADOW_MODE_VALUE,
    Alert,
    AlertStore,
    generate_alerts_for_run,
    generate_shadow_alerts_for_run,
    run_dq_state,
    to_shadow,
)
from reality_mesh.models import AgentFinding, RealitySignal, ThemePulse
from reality_mesh.runtime import PulseRun
from reality_mesh.replay import ReplayHarness
from reality_mesh.runtime import ReplayRequest
from reality_mesh.ledger import AgentRunLedger
from reality_mesh.orchestrator import Subscription
from cosmosiq_service import (
    DEFAULT_MODE,
    ServiceConfig,
    ServiceMode,
    continuous_activation_gate,
    load_health,
    pause,
    requires_activation_gate,
    resume,
    run_once,
)

_SERVICE_PY = os.path.join(_SRC, "cosmosiq_service", "service.py")
_ALERTS_PY = os.path.join(_SRC, "reality_mesh", "alerts.py")

# A Monday, 15:00 UTC -- inside the default 14:30-21:00 UTC session.
_NOW = "2026-06-29T15:00:00Z"
_EARLIER = "2026-06-29T14:00:00Z"

_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "asyncio", "threading", "multiprocessing", "subprocess",
                        "smtplib", "ftplib", "socketserver", "signal")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline 020D shadow suite")


_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# Store seeding helpers (mirror the 015C alert suite)                           #
# --------------------------------------------------------------------------- #
def _seed_run(store_dir, run_id, ts, *, pulses=(), signals=(), findings=(), dq=()):
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


def _sub(sid="sub.core", policy_ids=("cadence.news_filings",), adapter_refs=(),
         watchlist=("IREN", "NVDA"), data_dir=""):
    return Subscription(
        subscription_id=sid, watchlist=tuple(watchlist), themes=("physical_ai", "robotics"),
        policy_ids=tuple(policy_ids), adapter_refs=tuple(adapter_refs), data_dir=data_dir)


def _config(store_dir, *, mode=ServiceMode.SHADOW_24X7, subscriptions=None, **kw):
    return ServiceConfig(
        mode=mode, store_dir=store_dir,
        subscriptions=(subscriptions if subscriptions is not None else (_sub(),)), **kw)


# =========================================================================== #
# 1. The shadow gate is LIFTED; production stays refused; shadow not default   #
# =========================================================================== #
class ShadowGateTests(unittest.TestCase):
    def test_shadow_continuous_is_activated_not_gated(self):
        self.assertFalse(requires_activation_gate(ServiceMode.SHADOW_24X7))
        self.assertEqual(continuous_activation_gate(ServiceMode.SHADOW_24X7), "")

    def test_production_continuous_still_refused(self):
        self.assertTrue(requires_activation_gate(ServiceMode.PRODUCTION_24X7))
        self.assertEqual(continuous_activation_gate(ServiceMode.PRODUCTION_24X7), "Phase-020F")

    def test_shadow_is_not_the_default_mode(self):
        self.assertIs(DEFAULT_MODE, ServiceMode.OFF)
        with tempfile.TemporaryDirectory() as d:
            self.assertIs(ServiceConfig(store_dir=d).mode, ServiceMode.OFF)

    def test_shadow_can_be_enabled_explicitly(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIs(_config(d).mode, ServiceMode.SHADOW_24X7)


# =========================================================================== #
# 2. The Alert record -- shadow fields + closed vocab + forbidden-phrase guard #
# =========================================================================== #
class ShadowAlertRecordTests(unittest.TestCase):
    def _alert(self, **kw):
        base = dict(alert_id="alert.x", run_id="run-b", category="theme_pulse_changed",
                    severity="notice", human_readable_reason="Theme pulse changed state.",
                    created_at=_NOW)
        base.update(kw)
        return Alert(**base)

    def test_shadow_fields_default_empty_preserving_015c(self):
        alert = self._alert()
        self.assertEqual(alert.mode, "")
        self.assertEqual(alert.recommended_review_action, "")
        self.assertEqual(alert.dq_state, "")
        self.assertEqual(alert.candidate_ref, "")

    def test_recommended_review_action_is_a_closed_vocabulary(self):
        self.assertEqual(RECOMMENDED_REVIEW_ACTIONS, frozenset({
            "Review Required", "Review Candidate", "Review Thesis", "Review Data Gap",
            "Review Red-Team Risk", "Review Portfolio Fit", "Open Manual Execution Preview"}))
        self._alert(recommended_review_action="Review Thesis")   # in vocab: ok
        self._alert(recommended_review_action="")                # empty allowed
        with self.assertRaises(ValueError):
            self._alert(recommended_review_action="Place The Order")

    def test_forbidden_action_phrases_are_a_closed_set(self):
        self.assertEqual(FORBIDDEN_ALERT_PHRASES, frozenset({
            "buy now", "sell now", "strong buy", "submit order", "place order",
            "auto trade", "auto rebalance", "broker submit", "guaranteed upside"}))

    def test_forbidden_phrase_in_reason_is_construction_rejected(self):
        for phrase in FORBIDDEN_ALERT_PHRASES:
            with self.assertRaises(ValueError):
                self._alert(human_readable_reason="Signal says {0} on this ticker".format(phrase))

    def test_forbidden_phrase_case_insensitive_and_in_action_slot(self):
        with self.assertRaises(ValueError):
            self._alert(human_readable_reason="A STRONG BUY signal emerged.")
        # the forbidden guard also covers the action slot (before the vocab check would run)
        with self.assertRaises(ValueError):
            self._alert(recommended_review_action="submit order")


# =========================================================================== #
# 3. to_shadow -- marks, review-tags, carries dq/candidate, caps weak/DQ-fail  #
# =========================================================================== #
class ToShadowTests(unittest.TestCase):
    def _base(self, category="theme_pulse_changed", severity="notice",
              reason="Theme pulse changed.", tickers=()):
        return Alert(alert_id="alert.{0}".format(category), run_id="run-b", category=category,
                     severity=severity, human_readable_reason=reason,
                     subject_tickers=tickers, created_at=_NOW)

    def test_shadow_alert_is_marked_and_review_tagged(self):
        shadow = to_shadow(self._base(), now=_NOW, dq_state="pass")
        self.assertEqual(shadow.mode, SHADOW_MODE_VALUE)
        self.assertTrue(shadow.human_readable_reason.startswith(SHADOW_MARKER))
        self.assertIn(shadow.recommended_review_action, RECOMMENDED_REVIEW_ACTIONS)
        self.assertEqual(shadow.recommended_review_action, "Review Thesis")
        self.assertEqual(shadow.dq_state, "pass")
        self.assertEqual(shadow.alert_id, "shadow.alert.theme_pulse_changed")

    def test_candidate_ref_set_when_a_ticker_subject_exists(self):
        shadow = to_shadow(self._base(category="filing_dilution_risk", severity="warning",
                                      tickers=("IREN",)), now=_NOW, dq_state="pass",
                           candidate_ref="IREN")
        self.assertEqual(shadow.candidate_ref, "IREN")

    def test_critical_capped_to_warning_when_dq_failed(self):
        shadow = to_shadow(self._base(category="major_risk_emerged", severity="critical"),
                           now=_NOW, dq_state="failed")
        self.assertEqual(shadow.severity, "warning")

    def test_critical_capped_to_warning_for_weak_social(self):
        shadow = to_shadow(self._base(category="social_narrative_spike", severity="critical"),
                           now=_NOW, dq_state="pass")
        self.assertEqual(shadow.severity, "warning")

    def test_critical_preserved_when_dq_healthy_and_not_social(self):
        shadow = to_shadow(self._base(category="major_risk_emerged", severity="critical"),
                           now=_NOW, dq_state="pass")
        self.assertEqual(shadow.severity, "critical")


# =========================================================================== #
# 4. generate_shadow_alerts_for_run -- diff, mark, persist append-only         #
# =========================================================================== #
class GenerateShadowAlertsTests(unittest.TestCase):
    def _two_runs(self, d, a_kw, b_kw, *, now=_NOW):
        _seed_run(d, "run-a", _EARLIER, **a_kw)
        _seed_run(d, "run-b", _NOW, **b_kw)
        return generate_shadow_alerts_for_run(d, "run-b", now=now)

    def test_baseline_first_run_makes_no_shadow_alert(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-a", _NOW, pulses=(_pulse(state="Warming"),))
            result = generate_shadow_alerts_for_run(d, "run-a", now=_NOW)
            self.assertTrue(result.baseline)
            self.assertEqual(result.alerts, ())

    def test_theme_change_yields_one_marked_shadow_alert(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d, dict(pulses=(_pulse(state="Warming"),)),
                dict(pulses=(_pulse(state="Igniting"),)))
            self.assertEqual(len(result.alerts), 1)
            shadow = result.alerts[0]
            self.assertEqual(shadow.mode, SHADOW_MODE_VALUE)
            self.assertEqual(shadow.category, "theme_pulse_changed")
            self.assertIn(SHADOW_MARKER, shadow.human_readable_reason)
            self.assertEqual(shadow.recommended_review_action, "Review Thesis")
            self.assertEqual(shadow.dq_state, "unknown")

    def test_shadow_alerts_persist_append_only_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            self._two_runs(d, dict(pulses=(_pulse(state="Warming"),)),
                           dict(pulses=(_pulse(state="Igniting"),)))
            first = len(AlertStore(d).read_all())
            # a re-observation of the same run appends nothing (append-only)
            again = generate_shadow_alerts_for_run(d, "run-b", now=_NOW)
            self.assertEqual(again.alerts, ())
            self.assertEqual(len(AlertStore(d).read_all()), first)

    def test_candidate_ref_flows_from_a_ticker_subject(self):
        with tempfile.TemporaryDirectory() as d:
            finding = AgentFinding(
                finding_id="finding.news_filings.dilution_risk.iren",
                agent_id="news_filings.sensor", finding_type="dilution_risk",
                affected_companies=("IREN",))
            result = self._two_runs(d, dict(findings=()), dict(findings=(finding,)))
            self.assertEqual(len(result.alerts), 1)
            self.assertEqual(result.alerts[0].category, "filing_dilution_risk")
            self.assertEqual(result.alerts[0].candidate_ref, "IREN")

    def test_dq_failed_run_cannot_yield_a_critical_shadow_alert(self):
        with tempfile.TemporaryDirectory() as d:
            # run-b has a newly-failing DQ (which in 015C is a CRITICAL source_data_quality_failure);
            # the run's dq_state is 'failed', so the shadow alert is capped below critical.
            result = self._two_runs(
                d, dict(dq=(_dq("run-a", "coverage", "pass"),)),
                dict(dq=(_dq("run-b", "coverage", "fail", "coverage gate FAILED"),
                         _dq("run-b", "source_failure", "failed", "source went dark"))))
            self.assertTrue(result.alerts)
            self.assertEqual(run_dq_state(d, "run-b"), "failed")
            for shadow in result.alerts:
                self.assertEqual(shadow.category, "source_data_quality_failure")
                self.assertNotEqual(shadow.severity, "critical")
                self.assertEqual(shadow.dq_state, "failed")

    def test_social_only_run_cannot_yield_a_critical_shadow_alert(self):
        with tempfile.TemporaryDirectory() as d:
            result = self._two_runs(
                d,
                dict(signals=(_signal("sig.narr", "narrative", "accelerating",
                                      urgency="watch", magnitude="moderate"),)),
                dict(signals=(_signal("sig.narr", "narrative", "accelerating",
                                      urgency="high", magnitude="moderate"),)))
            self.assertTrue(result.alerts)
            for shadow in result.alerts:
                self.assertNotEqual(shadow.severity, "critical")

    def test_regex_sweep_no_action_language_in_generated_shadow_alerts(self):
        with tempfile.TemporaryDirectory() as d:
            self._two_runs(d, dict(pulses=(_pulse(state="Warming", crowding="moderate"),),
                                   signals=(_signal("s.reg", "market_regime", "rising"),)),
                           dict(pulses=(_pulse(state="Igniting", crowding="extreme"),),
                                signals=(_signal("s.reg", "market_regime", "falling"),)))
            sweep = re.compile("|".join(re.escape(p) for p in FORBIDDEN_ALERT_PHRASES),
                               re.IGNORECASE)
            for alert in AlertStore(d).read_all():
                self.assertIsNone(sweep.search(alert.human_readable_reason), alert.alert_id)
                self.assertIsNone(sweep.search(alert.recommended_review_action or ""),
                                  alert.alert_id)

    def test_shadow_layer_coexists_with_plain_015c_alerts(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-a", _EARLIER, pulses=(_pulse(state="Warming"),))
            _seed_run(d, "run-b", _NOW, pulses=(_pulse(state="Igniting"),))
            plain = generate_alerts_for_run(d, "run-b", now=_NOW)           # 015C, unchanged
            shadow = generate_shadow_alerts_for_run(d, "run-b", now=_NOW)   # 020D layer
            self.assertTrue(plain.alerts and shadow.alerts)
            self.assertTrue(all(a.mode == "" for a in plain.alerts))
            self.assertTrue(all(a.mode == SHADOW_MODE_VALUE for a in shadow.alerts))


# =========================================================================== #
# 5. The service runs a shadow pulse through the full 013 chain, inbox only    #
# =========================================================================== #
class ShadowServiceTickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = cls.tmp.name
        cls.config = _config(cls.d, mode=ServiceMode.SHADOW_24X7)
        cls.health = run_once(cls.config, now=_NOW, pid=7)
        cls.run_id = cls.health.last_successful_run_id

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_shadow_tick_persists_a_run(self):
        self.assertTrue(self.run_id.startswith("sched.cadence.news_filings."))
        self.assertEqual(self.health.service_mode, "shadow_24x7")
        self.assertTrue(S.RunStore(self.d).query(run_id=self.run_id))

    def test_dq_gate_ran_on_the_shadow_pulse(self):
        dq = S.DataQualityStore(self.d).query(run_id=self.run_id)
        self.assertIn("gate_overall", {r.category for r in dq})
        self.assertTrue(self.health.dq_status_summary.get("gate_ran"))

    def test_agent_and_source_health_update(self):
        self.assertGreaterEqual(self.health.agent_health_summary.get("results", 0), 1)
        self.assertIn("coverage_records", self.health.source_health_summary)
        self.assertTrue(AgentRunLedger(self.d).results_for_run(self.run_id))

    def test_shadow_run_is_replayable(self):
        harness = ReplayHarness(
            S.EventStore(self.d), S.FindingStore(self.d), S.SignalStore(self.d),
            S.ThemePulseStore(self.d), S.RunStore(self.d))
        replayed = harness.replay(ReplayRequest(run_id=self.run_id), now=_NOW)
        self.assertTrue(replayed.deterministic_match, replayed.differences)

    def test_no_external_delivery_or_production_escalation_in_the_log(self):
        import json
        success = [json.loads(l) for l in _read(self.config.log_path).splitlines()
                   if '"tick.success"' in l]
        self.assertTrue(success)
        line = success[-1]
        self.assertIs(line["external_delivery"], False)
        self.assertIs(line["production_escalation"], False)
        self.assertEqual(line["alerts_channel"], "in_app_inbox_only")
        self.assertIn("shadow_alerts", line)


# =========================================================================== #
# 6. Shadow pause/resume; failures stay visible; no fixture fall-back          #
# =========================================================================== #
class ShadowControlAndFailureTests(unittest.TestCase):
    def test_shadow_pause_then_resume(self):
        with tempfile.TemporaryDirectory() as d:
            config = _config(d, mode=ServiceMode.SHADOW_24X7)
            paused = pause(config, now=_NOW)
            self.assertTrue(paused.is_paused)
            after_pause = run_once(config, now="2026-06-29T15:05:00Z", pid=1)
            self.assertTrue(after_pause.is_paused)
            self.assertEqual(after_pause.last_successful_run_id, "")
            self.assertFalse(os.path.isfile(os.path.join(d, "run_store.jsonl")))
            resumed = resume(config, now="2026-06-29T15:06:00Z")
            self.assertFalse(resumed.is_paused)
            after_resume = run_once(config, now="2026-06-29T15:07:00Z", pid=1)
            self.assertTrue(after_resume.last_successful_run_id.startswith("sched."))

    def test_source_failure_is_a_visible_source_gap_no_fixture_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            # a subscription data_dir that does not exist -> a FAILED pulse, never a silent
            # fixture fall-back in shadow.
            missing = os.path.join(d, "does_not_exist")
            config = _config(d, mode=ServiceMode.SHADOW_24X7,
                             subscriptions=(_sub(data_dir=missing),))
            health = run_once(config, now=_NOW, pid=1)
            self.assertEqual(health.consecutive_failures, 1)
            failed_run = health.last_failed_run_id
            dq = S.DataQualityStore(d).query(run_id=failed_run)
            self.assertIn("source_failure", {r.category for r in dq})
            self.assertEqual([r.status for r in dq], ["failed"])
            # no fabricated spine run for a failed shadow pulse (no fixture fall-back)
            self.assertEqual(S.RunStore(d).query(run_id=failed_run), ())

    def test_agent_failure_is_a_visible_agent_health_issue(self):
        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, "nope")
            config = _config(d, mode=ServiceMode.SHADOW_24X7,
                             subscriptions=(_sub(data_dir=missing),))
            health = run_once(config, now=_NOW, pid=1)
            failed_run = health.last_failed_run_id
            results = AgentRunLedger(d).results_for_run(failed_run)
            self.assertEqual([r.status for r in results], ["failed"])
            self.assertEqual([r.health_status for r in results], ["failed"])


# =========================================================================== #
# 7. Offline + AST guards (shadow adds no net/scheduler/broker surface)        #
# =========================================================================== #
class ShadowGuardTests(unittest.TestCase):
    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()

    def test_service_py_has_no_network_or_delivery_import(self):
        tree = ast.parse(_read(_SERVICE_PY))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for banned in _BANNED_IMPORT_ROOTS:
                    self.assertFalse(name == banned or name.startswith(banned + "."),
                                     "banned import {0!r} in service.py".format(name))

    def test_shadow_health_reloads_the_service_mode(self):
        with tempfile.TemporaryDirectory() as d:
            config = _config(d, mode=ServiceMode.SHADOW_24X7)
            run_once(config, now=_NOW, pid=1)
            self.assertEqual(load_health(config).service_mode, "shadow_24x7")


if __name__ == "__main__":
    unittest.main()
