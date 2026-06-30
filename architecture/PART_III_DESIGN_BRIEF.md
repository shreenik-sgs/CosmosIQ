# Part III — Design Brief (Reality Intelligence)

**Status:** planning document · **Date:** 2026-06-30 · **Derived from:** completed Part II
(EIOS-007/008/009), ARB-001 (consistency), ARB-002 (mission traceability), ARB-003
(Part II↔III contract).

**Not authoritative architecture.** The single source of truth remains `specification/`
(compiled from `architecture/EIOS_Architecture_Book.md`). This brief plans Part III; it does
**not** write EIOS-010 and modifies nothing in the Book.

---

## Conceptual model — Part III is a first-class Intelligence Layer

**Resolved (refinement pass): Model B, with Model A retained only as the interface discipline.**

Part III is **not** a transport membrane. It is a **first-class Reality Intelligence Layer**
that continuously *forms* domain-specific understanding of reality — synthesizing incoming
Observations, the Scientific Worldview, Historical Experience, validated Scientific Theories,
and the Readiness/Emergence assessments into continuously evolving domain intelligence. This
places Part III at the same architectural stature as Part II: Part II forms domain-agnostic
*scientific understanding*; Part III forms domain *intelligence*.

The "membrane" framing from the first draft is **demoted to its correct level**: it describes
the *interface contract* between Part III and Part II (the three versioned interfaces, the
read-only worldview access, the domain-agnostic-core invariant) — not the *identity* of the
layer. The contract is how the layers connect; intelligence formation is what Part III is.

| | Model A (rejected as identity) | Model B (adopted) |
|---|---|---|
| Part III is… | a boundary that transports info | a layer that continuously forms intelligence |
| Core verb | consume / apply | **form / understand** |
| Role | application / plumbing | first-class intelligence production |
| Membrane | the whole role | only the Part III ↔ II *interface* |

---

## 1. Architectural objectives

Part III turns the Cognitive Architecture's validated scientific understanding into
real-world intelligence about emerging opportunities — bridging a **domain-agnostic science
engine** (Part II) to **actionable, domain-specific intelligence**.

- **O1 — Sense reality.** Surface weak/early/pre-consensus signals and convert them to
  canonical Observations (resolves ARB-002 Cap 1, the *input edge*).
- **O2 — Continuously form domain intelligence.** Synthesize incoming Observations, the
  Scientific Worldview, Historical Experience, validated Theories, and Readiness/Emergence
  assessments into continuously evolving domain understanding (technology, economic, supply,
  capital) — a first-class intelligence-production responsibility, **not** mere consumption.
- **O3 — Feed opportunity generation.** Provide the mature domain intelligence from which
  Genesis generates investable opportunity hypotheses (resolves ARB-002 Cap 12).
- **O4 — Preserve the invariants.** Everything Part III produces remains replayable (CI-008),
  explainable, challengeable, revisable, graph-native, and conformant to the canonical object
  model.
- **O5 — Protect the core.** Keep Part II domain-agnostic — zero investment semantics
  (the load-bearing boundary invariant from ARB-003).

---

## 2. Architectural scope

- **Name (working):** Reality Intelligence. **Chapters:** EIOS-010 (Reality Intelligence) as
  the layer foundation, the first-class domain-intelligence chapters EIOS-011–014, then the
  Genesis orchestrator and the PROM- engines (see §10).
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
| R2 | **Continuous Intelligence Formation** — continuously form domain intelligence, grounded in version-pinned, read-only worldview access | EIOS-010 + EIOS-011–014 |
| R3 | **Continuous Domain Understanding** — maintain continuously evolving domain models of reality; maintain the Intelligence Portfolio | EIOS-011–014 |
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
| Intelligence Product | EIOS-011–014 | A continuously-formed, domain-scoped understanding built on the worldview. |
| Intelligence Portfolio | EIOS-010 | Coordinated set of active intelligence products (Backlog BL-004). |
| Opportunity Hypothesis | GEN-001 | An investable opportunity hypothesis (resolves Cap 12). |
| Opportunity Portfolio | GEN-001 | Portfolio of evolving opportunities — *not* an investment portfolio (Backlog BL-005). |

Possible: **World Graph** (Backlog BL-002) — a graph projection of the World Model for
efficient Part III traversal.

---

## 8. Relationship with Part II

- **Topology — a continuous co-evolution loop between two first-class layers** (not a pipe,
  not a membrane). Reality Intelligence forms domain intelligence; it feeds Observations
  *down* into Scientific Cognition; Scientific Cognition forms the continuously evolving
  Scientific Worldview; Reality Intelligence reads that worldview *up* to ground and refine
  its domain intelligence; refined intelligence surfaces new Observations — and the loop
  continues. Worldview and domain intelligence **co-evolve**.

  ```
  Reality
     │
     ▼
  Reality Intelligence ──(Observations)──►  Scientific Discovery (Part II)
     ▲                                              │
     │                                              ▼
     └────(read worldview, version-pinned)──  Scientific Worldview
     │
     ▼
  Genesis  (orchestrates mature domain intelligence → Opportunity Hypotheses)
  ```
  *(The linear trace — Reality → Reality Intelligence → Scientific Discovery → Scientific
  Worldview → Reality Intelligence → Genesis — is one discovery pass through this loop.)*

- **The loop is data-flow, not dependency.** The architectural dependency stays strictly
  one-way: Part III `Builds Upon` Part II; Part II never `Builds Upon` Part III (no cycle).
  Part II has a *runtime service dependency* on the Observation feed but **no architectural
  dependency** — it consumes canonical Observations without knowing Part III exists. The
  bidirectional loop is mediated entirely by canonical objects (Observations down, Worldview
  up), which is precisely what keeps it acyclic.
- **Three interfaces (the contract — all versioned + replayable):** Observation Ingestion
  (III→II, append-only), Worldview Access (II→III, read-only, version-pinned), Change
  Propagation (II→III, notifications).
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

**Adopt the orchestrator-last model.** Genesis is an *orchestrator* that consumes multiple
*completed* domain intelligence engines; it must therefore come **after** them, not before.
The domain engines are promoted to **first-class chapters** (consistent with Model B), not
Genesis sub-engines.

1. **EIOS-010 — Reality Intelligence** *(the layer foundation — build first)*: Reality
   Sensing; the Part II ↔ III contract (the three interfaces); the Continuous Intelligence
   Formation framework; Change Propagation. Establishes and freezes the boundary; resolves
   Cap 1.
2. **EIOS-011 — Technology Intelligence**
3. **EIOS-012 — Economic Intelligence**
4. **EIOS-013 — Supply Network Intelligence**
5. **EIOS-014 — Capital Intelligence**
   *(EIOS-011–014: first-class domain intelligence engines, each continuously forming domain
   understanding on the worldview.)*
6. **GEN-001 — Genesis** *(orchestrator)*: consumes the completed domain engines → generates
   investable Opportunity Hypotheses; owns the Opportunity Portfolio; resolves Cap 12.
7. *(Part IV)* **PROM-001 Investment Thesis · PROM-002 Portfolio Intelligence ·
   PROM-003 Capital Allocation**.

Rationale: build the contract (EIOS-010) first so every domain engine conforms to one stable
boundary (as Part II built EIOS-000 before its dependents); build the domain engines **before**
the orchestrator so Genesis consumes finished, conformant intelligence rather than inverting
the dependency.

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
- **K7 — Scope explosion.** Reality Intelligence (EIOS-010) + four domain engines
  (EIOS-011–014) + Genesis + Prometheus is large. *Mitigation:* freeze the EIOS-010 contract
  before authoring domains.
- **K8 — Forward-reference drift (partially resolved during authoring, v5.0).** Three
  forward-references diverged from this model. Two were reconciled when Part III opened: Part III
  **"Platform Architecture" → "Reality Intelligence"**, and EIOS-010 **"World Intelligence" →
  "Reality Intelligence"** (the latter lived only in EIOS-009, which is not frozen). The third —
  **Technology/Economic Intelligence GEN-002/003 → EIOS-011/012** — **cannot** be reconciled the
  same way: those forward-references live in **frozen Part I** (EIOS-004/005/006), so renaming
  them requires an ADR. *Mitigation applied:* EIOS-010 references future domain engines **by
  name, not number**, deferring the numbering (see Q8).

---

## 12. Open questions

- **Q1 (BL-002):** Should the World Model become an explicit **World Graph** for Part III?
- **Q2:** Is a weak **Signal** a distinct canonical object, or a low-salience annotated
  Observation? (concept-budget decision)
- **Q3 (K5):** Does the `Opportunity` lifecycle live in EIOS-010 or GEN-001?
- **Q4 (resolved by this refinement):** Technology/Economic/Supply/Capital Intelligence are
  **first-class chapters** (EIOS-011–014), not sections of EIOS-010 — consistent with Model B.
- **Q8 (open governance decision — surfaced during EIOS-010 authoring).** The domain-engine
  numbering is unresolved. §10 proposed Technology/Economic/Supply/Capital Intelligence as
  first-class **EIOS-011–014**, but frozen Part I forward-references name Technology/Economic
  Intelligence as **GEN-002/GEN-003**, and frozen chapters cannot be edited without an ADR. The
  choice is therefore: (a) author them as **EIOS-011–014** and accept (or ADR-correct) the stale
  frozen GEN-002/003 pointers; or (b) keep them as **GEN-002/003** within the Genesis-numbered
  scheme while still treating them as first-class. A name/placement decision, not new
  architecture; it does not block EIOS-010. The Part IV–V names ("Applications", "Engineering
  Reference") remain a separate open re-decision.
- **Q5 (BL-003/004/005):** Do the Intelligence and Opportunity portfolios become the 6th/7th
  portfolio abstractions, and which chapter owns each?
- **Q6:** Part III REQ namespaces — e.g., `REQ-WI` (World Intelligence), `REQ-GEN` (Genesis)?
- **Q7 (governance):** Opening Part III — establishing the layer, its boundary contract, and
  the domain-agnostic invariant — almost certainly warrants a **new ADR** (next is ADR-0008).
