"""Shared deterministic helpers for the Prometheus / Nivesha diligence gauntlet.

Pure functions only -- no wall clock, no randomness. Every stage of the gauntlet
imports its clamps and reducers from here so the arithmetic is uniform and
byte-stable across runs.
"""

from __future__ import annotations

from typing import Iterable, Optional

EPS = 1e-9


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def sign(x: float) -> float:
    if x > EPS:
        return 1.0
    if x < -EPS:
        return -1.0
    return 0.0


def mean(values: Iterable[float]) -> float:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def safe_ratio(num: float, den: float) -> float:
    return float(num) / max(abs(float(den)), EPS)


def opt(value: Optional[float], default: float = 0.0) -> float:
    return default if value is None else float(value)
