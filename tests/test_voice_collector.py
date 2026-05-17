"""Tests for the voice collector (collectors/voice.py).

Covers the four operator-facing invariants of the durchstich:

- **Graceful agnostic**: empty / missing `voice_inbox` → `is_configured()`
  False, `run()` returns a clear message, no error.
- **Dry-run**: counts files, writes nothing, leaves inbox untouched.
- **Real run**: writes `raw/voice/voice-YYYY-MM-DD-HHMM-<slug>.md` with
  the expected frontmatter, archives sources under `.processed/`,
  ignores dot-files and wrong-suffix files.
- **Idempotent re-run**: after one run, a second run finds nothing
  (archive move is the dedup mechanism, no state file).

Plus the two non-obvious edge cases:

- **Empty source file** → archived without writing a raw note.
- **Slug collision in the same minute** → second file gets a seconds
  suffix appended (no clobber).

All tests use a tmpdir vault; CONFIG + RAW_DIR are monkey-patched so
the real vault is never touched.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def voice_env(tmp_path, monkeypatch):
    """Tmpdir inbox + tmpdir vault, with CONFIG and RAW_DIR pointed at them.

    Returns (collector, inbox, raw_voice_dir). The collector module is
    reloaded each test so it picks up the patched RAW_DIR constant at
    import time.
    """
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    vault_raw = tmp_path / "vault" / "raw"
    vault_raw.mkdir(parents=True)

    from core.config import CONFIG
    from core import paths as paths_mod

    monkeypatch.setattr(CONFIG.personal, "voice_inbox", str(inbox))
    monkeypatch.setattr(paths_mod, "RAW_DIR", vault_raw)
    # Disable the LLM punctuation pre-process for these tests so they
    # don't depend on a reachable Ollama. Frontmatter/body assertions
    # below were written against the raw-passthrough shape.
    monkeypatch.setattr(CONFIG.features, "voice_punctuate", False)

    from collectors import voice as voice_mod
    importlib.reload(voice_mod)

    return voice_mod.VoiceCollector(), inbox, vault_raw / "voice"


# ── Graceful agnostic ────────────────────────────────────────────────


def test_unconfigured_inbox_is_graceful(monkeypatch):
    from core.config import CONFIG
    from collectors import voice as voice_mod
    importlib.reload(voice_mod)

    monkeypatch.setattr(CONFIG.personal, "voice_inbox", "")
    coll = voice_mod.VoiceCollector()
    assert coll.is_configured() is False
    result = coll.run()
    assert result.files_written == ()
    assert "not configured" in result.message


def test_missing_inbox_path_is_graceful(monkeypatch, tmp_path):
    from core.config import CONFIG
    from collectors import voice as voice_mod
    importlib.reload(voice_mod)

    monkeypatch.setattr(CONFIG.personal, "voice_inbox", str(tmp_path / "does-not-exist"))
    coll = voice_mod.VoiceCollector()
    assert coll.is_configured() is False
    result = coll.run()
    assert "not found" in result.message


# ── Dry-run ──────────────────────────────────────────────────────────


def test_dry_run_counts_without_writing(voice_env):
    coll, inbox, raw_voice = voice_env
    (inbox / "a.txt").write_text("eine notiz")
    (inbox / "b.md").write_text("# noch eine")

    result = coll.run(dry_run=True)

    assert result.files_written == ()
    assert result.files_skipped == 2
    assert "dry-run" in result.message
    # Inbox untouched
    assert sorted(p.name for p in inbox.iterdir()) == ["a.txt", "b.md"]
    # Output dir not even created
    assert not raw_voice.exists()


# ── Real run: ingest, frontmatter, archive, ignore rules ─────────────


def test_real_run_writes_frontmatter_and_archives_sources(voice_env):
    coll, inbox, raw_voice = voice_env
    (inbox / "note-a.txt").write_text("Erste voice notiz, geht in raw/voice.\n")
    (inbox / "note-b.md").write_text("# B\n\nzweite notiz\n")

    result = coll.run()

    assert len(result.files_written) == 2
    assert result.errors == ()

    out = sorted(raw_voice.iterdir())
    assert all(p.name.startswith("voice-") and p.suffix == ".md" for p in out)

    content_a = out[0].read_text()
    assert "type: voice-note" in content_a
    assert "origin: voice-intake" in content_a
    assert "tags: [voice]" in content_a
    assert "source: note-" in content_a
    assert "captured_at: 20" in content_a  # ISO-ish, decade-stable

    # Sources moved into .processed/
    archive = inbox / ".processed"
    assert archive.is_dir()
    assert sorted(p.name for p in archive.iterdir()) == ["note-a.txt", "note-b.md"]
    # Inbox root only contains the archive folder now
    assert [p.name for p in inbox.iterdir() if not p.name.startswith(".")] == []


def test_dotfiles_and_wrong_suffix_are_ignored(voice_env):
    coll, inbox, raw_voice = voice_env
    (inbox / "real.txt").write_text("ingest me")
    (inbox / ".hidden").write_text("dot-file, skip")
    (inbox / "photo.jpg").write_text("wrong suffix, skip")

    result = coll.run()

    assert len(result.files_written) == 1
    # Ignored files stay in the inbox root, untouched
    leftover = sorted(p.name for p in inbox.iterdir() if not p.name == ".processed")
    assert leftover == [".hidden", "photo.jpg"]


# ── Idempotent re-run ────────────────────────────────────────────────


def test_rerun_is_idempotent(voice_env):
    coll, inbox, raw_voice = voice_env
    (inbox / "once.txt").write_text("only ingest me once")

    first = coll.run()
    assert len(first.files_written) == 1

    second = coll.run()
    assert second.files_written == ()
    assert "no new" in second.message


# ── Edge cases ───────────────────────────────────────────────────────


def test_empty_source_file_is_archived_without_ingest(voice_env):
    coll, inbox, raw_voice = voice_env
    (inbox / "empty.txt").write_text("")
    (inbox / "ok.txt").write_text("real content")

    result = coll.run()

    assert len(result.files_written) == 1  # only the non-empty one
    assert any("empty.txt" in e for e in result.errors)
    # Empty file still archived so re-runs don't keep retrying
    assert (inbox / ".processed" / "empty.txt").exists()


def test_same_minute_slug_collision_gets_seconds_suffix(voice_env, monkeypatch):
    coll, inbox, raw_voice = voice_env
    # Two files with identical first-six-word slug, written to the same minute
    (inbox / "first.txt").write_text("die gleiche slug erste sechs woerter")
    (inbox / "second.txt").write_text("die gleiche slug erste sechs woerter")
    # Force same mtime so the slug-base is identical
    import os
    fixed_ts = 1747341792  # 2026-05-15T17:23:12 UTC, arbitrary stable value
    os.utime(inbox / "first.txt", (fixed_ts, fixed_ts))
    os.utime(inbox / "second.txt", (fixed_ts, fixed_ts))

    result = coll.run()

    assert len(result.files_written) == 2
    names = sorted(p.name for p in raw_voice.iterdir())
    # First file: voice-YYYY-MM-DD-HHMM-<slug>.md
    # Second file: voice-YYYY-MM-DD-HHMM-<slug>-<SS>.md
    assert names[0] != names[1]
    assert any("-12.md" in n for n in names)  # seconds suffix from fixed_ts
