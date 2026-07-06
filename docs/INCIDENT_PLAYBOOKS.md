# CosmosIQ — Incident Playbooks (IMPLEMENTATION-023I)

Seven playbooks for the failure modes CosmosIQ is designed to surface **honestly** rather than hide.
Each is: **symptom → the exact diagnostic command → the exact remediation command → the rollback
trigger** (if one applies). All commands are real, existing CLIs.

Set up once (see `docs/OPERATOR_RUNBOOK.md` §1):

```bash
export STORE="generated/pulse_store"
export WORK="/tmp/cosmosiq_work"
```

Two shared diagnostics used throughout:

```bash
# the single rolled health surface (ok / degraded / failed) — source, agent, DQ, storage, delivery
curl -s http://127.0.0.1:8016/api/observability
# the sanitized service health snapshot
PYTHONPATH=src python3 -m cosmosiq_service status --store-dir "$STORE"
```

Rollback triggers referenced below are named exactly as `cosmosiq_ops rollback --trigger <name>`
accepts them; see `docs/ROLLBACK_GUIDE.md` for the full ladder.

---

## 1. SOURCE failure (credentials missing / rate-limited)

**Symptom.** A live source is not delivering: `credentials_missing` (a required env var such as
`SEC_USER_AGENT` / `FMP_API_KEY` is absent) or rate-limited. CosmosIQ shows a **visible source gap**
— it **never** falls back to fixtures and never fabricates data.

**Diagnose.**

```bash
curl -s http://127.0.0.1:8016/api/observability     # source_health_summary + failure_counts.source_failures
PYTHONPATH=src python3 -m cosmosiq_ops env          # env var PRESENCE (names + labels, never values)
```

**Remediate.** Set the missing var in your real `.env` (presence-only; never a value in any doc/log),
or wait out the rate limit, then re-run a tick:

```bash
cp .env.example .env    # if not already; edit .env, then:
PYTHONPATH=src python3 -m cosmosiq_service run-once --store-dir "$STORE" --mode manual
```

**Rollback trigger.** A *spike* in live-source failures → `--trigger source_failure_spike`
(downgrades to `SHADOW_24X7`). A single expected gap is not an incident — CosmosIQ already shows it.

---

## 2. AGENT failure

**Symptom.** One fused-discipline agent fails on a pulse. The batch **continues**; the failure is
recorded as an agent-health issue with a visible gap for that agent's contribution — no fabricated
result fills the hole.

**Diagnose.**

```bash
curl -s http://127.0.0.1:8016/api/observability     # agent_health_summary.agents_currently_failed
PYTHONPATH=src python3 -m cosmosiq_service status --store-dir "$STORE"
```

Inspect the specific run in the app: `/runs/<run_id>` and `/api/runs/<run_id>` show per-agent results.

**Remediate.** Fix the underlying agent input/config, then re-run the tick:

```bash
PYTHONPATH=src python3 -m cosmosiq_service run-once --store-dir "$STORE" --mode manual
```

**Rollback trigger.** A *spike* in agent-run failures → `--trigger agent_failure_spike` (downgrades
to `SHADOW_24X7` for investigation).

---

## 3. DQ (Data-Quality) failure — gate hard-fail

**Symptom.** The Data-Quality gate **hard-fails** (`blocked_by_policy`). The run is
**degraded/blocked**: no candidate is promoted on a blocked gate.

**Diagnose.**

```bash
curl -s http://127.0.0.1:8016/api/observability     # dq_status_summary.gate_overall_worst + fail_records
```

Inspect the run's DQ summary in the app: `/runs/<run_id>` (gate overall + per-category records) and
`/api/runs/<run_id>`.

**Remediate.** Resolve the failing input (coverage, freshness, provenance), then re-run:

```bash
PYTHONPATH=src python3 -m cosmosiq_service run-once --store-dir "$STORE" --mode manual
```

**Rollback trigger.** A *spike* in DQ HARD failures → `--trigger dq_hard_fail_spike` (downgrades to
`SHADOW_24X7`).

---

## 4. FALSE-POSITIVE alerts

**Symptom.** Shadow alerts look like precision collapse (too many low-value alerts). In shadow, alerts
land in the **in-app inbox only** (marked *Shadow Mode*, never escalated); social/rumor-class evidence
can **never** be critical on its own.

**Diagnose.** Shadow-review the inbox:

```bash
curl -s http://127.0.0.1:8016/api/alerts            # or open /alerts in the app
```

Record the finding in the shadow-validation report (re-run the controlled window if needed):

```bash
PYTHONPATH=src python3 -m cosmosiq_ops shadow-validate --work-dir "$WORK" --ticks 24 \
  --start 2026-07-06T13:00:00Z --interval-minutes 60 --report-out reports/SHADOW_VALIDATION_020I.md
```

**Remediate.** Note the precision issue in `reports/SHADOW_VALIDATION_020I.md` and do **not** promote
to production while it stands (prod-check keeps `operator_shadow_validation` as manual review anyway).

**Rollback trigger.** A *spike* in false-positive alerts → `--trigger false_positive_spike`
(downgrades to `SHADOW_24X7`). Note: **`delivery_failure`** is the separate trigger for external
alert delivery failing.

---

## 5. FIXTURE leakage

**Symptom.** A real fixture/demo ticker appears in a **default** (non-demo) product surface. This is a
hygiene breach — CosmosIQ must never present fixture data as real.

**Diagnose.** Run the security audit (its fixture-leakage / demo-vs-default byte-identical scans) and
the production gate's fixture scan:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops security-audit
PYTHONPATH=src python3 -m cosmosiq_ops prod-check --work-dir "$WORK"
```

**Remediate (ROLLBACK first).** Drop straight to `OFF`, then fix and re-audit:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$WORK" --to off --trigger fixture_leakage
PYTHONPATH=src python3 -m cosmosiq_ops security-audit
```

**Rollback trigger.** `--trigger fixture_leakage` → downgrades all the way to **`OFF`** (a hygiene
breach, not a mere operational spike).

---

## 6. SECRET leak

**Symptom.** A secret value appears in output, a log, or a tracked file (it must never — CosmosIQ
sanitizes every string and reads env vars presence-only).

**Diagnose / confirm hygiene.**

```bash
PYTHONPATH=src python3 -m cosmosiq_ops security-audit     # real secret scan + .env-not-tracked check
PYTHONPATH=src python3 -m cosmosiq_ops env                # confirm presence-only handling
```

**Remediate.** Rotate the exposed credential at its source, confirm the real `.env` is untracked
(gitignored), then re-run the audit to confirm the finding is cleared. **Drop to `OFF`** while doing
so:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$WORK" --to off --trigger secret_leakage
PYTHONPATH=src python3 -m cosmosiq_ops security-audit
```

**Rollback trigger.** `--trigger secret_leakage` → downgrades to **`OFF`**.

---

## 7. STORAGE corruption

**Symptom.** The append-only store integrity check reports a mutated prior line, a truncated/garbled
line, or a monotonic-append violation. Integrity detection **names the store + line**.

**Diagnose.** The observability surface runs the 023D integrity check over the active store:

```bash
curl -s http://127.0.0.1:8016/api/observability     # storage_health.ok=false, storage_health.findings>0
PYTHONPATH=src python3 -m cosmosiq_ops backup-health --backup-dir backups
```

**Remediate — restore from a verified backup, then replay-after-restore.** Verify a known-good
snapshot, restore it into an **empty** target (restore re-checks integrity and re-runs the
deterministic replay), and repoint the app/service at the restored store:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops verify --backup-path backups/<good-snapshot>
PYTHONPATH=src python3 -m cosmosiq_ops restore --backup-path backups/<good-snapshot> \
  --target-dir "$WORK/restored"          # reports integrity_ok + replay_ok
PYTHONPATH=src python3 -m cosmosiq_app --store-dir "$WORK/restored"
```

**Rollback trigger.** No dedicated storage trigger; use `--trigger operator_manual` to step the mode
down while you restore. The active store is never edited — only restored from a verified snapshot.

---

## Cross references

- `docs/OPERATOR_RUNBOOK.md` · `docs/DEPLOYMENT_GUIDE.md` · `docs/ROLLBACK_GUIDE.md`
- `reports/REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md`
</content>
