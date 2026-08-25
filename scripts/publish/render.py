"""Wikilink normalization for served articles (M030-S01-T02).

The producer contract serves links BY SLUG: readers on the meinkontext side
resolve `[[target-slug]]` via `get_object`, the dashboard renders them as
in-wiki navigation. Anything the remote reader cannot follow — unresolvable
targets, media embeds, articles outside the publish set (incl. the excluded
root ``index.md``) — degrades to plain text instead of dangling.

Reuses ``core.links`` primitives (incl. the private
``_strip_frontmatter_and_fences``) — in-repo single-source reuse of THE
wikilink grammar, same policy as every retargeting flow; duplicating the
fence/frontmatter walker here would be exactly the drift links.py exists to
prevent.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.links import (
    WIKILINK_RE,
    _strip_frontmatter_and_fences,
    resolve_link,
    strip_table_escape,
)


def normalize_links(
    text: str,
    source: Path,
    vault: Path,
    slug_by_relpath: dict[str, str],
) -> tuple[str, int]:
    """Rewrite ``text`` (an article at ``source``) for serving.

    - a link resolving to a published article (VAULT-relative path in
      ``slug_by_relpath``) gets its target replaced by the slug; embed-bang,
      ``#heading``, ``|alias`` and the table-escaped ``\\|`` all survive
    - every other link collapses to plain text: the alias if present, else the
      clean target (heading and bang dropped)

    Returns ``(new_text, changed_link_count)``; link-free text round-trips
    byte-identical.
    """
    vault_root = vault.resolve()
    changed = 0
    out: list[str] = []
    for _, line, live in _strip_frontmatter_and_fences(text.split("\n")):
        if not live:
            out.append(line)
            continue

        def _sub(m: re.Match) -> str:
            nonlocal changed
            bang, target, heading, alias = m.groups()
            clean, esc = strip_table_escape(target, alias)

            slug = None
            resolved = resolve_link(clean, source, vault)
            if resolved is not None:
                try:
                    rel = resolved.relative_to(vault_root).as_posix()
                except ValueError:
                    rel = None
                if rel is not None:
                    slug = slug_by_relpath.get(rel)

            if slug is not None:
                new = f"{bang}[[{slug}{heading or ''}{esc}{alias or ''}]]"
                if new != m.group(0):
                    changed += 1
                return new

            changed += 1
            if alias:
                alias_text = alias[1:].strip()
                if alias_text:
                    return alias_text
            return clean

        out.append(WIKILINK_RE.sub(_sub, line))
    return "\n".join(out), changed
