# Part III — The Intelligence Assessment (canonical object — complete semantic contract)

**Status:** design document (complete contract) · **Date:** 2026-06-30 · **Grounded in:**
ADR-0008, the Part III design brief, and the canonical-currencies analysis (with decisions
Q-a/Q-b). **Not authoritative architecture; modifies nothing in the Book; does not draft
EIOS-010.** This supersedes the earlier first-pass design of this object.

The Intelligence Assessment is the atom of Domain Intelligence — the *only* new canonical object
the Reality Intelligence layer introduces. Every Reality Intelligence engine (Technology,
Economic, Supply Network, Capital, …) produces Intelligence Assessments; everything else in
Part III composes, aggregates, prioritizes, compares, or orchestrates them.

---

## 0. Governance (precondition)

The Intelligence Assessment is a **specialized Knowledge Object**: it *conforms to* EIOS-002's
"Canonical Structure of a Knowledge Object" and adds specialized attributes, which EIOS-002
explicitly permits (*"Additional attributes MAY be defined by specialized object types"*;
*"backward compatible"*). It is introduced downstream by Part III exactly as EIOS-009 introduced
**Scientific Theory** and EIOS-008 introduced **Candidate Scientific Law** — types not in
EIOS-002's enumerated categories, added without amending it. **Frozen Part I is untouched; no
ADR is required.**

---

## 1. Canonical Definition

An **Intelligence Assessment** is a single, evidence-grounded, worldview-versioned judgment about
the **state or trajectory of one specified aspect of a domain**, formed by the Reality
Intelligence layer against a pinned version of the Scientific Worldview, carrying confidence and
full provenance, and continuously re-evaluable.

It is the point at which **general, domain-agnostic scientific understanding becomes specific,
situated domain understanding** — the hinge between Layer 1 (science) and Layer 3 (opportunity).

Distinguished from:

| Object | It is… | The Assessment differs because… |
|---|---|---|
| **Observation** (EIOS-002) | a raw, immutable perception with no truth value | an Assessment is an *interpreted judgment* over observations; it carries confidence and evolves |
| **Evidence** (EIOS-002) | a validated observation with provenance | Evidence *supports*; an Assessment *concludes* (tentatively) from evidence |
| **Hypothesis** (EIOS-002) | a candidate *scientific* explanation (Layer 1) | a Hypothesis asks "could this explain reality?"; an Assessment asks "what is the case in this domain, given validated science?" — it consumes validated understanding, it does not form it |
| **Scientific Theory** (EIOS-009) | an integrated, validated explanatory framework (Layer 1) | a Theory explains *how reality works in general*; an Assessment *applies* theories to judge a *specific domain situation now* |
| **Scientific Worldview** (EIOS-009) | the total best-supported scientific understanding (Layer 1) | the Worldview is the *lens*; an Assessment is *what is seen through it* in a domain, bound to a worldview version |
| **Intelligence Product** | a composition that *packages* Assessments for consumers | packaging is not cognition; the Assessment is the reasoning unit, the Product the package |

**Unique role:** it is the single canonical place where validated science is *situated* into a
domain — translating "how reality works" into "what is happening here and where it is going" —
**without yet asking what is worth doing** (that is Layer 3).

---

## 2. Purpose

An Intelligence Assessment answers exactly one Layer-2 question about its subject:

> *"What is the current best understanding of this aspect of this domain — its state, what is
> changing, where it is heading, and why it matters — given the validated worldview?"*

Decomposed (the canonical sub-questions):
- **What is currently emerging?** — state / emergence.
- **What is changing?** — trajectory / direction.
- **Why does it matter?** — *significance in understanding terms* (scientific/structural
  importance) — **not** value or opportunity.
- **What is the current understanding within this domain?** — the situated synthesis.

**Relationship to Scientific Understanding.** Scientific Understanding (Layer 1) produces
domain-agnostic truth (theories, principles, worldview, the readiness/timing metrics). An
Intelligence Assessment **applies** that truth to a specific domain aspect to form situated
understanding. It **consumes** the worldview; it **never alters** it (understanding flows up,
never down). Crucially, even "why it matters" stays inside *understanding* — an Assessment may
note structural significance, but **assigns no value and no opportunity**; that is Genesis.

---

## 3. Canonical Attributes

Most of what an Assessment needs is *inherited* from the canonical Knowledge-Object structure —
a strong sign it is the right, economical atom. The recommended complete set:

### Inherited (from EIOS-002 — conformance only, not restated)
Object Identifier · Canonical Name · Object Type (`Intelligence Assessment`) · Version Identifier
· Lifecycle State · Confidence · Provenance Chain · Supporting Evidence · Contradicting Evidence ·
Relationships · Temporal Validity · Historical Lineage · Responsible Agent · Last Verification ·
Replay Status.

### Specialized (added by this object type)
| Attribute | Meaning |
|---|---|
| **Assessment Scope** | the assessed Subject (a domain Entity/Concept) *and* its boundary/scale — what exactly is being assessed, and at what granularity. An Assessment is always about *one* scoped subject (atomicity). |
| **Assessment Type** | the modality — *illustrative, open:* state · trajectory · comparative · causal · readiness · timing. Distinguishes "X is in state Y" from "X is heading toward Y." |
| **Current Assessment** | the judgment itself — the current assertion about the subject. |
| **Significance** | why it matters *in understanding terms* (structural/scientific importance); explicitly carries **no** value/opportunity semantics. |
| **Worldview Version** | the pinned Scientific Worldview version the Assessment was formed against — the linchpin of replay and change-propagation. |
| **Scientific Grounding** | references to the Layer-1 artifacts the judgment rests on: Supporting Scientific Theories/Principles, the readiness/timing metrics where applicable (**ERS, RM, CRI, CAS, HAS, TTI**), and Historical Analogs (EIOS-008). Referenced/cited, never recomputed or redefined. |
| **Salience** *(optional)* | relevance / novelty / urgency — what lets an Assessment carry the **Signal** role (an "emerging signal" is a high-salience Assessment over salient Observations), which is why Signal needs no object of its own. |
| **Rationale** *(optional)* | a rendered narrative of the reasoning — the human-facing explainability surface, derived from the grounding. |

### Derived (not separately stored — computed from the above)
- **Assessment Confidence Evolution** — the confidence trajectory across versions (from
  Historical Lineage + per-version Confidence). A *view*, not a field.
- **Explainability** — guaranteed by Provenance + Scientific Grounding + Worldview Version.
- **Replayability** — guaranteed by Worldview Version + immutable inputs.
- **Supporting Observations** — reachable through the Provenance Chain (Evidence derives from
  Observations); no separate field needed.

**Recommendation:** the specialized surface is just **Scope, Type, Current Assessment,
Significance, Worldview Version, Scientific Grounding** (+ optional Salience, Rationale).
Everything else is inherited or derived. No further attributes are required.

---

## 4. Lifecycle

**Recommendation: separate two orthogonal axes** the candidate list conflated — *maturity*
(a lifecycle state) and *confidence direction* (a derived momentum). This mirrors the
architecture's own precedent (EIOS-008 separates **Readiness** from **Readiness Momentum**).

**Lifecycle State** (the inherited EIOS-002 field; *values owned by Part III*, semantics owned
by Genesis-style downstream precedent; *illustrative, open*):

```
Emerging → Developing → Active → Superseded → Archived
```
- **Emerging** — newly formed; minimal grounding; subject just entering attention.
- **Developing** — accumulating grounding; confidence forming.
- **Active** — the current, substantiated best understanding of its subject.
- **Superseded** — replaced by a stronger Assessment of the same subject (preserved).
- **Archived** — no longer current/relevant; retained for replay.

**Confidence Trajectory** (a *derived* descriptor, **not** a lifecycle state):
`Strengthening · Stable · Weakening`. This is where the candidate "Strengthening/Weakening"
belong — they are momentum on the confidence axis, not maturity states.

**Contested** is recommended as an orthogonal *flag*, not a state: an Assessment may be
`Active` *and* `Contested` when unresolved contradicting evidence is present.

Per EIOS-002, **every state transition itself becomes a historical event** — the lifecycle is
fully auditable.

---

## 5. Evolution

An Assessment evolves by producing a **new immutable version**; the prior version is preserved.
Triggers:

| Trigger | Effect |
|---|---|
| **New observations** | re-evaluate; may strengthen/weaken/refine → new version |
| **Contradictory evidence** | recorded in Contradicting Evidence; may set `Contested` / shift Confidence Trajectory; **never discarded** (contradictions preserved) |
| **Scientific worldview revision** | the linchpin path: belief revision (AR-0952) / validation drift (AR-0958) propagate via the ADR-0008 contract's Change-Propagation interface → the Assessment is **flagged and re-evaluated** against the new Worldview Version → new version (possibly `Superseded`) |
| **Readiness changes** | grounding metrics (ERS/TTI/CRI/…) update in EIOS-008 → re-evaluate |
| **Historical reinterpretation** | EIOS-008 reinterprets cases/analogs → Assessments grounded in them are flagged → re-evaluate |
| **Confidence evolution** | each version carries Confidence; the trajectory is derived; the full evolution is preserved in Historical Lineage |

**Replay of prior versions.** Each version is immutable and pins its Worldview Version + grounding
+ inputs. Any past version is replayed exactly by reconstructing that pinned worldview and the
immutable Observations/Evidence as-of-then, then re-deriving. The Assessment is a *chain of
immutable versions* (Historical Lineage) with an evolving HEAD — **nothing is overwritten;
superseded versions remain replayable** (CI-008). *Immutable perception in, evolving
understanding out.*

---

## 6. Graph Relationships

**Recommendation: reuse the existing Intelligence Graph (EIOS-006); do not mint an "Assessment
Graph."** Intelligence Assessments are a node type in the Intelligence Graph; their relationships
are edges. Canonical edge types (*illustrative, open*):

| Edge | Connects an Assessment to… |
|---|---|
| **supported-by** | its grounding — Evidence/Observations (Knowledge Graph) and Scientific Theories (Theory Graph) |
| **derived-from** | prior versions or source Assessments (lineage) |
| **contradicts** | Assessments asserting incompatible judgments (preserved, not eliminated) |
| **supersedes** | the Assessment version it replaces |
| **complements** | Assessments that jointly inform a fuller picture |
| **depends-on** | Assessments whose validity this one rests on |
| **influences** | Assessments whose subject this one affects — **the cross-domain edge** (e.g., a supply Assessment influences a capital Assessment), enabling cross-domain intelligence |

**Canonical model:** the Intelligence Graph is the Layer-2 reasoning fabric; its *supported-by*
edges connect outward to the Layer-1 graphs (Evidence/Validation/Theory/Knowledge), and its
outputs feed Layer-3 (Genesis). The graphs **interconnect**; they do not duplicate. The
`influences` edge is the architectural carrier of cross-domain analogical reasoning (ARB-002 Cap
9).

---

## 7. Relationship to Existing Canonical Objects (reference-only; no redefinition)

| Object | Interaction (one-directional, upward; never redefines the object) |
|---|---|
| **Observation** | the Assessment *grounds in* and *interprets* immutable Observations; never modifies them |
| **Evidence** | cited as Supporting/Contradicting Evidence (inherited fields); consumed, not redefined |
| **Hypothesis** | *indirect only* — hypotheses become validated Theories via the Part II pipeline; the Assessment grounds in those Theories. It never competes with or reopens scientific hypotheses |
| **Scientific Theory** | *applied* and *cited by version* (Scientific Grounding); the Assessment situates a general theory into a domain case; it never alters the theory |
| **Scientific Worldview** | *bound to a version* (Worldview Version); read-only — the Assessment reads the worldview and never writes to it |
| **Opportunity** | the Assessment *grounds* opportunity formation but **is not** an Opportunity; Genesis consumes Assessments to form Opportunities (and the candidate "Opportunity Hypothesis" state, Q-b). The Assessment stops at understanding |

Every interaction is a **reference/grounding** relationship — citing and consuming existing
canonical objects, never redefining any (EIOS-002 line 1000 honored).

---

## 8. Architectural Principles

Governing principles for all Intelligence Assessments:

- **P1 — Current understanding, not permanent truth.** An Assessment is the best *current*
  understanding of its subject; never final.
- **P2 — Continuously evolving.** It re-evaluates as observations, evidence, worldview, and
  readiness change.
- **P3 — Replayable.** Every version is reconstructable from its pinned worldview + immutable
  inputs (CI-008).
- **P4 — Uncertainty-preserving.** Confidence and contradictions are preserved, never hidden or
  eliminated.
- **P5 — Worldview-versioned.** Every Assessment binds the worldview version it was formed
  against.
- **P6 — Explainable.** Its reasoning is reconstructable from its grounding.
- **P7 — Purpose-free (understanding only).** It expresses domain understanding, never value or
  opportunity — the Layer-2 expression of ADR-0008 (*understanding flows up; purpose never down*).
- **P8 — Grounded, never free-floating.** No assertion without provenance; an ungrounded
  Assessment is invalid.
- **P9 — Single-subject atomicity.** One Assessment is about one scoped subject; broader pictures
  are *composed* (Products), never crammed into one Assessment.
- **P10 — Conforms, never redefines.** As a specialized Knowledge Object it conforms to the
  EIOS-002 structure and references existing objects without redefining them.

---

## 9. Deliverable — maturity verdict

**Verdict: READY.** The Intelligence Assessment is sufficiently mature to serve as the foundational
canonical object for all Reality Intelligence chapters. Basis:

- **Complete, minimal attribute set** — mostly inherited; specialized surface is six fields
  (+two optional).
- **Clean lifecycle** — maturity states with an orthogonal, derived confidence trajectory and a
  contested flag.
- **Well-defined evolution and replay** — worldview-bound, immutable versioned, change-propagated.
- **Reused graph model** — the EIOS-006 Intelligence Graph, interconnected with the Layer-1
  graphs; no proliferation.
- **Reference-only relationships** to existing objects — nothing redefined; freeze intact.
- **Ten governing principles** consistent with ADR-0008 and the architecture's invariants.
- **Zero frozen-Part-I impact**; introduced as a specialized Knowledge Object (precedent:
  Scientific Theory).

**Sufficiency for downstream:** every Reality Intelligence engine produces Intelligence
Assessments; Intelligence Products compose them; Intelligence Portfolios aggregate them; Genesis
consumes them to form Opportunities. No other Part III reasoning object is required.

**Non-blocking authoring details (settled inside EIOS-010, not before):** Q-c (Observation
salience as annotation vs. derived); whether to materialize the optional Rationale attribute; and
the exact Intelligence-Graph edge taxonomy. None blocks authoring.
