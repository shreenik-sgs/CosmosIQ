"""GO-LIVE PL-3 -- the operator PRODUCTION-ACTIVATION FLOW. OFFLINE, deterministic, compose-only.

This is the operator-facing flow that moves the sanctioned service mode from ``SHADOW_24X7`` to
``PRODUCTION_24X7`` -- and it REFUSES to do so unless the honest gate allows it. It re-implements
NOTHING: it composes the accepted machinery and only reads its verdict.

* the "may we promote" verdict is :func:`cosmosiq_ops.prod_check.run_prod_check`, RE-RUN at request
  time (never a cached ``allowed=True``); its ``production_mode_allowed`` already reflects the full
  honest gate -- every machine check, BOTH PL-2 evidence-backed attestations, and a valid recorded
  operator approval;
* the actual mode transition is the accepted state machine
  :func:`cosmosiq_service.activation.promote` / :func:`cosmosiq_service.activation.rollback` -- this
  module never bends the ladder (only ``SHADOW_24X7`` -> ``PRODUCTION_24X7``; a downgrade is always
  allowed);
* the sanctioned-mode marker is the accepted 021C marker
  (:data:`cosmosiq_ops.activate.SERVICE_MODE_MARKER`), so the product surface / service honour the
  same single source of truth.

The unforgiving rule (never weakened here)::

    request_production_promotion promotes to PRODUCTION_24X7  IFF
        run_prod_check(re-run NOW).production_mode_allowed is True
        AND a non-empty confirmed_by operator is supplied
        AND the explicit CONFIRM_TOKEN is supplied
        AND the current sanctioned mode is SHADOW_24X7
        AND the accepted promote() state machine allows it

On ANY refusal NOTHING changes: no marker is written, the mode is unchanged, and the exact blocking
items are returned. ``PRODUCTION_24X7`` is NEVER the default and is never auto-reached.
:func:`rollback_to_shadow` is ALWAYS available and is never gated -- stepping down to the safer
shadow posture can never be blocked.

Execution stays MANUAL even in production: this module recommends nothing to a broker, submits no
order, and writes no buy / sell / order / broker / trade token anywhere. Every promotion / rollback
is journaled to an APPEND-ONLY event log (no line ever rewritten). Deterministic: every ``now`` is
injected; no wall clock, no network, no secret. Importing this module starts nothing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from cosmosiq_service.activation import (
    ActivationReport,
    CheckResult,
    OperatorApproval,
    is_valid_approval,
    promote,
    read_operator_signoff,
    rollback,
)
from cosmosiq_service.service import ServiceMode, sanitize

__all__ = [
    "CONFIRM_TOKEN",
    "PROMOTION_EVENTS_FILENAME",
    "PromotionResult",
    "RollbackResult",
    "production_readiness_report",
    "request_production_promotion",
    "rollback_to_shadow",
    "read_promotion_events",
]

# The explicit confirm token an operator MUST supply to promote. It is not a secret (it is printed
# in the UI / CLI help); it exists purely so a promotion can never be a one-click accident.
CONFIRM_TOKEN = "PROMOTE_TO_PRODUCTION_24X7"

# The append-only journal of every promotion / rollback (under the operator store dir).
PROMOTION_EVENTS_FILENAME = "production_promotion_events.jsonl"

_PROMOTION_EVENT = "production_promotion"
_ROLLBACK_EVENT = "production_rollback"

# The forbidden CONTROL tokens -- a promotion banner / event may NEVER contain any of these. This
# is the same calibration as the 021C activation flow: it forbids trade-CONTROL affordances
# (buy/sell/order/submit/auto-trade/broker-submit ...), NOT the honest disclosures "Broker:
# Disabled" / "Execution: Manual Review Only" that the production banner deliberately carries.
_FORBIDDEN_TOKENS: Tuple[str, ...] = (
    "buy", "sell", "order", "submit", "auto-trade", "autotrade", "broker-submit",
    "auto-rebalance", "guaranteed-upside", "guaranteed upside", "trade now")

# The plain-English copy every production surface repeats verbatim. It conveys the two permanent
# guarantees -- execution stays manual review only, and nothing is ever sent to a market -- WITHOUT
# the literal trade-control words (the same discipline as the pages' default status line), so the
# copy stays clean for the trade-affordance sweep while remaining fully honest.
PRODUCTION_MEANING = (
    "Production means 24x7 live analysis and delivered recommendations. Execution stays MANUAL "
    "review only -- no market connection and no automated trading. Promotion needs the full "
    "activation gate.")


# --------------------------------------------------------------------------- #
# Results                                                                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PromotionResult:
    """The frozen outcome of a promotion request (nothing changes unless ``promoted``)."""

    promoted: bool
    production_mode_allowed: bool
    from_mode: str
    to_mode: str
    verdict: str
    confirmed_by: str = ""
    blocking_items: Tuple[str, ...] = field(default_factory=tuple)
    refusal_reasons: Tuple[str, ...] = field(default_factory=tuple)
    banner: str = ""
    marker_path: str = ""
    event_path: str = ""
    report: Optional[ActivationReport] = None


@dataclass(frozen=True)
class RollbackResult:
    """The frozen outcome of a rollback to shadow (always available -- never gated)."""

    applied: bool
    from_mode: str
    to_mode: str
    reason: str
    actor: str = ""
    rollback_reason: str = ""
    marker_path: str = ""
    event_path: str = ""


# --------------------------------------------------------------------------- #
# Guards + append-only event journal                                            #
# --------------------------------------------------------------------------- #
def _assert_no_trade_control(text: str) -> None:
    lowered = str(text).lower()
    for token in _FORBIDDEN_TOKENS:
        if token in lowered:
            raise AssertionError(
                "SAFETY VIOLATION: forbidden trade-control token {0!r} in promotion output"
                .format(token))


def _append_event(store_dir: str, payload: Mapping[str, object]) -> str:
    """Append ONE sanitized event line to the append-only promotion journal; return its path."""
    os.makedirs(str(store_dir), exist_ok=True)
    path = os.path.join(str(store_dir), PROMOTION_EVENTS_FILENAME)
    record = sanitize(dict(payload))
    line = json.dumps(record, sort_keys=True)
    _assert_no_trade_control(line)          # execution stays manual: no trade token is ever written
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path


def read_promotion_events(store_dir: str) -> Tuple[Dict[str, object], ...]:
    """Every journaled promotion / rollback event, oldest first (a corrupt line is skipped)."""
    path = os.path.join(str(store_dir), PROMOTION_EVENTS_FILENAME)
    events: List[Dict[str, object]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if isinstance(data, dict):
                    events.append(data)
    except (FileNotFoundError, OSError):
        return ()
    return tuple(events)


def _evidence_summary(report: ActivationReport) -> Dict[str, object]:
    """A counts + key-item-status summary of the gate report (labels only, never a score)."""
    key_items = ("live_source_health", "operator_shadow_validation", "operator_signoff")
    statuses: Dict[str, str] = {}
    for item_id in key_items:
        item = report.item(item_id)
        statuses[item_id] = item.status if item is not None else "unknown"
    return {
        "verdict": report.verdict,
        "production_mode_allowed": bool(report.production_mode_allowed),
        "operator_approval_valid": bool(report.operator_approval_valid),
        "items_total": len(report.items),
        "blocking_failures": list(report.blocking_failures),
        "manual_review_items": list(report.manual_review_items),
        "key_item_status": statuses,
    }


# --------------------------------------------------------------------------- #
# The honest readiness report -- run_prod_check re-run over the REAL evidence    #
# --------------------------------------------------------------------------- #
def production_readiness_report(store_dir: str, work_dir: str, repo_root: str, *, now: str,
                               signoff_path: Optional[str] = None,
                               operator_approval: Optional[OperatorApproval] = None,
                               extra_checks: Optional[Mapping[str, object]] = None,
                               quick: bool = True):
    """Compose :func:`run_prod_check` over the operator's REAL store and return its ProdCheckReport.

    ``store_dir`` is the operator's real append-only store (the two PL-2 attestations + the operator
    sign-off live here); ``work_dir`` is a THROWAWAY scratch dir for the machine sweep (never the
    real store, so the sweep's seeded run never pollutes it). The two attestation items are cleared
    only by an INDEPENDENT verifier re-reading ``store_dir`` (never the attestation's word), and the
    operator-sign-off item only by a valid recorded sign-off. ``now`` is injected; the call is fully
    offline. Returns whatever run_prod_check honestly reports -- it is NEVER weakened here.
    """
    if not str(now).strip():
        raise ValueError("production_readiness_report requires an injected 'now' instant")
    import tempfile
    from cosmosiq_ops.operator_attestation import (
        latest_live_source_health_attestation,
        latest_shadow_validation_attestation,
        verify_live_source_health,
        verify_shadow_validation,
    )
    from cosmosiq_ops.prod_check import run_prod_check

    approval = operator_approval
    extra: Dict[str, object] = dict(extra_checks or {})

    # The sign-off FILE is the recorded evidence for the operator_signoff checklist item -- a valid
    # read clears THAT item (and yields the operator approval). It NEVER clears the two live items.
    if signoff_path:
        file_approval = read_operator_signoff(str(signoff_path))
        if file_approval is not None:
            if approval is None:
                approval = file_approval
            extra.setdefault("operator_signoff", CheckResult(
                "operator_signoff", "pass",
                ("operator production sign-off recorded at " + str(signoff_path),)))

    # Independently re-verify the two PL-2 items against the REAL store (only when an attestation
    # exists -- with none, they fall through to the honest manual_review_required default, blocking).
    if latest_live_source_health_attestation(store_dir) is not None:
        extra.setdefault("live_source_health", verify_live_source_health(store_dir, now=now))
    if latest_shadow_validation_attestation(store_dir) is not None:
        extra.setdefault("operator_shadow_validation",
                         verify_shadow_validation(store_dir, now=now))

    # run_prod_check needs a FRESH scratch dir (it seeds a fixed run id into work_dir/store); a
    # fresh sub-dir per sweep makes repeated calls -- and a re-run at promote time -- always safe.
    os.makedirs(str(work_dir), exist_ok=True)
    sweep_dir = tempfile.mkdtemp(prefix="prodcheck-", dir=str(work_dir))
    return run_prod_check(sweep_dir, str(repo_root), now=now, quick=quick,
                          operator_approval=approval, extra_checks=extra or None)


# --------------------------------------------------------------------------- #
# request_production_promotion -- refuse unless the full gate allows            #
# --------------------------------------------------------------------------- #
def _current_mode(store_dir: str) -> ServiceMode:
    from cosmosiq_ops.activate import read_current_mode
    return read_current_mode(store_dir)


def request_production_promotion(store_dir: str, work_dir: str, repo_root: str, *, now: str,
                                confirmed_by: str, confirm: object = "",
                                signoff_path: Optional[str] = None,
                                operator_approval: Optional[OperatorApproval] = None,
                                extra_checks: Optional[Mapping[str, object]] = None,
                                quick: bool = True) -> PromotionResult:
    """Attempt to promote SHADOW_24X7 -> PRODUCTION_24X7 -- and REFUSE unless the full gate allows.

    The flow, in order:

    1. RE-RUN :func:`run_prod_check` NOW over the real ``store_dir`` (never a cached verdict). If
       ``production_mode_allowed`` is False -> REFUSE, listing the exact blocking items; NOTHING
       changes.
    2. Otherwise require a non-empty ``confirmed_by`` operator AND the explicit
       :data:`CONFIRM_TOKEN` -> else REFUSE; NOTHING changes.
    3. Require the current sanctioned mode to be ``SHADOW_24X7`` (no ``OFF`` / ``MANUAL`` jump) ->
       else REFUSE; NOTHING changes.
    4. Call the accepted :func:`cosmosiq_service.activation.promote` state machine. On its approval,
       record the sanctioned ``PRODUCTION_24X7`` marker AND an append-only promotion event, then
       return ``promoted=True``.

    ``now`` is injected; the call is deterministic + offline. ``PRODUCTION_24X7`` is never reached
    by accident: the machine gate, both attestations, a valid sign-off, an explicit operator, an
    explicit token, and the SHADOW-only ladder rule must ALL hold.
    """
    if not str(now).strip():
        raise ValueError("request_production_promotion requires an injected 'now' instant")

    current = _current_mode(store_dir)

    # 1. re-run the honest gate NOW -- never a cached allowed=True.
    pc = production_readiness_report(
        store_dir, work_dir, repo_root, now=now, signoff_path=signoff_path,
        operator_approval=operator_approval, extra_checks=extra_checks, quick=quick)
    report = pc.activation
    allowed = bool(pc.production_mode_allowed)
    approval = _resolve_approval(signoff_path, operator_approval)

    def _refuse(reasons: Tuple[str, ...]) -> PromotionResult:
        return PromotionResult(
            promoted=False, production_mode_allowed=allowed,
            from_mode=current.value, to_mode=current.value, verdict=report.verdict,
            confirmed_by=str(confirmed_by or "").strip(),
            blocking_items=tuple(report.blocking_failures) + tuple(report.manual_review_items),
            refusal_reasons=reasons, report=report)

    # 2. gate refusal -> the exact blocking items; nothing changes.
    if not allowed:
        reasons = tuple("blocking failure: " + b for b in report.blocking_failures) + tuple(
            "manual review required: " + m for m in report.manual_review_items)
        if not report.operator_approval_valid:
            reasons += ("no valid explicit operator approval / production sign-off recorded",)
        reasons += ("prod-check (re-run now) reports production_mode_allowed=False -- REFUSED; "
                    "nothing changed; remain in {0}.".format(current.value),)
        return _refuse(reasons)

    # 3. explicit operator + explicit confirm token (an allowed gate is not enough on its own).
    operator = str(confirmed_by or "").strip()
    if not operator:
        return _refuse((
            "a non-empty confirmed_by operator is required -- production is never auto-reached; "
            "nothing changed.",))
    if str(confirm).strip() != CONFIRM_TOKEN:
        return _refuse((
            "explicit confirmation required: resubmit with confirm={0!r}; nothing changed.".format(
                CONFIRM_TOKEN),))

    # 4. only SHADOW_24X7 -> PRODUCTION_24X7 (no OFF/MANUAL jump).
    if current is not ServiceMode.SHADOW_24X7:
        return _refuse((
            "refused: PRODUCTION_24X7 is reachable ONLY from SHADOW_24X7 -- current sanctioned "
            "mode is {0}. Run shadow first; nothing changed.".format(current.value),))

    # 5. the accepted state machine has the final say.
    decision = promote(current, ServiceMode.PRODUCTION_24X7, report=report,
                       operator_approval=approval)
    if not decision.allowed:
        return _refuse(("promote() refused: " + decision.reason,) + tuple(decision.blocking_reasons))

    # 6. sanctioned: write the marker + journal the append-only promotion event.
    from cosmosiq_ops.activate import _write_mode_marker
    marker_path = _write_mode_marker(store_dir, ServiceMode.PRODUCTION_24X7, now=now,
                                     approval=approval)
    event_path = _append_event(store_dir, {
        "event": _PROMOTION_EVENT,
        "from_mode": current.value,
        "to_mode": ServiceMode.PRODUCTION_24X7.value,
        "confirmed_by": operator,
        "confirm_token_ok": True,
        "recorded_at": now,
        "broker": "disabled",
        "execution_boundary": "manual_review_only",
        "evidence_summary": _evidence_summary(report),
    })
    banner = _production_banner(report)
    _assert_no_trade_control(banner)

    return PromotionResult(
        promoted=True, production_mode_allowed=True,
        from_mode=current.value, to_mode=ServiceMode.PRODUCTION_24X7.value,
        verdict=report.verdict, confirmed_by=operator,
        banner=banner, marker_path=marker_path, event_path=event_path, report=report)


def _resolve_approval(signoff_path: Optional[str],
                      operator_approval: Optional[OperatorApproval]) -> Optional[OperatorApproval]:
    if operator_approval is not None:
        return operator_approval
    if signoff_path:
        return read_operator_signoff(str(signoff_path))
    return None


def _production_banner(report: ActivationReport) -> str:
    live = report.item("live_source_health")
    live_status = {"pass": "On", "fail": "Source gap"}.get(
        live.status if live is not None else "", "Verified")
    return ("Mode: PRODUCTION_24X7 · Live Data: {0} · Scheduler: On · Broker: Disabled · "
            "Execution: Manual Review Only · Alert Delivery: On").format(live_status)


# --------------------------------------------------------------------------- #
# rollback_to_shadow -- ALWAYS available, never gated                           #
# --------------------------------------------------------------------------- #
def rollback_to_shadow(store_dir: str, *, now: str, actor: str,
                       reason: str = "") -> RollbackResult:
    """Roll the sanctioned mode DOWN to ``SHADOW_24X7`` -- always available, never blocked.

    Uses the accepted :func:`cosmosiq_service.activation.rollback` decision. From
    ``PRODUCTION_24X7`` this always steps down to ``SHADOW_24X7``; from ``SHADOW_24X7`` it is a
    no-op (already safe). It is NEVER gated by the activation gate -- stepping down to a safer mode
    can never be refused on evidence. Records an append-only rollback event either way. ``now`` is
    injected; offline; deterministic.
    """
    if not str(now).strip():
        raise ValueError("rollback_to_shadow requires an injected 'now' instant")
    current = _current_mode(store_dir)
    decision = rollback(current, ServiceMode.SHADOW_24X7)

    applied = False
    marker_path = ""
    if decision.allowed and ServiceMode.parse(decision.to_mode) is not current:
        from cosmosiq_ops.activate import _write_mode_marker
        marker_path = _write_mode_marker(
            store_dir, ServiceMode.SHADOW_24X7, now=now, trigger="operator_manual",
            trigger_description="operator rolled production back to shadow (PL-3)")
        applied = True

    event_path = _append_event(store_dir, {
        "event": _ROLLBACK_EVENT,
        "from_mode": current.value,
        "to_mode": ServiceMode.SHADOW_24X7.value,
        "applied": applied,
        "actor": str(actor or "").strip(),
        "rollback_reason": str(reason or "").strip(),
        "recorded_at": now,
        "broker": "disabled",
        "execution_boundary": "manual_review_only",
    })

    return RollbackResult(
        applied=applied, from_mode=current.value, to_mode=ServiceMode.SHADOW_24X7.value,
        reason=decision.reason, actor=str(actor or "").strip(),
        rollback_reason=str(reason or "").strip(), marker_path=marker_path, event_path=event_path)
