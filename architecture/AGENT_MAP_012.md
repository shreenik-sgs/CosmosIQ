# AGENT MAP — 012 (implementation-ready)

Status: **Draft for architect review** · Companion to `SPEC-012_REAL_TIME_REALITY_INTELLIGENCE_SENSOR_MESH.md`,
`ARCHITECTURE_CONTRACT_012.md`, `HANDOFF_CONTRACT_012.md`.

This is the authoritative registry of agents, subagents, and their consume/emit contracts for
Phase 012. It is implementation-ready: each agent has a stable `agent_id`, a layer, a discipline,
what it consumes, what it emits, and its subagents. **No runtime code exists yet** — this defines
what 012A–012K will build.

## Governing principle (enforced by every entry below)

```
Agents OBSERVE and ANALYZE within their discipline.
Synthesizers COMBINE evidence (preserving conflicts, weak signals, gaps).
Only DOWNSTREAM LAYERS decide what the evidence means.
No agent jumps directly from signal to trade.
```

An **agent** emits an `AgentFinding` (or a foundation/governance record) bounded to its discipline —
never a `RealitySignal`, `ThemePulse`, `OpportunityHypothesis`, `InvestmentThesis`, order, or
buy/sell/hold. A **synthesizer** emits the fused/higher packet. All labels are **labels, not numeric
scores** (see ARCHITECTURE_CONTRACT_012 §E). Phase 012 is **manual/on-demand pulse** — no agent runs
on a scheduler.

Legend: **Consumes** → **Emits**. `agent_id` is stable (used by the Buddhi Agent Router + the
Anubhava outcome tracker). "Subagents" are discipline-scoped tasks that roll up into the agent's
finding; they emit no cross-layer packet of their own.

---

## 3.1 Adhāra — Foundation / Provenance / Runtime

Foundation agents emit records, not findings; they stamp every event/finding with identity,
provenance, authority, freshness, conflicts, and a security gate.

| agent_id | Tasks | Consumes | Emits |
|---|---|---|---|
| `adhara.identity` | assign stable IDs; dedupe entities; map ticker/company/CIK/theme/value-chain IDs | raw source refs, ticker lists, company metadata | `EntityIdentityRecord` |
| `adhara.provenance` | track source lineage; attach `source_refs`; preserve `raw_payload_ref` | raw payloads + refs | `ProvenanceRecord` |
| `adhara.authority` | classify source authority; enforce `SEC canonical > primary(company IR) > convenience(FMP) > manual/analyst > fallback(yfinance) > rumor(X/social)`; prevent lower from overriding higher for the same metric/period/unit | source metadata | `AuthorityAssessment` |
| `adhara.freshness` | timestamp events; assign `freshness_label`; assign `half_life`; mark stale | events + timestamps | `FreshnessAssessment` |
| `adhara.conflict` | detect conflicting values; **preserve** conflicts; route conflicts to Data Quality + Red Team | values across sources | `ConflictRecord` |
| `adhara.security_boundary` | no secrets in HTML; no keys in logs; no network on import; offline-test enforcement | build/test context | `SecurityGateResult` |

## 3.2 Buddhi — Cognitive Governance / Orchestration

Buddhi routes and governs. It never analyzes evidence; it enforces boundaries and produces the
`HandoffEnvelope` (see HANDOFF_CONTRACT_012).

| agent_id | Tasks | Consumes | Emits |
|---|---|---|---|
| `buddhi.layer_boundary` | enforce layer responsibilities; block Tattva from investment conclusions; block Sphurana from trade decisions; block Kriya from broker execution | any inter-layer packet | `ArchitectureComplianceResult` |
| `buddhi.router` | route `RealityEvent`→sensor agents; route `AgentFinding`→correct synthesizer; route conflicts→Data Quality/Red Team | events, findings, conflicts | `HandoffEnvelope` |
| `buddhi.fusion_coordinator` | coordinate Tattva Signal Fusion; avoid premature certainty; preserve competing explanations | Tattva findings | `FusionPlan` |
| `buddhi.hypothesis_discipline` | maintain competing hypotheses; prevent averaging away minority possibilities; label uncertainty | signals/hypotheses | `HypothesisSet` |
| `buddhi.gatekeeper` | enforce no scheduler / no broker / no hidden score / no fake data | any output | `GateResult` |
| `buddhi.mode_controller` | keep demo / fixture / real / enriched / **pulse** modes separate; prevent silent fallback to demo | mode + inputs | `ModeState` |

## 3.3 Tattva — Reality Intelligence / Sensor Mesh

Every Tattva agent **consumes `RealityEvent`s and emits an `AgentFinding`** (discipline-bounded).
None emits a signal, opportunity, thesis, or trade. Each agent's subagents are discipline-scoped
sensors that roll into its finding.

| agent_id | Emits (`AgentFinding` subtype) | Subagents | Detects |
|---|---|---|---|
| `tattva.macro_regime` | `MacroRegimeFinding` | Rates · Yield Curve · Dollar · Credit Spread · Inflation/Jobs Surprise · Liquidity · VIX/Volatility | liquidity tightening/easing; risk-on/off; duration pressure; macro shock |
| `tattva.market_regime` | `MarketRegimeFinding` | Index Breadth · Advance/Decline · Distribution Day · Volatility Regime · Small-Cap Risk Appetite | broad pullback; breadth deterioration; risk appetite shift |
| `tattva.sector_rotation` | `SectorRotationFinding` | Sector ETF Relative Strength · Industry Group Breadth · Volume Expansion · Institutional Flow Proxy | money into/out of sectors; leadership change; sector exhaustion |
| `tattva.theme_rotation` | `ThemeRotationFinding` | Theme Basket Builder · Theme Relative Strength · Theme Breadth · Theme Momentum · Theme Crowding | theme movement/ignition/broadening/exhaustion (Physical AI, Robotics, AI Power, Optical, Nuclear, Quantum, …) |
| `tattva.policy_geopolitical` | `PolicyGeopoliticalFinding` | War Risk · Sanctions · Tariff/Export Control · Energy Policy · Defense Policy · AI Regulation · Industrial Policy | policy/geopolitical tailwinds or risks; map to sectors/value-chains |
| `tattva.news_filings` | `NewsFilingFinding` | 8-K · S-3/ATM · Insider Sale · Press Release · Contract Announcement · Guidance Update · Partnership | faster-than-quarterly events; dilution risk; contract validation; guidance changes |
| `tattva.narrative` | `NarrativeFinding` | Verified Account · Expert Account · Journalist · Promoter/Bot-Risk · Narrative Velocity · Rumor Propagation · Crowding | attention spikes; narrative velocity; rumor spread; crowding; bot/promoter risk |
| `tattva.options_flow` | `OptionsFlowFinding` | Unusual Volume · IV Expansion · Skew · Gamma Zone Proxy · Expiration Pressure | speculative pressure; squeeze risk; event-vol buildup; IV crush risk |
| `tattva.technical_regime` | `TechnicalRegimeFinding` | Compression · Breakout · EMA Stack · VWAP · Failure/Reversal · Overextension | setup forming; breakout confirm; failed breakout; overextension; tactical timing |
| `tattva.financial_inflection` | `FinancialInflectionFinding` | Revenue Acceleration · Margin · Cash/Debt · Dilution · Capex · Free Cash Flow | business acceleration/deterioration; balance-sheet risk; dilution pressure |
| `tattva.customer_evidence` | `CustomerEvidenceFinding` | Customer Win · Customer Concentration · Adoption Signal · Backlog/Order Signal | demand validation; concentration risk; early adoption |
| `tattva.supplier_evidence` | `SupplierEvidenceFinding` | Supplier Relationship · Supplier-of-Supplier · Dependency Risk · Substitution Risk | supplier dependencies/bottlenecks; substitution risk |
| `tattva.bottleneck_evidence` | `BottleneckEvidenceFinding` | Lead-Time · Capacity Expansion · Utilization · Pricing Power · Shortage Evidence · Resolution Risk | bottleneck intensity/easing; pricing power; capacity-ramp feasibility |
| `tattva.leadership_evidence` | `LeadershipEvidenceFinding` | Founder-Led · Execution Track Record · Capital Allocation · Credibility Flag · Dilution History | management-quality evidence; credibility risk; capital-allocation behavior |

**`tattva.narrative` (X/Social) special rules** — X **never confirms facts**; it emits **weak /
narrative signals only**; downstream high-confidence use **requires corroboration** by a
higher-authority source. Authority = `rumor`. Bot/promoter risk is flagged, not filtered silently.

## 3.4 Tattva Signal Fusion Synthesizer

The first synthesizer. Consumes **all Tattva `AgentFinding`s** + `RealityEvent`s +
`AuthorityAssessment`/`FreshnessAssessment`/`ConflictRecord`; emits fused reality intelligence.
**Never** creates an investment thesis or buy/sell/hold.

| agent_id | Subagents | Emits |
|---|---|---|
| `tattva.signal_fusion` | Freshness Fusion · Authority Fusion · Correlation · Contradiction · Noise Filter · Confirmation · Signal Packet Builder | `RealitySignal`, `SignalCluster`, `TattvaSignalPacket` + signal Data-Quality diagnostics |

Tasks: normalize findings; cluster related findings; apply half-life; **preserve conflicts**; keep
weak signals weak; mark corroborated vs uncorroborated; build `RealitySignal`/`SignalCluster`.

## 3.5 Sphurana — Opportunity Generation / Theme Pulse

Agents consume `RealitySignal`/`SignalCluster` and produce theme/opportunity hypotheses. **Never** a
final investment decision.

| agent_id | Tasks | Emits |
|---|---|---|
| `sphurana.theme_pulse` | assign theme state (Dormant/Warming/Igniting/Broadening/Crowded/Exhausting/Breaking down/Conflicted/Data insufficient) | `ThemePulse` |
| `sphurana.megatrend` | detect multiple related themes forming a larger capital cycle | `MegatrendHypothesis` |
| `sphurana.value_chain_discovery` | map theme → economic chain; identify layers + missing layers | `ValueChainHypothesis` |
| `sphurana.bottleneck` | identify constrained resource; assess bottleneck candidate; duration/severity labels | `BottleneckHypothesis` |
| `sphurana.beneficiary` | map companies → possible beneficiary role; mark directness to bottleneck | `BeneficiaryCandidate` |
| `sphurana.loser_disruption` | identify companies harmed by theme/bottleneck | `RiskCandidate` |
| `sphurana.crowding` | detect over-attention / narrative crowding / squeeze-crowded risk | `CrowdingAssessment` |
| `sphurana.opportunity_hypothesis` | combine ThemePulse + value-chain + bottleneck + beneficiary/risk → packet | `OpportunityHypothesisPacket` |

## 3.6 Nivesha — Investment Diligence / Capital Candidate

Consumes `OpportunityHypothesisPacket` + `DiligenceEnrichmentBundle` (011) + regime/inflection/
timing/red-team signals. May produce diligence conclusions; **does not submit orders, bypass
Saarathi, or treat weak signals as verified facts.**

| agent_id | Tasks | Emits |
|---|---|---|
| `nivesha.company_positioning` | test directness to value-chain/bottleneck; is the company an actual beneficiary | `CompanyPositioningAssessment` |
| `nivesha.forward_revenue` | evaluate NRE / design wins / pre-production contracts / backlog / ramp / pipeline conversion | `ForwardRevenueAssessment` |
| `nivesha.scenario_engine` | build base/upside/downside/delay/dilution scenarios | `ForwardScenario` |
| `nivesha.valuation` | future EV/sales, EV/EBITDA where applicable, margin expansion, dilution-adjusted up/downside | `ValuationAssessment` |
| `nivesha.financial_inflection` | test revenue/margin/cash/dilution trajectory | `FinancialDiligenceAssessment` |
| `nivesha.leadership_diligence` | test execution quality, capital allocation, credibility, dilution behavior | `LeadershipDiligenceAssessment` |
| `nivesha.red_team` | thesis breakers; false-positive risks; overvaluation/dilution/hype risks | `RedTeamAssessment` |
| `nivesha.timing_confirmation` | consume technical + market regime signals; assess tactical timing | `TimingConfirmation` |
| `nivesha.market_recognition` | under-recognized vs crowded vs euphoric | `MarketRecognitionAssessment` |
| `nivesha.capital_candidate` | synthesize Nivesha assessments → diligence conclusion | `CapitalCandidate`, `InvestmentThesis` |

## 3.7 Saarathi — Personal CIO / Portfolio Fit / Sizing Guardrails

Consumes `CapitalCandidate`/`InvestmentThesis` + portfolio state + user constraints + risk budget +
concentration. Emits fit + **sizing guardrail RANGES**. Never submits an order or forces action.

| agent_id | Emits |
|---|---|
| `saarathi.portfolio_exposure` · `saarathi.risk_budget` · `saarathi.correlation` · `saarathi.liquidity` · `saarathi.rotation` · `saarathi.personal_constraint` · `saarathi.conviction_to_size_guardrail` | `PortfolioFitAssessment`, `SizingGuardrail`, `PersonalizedAction`, `ConcentrationWarning` |

## 3.8 Kriya — Manual Execution Preview

Consumes `PersonalizedAction` **only after explicit user intent**. Emits preview + audit. **No
broker order, no order placement, no buy/sell/order/submit button, no automatic execution.**

| agent_id | Emits |
|---|---|
| `kriya.manual_ticket` · `kriya.execution_risk` · `kriya.manual_order_simulation` · `kriya.slippage_awareness` · `kriya.audit` | `ManualExecutionIntent`, `ManualExecutionPreview`, `ExecutionRiskDisclosure`, `AuditRecord` |

## 3.9 Anubhava — Outcome Learning

Consumes past signals/hypotheses/theses + outcomes/price-action/follow-through/timing/red-team
outcomes. **Never rewrites history or retroactively fabricates certainty.**

| agent_id | Emits |
|---|---|
| `anubhava.outcome_tracker` · `anubhava.signal_accuracy` · `anubhava.thesis_review` · `anubhava.timing_review` · `anubhava.red_team_review` · `anubhava.archetype_learning` · `anubhava.experience_layer_update` | `OutcomeRecord`, `SignalReliabilityUpdate`, `ThesisPostmortem`, `TimingLearning`, `ArchetypeUpdate`, `ExperienceLayerUpdate` |

---

## Registry summary (for `012B` agent registry)

- Foundation: 6 agents (Adhāra). Governance: 6 (Buddhi). Sensor mesh: 14 Tattva agents (+ ~70
  subagents). Synthesizers: Tattva Signal Fusion, Sphurana (8), Nivesha (10), Saarathi (7), Kriya
  (5), Anubhava (7).
- Every agent: stable `agent_id`, one layer, one discipline, typed consume/emit, subagents.
- Discipline agents emit `AgentFinding` (or a foundation/governance record) ONLY. Cross-layer
  packets are emitted by synthesizers ONLY. All wrapped in a `HandoffEnvelope` by `buddhi.router`.
- Enforcement: `buddhi.layer_boundary` + `buddhi.gatekeeper` + `adhara.security_boundary` +
  the TEST_MATRIX_012 boundary tests. Any agent emitting outside its contract is a NO at the gate.

## Cross references
`SPEC-012_REAL_TIME_REALITY_INTELLIGENCE_SENSOR_MESH.md` · `ARCHITECTURE_CONTRACT_012.md` ·
`HANDOFF_CONTRACT_012.md` · `TEST_MATRIX_012.md` · `IMPLEMENTATION_PLAN_012.md` · (011)
`ARCHITECTURE_CONTRACT_011.md`.
