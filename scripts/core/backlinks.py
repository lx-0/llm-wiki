"""Corpus-wide backlinks materialization (M020).

Walks `<vault>/knowledge/`, builds the inverse-wikilink index
``{slug: sorted([incoming_slugs])}``, and writes a sentinel-managed
``## Backlinks`` footer into each article so AI agents reading the markdown
directly get backlink information without a corpus-wide ripgrep.

Design intent: see `.ytstack/OFFICE-HOURS-backlinks-footer.md` (Approach B,
chosen 2026-05-17). Sentinel pattern mirrors `collectors/calendar_collector.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

# Region the pass owns. Content above/below is operator-or-compiler territory
# and must survive across runs.
BACKLINKS_BEGIN = "<!-- backlinks:begin -->"
BACKLINKS_END = "<!-- backlinks:end -->"

# `[[slug]]`, `[[slug|alias]]`, `[[slug#heading]]`, `[[slug#heading|alias]]`.
# The capture group keeps only the slug portion (before `#` or `|`).
_WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")

# Match fenced code blocks (``` or ~~~) so wikilinks inside are ignored.
_FENCE_RE = re.compile(r"^(```|~~~)", re.MULTILINE)


def _strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block (``--- … ---``) if present."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end < 0:
        return text
    return text[end + len("\n---\n"):]


def _strip_code_fences(text: str) -> str:
    """Drop content inside ``` or ~~~ fenced blocks (links there are illustrative)."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _outgoing_slugs(text: str) -> set[str]:
    """Return the set of slugs this article links to.

    Skips frontmatter, code-fences, and the backlinks footer itself (so a
    rewrite of an existing footer doesn't double-count the slugs inside it)."""
    # Strip the managed region first — its content is computed output, not source.
    begin = text.find(BACKLINKS_BEGIN)
    end = text.find(BACKLINKS_END)
    if begin >= 0 and end > begin:
        text = text[:begin] + text[end + len(BACKLINKS_END):]
    body = _strip_frontmatter(text)
    body = _strip_code_fences(body)
    return {m.group(1).strip() for m in _WIKILINK_RE.finditer(body) if m.group(1).strip()}


def _article_slug(path: Path, knowledge_dir: Path) -> str:
    """Path-relative slug as engine wikilinks see it.

    Convention (matches `core.utils.wiki_article_exists`): a wikilink
    `[[concepts/foo]]` resolves to `<knowledge>/concepts/foo.md`. So the
    canonical slug of `knowledge/concepts/foo.md` is `concepts/foo`.
    Articles directly under `knowledge/` (e.g. `index.md`) become bare
    stems."""
    rel = path.relative_to(knowledge_dir).with_suffix("")
    return rel.as_posix()


def _iter_articles(knowledge_dir: Path):
    """Yield every `.md` in the knowledge dir except `index.md` and any
    hidden file (those that start with `.`)."""
    for path in knowledge_dir.rglob("*.md"):
        if path.name == "index.md" and path.parent == knowledge_dir:
            continue
        if any(part.startswith(".") for part in path.relative_to(knowledge_dir).parts):
            continue
        yield path


def build_backlinks_index(knowledge_dir: Path) -> dict[str, list[str]]:
    """Return ``{target_slug: sorted([source_slug, …])}`` for every article
    in ``knowledge_dir`` that has at least one incoming link.

    Outgoing-edge extraction strips frontmatter + fenced code blocks. Self-links
    are dropped. Multiple links from the same source to the same target collapse
    to one entry. Stable ordering: incoming lists are alphabetically sorted."""
    incoming: dict[str, set[str]] = {}
    for path in _iter_articles(knowledge_dir):
        src = _article_slug(path, knowledge_dir)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for tgt in _outgoing_slugs(text):
            if tgt == src:
                continue
            incoming.setdefault(tgt, set()).add(src)
    return {tgt: sorted(srcs) for tgt, srcs in incoming.items()}


def _render_footer(incoming_slugs: list[str]) -> str:
    """Render the sentinel-managed `## Backlinks` block."""
    lines = [BACKLINKS_BEGIN, "", "## Backlinks", ""]
    lines.extend(f"- [[{slug}]]" for slug in incoming_slugs)
    lines.append("")
    lines.append(BACKLINKS_END)
    return "\n".join(lines)


def _strip_existing_footer(text: str) -> str:
    """Remove the managed region (and any surrounding blank lines) from `text`.

    Idempotent: returns `text` unchanged if no sentinel is present."""
    begin = text.find(BACKLINKS_BEGIN)
    end = text.find(BACKLINKS_END)
    if begin < 0 or end < begin:
        return text
    end_full = end + len(BACKLINKS_END)
    head = text[:begin].rstrip()
    tail = text[end_full:]
    if head and not tail.startswith("\n"):
        return head + tail
    return head + tail.lstrip("\n")


def write_backlinks_footer(article_path: Path, incoming_slugs: list[str]) -> bool:
    """Update (or remove) the sentinel-managed `## Backlinks` block in
    ``article_path``.

    Returns True if the file was rewritten, False if no change was needed
    (idempotency guard so unchanged corpora produce zero churn)."""
    try:
        original = article_path.read_text(encoding="utf-8")
    except OSError:
        return False

    stripped = _strip_existing_footer(original)

    if not incoming_slugs:
        new_text = stripped if stripped.endswith("\n") else stripped + "\n"
        if new_text == original:
            return False
        article_path.write_text(new_text, encoding="utf-8")
        return True

    body = stripped.rstrip()
    footer = _render_footer(incoming_slugs)
    new_text = (body + "\n\n" + footer + "\n") if body else (footer + "\n")
    if new_text == original:
        return False
    article_path.write_text(new_text, encoding="utf-8")
    return True


def run_backlinks_pass(knowledge_dir: Path) -> dict[str, int]:
    """Build the backlinks index and write footers across the entire corpus.

    Returns ``{"articles_seen": N, "articles_written": M}``. ``articles_seen``
    counts every article visited (regardless of incoming-link state);
    ``articles_written`` counts those whose contents actually changed."""
    if not knowledge_dir.exists():
        return {"articles_seen": 0, "articles_written": 0}

    index = build_backlinks_index(knowledge_dir)
    seen = 0
    written = 0
    for path in _iter_articles(knowledge_dir):
        seen += 1
        slug = _article_slug(path, knowledge_dir)
        incoming = index.get(slug, [])
        if write_backlinks_footer(path, incoming):
            written += 1
    return {"articles_seen": seen, "articles_written": written}
