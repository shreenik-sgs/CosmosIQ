# Operator Runbook — IMPLEMENTATION-020F: Production 24×7 Activation Gate

This runbook governs whether CosmosIQ may be **represented and operated as production 24×7**.
Production is **never** enabled automatically. It is enabled only when every precondition is
satisfied **and** an explicit operator approval is recorded. An honest OFFLINE evaluation
**refuses** full production and lands at **shadow 24×7 only** — that is the correct, safe default,
not a failure.

Permanent invariants (true in every mode, including an activated production):

- **Broker: Disabled.** No trading endpoint exists anywhere.
- **Execution: Manual Review Only.** Execution is always a manual preview (the 017 slice). There
  is no buy / sell / order / submit / auto-trade / auto-rebalance / broker-submit / guaranteed-upside
  control anywhere in the product.
- **No hidden score / rank.** Labels and volume counts only.
- **No fixture / demo leakage, no secrets.** The default product UI shows no real ticker.

---

## 1. The mode ladder

```
OFF  →  MANUAL  →  SHADOW_24X7  →  PRODUCTION_24X7
(safe)                                   (capable)
```

- `OFF` — the default, safe posture. The service does nothing.
- `MANUAL` — operator-attended single ticks.
- `SHADOW_24X7` — continuous shadow operation (activated by 020D). Alerts land in the in-app
  inbox only; **no external delivery, no escalation**.
- `PRODUCTION_24X7` — continuous production operation. **Gated by this slice (020F).**

Promotion climbs the ladder; rollback descends it.

## 2. The promotion flow

1. `OFF` / `MANUAL` → `SHADOW_24X7` — allowed freely (no gate).
2. Run **shadow 24×7** and let it accumulate a validation window.
3. Complete the **operator shadow-validation** run and review it (a manual, blocking item).
4. Confirm **live source health** with a real fetch (a manual, blocking item).
5. Run the **activation checklist**:
   ```
   python3 -m cosmosiq_ops prod-check --work-dir /tmp/prodcheck --now <ISO-8601>
   ```
   This runs the full CI gate + every machine check OFFLINE and prints `production_mode_allowed`,
   `blocking_failures`, `manual_review_items`, and `evidence_paths`. It exits **non-zero** whenever
   production is not allowed (the safe default).
6. Record an **explicit operator approval** (`OperatorApproval`: `approved_by`, `approved_at`,
   `target_mode = production_24x7`).
7. `SHADOW_24X7` → `PRODUCTION_24X7` — allowed **only** when the activation report allows it
   **and** the explicit approval is recorded. Any auto / unapproved jump is refused. A direct
   `OFF`/`MANUAL` → `PRODUCTION` jump is refused (production is reachable only from shadow).

The service's `can_enter_production_continuous` consults the gate and **refuses** continuous
production (with the blocking reasons) unless the gate allows it.

## 3. The rollback flow

Rollback always **downgrades** to a safer mode and is never gated:

```
PRODUCTION_24X7  →  SHADOW_24X7  →  MANUAL  →  OFF
```

Use `rollback(current_mode, target)`. A single call may step down one or more rungs.

### Rollback triggers

| Trigger | Meaning | Downgrade to |
|---|---|---|
| `source_failure_spike` | spike in live-source failures (visible gaps, never a fixture fall-back) | `SHADOW_24X7` |
| `agent_failure_spike` | spike in agent-run failures | `SHADOW_24X7` |
| `dq_hard_fail_spike` | spike in Data-Quality hard failures (`blocked_by_policy`) | `SHADOW_24X7` |
| `false_positive_spike` | spike in false-positive alerts | `SHADOW_24X7` |
| `delivery_failure` | external alert delivery failing | `SHADOW_24X7` |
| `candidate_eligibility_bug` | a candidate reached eligible without full provenance | `MANUAL` |
| `fixture_leakage` | fixture/demo data leaked into a product surface | `OFF` |
| `secret_leakage` | a secret value appeared in output / logs | `OFF` |
| `unexpected_trading_control` | an unexpected trading / broker / order control detected | `OFF` |
| `operator_manual` | an operator manually initiated a rollback | `SHADOW_24X7` |

A hygiene/safety breach (secret, fixture, trading control) drops all the way to `OFF`. An
operational spike drops one rung to `SHADOW_24X7` for investigation.

## 4. The prod-check command

```
python3 -m cosmosiq_ops prod-check --work-dir DIR [--repo-root DIR] [--now INSTANT] [--quick]
```

- OFFLINE + deterministic (`--now` is injected; the SEC adapter smoke uses a mock transport;
  the real live-source-health fetch is a manual item, never performed here).
- `--quick` skips the CI-gate full-suite subprocess run but keeps every sweep.
- Exit code `0` only when `production_mode_allowed = true`; otherwise non-zero.

Because the live-source-health, operator-shadow-validation, and operator-sign-off items cannot be
machine-verified OFFLINE, an honest run always reports `production_mode_allowed = false` and the
verdict `shadow_24x7_only` until those items are satisfied and an explicit approval is recorded.
