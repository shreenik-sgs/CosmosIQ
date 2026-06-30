# Part III — The Intelligence Assessment (canonical object design)

**Status:** design document · **Date:** 2026-06-30 · **Grounded in:** ADR-0008 (three cognitive
layers), the Part III design brief, and the canonical-currencies analysis (which established
this as the *single* new canonical object Part III requires). **Not authoritative architecture;
modifies nothing in the Book; does not draft EIOS-010.**

The Intelligence Assessment is the atom of Domain Intelligence — the one first-class canonical
object the Reality Intelligence layer introduces. This document specifies it so EIOS-010 can
formalize it directly.

---

## 1. Definition

An **Intelligence Assessment** is a single, evidence-grounded judgment about the **state or
trajectory of some aspect of a domain**, formed by the Reality Intelligence layer against a
specific version of the Scientific Worldview, carrying confidence and full provenance, and
continuously re-evaluable.

It answers the Layer-2 question — *"what is true about this aspect of this domain, and where is
it going?"* — and nothing beyond it. It is the unit Reality Intelligence forms, compares,
challenges, revises, and packages.

## 2. Governance — no frozen Part I change required

The Intelligence Assessment is a **specialized Knowledge Object**. It **conforms to** the
"Canonical Structure of a Knowledge Object" already defined in EIOS-002 (the mandatory minimum
fields) and adds specialized attributes, which EIOS-002 explicitly permits:
*"Additional attributes MAY be defined by specialized object types"* and *"The canonical
structure SHALL remain backward compatible."*

Introducing it follows an **established precedent**: EIOS-009 introduced **Scientific Theory**
and EIOS-008 introduced **Candidate Scientific Law** as specialized object types not present in
EIOS-002's enumerated categories — without amending EIOS-002. The Intelligence Assessment is
introduced the same way, by Part III. EIOS-002 is *referenced, not redefined* (line 1000), and
frozen Part I is untouched.

## 3. Canonical structure

### 3a. Inherited (from EIOS-002 — no restatement, only conformance)
The Assessment carries every mandatory Knowledge-Object field: Object Identifier · Canonical
Name · Object Type (= `Intelligence Assessment`) · Version Identifier · Lifecycle State ·
Confidence · Provenance Chain · Supporting Evidence · Contradicting Evidence · Relationships ·
Temporal Validity · Historical Lineage · Responsible Agent · Last Verification · Replay Status.

Most of what an Assessment needs is therefore *already* canonical — a strong sign it is the
right, economical atom.

### 3b. Specialized attributes (added by this object type)
1. **Assessed Subject** — the domain Entity/Concept the judgment is about. An Assessment is
   always *about something*; the subject references existing canonical objects, never a new one.
2. **Judgment** — the assertion itself: the assessed state and/or trajectory of the subject.
3. **Assessment Modality** — *illustrative, open:* state · trajectory · comparative · causal ·
   readiness · timing. Distinguishes "X is in state Y" from "X is heading toward Y."
4. **Worldview Binding** — the **Scientific Worldview version** the Assessment was formed
   against, plus references to the Part II artifacts it grounds in (validated Theories /
   Principles and the scientific assessments ERS · TTI · CRI · CAS · HAS). This is the
   load-bearing link to Layer 1 and the key to replay and change-propagation.
5. **Salience** — *optional:* relevance / novelty / urgency. This is what lets an Assessment
   carry the **Signal** role (an "emerging signal" is simply a high-salience Assessment over
   salient Observations); it is why Signal needs no object of its own.

That is the entire specialized surface: **Subject, Judgment, Modality, Worldview Binding, and
(optional) Salience.** Everything else is inherited.

## 4. Lifecycle and states

The Assessment's lifecycle is **owned by Part III** (Reality Intelligence) — exactly as
Research Question's lifecycle is owned by EIOS-004 while its structure is owned by EIOS-002, and
as Opportunity's lifecycle is owned by Genesis (Q-b). EIOS-002 owns the `Lifecycle State`
*field*; Part III owns its *values and semantics*.

*Illustrative, open* states:

```
Proposed → Substantiated → Active → Revised → Superseded / Retired
```

- **Proposed** — formed, not yet grounded.
- **Substantiated** — grounded in Worldview vN + evidence.
- **Active** — the current best assessment of its subject.
- **Revised** — updated after belief revision or new evidence (new version; prior preserved).
- **Superseded / Retired** — replaced by a stronger assessment, or no longer relevant.

Per EIOS-002, **every state transition itself becomes a historical event** — the lifecycle is
fully auditable.

## 5. Evolution, belief revision, and replay

- **Versioned, not mutated.** An Assessment evolves as understanding evolves, but every
  *version* is immutable and preserved; the object as a whole has an evolving HEAD with full
  Historical Lineage. (Mirrors Scientific Validation and the Worldview.)
- **Worldview-bound.** Because each version pins a Worldview version and references immutable
  Observations, it is **replayable** (CI-008): reconstruct the pinned worldview and the
  immutable inputs, re-derive the Assessment version.
- **Change propagation.** When Part II's understanding shifts — belief revision (AR-0952) or
  validation drift (AR-0958) — the affected Assessments are flagged via the ADR-0008/contract
  Change-Propagation interface and re-evaluated into a new (Revised) version. **No stale
  beliefs; nothing silently overwritten.**

This realizes the currencies insight directly: *immutable perception in, evolving understanding
out* — the Assessment is the "evolving understanding," the Observation the "immutable
perception."

## 6. Relationships and graph (reuse, do not reinvent)

Assessments relate to one another — support, contradict, refine, depend-on, supersede — through
the **inherited `Relationships` field**. Part III SHOULD express the resulting graph by building
on the existing **Intelligence Graph (EIOS-006)**, not by minting a parallel structure (design
brief risk K4). Whether the Intelligence Graph is extended or projected is an EIOS-010 authoring
detail; no new graph object is proposed here.

## 7. Placement under ADR-0008

- **Layer 2 (Domain Intelligence).** The Assessment is the atom of this layer.
- **Understanding flows up.** Assessments feed Intelligence Products (compositions) and then
  Genesis. They **never flow down** into Part II — that would contaminate the purpose-free core.
- **Grounds in, never mutates, Part II.** It *reads* the Worldview (version-pinned) and *cites*
  scientific assessments; it never writes to Part II objects.
- **Carries no purpose.** An Assessment expresses *understanding only* — never what is worth
  doing about it. Opportunity, value, and investability are Layer 3 (Genesis). This keeps
  intelligence formation honest, per ADR-0008.

## 8. What an Intelligence Assessment is NOT (boundary sharpening)

| Not a… | Because |
|---|---|
| **Hypothesis** (EIOS-002) | a Hypothesis is a candidate *scientific* explanation (Layer 1); an Assessment is a *domain* judgment grounded in already-validated understanding (Layer 2). |
| **Prediction** (EIOS-002) | a Prediction is about future state only; an Assessment spans current state, trajectory, and comparison. |
| **Fact** (EIOS-002) | a Fact is settled; an Assessment carries confidence/uncertainty and evolves. |
| **Opportunity** (EIOS-002) | an Opportunity is *what is worth pursuing* (Layer 3); an Assessment is *what is understood* (Layer 2). It grounds opportunity formation but is not an opportunity. |

## 9. Minimization scorecard

| Part III currency | Disposition |
|---|---|
| **Intelligence Assessment** | **the one new canonical object** (specialized Knowledge Object) |
| Observation | reused (EIOS-002) |
| Opportunity | reused (EIOS-002); candidate state = "Opportunity Hypothesis" (Q-b) |
| Signal | not an object — Observation + Assessment(salience); detection is a capability |
| Intelligence Product | composition of Assessments (Q-a) |
| Intelligence Portfolio · Opportunity Portfolio | compositions |

**One new atom for an entire new architectural layer — and even it is mostly the existing
canonical Knowledge-Object structure.** Frozen Part I is untouched; no ADR is required to
introduce it.

## 10. Ready for EIOS-010
Nothing in this design blocks authoring. The only non-blocking authoring details are: Q-c
(Observation salience as annotation vs. derived), and whether the assessment graph extends or
projects the EIOS-006 Intelligence Graph (§6). Both are settled inside EIOS-010, not before it.
