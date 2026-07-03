"""The source-adapter runtime for the Reality Mesh (IMPLEMENTATION-014A).

Implements the production source-adapter interface specified in
``SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md``: a frozen, self-validating
:class:`SourceAdapterDescriptor` (what a source is, what it needs, what it emits), a frozen
:class:`SourceAdapterResult` (what one fetch delivered -- and, honestly, what it did not), and
the :class:`SourceAdapter` ABC whose :meth:`SourceAdapter.fetch_checked` wrapper enforces the
contract at the boundary.

THE CONTRACT, baked into the shape (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1-§3):

* **Adapters emit RealityEvents ONLY** -- never an ``AgentFinding``. A source OBSERVES; it does
  not interpret. ``fetch_checked`` rejects any non-``RealityEvent`` output with ``ValueError``.
* **Source authority is explicit and assigned immediately.** Every descriptor declares its
  authority tier; every emitted event must carry a non-empty ``source_authority``.
* **Raw payload refs preserved.** Every emitted event must carry a non-empty
  ``raw_payload_ref`` (a pointer, never an inlined payload) plus evidence/source refs.
* **Source failure becomes a GAP** -- an exception inside ``fetch_events`` is caught and turned
  into a ``failed`` :class:`SourceAdapterResult` with an explicit ``data_gaps`` entry. It NEVER
  propagates, NEVER fabricates a value, and NEVER falls back silently to demo data.
* **Credentials are env-only presence labels.** ``credential_requirements`` holds env var
  NAMES only (validated as such -- a value-looking string is rejected); a result carries a
  ``credentials_status`` LABEL (``present`` / ``missing`` / ``not_required``), never a value.
* **NO production network path in this slice.** ``network_required=True`` adapters are the
  LAST onboarding stage (§4 stage 6); ``fetch_checked`` refuses to run one here, returning a
  ``skipped`` result with a visible gap. Everything in this module is OFFLINE.
* **Labels + volume counts only.** No trade / broker / order / score / rank / rating field
  exists on any object here (``assert_no_trade_fields`` enforced at class definition).

Deterministic, stdlib-only, Python 3.9. No network on import; no scheduler / broker; ``now``
is an injected string (no wall-clock in any id path).
"""

from __future__ import annotations

import abc
import hashlib
import re
from dataclasses import dataclass, field
from typing import FrozenSet, Iterable, Tuple

from .. import labels as _labels
from ..agents import FORBIDDEN_EMIT_TOKENS
from ..health import SourceHealthRecord
from ..models import RealityEvent
from ..validation import assert_no_trade_fields

__all__ = [
    "ADAPTER_RESULT_STATUSES",
    "ADAPTER_CREDENTIALS_STATUSES",
    "ADAPTER_RATE_LIMIT_STATUSES",
    "ADAPTER_FAILURE_MODES",
    "ADAPTER_SOURCE_HEALTH_LABELS",
    "SourceAdapterDescriptor",
    "SourceAdapterResult",
    "SourceAdapter",
    "deterministic_adapter_run_id",
    "source_health_from_result",
]

# --------------------------------------------------------------------------- #
# Closed vocabularies (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1/§2)            #
# --------------------------------------------------------------------------- #

# The four allowed outcomes of one adapter fetch (§2). A failed fetch is a RESULT + a gap,
# never a crash and never a fabricated event stream.
ADAPTER_RESULT_STATUSES: FrozenSet[str] = frozenset(
    {"success", "partial", "failed", "skipped"})

# Presence LABELS only -- never a credential value (§2/§3). ``not_required`` is the honest
# label for a local-file source that needs no credential at all (this slice needs NONE).
ADAPTER_CREDENTIALS_STATUSES: FrozenSet[str] = frozenset(
    {"present", "missing", "not_required"})

# How the source's rate limit stood after the fetch (§2). A local filesystem read is ``ok``
# by construction -- it cannot be throttled.
ADAPTER_RATE_LIMIT_STATUSES: FrozenSet[str] = frozenset(
    {"ok", "throttled", "exhausted"})

# The declared failure modes an adapter may exhibit (§1). Each becomes a VISIBLE gap/health
# record when it occurs -- never a crash, never an invented value.
ADAPTER_FAILURE_MODES: FrozenSet[str] = frozenset(
    {"credentials_missing", "rate_limited", "source_unavailable", "parse_error"})

# Source-health labels a result may carry (§2). A strict subset of the 013D HEALTH_STATES so
# a SourceAdapterResult maps 1:1 onto a real SourceHealthRecord.last_status.
ADAPTER_SOURCE_HEALTH_LABELS: FrozenSet[str] = frozenset(
    {"healthy", "degraded", "failed", "rate_limited", "source_unavailable",
     "credentials_missing"})
assert ADAPTER_SOURCE_HEALTH_LABELS <= _labels.HEALTH_STATES

# An env var NAME (never a value): uppercase, digits, underscores. Anything value-looking
# (an "=", a space, lowercase, a token that IS a secret) is rejected at construction.
_ENV_VAR_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# result.status -> the health label used when a result carries no explicit source_health.
_STATUS_TO_HEALTH = {
    "success": "healthy",
    "partial": "degraded",
    "failed": "failed",
    "skipped": "source_unavailable",
}


def _require_ids(obj, names: Tuple[str, ...]) -> None:
    for name in names:
        value = getattr(obj, name, "")
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(
                "{0}.{1} is a required id and must be non-empty".format(
                    type(obj).__name__, name))


def _require_member(obj, field_name: str, vocab: FrozenSet[str]) -> None:
    value = getattr(obj, field_name, "")
    if value not in vocab:
        raise ValueError(
            "{0}.{1}: invalid label {2!r} (allowed: {3})".format(
                type(obj).__name__, field_name, value, sorted(vocab)))


def _require_str_tuple(obj, field_name: str) -> None:
    value = getattr(obj, field_name, ())
    for element in value:
        if not isinstance(element, str) or element.strip() == "":
            raise ValueError(
                "{0}.{1}: every element must be a non-empty string".format(
                    type(obj).__name__, field_name))


# --------------------------------------------------------------------------- #
# 1. SourceAdapterDescriptor (§1)                                              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceAdapterDescriptor:
    """A frozen, self-validating declaration of one source adapter.

    Validated on construction: non-empty ids; ``source_authority`` is a NON-EMPTY member of the
    reused authority ladder (authority is assigned immediately, never deferred);
    ``credential_requirements`` holds env var NAMES only (a value-looking string is rejected);
    ``network_required`` is a real bool; ``outputs`` (the RealityEvent event_types produced)
    are non-empty and carry no trade / score token; ``claim_status_rules`` state how each
    output is stamped; ``failure_modes`` draw from the closed §1 set. Label-only: no trade /
    score field exists (asserted at class definition below).
    """

    adapter_id: str = ""
    source_name: str = ""
    source_type: str = ""                   # e.g. "market_data" / "filing" / "social"
    source_authority: str = ""              # closed: SOURCE_AUTHORITIES (non-empty required)
    credential_requirements: Tuple[str, ...] = field(default_factory=tuple)  # env var NAMES
    network_required: bool = False          # True only at onboarding stage 6 (NOT this slice)
    rate_limit_policy: str = ""             # how the adapter self-limits (a label/description)
    outputs: Tuple[str, ...] = field(default_factory=tuple)         # RealityEvent event_types
    claim_status_rules: Tuple[str, ...] = field(default_factory=tuple)
    failure_modes: Tuple[str, ...] = field(default_factory=tuple)   # closed: ADAPTER_FAILURE_MODES
    description: str = ""

    def __post_init__(self) -> None:
        _require_ids(self, ("adapter_id", "source_name", "source_type", "rate_limit_policy"))
        # Authority is explicit and assigned immediately -- an empty gap is NOT allowed here.
        if self.source_authority not in _labels.SOURCE_AUTHORITIES:
            raise ValueError(
                "SourceAdapterDescriptor.source_authority {0!r} must be a non-empty member of "
                "the authority ladder (allowed: {1})".format(
                    self.source_authority, sorted(_labels.SOURCE_AUTHORITIES)))
        # Env var NAMES only -- never a value. A "=", space, lowercase, or empty entry is a
        # value-shaped leak risk and is rejected.
        for name in self.credential_requirements:
            if not isinstance(name, str) or not _ENV_VAR_NAME_RE.match(name or ""):
                raise ValueError(
                    "SourceAdapterDescriptor.credential_requirements must hold env var NAMES "
                    "only (UPPER_SNAKE_CASE), got {0!r} -- never a credential value".format(name))
        if not isinstance(self.network_required, bool):
            raise ValueError(
                "SourceAdapterDescriptor.network_required must be a bool, got {0!r}".format(
                    self.network_required))
        if not self.outputs:
            raise ValueError(
                "SourceAdapterDescriptor.outputs must declare at least one RealityEvent "
                "event_type")
        _require_str_tuple(self, "outputs")
        for out in self.outputs:
            low = out.lower()
            for token in FORBIDDEN_EMIT_TOKENS:
                if token in low:
                    raise ValueError(
                        "SourceAdapterDescriptor {0}: forbidden output {1!r} (trade/score "
                        "token {2!r} not permitted)".format(self.adapter_id, out, token))
        if not self.claim_status_rules:
            raise ValueError(
                "SourceAdapterDescriptor.claim_status_rules must state how each output's "
                "claim_status is stamped (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §3)")
        _require_str_tuple(self, "claim_status_rules")
        for mode in self.failure_modes:
            if mode not in ADAPTER_FAILURE_MODES:
                raise ValueError(
                    "SourceAdapterDescriptor.failure_modes: {0!r} is not a closed failure "
                    "mode (allowed: {1})".format(mode, sorted(ADAPTER_FAILURE_MODES)))


# --------------------------------------------------------------------------- #
# 2. SourceAdapterResult (§2)                                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceAdapterResult:
    """What ONE adapter fetch delivered -- and, honestly, what it did not.

    ``raw_payload_refs`` are POINTERS into raw storage (never inlined payloads);
    ``events_created`` is a volume count (never a score); ``credentials_status`` /
    ``rate_limit_status`` / ``source_health`` are closed LABELS (a credential value never
    appears anywhere); ``data_gaps`` makes every source failure a VISIBLE gap. Label-only:
    no trade / score field exists (asserted at class definition below).
    """

    adapter_id: str = ""
    run_id: str = ""
    status: str = ""                        # closed: ADAPTER_RESULT_STATUSES
    raw_payload_refs: Tuple[str, ...] = field(default_factory=tuple)
    events_created: int = 0                 # volume count, never a score
    warnings: Tuple[str, ...] = field(default_factory=tuple)    # non-fatal (no secrets)
    errors: Tuple[str, ...] = field(default_factory=tuple)      # fatal (no secrets)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)   # failure -> VISIBLE gap (§3)
    credentials_status: str = ""            # closed: ADAPTER_CREDENTIALS_STATUSES (label only)
    rate_limit_status: str = ""             # closed: ADAPTER_RATE_LIMIT_STATUSES
    source_health: str = ""                 # closed: ADAPTER_SOURCE_HEALTH_LABELS

    def __post_init__(self) -> None:
        _require_ids(self, ("adapter_id", "run_id"))
        _require_member(self, "status", ADAPTER_RESULT_STATUSES)
        _require_member(self, "credentials_status", ADAPTER_CREDENTIALS_STATUSES)
        _require_member(self, "rate_limit_status", ADAPTER_RATE_LIMIT_STATUSES)
        _require_member(self, "source_health", ADAPTER_SOURCE_HEALTH_LABELS)
        _require_str_tuple(self, "raw_payload_refs")
        _require_str_tuple(self, "warnings")
        _require_str_tuple(self, "errors")
        _require_str_tuple(self, "data_gaps")
        if isinstance(self.events_created, bool) or not isinstance(self.events_created, int):
            raise ValueError("SourceAdapterResult.events_created must be an int volume count")
        if self.events_created < 0:
            raise ValueError("SourceAdapterResult.events_created must be >= 0")
        # A failed / skipped fetch must be VISIBLE: at least one error or gap explains it.
        if self.status in ("failed", "skipped") and not (self.errors or self.data_gaps):
            raise ValueError(
                "SourceAdapterResult: a {0!r} result must carry an explicit error or data gap "
                "(source failure becomes a gap -- never silent)".format(self.status))


# Construction-time guard: neither contract object may ever grow a trade / score field.
assert_no_trade_fields(SourceAdapterDescriptor)
assert_no_trade_fields(SourceAdapterResult)


# --------------------------------------------------------------------------- #
# Deterministic run ids (content-derived; no wall-clock)                        #
# --------------------------------------------------------------------------- #
def deterministic_adapter_run_id(adapter_id: str, parts: Iterable[str]) -> str:
    """A content-derived adapter run id: ``adapterrun.<adapter_id>.<sha256-prefix>``.

    Deterministic: the digest is computed from ``adapter_id`` plus the given parts (e.g. the
    injected ``now`` and the raw payload refs) -- the same inputs always yield the same id.
    """
    digest = hashlib.sha256(
        "|".join([adapter_id] + [str(p) for p in parts]).encode("utf-8")).hexdigest()[:12]
    return "adapterrun.{0}.{1}".format(adapter_id, digest)


# --------------------------------------------------------------------------- #
# 3. SourceAdapter ABC + the boundary-enforcing fetch_checked wrapper           #
# --------------------------------------------------------------------------- #
class SourceAdapter(abc.ABC):
    """The abstract interface every source adapter implements.

    An adapter OBSERVES a source: it fetches raw payloads and emits :class:`RealityEvent`s
    ONLY (never an ``AgentFinding`` -- it does not interpret). Subclasses provide
    :attr:`descriptor` and a deterministic :meth:`fetch_events`; :meth:`fetch_checked`
    enforces the SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 boundary at runtime.
    """

    @property
    @abc.abstractmethod
    def descriptor(self) -> SourceAdapterDescriptor:
        """The adapter's frozen :class:`SourceAdapterDescriptor`."""

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        """The closed disciplines this adapter is the source for (may be empty).

        When an adapter covers a discipline, a consumer (e.g. ``run_pulse``) must take that
        discipline's events from the adapter ONLY -- a failed source stays a VISIBLE gap and
        is never silently backfilled from demo fixtures.
        """
        return ()

    @abc.abstractmethod
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], "SourceAdapterResult"]:
        """Fetch this source and return ``(events, result)``. Deterministic; ``now`` injected."""

    # -- boundary-enforcing wrapper ---------------------------------------- #
    def fetch_checked(self, *, watchlist=(), themes=(),
                      now: str = "") -> Tuple[Tuple[RealityEvent, ...], "SourceAdapterResult"]:
        """Fetch with the SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 boundary enforced.

        (a) a ``network_required`` adapter is REFUSED in this slice (onboarding stage 6 is the
        production network path -- it does not exist yet): a ``skipped`` result with a visible
        gap, never a fetch; (b) an exception inside :meth:`fetch_events` becomes a ``failed``
        result + an explicit data gap -- it NEVER propagates and nothing is fabricated; (c)
        every output must be a :class:`RealityEvent` (an ``AgentFinding`` or anything else is
        rejected with ``ValueError``) carrying a non-empty ``source_authority``, a non-empty
        ``raw_payload_ref``, and at least one evidence/source ref; (d) the returned result
        must be a consistent :class:`SourceAdapterResult` for this adapter.
        """
        desc = self.descriptor
        if not isinstance(desc, SourceAdapterDescriptor):
            raise TypeError(
                "SourceAdapter.descriptor must be a SourceAdapterDescriptor, got {0}".format(
                    type(desc).__name__))

        # (a) NO production network path in this slice (contract §4: stage 6 is LAST).
        if desc.network_required:
            gap = ("adapter {0} requires a network path -- the production network path is the "
                   "LAST onboarding stage (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §4) and does "
                   "not exist in this slice: fetch refused, visible gap, nothing "
                   "fabricated".format(desc.adapter_id))
            return (), SourceAdapterResult(
                adapter_id=desc.adapter_id,
                run_id=deterministic_adapter_run_id(desc.adapter_id, (now, "network_refused")),
                status="skipped",
                events_created=0,
                errors=("network_refused: no production network path exists in this slice",),
                data_gaps=(gap,),
                credentials_status=("not_required" if not desc.credential_requirements
                                    else "missing"),
                rate_limit_status="ok",
                source_health="source_unavailable")

        # (b) source failure -> a failed result + a visible gap. NEVER a crash upward,
        # NEVER a fabricated value, NEVER a silent demo fallback.
        try:
            events, result = self.fetch_events(
                watchlist=watchlist, themes=themes, now=now)
        except Exception as exc:  # noqa: BLE001 -- the contract demands never-propagate
            reason = "{0}: {1}".format(type(exc).__name__, exc)
            gap = ("source {0} ({1}) failed: {2} -- visible gap, never a fabricated value, "
                   "never a silent demo fallback".format(
                       desc.adapter_id, desc.source_name, reason))
            return (), SourceAdapterResult(
                adapter_id=desc.adapter_id,
                run_id=deterministic_adapter_run_id(desc.adapter_id, (now, "source_failure")),
                status="failed",
                events_created=0,
                errors=("source_failure: {0}".format(reason),),
                data_gaps=(gap,),
                credentials_status=("not_required" if not desc.credential_requirements
                                    else "missing"),
                rate_limit_status="ok",
                source_health="failed")

        # (c) outputs are RealityEvents ONLY, each with authority + raw ref + refs.
        events = tuple(events)
        for out in events:
            if not isinstance(out, RealityEvent):
                raise ValueError(
                    "{0}: a source adapter may emit RealityEvent ONLY (it observes, it does "
                    "not interpret), got {1}".format(desc.adapter_id, type(out).__name__))
            assert_no_trade_fields(out)
            if not out.source_authority:
                raise ValueError(
                    "{0}: event {1!r} has no source_authority -- authority is explicit and "
                    "assigned immediately".format(desc.adapter_id, out.event_id))
            if not out.raw_payload_ref:
                raise ValueError(
                    "{0}: event {1!r} has no raw_payload_ref -- raw payloads are captured "
                    "before interpretation".format(desc.adapter_id, out.event_id))
            if not (out.evidence_refs or out.source_refs):
                raise ValueError(
                    "{0}: event {1!r} carries no evidence/source refs -- provenance may "
                    "never be bypassed".format(desc.adapter_id, out.event_id))

        # (d) the result must be a consistent SourceAdapterResult for THIS adapter.
        if not isinstance(result, SourceAdapterResult):
            raise ValueError(
                "{0}: fetch_events must return a SourceAdapterResult, got {1}".format(
                    desc.adapter_id, type(result).__name__))
        if result.adapter_id != desc.adapter_id:
            raise ValueError(
                "{0}: result.adapter_id {1!r} does not match the descriptor".format(
                    desc.adapter_id, result.adapter_id))
        if result.events_created != len(events):
            raise ValueError(
                "{0}: result.events_created={1} but {2} event(s) were returned -- counts are "
                "honest volumes".format(desc.adapter_id, result.events_created, len(events)))
        return events, result


# --------------------------------------------------------------------------- #
# SourceAdapterResult -> a real 013D SourceHealthRecord                         #
# --------------------------------------------------------------------------- #
def source_health_from_result(result: SourceAdapterResult, *,
                              now: str = "") -> SourceHealthRecord:
    """Map ONE :class:`SourceAdapterResult` onto a real 013D :class:`SourceHealthRecord`.

    The bridge into the observability surface: ``source_health`` (already a HEALTH_STATES
    member) becomes ``last_status``; the ``not_required`` credentials label maps to the ``""``
    explicit-gap sentinel (a local file needs no credential -- presence is never fabricated);
    ``throttled`` / ``exhausted`` roll to ``rate_limited``; the first error/gap becomes the
    visible ``unavailable_reason``. Deterministic; ``now`` is injected.
    """
    if not isinstance(result, SourceAdapterResult):
        raise TypeError("source_health_from_result expects a SourceAdapterResult")
    last_status = result.source_health or _STATUS_TO_HEALTH[result.status]
    credentials = {"present": "present", "missing": "missing", "not_required": ""}.get(
        result.credentials_status, "unknown")
    rate = "ok" if result.rate_limit_status == "ok" else "rate_limited"
    delivered = result.status in ("success", "partial")
    reason = ""
    if last_status != "healthy":
        explanation = result.errors + result.data_gaps + result.warnings
        reason = (explanation[0] if explanation else
                  "source {0} is {1} -- visible gap, nothing fabricated".format(
                      result.adapter_id, last_status))
    return SourceHealthRecord(
        source_id=result.adapter_id,
        last_status=last_status,
        credentials_status=credentials,
        rate_limit_status=rate,
        last_success_at=now if delivered else "",
        last_failure_at=now if result.status in ("failed", "skipped") else "",
        unavailable_reason=reason)
