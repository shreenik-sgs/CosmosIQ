# CosmosIQ — Operator Runbook (IMPLEMENTATION-023I)

The single day-to-day operating guide for CosmosIQ. It **consolidates** the earlier per-phase
runbooks (`OPERATOR_RUNBOOK_019.md`, `OPERATOR_RUNBOOK_020C.md`, `OPERATOR_RUNBOOK_020F.md`,
`OPERATOR_RUNBOOK_021C.md`, `DEPLOYMENT_019.md`) into one place. Every command below is a **real,
existing CLI** — nothing invented, no future flags.

Companion docs:

- `docs/DEPLOYMENT_GUIDE.md` — packaging (Docker / Compose / Makefile / launchd), profiles, secrets.
- `docs/INCIDENT_PLAYBOOKS.md` — what to do when a source / agent / DQ / alert / fixture / secret /
  storage problem occurs.
- `docs/ROLLBACK_GUIDE.md` — the mode ladder and how to step down safely.

> **CosmosIQ is a LOCAL, operator-started system.** There is no hosted daemon and no broker. It runs
> only because you start it. Evidence is read-only; every action is an explicit manual preview — no
> order is ever sent. Default mode is `OFF`. `SHADOW_24X7` is available (in-app inbox alerts only,
> never escalated). `PRODUCTION_24X7` is **gated** and is **not** enabled by any single command
> (see §5).

---

## 1. Setup

- **Python 3.9+**, standard library only (no `pip install`, no build step).
- Run everything from the repo root with `PYTHONPATH=src` on the command.
- Pick a durable **store directory** (append-only JSONL stores). Keep it out of Git, e.g.
  `generated/pulse_store`. Referred to below as `$STORE`; a scratch work dir as `$WORK`.

```bash
export STORE="generated/pulse_store"
export WORK="/tmp/cosmosiq_work"
mkdir -p "$STORE" "$WORK"

# confirm the toolkit runs (prints the honest banner + subcommands)
PYTHONPATH=src python3 -m cosmosiq_ops env
```

Copy the environment template to a real `.env` (never committed):

```bash
cp .env.example .env    # then edit .env with your OWN values
```

---

## 2. Environment variables (presence-only — a value is NEVER read, logged, or persisted)

CosmosIQ reads only the **presence** of these names (`name in os.environ`). A required var that is
absent **blocks** the live source it gates with an honest "not configured" gap — it never crashes
and never silently falls back to fixtures. See `.env.example` for the authoritative list.

| Name | Gates | Absent → |
|------|-------|----------|
| `SEC_USER_AGENT` | SEC EDGAR live source (a contact identity, not a secret) | SEC live blocked (visible gap) |
| `FMP_API_KEY` | FMP live source | FMP live blocked (visible gap) |
| `COSMOSIQ_ALERT_EMAIL_SENDER` | external email alert delivery (020E) | email delivery suppressed; in-app inbox still works |
| `COSMOSIQ_ALERT_EMAIL_HOST` | external email alert delivery | as above |
| `COSMOSIQ_ALERT_EMAIL_RECIPIENT` | external email alert delivery | as above |
| `COSMOSIQ_PROFILE` | the 023A environment profile | safe default `test_offline` |
| `COSMOSIQ_STORE_DIR` | container/default store path | unset (pass `--store-dir`) |

Check presence (names + labels only, never values):

```bash
PYTHONPATH=src python3 -m cosmosiq_ops env
```

**Never put a real secret value in any doc, log, or committed file.** The real `.env` is gitignored;
the CI gate fails if it is ever tracked (see `docs/DEPLOYMENT_GUIDE.md` §Secrets).

---

## 3. Run SHADOW_24X7 (the supported continuous mode — inbox-only alerts, never escalated)

Default mode is `OFF`; you must ask for shadow explicitly. Each due tick runs one pulse through the
full 013 chain (stores / ledger / source + agent health / DQ gates / replay) and produces **shadow**
alerts into the in-app inbox marked *Shadow Mode* — never delivered externally, never escalated.

```bash
PYTHONPATH=src python3 -m cosmosiq_service start --mode shadow_24x7 --store-dir "$STORE"
```

Optionally scope the ticks with a local subscriptions file:

```bash
PYTHONPATH=src python3 -m cosmosiq_service start --mode shadow_24x7 --store-dir "$STORE" \
  --subscriptions config/watchlists/shadow_watchlist.yaml
```

Run a single tick (no loop), or a fast deterministic injected-time validation window instead:

```bash
PYTHONPATH=src python3 -m cosmosiq_service run-once --store-dir "$STORE" --mode manual
PYTHONPATH=src python3 -m cosmosiq_ops shadow-validate --work-dir "$WORK" --ticks 24 \
  --start 2026-07-06T13:00:00Z --interval-minutes 60 --report-out reports/SHADOW_VALIDATION_020I.md
```

> **Honest limitation (carried forward from `reports/REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md`).**
> There is **no `--live-sec` CLI flag**. `python3 -m cosmosiq_service start --mode shadow_24x7` runs
> the default (local/fixture) pipeline; it does **not** wire the live SEC adapter. A **real live SEC
> fetch** is done today only with the short Python snippet in that 021D guide (it calls the existing
> public API `run_pulse(adapters=[...])` and reads `SEC_USER_AGENT` from the environment; absent →
> honest `credentials_missing` gap, no fixture fallback). A CLI flag would be a future enhancement,
> deliberately out of scope here.

---

## 4. View the app (localhost-only, read-only + explicit manual actions)

Point the local operator app at the same store and open it in a browser. It binds `127.0.0.1` by
default and refuses a non-local host without `--allow-remote` (CosmosIQ has no authentication).

```bash
PYTHONPATH=src python3 -m cosmosiq_app --store-dir "$STORE"          # serves on 127.0.0.1:8016
PYTHONPATH=src python3 -m cosmosiq_app --store-dir "$STORE" --port 8017
```

Pages (all read-only; a trade-like route returns 403 — there is no buy/sell/order control anywhere):

| What | Route |
|------|-------|
| Home / mode strip | `/` |
| Run history + trigger + gate overall + gaps | `/runs`, `/runs/<run_id>` |
| **Alert inbox** (shadow alerts, marked *Shadow Mode*) | `/alerts` |
| **Replay viewer** (deterministic_match banner) | `/replay/<run_id>` |
| Capital candidates (eligible / blocked+reason / empty) | `/candidates`, `/candidates/<TICKER>` |
| Company cockpit (explicit ticker only) | `/companies/<TICKER>` |
| Themes / portfolio / settings | `/themes`, `/portfolio`, `/settings` |

Read-only JSON surfaces (deterministic; labels + counts + injected-time latencies, never a secret):

| Surface | Route |
|---------|-------|
| Rolled health (basic counts) | `/api/health` |
| **Observability** (single rolled `status`: ok / degraded / failed) | `/api/observability` |
| Runs / run detail / run records | `/api/runs`, `/api/runs/<run_id>`, `/api/runs/<run_id>/<kind>` |
| Alerts / coverage / schedule | `/api/alerts`, `/api/coverage`, `/api/schedule` |

```bash
# view alerts / run history / replay / observability from the shell
curl -s http://127.0.0.1:8016/api/alerts
curl -s http://127.0.0.1:8016/api/runs
curl -s http://127.0.0.1:8016/api/observability
```

---

## 5. Production mode — GATED, never one command

`PRODUCTION_24X7` is **not** enabled by starting the service. `python3 -m cosmosiq_service start
--mode production_24x7` is **REFUSED**: continuous production requires the activation gate.

Reaching production is the explicit **021C activate flow** plus an operator **sign-off** plus manual
review items — and even then two items **cannot be machine-verified offline** today:

1. Run the gate — it refuses production by default:

   ```bash
   PYTHONPATH=src python3 -m cosmosiq_ops prod-check --work-dir "$WORK"
   ```

   Expected (before **and, per 021D, even after** a perfect live shadow run):

   ```
   production_mode_allowed=false recommendation_mode_allowed=false
   verdict: shadow_24x7_only
   manual_review_items: live_source_health, operator_shadow_validation, operator_signoff
   ```

   Exit code is non-zero — the correct, safe default.

2. The activation flow reads a **filled operator sign-off**, re-runs prod-check, and flips to
   `PRODUCTION_24X7` **only if** the evidence is complete. With no sign-off it **refuses** (exit
   non-zero, nothing written):

   ```bash
   PYTHONPATH=src python3 -m cosmosiq_ops activate --work-dir "$WORK"
   ```

> **Honest limitation (carried forward from 021D).** `prod-check` keeps `live_source_health` and
> `operator_shadow_validation` as `manual_review_required` even after a perfect live run — they
> "cannot be machine-verified" and there is **no command that marks them cleared** (no
> operator-attestation input). So a good live run gives you the *evidence*, but prod-check keeps
> `production_mode_allowed=false`. Production also stays **refused offline** (recommendation mode
> too). Production is therefore **never "just run this"** — it needs the 021C activate step, an
> explicit sign-off, the manual items satisfied, and a future attestation enhancement. Until then
> CosmosIQ correctly stays shadow/manual.

---

## 6. Pause / resume the service

A paused service's ticks run **nothing** until resume (an unexpired per-policy failure backoff still
holds after resume). Run these in a second shell while the loop is running, against the same store:

```bash
PYTHONPATH=src python3 -m cosmosiq_service status --store-dir "$STORE"
PYTHONPATH=src python3 -m cosmosiq_service pause  --store-dir "$STORE"
PYTHONPATH=src python3 -m cosmosiq_service resume --store-dir "$STORE"

# release the single-instance lockfile (also recovers a crashed loop's lock)
PYTHONPATH=src python3 -m cosmosiq_service stop --store-dir "$STORE"
```

---

## 7. Backup / restore

Backups are append-only snapshots with a sha256 manifest. The **active store is never edited,
pruned, or touched.** Restore refuses a non-empty target and re-checks integrity + replay.

```bash
# hardened backup: seal + snapshot + verify (writes a sha256 manifest)
PYTHONPATH=src python3 -m cosmosiq_ops backup --store-dir "$STORE" --backup-dir backups

# report the latest snapshot's health (present? verifies? schema supported?)
PYTHONPATH=src python3 -m cosmosiq_ops backup-health --backup-dir backups

# verify a snapshot against its manifest (sha256 + line counts)
PYTHONPATH=src python3 -m cosmosiq_ops verify --backup-path backups/<snapshot>

# dry-run a restore into an EMPTY target (writes NOTHING)
PYTHONPATH=src python3 -m cosmosiq_ops restore --backup-path backups/<snapshot> \
  --target-dir "$WORK/restored" --dry-run

# real restore into an EMPTY target (verify → schema-gate → integrity + replay)
PYTHONPATH=src python3 -m cosmosiq_ops restore --backup-path backups/<snapshot> \
  --target-dir "$WORK/restored"

# age out old snapshots by ARCHIVING whole directories (active store never touched)
PYTHONPATH=src python3 -m cosmosiq_ops retention --backup-dir backups --keep-latest 3
```

See `docs/INCIDENT_PLAYBOOKS.md` (Storage corruption) for the restore-after-corruption drill.

---

## 8. Rolling back a mode

To step the sanctioned mode **down** the ladder — `PRODUCTION_24X7 → SHADOW_24X7 → MANUAL → OFF` —
use `cosmosiq_ops rollback`. Rollback **never upgrades**. See `docs/ROLLBACK_GUIDE.md` for the full
trigger list and verification steps.

```bash
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$WORK" --to shadow_24x7 \
  --trigger operator_manual
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$WORK" --to off \
  --trigger operator_manual
```

---

## Cross references

- `docs/DEPLOYMENT_GUIDE.md` · `docs/INCIDENT_PLAYBOOKS.md` · `docs/ROLLBACK_GUIDE.md`
- `reports/REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md` (the honest live-SEC snippet + the two limitations)
- `reports/OPERATOR_SIGNOFF_020J_TEMPLATE.md` (the sign-off template) ·
  `reports/SHADOW_VALIDATION_020I.md` (validation report)
</content>
</invoke>
