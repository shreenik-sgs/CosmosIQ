# CosmosIQ — Deployment Guide (IMPLEMENTATION-023I)

How to package and run CosmosIQ **locally-first**. This consolidates the 023A–023G deployment
slices (`deploy/README.md`, `docs/DEPLOYMENT_019.md`, `Dockerfile`, `docker-compose.yml`, `Makefile`,
`deploy/launchd/`) into one operator-facing guide. Everything here is thin wiring over the CLIs that
phases 012–023H already shipped — **nothing new runs; nothing changes behaviour.**

> **SAFE BY DEFAULT — production is never auto-enabled.** Every artifact starts CosmosIQ in a safe
> posture (`test_offline` for the container, `shadow_24x7` for the launchd job). There is **no**
> build target, container command, or launchd job that turns on `PRODUCTION_24X7`. Production stays
> the explicit `cosmosiq_ops activate` + operator sign-off path — see `docs/OPERATOR_RUNBOOK.md` §5.

Companion docs: `docs/OPERATOR_RUNBOOK.md` · `docs/INCIDENT_PLAYBOOKS.md` · `docs/ROLLBACK_GUIDE.md`.

---

## 1. What ships

| File | Purpose |
|------|---------|
| `Makefile` | Wires the real CLIs: `test`, `ci`, `smoke`, `prod-check`, `run-shadow`, `run-app`, `backup`, `restore`. There is intentionally **no** `run-production` target. |
| `Dockerfile` | `python:3.9-slim`, non-root, `COSMOSIQ_PROFILE=test_offline`, offline `HEALTHCHECK`, safe CMD (the localhost app). Copies **no** `.env`. |
| `docker-compose.yml` | One service, persistent store volume, config + logs mounts, `.env` env-file (runtime injection), offline healthcheck, safe default command. |
| `deploy/launchd/com.cosmosiq.shadow.plist.template` | macOS launchd template that runs the supervised service in **SHADOW_24X7** (operator fills the `__PLACEHOLDER__` paths). |

---

## 2. Profiles (023A) — safe default, production explicit-only

CosmosIQ resolves an **environment profile** so behaviour is never implicit. The **default is
`test_offline`** (network blocked, fixtures only, everything off) — **never** `production`. A profile
never itself enables production; entering production still requires the activation gate + sign-off.

- Default / safe: `COSMOSIQ_PROFILE=test_offline`.
- The `production` profile only *declares* the production posture; it does **not** flip anything on.

---

## 3. Make targets (local, no Docker required)

```sh
make help          # list targets
make test          # offline unittest suite
make ci            # cosmosiq_ops ci-gate
make smoke         # cosmosiq_ops smoke (offline operator chain)
make prod-check    # cosmosiq_ops prod-check — OFFLINE, refuses production (the safe default)
make run-app       # cosmosiq_app on 127.0.0.1 against ./_cosmosiq_store
make run-shadow    # cosmosiq_service start --mode shadow_24x7 (NEVER production)
make backup        # snapshot + verify the store
make restore       # dry-run restore-check (never writes)
```

Override the store dir with `STORE=/path make run-app`. There is **no** `run-production` target —
production activation is `cosmosiq_ops activate` with sign-off.

The equivalent raw CLIs (what the targets wrap):

```sh
PYTHONPATH=src python3 -m cosmosiq_ops ci-gate
PYTHONPATH=src python3 -m cosmosiq_ops smoke --work-dir /tmp/cosmosiq_work
PYTHONPATH=src python3 -m cosmosiq_ops prod-check --work-dir /tmp/cosmosiq_work
```

---

## 4. Secrets (023B) — runtime injection, presence-only, `.env` untracked

- The **only** committed env file is `.env.example` (env var **names** + obviously-fake
  placeholders). There is no real secret in it and there must never be one.
- Create your real `.env` from it; the real `.env` is **gitignored** and never committed:

  ```sh
  cp .env.example .env    # then edit .env with your OWN values
  ```

- CosmosIQ reads only the **presence** of a var (`name in os.environ`) — a value is never read,
  logged, or persisted. See `docs/OPERATOR_RUNBOOK.md` §2 for the variable list.
- The CI gate (`cosmosiq_ops.ci_gate.check_env_not_tracked`) **fails** if any real `.env` is ever
  tracked. Confirm hygiene with the security audit:

  ```sh
  PYTHONPATH=src python3 -m cosmosiq_ops security-audit
  ```

Secrets are injected at **runtime** (env / `--env-file`), never baked into the image.

---

## 5. Container (the operator's step)

> **HONEST NOTE.** CosmosIQ's offline test suite validates the packaging **structure** and that
> every wrapped command works offline and that nothing auto-enables production. It does **not** run
> `docker build` or `docker compose up` — CI is offline. **Building and running the container is the
> operator's step.** No container was built or run by CosmosIQ CI.

```sh
cp .env.example .env                 # runtime secret injection (gitignored)
docker build -t cosmosiq:local .
docker compose up                    # safe default: the localhost app, test_offline profile
```

The image runs as non-root, sets `COSMOSIQ_PROFILE=test_offline`, mounts a persistent store volume,
and its healthcheck hits `/api/health` offline. It never enables production.

---

## 6. launchd (macOS) — supervised SHADOW_24X7

`deploy/launchd/com.cosmosiq.shadow.plist.template` runs the supervised service in **SHADOW_24X7**
(never production). Fill the `__PLACEHOLDER__` paths, install it into `~/Library/LaunchAgents/`, and
load it with `launchctl`. It wraps exactly:

```sh
PYTHONPATH=src python3 -m cosmosiq_service start --mode shadow_24x7 --store-dir /your/store
```

---

## 7. Persistence hardening (023D) + backup / restore (023F)

The append-only JSONL stores are hardened: a per-line sha256 seal, structural + monotonic-append
integrity checks that **name the store + line** on corruption, and a schema-compatibility gate that
refuses restoring an unsupported schema. The active store is never edited or pruned. Operate it with
the backup / restore / retention CLIs in `docs/OPERATOR_RUNBOOK.md` §7:

```sh
PYTHONPATH=src python3 -m cosmosiq_ops backup --store-dir "$STORE" --backup-dir backups
PYTHONPATH=src python3 -m cosmosiq_ops verify --backup-path backups/<snapshot>
PYTHONPATH=src python3 -m cosmosiq_ops restore --backup-path backups/<snapshot> \
  --target-dir "$WORK/restored"
```

---

## 8. Observability (023E)

A single sanitized surface aggregates every health signal (service / source / agent / scheduler /
alert-delivery / DQ / run latency / storage integrity / backup / env presence) into one rolled
`status` (ok / degraded / failed). It is read-only, deterministic, and never emits a secret / score /
trade. Reach it through the app:

```sh
curl -s http://127.0.0.1:8016/api/observability
```

---

## 9. CI/CD gate (023G) — prod-check as the deployment gate

`prod-check` is the offline production-activation gate. It composes every guardrail sweep and, by
default, **refuses production** (`production_mode_allowed=false`, non-zero exit) — so a pipeline can
gate on it without any risk of auto-enabling production:

```sh
PYTHONPATH=src python3 -m cosmosiq_ops prod-check --work-dir /tmp/cosmosiq_work
```

Real production activation is never a deploy-pipeline step: it is the explicit `cosmosiq_ops
activate` flow plus an operator sign-off plus the manual review items (see `docs/OPERATOR_RUNBOOK.md`
§5, and the honest limitations there and in `reports/REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md`).

---

## Cross references

- `docs/OPERATOR_RUNBOOK.md` · `docs/INCIDENT_PLAYBOOKS.md` · `docs/ROLLBACK_GUIDE.md`
- `deploy/README.md` · `docs/DEPLOYMENT_019.md` · `.env.example`
</content>
