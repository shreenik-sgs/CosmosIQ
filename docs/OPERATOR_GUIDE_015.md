# Operator Guide — Scheduled Pulse, Alerts, and Operator Controls (Phase 015)

How to run the Reality-Mesh pulse on a **cadence** — one explicitly-invoked tick at a time —
and how to read the **alert inbox** it fills. Phase 015 changes *when* pulses run and *what an
operator gets told*; it changes **nothing** about what a pulse may conclude, and it adds **no
autonomy**: CosmosIQ ships **NO daemon**, no background process, no loop, and nothing that
starts by itself.

Everything here is **offline, deterministic, and evidence-only**. Alerts **OBSERVE — they never
execute**: an alert is a frozen record that names a state change and points at its evidence; a
human reads it and decides. There is no action field on an alert and no way to act from one.

Governance: `architecture/ADR-CANDIDATE-015_SCHEDULED_PULSE_UNLOCK.md` plus the Phase-013
contracts (see `docs/OPERATOR_GUIDE_013.md`). `cosmosiq_pulse` is the approved (English-named)
command; the legacy `tattva_pulse` invocation remains a working **deprecated alias** only —
use `cosmosiq_pulse` in all runbooks.

The JSONL stores under `--persist-dir` are **local operator data** — keep them out of Git
(write them somewhere like `generated/`).

---

## 1. The scheduled-tick workflow — one tick, explicitly started, never a daemon

A "scheduled" pulse is still **one synchronous command**: it asks the cadence core what is due
at the injected `--tick-now` instant, runs each due policy's subscribed pulse through the full
Phase-013 chain (append-only stores, ledger, health, gates, deterministic replay), generates
diff-based alerts, journals the schedule state, prints what happened and why, and **exits**.

The cadence loop itself is **owned by the operator**, not by CosmosIQ. Either:

- you run the tick command by hand whenever you want a tick, **or**
- you start an **external** loop you own — e.g. `cron` or `launchd` on macOS — that invokes the
  one-tick command on your chosen rhythm.

CosmosIQ itself ships **no daemon, no scheduler process, no background thread**: if nobody
(human or operator-started cron/launchd job) invokes the command, nothing ever runs.

### The one-tick command

```bash
PYTHONPATH=src python3 -m cosmosiq_pulse \
  --scheduled-tick \
  --persist-dir generated/pulse_store \
  --tick-now 2026-06-29T15:00:00Z \
  --subscriptions subscriptions.json
```

- `--scheduled-tick` — run exactly ONE tick, then exit. Requires the three flags below.
- `--persist-dir` — the local append-only store directory. The tick persists runs here, reads
  the previous run for alert diffs, and journals schedule state to
  `schedule_state_store.jsonl` (append-style: a new line per tick, prior lines byte-unchanged;
  the next tick resumes from the latest line).
- `--tick-now` — the injected ISO-8601 instant the tick decides at. **Required**: the wall
  clock is never read, so a cron wrapper passes the current instant explicitly (e.g.
  `--tick-now "$(date -u +%Y-%m-%dT%H:%M:%SZ)"`).
- `--subscriptions` — a local JSON file naming what each policy pulses over. Labels and local
  paths only — no secrets, no endpoints:

```json
{
  "subscriptions": [
    {
      "subscription_id": "sub.core",
      "watchlist": ["IREN", "AAOI", "AMBA", "OUST"],
      "themes": ["physical-ai", "robotics", "ai-power"],
      "policy_ids": ["cadence.news_filings", "cadence.social_narrative"]
    }
  ],
  "max_runs_per_hour": 60
}
```

- `--max-pulses` — optional cap on pulse attempts per tick (default 1); remaining due policies
  wait for the next explicit tick.
- `--fixture-dir` — optional fixture override; pulses stay OFFLINE, local JSON only.

The tick prints every decision honestly: what ran (with `deterministic_match`), what failed
(with backoff), what was skipped and **why** (paused / backoff / throttled / market closed /
interval not elapsed / max_pulses / no subscription), any alerts appended, and where the
schedule state was journaled.

## 2. Cadences — the default policies

Cadence policies are data (minutes between runs), not autonomy. The defaults:

| Policy | Cadence | Market hours only |
|--------|---------|-------------------|
| `cadence.social_narrative` | 5 min | no |
| `cadence.news_filings` | 5 min | no |
| `cadence.market_regime` | 15 min | yes |
| `cadence.sector_rotation` | 15 min | yes |
| `cadence.theme_rotation` | 15 min | yes |
| `cadence.technical_regime` | 15 min | yes |
| `cadence.sec_filings` | 60 min | no |
| `cadence.company_documents` | daily | no |
| `cadence.macro_regime` | 60 min | no |
| `cadence.learning_daily` | daily | no |
| `cadence.learning_weekly` | weekly | no |

Guard rails, all enforced per tick: a global `max_runs_per_hour` throttle, deterministic
exponential failure backoff (capped at 24h, no jitter), a market-hours calendar for
market-hours-only policies, and pause/resume (below). A failing policy backs itself off and
**never** aborts the tick for the others.

## 3. Pause and resume — one-shot operator controls

Both journal the new schedule state as a NEW line in `schedule_state_store.jsonl` (append-only;
nothing is rewritten), print what changed, and exit. `--tick-now` is the injected instant that
gets journaled.

```bash
# pause one policy (or every policy with 'all')
PYTHONPATH=src python3 -m cosmosiq_pulse --pause-policy cadence.news_filings \
  --persist-dir generated/pulse_store --tick-now 2026-06-29T15:05:00Z

# resume it later
PYTHONPATH=src python3 -m cosmosiq_pulse --resume-policy cadence.news_filings \
  --persist-dir generated/pulse_store --tick-now 2026-06-29T16:00:00Z
```

- A paused policy (or a fully paused schedule) never runs, and every tick names the pause as
  the skip reason.
- **Resume lifts the pause only** — an unexpired failure backoff still applies; resuming a
  failing policy does not erase its failure history.

## 4. Alerts — observations, never actions

After each persisted scheduled pulse, the tick **diffs this run's persisted state against the
previous persisted run** (signals, theme pulses, findings, data-quality records — all from the
append-only stores). A state **change** produces an alert; sameness stays **quiet** — an
unchanged reality produces zero alerts. The **first** persisted run is a **baseline**: one
visible note, no alert flood. A failed scheduled pulse also produces one honest failure alert.

Every alert is a frozen record: id, run, **category** (closed vocabulary), **severity label**
(`info` / `notice` / `warning` / `critical` — labels, never scores), a **REQUIRED
plain-English reason** naming the evidence, subject tickers/themes, evidence references, and a
created-at instant. There is **no action field**.

### The closed alert categories

| Category | Fires when | Default severity |
|----------|------------|------------------|
| `market_regime_changed` | a market-regime signal's direction flipped between runs | warning |
| `sector_rotation_detected` | a sector-rotation signal appeared or changed direction | notice |
| `theme_pulse_changed` | a theme pulse changed state (e.g. Warming → Igniting) | notice (warning if Breaking down / Exhausting) |
| `filing_dilution_risk` | a new dilution-related filing finding appeared | warning |
| `social_narrative_spike` | narrative velocity reached an elevated urgency/magnitude (weak/social tier — the reason says corroboration is required) | notice |
| `crowding_warning` | a theme's crowding label newly reached major/extreme | warning |
| `source_data_quality_failure` | a data-quality check newly failed, or a scheduled pulse failed | critical |
| `thesis_deteriorated` | reserved for the diligence layer (no emitter yet) | warning |
| `new_opportunity_hypothesis` | reserved for the discovery layer (no emitter yet) | info |
| `major_risk_emerged` | reserved for the risk layer (no emitter yet) | critical |

### Reading and acknowledging alerts

```bash
# read the inbox (read-only, one-shot)
PYTHONPATH=src python3 -m cosmosiq_pulse --list-alerts \
  --persist-dir generated/pulse_store

# acknowledge one alert by id
PYTHONPATH=src python3 -m cosmosiq_pulse --ack-alert alert.sched.cadence.news_filings.20260629T150000Z.market_regime_changed.sig-market-regime \
  --persist-dir generated/pulse_store --tick-now 2026-06-29T15:10:00Z
```

Alerts live in `alert_store.jsonl` (append-only). **Acknowledging never edits the alert**: it
appends a NEW acknowledgment record referencing the alert id to `alert_ack_store.jsonl`; the
original alert line stays byte-unchanged forever. `--list-alerts` shows each alert as
`open` or `acknowledged` by joining the two stores. The optional alert-inbox HTML panel
(`build_alert_inbox_panel`) follows the same discipline: nothing in it is clickable —
acknowledgment happens via the CLI, not a button.

## 5. Still forbidden (unchanged by Phase 015)

Phase 015 unlocked **cadence + alerting only**. Everything else on the hard-forbidden list
stays forbidden and approval-gated:

- **No auto-buy/sell** and no buy/sell recommendation from any alert or pulse — an alert never
  says what to do, only what changed.
- **No broker execution** and no broker connection of any kind. Execution remains **manual
  execution preview only** (a human-readable preview a human may act on outside the system);
  any expansion is **Phase 020+ approval-gated** and requires a new ADR.
- **No auto-rebalance** — no automatic portfolio change of any kind.
- **`streaming` stays reserved** — the streaming trigger type is still rejected; there is no
  always-on, real-time, or live feed. Cadence is the only unlock, and it only ever runs when
  an operator (or an operator-started cron/launchd job) invokes the one-tick command.
- **No hidden score** — severities and every other quality are labels from closed
  vocabularies.

## 6. The store files at a glance

| File | What it holds |
|------|---------------|
| `run_store.jsonl` … (Phase-013 stores) | runs, events, findings, signals, theme pulses, data-quality, audit — see `docs/OPERATOR_GUIDE_013.md` |
| `schedule_state_store.jsonl` | one schedule-state snapshot per tick / operator control (append-style journal) |
| `alert_store.jsonl` | the alert inbox (append-only; one line per alert, never edited) |
| `alert_ack_store.jsonl` | acknowledgment records referencing alert ids (a NEW record per acknowledgment) |

Every store is local JSONL, append-only, deterministic, and free of secrets and scores — the
same Phase-013 discipline, extended to the schedule and the inbox.
