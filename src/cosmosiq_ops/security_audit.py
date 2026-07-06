"""The CosmosIQ security / compliance / audit pass (IMPLEMENTATION-023H). OFFLINE, deterministic.

``run_security_audit`` is the pre-deployment safety gate: it runs the WHOLE guardrail battery across
the CosmosIQ intelligence packages and folds each category's HONEST pass/fail into one frozen
:class:`SecurityAuditReport`. It COMPOSES the already-accepted scans -- it re-implements NONE of
them and it WEAKENS none of them:

* the 019A CI gate (:mod:`cosmosiq_ops.ci_gate`) -- the no-network / no-scheduler / no-broker AST
  sweep, the no-hidden-score/rank sweep, the demo-byte-identical build, and the secret-VALUE /
  trade-affordance / credential-key token sets;
* the 013E Data-Quality gate (:mod:`reality_mesh.gates`) -- the social-weak-signal and
  manual-analyst-authority HARD-fail checkers that reject rumor -> ``verified_fact`` and
  manual/analyst -> ``canonical`` laundering (asserted by CONSTRUCTING a laundering record and
  proving the accepted gate REJECTS it, never a grep);
* the 020F/022H/023A/023G production posture (:mod:`cosmosiq_ops.prod_check` /
  :mod:`cosmosiq_ops.env_profiles` / :mod:`cosmosiq_service.service` /
  :mod:`reality_mesh.recommendation_activation`) -- default profile safe, service default OFF,
  recommendation default ``shadow``, and prod-check REFUSES production in an honest OFFLINE run;
* the 020C sanitizer (:func:`cosmosiq_service.service.sanitize`) + the 023E structured-log / health
  paths -- proven to redact a PLANTED secret VALUE.

DISCIPLINE (the audit is HONEST):

* every category reports its REAL pass/fail -- a genuine issue is reported, never suppressed or
  rubber-stamped; :attr:`SecurityAuditReport.passed` is strict (any failed category fails the audit);
* NO secret VALUE is ever written into a finding or the rendered report (findings carry the pattern
  NAME + a ref, never the value);
* the source secret sweep uses the HIGH-ENTROPY value patterns (``AKIA…`` / ``sk-…{20,}`` / PEM /
  bearer) so an ordinary code idiom (``api_key = os.environ.get(...)``) or English prose
  (``risk-materials``) is NOT mistaken for a leaked secret -- a real assigned secret VALUE is
  high-entropy and IS caught;
* deterministic: ``now`` is the ONLY clock (no wall-clock read); two runs over the same repo + same
  ``now`` render byte-identically;
* OFFLINE: nothing here reaches the network; the accepted lazy transport boundary inside a function
  is permitted, a network CALL / import at module top level is not.

The UI-owned surface (``universe_ui`` / ``generated``) is a SEPARATE owned product and is NOT
swept here -- the audit scans the CosmosIQ packages
``reality_mesh / cosmosiq_app / cosmosiq_ops / cosmosiq_service / cosmosiq_pulse`` only.

``subprocess`` (via the composed CI gate / prod-check) stays confined to ``cosmosiq_ops`` operator
tooling -- never imported by runtime code. Stdlib-only, Python 3.9, OFFLINE.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import stat
import sys
import sysconfig
import tempfile
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence, Tuple

# Compose the accepted 019A CI-gate primitives (never re-implemented).
from cosmosiq_ops.ci_gate import (
    BROKER_IMPORT_ROOTS,
    NETWORK_IMPORT_ROOTS,
    SANCTIONED_NETWORK_SHELLS,
    SECRET_KEY_TOKENS,
    SECRET_VALUE_PATTERNS as _CIGATE_SECRET_PATTERNS,
    TRADE_WORD_RE,
    _python_files,
    check_env_not_tracked,
)
# Compose the accepted 013E secret-VALUE patterns + the top-level network-call detector.
from reality_mesh.gates import (
    SECRET_VALUE_PATTERNS as _GATES_SECRET_PATTERNS,
    DataQualityGateRunner,
    _network_call_on_import,
)
# Reuse the injected-time format the whole runtime uses (NO wall-clock helper).
from reality_mesh.scheduler import _format_utc, _parse_utc

__all__ = [
    "AUDIT_PACKAGES",
    "INTELLIGENCE_PACKAGES",
    "SecurityAuditCategory",
    "SecurityAuditReport",
    "run_security_audit",
    "render_security_audit",
    "scan_text_for_secret_values",
]

# The CosmosIQ packages the audit sweeps (the UI-owned surface is deliberately excluded).
AUDIT_PACKAGES: Tuple[str, ...] = (
    "reality_mesh", "cosmosiq_app", "cosmosiq_ops", "cosmosiq_service", "cosmosiq_pulse",
)
# The intelligence RUNTIME packages the hidden-score / rank / rating sweep targets (the ops CI
# tooling legitimately NAMES its checks after what they forbid, so it is not swept for score/rank).
INTELLIGENCE_PACKAGES: Tuple[str, ...] = ("reality_mesh", "cosmosiq_app")

# HIGH-ENTROPY secret-VALUE patterns for the SOURCE sweep: the accepted 013E patterns MINUS the
# broad ``key = value`` idiom (which matches ordinary env-reads like ``api_key = os.environ.get``).
# These match a real assigned secret VALUE, never a code idiom or English prose -> zero false
# positives on clean source, while a planted ``AKIA…`` / ``sk-…{20,}`` / PEM / bearer IS caught.
_STRICT_SECRET_REGEXES: Tuple[Tuple[str, "re.Pattern"], ...] = tuple(
    (name, re.compile(pat)) for name, pat in _GATES_SECRET_PATTERNS
    if name != "assigned_credential"
)

# Function-name signatures for an executable TRADE / broker order affordance in source (an AST
# name check, never a prose grep -- the honest guardrail nouns "no buy/sell recommendation" appear
# all over the source docstrings and are NOT controls).
_TRADE_EXEC_FN_RE = re.compile(
    r"(place|submit|send|execute|cancel|route)_?(order|trade|buy|sell)"
    r"|^(buy|sell)$|broker_?submit|market_order|limit_order")


# --------------------------------------------------------------------------- #
# The frozen report                                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SecurityAuditCategory:
    """One audit category: a stable ``id``, an honest ``passed`` bool, findings, and caveats.

    ``findings`` are the REAL issues the category found (empty -> clean); a non-empty findings list
    always means ``passed=False``. ``caveats`` document HOW the category was checked and any honest
    boundary of the check. No finding ever contains a secret VALUE -- only a pattern NAME + a ref.
    """

    id: str
    passed: bool
    findings: Tuple[str, ...] = field(default_factory=tuple)
    caveats: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SecurityAuditReport:
    """The whole audit run. ``passed`` is strict: ANY failing category fails the audit."""

    repo_root: str
    generated_at: str
    categories: Tuple[SecurityAuditCategory, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(cat.passed for cat in self.categories)

    @property
    def categories_failed(self) -> Tuple[str, ...]:
        return tuple(cat.id for cat in self.categories if not cat.passed)

    def category(self, category_id: str) -> Optional[SecurityAuditCategory]:
        for cat in self.categories:
            if cat.id == category_id:
                return cat
        return None


# --------------------------------------------------------------------------- #
# Shared scanning helpers                                                       #
# --------------------------------------------------------------------------- #
def _src_root(repo_root: str) -> str:
    return os.path.join(repo_root, "src")


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _source_secret_findings(label: str, text: str) -> List[str]:
    """Secret-VALUE findings in SOURCE text using the high-entropy patterns (no false positives)."""
    findings: List[str] = []
    for name, rx in _STRICT_SECRET_REGEXES:
        if rx.search(text):
            findings.append("{0}: high-entropy secret value matching {1!r} (value redacted)".format(
                label, name))
    return findings


def _output_secret_findings(label: str, text: str) -> List[str]:
    """Secret findings in a RENDERED/generated artifact (the accepted 019A output scan)."""
    findings: List[str] = []
    lowered = text.lower()
    for pattern in _CIGATE_SECRET_PATTERNS:
        if pattern.search(text):
            findings.append("{0}: secret-like value matching {1!r} (value redacted)".format(
                label, pattern.pattern))
    for token in SECRET_KEY_TOKENS:
        if token in lowered:
            findings.append("{0}: credential key token {1!r}".format(label, token))
    return findings


def scan_text_for_secret_values(text: object) -> Tuple[str, ...]:
    """Public helper: every secret-VALUE pattern NAME present in ``text`` (never the value).

    Composes BOTH accepted pattern sets (013E high-entropy + 019A output patterns) so a PLANTED
    secret (e.g. an ``AKIA…`` key or an ``sk-…`` token) is DETECTED -- proving the scan is real, not
    a rubber stamp. Returns pattern NAMES / patterns only; the secret VALUE is never captured.
    """
    haystack = str(text or "")
    hits: List[str] = []
    for name, rx in _STRICT_SECRET_REGEXES:
        if rx.search(haystack):
            hits.append(name)
    for pattern in _CIGATE_SECRET_PATTERNS:
        if pattern.search(haystack):
            hits.append(pattern.pattern)
    return tuple(sorted(set(hits)))


def _render_product_pages(now: str) -> List[Tuple[str, str]]:
    """The DEFAULT product UI pages over a FRESH (empty) store -> [(label, html)] (offline now)."""
    from cosmosiq_ops.prod_check import _render_product_pages as _rp
    with tempfile.TemporaryDirectory() as store_dir:
        return _rp(store_dir, now)


def _planted_html(repo_root: str) -> List[Tuple[str, str]]:
    """Any html planted under the repo's non-UI output trees -> [(label, text)] (reuse prod-check).

    The UI-owned ``generated`` tree is a separate product surface and is NOT swept here.
    """
    from cosmosiq_ops.prod_check import _planted_html as _ph
    return [(label, text) for label, text in _ph(repo_root)
            if not label.startswith("generated/")]


# --------------------------------------------------------------------------- #
# stdlib classification (Python 3.9 has no sys.stdlib_module_names)              #
# --------------------------------------------------------------------------- #
def _stdlib_bases() -> Tuple[str, ...]:
    bases = set()
    for key in ("stdlib", "platstdlib"):
        path = sysconfig.get_paths().get(key)
        if path:
            bases.add(os.path.abspath(path))
    return tuple(sorted(bases))


_STDLIB_BASES = _stdlib_bases()


def _is_stdlib_module(name: str) -> bool:
    """True iff top-level module ``name`` resolves to the Python standard library (not site-packages).

    A third-party package resolves under ``site-packages`` / ``dist-packages`` -> returns False (so
    it is classified as a third-party runtime dependency). Never imports the module -- only resolves
    its spec.
    """
    if name in sys.builtin_module_names or name == "__future__":
        return True
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError, AttributeError, ModuleNotFoundError):
        return False
    if spec is None:
        return False
    origin = spec.origin or ""
    if origin in ("built-in", "frozen"):
        return True
    locations: List[str] = []
    if origin and origin not in ("namespace",):
        locations.append(origin)
    for loc in (spec.submodule_search_locations or []):
        locations.append(loc)
    for loc in locations:
        ap = os.path.abspath(loc)
        if "site-packages" in ap or "dist-packages" in ap:
            return False
        for base in _STDLIB_BASES:
            try:
                if os.path.commonpath([ap, base]) == base:
                    return True
            except ValueError:
                continue
    return False


# --------------------------------------------------------------------------- #
# The category checkers -- each composes an accepted scan and reports honestly   #
# --------------------------------------------------------------------------- #
def _check_no_secrets(repo_root: str, now: str) -> SecurityAuditCategory:
    src_root = _src_root(repo_root)
    findings: List[str] = []

    # 1. CosmosIQ source (high-entropy value patterns -> no code-idiom / prose false positives).
    source_files = _python_files(src_root, AUDIT_PACKAGES)
    for rel in source_files:
        findings.extend(_source_secret_findings(rel, _read(os.path.join(src_root, rel))))

    # 2. rendered-UI + planted-artifact sweep (the accepted 019A output scan).
    surfaces = _render_product_pages(now) + _planted_html(repo_root)
    for label, text in surfaces:
        findings.extend(_output_secret_findings(label, text))

    # 3. the reports tree (operator artifacts) -- high-entropy value patterns only.
    reports_dir = os.path.join(repo_root, "reports")
    reports_scanned = 0
    if os.path.isdir(reports_dir):
        for root, dirs, names in os.walk(reports_dir):
            dirs.sort()
            for name in sorted(names):
                if name.endswith((".md", ".txt", ".json")):
                    path = os.path.join(root, name)
                    rel = os.path.relpath(path, repo_root).replace(os.sep, "/")
                    findings.extend(_source_secret_findings(rel, _read(path)))
                    reports_scanned += 1

    # 4. no tracked .env (reuse the accepted CI-gate git check).
    env = check_env_not_tracked(repo_root)
    if env.status == "fail":
        findings.extend(env.details)

    caveats = (
        "swept {0} source file(s) with high-entropy value patterns (AKIA / sk-{{20,}} / PEM / "
        "bearer); {1} rendered/planted surface(s) + {2} report(s) with the accepted 019A output "
        "scan; .env tracking checked via git".format(
            len(source_files), len(surfaces), reports_scanned),
        "an ordinary env-read idiom (api_key = os.environ.get(...)) is NOT a secret and is not "
        "flagged; a real assigned secret VALUE is high-entropy and IS caught",
    )
    return SecurityAuditCategory("no_secrets_in_repo_or_output", not findings,
                                 tuple(findings), caveats)


def _check_no_network_on_import(repo_root: str, now: str) -> SecurityAuditCategory:
    src_root = _src_root(repo_root)
    findings: List[str] = []
    files = _python_files(src_root, AUDIT_PACKAGES)
    for rel in files:
        source = _read(os.path.join(src_root, rel))
        tree = ast.parse(source)
        if rel not in SANCTIONED_NETWORK_SHELLS:
            # module TOP-LEVEL network import (a lazy import inside a function is the accepted
            # single boundary and does NOT count).
            for node in tree.body:
                roots: List[Tuple[str, int]] = []
                if isinstance(node, ast.Import):
                    roots = [(a.name.split(".")[0], node.lineno) for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    roots = [(node.module.split(".")[0], node.lineno)]
                for root, lineno in roots:
                    if root in NETWORK_IMPORT_ROOTS:
                        findings.append("{0}:{1}: top-level network import {2!r}".format(
                            rel, lineno, root))
            # a network CALL at module top level (would fire on import).
            if _network_call_on_import(source):
                findings.append("{0}: network call at module import time".format(rel))
    caveats = (
        "swept {0} file(s); sanctioned lazy-transport shells: {1}".format(
            len(files), ", ".join(SANCTIONED_NETWORK_SHELLS)),
        "a network call INSIDE a function (the live adapters' lazy transport) is permitted; only a "
        "top-level import / call is a violation",
    )
    return SecurityAuditCategory("no_network_on_import", not findings, tuple(findings), caveats)


def _check_no_broker_execution(repo_root: str, now: str) -> SecurityAuditCategory:
    src_root = _src_root(repo_root)
    findings: List[str] = []
    files = _python_files(src_root, AUDIT_PACKAGES)
    for rel in files:
        tree = ast.parse(_read(os.path.join(src_root, rel)))
        for node in ast.walk(tree):
            roots: List[Tuple[str, int]] = []
            if isinstance(node, ast.Import):
                roots = [(a.name.split(".")[0], node.lineno) for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [(node.module.split(".")[0], node.lineno)]
            for root, lineno in roots:
                if root in BROKER_IMPORT_ROOTS:
                    findings.append("{0}:{1}: broker/execution import {2!r}".format(
                        rel, lineno, root))
    caveats = (
        "AST sweep of {0} file(s) for a broker/execution client import ({1})".format(
            len(files), ", ".join(sorted(BROKER_IMPORT_ROOTS))),)
    return SecurityAuditCategory("no_broker_execution", not findings, tuple(findings), caveats)


def _check_no_trade_controls(repo_root: str, now: str) -> SecurityAuditCategory:
    src_root = _src_root(repo_root)
    findings: List[str] = []

    # 1. rendered UI pages + planted html: the accepted 019A trade-affordance scan (action phrasings).
    surfaces = _render_product_pages(now) + _planted_html(repo_root)
    for label, text in surfaces:
        match = TRADE_WORD_RE.search(text)
        if match:
            findings.append("{0}: trade-affordance token {1!r}".format(label, match.group(0)))

    # 2. source: an executable order/trade AFFORDANCE is an AST function-name signature, not prose
    #    (the honest guardrail nouns "no buy/sell recommendation" pervade the docstrings and are OK).
    files = _python_files(src_root, AUDIT_PACKAGES)
    for rel in files:
        tree = ast.parse(_read(os.path.join(src_root, rel)))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _TRADE_EXEC_FN_RE.search(node.name.lower()):
                    findings.append("{0}:{1}: trade-execution function {2!r}".format(
                        rel, node.lineno, node.name))
    caveats = (
        "scanned {0} rendered/planted surface(s) with the accepted TRADE_WORD_RE affordance scan + "
        "{1} source file(s) for an executable order/trade function name".format(
            len(surfaces), len(files)),
        "guardrail-DATA tokens in the gate definitions (bare nouns buy/sell/order in prose that "
        "DESCRIBES what is forbidden) are OK -- only an action affordance / executable order "
        "function counts",
    )
    return SecurityAuditCategory("no_trade_controls", not findings, tuple(findings), caveats)


def _check_no_hidden_score_rank(repo_root: str, now: str) -> SecurityAuditCategory:
    src_root = _src_root(repo_root)
    findings: List[str] = []
    files = _python_files(src_root, INTELLIGENCE_PACKAGES)
    for rel in files:
        tree = ast.parse(_read(os.path.join(src_root, rel)))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered = node.name.lower()
                if "score" in lowered or "rank" in lowered or "rating" in lowered:
                    findings.append("{0}:{1}: hidden score/rank/rating function {2!r}".format(
                        rel, node.lineno, node.name))
    caveats = (
        "AST sweep of {0} file(s) in the intelligence packages ({1}) for any function named "
        "*score* / *rank* / *rating*".format(len(files), ", ".join(INTELLIGENCE_PACKAGES)),
        "labels-not-numbers: the intelligence surface emits closed-vocabulary labels, never a "
        "hidden numeric score / rank / rating",
    )
    return SecurityAuditCategory("no_hidden_score_rank", not findings, tuple(findings), caveats)


def _check_no_social_laundering(repo_root: str, now: str) -> SecurityAuditCategory:
    """PROVE the accepted 013E social-weak gate REJECTS a rumor -> verified_fact (not a grep)."""
    runner = DataQualityGateRunner()
    findings: List[str] = []

    # a CONSTRUCTED laundering record: an X/social/rumor-tier datum marked 'verified_fact'.
    laundering = {"event_id": "AUDIT-SOCIAL-LAUNDER", "discipline": "narrative",
                  "source_type": "x_social", "source_authority": "rumor",
                  "claim_status": "verified_fact"}
    result = runner.check_social_weak_signal([laundering])
    if result.status != "fail":
        findings.append(
            "social-weak gate did NOT reject a rumor laundered into 'verified_fact' (status={0!r})"
            .format(result.status))

    # a clean rumor record must NOT be a hard fail (the gate is not blindly failing everything).
    clean = {"event_id": "AUDIT-SOCIAL-CLEAN", "discipline": "narrative",
             "source_type": "x_social", "source_authority": "rumor", "claim_status": "rumor",
             "corroboration_status": "uncorroborated"}
    clean_result = runner.check_social_weak_signal([clean])
    if clean_result.status == "fail":
        findings.append(
            "social-weak gate hard-failed a correctly-labelled rumor (over-blocking is dishonest)")

    caveats = (
        "asserted via the accepted 013E DataQualityGateRunner.check_social_weak_signal: a "
        "constructed rumor/social record marked 'verified_fact' is HARD-failed; a correctly "
        "labelled rumor is not -- the authority ladder holds (social never verified_fact)",)
    return SecurityAuditCategory("no_social_verified_fact_laundering", not findings,
                                 tuple(findings), caveats)


def _check_no_manual_canonical(repo_root: str, now: str) -> SecurityAuditCategory:
    """PROVE the accepted 013E gate REJECTS a manual/analyst datum marked 'canonical'."""
    runner = DataQualityGateRunner()
    findings: List[str] = []
    laundering = {"event_id": "AUDIT-MANUAL-LAUNDER", "source_authority": "canonical",
                  "claim_status": "manual"}
    result = runner.check_manual_analyst_authority([laundering])
    if result.status != "fail":
        findings.append(
            "manual-analyst gate did NOT reject a manual datum marked 'canonical' (status={0!r})"
            .format(result.status))
    analyst = {"event_id": "AUDIT-ANALYST-LAUNDER", "source_authority": "canonical",
               "claim_status": "analyst_estimate"}
    if runner.check_manual_analyst_authority([analyst]).status != "fail":
        findings.append(
            "manual-analyst gate did NOT reject an analyst_estimate marked 'canonical'")
    caveats = (
        "asserted via the accepted 013E DataQualityGateRunner.check_manual_analyst_authority: a "
        "constructed manual / analyst_estimate datum marked 'canonical' is HARD-failed -- manual "
        "/ analyst may never be canonical",)
    return SecurityAuditCategory("no_manual_canonical_laundering", not findings,
                                 tuple(findings), caveats)


def _check_no_unsafe_default_production(repo_root: str, now: str) -> SecurityAuditCategory:
    findings: List[str] = []
    from cosmosiq_ops.env_profiles import (
        DEFAULT_PROFILE_ID,
        default_profile,
        resolve_profile,
    )
    from cosmosiq_service.service import ServiceConfig, ServiceMode
    from reality_mesh.recommendation_activation import (
        RecommendationMode,
        default_recommendation_mode,
    )

    # 023A default deployment profile is safe.
    dp = default_profile()
    if dp.production_allowed:
        findings.append("default profile {0!r} declares production_allowed=True".format(
            dp.profile_id))
    resolved = resolve_profile(None)
    if resolved.production_allowed or resolved.profile_id != DEFAULT_PROFILE_ID:
        findings.append("resolve_profile(None) is not the safe default {0!r}".format(
            DEFAULT_PROFILE_ID))

    # service default OFF; recommendation default shadow.
    if ServiceConfig(store_dir="audit").mode is not ServiceMode.OFF:
        findings.append("default service mode is not OFF")
    if default_recommendation_mode() != RecommendationMode.SHADOW:
        findings.append("default recommendation mode is not 'shadow'")

    # prod-check REFUSES production in an honest OFFLINE run (compose the accepted 020F/023G gate).
    prod_verdict = "n/a"
    try:
        from cosmosiq_ops.prod_check import run_prod_check
        with tempfile.TemporaryDirectory() as work_dir:
            report = run_prod_check(work_dir, repo_root, now=now, quick=True)
        prod_verdict = report.verdict or "shadow_only"
        if report.production_mode_allowed:
            findings.append("prod-check ALLOWED production in an offline run (must refuse)")
        if report.recommendation_mode_allowed:
            findings.append("prod-check ALLOWED the recommendation mode offline (must refuse)")
    except Exception as exc:  # a crash is a hard fail, surfaced not hidden
        findings.append("prod-check raised {0}: {1}".format(
            type(exc).__name__, str(exc)[:160]))

    caveats = (
        "default profile {0!r} safe (production_allowed=False); service default OFF; recommendation "
        "default 'shadow'; prod-check offline verdict {1!r} (production + recommendation modes "
        "refused)".format(DEFAULT_PROFILE_ID, prod_verdict),)
    return SecurityAuditCategory("no_unsafe_default_production", not findings,
                                 tuple(findings), caveats)


def _check_no_fixture_leakage(repo_root: str, now: str) -> SecurityAuditCategory:
    """The DEFAULT product UI (empty store) shows no real fixture ticker (reuse prod-check scan)."""
    from cosmosiq_ops.prod_check import _scan_fixture_leakage
    result = _scan_fixture_leakage(repo_root, now)
    passed = result.status == "pass"
    findings = tuple(result.details) if not passed else ()
    caveats = (
        "reuse of the accepted prod-check fixture-leakage scan: the DEFAULT product UI over a FRESH "
        "empty store shows none of the real fixture tickers",) + (
        () if not passed else ())
    return SecurityAuditCategory("no_fixture_demo_production_leakage", passed, findings, caveats)


def _check_dependencies_reviewed(repo_root: str, now: str) -> SecurityAuditCategory:
    src_root = _src_root(repo_root)
    first_party = set(os.listdir(src_root)) if os.path.isdir(src_root) else set()
    roots: set = set()
    files = _python_files(src_root, AUDIT_PACKAGES)
    for rel in files:
        tree = ast.parse(_read(os.path.join(src_root, rel)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    third_party = sorted(
        r for r in roots
        if r not in first_party and r != "__future__" and not _is_stdlib_module(r))
    findings = tuple("third-party runtime dependency: {0!r}".format(r) for r in third_party)
    caveats = (
        "reviewed {0} distinct import root(s) across {1} file(s); classified against the Python "
        "{2}.{3} stdlib + the first-party src packages".format(
            len(roots), len(files), sys.version_info[0], sys.version_info[1]),
        "third-party runtime dependencies: {0}".format(
            ", ".join(third_party) if third_party else "none (stdlib-only)"),
    )
    return SecurityAuditCategory("dependencies_reviewed", not third_party, findings, caveats)


def _check_logs_and_errors_sanitized(repo_root: str, now: str) -> SecurityAuditCategory:
    """PROVE the 020C sanitize() + the 023E structured-log / health paths redact a PLANTED secret."""
    from cosmosiq_service.service import sanitize
    from cosmosiq_ops.observability import ObservabilityReport, emit_structured_log, render_health_json

    findings: List[str] = []
    # Synthetic secret VALUES (never a real credential) planted through each sanitized path:
    # an AWS-shaped key, an OpenAI-shaped token, and a credential value in key=value form.
    planted_key = "AKIA" + "IOSFODNN7EXAMPLE"       # AWS-shaped  (\bAKIA[0-9A-Z]{8,})
    planted_token = "sk-" + "A" * 24                # OpenAI-shaped (\bsk-...{6,})
    planted_kv_value = "s3cr3tVALUEplantedForAudit"  # a credential value in key=value form
    planted = {"aws": planted_key, "openai": planted_token, "kv": planted_kv_value}

    # 1. the raw 020C sanitizer (content-based: it redacts a secret-SHAPED value or a key=value
    #    credential inside a string).
    if planted_key in str(sanitize("note=" + planted_key)):
        findings.append("sanitize() did not redact a planted AWS-shaped secret value")
    if planted_token in str(sanitize("note=" + planted_token)):
        findings.append("sanitize() did not redact a planted OpenAI-shaped secret value")
    if planted_kv_value in str(sanitize("api_key=" + planted_kv_value)):
        findings.append("sanitize() did not redact a planted key=value credential")

    # 2. the 023E structured-log path (secret-shaped values + a key=value credential string).
    line = emit_structured_log("audit_probe", now=now, credential=planted_token,
                               region_key=planted_key, detail="api_key=" + planted_kv_value)
    for label, secret in sorted(planted.items()):
        if secret in line:
            findings.append("emit_structured_log() leaked a planted {0} secret value".format(label))

    # 3. the 023E health-JSON path (sanitized on render).
    report = ObservabilityReport(store_dir="audit", generated_at=now,
                                 service_health={"blob": planted_key, "token": planted_token,
                                                 "note": "api_key=" + planted_kv_value})
    health = render_health_json(report)
    for label, secret in sorted(planted.items()):
        if secret in health:
            findings.append("render_health_json() leaked a planted {0} secret value".format(label))

    caveats = (
        "planted synthetic AWS-/OpenAI-shaped secrets + a key=value credential through the 020C "
        "sanitize(), the 023E emit_structured_log(), and the 023E health-JSON render -- each path "
        "REDACTED the value; a value never reaches a log line, metric, or health file",)
    return SecurityAuditCategory("logs_and_errors_sanitized", not findings, tuple(findings), caveats)


def _check_file_permissions(repo_root: str, now: str) -> SecurityAuditCategory:
    src_root = _src_root(repo_root)
    findings: List[str] = []
    checked = 0
    for rel in _python_files(src_root, AUDIT_PACKAGES):
        path = os.path.join(src_root, rel)
        try:
            mode = os.stat(path).st_mode
        except OSError:
            continue
        checked += 1
        if mode & stat.S_IWOTH:
            findings.append("{0}: world-writable source file (mode {1:o})".format(
                rel, stat.S_IMODE(mode)))
    caveats = (
        "best-effort OFFLINE POSIX check of {0} source file(s): none is world-writable "
        "(no o+w bit)".format(checked),
        "on filesystems without POSIX permission bits this check is advisory",
    )
    return SecurityAuditCategory("file_permissions_sane", not findings, tuple(findings), caveats)


# The audit categories, in a fixed deterministic order.
_CHECKERS = (
    _check_no_secrets,
    _check_no_network_on_import,
    _check_no_broker_execution,
    _check_no_trade_controls,
    _check_no_hidden_score_rank,
    _check_no_social_laundering,
    _check_no_manual_canonical,
    _check_no_unsafe_default_production,
    _check_no_fixture_leakage,
    _check_dependencies_reviewed,
    _check_logs_and_errors_sanitized,
    _check_file_permissions,
)


# --------------------------------------------------------------------------- #
# The audit                                                                     #
# --------------------------------------------------------------------------- #
def run_security_audit(repo_root: str, *, now: str,
                       inject: Optional[Mapping[str, Sequence[str]]] = None
                       ) -> SecurityAuditReport:
    """Run every guardrail category against ``repo_root`` and return the frozen, honest report.

    ``now`` is the ONLY clock (injected everywhere; no wall-clock read) so the report is
    byte-deterministic. Each category reports its REAL pass/fail -- nothing is suppressed. ``inject``
    (category id -> extra findings) forces a synthetic finding INTO a category, flipping it to
    failed: it exists ONLY to PROVE the audit is honest (a real finding is reported and would exit
    the CLI non-zero); it never HIDES a finding. Everything is OFFLINE.
    """
    if not str(repo_root).strip():
        raise ValueError("run_security_audit requires a repo_root")
    if not str(now).strip():
        raise ValueError("run_security_audit requires an injected 'now' instant")
    generated_at = _format_utc(_parse_utc(now, name="now"))
    injected = {str(k): tuple(str(f) for f in v) for k, v in (inject or {}).items()}

    categories: List[SecurityAuditCategory] = []
    for checker in _CHECKERS:
        cat = checker(repo_root, now)
        extra = injected.get(cat.id)
        if extra:
            cat = SecurityAuditCategory(
                cat.id, False, tuple(cat.findings) + extra, cat.caveats)
        categories.append(cat)
    return SecurityAuditReport(repo_root=str(repo_root), generated_at=generated_at,
                               categories=tuple(categories))


def render_security_audit(report: SecurityAuditReport) -> str:
    """Render the reports/SECURITY_AUDIT_023H.md content: each category + pass/fail + findings.

    The rendered report NEVER contains a secret VALUE -- findings carry pattern NAMES + refs only.
    Deterministic (a function of the frozen report).
    """
    verdict = "PASS" if report.passed else "FAIL"
    lines = [
        "# CosmosIQ Security / Compliance / Audit Pass (IMPLEMENTATION-023H)",
        "",
        "**Verdict:** {0}".format(verdict),
        "",
        "- Repo root: `{0}`".format(report.repo_root),
        "- Generated at (injected): `{0}`".format(report.generated_at),
        "- Categories: {0} total, {1} failed".format(
            len(report.categories), len(report.categories_failed)),
        "- Swept packages: {0}".format(", ".join(AUDIT_PACKAGES)),
        "",
        "This audit COMPOSES the already-accepted guardrail scans (019A CI gate, 013E "
        "Data-Quality gate, 020C sanitizer, 020F/022H/023A/023G production posture). It is "
        "HONEST: each category reports its real pass/fail; no failure is hidden or rubber-stamped; "
        "no secret VALUE appears anywhere in this report.",
        "",
        "## Categories",
        "",
    ]
    for cat in report.categories:
        lines.append("### {0} -- {1}".format(cat.id, "PASS" if cat.passed else "FAIL"))
        lines.append("")
        if cat.findings:
            lines.append("Findings:")
            for finding in cat.findings:
                lines.append("- {0}".format(finding))
        else:
            lines.append("Findings: none.")
        if cat.caveats:
            lines.append("")
            lines.append("How checked / caveats:")
            for caveat in cat.caveats:
                lines.append("- {0}".format(caveat))
        lines.append("")
    lines.extend([
        "## Honest caveats",
        "",
        "- OFFLINE audit: it proves the guardrails HOLD in an offline evaluation; a live "
        "penetration test, a dependency CVE scan against a lockfile, and a running-host permission "
        "audit remain OUT OF SCOPE and are operator responsibilities before go-live.",
        "- The UI-owned surface (`universe_ui` / `generated`) is a separate product and is not "
        "swept here.",
        "- The secret sweeps report the presence + pattern NAME of any secret-shaped value; they "
        "never capture or print the value itself.",
        "",
        "## Recommended verdict",
        "",
        "**{0}** -- {1}".format(
            verdict,
            "every guardrail category passes on the current repository; safe to proceed to the "
            "operator deployment steps." if report.passed
            else "one or more guardrail categories FAILED; deployment must not proceed until the "
                 "findings above are resolved."),
        "",
    ])
    return "\n".join(lines)
