# Part VII — Execution (design note)

**Status:** design note · **Date:** 2026-06-30 · **Book:** opens at v9.0 · **Governed by:** ADR-0010

Unlike Parts IV–VI (GEN / PROM / CIO), which were clean *consequences* of ADR-0008 and so needed no
ADR, **Part VII is governed by a new architectural principle — ADR-0010, The Cognition–Actuation
Boundary.** This note records the conventions; the *principle* lives in the ADR.

## What Part VII is
Part VII is **Execution** — the actuation layer, the system's single narrow, gated aperture onto the
world, and the first layer that takes **irreversible, real-world action**. Where every layer before
it reasons, recommends, or personalizes (all reversible), Execution *acts*. It performs **operational
validation, not investment reasoning**, and carries out only what the cognitive layers have already
decided.

It is the actuation end of ADR-0008's *understanding → judgment → action* — the point where action
stops being a decision and becomes a deed.

## The EXEC identifier namespace
- `EIOS` understanding · `GEN` opportunity · `PROM` capital allocation · `CIO` personalization ·
  **`EXEC` execution** (Part VII): `EXEC-001` is the Execution Engine.

The namespace continues the established pattern, but here it marks a deeper line: the boundary
between cognition and actuation (ADR-0010).

## The boundary (ADR-0010, load-bearing)
- **Actuation is not cognition.** Execution validates (account, market-hours, cancelability, preview,
  slippage/fill risk, reconciliation, kill-switch) but SHALL NOT discover, understand, identify
  opportunities, construct theses, allocate capital, personalize counsel, or decide actions.
- **Consumes decisions; forms none.** It actuates approved Investment Actions; it originates nothing.
- **Every irreversible action passes a gate** before touching the world.
- **Operational reality flows up as Observation, never as purpose.**
- **Broker-specific logic is implementation, not architecture** — EXEC stays broker-agnostic; broker
  adapters (IBKR, etc.) belong later in `implementation/`.

## Conventions
- **Architectural Rules:** single `AR-NNNN` namespace continues — `EXEC-001` uses **AR-19xx**.
- **Requirements:** `REQ-EXEC`.
- **Generated path:** `specification/07_Execution/EXEC-001_execution-engine.md` (slug = kebab title).
- **Canonical objects — the bifurcation (ADR-0010):** Execution introduces the **`Order`, the first
  operational object** — distinct from the reasoning objects (Knowledge Object, Intelligence
  Assessment, Opportunity, Investment Thesis, Personal Investment Profile) and **not** a specialized
  Knowledge Object. The object model now has two families: **reasoning objects** (what is known/
  judged) and **operational objects** (what is done), bridged by the **Observation**. Execution
  **reuses** `Decision` (EIOS-002) for the User Confirmation Record and `Observation` (EIOS-002) for
  Fill and Exception/Failure Records. Execution Plan, Order Intent/Preview, Position Reconciliation,
  and the Audit Trail are operational views/states, not new objects.

## Sequence (planned)
1. **EXEC-001 — Execution Engine** (the actuation layer, the Order, the Actuation Gate, and the
   operational records — governance-first).
2. EXEC-002+ — subsequent execution chapters, if and as warranted.

Broker adapters and venue integrations are **implementation**, not Part VII; they bind to EXEC at its
edge and are never written into the architecture.
