# Operator Runbook — Supervised Operator Service (Phase 020C)

The runbook for the **CosmosIQ supervised operator service** (`cosmosiq_service`): a supervised,
always-on-**capable**, **local** operator service that calls the accepted 015B one-tick
orchestrator on a cadence — and **never bypasses** the 013 chain (append-only stores, agent-run
ledger, health roll-ups, data-quality gates, deterministic replay).

This service is **not a cloud daemon**. It runs only because you started it; there is no hosted
process, no broker, and no trading endpoint. Execution stays a **manual preview** (the 017
execution-manual slice) — nothing is ever sent. Everything is **offline and deterministic**: the
pure core reads an injected `now`; only the operator-started loop reads the wall clock.

Governance: `docs/OPERATOR_GUIDE_015.md` (scheduled ticks + alerts) ·
`docs/OPERATOR_GUIDE_016.md` (the app) · `docs/OPERATOR_RUNBOOK_019.md` (day-to-day ops) ·
`architecture/adr/ADR-CANDIDATE-015_SCHEDULED_PULSE_UNLOCK.md`.

---

## 1. What this is (and is not)

- **A single supervised loop.** The one `while` + `time.sleep` loop lives **only** in
  `cosmosiq_service/__main__.py` — the operator-started process. The pure core
  (`cosmosiq_service/service.py`) has no loop, no thread, no socket, and no wall-clock read; it is
  fully unit-tested with an injected `now`.
- **It calls, never replaces, the 015B orchestrator.** Each tick calls
  `reality_mesh.orchestrator.run_due_pulses` for exactly one pass through the full 013 chain.
- **Default OFF.** The service starts in `OFF`. Continuous production operation is **not** the
  default and is **gated** (see §3).

## 2. Install / configure

Requirements: Python 3.9, stdlib only. Run with `PYTHONPATH=src`.

Create a subscriptions file (the tick scope — watchlists/themes → cadence policies). Values are
config references only; **never put a secret in here**:

```json
{
  "subscriptions": [
    {
      "subscription_id": "sub.core",
      "watchlist": ["IREN", "NVDA"],
      "themes": ["physical_ai", "robotics"],
      "policy_ids": ["cadence.news_filings"]
    }
  ],
  "max_runs_per_hour": 60
}
```

The command surface:

```bash
PYTHONPATH=src python3 -m cosmosiq_service <start|stop|status|pause|resume|run-once> \
    --store-dir <persist dir> [--mode off|manual|shadow_24x7|production_24x7] \
    [--subscriptions subs.json] [--now <ISO instant>] [--poll-interval 60] [--max-pulses 1]
```

- `--store-dir` — the append-only 013B/015 store (keep it out of Git, e.g. `generated/pulse_store`).
- `--mode` — default `off`.
- `--now` — injected instant for `pause` / `resume` / `run-once` (defaults to the wall clock).

### launchd example (macOS — attended MANUAL mode only)

```xml
<!-- ~/Library/LaunchAgents/com.cosmosiq.service.plist -->
<plist version="1.0"><dict>
  <key>Label</key><string>com.cosmosiq.service</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string><string>-m</string><string>cosmosiq_service</string>
    <string>start</string>
    <string>--store-dir</string><string>/Users/you/cosmosiq/store</string>
    <string>--mode</string><string>manual</string>
    <string>--subscriptions</string><string>/Users/you/cosmosiq/subs.json</string>
  </array>
  <key>EnvironmentVariables</key><dict><key>PYTHONPATH</key><string>/Users/you/cosmosiq/src</string></dict>
  <key>RunAtLoad</key><false/>            <!-- operator-started, never auto-loaded -->
  <key>KeepAlive</key><false/>
</dict></plist>
```

### generic supervisor (systemd / supervisord)

Point the supervisor at `python3 -m cosmosiq_service start --store-dir ... --mode manual
--subscriptions subs.json`, with `PYTHONPATH=src`, restart policy `on-failure`. The single-instance
lockfile prevents a second copy from running.

## 3. Modes and the default-OFF posture

| Mode | Continuous loop | Notes |
|------|-----------------|-------|
| `OFF` (default) | runs nothing | the safe posture; `run-once` is a no-op |
| `MANUAL` | **allowed** (attended) | operator-attended supervised loop; single ticks via `run-once` |
| `SHADOW_24X7` | **REFUSED** | continuous shadow operation is **gated to Phase-020D** |
| `PRODUCTION_24X7` | **REFUSED** | continuous production operation is **gated to Phase-020F** |

In Phase 020C the *machinery + safe defaults* ship, not the shadow/production continuous run. A
single `run-once` tick is permitted in any non-OFF mode (to exercise the machinery), but the
**continuous loop** refuses to start in `SHADOW_24X7` / `PRODUCTION_24X7` and prints the gate it
requires.

## 4. start / stop / status / pause / resume / run-once

```bash
# one supervised tick, then exit (exercises the full 013 chain)
PYTHONPATH=src python3 -m cosmosiq_service run-once --store-dir store --mode manual \
    --subscriptions subs.json --now 2026-06-29T15:00:00Z

# the attended supervised loop (MANUAL only; Ctrl-C to stop)
PYTHONPATH=src python3 -m cosmosiq_service start --store-dir store --mode manual \
    --subscriptions subs.json --poll-interval 60

# print the sanitized health snapshot
PYTHONPATH=src python3 -m cosmosiq_service status --store-dir store --mode manual

# pause (ticks then run nothing) / resume (backoff still holds)
PYTHONPATH=src python3 -m cosmosiq_service pause  --store-dir store --now 2026-06-29T15:00:00Z
PYTHONPATH=src python3 -m cosmosiq_service resume --store-dir store --now 2026-06-29T15:05:00Z

# release a crashed loop's lockfile
PYTHONPATH=src python3 -m cosmosiq_service stop --store-dir store
```

`pause` journals `paused_all` on the schedule (append-only); a paused service's `run_once` runs
nothing until `resume`. `resume` lifts only the pause — an unexpired per-policy failure backoff
still holds.

## 5. Health file schema (`<store-dir>/service_health.json`)

Sanitized JSON, overwritten each tick. Fields:

| Field | Meaning |
|-------|---------|
| `service_mode` | `off` / `manual` / `shadow_24x7` / `production_24x7` |
| `is_running` | true while the supervised loop is attached |
| `is_paused` | true when `paused_all` is journaled |
| `pid` | the pid holding the lock (0 if none) |
| `lock_status` | `free` / `held` / `stale_reclaimed` |
| `last_tick_started_at` / `last_tick_completed_at` / `last_tick_failed_at` | injected instants |
| `last_successful_run_id` / `last_failed_run_id` | 015B run ids |
| `consecutive_failures` | volume count; drives backoff + the circuit |
| `last_error_class` | e.g. `ScheduledPulseFailure` (no secret) |
| `last_error_message_sanitized` | scrubbed of secret shapes |
| `next_scheduled_tick_at` | earliest cadence boundary hint |
| `next_retry_at` | deterministic backoff instant (`""` when clear) |
| `source_health_summary` / `agent_health_summary` / `dq_status_summary` | per-run count roll-ups |
| `updated_at` | when the snapshot was written |

## 6. Structured log format (`<store-dir>/service_log.jsonl`)

One **JSON object per line** (append-only), each with at least `ts`, `level`, `event`,
`service_mode`, and a sanitized `message`. Events: `tick.success`, `tick.failed`, `tick.idle`,
`tick.off`, `tick.paused`, `tick.backoff`, `tick.lock_held`, `service.paused`, `service.resumed`.
A failure line also carries `error_class`, `consecutive_failures`, `backoff_seconds`,
`next_retry_at`, and `circuit_open`. **No secret is ever written** — every string passes through
the sanitizer (`api_key=…`/`token=…`/`sk-…`/`AKIA…`/long opaque blobs → `<redacted>`).

## 7. Failure / backoff behavior

A failed pulse is recorded honestly (it lands in the ledger + a `source_failure` DQ record via the
015B tick) and:

1. increments `consecutive_failures`;
2. sets `last_error_class` / `last_error_message_sanitized` (sanitized) / `last_tick_failed_at`;
3. applies deterministic service backoff: `base_backoff_seconds * multiplier**(failures-1)`,
   capped at `max_backoff_seconds` → `next_retry_at`;
4. at `consecutive_failures >= max_consecutive_failures` the log marks `circuit_open`.

A tick within the backoff window is skipped **without** counting a new failure. There is **no
fixture fall-back** and the append-only stores are never corrupted.

## 8. Crash recovery + stale lock

The single-instance lockfile (`<store-dir>/service.lock`, carrying `pid` + `acquired_at`) refuses a
second concurrent service. If the loop crashes and leaves a lockfile:

- a lock older than `lock_stale_seconds` (default 1h) is **automatically reclaimed** on the next
  `start` / `run-once`;
- or clear it explicitly with `cosmosiq_service stop --store-dir <dir>`.

## 9. Rollback procedure

Roll back through the modes, most-cautious last:

```
PRODUCTION_24X7  →  SHADOW_24X7  →  MANUAL  →  OFF
```

1. **PRODUCTION_24X7 → SHADOW_24X7** — stop the loop; restart with `--mode shadow_24x7` (once its
   020D gate exists). Observation only.
2. **SHADOW_24X7 → MANUAL** — stop the loop; restart with `--mode manual` for attended single ticks.
3. **MANUAL → OFF** — `pause` to stop ticks immediately, then stop the process and restart (or
   leave stopped) with `--mode off`. `OFF` runs nothing.

Rollback is always safe: the stores are append-only, the schedule state is journaled, and no mode
sends an order.

## 10. Still forbidden

- No broker, no order routing, no trading endpoint — execution stays a manual preview (017).
- No network on import; no continuous production/shadow operation without the 020F/020D gates.
- No secret in the log, health file, or console output.
- The core never reads the wall clock and never loops; the loop lives only in the operator-started
  `__main__` process.
- No bypass of the DQ gates, replay, or the append-only persistence — every tick goes through
  `run_due_pulses`.
