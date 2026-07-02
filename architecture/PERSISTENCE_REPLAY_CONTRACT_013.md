# PERSISTENCE & REPLAY CONTRACT — 013

Status: **Draft for architect review** · Companion to `SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md`,
`RUNTIME_CONTRACT_013.md`. Defines the persistence stores and the replay capability. **No runtime
code exists yet.** Stores persist; they never conclude, score, or decide. All records are
append-only; historical records are never mutated (corrections are new records).

## 1. Required stores

Each store below specifies: **purpose · key fields · write rule · read/query · append-only vs mutable
· retention · schema versioning · replay role.** All stores: append-only; keyed for replay; schema
version on every record; no secrets/raw credentials; no score/rank field.

| Store | Purpose | Key fields | Read/query | Replay role |
|---|---|---|---|---|
| **RunStore** | one record per PulseRun | run_id, started_at, mode, trigger_type, schema_version | by run_id / time-window / mode | the spine — every replay starts from a run |
| **RawSourceStore** | raw source payloads (as fetched) | raw_payload_ref, run_id, source_id, source_authority, fetched_at | by run_id / source_id | reproduce what a source actually returned |
| **EventStore** | RealityEvents | event_id, run_id, source_id, discipline, timestamp | by run/ticker/theme/discipline/window | the inputs agents saw |
| **FindingStore** | AgentFindings | finding_id, run_id, agent_id, discipline, input_events | by run/agent/ticker/theme | what each agent concluded (in-discipline) |
| **HandoffEnvelopeStore** | HandoffEnvelopes | envelope_id, run_id, from_layer, to_layer, payload_ids | by run / from-to | the routing + allowed/forbidden-use record |
| **SignalStore** | RealitySignals | signal_id, run_id, discipline, source_findings | by run/ticker/theme/discipline | fused reality intelligence |
| **SignalClusterStore** | SignalClusters | cluster_id, run_id, theme/sector, signals | by run/theme | grouped signals + conflict labels |
| **ThemePulseStore** | ThemePulses | theme_pulse_id, run_id, theme_id, state | by run/theme/state | theme state over runs (follow-through) |
| **OpportunityHypothesisStore** | OpportunityHypothesisPackets | hypothesis_id, run_id, theme_pulse ref | by run/theme | what Nivesha was asked to test |
| **DiligenceInputStore** | DiligenceInputBundles | ticker, run_id, hypothesis refs, enrichment refs | by run/ticker | evidence handed to Nivesha |
| **DataQualityStore** | Data-Quality diagnostics per run | run_id, category, status, records | by run/category/status | coverage/gaps/conflicts/failures |
| **AgentRunLedger** | AgentRunResult + status per agent per run | run_id, agent_id, status, health_status | by run/agent/status | which agents ran/failed/were blocked |
| **AuditStore** | append-only audit trail (who/what/when/why) | audit_id, run_id, actor, action, subject_ref, at | by run/subject | provenance + correction records |

**Correction records:** a mistake is fixed by appending a `correction` record to `AuditStore` (and,
where needed, a superseding record in the target store) that references the corrected id — the
original is never edited or deleted.

## 2. Persistence requirements (all stores)
- Append-only log; `run_id` + `source_id`/`agent_id` + `timestamp` + `schema_version` on every
  record. Replay by **run / ticker / theme / time-window**.
- Raw payload refs preserved; source refs preserved; conflicts preserved; data gaps preserved;
  forbidden-uses preserved (on envelopes). Nothing averaged, upgraded, or dropped on write.
- Deterministic keys (content-addressed where possible); no wall-clock in id/replay paths.
- Storage backend is an **open decision** (SPEC-013 §E): local JSONL (simple, git-diffable,
  append-natural) vs SQLite (indexed queries, transactions) vs embedded DB. 013B picks per-store and
  documents the tradeoff; JSONL-first is the leaning for the append-only logs.

## 3. Required replay capabilities

The system must be able to answer, from stored records alone:

```
Why did the system say Physical AI was igniting?      → ThemePulseStore + its source SignalClusters/Signals/Findings/Events
Which sources caused that?                            → EventStore → RawSourceStore (source_id, authority)
Which agents agreed? Which disagreed?                 → FindingStore (direction/contradiction) + AgentRunLedger
Was X the only source?                                → source authority across the contributing findings
Was the signal stale?                                 → freshness/half-life on the signal + events
Was the signal contradicted?                          → contradiction_status + preserved conflicts
Did the theme actually follow through later?          → ThemePulseStore across later runs (+ Anubhava, Phase 016)
```

## 4. Replay invariants (enforced by TEST_MATRIX_013 §C)
```
same inputs + same schemas + same code version  ⇒  same outputs   (deterministic_match = True)
raw payload refs preserved
source refs preserved
data gaps preserved
conflicts preserved
forbidden uses preserved
no mutation of historical records except explicit correction records
```
A replay that cannot reproduce identical outputs from identical inputs+schema+code is a **failure**,
not a warning — it means non-determinism leaked in (wall-clock, ordering, hidden state).

## Cross references
`SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` · `RUNTIME_CONTRACT_013.md` ·
`OBSERVABILITY_CONTRACT_013.md` · `DATA_QUALITY_GATE_CONTRACT_013.md` · (012) `HANDOFF_CONTRACT_012.md`.
