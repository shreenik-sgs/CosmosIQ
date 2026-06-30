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

## Next ADR Number

ADR-0008
