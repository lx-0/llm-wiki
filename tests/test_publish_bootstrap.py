"""Tests for wiki bootstrap + start page (M030-S02-T02)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from publish.bootstrap import (
    START_SLUG,
    ensure_wiki,
    needs_start_page,
    record_start_page,
    start_page_payload,
)
from publish.corpus import manifest_store
from publish.delta import plan_delta


class FakeClient:
    def __init__(self, wikis: list[dict]):
        self.wikis = wikis
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        if name == "list_wikis":
            return {"content": [{"type": "text",
                                 "text": json.dumps({"wikis": self.wikis}, indent=2)}],
                    "isError": False}
        if name == "create_wiki":
            return {"content": [{"type": "text",
                                 "text": json.dumps({"wiki": {"slug": arguments.get("slug")}})}],
                    "isError": False}
        raise AssertionError(f"unexpected tool {name}")


def test_ensure_wiki_is_idempotent_when_present() -> None:
    client = FakeClient([{"slug": "llm-wiki", "name": "LLM Wiki"}])
    assert ensure_wiki(client, "llm-wiki", "LLM Wiki") is False
    assert [c[0] for c in client.calls] == ["list_wikis"]


def test_ensure_wiki_creates_with_managed_by() -> None:
    client = FakeClient([])
    assert ensure_wiki(client, "llm-wiki", "LLM Wiki") is True
    name, args = client.calls[-1]
    assert name == "create_wiki"
    assert args == {"name": "LLM Wiki", "slug": "llm-wiki", "managed_by": "llm-wiki"}


def test_start_page_lists_mocs_and_count() -> None:
    slug_map = {
        "foo": "concepts/foo.md",
        "llm-wiki-moc": "MOCs/llm-wiki-moc.md",
        "fleet": "MOCs/fleet.md",
    }
    payload = start_page_payload(slug_map, "LLM Wiki")
    assert payload.slug == START_SLUG
    assert "3 articles" in payload.content
    assert "[[llm-wiki-moc]]" in payload.content and "[[fleet]]" in payload.content
    assert payload.description


def test_start_page_slug_collision_raises() -> None:
    with pytest.raises(ValueError, match="start"):
        start_page_payload({"start": "concepts/start.md"}, "LLM Wiki")


def test_start_page_hash_tracked_outside_articles(tmp_path: Path) -> None:
    store = manifest_store(tmp_path / "publish.json")
    payload = start_page_payload({"foo": "concepts/foo.md"}, "LLM Wiki")
    assert needs_start_page(store, payload) is True
    record_start_page(store, payload)
    assert needs_start_page(store, payload) is False
    # the start page never appears in the article delta (no phantom retraction)
    plan = plan_delta([], store.reload().get("articles", {}))
    assert plan.retract == []

    changed = start_page_payload({"foo": "concepts/foo.md", "bar": "people/bar.md"}, "LLM Wiki")
    assert needs_start_page(store, changed) is True
