"""Wiki bootstrap + start page for ``wiki publish`` (M030-S02-T02).

The managed wiki is created ONCE (`create_wiki` with the cooperative
``managed_by: "llm-wiki"`` marker); every later run finds it via
``list_wikis``. The start page is a small generated overview (the huge
``knowledge/index.md`` is deliberately excluded from the publish set) and its
hash is tracked under the manifest's separate ``start_page`` key — never in
``articles``, where the delta engine would plan its retraction.
"""
from __future__ import annotations

import json

from publish.client import tool_text
from publish.delta import ArticlePayload, _payload_hash

from core.state_store import StateStore

PRODUCER_ID = "llm-wiki"
START_SLUG = "start"
START_REL = "<generated:start-page>"
_START_DESCRIPTION = (
    "Start page of this wiki — a compiled mirror of the operator's llm-wiki "
    "knowledge base, published one-way by the wiki publish producer."
)


def ensure_wiki(client, slug: str, name: str) -> bool:
    """Create the managed wiki if it does not exist. Returns True if created."""
    listing = json.loads(tool_text(client.call_tool("list_wikis", {})) or "{}")
    existing = {w.get("slug") for w in listing.get("wikis", [])}
    if slug in existing:
        return False
    client.call_tool(
        "create_wiki", {"name": name, "slug": slug, "managed_by": PRODUCER_ID}
    )
    return True


def start_page_payload(slug_map: dict[str, str], wiki_name: str) -> ArticlePayload:
    """The generated entry-point article: counts + Maps of Content links."""
    if START_SLUG in slug_map:
        raise ValueError(
            f"an article already claims the reserved start-page slug '{START_SLUG}' "
            f"({slug_map[START_SLUG]}) — rename it"
        )
    mocs = sorted(
        slug for slug, rel in slug_map.items() if rel.startswith("knowledge/MOCs/")
    )
    by_root: dict[str, int] = {}
    for rel in slug_map.values():
        by_root[rel.split("/", 1)[0]] = by_root.get(rel.split("/", 1)[0], 0) + 1
    corpora = " · ".join(f"{root} {n}" for root, n in sorted(by_root.items()))
    lines = [
        f"# {wiki_name}",
        "",
        f"One-way mirror of the operator's llm-wiki vault — {len(slug_map)} articles "
        f"({corpora}). knowledge/ is the compiled distillate; the other corpora are "
        "its substrate. Change it in the vault, read it here.",
        "",
    ]
    if mocs:
        lines += ["## Maps of Content", ""]
        lines += [f"- [[{slug}]]" for slug in mocs]
        lines.append("")
    content = "\n".join(lines)
    name = START_SLUG
    return ArticlePayload(
        slug=START_SLUG,
        rel=START_REL,
        name=name,
        description=_START_DESCRIPTION,
        content=content,
        content_hash=_payload_hash(name, _START_DESCRIPTION, content),
    )


def needs_start_page(store: StateStore, payload: ArticlePayload) -> bool:
    return store.load().get("start_page", {}).get("hash") != payload.content_hash


def record_start_page(store: StateStore, payload: ArticlePayload) -> None:
    def _mut(data: dict) -> None:
        data["start_page"] = {"hash": payload.content_hash}

    store.update(_mut)
