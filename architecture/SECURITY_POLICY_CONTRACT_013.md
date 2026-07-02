# SECURITY & POLICY CONTRACT — 013

Status: **Draft for architect review** · Companion to `SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md`,
`DATA_QUALITY_GATE_CONTRACT_013.md`. Consolidates the hard security and policy rules for the
production runtime and their gate outputs. **No runtime code exists yet.** These inherit and do not
weaken the 011/012 security/execution invariants; they make them a first-class, persisted gate.

## 1. Hard security rules (any violation ⇒ hard fail)
```
no secrets committed
no secrets in generated HTML
no secrets in logs
.env is not tracked
credentials are environment-only
no network on import
tests are offline by default
network must be explicitly mocked in tests
```
Presence is reported as a boolean-ish label only (e.g. "FMP API key present: False") — never the
value. Missing credentials → a visible gap, never a leak or a crash.

## 2. Policy rules (any violation ⇒ hard fail unless separately approved via a new ADR)
```
no scheduler unless approved
no background job unless approved
no streaming daemon unless approved
no broker automation unless approved
no automated trading unless approved
no buy / sell / order / submit affordance
no hidden score / rank / investability metric
no social rumor laundering (X/social never verified_fact; manual never canonical)
```
"Unless approved" means a new ADR with explicit human approval — reserved for Phase 015+ (scheduler/
alerting) and Phase 018+ (any execution), never a build-time decision.

## 3. Policy / security gate outputs
- `SecurityGateResult` — per run: secrets-in-output check, network-on-import check, .env-tracked
  check, credentials-env-only check; status pass/fail + offending refs (no secret values).
- `PolicyGateResult` — per run: scheduler/daemon/streaming/broker/trading/affordance/hidden-score/
  rumor-laundering checks; status pass/fail + offending refs.
Both persist to `DataQualityStore` + `AuditStore` and roll into the run's `data_quality_status`.

## 4. Enforcement techniques (carried forward from 010–012, now centralized)
- AST scans: no network/scheduler/broker imports; single lazy network boundary; no `def *score`/
  `*rank`/`*rating`; no forbidden decision fields on dataclasses.
- Offline suite under a `socket.socket.connect` kill-switch; no live endpoint in tests.
- Grep/HTML scans: no `<button>`/`<form>`/`onclick`/`type=submit`/place-order/buy/sell affordance; no
  API key in generated HTML.
- Git-scope checks: only intended files staged; `.env` never tracked; no secret committed.
- Determinism: injected `now`; byte-identical demo; deterministic replay.

## Cross references
`SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` · `DATA_QUALITY_GATE_CONTRACT_013.md` ·
`OBSERVABILITY_CONTRACT_013.md` · `SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md` · (012)
`ARCHITECTURE_CONTRACT_012.md` §F/§G/§H · (011) `ARCHITECTURE_CONTRACT_011.md`.
