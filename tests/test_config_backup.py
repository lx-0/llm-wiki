"""Round-robin config backup — every save snapshots the prior state."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_backup_created_on_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting a key snapshots the prior config to state/config-backups/."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "scheduling:\n  compile_after_hour: 17\n",
        encoding="utf-8",
    )

    from core import config

    monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
    config._set_in_yaml("scheduling.compile_after_hour", 18)

    backup_dir = tmp_path / "state" / "config-backups"
    assert backup_dir.exists()
    backups = sorted(backup_dir.glob("config-*.yaml"))
    assert len(backups) == 1
    snapshot = backups[0].read_text(encoding="utf-8")
    assert "compile_after_hour: 17" in snapshot  # prior value preserved


def test_backup_round_robin_keeps_last_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After more than _CONFIG_BACKUP_KEEP_LAST writes, oldest are pruned."""
    import time

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("scheduling:\n  compile_after_hour: 0\n", encoding="utf-8")

    from core import config

    monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(config, "_CONFIG_BACKUP_KEEP_LAST", 3)

    for i in range(5):
        config._set_in_yaml("scheduling.compile_after_hour", i)
        time.sleep(0.001)

    backup_dir = tmp_path / "state" / "config-backups"
    backups = sorted(backup_dir.glob("config-*.yaml"))
    assert len(backups) == 3, f"expected 3 backups, got {len(backups)}"


def test_backup_first_write_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No file to back up = no-op (no error, no empty file)."""
    cfg_file = tmp_path / "config.yaml"  # doesn't exist yet

    from core import config

    monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
    config._set_in_yaml("scheduling.compile_after_hour", 18)

    backup_dir = tmp_path / "state" / "config-backups"
    if backup_dir.exists():
        assert list(backup_dir.glob("*")) == []
