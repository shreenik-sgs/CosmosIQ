"""The Agent Registry for the Reality Mesh (IMPLEMENTATION-012B).

INFRASTRUCTURE ONLY. A deterministic, in-memory registry of :class:`AgentDescriptor`s (and,
optionally, the :class:`SensorAgent` instances that back them). It registers, looks up, and
lists agents, validates every descriptor against ARCHITECTURE_CONTRACT_012 (via
:func:`reality_mesh.agents.validate_descriptor`), and rejects duplicate ``agent_id``s.

:func:`build_default_registry` loads the built-in descriptors from ``AGENT_MAP_012.md`` --
DESCRIPTORS ONLY, no active sensor logic: 6 Adhāra foundation agents, 6 Buddhi governance
agents, and the 14 Tattva sensor-mesh agents (26 total). Downstream synthesizer/Sphurana/
Nivesha/Saarathi/Kriya/Anubhava agents are defined in later slices.

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no broker, no scoring.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from . import labels as _labels
from .agents import (
    AgentDescriptor,
    SensorAgent,
    TATTVA_FINDING_SUBTYPES,
    validate_descriptor,
)


class AgentRegistry:
    """A deterministic registry of agent descriptors + optional backing agents."""

    def __init__(self) -> None:
        self._descriptors: Dict[str, AgentDescriptor] = {}
        self._agents: Dict[str, SensorAgent] = {}

    # -- registration ------------------------------------------------------ #
    def register(self, descriptor: AgentDescriptor, agent: Optional[SensorAgent] = None) -> None:
        """Register ``descriptor`` (and an optional backing ``agent``).

        Validates the descriptor against ARCHITECTURE_CONTRACT_012 and rejects a duplicate
        ``agent_id``. Raises ``ValueError`` on either violation.
        """
        validate_descriptor(descriptor)
        if descriptor.agent_id in self._descriptors:
            raise ValueError(
                "duplicate agent_id {0!r} already registered".format(descriptor.agent_id))
        self._descriptors[descriptor.agent_id] = descriptor
        if agent is not None:
            self._agents[descriptor.agent_id] = agent

    def register_agent(self, agent: SensorAgent) -> None:
        """Register a :class:`SensorAgent` by its own ``descriptor``."""
        self.register(agent.descriptor, agent=agent)

    # -- lookup ------------------------------------------------------------ #
    def get(self, agent_id: str) -> AgentDescriptor:
        """Return the descriptor for ``agent_id``. Raises ``KeyError`` if unknown."""
        if agent_id not in self._descriptors:
            raise KeyError("no agent registered with id {0!r}".format(agent_id))
        return self._descriptors[agent_id]

    def get_agent(self, agent_id: str) -> SensorAgent:
        """Return the backing :class:`SensorAgent` for ``agent_id`` (``KeyError`` if none)."""
        if agent_id not in self._agents:
            raise KeyError("no backing agent for id {0!r}".format(agent_id))
        return self._agents[agent_id]

    def has(self, agent_id: str) -> bool:
        return agent_id in self._descriptors

    def descriptors(self) -> Tuple[AgentDescriptor, ...]:
        """All descriptors, ordered by ``agent_id`` (deterministic)."""
        return tuple(self._descriptors[k] for k in sorted(self._descriptors))

    def list_by_layer(self, layer: str) -> Tuple[AgentDescriptor, ...]:
        return tuple(
            d for d in self.descriptors() if d.layer == layer)

    def list_by_discipline(self, discipline: str) -> Tuple[AgentDescriptor, ...]:
        return tuple(
            d for d in self.descriptors() if d.discipline == discipline)

    def __len__(self) -> int:
        return len(self._descriptors)


# --------------------------------------------------------------------------- #
# Built-in descriptors (AGENT_MAP_012 -- descriptors only, no active impl)      #
# --------------------------------------------------------------------------- #

# (agent_id, agent_name, emits-record) for the 6 Adhāra foundation agents (§3.1).
_ADHARA = (
    ("adhara.identity", "Identity", "EntityIdentityRecord",
     "assign stable IDs; dedupe entities; map ticker/company/CIK/theme/value-chain IDs"),
    ("adhara.provenance", "Provenance", "ProvenanceRecord",
     "track source lineage; attach source_refs; preserve raw_payload_ref"),
    ("adhara.authority", "Authority", "AuthorityAssessment",
     "classify source authority; prevent lower overriding higher for the same metric/period"),
    ("adhara.freshness", "Freshness", "FreshnessAssessment",
     "timestamp events; assign freshness_label + half_life; mark stale"),
    ("adhara.conflict", "Conflict", "ConflictRecord",
     "detect conflicting values; preserve conflicts; route to Data Quality + Red Team"),
    ("adhara.security_boundary", "Security Boundary", "SecurityGateResult",
     "no secrets in HTML; no keys in logs; no network on import; offline-test enforcement"),
)

# (agent_id, agent_name, emits-record) for the 6 Buddhi governance agents (§3.2).
_BUDDHI = (
    ("buddhi.layer_boundary", "Layer Boundary", "ArchitectureComplianceResult",
     "enforce layer responsibilities; block cross-layer conclusions"),
    ("buddhi.router", "Agent Router", "HandoffEnvelope",
     "route RealityEvent->sensor agents; route AgentFinding->correct synthesizer"),
    ("buddhi.fusion_coordinator", "Signal Fusion Coordinator", "FusionPlan",
     "coordinate Tattva Signal Fusion; preserve competing explanations"),
    ("buddhi.hypothesis_discipline", "Hypothesis Discipline", "HypothesisSet",
     "maintain competing hypotheses; prevent averaging away minority possibilities"),
    ("buddhi.gatekeeper", "Gatekeeper", "GateResult",
     "enforce no scheduler / no broker / no hidden score / no fake data"),
    ("buddhi.mode_controller", "Mode Controller", "ModeState",
     "keep demo/fixture/real/enriched/pulse modes separate; no silent fallback"),
)

# (agent_id, discipline, subagents...) for the 14 Tattva sensor agents (§3.3). Each emits the
# base AgentFinding plus its discipline-specific subtype (index-aligned to TATTVA_FINDING_SUBTYPES).
_TATTVA = (
    ("tattva.macro_regime", "macro_regime",
     ("Rates", "Yield Curve", "Dollar", "Credit Spread", "Inflation/Jobs Surprise",
      "Liquidity", "VIX/Volatility")),
    ("tattva.market_regime", "market_regime",
     ("Index Breadth", "Advance/Decline", "Distribution Day", "Volatility Regime",
      "Small-Cap Risk Appetite")),
    ("tattva.sector_rotation", "sector_rotation",
     ("Sector ETF Relative Strength", "Industry Group Breadth", "Volume Expansion",
      "Institutional Flow Proxy")),
    ("tattva.theme_rotation", "theme_rotation",
     ("Theme Basket Builder", "Theme Relative Strength", "Theme Breadth", "Theme Momentum",
      "Theme Crowding")),
    ("tattva.policy_geopolitical", "policy_geopolitical",
     ("War Risk", "Sanctions", "Tariff/Export Control", "Energy Policy", "Defense Policy",
      "AI Regulation", "Industrial Policy")),
    ("tattva.news_filings", "news_filings",
     ("8-K", "S-3/ATM", "Insider Sale", "Press Release", "Contract Announcement",
      "Guidance Update", "Partnership")),
    ("tattva.narrative", "narrative",
     ("Verified Account", "Expert Account", "Journalist", "Promoter/Bot-Risk",
      "Narrative Velocity", "Rumor Propagation", "Crowding")),
    ("tattva.options_flow", "options_flow",
     ("Unusual Volume", "IV Expansion", "Skew", "Gamma Zone Proxy", "Expiration Pressure")),
    ("tattva.technical_regime", "technical_regime",
     ("Compression", "Breakout", "EMA Stack", "VWAP", "Failure/Reversal", "Overextension")),
    ("tattva.financial_inflection", "financial_inflection",
     ("Revenue Acceleration", "Margin", "Cash/Debt", "Dilution", "Capex", "Free Cash Flow")),
    ("tattva.customer_evidence", "customer_evidence",
     ("Customer Win", "Customer Concentration", "Adoption Signal", "Backlog/Order Signal")),
    ("tattva.supplier_evidence", "supplier_evidence",
     ("Supplier Relationship", "Supplier-of-Supplier", "Dependency Risk", "Substitution Risk")),
    ("tattva.bottleneck_evidence", "bottleneck_evidence",
     ("Lead-Time", "Capacity Expansion", "Utilization", "Pricing Power", "Shortage Evidence",
      "Resolution Risk")),
    ("tattva.leadership_evidence", "leadership_evidence",
     ("Founder-Led", "Execution Track Record", "Capital Allocation", "Credibility Flag",
      "Dilution History")),
)


def _build_default_descriptors() -> Tuple[AgentDescriptor, ...]:
    out = []
    for agent_id, name, record, desc in _ADHARA:
        out.append(AgentDescriptor(
            agent_id=agent_id, agent_name=name, layer="Adhara", discipline="",
            agent_type="foundation", consumes=("RealityEvent", "raw_payload_ref"),
            emits=(record,), allowed_downstream_layers=("Buddhi",), description=desc))
    for agent_id, name, record, desc in _BUDDHI:
        out.append(AgentDescriptor(
            agent_id=agent_id, agent_name=name, layer="Buddhi", discipline="",
            agent_type="governance", consumes=("AgentFinding", "RealityEvent"),
            emits=(record,),
            allowed_downstream_layers=("Tattva", "Sphurana", "Nivesha", "Saarathi", "Kriya"),
            description=desc))
    for (agent_id, discipline, subagents), subtype in zip(_TATTVA, TATTVA_FINDING_SUBTYPES):
        name = agent_id.split(".", 1)[1].replace("_", " ").title()
        allowed_sources = ("rumor", "social") if discipline == "narrative" else ()
        out.append(AgentDescriptor(
            agent_id=agent_id, agent_name=name, layer="Tattva", discipline=discipline,
            agent_type="sensor", consumes=("RealityEvent",),
            emits=("AgentFinding", subtype), subagents=subagents,
            allowed_sources=allowed_sources, allowed_downstream_layers=("Tattva",),
            requires_human_review_by_default=(discipline == "narrative"),
            description="Tattva {0} sensor; emits {1} (an AgentFinding)".format(
                discipline, subtype)))
    return tuple(out)


# The built-in descriptors, built once (deterministic, order-stable).
DEFAULT_DESCRIPTORS: Tuple[AgentDescriptor, ...] = _build_default_descriptors()


def build_default_registry() -> AgentRegistry:
    """Build a registry pre-loaded with the built-in AGENT_MAP_012 descriptors (no active impl)."""
    registry = AgentRegistry()
    for descriptor in DEFAULT_DESCRIPTORS:
        registry.register(descriptor)
    return registry
