"""cosmosiq_service -- the supervised operator service (IMPLEMENTATION-020C).

This package is a NEW top-level src package (like :mod:`cosmosiq_app` / :mod:`cosmosiq_ops`), kept
OUT of :mod:`reality_mesh` so the reality-mesh anti-scheduler / anti-network AST guards stay
untouched. It exposes the PURE, deterministic, offline-testable CORE (:mod:`cosmosiq_service.service`):
the mode state machine, the single-instance lock, :func:`run_once` (ONE tick through the accepted
015B one-tick orchestrator + FULL 013 chain), failure / backoff / health accounting, and the
sanitized health snapshot.

Importing this package starts NOTHING: there is no loop, no thread, no socket, no wall-clock read.
The ONLY place with a ``while`` + ``time.sleep`` loop is the operator-started
:mod:`cosmosiq_service.__main__` process, which this package does NOT import.
"""

from __future__ import annotations

from .service import (
    DEFAULT_MODE,
    LockError,
    LockHandle,
    ServiceConfig,
    ServiceHealth,
    ServiceMode,
    acquire_lock,
    continuous_activation_gate,
    continuous_shadow_allowed,
    load_health,
    pause,
    read_lock,
    release_lock,
    requires_activation_gate,
    resume,
    run_once,
    sanitize,
    service_status,
)

__all__ = [
    "DEFAULT_MODE",
    "LockError",
    "LockHandle",
    "ServiceConfig",
    "ServiceHealth",
    "ServiceMode",
    "acquire_lock",
    "continuous_activation_gate",
    "continuous_shadow_allowed",
    "load_health",
    "pause",
    "read_lock",
    "release_lock",
    "requires_activation_gate",
    "resume",
    "run_once",
    "sanitize",
    "service_status",
]
