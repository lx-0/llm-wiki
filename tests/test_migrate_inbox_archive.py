"""Tests for `scripts/migrations/migrate_inbox_archive.py` (M022-S03-T01).

The migration moves any pre-M022 `<voice_inbox>/.processed/*` and
`<picture_inbox>/.processed/*` into `<vault>/raw/inbox-mobile/<source>/`.
Tests use tmp_path everywhere — no real iCloud / vault files touched.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def fake_vault(tmp_path, monkeypatch):
    """Patch CONFIG.personal.voice_inbox + picture_inbox + paths.RAW_DIR at tmp_path.

    Returns (migrate_module, voice_inbox, picture_inbox, vault_raw).
    The module is reloaded after patches so module-level imports of
    CONFIG / RAW_DIR pick up the patched values.
    """
    voice_inbox = tmp_path / "icloud" / "voice"
    picture_inbox = tmp_path / "icloud" / "pictures"
    vault_raw = tmp_path / "vault" / "raw"
    voice_inbox.mkdir(parents=True)
    picture_inbox.mkdir(parents=True)
    vault_raw.mkdir(parents=True)

    from core.config import CONFIG
    from core import paths as paths_mod

    monkeypatch.setattr(CONFIG.personal, "voice_inbox", str(voice_inbox))
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", str(picture_inbox))
    monkeypatch.setattr(paths_mod, "RAW_DIR", vault_raw)

    from migrations import migrate_inbox_archive as mig
    importlib.reload(mig)

    return mig, voice_inbox, picture_inbox, vault_raw


def test_voice_files_migrate_into_vault_archive(fake_vault):
    mig, voice_inbox, _pic, vault_raw = fake_vault
    legacy = voice_inbox / ".processed"
    legacy.mkdir()
    (legacy / "foo.txt").write_text("transcript A")
    (legacy / "bar.md").write_text("# transcript B")

    mig.main([])

    dest = vault_raw / "inbox-mobile" / "voice"
    assert (dest / "foo.txt").read_text() == "transcript A"
    assert (dest / "bar.md").read_text() == "# transcript B"
    assert not legacy.exists(), "empty .processed/ should be rmdir-ed"


def test_picture_files_migrate_into_vault_archive(fake_vault):
    mig, _voice, picture_inbox, vault_raw = fake_vault
    legacy = picture_inbox / ".processed"
    legacy.mkdir()
    (legacy / "IMG_001.png").write_bytes(b"\x89PNG_fake")
    (legacy / "IMG_001.md").write_text("vision sidecar A")  # per-image sidecar

    mig.main([])

    dest = vault_raw / "inbox-mobile" / "pictures"
    assert (dest / "IMG_001.png").read_bytes() == b"\x89PNG_fake"
    assert (dest / "IMG_001.md").read_text() == "vision sidecar A"
    assert not legacy.exists()


def test_filename_collision_gets_mtime_suffix(fake_vault):
    mig, voice_inbox, _pic, vault_raw = fake_vault
    legacy = voice_inbox / ".processed"
    legacy.mkdir()
    src = legacy / "note.txt"
    src.write_text("legacy version")

    # Pre-existing file in destination forces collision-suffix path
    dest = vault_raw / "inbox-mobile" / "voice"
    dest.mkdir(parents=True)
    (dest / "note.txt").write_text("vault-resident version, keep me")

    mig.main([])

    # Original destination preserved
    assert (dest / "note.txt").read_text() == "vault-resident version, keep me"
    # Migrated file gets mtime-suffix
    collisions = [p for p in dest.iterdir() if p.name.startswith("note-") and p.name.endswith(".txt")]
    assert len(collisions) == 1, f"expected 1 mtime-suffixed file, got {[p.name for p in dest.iterdir()]}"
    assert collisions[0].read_text() == "legacy version"


def test_rerun_is_idempotent(fake_vault):
    mig, voice_inbox, _pic, vault_raw = fake_vault
    legacy = voice_inbox / ".processed"
    legacy.mkdir()
    (legacy / "once.txt").write_text("only migrate once")

    # First run: migrates
    rc = mig.main([])
    assert rc == 0
    dest = vault_raw / "inbox-mobile" / "voice"
    assert (dest / "once.txt").exists()
    assert not legacy.exists()

    # Second run: nothing to do, no error
    rc = mig.main([])
    assert rc == 0
    # Destination unchanged
    assert sorted(p.name for p in dest.iterdir()) == ["once.txt"]


def test_unconfigured_inboxes_are_skipped_gracefully(tmp_path, monkeypatch):
    """No voice_inbox / picture_inbox configured → migration is a no-op, no crash."""
    from core.config import CONFIG
    from core import paths as paths_mod

    monkeypatch.setattr(CONFIG.personal, "voice_inbox", "")
    monkeypatch.setattr(CONFIG.personal, "picture_inbox", "")
    monkeypatch.setattr(paths_mod, "RAW_DIR", tmp_path / "vault" / "raw")

    from migrations import migrate_inbox_archive as mig
    importlib.reload(mig)

    rc = mig.main([])
    assert rc == 0
    # Did NOT create the destination dirs since both sources were skipped
    assert not (tmp_path / "vault" / "raw" / "inbox-mobile").exists()


def test_dry_run_moves_nothing(fake_vault):
    mig, voice_inbox, _pic, vault_raw = fake_vault
    legacy = voice_inbox / ".processed"
    legacy.mkdir()
    (legacy / "stays.txt").write_text("don't touch me")

    mig.main(["--dry-run"])

    # Source untouched
    assert (legacy / "stays.txt").read_text() == "don't touch me"
    # Destination not created
    assert not (vault_raw / "inbox-mobile" / "voice").exists()
