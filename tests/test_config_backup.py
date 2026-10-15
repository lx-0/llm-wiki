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


def test_backup_round_robin_keeps_last_n(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_backup_first_write_no_op(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No file to back up = no-op (no error, no empty file)."""
    cfg_file = tmp_path / "config.yaml"  # doesn't exist yet

    from core import config

    monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
    config._set_in_yaml("scheduling.compile_after_hour", 18)

    backup_dir = tmp_path / "state" / "config-backups"
    if backup_dir.exists():
        assert list(backup_dir.glob("*")) == []


def test_round_robin_keeps_the_newest_within_one_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pruning goes by name, so name order must be time order. Within one second the
    names gained a micro-suffix only from the second backup on, and `config-T-<µs>.yaml`
    sorts BEFORE `config-T.yaml` ('-' < '.'): the prune deleted newer snapshots and kept
    the oldest (seen in the setup wizard, which writes several keys in one second)."""
    from datetime import UTC, datetime

    from core import config_backup

    ticks = iter(range(1, 1000))

    class _OneSecond(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 15, 16, 35, 23, next(ticks), tzinfo=UTC)

    monkeypatch.setattr(config_backup, "datetime", _OneSecond)
    cfg = tmp_path / "config.yaml"
    for value in range(4):
        cfg.write_text(f"v: {value}\n", encoding="utf-8")
        config_backup.backup_config_file(cfg, keep_last=2)

    kept = sorted(config_backup.backup_dir_for(cfg).glob("config-*.yaml"))
    assert [p.read_text(encoding="utf-8") for p in kept] == ["v: 2\n", "v: 3\n"]
