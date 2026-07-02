# ARCHITECTURE CONTRACT — 011

Status: **Draft for architect review** · Governs: 011B–011F · Companion to `SPEC-011_END_TO_END_DILIGENCE_RESEARCH_MVP.md`

These are **non-negotiable invariants**. Every 011 build slice must satisfy all of them. A slice
that violates any invariant is **NO** at the gate, regardless of feature completeness. Each
invariant is stated with its enforcement point (where in the code/tests it is checked).

---

## A. Layer boundaries

Each layer does its own job and only its job. Purpose flows up, never down (ADR-0008).

| Layer | Role | Must NOT do |
|-------|------|-------------|
| **Adhāra** | Foundation | — |
| **Buddhi** | Cognitive Architecture | — |
| **Tattva** | Reality Intelligence / understanding only | infer investment meaning; produce opportunities/theses/actions; factual observations must NOT become signals |
| **Sphurana** | Opportunity Generation / theme & opportunity hypothesis | produce a thesis, an action, or a size |
| **Nivesha** | Investment Diligence / **Capital Candidate** | perform final user-specific sizing; place/route orders; be relabelled "Capital Allocation" |
| **Saarathi** | Personal CIO / Portfolio Fit / **Sizing Guardrails** | force trade execution; emit exact orders — it shows ranges/guardrails |
| **Kriya** | **Manual Execution Preview** | place, route, or record a broker order; auto-execute |
| **Anubhava** | Feedback / Learning | — |

**Enforcement**: existing boundary tests per layer; 011 adapters must not import a layer's internals
to bypass its gates; the Nivesha-ready adapter (011D) maps inputs only.

## B. Stocks are the OUTPUT, never the entry point

Preserve the causal chain — reason from reality to the stock, never rank stocks first:

```
Reality → Technology → Adoption → Supply Chains → Bottlenecks
→ Corporate Winners → Financial Inflection → Institutional Accumulation → Stock Price
```

- No stock-first ranking logic. No "list of tickers scored/ranked" as a primary artifact.
- Ticker/security mapping appears only **after** value-chain / winner mapping.
- The watchlist (`--tickers`) is an operator research convenience, not a ranking; companies are
  grouped by inferred theme (co-location), never by a computed rank.

**Enforcement**: "security mapping after winners" qualifier tests; no `*score`/`*rank` function; the
watchlist merge produces theme groups + an explicit `unclassified` region, not an ordered leaderboard.

## C. Source authority

```
SEC / data.sec.gov      = CANONICAL for filings & facts
Company IR / IR presentations / official transcripts = PRIMARY (a company_claim, NOT auto-verified)
FMP                     = CONVENIENCE (paid API)
yfinance                = FALLBACK / research-only
manual / analyst / user = MANUAL/ANALYST — NEVER canonical
```

- **Lower authority cannot override higher authority for the same metric / period / unit.**
- Company statements are stamped `company_claim`, not `verified_fact`.
- Manual/analyst estimates (e.g. a manual TAM) are `estimate_type=manual`, authority manual — never
  promoted to canonical.
- Unsupported fields become **data gaps**, never invented values.

**Enforcement**: `evidence_ingestion/conflict.py` (family-scoped, period-aware; SEC wins) reused
verbatim; `diligence_enrichment/source_contract.py` (`assert_manual_not_canonical`, `ClaimStatus`);
authority-preservation tests.

## D. Real-mode honesty

- `real_evidence_on_demand` must **never silently fall back to demo data**. If a source/credential
  is missing or a fetch fails, that is a **visible** Data-Quality gap/status, not a demo substitute.
- **Sparse terrain is acceptable and correct.** Missing data must be visible (dashed encodings,
  gap cards, "terrain incomplete" notice, per-ticker status).
- **Demo remains explicit and the DEFAULT.** Mode labels are honest: `demo` / `evidence_ingested_fixture`
  / `real_evidence_on_demand` — never "live", "automated", "scheduled", "real-time", "trade-ready",
  or "production ranking".

**Enforcement**: mode-label tests; "no unrelated demo galaxies in evidence/real mode" tests; failed
ticker visible-not-dropped tests; demo default byte-identical tests.

## E. No hidden scoring

- Diligence enrichment provides **evidence and gaps only**.
- No hidden investability scores. No new alpha ranking. No buy/sell/hold field or output.
- `VisualEncoding` **must not create a score**: size = economic magnitude (existing `visual_size`),
  glow = heat/status, opacity = evidence quality, etc. — presentation of existing facts, never a
  new metric. Trust/completeness are **labels**, not numbers.

**Enforcement**: no `*score`/`*rank`/`*rating` function; no numeric investability field on any
enrichment/diagnostic model; VisualEncoding decoupling tests (large-weak ≠ top; size independent of
bucket/heat).

## F. Execution boundary

- No broker automation. No order placement, routing, or recording. No buy/sell/order/submit button
  or form anywhere in generated HTML.
- **Kriya creates a manual execution PREVIEW only.** `broker_order_id` is always `None`; ticket state
  is `previewed`.
- An **explicit user-selected size** appears only in the `ManualExecutionIntent` / Kriya context.
- **Saarathi shows ranges / sizing guardrails**, not forced trade execution.

**Enforcement**: no `<button>`/`<form>`/`onclick`/`type=submit`/`place order`/buy/sell in HTML;
ticket-preview tests; "personalized has no exact order/size" tests; explicit-size-required tests.

## G. Runtime / security boundary

- No scheduler. No background jobs. No automated refresh. No automated trading.
- **Real fetching only in explicit manual/on-demand mode.** No network call during import. No network
  call in tests unless mocked. The single network boundary is `evidence_ingestion/live_transport.py`,
  which imports `urllib` **lazily** (function-scoped) and is injected into the inert clients.
- No secrets committed. No API keys in generated HTML. No API keys printed (presence booleans only).
  Credentials read only in `runtime/live_evidence_run.py` (env). Missing credentials → visible gap,
  not a crash-with-leak.

**Enforcement**: AST tests (only `live_transport` imports network, lazily; new packages import no
network/scheduler); whole-suite socket kill-switch (offline); no-key-in-HTML tests; no `.env`
committed; empty-cred `ValueError` tests.

---

## Invariant → enforcement quick map

| Invariant | Primary enforcement |
|-----------|---------------------|
| A layer boundaries | per-layer boundary tests; adapters map inputs only |
| B stocks-are-output | after-winners qualifier; no rank fn; theme grouping not leaderboard |
| C source authority | `conflict.py` (SEC wins); `source_contract.py`; authority tests |
| D real-mode honesty | mode-label + no-silent-demo + sparse-visible + demo-default tests |
| E no hidden scoring | no `*score`/`*rank` fn; no numeric investability field; VisualEncoding decoupling |
| F execution boundary | no affordance in HTML; ticket preview / broker_order_id None; range-not-size |
| G runtime/security | offline suite; lazy single network boundary; no secret in HTML/commits |

Any change to these invariants requires a new ADR (see the repository ADR process), not a build patch.
