"""Tests for `links_audit` — broken-link report + approval fixer.

Covers the pure pieces: tiered suggestion (bucket vs fuzzy vs none),
categorization (embeds / placeholders / dangling), and the corpus rewrite
(relative form, decorations preserved).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import links_audit as la


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    def w(rel: str, body: str = "—") -> None:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    # existing articles
    w("knowledge/connections/cascading-debug.md")
    w("knowledge/projects/ytstack.md")
    w("knowledge/people/garry-tan.md")
    w("knowledge/concepts/diagram.png")
    return tmp_path


# ── _suggest ──────────────────────────────────────────────────────────────


def test_suggest_bucket_tier_wrong_folder(vault: Path) -> None:
    kn = vault / "knowledge"
    slugs = ["connections/cascading-debug", "projects/ytstack"]
    by_base = {"cascading-debug": ["connections/cascading-debug"], "ytstack": ["projects/ytstack"]}
    slug, tier = la._suggest("concepts/cascading-debug", slugs, by_base)
    assert (slug, tier) == ("connections/cascading-debug", "bucket")


def test_suggest_fuzzy_tier_typo(vault: Path) -> None:
    slugs = ["projects/ytstack"]
    by_base = {"ytstack": ["projects/ytstack"]}
    slug, tier = la._suggest("projects/ydstack", slugs, by_base)
    assert (slug, tier) == ("projects/ytstack", "fuzzy")


def test_suggest_no_match_distinct_entity(vault: Path) -> None:
    slugs = ["people/alex"]
    by_base = {"alex": ["people/alex"]}
    # `eva` is a distinct person — string distance must NOT cross the cutoff.
    slug, tier = la._suggest("people/eva", slugs, by_base)
    assert slug is None and tier is None


def test_is_placeholder() -> None:
    assert la._is_placeholder("concepts/foo")
    assert la._is_placeholder("raw/notes/...")
    assert la._is_placeholder("…")
    assert la._is_placeholder("wikilink")
    assert not la._is_placeholder("concepts/real-article")


# ── build_audit ───────────────────────────────────────────────────────────


def test_build_audit_categorizes(vault: Path) -> None:
    kn = vault / "knowledge"
    (kn / "concepts" / "src.md").write_text(
        "Wrong bucket [[concepts/cascading-debug]]. "
        "Typo [[projects/ydstack]]. "
        "Missing [[concepts/totally-gone]]. "
        "Example [[concepts/foo]]. "
        "Embed ![[missing-image-xyz.png]]. "
        "Good [[../projects/ytstack]].",
        encoding="utf-8",
    )
    audit = la.build_audit(kn, vault)
    targets = {d.target: (d.suggestion, d.tier) for d in audit.dangling}
    assert targets["concepts/cascading-debug"] == ("connections/cascading-debug", "bucket")
    assert targets["projects/ydstack"] == ("projects/ytstack", "fuzzy")
    assert targets["concepts/totally-gone"] == (None, None)
    assert "concepts/foo" in {t for t, _, _ in audit.literals}
    assert any("missing-image-xyz.png" in t for t, _, _ in audit.embeds)
    # the resolvable link is not reported
    assert "../projects/ytstack" not in targets


# ── apply_fixes ───────────────────────────────────────────────────────────


def test_apply_fixes_rewrites_relative_preserving_alias(vault: Path) -> None:
    kn = vault / "knowledge"
    src = kn / "concepts" / "src.md"
    src.write_text("See [[concepts/cascading-debug|the debug pattern]] here.", encoding="utf-8")
    stats = la.apply_fixes(kn, vault, {"concepts/cascading-debug": "connections/cascading-debug"})
    assert stats == {"files": 1, "links": 1}
    # from concepts/src.md → connections/cascading-debug = ../connections/cascading-debug, alias kept
    assert src.read_text(encoding="utf-8") == "See [[../connections/cascading-debug|the debug pattern]] here."


def test_apply_fixes_only_touches_approved(vault: Path) -> None:
    kn = vault / "knowledge"
    src = kn / "concepts" / "src.md"
    src.write_text("[[concepts/cascading-debug]] and [[projects/untouched]].", encoding="utf-8")
    la.apply_fixes(kn, vault, {"concepts/cascading-debug": "connections/cascading-debug"})
    txt = src.read_text(encoding="utf-8")
    assert "[[../connections/cascading-debug]]" in txt
    assert "[[projects/untouched]]" in txt  # not in corrections → left as-is


def test_apply_fixes_skips_code_fence(vault: Path) -> None:
    kn = vault / "knowledge"
    src = kn / "concepts" / "src.md"
    src.write_text("```\n[[concepts/cascading-debug]]\n```\n[[concepts/cascading-debug]]", encoding="utf-8")
    stats = la.apply_fixes(kn, vault, {"concepts/cascading-debug": "connections/cascading-debug"})
    assert stats["links"] == 1  # only the non-fenced one
    txt = src.read_text(encoding="utf-8")
    assert "```\n[[concepts/cascading-debug]]\n```" in txt
