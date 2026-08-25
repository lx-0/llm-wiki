"""Content-hash delta engine for ``wiki publish`` (M030-S01-T04).

The server versions EVERY ``write_article`` call — idempotency is the
producer's job (PRODUCER-CONTRACT.md). This module turns the corpus into
contract-shaped payloads and diffs them against the manifest, so the executor
only writes created/changed articles and retracts deleted ones. Manifest
writes happen per article, only after server success (S02 executor calls
``record_published`` / ``record_retracted``).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from publish.corpus import server_slug
from publish.describe import describe
from publish.render import normalize_links

from core.state_store import StateStore


@dataclass(frozen=True)
class ArticlePayload:
    """One article as it goes over the wire.

    ``name`` is write_article's name argument. The server re-slugifies it
    (slugifySkillName) into the article id, so ``server_slug(name)`` MUST
    equal ``slug`` — for disambiguated slugs the pretty stem would collapse
    back to the contested base, hence the slug itself is sent as name there.
    """

    slug: str
    rel: str
    name: str
    description: str
    content: str
    content_hash: str


@dataclass
class PublishPlan:
    create: list[ArticlePayload] = field(default_factory=list)
    update: list[ArticlePayload] = field(default_factory=list)
    retract: list[tuple[str, str]] = field(default_factory=list)
    unchanged: int = 0


def _payload_hash(name: str, description: str, content: str) -> str:
    h = hashlib.sha256()
    for part in (name, description, content):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def build_payloads(
    knowledge_dir: Path,
    vault: Path,
    slug_map: dict[str, str],
    index: dict[str, str],
) -> list[ArticlePayload]:
    """Read + transform every mapped article into its wire shape, sorted by
    slug. ``slug_map`` is T01's ``{slug: rel}``; ``index`` is T03's
    ``{rel: summary}``."""
    slug_by_relpath = {rel: slug for slug, rel in slug_map.items()}
    payloads: list[ArticlePayload] = []
    for slug, rel in sorted(slug_map.items()):
        path = knowledge_dir / rel
        body = path.read_text(encoding="utf-8")
        content, _ = normalize_links(body, path, vault, slug_by_relpath, knowledge_dir)
        description = describe(rel, body, index)
        stem = Path(rel).stem
        name = stem if server_slug(stem) == slug else slug
        payloads.append(
            ArticlePayload(
                slug=slug,
                rel=rel,
                name=name,
                description=description,
                content=content,
                content_hash=_payload_hash(name, description, content),
            )
        )
    return payloads


def plan_delta(
    payloads: list[ArticlePayload], manifest_articles: dict
) -> PublishPlan:
    """Diff wire payloads against the manifest's ``articles`` section."""
    plan = PublishPlan()
    seen: set[str] = set()
    for payload in payloads:
        seen.add(payload.slug)
        entry = manifest_articles.get(payload.slug)
        if entry is None:
            plan.create.append(payload)
        elif entry.get("hash") != payload.content_hash:
            plan.update.append(payload)
        else:
            plan.unchanged += 1
    for slug in sorted(set(manifest_articles) - seen):
        plan.retract.append((slug, manifest_articles[slug].get("path", "")))
    return plan


def record_published(store: StateStore, payload: ArticlePayload) -> None:
    """Persist one article's manifest entry AFTER the server accepted it."""

    def _mut(data: dict) -> None:
        articles = data.setdefault("articles", {})
        articles[payload.slug] = {"path": payload.rel, "hash": payload.content_hash}

    store.update(_mut)


def record_retracted(store: StateStore, slug: str) -> None:
    """Drop one article's manifest entry AFTER the server archived it."""

    def _mut(data: dict) -> None:
        data.setdefault("articles", {}).pop(slug, None)

    store.update(_mut)
