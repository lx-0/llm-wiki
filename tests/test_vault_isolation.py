"""The guard that keeps test writes inside the checkout must itself be live.

Without these, `tests/_vault_isolation.py` is a plausible-looking no-op: the
patching happens in `pytest_configure`, so nothing else in the suite would
notice if it silently stopped applying.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core import daily_capture
from core.paths import ROOT_DIR, WIKI_DIR

from ._vault_isolation import VaultWriteEscape, _escapee, changed_neighbours, neighbours


def test_path_next_to_the_checkout_is_flagged():
    assert _escapee(ROOT_DIR / "daily" / "2026-07-25" / "voice.md") is not None


def test_path_inside_the_checkout_is_allowed():
    assert _escapee(WIKI_DIR / "scripts" / "core" / "paths.py") is None


def test_write_outside_the_checkout_raises(tmp_path):
    probe = ROOT_DIR / "vault-isolation-probe.md"
    with pytest.raises(VaultWriteEscape):
        probe.write_text("should never reach the filesystem", encoding="utf-8")
    with pytest.raises(VaultWriteEscape):
        (ROOT_DIR / "vault-isolation-probe-dir").mkdir()
    assert not probe.exists()
    # A write inside the checkout's tmp area still works.
    (tmp_path / "ok.md").write_text("fine", encoding="utf-8")


def test_daily_dir_is_repointed_into_the_tmp_sink():
    assert "vault-sink" in Path(daily_capture.DAILY_DIR).parts


def test_the_session_sees_what_a_child_process_wrote_next_to_the_checkout(tmp_path):
    """The session guard compares the checkout's neighbours (conftest's sessionfinish): a new
    entry and a rewritten file count; the checkout itself, a sibling repository and Finder's
    `.DS_Store` do not."""
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (tmp_path / "sibling" / ".git").mkdir(parents=True)
    old = tmp_path / "_dashboard-stats.md"
    old.write_text("x", encoding="utf-8")
    before = neighbours(tmp_path, checkout)

    (tmp_path / ".obsidian").mkdir()
    os.utime(old, ns=(before[old.name], before[old.name] + 10**9))
    (checkout / "inside.md").write_text("fine", encoding="utf-8")
    (tmp_path / "sibling" / "work.md").write_text("theirs", encoding="utf-8")
    (tmp_path / ".DS_Store").write_text("finder", encoding="utf-8")

    assert changed_neighbours(before, neighbours(tmp_path, checkout)) == [
        ".obsidian",
        "_dashboard-stats.md",
    ]
