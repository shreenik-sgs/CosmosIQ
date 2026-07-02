"""The AgentRunLedger + the failure-isolating agent runner (IMPLEMENTATION-013D).

The runtime layer that makes **failure isolation the point**: one failed OR policy-blocked
agent must NEVER crash a pulse run. This module adds an *isolating* layer ALONGSIDE the accepted
012K :func:`~reality_mesh.pulse.run_pulse` (it does NOT modify it): where the pulse runs the five
sensor agents optimistically, :func:`run_agent_isolated` wraps ONE agent's
:meth:`~reality_mesh.agents.SensorAgent.run_checked` so that:

* any exception (a crash inside the agent, a timeout) -> an
  :class:`~reality_mesh.runtime.AgentRunResult` with ``status="failed"`` + a safe (secret-free)
  error note + a data gap + ``health_status="failed"`` -- the exception NEVER propagates;
* a policy refusal (``run_checked`` refusing a forbidden / out-of-discipline / trade-bearing
  output, or an agent raising :class:`PolicyBlock`) -> ``status="blocked_by_policy"`` + a gap;
* an agent that declines to run (raising :class:`SkipAgent`) -> ``status="skipped"`` + a gap;
* a clean run -> ``status="success"`` carrying the produced finding ids.

A partial / degraded batch STILL produces a result per agent (:func:`run_agents_isolated`); one
failure never aborts the batch. The :class:`AgentRunLedger` is an APPEND-ONLY store (it composes
the 013B :class:`~reality_mesh.stores.AppendOnlyStore`) recording one ``AgentRunResult`` per agent
per run -- never a score / rank / trade field, never a secret.

OBSERVABILITY, not a run loop. There is NO scheduler, NO daemon, NO streaming, NO 24x7 loop, NO
broker, NO order, and no buy/sell/order affordance anywhere. Health is labels + volume counts,
never a score. Deterministic, stdlib-only, Python 3.9: ``now`` is an injected string (no
wall-clock), collections are order-stable, no network on import.
"""

from __future__ import annotations

from typing import Any, Iterable, Tuple

from .runtime import AgentRunContext, AgentRunResult
from .stores import CREDENTIAL_KEY_TOKENS, AppendOnlyStore

__all__ = [
    "SkipAgent",
    "PolicyBlock",
    "POLICY_MESSAGE_TOKENS",
    "AgentRunLedger",
    "run_agent_isolated",
    "run_agents_isolated",
]


# --------------------------------------------------------------------------- #
# Control-flow signals an agent may raise (classified, never propagated)        #
# --------------------------------------------------------------------------- #
class SkipAgent(Exception):
    """Raised by an agent to DECLINE a run (e.g. no matching events / sources in scope).

    A skip is honest coverage absence, not a malfunction: the isolating runner records
    ``status="skipped"`` + a data gap, and the run continues.
    """


class PolicyBlock(ValueError):
    """Raised when a policy / security gate REFUSES an agent output (not a crash).

    Subclasses ``ValueError`` so it is caught like a boundary refusal; the isolating runner
    records ``status="blocked_by_policy"`` + a data gap, and the run continues.
    """


# Message tokens that mark a ``run_checked`` refusal as a POLICY block (a forbidden / cross-layer
# / out-of-discipline / trade-bearing output) rather than a generic crash. Matched case-insensitively
# against the exception text so the accepted ``run_checked`` / ``assert_no_trade_fields`` messages
# classify as ``blocked_by_policy`` without a new dedicated exception on the 012 boundary.
POLICY_MESSAGE_TOKENS: Tuple[str, ...] = (
    "agentfinding only",
    "out-of-discipline",
    "may not emit",
    "may emit",
    "forbidden",
    "not permitted",
    "trade/score",
    "boundary",
    "policy",
)


# --------------------------------------------------------------------------- #
# Safe (secret-free) error notes                                                #
# --------------------------------------------------------------------------- #
def _safe_error_message(exc: BaseException) -> str:
    """A short ``Type: detail`` note with any credential-like content REDACTED (no secret).

    The ledger never persists a secret. If the exception text contains a credential-like token
    the whole detail is replaced with a redaction marker; otherwise it is length-capped.
    """
    detail = str(exc)
    low = detail.lower()
    for token in CREDENTIAL_KEY_TOKENS:
        if token in low:
            return "{0}: <error detail redacted (contained a credential-like token)>".format(
                type(exc).__name__)
    if len(detail) > 400:
        detail = detail[:400] + "..."
    return "{0}: {1}".format(type(exc).__name__, detail)


def _is_policy_refusal(exc: BaseException) -> bool:
    """True iff ``exc`` is a POLICY refusal (a forbidden / boundary output), not a generic crash."""
    if isinstance(exc, PolicyBlock):
        return True
    # A structural trade/score/broker-field refusal (assert_no_trade_fields) is a policy block.
    if isinstance(exc, AssertionError):
        return True
    if isinstance(exc, ValueError):
        low = str(exc).lower()
        return any(tok in low for tok in POLICY_MESSAGE_TOKENS)
    return False


# --------------------------------------------------------------------------- #
# Context / identity resolution                                                 #
# --------------------------------------------------------------------------- #
def _resolve_ids(agent: Any, context: Any) -> Tuple[str, str, str]:
    """Resolve (run_id, agent_id, started_at) from the context (an AgentRunContext or a run_id str).

    ``context`` may be an :class:`~reality_mesh.runtime.AgentRunContext` (identity + policy), or a
    plain ``run_id`` string (agent_id then comes from the agent's descriptor). A missing run_id is
    a caller error (raised BEFORE the isolated section -- it is misuse, not an agent failure).
    """
    agent_id = ""
    descriptor = getattr(agent, "descriptor", None)
    if descriptor is not None:
        agent_id = getattr(descriptor, "agent_id", "") or ""

    if isinstance(context, AgentRunContext):
        run_id = context.run_id
        agent_id = context.agent_id or agent_id
        started_at = context.started_at
    elif isinstance(context, str):
        run_id = context
        started_at = ""
    elif context is None:
        run_id = ""
        started_at = ""
    else:  # a duck-typed context object
        run_id = getattr(context, "run_id", "") or ""
        agent_id = getattr(context, "agent_id", "") or agent_id
        started_at = getattr(context, "started_at", "") or ""

    if not str(run_id).strip():
        raise ValueError(
            "run_agent_isolated requires a run_id (pass an AgentRunContext carrying run_id, or a "
            "run_id string as the context)")
    if not str(agent_id).strip():
        raise ValueError(
            "run_agent_isolated could not resolve an agent_id (agent has no descriptor.agent_id "
            "and the context carried none)")
    return str(run_id), str(agent_id), str(started_at)


def _input_event_ids(context: Any, events: Iterable[Any]) -> Tuple[str, ...]:
    """The input event ids for the result: the context's declared ids, else the events' own ids."""
    if isinstance(context, AgentRunContext) and context.input_event_ids:
        return tuple(context.input_event_ids)
    ids = []
    for ev in events or ():
        eid = getattr(ev, "event_id", "")
        if eid:
            ids.append(eid)
    return tuple(ids)


# --------------------------------------------------------------------------- #
# The isolating runner -- one agent, never a crash                              #
# --------------------------------------------------------------------------- #
def run_agent_isolated(agent: Any, context: Any, events: Iterable[Any],
                       *, now: str = "") -> AgentRunResult:
    """Run ONE agent under failure isolation; ALWAYS return an AgentRunResult (never propagate).

    Runs ``agent.run_checked(context, events)`` and maps the outcome to a frozen
    :class:`~reality_mesh.runtime.AgentRunResult`:

    * clean -> ``status="success"``, ``health_status="healthy"``, carrying the produced finding ids;
    * :class:`SkipAgent` -> ``status="skipped"`` (+ a coverage gap);
    * a policy refusal (:class:`PolicyBlock`, a trade-field ``AssertionError``, or a ``run_checked``
      forbidden/out-of-discipline ``ValueError``) -> ``status="blocked_by_policy"`` (+ a gap);
    * a timeout (``TimeoutError``) -> ``status="failed"``, ``health_status="failed"`` (+ a gap);
    * ANY other exception -> ``status="failed"``, ``health_status="failed"`` (+ a gap).

    Error notes are secret-free (:func:`_safe_error_message`). ``now`` is the injected
    ``completed_at`` (no wall-clock). The only thing that can raise is a CALLER misuse (a missing
    run_id / agent_id), surfaced before the isolated section.
    """
    run_id, agent_id, started_at = _resolve_ids(agent, context)
    input_ids = _input_event_ids(context, events)
    ev_tuple = tuple(events or ())

    try:
        outputs = agent.run_checked(context, ev_tuple)
    except SkipAgent as exc:
        note = _safe_error_message(exc) if str(exc) else "agent declined to run"
        return AgentRunResult(
            run_id=run_id, agent_id=agent_id, status="skipped",
            started_at=started_at, completed_at=now, input_event_ids=input_ids,
            warnings=(note,),
            data_gaps=("agent {0} skipped in run {1}: {2} -- honest coverage gap, no fabricated "
                       "value".format(agent_id, run_id, note),),
            health_status="healthy")
    except TimeoutError as exc:
        note = _safe_error_message(exc)
        return AgentRunResult(
            run_id=run_id, agent_id=agent_id, status="failed",
            started_at=started_at, completed_at=now, input_event_ids=input_ids,
            errors=("timeout: {0}".format(note),),
            data_gaps=("agent {0} timed out in run {1}: {2} -- isolated, run continues; no "
                       "fabricated value".format(agent_id, run_id, note),),
            health_status="failed")
    except BaseException as exc:  # noqa: B902 -- isolation is the point: nothing escapes.
        note = _safe_error_message(exc)
        if _is_policy_refusal(exc):
            return AgentRunResult(
                run_id=run_id, agent_id=agent_id, status="blocked_by_policy",
                started_at=started_at, completed_at=now, input_event_ids=input_ids,
                errors=(note,),
                data_gaps=("agent {0} blocked by policy in run {1}: {2} -- output refused, run "
                           "continues".format(agent_id, run_id, note),),
                health_status="blocked_by_policy")
        return AgentRunResult(
            run_id=run_id, agent_id=agent_id, status="failed",
            started_at=started_at, completed_at=now, input_event_ids=input_ids,
            errors=(note,),
            data_gaps=("agent {0} failed in run {1}: {2} -- isolated, run continues; no "
                       "fabricated value".format(agent_id, run_id, note),),
            health_status="failed")

    finding_ids = tuple(
        getattr(f, "finding_id", "") for f in outputs if getattr(f, "finding_id", ""))
    return AgentRunResult(
        run_id=run_id, agent_id=agent_id, status="success",
        started_at=started_at, completed_at=now, input_event_ids=input_ids,
        finding_ids=finding_ids, health_status="healthy")


def _split_item(item: Any) -> Tuple[Any, Tuple[Any, ...]]:
    """Split a batch item into ``(context, events)``.

    Accepts a ``(context, events)`` pair, a bare context (no events), or a bare events sequence
    (no distinct context -> the events double as the run scope, context defaults to ``None``).
    """
    # A (context, events) pair: a 2-tuple whose first element is a context (AgentRunContext / a
    # run_id str / None) and whose second element is the events sequence.
    if (isinstance(item, tuple) and len(item) == 2
            and (isinstance(item[0], (AgentRunContext, str)) or item[0] is None)
            and isinstance(item[1], (list, tuple))):
        return item[0], tuple(item[1] or ())
    if isinstance(item, AgentRunContext) or isinstance(item, str) or item is None:
        return item, ()
    if isinstance(item, (list, tuple)):
        return None, tuple(item)
    return item, ()


def run_agents_isolated(agents: Iterable[Any], contexts_or_events: Any,
                        *, now: str = "") -> Tuple[AgentRunResult, ...]:
    """Run MANY agents under failure isolation; return ALL results (one failure never aborts).

    Each agent MUST resolve a run_id + agent_id (from an :class:`~reality_mesh.runtime.AgentRunContext`
    carrying both, or a run_id string with the agent_id from the agent's descriptor).
    ``contexts_or_events`` may be:

    * a mapping ``{agent | agent_id -> (context, events) | context}`` -- each agent looked up by
      object identity then by ``descriptor.agent_id``; a missing entry runs with no events;
    * a sequence aligned with ``agents`` (``zip``), each element a ``(context, events)`` pair or a
      bare context.

    Every agent yields exactly one :class:`~reality_mesh.runtime.AgentRunResult`; a failed / blocked
    / skipped agent is isolated (a result + a gap) and the remaining agents still run.
    """
    agents = list(agents)
    results = []

    if isinstance(contexts_or_events, dict):
        for agent in agents:
            item = _lookup_batch(agent, contexts_or_events)
            context, events = _split_item(item)
            results.append(run_agent_isolated(agent, context, events, now=now))
        return tuple(results)

    # A per-agent sequence, zipped with agents.
    for agent, item in zip(agents, contexts_or_events or ()):
        context, events = _split_item(item)
        results.append(run_agent_isolated(agent, context, events, now=now))
    return tuple(results)


def _lookup_batch(agent: Any, mapping: dict) -> Any:
    """Find an agent's batch item in ``mapping`` by object identity then by descriptor agent_id."""
    if agent in mapping:
        return mapping[agent]
    descriptor = getattr(agent, "descriptor", None)
    aid = getattr(descriptor, "agent_id", "") if descriptor is not None else ""
    if aid in mapping:
        return mapping[aid]
    return None


# --------------------------------------------------------------------------- #
# AgentRunLedger -- append-only log of AgentRunResults                          #
# --------------------------------------------------------------------------- #
class AgentRunLedger(AppendOnlyStore):
    """An APPEND-ONLY ledger of :class:`~reality_mesh.runtime.AgentRunResult`s (one per agent-run).

    Composes the 013B :class:`~reality_mesh.stores.AppendOnlyStore` so it inherits the same hard
    guarantees: no update / delete / in-place mutation, a replay envelope on every line, the
    credential-key + trade/score-key write refusal, and deterministic ``sort_keys`` JSONL. A
    result's stable record id is ``"{run_id}:{agent_id}"`` (an agent re-run in a LATER run appends a
    NEW line -- history is never overwritten).
    """

    filename = "agent_run_ledger.jsonl"
    record_cls = AgentRunResult
    id_field = None
    timestamp_field = "completed_at"

    def append_result(self, result: AgentRunResult) -> str:
        """Append ONE AgentRunResult; return its stable ``"{run_id}:{agent_id}"`` record id."""
        if not isinstance(result, AgentRunResult):
            raise TypeError("append_result expects an AgentRunResult")
        record_id = "{0}:{1}".format(result.run_id, result.agent_id)
        return self.append(
            result, run_id=result.run_id, timestamp=result.completed_at or result.started_at,
            record_id=record_id)

    def results_for_run(self, run_id: str) -> Tuple[AgentRunResult, ...]:
        """Every recorded result for one pulse run, in append order."""
        return self.query(run_id=run_id)

    def results_for_agent(self, agent_id: str) -> Tuple[AgentRunResult, ...]:
        """Every recorded result for one agent across all runs, in append order."""
        return self.query(agent_id=agent_id)
