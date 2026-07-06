"""IMPLEMENTATION-022A -- typed CapitalRecommendation contract (MODEL slice).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE -- no network, no scheduler, no broker, no
live endpoint. It proves the one invariant that keeps a stock-pick-for-MANUAL-REVIEW honest: a
``CapitalRecommendation`` is a TYPED object that CANNOT be ``actionable_pick_manual_review`` without
its FULL ref set (mirroring 019B ``CapitalCandidate.eligible``), that carries only qualitative
labels (never a score / rank / rating / trade field), that REJECTS marketing/trade labels, and
that names an EXACT reason whenever it is ``blocked``.

The gates themselves (022B), timing (022C) and portfolio-fit (022D) are OUT of scope here -- this
is the model + its structural invariants only.
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
from reality_mesh import recommendation as REC
from reality_mesh.recommendation import (
    FORBIDDEN_RECOMMENDATION_LABELS,
    RECOMMENDATION_LABELS,
    RECOMMENDATION_STATES,
    RECOMMENDATION_STATE_LABELS,
    CapitalRecommendation,
    assess_recommendation,
    recommendation_id_for,
)

_REC_PY = os.path.join(_SRC, "reality_mesh", "recommendation.py")
_NOW = "2026-07-06T00:00:00Z"
_ACTIONABLE_LABEL = "Actionable Pick — Manual Review"

# The full ref set every ``actionable_pick_manual_review`` recommendation must carry.
_FULL_ACTIONABLE = dict(
    recommendation_id="rec:RUN-1:IREN", run_id="RUN-1", candidate_id="cc:RUN-1:IREN",
    ticker="IREN", company_name="IREN Ltd",
    recommendation_state="actionable_pick_manual_review",
    recommendation_label=_ACTIONABLE_LABEL,
    capital_candidate_ref="cc:RUN-1:IREN",
    investment_diligence_ref="THS-1",
    forward_scenario_ref="FWD-1",
    technical_timing_ref="TT-1",
    portfolio_fit_ref="PF-1",
    red_team_ref="RT-1",
    data_quality_ref="DQ-1",
    source_provenance=("run:RUN-1", "signal:sig-1"),
    invalidation_conditions=("thesis broken if X",),
    exit_watch_conditions=("exit if Y",),
    sizing_guardrail="starter position only (range, not a number)",
    generated_at=_NOW,
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# =========================================================================== #
# The contract constructs; basic vocab                                          #
# =========================================================================== #
class ContractConstructionTests(unittest.TestCase):
    def test_constructs_a_default_not_recommended(self):
        r = CapitalRecommendation(recommendation_id="rec:R:T", run_id="R",
                                  candidate_id="cc:R:T", ticker="T")
        self.assertEqual(r.recommendation_state, "not_recommended")
        self.assertFalse(r.is_actionable_pick)
        self.assertFalse(r.is_blocked)

    def test_required_ids_must_be_non_empty(self):
        base = dict(recommendation_id="rec:R:T", run_id="R", candidate_id="cc:R:T", ticker="T")
        for key in ("recommendation_id", "run_id", "candidate_id", "ticker"):
            kw = dict(base); kw[key] = ""
            with self.assertRaises(ValueError):
                CapitalRecommendation(**kw)

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(recommendation_id="rec:R:T", run_id="R",
                                  candidate_id="cc:R:T", ticker="T",
                                  recommendation_state="bogus")

    def test_invalid_publication_state_rejected(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(recommendation_id="rec:R:T", run_id="R",
                                  candidate_id="cc:R:T", ticker="T",
                                  publication_state="live_trading")

    def test_deterministic_id(self):
        self.assertEqual(recommendation_id_for("RUN-1", "iren"), "rec:RUN-1:IREN")


# =========================================================================== #
# actionable_pick_manual_review is UNFORGEABLE -- each missing piece raises      #
# =========================================================================== #
class UnforgeableActionableTests(unittest.TestCase):
    def test_full_ref_set_constructs(self):
        r = CapitalRecommendation(**_FULL_ACTIONABLE)
        self.assertTrue(r.is_actionable_pick)
        self.assertEqual(r.missing_actionable_requirements(), ())
        self.assertEqual(r.recommendation_label, _ACTIONABLE_LABEL)

    def _without(self, field_name, empty):
        kw = dict(_FULL_ACTIONABLE); kw[field_name] = empty
        return kw

    def test_actionable_without_capital_candidate_ref_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("capital_candidate_ref", ""))

    def test_actionable_without_source_provenance_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("source_provenance", ()))

    def test_actionable_without_investment_diligence_ref_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("investment_diligence_ref", ""))

    def test_actionable_without_forward_scenario_ref_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("forward_scenario_ref", ""))

    def test_actionable_without_technical_timing_ref_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("technical_timing_ref", ""))

    def test_actionable_without_portfolio_fit_ref_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("portfolio_fit_ref", ""))

    def test_actionable_without_red_team_ref_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("red_team_ref", ""))

    def test_actionable_without_data_quality_ref_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("data_quality_ref", ""))

    def test_actionable_without_invalidation_conditions_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("invalidation_conditions", ()))

    def test_actionable_without_exit_watch_conditions_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("exit_watch_conditions", ()))

    def test_actionable_without_sizing_guardrail_raises(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._without("sizing_guardrail", ""))

    def test_every_single_missing_piece_raises(self):
        # exhaustive: dropping ANY one required piece makes actionable unconstructible.
        for field_name in ("capital_candidate_ref", "source_provenance",
                           "investment_diligence_ref", "forward_scenario_ref",
                           "technical_timing_ref", "portfolio_fit_ref", "red_team_ref",
                           "data_quality_ref", "invalidation_conditions",
                           "exit_watch_conditions", "sizing_guardrail"):
            empty = () if field_name in ("source_provenance", "invalidation_conditions",
                                         "exit_watch_conditions") else ""
            kw = dict(_FULL_ACTIONABLE); kw[field_name] = empty
            with self.assertRaises(ValueError, msg="missing {0} did not raise".format(field_name)):
                CapitalRecommendation(**kw)


# =========================================================================== #
# blocked carries an EXACT reason                                               #
# =========================================================================== #
class BlockedReasonTests(unittest.TestCase):
    def test_blocked_requires_non_empty_reason(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(recommendation_id="rec:R:T", run_id="R", candidate_id="cc:R:T",
                                  ticker="T", recommendation_state="blocked",
                                  recommendation_label="Blocked", blocked_reason="")

    def test_blocked_with_reason_constructs_and_keeps_exact_text(self):
        reason = "cannot reach actionable_pick_manual_review: missing red_team_ref"
        r = CapitalRecommendation(recommendation_id="rec:R:T", run_id="R", candidate_id="cc:R:T",
                                  ticker="T", recommendation_state="blocked",
                                  recommendation_label="Blocked", blocked_reason=reason)
        self.assertTrue(r.is_blocked)
        self.assertEqual(r.blocked_reason, reason)


# =========================================================================== #
# Labels: closed vocab, forbidden phrases rejected, state<->label consistency    #
# =========================================================================== #
class LabelTests(unittest.TestCase):
    def _base(self, **kw):
        base = dict(recommendation_id="rec:R:T", run_id="R", candidate_id="cc:R:T", ticker="T")
        base.update(kw)
        return base

    def test_out_of_vocab_label_rejected(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._base(recommendation_state="watch",
                                               recommendation_label="Kinda Interesting"))

    def test_each_forbidden_label_rejected(self):
        for bad in FORBIDDEN_RECOMMENDATION_LABELS:
            with self.assertRaises(ValueError, msg="{0!r} not rejected".format(bad)):
                CapitalRecommendation(**self._base(recommendation_state="watch",
                                                   recommendation_label=bad))

    def test_forbidden_phrase_as_substring_rejected(self):
        # even embedded in a longer string, a forbidden phrase is fatal.
        for bad in ("IREN — Strong Buy", "Alpha Score: high", "Guaranteed Upside ahead"):
            with self.assertRaises(ValueError):
                CapitalRecommendation(**self._base(recommendation_state="watch",
                                                   recommendation_label=bad))

    def test_state_label_consistency_enforced(self):
        # a valid label that does not match the state is rejected.
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._base(recommendation_state="watch",
                                               recommendation_label="Avoid"))

    def test_actionable_requires_exact_label(self):
        kw = dict(_FULL_ACTIONABLE); kw["recommendation_label"] = "Prepare Entry"
        with self.assertRaises(ValueError):
            CapitalRecommendation(**kw)
        kw = dict(_FULL_ACTIONABLE); kw["recommendation_label"] = ""
        with self.assertRaises(ValueError):
            CapitalRecommendation(**kw)

    def test_blocked_requires_blocked_label(self):
        with self.assertRaises(ValueError):
            CapitalRecommendation(**self._base(recommendation_state="blocked",
                                               recommendation_label="Watch",
                                               blocked_reason="x"))

    def test_each_canonical_state_label_pair_constructs(self):
        for state, label in RECOMMENDATION_STATE_LABELS.items():
            kw = dict(self._base(recommendation_state=state, recommendation_label=label))
            if state == "blocked":
                kw["blocked_reason"] = "an exact reason"
            if state == "actionable_pick_manual_review":
                kw = dict(_FULL_ACTIONABLE)
            r = CapitalRecommendation(**kw)
            self.assertEqual(r.recommendation_state, state)

    def test_all_labels_are_forbidden_phrase_free(self):
        for label in RECOMMENDATION_LABELS:
            low = label.lower()
            for phrase in FORBIDDEN_RECOMMENDATION_LABELS:
                self.assertNotIn(phrase.lower(), low)


# =========================================================================== #
# No score / rank / rating / trade field anywhere; no numeric field             #
# =========================================================================== #
class NoTradeOrScoreFieldTests(unittest.TestCase):
    def test_assert_no_trade_fields_clean(self):
        rm.assert_no_trade_fields(CapitalRecommendation)
        REC.assert_no_trade_fields  # module ran the guard at import

    def test_no_forbidden_token_in_any_field_name(self):
        for f in fields(CapitalRecommendation):
            low = f.name.lower()
            for tok in ("buy", "sell", "order", "submit", "broker", "trade",
                        "score", "rank", "rating", "investab", "alpha"):
                self.assertNotIn(tok, low, "{0} exposes {1!r}".format(f.name, tok))

    def test_no_numeric_field_present(self):
        r = CapitalRecommendation(**_FULL_ACTIONABLE)
        for f in fields(CapitalRecommendation):
            val = getattr(r, f.name)
            self.assertNotIsInstance(val, (int, float, bool),
                                     "{0} carries a number".format(f.name))


# =========================================================================== #
# assess_recommendation -- honest; NEVER forges actionable, exact blocked reason #
# =========================================================================== #
class AssessRecommendationTests(unittest.TestCase):
    def _full_kwargs(self):
        return dict(
            ticker="IREN", run_id="RUN-1", candidate_id="cc:RUN-1:IREN",
            intended_state="actionable_pick_manual_review", now=_NOW,
            capital_candidate_ref="cc:RUN-1:IREN", investment_diligence_ref="THS-1",
            forward_scenario_ref="FWD-1", technical_timing_ref="TT-1",
            portfolio_fit_ref="PF-1", red_team_ref="RT-1", data_quality_ref="DQ-1",
            source_provenance=("run:RUN-1",),
            invalidation_conditions=("thesis broken if X",),
            exit_watch_conditions=("exit if Y",),
            sizing_guardrail="starter only")

    def test_full_set_reaches_actionable(self):
        r = assess_recommendation(**self._full_kwargs())
        self.assertTrue(r.is_actionable_pick)
        self.assertEqual(r.recommendation_label, _ACTIONABLE_LABEL)
        self.assertEqual(r.publication_state, "published")

    def test_missing_piece_downgrades_to_blocked_with_exact_reason(self):
        kw = self._full_kwargs(); kw["red_team_ref"] = ""
        r = assess_recommendation(**kw)
        self.assertTrue(r.is_blocked)
        self.assertIn("red_team_ref", r.blocked_reason)
        self.assertIn("cannot reach actionable_pick_manual_review", r.blocked_reason)
        self.assertFalse(r.is_actionable_pick)

    def test_everything_missing_never_reaches_actionable(self):
        r = assess_recommendation(ticker="T", run_id="R", candidate_id="cc:R:T",
                                  intended_state="actionable_pick_manual_review", now=_NOW)
        self.assertTrue(r.is_blocked)
        self.assertFalse(r.is_actionable_pick)

    def test_non_actionable_intent_passes_through(self):
        r = assess_recommendation(ticker="T", run_id="R", candidate_id="cc:R:T",
                                  intended_state="watch", now=_NOW)
        self.assertEqual(r.recommendation_state, "watch")
        self.assertEqual(r.recommendation_label, "Watch")

    def test_deterministic(self):
        self.assertEqual(assess_recommendation(**self._full_kwargs()),
                         assess_recommendation(**self._full_kwargs()))


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

    def test_recommendation_imports_no_network_scheduler_broker(self):
        tree = ast.parse(self._read(_REC_PY))
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods.append((node.module or "").split(".")[0])
        for m in mods:
            self.assertNotIn(m, self._NET, "imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "imports forbidden {0}".format(m))

    def test_recommendation_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_REC_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "defines {0}".format(node.name))

    def test_source_has_no_broker_or_execution_token(self):
        blob = self._read(_REC_PY).lower()
        for tok in ("place_order", "submit_order", "broker.submit", "execute_trade",
                    "time.time(", "datetime.now("):
            self.assertNotIn(tok, blob, "forbidden token {0}".format(tok))

    def test_actionable_is_offline_under_socket_kill_switch(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            r = CapitalRecommendation(**_FULL_ACTIONABLE)
        finally:
            socket.socket = real
        self.assertTrue(r.is_actionable_pick)

    def test_demo_pulse_is_byte_identical(self):
        a = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        b = rm.run_pulse(["IREN"], ["physical_ai"], now=_NOW)
        self.assertEqual(tuple(s.signal_id for s in a.signals),
                         tuple(s.signal_id for s in b.signals))
        self.assertEqual(tuple(f.finding_id for f in a.findings),
                         tuple(f.finding_id for f in b.findings))

    def test_construction_is_deterministic(self):
        self.assertEqual(CapitalRecommendation(**_FULL_ACTIONABLE),
                         CapitalRecommendation(**_FULL_ACTIONABLE))


if __name__ == "__main__":
    unittest.main()
