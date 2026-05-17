"""Tests for the backlinks-footer corpus-pass (M020).

Three layers:

- extractor (build_backlinks_index): pure function over a knowledge_dir
- writer (write_backlinks_footer): sentinel-managed region on a single article
- orchestrator (run_backlinks_pass): walks corpus + writes footers

Each layer is covered independently. Edge cases live where they apply.

Convention: wikilinks are path-relative (`[[concepts/foo]]` → `knowledge/concepts/foo.md`),
matching `core.utils.wiki_article_exists`. Article slugs in the index are the same
form (`concepts/foo`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    """Article `concepts/a` links to `concepts/b`; index['concepts/b'] == ['concepts/a']."""
    _write(tmp_path / "concepts" / "a.md", "Body with a [[concepts/b]] link.")
    _write(tmp_path / "concepts" / "b.md", "Plain body, no links.")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/b"] == ["concepts/a"]
    assert index.get("concepts/a", []) == []


def test_extractor_pipe_alias(tmp_path: Path) -> None:
    """`[[slug|display text]]` resolves to `slug`."""
    _write(tmp_path / "concepts" / "src.md", "See [[concepts/target|the target]] please.")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/src"]


def test_extractor_anchor_in_link(tmp_path: Path) -> None:
    """`[[slug#heading]]` resolves to `slug` (anchor is dropped for backlinks)."""
    _write(tmp_path / "concepts" / "src.md", "Jump to [[concepts/target#section-two]].")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/src"]


def test_extractor_pipe_and_anchor_combined(tmp_path: Path) -> None:
    _write(tmp_path / "concepts" / "src.md", "Hop to [[concepts/target#heading|aliased]].")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/src"]


def test_extractor_ignores_self_link(tmp_path: Path) -> None:
    """An article linking to itself is NOT its own backlink."""
    _write(tmp_path / "concepts" / "a.md", "I cite [[concepts/a]] from inside a.")
    index = build_backlinks_index(tmp_path)
    assert index.get("concepts/a", []) == []


def test_extractor_ignores_code_fence_links(tmp_path: Path) -> None:
    """Wikilinks inside fenced code blocks are illustrative, not real edges."""
    _write(
        tmp_path / "concepts" / "src.md",
        "Example syntax:\n```\n[[concepts/fake-link]]\n```\nReal: [[concepts/real-link]]",
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
        "---\ntitle: src\ntags: [[concepts/fake-tag]]\n---\nBody [[concepts/real]].",
    )
    _write(tmp_path / "concepts" / "real.md", "—")
    _write(tmp_path / "concepts" / "fake-tag.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/real"] == ["concepts/src"]
    assert index.get("concepts/fake-tag", []) == []


def test_extractor_dedupes_multiple_links_to_same_target(tmp_path: Path) -> None:
    """If `a` links to `b` three times, backlinks_index[b] == ['a'] not ['a','a','a']."""
    _write(tmp_path / "concepts" / "a.md",
           "[[concepts/b]] and [[concepts/b]] and [[concepts/b]] again.")
    _write(tmp_path / "concepts" / "b.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/b"] == ["concepts/a"]


def test_extractor_sorts_incoming_alphabetically(tmp_path: Path) -> None:
    """Stable ordering so re-runs produce byte-identical output."""
    _write(tmp_path / "concepts" / "zulu.md", "[[concepts/target]]")
    _write(tmp_path / "concepts" / "alpha.md", "[[concepts/target]]")
    _write(tmp_path / "concepts" / "mike.md", "[[concepts/target]]")
    _write(tmp_path / "concepts" / "target.md", "—")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/target"] == ["concepts/alpha", "concepts/mike", "concepts/zulu"]


def test_extractor_walks_nested_buckets(tmp_path: Path) -> None:
    """Articles live under concepts/, projects/, people/, etc."""
    _write(tmp_path / "concepts" / "c1.md", "[[projects/p1]]")
    _write(tmp_path / "projects" / "p1.md", "[[concepts/c1]]")
    index = build_backlinks_index(tmp_path)
    assert index["concepts/c1"] == ["projects/p1"]
    assert index["projects/p1"] == ["concepts/c1"]


def test_extractor_skips_index_md(tmp_path: Path) -> None:
    """knowledge/index.md is the flat catalog — every entry has wikilinks; treating it as an
    article would make every other article have an incoming link from `index`. Skip it."""
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
    changed = write_backlinks_footer(art, ["concepts/alpha", "concepts/bravo"])
    assert changed is True
    txt = art.read_text(encoding="utf-8")
    assert "<!-- backlinks:begin -->" in txt
    assert "<!-- backlinks:end -->" in txt
    assert "## Backlinks" in txt
    assert "[[concepts/alpha]]" in txt
    assert "[[concepts/bravo]]" in txt


def test_writer_is_idempotent(tmp_path: Path) -> None:
    """Second call with same input produces zero file change."""
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.\n")
    write_backlinks_footer(art, ["concepts/alpha", "concepts/bravo"])
    after_first = art.read_text(encoding="utf-8")
    changed = write_backlinks_footer(art, ["concepts/alpha", "concepts/bravo"])
    assert changed is False
    assert art.read_text(encoding="utf-8") == after_first


def test_writer_replaces_existing_block(tmp_path: Path) -> None:
    """Re-run with different incoming list updates the block in place."""
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.\n")
    write_backlinks_footer(art, ["concepts/alpha"])
    changed = write_backlinks_footer(art, ["concepts/alpha", "concepts/bravo", "concepts/charlie"])
    assert changed is True
    txt = art.read_text(encoding="utf-8")
    assert txt.count("<!-- backlinks:begin -->") == 1
    assert txt.count("<!-- backlinks:end -->") == 1
    assert "[[concepts/charlie]]" in txt


def test_writer_removes_block_when_incoming_empty(tmp_path: Path) -> None:
    """If incoming list is empty, the sentinel pair is removed entirely
    (no orphan empty Backlinks heading left behind)."""
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.\n")
    write_backlinks_footer(art, ["concepts/alpha"])
    changed = write_backlinks_footer(art, [])
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
    write_backlinks_footer(art, ["concepts/alpha"])
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
    changed = write_backlinks_footer(art, [])
    assert changed is False
    assert art.stat().st_mtime_ns == before_mtime


def test_writer_handles_missing_trailing_newline(tmp_path: Path) -> None:
    art = tmp_path / "concepts" / "target.md"
    _write(art, "# Target\n\nBody.")  # no trailing newline
    write_backlinks_footer(art, ["concepts/alpha"])
    txt = art.read_text(encoding="utf-8")
    assert txt.endswith("\n")
    assert "<!-- backlinks:end -->" in txt


# ── orchestrator ───────────────────────────────────────────────────────


def test_orchestrator_writes_footers_across_corpus(tmp_path: Path) -> None:
    _write(tmp_path / "concepts" / "a.md", "Refs [[concepts/b]] and [[concepts/c]].")
    _write(tmp_path / "concepts" / "b.md", "Refs [[concepts/c]].")
    _write(tmp_path / "concepts" / "c.md", "Plain.")
    stats = run_backlinks_pass(tmp_path)
    assert stats["articles_seen"] == 3
    assert stats["articles_written"] >= 2  # b (←a) and c (←a,b) get footers
    b_txt = (tmp_path / "concepts" / "b.md").read_text(encoding="utf-8")
    c_txt = (tmp_path / "concepts" / "c.md").read_text(encoding="utf-8")
    a_txt = (tmp_path / "concepts" / "a.md").read_text(encoding="utf-8")
    assert "[[concepts/a]]" in b_txt
    assert "[[concepts/a]]" in c_txt and "[[concepts/b]]" in c_txt
    # `a` has no incoming → no footer.
    assert "<!-- backlinks:begin -->" not in a_txt


def test_orchestrator_is_idempotent(tmp_path: Path) -> None:
    """Second run on an unchanged corpus writes zero files."""
    _write(tmp_path / "concepts" / "a.md", "Refs [[concepts/b]].")
    _write(tmp_path / "concepts" / "b.md", "Plain.")
    run_backlinks_pass(tmp_path)
    stats = run_backlinks_pass(tmp_path)
    assert stats["articles_written"] == 0


def test_orchestrator_handles_empty_corpus(tmp_path: Path) -> None:
    stats = run_backlinks_pass(tmp_path)
    assert stats["articles_seen"] == 0
    assert stats["articles_written"] == 0
