"""IMPLEMENTATION-017B -- Learning & Feedback reviews: postmortems, red team,
timing, expert accounts, archetypes, experience layer.

This suite proves the review discipline over the 017A outcome core:

* a review reviews a RECORDED thesis run: the operator journals the thesis
  (labels + text only) into the append-only thesis journal, and every review
  cites that entry plus the persisted OutcomeRecord ids it compared against;
* postmortem labels come from outcome VOLUMES with thresholds-as-data --
  a contradicted claim weakens, repeated contradiction (or a triggered
  journaled invalidation condition) breaks, and too little history honestly
  reads ``insufficient_history``;
* a red-team point is ``confirmed`` ONLY where a later persisted ADVERSE
  outcome explicitly matches its warning by subject / theme (cited by id);
  an unmatched point stays ``unrealized`` -- never guessed;
* the timing review judges the journaled claim against the persisted
  sequence only (early / on_time / late) and reads ``unresolved`` wherever
  the history cannot answer;
* expert-account reliability is VOLUME counts + the 017A closed label per
  social account (via the subject signal's cited source events); under 3
  resolved outcomes it reads ``insufficient_history``;
* archetypes roll from REPEATED persisted state-arc transitions; the
  experience entry cites record ids only (no synthesis beyond citation);
* every record is labels / citations / volume counts -- no numeric metric
  field (introspected), no trade token, frozen;
* reviewing is append-only + idempotent: a re-review leaves the learning
  store byte-identical and never modifies any existing store byte;
* reviews.py carries no banned import / loop / wall-clock / metric-named
  function; the demo default + default pulse remain byte-identical.

Entirely OFFLINE and deterministic: injected ISO ``now`` strings everywhere;
a socket kill-switch guards the whole module.
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
from reality_mesh.learning import (
    LEARNING_THRESHOLDS,
    LearningStore,
    OutcomeStore,
    OutcomeTracker,
    SignalReliabilityRecord,
    record_learning_rollups,
)
from reality_mesh.models import RealityEvent, RealitySignal, ThemePulse
from reality_mesh.reviews import (
    JOURNAL_VERDICTS,
    POSTMORTEM_LABELS,
    REVIEW_RECORDS,
    REVIEW_THRESHOLDS,
    TIMING_CLAIMS,
    TIMING_LABELS,
    ArchetypeUpdate,
    ExperienceLayerUpdate,
    ExpertAccountReliabilityRecord,
    RedTeamReview,
    ThesisJournalEntry,
    ThesisJournalStore,
    ThesisPostmortem,
    TimingReview,
    append_experience_update,
    journal_thesis,
    review_red_team,
    review_thesis,
    review_timing,
    roll_archetypes,
    roll_expert_reliability,
)
from reality_mesh.runtime import PulseRun
from reality_mesh.validation import assert_no_trade_fields

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_REVIEWS_PY = os.path.join(_PKG_DIR, "reviews.py")

_T1 = "2026-06-29T11:00:00Z"
_T2 = "2026-06-29T12:00:00Z"
_T3 = "2026-06-29T13:00:00Z"
_T4 = "2026-06-29T14:00:00Z"
_NOW = "2026-06-29T17:00:00Z"
_LATER = "2026-07-04T09:00:00Z"
_RUN_TS = {"run-1": _T1, "run-2": _T2, "run-3": _T3, "run-4": _T4}

# The 015/017 guard vocabulary applied to reviews.py (reviews observe, never act).
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
    raise AssertionError("network access attempted during the offline reviews suite")


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


def _seed_run(store_dir, run_id, ts, *, pulses=(), signals=(), events=()):
    """Persist one fabricated run (spine + records) into the 013B stores."""
    S.RunStore(store_dir).append(
        PulseRun(run_id=run_id, started_at=ts, completed_at=ts, mode="pulse"),
        timestamp=ts)
    for event in events:
        S.EventStore(store_dir).append(event, run_id=run_id, timestamp=ts)
    for pulse in pulses:
        S.ThemePulseStore(store_dir).append(pulse, run_id=run_id, timestamp=ts)
    for signal in signals:
        S.SignalStore(store_dir).append(signal, run_id=run_id, timestamp=ts)


def _seed_theme_arc(store_dir, states, *, theme="physical-ai", signals_by_run=()):
    """Seed one run per state (plus optional per-run signal tuples)."""
    for index, state in enumerate(states):
        run_id = "run-{0}".format(index + 1)
        signals = signals_by_run[index] if index < len(signals_by_run) else ()
        pulses = ()
        if state is not None:
            pulses = (ThemePulse(theme_pulse_id="pulse.{0}".format(theme),
                                 theme_id=theme, theme_name=theme, state=state),)
        _seed_run(store_dir, run_id, _RUN_TS[run_id], pulses=pulses,
                  signals=signals)


def _signal(sid, direction, discipline="technical_regime", companies=("IREN",),
            source_events=()):
    return RealitySignal(signal_id=sid, discipline=discipline,
                         direction_label=direction,
                         affected_companies=tuple(companies),
                         source_events=tuple(source_events))


def _social_event(event_id, handle, *, source_type="x", ts=_T1):
    return RealityEvent(event_id=event_id, timestamp=ts, source_id=handle,
                        source_type=source_type, discipline="narrative")


def _journal(store_dir, **kw):
    base = dict(ticker="IREN", verdict_label="thesis_worthy",
                timing_claimed="timing_confirmed", recorded_at=_T1,
                run_context="candidate cockpit render; theme physical-ai for IREN")
    base.update(kw)
    return journal_thesis(store_dir, **base)


# =========================================================================== #
# 1. The thesis journal -- a thesis becomes reviewable by being RECORDED      #
# =========================================================================== #
class ThesisJournalTests(unittest.TestCase):
    def test_closed_verdict_and_timing_vocabularies(self):
        self.assertEqual(JOURNAL_VERDICTS, frozenset(
            {"not_investable", "watch", "thesis_worthy",
             "thesis_worthy_timing_confirmed"}))
        self.assertEqual(TIMING_CLAIMS,
                         frozenset({"timing_confirmed", "timing_not_confirmed"}))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                _journal(d, verdict_label="strong_conviction")
            with self.assertRaises(ValueError):
                _journal(d, verdict_label="")
            with self.assertRaises(ValueError):
                _journal(d, timing_claimed="soon")

    def test_journal_entry_requires_its_citations(self):
        with self.assertRaises(ValueError):
            ThesisJournalEntry(journal_id="", ticker="IREN",
                               verdict_label="watch",
                               timing_claimed="timing_confirmed",
                               recorded_at=_T1)
        with self.assertRaises(ValueError):
            ThesisJournalEntry(journal_id="x", ticker="",
                               verdict_label="watch",
                               timing_claimed="timing_confirmed",
                               recorded_at=_T1)

    def test_journaling_is_append_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            entry = _journal(d)
            path = ThesisJournalStore(d).path
            before = _read_bytes(path)
            again = _journal(d)                 # same ticker + recorded_at
            self.assertEqual(again.journal_id, entry.journal_id)
            self.assertEqual(_read_bytes(path), before)
            later = _journal(d, recorded_at=_T2)    # a NEW thesis run
            self.assertNotEqual(later.journal_id, entry.journal_id)
            data = _read_bytes(path)
            self.assertTrue(data.startswith(before),
                            "an existing journal line was rewritten")

    def test_journal_store_round_trips_and_has_no_mutation_affordance(self):
        with tempfile.TemporaryDirectory() as d:
            entry = _journal(d, invalidation_conditions=("cond A",),
                             monitoring_signals=("watch B",),
                             red_team_summary="risk C")
            (back,) = ThesisJournalStore(d).read_all()
            self.assertEqual(back, entry)
        names = {n for n in dir(ThesisJournalStore) if not n.startswith("_")}
        for banned in ("update", "delete", "remove", "rewrite", "pop"):
            self.assertNotIn(banned, names)

    def test_journal_is_labels_and_text_only(self):
        with self.assertRaises(ValueError):
            ThesisJournalEntry(journal_id="x", ticker="IREN",
                               verdict_label="watch",
                               timing_claimed="timing_confirmed",
                               invalidation_conditions=(0.5,),
                               recorded_at=_T1)

    def test_frozen(self):
        with tempfile.TemporaryDirectory() as d:
            entry = _journal(d)
            with self.assertRaises(FrozenInstanceError):
                entry.verdict_label = "watch"  # type: ignore[misc]

    def test_reviewing_an_unjournaled_thesis_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                review_thesis(d, "thesis.ghost", now=_NOW)


# =========================================================================== #
# 2. ThesisPostmortem -- labels from volumes, thresholds as data              #
# =========================================================================== #
class ThesisPostmortemTests(unittest.TestCase):
    def test_thresholds_live_as_data(self):
        self.assertEqual(REVIEW_THRESHOLDS["min_resolved_outcomes"],
                         LEARNING_THRESHOLDS["min_resolved_outcomes"])
        self.assertEqual(REVIEW_THRESHOLDS["weakened_min_contradicted"], 1)
        self.assertEqual(REVIEW_THRESHOLDS["broken_min_contradicted"], 2)
        self.assertEqual(POSTMORTEM_LABELS, frozenset(
            {"thesis_held", "thesis_weakened", "thesis_broken",
             "insufficient_history"}))

    def _postmortem_for(self, states, *, signals=True, **journal_kw):
        with tempfile.TemporaryDirectory() as d:
            by_run = tuple(
                (_signal("sig.{0}".format(i + 1), "rising"),) if signals else ()
                for i in range(len(states)))
            _seed_theme_arc(d, states, signals_by_run=by_run)
            OutcomeTracker(d).track(now=_NOW)
            entry = _journal(d, **journal_kw)
            return review_thesis(d, entry.journal_id, now=_NOW), entry

    def test_one_contradicted_theme_claim_reads_thesis_weakened(self):
        record, entry = self._postmortem_for(("Warming", "Igniting", "Dormant"))
        self.assertEqual(record.postmortem_label, "thesis_weakened")
        self.assertEqual(record.thesis_ref, entry.journal_id)
        self.assertEqual(len(record.what_contradicted), 1)
        self.assertIn("outcome '", record.what_contradicted[0])
        self.assertIn("'run-2'", record.what_contradicted[0])

    def test_repeated_contradiction_reads_thesis_broken(self):
        record, _ = self._postmortem_for(
            ("Warming", "Igniting", "Breaking down", "Dormant"))
        self.assertEqual(record.postmortem_label, "thesis_broken")
        self.assertEqual(len(record.what_contradicted),
                         REVIEW_THRESHOLDS["broken_min_contradicted"])

    def test_clean_follow_through_reads_thesis_held(self):
        record, _ = self._postmortem_for(("Warming", "Igniting", "Broadening"))
        self.assertEqual(record.postmortem_label, "thesis_held")
        self.assertEqual(record.what_contradicted, ())
        self.assertEqual(record.invalidation_conditions_triggered, ())

    def test_too_little_history_reads_insufficient_history(self):
        record, _ = self._postmortem_for(("Warming", "Igniting"))
        self.assertEqual(record.postmortem_label, "insufficient_history")
        self.assertIn("no label pretends confidence", record.basis)

    def test_triggered_invalidation_condition_breaks_the_thesis(self):
        record, _ = self._postmortem_for(
            ("Warming", "Igniting", "Dormant"),
            invalidation_conditions=(
                "Invalid if the physical-ai pulse reads state 'Dormant'",))
        self.assertEqual(record.postmortem_label, "thesis_broken")
        (triggered,) = record.invalidation_conditions_triggered
        self.assertIn("triggered by outcome '", triggered)
        self.assertIn("'Dormant'", triggered)

    def test_untriggered_condition_stays_untriggered_never_guessed(self):
        record, _ = self._postmortem_for(
            ("Warming", "Igniting", "Dormant"),
            invalidation_conditions=(
                "Invalid if the pulse reads state 'Breaking down'",))
        self.assertEqual(record.invalidation_conditions_triggered, ())
        self.assertEqual(record.postmortem_label, "thesis_weakened")

    def test_every_what_entry_cites_a_persisted_outcome_id(self):
        record, _ = self._postmortem_for(
            ("Warming", "Igniting", "Breaking down", "Dormant"))
        for entry_line in (record.what_followed_through
                           + record.what_contradicted + record.what_faded):
            self.assertRegex(entry_line, r"outcome '[^']+':")

    def test_unrelated_theme_outcomes_stay_out_of_scope(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, pulses=(
                ThemePulse(theme_pulse_id="pulse.physical-ai",
                           theme_id="physical-ai", theme_name="physical-ai",
                           state="Warming"),
                ThemePulse(theme_pulse_id="pulse.robotics", theme_id="robotics",
                           theme_name="robotics", state="Igniting")))
            _seed_run(d, "run-2", _T2, pulses=(
                ThemePulse(theme_pulse_id="pulse.physical-ai",
                           theme_id="physical-ai", theme_name="physical-ai",
                           state="Igniting"),
                ThemePulse(theme_pulse_id="pulse.robotics", theme_id="robotics",
                           theme_name="robotics", state="Dormant")))
            OutcomeTracker(d).track(now=_NOW)
            entry = _journal(d)     # journal names physical-ai only
            record = review_thesis(d, entry.journal_id, now=_NOW)
            self.assertEqual(record.what_contradicted, (),
                             "a robotics outcome leaked into an IREN/physical-ai thesis")

    def test_basis_cites_thesis_and_window_runs(self):
        record, entry = self._postmortem_for(("Warming", "Igniting", "Dormant"))
        self.assertIn(entry.journal_id, record.basis)
        self.assertIn("'run-1'", record.basis)
        self.assertIn("no ratio is stored", record.basis)


# =========================================================================== #
# 3. RedTeamReview -- confirmed only by an explicit later adverse match       #
# =========================================================================== #
class RedTeamReviewTests(unittest.TestCase):
    def _review_for(self, states, summary, *, signals_by_run=(), **kw):
        with tempfile.TemporaryDirectory() as d:
            _seed_theme_arc(d, states, signals_by_run=signals_by_run)
            OutcomeTracker(d).track(now=_NOW)
            entry = _journal(d, red_team_summary=summary, **kw)
            return review_red_team(d, entry.journal_id, now=_NOW)

    def test_theme_matched_point_is_confirmed_and_cites_the_outcome(self):
        by_run = tuple((_signal("sig.{0}".format(i + 1), "rising"),)
                       for i in range(3))
        record = self._review_for(
            ("Warming", "Igniting", "Dormant"),
            "Crowding risk in physical-ai; A supplier issue may slow NVDA",
            signals_by_run=by_run)
        (confirmed,) = record.red_team_points_confirmed
        self.assertIn("Crowding risk in physical-ai", confirmed)
        self.assertRegex(confirmed, r"confirmed by outcome '[^']+'")
        (unrealized,) = record.red_team_points_unrealized
        self.assertIn("NVDA", unrealized)
        self.assertIn("never guessed", unrealized)
        self.assertEqual(record.review_label, "thesis_weakened")

    def test_ticker_matched_point_is_confirmed_via_adverse_signal_outcome(self):
        by_run = ((_signal("sig.1", "rising"),), (_signal("sig.2", "rising"),),
                  (_signal("sig.3", "falling"),), (_signal("sig.4", "falling"),))
        record = self._review_for(
            ("Warming", "Igniting", "Broadening", "Crowded"),
            "IREN capacity shortfall is a real risk",
            signals_by_run=by_run)
        (confirmed,) = record.red_team_points_confirmed
        self.assertIn("IREN", confirmed)
        self.assertRegex(confirmed, r"confirmed by outcome '[^']+'")

    def test_with_no_adverse_outcome_every_point_stays_unrealized(self):
        by_run = tuple((_signal("sig.{0}".format(i + 1), "rising"),)
                       for i in range(3))
        record = self._review_for(
            ("Warming", "Igniting", "Broadening"),
            "Crowding risk in physical-ai; IREN dilution risk",
            signals_by_run=by_run)
        self.assertEqual(record.red_team_points_confirmed, ())
        self.assertEqual(len(record.red_team_points_unrealized), 2)
        self.assertEqual(record.review_label, "thesis_held")

    def test_under_the_resolved_floor_reads_insufficient_history(self):
        record = self._review_for(("Warming", "Igniting"),
                                  "Crowding risk in physical-ai")
        self.assertEqual(record.review_label, "insufficient_history")
        self.assertIn("no label pretends confidence", record.basis)

    def test_two_confirmed_points_read_thesis_broken(self):
        by_run = ((_signal("sig.1", "rising"),), (_signal("sig.2", "falling"),),
                  (_signal("sig.3", "falling"),), ())
        record = self._review_for(
            ("Igniting", "Breaking down", "Breaking down", "Dormant"),
            "physical-ai exhaustion risk; IREN could reverse hard",
            signals_by_run=by_run)
        self.assertEqual(len(record.red_team_points_confirmed),
                         REVIEW_THRESHOLDS["broken_min_confirmed_points"])
        self.assertEqual(record.review_label, "thesis_broken")


# =========================================================================== #
# 4. TimingReview -- honest early / on_time / late / unresolved               #
# =========================================================================== #
class TimingReviewTests(unittest.TestCase):
    def _timing_for(self, states, claim, *, signals_by_run=()):
        with tempfile.TemporaryDirectory() as d:
            _seed_theme_arc(d, states, signals_by_run=signals_by_run)
            OutcomeTracker(d).track(now=_NOW)
            entry = _journal(d, timing_claimed=claim)
            return review_timing(d, entry.journal_id, now=_NOW)

    def test_confirmed_claim_with_immediate_follow_through_is_on_time(self):
        by_run = tuple((_signal("sig.{0}".format(i + 1), "rising"),)
                       for i in range(3))
        record = self._timing_for(("Warming", "Igniting", "Broadening"),
                                  "timing_confirmed", signals_by_run=by_run)
        self.assertEqual(record.timing_label, "on_time")
        self.assertGreaterEqual(len(record.what_happened_next), 3)
        for line in record.what_happened_next:
            self.assertRegex(line, r"outcome '[^']+'")

    def test_confirmed_claim_with_adversity_first_is_early(self):
        record = self._timing_for(
            ("Igniting", "Dormant", "Warming", "Igniting"), "timing_confirmed")
        self.assertEqual(record.timing_label, "early")
        self.assertIn("before follow-through arrived", record.basis)

    def test_unconfirmed_claim_with_immediate_follow_through_is_late(self):
        by_run = tuple((_signal("sig.{0}".format(i + 1), "rising"),)
                       for i in range(3))
        record = self._timing_for(("Warming", "Igniting", "Broadening"),
                                  "timing_not_confirmed", signals_by_run=by_run)
        self.assertEqual(record.timing_label, "late")

    def test_unconfirmed_claim_with_later_follow_through_is_on_time(self):
        record = self._timing_for(
            ("Igniting", "Dormant", "Warming", "Igniting"),
            "timing_not_confirmed")
        self.assertEqual(record.timing_label, "on_time")

    def test_no_resolved_history_is_unresolved_never_guessed(self):
        record = self._timing_for(("Warming",), "timing_confirmed")
        self.assertEqual(record.timing_label, "unresolved")
        self.assertEqual(record.what_happened_next, ())
        self.assertIn("no answer is guessed", record.basis)

    def test_under_the_resolved_floor_is_unresolved(self):
        record = self._timing_for(("Warming", "Igniting"), "timing_confirmed")
        self.assertEqual(record.timing_label, "unresolved")

    def test_no_follow_through_at_all_is_unresolved(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, signals=(_signal("sig.1", "rising"),))
            _seed_run(d, "run-2", _T2, signals=(_signal("sig.2", "falling"),))
            _seed_run(d, "run-3", _T3, signals=(_signal("sig.3", "rising"),))
            _seed_run(d, "run-4", _T4, signals=())
            OutcomeTracker(d).track(now=_NOW)
            entry = _journal(d, run_context="IREN only; no theme journaled")
            record = review_timing(d, entry.journal_id, now=_NOW)
            self.assertEqual(record.timing_label, "unresolved")
            self.assertIn("did not develop", record.basis)

    def test_closed_timing_vocabulary(self):
        self.assertEqual(TIMING_LABELS,
                         frozenset({"early", "on_time", "late", "unresolved"}))
        with self.assertRaises(ValueError):
            TimingReview(learning_id="x", thesis_ref="t", window=("a", "b"),
                         timing_claimed="timing_confirmed",
                         timing_label="perfect", basis="b", created_at=_NOW)


# =========================================================================== #
# 5. Expert-account reliability -- volumes + label per social account         #
# =========================================================================== #
class ExpertReliabilityTests(unittest.TestCase):
    def _seed_expert_store(self, d):
        directions = ("rising", "rising", "falling", "falling")
        for index in range(4):
            run_id = "run-{0}".format(index + 1)
            events = [_social_event("ev.chip.{0}".format(index + 1),
                                    "@chipwhisperer", ts=_RUN_TS[run_id])]
            signals = [_signal("sig.chip.{0}".format(index + 1),
                               directions[index], discipline="narrative",
                               companies=("IREN",),
                               source_events=("ev.chip.{0}".format(index + 1),))]
            if index >= 2:      # @quietone appears only in runs 3-4
                events.append(_social_event("ev.quiet.{0}".format(index + 1),
                                            "@quietone", source_type="reddit",
                                            ts=_RUN_TS[run_id]))
                signals.append(_signal("sig.quiet.{0}".format(index + 1),
                                       "rising", discipline="narrative",
                                       companies=("NVDA",),
                                       source_events=("ev.quiet.{0}".format(index + 1),)))
            if index == 0:      # a canonical (non-social) source is never an "account"
                events.append(RealityEvent(
                    event_id="ev.sec.1", timestamp=_T1, source_id="sec-edgar",
                    source_type="regulatory_filing", source_authority="canonical",
                    claim_status="verified_fact", discipline="news_filings"))
                signals.append(_signal("sig.sec.1", "rising",
                                       discipline="news_filings",
                                       companies=("MSFT",),
                                       source_events=("ev.sec.1",)))
            _seed_run(d, run_id, _RUN_TS[run_id], signals=tuple(signals),
                      events=tuple(events))
        OutcomeTracker(d).track(now=_NOW)

    def test_volume_counts_and_label_per_account(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_expert_store(d)
            records = roll_expert_reliability(d, now=_NOW)
            by_handle = {r.account_handle: r for r in records}
            self.assertEqual(sorted(by_handle), ["@chipwhisperer", "@quietone"])
            chip = by_handle["@chipwhisperer"]
            # rising->rising followed; rising->falling contradicted;
            # falling->falling followed; last run unresolved.
            self.assertEqual(chip.followed_through_count, 2)
            self.assertEqual(chip.contradicted_count, 1)
            self.assertEqual(chip.faded_count, 0)
            self.assertEqual(chip.unresolved_count, 1)
            self.assertEqual(chip.reliability_label, "improving")
            self.assertEqual(chip.account_kind, "x")
            self.assertIn("@chipwhisperer", chip.basis)
            self.assertIn("no ratio is stored", chip.basis)

    def test_under_three_resolved_reads_insufficient_history(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_expert_store(d)
            records = roll_expert_reliability(d, now=_NOW)
            quiet = {r.account_handle: r for r in records}["@quietone"]
            self.assertEqual(quiet.followed_through_count, 1)
            self.assertEqual(quiet.unresolved_count, 1)
            self.assertEqual(quiet.reliability_label, "insufficient_history")
            self.assertIn("no label pretends confidence", quiet.basis)

    def test_non_social_sources_are_never_rolled_as_accounts(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_expert_store(d)
            handles = {r.account_handle
                       for r in roll_expert_reliability(d, now=_NOW)}
            self.assertNotIn("sec-edgar", handles)

    def test_unattributed_signals_are_skipped_never_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, signals=(_signal("sig.1", "rising"),))
            _seed_run(d, "run-2", _T2, signals=(_signal("sig.2", "rising"),))
            OutcomeTracker(d).track(now=_NOW)
            self.assertEqual(roll_expert_reliability(d, now=_NOW), ())

    def test_deterministic_and_windowed(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_expert_store(d)
            first = roll_expert_reliability(d, now=_NOW)
            second = roll_expert_reliability(d, now=_NOW)
            self.assertEqual(repr(first), repr(second))
            self.assertEqual(first[0].window, ("run-1", "run-4"))

    def test_account_record_requires_a_handle(self):
        with self.assertRaises(ValueError):
            ExpertAccountReliabilityRecord(
                learning_id="x", account_handle="", window=("a", "b"),
                reliability_label="stable", basis="b", created_at=_NOW)


# =========================================================================== #
# 6. Archetypes + the experience layer                                        #
# =========================================================================== #
class ArchetypeTests(unittest.TestCase):
    def _seed_arcs(self, d):
        themes = ("physical-ai", "robotics", "space-compute", "quantum")
        first = ("Igniting", "Igniting", "Igniting", "Igniting")
        second = ("Broadening", "Broadening", "Broadening", "Dormant")
        for run_id, states, ts in (("run-1", first, _T1), ("run-2", second, _T2)):
            pulses = tuple(
                ThemePulse(theme_pulse_id="pulse.{0}".format(theme),
                           theme_id=theme, theme_name=theme, state=state)
                for theme, state in zip(themes, states))
            _seed_run(d, run_id, ts, pulses=pulses)
        OutcomeTracker(d).track(now=_NOW)

    def test_repeated_state_arc_becomes_a_learned_archetype(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_arcs(d)
            records = roll_archetypes(d, now=_NOW)
            by_id = {r.archetype_id: r for r in records}
            self.assertEqual(sorted(by_id), ["theme_igniting_to_broadening",
                                             "theme_igniting_to_dormant"])
            learned = by_id["theme_igniting_to_broadening"]
            self.assertEqual(learned.occurrences_count, 3)
            self.assertEqual(learned.followed_through_count, 3)
            self.assertEqual(learned.reversed_count, 0)
            self.assertEqual(learned.archetype_label, "improving")
            self.assertIn("recurred 3 time(s)", learned.basis)

    def test_a_single_occurrence_is_not_asserted_as_a_pattern(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed_arcs(d)
            by_id = {r.archetype_id: r for r in roll_archetypes(d, now=_NOW)}
            lone = by_id["theme_igniting_to_dormant"]
            self.assertEqual(lone.occurrences_count, 1)
            self.assertEqual(lone.reversed_count, 1)
            self.assertEqual(lone.archetype_label, "insufficient_history")
            self.assertIn("no pattern is asserted", lone.basis)

    def test_unresolved_outcomes_never_feed_an_archetype(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "run-1", _T1, pulses=(
                ThemePulse(theme_pulse_id="pulse.t", theme_id="t",
                           theme_name="t", state="Warming"),))
            OutcomeTracker(d).track(now=_NOW)
            self.assertEqual(roll_archetypes(d, now=_NOW), ())


class ExperienceLayerTests(unittest.TestCase):
    def _reviewed_store(self, d):
        _seed_theme_arc(d, ("Warming", "Igniting", "Dormant"),
                        signals_by_run=tuple(
                            (_signal("sig.{0}".format(i + 1), "rising"),)
                            for i in range(3)))
        OutcomeTracker(d).track(now=_NOW)
        entry = _journal(d, red_team_summary="Crowding risk in physical-ai")
        review_thesis(d, entry.journal_id, now=_NOW)
        review_red_team(d, entry.journal_id, now=_NOW)
        review_timing(d, entry.journal_id, now=_NOW)
        roll_archetypes(d, now=_NOW)

    def test_experience_update_cites_record_ids_only(self):
        with tempfile.TemporaryDirectory() as d:
            self._reviewed_store(d)
            record = append_experience_update(d, now=_NOW)
            persisted_ids = {str(rec.get("record_id", ""))
                             for rec in LearningStore(d).read_records()}
            self.assertTrue(record.cited_record_ids)
            for cited in record.cited_record_ids:
                self.assertIn(cited, persisted_ids)
                self.assertIn("'{0}'".format(cited), record.basis)
            self.assertIn("Citation only", record.basis)
            self.assertEqual(record.entry_date, _NOW)

    def test_nothing_to_cite_appends_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(append_experience_update(d, now=_NOW))
            self.assertFalse(os.path.isfile(LearningStore(d).path))

    def test_experience_update_is_idempotent_and_never_cites_itself(self):
        with tempfile.TemporaryDirectory() as d:
            self._reviewed_store(d)
            first = append_experience_update(d, now=_NOW)
            before = _read_bytes(LearningStore(d).path)
            second = append_experience_update(d, now=_LATER)
            self.assertEqual(second.learning_id, first.learning_id)
            self.assertEqual(second.cited_record_ids, first.cited_record_ids)
            self.assertEqual(_read_bytes(LearningStore(d).path), before)

    def test_an_empty_experience_entry_is_refused(self):
        with self.assertRaises(ValueError):
            ExperienceLayerUpdate(learning_id="x", entry_date=_NOW,
                                  cited_record_ids=(), basis="b",
                                  created_at=_NOW)


# =========================================================================== #
# 7. Append-only + idempotence + record hygiene across the whole layer        #
# =========================================================================== #
class AppendOnlyReviewTests(unittest.TestCase):
    def _full_review(self, d, now):
        entry = _journal(d, red_team_summary="Crowding risk in physical-ai")
        review_thesis(d, entry.journal_id, now=now)
        review_red_team(d, entry.journal_id, now=now)
        review_timing(d, entry.journal_id, now=now)
        roll_expert_reliability(d, now=now)
        roll_archetypes(d, now=now)
        append_experience_update(d, now=now)

    def test_re_review_is_idempotent_byte_identical_store(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_theme_arc(d, ("Warming", "Igniting", "Dormant"),
                            signals_by_run=tuple(
                                (_signal("sig.{0}".format(i + 1), "rising"),)
                                for i in range(3)))
            OutcomeTracker(d).track(now=_NOW)
            self._full_review(d, _NOW)
            path = LearningStore(d).path
            before = _read_bytes(path)
            self._full_review(d, _LATER)    # a later re-review appends NOTHING
            self.assertEqual(_read_bytes(path), before)

    def test_reviewing_never_modifies_any_existing_store_byte(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_theme_arc(d, ("Warming", "Igniting", "Dormant"),
                            signals_by_run=tuple(
                                (_signal("sig.{0}".format(i + 1), "rising"),)
                                for i in range(3)))
            OutcomeTracker(d).track(now=_NOW)
            _journal(d, red_team_summary="Crowding risk in physical-ai")
            before = _snapshot_dir(d)
            self._full_review(d, _NOW)
            after = _snapshot_dir(d)
            for name, data in before.items():
                if name == LearningStore.filename:
                    self.assertTrue(after[name].startswith(data))
                else:
                    self.assertEqual(after[name], data,
                                     "review modified existing store {0}".format(name))

    def test_new_history_appends_new_records_old_lines_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_theme_arc(d, ("Warming", "Igniting", "Dormant"),
                            signals_by_run=tuple(
                                (_signal("sig.{0}".format(i + 1), "rising"),)
                                for i in range(3)))
            tracker = OutcomeTracker(d)
            tracker.track(now=_NOW)
            entry = _journal(d)
            review_thesis(d, entry.journal_id, now=_NOW)
            path = LearningStore(d).path
            before = _read_bytes(path)
            _seed_run(d, "run-4", _T4, pulses=(
                ThemePulse(theme_pulse_id="pulse.physical-ai",
                           theme_id="physical-ai", theme_name="physical-ai",
                           state="Breaking down"),))
            tracker.track(now=_LATER)
            review_thesis(d, entry.journal_id, now=_LATER)
            data = _read_bytes(path)
            self.assertTrue(data.startswith(before),
                            "an existing postmortem line was rewritten")
            labels = [r.postmortem_label for r in LearningStore(d).read_all()
                      if isinstance(r, ThesisPostmortem)]
            self.assertEqual(labels, ["thesis_weakened", "thesis_broken"])

    def test_review_records_coexist_with_017a_rollups_in_one_store(self):
        with tempfile.TemporaryDirectory() as d:
            rollup = SignalReliabilityRecord(
                learning_id="learn.signal-reliability.x", discipline="narrative",
                window=("run-1", "run-2"), followed_through_count=1,
                contradicted_count=2, faded_count=1, unresolved_count=0,
                reliability_label="deteriorating",
                basis="Across runs 'run-1'..'run-2': volumes only.",
                created_at=_NOW)
            record_learning_rollups(d, (rollup,))
            _seed_theme_arc(d, ("Warming", "Igniting", "Dormant"))
            OutcomeTracker(d).track(now=_NOW)
            entry = _journal(d)
            postmortem = review_thesis(d, entry.journal_id, now=_NOW)
            back = LearningStore(d).read_all()
            self.assertEqual(back, (rollup, postmortem))

    def test_no_numeric_metric_field_on_any_review_record(self):
        self.assertEqual(len(REVIEW_RECORDS), 7)
        for cls in REVIEW_RECORDS:
            assert_no_trade_fields(cls)
            for f in fields(cls):
                low = f.name.lower()
                for fragment in _METRIC_FIELD_FRAGMENTS:
                    self.assertNotIn(fragment, low,
                                     "metric-named field {0!r} on {1}".format(
                                         f.name, cls.__name__))

    def test_no_float_value_anywhere_on_instances(self):
        instances = (
            ThesisJournalEntry(journal_id="j", ticker="IREN",
                               verdict_label="watch",
                               timing_claimed="timing_confirmed",
                               recorded_at=_NOW),
            ThesisPostmortem(learning_id="l", thesis_ref="j", window=("a", "b"),
                             postmortem_label="thesis_held", basis="b",
                             created_at=_NOW),
            RedTeamReview(learning_id="l", thesis_ref="j", window=("a", "b"),
                          review_label="thesis_held", basis="b", created_at=_NOW),
            TimingReview(learning_id="l", thesis_ref="j", window=("a", "b"),
                         timing_claimed="timing_confirmed",
                         timing_label="unresolved", basis="b", created_at=_NOW),
            ExpertAccountReliabilityRecord(
                learning_id="l", account_handle="@x", window=("a", "b"),
                reliability_label="stable", basis="b", created_at=_NOW),
            ArchetypeUpdate(learning_id="l", archetype_id="theme_a_to_b",
                            window=("a", "b"), archetype_label="stable",
                            basis="b", created_at=_NOW),
            ExperienceLayerUpdate(learning_id="l", entry_date=_NOW,
                                  cited_record_ids=("r1",), basis="b",
                                  created_at=_NOW),
        )
        for record in instances:
            for f in fields(record):
                value = getattr(record, f.name)
                self.assertNotIsInstance(value, float,
                                         "{0}.{1}".format(type(record).__name__,
                                                          f.name))
                self.assertIn(type(value), (str, int, tuple),
                              "{0}.{1}".format(type(record).__name__, f.name))

    def test_counts_are_volumes_never_floats(self):
        with self.assertRaises(ValueError):
            ExpertAccountReliabilityRecord(
                learning_id="l", account_handle="@x", window=("a", "b"),
                followed_through_count=0.5, reliability_label="stable",
                basis="b", created_at=_NOW)
        with self.assertRaises(ValueError):
            ArchetypeUpdate(learning_id="l", archetype_id="a", window=("a", "b"),
                            occurrences_count=-1, archetype_label="stable",
                            basis="b", created_at=_NOW)

    def test_store_guard_refuses_a_metric_key_outright(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                ThesisJournalStore(d).append(
                    {"journal_id": "x", "accuracy_score": 0.9}, record_id="x")

    def test_frozen_review_records(self):
        record = ThesisPostmortem(learning_id="l", thesis_ref="j",
                                  window=("a", "b"),
                                  postmortem_label="thesis_held", basis="b",
                                  created_at=_NOW)
        with self.assertRaises(FrozenInstanceError):
            record.postmortem_label = "thesis_broken"  # type: ignore[misc]

    def test_reviews_require_an_injected_now(self):
        with tempfile.TemporaryDirectory() as d:
            _journal(d)
            for fn in (review_thesis, review_red_team, review_timing):
                with self.assertRaises(ValueError):
                    fn(d, "thesis.iren." + _T1.replace(":", "-"), now="")
            with self.assertRaises(ValueError):
                roll_expert_reliability(d, now="")
            with self.assertRaises(ValueError):
                roll_archetypes(d, now="")
            with self.assertRaises(ValueError):
                append_experience_update(d, now="")


# =========================================================================== #
# 8. Module guards -- AST bans, offline, additive exports                     #
# =========================================================================== #
class ReviewsModuleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_REVIEWS_PY, encoding="utf-8") as fh:
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
                        "banned import {0!r} in reviews.py".format(name))

    def test_no_loop_async_or_timed_wait_construct(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in reviews.py")
            self.assertNotIsInstance(node, ast.AsyncFunctionDef)
            self.assertNotIsInstance(node, ast.Await)
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotIn(called, _BANNED_CALL_NAMES,
                                 "daemon-style call {0!r} in reviews.py".format(called))

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
                              "execution-adjacent word {0!r} in reviews.py".format(word))

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
        for name in ("JOURNAL_VERDICTS", "POSTMORTEM_LABELS", "REVIEW_RECORDS",
                     "REVIEW_THRESHOLDS", "TIMING_CLAIMS", "TIMING_LABELS",
                     "ThesisJournalEntry", "ThesisJournalStore",
                     "ThesisPostmortem", "RedTeamReview", "TimingReview",
                     "ExpertAccountReliabilityRecord", "ArchetypeUpdate",
                     "ExperienceLayerUpdate", "journal_thesis", "review_thesis",
                     "review_red_team", "review_timing",
                     "roll_expert_reliability", "roll_archetypes",
                     "append_experience_update"):
            self.assertTrue(hasattr(rm, name), "reality_mesh.{0} missing".format(name))

    def test_the_seven_013b_stores_and_017a_shapes_are_untouched(self):
        self.assertEqual(len(S.STORE_CLASSES), 7)
        self.assertNotIn(ThesisJournalStore, S.STORE_CLASSES)
        # The 017A LearningStore still refuses a non-roll-up record.
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(TypeError):
                LearningStore(d).append(
                    OutcomeStore(d))    # any non-record object is refused


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
