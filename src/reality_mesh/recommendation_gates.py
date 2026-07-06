"""The Recommendation Eligibility Gate Engine (IMPLEMENTATION-022B).

The runtime decision layer ABOVE the 022A :class:`~reality_mesh.recommendation.CapitalRecommendation`
model. 022A made ``actionable_pick_manual_review`` UNFORGEABLE at the *structural* level (the full
ref set must be present). 022B adds the RUNTIME GATE LOGIC that decides, from the real evidence,
WHICH state a recommendation is honestly allowed to reach:

* **Actionable requires ALL 15 hard gates to pass.** A recommendation may become
  ``actionable_pick_manual_review`` ONLY when every one of the fifteen
  :data:`RECOMMENDATION_HARD_GATES` passes. The engine builds that state THROUGH the 022A model
  (:func:`~reality_mesh.recommendation.assess_recommendation`), which independently re-checks the
  ref set -- the gate engine never bypasses the unforgeable-actionable invariant.

* **A hard-gate failure on required grounds -> ``blocked`` with an EXACT reason** naming the
  failed gate. Missing / absent inputs are NEVER passes: they block or downgrade, never silently
  pass.

* **A sound basis with merely-incomplete SOFT pieces -> ``active_diligence`` or ``watch``,
  never actionable.** Diligence still in progress, or timing / portfolio not yet assessed (the
  022C ``TechnicalTimingSetup`` and 022D ``PortfolioFit`` models are NOT built yet, so gates 11
  and 12 have no real input and CANNOT pass today) -> ``active_diligence``. A social / rumor-only
  basis -> at most ``watch``.

* **A social / rumor-only basis can NEVER be actionable** (it fails multi-source corroboration /
  company-evidence on non-social grounds -> at most ``watch``). **Fixture / demo data can NEVER
  be actionable** (a demo/fixture-mode candidate fails candidate-eligibility -> ``blocked``).

Because 022C / 022D are absent, ``actionable_pick_manual_review`` is UNREACHABLE for any real
input today -- which is the correct, honest state. The path is proven reachable only by injecting
genuine, complete technical + portfolio evidence (see the 022B test suite).

Labels / reasons ONLY -- there is NO numeric score / rank / rating field and NO buy / sell /
order / submit / broker / trade field anywhere. Deterministic (injected ``now`` + a
run+ticker-derived id), stdlib-only, Python 3.9, OFFLINE. No network / scheduler / broker on
import; no wall-clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

from . import labels as _labels
from .capital_candidate import CapitalCandidate, candidate_id_for
from .recommendation import (
    RECOMMENDATION_STATE_LABELS,
    CapitalRecommendation,
    assess_recommendation,
    recommendation_id_for,
)
from .validation import assert_no_trade_fields

__all__ = [
    "RECOMMENDATION_HARD_GATES",
    "HARD_GATE_IDS",
    "CORROBORATION_AUTHORITIES",
    "ACCEPTABLE_DATA_QUALITY_STATES",
    "FRESH_SOURCE_LABELS",
    "STRENGTHENING_THEME_STATES",
    "FIXTURE_DEMO_MODES",
    "GATE_FAILURE_MODES",
    "HardGate",
    "GateResult",
    "RecommendationGateOutcome",
    "evaluate_recommendation",
]


# --------------------------------------------------------------------------- #
# Closed vocabularies driving the gates                                         #
# --------------------------------------------------------------------------- #

# The source authorities that COUNT as independent, non-social corroboration. ``manual``
# (operator-entered, not independent) and ``rumor`` (social) are DELIBERATELY excluded -- a
# corroboration source must be a real, independent data source.
CORROBORATION_AUTHORITIES: Tuple[str, ...] = ("canonical", "primary", "convenience", "fallback")

# The producing run's data-quality states under which a recommendation may proceed: ``healthy``
# or ``explicitly_acceptable`` (a known-gaps run an operator has explicitly accepted). Anything
# else (degraded / failed / unstated) blocks.
ACCEPTABLE_DATA_QUALITY_STATES: Tuple[str, ...] = ("healthy", "explicitly_acceptable")

# The source-freshness labels that pass gate 3 -- current evidence only.
FRESH_SOURCE_LABELS: Tuple[str, ...] = ("fresh", "recent")

# The ThemePulse states that read as strengthening or already strong (gate 5). Every other state
# (Dormant / Crowded / Exhausting / Breaking down / Conflicted / Data insufficient) blocks.
STRENGTHENING_THEME_STATES: Tuple[str, ...] = ("Warming", "Igniting", "Broadening")

# Producing-run modes that mark a NON-real (fixture / demo) basis -- never actionable.
FIXTURE_DEMO_MODES: Tuple[str, ...] = ("demo", "fixture")

# How a failed gate downgrades the recommendation. ``block`` = an unsound / contaminated / absent
# basis -> ``blocked`` with an exact reason. ``watch`` = a social/rumor-only basis -> monitored,
# never promoted. ``active_diligence`` = a sound basis whose completion pieces (diligence in
# progress, timing / portfolio not yet assessed) are merely pending.
GATE_FAILURE_MODES: Tuple[str, ...] = ("block", "watch", "active_diligence")

# The precedence of failure modes when several gates fail: a block dominates a watch, which
# dominates an active_diligence. (Lower index = higher precedence.)
_FAILURE_PRECEDENCE = {"block": 0, "watch": 1, "active_diligence": 2}
_FAILURE_TO_STATE = {
    "block": "blocked",
    "watch": "watch",
    "active_diligence": "active_diligence",
}


# --------------------------------------------------------------------------- #
# Gate + result shapes                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GateResult:
    """One gate's verdict: its id, whether it PASSED, and a plain-English reason.

    ``failure_mode`` is "" when the gate passed; otherwise one of :data:`GATE_FAILURE_MODES`
    naming how this failure downgrades the recommendation (block / watch / active_diligence). It
    is a LABEL, never a number -- there is no score / rank / rating anywhere.
    """

    gate_id: str = ""
    passed: bool = False
    reason: str = ""
    failure_mode: str = ""      # "" when passed; else a GATE_FAILURE_MODES member

    def __post_init__(self) -> None:
        if not str(self.gate_id or "").strip():
            raise ValueError("GateResult.gate_id is required and must be non-empty")
        if self.failure_mode and self.failure_mode not in GATE_FAILURE_MODES:
            raise ValueError(
                "GateResult.failure_mode {0!r} invalid (allowed: {1})".format(
                    self.failure_mode, list(GATE_FAILURE_MODES)))
        if self.passed and self.failure_mode:
            raise ValueError("GateResult that passed must not carry a failure_mode")
        if not self.passed and not self.failure_mode:
            raise ValueError("GateResult that failed must carry a failure_mode")


@dataclass(frozen=True)
class HardGate:
    """One of the 15 hard recommendation gates: an id, a description, and a predicate.

    The ``predicate`` takes the normalized :class:`_GateInputs` and returns a :class:`GateResult`.
    Predicates are pure and deterministic; they never fabricate a pass from an absent input.
    """

    gate_id: str = ""
    description: str = ""
    predicate: Optional[Callable[["_GateInputs"], GateResult]] = None

    def __post_init__(self) -> None:
        if not str(self.gate_id or "").strip():
            raise ValueError("HardGate.gate_id is required and must be non-empty")

    def evaluate(self, inputs: "_GateInputs") -> GateResult:
        return self.predicate(inputs)      # type: ignore[misc]


@dataclass(frozen=True)
class RecommendationGateOutcome:
    """The overall gate verdict: the state a recommendation is honestly allowed to reach.

    ``state`` / ``label`` are the derived :data:`~reality_mesh.recommendation.RECOMMENDATION_STATES`
    verdict; ``blocked_reason`` is the EXACT failed-gate reason when ``state == "blocked"`` (empty
    otherwise); ``gate_results`` is the full, ordered tuple of all 15 :class:`GateResult`. There is
    NO score / rank / rating anywhere -- labels + reasons only.
    """

    state: str = ""
    label: str = ""
    blocked_reason: str = ""
    downgrade_reason: str = ""          # why a sound-but-incomplete basis stayed non-actionable
    gate_results: Tuple[GateResult, ...] = field(default_factory=tuple)

    @property
    def is_actionable(self) -> bool:
        return self.state == "actionable_pick_manual_review"

    @property
    def is_blocked(self) -> bool:
        return self.state == "blocked"

    def passed_gate_ids(self) -> Tuple[str, ...]:
        return tuple(g.gate_id for g in self.gate_results if g.passed)

    def failed_gate_ids(self) -> Tuple[str, ...]:
        return tuple(g.gate_id for g in self.gate_results if not g.passed)


# --------------------------------------------------------------------------- #
# Normalized inputs                                                             #
# --------------------------------------------------------------------------- #
def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _source_is_social(authority: str, source_type: str) -> bool:
    """True iff a source is X/social or rumor-tier (never counts as real corroboration)."""
    if _clean_str(authority).lower() == "rumor":
        return True
    st = _clean_str(source_type)
    if st and (_labels.is_social_source_type(st) or st.lower() in _labels.SOCIAL_SOURCE_TYPES):
        return True
    return False


def _normalize_source(item: Any) -> Tuple[str, str, str]:
    """Coerce a source descriptor to ``(source_id, authority, source_type)``.

    Accepts a bare id string, a ``(id, authority[, source_type])`` tuple, or any object exposing
    ``source_id`` / ``source_authority`` (or ``source_authority_summary``) / ``source_type``.
    """
    if isinstance(item, (tuple, list)):
        sid = _clean_str(item[0]) if len(item) > 0 else ""
        auth = _clean_str(item[1]) if len(item) > 1 else ""
        stype = _clean_str(item[2]) if len(item) > 2 else ""
        return sid, auth, stype
    if isinstance(item, str):
        return _clean_str(item), "", ""
    sid = _clean_str(getattr(item, "source_id", "") or getattr(item, "ref", ""))
    auth = _clean_str(getattr(item, "source_authority", "")
                      or getattr(item, "source_authority_summary", ""))
    stype = _clean_str(getattr(item, "source_type", ""))
    return sid, auth, stype


def _real_corroboration_ids(items: Tuple[Any, ...]) -> Tuple[str, ...]:
    """The DISTINCT, independent, non-social source ids that count as corroboration."""
    seen = []
    for item in items or ():
        sid, auth, stype = _normalize_source(item)
        if not sid:
            continue
        if auth not in CORROBORATION_AUTHORITIES:
            continue
        if _source_is_social(auth, stype):
            continue
        if sid not in seen:
            seen.append(sid)
    return tuple(seen)


def _has_any_source(items: Tuple[Any, ...]) -> bool:
    return any(_normalize_source(i)[0] for i in (items or ()))


def _has_social_source(items: Tuple[Any, ...]) -> bool:
    for item in items or ():
        sid, auth, stype = _normalize_source(item)
        if sid and _source_is_social(auth, stype):
            return True
    return False


@dataclass(frozen=True)
class _GateInputs:
    """The normalized, deterministic inputs the 15 gate predicates read (internal)."""

    ticker: str = ""
    candidate: Optional[CapitalCandidate] = None
    data_quality_ref: str = ""
    data_quality_state: str = ""
    source_freshness: str = ""
    corroboration_sources: Tuple[Any, ...] = field(default_factory=tuple)
    theme_pulse_state: str = ""
    bottleneck_exposure_refs: Tuple[str, ...] = field(default_factory=tuple)
    company_evidence_refs: Tuple[Any, ...] = field(default_factory=tuple)
    investment_diligence_ref: str = ""
    diligence_complete: bool = False
    forward_scenario_ref: str = ""
    red_team_ref: str = ""
    unresolved_thesis_killer: bool = False
    technical_timing_ref: str = ""
    technical_timing_acceptable: bool = False
    portfolio_fit_ref: str = ""
    portfolio_fit_acceptable: bool = False
    sizing_guardrail: str = ""
    invalidation_conditions: Tuple[str, ...] = field(default_factory=tuple)
    exit_watch_conditions: Tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
# The 15 gate predicates -- each pure, deterministic, never fabricates a pass    #
# --------------------------------------------------------------------------- #
def _passed(gate_id: str, reason: str) -> GateResult:
    return GateResult(gate_id=gate_id, passed=True, reason=reason, failure_mode="")


def _failed(gate_id: str, reason: str, mode: str) -> GateResult:
    return GateResult(gate_id=gate_id, passed=False, reason=reason, failure_mode=mode)


def _gate_candidate_eligibility(x: _GateInputs) -> GateResult:
    gid = "candidate_eligibility"
    cand = x.candidate
    if cand is None:
        return _failed(gid, "no CapitalCandidate supplied -- a recommendation needs an eligible "
                            "020A candidate with full provenance lineage", "block")
    if not isinstance(cand, CapitalCandidate):
        return _failed(gid, "the supplied candidate is not a CapitalCandidate", "block")
    if _clean_str(cand.mode).lower() in FIXTURE_DEMO_MODES:
        return _failed(gid, "the candidate was produced in {0!r} (fixture/demo) mode -- "
                            "fixture/demo data can never be actionable".format(cand.mode), "block")
    if not cand.is_eligible:
        return _failed(gid, "the CapitalCandidate is {0!r}, not 'eligible' -- {1}".format(
            cand.candidate_state, cand.basis or "full 020A lineage absent"), "block")
    return _passed(gid, "candidate {0} is an eligible 020A candidate (real, non-demo mode {1})"
                        .format(cand.candidate_id, cand.mode))


def _gate_trust_data_quality(x: _GateInputs) -> GateResult:
    gid = "trust_data_quality"
    if not _clean_str(x.data_quality_ref):
        return _failed(gid, "no data-quality verdict ref -- the producing run's DQ is unstated", "block")
    state = _clean_str(x.data_quality_state)
    if state not in ACCEPTABLE_DATA_QUALITY_STATES:
        return _failed(gid, "producing-run data quality is {0!r} -- only {1} may proceed".format(
            state or "unstated", list(ACCEPTABLE_DATA_QUALITY_STATES)), "block")
    return _passed(gid, "data quality is {0!r} (ref {1})".format(state, x.data_quality_ref))


def _gate_source_freshness(x: _GateInputs) -> GateResult:
    gid = "source_freshness"
    fresh = _clean_str(x.source_freshness)
    if fresh not in FRESH_SOURCE_LABELS:
        return _failed(gid, "source freshness is {0!r} -- evidence must be fresh/recent, not "
                            "stale/expired/aging/missing".format(fresh or "missing"), "block")
    return _passed(gid, "source evidence is {0!r}".format(fresh))


def _gate_multi_source_corroboration(x: _GateInputs) -> GateResult:
    gid = "multi_source_corroboration"
    real = _real_corroboration_ids(x.corroboration_sources)
    if len(real) >= 2:
        return _passed(gid, "corroborated by {0} independent non-social source(s): {1}".format(
            len(real), ", ".join(real)))
    # A social/rumor-only basis is monitored, never promoted -> watch (at most).
    if not real and _has_social_source(x.corroboration_sources):
        return _failed(gid, "corroboration is social/rumor-only -- social/rumor never counts; a "
                            "social-only basis is monitored, never actionable", "watch")
    return _failed(gid, "fewer than 2 independent non-social sources ({0} found) -- multi-source "
                        "corroboration is missing".format(len(real)), "block")


def _gate_theme_pulse_strength(x: _GateInputs) -> GateResult:
    gid = "theme_pulse_strength"
    state = _clean_str(x.theme_pulse_state)
    if state in STRENGTHENING_THEME_STATES:
        return _passed(gid, "theme pulse is {0!r} (strengthening / strong)".format(state))
    return _failed(gid, "theme pulse is {0!r} -- not strengthening/strong (weak, crowded, "
                        "breaking-down, conflicted or data-insufficient)".format(
                            state or "unstated"), "block")


def _gate_value_chain_bottleneck_exposure(x: _GateInputs) -> GateResult:
    gid = "value_chain_bottleneck_exposure"
    refs = tuple(r for r in (x.bottleneck_exposure_refs or ()) if _clean_str(r))
    if refs:
        return _passed(gid, "explicit value-chain / bottleneck exposure: {0}".format(
            ", ".join(refs)))
    return _failed(gid, "no explicit value-chain / bottleneck exposure on the graph -- the "
                        "beneficiary is not mapped to a chokepoint", "block")


def _gate_company_evidence_beneficiary(x: _GateInputs) -> GateResult:
    gid = "company_evidence_beneficiary"
    real = _real_corroboration_ids(x.company_evidence_refs)
    if real:
        return _passed(gid, "company-level evidence supports beneficiary status: {0}".format(
            ", ".join(real)))
    if _has_social_source(x.company_evidence_refs):
        return _failed(gid, "company evidence is social/rumor-only -- no company-level "
                            "corroboration of beneficiary status; monitored, never actionable", "watch")
    return _failed(gid, "no company-level evidence supporting beneficiary status", "block")


def _gate_investment_diligence_complete(x: _GateInputs) -> GateResult:
    gid = "investment_diligence_complete"
    if not _clean_str(x.investment_diligence_ref):
        return _failed(gid, "no investment-diligence thesis ref -- the accepted engine's thesis "
                            "is absent", "block")
    if not x.diligence_complete:
        return _failed(gid, "investment diligence is in progress / not complete enough -- the "
                            "thesis is not yet finished", "active_diligence")
    return _passed(gid, "investment diligence complete (thesis {0})".format(
        x.investment_diligence_ref))


def _gate_forward_scenario_exists(x: _GateInputs) -> GateResult:
    gid = "forward_scenario_exists"
    if _clean_str(x.forward_scenario_ref):
        return _passed(gid, "forward-scenario packet present ({0})".format(x.forward_scenario_ref))
    return _failed(gid, "no forward-scenario packet -- the forward view is absent", "block")


def _gate_red_team_no_thesis_killer(x: _GateInputs) -> GateResult:
    gid = "red_team_no_thesis_killer"
    if not _clean_str(x.red_team_ref):
        return _failed(gid, "no red-team review ref -- thesis-killer risk is unassessed", "block")
    if x.unresolved_thesis_killer:
        return _failed(gid, "an UNRESOLVED red-team thesis-killer risk is present -- the thesis "
                            "is not cleared", "block")
    return _passed(gid, "red-team review present ({0}); no unresolved thesis-killer".format(
        x.red_team_ref))


def _gate_technical_timing_acceptable(x: _GateInputs) -> GateResult:
    gid = "technical_timing_acceptable"
    if not _clean_str(x.technical_timing_ref) or not x.technical_timing_acceptable:
        return _failed(gid, "no acceptable TechnicalTimingSetup -- 022C is not built, so technical "
                            "timing cannot be assessed yet (not yet assessed)", "active_diligence")
    return _passed(gid, "acceptable technical-timing setup present ({0})".format(
        x.technical_timing_ref))


def _gate_portfolio_fit_acceptable(x: _GateInputs) -> GateResult:
    gid = "portfolio_fit_acceptable"
    if not _clean_str(x.portfolio_fit_ref) or not x.portfolio_fit_acceptable:
        return _failed(gid, "no acceptable PortfolioFit -- 022D is not built, so portfolio fit "
                            "cannot be assessed yet (not yet assessed)", "active_diligence")
    return _passed(gid, "acceptable portfolio-fit assessment present ({0})".format(
        x.portfolio_fit_ref))


def _gate_sizing_guardrail_exists(x: _GateInputs) -> GateResult:
    gid = "sizing_guardrail_exists"
    if _clean_str(x.sizing_guardrail):
        return _passed(gid, "sizing guardrail present (qualitative range)")
    return _failed(gid, "no sizing guardrail -- a manual-review pick must carry a qualitative "
                        "sizing range", "block")


def _gate_invalidation_condition_exists(x: _GateInputs) -> GateResult:
    gid = "invalidation_condition_exists"
    conds = tuple(c for c in (x.invalidation_conditions or ()) if _clean_str(c))
    if conds:
        return _passed(gid, "{0} invalidation condition(s) present".format(len(conds)))
    return _failed(gid, "no invalidation condition -- a pick must state what breaks the thesis",
                   "block")


def _gate_exit_watch_condition_exists(x: _GateInputs) -> GateResult:
    gid = "exit_watch_condition_exists"
    conds = tuple(c for c in (x.exit_watch_conditions or ()) if _clean_str(c))
    if conds:
        return _passed(gid, "{0} exit / watch condition(s) present".format(len(conds)))
    return _failed(gid, "no exit / watch condition -- a pick must state its exit watch", "block")


# The 15 hard gates, in canonical order. Actionable requires ALL to pass.
RECOMMENDATION_HARD_GATES: Tuple[HardGate, ...] = (
    HardGate("candidate_eligibility",
             "The CapitalCandidate ref is ELIGIBLE (full 020A provenance lineage; real, non-demo).",
             _gate_candidate_eligibility),
    HardGate("trust_data_quality",
             "The producing run's data quality is healthy or explicitly-acceptable-with-gaps.",
             _gate_trust_data_quality),
    HardGate("source_freshness",
             "Source evidence is fresh / recent -- not stale / expired.",
             _gate_source_freshness),
    HardGate("multi_source_corroboration",
             ">=2 independent non-social sources; a social/rumor source never counts.",
             _gate_multi_source_corroboration),
    HardGate("theme_pulse_strength",
             "The ThemePulse is strengthening or already strong (not weak / data-insufficient).",
             _gate_theme_pulse_strength),
    HardGate("value_chain_bottleneck_exposure",
             "Explicit value-chain / bottleneck exposure on the graph.",
             _gate_value_chain_bottleneck_exposure),
    HardGate("company_evidence_beneficiary",
             "Company-level evidence supports beneficiary status (non-social).",
             _gate_company_evidence_beneficiary),
    HardGate("investment_diligence_complete",
             "The diligence thesis is present and complete enough.",
             _gate_investment_diligence_complete),
    HardGate("forward_scenario_exists",
             "A forward-scenario packet exists.",
             _gate_forward_scenario_exists),
    HardGate("red_team_no_thesis_killer",
             "A red-team review exists with no unresolved thesis-killer risk.",
             _gate_red_team_no_thesis_killer),
    HardGate("technical_timing_acceptable",
             "A TechnicalTimingSetup ref with an acceptable setup (022C -- cannot pass yet).",
             _gate_technical_timing_acceptable),
    HardGate("portfolio_fit_acceptable",
             "A PortfolioFit ref that is acceptable (022D -- cannot pass yet).",
             _gate_portfolio_fit_acceptable),
    HardGate("sizing_guardrail_exists",
             "A qualitative sizing guardrail exists.",
             _gate_sizing_guardrail_exists),
    HardGate("invalidation_condition_exists",
             "An invalidation condition exists.",
             _gate_invalidation_condition_exists),
    HardGate("exit_watch_condition_exists",
             "An exit / watch condition exists.",
             _gate_exit_watch_condition_exists),
)

# The 15 gate ids, in canonical order.
HARD_GATE_IDS: Tuple[str, ...] = tuple(g.gate_id for g in RECOMMENDATION_HARD_GATES)


# --------------------------------------------------------------------------- #
# The engine                                                                    #
# --------------------------------------------------------------------------- #
def _worst_failure(results: Tuple[GateResult, ...]) -> Optional[GateResult]:
    """The dominating failed gate: highest-precedence failure_mode, then canonical gate order."""
    order = {gid: i for i, gid in enumerate(HARD_GATE_IDS)}
    failed = [r for r in results if not r.passed]
    if not failed:
        return None
    failed.sort(key=lambda r: (_FAILURE_PRECEDENCE.get(r.failure_mode, 99),
                               order.get(r.gate_id, 99)))
    return failed[0]


def evaluate_recommendation(
    *,
    run_id: str,
    ticker: str,
    now: str,
    candidate: Optional[CapitalCandidate] = None,
    data_quality_ref: str = "",
    data_quality_state: str = "",
    source_freshness: str = "",
    corroboration_sources: Tuple[Any, ...] = (),
    theme_pulse_state: str = "",
    bottleneck_exposure_refs: Tuple[str, ...] = (),
    company_evidence_refs: Tuple[Any, ...] = (),
    investment_diligence_ref: str = "",
    diligence_complete: bool = False,
    forward_scenario_ref: str = "",
    red_team_ref: str = "",
    unresolved_thesis_killer: bool = False,
    technical_timing_ref: str = "",
    technical_timing_acceptable: bool = False,
    portfolio_fit_ref: str = "",
    portfolio_fit_acceptable: bool = False,
    sizing_guardrail: str = "",
    invalidation_conditions: Tuple[str, ...] = (),
    exit_watch_conditions: Tuple[str, ...] = (),
    # passthrough narrative / graph refs (never gate inputs)
    company_name: str = "",
    mode: str = "",
    theme_ref: str = "",
    mega_theme_ref: str = "",
    value_chain_ref: str = "",
    bottleneck_ref: str = "",
    source_provenance: Tuple[str, ...] = (),
    evidence_summary: str = "",
    key_thesis: str = "",
    why_now: str = "",
    expected_catalysts: Tuple[str, ...] = (),
    primary_risks: Tuple[str, ...] = (),
    data_gaps: Tuple[str, ...] = (),
    recommendation_time_horizon: str = "",
) -> Tuple[RecommendationGateOutcome, CapitalRecommendation]:
    """Run all 15 hard gates and build the honest :class:`CapitalRecommendation`.

    Returns ``(RecommendationGateOutcome, CapitalRecommendation)``:

    * **ALL 15 gates pass** -> ``actionable_pick_manual_review``, built THROUGH the 022A model
      (:func:`~reality_mesh.recommendation.assess_recommendation`), which independently re-checks
      the full ref set -- the engine never bypasses the unforgeable-actionable invariant.
    * **A hard (``block``) gate fails** -> ``blocked`` whose ``blocked_reason`` is the EXACT
      dominating failed-gate reason (canonical-order first).
    * **Only soft failures remain** -> ``watch`` (a social/rumor-only basis) or
      ``active_diligence`` (a sound basis whose diligence / timing / portfolio pieces are merely
      incomplete). Never actionable.

    Deterministic: the id derives from ``run_id`` + ``ticker`` and ``now`` is injected.
    """
    if not _clean_str(run_id):
        raise ValueError("evaluate_recommendation requires a non-empty run_id")
    if not _clean_str(ticker):
        raise ValueError("evaluate_recommendation requires a non-empty ticker")

    symbol = _clean_str(ticker).upper()
    run = _clean_str(run_id)
    cand = candidate
    # The underlying candidate id field is ALWAYS populated (022A requires it): the real
    # candidate's id when present, else the deterministic id the candidate WOULD carry.
    candidate_id = _clean_str(getattr(cand, "candidate_id", "")) or candidate_id_for(run, symbol)
    # ``capital_candidate_ref`` claims an ELIGIBLE candidate -- only set when genuinely eligible,
    # so a blocked / downgraded record never falsely claims capital standing.
    capital_candidate_ref = cand.candidate_id if (
        isinstance(cand, CapitalCandidate) and cand.is_eligible) else ""
    run_mode = _clean_str(mode) or _clean_str(getattr(cand, "mode", "")) or "pulse"

    inputs = _GateInputs(
        ticker=symbol,
        candidate=cand,
        data_quality_ref=_clean_str(data_quality_ref),
        data_quality_state=_clean_str(data_quality_state),
        source_freshness=_clean_str(source_freshness),
        corroboration_sources=tuple(corroboration_sources or ()),
        theme_pulse_state=_clean_str(theme_pulse_state),
        bottleneck_exposure_refs=tuple(bottleneck_exposure_refs or ()),
        company_evidence_refs=tuple(company_evidence_refs or ()),
        investment_diligence_ref=_clean_str(investment_diligence_ref),
        diligence_complete=bool(diligence_complete),
        forward_scenario_ref=_clean_str(forward_scenario_ref),
        red_team_ref=_clean_str(red_team_ref),
        unresolved_thesis_killer=bool(unresolved_thesis_killer),
        technical_timing_ref=_clean_str(technical_timing_ref),
        technical_timing_acceptable=bool(technical_timing_acceptable),
        portfolio_fit_ref=_clean_str(portfolio_fit_ref),
        portfolio_fit_acceptable=bool(portfolio_fit_acceptable),
        sizing_guardrail=_clean_str(sizing_guardrail),
        invalidation_conditions=tuple(invalidation_conditions or ()),
        exit_watch_conditions=tuple(exit_watch_conditions or ()),
    )

    results = tuple(gate.evaluate(inputs) for gate in RECOMMENDATION_HARD_GATES)

    # Source provenance for the built record: explicit, else derived from the real corroboration.
    provenance = tuple(str(p) for p in (source_provenance or ()) if _clean_str(p)) \
        or _real_corroboration_ids(inputs.corroboration_sources)

    common = dict(
        candidate_id=candidate_id, company_name=company_name, mode=run_mode,
        recommendation_time_horizon=recommendation_time_horizon,
        theme_ref=theme_ref, mega_theme_ref=mega_theme_ref, value_chain_ref=value_chain_ref,
        bottleneck_ref=bottleneck_ref,
        capital_candidate_ref=capital_candidate_ref,
        investment_diligence_ref=inputs.investment_diligence_ref,
        forward_scenario_ref=inputs.forward_scenario_ref,
        portfolio_fit_ref=inputs.portfolio_fit_ref,
        technical_timing_ref=inputs.technical_timing_ref,
        red_team_ref=inputs.red_team_ref,
        data_quality_ref=inputs.data_quality_ref,
        source_provenance=provenance,
        evidence_summary=evidence_summary, key_thesis=key_thesis, why_now=why_now,
        expected_catalysts=tuple(expected_catalysts or ()),
        primary_risks=tuple(primary_risks or ()),
        data_gaps=tuple(data_gaps or ()),
        invalidation_conditions=inputs.invalidation_conditions,
        exit_watch_conditions=inputs.exit_watch_conditions,
        sizing_guardrail=inputs.sizing_guardrail,
    )

    worst = _worst_failure(results)

    if worst is None:
        # ALL 15 gates passed -> actionable, built THROUGH the 022A model (re-checks the ref set).
        recommendation = assess_recommendation(
            ticker=symbol, run_id=run,
            intended_state="actionable_pick_manual_review", now=now, **common)
        # Honesty guard: if 022A refused (a ref genuinely missing), reflect its honest state.
        if recommendation.is_actionable_pick:
            outcome = RecommendationGateOutcome(
                state="actionable_pick_manual_review",
                label=RECOMMENDATION_STATE_LABELS["actionable_pick_manual_review"],
                gate_results=results)
        else:
            outcome = RecommendationGateOutcome(
                state=recommendation.recommendation_state,
                label=recommendation.recommendation_label,
                blocked_reason=recommendation.blocked_reason,
                gate_results=results)
        return outcome, recommendation

    state = _FAILURE_TO_STATE[worst.failure_mode]
    reason = "gate {0!r} failed: {1}".format(worst.gate_id, worst.reason)

    if state == "blocked":
        recommendation = CapitalRecommendation(
            recommendation_id=recommendation_id_for(run, symbol), run_id=run,
            generated_at=str(now), ticker=symbol,
            recommendation_state="blocked",
            recommendation_label=RECOMMENDATION_STATE_LABELS["blocked"],
            publication_state="blocked", blocked_reason=reason, **common)
        return (RecommendationGateOutcome(
            state="blocked", label=RECOMMENDATION_STATE_LABELS["blocked"],
            blocked_reason=reason, gate_results=results), recommendation)

    # A downgrade (watch / active_diligence): a non-actionable, non-blocked review label.
    recommendation = CapitalRecommendation(
        recommendation_id=recommendation_id_for(run, symbol), run_id=run,
        generated_at=str(now), ticker=symbol,
        recommendation_state=state,
        recommendation_label=RECOMMENDATION_STATE_LABELS[state],
        publication_state="draft", **common)
    return (RecommendationGateOutcome(
        state=state, label=RECOMMENDATION_STATE_LABELS[state],
        downgrade_reason=reason, gate_results=results), recommendation)


# --------------------------------------------------------------------------- #
# Construction-time guard: none of the gate shapes may carry a trade/score field. #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(GateResult)
assert_no_trade_fields(HardGate)
assert_no_trade_fields(RecommendationGateOutcome)
assert_no_trade_fields(_GateInputs)
