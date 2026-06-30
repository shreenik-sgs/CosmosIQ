---
generated: true
do_not_edit: true
canonical_source: architecture/EIOS_Architecture_Book.md
chapter: EXEC-002
slug: execution-safety-and-operational-integrity
book_version: 9.1
generator_version: 1.1
source_hash: a28bdb4f6807ec3fa5d2ddabd2b9b703f59aa80a9486aeb29f42599108cd9ce7
generated_at: 2026-06-30T11:21:33-05:00
---

# EXEC-002 — Execution Safety & Operational Integrity

**Chapter Class:** Execution

### Purpose

Execution Safety & Operational Integrity makes actuation safe before any real-world order can be submitted.

EXEC-001 established the boundary and the gate; EXEC-002 establishes the hard invariants that irreversible action depends upon.

On the irreversibility surface, the absence of these invariants is how real capital is lost: a duplicate order, an unknown outcome assumed filled, a stale action submitted, a confirmation that authorized a different order than the one sent.

The objective is an Execution layer operationally safe enough to support implementation — submitting at most once, never assuming the unknown, never acting on the stale, and reconciling everything it does.

---

### Conformance

This chapter SHALL conform to:

* EIOS-000 — Constitution
* EIOS-001 — Purpose
* EIOS-002 — Knowledge Model
* EIOS-003 — World Model
* EIOS-004 — Computational Scientific Cognition
* EIOS-005 — Systems Theory
* EIOS-006 — Interconnected Systems Intelligence
* EIOS-007 — Models & Model Management
* EIOS-008 — Experience Layer
* EIOS-009 — Scientific Discovery
* EIOS-010 — Reality Intelligence
* EIOS-011 — Technology Intelligence
* EIOS-012 — Economic Intelligence
* EIOS-013 — Supply Network Intelligence
* EIOS-014 — Capital Intelligence
* GEN-001 — Genesis Discovery Engine
* PROM-001 — Prometheus Capital Allocation Engine
* PROM-002 — Position Lifecycle Intelligence
* CIO-001 — Personal CIO Engine
* EXEC-001 — Execution Engine

This chapter additionally conforms to ADR-0008, ADR-0009, and ADR-0010.

---

### Position in the Architecture

Execution Safety & Operational Integrity is part of the Execution layer and extends EXEC-001.

EXEC-001 holds the line between cognition and actuation; EXEC-002 holds the line between actuation and disaster.

It introduces no new object: every safeguard here is an Order state, an Order operation, an invariant, or a view, reusing the Decision and Observation already defined. It is governed, like all of Execution, by ADR-0010.

---

### Operational Integrity

Execution SHALL be operationally safe before it acts.

An action SHALL be actuated at most once, an unknown outcome SHALL never be assumed, nothing stale SHALL be acted upon, and every action and its outcome SHALL be reconciled end to end.

These are not refinements of actuation; on the irreversibility surface they are its preconditions, as binding as the Actuation Gate itself.

---

### At-Most-Once Actuation

Every approved Investment Action SHALL be actuated at most once.

A retry, replay, reconnect, crash recovery, double request, or repeated submission SHALL NEVER produce a duplicate order.

Actuation SHALL be made idempotent by a stable identity derived from the Investment Action and its confirmation, so that a repeated request resolves to the same single Order rather than a new one.

Replay for audit SHALL reconstruct an Order; it SHALL NEVER re-submit one.

---

### The Indeterminate Order State

When broker acknowledgment is missing, delayed, disconnected, timed out, or ambiguous, the Order SHALL enter an explicit indeterminate state.

In the indeterminate state, Execution SHALL NOT assume the Order filled, unfilled, cancelled, or rejected.

An indeterminate Order SHALL be resolved only by reconciliation against the broker's authoritative record, never by assumption.

No downstream effect SHALL depend on an indeterminate Order until its true state is established.

---

### Stale-Action Revalidation

Before actuation, Execution SHALL revalidate that the action remains current.

Revalidation SHALL check:

* the Investment Action version
* the Personalized Action Queue item version
* Order Preview freshness
* User Confirmation freshness
* market movement beyond the previewed tolerance
* account and venue constraints
* available buying power, margin, and cash
* instrument tradability
* market-hours status
* the kill-switch and disable-execution state

If anything material has changed, the Order SHALL return to preview and confirmation rather than act.

Execution SHALL NOT act on stale state.

---

### Confirmation-to-Preview Binding

User Confirmation SHALL bind to the exact Order Preview shown to the user.

Any change to instrument, side, quantity, order type, limit price, stop price, time-in-force, account, estimated cost, risk warning, or execution venue SHALL invalidate the confirmation and SHALL require a new preview and a new confirmation.

A confirmation SHALL authorize only the previewed Order, and never any Order that differs from it.

---

### The Single Actuation Chokepoint

The Actuation Gate SHALL be the sole path by which any Order reaches the world.

No adapter, script, workflow, retry path, emergency path, or implementation shortcut SHALL bypass the Gate.

There SHALL be exactly one aperture onto the world, and the Actuation Gate SHALL be it.

---

### Full-Chain Reconciliation

Execution SHALL reconcile the entire chain from decision to outcome:

* intended action against Order Intent
* Order Intent against Order Preview
* Order Preview against User Confirmation
* User Confirmation against the submitted order
* the submitted order against broker acknowledgment
* broker acknowledgment against fills
* fills against the resulting position
* the resulting position against the expected position
* the execution outcome against the Personal CIO and Prometheus records

Any divergence at any link SHALL be surfaced as Observation and SHALL halt dependent actuation until it is resolved.

---

### Cancel, Replace, and Modify

Cancel, replace, and modify SHALL themselves be gated actuations, subject to the Actuation Gate.

Execution SHALL model: cancel requested, cancel acknowledged, cancel rejected, the cancel/fill race, replace requested, replace acknowledged, replace rejected, the modified Order state, and recovery from a failed cancel or replace.

A cancel that races a fill SHALL be resolved by reconciliation against the broker's authoritative record; Execution SHALL NEVER assume a cancel succeeded.

---

### Partial Fills and Multi-Fill Completion

Execution SHALL support partial fills and multiple fills against a single Order.

Execution SHALL aggregate fills, tracking remaining quantity and average price, and SHALL recognize final completion only when the Order is fully filled, cancelled, expired, or rejected.

Execution SHALL support partial cancellation and SHALL reconcile position after partial execution.

Each fill SHALL be an Observation; the aggregate SHALL be a derived view over those Observations.

---

### Order Expiration

Execution SHALL support time-in-force expiration as an explicit Order state.

Expiration SHALL be distinguished from cancellation, rejection, and failure.

An expired Order SHALL have produced no further fills after expiry, confirmed by reconciliation.

---

### Emergency Controls

Execution SHALL provide:

* a kill switch — the standing power to halt all actuation at once
* cancel-all — the power to cancel all open orders
* a disable-execution mode — a persistent state in which no actuation is permitted
* human override — the standing ability of a human to halt, cancel, or override any action
* an emergency audit trail — a complete record of every emergency control invoked
* safe recovery — a defined, reconciled path back to normal operation after an emergency stop

Emergency controls SHALL be available independent of any single Order, and their use SHALL itself be recorded and reconciled.

---

### Object Discipline

EXEC-002 SHALL introduce no new canonical object, and no new object beyond the Order.

The capabilities of this chapter SHALL be expressed as Order states, Order operations, invariants, and views, reusing existing objects: User Confirmation as a Decision; fills, rejections, failures, and exceptions as Observations; reconciliation and audit trails as views; Position State as a derived view; and cancel, replace, and modify as gated operations on the Order.

---

### Boundary

Execution performs operational validation, not investment reasoning.

Execution SHALL NOT decide what to buy, sell, hold, add, trim, exit, avoid, wait, or rotate.

Execution SHALL NOT change Prometheus or Personal CIO recommendations.

Execution SHALL NOT bypass confirmation.

Execution SHALL NOT act on stale, ambiguous, unconfirmed, or unreconciled state.

Broker-specific adapter logic SHALL remain implementation, not architecture.

---

### Replayability and Auditability

Every Order state, operation, revalidation, reconciliation, and emergency control SHALL be replayable and auditable.

Replay SHALL reconstruct what happened; it SHALL NEVER re-actuate.

The operational history SHALL be preserved complete and SHALL never be rewritten.

---

### Architectural Rules

- **AR-2001** — Every approved Investment Action SHALL be actuated at most once; no retry, replay, reconnect, crash recovery, or repeated request SHALL produce a duplicate order.
- **AR-2002** — Actuation SHALL be made idempotent by a stable identity derived from the Investment Action and its confirmation, so a repeated request resolves to the same single Order.
- **AR-2003** — Replay for audit SHALL reconstruct an Order and SHALL NEVER re-submit one.
- **AR-2004** — When broker acknowledgment is missing, delayed, disconnected, timed out, or ambiguous, the Order SHALL enter an explicit indeterminate state.
- **AR-2005** — In the indeterminate state, Execution SHALL NOT assume the Order filled, unfilled, cancelled, or rejected; it SHALL be resolved only by reconciliation against the broker's authoritative record.
- **AR-2006** — No downstream effect SHALL depend on an indeterminate Order until its true state is established.
- **AR-2007** — Before actuation, Execution SHALL revalidate currency against the Investment Action version, the Personalized Action Queue item version, Order Preview freshness, User Confirmation freshness, market movement, account and venue constraints, available buying power/margin/cash, instrument tradability, market-hours status, and the kill-switch/disable-execution state.
- **AR-2008** — If anything material has changed at revalidation, the Order SHALL return to preview and confirmation rather than act; Execution SHALL NOT act on stale state.
- **AR-2009** — User Confirmation SHALL bind to the exact Order Preview shown; any change to instrument, side, quantity, order type, limit price, stop price, time-in-force, account, estimated cost, risk warning, or venue SHALL invalidate the confirmation and require a new preview and confirmation.
- **AR-2010** — A confirmation SHALL authorize only the previewed Order and never any Order that differs from it.
- **AR-2011** — The Actuation Gate SHALL be the sole path by which any Order reaches the world; no adapter, script, workflow, retry path, emergency path, or implementation shortcut SHALL bypass it.
- **AR-2012** — Execution SHALL reconcile the full chain — intended action, Order Intent, Order Preview, User Confirmation, submitted order, broker acknowledgment, fills, resulting position, expected position, and the Personal CIO and Prometheus records — surfacing any divergence as Observation.
- **AR-2013** — Any reconciliation divergence SHALL halt dependent actuation until it is resolved.
- **AR-2014** — Cancel, replace, and modify SHALL themselves be gated actuations subject to the Actuation Gate.
- **AR-2015** — Execution SHALL model cancel requested, cancel acknowledged, cancel rejected, the cancel/fill race, replace requested, replace acknowledged, replace rejected, the modified Order state, and recovery from a failed cancel or replace.
- **AR-2016** — A cancel that races a fill SHALL be resolved by reconciliation against the broker's authoritative record; Execution SHALL NEVER assume a cancel succeeded.
- **AR-2017** — Execution SHALL support partial and multiple fills against a single Order, aggregating fills with remaining quantity and average price, and recognizing completion only when the Order is fully filled, cancelled, expired, or rejected.
- **AR-2018** — Execution SHALL support partial cancellation and SHALL reconcile position after partial execution; each fill SHALL be an Observation and the aggregate a derived view.
- **AR-2019** — Execution SHALL support time-in-force expiration as an explicit Order state, distinct from cancellation, rejection, and failure.
- **AR-2020** — Execution SHALL provide a kill switch, cancel-all of open orders, a disable-execution mode, human override, an emergency audit trail, and a defined reconciled safe-recovery path; emergency controls SHALL be available independent of any single Order and their use recorded and reconciled.
- **AR-2021** — EXEC-002 SHALL introduce no new canonical object and no new object beyond the Order; its capabilities SHALL be expressed as Order states, operations, invariants, and views, reusing Decision and Observation.
- **AR-2022** — Execution SHALL perform operational validation, not investment reasoning; it SHALL NOT decide what to buy, sell, hold, add, trim, exit, avoid, wait, or rotate, and SHALL NOT change Prometheus or Personal CIO recommendations.
- **AR-2023** — Execution SHALL NOT bypass confirmation and SHALL NOT act on stale, ambiguous, unconfirmed, or unreconciled state.
- **AR-2024** — Every Order state, operation, revalidation, reconciliation, and emergency control SHALL be replayable and auditable; replay SHALL reconstruct, never re-actuate; operational history SHALL never be rewritten.
- **AR-2025** — Broker-specific adapter logic SHALL remain implementation, not architecture; Execution Safety SHALL remain implementation independent.

---

### Requirements Introduced

- **REQ-EXS-001** — Operational Integrity
- **REQ-EXS-002** — At-Most-Once Actuation
- **REQ-EXS-003** — Idempotency
- **REQ-EXS-004** — Indeterminate Order State
- **REQ-EXS-005** — Indeterminate Resolution by Reconciliation
- **REQ-EXS-006** — Stale-Action Revalidation
- **REQ-EXS-007** — Confirmation-to-Preview Binding
- **REQ-EXS-008** — Single Actuation Chokepoint
- **REQ-EXS-009** — Full-Chain Reconciliation
- **REQ-EXS-010** — Divergence Halts Actuation
- **REQ-EXS-011** — Cancel, Replace, and Modify
- **REQ-EXS-012** — Cancel/Fill Race Resolution
- **REQ-EXS-013** — Partial and Multi-Fill Completion
- **REQ-EXS-014** — Fill Aggregation
- **REQ-EXS-015** — Order Expiration
- **REQ-EXS-016** — Kill Switch
- **REQ-EXS-017** — Cancel-All
- **REQ-EXS-018** — Disable-Execution Mode
- **REQ-EXS-019** — Human Override
- **REQ-EXS-020** — Safe Recovery
- **REQ-EXS-021** — Object Discipline
- **REQ-EXS-022** — Operational Boundary
- **REQ-EXS-023** — Replayability and Auditability
- **REQ-EXS-024** — Implementation Independence

---

### Future Dependencies

Referenced by:

* broker adapters and venue integration modules (implementation)
* operational and reconciliation subsystems
* the cognitive layers, via returned Observations

Provides:

* at-most-once actuation and idempotency
* the indeterminate Order state and its resolution
* stale-action revalidation
* confirmation-to-preview binding
* the single actuation chokepoint
* full-chain reconciliation
* cancel / replace / modify operations
* partial-fill and expiration handling
* emergency controls and safe recovery

---

### Cross References

- **Conforms To:** EIOS-000; EIOS-001; EIOS-002; EIOS-003; EIOS-004; EIOS-005; EIOS-006; EIOS-007; EIOS-008; EIOS-009; EIOS-010; EIOS-011; EIOS-012; EIOS-013; EIOS-014; GEN-001; PROM-001; PROM-002; CIO-001; EXEC-001
- **Builds Upon:** Execution (EXEC-001); Order (EXEC-001); Actuation Gate (EXEC-001); Order Preview (EXEC-001); User Confirmation Record (EXEC-001); Investment Action (PROM-002); Decision (EIOS-002); Observation (EIOS-002)
- **Defines:** Operational Integrity; At-Most-Once Actuation; the Indeterminate Order State; Stale-Action Revalidation; Confirmation-to-Preview Binding; the Single Actuation Chokepoint; Full-Chain Reconciliation; Cancel / Replace / Modify operations; Multi-Fill Completion; Order Expiration; Emergency Controls
- **Referenced By:** broker adapters and venue integration modules (implementation), operational and reconciliation subsystems, and the cognitive layers via returned Observations
