# Part III — Design Brief (Reality Intelligence)

**Status:** planning document · **Date:** 2026-06-30 · **Derived from:** completed Part II
(EIOS-007/008/009), ARB-001 (consistency), ARB-002 (mission traceability), ARB-003
(Part II↔III contract).

**Not authoritative architecture.** The single source of truth remains `specification/`
(compiled from `architecture/EIOS_Architecture_Book.md`). This brief plans Part III; it does
**not** write EIOS-010 and modifies nothing in the Book.

---

## 1. Architectural objectives

Part III turns the Cognitive Architecture's validated scientific understanding into
real-world intelligence about emerging opportunities — bridging a **domain-agnostic science
engine** (Part II) to **actionable, domain-specific intelligence**.

- **O1 — Sense reality.** Surface weak/early/pre-consensus signals and convert them to
  canonical Observations (resolves ARB-002 Cap 1, the *input edge*).
- **O2 — Apply the worldview.** Consume Part II's Scientific Worldview to produce
  domain-scoped intelligence (technology, economic, supply, capital).
- **O3 — Feed opportunity generation.** Provide the substrate from which Genesis generates
  investable opportunity hypotheses (resolves ARB-002 Cap 12, the *application edge*).
- **O4 — Preserve the invariants.** Everything Part III produces remains replayable (CI-008),
  explainable, challengeable, revisable, graph-native, and conformant to the canonical object
  model.
- **O5 — Protect the core.** Keep Part II domain-agnostic — zero investment semantics
  (the load-bearing boundary invariant from ARB-003).

---

## 2. Architectural scope

- **Name (working):** Reality Intelligence. **Chapters:** EIOS-010 (World Intelligence) and
  the GEN-/PROM- engines that build on it.
- **In scope:** reality sensing / weak-signal detection; the worldview-consumption interface;
  world-intelligence synthesis; change propagation; the handoff contract to Genesis.
- **Adjacent (defined here, owned downstream):** Genesis (opportunity generation),
  Prometheus (investment theses, portfolios — likely Part IV).
- **Out of scope for this brief:** authoring EIOS-010; Genesis/Prometheus internals;
  investment/portfolio mechanics.

---

## 3. Responsibilities

| # | Responsibility | Owner (proposed) |
|---|---|---|
| R1 | Reality Sensing — ingest raw reality, detect weak signals, emit canonical Observations (+provenance/salience) | EIOS-010 |
| R2 | Worldview Consumption — version-pinned, read-only access to Part II's Scientific Worldview, theories, assessments | EIOS-010 |
| R3 | World Intelligence Synthesis — build domain Intelligence Products; maintain the Intelligence Portfolio | EIOS-010 + GEN-002/003 |
| R4 | Change Propagation — react to belief-revision / validation-drift; re-evaluate dependent intelligence | EIOS-010 |
| R5 | Handoff to Genesis — provide World Intelligence + Opportunity substrate | EIOS-010 → GEN-001 |
| R6 | Opportunity generation — convert intelligence into investable opportunity hypotheses | GEN-001 (Genesis) |

---

## 4. Boundaries

**Must remain OUTSIDE Cognitive Architecture (Part II):**
- Sensing / ingestion / connectors and weak-signal scanning of raw external data.
- Domain intelligence (technology / economic / supply / capital).
- **All investment semantics** — investor, market, asset, valuation, thesis, opportunity
  generation.
- Personalization / user-facing products (Personal CIO).

**Hard rules (from the ARB-003 contract):**
1. Observations are the *only* inbound cognitive currency into Part II.
2. Part III **reads, never mutates** Part II cognitive objects.
3. Part III is the *only* place raw/external data enters; Part II sees only canonical
   Observations/Evidence.
4. Investment semantics first appear in **Genesis**, never in Part II — and not even in
   EIOS-010 (World Intelligence produces *intelligence about reality*, not *investable
   opportunities*).

---

## 5. Inputs

- **From reality (via connectors):** technology, economic, scientific-literature,
  measurement, supply, and capital data streams.
- **From Part II (read-only, version-pinned):** the Scientific Worldview, Scientific
  Theories, Candidate-Law assessments, validated Hypotheses, Scientific Principles, the
  assessment metrics (ERS, TTI, CRI, CAS, HAS), and the Experience Layer (historical cases,
  analogs, institutional intelligence). *(= the union of the EIOS-008/009 `Provides` lists.)*
- **Change notifications from Part II:** belief-revision (AR-0952) and validation-drift
  (AR-0958) events.

---

## 6. Outputs

- **Into Part II:** canonical Observations (+ proposed Research Questions; Part II adjudicates).
- **Downstream (Genesis / Prometheus / Personal CIO / users):** Intelligence Products
  (Technology / Economic / Supply / Capital Intelligence), the Intelligence Portfolio, and the
  substrate for Opportunity Hypotheses.
- All outputs are versioned, replayable, and explainable, and record the worldview version
  they were produced against.

---

## 7. Canonical objects introduced

Reused unchanged (cross the boundary): Observation, Evidence, Research Question, Hypothesis,
Scientific Principle, Candidate Scientific Law, Scientific Theory, **Scientific Worldview**,
Opportunity, and the assessment metrics — all already canonical (EIOS-002/008/009).

**Minimal new Part III objects:**
| Object | Owner | Notes |
|---|---|---|
| Signal (Weak Signal) | EIOS-010 | A sensed indicator triaged/promoted into a canonical Observation. *Open: distinct object vs. annotated low-salience Observation (see §12).* |
| Intelligence Product | EIOS-010 / GEN-002/003 | A domain-scoped synthesis built on the worldview. |
| Intelligence Portfolio | EIOS-010 | Coordinated set of active intelligence products (Backlog BL-004). |
| Opportunity Hypothesis | GEN-001 | An investable opportunity hypothesis (resolves Cap 12). |
| Opportunity Portfolio | GEN-001 | Portfolio of evolving opportunities — *not* an investment portfolio (Backlog BL-005). |

Possible: **World Graph** (Backlog BL-002) — a graph projection of the World Model for
efficient Part III traversal.

---

## 8. Relationship with Part II

- **Topology:** Part III *brackets* Part II (sensing in → cognition → worldview out).
- **Three interfaces (all versioned + replayable):** Observation Ingestion (III→II,
  append-only), Worldview Access (II→III, read-only, version-pinned), Change Propagation
  (II→III, notifications).
- **Dependency direction stays clean:** Part III `Builds Upon` Part II; Part II never
  `Builds Upon` Part III (no cycle). Note the distinction: Part II has a *runtime service
  dependency* on the Observation feed, but **no architectural dependency** — it consumes
  canonical Observations without knowing Part III exists.
- **Invariant:** Part II remains domain-agnostic; it carries zero Part III / investment
  semantics.

---

## 9. Relationship with Genesis

- **Genesis (GEN-001) consumes** World Intelligence (EIOS-010) + the Scientific Worldview +
  the `Opportunity` object, and **produces** Opportunity Hypotheses (Opportunity Portfolio).
- **Clean separation:** EIOS-010 answers *"what is emerging and when"* (intelligence);
  Genesis answers *"what is investable"* (opportunity). Investment semantics begin at Genesis.
- Genesis is the resolution of ARB-002 Cap 12; EIOS-010 supplies its substrate.
- **Prometheus (PROM-)** consumes Genesis opportunities → investment theses, portfolios
  (Part IV).

---

## 10. Recommended chapter sequence

1. **EIOS-010 — World Intelligence** *(the membrane — build first)*: Reality Sensing →
   Worldview Consumption → World Intelligence synthesis foundation → Change Propagation →
   handoff contract. Establishes and freezes the Part II↔III boundary; resolves Cap 1.
2. **GEN-001 — Genesis Discovery Engine**: opportunity-hypothesis generation framework;
   Opportunity Portfolio; resolves Cap 12.
3. **GEN-002 — Technology Intelligence**, **GEN-003 — Economic Intelligence**: domain engines
   on the worldview.
4. **Supply Network Intelligence**, **Capital Intelligence**: further domain depth.
5. *(Part IV)* **PROM-001 Investment Thesis · PROM-002 Portfolio Intelligence ·
   PROM-003 Capital Allocation**: the investment layer.

Rationale: build the membrane (contract) first so every later engine conforms to one stable
boundary, exactly as Part II built EIOS-000 (Constitution) before its dependents.

---

## 11. Major architectural risks

- **K1 — Boundary erosion.** Domain/investment semantics leaking into Part II. *Mitigation:*
  ARB-003 contract invariants; a canonical-ownership ARB during authoring.
- **K2 — Stale beliefs.** Intelligence not re-evaluated when the worldview shifts.
  *Mitigation:* Change Propagation interface + worldview-version binding on every object.
- **K3 — Replay break.** Non-deterministic ingestion/intelligence violating CI-008.
  *Mitigation:* immutable Observations with provenance; version-pinned worldview reads.
- **K4 — Concept duplication.** Reinventing structures Part II / EIOS-006 already define
  (esp. the **Intelligence Graph**, EIOS-006). *Mitigation:* reuse canonical; ownership check.
- **K5 — Membrane ownership ambiguity.** Who owns the `Opportunity` lifecycle — EIOS-010 or
  Genesis? *Mitigation:* explicit clause (Genesis owns opportunity reasoning).
- **K6 — Weak-signal precision/recall.** Too much noise or missed signals. *Mitigation:*
  salience/triage model (partly an implementation concern — flag).
- **K7 — Scope explosion.** World Intelligence + four domain engines + Genesis + Prometheus
  is large. *Mitigation:* freeze the EIOS-010 contract before authoring domains.

---

## 12. Open questions

- **Q1 (BL-002):** Should the World Model become an explicit **World Graph** for Part III?
- **Q2:** Is a weak **Signal** a distinct canonical object, or a low-salience annotated
  Observation? (concept-budget decision)
- **Q3 (K5):** Does the `Opportunity` lifecycle live in EIOS-010 or GEN-001?
- **Q4:** Are Technology/Economic/Supply/Capital Intelligence *sections* of EIOS-010 or
  *separate* chapters? (chapter granularity)
- **Q5 (BL-003/004/005):** Do the Intelligence and Opportunity portfolios become the 6th/7th
  portfolio abstractions, and which chapter owns each?
- **Q6:** Part III REQ namespaces — e.g., `REQ-WI` (World Intelligence), `REQ-GEN` (Genesis)?
- **Q7 (governance):** Opening Part III — establishing the layer, its boundary contract, and
  the domain-agnostic invariant — almost certainly warrants a **new ADR** (next is ADR-0008).
