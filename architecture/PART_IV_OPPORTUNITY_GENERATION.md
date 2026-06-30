# Part IV — Opportunity Generation (design note)

**Status:** design note · **Date:** 2026-06-30 · **Book:** opens at v6.0

A lightweight record of the design decisions that open Part IV. **This is deliberately not an
ADR.** It records consequences of already-accepted governance (ADR-0008), not a new architectural
principle — preserving the discipline that ADRs capture only genuinely new principles.

## What Part IV is
Part IV is **Opportunity Generation** — Layer 3 of ADR-0008. It is the first layer to consume the
understanding produced by Parts I–III rather than to form understanding. Where Reality Intelligence
(Part III) forms domain understanding, Opportunity Generation decides what is worth pursuing. This
is where **purpose** — opportunity, value, investability — first legitimately enters the
architecture. Per ADR-0008, purpose enters here and never flows back down into understanding.

## The EIOS → GEN identifier boundary (decision)
Chapters in Part IV carry a distinct identifier namespace:

- **`EIOS-NNN`** names *understanding* (Parts I–III).
- **`GEN-NNN`** names *opportunity generation* (Part IV): `GEN-001` is Genesis; `GEN-002`, `GEN-003`,
  … are subsequent opportunity-generation chapters.

**Rationale.** This is an implementation consequence of ADR-0008's accepted separation between
Understanding and Opportunity Generation, not a new governing principle (hence no ADR). The
distinct namespace makes the boundary self-describing: Genesis is the *first consumer of EIOS*, not
the *final chapter of EIOS*. It also generalizes — future consumers (e.g. investment, a personal
CIO, other applications) carry their own namespaces, keeping the shape *EIOS = understanding
substrate; consumers carry their own identity* visible in the identifiers themselves.

## Conventions
- **Architectural Rules:** the single `AR-NNNN` namespace continues sequentially — `GEN-001`
  uses **AR-15xx**, `GEN-002` would use AR-16xx, and so on. No parallel rule namespace is
  introduced (consistent with the retirement of `MR`). The Architectural Rule Index maps each
  rule to the chapter it appears in, so the scheme is collision-free.
- **Requirements:** `REQ-GEN` (Genesis). Future opportunity chapters take their own `REQ-` prefix.
- **Generated path:** `specification/04_Opportunity_Generation/GEN-001_genesis.md` (the generator
  already accepts the `GEN-` id scheme without modification — its chapter-id pattern is general).
- **Canonical objects:** Opportunity Generation introduces no new canonical object. It reuses the
  `Opportunity` object (EIOS-002), names its lifecycle states (the candidate "Opportunity
  Hypothesis"), and composes Opportunity Portfolios — consistent with the canonical-currencies
  analysis and decision Q-b (Genesis owns the Opportunity lifecycle semantics without redefining
  the frozen object).

## Sequence (planned)
1. **GEN-001 — Genesis** (the opportunity-generation engine; resolves ARB-002 Cap 12).
2. GEN-002+ — subsequent opportunity-generation chapters, as warranted.

Downstream investment subsystems (investment thesis, portfolio, allocation) are further consumers
again and will carry their own namespace when authored; they are not Part IV.
