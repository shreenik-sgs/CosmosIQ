# ARB-012 — Intelligence Discipline Architecture (future review proposal)

**Status:** Proposed — **deferred** (future architectural investigation) · **Recorded:** 2026-06-30

**This is not an implementation task and not an immediate backlog item.** It captures a possible
architectural pattern for review *after several domain intelligence chapters have been authored*.
Do not act on it now. Do not change EIOS-010. Do not change ADR-0008. Do not redesign the
architecture on the basis of this note.

## Trigger
Run this review once enough domain intelligence chapters exist to compare — e.g., after
Technology, Economic, Supply Network, and Capital Intelligence have been authored (and ideally
before authoring a long tail such as Energy, Healthcare, Defense, …).

## Context
EIOS-010 (Reality Intelligence) establishes the layer and its single canonical object, the
Intelligence Assessment. Each domain intelligence engine authored after it (Technology Intelligence
first) conforms to the same Reality Intelligence contract and adds domain-specific scope and
grounding. As more are written, a reusable shape may become visible: *conform to the Reality
Intelligence contract + supply domain specifics + produce Intelligence Assessments.*

## Hypothesis
Technology Intelligence, Economic Intelligence, Supply Intelligence, Capital Intelligence, Energy
Intelligence, Healthcare Intelligence, Defense Intelligence, and others may all be **instances of a
single reusable architectural abstraction — an "Intelligence Discipline"** — rather than
individually designed engines.

## Questions to investigate
- What defines an Intelligence Discipline?
- Which architectural properties are mandatory for one?
- Can new disciplines be added **without changing the architecture**?
- Is Reality Intelligence **composed of** Intelligence Disciplines?
- Does Genesis **orchestrate Intelligence Disciplines** rather than bespoke engines?
- Is there a reusable architectural pattern emerging across all domain intelligence chapters?

## What a positive finding might imply (for the review to weigh — not to pre-decide)
- A canonical **Intelligence Discipline** abstraction (likely owned by Reality Intelligence) that
  domain chapters *instantiate* rather than re-derive.
- New disciplines added purely as instances — no architectural change, no new reasoning objects.
- Genesis orchestrating a *set of disciplines* through one uniform interface.

## Constraints on the future review
- Preserve EIOS-010 and ADR-0008 unless the review itself produces an ADR.
- Minimize new canonical objects (the Intelligence Assessment should remain the atom).
- Treat any abstraction as a *pattern over existing chapters*, not a redesign of them.

## Why deferred
The pattern can only be judged honestly against several *real* domain chapters. Abstracting after
one or two would risk premature generalization; abstracting after several lets the genuine
commonalities (and genuine differences) speak for themselves.

> Cross-reference: this sits alongside the Architecture Backlog. It is a *review proposal*, not a
> committed change.
