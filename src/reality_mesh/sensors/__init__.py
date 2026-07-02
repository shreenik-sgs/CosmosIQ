"""Concrete Tattva sensor agents for the Reality Mesh (IMPLEMENTATION-012D+).

The FIRST real sensor logic in Phase 012. Where :mod:`reality_mesh.agents` /
:mod:`reality_mesh.registry` (012B) define *what a sensor is and may emit*, this package holds
the concrete :class:`~reality_mesh.agents.SensorAgent` implementations that turn FIXTURE-backed
:class:`~reality_mesh.models.RealityEvent`s into :class:`~reality_mesh.models.AgentFinding`s.

Every sensor here is FIXTURE / MOCK ONLY: it interprets injected RealityEvents and NEVER fetches
live market data, opens a socket, schedules, streams, or touches a broker. It emits qualitative
LABELS -- never a number, score, rank, buy/sell/hold, order, or thesis -- and it stays strictly
within its declared discipline (``run_checked`` enforces this at the boundary). Missing input
becomes an explicit data gap; stale input is marked stale and preserved, never dropped or faked.

Deterministic, stdlib-only, Python 3.9. No network on import; no wall-clock in any id path.
"""

from __future__ import annotations

from .market_regime import (
    MarketRegimeAgent,
    MARKET_REGIME_FINDING_TYPES,
    MARKET_REGIME_SUBAGENTS,
    events_from_fixture,
)
from .rotation import (
    SectorRotationAgent,
    ThemeRotationAgent,
    SECTOR_ROTATION_FINDING_TYPES,
    SECTOR_ROTATION_SUBAGENTS,
    THEME_ROTATION_FINDING_TYPES,
    THEME_ROTATION_SUBAGENTS,
    FLOW_PROXY_CAVEAT,
    BROADENING_MIN_MEMBERS,
)

__all__ = [
    "MarketRegimeAgent",
    "MARKET_REGIME_FINDING_TYPES",
    "MARKET_REGIME_SUBAGENTS",
    "events_from_fixture",
    "SectorRotationAgent",
    "ThemeRotationAgent",
    "SECTOR_ROTATION_FINDING_TYPES",
    "SECTOR_ROTATION_SUBAGENTS",
    "THEME_ROTATION_FINDING_TYPES",
    "THEME_ROTATION_SUBAGENTS",
    "FLOW_PROXY_CAVEAT",
    "BROADENING_MIN_MEMBERS",
]
