# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

SGS Genesis is the specification repository for **EIOS** — an Economic Intelligence Operating System. At this stage the repo contains **specifications and governance documents only**; there is no application code, build system, or test suite yet. The top-level directories `implementation/`, `generated/`, `tools/`, `research/`, and `docs/` exist (created by `bootstrap_repository.sh`) but are currently empty placeholders for future work.

Treat this as a **document/architecture repository**, not a software project. Most work here is authoring and refining Markdown specifications under governance rules — not editing code.

## Governance — read these before changing anything

Three files define the rules that override normal instincts. Read them when in doubt:

- `PROJECT_CONTEXT.md` — mission, guiding philosophy, repository principles, definition of done.
- `ARCHITECTURE_DECISIONS.md` — the Architecture Decision Register (ADR).
- `specification/SUMMARY.md` — table of contents and completion status for the 11 specification Parts.

Non-negotiable rules derived from these:

- **`specification/` is the single source of truth** (ADR-0001). Architecture is *never* defined in code, generated artifacts, or top-level docs — only in `specification/`.
- **Markdown is canonical** (ADR-0002). DOCX/PDF/XLSX are *generated artifacts*. Never treat a `.docx` as authoritative or hand-edit one as a source.
- **The top-level directory structure is frozen** (ADR-0003). Do not add, rename, or reorganize top-level directories. New capabilities fit into the existing structure.
- **Architectural changes require a new ADR** (ADR-0004) — added, never edited in place; prior ADRs are superseded, not rewritten. The next ADR number is tracked at the bottom of `ARCHITECTURE_DECISIONS.md` (currently ADR-0005) — increment it when you add one.
- **Define each concept exactly once.** Cross-reference other spec files instead of duplicating a definition.

## Specification layout and conventions

`specification/` is organized into 11 numbered Parts (`01_Foundation` … `11_Reference`; see `SUMMARY.md`). Each spec file follows a naming convention: a Part-specific prefix + zero-padded number + title, e.g. `EIOS-001_Mission.md` (Foundation), `SYS-002_Layers_of_Reality.md` (Systems Science). When adding a file, continue the existing prefix and numbering for that Part and add it to `SUMMARY.md`.

Existing spec files are intentionally terse stubs (often one or two sentences stating what the document defines). When expanding the specification, match this concise, definitional style.

### Heading hierarchy (permanent — never deviate)

Within the Architecture Book and the content it generates, headings map to structure exactly as follows:

| Level | Meaning |
|-------|---------|
| `#` | PART |
| `##` | CHAPTER |
| `###` | Major Section |
| `####` | Definition / Principle / Requirement |
| `#####` | Example |

Book front/back matter (book title, `## Preface`, `## Book Status`, `# GENERATION CONTRACT`) sits outside this hierarchy. Constitutional invariants live in their own `CI-NNN` namespace (defined in `EIOS-000`); do not reuse or renumber the `FI-NNN` invariants already defined inside other chapters. Every chapter ends with a `### Cross References` section; non-root chapters declare `Conforms To: EIOS-000`.

## The `archive/` directory

`archive/` holds the original v1 source material — `GPSR_*`, `GPMA_*`, `Volume_0_*`, etc. — in paired `.md` + `.docx` form. These are the **legacy/reference drafts being distilled** into the new numbered `specification/` Parts. They are historical input, **not authoritative**. Mine them for content when authoring specs, but the canonical version is whatever lands in `specification/`.

## Workflow

- One logical Git commit per change; one coherent capability per commit; keep history clean (`PROJECT_CONTEXT.md` §5).
- Commit messages follow Conventional Commits with a scope, e.g. `feat(specification): add Systems Science`, `docs: establish architecture decision register`.
- "Definition of Done" for a capability requires spec + tests + implementation + docs + replay validation (`PROJECT_CONTEXT.md` §8) — relevant once implementation work begins.

## Commands

`bootstrap_repository.sh` (re)creates the frozen directory skeleton and the empty root docs. It is idempotent-ish (uses `mkdir -p` / `touch`) and is normally only run once at repo inception — there is no reason to re-run it during routine work.

There is no build, lint, or test tooling in the repo yet.
