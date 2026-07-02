# Operator Guide — Manual Reality Pulse (Phase 012)

How to run the Reality-Mesh **manual pulse** — the Phase 012 Real-Time Reality Intelligence Sensor
Mesh, operated **on demand by a human**. Despite the phase title, this is **manual / on-demand
pulse mode**: you trigger ONE pulse, it reads bundled fixtures once and reasons over them, and it
stops. It is **not** always-on, **not** real-time, **not** streaming, **not** scheduled, has **no
daemon / background job**, is **not** broker-connected, and places **no orders**. Missing data is
expected and is shown as **visible gaps** — never fabricated, and never a silent fall-back to the
demo universe.

Governance: `architecture/SPEC-012_REAL_TIME_REALITY_INTELLIGENCE_SENSOR_MESH.md`,
`architecture/ARCHITECTURE_CONTRACT_012.md` (§G manual/on-demand, §H runtime/security),
`architecture/TEST_MATRIX_012.md`.

Generated HTML and `pulse_summary.json` are build **artifacts** — do not commit them.

---

## 1. The command

Run from the repo root. Output goes to `--out` (default `generated/tattva_pulse`).

```bash
PYTHONPATH=src python3 -m tattva_pulse \
  --watchlist IREN,AAOI,AMBA,OUST \
  --themes physical-ai,robotics,ai-power \
  --out generated/tattva_pulse
```

- `--watchlist` — **REQUIRED**, comma-separated tickers (normalised: strip / upper / dedupe).
  An empty watchlist is **rejected** and nothing is produced — exactly as real mode requires a
  ticker.
- `--themes` — **REQUIRED**, comma-separated themes (normalised: strip / lower / dedupe). An empty
  themes list is **rejected**.
- `--out` — output directory (a build artifact).
- `--fixture-dir` — optional override for the bundled pulse fixture directory. There is **no live
  / network source**: pulses are FIXTURE-backed, OFFLINE JSON only.

On start the CLI prints the honest banner:

```
manual pulse · on demand · not scheduled · not broker-connected · fixture-backed · data may be incomplete
```

There is **no X / social live feed and no network**. If a live X or other real transport is ever
wired later, it stays behind an explicit flag through a single lazily-imported boundary and is
never exercised by the test suite.

---

## 2. What a pulse does (the chain)

One pulse runs the full sensor chain, deterministically and offline:

```
fixtures (RealityEvents)
   → Tattva sensor agents (run_checked, discipline-bounded)
        market regime · sector rotation · theme rotation · news/filings · X/social narrative
   → Buddhi routing (HandoffEnvelope per finding)
   → Tattva Signal Fusion  → RealitySignals + SignalClusters
   → Sphurana Theme Pulse   → ThemePulses
   → Data-Quality roll-up   → signals/pulses + honest gaps
```

Every agent emits qualitative **labels** only (direction / magnitude / urgency / confidence /
freshness / corroboration / contradiction). **No numeric investability score, rank, or rating**
appears anywhere; **no buy / sell / hold / order / broker** field exists on any output.

The produced signals and theme pulses are rendered into the Economic Universe **Data-Quality page**
as **evidence** (the 012J panel), and a machine-readable `pulse_summary.json` (labels / gaps /
provenance — no scores) is written alongside the pages.

---

## 3. Outputs

Under `--out`:

| File | What it is |
|------|------------|
| `universe.html`, `dashboard.html`, `data_quality.html`, `cockpit.html` | the Economic Universe pages (demo terrain). **Data Quality** carries the manual-pulse reality-signal evidence panel. |
| `pulse_summary.json` | machine-readable pulse summary: watchlist / themes, per-agent run status, signal labels + provenance, theme-pulse states, and the consolidated data gaps. **Labels only — no scores.** |
| `assets/…` | local CSS / JS / SVG (no network). |

The pulse pages are **explicitly a pulse-mode overlay on the demo terrain**. The demo default is
unchanged: running `universe_ui` with no pulse arguments is byte-identical to before. There is
**no silent fall-back** — if a requested ticker or theme has no coverage you get a gap, not demo
data standing in for it.

---

## 4. Reading signal quality + gaps

On the Data-Quality page and in `pulse_summary.json`:

- **Signal coverage** — per discipline: `direction`, `freshness` (stale is flagged, never dropped),
  **source authority**, `confidence`, and a gap count. Authority is a fusion sidecar because a
  `RealitySignal` has no authority field; when unknown it renders as `unknown` — a visible gap,
  never fabricated.
- **Weak / social signals** — X/social signals are **clearly marked WEAK / uncorroborated**. X/
  social is **narrative only**: it is `rumor` authority and is **never** promoted to a verified
  fact. A rumor stays a rumor even when a non-social source agrees (corroboration can lift the
  corroboration status, never the authority).
- **Conflicting signals** — contradictions are shown with **both sides preserved**, never averaged
  into a bland middle.
- **Theme pulse status** — a `ThemePulse` is a **STATE** (`Dormant … Broadening … Crowded …
  Data insufficient`), **not** a trade recommendation, price target, or stock pick. A social-only
  theme reads `Data insufficient`; a narrow one-name move never reads `Broadening`.
- **Pulse data gaps** — a requested watchlist ticker or theme with **no fixture coverage** is an
  explicit gap (e.g. `no fixture coverage for theme 'ai-power'`). Missing inputs (e.g. a missing
  institutional-flow proxy) stay visible. A gap means "no source yet" — not zero, not inferred.
  The correct response is to add a source, never to trust a fabricated value.

---

## 5. What this tool does NOT do

- **No scheduler, no daemon, no background job, no streaming, no always-on / real-time refresh, no
  automated trading.** A human runs one pulse; continuous mode would require separate approval and
  a new ADR.
- **No live X / social feed, no network.** Fixture / mock only.
- **No broker connection; no order placement / routing / recording; no buy / sell / order / submit
  affordance** anywhere in the output.
- **No investment ranking / score / rank / rating.** The mesh emits reality **evidence** only.
- **No secrets in output.** No API keys in HTML, JSON, or logs.

The downstream layer boundaries remain **intact**: a `ThemePulse` is not a Nivesha investment
thesis; **Nivesha** tests hypotheses (it is not run by the pulse), **Saarathi** would show sizing
ranges / guardrails (not orders), and **Kriya** is manual execution **preview** only
(`broker_order_id` always `None`). The pulse stops at Tattva-fusion + Sphurana evidence.

---

## 6. Fixture vs mocked vs real (for developers)

- **Fixture**: the pulse reads bundled JSON under `tests/fixtures/reality_mesh/pulse/` (override
  with `--fixture-dir`). No network.
- **Mocked / offline**: the whole test suite (`tests/test_reality_mesh_e2e.py`) runs **offline**
  under a socket kill-switch, with an injected `now` for determinism.
- **Real**: no real transport is wired for the pulse in Phase 012. Any future real source stays
  behind an explicit flag through a single lazily-imported boundary and is never exercised in
  tests.

---

## 7. Cross references

`architecture/SPEC-012_REAL_TIME_REALITY_INTELLIGENCE_SENSOR_MESH.md` ·
`architecture/ARCHITECTURE_CONTRACT_012.md` · `architecture/HANDOFF_CONTRACT_012.md` ·
`architecture/AGENT_MAP_012.md` · `architecture/TEST_MATRIX_012.md` ·
`docs/OPERATOR_GUIDE_011.md` (the accepted 011 research surface this pulse renders into).
