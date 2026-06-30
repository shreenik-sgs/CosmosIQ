---
generated: true
do_not_edit: true
canonical_source: architecture/EIOS_Architecture_Book.md
chapter: EXEC-001
slug: execution-engine
book_version: 9.1
generator_version: 1.1
source_hash: a28bdb4f6807ec3fa5d2ddabd2b9b703f59aa80a9486aeb29f42599108cd9ce7
generated_at: 2026-06-30T11:21:33-05:00
---

# EXEC-001 — Execution Engine

**Chapter Class:** Execution

### Purpose

Execution carries out, in the world, the actions the cognitive layers have already decided.

Execution is the actuation layer — the system's single, narrow, gated aperture onto the world.

Where every layer before it reasons, recommends, or personalizes — all reversible — Execution acts, and action cannot be undone.

The objective is faithful, gated, fully auditable actuation: the system does only what it was told to do, only after it is allowed to, and remembers exactly what it did.

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

This chapter additionally conforms to ADR-0008, ADR-0009, and ADR-0010.

---

### Position in the Architecture

The architecture reasons, then judges, then decides, then personalizes — and only then acts.

Genesis identifies opportunities; Prometheus forms Investment Actions; Personal CIO personalizes and queues them; Execution actuates the approved ones.

Execution is the layer of Actuation, governed by ADR-0010 — the Cognition–Actuation Boundary.

It is the first operational layer and the first to touch the world. Cognition is reversible; actuation is not — and so actuation alone is gated.

Execution carries its own identifier namespace (EXEC) to make this boundary visible: it is where thought ends and deed begins.

---

### Execution

Execution is the actuation engine.

Execution SHALL carry out approved Investment Actions in the world, and SHALL do nothing else.

Execution performs operational validation, not investment reasoning. It MAY validate account constraints, market-hours constraints, cancelability, order previews, slippage and fill risk, reconciliation, and kill-switch conditions. It SHALL NOT discover, understand, identify opportunities, construct theses, allocate capital, personalize counsel, or decide actions.

---

### The Cognition-to-Actuation Boundary

Execution SHALL consume the decisions handed to it and SHALL originate none of them.

Execution SHALL receive the verdict; it SHALL NEVER reach it.

No reasoning, judgment, or purpose SHALL be formed in Execution, and nothing operational SHALL flow upward as purpose.

The boundary is the one this chapter exists to enforce: the system thinks freely and acts only narrowly.

---

### The Consumption Contract

Execution SHALL consume, from Personal CIO:

* the Personalized Action Queue
* the Investment Actions it contains
* the Personal CIO Decision Records and Prometheus Decision Records that justify them
* the security and instrument mapping, allocation amount, and timing-to-action carried with each
* the user's confirmation state

Execution SHALL consume these by version, reading them and never mutating them.

Every operational record Execution produces SHALL bind the versions it acted upon, so that the deed remains traceable to the decision that authorized it.

---

### The Order

The Order is the canonical object of this layer, and the first operational object of the architecture.

An Order is the durable record of an actuated Investment Action and the state of that action in the world.

Per ADR-0010, the Order SHALL be an operational object — not a reasoning object, and not a specialized Knowledge Object. Its justification lives upstream in the Investment Action it carries out; its state is operational and its own.

The Order SHALL represent what the system is doing, not what it believes; its truth is fact, not warrant — whether it happened, not whether it is justified.

---

### Operational Objects and Reasoning Objects

The object model has, until now, held only reasoning objects — the Knowledge Object and its kin, the Intelligence Assessment, the Opportunity, the Investment Thesis, the Personal Investment Profile — each representing what is known, judged, or recommended.

The Order is the first operational object: a record of what is done.

The Observation bridges the two. When the world answers an Order — a fill, a rejection — that answer re-enters the system as an Observation, a reasoning object once more, to be understood like any other evidence.

---

### The Order Lifecycle

An Order SHALL carry an operational lifecycle: intent, preview, submitted, partially filled, filled, rejected, cancelled.

Every transition in an Order's lifecycle SHALL be recorded and replayable.

Position State (PROM-002) SHALL reflect the outcome of Orders, reconciled from the fills they produce.

---

### Execution Plan

Execution SHALL form an Execution Plan describing how an approved Investment Action will be actuated — order type, routing, and timing.

The Execution Plan SHALL describe how to act without altering what was decided.

---

### Order Intent

Order Intent is the intended order, formed from the approved Investment Action, before any submission to the world.

Order Intent SHALL preserve a faithful link to the Investment Action it actuates.

---

### Order Preview

Execution SHALL produce an Order Preview before any submission.

The Order Preview SHALL present the intended order and its estimated impact, including slippage and fill risk, so that the action can be reviewed before it becomes irreversible.

---

### The Actuation Gate

No actuation SHALL touch the world until it has passed the Actuation Gate.

The Actuation Gate SHALL require:

* confirmation by the responsible authority
* an order preview
* a check that the action can still be cancelled or reversed while that remains possible
* checks against account and venue constraints
* a check that the moment is permitted (market-hours)
* awareness of slippage and fill risk
* the standing power to halt everything at once (kill switch)
* a record sufficient to account for the action afterward

The Actuation Gate is not a feature of actuation; it is its precondition. A system that cannot confirm, preview, reverse, or halt SHALL NOT act.

---

### User Confirmation

Execution SHALL require user confirmation before any irreversible action, and SHALL record it as a User Confirmation Record.

The User Confirmation Record SHALL be a Decision (EIOS-002); Execution SHALL NOT introduce a new object for it.

An unconfirmed action SHALL NOT be actuated.

---

### Executed Order Record

When an Order is submitted, Execution SHALL preserve an Executed Order Record binding the Order, the approved Investment Action, the confirmation, and the grounding versions.

The Executed Order Record SHALL be complete enough to reconstruct and audit the actuation exactly.

---

### Fill Record

A Fill Record is the world's answer to an Order — the price, quantity, and time at which it was filled.

A Fill Record SHALL be an Observation (EIOS-002) of reality; Execution SHALL NOT introduce a new object for it.

Fill Records MAY flow upward as evidence; they SHALL NEVER flow upward as purpose.

---

### Position Reconciliation

Execution SHALL reconcile intended positions against actual positions established by fills.

Position Reconciliation SHALL surface any divergence between what was decided and what occurred, and SHALL feed the reconciled truth back as Observation.

---

### Exception and Failure

Rejections, cancellations, partial fills, timeouts, and operational failures SHALL be recorded as Exception and Failure Records.

Exception and Failure Records SHALL be Observations (EIOS-002) of reality.

No failure SHALL be silently discarded; every one SHALL be preserved and auditable.

---

### Kill Switch

Execution SHALL provide a kill switch — the standing power to halt all actuation at once.

The kill switch SHALL be available independent of any single action, and its use SHALL itself be recorded.

---

### Operational Reality Flows Up as Observation

Everything the world returns — fills, rejections, cancellations, exceptions, failures, and reconciliation — SHALL be treated as Observation of reality.

These Observations MAY flow upward as evidence, to inform understanding like any other observation.

They SHALL NEVER flow upward as purpose. The world may inform the system; it may not instruct it.

---

### Broker Agnosticism

Execution SHALL define execution governance and operational state in the abstract — what a gate is, what an Order's life consists of, what must be reconciled.

Execution SHALL remain broker-agnostic. Broker-specific logic — the particular venues through which action reaches the world — SHALL be implementation, bound to the architecture at its edge and never written into it.

Execution SHALL NOT become specific to any one broker, venue, or account provider.

---

### Replayability and Auditability

Every Order, Execution Plan, confirmation, fill, exception, and reconciliation SHALL be replayable and auditable.

Each SHALL bind the Investment Action and upstream grounding it acted upon, so that the deed can be reconstructed exactly as it occurred.

Prior operational records SHALL be preserved; the operational history SHALL never be rewritten.

---

### What Execution Is Not

Execution is not an understanding engine, an intelligence engine, an opportunity engine, a capital-allocation engine, or a personalization engine.

Execution SHALL form no understanding, opportunity, thesis, allocation, personalization, or action, and SHALL NOT rewrite or override any of them.

Execution SHALL only actuate what has been decided and approved; it SHALL carry no intelligence of its own.

---

### Handoff

Execution SHALL return Observations — fills, rejections, exceptions, failures, and reconciliation — to the cognitive layers as evidence.

Execution SHALL hand the operational truth of the world back to understanding; it SHALL NEVER hand it back as instruction.

---

### Architectural Rules

- **AR-1901** — Execution SHALL carry out approved Investment Actions in the world and do nothing else; it performs operational validation, not investment reasoning, and SHALL NOT discover, understand, identify opportunities, construct theses, allocate capital, personalize counsel, or decide actions.
- **AR-1902** — Execution SHALL consume the decisions handed to it — the Personalized Action Queue, Investment Actions, Personal CIO Decision Records, and Prometheus Decision Records — and SHALL originate none of them.
- **AR-1903** — Execution SHALL consume its inputs by version and SHALL read them without ever mutating them.
- **AR-1904** — The Order SHALL be the first operational object, distinct from the reasoning objects, and SHALL NOT be modeled as a specialized Knowledge Object (ADR-0010).
- **AR-1905** — Operational objects SHALL represent what is done; reasoning objects represent what is known or judged; the Observation SHALL bridge operational reality back into reasoning.
- **AR-1906** — An Order SHALL carry an operational lifecycle — intent, preview, submitted, partially filled, filled, rejected, cancelled — and every transition SHALL be recorded and replayable.
- **AR-1907** — No actuation SHALL touch the world until it has passed the Actuation Gate.
- **AR-1908** — The Actuation Gate SHALL require confirmation by the responsible authority, an order preview, a reversibility/cancelability check, account and venue constraint checks, a market-hours check, awareness of slippage and fill risk, kill-switch availability, and a complete audit record.
- **AR-1909** — A system that cannot confirm, preview, reverse, or halt an action SHALL NOT act.
- **AR-1910** — User confirmation SHALL be required before any irreversible action and SHALL be recorded as a User Confirmation Record, which SHALL be a Decision (EIOS-002); an unconfirmed action SHALL NOT be actuated.
- **AR-1911** — A Fill Record SHALL be an Observation (EIOS-002) of reality; Execution SHALL introduce no new object for it.
- **AR-1912** — Exception and Failure Records SHALL be Observations (EIOS-002); no failure SHALL be silently discarded.
- **AR-1913** — Operational reality — orders, fills, rejections, cancellations, exceptions, failures, reconciliation — MAY flow upward as evidence and SHALL NEVER flow upward as purpose.
- **AR-1914** — Execution SHALL reconcile intended against actual positions, surface any divergence, and feed the reconciled truth back as Observation.
- **AR-1915** — Execution SHALL provide a kill switch — the standing power to halt all actuation at once — available independent of any single action, and its use SHALL be recorded.
- **AR-1916** — The Order Preview SHALL present the intended order and its estimated impact, including slippage and fill risk, before any submission; the Execution Plan SHALL describe how to act without altering what was decided.
- **AR-1917** — Execution SHALL honor market-hours and venue constraints, queuing or declining actions that cannot be actuated within them.
- **AR-1918** — Broker-specific logic SHALL be implementation, not architecture; Execution SHALL define execution governance and operational state abstractly and SHALL remain broker-agnostic.
- **AR-1919** — Every Order, confirmation, fill, exception, and reconciliation SHALL be replayable and auditable, traceable to the Investment Action and its upstream grounding; operational history SHALL never be rewritten.
- **AR-1920** — Execution SHALL form no understanding, opportunity, thesis, allocation, personalization, or action, and SHALL carry no intelligence of its own.
- **AR-1921** — Execution SHALL remain implementation independent.

---

### Requirements Introduced

- **REQ-EXEC-001** — Execution
- **REQ-EXEC-002** — Cognition-to-Actuation Boundary
- **REQ-EXEC-003** — Consumption Contract
- **REQ-EXEC-004** — Order (operational object)
- **REQ-EXEC-005** — Operational and Reasoning Objects
- **REQ-EXEC-006** — Order Lifecycle
- **REQ-EXEC-007** — Execution Plan
- **REQ-EXEC-008** — Order Intent
- **REQ-EXEC-009** — Order Preview
- **REQ-EXEC-010** — Actuation Gate
- **REQ-EXEC-011** — User Confirmation
- **REQ-EXEC-012** — Executed Order Record
- **REQ-EXEC-013** — Fill Record
- **REQ-EXEC-014** — Position Reconciliation
- **REQ-EXEC-015** — Exception and Failure
- **REQ-EXEC-016** — Kill Switch
- **REQ-EXEC-017** — Operational Reality as Observation
- **REQ-EXEC-018** — Broker Agnosticism
- **REQ-EXEC-019** — Replayability and Auditability
- **REQ-EXEC-020** — Implementation Independence

---

### Future Dependencies

Referenced by:

* broker adapters and venue integration modules (implementation)
* portfolio management and operational subsystems
* the cognitive layers, which consume returned Observations as evidence

Provides:

* Orders and the Order lifecycle
* Execution Plans, Order Intents, and Order Previews
* the Actuation Gate
* User Confirmation Records, Executed Order Records, Fill Records
* Position Reconciliation
* Exception and Failure Records
* operational Observations fed back as evidence

---

### Cross References

- **Conforms To:** EIOS-000; EIOS-001; EIOS-002; EIOS-003; EIOS-004; EIOS-005; EIOS-006; EIOS-007; EIOS-008; EIOS-009; EIOS-010; EIOS-011; EIOS-012; EIOS-013; EIOS-014; GEN-001; PROM-001; PROM-002; CIO-001
- **Builds Upon:** Personal CIO (CIO-001); Personalized Action Queue (CIO-001); Personal CIO Decision Record (CIO-001); Investment Action (PROM-002); Prometheus Decision Record (PROM-001); Security and Instrument Mapping (PROM-001); Capital Allocation Recommendation (PROM-001); Timing-to-Action Assessment (PROM-001); Decision (EIOS-002); Observation (EIOS-002)
- **Defines:** Execution; Order; Operational Object; Order Lifecycle; Execution Plan; Order Intent; Order Preview; Actuation Gate; User Confirmation Record; Executed Order Record; Fill Record; Position Reconciliation; Exception and Failure Record; Kill Switch
- **Referenced By:** broker adapters and venue integration modules (implementation), portfolio management and operational subsystems, and the cognitive layers via returned Observations
