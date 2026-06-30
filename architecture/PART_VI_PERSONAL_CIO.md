# Part VI — Personal CIO (design note)

**Status:** design note · **Date:** 2026-06-30 · **Book:** opens at v8.0

A lightweight record of the decisions that open Part VI. **Not an ADR** — these are consequences
of already-accepted governance (ADR-0008), not a new governing principle.

## What Part VI is
Part VI is **Personal CIO** — the personalization layer, and the consumer of Capital Allocation
(Part V). Where Prometheus determines investability and capital allocation in general, Personal
CIO **adapts those outputs to the individual user**. This is where **personalization legitimately
begins**: user objectives, risk tolerance, liquidity needs, tax constraints, time horizon, account
structure, existing holdings, position limits, preferences and exclusions, communication style,
and action prioritization.

The full chain is now: **EIOS understands reality → Genesis identifies opportunities → Prometheus
determines investability and capital allocation → Personal CIO adapts those outputs to the
individual user.**

## The CIO identifier namespace (decision)
- **`EIOS-NNN`** understanding (Parts I–III) · **`GEN-NNN`** opportunity (Part IV) ·
  **`PROM-NNN`** capital allocation (Part V) · **`CIO-NNN`** personalization (Part VI):
  `CIO-001` is the Personal CIO Engine.

**Rationale.** The CIO namespace follows from ADR-0008 exactly as GEN and PROM did — an
implementation consequence of the layer separation, not a new principle (hence no ADR). The
acronym `CIO` is preserved through generation by the generator's `ACRONYMS` set.

## The boundary (load-bearing — clarified by the Chief Architect)
- Personal CIO **personalizes Prometheus outputs**; it does **not** become the generic
  portfolio-construction engine.
- **Holistic portfolio construction** — sizing logic, correlation budget, rebalancing, full
  position-set optimization — belongs primarily to **Prometheus** (likely a future PROM-005), **not**
  to Personal CIO.
- Personal CIO may apply **user-specific constraints and preferences** to Prometheus
  recommendations, but it **must not redefine the general capital-allocation machinery**.
- Personal CIO **must never rewrite** Prometheus, Genesis, Reality Intelligence, or Scientific
  Understanding. It consumes and adapts; it does not reconstruct.

## Conventions
- **Architectural Rules:** the single `AR-NNNN` namespace continues — `CIO-001` uses **AR-17xx**
  (after PROM-001's AR-16xx). No parallel rule namespace.
- **Requirements:** `REQ-CIO`.
- **Generated path:** `specification/06_Personal_CIO/CIO-001_personal-cio-engine.md` (slug =
  kebab-cased title from the outset; acronym preserved).
- **Canonical objects:** Personal CIO introduces **one** new canonical object — the **Personal
  Investment Profile** (a specialized Knowledge Object: the user's objectives, constraints, and
  preferences). It **reuses** the canonical `Decision` object (EIOS-002) for the **Personal CIO
  Decision Record**. The personalized views (thesis/allocation/risk), the action queue, and the
  explanation are **personalized projections** of Prometheus outputs, not new canonical objects.

## The Prometheus → Personal CIO consumption contract
Defined on the Personal CIO side: Personal CIO consumes all ten Prometheus outputs (Investment
Theses, Investability Assessments, Security/Instrument Mapping, Valuation Evidence, Risk/Reward
Assessments, Position Suitability, Portfolio Fit Assessments, Capital Allocation Recommendations,
Timing-to-Action Assessments, Prometheus Decision Records) **by version** — version-pinned,
replayable, explainable, auditable, and **re-evaluable when Prometheus updates a thesis,
recommendation, or decision record** — reading them and never mutating them.

## Sequence (planned)
1. **CIO-001 — Personal CIO Engine** (defines the layer, its boundary, the consumption contract,
   and its outputs).
2. CIO-002+ — subsequent personalization chapters, if and as warranted.

Execution (placing the user's capital, operating live positions) is a further consumer again and
will carry its own namespace when authored; it is not Part VI.
