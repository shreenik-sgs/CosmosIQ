# Operator Signoff — TEMPLATE (Phase 020J)

**THIS IS A TEMPLATE. It grants nothing.** No production is enabled by this file's existence.

To record a real decision, the operator copies this to **`reports/OPERATOR_SIGNOFF_020J.md`**, fills
every field, and writes the explicit approval text. Claude/automation must **never** create the actual
signoff file or fill an approval on the operator's behalf — approval is the human operator's act alone.

Even a completed `PRODUCTION_24X7_APPROVED` signoff does **not** by itself enable production: the 020F
activation gate is layered. Production remains refused until **all** blocking items clear —
`live_source_health` (a real live-source fetch) and `operator_shadow_validation` (a real
calendar-duration operator shadow run) both still require the operator's live/wall-clock run, in
addition to this sign-off. The sign-off is necessary, not sufficient.

---

## Signoff record

| Field | Value (operator fills) |
|-------|------------------------|
| Operator name | |
| Timestamp (RFC3339) | |
| Approved mode | `CONTINUE_SHADOW_24X7` **or** `PRODUCTION_24X7_APPROVED` |
| Shadow validation report reference | `reports/SHADOW_VALIDATION_020I.md` (or the operator's real wall-clock run report) |
| prod-check report reference | output of `python3 -m cosmosiq_ops prod-check --work-dir <dir>` |

## Acknowledgements (operator checks each before approving production)

- [ ] **Known limitations accepted** — CosmosIQ is one live adapter deep (SEC EDGAR, and only when a
      real `SEC_USER_AGENT` is configured); FMP + broader sensor coverage are not yet live; the shadow
      validation to date was an injected-time window, not a real calendar-duration run.
- [ ] **Rollback plan accepted** — `PRODUCTION_24X7 → SHADOW_24X7 → MANUAL → OFF`; triggers: source /
      agent / DQ-hard-fail / false-positive spikes, delivery failure, candidate-eligibility bug,
      fixture leakage, secret leakage, unexpected trading/broker control, operator decision.
- [ ] **Production alert delivery accepted** — external delivery turns on only under `PRODUCTION_24X7`
      with an explicit delivery policy; alerts remain review-only, never buy/sell/order language.
- [ ] **Manual-review-only execution boundary accepted** — no automated trading, no broker automation,
      no buy/sell/order/submit control; execution stays a read-only Manual Execution Preview; every
      candidate/alert passes the Trust/Data-Quality gate.

## Explicit approval text (operator writes in the real file, verbatim intent)

> I, <operator name>, have reviewed the shadow validation and prod-check evidence above and the
> acknowledgements, and I approve CosmosIQ to operate in **<CONTINUE_SHADOW_24X7 | PRODUCTION_24X7_APPROVED>**.

Signature / explicit approval: ____________________

---

## Activation flow (what happens after a real signoff)

```
OFF/MANUAL → SHADOW_24X7 → shadow validation (real, wall-clock) → activation checklist (prod-check)
  → explicit operator approval (reports/OPERATOR_SIGNOFF_020J.md, PRODUCTION_24X7_APPROVED)
  → re-run prod-check
  → PRODUCTION_24X7 enabled ONLY IF prod-check production_mode_allowed = true
```

Production activation itself (reading a real signoff, re-running prod-check, and flipping mode) is
**Phase 021C — and only if the operator approves**. Until then the accepted mode is
`CONTINUE_SHADOW_24X7`.
