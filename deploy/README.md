# CosmosIQ — Deployment Packaging (IMPLEMENTATION-023C)

A **local-first** packaging path for CosmosIQ. Everything here is thin wiring over the CLIs
that phases 012–023B already shipped (`cosmosiq_ops`, `cosmosiq_service`, `cosmosiq_app`).
Nothing new runs; nothing here changes behaviour.

> **SAFE BY DEFAULT — production is never auto-enabled.** Every artifact in this directory
> starts CosmosIQ in a safe posture (`test_offline` for the container, `shadow_24x7` for the
> launchd job). There is no build target, container command, or launchd job that turns on
> `PRODUCTION_24X7` or `production_manual_review`. Production activation stays the **explicit**
> `cosmosiq_ops activate` + operator sign-off path (021C/022H). See `PROJECT_CONTEXT.md`,
> `docs/DEPLOYMENT_019.md`, `docs/OPERATOR_RUNBOOK_020C.md`, and `docs/OPERATOR_RUNBOOK_021C.md`.

## Honest scope of what CosmosIQ's tests prove

The offline test suite (`tests/test_deployment_packaging.py`) validates the packaging
**structure** and that every wrapped command works **offline** and that nothing auto-enables
production. It does **not** run `docker build` or `docker compose up` — CosmosIQ CI has no
Docker and is offline. **Building and running the container is the operator's step.** No
container was built or run by CosmosIQ; do not read the green suite as a container build.

## What is here

| File | Purpose |
|------|---------|
| `Makefile` (repo root) | Wires the real CLIs: `test`, `ci`, `run-shadow`, `prod-check`, `backup`, `restore`, `smoke`, `run-app`, `help`. No `run-production`. |
| `Dockerfile` (repo root) | `python:3.9-slim`, non-root, `COSMOSIQ_PROFILE=test_offline`, offline `HEALTHCHECK`, safe CMD (the localhost app). Copies **no** `.env`. |
| `docker-compose.yml` (repo root) | One service, persistent store volume, config + logs mounts, `.env` env-file (runtime injection), offline healthcheck, safe default command. |
| `deploy/launchd/com.cosmosiq.shadow.plist.template` | macOS launchd template that runs the supervised service in **SHADOW_24X7** (operator fills the `__PLACEHOLDER__` paths). |

## Make targets (local, no Docker required)

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

Override the store dir with `STORE=/path make run-app`. There is intentionally **no**
`run-production` target — production activation is `cosmosiq_ops activate` with sign-off.

## Container (operator's step)

Secrets are injected at **runtime**, never baked into the image. First create your real
`.env` from the committed template (the real `.env` is gitignored):

```sh
cp .env.example .env      # then edit .env with your own values (presence-only; never logged)
```

Then, **as the operator**, build and run:

```sh
docker build -t cosmosiq:local .
docker compose up            # safe default: the localhost operator app, profile test_offline
```

The image copies no `.env`; `docker compose` reads your `.env` at runtime via `env_file`.
The default command is the localhost-only app (`127.0.0.1:8016`) — CosmosIQ has no
authentication, so it stays local by default (the app refuses a non-local host without an
explicit `--allow-remote`). To run the supervised **shadow** service in a container instead,
override the command with `cosmosiq_service start --mode shadow_24x7 --store-dir /data/store`.
There is no supported command that starts production.

## launchd (macOS, shadow only)

```sh
cp deploy/launchd/com.cosmosiq.shadow.plist.template ~/Library/LaunchAgents/com.cosmosiq.shadow.plist
# edit the file: replace __REPO_ROOT__, __STORE_DIR__, __LOG_DIR__,
#                        __LIVE_WATCHLIST__, __LIVE_THEMES__ with real values
launchctl load ~/Library/LaunchAgents/com.cosmosiq.shadow.plist
```

The template runs `--mode shadow_24x7` only. There is no production launchd template.

### The continuous-shadow opt-in and the live paper window (GO-LIVE PL-5)

Continuous `SHADOW_24X7` is **safe** — inbox-only alerts, **no** external delivery, **no** broker,
**no** orders — but it does not run on a bare `start --mode shadow_24x7`. That still **refuses**
(safe default). To run the continuous paper/observation window you must pass the **explicit
operator opt-in** `--confirm-continuous-shadow`, and to source real evidence you add
`--live-sources`:

```sh
PYTHONPATH=src python3 -m cosmosiq_service start \
  --mode shadow_24x7 --confirm-continuous-shadow --live-sources \
  --store-dir ./_cosmosiq_store \
  --live-watchlist IREN,NBIS --live-themes physical_ai,robotics
```

Continuous `PRODUCTION_24X7` is **always** refused here regardless of any flag — production
activation stays the explicit `cosmosiq_ops activate` + operator sign-off path; there is no launchd
job and no flag that starts it.

**Credentials via the wrapper — never in the plist.** launchd does **not** inherit your login-shell
environment, and secrets are **never** written into the plist. The template's `ProgramArguments`
run a small `zsh -lc` wrapper that sources your gitignored `.env` (`. __REPO_ROOT__/.env`) at
**runtime**, then `exec`s the service — so `SEC_USER_AGENT` / `FMP_API_KEY` load from your `.env`
(presence-only; the plist references only the `.env` **path**, never a value). If `.env` is absent,
the live pulse takes an **honest** credential gap (no fixture fallback, nothing fabricated). Create
your `.env` from the committed template first (`cp .env.example .env`).

Running this window accumulates the **PL-2 shadow-validation window** (`>= 3` runs / `>= 2` days of
continuous shadow) that the operator then **attests** before any production activation is even
eligible.

## Invocation

The Makefile / launchd / container use the repo's own documented invocation
`PYTHONPATH=src python3 -m cosmosiq_service start …` (see `docs/OPERATOR_RUNBOOK_020C.md`).
`python3 -m cosmosiq_service` imports cleanly in a fresh process (the 022H core→shell import
cycle was fixed in 023C by making `reality_mesh`'s lazy `__getattr__` defer the recommendation-
activation import — see `src/reality_mesh/__init__.py`). The container's safe default is the
**app** (`cosmosiq_app`, localhost only); the launchd template runs the supervised service in
`SHADOW_24X7`. Both entrypoints import cleanly.
