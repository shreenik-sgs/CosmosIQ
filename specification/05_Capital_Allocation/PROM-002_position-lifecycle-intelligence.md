---
generated: true
do_not_edit: true
canonical_source: architecture/EIOS_Architecture_Book.md
chapter: PROM-002
slug: position-lifecycle-intelligence
book_version: 9.0
generator_version: 1.1
source_hash: e416340f78f2a32bb6c5a9bb7b9685ae14ccb21632f09116c671e0aca45f57fd
generated_at: 2026-06-30T11:09:16-05:00
---

# PROM-002 — Position Lifecycle Intelligence

**Chapter Class:** Capital Allocation

### Purpose

Position Lifecycle Intelligence governs the life of an investment after a thesis is formed — every decision to enter, hold, add, trim, exit, avoid, wait, or rotate.

PROM-001 determines whether and how to invest; PROM-002 determines what to do about that investment as reality changes.

A system that can enter but cannot exit or rotate is incomplete for the mission; this chapter closes that gap.

The objective is a complete, justified, auditable lifecycle for every position — never only its opening.

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

This chapter additionally conforms to ADR-0008 and ADR-0009.

---

### Position in the Architecture

Position Lifecycle Intelligence is part of the Capital Allocation layer and extends Prometheus (PROM-001).

Genesis detects how opportunities evolve; Prometheus decides how investments should respond; Personal CIO personalizes that response; Execution later carries it out.

PROM-002 recommends Investment Actions over the life of a position. It SHALL NOT execute them, and SHALL NOT perform holistic portfolio construction, which belongs to a later chapter (PROM-005).

---

### The Position Lifecycle

A position has a life: it is entered, maintained, adjusted, and eventually closed or rotated.

PROM-002 SHALL govern the full lifecycle of a position, not only its opening.

Every transition in a position's life SHALL be a justified, recorded Investment Action.

---

### Investment Action

An Investment Action is a recommended decision about a position.

An Investment Action SHALL be a typed Prometheus Decision Record — a Decision (EIOS-002) — and PROM-002 SHALL introduce no new canonical object.

The type of an Investment Action SHALL be one of: enter, hold, add, trim, exit, avoid, wait, or rotate.

Every Investment Action SHALL be explicit and justified; none SHALL be implicit.

---

### The Investment Actions

#### Enter

Enter opens a position in response to an investable Investment Thesis, at the size and timing Prometheus recommends.

#### Hold

Hold maintains a position unchanged. Hold is a justified Investment Action, not the absence of action: it SHALL be recommended and recorded with the reasoning that the thesis continues to hold and no exit or adjustment trigger has fired.

#### Add

Add increases a position when the thesis strengthens, conviction rises, or timing favors deploying further capital.

#### Trim

Trim reduces a position without closing it — for risk management, partial valuation exhaustion, or approach to a position limit.

#### Exit

Exit closes a position. Exit SHALL be supported for every exit trigger named below.

#### Avoid

Avoid declines to open a position in an otherwise investable opportunity — for constraint, insufficient conviction, or a superior alternative. Avoid SHALL be recorded with its reasoning, so that the road not taken remains auditable.

#### Wait

Wait defers action on a valid thesis whose timing is not yet right, pending a condition or trigger.

#### Rotate

Rotate exits one position and enters another because the new opportunity is now superior to continuing to hold the old one.

---

### Exit Triggers

Prometheus SHALL support exit recommendations driven by, at least:

* stop loss
* thesis invalidation
* opportunity maturation
* valuation exhaustion
* risk/reward deterioration
* superior opportunity emergence
* bubble / hype-cycle risk
* technical deterioration
* capital rotation

Each exit SHALL record which trigger fired and the grounding that established it.

---

### Rotation

Rotation is a pairwise lifecycle action: exit position A and enter position B because B is now superior to continuing to hold A.

PROM-002 SHALL ground rotation in the comparative ranking of the held opportunity against the candidate — using Opportunity Prioritization and the Prometheus assessments — considering opportunity aging, forward-return decay, conviction decay, and thesis supersession.

PROM-002 SHALL NOT perform holistic, portfolio-wide optimization — full-book sizing, correlation budget, and capital-efficiency optimization — which belongs to a later chapter (PROM-005).

---

### Position State

Position State is the current state of a position — entered, held, adding, trimming, exiting, exited, avoided, or waiting.

Position State SHALL be a derived view, reconstructed from the history of Investment Actions and the live Investment Thesis; PROM-002 SHALL NOT store it as a new object.

---

### Grounding and Justification

Every Investment Action SHALL be grounded and justified, binding:

* the original Opportunity version
* the original Investment Thesis
* the updated Opportunity state
* the updated Prometheus assessment
* the changed risk and reward
* the changed valuation evidence
* the changed portfolio context
* the changed personal constraints, where applicable

An Investment Action SHALL never be recommended without the grounding that justifies it.

---

### Replayability and Auditability

Every Investment Action SHALL be replayable and auditable.

Each SHALL bind the versions of opportunity, thesis, and assessment it was formed against, so that the action — and the position's entire history — can be reconstructed exactly.

Prior Investment Actions SHALL be preserved; the lifecycle SHALL never be rewritten.

---

### Boundary

Genesis detects Opportunity evolution; it SHALL NOT recommend exit, trim, or rotation.

Prometheus SHALL recommend Investment Actions; it SHALL NOT execute them, and SHALL NOT perform holistic portfolio construction in this chapter.

Personal CIO SHALL personalize Investment Actions; it SHALL NOT originate lifecycle logic.

Execution SHALL later actuate Investment Actions; it SHALL form none of them.

---

### Handoff

PROM-002 SHALL provide Investment Actions, with their grounding and justification, to Personal CIO for personalization and onward to execution subsystems.

Prometheus SHALL recommend the action; personalizing and acting upon it belong to consumers beyond this chapter.

---

### Architectural Rules

- **AR-1801** — Position Lifecycle Intelligence SHALL govern the full lifecycle of a position — enter, hold, add, trim, exit, avoid, wait, rotate — and SHALL NOT limit Prometheus to entry and allocation.
- **AR-1802** — Every position transition SHALL be a justified, recorded Investment Action; none SHALL be implicit.
- **AR-1803** — An Investment Action SHALL be a typed Prometheus Decision Record — a Decision (EIOS-002); PROM-002 SHALL introduce no new canonical object.
- **AR-1804** — The type of an Investment Action SHALL be one of enter, hold, add, trim, exit, avoid, wait, or rotate.
- **AR-1805** — Hold SHALL be a justified Investment Action, recorded with its reasoning; it SHALL NEVER be treated as the absence of action.
- **AR-1806** — Avoid and Wait SHALL each be recorded with their reasoning, so that positions not opened and actions deferred remain auditable.
- **AR-1807** — Exit SHALL be supported for, at least, stop loss, thesis invalidation, opportunity maturation, valuation exhaustion, risk/reward deterioration, superior opportunity emergence, bubble/hype-cycle risk, technical deterioration, and capital rotation; each exit SHALL record the trigger that fired.
- **AR-1808** — Rotation SHALL be a pairwise lifecycle action — exit A, enter B because B is superior to holding A — grounded in comparative ranking, opportunity aging, forward-return decay, conviction decay, and thesis supersession.
- **AR-1809** — PROM-002 SHALL NOT perform holistic, portfolio-wide optimization (full-book sizing, correlation budget, capital-efficiency optimization); that belongs to PROM-005.
- **AR-1810** — Position State SHALL be a derived view reconstructed from the Investment Action history and the live Investment Thesis; it SHALL NOT be stored as a new object.
- **AR-1811** — Every Investment Action SHALL bind its grounding — original Opportunity version, original Investment Thesis, updated Opportunity state, updated Prometheus assessment, changed risk and reward, changed valuation evidence, changed portfolio context, and changed personal constraints where applicable — and SHALL never be recommended without it.
- **AR-1812** — Every Investment Action SHALL be replayable and auditable; prior actions SHALL be preserved and the lifecycle SHALL never be rewritten.
- **AR-1813** — PROM-002 SHALL consume Genesis Opportunity evolution and PROM-001 assessments by version, reading them without mutating them.
- **AR-1814** — Genesis SHALL NOT recommend exit, trim, or rotation; Opportunity evolution is a signal, not an Investment Action.
- **AR-1815** — Prometheus SHALL recommend Investment Actions and SHALL NOT execute them.
- **AR-1816** — Personal CIO SHALL personalize Investment Actions and SHALL NOT originate lifecycle logic; Execution SHALL actuate Investment Actions and SHALL form none of them.
- **AR-1817** — Position Lifecycle Intelligence SHALL remain implementation independent.

---

### Requirements Introduced

- **REQ-PL-001** — Position Lifecycle
- **REQ-PL-002** — Investment Action
- **REQ-PL-003** — Enter
- **REQ-PL-004** — Hold
- **REQ-PL-005** — Add
- **REQ-PL-006** — Trim
- **REQ-PL-007** — Exit
- **REQ-PL-008** — Avoid
- **REQ-PL-009** — Wait
- **REQ-PL-010** — Rotate
- **REQ-PL-011** — Exit Triggers
- **REQ-PL-012** — Rotation Scope
- **REQ-PL-013** — Position State
- **REQ-PL-014** — Grounding and Justification
- **REQ-PL-015** — Replayability and Auditability
- **REQ-PL-016** — Lifecycle Boundary
- **REQ-PL-017** — Implementation Independence

---

### Future Dependencies

Referenced by:

* Personal CIO
* execution and operational subsystems
* the future portfolio-construction chapter (PROM-005)

Provides:

* Investment Actions — enter, hold, add, trim, exit, avoid, wait, rotate
* Position State (derived)
* exit-trigger recommendations
* pairwise rotation recommendations

---

### Cross References

- **Conforms To:** EIOS-000; EIOS-001; EIOS-002; EIOS-003; EIOS-004; EIOS-005; EIOS-006; EIOS-007; EIOS-008; EIOS-009; EIOS-010; EIOS-011; EIOS-012; EIOS-013; EIOS-014; GEN-001; PROM-001
- **Builds Upon:** Prometheus (PROM-001); Investment Thesis (PROM-001); Capital Allocation Recommendation (PROM-001); Timing-to-Action Assessment (PROM-001); Prometheus Decision Record (PROM-001); Decision (EIOS-002); Opportunity (EIOS-002); Opportunity Evolution (GEN-001); Opportunity Prioritization (GEN-001)
- **Defines:** Position Lifecycle; Investment Action; Position State; Enter; Hold; Add; Trim; Exit; Avoid; Wait; Rotate; Exit Triggers; pairwise Rotation
- **Referenced By:** Personal CIO (CIO-001), execution and operational subsystems, and the future portfolio-construction chapter (PROM-005)
