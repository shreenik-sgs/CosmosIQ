"""IMPLEMENTATION-022E -- the Capital Picks Report Renderer (MANUAL REVIEW).

This suite runs entirely OFFLINE -- no network, no scheduler, no broker, no live endpoint. It
proves the renderer is an honest, READ/INSPECT-ONLY presentation of the 022A/B/C/D stack:

* it renders the ZERO-PICK state honestly (0 Actionable Picks + honest counts, and the
  DQ-insufficient variant), never fabricating a pick to fill the report;
* an actionable pick appears in section 3 ONLY when its state is
  ``actionable_pick_manual_review`` -- a non-actionable one never does;
* every per-pick field, the blocked reasons, the provenance appendix, the DQ summary, the
  portfolio fit and the timing setup all render;
* there is NO buy / sell / order / submit / place-trade / auto-trade affordance anywhere (regex
  sweep) and NO hidden score / rank / rating;
* the 13 section headers appear in order; output is deterministic (byte-identical for the same
  input) and demo + default-pulse renders are byte-identical.
"""

from __future__ import annotations

import os
import re
import socket
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import capital_picks_report as CPR
from reality_mesh.capital_picks_report import (
    ALLOWED_NEXT_ACTIONS,
    REPORT_TITLE,
    SECTION_TITLES,
    render_capital_picks_report,
)
from reality_mesh.recommendation import (
    RECOMMENDATION_STATE_LABELS,
    CapitalRecommendation,
    assess_recommendation,
)

_RUN = "RUN-1"
_NOW = "2026-07-06T00:00:00Z"

# The forbidden marketing / trade phrases -- none may appear anywhere in the report.
_FORBIDDEN_PHRASES = ("buy now", "sell now", "submit order", "place trade", "auto trade")
# The forbidden trade verbs (whole-word). "order" is allowed ONLY in "no order is placed".
_FORBIDDEN_VERBS = ("buy", "sell", "submit", "trade")
# The forbidden hidden-score/rank tokens (whole-word; "Deteriorating" legitimately holds "rating").
_FORBIDDEN_SCORE_TOKENS = ("score", "rank", "rating", "alpha score")


def _full_actionable(ticker="IREN", **overrides):
    """A fully-populated ``actionable_pick_manual_review`` recommendation (the unforgeable state)."""
    base = dict(
        recommendation_id="rec:{0}:{1}".format(_RUN, ticker), run_id=_RUN,
        generated_at=_NOW, candidate_id="cc:{0}:{1}".format(_RUN, ticker),
        ticker=ticker, company_name="{0} Ltd".format(ticker),
        recommendation_state="actionable_pick_manual_review",
        recommendation_label=RECOMMENDATION_STATE_LABELS["actionable_pick_manual_review"],
        recommendation_time_horizon="6-18 months",
        theme_ref="theme:ai-datacenter", mega_theme_ref="mega:compute-buildout",
        value_chain_ref="vc:power-shell", bottleneck_ref="bneck:grid-interconnect",
        capital_candidate_ref="cc:{0}:{1}".format(_RUN, ticker),
        investment_diligence_ref="THS-1", forward_scenario_ref="FWD-1",
        technical_timing_ref="tts:{0}:{1}".format(_RUN, ticker),
        portfolio_fit_ref="pf:{0}:{1}".format(_RUN, ticker),
        red_team_ref="RT-1", data_quality_ref="DQ-1",
        source_provenance=("run:{0}".format(_RUN), "signal:sig-1"),
        evidence_summary="canonical filings plus two independent primary sources",
        key_thesis="beneficiary of the interconnect chokepoint",
        why_now="capacity contract signed; repricing underway",
        expected_catalysts=("Q3 capacity ramp",),
        primary_risks=("power-price spike could compress margin",),
        data_gaps=("no independent liquidity read yet",),
        invalidation_conditions=("thesis broken if contract cancelled",),
        exit_watch_conditions=("exit if EMA stack breaks down",),
        sizing_guardrail="starter position only (range, not a number)",
        manual_execution_preview_ref="mep:{0}:{1}".format(_RUN, ticker),
        publication_state="published",
    )
    base.update(overrides)
    return CapitalRecommendation(**base)


def _simple(state, ticker):
    """A non-actionable recommendation in ``state`` (built honestly by the 022A assembler)."""
    kwargs = dict(ticker=ticker, run_id=_RUN, intended_state=state, now=_NOW,
                  candidate_id="cc:{0}:{1}".format(_RUN, ticker),
                  company_name="{0} Inc".format(ticker),
                  why_now="under review", recommendation_time_horizon="TBD")
    if state == "blocked":
        # A blocked recommendation via the gate engine carries an exact reason; here use the
        # assembler which downgrades a would-be-actionable with missing refs to a reasoned block.
        rec = assess_recommendation(intended_state="actionable_pick_manual_review",
                                    **{k: v for k, v in kwargs.items()
                                       if k != "intended_state"})
        return rec
    return assess_recommendation(**kwargs)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# =========================================================================== #
# Title, mode, sections, ordering                                              #
# =========================================================================== #
class StructureTests(unittest.TestCase):
    def test_title_and_mode(self):
        report = render_capital_picks_report([], run_id=_RUN, generated_at=_NOW)
        self.assertTrue(report.startswith(REPORT_TITLE))
        self.assertIn("Mode: Shadow", report)
        prod = render_capital_picks_report([], run_id=_RUN, generated_at=_NOW, mode="production")
        self.assertIn("Mode: Production", prod)

    def test_all_13_section_headers_present_in_order(self):
        report = render_capital_picks_report([_full_actionable()], run_id=_RUN, generated_at=_NOW)
        self.assertEqual(len(SECTION_TITLES), 13)
        last = -1
        for index, title in enumerate(SECTION_TITLES, start=1):
            header = "Section {0}. {1}".format(index, title)
            pos = report.find(header)
            self.assertNotEqual(pos, -1, "missing header: {0}".format(header))
            self.assertGreater(pos, last, "section {0} out of order".format(index))
            last = pos

    def test_as_of_honesty_line(self):
        report = render_capital_picks_report([], run_id=_RUN, generated_at=_NOW)
        self.assertIn("As of: {0}".format(_NOW), report)
        self.assertIn("nothing is fetched live", report)


# =========================================================================== #
# Zero-pick honesty                                                           #
# =========================================================================== #
class ZeroPickTests(unittest.TestCase):
    def test_no_recommendations_is_zero_actionable(self):
        report = render_capital_picks_report([], run_id=_RUN, generated_at=_NOW)
        self.assertIn("Headline: 0 Actionable Picks", report)
        self.assertIn("Actionable picks: 0", report)
        self.assertIn("Watchlist: 0", report)
        self.assertIn("Blocked: 0", report)
        self.assertIn("valid, expected outcome", report)
        # section 3 states it plainly
        self.assertIn("0 Actionable Picks. No recommendation reached", report)

    def test_none_actionable_still_zero(self):
        recs = [_simple("watch", "AAA"), _simple("active_diligence", "BBB")]
        report = render_capital_picks_report(recs, run_id=_RUN, generated_at=_NOW)
        self.assertIn("Headline: 0 Actionable Picks", report)
        self.assertIn("Actionable picks: 0", report)
        self.assertIn("Watchlist: 1", report)
        self.assertIn("Active-diligence candidates: 1", report)

    def test_dq_insufficient_variant(self):
        report = render_capital_picks_report(
            [], run_id=_RUN, generated_at=_NOW, dq_summary="producing run data quality failed")
        self.assertIn("0 Picks — source freshness / Data Quality insufficient", report)

    def test_never_fabricates_a_pick(self):
        report = render_capital_picks_report([], run_id=_RUN, generated_at=_NOW)
        # no per-pick "Pick 1:" block when there are no actionable picks
        self.assertNotIn("Pick 1:", report)


# =========================================================================== #
# Actionable pick appears ONLY when state is actionable                       #
# =========================================================================== #
class ActionableRenderTests(unittest.TestCase):
    def test_actionable_pick_renders_all_fields(self):
        report = render_capital_picks_report([_full_actionable("IREN")],
                                             run_id=_RUN, generated_at=_NOW)
        self.assertIn("Headline: 1 New Actionable Pick(s) — Manual Review", report)
        self.assertIn("Pick 1: IREN — IREN Ltd", report)
        for label in (
            "Recommendation: Actionable Pick — Manual Review",
            "Time horizon: 6-18 months",
            "Why now: capacity contract signed",
            "Theme: theme:ai-datacenter",
            "Mega theme: mega:compute-buildout",
            "Value chain: vc:power-shell",
            "Bottleneck exposure: bneck:grid-interconnect",
            "Evidence summary: canonical filings",
            "Source authority / provenance:",
            "Signal state:",
            "Forward scenario: FWD-1",
            "Technical setup (022C): tts:RUN-1:IREN",
            "Portfolio fit (022D): pf:RUN-1:IREN",
            "Sizing guardrail: starter position only",
            "Invalidation:",
            "thesis broken if contract cancelled",
            "Exit / watch:",
            "exit if EMA stack breaks down",
            "Red-team risks: RT-1",
            "power-price spike could compress margin",
            "Data gaps:",
            "no independent liquidity read yet",
            "Next action:",
        ):
            self.assertIn(label, report, "missing per-pick field: {0}".format(label))

    def test_non_actionable_never_in_section_3(self):
        recs = [_simple("watch", "AAA"), _simple("active_diligence", "BBB")]
        report = render_capital_picks_report(recs, run_id=_RUN, generated_at=_NOW)
        section3 = _slice_section(report, 3, 4)
        self.assertIn("0 Actionable Picks", section3)
        self.assertNotIn("AAA", section3)
        self.assertNotIn("BBB", section3)
        # but they DO show in their own sections
        self.assertIn("AAA", _slice_section(report, 6, 7))
        self.assertIn("BBB", _slice_section(report, 5, 6))

    def test_next_action_only_allowed_values(self):
        report = render_capital_picks_report([_full_actionable()], run_id=_RUN, generated_at=_NOW)
        for m in re.finditer(r"^  Next action: (.+)$", report, flags=re.MULTILINE):
            actions = [a.strip() for a in m.group(1).split("·")]
            for action in actions:
                self.assertIn(action, ALLOWED_NEXT_ACTIONS,
                              "disallowed next-action rendered: {0!r}".format(action))


# =========================================================================== #
# Blocked, red-team, DQ, portfolio, timing, provenance                        #
# =========================================================================== #
class SectionContentTests(unittest.TestCase):
    def test_blocked_reasons_rendered_exactly(self):
        blocked = _simple("blocked", "CCC")
        self.assertTrue(blocked.is_blocked)
        report = render_capital_picks_report([blocked], run_id=_RUN, generated_at=_NOW)
        section8 = _slice_section(report, 8, 9)
        self.assertIn("CCC:", section8)
        self.assertIn(blocked.blocked_reason, section8)
        self.assertIn("Blocked: 1", report)

    def test_provenance_appendix(self):
        rec = _full_actionable("IREN")
        report = render_capital_picks_report([rec], run_id=_RUN, generated_at=_NOW)
        section13 = _slice_section(report, 13, 14)
        self.assertIn("Run id: RUN-1", section13)
        self.assertIn(rec.recommendation_id, section13)
        self.assertIn(rec.candidate_id, section13)
        self.assertIn("run:RUN-1", section13)
        self.assertIn("signal:sig-1", section13)

    def test_dq_summary_rendered(self):
        report = render_capital_picks_report(
            [], run_id=_RUN, generated_at=_NOW, dq_summary="freshness healthy; conflicts none")
        section10 = _slice_section(report, 10, 11)
        self.assertIn("freshness healthy; conflicts none", section10)

    def test_dq_summary_gate_result_sequence(self):
        class _R:
            def __init__(self, category, status, findings):
                self.category = category
                self.status = status
                self.findings = findings
        results = [_R("freshness", "pass", ("all sources fresh",)),
                   _R("conflict", "warn", ("one unresolved conflict",))]
        report = render_capital_picks_report([], run_id=_RUN, generated_at=_NOW, dq_summary=results)
        section10 = _slice_section(report, 10, 11)
        self.assertIn("freshness: pass", section10)
        self.assertIn("conflict: warn", section10)
        self.assertIn("one unresolved conflict", section10)

    def test_portfolio_fit_rendered(self):
        rec = _full_actionable("IREN")
        report = render_capital_picks_report([rec], run_id=_RUN, generated_at=_NOW)
        section11 = _slice_section(report, 11, 12)
        self.assertIn("IREN", section11)
        self.assertIn("pf:RUN-1:IREN", section11)
        self.assertIn("starter position only", section11)

    def test_timing_setup_per_actionable_pick(self):
        rec = _full_actionable("IREN")
        report = render_capital_picks_report([rec], run_id=_RUN, generated_at=_NOW)
        self.assertIn("Technical setup (022C): tts:RUN-1:IREN", report)

    def test_red_team_section(self):
        rec = _full_actionable("IREN")
        report = render_capital_picks_report([rec], run_id=_RUN, generated_at=_NOW)
        section9 = _slice_section(report, 9, 10)
        self.assertIn("IREN", section9)
        self.assertIn("RT-1", section9)
        self.assertIn("power-price spike could compress margin", section9)

    def test_market_theme_context(self):
        report = render_capital_picks_report(
            [], run_id=_RUN, generated_at=_NOW,
            market_theme_context="AI datacenter theme is Broadening; power is the chokepoint.")
        self.assertIn("AI datacenter theme is Broadening", report)

    def test_manual_execution_preview_read_only(self):
        rec = _full_actionable("IREN")
        report = render_capital_picks_report([rec], run_id=_RUN, generated_at=_NOW)
        section12 = _slice_section(report, 12, 13)
        self.assertIn("no order is placed", section12)
        self.assertIn("Execution stays Manual Review", section12)
        self.assertIn("mep:RUN-1:IREN", section12)


# =========================================================================== #
# The trade-affordance / score sweep (the whole point of the slice)           #
# =========================================================================== #
class NoTradeAffordanceTests(unittest.TestCase):
    def _every_report(self):
        """A representative set of reports covering every state + all inputs."""
        recs = [
            _full_actionable("IREN"),
            _simple("prepare_entry", "PPP"),
            _simple("active_diligence", "AAA"),
            _simple("watch", "WWW"),
            _simple("blocked", "BBB"),
        ]
        return [
            render_capital_picks_report([], run_id=_RUN, generated_at=_NOW),
            render_capital_picks_report(recs, run_id=_RUN, generated_at=_NOW,
                                        dq_summary="data quality healthy",
                                        market_theme_context="theme is Broadening"),
            render_capital_picks_report(recs, run_id=_RUN, generated_at=_NOW, mode="production"),
        ]

    def test_no_forbidden_marketing_phrases(self):
        for report in self._every_report():
            low = report.lower()
            for phrase in _FORBIDDEN_PHRASES:
                self.assertNotIn(phrase, low, "forbidden phrase rendered: {0!r}".format(phrase))

    def test_no_bare_buy_sell_submit_trade_verbs(self):
        for report in self._every_report():
            low = report.lower()
            for verb in _FORBIDDEN_VERBS:
                self.assertIsNone(
                    re.search(r"\b{0}\b".format(verb), low),
                    "forbidden trade verb rendered: {0!r}".format(verb))

    def test_order_only_in_no_order_is_placed(self):
        for report in self._every_report():
            occurrences = re.findall(r"\border\b", report.lower())
            allowed = report.lower().count("no order is placed")
            self.assertEqual(len(occurrences), allowed,
                             "the 'order' token appears outside 'no order is placed'")

    def test_no_hidden_score_or_rank(self):
        for report in self._every_report():
            low = report.lower()
            for token in _FORBIDDEN_SCORE_TOKENS:
                self.assertIsNone(
                    re.search(r"\b{0}\b".format(re.escape(token)), low),
                    "forbidden score/rank token rendered: {0!r}".format(token))


# =========================================================================== #
# Determinism, demo==pulse, offline                                           #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_byte_identical_for_same_input(self):
        recs = [_full_actionable("IREN"), _simple("watch", "WWW")]
        a = render_capital_picks_report(recs, run_id=_RUN, generated_at=_NOW,
                                        dq_summary="healthy", market_theme_context="ctx")
        b = render_capital_picks_report(recs, run_id=_RUN, generated_at=_NOW,
                                        dq_summary="healthy", market_theme_context="ctx")
        self.assertEqual(a, b)

    def test_demo_and_default_pulse_byte_identical(self):
        # The producing-run mode (demo vs default pulse) is NEVER rendered -> identical output.
        demo = assess_recommendation(ticker="WWW", run_id=_RUN, intended_state="watch",
                                     now=_NOW, mode="demo", why_now="ctx",
                                     candidate_id="cc:RUN-1:WWW")
        pulse = assess_recommendation(ticker="WWW", run_id=_RUN, intended_state="watch",
                                      now=_NOW, mode="pulse", why_now="ctx",
                                      candidate_id="cc:RUN-1:WWW")
        self.assertNotEqual(demo.mode, pulse.mode)  # the inputs genuinely differ in mode
        report_demo = render_capital_picks_report([demo], run_id=_RUN, generated_at=_NOW)
        report_pulse = render_capital_picks_report([pulse], run_id=_RUN, generated_at=_NOW)
        self.assertEqual(report_demo, report_pulse)

    def test_offline_no_socket(self):
        original = socket.socket
        socket.socket = _boom_socket
        try:
            render_capital_picks_report([_full_actionable()], run_id=_RUN, generated_at=_NOW)
        finally:
            socket.socket = original

    def test_exported_from_package(self):
        self.assertIs(rm.render_capital_picks_report, render_capital_picks_report)
        self.assertEqual(rm.REPORT_TITLE, REPORT_TITLE)
        self.assertEqual(len(rm.SECTION_TITLES), 13)
        self.assertEqual(rm.ALLOWED_NEXT_ACTIONS, ALLOWED_NEXT_ACTIONS)


# --------------------------------------------------------------------------- #
# Test helper: slice a rendered report between section N and section M headers  #
# --------------------------------------------------------------------------- #
def _slice_section(report, start_index, stop_index):
    start = report.find("Section {0}. ".format(start_index))
    if stop_index <= len(SECTION_TITLES):
        stop = report.find("Section {0}. ".format(stop_index))
    else:
        stop = len(report)
    if stop == -1:
        stop = len(report)
    return report[start:stop]


if __name__ == "__main__":
    unittest.main()
