"""Tests for `core.links` — wikilink resolution + relativization.

A link in a markdown file is relative to that file. These cover the resolver
(against a realistic `<vault>/{knowledge,daily,raw}` layout), canonical-slug
derivation, the text rewriter (the three relative shapes + idempotency +
skip-zones + table escapes + leave-unresolvable-untouched), and the corpus
pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.links import (
    canonical_slug,
    iter_articles,
    link_target,
    relativize_text,
    resolve_link,
    run_relativize_pass,
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A vault with knowledge/{concepts,people}, daily/, raw/notes/."""
    def w(rel: str) -> None:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("—", encoding="utf-8")

    w("knowledge/concepts/foo.md")
    w("knowledge/concepts/bar.md")
    w("knowledge/people/alex.md")
    w("daily/2026-05-15.md")
    w("raw/notes/transcript.md")
    w("knowledge/concepts/diagram.png")
    return tmp_path


# ── resolve_link ────────────────────────────────────────────────────────


def test_resolve_same_folder_bare(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    assert resolve_link("bar", src, vault) == (vault / "knowledge/concepts/bar.md").resolve()


def test_resolve_cross_folder_relative(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    assert resolve_link("../people/alex", src, vault) == (vault / "knowledge/people/alex.md").resolve()


def test_resolve_legacy_knowledge_relative_form(vault: Path) -> None:
    """The historic `[[people/alex]]` form resolves via the knowledge base."""
    src = vault / "knowledge" / "concepts" / "foo.md"
    assert resolve_link("people/alex", src, vault) == (vault / "knowledge/people/alex.md").resolve()


def test_resolve_substrate_sibling_vault_absolute(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    assert resolve_link("daily/2026-05-15.md", src, vault) == (vault / "daily/2026-05-15.md").resolve()
    assert resolve_link("../../daily/2026-05-15.md", src, vault) == (vault / "daily/2026-05-15.md").resolve()


def test_resolve_unresolvable_returns_none(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    assert resolve_link("concepts/does-not-exist", src, vault) is None


def test_resolve_media_extension_kept(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    assert resolve_link("diagram.png", src, vault) == (vault / "knowledge/concepts/diagram.png").resolve()


# ── canonical_slug ────────────────────────────────────────────────────────


def test_canonical_slug_under_knowledge(vault: Path) -> None:
    kn = vault / "knowledge"
    assert canonical_slug(vault / "knowledge/people/alex.md", kn) == "people/alex"


def test_canonical_slug_outside_knowledge_is_none(vault: Path) -> None:
    kn = vault / "knowledge"
    assert canonical_slug(vault / "daily/2026-05-15.md", kn) is None


# ── link_target ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("concepts/foo", "concepts/foo"),
        ("concepts/foo|Alias", "concepts/foo"),
        ("concepts/foo#Heading", "concepts/foo"),
        ("concepts/foo#H|Alias", "concepts/foo"),
        ("concepts/foo\\|table alias", "concepts/foo"),
    ],
)
def test_link_target(raw: str, expected: str) -> None:
    assert link_target(raw) == expected


# ── relativize_text ───────────────────────────────────────────────────────


def test_relativize_three_shapes(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    text = (
        "Same: [[concepts/bar]]. Cross: [[people/alex|Alex]]. "
        "Substrate: [[daily/2026-05-15.md]]."
    )
    new, n, unresolved = relativize_text(text, src, vault)
    assert "[[bar]]" in new
    assert "[[../people/alex|Alex]]" in new
    assert "[[../../daily/2026-05-15.md]]" in new
    assert n == 3
    assert unresolved == []


def test_relativize_idempotent(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    text = "Cross: [[../people/alex]]."
    new, n, _ = relativize_text(text, src, vault)
    assert new == text
    assert n == 0


def test_relativize_skips_code_fence_and_frontmatter(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    text = "---\nrelated: [[people/alex]]\n---\n```\n[[people/alex]]\n```\nBody [[people/alex]]."
    new, n, _ = relativize_text(text, src, vault)
    # Only the body link is rewritten; frontmatter + fence stay verbatim.
    assert new.count("[[../people/alex]]") == 1
    assert "related: [[people/alex]]" in new
    assert "```\n[[people/alex]]\n```" in new
    assert n == 1


def test_relativize_table_escaped_pipe_preserved(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    text = "| [[people/alex\\|Alex]] | x |"
    new, n, _ = relativize_text(text, src, vault)
    assert "[[../people/alex\\|Alex]]" in new
    assert n == 1


def test_relativize_leaves_unresolvable_untouched(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    text = "Dangling [[concepts/ghost]] and example [[wikilink]]."
    new, n, unresolved = relativize_text(text, src, vault)
    assert new == text
    assert n == 0
    assert set(unresolved) == {"concepts/ghost", "wikilink"}


def test_relativize_embed_image(vault: Path) -> None:
    src = vault / "knowledge" / "concepts" / "foo.md"
    text = "![[concepts/diagram.png]]"
    new, n, _ = relativize_text(text, src, vault)
    assert new == "![[diagram.png]]"
    assert n == 1


# ── run_relativize_pass ───────────────────────────────────────────────────


def test_pass_rewrites_corpus_and_skips_index(vault: Path) -> None:
    kn = vault / "knowledge"
    (kn / "concepts" / "foo.md").write_text("Link [[people/alex]].", encoding="utf-8")
    (kn / "index.md").write_text("| [[concepts/foo]] | summary |", encoding="utf-8")
    stats = run_relativize_pass(kn, vault)
    assert stats["links_rewritten"] == 1
    assert "[[../people/alex]]" in (kn / "concepts" / "foo.md").read_text(encoding="utf-8")
    # index.md is excluded — its links already resolve source-relative.
    assert (kn / "index.md").read_text(encoding="utf-8") == "| [[concepts/foo]] | summary |"


def test_pass_is_idempotent(vault: Path) -> None:
    kn = vault / "knowledge"
    (kn / "concepts" / "foo.md").write_text("Link [[people/alex]].", encoding="utf-8")
    run_relativize_pass(kn, vault)
    stats = run_relativize_pass(kn, vault)
    assert stats["links_rewritten"] == 0
    assert stats["articles_written"] == 0


def test_iter_articles_skips_index(vault: Path) -> None:
    kn = vault / "knowledge"
    (kn / "index.md").write_text("—", encoding="utf-8")
    names = {p.name for p in iter_articles(kn)}
    assert "index.md" not in names
    assert "foo.md" in names
