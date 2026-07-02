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
]
