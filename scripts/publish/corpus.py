"""Corpus → contract-shaped mapping for ``wiki publish`` (M030-S01).

Pure functions, no network. The slug rules mirror the SERVER side exactly:
context-mcp re-slugifies ``write_article``'s ``name`` via ``slugifySkillName``
(packages/core/src/validation/skill-validation.ts:152-158), so every slug we
persist locally must be a fixpoint of that function — otherwise the manifest
id and the server article id diverge and retraction (`delete_object` by id)
silently misses (architect review 2026-08-25, issue 2).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from core.links import iter_articles
from core.paths import STATE_DIR
from core.state_store import StateStore

# write_article's name cap server-side (skill-validation.ts:29). The slug
# function itself does NOT truncate — overlong names are rejected upstream,
# so we reject them here before they ever reach the wire.
MAX_NAME_LENGTH = 120

DEFAULT_MANIFEST_PATH = STATE_DIR / "publish.json"

# slugifySkillName strips exactly the Combining Diacritical Marks block
# (U+0300..U+036F) after NFKD — not every combining mark. Port faithfully; do
# not "improve". chr()-constructed so no invisible literals live in source.
_COMBINING_DIACRITICS = re.compile(f"[{chr(0x0300)}-{chr(0x036F)}]")
_NON_ALNUM_RUN = re.compile(r"[^a-z0-9]+")
_HYPHEN_TRIM = re.compile(r"^-+|-+$")


class PublishCollisionError(RuntimeError):
    """Two articles map to the same slug even after disambiguation."""


def server_slug(name: str) -> str:
    """Exact port of context-mcp's ``slugifySkillName``. May return ``""`` —
    callers must reject that (the TS docstring makes the same demand)."""
    folded = _COMBINING_DIACRITICS.sub("", unicodedata.normalize("NFKD", name))
    return _HYPHEN_TRIM.sub("", _NON_ALNUM_RUN.sub("-", folded.lower()))


def map_slugs(
    knowledge_dir: Path, previous: dict[str, str] | None = None
) -> dict[str, str]:
    """Assign a flat global slug to every article under ``knowledge_dir``.

    Returns ``{slug: knowledge-relative posix path}``. Walk = ``iter_articles``
    (root ``index.md`` and hidden files excluded there). Deterministic and
    input-order-independent: entries and base-slug groups are processed in
    sorted order.

    Rules:
    - stability: a path present in ``previous`` keeps its slug (retraction ids
      must not drift when a newcomer collides with an established slug)
    - a contested base slug (shared by several new articles, or already taken)
      disambiguates EVERY contested newcomer to ``server_slug(parent-stem)``
    - an empty slug or a collision surviving disambiguation is a hard error
    """
    entries: list[tuple[str, Path]] = []
    for path in sorted(iter_articles(knowledge_dir)):
        rel = path.relative_to(knowledge_dir).as_posix()
        if len(path.stem) > MAX_NAME_LENGTH:
            raise ValueError(
                f"{rel}: article name exceeds {MAX_NAME_LENGTH} chars "
                "(server-side write_article name cap) — rename the article"
            )
        entries.append((rel, path))

    prev_by_path = {rel: slug for slug, rel in (previous or {}).items()}
    assigned: dict[str, str] = {}
    fresh: list[tuple[str, Path]] = []
    for rel, path in entries:
        slug = prev_by_path.get(rel)
        if slug is not None:
            assigned[slug] = rel
        else:
            fresh.append((rel, path))

    base_groups: dict[str, list[tuple[str, Path]]] = {}
    for rel, path in fresh:
        base = server_slug(path.stem)
        if not base:
            raise ValueError(f"{rel}: name slugifies to empty — rename the article")
        base_groups.setdefault(base, []).append((rel, path))

    for base, group in sorted(base_groups.items()):
        contested = len(group) > 1 or base in assigned
        for rel, path in group:
            slug = server_slug(f"{path.parent.name}-{path.stem}") if contested else base
            if slug in assigned:
                raise PublishCollisionError(
                    f"slug '{slug}' collides: {assigned[slug]} vs {rel} — "
                    "rename one of the articles"
                )
            assigned[slug] = rel

    return dict(sorted(assigned.items()))


def manifest_store(path: Path | None = None) -> StateStore:
    """StateStore over the publish manifest (locked + atomic writes). A fresh
    instance per call so reloads observe the disk truth; the schema is
    additive — T04 adds hashes, S02 adds wiki metadata."""
    return StateStore(path or DEFAULT_MANIFEST_PATH)


def load_manifest(store: StateStore) -> dict:
    """The persisted ``articles`` map: ``{slug: {"path": rel, ...}}``."""
    return dict(store.load().get("articles", {}))


def save_manifest(mapping: dict[str, str], store: StateStore) -> None:
    """Persist ``{slug: rel-path}`` as the manifest's ``articles`` section,
    preserving unknown per-article keys (future hash fields) for known slugs."""

    def _mut(data: dict) -> None:
        old = data.get("articles", {})
        data["articles"] = {
            slug: {**old.get(slug, {}), "path": rel}
            for slug, rel in sorted(mapping.items())
        }

    store.update(_mut)
