"""Stage D -- Bottleneck analysis.

Characterises the binding constraint behind the opportunity: how severe it is,
how long it persists, how likely it is to resolve, who wins and who loses when it
binds, and over what window. ``bottleneck_leverage`` is the alpha the constraint
confers: severe + durable + hard-to-resolve constraints reprice the nodes that
own them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from ._common import clamp

# driving_constraint -> a structured bottleneck profile.
_BOTTLENECK_PROFILES = {
    "power/energy": dict(
        bottleneck_type="secured_power_capacity",
        constrained_node="grid-connected, power-secured compute capacity",
        severity=0.85,
        duration="multi_year",
        resolution_risk=0.30,
        evidence_quality=0.70,
        direct_beneficiaries=("secured-power capacity owners",),
        indirect_beneficiaries=("turbine/transformer suppliers",),
        constrained_losers=("compute tenants without secured power",),
        timing_window="next 4-8 quarters",
    ),
}

_DURATION_FACTOR = {
    "transient": 0.4,
    "multi_quarter": 0.7,
    "multi_year": 1.0,
    "structural": 1.0,
}


@dataclass(frozen=True)
class BottleneckResult:
    bottleneck_type: str = ""
    constrained_node: str = ""
    severity: float = 0.0
    duration: str = ""
    resolution_risk: float = 0.0
    evidence_quality: float = 0.0
    direct_beneficiaries: Tuple[str, ...] = field(default_factory=tuple)
    indirect_beneficiaries: Tuple[str, ...] = field(default_factory=tuple)
    constrained_losers: Tuple[str, ...] = field(default_factory=tuple)
    timing_window: str = ""
    bottleneck_leverage: float = 0.0


def analyze_bottleneck(opportunity_hypothesis) -> BottleneckResult:
    oh = opportunity_hypothesis
    if not oh.bottleneck_driven or not oh.driving_constraint:
        return BottleneckResult(bottleneck_type="none", bottleneck_leverage=0.0)

    profile = _BOTTLENECK_PROFILES.get(oh.driving_constraint)
    if profile is None:
        profile = dict(
            bottleneck_type="{0}_constraint".format(oh.driving_constraint),
            constrained_node=oh.value_chain_position or oh.driving_constraint,
            severity=0.6, duration="multi_quarter", resolution_risk=0.4,
            evidence_quality=float(getattr(oh, "evidence_strength", 0.5)),
            direct_beneficiaries=(oh.value_chain_position,) if oh.value_chain_position else (),
            indirect_beneficiaries=(), constrained_losers=(),
            timing_window="next 2-4 quarters",
        )
    duration_factor = _DURATION_FACTOR.get(profile["duration"], 0.7)
    leverage = clamp(profile["severity"] * (1.0 - profile["resolution_risk"]) * duration_factor)
    return BottleneckResult(bottleneck_leverage=round(leverage, 4), **profile)
