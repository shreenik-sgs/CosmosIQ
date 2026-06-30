---
generated: true
do_not_edit: true
canonical_source: architecture/EIOS_Architecture_Book.md
kind: glossary
book_version: 4.3
generator_version: 1.1
source_hash: 1599a92b6088235263862fabc2f4f2595d1b656450ec6be9e4a24a83f40c8269
generated_at: 2026-06-29T23:35:28-05:00
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
| Model | A bounded, purpose-specific representation of part of reality, built to support explanation, prediction, simulation, reasoning, or decision; never reality itself. | EIOS-007 | Mental Model, World Model | Cognitive Architecture |
| Replay | Historical replay: scientific re-validation against a point-in-time reconstruction of the world; a precondition of production. | EIOS-000 (CI-008) | Confidence, FI-002 | Constitutional |
| Experience Layer | The institutional memory of scientific understanding — validated models, reasoning strategies, replay outcomes, lessons learned — that turns accumulated experience into reusable institutional intelligence. | EIOS-008 | Scientific Memory, Institutional Intelligence | Cognitive Architecture |
| Institutional Intelligence | The collective scientific capability accumulated through continuous experience; unlike memory, it actively improves reasoning (analogy, pattern recognition, principle extraction, strategy selection). | EIOS-008 | Experience Layer, Scientific Memory | Cognitive Architecture |
| System State | A real-world system's condition as a multidimensional state vector (readiness, constraint, dependency, confidence, evolution, transition), not a scalar; estimated continuously by the Experience Layer. | EIOS-008 | Readiness, Experience Layer | Cognitive Architecture |
| Readiness | The degree to which a system holds the prerequisites for a future transition; an extensible multidimensional vector (not a scalar), with momentum (direction of change) tracked separately. | EIOS-008 | System State, Constraint Release | Cognitive Architecture |
| Constraint Release | The reduction or elimination of limiting conditions that previously blocked system evolution; often precedes major transitions; tracked independently of readiness (measured by CRI). | EIOS-008 | Constraint, Readiness | Cognitive Architecture |
| Convergence | The simultaneous satisfaction of multiple independently evolving readiness dimensions; major transitions emerge from convergence rather than any single condition (measured by CAS). | EIOS-008 | Readiness, Emergence Readiness Score | Cognitive Architecture |
| Emergence Readiness Score | The headline architectural assessment (ERS) of how prepared a system appears for significant transition; an architectural concept, not a prescribed algorithm — one of six (ERS, RM, CRI, CAS, HAS, TTI). | EIOS-008 | Readiness, Convergence | Cognitive Architecture |
| Historical Scientific Intelligence | The Experience Layer capability that extracts enduring, reusable scientific understanding from historical reality — cases, transitions, successes, and failures — rather than merely recording history. | EIOS-008 | Historical Case, Scientific Principle | Cognitive Architecture |
| Historical Case | A bounded, replayable observation of reality over a defined period, preserving its full scientific context; the unit from which scientific principles are extracted. | EIOS-008 | Historical Scientific Intelligence, Scientific Principle | Cognitive Architecture |
| Scientific Principle | A Principle (EIOS-002) generalized from recurring mechanisms across multiple independent Historical Cases; preserves supporting cases, evidence, models, confidence, applicability, and limits; continuously re-evaluable. | EIOS-008 | Principle, Candidate Scientific Law | Cognitive Architecture |
| Candidate Scientific Law | A Scientific Principle showing persistent validity across many domains and long history, proposed with stronger evidence for validation. Experience proposes; Scientific Discovery validates. | EIOS-008 | Scientific Principle | Cognitive Architecture |
| Institutional Scientific Learning | The Experience Layer capability that turns accumulated scientific experience into enduring organizational intelligence — consolidation, confidence evolution, conflict preservation, maturity, continuity — so every validated discovery permanently improves future reasoning. | EIOS-008 | Institutional Intelligence, Institutional Wisdom | Cognitive Architecture |
| Institutional Wisdom | The highest level of accumulated scientific understanding, emerging from long-term integration of validated experience, principles, candidate laws, and organizational learning; evidence-based and distinguished from opinion. | EIOS-008 | Institutional Scientific Learning, Scientific Principle | Cognitive Architecture |
| Knowledge Consolidation | Combining related scientific understanding into coherent institutional knowledge while preserving provenance, uncertainty, and competing explanations; never discards contradictory evidence. | EIOS-008 | Institutional Scientific Learning | Cognitive Architecture |
| Knowledge Maturity | The progressive stages (emerging → developing → validated → established → foundational) through which an institutional knowledge artifact advances; evolves independently per artifact and is continuously reassessable. | EIOS-008 | Institutional Scientific Learning | Cognitive Architecture |
| Scientific Discovery | The architectural capability that generates new scientific understanding — managing the lifecycle of Research Questions and producing hypotheses, candidate models, principles, and candidate laws. Inquiry before inference. | EIOS-009 | Research Question, Experience Layer | Cognitive Architecture |
| Research Agenda | The continuously evolving collection of active, unresolved, and emerging Research Questions requiring investigation; expands as discovery proceeds. | EIOS-009 | Scientific Discovery, Research Question | Cognitive Architecture |
| Question Graph | The first-class graph of relationships among active Research Questions — dependency, refinement, decomposition, contradiction, support, competition — over which Scientific Discovery reasons. | EIOS-009 | Research Agenda, Research Question | Cognitive Architecture |
| Knowledge Gap | An explicit region of incomplete scientific understanding, preserved independently of existing hypotheses as a discovery asset. | EIOS-009 | Scientific Discovery, Research Question | Cognitive Architecture |
| Discovery Readiness | An assessment of whether a Research Question is currently investigable (available evidence, models, experimental capability); independent of question priority. | EIOS-009 | Research Question, Scientific Discovery | Cognitive Architecture |
| Hypothesis Graph | The first-class graph of relationships among Hypotheses — refinement, dependency, competition, support, contradiction, composition — over which Scientific Discovery reasons. | EIOS-009 | Hypothesis, Question Graph | Cognitive Architecture |
| Hypothesis Portfolio | A coordinated collection of competing and cooperating candidate explanations for a Research Question; preserves diversity of scientific reasoning rather than converging prematurely. | EIOS-009 | Hypothesis, Research Program | Cognitive Architecture |
| Research Program | A long-term scientific investigation organized around a coherent family of Research Questions and Hypotheses (with supporting models and evidence); replayable, and the unit an investment domain can map to. | EIOS-009 | Research Question, Hypothesis | Cognitive Architecture |
| Scientific Investigation | The capability that systematically acquires evidence to strengthen, weaken, refine, or reject competing Hypotheses; evidence acquisition before judgment, and the stage feeding Validation & Falsification. | EIOS-009 | Hypothesis, Evidence Graph | Cognitive Architecture |
| Evidence Graph | The first-class graph of Evidence and its relationships — supports, contradicts, explains, derives-from, validates, challenges — kept synchronized with the Hypothesis Graph during investigation. | EIOS-009 | Hypothesis Graph, Scientific Investigation | Cognitive Architecture |
| Investigation Portfolio | A coordinated collection of related investigations pursuing complementary objectives; preserves the autonomy of each investigation while optimizing scientific value across the set. | EIOS-009 | Scientific Investigation, Hypothesis Portfolio | Cognitive Architecture |
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
| Model Graph | The first-class graph of relationships among models — inheritance, specialization, composition, dependency, validation, refinement; the primary primitive for reasoning about models. The Model Registry is an index over it. | EIOS-007 | Model, Intelligence Graph | Cognitive Architecture |
| Model Repository | The store of model definitions, implementations, artifacts, and historical versions; distinct from the Model Registry (the index) and the Model Graph (the relationships). | EIOS-007 | Model Graph, Model Registry | Cognitive Architecture |
| Model Portfolio | A purpose-specific collection of cooperating models assembled for a reasoning objective; more than a set of models — a reusable reasoning strategy whose effectiveness the Experience Layer learns over time. | EIOS-007 | Model, Model Graph | Cognitive Architecture |
| Scientific Memory | The accumulated body of validated models, reasoning strategies, validation history, replay outcomes, and lessons learned; grows without rewriting history and is a primary input to future discovery — the bridge to the Experience Layer. | EIOS-007 | Model Portfolio, Experience Layer | Cognitive Architecture |
| Genesis | Operational subsystem that discovers transformations in real-world systems rather than searching directly for securities. | EIOS-001 | Prometheus, Personal CIO | Operational |
| Prometheus | Operational subsystem that evaluates the implications of validated knowledge for publicly traded entities. | EIOS-001 | Genesis, Personal CIO | Operational |
| Personal CIO | Operational subsystem that explains causal chains, quantifies uncertainty, and retains human accountability for recommendations. | EIOS-001 | Genesis, Prometheus | Operational |
