# Part V — Capital Allocation (design note)

**Status:** design note · **Date:** 2026-06-30 · **Book:** opens at v7.0

A lightweight record of the decisions that open Part V. **Not an ADR** — these are consequences
of already-accepted governance (ADR-0008), not a new governing principle, preserving the
discipline that ADRs capture only genuinely new principles.

## What Part V is
Part V is **Capital Allocation** — the investment layer, and the consumer of Opportunity
Generation (Part IV). Where Genesis decides *what is worth pursuing*, Prometheus decides
*whether, how, when, and through what instruments to invest*. This is where **investment
semantics legitimately begin**: investability, investment-thesis construction, opportunity-to-
security mapping, valuation evidence, risk/reward, position suitability, portfolio fit, capital
allocation, and timing-to-action.

It is the terminal point of ADR-0008's *understanding → judgment → action* ordering: Prometheus
is the action/decision layer.

## The PROM identifier namespace (decision)
- **`EIOS-NNN`** names *understanding* (Parts I–III).
- **`GEN-NNN`** names *opportunity generation* (Part IV).
- **`PROM-NNN`** names *capital allocation* (Part V): `PROM-001` is the Prometheus Capital
  Allocation Engine.

**Rationale.** The PROM namespace follows from ADR-0008 exactly as GEN did — it is an
implementation consequence of the layer separation, not a new principle (hence no ADR). The
distinct namespace keeps the architecture self-describing: Prometheus is a *consumer* of Genesis,
not an extension of it, and investment purpose is visibly quarantined to its own namespace.

## The boundary (load-bearing)
- Genesis says **what is worth pursuing**; Prometheus says **whether, how, when, and through what
  instruments to invest**.
- Investment purpose **SHALL NEVER flow back down** into Genesis, Reality Intelligence, or
  Scientific Understanding. Prometheus **consumes and evaluates; it does not rewrite upstream
  understanding**.
- Prometheus **recommends**; it does not execute. Execution (orders, trades, operations) is a
  further consumer again, beyond this layer.

## Conventions
- **Architectural Rules:** the single `AR-NNNN` namespace continues — `PROM-001` uses **AR-16xx**
  (after GEN-001's AR-15xx). No parallel rule namespace.
- **Requirements:** `REQ-PROM`.
- **Generated path:** `specification/05_Capital_Allocation/PROM-001_prometheus-capital-allocation-engine.md`
  (the generator already accepts the `PROM-` id scheme; the slug equals the kebab-cased title from
  the outset, per the GEN-001 slug lesson).
- **Canonical objects:** Prometheus introduces **one** new canonical object — the **Investment
  Thesis** (a specialized Knowledge Object, like the Intelligence Assessment). It **reuses** the
  canonical `Decision` object (EIOS-002) for the **Prometheus Decision Record**, and consumes the
  `Opportunity` object (EIOS-002) as input. The various assessments (investability, valuation,
  risk/reward, fit, suitability, timing, instrument mapping) are components/grounding of the
  Investment Thesis, not separate canonical objects.

## The Genesis → Prometheus consumption contract
Defined on the Prometheus side: Prometheus consumes Opportunity Hypotheses, the Opportunity
Portfolio, Opportunity Relationships (the Opportunity Graph), Opportunity Evolution, and
Opportunity Prioritization **by version** — version-pinned, replayable, explainable, and
auditable — reading them and never mutating them.

## Sequence (planned)
1. **PROM-001 — Prometheus Capital Allocation Engine** (defines the layer, its boundary, the
   consumption contract, and its outputs).
2. PROM-002+ — subsequent capital-allocation chapters, if and as warranted.

Execution/operations (placing capital, managing live positions) is a further consumer again and
will carry its own namespace when authored; it is not Part V.
