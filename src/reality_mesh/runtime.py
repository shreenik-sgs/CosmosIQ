"""Frozen, typed runtime objects for the manual/on-demand pulse (IMPLEMENTATION-013A).

The production runtime records specified in ``RUNTIME_CONTRACT_013.md`` -- the objects that
capture ONE manual pulse, one agent run, an agent's rolling health, and a deterministic replay.
Phase 013 makes the 012 substrate durable / replayable / observable; this slice is the frozen
typed layer those stores and harnesses will later persist and reconstruct.

INFRASTRUCTURE ONLY: typed contracts + closed vocabularies + validation + tests. There is NO
scheduler, NO daemon, NO streaming, NO 24x7 loop, NO broker, NO order, and NO buy/sell/order
affordance anywhere. In particular:

* **Manual-only trigger.** :attr:`PulseRun.trigger_type` accepts ``manual`` only; ``scheduled``
  and ``streaming`` are RESERVED/DEFERRED and are REJECTED at construction with a clear
  ``ValueError`` -- they are not permitted until Phase 015 (and then only behind a new ADR).
* **No broker, offline-by-default.** :class:`AgentRunContext` has NO ``broker_allowed`` field;
  ``network_allowed`` defaults ``False`` (and is False under the offline test suite). No order,
  affordance, or score is reachable from any runtime object.
* **Labels, not numbers.** Quality / state / status fields are QUALITATIVE labels from the closed
  vocabularies in :mod:`reality_mesh.labels`; integer fields are VOLUME counts (events created,
  failures, …), never an investability / score / rank / rating.
* **Failure isolated + missing explicit.** A failed/blocked agent yields a health record + a data
  gap, never a crashed run; collections default to empty tuples (an absent value is an explicit
  gap, never fabricated).

Deterministic, stdlib-only, Python 3.9. No network on import; no scheduler / broker; every
timestamp is an injected string (no wall-clock in any id / replay path).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Tuple

from . import labels as _labels
from .validation import assert_no_trade_fields

# Re-export the guard shape so the runtime uses the SAME structural check as the 012A substrate:
# no runtime object may carry a buy/sell/hold/order/trade/broker/score/rank/rating field.
__all__ = [
    "PulseRun",
    "AgentRunContext",
    "AgentRunResult",
    "AgentHealthRecord",
    "ReplayRequest",
    "ReplayResult",
    "RUNTIME_OBJECTS",
    "assert_no_trade_fields",
]


# --------------------------------------------------------------------------- #
# Shared validation (mirrors models.py; runtime-local so 012 stays untouched)   #
# --------------------------------------------------------------------------- #
# field name -> its closed SCALAR vocabulary (a "" gap is always accepted).
_RUNTIME_SCALAR_VOCAB = {
    "mode": _labels.RUN_MODES,
    "data_quality_status": _labels.RUN_STATUSES,
    "status": _labels.AGENT_RUN_STATUSES,
    "last_status": _labels.AGENT_RUN_STATUSES,
    "health_status": _labels.HEALTH_STATES,
}

# field name -> the closed vocabulary EACH element of a tuple-of-label field must belong to.
_RUNTIME_TUPLE_VOCAB = {
    "allowed_sources": _labels.SOURCE_AUTHORITIES,
    "forbidden_outputs": _labels.FORBIDDEN_DOWNSTREAM_USES,
}


def _require_ids(obj, names: Tuple[str, ...]) -> None:
    """Raise ValueError if any named required-id field is empty/blank."""
    for name in names:
        value = getattr(obj, name, "")
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(
                "{0}.{1} is a required id and must be non-empty".format(
                    type(obj).__name__, name))


def _validate_labels(obj) -> None:
    """Validate every closed-label field of ``obj`` against its vocabulary (scalar + tuple)."""
    for f in fields(obj):
        value = getattr(obj, f.name)
        if f.name in _RUNTIME_SCALAR_VOCAB:
            vocab = _RUNTIME_SCALAR_VOCAB[f.name]
            if not _labels.is_member(vocab, value):
                raise ValueError(
                    "{0}.{1}: invalid label {2!r} (allowed: {3})".format(
                        type(obj).__name__, f.name, value, sorted(vocab)))
        elif f.name in _RUNTIME_TUPLE_VOCAB:
            vocab = _RUNTIME_TUPLE_VOCAB[f.name]
            for element in value:
                if element not in vocab:
                    raise ValueError(
                        "{0}.{1}: invalid label {2!r} (allowed: {3})".format(
                            type(obj).__name__, f.name, element, sorted(vocab)))


def _validate_trigger_type(obj) -> None:
    """Enforce the manual-only trigger rule (RUNTIME_CONTRACT_013 §1).

    ``manual`` (or the "" gap sentinel) is accepted; ``scheduled`` / ``streaming`` are
    RESERVED and rejected with an explicit message; any other value is an invalid label.
    """
    value = getattr(obj, "trigger_type", "")
    if _labels.is_reserved_trigger_type(value):
        raise ValueError(
            "{0}.trigger_type {1!r} is RESERVED/DEFERRED and rejected in Phase 013 -- only "
            "'manual' is permitted (scheduled/streaming require Phase 015 + a new ADR)".format(
                type(obj).__name__, value))
    if not _labels.is_member(_labels.ALLOWED_TRIGGER_TYPES, value):
        raise ValueError(
            "{0}.trigger_type: invalid value {1!r} (allowed: {2})".format(
                type(obj).__name__, value, sorted(_labels.ALLOWED_TRIGGER_TYPES)))


# --------------------------------------------------------------------------- #
# 1. PulseRun -- one manual pulse (the top-level run record)                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PulseRun:
    """The record of ONE manual pulse. Counts are VOLUMES, never scores; trigger is manual-only."""
    run_id: str = ""
    started_at: str = ""                    # injected timestamp (no wall-clock)
    completed_at: str = ""                  # injected timestamp
    mode: str = "demo"                      # closed: RUN_MODES (demo stays the DEFAULT)
    trigger_type: str = "manual"            # manual ONLY; scheduled/streaming REJECTED
    watchlist: Tuple[str, ...] = field(default_factory=tuple)
    themes: Tuple[str, ...] = field(default_factory=tuple)
    source_adapters_requested: Tuple[str, ...] = field(default_factory=tuple)
    source_adapters_used: Tuple[str, ...] = field(default_factory=tuple)
    agents_requested: Tuple[str, ...] = field(default_factory=tuple)
    agents_run: Tuple[str, ...] = field(default_factory=tuple)
    agents_failed: Tuple[str, ...] = field(default_factory=tuple)
    events_created: int = 0                 # volume count (NOT a score)
    findings_created: int = 0               # volume count
    signals_created: int = 0                # volume count
    theme_pulses_created: int = 0           # volume count
    data_quality_status: str = ""           # closed: RUN_STATUSES
    generated_outputs: Tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = ""
    runtime_version: str = ""

    def __post_init__(self) -> None:
        _require_ids(self, ("run_id",))
        _validate_trigger_type(self)
        _validate_labels(self)


# --------------------------------------------------------------------------- #
# 2. AgentRunContext -- what one agent is handed for one run                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentRunContext:
    """The bounded context handed to one agent. Offline by default; NO broker affordance.

    ``forbidden_outputs`` ALWAYS includes the four default-forbidden uses
    (``broker_order`` / ``auto_execute`` / ``buy_sell_recommendation`` / ``hidden_score``);
    they are merged in on construction so a context can never omit them. There is NO
    ``broker_allowed`` field, and ``network_allowed`` defaults ``False``.
    """
    run_id: str = ""
    agent_id: str = ""
    mode: str = "demo"                      # closed: RUN_MODES (inherited pulse mode)
    watchlist: Tuple[str, ...] = field(default_factory=tuple)
    themes: Tuple[str, ...] = field(default_factory=tuple)
    input_event_ids: Tuple[str, ...] = field(default_factory=tuple)
    allowed_sources: Tuple[str, ...] = field(default_factory=tuple)   # closed: SOURCE_AUTHORITIES
    forbidden_outputs: Tuple[str, ...] = field(
        default_factory=lambda: tuple(sorted(_labels.DEFAULT_FORBIDDEN_DOWNSTREAM_USES)))
    started_at: str = ""                    # injected timestamp
    timeout_policy: str = ""                # soft budget; a timeout is recorded, never a crash
    fixture_mode: bool = True               # true -> fixtures only (offline-first default)
    network_allowed: bool = False           # MUST be False under the offline test suite

    def __post_init__(self) -> None:
        _require_ids(self, ("run_id", "agent_id"))
        # Merge in the mandatory default-forbidden outputs (order-stable, deduped).
        merged = list(self.forbidden_outputs)
        for use in sorted(_labels.DEFAULT_FORBIDDEN_DOWNSTREAM_USES):
            if use not in merged:
                merged.append(use)
        object.__setattr__(self, "forbidden_outputs", tuple(merged))
        _validate_labels(self)


# --------------------------------------------------------------------------- #
# 3. AgentRunResult -- the outcome of one agent run                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentRunResult:
    """The outcome of one agent run. A failed/blocked result never crashes the pulse."""
    run_id: str = ""
    agent_id: str = ""
    status: str = ""                        # closed: AGENT_RUN_STATUSES
    started_at: str = ""                    # injected timestamp
    completed_at: str = ""                  # injected timestamp
    input_event_ids: Tuple[str, ...] = field(default_factory=tuple)
    finding_ids: Tuple[str, ...] = field(default_factory=tuple)
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    errors: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    health_status: str = ""                 # closed: HEALTH_STATES

    def __post_init__(self) -> None:
        _require_ids(self, ("run_id", "agent_id"))
        _validate_labels(self)


# --------------------------------------------------------------------------- #
# 4. AgentHealthRecord -- rolling health for one agent                         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentHealthRecord:
    """Rolling per-agent health. ``failure_count`` is a volume count, never a score."""
    agent_id: str = ""
    last_run_id: str = ""
    last_status: str = ""                   # closed: AGENT_RUN_STATUSES
    failure_count: int = 0                  # volume count (NOT a score)
    last_error: str = ""                    # last error note (no secrets)
    last_success_at: str = ""               # injected timestamp
    last_failure_at: str = ""               # injected timestamp
    degraded_reason: str = ""

    def __post_init__(self) -> None:
        _require_ids(self, ("agent_id",))
        _validate_labels(self)


# --------------------------------------------------------------------------- #
# 5. ReplayRequest -- ask to reconstruct a past run                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReplayRequest:
    """A request to reconstruct a past run by run / ticker / theme / time-window."""
    run_id: str = ""                        # optional if querying by ticker/theme/window
    ticker: str = ""
    theme: str = ""
    time_window: Tuple[str, ...] = field(default_factory=tuple)   # (from, to) ISO strings
    source_filter: Tuple[str, ...] = field(default_factory=tuple)
    agent_filter: Tuple[str, ...] = field(default_factory=tuple)
    include_raw_payloads: bool = False
    include_generated_outputs: bool = False

    def __post_init__(self) -> None:
        # run_id is optional, but a replay MUST be scoped by at least one filter.
        scoped = (self.run_id.strip() or self.ticker.strip() or self.theme.strip()
                  or bool(self.time_window))
        if not scoped:
            raise ValueError(
                "ReplayRequest must be scoped by at least one of run_id / ticker / theme / "
                "time_window (an unscoped replay is rejected)")


# --------------------------------------------------------------------------- #
# 6. ReplayResult -- what a replay produced                                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReplayResult:
    """What a replay reconstructed. ``deterministic_match`` is True for a clean deterministic replay."""
    replay_id: str = ""
    source_run_id: str = ""
    events_replayed: int = 0                # volume count
    findings_replayed: int = 0              # volume count
    signals_replayed: int = 0               # volume count
    outputs_reconstructed: Tuple[str, ...] = field(default_factory=tuple)
    differences: Tuple[str, ...] = field(default_factory=tuple)
    deterministic_match: bool = False

    def __post_init__(self) -> None:
        _require_ids(self, ("replay_id", "source_run_id"))


# The six runtime objects (for registry / test introspection).
RUNTIME_OBJECTS = (
    PulseRun,
    AgentRunContext,
    AgentRunResult,
    AgentHealthRecord,
    ReplayRequest,
    ReplayResult,
)
