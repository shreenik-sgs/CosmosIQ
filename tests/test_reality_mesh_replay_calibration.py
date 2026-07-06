"""IMPLEMENTATION-022G -- Historical Replay Calibration.

BEFORE trusting production stock-pick reports, the recommendation layer is run over
REPLAY-MODE historical cases to CHECK it avoids obvious bad recommendations, blocks weak
candidates, surfaces a strong+complete-evidence candidate, and flags a deteriorating thesis.
This suite proves the calibration discipline:

* the SAME 022B gates are applied UNCHANGED -- a calibration verdict is byte-identical to the
  live gate output for the same inputs (no hindsight tuning);
* a weak / social-only / insufficient case is honestly BLOCKED / capped-at-watch;
* a deteriorating thesis is FLAGGED (red-team thesis-killer block -> exit_review);
* a strong+complete-evidence case reaches actionable via the real gates (no special-casing);
* EVERY replay record is marked ``replay_mode=True``;
* a replay verdict NEVER appears as a live recommendation (kept in its own append-only log;
  a live recommendation-journal query returns none of them);
* the calibration mutates NO source record (source stores byte-unchanged);
* calibration results are APPEND-ONLY (a re-run into a fresh dir is byte-identical; a new
  record never rewrites a prior line);
* there is NO score / rank / rating field and NO buy/sell/order token anywhere;
* replay_calibration.py carries no banned import / loop / wall-clock / metric-named function /
  execution token, the offline kill-switch is active, and the demo default + default pulse
  stay byte-identical.

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
from dataclasses import FrozenInstanceError, fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh.recommendation_gates import evaluate_recommendation
from reality_mesh.recommendation_journal import journal_recommendation, journaled
from reality_mesh.recommendation import CapitalRecommendation
from reality_mesh.replay_calibration import (
    EXPECTATION_LABELS,
    SCENARIO_KINDS,
    ReplayCalibrationCase,
    ReplayCalibrationResult,
    ReplayCalibrationStore,
    build_illustrative_cases,
    calibration_results,
    calibration_summary,
    record_calibration,
    render_calibration_report,
    run_replay_calibration,
)
from reality_mesh.validation import assert_no_trade_fields

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_CALIB_PY = os.path.join(_PKG_DIR, "replay_calibration.py")

_NOW = "2026-07-06T00:00:00Z"
_LATER = "2026-07-11T09:00:00Z"

_BANNED_IMPORT_ROOTS = ("socket", "requests", "urllib", "http", "sched", "schedule",
                        "apscheduler", "asyncio", "threading", "multiprocessing",
                        "subprocess", "smtplib", "ftplib", "socketserver", "broker",
                        "signal", "time", "random", "select", "selectors", "queue")
_BANNED_CALL_NAMES = ("sleep", "run_forever", "serve_forever", "start_polling", "Thread",
                      "Timer", "Process", "fork", "spawn", "run_in_executor", "setdaemon")
_EXECUTION_TOKENS = ("order", "orders", "broker", "buy", "sell", "submit", "fill_order",
                     "ticket_id")
_WALL_CLOCK_TOKENS = ("time.time(", "datetime.now(", "datetime.utcnow(", "utcnow(",
                      "time.monotonic(", "perf_counter(")
_METRIC_FIELD_FRAGMENTS = ("score", "rank", "rating", "pct", "percent", "ratio",
                           "probability", "weight")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline calibration suite")


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


def _cases():
    return build_illustrative_cases(_NOW)


def _result_for(results, kind):
    return [r for r in results if r.scenario_kind == kind][0]


def _live_rec(**kw):
    base = dict(
        recommendation_id="rec:live-1:IREN", run_id="live-1", candidate_id="cand-1",
        ticker="IREN", recommendation_state="prepare_entry",
        recommendation_label="Prepare Entry", recommendation_time_horizon="12-24 months",
        key_thesis="a genuinely live recommendation",
        invalidation_conditions=("thesis-killer",), exit_watch_conditions=("EMA breakdown",),
        source_provenance=("sec:10-K:IREN:2026",), data_quality_ref="healthy")
    base.update(kw)
    return CapitalRecommendation(**base)


# =========================================================================== #
# 1. The case + result contracts                                              #
# =========================================================================== #
class ContractTests(unittest.TestCase):
    def test_scenario_kinds_are_the_five_closed_kinds(self):
        self.assertEqual(
            SCENARIO_KINDS,
            ("strong_beneficiary_complete_evidence", "hype_weak_evidence",
             "deteriorating_thesis", "social_only_noise", "insufficient_data"))

    def test_expectation_labels_closed(self):
        self.assertEqual(
            set(EXPECTATION_LABELS),
            {"block", "watch", "active_diligence", "actionable", "flag_deterioration"})

    def test_case_requires_ids_and_closed_vocab(self):
        with self.assertRaises(ValueError):
            ReplayCalibrationCase(case_id="", label="x", scenario_kind="hype_weak_evidence",
                                  expectation_label="block", run_id="r", ticker="T")
        with self.assertRaises(ValueError):
            ReplayCalibrationCase(case_id="c", label="x", scenario_kind="not_a_kind",
                                  expectation_label="block", run_id="r", ticker="T")
        with self.assertRaises(ValueError):
            ReplayCalibrationCase(case_id="c", label="x", scenario_kind="hype_weak_evidence",
                                  expectation_label="going_up", run_id="r", ticker="T")

    def test_result_replay_mode_must_be_true(self):
        with self.assertRaises(ValueError):
            ReplayCalibrationResult(case_id="c", replay_mode=False)

    def test_result_state_vocab_enforced(self):
        with self.assertRaises(ValueError):
            ReplayCalibrationResult(case_id="c", recommendation_state="going_up")
        with self.assertRaises(ValueError):
            ReplayCalibrationResult(case_id="c", gate_state="going_up")

    def test_result_frozen(self):
        r = ReplayCalibrationResult(case_id="c")
        with self.assertRaises(FrozenInstanceError):
            r.recommendation_state = "blocked"  # type: ignore[misc]

    def test_no_float_metric_on_result(self):
        with self.assertRaises(ValueError):
            ReplayCalibrationResult(case_id="c", notes=0.5)  # type: ignore[arg-type]


# =========================================================================== #
# 2. The SAME 022B gates -- no hindsight tuning                                #
# =========================================================================== #
class SameGatesTests(unittest.TestCase):
    def test_calibration_gate_state_equals_the_live_gate_output(self):
        # For every case, the calibration's gate_state is byte-identical to calling the LIVE
        # evaluate_recommendation on the same inputs -- proving the gates are not tuned.
        cases = _cases()
        results = run_replay_calibration(cases, now=_NOW)
        by_id = {c.case_id: c for c in cases}
        for r in results:
            c = by_id[r.case_id]
            live_outcome, _ = evaluate_recommendation(
                run_id=c.run_id, ticker=c.ticker, now=_NOW, company_name=c.company_name,
                candidate=c.candidate, data_quality_ref=c.data_quality_ref,
                data_quality_state=c.data_quality_state, source_freshness=c.source_freshness,
                corroboration_sources=c.corroboration_sources,
                theme_pulse_state=c.theme_pulse_state,
                bottleneck_exposure_refs=c.bottleneck_exposure_refs,
                company_evidence_refs=c.company_evidence_refs,
                investment_diligence_ref=c.investment_diligence_ref,
                diligence_complete=c.diligence_complete,
                forward_scenario_ref=c.forward_scenario_ref, red_team_ref=c.red_team_ref,
                unresolved_thesis_killer=c.unresolved_thesis_killer,
                technical_timing_ref=c.technical_timing_ref,
                technical_timing_acceptable=c.technical_timing_acceptable,
                portfolio_fit_ref=c.portfolio_fit_ref,
                portfolio_fit_acceptable=c.portfolio_fit_acceptable,
                sizing_guardrail=c.sizing_guardrail,
                invalidation_conditions=c.invalidation_conditions,
                exit_watch_conditions=c.exit_watch_conditions)
            self.assertEqual(r.gate_state, live_outcome.state,
                             "calibration diverged from the live gate for {0}".format(r.case_id))

    def test_weak_case_is_blocked(self):
        results = run_replay_calibration(_cases(), now=_NOW)
        self.assertEqual(_result_for(results, "hype_weak_evidence").gate_state, "blocked")

    def test_insufficient_case_is_blocked(self):
        results = run_replay_calibration(_cases(), now=_NOW)
        self.assertEqual(_result_for(results, "insufficient_data").gate_state, "blocked")

    def test_social_only_case_is_capped_at_watch(self):
        results = run_replay_calibration(_cases(), now=_NOW)
        social = _result_for(results, "social_only_noise")
        self.assertEqual(social.gate_state, "watch")
        self.assertNotEqual(social.gate_state, "actionable_pick_manual_review")

    def test_strong_complete_case_reaches_actionable(self):
        results = run_replay_calibration(_cases(), now=_NOW)
        strong = _result_for(results, "strong_beneficiary_complete_evidence")
        self.assertIn(strong.gate_state,
                      ("active_diligence", "actionable_pick_manual_review"))
        self.assertEqual(strong.gate_state, "actionable_pick_manual_review")
        self.assertTrue(strong.matched_expectation)

    def test_deteriorating_case_is_flagged(self):
        results = run_replay_calibration(_cases(), now=_NOW)
        det = _result_for(results, "deteriorating_thesis")
        self.assertTrue(det.deterioration_flag)
        self.assertIn(det.recommendation_state, ("exit_review", "deteriorating"))
        # the underlying 022B gate honestly BLOCKED on the thesis-killer.
        self.assertEqual(det.gate_state, "blocked")
        self.assertIn("thesis-killer", det.blocked_reason)

    def test_no_bad_case_ever_reaches_actionable(self):
        results = run_replay_calibration(_cases(), now=_NOW)
        for r in results:
            if r.scenario_kind == "strong_beneficiary_complete_evidence":
                continue
            self.assertNotEqual(r.gate_state, "actionable_pick_manual_review")
            self.assertNotEqual(r.recommendation_state, "actionable_pick_manual_review")

    def test_every_expectation_matched_on_the_illustrative_set(self):
        # Illustrative cases are designed so the conservative expectation matches the actual
        # conservative behaviour -- NOT by tuning gates, but because the inputs genuinely drive it.
        results = run_replay_calibration(_cases(), now=_NOW)
        for r in results:
            self.assertTrue(r.matched_expectation,
                            "{0} did not match its expectation".format(r.case_id))


# =========================================================================== #
# 3. Replay-mode marking + live isolation                                     #
# =========================================================================== #
class ReplayModeAndIsolationTests(unittest.TestCase):
    def test_every_result_is_marked_replay_mode(self):
        results = run_replay_calibration(_cases(), now=_NOW)
        self.assertEqual(len(results), 5)
        for r in results:
            self.assertIs(r.replay_mode, True)

    def test_persisted_records_all_carry_replay_mode(self):
        with tempfile.TemporaryDirectory() as d:
            record_calibration(d, run_replay_calibration(_cases(), now=_NOW), now=_NOW)
            for raw in ReplayCalibrationStore(d).read_records():
                self.assertIs(raw["payload"]["replay_mode"], True)

    def test_replay_verdict_never_appears_as_a_live_recommendation(self):
        with tempfile.TemporaryDirectory() as d:
            # a genuinely LIVE recommendation is journaled...
            journal_recommendation(d, _live_rec(), now=_NOW)
            # ...and the replay calibration is recorded into the SAME store dir.
            record_calibration(d, run_replay_calibration(_cases(), now=_NOW), now=_NOW)
            # the live recommendation-journal query returns ONLY the live rec, none of the replay.
            live = journaled(d)
            self.assertEqual(len(live), 1)
            self.assertEqual(live[0].recommendation_id, "rec:live-1:IREN")
            live_ids = {e.recommendation_id for e in live}
            for r in calibration_results(d):
                self.assertNotIn(r.case_id, live_ids)
            # the two logs are physically distinct files.
            self.assertNotEqual(ReplayCalibrationStore(d).filename,
                                "recommendation_journal.jsonl")


# =========================================================================== #
# 4. No source mutation                                                       #
# =========================================================================== #
class NoSourceMutationTests(unittest.TestCase):
    def test_calibration_does_not_mutate_the_recommendation_journal(self):
        with tempfile.TemporaryDirectory() as d:
            journal_recommendation(d, _live_rec(), now=_NOW)
            journal_path = os.path.join(d, "recommendation_journal.jsonl")
            before = _read_bytes(journal_path)
            record_calibration(d, run_replay_calibration(_cases(), now=_NOW), now=_NOW)
            self.assertEqual(_read_bytes(journal_path), before,
                             "the recommendation journal was mutated by a replay calibration")

    def test_calibration_leaves_an_unrelated_source_file_byte_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            other = os.path.join(d, "signal_store.jsonl")
            with open(other, "w", encoding="utf-8") as fh:
                fh.write('{"record_id":"sig-1"}\n')
            before = _read_bytes(other)
            record_calibration(d, run_replay_calibration(_cases(), now=_NOW), now=_NOW)
            self.assertEqual(_read_bytes(other), before)


# =========================================================================== #
# 5. Append-only persistence                                                  #
# =========================================================================== #
class AppendOnlyPersistenceTests(unittest.TestCase):
    def test_writes_one_line_per_case(self):
        with tempfile.TemporaryDirectory() as d:
            record_calibration(d, run_replay_calibration(_cases(), now=_NOW), now=_NOW)
            self.assertEqual(len(ReplayCalibrationStore(d).read_records()), 5)

    def test_re_record_identical_is_idempotent_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            results = run_replay_calibration(_cases(), now=_NOW)
            record_calibration(d, results, now=_NOW)
            path = ReplayCalibrationStore(d).path
            before = _read_bytes(path)
            record_calibration(d, results, now=_LATER)   # same content -> nothing appended
            self.assertEqual(_read_bytes(path), before)

    def test_deterministic_across_store_dirs(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            record_calibration(d1, run_replay_calibration(_cases(), now=_NOW), now=_NOW)
            record_calibration(d2, run_replay_calibration(_cases(), now=_NOW), now=_NOW)
            p1 = ReplayCalibrationStore(d1).path
            p2 = ReplayCalibrationStore(d2).path
            self.assertEqual(_read_bytes(p1), _read_bytes(p2))

    def test_a_new_record_never_rewrites_a_prior_line(self):
        with tempfile.TemporaryDirectory() as d:
            record_calibration(d, run_replay_calibration(_cases(), now=_NOW), now=_NOW)
            path = ReplayCalibrationStore(d).path
            lines_before = _read_bytes(path).splitlines()
            # a CHANGED result for one case_id appends a NEW line; prior lines are untouched.
            changed = (ReplayCalibrationResult(
                case_id="replaycal:hype_weak_evidence", replay_mode=True,
                scenario_kind="hype_weak_evidence", expectation_label="block",
                recommendation_state="blocked", gate_state="blocked",
                blocked_reason="re-calibrated", matched_expectation=True),)
            record_calibration(d, changed, now=_LATER)
            lines_after = _read_bytes(path).splitlines()
            self.assertEqual(lines_after[:len(lines_before)], lines_before)
            self.assertEqual(len(lines_after), len(lines_before) + 1)
            # latest-wins per case_id.
            latest = {r.case_id: r for r in calibration_results(d)}
            self.assertEqual(latest["replaycal:hype_weak_evidence"].blocked_reason,
                             "re-calibrated")
            self.assertEqual(len(calibration_results(d)), 5)

    def test_store_refuses_a_trade_or_score_key(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                ReplayCalibrationStore(d).append(
                    {"case_id": "x", "alpha_score": 0.9}, record_id="x")
            with self.assertRaises(ValueError):
                ReplayCalibrationStore(d).append(
                    {"case_id": "x", "order_ref": "T1"}, record_id="x")

    def test_store_has_no_update_or_delete_api(self):
        store = ReplayCalibrationStore(tempfile.mkdtemp())
        for banned in ("update", "delete", "remove", "edit", "__setitem__", "__delitem__"):
            self.assertFalse(hasattr(store, banned))

    def test_round_trips_equal(self):
        with tempfile.TemporaryDirectory() as d:
            results = run_replay_calibration(_cases(), now=_NOW)
            record_calibration(d, results, now=_NOW)
            back = {r.case_id: r for r in ReplayCalibrationStore(d).read_all()}
            for r in results:
                self.assertEqual(back[r.case_id], r)


# =========================================================================== #
# 6. Summary + report (labels + counts, honest tone)                          #
# =========================================================================== #
class SummaryAndReportTests(unittest.TestCase):
    def test_summary_is_labels_and_integer_volumes_only(self):
        summary = calibration_summary(run_replay_calibration(_cases(), now=_NOW))
        for value in summary.values():
            self.assertIsInstance(value, int)
            self.assertNotIsInstance(value, bool)
        self.assertEqual(summary["cases_total"], 5)
        self.assertEqual(summary["matched_expectation"], 5)
        self.assertEqual(summary["actionable"], 1)
        self.assertEqual(summary["blocked"], 3)
        self.assertEqual(summary["watch"], 1)
        self.assertEqual(summary["flagged_deterioration"], 1)

    def test_report_answers_the_four_questions_and_states_caveats(self):
        cases = _cases()
        results = run_replay_calibration(cases, now=_NOW)
        report = render_calibration_report(cases, results, calibration_summary(results), now=_NOW)
        low = report.lower()
        self.assertIn("not a validated", low)
        self.assertIn("synthetic", low)
        self.assertIn("illustrative", low)
        self.assertIn("avoid obvious bad recommendations", low)
        self.assertIn("block weak candidates", low)
        self.assertIn("surface a strong candidate", low)
        self.assertIn("flag a deteriorating thesis", low)
        # honesty: never claims a real ticker was caught.
        self.assertIn("no real ticker is claimed", low)

    def test_report_matches_the_committed_report_file(self):
        cases = _cases()
        results = run_replay_calibration(cases, now=_NOW)
        rendered = render_calibration_report(
            cases, results, calibration_summary(results), now=_NOW)
        report_path = os.path.join(_ROOT, "reports", "HISTORICAL_REPLAY_CALIBRATION_022G.md")
        with open(report_path, encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(rendered.strip(), committed.strip(),
                         "the committed 022G report drifted from the deterministic renderer")


# =========================================================================== #
# 7. No trade / score field anywhere                                          #
# =========================================================================== #
class NoTradeOrScoreFieldTests(unittest.TestCase):
    def test_case_and_result_have_no_trade_or_score_field(self):
        for cls in (ReplayCalibrationCase, ReplayCalibrationResult):
            assert_no_trade_fields(cls)
            for f in fields(cls):
                low = f.name.lower()
                for tok in _EXECUTION_TOKENS:
                    self.assertNotIn(tok, low,
                                     "execution token {0!r} in field {1!r}".format(tok, f.name))

    def test_persisted_result_record_carries_no_numeric_value(self):
        # The result is what gets persisted + fed to 017 as labels+counts: every field is a
        # string or a bool -- never a numeric metric. (canonical trade/score field names are
        # already rejected by assert_no_trade_fields above.)
        results = run_replay_calibration(_cases(), now=_NOW)
        for r in results:
            for f in fields(r):
                value = getattr(r, f.name)
                self.assertNotIsInstance(value, float,
                                         "numeric field {0!r}".format(f.name))
                if not isinstance(value, bool):
                    self.assertNotIsInstance(value, int,
                                             "numeric field {0!r}".format(f.name))


# =========================================================================== #
# 8. Module guards -- AST bans, offline, additive exports                     #
# =========================================================================== #
class ModuleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_CALIB_PY, encoding="utf-8") as fh:
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
                        "banned import {0!r} in replay_calibration.py".format(name))

    def test_no_loop_async_or_timed_wait_construct(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.While, "while-loop in the calibration")
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
                "execution/directive token {0!r} in replay_calibration.py".format(tok))

    def test_no_wall_clock_or_randomness(self):
        for token in _WALL_CLOCK_TOKENS:
            self.assertNotIn(token, self.source, "wall-clock call {0!r}".format(token))
        self.assertIsNone(re.search(r"\brandom\b|\brandint\b|\buuid\b", self.source.lower()))

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
        for name in ("SCENARIO_KINDS", "EXPECTATION_LABELS", "ReplayCalibrationCase",
                     "ReplayCalibrationResult", "ReplayCalibrationStore",
                     "run_replay_calibration", "calibration_summary", "record_calibration",
                     "calibration_results", "build_illustrative_cases",
                     "render_calibration_report"):
            self.assertTrue(hasattr(rm, name), "reality_mesh.{0} missing".format(name))

    def test_the_seven_013b_stores_are_untouched(self):
        from reality_mesh import stores as S
        self.assertEqual(len(S.STORE_CLASSES), 7)
        self.assertNotIn(ReplayCalibrationStore, S.STORE_CLASSES)


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
