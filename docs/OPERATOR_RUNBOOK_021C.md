# Operator Runbook — IMPLEMENTATION-021C: Production 24×7 Activation FLOW

This runbook governs the **operator flow** that flips CosmosIQ into `PRODUCTION_24X7`. It sits on
top of the accepted 020F activation **CORE** (`cosmosiq_service.activation`) and adds only the two
missing operator-facing pieces: a strict **sign-off file reader** and an
**`activate` / `rollback`** command line.

Production is **never** enabled automatically, and never by wishful representation. It is enabled
only when **every** blocking precondition is satisfied **and** a real, filled operator sign-off is
recorded. In the current repo state an activation attempt correctly **REFUSES** and lands at
**shadow 24×7 only** — that is the correct, safe default, not a failure.

Permanent invariants (true in every mode, including an activated production):

- **Broker: Disabled.** No trading endpoint exists anywhere.
- **Execution: Manual Review Only.** Execution is always a read-only manual preview. There is no
  buy / sell / order / submit / auto-trade / auto-rebalance / broker-submit / guaranteed-upside
  control anywhere in the product — including under production.
- **No hidden score / rank; no fixture / demo leakage; no secrets.**

---

## 1. The mode ladder

```
OFF  →  MANUAL  →  SHADOW_24X7  →  PRODUCTION_24X7
(safe)                                   (capable)
```

Promotion climbs the ladder; rollback descends it. `PRODUCTION_24X7` is reachable **only** from
`SHADOW_24X7`, and only through this flow.

## 2. The promotion flow

1. `OFF` / `MANUAL` → `SHADOW_24X7` — allowed freely (no gate).
2. Run **shadow 24×7** and accumulate a validation window (020D / 020I).
3. Complete the **operator shadow-validation** run over a real, wall-clock calendar duration and
   review it. This is a manual, **blocking** item (`operator_shadow_validation`) — it can **never**
   be cleared from code.
4. Confirm **live source health** with a **real** live fetch. This is a manual, **blocking** item
   (`live_source_health`) — also never cleared from code.
5. Run the **activation checklist** (the offline machine sweep):
   ```
   python3 -m cosmosiq_ops prod-check --work-dir /tmp/prodcheck --now <ISO-8601>
   ```
   It exits **non-zero** whenever production is not allowed (the safe default).
6. Record an **explicit operator sign-off**. The operator copies
   `reports/OPERATOR_SIGNOFF_020J_TEMPLATE.md` to **`reports/OPERATOR_SIGNOFF_020J.md`**, fills the
   operator name, an RFC3339 timestamp, sets the approved mode to `PRODUCTION_24X7_APPROVED`, and
   **checks all four acknowledgements**. Automation must **never** create or fill this file — the
   approval is the human operator's act alone.
7. Run the **activation flow**:
   ```
   python3 -m cosmosiq_ops activate --work-dir <store-work-dir> --now <ISO-8601> \
       [--signoff reports/OPERATOR_SIGNOFF_020J.md]
   ```

### The exact condition to flip to PRODUCTION_24X7

`activate` switches to `PRODUCTION_24X7` **iff BOTH** hold:

1. `read_operator_signoff(path)` returns a **valid** approval — the file exists, `approved_mode` is
   `PRODUCTION_24X7_APPROVED`, a non-placeholder operator name and an RFC3339 timestamp are present,
   and **all four** acknowledgements are `[x]`; **AND**
2. `evaluate_activation(...)` with that approval returns `production_mode_allowed = True` — i.e.
   **zero** blocking failures **and zero** blocking manual-review items.

Today, condition (2) is `False`: `live_source_health` and `operator_shadow_validation` are still
`manual_review_required` and **blocking**. So the current-state attempt **REFUSES**, printing the
exact blocking / manual reasons and changing nothing. The sign-off is **necessary but not
sufficient**: a valid sign-off satisfies the operator-approval gate and clears the `operator_signoff`
checklist item, but it can never clear the two live/wall-clock items — those are the operator's live
evidence.

On success, and only on success, the flow records the sanctioned `PRODUCTION_24X7` mode marker
(`<store>/service_mode.json` + the service-health snapshot) and prints the production banner:

```
Mode: PRODUCTION_24X7 · Live Data: <status> · Scheduler: On · Broker: Disabled ·
Execution: Manual Review Only · Alert Delivery: On
```

The banner **never** contains a buy / sell / order / submit / auto-trade / broker-submit /
guaranteed-upside token.

## 3. The production-mode surface

- **Shown only when production was genuinely activated** (a `PRODUCTION_24X7` marker / health
  snapshot exists). The default, service-never-started posture shows no indicator.
- **Forbidden controls (permanent):** no buy / sell / order / submit / auto-trade / auto-rebalance /
  broker-submit / guaranteed-upside affordance anywhere, in any mode.
- **Allowed alert language:** review-only observations, evidence references, DQ state, severity
  labels.
- **Forbidden alert language:** any action / order phrase or a guaranteed-return claim.

## 4. The rollback flow

Stepping **down** to a safer mode is always allowed; an **upgrade** is refused (use `activate`).

```
python3 -m cosmosiq_ops rollback --work-dir <store-work-dir> \
    --to <SHADOW_24X7|MANUAL|OFF> [--trigger NAME] --now <ISO-8601>
```

Intended descent: `PRODUCTION_24X7 → SHADOW_24X7 → MANUAL → OFF`. The trigger (default
`operator_manual`) must be one of the named `ROLLBACK_TRIGGERS`:

| Trigger | Rolls down to |
|---------|---------------|
| `source_failure_spike` | `SHADOW_24X7` |
| `agent_failure_spike` | `SHADOW_24X7` |
| `dq_hard_fail_spike` | `SHADOW_24X7` |
| `false_positive_spike` | `SHADOW_24X7` |
| `delivery_failure` | `SHADOW_24X7` |
| `candidate_eligibility_bug` | `MANUAL` |
| `fixture_leakage` | `OFF` |
| `secret_leakage` | `OFF` |
| `unexpected_trading_control` | `OFF` |
| `operator_manual` | `SHADOW_24X7` |

A hygiene / safety breach (fixture leakage, secret leakage, an unexpected trading control) drops all
the way to `OFF`; an operational spike drops one rung to `SHADOW_24X7` for investigation.

## 5. Current-state verdict

With no `reports/OPERATOR_SIGNOFF_020J.md` present and `live_source_health` +
`operator_shadow_validation` unmet, `activate` **REFUSES** (verdict `shadow_24x7_only`, exit
non-zero, nothing written). This is correct. **Remain shadow.** Production is unflippable until the
operator supplies the real live/shadow evidence **and** records an explicit
`PRODUCTION_24X7_APPROVED` sign-off.
