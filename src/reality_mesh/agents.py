"""Agent descriptors + the SensorAgent interface for the Reality Mesh (IMPLEMENTATION-012B).

INFRASTRUCTURE ONLY. This module defines *what an agent is* and *what it is permitted to
emit* -- it contains NO real sensor logic, NO synthesis, NO scheduler / streaming / broker /
trading / scoring. It extends the accepted 012A handoff substrate (:mod:`reality_mesh.models`
/ :mod:`reality_mesh.labels` / :mod:`reality_mesh.validation`).

Two things live here:

* :class:`AgentDescriptor` -- a frozen, self-validating declaration of an agent's identity,
  layer, discipline, consume/emit contract, subagents, allowed sources / downstream layers,
  and forbidden outputs. On construction it enforces the ARCHITECTURE_CONTRACT_012 §A/§E/§F
  invariants that can be checked structurally: a valid layer + discipline, the four mandatory
  forbidden outputs, and the **LAYER-EMIT rule** (a descriptor's ``emits`` must be a subset of
  what its layer may emit -- so a Tattva agent can never declare an OpportunityHypothesis /
  InvestmentThesis / order / buy-sell output, and NO agent may declare a broker / auto-execute
  / hidden-score / investability-score output).
* :class:`SensorAgent` -- the abstract interface every discipline agent implements: a
  ``descriptor`` property + a deterministic ``run(context, events) -> Tuple[AgentFinding, ...]``.
  The concrete :meth:`SensorAgent.run_checked` wrapper enforces the runtime half of the
  invariant: inputs must be :class:`RealityEvent`s, and every output must be an
  :class:`AgentFinding` within the agent's discipline carrying no trade / broker / score field.

Deterministic, stdlib-only, Python 3.9. No network on import; no scheduler / broker; no
wall-clock. Labels, not numbers.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Tuple

from . import labels as _labels
from .models import AgentFinding, RealityEvent
from .validation import assert_no_trade_fields

# --------------------------------------------------------------------------- #
# Closed vocabularies specific to the agent layer                              #
# --------------------------------------------------------------------------- #

# The kind of participant a descriptor describes. Foundation/governance/sensor are the three
# built-in kinds this slice loads; the others are declared for future synthesizer/layer slices.
AGENT_TYPES = frozenset(
    {
        "foundation",
        "governance",
        "sensor",
        "synthesizer",
        "diligence",
        "portfolio",
        "execution_preview",
        "learning",
    }
)

# The four outputs that are ALWAYS forbidden for ANY agent -- merged into every descriptor's
# ``forbidden_outputs`` exactly like :class:`HandoffEnvelope` merges its forbidden uses.
MANDATORY_FORBIDDEN_OUTPUTS: Tuple[str, ...] = (
    "broker_order",
    "auto_execute",
    "buy_sell_recommendation",
    "hidden_score",
)

# Substring tokens that may NEVER appear in an ``emits`` type name (labels, not trades /
# numbers). A declared output containing any of these is a boundary violation.
FORBIDDEN_EMIT_TOKENS: Tuple[str, ...] = (
    "buy", "sell", "hold", "order", "submit", "broker", "auto_execute",
    "hidden_score", "investab", "score", "rank", "rating",
)

# The 14 Tattva AgentFinding subtypes (AGENT_MAP_012 §3.3). A Tattva sensor emits one of these
# (each IS an AgentFinding) plus the base ``AgentFinding`` type name -- nothing else.
TATTVA_FINDING_SUBTYPES: Tuple[str, ...] = (
    "MacroRegimeFinding",
    "MarketRegimeFinding",
    "SectorRotationFinding",
    "ThemeRotationFinding",
    "PolicyGeopoliticalFinding",
    "NewsFilingFinding",
    "NarrativeFinding",
    "OptionsFlowFinding",
    "TechnicalRegimeFinding",
    "FinancialInflectionFinding",
    "CustomerEvidenceFinding",
    "SupplierEvidenceFinding",
    "BottleneckEvidenceFinding",
    "LeadershipEvidenceFinding",
)

# What each layer is permitted to emit (AGENT_MAP_012 §3.1-§3.9 / ARCHITECTURE_CONTRACT_012 §6).
# A descriptor's ``emits`` MUST be a subset of its layer's set. Layers without an entry
# (DataQuality / RedTeam) are diagnostic surfaces with no built-in agent in this slice; their
# emits are still token-checked but not subset-restricted.
LAYER_ALLOWED_EMITS = {
    "Adhara": frozenset(
        {
            "EntityIdentityRecord",
            "ProvenanceRecord",
            "AuthorityAssessment",
            "FreshnessAssessment",
            "ConflictRecord",
            "SecurityGateResult",
        }
    ),
    "Buddhi": frozenset(
        {
            "ArchitectureComplianceResult",
            "HandoffEnvelope",
            "FusionPlan",
            "HypothesisSet",
            "GateResult",
            "ModeState",
        }
    ),
    "Tattva": frozenset({"AgentFinding"}) | frozenset(TATTVA_FINDING_SUBTYPES),
    "Sphurana": frozenset(
        {
            "ThemePulse",
            "MegatrendHypothesis",
            "ValueChainHypothesis",
            "BottleneckHypothesis",
            "BeneficiaryCandidate",
            "RiskCandidate",
            "CrowdingAssessment",
            "OpportunityHypothesisPacket",
        }
    ),
    "Nivesha": frozenset(
        {
            "CompanyPositioningAssessment",
            "ForwardRevenueAssessment",
            "ForwardScenario",
            "ValuationAssessment",
            "FinancialDiligenceAssessment",
            "LeadershipDiligenceAssessment",
            "RedTeamAssessment",
            "TimingConfirmation",
            "MarketRecognitionAssessment",
            "CapitalCandidate",
            "InvestmentThesis",
        }
    ),
    "Saarathi": frozenset(
        {
            "PortfolioFitAssessment",
            "SizingGuardrail",
            "PersonalizedAction",
            "ConcentrationWarning",
        }
    ),
    "Kriya": frozenset(
        {
            "ManualExecutionIntent",
            "ManualExecutionPreview",
            "ExecutionRiskDisclosure",
            "AuditRecord",
        }
    ),
    "Anubhava": frozenset(
        {
            "OutcomeRecord",
            "SignalReliabilityUpdate",
            "ThesisPostmortem",
            "TimingLearning",
            "ArchetypeUpdate",
            "ExperienceLayerUpdate",
        }
    ),
}

# Explicit cross-layer emits a layer may NEVER declare (ARCHITECTURE_CONTRACT_012 §6). The
# subset rule above already excludes these; this map gives a precise, testable error message
# and a second, independent guard.
LAYER_FORBIDDEN_EMITS = {
    "Tattva": frozenset(
        {
            "RealitySignal",
            "SignalCluster",
            "ThemePulse",
            "OpportunityHypothesisPacket",
            "InvestmentThesis",
            "CapitalCandidate",
            "PersonalizedAction",
            "ManualExecutionPreview",
            "ManualExecutionIntent",
        }
    ),
    "Sphurana": frozenset(
        {"InvestmentThesis", "PersonalizedAction", "ManualExecutionPreview"}
    ),
    "Nivesha": frozenset({"PersonalizedAction", "ManualExecutionPreview"}),
    "Saarathi": frozenset({"ManualExecutionPreview"}),
    "Kriya": frozenset({"broker_order", "auto_execute"}),
}


# --------------------------------------------------------------------------- #
# AgentDescriptor                                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentDescriptor:
    """A frozen, self-validating declaration of one agent's identity + consume/emit contract.

    Validated on construction (``__post_init__``): non-empty ``agent_id``; ``layer`` is one of
    the 8+ registry layers; ``discipline`` is a member of the closed discipline vocabulary (or
    an explicit gap for a foundation/governance agent); the four mandatory forbidden outputs are
    merged into ``forbidden_outputs``; and the LAYER-EMIT rule holds (``emits`` is a subset of
    what the layer may emit and contains no trade / broker / score token). An X/social
    (``narrative``) descriptor defaults to weak/narrative/rumor sources and may not declare a
    ``canonical`` / ``verified_fact`` source.
    """

    agent_id: str = ""
    agent_name: str = ""
    layer: str = ""
    discipline: str = ""
    agent_type: str = ""
    consumes: Tuple[str, ...] = field(default_factory=tuple)
    emits: Tuple[str, ...] = field(default_factory=tuple)
    subagents: Tuple[str, ...] = field(default_factory=tuple)
    allowed_sources: Tuple[str, ...] = field(default_factory=tuple)
    allowed_downstream_layers: Tuple[str, ...] = field(default_factory=tuple)
    forbidden_outputs: Tuple[str, ...] = field(
        default_factory=lambda: tuple(MANDATORY_FORBIDDEN_OUTPUTS))
    requires_human_review_by_default: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or self.agent_id.strip() == "":
            raise ValueError("AgentDescriptor.agent_id is required and must be non-empty")
        if self.layer not in _labels.LAYERS:
            raise ValueError(
                "AgentDescriptor.layer {0!r} is not a registry layer (allowed: {1})".format(
                    self.layer, sorted(_labels.LAYERS)))
        if not _labels.is_member(_labels.DISCIPLINES, self.discipline):
            raise ValueError(
                "AgentDescriptor.discipline {0!r} is not a closed discipline".format(
                    self.discipline))
        if self.agent_type != "" and self.agent_type not in AGENT_TYPES:
            raise ValueError(
                "AgentDescriptor.agent_type {0!r} is not a known agent type".format(
                    self.agent_type))
        for dl in self.allowed_downstream_layers:
            if dl not in _labels.LAYERS:
                raise ValueError(
                    "AgentDescriptor.allowed_downstream_layers has unknown layer {0!r}".format(dl))

        # Merge in the mandatory forbidden outputs (order-stable, deduped) -- an agent can never
        # omit the broker/auto-execute/buy-sell/hidden-score prohibition.
        merged = list(self.forbidden_outputs)
        for out in MANDATORY_FORBIDDEN_OUTPUTS:
            if out not in merged:
                merged.append(out)
        object.__setattr__(self, "forbidden_outputs", tuple(merged))

        # X/social (narrative) discipline: weak/narrative/rumor by default; never canonical/fact.
        if self.discipline == _labels.NARRATIVE_DISCIPLINE:
            for banned in ("canonical", "verified_fact"):
                if banned in self.allowed_sources:
                    raise ValueError(
                        "narrative (X/social) descriptor may not declare a {0!r} source".format(
                            banned))
            if not self.allowed_sources:
                object.__setattr__(self, "allowed_sources", ("rumor", "social"))

        self._validate_emits()

    # -- LAYER-EMIT rule ---------------------------------------------------- #
    def _validate_emits(self) -> None:
        for out in self.emits:
            low = out.lower()
            for tok in FORBIDDEN_EMIT_TOKENS:
                if tok in low:
                    raise ValueError(
                        "{0}: forbidden output {1!r} (trade/score not permitted)".format(
                            self.agent_id, out))
            forbidden_here = LAYER_FORBIDDEN_EMITS.get(self.layer, frozenset())
            if out in forbidden_here:
                raise ValueError(
                    "{0}: layer {1} may not emit {2!r}".format(self.agent_id, self.layer, out))
            allowed_here = LAYER_ALLOWED_EMITS.get(self.layer)
            if allowed_here is not None and out not in allowed_here:
                raise ValueError(
                    "{0}: layer {1} may not emit {2!r} (allowed: {3})".format(
                        self.agent_id, self.layer, out, sorted(allowed_here)))


def validate_descriptor(descriptor: AgentDescriptor) -> None:
    """Re-assert the ARCHITECTURE_CONTRACT_012 descriptor invariants (callable for the registry).

    A constructed :class:`AgentDescriptor` is already valid (``__post_init__``); this makes the
    same guarantees explicit + introspectable so the registry can reject a hand-rolled or
    tampered descriptor. Raises ``ValueError`` on a violation.
    """
    if not isinstance(descriptor, AgentDescriptor):
        raise TypeError("validate_descriptor expects an AgentDescriptor")
    if descriptor.layer not in _labels.LAYERS:
        raise ValueError("descriptor.layer {0!r} invalid".format(descriptor.layer))
    if not _labels.is_member(_labels.DISCIPLINES, descriptor.discipline):
        raise ValueError("descriptor.discipline {0!r} invalid".format(descriptor.discipline))
    for out in MANDATORY_FORBIDDEN_OUTPUTS:
        if out not in descriptor.forbidden_outputs:
            raise ValueError(
                "descriptor missing mandatory forbidden output {0!r}".format(out))
    # LAYER-EMIT rule (re-run, independent of construction).
    descriptor._validate_emits()


# --------------------------------------------------------------------------- #
# SensorAgent interface                                                       #
# --------------------------------------------------------------------------- #
class SensorAgent(abc.ABC):
    """The abstract interface every discipline agent implements.

    A sensor OBSERVES within its discipline: it consumes :class:`RealityEvent`s and emits
    :class:`AgentFinding`s ONLY. It performs no synthesis, no scheduling, no network access, and
    has no side effects. Subclasses provide :attr:`descriptor` and a deterministic :meth:`run`;
    :meth:`run_checked` enforces the boundary at runtime.
    """

    @property
    @abc.abstractmethod
    def descriptor(self) -> AgentDescriptor:
        """The agent's frozen :class:`AgentDescriptor`."""

    @abc.abstractmethod
    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Deterministically interpret ``events`` into findings. No side effects, no network."""

    # -- boundary-enforcing wrapper ---------------------------------------- #
    def run_checked(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Run the agent, enforcing the ARCHITECTURE_CONTRACT_012 §A/§E/§F runtime invariant.

        (a) every input must be a :class:`RealityEvent`; (b) every output must be an
        :class:`AgentFinding` within the agent's discipline; (c) no output may carry a
        trade / broker / score field (reuses 012A :func:`assert_no_trade_fields`). Raises
        ``TypeError`` for a bad input, ``AssertionError`` for a trade/score field, and
        ``ValueError`` for a non-finding / out-of-discipline output.
        """
        for ev in events:
            if not isinstance(ev, RealityEvent):
                raise TypeError(
                    "{0}: inputs must be RealityEvents, got {1}".format(
                        self.descriptor.agent_id, type(ev).__name__))

        outputs = self.run(context, events)
        desc = self.descriptor
        for out in outputs:
            # Structural guard first: reject any trade/broker/score-bearing output.
            if is_dataclass(out):
                assert_no_trade_fields(out)
            if not isinstance(out, AgentFinding):
                raise ValueError(
                    "{0}: an agent may emit AgentFinding ONLY, got {1}".format(
                        desc.agent_id, type(out).__name__))
            if desc.discipline and out.discipline and out.discipline != desc.discipline:
                raise ValueError(
                    "{0}: out-of-discipline finding {1!r} (agent discipline {2!r})".format(
                        desc.agent_id, out.discipline, desc.discipline))
        return tuple(outputs)
