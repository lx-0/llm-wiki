"""Migrate renamed / removed / added config.yaml keys to current engine schema.

The engine's config loader falls back to dataclass defaults for any key it
doesn't recognise — so a *renamed* key in an operator's `config.yaml` is
silently ignored and the operator's customisation stops applying without a
warning, and a *new* key never appears in the operator's file at all so they
don't see that it's tunable. This one-shot migration renames stale keys in
place (preserving operator values), drops keys for removed features, injects
new keys under their parent block with the engine default, and prunes orphan
keys whose backing dataclass entry was deleted (otherwise they linger as
silent YAML cruft forever).

Key changes covered (chronological):
  piggybacks.follow_requests              → piggybacks.curiosity_followup   (curiosity rework)
  piggybacks.scan_screenshots             → piggybacks.screenshots          (Collector port 2026-05-14)
  piggybacks.email_incremental            → piggybacks.email                (M002 — kept for old vaults)
  piggybacks.sync_memories                → (removed — sync-memories deleted 2026-05-13)
  piggybacks.optimize_claude_md           → force-disabled 2026-06-13 (only piggyback writing outside the vault — autonomously LLM-rewrites global ~/.claude/CLAUDE.md; block kept, enabled flipped true→false)
  limits.compile_force_long_context_types     (added 2026-05-15, default ["daily-digest"])
  limits.compile_skip_on_long_context_unknown (added 2026-05-15, default True)
  limits.calendar_request_timeout_s       (added 2026-05-15 M006, default 30)
  limits.calendar_max_per_run             (added 2026-05-15 M006, default 500)
  limits.calendar_backfill_days           (added 2026-05-15 M006, default 90)
  limits.calendar_future_days             (added 2026-05-15 M006, default 7)
  piggybacks.calendar                     (added 2026-05-15 M006, cooldown 6h, max_per_run 500)
  personal.calendar_work_keywords         → (dropped 2026-05-15 M006, scan_calendar-only legacy field)
  personal.calendar_categories            → (dropped 2026-05-15 M006, scan_calendar-only legacy field)
  personal.calendar_report_language       → (dropped 2026-05-15 M006, scan_calendar-only legacy field)
  limits.compile_force_long_context_types ← list-extend with "calendar-rollup" (2026-05-16, M006 hardening)
  limits.compile_max_turns_long_context   (added 2026-05-16, default 30 — fixes max_turns trap on dense fan-out substrates)
  limits.compile_max_cost_per_file_usd    (added 2026-05-16, default 1.0 — per-file budget guard, aborts batch on overrun)
  limits.compile_skip_substrate_types     (added 2026-05-16, default [] — substrate-skip-list for batch mode)
  limits.compile_force_long_context_types ← list-prune calendar-rollup AND daily-digest (2026-05-16 P2, dedicated prompts shipped)
  limits.compile_skip_substrate_types     ← list-prune calendar-rollup (2026-05-16 P2, compile_calendar.md ships)
  piggybacks.curiosity_followup           (added 2026-05-16, default cooldown 6h / max 5 — never injected by original 2026-05-13 rollout, requests accumulated)
  limits.flush_assistant_text_budget_chars (added 2026-05-16, default 50_000 — replaces MAX_CONTEXT_CHARS=15_000)
  limits.flush_user_text_budget_chars      (added 2026-05-16, default 10_000)
  limits.flush_tool_summary_budget_chars   (added 2026-05-16, default 10_000)
  limits.compile_per_call_timeout_s        (added 2026-05-16, default 600 — per-call timeout for compile SDK invocations)
  personal.implicit_operator_author        (added 2026-05-16, default None — author-attribution fallback for single-tenant vaults)
  personal.domains                         (added 2026-05-16 M013, default [company, personal, ai, meta] — optional domain:-frontmatter enum)
  limits.connection_min_words              (added 2026-05-16 M012, default 50 — connection-article quality gate floor)
  scheduling.dream_cooldown_days           (added 2026-05-16 M014, default 7 — dream-cycle per-entity cooldown)
  scheduling.dream_priority                (added 2026-05-17 M017, dict — config-driven entity priority weighting)
  limits.dream_entity_max_cost_usd         (added 2026-05-16 M014, default 2.0 — dream-cycle per-entity pre-flight USD cap)
  limits.dream_cycle_max_cost_per_run_usd  (added 2026-05-16 M014, default 5.0 — dream-cycle per-run cumulative USD cap)
  piggybacks.dream_cycle                   (added 2026-05-16 M014, cooldown 24h, max_per_run 3)
  personal.picture_inbox                   (added 2026-05-17, default "" — camera/phone-photo inbox for collectors/pictures.py)
  piggybacks.pictures                      (added 2026-05-17, cooldown 6h, max_per_run 20 — vision-LLM-driven, lighter cadence than screenshots)
  features.voice_punctuate                 (added 2026-05-17, default True — Ollama-driven punctuation pass on voice transcripts at ingest)
  features.compile_callback_gate           (added 2026-05-17, default True — `can_use_tool` callback as the real path-scope gate for compile + dream; replaces decorative `Write(knowledge/**)` syntax)
  features.materialize_backlinks           (added 2026-05-17 M020, default True — corpus-wide post-compile pass writes a sentinel-managed `## Backlinks` footer into every knowledge/<article>)
  features.relativize_wikilinks            (added 2026-05-29, default True — corpus-wide post-compile pass rewrites every wikilink relative to its containing article so Obsidian resolves cross-article links from nested folders)
  limits.dream_tier1_recent_count          (added 2026-05-17 M016, default 20 — Tier 1 most-recent substrate count)
  limits.dream_tier1_digest_days           (added 2026-05-17 M016, default 7 — Tier 1 daily-digest day count)
  limits.dream_tier2_sample_count          (added 2026-05-17 M016, default 50 — Tier 2 weighted-sample size)
  features.suggestions_source_globs        (added 2026-05-17 Producer-seam, default ["raw/email/*.md"] — lifts legacy hardcoded _is_email_source filter onto Spec)
  limits.compile_aggregated_max_consecutive_failures (added 2026-05-17, default 3 — circuit-breaker on memory-seed chunked compiles; aborts loop after N consecutive chunk failures to stop $-bleed on substrate-prompt mismatch)
  personal.capture_inbox                   (added 2026-05-23 M025, default "" — quick-capture inbox for collectors/capture_collector.py)
  piggybacks.capture                       (added 2026-05-23 M025, cooldown 1h — operator override for the capture collector piggyback)
  limits.daily_email_top_senders           (added 2026-05-23, default 5 — email daily-rollup top-senders cap)
  limits.daily_email_sample_subjects       (added 2026-05-23, default 12 — email daily-rollup recent-subject sample cap)
  personal.voice_transcribe_model            (added 2026-05-28, default "" — whisper.cpp ggml model path; empty disables audio ingest)
  personal.voice_transcribe_language         (added 2026-05-28, default "auto")
  personal.voice_transcribe_threads          (added 2026-05-28, default 4)
  personal.voice_transcribe_binary           (added 2026-05-28, default "" — override whisper-cli path; empty = $PATH lookup)
  personal.voice_transcribe_ffmpeg           (added 2026-05-28, default "" — override ffmpeg path; empty = $PATH lookup; only used for m4a/mp4/aac pre-conversion)
  limits.voice_punctuate_timeout_s           (added 2026-05-28, default 120 — gemma4:e4b cold-call routinely >30s; absorbs model-load latency)
  personal.inbox_bridges                     (added 2026-05-28, default [] — rsync-based mirror for sandbox-restricted intake folders; see scripts/bridge/drive_sync.py)
  features.extract_picture_metadata          (added 2026-05-29, default True — EXIF + Android-screenshot-filename metadata extraction in pictures collector)
  limits.ollama_connect_timeout_s            (added 2026-05-30, default 10 — TCP connect cap for Ollama calls; prevents a down LAN GPU from burning the full read budget on connect)
  limits.{compile_force_long_context_types, compile_max_turns_long_context, compile_large_source_chars}  → (removed 2026-07-18 — dead precedence-ladder knobs. Every SUBSTRATE_PROMPTS row + the default dispatch pin the model + max_turns, so the config-side long-context escalation tiers could never fire; deleted per the no-soft-deprecation policy. compile_large_source_model itself stays — it still backs the kind=unknown retry.)
  limits.piggyback_max_runtime_s             (added 2026-05-30, default 14400 — hard wall-clock cap the piggyback runner enforces on each spawned task; backstop against the review-wiki 19h half-open-socket hang)
  limits.review_ollama_timeout_s             (added 2026-05-30, default 300 — per-article Ollama read timeout for review-wiki.py, lifted from a module constant)
  limits.review_consecutive_failure_abort    (added 2026-05-30, default 5 — review-wiki aborts the sweep after N consecutive Ollama failures instead of grinding 1700×timeout when kcma is down)
  limits.review_checkpoint_every             (added 2026-05-30, default 25 — review-wiki writes the partial report every N articles so an aborted/killed sweep isn't lost)
  limits.dedup_fuzzy_threshold               (added 2026-05-31, default 0.85 — `wiki dedup` fuzzy-title match floor for duplicate-candidate proposal)
  limits.curiosity_exclude_globs             (added 2026-06-13, default ["raw/notes/email/deep-*"] — denylist: both curiosity passes skip circular email-deep-scan substrate before the Ollama call)
  limits.review_max_sweep_runtime_s          (added 2026-06-13, default 12600 — review-wiki soft sweep deadline; clean partial + exit before the piggyback hard cap kills it)
  features.dream_web_research                (added 2026-05-31, default False — Exa-AI public-entity enrichment dream post-pass; issue #2)
  scheduling.web_research_cooldown_days      (added 2026-05-31, default 30 — `## Public Profile` refresh cooldown)
  scheduling.piggybacks_on_compile           (added 2026-06-13, default True — `wiki compile` drains due piggybacks at run-end, bypassing the evening hour-gate so update+compile-only operators keep maintenance current)
  personal.exa_api_key                       (added 2026-05-31, default "" — Exa AI key; falls back to env EXA_API_KEY)
  personal.output_language                    (added 2026-06-13 issue #4, default "auto" — pin compiled-prose language; non-"auto" forces target language across compile prompts)
  features.extract_intents                    (added 2026-06-13, default False — intent-dispatch master switch; post-compile classifies intake notes → tasks/)
  limits.intent_source_globs                  (added 2026-06-13, default ["raw/voice/*"] — intake substrates the intent pass runs on)
  limits.intent_source_globs                  ← list-extend with "raw/inbox-mobile/pictures/*.md" (2026-06-14 — intent now attaches to the mobile picture channel: camera photos + phone screenshots; desktop screenshots in raw/notes/screenshots/ stay out)
  limits.intent_classify_timeout_s            (added 2026-06-13, default 120 — per-call timeout for intent classification SDK invocation)
  limits.intent_min_confidence                (added 2026-06-13, default "high" — confidence floor below which an intent is logged but not dispatched)
  models.{compile_model,compile_large_source_model,dream_model}  (value upgrade 2026-06-13: opus 4-7 → 4-8; only exact old-default values are bumped, pinned models preserved)
  models.intent_classify_model               (added 2026-06-14, default "claude-haiku-4-5" — cheap triage tier for the intent-dispatch producer; "" → compile_model)
  limits.dashboard_refresh_timeout_s         (added 2026-07-14, default 300 — best-effort dashboard refresh
                                              budget; lifted from a hardcoded 120 s that was too tight for a
                                              growing vault under iCloud fs-stat variance)
  scheduling.dedup_window_seconds            (value upgrade 2026-07-14: 60 → 900; codex-session-capture
                                              — knob broadened to per-session re-capture / Codex-per-turn-Stop
                                              coalescing window; only the exact old default 60 is bumped)
  personal.accounts.<id>.health.healthkit    (added 2026-05-19 M023 — Apple HealthKit XML export ingest;
                                              injected as a placeholder into any account already carrying
                                              `health.oura`, kind: healthkit-xml-export, empty inbox_dir
                                              = opt-out; operator fills in the iCloud / vault path)
  piggybacks.{jamie,gmeet,calendar}.max_per_run  → (dropped 2026-07-18 C05 — dead knobs:
                                              build_piggyback_tasks never passes max_per_run to a
                                              Registry collector; the live caps are
                                              limits.{jamie,gmeet,calendar}_max_per_run + the
                                              per-account sub-blocks. Values 20/20/500 also
                                              contradicted the live limits defaults 50/50/500.)
  (structural, 2026-07-18 C05 piggyback-defaults collapse: `_default_piggybacks`
   is now the ONE piggyback-defaults source — its zombie `email_incremental`
   entry (readable by nothing; the runtime looks up `email`) became `email`,
   and `health` gained an entry; runtime cooldowns are unchanged (both matched
   the CollectorSpec fallback values, now parity-tested).)
  (structural, 2026-07-18 C05 config-schema seam: injected VALUES are now derived
   from `core.config_schema` — the hand-copied defaults and their "Match X default
   in scripts/core/config.py" comments are gone. The curated injection policy
   lives in INJECTED_KEYS / NEVER_INJECTED below;
   tests/test_migrate_config_keys.py::test_every_schema_knob_has_a_migration_policy
   fails when a schema knob is added without a policy entry.)

Idempotent: a config already on the current schema produces no change.

Usage:
    uv run python scripts/migrations/migrate_config_keys.py --vault PATH            # preview
    uv run python scripts/migrations/migrate_config_keys.py --vault PATH --apply    # write
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

import yaml

# Standalone-script bootstrap (mirrors core/config.py): the migration is
# invoked as `python scripts/migrations/migrate_config_keys.py` by `wiki
# update`, so `scripts/` must be on sys.path for the core.* imports below.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# IMPORTANT: import from core.config_schema, NEVER from core.config — that
# module runs `load()` + dotenv against the global CONFIG_FILE at import time,
# which need not be the vault we're migrating. The schema module is
# side-effect-free by contract (see its docstring).
from core.config_backup import backup_config_file  # noqa: E402
from core.config_schema import WikiConfig, _default_piggybacks  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("migrate-config-keys")


# ── Schema-derived defaults ─────────────────────────────────────────────
# KEY_ADDITIONS below curates WHICH keys get injected (a policy choice —
# see NEVER_INJECTED); the injected VALUES are read from the engine schema
# so a default can never drift between dataclass and migration again. The
# pre-C05 shape hand-copied every default with a "Match X default in
# scripts/core/config.py" comment as the only sync protocol.

_SCHEMA_DEFAULTS = WikiConfig()


def _plain(value: object) -> object:
    """Convert a schema default to plain YAML-dumpable types (tuple → list)."""
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _schema_default(section: str, key: str) -> object:
    """Engine default for `<section>.<key>`, read from core.config_schema."""
    return _plain(getattr(getattr(_SCHEMA_DEFAULTS, section), key))


def _piggyback_default(name: str) -> dict[str, object]:
    """Engine default block for `piggybacks.<name>` (max_per_run omitted when unset)."""
    task = _default_piggybacks()[name]
    block: dict[str, object] = {"enabled": task.enabled, "cooldown_hours": task.cooldown_hours}
    if task.max_per_run is not None:
        block["max_per_run"] = task.max_per_run
    return block

# old_key → new_key (rename, value preserved). new_key=None → drop the block.
PIGGYBACK_RENAMES: dict[str, str | None] = {
    "follow_requests": "curiosity_followup",
    "scan_screenshots": "screenshots",
    "email_incremental": "email",
    "sync_memories": None,  # feature removed 2026-05-13
}

# Piggybacks the engine force-disables on existing operator configs (an explicit
# `enabled: true` is flipped to false; the block is KEPT so the operator can see
# it and opt back in). Use when an engine-policy decision deprecates a piggyback
# that operators may have already enabled — distinct from RENAMES (which drops/
# renames the block) because the feature still exists.
#   optimize_claude_md: the only piggyback that writes OUTSIDE the vault — it
#   autonomously LLM-rewrites the operator's GLOBAL ~/.claude/CLAUDE.md. Disabled
#   by operator decision 2026-06-13 (vault-boundary violation + risk of silently
#   dropping hand-built global rules). Code kept; default off.
PIGGYBACK_FORCE_DISABLE: set[str] = {"optimize_claude_md"}

# Dead per-piggyback subkeys pruned from operator blocks (2026-07-18 C05).
# `build_piggyback_tasks` never passes max_per_run to a Registry collector, so
# on jamie/gmeet/calendar the subkey was a knob that did nothing — while the
# LIVE caps (limits.{jamie,gmeet,calendar}_max_per_run + the per-account
# sub-blocks) sat elsewhere. Pruning is unconditional: the knob is dead at any
# value, and leaving it suggests tunability that isn't there.
PIGGYBACK_SUBKEY_DROPS: dict[str, tuple[str, ...]] = {
    "jamie": ("max_per_run",),
    "gmeet": ("max_per_run",),
    "calendar": ("max_per_run",),
}

# Engine-policy model-version upgrades: an operator config still pinned to a
# SUPERSEDED engine default is bumped to the current default. Only an EXACT
# match of the old default is upgraded — a deliberately-pinned other model is
# preserved untouched. Keyed by models.<key> → {old_value: new_value}.
#   2026-06-13: opus 4-7 → 4-8 across compile / large-source / dream.
#   2026-08-26: compile_model opus → Haiku, then REVERTED the same day. Audit
#   E3 read only compile_stages/route.py, saw Haiku pinned on every row, and
#   concluded the knob was dead — but five agentic surfaces read it, including
#   `wiki correct apply`, which writes into knowledge/. The flip re-tiered them
#   silently, so the haiku value is mapped back to Opus here; the compile
#   fall-through moved to its own knob (models.compile_default_route_model).
MODEL_UPGRADES: dict[str, dict[str, str]] = {
    "compile_model": {
        "claude-opus-4-7": "claude-opus-4-8",
        "claude-haiku-4-5-20251001": "claude-opus-4-8",
    },
    "compile_large_source_model": {"claude-opus-4-7[1m]": "claude-opus-4-8[1m]"},
    "dream_model": {"claude-opus-4-7[1m]": "claude-opus-4-8[1m]"},
}

# Engine-policy scalar value upgrades: an operator config still pinned to a
# SUPERSEDED engine default is bumped to the current default. Only an EXACT
# match of the old default is upgraded — a deliberately-tuned other value is
# preserved. Keyed by "<parent>.<key>" → {old_value: new_value}.
#   2026-07-14 (codex-session-capture): scheduling.dedup_window_seconds 60 → 900.
#   The knob broadened from a rapid double-fire guard to the per-session
#   re-capture / Codex-per-turn-Stop coalescing window; 60 s no longer bounds a
#   multi-hour Codex session (fires are minutes-to-hours apart).
VALUE_UPGRADES: dict[str, dict[object, object]] = {
    "scheduling.dedup_window_seconds": {60: 900},
}

# ── Injection policy ────────────────────────────────────────────────────
# WHICH keys the migration injects into operator vaults is a curated policy
# choice, not a schema derivative: keys that predate the migration era are
# already in every operator config (copied from config.example.yaml at
# install), and some keys are deliberately left to dataclass fall-through
# (e.g. personal secrets that belong in `.claude/.env`, or singleton paths
# the operator sets once during setup). Every schema knob MUST appear in
# exactly one of INJECTED_KEYS / NEVER_INJECTED — the drift test
# (tests/test_migrate_config_keys.py::test_every_schema_knob_has_a_migration_policy)
# enforces that, turning the CLAUDE.md hard rule ("config-knob changes are
# not done until the vault is migrated") into a mechanical invariant.
#
# The injected VALUES are always read from core.config_schema (see
# KEY_ADDITIONS below) — never hand-copied here.

INJECTED_KEYS: dict[str, tuple[str, ...]] = {
    "models": (
        "dream_model",                # M014 dream-cycle model (2026-05-18)
        "folder_scan_provider",       # M027-S04 Q9 seam (2026-06-10)
        "intent_classify_model",      # intent-dispatch cheap tier (2026-06-14)
        "compile_default_route_model",  # compile fall-through route (2026-08-26)
    ),
    "graph_view": (
        # Was NEVER_INJECTED, so no vault could set it — and lint.py grew a
        # hardcoded copy of ONE operator's project names as the fallback
        # (2026-08-26).
        "domain_tags",
    ),
    "limits": (
        "curiosity_exclude_globs",    # curiosity substrate denylist (2026-06-13)
        "review_max_sweep_runtime_s",  # review-wiki soft sweep deadline (2026-06-13)
        "curiosity_folder_max_candidates",  # M027 candidate retrieval (2026-06-13)
        "dream_per_call_timeout_s",   # M014 per-message stall timeout (2026-05-18)
        "compile_skip_on_long_context_unknown",   # kind=unknown → skip (2026-05-15)
        "compile_aggregated_max_consecutive_failures",  # chunk circuit-breaker (2026-05-17)
        "compile_role_default_by_location",       # M007-S01-T02 (2026-05-16)
        # M006 Google Calendar collector (2026-05-15)
        "calendar_request_timeout_s",
        "calendar_max_per_run",
        "calendar_backfill_days",
        "calendar_future_days",
        "compile_max_tokens_per_file",  # per-file token guard (2026-05-16, USD→tokens 2026-05-23)
        "compile_skip_substrate_types",  # batch-mode substrate skip-list (2026-05-16)
        # M027-S02-T04 watched-folder index knobs (2026-06-10)
        "folder_index_max_depth",
        "folder_index_recent_n",
        # Email daily-rollup signal (beta, 2026-05-23)
        "daily_email_top_senders",
        "daily_email_sample_subjects",
        # Per-class flush-context budgets (2026-05-16)
        "flush_assistant_text_budget_chars",
        "flush_user_text_budget_chars",
        "flush_tool_summary_budget_chars",
        "dashboard_refresh_timeout_s",  # dashboard refresh budget (2026-07-14)
        "compile_per_call_timeout_s",   # per-compile-call hang guard (2026-05-16)
        "reports_default_lookback_days",  # M019 instrument lookback (2026-05-17)
        "connection_min_words",         # M012 connection quality gate (2026-05-16)
        # M011 takes substrate (2026-05-16)
        "extract_takes_source_globs",
        "extract_takes_timeout_s",
        "extract_takes_max_per_source",
        # M014 dream-cycle resource gates (2026-05-16, USD→tokens 2026-05-23)
        "dream_entity_max_prompt_chars",
        "dream_cycle_max_tokens_per_run",
        # M016 dream-cycle sampled-activation (2026-05-17)
        "dream_tier1_recent_count",
        "dream_tier1_digest_days",
        "dream_tier2_sample_count",
        # Concept-reconciliation routine (2026-05-22)
        "concept_reconcile_max_files_per_fact",
        "concept_reconcile_max_facts_per_run",
        "concept_reconcile_max_turns",
        # M028 hard-facts issue #5 (2026-06-13)
        "correct_apply_max_turns",
        "correct_broad_term_threshold",
        # Health-trend synthesis (2026-05-23)
        "health_trends_recent_months",
        "health_trends_min_coverage_days",
        "voice_punctuate_timeout_s",    # gemma cold-call absorb (2026-05-28)
        # Ollama/piggyback/review reliability bundle (2026-05-30)
        "ollama_connect_timeout_s",
        "piggyback_max_runtime_s",
        "review_ollama_timeout_s",
        "review_consecutive_failure_abort",
        "review_checkpoint_every",
        "dedup_fuzzy_threshold",        # wiki dedup, issue #3 (2026-05-31)
        # Intent-dispatch (2026-06-13)
        "intent_source_globs",
        "intent_classify_timeout_s",
        "intent_min_confidence",
        # M031 reliability wave (2026-08-26)
        "gmeet_export_dead_letter_attempts",
        "gmeet_export_dead_letter_reprobe_days",
        "doctor_piggyback_stale_factor",
        "doctor_piggyback_stale_min_hours",
        # Misfiled in NEVER_INJECTED until 2026-08-26 — born 2026-05-15, one
        # day after the migration shipped, so no install-time copy carried
        # them and no backfill ever ran. The compile pair is the sharpest
        # case: the retry's on/off switch was visible while the threshold
        # that gates it and the failure-backoff were not.
        "oura_request_timeout_s",
        "oura_max_backfill_days",
        "compile_failure_backoff_s",
        "compile_retry_long_context_min_source_chars",
    ),
    "scheduling": (
        "piggybacks_on_compile",        # compile drains due piggybacks (2026-06-13)
        "dream_cooldown_days",          # M014 (2026-05-16)
        "dream_priority",               # M017 (2026-05-17)
        "concept_reconcile_cooldown_days",  # concept routine (2026-05-22)
        "web_research_cooldown_days",   # dream web-research, issue #2 (2026-05-31)
        "dream_insufficient_corpus_backoff_max_days",  # backoff (2026-06-02)
    ),
    "features": (
        "extract_takes",                # M011 master switch (2026-05-16)
        "dream_web_research",           # issue #2, external paid Exa call (2026-05-31)
        "concept_reconciliation",       # autonomous concept edits, opt-in (2026-05-22)
        "health_trends",                # deterministic + $0, default OFF (2026-05-23)
        "voice_punctuate",              # Ollama punctuation pass (2026-05-17)
        "suggestions_source_globs",     # Producer-seam arc (2026-05-17)
        "compile_callback_gate",        # can_use_tool path-scope gate (2026-05-17)
        "materialize_backlinks",        # M020 backlinks footer (2026-05-17)
        "relativize_wikilinks",         # wikilink relativize pass (2026-05-29)
        "extract_picture_metadata",     # EXIF + Android filename pattern (2026-05-29)
        "operator_reports",             # M019 master switch (2026-05-17)
        "dream_require_entity_substrate",  # dream no-op skip (2026-05-31)
        "extract_intents",              # intent-dispatch master switch (2026-06-13)
    ),
    "personal": (
        "implicit_operator_author",     # author-attribution fallback (2026-05-16)
        "picture_inbox",                # pictures collector (2026-05-17)
        "capture_inbox",                # M025 quick-capture loop (2026-05-23)
        "reports_dir",                  # M019 reports surface (2026-05-17)
        "domains",                      # M013 domain frontmatter axis (2026-05-16)
        # Misfiled in NEVER_INJECTED until 2026-08-26: it is a real tuning
        # knob the calendar collector reads, not an operator-authored
        # structure, and it only entered config.example.yaml long after this
        # vault was installed.
        "calendar_skip_keywords",
        # M026 audio ingest via whisper.cpp (2026-05-28)
        "voice_transcribe_model",
        "voice_transcribe_language",
        "voice_transcribe_threads",
        "voice_transcribe_binary",
        "voice_transcribe_ffmpeg",
        "inbox_bridges",                # inbox-bridge rsync mirror (2026-05-28)
        "watched_folders",              # M027 watched-folder curiosity (2026-06-07)
        "exa_api_key",                  # Exa key; prefers .claude/.env (2026-05-31)
        "output_language",              # issue #4 compiled-prose language (2026-06-13)
    ),
    # M030 `wiki publish` (2026-08-25) — whole block is new; migrate_additions
    # creates the parent on first run. Token stays .env-only (no schema key).
    "publish": (
        "enabled",
        "endpoint",
        "wiki_slug",
        "wiki_name",
        "roots",                # M030-S04 ALLES widening (2026-08-25)
    ),
}

# Piggyback default blocks injected so the knob is visible/tunable in the
# operator's YAML. Values derive from _default_piggybacks().
INJECTED_PIGGYBACKS: tuple[str, ...] = (
    "calendar",             # M006 (2026-05-15)
    "curiosity_followup",   # consumer piggyback, backlog-corrective (2026-05-16)
    "dream_cycle",          # M014 (2026-05-16)
    "pictures",             # pictures collector (2026-05-17)
    "capture",              # M025 (2026-05-23)
    "study_run_due",        # M019 schedule dispatcher, default OFF (2026-05-17)
    "analyst_pass2",        # M019-S05 Pass-2 analyst, default OFF (2026-05-17)
    "publish",              # M030-S03 meinkontext-mirror cadence (2026-08-25)
    # Enabled-by-default daily job that no vault could see or retune — it sat
    # in NEVER_INJECTED with no stated justification at all (2026-08-26).
    "daily_digest_yesterday",
)

# Schema knobs the migration deliberately does NOT inject.
#
# This list used to justify itself with "pre-migration-era keys every operator
# config already carries from the install-time config.example.yaml copy". That
# premise was never checkable and was measurably FALSE: install.sh copies
# config.example.yaml into the vault exactly once, so a knob that entered
# config.example.yaml AFTER a vault was installed never reaches it, and
# NEVER_INJECTED guarantees no backfill. Eight such knobs were found running on
# hidden dataclass defaults on the live vault (2026-08-26) — including two
# halves of the compile retry ladder whose on/off switch WAS visible. Seven
# were moved to INJECTED_KEYS; the classes below are what remains, and each is
# something you can verify by reading the value's nature, not by assuming
# history:
#   - secrets and credentials — those belong in `.claude/.env`;
#   - per-install paths set once during setup;
#   - operator-authored structures (accounts, folder lists) where an injected
#     empty default would be noise, not a starting point;
#   - engine-internal tuning an operator has no basis to change (buffer sizes,
#     prompt-char ceilings) — visible in config.example.yaml as documentation.
# Explicit so the drift test can prove every schema knob has a policy, and
# frozen by tests/test_migrate_config_keys.py so a NEW knob can never be
# appended here by prefix-adjacency.
NEVER_INJECTED: dict[str, tuple[str, ...]] = {
    "models": (
        "compile_model",
        "compile_large_source_model",
        "ollama_url",
        "vision_model",
        "curiosity_model",
        "classify_model",
    ),
    "limits": (
        "compile_max_files",
        "compile_max_consecutive_failures",
        "flush_max_retries",
        "flush_retry_delay_seconds",
        "screenshot_resize_width",
        "screenshot_timeout_seconds",
        "curiosity_max_gaps",
        "curiosity_min_source_chars",
        "curiosity_timeout_s",
        "curiosity_max_prompt_chars",
        "curiosity_source_globs",
        "curiosity_folder_confidence_min",
        "curiosity_quote_min_anchor_tokens",
        "sparse_threshold_words",
        "youtube_max_frames",
        "youtube_max_duration_s",
        "youtube_frame_resize_width",
        "youtube_vision_timeout_s",
        "youtube_aggregate_timeout_s",
        "jamie_request_timeout_s",
        "jamie_max_per_run",
        "gmeet_request_timeout_s",
        "gmeet_max_per_run",
        "sdk_max_buffer_size_mb",
        "query_max_prompt_chars",
        "compile_max_prompt_chars",
        "compile_max_turns",
        "compile_retry_long_context_on_unknown",
    ),
    "scheduling": (
        "compile_after_hour",
        "dedup_window_seconds",   # value bump handled via VALUE_UPGRADES
        "timezone",
    ),
    "features": (
        "curiosity_loop",
        "vision_screenshots",
        "procmail_execution",
        "clippings_sweep",
    ),
    "graph_view": (
        "mode",
        "custom_search",
    ),
    "skills": (
        "global_install",
    ),
    "personal": (
        "primary_account",
        "accounts",               # operator-authored structure
        "email_folders",
        "curiosity_folders",
        "project_examples",
        "thunderbird_profile",
        "firefox_profile",
        "stg_backup_dir",
        "voice_inbox",
    ),
}

NEVER_INJECTED_PIGGYBACKS: tuple[str, ...] = (
    "email",                  # pre-migration-era; in every config since install
    "lint_structural",
    "review_wiki",
    "optimize_claude_md",     # force-disable handled via PIGGYBACK_FORCE_DISABLE
    "screenshots",
    "jamie",
    "gmeet",
    # Third class, distinct from the two above: designed to run block-less and
    # skip gracefully per account when no health sub-block exists
    # (config_schema `_default_piggybacks`). Injecting a block would state a
    # cadence for a job that may have nothing to collect.
    "health",
    "voice",
    "retry_failed_flushes",
)

# Keys introduced in newer engine versions that should be injected into the
# operator's config so they're visible/tunable. Structure: parent block name
# → {key: default_value}. Missing parent blocks are created. Keys already
# present (even with a different value) are left untouched. Values are
# DERIVED from core.config_schema — a default can never drift between the
# dataclass and the migration again.
KEY_ADDITIONS: dict[str, dict[str, object]] = {
    section: (
        {name: _piggyback_default(name) for name in INJECTED_PIGGYBACKS}
        if section == "piggybacks"
        else {name: _schema_default(section, name) for name in INJECTED_KEYS[section]}
    )
    for section in ("models", "limits", "scheduling", "features", "piggybacks",
                    "personal", "graph_view", "publish")
}

# Elements to add to existing list-valued config entries. Used when an
# engine update widens a list default (e.g. a new substrate type added to
# `compile_skip_substrate_types`). KEY_ADDITIONS only injects MISSING
# keys, so an operator who already pinned the list to the old default
# wouldn't otherwise pick up the new element. Structure: dotted parent.key
# path → list of elements to ensure are present. Idempotent: existing
# elements are left untouched. Missing parent block / missing key falls
# through to KEY_ADDITIONS for first-time injection.
LIST_ADDITIONS: dict[str, list[object]] = {
    # 2026-05-16: add `email-delta` to the skip-list. These 14-line
    # metadata files have no compile-extractable knowledge (actual
    # content arrives via curiosity/email-deep-scan); compile_main.md
    # was burning $2+ per file. Both new vaults (greenfield default)
    # and existing vaults (where the skip-list was emptied earlier
    # today) get the entry via this list-extend.
    # 2026-06-10 (M027-S02-T03): add `folder-index` — body-blind
    # watched-folder digests under raw/index/ are producer metadata,
    # nothing to distil; the 0.1.7 Skip route hash-records them so they
    # never re-list. raw/notes/folder/ answers stay compile sources
    # (NOT in this list).
    "limits.compile_skip_substrate_types": ["email-delta", "folder-index"],
    # 2026-06-14: widen intent-dispatch to the mobile picture channel.
    # The intent pass shipped voice-only (2026-06-13); operators who already
    # have `intent_source_globs: [raw/voice/*]` pinned wouldn't otherwise pick
    # up the new channel. Camera photos + phone screenshots both arrive via
    # personal.picture_inbox → raw/inbox-mobile/pictures/*.md (the .md sidecar
    # carries the vision text the classifier reads). Channel-based, not file-
    # type-based: desktop screenshots (raw/notes/screenshots/) stay out.
    "limits.intent_source_globs": ["raw/inbox-mobile/pictures/*.md"],
}

# Elements to REMOVE from existing list-valued config entries. The
# inverse of LIST_ADDITIONS — used when a list default narrows or an
# entry's old position is no longer correct (e.g. a substrate type
# moves out of compile_skip_substrate_types because it got a
# dedicated lean prompt). Structure: dotted parent.key path → list of
# elements to ensure are NOT present. Idempotent.
LIST_REMOVALS: dict[str, list[object]] = {
    # (2026-05-16 removed calendar-rollup + daily-digest from
    # compile_force_long_context_types here; that whole key was dropped
    # 2026-07-18 as a dead precedence-ladder knob — see KEY_DROPS.)
    # The P1 hotfix added calendar-rollup here to stop the burn;
    # P2 ships the actual fix (compile_calendar.md), so the skip is
    # no longer needed. Calendar files compile via the dedicated
    # prompt under an 8-turn budget at <$0.10/file.
    # 2026-05-18: memory-sync + memory-seed removed from skip-list as
    # part of the 2026-05-13 reversal (see DECISIONS). Memories are
    # first-class substrate again, distilled into knowledge/concepts/
    # via the two-mode compile_memories.md prompt. Skip-list entries
    # in operator vaults (added at some point during the wind-down)
    # short-circuited the dispatch BEFORE the substrate-handler ran.
    "limits.compile_skip_substrate_types": [
        "calendar-rollup", "memory-sync", "memory-seed",
    ],
}

# Fields whose backing dataclass entry was removed; their leftover entries
# in operator configs are silently ignored on load but linger as YAML cruft
# until pruned. Structure: parent block name → set of orphan field names.
KEY_DROPS: dict[str, set[str]] = {
    "limits": {
        # Removed 2026-05-23 — USD cost caps replaced by token/structural gates
        # (DECISIONS 2026-05-23; usage tracked in tokens per provider/model via
        # core/usage.py, never gated in dollars).
        "concept_reconcile_per_fact_max_cost_usd",
        "concept_reconcile_max_cost_per_run_usd",
        "compile_max_cost_per_file_usd",
        "dream_entity_max_cost_usd",
        "dream_cycle_max_cost_per_run_usd",
        # Removed 2026-06-10 (same-day amendment to M027-S02-T04) — the
        # write-time tree cap is gone; the digest is always the complete
        # inventory, prompt budget lives at the consumer (S03).
        "folder_index_max_tree_entries",
        # Removed 2026-06-13 (same day) — the relevance grep moved to
        # coverage+recency candidate ranking, which needs no structural
        # keyword pre-filter (a keyword matching all files adds uniform
        # coverage, no distortion). Transitional knob from the drop-based
        # selection that briefly shipped earlier today.
        "curiosity_folder_keyword_max_matches",
        # Removed 2026-07-18 (C13 interface-honesty sweep) — dead
        # precedence-ladder knobs. Every SUBSTRATE_PROMPTS row and the
        # default dispatch pin model + max_turns, so the config-side
        # long-context escalation tiers these three fed could never fire.
        # compile_large_source_model is KEPT (backs the kind=unknown retry).
        "compile_force_long_context_types",
        "compile_max_turns_long_context",
        "compile_large_source_chars",
    },
    "personal": {
        # Removed 2026-05-15 (M006) — calendar moved off Thunderbird-SQLite
        # to Google Calendar v3. These three were scan_calendar-only knobs
        # (year-counts report bucketing, work-keyword highlighting, output
        # language). `calendar_skip_keywords` is KEPT — the new collector
        # still consumes it for holiday-title filtering.
        "calendar_work_keywords",
        "calendar_categories",
        "calendar_report_language",
    },
}


def migrate_additions(data: dict) -> list[str]:
    """Inject missing keys from KEY_ADDITIONS under their parent block.

    Mutates `data` in place. Returns a list of human-readable change strings.
    """
    changes: list[str] = []
    for parent, keys in KEY_ADDITIONS.items():
        block = data.get(parent)
        if block is None:
            block = {}
            data[parent] = block
            changes.append(f"created empty {parent}: block")
        if not isinstance(block, dict):
            # Operator has something non-dict under this key — don't clobber.
            continue
        for key, default in keys.items():
            if key in block:
                continue
            block[key] = default
            changes.append(f"added {parent}.{key} = {default!r}")
    return changes


def migrate_list_additions(data: dict) -> list[str]:
    """Append missing elements to existing list-valued config entries.

    Only acts when the parent block AND the target key already exist as a
    list. Missing keys are left for KEY_ADDITIONS to inject with the engine
    default. Mutates `data` in place. Returns human-readable change strings.
    """
    changes: list[str] = []
    for path, additions in LIST_ADDITIONS.items():
        parent_name, _, key = path.partition(".")
        if not key:
            continue
        block = data.get(parent_name)
        if not isinstance(block, dict):
            continue
        existing = block.get(key)
        if not isinstance(existing, list):
            continue
        # Copy before mutating: migrate_additions assigns KEY_ADDITIONS
        # defaults by reference, so an in-place append here would mutate
        # the module-level default and leak into the next migrate_config
        # call (visible across pytest collection runs).
        new_list = list(existing)
        run_changes: list[str] = []
        for item in additions:
            if item in new_list:
                continue
            new_list.append(item)
            run_changes.append(f"appended {item!r} to {path}")
        if run_changes:
            block[key] = new_list
            changes.extend(run_changes)
    return changes


def migrate_list_removals(data: dict) -> list[str]:
    """Remove specified elements from existing list-valued config entries.

    Inverse of migrate_list_additions. Only acts when parent block AND
    target key exist as a list. Missing parent/key is a no-op. Mutates
    `data` in place; returns human-readable change strings.
    """
    changes: list[str] = []
    for path, removals in LIST_REMOVALS.items():
        parent_name, _, key = path.partition(".")
        if not key:
            continue
        block = data.get(parent_name)
        if not isinstance(block, dict):
            continue
        existing = block.get(key)
        if not isinstance(existing, list):
            continue
        # Copy before mutating — same module-level-default-leak concern
        # as migrate_list_additions.
        new_list = list(existing)
        run_changes: list[str] = []
        for item in removals:
            while item in new_list:
                new_list.remove(item)
                run_changes.append(f"removed {item!r} from {path}")
        if run_changes:
            block[key] = new_list
            changes.extend(run_changes)
    return changes


def migrate_drops(data: dict) -> list[str]:
    """Remove orphan keys whose backing dataclass field is gone.

    Mutates `data` in place. Returns a list of human-readable change strings.
    """
    changes: list[str] = []
    for parent, orphans in KEY_DROPS.items():
        block = data.get(parent)
        if not isinstance(block, dict):
            continue
        for field in sorted(orphans):
            if field in block:
                block.pop(field)
                changes.append(f"dropped orphan {parent}.{field} (dataclass field removed)")
    return changes


def migrate_account_additions(data: dict) -> list[str]:
    """Inject discoverable placeholders into per-account sub-blocks.

    The generic KEY_ADDITIONS table operates on top-level dataclass blocks
    (`limits`, `features`, …). Per-account additions live under
    `personal.accounts.<id>.…` and need bespoke walking; this function is
    the catch-all for that.

    Current additions:
      - M023 (2026-05-19): inject `health.healthkit` placeholder into any
        account that already carries `health.oura`. Operator opted into the
        health substrate when they configured Oura; the placeholder makes
        the second source discoverable without auto-enabling (empty
        `inbox_dir` keeps the collector silent for that account).
      - M024 (2026-05-21): inject `gmeet.email_discovery` (enabled / senders /
        folder / backfill_days) into any account with a `gmeet` block (kind
        gmeet-api) lacking it. Unlike healthkit this ships enabled — it's
        functional with defaults and bounded by the gemini-notes sender
        allowlist + the account's configured reader.
    """
    changes: list[str] = []
    personal = data.get("personal")
    if not isinstance(personal, dict):
        return changes
    accounts = personal.get("accounts")
    if not isinstance(accounts, dict):
        return changes
    for aid, body in accounts.items():
        if not isinstance(body, dict):
            continue
        health = body.get("health")
        if not isinstance(health, dict):
            continue
        if "oura" not in health:
            # Operator hasn't opted into the health substrate at all on this
            # account — don't auto-add the second source either.
            continue
        if "healthkit" in health:
            continue
        health["healthkit"] = {
            "kind": "healthkit-xml-export",
            "inbox_dir": "",       # operator fills in (empty = feature off)
            "filename": "Export.xml",
        }
        changes.append(
            f"injected personal.accounts.{aid}.health.healthkit "
            f"(M023, empty inbox_dir = opt-out)"
        )

    # M024 (2026-05-21): inject `gmeet.email_discovery` into any account with a
    # gmeet block (kind gmeet-api) lacking it. Email-discovery is the second
    # discovery source (colleague-shared meetings the own-Drive scan can't see);
    # it ships on-by-default for accounts that already opted into gmeet, gated by
    # the gemini-notes sender allowlist + each account's configured reader.
    for aid, body in accounts.items():
        if not isinstance(body, dict):
            continue
        gmeet_block = body.get("gmeet")
        if not isinstance(gmeet_block, dict) or gmeet_block.get("kind") != "gmeet-api":
            continue
        if "email_discovery" in gmeet_block:
            continue
        gmeet_block["email_discovery"] = {
            "enabled": True,
            "senders": ["gemini-notes@google.com"],
            "folder": "INBOX",
            "backfill_days": 30,
        }
        changes.append(
            f"injected personal.accounts.{aid}.gmeet.email_discovery (M024)"
        )

    return changes


def migrate_piggybacks(piggybacks: dict) -> tuple[dict, list[str]]:
    """Return (new_piggybacks_dict, list_of_change_descriptions)."""
    changes: list[str] = []
    out = dict(piggybacks)  # shallow copy — preserve key order as much as possible

    for old_key, new_key in PIGGYBACK_RENAMES.items():
        if old_key not in out:
            continue
        old_value = out.pop(old_key)
        if new_key is None:
            changes.append(f"dropped piggybacks.{old_key} (feature removed)")
            continue
        if new_key in out:
            # Both old and new present — new wins, old discarded (operator
            # already migrated this one; the stale key is just cruft).
            changes.append(f"dropped stale piggybacks.{old_key} (piggybacks.{new_key} already set)")
        else:
            out[new_key] = old_value
            changes.append(f"renamed piggybacks.{old_key} → piggybacks.{new_key}")

    # Engine-policy force-disable: flip an existing `enabled: true` to false,
    # keeping the rest of the block so the operator can see it + opt back in.
    for key in PIGGYBACK_FORCE_DISABLE:
        block = out.get(key)
        if isinstance(block, dict) and block.get("enabled") is True:
            block["enabled"] = False
            changes.append(f"disabled piggybacks.{key} (engine policy — was enabled)")

    # Dead-subkey pruning: remove knobs that no consumer reads (see
    # PIGGYBACK_SUBKEY_DROPS). The rest of the block is preserved.
    for key, subkeys in PIGGYBACK_SUBKEY_DROPS.items():
        block = out.get(key)
        if not isinstance(block, dict):
            continue
        for subkey in subkeys:
            if subkey in block:
                block.pop(subkey)
                changes.append(
                    f"dropped piggybacks.{key}.{subkey} (dead knob — the live cap is "
                    f"limits.{key}_max_per_run / the per-account sub-block)"
                )

    return out, changes


def migrate_model_upgrades(data: dict) -> list[str]:
    """Bump model values still pinned to a superseded engine default.

    Inverse intent of KEY_ADDITIONS (which only injects MISSING keys): this
    rewrites an EXISTING `models.<key>` whose value exactly equals a retired
    default. A model the operator deliberately pinned to something else is
    preserved — only the exact old-default string is touched.
    """
    models = data.get("models")
    if not isinstance(models, dict):
        return []
    changes: list[str] = []
    for key, mapping in MODEL_UPGRADES.items():
        cur = models.get(key)
        if isinstance(cur, str) and cur in mapping:
            models[key] = mapping[cur]
            changes.append(f"upgraded models.{key} {cur!r} → {mapping[cur]!r}")
    return changes


def migrate_value_upgrades(data: dict) -> list[str]:
    """Bump scalar config values still pinned to a superseded engine default.

    Like migrate_model_upgrades but for arbitrary "<parent>.<key>" scalars.
    Only an EXACT match of a retired default is rewritten; a deliberately-tuned
    value is preserved untouched.
    """
    changes: list[str] = []
    for path, mapping in VALUE_UPGRADES.items():
        parent_name, _, key = path.partition(".")
        if not key:
            continue
        block = data.get(parent_name)
        if not isinstance(block, dict):
            continue
        cur = block.get(key)
        # Guard bool (True == 1) so a boolean knob never matches an int default.
        if not isinstance(cur, bool) and cur in mapping:
            block[key] = mapping[cur]
            changes.append(f"upgraded {path} {cur!r} → {mapping[cur]!r}")
    return changes


# The domain list `scripts/lint.py` carried as a module constant until
# 2026-08-26. It was ONE operator's project names living in engine code — the
# knob that was supposed to hold them (graph_view.domain_tags) sat in
# NEVER_INJECTED, so no vault could ever set it and the fallback became the
# de-facto behaviour. Writing it into the config of a vault that predates the
# knob preserves that behaviour exactly; fresh installs carry
# `domain_tags: []` from config.example.yaml and are left alone.
_LEGACY_LINT_DOMAIN_TAGS: list[str] = [
    "fleet", "openclaw", "claude-code", "yesterday", "llm-wiki",
    "paperclip", "ytstack", "township", "pixeltales", "lxw",
]


def migrate_domain_tags_seed(data: dict) -> list[str]:
    """Seed `graph_view.domain_tags` on vaults that never had the key.

    Only when ABSENT — an operator who set it (including to an empty list)
    keeps their choice.
    """
    gv = data.get("graph_view")
    if not isinstance(gv, dict):
        gv = {}
        data["graph_view"] = gv
    if "domain_tags" in gv:
        return []
    gv["domain_tags"] = list(_LEGACY_LINT_DOMAIN_TAGS)
    return [
        "seeded graph_view.domain_tags with the list lint.py used to hardcode "
        f"({len(_LEGACY_LINT_DOMAIN_TAGS)} tags) — edit it to match your own domains"
    ]


def migrate_config(config_path: Path) -> tuple[str | None, list[str]]:
    """Return (new_yaml_text_or_None, changes). None text → no change needed."""
    if not config_path.exists():
        log.error("config.yaml not found: %s", config_path)
        return None, []

    raw = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}

    changes: list[str] = []

    # Piggyback renames / removals (only if the operator has a piggybacks
    # block at all — fresh installs and pre-piggyback configs skip this).
    if isinstance(data.get("piggybacks"), dict):
        new_piggybacks, pb_changes = migrate_piggybacks(data["piggybacks"])
        if pb_changes:
            data["piggybacks"] = new_piggybacks
            changes.extend(pb_changes)

    # Legacy domain-tag seed. MUST run before migrate_additions, which would
    # otherwise inject the schema default (an empty list) and lock the vault
    # out of the seed.
    changes.extend(migrate_domain_tags_seed(data))

    # Key additions — backfill new knobs under their parent block so they're
    # visible to the operator. Runs unconditionally; entries already present
    # are left untouched.
    changes.extend(migrate_additions(data))

    # Per-account additions — inject discoverable placeholders into
    # `personal.accounts.<id>` sub-blocks (these aren't top-level keys, so
    # the generic KEY_ADDITIONS path can't reach them).
    changes.extend(migrate_account_additions(data))

    # List-element additions — widen existing list-valued knobs (e.g. when
    # a new substrate type joins compile_skip_substrate_types). Must
    # run after migrate_additions so a freshly-injected list also gets
    # any LIST_ADDITIONS for it (idempotent: already-present entries are
    # untouched).
    changes.extend(migrate_list_additions(data))

    # List-element removals — narrow list-valued knobs (e.g. when a
    # substrate type leaves the skip-list because its dedicated prompt
    # landed). Runs after additions so a freshly-injected list with the
    # NEW default gets pruned correctly if the operator's old config had
    # extra entries.
    changes.extend(migrate_list_removals(data))

    # Orphan-field drops — prune entries whose backing dataclass field is
    # gone, otherwise they live forever in operator YAML as silent cruft.
    changes.extend(migrate_drops(data))

    # Model-version upgrades — bump models.* values still on a retired default
    # (opus 4-7 → 4-8) so existing vaults don't stay frozen on the old default.
    changes.extend(migrate_model_upgrades(data))

    # Scalar value upgrades — bump other retired-default scalars (e.g.
    # scheduling.dedup_window_seconds 60 → 900) the same way.
    changes.extend(migrate_value_upgrades(data))

    if not changes:
        return None, []

    # PyYAML round-trip drops comments — config.yaml is operator-owned and
    # already documents this trade-off (see wiki config CLI note).
    new_text = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return new_text, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--vault", type=str, required=True,
                        help="Path to the vault root (config.yaml lives at <vault>/.wiki/config.yaml)")
    parser.add_argument("--apply", action="store_true",
                        help="Write the migrated config (default: preview only)")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser()
    config_path = vault / ".wiki" / "config.yaml"

    new_text, changes = migrate_config(config_path)

    if not changes:
        log.info("config.yaml is already on the current key schema — no change.")
        return 0

    log.info("Changes for %s:", config_path)
    for c in changes:
        log.info("  - %s", c)

    if not args.apply:
        log.info("Preview only. Re-run with --apply to write.")
        return 0

    # Round-robin backup via the shared core.config_backup helper — the same
    # location/naming/keep-count as engine writes (`wiki config set`).
    backup = backup_config_file(config_path)
    if backup is not None:
        log.info("Backed up → %s", backup.relative_to(config_path.parent))
    else:
        log.warning("Backup failed (continuing) — check %s permissions", config_path.parent)

    config_path.write_text(new_text, encoding="utf-8")
    log.info("Wrote migrated config.yaml (%d change(s)).", len(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
