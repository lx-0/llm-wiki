"""Tests for the publish corpus mapper (M030-S01-T01, vault-rel since S04).

Three layers:

- server_slug: exact Python port of context-mcp's slugifySkillName
  (skill-validation.ts:152-158) — the published slug MUST be a fixpoint of the
  server-side re-slugification or retraction ids diverge (architect review
  issue 2).
- map_slugs: walk the publish roots (knowledge via links.iter_articles),
  assign flat global slugs with deterministic, order-independent collision
  disambiguation and slug stability against a previous manifest. Keys are
  VAULT-relative (M030-S04).
- manifest: StateStore-backed slug↔path persistence at an explicit path
  (tests never touch the real STATE_DIR).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from publish.corpus import (
    PublishCollisionError,
    load_manifest,
    manifest_store,
    map_slugs,
    save_manifest,
    server_slug,
)


def _article(vault: Path, rel: str, body: str = "x\n") -> Path:
    p = vault / "knowledge" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# --- server_slug: exact port + fixpoint property ---------------------------


def test_server_slug_basic_kebab() -> None:
    assert server_slug("Vault Dashboard") == "vault-dashboard"


def test_server_slug_diacritics_nfkd_fold() -> None:
    # Ü → U + U+0308 (stripped), ä → a; matches slugifySkillName exactly.
    assert server_slug("Über Städte!") == "uber-stadte"


def test_server_slug_digits_kept_and_symbol_runs_collapse() -> None:
    assert server_slug("2026 -- Plan (v2)") == "2026-plan-v2"


def test_server_slug_emoji_becomes_separator() -> None:
    assert server_slug("Rocket 🚀 Launch") == "rocket-launch"


def test_server_slug_trims_hyphen_runs() -> None:
    assert server_slug("--Foo--") == "foo"


def test_server_slug_all_symbols_returns_empty() -> None:
    # slugifySkillName may return "" — callers must reject (docstring in the
    # TS source); the walker turns this into a hard error, see below.
    assert server_slug("!!!") == ""


@pytest.mark.parametrize(
    "name",
    ["Über Städte!", "Rocket 🚀 Launch", "--Foo--", "2026 -- Plan (v2)", "a" * 300],
)
def test_server_slug_is_fixpoint(name: str) -> None:
    once = server_slug(name)
    assert server_slug(once) == once


# --- map_slugs: walk, exclusions, collisions, determinism -------------------


def test_map_slugs_walks_recursive_and_excludes_root_index(tmp_path: Path) -> None:
    _article(tmp_path, "index.md")  # root catalog — excluded
    _article(tmp_path, "concepts/foo.md")
    _article(tmp_path, "MOCs/hub.md")
    mapping = map_slugs(tmp_path)
    assert mapping == {
        "foo": "knowledge/concepts/foo.md",
        "hub": "knowledge/MOCs/hub.md",
    }


def test_map_slugs_collision_disambiguates_both_by_parent(tmp_path: Path) -> None:
    _article(tmp_path, "concepts/alex.md")
    _article(tmp_path, "people/alex.md")
    mapping = map_slugs(tmp_path)
    assert mapping == {
        "concepts-alex": "knowledge/concepts/alex.md",
        "people-alex": "knowledge/people/alex.md",
    }


def test_map_slugs_is_order_independent(tmp_path: Path) -> None:
    a = tmp_path / "a"
    _article(a, "concepts/alex.md")
    _article(a, "people/alex.md")
    _article(a, "concepts/foo.md")

    b = tmp_path / "b"
    _article(b, "concepts/foo.md")
    _article(b, "people/alex.md")
    _article(b, "concepts/alex.md")

    assert map_slugs(a) == map_slugs(b)


def test_map_slugs_empty_slug_raises_naming_path(tmp_path: Path) -> None:
    _article(tmp_path, "concepts/!!!.md")
    with pytest.raises(ValueError, match=r"!!!\.md"):
        map_slugs(tmp_path)


def test_map_slugs_overlong_name_raises(tmp_path: Path) -> None:
    # write_article's name param is capped at MAX_NAME_LENGTH=120 server-side.
    _article(tmp_path, f"concepts/{'a' * 121}.md")
    with pytest.raises(ValueError, match="120"):
        map_slugs(tmp_path)


def test_map_slugs_unresolvable_collision_raises_with_both_paths(tmp_path: Path) -> None:
    # Same stem AND same parent dir name in different subtrees: parent-based
    # disambiguation yields the identical slug for both — must hard-fail.
    _article(tmp_path, "people/x/alex.md")
    _article(tmp_path, "friends/x/alex.md")
    with pytest.raises(PublishCollisionError) as exc:
        map_slugs(tmp_path)
    msg = str(exc.value)
    assert "people/x/alex.md" in msg and "friends/x/alex.md" in msg


def test_map_slugs_stability_keeps_prior_slug_on_new_collision(tmp_path: Path) -> None:
    _article(tmp_path, "concepts/alex.md")
    first = map_slugs(tmp_path)
    assert first == {"alex": "knowledge/concepts/alex.md"}

    _article(tmp_path, "people/alex.md")  # newcomer collides with established slug
    second = map_slugs(tmp_path, previous=first)
    assert second == {
        "alex": "knowledge/concepts/alex.md",  # stable — retraction ids must not drift
        "people-alex": "knowledge/people/alex.md",
    }


# --- manifest persistence ---------------------------------------------------


def test_manifest_round_trip(tmp_path: Path) -> None:
    store = manifest_store(tmp_path / "publish.json")
    save_manifest({"foo": "knowledge/concepts/foo.md"}, store)
    assert load_manifest(store) == {"foo": {"path": "knowledge/concepts/foo.md"}}
    # fresh store over the same file sees the persisted state
    fresh = manifest_store(tmp_path / "publish.json")
    assert load_manifest(fresh) == {"foo": {"path": "knowledge/concepts/foo.md"}}
