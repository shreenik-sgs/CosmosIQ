# Shadow Validation Report -- Shadow 24x7 Mode (Phase 020G run)

Filled from the PERSISTED stores / health snapshot / service log of an actual controlled `SHADOW_24X7` validation window driven by `cosmosiq_ops.shadow_validation.run_shadow_window`. Every field below is read back from the run -- never from memory or assumption. This report structure follows the `docs/SHADOW_VALIDATION_020D.md` template.

> HONESTY: controlled validation window: 24 scheduled ticks over an injected-time span of 23.0 hours (NOT a wall-clock 24-72h calendar run)

---

## 0. Run identity

| Field | Value |
|-------|-------|
| Operator | SGS Operator |
| Store dir | `/private/tmp/claude-501/-Users-srinivaskodavatiganti-Desktop-SGS-Investing-SGS-Genesis/8514a1c6-76fc-4837-a54c-d2347383e5e4/scratchpad/shadow_work/store` |
| Service mode | `SHADOW_24X7` (explicitly enabled; **not** the default) |
| Subscriptions | shadow-validation-universe |
| Watchlist | IREN, AAOI |
| Themes | physical_ai |
| Tick interval (injected min) | 60 |
| Report prepared at (injected) | 2026-06-29T14:30:00Z |

> `SHADOW_24X7` is enabled EXPLICITLY. The service default is `OFF`. Continuous `PRODUCTION_24X7` remains REFUSED (Phase-020F gate, not flipped by this pass).

## 1. Shadow window

| Field | Value |
|-------|-------|
| Duration (HONEST) | controlled validation window: 24 scheduled ticks over an injected-time span of 23.0 hours (NOT a wall-clock 24-72h calendar run) |
| First tick (injected) | 2026-06-29T14:30:00Z |
| Last tick (injected) | 2026-06-30T13:30:00Z |
| Injected-time span | 23.0 hours |
| Wall-clock duration claimed | none -- this is NOT a 24-72h calendar run |

## 2. Pulse accounting (from the run history + service log)

| Metric | Count |
|--------|-------|
| Ticks scheduled | 24 |
| Ticks succeeded | 24 |
| Ticks failed | 0 |
| Ticks idle (nothing due) | 0 |
| Ticks skipped for backoff | 0 |
| Distinct pulses persisted | 24 |
| Runs replayed `deterministic_match = True` | 24 |
| Replay divergences (must be 0) | 0 |

Ran-policy distribution: cadence.company_documents=1, cadence.learning_daily=1, cadence.learning_weekly=1, cadence.macro_regime=20, cadence.social_narrative=1

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
| 120 | 120 | 0 | 0 |

> An agent failure would appear as a VISIBLE `failed` ledger row (`health_status = failed`). Failed agent runs this window: 0.

## 5. Data-quality gate outcomes (DQ gates EVERY shadow pulse)

| `gate_overall` status | Runs |
|-----------------------|------|
| degraded | 24 |

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
| `cc:sched.cadence.social_narrative.20260629T143000Z:IREN` | IREN | `sched.cadence.social_narrative.20260629T143000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.social_narrative.20260629T143000Z:AAOI` | AAOI | `sched.cadence.social_narrative.20260629T143000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.company_documents.20260629T153000Z:IREN` | IREN | `sched.cadence.company_documents.20260629T153000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.company_documents.20260629T153000Z:AAOI` | AAOI | `sched.cadence.company_documents.20260629T153000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_daily.20260629T163000Z:IREN` | IREN | `sched.cadence.learning_daily.20260629T163000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_daily.20260629T163000Z:AAOI` | AAOI | `sched.cadence.learning_daily.20260629T163000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_weekly.20260629T173000Z:IREN` | IREN | `sched.cadence.learning_weekly.20260629T173000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.learning_weekly.20260629T173000Z:AAOI` | AAOI | `sched.cadence.learning_weekly.20260629T173000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T183000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T183000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T183000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T183000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T193000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T193000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T193000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T193000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T203000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T203000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T203000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T203000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T213000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T213000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T213000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T213000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T223000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T223000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T223000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T223000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T233000Z:IREN` | IREN | `sched.cadence.macro_regime.20260629T233000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260629T233000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260629T233000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T003000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T003000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T003000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T003000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T013000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T013000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T013000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T013000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T023000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T023000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T023000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T023000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T033000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T033000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T033000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T033000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T043000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T043000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T043000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T043000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T053000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T053000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T053000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T053000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T063000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T063000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T063000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T063000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T073000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T073000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T073000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T073000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T083000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T083000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T083000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T083000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T093000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T093000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T093000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T093000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T103000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T103000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T103000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T103000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T113000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T113000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T113000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T113000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T123000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T123000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T123000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T123000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T133000Z:IREN` | IREN | `sched.cadence.macro_regime.20260630T133000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |
| `cc:sched.cadence.macro_regime.20260630T133000Z:AAOI` | AAOI | `sched.cadence.macro_regime.20260630T133000Z` | ineligible_missing_provenance | no | opportunity_hypothesis_ref, investment_diligence_ref, trust_data_quality_state==healthy |

Publication attempts: 48. Forged-eligible (must be 0): 0. Blocked-candidate verdicts: ineligible_missing_provenance.

> No candidate is ever forged eligible: an automated pass supplies no diligence, so every candidate lands `ineligible_*` WITH its exact missing-lineage reason -- nothing hidden, nothing fabricated.

## 9. Replay checks

| Run | `deterministic_match` | Differences |
|-----|-----------------------|-------------|
| `sched.cadence.social_narrative.20260629T143000Z` | yes | none |
| `sched.cadence.company_documents.20260629T153000Z` | yes | none |
| `sched.cadence.learning_daily.20260629T163000Z` | yes | none |
| `sched.cadence.learning_weekly.20260629T173000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T183000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T193000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T203000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T213000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T223000Z` | yes | none |
| `sched.cadence.macro_regime.20260629T233000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T003000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T013000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T023000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T033000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T043000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T053000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T063000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T073000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T083000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T093000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T103000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T113000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T123000Z` | yes | none |
| `sched.cadence.macro_regime.20260630T133000Z` | yes | none |

> Every persisted run was replayed through the deterministic `ReplayHarness`. Any divergence is a FAILURE, named and investigated -- never hidden. Divergences this window: 0.

## 10. Operator notes

Service health snapshot: mode=`shadow_24x7`, consecutive_failures=0, last_successful_run_id=`sched.cadence.macro_regime.20260630T133000Z`.

Honesty caveats (stated plainly):
- Controlled injected-time validation window (24 ticks, 23.0h injected span) -- NOT a wall-clock 24-72h calendar run.
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

