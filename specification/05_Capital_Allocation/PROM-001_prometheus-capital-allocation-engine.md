---
generated: true
do_not_edit: true
canonical_source: architecture/EIOS_Architecture_Book.md
chapter: PROM-001
slug: prometheus-capital-allocation-engine
book_version: 7.0
generator_version: 1.1
source_hash: f1c04395f7d4b05211dc15cb7eed14fb8d84ff7f26e7e1cb79ca993299ae24c1
generated_at: 2026-06-30T10:08:04-05:00
---

# PROM-001 — Prometheus Capital Allocation Engine

**Chapter Class:** Capital Allocation

### Purpose

Prometheus decides whether, how, when, and through what instruments to invest in the opportunities Genesis discovers.

Prometheus is the consumer of Genesis, not an extension of it.

Where Genesis discovers what is worth pursuing, Prometheus determines what to do about it.

The objective is sound, evidence-grounded, fully auditable capital allocation — the point at which understanding, at last, becomes action.

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

This chapter additionally conforms to ADR-0008 and ADR-0009.

---

### Position in the Architecture

The architecture orders cognition as understanding, then judgment, then action.

Scientific Understanding and Domain Intelligence form understanding. Genesis forms judgment — what is worth pursuing. Prometheus forms action — whether and how to invest.

Prometheus is the layer of Capital Allocation.

Investment semantics — investability, valuation, securities, allocation — legitimately begin here, and SHALL NEVER flow back down into Genesis, Reality Intelligence, or Scientific Understanding.

Prometheus carries its own identifier namespace (PROM) to make this boundary visible: it is the consumer of opportunity, not a producer of understanding.

---

### Prometheus

Prometheus is the capital allocation engine.

Prometheus SHALL consume the opportunities Genesis discovers and determine how capital should respond to them.

Prometheus SHALL evaluate opportunities for investment; it SHALL NOT form opportunities, intelligence, or understanding.

Prometheus is where the architecture is permitted, for the first time, to ask not what is true or what is emerging, but what is worth doing with capital.

---

### The Genesis-to-Prometheus Consumption Contract

Prometheus SHALL consume from Genesis:

* Opportunity Hypotheses
* the Opportunity Portfolio
* Opportunity Relationships (the Opportunity Graph)
* Opportunity Evolution
* Opportunity Prioritization

Prometheus SHALL consume these by version.

Every Prometheus output SHALL bind the Opportunity and underlying understanding versions it was formed against, so that it remains:

* replayable — reconstructable from its pinned grounding
* explainable — its reasoning recoverable from that grounding
* auditable — every decision preserved with its complete justification

Prometheus SHALL read Genesis outputs and SHALL NEVER mutate them.

When an Opportunity evolves, every Investment Thesis grounded upon it SHALL be re-evaluated.

---

### The Opportunity-to-Investment Boundary

Genesis says what is worth pursuing; Prometheus says whether, how, when, and through what instruments to invest.

Prometheus SHALL consume and evaluate upstream understanding and opportunity; it SHALL NEVER rewrite, restate, or redefine them.

Prometheus SHALL NEVER push investment purpose downward into Genesis, Reality Intelligence, or Scientific Understanding.

Where an Opportunity is uncertain, the Investment Thesis built upon it SHALL inherit that uncertainty rather than conceal it.

---

### Investability Assessment

Prometheus SHALL assess whether an Opportunity is investable.

Investability Assessment SHALL determine whether an Opportunity can be acted upon with capital at all, before any thesis is constructed.

Not every Opportunity worth pursuing is investable; Investability Assessment SHALL preserve that distinction explicitly.

---

### Investment Thesis

The Investment Thesis is the canonical object of this layer.

An Investment Thesis is the reasoned case for whether, how, when, and through what instruments to invest in an Opportunity.

The Investment Thesis SHALL be a specialized Knowledge Object conforming to the canonical structure defined by the Knowledge Model (EIOS-002); it SHALL reference, and SHALL NOT redefine, existing canonical objects.

Every Investment Thesis SHALL bind the Opportunity version it addresses and preserve its grounding, confidence, and uncertainty.

Multiple competing Investment Theses MAY coexist for the same Opportunity and SHALL be preserved until evidence supports adjudication.

---

### Security and Instrument Mapping

Prometheus SHALL map Opportunities to the securities and instruments through which they may be expressed.

Security and Instrument Mapping SHALL preserve the relationship between an Opportunity and every instrument that expresses it, and SHALL preserve alternatives.

Mapping SHALL remain explainable and revisable.

---

### Valuation Evidence

Prometheus SHALL gather and preserve valuation evidence for every Investment Thesis.

Valuation Evidence SHALL be grounded, provenanced, and uncertainty-preserving.

No valuation SHALL be asserted as certain, and no Investment Thesis SHALL rest on a single valuation.

---

### Risk and Reward Assessment

Prometheus SHALL assess the risk and reward of every Investment Thesis.

Risk and Reward Assessment SHALL preserve explicit uncertainty, downside, and the conditions under which the thesis fails.

Reward SHALL never be expressed without its accompanying risk.

---

### Position Suitability

Prometheus SHALL assess the suitability of a position for the Investment Thesis it expresses.

Position Suitability SHALL consider scale, structure, liquidity, time horizon, and constraints.

Suitability SHALL remain distinct from portfolio fit.

---

### Portfolio Fit Assessment

Prometheus SHALL assess how an Investment Thesis fits within the broader set of positions.

Portfolio Fit Assessment SHALL consider concentration, correlation, diversification, and interaction with existing positions.

Portfolio Fit SHALL be assessed without rewriting any upstream understanding or opportunity.

---

### Capital Allocation Recommendation

Prometheus SHALL produce Capital Allocation Recommendations.

A Capital Allocation Recommendation SHALL express how much capital, in what structure, and under what conditions an Investment Thesis warrants.

A Capital Allocation Recommendation is a recommendation; Prometheus SHALL NOT execute it.

---

### Timing-to-Action Assessment

Prometheus SHALL assess the timing of action for every Investment Thesis.

Timing-to-Action Assessment SHALL ground in the opportunity timing and the readiness understanding produced upstream, and SHALL preserve uncertainty.

Timing-to-Action SHALL distinguish the timing of an opportunity from the timing of acting upon it.

---

### Prometheus Decision Record

Every Prometheus decision SHALL be recorded in a Prometheus Decision Record.

The Prometheus Decision Record is a Decision (EIOS-002); Prometheus SHALL NOT introduce a new object for it.

The Prometheus Decision Record SHALL preserve the Investment Thesis, the grounding Opportunity and understanding versions, the recommendation, the rationale, and the alternatives considered.

The Prometheus Decision Record SHALL be complete enough to reconstruct and audit the decision exactly.

---

### Investment Thesis Evolution

Investment Theses SHALL evolve as the opportunities and understanding beneath them evolve.

When an Opportunity is adjudicated, superseded, or overturned, every Investment Thesis grounded upon it SHALL be re-evaluated.

A thesis sound today MAY be invalidated tomorrow by a changed opportunity; Prometheus SHALL preserve the complete evolution rather than discard it.

No Investment Thesis SHALL silently retain a superseded grounding.

---

### Replayability and Auditability

Every Investment Thesis, Capital Allocation Recommendation, and Prometheus Decision Record SHALL be replayable and auditable.

Each SHALL bind the versions of opportunity and understanding it was formed against, so that the decision can be reconstructed exactly as it was made.

Prior versions SHALL be preserved and SHALL remain replayable.

---

### What Prometheus Is Not

Prometheus is not an understanding engine, an intelligence engine, or an opportunity engine.

Prometheus SHALL NOT form scientific understanding, domain intelligence, or opportunities, and SHALL NOT rewrite or override any of them.

Prometheus recommends capital allocation; it SHALL NOT execute trades, place orders, or operate live positions.

Execution and operation are the responsibility of consumers beyond this layer.

---

### Handoff

Prometheus SHALL provide Investment Theses, Capital Allocation Recommendations, and Prometheus Decision Records to downstream execution, operational, and human decision subsystems.

Prometheus SHALL recommend; acting upon its recommendations is the responsibility of consumers beyond this layer.

---

### Architectural Rules

- **AR-1601** — Prometheus SHALL consume the opportunities Genesis discovers and determine how capital should respond; it SHALL NOT form scientific understanding, domain intelligence, or opportunities.
- **AR-1602** — Investment semantics SHALL begin at Prometheus and SHALL NEVER flow downward into Genesis, Reality Intelligence, or Scientific Understanding.
- **AR-1603** — Prometheus SHALL consume Genesis outputs — Opportunity Hypotheses, the Opportunity Portfolio, Opportunity Relationships, Opportunity Evolution, and Opportunity Prioritization — by version, and SHALL read them without ever mutating them.
- **AR-1604** — Every Prometheus output SHALL be replayable, explainable, and auditable, binding the Opportunity and understanding versions it was formed against.
- **AR-1605** — Prometheus SHALL consume and evaluate upstream understanding and opportunity and SHALL NEVER rewrite, restate, or redefine them.
- **AR-1606** — The Investment Thesis SHALL be a specialized Knowledge Object conforming to the canonical structure defined by the Knowledge Model; it SHALL reference, and SHALL NOT redefine, existing canonical objects, and it SHALL be the only new canonical object introduced by Prometheus.
- **AR-1607** — Prometheus SHALL assess Investability before constructing any Investment Thesis, preserving the distinction that not every Opportunity worth pursuing is investable.
- **AR-1608** — Every Investment Thesis SHALL bind the Opportunity version it addresses and preserve grounding, confidence, and uncertainty; competing Theses SHALL be preserved until evidence supports adjudication.
- **AR-1609** — Prometheus SHALL map Opportunities to the securities and instruments that express them, preserving alternatives, explainably and revisably.
- **AR-1610** — Prometheus SHALL preserve grounded, provenanced, uncertainty-preserving Valuation Evidence; no valuation SHALL be asserted as certain and no Thesis SHALL rest on a single valuation.
- **AR-1611** — Prometheus SHALL assess Risk and Reward together, preserving uncertainty, downside, and failure conditions; reward SHALL never be expressed without its accompanying risk.
- **AR-1612** — Prometheus SHALL assess Position Suitability (scale, structure, liquidity, horizon, constraints), kept distinct from Portfolio Fit.
- **AR-1613** — Prometheus SHALL assess Portfolio Fit (concentration, correlation, diversification, interaction) without rewriting any upstream understanding or opportunity.
- **AR-1614** — Prometheus SHALL produce Capital Allocation Recommendations expressing how much capital, in what structure, and under what conditions; a recommendation SHALL NOT be executed by Prometheus.
- **AR-1615** — Prometheus SHALL assess Timing-to-Action, grounded in upstream opportunity timing and readiness, preserving uncertainty, and distinguishing the timing of an opportunity from the timing of acting upon it.
- **AR-1616** — Every Prometheus decision SHALL be recorded in a Prometheus Decision Record, which SHALL be a Decision (EIOS-002), preserving the Thesis, grounding versions, recommendation, rationale, and alternatives, complete enough to reconstruct and audit the decision exactly.
- **AR-1617** — When an Opportunity is adjudicated, superseded, or overturned, every Investment Thesis grounded upon it SHALL be re-evaluated; no Thesis SHALL silently retain a superseded grounding.
- **AR-1618** — Every Investment Thesis, Capital Allocation Recommendation, and Prometheus Decision Record SHALL be replayable and auditable, with prior versions preserved.
- **AR-1619** — Prometheus SHALL recommend capital allocation and SHALL NOT execute trades, place orders, or operate live positions; execution belongs to consumers beyond this layer.
- **AR-1620** — Prometheus SHALL remain implementation independent.

---

### Requirements Introduced

- **REQ-PROM-001** — Prometheus
- **REQ-PROM-002** — Genesis-to-Prometheus Consumption Contract
- **REQ-PROM-003** — Opportunity-to-Investment Boundary
- **REQ-PROM-004** — Investability Assessment
- **REQ-PROM-005** — Investment Thesis
- **REQ-PROM-006** — Security and Instrument Mapping
- **REQ-PROM-007** — Valuation Evidence
- **REQ-PROM-008** — Risk and Reward Assessment
- **REQ-PROM-009** — Position Suitability
- **REQ-PROM-010** — Portfolio Fit Assessment
- **REQ-PROM-011** — Capital Allocation Recommendation
- **REQ-PROM-012** — Timing-to-Action Assessment
- **REQ-PROM-013** — Prometheus Decision Record
- **REQ-PROM-014** — Investment Thesis Evolution
- **REQ-PROM-015** — Replayability and Auditability
- **REQ-PROM-016** — Purpose Boundary
- **REQ-PROM-017** — Handoff to Execution
- **REQ-PROM-018** — Implementation Independence

---

### Future Dependencies

Referenced by:

* execution and operational subsystems
* portfolio management subsystems
* Personal CIO
* human decision-makers

Provides:

* Investment Theses
* Investability Assessments
* Security and Instrument Mappings
* Valuation Evidence
* Risk and Reward Assessments
* Portfolio Fit Assessments
* Capital Allocation Recommendations
* Timing-to-Action Assessments
* Prometheus Decision Records

---

### Cross References

- **Conforms To:** EIOS-000; EIOS-001; EIOS-002; EIOS-003; EIOS-004; EIOS-005; EIOS-006; EIOS-007; EIOS-008; EIOS-009; EIOS-010; EIOS-011; EIOS-012; EIOS-013; EIOS-014; GEN-001
- **Builds Upon:** Genesis (GEN-001); Opportunity Hypothesis (GEN-001); Opportunity Portfolio (GEN-001); Opportunity Graph (GEN-001); Opportunity (EIOS-002); Decision (EIOS-002); Reality Intelligence (EIOS-010); Scientific Worldview (EIOS-009)
- **Defines:** Prometheus; Genesis-to-Prometheus Consumption Contract; Investability Assessment; Investment Thesis; Security and Instrument Mapping; Valuation Evidence; Risk and Reward Assessment; Position Suitability; Portfolio Fit Assessment; Capital Allocation Recommendation; Timing-to-Action Assessment; Prometheus Decision Record; Investment Thesis Evolution
- **Referenced By:** execution and operational subsystems, portfolio management subsystems, Personal CIO, human decision-makers, and downstream capital-allocation subsystems
