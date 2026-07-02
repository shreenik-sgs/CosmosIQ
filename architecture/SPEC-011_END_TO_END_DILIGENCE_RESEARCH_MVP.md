# SPEC-011 — End-to-End Diligence Research MVP

Status: **Draft for architect review** · Phase: 011 · Depends on: 010 (complete), 011A (accepted)
Type: design-guidance specification (architecture/, not generated `specification/`)

> This document governs the remainder of Phase 011. It changes no runtime behaviour. It is
> the contract the 011B–011F build slices must conform to. Companion documents:
> `ARCHITECTURE_CONTRACT_011.md` (invariants), `GATE-011_BUILD_ACCEPTANCE_CHECKLIST.md`
> (pass/fail gate), `TEST_MATRIX_011.md` (required tests),
> `adr/ADR-CANDIDATE-011_DILIGENCE_ENRICHMENT_AS_EVIDENCE_LAYER.md`,
> `IMPLEMENTATION_PLAN_011.md` (sub-milestones).

## 1. Purpose

Deliver a **manual, on-demand, evidence-grounded diligence research MVP**: a human operator
requests one or a small watchlist of tickers, the system fetches real evidence (SEC canonical,
FMP convenience, yfinance fallback) on demand, runs the accepted cognition→diligence chain as far
as the evidence honestly supports, enriches the sparse diligence inputs from disciplined sources,
and renders the result as an Economic Universe (terrain), a CIO dashboard, a company cockpit, and
a Data-Quality/diagnostics surface — **with missing data always visible and no automated action**.

011 is about **input quality, completeness, provenance, and trust** — not about new alpha scoring.

## 2. Scope

- Diligence **input enrichment** (market cap / EV, TAM / revenue pool, value-chain layers,
  supplier/customer/supplier-of-supplier, bottleneck severity/duration/capacity, company IR /
  investor presentations / transcripts, leadership evidence) as an **evidence layer** with explicit
  source authority, claim status, provenance, and data gaps.
- Mapping enrichment + pipeline outputs into the `UniverseTerrain` and into **Nivesha-ready**
  diligence inputs.
- Data-Quality integration: enrichment coverage, per-area authority, per-ticker gaps, and
  data-sourcing actions.
- Company cockpit continues to render via the **accepted** `render_cockpit_html`.
- Operator CLI workflow for demo / evidence-ingested-fixture / real-on-demand (single + watchlist).

## 3. Non-goals (explicitly out of scope for all of 011)

- No scheduler, background jobs, automated refresh, or automated trading.
- No broker automation, order placement, or buy/sell/hold/order/submit affordance.
- No new investment scoring, alpha ranking, master score, or hidden ranking.
- No web scraping, OCR, arbitrary-internet fetch, or user-PDF ingestion (unless a safe local
  fixture already exists).
- No change to the accepted UI layout or visual language beyond what is strictly needed to display
  diagnostics/evidence correctly.
- No weakening of the source-authority hierarchy or the conflict-resolution rules.
- No change to Tattva / Sphurana / Nivesha / Saarathi / Kriya reasoning logic beyond wiring inputs.

## 4. Current accepted foundation

- **010A–010G** — Economic Universe UI: single zoomable two-pane telescope hero + below-fold
  intelligence pane; the `UniverseTerrain` metadata model (010B) as source of truth; the
  evidence-ingested fixture terrain (010C); the on-demand real loader behind an explicit manual
  mode (010D); multi-ticker watchlist merge (010E); label-only data-quality/theme diagnostics
  (010F); and a closed interaction cross-link graph (010G).
- **011A** — Diligence Input Enrichment Foundation (see §14): the `src/diligence_enrichment/`
  package (8 evidence models, source contract, fixture-backed adapters, coverage diagnostic) and
  the optional, byte-identical-when-absent terrain/Data-Quality wiring.
- **Modes**: `demo` (default, hand-authored terrain), `evidence_ingested_fixture` (IREN slice),
  `real_evidence_on_demand` (single `--ticker` / watchlist `--tickers`, real network behind the
  explicit run only).
- **Test baseline**: 680 tests, all offline (socket-safe), deterministic; demo build byte-identical.

## 5. Target end-to-end flow

```
operator (manual, on demand)
  → live_transport (SEC canonical · FMP convenience · yfinance fallback) — lazy, explicit only
  → evidence ingestion: raw → normalized → conflict-resolved (SEC wins) → Observations
  → Tattva IntelligenceAssessment (understanding only; factual ≠ signal)
  → Sphurana OpportunityHypothesis (theme / why-now / why-before-obvious / bottleneck)
  → diligence enrichment (market cap / TAM / value-chain / bottleneck / IR / leadership) — evidence + gaps
  → Nivesha InvestmentThesis (diligence gauntlet; investability / timing / red-team — labels)
  → InvestmentAction (governed candidate)
  → Saarathi PersonalizedAction (portfolio fit + sizing RANGE / guardrails)
  → Kriya ManualExecutionIntent (preview only; explicit user-selected size; no order)
  → UniverseTerrain (mode-labelled; sparse-honest; provenance + data gaps)
  → Economic Universe UI + CIO Dashboard + Company Cockpit + Data Quality / Diagnostics
```

Everything downstream stops at a **manual review preview**. No step places, routes, or records an order.

## 6. Diligence enrichment architecture (011A + forward)

- Package `src/diligence_enrichment/`: `models.py` (evidence models), `source_contract.py`
  (authority + claim status), `adapters.py` / `enrich.py` (fixture-backed mappers →
  `DiligenceEnrichmentBundle`), `coverage.py` (Data-Quality coverage diagnostic).
- Every enrichment datum carries an explicit **authority** and **claim_status**; unsupported
  fields become **data gaps**, never invented values.
- Enrichment is an **overlay**: it populates existing terrain fields (magnitude / size basis /
  value-chain layers / bottleneck severity) via existing helpers; absent → the honest dashed gap.

## 7. Source authority contract (see ARCHITECTURE_CONTRACT_011 §C)

`SEC (canonical for filings/facts) > Company IR (primary; a company_claim, not auto-verified) >
FMP (convenience) > yfinance (fallback/research-only) > manual/analyst/user (never canonical)`.
Lower authority may not override higher authority for the **same metric/period/unit** — enforced by
the existing family-scoped, period-aware `evidence_ingestion/conflict.py`. Reused verbatim by 011.

## 8. Nivesha handoff contract

- Enrichment + terrain provide Nivesha's **diligence inputs** (financials, value-chain/winner
  context, bottleneck exposure, capital-structure/dilution signals, catalysts, red-team evidence)
  with provenance + gaps. Enrichment **does not** compute investability.
- Nivesha returns an `InvestmentThesis` using its **existing** gauntlet (investability assessment,
  timing confirmation, red-team, winner-before-security). No new formulas; enrichment only improves
  input completeness.
- A **Nivesha-ready input adapter** (011D) maps `DiligenceEnrichmentBundle` (+ slice outputs) into
  Nivesha's input types **without** fabricating any field; missing inputs remain gaps and Nivesha's
  gates behave accordingly (a thin thesis, not a padded one).

## 9. Terrain integration contract

- `terrain_from_slice` / `build_real_evidence_terrain_for_ticker` / watchlist merge accept an
  **optional** enrichment; when absent, output is unchanged (demo byte-identical).
- Enrichment maps only to **existing** node fields and `VisualEncoding` **bases** (size = economic
  magnitude via `visual_size`; TAM → theme/value-chain magnitude; value-chain layers; bottleneck
  severity/duration). Never a new score. Terrain `validate()==()` (no centre; endpoints resolve).

## 10. Data-Quality integration contract

Real/watchlist Data Quality shows: source pipeline + authority matrix; per-source status
(fetched/unavailable/credentials_missing/failed/deferred); canonical/convenience/fallback counts;
factual vs signal observations; conflicts; overridden facts; deferred records; data gaps;
provenance; run timestamp; ticker(s); mode label; the 010F trust/completeness diagnostics; and the
011A **enrichment-coverage** panel (per-area available/missing + authority + gaps + data-sourcing
actions). All labels — **never** a numeric investability score; **never** a trade recommendation.

## 11. Company cockpit contract

The cockpit renders via the **accepted** `infinite_canvas.render_cockpit_html` only. Opened from a
planet; conditional (only where a cockpit view exists). Ticker/security mapping appears **after**
value-chain/winner mapping. Manual review required; `broker_order_id` is always `None`.

## 12. CLI / operator workflow

```
# demo (default)
PYTHONPATH=src python3 -m universe_ui --out generated/universe_ui
# evidence-ingested fixture (IREN)
PYTHONPATH=src python3 -m universe_ui --mode evidence_ingested_fixture --out generated/evidence_ui
# real, on-demand, single ticker (requires SEC_USER_AGENT; optional FMP_API_KEY)
PYTHONPATH=src python3 -m universe_ui --mode real_evidence_on_demand --ticker IREN --out generated/real_iren_ui
# real, on-demand, watchlist (<= 10 tickers)
PYTHONPATH=src python3 -m universe_ui --mode real_evidence_on_demand --tickers IREN,AAOI,INOD --out generated/real_watchlist_ui
```
Credentials are read only in `runtime/live_evidence_run.py` (env), never printed, never in HTML.

## 13. End-to-end test plan (see TEST_MATRIX_011.md)

Offline, deterministic, mock/fixture transports only. Cover: enrichment models; source authority;
data gaps; VisualEncoding semantics; Nivesha handoff adapter; no-credentials; SEC-only; SEC+FMP
mocked; multi-ticker watchlist; failed ticker; each missing enrichment area; universe/dashboard/
data-quality/cockpit render; every `data-intel` resolves; no dead anchors; no secrets; and the full
guardrail set (no scheduler/broker/buy-sell-order-submit/new-score-rank).

## 14. 011A — first accepted implementation slice

011A is **already implemented and accepted** (commit `0c0bef7`) and is treated as **011's first
accepted slice**, not re-opened. It established the enrichment package, the source contract
(manual ≠ canonical; company_claim ≠ verified_fact), fixture-backed mapping, optional terrain
integration (byte-identical when absent), and the Data-Quality enrichment-coverage panel — all
evidence-only, no scoring, offline, demo default preserved. 011B–011F build strictly on top of it
under this spec.

## 15. Acceptance gate (summary; full gate in GATE-011)

A slice is acceptable only if: the ARCHITECTURE_CONTRACT_011 invariants hold; the TEST_MATRIX_011
required tests exist and pass; the full suite is green and offline; demo default is byte-identical;
real/watchlist modes still build; no runtime guardrail is violated; and no scheduler/broker/scoring/
scraping/secret was added. Verdict is YES / PARTIAL / NO with evidence.

## 16. Proposed sub-milestones

011A (done) · 011B (enrichment mapping hardening) · 011C (terrain/DQ/cockpit integration expansion)
· 011D (Nivesha-ready input adapter) · 011E (end-to-end integration tests) · 011F (operator docs +
final hardening). Detailed in `IMPLEMENTATION_PLAN_011.md`.

## 17. Open decisions

1. Should `real_evidence_on_demand` become a non-default operator entry point, or remain purely CLI?
2. Company-IR / transcript ingestion: which safe local-fixture format, and when (if ever) a vetted
   fetch path is allowed — currently deferred.
3. yfinance real history transport: keep deferred (gap) or implement behind the explicit run.
4. Where the Nivesha-ready adapter lives (`prometheus/` input adapter vs `diligence_enrichment/`).
5. Whether a small on-disk cache for a manual run is permitted (still no scheduler).

## 18. Risks

- **Silent-demo-fallback risk**: real mode must never quietly substitute demo data → contract §D +
  gate.
- **Scope-creep into scoring**: enrichment must stay evidence-only → ADR-CANDIDATE-011 + gate.
- **Authority erosion**: convenience/fallback/manual overriding SEC → conflict.py + gate.
- **Secret leakage**: keys in HTML/logs/commits → security gate.
- **Sparse-terrain confusion**: missing data must read as missing, not empty/fake → visible gaps.
- **Test-offline drift**: a future real transport must never be hit in tests → socket-safe gate.

## 19. Cross references

- `ARCHITECTURE_CONTRACT_011.md` · `GATE-011_BUILD_ACCEPTANCE_CHECKLIST.md` · `TEST_MATRIX_011.md`
- `adr/ADR-CANDIDATE-011_DILIGENCE_ENRICHMENT_AS_EVIDENCE_LAYER.md` · `IMPLEMENTATION_PLAN_011.md`
- Repo governance: `PROJECT_CONTEXT.md`, `ARCHITECTURE_DECISIONS.md`, `specification/SUMMARY.md`
