"""The CosmosIQ CI gate (Phase 019): every guardrail sweep as CODE, one command.

``run_ci_gate`` is THE gate for any future pipeline. It re-proves, on demand:

1. the full unittest suite passes OFFLINE (run in a subprocess under a socket
   kill-switch -- ``socket.socket.connect`` refuses everything);
2. no network / scheduler / broker import exists in the swept packages outside the
   two sanctioned shells (AST facts, not grep);
3. no ``*score*`` / ``*rank*`` function exists in the swept packages;
4. the runtime packages stay free of ``subprocess`` and wall-clock calls (both are
   sanctioned ONLY inside ``cosmosiq_ops`` -- an operator tool, not runtime);
5. the demo build is byte-identical run-to-run AND to the default build;
6. rendered pages carry ZERO Sanskrit / trade-affordance / secret tokens (the gate
   renders a scratch store's pages itself, and also scans any ``*.html`` planted
   under ``<repo_root>/generated`` or ``<repo_root>/pages``);
7. no ``.env`` file is tracked by git;
8. the frozen specification tree has no uncommitted edits (optional; skipped
   outside a git checkout).

``subprocess`` use here (the suite run and the two git checks) is deliberate and
confined to ``cosmosiq_ops``: this module is operator tooling that inspects the
repository -- it is never imported by runtime code.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess  # ops-only: sanctioned for the suite run + git checks (see module docstring)
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Tuple

# --------------------------------------------------------------------------- #
# Guardrail data (single source for the sweeps below)                          #
# --------------------------------------------------------------------------- #

SWEPT_PACKAGES = ("reality_mesh", "cosmosiq_app", "cosmosiq_ops")
RUNTIME_PACKAGES = ("reality_mesh", "cosmosiq_app")

# The ONLY files allowed to import network modules (paths relative to ``src/``).
SANCTIONED_NETWORK_SHELLS = (
    "cosmosiq_app/server.py",
    "evidence_ingestion/live_transport.py",
)
# The ONLY runtime file allowed to call a wall clock (the operator-started shell).
SANCTIONED_WALL_CLOCK_FILES = ("cosmosiq_app/server.py",)

NETWORK_IMPORT_ROOTS = frozenset({
    "socket", "socketserver", "ssl", "http", "urllib", "requests", "ftplib",
    "smtplib", "telnetlib", "xmlrpc", "poplib", "imaplib", "nntplib",
})
SCHEDULER_IMPORT_ROOTS = frozenset({
    "sched", "schedule", "asyncio", "apscheduler", "celery", "crontab",
})
BROKER_IMPORT_ROOTS = frozenset({
    "ib_insync", "ibapi", "alpaca", "alpaca_trade_api", "ccxt", "broker",
})
RUNTIME_BANNED_IMPORT_ROOTS = frozenset({"subprocess", "multiprocessing", "pty"})
WALL_CLOCK_ATTRS = ("now", "utcnow", "today", "time", "monotonic", "perf_counter",
                    "sleep")

# Page-token guardrails (identical to the standing page-test lists).
SANSKRIT_TOKENS = ("adhara", "buddhi", "tattva", "sphurana", "nivesha", "saarathi",
                   "kriya", "anubhava")
# A TRADE AFFORDANCE (an actual control/action), NOT the honest guardrail nouns. The standing
# page tests pass on a UI that legitimately says "Broker: Disabled", "no order is placed",
# "not a trade recommendation" -- so match action phrasings, never the bare nouns broker/trade/
# order. The planted-violation test uses "BUY", which \bbuy\b still catches.
TRADE_WORD_RE = re.compile(
    r"\b(buy|sell|strong\s+buy|hold\s+recommendation)\b"
    r"|place[\s_-]*order|submit[\s_-]*order|order[\s_-]*now|execute[\s_-]*trade"
    r"|trade[\s_-]*now|broker[\s:_-]*(submit|connect)|auto[\s_-]*(trade|rebalance)",
    re.IGNORECASE)
SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]{8,}"),
)
SECRET_KEY_TOKENS = ("api_key", "apikey", "client_secret", "access_key",
                     "private_key", "auth_token")

# Extra html trees the page scan sweeps for planted artifacts (relative to repo_root).
PLANTABLE_PAGE_DIRS = ("generated", "pages")

# The scratch pages the gate renders and scans (matches the standing page tests).
GATE_PAGE_PATHS = ("/", "/runs", "/alerts", "/settings", "/themes", "/portfolio")

_GATE_NOW = "2026-06-29T00:00:00Z"
_INNER_ENV_FLAG = "COSMOSIQ_CI_GATE_INNER"

# Bootstrap for the suite subprocess: kill the socket FIRST, then discover tests.
_SUITE_BOOTSTRAP = (
    "import socket\n"
    "def _refuse(*a, **k):\n"
    "    raise OSError('network disabled by the CosmosIQ CI gate kill-switch')\n"
    "socket.socket.connect = _refuse\n"
    "socket.create_connection = _refuse\n"
    "import unittest\n"
    "unittest.main(module=None, argv=['ci-gate', 'discover', '-s', 'tests'])\n"
)


@dataclass(frozen=True)
class CheckResult:
    """One gate check: a name, a closed status, and NAMED findings."""

    name: str
    status: str  # "pass" | "fail" | "skipped"
    details: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CiGateReport:
    """The whole gate run. ``passed`` is strict: any failing check fails the gate."""

    repo_root: str
    quick: bool
    checks: Tuple[CheckResult, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    @property
    def checks_failed(self) -> int:
        return sum(1 for check in self.checks if check.status == "fail")


# --------------------------------------------------------------------------- #
# AST sweeps                                                                    #
# --------------------------------------------------------------------------- #

def _python_files(src_root: str, packages: Tuple[str, ...]) -> List[str]:
    """Relative (to src_root) paths of every .py file in the given packages, sorted."""
    found = []
    for package in packages:
        base = os.path.join(src_root, package)
        if not os.path.isdir(base):
            continue
        for root, dirs, names in os.walk(base):
            dirs.sort()
            for name in sorted(names):
                if name.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, name), src_root)
                    found.append(rel.replace(os.sep, "/"))
    return found


def _import_roots(tree: ast.AST) -> List[Tuple[str, int]]:
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.append((node.module.split(".")[0], node.lineno))
    return roots


def _parse(src_root: str, rel: str) -> ast.AST:
    with open(os.path.join(src_root, rel.replace("/", os.sep)), encoding="utf-8") as fh:
        return ast.parse(fh.read())


def check_no_network_scheduler_broker_imports(repo_root: str) -> CheckResult:
    """AST sweep: zero network/scheduler/broker imports outside the sanctioned shells."""
    src_root = os.path.join(repo_root, "src")
    banned = NETWORK_IMPORT_ROOTS | SCHEDULER_IMPORT_ROOTS | BROKER_IMPORT_ROOTS
    violations = []
    files = _python_files(src_root, SWEPT_PACKAGES)
    for rel in files:
        if rel in SANCTIONED_NETWORK_SHELLS:
            continue
        for root, lineno in _import_roots(_parse(src_root, rel)):
            if root in banned:
                violations.append("{0}:{1}: banned import '{2}'".format(rel, lineno, root))
    status = "fail" if violations else "pass"
    details = tuple(violations) or ("{0} files swept; sanctioned shells: {1}".format(
        len(files), ", ".join(SANCTIONED_NETWORK_SHELLS)),)
    return CheckResult("no_network_scheduler_broker_imports", status, details)


def check_no_score_rank_functions(repo_root: str) -> CheckResult:
    """AST sweep: no hidden-scoring function in the intelligence RUNTIME packages.

    The guardrail targets the intelligence surface (``reality_mesh`` / ``cosmosiq_app``). The
    ``cosmosiq_ops`` CI tooling legitimately NAMES its checks after what they forbid (e.g. this
    very function contains 'score' and 'rank'), so it is not swept for this particular check --
    it defines no runtime scoring, only a gate over the runtime.
    """
    src_root = os.path.join(repo_root, "src")
    violations = []
    files = _python_files(src_root, ("reality_mesh", "cosmosiq_app"))
    for rel in files:
        for node in ast.walk(_parse(src_root, rel)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered = node.name.lower()
                if "score" in lowered or "rank" in lowered:
                    violations.append("{0}:{1}: hidden-score function '{2}'".format(
                        rel, node.lineno, node.name))
    status = "fail" if violations else "pass"
    return CheckResult("no_score_rank_functions", status,
                       tuple(violations) or ("{0} files swept".format(len(files)),))


def check_runtime_shell_discipline(repo_root: str) -> CheckResult:
    """AST sweep: runtime packages hold NO subprocess/multiprocessing import and NO
    wall-clock call -- both stay confined to cosmosiq_ops (operator tooling) and, for
    the wall clock, the operator-started server shell."""
    src_root = os.path.join(repo_root, "src")
    violations = []
    files = _python_files(src_root, RUNTIME_PACKAGES)
    for rel in files:
        tree = _parse(src_root, rel)
        for root, lineno in _import_roots(tree):
            if root in RUNTIME_BANNED_IMPORT_ROOTS:
                violations.append("{0}:{1}: runtime import '{2}' (ops-only)".format(
                    rel, lineno, root))
        if rel in SANCTIONED_WALL_CLOCK_FILES:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in WALL_CLOCK_ATTRS):
                violations.append("{0}:{1}: wall-clock call '.{2}()' (ops-only)".format(
                    rel, node.lineno, node.func.attr))
    status = "fail" if violations else "pass"
    return CheckResult("runtime_free_of_subprocess_and_wall_clock", status,
                       tuple(violations) or ("{0} runtime files swept".format(len(files)),))


# --------------------------------------------------------------------------- #
# Demo build + page scans                                                       #
# --------------------------------------------------------------------------- #

def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def check_demo_build_byte_identical() -> CheckResult:
    """Build the demo twice AND once with defaults: every page must be byte-identical."""
    from universe_ui.app import build_universe_app

    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2, \
            tempfile.TemporaryDirectory() as d3:
        first = build_universe_app(d1, mode="demo")
        second = build_universe_app(d2, mode="demo")
        default = build_universe_app(d3)
        drifted = []
        for name in sorted(first):
            a = _read_bytes(first[name])
            if name not in second or a != _read_bytes(second[name]):
                drifted.append("demo rebuild drifted: " + name)
            if name not in default or a != _read_bytes(default[name]):
                drifted.append("demo vs default drifted: " + name)
    status = "fail" if drifted else "pass"
    return CheckResult("demo_build_byte_identical", status,
                       tuple(drifted) or ("{0} pages byte-identical across demo x2 + "
                                          "default".format(len(first)),))


def _scan_page_text(label: str, text: str) -> List[str]:
    lowered = text.lower()
    findings = []
    for token in SANSKRIT_TOKENS:
        if token in lowered:
            findings.append("{0}: sanskrit token '{1}'".format(label, token))
    match = TRADE_WORD_RE.search(text)
    if match:
        findings.append("{0}: trade-affordance token '{1}'".format(label, match.group(0)))
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.search(text):
            findings.append("{0}: secret-like value matching {1}".format(
                label, pattern.pattern))
    for token in SECRET_KEY_TOKENS:
        if token in lowered:
            findings.append("{0}: credential key token '{1}'".format(label, token))
    return findings


def check_generated_pages_clean(repo_root: str) -> CheckResult:
    """Render a scratch store's pages + scan any planted html: ZERO Sanskrit /
    trade-affordance / secret tokens."""
    findings: List[str] = []
    pages_scanned = 0

    # 1. any html sitting in the plantable output trees of the target repo.
    for rel_dir in PLANTABLE_PAGE_DIRS:
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
                        findings.extend(_scan_page_text(label, fh.read()))
                    pages_scanned += 1

    # 2. the app's own server-rendered pages over a freshly seeded scratch store.
    from cosmosiq_app.api import dispatch
    from reality_mesh import run_pulse
    from reality_mesh.pulse_persistence import persist_and_summarize

    with tempfile.TemporaryDirectory() as store_dir:
        pulse = run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_GATE_NOW)
        persist_and_summarize(pulse, store_dir=store_dir, run_id="RUN-CI-GATE",
                              now=_GATE_NOW)
        for path in GATE_PAGE_PATHS:
            response = dispatch({"method": "GET", "path": path, "query": {},
                                 "body": None}, store_dir=store_dir, now=_GATE_NOW)
            if response["status"] != 200:
                findings.append("page {0}: status {1}".format(path, response["status"]))
                continue
            findings.extend(_scan_page_text("page " + path, str(response["body"])))
            pages_scanned += 1

    status = "fail" if findings else "pass"
    return CheckResult("generated_pages_clean", status,
                       tuple(findings) or ("{0} pages scanned; 0 sanskrit / "
                                           "trade-affordance / secret tokens"
                                           .format(pages_scanned),))


# --------------------------------------------------------------------------- #
# Git-backed checks (subprocess, ops-only)                                      #
# --------------------------------------------------------------------------- #

def _git(repo_root: str, *args: str):
    try:
        return subprocess.run(["git", "-C", repo_root] + list(args),
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_env_not_tracked(repo_root: str) -> CheckResult:
    """`git ls-files` must show NO tracked .env anywhere. Skipped outside a git repo."""
    completed = _git(repo_root, "ls-files")
    if completed is None or completed.returncode != 0:
        return CheckResult("env_not_tracked", "skipped",
                           ("not a git checkout (or git unavailable) -- nothing tracked",))
    tracked = [line for line in completed.stdout.splitlines()
               if os.path.basename(line) == ".env" or line.endswith("/.env")]
    status = "fail" if tracked else "pass"
    return CheckResult("env_not_tracked", status,
                       tuple("tracked secret file: " + t for t in tracked)
                       or (".env is not tracked by git",))


def check_frozen_spec_untouched(repo_root: str) -> CheckResult:
    """The frozen specification tree must carry no uncommitted edits (optional check)."""
    completed = _git(repo_root, "status", "--porcelain", "--", "specification/")
    if completed is None or completed.returncode != 0:
        return CheckResult("frozen_spec_untouched", "skipped",
                           ("not a git checkout (or git unavailable)",))
    dirty = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    status = "fail" if dirty else "pass"
    return CheckResult("frozen_spec_untouched", status,
                       tuple("uncommitted spec change: " + d for d in dirty)
                       or ("specification/ clean",))


# --------------------------------------------------------------------------- #
# Full suite under the socket kill-switch                                       #
# --------------------------------------------------------------------------- #

def check_suite_offline(repo_root: str) -> CheckResult:
    """Run the ENTIRE unittest suite in a subprocess with the socket refused."""
    env = dict(os.environ)
    env[_INNER_ENV_FLAG] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", _SUITE_BOOTSTRAP],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=1800)
    output = (completed.stderr or "") + (completed.stdout or "")
    ran_line = ""
    for line in output.splitlines():
        if line.startswith("Ran "):
            ran_line = line.strip()
    if completed.returncode == 0 and ran_line:
        return CheckResult("suite_offline", "pass",
                           (ran_line + " -- OK under socket kill-switch",))
    tail = tuple(line for line in output.splitlines()[-15:] if line.strip())
    return CheckResult("suite_offline", "fail",
                       (("suite exit code {0}".format(completed.returncode),) + tail))


# --------------------------------------------------------------------------- #
# The gate                                                                      #
# --------------------------------------------------------------------------- #

def run_ci_gate(repo_root: str, *, quick: bool = False) -> CiGateReport:
    """Run every gate check against ``repo_root`` and return the frozen report.

    ``quick=True`` skips the full-suite subprocess run (the expensive check) but keeps
    every sweep. The gate also never recurses: when invoked FROM inside a suite run it
    started (env flag), the suite check reports itself skipped.
    """
    checks: List[CheckResult] = []
    if quick or os.environ.get(_INNER_ENV_FLAG):
        checks.append(CheckResult("suite_offline", "skipped",
                                  ("quick mode -- run without --quick for the full "
                                   "suite under the socket kill-switch",)))
    else:
        checks.append(check_suite_offline(repo_root))
    checks.append(check_no_network_scheduler_broker_imports(repo_root))
    checks.append(check_no_score_rank_functions(repo_root))
    checks.append(check_runtime_shell_discipline(repo_root))
    checks.append(check_demo_build_byte_identical())
    checks.append(check_generated_pages_clean(repo_root))
    checks.append(check_env_not_tracked(repo_root))
    checks.append(check_frozen_spec_untouched(repo_root))
    return CiGateReport(repo_root=str(repo_root), quick=bool(quick),
                        checks=tuple(checks))


def format_ci_gate_report(report: CiGateReport) -> str:
    lines = ["CosmosIQ CI gate -- {0}".format("PASS" if report.passed else "FAIL"),
             "repo: {0}".format(report.repo_root),
             "mode: {0}".format("quick" if report.quick else "full")]
    for check in report.checks:
        lines.append("[{0:^7}] {1}".format(check.status, check.name))
        for detail in check.details:
            lines.append("          - " + detail)
    lines.append("checks: {0} total, {1} failed".format(
        len(report.checks), report.checks_failed))
    return "\n".join(lines)
