# ARCHITECTURE_DECISIONS.md

# Architecture Decision Register (ADR)

Status: Active

This file records all permanent architectural decisions for the EIOS platform.
No architectural decision may be changed without adding a new ADR.
Previous ADRs are never edited to change history; they may only be superseded.

---

## ADR-0001
Title: Unified Specification is the Single Source of Truth
Status: Accepted

Decision:
The `specification/` directory is the only authoritative source for platform architecture.

Consequences:
- Implementation must conform to the specification.
- Generated artifacts are derived from the specification.
- Architecture is never defined in code.

---

## ADR-0002
Title: Markdown is Canonical
Status: Accepted

Decision:
Markdown files are the canonical representation of the specification.

Consequences:
- DOCX and PDF are generated artifacts.
- Repository reviews occur against Markdown.

---

## ADR-0003
Title: Repository Structure is Frozen
Status: Accepted

Decision:
The top-level repository structure is frozen.

Top-level directories:
- specification/
- implementation/
- generated/
- tools/
- research/
- docs/
- archive/

Consequences:
- New capabilities fit within the existing structure.
- Reorganization requires a new ADR.

---

## ADR-0004
Title: Architectural Changes Require ADRs
Status: Accepted

Decision:
Any proposal that changes architecture must be documented as a new ADR before implementation.

Consequences:
- Architectural drift is prevented.
- Design rationale is preserved.

---

## ADR-0005
Title: Architecture-First Generation Workflow
Status: Accepted

Context:
ADR-0001 named `specification/` the single source of truth. The introduction of
`architecture/EIOS_Architecture_Book.md` (the Architecture Book) establishes a
canonical layer above `specification/`. This ADR records that change of ordering.

Decision:
- The Architecture Book (`architecture/EIOS_Architecture_Book.md`) is the canonical
  architectural source of truth.
- The `specification/` directory is a generated artifact derived from the Book.
- Generation is performed only by `tools/generators/generate_specification.py`.
- Only Parts and Chapters that exist in the Book are generated; missing chapters
  are never invented.
- Every generated file carries a YAML front-matter header marking it generated and
  prohibiting manual edits:
    generated, generated_from, chapter_id, book_version, manual_edits.
- The Book's BEGIN/END part and chapter markers are not carried into generated files.
- The Architecture Book is never modified by the generator and is changed only on
  explicit human instruction.

Relationship to prior ADRs:
- Refines ADR-0001: `specification/` is authoritative for downstream implementation
  but is itself generated from, and subordinate to, the Architecture Book.
- Consistent with ADR-0002: Markdown remains canonical; the Book is Markdown.

Consequences:
- Specification content is edited by changing the Book and regenerating.
- Manual edits to `specification/` are prohibited and may be overwritten on the next
  generation; the generator can run in `--check` mode as a CI drift gate.
- Architectural change still flows through ADRs (ADR-0004).

---

## ADR-0006
Title: Freeze the Constitution
Status: Accepted

Context:
EIOS-000 — Constitution of EIOS defines the platform's constitutional invariants
(CI-001 … CI-016). It is marked Constitution Status: Stable. Constitutional law
must be more stable than ordinary architectural content.

Decision:
- The Constitution (chapter EIOS-000) is a frozen artifact.
- Constitutional changes SHALL NOT be made by ordinary manuscript patch.
- A constitutional change requires all of:
  - a new ADR that explicitly supersedes the affected invariant,
  - architecture review,
  - explicit human approval.

Consequences:
- The CI-NNN constitutional invariants are durable across the lifetime of the
  platform; subsystems may rely on them without fear of silent change.
- Manuscript patches (AB-xxxx) may add or modify non-constitutional chapters but
  may not alter EIOS-000.
- This decision is consistent with ADR-0004 (architectural changes require ADRs)
  and raises the bar specifically for constitutional change.

---

## ADR-0007
Title: Freeze Foundation Release 2.0
Status: Accepted

Context:
Part I — Foundation (chapters EIOS-000 through EIOS-006) is complete, consolidated
(AB-0006A), and reviewed end-to-end at Book v1.5. It provides the stable
architectural base for all downstream chapters and implementation.

Decision:
- Chapters EIOS-000 through EIOS-006 are designated Foundation Release 2.0 and are
  FROZEN.
- Changes to these seven chapters require a new ADR (with architecture review and
  explicit approval), not an ordinary manuscript patch.
- The freeze applies to the Foundation chapters ONLY. It does NOT freeze:
  - the Architecture Book as a whole — the book version continues to increment;
  - the Appendices and other reference material (Architecture Registry, Architectural
    Dictionary/Lexicon, Graph Taxonomy, Architectural Patterns, Notation, Acronyms,
    diagrams), which evolve independently and continuously;
  - future Parts (II–V) and chapters (EIOS-007 and beyond).

Relationship to prior ADRs:
- Extends ADR-0006 (which froze EIOS-000, the Constitution) to the entire Foundation.
- Consistent with ADR-0004 (architectural changes require ADRs).

Consequences:
- Manuscript patches (AB-xxxx) may add new chapters (EIOS-007+) and evolve
  appendices, but may not modify EIOS-000 … EIOS-006.
- Reference material is documentation: it continues to evolve freely without an ADR.
- Source (Foundation chapters) freezes; documentation (appendices) evolves.

---

## ADR-0008
Title: Separation of Scientific Understanding, Domain Intelligence, and Opportunity Generation
Status: Accepted

Context:
Reality exists independently. The purpose of EIOS is not to predict reality, nor to optimize
decisions, but to progressively understand reality. That progression separates naturally into
three fundamentally different cognitive acts —

Scientific Understanding → Domain Understanding → Opportunity Formation

— each of which answers a different question, requires different reasoning, and must remain
architecturally independent.

The Cognitive Architecture has so far built only the first: it forms a continuously evolving,
best-supported scientific understanding of reality — a Scientific Worldview. That understanding
is necessary for the mission but not sufficient. Understanding reality scientifically is not the
same as understanding a domain of reality well enough to recognize what is emerging within it;
and recognizing what is emerging is not the same as deciding what is worth acting on.

As the architecture turns outward toward the world, three temptations press on it:
- to give the scientific core a purpose, so it can "just produce the answer";
- to treat domain understanding as a thin application of the worldview rather than a discipline
  in its own right;
- to fuse the recognition of opportunity with the formation of understanding, so the system can
  go from reality to recommendation in a single step.

Each trades long-term integrity for short-term convenience. This decision records why the
architecture resists all three.

Decision:
The architecture SHALL maintain three distinct layers of cognition, separated on principle.

1. Scientific Understanding.
   The Cognitive Architecture forms understanding of reality as such, and SHALL remain free of
   purpose. A scientific instrument is trustworthy precisely because it does not know which
   answer would be preferable. The core may come to know a great deal about particular domains —
   semiconductors, biology, economics — and that is not contamination; those are scientific
   subjects. What contaminates science is wanting a particular answer. Purpose is the
   contaminant: science must never know which answer would be preferable. That is what keeps it
   a reusable, trustworthy instrument rather than a special-purpose tool that ages and
   accumulates bias.

2. Domain Intelligence — a first-class layer (Reality Intelligence).
   Forming domain-specific understanding — continuously synthesizing observations, the worldview,
   historical experience, and assessments into living understanding of a domain as it is and as
   it is becoming — is itself a first-class cognitive act, not an application of the science
   engine. It SHALL be its own architectural layer, of the same stature as Scientific
   Understanding and held to the same rigor: replayable, explainable, challengeable, revisable.
   Giving it its own layer lets domain understanding evolve continuously and independently, and
   keeps purpose out of the scientific core.

3. Opportunity Generation — separated from intelligence formation (Genesis).
   Deciding what is worth pursuing is a different act from understanding what is true. If the two
   are fused, the desire for an opportunity will bias the understanding that justifies it — the
   same contamination, one layer higher. Opportunity Generation SHALL be separated from Domain
   Intelligence: it consumes finished, conformant intelligence rather than forming it. This keeps
   intelligence formation honest — it forms understanding without knowing which conclusion would
   be lucrative — and lets opportunity generation orchestrate across many domains without
   entangling itself in any one of them.

**Understanding flows upward through these layers; purpose never flows downward.** Reality is
sensed, understood scientifically, understood as domains, and only then weighed for opportunity
— and no later layer's desire is permitted to shape an earlier layer's understanding.

Why Part III therefore exists:
Part III exists to be the layer of Domain Intelligence — the faculty by which the system
continuously forms domain-specific understanding of the world out of its purpose-free science.
Without it, the architecture is a science engine with no sustained understanding of any actual
domain. With it, the science becomes usable without being corrupted.

Relationship to prior ADRs:
- Extends the intent of ADR-0006 (Constitution frozen) and ADR-0007 (Foundation frozen): the
  purpose-free core is the thing those freezes protect; this ADR explains why that core must
  stay pure as the architecture turns outward.
- Consistent with ADR-0001 (specification is the single source of truth) and ADR-0004
  (architectural change requires an ADR): the separation established here is architectural and
  governs every downstream layer.

Consequences:
- The Cognitive Architecture remains a reusable scientific instrument free of purpose; no
  downstream purpose may be encoded into it.
- Domain Intelligence is built and reasoned about as a first-class layer, not an application; it
  depends on the scientific core, never the reverse.
- Opportunity Generation consumes intelligence; it does not form it. It may orchestrate across
  domains but may not reach back into how understanding is formed.
- The separation is a permanent architectural invariant: any future capability must locate
  itself in exactly one of these three layers, and understanding must never be shaped by purpose
  from a layer above.

The architecture therefore places understanding before judgment, and judgment before action.
That ordering is a permanent invariant.

The concrete expression of this decision — the naming, sequencing, and placement of the chapters
that realize these layers — is recorded in the Part III design materials, not here. This ADR
fixes the principles; the design brief carries the mechanics.

---

## ADR-0009
Title: The Invariant Grammar of Domain Understanding
Status: Accepted

Context:
It is tempting to believe that each kind of thing demands its own kind of understanding — that
to understand a technology is one craft, to understand an economy another, to understand a
balance of power a third. This decision records the discovery that it is not so.

When understanding was built, separately and without coordination, for domains as unlike one
another as technology, economics, supply, and capital, the results came out the same. Not the
same in what they concluded — they concerned different worlds — but the same in how they
reasoned. Each grounded itself in what was already known; each assessed the state and movement
of its subject; each related that subject to others; each held its conclusions open to revision;
and each refused to mistake understanding for judgment. Only the subject differed.

A harder test followed. A domain was chosen for its distance from the rest — the domain of
intention itself, whose actors hold purposes, form alliances, and practice deception. If any
subject would demand a new way of reasoning, this one would. It did not. The same reasoning
understood it unchanged. Intention and deceit were not new ways of reasoning; they were only new
things to reason about.

What this reveals is not a convenience of construction. It is a fact about understanding. To
understand a domain is not a craft peculiar to that domain. It is the turning of one invariant
reasoning process toward a particular reality.

Decision:
Understanding SHALL follow one invariant reasoning grammar, whatever the domain being understood.
How understanding is formed does not change with what is understood. A domain does not bring its
own manner of reasoning. It brings only what it is about. A domain contributes new reality, not
new reasoning.

A domain contributes three things, and nothing more:
  - its ontology — the subjects it concerns;
  - its grounding — the validated understanding and accumulated experience it draws upon;
  - its assessments — the particular judgments it forms.

All else is the grammar, and is everywhere the same: to ground reasoning in what is known rather
than to invent it; to assess the state and the trajectory of a subject; to relate each subject
to the others; to gather particular judgments into a larger understanding; to hold that
understanding always open to revision; to remain free of purpose; and to pass understanding
onward without acting upon it.

Two clarifications, each weighed against the hardest case, belong to this decision.

First: grounding is a parameter of the domain, not a variation of the grammar. A domain may rest
mostly upon established science, mostly upon the memory of history, or upon any mixture of the
two. The proportion belongs to the domain; the act of grounding belongs to the grammar. A domain
that reasons chiefly from historical likeness does not bend the rule but answers it, with what
that domain has been given to know. How deeply a domain can be understood therefore follows from
how much reality has so far disclosed about it — a limit of knowledge, never of method.

Second: where a domain concerns intentional actors, it appears to share a family of judgments —
of intent, of alliance, of power. This is set down as an observation awaiting confirmation, not
as law. It SHALL NOT be raised into the grammar on the testimony of a single domain. The grammar
already receives such judgments as a domain's own contribution; the architecture SHALL NOT
generalize from one case what only many can establish.

Relationship to prior decisions:
- This deepens the decision that set understanding apart from judgment, and judgment from action
  (ADR-0008). That decision made understanding its own act; this one states the law within that
  act — that understanding, wherever it turns, takes a single form.
- It keeps faith with the rule that each thing is defined once, and the rule that architecture
  changes only by deliberate decision (ADR-0004). The grammar is such a structure and is held to
  those rules; to inscribe it into the working specification is a separate act, reserved for
  later.

Consequences:
- Understanding is one process turned upon many realities, not many processes.
- A new domain is understood by naming what it concerns, what it draws upon, and what it judges —
  never by inventing a new way to reason. To extend understanding to a new domain is to admit a
  new reality, not to build a new engine.
- Reasoning may not quietly diverge from the grammar. Where a domain seems to require a different
  way of reasoning, that is cause to examine the grammar, not to fork it.
- The grammar carries the deeper commitments forward and makes them harder to break: that
  understanding serves no purpose of its own; that it rests upon a single kind of judgment; that
  it is grounded rather than invented; and that it can always be retraced.
- The understandings already built are, seen rightly, instances of this grammar. To bring them
  into open accordance with it is a separate undertaking, to be taken up only if this decision is
  carried into the working architecture, and not before.

This decision fixes a principle, not its expression. Where the grammar is written, and how a
domain declares what it concerns, what it draws upon, and what it judges, are left to be settled.
The principle is this: understanding has one form, and a domain supplies only what it is about.

---

## Next ADR Number

ADR-0010
