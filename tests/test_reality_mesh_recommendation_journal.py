"""IMPLEMENTATION-022F -- the Paper Recommendation Journal.

Before production recommendations, EVERY recommendation is journaled append-only so the
system can measure whether its recommendations improve, count false positives / missed
opportunities, calibrate signal families, and feed the 017 Learning & Feedback layer. This
suite proves the journal discipline:

* journalling a recommendation writes ONE line; re-journalling the SAME recommendation
  appends nothing (idempotent, byte-identical);
* recording a later outcome appends a NEW line carrying the SAME journal_id -- the prior
  line stays BYTE-UNCHANGED, and the latest line for an id is the current knowledge
  (correction-not-mutation, latest-wins per id);
* the line records the recommendation STATE + label, the source_refs, and the DQ state;
* an outcome / correction NEVER rewrites an earlier line (asserted byte-for-byte);
* the journal does NOT imply execution: no directive-to-act field or token anywhere;
  entry_reference_price is an OPTIONAL labelled reference (absent -> None, a gap never
  fabricated), never a directive;
* there is NO score / rank / rating field; the status vocabulary is closed;
* the store has NO update / delete affordance; ids are deterministic;
* the journal's outcomes feed 017 as labels + VOLUME counts only (no numeric score);
* recommendation_journal.py carries no banned import / loop / wall-clock / metric-named
  function / execution token, the offline kill-switch is active, and the demo default +
  default pulse stay byte-identical.

Entirely OFFLINE and deterministic: injected ISO ``now`` strings everywhere; a socket
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
from dataclasses import FrozenInstanceError, fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh.recommendation import CapitalRecommendation
from reality_mesh.recommendation_journal import (
    JOURNAL_STATUSES,
    JOURNAL_STATUS_OUTCOME,
    RecommendationJournalEntry,
    RecommendationJournalStore,
    feed_learning,
    journal_id_for,
    journal_recommendation,
    journaled,
    open_recommendations,
    record_outcome,
)
from reality_mesh.learning import OUTCOME_LABELS
from reality_mesh.validation import assert_no_trade_fields

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_JOURNAL_PY = os.path.join(_PKG_DIR, "recommendation_journal.py")

_NOW = "2026-06-29T17:00:00Z"
_LATER = "2026-07-04T09:00:00Z"

# The guard vocabulary applied to recommendation_journal.py (the journal observes, never acts).
_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "asyncio", "threading", "multiprocessing",
                        "subprocess", "smtplib", "ftplib", "socketserver", "broker",
                        "signal", "time", "random", "select", "selectors", "queue")
_BANNED_CALL_NAMES = ("sleep", "run_forever", "serve_forever", "start_polling", "Thread",
                      "Timer", "Process", "fork", "spawn", "run_in_executor", "setdaemon")
# The execution / directive-to-act tokens that must NEVER appear as a source token.
_EXECUTION_TOKENS = ("order", "orders", "broker", "buy", "sell", "submit", "fill_order",
                     "ticket_id")
_WALL_CLOCK_TOKENS = ("time.time(", "datetime.now(", "datetime.utcnow(", "utcnow(",
                      "time.monotonic(", "perf_counter(")
_METRIC_FIELD_FRAGMENTS = ("score", "rank", "rating", "pct", "percent", "ratio",
                           "probability", "weight")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline journal suite")


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
    out = {}
    for name in sorted(os.listdir(store_dir)):
        path = os.path.join(store_dir, name)
        if os.path.isfile(path):
            out[name] = _read_bytes(path)
    return out


def _rec(**kw):
    base = dict(
        recommendation_id="rec:run-1:IREN", run_id="run-1", candidate_id="cand-1",
        ticker="IREN", recommendation_state="prepare_entry",
        recommendation_label="Prepare Entry",
        recommendation_time_horizon="12-24 months",
        key_thesis="Physical-AI compute buildout inflection",
        invalidation_conditions=("thesis-killer: gross-margin collapse",),
        exit_watch_conditions=("EMA stack breaks down",),
        source_provenance=("sec:10-K:IREN:2026", "fmp:quote:IREN"),
        data_quality_ref="healthy")
    base.update(kw)
    return CapitalRecommendation(**base)


# =========================================================================== #
# 1. The entry contract                                                       #
# =========================================================================== #
class JournalEntryTests(unittest.TestCase):
    def test_closed_status_vocabulary(self):
        self.assertEqual(
            JOURNAL_STATUSES,
            ("open", "invalidation_hit", "exit_watch_hit", "thesis_confirmed",
             "lapsed", "superseded"))

    def test_required_ids_enforced(self):
        for missing in ("journal_id", "recommendation_id", "run_id", "ticker"):
            kw = dict(journal_id="j", recommendation_id="r", run_id="run-1",
                      ticker="IREN")
            kw[missing] = ""
            with self.assertRaises(ValueError):
                RecommendationJournalEntry(**kw)

    def test_status_vocab_enforced(self):
        with self.assertRaises(ValueError):
            RecommendationJournalEntry(journal_id="j", recommendation_id="r",
                                       run_id="run-1", ticker="IREN",
                                       status="closed_won")

    def test_state_and_label_vocab_enforced(self):
        with self.assertRaises(ValueError):
            RecommendationJournalEntry(journal_id="j", recommendation_id="r",
                                       run_id="run-1", ticker="IREN",
                                       recommendation_state="going_up")
        with self.assertRaises(ValueError):
            RecommendationJournalEntry(journal_id="j", recommendation_id="r",
                                       run_id="run-1", ticker="IREN",
                                       recommendation_label="Strong Buy")

    def test_entry_reference_price_is_optional_label_or_none(self):
        # absent -> None (a gap, never fabricated)
        e = RecommendationJournalEntry(journal_id="j", recommendation_id="r",
                                       run_id="run-1", ticker="IREN")
        self.assertIsNone(e.entry_reference_price)
        # present -> a labelled string reference
        e2 = RecommendationJournalEntry(journal_id="j", recommendation_id="r",
                                        run_id="run-1", ticker="IREN",
                                        entry_reference_price="$12.50 (ref close 2026-06-29)")
        self.assertEqual(e2.entry_reference_price, "$12.50 (ref close 2026-06-29)")

    def test_entry_reference_price_rejects_a_bare_number(self):
        # a bare float could be mistaken for a computable instruction -> refused.
        with self.assertRaises(ValueError):
            RecommendationJournalEntry(journal_id="j", recommendation_id="r",
                                       run_id="run-1", ticker="IREN",
                                       entry_reference_price=12.50)

    def test_no_float_metric_anywhere(self):
        with self.assertRaises(ValueError):
            RecommendationJournalEntry(journal_id="j", recommendation_id="r",
                                       run_id="run-1", ticker="IREN",
                                       subsequent_outcomes=(0.42,))

    def test_frozen(self):
        e = RecommendationJournalEntry(journal_id="j", recommendation_id="r",
                                       run_id="run-1", ticker="IREN")
        with self.assertRaises(FrozenInstanceError):
            e.status = "lapsed"  # type: ignore[misc]

    def test_no_trade_or_score_field(self):
        assert_no_trade_fields(RecommendationJournalEntry)
        for f in fields(RecommendationJournalEntry):
            low = f.name.lower()
            for fragment in _METRIC_FIELD_FRAGMENTS:
                self.assertNotIn(fragment, low,
                                 "metric-named field {0!r}".format(f.name))
            for tok in _EXECUTION_TOKENS:
                self.assertNotIn(tok, low,
                                 "execution token {0!r} in field {1!r}".format(tok, f.name))


# =========================================================================== #
# 2. Journalling -- append-only, idempotent, records state/label/refs/DQ       #
# =========================================================================== #
class JournalRecommendationTests(unittest.TestCase):
    def test_journal_writes_one_line(self):
        with tempfile.TemporaryDirectory() as d:
            entry = journal_recommendation(d, _rec(), now=_NOW)
            self.assertEqual(entry.journal_id,
                             journal_id_for("run-1", "rec:run-1:IREN"))
            records = RecommendationJournalStore(d).read_records()
            self.assertEqual(len(records), 1)

    def test_records_state_and_label(self):
        with tempfile.TemporaryDirectory() as d:
            entry = journal_recommendation(d, _rec(), now=_NOW)
            self.assertEqual(entry.recommendation_state, "prepare_entry")
            self.assertEqual(entry.recommendation_label, "Prepare Entry")
            back = journaled(d)[0]
            self.assertEqual(back.recommendation_state, "prepare_entry")
            self.assertEqual(back.recommendation_label, "Prepare Entry")

    def test_records_source_refs(self):
        with tempfile.TemporaryDirectory() as d:
            entry = journal_recommendation(d, _rec(), now=_NOW)
            self.assertEqual(entry.source_refs,
                             ("sec:10-K:IREN:2026", "fmp:quote:IREN"))

    def test_records_dq_state(self):
        with tempfile.TemporaryDirectory() as d:
            entry = journal_recommendation(d, _rec(data_quality_ref="explicitly_acceptable"),
                                           now=_NOW)
            self.assertEqual(entry.data_quality_state, "explicitly_acceptable")

    def test_records_the_optional_entry_reference_price(self):
        with tempfile.TemporaryDirectory() as d:
            entry = journal_recommendation(
                d, _rec(), now=_NOW,
                entry_reference_price="$12.50 (reference close)")
            self.assertEqual(entry.entry_reference_price, "$12.50 (reference close)")
            # absent -> None (a gap, never fabricated)
            entry2 = journal_recommendation(d, _rec(recommendation_id="rec:run-1:NVDA",
                                                    ticker="NVDA"), now=_NOW)
            self.assertIsNone(entry2.entry_reference_price)

    def test_re_journal_same_is_idempotent_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _rec(), now=_NOW)
            path = RecommendationJournalStore(d).path
            before = _read_bytes(path)
            journal_recommendation(d, _rec(), now=_LATER)   # same id -> nothing appended
            self.assertEqual(_read_bytes(path), before)

    def test_deterministic_across_store_dirs(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            journal_recommendation(d1, _rec(), now=_NOW)
            journal_recommendation(d2, _rec(), now=_NOW)
            p1 = RecommendationJournalStore(d1).path
            p2 = RecommendationJournalStore(d2).path
            self.assertEqual(_read_bytes(p1), _read_bytes(p2))

    def test_requires_injected_now(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                journal_recommendation(d, _rec(), now="")

    def test_schema_version_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _rec(), now=_NOW)
            raw = RecommendationJournalStore(d).read_records()[0]
            self.assertIn("schema_version", raw)                 # 013B envelope
            self.assertIn("schema_version", raw["payload"])      # journal record


# =========================================================================== #
# 3. record_outcome -- a NEW line, correction-not-mutation, latest-wins        #
# =========================================================================== #
class RecordOutcomeTests(unittest.TestCase):
    def test_outcome_appends_a_new_line_prior_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _rec(), now=_NOW)
            path = RecommendationJournalStore(d).path
            first_line = _read_bytes(path)
            record_outcome(d, "rec:run-1:IREN",
                           outcome_ref="obs:run-3: EMA stack held; +follow-through",
                           now=_LATER, status="thesis_confirmed")
            after = _read_bytes(path)
            # the prior line is byte-unchanged; the new line is appended AFTER it.
            self.assertTrue(after.startswith(first_line),
                            "an existing journal line was rewritten")
            self.assertGreater(len(after), len(first_line))
            self.assertEqual(len(RecommendationJournalStore(d).read_records()), 2)

    def test_latest_wins_extends_outcomes_and_status(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _rec(), now=_NOW)
            record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:run-2: watch",
                           now=_LATER)
            entry = record_outcome(d, "rec:run-1:IREN",
                                   outcome_ref="obs:run-3: invalidation",
                                   now=_LATER, status="invalidation_hit")
            self.assertEqual(entry.subsequent_outcomes,
                             ("obs:run-2: watch", "obs:run-3: invalidation"))
            self.assertEqual(entry.status, "invalidation_hit")
            latest = journaled(d)[0]
            self.assertEqual(latest.status, "invalidation_hit")
            self.assertEqual(len(latest.subsequent_outcomes), 2)

    def test_correction_never_rewrites_an_earlier_line(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _rec(), now=_NOW)
            record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:a", now=_LATER)
            path = RecommendationJournalStore(d).path
            raw_lines_before = _read_bytes(path).splitlines()
            record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:b", now=_LATER,
                           status="lapsed")
            raw_lines_after = _read_bytes(path).splitlines()
            # every earlier physical line is byte-for-byte identical.
            self.assertEqual(raw_lines_after[:len(raw_lines_before)], raw_lines_before)
            self.assertEqual(len(raw_lines_after), len(raw_lines_before) + 1)

    def test_recording_same_outcome_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _rec(), now=_NOW)
            record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:a", now=_LATER,
                           status="thesis_confirmed")
            path = RecommendationJournalStore(d).path
            before = _read_bytes(path)
            record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:a", now=_LATER,
                           status="thesis_confirmed")   # no change -> nothing appended
            self.assertEqual(_read_bytes(path), before)

    def test_outcome_before_journalling_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                record_outcome(d, "rec:never:journaled", outcome_ref="obs:a", now=_LATER)

    def test_outcome_requires_ref_and_now_and_valid_status(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _rec(), now=_NOW)
            with self.assertRaises(ValueError):
                record_outcome(d, "rec:run-1:IREN", outcome_ref="", now=_LATER)
            with self.assertRaises(ValueError):
                record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:a", now="")
            with self.assertRaises(ValueError):
                record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:a", now=_LATER,
                               status="nonsense")


# =========================================================================== #
# 4. Query helpers                                                            #
# =========================================================================== #
class QueryHelperTests(unittest.TestCase):
    def _seed(self, d):
        journal_recommendation(d, _rec(), now=_NOW)
        journal_recommendation(d, _rec(recommendation_id="rec:run-1:NVDA",
                                       ticker="NVDA"), now=_NOW)
        journal_recommendation(d, _rec(recommendation_id="rec:run-2:AVGO",
                                       run_id="run-2", ticker="AVGO"), now=_NOW)

    def test_journaled_returns_latest_per_id(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed(d)
            record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:a", now=_LATER,
                           status="lapsed")
            entries = journaled(d)
            self.assertEqual(len(entries), 3)                  # latest line per id
            iren = [e for e in entries if e.ticker == "IREN"][0]
            self.assertEqual(iren.status, "lapsed")

    def test_journaled_scoped_by_run(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed(d)
            run1 = journaled(d, run_id="run-1")
            self.assertEqual({e.ticker for e in run1}, {"IREN", "NVDA"})

    def test_open_recommendations(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed(d)
            record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:a", now=_LATER,
                           status="thesis_confirmed")
            still_open = {e.ticker for e in open_recommendations(d)}
            self.assertEqual(still_open, {"NVDA", "AVGO"})


# =========================================================================== #
# 5. The 017 Learning & Feedback hook -- labels + volume counts, no score      #
# =========================================================================== #
class FeedLearningTests(unittest.TestCase):
    def test_feed_learning_is_labels_and_volume_counts_only(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _rec(), now=_NOW)                       # open
            journal_recommendation(d, _rec(recommendation_id="rec:run-1:NVDA",
                                           ticker="NVDA"), now=_NOW)          # open
            record_outcome(d, "rec:run-1:IREN", outcome_ref="obs:x", now=_LATER,
                           status="thesis_confirmed")                         # -> followed_through
            counts = feed_learning(d)
            # keys are exactly the 017 outcome vocabulary; values are integer VOLUMES.
            self.assertEqual(set(counts), set(OUTCOME_LABELS))
            for value in counts.values():
                self.assertIsInstance(value, int)
                self.assertNotIsInstance(value, bool)
            self.assertEqual(counts["followed_through"], 1)
            self.assertEqual(counts["unresolved"], 1)          # the still-open NVDA line

    def test_status_outcome_map_targets_the_017_vocabulary(self):
        self.assertEqual(set(JOURNAL_STATUS_OUTCOME), set(JOURNAL_STATUSES))
        for outcome in JOURNAL_STATUS_OUTCOME.values():
            self.assertIn(outcome, OUTCOME_LABELS)


# =========================================================================== #
# 6. Store discipline -- append-only, no update/delete, guards inherited        #
# =========================================================================== #
class StoreDisciplineTests(unittest.TestCase):
    def test_no_update_or_delete_api(self):
        store = RecommendationJournalStore(tempfile.mkdtemp())
        for banned in ("update", "delete", "remove", "edit", "__setitem__", "__delitem__"):
            self.assertFalse(hasattr(store, banned),
                             "journal store exposes a mutation API {0!r}".format(banned))

    def test_store_refuses_a_trade_or_score_key(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                RecommendationJournalStore(d).append(
                    {"journal_id": "x", "conviction_score": 0.9}, record_id="x")
            with self.assertRaises(ValueError):
                RecommendationJournalStore(d).append(
                    {"journal_id": "x", "order_ticket": "T1"}, record_id="x")

    def test_store_refuses_a_credential_key(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                RecommendationJournalStore(d).append(
                    {"journal_id": "x", "api_key": "sk-secret"}, record_id="x")

    def test_round_trips_equal(self):
        with tempfile.TemporaryDirectory() as d:
            entry = journal_recommendation(
                d, _rec(), now=_NOW, entry_reference_price="$12.50 (ref)")
            back = RecommendationJournalStore(d).read_all()[0]
            self.assertEqual(back, entry)

    def test_does_not_modify_any_upstream_store_byte(self):
        # journalling into a store dir that already holds unrelated files leaves them intact.
        with tempfile.TemporaryDirectory() as d:
            other = os.path.join(d, "audit_store.jsonl")
            with open(other, "w", encoding="utf-8") as fh:
                fh.write('{"record_id":"a"}\n')
            before = _snapshot_dir(d)["audit_store.jsonl"]
            journal_recommendation(d, _rec(), now=_NOW)
            after = _snapshot_dir(d)["audit_store.jsonl"]
            self.assertEqual(after, before)


# =========================================================================== #
# 7. Module guards -- AST bans, offline, additive exports                     #
# =========================================================================== #
class JournalModuleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_JOURNAL_PY, encoding="utf-8") as fh:
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
                        "banned import {0!r} in recommendation_journal.py".format(name))

    def test_no_loop_async_or_timed_wait_construct(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in the journal")
            self.assertNotIsInstance(node, ast.AsyncFunctionDef)
            self.assertNotIsInstance(node, ast.Await)
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                self.assertNotIn(called, _BANNED_CALL_NAMES,
                                 "daemon-style call {0!r}".format(called))

    def test_import_has_no_side_effect_beyond_definitions(self):
        allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr,
                   ast.FunctionDef, ast.ClassDef)
        for node in self.tree.body:
            self.assertIsInstance(node, allowed)
            if isinstance(node, ast.Expr):
                # only the docstring, or the construction-time no-trade-field guard call.
                if isinstance(node.value, ast.Call):
                    func = node.value.func
                    self.assertEqual(getattr(func, "id", ""), "assert_no_trade_fields",
                                     "unexpected import-time side effect")
                else:
                    self.assertIsInstance(node.value, ast.Constant)

    def test_no_execution_or_directive_token_anywhere(self):
        low = self.source.lower()
        for tok in _EXECUTION_TOKENS:
            self.assertIsNone(
                re.search(r"\b{0}\b".format(re.escape(tok)), low),
                "execution/directive token {0!r} in recommendation_journal.py".format(tok))

    def test_no_wall_clock_or_randomness(self):
        for token in _WALL_CLOCK_TOKENS:
            self.assertNotIn(token, self.source, "wall-clock call {0!r}".format(token))
        self.assertIsNone(re.search(r"\brandom\b|\brandint\b|\buuid\b",
                                    self.source.lower()))

    def test_no_function_named_like_a_metric(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNone(re.search(r"(score|rank|rating)", node.name.lower()),
                                  "metric-named fn {0!r}".format(node.name))

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()

    def test_exports_are_additive_on_the_package(self):
        for name in ("JOURNAL_STATUSES", "JOURNAL_STATUS_OUTCOME",
                     "RecommendationJournalEntry", "RecommendationJournalStore",
                     "feed_learning", "journal_id_for", "journal_recommendation",
                     "journaled", "open_recommendations", "record_outcome"):
            self.assertTrue(hasattr(rm, name), "reality_mesh.{0} missing".format(name))

    def test_the_seven_013b_stores_are_untouched(self):
        from reality_mesh import stores as S
        self.assertEqual(len(S.STORE_CLASSES), 7)
        self.assertNotIn(RecommendationJournalStore, S.STORE_CLASSES)


# =========================================================================== #
# 8. Untouched paths -- demo default + default pulse stay byte-identical       #
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
