"""Closed label vocabularies for the Reality Mesh handoff substrate (IMPLEMENTATION-012A).

Phase 012 is **labels, not numbers**. Every quality / state / provenance field on a
handoff object draws from a CLOSED vocabulary defined here -- never a numeric score, rank,
or rating. This module is pure, deterministic, stdlib-only metadata: the closed sets plus
membership helpers. It performs NO network access, reads NO secrets, imports NO scheduler /
broker / streaming module.

The ``source_authority`` vocabulary is REUSED verbatim from the accepted evidence-ingestion
authority order (``evidence_ingestion.source_model``) so 012 cannot silently weaken the
010/011 provenance ladder ``canonical > primary > convenience > fallback > manual > rumor``.

Conventions (from HANDOFF_CONTRACT_012):

* ``*_label`` = a closed-vocabulary quality/qualitative string.
* ``*_status`` = a closed-vocabulary enum-like string.
* The empty string ``""`` is the universal UNSPECIFIED / gap sentinel: it is accepted by
  every membership check (an absent label is an explicit gap, never a fabricated value),
  while any NON-empty value MUST be a member of its closed set or validation raises.
"""

from __future__ import annotations

from typing import FrozenSet, Iterable, Tuple

# Reuse the accepted authority ladder + its total order. Do NOT redefine or weaken it.
from evidence_ingestion.source_model import (  # noqa: F401  (authority_rank re-exported)
    SOURCE_AUTHORITIES,
    authority_rank,
)

# --------------------------------------------------------------------------- #
# Provenance vocabularies                                                      #
# --------------------------------------------------------------------------- #

# Kind of assertion a datum/event is. Extends the 011 claim-status set with the two
# narrative-era members required by ARCHITECTURE_CONTRACT_012 §C: ``reported_claim``
# (a third party reported it) and ``rumor`` (X/social, never a verified fact).
CLAIM_STATUSES: FrozenSet[str] = frozenset(
    {
        "verified_fact",
        "company_claim",
        "reported_claim",
        "analyst_estimate",
        "inferred",
        "manual",
        "rumor",
    }
)

# The 14 Tattva sensor disciplines (AGENT_MAP_012 §3.3) plus ``cross_discipline`` for a
# fused signal that spans several. A discipline agent is bounded to exactly one of these.
DISCIPLINES: FrozenSet[str] = frozenset(
    {
        "macro_regime",
        "market_regime",
        "sector_rotation",
        "theme_rotation",
        "policy_geopolitical",
        "news_filings",
        "narrative",
        "options_flow",
        "technical_regime",
        "financial_inflection",
        "customer_evidence",
        "supplier_evidence",
        "bottleneck_evidence",
        "leadership_evidence",
        "cross_discipline",
    }
)

# The narrative / X-social discipline is special: authority = rumor, never verified_fact.
NARRATIVE_DISCIPLINE = "narrative"

# Source-type tokens that mark an event as X/social narrative (rumor by default). Matched
# EXACTLY (used for the constructor's rumor-default behaviour, so a benign token like a bare
# "x" cannot flip an unrelated source_type into social by accident).
SOCIAL_SOURCE_TYPES: FrozenSet[str] = frozenset(
    {"x", "twitter", "social", "narrative", "reddit", "stocktwits", "rumor"}
)

# Multi-character SUBSTRING tokens denoting an X/social source_type. Matched as a substring
# by the ``assert_social_not_verified`` guard so a rumor-tier source cannot smuggle a
# ``verified_fact`` past the boundary however its source_type is spelled. Deliberately no
# bare single-letter token (no false positives from an unrelated source_type).
SOCIAL_SOURCE_SUBSTRINGS: Tuple[str, ...] = (
    "x_social", "x.com", "social", "twitter", "stocktwits", "reddit",
)


def is_social_source_type(source_type: str) -> bool:
    """True iff ``source_type`` contains an X/social substring token (spelling-tolerant)."""
    low = source_type.lower()
    return any(tok in low for tok in SOCIAL_SOURCE_SUBSTRINGS)

# --------------------------------------------------------------------------- #
# Qualitative quality / state vocabularies (labels, NOT numbers)               #
# --------------------------------------------------------------------------- #

DIRECTION_LABELS: FrozenSet[str] = frozenset(
    {
        "improving",
        "deteriorating",
        "accelerating",
        "decelerating",
        "rising",
        "falling",
        "stable",
        "mixed",
        "neutral",
        "reversing",
        "unknown",
    }
)

MAGNITUDE_LABELS: FrozenSet[str] = frozenset(
    {"negligible", "minor", "moderate", "major", "extreme", "unknown"}
)

URGENCY_LABELS: FrozenSet[str] = frozenset(
    {"none", "low", "watch", "elevated", "high", "immediate", "unknown"}
)

# ``missing`` is the default for an unpopulated object (aligns with the 011 convention).
CONFIDENCE_LABELS: FrozenSet[str] = frozenset(
    {"missing", "very_low", "low", "moderate", "high", "very_high", "unknown"}
)

FRESHNESS_LABELS: FrozenSet[str] = frozenset(
    {"missing", "fresh", "recent", "aging", "stale", "expired", "unknown"}
)

# How fast an observation decays -- a label, never a numeric half-life.
HALF_LIFE_LABELS: FrozenSet[str] = frozenset(
    {"minutes", "hours", "days", "weeks", "months", "quarters", "years", "permanent", "unknown"}
)

CORROBORATION_STATUSES: FrozenSet[str] = frozenset(
    {"corroborated", "partially_corroborated", "uncorroborated", "unknown"}
)

CONTRADICTION_STATUSES: FrozenSet[str] = frozenset(
    {"contradicted", "disputed", "unopposed", "unknown"}
)

# The Sphurana theme-pulse state machine (HANDOFF_CONTRACT_012 §1.6). Verbatim spelling.
THEME_PULSE_STATES: FrozenSet[str] = frozenset(
    {
        "Dormant",
        "Warming",
        "Igniting",
        "Broadening",
        "Crowded",
        "Exhausting",
        "Breaking down",
        "Conflicted",
        "Data insufficient",
    }
)

# --------------------------------------------------------------------------- #
# Runtime vocabularies (IMPLEMENTATION-013A -- Phase-013 runtime objects)       #
# --------------------------------------------------------------------------- #

# Honestly-labelled pulse-run modes (RUNTIME_CONTRACT_013 §1). ``demo`` stays the DEFAULT;
# a real/pulse mode is always explicit -- there is never a silent demo fall-back.
RUN_MODES: FrozenSet[str] = frozenset(
    {"demo", "fixture", "real_evidence_on_demand", "enriched", "pulse"}
)

# How a pulse was triggered. ``manual`` has been allowed since Phase 013. ``scheduled`` is
# UNLOCKED as of Phase 015B (ADR-CANDIDATE-015): it is recorded ONLY by the explicitly-started
# pulse orchestrator (one synchronous tick, never a daemon), and every scheduled run carries
# the CadencePolicy ``policy_id`` that scheduled it (``scheduled_by_policy:<id>`` in
# ``PulseRun.generated_outputs`` + an audit attribution). ``streaming`` stays RESERVED/DEFERRED
# (rejected at construction until a later phase + its own ADR). The full closed vocabulary is
# kept so the reserved member is named (and provably rejected), but only
# ``ALLOWED_TRIGGER_TYPES`` may be constructed.
ALLOWED_TRIGGER_TYPES: FrozenSet[str] = frozenset({"manual", "scheduled"})
RESERVED_TRIGGER_TYPES: FrozenSet[str] = frozenset({"streaming"})
TRIGGER_TYPES: FrozenSet[str] = ALLOWED_TRIGGER_TYPES | RESERVED_TRIGGER_TYPES

# Overall run / data-quality status (RUNTIME_CONTRACT_013 §1; OBSERVABILITY_CONTRACT_013 §2).
# A degraded / partial run still renders Data Quality; ``blocked_by_policy`` is a gate refusal.
RUN_STATUSES: FrozenSet[str] = frozenset(
    {"healthy", "degraded", "failed", "blocked_by_policy"}
)
# ``data_quality_status`` draws from the same closed set.
DATA_QUALITY_STATUSES: FrozenSet[str] = RUN_STATUSES

# The five allowed outcomes of one agent run (RUNTIME_CONTRACT_013 §3). A ``failed`` /
# ``blocked_by_policy`` result NEVER crashes the pulse -- it becomes a health record + a gap.
AGENT_RUN_STATUSES: FrozenSet[str] = frozenset(
    {"success", "partial", "failed", "skipped", "blocked_by_policy"}
)

# Rolling health states for agents / sources / the run (OBSERVABILITY_CONTRACT_013 §2).
HEALTH_STATES: FrozenSet[str] = frozenset(
    {
        "healthy",
        "degraded",
        "failed",
        "blocked_by_policy",
        "stale",
        "credentials_missing",
        "rate_limited",
        "source_unavailable",
    }
)


# --------------------------------------------------------------------------- #
# Routing vocabularies                                                         #
# --------------------------------------------------------------------------- #

# Layers a HandoffEnvelope may route between (011/012 layer registry).
#
# MIGRATION (LAYER SYSTEM): the eight architectural layers are now serialized with their
# APPROVED ENGLISH identifiers. The retired Sanskrit names (Adhara/Buddhi/Tattva/...) are kept
# working through ``LEGACY_LAYER_ALIASES`` + :func:`normalize_layer`, so any legacy value still
# validates and is canonicalised to its English form. ``DataQuality`` / ``RedTeam`` are
# diagnostic surfaces (never Sanskrit) and are unchanged.
LAYERS: FrozenSet[str] = frozenset(
    {
        "foundation",
        "intelligence_governance",
        "reality_intelligence",
        "opportunity_discovery",
        "investment_diligence",
        "portfolio_intelligence",
        "execution_preview",
        "learning_feedback",
        "DataQuality",
        "RedTeam",
    }
)

# Human-facing display label for each serialized layer value (value -> "… Layer").
LAYER_DISPLAY = {
    "foundation": "Foundation Layer",
    "intelligence_governance": "Intelligence Governance Layer",
    "reality_intelligence": "Reality Intelligence Layer",
    "opportunity_discovery": "Opportunity Discovery Layer",
    "investment_diligence": "Investment Diligence Layer",
    "portfolio_intelligence": "Portfolio Intelligence Layer",
    "execution_preview": "Execution Preview Layer",
    "learning_feedback": "Learning & Feedback Layer",
    "DataQuality": "Data Quality Layer",
    "RedTeam": "Red Team Layer",
}

# Retired Sanskrit layer name -> approved English serialized value. The compatibility layer:
# every legacy identifier maps to exactly one English value so old data / callers still validate.
LEGACY_LAYER_ALIASES = {
    "adhara": "foundation",
    "buddhi": "intelligence_governance",
    "tattva": "reality_intelligence",
    "sphurana": "opportunity_discovery",
    "nivesha": "investment_diligence",
    "saarathi": "portfolio_intelligence",
    "kriya": "execution_preview",
    "anubhava": "learning_feedback",
}

# Case-insensitive lookup for normalize_layer(): legacy names, English values, and display
# forms all resolve to the canonical English serialized value. Built once, deterministic.
_LAYER_NORMALIZE_INDEX = {}
for _new_value in LAYERS:
    _LAYER_NORMALIZE_INDEX[_new_value.lower()] = _new_value
for _legacy, _canonical in LEGACY_LAYER_ALIASES.items():
    _LAYER_NORMALIZE_INDEX[_legacy.lower()] = _canonical
for _value, _display in LAYER_DISPLAY.items():
    _LAYER_NORMALIZE_INDEX[_display.lower()] = _value
del _new_value, _legacy, _canonical, _value, _display


def normalize_layer(value: str) -> str:
    """Return the approved English serialized layer value for ``value``.

    Accepts a legacy Sanskrit name, an English serialized value, or a display label (any
    case). The empty string (explicit gap) passes through unchanged. An UNKNOWN value is
    returned as-is so downstream membership validation can reject it with a precise error.
    """
    if not value:
        return value
    return _LAYER_NORMALIZE_INDEX.get(value.strip().lower(), value)


# Which synthesizer(s) / surfaces a finding or signal may be routed to. ``SignalFusion`` is the
# migrated name of the reality-intelligence signal-fusion synthesizer; the retired
# ``TattvaSignalFusion`` token is retained so legacy routing values still validate.
ROUTING_TARGETS: FrozenSet[str] = frozenset(
    {
        "SignalFusion",
        "TattvaSignalFusion",
        "Sphurana",
        "Nivesha",
        "Saarathi",
        "Kriya",
        "DataQuality",
        "RedTeam",
        "Anubhava",
    }
)

# The kinds of wrapped payload a HandoffEnvelope may carry.
PAYLOAD_TYPES: FrozenSet[str] = frozenset(
    {
        "RealityEvent",
        "AgentFinding",
        "RealitySignal",
        "SignalCluster",
        "ThemePulse",
        "OpportunityHypothesisPacket",
        "DiligenceInputBundle",
        "TattvaSignalPacket",
        "DiligenceConclusionPacket",
        "PersonalizedActionPacket",
    }
)

# --------------------------------------------------------------------------- #
# Consent vocabularies -- allowed vs forbidden downstream uses                 #
# --------------------------------------------------------------------------- #

# Accepted downstream SEMANTICS a consumer may perform (the envelope's "consent").
ALLOWED_DOWNSTREAM_USES: FrozenSet[str] = frozenset(
    {
        "sense",
        "fuse",
        "hypothesize",
        "diligence-input",
        "test",
        "portfolio-fit",
        "sizing-guardrail",
        "manual-preview",
        "data-quality",
        "outcome-track",
        "red-team",
    }
)

# Uses that are ALWAYS forbidden (a consumer performing one is a boundary violation).
FORBIDDEN_DOWNSTREAM_USES: FrozenSet[str] = frozenset(
    {
        "broker_order",
        "auto_execute",
        "buy_sell_recommendation",
        "hidden_score",
        "place-order",
        "broker-submit",
        "buy_sell_hold",
        "score_rank",
        "final-decision",
        "size",
        "order",
    }
)

# The four forbidden uses that MUST appear on EVERY HandoffEnvelope by default
# (ARCHITECTURE_CONTRACT_012 §A/§E/§F; HANDOFF_CONTRACT_012 §3).
DEFAULT_FORBIDDEN_DOWNSTREAM_USES: FrozenSet[str] = frozenset(
    {"broker_order", "auto_execute", "buy_sell_recommendation", "hidden_score"}
)

# --------------------------------------------------------------------------- #
# Field -> closed vocabulary registry (single source for validation)          #
# --------------------------------------------------------------------------- #

# Scalar label fields: field name -> its closed vocabulary. Used by validation.py so the
# rules live in exactly one place.
SCALAR_LABEL_VOCABULARIES = {
    "source_authority": SOURCE_AUTHORITIES,
    "source_authority_summary": SOURCE_AUTHORITIES,
    "authority_summary": SOURCE_AUTHORITIES,
    "claim_status": CLAIM_STATUSES,
    "discipline": DISCIPLINES,
    "direction_label": DIRECTION_LABELS,
    "magnitude_label": MAGNITUDE_LABELS,
    "urgency_label": URGENCY_LABELS,
    "confidence_label": CONFIDENCE_LABELS,
    "freshness_label": FRESHNESS_LABELS,
    "freshness_summary": FRESHNESS_LABELS,
    "half_life": HALF_LIFE_LABELS,
    "corroboration_status": CORROBORATION_STATUSES,
    "contradiction_status": CONTRADICTION_STATUSES,
    "state": THEME_PULSE_STATES,
    "from_layer": LAYERS,
    "to_layer": LAYERS,
    "payload_type": PAYLOAD_TYPES,
    # cluster/pulse qualitative labels reuse existing closed sets
    "breadth_label": MAGNITUDE_LABELS,
    "crowding_label": MAGNITUDE_LABELS,
    "momentum_label": DIRECTION_LABELS,
    "conflict_label": MAGNITUDE_LABELS,
    "rotation_label": DIRECTION_LABELS,
    "bottleneck_label": MAGNITUDE_LABELS,
}

# Tuple-of-label fields: field name -> the closed vocabulary each element must belong to.
TUPLE_LABEL_VOCABULARIES = {
    "routing_targets": ROUTING_TARGETS,
    "allowed_downstream_uses": ALLOWED_DOWNSTREAM_USES,
    "forbidden_downstream_uses": FORBIDDEN_DOWNSTREAM_USES,
}


# --------------------------------------------------------------------------- #
# Membership helpers                                                           #
# --------------------------------------------------------------------------- #
def is_member(vocabulary: FrozenSet[str], value: str, allow_empty: bool = True) -> bool:
    """True iff ``value`` is in ``vocabulary`` (empty string allowed as an explicit gap)."""
    if allow_empty and value == "":
        return True
    return value in vocabulary


def all_members(vocabulary: FrozenSet[str], values: Iterable[str]) -> bool:
    """True iff every value is a member of ``vocabulary`` (empty elements are NOT allowed)."""
    return all(v in vocabulary for v in values)


def is_source_authority(value: str) -> bool:
    """True iff ``value`` is a member of the (reused) source-authority ladder."""
    return is_member(SOURCE_AUTHORITIES, value)


def is_claim_status(value: str) -> bool:
    return is_member(CLAIM_STATUSES, value)


def is_discipline(value: str) -> bool:
    return is_member(DISCIPLINES, value)


def is_theme_pulse_state(value: str) -> bool:
    return is_member(THEME_PULSE_STATES, value)


def is_confidence_label(value: str) -> bool:
    return is_member(CONFIDENCE_LABELS, value)


def is_freshness_label(value: str) -> bool:
    return is_member(FRESHNESS_LABELS, value)


def is_routing_target(value: str) -> bool:
    return is_member(ROUTING_TARGETS, value, allow_empty=False)


def is_allowed_use(value: str) -> bool:
    return is_member(ALLOWED_DOWNSTREAM_USES, value, allow_empty=False)


def is_forbidden_use(value: str) -> bool:
    return is_member(FORBIDDEN_DOWNSTREAM_USES, value, allow_empty=False)


def is_social_source(source_type: str = "", discipline: str = "") -> bool:
    """True iff an event's discipline / source_type marks it as X/social narrative."""
    return discipline == NARRATIVE_DISCIPLINE or source_type.lower() in SOCIAL_SOURCE_TYPES


def ordered_authorities() -> Tuple[str, ...]:
    """The reused authorities, strongest first (for display / tests)."""
    return tuple(sorted(SOURCE_AUTHORITIES, key=authority_rank, reverse=True))


# --------------------------------------------------------------------------- #
# Runtime membership helpers (013A)                                            #
# --------------------------------------------------------------------------- #
def is_run_mode(value: str) -> bool:
    return is_member(RUN_MODES, value)


def is_trigger_type(value: str) -> bool:
    """True iff ``value`` is an ALLOWED (constructible) trigger type -- ``manual`` or
    ``scheduled`` (the latter unlocked by 015B per ADR-CANDIDATE-015).

    ``streaming`` is RESERVED and returns False (rejected at construction).
    """
    return is_member(ALLOWED_TRIGGER_TYPES, value)


def is_reserved_trigger_type(value: str) -> bool:
    """True iff ``value`` is a RESERVED/DEFERRED trigger type (``streaming``)."""
    return value in RESERVED_TRIGGER_TYPES


def is_run_status(value: str) -> bool:
    return is_member(RUN_STATUSES, value)


def is_agent_run_status(value: str) -> bool:
    return is_member(AGENT_RUN_STATUSES, value)


def is_health_state(value: str) -> bool:
    return is_member(HEALTH_STATES, value)
