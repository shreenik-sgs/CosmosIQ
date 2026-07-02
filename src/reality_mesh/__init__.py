"""Reality Mesh -- typed handoff substrate for Phase 012 (IMPLEMENTATION-012A).

The frozen, label-only, provenance/conflict/gap-preserving objects that flow between agents,
synthesizers, and layers in the Real-Time Reality Intelligence Sensor Mesh, plus the closed
label vocabularies and validation guards that keep them honest.

This slice is INFRASTRUCTURE ONLY: typed contracts + closed vocabularies + validation +
tests. There are NO agents, NO reasoning, NO scheduler / streaming / broker / trading /
scoring here. Every object is:

* **labels, not numbers** -- no numeric investability / score / rank / rating field, and no
  buy / sell / hold / order / trade / broker field anywhere;
* **evidence-preserving** -- ``source_refs`` / ``evidence_refs``, ``conflicts`` and
  ``data_gaps`` carried end-to-end; missing -> explicit gap, never a fabricated value;
* **frozen + validated on construction** -- closed labels only; empty required id rejected;
  X/social never a verified fact; manual/analyst never canonical.

Deterministic, stdlib-only, Python 3.9. No network on import; no scheduler / broker; every
timestamp is an injected string (no wall-clock in any id/replay path).
"""

from __future__ import annotations

from .labels import (
    ALLOWED_DOWNSTREAM_USES,
    CLAIM_STATUSES,
    CONFIDENCE_LABELS,
    CONTRADICTION_STATUSES,
    CORROBORATION_STATUSES,
    DEFAULT_FORBIDDEN_DOWNSTREAM_USES,
    DIRECTION_LABELS,
    DISCIPLINES,
    FORBIDDEN_DOWNSTREAM_USES,
    FRESHNESS_LABELS,
    HALF_LIFE_LABELS,
    LAYERS,
    MAGNITUDE_LABELS,
    PAYLOAD_TYPES,
    ROUTING_TARGETS,
    SOURCE_AUTHORITIES,
    THEME_PULSE_STATES,
    URGENCY_LABELS,
    authority_rank,
    is_claim_status,
    is_discipline,
    is_member,
    is_social_source,
    is_source_authority,
    is_theme_pulse_state,
    ordered_authorities,
)
from .models import (
    CORE_MODELS,
    AgentFinding,
    DiligenceInputBundle,
    HandoffEnvelope,
    OpportunityHypothesisPacket,
    RealityEvent,
    RealitySignal,
    SignalCluster,
    ThemePulse,
)
from .validation import (
    TRADE_FIELD_TOKENS,
    assert_evidence_preserved,
    assert_manual_not_canonical,
    assert_no_trade_fields,
    assert_required_ids,
    assert_social_not_verified,
    validate_envelope,
    validate_event,
    validate_finding,
    validate_labels,
    validate_signal,
    validate_theme_pulse,
)
from .agents import (
    AGENT_TYPES,
    LAYER_ALLOWED_EMITS,
    LAYER_FORBIDDEN_EMITS,
    MANDATORY_FORBIDDEN_OUTPUTS,
    TATTVA_FINDING_SUBTYPES,
    AgentDescriptor,
    SensorAgent,
    validate_descriptor,
)
from .registry import (
    DEFAULT_DESCRIPTORS,
    AgentRegistry,
    build_default_registry,
)
from .router import BuddhiRouter
from .fusion import FusionResult, TattvaSignalFusionSynthesizer
from .sphurana import SphuranaResult, ThemePulseSynthesizer
from .render_adapters import build_pulse_data_quality_panel
from .sensors import (
    MARKET_REGIME_FINDING_TYPES,
    MARKET_REGIME_SUBAGENTS,
    MarketRegimeAgent,
    events_from_fixture,
    SectorRotationAgent,
    ThemeRotationAgent,
    SECTOR_ROTATION_FINDING_TYPES,
    SECTOR_ROTATION_SUBAGENTS,
    THEME_ROTATION_FINDING_TYPES,
    THEME_ROTATION_SUBAGENTS,
    FLOW_PROXY_CAVEAT,
    BROADENING_MIN_MEMBERS,
    NewsFilingsAgent,
    NEWS_FILINGS_FINDING_TYPES,
    NEWS_FILINGS_SUBAGENTS,
    FILING_FACT_FINDINGS,
    COMPANY_CLAIM_FINDINGS,
    claim_status_of,
    SocialNarrativeAgent,
    SOCIAL_NARRATIVE_FINDING_TYPES,
    SOCIAL_NARRATIVE_SUBAGENTS,
    assert_narrative_not_verified,
)
from .nivesha_forward import (
    FORWARD_INPUT_NAMES,
    SCENARIO_LABELS,
    ForwardScenarioInput,
    ForwardScenarioCase,
    ForwardScenarioPacket,
    ForwardMappedField,
    ForwardSidecarMapping,
    build_forward_scenario_packet,
    to_nivesha_forward_sidecar,
    run_nivesha_thesis_on_forward_sidecar,
)

__all__ = [
    # models
    "RealityEvent",
    "AgentFinding",
    "HandoffEnvelope",
    "RealitySignal",
    "SignalCluster",
    "ThemePulse",
    "OpportunityHypothesisPacket",
    "DiligenceInputBundle",
    "CORE_MODELS",
    # label vocabularies
    "SOURCE_AUTHORITIES",
    "CLAIM_STATUSES",
    "DISCIPLINES",
    "DIRECTION_LABELS",
    "MAGNITUDE_LABELS",
    "URGENCY_LABELS",
    "CONFIDENCE_LABELS",
    "FRESHNESS_LABELS",
    "HALF_LIFE_LABELS",
    "CORROBORATION_STATUSES",
    "CONTRADICTION_STATUSES",
    "THEME_PULSE_STATES",
    "LAYERS",
    "ROUTING_TARGETS",
    "PAYLOAD_TYPES",
    "ALLOWED_DOWNSTREAM_USES",
    "FORBIDDEN_DOWNSTREAM_USES",
    "DEFAULT_FORBIDDEN_DOWNSTREAM_USES",
    # label helpers
    "is_member",
    "is_source_authority",
    "is_claim_status",
    "is_discipline",
    "is_theme_pulse_state",
    "is_social_source",
    "ordered_authorities",
    "authority_rank",
    # validation
    "TRADE_FIELD_TOKENS",
    "assert_no_trade_fields",
    "assert_manual_not_canonical",
    "assert_social_not_verified",
    "assert_required_ids",
    "assert_evidence_preserved",
    "validate_labels",
    "validate_event",
    "validate_finding",
    "validate_signal",
    "validate_theme_pulse",
    "validate_envelope",
    # agents / registry / router (012B)
    "AgentDescriptor",
    "SensorAgent",
    "validate_descriptor",
    "AGENT_TYPES",
    "TATTVA_FINDING_SUBTYPES",
    "LAYER_ALLOWED_EMITS",
    "LAYER_FORBIDDEN_EMITS",
    "MANDATORY_FORBIDDEN_OUTPUTS",
    "AgentRegistry",
    "build_default_registry",
    "DEFAULT_DESCRIPTORS",
    "BuddhiRouter",
    # fusion synthesizer (012C)
    "TattvaSignalFusionSynthesizer",
    "FusionResult",
    # sphurana theme-pulse synthesizer (012F)
    "ThemePulseSynthesizer",
    "SphuranaResult",
    # sensor agents (012D)
    "MarketRegimeAgent",
    "MARKET_REGIME_FINDING_TYPES",
    "MARKET_REGIME_SUBAGENTS",
    "events_from_fixture",
    # sensor agents (012E)
    "SectorRotationAgent",
    "ThemeRotationAgent",
    "SECTOR_ROTATION_FINDING_TYPES",
    "SECTOR_ROTATION_SUBAGENTS",
    "THEME_ROTATION_FINDING_TYPES",
    "THEME_ROTATION_SUBAGENTS",
    "FLOW_PROXY_CAVEAT",
    "BROADENING_MIN_MEMBERS",
    # sensor agents (012G)
    "NewsFilingsAgent",
    "NEWS_FILINGS_FINDING_TYPES",
    "NEWS_FILINGS_SUBAGENTS",
    "FILING_FACT_FINDINGS",
    "COMPANY_CLAIM_FINDINGS",
    "claim_status_of",
    # sensor agents (012H)
    "SocialNarrativeAgent",
    "SOCIAL_NARRATIVE_FINDING_TYPES",
    "SOCIAL_NARRATIVE_SUBAGENTS",
    "assert_narrative_not_verified",
    # forward scenario engine / sidecar (012I)
    "FORWARD_INPUT_NAMES",
    "SCENARIO_LABELS",
    "ForwardScenarioInput",
    "ForwardScenarioCase",
    "ForwardScenarioPacket",
    "ForwardMappedField",
    "ForwardSidecarMapping",
    "build_forward_scenario_packet",
    "to_nivesha_forward_sidecar",
    "run_nivesha_thesis_on_forward_sidecar",
    # data-quality / universe signal integration (012J)
    "build_pulse_data_quality_panel",
]
