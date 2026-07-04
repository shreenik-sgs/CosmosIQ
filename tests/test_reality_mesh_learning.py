"""IMPLEMENTATION-017A -- Learning & Feedback core: outcomes, roll-ups, reliability.

This suite proves the Learning & Feedback discipline:

* an :class:`OutcomeRecord` compares a PAST persisted claim to a LATER persisted
  observation, both cited by id; it NEVER modifies the subject it evaluates;
* where the later observation does not exist the outcome is ``unresolved`` -- an
  honest state (no observed run / value), never a guess (enforced at construction);
* reliability / accuracy is LABELS + VOLUME COUNTS only: no record carries any
  numeric metric / percentage / float field (introspected), and the 013B store
  guard refuses a metric key outright;
* below 3 resolved outcomes every roll-up honestly reads ``insufficient_history``;
* source reliability is learned by authority tier: a failing rumor tier rolls up
  ``deteriorating``, and a past record is NEVER retroactively upgraded -- new
  evidence appends a NEW line while the earlier line stays byte-unchanged;
* tracking is append-only + idempotent: a re-track leaves the outcome store
  byte-identical, and learning never modifies any existing store byte;
* the reserved ``thesis_deteriorated`` / ``major_risk_emerged`` alert categories
  are emitted ONLY where an outcome implies them (contradicted theme claim /
  followed-through risk-state claim); ``new_opportunity_hypothesis`` stays reserved;
* learning.py carries no banned import / loop / wall-clock / metric-named function;
  the demo default + default pulse remain byte-identical; exports are additive.

Entirely OFFLINE and deterministic: injected ISO ``now`` strings everywhere; a
socket kill-switch guards the whole module.
"""

from __future__ import annotations

import ast
import os
import re
import socket
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import stores as S
from reality_mesh.alerts import AlertStore, generate_alerts_for_run
from reality_mesh.learning import (
    LEARNING_RECORDS,
    LEARNING_STORE_CLASSES,
    LEARNING_THRESHOLDS,
    OUTCOME_LABELS,
    RELIABILITY_LABELS,
    RISK_CLAIM_STATES,
    SUBJECT_KINDS,
    LearningStore,
    OutcomeRecord,
    OutcomeStore,
    OutcomeTracker,
    SignalReliabilityRecord,
    SourceReliabilityRecord,
    ThemePulseAccuracyRecord,
    emit_outcome_alerts,
    persisted_run_ids,
    record_learning_rollups,
    record_outcomes,
    roll_signal_reliability,
    roll_source_reliability,
    roll_theme_pulse_accuracy,
    track_outcomes,
)
from reality_mesh.models import RealitySignal, ThemePulse
from reality_mesh.runtime import PulseRun
from reality_mesh.validation import assert_no_trade_fields

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_LEARNING_PY = os.path.join(_PKG_DIR, "learning.py")

_T1 = "2026-06-29T14:00:00Z"
_T2 = "2026-06-29T15:00:00Z"
_T3 = "2026-06-29T16:00:00Z"
_NOW = "2026-06-29T17:00:00Z"
_LATER = "2026-07-01T09:00:00Z"

# The 015 guard vocabulary applied to learning.py (learning observes, never acts).
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

# Field-name fragments that would smuggle a numeric metric onto a record.
_METRIC_FIELD_FRAGMENTS = ("score", "rank", "rating", "pct", "percent", "ratio",
                           "probability", "weight")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline learning suite")


_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _snapshot_dir(store_dir):
    """filename -> bytes for every file in the store dir."""
    out = {}
    for name in sorted(os.listdir(store_dir)):
        path = os.path.join(store_dir, name)
        if os.path.isfile(path):
            out[name] = _read_bytes(path)
    return out


def _seed_run(store_dir, run_id, ts, *, pulses=(), signals=()):
    """Persist one fabricated run (spine + records) into the 013B stores."""
    S.RunStore(store_dir).append(
        PulseRun(run_id=run_id, started_at=ts, completed_at=ts, mode="pulse"),
        timestamp=ts)
    for pulse in pulses:
        S.ThemePulseStore(store_dir).append(pulse, run_id=run_id, timestamp=ts)
    for signal in signals:
        S.SignalStore(store_dir).append(signal, run_id=run_id, timestamp=ts)


def _pulse(theme="physical-ai", state="Warming", pulse_id=None):
    return ThemePulse(theme_pulse_id=pulse_id or "pulse.{0}".format(theme),
                      theme_id=theme, theme_name=theme, state=state)


def _signal(sid, direction, discipline="technical_regime", companies=("IREN",)):
    return RealitySignal(signal_id=sid, discipline=discipline,
                         direction_label=direction,
                         affected_companies=tuple(companies))


def _outcome(**kw):
    base = dict(outcome_id="outcome.signal.sig-1.run-1.run-2",
                subject_kind="signal", subject_id="sig-1",
                subject_run_id="run-1", subject_discipline="technical_regime",
                claimed="direction_label 'rising'", observed_run_id="run-2",
                observed="direction_label 'rising' on signal 'sig-1'",
                outcome_label="followed_through",
                basis="Signal 'sig-1' in run 'run-1' claimed direction_label "
                      "'rising'; run 'run-2' persisted the same.",
                created_at=_NOW)
    base.update(kw)
    return OutcomeRecord(**base)


def _signal_outcome_for_roll(n, label, discipline="technical_regime",
                             subject_id=None, run="run-1", observed_run="run-2"):
    """A synthetic resolved/unresolved signal outcome for the pure roll-ups."""
    kw = dict(
        outcome_id="outcome.signal.s{0}.{1}".format(n, label),
        subject_id=subject_id or "sig-{0}".format(n),
        subject_run_id=run, subject_discipline=discipline,
        outcome_label=label,
        basis="Synthetic outcome {0} for roll-up tests citing run '{1}' and "
              "run '{2}'.".format(n, run, observed_run))
    if label == "unresolved":
        kw.update(observed_run_id="", observed="")
    else:
        kw.update(observed_run_id=observed_run,
                  observed="direction_label 'falling' on signal 'x'")
    return _outcome(**kw)


def _theme_outcome_for_roll(n, label, theme="physical-ai"):
    kw = dict(
        outcome_id="outcome.theme-pulse.p{0}.{1}".format(n, label),
        subject_kind="theme_pulse", subject_id="pulse.{0}.{1}".format(theme, n),
        subject_discipline="", subject_theme_id=theme,
        claimed="state 'Warming'", outcome_label=label,
        basis="Synthetic theme outcome {0} citing run 'run-1' and "
              "run 'run-2'.".format(n))
    if label == "unresolved":
        kw.update(observed_run_id="", observed="")
    else:
        kw.update(observed_run_id="run-2",
                  observed="state 'Igniting' on theme pulse 'p'")
    return _outcome(**kw)


# =========================================================================== #
# 1. The record set -- closed vocabularies, honesty invariants, frozen        #
# =========================================================================== #
class OutcomeRecordTests(unittest.TestCase):
    def test_closed_outcome_vocabulary(self):
        self.assertEqual(OUTCOME_LABELS, frozenset(
            {"followed_through", "contradicted", "faded", "unresolved"}))
        with self.assertRaises(ValueError):
            _outcome(outcome_label="hit")
        with self.assertRaises(ValueError):
            _outcome(outcome_label="")

    def test_closed_subject_kinds(self):
        self.assertEqual(SUBJECT_KINDS,
                         frozenset({"signal", "theme_pulse", "finding"}))
        with self.assertRaises(ValueError):
            _outcome(subject_kind="thesis")

    def test_required_citations(self):
        for name in ("outcome_id", "subject_id", "subject_run_id", "claimed",
                     "basis", "created_at"):
            with self.assertRaises(ValueError, msg=name):
                _outcome(**{name: ""})

    def test_unresolved_is_never_a_guess(self):
        # unresolved MUST carry no observed run / value -- honest, not fabricated.
        ok = _outcome(outcome_label="unresolved", observed_run_id="", observed="",
                      outcome_id="outcome.signal.sig-1.run-1.unresolved",
                      basis="Signal 'sig-1' in run 'run-1' claimed "
                            "direction_label 'rising'; no later run persisted.")
        self.assertEqual(ok.observed_run_id, "")
        self.assertEqual(ok.observed, "")
        with self.assertRaises(ValueError):
            _outcome(outcome_label="unresolved", observed="something")
        with self.assertRaises(ValueError):
            _outcome(outcome_label="unresolved", observed="", observed_run_id="run-2")

    def test_resolved_must_cite_the_observed_run(self):
        for label in ("followed_through", "contradicted", "faded"):
            with self.assertRaises(ValueError, msg=label):
                _outcome(outcome_label=label, observed_run_id="")

    def test_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            _outcome().outcome_label = "contradicted"  # type: ignore[misc]

    def test_discipline_is_a_closed_label(self):
        with self.assertRaises(ValueError):
            _outcome(subject_discipline="astrology")


class RollupRecordTests(unittest.TestCase):
    def _reliability(self, **kw):
        base = dict(learning_id="learn.signal-reliability.x",
                    discipline="technical_regime", window=("run-1", "run-3"),
                    followed_through_count=2, contradicted_count=1,
                    faded_count=1, unresolved_count=0,
                    reliability_label="stable",
                    basis="Across runs 'run-1'..'run-3': volumes only.",
                    created_at=_NOW)
        base.update(kw)
        return SignalReliabilityRecord(**base)

    def test_closed_reliability_vocabulary(self):
        self.assertEqual(RELIABILITY_LABELS, frozenset(
            {"improving", "stable", "deteriorating", "insufficient_history"}))
        with self.assertRaises(ValueError):
            self._reliability(reliability_label="excellent")
        with self.assertRaises(ValueError):
            self._reliability(reliability_label="")

    def test_counts_are_volumes_never_floats(self):
        with self.assertRaises(ValueError):
            self._reliability(followed_through_count=-1)
        with self.assertRaises(ValueError):
            self._reliability(contradicted_count=0.5)
        with self.assertRaises(ValueError):
            self._reliability(faded_count=True)

    def test_window_is_a_run_id_pair(self):
        with self.assertRaises(ValueError):
            self._reliability(window=("run-1",))
        rec = self._reliability(window=["run-1", "run-2"])
        self.assertEqual(rec.window, ("run-1", "run-2"))

    def test_theme_pulse_accuracy_record(self):
        rec = ThemePulseAccuracyRecord(
            learning_id="learn.theme-pulse-accuracy.x", theme_id="physical-ai",
            window=("run-1", "run-2"), transitions_observed=3,
            transitions_followed_through=2, transitions_reversed=1,
            accuracy_label="improving",
            basis="Across runs 'run-1'..'run-2': volumes only.", created_at=_NOW)
        self.assertEqual(rec.accuracy_label, "improving")
        with self.assertRaises(ValueError):
            ThemePulseAccuracyRecord(
                learning_id="x", theme_id="", window=("a", "b"),
                accuracy_label="stable", basis="b", created_at=_NOW)

    def test_source_reliability_requires_a_scope(self):
        with self.assertRaises(ValueError):
            SourceReliabilityRecord(
                learning_id="x", source_kind="", adapter_id="",
                window=("a", "b"), reliability_label="stable", basis="b",
                created_at=_NOW)
        with self.assertRaises(ValueError):
            SourceReliabilityRecord(
                learning_id="x", source_kind="gossip", window=("a", "b"),
                reliability_label="stable", basis="b", created_at=_NOW)
        rec = SourceReliabilityRecord(
            learning_id="x", source_kind="rumor", window=("a", "b"),
            reliability_label="deteriorating", basis="b", created_at=_NOW)
        self.assertEqual(rec.source_kind, "rumor")

    def test_no_trade_or_metric_field_on_any_learning_record(self):
        self.assertEqual(len(LEARNING_RECORDS), 4)
        for cls in LEARNING_RECORDS:
            assert_no_trade_fields(cls)
            for f in fields(cls):
                low = f.name.lower()
                for fragment in _METRIC_FIELD_FRAGMENTS:
                    self.assertNotIn(fragment, low,
                                     "metric-named field {0!r} on {1}".format(
                                         f.name, cls.__name__))

    def test_no_float_value_anywhere_on_instances(self):
        # NO numeric accuracy value / percentage is ever stored as a field.
        instances = (
            _outcome(),
            self._reliability(),
            ThemePulseAccuracyRecord(
                learning_id="l", theme_id="t", window=("a", "b"),
                transitions_observed=3, transitions_followed_through=2,
                transitions_reversed=1, accuracy_label="improving", basis="b",
                created_at=_NOW),
            SourceReliabilityRecord(
                learning_id="l", source_kind="rumor", window=("a", "b"),
                reliability_label="deteriorating", basis="b", created_at=_NOW),
        )
        for record in instances:
            for f in fields(record):
                value = getattr(record, f.name)
                self.assertNotIsInstance(value, float,
                                         "{0}.{1}".format(type(record).__name__,
                                                          f.name))
                self.assertIn(type(value), (str, int, tuple),
                              "{0}.{1}".format(type(record).__name__, f.name))

    def test_store_guard_refuses_a_metric_key_outright(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                OutcomeStore(d).append({"outcome_id": "x", "accuracy_score": 0.9},
                                       record_id="x")


# =========================================================================== #
# 2. Outcome tracking -- past claim vs later observation, both cited          #
# =========================================================================== #
class TrackOutcomeSemanticsTests(unittest.TestCase):
    def _track_two_runs(self, first, second, now=_NOW):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, **first)
            _seed_run(d, "run-2", _T2, **second)
            return track_outcomes(d, now=now)

    def _one(self, outcomes, subject_run_id, subject_kind):
        scoped = [o for o in outcomes
                  if o.subject_run_id == subject_run_id
                  and o.subject_kind == subject_kind]
        self.assertEqual(len(scoped), 1)
        return scoped[0]

    def test_same_theme_stronger_state_follows_through(self):
        outs = self._track_two_runs(
            dict(pulses=(_pulse(state="Warming"),)),
            dict(pulses=(_pulse(state="Igniting"),)))
        outcome = self._one(outs, "run-1", "theme_pulse")
        self.assertEqual(outcome.outcome_label, "followed_through")
        self.assertEqual(outcome.claimed, "state 'Warming'")
        self.assertIn("Igniting", outcome.observed)
        self.assertEqual(outcome.observed_run_id, "run-2")

    def test_theme_state_reversal_is_contradicted(self):
        for observed_state in ("Dormant", "Breaking down", "Exhausting"):
            outs = self._track_two_runs(
                dict(pulses=(_pulse(state="Igniting"),)),
                dict(pulses=(_pulse(state=observed_state),)))
            outcome = self._one(outs, "run-1", "theme_pulse")
            self.assertEqual(outcome.outcome_label, "contradicted",
                             observed_state)

    def test_not_comparable_theme_state_stays_unresolved_never_guessed(self):
        outs = self._track_two_runs(
            dict(pulses=(_pulse(state="Warming"),)),
            dict(pulses=(_pulse(state="Data insufficient"),)))
        outcome = self._one(outs, "run-1", "theme_pulse")
        self.assertEqual(outcome.outcome_label, "unresolved")
        self.assertEqual(outcome.observed_run_id, "")
        self.assertEqual(outcome.observed, "")

    def test_same_signal_direction_follows_through(self):
        outs = self._track_two_runs(
            dict(signals=(_signal("sig.a", "rising"),)),
            dict(signals=(_signal("sig.b", "rising"),)))
        outcome = self._one(outs, "run-1", "signal")
        self.assertEqual(outcome.outcome_label, "followed_through")
        self.assertEqual(outcome.subject_id, "sig.a")
        self.assertIn("sig.b", outcome.observed)

    def test_opposite_signal_direction_is_contradicted(self):
        outs = self._track_two_runs(
            dict(signals=(_signal("sig.a", "rising"),)),
            dict(signals=(_signal("sig.b", "falling"),)))
        self.assertEqual(self._one(outs, "run-1", "signal").outcome_label,
                         "contradicted")

    def test_direction_dropping_to_neutral_fades(self):
        outs = self._track_two_runs(
            dict(signals=(_signal("sig.a", "rising"),)),
            dict(signals=(_signal("sig.b", "stable"),)))
        self.assertEqual(self._one(outs, "run-1", "signal").outcome_label,
                         "faded")

    def test_subject_absent_with_a_later_run_fades(self):
        outs = self._track_two_runs(
            dict(signals=(_signal("sig.a", "rising"),),
                 pulses=(_pulse(theme="robotics", state="Warming"),)),
            dict(signals=(), pulses=()))
        signal_outcome = self._one(outs, "run-1", "signal")
        self.assertEqual(signal_outcome.outcome_label, "faded")
        self.assertEqual(signal_outcome.observed, "absent")
        self.assertEqual(signal_outcome.observed_run_id, "run-2")
        self.assertEqual(self._one(outs, "run-1", "theme_pulse").outcome_label,
                         "faded")

    def test_single_run_is_unresolved_never_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, pulses=(_pulse(),),
                      signals=(_signal("sig.a", "rising"),))
            outs = track_outcomes(d, now=_NOW)
            self.assertEqual(len(outs), 2)
            for outcome in outs:
                self.assertEqual(outcome.outcome_label, "unresolved")
                self.assertEqual(outcome.observed_run_id, "")
                self.assertEqual(outcome.observed, "")
                self.assertIn("honest state", outcome.basis)

    def test_basis_cites_both_run_ids_on_resolved_outcomes(self):
        outs = self._track_two_runs(
            dict(pulses=(_pulse(state="Warming"),),
                 signals=(_signal("sig.a", "rising"),)),
            dict(pulses=(_pulse(state="Igniting"),),
                 signals=(_signal("sig.b", "falling"),)))
        resolved = [o for o in outs if o.outcome_label != "unresolved"]
        self.assertEqual(len(resolved), 2)
        for outcome in resolved:
            self.assertIn("'run-1'", outcome.basis)
            self.assertIn("'run-2'", outcome.basis)
            self.assertIn("'{0}'".format(outcome.subject_id), outcome.basis)

    def test_last_run_subjects_are_tracked_unresolved_too(self):
        outs = self._track_two_runs(
            dict(pulses=(_pulse(state="Warming"),)),
            dict(pulses=(_pulse(state="Igniting"),)))
        outcome = self._one(outs, "run-2", "theme_pulse")
        self.assertEqual(outcome.outcome_label, "unresolved")

    def test_signal_subject_identity_is_discipline_plus_scope(self):
        # Same discipline, DIFFERENT company -> not the same subject -> faded.
        outs = self._track_two_runs(
            dict(signals=(_signal("sig.a", "rising", companies=("IREN",)),)),
            dict(signals=(_signal("sig.b", "rising", companies=("NVDA",)),)))
        self.assertEqual(self._one(outs, "run-1", "signal").outcome_label,
                         "faded")

    def test_deterministic_same_stores_same_outcomes(self):
        first = dict(pulses=(_pulse(state="Warming"),),
                     signals=(_signal("sig.a", "rising"),))
        second = dict(pulses=(_pulse(state="Igniting"),),
                      signals=(_signal("sig.b", "falling"),))
        self.assertEqual(repr(self._track_two_runs(first, second)),
                         repr(self._track_two_runs(first, second)))

    def test_track_requires_an_injected_now(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                track_outcomes(d, now="")

    def test_empty_store_dir_yields_no_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(track_outcomes(d, now=_NOW), ())
            self.assertEqual(persisted_run_ids(d), ())


# =========================================================================== #
# 3. Append-only + idempotence -- history is never rewritten                  #
# =========================================================================== #
class AppendOnlyLearningTests(unittest.TestCase):
    def _seed_two(self, d):
        _seed_run(d, "run-1", _T1, pulses=(_pulse(state="Warming"),),
                  signals=(_signal("sig.a", "rising"),))
        _seed_run(d, "run-2", _T2, pulses=(_pulse(state="Igniting"),),
                  signals=(_signal("sig.b", "falling"),))

    def test_retrack_is_idempotent_byte_identical_store(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_two(d)
            tracker = OutcomeTracker(d)
            tracker.track(now=_NOW)
            path = OutcomeStore(d).path
            before = _read_bytes(path)
            tracker.track(now=_LATER)       # a later re-track appends NOTHING
            self.assertEqual(_read_bytes(path), before)

    def test_learning_never_modifies_any_existing_store_byte(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_two(d)
            before = _snapshot_dir(d)
            outcomes = OutcomeTracker(d).track(now=_NOW)
            record_learning_rollups(
                d, roll_signal_reliability(outcomes, now=_NOW)
                + roll_theme_pulse_accuracy(outcomes, now=_NOW))
            emit_outcome_alerts(d, outcomes, now=_NOW)
            after = _snapshot_dir(d)
            for name, data in before.items():
                self.assertEqual(after[name], data,
                                 "learning modified existing store {0}".format(name))

    def test_outcome_never_modifies_the_subject_it_evaluates(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_two(d)
            signal_bytes = _read_bytes(S.SignalStore(d).path)
            pulse_bytes = _read_bytes(S.ThemePulseStore(d).path)
            run_bytes = _read_bytes(S.RunStore(d).path)
            OutcomeTracker(d).track(now=_NOW)
            self.assertEqual(_read_bytes(S.SignalStore(d).path), signal_bytes)
            self.assertEqual(_read_bytes(S.ThemePulseStore(d).path), pulse_bytes)
            self.assertEqual(_read_bytes(S.RunStore(d).path), run_bytes)

    def test_later_resolution_is_a_new_record_old_unresolved_line_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, pulses=(_pulse(state="Warming"),))
            tracker = OutcomeTracker(d)
            tracker.track(now=_NOW)
            path = OutcomeStore(d).path
            first_lines = _read_bytes(path)
            # A third... second run arrives; the unresolved claim now resolves.
            _seed_run(d, "run-2", _T2, pulses=(_pulse(state="Igniting"),))
            tracker.track(now=_LATER)
            data = _read_bytes(path)
            self.assertTrue(data.startswith(first_lines),
                            "an existing outcome line was rewritten")
            labels = [o.outcome_label for o in tracker.outcomes()
                      if o.subject_run_id == "run-1"]
            self.assertEqual(labels, ["unresolved", "followed_through"])

    def test_outcome_store_has_no_mutation_affordance(self):
        for store_cls in LEARNING_STORE_CLASSES:
            names = {n for n in dir(store_cls) if not n.startswith("_")}
            for banned in ("update", "delete", "remove", "rewrite", "pop"):
                self.assertNotIn(banned, names, store_cls.__name__)

    def test_record_outcomes_returns_only_newly_appended_ids(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_two(d)
            outcomes = track_outcomes(d, now=_NOW)
            first = record_outcomes(d, outcomes)
            self.assertEqual(len(first), len(outcomes))
            self.assertEqual(record_outcomes(d, outcomes), ())

    def test_learning_store_round_trips_each_shape(self):
        with tempfile.TemporaryDirectory() as d:
            rollup = SignalReliabilityRecord(
                learning_id="learn.signal-reliability.x", discipline="narrative",
                window=("run-1", "run-2"), followed_through_count=1,
                contradicted_count=2, faded_count=1, unresolved_count=0,
                reliability_label="deteriorating",
                basis="Across runs 'run-1'..'run-2': volumes only.",
                created_at=_NOW)
            record_learning_rollups(d, (rollup,))
            back = LearningStore(d).read_all()
            self.assertEqual(back, (rollup,))
            with self.assertRaises(TypeError):
                LearningStore(d).append(_outcome())


# =========================================================================== #
# 4. Roll-ups -- labels + counts; thresholds as data; no pretended confidence #
# =========================================================================== #
class RollupSemanticsTests(unittest.TestCase):
    def test_threshold_lives_as_data(self):
        self.assertEqual(LEARNING_THRESHOLDS["min_resolved_outcomes"], 3)

    def test_below_three_resolved_reads_insufficient_history(self):
        outcomes = (_signal_outcome_for_roll(1, "followed_through"),
                    _signal_outcome_for_roll(2, "contradicted"),
                    _signal_outcome_for_roll(3, "unresolved"))
        (record,) = roll_signal_reliability(outcomes, now=_NOW)
        self.assertEqual(record.reliability_label, "insufficient_history")
        self.assertIn("no label pretends confidence", record.basis)
        self.assertEqual(record.unresolved_count, 1)

    def test_majority_follow_through_reads_improving(self):
        outcomes = tuple(_signal_outcome_for_roll(i, "followed_through")
                         for i in range(3))
        (record,) = roll_signal_reliability(outcomes, now=_NOW)
        self.assertEqual(record.reliability_label, "improving")
        self.assertEqual(record.followed_through_count, 3)

    def test_majority_misses_reads_deteriorating_and_balance_reads_stable(self):
        misses = (_signal_outcome_for_roll(1, "contradicted"),
                  _signal_outcome_for_roll(2, "contradicted"),
                  _signal_outcome_for_roll(3, "faded"))
        (record,) = roll_signal_reliability(misses, now=_NOW)
        self.assertEqual(record.reliability_label, "deteriorating")
        balanced = (_signal_outcome_for_roll(1, "followed_through"),
                    _signal_outcome_for_roll(2, "followed_through"),
                    _signal_outcome_for_roll(3, "contradicted"),
                    _signal_outcome_for_roll(4, "faded"))
        (record,) = roll_signal_reliability(balanced, now=_NOW)
        self.assertEqual(record.reliability_label, "stable")

    def test_grouped_per_discipline_in_sorted_sequence(self):
        outcomes = (_signal_outcome_for_roll(1, "followed_through",
                                             discipline="technical_regime"),
                    _signal_outcome_for_roll(2, "contradicted",
                                             discipline="narrative"))
        records = roll_signal_reliability(outcomes, now=_NOW)
        self.assertEqual([r.discipline for r in records],
                         ["narrative", "technical_regime"])
        for record in records:
            self.assertIn("'run-1'", record.basis)

    def test_theme_pulse_accuracy_counts_transitions(self):
        outcomes = (_theme_outcome_for_roll(1, "followed_through"),
                    _theme_outcome_for_roll(2, "followed_through"),
                    _theme_outcome_for_roll(3, "contradicted"),
                    _theme_outcome_for_roll(4, "unresolved"),
                    _theme_outcome_for_roll(5, "followed_through",
                                            theme="robotics"))
        records = roll_theme_pulse_accuracy(outcomes, now=_NOW)
        self.assertEqual([r.theme_id for r in records],
                         ["physical-ai", "robotics"])
        physical = records[0]
        self.assertEqual(physical.transitions_observed, 3)   # resolved only
        self.assertEqual(physical.transitions_followed_through, 2)
        self.assertEqual(physical.transitions_reversed, 1)
        self.assertEqual(physical.accuracy_label, "improving")
        self.assertEqual(records[1].accuracy_label, "insufficient_history")

    def test_rollup_ignores_other_subject_kinds(self):
        outcomes = (_theme_outcome_for_roll(1, "followed_through"),)
        self.assertEqual(roll_signal_reliability(outcomes, now=_NOW), ())
        signal_only = (_signal_outcome_for_roll(1, "followed_through"),)
        self.assertEqual(roll_theme_pulse_accuracy(signal_only, now=_NOW), ())

    def test_rollup_recording_is_idempotent(self):
        outcomes = tuple(_signal_outcome_for_roll(i, "followed_through")
                         for i in range(3))
        with tempfile.TemporaryDirectory() as d:
            rollups = roll_signal_reliability(outcomes, now=_NOW)
            self.assertEqual(len(record_learning_rollups(d, rollups)), 1)
            before = _read_bytes(LearningStore(d).path)
            self.assertEqual(record_learning_rollups(d, rollups), ())
            self.assertEqual(_read_bytes(LearningStore(d).path), before)


class SourceReliabilityLearningTests(unittest.TestCase):
    def _rumor_failures(self, n):
        return tuple(_signal_outcome_for_roll(
            i, "contradicted", discipline="narrative",
            subject_id="sig.rumor.{0}".format(i)) for i in range(n))

    def test_failing_rumor_tier_rolls_up_deteriorating(self):
        outcomes = self._rumor_failures(3)
        authority = {o.subject_id: "rumor" for o in outcomes}
        (record,) = roll_source_reliability(outcomes, authority, now=_NOW)
        self.assertEqual(record.source_kind, "rumor")
        self.assertEqual(record.adapter_id, "")
        self.assertEqual(record.reliability_label, "deteriorating")
        self.assertEqual(record.contradicted_count, 3)
        self.assertIn("rumor", record.basis)

    def test_grouped_by_authority_tier(self):
        outcomes = (self._rumor_failures(1)
                    + (_signal_outcome_for_roll(9, "followed_through",
                                                subject_id="sig.sec"),))
        authority = {"sig.rumor.0": "rumor", "sig.sec": "canonical"}
        records = roll_source_reliability(outcomes, authority, now=_NOW)
        self.assertEqual([r.source_kind for r in records],
                         ["canonical", "rumor"])
        for record in records:
            self.assertEqual(record.reliability_label, "insufficient_history")

    def test_adapter_id_scope_when_mapping_names_an_adapter(self):
        outcomes = (_signal_outcome_for_roll(1, "faded", subject_id="sig.x"),)
        (record,) = roll_source_reliability(
            outcomes, {"sig.x": "adapter.social_narrative"}, now=_NOW)
        self.assertEqual(record.source_kind, "")
        self.assertEqual(record.adapter_id, "adapter.social_narrative")

    def test_unmapped_signals_are_skipped_never_guessed(self):
        outcomes = (_signal_outcome_for_roll(1, "contradicted",
                                             subject_id="sig.unknown"),)
        self.assertEqual(roll_source_reliability(outcomes, {}, now=_NOW), ())

    def test_a_past_record_is_never_retroactively_upgraded(self):
        with tempfile.TemporaryDirectory() as d:
            failures = self._rumor_failures(3)
            authority = {o.subject_id: "rumor" for o in failures}
            record_learning_rollups(
                d, roll_source_reliability(failures, authority, now=_NOW))
            path = LearningStore(d).path
            deteriorated_bytes = _read_bytes(path)
            # New evidence arrives: rumor claims now follow through. The roll
            # APPENDS a new record; the past 'deteriorating' line is untouched.
            recoveries = tuple(_signal_outcome_for_roll(
                i, "followed_through", discipline="narrative",
                subject_id="sig.rumor.{0}".format(i)) for i in range(10, 16))
            all_authority = dict(authority)
            all_authority.update({o.subject_id: "rumor" for o in recoveries})
            record_learning_rollups(
                d, roll_source_reliability(failures + recoveries,
                                           all_authority, now=_LATER))
            data = _read_bytes(path)
            self.assertTrue(data.startswith(deteriorated_bytes),
                            "a past source-reliability line was rewritten")
            labels = [r.reliability_label for r in LearningStore(d).read_all()]
            self.assertEqual(labels, ["deteriorating", "improving"])


# =========================================================================== #
# 5. Reserved alert categories -- emitted only where an outcome implies them  #
# =========================================================================== #
class OutcomeAlertTests(unittest.TestCase):
    def _outcomes_for(self, first_state, second_state):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, pulses=(_pulse(state=first_state),))
            _seed_run(d, "run-2", _T2, pulses=(_pulse(state=second_state),))
            outcomes = OutcomeTracker(d).track(now=_NOW)
            alerts = emit_outcome_alerts(d, outcomes, now=_NOW)
            stored = AlertStore(d).read_all()
            return outcomes, alerts, stored

    def test_contradicted_theme_claim_emits_thesis_deteriorated(self):
        outcomes, alerts, stored = self._outcomes_for("Igniting", "Breaking down")
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.category, "thesis_deteriorated")
        self.assertEqual(alert.severity, "warning")
        self.assertEqual(alert.run_id, "run-2")
        self.assertIn("'run-1'", alert.human_readable_reason)
        self.assertIn("'run-2'", alert.human_readable_reason)
        self.assertIn("outcome record", alert.human_readable_reason)
        contradicted = [o for o in outcomes if o.outcome_label == "contradicted"]
        self.assertIn(contradicted[0].outcome_id, alert.evidence_refs)
        self.assertEqual(len(stored), 1)

    def test_followed_through_risk_state_emits_major_risk_emerged(self):
        self.assertEqual(RISK_CLAIM_STATES,
                         frozenset({"Crowded", "Exhausting", "Breaking down"}))
        _, alerts, _ = self._outcomes_for("Crowded", "Crowded")
        self.assertEqual([a.category for a in alerts], ["major_risk_emerged"])
        self.assertEqual(alerts[0].severity, "critical")
        self.assertIn("Risk-state theme claim confirmed",
                      alerts[0].human_readable_reason)

    def test_benign_follow_through_emits_nothing(self):
        _, alerts, stored = self._outcomes_for("Warming", "Igniting")
        self.assertEqual(alerts, ())
        self.assertEqual(stored, ())

    def test_new_opportunity_hypothesis_stays_reserved(self):
        for pair in (("Warming", "Igniting"), ("Igniting", "Dormant"),
                     ("Crowded", "Crowded")):
            _, alerts, _ = self._outcomes_for(*pair)
            self.assertNotIn("new_opportunity_hypothesis",
                             [a.category for a in alerts])

    def test_emitting_twice_appends_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, pulses=(_pulse(state="Igniting"),))
            _seed_run(d, "run-2", _T2, pulses=(_pulse(state="Dormant"),))
            outcomes = OutcomeTracker(d).track(now=_NOW)
            emit_outcome_alerts(d, outcomes, now=_NOW)
            before = _read_bytes(AlertStore(d).path)
            self.assertEqual(emit_outcome_alerts(d, outcomes, now=_LATER), ())
            self.assertEqual(_read_bytes(AlertStore(d).path), before)

    def test_coexists_with_the_015c_diff_engine(self):
        # Learning alerts run AFTER generate_alerts_for_run; both land in the
        # same append-only inbox without disturbing each other.
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, pulses=(_pulse(state="Igniting"),))
            _seed_run(d, "run-2", _T2, pulses=(_pulse(state="Breaking down"),))
            diff_result = generate_alerts_for_run(d, "run-2", now=_NOW)
            self.assertEqual([a.category for a in diff_result.alerts],
                             ["theme_pulse_changed"])
            outcomes = OutcomeTracker(d).track(now=_NOW)
            emitted = emit_outcome_alerts(d, outcomes, now=_NOW)
            self.assertEqual([a.category for a in emitted],
                             ["thesis_deteriorated"])
            categories = sorted(a.category for a in AlertStore(d).read_all())
            self.assertEqual(categories,
                             ["theme_pulse_changed", "thesis_deteriorated"])


# =========================================================================== #
# 6. Module guards -- AST bans, offline, additive exports                     #
# =========================================================================== #
class LearningModuleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_LEARNING_PY, encoding="utf-8") as fh:
            cls.source = fh.read()
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
                        "banned import {0!r} in learning.py".format(name))

    def test_no_loop_async_or_timed_wait_construct(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in learning.py")
            self.assertNotIsInstance(node, ast.AsyncFunctionDef)
            self.assertNotIsInstance(node, ast.Await)
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotIn(called, _BANNED_CALL_NAMES,
                                 "daemon-style call {0!r} in learning.py".format(called))

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
                              "execution-adjacent word {0!r} in learning.py".format(word))

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
        for name in ("OutcomeRecord", "SignalReliabilityRecord",
                     "ThemePulseAccuracyRecord", "SourceReliabilityRecord",
                     "OutcomeStore", "LearningStore", "OutcomeTracker",
                     "OUTCOME_LABELS", "RELIABILITY_LABELS", "SUBJECT_KINDS",
                     "LEARNING_THRESHOLDS", "track_outcomes", "record_outcomes",
                     "roll_signal_reliability", "roll_theme_pulse_accuracy",
                     "roll_source_reliability", "record_learning_rollups",
                     "emit_outcome_alerts", "persisted_run_ids"):
            self.assertTrue(hasattr(rm, name), "reality_mesh.{0} missing".format(name))

    def test_the_seven_013b_stores_are_untouched(self):
        # the learning stores are ADDITIVE: the 013B spine still counts seven.
        self.assertEqual(len(S.STORE_CLASSES), 7)
        for store_cls in LEARNING_STORE_CLASSES:
            self.assertNotIn(store_cls, S.STORE_CLASSES)


# =========================================================================== #
# 7. Untouched paths -- demo default + default pulse stay byte-identical      #
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
