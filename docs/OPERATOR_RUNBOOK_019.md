# Operator Runbook — Day-to-Day CosmosIQ Operations (Phase 019)

The everyday operator's runbook for a running **CosmosIQ** install: how to start the app, run a
pulse, read health and alerts, take and verify backups, run the production smoke, and run the CI
gate — plus the basics of the two incidents you are most likely to meet.

Everything here is **offline, local, and deterministic**. CosmosIQ ships **no daemon, no
scheduler process, no broker connection, and no trading endpoint of any kind**. The Phase-019
operator toolkit (`cosmosiq_ops`) is **operator tooling, not runtime** — it is the one place
allowed a real wall clock (only to measure durations) and `subprocess` (only to run the suite
and read `git`); the runtime packages (`reality_mesh`, `cosmosiq_app`) stay clock-free and
subprocess-free.

Governance: `docs/OPERATOR_GUIDE_013.md` (persistence/replay) · `docs/OPERATOR_GUIDE_015.md`
(scheduled ticks + alerts) · `docs/OPERATOR_GUIDE_016.md` (the app) · `docs/DEPLOYMENT_019.md`
(deployment + secrets + schema-compatibility policy).

The one command surface for Phase-019 tooling is:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops <ci-gate|smoke|backup|verify|restore-check|perf|env>
```

Every command **prints its report and exits non-zero on failure**, so a shell or CI pipeline
can gate on it.

---

## 1. Start the app

```bash
PYTHONPATH=src python3 -m cosmosiq_app --store-dir <your persist dir> [--port 8321]
```

- Binds **127.0.0.1 only** by default; the store dir is the same one your pulses write.
- Every page carries the honest as-of strip — the app never claims to be live.
- Stop it the way you started it (Ctrl-C / stop the process). There is nothing to daemonize.

## 2. Run a pulse / a scheduled tick

A pulse is always **one synchronous command** — manual and on-demand; nothing starts by itself.

```bash
# manual, on-demand pulse
PYTHONPATH=src python3 -m cosmosiq_pulse --watchlist IREN,NVDA --themes physical_ai,robotics \
    --persist-dir <your persist dir> --now <ISO instant>

# one scheduled tick (asks the cadence core what is due; runs it; exits) — see OPERATOR_GUIDE_015
PYTHONPATH=src python3 -m cosmosiq_pulse --tick --persist-dir <your persist dir> \
    --tick-now <ISO instant>
```

Each pulse runs the full Phase-013 chain (append-only stores → ledger → health → gates →
deterministic replay) and prints what happened. A pulse writes **new** records only; no stored
line is ever rewritten.

## 3. Read alerts and health

- **Alerts** (`/alerts`): the append-only inbox. An alert **observes, never executes** — it
  names a state change and points at its evidence. Acknowledge from the page; ack appends a
  record, it never edits the alert. On the **first** persisted run the inbox is **quiet by
  design** (a baseline — nothing to compare yet); state-change alerts begin with the next run.
- **Health** (`/runs`, run detail): per-run gate overall, per-agent status/health badges,
  source health, and gaps. A degraded or failed run still renders — honestly — it never crashes
  the pulse.

## 4. Backup, verify, restore

Backups are **snapshots of the whole store** — append-only artifacts, never edited in place.

```bash
# snapshot the store and verify the roundtrip in one step
PYTHONPATH=src python3 -m cosmosiq_ops backup --store-dir <store> --backup-dir <backups> \
    --now <ISO instant>
```

This copies every `*.jsonl` store plus the operator files (portfolio, diligence inputs, personal
profile, subscriptions) into `<backups>/snapshot-<instant>/`, writes a `manifest.json` with a
sha256 + line count per file, and re-verifies. Then, at any time:

```bash
# re-verify an existing snapshot against its manifest (sha256 + line counts)
PYTHONPATH=src python3 -m cosmosiq_ops verify --backup-path <backups>/snapshot-<instant>

# dry-run a restore — NEVER writes; refuses a non-empty target
PYTHONPATH=src python3 -m cosmosiq_ops restore-check --backup-path <snapshot> --target-dir <new dir>
```

**A restore only ever goes into a missing or empty directory.** An existing non-empty store is
**never** overwritten in place — restore into a fresh directory and inspect it there. Aging a
snapshot out means **moving its whole directory under `<backups>/archive/` intact** — a store or
snapshot line is never pruned, deleted, or rewritten.

## 5. Production smoke

Before trusting a fresh install (or after an upgrade), run the full operator chain end-to-end
against a scratch work dir, offline:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops smoke --work-dir <fresh dir> --now <ISO instant>
```

It walks: pulse → persist → **deterministic replay** → **gates raise no hard fail** → the app
renders `/`, `/runs`, `/portfolio` (honest absence when nothing is recorded), `/themes` as 200
HTML → the alert inbox is **quiet on the first run** → a backup snapshot **verifies clean**. Each
step prints pass/fail with a plain reason; overall pass only if every step passed (exit 0).

## 6. CI gate

The gate re-proves every guardrail as code, in one command:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops ci-gate            # full: also runs the offline suite
PYTHONPATH=src python3 -m cosmosiq_ops ci-gate --quick    # every sweep, skips the suite run
```

It proves: the whole unittest suite passes **offline** (under a socket kill-switch); no
network/scheduler/broker import outside the two sanctioned shells; no `*score*`/`*rank*`
function; the runtime packages stay free of `subprocess` and wall-clock calls; the demo build is
byte-identical run-to-run and to the default; rendered pages carry zero Sanskrit /
trade-affordance / secret tokens; no `.env` is tracked by git; and the frozen specification tree
has no uncommitted edits.

## 7. Environment / secrets check

```bash
PYTHONPATH=src python3 -m cosmosiq_ops env
```

Prints env-var **NAMES + presence labels only** (`present` / `absent`) and the secrets policy —
**never a value**. Presence is computed with `name in os.environ`; the value is never read.

---

## 8. Incident basics

### 8.1 A source failed → a gap, not a crash

A missing or failed data source becomes a **visible `data_gap`** on the run — never a fabricated
value and never a silent fall-back to the bundled fixtures. Where to look:

- **Run detail** (`/runs/<id>`) — the gaps panel names the missing source; the affected agent
  shows `partial`/`failed` with its health badge.
- The pulse still completes and still persists; downstream stays honest ("insufficient inputs —
  no thesis fabricated" rather than an invented number).

Action: fix the source file / credential, then run another pulse. Nothing needs restarting.

### 8.2 A store was tampered with → replay surfaces it

The append-only stores are integrity-checked two ways:

- **`verify`** on a backup recomputes every file's sha256 + line count against the manifest and
  **NAMES** any mismatched / missing / extra file.
- **Deterministic replay** re-computes a run's outputs from its persisted inputs and compares
  field-by-field: a tampered store yields `deterministic_match = False` with the **named**
  divergence (`persisted=` vs `recomputed=`), visible on `/replay/<run_id>` and in the smoke's
  `replay_deterministic` step.

Action: do **not** edit the store to "fix" it (that violates append-only). Restore the last
**verified** snapshot into a fresh directory (`restore-check` first, it refuses a non-empty
target), point the app at it, and re-run the pulse. A correction is a **new** record referencing
the corrected id — never a mutation.

---

## 9. The still-forbidden list

No broker connection, no order/execution endpoint, no 24×7 daemon or background loop, no hidden
score/rank, no network in the runtime, no secret value in any report or page. These remain
**approval-gated for Phase 020+** — see `docs/DEPLOYMENT_019.md`.
