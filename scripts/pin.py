"""Pin an article to a Map-of-Content (MOC).

Usage:
    uv run python pin.py <article> [--moc NAME] [--section "Name"] [--summary "Text"]

Positional `article` accepts:
    - bare basename:           "alex"             (resolves to knowledge/people/alex.md if unique)
    - path relative to vault:  "knowledge/people/alex.md"
    - absolute path:           "/full/path/.../alex.md"

The target MOC is auto-derived from the article's `type:` frontmatter:
    type: concept     → knowledge/MOCs/concepts.md
    type: connection  → knowledge/MOCs/connections.md
    type: person      → knowledge/MOCs/people.md
    type: project     → knowledge/MOCs/projects.md
    type: area        → knowledge/MOCs/areas.md
    type: qa          → knowledge/MOCs/qa.md
Override with --moc.

The annotation summary defaults to the article's row in `knowledge/index.md`
(column 2 of the index table). Override with --summary "...".

Section is interactive when not passed: shows existing H2 sections in the
MOC plus a "(new section)" option. Pass --section "Name" to skip the
prompt; an unknown section name is created at the end of the MOC body
(before any trailing dataview block).

The script is idempotent: if the article's wikilink is already anywhere
in the MOC, it logs and exits without modifying the file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.paths import KNOWLEDGE_DIR, ROOT_DIR

TYPE_TO_MOC = {
    "concept": "concepts",
    "connection": "connections",
    "person": "people",
    "project": "projects",
    "area": "areas",
    "qa": "qa",
}


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def _resolve_article(arg: str) -> Path:
    """Resolve a user-supplied article reference to an absolute file path."""
    p = Path(arg)
    if p.is_absolute() and p.exists():
        return p.resolve()
    # try as path relative to vault root
    candidate = ROOT_DIR / arg
    if candidate.exists():
        return candidate.resolve()
    # try basename match under knowledge/, excluding MOCs themselves
    basename = p.name if p.suffix == ".md" else f"{p.name}.md"
    matches = [
        m for m in KNOWLEDGE_DIR.rglob(basename)
        if "MOCs" not in m.parts and m.is_file()
    ]
    if not matches:
        sys.exit(f"article not found: {arg}")
    if len(matches) > 1:
        print("multiple matches — pass a specific path:", file=sys.stderr)
        for m in matches:
            print(f"  {m.relative_to(ROOT_DIR)}", file=sys.stderr)
        sys.exit(1)
    return matches[0].resolve()


def _lookup_summary(wikilink_basename: str) -> str:
    """Pull a one-line summary from knowledge/index.md if a row matches."""
    idx = KNOWLEDGE_DIR / "index.md"
    if not idx.exists():
        return ""
    needle = f"[[{wikilink_basename}]]"
    needle_path_suffix = f"/{wikilink_basename}]]"
    for line in idx.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        if needle in line or needle_path_suffix in line:
            cols = [c.strip() for c in line.split("|")]
            # Index format: | [[link]] | summary | sources | updated |
            # cols[0] is empty (leading |), cols[1] is link, cols[2] is summary
            if len(cols) >= 3:
                return cols[2]
    return ""


def _existing_sections(moc_text: str) -> list[str]:
    return [l[3:].strip() for l in moc_text.splitlines() if l.startswith("## ")]


def _pick_section(sections: list[str]) -> str:
    if not sections:
        return input("No sections yet. New section name: ").strip()
    print("Existing sections:")
    for i, s in enumerate(sections, 1):
        print(f"  [{i}] {s}")
    print(f"  [{len(sections) + 1}] (new section)")
    raw = input("Pick (number or name): ").strip()
    if raw.isdigit():
        n = int(raw)
        if 1 <= n <= len(sections):
            return sections[n - 1]
        if n == len(sections) + 1:
            return input("New section name: ").strip()
    return raw


def _insert_pin(moc_path: Path, section: str, line: str) -> tuple[bool, str]:
    """Insert `line` under H2 `section`. Append section if missing.

    Returns (changed, message).
    """
    text = moc_path.read_text(encoding="utf-8")
    if line in text:
        return (False, "exact line already present")

    lines = text.splitlines()
    section_marker = f"## {section}"

    if section_marker in lines:
        idx = lines.index(section_marker)
        # End of this section = next H2, dataview-fence, or EOF
        end = len(lines)
        for j in range(idx + 1, len(lines)):
            stripped = lines[j].strip()
            if lines[j].startswith("## ") or stripped.startswith("```dataview") or stripped.startswith("```dataviewjs"):
                end = j
                break
        # Append after the last existing `- ` item in this section,
        # or right after the heading + blank line if section is empty.
        insert_at = idx + 1
        for j in range(idx + 1, end):
            if lines[j].lstrip().startswith("- "):
                insert_at = j + 1
        # Skip blank lines after the heading so the bullet stays attached
        if insert_at == idx + 1:
            while insert_at < end and lines[insert_at].strip() == "":
                insert_at += 1
        lines.insert(insert_at, line)
        msg = f"appended under '{section}'"
    else:
        # Find first dataview block to insert before; else append to EOF.
        dv_start = len(lines)
        for j, l in enumerate(lines):
            stripped = l.strip()
            if stripped.startswith("```dataview") or stripped.startswith("```dataviewjs"):
                dv_start = j
                break
        # Trim trailing blank lines from the block we keep above the dataview.
        before = lines[:dv_start]
        while before and before[-1].strip() == "":
            before.pop()
        new_block = ["", section_marker, "", line, ""]
        after = lines[dv_start:]
        lines = before + new_block + after
        msg = f"created new section '{section}'"

    moc_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return (True, msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pin an article to a MOC")
    parser.add_argument("article", help="basename, vault-relative path, or absolute path")
    parser.add_argument("--moc", help="override target MOC name (default: from `type:` frontmatter)")
    parser.add_argument("--section", help="MOC section (interactive prompt if omitted)")
    parser.add_argument("--summary", help="annotation text (default: from knowledge/index.md row)")
    args = parser.parse_args()

    article = _resolve_article(args.article)
    fm = _parse_frontmatter(article.read_text(encoding="utf-8"))

    if args.moc:
        moc_name = args.moc.removesuffix(".md")
    else:
        atype = fm.get("type")
        if not atype:
            sys.exit(
                f"no `type:` frontmatter in {article.relative_to(ROOT_DIR)} — "
                "pass --moc explicitly"
            )
        moc_name = TYPE_TO_MOC.get(atype)
        if not moc_name:
            sys.exit(
                f"no default MOC mapping for type: {atype} — pass --moc explicitly "
                f"(known types: {', '.join(TYPE_TO_MOC)})"
            )

    moc_path = KNOWLEDGE_DIR / "MOCs" / f"{moc_name}.md"
    if not moc_path.exists():
        sys.exit(
            f"MOC not found: {moc_path.relative_to(ROOT_DIR)} "
            "(create it manually or run `wiki seed`)"
        )

    basename = article.stem  # `alex.md` → `alex`

    moc_text = moc_path.read_text(encoding="utf-8")
    if f"[[{basename}]]" in moc_text or f"/{basename}]]" in moc_text:
        print(f"already pinned: [[{basename}]] in MOCs/{moc_name}.md")
        return

    summary = args.summary or _lookup_summary(basename)
    line = f"- [[{basename}]]"
    if summary:
        line += f" — {summary}"

    sections = _existing_sections(moc_text)
    section = args.section or _pick_section(sections)
    if not section:
        sys.exit("no section chosen — aborted")

    changed, msg = _insert_pin(moc_path, section, line)
    if changed:
        print(f"✓ pinned [[{basename}]] → MOCs/{moc_name}.md  ({msg})")
    else:
        print(f"no change: {msg}")


if __name__ == "__main__":
    main()
