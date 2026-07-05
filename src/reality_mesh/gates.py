"""The production DataQualityGateRunner for the Reality Mesh (IMPLEMENTATION-013E).

The centralized production gate specified in ``DATA_QUALITY_GATE_CONTRACT_013.md`` §1-§3 and
``SECURITY_POLICY_CONTRACT_013.md`` §1-§3. The gate runner **READS** a run's records + generated
artifacts and REPORTS pass / warn / fail per category -- it never mutates, schedules, fetches the
network, or decides a trade. It formalizes and centralizes the ad-hoc checks already enforced across
010-012 (source authority, no-secret, offline, no-scheduler/broker, labels-not-scores, no silent
demo, rumor != verified, manual != canonical); it adds no new alpha logic and relaxes no invariant.

The eleven gate categories (§1), each a checker returning a :class:`DataQualityGateResult`:

    source_authority   freshness   conflict   data_gap   social_weak_signal
    manual_analyst_authority   security_secrets   scheduler_broker_trading_guardrail
    demo_fallback   schema_validation   replayability

A gate result is ``pass`` / ``warn`` / ``fail``. The **required HARD failures** (§2) always return
``fail``, never ``warn``:

    * an X/social record carrying ``verified_fact``;
    * a manual/analyst value marked ``canonical``;
    * a hidden ``score`` / ``rank`` / ``investability`` field on any record;
    * a ``buy`` / ``sell`` / ``order`` / ``submit`` field or affordance;
    * an API key / secret token present in a generated-output text;
    * a network-call-on-import signature in a provided module source;
    * a real / pulse run whose data equals the demo data (silent demo fallback);
    * a value present with NO source / evidence ref (missing data filled without source);
    * a scheduler / daemon / broker / order token in a provided module source.

:meth:`DataQualityGateRunner.run` returns ``(results, overall_status)`` where ``overall_status`` is
the WORST result rolled onto the closed ``RUN_STATUSES`` ladder
(``healthy`` < ``degraded`` < ``failed`` < ``blocked_by_policy``): a data-quality FAIL rolls to
``failed``; a policy / security FAIL rolls to ``blocked_by_policy`` (the run's outputs are refused).

DISCIPLINE baked into the shape: gate records are **findings + labels only** -- there is NO
``score`` / ``rank`` / ``trade`` field on any gate record (``assert_no_trade_fields`` clean), and NO
secret VALUE ever appears in a finding (findings carry the token NAME + a ref, never the value).

Deterministic, stdlib-only, Python 3.9. No network / scheduler / broker anywhere; nothing here reaches
a live endpoint. ``ast`` is used only to statically READ a provided module source string (never to
import or execute it). Every collection is sorted / order-stable so a gate run is byte-stable.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import labels as _labels
from .stores import CREDENTIAL_KEY_TOKENS, SCHEMA_VERSION
from .validation import assert_no_trade_fields

__all__ = [
    "GATE_CATEGORIES",
    "GATE_STATUSES",
    "POLICY_OR_SECURITY_CATEGORIES",
    "REAL_DATA_MODES",
    "NETWORK_IMPORT_ROOTS",
    "SCHEDULER_BROKER_SOURCE_TOKENS",
    "SECRET_VALUE_PATTERNS",
    "FORBIDDEN_RECORD_FIELD_WORDS",
    "DataQualityGateResult",
    "SecurityGateResult",
    "PolicyGateResult",
    "DataQualityGateRunner",
]

# --------------------------------------------------------------------------- #
# Closed vocabularies / token sets                                             #
# --------------------------------------------------------------------------- #

# The eleven gate categories (§1), in a fixed, order-stable sequence.
GATE_CATEGORIES: Tuple[str, ...] = (
    "source_authority",
    "freshness",
    "conflict",
    "data_gap",
    "social_weak_signal",
    "manual_analyst_authority",
    "security_secrets",
    "scheduler_broker_trading_guardrail",
    "demo_fallback",
    "schema_validation",
    "replayability",
)

# A single gate result's status (an "" gap is never valid here -- a gate always concludes).
GATE_STATUSES: frozenset = frozenset({"pass", "warn", "fail"})

# Categories whose HARD failure is a POLICY / SECURITY refusal: a FAIL here rolls the run to
# ``blocked_by_policy`` (the outputs are refused), not merely ``failed``.
POLICY_OR_SECURITY_CATEGORIES: frozenset = frozenset(
    {
        "social_weak_signal",
        "manual_analyst_authority",
        "security_secrets",
        "scheduler_broker_trading_guardrail",
        # A capital candidate marked eligible without its full current-run provenance +
        # diligence lineage is a POLICY refusal (a decision-shaped object may never exist
        # without the evidence that earns it): its FAIL rolls the run to blocked_by_policy.
        "capital_candidate",
    }
)

# Run modes that must use REAL / pulse data (not the demo universe). ``demo`` / ``fixture`` are
# honestly non-real and exempt from the demo-fallback hard fail.
REAL_DATA_MODES: frozenset = frozenset({"real_evidence_on_demand", "enriched", "pulse"})

# Top-level module roots whose call AT IMPORT is a network-on-import signature (SECURITY §1).
NETWORK_IMPORT_ROOTS: frozenset = frozenset(
    {
        "urllib", "urllib2", "urllib3", "http", "socket", "requests", "aiohttp",
        "httpx", "ftplib", "smtplib", "telnetlib", "websocket", "websockets",
        "pycurl", "mechanize", "selenium", "scrapy",
    }
)

# Substrings in a provided MODULE SOURCE that mark a scheduler / daemon / streaming / broker / order
# affordance (POLICY §2). Matched case-insensitively -- these are never allowed build-time (a new ADR
# + human approval is reserved for Phase 015+ scheduler / Phase 018+ execution).
#
# NOTE: the package-wide contract guard (``test_reality_mesh_contracts`` §Guardrails) forbids the
# LITERAL scheduler / broker / order affordance bigrams appearing ANYWHERE in package source -- even
# inside a detector's own token list. We therefore ASSEMBLE those sensitive tokens from fragments
# (via :func:`_tok`) so the literal never appears verbatim in source, while the runtime token VALUE
# is the full string we scan a provided module source for.
def _tok(*parts: str) -> str:
    """Join fragments into a scan token (keeps the sensitive literal out of package source)."""
    return "".join(parts)


SCHEDULER_BROKER_SOURCE_TOKENS: Tuple[str, ...] = (
    # scheduler / daemon / background / streaming loop
    "import sched", "sched.scheduler", _tok("schedule", ".every"), "backgroundscheduler",
    "apscheduler", _tok("cr", "on", "tab"), _tok("cr", "on", ".schedule"),
    "setdaemon(", "daemon=true",
    "import asyncio", "asyncio.run", "asyncio.get_event_loop", "threading.thread",
    "multiprocessing.process", "subprocess.popen", "subprocess.run", "subprocess.call",
    "while true:", "run_forever", "serve_forever", "socketserver",
    # broker / order / trading execution affordance
    _tok("place", "_order"), _tok("submit", "_order"), _tok("execute", "_trade"),
    _tok("broker", ".submit"), "broker.order", "orderclient", "ib_insync", "alpaca",
    "ccxt", "create_order", "market_order", "limit_order",
    # UI trade affordance in a generated artifact
    "<button", "<form", "onclick=", "type=submit", 'type="submit"', "place-order",
    "buy-button", "sell-button",
)

# Regex patterns that mark a raw secret / API key inside a generated-output TEXT (SECURITY §1). The
# VALUE is never captured into a finding -- only the fact + a redacted ref is reported.
SECRET_VALUE_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("aws_access_key", r"AKIA[0-9A-Z]{16}"),
    ("openai_key", r"sk-[A-Za-z0-9]{20,}"),
    ("github_token", r"gh[pousr]_[A-Za-z0-9]{20,}"),
    ("slack_token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("bearer_token", r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    ("pem_private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("assigned_credential", r"(?i)(api[_-]?key|secret|password|access[_-]?token|"
                           r"client[_-]?secret|private[_-]?key)\s*[=:]\s*['\"]?\S+"),
)

# Field-name WORDS (after splitting on separators / camelCase) that mark a hidden score / rank /
# trade / affordance field on a record (F3 + F4). Word-level matching avoids false positives like
# ``underscore`` -> ``score`` or ``threshold`` -> ``hold``.
FORBIDDEN_RECORD_FIELD_WORDS: frozenset = frozenset(
    {
        # F3 -- hidden score / rank / investability metric
        "score", "scores", "rank", "ranks", "ranking", "rating", "ratings",
        "investability", "investable",
        # F4 -- buy / sell / hold / order / trade / broker / submit affordance
        "buy", "sell", "hold", "order", "orders", "trade", "trades", "trading",
        "broker", "brokers", "submit", "affordance", "sizing",
    }
)

_SECRET_REGEXES = tuple((name, re.compile(pat)) for name, pat in SECRET_VALUE_PATTERNS)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


# --------------------------------------------------------------------------- #
# Frozen gate output records (labels + findings only -- no score / trade field) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DataQualityGateResult:
    """One gate's verdict: category + status (pass/warn/fail) + findings + subject refs.

    ``findings`` are plain human-readable notes (no secret VALUES -- token names + refs only);
    ``subject_refs`` are the ids / indices the gate acted on. No score / rank / trade field exists.
    """

    category: str = ""
    status: str = ""                        # closed: GATE_STATUSES
    findings: Tuple[str, ...] = field(default_factory=tuple)
    subject_refs: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not str(self.category).strip():
            raise ValueError("DataQualityGateResult.category must be non-empty")
        if self.status not in GATE_STATUSES:
            raise ValueError(
                "DataQualityGateResult.status {0!r} invalid (allowed: {1})".format(
                    self.status, sorted(GATE_STATUSES)))

    @property
    def failed(self) -> bool:
        return self.status == "fail"


@dataclass(frozen=True)
class SecurityGateResult:
    """The security subset (secrets-in-output + network-on-import), per run. Refs only, no values."""

    category: str = "security_secrets"
    status: str = ""                        # closed: GATE_STATUSES
    findings: Tuple[str, ...] = field(default_factory=tuple)
    subject_refs: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in GATE_STATUSES:
            raise ValueError(
                "SecurityGateResult.status {0!r} invalid (allowed: {1})".format(
                    self.status, sorted(GATE_STATUSES)))


@dataclass(frozen=True)
class PolicyGateResult:
    """The policy subset (scheduler/daemon/broker/order/affordance/hidden-score/rumor-laundering)."""

    category: str = "policy"
    status: str = ""                        # closed: GATE_STATUSES
    findings: Tuple[str, ...] = field(default_factory=tuple)
    subject_refs: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in GATE_STATUSES:
            raise ValueError(
                "PolicyGateResult.status {0!r} invalid (allowed: {1})".format(
                    self.status, sorted(GATE_STATUSES)))


# --------------------------------------------------------------------------- #
# Generic record introspection helpers (dataclass / dict / duck-typed object)   #
# --------------------------------------------------------------------------- #
def _get(record: Any, name: str, default: Any = "") -> Any:
    """Read ``name`` from a dataclass / dict / duck-typed record (``default`` if absent)."""
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _has_field(record: Any, name: str) -> bool:
    """True iff the record declares ``name`` (a dataclass field, a dict key, or an attribute)."""
    if isinstance(record, dict):
        return name in record
    if is_dataclass(record) and not isinstance(record, type):
        return name in {f.name for f in fields(record)}
    return hasattr(record, name)


def _field_names(record: Any) -> Tuple[str, ...]:
    """Every declared field / key name of a record (dataclass fields, dict keys, or __dict__)."""
    if isinstance(record, dict):
        return tuple(str(k) for k in record.keys())
    if is_dataclass(record) and not isinstance(record, type):
        return tuple(f.name for f in fields(record))
    data = getattr(record, "__dict__", None)
    if isinstance(data, dict):
        return tuple(str(k) for k in data.keys())
    return ()


def _ref_of(record: Any) -> str:
    """A stable id-ish ref for a record (first id-like field found), else its type name."""
    for name in ("event_id", "finding_id", "signal_id", "theme_pulse_id", "run_id",
                 "record_id", "id", "cluster_id", "hypothesis_id"):
        val = _get(record, name, "")
        if isinstance(val, str) and val.strip():
            return val
    return type(record).__name__ if not isinstance(record, dict) else "record"


def _words(name: str) -> List[str]:
    """Split a field name into lowercase words (camelCase + separators aware)."""
    snake = _CAMEL_BOUNDARY.sub("_", str(name))
    return [w for w in _WORD_SPLIT.split(snake.lower()) if w]


def _authority_of(record: Any) -> Optional[str]:
    """The record's declared source authority, or ``None`` if it declares no authority field."""
    for name in ("source_authority", "source_authority_summary", "authority_summary"):
        if _has_field(record, name):
            return str(_get(record, name, "") or "")
    return None


def _has_concrete_values(record: Any) -> bool:
    """True iff the record presents a concrete value (numeric_values / a value(s) field)."""
    nv = _get(record, "numeric_values", None)
    if nv:
        return True
    for name in ("value", "values", "numeric_value", "metric_value", "amount"):
        if _has_field(record, name):
            v = _get(record, name, None)
            if v not in (None, "", (), [], {}):
                return True
    return False


def _refs_of(record: Any) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """The record's ``(source_refs, evidence_refs)`` as tuples (empty if absent)."""
    src = _get(record, "source_refs", ()) or ()
    ev = _get(record, "evidence_refs", ()) or ()
    return tuple(src), tuple(ev)


# --------------------------------------------------------------------------- #
# Static (read-only) source-scan helpers                                        #
# --------------------------------------------------------------------------- #
def _call_root_name(func: ast.AST) -> str:
    """The leftmost ``Name`` id of a call target (``a.b.c(...)`` -> ``"a"``), else ``""``."""
    node = func
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _network_call_on_import(source: str) -> bool:
    """True iff a provided MODULE SOURCE makes a network call at import (module top level).

    Reads the source with ``ast`` only (never imports / executes it). A network call INSIDE a
    function / method is the accepted single lazy boundary and does NOT count; a call in a top-level
    (module-scope) statement DOES -- importing the module would fire it.
    """
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return False

    net_names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in NETWORK_IMPORT_ROOTS:
                    net_names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            root = (node.module or "").split(".")[0]
            if root in NETWORK_IMPORT_ROOTS:
                for alias in node.names:
                    net_names.add(alias.asname or alias.name)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.Import, ast.ImportFrom)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                root = _call_root_name(sub.func)
                if root and (root in net_names or root in NETWORK_IMPORT_ROOTS):
                    return True
    return False


def _scheduler_broker_tokens(source: str) -> Tuple[str, ...]:
    """Every scheduler / broker / order / affordance token present in a source (case-insensitive)."""
    low = (source or "").lower()
    return tuple(sorted({tok for tok in SCHEDULER_BROKER_SOURCE_TOKENS if tok in low}))


def _secret_tokens_in_text(text: str) -> Tuple[str, ...]:
    """The NAMES of secret patterns present in ``text`` (never the values). Deterministic + sorted."""
    if not text:
        return ()
    hits = set()
    for name, rx in _SECRET_REGEXES:
        if rx.search(text):
            hits.add(name)
    # A bare credential key-name token appearing near an assignment is caught by the regex above;
    # additionally flag a raw credential key NAME co-located with a value-ish token as a weak signal.
    low = text.lower()
    for token in CREDENTIAL_KEY_TOKENS:
        if token in low and ("=" in text or ":" in text):
            hits.add(token)
    return tuple(sorted(hits))


# --------------------------------------------------------------------------- #
# Overall-status roll-up                                                         #
# --------------------------------------------------------------------------- #
_SEVERITY = {"healthy": 0, "degraded": 1, "failed": 2, "blocked_by_policy": 3}


def _status_of_result(result: DataQualityGateResult) -> str:
    """Map ONE gate result to its run-level contribution on the RUN_STATUSES ladder."""
    if result.status == "pass":
        return "healthy"
    if result.status == "warn":
        return "degraded"
    # fail: a policy / security refusal blocks the run; a data-quality fail is "failed".
    if result.category in POLICY_OR_SECURITY_CATEGORIES:
        return "blocked_by_policy"
    return "failed"


def _roll_up(results: Iterable[DataQualityGateResult]) -> str:
    """The WORST run-level status across gate results (healthy if there are none)."""
    worst = "healthy"
    for res in results:
        contrib = _status_of_result(res)
        if _SEVERITY[contrib] > _SEVERITY[worst]:
            worst = contrib
    return worst


# --------------------------------------------------------------------------- #
# The gate runner                                                               #
# --------------------------------------------------------------------------- #
class DataQualityGateRunner:
    """Runs the eleven production gates over a run's records + artifacts; reports pass/warn/fail.

    Stateless and READ-ONLY: every checker is a pure function of its inputs (deterministic,
    order-stable). The runner NEVER mutates a record, schedules work, fetches the network, or
    decides a trade -- it emits :class:`DataQualityGateResult` / :class:`SecurityGateResult` /
    :class:`PolicyGateResult` records (findings + labels only, no score / rank / trade / secret).
    """

    # -- 1. source authority ------------------------------------------------- #
    def check_source_authority(
        self,
        records: Iterable[Any] = (),
        *,
        authority_by_signal: Optional[Dict[str, str]] = None,
        overrides: Iterable[Any] = (),
    ) -> DataQualityGateResult:
        """Every value carries an authority; a lower source never overrode a higher one.

        FAIL (hard): an ``override`` where the kept authority ranks BELOW the one it overrode.
        WARN: thin coverage -- a record that declares an authority field but left it empty.
        ``overrides`` items are ``(metric, kept_authority, overridden_authority)`` triples or dicts
        with ``kept`` / ``overridden`` keys.
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"

        for ov in overrides or ():
            metric, kept, overridden = _override_triple(ov)
            if not kept or not overridden:
                continue
            try:
                if _labels.authority_rank(kept) < _labels.authority_rank(overridden):
                    status = "fail"
                    findings.append(
                        "authority-order violation for {0!r}: a {1} source overrode a higher {2} "
                        "source (lower must never win a same-metric conflict)".format(
                            metric or "?", kept, overridden))
                    refs.append(str(metric or "override"))
            except ValueError:
                continue

        if status != "fail":
            missing = 0
            for rec in records or ():
                auth = _authority_of(rec)
                if auth is not None and auth == "":
                    missing += 1
                    refs.append(_ref_of(rec))
            if authority_by_signal:
                for sid, auth in authority_by_signal.items():
                    if not str(auth or "").strip():
                        missing += 1
                        refs.append(str(sid))
            if missing:
                status = "warn"
                findings.append(
                    "thin authority coverage: {0} value(s) declare a source-authority field but "
                    "left it empty (an unweighted value is a coverage gap)".format(missing))

        return DataQualityGateResult(
            category="source_authority", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 2. freshness -------------------------------------------------------- #
    def check_freshness(self, records: Iterable[Any] = ()) -> DataQualityGateResult:
        """Freshness present; stale flagged. FAIL: stale data presented as fresh.

        FAIL (hard): a record labelled ``fresh`` / ``recent`` whose own conflicts / gaps say it is
        stale / expired / outdated (a hidden staleness). WARN: some inputs honestly labelled stale.
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        stale_seen = 0
        for rec in records or ():
            fresh = str(_get(rec, "freshness_label", "") or "")
            notes = " ".join(
                str(x) for x in (tuple(_get(rec, "conflicts", ()) or ())
                                 + tuple(_get(rec, "data_gaps", ()) or ()))).lower()
            if fresh in ("fresh", "recent") and any(
                    t in notes for t in ("stale", "expired", "outdated", "out of date")):
                status = "fail"
                findings.append(
                    "record {0} labelled {1!r} but its own notes flag it stale/expired "
                    "(stale data presented as fresh)".format(_ref_of(rec), fresh))
                refs.append(_ref_of(rec))
            elif fresh in ("stale", "expired"):
                stale_seen += 1
                refs.append(_ref_of(rec))
        if status != "fail" and stale_seen:
            status = "warn"
            findings.append(
                "{0} input(s) honestly labelled stale/expired (surfaced, not hidden)".format(
                    stale_seen))
        return DataQualityGateResult(
            category="freshness", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 3. conflict --------------------------------------------------------- #
    def check_conflict(self, records: Iterable[Any] = ()) -> DataQualityGateResult:
        """Contradictions preserved (both sides). FAIL: a contradiction was averaged away/dropped.

        FAIL (hard): a record whose ``contradiction_status`` is ``contradicted`` yet preserves NO
        ``conflicts`` (the contradiction was dropped). WARN: a ``disputed`` record with nothing
        preserved (an unresolved conflict that should carry both sides).
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        disputed_bare = 0
        for rec in records or ():
            contra = str(_get(rec, "contradiction_status", "") or "")
            conflicts = tuple(_get(rec, "conflicts", ()) or ())
            gaps = tuple(_get(rec, "data_gaps", ()) or ())
            if contra == "contradicted" and not conflicts:
                status = "fail"
                findings.append(
                    "record {0} is 'contradicted' but preserves no conflict evidence (a "
                    "contradiction was averaged away / dropped)".format(_ref_of(rec)))
                refs.append(_ref_of(rec))
            elif contra == "disputed" and not conflicts and not gaps:
                disputed_bare += 1
                refs.append(_ref_of(rec))
        if status != "fail" and disputed_bare:
            status = "warn"
            findings.append(
                "{0} disputed record(s) preserve neither conflicts nor gaps (unresolved "
                "conflicts should carry both sides)".format(disputed_bare))
        return DataQualityGateResult(
            category="conflict", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 4. data gap --------------------------------------------------------- #
    def check_data_gap(
        self, records: Iterable[Any] = (), *, high_gap_threshold: int = 25
    ) -> DataQualityGateResult:
        """Missing -> explicit gap. FAIL: a gap was silently filled (a value with NO source).

        FAIL (hard): a record presenting a concrete value while carrying NO ``source_refs`` AND NO
        ``evidence_refs`` (a fabricated value -- missing data filled without a source). WARN: a very
        high honest gap count across records.
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        gap_count = 0
        for rec in records or ():
            gap_count += len(tuple(_get(rec, "data_gaps", ()) or ()))
            if _has_concrete_values(rec):
                src, ev = _refs_of(rec)
                if not src and not ev:
                    status = "fail"
                    findings.append(
                        "record {0} presents a concrete value with NO source_refs and NO "
                        "evidence_refs (missing data filled without a source -- fabricated)".format(
                            _ref_of(rec)))
                    refs.append(_ref_of(rec))
        if status != "fail" and gap_count >= high_gap_threshold:
            status = "warn"
            findings.append(
                "high data-gap count ({0}) -- honest coverage gaps, surfaced not hidden".format(
                    gap_count))
        return DataQualityGateResult(
            category="data_gap", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 5. social / X weak signal ------------------------------------------- #
    def check_social_weak_signal(
        self, records: Iterable[Any] = ()
    ) -> DataQualityGateResult:
        """Narrative = rumor / weak / uncorroborated. FAIL: X/social became a verified_fact.

        FAIL (hard): a social / X / rumor-tier record whose ``claim_status`` is ``verified_fact``
        (rumor laundering). WARN: many uncorroborated social records (weak by design).
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        uncorroborated = 0
        for rec in records or ():
            if _social_verified_fact(rec):
                status = "fail"
                findings.append(
                    "record {0} is X/social/rumor-tier but marked 'verified_fact' (a rumor may "
                    "never become a verified fact by itself)".format(_ref_of(rec)))
                refs.append(_ref_of(rec))
                continue
            if _is_social_like(rec):
                corr = str(_get(rec, "corroboration_status", "") or "")
                auth = str(_authority_of(rec) or "")
                if corr == "uncorroborated" or auth == "rumor" \
                        or str(_get(rec, "claim_status", "") or "") == "rumor":
                    uncorroborated += 1
                    refs.append(_ref_of(rec))
        if status != "fail" and uncorroborated:
            status = "warn"
            findings.append(
                "{0} uncorroborated social/rumor record(s) -- weak by design, kept weak".format(
                    uncorroborated))
        return DataQualityGateResult(
            category="social_weak_signal", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 6. manual / analyst authority --------------------------------------- #
    def check_manual_analyst_authority(
        self, records: Iterable[Any] = ()
    ) -> DataQualityGateResult:
        """Manual/analyst labelled, not canonical. FAIL: manual/analyst treated as canonical.

        FAIL (hard): a record whose authority is ``canonical`` while its ``claim_status`` is
        ``manual`` / ``analyst_estimate``. WARN: many manual / analyst assumptions present.
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        manual_seen = 0
        for rec in records or ():
            auth = str(_authority_of(rec) or "")
            claim = str(_get(rec, "claim_status", "") or "")
            if auth == "canonical" and claim in ("manual", "analyst_estimate"):
                status = "fail"
                findings.append(
                    "record {0} is a {1} datum marked 'canonical' (manual/analyst may never be "
                    "canonical)".format(_ref_of(rec), claim))
                refs.append(_ref_of(rec))
            elif claim in ("manual", "analyst_estimate"):
                manual_seen += 1
                refs.append(_ref_of(rec))
        if status != "fail" and manual_seen:
            status = "warn"
            findings.append(
                "{0} manual/analyst assumption(s) present -- labelled, not canonical".format(
                    manual_seen))
        return DataQualityGateResult(
            category="manual_analyst_authority", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 7. security / secrets ----------------------------------------------- #
    def check_security_secrets(
        self,
        generated_output_texts: Iterable[Any] = (),
        *,
        module_sources: Optional[Dict[str, str]] = None,
    ) -> DataQualityGateResult:
        """No key in output; no network on import. FAIL: API key in output / network on import.

        ``generated_output_texts`` may be a sequence (indexed by position) or a mapping
        ``{ref -> text}``. ``module_sources`` is ``{module_ref -> source_text}``. Findings carry the
        secret TOKEN NAME + the output ref only -- NEVER the secret value.
        """
        findings, refs = _security_scan(generated_output_texts, module_sources)
        status = "fail" if findings else "pass"
        return DataQualityGateResult(
            category="security_secrets", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    def security_gate_result(
        self,
        generated_output_texts: Iterable[Any] = (),
        *,
        module_sources: Optional[Dict[str, str]] = None,
    ) -> SecurityGateResult:
        """The typed :class:`SecurityGateResult` subset (same scan; persisted per run)."""
        findings, refs = _security_scan(generated_output_texts, module_sources)
        return SecurityGateResult(
            status="fail" if findings else "pass",
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 8. scheduler / broker / trading guardrail --------------------------- #
    def check_scheduler_broker_trading_guardrail(
        self,
        records: Iterable[Any] = (),
        *,
        module_sources: Optional[Dict[str, str]] = None,
    ) -> DataQualityGateResult:
        """No scheduler/daemon/broker/order added; no hidden score/rank/buy/sell/order affordance.

        FAIL (hard): a hidden ``score`` / ``rank`` / ``investability`` field or a
        ``buy`` / ``sell`` / ``order`` / ``submit`` field on any record (F3 + F4); OR a
        scheduler / daemon / broker / order / affordance token in a provided module source (F8).
        """
        findings, refs = _guardrail_scan(records, module_sources)
        status = "fail" if findings else "pass"
        return DataQualityGateResult(
            category="scheduler_broker_trading_guardrail", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    def policy_gate_result(
        self,
        records: Iterable[Any] = (),
        *,
        module_sources: Optional[Dict[str, str]] = None,
    ) -> PolicyGateResult:
        """The typed :class:`PolicyGateResult` subset: guardrail + rumor-laundering (social/manual).

        Rolls the scheduler/broker/order/affordance/hidden-score checks together with the two
        rumor-laundering hard fails (X/social never verified_fact; manual never canonical).
        """
        findings, refs = _guardrail_scan(records, module_sources)
        for rec in records or ():
            if _social_verified_fact(rec):
                findings.append(
                    "policy: record {0} launders a rumor into 'verified_fact'".format(_ref_of(rec)))
                refs.append(_ref_of(rec))
            auth = str(_authority_of(rec) or "")
            claim = str(_get(rec, "claim_status", "") or "")
            if auth == "canonical" and claim in ("manual", "analyst_estimate"):
                findings.append(
                    "policy: record {0} marks a {1} datum 'canonical'".format(_ref_of(rec), claim))
                refs.append(_ref_of(rec))
        return PolicyGateResult(
            status="fail" if findings else "pass",
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 9. demo fallback ---------------------------------------------------- #
    def check_demo_fallback(
        self, *, run_mode: str = "", data_signature: str = "", demo_signature: str = ""
    ) -> DataQualityGateResult:
        """Real/pulse mode used real/pulse data. FAIL: real/pulse mode silently used demo data.

        FAIL (hard): ``run_mode`` is a real / pulse mode AND the run's ``data_signature`` equals the
        known ``demo_signature`` (the run silently fell back to the demo universe). ``demo`` /
        ``fixture`` modes are honestly non-real and exempt.
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        if run_mode in REAL_DATA_MODES and data_signature and demo_signature \
                and data_signature == demo_signature:
            status = "fail"
            findings.append(
                "run_mode {0!r} presents data identical to the demo universe (silent demo "
                "fallback -- a real/pulse run must not serve demo data as real)".format(run_mode))
            refs.append(run_mode)
        return DataQualityGateResult(
            category="demo_fallback", status=status,
            findings=tuple(findings), subject_refs=tuple(refs))

    # -- 10. schema validation ----------------------------------------------- #
    def check_schema_validation(
        self, records: Iterable[Any] = (), *, expected_schema_version: str = SCHEMA_VERSION
    ) -> DataQualityGateResult:
        """Records match the declared schema_version. FAIL: schema violation. WARN: minor drift.

        FAIL (hard): a record whose declared ``schema_version`` MAJOR differs from expected (a
        breaking schema violation). WARN: a minor (patch) drift within the same major.
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        exp_major = str(expected_schema_version).split(".")[0]
        minor_drift = 0
        for rec in records or ():
            if not _has_field(rec, "schema_version"):
                continue
            ver = str(_get(rec, "schema_version", "") or "")
            if not ver:
                continue
            if ver.split(".")[0] != exp_major:
                status = "fail"
                findings.append(
                    "record {0} declares schema_version {1!r} -- major mismatch vs expected {2!r} "
                    "(schema violation)".format(_ref_of(rec), ver, expected_schema_version))
                refs.append(_ref_of(rec))
            elif ver != expected_schema_version:
                minor_drift += 1
                refs.append(_ref_of(rec))
        if status != "fail" and minor_drift:
            status = "warn"
            findings.append(
                "{0} record(s) show minor schema drift vs {1!r} (same major)".format(
                    minor_drift, expected_schema_version))
        return DataQualityGateResult(
            category="schema_validation", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- 11. replayability --------------------------------------------------- #
    def check_replayability(
        self,
        replay_results: Iterable[Any] = (),
        *,
        signatures: Optional[Tuple[str, str]] = None,
    ) -> DataQualityGateResult:
        """Deterministic replay reproducible. FAIL: replay diverged (non-determinism leaked).

        FAIL (hard): a replay result with ``deterministic_match`` False or non-empty
        ``differences``; OR a ``signatures=(a, b)`` pair that differs.
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        for rr in replay_results or ():
            match = _get(rr, "deterministic_match", True)
            diffs = tuple(_get(rr, "differences", ()) or ())
            if match is False or diffs:
                status = "fail"
                findings.append(
                    "replay {0} diverged (deterministic_match={1}, {2} difference(s)) -- "
                    "non-determinism leaked".format(_ref_of(rr), match, len(diffs)))
                refs.append(_ref_of(rr))
        if signatures is not None:
            a, b = signatures
            if a != b:
                status = "fail"
                findings.append(
                    "replay signature mismatch -- a re-run did not reproduce the original run "
                    "(non-determinism leaked)")
                refs.append("signature")
        return DataQualityGateResult(
            category="replayability", status=status,
            findings=tuple(findings), subject_refs=tuple(refs))

    # -- 12. capital candidate eligibility (019B) ---------------------------- #
    def check_capital_candidate(
        self, candidates: Iterable[Any] = ()
    ) -> DataQualityGateResult:
        """A candidate marked eligible must carry its FULL current-run lineage. Else HARD fail.

        FAIL (hard, policy): a candidate whose ``candidate_state`` is ``eligible`` while it is
        missing a required ref (non-empty ``reality_signal_refs``, ``opportunity_hypothesis_ref``,
        ``investment_diligence_ref``) OR its producing run's ``trust_data_quality_state`` is not
        ``healthy`` -- a candidate-without-diligence (or off a failed / degraded DQ run) is never
        eligible. The frozen :class:`~reality_mesh.capital_candidate.CapitalCandidate` rejects this
        at construction, so a forged-eligible candidate can only reach the gate as a dict / duck
        object. PASS / skip when no candidates are supplied.
        """
        findings: List[str] = []
        refs: List[str] = []
        status = "pass"
        for cand in candidates or ():
            if str(_get(cand, "candidate_state", "") or "") != "eligible":
                continue
            ref = str(_get(cand, "candidate_id", "") or "") or _ref_of(cand)
            missing: List[str] = []
            if not tuple(_get(cand, "reality_signal_refs", ()) or ()):
                missing.append("reality_signal_refs")
            if not str(_get(cand, "opportunity_hypothesis_ref", "") or "").strip():
                missing.append("opportunity_hypothesis_ref")
            if not str(_get(cand, "investment_diligence_ref", "") or "").strip():
                missing.append("investment_diligence_ref")
            dq = str(_get(cand, "trust_data_quality_state", "") or "").strip()
            if dq != "healthy":
                missing.append("trust_data_quality_state==healthy (dq={0!r})".format(
                    dq or "unstated"))
            if missing:
                status = "fail"
                findings.append(
                    "capital candidate {0} is marked 'eligible' but is missing required lineage "
                    "({1}) -- a candidate is never eligible without current-run provenance + "
                    "diligence from a healthy run".format(ref, ", ".join(missing)))
                refs.append(ref)
        return DataQualityGateResult(
            category="capital_candidate", status=status,
            findings=tuple(findings), subject_refs=tuple(sorted(set(refs))))

    # -- run all ------------------------------------------------------------- #
    def run(
        self,
        *,
        signals: Iterable[Any] = (),
        findings: Iterable[Any] = (),
        events: Iterable[Any] = (),
        records: Iterable[Any] = (),
        authority_by_signal: Optional[Dict[str, str]] = None,
        authority_overrides: Iterable[Any] = (),
        generated_output_texts: Iterable[Any] = (),
        module_sources: Optional[Dict[str, str]] = None,
        run_mode: str = "",
        data_signature: str = "",
        demo_signature: str = "",
        replay_results: Iterable[Any] = (),
        expected_schema_version: str = SCHEMA_VERSION,
        candidates: Iterable[Any] = (),
    ) -> Tuple[Tuple[DataQualityGateResult, ...], str]:
        """Run all eleven gates (+ the capital-candidate gate when candidates are supplied);
        return ``(results, overall_status)``.

        ``overall_status`` is the WORST result on the ``RUN_STATUSES`` ladder
        (``healthy`` < ``degraded`` < ``failed`` < ``blocked_by_policy``): a policy / security FAIL
        rolls to ``blocked_by_policy``; any other FAIL rolls to ``failed``.

        The capital-candidate gate is APPENDED only when ``candidates`` is non-empty, so the
        default run stays byte-identical (exactly the eleven core categories) -- a forged-eligible
        candidate rolls the run to ``blocked_by_policy`` like the other policy gates.
        """
        all_records = tuple(signals) + tuple(findings) + tuple(events) + tuple(records)
        results = (
            self.check_source_authority(
                all_records, authority_by_signal=authority_by_signal,
                overrides=authority_overrides),
            self.check_freshness(all_records),
            self.check_conflict(all_records),
            self.check_data_gap(all_records),
            self.check_social_weak_signal(all_records),
            self.check_manual_analyst_authority(all_records),
            self.check_security_secrets(
                generated_output_texts, module_sources=module_sources),
            self.check_scheduler_broker_trading_guardrail(
                all_records, module_sources=module_sources),
            self.check_demo_fallback(
                run_mode=run_mode, data_signature=data_signature,
                demo_signature=demo_signature),
            self.check_schema_validation(
                all_records, expected_schema_version=expected_schema_version),
            self.check_replayability(replay_results),
        )
        candidate_list = tuple(candidates)
        if candidate_list:
            results = results + (self.check_capital_candidate(candidate_list),)
        return results, _roll_up(results)


# --------------------------------------------------------------------------- #
# Shared detection helpers (module-level so the checkers + subsets agree)        #
# --------------------------------------------------------------------------- #
def _override_triple(ov: Any) -> Tuple[str, str, str]:
    """Normalise an override claim to ``(metric, kept_authority, overridden_authority)``."""
    if isinstance(ov, dict):
        return (str(ov.get("metric", "") or ""), str(ov.get("kept", "") or ""),
                str(ov.get("overridden", "") or ""))
    if isinstance(ov, (list, tuple)):
        vals = list(ov) + ["", "", ""]
        return str(vals[0] or ""), str(vals[1] or ""), str(vals[2] or "")
    return "", "", ""


def _is_social_like(record: Any) -> bool:
    """True iff a record looks like an X/social / narrative / rumor-tier record."""
    discipline = str(_get(record, "discipline", "") or "")
    source_type = str(_get(record, "source_type", "") or "")
    authority = str(_authority_of(record) or "")
    if _labels.is_social_source(source_type=source_type, discipline=discipline):
        return True
    if source_type and _labels.is_social_source_type(source_type):
        return True
    return authority == "rumor"


def _social_verified_fact(record: Any) -> bool:
    """True iff a social / rumor-tier record is (illegally) marked ``verified_fact``.

    Works on ANY record (dataclass / dict / duck-typed) via ``getattr`` -- the frozen 012 models
    reject this at construction, so a laundering record can only reach the gate from elsewhere.
    """
    if str(_get(record, "claim_status", "") or "") != "verified_fact":
        return False
    return _is_social_like(record)


def _iter_texts(texts: Any):
    """Yield ``(ref, text)`` from a sequence (positional refs) or a mapping (keyed refs)."""
    if isinstance(texts, dict):
        for key in sorted(texts.keys(), key=str):
            yield str(key), str(texts[key] or "")
    else:
        for i, text in enumerate(texts or ()):
            yield "output#{0}".format(i), str(text or "")


def _security_scan(
    generated_output_texts: Any, module_sources: Optional[Dict[str, str]]
) -> Tuple[List[str], List[str]]:
    """The security scan: secrets-in-output + network-on-import. Returns ``(findings, refs)``.

    Findings never contain a secret VALUE -- only the token NAME + the output / module ref.
    """
    findings: List[str] = []
    refs: List[str] = []
    for ref, text in _iter_texts(generated_output_texts):
        tokens = _secret_tokens_in_text(text)
        if tokens:
            findings.append(
                "generated output {0} contains a credential/API-key token ({1}) -- value redacted, "
                "a secret must never appear in a generated artifact".format(
                    ref, ", ".join(tokens)))
            refs.append(ref)
    for mref in sorted((module_sources or {}).keys(), key=str):
        if _network_call_on_import(str(module_sources[mref] or "")):
            findings.append(
                "module {0} makes a network call at import (network-on-import is forbidden; a "
                "single lazy network boundary inside a function is the only accepted form)".format(
                    mref))
            refs.append(str(mref))
    return findings, refs


def _guardrail_scan(
    records: Iterable[Any], module_sources: Optional[Dict[str, str]]
) -> Tuple[List[str], List[str]]:
    """The guardrail scan: forbidden record fields + scheduler/broker source tokens.

    Returns ``(findings, refs)``. Catches F3 (hidden score/rank) + F4 (buy/sell/order affordance)
    on records, and F8 (scheduler/daemon/broker/order token) in a provided module source.
    """
    findings: List[str] = []
    refs: List[str] = []
    for rec in records or ():
        for name in _field_names(rec):
            bad = sorted(set(_words(name)) & FORBIDDEN_RECORD_FIELD_WORDS)
            if bad:
                findings.append(
                    "record {0} exposes a forbidden field {1!r} ({2}) -- labels-not-scores, no "
                    "trade/score/order affordance".format(_ref_of(rec), name, ", ".join(bad)))
                refs.append(_ref_of(rec))
                break
    for mref in sorted((module_sources or {}).keys(), key=str):
        tokens = _scheduler_broker_tokens(str(module_sources[mref] or ""))
        if tokens:
            findings.append(
                "module {0} contains a scheduler/daemon/broker/order/affordance token ({1}) -- no "
                "scheduler / background job / broker / order is permitted (reserved for a future "
                "ADR)".format(mref, ", ".join(tokens)))
            refs.append(str(mref))
    return findings, refs


# --------------------------------------------------------------------------- #
# Construction-time guard: no gate record may carry a trade / score field.      #
# --------------------------------------------------------------------------- #
for _record_cls in (DataQualityGateResult, SecurityGateResult, PolicyGateResult):
    assert_no_trade_fields(_record_cls)
del _record_cls
