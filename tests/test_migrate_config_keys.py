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
    """Piggyback rename + drop AND missing-limits backfill in one pass."""
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
    # 2 piggyback (rename + drop)
    #  + 1 created-limits-block
    #  + 9 limits additions (compile_force_long_context_types,
    #    compile_skip_on_long_context_unknown, 4 calendar_*,
    #    compile_max_turns_long_context, compile_max_cost_per_file_usd,
    #    compile_skip_substrate_types)
    #  + 1 piggybacks.calendar addition
    # (LIST_ADDITIONS currently empty; LIST_REMOVALS only fires when
    # operator already has the entries to remove, not on greenfield.)
    # = 13 changes (no drops here — operator has no orphan personal.* fields)
    assert len(changes) == 13, f"got {len(changes)} changes: {changes}"

    reparsed = yaml.safe_load(new_text)
    # piggyback side
    assert "screenshots" in reparsed["piggybacks"]
    assert "scan_screenshots" not in reparsed["piggybacks"]
    assert "sync_memories" not in reparsed["piggybacks"]
    assert reparsed["piggybacks"]["lint_structural"] == {"enabled": True, "cooldown_hours": 24}
    # new piggyback injected
    assert reparsed["piggybacks"]["calendar"] == {"enabled": True, "cooldown_hours": 6, "max_per_run": 500}
    # additions side — both are empty defaults since 2026-05-16 P2
    assert reparsed["limits"]["compile_force_long_context_types"] == []
    assert reparsed["limits"]["compile_skip_substrate_types"] == []
    assert reparsed["limits"]["compile_skip_on_long_context_unknown"] is True
    assert reparsed["limits"]["calendar_request_timeout_s"] == 30
    assert reparsed["limits"]["calendar_max_per_run"] == 500
    assert reparsed["limits"]["calendar_backfill_days"] == 90
    assert reparsed["limits"]["calendar_future_days"] == 7
    # unrelated section untouched
    assert reparsed["scheduling"] == {"compile_after_hour": 18}


def test_migrate_config_no_change_when_fully_current(tmp_path):
    """Piggybacks current AND additions already present → no change."""
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump({
        "piggybacks": {
            "email": {"enabled": True, "cooldown_hours": 24},
            "calendar": {"enabled": True, "cooldown_hours": 6, "max_per_run": 500},
        },
        "limits": {
            "compile_force_long_context_types": [],
            "compile_skip_on_long_context_unknown": True,
            "calendar_request_timeout_s": 30,
            "calendar_max_per_run": 500,
            "calendar_backfill_days": 90,
            "calendar_future_days": 7,
            "compile_max_turns_long_context": 30,
            "compile_max_cost_per_file_usd": 2.5,
            "compile_skip_substrate_types": [],
        },
    }), encoding="utf-8")

    new_text, changes = m.migrate_config(config_path)
    assert new_text is None
    assert changes == []


def test_migrate_config_missing_file(tmp_path):
    m = _mod()
    new_text, changes = m.migrate_config(tmp_path / "nonexistent" / "config.yaml")
    assert new_text is None
    assert changes == []


def test_migrate_config_no_piggybacks_block_still_runs_additions(tmp_path):
    """Configs without piggybacks should still receive new-key additions."""
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump({"scheduling": {"compile_after_hour": 18}}), encoding="utf-8")

    new_text, changes = m.migrate_config(config_path)
    assert new_text is not None
    reparsed = yaml.safe_load(new_text)
    assert reparsed["limits"]["compile_force_long_context_types"] == []
    assert reparsed["limits"]["compile_skip_on_long_context_unknown"] is True
    assert reparsed["scheduling"] == {"compile_after_hour": 18}


# ── migrate_additions: key backfill logic ───────────────────────────


def test_migrate_additions_creates_missing_parent_block():
    """migrate_additions only injects MISSING keys with their defaults."""
    m = _mod()
    data: dict = {}
    changes = m.migrate_additions(data)
    assert "limits" in data
    # Default for force-long-context is empty since 2026-05-16 P2.
    assert data["limits"]["compile_force_long_context_types"] == []
    assert data["limits"]["compile_skip_on_long_context_unknown"] is True
    assert any("created empty limits" in c for c in changes)
    assert any("added limits.compile_force_long_context_types" in c for c in changes)


def test_migrate_additions_preserves_existing_values():
    """Operator already set the key — leave it, don't clobber."""
    m = _mod()
    data: dict = {
        "limits": {
            "compile_force_long_context_types": ["daily-digest", "meeting-rollup"],  # operator override
            "compile_max_turns": 30,  # unrelated existing key
        },
    }
    m.migrate_additions(data)
    # operator value untouched
    assert data["limits"]["compile_force_long_context_types"] == ["daily-digest", "meeting-rollup"]
    # missing key still backfilled
    assert data["limits"]["compile_skip_on_long_context_unknown"] is True
    # unrelated key preserved
    assert data["limits"]["compile_max_turns"] == 30


def test_migrate_additions_skips_non_dict_parent():
    """Operator has something non-dict under the limits parent — don't clobber."""
    m = _mod()
    data: dict = {"limits": "broken"}
    m.migrate_additions(data)
    # limits stays as the operator's broken value (don't clobber)
    assert data["limits"] == "broken"


def test_migrate_additions_idempotent():
    m = _mod()
    data: dict = {
        "limits": {
            "compile_force_long_context_types": ["daily-digest", "calendar-rollup"],
            "compile_skip_on_long_context_unknown": True,
            "calendar_request_timeout_s": 30,
            "calendar_max_per_run": 500,
            "calendar_backfill_days": 90,
            "calendar_future_days": 7,
            "compile_max_turns_long_context": 30,
            "compile_max_cost_per_file_usd": 2.5,
            "compile_skip_substrate_types": ["calendar-rollup"],
        },
        "piggybacks": {
            "calendar": {"enabled": True, "cooldown_hours": 6, "max_per_run": 500},
        },
    }
    changes = m.migrate_additions(data)
    assert changes == []


def test_migrate_additions_adds_calendar_block_when_absent():
    """M006: limits.calendar_* + piggybacks.calendar must be injected."""
    m = _mod()
    data: dict = {}
    m.migrate_additions(data)
    assert data["limits"]["calendar_request_timeout_s"] == 30
    assert data["limits"]["calendar_max_per_run"] == 500
    assert data["limits"]["calendar_backfill_days"] == 90
    assert data["limits"]["calendar_future_days"] == 7
    assert data["piggybacks"]["calendar"] == {
        "enabled": True,
        "cooldown_hours": 6,
        "max_per_run": 500,
    }


def test_migrate_list_removals_prunes_legacy_substrate_entries():
    """2026-05-16 P2 cleanup: operator configs from the P1 hotfix window
    had calendar-rollup in skip-list and force-long-context-types; both
    move out when dedicated lean prompts ship."""
    m = _mod()
    data: dict = {
        "limits": {
            "compile_force_long_context_types": ["daily-digest", "calendar-rollup", "custom-type"],
            "compile_skip_substrate_types": ["calendar-rollup", "operator-custom"],
        },
    }
    changes = m.migrate_list_removals(data)
    # Both legacy entries pruned; operator-custom entries preserved.
    assert data["limits"]["compile_force_long_context_types"] == ["custom-type"]
    assert data["limits"]["compile_skip_substrate_types"] == ["operator-custom"]
    assert any("removed 'calendar-rollup' from limits.compile_force_long_context_types" in c for c in changes)
    assert any("removed 'daily-digest' from limits.compile_force_long_context_types" in c for c in changes)
    assert any("removed 'calendar-rollup' from limits.compile_skip_substrate_types" in c for c in changes)


def test_migrate_list_removals_idempotent():
    """Re-running on already-pruned config produces no changes."""
    m = _mod()
    data: dict = {
        "limits": {
            "compile_force_long_context_types": [],
            "compile_skip_substrate_types": [],
        },
    }
    changes = m.migrate_list_removals(data)
    assert changes == []


def test_migrate_additions_preserves_existing_calendar_piggyback():
    """Operator-tweaked calendar cooldown is not clobbered."""
    m = _mod()
    data: dict = {
        "piggybacks": {
            "calendar": {"enabled": True, "cooldown_hours": 12, "max_per_run": 100},
        },
    }
    m.migrate_additions(data)
    assert data["piggybacks"]["calendar"] == {
        "enabled": True, "cooldown_hours": 12, "max_per_run": 100,
    }


# ── migrate_drops: orphan-field pruning ─────────────────────────────


def test_migrate_drops_removes_orphan_personal_calendar_fields():
    """M006: scan_calendar legacy fields no longer exist on dataclass; prune."""
    m = _mod()
    data: dict = {
        "personal": {
            "primary_account": "work",
            "calendar_skip_keywords": ["Weihnacht"],       # KEPT
            "calendar_work_keywords": ["Customer X"],       # DROP
            "calendar_categories": {"Health": ["doctor"]},  # DROP
            "calendar_report_language": "de",               # DROP
        },
    }
    changes = m.migrate_drops(data)
    assert "calendar_skip_keywords" in data["personal"]  # kept
    assert "calendar_work_keywords" not in data["personal"]
    assert "calendar_categories" not in data["personal"]
    assert "calendar_report_language" not in data["personal"]
    assert "primary_account" in data["personal"]  # unrelated
    assert len(changes) == 3
    assert all("dropped orphan personal." in c for c in changes)


def test_migrate_drops_idempotent_when_clean():
    m = _mod()
    data: dict = {"personal": {"primary_account": "work", "calendar_skip_keywords": []}}
    changes = m.migrate_drops(data)
    assert changes == []
    assert data == {"personal": {"primary_account": "work", "calendar_skip_keywords": []}}


def test_migrate_drops_handles_missing_parent():
    m = _mod()
    data: dict = {}
    changes = m.migrate_drops(data)
    assert changes == []
    assert data == {}


def test_migrate_drops_handles_non_dict_parent():
    m = _mod()
    data: dict = {"personal": "broken"}
    changes = m.migrate_drops(data)
    assert changes == []
    assert data == {"personal": "broken"}


def test_migrate_config_round_trip_with_drops(tmp_path):
    """Full round-trip: operator config with legacy personal.calendar_* keys
    gets them pruned, AND gets the new limits.calendar_* keys + piggybacks.calendar
    injected. Demonstrates the M006 migration end-to-end."""
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump({
        "personal": {
            "primary_account": "work",
            "calendar_skip_keywords": ["Weihnacht"],
            "calendar_categories": {"Health": ["doctor"]},
            "calendar_work_keywords": ["Customer X"],
            "calendar_report_language": "de",
        },
        "piggybacks": {"email": {"enabled": True, "cooldown_hours": 24}},
    }), encoding="utf-8")

    new_text, changes = m.migrate_config(config_path)
    assert new_text is not None
    reparsed = yaml.safe_load(new_text)

    # orphans pruned
    assert "calendar_work_keywords" not in reparsed["personal"]
    assert "calendar_categories" not in reparsed["personal"]
    assert "calendar_report_language" not in reparsed["personal"]
    # kept field survives
    assert reparsed["personal"]["calendar_skip_keywords"] == ["Weihnacht"]
    assert reparsed["personal"]["primary_account"] == "work"
    # M006 additions landed
    assert reparsed["limits"]["calendar_request_timeout_s"] == 30
    assert reparsed["piggybacks"]["calendar"]["cooldown_hours"] == 6
    # unrelated piggyback untouched
    assert reparsed["piggybacks"]["email"] == {"enabled": True, "cooldown_hours": 24}
