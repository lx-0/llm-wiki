"""Tests for `scripts/process-inbox.py` + `scripts/ingest-html.py`.

Both scripts are LLM-bound on their happy paths (process-inbox calls
Ollama for classification; ingest-html visual-mode calls Playwright +
Vision-LLM). We test the pure helpers that don't touch the network:
frontmatter injection, html2text round-trip, title/slug extraction.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module(name: str, file_basename: str):
    """Load a script via importlib (handles `process-inbox.py` filename with hyphen)."""
    src = Path(__file__).resolve().parent.parent / "scripts" / file_basename
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def process_inbox_mod():
    return _load_module("process_inbox", "process-inbox.py")


@pytest.fixture
def ingest_html_mod():
    return _load_module("ingest_html", "ingest-html.py")


# ── process-inbox.add_frontmatter ───────────────────────────────────


def test_add_frontmatter_skips_files_with_existing_block(process_inbox_mod, tmp_path):
    p = tmp_path / "note.md"
    p.write_text("---\ntype: existing\n---\n\nbody\n", encoding="utf-8")
    process_inbox_mod.add_frontmatter(p, {"category": "note"})
    assert p.read_text(encoding="utf-8").startswith("---\ntype: existing\n")


def test_add_frontmatter_skips_unsupported_suffixes(process_inbox_mod, tmp_path):
    p = tmp_path / "thing.pdf"
    p.write_text("binary-ish", encoding="utf-8")
    process_inbox_mod.add_frontmatter(p, {"category": "paper"})
    # No frontmatter added — PDF files don't get YAML frontmatter
    assert p.read_text(encoding="utf-8") == "binary-ish"


def test_add_frontmatter_injects_for_markdown(process_inbox_mod, tmp_path):
    p = tmp_path / "drop.md"
    p.write_text("# Hello\n\nbody\n", encoding="utf-8")
    classification = {
        "category": "article",
        "tags": ["foo", "bar"],
        "language": "en",
        "summary": "Test article",
    }
    process_inbox_mod.add_frontmatter(p, classification)
    content = p.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "type: article" in content
    assert "language: en" in content
    assert "tags: [foo, bar]" in content
    assert 'origin: "inbox-drop"' in content
    assert "# Hello" in content  # original body preserved


def test_add_frontmatter_uses_defaults_when_classification_missing_fields(process_inbox_mod, tmp_path):
    p = tmp_path / "drop.md"
    p.write_text("body\n", encoding="utf-8")
    process_inbox_mod.add_frontmatter(p, {})  # empty classification
    content = p.read_text(encoding="utf-8")
    assert "type: note" in content       # default category
    assert "language: de" in content     # default language
    assert "tags: []" in content         # empty tag list


# ── ingest-html.extract_content (html2text round-trip) ─────────────


def test_extract_content_emits_markdown(ingest_html_mod):
    html = "<html><body><h1>Title</h1><p>Hello <a href='https://example.com'>world</a>.</p></body></html>"
    md = ingest_html_mod.extract_content(html)
    assert "# Title" in md
    assert "https://example.com" in md
    assert "Hello" in md and "world" in md


def test_extract_content_preserves_inline_links(ingest_html_mod):
    html = '<p>See <a href="https://example.com/page">this page</a>.</p>'
    md = ingest_html_mod.extract_content(html)
    # html2text inline mode emits `[text](<url>)` with angle-bracket-protected URL.
    assert "[this page]" in md
    assert "https://example.com/page" in md


# ── ingest-html.extract_title ──────────────────────────────────────


def test_extract_title_finds_basic(ingest_html_mod):
    html = "<html><head><title>Test Page</title></head><body></body></html>"
    assert ingest_html_mod.extract_title(html) == "Test Page"


def test_extract_title_handles_multiline(ingest_html_mod):
    html = "<html><head><title>\n  Multi\n  Line\n</title></head></html>"
    title = ingest_html_mod.extract_title(html)
    # Function returns the raw match content with .strip() — internal newlines kept
    assert "Multi" in title and "Line" in title


def test_extract_title_returns_empty_when_missing(ingest_html_mod):
    html = "<html><body>No title here</body></html>"
    assert ingest_html_mod.extract_title(html) == ""


def test_extract_title_is_case_insensitive(ingest_html_mod):
    html = "<HTML><HEAD><TITLE>Upcase</TITLE></HEAD></HTML>"
    assert ingest_html_mod.extract_title(html) == "Upcase"


# ── ingest-html.slugify ────────────────────────────────────────────


def test_slugify_lowercases_and_dashes(ingest_html_mod):
    assert ingest_html_mod.slugify("Hello World") == "hello-world"


def test_slugify_strips_punctuation(ingest_html_mod):
    assert ingest_html_mod.slugify("It's a Test! 100%") == "its-a-test-100"


def test_slugify_collapses_multiple_separators(ingest_html_mod):
    assert ingest_html_mod.slugify("a___b   c--d") == "a-b-c-d"


def test_slugify_caps_at_80_chars(ingest_html_mod):
    long_input = "a" * 200
    assert len(ingest_html_mod.slugify(long_input)) == 80
