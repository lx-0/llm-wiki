"""Tests for the inbox + html Preprocessors (`scripts/preprocessors/`).

Both are LLM-bound on their happy paths (inbox calls Ollama for classification;
html visual-mode calls Playwright + Vision-LLM). We test the pure helpers that
don't touch the network (frontmatter injection, html2text round-trip, title
extraction), the two-zone inbox routing, and the in-process HTML delegation —
the last un-mocked, so the wiring the compile pipeline depends on is actually
exercised rather than faked behind a `subprocess.run` stub.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import preprocessors.html_ingest as ingest_html_mod
import preprocessors.inbox as process_inbox_mod
from core.utils import slugify


@pytest.fixture
def process_inbox_mod_fixture():
    return process_inbox_mod


@pytest.fixture
def ingest_html_mod_fixture():
    return ingest_html_mod


# ── inbox.add_frontmatter ───────────────────────────────────────────


def test_add_frontmatter_skips_files_with_existing_block(tmp_path):
    p = tmp_path / "note.md"
    p.write_text("---\ntype: existing\n---\n\nbody\n", encoding="utf-8")
    process_inbox_mod.add_frontmatter(p, {"category": "note"})
    assert p.read_text(encoding="utf-8").startswith("---\ntype: existing\n")


def test_add_frontmatter_skips_unsupported_suffixes(tmp_path):
    p = tmp_path / "thing.pdf"
    p.write_text("binary-ish", encoding="utf-8")
    process_inbox_mod.add_frontmatter(p, {"category": "paper"})
    # No frontmatter added — PDF files don't get YAML frontmatter
    assert p.read_text(encoding="utf-8") == "binary-ish"


def test_add_frontmatter_injects_for_markdown(tmp_path):
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


def test_add_frontmatter_uses_defaults_when_classification_missing_fields(tmp_path):
    p = tmp_path / "drop.md"
    p.write_text("body\n", encoding="utf-8")
    process_inbox_mod.add_frontmatter(p, {})  # empty classification
    content = p.read_text(encoding="utf-8")
    assert "type: note" in content       # default category
    assert "language: de" in content     # default language
    assert "tags: []" in content         # empty tag list


# ── html.extract_content (html2text round-trip) ────────────────────


def test_extract_content_emits_markdown():
    html = "<html><body><h1>Title</h1><p>Hello <a href='https://example.com'>world</a>.</p></body></html>"
    md = ingest_html_mod.extract_content(html)
    assert "# Title" in md
    assert "https://example.com" in md
    assert "Hello" in md and "world" in md


def test_extract_content_preserves_inline_links():
    html = '<p>See <a href="https://example.com/page">this page</a>.</p>'
    md = ingest_html_mod.extract_content(html)
    # html2text inline mode emits `[text](<url>)` with angle-bracket-protected URL.
    assert "[this page]" in md
    assert "https://example.com/page" in md


# ── html.extract_title ─────────────────────────────────────────────


def test_extract_title_finds_basic():
    html = "<html><head><title>Test Page</title></head><body></body></html>"
    assert ingest_html_mod.extract_title(html) == "Test Page"


def test_extract_title_handles_multiline():
    html = "<html><head><title>\n  Multi\n  Line\n</title></head></html>"
    title = ingest_html_mod.extract_title(html)
    # Function returns the raw match content with .strip() — internal newlines kept
    assert "Multi" in title and "Line" in title


def test_extract_title_returns_empty_when_missing():
    html = "<html><body>No title here</body></html>"
    assert ingest_html_mod.extract_title(html) == ""


def test_extract_title_is_case_insensitive():
    html = "<HTML><HEAD><TITLE>Upcase</TITLE></HEAD></HTML>"
    assert ingest_html_mod.extract_title(html) == "Upcase"


# ── core.utils.slugify (html's slug source after C12) ──────────────


def test_slugify_lowercases_and_dashes():
    assert slugify("Hello World") == "hello-world"


def test_slugify_strips_punctuation():
    assert slugify("It's a Test! 100%") == "its-a-test-100"


def test_slugify_collapses_multiple_separators():
    assert slugify("a___b   c--d") == "a-b-c-d"


def test_slugify_caps_at_max_len():
    long_input = "a" * 200
    assert len(slugify(long_input, max_len=80)) == 80


def test_slugify_no_cap_by_default():
    long_input = "a" * 200
    assert len(slugify(long_input)) == 200


# ── inbox two-zone routing (M022-S01-T05) ──────────────────────────


def _isolated_inbox(tmp_path: Path, mod):
    """Redirect every path constant in the inbox module to tmp_path.

    Returns a dict of the redirected dirs for assertion convenience.
    """
    inbox = tmp_path / "inbox"
    raw = tmp_path / "raw"
    inbox.mkdir()
    raw.mkdir()
    dirs = {
        "inbox": inbox,
        "raw_inbox_wiki": raw / "inbox-wiki",
        "raw_articles": raw / "articles",
        "raw_notes": raw / "notes",
        "raw_transcripts": raw / "transcripts",
        "root": tmp_path,
    }
    mod.INBOX_DIR = inbox
    mod.RAW_DIR = raw
    mod.RAW_INBOX_WIKI_DIR = dirs["raw_inbox_wiki"]
    mod.RAW_ARTICLES_DIR = dirs["raw_articles"]
    mod.RAW_NOTES_DIR = dirs["raw_notes"]
    mod.RAW_TRANSCRIPTS_DIR = dirs["raw_transcripts"]
    mod.ROOT_DIR = tmp_path
    mod.CATEGORY_DIRS = {
        "article": dirs["raw_articles"],
        "note": dirs["raw_notes"],
        "transcript": dirs["raw_transcripts"],
    }
    return dirs


def _isolate_html(tmp_path: Path, dirs: dict) -> None:
    """Point the html module's write targets at the same isolated tmp tree.

    The inbox HTML branch calls `preprocessors.html_ingest.ingest` in-process,
    and `ingest()` writes to the html module's own `RAW_ARTICLES_DIR` / `ROOT_DIR`
    globals — redirect those too so the artifact lands under tmp_path.
    """
    ingest_html_mod.RAW_ARTICLES_DIR = dirs["raw_articles"]
    ingest_html_mod.ROOT_DIR = tmp_path


def test_process_inbox_md_writes_artifact_and_archives_original(tmp_path, monkeypatch):
    dirs = _isolated_inbox(tmp_path, process_inbox_mod)
    original = "# Hello\nThis is a test note body.\n"
    (dirs["inbox"] / "test.md").write_text(original)

    monkeypatch.setattr(process_inbox_mod, "classify_file", lambda fp, m: {"category": "note", "suggested_name": "test"})
    process_inbox_mod.process_inbox(model="stub", dry_run=False)

    artifact = dirs["raw_notes"] / "test.md"
    archive = dirs["raw_inbox_wiki"] / "test.md"
    assert artifact.exists(), "md artifact missing from raw/notes/"
    assert archive.exists(), "md original missing from raw/inbox-wiki/"
    assert artifact.read_text().startswith("---\n"), "artifact lacks frontmatter"
    assert archive.read_text() == original, "original was mutated"
    assert list(dirs["inbox"].iterdir()) == [], "inbox not drained"


def test_process_inbox_html_ingests_in_process_and_archives_original(tmp_path, monkeypatch):
    """The .html branch must ingest IN-PROCESS (no subprocess) and archive the
    original. Regression guard for the C12 live bug: the old delegation shelled
    out to `ROOT_DIR/scripts/ingest-html.py` — a path that exists in no deployed
    layout — so every HTML drop failed and was stranded in inbox/ forever."""
    dirs = _isolated_inbox(tmp_path, process_inbox_mod)
    _isolate_html(tmp_path, dirs)
    html_body = "<html><head><title>My Page</title></head><body><h1>Title</h1><p>Body text.</p></body></html>"
    (dirs["inbox"] / "page.html").write_text(html_body)

    # Skip the visual path (Playwright + Vision-LLM) — content extraction and
    # file writing run for real, exercising the full in-process wiring.
    monkeypatch.setattr(ingest_html_mod, "screenshot_html", lambda *a, **k: False)
    # Guard: the html path must NOT spawn a subprocess (the old broken behavior).
    def _boom(*a, **k):
        raise AssertionError("HTML path spawned a subprocess — should be in-process")
    monkeypatch.setattr(ingest_html_mod.subprocess, "run", _boom)
    monkeypatch.setattr(process_inbox_mod.subprocess, "run", _boom)

    process_inbox_mod.process_inbox(model="stub", dry_run=False)

    archive = dirs["raw_inbox_wiki"] / "page.html"
    assert archive.exists(), "HTML original missing from raw/inbox-wiki/ (regression: stranded again?)"
    assert archive.read_text() == html_body, "HTML original was mutated"
    assert list(dirs["inbox"].iterdir()) == [], "inbox not drained"
    # The in-process ingest wrote a derived article + saved the original HTML.
    md_artifacts = list(dirs["raw_articles"].glob("*.md"))
    assert md_artifacts, "no markdown artifact written to raw/articles/ by in-process ingest"
    assert any(p.suffix == ".html" for p in dirs["raw_articles"].iterdir()), "original HTML not saved alongside article"


def test_process_inbox_html_missing_output_leaves_inbox_untouched(tmp_path, monkeypatch):
    """If the in-process ingest yields no output, the original stays in inbox/
    (not archived) so a later retry can pick it up — no silent data loss."""
    dirs = _isolated_inbox(tmp_path, process_inbox_mod)
    _isolate_html(tmp_path, dirs)
    (dirs["inbox"] / "page.html").write_text("<html></html>")

    monkeypatch.setattr(process_inbox_mod, "ingest_html_source", lambda *a, **k: None)
    process_inbox_mod.process_inbox(model="stub", dry_run=False)

    assert (dirs["inbox"] / "page.html").exists(), "failed HTML ingest should leave the original in inbox/"
    assert not dirs["raw_inbox_wiki"].exists() or list(dirs["raw_inbox_wiki"].iterdir()) == []


def test_process_inbox_mp3_archives_only_no_artifact(tmp_path, monkeypatch):
    dirs = _isolated_inbox(tmp_path, process_inbox_mod)
    audio_bytes = b"FAKE_MP3_HEADER\x00\x01\x02"
    (dirs["inbox"] / "memo.mp3").write_bytes(audio_bytes)

    classify_calls = []
    monkeypatch.setattr(process_inbox_mod, "classify_file", lambda fp, m: classify_calls.append(fp) or None)
    process_inbox_mod.process_inbox(model="stub", dry_run=False)

    archive = dirs["raw_inbox_wiki"] / "memo.mp3"
    assert archive.exists(), "mp3 original missing from raw/inbox-wiki/"
    assert archive.read_bytes() == audio_bytes, "mp3 original was mutated"
    assert not dirs["raw_notes"].exists() or list(dirs["raw_notes"].iterdir()) == [], "binary should produce no artifact"
    assert classify_calls == [], "binary path should skip LLM classify"
    assert list(dirs["inbox"].iterdir()) == [], "inbox not drained"


def test_process_inbox_pdf_archives_only_no_artifact(tmp_path, monkeypatch):
    dirs = _isolated_inbox(tmp_path, process_inbox_mod)
    pdf_bytes = b"%PDF-1.4\n%fake"
    (dirs["inbox"] / "paper.pdf").write_bytes(pdf_bytes)

    classify_calls = []
    monkeypatch.setattr(process_inbox_mod, "classify_file", lambda fp, m: classify_calls.append(fp) or None)
    process_inbox_mod.process_inbox(model="stub", dry_run=False)

    archive = dirs["raw_inbox_wiki"] / "paper.pdf"
    assert archive.exists(), "pdf original missing from raw/inbox-wiki/"
    assert archive.read_bytes() == pdf_bytes
    assert not dirs["raw_notes"].exists() or list(dirs["raw_notes"].iterdir()) == []
    assert classify_calls == [], "binary path should skip LLM classify"
    assert list(dirs["inbox"].iterdir()) == [], "inbox not drained"
