"""Tests for the publish delta engine (M030-S01-T04).

The server versions EVERY write_article call — idempotency is the producer's
job (PRODUCER-CONTRACT.md): diff by content hash locally, publish only
created/changed, retract deleted. A rerun over unchanged input must plan
zero writes.
"""
from __future__ import annotations

from pathlib import Path

from publish.corpus import manifest_store, map_slugs, server_slug
from publish.delta import (
    build_payloads,
    plan_delta,
    record_published,
    record_retracted,
)


def _vault(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    k = vault / "knowledge"
    for rel, body in {
        "concepts/foo.md": "Foo body with [[../people/alex|Alex]].\n",
        "people/alex.md": "Alex body.\n",
        "concepts/alex.md": "Concept alex.\n",
    }.items():
        p = k / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (k / "index.md").write_text(
        "| Article | Summary | Compiled From | Updated |\n"
        "|---------|---------|---------------|---------|\n"
        "| [[concepts/foo]] | About foo. | raw/a.md | 2026-08-01 |\n",
        encoding="utf-8",
    )
    return vault, k


def _payloads(vault: Path, k: Path):
    from publish.describe import description_index

    slug_map = map_slugs(vault)
    index = description_index((k / "index.md").read_text(encoding="utf-8"), k, vault)
    return build_payloads(vault, slug_map, index)


def test_payload_content_is_link_normalized_and_described(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    by_slug = {p.slug: p for p in _payloads(vault, k)}
    foo = by_slug["foo"]
    assert "[[people-alex|Alex]]" in foo.content
    assert foo.description == "About foo."
    assert foo.name == "foo"


def test_disambiguated_slug_forces_name_to_slug(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    by_slug = {p.slug: p for p in _payloads(vault, k)}
    # people/alex.md + concepts/alex.md contest "alex": names must re-slugify
    # to OUR slugs on the server, so the pretty stem is not usable here.
    assert by_slug["people-alex"].name == "people-alex"
    assert server_slug(by_slug["people-alex"].name) == "people-alex"


def test_first_run_plans_all_creates_then_idempotent(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    store = manifest_store(tmp_path / "publish.json")
    payloads = _payloads(vault, k)

    first = plan_delta(payloads, {})
    assert {p.slug for p in first.create} == {"foo", "people-alex", "concepts-alex"}
    assert not first.update and not first.retract

    for p in payloads:
        record_published(store, p)

    manifest = store.reload().get("articles", {})
    second = plan_delta(_payloads(vault, k), manifest)
    assert not second.create and not second.update and not second.retract
    assert second.unchanged == 3


def test_edited_body_plans_exactly_one_update(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    store = manifest_store(tmp_path / "publish.json")
    for p in _payloads(vault, k):
        record_published(store, p)

    (k / "people" / "alex.md").write_text("Alex body v2.\n", encoding="utf-8")
    plan = plan_delta(_payloads(vault, k), store.reload().get("articles", {}))
    assert [p.slug for p in plan.update] == ["people-alex"]
    assert not plan.create and not plan.retract


def test_description_change_alone_triggers_update(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    store = manifest_store(tmp_path / "publish.json")
    for p in _payloads(vault, k):
        record_published(store, p)

    (k / "index.md").write_text(
        "| Article | Summary | Compiled From | Updated |\n"
        "|---------|---------|---------------|---------|\n"
        "| [[concepts/foo]] | About foo, sharper. | raw/a.md | 2026-08-02 |\n",
        encoding="utf-8",
    )
    plan = plan_delta(_payloads(vault, k), store.reload().get("articles", {}))
    assert [p.slug for p in plan.update] == ["foo"]


def test_deleted_article_plans_retraction_and_record_removes(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    store = manifest_store(tmp_path / "publish.json")
    for p in _payloads(vault, k):
        record_published(store, p)

    (k / "concepts" / "foo.md").unlink()
    manifest = store.reload().get("articles", {})
    plan = plan_delta(_payloads(vault, k), manifest)
    assert plan.retract == [("foo", "knowledge/concepts/foo.md")]

    record_retracted(store, "foo")
    assert "foo" not in store.reload().get("articles", {})
