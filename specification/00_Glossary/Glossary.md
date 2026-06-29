---
generated: true
generated_from: architecture/EIOS_Architecture_Book.md
kind: glossary
book_version: 0.7
source_hash: 3ef55d55951a7eddd434df91aca435bb0703fbcd642f989bb224e7f9c260e38b
manual_edits: prohibited
---

# Glossary

Each architectural term is defined exactly once, here. Chapters reference these definitions rather than redefining them. These definitions are normative.

| Term | Definition |
|------|------------|
| Reality | The external world. It exists independently of EIOS and is only ever represented, never stored (EIOS-000, EIOS-002). |
| Observation | A raw, immutable perception of reality with no inherent truth value (EIOS-002). |
| Evidence | An Observation that has passed validation and carries provenance (EIOS-002). |
| Fact | A validated assertion supported by one or more Evidence objects (EIOS-002). |
| Knowledge Object | The canonical unit of persistent knowledge; every persistent concept is exactly one Knowledge Object, carrying provenance, versioning, confidence, and temporal history (EIOS-002). |
| Knowledge Graph | The complete collection of Knowledge Objects and their Relationships; the persistent memory of EIOS (EIOS-002, EIOS-003). |
| World Model | The continuously evolving cognitive representation of reality constructed from the Knowledge Graph; the platform's primary product and sole authoritative representation of reality (EIOS-003). |
| Hypothesis | A competing explanation maintained with independent evidence, confidence, and replay history; contradictory hypotheses are preserved (EIOS-002, EIOS-003). |
| Confidence | The current scientific belief EIOS holds in a Knowledge Object or Relationship; it evolves continuously and is never silently overridden (EIOS-002). |
| Replay | Historical replay: scientific re-validation of a model, hypothesis, or decision against a point-in-time reconstruction of the world; a precondition of production (CI-008). |
| Experience Layer | The accumulated record of past reasoning outcomes that continuously modifies future reasoning (EIOS-003, EIOS-005). |
| Economic System | A primary system within which organizations, governments, markets, technologies, and companies participate; participants are never analyzed in isolation (CI-013). |
| Causal Relationship | A relationship expressing why a change occurs, kept distinct from statistical correlation (CI-004, EIOS-003). |
| System Dynamics | The interconnected behavior of reality's systems (technology, energy, manufacturing, finance, and others) that must be considered together (EIOS-003). |
| Genesis | Operational subsystem that discovers transformations in real-world systems rather than searching directly for securities (EIOS-001). |
| Prometheus | Operational subsystem that evaluates the implications of validated knowledge for publicly traded entities (EIOS-001). |
| Personal CIO | Operational subsystem that explains causal chains, quantifies uncertainty, and retains human accountability for recommendations (EIOS-001). |
