# Architecture Backlog

**Status:** living document · **Last updated:** 2026-06-30

A parking lot for architectural ideas that have been **intentionally deferred** — preserved
without prematurely locking in decisions.

This is **not an ADR** (no decision is recorded here) and **not a TODO** (no work is
committed here). The single source of truth for the architecture remains `specification/`
(compiled from `architecture/EIOS_Architecture_Book.md`). Items graduate from this backlog
*into* an ADR, a chapter, or a roadmap once their proper context exists.

## How to use this document

- Each item has an ID (`BL-NNN`), an origin, and one or more **status tags**.
- Status tags: `Requires ADR`, `Requires Part III`, `Requires Genesis`, `Requires EIOS-010`.
- Adding an item here is a way to *not lose* an idea — not a commitment to build it.
- The Dependency Index at the bottom gives cross-cut views by status tag.

---

## Deferred Architectural Decisions

Decisions intentionally postponed until the right context exists.

### BL-001 — System Dynamics canonical ownership
- **Origin:** ARB-001 finding M-3.
- **Question:** "System Dynamics" is currently attributed to **both** EIOS-003 (World Model)
  and EIOS-005 (Systems Theory) in the Architectural Lexicon (a dual canonical owner).
- **Why deferred:** both chapters are frozen Part I (ADR-0007), and the better boundary may
  only become clear once Reality Intelligence (Part III) is written. Not a decision we need
  to make today.
- **Tags:** `Requires ADR` · `Requires Part III`

---

## Open Architectural Questions

Questions with no committed answer yet.

### BL-002 — Should the World Model become an explicit "World Graph"?
- **Origin:** ARB-001 finding L-1.
- **Question:** The World Model (EIOS-003) is already graph-structured but is not named as a
  first-class graph. Should it be promoted to a "World Graph," making the canonical graph
  inventory ten instead of nine?
- **Why deferred:** this is a large architectural question that belongs in the context of
  EIOS-010 — World Intelligence, not in isolation. We deliberately do **not** declare "nine
  graphs forever."
- **Tags:** `Requires EIOS-010`

### BL-008 — Are domain intelligence engines instances of one "Intelligence Discipline"?
- **Origin:** future review proposal ARB-012.
- **Question:** are Technology / Economic / Supply / Capital / Energy / Healthcare / Defense
  Intelligence all instances of a single reusable **Intelligence Discipline** abstraction rather
  than individually designed engines? See `ARB-012_Intelligence_Discipline_Architecture.md`.
- **Status:** **Investigated** at v5.5 (`ARB-012_Investigation_Report.md`). Reframed as a
  *canonical grammar of domain intelligence*; verdict compelling; a recommendation to define the
  grammar (extending EIOS-010) is recorded but **not implemented** — gated on ADR-0009.
- **Tags:** `Requires ADR` (ADR-0009 to define the grammar, if approved)

### BL-003 — Are five portfolio abstractions sufficient?
- **Origin:** ARB-001 architect note.
- **Question:** The architecture defines five portfolio layers (Model, Hypothesis,
  Investigation, Validation, Theory). Two further abstractions may be warranted — see BL-004
  and BL-005.
- **Tags:** `Requires Part III` · `Requires Genesis`

---

## Roadmap Candidates

Concrete capabilities likely to be added in a future part — not yet designed.

### BL-004 — Intelligence Portfolio
- **Origin:** ARB-001 architect note.
- **Idea:** a portfolio of the active **intelligence products** feeding Genesis — distinct
  from hypotheses and theories (the set of products, not the explanations).
- **Likely home:** Part III.
- **Tags:** `Requires Part III` · `Requires Genesis`

### BL-005 — Opportunity Portfolio
- **Origin:** ARB-001 architect note.
- **Idea:** a portfolio of active **scientific opportunities** being monitored as they
  evolve. Explicitly **not** an investment portfolio — a portfolio of evolving opportunities.
- **Likely home:** Genesis.
- **Tags:** `Requires Genesis`

---

## Potential Future Enhancements

Low-priority polish, intentionally not done now.

### BL-006 — Portfolio heading number agreement
- **Origin:** ARB-001 finding L-2.
- **Note:** EIOS-007 uses the plural heading "Model Portfolios"; EIOS-009 uses singular
  "X Portfolio." Purely cosmetic.
- **Tags:** *(none)*

### BL-007 — Explainability as an explicit cross-cutting principle
- **Origin:** ARB-001 finding L-5.
- **Note:** "Explainability" appears as a section in both EIOS-004 and EIOS-007. It is a
  cross-cutting concern and could be stated once and referenced — low value, expected
  duplication.
- **Tags:** *(none)*

---

## Dependency Index

Cross-cut views of the items above by status tag.

### Requires Part III
- BL-001 · BL-003 · BL-004

### Requires Genesis
- BL-003 · BL-004 · BL-005

### Requires EIOS-010
- BL-002

### Requires ADR
- BL-001
