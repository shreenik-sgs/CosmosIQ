"""IMPLEMENTATION-022C -- the Timing / Technical Setup Gate (TechnicalTimingSetup).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE -- no network, no scheduler, no broker, no
live endpoint. It proves the timing model + verdict that 022B gate 11 consumes:

* a recommendation cannot be actionable without a TechnicalTimingSetup (no setup -> gate 11 fails);
* ``extended_chase_risk`` can never be actionable (blocks / forces a risk warning);
* ``breakdown_exit_review`` routes to exit review, never actionable;
* a setup REQUIRES freshness (a stale actionable-looking setup is not acceptable);
* a fixture-only setup can never be PRODUCTION-actionable (but is fine in shadow / non-production);
* a clean fresh source-backed actionable setup IS acceptable;
* absent evidence -> ``not_ready`` + a visible gap, NEVER an invented level;
* labels + reasons ONLY -- NO score / rank / rating / numeric field; deterministic; AST clean;
  offline kill-switch; demo + default pulse byte-identical;
* wiring the full-evidence gate path with an acceptable timing setup makes gate 11 PASS while
  gate 12 (portfolio, 022D) still blocks actionable -- proving 022C alone does not unlock it.
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
from reality_mesh import technical_timing as TT
from reality_mesh.capital_candidate import assess_candidate_eligibility
from reality_mesh.recommendation_gates import evaluate_recommendation
from reality_mesh.technical_timing import (
    TECHNICAL_SETUP_STATES,
    TechnicalTimingSetup,
    assess_technical_timing,
    technical_timing_acceptable,
    technical_timing_id_for,
)

_TT_PY = os.path.join(_SRC, "reality_mesh", "technical_timing.py")
_NOW = "2026-07-06T00:00:00Z"

# A clean, constructive, non-extended technical evidence set WITH explicit zones.
_CLEAN_EVIDENCE = dict(
    trend_state="ema_stack_aligned",
    compression_state="compression_forming",
    breakout_state="breakout_confirmed",
    volume_state="expanding",
    relative_strength_state="leading",
    support_zone="prior base / rising 21-EMA shelf (zone label, not a precise target)",
    resistance_zone="prior swing-high supply band",
    entry_zone_label="on hold above the breakout shelf",
    invalidation_level_or_condition="thesis timing broken on a decisive close back under the base",
    risk_reward_label="favorable",
)

# Evidence that is over-extended above trend.
_EXTENDED_EVIDENCE = dict(trend_state="ema_stack_aligned", overextended=True)

# Evidence that has broken down.
_BREAKDOWN_EVIDENCE = dict(trend_state="ema_stack_broken", breakout_state="breakout_failed",
                          breakdown=True)


def _clean_setup(**overrides):
    kw = dict(ticker="IREN", run_id="RUN-1", now=_NOW, technical_evidence=dict(_CLEAN_EVIDENCE),
              data_freshness="fresh", source_mode="source-backed")
    kw.update(overrides)
    return assess_technical_timing(kw.pop("ticker"), **kw)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# --------------------------------------------------------------------------- #
# Shared full-evidence recommendation input (mirrors the 022B suite)            #
# --------------------------------------------------------------------------- #
def _eligible_candidate(mode="pulse", ticker="IREN", run_id="RUN-1"):
    return assess_candidate_eligibility(
        ticker=ticker, run_id=run_id, reality_signal_refs=("sig-1",),
        opportunity_hypothesis_ref="hyp-1", investment_diligence_ref="THS-1",
        trust_data_quality_state="healthy", mode=mode, now=_NOW)


def _full_inputs(**overrides):
    base = dict(
        run_id="RUN-1", ticker="IREN", now=_NOW, company_name="IREN Ltd",
        candidate=_eligible_candidate(),
        data_quality_ref="DQ-1", data_quality_state="healthy",
        source_freshness="fresh",
        corroboration_sources=(("sec:1", "primary", "sec_filing"),
                               ("fmp:2", "convenience", "fmp")),
        theme_pulse_state="Igniting",
        bottleneck_exposure_refs=("bn-hbm",),
        company_evidence_refs=(("sec:1", "primary", "sec_filing"),),
        investment_diligence_ref="THS-1", diligence_complete=True,
        forward_scenario_ref="FWD-1",
        red_team_ref="RT-1", unresolved_thesis_killer=False,
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
    def test_closed_setup_states(self):
        self.assertEqual(TECHNICAL_SETUP_STATES, (
            "not_ready", "watch_for_setup", "setup_forming",
            "actionable_setup_manual_review", "extended_chase_risk", "breakdown_exit_review"))

    def test_setup_state_must_be_in_vocab(self):
        with self.assertRaises(ValueError):
            TechnicalTimingSetup(ticker="T", run_id="R", generated_at=_NOW,
                                 setup_state="buy_now", setup_reason="x")

    def test_required_fields_non_empty(self):
        for missing in ("ticker", "run_id", "generated_at", "setup_state", "setup_reason"):
            kw = dict(ticker="T", run_id="R", generated_at=_NOW,
                      setup_state="not_ready", setup_reason="x")
            kw[missing] = ""
            with self.assertRaises(ValueError, msg=missing):
                TechnicalTimingSetup(**kw)

    def test_risk_reward_is_a_label_not_a_number(self):
        with self.assertRaises(ValueError):
            TechnicalTimingSetup(ticker="T", run_id="R", generated_at=_NOW,
                                 setup_state="not_ready", setup_reason="x",
                                 risk_reward_label="2.5")

    def test_bad_source_mode_and_freshness_rejected(self):
        with self.assertRaises(ValueError):
            TechnicalTimingSetup(ticker="T", run_id="R", generated_at=_NOW,
                                 setup_state="not_ready", setup_reason="x", source_mode="live_wire")
        with self.assertRaises(ValueError):
            TechnicalTimingSetup(ticker="T", run_id="R", generated_at=_NOW,
                                 setup_state="not_ready", setup_reason="x",
                                 data_freshness="brand_new")


# =========================================================================== #
# assess derivation                                                             #
# =========================================================================== #
class AssessDerivationTests(unittest.TestCase):
    def test_clean_fresh_evidence_is_actionable_setup(self):
        s = _clean_setup()
        self.assertEqual(s.setup_state, "actionable_setup_manual_review")
        self.assertTrue(s.is_actionable_setup)
        self.assertTrue(s.support_zone.strip() and s.entry_zone_label.strip())
        self.assertTrue(s.invalidation_level_or_condition.strip())

    def test_extended_move_is_chase_risk_never_actionable(self):
        s = _clean_setup(technical_evidence=dict(_EXTENDED_EVIDENCE))
        self.assertEqual(s.setup_state, "extended_chase_risk")
        self.assertFalse(s.is_actionable_setup)
        self.assertTrue(s.requires_risk_warning)
        self.assertIn("risk warning", s.setup_reason.lower())

    def test_breakdown_routes_to_exit_review(self):
        s = _clean_setup(technical_evidence=dict(_BREAKDOWN_EVIDENCE))
        self.assertEqual(s.setup_state, "breakdown_exit_review")
        self.assertFalse(s.is_actionable_setup)
        self.assertTrue(s.routes_to_exit_review)
        self.assertIn("exit review", s.setup_reason.lower())

    def test_breakdown_dominates_when_also_extended(self):
        s = _clean_setup(technical_evidence=dict(
            trend_state="ema_stack_broken", breakdown=True, overextended=True))
        self.assertEqual(s.setup_state, "breakdown_exit_review")

    def test_constructive_but_untriggered_is_forming(self):
        s = _clean_setup(technical_evidence=dict(
            trend_state="ema_stack_aligned", compression_state="compression_forming"))
        self.assertEqual(s.setup_state, "setup_forming")

    def test_absent_evidence_is_not_ready_with_gap_no_invented_level(self):
        s = assess_technical_timing("IREN", run_id="RUN-1", now=_NOW, technical_evidence=None)
        self.assertEqual(s.setup_state, "not_ready")
        self.assertTrue(s.data_gaps)
        # NO level / zone was invented from nothing.
        self.assertEqual(s.support_zone, "")
        self.assertEqual(s.resistance_zone, "")
        self.assertEqual(s.entry_zone_label, "")
        self.assertEqual(s.invalidation_level_or_condition, "")

    def test_empty_evidence_sequence_is_not_ready(self):
        s = assess_technical_timing("IREN", run_id="RUN-1", now=_NOW, technical_evidence=())
        self.assertEqual(s.setup_state, "not_ready")
        self.assertTrue(s.data_gaps)

    def test_strong_structure_missing_zones_downgrades_not_fabricates(self):
        # actionable-quality trend/breakout/volume but NO support/entry/invalidation supplied.
        s = _clean_setup(technical_evidence=dict(
            trend_state="ema_stack_aligned", breakout_state="breakout_confirmed",
            volume_state="expanding", relative_strength_state="leading"))
        self.assertEqual(s.setup_state, "setup_forming")
        self.assertFalse(s.is_actionable_setup)
        self.assertTrue(any("never fabricated" in g for g in s.data_gaps))
        self.assertEqual(s.support_zone, "")          # not invented
        self.assertEqual(s.entry_zone_label, "")

    def test_derives_from_014d_findings_without_inventing_zones(self):
        # A real 014D TechnicalRegimeAgent finding set (from the local price-history sensor)
        # carries chart-state labels but no zones -> a non-fabricated, non-actionable setup.
        agent = rm.TechnicalRegimeAgent()
        event = rm.RealityEvent(
            event_id="ev.tech.IREN", discipline="technical_regime", source_id="local:1",
            source_authority="convenience", affected_companies=("IREN",),
            freshness_label="fresh", confidence_label="moderate",
            numeric_values=(("ema8", 10.0, "usd"), ("ema21", 9.0, "usd"),
                            ("ema50", 8.0, "usd"), ("ema200", 7.0, "usd")))
        findings = agent.run(None, (event,))
        self.assertTrue(findings)
        s = assess_technical_timing("IREN", run_id="RUN-1", now=_NOW,
                                    technical_evidence=findings, source_mode="local-file")
        self.assertIn(s.setup_state, TECHNICAL_SETUP_STATES)
        self.assertFalse(s.is_actionable_setup)       # no zones from a finding -> never actionable
        self.assertEqual(s.entry_zone_label, "")


# =========================================================================== #
# technical_timing_acceptable -- the verdict gate 11 consumes                    #
# =========================================================================== #
class AcceptableTests(unittest.TestCase):
    def test_clean_fresh_source_backed_actionable_is_acceptable(self):
        ok, reason = technical_timing_acceptable(_clean_setup())
        self.assertTrue(ok)
        self.assertTrue(reason.strip())

    def test_clean_actionable_acceptable_in_production_when_source_backed(self):
        ok, _ = technical_timing_acceptable(_clean_setup(), production=True)
        self.assertTrue(ok)

    def test_no_setup_is_not_acceptable(self):
        ok, reason = technical_timing_acceptable(None)
        self.assertFalse(ok)
        self.assertIn("without", reason.lower())

    def test_extended_chase_risk_is_not_acceptable(self):
        ok, reason = technical_timing_acceptable(
            _clean_setup(technical_evidence=dict(_EXTENDED_EVIDENCE)))
        self.assertFalse(ok)
        self.assertIn("extended_chase_risk", reason)

    def test_breakdown_is_not_acceptable(self):
        ok, reason = technical_timing_acceptable(
            _clean_setup(technical_evidence=dict(_BREAKDOWN_EVIDENCE)))
        self.assertFalse(ok)
        self.assertIn("breakdown_exit_review", reason)

    def test_stale_actionable_looking_setup_is_not_acceptable(self):
        stale = _clean_setup(data_freshness="stale")
        self.assertEqual(stale.setup_state, "actionable_setup_manual_review")  # structure ok
        ok, reason = technical_timing_acceptable(stale)
        self.assertFalse(ok)
        self.assertIn("fresh", reason.lower())

    def test_missing_freshness_actionable_setup_is_not_acceptable(self):
        s = assess_technical_timing("IREN", run_id="RUN-1", now=_NOW,
                                    technical_evidence=dict(_CLEAN_EVIDENCE),
                                    source_mode="source-backed")  # no data_freshness
        ok, _ = technical_timing_acceptable(s)
        self.assertFalse(ok)

    def test_fixture_setup_not_production_acceptable_but_ok_in_shadow(self):
        fixture = _clean_setup(source_mode="fixture")
        self.assertEqual(fixture.setup_state, "actionable_setup_manual_review")
        # shadow / non-production: a fixture actionable setup is acceptable.
        ok_shadow, _ = technical_timing_acceptable(fixture, production=False)
        self.assertTrue(ok_shadow)
        # production: a fixture-sourced setup can NEVER be actionable.
        ok_prod, reason = technical_timing_acceptable(fixture, production=True)
        self.assertFalse(ok_prod)
        self.assertIn("fixture", reason.lower())

    def test_not_ready_absent_evidence_is_not_acceptable(self):
        s = assess_technical_timing("IREN", run_id="RUN-1", now=_NOW, technical_evidence=None)
        ok, _ = technical_timing_acceptable(s)
        self.assertFalse(ok)


# =========================================================================== #
# Wiring into 022B gate 11 (gate 11 passes; gate 12 / 022D still blocks)         #
# =========================================================================== #
class GateElevenWiringTests(unittest.TestCase):
    def _acceptable_setup(self):
        setup = _clean_setup()
        ok, _ = technical_timing_acceptable(setup, production=True)
        self.assertTrue(ok)
        return setup

    def test_no_setup_makes_gate_11_fail_recommendation_not_actionable(self):
        # No acceptable technical setup -> gate 11 fails -> never actionable.
        outcome, rec = evaluate_recommendation(**_full_inputs(
            technical_timing_ref="", technical_timing_acceptable=False))
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertFalse(by_id["technical_timing_acceptable"].passed)
        self.assertFalse(outcome.is_actionable)
        self.assertFalse(rec.is_actionable_pick)

    def test_acceptable_setup_passes_gate_11_but_gate_12_still_blocks(self):
        setup = self._acceptable_setup()
        ok, _ = technical_timing_acceptable(setup, production=True)
        # Feed gate 11 the acceptable verdict + ref, but withhold 022D portfolio fit.
        outcome, rec = evaluate_recommendation(**_full_inputs(
            technical_timing_ref=technical_timing_id_for("RUN-1", "IREN"),
            technical_timing_acceptable=ok,
            portfolio_fit_ref="", portfolio_fit_acceptable=False))
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertTrue(by_id["technical_timing_acceptable"].passed)     # gate 11 now passes
        self.assertFalse(by_id["portfolio_fit_acceptable"].passed)       # gate 12 still blocks
        self.assertEqual(outcome.state, "active_diligence")
        self.assertFalse(rec.is_actionable_pick)                         # 022C alone != actionable

    def test_extended_setup_never_unlocks_gate_11(self):
        extended = _clean_setup(technical_evidence=dict(_EXTENDED_EVIDENCE))
        ok, _ = technical_timing_acceptable(extended, production=True)
        outcome, rec = evaluate_recommendation(**_full_inputs(
            technical_timing_ref=technical_timing_id_for("RUN-1", "IREN"),
            technical_timing_acceptable=ok))
        by_id = {g.gate_id: g for g in outcome.gate_results}
        self.assertFalse(by_id["technical_timing_acceptable"].passed)
        self.assertFalse(rec.is_actionable_pick)


# =========================================================================== #
# No score / rank / rating / numeric field anywhere                             #
# =========================================================================== #
class NoScoreFieldTests(unittest.TestCase):
    def test_assert_no_trade_fields_clean(self):
        rm.assert_no_trade_fields(TechnicalTimingSetup)

    def test_no_forbidden_token_in_any_field_name(self):
        for f in fields(TechnicalTimingSetup):
            low = f.name.lower()
            for tok in ("buy", "sell", "order", "submit", "broker", "trade",
                        "score", "rank", "rating", "target", "investab", "alpha"):
                self.assertNotIn(tok, low, f.name)

    def test_setup_carries_no_numeric_verdict(self):
        s = _clean_setup()
        self.assertIsInstance(s.setup_state, str)
        self.assertIsInstance(s.risk_reward_label, str)
        self.assertIn(s.risk_reward_label, ("favorable", "balanced", "poor", "unknown", ""))


# =========================================================================== #
# Determinism                                                                   #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_assessment_is_deterministic(self):
        self.assertEqual(_clean_setup(), _clean_setup())

    def test_absent_evidence_deterministic(self):
        a = assess_technical_timing("IREN", run_id="RUN-1", now=_NOW, technical_evidence=None)
        b = assess_technical_timing("IREN", run_id="RUN-1", now=_NOW, technical_evidence=None)
        self.assertEqual(a, b)

    def test_deterministic_id(self):
        self.assertEqual(technical_timing_id_for("RUN-1", "iren"), "tts:RUN-1:IREN")


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
        tree = ast.parse(self._read(_TT_PY))
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
        tree = ast.parse(self._read(_TT_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "defines {0}".format(node.name))

    def test_source_has_no_broker_or_execution_token(self):
        blob = self._read(_TT_PY).lower()
        for tok in ("place_order", "submit_order", "broker.submit", "execute_trade",
                    "time.time(", "datetime.now("):
            self.assertNotIn(tok, blob, "forbidden token {0}".format(tok))

    def test_assessment_is_offline_under_socket_kill_switch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            s = _clean_setup()
            ok, _ = technical_timing_acceptable(s, production=True)
        finally:
            socket.socket = real
        self.assertTrue(s.is_actionable_setup)
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
