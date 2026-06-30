"""Shared test fixtures: build the REAL EIOS reasoning chain end to end.

Observation -> IntelligenceAssessment -> OpportunityHypothesis -> InvestmentThesis
(gauntlet) -> InvestmentAction -> PersonalizedAction (Saarathi) -> the labelled
Kriya ``ManualExecutionAdapter``.

The execution-threading tests use ``real_adapter`` to obtain the single adapter
object that the Kriya manual-ticket path reads (passed as BOTH the action and
personalized args to ``create_or_get_ticket``). ``real_chain`` returns every
intermediate object for provenance / mutation assertions.
"""

from __future__ import annotations

import os as _os
import sys as _sys

_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

from reality_intelligence.intelligence_assessment import generate_intelligence_assessment
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis
from prometheus.investment_thesis import generate_investment_thesis
from prometheus.investment_action import (
    generate_investment_action,
    make_manual_execution_adapter,
)
from personal_cio.personal_investment_profile import make_personal_investment_profile
from personal_cio.portfolio_snapshot import make_portfolio_snapshot
from personal_cio.personalized_action import generate_personalized_action
from runtime.vertical_slice_runner import iren_source_observations, iren_diligence_inputs

DOMAIN = "ai-infrastructure"


def real_chain(now=0.0, account="ACCT"):
    """Build the full real reasoning chain and return every object."""
    obs = iren_source_observations(now)
    ia = generate_intelligence_assessment(obs, domain=DOMAIN, actor="t", now=now)
    oph = generate_opportunity_hypothesis([ia], domain=DOMAIN, actor="t", now=now)
    thesis = generate_investment_thesis(oph, iren_diligence_inputs(), actor="t", now=now)
    action = generate_investment_action(thesis, actor="t", now=now)
    profile = make_personal_investment_profile(account, actor="t", now=now)
    portfolio = make_portfolio_snapshot(account=account, actor="t", now=now)
    psa = generate_personalized_action(thesis, action, profile, portfolio,
                                       actor="t", now=now)
    return {
        "observations": obs, "observation": obs[0], "assessment": ia,
        "hypothesis": oph, "thesis": thesis, "action": action,
        "profile": profile, "portfolio": portfolio, "personalized": psa,
    }


def real_adapter(now=0.0, account="ACCT", intended_allocation=2000.0, instrument="IREN"):
    """The labelled Kriya ``ManualExecutionAdapter`` -- the user's chosen exact size
    within Saarathi's recommended range -- for the Kriya manual-ticket path."""
    c = real_chain(now=now, account=account)
    return make_manual_execution_adapter(
        c["action"], c["personalized"],
        intended_allocation=intended_allocation, instrument=instrument,
        side="buy", action_type="enter", actor="t", now=now,
    )
