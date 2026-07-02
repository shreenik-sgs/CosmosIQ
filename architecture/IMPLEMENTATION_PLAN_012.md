# IMPLEMENTATION PLAN — 012

Status: **Draft for architect review** · Companions: `SPEC-012_…SENSOR_MESH.md`,
`ARCHITECTURE_CONTRACT_012.md`, `AGENT_MAP_012.md`, `HANDOFF_CONTRACT_012.md`, `TEST_MATRIX_012.md`.

Phase 012 is broken into eleven slices, each a coherent capability, gated (YES/PARTIAL/NO) before
commit, committed locally, never pushed. Fixture/mock-backed, deterministic, **offline**, **manual/
on-demand** (no scheduler). Demo stays default and byte-identical; the accepted 010/011 boundaries
(layer / authority / execution / security) are unbroken. Every slice re-runs the global guardrails
(TEST_MATRIX_012 §I).

Sequencing: 012A → 012B → 012C → {012D, 012E, 012G, 012H} → 012F → 012I → 012J → 012K. Sensor agents
(D/E/G/H) can proceed in parallel once B+C exist; Sphurana (F) needs fusion (C); Nivesha (I) needs
the Sphurana packet (F) + 011 enrichment; integration (J) needs signals/pulses; CLI/E2E (K) is last.

---

## 012A — Core contracts
- **Purpose**: the typed handoff objects — RealityEvent, AgentFinding, HandoffEnvelope, RealitySignal,
  SignalCluster (+ the rest as they're needed) — frozen, label-only, provenance/conflict/gap-
  preserving, deterministic.
- **Files likely**: new `src/reality_mesh/contracts.py` (or chosen home); tests.
- **Tests**: TEST_MATRIX_012 A1–A5 + globals.
- **Gate**: contract §A/§E/§I; no numeric score field; byte-identical; offline.
- **Risks**: smuggling a numeric score; wall-clock in id path. **Fallback**: unknown → explicit gap.

## 012B — Agent registry + SensorAgent interface
- **Purpose**: the registry (from `AGENT_MAP_012.md`) + a `SensorAgent` interface (consume
  RealityEvent → emit AgentFinding within discipline) + the Buddhi router producing HandoffEnvelopes.
- **Files likely**: `src/reality_mesh/registry.py`, `sensor_agent.py`, `router.py`; tests.
- **Tests**: B1–B5 + globals.
- **Gate**: contract §A/§B; an agent emitting outside its contract is caught. **Risks**: an agent
  emitting a cross-layer packet. **Fallback**: router refuses to wrap an out-of-contract payload.

## 012C — Tattva Signal Fusion synthesizer
- **Purpose**: fuse findings+events → RealitySignal/SignalCluster; preserve conflicts + weak signals;
  apply authority/freshness/half-life; mark corroboration/contradiction.
- **Files likely**: `src/reality_mesh/tattva_fusion.py`; tests.
- **Tests**: C1–C5 + globals.
- **Gate**: contract §D; no thesis/buy-sell; contradictions preserved. **Risks**: averaging conflicts;
  upgrading weak signals. **Fallback**: uncorroborated stays weak; conflicts surfaced.

## 012D — Market Regime Agent (fixture-backed)
- **Purpose**: first sensor agent end-to-end (subagents: rates/curve/dollar/credit/…); MarketRegime
  (or MacroRegime) findings from local fixtures.
- **Files likely**: `src/reality_mesh/agents/market_regime.py`; `tests/fixtures/`; tests.
- **Tests**: D1, D5 + globals. **Gate**: labels only; in-discipline; missing → gap. **Risks**:
  cross-discipline conclusions. **Fallback**: absent inputs → gap finding.

## 012E — Sector + Theme Rotation Agents (fixture-backed)
- **Purpose**: sector-rotation + theme-rotation findings (theme baskets, relative strength, breadth,
  momentum, crowding) from fixtures.
- **Files likely**: `src/reality_mesh/agents/{sector_rotation,theme_rotation}.py`; tests.
- **Tests**: D2, D5 + globals. **Gate**: theme movement as labels; no ranking. **Risks**: implying a
  buy. **Fallback**: exhaustion/crowding surfaced as labels.

## 012F — Sphurana Theme Pulse synthesizer
- **Purpose**: SignalClusters → ThemePulse (state machine) + OpportunityHypothesisPacket; preserve
  contradictions; no final decision.
- **Files likely**: `src/reality_mesh/sphurana_pulse.py`; tests.
- **Tests**: E1–E3 + globals. **Gate**: valid state; contradictions preserved; packet has diligence
  questions. **Risks**: a pulse becoming a stock pick. **Fallback**: Conflicted/Data-insufficient.

## 012G — News / Filings / Press-Release Agent
- **Purpose**: 8-K/S-3/insider/guidance/partnership findings from SEC/FMP fixtures; dilution risk;
  company_claim marking.
- **Files likely**: `src/reality_mesh/agents/news_filings.py` (reuse 009B/C parsers); tests.
- **Tests**: D3, D5 + globals. **Gate**: authority preserved; company_claim ≠ fact. **Risks**:
  treating a claim as verified. **Fallback**: unverifiable → company_claim + gap.

## 012H — X / Social Narrative Agent (weak-signal only)
- **Purpose**: NarrativeFinding from fixtures; authority=rumor; weak-signal-only; corroboration
  required; bot/promoter + crowding flags. **No live X fetch** (fixtures/mocks; real transport
  deferred).
- **Files likely**: `src/reality_mesh/agents/narrative.py`; tests.
- **Tests**: D4, C5 + globals. **Gate**: rumor never verified; needs corroboration downstream.
  **Risks**: rumor laundering. **Fallback**: everything stays weak/uncorroborated.

## 012I — Nivesha Forward-Scenario engine (spec/adapter)
- **Purpose**: forward-scenario inputs (base/upside/downside/delay/dilution) feeding the **accepted**
  Nivesha gauntlet via the 011D-style handoff adapter; insufficient inputs → honest limited thesis.
- **Files likely**: `src/reality_mesh/nivesha_forward.py` (+ reuse 011D adapter); tests. **Prometheus/
  Nivesha reasoning unmodified.**
- **Tests**: F1–F3 + globals. **Gate**: no new score; Nivesha semantics unchanged; not padded.
  **Risks**: fabricating scenario inputs. **Fallback**: missing → gap; thin thesis.

## 012J — Data Quality + Economic Universe signal integration
- **Purpose**: surface signals/pulses in the accepted terrain + Data Quality as evidence (labels +
  gaps + provenance + conflicts); a distinct honestly-labelled **pulse** mode; no ranking.
- **Files likely**: additive wiring in `src/universe_ui/{view_models,render,app,terrain_adapters}.py`;
  tests. Demo untouched/byte-identical.
- **Tests**: G1–G4 + globals. **Gate**: closed link graph; no ranking; no silent demo. **Risks**: a
  UI ranking; demo drift. **Fallback**: absent → visible gap; enrichment/pulse optional.

## 012K — CLI / operator docs + end-to-end tests
- **Purpose**: the manual pulse CLI (`tattva_pulse` or `universe_ui --mode pulse`); operator docs; the
  full offline E2E pulse-chain matrix.
- **Files likely**: `src/…/__main__` addition; `docs/OPERATOR_GUIDE_012.md`; `tests/`.
- **Tests**: H1–H3 + globals. **Gate**: manual/on-demand; no scheduler; full chain honest; docs
  build. **Risks**: docs implying automation/live/trade-readiness; a scheduler sneaking in.
  **Fallback**: docs state manual/on-demand + deferred/forbidden items explicitly.

---

## Rules
- One coherent capability per commit; commit locally on a clean gate; **never push**.
- Demo default byte-identical after every slice; real/enriched/pulse modes explicit; no silent demo
  fallback. Prometheus/Nivesha reasoning untouched (adapters only). Manual/on-demand only — **no
  scheduler** in Phase 012 unless separately approved via a new ADR.
- Every slice ends with a YES/PARTIAL/NO verdict + evidence per `TEST_MATRIX_012` + `GATE-011` globals.
- Any change to `ARCHITECTURE_CONTRACT_012` invariants requires a new ADR, not a build patch.
