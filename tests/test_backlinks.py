"""Tests for the backlinks-footer corpus-pass (M020).

Three layers:

- extractor (build_backlinks_index): resolves each body link against the source
  article, keeps knowledge→knowledge edges, keys the index on canonical slugs
- writer (write_backlinks_footer): sentinel-managed region on a single article,
  each incoming canonical slug rendered relative to the article it's written into
- orchestrator (run_backlinks_pass): walks corpus + writes footers

Convention (post-2026-05: relativize-wikilinks arc): a link in a markdown file is
relative to that file. From `concepts/a.md` a same-folder link is `[[b]]`; a
cross-folder link is `[[../people/alex]]`. Index keys + incoming lists are the
canonical knowledge-slug form (`concepts/foo`); the footer renderer converts
them back to article-relative links.
"""

from __future__ import annotations

from pathlib import Path

from core.backlinks import (
    build_backlinks_index,
    run_backlinks_pass,
    write_backlinks_footer,
)


# ── extractor ──────────────────────────────────────────────────────────


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_extractor_basic_incoming_links(tmp_path: Path) -> None:
    """`concepts/a` links same-folder `[[b]]`; index['concepts/b'] == ['concepts/a']."""
    _write(tmp_path / "concepts" / "a.md", "Body with a [[b]] link.")
    _write(tmp_path / "concepts" / "b.md", "Plain body, no links.")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/b"] == ["concepts/a"]
    assert index.get("concepts/a", []) == []


def test_extractor_cross_folder_relative_link(tmp_path: Path) -> None:
    """A `../people/alex` link from concepts/ resolves to canonical `people/alex`."""
    _write(tmp_path / "concepts" / "src.md", "See [[../people/alex]].")
    _write(tmp_path / "people" / "alex.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["people/alex"] == ["concepts/src"]


def test_extractor_pipe_alias(tmp_path: Path) -> None:
    """`[[slug|display text]]` resolves to `slug`."""
    _write(tmp_path / "concepts" / "src.md", "See [[target|the target]] please.")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/src"]


def test_extractor_anchor_in_link(tmp_path: Path) -> None:
    """`[[slug#heading]]` resolves to `slug` (anchor is dropped for backlinks)."""
    _write(tmp_path / "concepts" / "src.md", "Jump to [[target#section-two]].")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/src"]


def test_extractor_pipe_and_anchor_combined(tmp_path: Path) -> None:
    _write(tmp_path / "concepts" / "src.md", "Hop to [[target#heading|aliased]].")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/src"]


def test_extractor_table_escaped_pipe(tmp_path: Path) -> None:
    """In tables the alias pipe is escaped `\\|`; the target still resolves."""
    _write(tmp_path / "concepts" / "src.md", "| [[target\\|label]] | x |")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/src"]


def test_extractor_drops_unresolvable_link(tmp_path: Path) -> None:
    """A link to a non-existent target is not an edge (no phantom backlink)."""
    _write(tmp_path / "concepts" / "a.md", "Dangling [[nonexistent]] ref.")
    index = build_backlinks_index(tmp_path)
    assert index.get("concepts/nonexistent", []) == []
    assert index == {}


def test_extractor_drops_substrate_citations(tmp_path: Path) -> None:
    """daily/raw citations are sources, not backlink edges. Realistic layout:
    daily/ is a sibling of knowledge/ under the vault root."""
    knowledge = tmp_path / "knowledge"
    _write(tmp_path / "daily" / "2026-05-15.md", "—")
    _write(knowledge / "concepts" / "a.md", "Cited in [[../../daily/2026-05-15.md]].")
    index = build_backlinks_index(knowledge)
    # The daily file lives outside the knowledge dir → no canonical slug → dropped.
    assert index == {}


def test_extractor_ignores_self_link(tmp_path: Path) -> None:
    """An article linking to itself is NOT its own backlink."""
    _write(tmp_path / "concepts" / "a.md", "I cite [[a]] from inside a.")
    index = build_backlinks_index(tmp_path)
    assert index.get("concepts/a", []) == []


def test_extractor_ignores_code_fence_links(tmp_path: Path) -> None:
    """Wikilinks inside fenced code blocks are illustrative, not real edges."""
    _write(
        tmp_path / "concepts" / "src.md",
        "Example syntax:\n```\n[[fake-link]]\n```\nReal: [[real-link]]",
    )
    _write(tmp_path / "concepts" / "real-link.md", "—")
    _write(tmp_path / "concepts" / "fake-link.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/real-link"] == ["concepts/src"]
    assert index.get("concepts/fake-link", []) == []


def test_extractor_ignores_frontmatter_links(tmp_path: Path) -> None:
    """Links inside YAML frontmatter are metadata, not body-edges."""
    _write(
        tmp_path / "concepts" / "src.md",
        "---\ntitle: src\ntags: [[fake-tag]]\n---\nBody [[real]].",
    )
    _write(tmp_path / "concepts" / "real.md", "—")
    _write(tmp_path / "concepts" / "fake-tag.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/real"] == ["concepts/src"]
    assert index.get("concepts/fake-tag", []) == []


def test_extractor_dedupes_multiple_links_to_same_target(tmp_path: Path) -> None:
    """If `a` links to `b` three times, backlinks_index[b] == ['a'] not ['a','a','a']."""
    _write(tmp_path / "concepts" / "a.md", "[[b]] and [[b]] and [[b]] again.")
    _write(tmp_path / "concepts" / "b.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/b"] == ["concepts/a"]


def test_extractor_sorts_incoming_alphabetically(tmp_path: Path) -> None:
    """Stable ordering so re-runs produce byte-identical output."""
    _write(tmp_path / "concepts" / "zulu.md", "[[target]]")
    _write(tmp_path / "concepts" / "alpha.md", "[[target]]")
    _write(tmp_path / "concepts" / "mike.md", "[[target]]")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/alpha", "concepts/mike", "concepts/zulu"]


def test_extractor_walks_nested_buckets(tmp_path: Path) -> None:
    """Articles live under concepts/, projects/, people/, etc."""
    _write(tmp_path / "concepts" / "c1.md", "[[../projects/p1]]")
    _write(tmp_path / "projects" / "p1.md", "[[../concepts/c1]]")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/c1"] == ["projects/p1"]
    assert index["projects/p1"] == ["concepts/c1"]


def test_extractor_skips_index_md(tmp_path: Path) -> None:
    """knowledge/index.md is the flat catalog — treating it as an article would
    make every other article have an incoming link from `index`. Skip it."""
    _write(tmp_path / "index.md", "| [[concepts/a]] | summary |\n| [[concepts/b]] | summary |")
    _write(tmp_path / "concepts" / "a.md", "—")
    _write(tmp_path / "concepts" / "b.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index.get("concepts/a", []) == []
    assert index.get("concepts/b", []) == []


# ── writer ─────────────────────────────────────────────────────────────


def test_writer_adds_footer_when_incoming_present(tmp_path: Path) -> None:
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.\n")
    changed = write_backlinks_footer(art, ["concepts/alpha", "concepts/bravo"], tmp_path)
    assert changed is True
    txt = art.read_text(encoding="utf-8")
    assert "<!-- backlinks:begin -->" in txt
    assert "<!-- backlinks:end -->" in txt
    assert "## Backlinks" in txt
    # Same-folder incoming → bare relative link.
    assert "[[alpha]]" in txt
    assert "[[bravo]]" in txt


def test_writer_renders_cross_folder_incoming_relative(tmp_path: Path) -> None:
    """REGRESSION GUARD (relativize-wikilinks arc): a backlink from another
    bucket must render with `../`, not as a vault-root path Obsidian can't
    resolve from a nested article."""
    art = tmp_path / "people" / "alex.md"
    _write(art, "# Alex\n\nBody.\n")
    write_backlinks_footer(art, ["concepts/agi-level-3-urgency"], tmp_path)
    txt = art.read_text(encoding="utf-8")
    assert "[[../concepts/agi-level-3-urgency]]" in txt


def test_writer_is_idempotent(tmp_path: Path) -> None:
    """Second call with same input produces zero file change."""
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.\n")
    write_backlinks_footer(art, ["concepts/alpha", "concepts/bravo"], tmp_path)
    after_first = art.read_text(encoding="utf-8")
    changed = write_backlinks_footer(art, ["concepts/alpha", "concepts/bravo"], tmp_path)
    assert changed is False
    assert art.read_text(encoding="utf-8") == after_first


def test_writer_replaces_existing_block(tmp_path: Path) -> None:
    """Re-run with different incoming list updates the block in place."""
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.\n")
    write_backlinks_footer(art, ["concepts/alpha"], tmp_path)
    changed = write_backlinks_footer(
        art, ["concepts/alpha", "concepts/bravo", "concepts/charlie"], tmp_path
    )
    assert changed is True
    txt = art.read_text(encoding="utf-8")
    assert txt.count("<!-- backlinks:begin -->") == 1
    assert txt.count("<!-- backlinks:end -->") == 1
    assert "[[charlie]]" in txt


def test_writer_removes_block_when_incoming_empty(tmp_path: Path) -> None:
    """If incoming list is empty, the sentinel pair is removed entirely."""
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.\n")
    write_backlinks_footer(art, ["concepts/alpha"], tmp_path)
    changed = write_backlinks_footer(art, [], tmp_path)
    assert changed is True
    txt = art.read_text(encoding="utf-8")
    assert "<!-- backlinks:begin -->" not in txt
    assert "## Backlinks" not in txt
    assert "Body." in txt


def test_writer_preserves_operator_content_above_footer(tmp_path: Path) -> None:
    """Anything above the sentinel survives a footer rewrite."""
    art = tmp_path / "concepts" / "target.md"
    original = "---\ntitle: Target\n---\n# Target\n\nOperator paragraph.\n\n## A heading\n\nMore body.\n"
    _write(art, original)
    write_backlinks_footer(art, ["concepts/alpha"], tmp_path)
    txt = art.read_text(encoding="utf-8")
    assert "Operator paragraph." in txt
    assert "## A heading" in txt
    assert "More body." in txt
    assert txt.rindex("More body.") < txt.rindex("<!-- backlinks:begin -->")


def test_writer_no_op_on_empty_incoming_and_no_existing_block(tmp_path: Path) -> None:
    """No incoming + no prior block → no change, no spurious touch."""
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.\n")
    before_mtime = art.stat().st_mtime_ns
    changed = write_backlinks_footer(art, [], tmp_path)
    assert changed is False
    assert art.stat().st_mtime_ns == before_mtime


def test_writer_handles_missing_trailing_newline(tmp_path: Path) -> None:
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.")  # no trailing newline
    write_backlinks_footer(art, ["concepts/alpha"], tmp_path)
    txt = art.read_text(encoding="utf-8")
    assert txt.endswith("\n")
    assert "<!-- backlinks:end -->" in txt


# ── orchestrator ───────────────────────────────────────────────────────


def test_orchestrator_writes_footers_across_corpus(tmp_path: Path) -> None:
    _write(tmp_path / "concepts" / "a.md", "Refs [[b]] and [[c]].")
    _write(tmp_path / "concepts" / "b.md", "Refs [[c]].")
    _write(tmp_path / "concepts" / "c.md", "Plain.")
    stats = run_backlinks_pass(tmp_path)
    assert stats["articles_seen"] == 3
    assert stats["articles_written"] >= 2  # b (←a) and c (←a,b) get footers
    b_txt = (tmp_path / "concepts" / "b.md").read_text(encoding="utf-8")
    c_txt = (tmp_path / "concepts" / "c.md").read_text(encoding="utf-8")
    a_txt = (tmp_path / "concepts" / "a.md").read_text(encoding="utf-8")
    assert "[[a]]" in b_txt
    assert "[[a]]" in c_txt and "[[b]]" in c_txt
    # `a` has no incoming → no footer.
    assert "<!-- backlinks:begin -->" not in a_txt


def test_orchestrator_is_idempotent(tmp_path: Path) -> None:
    """Second run on an unchanged corpus writes zero files."""
    _write(tmp_path / "concepts" / "a.md", "Refs [[b]].")
    _write(tmp_path / "concepts" / "b.md", "Plain.")
    run_backlinks_pass(tmp_path)
    stats = run_backlinks_pass(tmp_path)
    assert stats["articles_written"] == 0


def test_orchestrator_handles_empty_corpus(tmp_path: Path) -> None:
    stats = run_backlinks_pass(tmp_path)
    assert stats["articles_seen"] == 0
    assert stats["articles_written"] == 0
