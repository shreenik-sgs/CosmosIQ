# Real SEC-Backed Shadow Run — Operator Guide (Phase 021D)

How to run CosmosIQ in **real `SHADOW_24X7`** mode against the live SEC EDGAR adapter, capture the
validation evidence, and keep **production mode blocked** until you explicitly sign off. This is
launch *support* — it adds no architecture. Every command below is an existing capability.

> **Boundary (unchanged).** CosmosIQ may operate in `MANUAL` and `SHADOW_24X7` only. It is **not**
> approved for `PRODUCTION_24X7` and must not be represented as production-live, current-data
> recommendation-capable, or production-alerting until the manual-review items are satisfied and an
> explicit operator sign-off is recorded. This guide never enables production and never writes a
> sign-off.

---

## 0. Read this first — two honest limitations

Before you start, know exactly what today's tooling does and does **not** do:

1. **There is no `--live-sec` CLI flag.** `python3 -m cosmosiq_pulse` is offline/fixture-only, and
   `python3 -m cosmosiq_service start --mode shadow_24x7` runs the **default (local/fixture)
   pipeline** — neither wires the live SEC adapter. A **real live SEC fetch** is done today with the
   short **Python snippet in §2** (it calls the existing public API `run_pulse(adapters=[...])`). A
   CLI flag would be a small future enhancement, deliberately out of this documentation phase.

2. **`prod-check` will still show `live_source_health` and `operator_shadow_validation` as
   `manual_review_required`** even after a perfect live run. They "cannot be machine-verified" and
   there is currently **no command that marks them cleared** — the tooling has no
   operator-attestation input for them. So a successful live run gives you the *evidence*, but
   `prod-check` will keep `production_mode_allowed = false`. Reaching production therefore needs, in
   addition to your sign-off, a small future "operator attestation" enhancement to `prod-check` /
   `activate`. **That is not built.** Until it is, production stays correctly blocked and CosmosIQ
   remains shadow/manual — which is the intended, safe state.

Everything below is still worth doing: it produces the genuine live-source and shadow-window evidence
you'll need, and proves the pipeline against real filings.

---

## 1. Prerequisites

- Python 3.9+, this repo checked out, run everything from the repo root with `PYTHONPATH=src`.
- Outbound HTTPS to `data.sec.gov` and `www.sec.gov` (no proxy blocking).
- A **contact identity** for SEC's fair-access policy (see §1.1). SEC is a public regulator; use a
  real name + email. Do **not** invent or spoof contact details.
- Pick a durable **store directory** for the run, e.g. `reports/shadow_live/store` (referred to below
  as `$STORE`). It holds the append-only JSONL stores.

### 1.1 `SEC_USER_AGENT` format

SEC requires a descriptive `User-Agent` that identifies who is making requests. It is a **contact
identity, not a secret** — but CosmosIQ still treats it presence-only (its value is never printed,
logged, or persisted). Format: a name/organisation plus a contact email.

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"
# or:  export SEC_USER_AGENT="AcmeCapital ops@acmecapital.com"
```

Confirm it is set (prints only presence, never the value):

```bash
PYTHONPATH=src python3 -c "import os; print('SEC_USER_AGENT present:', bool(os.environ.get('SEC_USER_AGENT')))"
```

---

## 2. Run a real live SEC-backed pulse (evidence for `live_source_health`)

There is no CLI flag for this yet, so run the existing public API directly. Save as
`run_live_sec_pulse.py` (or paste into `python3 -`). Replace the watchlist/themes/now as you like.

```python
# run_live_sec_pulse.py — a real, live SEC EDGAR-backed pulse using existing public APIs.
import sys; sys.path.insert(0, "src")
from datetime import datetime, timezone
from reality_mesh.adapters.sec_edgar_live import SecEdgarLiveAdapter
from reality_mesh import run_pulse
from reality_mesh.pulse_persistence import persist_and_summarize

STORE = "reports/shadow_live/store"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# transport=None -> the adapter lazily builds the REAL SEC transport and reads SEC_USER_AGENT from the
# environment. If SEC_USER_AGENT is absent it does NOT fetch: it emits an honest credentials_missing
# source gap (no fabricated data, no fixture fallback).
adapter = SecEdgarLiveAdapter()

result = run_pulse(["IREN", "AAOI", "INOD"], ["physical-ai"], now=NOW, adapters=[adapter])

# Inspect the live source health BEFORE persisting.
for ar in result.adapter_results:
    print("adapter:", ar.adapter_id, "| status:", ar.status,
          "| source_health:", ar.source_health, "| gaps:", list(ar.data_gaps))

run, replay, _ = persist_and_summarize(result, store_dir=STORE,
                                       run_id="shadow.live." + NOW.replace(":", "").replace("-", ""),
                                       now=NOW)
print("persisted run:", run.run_id, "| replay deterministic_match:", replay.deterministic_match)
```

Run it:

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"
PYTHONPATH=src python3 run_live_sec_pulse.py
```

### Expected output

- **`SEC_USER_AGENT` set + reachable:** the SEC adapter line shows `status: success` (or `partial`),
  a non-gap `source_health` (reachable/fresh), and real filing events landing (10-K/10-Q/8-K/S-3/424B/
  Form 4 …) with SEC accession + document URLs. `replay deterministic_match: True`.
- **`SEC_USER_AGENT` absent:** `status: skipped`, `source_health: credentials_missing`, a visible gap
  naming `SEC_USER_AGENT` — **no fetch, nothing fabricated, no fixture fallback.** Set the env var and
  re-run.

That successful line **is** your `live_source_health` evidence (reachable + fresh live filings). Note:
`prod-check` does not auto-detect it — see §0 point 2 and §7.

---

## 3. Run a wall-clock `SHADOW_24X7` window (evidence for `operator_shadow_validation`)

This exercises the supervised service continuously over **real wall-clock time**. (It validates the
scheduler/DQ/replay/alert machinery; note the service loop runs the default pipeline, so the *live SEC*
evidence comes from §2, not from this loop — see §0 point 1.)

Start the service (default mode is `OFF`; you must ask for shadow explicitly):

```bash
PYTHONPATH=src python3 -m cosmosiq_service start \
  --mode shadow_24x7 --store-dir "$STORE" [--subscriptions config/watchlists/shadow_watchlist.yaml]
```

- It runs the supervised loop (operator-started; there is no hosted daemon). Each due tick runs a
  pulse through the full 013 chain, generates **shadow** alerts (in-app inbox only, marked *Shadow
  Mode*, never escalated), and updates health. Leave it running for your target window (24h minimum;
  48–72h preferred).
- **Check status / pause / resume** in another shell:

```bash
PYTHONPATH=src python3 -m cosmosiq_service status --store-dir "$STORE"
PYTHONPATH=src python3 -m cosmosiq_service pause  --store-dir "$STORE"
PYTHONPATH=src python3 -m cosmosiq_service resume --store-dir "$STORE"
```

For a fast, deterministic (injected-time, **not** wall-clock) dry run of the same machinery:

```bash
PYTHONPATH=src python3 -m cosmosiq_ops shadow-validate --work-dir /tmp/shadow_dryrun --ticks 24 \
  --start 2026-07-06T13:00:00Z --interval-minutes 60 --report-out reports/SHADOW_VALIDATION_020I.md
```

---

## 4. Inspect the app

Point the local operator app at the same store and open it in a browser:

```bash
PYTHONPATH=src python3 -m cosmosiq_app --store-dir "$STORE"   # serves on 127.0.0.1
```

Pages to check (all read-only; no buy/sell/order control anywhere; a trade-like route returns 403):

| What | Route |
|------|-------|
| Latest run + trigger + gate overall + gaps | `/runs`, `/runs/<run_id>` |
| Source health / agent health / DQ | run detail (`/runs/<run_id>`) + `/api/health`, `/api/coverage` |
| Capital Candidates (eligible / blocked+reason / empty) | `/candidates`, `/candidates/<TICKER>` |
| Company cockpit (explicit ticker only) | `/companies/<TICKER>` |
| Alert Inbox (shadow alerts, marked Shadow Mode) | `/alerts` |
| Replay Viewer (deterministic_match banner) | `/replay/<run_id>` |
| Mode indicator | top strip — in shadow shows `Mode: SHADOW_24X7 · Live Data: … · Scheduler: On · Broker: Disabled · Execution: Manual Review Only · Alerts: Shadow Mode` |

---

## 5. Run `prod-check` (confirm production stays blocked)

```bash
PYTHONPATH=src python3 -m cosmosiq_ops prod-check --work-dir "$STORE"
```

**Expected before sign-off (and, per §0 point 2, even after a good live run):**

```
production_mode_allowed = false
verdict: shadow_24x7_only
manual_review_items: live_source_health, operator_shadow_validation, operator_signoff
```

Exit code is non-zero — that is the correct, safe default.

---

## 6. Stop / pause / roll back

```bash
# stop the supervised service (releases the single-instance lock)
PYTHONPATH=src python3 -m cosmosiq_service stop --store-dir "$STORE"

# pause / resume scheduled ticks without stopping
PYTHONPATH=src python3 -m cosmosiq_service pause  --store-dir "$STORE"
PYTHONPATH=src python3 -m cosmosiq_service resume --store-dir "$STORE"

# roll a sanctioned mode DOWN (never up): PRODUCTION_24X7 -> SHADOW_24X7 -> MANUAL -> OFF
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$STORE" --to shadow_24x7 --trigger operator_manual
PYTHONPATH=src python3 -m cosmosiq_ops rollback --work-dir "$STORE" --to off --trigger operator_manual
```

Rollback triggers (any of): source-failure spike, agent-failure spike, DQ hard-fail spike,
false-positive-alert spike, delivery failure, candidate-eligibility bug, fixture leakage, secret
leakage, unexpected trading/broker control, operator decision.

---

## 7. Where evidence lives + how items clear

| Artifact | Location |
|----------|----------|
| Append-only run stores | `$STORE/*.jsonl` (run / event / finding / signal / theme_pulse / capital_candidate / data_quality / agent_run_ledger) |
| Run history | the app `/runs`; the `run_store.jsonl` |
| Shadow alerts | `$STORE` alert store; the app `/alerts` |
| Replay | the app `/replay/<run_id>`; deterministic_match in run detail |
| Service health | `$STORE/service_health.json`; structured log `$STORE/service_log.jsonl` |
| Validation report | `reports/SHADOW_VALIDATION_020I.md` (or a new dated `reports/SHADOW_VALIDATION_<date>.md`) |
| Live SEC pulse output | the store from §2 + the printed adapter source-health line |

**How to know `live_source_health` cleared (evidence, not an auto-flag):** the §2 pulse returns the SEC
adapter at `status: success` with a non-gap `source_health` and real, freshly-dated filings — reachable
and fresh. `prod-check` still lists it `manual_review` (no attestation input exists; §0 point 2).

**How to know `operator_shadow_validation` cleared (evidence, not an auto-flag):** you ran a real
wall-clock `SHADOW_24X7` window (§3), filled `reports/SHADOW_VALIDATION_020I.md` (ticks succeeded, DQ
clean, replay 0 divergences, no fixture leakage, shadow-only alerts), and reviewed it. Again
`prod-check` keeps it `manual_review`.

**How to keep production blocked (default — do nothing special):** do not create
`reports/OPERATOR_SIGNOFF_020J.md`; `prod-check` returns `production_mode_allowed = false` and
`python3 -m cosmosiq_ops activate` **refuses** (exit non-zero, nothing written). The three manual items
remain blocking. There is no accidental path to production.

---

## 8. Operator checklist

- [ ] `SEC_USER_AGENT` exported with a real name + email (presence confirmed; value never printed).
- [ ] §2 live pulse run → SEC adapter `status: success`, non-gap source health, real dated filings,
      `replay deterministic_match: True`. (Evidence for `live_source_health`.)
- [ ] §3 wall-clock `SHADOW_24X7` window run for ≥24h; `status`/health checked periodically.
- [ ] `reports/SHADOW_VALIDATION_020I.md` (or a dated copy) filled and reviewed → recommendation
      recorded. (Evidence for `operator_shadow_validation`.)
- [ ] App inspected (`/runs`, `/candidates`, `/companies/<T>`, `/alerts`, `/replay/<id>`); candidates
      honest (eligible with full provenance / blocked with reason / none); alerts marked Shadow Mode.
- [ ] `prod-check` run → `production_mode_allowed = false` (expected).
- [ ] Production **not** enabled; no sign-off created; rollback command known.
- [ ] (When you decide to pursue production) fill `reports/OPERATOR_SIGNOFF_020J.md` from the template —
      **your explicit act only** — and be aware the two live/shadow items still need the attestation
      enhancement noted in §0 before `prod-check` can return `true`.

---

Governance: `docs/OPERATOR_RUNBOOK_020C.md` (service) · `docs/OPERATOR_RUNBOOK_020F.md` /
`ACTIVATION_CHECKLIST_020F.md` (activation gate) · `docs/OPERATOR_RUNBOOK_021C.md` (activate/rollback) ·
`reports/OPERATOR_SIGNOFF_020J_TEMPLATE.md` (sign-off) · `reports/SHADOW_VALIDATION_020I.md`
(validation) · `config/shadow_launch_020g.yaml` (launch posture).
