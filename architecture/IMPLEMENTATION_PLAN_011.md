# IMPLEMENTATION PLAN — 011

Status: **Draft for architect review** · Companion to `SPEC-011_END_TO_END_DILIGENCE_RESEARCH_MVP.md`,
`ARCHITECTURE_CONTRACT_011.md`, `GATE-011_BUILD_ACCEPTANCE_CHECKLIST.md`, `TEST_MATRIX_011.md`.

Phase 011 is broken into six slices. **011A is already implemented and accepted** and is the first
accepted slice; 011B–011F build strictly on top of it under the contract and gate. Each slice is one
coherent capability, gated (YES/PARTIAL/NO) before commit, committed locally, never pushed. Demo
stays default and byte-identical throughout; no scheduler/broker/automation/scoring is added by any
slice.

---

## 011A — Enrichment models & source contract — **DONE / ACCEPTED** (commit `0c0bef7`)

- **Purpose**: establish the evidence-only enrichment layer: typed models, source authority + claim
  status, fixture-backed adapters, optional terrain/Data-Quality wiring.
- **Files (delivered)**: `src/diligence_enrichment/{models,source_contract,adapters,enrich,coverage,
  __init__}.py`; additive optional wiring in `src/universe_ui/{terrain_adapters,real_terrain,
  view_models,render,app}.py`; `tests/test_diligence_enrichment.py`.
- **Tests (delivered)**: matrix rows 1–5, 15–21 (models, authority, claim status, per-area gaps),
  plus terrain wiring via `visual_size` and the enrichment-coverage panel.
- **Gate**: passed — no decision/score field; manual ≠ canonical; SEC preferred over FMP; demo
  byte-identical; offline; 680 tests green.
- **Status**: accepted; **not re-opened**.

## 011B — Fixture-backed enrichment mapping hardening

- **Purpose**: broaden and harden the fixture→enrichment mapping so more real SEC/FMP fields populate
  correctly, edge cases degrade to gaps, and authority/claim-status are applied consistently.
- **Files likely to change**: `src/diligence_enrichment/{adapters,enrich,source_contract}.py`;
  possibly small fixture files under `tests/fixtures/`; `tests/test_diligence_enrichment.py`.
- **Required tests**: matrix rows 3–7, 10–12, 15–21 (SEC-only; SEC+FMP; no-creds; each missing area →
  gap; manual stays manual; company_claim stays claim); no-fabrication assertions.
- **Acceptance gate**: GATE-011 §2/§4/§10/§11 + globals; demo byte-identical; offline; no new score.
- **Risks**: over-mapping (inventing fields FMP/SEC don't actually provide); mis-stamping authority.
- **Fallback behaviour**: any field a fixture doesn't support → explicit gap + data action; never a
  synthesized value.

## 011C — Terrain / Data-Quality / cockpit integration expansion

- **Purpose**: surface more enrichment in the terrain, Data-Quality panels, and (read-only) cockpit
  context — for single and watchlist real modes — while keeping everything a visible gap when absent.
- **Files likely to change**: `src/universe_ui/{terrain_adapters,real_terrain,watchlist_terrain,
  view_models,render,terrain_diagnostics}.py`; interaction tests.
- **Required tests**: matrix rows 8, 13–14, 22–27 (VisualEncoding semantics; watchlist merge; failed
  ticker; universe/dashboard/DQ/cockpit render; every data-intel resolves; no dead anchors); no
  new metric; validate()==().
- **Acceptance gate**: GATE-011 §6/§7/§8/§9 + globals; demo byte-identical; closed cross-link graph.
- **Risks**: introducing a centre/edge or a UI ranking; breaking the closed link graph; demo drift.
- **Fallback behaviour**: absent enrichment ⇒ pre-011C output (byte-identical); missing field ⇒
  dashed/neutral gap + diagnostic.

## 011D — Nivesha-ready input adapter

- **Purpose**: map `DiligenceEnrichmentBundle` (+ slice outputs) into Nivesha's existing diligence
  input types, so Nivesha runs on real enriched inputs — **without** fabricating fields or changing
  Nivesha logic.
- **Files likely to change**: a new adapter (location TBD per SPEC-011 open decision — `prometheus/`
  input adapter vs `diligence_enrichment/`); tests only otherwise.
- **Required tests**: matrix row 9 (+ 2, 5, 7): enrichment→Nivesha inputs; missing inputs stay gaps
  (thin thesis, not padded); no new score/rank; Nivesha gates unchanged; authority preserved.
- **Acceptance gate**: GATE-011 §1/§5 + globals; Nivesha behaviour identical for identical inputs.
- **Risks**: smuggling a score/decision into the adapter; padding missing inputs; bypassing a gate.
- **Fallback behaviour**: insufficient inputs ⇒ Nivesha produces a limited/blocked thesis honestly;
  the adapter never invents inputs to force a stronger thesis.

## 011E — End-to-end integration tests

- **Purpose**: a fixture/mock-backed end-to-end proof that on-demand evidence → ingestion → Tattva →
  Sphurana → enrichment → Nivesha → Saarathi → Kriya → terrain → render works and stays honest and
  gap-visible, single and watchlist.
- **Files likely to change**: `tests/` only (a new end-to-end test module); possibly a thin runtime
  wiring helper if strictly required (no new behaviour).
- **Required tests**: matrix row 36 (+ 13, 22–27, 33–35): full chain from mock transports; sparse but
  honest; offline; deterministic with injected `now`; broker_order_id None; no affordance.
- **Acceptance gate**: full GATE-011; whole suite offline; demo byte-identical.
- **Risks**: a test accidentally hitting the network; over-fitting to one fixture; hidden coupling.
- **Fallback behaviour**: stages that can't run on the available evidence are asserted to stop with a
  visible gap, not to fabricate.

## 011F — Operator docs & final hardening

- **Purpose**: operator-facing documentation (how to run demo / fixture / real single / watchlist,
  configure `SEC_USER_AGENT` / `FMP_API_KEY` safely, interpret sparse terrain + gaps + data actions)
  and a final guardrail sweep.
- **Files likely to change**: `docs/` and/or `architecture/` markdown; possibly `README`-level notes;
  no runtime behaviour change.
- **Required tests**: re-run the whole matrix (globals 28–35) + a docs-accuracy check (commands in the
  docs actually build).
- **Acceptance gate**: full GATE-011; documentation matches behaviour; nothing new introduced.
- **Risks**: docs implying automation/live/trade-readiness; credential guidance that encourages
  leaking secrets.
- **Fallback behaviour**: docs explicitly state manual/on-demand, deferred/forbidden items, and that
  missing data is expected and shown.

---

## Sequencing & rules

- Order: 011B → 011C → 011D → 011E → 011F (011A done). 011D depends on 011B/C input quality; 011E
  depends on 011D.
- One coherent capability per commit; commit locally only on a clean gate; **never push**.
- Demo default stays byte-identical after every slice; real single + watchlist modes always build.
- Any change to the ARCHITECTURE_CONTRACT_011 invariants requires a new ADR, not a build patch.
- Every slice ends with a YES/PARTIAL/NO verdict + evidence per `GATE-011`.
