"""IMPLEMENTATION-022D -- the Portfolio Fit / Sizing Guardrail Gate (PortfolioFit).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE -- no network, no scheduler, no broker, no
live endpoint. It proves the portfolio-fit model + verdict that 022B gate 12 consumes, built on the
018A read-only Portfolio Intelligence:

* a recommendation cannot be actionable without a portfolio-fit state (no fit / non-acceptable ->
  gate 12 fails);
* concentration risk REDUCES / BLOCKS (concentration_risk | avoid_due_to_portfolio_risk ->
  acceptable False, sizing reduced / avoid);
* insufficient portfolio data prevents production-grade sizing (insufficient_portfolio_data ->
  acceptable False in production, sizing "watch only");
* the sizing guardrail renders as a LABEL / range only (in the sizing vocab; no number / share /
  dollar);
* NO order / execution control or field is created (no buy / sell / order / submit / rebalance
  token anywhere);
* an acceptable fit with recorded holdings -> acceptable True; absent holdings -> insufficient +
  gap (no invented exposure);
* NO score / rank / numeric field; deterministic; offline kill-switch; AST clean;
* MILESTONE: with BOTH an acceptable 022C technical setup AND an acceptable 022D portfolio fit
  wired into the 022B gates over an otherwise-complete evidence set, a recommendation NOW reaches
  ``actionable_pick_manual_review`` -- and a missing / non-acceptable fit drops it back to
  ``active_diligence``; demo + default pulse byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import unittest
from dataclasses import fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import portfolio_fit as PF
from reality_mesh.capital_candidate import assess_candidate_eligibility
from reality_mesh.portfolio import (
    ConcentrationView,
    HoldingRecord,
    PairCorrelationView,
    PortfolioHoldings,
    RotationAlignmentView,
)
from reality_mesh.portfolio_fit import (
    PORTFOLIO_FIT_STATES,
    SIZING_GUARDRAIL_LABELS,
    PortfolioFit,
    assess_portfolio_fit,
    portfolio_fit_acceptable,
    portfolio_fit_id_for,
)
from reality_mesh.recommendation_gates import evaluate_recommendation
from reality_mesh.technical_timing import (
    assess_technical_timing,
    technical_timing_acceptable,
    technical_timing_id_for,
)

_PF_PY = os.path.join(_SRC, "reality_mesh", "portfolio_fit.py")
_NOW = "2026-07-06T00:00:00Z"

# A recorded holdings statement with one unrelated position (portfolio data is PRESENT).
_HOLDINGS = PortfolioHoldings(
    as_of=_NOW, freshness_label="current",
    positions=(HoldingRecord(ticker="MSFT"),), position_count=1)


def _fit(**overrides):
    kw = dict(ticker="IREN", run_id="RUN-1", now=_NOW, holdings=_HOLDINGS,
              candidate_exposure="minimal", source_mode="source-backed")
    kw.update(overrides)
    return assess_portfolio_fit(kw.pop("ticker"), **kw)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# A clean, fresh, source-backed 022C technical setup (mirrors the 022C suite).
_CLEAN_TECH = dict(
    trend_state="ema_stack_aligned", compression_state="compression_forming",
    breakout_state="breakout_confirmed", volume_state="expanding",
    relative_strength_state="leading",
    support_zone="prior base / rising 21-EMA shelf (zone label)",
    resistance_zone="prior swing-high supply band",
    entry_zone_label="on hold above the breakout shelf",
    invalidation_level_or_condition="decisive close back under the base",
    risk_reward_label="favorable")


def _acceptable_setup():
    return assess_technical_timing("IREN", run_id="RUN-1", now=_NOW,
                                   technical_evidence=dict(_CLEAN_TECH),
                                   data_freshness="fresh", source_mode="source-backed")


def _eligible_candidate(mode="pulse"):
    return assess_candidate_eligibility(
        ticker="IREN", run_id="RUN-1", reality_signal_refs=("sig-1",),
        opportunity_hypothesis_ref="hyp-1", investment_diligence_ref="THS-1",
        trust_data_quality_state="healthy", mode=mode, now=_NOW)


def _full_inputs(**overrides):
    base = dict(
        run_id="RUN-1", ticker="IREN", now=_NOW, company_name="IREN Ltd",
        candidate=_eligible_candidate(),
        data_quality_ref="DQ-1", data_quality_state="healthy", source_freshness="fresh",
        corroboration_sources=(("sec:1", "primary", "sec_filing"),
                               ("fmp:2", "convenience", "fmp")),
        theme_pulse_state="Igniting", bottleneck_exposure_refs=("bn-hbm",),
        company_evidence_refs=(("sec:1", "primary", "sec_filing"),),
        investment_diligence_ref="THS-1", diligence_complete=True,
        forward_scenario_ref="FWD-1", red_team_ref="RT-1", unresolved_thesis_killer=False,
        technical_timing_ref="TT-1", technical_timing_acceptable=True,
        portfolio_fit_ref="PF-1", portfolio_fit_acceptable=True,
        sizing_guardrail="starter position only (qualitative range)",
        invalidation_conditions=("thesis broken if HBM demand rolls over",),
        exit_watch_conditions=("exit watch if margin compresses",),
    )
    base.update(overrides)
    return base


# =========================================================================== #
# Vocabulary + model shape                                                      #
# =========================================================================== #
class VocabularyTests(unittest.TestCase):
    def test_closed_fit_states(self):
        self.assertEqual(PORTFOLIO_FIT_STATES, (
            "acceptable", "concentration_risk", "liquidity_risk", "correlation_risk",
            "insufficient_portfolio_data", "avoid_due_to_portfolio_risk"))

    def test_closed_sizing_vocab(self):
        self.assertEqual(SIZING_GUARDRAIL_LABELS, (
            "starter position only", "small position", "normal risk budget",
            "reduced due to volatility", "avoid due to concentration", "watch only"))

    def test_fit_state_must_be_in_vocab(self):
        with self.assertRaises(ValueError):
            PortfolioFit(ticker="T", run_id="R", generated_at=_NOW, fit_state="buy_it",
                         fit_reason="x", sizing_guardrail_label="watch only",
                         data_availability="present")

    def test_sizing_must_be_in_vocab(self):
        with self.assertRaises(ValueError):
            PortfolioFit(ticker="T", run_id="R", generated_at=_NOW, fit_state="acceptable",
                         fit_reason="x", sizing_guardrail_label="buy 100 shares",
                         data_availability="present")

    def test_required_fields_non_empty(self):
        for missing in ("ticker", "run_id", "generated_at", "fit_state", "fit_reason",
                        "sizing_guardrail_label", "data_availability"):
            kw = dict(ticker="T", run_id="R", generated_at=_NOW, fit_state="acceptable",
                      fit_reason="x", sizing_guardrail_label="normal risk budget",
                      data_availability="present")
            kw[missing] = ""
            with self.assertRaises(ValueError, msg=missing):
                PortfolioFit(**kw)

    def test_risk_labels_are_reused_018_bands(self):
        # A risk label that is not an 018 band is rejected.
        with self.assertRaises(ValueError):
            PortfolioFit(ticker="T", run_id="R", generated_at=_NOW, fit_state="acceptable",
                         fit_reason="x", sizing_guardrail_label="normal risk budget",
                         data_availability="present", concentration_risk_label="very_high")

    def test_no_numeric_size_field_accepted(self):
        # A numeric value on any field is refused -- sizing is a LABEL, never a share count.
        with self.assertRaises(ValueError):
            PortfolioFit(ticker="T", run_id="R", generated_at=_NOW, fit_state="acceptable",
                         fit_reason="x", sizing_guardrail_label="normal risk budget",
                         data_availability="present", data_gaps=(100,))  # type: ignore[arg-type]

    def test_bad_data_availability_and_source_mode_rejected(self):
        with self.assertRaises(ValueError):
            PortfolioFit(ticker="T", run_id="R", generated_at=_NOW, fit_state="acceptable",
                         fit_reason="x", sizing_guardrail_label="normal risk budget",
                         data_availability="maybe")
        with self.assertRaises(ValueError):
            PortfolioFit(ticker="T", run_id="R", generated_at=_NOW, fit_state="acceptable",
                         fit_reason="x", sizing_guardrail_label="normal risk budget",
                         data_availability="present", source_mode="live_wire")


# =========================================================================== #
# assess derivation -- REUSE the 018 bands, never fabricate exposure             #
# =========================================================================== #
class AssessDerivationTests(unittest.TestCase):
    def test_no_holdings_is_insufficient_with_gap_no_invented_exposure(self):
        f = assess_portfolio_fit("IREN", run_id="RUN-1", now=_NOW)  # no holdings, no store
        self.assertEqual(f.fit_state, "insufficient_portfolio_data")
        self.assertEqual(f.data_availability, "insufficient")
        self.assertEqual(f.sizing_guardrail_label, "watch only")
        self.assertTrue(f.data_gaps)
        # No exposure was invented: every risk band is the honest unknown.
        self.assertEqual(f.concentration_risk_label, "unknown")
        self.assertEqual(f.risk_budget_label, "unknown")

    def test_clean_fit_with_recorded_holdings_is_acceptable(self):
        f = _fit()
        self.assertEqual(f.fit_state, "acceptable")
        self.assertTrue(f.is_acceptable_fit)
        self.assertTrue(f.has_portfolio_data)
        self.assertIn(f.sizing_guardrail_label,
                      ("starter position only", "small position", "normal risk budget"))

    def test_dominant_concentration_is_avoid(self):
        f = _fit(candidate_exposure="dominant")
        self.assertEqual(f.fit_state, "avoid_due_to_portfolio_risk")
        self.assertEqual(f.sizing_guardrail_label, "avoid due to concentration")
        self.assertEqual(f.concentration_risk_label, "dominant")

    def test_elevated_concentration_is_concentration_risk(self):
        f = _fit(candidate_exposure="elevated")
        self.assertEqual(f.fit_state, "concentration_risk")
        self.assertIn(f.sizing_guardrail_label, PF._REDUCE_OR_AVOID)
        self.assertEqual(f.concentration_risk_label, "elevated")

    def test_thin_liquidity_is_liquidity_risk(self):
        f = _fit(liquidity_signal="thin trading, hard to exit")
        self.assertEqual(f.fit_state, "liquidity_risk")
        self.assertEqual(f.liquidity_risk_label, "elevated")
        self.assertIn(f.sizing_guardrail_label, SIZING_GUARDRAIL_LABELS)

    def test_co_exposure_is_correlation_risk(self):
        corr = (PairCorrelationView(ticker_a="IREN", ticker_b="MSFT",
                                    correlation_label="co_exposed"),)
        f = _fit(correlation=corr)
        self.assertEqual(f.fit_state, "correlation_risk")
        self.assertEqual(f.correlation_risk_label, "elevated")
        self.assertIn(f.sizing_guardrail_label, PF._REDUCE_OR_AVOID)

    def test_rotation_against_is_correlation_risk(self):
        rot = (RotationAlignmentView(ticker="IREN", theme_id="ai", theme_state="Exhausting",
                                     alignment_label="against"),)
        f = _fit(rotation=rot)
        self.assertEqual(f.fit_state, "correlation_risk")

    def test_concentration_from_018_concentration_view_reused(self):
        # A real 018 ConcentrationView for the candidate -> its band is REUSED verbatim.
        conc = (ConcentrationView(ticker="IREN", weight_band="dominant", basis="b"),)
        f = assess_portfolio_fit("IREN", run_id="RUN-1", now=_NOW, holdings=_HOLDINGS,
                                 concentration=conc, source_mode="source-backed")
        self.assertEqual(f.fit_state, "avoid_due_to_portfolio_risk")
        self.assertEqual(f.concentration_risk_label, "dominant")

    def test_concentration_dominates_liquidity_and_correlation(self):
        corr = (PairCorrelationView(ticker_a="IREN", ticker_b="MSFT",
                                    correlation_label="co_exposed"),)
        f = _fit(candidate_exposure="dominant", liquidity_signal="thin", correlation=corr)
        self.assertEqual(f.fit_state, "avoid_due_to_portfolio_risk")

    def test_moderate_concentration_is_acceptable_starter(self):
        f = _fit(candidate_exposure="moderate")
        self.assertEqual(f.fit_state, "acceptable")
        self.assertEqual(f.sizing_guardrail_label, "starter position only")


# =========================================================================== #
# portfolio_fit_acceptable -- the verdict gate 12 consumes                       #
# =========================================================================== #
class AcceptableTests(unittest.TestCase):
    def test_clean_fit_is_acceptable(self):
        ok, reason = portfolio_fit_acceptable(_fit())
        self.assertTrue(ok)
        self.assertTrue(reason.strip())

    def test_clean_fit_acceptable_in_production_when_source_backed(self):
        ok, _ = portfolio_fit_acceptable(_fit(), production=True)
        self.assertTrue(ok)

    def test_no_fit_is_not_acceptable(self):
        ok, reason = portfolio_fit_acceptable(None)
        self.assertFalse(ok)
        self.assertIn("without", reason.lower())

    def test_concentration_risk_is_not_acceptable(self):
        ok, reason = portfolio_fit_acceptable(_fit(candidate_exposure="elevated"))
        self.assertFalse(ok)
        self.assertIn("concentration_risk", reason)

    def test_avoid_due_to_portfolio_risk_is_not_acceptable(self):
        ok, reason = portfolio_fit_acceptable(_fit(candidate_exposure="dominant"))
        self.assertFalse(ok)
        self.assertIn("avoid_due_to_portfolio_risk", reason)

    def test_liquidity_risk_is_not_acceptable(self):
        ok, reason = portfolio_fit_acceptable(_fit(liquidity_signal="thin"))
        self.assertFalse(ok)
        self.assertIn("liquidity_risk", reason)

    def test_correlation_risk_is_not_acceptable(self):
        corr = (PairCorrelationView(ticker_a="IREN", ticker_b="MSFT",
                                    correlation_label="co_exposed"),)
        ok, reason = portfolio_fit_acceptable(_fit(correlation=corr))
        self.assertFalse(ok)
        self.assertIn("correlation_risk", reason)

    def test_insufficient_data_prevents_production_sizing(self):
        f = assess_portfolio_fit("IREN", run_id="RUN-1", now=_NOW)
        ok, reason = portfolio_fit_acceptable(f, production=True)
        self.assertFalse(ok)
        self.assertIn("insufficient_portfolio_data", reason)
        self.assertEqual(f.sizing_guardrail_label, "watch only")

    def test_insufficient_data_not_acceptable_even_in_shadow(self):
        f = assess_portfolio_fit("IREN", run_id="RUN-1", now=_NOW)
        ok, _ = portfolio_fit_acceptable(f, production=False)
        self.assertFalse(ok)

    def test_fixture_fit_not_production_acceptable_but_ok_in_shadow(self):
        fixture = _fit(source_mode="fixture")
        self.assertEqual(fixture.fit_state, "acceptable")
        ok_shadow, _ = portfolio_fit_acceptable(fixture, production=False)
        self.assertTrue(ok_shadow)
        ok_prod, reason = portfolio_fit_acceptable(fixture, production=True)
        self.assertFalse(ok_prod)
        self.assertIn("fixture", reason.lower())


# =========================================================================== #
# The sizing guardrail is a LABEL / range only -- never a number                #
# =========================================================================== #
class SizingLabelOnlyTests(unittest.TestCase):
    def test_every_state_sizing_is_a_closed_label(self):
        cases = (
            _fit(),
            _fit(candidate_exposure="elevated"),
            _fit(candidate_exposure="dominant"),
            _fit(liquidity_signal="thin"),
            assess_portfolio_fit("IREN", run_id="RUN-1", now=_NOW),
        )
        for f in cases:
            self.assertIn(f.sizing_guardrail_label, SIZING_GUARDRAIL_LABELS)

    def test_sizing_label_carries_no_number_or_share_or_dollar(self):
        for label in SIZING_GUARDRAIL_LABELS:
            self.assertFalse(any(ch.isdigit() for ch in label), label)
            low = label.lower()
            for tok in ("share", "$", "usd", "dollar", "%", "percent", "shares", "units"):
                self.assertNotIn(tok, low, label)

    def test_no_order_or_execution_token_in_sizing_vocab(self):
        for label in SIZING_GUARDRAIL_LABELS:
            low = label.lower()
            for tok in ("buy", "sell", "order", "submit", "rebalance", "execute", "broker"):
                self.assertNotIn(tok, low, label)


# =========================================================================== #
# No score / rank / rating / numeric / order field anywhere                      #
# =========================================================================== #
class NoScoreOrOrderFieldTests(unittest.TestCase):
    def test_assert_no_trade_fields_clean(self):
        rm.assert_no_trade_fields(PortfolioFit)

    def test_no_forbidden_token_in_any_field_name(self):
        for f in fields(PortfolioFit):
            low = f.name.lower()
            for tok in ("buy", "sell", "order", "submit", "rebalance", "broker", "trade",
                        "score", "rank", "rating", "target", "shares", "quantity", "amount",
                        "notional", "dollar"):
                self.assertNotIn(tok, low, f.name)

    def test_fit_carries_no_numeric_field(self):
        f = _fit()
        for field_obj in fields(PortfolioFit):
            value = getattr(f, field_obj.name)
            self.assertNotIsInstance(value, (int, float), field_obj.name)


# =========================================================================== #
# Determinism + deterministic id                                                #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_assessment_is_deterministic(self):
        self.assertEqual(_fit(), _fit())

    def test_insufficient_is_deterministic(self):
        a = assess_portfolio_fit("IREN", run_id="RUN-1", now=_NOW)
        b = assess_portfolio_fit("IREN", run_id="RUN-1", now=_NOW)
        self.assertEqual(a, b)

    def test_deterministic_id(self):
        self.assertEqual(portfolio_fit_id_for("RUN-1", "iren"), "pf:RUN-1:IREN")


# =========================================================================== #
# Wiring into 022B gate 12                                                       #
# =========================================================================== #
class GateTwelveWiringTests(unittest.TestCase):
    def test_no_fit_makes_gate_12_fail_recommendation_not_actionable(self):
        outcome, rec = evaluate_recommendation(**_full_inputs(
            portfolio_fit_ref="", portfolio_fit_acceptable=False))
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertFalse(by_id["portfolio_fit_acceptable"].passed)
        self.assertFalse(outcome.is_actionable)
        self.assertFalse(rec.is_actionable_pick)

    def test_concentration_risk_fit_never_unlocks_gate_12(self):
        fit = _fit(candidate_exposure="dominant")
        ok, _ = portfolio_fit_acceptable(fit, production=True)
        self.assertFalse(ok)
        outcome, rec = evaluate_recommendation(**_full_inputs(
            portfolio_fit_ref=portfolio_fit_id_for("RUN-1", "IREN"),
            portfolio_fit_acceptable=ok))
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertFalse(by_id["portfolio_fit_acceptable"].passed)
        self.assertFalse(rec.is_actionable_pick)


# =========================================================================== #
# MILESTONE -- 022C + 022D wired -> actionable REACHABLE with complete evidence  #
# =========================================================================== #
class MilestoneTests(unittest.TestCase):
    def _acceptable_fit(self):
        fit = _fit()
        ok, _ = portfolio_fit_acceptable(fit, production=True)
        self.assertTrue(ok)
        return fit

    def test_both_022c_and_022d_acceptable_reach_actionable(self):
        setup = _acceptable_setup()
        tok, _ = technical_timing_acceptable(setup, production=True)
        self.assertTrue(tok)
        fit = self._acceptable_fit()
        pok, _ = portfolio_fit_acceptable(fit, production=True)
        outcome, rec = evaluate_recommendation(**_full_inputs(
            technical_timing_ref=technical_timing_id_for("RUN-1", "IREN"),
            technical_timing_acceptable=tok,
            portfolio_fit_ref=portfolio_fit_id_for("RUN-1", "IREN"),
            portfolio_fit_acceptable=pok,
            sizing_guardrail=fit.sizing_guardrail_label))
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertTrue(by_id["technical_timing_acceptable"].passed)
        self.assertTrue(by_id["portfolio_fit_acceptable"].passed)
        self.assertEqual(outcome.state, "actionable_pick_manual_review")
        self.assertTrue(rec.is_actionable_pick)

    def test_missing_portfolio_fit_drops_back_to_active_diligence(self):
        setup = _acceptable_setup()
        tok, _ = technical_timing_acceptable(setup, production=True)
        outcome, rec = evaluate_recommendation(**_full_inputs(
            technical_timing_ref=technical_timing_id_for("RUN-1", "IREN"),
            technical_timing_acceptable=tok,
            portfolio_fit_ref="", portfolio_fit_acceptable=False))
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertTrue(by_id["technical_timing_acceptable"].passed)
        self.assertFalse(by_id["portfolio_fit_acceptable"].passed)
        self.assertEqual(outcome.state, "active_diligence")
        self.assertFalse(rec.is_actionable_pick)

    def test_non_acceptable_portfolio_fit_drops_back_to_active_diligence(self):
        setup = _acceptable_setup()
        tok, _ = technical_timing_acceptable(setup, production=True)
        fit = _fit(candidate_exposure="elevated")
        pok, _ = portfolio_fit_acceptable(fit, production=True)
        self.assertFalse(pok)
        outcome, rec = evaluate_recommendation(**_full_inputs(
            technical_timing_ref=technical_timing_id_for("RUN-1", "IREN"),
            technical_timing_acceptable=tok,
            portfolio_fit_ref=portfolio_fit_id_for("RUN-1", "IREN"),
            portfolio_fit_acceptable=pok))
        self.assertEqual(outcome.state, "active_diligence")
        self.assertFalse(rec.is_actionable_pick)


# =========================================================================== #
# Guardrails -- AST clean, offline kill-switch, demo byte-identical             #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "ftplib", "smtplib", "selenium", "scrapy", "websocket", "websockets", "pycurl"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "signal"}

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_imports_no_network_scheduler_broker(self):
        tree = ast.parse(self._read(_PF_PY))
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.append((node.module or "").split(".")[0])
        for m in mods:
            self.assertNotIn(m, self._NET, "imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "imports forbidden {0}".format(m))

    def test_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_PF_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "defines {0}".format(node.name))

    def test_source_has_no_broker_or_execution_token(self):
        blob = self._read(_PF_PY).lower()
        for tok in ("place_order", "submit_order", "broker.submit", "execute_trade",
                    "rebalance(", "time.time(", "datetime.now("):
            self.assertNotIn(tok, blob, "forbidden token {0}".format(tok))

    def test_assessment_is_offline_under_socket_kill_switch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            f = _fit()
            ok, _ = portfolio_fit_acceptable(f, production=True)
        finally:
            socket.socket = real
        self.assertTrue(f.is_acceptable_fit)
        self.assertTrue(ok)

    def test_demo_pulse_is_byte_identical(self):
        a = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        b = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        self.assertEqual(tuple(s.signal_id for s in a.signals),
                         tuple(s.signal_id for s in b.signals))
        self.assertEqual(tuple(f.finding_id for f in a.findings),
                         tuple(f.finding_id for f in b.findings))


if __name__ == "__main__":
    unittest.main()
