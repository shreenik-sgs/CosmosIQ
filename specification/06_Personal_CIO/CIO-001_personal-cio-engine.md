---
generated: true
do_not_edit: true
canonical_source: architecture/EIOS_Architecture_Book.md
chapter: CIO-001
slug: personal-cio-engine
book_version: 9.1
generator_version: 1.1
source_hash: a28bdb4f6807ec3fa5d2ddabd2b9b703f59aa80a9486aeb29f42599108cd9ce7
generated_at: 2026-06-30T11:21:33-05:00
---

# CIO-001 — Personal CIO Engine

**Chapter Class:** Personal CIO

### Purpose

Personal CIO adapts the investment outputs of Prometheus to the individual user.

Personal CIO is the consumer of Prometheus, not an extension of it.

Where Prometheus determines investability and capital allocation in general, Personal CIO makes those outputs personal — shaped by who the user is, what they want, and what constrains them.

The objective is investment guidance that is faithful to upstream reasoning and fitted to one person, without ever rewriting that reasoning.

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

The architecture forms understanding, then opportunity, then capital allocation, then personalization.

EIOS understands reality. Genesis identifies opportunities. Prometheus determines investability and capital allocation. Personal CIO adapts those outputs to the individual user.

Personal CIO is the layer of Personalization.

Personalization — objectives, constraints, preferences, and the voice in which guidance is given — legitimately begins here, and SHALL NEVER flow back down into Prometheus, Genesis, Reality Intelligence, or Scientific Understanding.

Personal CIO carries its own identifier namespace (CIO) to make this boundary visible: it is the consumer of capital allocation, fitted to one person.

---

### Personal CIO

Personal CIO is the personalization engine.

Personal CIO SHALL consume the outputs of Prometheus and adapt them to a single user's objectives, constraints, and preferences.

Personal CIO SHALL personalize; it SHALL NOT form understanding, opportunities, investability, or the general capital-allocation machinery.

Personal CIO is where the architecture, having reasoned in general, at last speaks to one person.

---

### The Prometheus-to-Personal-CIO Consumption Contract

Personal CIO SHALL consume from Prometheus:

* Investment Theses
* Investability Assessments
* Security and Instrument Mappings
* Valuation Evidence
* Risk and Reward Assessments
* Position Suitability
* Portfolio Fit Assessments
* Capital Allocation Recommendations
* Timing-to-Action Assessments
* Prometheus Decision Records

Personal CIO SHALL consume these by version.

Every Personal CIO output SHALL bind the Prometheus, opportunity, and understanding versions it was formed against, so that it remains replayable, explainable, and auditable.

Personal CIO SHALL read Prometheus outputs and SHALL NEVER mutate them.

When Prometheus updates a thesis, recommendation, or decision record, every Personal CIO output grounded upon it SHALL be re-evaluated.

---

### Personalization, Not Reconstruction

Personal CIO SHALL apply user-specific constraints and preferences to Prometheus outputs; it SHALL NOT redefine the general capital-allocation machinery.

Holistic portfolio construction — sizing logic, correlation budget, rebalancing, and full position-set optimization — belongs to Prometheus, and SHALL NOT be performed by Personal CIO.

Personal CIO SHALL consume and adapt upstream understanding, opportunity, and allocation; it SHALL NEVER rewrite, restate, or redefine them.

Where an upstream output is uncertain, the personalized view built upon it SHALL inherit that uncertainty rather than conceal it.

---

### Personal Investment Profile

The Personal Investment Profile is the canonical object of this layer.

The Personal Investment Profile captures who the user is for the purpose of investment: objectives, risk tolerance, liquidity needs, tax constraints, time horizon, account structure, existing holdings, position limits, preferences and exclusions, communication style, and action prioritization.

The Personal Investment Profile SHALL be a specialized Knowledge Object conforming to the canonical structure defined by the Knowledge Model (EIOS-002); it SHALL reference, and SHALL NOT redefine, existing canonical objects.

The Personal Investment Profile SHALL be versioned, and every personalization SHALL bind the profile version it was formed against.

---

### Personalized Thesis View

Personal CIO SHALL produce a Personalized Thesis View.

The Personalized Thesis View SHALL present Prometheus Investment Theses filtered and framed for the user — honoring exclusions, preferences, and suitability — without altering the underlying theses.

The Personalized Thesis View SHALL preserve a faithful link to the Prometheus Investment Theses it presents.

---

### Personalized Allocation View

Personal CIO SHALL produce a Personalized Allocation View.

The Personalized Allocation View SHALL apply the user's account structure, existing holdings, position limits, and exclusions to Prometheus Capital Allocation Recommendations.

The Personalized Allocation View SHALL apply constraints to recommendations; it SHALL NOT reconstruct the portfolio or re-derive allocation, which remain Prometheus's responsibility.

---

### Personalized Risk View

Personal CIO SHALL produce a Personalized Risk View.

The Personalized Risk View SHALL express Prometheus Risk and Reward Assessments relative to the user's risk tolerance, liquidity needs, and time horizon.

The Personalized Risk View SHALL preserve upstream uncertainty and SHALL NOT understate downside to suit preference.

---

### Personalized Action Queue

Personal CIO SHALL produce a Personalized Action Queue.

The Personalized Action Queue SHALL order the actions available to the user according to the user's action prioritization and the upstream Timing-to-Action Assessments.

The Personalized Action Queue SHALL present actions for the user to take; Personal CIO SHALL NOT execute them.

---

### Personalized Explanation

Personal CIO SHALL produce Personalized Explanations.

A Personalized Explanation SHALL render the upstream reasoning in the user's communication style, at the depth the user prefers.

A Personalized Explanation SHALL remain faithful to the upstream reasoning; personalization of voice SHALL NEVER alter substance.

---

### Personal CIO Decision Record

Every Personal CIO recommendation to a user SHALL be recorded in a Personal CIO Decision Record.

The Personal CIO Decision Record is a Decision (EIOS-002); Personal CIO SHALL NOT introduce a new object for it.

The Personal CIO Decision Record SHALL preserve the Personal Investment Profile version, the grounding Prometheus outputs and their versions, what was presented to the user, and the rationale — complete enough to reconstruct and audit the personalization exactly.

---

### Personalization Evolution

Personalized outputs SHALL evolve as their grounding evolves.

When Prometheus updates an upstream output, or when the Personal Investment Profile changes, every affected Personal CIO output SHALL be re-evaluated.

Personal CIO SHALL preserve the complete evolution of its personalized outputs rather than discard it.

No Personal CIO output SHALL silently retain a superseded grounding or a superseded profile.

---

### Replayability and Auditability

Every Personalized View, Action Queue, Explanation, and Personal CIO Decision Record SHALL be replayable and auditable.

Each SHALL bind the versions of profile, Prometheus output, opportunity, and understanding it was formed against, so that the personalization can be reconstructed exactly as it was made.

Prior versions SHALL be preserved and SHALL remain replayable.

---

### What Personal CIO Is Not

Personal CIO is not an understanding engine, an opportunity engine, a capital-allocation engine, or a portfolio-construction engine.

Personal CIO SHALL NOT form understanding, opportunities, investability, theses, valuations, or portfolio construction, and SHALL NOT rewrite or override any of them.

Personal CIO presents personalized guidance; it SHALL NOT execute trades, place orders, or operate live positions.

Execution and operation are the responsibility of consumers beyond this layer.

---

### Handoff

Personal CIO SHALL provide Personalized Views, the Personalized Action Queue, Personalized Explanations, and Personal CIO Decision Records to the user and to downstream execution and operational subsystems.

Personal CIO SHALL present and recommend; acting upon its guidance is the responsibility of the user and of consumers beyond this layer.

---

### Architectural Rules

- **AR-1701** — Personal CIO SHALL consume Prometheus outputs and adapt them to a single user's objectives, constraints, and preferences; it SHALL NOT form understanding, opportunities, investability, or the general capital-allocation machinery.
- **AR-1702** — Personalization SHALL begin at Personal CIO and SHALL NEVER flow downward into Prometheus, Genesis, Reality Intelligence, or Scientific Understanding.
- **AR-1703** — Personal CIO SHALL consume all ten Prometheus outputs by version and SHALL read them without ever mutating them.
- **AR-1704** — Every Personal CIO output SHALL be replayable, explainable, and auditable, binding the profile, Prometheus, opportunity, and understanding versions it was formed against.
- **AR-1705** — When Prometheus updates a thesis, recommendation, or decision record, or when the Personal Investment Profile changes, every affected Personal CIO output SHALL be re-evaluated; none SHALL silently retain a superseded grounding or profile.
- **AR-1706** — Personal CIO SHALL apply user-specific constraints and preferences to Prometheus outputs and SHALL NOT redefine the general capital-allocation machinery.
- **AR-1707** — Holistic portfolio construction — sizing logic, correlation budget, rebalancing, and full position-set optimization — SHALL belong to Prometheus and SHALL NOT be performed by Personal CIO.
- **AR-1708** — Personal CIO SHALL consume and adapt upstream understanding, opportunity, and allocation and SHALL NEVER rewrite, restate, or redefine them.
- **AR-1709** — The Personal Investment Profile SHALL be a specialized Knowledge Object conforming to the canonical structure defined by the Knowledge Model; it SHALL reference, and SHALL NOT redefine, existing canonical objects, and it SHALL be the only new canonical object introduced by Personal CIO.
- **AR-1710** — The Personal Investment Profile SHALL be versioned, and every personalization SHALL bind the profile version it was formed against.
- **AR-1711** — The Personalized Thesis View SHALL present Prometheus Investment Theses filtered and framed for the user without altering the underlying theses, preserving a faithful link to them.
- **AR-1712** — The Personalized Allocation View SHALL apply the user's account structure, holdings, position limits, and exclusions to Capital Allocation Recommendations, and SHALL NOT reconstruct the portfolio or re-derive allocation.
- **AR-1713** — The Personalized Risk View SHALL express Risk and Reward relative to the user's tolerance, liquidity, and horizon, preserving upstream uncertainty and never understating downside to suit preference.
- **AR-1714** — The Personalized Action Queue SHALL order available actions by the user's prioritization and upstream Timing-to-Action, and SHALL NOT execute them.
- **AR-1715** — Personalized Explanations SHALL render upstream reasoning in the user's communication style and preferred depth, and SHALL NEVER alter substance.
- **AR-1716** — Every Personal CIO recommendation SHALL be recorded in a Personal CIO Decision Record, which SHALL be a Decision (EIOS-002), preserving the profile version, grounding Prometheus outputs and versions, what was presented, and the rationale, complete enough to reconstruct and audit the personalization exactly.
- **AR-1717** — Personal CIO presented outputs SHALL be replayable and auditable, with prior versions preserved.
- **AR-1718** — Personal CIO SHALL present and recommend and SHALL NOT execute trades, place orders, or operate live positions; execution belongs to consumers beyond this layer.
- **AR-1719** — Personal CIO SHALL remain implementation independent.

---

### Requirements Introduced

- **REQ-CIO-001** — Personal CIO
- **REQ-CIO-002** — Prometheus-to-Personal-CIO Consumption Contract
- **REQ-CIO-003** — Personalization, Not Reconstruction
- **REQ-CIO-004** — Personal Investment Profile
- **REQ-CIO-005** — Personalized Thesis View
- **REQ-CIO-006** — Personalized Allocation View
- **REQ-CIO-007** — Personalized Risk View
- **REQ-CIO-008** — Personalized Action Queue
- **REQ-CIO-009** — Personalized Explanation
- **REQ-CIO-010** — Personal CIO Decision Record
- **REQ-CIO-011** — Personalization Evolution
- **REQ-CIO-012** — Replayability and Auditability
- **REQ-CIO-013** — Personalization Boundary
- **REQ-CIO-014** — Handoff to Execution
- **REQ-CIO-015** — Implementation Independence

---

### Future Dependencies

Referenced by:

* the user
* execution and operational subsystems
* portfolio management subsystems

Provides:

* Personal Investment Profile
* Personalized Thesis View
* Personalized Allocation View
* Personalized Risk View
* Personalized Action Queue
* Personalized Explanation
* Personal CIO Decision Record

---

### Cross References

- **Conforms To:** EIOS-000; EIOS-001; EIOS-002; EIOS-003; EIOS-004; EIOS-005; EIOS-006; EIOS-007; EIOS-008; EIOS-009; EIOS-010; EIOS-011; EIOS-012; EIOS-013; EIOS-014; GEN-001; PROM-001
- **Builds Upon:** Prometheus (PROM-001); Investment Thesis (PROM-001); Capital Allocation Recommendation (PROM-001); Prometheus Decision Record (PROM-001); Decision (EIOS-002); Genesis (GEN-001); Reality Intelligence (EIOS-010)
- **Defines:** Personal CIO; Prometheus-to-Personal-CIO Consumption Contract; Personal Investment Profile; Personalized Thesis View; Personalized Allocation View; Personalized Risk View; Personalized Action Queue; Personalized Explanation; Personal CIO Decision Record; Personalization Evolution
- **Referenced By:** the user, execution and operational subsystems, portfolio management subsystems, and downstream consumers
