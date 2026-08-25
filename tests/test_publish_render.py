"""Tests for publish wikilink normalization (M030-S01-T02).

A served article's links must resolve BY SLUG on the meinkontext side
(PRODUCER-CONTRACT.md: links are `[[target-slug]]`, resolved by convention).
Links the remote reader cannot follow — unresolvable targets, media embeds,
anything outside the publish set — degrade to plain text instead of dangling.
"""
from __future__ import annotations

from pathlib import Path

from publish.corpus import map_slugs
from publish.render import normalize_links


def _vault(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    k = vault / "knowledge"
    for rel in ("concepts/foo.md", "concepts/alex.md", "people/alex.md", "people/bar.md"):
        p = k / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("body\n", encoding="utf-8")
    (k / "index.md").write_text("| catalog |\n", encoding="utf-8")
    (vault / "raw" / "notes").mkdir(parents=True)
    (vault / "raw" / "notes" / "scratch.md").write_text("raw\n", encoding="utf-8")
    return vault, k


def _slug_index(k: Path) -> dict[str, str]:
    return {rel: slug for slug, rel in map_slugs(k).items()}


def test_cross_folder_link_becomes_slug(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "people" / "bar.md"
    text, n = normalize_links("see [[../concepts/foo]]\n", src, vault, _slug_index(k), k)
    assert text == "see [[foo]]\n"
    assert n == 1


def test_alias_heading_and_bang_preserved_on_slug_rewrite(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "people" / "bar.md"
    text, _ = normalize_links(
        "a [[../concepts/foo#History|the Foo]] b ![[../concepts/foo]]\n",
        src, vault, _slug_index(k), k,
    )
    assert text == "a [[foo#History|the Foo]] b ![[foo]]\n"


def test_disambiguated_slug_is_used(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "people" / "bar.md"
    text, _ = normalize_links("[[../concepts/alex]] und [[alex]]\n", src, vault, _slug_index(k), k)
    # people/bar.md's neighbor link [[alex]] resolves source-relative to people/alex.md
    assert text == "[[concepts-alex]] und [[people-alex]]\n"


def test_unresolvable_link_degrades_to_plain_text(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "concepts" / "foo.md"
    text, n = normalize_links("see [[does-not-exist]] here\n", src, vault, _slug_index(k), k)
    assert text == "see does-not-exist here\n"
    assert n == 1


def test_alias_wins_as_plain_text(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "concepts" / "foo.md"
    text, _ = normalize_links("[[does-not-exist#h|Nice Name]]\n", src, vault, _slug_index(k), k)
    assert text == "Nice Name\n"


def test_outside_knowledge_target_degrades(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "concepts" / "foo.md"
    text, _ = normalize_links("[[../../raw/notes/scratch]]\n", src, vault, _slug_index(k), k)
    assert text == "../../raw/notes/scratch\n"


def test_index_md_link_degrades(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "concepts" / "foo.md"
    text, _ = normalize_links("[[../index|Katalog]]\n", src, vault, _slug_index(k), k)
    assert text == "Katalog\n"


def test_media_embed_degrades_to_filename(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "concepts" / "foo.md"
    text, _ = normalize_links("![[diagram.png]]\n", src, vault, _slug_index(k), k)
    assert text == "diagram.png\n"


def test_frontmatter_and_fences_untouched(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "people" / "bar.md"
    original = (
        "---\ncompiled_from: [[x]]\n---\n"
        "```\n[[../concepts/foo]]\n```\n"
        "[[../concepts/foo]]\n"
    )
    text, n = normalize_links(original, src, vault, _slug_index(k), k)
    assert "compiled_from: [[x]]" in text
    assert "```\n[[../concepts/foo]]\n```" in text
    assert text.endswith("[[foo]]\n")
    assert n == 1


def test_no_links_round_trips_byte_identical(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "concepts" / "foo.md"
    original = "plain text\n\nwith | table | pipes |\n"
    text, n = normalize_links(original, src, vault, _slug_index(k), k)
    assert text == original
    assert n == 0


def test_table_escaped_alias_pipe_preserved(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    src = k / "people" / "bar.md"
    text, _ = normalize_links(
        "| [[../concepts/foo\\|Foo]] |\n", src, vault, _slug_index(k), k
    )
    assert text == "| [[foo\\|Foo]] |\n"
