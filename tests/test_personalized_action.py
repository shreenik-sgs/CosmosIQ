from __future__ import annotations

import os as _os, sys as _sys
_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import copy
import dataclasses
import unittest

from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis
from prometheus.diligence_inputs import DiligenceInputs
from prometheus.investment_thesis import generate_investment_thesis
from prometheus.investment_action import generate_investment_action
from prometheus.position_lifecycle import PositionContext
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.portfolio_snapshot import make_portfolio_snapshot
from personal_cio.personalized_action import (
    generate_personalized_action,
    PersonalizedAction,
)
from runtime.vertical_slice_runner import (
    iren_source_observations,
    iren_diligence_inputs,
    run_iren_slice,
)

DOMAIN = "ai-infrastructure"
NOW = 1_700_000_000.0

# Execution / order / sizing language that must never appear in a personalized view.
_FORBIDDEN = (
    "buy", "sell", "market order", "limit order", "stop order", "trade ticket",
    "broker", "execute", "submit", "exact shares", "option contract",
    "order quantity", "shares",
)
_ALLOWED_VOCAB = (
    "suitable_candidate", "priority_candidate", "reduced_size_candidate",
    "wait_for_user", "blocked_for_user", "monitor_only",
    "recommended_max_exposure_pct", "recommended max exposure", "percent",
)


# --- real-gauntlet thesis / action builders --------------------------------
def _hypothesis(now=NOW):
    obs = iren_source_observations(now)
    ia = generate_intelligence_assessment(obs, domain=DOMAIN, actor="t", now=now)
    return generate_opportunity_hypothesis([ia], domain=DOMAIN, actor="t", now=now)


def _base_candidate():
    return iren_diligence_inputs().candidates[0]


def _thesis_from(candidate, now=NOW):
    oh = _hypothesis(now)
    di = DiligenceInputs(domain=DOMAIN, candidates=(candidate,))
    return generate_investment_thesis(oh, di, actor="t", now=now)


def _base_thesis():
    return generate_investment_thesis(_hypothesis(), iren_diligence_inputs(),
                                      actor="t", now=NOW)


def _weak_chart_thesis():  # thesis_worthy, timing NOT confirmed -> wait
    c = dataclasses.replace(_base_candidate(), volume_recent=900_000.0)
    return _thesis_from(c)


def _watch_thesis():  # weak inflection -> watch -> monitor
    c = dataclasses.replace(_base_candidate(), revenue=210.0, prior_revenue=200.0,
                            gross_margin=0.50, prior_gross_margin=0.50, guidance="inline")
    return _thesis_from(c)


def _poor_asymmetry_thesis():  # poor asymmetry -> not_investable -> avoid
    c = dataclasses.replace(_base_candidate(), bull_price=10.50, extreme_bull_price=11.0)
    return _thesis_from(c)


def _severe_dilution_thesis():  # red-team fail -> not_investable
    c = dataclasses.replace(_base_candidate(), dilution_risk="high")
    return _thesis_from(c)


def _enter_action():
    return generate_investment_action(_base_thesis(), now=NOW)


def _profile(**kw):
    kw.setdefault("risk_tolerance", "moderate")
    return make_personal_investment_profile("ACCT", actor="t", now=NOW, **kw)


def _portfolio(**kw):
    kw.setdefault("total_portfolio_value", 100_000.0)
    kw.setdefault("available_cash", 50_000.0)
    return make_portfolio_snapshot(account="ACCT", actor="t", now=NOW, **kw)


def _pa(thesis, action, profile=None, portfolio=None):
    return generate_personalized_action(
        thesis, action, profile or _profile(), portfolio or _portfolio(),
        actor="t", now=NOW)


class TestPersonalizedAction(unittest.TestCase):
    # --- validation --------------------------------------------------------
    def test_personal_action_requires_investment_action(self):
        with self.assertRaises(ValueError):
            generate_personalized_action(_base_thesis(), object(), _profile(),
                                         _portfolio(), now=NOW)

    def test_personal_action_requires_user_profile(self):
        with self.assertRaises(ValueError):
            generate_personalized_action(_base_thesis(), _enter_action(), None,
                                         _portfolio(), now=NOW)

    def test_personal_action_requires_portfolio_snapshot(self):
        with self.assertRaises(ValueError):
            generate_personalized_action(_base_thesis(), _enter_action(), _profile(),
                                         None, now=NOW)

    # --- upstream action_type mapping -------------------------------------
    def test_avoid_action_becomes_blocked_or_monitor_only(self):
        t = _poor_asymmetry_thesis()
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(action.action_type, "avoid")
        p = _pa(t, action)
        self.assertIn(p.recommendation_status, ("blocked_for_user", "monitor_only"))

    def test_wait_action_becomes_wait_for_user(self):
        t = _weak_chart_thesis()
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(action.action_type, "wait")
        self.assertEqual(_pa(t, action).recommendation_status, "wait_for_user")

    def test_monitor_action_becomes_monitor_only(self):
        t = _watch_thesis()
        action = generate_investment_action(t, now=NOW)
        self.assertEqual(action.action_type, "monitor")
        self.assertEqual(_pa(t, action).recommendation_status, "monitor_only")

    def test_enter_candidate_with_good_fit_becomes_suitable_or_priority_candidate(self):
        p = _pa(_base_thesis(), _enter_action())
        self.assertIn(p.recommendation_status, ("suitable_candidate", "priority_candidate"))
        self.assertGreater(p.recommended_max_exposure_pct, 0.0)

    def test_trim_or_exit_candidate_becomes_risk_reduction_or_exit_candidate(self):
        held = PositionContext(has_position=True)
        trim_t = _watch_thesis()
        trim_action = generate_investment_action(trim_t, position_context=held, now=NOW)
        self.assertEqual(trim_action.action_type, "trim_candidate")
        self.assertEqual(_pa(trim_t, trim_action).recommendation_status,
                         "risk_reduction_candidate")

        exit_t = _severe_dilution_thesis()
        exit_action = generate_investment_action(exit_t, position_context=held, now=NOW)
        self.assertEqual(exit_action.action_type, "exit_candidate")
        self.assertEqual(_pa(exit_t, exit_action).recommendation_status, "exit_candidate")

    # --- risk-tolerance gates ---------------------------------------------
    def test_conservative_profile_downgrades_marginal_thesis(self):
        # A marginal-confidence enter candidate for a conservative user waits.
        marginal = dataclasses.replace(_base_thesis(), thesis_confidence=0.55)
        action = _enter_action()
        p = _pa(marginal, action, profile=_profile(risk_tolerance="conservative"))
        self.assertEqual(p.recommendation_status, "wait_for_user")

    def test_asymmetric_growth_profile_allows_stronger_candidate(self):
        profile = _profile(risk_tolerance="asymmetric_growth",
                           max_single_position_pct=15.0, max_theme_exposure_pct=40.0)
        p = _pa(_base_thesis(), _enter_action(), profile=profile)
        self.assertEqual(p.recommendation_status, "priority_candidate")

    def test_high_concentration_prevents_priority_candidate(self):
        # Would otherwise be priority (asymmetric, high conviction, timing), but the
        # existing exposure is near the single-position limit -> never priority.
        profile = _profile(risk_tolerance="asymmetric_growth",
                           max_single_position_pct=60.0, max_theme_exposure_pct=80.0)
        portfolio = _portfolio(existing_exposure_to_candidate=48.0)  # >= 0.8 * 60
        p = _pa(_base_thesis(), _enter_action(), profile=profile, portfolio=portfolio)
        self.assertNotEqual(p.recommendation_status, "priority_candidate")
        self.assertIn(p.recommendation_status,
                      ("suitable_candidate", "reduced_size_candidate"))

    # --- portfolio gates ---------------------------------------------------
    def test_existing_position_over_max_single_position_blocks_or_reduces(self):
        portfolio = _portfolio(existing_exposure_to_candidate=8.0)  # == max_single 8
        p = _pa(_base_thesis(), _enter_action(), portfolio=portfolio)
        self.assertIn(p.recommendation_status, ("blocked_for_user", "reduced_size_candidate"))

    def test_theme_exposure_over_limit_blocks_or_reduces(self):
        portfolio = _portfolio(existing_exposure_to_theme=25.0)  # == max_theme 25
        p = _pa(_base_thesis(), _enter_action(), portfolio=portfolio)
        self.assertIn(p.recommendation_status, ("blocked_for_user", "reduced_size_candidate"))

    def test_insufficient_cash_blocks_or_reduces(self):
        # Cash below the 10% reserve -> no room without breaching the reserve.
        portfolio = _portfolio(available_cash=5_000.0)
        p = _pa(_base_thesis(), _enter_action(), portfolio=portfolio)
        self.assertIn(p.recommendation_status, ("blocked_for_user", "reduced_size_candidate"))

    def test_minimum_cash_reserve_is_preserved(self):
        # Only 2% of the portfolio is free above the reserve; the recommendation can
        # never exceed that, so deploying it cannot breach the reserve.
        portfolio = _portfolio(available_cash=12_000.0)  # reserve 10k -> 2% free
        p = _pa(_base_thesis(), _enter_action(), portfolio=portfolio)
        self.assertLessEqual(p.recommended_max_exposure_pct, 2.0 + 1e-6)
        self.assertLessEqual(p.suggested_sizing_range_pct[1], 2.0 + 1e-6)

    def test_disallowed_instrument_blocks_candidate(self):
        profile = _profile(restricted_instruments=("IREN",))
        p = _pa(_base_thesis(), _enter_action(), profile=profile)
        self.assertEqual(p.recommendation_status, "blocked_for_user")

    def test_leverage_or_options_disallowed_blocks_option_route(self):
        action = _enter_action()
        option_action = dataclasses.replace(
            action, security_or_instrument_mapping="IREN CALL OPTION")
        p = _pa(_base_thesis(), option_action, profile=_profile(options_allowed=False))
        self.assertEqual(p.recommendation_status, "blocked_for_user")

        lev_action = dataclasses.replace(
            action, security_or_instrument_mapping="IREN 2X LEVERAGED")
        q = _pa(_base_thesis(), lev_action, profile=_profile(leverage_allowed=False))
        self.assertEqual(q.recommendation_status, "blocked_for_user")

    # --- sizing range respects every constraint ---------------------------
    def test_sizing_range_respects_max_single_position_pct(self):
        profile = _profile(max_single_position_pct=2.0)
        p = _pa(_base_thesis(), _enter_action(), profile=profile)
        self.assertLessEqual(p.recommended_max_exposure_pct, 2.0 + 1e-6)
        self.assertLessEqual(p.suggested_sizing_range_pct[1], 2.0 + 1e-6)

    def test_sizing_range_respects_theme_exposure_limit(self):
        profile = _profile(max_theme_exposure_pct=1.5)
        p = _pa(_base_thesis(), _enter_action(), profile=profile)
        self.assertLessEqual(p.recommended_max_exposure_pct, 1.5 + 1e-6)

    def test_sizing_range_respects_available_cash(self):
        portfolio = _portfolio(available_cash=11_000.0)  # 1% free above reserve
        p = _pa(_base_thesis(), _enter_action(), portfolio=portfolio)
        self.assertLessEqual(p.recommended_max_exposure_pct, 1.0 + 1e-6)

    # --- provenance / immutability ----------------------------------------
    def test_personalized_action_preserves_thesis_and_action_provenance(self):
        t, action = _base_thesis(), _enter_action()
        p = _pa(t, action)
        self.assertEqual(p.source_action_id, action.id)
        self.assertEqual(p.source_action_version, action.version)
        self.assertEqual(p.source_thesis_id, t.id)
        self.assertEqual(p.source_thesis_version, t.version)
        ids = {r.object_id for r in p.provenance.sources}
        self.assertIn(action.id, ids)
        self.assertIn(t.id, ids)
        ref = next(r for r in p.provenance.sources if r.object_id == action.id)
        self.assertEqual(ref.version, action.version)

    def test_personalized_action_preserves_upstream_observation_ids(self):
        action = _enter_action()
        p = _pa(_base_thesis(), action)
        self.assertTrue(p.upstream_observation_ids)
        self.assertEqual(set(p.upstream_observation_ids),
                         set(action.upstream_observation_ids))

    def test_personalized_action_does_not_mutate_thesis_or_action(self):
        t, action = _base_thesis(), _enter_action()
        t_snap, a_snap = copy.deepcopy(t), copy.deepcopy(action)
        _pa(t, action)
        _pa(t, action, portfolio=_portfolio(existing_exposure_to_candidate=4.0))
        self.assertEqual(t, t_snap)
        self.assertEqual(action, a_snap)

    # --- boundary purity ---------------------------------------------------
    def test_personalized_action_has_no_broker_order_trade_ticket_fields(self):
        fields = set(PersonalizedAction.__dataclass_fields__.keys())
        for bad in ("side", "quantity", "order", "order_type", "limit_price",
                    "stop_price", "broker_order_id", "trade_ticket",
                    "cio_decision_record_id", "venue"):
            self.assertNotIn(bad, fields)

    def test_personalized_action_has_no_exact_share_or_contract_quantity(self):
        fields = set(PersonalizedAction.__dataclass_fields__.keys())
        for bad in ("intended_allocation", "allocation", "shares", "exact_shares",
                    "contracts", "option_contracts", "quantity", "dollar_amount"):
            self.assertNotIn(bad, fields)
        # Only percentages -- the recommendation is an exposure %, with a % range.
        p = _pa(_base_thesis(), _enter_action())
        self.assertIsInstance(p.recommended_max_exposure_pct, float)
        self.assertEqual(len(p.suggested_sizing_range_pct), 2)

    def test_personalized_action_does_not_modify_kriya(self):
        # No Personal CIO (Saarathi) module imports the execution (Kriya) layer.
        import personal_cio.personalized_action as pa_mod
        import personal_cio.personal_investment_profile as pip_mod
        import personal_cio.portfolio_snapshot as ps_mod
        for mod in (pa_mod, pip_mod, ps_mod):
            with open(mod.__file__) as fh:
                src = fh.read().lower()
            self.assertNotIn("import execution_manual", src)
            self.assertNotIn("from execution_manual", src)

    def test_personalized_action_language_has_no_order_or_sizing_leakage(self):
        held = PositionContext(has_position=True)
        cases = [
            _pa(_base_thesis(), _enter_action()),
            _pa(_weak_chart_thesis(), generate_investment_action(_weak_chart_thesis(), now=NOW)),
            _pa(_watch_thesis(), generate_investment_action(_watch_thesis(), now=NOW)),
            _pa(_poor_asymmetry_thesis(), generate_investment_action(_poor_asymmetry_thesis(), now=NOW)),
            _pa(_watch_thesis(), generate_investment_action(_watch_thesis(), position_context=held, now=NOW)),
            _pa(_severe_dilution_thesis(), generate_investment_action(_severe_dilution_thesis(), position_context=held, now=NOW)),
        ]
        for p in cases:
            blob = " ".join([
                p.personalized_rationale, p.recommendation_status,
                " ".join(p.required_user_confirmations), " ".join(p.blocking_conditions),
                " ".join(p.risk_warnings), " ".join(p.monitoring_signals),
                " ".join(p.review_triggers),
            ]).lower()
            for term in _FORBIDDEN:
                self.assertNotIn(term, blob,
                                 msg="leaked {0!r} in {1}".format(term, p.recommendation_status))

    def test_personalized_action_may_carry_candidate_vocabulary(self):
        p = _pa(_base_thesis(), _enter_action())
        blob = (p.personalized_rationale + " " + p.recommendation_status).lower()
        self.assertTrue(any(v in blob for v in _ALLOWED_VOCAB))

    # --- slice integration -------------------------------------------------
    def test_vertical_slice_iren_generates_personalized_action(self):
        r = run_iren_slice()
        p = r.personalized_action
        self.assertIsInstance(p, PersonalizedAction)
        self.assertIn(p.recommendation_status,
                      ("suitable_candidate", "priority_candidate", "reduced_size_candidate"))
        self.assertEqual(p.source_action_id, r.action.id)
        self.assertEqual(p.source_thesis_id, r.thesis.id)
        self.assertGreater(p.recommended_max_exposure_pct, 0.0)
        self.assertEqual(r.ticket_preview1.quantity, 200)


if __name__ == "__main__":
    unittest.main()
