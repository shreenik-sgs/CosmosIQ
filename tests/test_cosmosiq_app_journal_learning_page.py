"""IMPLEMENTATION-UX-4 -- the Journal & Learning page (/journal).

Dispatcher-only, OFFLINE (the whole module runs under a socket kill-switch; no
server, no socket, no wall clock). This surfaces the learning loop in the cockpit's
"Journal & Learning" tab, over three read-only sections built by a PURE function from
the store:

* the 022F recommendation journal (newest first) -- ticker, recommendation label,
  published date, thesis, invalidation + exit/watch conditions, DQ state, the closed
  status ladder, and the subsequent outcomes accrued -- plus an honest empty state;
* the 017 learning loop as LABELS + VOLUME COUNTS -- an outcome tally per
  OUTCOME_LABELS and a per-signal-family reliability panel per RELIABILITY_LABELS --
  with a plain-English calibration note (never a hit-rate / track-record number) and
  an honest empty state;
* the operator's actions vs recommendations, via the UX-2 ledger
  (outcomes_for_learning): each journaled recommendation labelled acted (a linked fill
  exists) or not-yet-acted -- the visible close of the loop -- plus its honest empty
  state.

Proven: labels + counts only (no score / rank / rating / return / pct / % metric); no
trade affordance (strict word-boundary sweep AND the accepted ci-gate action-phrase
sweep find NONE); a real order route -> 403; no secret; the prod_check
no_trade_control + ci_gate page scans STILL pass with the page live; deterministic
render; universe_ui demo + reality_mesh default pulse stay byte-identical; offline.
"""

from __future__ import annotations

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
from reality_mesh.recommendation_journal import (
    RecommendationJournalEntry,
    RecommendationJournalStore,
)
from reality_mesh.learning import (
    LearningStore,
    OutcomeRecord,
    OutcomeStore,
    SignalReliabilityRecord,
)
from cosmosiq_app.api import dispatch, EXECUTION_REFUSAL
from cosmosiq_ops.ci_gate import TRADE_WORD_RE, check_generated_pages_clean
from cosmosiq_ops.prod_check import _scan_no_trade_control

_NOW = "2026-06-29T00:00:00Z"

# The strict per-tab affordance sweep (identical to the standing cockpit-shell list):
# ZERO of these word-boundary trade verbs may appear on the surface.
_STRICT_TRADE = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
# A fabricated numeric METRIC would name one of these tokens as a WHOLE word (a label like
# "deteriorating" legitimately contains "rating" as a substring -- word boundaries avoid that
# false positive; a threshold legend naming a label is fine).
_METRIC_WORD = re.compile(
    r"\b(score|rank|ranking|rating|return|returns|rate|pct|percentage)\b", re.IGNORECASE)
_CRED_TOKENS = tuple(rm.CREDENTIAL_KEY_TOKENS)

_ORIG_CONNECT = None


def _boom(*a, **k):
    raise AssertionError("network access attempted during offline UX-4 journal tests")


def _call(store_dir, method, path, body=None):
    return dispatch({"method": method, "path": path, "query": {}, "body": body},
                    store_dir=store_dir, now=_NOW)


def _journal_html(store_dir):
    r = _call(store_dir, "GET", "/journal")
    assert r["status"] == 200, r
    assert r["headers"]["Content-Type"].startswith("text/html"), r
    return r["body"]


def _body_after_style(html):
    """The page body (everything after the inline <style> in <head>) -- so a CSS percentage in
    the stylesheet never masquerades as a rendered performance metric."""
    return html.split("</style>", 1)[1]


def _seed_recommendation(store_dir, *, rec_id, ticker, label, state, status,
                         thesis, invalidation, exit_watch, dq="healthy", outcomes=()):
    entry = RecommendationJournalEntry(
        journal_id="recjournal:RUN-UX4:{0}".format(rec_id),
        recommendation_id=rec_id, run_id="RUN-UX4", ticker=ticker,
        recommendation_label=label, recommendation_state=state, published_at=_NOW,
        thesis_summary=thesis, invalidation_condition=invalidation,
        exit_watch_condition=exit_watch, data_quality_state=dq,
        subsequent_outcomes=tuple(outcomes), status=status)
    RecommendationJournalStore(store_dir).append(entry, run_id="RUN-UX4", timestamp=_NOW)
    return entry


def _seed_outcome(store_dir, *, oid, subject_id, label):
    kwargs = dict(outcome_id=oid, subject_kind="signal", subject_id=subject_id,
                  subject_run_id="r1", claimed="direction 'rising'", outcome_label=label,
                  basis="cites r1 and r2", created_at=_NOW)
    if label != "unresolved":
        kwargs.update(observed_run_id="r2", observed="direction 'rising'")
    OutcomeStore(store_dir).append(OutcomeRecord(**kwargs), run_id="r1", timestamp=_NOW)


def _seed_reliability(store_dir, *, discipline, label, ft=2, ct=1, fd=1, un=0):
    rec = SignalReliabilityRecord(
        learning_id="learn.signal-reliability.{0}".format(discipline), discipline=discipline,
        window=("r1", "r2"), followed_through_count=ft, contradicted_count=ct,
        faded_count=fd, unresolved_count=un, reliability_label=label,
        basis="across runs r1..r2", created_at=_NOW)
    LearningStore(store_dir).append(rec, timestamp=_NOW)


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


# =========================================================================== #
# 1. Empty store: all three sections render honest empty states                #
# =========================================================================== #
class EmptyStateTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ux4_empty_")
        self.html = _journal_html(self.d)

    def test_the_three_section_headings_render(self):
        self.assertIn("Recommendation journal", self.html)
        self.assertIn("Learning &amp; feedback", self.html)
        self.assertIn("Your actions vs recommendations", self.html)

    def test_honest_empty_states(self):
        self.assertIn("No recommendations journaled yet", self.html)
        self.assertIn("they appear here once the recommendation layer publishes", self.html)
        self.assertIn("No learning history yet", self.html)
        self.assertIn("No recorded fills linked to a recommendation yet", self.html)

    def test_journal_tab_is_active_on_journal(self):
        # the primary tab lights up on /journal
        self.assertIn('<a class="navlink here" href="/journal">Journal &amp; Learning</a>',
                      self.html)


# =========================================================================== #
# 2. The 022F recommendation journal renders (label/status/thesis/etc.)         #
# =========================================================================== #
class RecommendationJournalTests(unittest.TestCase):
    def test_a_journaled_recommendation_renders_with_its_fields(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_recommendation(
                d, rec_id="rec1", ticker="ABC",
                label="Actionable Pick — Manual Review",
                state="actionable_pick_manual_review", status="thesis_confirmed",
                thesis="Bottleneck owner with pricing power",
                invalidation="gross margin falls two quarters",
                exit_watch="watch the next guidance print", outcomes=("obs:confirmed-q3",))
            html = _journal_html(d)
            self.assertIn("ABC", html)
            self.assertIn("Actionable Pick", html)
            self.assertIn("Bottleneck owner with pricing power", html)
            self.assertIn("gross margin falls two quarters", html)
            self.assertIn("watch the next guidance print", html)
            self.assertIn("thesis_confirmed", html)          # its status
            self.assertIn("obs:confirmed-q3", html)          # the subsequent outcome accrued

    def test_the_closed_status_vocab_renders_as_a_legend(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_recommendation(
                d, rec_id="rec1", ticker="ABC", label="Watch", state="watch",
                status="open", thesis="t", invalidation="i", exit_watch="x")
            html = _journal_html(d)
            for status in rm.JOURNAL_STATUSES:
                self.assertIn(status, html, status)

    def test_newest_first_ordering(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_recommendation(d, rec_id="rec1", ticker="OLD", label="Watch",
                                 state="watch", status="open", thesis="t",
                                 invalidation="i", exit_watch="x")
            _seed_recommendation(d, rec_id="rec2", ticker="NEW", label="Watch",
                                 state="watch", status="open", thesis="t",
                                 invalidation="i", exit_watch="x")
            html = _journal_html(d)
            self.assertLess(html.index("NEW"), html.index("OLD"))


# =========================================================================== #
# 3. The 017 learning loop: LABELS + VOLUME COUNTS, no numeric metric           #
# =========================================================================== #
class LearningFeedbackTests(unittest.TestCase):
    def _seed(self, d):
        _seed_outcome(d, oid="o.ft.1", subject_id="s1", label="followed_through")
        _seed_outcome(d, oid="o.ft.2", subject_id="s2", label="followed_through")
        _seed_outcome(d, oid="o.faded.1", subject_id="s3", label="faded")
        _seed_outcome(d, oid="o.unres.1", subject_id="s4", label="unresolved")
        _seed_reliability(d, discipline="macro_regime", label="improving")
        _seed_reliability(d, discipline="narrative", label="insufficient_history",
                          ft=0, ct=0, fd=1, un=2)

    def test_outcome_tally_renders_labels_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed(d)
            html = _journal_html(d)
            self.assertIn("Outcome tally", html)
            self.assertIn("followed through", html)          # OUTCOME_LABELS display
            self.assertIn("faded", html)
            # the volume counts render (2 followed-through outcomes)
            self.assertIn(">2<", html)

    def test_reliability_panel_renders_labels_per_family(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed(d)
            html = _journal_html(d)
            self.assertIn("Signal reliability", html)
            self.assertIn("macro_regime", html)              # a signal family
            self.assertIn("strengthening", html)             # improving RELIABILITY_LABEL, glossed
            self.assertIn("insufficient_history", html)      # the honest below-threshold label
            # the threshold legend names the min-resolved-outcomes threshold as DATA
            self.assertIn(str(rm.LEARNING_THRESHOLDS["min_resolved_outcomes"]), html)

    def test_no_numeric_score_rate_or_percentage_metric_appears(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed(d)
            body = _body_after_style(_journal_html(d))
            self.assertEqual(_METRIC_WORD.findall(body), [], _METRIC_WORD.findall(body))
            self.assertNotIn("%", body)                      # no percentage figure at all
            self.assertIsNone(re.search(r"\d\s*%", body))    # no fabricated hit-rate figure

    def test_calibration_note_states_labels_over_volume(self):
        with tempfile.TemporaryDirectory() as d:
            self._seed(d)
            low = _journal_html(d).lower()
            self.assertIn("calibration", low)
            self.assertIn("volume", low)


# =========================================================================== #
# 4. Your actions vs recommendations (the loop close) via the UX-2 ledger       #
# =========================================================================== #
class ActionsVsRecommendationsTests(unittest.TestCase):
    def test_acted_and_not_yet_acted_labels(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_recommendation(d, rec_id="rec1", ticker="ABC", label="Watch",
                                 state="watch", status="open", thesis="t",
                                 invalidation="i", exit_watch="x")
            _seed_recommendation(d, rec_id="rec2", ticker="XYZ", label="Watch",
                                 state="watch", status="open", thesis="t",
                                 invalidation="i", exit_watch="x")
            # a recorded fill LINKED to rec1 -> ABC is acted; rec2 stays not-yet-acted
            rm.record_fill(d, ticker="ABC", side="bought", quantity=10, price=5,
                           trade_date="2026-01-05", recommendation_ref="rec1", now=_NOW)
            html = _journal_html(d)
            self.assertIn(">acted<", html)
            self.assertIn(">not-yet-acted<", html)
            # the past-tense recorded action + its ref render; no P&L
            self.assertIn("rec1", html)
            self.assertIn("bought", html)
            body = _body_after_style(html)
            self.assertEqual(_METRIC_WORD.findall(body), [], _METRIC_WORD.findall(body))

    def test_a_linked_fill_for_an_unjournaled_ref_is_never_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            rm.record_fill(d, ticker="QQQ", side="bought", quantity=1, price=1,
                           trade_date="2026-01-05", recommendation_ref="ghost-rec", now=_NOW)
            html = _journal_html(d)
            self.assertIn("ghost-rec", html)                 # the recorded action still shows
            self.assertIn(">acted<", html)

    def test_empty_state_when_nothing_linked(self):
        with tempfile.TemporaryDirectory() as d:
            html = _journal_html(d)
            self.assertIn("No recorded fills linked to a recommendation yet", html)


# =========================================================================== #
# 5. No trade affordance / no secret / a real order route still 403             #
# =========================================================================== #
class AffordanceAndSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty = tempfile.mkdtemp(prefix="ux4_sweep_empty_")
        cls.full = tempfile.mkdtemp(prefix="ux4_sweep_full_")
        _seed_recommendation(cls.full, rec_id="rec1", ticker="ABC",
                             label="Actionable Pick — Manual Review",
                             state="actionable_pick_manual_review", status="invalidation_hit",
                             thesis="thesis words", invalidation="inval words",
                             exit_watch="exit words", outcomes=("obs:1",))
        _seed_outcome(cls.full, oid="o.ct.1", subject_id="s1", label="contradicted")
        _seed_reliability(cls.full, discipline="technical_regime", label="deteriorating")
        rm.record_fill(cls.full, ticker="ABC", side="bought", quantity=5, price=2,
                       trade_date="2026-01-04", recommendation_ref="rec1", now=_NOW)
        cls.pages = {
            "empty": _journal_html(cls.empty),
            "full": _journal_html(cls.full),
        }

    def test_strict_word_boundary_sweep_finds_no_trade_verb(self):
        for name, html in self.pages.items():
            self.assertEqual(_STRICT_TRADE.findall(html), [],
                             "{0}: {1}".format(name, _STRICT_TRADE.findall(html)))

    def test_accepted_ci_gate_action_phrase_sweep_finds_none(self):
        for name, html in self.pages.items():
            self.assertEqual(TRADE_WORD_RE.findall(html), [],
                             "{0}: {1}".format(name, TRADE_WORD_RE.findall(html)))

    def test_no_metric_and_no_secret_token(self):
        for name, html in self.pages.items():
            body = _body_after_style(html)
            self.assertEqual(_METRIC_WORD.findall(body), [],
                             "{0}: {1}".format(name, _METRIC_WORD.findall(body)))
            low = html.lower()
            for token in _CRED_TOKENS:
                self.assertNotIn(token, low, "{0}: {1}".format(name, token))
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{8,}", html))

    def test_no_form_or_button_on_the_read_only_page(self):
        for name, html in self.pages.items():
            self.assertNotIn("<form", html, name)
            self.assertNotIn("<button", html, name)

    def test_a_real_order_route_stays_403(self):
        for path in ("/api/orders", "/api/execution/submit", "/api/journal/trade", "/api/buy"):
            r = _call(self.full, "GET", path, body={"ticker": "ABC"})
            self.assertEqual(r["status"], 403, path)
            self.assertEqual(r["body"]["error"], EXECUTION_REFUSAL, path)


# =========================================================================== #
# 6. ci_gate + prod_check still pass; determinism; byte-identical; offline       #
# =========================================================================== #
class GateAndDisciplineTests(unittest.TestCase):
    def test_prod_check_no_trade_control_still_passes(self):
        result = _scan_no_trade_control(_ROOT, _NOW)
        self.assertEqual(result.status, "pass", result.details)

    def test_ci_gate_generated_pages_clean_still_passes(self):
        result = check_generated_pages_clean(_ROOT)
        self.assertEqual(result.status, "pass", result.details)

    def test_render_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_recommendation(d, rec_id="rec1", ticker="ABC", label="Watch",
                                 state="watch", status="open", thesis="t",
                                 invalidation="i", exit_watch="x")
            _seed_outcome(d, oid="o.ft.1", subject_id="s1", label="followed_through")
            _seed_reliability(d, discipline="macro_regime", label="improving")
            rm.record_fill(d, ticker="ABC", side="bought", quantity=1, price=1,
                           trade_date="2026-01-05", recommendation_ref="rec1", now=_NOW)
            self.assertEqual(_journal_html(d), _journal_html(d))

    def test_rendering_mutates_no_stored_byte(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_recommendation(d, rec_id="rec1", ticker="ABC", label="Watch",
                                 state="watch", status="open", thesis="t",
                                 invalidation="i", exit_watch="x")
            path = os.path.join(d, "recommendation_journal.jsonl")
            with open(path, "rb") as fh:
                before = fh.read()
            _journal_html(d)
            _journal_html(d)
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), before)

    def test_universe_ui_demo_stays_byte_identical(self):
        from universe_ui.app import build_universe_app
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                with open(a[name], "rb") as fa, open(b[name], "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(), name)

    def test_reality_mesh_default_pulse_stays_byte_identical(self):
        first = rm.run_pulse(["ABC", "XYZ"], ["physical_ai"], now=_NOW)
        again = rm.run_pulse(["ABC", "XYZ"], ["physical_ai"], now=_NOW)
        self.assertEqual([s.signal_id for s in first.signals],
                         [s.signal_id for s in again.signals])
        self.assertEqual(first.theme_pulses, again.theme_pulses)

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
