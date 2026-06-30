"""Stage C -- Value-chain graph and economic-capture identification.

Builds a small curated value-chain graph for the opportunity's (domain, driving
constraint) and scores each node's ECONOMIC LEVERAGE -- how much of the chain's
economics that node can capture and defend. The Tier-1 node with the highest
economic leverage is the capture node: where the money actually concentrates when
the bottleneck binds. This is structural reasoning about WHERE value accrues; it
names roles, not securities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from ._common import mean


@dataclass(frozen=True)
class ValueChainNode:
    node_id: str
    tier: int
    node_type: str
    role: str
    upstream_dependencies: Tuple[str, ...] = field(default_factory=tuple)
    downstream_demand: Tuple[str, ...] = field(default_factory=tuple)
    choke_point: bool = False
    substitution_difficulty: float = 0.0
    pricing_power: float = 0.0
    margin_capture_potential: float = 0.0
    capital_intensity: float = 0.0
    evidence_strength: float = 0.0
    economic_leverage_score: float = 0.0


@dataclass(frozen=True)
class ValueChainResult:
    nodes: Tuple[ValueChainNode, ...] = field(default_factory=tuple)
    value_chain_capture: float = 0.0
    capture_node: ValueChainNode = None
    capture_role: str = ""


def _leverage(choke_point, substitution_difficulty, pricing_power, margin_capture):
    return round(mean([
        1.0 if choke_point else 0.0,
        substitution_difficulty,
        pricing_power,
        margin_capture,
    ]), 4)


def _power_energy_graph(evidence_strength: float) -> Tuple[ValueChainNode, ...]:
    raw = (
        # T1: secured-power capacity owner -- the choke point and capture node.
        dict(node_id="t1_secured_power", tier=1, node_type="capacity_owner",
             role="secured-power capacity owner",
             upstream_dependencies=("grid interconnect",),
             downstream_demand=("AI compute tenants",),
             choke_point=True, substitution_difficulty=0.85, pricing_power=0.85,
             margin_capture_potential=0.85, capital_intensity=0.80),
        # T4: grid interconnect -- the enabling constraint itself.
        dict(node_id="t4_grid", tier=4, node_type="enabling_constraint",
             role="grid interconnect / enabling",
             upstream_dependencies=(), downstream_demand=("secured-power capacity owner",),
             choke_point=True, substitution_difficulty=0.70, pricing_power=0.45,
             margin_capture_potential=0.40, capital_intensity=0.90),
        # T2: turbine / transformer suppliers.
        dict(node_id="t2_equipment", tier=2, node_type="equipment_supplier",
             role="turbine/transformer supplier",
             upstream_dependencies=("components",), downstream_demand=("capacity owners",),
             choke_point=False, substitution_difficulty=0.55, pricing_power=0.55,
             margin_capture_potential=0.50, capital_intensity=0.60),
        # T3: supplier-of-supplier.
        dict(node_id="t3_components", tier=3, node_type="component_supplier",
             role="supplier-of-supplier",
             upstream_dependencies=(), downstream_demand=("equipment suppliers",),
             choke_point=False, substitution_difficulty=0.40, pricing_power=0.35,
             margin_capture_potential=0.35, capital_intensity=0.45),
    )
    nodes = []
    for d in raw:
        lev = _leverage(d["choke_point"], d["substitution_difficulty"],
                        d["pricing_power"], d["margin_capture_potential"])
        nodes.append(ValueChainNode(evidence_strength=round(evidence_strength, 4),
                                    economic_leverage_score=lev, **d))
    return tuple(nodes)


def _generic_graph(driving_constraint: str, evidence_strength: float) -> Tuple[ValueChainNode, ...]:
    role = "{0}-advantaged operator".format(driving_constraint or "constraint")
    lev = _leverage(True, 0.6, 0.6, 0.6)
    return (ValueChainNode(
        node_id="t1_generic", tier=1, node_type="capacity_owner", role=role,
        choke_point=True, substitution_difficulty=0.6, pricing_power=0.6,
        margin_capture_potential=0.6, capital_intensity=0.6,
        evidence_strength=round(evidence_strength, 4), economic_leverage_score=lev),)


def analyze_value_chain(opportunity_hypothesis) -> ValueChainResult:
    oh = opportunity_hypothesis
    constraint = (oh.driving_constraint or "").lower()
    evidence = float(getattr(oh, "evidence_strength", 0.0))
    if "power" in constraint or "energy" in constraint:
        nodes = _power_energy_graph(evidence)
    elif oh.driving_constraint:
        nodes = _generic_graph(oh.driving_constraint, evidence)
    else:
        nodes = ()

    tier1 = [n for n in nodes if n.tier == 1]
    if tier1:
        capture = max(tier1, key=lambda n: n.economic_leverage_score)
        return ValueChainResult(
            nodes=nodes,
            value_chain_capture=capture.economic_leverage_score,
            capture_node=capture,
            capture_role=capture.role,
        )
    return ValueChainResult(nodes=nodes, value_chain_capture=0.0,
                            capture_node=None, capture_role="")
