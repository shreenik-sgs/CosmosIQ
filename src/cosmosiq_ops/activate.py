"""The Production 24x7 Activation FLOW (IMPLEMENTATION-021C). OFFLINE, local files only.

This is the operator-facing FLOW that sits on top of the accepted 020F activation CORE
(:mod:`cosmosiq_service.activation`). It does exactly two things, and refuses everything else:

* :func:`run_activation` -- read a filled operator sign-off file, run the offline prod-check
  machine sweep, fold the sign-off in, and flip the service to ``PRODUCTION_24X7`` **only if**
  the activation report says ``production_mode_allowed`` -- i.e. only when EVERY blocking item is
  satisfied (zero fails, zero blocking manual-reviews) AND a valid operator approval is recorded.
  Otherwise it REFUSES and changes nothing.
* :func:`run_rollback` -- step the mode DOWN the safety ladder
  (``PRODUCTION_24X7`` -> ``SHADOW_24X7`` -> ``MANUAL`` -> ``OFF``), recording the named
  :data:`cosmosiq_service.activation.ROLLBACK_TRIGGERS` trigger. An upgrade is refused here.

The unforgiving safety rule (never weakened here -- this module only READS the CORE's verdict)::

    activate flips to PRODUCTION_24X7  IFF
        read_operator_signoff(path) is a valid PRODUCTION_24X7_APPROVED approval
        AND evaluate_activation(...).production_mode_allowed is True
            (zero blocking failures AND zero blocking manual-review items --
             which today STILL includes live_source_health + operator_shadow_validation)

Those two live items are the operator's live / wall-clock evidence; they are NEVER cleared from
code. So in the current repo state (no sign-off file, the two live items unmet) an activation
attempt correctly REFUSES. That is the safe default, not a failure.

The activated production surface keeps every permanent guarantee: Broker Disabled, Execution
Manual Review Only, Alert Delivery On -- and NEVER a buy / sell / order / submit / auto-trade /
broker-submit / guaranteed-upside control anywhere. This module writes no such token.

Stdlib-only, Python 3.9, OFFLINE. ``now`` is injected everywhere; no wall clock, no network, no
secret. It never creates ``reports/OPERATOR_SIGNOFF_020J.md`` and never fills an approval.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from typing import Dict, Mapping, Optional, Tuple

from cosmosiq_service.activation import (
    ActivationReport,
    CheckResult,
    OperatorApproval,
    ROLLBACK_TRIGGERS,
    evaluate_activation,
    read_operator_signoff,
)
from cosmosiq_service.service import ServiceMode

__all__ = [
    "DEFAULT_SIGNOFF_REL",
    "SERVICE_MODE_MARKER",
    "ActivationOutcome",
    "RollbackOutcome",
    "run_activation",
    "run_rollback",
    "format_activation_report",
    "format_rollback_report",
    "read_current_mode",
]

# The default location of a REAL, filled operator sign-off (relative to the repo root). This file
# is the operator's act alone; 021C NEVER creates or fills it.
DEFAULT_SIGNOFF_REL = os.path.join("reports", "OPERATOR_SIGNOFF_020J.md")
# The sanctioned-mode marker the service / product surface honours (written under the store).
SERVICE_MODE_MARKER = "service_mode.json"
_HEALTH_FILENAME = "service_health.json"

# The forbidden control tokens -- a production banner / marker may NEVER contain any of these.
_FORBIDDEN_TOKENS: Tuple[str, ...] = (
    "buy", "sell", "order", "submit", "auto-trade", "autotrade", "broker-submit",
    "auto-rebalance", "guaranteed-upside", "guaranteed upside", "trade now")


# --------------------------------------------------------------------------- #
# Outcomes                                                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ActivationOutcome:
    """The frozen result of an activation attempt (nothing is written unless ``activated``)."""

    activated: bool
    target_mode: str
    signoff_path: str
    signoff_present: bool
    signoff_valid: bool
    verdict: str
    blocking_failures: Tuple[str, ...] = field(default_factory=tuple)
    manual_review_items: Tuple[str, ...] = field(default_factory=tuple)
    refusal_reasons: Tuple[str, ...] = field(default_factory=tuple)
    banner: str = ""
    marker_path: str = ""
    report: Optional[ActivationReport] = None


@dataclass(frozen=True)
class RollbackOutcome:
    """The frozen result of a rollback (a downgrade). ``applied`` is False for an upgrade refusal."""

    allowed: bool
    applied: bool
    from_mode: str
    to_mode: str
    reason: str
    trigger: str = ""
    trigger_description: str = ""
    marker_path: str = ""


# --------------------------------------------------------------------------- #
# Mode marker read / write (the service honours the sanctioned mode)            #
# --------------------------------------------------------------------------- #
def _atomic_write_json(path: str, payload: Mapping[str, object]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
    os.replace(tmp, path)


def _read_mode_field(store_dir: str, filename: str) -> str:
    path = os.path.join(store_dir, filename)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return str(data.get("service_mode", "") or "").strip()
    except (FileNotFoundError, ValueError, OSError):
        return ""
    return ""


def read_current_mode(store_dir: str) -> ServiceMode:
    """The sanctioned service mode recorded under ``store_dir`` (``OFF`` if none / unreadable).

    Prefers the :data:`SERVICE_MODE_MARKER`, then the service-health snapshot; the safe default
    is ``OFF``. Never raises.
    """
    for filename in (SERVICE_MODE_MARKER, _HEALTH_FILENAME):
        raw = _read_mode_field(store_dir, filename)
        if raw:
            try:
                return ServiceMode.parse(raw)
            except ValueError:
                continue
    return ServiceMode.OFF


def _set_health_mode(store_dir: str, mode: ServiceMode, now: str) -> None:
    """Reflect the sanctioned mode in the service-health snapshot the product UI reads."""
    from cosmosiq_service.service import ServiceHealth
    path = os.path.join(store_dir, _HEALTH_FILENAME)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        data = {}
    health = ServiceHealth.from_dict(data if isinstance(data, dict) else {})
    health = replace(health, service_mode=mode.value, updated_at=now)
    _atomic_write_json(path, health.to_dict())


def _write_mode_marker(store_dir: str, mode: ServiceMode, *, now: str,
                       approval: Optional[OperatorApproval] = None,
                       trigger: str = "", trigger_description: str = "") -> str:
    """Record the sanctioned ``mode`` (marker + health snapshot). Returns the marker path."""
    os.makedirs(store_dir, exist_ok=True)
    payload: Dict[str, object] = {
        "service_mode": mode.value,
        "sanctioned_mode": mode.name,
        "recorded_at": now,
        "broker": "disabled",
        "execution_boundary": "manual_review_only",
    }
    if approval is not None:
        payload["approved_by"] = approval.approved_by
        payload["approved_at"] = approval.approved_at
    if trigger:
        payload["rollback_trigger"] = trigger
        payload["rollback_trigger_description"] = trigger_description
    marker_path = os.path.join(store_dir, SERVICE_MODE_MARKER)
    _atomic_write_json(marker_path, payload)
    _set_health_mode(store_dir, mode, now)
    return marker_path


# --------------------------------------------------------------------------- #
# The activation flow                                                           #
# --------------------------------------------------------------------------- #
def _live_status(report: Optional[ActivationReport]) -> str:
    if report is None:
        return "Verified"
    item = report.item("live_source_health")
    if item is None:
        return "Verified"
    return {"pass": "On", "fail": "Source gap"}.get(item.status, "Verified")


def _production_banner(report: Optional[ActivationReport]) -> str:
    """The verbatim production banner -- Broker Disabled, Manual Review Only, NO trade control."""
    return ("Mode: PRODUCTION_24X7 · Live Data: {0} · Scheduler: On · "
            "Broker: Disabled · Execution: Manual Review Only · "
            "Alert Delivery: On").format(_live_status(report))


def _refusal_reasons(report: ActivationReport, signoff_present: bool,
                     signoff_valid: bool) -> Tuple[str, ...]:
    reasons = ["blocking failure: " + b for b in report.blocking_failures]
    reasons += ["manual review required: " + m for m in report.manual_review_items]
    if not report.operator_approval_valid:
        if not signoff_present:
            reasons.append("no operator sign-off file found (none present at the sign-off path)")
        else:
            reasons.append(
                "operator sign-off present but NOT a valid PRODUCTION_24X7_APPROVED approval "
                "(a CONTINUE_SHADOW sign-off, an unchecked acknowledgement, a missing name or "
                "timestamp, or a malformed file)")
    return tuple(reasons)


def run_activation(work_dir: str, *, now: str, signoff_path: str,
                   repo_root: Optional[str] = None,
                   checks: Optional[Mapping[str, object]] = None,
                   quick: bool = True) -> ActivationOutcome:
    """Attempt to activate ``PRODUCTION_24X7`` -- and REFUSE unless the evidence is complete.

    Reads the sign-off at ``signoff_path`` via
    :func:`cosmosiq_service.activation.read_operator_signoff`, gathers the machine checks (the
    real offline prod-check sweep when ``checks`` is None; otherwise the injected ``checks`` map,
    used by the deterministic tests), folds in the sign-off, and evaluates the 020F activation
    report. Production is enabled ONLY when ``report.production_mode_allowed`` is True -- zero
    blocking failures, zero blocking manual-review items, AND a valid operator approval.

    On success it records the sanctioned ``PRODUCTION_24X7`` mode marker + prints the production
    banner. On refusal it writes NOTHING and returns the exact blocking / manual reasons. The two
    live manual items (live_source_health, operator_shadow_validation) are NEVER cleared here, so
    an honest current-state attempt refuses. ``now`` is injected; the call is fully offline.
    """
    if not str(now).strip():
        raise ValueError("run_activation requires an injected 'now' instant")
    store_dir = os.path.join(str(work_dir), "store")
    os.makedirs(store_dir, exist_ok=True)

    signoff_present = os.path.isfile(str(signoff_path))
    approval = read_operator_signoff(str(signoff_path))
    signoff_valid = approval is not None

    # A genuine, filled sign-off file IS the recorded evidence for the operator_signoff checklist
    # item -- so a valid read clears THAT item. It does NOT (and code never does) clear the live /
    # shadow items; those stay blocking until the operator supplies live/wall-clock evidence.
    extra: Dict[str, CheckResult] = {}
    if signoff_valid:
        extra["operator_signoff"] = CheckResult(
            "operator_signoff", "pass",
            ("operator production sign-off recorded at " + str(signoff_path),))

    if checks is not None:
        merged: Dict[str, object] = dict(checks)
        merged.update(extra)
        report = evaluate_activation(store_dir, now=now, operator_approval=approval,
                                     checks=merged)
    else:
        from cosmosiq_ops.prod_check import run_prod_check
        pc = run_prod_check(str(work_dir), repo_root or _default_repo_root(), now=now,
                            quick=quick, operator_approval=approval, extra_checks=extra)
        report = pc.activation

    activated = bool(report.production_mode_allowed)
    marker_path = ""
    banner = ""
    refusal: Tuple[str, ...] = ()
    if activated:
        marker_path = _write_mode_marker(store_dir, ServiceMode.PRODUCTION_24X7, now=now,
                                         approval=approval)
        banner = _production_banner(report)
        _assert_no_trade_control(banner)
    else:
        refusal = _refusal_reasons(report, signoff_present, signoff_valid)

    return ActivationOutcome(
        activated=activated,
        target_mode=ServiceMode.PRODUCTION_24X7.value if activated else read_current_mode(
            store_dir).value,
        signoff_path=str(signoff_path), signoff_present=signoff_present,
        signoff_valid=signoff_valid, verdict=report.verdict,
        blocking_failures=report.blocking_failures,
        manual_review_items=report.manual_review_items,
        refusal_reasons=refusal, banner=banner, marker_path=marker_path, report=report)


def _assert_no_trade_control(text: str) -> None:
    lowered = str(text).lower()
    for token in _FORBIDDEN_TOKENS:
        if token in lowered:
            raise AssertionError(
                "SAFETY VIOLATION: forbidden trade-control token {0!r} in activation output"
                .format(token))


# --------------------------------------------------------------------------- #
# The rollback flow                                                             #
# --------------------------------------------------------------------------- #
def run_rollback(work_dir: str, *, to: object, now: str,
                 trigger: Optional[str] = None) -> RollbackOutcome:
    """Step the sanctioned mode DOWN the ladder, recording a named rollback trigger.

    Reads the current sanctioned mode under ``work_dir/store`` and applies
    :func:`cosmosiq_service.activation.rollback` toward ``to`` (one of
    ``SHADOW_24X7`` / ``MANUAL`` / ``OFF``). A downgrade is always allowed; an UPGRADE request is
    REFUSED and changes nothing. The trigger defaults to ``operator_manual`` and must be a known
    :data:`cosmosiq_service.activation.ROLLBACK_TRIGGERS` name.
    """
    from cosmosiq_service.activation import rollback as _rollback_decision
    if not str(now).strip():
        raise ValueError("run_rollback requires an injected 'now' instant")
    store_dir = os.path.join(str(work_dir), "store")
    os.makedirs(store_dir, exist_ok=True)

    trigger_name = str(trigger or "operator_manual").strip()
    if trigger_name not in ROLLBACK_TRIGGERS:
        return RollbackOutcome(
            allowed=False, applied=False, from_mode=read_current_mode(store_dir).value,
            to_mode=str(to), reason="refused: unknown rollback trigger {0!r} (known: {1})".format(
                trigger_name, ", ".join(sorted(ROLLBACK_TRIGGERS))),
            trigger=trigger_name)
    trigger_description = ROLLBACK_TRIGGERS[trigger_name][0]

    current = read_current_mode(store_dir)
    decision = _rollback_decision(current, to)

    applied = False
    marker_path = ""
    if decision.allowed and ServiceMode.parse(decision.to_mode) is not current:
        marker_path = _write_mode_marker(
            store_dir, ServiceMode.parse(decision.to_mode), now=now,
            trigger=trigger_name, trigger_description=trigger_description)
        applied = True

    return RollbackOutcome(
        allowed=decision.allowed, applied=applied, from_mode=decision.from_mode,
        to_mode=decision.to_mode, reason=decision.reason, trigger=trigger_name,
        trigger_description=trigger_description, marker_path=marker_path)


# --------------------------------------------------------------------------- #
# Reports                                                                       #
# --------------------------------------------------------------------------- #
def format_activation_report(outcome: ActivationOutcome) -> str:
    lines = [
        "CosmosIQ production 24x7 activation (Phase 021C) -- {0}".format(
            "ACTIVATED" if outcome.activated else "REFUSED"),
        "sign-off file: {0} ({1}{2})".format(
            outcome.signoff_path,
            "present" if outcome.signoff_present else "not present",
            ", valid PRODUCTION approval" if outcome.signoff_valid
            else ", no valid production approval"),
        "verdict: {0}".format(outcome.verdict),
        "production_mode_allowed = {0}".format(str(outcome.activated).lower()),
    ]
    if outcome.activated:
        lines.append("mode marker written: {0}".format(outcome.marker_path))
        lines.append(outcome.banner)
        lines.append("Permanent guarantees hold: Broker Disabled; Execution Manual Review Only; "
                     "no trading or order-entry affordance exists anywhere.")
    else:
        lines.append("blocking_failures: {0}".format(
            ", ".join(outcome.blocking_failures) or "none"))
        lines.append("manual_review_items: {0}".format(
            ", ".join(outcome.manual_review_items) or "none"))
        lines.append("REFUSED -- nothing was written. Reasons:")
        for reason in outcome.refusal_reasons:
            lines.append("  - " + reason)
        lines.append("This is the correct, safe default: production stays refused until the "
                     "live-source-health fetch AND the operator shadow-validation are satisfied "
                     "AND an explicit PRODUCTION_24X7_APPROVED sign-off is recorded. Remain shadow.")
    return "\n".join(lines)


def format_rollback_report(outcome: RollbackOutcome) -> str:
    lines = [
        "CosmosIQ mode rollback (Phase 021C) -- {0}".format(
            "APPLIED" if outcome.applied else ("NO-OP" if outcome.allowed else "REFUSED")),
        "from {0} -> {1}".format(outcome.from_mode, outcome.to_mode),
        "trigger: {0}{1}".format(
            outcome.trigger,
            " -- " + outcome.trigger_description if outcome.trigger_description else ""),
        outcome.reason,
    ]
    if outcome.applied:
        lines.append("mode marker written: {0}".format(outcome.marker_path))
    return "\n".join(lines)


def _default_repo_root() -> str:
    # src/cosmosiq_ops/activate.py -> repo root is three levels up.
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
