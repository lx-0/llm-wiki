"""Wikilink resolution + relativization — single source of truth.

A link in a markdown file is relative to that file. Obsidian resolves a
slash-bearing wikilink against the **vault root** (`<vault>/`, where
`.obsidian/` lives), so a nested article at `knowledge/<type>/x.md` that
writes `[[concepts/foo]]` points at the non-existent `<vault>/concepts/foo.md`
and Obsidian offers to create an empty stub. The fix: every link is rewritten
to `os.path.relpath(target, source.parent)`.

This module owns four operations, used across the engine so they never drift:

- ``resolve_link``      — locate the real file a link target points at.
- ``canonical_slug``    — the knowledge-relative id of an article (``concepts/foo``).
- ``relative_target``   — render a resolved file as a path relative to a source.
- ``relativize_text``   — rewrite every link in an article to relative form.

Consumers: the corpus relativize pass (`compile` post-pass + migration CLI),
the backlinks footer pass (`core.backlinks`), and lint's link checks.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# `[[target]]`, `![[target]]`, with optional `#heading` and `|alias`.
# Groups: 1=bang 2=target 3=heading(incl #) 4=alias(incl |)
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]#|]+)(#[^\]|]*)?(\|[^\]]*)?\]\]")

_MEDIA_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico",
    ".pdf", ".mp3", ".mp4", ".m4a", ".wav", ".mov", ".webm", ".excalidraw",
}


def has_ext(target: str) -> bool:
    """True if the link target already carries a file extension."""
    suffix = Path(target).suffix.lower()
    return suffix == ".md" or suffix in _MEDIA_EXT


def strip_table_escape(target: str, alias: str | None) -> tuple[str, str]:
    """In markdown tables the alias pipe is escaped as ``\\|``; the trailing
    ``\\`` lands at the tail of the target token. Return (clean_target, esc)
    where ``esc`` is the backslash to re-emit before the alias on output."""
    target = target.strip()
    if target.endswith("\\") and alias:
        return target[:-1], "\\"
    return target, ""


def resolve_link(link: str, source: Path, vault: Path) -> Path | None:
    """Locate the real file a link target points at, trying the historic
    resolution bases in priority order. Returns an absolute Path or None.

    Bases (first hit wins): vault-root, ``<vault>/knowledge/``, source-relative
    (so already-relative links stay idempotent). A single-hit shortest-path
    fallback covers bare media embeds whose folder we don't know up front.
    """
    link = link.strip()
    if not link:
        return None

    raw = vault / link
    knw = vault / "knowledge" / link
    src_rel = source.parent / link  # already-relative links (idempotency)

    candidates: list[Path] = []
    for base in (raw, knw, src_rel):
        if has_ext(link):
            candidates.append(base)
        else:
            candidates.append(base.with_name(base.name + ".md"))
            candidates.append(base)

    for cand in candidates:
        if cand.is_file():
            return cand.resolve()

    name = Path(link).name
    if has_ext(link):
        hits = [p for p in vault.rglob(name) if ".obsidian" not in p.parts]
        if len(hits) == 1:
            return hits[0].resolve()
    return None


def link_target(raw: str) -> str:
    """Clean target path from a raw wikilink inner string ``target#anchor|alias``
    (also handling the table-escaped ``\\|``). ``extract_wikilinks`` hands back
    the inner string verbatim; this strips the anchor + alias so callers can
    resolve the path."""
    m = WIKILINK_RE.fullmatch(f"[[{raw}]]")
    if not m:
        return raw.split("#", 1)[0].split("|", 1)[0].strip()
    target, _ = strip_table_escape(m.group(2), m.group(4))
    return target


def canonical_slug(path: Path, knowledge_dir: Path) -> str | None:
    """The knowledge-relative id of an article: ``knowledge/concepts/foo.md``
    → ``concepts/foo``. Returns None if ``path`` is not under ``knowledge_dir``
    (substrate citations to daily/raw have no backlink slug)."""
    try:
        rel = path.resolve().relative_to(knowledge_dir.resolve())
    except ValueError:
        return None
    return rel.with_suffix("").as_posix()


def relative_target(resolved: Path, source: Path, original_has_ext: bool) -> str:
    """Render ``resolved`` as a path relative to ``source.parent``, matching the
    original link's extension-presence (Obsidian resolves both forms; we
    preserve author style + minimize churn)."""
    rel = Path(os.path.relpath(resolved, source.parent)).as_posix()
    if not original_has_ext and rel.endswith(".md"):
        rel = rel[:-3]
    return rel


def relative_link_for_slug(target_slug: str, source: Path, knowledge_dir: Path) -> str:
    """Render a canonical knowledge slug (``concepts/foo``) as a link relative
    to ``source`` — used by the backlinks footer renderer."""
    resolved = (knowledge_dir / f"{target_slug}.md").resolve()
    return relative_target(resolved, source, original_has_ext=False)


def _strip_frontmatter_and_fences(lines: list[str]):
    """Yield (index, line, live) where ``live`` is False inside YAML
    frontmatter or fenced code blocks (links there are not rewritten)."""
    in_fence = False
    in_frontmatter = lines[:1] == ["---"]
    fm_closed = not in_frontmatter
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if in_frontmatter and not fm_closed:
            yield i, line, False
            if i > 0 and stripped == "---":
                fm_closed = True
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            yield i, line, False
            continue
        yield i, line, not in_fence


def relativize_text(text: str, source: Path, vault: Path) -> tuple[str, int, list[str]]:
    """Rewrite wikilinks in ``text`` to be relative to ``source``. Skips YAML
    frontmatter and fenced code blocks. Returns
    (new_text, rewritten_count, unresolved_targets)."""
    lines = text.split("\n")
    unresolved: list[str] = []
    rewritten = 0
    out: list[str] = []

    for _, line, live in _strip_frontmatter_and_fences(lines):
        if not live:
            out.append(line)
            continue

        def _sub(m: re.Match) -> str:
            nonlocal rewritten
            bang, target, heading, alias = m.groups()
            target, esc = strip_table_escape(target, alias)
            resolved = resolve_link(target, source, vault)
            if resolved is None:
                unresolved.append(target)
                return m.group(0)
            new_target = relative_target(resolved, source, has_ext(target))
            if new_target == target:
                return m.group(0)
            rewritten += 1
            return f"{bang}[[{new_target}{heading or ''}{esc}{alias or ''}]]"

        out.append(WIKILINK_RE.sub(_sub, line))

    return "\n".join(out), rewritten, unresolved


def outgoing_canonical_slugs(
    text: str, source: Path, vault: Path, knowledge_dir: Path,
    footer_begin: str, footer_end: str,
) -> set[str]:
    """Canonical knowledge-slugs this article links to (for the backlinks index).

    Resolves each body link against ``source`` and keeps only targets that live
    under ``knowledge_dir`` — daily/raw substrate citations are not backlink
    edges. Skips the managed backlinks footer, frontmatter, and code fences."""
    begin = text.find(footer_begin)
    end = text.find(footer_end)
    if begin >= 0 and end > begin:
        text = text[:begin] + text[end + len(footer_end):]

    slugs: set[str] = set()
    for _, line, live in _strip_frontmatter_and_fences(text.split("\n")):
        if not live:
            continue
        for m in WIKILINK_RE.finditer(line):
            if m.group(1):  # skip embeds (`![[...]]`)
                continue
            target, _ = strip_table_escape(m.group(2), m.group(4))
            resolved = resolve_link(target, source, vault)
            if resolved is None:
                continue
            slug = canonical_slug(resolved, knowledge_dir)
            if slug:
                slugs.add(slug)
    return slugs


def iter_articles(knowledge_dir: Path):
    """Every `.md` under ``knowledge_dir`` except `index.md` (the catalog —
    its links already resolve source-relative from `knowledge/`) and hidden
    files. Mirrors `core.backlinks`'s walk."""
    for path in knowledge_dir.rglob("*.md"):
        if path.name == "index.md" and path.parent == knowledge_dir:
            continue
        if any(part.startswith(".") for part in path.relative_to(knowledge_dir).parts):
            continue
        yield path


def run_relativize_pass(knowledge_dir: Path, vault: Path) -> dict[str, int]:
    """Rewrite every knowledge article's links to relative form. Idempotent —
    already-relative links resolve to themselves and produce no write.

    Returns ``{"articles_seen", "articles_written", "links_rewritten"}``."""
    if not knowledge_dir.exists():
        return {"articles_seen": 0, "articles_written": 0, "links_rewritten": 0}
    seen = written = total = 0
    for path in iter_articles(knowledge_dir):
        seen += 1
        try:
            original = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text, n, _ = relativize_text(original, path, vault)
        if n and new_text != original:
            path.write_text(new_text, encoding="utf-8")
            written += 1
            total += n
    return {"articles_seen": seen, "articles_written": written, "links_rewritten": total}
