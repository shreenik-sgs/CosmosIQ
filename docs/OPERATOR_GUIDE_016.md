# Operator Guide — The CosmosIQ App (Phase 016)

How to run and use the **CosmosIQ local operator app** — the product surface over the persisted
Reality-Mesh stores. It is a **local, operator-started** application: you start it, it serves on
localhost, and it stops when you stop it. It ships **no daemon, no scheduler process, no broker
connection, and no trading endpoint of any kind** — an attempt to reach a trade-like route returns
`403: execution is manual preview only; no trading endpoints exist`.

Governance: `architecture/SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` ·
`architecture/adr/ADR-CANDIDATE-015_SCHEDULED_PULSE_UNLOCK.md` · `docs/OPERATOR_GUIDE_013.md`
(persistence/replay) · `docs/OPERATOR_GUIDE_015.md` (scheduled ticks + alerts).

---

## 1. Start the app

```bash
PYTHONPATH=src python3 -m cosmosiq_app --store-dir <your persist dir> [--port 8321]
```

- Binds **127.0.0.1 only** by default (a non-local host is refused unless `--allow-remote`, which
  prints a no-auth warning).
- The store dir is the same `--persist-dir` your pulses write (see OPERATOR_GUIDE_013/015).
- Every page carries an honest strip: *as of ⟨persisted run time⟩ · manual/scheduled pulse data ·
  refreshed only when a pulse is run* — the app never claims to be live.

## 2. The user workflows → where they live

| Workflow | Page |
|---|---|
| Add / edit watchlist & themes & subscriptions | **Settings** (`/settings` — Save settings appends a journal snapshot) |
| Run a manual pulse | **Home / Runs** — the *Run manual pulse* form ("manual, on-demand; no scheduler started") |
| Inspect the latest pulse | **Runs** (`/runs`, newest first: trigger attribution, gate overall, health, gaps) |
| Inspect WHY a theme changed | **Theme cockpit** (`/themes/<theme>` — the pulse-state timeline + the persisted-state diff naming state A → state B between run X → run Y, with the inbox alert reason when one fired) |
| Inspect source gaps | Run detail (`/runs/<id>` — persisted + coverage gaps) and every cockpit's gaps panel |
| Inspect weak social signals | Theme cockpit / run detail — narrative signals carry the **WEAK — uncorroborated; corroboration required** mark |
| Inspect contradictions | Run detail + theme cockpit — both sides preserved, never averaged |
| Inspect agent failures | Run detail — per-agent status/health badges (failed / blocked_by_policy shown honestly) |
| Run history | **Runs** (`/runs`) |
| Replay a prior run | **Replay viewer** (`/replay/<run_id>` — `deterministic_match` verdict banner; a divergence renders FAILURE with the named field, `persisted=` vs `recomputed=`) |
| Open a company cockpit | `/companies/<TICKER>` — per-ticker events/findings/signals, claim-status labels (a company claim is shown as UNVERIFIED, never as a fact) |
| View a capital candidate | `/candidates/<TICKER>` — see §3 |
| View portfolio fit | The candidate cockpit's fit section (renders only when a personal profile / portfolio snapshot is recorded in the store; honest absence otherwise) |
| View manual execution preview | The candidate cockpit's preview section — **read-only**; see §3 |
| Acknowledge an alert / pause / resume a cadence | **Alerts** (`/alerts`) + Runs — the operator forms (Acknowledge / Pause / Resume) |

## 3. The capital-candidate cockpit (`/candidates/<TICKER>`)

The diligence verdict is computed **on demand at page render by the already-accepted engines** over
operator-recorded inputs at `<store>/diligence_inputs/<TICKER>.json` (domain, source observations,
optional hand-fed base candidate, optional enrichment areas, optional forward-scenario cases).
Deterministic given those inputs; labels and ranges only.

- **No inputs recorded** → *"insufficient inputs — no thesis fabricated."* Nothing is invented to
  fill a page.
- **Malformed inputs** → the parse error is named; *"nothing is guessed."*
- **Execution preview** is a **read-only display** of a recorded `ManualExecutionPreview`
  (`broker_order_id` always `None`; *"manual preview only — no order is placed"*). With none
  recorded the section says *"no manual execution intent recorded."* Creating an intent is a
  separate, explicitly-approved flow — **not** part of this app (Phase 020+, approval-gated).

## 4. What this app does NOT do

- **No trading**: no buy/sell/order/submit control exists on any page; no trading endpoint exists in
  the API (403 by construction). Execution remains **manual preview only** (Phase 020+ expansion is
  approval-gated behind a new ADR).
- **No daemon / no auto-refresh / no streaming**: the app renders persisted data; new data appears
  only when a pulse runs (manually, or via the operator-owned scheduled tick loop of
  OPERATOR_GUIDE_015). `streaming` remains a reserved, rejected trigger.
- **No secrets**: credentials appear as presence labels only; a secret-bearing settings write is
  rejected and never persisted.
- **No hidden scores**: labels, ranges, and volume counts only — everywhere.

## 5. Cross references
`OPERATOR_GUIDE_012.md` (manual pulse) · `OPERATOR_GUIDE_013.md` (persistence/replay/health/gates) ·
`OPERATOR_GUIDE_015.md` (cadence ticks, alerts, pause/resume) ·
`docs/product/BRAND_NOMENCLATURE.md` (naming).
