"""Tests for the publish executor (M030-S02-T03)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from publish.bootstrap import start_page_payload
from publish.client import PublishClientError, ToolCallError
from publish.corpus import manifest_store
from publish.delta import ArticlePayload, PublishPlan, _payload_hash
from publish.executor import execute_publish


def _payload(slug: str, body: str = "b") -> ArticlePayload:
    return ArticlePayload(
        slug=slug, rel=f"concepts/{slug}.md", name=slug,
        description=f"About {slug}.", content=body,
        content_hash=_payload_hash(slug, f"About {slug}.", body),
    )


class FakeClient:
    def __init__(self, reject: set[str] = frozenset(), transport_fail: set[str] = frozenset()):
        self.reject = set(reject)
        self.transport_fail = set(transport_fail)
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        key = arguments.get("name") or arguments.get("object_id") or ""
        if key in self.transport_fail:
            raise PublishClientError("boom: connection lost")
        if key in self.reject:
            raise ToolCallError("secret-shaped value detected")
        if name == "write_article":
            return {"content": [{"type": "text", "text": json.dumps(
                {"article_id": key, "wiki": arguments["wiki"],
                 "version_seq": 1, "created": True})}], "isError": False}
        return {"content": [{"type": "text", "text": "{}"}], "isError": False}


def test_executes_sequentially_and_records(tmp_path: Path) -> None:
    store = manifest_store(tmp_path / "p.json")
    plan = PublishPlan(create=[_payload("a"), _payload("b")], update=[_payload("c")])
    client = FakeClient()
    report = execute_publish(client, store, plan, None, "llm-wiki")
    assert report.created == ["a", "b"] and report.updated == ["c"]
    names = [(n, a.get("name")) for n, a in client.calls]
    assert names == [("write_article", "a"), ("write_article", "b"), ("write_article", "c")]
    articles = store.reload()["articles"]
    assert set(articles) == {"a", "b", "c"}
    assert all(a["wiki"] == "llm-wiki" for _, a in client.calls)


def test_tool_reject_is_fail_soft(tmp_path: Path) -> None:
    store = manifest_store(tmp_path / "p.json")
    plan = PublishPlan(create=[_payload("a"), _payload("bad"), _payload("c")])
    report = execute_publish(FakeClient(reject={"bad"}), store, plan, None, "llm-wiki")
    assert report.created == ["a", "c"]
    assert report.skipped == [("bad", "secret-shaped value detected")]
    assert "bad" not in store.reload()["articles"]


def test_retract_calls_delete_object_and_records(tmp_path: Path) -> None:
    store = manifest_store(tmp_path / "p.json")
    for p in (_payload("gone"), _payload("stays")):
        from publish.delta import record_published

        record_published(store, p)
    plan = PublishPlan(retract=[("gone", "concepts/gone.md")])
    client = FakeClient()
    report = execute_publish(client, store, plan, None, "llm-wiki")
    assert report.retracted == ["gone"]
    assert ("delete_object", {"object_id": "gone"}) in client.calls
    assert set(store.reload()["articles"]) == {"stays"}


def test_start_page_written_once(tmp_path: Path) -> None:
    store = manifest_store(tmp_path / "p.json")
    start = start_page_payload({"foo": "concepts/foo.md"}, "LLM Wiki")
    client = FakeClient()
    report = execute_publish(client, store, PublishPlan(), start, "llm-wiki")
    assert report.start_page_written is True
    call = next(a for n, a in client.calls if n == "write_article")
    assert call["start_page"] is True

    again = execute_publish(FakeClient(), store, PublishPlan(), start, "llm-wiki")
    assert again.start_page_written is False


def test_transport_error_propagates_but_keeps_progress(tmp_path: Path) -> None:
    store = manifest_store(tmp_path / "p.json")
    plan = PublishPlan(create=[_payload("a"), _payload("dead"), _payload("c")])
    with pytest.raises(PublishClientError):
        execute_publish(FakeClient(transport_fail={"dead"}), store, plan, None, "llm-wiki")
    assert set(store.reload()["articles"]) == {"a"}
