"""The Production 24x7 Activation Gate (IMPLEMENTATION-020F). PURE, OFFLINE, deterministic.

Phases 012-020E shipped the offline reality mesh, the persistence / replay / gate chain, the
015 cadence + one-tick orchestrator, the 016 operator app, the 020C supervised service, the
020D shadow activation, and the 020E alert-delivery policy. THIS slice is the FORMAL,
evidence-based gate that decides whether CosmosIQ may be REPRESENTED and OPERATED as production
24x7 -- and this module is its DETERMINISTIC, OFFLINE-TESTABLE CORE. It holds only pure state
logic; the heavy machine checks run in :mod:`cosmosiq_ops.prod_check` and are handed in.

The whole point of this slice is that production CANNOT be enabled by accident or by wishful
representation. The rule is unforgiving::

    production_mode_allowed = (no item is fail)
                          AND (no BLOCKING item is manual_review_required or fail)
                          AND operator_approval is a valid recorded approval

Some preconditions CANNOT be machine-verified OFFLINE -- a real live-source-health fetch, a
completed operator shadow-validation run, the human production sign-off. Those items are
``manual_review_required`` and BLOCKING, so an honest OFFLINE evaluation REFUSES full production
and lands at the "shadow 24x7 only" verdict until they are satisfied AND explicitly approved.
That is the CORRECT outcome, not a failure.

The promotion state machine allows ``OFF`` / ``MANUAL`` -> ``SHADOW_24X7`` freely, but
``SHADOW_24X7`` -> ``PRODUCTION_24X7`` ONLY when the report allows it AND an explicit operator
approval is recorded; it REFUSES any auto / unapproved jump. :func:`rollback` always downgrades.

Stdlib-only, Python 3.9. No network, no wall clock (every instant is an injected ``now``), no
subprocess, no secret. Importing this module starts nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple

from .service import ServiceMode

__all__ = [
    "SECTIONS",
    "ChecklistStatus",
    "STATUSES",
    "BLOCKING_STATUSES",
    "Verdict",
    "ChecklistItem",
    "ActivationChecklist",
    "build_activation_checklist",
    "OperatorApproval",
    "is_valid_approval",
    "CheckResult",
    "ActivationReport",
    "evaluate_activation",
    "PromotionDecision",
    "promote",
    "rollback",
    "ROLLBACK_TRIGGERS",
    "MODE_LADDER",
    "can_enter_production",
]


# --------------------------------------------------------------------------- #
# 0. The closed status + verdict vocabularies                                   #
# --------------------------------------------------------------------------- #
class ChecklistStatus:
    """The CLOSED status vocabulary for one checklist item."""

    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


STATUSES: Tuple[str, ...] = (
    ChecklistStatus.PASS,
    ChecklistStatus.FAIL,
    ChecklistStatus.NOT_APPLICABLE,
    ChecklistStatus.MANUAL_REVIEW_REQUIRED,
)
# A BLOCKING item in either of these states forbids production (a fail forbids it unconditionally).
BLOCKING_STATUSES: frozenset = frozenset(
    {ChecklistStatus.FAIL, ChecklistStatus.MANUAL_REVIEW_REQUIRED})


class Verdict:
    """The CLOSED verdict vocabulary for an activation report."""

    PRODUCTION_APPROVED = "production_24x7_approved"
    SHADOW_ONLY = "shadow_24x7_only"
    BLOCKED = "blocked_remediation_required"
    AWAITING_APPROVAL = "awaiting_operator_approval"


# The eleven activation SECTIONS -- the whole readiness surface, in review order.
SECTIONS: Tuple[str, ...] = (
    "Build/Test",
    "Mode Configuration",
    "Source Configuration",
    "Scheduler/Service",
    "Persistence/Replay",
    "Trust/Data Quality",
    "Candidate Eligibility",
    "Alert Safety",
    "UI/Operator Surfaces",
    "Security/Secrets",
    "Runbook/Rollback",
)


# --------------------------------------------------------------------------- #
# 1. ChecklistItem + the checklist template                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChecklistItem:
    """One activation precondition: an id, its section, a description, a closed status,
    an evidence path, whether it BLOCKS production, and any notes.

    ``status`` is one of :data:`STATUSES`. ``blocking`` is ``True`` for every precondition that
    forbids production while unmet (all of 020F's items are blocking -- the gate is strict).
    """

    id: str
    section: str
    description: str
    status: str = ChecklistStatus.MANUAL_REVIEW_REQUIRED
    evidence_path: str = ""
    blocking: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(
                "ChecklistItem.status {0!r} invalid (closed vocabulary: {1})".format(
                    self.status, list(STATUSES)))
        if self.section not in SECTIONS:
            raise ValueError(
                "ChecklistItem.section {0!r} invalid (closed vocabulary: {1})".format(
                    self.section, list(SECTIONS)))

    @property
    def blocks_production(self) -> bool:
        """True iff this item, in its current state, forbids production."""
        if self.status == ChecklistStatus.FAIL:
            return True
        if self.blocking and self.status == ChecklistStatus.MANUAL_REVIEW_REQUIRED:
            return True
        return False


# One internal spec per item: id, section, description, blocking, is_manual (cannot be
# machine-verified OFFLINE -> stays manual_review_required unless evidence is recorded).
@dataclass(frozen=True)
class _ItemSpec:
    id: str
    section: str
    description: str
    blocking: bool = True
    is_manual: bool = False
    evidence_hint: str = ""


_ITEM_SPECS: Tuple[_ItemSpec, ...] = (
    # 1. Build/Test ---------------------------------------------------------- #
    _ItemSpec("suite_or_ci_gate", "Build/Test",
              "the full OFFLINE unittest suite / CI gate passes (019A run_ci_gate)",
              evidence_hint="ci_gate"),
    # 2. Mode Configuration -------------------------------------------------- #
    _ItemSpec("mode_state_machine", "Mode Configuration",
              "the service starts OFF; PRODUCTION_24X7 is never the default and stays gated",
              evidence_hint="service.py"),
    _ItemSpec("no_auto_promotion", "Mode Configuration",
              "production is reachable ONLY from SHADOW_24X7 with explicit approval (no auto jump)",
              evidence_hint="activation.py"),
    # 3. Source Configuration ------------------------------------------------ #
    _ItemSpec("sec_adapter_offline_smoke", "Source Configuration",
              "the 020B SEC EDGAR live adapter passes an OFFLINE mock-transport dry-run",
              evidence_hint="sec_edgar_live"),
    _ItemSpec("live_source_health", "Source Configuration",
              "a REAL live-source-health fetch confirms the sources are reachable and fresh",
              is_manual=True, evidence_hint="manual: live fetch"),
    # 4. Scheduler/Service --------------------------------------------------- #
    _ItemSpec("scheduler_dry_run", "Scheduler/Service",
              "a scheduler dry-run resolves one due-policy tick (no loop, injected now)",
              evidence_hint="scheduler"),
    _ItemSpec("service_wrapper_health", "Scheduler/Service",
              "the supervised service (020C) reports an honest, sanitized health snapshot",
              evidence_hint="service_health.json"),
    # 5. Persistence/Replay -------------------------------------------------- #
    _ItemSpec("replay_deterministic", "Persistence/Replay",
              "a persisted run REPLAYS deterministically (deterministic_match True)",
              evidence_hint="replay"),
    # 6. Trust/Data Quality -------------------------------------------------- #
    _ItemSpec("dq_gate_pass", "Trust/Data Quality",
              "the production DQ gates raise NO hard fail on the seeded run",
              evidence_hint="data_quality"),
    # 7. Candidate Eligibility ---------------------------------------------- #
    _ItemSpec("candidate_publication", "Candidate Eligibility",
              "the 020A publish path runs; an eligible candidate lands only with full provenance",
              evidence_hint="capital_candidates"),
    # 8. Alert Safety -------------------------------------------------------- #
    _ItemSpec("alert_safety_policy", "Alert Safety",
              "020E policy: NO external escalation is possible pre-activation + no forbidden phrase",
              evidence_hint="alert_delivery"),
    # 9. UI/Operator Surfaces ------------------------------------------------ #
    _ItemSpec("no_trade_control", "UI/Operator Surfaces",
              "the product UI carries NO buy/sell/order/broker/auto-trade control anywhere",
              evidence_hint="pages"),
    _ItemSpec("no_hidden_score", "UI/Operator Surfaces",
              "no hidden score/rank function exists in the intelligence packages",
              evidence_hint="ci_gate"),
    _ItemSpec("fixture_leakage", "UI/Operator Surfaces",
              "the DEFAULT product UI shows no real fixture ticker (no demo/fixture leakage)",
              evidence_hint="pages"),
    _ItemSpec("demo_byte_identical", "UI/Operator Surfaces",
              "the demo build is byte-identical run-to-run AND to the default build",
              evidence_hint="universe_ui"),
    _ItemSpec("operator_shadow_validation", "UI/Operator Surfaces",
              "a completed operator SHADOW-validation run (020D) is reviewed and signed off",
              is_manual=True, evidence_hint="manual: shadow validation"),
    # 10. Security/Secrets --------------------------------------------------- #
    _ItemSpec("secret_scan", "Security/Secrets",
              "no secret value in any rendered output and no tracked .env",
              evidence_hint="ci_gate"),
    # 11. Runbook/Rollback --------------------------------------------------- #
    _ItemSpec("rollback_docs", "Runbook/Rollback",
              "the 020F operator runbook + activation checklist docs exist",
              evidence_hint="docs"),
    _ItemSpec("operator_signoff", "Runbook/Rollback",
              "the human production sign-off / operator approval is recorded",
              is_manual=True, evidence_hint="manual: operator approval"),
)


@dataclass(frozen=True)
class ActivationChecklist:
    """The activation checklist -- the eleven sections and their items."""

    items: Tuple[ChecklistItem, ...] = field(default_factory=tuple)

    @property
    def sections(self) -> Tuple[str, ...]:
        return SECTIONS

    def for_section(self, section: str) -> Tuple[ChecklistItem, ...]:
        return tuple(i for i in self.items if i.section == section)

    @property
    def blocking_items(self) -> Tuple[ChecklistItem, ...]:
        return tuple(i for i in self.items if i.blocking)


def build_activation_checklist() -> ActivationChecklist:
    """The blank checklist template (every item ``manual_review_required`` until evaluated)."""
    return ActivationChecklist(items=tuple(
        ChecklistItem(
            id=spec.id, section=spec.section, description=spec.description,
            status=ChecklistStatus.MANUAL_REVIEW_REQUIRED,
            evidence_path=spec.evidence_hint, blocking=spec.blocking,
            notes=("cannot be machine-verified OFFLINE -- manual review required"
                   if spec.is_manual else "not yet evaluated"))
        for spec in _ITEM_SPECS))


# --------------------------------------------------------------------------- #
# 2. The operator approval -- an explicit, recorded human sign-off              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OperatorApproval:
    """An explicit, recorded operator approval to activate a target mode.

    A VALID approval carries a non-empty ``approved_by`` identity, a non-empty ``approved_at``
    injected instant, and a ``target_mode`` that parses to the mode being approved. This is the
    human sign-off the gate REQUIRES for production; there is no automatic promotion.
    """

    approved_by: str = ""
    approved_at: str = ""
    target_mode: str = ServiceMode.PRODUCTION_24X7.value
    statement: str = ""


def is_valid_approval(approval: Optional[OperatorApproval], *,
                      target: ServiceMode = ServiceMode.PRODUCTION_24X7) -> bool:
    """True iff ``approval`` is a valid recorded approval for ``target`` (identity + time + mode)."""
    if approval is None:
        return False
    if not str(getattr(approval, "approved_by", "")).strip():
        return False
    if not str(getattr(approval, "approved_at", "")).strip():
        return False
    try:
        approved_target = ServiceMode.parse(getattr(approval, "target_mode", ""))
    except ValueError:
        return False
    return approved_target is ServiceMode.parse(target)


# --------------------------------------------------------------------------- #
# 3. CheckResult -- the machine-check shape handed in from cosmosiq_ops          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CheckResult:
    """One machine check: a name, a closed status, and NAMED details.

    Mirrors :class:`cosmosiq_ops.ci_gate.CheckResult` so a ci-gate result can be handed straight
    in. :func:`evaluate_activation` reads only ``.status`` (+ optional ``.details``), so any object
    exposing those attributes works. A ``skipped`` status is treated as ``manual_review_required``.
    """

    name: str
    status: str  # "pass" | "fail" | "not_applicable" | "manual_review_required" | "skipped"
    details: Tuple[str, ...] = field(default_factory=tuple)


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


# --------------------------------------------------------------------------- #
# 4. The report + the evaluation                                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ActivationReport:
    """The frozen result of evaluating the activation checklist.

    ``production_mode_allowed`` is the single unforgiving verdict: production may be enabled ONLY
    when no item is ``fail``, no blocking item is ``manual_review_required``/``fail``, AND a valid
    operator approval is recorded.
    """

    production_mode_allowed: bool
    verdict: str
    operator_approval_valid: bool
    blocking_failures: Tuple[str, ...] = field(default_factory=tuple)
    manual_review_items: Tuple[str, ...] = field(default_factory=tuple)
    items: Tuple[ChecklistItem, ...] = field(default_factory=tuple)
    evidence_paths: Tuple[str, ...] = field(default_factory=tuple)

    def item(self, item_id: str) -> Optional[ChecklistItem]:
        for i in self.items:
            if i.id == item_id:
                return i
        return None


def evaluate_activation(store_dir: str, *, now: str,
                        operator_approval: Optional[OperatorApproval] = None,
                        checks: Optional[Mapping[str, object]] = None) -> ActivationReport:
    """Evaluate the activation checklist and return the frozen :class:`ActivationReport`.

    ``checks`` maps an item id to a machine :class:`CheckResult` (or any object exposing
    ``.status``). For a machine item NOT supplied -- and for every item that CANNOT be
    machine-verified OFFLINE (live source health, operator shadow validation, operator
    sign-off) -- the status defaults to ``manual_review_required`` (BLOCKING). This is why an
    honest OFFLINE evaluation, even with every machine check passing AND a valid approval,
    REFUSES full production and lands at ``shadow_24x7_only``: the manual items still block.

    Deterministic + offline: ``now`` is injected, no wall clock is read, nothing is fetched.
    """
    if not str(now).strip():
        raise ValueError("evaluate_activation requires an injected 'now' instant")
    supplied: Dict[str, object] = dict(checks or {})

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
        elif spec.is_manual:
            status = ChecklistStatus.MANUAL_REVIEW_REQUIRED
            note = "cannot be machine-verified OFFLINE -- manual review required"
        else:
            # A machine item that was never run cannot be claimed as passing (safe default).
            status = ChecklistStatus.MANUAL_REVIEW_REQUIRED
            note = "not evaluated (no machine result supplied) -- treated as pending"
        items.append(ChecklistItem(
            id=spec.id, section=spec.section, description=spec.description,
            status=status, evidence_path=evidence, blocking=spec.blocking, notes=note))
    items = tuple(items)

    blocking_failures = tuple(
        i.id for i in items if i.status == ChecklistStatus.FAIL)
    manual_review_items = tuple(
        i.id for i in items if i.status == ChecklistStatus.MANUAL_REVIEW_REQUIRED)

    any_fail = any(i.status == ChecklistStatus.FAIL for i in items)
    any_blocking_unmet = any(i.blocks_production for i in items)
    approval_valid = is_valid_approval(operator_approval)

    production_mode_allowed = (not any_fail) and (not any_blocking_unmet) and approval_valid

    if production_mode_allowed:
        verdict = Verdict.PRODUCTION_APPROVED
    elif any_fail:
        verdict = Verdict.BLOCKED
    elif any_blocking_unmet:
        # No machine failure, but blocking manual reviews remain -> the honest shadow verdict.
        verdict = Verdict.SHADOW_ONLY
    else:
        # Everything satisfied but no valid approval recorded.
        verdict = Verdict.AWAITING_APPROVAL

    evidence_paths = tuple(sorted({i.evidence_path for i in items if i.evidence_path}))

    return ActivationReport(
        production_mode_allowed=production_mode_allowed,
        verdict=verdict,
        operator_approval_valid=approval_valid,
        blocking_failures=blocking_failures,
        manual_review_items=manual_review_items,
        items=items,
        evidence_paths=evidence_paths)


# --------------------------------------------------------------------------- #
# 5. The promotion / rollback state machine                                     #
# --------------------------------------------------------------------------- #
# The mode safety ladder, low (safe) -> high (capable). Promotion climbs; rollback descends.
MODE_LADDER: Tuple[ServiceMode, ...] = (
    ServiceMode.OFF,
    ServiceMode.MANUAL,
    ServiceMode.SHADOW_24X7,
    ServiceMode.PRODUCTION_24X7,
)
_LADDER_INDEX: Dict[ServiceMode, int] = {mode: i for i, mode in enumerate(MODE_LADDER)}

# The named rollback triggers -> the mode CosmosIQ downgrades to when the trigger fires. A
# hygiene/safety breach (secret / trading control) drops all the way to OFF; an operational
# spike drops one rung to SHADOW_24X7 for investigation.
ROLLBACK_TRIGGERS: Dict[str, Tuple[str, ServiceMode]] = {
    "source_failure_spike": (
        "a spike in live-source failures (visible gaps, not a fixture fall-back)",
        ServiceMode.SHADOW_24X7),
    "agent_failure_spike": (
        "a spike in agent-run failures across the fused disciplines",
        ServiceMode.SHADOW_24X7),
    "dq_hard_fail_spike": (
        "a spike in Data-Quality HARD failures (blocked_by_policy)",
        ServiceMode.SHADOW_24X7),
    "false_positive_spike": (
        "a spike in false-positive alerts (precision collapse)",
        ServiceMode.SHADOW_24X7),
    "delivery_failure": (
        "external alert delivery is failing (retryable/permanent)",
        ServiceMode.SHADOW_24X7),
    "candidate_eligibility_bug": (
        "a candidate-eligibility bug (a candidate reached eligible without full provenance)",
        ServiceMode.MANUAL),
    "fixture_leakage": (
        "fixture/demo data leaked into a product surface",
        ServiceMode.OFF),
    "secret_leakage": (
        "a secret value appeared in output / logs",
        ServiceMode.OFF),
    "unexpected_trading_control": (
        "an unexpected trading / broker / order control was detected",
        ServiceMode.OFF),
    "operator_manual": (
        "an operator manually initiated a rollback",
        ServiceMode.SHADOW_24X7),
}


@dataclass(frozen=True)
class PromotionDecision:
    """The frozen outcome of a promotion / rollback request."""

    allowed: bool
    from_mode: str
    to_mode: str
    reason: str
    blocking_reasons: Tuple[str, ...] = field(default_factory=tuple)


def promote(current_mode: object, target: object, *,
            report: Optional[ActivationReport] = None,
            operator_approval: Optional[OperatorApproval] = None) -> PromotionDecision:
    """Decide a promotion from ``current_mode`` to ``target`` (an UPGRADE on the ladder).

    * ``OFF`` / ``MANUAL`` -> ``SHADOW_24X7`` (or ``MANUAL``): allowed freely.
    * ``SHADOW_24X7`` -> ``PRODUCTION_24X7``: allowed ONLY when ``report.production_mode_allowed``
      is True AND a valid ``operator_approval`` is recorded.
    * Any direct jump to ``PRODUCTION_24X7`` from below ``SHADOW_24X7``, and any auto / unapproved
      jump, is REFUSED. A downgrade request is refused here -- use :func:`rollback`.
    """
    current = ServiceMode.parse(current_mode)
    to = ServiceMode.parse(target)
    c_idx, t_idx = _LADDER_INDEX[current], _LADDER_INDEX[to]

    if to is current:
        return PromotionDecision(True, current.value, to.value, "already in {0}".format(to.value))
    if t_idx < c_idx:
        return PromotionDecision(
            False, current.value, to.value,
            "refused: {0} is a downgrade from {1} -- use rollback() to step down".format(
                to.value, current.value))

    if to is ServiceMode.PRODUCTION_24X7:
        if current is not ServiceMode.SHADOW_24X7:
            return PromotionDecision(
                False, current.value, to.value,
                "refused: PRODUCTION_24X7 is reachable ONLY from SHADOW_24X7 (run shadow first)",
                ("production must be promoted from SHADOW_24X7, not {0}".format(current.value),))
        reasons = []
        if report is None or not report.production_mode_allowed:
            reasons.append("the activation report does not allow production_mode")
            if report is not None:
                reasons.extend("blocking failure: " + b for b in report.blocking_failures)
                reasons.extend("manual review pending: " + m
                               for m in report.manual_review_items)
        if not is_valid_approval(operator_approval):
            reasons.append("no valid explicit operator approval recorded")
        if reasons:
            return PromotionDecision(
                False, current.value, to.value,
                "refused: production activation requires a passing report AND explicit approval",
                tuple(reasons))
        return PromotionDecision(
            True, current.value, to.value,
            "promoted to PRODUCTION_24X7: activation report allows it and an explicit operator "
            "approval is recorded")

    # OFF/MANUAL -> MANUAL/SHADOW_24X7: an ordinary, freely-allowed upgrade.
    return PromotionDecision(
        True, current.value, to.value,
        "promoted {0} -> {1} (below production -- no activation gate required)".format(
            current.value, to.value))


def rollback(current_mode: object, target: object) -> PromotionDecision:
    """Decide a rollback (a DOWNGRADE) from ``current_mode`` to ``target``.

    A downgrade is ALWAYS allowed -- stepping down to a safer mode is never gated. The intended
    descent is ``PRODUCTION_24X7`` -> ``SHADOW_24X7`` -> ``MANUAL`` -> ``OFF``. An upgrade request
    is refused here (use :func:`promote`).
    """
    current = ServiceMode.parse(current_mode)
    to = ServiceMode.parse(target)
    c_idx, t_idx = _LADDER_INDEX[current], _LADDER_INDEX[to]
    if to is current:
        return PromotionDecision(True, current.value, to.value,
                                 "already in {0} -- no rollback needed".format(to.value))
    if t_idx > c_idx:
        return PromotionDecision(
            False, current.value, to.value,
            "refused: {0} is an upgrade from {1} -- use promote() to step up".format(
                to.value, current.value))
    return PromotionDecision(
        True, current.value, to.value,
        "rolled back {0} -> {1} (downgrade to a safer mode is always allowed)".format(
            current.value, to.value))


# --------------------------------------------------------------------------- #
# 6. can_enter_production -- the predicate the service consults                  #
# --------------------------------------------------------------------------- #
def can_enter_production(store_dir: str, *, operator_approval: Optional[OperatorApproval],
                         now: str, checks: Optional[Mapping[str, object]] = None) -> bool:
    """True iff continuous ``PRODUCTION_24X7`` may be entered -- ``False`` unless the gate allows.

    Consulted by the service before it enters continuous production. In an honest OFFLINE call
    (no ``checks`` supplied) the manual items keep this ``False``: production cannot be entered
    without the live-source-health fetch, the operator shadow-validation, and explicit approval.
    """
    report = evaluate_activation(store_dir, now=now, operator_approval=operator_approval,
                                 checks=checks)
    return report.production_mode_allowed
