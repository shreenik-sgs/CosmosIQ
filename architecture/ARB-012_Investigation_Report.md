# ARB-012 — Investigation: Is there a canonical grammar of domain intelligence?

**Status:** investigation report (executed) · **Date:** 2026-06-30 · **Book:** v5.5
**Inputs:** EIOS-010 (Reality Intelligence) and EIOS-011–014 (Technology / Economic / Supply
Network / Capital Intelligence); the comparative structural analysis
(`EIOS-011-014_Comparative_Structural_Analysis.md`).

**This is an architectural investigation only.** It modifies nothing in the Architecture Book,
leaves EIOS-010–014 unchanged, and — where it recommends evolution — does **not** implement it.

**Reframing (per direction):** the question is not "are these instances of an *Intelligence
Discipline*?" but "do they reveal a **canonical grammar of domain intelligence** — a reusable
reasoning process independent of any particular domain?"

---

## Method
The four domain chapters were authored independently but compared structurally. The comparison
is precise (section-for-section, rule-for-rule), so the grammar question can be answered from
evidence, not impression.

---

## Q1 — Which reasoning steps are invariant across all domain chapters?

Nine reasoning steps appear, in the same order, in all four chapters. They are the candidate
**productions of the grammar**:

| Step | What it does | Where it shows up |
|---|---|---|
| **Conform** | produce Intelligence Assessments; reference, not redefine, the canonical object | §"Conformance to the RI Contract"; AR-`NN`01–02 |
| **Scope** | declare the domain's assessed subjects | §"… Domain Scope" |
| **Ground** | bind to the Worldview + Experience assessments; recompute nothing | §"Grounding in Scientific Understanding"; AR-`NN`03 |
| **Assess** | form assessments over the scoped subjects | §positions 6–10; AR-`NN`04–08 |
| **Influence** | relate to other domains through the Intelligence Graph | §"Cross-Domain … Influence"; AR-`NN`09 |
| **Compose** | aggregate Assessments into (non-canonical) Products | §"… Intelligence Products"; AR-`NN`10 |
| **Sustain** | keep understanding continuously evolving | §"Continuous … Understanding"; AR-`NN`12 |
| **Stay purpose-free** | express understanding only; no value/opportunity | §"Purpose-Free …"; AR-`NN`11 |
| **Hand off** | provide to the Intelligence Portfolio + Genesis; ground but never form opportunities | §"Handoff"; AR-`NN`13 |

These nine steps are **invariant**: identical in intent, order, and (templated) wording across
EIOS-011–014. They account for ~74% of sections, ~64% of rules, ~67% of requirements.

## Q2 — Which concepts vary only by ontology?

Three inputs vary, and they vary **only by domain ontology** — the reasoning around them is
identical:

1. **The assessed subjects** (the ontology terminals): *technologies* / *economic systems* /
   *supply networks* / *capital*.
2. **The grounding sources**: which worldview Theories/Principles and which Experience
   assessments (ERS/RM/CRI/CAS/HAS/TTI, evolution analyses) are cited.
3. **The assessment names**: "*Technology* Constraint Assessment" vs "*Capital* Constraint
   Assessment" — same production, different ontology word.

Nothing about the *reasoning* changes between domains; only the *nouns* change. This is the
defining signature of a grammar: fixed productions, variable terminals.

## Q3 — Which concepts appear mandatory for every future domain?

Mandatory in all four (the **non-negotiable grammar**):
- Conform · Scope · Ground · Influence · Compose · Sustain · Purpose-free · Hand off, **and**
- two assessment productions that are universal so far: **Constraint Assessment** and
  **Readiness/Timing Assessment**.

Optional / ontology-driven (the **open productions**):
- structural assessments (Structure / Transition / Evolution), and
- domain-unique assessments (Technology Emergence/Convergence; Economic Value Network/Capital
  Flow; Supply Fragility; Capital Cycle/Concentration).

So a future domain *must* Conform, Scope, Ground, assess Constraints and Readiness/Timing,
Influence, Compose, Sustain, stay Purpose-free, and Hand off — and *may* add domain-unique
assessments.

## Q4 — Is the architecture revealing a reusable reasoning grammar independent of discipline?

**Yes — clearly.** Stated as a grammar:

```
DomainIntelligence(D) ::=
    Conform                                   -- to Reality Intelligence (EIOS-010)
    Scope(ontology of D)                      -- VARIABLE: the domain's assessed subjects
    Ground(Worldview + Experience)            -- VARIABLE: which artifacts are cited
    Assess(D) ::=
        ConstraintAssessment(D)               -- mandatory
        ReadinessTimingAssessment(D)          -- mandatory
        StructuralAssessment(D)*              -- common
        DomainSpecificAssessment(D)*          -- optional, ontology-driven
    Influence                                 -- cross-domain, via the Intelligence Graph
    Compose                                   -- Assessments -> Products (compositions)
    Sustain                                   -- continuous understanding
    PurposeFree                               -- understanding only
    Handoff                                   -- to the Intelligence Portfolio + Genesis
```

The productions are discipline-independent; the discipline supplies only `ontology(D)`,
`grounding(D)`, and the `Assess(D)` set. The grammar is reusable across any domain.

## Q5 — Are "Technology Intelligence," etc., better understood as instances of this grammar?

**Yes.** Each of EIOS-011–014 is `DomainIntelligence(D)` for a particular D. They were not
independently designed — they were authored by applying the same grammar to different
ontologies, which is exactly why ~70% of their content is identical. Understanding them as
*derivations of one grammar* is more accurate, and more economical, than treating them as four
bespoke engines.

## Q6 — Would such a grammar improve extensibility without reducing clarity?

**Extensibility: yes, substantially.** A new domain (Energy, Healthcare, Defense) becomes a
declaration — *ontology + grounding + assessment set* — that inherits the entire invariant spine.
New disciplines are added with no new architecture and no new reasoning objects.

**Clarity: yes, if the grammar is stated once and domains stay real.** The tension is real: a
grammar can degrade into terse configuration that hides reasoning. It is avoided by two
conditions:
1. The grammar is defined **once, canonically** (so the spine is read once, not re-derived four+
   times — which *removes* the current ~70% duplication that itself harms clarity).
2. Each domain remains a **real, named chapter** that clearly declares its ontology, its grounding
   choices, and its domain-unique assessments — the genuinely domain-specific architecture stays
   visible and first-class.

Under those conditions, a grammar **improves** clarity (one canonical reasoning process, plus
each domain's true specifics) rather than reducing it.

---

## Verdict

**The evidence is compelling.** Four independent domains exhibit one invariant nine-step
reasoning process parameterized only by ontology, two universal assessment productions, and a
shared conformance/grounding/composition/purpose-free/handoff spine. The architecture is
revealing a **canonical grammar of domain intelligence**, and the domain engines are best
understood as derivations of it.

This is also coherent with the deeper architecture: ADR-0008 made *understanding* the load-bearing
act; a grammar of domain intelligence is simply the statement that *forming domain understanding
follows one reasoning process regardless of the domain* — the epistemological layering expressed
as a generative rule.

---

## Recommendation (how the architecture should evolve — NOT implemented here)

1. **Name and define the grammar canonically** — a *Domain Intelligence Grammar* defined once,
   in Reality Intelligence (EIOS-010, which already states that the layer is realized by domain
   intelligence engines producing Intelligence Assessments). It would specify: the nine invariant
   productions; the two mandatory assessment productions (Constraint, Readiness/Timing); and the
   three parameters each domain supplies (ontology, grounding, assessment set).

2. **Domain chapters become grammar derivations** — each declares its ontology, grounding
   sources, and assessment set (mandatory + domain-unique) and inherits the spine by conformance
   to the grammar. They stay real chapters; they become leaner.

3. **Add future domains as derivations** — Energy / Healthcare / Defense Intelligence become
   declarations, not bespoke engines.

4. **Decide the retrofit** — whether to refactor EIOS-011–014 to derive from the grammar (removing
   the measured ~70% duplication) or to apply the grammar only to new domains. Recommended:
   retrofit, so the duplication does not calcify; the comparative analysis quantifies what would be
   removed.

5. **Govern it with an ADR** — this defines a new canonical structure and changes how domain
   chapters are authored; it is ADR-worthy (next number ADR-0009). The grammar would extend EIOS-010
   (not frozen), but **only after the ADR is accepted** — not in this investigation.

### Conditions and risks the ADR must address
- **Clarity guardrail:** domains remain real chapters; the grammar is a conformance contract, not
  a code generator producing configuration.
- **Generalization beyond four domains:** a structurally different domain (e.g., Defense) may need
  productions not seen yet; the grammar's *optional* productions accommodate this, but a check
  should run when the first structurally-divergent domain is authored.
- **Strengthen, don't weaken, invariants:** the grammar must *encode* purpose-freedom, the
  single-canonical-object rule, grounding-not-recomputation, and replayability — making them
  harder to violate, not softer.
- **Namespace rule:** specify a collision-safe per-domain requirement-namespace convention (the
  REQ-CP-over-REQ-CI choice during EIOS-014 authoring showed this is needed).

---

## Constraints honored
- The Architecture Book is **unchanged**; EIOS-010–014 are **unmodified**.
- This is an **investigation and recommendation only**; nothing is implemented.
- If the recommendation is approved, the first step is an **ADR**, not a manuscript edit.
