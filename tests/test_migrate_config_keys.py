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
    # 2 piggyback (rename + drop)
    #  + 1 created-limits-block + 28 limits additions:
    #    compile_force_long_context_types, compile_skip_on_long_context_unknown,
    #    compile_aggregated_max_consecutive_failures (2026-05-17 circuit-breaker),
    #    compile_role_default_by_location (M007), 4 calendar_*,
    #    compile_max_turns_long_context, compile_max_cost_per_file_usd,
    #    compile_skip_substrate_types — default ["email-delta"],
    #    daily_email_top_senders + daily_email_sample_subjects (2026-05-23 email rollup beta),
    #    3 flush_*_budget_chars (2026-05-16),
    #    compile_per_call_timeout_s (M010), reports_default_lookback_days (M019),
    #    connection_min_words (M012),
    #    3 extract_takes_* (M011),
    #    dream_entity_max_cost_usd + dream_cycle_max_cost_per_run_usd (M014),
    #    dream_tier1_recent_count + dream_tier1_digest_days +
    #    dream_tier2_sample_count (M016),
    #    correct_apply_max_turns + correct_broad_term_threshold (M028, issue #5)
    #  + 6 piggybacks additions (calendar, curiosity_followup, dream_cycle — M014,
    #    pictures — 2026-05-17, study_run_due + analyst_pass2 — M019-S05)
    #  + 1 created-features-block + 6 features additions
    #    (extract_takes — M011, voice_punctuate — 2026-05-17,
    #    suggestions_source_globs — Producer-seam arc,
    #    compile_callback_gate — 2026-05-17 compile-scope fix,
    #    materialize_backlinks — M020 backlinks-footer,
    #    operator_reports — M019 operator-self-reports master switch)
    #  + 1 created-personal-block + 5 personal additions
    #    (implicit_operator_author — M009, picture_inbox — 2026-05-17,
    #    reports_dir — M019, domains — M013, capture_inbox — M025)
    #  + 1 scheduling addition (dream_cooldown_days — M014; the scheduling
    #    block already exists in the test fixture, so no "created" event)
    # (LIST_ADDITIONS has one entry but operator's freshly-injected
    # skip-list already contains "email-delta" from KEY_ADDITIONS, so
    # the list-extend is a no-op on greenfield.)
    #  + 1 created-models-block + 1 models.dream_model (M014/M018 — fixture
    #    sync was missing; pre-existing red until 2026-05-22)
    #  + 1 limits.dream_per_call_timeout_s (M014 — same pre-existing gap)
    #  + 3 limits.concept_reconcile_* + 1 scheduling.concept_reconcile_cooldown_days
    #    + 1 features.concept_reconciliation (2026-05-22 concept-consistency-routine)
    # +3 health_trends (2 limits + 1 features), 2026-05-23
    # +1 personal.capture_inbox (M025 quick-capture loop), 2026-05-23
    # +1 piggybacks.capture (M025 capture piggyback knob), 2026-05-23
    # +5 personal.voice_transcribe_* (M026 audio ingest), 2026-05-28
    # +1 limits.voice_punctuate_timeout_s (M026 hotfix), 2026-05-28
    # +1 personal.inbox_bridges (inbox-bridge rsync mirror), 2026-05-28
    # +1 features.relativize_wikilinks (relativize-wikilinks pass), 2026-05-29
    # +1 features.extract_picture_metadata (EXIF + Android filename pattern), 2026-05-29
    # +5 limits.{ollama_connect_timeout_s, piggyback_max_runtime_s,
    #    review_ollama_timeout_s, review_consecutive_failure_abort,
    #    review_checkpoint_every} (Ollama/piggyback/review reliability), 2026-05-30
    # +1 limits.dedup_fuzzy_threshold (wiki dedup, issue #3), 2026-05-31
    # +3 dream web-research (issue #2), 2026-05-31:
    #    features.dream_web_research, scheduling.web_research_cooldown_days,
    #    personal.exa_api_key
    # +1 features.dream_require_entity_substrate (dream no-op skip), 2026-05-31
    # +1 scheduling.dream_insufficient_corpus_backoff_max_days (backoff), 2026-06-02
    # +1 personal.watched_folders (M027 watched-folder curiosity), 2026-06-07
    # KEY_ADDITIONS injects the skip-list with BOTH defaults in one change;
    # the LIST_ADDITIONS extend is a no-op on greenfield (folder-index
    # already present), 2026-06-10 M027-S02-T03.
    # +2 limits.folder_index_{max_depth,recent_n} (M027-S02-T04 `wiki
    #    index`; max_tree_entries shipped+removed same day — write-time
    #    cap reversal 2026-06-10, never in this greenfield fixture)
    # +1 models.folder_scan_provider (M027-S04-T01 Q9 seam), 2026-06-10
    # +1 limits.curiosity_folder_max_candidates (candidate retrieval), 2026-06-13
    # +1 scheduling.piggybacks_on_compile (compile drains due piggybacks), 2026-06-13
    # +1 personal.output_language (issue #4 compiled-prose language), 2026-06-13
    # +1 limits.curiosity_exclude_globs (curiosity substrate denylist), 2026-06-13
    # +1 limits.correct_apply_max_turns (M028 sandbox apply, issue #5), 2026-06-13
    # +1 limits.correct_broad_term_threshold (M028 broad-term warning, issue #5), 2026-06-13
    assert len(changes) == 93, f"got {len(changes)} changes: {changes}"

    reparsed = yaml.safe_load(new_text)
    # piggyback side
    assert "screenshots" in reparsed["piggybacks"]
    assert "scan_screenshots" not in reparsed["piggybacks"]
    assert "sync_memories" not in reparsed["piggybacks"]
    assert reparsed["piggybacks"]["lint_structural"] == {"enabled": True, "cooldown_hours": 24}
    # new piggyback injected
    assert reparsed["piggybacks"]["calendar"] == {"enabled": True, "cooldown_hours": 6, "max_per_run": 500}
    # additions side — force-long-context empty, skip-substrate-types
    # has email-delta from KEY_ADDITIONS default (2026-05-16-evening)
    # + folder-index (2026-06-10 M027-S02-T03)
    assert reparsed["limits"]["compile_force_long_context_types"] == []
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
    """Piggybacks current AND additions already present → no change."""
    m = _mod()
    config_path = tmp_path / ".wiki" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump({
        "models": {
            "dream_model": "claude-opus-4-7[1m]",
            "folder_scan_provider": "claude-sdk",
        },
        "scheduling": {
            "piggybacks_on_compile": True,
            "dream_cooldown_days": 7,
            "dream_priority": {"default": 1.0, "paths": {}, "domain": {}, "tag_strategy": "max", "tags": {}, "status": {}},
            "concept_reconcile_cooldown_days": 14,
            "web_research_cooldown_days": 30,
            "dream_insufficient_corpus_backoff_max_days": 30,
        },
        "piggybacks": {
            "email": {"enabled": True, "cooldown_hours": 24},
            "calendar": {"enabled": True, "cooldown_hours": 6, "max_per_run": 500},
            "curiosity_followup": {"enabled": True, "cooldown_hours": 6, "max_per_run": 5},
            "dream_cycle": {"enabled": True, "cooldown_hours": 24, "max_per_run": 3},
            "pictures": {"enabled": True, "cooldown_hours": 6, "max_per_run": 20},
            "capture": {"enabled": True, "cooldown_hours": 1},
            "study_run_due": {"enabled": False, "cooldown_hours": 6},
            "analyst_pass2": {"enabled": False, "cooldown_hours": 168},
        },
        "limits": {
            "compile_force_long_context_types": [],
            "compile_skip_on_long_context_unknown": True,
            "compile_aggregated_max_consecutive_failures": 3,
            "compile_role_default_by_location": True,
            "calendar_request_timeout_s": 30,
            "calendar_max_per_run": 500,
            "calendar_backfill_days": 90,
            "calendar_future_days": 7,
            "compile_max_turns_long_context": 30,
            "compile_max_tokens_per_file": 500_000,
            "compile_skip_substrate_types": ["email-delta", "folder-index"],
            "folder_index_max_depth": 0,
            "folder_index_recent_n": 20,
            "daily_email_top_senders": 5,
            "daily_email_sample_subjects": 12,
            "flush_assistant_text_budget_chars": 50000,
            "flush_user_text_budget_chars": 10000,
            "flush_tool_summary_budget_chars": 10000,
            "compile_per_call_timeout_s": 600,
            "reports_default_lookback_days": 14,
            "connection_min_words": 50,
            "extract_takes_source_globs": ["raw/transcripts/*", "raw/transcripts/**/*", "raw/voice/*", "daily/*"],
            "extract_takes_timeout_s": 180,
            "extract_takes_max_per_source": 12,
            "dream_entity_max_prompt_chars": 415_000,
            "dream_cycle_max_tokens_per_run": 2_000_000,
            "dream_per_call_timeout_s": 300,
            "curiosity_folder_max_candidates": 40,
            "curiosity_exclude_globs": ["raw/notes/email/deep-*"],
            "dream_tier1_recent_count": 20,
            "dream_tier1_digest_days": 7,
            "dream_tier2_sample_count": 50,
            "concept_reconcile_max_files_per_fact": 25,
            "concept_reconcile_max_facts_per_run": 10,
            "concept_reconcile_max_turns": 15,
            "correct_apply_max_turns": 50,
            "correct_broad_term_threshold": 15,
            "health_trends_recent_months": 6,
            "health_trends_min_coverage_days": 10,
            "voice_punctuate_timeout_s": 120,
            "ollama_connect_timeout_s": 10,
            "piggyback_max_runtime_s": 14400,
            "review_ollama_timeout_s": 300,
            "review_consecutive_failure_abort": 5,
            "review_checkpoint_every": 25,
            "dedup_fuzzy_threshold": 0.85,
        },
        "features": {
            "extract_takes": False,
            "dream_web_research": False,
            "voice_punctuate": True,
            "suggestions_source_globs": ["raw/email/*.md"],
            "compile_callback_gate": True,
            "materialize_backlinks": True,
            "relativize_wikilinks": True,
            "extract_picture_metadata": True,
            "operator_reports": False,
            "concept_reconciliation": False,
            "health_trends": False,
            "dream_require_entity_substrate": True,
        },
        "personal": {
            "implicit_operator_author": None,
            "picture_inbox": "",
            "capture_inbox": "",
            "reports_dir": "reports",
            "domains": ["company", "personal", "ai", "meta"],
            "voice_transcribe_model": "",
            "voice_transcribe_language": "auto",
            "voice_transcribe_threads": 4,
            "voice_transcribe_binary": "",
            "voice_transcribe_ffmpeg": "",
            "inbox_bridges": [],
            "watched_folders": [],
            "exa_api_key": "",
            "output_language": "auto",
        },
    }), encoding="utf-8")

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
    assert reparsed["limits"]["compile_force_long_context_types"] == []
    assert reparsed["limits"]["compile_skip_on_long_context_unknown"] is True
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
        "models": {
            "dream_model": "claude-opus-4-7[1m]",
            "folder_scan_provider": "claude-sdk",
        },
        "scheduling": {
            "piggybacks_on_compile": True,
            "dream_cooldown_days": 7,
            "dream_priority": {"default": 1.0, "paths": {}, "domain": {}, "tag_strategy": "max", "tags": {}, "status": {}},
            "concept_reconcile_cooldown_days": 14,
            "web_research_cooldown_days": 30,
            "dream_insufficient_corpus_backoff_max_days": 30,
        },
        "limits": {
            "compile_force_long_context_types": ["daily-digest", "calendar-rollup"],
            "compile_skip_on_long_context_unknown": True,
            "compile_aggregated_max_consecutive_failures": 3,
            "compile_role_default_by_location": True,
            "calendar_request_timeout_s": 30,
            "calendar_max_per_run": 500,
            "calendar_backfill_days": 90,
            "calendar_future_days": 7,
            "compile_max_turns_long_context": 30,
            "compile_max_tokens_per_file": 500_000,
            "compile_skip_substrate_types": ["calendar-rollup"],
            "folder_index_max_depth": 0,
            "folder_index_recent_n": 20,
            "daily_email_top_senders": 5,
            "daily_email_sample_subjects": 12,
            "flush_assistant_text_budget_chars": 50000,
            "flush_user_text_budget_chars": 10000,
            "flush_tool_summary_budget_chars": 10000,
            "compile_per_call_timeout_s": 600,
            "reports_default_lookback_days": 14,
            "connection_min_words": 50,
            "extract_takes_source_globs": ["raw/transcripts/*", "raw/transcripts/**/*", "raw/voice/*", "daily/*"],
            "extract_takes_timeout_s": 180,
            "extract_takes_max_per_source": 12,
            "dream_entity_max_prompt_chars": 415_000,
            "dream_cycle_max_tokens_per_run": 2_000_000,
            "dream_per_call_timeout_s": 300,
            "curiosity_folder_max_candidates": 40,
            "curiosity_exclude_globs": ["raw/notes/email/deep-*"],
            "dream_tier1_recent_count": 20,
            "dream_tier1_digest_days": 7,
            "dream_tier2_sample_count": 50,
            "concept_reconcile_max_files_per_fact": 25,
            "concept_reconcile_max_facts_per_run": 10,
            "concept_reconcile_max_turns": 15,
            "correct_apply_max_turns": 50,
            "correct_broad_term_threshold": 15,
            "health_trends_recent_months": 6,
            "health_trends_min_coverage_days": 10,
            "voice_punctuate_timeout_s": 120,
            "ollama_connect_timeout_s": 10,
            "piggyback_max_runtime_s": 14400,
            "review_ollama_timeout_s": 300,
            "review_consecutive_failure_abort": 5,
            "review_checkpoint_every": 25,
            "dedup_fuzzy_threshold": 0.85,
        },
        "piggybacks": {
            "calendar": {"enabled": True, "cooldown_hours": 6, "max_per_run": 500},
            "curiosity_followup": {"enabled": True, "cooldown_hours": 6, "max_per_run": 5},
            "dream_cycle": {"enabled": True, "cooldown_hours": 24, "max_per_run": 3},
            "pictures": {"enabled": True, "cooldown_hours": 6, "max_per_run": 20},
            "capture": {"enabled": True, "cooldown_hours": 1},
            "study_run_due": {"enabled": False, "cooldown_hours": 6},
            "analyst_pass2": {"enabled": False, "cooldown_hours": 168},
        },
        "features": {
            "extract_takes": False,
            "dream_web_research": False,
            "voice_punctuate": True,
            "suggestions_source_globs": ["raw/email/*.md"],
            "compile_callback_gate": True,
            "materialize_backlinks": True,
            "relativize_wikilinks": True,
            "extract_picture_metadata": True,
            "operator_reports": False,
            "concept_reconciliation": False,
            "health_trends": False,
            "dream_require_entity_substrate": True,
        },
        "personal": {
            "implicit_operator_author": None,
            "picture_inbox": "",
            "capture_inbox": "",
            "reports_dir": "reports",
            "domains": ["company", "personal", "ai", "meta"],
            "voice_transcribe_model": "",
            "voice_transcribe_language": "auto",
            "voice_transcribe_threads": 4,
            "voice_transcribe_binary": "",
            "voice_transcribe_ffmpeg": "",
            "inbox_bridges": [],
            "watched_folders": [],
            "exa_api_key": "",
            "output_language": "auto",
        },
    }
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
    assert data["piggybacks"]["calendar"] == {
        "enabled": True,
        "cooldown_hours": 6,
        "max_per_run": 500,
    }


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
            "compile_skip_substrate_types": ["email-delta"],
            "daily_email_top_senders": 5,
            "daily_email_sample_subjects": 12,
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
