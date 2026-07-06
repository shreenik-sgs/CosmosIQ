"""The Recommendation Activation Gate (IMPLEMENTATION-022H). PURE, OFFLINE, deterministic.

Phases 012-022G shipped the offline reality mesh, the 019B/020A capital-candidate contract +
publish path, the 022B recommendation gates, the 022D portfolio-fit gate, the 022E Capital Picks
report, the 022F paper recommendation journal, and the 022G historical replay calibration. THIS
slice is the FORMAL, evidence-based gate that decides whether CosmosIQ may be REPRESENTED and
OPERATED in a production RECOMMENDATION mode -- and this module is its DETERMINISTIC,
OFFLINE-TESTABLE CORE. It MIRRORS the 020F production-activation discipline
(:mod:`cosmosiq_service.activation`) exactly, one layer up: for the recommendation surface rather
than the 24x7 service. It CONSUMES the 020F activation core (its ``ChecklistStatus`` /
``CheckResult`` / ``OperatorApproval`` / ``is_valid_approval`` / ``read_operator_signoff``); it
never re-implements them.

The whole point of this slice is that a production recommendation mode CANNOT be enabled by
accident or by wishful representation. The rule is unforgiving::

    recommendation_mode_allowed = (no item is fail)
                              AND (no BLOCKING item is manual_review_required or fail)
                              AND is_valid_approval(operator_approval)

Some preconditions CANNOT be machine-verified OFFLINE -- a REAL live-source-health fetch and the
human operator sign-off. Those items are ``manual_review_required`` and BLOCKING, so an honest
OFFLINE evaluation REFUSES a production recommendation mode and lands at the "shadow only" verdict
until they are satisfied AND explicitly approved. That is the CORRECT outcome, not a failure. The
default recommendation mode is ``shadow`` -- NEVER ``production_manual_review``.

The machine-verifiable items (candidate publication / recommendation gates / report render /
journal / calibration completed / trust data quality / alert safety / portfolio fit / no fixture
leakage / no trade control / no hidden score) are computed from REAL checks against the consumed
022x layers by :func:`run_recommendation_checks`; ``live_source_health`` and ``operator_signoff``
stay manual + blocking (the sign-off item is cleared ONLY by a valid recorded operator approval,
the same one the 020F sign-off reader produces).

The promotion state machine allows ``OFF`` / ``SHADOW`` -> ``MANUAL_REVIEW`` freely, but
``MANUAL_REVIEW`` -> ``PRODUCTION_MANUAL_REVIEW`` ONLY when the report allows it AND an explicit
operator approval is recorded; it REFUSES any auto / unapproved jump.

Stdlib-only, Python 3.9. No network, no wall clock (every instant is an injected ``now``), no
subprocess, no secret. Labels + refs only -- there is NO score / rank / rating field and NO
trade / purchase / disposal directive anywhere. Importing this module starts nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from cosmosiq_service.activation import (
    STATUSES,
    ChecklistStatus,
    CheckResult,
    OperatorApproval,
    is_valid_approval,
    read_operator_signoff,
)

from .alert_delivery import AlertDeliveryPolicy, AlertDeliveryStatus
from .alerts import Alert
from .capital_candidate import CapitalCandidate, assess_candidate_eligibility
from .capital_picks_report import REPORT_TITLE, render_capital_picks_report
from .portfolio_fit import PortfolioFit, assess_portfolio_fit, portfolio_fit_acceptable
from .recommendation import CapitalRecommendation
from .recommendation_gates import RecommendationGateOutcome, evaluate_recommendation
from .recommendation_journal import (
    RecommendationJournalEntry,
    journal_recommendation,
    journaled,
)
from .replay_calibration import (
    SCENARIO_KINDS,
    build_illustrative_cases,
    calibration_results,
    calibration_summary,
    record_calibration,
    run_replay_calibration,
)
from .validation import assert_no_trade_fields

__all__ = [
    "RecommendationMode",
    "RECOMMENDATION_MODES",
    "RecommendationVerdict",
    "RECOMMENDATION_ACTIVATION_ITEMS",
    "RecommendationActivationItem",
    "RecommendationActivationReport",
    "run_recommendation_checks",
    "evaluate_recommendation_activation",
    "can_enter_production_recommendation",
    "default_recommendation_mode",
    "RecommendationPromotionDecision",
    "promote_recommendation_mode",
    "rollback_recommendation_mode",
    "MODE_LADDER",
    "read_operator_signoff",
    "OperatorApproval",
    "is_valid_approval",
]


# --------------------------------------------------------------------------- #
# 0. The closed recommendation-mode + verdict vocabularies                      #
# --------------------------------------------------------------------------- #
class RecommendationMode:
    """The CLOSED recommendation-mode vocabulary. ``SHADOW`` is the DEFAULT.

    ``PRODUCTION_MANUAL_REVIEW`` is NEVER the default and is reachable only through the gate. The
    modes climb a safety ladder: ``off`` (nothing surfaced) < ``shadow`` (recommendations produced
    but never represented as production) < ``manual_review`` (an operator reviews them offline) <
    ``production_manual_review`` (surfaced as production, still manual-review-only, never execution).
    """

    OFF = "off"
    SHADOW = "shadow"                       # the DEFAULT
    MANUAL_REVIEW = "manual_review"
    PRODUCTION_MANUAL_REVIEW = "production_manual_review"

    DEFAULT = "shadow"

    @classmethod
    def parse(cls, value: object) -> str:
        text = str(getattr(value, "value", value) or "").strip().lower()
        if text not in RECOMMENDATION_MODES:
            raise ValueError(
                "invalid recommendation mode {0!r} (closed vocabulary: {1})".format(
                    value, list(RECOMMENDATION_MODES)))
        return text


RECOMMENDATION_MODES: Tuple[str, ...] = (
    RecommendationMode.OFF,
    RecommendationMode.SHADOW,
    RecommendationMode.MANUAL_REVIEW,
    RecommendationMode.PRODUCTION_MANUAL_REVIEW,
)


class RecommendationVerdict:
    """The CLOSED verdict vocabulary for a recommendation-activation report."""

    PRODUCTION_APPROVED = "production_manual_review_approved"
    SHADOW_ONLY = "shadow_only"
    BLOCKED = "blocked_remediation_required"
    AWAITING_APPROVAL = "awaiting_operator_approval"


# --------------------------------------------------------------------------- #
# 1. The checklist item + the machine-checkable checklist template              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RecommendationActivationItem:
    """One recommendation-activation precondition (ChecklistItem-style).

    An ``id``, a ``description``, a closed ``status`` (one of :data:`STATUSES`), an ``evidence``
    path/ref, whether it ``blocking``-forbids a production recommendation mode while unmet, and any
    ``notes``. Labels only -- there is NO score / rank / trade field anywhere.
    """

    id: str
    description: str
    status: str = ChecklistStatus.MANUAL_REVIEW_REQUIRED
    evidence: str = ""
    blocking: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(
                "RecommendationActivationItem.status {0!r} invalid (closed vocabulary: {1})".format(
                    self.status, list(STATUSES)))

    @property
    def blocks_production(self) -> bool:
        """True iff this item, in its current state, forbids a production recommendation mode."""
        if self.status == ChecklistStatus.FAIL:
            return True
        if self.blocking and self.status == ChecklistStatus.MANUAL_REVIEW_REQUIRED:
            return True
        return False


@dataclass(frozen=True)
class _ItemSpec:
    """One internal item spec: id, description, blocking, and whether it is manual-only."""

    id: str
    description: str
    blocking: bool = True
    is_manual: bool = False        # cannot be machine-verified OFFLINE -> manual_review_required
    evidence_hint: str = ""


# The recommendation-activation checklist, in review sequence. Every item is BLOCKING -- the gate is
# strict. Manual items (live_source_health, operator_signoff) can never be cleared from code.
_ITEM_SPECS: Tuple[_ItemSpec, ...] = (
    _ItemSpec("pipeline_020_stable",
              "the 020 production-activation core is wired and safe-by-default (its gate refuses "
              "production_mode by default in an honest OFFLINE evaluation)",
              evidence_hint="cosmosiq_service.activation"),
    _ItemSpec("live_source_health",
              "a REAL live-source-health fetch confirms the sources are reachable and fresh",
              is_manual=True, evidence_hint="manual: live fetch"),
    _ItemSpec("capital_candidate_publication_works",
              "the 020A candidate publish path works: an eligible candidate exists ONLY with full "
              "provenance lineage; a missing-lineage candidate is ineligible",
              evidence_hint="capital_candidate"),
    _ItemSpec("recommendation_gates_work",
              "the 022B recommendation gates discriminate: complete evidence reaches actionable; "
              "weak evidence is honestly blocked",
              evidence_hint="recommendation_gates"),
    _ItemSpec("capital_picks_report_renders",
              "the 022E Capital Picks report renders deterministically with the canonical title "
              "and no trade verb",
              evidence_hint="capital_picks_report"),
    _ItemSpec("recommendation_journal_works",
              "the 022F paper recommendation journal records append-only and re-journalling is "
              "idempotent (byte-identical)",
              evidence_hint="recommendation_journal"),
    _ItemSpec("historical_replay_calibration_completed",
              "the 022G historical replay calibration has COMPLETED over every scenario kind and "
              "matched every conservative expectation",
              evidence_hint="replay_calibration"),
    _ItemSpec("trust_data_quality_pass",
              "the trust / data-quality discipline holds: a degraded / unstated producing run is "
              "blocked; only a healthy run proceeds",
              evidence_hint="recommendation_gates"),
    _ItemSpec("alert_safety_pass",
              "the 020E alert-safety policy suppresses external escalation for the production mode "
              "pre-activation (no escalation is possible)",
              evidence_hint="alert_delivery"),
    _ItemSpec("portfolio_fit_gates_work",
              "the 022D portfolio-fit gate is conservative: it refuses an absent / insufficient "
              "portfolio and never fabricates exposure",
              evidence_hint="portfolio_fit"),
    _ItemSpec("no_fixture_leakage",
              "fixture / demo data can never be surfaced as actionable: a demo-mode candidate is "
              "refused by the recommendation gates",
              evidence_hint="recommendation_gates"),
    _ItemSpec("no_trading_control",
              "no trade / execution control (a purchase / disposal affordance) exists on any "
              "recommendation-layer shape",
              evidence_hint="validation"),
    _ItemSpec("no_hidden_score",
              "no hidden score / rank / rating field exists on any recommendation-layer shape",
              evidence_hint="validation"),
    _ItemSpec("operator_signoff",
              "the human production sign-off / operator approval is recorded (the 020F sign-off "
              "reader yields the approval)",
              is_manual=True, evidence_hint="manual: operator approval"),
)

# The machine-verifiable item ids (everything except the two manual items).
_MACHINE_ITEM_IDS: Tuple[str, ...] = tuple(s.id for s in _ITEM_SPECS if not s.is_manual)
# The manual, always-blocking item ids.
_MANUAL_ITEM_IDS: Tuple[str, ...] = tuple(s.id for s in _ITEM_SPECS if s.is_manual)


# The blank checklist template (every item manual_review_required until evaluated).
RECOMMENDATION_ACTIVATION_ITEMS: Tuple[RecommendationActivationItem, ...] = tuple(
    RecommendationActivationItem(
        id=spec.id, description=spec.description,
        status=ChecklistStatus.MANUAL_REVIEW_REQUIRED,
        evidence=spec.evidence_hint, blocking=spec.blocking,
        notes=("cannot be machine-verified OFFLINE -- manual review required"
               if spec.is_manual else "not yet evaluated"))
    for spec in _ITEM_SPECS)


# --------------------------------------------------------------------------- #
# 2. run_recommendation_checks -- the REAL machine checks over the 022x layers   #
# --------------------------------------------------------------------------- #
def _normalise_status(raw: object) -> str:
    text = str(raw or "").strip().lower()
    if text in STATUSES:
        return text
    if text in ("skipped", "skip", "unknown", ""):
        return ChecklistStatus.MANUAL_REVIEW_REQUIRED
    if text in ("ok", "passed", "success"):
        return ChecklistStatus.PASS
    if text in ("failed", "error"):
        return ChecklistStatus.FAIL
    return ChecklistStatus.MANUAL_REVIEW_REQUIRED


def _result(name: str, ok: bool, detail: str) -> CheckResult:
    return CheckResult(name, ChecklistStatus.PASS if ok else ChecklistStatus.FAIL, (detail,))


def _case_gate_kwargs(case, now: str) -> Dict[str, object]:
    """The exact kwargs handed to the UNCHANGED 022B gate engine for an illustrative case."""
    return dict(
        run_id=case.run_id, ticker=case.ticker, now=now, company_name=case.company_name,
        candidate=case.candidate,
        data_quality_ref=case.data_quality_ref, data_quality_state=case.data_quality_state,
        source_freshness=case.source_freshness,
        corroboration_sources=tuple(case.corroboration_sources or ()),
        theme_pulse_state=case.theme_pulse_state,
        bottleneck_exposure_refs=tuple(case.bottleneck_exposure_refs or ()),
        company_evidence_refs=tuple(case.company_evidence_refs or ()),
        investment_diligence_ref=case.investment_diligence_ref,
        diligence_complete=case.diligence_complete,
        forward_scenario_ref=case.forward_scenario_ref,
        red_team_ref=case.red_team_ref, unresolved_thesis_killer=case.unresolved_thesis_killer,
        technical_timing_ref=case.technical_timing_ref,
        technical_timing_acceptable=case.technical_timing_acceptable,
        portfolio_fit_ref=case.portfolio_fit_ref,
        portfolio_fit_acceptable=case.portfolio_fit_acceptable,
        sizing_guardrail=case.sizing_guardrail,
        invalidation_conditions=tuple(case.invalidation_conditions or ()),
        exit_watch_conditions=tuple(case.exit_watch_conditions or ()),
    )


def _strong_and_weak(now: str):
    """The strong (complete evidence) and weak (hype) illustrative cases from 022G."""
    cases = build_illustrative_cases(now)
    by_kind = {c.scenario_kind: c for c in cases}
    return (by_kind["strong_beneficiary_complete_evidence"], by_kind["hype_weak_evidence"])


# The recommendation-layer shapes that must carry NO trade / score field (structural guard).
_RECOMMENDATION_SHAPES = (
    CapitalRecommendation, RecommendationGateOutcome, RecommendationJournalEntry,
    CapitalCandidate, PortfolioFit,
)


def _check_pipeline_020_stable(store_dir: str, now: str) -> CheckResult:
    from cosmosiq_service.activation import Verdict, evaluate_activation
    try:
        report = evaluate_activation(store_dir, now=now)
    except Exception as exc:                                       # noqa: BLE001
        return _result("pipeline_020_stable", False,
                       "020 activation core raised {0}: {1}".format(
                           type(exc).__name__, str(exc)[:160]))
    known = {Verdict.PRODUCTION_APPROVED, Verdict.SHADOW_ONLY, Verdict.BLOCKED,
             Verdict.AWAITING_APPROVAL}
    ok = (report.production_mode_allowed is False) and (report.verdict in known)
    return _result("pipeline_020_stable", ok,
                   "020 gate present + safe-by-default: production_mode_allowed={0}, verdict={1!r}"
                   .format(report.production_mode_allowed, report.verdict))


def _check_candidate_publication(now: str) -> CheckResult:
    try:
        eligible = assess_candidate_eligibility(
            ticker="SYNTH-A", run_id="RUN-022H", reality_signal_refs=("sig-1",),
            opportunity_hypothesis_ref="hyp-1", investment_diligence_ref="THS-1",
            trust_data_quality_state="healthy", mode="pulse", now=now)
        missing = assess_candidate_eligibility(
            ticker="SYNTH-A", run_id="RUN-022H", reality_signal_refs=("sig-1",),
            opportunity_hypothesis_ref="hyp-1", investment_diligence_ref="",
            trust_data_quality_state="healthy", mode="pulse", now=now)
    except Exception as exc:                                       # noqa: BLE001
        return _result("capital_candidate_publication_works", False,
                       "publish path raised {0}: {1}".format(type(exc).__name__, str(exc)[:160]))
    ok = (eligible.is_eligible and not eligible.missing_lineage()
          and not missing.is_eligible)
    return _result("capital_candidate_publication_works", ok,
                   "eligible={0} (missing_lineage={1}); missing-diligence candidate eligible={2}"
                   .format(eligible.is_eligible, eligible.missing_lineage(), missing.is_eligible))


def _check_recommendation_gates(now: str) -> CheckResult:
    strong, weak = _strong_and_weak(now)
    try:
        strong_outcome, _r = evaluate_recommendation(**_case_gate_kwargs(strong, now))
        weak_outcome, _w = evaluate_recommendation(**_case_gate_kwargs(weak, now))
    except Exception as exc:                                       # noqa: BLE001
        return _result("recommendation_gates_work", False,
                       "gates raised {0}: {1}".format(type(exc).__name__, str(exc)[:160]))
    ok = (strong_outcome.state == "actionable_pick_manual_review"
          and weak_outcome.state == "blocked")
    return _result("recommendation_gates_work", ok,
                   "strong -> {0!r}; weak -> {1!r}".format(strong_outcome.state, weak_outcome.state))


def _check_report_renders(now: str) -> CheckResult:
    strong, _weak = _strong_and_weak(now)
    try:
        outcome, recommendation = evaluate_recommendation(**_case_gate_kwargs(strong, now))
        text = render_capital_picks_report(
            [recommendation], run_id=strong.run_id, generated_at=now)
    except Exception as exc:                                       # noqa: BLE001
        return _result("capital_picks_report_renders", False,
                       "report render raised {0}: {1}".format(type(exc).__name__, str(exc)[:160]))
    forbidden = ("place a trade", "auto-trade", "execute a purchase")
    clean = not any(phrase in text.lower() for phrase in forbidden)
    ok = REPORT_TITLE in text and clean and outcome.state == "actionable_pick_manual_review"
    return _result("capital_picks_report_renders", ok,
                   "title present={0}; no trade verb={1}; {2} chars".format(
                       REPORT_TITLE in text, clean, len(text)))


def _check_journal_works(store_dir: str, now: str) -> CheckResult:
    strong, _weak = _strong_and_weak(now)
    try:
        _outcome, recommendation = evaluate_recommendation(**_case_gate_kwargs(strong, now))
        journal_recommendation(store_dir, recommendation, now=now)
        after_first = len(journaled(store_dir))
        journal_recommendation(store_dir, recommendation, now=now)     # idempotent re-journal
        after_second = len(journaled(store_dir))
    except Exception as exc:                                       # noqa: BLE001
        return _result("recommendation_journal_works", False,
                       "journal raised {0}: {1}".format(type(exc).__name__, str(exc)[:160]))
    ok = after_first >= 1 and after_second == after_first
    return _result("recommendation_journal_works", ok,
                   "journaled {0} entry(ies); idempotent re-journal kept {1}".format(
                       after_first, after_second))


def _check_calibration_completed(store_dir: str, now: str) -> CheckResult:
    try:
        results = run_replay_calibration(build_illustrative_cases(now), now=now)
        summary = calibration_summary(results)
        record_calibration(store_dir, results, now=now)
        recorded = calibration_results(store_dir)
    except Exception as exc:                                       # noqa: BLE001
        return _result("historical_replay_calibration_completed", False,
                       "calibration raised {0}: {1}".format(type(exc).__name__, str(exc)[:160]))
    ok = (summary.get("cases_total", 0) == len(SCENARIO_KINDS)
          and summary.get("unmatched_expectation", 1) == 0
          and len(recorded) == len(SCENARIO_KINDS))
    return _result("historical_replay_calibration_completed", ok,
                   "cases_total={0}, unmatched={1}, recorded={2}".format(
                       summary.get("cases_total", 0), summary.get("unmatched_expectation", 0),
                       len(recorded)))


def _check_trust_data_quality(now: str) -> CheckResult:
    strong, _weak = _strong_and_weak(now)
    try:
        healthy_outcome, _h = evaluate_recommendation(**_case_gate_kwargs(strong, now))
        degraded_kwargs = _case_gate_kwargs(strong, now)
        degraded_kwargs["data_quality_state"] = "degraded"
        degraded_outcome, _d = evaluate_recommendation(**degraded_kwargs)
    except Exception as exc:                                       # noqa: BLE001
        return _result("trust_data_quality_pass", False,
                       "DQ check raised {0}: {1}".format(type(exc).__name__, str(exc)[:160]))
    dq_gate = next((g for g in healthy_outcome.gate_results
                    if g.gate_id == "trust_data_quality"), None)
    ok = (dq_gate is not None and dq_gate.passed
          and degraded_outcome.state == "blocked")
    return _result("trust_data_quality_pass", ok,
                   "healthy DQ gate passed={0}; degraded producing run -> {1!r}".format(
                       dq_gate.passed if dq_gate else None, degraded_outcome.state))


def _check_alert_safety(store_dir: str, now: str) -> CheckResult:
    try:
        policy = AlertDeliveryPolicy.default()
        alert = Alert(
            alert_id="ALERT-022H-001", run_id="RUN-022H", category="major_risk_emerged",
            severity="critical", human_readable_reason="observation for the 022H alert-safety probe",
            subject_tickers=("SYNTH-A",), evidence_refs=("finding.x",), created_at=now,
            dq_state="healthy")
        activated = policy.production_activated
        decision = policy.decide(is_external=True, mode="PRODUCTION_24X7", alert=alert)
    except Exception as exc:                                       # noqa: BLE001
        return _result("alert_safety_pass", False,
                       "alert-safety check raised {0}: {1}".format(
                           type(exc).__name__, str(exc)[:160]))
    ok = (activated is False) and (decision == AlertDeliveryStatus.SUPPRESSED_BY_POLICY)
    return _result("alert_safety_pass", ok,
                   "production_activated={0}; external production decision={1!r}".format(
                       activated, decision))


def _check_portfolio_fit(now: str) -> CheckResult:
    try:
        none_ok, _none_reason = portfolio_fit_acceptable(None)
        insufficient = assess_portfolio_fit("SYNTH-A", run_id="RUN-022H", now=now)
        insuff_ok, _reason = portfolio_fit_acceptable(insufficient)
    except Exception as exc:                                       # noqa: BLE001
        return _result("portfolio_fit_gates_work", False,
                       "portfolio-fit check raised {0}: {1}".format(
                           type(exc).__name__, str(exc)[:160]))
    ok = (none_ok is False and insuff_ok is False
          and insufficient.fit_state == "insufficient_portfolio_data")
    return _result("portfolio_fit_gates_work", ok,
                   "None acceptable={0}; no-holdings fit_state={1!r} acceptable={2}".format(
                       none_ok, insufficient.fit_state, insuff_ok))


def _check_no_fixture_leakage(now: str) -> CheckResult:
    strong, _weak = _strong_and_weak(now)
    try:
        demo_candidate = assess_candidate_eligibility(
            ticker="SYNTH-A", run_id="RUN-022H", reality_signal_refs=("sig-1",),
            opportunity_hypothesis_ref="hyp-1", investment_diligence_ref="THS-1",
            trust_data_quality_state="healthy", mode="demo", now=now)
        demo_kwargs = _case_gate_kwargs(strong, now)
        demo_kwargs["candidate"] = demo_candidate
        demo_kwargs["mode"] = "demo"
        outcome, _r = evaluate_recommendation(**demo_kwargs)
    except Exception as exc:                                       # noqa: BLE001
        return _result("no_fixture_leakage", False,
                       "fixture-leak check raised {0}: {1}".format(
                           type(exc).__name__, str(exc)[:160]))
    ok = outcome.state == "blocked"
    return _result("no_fixture_leakage", ok,
                   "demo-mode candidate -> {0!r} (fixture/demo can never be actionable)".format(
                       outcome.state))


def _check_no_trading_control() -> CheckResult:
    findings: List[str] = []
    for shape in _RECOMMENDATION_SHAPES:
        try:
            assert_no_trade_fields(shape)
        except AssertionError as exc:
            findings.append(str(exc))
    ok = not findings
    return _result("no_trading_control", ok,
                   "; ".join(findings) or "{0} recommendation shape(s): no trade/execution field"
                   .format(len(_RECOMMENDATION_SHAPES)))


def _check_no_concealed_metric_field() -> CheckResult:
    # assert_no_trade_fields also bans score/rank/rating -- the structural no-hidden-score guard.
    findings: List[str] = []
    for shape in _RECOMMENDATION_SHAPES:
        try:
            assert_no_trade_fields(shape)
        except AssertionError as exc:
            findings.append(str(exc))
    ok = not findings
    return _result("no_hidden_score", ok,
                   "; ".join(findings) or "{0} recommendation shape(s): no score/rank/rating field"
                   .format(len(_RECOMMENDATION_SHAPES)))


def run_recommendation_checks(store_dir: str, *, now: str) -> Dict[str, CheckResult]:
    """Run every machine-verifiable recommendation-activation check OFFLINE over the 022x layers.

    Returns an item-id -> :class:`CheckResult` mapping for the machine items ONLY (each an honest,
    deterministic pass/fail computed by actually exercising the consumed layer). The two manual
    items -- ``live_source_health`` and ``operator_signoff`` -- are NEVER produced here: they
    cannot be machine-verified OFFLINE and remain ``manual_review_required`` + BLOCKING. Feeding
    this mapping into :func:`evaluate_recommendation_activation` therefore still REFUSES a
    production recommendation mode (the honest OFFLINE outcome). ``now`` is injected everywhere;
    nothing is fetched.
    """
    if not str(now).strip():
        raise ValueError("run_recommendation_checks requires an injected 'now' instant")
    checks = (
        _check_pipeline_020_stable(store_dir, now),
        _check_candidate_publication(now),
        _check_recommendation_gates(now),
        _check_report_renders(now),
        _check_journal_works(store_dir, now),
        _check_calibration_completed(store_dir, now),
        _check_trust_data_quality(now),
        _check_alert_safety(store_dir, now),
        _check_portfolio_fit(now),
        _check_no_fixture_leakage(now),
        _check_no_trading_control(),
        _check_no_concealed_metric_field(),
    )
    return {c.name: c for c in checks}


# --------------------------------------------------------------------------- #
# 3. The report + the evaluation                                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RecommendationActivationReport:
    """The frozen result of evaluating the recommendation-activation checklist.

    ``recommendation_mode_allowed`` is the single unforgiving verdict: a production recommendation
    mode may be enabled ONLY when no item is ``fail``, no blocking item is
    ``manual_review_required`` / ``fail``, AND a valid operator approval is recorded.
    """

    recommendation_mode_allowed: bool
    verdict: str
    operator_approval_valid: bool
    blocking_failures: Tuple[str, ...] = field(default_factory=tuple)
    manual_review_items: Tuple[str, ...] = field(default_factory=tuple)
    items: Tuple[RecommendationActivationItem, ...] = field(default_factory=tuple)
    evidence_paths: Tuple[str, ...] = field(default_factory=tuple)

    def item(self, item_id: str) -> Optional[RecommendationActivationItem]:
        for i in self.items:
            if i.id == item_id:
                return i
        return None


def evaluate_recommendation_activation(
        store_dir: str, *, now: str,
        operator_approval: Optional[OperatorApproval] = None,
        checks: Optional[Mapping[str, object]] = None) -> RecommendationActivationReport:
    """Evaluate the recommendation-activation checklist and return the frozen report.

    ``checks`` maps an item id to a machine :class:`CheckResult` (or any object exposing
    ``.status``) -- normally the output of :func:`run_recommendation_checks`. For a machine item
    NOT supplied the status defaults to ``manual_review_required`` (BLOCKING, safe): a machine
    item that was never run cannot be claimed as passing. ``live_source_health`` stays
    ``manual_review_required`` unless a supplied check clears it (it cannot be machine-verified
    OFFLINE). ``operator_signoff`` is cleared ONLY by a valid recorded ``operator_approval`` (the
    same object the 020F sign-off reader produces) or an explicitly supplied check; otherwise it
    is ``manual_review_required`` + BLOCKING.

    This is why an honest OFFLINE evaluation, even with every machine check passing, REFUSES a
    production recommendation mode and lands at ``shadow_only``: the live-source-health and
    operator-sign-off items still block. Deterministic + offline: ``now`` is injected.
    """
    if not str(now).strip():
        raise ValueError("evaluate_recommendation_activation requires an injected 'now' instant")
    supplied: Dict[str, object] = dict(checks or {})
    approval_valid = is_valid_approval(operator_approval)

    items = []
    for spec in _ITEM_SPECS:
        note = ""
        evidence = spec.evidence_hint
        if spec.id in supplied:
            result = supplied[spec.id]
            status = _normalise_status(getattr(result, "status", None))
            details = tuple(getattr(result, "details", ()) or ())
            note = "; ".join(str(d) for d in details) if details else ""
            ev = str(getattr(result, "evidence_path", "") or "")
            if ev:
                evidence = ev
        elif spec.id == "operator_signoff":
            # cleared ONLY by a valid recorded operator approval (the sign-off reader's output).
            status = ChecklistStatus.PASS if approval_valid \
                else ChecklistStatus.MANUAL_REVIEW_REQUIRED
            note = ("operator production sign-off recorded (valid approval)" if approval_valid
                    else "no valid recorded operator sign-off -- manual review required")
        elif spec.is_manual:
            status = ChecklistStatus.MANUAL_REVIEW_REQUIRED
            note = "cannot be machine-verified OFFLINE -- manual review required"
        else:
            # A machine item that was never run cannot be claimed as passing (safe default).
            status = ChecklistStatus.MANUAL_REVIEW_REQUIRED
            note = "not evaluated (no machine result supplied) -- treated as pending"
        items.append(RecommendationActivationItem(
            id=spec.id, description=spec.description, status=status,
            evidence=evidence, blocking=spec.blocking, notes=note))
    items = tuple(items)

    blocking_failures = tuple(i.id for i in items if i.status == ChecklistStatus.FAIL)
    manual_review_items = tuple(
        i.id for i in items if i.status == ChecklistStatus.MANUAL_REVIEW_REQUIRED)

    any_fail = any(i.status == ChecklistStatus.FAIL for i in items)
    any_blocking_unmet = any(i.blocks_production for i in items)

    recommendation_mode_allowed = (
        (not any_fail) and (not any_blocking_unmet) and approval_valid)

    if recommendation_mode_allowed:
        verdict = RecommendationVerdict.PRODUCTION_APPROVED
    elif any_fail:
        verdict = RecommendationVerdict.BLOCKED
    elif any_blocking_unmet:
        # No machine failure, but blocking manual reviews remain -> the honest shadow verdict.
        verdict = RecommendationVerdict.SHADOW_ONLY
    else:
        # Everything satisfied but no valid approval recorded.
        verdict = RecommendationVerdict.AWAITING_APPROVAL

    evidence_paths = tuple(sorted({i.evidence for i in items if i.evidence}))

    return RecommendationActivationReport(
        recommendation_mode_allowed=recommendation_mode_allowed,
        verdict=verdict,
        operator_approval_valid=approval_valid,
        blocking_failures=blocking_failures,
        manual_review_items=manual_review_items,
        items=items,
        evidence_paths=evidence_paths)


# --------------------------------------------------------------------------- #
# 4. can_enter_production_recommendation + the default mode                      #
# --------------------------------------------------------------------------- #
def can_enter_production_recommendation(
        store_dir: str, *, operator_approval: Optional[OperatorApproval],
        now: str, checks: Optional[Mapping[str, object]] = None
        ) -> Tuple[bool, Tuple[str, ...]]:
    """Whether ``production_manual_review`` may be entered -- ``(allowed, reasons)``.

    ``allowed`` is ``False`` unless the gate allows it. In an honest OFFLINE call (no ``checks``
    supplied, or only the machine checks supplied) the manual items keep this ``False``: a
    production recommendation mode cannot be entered without the live-source-health fetch AND an
    explicit operator sign-off. ``reasons`` names every blocking failure, pending manual review,
    and a missing approval -- empty iff allowed.
    """
    report = evaluate_recommendation_activation(
        store_dir, now=now, operator_approval=operator_approval, checks=checks)
    if report.recommendation_mode_allowed:
        return True, ()
    reasons: List[str] = []
    reasons.extend("blocking failure: " + b for b in report.blocking_failures)
    reasons.extend("manual review pending: " + m for m in report.manual_review_items)
    if not report.operator_approval_valid:
        reasons.append("no valid explicit operator approval recorded")
    return False, tuple(reasons)


def default_recommendation_mode() -> str:
    """The default recommendation mode -- always ``shadow`` (never production_manual_review)."""
    return RecommendationMode.DEFAULT


# --------------------------------------------------------------------------- #
# 5. The promotion / rollback state machine                                     #
# --------------------------------------------------------------------------- #
# The mode safety ladder, low (safe) -> high (capable). Promotion climbs; rollback descends.
MODE_LADDER: Tuple[str, ...] = (
    RecommendationMode.OFF,
    RecommendationMode.SHADOW,
    RecommendationMode.MANUAL_REVIEW,
    RecommendationMode.PRODUCTION_MANUAL_REVIEW,
)
_LADDER_INDEX: Dict[str, int] = {mode: i for i, mode in enumerate(MODE_LADDER)}


@dataclass(frozen=True)
class RecommendationPromotionDecision:
    """The frozen outcome of a recommendation-mode promotion / rollback request."""

    allowed: bool
    from_mode: str
    to_mode: str
    reason: str
    blocking_reasons: Tuple[str, ...] = field(default_factory=tuple)


def promote_recommendation_mode(
        current_mode: object, target: object, *,
        report: Optional[RecommendationActivationReport] = None,
        operator_approval: Optional[OperatorApproval] = None
        ) -> RecommendationPromotionDecision:
    """Decide a recommendation-mode promotion from ``current_mode`` to ``target`` (an UPGRADE).

    * ``OFF`` / ``SHADOW`` -> ``SHADOW`` / ``MANUAL_REVIEW``: allowed freely.
    * ``MANUAL_REVIEW`` -> ``PRODUCTION_MANUAL_REVIEW``: allowed ONLY when
      ``report.recommendation_mode_allowed`` is True AND a valid ``operator_approval`` is recorded.
    * Any direct jump to ``PRODUCTION_MANUAL_REVIEW`` from below ``MANUAL_REVIEW``, and any auto /
      unapproved jump, is REFUSED. A downgrade request is refused here -- use
      :func:`rollback_recommendation_mode`.
    """
    current = RecommendationMode.parse(current_mode)
    to = RecommendationMode.parse(target)
    c_idx, t_idx = _LADDER_INDEX[current], _LADDER_INDEX[to]

    if to == current:
        return RecommendationPromotionDecision(True, current, to, "already in {0}".format(to))
    if t_idx < c_idx:
        return RecommendationPromotionDecision(
            False, current, to,
            "refused: {0} is a downgrade from {1} -- use rollback to step down".format(to, current))

    if to == RecommendationMode.PRODUCTION_MANUAL_REVIEW:
        if current != RecommendationMode.MANUAL_REVIEW:
            return RecommendationPromotionDecision(
                False, current, to,
                "refused: production_manual_review is reachable ONLY from manual_review",
                ("production must be promoted from manual_review, not {0}".format(current),))
        reasons: List[str] = []
        if report is None or not report.recommendation_mode_allowed:
            reasons.append("the activation report does not allow production_manual_review")
            if report is not None:
                reasons.extend("blocking failure: " + b for b in report.blocking_failures)
                reasons.extend("manual review pending: " + m
                               for m in report.manual_review_items)
        if not is_valid_approval(operator_approval):
            reasons.append("no valid explicit operator approval recorded")
        if reasons:
            return RecommendationPromotionDecision(
                False, current, to,
                "refused: production recommendation activation requires a passing report AND "
                "explicit approval", tuple(reasons))
        return RecommendationPromotionDecision(
            True, current, to,
            "promoted to production_manual_review: the activation report allows it and an explicit "
            "operator approval is recorded")

    # OFF/SHADOW -> SHADOW/MANUAL_REVIEW: an ordinary, freely-allowed upgrade below production.
    return RecommendationPromotionDecision(
        True, current, to,
        "promoted {0} -> {1} (below production_manual_review -- no activation gate required)".format(
            current, to))


def rollback_recommendation_mode(current_mode: object, target: object
                                 ) -> RecommendationPromotionDecision:
    """Decide a rollback (a DOWNGRADE) from ``current_mode`` to ``target``.

    A downgrade is ALWAYS allowed -- stepping down to a safer mode is never gated. An upgrade
    request is refused here (use :func:`promote_recommendation_mode`).
    """
    current = RecommendationMode.parse(current_mode)
    to = RecommendationMode.parse(target)
    c_idx, t_idx = _LADDER_INDEX[current], _LADDER_INDEX[to]
    if to == current:
        return RecommendationPromotionDecision(
            True, current, to, "already in {0} -- no rollback needed".format(to))
    if t_idx > c_idx:
        return RecommendationPromotionDecision(
            False, current, to,
            "refused: {0} is an upgrade from {1} -- use promote to step up".format(to, current))
    return RecommendationPromotionDecision(
        True, current, to,
        "rolled back {0} -> {1} (downgrade to a safer mode is always allowed)".format(current, to))


# --------------------------------------------------------------------------- #
# Construction-time guard: no recommendation-activation shape carries a trade    #
# / score field.                                                                #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(RecommendationActivationItem)
assert_no_trade_fields(RecommendationActivationReport)
assert_no_trade_fields(RecommendationPromotionDecision)
