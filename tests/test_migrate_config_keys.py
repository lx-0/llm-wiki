"""Tests for the config-key migration (scripts/migrations/migrate_config_keys.py)."""

from __future__ import annotations

from pathlib import Path

import yaml


def _mod():
    from migrations import migrate_config_keys as m
    return m


# ── migrate_piggybacks: pure rename/drop logic ──────────────────────


def test_renames_scan_screenshots_preserving_value():
    m = _mod()
    src = {"scan_screenshots": {"enabled": True, "cooldown_hours": 12, "max_per_run": 30}}
    out, changes = m.migrate_piggybacks(src)
    assert "scan_screenshots" not in out
    assert out["screenshots"] == {"enabled": True, "cooldown_hours": 12, "max_per_run": 30}
    assert any("scan_screenshots → piggybacks.screenshots" in c for c in changes)


def test_renames_follow_requests():
    m = _mod()
    src = {"follow_requests": {"enabled": True, "cooldown_hours": 24}}
    out, changes = m.migrate_piggybacks(src)
    assert "follow_requests" not in out
    assert out["curiosity_followup"] == {"enabled": True, "cooldown_hours": 24}


def test_renames_email_incremental():
    m = _mod()
    src = {"email_incremental": {"enabled": False, "cooldown_hours": 48}}
    out, changes = m.migrate_piggybacks(src)
    assert "email_incremental" not in out
    assert out["email"] == {"enabled": False, "cooldown_hours": 48}


def test_drops_sync_memories():
    m = _mod()
    src = {"sync_memories": {"enabled": False, "cooldown_hours": 24}}
    out, changes = m.migrate_piggybacks(src)
    assert "sync_memories" not in out
    assert any("dropped piggybacks.sync_memories" in c for c in changes)


def test_drops_stale_key_when_new_key_already_present():
    """Old + new both present → new wins, old discarded as cruft."""
    m = _mod()
    src = {
        "scan_screenshots": {"enabled": True, "cooldown_hours": 99},
        "screenshots": {"enabled": False, "cooldown_hours": 24},
    }
    out, changes = m.migrate_piggybacks(src)
    assert out["screenshots"] == {"enabled": False, "cooldown_hours": 24}  # new wins
    assert "scan_screenshots" not in out
    assert any("dropped stale piggybacks.scan_screenshots" in c for c in changes)


def test_idempotent_on_current_schema():
    m = _mod()
    src = {
        "email": {"enabled": True, "cooldown_hours": 24},
        "screenshots": {"enabled": True, "cooldown_hours": 24},
        "curiosity_followup": {"enabled": True, "cooldown_hours": 24},
    }
    out, changes = m.migrate_piggybacks(src)
    assert out == src
    assert changes == []


def test_preserves_unrelated_keys():
    m = _mod()
    src = {
        "scan_screenshots": {"enabled": True, "cooldown_hours": 24},
        "lint_structural": {"enabled": True, "cooldown_hours": 24},
        "review_wiki": {"enabled": True, "cooldown_hours": 168},
    }
    out, changes = m.migrate_piggybacks(src)
    assert out["lint_structural"] == {"enabled": True, "cooldown_hours": 24}
    assert out["review_wiki"] == {"enabled": True, "cooldown_hours": 168}
    assert "screenshots" in out


# ── migrate_config: file-level round-trip ───────────────────────────


def test_migrate_config_file_round_trip(tmp_path):
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump({
        "scheduling": {"compile_after_hour": 18},
        "piggybacks": {
            "scan_screenshots": {"enabled": True, "cooldown_hours": 24},
            "sync_memories": {"enabled": False, "cooldown_hours": 24},
            "lint_structural": {"enabled": True, "cooldown_hours": 24},
        },
    }), encoding="utf-8")

    new_text, changes = m.migrate_config(config_path)
    assert new_text is not None
    assert len(changes) == 2  # rename + drop

    reparsed = yaml.safe_load(new_text)
    assert "screenshots" in reparsed["piggybacks"]
    assert "scan_screenshots" not in reparsed["piggybacks"]
    assert "sync_memories" not in reparsed["piggybacks"]
    assert reparsed["piggybacks"]["lint_structural"] == {"enabled": True, "cooldown_hours": 24}
    # unrelated section untouched
    assert reparsed["scheduling"] == {"compile_after_hour": 18}


def test_migrate_config_no_change_returns_none(tmp_path):
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump({
        "piggybacks": {"email": {"enabled": True, "cooldown_hours": 24}},
    }), encoding="utf-8")

    new_text, changes = m.migrate_config(config_path)
    assert new_text is None
    assert changes == []


def test_migrate_config_missing_file(tmp_path):
    m = _mod()
    new_text, changes = m.migrate_config(tmp_path / "nonexistent" / "config.yaml")
    assert new_text is None
    assert changes == []


def test_migrate_config_no_piggybacks_block(tmp_path):
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump({"scheduling": {"compile_after_hour": 18}}), encoding="utf-8")

    new_text, changes = m.migrate_config(config_path)
    assert new_text is None
    assert changes == []
