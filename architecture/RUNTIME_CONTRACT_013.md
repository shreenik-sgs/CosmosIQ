# RUNTIME CONTRACT — 013 (implementation-ready)

Status: **Draft for architect review** · Companion to `SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md`.
Defines the production runtime objects for the manual/on-demand pulse run model. Frozen dataclasses,
stdlib, deterministic, offline-buildable; label fields draw from closed vocabularies (labels, not
scores). **No runtime code exists yet.** Field name · type · semantics.

Conventions: `*_id` = stable id; `*_at` = ISO timestamp (injectable; no wall-clock in id/replay
paths); `Tuple[...]` = ordered immutable; absent/unknown → explicit gap, never a fabricated default.

---

## 1. PulseRun — one manual pulse (the top-level run record)
| field | type | semantics |
|---|---|---|
| `run_id` | str | stable id for the whole pulse |
| `started_at` / `completed_at` | str | run window (injectable) |
| `mode` | label | demo / fixture / real_evidence_on_demand / enriched / **pulse** (honestly labelled; no silent demo) |
| `trigger_type` | label | **must initially be `manual`** — `scheduled` / `streaming` are RESERVED/DEFERRED (rejected until Phase 015 + a new ADR) |
| `watchlist` | Tuple[str] | requested tickers |
| `themes` | Tuple[str] | requested themes |
| `source_adapters_requested` / `source_adapters_used` | Tuple[str] | requested vs actually used (divergence → gap) |
| `agents_requested` / `agents_run` / `agents_failed` | Tuple[str] | agent coverage + failures (isolated) |
| `events_created` / `findings_created` / `signals_created` / `theme_pulses_created` | int | counts (volume metrics, NOT scores) |
| `data_quality_status` | label | healthy / degraded / failed / blocked_by_policy |
| `generated_outputs` | Tuple[ref] | output artifact refs (files under generated/) |
| `schema_version` / `runtime_version` | str | for replay determinism |

**Rules:** `trigger_type` manual-only in 013; a `scheduled`/`streaming` value is rejected at
construction (reserved). No broker field exists. Counts are volume, not investability.

## 2. AgentRunContext — what one agent is handed for one run
| field | type | semantics |
|---|---|---|
| `run_id` / `agent_id` | str | which pulse / which agent |
| `mode` | label | inherited pulse mode |
| `watchlist` / `themes` | Tuple[str] | scope |
| `input_event_ids` | Tuple[str] | the events this agent may read |
| `allowed_sources` | Tuple[label] | source authorities the agent may consume |
| `forbidden_outputs` | Tuple[label] | always includes broker_order/auto_execute/buy_sell_recommendation/hidden_score |
| `started_at` | str | injectable |
| `timeout_policy` | label/str | soft budget; a timeout is recorded, never crashes the run |
| `fixture_mode` | bool | true → fixtures only |
| `network_allowed` | bool | **must be `False` in tests**; true only behind an explicit real pulse |

**Rules:** `network_allowed` is `False` under the offline test suite. **`broker_allowed` must never
exist, or must always be `False`.** No affordance, order, or score is reachable from a context.

## 3. AgentRunResult — the outcome of one agent run
| field | type | semantics |
|---|---|---|
| `run_id` / `agent_id` | str | which pulse / agent |
| `status` | label | success / partial / failed / skipped / **blocked_by_policy** |
| `started_at` / `completed_at` | str | timing (injectable) |
| `input_event_ids` / `finding_ids` | Tuple[str] | consumed / produced |
| `warnings` / `errors` | Tuple[str] | non-fatal / fatal notes (failure isolated) |
| `data_gaps` / `conflicts` | Tuple[...] | preserved, surfaced |
| `health_status` | label | see OBSERVABILITY_CONTRACT_013 health states |

**Rules:** a `failed`/`blocked_by_policy` result NEVER crashes the pulse; it produces a health record
+ a data gap. `blocked_by_policy` is the status when a policy gate refuses an agent's output.

## 4. AgentHealthRecord — rolling health for one agent
| field | type | semantics |
|---|---|---|
| `agent_id` | str | which agent |
| `last_run_id` / `last_status` | str/label | most recent run + status |
| `failure_count` | int | consecutive/total failures |
| `last_error` | str | last error note (no secrets) |
| `last_success_at` / `last_failure_at` | str | timing |
| `degraded_reason` | str | why degraded (stale source / credentials missing / rate limited / …) |

## 5. ReplayRequest — ask to reconstruct a past run
| field | type | semantics |
|---|---|---|
| `run_id` | str | source run (optional if querying by ticker/theme/window) |
| `ticker` / `theme` | str | replay scope filters |
| `time_window` | (str,str) | from/to |
| `source_filter` / `agent_filter` | Tuple[str] | narrow to sources / agents |
| `include_raw_payloads` | bool | whether to pull raw payload refs |
| `include_generated_outputs` | bool | whether to reconstruct outputs |

## 6. ReplayResult — what a replay produced
| field | type | semantics |
|---|---|---|
| `replay_id` / `source_run_id` | str | this replay / the run it reconstructs |
| `events_replayed` / `findings_replayed` / `signals_replayed` | int | counts |
| `outputs_reconstructed` | Tuple[ref] | rebuilt artifacts |
| `differences` | Tuple[str] | any divergence from the original (should be empty for a clean deterministic replay) |
| `deterministic_match` | bool | true iff same inputs + schemas + code version reproduced identical outputs |

---

## Runtime invariants (enforced by TEST_MATRIX_013)
- `trigger_type` manual-only in 013; scheduled/streaming reserved (rejected). No `broker_allowed`
  true; no order/score reachable from any runtime object.
- Failure isolation: one failed source/agent → a health record + a data gap, never a crashed run; a
  partial run can still render Data Quality.
- Deterministic + offline: injected `now`; no wall-clock in id/replay paths; `network_allowed` false
  in tests; `deterministic_match` provable for a clean replay.
- Labels-not-scores: counts are volumes; no investability/score/rank field on any runtime object.

## Cross references
`SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` · `PERSISTENCE_REPLAY_CONTRACT_013.md` ·
`OBSERVABILITY_CONTRACT_013.md` · `DATA_QUALITY_GATE_CONTRACT_013.md` · (012)
`HANDOFF_CONTRACT_012.md`, `ARCHITECTURE_CONTRACT_012.md`.
