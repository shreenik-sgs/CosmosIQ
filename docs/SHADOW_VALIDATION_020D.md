# Shadow Validation Report — Shadow 24×7 Mode (Phase 020D)

The operator's **shadow-validation report template** for a `SHADOW_24X7` run of the CosmosIQ
supervised operator service (`cosmosiq_service`). Shadow mode runs the system **continuously**
through the full 013 chain and generates alerts — but every shadow alert is **non-production**:
it lands in the **in-app inbox only**, is clearly marked **Shadow Mode**, and **escalates to
nothing**. There is **no external delivery** (that is Phase-020E) and **no production
notification**. Execution stays **Manual Review Only**; no broker, no trading endpoint.

Copy this file per shadow window, fill every field from the **persisted** stores / health
snapshot / logs (never from memory), and record a promotion recommendation at the end.

Governance: `docs/OPERATOR_RUNBOOK_020C.md` (the service) · `docs/OPERATOR_GUIDE_015.md`
(scheduled ticks + alerts) · `docs/OPERATOR_GUIDE_016.md` (the app).

---

## 0. Run identity

| Field | Value |
|-------|-------|
| Operator | |
| Store dir (`--store-dir`) | |
| Service mode | `SHADOW_24X7` (explicitly enabled; **not** the default) |
| Subscriptions file | |
| Poll interval (s) | |
| Report prepared at | |

> Reminder: `SHADOW_24X7` is enabled **explicitly** by the operator. The service default is
> `OFF`. Continuous `PRODUCTION_24X7` remains **refused** (Phase-020F gate).

## 1. Shadow window

| Field | Value |
|-------|-------|
| Shadow start time (first tick) | |
| Shadow end time (last tick) | |
| Total elapsed | |

## 2. Pulse accounting (from the run history + service log)

| Metric | Count |
|--------|-------|
| Ticks attempted | |
| Pulses run (persisted runs) | |
| Successful pulses | |
| Failed pulses | |
| Idle ticks (nothing due) | |
| Runs replayed `deterministic_match = True` | |
| Replay divergences (must be 0) | |

## 3. Source-health summary (per `source_health_summary`)

| Source | Status label | Coverage records | Failed source records | Notes |
|--------|--------------|------------------|-----------------------|-------|
| | | | | |

> A source failure appears as a **visible source gap** (a `source_failure` DQ record + a failed
> pulse) — **never** a silent fixture fall-back.

## 4. Agent-health summary (per `agent_health_summary` + the run ledger)

| Agent | Results | Succeeded | Degraded | Failed | Notes |
|-------|---------|-----------|----------|--------|-------|
| | | | | | |

> An agent failure appears as a **visible agent-health issue** (a `failed` ledger row with
> `health_status = failed`).

## 5. Data-quality gate outcomes (DQ gates EVERY shadow pulse)

| Run | `gate_overall` | Failing categories | dq_state carried by shadow alerts | Notes |
|-----|----------------|--------------------|-----------------------------------|-------|
| | | | | |

> Every shadow pulse is gated. A shadow alert **carries the run's `dq_state`** and can **never
> bypass it**: a rumor / social-only or DQ-failed input can **never** become a high-severity
> (critical) production-action alert — it is capped.

## 6. Shadow alerts generated (inbox only — no escalation, no external delivery)

| Alert id | Category | Severity (capped?) | Recommended review action | dq_state | Candidate ref | Marked Shadow? |
|----------|----------|--------------------|---------------------------|----------|---------------|----------------|
| | | | | | | |

Checks:

- [ ] Every shadow alert carries `mode = SHADOW_24X7` and the shadow marker
      (`[SHADOW MODE — non-production observation; no escalation, review only]`).
- [ ] Every shadow alert carries a **recommended review action** from the closed vocabulary
      (`Review Required` / `Review Candidate` / `Review Thesis` / `Review Data Gap` /
      `Review Red-Team Risk` / `Review Portfolio Fit` / `Open Manual Execution Preview`).
- [ ] A **regex sweep** over all generated shadow alerts found **no** action language
      (`buy now` / `sell now` / `strong buy` / `submit order` / `place order` / `auto trade` /
      `auto rebalance` / `broker submit` / `guaranteed upside`).
- [ ] **No** external delivery occurred; **no** production escalation flag was set.
- [ ] The app mode indicator showed `Mode: SHADOW_24X7 …` and **never** "Production 24×7".

## 7. False positives reviewed

| Alert id | Reviewed by | Verdict (true / false positive) | Rationale |
|----------|-------------|---------------------------------|-----------|
| | | | |

## 8. Candidate changes observed

| Ticker | Change (new / eligible → blocked / etc.) | Producing run | Notes |
|--------|-------------------------------------------|---------------|-------|
| | | | |

## 9. Replay checks

| Run | `deterministic_match` | Differences | Notes |
|-----|-----------------------|-------------|-------|
| | | | |

> Any divergence is a **failure**, named and investigated — never hidden.

## 10. Operator notes

_Free-form: anomalies, source outages, backoff events, pause/resume actions, anything the
tables above do not capture._

## 11. Promotion recommendation

| Field | Value |
|-------|-------|
| Recommendation | ☐ Promote toward production (Phase-020F review)  ☐ Extend shadow window  ☐ Do not promote |
| Rationale | |
| Outstanding risks / blockers | |
| Signed off by | |
| Date | |

---

**Standing invariants for this window (must all hold):**

- Shadow mode is **enabled explicitly**; the service default stays `OFF`.
- Continuous `PRODUCTION_24X7` stays **refused**.
- Shadow alerts land in the **in-app inbox only** — no external delivery, no production
  escalation.
- Shadow alerts **never** contain buy/sell/order/submit/auto-trade/auto-rebalance/broker-submit/
  "strong buy"/"guaranteed upside" language (construction-rejected + regex-swept).
- Execution stays **Manual Review Only**; no broker, no trading endpoint.
- **No** fixture / demo fall-back in shadow: a source failure is a visible source gap; an agent
  failure is a visible agent-health issue.
- DQ gates **every** shadow pulse; a shadow alert carries the run's `dq_state` and cannot bypass
  it.
- Deterministic and offline: the pure core reads an **injected** `now`; only the operator-started
  loop reads the wall clock. No secret ever reaches a log or the health file.
