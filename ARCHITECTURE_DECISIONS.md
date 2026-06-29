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

## Next ADR Number

ADR-0005
