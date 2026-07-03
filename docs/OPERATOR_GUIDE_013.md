# Operator Guide — Manual Pulse Production Workflow (Phase 013)

How to run the Reality-Mesh **manual pulse** as a **production** workflow: one on-demand pulse,
persisted into local append-only stores, verified by a deterministic replay, gated by the
production Data-Quality gates, and summarized on the observability surface. Phase 013 changes
**nothing** about what a pulse concludes — it makes the run **durable, replayable, and auditable**.

Everything here is **manual / on-demand, offline, and evidence-only**: a human triggers ONE pulse,
it reads bundled fixtures once, persists what it did, proves it can replay, and stops. There is
**no scheduler, no daemon, no streaming, no live feed, no broker, no order, no score** — see
section 7 for exactly what is deferred or forbidden, and what would unlock each item.

Governance: `architecture/SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md`,
`architecture/RUNTIME_CONTRACT_013.md`, `architecture/PERSISTENCE_REPLAY_CONTRACT_013.md`,
`architecture/OBSERVABILITY_CONTRACT_013.md`, `architecture/DATA_QUALITY_GATE_CONTRACT_013.md`,
`architecture/SECURITY_POLICY_CONTRACT_013.md`, `architecture/TEST_MATRIX_013.md`.

Generated HTML and `pulse_summary.json` are build **artifacts** — do not commit them. The
persisted JSONL stores under `--persist-dir` are **local operator data** — keep them out of Git
too (write them somewhere like `generated/` or a directory of your own).

---

## 1. The command — run a pulse with persistence

Run from the repo root. `--persist-dir` is the Phase-013 opt-in: without it the CLI behaves
exactly as in Phase 012 (byte-identical output, nothing persisted).

```bash
PYTHONPATH=src python3 -m cosmosiq_pulse \
  --watchlist IREN,AAOI,AMBA,OUST \
  --themes physical-ai,robotics,ai-power \
  --out generated/cosmosiq_pulse \
  --persist-dir generated/pulse_store
```

`cosmosiq_pulse` is the approved (English-named) entry point. The legacy `python3 -m tattva_pulse`
invocation remains a working **deprecated alias** with byte-identical output; use `cosmosiq_pulse`
in all new runbooks.

- `--watchlist` — **REQUIRED**, comma-separated tickers (normalised: strip / upper / dedupe).
  Empty is rejected and nothing is produced.
- `--themes` — **REQUIRED**, comma-separated themes (normalised: strip / lower / dedupe). Empty is
  rejected.
- `--out` — output directory for the generated evidence pages + `pulse_summary.json` (a build
  artifact).
- `--persist-dir` — **OPT-IN** (default OFF): also persist this run into append-only JSONL stores
  under this local directory, verify it replays deterministically, and render the
  run-observability panel into the Trust & Data Quality page. Local files only — no network, no
  scheduler, no broker.
- `--run-id` — optional stable run id for `--persist-dir` (default: derived deterministically from
  the watchlist + themes). Stores are append-only, so re-persisting the same run id into the same
  store dir appends **new** history — use a fresh run id per persisted run.
- `--fixture-dir` — optional override for the bundled pulse fixture directory. There is **no live
  / network source**: pulses are FIXTURE-backed, OFFLINE JSON only.

On start the CLI prints the honest banner:

```
manual pulse · on demand · not scheduled · not broker-connected · fixture-backed · data may be incomplete
```

On success, with `--persist-dir`, the report ends with the persistence proof:

```
run persisted · replayable (deterministic_match: True)
  run_id: pulse-…  · stores (append-only JSONL): generated/pulse_store
```

If `deterministic_match` ever reads `False`, treat the run as a **failure** — see section 4.

---

## 2. What gets persisted (the append-only stores)

Under `--persist-dir` the run lands in plain local JSONL logs — one JSON record per line, ordered,
git-diffable, no database and no server:

| File | Store | What it holds |
|------|-------|---------------|
| `run_store.jsonl` | RunStore | the spine: one `PulseRun` per manual pulse (watchlist, themes, volume counts, `trigger_type: manual`) |
| `event_store.jsonl` | EventStore | the `RealityEvent`s the agents saw (the run's inputs) |
| `finding_store.jsonl` | FindingStore | each sensor agent's in-discipline `AgentFinding`s |
| `signal_store.jsonl` | SignalStore | the fused `RealitySignal`s |
| `theme_pulse_store.jsonl` | ThemePulseStore | the `ThemePulse` states (a STATE, never a recommendation) |
| `data_quality_store.jsonl` | DataQualityStore | per-run Data-Quality diagnostics + the gate verdicts (section 5) |
| `agent_run_ledger.jsonl` | AgentRunLedger | one `AgentRunResult` per sensor agent per run (status, gaps, errors) |
| `audit_store.jsonl` | AuditStore | the audit trail: provenance + **correction** records |

Rules baked into the stores (they are enforced at write time, not by convention):

- **Append-only.** A store exposes append / read / query and nothing that mutates history. A
  historical record, once written, is never edited or removed. **A correction is a NEW record** —
  an `AuditStore` entry whose `corrects` field references the superseded record id. The original
  line stays byte-unchanged forever.
- **Every record is keyed for replay.** Each line carries an envelope with `run_id`, a stable
  `record_id`, a `timestamp`, and a `schema_version` around the typed payload.
- **No secret ever persists.** `append` deep-scans every record and refuses any credential-like
  key (`api_key`, `token`, `password`, `secret`, …).
- **No score / rank / trade field ever persists.** `append` likewise refuses any key carrying a
  trade-decision or scoring token. Stores hold labels + volume counts, never a metric.
- **Deterministic.** Sorted-key JSON with injected timestamps: the same input and the same
  injected time produce byte-identical JSONL.

---

## 3. How to replay a run

Replay answers, from the stored records alone: *"why did the system say X — and is that answer
reproducible?"* The `ReplayHarness` **reads** the stores (never writes), re-computes signal fusion
and theme-pulse synthesis with the run's own recorded time, and compares the recompute
**field-by-field** against what was persisted.

```python
# PYTHONPATH=src python3 — manual, on-demand; reads only, never mutates the stores.
from reality_mesh import (ReplayHarness, ReplayRequest, EventStore, FindingStore,
                          SignalStore, ThemePulseStore, RunStore)

store_dir = "generated/pulse_store"
harness = ReplayHarness(EventStore(store_dir), FindingStore(store_dir),
                        SignalStore(store_dir), ThemePulseStore(store_dir),
                        RunStore(store_dir))
result = harness.replay(ReplayRequest(run_id="pulse-…"))
print(result.deterministic_match, result.differences)
```

- A `ReplayRequest` must be scoped by at least one of `run_id` / `ticker` / `theme` /
  `time_window`; an unscoped replay is rejected.
- **`deterministic_match=True`** means the recompute reproduced every persisted output exactly:
  same inputs + same schema + same code ⇒ same outputs.
- **A divergence is a surfaced FAILURE, never a silent pass.** If anything differs —
  non-determinism leaked in, or the stored history was tampered with — `deterministic_match` is
  `False` and every divergence is named in `differences` (run, record, field, persisted vs
  recomputed value). The replayability gate (section 5) then fails, and the run's outputs must not
  be treated as trustworthy until the divergence is explained.
- Conflicts, data gaps, source / evidence refs, and forbidden downstream uses flow through the
  recompute unchanged — nothing is averaged, dropped, or upgraded on replay.
- Replay never writes: the store files are byte-identical before and after any replay.

The pulse CLI already runs one verification replay per persisted run (that is the
`deterministic_match: True` line in its report), so an operator only reaches for the harness
directly when investigating a run after the fact.

---

## 4. Reading health and the observability panel

With `--persist-dir`, the Trust & Data Quality page (`data_quality.html` under `--out`) carries a
**"Run observability — persisted pulse"** panel alongside the Phase-012 reality-signal evidence
panel. It shows, as labels and volume counts only:

- **Run metadata** — run id, mode, `manual pulse · not scheduled` trigger, started/completed
  timestamps, volume counts (events / findings / signals / theme pulses created), schema and
  runtime versions.
- **Run health** (`RunHealthSummary`) — agents run / failed / blocked / skipped, sources used /
  failed, data-gap and conflict counts, and an honest overall status: `healthy`, `degraded`,
  `failed`, or `blocked_by_policy`.
- **Agent health** (`AgentHealthRecord` per agent) — last status, failure count (a volume, not a
  score), last error note (secret-free), degraded reason.
- **Source health** (`SourceHealthRecord` per source) — last status, credentials status (a
  **presence label only** — `present` / `missing` / `unknown`, never a credential value),
  rate-limit status, unavailable reason.
- **Data-quality gate results** — the per-category verdicts from section 5.
- **Replay metadata** — `replayable · deterministic_match: True/False` plus the difference count.

**Failure isolation** is the point of this surface. One failed agent or source never crashes a
run: the failure becomes a health record plus an explicit data gap, and the remaining agents still
run. A degraded / partial run **still renders honestly** — it produces a `RunHealthSummary` and a
`DataQualityRunSummary` labelled `degraded`, with the failed agent and its reason visible on the
panel. Nothing is hidden, nothing is fabricated, and a failed real/pulse run is never silently
"completed" with demo data. A gap means "no source yet" — the correct response is to add a source,
never to trust a fabricated value.

---

## 5. The production Data-Quality gates

Every persisted run is checked by the `DataQualityGateRunner` — it **reads** the persisted records
and reports `pass` / `warn` / `fail` per category; it never mutates, fetches, or decides a trade.
The eleven categories:

```
source_authority   freshness   conflict   data_gap   social_weak_signal
manual_analyst_authority   security_secrets   scheduler_broker_trading_guardrail
demo_fallback   schema_validation   replayability
```

A **warning** annotates (e.g. "some inputs honestly labelled stale", "uncorroborated social
records — weak by design"). A **hard failure** blocks the run's outputs from being treated as
trustworthy; the run still renders its Data Quality honestly, marked failed. The required hard
failures — these always FAIL, never warn:

- an X/social record carrying `verified_fact` (a rumor may never become a verified fact);
- a manual / analyst value marked `canonical`;
- a hidden `score` / `rank` / `investability` field on any record;
- a `buy` / `sell` / `order` / `submit` field or affordance;
- an API key / secret token in a generated output;
- a network call at module import;
- a real/pulse run whose data silently equals the demo data (silent demo fallback);
- a value presented with NO source / evidence ref (missing data filled without a source);
- a scheduler / daemon / broker / order token in module source.

The gate verdicts are appended to the `DataQualityStore` per run, and the run's overall status is
the **worst** gate result on the `healthy < degraded < failed < blocked_by_policy` ladder — a
policy / security failure rolls to `blocked_by_policy` (the outputs are refused). A normal
fixture pulse reads `degraded`, not `healthy`: it honestly carries weak social signals, and the
gate surfaces that rather than hiding it.

---

## 6. A worked production run, end to end

1. Run the section-1 command. Read the banner and the final report: agent statuses, theme-pulse
   states, data gaps, and the `deterministic_match: True` persistence line.
2. Open `universe.html` → **Trust & Data Quality**. Check the reality-signal evidence panel
   (weak/social marked WEAK, conflicts both-sided, gaps visible) and the run-observability panel
   (run health, agent/source health, gate results, replay metadata).
3. If anything is `degraded` / `failed` / `blocked_by_policy`: the panel names the agent, source,
   or gate and the reason. That is information, not something to suppress — fix the source or the
   input, then run a **new** pulse with a **fresh run id**.
4. To correct a bad record later: never edit a JSONL line. Append an `AuditStore` correction
   record referencing the superseded record id (`AuditStore.append_correction`). History stays
   intact; the correction is itself a record.
5. To audit an old run: use the section-3 replay. `deterministic_match: False` on previously-good
   history means the store bytes changed or non-determinism leaked — investigate before trusting
   anything derived from that run.

---

## 7. What this workflow does NOT do

Explicitly deferred or forbidden. Each item names what would unlock it — nothing on this list is
enabled quietly.

- **No scheduler, no daemon, no background job, no streaming, no always-on / real-time refresh, no
  alerting loop.** A human runs one pulse. A scheduled pulse is **deferred to Phase 015**, only
  after Phases 013 + 014 are accepted, and **requires a new ADR** with explicit approval. It is
  not reconsidered before then.
- **No execution beyond manual preview.** Execution today is **manual execution preview only**
  (`broker_order_id` always `None`; no order placement, routing, or recording anywhere). Any
  execution expansion — broker-connected read-only portfolio, order-ticket generation, execution
  simulation — is **deferred to Phase 020+ and is approval-gated**: separate explicit approval
  plus a new ADR, per the SPEC-013 §D roadmap. Auto-buy, auto-sell, broker execution, and
  portfolio auto-rebalancing are **forbidden unless separately approved** — no automation, ever,
  without that approval.
- **No live X / social feed, and no network at all.** Pulses are fixture-backed, offline JSON.
  Real source adapters are **Phase 014**, each one local-file-first → mocked → failure-tested →
  Data-Quality-integrated before any production network path; **X/social comes LAST and is
  strictly weak-signal-only** — rumor authority, never a verified fact, never canonical.
- **No broker connection; no buy / sell / order / submit affordance** anywhere in any output,
  page, or store.
- **No investment score, rank, or rating.** Signals and theme pulses are qualitative labels;
  every integer in the runtime records is a volume count. A `ThemePulse` is a state, not a pick.
- **No secrets on disk or in output.** Stores refuse credential-like keys at write time; the
  security gate fails any generated output carrying a key; source credential status is a presence
  label only.
- **No silent demo fallback.** The demo universe stays the default and byte-identical; a pulse
  that lacks coverage shows a gap, never demo data standing in for it.

The downstream layer boundaries remain intact: the pulse stops at Signal Fusion + Opportunity
Discovery **evidence**. A `ThemePulse` is not an Investment Diligence thesis; the Investment
Diligence Layer tests hypotheses (not run by the pulse); the Portfolio Intelligence Layer would
show sizing ranges / guardrails (not orders); and the Execution Preview Layer stays manual
preview only.

---

## 8. Cross references

`architecture/SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` ·
`architecture/RUNTIME_CONTRACT_013.md` · `architecture/PERSISTENCE_REPLAY_CONTRACT_013.md` ·
`architecture/OBSERVABILITY_CONTRACT_013.md` · `architecture/DATA_QUALITY_GATE_CONTRACT_013.md` ·
`architecture/SECURITY_POLICY_CONTRACT_013.md` · `architecture/IMPLEMENTATION_PLAN_013.md` ·
`architecture/TEST_MATRIX_013.md` · `docs/OPERATOR_GUIDE_012.md` (the Phase-012 manual pulse this
workflow hardens).
