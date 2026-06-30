---
generated: true
do_not_edit: true
canonical_source: architecture/EIOS_Architecture_Book.md
kind: glossary
book_version: 1.6
generator_version: 1.0
source_hash: 7d867c694c1d76c69c59ae56b7e9f6bad9dba0ff2c2084648e70aba680d87570
generated_at: 2026-06-29T19:54:49-05:00
---

# Glossary

This is the **Architectural Lexicon** of EIOS: every first-class architectural concept, defined exactly once. Chapters reference these definitions rather than redefining them. These definitions are normative. The **Status** column uses the Chapter Class taxonomy; **Canonical** names the chapter (or invariant) that owns the definition. ID namespaces (CI, FI, AR, REQ-*) are catalogued in the Book's Namespace Registry.

| Concept | Definition | Canonical | Related | Status |
|---------|------------|-----------|---------|--------|
| Reality | The external world; exists independently of EIOS and is only ever represented, never stored. | EIOS-002 | Observation, World Model | Foundational |
| Observation | A raw, immutable perception of reality with no inherent truth value. | EIOS-002 | Evidence, Fact | Foundational |
| Evidence | An Observation that has passed validation and carries provenance. | EIOS-002 | Observation, Fact | Foundational |
| Fact | A validated assertion supported by one or more Evidence objects. | EIOS-002 | Evidence, Knowledge Object | Foundational |
| Knowledge Object | The canonical unit of persistent knowledge; one per persistent concept, carrying provenance, versioning, confidence, and temporal history. | EIOS-002 | Knowledge Graph, Relationship | Foundational |
| Concept | An abstract idea that participates in reasoning but has no physical existence (e.g. scarcity, network effects); reusable across domains. | EIOS-002 | Principle, Knowledge Object | Foundational |
| Principle | A reusable explanatory mechanism describing recurring system behavior (e.g. Moore's Law); a first-class reasoning object. | EIOS-002 | Concept, Scientific Cognition | Foundational |
| Relationship | A first-class interaction between participants, carrying type, direction, confidence, and provenance. | EIOS-002 | Knowledge Object, Network | Foundational |
| Knowledge Graph | The complete collection of Knowledge Objects and Relationships; the persistent memory of EIOS. | EIOS-002 | World Model, Intelligence Graph | Foundational |
| Research Question | The unit that opens a scientific investigation; progresses through a defined lifecycle. | EIOS-004 | Hypothesis, Scientific Cognition | Foundational |
| Hypothesis | A competing explanation maintained with independent evidence, confidence, and replay history; contradictions preserved. | EIOS-002 | Research Question, Confidence | Foundational |
| Confidence | The current scientific belief in an object or relationship; evolves continuously and is never silently overridden. | EIOS-002 | Evidence, Replay | Foundational |
| Scientific Cognition | The architectural process turning knowledge into understanding: curiosity, mental modeling, inquiry, judgment, evolution. | EIOS-004 | Mental Model, Research Question | Foundational |
| Mental Model | A temporary, domain-specific reasoning context derived from and synchronized with the World Model; never an independent source of truth. | EIOS-004 | World Model, Scientific Cognition | Foundational |
| Replay | Historical replay: scientific re-validation against a point-in-time reconstruction of the world; a precondition of production. | EIOS-000 (CI-008) | Confidence, FI-002 | Constitutional |
| Experience Layer | The accumulated record of past reasoning outcomes that continuously modifies future reasoning. | EIOS-003 (detailed in EIOS-008) | Scientific Cognition, Confidence | Foundational |
| World Model | The continuously evolving cognitive representation of reality built from the Knowledge Graph; the primary product and sole authoritative representation of reality. | EIOS-003 | Knowledge Graph, Intelligence Graph | Foundational |
| World Model View | A persistent projection of the World Model optimized for a class of investigations; derived from and subordinate to the World Model. | EIOS-003 | World Model | Foundational |
| Event | A discrete occurrence that modifies system state; distinct from state (state is what exists, an event is what caused change). | EIOS-003 | World Model | Foundational |
| Belief | A held conviction that may diverge from observed reality yet influences behavior; represented independently of objective reality. | EIOS-003 | World Model, Reality | Foundational |
| Economic System | A primary system within which organizations, governments, markets, technologies, and companies participate; never analyzed in isolation. | EIOS-005 (CI-013) | System Dynamics, Network | Foundational |
| System Dynamics | The interconnected behavior of reality's systems that must be considered together. | EIOS-003, EIOS-005 | Propagation, Emergence | Foundational |
| Causal Relationship | A relationship expressing why a change occurs, kept distinct from statistical correlation. | EIOS-003 (CI-004) | Relationship, Propagation | Foundational |
| Emergence | Behavior arising from interaction among many participants, not attributable to any individual; a property of systems. | EIOS-005 | System Dynamics, Network | Foundational |
| Propagation | How a change in one part of a system influences others over time (origin, direction, magnitude, delay, amplification). | EIOS-005 | Bottleneck, Leverage Point | Foundational |
| Constraint | A factor that regulates propagation or limits a system; represented explicitly. | EIOS-005 | Bottleneck, Propagation | Foundational |
| Bottleneck | A constraint that limits system throughput; its removal reorganizes the whole system, so it receives elevated priority. | EIOS-005 | Constraint, Leverage Point | Foundational |
| Leverage Point | A location where a small change produces disproportionately large downstream effects. | EIOS-005 | Propagation, Bottleneck | Foundational |
| Network | A first-class analytical structure of nodes, relationships, flows, dependencies, and constraints; participants belong to many at once. | EIOS-006 | Intelligence Graph, Relationship | Foundational |
| Intelligence Graph | A dynamic analytical projection assembled from interconnected networks to answer a class of questions; derived from the World Model, not a replacement for it. | EIOS-006 | World Model, Decision Graph | Foundational |
| Decision Graph | A transient, goal-specific projection of feasible choices, consequences, trade-offs, and recommendations, derived exclusively from the Intelligence Graph; never a canonical representation of reality. | EIOS-006 | Intelligence Graph | Foundational |
| Genesis | Operational subsystem that discovers transformations in real-world systems rather than searching directly for securities. | EIOS-001 | Prometheus, Personal CIO | Operational |
| Prometheus | Operational subsystem that evaluates the implications of validated knowledge for publicly traded entities. | EIOS-001 | Genesis, Personal CIO | Operational |
| Personal CIO | Operational subsystem that explains causal chains, quantifies uncertainty, and retains human accountability for recommendations. | EIOS-001 | Genesis, Prometheus | Operational |
