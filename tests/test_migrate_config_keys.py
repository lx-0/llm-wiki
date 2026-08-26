"""Tests for the config-key migration (scripts/migrations/migrate_config_keys.py).

The policy/drift tests at the bottom mechanically enforce the CLAUDE.md hard
rule ("config-knob changes are not done until the vault is migrated"): adding
a knob to `core.config_schema` without an explicit INJECTED_KEYS /
NEVER_INJECTED entry fails the suite.
"""

from __future__ import annotations

import copy
from dataclasses import fields

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


def test_force_disables_optimize_claude_md_keeping_block():
    """Engine policy 2026-06-13: optimize_claude_md is the only piggyback that
    writes OUTSIDE the vault (autonomously LLM-rewrites the operator's global
    ~/.claude/CLAUDE.md). It's force-disabled. The block is kept (visible +
    re-enable-able), only `enabled` flips true→false; other fields preserved."""
    m = _mod()
    src = {"optimize_claude_md": {"enabled": True, "cooldown_hours": 24}}
    out, changes = m.migrate_piggybacks(src)
    assert out["optimize_claude_md"]["enabled"] is False
    assert out["optimize_claude_md"]["cooldown_hours"] == 24
    assert any("optimize_claude_md" in c and "disabled" in c.lower() for c in changes)


def test_force_disable_idempotent_when_already_false():
    m = _mod()
    src = {"optimize_claude_md": {"enabled": False, "cooldown_hours": 24}}
    out, changes = m.migrate_piggybacks(src)
    assert changes == []
    assert out["optimize_claude_md"]["enabled"] is False


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
    # No hand-counted change total here: KEY_ADDITIONS is derived from the
    # schema, so the greenfield injection count changes with every new knob.
    # What matters is behavior (below) + convergence: a second run on the
    # migrated output must be a no-op.
    config_path.write_text(new_text, encoding="utf-8")
    second_text, second_changes = m.migrate_config(config_path)
    assert second_text is None, f"migration did not converge: {second_changes}"

    reparsed = yaml.safe_load(new_text)
    # piggyback side
    assert "screenshots" in reparsed["piggybacks"]
    assert "scan_screenshots" not in reparsed["piggybacks"]
    assert "sync_memories" not in reparsed["piggybacks"]
    assert reparsed["piggybacks"]["lint_structural"] == {"enabled": True, "cooldown_hours": 24}
    # new piggyback injected — no max_per_run: dead on registry collectors
    # (the live cap is limits.calendar_max_per_run / per-account sub-block)
    assert reparsed["piggybacks"]["calendar"] == {"enabled": True, "cooldown_hours": 6}
    # additions side — skip-substrate-types has email-delta from
    # KEY_ADDITIONS default (2026-05-16-evening) + folder-index
    # (2026-06-10 M027-S02-T03). The dead compile_force_long_context_types
    # knob is no longer injected (removed 2026-07-18 C13).
    assert "compile_force_long_context_types" not in reparsed["limits"]
    assert "compile_max_turns_long_context" not in reparsed["limits"]
    assert reparsed["limits"]["compile_skip_substrate_types"] == [
        "email-delta",
        "folder-index",
    ]
    assert reparsed["limits"]["compile_skip_on_long_context_unknown"] is True
    assert reparsed["limits"]["calendar_request_timeout_s"] == 30
    assert reparsed["limits"]["calendar_max_per_run"] == 500
    assert reparsed["limits"]["calendar_backfill_days"] == 90
    assert reparsed["limits"]["calendar_future_days"] == 7
    # scheduling block: operator's value preserved; M014 dream_cooldown_days added
    assert reparsed["scheduling"]["compile_after_hour"] == 18
    assert reparsed["scheduling"]["dream_cooldown_days"] == 7


def test_migrate_config_no_change_when_fully_current(tmp_path):
    """A config carrying every injected key at its engine default is a no-op.

    The fixture is DERIVED from the migration's own KEY_ADDITIONS (whose
    values come from core.config_schema) instead of a hand-enumerated copy of
    every default — so it can never drift from the schema, and a KEY_ADDITION
    whose injected value the migration itself would then rewrite (rename /
    list-prune / value-upgrade conflict) fails as a non-convergence.
    """
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    fully_current = copy.deepcopy(m.KEY_ADDITIONS)
    config_path.write_text(yaml.safe_dump(fully_current), encoding="utf-8")

    new_text, changes = m.migrate_config(config_path)
    assert new_text is None, f"unexpected migration: {changes}"
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
    assert reparsed["limits"]["compile_skip_on_long_context_unknown"] is True
    # Dead compile_force_long_context_types knob is no longer injected (C13).
    assert "compile_force_long_context_types" not in reparsed["limits"]
    # M014 also injects scheduling.dream_cooldown_days under the existing
    # scheduling block — operator's compile_after_hour stays untouched.
    assert reparsed["scheduling"]["compile_after_hour"] == 18
    assert reparsed["scheduling"]["dream_cooldown_days"] == 7


# ── migrate_additions: key backfill logic ───────────────────────────


def test_migrate_additions_creates_missing_parent_block():
    """migrate_additions only injects MISSING keys with their defaults."""
    m = _mod()
    data: dict = {}
    changes = m.migrate_additions(data)
    assert "limits" in data
    assert data["limits"]["compile_skip_on_long_context_unknown"] is True
    assert any("created empty limits" in c for c in changes)
    assert any("added limits.compile_skip_on_long_context_unknown" in c for c in changes)


def test_migrate_additions_preserves_existing_values():
    """Operator already set the key — leave it, don't clobber."""
    m = _mod()
    data: dict = {
        "limits": {
            "compile_skip_substrate_types": ["email-delta", "operator-custom"],  # operator override
            "compile_max_turns": 30,  # unrelated existing key
        },
    }
    m.migrate_additions(data)
    # operator value untouched (migrate_additions only injects MISSING keys)
    assert data["limits"]["compile_skip_substrate_types"] == ["email-delta", "operator-custom"]
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
    """Derived fixture: a config that already carries every KEY_ADDITIONS
    entry (at any value) receives no further additions."""
    m = _mod()
    data = copy.deepcopy(m.KEY_ADDITIONS)
    changes = m.migrate_additions(data)
    assert changes == [], f"expected idempotent, got changes: {changes}"


def test_migrate_additions_adds_calendar_block_when_absent():
    """M006: limits.calendar_* + piggybacks.calendar must be injected."""
    m = _mod()
    data: dict = {}
    m.migrate_additions(data)
    assert data["limits"]["calendar_request_timeout_s"] == 30
    assert data["limits"]["calendar_max_per_run"] == 500
    assert data["limits"]["calendar_backfill_days"] == 90
    assert data["limits"]["calendar_future_days"] == 7
    assert data["piggybacks"]["calendar"] == {"enabled": True, "cooldown_hours": 6}


def test_migrate_list_additions_appends_to_existing_operator_list():
    """M027-S02-T03: an operator vault that already pinned the skip-list to
    the old default `["email-delta"]` must pick up `folder-index` via the
    list-extend (KEY_ADDITIONS only injects MISSING keys). This is the exact
    path live vaults take on `wiki update`."""
    m = _mod()
    data: dict = {"limits": {"compile_skip_substrate_types": ["email-delta"]}}
    changes = m.migrate_list_additions(data)
    assert data["limits"]["compile_skip_substrate_types"] == [
        "email-delta",
        "folder-index",
    ]
    assert any("folder-index" in c for c in changes)
    # idempotent on re-run; operator-custom entries untouched
    assert m.migrate_list_additions(data) == []
    data["limits"]["compile_skip_substrate_types"].append("operator-custom")
    assert m.migrate_list_additions(data) == []
    assert "operator-custom" in data["limits"]["compile_skip_substrate_types"]


def test_migrate_list_removals_prunes_legacy_substrate_entries():
    """2026-05-18 cleanup: operator configs from the wind-down window had
    calendar-rollup / memory-sync / memory-seed in the skip-list; they move
    out when the dedicated lean prompts + memory-substrate reversal ship.
    (compile_force_long_context_types itself was dropped entirely 2026-07-18
    via KEY_DROPS, so it's no longer list-pruned here.)"""
    m = _mod()
    data: dict = {
        "limits": {
            "compile_skip_substrate_types": ["calendar-rollup", "operator-custom"],
        },
    }
    changes = m.migrate_list_removals(data)
    # Legacy entry pruned; operator-custom entries preserved.
    assert data["limits"]["compile_skip_substrate_types"] == ["operator-custom"]
    assert any("removed 'calendar-rollup' from limits.compile_skip_substrate_types" in c for c in changes)


def test_migrate_list_removals_idempotent():
    """Re-running on already-pruned config produces no changes."""
    m = _mod()
    data: dict = {
        "limits": {
            "compile_skip_substrate_types": ["email-delta"],
            "daily_email_top_senders": 5,
            "daily_email_sample_subjects": 12,
        },
    }
    changes = m.migrate_list_removals(data)
    assert changes == []


def test_migrate_additions_preserves_existing_calendar_piggyback():
    """Operator-tweaked calendar cooldown is not clobbered by injection (the
    dead max_per_run subkey is pruned separately, in migrate_piggybacks)."""
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


def test_drops_dead_max_per_run_from_registry_meeting_piggybacks():
    """C05: piggybacks.{jamie,gmeet,calendar}.max_per_run is a dead knob —
    build_piggyback_tasks never passes it to a Registry collector; the live
    caps are limits.*_max_per_run + per-account sub-blocks. Pruned
    unconditionally, rest of the block preserved."""
    m = _mod()
    src = {
        "jamie": {"enabled": True, "cooldown_hours": 6, "max_per_run": 20},
        "gmeet": {"enabled": False, "cooldown_hours": 12, "max_per_run": 20},
        "calendar": {"enabled": True, "cooldown_hours": 6, "max_per_run": 500},
        "pictures": {"enabled": True, "cooldown_hours": 6, "max_per_run": 20},  # LIVE — kept
    }
    out, changes = m.migrate_piggybacks(src)
    assert out["jamie"] == {"enabled": True, "cooldown_hours": 6}
    assert out["gmeet"] == {"enabled": False, "cooldown_hours": 12}  # operator fields kept
    assert out["calendar"] == {"enabled": True, "cooldown_hours": 6}
    # pictures self-caps via CONFIG.piggybacks — its max_per_run is live
    assert out["pictures"] == {"enabled": True, "cooldown_hours": 6, "max_per_run": 20}
    assert sum("dropped piggybacks." in c and "max_per_run" in c for c in changes) == 3


def test_subkey_drop_idempotent_when_absent():
    m = _mod()
    src = {"jamie": {"enabled": True, "cooldown_hours": 6}}
    out, changes = m.migrate_piggybacks(src)
    assert changes == []
    assert out == src


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


def test_migrate_drops_removes_dead_compile_ladder_knobs():
    """C13 (2026-07-18): the three dead precedence-ladder knobs are pruned from
    operator vaults on `wiki update`. compile_large_source_model is NOT touched
    (it still backs the kind=unknown retry)."""
    m = _mod()
    data: dict = {
        "limits": {
            "compile_force_long_context_types": ["daily-digest"],
            "compile_max_turns_long_context": 30,
            "compile_large_source_chars": 50000,
            "compile_max_turns": 20,  # KEPT — live default-dispatch knob
        },
        "models": {"compile_large_source_model": "claude-opus-4-8[1m]"},  # KEPT
    }
    changes = m.migrate_drops(data)
    assert "compile_force_long_context_types" not in data["limits"]
    assert "compile_max_turns_long_context" not in data["limits"]
    assert "compile_large_source_chars" not in data["limits"]
    assert data["limits"]["compile_max_turns"] == 20
    assert data["models"]["compile_large_source_model"] == "claude-opus-4-8[1m]"
    assert len(changes) == 3
    assert all("dropped orphan limits." in c for c in changes)


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


# ── migrate_account_additions: per-account placeholder injection ────


def test_migrate_account_additions_injects_healthkit_into_oura_account():
    """M023: any account with health.oura gets a healthkit placeholder."""
    m = _mod()
    data = {
        "personal": {
            "accounts": {
                "default": {
                    "email": "alex@example.com",
                    "health": {
                        "oura": {"kind": "oura-pat", "api_key_env": "OURA_PRIVATE_PAT"},
                    },
                },
            },
        },
    }
    changes = m.migrate_account_additions(data)
    hk = data["personal"]["accounts"]["default"]["health"]["healthkit"]
    assert hk == {
        "kind": "healthkit-xml-export",
        "inbox_dir": "",
        "filename": "Export.xml",
    }
    assert any("healthkit" in c for c in changes)


def test_migrate_account_additions_skips_account_without_oura():
    """Accounts that never opted into health get no second-source nudge."""
    m = _mod()
    data = {
        "personal": {
            "accounts": {
                "work": {"email": "work@example.com"},
            },
        },
    }
    changes = m.migrate_account_additions(data)
    assert changes == []
    assert "health" not in data["personal"]["accounts"]["work"]


def test_migrate_account_additions_idempotent_when_healthkit_present():
    """Operator-set values must not be overwritten on re-run."""
    m = _mod()
    data = {
        "personal": {
            "accounts": {
                "default": {
                    "health": {
                        "oura": {"kind": "oura-pat"},
                        "healthkit": {
                            "kind": "healthkit-xml-export",
                            "inbox_dir": "/operator/path",
                            "filename": "Custom.xml",
                        },
                    },
                },
            },
        },
    }
    changes = m.migrate_account_additions(data)
    assert changes == []
    assert (
        data["personal"]["accounts"]["default"]["health"]["healthkit"]["inbox_dir"]
        == "/operator/path"
    )


# ── migrate_account_additions: M024 gmeet.email_discovery ───────────────


def test_migrate_account_additions_injects_email_discovery_into_gmeet_account():
    """M024: any account with a gmeet block gains an email_discovery block."""
    m = _mod()
    data = {
        "personal": {
            "accounts": {
                "work": {
                    "email": "alex@example.com",
                    "gmeet": {"kind": "gmeet-api", "drive_folder_name": "Meet Recordings"},
                },
            },
        },
    }
    changes = m.migrate_account_additions(data)
    ed = data["personal"]["accounts"]["work"]["gmeet"]["email_discovery"]
    assert ed == {
        "enabled": True,
        "senders": ["gemini-notes@google.com"],
        "folder": "INBOX",
        "backfill_days": 30,
    }
    assert any("email_discovery" in c for c in changes)


def test_migrate_account_additions_skips_account_without_gmeet():
    m = _mod()
    data = {"personal": {"accounts": {"plain": {"email": "x@y.de"}}}}
    changes = m.migrate_account_additions(data)
    assert changes == []
    assert "gmeet" not in data["personal"]["accounts"]["plain"]


def test_migrate_account_additions_idempotent_when_email_discovery_present():
    """Operator-set email_discovery values must not be overwritten on re-run."""
    m = _mod()
    data = {
        "personal": {
            "accounts": {
                "work": {
                    "gmeet": {
                        "kind": "gmeet-api",
                        "email_discovery": {"enabled": False, "senders": ["x@y.de"]},
                    },
                },
            },
        },
    }
    changes = m.migrate_account_additions(data)
    assert changes == []
    assert data["personal"]["accounts"]["work"]["gmeet"]["email_discovery"]["enabled"] is False


# ── migrate_model_upgrades: superseded-default value bumps ──────────


def test_model_upgrade_bumps_retired_default():
    m = _mod()
    data = {"models": {
        "compile_model": "claude-opus-4-7",
        "compile_large_source_model": "claude-opus-4-7[1m]",
        "dream_model": "claude-opus-4-7[1m]",
    }}
    changes = m.migrate_model_upgrades(data)
    assert data["models"]["compile_model"] == "claude-haiku-4-5-20251001"
    assert data["models"]["compile_large_source_model"] == "claude-opus-4-8[1m]"
    assert data["models"]["dream_model"] == "claude-opus-4-8[1m]"
    assert len(changes) == 3


def test_model_upgrade_compile_model_opus_to_haiku():
    """2026-08-26 flip (audit E3): route.py has pinned Haiku per-substrate since
    M026 — an operator vault still on the old opus default follows the engine
    default so the knob tells the truth again."""
    m = _mod()
    data = {"models": {"compile_model": "claude-opus-4-8"}}
    changes = m.migrate_model_upgrades(data)
    assert data["models"]["compile_model"] == "claude-haiku-4-5-20251001"
    assert len(changes) == 1


def test_model_upgrade_preserves_pinned_other_model():
    """A deliberately-pinned non-default model is left untouched."""
    m = _mod()
    data = {"models": {"compile_model": "claude-sonnet-4-6"}}
    changes = m.migrate_model_upgrades(data)
    assert data["models"]["compile_model"] == "claude-sonnet-4-6"
    assert changes == []


def test_model_upgrade_idempotent_on_current():
    m = _mod()
    data = {"models": {
        "compile_model": "claude-haiku-4-5-20251001",
        "dream_model": "claude-opus-4-8[1m]",
    }}
    assert m.migrate_model_upgrades(data) == []


def test_model_upgrade_noop_without_models_block():
    m = _mod()
    assert m.migrate_model_upgrades({}) == []

# ── Schema ↔ migration drift policy (the mechanical hard-rule gate) ──
#
# CLAUDE.md hard rule: "Config-knob changes are not done until the vault is
# migrated." These tests enforce it: every knob on the schema must carry an
# explicit injection policy in the migration, so adding a dataclass field
# without touching migrate_config_keys.py fails the suite.


def _schema_leaf_fields() -> dict[str, set[str]]:
    from core.config_schema import WikiConfig

    cfg = WikiConfig()
    return {
        section: {f.name for f in fields(getattr(cfg, section))}
        for section in (
            "scheduling", "models", "limits", "features",
            "graph_view", "skills", "personal",
        )
    }


def test_every_schema_knob_has_a_migration_policy():
    """Each schema field is in exactly one of INJECTED_KEYS / NEVER_INJECTED."""
    m = _mod()
    for section, schema_keys in _schema_leaf_fields().items():
        injected = set(m.INJECTED_KEYS.get(section, ()))
        never = set(m.NEVER_INJECTED.get(section, ()))
        overlap = injected & never
        assert not overlap, f"{section}: {sorted(overlap)} in BOTH policy tables"
        missing = schema_keys - injected - never
        assert not missing, (
            f"{section}: knob(s) {sorted(missing)} have NO migration policy. "
            "Add each to INJECTED_KEYS (inject into operator vaults with the "
            "schema default) or NEVER_INJECTED (explicit dataclass fall-through) "
            "in scripts/migrations/migrate_config_keys.py — CLAUDE.md hard rule: "
            "config-knob changes are not done until the vault is migrated."
        )
        ghosts = (injected | never) - schema_keys
        assert not ghosts, (
            f"{section}: policy entries {sorted(ghosts)} have no backing schema "
            "field — remove the stale entry (and add a KEY_DROPS entry if the "
            "knob was deleted from the schema)."
        )


def test_injected_values_match_schema_defaults():
    """KEY_ADDITIONS values are derived — guard against future hand-set literals."""
    m = _mod()
    for section, keys in m.INJECTED_KEYS.items():
        for key in keys:
            assert m.KEY_ADDITIONS[section][key] == m._schema_default(section, key), (
                f"{section}.{key}: injected value diverges from the schema default"
            )


# NEVER_INJECTED is a CLOSED historical set. Both of its justifying classes are
# backward-looking: (1) pre-migration-era keys operator configs ALREADY carry
# from the install-time config.example.yaml copy, (2) secrets / per-install
# paths / operator-authored account structures. A brand-new knob can be
# neither — it belongs in INJECTED_KEYS so the migration writes it into
# operator vaults (CLAUDE.md hard rule). Incident 2026-08-26: three new limits
# knobs were appended here next to same-prefixed neighbours
# (gmeet_request_timeout_s) and silently never reached the operator's config;
# `wiki update` reported "already on the current key schema" and every existing
# test stayed green, because the drift test only checks that a knob is in
# EXACTLY ONE table — never that it is in the RIGHT one.
#
# To add an entry here: extend this snapshot in the same commit AND write the
# justifying class into the NEVER_INJECTED docstring. If you cannot name the
# class, the key belongs in INJECTED_KEYS.
_FROZEN_NEVER_INJECTED: dict[str, set[str]] = {
    "features": {
        "clippings_sweep", "curiosity_loop", "procmail_execution",
        "vision_screenshots",
    },
    "graph_view": {"custom_search", "domain_tags", "mode"},
    "limits": {
        "compile_failure_backoff_s", "compile_max_consecutive_failures",
        "compile_max_files", "compile_max_prompt_chars", "compile_max_turns",
        "compile_retry_long_context_min_source_chars",
        "compile_retry_long_context_on_unknown",
        "curiosity_folder_confidence_min", "curiosity_max_gaps",
        "curiosity_max_prompt_chars", "curiosity_min_source_chars",
        "curiosity_quote_min_anchor_tokens", "curiosity_source_globs",
        "curiosity_timeout_s", "flush_max_retries", "flush_retry_delay_seconds",
        "gmeet_max_per_run", "gmeet_request_timeout_s", "jamie_max_per_run",
        "jamie_request_timeout_s", "oura_max_backfill_days",
        "oura_request_timeout_s", "query_max_prompt_chars",
        "screenshot_resize_width", "screenshot_timeout_seconds",
        "sdk_max_buffer_size_mb", "sparse_threshold_words",
        "youtube_aggregate_timeout_s", "youtube_frame_resize_width",
        "youtube_max_duration_s", "youtube_max_frames",
        "youtube_vision_timeout_s",
    },
    "models": {
        "classify_model", "compile_large_source_model", "compile_model",
        "curiosity_model", "ollama_url", "vision_model",
    },
    "personal": {
        "accounts", "calendar_skip_keywords", "curiosity_folders",
        "email_folders", "firefox_profile", "primary_account",
        "project_examples", "stg_backup_dir", "thunderbird_profile",
        "voice_inbox",
    },
    "scheduling": {"compile_after_hour", "dedup_window_seconds", "timezone"},
    "skills": {"global_install"},
}


def test_never_injected_is_a_closed_historical_set():
    m = _mod()
    actual = {section: set(keys) for section, keys in m.NEVER_INJECTED.items()}
    added = {
        s: sorted(actual.get(s, set()) - _FROZEN_NEVER_INJECTED.get(s, set()))
        for s in actual
    }
    added = {s: keys for s, keys in added.items() if keys}
    assert not added, (
        f"new NEVER_INJECTED entries: {added}. A brand-new knob cannot satisfy "
        "either justifying class — put it in INJECTED_KEYS so operator vaults "
        "actually receive it (CLAUDE.md hard rule). If it genuinely is a "
        "secret / per-install path / operator-authored structure, extend "
        "_FROZEN_NEVER_INJECTED here AND document the class in the "
        "NEVER_INJECTED docstring, in the same commit."
    )
    removed = {
        s: sorted(_FROZEN_NEVER_INJECTED[s] - actual.get(s, set()))
        for s in _FROZEN_NEVER_INJECTED
    }
    removed = {s: keys for s, keys in removed.items() if keys}
    assert not removed, (
        f"NEVER_INJECTED entries disappeared: {removed}. If the knob was "
        "deleted from the schema, drop it from _FROZEN_NEVER_INJECTED too; if "
        "it moved to INJECTED_KEYS, that is a policy change worth stating."
    )


def test_piggyback_defaults_have_a_migration_policy():
    """Every _default_piggybacks entry is either injected or explicitly not."""
    from core.config_schema import _default_piggybacks

    m = _mod()
    default_names = set(_default_piggybacks())
    injected = set(m.INJECTED_PIGGYBACKS)
    never = set(m.NEVER_INJECTED_PIGGYBACKS)
    assert not injected & never
    missing = default_names - injected - never
    assert not missing, (
        f"piggybacks: {sorted(missing)} have no migration policy — add to "
        "INJECTED_PIGGYBACKS or NEVER_INJECTED_PIGGYBACKS."
    )
    ghosts = (injected | never) - default_names
    assert not ghosts, f"piggybacks: policy entries {sorted(ghosts)} not in _default_piggybacks()"
    # A renamed-away old key must never reappear as a defaults-table name.
    resurrected = set(m.PIGGYBACK_RENAMES) & default_names
    assert not resurrected, (
        f"piggybacks: renamed-away name(s) {sorted(resurrected)} back in defaults"
    )
    for name in injected:
        assert m.KEY_ADDITIONS["piggybacks"][name] == m._piggyback_default(name)


def test_key_drops_do_not_resurrect():
    """A dropped orphan key must not exist on the schema (else the migration
    would prune a live knob from operator vaults)."""
    m = _mod()
    schema = _schema_leaf_fields()
    for section, orphans in m.KEY_DROPS.items():
        live = set(orphans) & schema.get(section, set())
        assert not live, f"{section}: KEY_DROPS would prune live schema knob(s) {sorted(live)}"


def test_migration_converges_from_empty_config(tmp_path):
    """Greenfield: empty config → one migration pass → second pass is a no-op."""
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}\n", encoding="utf-8")

    first_text, first_changes = m.migrate_config(config_path)
    assert first_changes, "expected greenfield injections"
    config_path.write_text(first_text, encoding="utf-8")
    second_text, second_changes = m.migrate_config(config_path)
    assert second_text is None, f"migration did not converge: {second_changes}"
