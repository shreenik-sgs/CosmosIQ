"""Health + Data-Quality observability records and the AgentHealthMonitor (IMPLEMENTATION-013D).

The observability outputs specified in ``OBSERVABILITY_CONTRACT_013.md`` §2/§3. Everything here is
**labels + volume counts, never a score / rank / rating**, and it is resilient by construction: a
degraded / partial run STILL rolls up into a :class:`RunHealthSummary` + a
:class:`DataQualityRunSummary` (honestly labelled ``degraded``), never a silent demo fallback and
never a fabricated value.

Three frozen records join the 013A :class:`~reality_mesh.runtime.AgentHealthRecord`:

* :class:`SourceHealthRecord` -- per-source last status / credentials / rate-limit / unavailable
  reason (a failed source is a VISIBLE gap, never a fabricated value);
* :class:`RunHealthSummary` -- the per-run roll-up (agents run / failed / blocked / skipped, sources
  used / failed, data-gap + conflict counts, an overall health state);
* :class:`DataQualityRunSummary` -- the per-run Data-Quality roll-up (source coverage, gaps,
  conflicts, weak-social + unsupported-claim counts, status) that feeds the Data-Quality surface.

:class:`AgentHealthMonitor` rolls a sequence of :class:`~reality_mesh.runtime.AgentRunResult`s into
:class:`~reality_mesh.runtime.AgentHealthRecord`s and builds the two run-level summaries from a run's
results / sources / signals / gaps.

Deterministic, stdlib-only, Python 3.9. No network / scheduler / broker; ``*_at`` timestamps are
injected strings (no wall-clock); the records reuse
:func:`~reality_mesh.validation.assert_no_trade_fields` so none can grow a trade / score field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Tuple

from . import labels as _labels
from .runtime import AgentHealthRecord, AgentRunResult
from .validation import assert_no_trade_fields

__all__ = [
    "CREDENTIALS_STATUSES",
    "RATE_LIMIT_STATUSES",
    "SourceHealthRecord",
    "RunHealthSummary",
    "DataQualityRunSummary",
    "AgentHealthMonitor",
    "HEALTH_RECORDS",
]

# Small closed vocabularies for a source's credential / rate-limit status (the "" gap is allowed).
CREDENTIALS_STATUSES = frozenset({"present", "missing", "unknown"})
RATE_LIMIT_STATUSES = frozenset({"ok", "rate_limited", "unknown"})


def _require_ids(obj, names: Tuple[str, ...]) -> None:
    for name in names:
        value = getattr(obj, name, "")
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(
                "{0}.{1} is a required id and must be non-empty".format(
                    type(obj).__name__, name))


def _require_label(obj, field_name: str, vocab) -> None:
    value = getattr(obj, field_name, "")
    if not _labels.is_member(vocab, value):
        raise ValueError(
            "{0}.{1}: invalid label {2!r} (allowed: {3})".format(
                type(obj).__name__, field_name, value, sorted(vocab)))


# --------------------------------------------------------------------------- #
# 1. SourceHealthRecord -- per-source health (a failed source is a visible gap) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceHealthRecord:
    """Per-source health: last status + credentials / rate-limit + last success/failure + reason.

    A source that could not deliver (``credentials_missing`` / ``rate_limited`` /
    ``source_unavailable``) becomes a VISIBLE gap via ``unavailable_reason`` -- never a fabricated
    value. Labels only: no score / rank field exists here.
    """

    source_id: str = ""
    last_status: str = ""                   # closed: HEALTH_STATES
    credentials_status: str = ""            # closed: CREDENTIALS_STATUSES
    rate_limit_status: str = ""             # closed: RATE_LIMIT_STATUSES
    last_success_at: str = ""               # injected timestamp
    last_failure_at: str = ""               # injected timestamp
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        _require_ids(self, ("source_id",))
        _require_label(self, "last_status", _labels.HEALTH_STATES)
        _require_label(self, "credentials_status", CREDENTIALS_STATUSES)
        _require_label(self, "rate_limit_status", RATE_LIMIT_STATUSES)

    @property
    def is_failed(self) -> bool:
        """True iff the source is in a non-healthy delivery state (failed / unavailable / blocked)."""
        return self.last_status in (
            "failed", "source_unavailable", "credentials_missing", "rate_limited")


# --------------------------------------------------------------------------- #
# 2. RunHealthSummary -- the per-run roll-up (counts + an overall state)         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RunHealthSummary:
    """Per-run roll-up: agent coverage / failures / blocks, source coverage, gaps, conflicts, state.

    Every integer is a VOLUME count (agents run, failures, gaps, …), never a score. ``overall_status``
    is an honest label from ``RUN_STATUSES`` -- a partial run reads ``degraded`` (surfaced, not hidden).
    """

    run_id: str = ""
    agents_total: int = 0
    agents_run: int = 0                     # successes (volume count)
    agents_failed: int = 0                  # volume count
    agents_blocked: int = 0                 # volume count (blocked_by_policy)
    agents_skipped: int = 0                 # volume count
    sources_used: int = 0                   # volume count
    sources_failed: int = 0                 # volume count
    data_gap_count: int = 0                 # volume count
    conflict_count: int = 0                 # volume count
    overall_status: str = ""                # closed: RUN_STATUSES
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_ids(self, ("run_id",))
        _require_label(self, "overall_status", _labels.RUN_STATUSES)


# --------------------------------------------------------------------------- #
# 3. DataQualityRunSummary -- the per-run Data-Quality roll-up                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DataQualityRunSummary:
    """Per-run Data-Quality roll-up: coverage, gaps, conflicts, weak-social, unsupported claims.

    Produced for EVERY run, even a degraded / partial one (``status="degraded"`` -- honestly
    labelled, never a silent demo fallback). A high gap / weak-social count is information, not a
    defect. Counts are volumes; ``source_coverage`` is a qualitative label; no score / rank exists.
    """

    run_id: str = ""
    sources_used: int = 0                   # volume count
    sources_failed: int = 0                 # volume count
    source_coverage: str = ""               # qualitative: full / partial / none / unknown
    gap_count: int = 0                      # volume count
    conflict_count: int = 0                 # volume count
    weak_social_count: int = 0              # volume count (rumor-tier signals -- weak by design)
    unsupported_claim_count: int = 0        # volume count
    status: str = ""                        # closed: RUN_STATUSES
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_ids(self, ("run_id",))
        _require_label(self, "status", _labels.RUN_STATUSES)


# The three new health records (for registry / test introspection).
HEALTH_RECORDS = (
    SourceHealthRecord,
    RunHealthSummary,
    DataQualityRunSummary,
)


# --------------------------------------------------------------------------- #
# Overall-status logic (shared by both roll-ups)                                #
# --------------------------------------------------------------------------- #
def _overall_status(successes: int, failures: int, blocked: int) -> str:
    """Map success / failure / block counts to an honest RUN_STATUSES label.

    healthy (nothing failed/blocked) · degraded (some worked, some did not -- partial) ·
    blocked_by_policy (nothing failed, everything that did not succeed was policy-blocked) ·
    failed (there were failures and NOTHING succeeded).
    """
    if failures == 0 and blocked == 0:
        return "healthy"
    if successes > 0:
        return "degraded"
    if failures == 0 and blocked > 0:
        return "blocked_by_policy"
    return "failed"


def _coverage_label(sources_used: int, sources_failed: int) -> str:
    """A qualitative source-coverage label (never a score).

    ``sources_used`` is the number of sources ATTEMPTED; ``sources_failed`` how many could not
    deliver. full (none failed) · none (every attempted source failed) · partial (some delivered).
    """
    if sources_used == 0:
        return "unknown"
    if sources_failed == 0:
        return "full"
    if sources_failed >= sources_used:
        return "none"
    return "partial"


# --------------------------------------------------------------------------- #
# AgentHealthMonitor -- roll results into health records + the run summaries     #
# --------------------------------------------------------------------------- #
class AgentHealthMonitor:
    """Roll :class:`AgentRunResult`s into health records + the two per-run summaries.

    Stateless: every method is a pure function of its inputs (deterministic, order-stable). It
    counts volumes and assigns labels -- it NEVER scores, ranks, or decides.
    """

    # -- per-agent rolling health -------------------------------------------- #
    def roll_agent_health(self, results: Iterable[AgentRunResult]) -> Tuple[AgentHealthRecord, ...]:
        """One :class:`~reality_mesh.runtime.AgentHealthRecord` per agent, from its results in order.

        ``failure_count`` is the number of ``failed`` results seen for that agent (a volume count
        that increments across failures); ``last_*`` reflect the most recent result; ``last_error``
        / ``degraded_reason`` carry the last non-healthy note (secret-free by construction upstream).
        """
        order = []
        by_agent = {}
        for res in results:
            aid = res.agent_id
            if aid not in by_agent:
                by_agent[aid] = []
                order.append(aid)
            by_agent[aid].append(res)

        records = []
        for aid in order:
            records.append(self._agent_record(aid, by_agent[aid]))
        return tuple(records)

    def agent_health(self, agent_id: str,
                     results: Iterable[AgentRunResult]) -> AgentHealthRecord:
        """The rolling :class:`~reality_mesh.runtime.AgentHealthRecord` for ONE agent."""
        scoped = [r for r in results if r.agent_id == agent_id]
        return self._agent_record(agent_id, scoped)

    @staticmethod
    def _agent_record(agent_id: str,
                      results: Iterable[AgentRunResult]) -> AgentHealthRecord:
        results = list(results)
        failure_count = sum(1 for r in results if r.status == "failed")
        last = results[-1] if results else None

        last_run_id = last.run_id if last is not None else ""
        last_status = last.status if last is not None else ""
        last_error = ""
        degraded_reason = ""
        last_success_at = ""
        last_failure_at = ""

        for res in results:
            if res.status == "success":
                last_success_at = res.completed_at or last_success_at
            elif res.status in ("failed", "blocked_by_policy"):
                last_failure_at = res.completed_at or last_failure_at

        if last is not None and last.status in ("failed", "blocked_by_policy", "partial"):
            if last.errors:
                last_error = last.errors[0]
            elif last.warnings:
                last_error = last.warnings[0]
            degraded_reason = "last run {0!r} status={1}".format(last.run_id, last.status)

        return AgentHealthRecord(
            agent_id=agent_id,
            last_run_id=last_run_id,
            last_status=last_status,
            failure_count=failure_count,
            last_error=last_error,
            last_success_at=last_success_at,
            last_failure_at=last_failure_at,
            degraded_reason=degraded_reason)

    # -- per-run roll-ups ---------------------------------------------------- #
    @staticmethod
    def _tally(results, sources, extra_gaps, extra_conflicts):
        results = list(results)
        sources = list(sources or ())
        successes = sum(1 for r in results if r.status in ("success", "partial"))
        failures = sum(1 for r in results if r.status == "failed")
        blocked = sum(1 for r in results if r.status == "blocked_by_policy")
        skipped = sum(1 for r in results if r.status == "skipped")

        gap_count = sum(len(r.data_gaps) for r in results) + len(tuple(extra_gaps or ()))
        conflict_count = sum(len(r.conflicts) for r in results) + len(tuple(extra_conflicts or ()))

        sources_failed = sum(1 for s in sources if getattr(s, "is_failed", False))
        sources_used = len(sources)
        return {
            "results": results, "successes": successes, "failures": failures,
            "blocked": blocked, "skipped": skipped, "gap_count": gap_count,
            "conflict_count": conflict_count, "sources_used": sources_used,
            "sources_failed": sources_failed,
        }

    def build_run_health_summary(
        self,
        run_id: str,
        results: Iterable[AgentRunResult],
        *,
        sources: Iterable[SourceHealthRecord] = (),
        gaps: Iterable[str] = (),
        conflicts: Iterable[str] = (),
        notes: Iterable[str] = (),
    ) -> RunHealthSummary:
        """Roll a run's results (+ sources / gaps / conflicts) into a :class:`RunHealthSummary`.

        Always produces a summary -- a partial run reads ``overall_status="degraded"``. Counts are
        volumes; the overall status is an honest label.
        """
        if not str(run_id).strip():
            raise ValueError("build_run_health_summary requires a non-empty run_id")
        t = self._tally(results, sources, gaps, conflicts)
        overall = _overall_status(t["successes"], t["failures"], t["blocked"])
        return RunHealthSummary(
            run_id=run_id,
            agents_total=len(t["results"]),
            agents_run=t["successes"],
            agents_failed=t["failures"],
            agents_blocked=t["blocked"],
            agents_skipped=t["skipped"],
            sources_used=t["sources_used"],
            sources_failed=t["sources_failed"],
            data_gap_count=t["gap_count"],
            conflict_count=t["conflict_count"],
            overall_status=overall,
            notes=tuple(notes or ()))

    def build_data_quality_summary(
        self,
        run_id: str,
        results: Iterable[AgentRunResult],
        *,
        sources: Iterable[SourceHealthRecord] = (),
        gaps: Iterable[str] = (),
        conflicts: Iterable[str] = (),
        weak_social: Iterable[str] = (),
        unsupported_claims: Iterable[str] = (),
        notes: Iterable[str] = (),
    ) -> DataQualityRunSummary:
        """Roll a run's results into a :class:`DataQualityRunSummary` -- ALWAYS, even when degraded.

        A partial / degraded run STILL yields a Data-Quality summary (``status="degraded"``, honestly
        labelled). ``weak_social`` and ``unsupported_claims`` are surfaced as volume counts -- a high
        count is honesty about coverage, not a defect. No score / rank field is produced.
        """
        if not str(run_id).strip():
            raise ValueError("build_data_quality_summary requires a non-empty run_id")
        t = self._tally(results, sources, gaps, conflicts)
        status = _overall_status(t["successes"], t["failures"], t["blocked"])
        coverage = _coverage_label(t["sources_used"], t["sources_failed"])
        return DataQualityRunSummary(
            run_id=run_id,
            sources_used=t["sources_used"],
            sources_failed=t["sources_failed"],
            source_coverage=coverage,
            gap_count=t["gap_count"],
            conflict_count=t["conflict_count"],
            weak_social_count=len(tuple(weak_social or ())),
            unsupported_claim_count=len(tuple(unsupported_claims or ())),
            status=status,
            notes=tuple(notes or ()))


# A construction-time guard: none of the new records may carry a trade / score field.
for _record_cls in HEALTH_RECORDS:
    assert_no_trade_fields(_record_cls)
del _record_cls
