# Operator Guide — Economic Universe (Phase 011)

How to run the Sudarshan Economic Universe research surface. It is a **manual, on-demand,
read-only research tool**. It is **not** scheduled, **not** real-time, **not** broker-connected,
and it places **no orders**. Missing data is expected and is shown as visible gaps — never
fabricated. Governance: `architecture/SPEC-011_END_TO_END_DILIGENCE_RESEARCH_MVP.md`,
`architecture/ARCHITECTURE_CONTRACT_011.md`.

Generated HTML is a build **artifact** — do not commit it. Open `universe.html` in a browser.

---

## 1. Commands

All commands run from the repo root. Output goes to `--out` (default `generated/universe_ui`).

### Demo (default) — hand-authored universe, no data fetch
```bash
PYTHONPATH=src python3 -m universe_ui --out generated/universe_ui
```
The default surface. A curated multi-galaxy demo terrain. No network, no credentials. Labelled
`fixture/demo` on every page.

### Evidence-ingested fixture — REAL sparse terrain from the accepted IREN slice
```bash
PYTHONPATH=src python3 -m universe_ui --mode evidence_ingested_fixture --out generated/evidence_ui
```
Builds a sparse `UniverseTerrain` from the accepted 009G IREN evidence-alpha slice (SEC/FMP/
yfinance **fixtures**, no network). Mode `evidence_ingested_fixture`. Honestly incomplete.

### Real, on-demand, single ticker
```bash
export SEC_USER_AGENT="Your Name your.email@example.com"   # REQUIRED (SEC rule)
export FMP_API_KEY="…"                                     # OPTIONAL (convenience source)
PYTHONPATH=src python3 -m universe_ui --mode real_evidence_on_demand --ticker IREN --out generated/real_iren_ui
```
Fetches **real current** SEC (canonical) + FMP (convenience, if a key is set) data for one ticker
**at the moment you run it**. Manual refresh only.

### Real, on-demand, watchlist (≤ 10 tickers)
```bash
PYTHONPATH=src python3 -m universe_ui --mode real_evidence_on_demand --tickers IREN,AAOI,INOD --out generated/real_watchlist_ui
```
One merged sparse terrain of multiple real company planets, grouped by inferred theme; a company
whose theme can't be inferred lands in an explicit **"Unclassified / needs theme inference"**
region. Tickers are normalised (strip / upper / dedupe).

### Optional flags (real mode)
- `--enrich` — **diligence enrichment** (011C): overlay market cap + financials from each ticker's
  already-fetched SEC/FMP payloads onto the CompanyNode / Data Quality / cockpit, **source-backed
  only**. See §3.
- `--enable-yfinance` — opt in to the yfinance **fallback** (research-only). Off by default;
  yfinance history is currently **deferred** (see §5).

---

## 2. Modes at a glance

| Mode | Data | Network | Credentials | Terrain |
|------|------|---------|-------------|---------|
| `demo` (default) | hand-authored | none | none | full curated demo universe |
| `evidence_ingested_fixture` | IREN fixtures | none | none | sparse, real-shaped, honest gaps |
| `real_evidence_on_demand` (default / unenriched) | real SEC/FMP now | on the explicit run only | `SEC_USER_AGENT` req. | sparse; market cap etc. shown as gaps |
| `real_evidence_on_demand --enrich` | real SEC/FMP now | on the explicit run only | `SEC_USER_AGENT` req. | sparse; market cap / financials **source-backed**; unsupported areas still gaps |

Demo is always the default. Real mode never silently falls back to demo data — a missing source or
credential shows as a **visible Data-Quality gap**, not a demo substitute.

---

## 3. Default real vs enriched real

**Default real (`--enrich` off)** — honest and sparse. Market cap, TAM, value-chain layers,
bottleneck severity, company IR, and leadership are shown as **visible gaps** (dashed/neutral
bodies + "add … source" data actions). Backward-compatible with the pre-enrichment build.

**Enriched real (`--enrich`)** — the system builds a diligence-enrichment bundle **from each
ticker's already-fetched SEC/FMP payloads** (no new fetch) and overlays it:
- **CompanyNode** size becomes market-cap-derived economic magnitude (FMP convenience), un-dashed;
  shares / revenue / net income (SEC **canonical**) and margins (FMP, marked **inferred**) appear
  as authority-stamped company evidence.
- **Data Quality** gains a per-ticker **enrichment-coverage** panel (available/missing + authority
  + data-sourcing actions).
- **Cockpit** gains a **read-only** enrichment status note (no trade action; broker order: none).
- **Unsupported** TAM / value-chain / bottleneck / company-IR / leadership **stay gaps** — enrichment
  is source-backed only and fabricates nothing. A manual TAM (if supplied) sizes a theme but stays
  authority **manual**, never canonical.

Neither path ranks companies, computes an investability score, or emits buy/sell/hold. Size = economic
magnitude only; it is not a ranking.

---

## 4. Credentials & security

- `SEC_USER_AGENT` is **required** for real mode (SEC's fair-access rule). Use a real name + contact.
  It is read only by `runtime/live_evidence_run.py`, never printed, never embedded in HTML.
- `FMP_API_KEY` is **optional**. Without it, FMP fields show as a `credentials_missing` gap and the
  run degrades gracefully (SEC can still succeed).
- Keys are never printed (the CLI logs only presence booleans) and never appear in any generated page.
- Real network happens **only** when you explicitly run `--mode real_evidence_on_demand`. There is no
  network on import, no scheduled fetch, and no background job.

---

## 5. Source authority & deferred sources

Authority (higher wins for the same metric/period/unit; enforced by `evidence_ingestion/conflict.py`):

```
SEC / data.sec.gov  = CANONICAL (filings & facts)
Company IR          = PRIMARY   (a company_claim, not auto-verified)
FMP                 = CONVENIENCE
yfinance            = FALLBACK / research-only
manual / analyst    = MANUAL    (never canonical)
```

**Real transports today**: SEC submissions + companyfacts (real), FMP profile/income/OHLCV (real).
**Deferred**: yfinance history (a narrow interface exists but real history fetching is deferred — off
by default and shown as an explicit gap when relevant); company-IR / investor-presentation / transcript
ingestion; TAM / supplier-of-supplier / leadership datasets. These remain **known gaps** with
data-sourcing actions.

---

## 6. Reading the Data Quality dashboard

- **Source pipeline & authority matrix** — SEC canonical → FMP convenience → yfinance fallback →
  manual/other; per-source status: `fetched` / `unavailable` / `credentials_missing` / `failed` /
  `deferred`.
- **Watchlist run summary** — requested / built / failed / deferred; summed canonical/convenience/
  fallback counts; conflicts; overridden facts.
- **Diagnostics (010F)** — per-ticker **trust** + **completeness** **labels** (sufficient / partial /
  weak / missing / conflicted / stale / credentials_missing / source_failed / needs_human_review) and
  theme-classification status (direct / weak / fallback / missing). These are **labels, not scores**.
- **Enrichment coverage (`--enrich`)** — per area (market cap / TAM / value-chain / bottleneck / IR /
  leadership): available vs missing, source authority, and a **data-sourcing action** (e.g. "add an
  investor-presentation source", "add a TAM / revenue-pool source"). These are **data actions, never
  trade recommendations**.

Interpretation: a **gap** means the pipeline has no source for that field yet — it is not zero and not
inferred. The correct response is to add the suggested source, not to trust a fabricated value. Sparse
terrain is expected for real tickers until more diligence sources are wired.

---

## 7. What this tool does NOT do

- No scheduler, background jobs, automated refresh, or automated trading.
- No broker connection, order placement/routing/recording; **no buy/sell/order/submit** anywhere.
- No investment ranking / score; Kriya produces a **manual execution preview** only
  (`broker_order_id` is always `None`); Saarathi shows **sizing ranges/guardrails**, not orders.
- No web scraping, OCR, or arbitrary-internet fetch. No secrets in output.

---

## 8. Fixture vs mocked vs real (for developers)

- **Fixture**: `evidence_ingested_fixture` mode + the tests use local JSON fixtures under
  `tests/fixtures/` — no network.
- **Mocked**: the test suite injects mock transports (`transports` / `transports_by_ticker`) and a
  fixed `now`; the entire suite runs **offline** under a socket kill-switch.
- **Real**: only `--mode real_evidence_on_demand` on an explicit run fetches live SEC/FMP.

## 9. Cross references
`architecture/SPEC-011_END_TO_END_DILIGENCE_RESEARCH_MVP.md` · `ARCHITECTURE_CONTRACT_011.md` ·
`GATE-011_BUILD_ACCEPTANCE_CHECKLIST.md` · `TEST_MATRIX_011.md` ·
`adr/ADR-CANDIDATE-011_DILIGENCE_ENRICHMENT_AS_EVIDENCE_LAYER.md` · `IMPLEMENTATION_PLAN_011.md`.
