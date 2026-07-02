# GATE-011 — Build Acceptance Checklist

Status: **Draft for architect review** · Applies to: every 011B–011F slice · Companion to
`ARCHITECTURE_CONTRACT_011.md` and `TEST_MATRIX_011.md`.

Run this checklist against a slice **before** accepting/committing. Every item is a hard
**PASS / FAIL**. Any FAIL ⇒ overall verdict is **NO** (or PARTIAL if the slice is explicitly
scoped narrower). Record evidence (command output) for each section.

Legend: ☐ = to verify · each item names how to check it.

---

## 1. Architecture boundaries
- ☐ Tattva remains understanding-only (no opportunity/thesis/action/size produced; factual ≠ signal).
- ☐ Sphurana produces only opportunity hypotheses (no thesis/action/size).
- ☐ Nivesha = Investment Diligence / Capital Candidate (never relabelled "Capital Allocation"; no
  final user-specific sizing).
- ☐ Saarathi = ranges / sizing guardrails (no forced execution / exact order).
- ☐ Kriya = manual execution preview only.
- ☐ No adapter bypasses a layer's gates by importing its internals.

## 2. Source authority
- ☐ SEC canonical wins vs FMP/yfinance for the same metric/period/unit (conflict.py reused).
- ☐ Company IR is `company_claim`, not auto-verified fact.
- ☐ FMP = convenience; yfinance = fallback; manual/analyst = manual — **never** canonical.
- ☐ `assert_manual_not_canonical` / `manual_is_not_canonical()` hold.
- ☐ Unsupported fields become data gaps, never invented values.

## 3. Real-mode honesty
- ☐ `real_evidence_on_demand` never silently substitutes demo data.
- ☐ Missing sources/creds → visible Data-Quality gap/status (credentials_missing/failed/deferred).
- ☐ Sparse terrain renders with visible gaps + "terrain incomplete" notice.
- ☐ Mode label is honest (`demo`/`evidence_ingested_fixture`/`real_evidence_on_demand`); no
  live/automated/scheduled/real-time/trade-ready/production-ranking wording.
- ☐ Demo remains the default and is **byte-identical** to the previous accepted demo build.

## 4. Enrichment models
- ☐ Models construct; every data value carries explicit authority + claim_status + source_refs.
- ☐ Missing fields → explicit data gaps.
- ☐ **No** field named buy/sell/hold/order/trade/score/rank/rating on any model.
- ☐ Manual estimates keep `estimate_type=manual`, authority manual.

## 5. Nivesha handoff
- ☐ Enrichment/terrain feed Nivesha inputs with provenance + gaps; enrichment computes no investability.
- ☐ Nivesha uses its existing gauntlet; no new formulas; missing inputs → a thin thesis, not padded.
- ☐ The Nivesha-ready adapter fabricates no field; gaps stay gaps.

## 6. Terrain integration
- ☐ Enrichment is optional; absent ⇒ output unchanged (demo byte-identical).
- ☐ market_cap → CompanyNode magnitude + `size_basis` via existing `visual_size` (no new metric).
- ☐ TAM → theme/value-chain magnitude; value-chain layers / bottleneck severity+duration populate
  only when provided; else honest gap + dashed encoding.
- ☐ `terrain.validate() == ()` (endpoints resolve; no centre/hub; no fake edges).

## 7. Data Quality
- ☐ Source pipeline + authority matrix + per-source status + counts render.
- ☐ Enrichment coverage: per-area available/missing + authority + per-ticker gaps.
- ☐ Data-sourcing actions render — **never** a trade recommendation.
- ☐ Diagnostics are labels (010F vocab); no numeric investability score.

## 8. Cockpit
- ☐ Cockpit renders via the accepted `render_cockpit_html` only (panel markers present).
- ☐ Conditional (only where a cockpit view exists); disabled text otherwise, no dead anchor.
- ☐ `broker_order_id == None`; ticket state `previewed`; manual review required.

## 9. UI interaction
- ☐ Full-screen telescope hero first; intelligence pane below the fold; floating preview.
- ☐ Every `data-intel` resolves; every `data-target-path` resolves to a level panel.
- ☐ Breadcrumb parent chains reach `universe`; dashboard "Locate in Universe" resolves.
- ☐ No dead anchors; no stale `.selected` after click/back/fit/reset.
- ☐ Semantic relationship lines only; no centre-of-universe; no page-per-level; no entity tabs.

## 10. Security
- ☐ No network on import; whole suite runs offline (socket kill-switch).
- ☐ Only `live_transport` imports network, lazily; new packages import no network/scheduler.
- ☐ No API key in generated HTML; no key printed; no `.env`/secret committed.
- ☐ Missing credentials → visible gap, not a leak/crash.

## 11. Tests
- ☐ TEST_MATRIX_011 required rows for the slice exist and pass.
- ☐ Tests use mocks/fixtures only (no real network).
- ☐ Tests are not over-fitted (structural assertions, e.g. link-graph helpers, not brittle strings).

## 12. No scheduler / broker / scoring guardrails
- ☐ No scheduler/background-job/automated-refresh/automated-trading import or code path.
- ☐ No broker automation / order placement / routing / recording.
- ☐ No `<button>`/`<form>`/`onclick`/`type=submit`/place-order/buy/sell in generated HTML.
- ☐ No new `def *score`/`*rank`/`*rating`; no new alpha ranking; no hidden master score.

## 13. Deterministic / offline tests
- ☐ Two builds (same inputs / injected `now`) are byte-identical for demo and for mock-transport
  real builds.
- ☐ No `Math.random`/`Date.now`/`time.time()` in id/replay/render paths (real-mode timestamp is
  injectable and only stamped on real runs).

---

## Verdict block (fill in per slice)

```
Slice: 011x — <name>
Suite: <N> tests, OFFLINE OK
Demo default byte-identical: YES/NO
Real single + watchlist build: YES/NO
Contract invariants A–G: <pass/fail per letter>
Checklist sections 1–13: <pass/fail>
Verdict: YES / PARTIAL / NO
Evidence: <commands + key outputs>
```
