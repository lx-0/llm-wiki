"""Corpus-wide backlinks materialization (M020).

Walks `<vault>/knowledge/`, builds the inverse-wikilink index
``{slug: sorted([incoming_slugs])}``, and writes a sentinel-managed
``## Backlinks`` footer into each article so AI agents reading the markdown
directly get backlink information without a corpus-wide ripgrep.

Links are stored relative to each article (a link in a markdown file is
relative to that file — see `core.links`). The inverse index is keyed on
*canonical* knowledge-slugs (`concepts/foo`); the footer renderer converts
each incoming canonical slug back to a link relative to the article it is
written into.

Design intent: see `.ytstack/OFFICE-HOURS-backlinks-footer.md` (Approach B,
chosen 2026-05-17). Sentinel pattern mirrors `collectors/calendar_collector.py`.
"""

from __future__ import annotations

from pathlib import Path

from core.links import (
    canonical_slug,
    outgoing_canonical_slugs,
    relative_link_for_slug,
)

# Region the pass owns. Content above/below is operator-or-compiler territory
# and must survive across runs.
BACKLINKS_BEGIN = "<!-- backlinks:begin -->"
BACKLINKS_END = "<!-- backlinks:end -->"


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

    Outgoing links are resolved against each source article and canonicalized
    to knowledge-slugs; only knowledge→knowledge edges count (daily/raw
    substrate citations are dropped). Self-links are dropped; duplicates
    collapse; incoming lists are alphabetically sorted."""
    vault = knowledge_dir.parent
    incoming: dict[str, set[str]] = {}
    for path in _iter_articles(knowledge_dir):
        src = canonical_slug(path, knowledge_dir)
        if src is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for tgt in outgoing_canonical_slugs(
            text, path, vault, knowledge_dir, BACKLINKS_BEGIN, BACKLINKS_END
        ):
            if tgt == src:
                continue
            incoming.setdefault(tgt, set()).add(src)
    return {tgt: sorted(srcs) for tgt, srcs in incoming.items()}


def _render_footer(incoming_slugs: list[str], article: Path, knowledge_dir: Path) -> str:
    """Render the sentinel-managed `## Backlinks` block, each incoming
    canonical slug as a link relative to ``article``."""
    lines = [BACKLINKS_BEGIN, "", "## Backlinks", ""]
    lines.extend(
        f"- [[{relative_link_for_slug(slug, article, knowledge_dir)}]]"
        for slug in incoming_slugs
    )
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


def write_backlinks_footer(
    article_path: Path, incoming_slugs: list[str], knowledge_dir: Path
) -> bool:
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
    footer = _render_footer(incoming_slugs, article_path, knowledge_dir)
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
        slug = canonical_slug(path, knowledge_dir)
        if slug is None:
            continue
        incoming = index.get(slug, [])
        if write_backlinks_footer(path, incoming, knowledge_dir):
            written += 1
    return {"articles_seen": seen, "articles_written": written}
