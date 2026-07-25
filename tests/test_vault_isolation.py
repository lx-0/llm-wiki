"""The guard that keeps test writes inside the checkout must itself be live.

Without these, `tests/_vault_isolation.py` is a plausible-looking no-op: the
patching happens in `pytest_configure`, so nothing else in the suite would
notice if it silently stopped applying.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from core import daily_capture
from core.paths import ROOT_DIR, WIKI_DIR

from ._vault_isolation import VaultWriteEscape, _escapee


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
