"""Unit tests for daily_capture — per-source append-only writer for daily/<date>/.

Tests the core invariants:
- ensure_subfolder is idempotent
- append creates file + appends without overwriting
- replace_section overwrites prior content of the same source
- fcntl lock prevents concurrent corruption
- inputs are date-stamped (any source can claim "today")
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core import daily_capture


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Pin DAILY_DIR to tmp_path/daily so tests can't touch the real vault."""
    daily = tmp_path / "daily"
    daily.mkdir()
    monkeypatch.setattr(daily_capture, "DAILY_DIR", daily)
    return tmp_path


# ── ensure_subfolder ────────────────────────────────────────────────


def test_ensure_subfolder_creates_directory(vault):
    out = daily_capture.ensure_subfolder("2026-05-14")
    assert out.is_dir()
    assert out.name == "2026-05-14"
    assert out.parent.name == "daily"


def test_ensure_subfolder_is_idempotent(vault):
    a = daily_capture.ensure_subfolder("2026-05-14")
    b = daily_capture.ensure_subfolder("2026-05-14")
    assert a == b
    assert a.is_dir()


def test_ensure_subfolder_rejects_malformed_date(vault):
    with pytest.raises(ValueError, match="ISO date"):
        daily_capture.ensure_subfolder("2026/05/14")
    with pytest.raises(ValueError, match="ISO date"):
        daily_capture.ensure_subfolder("14-05-2026")
    with pytest.raises(ValueError, match="ISO date"):
        daily_capture.ensure_subfolder("not-a-date")


# ── append ──────────────────────────────────────────────────────────


def test_append_creates_file_with_content(vault):
    daily_capture.append("2026-05-14", "voice", "- coffee shop thought")
    f = vault / "daily" / "2026-05-14" / "voice.md"
    assert f.is_file()
    assert f.read_text() == "- coffee shop thought\n"


def test_append_appends_without_overwriting(vault):
    daily_capture.append("2026-05-14", "voice", "- first")
    daily_capture.append("2026-05-14", "voice", "- second")
    f = vault / "daily" / "2026-05-14" / "voice.md"
    assert f.read_text() == "- first\n- second\n"


def test_append_adds_trailing_newline_if_missing(vault):
    daily_capture.append("2026-05-14", "voice", "no trailing newline")
    f = vault / "daily" / "2026-05-14" / "voice.md"
    assert f.read_text().endswith("\n")


def test_append_preserves_existing_trailing_newline(vault):
    daily_capture.append("2026-05-14", "voice", "line one\n")
    daily_capture.append("2026-05-14", "voice", "line two\n")
    f = vault / "daily" / "2026-05-14" / "voice.md"
    # No double-newline between entries
    assert "\n\n" not in f.read_text()


def test_append_creates_subfolder_implicitly(vault):
    # ensure_subfolder shouldn't need to be called separately
    daily_capture.append("2026-05-14", "voice", "test")
    assert (vault / "daily" / "2026-05-14").is_dir()


def test_append_rejects_unknown_source(vault):
    # source must be in the known set — typo-protection
    with pytest.raises(ValueError, match="unknown source"):
        daily_capture.append("2026-05-14", "voic", "test")  # typo


def test_append_rejects_path_traversal_in_source(vault):
    # source names like "../escape" must be rejected
    with pytest.raises(ValueError):
        daily_capture.append("2026-05-14", "../etc", "test")


# ── replace_section ─────────────────────────────────────────────────


def test_replace_section_creates_file_with_content(vault):
    daily_capture.replace_section("2026-05-14", "health", "sleep: 7.2\nsteps: 8412")
    f = vault / "daily" / "2026-05-14" / "health.md"
    assert f.read_text() == "sleep: 7.2\nsteps: 8412\n"


def test_replace_section_overwrites_existing_content(vault):
    daily_capture.replace_section("2026-05-14", "health", "old content")
    daily_capture.replace_section("2026-05-14", "health", "new content")
    f = vault / "daily" / "2026-05-14" / "health.md"
    assert f.read_text() == "new content\n"


def test_replace_section_independent_of_other_sources(vault):
    daily_capture.append("2026-05-14", "voice", "voice entry")
    daily_capture.replace_section("2026-05-14", "health", "health metrics")
    voice_f = vault / "daily" / "2026-05-14" / "voice.md"
    health_f = vault / "daily" / "2026-05-14" / "health.md"
    assert voice_f.read_text() == "voice entry\n"
    assert health_f.read_text() == "health metrics\n"


# ── known sources contract ──────────────────────────────────────────


def test_known_sources_contains_phase_1_set():
    # Phase 1 wires these five sources; new sources require explicit allow-list extension.
    assert daily_capture.KNOWN_SOURCES >= {"sessions", "health", "meetings", "voice", "email"}


# ── fcntl locking (best-effort smoke test) ──────────────────────────


def test_append_uses_lock(vault, monkeypatch):
    # Smoke check: the helper imports fcntl and calls flock around the file write.
    # We assert by intercepting fcntl.flock and confirming it's called.
    import fcntl
    calls = []
    original = fcntl.flock

    def spy(fd, op):
        calls.append(op)
        return original(fd, op)

    monkeypatch.setattr(fcntl, "flock", spy)
    daily_capture.append("2026-05-14", "voice", "locked write")

    # Expect at least one LOCK_EX and one LOCK_UN
    assert fcntl.LOCK_EX in calls
    assert fcntl.LOCK_UN in calls


# ── today helper ────────────────────────────────────────────────────


def test_today_iso_returns_current_date(vault):
    # daily_capture.today_iso() should mirror date.today().isoformat()
    assert daily_capture.today_iso() == date.today().isoformat()
