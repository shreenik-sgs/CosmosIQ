# ARB-012 — Adversarial Validation of the Domain Intelligence Grammar

**Status:** validation artifact · **Date:** 2026-06-30 · **Book:** v5.5 (unchanged)

**Purpose:** stress-test the proposed Domain Intelligence Grammar against a *deliberately
different* domain before recommending governance. The four authored domains
(Technology/Economic/Supply/Capital) are a tight, system-and-market cluster. This trial uses the
single most divergent domain available — **Geopolitical Intelligence** — to see whether the
grammar accommodates it **without modification**.

**Constraints:** nothing here is part of the Architecture Book; the trial chapter below is a
*draft for validation only*; no chapter, marker, or ADR is created.

---

## Why Geopolitical Intelligence is the adversarial choice
Technology, Economic, Supply, and Capital are all **non-agentic system domains** — they evolve
under constraints, they don't *intend*. Geopolitics is the opposite: it is driven by
**intentional agents** (states, blocs, leaders) with **strategy, deception, deterrence, and
alliances**. It also sits closest to *policy* (the purpose-free temptation, one layer past even
capital's allocation temptation). If the grammar holds here, it generalizes.

The grammar under test:
```
DomainIntelligence(D) ::= Conform · Scope(ontology of D) · Ground(Worldview+Experience) ·
   Assess(D)=[ConstraintAssessment, ReadinessTimingAssessment, Structural*, DomainSpecific*] ·
   Influence · Compose · Sustain · PurposeFree · Handoff
```

---

## Trial chapter (DRAFT — validation only, not for the Book)

### EIOS-0xx — Geopolitical Intelligence  *(hypothetical placement; trial only)*

- **Purpose.** Geopolitical Intelligence continuously forms understanding of the geopolitical
  domain — states, blocs, power structures, and their transitions. The objective is geopolitical
  understanding, not policy and not action.
- **Conformance.** EIOS-000…010 + ADR-0008; conforms to Reality Intelligence, not to sibling
  engines. *(grammar: Conform)*
- **Conformance to the RI Contract.** Produces Intelligence Assessments; references, does not
  redefine, the canonical object; introduces no new reasoning object. *(grammar: Conform)*
- **Geopolitical Domain Scope.** Assessed subjects: states and actors (canonical **Entity**),
  alliances and rivalries (canonical **Relationship**), power structures, geopolitical
  transitions. *(grammar: Scope — reuses existing canonical objects)*
- **Grounding in Scientific Understanding.** Grounds in systems theory, constraint/resource
  understanding, economic drivers, and — heavily — **Historical Analogs** of past power
  transitions; plus any validated geopolitical Principles the Scientific Worldview contains.
  *(grammar: Ground)*
- **Geopolitical Structure Assessment.** Power balances and alliance structures. *(Structural)*
- **Geopolitical Constraint Assessment.** Resource, geographic, military, and economic
  constraints on actors; constraint release as a driver of realignment. *(mandatory: Constraint)*
- **Actor Intent Assessment.** The intent and strategic posture of an actor — a judgment about
  the *state/trajectory of an actor's intent*, with confidence, competing assessments, and
  preserved contradictions to represent ambiguity and deception. *(DomainSpecific — agency)*
- **Alliance and Power-Balance Assessment.** Formation, durability, and shift of alliances and
  balances. *(DomainSpecific — agency)*
- **Geopolitical Transition Assessment.** Realignments, escalations, and de-escalations.
  *(Structural / transition)*
- **Geopolitical Readiness and Timing Assessment.** Readiness of conditions for a transition and
  its timing; readiness kept distinct from timing; uncertainty preserved. *(mandatory:
  Readiness/Timing)*
- **Cross-Domain Geopolitical Influence.** Geopolitical assessments influence technology,
  economic, supply, and capital assessments through the Intelligence Graph. *(Influence — strong)*
- **Geopolitical Intelligence Products.** Compositions of geopolitical Assessments. *(Compose)*
- **Continuous Geopolitical Understanding.** Continuously evolving; never permanently complete.
  *(Sustain)*
- **Purpose-Free Geopolitical Intelligence.** Expresses understanding only; assigns no policy,
  no strategy, no recommended action, no opportunity. Policy and action belong downstream
  (e.g., a national-strategy consumer), never to Geopolitical Intelligence. *(PurposeFree —
  hardest case)*
- **Handoff.** Provides geopolitical Assessments and Products to the Intelligence Portfolio and
  to Genesis; grounds but does not form opportunities. *(Handoff)*
- **Rules/Requirements.** Would follow the invariant slots exactly (AR-`NN`01–03, 09–14 invariant;
  04–08 the five geopolitical assessments; REQ-GP-001…015 parallel). Not enumerated — the
  structural fit is what is under test.

---

## Reassessment — did the grammar hold? (production by production)

| Production | Held? | Notes |
|---|---|---|
| **Conform** | ✅ | produces Intelligence Assessments; no new reasoning object |
| **Scope** | ✅ | reuses **Entity** (actors) and **Relationship** (alliances) — *no new canonical object needed*, even for agents |
| **Ground** | ✅ with a shift | grounds validly, but the *mix* leans on **Historical Analogs/Experience** more than scientific Theories (see Strain 1) |
| **Assess — Constraint** | ✅ | geopolitical constraints map cleanly; mandatory production satisfied |
| **Assess — Readiness/Timing** | ✅ | timing/readiness of transitions maps; mandatory production satisfied |
| **Assess — agency (Intent/Alliance)** | ✅ as DomainSpecific | fits the open production; ambiguity/deception handled by the Assessment's confidence + preserved contradictions + competing assessments (see Strain 2) |
| **Influence** | ✅ | strong — geopolitics influences every other domain via the Intelligence Graph |
| **Compose** | ✅ | products as compositions |
| **Sustain** | ✅ | continuous understanding |
| **PurposeFree** | ✅ strongly | the hardest case holds: understanding vs policy is a clean line; *validates* the invariant |
| **Handoff** | ✅ | to Portfolio + Genesis; grounds, never forms |

**No production broke. No new canonical object was required. The invariant spine held intact.**

### Strain 1 — grounding mix (observation, not a break)
For agentic/strategic domains, grounding leans on **Historical Analogs and Experience** more than
on scientific Theories, because the Scientific Worldview's *coverage* of geopolitics is thinner
than its coverage of technology. The grammar already treats grounding sources as a domain
*parameter*, so this is accommodated — but it reveals a real dependency: **a domain's intelligence
quality tracks how much validated science the Worldview holds for that domain.** That is a
property of the worldview, not a defect of the grammar.

### Strain 2 — an agency-assessment family (observation, not a break)
Geopolitics introduces a coherent new *family* of assessments — **intent / alliance / power** —
about *intentional agents*. These fit the grammar's open "DomainSpecific" production today. But
they are the first sign of a third theme (alongside the universal Constraint and Readiness/Timing)
that **agentic domains** (geopolitical, competitive, organizational) may share. This is a
candidate future near-universal theme — to *confirm* when a second agentic domain is authored,
**not** to add now.

### What did NOT strain (notable)
- Deception/hidden intent did **not** require new machinery — confidence, contradicting evidence,
  and competing Assessments already model strategic ambiguity.
- Agents did **not** require a new canonical object — Entity and Relationship (EIOS-002) suffice.
- The purpose-free boundary did **not** weaken under policy pressure — it held most clearly of all.

---

## Verdict

**The grammar naturally accommodates Geopolitical Intelligence without modification.** The
invariant nine-step spine, the two mandatory assessments, the single-canonical-object rule, the
composition model, cross-domain influence, and — most importantly — the purpose-free boundary all
held under the most adversarial domain available. The only novelties (agency assessments) fit the
grammar's *existing* open production, and the only shift (grounding mix) is already a grammar
parameter.

Per the validation criterion: **the grammar held → recommend proceeding to ADR-0009.**

## Recommendation
1. **Proceed to ADR-0009** to elevate the Domain Intelligence Grammar to governance, as
   previously recommended.
2. **Fold two clarifications into the ADR** (refinements, not revisions — the grammar already
   permits both):
   - **Grounding is a domain parameter**, and the worldview/experience *mix* legitimately varies
     by domain (analog-heavy domains are valid); state this explicitly so analog-grounded domains
     are not seen as non-conforming.
   - **Flag the agency-assessment family** (intent/alliance/power) as a *candidate* third
     near-universal assessment theme, to be confirmed — not adopted — when a second agentic domain
     is authored.
3. **Do not pre-add** agency productions or new objects now; the open production already covers
   them, and over-fitting to one adversarial domain would repeat the premature-abstraction risk.

## Constraints honored
- Architecture Book and EIOS-010–014 **unchanged**; the trial chapter is a draft in this document
  only.
- **No ADR created.** The recommendation is to author ADR-0009 next, on the architect's decision.
