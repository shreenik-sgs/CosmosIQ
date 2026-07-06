# CosmosIQ — Rollback Guide (IMPLEMENTATION-023I)

How to step CosmosIQ **down** the mode ladder safely. Rollback is a one-way, always-safe operation:
it **never upgrades** a mode. Promotion (upgrading toward production) is the separate, gated
`cosmosiq_ops activate` path — see `docs/OPERATOR_RUNBOOK.md` §5.

Companion docs: `docs/OPERATOR_RUNBOOK.md` · `docs/DEPLOYMENT_GUIDE.md` · `docs/INCIDENT_PLAYBOOKS.md`.

---

## 1. The mode ladder

```
PRODUCTION_24X7  →  SHADOW_24X7  →  MANUAL  →  OFF
   (highest)                                   (safest)
```

`cosmosiq_ops rollback` steps the sanctioned mode **down** this ladder. A request to move **up** is
**refused** — use the activation flow for that (which itself refuses production by default).

```bash
export WORK="/tmp/cosmosiq_work"

# step down one rung (or several) — always allowed
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$WORK" --to shadow_24x7 \
  --trigger operator_manual
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$WORK" --to manual \
  --trigger operator_manual
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$WORK" --to off \
  --trigger operator_manual
```

`--to` accepts `shadow_24x7` / `manual` / `off` (production is only ever a *from*, never a rollback
*to*). If `--trigger` is omitted it defaults to `operator_manual`.

---

## 2. The rollback triggers

Each named trigger declares the mode CosmosIQ downgrades to. A **hygiene/safety breach** drops all
the way to `OFF`; an **operational spike** drops one rung to `SHADOW_24X7` for investigation; a
**correctness bug** drops to `MANUAL`.

| Trigger | Meaning | Downgrades to |
|---------|---------|---------------|
| `source_failure_spike` | a spike in live-source failures (visible gaps, not a fixture fall-back) | `SHADOW_24X7` |
| `agent_failure_spike` | a spike in agent-run failures across the fused disciplines | `SHADOW_24X7` |
| `dq_hard_fail_spike` | a spike in Data-Quality HARD failures (`blocked_by_policy`) | `SHADOW_24X7` |
| `false_positive_spike` | a spike in false-positive alerts (precision collapse) | `SHADOW_24X7` |
| `delivery_failure` | external alert delivery is failing (retryable/permanent) | `SHADOW_24X7` |
| `candidate_eligibility_bug` | a candidate reached eligible without full provenance | `MANUAL` |
| `fixture_leakage` | fixture/demo data leaked into a product surface | `OFF` |
| `secret_leakage` | a secret value appeared in output / logs | `OFF` |
| `unexpected_trading_control` | an unexpected trading / broker / order control was detected | `OFF` |
| `operator_manual` | an operator manually initiated a rollback | `SHADOW_24X7` |

Pass the value on `--trigger`, e.g. `--trigger fixture_leakage`. See `docs/INCIDENT_PLAYBOOKS.md` for
which trigger each incident maps to.

---

## 3. When to use each

- **Operational spike** (`source_failure_spike`, `agent_failure_spike`, `dq_hard_fail_spike`,
  `false_positive_spike`, `delivery_failure`) → back to `SHADOW_24X7`, investigate, fix, and only
  then consider re-promotion through the gate.
- **Correctness bug** (`candidate_eligibility_bug`) → `MANUAL`; no automated tick until the
  provenance/eligibility bug is fixed.
- **Hygiene / safety breach** (`fixture_leakage`, `secret_leakage`, `unexpected_trading_control`) →
  straight to `OFF`. These are non-negotiable: stop everything, remediate, re-audit.
- **Operator decision** (`operator_manual`) → `SHADOW_24X7` when you simply want to stand down.

---

## 4. Verify the downgrade

After a rollback, confirm the safer posture. Rolling **below** shadow keeps production refused
anyway, but always re-check:

```bash
# the gate still refuses production (production_mode_allowed=false) — the safe default
PYTHONPATH=src python3 -m cosmosiq_ops prod-check --work-dir "$WORK"

# the service health snapshot reflects the new mode
PYTHONPATH=src python3 -m cosmosiq_service status --store-dir "$STORE"

# the observability surface rolls source/agent/DQ/storage into one status
curl -s http://127.0.0.1:8016/api/observability
```

---

## 5. Rollback never upgrades

`cosmosiq_ops rollback` refuses any request that would move **up** the ladder (e.g. from `OFF` toward
`SHADOW_24X7`, or anything toward `PRODUCTION_24X7`). Moving up is the deliberate, gated act:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops activate --work-dir "$WORK"    # refuses production by default
```

Production is **never** reached by a rollback, and never by one command — it needs the 021C activate
flow, an explicit operator sign-off, and the manual review items (two of which cannot be
machine-verified offline today — see `docs/OPERATOR_RUNBOOK.md` §5 and
`reports/REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md`).

---

## Cross references

- `docs/OPERATOR_RUNBOOK.md` · `docs/DEPLOYMENT_GUIDE.md` · `docs/INCIDENT_PLAYBOOKS.md`
- `src/cosmosiq_service/activation.py` (`MODE_LADDER`, `ROLLBACK_TRIGGERS`) ·
  `reports/OPERATOR_SIGNOFF_020J_TEMPLATE.md`
</content>
