# DATA QUALITY GATE CONTRACT — 013

Status: **Draft for architect review** · Companion to `SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md`,
`SECURITY_POLICY_CONTRACT_013.md`. Defines the production gate runner. **No runtime code exists yet.**

The `DataQualityGateRunner` centralizes the production gates. It runs the gate categories over a
PulseRun's records and emits gate records (persisted to `DataQualityStore` + `AuditStore`). A **hard
failure** blocks the run's outputs from being treated as trustworthy (the run still renders Data
Quality honestly, marked failed); a **warning** annotates but does not block.

## 1. Gate categories
```
source authority gate            manual/analyst authority gate       demo fallback gate
freshness gate                   security/secrets gate               schema validation gate
conflict gate                    scheduler/broker/trading guardrail   replayability gate
data gap gate                    gate
social/X weak-signal gate
```

Each gate defines: **inputs · checks · pass · warn · fail · output record.**

| Gate | Checks (summary) | Warn | Fail (hard) |
|---|---|---|---|
| Source authority | every value carries an authority; lower never overrides higher for same metric/period/unit | thin coverage | a lower source overrode a higher one |
| Freshness | freshness/half-life present; stale flagged | some stale inputs | stale data presented as fresh |
| Conflict | contradictions preserved (both sides) | many unresolved conflicts | a contradiction was averaged away/dropped |
| Data gap | missing → explicit gap | high gap count | a gap was silently filled (fabricated value) |
| Social/X weak-signal | narrative = rumor, weak, uncorroborated | lots of uncorroborated social | **X/social became verified_fact** |
| Manual/analyst authority | manual/analyst labelled, not canonical | many manual assumptions | **manual/analyst treated as canonical** |
| Security/secrets | no key in output/logs; no network on import | — | **API key in output / network on import** |
| Scheduler/broker/trading guardrail | no scheduler/daemon/broker/order added | — | **scheduler/broker/order/buy-sell affordance present** |
| Demo fallback | real/pulse mode used real/pulse data | — | **real/pulse mode silently used demo data** |
| Schema validation | records match declared schema_version | minor drift | schema violation |
| Replayability | deterministic_match reproducible | — | replay diverged (non-determinism leaked) |

## 2. Required HARD failures (never a warning)
```
API key in generated output
network on import
scheduler / background process added without approval
broker / order / submit affordance
buy / sell / hold outside accepted Nivesha semantics
hidden score / rank field
X/social verified_fact
manual/analyst canonical
real/pulse mode silently uses demo data
missing data filled without source
```

## 3. Gate output records
- `DataQualityGateResult` — per-gate: category, status (pass/warn/fail), findings, subject refs.
- `PolicyGateResult` + `SecurityGateResult` — the policy/security subsets (also in
  `OBSERVABILITY_CONTRACT_013`), persisted per run.
- A run's overall `data_quality_status` (healthy/degraded/failed/blocked_by_policy) is the worst of
  its gate results.

## 4. Relationship to existing behaviour
This gate runner **formalizes and centralizes** the ad-hoc checks already enforced across 010–012
(source authority, no-secret, offline, no-scheduler/broker, labels-not-scores, no silent demo,
rumor≠verified, manual≠canonical). It adds no new alpha logic and relaxes none of the existing
invariants — it makes them a first-class, persisted, per-run production gate.

## Cross references
`SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` · `SECURITY_POLICY_CONTRACT_013.md` ·
`OBSERVABILITY_CONTRACT_013.md` · `SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md` · (012)
`ARCHITECTURE_CONTRACT_012.md` §C/§E/§G/§H.
