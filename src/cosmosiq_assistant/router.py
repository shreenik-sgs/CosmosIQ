"""The assistant router: precedence + free/paid selection + failover + circuit breaker (PROD-LIVE-3).

:func:`run_assistant` runs ONE assistant task against the appropriate provider chain and returns a
frozen :class:`AssistantResult` whose ``text`` is ALWAYS post-filtered (:mod:`.guardrails`) and
which ALWAYS carries the mandatory AI-generated ``label``. It NEVER touches the deterministic
engine, is NEVER persisted as evidence, and issues NO buy / sell / hold / order directive.

PRECEDENCE per task: ``force_provider(task)`` -> the runtime toggle -> ``LLM_PRIMARY`` env
(default ``"nvidia"``) -> ``nvidia``. Selection between the FREE chain (default; all unattended
work) and the PAID chain (an explicit ``full_api`` opt-in) is the ``mode`` argument.

FAILOVER: each configured client in the chain is tried in order; a :class:`ProviderError` moves to
the next; an all-fail run returns an honest, still-labelled gap result (never a fabricated answer).

CIRCUIT BREAKER (process-global): when a PAID (Claude) call fails with ``billing`` / ``5xx`` /
``auth``, a global breaker TRIPS and every subsequent paid request routes to the FREE chain for a
~10-minute window (an INJECTED clock in tests); after the window it half-opens and PROBES the paid
chain once, closing on success or re-tripping on another billing/5xx/auth failure.

Stdlib-only, Python 3.9, deterministic, OFFLINE tests (providers are injected fakes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from .guardrails import AI_LABEL, filter_action_directives
from .providers import (
    ProviderChain,
    ProviderError,
    build_provider_chain,
    normalize_mode,
)

__all__ = [
    "AssistantResult",
    "CircuitBreaker",
    "AssistantRouter",
    "run_assistant",
    "register_force_provider",
    "clear_force_provider",
    "set_runtime_toggle",
    "install_test_clients",
    "clear_test_clients",
    "current_test_clients",
    "app_run_assistant",
    "CIRCUIT_WINDOW_SECONDS",
    "GLOBAL_BREAKER",
]

# The default recovery window: paid failures route to the free chain for ~10 minutes.
CIRCUIT_WINDOW_SECONDS = 600.0

_PAID = "paid"
_FREE = "free"


@dataclass(frozen=True)
class AssistantResult:
    """One assistant run's outcome. ``text`` is POST-FILTERED; ``label`` is the mandatory tag.

    It is display-only: never evidence, never a gate / candidate / recommendation / DQ input,
    never part of replay. ``provider_used`` is "" when every provider was unavailable (an honest
    gap). ``circuit_state`` is ``closed`` / ``open`` / ``half_open`` at the time of the run.
    """

    text: str = ""
    provider_used: str = ""
    mode: str = "free"
    circuit_state: str = "closed"
    label: str = AI_LABEL
    notes: Tuple[str, ...] = field(default_factory=tuple)
    task: str = ""
    ai_generated: bool = True


# --------------------------------------------------------------------------- #
# Injected-clock helper                                                          #
# --------------------------------------------------------------------------- #
def _epoch(now: object) -> float:
    """Injected instant -> epoch seconds. Accepts a float (tests) or an ISO-8601 string (app).

    NEVER reads a wall clock; a blank / unparseable value is 0.0 (deterministic).
    """
    if isinstance(now, bool):
        return 0.0
    if isinstance(now, (int, float)):
        return float(now)
    text = str(now or "").strip()
    if not text:
        return 0.0
    import datetime  # lazy; stdlib
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# --------------------------------------------------------------------------- #
# The process-global circuit breaker                                             #
# --------------------------------------------------------------------------- #
class CircuitBreaker:
    """A minimal process-global breaker over an INJECTED clock (never a wall clock).

    ``closed`` normally; ``trip(now)`` opens it (records the instant); it stays ``open`` for
    ``window_seconds`` then reports ``half_open`` (a single probe is allowed); ``record_success``
    closes it. All timing comes from the injected ``now`` -- deterministic and offline.
    """

    def __init__(self, *, window_seconds: float = CIRCUIT_WINDOW_SECONDS) -> None:
        self._window = float(window_seconds)
        self._tripped_at: Optional[float] = None
        self.trip_count = 0

    def state(self, now: object) -> str:
        if self._tripped_at is None:
            return "closed"
        elapsed = _epoch(now) - self._tripped_at
        return "half_open" if elapsed >= self._window else "open"

    def is_open(self, now: object) -> bool:
        return self.state(now) == "open"

    def trip(self, now: object) -> None:
        self._tripped_at = _epoch(now)
        self.trip_count += 1

    def record_success(self) -> None:
        self._tripped_at = None

    def reset(self) -> None:
        self._tripped_at = None
        self.trip_count = 0


# The single process-global breaker every default run shares.
GLOBAL_BREAKER = CircuitBreaker()

# --------------------------------------------------------------------------- #
# Precedence hooks (force_provider / runtime toggle) + the offline test seam     #
# --------------------------------------------------------------------------- #
_FORCE_PROVIDER: Dict[str, str] = {}          # task -> forced mode/provider
_RUNTIME_TOGGLE: Optional[str] = None         # a process-wide mode override
_TEST_CLIENTS: Optional[Dict[str, Any]] = None  # injected fakes for the app path (OFFLINE tests)


def register_force_provider(task: str, mode: str) -> None:
    """Force a per-task chain override (highest precedence). ``mode`` is 'free' or 'full_api'."""
    _FORCE_PROVIDER[str(task)] = str(mode)


def clear_force_provider(task: Optional[str] = None) -> None:
    if task is None:
        _FORCE_PROVIDER.clear()
    else:
        _FORCE_PROVIDER.pop(str(task), None)


def set_runtime_toggle(mode: Optional[str]) -> None:
    """Set (or clear with ``None``) the process-wide runtime chain toggle."""
    global _RUNTIME_TOGGLE
    _RUNTIME_TOGGLE = None if mode is None else str(mode)


def install_test_clients(clients: Optional[Mapping[str, Any]]) -> None:
    """OFFLINE test seam: make the app-path :func:`run_assistant` use these injected fakes.

    Used ONLY by tests to keep the app POST path offline; the production default is ``None``
    (real clients from env presence). Cleared with :func:`clear_test_clients`.
    """
    global _TEST_CLIENTS
    _TEST_CLIENTS = dict(clients) if clients is not None else None


def clear_test_clients() -> None:
    global _TEST_CLIENTS
    _TEST_CLIENTS = None


def current_test_clients() -> Optional[Dict[str, Any]]:
    """The injected offline-test clients (``None`` in production -- real clients from env presence)."""
    return dict(_TEST_CLIENTS) if _TEST_CLIENTS is not None else None


def _effective_mode(task: str, mode: object, env: Mapping[str, str]) -> str:
    """Resolve the chain per precedence: force_provider(task) -> runtime toggle -> mode arg.

    (``LLM_PRIMARY`` selects the free workhorse, which is already nvidia-first, so an explicit
    mode of 'free' / 'paid' is the effective selector here; the default is the free chain.)
    """
    forced = _FORCE_PROVIDER.get(str(task))
    if forced is not None:
        return normalize_mode(forced)
    if _RUNTIME_TOGGLE is not None:
        return normalize_mode(_RUNTIME_TOGGLE)
    return normalize_mode(mode)


# --------------------------------------------------------------------------- #
# run_assistant -- run one task through the chain, with failover + breaker        #
# --------------------------------------------------------------------------- #
def _run_chain(chain: ProviderChain, prompt: str, system: str,
               notes: list) -> Tuple[str, str, Optional[ProviderError]]:
    """Try each configured client in order. Return (text, provider_used, last_error)."""
    last_err: Optional[ProviderError] = None
    for client in chain.clients:
        provider = getattr(client, "provider", "")
        try:
            text = client.complete(prompt, system=system)
        except ProviderError as exc:
            last_err = exc
            notes.append("provider {0} failed ({1}) -- trying next in chain".format(
                provider, exc.kind))
            continue
        except Exception as exc:                        # noqa: BLE001 -- a fake/real raising oddly
            last_err = ProviderError(str(exc), kind="http", provider=provider)
            notes.append("provider {0} errored ({1}) -- trying next in chain".format(
                provider, type(exc).__name__))
            continue
        return str(text or ""), provider, None
    return "", "", last_err


def run_assistant(task: str, prompt: str, *, system: str = "", mode: str = "free",
                  env: Optional[Mapping[str, str]] = None,
                  clients: Optional[Mapping[str, Any]] = None,
                  now: object = 0.0,
                  breaker: Optional[CircuitBreaker] = None) -> AssistantResult:
    """Run ONE assistant task and return a frozen, LABELLED, POST-FILTERED :class:`AssistantResult`.

    ``mode`` picks the FREE (default) or PAID (``full_api``) chain, subject to the per-task
    ``force_provider`` / runtime-toggle precedence. Providers are tried in order (failover). A PAID
    ``billing`` / ``5xx`` / ``auth`` failure TRIPS the circuit breaker and reroutes to the FREE
    chain for the recovery window; while the breaker is open, paid requests use the free chain
    directly and PROBE the paid chain once the window elapses. ``clients`` injects fakes (tests);
    ``now`` is the injected clock; ``breaker`` defaults to the process-global one.
    """
    breaker = breaker if breaker is not None else GLOBAL_BREAKER
    requested = _effective_mode(task, mode, env if env is not None else {})
    notes: list = []
    circuit_state = breaker.state(now)

    effective = requested
    if requested == _PAID and circuit_state == "open":
        effective = _FREE
        notes.append("circuit breaker OPEN -- paid chain suppressed; routing to the FREE chain "
                     "until the recovery window elapses")

    chain = build_provider_chain(mode=effective, env=env, clients=clients)
    notes.extend(chain.notes)

    text, provider_used, last_err = _run_chain(chain, str(prompt or ""), str(system or ""), notes)

    # A PAID billing/5xx/auth failure trips the breaker and reroutes THIS run to the free chain.
    if provider_used == "" and effective == _PAID and last_err is not None \
            and last_err.kind in ("billing", "5xx", "auth"):
        breaker.trip(now)
        notes.append("circuit breaker TRIPPED on {0} {1} -- routing to the FREE chain for ~{2:.0f} "
                     "min".format(last_err.provider or "claude", last_err.kind,
                                  CIRCUIT_WINDOW_SECONDS / 60.0))
        free_chain = build_provider_chain(mode=_FREE, env=env, clients=clients)
        notes.extend(free_chain.notes)
        text, provider_used, last_err = _run_chain(
            free_chain, str(prompt or ""), str(system or ""), notes)
        effective = _FREE

    if provider_used:
        if requested == _PAID and effective == _PAID:
            breaker.record_success()            # a clean paid call closes / probes-successful
        filtered = filter_action_directives(text)
        return AssistantResult(
            text=filtered, provider_used=provider_used, mode=effective,
            circuit_state=breaker.state(now), label=AI_LABEL, notes=tuple(notes), task=str(task))

    # Every provider unavailable: an honest, still-labelled gap (nothing fabricated).
    reason = ("no LLM provider is configured -- set NVIDIA_API_KEY / GOOGLE_API_KEY / "
              "ANTHROPIC_API_KEY" if not chain.clients
              else "every configured provider failed ({0})".format(
                  last_err.kind if last_err is not None else "unknown"))
    notes.append(reason)
    return AssistantResult(
        text=filter_action_directives(
            "AI assistant unavailable: {0}. No summary or note was generated.".format(reason)),
        provider_used="", mode=effective, circuit_state=breaker.state(now),
        label=AI_LABEL, notes=tuple(notes), task=str(task))


# --------------------------------------------------------------------------- #
# AssistantRouter -- a thin OO wrapper for callers that want an instance          #
# --------------------------------------------------------------------------- #
class AssistantRouter:
    """A thin wrapper binding a breaker + optional injected clients to :func:`run_assistant`."""

    def __init__(self, *, breaker: Optional[CircuitBreaker] = None,
                 clients: Optional[Mapping[str, Any]] = None) -> None:
        self.breaker = breaker if breaker is not None else GLOBAL_BREAKER
        self._clients = dict(clients) if clients is not None else None

    def run(self, task: str, prompt: str, *, system: str = "", mode: str = "free",
            env: Optional[Mapping[str, str]] = None, now: object = 0.0) -> AssistantResult:
        return run_assistant(task, prompt, system=system, mode=mode, env=env,
                             clients=self._clients, now=now, breaker=self.breaker)


def app_run_assistant(task: str, prompt: str, *, system: str = "", mode: str = "free",
                      env: Optional[Mapping[str, str]] = None,
                      now: object = 0.0) -> AssistantResult:
    """The app-path entry: uses the OFFLINE test-seam clients when installed, else real clients."""
    return run_assistant(task, prompt, system=system, mode=mode, env=env,
                         clients=_TEST_CLIENTS, now=now)
