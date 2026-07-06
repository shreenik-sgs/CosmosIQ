"""The CosmosIQ production activation check (IMPLEMENTATION-020F). OFFLINE, local files only.

``run_prod_check`` runs every machine-verifiable activation precondition against a fresh scratch
work dir + the repo, entirely offline, and folds the results into the 020F activation checklist
(:mod:`cosmosiq_service.activation`). It NEVER promotes to production on its own: the honest
OFFLINE outcome is ``production_mode_allowed = False`` -- the live-source-health fetch, the
operator shadow-validation, and the human sign-off are ``manual_review_required`` and BLOCKING,
so the verdict lands at "shadow 24x7 only" until those are satisfied AND explicitly approved.

The machine checks (each an offline, deterministic pass/fail):

1. the 019A CI gate (the full suite + every guardrail sweep) passes (``suite_or_ci_gate``);
2. the mode state machine is safe (default OFF; production gated) + no auto promotion;
3. the 020B SEC adapter passes an OFFLINE mock-transport dry-run (``sec_adapter_offline_smoke``);
4. a scheduler dry-run resolves one due-policy tick (no loop) + the 020C service is healthy;
5. a persisted run REPLAYS deterministically; the DQ gates raise no hard fail;
6. the 020A publish path runs (an eligible candidate lands only with full provenance);
7. the 020E alert-safety policy blocks all external escalation pre-activation + no forbidden phrase;
8. the product UI carries no trade control / hidden score / fixture-ticker leakage; the demo build
   is byte-identical; no secret / tracked .env;
9. the 020F runbook + activation-checklist docs exist.

``subprocess`` (the CI-gate suite run) is confined to this ``cosmosiq_ops`` package -- operator
tooling that inspects the repository, never imported by runtime code. Exit is NON-ZERO whenever
production is not allowed (the safe default).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from cosmosiq_ops.ci_gate import (
    GATE_PAGE_PATHS,
    SECRET_KEY_TOKENS,
    SECRET_VALUE_PATTERNS,
    TRADE_WORD_RE,
    check_demo_build_byte_identical,
    check_env_not_tracked,
    check_no_score_rank_functions,
    format_ci_gate_report,
    run_ci_gate,
)
from cosmosiq_service.activation import (
    CheckResult,
    OperatorApproval,
    evaluate_activation,
    promote,
)
from cosmosiq_service.service import (
    ServiceConfig,
    ServiceMode,
    can_enter_production_continuous,
    continuous_activation_gate,
    load_health,
    requires_activation_gate,
    run_once,
)
from reality_mesh.recommendation_activation import (
    RecommendationActivationReport,
    evaluate_recommendation_activation,
    run_recommendation_checks,
)

# The real fixture tickers -- the DEFAULT product UI must show none of these (no demo leakage).
FIXTURE_TICKERS: Tuple[str, ...] = ("IREN", "AAOI", "NVDA")
# The plantable output trees the page scans also sweep (relative to repo_root).
_PLANTABLE_PAGE_DIRS = ("generated", "pages")
_PROD_WATCHLIST = ("IREN", "NVDA")
_PROD_THEMES = ("physical_ai", "robotics")
_PROD_RUN_ID = "RUN-PRODCHECK-001"
_HARD_FAIL_STATUSES = frozenset({"failed", "blocked_by_policy"})


# --------------------------------------------------------------------------- #
# The report                                                                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProdCheckReport:
    """The whole prod-check run: the machine results + the folded activation reports.

    Carries BOTH honest verdicts, each derived from its own accepted gate and never re-implemented:
    ``production_mode_allowed`` from the 020F :func:`evaluate_activation` (``activation``) and
    ``recommendation_mode_allowed`` from the 022H :func:`evaluate_recommendation_activation`
    (``recommendation``). Both stay ``False`` in an honest OFFLINE run -- neither gate is weakened.
    """

    work_dir: str
    repo_root: str
    checks: Tuple[CheckResult, ...] = field(default_factory=tuple)
    activation: object = None            # cosmosiq_service.activation.ActivationReport
    recommendation: object = None        # reality_mesh...RecommendationActivationReport

    @property
    def production_mode_allowed(self) -> bool:
        return bool(self.activation and self.activation.production_mode_allowed)

    @property
    def recommendation_mode_allowed(self) -> bool:
        return bool(self.recommendation and self.recommendation.recommendation_mode_allowed)

    @property
    def verdict(self) -> str:
        return self.activation.verdict if self.activation else ""

    @property
    def recommendation_verdict(self) -> str:
        return self.recommendation.verdict if self.recommendation else ""

    @property
    def blocking_failures(self) -> Tuple[str, ...]:
        return self.activation.blocking_failures if self.activation else ()

    @property
    def manual_review_items(self) -> Tuple[str, ...]:
        return self.activation.manual_review_items if self.activation else ()

    @property
    def evidence_paths(self) -> Tuple[str, ...]:
        return self.activation.evidence_paths if self.activation else ()

    @property
    def recommendation_blocking_failures(self) -> Tuple[str, ...]:
        return self.recommendation.blocking_failures if self.recommendation else ()

    @property
    def recommendation_manual_review_items(self) -> Tuple[str, ...]:
        return self.recommendation.manual_review_items if self.recommendation else ()


# --------------------------------------------------------------------------- #
# Page rendering + token scans (reuse the ci_gate primitives)                   #
# --------------------------------------------------------------------------- #
def _render_product_pages(store_dir: str, now: str) -> List[Tuple[str, str]]:
    """Render every product page over ``store_dir`` -> [(label, html)] (offline, injected now)."""
    from cosmosiq_app.api import dispatch
    rendered: List[Tuple[str, str]] = []
    for path in GATE_PAGE_PATHS:
        response = dispatch({"method": "GET", "path": path, "query": {}, "body": None},
                            store_dir=store_dir, now=now)
        rendered.append(("page " + path, str(response.get("body") or "")))
    return rendered


def _planted_html(repo_root: str) -> List[Tuple[str, str]]:
    """Any html sitting in the plantable output trees of ``repo_root`` -> [(label, text)]."""
    found: List[Tuple[str, str]] = []
    for rel_dir in _PLANTABLE_PAGE_DIRS:
        base = os.path.join(repo_root, rel_dir)
        if not os.path.isdir(base):
            continue
        for root, dirs, names in os.walk(base):
            dirs.sort()
            for name in sorted(names):
                if name.endswith((".html", ".htm")):
                    path = os.path.join(root, name)
                    label = os.path.relpath(path, repo_root).replace(os.sep, "/")
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        found.append((label, fh.read()))
    return found


def _scan_no_trade_control(repo_root: str, now: str) -> CheckResult:
    """No buy/sell/order/broker/auto-trade control in the DEFAULT product UI or planted html."""
    findings: List[str] = []
    with tempfile.TemporaryDirectory() as store_dir:
        surfaces = _render_product_pages(store_dir, now) + _planted_html(repo_root)
    for label, text in surfaces:
        match = TRADE_WORD_RE.search(text)
        if match:
            findings.append("{0}: trade-affordance token '{1}'".format(label, match.group(0)))
    status = "fail" if findings else "pass"
    return CheckResult("no_trade_control", status,
                       tuple(findings) or ("{0} surfaces scanned; 0 trade-affordance token"
                                           .format(len(surfaces)),))


def _scan_fixture_leakage(repo_root: str, now: str) -> CheckResult:
    """The DEFAULT product UI (empty store) shows no real fixture ticker (no demo/fixture leak)."""
    findings: List[str] = []
    with tempfile.TemporaryDirectory() as store_dir:      # a FRESH store -> the default posture
        surfaces = _render_product_pages(store_dir, now) + _planted_html(repo_root)
    for label, text in surfaces:
        for ticker in FIXTURE_TICKERS:
            if _contains_ticker(text, ticker):
                findings.append("{0}: fixture-ticker leakage '{1}'".format(label, ticker))
    status = "fail" if findings else "pass"
    return CheckResult("fixture_leakage", status,
                       tuple(findings) or ("{0} default surfaces scanned; 0 fixture ticker"
                                           .format(len(surfaces)),))


def _contains_ticker(text: str, ticker: str) -> bool:
    """A whole-word (uppercase) ticker match -- avoids matching inside unrelated words."""
    import re
    return re.search(r"\b" + re.escape(ticker) + r"\b", text) is not None


def _scan_secrets(repo_root: str, now: str) -> CheckResult:
    """No secret value in any rendered / planted page AND no tracked .env."""
    findings: List[str] = []
    with tempfile.TemporaryDirectory() as store_dir:
        surfaces = _render_product_pages(store_dir, now) + _planted_html(repo_root)
    for label, text in surfaces:
        lowered = text.lower()
        for pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(text):
                findings.append("{0}: secret-like value matching {1}".format(
                    label, pattern.pattern))
        for token in SECRET_KEY_TOKENS:
            if token in lowered:
                findings.append("{0}: credential key token '{1}'".format(label, token))
    env = check_env_not_tracked(repo_root)
    if env.status == "fail":
        findings.extend(env.details)
    status = "fail" if findings else "pass"
    return CheckResult("secret_scan", status,
                       tuple(findings) or ("{0} surfaces scanned + .env untracked; 0 secret"
                                           .format(len(surfaces)),))


# --------------------------------------------------------------------------- #
# Machine checks over a seeded scratch store                                     #
# --------------------------------------------------------------------------- #
def _sec_adapter_offline_smoke(now: str) -> CheckResult:
    """The 020B SEC EDGAR live adapter passes an OFFLINE mock-transport dry-run."""
    from reality_mesh.adapters.sec_edgar_live import SecEdgarLiveAdapter

    def _company_tickers():
        return {"0": {"cik_str": 1878848, "ticker": "IREN", "title": "IREN Limited"}}

    def _submissions(cik):
        return {"cik": str(cik), "name": "IREN Limited", "tickers": ["IREN"],
                "filings": {"recent": {
                    "accessionNumber": ["0001878848-26-000050"], "form": ["8-K"],
                    "filingDate": ["2026-06-30"], "primaryDocument": ["iren8k.htm"],
                    "primaryDocDescription": ["FORM 8-K"], "items": ["1.01"]}}}

    try:
        adapter = SecEdgarLiveAdapter(
            transport={"company_tickers": _company_tickers, "submissions": _submissions},
            sec_user_agent_present=True)
        events, result = adapter.fetch_checked(
            watchlist=["IREN"], themes=["physical_ai"], now=now)
    except Exception as exc:      # any crash is a hard fail, surfaced not hidden
        return CheckResult("sec_adapter_offline_smoke", "fail",
                           ("mock-transport dry-run raised {0}: {1}".format(
                               type(exc).__name__, str(exc)[:160]),))
    ok = result.status in ("success", "partial") and events is not None
    return CheckResult(
        "sec_adapter_offline_smoke", "pass" if ok else "fail",
        ("offline mock-transport dry-run: {0} event(s), result status {1!r}".format(
            len(events), result.status),))


def _scheduler_dry_run(now: str) -> CheckResult:
    """A scheduler dry-run resolves ONE due-policy tick (no loop, injected now)."""
    from reality_mesh.orchestrator import run_due_pulses
    from reality_mesh.scheduler import DEFAULT_MARKET_HOURS, build_default_schedule
    with tempfile.TemporaryDirectory() as store_dir:
        schedule = build_default_schedule(max_runs_per_hour=60)
        try:
            result = run_due_pulses(schedule, now=now, store_dir=store_dir, subscriptions=(),
                                    calendar=DEFAULT_MARKET_HOURS, max_pulses=1)
        except Exception as exc:
            return CheckResult("scheduler_dry_run", "fail",
                               ("one-tick dry-run raised {0}: {1}".format(
                                   type(exc).__name__, str(exc)[:160]),))
    ran = len(getattr(result, "ran", ()) or ())
    skipped = len(getattr(result, "skipped", ()) or ())
    return CheckResult("scheduler_dry_run", "pass",
                       ("one due-policy tick resolved (no loop): {0} ran, {1} skipped".format(
                           ran, skipped),))


def _service_wrapper_health(store_dir: str, now: str) -> CheckResult:
    """The 020C supervised service reports an honest, sanitized health snapshot (one MANUAL tick)."""
    config = ServiceConfig(mode=ServiceMode.MANUAL, store_dir=store_dir)
    try:
        run_once(config, now=now, pid=0)
        health = load_health(config)
    except Exception as exc:
        return CheckResult("service_wrapper_health", "fail",
                           ("service tick/health raised {0}: {1}".format(
                               type(exc).__name__, str(exc)[:160]),))
    known = {m.value for m in ServiceMode}
    ok = health.service_mode in known
    return CheckResult("service_wrapper_health", "pass" if ok else "fail",
                       ("service health snapshot: mode={0}, failures={1}".format(
                           health.service_mode, health.consecutive_failures),))


def _replay_and_dq(store_dir: str, now: str) -> Tuple[CheckResult, CheckResult, CheckResult]:
    """Seed one run: persist -> replay -> DQ gate -> candidate publication. Returns 3 results."""
    from reality_mesh import (
        DataQualityStore,
        persist_and_summarize,
        run_pulse,
    )
    from reality_mesh.capital_candidate import publish_candidates_for_run

    pulse = run_pulse(list(_PROD_WATCHLIST), list(_PROD_THEMES), now=now)
    _run, replay_result, _panels = persist_and_summarize(
        pulse, store_dir=store_dir, run_id=_PROD_RUN_ID, now=now)

    replay = CheckResult(
        "replay_deterministic",
        "pass" if replay_result.deterministic_match else "fail",
        ("replay deterministic_match={0}{1}".format(
            replay_result.deterministic_match,
            "" if replay_result.deterministic_match
            else " -- " + "; ".join(replay_result.differences)),))

    dq_records = DataQualityStore(store_dir).query(run_id=_PROD_RUN_ID)
    failed_gates = tuple(r.category for r in dq_records
                         if r.category != "gate_overall" and r.status == "fail")
    overall = next((r.status for r in dq_records if r.category == "gate_overall"), "healthy")
    dq_ok = not failed_gates and overall not in _HARD_FAIL_STATUSES
    dq = CheckResult("dq_gate_pass", "pass" if dq_ok else "fail",
                     ("overall gate status {0!r}; {1}".format(
                         overall, "no gate failed" if not failed_gates
                         else "failed gates: " + ", ".join(failed_gates)),))

    try:
        published = publish_candidates_for_run(store_dir, _PROD_RUN_ID, now=now)
        forged = tuple(c for c in published if c.is_eligible and c.missing_lineage)
        cand_ok = not forged
        detail = "published {0} candidate(s); {1} eligible; 0 forged-eligible".format(
            len(published), sum(1 for c in published if c.is_eligible))
        if forged:
            detail = "FORGED eligible without provenance: " + ", ".join(
                c.candidate_id for c in forged)
    except Exception as exc:
        cand_ok = False
        detail = "publish path raised {0}: {1}".format(type(exc).__name__, str(exc)[:160])
    candidate = CheckResult("candidate_publication", "pass" if cand_ok else "fail", (detail,))
    return replay, dq, candidate


def _alert_safety(store_dir: str, now: str) -> CheckResult:
    """020E: NO external escalation is possible pre-activation + no forbidden action phrase."""
    from reality_mesh.alerts import Alert, FORBIDDEN_ALERT_PHRASES
    from reality_mesh.alert_delivery import (
        AlertDeliveryPolicy,
        AlertDeliveryStatus,
        EmailChannel,
        deliver_alert,
    )

    findings: List[str] = []
    policy = AlertDeliveryPolicy.default()
    if policy.production_activated:
        findings.append("policy.production_activated is True pre-activation (external delivery open)")

    alert = Alert(
        alert_id="ALERT-PRODCHECK-001", run_id=_PROD_RUN_ID, category="major_risk_emerged",
        severity="critical", human_readable_reason="observation for the 020F alert-safety probe",
        subject_tickers=("IREN",), evidence_refs=("finding.x",), created_at=now,
        dq_state="healthy")

    # An external channel under EVERY mode must be suppressed pre-activation (no escalation).
    for mode in ("OFF", "MANUAL", "SHADOW_24X7", "PRODUCTION_24X7"):
        decision = policy.decide(is_external=True, mode=mode, alert=alert)
        if decision == "allowed":
            findings.append("external delivery ALLOWED in {0} pre-activation".format(mode))
    if policy.decide(is_external=True, mode="PRODUCTION_24X7", alert=alert) != (
            AlertDeliveryStatus.SUPPRESSED_BY_POLICY):
        findings.append("production external delivery is not suppressed_by_policy pre-activation")

    # A real delivery attempt through an external channel must NOT deliver (persisted suppressed).
    with tempfile.TemporaryDirectory() as d:
        results = deliver_alert(
            alert, policy=policy, mode="PRODUCTION_24X7",
            channels=(EmailChannel(),), store_dir=d, now=now)
        for r in results:
            if r.status == AlertDeliveryStatus.DELIVERED:
                findings.append("an external alert was DELIVERED pre-activation")
            blob = " ".join((r.detail_sanitized,)).lower()
            for phrase in FORBIDDEN_ALERT_PHRASES:
                if phrase in blob:
                    findings.append("forbidden action phrase in delivery detail: " + phrase)

    status = "fail" if findings else "pass"
    return CheckResult("alert_safety_policy", status,
                       tuple(findings) or ("no external escalation possible pre-activation; "
                                           "no forbidden action phrase",))


def _mode_state_machine() -> CheckResult:
    """The service starts OFF; PRODUCTION_24X7 is never the default and stays 020F-gated."""
    findings: List[str] = []
    if ServiceConfig(store_dir="x").mode is not ServiceMode.OFF:
        findings.append("default service mode is not OFF")
    if not requires_activation_gate(ServiceMode.PRODUCTION_24X7):
        findings.append("PRODUCTION_24X7 is not activation-gated")
    if continuous_activation_gate(ServiceMode.PRODUCTION_24X7) != "Phase-020F":
        findings.append("PRODUCTION_24X7 gate is not Phase-020F")
    status = "fail" if findings else "pass"
    return CheckResult("mode_state_machine", status,
                       tuple(findings) or ("default OFF; PRODUCTION_24X7 gated to Phase-020F",))


def _no_auto_promotion() -> CheckResult:
    """Production is reachable ONLY from SHADOW_24X7 with explicit approval -- no auto/unapproved jump."""
    findings: List[str] = []
    # a direct OFF -> PRODUCTION jump must be refused
    if promote(ServiceMode.OFF, ServiceMode.PRODUCTION_24X7,
               report=None, operator_approval=None).allowed:
        findings.append("OFF -> PRODUCTION_24X7 was allowed (auto jump)")
    # SHADOW -> PRODUCTION with no report / no approval must be refused
    if promote(ServiceMode.SHADOW_24X7, ServiceMode.PRODUCTION_24X7,
               report=None, operator_approval=None).allowed:
        findings.append("SHADOW -> PRODUCTION with no report/approval was allowed")
    status = "fail" if findings else "pass"
    return CheckResult("no_auto_promotion", status,
                       tuple(findings) or ("no auto / unapproved promotion to PRODUCTION_24X7",))


# --------------------------------------------------------------------------- #
# 023G additive checks -- compose 022H / 023A / 023F (never re-implement them)   #
# --------------------------------------------------------------------------- #
def _recommendation_eligibility(
        rec_store: str, now: str, *,
        operator_approval: Optional[OperatorApproval] = None,
        extra_recommendation_checks: Optional[Mapping[str, object]] = None
        ) -> Tuple[CheckResult, "RecommendationActivationReport"]:
    """Run the 022H recommendation-activation gate OFFLINE and fold in its honest verdict.

    Composes :func:`run_recommendation_checks` (the REAL machine checks over the 022x layers) and
    :func:`evaluate_recommendation_activation` -- it re-implements NOTHING. The returned
    :class:`CheckResult` PASSES iff every machine-verifiable recommendation check passes (the honest
    machine posture); it does NOT claim the recommendation MODE is allowed -- that stays ``False``
    OFFLINE because ``live_source_health`` + ``operator_signoff`` remain manual + BLOCKING in the
    returned report. ``extra_recommendation_checks`` lets a caller inject / clear the manual items
    (used to prove the recommendation mode is reachable-only-with-complete-evidence).
    """
    try:
        machine = run_recommendation_checks(rec_store, now=now)
    except Exception as exc:      # any crash is a hard fail, surfaced not hidden
        empty = evaluate_recommendation_activation(rec_store, now=now)
        return (CheckResult("recommendation_eligibility", "fail",
                            ("recommendation checks raised {0}: {1}".format(
                                type(exc).__name__, str(exc)[:160]),)),
                empty)
    merged: Dict[str, object] = dict(machine)
    if extra_recommendation_checks:
        merged.update(dict(extra_recommendation_checks))
    report = evaluate_recommendation_activation(
        rec_store, now=now, operator_approval=operator_approval, checks=merged)
    machine_failures = tuple(name for name, r in machine.items()
                             if getattr(r, "status", "") == "fail")
    status = "fail" if machine_failures else "pass"
    detail = ("{0} machine recommendation check(s) pass; recommendation_mode_allowed={1}; "
              "verdict={2}; blocking={3}; manual={4}".format(
                  len(machine), report.recommendation_mode_allowed, report.verdict,
                  ", ".join(report.blocking_failures) or "none",
                  ", ".join(report.manual_review_items) or "none"))
    if machine_failures:
        detail = "machine recommendation checks FAILED: " + ", ".join(machine_failures)
    return CheckResult("recommendation_eligibility", status, (detail,)), report


def _deployment_config_valid() -> CheckResult:
    """023A: the deployment profiles are safe-by-default, self-consistent, production explicit-only.

    Composes :mod:`cosmosiq_ops.env_profiles` -- the default profile is safe
    (``production_allowed=False``), ``resolve_profile(None)`` never returns production, the
    ``production`` posture is reachable ONLY by its explicit name, and every profile satisfies the
    declared invariants (a blocked network draws only from an offline source; a production-declared
    profile carries the production service + recommendation modes and is never the default).
    """
    from cosmosiq_ops.env_profiles import (
        DEFAULT_PROFILE_ID,
        PROFILES,
        RecommendationMode,
        ServiceMode as _EnvServiceMode,
        default_profile,
        get_profile,
        resolve_profile,
    )
    _OFFLINE_SOURCES = frozenset({"fixture_only", "local_file"})
    findings: List[str] = []

    dp = default_profile()
    if dp.production_allowed:
        findings.append("default profile {0!r} declares production_allowed=True".format(
            dp.profile_id))
    resolved = resolve_profile(None)
    if resolved.production_allowed:
        findings.append("resolve_profile(None) returned a production-allowed profile")
    if resolved.profile_id != DEFAULT_PROFILE_ID:
        findings.append("resolve_profile(None) did not return the safe default {0!r}".format(
            DEFAULT_PROFILE_ID))

    try:
        prod = get_profile("production")
    except Exception as exc:                                        # noqa: BLE001
        prod = None
        findings.append("production profile not reachable by name: {0}".format(str(exc)[:120]))
    if prod is not None and not prod.production_allowed:
        findings.append("the explicit production profile is not production_allowed")

    for pid, prof in PROFILES.items():
        if prof.network_behavior == "blocked" and prof.source_behavior not in _OFFLINE_SOURCES:
            findings.append("profile {0!r}: blocked network with non-offline source {1!r}".format(
                pid, prof.source_behavior))
        if prof.production_allowed:
            if prof.service_mode != _EnvServiceMode.PRODUCTION_24X7.value:
                findings.append("profile {0!r}: production_allowed but service_mode {1!r}".format(
                    pid, prof.service_mode))
            if prof.recommendation_mode != RecommendationMode.PRODUCTION_MANUAL_REVIEW:
                findings.append(
                    "profile {0!r}: production_allowed but recommendation_mode {1!r}".format(
                        pid, prof.recommendation_mode))
            if pid == DEFAULT_PROFILE_ID:
                findings.append("the default profile {0!r} declares production_allowed=True".format(
                    pid))

    status = "fail" if findings else "pass"
    return CheckResult(
        "deployment_config_valid", status,
        tuple(findings) or ("default profile {0!r} safe (production_allowed=False); production "
                            "reachable explicit-only; {1} profile(s) self-consistent".format(
                                DEFAULT_PROFILE_ID, len(PROFILES)),))


def _backup_restore_smoke(work_dir: str, now: str) -> CheckResult:
    """023F: seed a scratch store, back it up, restore into an EMPTY target, re-prove it.

    Composes :mod:`cosmosiq_ops.backup_ops` end to end: a hardened backup of a freshly seeded store
    (sha256 manifest + verify), then a restore into an empty target that re-runs integrity + a
    deterministic replay-after-restore. PASSES only when the backup verifies AND the restore is
    allowed, verifies, is schema-compatible, and passes integrity + replay. Everything OFFLINE; the
    scratch trees live under ``work_dir`` (the caller's fresh work dir).
    """
    from cosmosiq_ops import backup_ops
    from reality_mesh import persist_and_summarize, run_pulse

    smoke_root = os.path.join(str(work_dir), "backup_smoke")
    src_store = os.path.join(smoke_root, "store")
    backup_dir = os.path.join(smoke_root, "backups")
    target = os.path.join(smoke_root, "restored")
    os.makedirs(src_store, exist_ok=True)
    try:
        pulse = run_pulse(list(_PROD_WATCHLIST), list(_PROD_THEMES), now=now)
        persist_and_summarize(pulse, store_dir=src_store, run_id="RUN-BACKUP-SMOKE", now=now)
        backup = backup_ops.backup(src_store, backup_dir, now=now)
        restore = backup_ops.restore(backup.snapshot_path, target, now=now)
    except Exception as exc:      # any crash is a hard fail, surfaced not hidden
        return CheckResult("backup_restore_smoke", "fail",
                           ("backup/restore smoke raised {0}: {1}".format(
                               type(exc).__name__, str(exc)[:160]),))
    ok = (backup.verify_ok and backup.ok
          and restore.allowed and restore.verify_ok and restore.schema_compatible
          and restore.integrity_ok and restore.replay_ok and restore.ok)
    detail = ("backup {0} (verify={1}); restore {2} (verify={3}, integrity={4}, "
              "replay={5}) into empty target".format(
                  backup.status, backup.verify_ok, restore.status, restore.verify_ok,
                  restore.integrity_ok, restore.replay_ok))
    return CheckResult("backup_restore_smoke", "pass" if ok else "fail", (detail,))


def _rollback_docs(repo_root: str) -> CheckResult:
    """The 020F operator runbook + activation-checklist docs exist under the repo."""
    required = ("docs/OPERATOR_RUNBOOK_020F.md", "docs/ACTIVATION_CHECKLIST_020F.md")
    missing = tuple(rel for rel in required
                    if not os.path.isfile(os.path.join(repo_root, rel.replace("/", os.sep))))
    status = "fail" if missing else "pass"
    return CheckResult("rollback_docs", status,
                       tuple("missing doc: " + m for m in missing)
                       or ("both 020F docs present: " + ", ".join(required),))


# --------------------------------------------------------------------------- #
# The gate                                                                      #
# --------------------------------------------------------------------------- #
def run_prod_check(work_dir: str, repo_root: str, *, now: str, quick: bool = False,
                   operator_approval: Optional[OperatorApproval] = None,
                   extra_checks: Optional[Mapping[str, CheckResult]] = None,
                   extra_recommendation_checks: Optional[Mapping[str, object]] = None
                   ) -> ProdCheckReport:
    """Run every machine-verifiable activation check OFFLINE and fold them into the 020F checklist.

    ``now`` is injected everywhere (no wall clock in the runtime chain). ``quick`` skips the
    CI-gate's full-suite subprocess run but keeps every sweep. ``operator_approval`` is passed to
    BOTH the 020F activation evaluation and the 022H recommendation-activation evaluation; without
    it (and without the manual items) neither production nor the recommendation mode is allowed.
    ``extra_checks`` lets a caller inject / override the 020F machine results (used to prove an
    injected violation blocks); ``extra_recommendation_checks`` does the same for the 022H
    recommendation gate (used to prove the recommendation mode is reachable-only-with-complete-
    evidence). Returns the frozen report; NEITHER production NOR the recommendation mode is allowed
    unless every gate -- including the human manual items -- is satisfied AND approved.
    """
    if not str(now).strip():
        raise ValueError("run_prod_check requires an injected 'now' instant")
    store_dir = os.path.join(str(work_dir), "store")
    os.makedirs(store_dir, exist_ok=True)

    checks: List[CheckResult] = []

    # 1. the 019A CI gate (full suite + every guardrail sweep). --------------------------------- #
    ci = run_ci_gate(repo_root, quick=quick)
    checks.append(CheckResult(
        "suite_or_ci_gate", "pass" if ci.passed else "fail",
        ("CI gate {0}: {1} checks, {2} failed".format(
            "PASS" if ci.passed else "FAIL", len(ci.checks), ci.checks_failed),)
        + tuple("gate check failed: " + c.name for c in ci.checks if c.status == "fail")))

    # 2. mode configuration. -------------------------------------------------------------------- #
    checks.append(_mode_state_machine())
    checks.append(_no_auto_promotion())

    # 3. source configuration (offline SEC dry-run). -------------------------------------------- #
    checks.append(_sec_adapter_offline_smoke(now))

    # 4. scheduler + service. ------------------------------------------------------------------- #
    checks.append(_scheduler_dry_run(now))
    checks.append(_service_wrapper_health(store_dir, now))

    # 5-7. persistence/replay, DQ, candidate eligibility (seeded run). -------------------------- #
    replay, dq, candidate = _replay_and_dq(store_dir, now)
    checks.extend((replay, dq, candidate))

    # 8. alert safety. -------------------------------------------------------------------------- #
    checks.append(_alert_safety(store_dir, now))

    # 9. UI/operator surfaces + security. ------------------------------------------------------- #
    checks.append(_scan_no_trade_control(repo_root, now))
    checks.append(check_no_score_rank_functions(repo_root))          # -> no_hidden_score below
    checks.append(_scan_fixture_leakage(repo_root, now))
    checks.append(_demo_byte_identical())
    checks.append(_scan_secrets(repo_root, now))

    # 10. runbook/rollback docs. ---------------------------------------------------------------- #
    checks.append(_rollback_docs(repo_root))

    # 11. 023G additive checks -- compose 022H / 023A / 023F; each an offline machine check. ----- #
    #     They enrich the checklist but NEVER weaken the 020F gate: their ids are not 020F item
    #     ids, so evaluate_activation (which iterates the fixed 020F specs) ignores them.
    rec_store = os.path.join(str(work_dir), "rec_store")
    os.makedirs(rec_store, exist_ok=True)
    rec_check, recommendation = _recommendation_eligibility(
        rec_store, now, operator_approval=operator_approval,
        extra_recommendation_checks=extra_recommendation_checks)
    checks.append(rec_check)
    checks.append(_deployment_config_valid())
    checks.append(_backup_restore_smoke(work_dir, now))

    # Map machine results to checklist item ids (ci_gate's score check id -> no_hidden_score).
    by_id: Dict[str, CheckResult] = {}
    for c in checks:
        item_id = "no_hidden_score" if c.name == "no_score_rank_functions" else c.name
        by_id[item_id] = CheckResult(item_id, c.status, c.details)
    if extra_checks:
        for item_id, result in extra_checks.items():
            by_id[item_id] = result

    activation = evaluate_activation(
        store_dir, now=now, operator_approval=operator_approval, checks=by_id)
    return ProdCheckReport(
        work_dir=str(work_dir), repo_root=str(repo_root),
        checks=tuple(checks), activation=activation, recommendation=recommendation)


def _demo_byte_identical() -> CheckResult:
    """Wrap the ci_gate demo-byte-identical check under the 020F item id."""
    result = check_demo_build_byte_identical()
    return CheckResult("demo_byte_identical", result.status, result.details)


def format_prod_check_report(report: ProdCheckReport) -> str:
    """Human-readable render: the verdict, the checklist state, and the honest blocking reasons."""
    allowed = report.production_mode_allowed
    lines = [
        "CosmosIQ production activation check (Phase 020F) -- {0}".format(
            "PRODUCTION ALLOWED" if allowed else "PRODUCTION NOT ALLOWED"),
        "repo: {0}".format(report.repo_root),
        "work dir: {0}".format(report.work_dir),
        "production_mode_allowed = {0}".format(str(allowed).lower()),
        "recommendation_mode_allowed = {0}".format(
            str(report.recommendation_mode_allowed).lower()),
        "verdict: {0}".format(report.verdict),
        "recommendation_verdict: {0}".format(report.recommendation_verdict),
    ]
    act = report.activation
    if act is not None:
        lines.append("checklist ({0} items across 11 sections):".format(len(act.items)))
        section = ""
        for item in act.items:
            if item.section != section:
                section = item.section
                lines.append("  [{0}]".format(section))
            lines.append("    [{0:^22}] {1} -- {2}".format(
                item.status, item.id, item.description))
            if item.notes:
                lines.append("        note: " + item.notes)
    lines.append("blocking_failures: {0}".format(
        ", ".join(report.blocking_failures) or "none"))
    lines.append("manual_review_items: {0}".format(
        ", ".join(report.manual_review_items) or "none"))
    lines.append("recommendation_blocking_failures: {0}".format(
        ", ".join(report.recommendation_blocking_failures) or "none"))
    lines.append("recommendation_manual_review_items: {0}".format(
        ", ".join(report.recommendation_manual_review_items) or "none"))
    lines.append("evidence_paths: {0}".format(", ".join(report.evidence_paths) or "none"))
    if not allowed:
        lines.append(
            "REFUSED: production 24x7 cannot be enabled. This is the correct, safe default -- the "
            "live-source-health fetch, the operator shadow-validation, and the explicit human "
            "sign-off cannot be machine-verified OFFLINE and remain BLOCKING. Land at shadow 24x7.")
    return "\n".join(lines)
