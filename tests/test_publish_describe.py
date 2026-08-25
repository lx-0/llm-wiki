"""Tests for publish description sourcing (M030-S01-T03, vault-rel since S04).

write_article requires a non-empty description ≤1024 chars — it drives
listings and search on the meinkontext side. Source of truth is the article's
index.md summary row; body paragraph and stem are fallbacks.
"""
from __future__ import annotations

from pathlib import Path

from publish.describe import describe, description_index

INDEX = """# Knowledge Base Index

| Article | Summary | Compiled From | Updated |
|---------|---------|---------------|---------|
| [[concepts/foo\\|Foo]] | What foo is about. | raw/a.md | 2026-08-01 |
| [[people/alex]] | Wer [[concepts/foo\\|Foo]] baut. | daily/x.md | 2026-08-02 |
| [[concepts/empty]] |  | raw/b.md | 2026-08-03 |
"""


def _knowledge(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    k = vault / "knowledge"
    for rel in ("concepts/foo.md", "people/alex.md", "concepts/empty.md"):
        p = k / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("body\n", encoding="utf-8")
    (k / "index.md").write_text(INDEX, encoding="utf-8")
    return vault, k


def test_description_index_maps_vault_rel_to_summary(tmp_path: Path) -> None:
    vault, k = _knowledge(tmp_path)
    idx = description_index(INDEX, k, vault)
    assert idx["knowledge/concepts/foo.md"] == "What foo is about."
    assert "knowledge/people/alex.md" in idx


def test_index_summary_wikilinks_collapse_to_text(tmp_path: Path) -> None:
    vault, k = _knowledge(tmp_path)
    idx = description_index(INDEX, k, vault)
    assert idx["knowledge/people/alex.md"] == "Wer Foo baut."


def test_describe_prefers_index_summary(tmp_path: Path) -> None:
    vault, k = _knowledge(tmp_path)
    idx = description_index(INDEX, k, vault)
    body = "---\ndomain: x\n---\n\n# Title\n\nFirst paragraph here.\n"
    assert describe("knowledge/concepts/foo.md", body, idx) == "What foo is about."


def test_describe_falls_back_to_first_paragraph(tmp_path: Path) -> None:
    vault, k = _knowledge(tmp_path)
    idx = description_index(INDEX, k, vault)
    body = (
        "---\ndomain: x\n---\n\n# Heading\n\n"
        "Erster Absatz mit [[concepts/foo|Foo]] drin.\nZweite Zeile.\n\nNext para.\n"
    )
    got = describe("knowledge/concepts/empty.md", body, idx)
    assert got == "Erster Absatz mit Foo drin. Zweite Zeile."


def test_describe_final_fallback_is_stem(tmp_path: Path) -> None:
    got = describe("knowledge/concepts/some-article.md", "---\nx: y\n---\n", {})
    assert got == "some-article"


def test_describe_caps_at_1024(tmp_path: Path) -> None:
    long_body = "x" * 3000 + "\n"
    got = describe("knowledge/concepts/foo.md", long_body, {})
    assert len(got) <= 1024
    assert got.endswith("…")


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def test_describe_caps_by_utf16_units_not_codepoints(tmp_path: Path) -> None:
    # The server validates description.length in JS — UTF-16 code units, where
    # astral chars (emoji) count DOUBLE. Live incident 2026-08-25: beulco/
    # sprenger passed the Python len-cap yet were rejected upstream.
    emoji_summary = "🚀" * 600  # 600 codepoints, 1200 UTF-16 units
    rel = "knowledge/concepts/foo.md"
    got = describe(rel, "", {rel: emoji_summary})
    assert _utf16_units(got) <= 1024
    assert got.endswith("…")
