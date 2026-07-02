# SPEC-012 — Real-Time Reality Intelligence Sensor Mesh

Status: **Draft for architect review** · Phase: 012 · Depends on: 010 (complete), 011 (complete),
`architecture/ARCHITECTURE_CONTRACT_011.md`.
Type: design-guidance specification (architecture/, not generated `specification/`).

> Governs Phase 012. Changes NO runtime behaviour. Companion documents:
> `ARCHITECTURE_CONTRACT_012.md` (invariants), **`AGENT_MAP_012.md`** (agent registry — most
> important), **`HANDOFF_CONTRACT_012.md`** (typed objects + paths — most important),
> `TEST_MATRIX_012.md` (required tests), `IMPLEMENTATION_PLAN_012.md` (sub-milestones).

## 0. Honesty framing — "real-time" ≠ scheduled

The architecture is a **sensor mesh** capable of near-real-time, multi-discipline reasoning. **Phase
012 runs it in MANUAL / ON-DEMAND "pulse" mode only** — a human triggers one pulse (e.g.
`tattva_pulse --watchlist …`), which reads current data once and reasons over it. There is **no
scheduler, no streaming, no background job, no automated refresh, and no automated trading**.
Continuous "real-time mode" is **deferred and is NOT the default**; enabling it requires separate
approval and a new ADR. The name describes the *capability*, not the *operating mode* of this phase.

## 1. Purpose

Extend the accepted diligence-research MVP into a disciplined **multi-agent reality-intelligence
mesh**: many narrow discipline agents observe reality within their lane, synthesizers fuse their
evidence (preserving conflicts, weak signals, and gaps), and only the accepted downstream layers
decide what the evidence means — up to a **manual execution preview**, never an order.

## 2. Core principle (the whole phase enforces this)

```
Agents observe and analyze within their discipline.
Synthesizers combine evidence.
Only downstream layers decide what the evidence means.
No agent jumps directly from signal to trade.
```

## 3. Scope

- Typed **handoff objects** (`HANDOFF_CONTRACT_012.md`): RealityEvent, AgentFinding, HandoffEnvelope,
  RealitySignal, SignalCluster, ThemePulse, OpportunityHypothesisPacket, DiligenceInputBundle (+
  synthesizer transport packets).
- The **agent registry** (`AGENT_MAP_012.md`): Adhāra foundation, Buddhi governance/orchestration, a
  14-agent Tattva sensor mesh (+ ~70 subagents), and the synthesizer chain (Tattva Signal Fusion →
  Sphurana → Nivesha → Saarathi → Kriya → Anubhava).
- The **synthesizer chain** and the flow through `Tattva → Sphurana → Nivesha → Saarathi → Kriya →
  Anubhava`.
- Fixture/mock-backed, deterministic, offline. Manual/on-demand pulse. Integration into the accepted
  Economic Universe terrain + Data Quality (011) for signals.

## 4. Non-goals (all of Phase 012)

- No scheduler, background jobs, automated refresh, streaming, or automated trading.
- No broker automation / order placement; no buy/sell/hold/order/submit affordance.
- No hidden scoring/ranking, no numeric investability metric, no stock-first ranking.
- Real-time (continuous) mode is NOT default and is out of scope here.
- No weakening of source authority; no fabricating missing data; no silent demo fallback.
- No change to accepted Tattva/Sphurana/Nivesha/Saarathi/Kriya *reasoning semantics* beyond adding
  the agentic input/fusion structure around them.

## 5. Accepted foundation (010 + 011)

Economic Universe UI + `UniverseTerrain` (010B); evidence-ingested + real on-demand + watchlist
terrain (010C–E); data-quality/theme diagnostics as labels (010F); closed interaction graph (010G);
diligence enrichment as an **evidence layer** (011A–C), the Nivesha-ready **handoff-only** input
adapter (011D), the E2E matrix (011E), and operator docs + `--enrich` (011F). Source authority
(`SEC canonical > company IR primary > FMP convenience > yfinance fallback > manual > rumor`) and the
execution/security boundaries are inherited unchanged.

## 6. Conceptual handoff model

Defined field-by-field in `HANDOFF_CONTRACT_012.md`. Summary of intent:
- **RealityEvent** — "something happened / was observed." Not investable.
- **AgentFinding** — an agent's disciplined interpretation of events. Not a trade.
- **HandoffEnvelope** — who produced it, who may consume it, and what the consumer is allowed/
  forbidden to do (the contract of consent).
- **RealitySignal / SignalCluster** — fused reality intelligence; what appears to be changing;
  conflicts + weak signals preserved. Not an opportunity yet.
- **ThemePulse** — whether a theme is forming/broadening/crowding/fading. Not a stock pick.
- **OpportunityHypothesisPacket** — something for Nivesha to test. Not a thesis.
- **DiligenceInputBundle** — the evidence-backed package Nivesha may use; gaps + conflicts preserved.

## 7. Synthesizer chain

Multiple synthesizers, each with strict responsibilities (full consume/emit in `AGENT_MAP_012.md`):
1. **Tattva Signal Fusion** — findings+events → `RealitySignal`/`SignalCluster` + signal diagnostics.
   Never a thesis or buy/sell.
2. **Sphurana Opportunity** — signals/clusters → `ThemePulse` + `OpportunityHypothesisPacket` (+
   value-chain/bottleneck/beneficiary/loser). Never a final decision.
3. **Nivesha Diligence** — hypothesis + enrichment + regime/inflection/timing/red-team →
   `InvestmentThesis` / `CapitalCandidate` / `ForwardScenario` / `RedTeamAssessment` /
   `TimingConfirmation`. Never places orders; never bypasses Saarathi.
4. **Saarathi Portfolio** — candidate + portfolio/constraints → `PortfolioFitAssessment` /
   `SizingGuardrail` (RANGES) / `PersonalizedAction` / `ConcentrationWarning`. Never submits/forces.
5. **Kriya Manual Preview** — personalized action + explicit user intent → `ManualExecutionIntent` /
   `ManualExecutionPreview` / `ExecutionRiskDisclosure` / `AuditRecord`. **No broker order, no
   buy/sell button.**
6. **Anubhava Learning** — past packets + outcomes → `OutcomeRecord` / `SignalReliabilityUpdate` /
   `ThesisPostmortem` / `TimingLearning` / `ArchetypeUpdate` / `ExperienceLayerUpdate`. Never rewrites
   history or fabricates certainty.

## 8. End-to-end flow

```
sources (manual pulse) → Adhāra (identity/provenance/authority/freshness/conflict/security)
  → Tattva sensor agents (AgentFindings, discipline-bounded)
  → Tattva Signal Fusion (RealitySignal / SignalCluster; conflicts preserved)
  → Sphurana (ThemePulse → OpportunityHypothesisPacket)
  → Nivesha (diligence: thesis / capital candidate / red-team / timing)  [+ 011 enrichment inputs]
  → Saarathi (portfolio fit + sizing guardrail RANGES → personalized action)
  → Kriya (manual execution PREVIEW only, after explicit user intent; broker order: none)
  → Anubhava (outcome learning; calibration; never rewrites history)
  → Data Quality / Economic Universe (labels, gaps, conflicts, provenance)
```

Every hop is wrapped in a `HandoffEnvelope` (Buddhi router) with allowed/forbidden downstream uses.

## 9. Label discipline (no hidden scoring)

Every quality/state field is a **label** from a closed vocabulary — `direction_/magnitude_/urgency_/
confidence_/freshness_` labels, `half_life`, `corroboration_/contradiction_status`, theme `state`,
`breadth_/crowding_/momentum_/rotation_/bottleneck_` labels, `claim_status`. **No numeric
investability/score/rank field** appears on any agent output, finding, signal, pulse, hypothesis, or
packet. VisualEncoding (if any signal reaches the UI) stays presentation of existing labels/facts.

## 10. Integration with the accepted product (011)

Signals/pulses surface in the Economic Universe terrain + Data Quality as **evidence** (labels +
gaps + provenance + conflicts), never as a ranking. Demo stays the default; a new **pulse mode** is
explicit and separate from demo/fixture/real/enriched; no silent fallback. A potential operator CLI:

```bash
PYTHONPATH=src python3 -m tattva_pulse --watchlist IREN,AAOI,AMBA,OUST \
  --themes physical-ai,robotics,ai-power --out generated/tattva_pulse
```
Manual/on-demand only. No scheduler in Phase 012 unless separately approved (new ADR).

## 11. Acceptance gate (summary; full gate in TEST_MATRIX_012 + GATE-011 globals)

A slice is acceptable only if: the `ARCHITECTURE_CONTRACT_012` invariants hold; agents emit only
within their contract; every cross-layer transfer is a `HandoffEnvelope` with correct allowed/
forbidden uses; conflicts/weak-signals/gaps are preserved; labels-not-scores; manual/on-demand (no
scheduler/real-time-default); no broker/order/affordance; no secrets; whole suite offline +
deterministic; demo default byte-identical; and the accepted 011 layer/authority/execution/security
boundaries are unbroken. Verdict YES / PARTIAL / NO with evidence.

## 12. Proposed sub-milestones

`012A` contracts · `012B` agent registry + SensorAgent interface · `012C` Tattva Signal Fusion ·
`012D` Market Regime Agent (fixture) · `012E` Sector + Theme Rotation Agents (fixture) · `012F`
Sphurana Theme Pulse synthesizer · `012G` News/Filings/Press-Release Agent · `012H` X/Social
Narrative Agent (weak-signal only) · `012I` Nivesha Forward-Scenario engine spec/adapter · `012J`
Data Quality + Economic Universe signal integration · `012K` CLI/operator docs + E2E tests. Detailed
in `IMPLEMENTATION_PLAN_012.md`.

## 13. Open decisions

1. Package/module home for the mesh (`src/reality_mesh/`? `src/tattva_sensors/`?) and the pulse CLI
   (`tattva_pulse` vs `universe_ui --mode pulse`).
2. Which sensor agents ship first from **local/fixtured** data vs which require a (deferred) real
   transport (X/social, options flow, institutional-flow proxies are the hardest to source safely).
3. How pulses persist for Anubhava outcome tracking without a scheduler or DB (fixture/journal file?).
4. Whether ThemePulse/RealitySignal render in the Economic Universe now (012J) or after more agents.
5. Governance of the X/social agent's rumor handling and bot/promoter flags.
6. Whether any of this warrants promotion into the frozen `specification/` (needs an ADR).

## 14. Risks

- **Signal→trade leakage** — an agent or synthesizer producing a decision/order → contract §agentic +
  handoff forbidden-uses + gate.
- **Averaging away conflict** — fusion hiding minority/contradicting signals → preserve-conflicts
  tests.
- **Rumor laundering** — X/social becoming "fact" → authority=rumor + corroboration-required tests.
- **Hidden scoring** — a numeric composite sneaking in → labels-not-scores gate.
- **Scheduler creep** — "real-time" tempting a background loop → manual/on-demand + no-scheduler gate.
- **Secret/network leakage** — new sources fetching on import/in tests → offline + single-boundary +
  no-secret gate.
- **Over-build** — ~14 agents + ~70 subagents is large; sequence fixture-backed slices and keep each
  small + gated.

## 15. This task

SPEC-012 is **specification only**. It adds no runtime code, no scheduler, no broker, no scoring, no
secrets. It records the agent taxonomy, handoff contracts, synthesizer chain, and plan for architect
review before any 012 build begins.

## 16. Cross references
`ARCHITECTURE_CONTRACT_012.md` · `AGENT_MAP_012.md` · `HANDOFF_CONTRACT_012.md` · `TEST_MATRIX_012.md`
· `IMPLEMENTATION_PLAN_012.md` · (011) `SPEC-011_END_TO_END_DILIGENCE_RESEARCH_MVP.md`,
`ARCHITECTURE_CONTRACT_011.md`, `adr/ADR-CANDIDATE-011_DILIGENCE_ENRICHMENT_AS_EVIDENCE_LAYER.md` ·
repo governance `PROJECT_CONTEXT.md`, `ARCHITECTURE_DECISIONS.md`.
