# SPEC-013 — Agent Runtime, Persistence, Replay, Observability, and Production Readiness

Status: **Draft for architect review** · Phase: 013 · Depends on: 010 (complete), 011 (complete),
012 (SPEC accepted; 012A accepted; 012B–012K planned/in progress). Type: design-guidance
specification (architecture/, not generated `specification/`).

> Governs Phase 013. Changes NO runtime behaviour. Companion documents:
> `RUNTIME_CONTRACT_013.md`, `PERSISTENCE_REPLAY_CONTRACT_013.md`, `OBSERVABILITY_CONTRACT_013.md`,
> `DATA_QUALITY_GATE_CONTRACT_013.md`, `SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md`,
> `SECURITY_POLICY_CONTRACT_013.md`, `TEST_MATRIX_013.md`, `IMPLEMENTATION_PLAN_013.md`.

## A. Purpose

Phase 012 creates the agentic intelligence substrate:

```
RealityEvent → AgentFinding → HandoffEnvelope → RealitySignal → SignalCluster
  → ThemePulse → OpportunityHypothesisPacket → DiligenceInputBundle
```

Phase 013 exists to make that substrate **production-ready** — durable, replayable, auditable,
observable, failure-isolated, source-aware, data-quality-gated, secure, and **manual/on-demand
first**. It does **not** add new alpha logic, new trading behaviour, or always-on behaviour. It adds
the runtime, persistence, replay, observability, and governance infrastructure required *before*
live scheduling or broader production deployment is even reconsidered.

**The core production principle:**

```
Agents do not talk peer-to-peer.
Agents publish typed outputs.
Synthesizers consume typed outputs.
Buddhi controls routing.
Data Quality observes everything.
Every conclusion is traceable to evidence.
```

## B. Scope

**In scope:** RunStore · EventStore · FindingStore · SignalStore · ThemePulseStore ·
HandoffEnvelopeStore · AgentRunLedger · ReplayHarness · AgentHealthMonitor · DataQualityGateRunner ·
SchemaVersioning · PulseRun persistence · source payload storage · audit trail · observability
records · failure isolation · the **manual/on-demand production run model**.

**Out of scope:** scheduler · background daemon · streaming · live X firehose · broker automation ·
automated trading · auto-rebalancing · autonomous execution · new alpha ranking · stock-first
screening. (All remain deferred/forbidden; several require a future ADR to even reconsider.)

## C. Production architecture — six planes

Every plane inherits the accepted 011/012 invariants unchanged (layer boundaries, source authority,
labels-not-scores, execution boundary, offline/secure runtime). Phase 013 adds durability +
observability *around* them, never new decision authority.

### 1. Source / ingestion plane
**Responsibilities:** source adapters · credential isolation · rate-limit handling · raw payload
capture · source authority assignment · source failure capture · `RealityEvent` production.
Sources (later, onboarded one at a time): SEC · FMP · company IR · investor presentations · earnings
transcripts · news · press releases · market data · sector ETFs · theme baskets · options data ·
X/social · manual research · user-uploaded reports.
**Rules:** adapters are isolated; credentials environment-only; raw payloads are stored; failures
become visible gaps; source authority assigned immediately; **no source bypasses provenance**.
Detailed in `SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md`.

### 2. Agent runtime plane
**Responsibilities:** AgentRegistry · SensorAgent interface · BuddhiRouter · AgentRunContext ·
AgentRunResult · AgentRunLedger · AgentHealthRecord · failure isolation · timeout tracking.
**Rules:** each agent has a descriptor declaring consumes/emits/allowed-sources/forbidden-outputs; a
single failed agent cannot crash the pulse run; **no agent emits broker/order/buy/sell/hidden-score**.
Detailed in `RUNTIME_CONTRACT_013.md`.

### 3. Synthesis plane
**Responsibilities:** Tattva Signal Fusion · Sphurana Opportunity · Nivesha Diligence · Saarathi
Portfolio · Kriya Manual Preview · Anubhava Learning.
**Rules (from CONTRACT-012 §D):** weak signals stay weak; conflicts preserved; freshness/half-life
applied; X/social never verified_fact; manual never canonical; no hidden scoring; no trade actions.

### 4. Persistence / memory plane
**Responsibilities:** raw payload · RealityEvent · AgentFinding · HandoffEnvelope · RealitySignal ·
SignalCluster · ThemePulse · OpportunityHypothesis · DiligenceInputBundle · Data-Quality diagnostics
· run history · (later) outcome records.
**Requirements:** append-only event log keyed by `run_id`/`source_id`/`agent_id`/`timestamp`/schema
version; replay by run / ticker / theme / time-window. Detailed in
`PERSISTENCE_REPLAY_CONTRACT_013.md`.

### 5. Data Quality / governance plane
**Responsibilities:** source coverage · source failures · stale data · conflicts · weak signals ·
unsupported claims · manual assumptions · social-only claims · missing evidence · agent failures ·
schema violations · forbidden-output attempts.
**Hard-fails** if: X/social becomes verified_fact · manual becomes canonical · agent emits buy/sell/
order · a hidden score appears · source gaps silently filled · real/pulse mode falls back to demo ·
an API key appears in output · a network call happens on import. Detailed in
`DATA_QUALITY_GATE_CONTRACT_013.md` + `SECURITY_POLICY_CONTRACT_013.md`.

### 6. Product / UI plane
**Responsibilities:** Economic Universe signal rendering · Data-Quality signal coverage · dashboard
pulse summaries · company cockpit signal notes · theme pulse / market regime / sector rotation
status · weak-social warnings · conflict visibility · freshness/half-life visibility.
**Rules:** the UI must not overstate certainty; ThemePulse is not a trade recommendation; Kriya
remains manual preview only.

## D. Production roadmap beyond 013

- **Phase 014 — Real source adapter expansion** (each local-file-first → mocked → rate-limit/failure
  tested → Data-Quality integrated → only then a production network path): company IR / investor
  presentations → earnings transcripts → market-cap/EV reliable source → sector-ETF & theme-basket
  data → news/filings/press-releases → options-flow (if available) → **X/social, strict weak-signal
  only, last**.
- **Phase 015 — Scheduled pulse / alerting** (ONLY after 013 + 014; requires a new ADR). Allowed:
  scheduled pulse, alert generation, alert-review UI for regime change / rotation / theme-pulse
  change / filing risk / narrative spike / crowding warning / data-quality failure. **Forbidden
  unless separately approved:** auto-buy, auto-sell, broker execution, portfolio auto-rebalancing.
- **Phase 016 — Anubhava production learning:** signal accuracy · theme-pulse accuracy · Nivesha
  thesis accuracy · red-team quality · timing quality · social-source reliability · expert-account
  reliability · false positives · missed opportunities.
- **Phase 017 — Saarathi portfolio productionization:** real exposure · theme concentration · sizing
  guardrails · rotation · risk budget · correlation · liquidity constraints.
- **Phase 018+ — Execution expansion IF approved (future only):** broker-connected **read-only**
  portfolio · manual order-ticket generation · execution simulation · slippage modelling · trade
  audit. **No automation without separate explicit approval + ADR.**

## E. Open decisions (must be resolved before/within the relevant slice)

1. Storage backend: local JSONL vs SQLite vs embedded DB (per-store tradeoffs in
   `PERSISTENCE_REPLAY_CONTRACT_013.md`).
2. Schema-versioning format (semantic string vs integer; per-record vs per-store).
3. Run retention policy; raw-payload retention policy.
4. Whether pulse outputs are committed or generated-only (leaning generated-only, like `generated/`).
5. Where replay artifacts live.
6. How much UI integration belongs in 013 vs 014.
7. Whether any source adapter should be upgraded before persistence exists (leaning no — persistence
   first).
8. When a scheduler can even be reconsidered (not before 015 + a new ADR).
9. Whether the production runtime/persistence plane warrants promotion into the frozen
   `specification/` or a new ADR (likely an **ADR candidate** once 013A/013B stabilize; not created
   by this spec-only task).

## F. Risks

- **Scope creep into always-on** — "runtime" tempting a scheduler/daemon → manual/on-demand-first
  invariant + no-scheduler gate; scheduled/streaming triggers are reserved and rejected until 015.
- **Persistence becoming a decision engine** — a store computing a score/rank → labels-not-scores
  gate; stores persist, they never conclude.
- **Replay non-determinism** — wall-clock/randomness leaking into ids/outputs → injected `now`,
  deterministic-match tests, no-wall-clock AST guard.
- **Secret/network leakage via new adapters** — offline-by-default suite, single lazy network
  boundary, no-key-in-output/commits, credentials env-only.
- **Silent demo fallback** — a real/pulse run quietly using demo data → demo-fallback hard-fail gate.
- **Rumor laundering through persistence** — a stored social claim resurfacing as fact → X/social
  never verified_fact preserved through stores + replay.
- **Over-build** — 13 stores + runtime + replay + observability is large; sequence 013A→013G, each
  small, fixture-backed, gated.

## G. This task

SPEC-013 is **specification only**. It adds no runtime code, no scheduler, no broker, no scoring, no
secrets, and changes no existing 010/011/012 runtime behaviour. It records the production-readiness
architecture, runtime/persistence/replay/observability/gate/adapter/security contracts, test matrix,
and implementation plan for architect review before any 013 build begins.

## H. Cross references
`RUNTIME_CONTRACT_013.md` · `PERSISTENCE_REPLAY_CONTRACT_013.md` · `OBSERVABILITY_CONTRACT_013.md` ·
`DATA_QUALITY_GATE_CONTRACT_013.md` · `SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md` ·
`SECURITY_POLICY_CONTRACT_013.md` · `TEST_MATRIX_013.md` · `IMPLEMENTATION_PLAN_013.md` · (012)
`SPEC-012_REAL_TIME_REALITY_INTELLIGENCE_SENSOR_MESH.md`, `ARCHITECTURE_CONTRACT_012.md`,
`HANDOFF_CONTRACT_012.md`, `AGENT_MAP_012.md` · (011) `ARCHITECTURE_CONTRACT_011.md` · governance
`PROJECT_CONTEXT.md`, `ARCHITECTURE_DECISIONS.md`.
