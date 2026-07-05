# Deployment — Single-Machine Local CosmosIQ (Phase 019)

How to deploy **CosmosIQ** the only way it is meant to run today: **on one machine, locally,
started by an operator**. There is no server fleet, no container orchestration, no message
broker, no scheduler process, and no trading connection. This document is the deployment
contract; the day-to-day commands live in `docs/OPERATOR_RUNBOOK_019.md`.

Governance: `PROJECT_CONTEXT.md` · `docs/OPERATOR_GUIDE_013.md` (persistence/replay) ·
`docs/OPERATOR_GUIDE_016.md` (the app) · the Phase-013/015 contracts.

---

## 1. What a deployment is

- **Python 3.9, standard library only.** No third-party runtime dependency; no build step.
- **One machine.** Put the checkout somewhere stable, pick a persist directory, start the app
  and run pulses against it (`docs/OPERATOR_RUNBOOK_019.md` §1–2).
- **The persist dir is the deployment's state.** It holds the append-only JSONL stores plus the
  operator files (portfolio, diligence inputs, personal profile, subscriptions). Keep it **out
  of Git** (write it somewhere like `generated/`), and back it up with `cosmosiq_ops backup`.
- **The operator owns the cadence.** A "scheduled" pulse is still one synchronous command; if you
  want it to recur, wrap the command in the OS scheduler **you** control (cron / launchd /
  Task Scheduler). CosmosIQ starts nothing by itself.

Verify a fresh (or upgraded) deployment with the production smoke and the CI gate:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops smoke --work-dir <fresh dir> --now <ISO instant>
PYTHONPATH=src python3 -m cosmosiq_ops ci-gate
```

## 2. Secrets policy — env-only

Credentials enter the system **exclusively as environment variables**, passed explicitly into
the two sanctioned shells (`cosmosiq_app/server.py`, `evidence_ingestion/live_transport.py`) and
nowhere else. The known variables are `SEC_USER_AGENT` (SEC EDGAR fair-use identification) and
`FMP_API_KEY` (Financial Modeling Prep) — both consumed only by the live transport shell.

The policy, enforced not just stated:

- **`.env` files are never tracked.** The CI gate runs `git ls-files` and **fails** if any `.env`
  is tracked. Keep secrets in your shell / OS keychain, or an untracked `.env` you `source`
  yourself — never committed.
- **Stores refuse credential keys (the 013B guard).** `reality_mesh.stores` **rejects** any
  record whose key contains a credential token (`api_key`, `client_secret`, `access_key`,
  `private_key`, `auth_token`, …). A store can never hold a secret — an attempt raises rather
  than writes.
- **Reports and pages carry NAMES + presence labels only.** `cosmosiq_ops env` prints
  `present`/`absent` per variable and never reads a value (`name in os.environ` is the only
  access). No page or report ever renders a secret value.

Check it any time with `python3 -m cosmosiq_ops env`.

## 3. Schema-version compatibility contract

Every persisted record carries a `schema_version`. Upgrades stay compatible under three rules:

- **`schema_version` on every record.** It is stamped on write and preserved on read; the CI
  gate's schema-validation check proves it.
- **Additive-only.** A new schema version may **add** optional fields; it never renames, retypes,
  or removes an existing field. Old records keep reconstructing to their typed objects unchanged,
  so a store written by an older build still reads (and replays) under a newer one.
- **Corrections, not mutations.** A wrong value is fixed by appending a **new** record (an
  `AuditStore` correction referencing the corrected id) — never by editing a stored line. The
  append-only history is the revision history.

Because of this, a backup taken under one schema version restores and verifies under a
compatible later one; a `verify` mismatch means the file was **altered**, not merely upgraded.

## 4. Retention & backup — archive, never edit

Backups and stores are append-only artifacts:

- A snapshot copies the **whole store** and records a sha256 + line count per file in
  `manifest.json`; `verify` recomputes and **NAMES** any divergence.
- Aging a snapshot out means **moving its whole directory under `<backup-dir>/archive/` intact**.
  Nothing inside is pruned, deleted, or rewritten. The default is **keep everything**.
- A restore only ever targets a **missing or empty** directory; a non-empty store is never
  overwritten in place (`restore-check` refuses it). Restore into a fresh directory and inspect.

## 5. Still forbidden — approval-gated for Phase 020+

The following are **not** part of a Phase-019 deployment and remain forbidden until a future
phase unlocks each behind an explicit, approved ADR:

- **No broker / execution.** No broker connection, no order/submit/execute endpoint. Execution is
  **manual preview only**; any trade-like route returns `403: execution is manual preview only;
  no trading endpoints exist`. A real execution intent flow is Phase 020+, approval-gated.
- **No 24×7 daemon.** No background process, no loop, nothing that starts by itself. The operator
  (or the OS scheduler the operator controls) starts every pulse. An autonomous scheduler is
  Phase 020+, approval-gated.
- **No hidden score / rank.** No numeric investability / score / rank / rating field anywhere; the
  CI gate's AST sweep fails the build if one appears. Labels and ranges only.
- **No network in the runtime; no secret in any output.** The runtime packages import no
  network module outside the two sanctioned shells, and no report or page ever carries a secret
  value.

The operator toolkit (`cosmosiq_ops`) is the single sanctioned exception for `subprocess`
(suite + `git` reads) and the wall clock (duration **measurement** only, never a runtime
behaviour) — and it is never imported by runtime code.
