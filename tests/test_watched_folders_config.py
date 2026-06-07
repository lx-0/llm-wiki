"""personal.watched_folders config schema + migration (M027-S01-T01).

Validation-only: these tests cover the schema shape and the migration
injection. Nothing scans the filesystem yet (that's S02).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_watched_folders_in_key_additions():
    """`wiki update` injects personal.watched_folders: [] into operator vaults."""
    from migrations.migrate_config_keys import KEY_ADDITIONS

    assert KEY_ADDITIONS["personal"]["watched_folders"] == []


def test_validate_accepts_valid_local_and_smb():
    from core.config import _validate_watched_folders_schema

    _validate_watched_folders_schema(
        {
            "watched_folders": [
                {"id": "docs", "kind": "local", "path": "~/Sync/Private/Documents"},
                {"id": "nas", "kind": "smb", "share": "Multimedia"},
            ]
        }
    )  # must not raise


def test_validate_empty_or_missing_is_ok():
    from core.config import _validate_watched_folders_schema

    _validate_watched_folders_schema({})
    _validate_watched_folders_schema({"watched_folders": []})


def test_validate_rejects_unknown_kind():
    from core.config import ConfigError, _validate_watched_folders_schema

    with pytest.raises(ConfigError) as exc:
        _validate_watched_folders_schema(
            {"watched_folders": [{"id": "x", "kind": "bogus", "path": "/p"}]}
        )
    assert "x" in str(exc.value)


def test_validate_local_requires_path():
    from core.config import ConfigError, _validate_watched_folders_schema

    with pytest.raises(ConfigError):
        _validate_watched_folders_schema({"watched_folders": [{"id": "x", "kind": "local"}]})


def test_validate_smb_requires_share():
    from core.config import ConfigError, _validate_watched_folders_schema

    with pytest.raises(ConfigError):
        _validate_watched_folders_schema({"watched_folders": [{"id": "x", "kind": "smb"}]})


def test_validate_requires_id():
    from core.config import ConfigError, _validate_watched_folders_schema

    with pytest.raises(ConfigError):
        _validate_watched_folders_schema(
            {"watched_folders": [{"kind": "local", "path": "/p"}]}
        )


# ── load() wiring: the validator actually fires through config.load() ──
# (mirrors test_s02_adapters.py's _validate_accounts_schema wiring tests;
#  guards against the validator being defined but never called.)


def test_load_rejects_bad_watched_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from core import config

    bad = tmp_path / "config.yaml"
    bad.write_text(
        "personal:\n"
        "  watched_folders:\n"
        "    - id: x\n"
        "      kind: bogus\n"
        "      path: /p\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_FILE", bad)
    with pytest.raises(config.ConfigError) as exc:
        config.load()
    assert "watched_folders" in str(exc.value)


def test_load_accepts_valid_watched_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from core import config

    good = tmp_path / "config.yaml"
    good.write_text(
        "personal:\n"
        "  watched_folders:\n"
        "    - id: docs\n"
        "      kind: local\n"
        "      path: ~/Sync/Private\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_FILE", good)
    cfg = config.load()
    assert cfg.personal.watched_folders == [
        {"id": "docs", "kind": "local", "path": "~/Sync/Private"}
    ]
