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

## Next ADR Number

ADR-0006
