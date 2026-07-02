# HANDOFF CONTRACT — 012 (implementation-ready)

Status: **Draft for architect review** · Companion to `AGENT_MAP_012.md`,
`ARCHITECTURE_CONTRACT_012.md`, `SPEC-012_REAL_TIME_REALITY_INTELLIGENCE_SENSOR_MESH.md`.

The typed objects that flow between agents, synthesizers, and layers in Phase 012, and the exact
handoff paths. Implementation-ready: field name · type · semantics. **No runtime code exists yet.**
Objects are intended as **frozen dataclasses** (stdlib, deterministic, offline-buildable). All
label fields draw from **closed vocabularies (labels, not numeric scores)**. Every object preserves
`evidence_refs` / `source_refs`, `conflicts`, and `data_gaps` — nothing is averaged away or hidden.

Conventions: `*_label` = a closed-vocabulary string; `*_status` = an enum; `*_ref(s)` = stable
id(s) into a store (no raw payloads inlined); `Tuple[...]` = ordered immutable. Absent/unknown → an
explicit gap entry, never a fabricated value or a silent default.

---

## 1. Core objects

### 1.1 RealityEvent — "something happened / was observed" (NOT investable)
| field | type | semantics |
|---|---|---|
| `event_id` | str | stable id |
| `timestamp` | str (ISO) | when observed (injectable for tests; no wall-clock in id path) |
| `source_id` / `source_type` | str | which source / kind |
| `source_authority` | label | canonical / primary / convenience / fallback / manual / rumor |
| `claim_status` | label | verified_fact / company_claim / analyst_estimate / inferred / manual / rumor |
| `raw_payload_ref` | ref | pointer to raw payload (never inlined) |
| `discipline` | label | which sensor discipline this belongs to |
| `event_type` | label | 8-K / market-cap-update / narrative-spike / breakout / … |
| `affected_companies/themes/sectors/value_chains` | Tuple[id] | mappings (via `adhara.identity`) |
| `observed_fact` | str | the factual observation (neutral) |
| `company_claim` | str | a company statement, if any (marked, not verified) |
| `numeric_values` | Tuple[(name,value,unit)] | raw numbers with units |
| `text_excerpt_refs` / `evidence_refs` | Tuple[ref] | supporting excerpts/evidence |
| `confidence_label` / `freshness_label` | label | quality/recency |
| `half_life` | label | how fast it decays |
| `conflicts` / `data_gaps` | Tuple[...] | preserved, never hidden |

### 1.2 AgentFinding — an agent's disciplined interpretation (NOT a trade)
| field | type | semantics |
|---|---|---|
| `finding_id` | str | stable id |
| `agent_id` / `agent_layer` / `agent_name` / `discipline` | str/label | producer + its discipline |
| `input_events` | Tuple[event_id] | events consumed |
| `finding_type` / `finding_summary` | label / str | discipline-bounded interpretation |
| `affected_companies/themes/sectors/value_chains` | Tuple[id] | scope |
| `direction_label` / `magnitude_label` / `urgency_label` | label | qualitative only |
| `confidence_label` / `freshness_label` / `half_life` | label | quality/recency/decay |
| `source_authority_summary` | label | best authority backing this finding |
| `corroboration_status` / `contradiction_status` | status | corroborated/uncorroborated; contradicted/unopposed |
| `evidence_refs` / `data_gaps` | Tuple[...] | preserved |
| `routing_targets` | Tuple[label] | which synthesizer(s) may consume it |

An agent emits `AgentFinding` ONLY (or a foundation/governance record). It never emits a signal,
opportunity, thesis, size, order, or buy/sell/hold.

### 1.3 HandoffEnvelope — who produced it, who may consume it, what is allowed/forbidden
| field | type | semantics |
|---|---|---|
| `envelope_id` / `created_at` | str | id / timestamp (injectable) |
| `from_layer` / `to_layer` | label | routing |
| `from_agent` / `to_synthesizer` | str | producer / intended synthesizer |
| `payload_type` | label | e.g. AgentFinding / TattvaSignalPacket / OpportunityHypothesisPacket |
| `payload_ids` | Tuple[id] | the wrapped objects |
| `routing_reason` | str | why routed here |
| `authority_summary` / `freshness_summary` | label | rolled-up quality |
| `conflict_summary` / `data_gap_summary` | str | preserved, surfaced |
| `requires_human_review` | bool | true whenever a decision or manual step is implied |
| `allowed_downstream_uses` | Tuple[label] | e.g. "fuse", "hypothesize", "diligence-input" |
| `forbidden_downstream_uses` | Tuple[label] | ALWAYS includes "place-order", "buy/sell/hold", "auto-execute", "score/rank" where not an accepted downstream semantic |

The envelope is the **contract of consent**: the router (`buddhi.router`) stamps `allowed_/
forbidden_downstream_uses`; a consumer that performs a forbidden use is a boundary violation.

### 1.4 RealitySignal — fused reality intelligence (what appears to be changing; NOT an opportunity)
Fields: `signal_id`, `signal_type`, `source_findings` (Tuple[finding_id]), `source_events`,
`discipline`, `affected_companies/themes/sectors/value_chains`, `direction_label`,
`magnitude_label`, `urgency_label`, `confidence_label`, `freshness_label`, `half_life`,
`corroboration_status`, `contradiction_status`, `evidence_refs`, `data_gaps`, `routing_targets`.

### 1.5 SignalCluster — related signals, conflicts preserved
Fields: `cluster_id`, `cluster_type`, `theme`, `sector`, `value_chain`, `companies`, `signals`
(Tuple[signal_id]), `breadth_label`, `crowding_label`, `momentum_label`, `conflict_label`,
`confidence_label`, `freshness_label`, `data_gaps`.

### 1.6 ThemePulse — theme forming/broadening/crowding/fading (NOT a stock pick)
Fields: `theme_pulse_id`, `theme_id`, `theme_name`, `state`, `source_signal_clusters`,
`supporting_signals`, `contradicting_signals`, `breadth_label`, `rotation_label`, `crowding_label`,
`bottleneck_label`, `beneficiary_candidates`, `risk_candidates`, `confidence_label`,
`freshness_label`, `data_gaps`.
`state ∈ { Dormant, Warming, Igniting, Broadening, Crowded, Exhausting, Breaking down, Conflicted,
Data insufficient }`.

### 1.7 OpportunityHypothesisPacket — something for Nivesha to TEST (NOT a thesis)
Fields: `hypothesis_id`, `theme_pulse` (ref), `opportunity_summary`, `value_chain_hypothesis`,
`bottleneck_hypothesis`, `beneficiary_candidates`, `loser_candidates`, `required_diligence_questions`,
`supporting_evidence_refs`, `contradicting_evidence_refs`, `confidence_label`, `data_gaps`.

### 1.8 DiligenceInputBundle — evidence-backed package Nivesha may use (gaps + conflicts preserved)
Fields: `ticker`, `company`, `opportunity_hypothesis_refs`, `enrichment_bundle_refs` (011),
`market_regime_signals`, `sector_rotation_signals`, `theme_pulse_refs`,
`financial_inflection_signals`, `technical_timing_signals`, `forward_scenario_inputs`,
`red_team_questions`, `evidence_refs`, `data_gaps`.

### 1.9 Synthesizer transport packets
- `TattvaSignalPacket` — wraps `RealitySignal` + `SignalCluster` sets for Sphurana; carries authority/
  freshness/conflict/gap summaries.
- `DiligenceConclusionPacket` — wraps `InvestmentThesis` + `CapitalCandidate` + `RedTeamAssessment` +
  `TimingConfirmation` for Saarathi.
- `PersonalizedActionPacket` — wraps `PersonalizedAction` + `SizingGuardrail` + `PortfolioFitAssessment`
  for Kriya (consumable only after explicit user intent).

---

## 2. Handoff paths

Each path: **Input → Output**, wrapped by a `HandoffEnvelope` from `buddhi.router`, with the
allowed/forbidden downstream uses fixed by the contract.

### 4.1 Source → Tattva Sensor Agent
Input: raw source payload + source metadata + timestamp + authority label. **Output: `RealityEvent`.**
Allowed downstream: "sense". Forbidden: everything decision-ward.

### 4.2 Tattva Sensor Agent → Tattva Signal Fusion Synthesizer
Input: `RealityEvent`. **Output: `AgentFinding`.** Envelope: `to_synthesizer="TattvaSignalFusion"`.
Allowed: "fuse". Forbidden: "hypothesize", "diligence", "size", "order", "buy/sell/hold".

### 4.3 Tattva Signal Fusion → Sphurana
Input: `RealitySignal` + `SignalCluster`. **Output: `TattvaSignalPacket`.**
Envelope: `to_layer="Sphurana", payload_type="TattvaSignalPacket"`. Allowed: "hypothesize".
Forbidden: "diligence-decision", "size", "order".

### 4.4 Sphurana → Nivesha
Input: `ThemePulse` + `ValueChainHypothesis` + `BottleneckHypothesis` + `BeneficiaryCandidate` +
`RiskCandidate`. **Output: `OpportunityHypothesisPacket`.**
Envelope: `to_layer="Nivesha", payload_type="OpportunityHypothesisPacket"`. Allowed: "diligence-input
/ test". Forbidden: "final-decision", "size", "order".

### 4.5 Nivesha → Saarathi
Input: `InvestmentThesis` + `CapitalCandidate` + `RedTeamAssessment` + `TimingConfirmation`.
**Output: `DiligenceConclusionPacket`.** Envelope: `to_layer="Saarathi",
payload_type="DiligenceConclusionPacket"`. Allowed: "portfolio-fit / sizing-guardrail". Forbidden:
"order", "auto-execute".

### 4.6 Saarathi → Kriya
Input: `PersonalizedAction` + `SizingGuardrail` + `PortfolioFitAssessment`. **Output:
`PersonalizedActionPacket`.** Rule: **Kriya may act only after explicit user-selected intent.**
Envelope: `requires_human_review=True`, allowed: "manual-preview". Forbidden: "place-order",
"broker-submit", "auto-execute", "buy/sell/order/submit button".

### 4.7 All layers → Data Quality
Every layer MUST emit: source coverage · confidence labels · freshness labels · data gaps ·
conflicts · unsupported claims. Rendered in the Data-Quality / diagnostics surface (011 style:
labels, not scores; data actions, not trade recs).

### 4.8 All layers → Anubhava (outcome-trackable)
These major packets carry an outcome-tracking id so Anubhava can compare to reality later:
`RealitySignal`, `ThemePulse`, `OpportunityHypothesisPacket`, `InvestmentThesis`, `CapitalCandidate`,
`PersonalizedAction`, `ManualExecutionPreview`. Anubhava never rewrites history.

---

## 3. Handoff invariants (enforced by TEST_MATRIX_012)

- Every cross-layer transfer is wrapped in a `HandoffEnvelope` with explicit `allowed_/
  forbidden_downstream_uses`; a consumer performing a forbidden use is a boundary violation.
- `forbidden_downstream_uses` for EVERY envelope includes order placement / broker submit /
  auto-execute / buy-sell-hold / hidden score-rank (except where an accepted downstream semantic
  already permits it — e.g. Nivesha's diligence conclusion, Saarathi's sizing range, Kriya's manual
  preview — and even then never an order).
- Conflicts, weak signals, and data gaps are **preserved end-to-end** — never averaged away,
  upgraded without corroboration, or dropped.
- X/social (`rumor`) never becomes a `verified_fact`; downstream high-confidence use requires
  corroboration; the envelope's `authority_summary` reflects this.
- Labels only — no numeric investability/score/rank field on any handoff object.
- Deterministic + offline: objects build from fixtures/mocks; no wall-clock in id/replay paths
  (timestamps injectable); no network on import; no secrets in any rendered output.

## Cross references
`AGENT_MAP_012.md` · `ARCHITECTURE_CONTRACT_012.md` · `SPEC-012_…SENSOR_MESH.md` ·
`TEST_MATRIX_012.md` · `IMPLEMENTATION_PLAN_012.md` · (011) `ARCHITECTURE_CONTRACT_011.md`,
`adr/ADR-CANDIDATE-011_DILIGENCE_ENRICHMENT_AS_EVIDENCE_LAYER.md`.
