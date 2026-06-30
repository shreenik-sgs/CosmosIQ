# Part III — Canonical Information Currencies (design document)

**Status:** design document · **Date:** 2026-06-30 · **Grounded in:** ADR-0008 (the three
cognitive layers) and the Part III design brief. **Not authoritative architecture; modifies
nothing in the Book; does not draft EIOS-010.**

## Purpose and method

Before designing canonical objects, identify the **information currencies** — the units of
information that *flow between layers*. A currency is not automatically an object. The goal
(your stated goal) is to **minimize the number of canonical objects while maximizing clarity**.

A candidate currency earns **first-class canonical-object** status only if it has all of:
identity, provenance, an independent lifecycle, and is *reasoned about* in its own right.
Otherwise it is one of:
- **(reuse)** an existing canonical object (EIOS-002);
- **(state)** a lifecycle state of an existing object;
- **(composition)** an aggregation/graph of other objects (the Portfolio pattern);
- **(capability)** an act the layer performs, not a thing it stores.

### The ADR-0008 flow test (decisive)
ADR-0008: *understanding flows upward; purpose never flows downward.* This yields a hard rule
on currencies: **the only currency that may flow *down* into the purpose-free science core is
the raw Observation.** Everything Part III *forms* (assessments, products, opportunities) flows
*up* or stays in its layer — it must never re-enter Part II, or it would contaminate the core.

## The currency flow

```
Reality ──raw data──►  REALITY INTELLIGENCE  ──Intelligence──►  GENESIS  ──►  Prometheus / CIO
                            │     ▲                                │
                  Observations   │ Worldview (read, version-pinned)│
                            ▼     │                                ▼
                       COGNITIVE ARCHITECTURE (Part II)        Opportunities
```
- **Down into Part II:** Observations only (raw, purpose-free).
- **Up from Part II:** the Scientific Worldview + scientific assessments (consumed, *owned by
  Part II*) — an input currency to Layer 2, not a Part III object.
- **Within/up from Part III:** Intelligence Assessments → (Products) → (Portfolio).
- **Layer 3:** Opportunities (hypothesized → validated) → (Opportunity Portfolio).

---

## Per-currency analysis

### Observation
- **Why it must exist:** the sole raw input currency; reality enters cognition only as
  Observations.
- **Immutable?** Yes — a raw, immutable perception of reality (EIOS-002).
- **Owns:** *defined* by the Knowledge Model (EIOS-002, Part I); *produced* by Reality
  Intelligence sensing.
- **Consumes:** Part II (Scientific Discovery). The one currency permitted to flow downward.
- **Object or state?** **Existing canonical object (reuse).** No new object.

### Signal
- **Why it must exist:** the mission needs weak/early-signal detection (ARB-002 Cap 1).
- **Immutable?** A signal's *datum* is an immutable Observation; its *significance* evolves.
- **Owns / Consumes:** sensed by Reality Intelligence; the significance is consumed within
  Layer 2.
- **Object or state?** **Not an object.** A "signal" decomposes into (a) an **Observation**
  carrying salience/novelty, plus (b) the *interpretation* that it is an early indicator —
  which is itself an **Intelligence Assessment**. The raw datum is an Observation; "this is a
  signal" is an Assessment. Weak-signal detection is a **capability**, not a stored object.

### Intelligence Assessment
- **Why it must exist:** the **atom of domain intelligence** — a judgment about the state or
  trajectory of some aspect of a domain (e.g., "HBM supply is approaching constraint
  release"), grounded in Observations + the Worldview + Experience + the scientific
  assessments (ERS/TTI/CRI/…), carrying confidence and provenance. Nothing in EIOS-002 captures
  this: it is not a Hypothesis (scientific), not a Prediction (future-only), not a Fact
  (settled). It is the unit Layer 2 forms, compares, challenges, and revises.
- **Immutable?** **No** — it continuously evolves as understanding evolves (belief revision and
  validation drift propagate up from Part II). But every *version* is immutable and preserved
  (replayable), and each version is bound to the **worldview version** it was formed against —
  exactly like Scientific Validation and the Worldview itself.
- **Owns:** Reality Intelligence (Layer 2). **Consumes:** Intelligence Products, then Genesis.
  Never flows down into Part II.
- **Object or state?** **First-class canonical object — the one new atom Part III introduces.**

### Intelligence Product
- **Why it must exist:** a coherent, continuously-evolving domain understanding (e.g.,
  "Technology Intelligence") — a structured body of Intelligence Assessments about one domain.
- **Immutable?** No — an evolving, versioned synthesis.
- **Owns:** a Reality Intelligence domain engine. **Consumes:** the Intelligence Portfolio;
  Genesis.
- **Object or state?** **Composition (default).** By the Portfolio precedent, a Product is a
  named, versioned aggregation/graph of Intelligence Assessments — a first-class *concept*, not
  a new atom. *(This is the one genuine judgment call — see "The single decision" below.)*

### Intelligence Portfolio
- **Why it must exist:** the coordinated set of active intelligence products feeding Genesis
  (BL-004).
- **Immutable?** No — continuously evolving collection.
- **Owns:** Reality Intelligence (Layer 2). **Consumes:** Genesis.
- **Object or state?** **Composition.** Same pattern as Part II's portfolios — a first-class
  concept that reduces to a collection of Products/Assessments. No new atom.

### Opportunity Hypothesis
- **Why it must exist:** Genesis generates candidate investable opportunities (ARB-002 Cap 12).
- **Immutable?** No — evolves through its lifecycle (refined / validated / rejected).
- **Owns:** Genesis (Layer 3). **Consumes:** Prometheus, Personal CIO.
- **Object or state?** **State of an existing object.** EIOS-002 already defines **Opportunity**.
  "Opportunity Hypothesis" is the Opportunity in its **candidate / hypothesized lifecycle
  state** — not a new object. (Keeping it a state of Opportunity, rather than reusing the
  scientific *Hypothesis* object, also respects ADR-0008: opportunity reasoning is Layer 3, not
  scientific cognition.)

### Opportunity Portfolio
- **Why it must exist:** a portfolio of evolving opportunities being monitored — *not* an
  investment portfolio (BL-005).
- **Immutable?** No.
- **Owns:** Genesis (Layer 3). **Consumes:** Prometheus.
- **Object or state?** **Composition** of Opportunities. No new atom.

---

## Minimization result

| Currency | Verdict | Canonical atom? |
|---|---|---|
| Observation | reuse (EIOS-002) | — |
| Signal | Observation + Assessment; detection is a capability | **no** |
| **Intelligence Assessment** | the atom of domain intelligence | **YES (new)** |
| Intelligence Product | composition of Assessments *(judgment call)* | no (default) |
| Intelligence Portfolio | composition | no |
| Opportunity Hypothesis | state of **Opportunity** (EIOS-002) | no |
| Opportunity Portfolio | composition of Opportunities | no |

**Recommendation: Part III introduces exactly ONE new first-class canonical object — the
Intelligence Assessment.** It reuses Observation and Opportunity (both already canonical), and
expresses everything else as states or compositions. One new atom for an entire new
architectural layer is the minimal result consistent with clarity.

## The single decision worth making deliberately

**Is Intelligence Product a composition or a first-class object?** The precedent cuts both ways:
- Like a **Portfolio** → composition (default; minimal).
- Like a **Scientific Theory** (which integrates Principles into a framework with its own
  emergent identity, applicability, and limitations) → a first-class object.

Recommendation: **composition by default**, promotable to a first-class object *only if* domain
syntheses turn out to need identity and lifecycle independent of their assessments. Decide this
when authoring the first domain engine, not now. If promoted, Part III would have **two** new
atoms (Assessment, Product); otherwise **one**.

## One architectural insight this surfaced

**Immutability tracks the layer boundary.** The *only* immutable currency is the raw
Observation. Everything Part III *forms* — assessments, products, opportunities — evolves,
because understanding evolves. Each carries an immutable version history bound to a worldview
version, which is exactly what makes the whole layer replayable (CI-008): replay by
reconstructing the immutable Observations and the pinned worldview, then re-deriving the
evolving assessments. *Immutable perception in; evolving understanding out.*

## Open questions
- **Q-a:** Intelligence Product — composition or object? (the decision above)
- **Q-b:** Does the **Opportunity** object's canonical lifecycle (EIOS-002, frozen Part I)
  already admit a "hypothesized/candidate" state, or must that state be *named* by Part III
  without modifying EIOS-002? (Naming a state of a frozen object, not redefining it.)
- **Q-c:** Should "salience / novelty" on an Observation be a first-class annotation or derived
  by the sensing capability? (affects how Signal decomposes)
