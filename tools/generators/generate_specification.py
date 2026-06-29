#!/usr/bin/env python3
"""Generate the specification/ tree from the canonical Architecture Book.

Canonical source : architecture/EIOS_Architecture_Book.md
Output           : specification/

This generator is the only sanctioned way to produce specification/ content
(see ADR-0005). It parses the machine-readable markers embedded in the book and
splits each chapter into its own Markdown file. It never invents architecture:
only Parts and Chapters that physically exist between the book's BEGIN/END
fences are emitted.

Markers consumed
----------------
  <!-- BOOK-METADATA ... -->          book-level key/value metadata (book version)
  <!-- BEGIN:PART:<ID> -->  ...  <!-- END:PART:<ID> -->
  <!-- BEGIN:CHAPTER:<ID> --> ... <!-- END:CHAPTER:<ID> -->
  # PART <ROMAN> — <TITLE>            part heading (number + title)
  ## CHAPTER <CHAPTER-ID> — <TITLE>   chapter heading (stable id + title)

Output contract
---------------
  * Part  -> directory  specification/<NN>_<Title_Case>/
  * Chapter -> file      specification/<NN>_<Title_Case>/<CHAPTER-ID>_<slug>.md
    (the filename comes from the chapter's canonical <!-- SLUG: ... --> directive,
    never from its display title).
  * The front-matter `## Glossary` -> specification/00_Glossary/Glossary.md, the
    single normative architectural dictionary.
  * Every generated file begins with a YAML front-matter header marking it
    generated and prohibiting manual edits (ADR-0005): generated, generated_from,
    chapter_id (or kind: summary | glossary), book_version, source_hash, manual_edits.
    source_hash is the SHA-256 of the canonical Architecture Book.
  * BEGIN/END markers and SLUG directives are NOT carried into generated files.
  * specification/SUMMARY.md is regenerated as an index and links the Glossary.

Usage
-----
  python3 tools/generators/generate_specification.py            # generate
  python3 tools/generators/generate_specification.py --check    # dry run, no writes
  python3 tools/generators/generate_specification.py \
      --book PATH --out PATH                                     # override paths

Exit status is non-zero on any parse/consistency error so the generator can be
wired into CI as a drift check.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# Repo root = two levels up from tools/generators/<this file>.
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOOK = REPO_ROOT / "architecture" / "EIOS_Architecture_Book.md"
DEFAULT_OUT = REPO_ROOT / "specification"

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

# Em dash (—) is the canonical separator in book headings; tolerate a hyphen too.
DASH = r"[—\-]"

PART_HEADING_RE = re.compile(
    rf"^#\s+PART\s+(?P<roman>[IVXLCDM]+)\s+{DASH}\s+(?P<title>.+?)\s*$",
    re.MULTILINE,
)
PART_BEGIN_RE = re.compile(r"<!--\s*BEGIN:PART:(?P<id>[A-Z0-9_]+)\s*-->")
CHAPTER_BLOCK_RE = re.compile(
    r"^##\s+CHAPTER\s+(?P<id>[A-Z]+-\d+)\s+" + DASH + r"\s+(?P<title>.+?)\s*$"
    r"(?P<preamble>.*?)<!--\s*BEGIN:CHAPTER:(?P=id)\s*-->"
    r"(?P<body>.*?)"
    r"<!--\s*END:CHAPTER:(?P=id)\s*-->",
    re.MULTILINE | re.DOTALL,
)
# Canonical slug directive, e.g. <!-- SLUG: world-model -->. It lives between the
# chapter heading and the BEGIN marker so it never leaks into generated content.
SLUG_RE = re.compile(r"<!--\s*SLUG:\s*(?P<slug>[a-z0-9][a-z0-9-]*)\s*-->")
METADATA_RE = re.compile(r"<!--\s*BOOK-METADATA(?P<body>.*?)-->", re.DOTALL)
# Front-matter Glossary: from the `## Glossary` heading to the next `---` rule.
GLOSSARY_RE = re.compile(
    r"^##\s+Glossary\s*$\n(?P<body>.*?)\n---\s*$",
    re.MULTILINE | re.DOTALL,
)


class GenerationError(Exception):
    """Raised on any condition that would otherwise risk inventing architecture."""


def roman_to_int(roman: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(roman.upper()):
        val = ROMAN_VALUES[ch]
        total += -val if val < prev else val
        prev = max(prev, val)
    return total


def title_case(title: str) -> str:
    """`FOUNDATION` -> `Foundation`, `SYSTEMS SCIENCE` -> `Systems Science`."""
    return " ".join(word.capitalize() for word in title.split())


def part_dir_name(number: int, title: str) -> str:
    """`I`, `FOUNDATION` -> `01_Foundation`."""
    return f"{number:02d}_{title_case(title).replace(' ', '_')}"


def chapter_file_name(chapter_id: str, slug: str) -> str:
    """`EIOS-003`, `world-model` -> `EIOS-003_world-model.md`.

    Filenames are built from the chapter's canonical slug, never from its display
    title, so retitling a chapter never renames its generated file.
    """
    return f"{chapter_id}_{slug}.md"


def parse_book_version(text: str) -> str:
    match = METADATA_RE.search(text)
    if not match:
        raise GenerationError("BOOK-METADATA block not found in the Architecture Book.")
    for line in match.group("body").splitlines():
        line = line.strip()
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    raise GenerationError("BOOK-METADATA block has no `version:` field.")


def parse_glossary(text: str) -> str:
    """Return the front-matter Glossary body (intro + table), without its heading."""
    match = GLOSSARY_RE.search(text)
    if not match:
        raise GenerationError(
            "Front-matter `## Glossary` section not found. The Glossary is the "
            "canonical architectural dictionary and SHALL be present."
        )
    return match.group("body").strip("\n")


def parse_parts(text: str) -> list[dict]:
    """Slice the book into parts, then collect each part's chapters."""
    headings = list(PART_HEADING_RE.finditer(text))
    if not headings:
        raise GenerationError("No `# PART <ROMAN> — <TITLE>` headings found.")

    parts = []
    for i, heading in enumerate(headings):
        start = heading.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        segment = text[start:end]

        begin = PART_BEGIN_RE.search(segment)
        if not begin:
            raise GenerationError(
                f"Part '{heading.group('title')}' is missing its BEGIN:PART marker."
            )

        number = roman_to_int(heading.group("roman"))
        chapters = []
        for cm in CHAPTER_BLOCK_RE.finditer(segment):
            slug_match = SLUG_RE.search(cm.group("preamble"))
            if not slug_match:
                raise GenerationError(
                    f"Chapter {cm.group('id')} is missing a `<!-- SLUG: ... -->` "
                    "directive. Filenames are derived from canonical slugs, never "
                    "from display titles."
                )
            chapters.append(
                {
                    "id": cm.group("id"),
                    "title": cm.group("title").strip(),
                    "slug": slug_match.group("slug"),
                    "body": cm.group("body").strip("\n"),
                }
            )

        parts.append(
            {
                "id": begin.group("id"),
                "number": number,
                "title": heading.group("title").strip(),
                "dir": part_dir_name(number, heading.group("title").strip()),
                "chapters": chapters,
            }
        )
    return parts


def render_chapter(
    chapter: dict, book_rel: str, book_version: str, source_hash: str
) -> str:
    header = (
        "---\n"
        "generated: true\n"
        f"generated_from: {book_rel}\n"
        f"chapter_id: {chapter['id']}\n"
        f"book_version: {book_version}\n"
        f"source_hash: {source_hash}\n"
        "manual_edits: prohibited\n"
        "---\n\n"
    )
    title_line = f"# {chapter['id']} — {chapter['title']}\n\n"
    body = chapter["body"].strip("\n")
    return header + title_line + body + "\n"


def render_glossary(
    body: str, book_rel: str, book_version: str, source_hash: str
) -> str:
    header = (
        "---\n"
        "generated: true\n"
        f"generated_from: {book_rel}\n"
        "kind: glossary\n"
        f"book_version: {book_version}\n"
        f"source_hash: {source_hash}\n"
        "manual_edits: prohibited\n"
        "---\n\n"
    )
    return header + "# Glossary\n\n" + body.strip("\n") + "\n"


def render_summary(
    parts: list[dict], book_rel: str, book_version: str, source_hash: str
) -> str:
    lines = [
        "---",
        "generated: true",
        f"generated_from: {book_rel}",
        "kind: summary",
        f"book_version: {book_version}",
        f"source_hash: {source_hash}",
        "manual_edits: prohibited",
        "---",
        "",
        "# EIOS Unified Specification",
        "",
        f"Generated from `{book_rel}` (book version {book_version}).",
        "",
        "## Glossary",
        "",
        "- [Glossary](00_Glossary/Glossary.md) — the normative architectural dictionary",
        "",
    ]
    for part in parts:
        lines.append(f"## Part {part['number']} — {title_case(part['title'])}")
        lines.append("")
        if not part["chapters"]:
            lines.append("_No chapters defined in the book yet._")
            lines.append("")
            continue
        for ch in part["chapters"]:
            rel = f"{part['dir']}/{chapter_file_name(ch['id'], ch['slug'])}"
            lines.append(f"- [{ch['id']} — {ch['title']}]({rel})")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def plan_outputs(
    parts: list[dict],
    glossary_body: str,
    out_dir: Path,
    book_rel: str,
    version: str,
    source_hash: str,
):
    """Return list of (path, content) tuples without touching disk."""
    outputs = [
        (out_dir / "SUMMARY.md", render_summary(parts, book_rel, version, source_hash)),
        (
            out_dir / "00_Glossary" / "Glossary.md",
            render_glossary(glossary_body, book_rel, version, source_hash),
        ),
    ]
    for part in parts:
        for ch in part["chapters"]:
            path = out_dir / part["dir"] / chapter_file_name(ch["id"], ch["slug"])
            outputs.append(
                (path, render_chapter(ch, book_rel, version, source_hash))
            )
    return outputs


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", type=Path, default=DEFAULT_BOOK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Parse and report planned files without writing anything.",
    )
    args = parser.parse_args(argv)

    if not args.book.exists():
        print(f"error: Architecture Book not found: {args.book}", file=sys.stderr)
        return 2

    raw = args.book.read_bytes()
    text = raw.decode("utf-8")
    try:
        version = parse_book_version(text)
        glossary_body = parse_glossary(text)
        parts = parse_parts(text)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # source_hash is the SHA-256 of the canonical source file named by
    # generated_from, so a generated file can be checked for drift against the
    # current Architecture Book (e.g. `shasum -a 256 <book>`).
    source_hash = hashlib.sha256(raw).hexdigest()
    book_rel = args.book.resolve().relative_to(REPO_ROOT).as_posix()
    outputs = plan_outputs(parts, glossary_body, args.out, book_rel, version, source_hash)

    chapter_count = sum(len(p["chapters"]) for p in parts)
    print(
        f"Book version {version}: {len(parts)} part(s), {chapter_count} chapter(s)."
    )
    for path, _ in outputs:
        resolved = path.resolve()
        try:
            rel = resolved.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = resolved.as_posix()
        print(f"  {'plan' if args.check else 'write'}: {rel}")

    if args.check:
        print("Dry run — no files written.")
        return 0

    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(f"Generated {len(outputs)} file(s) under {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
