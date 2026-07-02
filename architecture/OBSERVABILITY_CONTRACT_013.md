# OBSERVABILITY & HEALTH CONTRACT — 013

Status: **Draft for architect review** · Companion to `SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md`,
`RUNTIME_CONTRACT_013.md`. Defines what a pulse run measures and reports, and how failures are
isolated. **No runtime code exists yet.** All observability records are labels + counts (volumes),
never investability scores; no secrets in any record.

## 1. Metrics / records (per pulse run)
Counts and durations only — volumes, not quality scores:
```
run duration                 events created            failed source count
source adapter duration      findings created          failed agent count
agent duration               signals created           stale signal count
synthesizer duration         data gaps count           weak social signal count
                             conflict count            policy block count
                                                        forbidden output attempt count
```
These roll up into `RunHealthSummary` + `DataQualityRunSummary`. A high "data gaps count" or "weak
social signal count" is **information, not a defect** — honesty about coverage, surfaced not hidden.

## 2. Health states (for agents, sources, and the run)
```
healthy · degraded · failed · blocked_by_policy · stale · credentials_missing · rate_limited · source_unavailable
```
- `blocked_by_policy` — a policy/security gate refused an output (not a crash; recorded).
- `credentials_missing` / `rate_limited` / `source_unavailable` — a source couldn't deliver; becomes
  a **visible gap**, never a fabricated value or a silent demo fallback.
- `stale` — data older than its half-life; kept + flagged, never dropped.

## 3. Observability outputs
| record | purpose |
|---|---|
| `AgentHealthRecord` | rolling per-agent health (from RUNTIME_CONTRACT_013 §4) |
| `SourceHealthRecord` | per-source: last status, credentials_status, rate_limit_status, last_success/failure, unavailable_reason |
| `RunHealthSummary` | per-run roll-up: agents run/failed/blocked, sources used/failed, gap/conflict counts, overall health state |
| `DataQualityRunSummary` | per-run data-quality roll-up (coverage, gaps, conflicts, weak-social, unsupported claims) — feeds the Data-Quality surface |
| `SecurityGateResult` | result of the security gate (no-secret/no-network-on-import/etc.) |
| `PolicyGateResult` | result of the policy gate (no-scheduler/no-broker/no-hidden-score/etc.) |

## 4. Failure isolation rules (enforced by TEST_MATRIX_013 §D/§E)
```
one failed source does NOT crash the run          → SourceHealthRecord + a data gap
one failed agent does NOT crash the run           → AgentHealthRecord + AgentRunResult(status=failed) + a data gap
a policy-blocked agent                            → AgentRunResult(status=blocked_by_policy), run continues
a partial run                                     → can STILL render Data Quality (degraded, honestly labelled)
```
The pulse run is resilient by construction: it collects health + gaps and always produces a
`RunHealthSummary` + `DataQualityRunSummary`, even when degraded. It never silently substitutes demo
data to "complete" a failed real/pulse run.

## Cross references
`SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` · `RUNTIME_CONTRACT_013.md` ·
`DATA_QUALITY_GATE_CONTRACT_013.md` · `PERSISTENCE_REPLAY_CONTRACT_013.md` ·
`SECURITY_POLICY_CONTRACT_013.md`.
