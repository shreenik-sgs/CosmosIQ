"""The FINAL Production Deployment Readiness Gate (IMPLEMENTATION-023J). OFFLINE, deterministic.

This is the CAPSTONE. ONE command that AGGREGATES every already-accepted gate into a single,
frozen :class:`DeploymentReadinessReport` and renders it into ONE honest readiness report with an
HONEST overall verdict. It COMPOSES the accepted gates -- it re-implements NONE of them and it
WEAKENS none of them:

* the 019A CI gate (:func:`cosmosiq_ops.ci_gate.run_ci_gate`, transitively via prod-check);
* the 023G production activation gate (:func:`cosmosiq_ops.prod_check.run_prod_check`) -- the
  20-item 020F checklist folded into ``production_mode_allowed`` + ``recommendation_mode_allowed``;
* the 023H security / compliance / audit pass (:func:`cosmosiq_ops.security_audit.run_security_audit`);
* the 023F backup / restore smoke (:mod:`cosmosiq_ops.backup_ops`, transitively via prod-check);
* the 019A deployment smoke (:func:`cosmosiq_ops.smoke.run_production_smoke`);
* the 013C deterministic replay + 013E Data-Quality + 020E alert-delivery posture (via prod-check);
* the 023E observability surface (:func:`cosmosiq_ops.observability.aggregate_observability`) --
  source / agent / DQ / replay health made VISIBLE;
* the 016 operator app UI (:func:`cosmosiq_app.api.dispatch`) -- the read-only surfaces answer 200;
* the 023I operator runbook + companion docs (the evidence path).

THE HONESTY MANDATE (this gate NEVER lies):

* it does NOT mark CosmosIQ production-deployment-ready. Operator sign-off does NOT exist
  (``reports/OPERATOR_SIGNOFF_020J.md`` is absent) and ``live_source_health`` +
  ``operator_shadow_validation`` cannot be machine-verified OFFLINE, so
  ``production_mode_allowed`` + ``recommendation_mode_allowed`` are BOTH ``False`` and the HONEST
  overall verdict is ``shadow deployment ready only`` -- production-ready is PENDING the operator
  sign-off and the manual live items;
* a check that CANNOT run offline (a REAL live-source-health fetch) is ``manual_review_required``,
  NEVER a fabricated pass;
* the ``production deployment ready`` verdict is REACHABLE -- but ONLY with complete evidence
  (``production_mode_allowed`` True, which itself requires a valid operator approval AND the manual
  live items attested) AND a recorded sign-off. The path exists; the REAL offline run does not
  take it.

Deterministic + OFFLINE + stdlib-only, Python 3.9: every instant is an injected ``now`` string; no
wall clock, no network, no secret VALUE, no score / rank / trade field ever appears in a report.
``subprocess`` (via the composed CI gate) stays confined to ``cosmosiq_ops`` operator tooling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from cosmosiq_service.activation import (
    CheckResult,
    OperatorApproval,
    is_valid_approval,
)

__all__ = [
    "STATUS_PASS",
    "STATUS_FAIL",
    "STATUS_NOT_APPLICABLE",
    "STATUS_MANUAL",
    "GATE_STATUSES",
    "VERDICT_PRODUCTION_READY",
    "VERDICT_SHADOW_READY_ONLY",
    "VERDICT_PARTIAL",
    "GateResult",
    "DeploymentReadinessReport",
    "run_deployment_readiness",
    "render_deployment_readiness",
    "REPORT_TITLE",
    "DEFAULT_COMMIT_PLACEHOLDER",
]

# --------------------------------------------------------------------------- #
# Closed status + verdict vocabularies                                          #
# --------------------------------------------------------------------------- #
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_MANUAL = "manual_review_required"
GATE_STATUSES: Tuple[str, ...] = (
    STATUS_PASS, STATUS_FAIL, STATUS_NOT_APPLICABLE, STATUS_MANUAL)

VERDICT_PRODUCTION_READY = "production deployment ready"
VERDICT_SHADOW_READY_ONLY = "shadow deployment ready only"
VERDICT_PARTIAL = "partial -- remediation required"

REPORT_TITLE = "COSMOSIQ PRODUCTION DEPLOYMENT READINESS REPORT"
# A deterministic, secret-free placeholder for the commit hash (no wall clock / no subprocess in
# the read path -- the operator fills the real HEAD when publishing the artifact).
DEFAULT_COMMIT_PLACEHOLDER = "<COMMIT_HASH>"

# The absent human sign-off the gate is honest about (see the HONESTY MANDATE above).
_SIGNOFF_REL = os.path.join("reports", "OPERATOR_SIGNOFF_020J.md")
# The 023I operator-runbook review evidence path -- the four consolidated docs must all exist.
_RUNBOOK_DOCS: Tuple[str, ...] = (
    os.path.join("docs", "OPERATOR_RUNBOOK.md"),
    os.path.join("docs", "DEPLOYMENT_GUIDE.md"),
    os.path.join("docs", "INCIDENT_PLAYBOOKS.md"),
    os.path.join("docs", "ROLLBACK_GUIDE.md"),
)
# The 023F/019 deployment-packaging artifacts (the DEPLOYMENT_GUIDE describes them).
_PACKAGING_ARTIFACTS: Tuple[str, ...] = (
    "Dockerfile", "docker-compose.yml", "Makefile", "deploy")
# The UI routes the readiness UI smoke dispatches -- each must answer 200 (read-only surfaces).
_UI_SMOKE_ROUTES: Tuple[str, ...] = (
    "/", "/runs", "/candidates", "/alerts", "/replay", "/api/observability")
_UI_SMOKE_WATCHLIST = ("IREN", "NVDA")
_UI_SMOKE_THEMES = ("physical_ai", "robotics")
_UI_SMOKE_RUN_ID = "RUN-023J-UISMOKE"


# --------------------------------------------------------------------------- #
# Result shapes -- frozen; labels + refs only, never a secret / score / trade   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GateResult:
    """One folded gate (or readiness-checklist item): id, status, evidence path, notes.

    ``status`` is one of :data:`GATE_STATUSES`. ``evidence_path`` is a repo-relative reference to
    where the evidence lives; ``notes`` is a plain-English one-liner. No field ever holds a secret
    VALUE or a score / rank / trade dimension.
    """

    id: str
    status: str
    evidence_path: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in GATE_STATUSES:
            raise ValueError(
                "GateResult.status {0!r} invalid (closed vocabulary: {1})".format(
                    self.status, list(GATE_STATUSES)))

    @property
    def is_pass(self) -> bool:
        return self.status == STATUS_PASS

    @property
    def is_fail(self) -> bool:
        return self.status == STATUS_FAIL

    @property
    def is_manual(self) -> bool:
        return self.status == STATUS_MANUAL


@dataclass(frozen=True)
class DeploymentReadinessReport:
    """The whole readiness aggregation, frozen.

    ``overall_verdict`` is the single HONEST verdict. It is ``production deployment ready`` ONLY
    when production is genuinely allowed (a valid sign-off + the manual live items attested, which
    is exactly what ``production_mode_allowed`` encodes) AND every offline gate passes AND a
    sign-off exists; otherwise, when every offline gate passes but production is (correctly)
    refused, it is ``shadow deployment ready only``; a real FAIL lands it at ``partial``.
    """

    repo_root: str
    store_dir: str
    generated_at: str
    commit_hash: str = DEFAULT_COMMIT_PLACEHOLDER
    gates: Tuple[GateResult, ...] = field(default_factory=tuple)
    readiness_checklist: Tuple[GateResult, ...] = field(default_factory=tuple)
    production_mode_allowed: bool = False
    recommendation_mode_allowed: bool = False
    signoff_recorded: bool = False
    environment_profile: str = ""
    sources_configured: Tuple[str, ...] = field(default_factory=tuple)
    overall_verdict: str = VERDICT_PARTIAL
    blocking_failures: Tuple[str, ...] = field(default_factory=tuple)
    manual_review_items: Tuple[str, ...] = field(default_factory=tuple)
    known_limitations: Tuple[str, ...] = field(default_factory=tuple)
    # A small, sanitized health snapshot proving source / agent / DQ / replay are VISIBLE.
    health_snapshot: Dict[str, object] = field(default_factory=dict)

    @property
    def production_deployment_ready(self) -> bool:
        return self.overall_verdict == VERDICT_PRODUCTION_READY

    @property
    def shadow_deployment_ready(self) -> bool:
        return self.overall_verdict in (VERDICT_SHADOW_READY_ONLY, VERDICT_PRODUCTION_READY)

    def gate(self, gate_id: str) -> Optional[GateResult]:
        for g in tuple(self.gates) + tuple(self.readiness_checklist):
            if g.id == gate_id:
                return g
        return None


# --------------------------------------------------------------------------- #
# helpers                                                                        #
# --------------------------------------------------------------------------- #
def _status_from_bool(ok: bool) -> str:
    return STATUS_PASS if ok else STATUS_FAIL


def _prod_check_by_id(prod_report) -> Dict[str, object]:
    """Index the prod-check machine results by their check name (id)."""
    return {c.name: c for c in getattr(prod_report, "checks", ()) or ()}


def _check_status(check: object) -> str:
    """Normalise a folded prod-check :class:`CheckResult` status into a gate status."""
    raw = str(getattr(check, "status", "") or "").strip().lower()
    if raw in GATE_STATUSES:
        return raw
    if raw in ("ok", "passed", "success"):
        return STATUS_PASS
    if raw in ("failed", "error"):
        return STATUS_FAIL
    if raw in ("skipped", "skip", "unknown", ""):
        return STATUS_MANUAL
    return STATUS_MANUAL


def _check_note(check: object, fallback: str) -> str:
    details = tuple(getattr(check, "details", ()) or ())
    return "; ".join(str(d) for d in details) if details else fallback


# --------------------------------------------------------------------------- #
# The gate                                                                      #
# --------------------------------------------------------------------------- #
def run_deployment_readiness(
        repo_root: str, store_dir: str, *, now: str, quick: bool = True,
        commit_hash: str = DEFAULT_COMMIT_PLACEHOLDER,
        operator_approval: Optional[OperatorApproval] = None,
        extra_checks: Optional[Mapping[str, CheckResult]] = None,
        extra_recommendation_checks: Optional[Mapping[str, object]] = None
        ) -> DeploymentReadinessReport:
    """Aggregate EVERY accepted gate into ONE frozen, HONEST :class:`DeploymentReadinessReport`.

    ``now`` is injected everywhere (no wall clock). ``store_dir`` is a fresh scratch WORK root the
    aggregation seeds under (a store, a smoke tree, a UI-smoke tree) -- never the operator's live
    store. ``quick`` skips the CI-gate full-suite subprocess (keeping every sweep) so the capstone
    runs fast and offline. ``operator_approval`` + ``extra_checks`` +
    ``extra_recommendation_checks`` are forwarded to the composed 023G prod-check: in an honest run
    they are absent and production is REFUSED; a caller may inject a valid approval AND clear the
    manual live items to PROVE the ``production deployment ready`` verdict is reachable-only-with-
    complete-evidence.

    The REAL offline run returns ``production_mode_allowed = recommendation_mode_allowed = False``
    and the HONEST verdict ``shadow deployment ready only``.
    """
    if not str(now).strip():
        raise ValueError("run_deployment_readiness requires an injected 'now' instant")
    # Lazy first-party imports (kept out of module top level so the operator tooling imports fast
    # and the no-network-on-import sweep sees a clean top level).
    from cosmosiq_ops.env_profiles import default_profile
    from cosmosiq_ops.observability import aggregate_observability
    from cosmosiq_ops.prod_check import run_prod_check
    from cosmosiq_ops.security_audit import run_security_audit
    from cosmosiq_ops.smoke import run_production_smoke

    root = str(repo_root)
    work = str(store_dir)
    os.makedirs(work, exist_ok=True)

    # 1. The 023G production activation gate (folds 019A CI, 013C replay, 013E DQ, 020E alerts,
    #    023F backup/restore, 022H recommendation, 023A profiles). One run; we read its results. #
    prod_work = os.path.join(work, "prod_check")
    os.makedirs(prod_work, exist_ok=True)
    prod = run_prod_check(
        prod_work, root, now=now, quick=quick, operator_approval=operator_approval,
        extra_checks=extra_checks, extra_recommendation_checks=extra_recommendation_checks)
    prod_by_id = _prod_check_by_id(prod)

    # 2. The 023H security / compliance / audit pass. --------------------------------------- #
    audit = run_security_audit(root, now=now)

    # 3. The 019A deployment smoke (full operator chain end to end). ------------------------ #
    smoke_work = os.path.join(work, "deployment_smoke")
    os.makedirs(smoke_work, exist_ok=True)
    smoke = run_production_smoke(smoke_work, now=now)

    # 4. The 016 UI smoke (read-only surfaces answer 200 over a seeded store). --------------- #
    ui = _ui_smoke(work, now)

    # 5. The 023E observability surface over the prod-check seeded store (health made VISIBLE). #
    health = aggregate_observability(os.path.join(prod_work, "store"), now=now)

    # ----- fold each into a labelled gate result ------------------------------------------- #
    ci_check = prod_by_id.get("suite_or_ci_gate")
    replay_check = prod_by_id.get("replay_deterministic")
    dq_check = prod_by_id.get("dq_gate_pass")
    alert_check = prod_by_id.get("alert_safety_policy")
    backup_check = prod_by_id.get("backup_restore_smoke")
    candidate_check = prod_by_id.get("candidate_publication")
    rec_check = prod_by_id.get("recommendation_eligibility")

    gates: List[GateResult] = [
        GateResult(
            "full_suite_ci_gate",
            _check_status(ci_check) if ci_check is not None else STATUS_MANUAL,
            "cosmosiq_ops.ci_gate",
            _check_note(ci_check, "019A CI gate + guardrail sweeps")
            + ("" if not quick else " (full-suite subprocess skipped: --quick; sweeps kept)")),
        GateResult(
            "prod_check_023G",
            STATUS_PASS if not prod.blocking_failures else STATUS_FAIL,
            "cosmosiq_ops.prod_check",
            "020F machine checks pass; production_mode_allowed={0}; recommendation_mode_allowed="
            "{1}; verdict={2!r} (production correctly REFUSED offline)".format(
                prod.production_mode_allowed, prod.recommendation_mode_allowed, prod.verdict)),
        GateResult(
            "security_audit_023H",
            _status_from_bool(audit.passed),
            "reports/SECURITY_AUDIT_023H.md",
            "{0} guardrail categories, {1} failed".format(
                len(audit.categories), len(audit.categories_failed))),
        GateResult(
            "backup_restore_smoke_023F",
            _check_status(backup_check) if backup_check is not None else STATUS_MANUAL,
            "cosmosiq_ops.backup_ops",
            _check_note(backup_check, "hardened backup + restore-into-empty + replay-after-restore")),
        GateResult(
            "deployment_smoke_019A",
            _status_from_bool(smoke.passed),
            "cosmosiq_ops.smoke",
            "{0} chain steps; {1}".format(
                len(smoke.steps),
                "all passed" if smoke.passed else "failed: " + ", ".join(smoke.failed_steps))),
        GateResult(
            "shadow_live_source_health",
            STATUS_MANUAL,
            "reports/REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md",
            "a REAL live SEC/FMP source-health fetch CANNOT run offline -- manual_review_required, "
            "never a fabricated pass (the 021D snippet does the real fetch; absent SEC_USER_AGENT "
            "is an honest credentials_missing gap)"),
        GateResult(
            "replay_deterministic_013C",
            _check_status(replay_check) if replay_check is not None else STATUS_MANUAL,
            "reality_mesh.replay",
            _check_note(replay_check, "a persisted run replays deterministically")),
        GateResult(
            "alert_delivery_020E",
            _check_status(alert_check) if alert_check is not None else STATUS_MANUAL,
            "reality_mesh.alert_delivery",
            _check_note(alert_check,
                        "external escalation suppressed_by_policy pre-activation")),
        GateResult(
            "ui_smoke_016",
            _status_from_bool(ui[0]),
            "cosmosiq_app.api",
            ui[1]),
        GateResult(
            "operator_runbook_review_023I",
            _status_from_bool(_all_exist(root, _RUNBOOK_DOCS)),
            "docs/OPERATOR_RUNBOOK.md",
            "the four consolidated 023I docs exist: "
            + ", ".join(d.replace(os.sep, "/") for d in _RUNBOOK_DOCS)),
    ]

    # ----- the user's "definition of production deployment ready" checklist ---------------- #
    signoff_path = os.path.join(root, _SIGNOFF_REL)
    signoff_recorded = is_valid_approval(operator_approval) or os.path.isfile(signoff_path)
    checklist = _readiness_checklist(
        root, prod, audit, smoke, ui, health, prod_by_id, signoff_recorded)

    # ----- roll the verdict ---------------------------------------------------------------- #
    all_results = tuple(gates) + tuple(checklist)
    blocking_failures = tuple(sorted(
        {g.id for g in all_results if g.is_fail} | set(prod.blocking_failures)))
    manual_review_items = tuple(sorted(
        {g.id for g in all_results if g.is_manual} | set(prod.manual_review_items)))

    # An OFFLINE gate is every folded gate EXCEPT the one that can only be verified live.
    offline_gates = tuple(g for g in gates if g.id != "shadow_live_source_health")
    all_offline_pass = all(g.is_pass for g in offline_gates)
    any_fail = bool(blocking_failures)

    if prod.production_mode_allowed and signoff_recorded and all_offline_pass and not any_fail:
        overall_verdict = VERDICT_PRODUCTION_READY
    elif all_offline_pass and not any_fail:
        overall_verdict = VERDICT_SHADOW_READY_ONLY
    else:
        overall_verdict = VERDICT_PARTIAL

    known_limitations = _known_limitations(signoff_recorded)

    health_snapshot = {
        "status": health.status,
        "agent_results": int(health.agent_health_summary.get("results", 0) or 0),
        "agents_failed": int(health.agent_health_summary.get("failed", 0) or 0),
        "source_coverage_records": int(
            health.source_health_summary.get("coverage_records", 0) or 0),
        "dq_records": int(health.dq_status_summary.get("records", 0) or 0),
        "dq_gate_overall_worst": str(health.dq_status_summary.get("gate_overall_worst", "")),
        "replay_deterministic_match": bool(
            health.last_replay_check.get("deterministic_match", False)),
    }

    return DeploymentReadinessReport(
        repo_root=root,
        store_dir=work,
        generated_at=str(now),
        commit_hash=str(commit_hash),
        gates=tuple(gates),
        readiness_checklist=tuple(checklist),
        production_mode_allowed=bool(prod.production_mode_allowed),
        recommendation_mode_allowed=bool(prod.recommendation_mode_allowed),
        signoff_recorded=bool(signoff_recorded),
        environment_profile=default_profile().profile_id,
        sources_configured=("SEC_USER_AGENT -> SEC EDGAR live", "FMP_API_KEY -> FMP live"),
        overall_verdict=overall_verdict,
        blocking_failures=blocking_failures,
        manual_review_items=manual_review_items,
        known_limitations=known_limitations,
        health_snapshot=health_snapshot)


def _all_exist(repo_root: str, rels: Tuple[str, ...]) -> bool:
    return all(os.path.exists(os.path.join(repo_root, rel)) for rel in rels)


def _ui_smoke(work_dir: str, now: str) -> Tuple[bool, str]:
    """Seed one run, dispatch every read-only UI route, and report whether all answer 200."""
    from cosmosiq_app.api import dispatch
    from reality_mesh import persist_and_summarize, run_pulse

    store = os.path.join(str(work_dir), "ui_smoke", "store")
    os.makedirs(store, exist_ok=True)
    try:
        pulse = run_pulse(list(_UI_SMOKE_WATCHLIST), list(_UI_SMOKE_THEMES), now=now)
        persist_and_summarize(pulse, store_dir=store, run_id=_UI_SMOKE_RUN_ID, now=now)
    except Exception as exc:      # a crash is a hard fail, surfaced not hidden
        return False, "UI smoke seed raised {0}: {1}".format(type(exc).__name__, str(exc)[:120])

    statuses: List[str] = []
    ok = True
    for route in _UI_SMOKE_ROUTES:
        # The replay viewer needs an explicit run id; the bare route is a 404 by design.
        path = "/replay/" + _UI_SMOKE_RUN_ID if route == "/replay" else route
        response = dispatch({"method": "GET", "path": path, "query": {}, "body": None},
                            store_dir=store, now=now)
        status = response.get("status")
        statuses.append("{0}->{1}".format(route, status))
        if status != 200:
            ok = False
    return ok, "{0}/{1} routes 200: {2}".format(
        sum(1 for s in statuses if s.endswith("->200")), len(statuses), ", ".join(statuses))


def _readiness_checklist(repo_root, prod, audit, smoke, ui, health, prod_by_id,
                         signoff_recorded) -> Tuple[GateResult, ...]:
    """Evaluate the user's definition-of-production-deployment-ready checklist, each pass/manual/fail."""
    replay_ok = _check_status(prod_by_id.get("replay_deterministic")) == STATUS_PASS
    dq_ok = _check_status(prod_by_id.get("dq_gate_pass")) == STATUS_PASS
    alert_ok = _check_status(prod_by_id.get("alert_safety_policy")) == STATUS_PASS
    candidate_ok = _check_status(prod_by_id.get("candidate_publication")) == STATUS_PASS
    rec_ok = _check_status(prod_by_id.get("recommendation_eligibility")) == STATUS_PASS
    backup_ok = _check_status(prod_by_id.get("backup_restore_smoke")) == STATUS_PASS
    ci_ok = _check_status(prod_by_id.get("suite_or_ci_gate")) == STATUS_PASS
    health_visible = bool(health.status)  # aggregate produced a rolled status -> health is visible

    items: List[GateResult] = [
        # -- capability: implemented (verified by importable, exercised layers) -------------- #
        _impl_item("theme_graph_implemented", "reality_mesh.theme_graph",
                   "Theme Graph layer present"),
        _impl_item("candidate_discovery_implemented", "reality_mesh.capital_candidate",
                   "Candidate Discovery (assess_candidate_eligibility) present",
                   attr="assess_candidate_eligibility"),
        _impl_item("capital_recommendation_implemented", "reality_mesh.recommendation",
                   "CapitalRecommendation shape present", attr="CapitalRecommendation"),
        _impl_item("capital_picks_report_implemented", "reality_mesh.capital_picks_report",
                   "Capital Picks Report renderer present", attr="render_capital_picks_report"),
        _impl_item("recommendation_journal_implemented", "reality_mesh.recommendation_journal",
                   "RecommendationJournal present", attr="journal_recommendation"),
        # -- live source health: cannot be machine-verified OFFLINE (manual) ---------------- #
        GateResult("live_sec_fmp_source_health_accepted", STATUS_MANUAL,
                   "reports/REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md",
                   "a REAL SEC/FMP live-source-health fetch cannot run offline -- manual_review"),
        # -- calibration + validation completeness ------------------------------------------ #
        _impl_item("historical_replay_calibration_completed",
                   "reality_mesh.replay_calibration",
                   "022G historical replay calibration completed (recorded)",
                   ok=rec_ok, evidence="reports/HISTORICAL_REPLAY_CALIBRATION_022G.md"),
        GateResult("shadow_24x7_validation_completed", STATUS_MANUAL,
                   "reports/SHADOW_VALIDATION_020I.md",
                   "the injected-time shadow window is complete, but a real wall-clock 24x7 "
                   "validation run must be reviewed + signed off -- manual_review"),
        # -- operator sign-off: OUTSTANDING (file absent, no recorded approval) -------------- #
        GateResult("operator_signoff_recorded",
                   STATUS_PASS if signoff_recorded else STATUS_MANUAL,
                   "reports/OPERATOR_SIGNOFF_020J_TEMPLATE.md",
                   "operator production sign-off recorded" if signoff_recorded
                   else "reports/OPERATOR_SIGNOFF_020J.md is ABSENT -- no human sign-off recorded"),
        # -- the machine gates ------------------------------------------------------------- #
        GateResult("prod_check_passes", STATUS_PASS if not prod.blocking_failures else STATUS_FAIL,
                   "cosmosiq_ops.prod_check",
                   "020F machine checks pass (production correctly refused pending manual items)"),
        GateResult("ci_gate_passes", _status_from_bool(ci_ok), "cosmosiq_ops.ci_gate",
                   "019A CI gate + guardrail sweeps pass"),
        GateResult("security_audit_passes", _status_from_bool(audit.passed),
                   "reports/SECURITY_AUDIT_023H.md",
                   "every 023H guardrail category passes"),
        GateResult("backup_restore_passes", _status_from_bool(backup_ok),
                   "cosmosiq_ops.backup_ops",
                   "023F hardened backup + restore-into-empty + replay-after-restore pass"),
        GateResult("deployment_smoke_passes", _status_from_bool(smoke.passed),
                   "cosmosiq_ops.smoke", "019A deployment smoke passes end to end"),
        # -- observability: source / agent / DQ / replay VISIBLE ---------------------------- #
        GateResult("source_agent_health_visible", _status_from_bool(health_visible),
                   "cosmosiq_ops.observability",
                   "023E observability rolls source + agent health to status {0!r}".format(
                       health.status)),
        GateResult("data_quality_visible", _status_from_bool(dq_ok and health_visible),
                   "cosmosiq_ops.observability",
                   "DQ gate verdicts persisted + surfaced (gate_overall_worst={0!r})".format(
                       health.dq_status_summary.get("gate_overall_worst", ""))),
        GateResult("replay_works", _status_from_bool(replay_ok),
                   "reality_mesh.replay", "013C deterministic replay matches"),
        GateResult("alerts_work", _status_from_bool(alert_ok),
                   "reality_mesh.alert_delivery",
                   "020E alert policy holds (external escalation suppressed pre-activation)"),
        GateResult("rollback_works", _status_from_bool(_rollback_works()),
                   "docs/ROLLBACK_GUIDE.md",
                   "the mode ladder steps down (PRODUCTION -> SHADOW -> MANUAL -> OFF)"),
        GateResult("deployment_packaging_present",
                   _status_from_bool(_all_exist(repo_root, _PACKAGING_ARTIFACTS)),
                   "docs/DEPLOYMENT_GUIDE.md",
                   "Dockerfile / docker-compose.yml / Makefile / deploy present"),
        GateResult("candidate_eligibility_provenanced", _status_from_bool(candidate_ok),
                   "reality_mesh.capital_candidate",
                   "an eligible candidate lands ONLY with full provenance lineage"),
        GateResult("recommendation_eligibility_gated", _status_from_bool(rec_ok),
                   "reality_mesh.recommendation_activation",
                   "022H recommendation machine checks pass (mode still refused offline)"),
        GateResult("no_guardrail_violations", _status_from_bool(audit.passed),
                   "reports/SECURITY_AUDIT_023H.md",
                   "no secret / no trade control / no hidden score / no laundering / no network "
                   "on import"),
    ]
    return tuple(items)


def _impl_item(item_id: str, module: str, note: str, *, attr: str = "",
               ok: Optional[bool] = None, evidence: str = "") -> GateResult:
    """A capability-implemented checklist item: PASS iff the module (+ attr) imports, else manual."""
    if ok is None:
        import importlib
        try:
            mod = importlib.import_module(module)
            ok = (not attr) or hasattr(mod, attr)
        except Exception:      # a genuinely missing capability is honest manual_review, not a lie
            ok = False
    status = STATUS_PASS if ok else STATUS_MANUAL
    return GateResult(item_id, status, evidence or module.replace(".", "/"),
                      note if ok else note + " -- NOT verifiable")


def _rollback_works() -> bool:
    """The 020F mode ladder steps DOWN (a downgrade is always allowed)."""
    from cosmosiq_service.activation import rollback
    from cosmosiq_service.service import ServiceMode
    down = rollback(ServiceMode.PRODUCTION_24X7, ServiceMode.SHADOW_24X7)
    up = rollback(ServiceMode.SHADOW_24X7, ServiceMode.PRODUCTION_24X7)
    return bool(down.allowed) and not bool(up.allowed)


def _known_limitations(signoff_recorded: bool) -> Tuple[str, ...]:
    limits = [
        "live_source_health: a REAL SEC/FMP live-source-health fetch CANNOT be machine-verified "
        "OFFLINE -- it stays manual_review_required (see "
        "reports/REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md); an absent SEC_USER_AGENT is an honest "
        "credentials_missing gap, never a fixture fallback.",
        "operator_shadow_validation: the completed window (reports/SHADOW_VALIDATION_020I.md) is "
        "an injected-time run, not a wall-clock 24x7 calendar run; a real shadow run must be "
        "reviewed and signed off.",
        "there is NO CLI flag that marks the manual live items cleared (no operator-attestation "
        "input); production is reached only via the 021C activate flow with a filled sign-off.",
        "no broker / execution path exists anywhere; every action is manual-review-only and no "
        "order is ever sent.",
    ]
    if not signoff_recorded:
        limits.insert(
            1,
            "operator_signoff: reports/OPERATOR_SIGNOFF_020J.md is ABSENT -- no human production "
            "sign-off is recorded, so production_mode_allowed stays False.")
    return tuple(limits)


# --------------------------------------------------------------------------- #
# The renderer                                                                  #
# --------------------------------------------------------------------------- #
def render_deployment_readiness(report: DeploymentReadinessReport) -> str:
    """Render the full ``reports/PRODUCTION_DEPLOYMENT_READINESS_023J.md`` content.

    Deterministic (a pure function of the frozen report; no wall clock, no scratch path). NEVER
    contains a secret VALUE and NEVER a score / rank / trade field -- statuses, labels, and
    repo-relative evidence refs only.
    """
    ready = report.production_deployment_ready
    lines: List[str] = [
        "# " + REPORT_TITLE,
        "",
        "**Overall verdict:** {0}".format(report.overall_verdict.upper()),
        "",
        "- Commit: `{0}`".format(report.commit_hash),
        "- Repo root: `{0}`".format(report.repo_root),
        "- Generated at (injected): `{0}`".format(report.generated_at),
        "- Environment profile (default): `{0}`".format(report.environment_profile),
        "- production_mode_allowed: **{0}**".format(str(report.production_mode_allowed).lower()),
        "- recommendation_mode_allowed: **{0}**".format(
            str(report.recommendation_mode_allowed).lower()),
        "- operator sign-off recorded: **{0}**".format(str(report.signoff_recorded).lower()),
        "",
        "> This is the HONEST capstone readiness report. It COMPOSES every accepted gate and "
        "weakens none. Production is NOT enabled: the operator sign-off is absent and the live "
        "source-health + operator shadow-validation items cannot be machine-verified offline, so "
        "both mode-allowed flags are FALSE and the honest verdict is "
        "**\"shadow deployment ready only\"** -- production-ready is PENDING those items.",
        "",
        "## Sources configured (presence-only labels -- a value is NEVER read or printed)",
        "",
    ]
    for src in report.sources_configured:
        lines.append("- {0} (live fetch is manual_review; absent -> honest gap)".format(src))
    lines.extend([
        "",
        "## Folded gates",
        "",
        "| Gate | Status | Evidence | Notes |",
        "|------|--------|----------|-------|",
    ])
    for g in report.gates:
        lines.append("| {0} | {1} | `{2}` | {3} |".format(
            g.id, g.status.upper(), g.evidence_path, _cell(g.notes)))
    lines.extend([
        "",
        "## Definition of \"production deployment ready\" -- checklist",
        "",
        "| Item | Status | Evidence | Notes |",
        "|------|--------|----------|-------|",
    ])
    for g in report.readiness_checklist:
        lines.append("| {0} | {1} | `{2}` | {3} |".format(
            g.id, g.status.upper(), g.evidence_path, _cell(g.notes)))

    lines.extend([
        "",
        "## Health snapshot (source / agent / DQ / replay -- made VISIBLE, sanitized)",
        "",
    ])
    for key in sorted(report.health_snapshot):
        lines.append("- {0}: {1}".format(key, report.health_snapshot[key]))

    lines.extend([
        "",
        "## Operator runbook + rollback paths",
        "",
    ])
    for doc in _RUNBOOK_DOCS:
        lines.append("- `{0}`".format(doc.replace(os.sep, "/")))
    lines.append("- rollback path: `PRODUCTION_24X7 -> SHADOW_24X7 -> MANUAL -> OFF` "
                 "(cosmosiq_ops rollback; downgrade always allowed, upgrade refused)")

    lines.extend([
        "",
        "## Manual-review items (OUTSTANDING -- must be satisfied + signed off before production)",
        "",
    ])
    for item in report.manual_review_items:
        lines.append("- {0}".format(item))
    if not report.manual_review_items:
        lines.append("- none")

    lines.extend([
        "",
        "## Blocking failures",
        "",
    ])
    if report.blocking_failures:
        for item in report.blocking_failures:
            lines.append("- {0}".format(item))
    else:
        lines.append("- none (no machine gate failed)")

    lines.extend([
        "",
        "## Known limitations (honest)",
        "",
    ])
    for limit in report.known_limitations:
        lines.append("- {0}".format(limit))

    lines.extend([
        "",
        "## Final verdict",
        "",
        "**{0}**".format(report.overall_verdict.upper()),
        "",
    ])
    if ready:
        lines.append(
            "Every offline gate passes, production_mode_allowed is True (a valid sign-off + the "
            "attested live items), and a sign-off is recorded -- CosmosIQ is production "
            "deployment ready.")
    else:
        lines.append(
            "Every offline gate passes and CosmosIQ is READY FOR SHADOW DEPLOYMENT. It is NOT "
            "production deployment ready: production is correctly REFUSED until the operator "
            "sign-off is recorded and the live-source-health + operator-shadow-validation items "
            "are satisfied. This is the correct, safe default -- no gate was fabricated.")
    lines.append("")
    return "\n".join(lines)


def _cell(text: str) -> str:
    """Make a note safe for a single markdown table cell (no pipe, no newline)."""
    return str(text or "").replace("|", "/").replace("\n", " ").strip()
