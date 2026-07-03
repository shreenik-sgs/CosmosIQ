"""Frozen, label-only handoff objects for the Reality Mesh (IMPLEMENTATION-012A).

The typed objects that flow between agents, synthesizers, and layers in Phase 012, exactly
as specified in ``HANDOFF_CONTRACT_012.md``. Every object is a **frozen dataclass**
(stdlib, deterministic, offline-buildable) validated on construction.

CRITICAL DISCIPLINE baked into the shape (ARCHITECTURE_CONTRACT_012 §A/§E/§F):

* **Labels, not numbers.** There is NO numeric investability / score / rank / rating field,
  and NO buy / sell / hold / order / trade / broker field on ANY object. Quality and state
  are QUALITATIVE labels drawn from the closed vocabularies in :mod:`reality_mesh.labels`.
* **Evidence preserved end-to-end.** Every evidence-bearing object keeps its
  ``source_refs`` / ``evidence_refs``, its ``conflicts``, and its ``data_gaps`` -- nothing
  is averaged away, upgraded without corroboration, or hidden.
* **Consent is explicit.** A :class:`HandoffEnvelope` carries ``allowed_downstream_uses``
  and ``forbidden_downstream_uses``; its default forbidden set ALWAYS includes
  ``broker_order`` / ``auto_execute`` / ``buy_sell_recommendation`` / ``hidden_score``.
* **Missing is explicit.** Collections default to empty tuples via ``field(default_factory
  =tuple)``; an everything-missing object yields explicit gaps, never an invented value.
* **Frozen + validated on construction.** ``__post_init__`` rejects an empty required id,
  an out-of-vocabulary label, a social claim marked ``verified_fact``, or a manual/analyst
  datum marked ``canonical`` -- raising ``ValueError``.

Deterministic, stdlib-only, Python 3.9. No network on import; timestamps are injected
strings (no wall-clock in any id/replay path).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Tuple

from . import labels as _labels


# --------------------------------------------------------------------------- #
# Internal validation shared by every model's __post_init__                     #
# --------------------------------------------------------------------------- #
def _require_ids(obj, names: Tuple[str, ...]) -> None:
    """Raise ValueError if any named required-id field is empty/blank."""
    for name in names:
        value = getattr(obj, name, "")
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(
                "{0}.{1} is a required id and must be non-empty".format(
                    type(obj).__name__, name))


def _normalize_layer_fields(obj, names) -> None:
    """Canonicalise the named layer fields to their approved English value (in place).

    Backward compatibility: a legacy Sanskrit layer name (or a display label) is rewritten to
    its English serialized value BEFORE label validation, so any old value still validates.
    """
    for name in names:
        value = getattr(obj, name, "")
        if value:
            object.__setattr__(obj, name, _labels.normalize_layer(value))


def _validate_labels(obj) -> None:
    """Validate every closed-label field of ``obj`` against its vocabulary.

    A scalar label must be "" (explicit gap) or a member of its closed set; every element
    of a tuple-label field must be a member (no empty elements). Any violation -> ValueError.
    """
    for f in fields(obj):
        value = getattr(obj, f.name)
        if f.name in _labels.SCALAR_LABEL_VOCABULARIES:
            vocab = _labels.SCALAR_LABEL_VOCABULARIES[f.name]
            if not _labels.is_member(vocab, value):
                raise ValueError(
                    "{0}.{1}: invalid label {2!r} (allowed: {3})".format(
                        type(obj).__name__, f.name, value, sorted(vocab)))
        elif f.name in _labels.TUPLE_LABEL_VOCABULARIES:
            vocab = _labels.TUPLE_LABEL_VOCABULARIES[f.name]
            for element in value:
                if element not in vocab:
                    raise ValueError(
                        "{0}.{1}: invalid label {2!r} (allowed: {3})".format(
                            type(obj).__name__, f.name, element, sorted(vocab)))


def _guard_provenance(obj) -> None:
    """Enforce the two provenance invariants where the relevant fields are present.

    * A manual / analyst datum is NEVER canonical.
    * An X/social (narrative) event/finding is NEVER a ``verified_fact`` (rumor/narrative
      unless explicitly ``company_claim`` / ``reported_claim``).
    * A ``rumor``-authority datum is NEVER a ``verified_fact`` -- a rumor-tier source cannot
      confirm a fact however its discipline / source_type is marked (ARCHITECTURE_CONTRACT_012 §C).
    """
    authority = getattr(obj, "source_authority", "") or getattr(obj, "source_authority_summary", "")
    claim = getattr(obj, "claim_status", "")
    if authority == "canonical" and claim in ("manual", "analyst_estimate"):
        raise ValueError(
            "{0}: a manual/analyst datum may never be marked canonical".format(
                type(obj).__name__))

    if claim == "verified_fact":
        discipline = getattr(obj, "discipline", "")
        source_type = getattr(obj, "source_type", "")
        if _labels.is_social_source(source_type=source_type, discipline=discipline):
            raise ValueError(
                "{0}: an X/social (narrative) claim may never be a verified_fact".format(
                    type(obj).__name__))
        if authority == "rumor":
            raise ValueError(
                "{0}: a rumor-authority source may never produce a verified_fact".format(
                    type(obj).__name__))


# --------------------------------------------------------------------------- #
# 1.1 RealityEvent -- "something happened / was observed" (NOT investable)      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RealityEvent:
    """A single observed reality event. Factual, discipline-tagged -- never a signal."""
    event_id: str = ""
    timestamp: str = ""                     # ISO string, injected (no wall-clock)
    source_id: str = ""
    source_type: str = ""
    source_authority: str = ""              # closed: SOURCE_AUTHORITIES
    claim_status: str = ""                  # closed: CLAIM_STATUSES
    raw_payload_ref: str = ""               # pointer, never inlined
    discipline: str = ""                    # closed: DISCIPLINES
    event_type: str = ""                    # descriptive kind (8-K / breakout / ...)
    affected_companies: Tuple[str, ...] = field(default_factory=tuple)
    affected_themes: Tuple[str, ...] = field(default_factory=tuple)
    affected_sectors: Tuple[str, ...] = field(default_factory=tuple)
    affected_value_chains: Tuple[str, ...] = field(default_factory=tuple)
    observed_fact: str = ""
    company_claim: str = ""                 # a company statement, marked (not verified)
    numeric_values: Tuple[Tuple[str, object, str], ...] = field(default_factory=tuple)
    text_excerpt_refs: Tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"       # closed: CONFIDENCE_LABELS
    freshness_label: str = "missing"        # closed: FRESHNESS_LABELS
    half_life: str = ""                     # closed: HALF_LIFE_LABELS
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_ids(self, ("event_id",))
        # An X/social event defaults to rumor authority + rumor claim (never fabricated fact).
        if _labels.is_social_source(source_type=self.source_type, discipline=self.discipline):
            if self.source_authority == "":
                object.__setattr__(self, "source_authority", "rumor")
            if self.claim_status == "":
                object.__setattr__(self, "claim_status", "rumor")
        _validate_labels(self)
        _guard_provenance(self)


# --------------------------------------------------------------------------- #
# 1.2 AgentFinding -- an agent's disciplined interpretation (NOT a trade)       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentFinding:
    """A discipline-bounded interpretation. An agent emits ONLY this (or a foundation record)."""
    finding_id: str = ""
    agent_id: str = ""
    agent_layer: str = ""
    agent_name: str = ""
    discipline: str = ""                    # closed: DISCIPLINES
    input_events: Tuple[str, ...] = field(default_factory=tuple)
    finding_type: str = ""
    finding_summary: str = ""
    affected_companies: Tuple[str, ...] = field(default_factory=tuple)
    affected_themes: Tuple[str, ...] = field(default_factory=tuple)
    affected_sectors: Tuple[str, ...] = field(default_factory=tuple)
    affected_value_chains: Tuple[str, ...] = field(default_factory=tuple)
    direction_label: str = ""               # closed: DIRECTION_LABELS
    magnitude_label: str = ""               # closed: MAGNITUDE_LABELS
    urgency_label: str = ""                 # closed: URGENCY_LABELS
    confidence_label: str = "missing"       # closed: CONFIDENCE_LABELS
    freshness_label: str = "missing"        # closed: FRESHNESS_LABELS
    half_life: str = ""                     # closed: HALF_LIFE_LABELS
    source_authority_summary: str = ""      # closed: SOURCE_AUTHORITIES
    corroboration_status: str = ""          # closed: CORROBORATION_STATUSES
    contradiction_status: str = ""          # closed: CONTRADICTION_STATUSES
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    routing_targets: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_ids(self, ("finding_id", "agent_id"))
        _normalize_layer_fields(self, ("agent_layer",))
        _validate_labels(self)
        _guard_provenance(self)


# --------------------------------------------------------------------------- #
# 1.3 HandoffEnvelope -- the contract of consent (who may consume, what's allowed) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HandoffEnvelope:
    """Wraps a cross-layer transfer with explicit allowed / forbidden downstream uses.

    ``forbidden_downstream_uses`` ALWAYS includes the four default-forbidden uses
    (``broker_order`` / ``auto_execute`` / ``buy_sell_recommendation`` / ``hidden_score``);
    they are merged in on construction so an envelope can never omit them.
    """
    envelope_id: str = ""
    created_at: str = ""                    # injected timestamp
    from_layer: str = ""                    # closed: LAYERS
    to_layer: str = ""                      # closed: LAYERS
    from_agent: str = ""
    to_synthesizer: str = ""
    payload_type: str = ""                  # closed: PAYLOAD_TYPES
    payload_ids: Tuple[str, ...] = field(default_factory=tuple)
    routing_reason: str = ""
    authority_summary: str = ""             # closed: SOURCE_AUTHORITIES
    freshness_summary: str = ""             # closed: FRESHNESS_LABELS
    conflict_summary: str = ""
    data_gap_summary: str = ""
    requires_human_review: bool = False
    allowed_downstream_uses: Tuple[str, ...] = field(default_factory=tuple)
    forbidden_downstream_uses: Tuple[str, ...] = field(
        default_factory=lambda: tuple(sorted(_labels.DEFAULT_FORBIDDEN_DOWNSTREAM_USES)))

    def __post_init__(self) -> None:
        _require_ids(self, ("envelope_id",))
        # Merge in the mandatory default-forbidden uses (order-stable, deduped).
        merged = list(self.forbidden_downstream_uses)
        for use in sorted(_labels.DEFAULT_FORBIDDEN_DOWNSTREAM_USES):
            if use not in merged:
                merged.append(use)
        object.__setattr__(self, "forbidden_downstream_uses", tuple(merged))
        _normalize_layer_fields(self, ("from_layer", "to_layer"))
        _validate_labels(self)

    def permits(self, use: str) -> bool:
        """True iff ``use`` is explicitly allowed and not forbidden."""
        return use in self.allowed_downstream_uses and use not in self.forbidden_downstream_uses


# --------------------------------------------------------------------------- #
# 1.4 RealitySignal -- fused reality intelligence (NOT an opportunity)          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RealitySignal:
    """Fused reality intelligence: what appears to be changing. Emitted by a synthesizer only."""
    signal_id: str = ""
    signal_type: str = ""
    source_findings: Tuple[str, ...] = field(default_factory=tuple)
    source_events: Tuple[str, ...] = field(default_factory=tuple)
    discipline: str = ""                    # closed: DISCIPLINES
    affected_companies: Tuple[str, ...] = field(default_factory=tuple)
    affected_themes: Tuple[str, ...] = field(default_factory=tuple)
    affected_sectors: Tuple[str, ...] = field(default_factory=tuple)
    affected_value_chains: Tuple[str, ...] = field(default_factory=tuple)
    direction_label: str = ""               # closed: DIRECTION_LABELS
    magnitude_label: str = ""               # closed: MAGNITUDE_LABELS
    urgency_label: str = ""                 # closed: URGENCY_LABELS
    confidence_label: str = "missing"       # closed: CONFIDENCE_LABELS
    freshness_label: str = "missing"        # closed: FRESHNESS_LABELS
    half_life: str = ""                     # closed: HALF_LIFE_LABELS
    corroboration_status: str = ""          # closed: CORROBORATION_STATUSES
    contradiction_status: str = ""          # closed: CONTRADICTION_STATUSES
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    routing_targets: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_ids(self, ("signal_id",))
        _validate_labels(self)
        _guard_provenance(self)


# --------------------------------------------------------------------------- #
# 1.5 SignalCluster -- related signals, conflicts preserved                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SignalCluster:
    """A cluster of related signals with conflicts preserved (never averaged away)."""
    cluster_id: str = ""
    cluster_type: str = ""
    theme: str = ""
    sector: str = ""
    value_chain: str = ""
    companies: Tuple[str, ...] = field(default_factory=tuple)
    signals: Tuple[str, ...] = field(default_factory=tuple)
    breadth_label: str = ""                 # closed: MAGNITUDE_LABELS
    crowding_label: str = ""                # closed: MAGNITUDE_LABELS
    momentum_label: str = ""                # closed: DIRECTION_LABELS
    conflict_label: str = ""                # closed: MAGNITUDE_LABELS
    confidence_label: str = "missing"       # closed: CONFIDENCE_LABELS
    freshness_label: str = "missing"        # closed: FRESHNESS_LABELS
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_ids(self, ("cluster_id",))
        _validate_labels(self)


# --------------------------------------------------------------------------- #
# 1.6 ThemePulse -- theme forming/broadening/crowding/fading (NOT a stock pick) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ThemePulse:
    """A theme's state (Dormant..Data insufficient). Contradictions preserved on the pulse."""
    theme_pulse_id: str = ""
    theme_id: str = ""
    theme_name: str = ""
    state: str = ""                         # closed: THEME_PULSE_STATES
    source_signal_clusters: Tuple[str, ...] = field(default_factory=tuple)
    supporting_signals: Tuple[str, ...] = field(default_factory=tuple)
    contradicting_signals: Tuple[str, ...] = field(default_factory=tuple)
    breadth_label: str = ""                 # closed: MAGNITUDE_LABELS
    rotation_label: str = ""                # closed: DIRECTION_LABELS
    crowding_label: str = ""                # closed: MAGNITUDE_LABELS
    bottleneck_label: str = ""              # closed: MAGNITUDE_LABELS
    beneficiary_candidates: Tuple[str, ...] = field(default_factory=tuple)
    risk_candidates: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"       # closed: CONFIDENCE_LABELS
    freshness_label: str = "missing"        # closed: FRESHNESS_LABELS
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_ids(self, ("theme_pulse_id",))
        _validate_labels(self)


# --------------------------------------------------------------------------- #
# 1.7 OpportunityHypothesisPacket -- something for Nivesha to TEST (NOT a thesis) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OpportunityHypothesisPacket:
    """A hypothesis for Nivesha to TEST. Carries diligence questions + both-sided evidence."""
    hypothesis_id: str = ""
    theme_pulse: str = ""                   # ref
    opportunity_summary: str = ""
    value_chain_hypothesis: str = ""
    bottleneck_hypothesis: str = ""
    beneficiary_candidates: Tuple[str, ...] = field(default_factory=tuple)
    loser_candidates: Tuple[str, ...] = field(default_factory=tuple)
    required_diligence_questions: Tuple[str, ...] = field(default_factory=tuple)
    supporting_evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    contradicting_evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"       # closed: CONFIDENCE_LABELS
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_ids(self, ("hypothesis_id",))
        _validate_labels(self)


# --------------------------------------------------------------------------- #
# 1.8 DiligenceInputBundle -- evidence-backed package Nivesha may use            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DiligenceInputBundle:
    """Evidence-backed inputs Nivesha may use, with gaps + conflicts preserved."""
    ticker: str = ""
    company: str = ""
    opportunity_hypothesis_refs: Tuple[str, ...] = field(default_factory=tuple)
    enrichment_bundle_refs: Tuple[str, ...] = field(default_factory=tuple)   # 011 bundles
    market_regime_signals: Tuple[str, ...] = field(default_factory=tuple)
    sector_rotation_signals: Tuple[str, ...] = field(default_factory=tuple)
    theme_pulse_refs: Tuple[str, ...] = field(default_factory=tuple)
    financial_inflection_signals: Tuple[str, ...] = field(default_factory=tuple)
    technical_timing_signals: Tuple[str, ...] = field(default_factory=tuple)
    forward_scenario_inputs: Tuple[str, ...] = field(default_factory=tuple)
    red_team_questions: Tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"       # closed: CONFIDENCE_LABELS

    def __post_init__(self) -> None:
        _require_ids(self, ("ticker",))
        _validate_labels(self)


# The eight core handoff objects (for registry / test introspection).
CORE_MODELS = (
    RealityEvent,
    AgentFinding,
    HandoffEnvelope,
    RealitySignal,
    SignalCluster,
    ThemePulse,
    OpportunityHypothesisPacket,
    DiligenceInputBundle,
)
