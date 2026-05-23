"""Tests for the capture collector (collectors/capture_collector.py).

The capture collector is the spine of M025's quick-capture-correction loop:
the operator one-taps cryptic notes / article snippets into a watched inbox
folder, and this collector turns each into a frontmatter-stamped note under
`raw/captures/` with a *deterministic, content-derived capture-ID*.

What separates it from voice.py (its structural template):

- **Stable capture-ID** = first 12 hex of `sha256(content.strip())`. Same
  content → same ID (idempotent on re-drop); edited content → new ID.
- **ID-derived filename** `capture-<id12>.md`, so a re-drop of identical
  content OVERWRITES the same article rather than spawning a duplicate.
  (Voice keys on timestamp+slug, so two identical notes coexist; captures
  must collapse to one because the ID is the loop's join-key.)
- **No punctuation pass** — captures may be article snippets; body is verbatim.

Everything else mirrors voice: graceful-agnostic gate, dry-run, two-zone
archive (`raw/inbox-mobile/captures/`) as the dedup mechanism, dot-file /
wrong-suffix skipping, empty-file archive-without-ingest.

All tests use a tmpdir vault; CONFIG + RAW_DIR are monkey-patched so the
real vault is never touched.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def capture_env(tmp_path, monkeypatch):
    """Tmpdir inbox + tmpdir vault, CONFIG and RAW_DIR pointed at them.

    Returns (collector, inbox, raw_captures_dir). The collector module is
    reloaded each test so it picks up the patched RAW_DIR constant at
    import time.
    """
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    vault_raw = tmp_path / "vault" / "raw"
    vault_raw.mkdir(parents=True)

    from core.config import CONFIG
    from core import paths as paths_mod

    monkeypatch.setattr(CONFIG.personal, "capture_inbox", str(inbox))
    monkeypatch.setattr(paths_mod, "RAW_DIR", vault_raw)

    from collectors import capture_collector as cap_mod
    importlib.reload(cap_mod)

    return cap_mod.CaptureCollector(), inbox, vault_raw / "captures"


# ── capture-ID: determinism + idempotency ────────────────────────────


def test_capture_id_is_deterministic_for_same_content():
    from collectors import capture_collector as cap_mod
    importlib.reload(cap_mod)

    a = cap_mod._capture_id("crack the nuts at the bakery")
    b = cap_mod._capture_id("crack the nuts at the bakery")
    assert a == b
    assert len(a) == 12
    assert all(c in "0123456789abcdef" for c in a)


def test_capture_id_ignores_surrounding_whitespace():
    from collectors import capture_collector as cap_mod
    importlib.reload(cap_mod)

    bare = cap_mod._capture_id("eine kryptische notiz")
    padded = cap_mod._capture_id("  \n eine kryptische notiz \n\n ")
    assert bare == padded


def test_capture_id_differs_for_different_content():
    from collectors import capture_collector as cap_mod
    importlib.reload(cap_mod)

    assert cap_mod._capture_id("note one") != cap_mod._capture_id("note two")


# ── Graceful agnostic ────────────────────────────────────────────────


def test_unconfigured_inbox_is_graceful(monkeypatch):
    from core.config import CONFIG
    from collectors import capture_collector as cap_mod
    importlib.reload(cap_mod)

    monkeypatch.setattr(CONFIG.personal, "capture_inbox", "")
    coll = cap_mod.CaptureCollector()
    assert coll.is_configured() is False
    result = coll.run()
    assert result.files_written == ()
    assert "not configured" in result.message


def test_missing_inbox_path_is_graceful(monkeypatch, tmp_path):
    from core.config import CONFIG
    from collectors import capture_collector as cap_mod
    importlib.reload(cap_mod)

    monkeypatch.setattr(CONFIG.personal, "capture_inbox", str(tmp_path / "nope"))
    coll = cap_mod.CaptureCollector()
    assert coll.is_configured() is False
    result = coll.run()
    assert "not found" in result.message


# ── Dry-run ──────────────────────────────────────────────────────────


def test_dry_run_counts_without_writing(capture_env):
    coll, inbox, raw_captures = capture_env
    (inbox / "a.txt").write_text("eine notiz")
    (inbox / "b.md").write_text("# noch eine")

    result = coll.run(dry_run=True)

    assert result.files_written == ()
    assert result.files_skipped == 2
    assert "dry-run" in result.message
    assert sorted(p.name for p in inbox.iterdir()) == ["a.txt", "b.md"]
    assert not raw_captures.exists()


# ── Real run: frontmatter, ID-derived filename, archive ──────────────


def test_real_run_writes_id_named_note_with_frontmatter(capture_env):
    coll, inbox, raw_captures = capture_env
    content = "crack the nuts — bakery context, not kiss alex"
    (inbox / "note.txt").write_text(content + "\n")

    result = coll.run()

    assert len(result.files_written) == 1
    assert result.errors == ()

    from collectors import capture_collector as cap_mod
    expected_id = cap_mod._capture_id(content)
    out_path = raw_captures / f"capture-{expected_id}.md"
    assert out_path.exists(), f"expected ID-derived filename capture-{expected_id}.md"

    text = out_path.read_text()
    assert "type: capture" in text
    assert "origin: capture-intake" in text
    assert f"capture_id: {expected_id}" in text
    assert "tags: [capture]" in text
    assert "source: note.txt" in text
    assert "captured_at: 20" in text  # ISO-ish, decade-stable
    # Body is the verbatim capture content (no punctuation pass).
    assert content in text


def test_source_is_moved_into_vault_archive_zone(capture_env):
    coll, inbox, raw_captures = capture_env
    (inbox / "drop.md").write_text("ingest then archive me")

    coll.run()

    from collectors import capture_collector as cap_mod
    archive = cap_mod.MOBILE_ARCHIVE_DIR
    assert archive.is_dir()
    assert sorted(p.name for p in archive.iterdir()) == ["drop.md"]
    # Inbox emptied; legacy <inbox>/.processed/ never created.
    assert list(inbox.iterdir()) == []
    assert not (inbox / ".processed").exists()


def test_dotfiles_and_wrong_suffix_are_ignored(capture_env):
    coll, inbox, raw_captures = capture_env
    (inbox / "real.txt").write_text("ingest me")
    (inbox / ".hidden").write_text("dot-file, skip")
    (inbox / "photo.jpg").write_text("wrong suffix, skip")

    result = coll.run()

    assert len(result.files_written) == 1
    leftover = sorted(p.name for p in inbox.iterdir())
    assert leftover == [".hidden", "photo.jpg"]


# ── Re-drop idempotency (the ID-derived-filename invariant) ──────────


def test_redropping_same_content_overwrites_not_duplicates(capture_env):
    coll, inbox, raw_captures = capture_env
    content = "the same cryptic thought, dropped twice"

    (inbox / "first.txt").write_text(content)
    first = coll.run()
    assert len(first.files_written) == 1
    assert len(list(raw_captures.iterdir())) == 1

    # Operator re-drops identical content under a DIFFERENT source filename.
    # Same content → same capture-ID → same article filename → overwrite.
    (inbox / "second.txt").write_text(content)
    second = coll.run()
    assert len(second.files_written) == 1
    # Still exactly one article — the re-drop collapsed onto the same ID.
    assert len(list(raw_captures.iterdir())) == 1


def test_rerun_with_empty_inbox_is_idempotent(capture_env):
    coll, inbox, raw_captures = capture_env
    (inbox / "once.txt").write_text("only here once")

    first = coll.run()
    assert len(first.files_written) == 1

    second = coll.run()
    assert second.files_written == ()
    assert "no new" in second.message


# ── Edge case: empty source file ─────────────────────────────────────


def test_empty_source_file_is_archived_without_ingest(capture_env):
    coll, inbox, raw_captures = capture_env
    (inbox / "empty.txt").write_text("")
    (inbox / "ok.txt").write_text("real content")

    result = coll.run()

    assert len(result.files_written) == 1  # only the non-empty one
    assert any("empty.txt" in e for e in result.errors)
    from collectors import capture_collector as cap_mod
    assert (cap_mod.MOBILE_ARCHIVE_DIR / "empty.txt").exists()
    assert not (inbox / ".processed").exists()


# ── Daily rollup actually lands (KNOWN_SOURCES extended) ─────────────


def test_daily_rollup_line_lands(capture_env, monkeypatch, tmp_path):
    coll, inbox, raw_captures = capture_env
    from core import daily_capture
    daily_dir = tmp_path / "daily"
    monkeypatch.setattr(daily_capture, "DAILY_DIR", daily_dir)

    (inbox / "thought.txt").write_text("a thought worth a rollup line")
    result = coll.run()
    assert len(result.files_written) == 1

    # One captures.md somewhere under daily/<date>/ with a backlink line.
    rollups = list(daily_dir.glob("*/captures.md"))
    assert len(rollups) == 1
    assert "[[capture-" in rollups[0].read_text()


# ── Config + migration wiring ────────────────────────────────────────


def test_config_personal_has_capture_inbox_field():
    from core.config import Personal
    assert hasattr(Personal(), "capture_inbox")
    assert Personal().capture_inbox == ""


def test_migration_injects_capture_inbox():
    from migrations.migrate_config_keys import KEY_ADDITIONS
    assert KEY_ADDITIONS["personal"]["capture_inbox"] == ""
