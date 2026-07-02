# IMPLEMENTATION PLAN — 013

Status: **Draft for architect review** · Companions: the SPEC-013 contracts + `TEST_MATRIX_013.md`.

Phase 013 is broken into seven slices, each a coherent capability, gated (YES/PARTIAL/NO) before
commit, committed locally, **never pushed**. Fixture/mock-backed, deterministic, **offline**,
**manual/on-demand first** (no scheduler). Demo stays default and byte-identical; the accepted
010/011/012 boundaries are unbroken; every slice re-runs the global guardrails (TEST_MATRIX_013 §I).

Sequencing: 013A → 013B → 013C → 013D → 013E → 013F → 013G. Runtime objects (A) precede stores (B);
replay (C) needs stores; ledger/health (D) needs runtime+stores; the gate runner (E) centralizes the
checks; UI/persistence links (F) need stores + health + gate; operator docs + E2E (G) last.

---

## 013A — Runtime objects and PulseRun model
- **Purpose:** implement PulseRun, AgentRunContext, AgentRunResult, AgentHealthRecord, ReplayRequest,
  ReplayResult (RUNTIME_CONTRACT_013) — frozen, label-only, deterministic.
- **Files likely:** new `src/reality_mesh/runtime.py` (or `src/pulse_runtime/`); tests.
- **Tests:** §A1–A5 + globals. **Gate:** models frozen/validated; **manual trigger only** (scheduled/
  streaming rejected); no scheduler/streaming; no order/score field; tests green.
- **Risks:** a scheduled trigger sneaking in; a score field. **Fallback:** reserved triggers rejected
  at construction.

## 013B — Store contracts and local append-only stores
- **Purpose:** RunStore, EventStore, FindingStore, SignalStore, ThemePulseStore, DataQualityStore,
  AuditStore (+ the rest as needed) as append-only local stores.
- **Files likely:** new `src/reality_mesh/stores/` (JSONL-first; SQLite only if a query need justifies
  it — document the tradeoff per PERSISTENCE_REPLAY_CONTRACT_013 §2); tests + fixtures.
- **Tests:** §B1–B5 + globals. **Gate:** append/read/query; schema_version on every record; **append-
  only (correction-not-mutation)**; no secrets/score field; deterministic fixture tests.
- **Risks:** a store computing a score; mutating history. **Fallback:** stores persist only; a fix is
  a new record.

## 013C — ReplayHarness
- **Purpose:** replay pulse runs; reconstruct events/findings/signals/theme-pulses; compare outputs.
- **Files likely:** new `src/reality_mesh/replay.py`; tests.
- **Tests:** §C1–C5 + globals. **Gate:** replay by run_id/ticker/theme/window; conflicts/gaps/source-
  refs/forbidden-uses preserved; **deterministic_match** proven on a clean replay.
- **Risks:** non-determinism (wall-clock/order). **Fallback:** injected `now`; sorted iteration; a
  divergent replay is a FAIL, surfaced in `differences`.

## 013D — AgentRunLedger and health monitoring
- **Purpose:** record agent run status; isolate failures; produce health summaries
  (AgentHealthRecord, SourceHealthRecord, RunHealthSummary, DataQualityRunSummary).
- **Files likely:** new `src/reality_mesh/ledger.py` + `health.py`; tests.
- **Tests:** §D1–D5, §E1–E4 + globals. **Gate:** **one failed agent does not crash the run**; a
  degraded/partial run still produces Data Quality; health records visible; blocked_by_policy
  recorded.
- **Risks:** one failure aborting the pulse. **Fallback:** failure → health record + gap; run
  continues.

## 013E — DataQualityGateRunner
- **Purpose:** centralize the production gates (source-authority/freshness/conflict/gap/social-weak/
  manual-authority/security/guardrail/demo-fallback/schema/replayability) → gate records.
- **Files likely:** new `src/reality_mesh/gates.py` (reuse the 010–012 AST/socket/HTML guards); tests.
- **Tests:** §F1–F8 + globals. **Gate:** the required HARD failures all caught (X/social verified_
  fact, manual canonical, hidden score, buy/sell/order, key-in-output, demo fallback in real/pulse,
  missing-data-without-source, scheduler/broker); warn-vs-fail distinction; gate records persisted.
- **Risks:** a gate that only warns where it must fail. **Fallback:** the §2 list is hard-fail by
  contract.

## 013F — Pulse persistence and UI links
- **Purpose:** connect pulse outputs to Data Quality / Universe / cockpit **metadata** (run/source/
  agent health, replay metadata) — evidence, not trade actions.
- **Files likely:** additive wiring in `src/universe_ui/{view_models,render,app}.py` + a
  `src/reality_mesh/render_adapters.py`; tests. Demo untouched/byte-identical.
- **Tests:** §H1–H4, §G1–G4 + globals. **Gate:** run/source/agent health + replay metadata visible;
  **no trade action**; every `data-intel` resolves (no dead anchors); no key in HTML; demo byte-
  identical.
- **Risks:** UI overstating certainty / a ranking / demo drift. **Fallback:** absent → visible gap;
  ThemePulse is a state label, never a recommendation.

## 013G — Operator docs and production-hardening E2E
- **Purpose:** document the manual pulse **production** workflow; complete offline end-to-end tests.
- **Files likely:** `docs/OPERATOR_GUIDE_013.md`; `tests/test_reality_mesh_production_e2e.py`.
- **Tests:** full suite green; §I globals. **Gate:** offline; **manual/on-demand only**; no scheduler/
  broker/scoring/secrets; docs state the deferred/forbidden items explicitly (scheduler = Phase 015 +
  ADR; execution = Phase 018+ + approval).
- **Risks:** docs implying automation/live/trade-readiness. **Fallback:** docs state manual/on-demand
  + deferred items plainly.

---

## Rules
- One coherent capability per commit; commit locally on a clean gate; **never push**.
- Demo default byte-identical after every slice; real/pulse modes explicit; **no silent demo
  fallback**. Stores are append-only (corrections, not mutations). Manual/on-demand only — **no
  scheduler** in Phase 013; a scheduler is not reconsidered before Phase 015 + a new ADR.
- No new alpha logic, no trading behaviour, no always-on behaviour. Persistence/runtime/observability
  only — the system's conclusions are unchanged; 013 makes them durable, replayable, and auditable.
- Every slice ends with a YES/PARTIAL/NO verdict + evidence per `TEST_MATRIX_013` + prior globals.
- Whether the production runtime/persistence plane warrants promotion into frozen `specification/` or
  a new ADR is an open decision — likely an **ADR candidate** once 013A/013B stabilize (not created
  by the spec-only task).

## Cross references
`SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` · `RUNTIME_CONTRACT_013.md` ·
`PERSISTENCE_REPLAY_CONTRACT_013.md` · `OBSERVABILITY_CONTRACT_013.md` ·
`DATA_QUALITY_GATE_CONTRACT_013.md` · `SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md` ·
`SECURITY_POLICY_CONTRACT_013.md` · `TEST_MATRIX_013.md`.
