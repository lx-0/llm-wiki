"""Corpus → contract-shaped mapping for ``wiki publish`` (M030-S01).

Pure functions, no network. The slug rules mirror the SERVER side exactly:
context-mcp re-slugifies ``write_article``'s ``name`` via ``slugifySkillName``
(packages/core/src/validation/skill-validation.ts:152-158), so every slug we
persist locally must be a fixpoint of that function — otherwise the manifest
id and the server article id diverge and retraction (`delete_object` by id)
silently misses (architect review 2026-08-25, issue 2).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Iterator, Sequence

from core.links import iter_articles
from core.paths import STATE_DIR
from core.state_store import StateStore

# Default corpus: the curated wiki only. The ALLES widening (M030-S04,
# operator 2026-08-25: "Substrat und Destillat gehören zusammen") adds
# raw/daily/reports/workspace per-vault via `publish.roots`.
DEFAULT_ROOTS: tuple[str, ...] = ("knowledge",)

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


def _capped_slug(name: str) -> str:
    """Slug candidate under the server's 120-char NAME cap: slugify, then
    truncate deterministically (S04 — raw/memories/ carries >120-char
    filenames; aborting the whole plan over one pathological name would
    defeat ALLES-mode). The result stays a slugify fixpoint."""
    return server_slug(name)[:MAX_NAME_LENGTH].rstrip("-")


def _walk_root(vault: Path, root: str) -> Iterator[Path]:
    """Markdown files of one publish root. ``knowledge`` keeps THE canonical
    walker (``iter_articles`` — root index.md + hidden excluded); every other
    root walks ``**/*.md`` with the same hidden-exclusion. A missing root is
    silently empty (not every vault has workspace/)."""
    base = vault / root
    if not base.is_dir():
        return
    if root == "knowledge":
        yield from iter_articles(base)
        return
    for path in base.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(base).parts):
            continue
        yield path


def count_non_markdown(vault: Path, roots: Sequence[str]) -> int:
    """Files in the publish roots the contract cannot carry (markdown-only).
    Reported by the CLI so the cap is never silent."""
    count = 0
    for root in roots:
        base = vault / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix == ".md":
                continue
            if any(part.startswith(".") for part in path.relative_to(base).parts):
                continue
            count += 1
    return count


def map_slugs(
    vault: Path,
    roots: Sequence[str] = DEFAULT_ROOTS,
    previous: dict[str, str] | None = None,
) -> dict[str, str]:
    """Assign a flat global slug to every markdown article under ``roots``.

    Returns ``{slug: VAULT-relative posix path}`` (e.g.
    ``knowledge/concepts/foo.md``, ``raw/notes/x.md``). Deterministic and
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
    walked: list[Path] = []
    for root in roots:
        walked.extend(_walk_root(vault, root))
    for path in sorted(walked):
        entries.append((path.relative_to(vault).as_posix(), path))

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
        base = _capped_slug(path.stem)
        if not base:
            raise ValueError(f"{rel}: name slugifies to empty — rename the article")
        base_groups.setdefault(base, []).append((rel, path))

    for base, group in sorted(base_groups.items()):
        contested = len(group) > 1 or base in assigned
        for rel, path in group:
            for slug in _disambiguation_ladder(base, rel, path, contested):
                if slug not in assigned:
                    assigned[slug] = rel
                    break
            else:
                raise PublishCollisionError(
                    f"no free slug for {rel} (base '{base}') — "
                    f"last candidate taken by {assigned.get(base, '?')}"
                )

    return dict(sorted(assigned.items()))


def _disambiguation_ladder(
    base: str, rel: str, path: Path, contested: bool
) -> Iterator[str]:
    """Slug candidates, cheapest first. Uncontested → the base. Contested →
    parent-stem, then the full vault-relative path (unique by construction;
    real-corpus case: reports/studies/*/runs/<ts>/instruments/gad-7.md shares
    stem AND parent name across runs), then path+hash as the truncation-proof
    last resort (two >120-char paths can collide after capping)."""
    if not contested:
        yield base
        return
    yield _capped_slug(f"{path.parent.name}-{path.stem}")
    rel_stem = rel[:-3] if rel.endswith(".md") else rel
    full = _capped_slug(rel_stem.replace("/", "-"))
    yield full
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:8]
    yield f"{full[: MAX_NAME_LENGTH - 9].rstrip('-')}-{digest}"


def manifest_store(path: Path | None = None) -> StateStore:
    """StateStore over the publish manifest (locked + atomic writes). A fresh
    instance per call so reloads observe the disk truth; the schema is
    additive — T04 adds hashes, S02 adds wiki metadata."""
    return StateStore(path or DEFAULT_MANIFEST_PATH)


def migrate_manifest_layout(store: StateStore) -> None:
    """One-shot v1→v2 manifest migration (M030-S04): v1 stored
    KNOWLEDGE-relative paths (`concepts/foo.md`), v2 stores VAULT-relative
    (`knowledge/concepts/foo.md`). Without this, the first widened run would
    see every live article as deleted and plan 2000+ phantom retractions.
    Idempotent via the ``layout`` marker; locked RMW like every manifest write."""
    if store.load().get("layout") == "vault-rel":
        return

    def _mut(data: dict) -> None:
        articles = data.get("articles", {})
        for entry in articles.values():
            path = entry.get("path", "")
            if path and not path.startswith("knowledge/"):
                entry["path"] = f"knowledge/{path}"
        data["layout"] = "vault-rel"

    store.update(_mut)


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
