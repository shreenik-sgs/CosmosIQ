# Shadow Validation Report -- Shadow 24x7 Mode (Phase 020G run)

Filled from the PERSISTED stores / health snapshot / service log of an actual controlled `SHADOW_24X7` validation window driven by `cosmosiq_ops.shadow_validation.run_shadow_window`. Every field below is read back from the run -- never from memory or assumption. This report structure follows the `docs/SHADOW_VALIDATION_020D.md` template.

> HONESTY: controlled validation window: 72 scheduled ticks over an injected-time span of 71.0 hours (NOT a wall-clock 24-72h calendar run)

---

## 0. Run identity

| Field | Value |
|-------|-------|
| Operator | cosmosiq-automated-shadow-020i |
| Store dir | `reports/shadow_020i/store/store` |
| Service mode | `SHADOW_24X7` (explicitly enabled; **not** the default) |
| Subscriptions | shadow-validation-universe |
| Watchlist | IREN, AAOI |
| Themes | physical_ai |
| Tick interval (injected min) | 60 |
| Report prepared at (injected) | 2026-06-29T13:00:00Z |

> `SHADOW_24X7` is enabled EXPLICITLY. The service default is `OFF`. Continuous `PRODUCTION_24X7` remains REFUSED (Phase-020F gate, not flipped by this pass).

## 1. Shadow window

| Field | Value |
|-------|-------|
| Duration (HONEST) | controlled validation window: 72 scheduled ticks over an injected-time span of 71.0 hours (NOT a wall-clock 24-72h calendar run) |
| First tick (injected) | 2026-06-29T13:00:00Z |
| Last tick (injected) | 2026-07-02T12:00:00Z |
| Injected-time span | 71.0 hours |
| Wall-clock duration claimed | none -- this is NOT a 24-72h calendar run |

## 2. Pulse accounting (from the run history + service log)

| Metric | Count |
|--------|-------|
| Ticks scheduled | 72 |
| Ticks succeeded | 72 |
| Ticks failed | 0 |
| Ticks idle (nothing due) | 0 |
| Ticks skipped for backoff | 0 |
| Distinct pulses persisted | 72 |
| Runs replayed `deterministic_match = True` | 72 |
| Replay divergences (must be 0) | 0 |

Ran-policy distribution: cadence.company_documents=3, cadence.learning_daily=3, cadence.learning_weekly=1, cadence.macro_regime=64, cadence.social_narrative=1

## 3. Source-health summary

| Source | Configured | Status label | Health | Events | Notes |
|--------|------------|--------------|--------|--------|-------|
| SEC EDGAR live (`evidence.sec_edgar_live`) | no | skipped | credentials_missing | 0 | credentials-not-configured (`SEC_USER_AGENT` absent) -> honest source GAP, no fetch |
| Bundled offline fixtures | n/a | static | n/a | n/a | pulse disciplines run over local fixtures; no live source |

> A source failure appears as a VISIBLE source gap (never a silent fixture fall-back). `live_source_health` verified = no -- it stays UNVERIFIED/manual (no live SEC fetch).

SEC gap detail:
- SEC_USER_AGENT missing (presence flag false): SEC EDGAR live fetch skipped this pulse -- filings have NO coverage; visible gap (credentials_missing), nothing fabricated, no silent fixture/demo fallback

Freshness note: SEC EDGAR live: no fetch (credentials_missing) -> no freshness signal. Pulse disciplines run over the bundled offline fixtures (static reality); freshness is not a live measurement in this window.

## 4. Agent-health summary (per the run ledger)

| Results | Succeeded | Degraded (partial) | Failed |
|---------|-----------|--------------------|--------|
| 360 | 360 | 0 | 0 |

> An agent failure would appear as a VISIBLE `failed` ledger row (`health_status = failed`). Failed agent runs this window: 0.

## 5. Data-quality gate outcomes (DQ gates EVERY shadow pulse)

| `gate_overall` status | Runs |
|-----------------------|------|
| degraded | 72 |

DQ gate ran on every persisted pulse: yes.
Failing DQ records: 0.

> Every shadow pulse is gated. A shadow alert CARRIES the run's `dq_state` and can never bypass it: a rumor / social-only or DQ-failed input can never become a high-severity production-action alert -- it is capped.

## 6. Shadow alerts generated (inbox only -- no escalation, no external delivery)

| Alert id | Category | Severity | Recommended review action | dq_state | Candidate ref | Marked Shadow? |
|----------|----------|----------|---------------------------|----------|---------------|----------------|
| (none) | - | - | - | - | - | - |

Total shadow alerts: 0. Categories: none. Severities: none.

> Zero shadow alerts is the HONEST answer here: the bundled offline fixtures are a static reality, so successive runs observe no state change -- the diff-based engine stays quiet (it never floods a baseline). This is not a defect; it is the correct shadow behaviour for an unchanging input.

Checks:
- Every shadow alert carries `mode = SHADOW_24X7` and the shadow marker: yes.
- Regex sweep found no action language (buy/sell/order/submit/auto-trade/...): 0 hit(s).
- External delivery occurred: no. Production escalation occurred: no.
- Delivery channel for every shadow alert: in-app inbox only (no external channel invoked).

## 7. False positives reviewed

| Alert id | Reviewed by | Verdict | Rationale |
|----------|-------------|---------|-----------|
| (none) | -- | -- | -- |

> False positives reviewed: 0. This is an AUTOMATED validation pass -- it reviews no alert. Human false-positive review is an outstanding manual item for the operator before any promotion.

## 8. Candidate publication results (020A publish path, per persisted run)

| Candidate id | Ticker | Producing run | State | Eligible? | Blocked reason (missing lineage) |
|--------------|--------|---------------|-------|-----------|------------------------------|
| `cc:sched.cadence.social_narrative.20260629T130000Z:IREN` | IREN | `sched.cadence.social_narrative.20260629T130000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.social_narrative.20260629T130000Z:AAOI` | AAOI | `sched.cadence.social_narrative.20260629T130000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.company_documents.20260629T140000Z:IREN` | IREN | `sched.cadence.company_documents.20260629T140000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.company_documents.20260629T140000Z:AAOI` | AAOI | `sched.cadence.company_documents.20260629T140000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_daily.20260629T150000Z:IREN` | IREN | `sched.cadence.learning_daily.20260629T150000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_daily.20260629T150000Z:AAOI` | AAOI | `sched.cadence.learning_daily.20260629T150000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_weekly.20260629T160000Z:IREN` | IREN | `sched.cadence.learning_weekly.20260629T160000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_weekly.20260629T160000Z:AAOI` | AAOI | `sched.cadence.learning_weekly.20260629T160000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T170000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T170000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T170000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T170000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T180000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T180000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T180000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T180000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T190000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T190000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T190000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T190000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T200000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T200000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T200000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T200000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T210000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T210000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T210000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T210000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T220000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T220000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T220000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T220000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T230000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T230000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T230000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T230000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T000000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T000000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T000000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T000000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T010000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T010000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T010000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T010000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T020000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T020000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T020000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T020000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T030000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T030000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T030000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T030000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T040000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T040000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T040000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T040000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T050000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T050000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T050000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T050000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T060000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T060000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T060000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T060000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T070000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T070000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T070000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T070000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T080000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T080000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T080000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T080000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T090000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T090000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T090000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T090000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T100000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T100000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T100000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T100000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T110000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T110000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T110000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T110000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T120000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T120000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T120000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T120000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T130000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T130000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T130000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T130000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.company_documents.20260630T140000Z:IREN` | IREN | `sched.cadence.company_documents.20260630T140000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.company_documents.20260630T140000Z:AAOI` | AAOI | `sched.cadence.company_documents.20260630T140000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_daily.20260630T150000Z:IREN` | IREN | `sched.cadence.learning_daily.20260630T150000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_daily.20260630T150000Z:AAOI` | AAOI | `sched.cadence.learning_daily.20260630T150000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T160000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T160000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T160000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T160000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T170000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T170000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T170000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T170000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T180000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T180000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T180000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T180000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T190000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T190000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T190000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T190000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T200000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T200000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T200000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T200000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T210000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T210000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T210000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T210000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T220000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T220000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T220000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T220000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T230000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T230000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T230000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T230000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T000000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T000000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T000000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T000000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T010000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T010000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T010000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T010000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T020000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T020000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T020000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T020000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T030000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T030000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T030000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T030000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T040000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T040000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T040000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T040000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T050000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T050000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T050000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T050000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T060000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T060000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T060000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T060000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T070000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T070000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T070000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T070000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T080000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T080000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T080000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T080000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T090000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T090000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T090000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T090000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T100000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T100000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T100000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T100000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T110000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T110000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T110000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T110000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T120000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T120000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T120000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T120000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T130000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T130000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T130000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T130000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.company_documents.20260701T140000Z:IREN` | IREN | `sched.cadence.company_documents.20260701T140000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.company_documents.20260701T140000Z:AAOI` | AAOI | `sched.cadence.company_documents.20260701T140000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_daily.20260701T150000Z:IREN` | IREN | `sched.cadence.learning_daily.20260701T150000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_daily.20260701T150000Z:AAOI` | AAOI | `sched.cadence.learning_daily.20260701T150000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T160000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T160000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T160000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T160000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T170000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T170000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T170000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T170000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T180000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T180000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T180000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T180000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T190000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T190000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T190000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T190000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T200000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T200000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T200000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T200000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T210000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T210000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T210000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T210000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T220000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T220000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T220000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T220000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T230000Z:IREN` | IREN | `sched.cadence.macro_regime.20260701T230000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260701T230000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260701T230000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T000000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T000000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T000000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T000000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T010000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T010000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T010000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T010000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T020000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T020000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T020000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T020000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T030000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T030000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T030000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T030000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T040000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T040000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T040000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T040000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T050000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T050000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T050000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T050000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T060000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T060000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T060000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T060000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T070000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T070000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T070000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T070000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T080000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T080000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T080000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T080000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T090000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T090000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T090000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T090000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T100000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T100000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T100000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T100000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T110000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T110000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T110000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T110000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T120000Z:IREN` | IREN | `sched.cadence.macro_regime.20260702T120000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260702T120000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260702T120000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |

Publication attempts: 144. Forged-eligible (must be 0): 0. Blocked-candidate verdicts: ineligible_missing_provenance.

> No candidate is ever forged eligible: an automated pass supplies no diligence, so every candidate lands `ineligible_*` WITH its exact missing-lineage reason -- nothing hidden, nothing fabricated.

## 9. Replay checks

| Run | `deterministic_match` | Differences |
|-----|-----------------------|-------------|
| `sched.cadence.social_narrative.20260629T130000Z` | yes | none |
| `sched.cadence.company_documents.20260629T140000Z` | yes | none |
| `sched.cadence.learning_daily.20260629T150000Z` | yes | none |
| `sched.cadence.learning_weekly.20260629T160000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T170000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T180000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T190000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T200000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T210000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T220000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T230000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T000000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T010000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T020000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T030000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T040000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T050000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T060000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T070000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T080000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T090000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T100000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T110000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T120000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T130000Z` | yes | none |
| `sched.cadence.company_documents.20260630T140000Z` | yes | none |
| `sched.cadence.learning_daily.20260630T150000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T160000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T170000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T180000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T190000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T200000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T210000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T220000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T230000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T000000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T010000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T020000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T030000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T040000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T050000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T060000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T070000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T080000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T090000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T100000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T110000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T120000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T130000Z` | yes | none |
| `sched.cadence.company_documents.20260701T140000Z` | yes | none |
| `sched.cadence.learning_daily.20260701T150000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T160000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T170000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T180000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T190000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T200000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T210000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T220000Z` | yes | none |
| `sched.cadence.macro_regime.20260701T230000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T000000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T010000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T020000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T030000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T040000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T050000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T060000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T070000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T080000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T090000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T100000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T110000Z` | yes | none |
| `sched.cadence.macro_regime.20260702T120000Z` | yes | none |

> Every persisted run was replayed through the deterministic `ReplayHarness`. Any divergence is a FAILURE, named and investigated -- never hidden. Divergences this window: 0.

## 10. Operator notes

Service health snapshot: mode=`shadow_24x7`, consecutive_failures=0, last_successful_run_id=`sched.cadence.macro_regime.20260702T120000Z`.

Honesty caveats (stated plainly):
- Controlled injected-time validation window (72 ticks, 71.0h injected span) -- NOT a wall-clock 24-72h calendar run.
- No live SEC fetch: SEC_USER_AGENT is not configured, so the SEC EDGAR live adapter ran only in its honest credentials_missing state -- a visible source gap, never fabricated.
- live_source_health stays UNVERIFIED / manual; a real calendar-duration validation and the operator sign-off are outstanding.
- This pass promotes nothing: production_mode_allowed stays False and the 020F gate is not flipped; promotion recommendation = remain_shadow.

## 11. Promotion recommendation

| Field | Value |
|-------|-------|
| Recommendation | **remain_shadow** |
| Rationale | Production is NOT ready: live source health is unverified (no live SEC fetch -- `SEC_USER_AGENT` unconfigured), a real calendar-duration validation is outstanding (this was a controlled injected-time window), and the operator sign-off is required and not given. Remain in shadow mode. |
| Outstanding manual items | live_source_health (live SEC/source fetch), real-duration operator shadow-validation, human false-positive review, operator sign-off |
| production_mode_allowed | false (the 020F gate was NOT flipped by this pass) |
| operator_signoff | required -- not created by this automated pass |
| Signed off by | -- (no sign-off artifact created) |

---

**Standing invariants for this window (all held):**

- Shadow mode enabled EXPLICITLY; service default stays `OFF`.
- Continuous `PRODUCTION_24X7` stays REFUSED; the 020F gate was not flipped.
- Shadow alerts land in the in-app inbox ONLY -- no external delivery, no production escalation.
- No shadow alert carried buy/sell/order/submit/auto-trade/auto-rebalance/broker-submit language (construction-rejected + regex-swept).
- No fixture/demo fall-back: a source failure is a visible source gap (SEC = credentials_missing).
- DQ gates EVERY shadow pulse; a shadow alert carries the run's `dq_state`.
- Deterministic + offline: the pure core read an INJECTED `now`; no secret reached a log or the health file; no network was touched.

