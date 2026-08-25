"""Description sourcing for published articles (M030-S01-T03).

``write_article`` requires a non-empty ``description`` (≤1024 chars,
server-enforced) — it is what meinkontext listings and search show. The
authoritative source is the article's summary row in ``knowledge/index.md``
(zero new LLM cost); fallbacks: first body paragraph, then the article stem.
"""
from __future__ import annotations

import re
from pathlib import Path

from core import frontmatter
from core.links import WIKILINK_RE, resolve_link, strip_table_escape

# Server-side cap: MAX_DESCRIPTION_LENGTH in context-mcp's write_article gate.
MAX_DESCRIPTION_LENGTH = 1024

# Placeholder for `\|` while splitting index rows on `|` — same technique as
# core.utils.read_wiki_index_compact (the row grammar's single quirk).
_PIPE_SENTINEL = "\x00"


def _links_to_text(text: str) -> str:
    """Collapse wikilinks to reader text: alias if present, else clean target."""

    def _sub(m: re.Match) -> str:
        _bang, target, _heading, alias = m.groups()
        clean, _esc = strip_table_escape(target, alias)
        if alias:
            alias_text = alias[1:].strip()
            if alias_text:
                return alias_text
        return clean

    return WIKILINK_RE.sub(_sub, text)


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _utf16_units(text: str) -> int:
    """The server validates ``description.length`` in JS — UTF-16 code units,
    where astral characters (emoji) count double. Measure the same way (live
    incident 2026-08-25: Python len passed, server rejected)."""
    return len(text.encode("utf-16-le")) // 2


def _cap(text: str) -> str:
    if _utf16_units(text) <= MAX_DESCRIPTION_LENGTH:
        return text
    units = text.encode("utf-16-le")[: (MAX_DESCRIPTION_LENGTH - 1) * 2]
    # errors="ignore" drops a half surrogate pair cut at the boundary
    return units.decode("utf-16-le", errors="ignore").rstrip() + "…"


def description_index(
    index_text: str, knowledge_dir: Path, vault: Path
) -> dict[str, str]:
    """Parse the full index (`| Article | Summary | Compiled From | Updated |`)
    into ``{knowledge-relative path: summary text}``. Rows whose Article link
    does not resolve are skipped (the audit surface for those is `wiki links`,
    not publish)."""
    source = knowledge_dir / "index.md"
    knowledge_root = knowledge_dir.resolve()
    out: dict[str, str] = {}
    for line in index_text.splitlines():
        if not line.startswith("| ") or line.startswith("| Article |"):
            continue
        safe = line.replace(r"\|", _PIPE_SENTINEL)
        cols = [c.strip().replace(_PIPE_SENTINEL, r"\|") for c in safe.split("|")]
        # Standard shape: ['', title, summary, sources, date, ''].
        if len(cols) < 6:
            continue
        m = WIKILINK_RE.search(cols[1])
        if not m:
            continue
        clean, _esc = strip_table_escape(m.group(2), m.group(4))
        resolved = resolve_link(clean, source, vault)
        if resolved is None:
            continue
        try:
            rel = resolved.relative_to(knowledge_root).as_posix()
        except ValueError:
            continue
        out[rel] = _collapse(_links_to_text(cols[2]))
    return out


def describe(rel: str, body: str, index: dict[str, str]) -> str:
    """The article's served description: index summary → first non-heading
    body paragraph (frontmatter stripped via the single grammar) → stem.
    Always non-empty, always ≤1024."""
    summary = (index.get(rel) or "").strip()
    if summary:
        return _cap(summary)

    try:
        _fm, content = frontmatter.parse(body)
    except frontmatter.FrontmatterError:
        content = body
    for para in re.split(r"\n\s*\n", content):
        lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
        text_lines = [ln for ln in lines if not ln.startswith("#")]
        if not text_lines:
            continue
        text = _collapse(_links_to_text(" ".join(text_lines)))
        if text:
            return _cap(text)

    return Path(rel).stem
