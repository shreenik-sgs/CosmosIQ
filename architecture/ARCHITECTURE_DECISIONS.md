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

## ADR-0010
Title: The Cognition–Actuation Boundary
Status: Accepted

Context:

A system that understands the world, judges what is worth pursuing, decides how to commit, and
shapes its counsel to a particular person has still done only one kind of thing: it has thought.
Every act so far — to observe, to model, to hypothesize, to assess, to recommend, to personalize —
is reversible. A belief can be revised, a judgment withdrawn, a recommendation replayed and remade,
and the world is none the wiser. Thought leaves no mark.

Action is not like this. To place capital is to change the world, and the world offers no undo. A
reasoning that proves mistaken is corrected at no cost but the correcting; an action that proves
mistaken has already happened. Between the last thought and the first deed lies the one threshold
the system cannot recross.

This decision concerns that threshold. It holds that the freedom proper to thought is not proper to
action, and that the system must therefore keep the two apart — reasoning without limit, but acting
only through a single, guarded, accountable passage.

**What can be undone may be done freely; what cannot be undone must be gated.**

Decision:

The system MAY reason, recommend, and personalize within its governed cognitive layers. It MAY
actuate only through a separate, gated, auditable layer that does nothing but carry out what has
already been decided. Cognition and actuation are different in kind and SHALL be kept apart.

This boundary establishes the following.

**Actuation is not cognition.** Execution performs operational validation, not investment reasoning.
It MAY validate account constraints, market-hours constraints, cancelability, order previews,
slippage and fill risk, reconciliation, and kill-switch conditions. But it SHALL NOT discover,
understand, identify opportunities, construct theses, allocate capital, personalize counsel, or
decide actions. It SHALL only carry out actions already approved.

**Actuation consumes decisions; it does not form them.** The actuation layer SHALL consume the
decisions handed to it — the personalized actions and the records that justify them — and SHALL
originate none of them. It receives the verdict; it never reaches it.

**Every irreversible action passes through a gate.** No actuation SHALL touch the world until it has
passed an explicit gate: confirmation by the responsible authority, a preview of what will be done,
a check that the action can still be cancelled or reversed while that remains possible, a check
against the constraints of account and venue, a check that the moment is permitted, an awareness of
the cost of imperfect execution, the standing power to halt everything at once, and a record
sufficient to account for it afterward. The gate is not a feature of actuation; it is its
precondition.

**Actuation produces operational reality.** What returns from the world — orders placed, fills
received, rejections, cancellations, exceptions, failures, and the reconciliation of intent against
outcome — are observations of reality, not judgments about it. They MAY flow upward as evidence, to
be understood like any other observation; they SHALL NEVER flow upward as purpose. The world may
inform the system; it may not instruct it.

**Broker-specific logic is implementation, not architecture.** The actuation layer SHALL define the
governance and operational state of action in the abstract — what a gate is, what an order's life
consists of, what must be reconciled. The particular venues through which action reaches the world
are matters of implementation, bound to the architecture at its edge and never written into it.

**The Order is the first operational object.** Until now every object the system has held has been a
reasoning object — a thing known, judged, or recommended: the Knowledge Object and its kin, the
Intelligence Assessment, the Opportunity, the Investment Thesis, the Personal Investment Profile. The
Order is not of this kind. It does not represent what the system believes or counsels; it represents
what the system is doing, and the state of that doing in the world. Its truth is not warrant but fact
— not "is this justified?" but "did it happen?". The Order SHALL therefore be recognized as the first
operational object — the first member of a category distinct from the reasoning objects — and SHALL
NOT be modeled as a specialized Knowledge Object. To make the record of a deed a species of knowledge
would erase, in the model itself, the very line this decision draws. The Order's justification lives
upstream, in the reasoning objects it carries out; its state is operational and its own. Where the
world answers — a fill, a rejection — that answer re-enters the system as an Observation, a reasoning
object once more. Thus the operational layer touches the world and returns observations to thought,
while remaining, in itself, not thought but action.

Relationship to prior decisions:

- This completes the ordering set down when understanding, judgment, and action were separated
  (ADR-0008). That decision named action as the last of the three and held that purpose flows only
  upward; this one reaches the end of the line — where action stops being a decision and becomes a
  deed — and gates it. Purpose still never descends; now neither does the irreversible ascend without
  a gate.
- It is consistent with the invariant grammar of understanding (ADR-0009). That grammar governs how
  the system reasons; actuation does not reason, and so stands outside the grammar rather than
  against it. The grammar shapes thought; this decision bounds the passage out of thought into the
  world.

Consequences:

- The system gains a single, narrow, accountable aperture onto the world, and no other. Everywhere
  else it is free; here alone it is gated.
- The actuation layer carries no intelligence of its own and is forbidden to acquire any; its
  discipline is governance, not judgment.
- The object model bifurcates for the first time: reasoning objects, which represent what is known
  and judged, and operational objects, which represent what is done. The bridge between them is the
  Observation — the world's answer, returning as evidence.
- The cost of error becomes visible in the architecture: because action is irreversible, its gate is
  not optional, and a system that cannot confirm, preview, reverse, or halt is not permitted to act
  at all.
- The machinery of any particular venue is kept outside the architecture, so that what is true of
  action remains true however the system is connected to the world.

This decision fixes a principle, not its mechanism. What a gate checks, how an order's states are
named, and how reconciliation is performed are left to be settled where execution is written. The
principle is this: the system may think freely and act only narrowly, and the record of a deed is not
a kind of knowledge.

---

## ADR-0011
Title: Autonomous Universe Composition
Status: Accepted

Context:

CosmosIQ was built to find what is worth watching. The slice that composes its universe says so
without hedging: it is "the slice that ENDS hand-curation." Yet the universe the system actually
watched was eight tickers and three themes, typed by a person into a deployment argument.

The sight was never missing. Run against real credentials, the discovery producers return grounded
candidates from a sector query or a theme phrase, each carrying a real filing or screener reference,
each honestly reporting the hits it could not map rather than guessing a ticker. The engine could
see. It had nowhere to put what it saw: discovery had no caller and no store, the accepted-universe
record had never once existed, and acceptance refused to run unattended.

That refusal is the reason this is a decision and not a repair. It held that the engine may never
accept on its own. It was written in no specification, no contract, and no ADR — it lived in a
docstring, which under ADR-0001 is not where architecture lives at all.

Ask what kind of act it is to admit a company into the universe. It places no capital, sends no
order, touches no venue. The record that holds it is append-only and correctable, so a later entry
supersedes it and the reasoning stands corrected at no cost but the correcting. Admitting a company
is a belief about what merits attention — and ADR-0010 has already ruled on beliefs: what can be
undone may be done freely. The gate on acceptance was the discipline reserved for irreversible
deeds, spent on a reversible thought. Nothing was protected, because no mark was ever at risk.

But the old gate was right about one thing, and it is not the thing it appeared to be about. To
accept unattended, the engine would have had to write a person's name onto a judgment that person
never made. That is not caution about capital; it is a refusal to forge a signature. Automating the
decision is safe. Automating the signature is not. That distinction is the whole of this decision.

Decision:

**Universe composition is cognition. The engine SHALL compose its own universe, and SHALL attribute
its own judgments to itself.**

**The engine MAY accept autonomously.** A grounded candidate MAY enter the universe with no human in
the loop. Membership is a reversible belief and is governed as cognition, not as actuation.

**The evidence gate is untouched.** Only a candidate grounded against a real source may be accepted.
An ungrounded candidate, an unverified suggestion, or a hit with no ticker mapping is refused.
Autonomy removes the human from the decision; it removes nothing from the evidence. What could not
be accepted by a person on the evidence SHALL NOT be accepted by the engine on the same evidence.

**Attribution SHALL be truthful.** The record SHALL name the principal that actually decided. An
engine acceptance SHALL be attributed to the engine and the policy under which it acted, never to a
person. Machine and human acceptances SHALL remain distinguishable for all time, so that any reader
asking who judged this receives a true answer.

**Reversibility is the operator's standing power.** Every engine acceptance remains correctable, and
a human correction SHALL outrank an engine acceptance. The operator's authority moves from
gatekeeper of every entry to editor of the whole — the authority appropriate to a reversible act at
scale.

**The universe is bounded by the real chokepoint structure, not by rank.** The engine SHALL admit a
company where it occupies a chokepoint that genuinely exists in the value-chain map — the scarce
capacity that gates a theme's advance. Occupancy is a structural label about the world, established
by evidence; it is not a score, a rating, or an ordering, and this decision introduces none. The
repository's standing prohibition holds without exception: there is no score, rank, or rating field
anywhere. A bound is required because sight without discrimination is noise — a sector query returns
fifty names, and fifty names is not a universe, it is a directory. Chokepoint occupancy is the
discrimination the architecture already carries, and it is finite by construction: few companies gate
a scarce capacity, which is what makes such a company worth watching at all.

**A chokepoint SHALL NOT be invented to admit a company.** Where a candidate maps to a theme whose
value-chain analysis does not really exist, the engine SHALL NOT assert a chokepoint in order to
qualify it. Such a candidate is an honest gap: it may be surfaced and monitored, and it awaits a real
analysis. The bound admits only companies standing at chokepoints that were mapped before them.

**Membership is not a claim about return.** That a company holds a defensible position is a statement
about the world. That it will multiply capital is a thesis about the future, formed downstream under
the gates that govern theses, and reached by an operator. The two SHALL NOT be conflated: the
universe records what merits attention, never what is expected to pay.

**The actuation boundary is reaffirmed.** A company in the universe is not a position. Nothing here
permits capital to move; every irreversible action passes the ADR-0010 gate in full. This decision
widens what the system may think about and widens nothing about what it may do.

**Direction is not curation.** Discovery is steered by a mandate — a sector, a theme, a phrase — and
a mandate is not a watchlist. To name a domain worth investigating states an interest and leaves the
engine to find who matters; to name the companies states the answer and leaves the engine nothing to
find. The former is legitimate architectural input and belongs in the architecture. The latter is the
practice this decision ends: a hardcoded ticker list SHALL NOT be a supported means of setting the
universe.

Consequences:
- Deployment stops carrying a ticker list; the service resolves its scope from the composed universe.
- Discovery gains a caller and a record, and may run unattended.
- Acceptance gains a truthful machine principal; it does not lose its grounding validation.
- The universe becomes mixed-provenance, and every reader must be able to show whether a company was
  admitted by the engine or by a person, and under what policy.
- Governing the universe becomes a matter of the mandate, the chokepoint map, and the correction
  record, rather than of an argument vector.
- A rule that lived only in a docstring becomes an architectural decision, closing an ADR-0001 drift.

This decision fixes a principle, not its mechanism. How the deciding principal is spelled in a
record, where the mandate is kept, and how often the engine sweeps are left to be settled where the
universe is composed. The principle is this: the system may think for itself about what is worth
watching, provided it never claims a human thought it.

---

## Next ADR Number

ADR-0012
