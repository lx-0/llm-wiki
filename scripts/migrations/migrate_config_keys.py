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
  limits.piggyback_max_runtime_s             (added 2026-05-30, default 14400 — hard wall-clock cap the piggyback runner enforces on each spawned task; backstop against the review-wiki 19h half-open-socket hang)
  limits.review_ollama_timeout_s             (added 2026-05-30, default 300 — per-article Ollama read timeout for review-wiki.py, lifted from a module constant)
  limits.review_consecutive_failure_abort    (added 2026-05-30, default 5 — review-wiki aborts the sweep after N consecutive Ollama failures instead of grinding 1700×timeout when kcma is down)
  limits.review_checkpoint_every             (added 2026-05-30, default 25 — review-wiki writes the partial report every N articles so an aborted/killed sweep isn't lost)
  limits.dedup_fuzzy_threshold               (added 2026-05-31, default 0.85 — `wiki dedup` fuzzy-title match floor for duplicate-candidate proposal)
  features.dream_web_research                (added 2026-05-31, default False — Exa-AI public-entity enrichment dream post-pass; issue #2)
  scheduling.web_research_cooldown_days      (added 2026-05-31, default 30 — `## Public Profile` refresh cooldown)
  personal.exa_api_key                       (added 2026-05-31, default "" — Exa AI key; falls back to env EXA_API_KEY)
  personal.accounts.<id>.health.healthkit    (added 2026-05-19 M023 — Apple HealthKit XML export ingest;
                                              injected as a placeholder into any account already carrying
                                              `health.oura`, kind: healthkit-xml-export, empty inbox_dir
                                              = opt-out; operator fills in the iCloud / vault path)

Idempotent: a config already on the current schema produces no change.

Usage:
    uv run python scripts/migrations/migrate_config_keys.py --vault PATH            # preview
    uv run python scripts/migrations/migrate_config_keys.py --vault PATH --apply    # write
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("migrate-config-keys")

# old_key → new_key (rename, value preserved). new_key=None → drop the block.
PIGGYBACK_RENAMES: dict[str, str | None] = {
    "follow_requests": "curiosity_followup",
    "scan_screenshots": "screenshots",
    "email_incremental": "email",
    "sync_memories": None,  # feature removed 2026-05-13
}

# Keys introduced in newer engine versions that should be injected into the
# operator's config so they're visible/tunable. Structure: parent block name
# → {key: default_value}. Missing parent blocks are created. Keys already
# present (even with a different value) are left untouched.
KEY_ADDITIONS: dict[str, dict[str, object]] = {
    "models": {
        # M014 dream-cycle model. Default [1m] up-front — dream-entity is
        # a fan-out workload that blows standard 200K Opus context mid-stream
        # (see KNOWLEDGE.md "tool-turn ballooning"). Set to "" to fall back
        # to models.compile_model. Added 2026-05-18.
        "dream_model": "claude-opus-4-7[1m]",
        # M027-S04 folder-scan answer provider (Q9 seam). claude-sdk is
        # the only provider today; local LLM/agent later. Unknown values
        # raise loudly — no silent fallback. Added 2026-06-10.
        "folder_scan_provider": "claude-sdk",
    },
    "limits": {
        # M027 watched-folder relevance grep: drop source keywords that
        # match more than N file-paths (structural noise, not topic
        # selectors). Only rare/discriminative keywords select which
        # file-lines get injected. Added 2026-06-13 after lxw showed the
        # producer over-matching generic keywords (admin/kosten/cloud).
        "curiosity_folder_keyword_max_matches": 30,
        # M027 watched-folder candidate retrieval: over budget, inject the
        # top-N rarity-ranked candidate files (not the folder tree). Added
        # 2026-06-13 — the full dir-skeleton bloated the prompt and timed
        # out the local 8B model at 240s.
        "curiosity_folder_max_candidates": 40,
        # M014 dream-cycle per-message stall timeout. Added 2026-05-18
        # after paperclip-companies crashed at 339s on [1m] with empty
        # stderr — diagnostic instrumentation + structural alignment
        # with compile_per_call_timeout_s. See KNOWLEDGE.md.
        "dream_per_call_timeout_s": 300,
        # Empty by default since 2026-05-16 P2: daily-digest and
        # calendar-rollup moved to dedicated lean prompts in
        # SUBSTRATE_PROMPTS (compile.py). No remaining substrate
        # legitimately needs [1m] up-front; the 50 KB size-threshold
        # is the right escape hatch for large sources.
        "compile_force_long_context_types": [],
        # Treat kind=unknown failures with no further retry path (small
        # source OR already on [1m]) as skips instead of hard failures.
        # Preserves the consecutive-failure budget so the batch survives
        # a structurally-unprocessable file.
        "compile_skip_on_long_context_unknown": True,
        # Circuit-breaker for aggregated-memory chunked compiles (2026-05-17).
        # When N consecutive chunks fail (skipped OR failed), abort the
        # rest of the chunk loop. Stops runaway $-burn on broken
        # substrate-prompt × N-chunk fan-out (per-file cost guard fires
        # per-chunk, not cumulatively). Set 0 to disable.
        "compile_aggregated_max_consecutive_failures": 3,
        # M007-S01-T02 (2026-05-16): When true (default), files without
        # explicit `compile_role:` frontmatter get a role inferred from
        # their top-level segment (raw/daily/inbox/knowledge → source-only).
        # Set false to require explicit frontmatter on every file (useful
        # if you have non-standard top-level folders).
        "compile_role_default_by_location": True,
        # Google Calendar collector (M006, 2026-05-15). Per-HTTP-call timeout
        # against calendar.googleapis.com / per-calendar event cap / past +
        # future windows in days. Match the dataclass defaults in
        # `scripts/core/config.py:Limits.calendar_*`.
        "calendar_request_timeout_s": 30,
        "calendar_max_per_run": 500,
        "calendar_backfill_days": 90,
        "calendar_future_days": 7,
        # Higher max_turns for force-long-context substrates (2026-05-16).
        # Default 12 ran out partway through dense calendar-rollup days
        # with 6+ attendees, hit `subtype=error_max_turns` and burned
        # ~$3-4/attempt at [1m] pricing. 30 covers the realistic depth.
        "compile_max_turns_long_context": 30,
        # Per-file cost guard (USD); abort batch on overrun. Defense
        # against substrate-prompt-mismatch loops that burn $5-10/file
        # silently. See KNOWLEDGE.md "calendar-rollup max_turns trap".
        "compile_max_tokens_per_file": 500_000,
        # Substrate-skip-list for batch mode (frontmatter `type:` values).
        # Empty default since 2026-05-16 P2 landed (calendar-rollup
        # moved out of the skip-list once compile_calendar.md prompt
        # shipped). Last-resort escape hatch for substrate types with
        # no good prompt yet. folder-index added 2026-06-10 (M027-S02
        # body-blind watched-folder digests — metadata, nothing to distil).
        "compile_skip_substrate_types": ["email-delta", "folder-index"],
        # Watched-folder index knobs (M027-S02-T04, `wiki index`). Match
        # Limits.folder_index_* defaults in scripts/core/config.py.
        # max_depth 0 = unlimited (2026-06-10 reversal — complete
        # inventory; raise per-install only for huge NAS roots).
        "folder_index_max_depth": 0,
        "folder_index_recent_n": 20,
        # Email daily-rollup signal (beta, 2026-05-23). Top-N senders + sample
        # of recent subjects in the per-account daily/<date>/email.md block, so
        # the daily-digest agent extracts correspondents + themes. Match
        # Limits.daily_email_* defaults in scripts/core/config.py.
        "daily_email_top_senders": 5,
        "daily_email_sample_subjects": 12,
        # Per-class flush-context budgets (hooks/_transcript.py). Replaces
        # the content-blind globals MAX_TURNS=30 + MAX_CONTEXT_CHARS=15_000
        # that lost assistant analytical prose to tool-summary truncation.
        # See KNOWLEDGE.md "Flush context — Karpathy/Cole pattern gen-2".
        "flush_assistant_text_budget_chars": 50_000,
        "flush_user_text_budget_chars": 10_000,
        "flush_tool_summary_budget_chars": 10_000,
        # Per-compile-call timeout (seconds). Guards against bundled-CLI
        # HANG (vs crash — crashes already retry/abort). One stuck file
        # otherwise blocks every remaining file in the batch. On timeout:
        # log WARNING, _skipped (preserves consecutive-failure budget).
        # Match Limits.compile_per_call_timeout_s default in
        # `scripts/core/config.py`.
        "compile_per_call_timeout_s": 600,
        # M019 (2026-05-17): default lookback window for operator-self-report
        # instruments (PHQ-9, GAD-7, ASRS-v1.1, WHO-5, MEQ-19 in the wedge).
        # 14 days = standard clinical reference window for the PHQ/GAD family.
        # Per-instrument override via `inference.default_lookback_days` field
        # in instrument.yaml.
        "reports_default_lookback_days": 14,
        # M012 (2026-05-16): connection-article quality gate. Body word
        # count below this floor fires `connection_shallow_body` in lint;
        # 50 was chosen because anything shorter empirically just restates
        # the linked concepts without asserting a real mechanism.
        "connection_min_words": 50,
        # M011 takes substrate (2026-05-16).
        "extract_takes_source_globs": [
            "raw/transcripts/*",
            "raw/transcripts/**/*",
            "raw/voice/*",
            "daily/*",
        ],
        "extract_takes_timeout_s": 180,
        "extract_takes_max_per_source": 12,
        # M014 dream-cycle cost gates (2026-05-16). Pre-flight per-entity
        # USD cap (estimate from prompt-char count; reject SDK call if over)
        # + cumulative per-run cap for `wiki dream --all-entities` and the
        # dream_cycle piggyback sweep. Match Limits.dream_*_usd defaults
        # in `scripts/core/config.py`.
        "dream_entity_max_prompt_chars": 415_000,
        "dream_cycle_max_tokens_per_run": 2_000_000,
        # M016 dream-cycle sampled-activation knobs (2026-05-17). Bound the
        # per-dream corpus by construction (~600 KB) regardless of vault size.
        # See `.ytstack/backlog/dream-sampled-activation.md` for the full
        # 4-tier architecture + research grounding.
        "dream_tier1_recent_count": 20,
        "dream_tier1_digest_days": 7,
        "dream_tier2_sample_count": 50,
        # Concept-reconciliation routine (2026-05-22). Cost caps + turn budget
        # for the autonomous `wiki reconcile` strict correct_apply.
        # See `.ytstack/backlog/concept-consistency-routine.md`.
        "concept_reconcile_max_files_per_fact": 25,
        "concept_reconcile_max_facts_per_run": 10,
        "concept_reconcile_max_turns": 15,
        # Health-trend synthesis (2026-05-23). Recent-window + min-coverage for
        # `wiki health-trends`. See `.ytstack/backlog/health-trend-synthesis.md`.
        "health_trends_recent_months": 6,
        "health_trends_min_coverage_days": 10,
        # voice-punctuate Ollama timeout (2026-05-28). gemma4:e4b
        # cold-call into VRAM regularly hits 30–40 s; pre-2026-05-28
        # hardcoded 30 s tripped on every first call after a quiet
        # period. 120 s mirrors the chat() default.
        "voice_punctuate_timeout_s": 120,
        # Reliability bundle (2026-05-30) — bounds the half-open-socket hang
        # class that left review-wiki running 19h47m on a slept LAN GPU.
        # See KNOWLEDGE.md "Ollama half-open socket". Match Limits defaults in
        # scripts/core/config.py.
        "ollama_connect_timeout_s": 10,
        "piggyback_max_runtime_s": 14_400,
        "review_ollama_timeout_s": 300,
        "review_consecutive_failure_abort": 5,
        "review_checkpoint_every": 25,
        # `wiki dedup` (entity-dedup, issue #3, 2026-05-31). Fuzzy-title match
        # floor for duplicate-candidate proposal. Match Limits.dedup_fuzzy_threshold
        # default in scripts/core/config.py.
        "dedup_fuzzy_threshold": 0.85,
    },
    "scheduling": {
        # M014 dream-cycle (2026-05-16). Per-entity cooldown — entities
        # synthesized within this window are skipped by sweep + piggyback.
        # Match Scheduling.dream_cooldown_days default in
        # `scripts/core/config.py`.
        "dream_cooldown_days": 7,
        # M017 (2026-05-17): config-driven entity priority for dream-cycle
        # selection. Empty defaults preserve M014 behavior (greedy by age).
        # Operator populates paths/domain/tags/status to bias selection.
        # See `.ytstack/backlog/dream-priority-config.md` for full spec.
        "dream_priority": {
            "default": 1.0,
            "paths": {},
            "domain": {},
            "tag_strategy": "max",
            "tags": {},
            "status": {},
        },
        # Concept-reconciliation routine (2026-05-22). Per-fact cooldown —
        # facts reconciled within this window are skipped. Match
        # Scheduling.concept_reconcile_cooldown_days in config.py.
        "concept_reconcile_cooldown_days": 14,
        # Dream web-research (issue #2, 2026-05-31). Per-entity `## Public
        # Profile` refresh cooldown. Match Scheduling.web_research_cooldown_days.
        "web_research_cooldown_days": 30,
        # Insufficient-corpus backoff cap (2026-06-02). Match
        # Scheduling.dream_insufficient_corpus_backoff_max_days in config.py.
        "dream_insufficient_corpus_backoff_max_days": 30,
    },
    "features": {
        # M011 master switch — default OFF, flip True after dogfooding.
        "extract_takes": False,
        # Dream web-research (issue #2, 2026-05-31) — default OFF. Makes an
        # EXTERNAL paid Exa API call; doubly gated by this flag + per-entity
        # opt-in. Match Features.dream_web_research in config.py.
        "dream_web_research": False,
        # Concept-reconciliation routine (2026-05-22) — default OFF. Makes
        # scoped autonomous writes to knowledge/concepts/; opt in after a
        # `wiki reconcile --dry-run` review. See backlog doc.
        "concept_reconciliation": False,
        # Health-trend synthesis (2026-05-23) — deterministic + $0, default OFF.
        # When True, `wiki health-trends` writes the trends block + the
        # health_trends piggyback runs. See health-trend-synthesis.md.
        "health_trends": False,
        # 2026-05-17 voice-punctuation pre-process. Calls Ollama
        # classify_model on every voice ingest to add punctuation +
        # German-noun-case to dictation transcripts. Raw text preserved
        # in `raw_transcript:` frontmatter. Default True; flip False if
        # your dictation tool already punctuates or you want to skip
        # the extra LLM call.
        "voice_punctuate": True,
        # 2026-05-17 Producer-seam arc. Source-glob allowlist for the
        # suggestions post-pass. Default mirrors the legacy hardcoded
        # `_is_email_source` filter; widening the list enables suggestions
        # for additional substrates without code changes.
        "suggestions_source_globs": ["raw/email/*.md"],
        # 2026-05-17 Path-scope enforcement via `can_use_tool` callback.
        # Replaces the decorative `Write(knowledge/**)` /
        # `Edit(knowledge/**)` syntax in `--allowedTools` (bundled CLI
        # parses it as bare Write/Edit, verified by
        # `scripts/probe_compile_scope.py`). When True the compile + dream
        # agents run in streaming mode with a Python-side gate; when False
        # they use the legacy decorative allowlist (kept as a one-line
        # rollback path while the streaming-mode rewrite proves itself
        # under production load). Default True.
        "compile_callback_gate": True,
        # M020 backlinks footer — corpus-wide post-compile pass that writes a
        # sentinel-managed `## Backlinks` block into every knowledge/<article>
        # so AI agents reading raw markdown get incoming-link information
        # without a corpus-wide ripgrep. Idempotent. Flip false to skip the
        # sweep. Default True.
        "materialize_backlinks": True,
        # Relativize-wikilinks pass (2026-05-29) — corpus-wide post-compile
        # rewrite of every wikilink to a path relative to its containing
        # article, so Obsidian resolves cross-article links from nested
        # folders instead of creating empty stubs. Idempotent. Default True.
        "relativize_wikilinks": True,
        # Per-picture deterministic metadata extraction (2026-05-29) — EXIF
        # via Pillow + Android-screenshot filename pattern. Adds
        # captured_at / device / location / shot / app_context frontmatter
        # to each pictures-collector sidecar. Default True; graceful no-op
        # when source carries no EXIF and isn't an Android screenshot.
        "extract_picture_metadata": True,
        # M019 operator-self-reports master switch (2026-05-17). When True,
        # `wiki study run` + `wiki analyze` are wired and flush.py piggybacks
        # for Pass-1 / Pass-2 fire. Default OFF — flip True after S05 lands
        # and dogfooding completes. Air-gapped from the compile loop.
        "operator_reports": False,
        # Pre-flight no-op skip for dream-entity passes with ZERO
        # entity-specific substrate (2026-05-31). When the corpus is only
        # date-pulled daily digests that don't mention the entity, the
        # synthesis is a guaranteed INSUFFICIENT_CORPUS no-op yet still bills a
        # full prompt-cache write (~$0.80). True → skip the SDK call for $0.
        # Match Features.dream_require_entity_substrate in config.py.
        "dream_require_entity_substrate": True,
    },
    "piggybacks": {
        # M006 calendar collector — mirrors gmeet / jamie 6 h cadence.
        # Per-account override lives in personal.accounts.<id>.calendar; the
        # piggyback block here is the cooldown / batch-cap, not the auth
        # state. An account without a kind=google-calendar sub-block silently
        # skips the run.
        "calendar": {"enabled": True, "cooldown_hours": 6, "max_per_run": 500},
        # 2026-05-16: curiosity-consumer piggyback. Producer (compile.py)
        # writes raw/requests/request-*.json after every compile;
        # consumer (curiosity/cli.py --run-batch N) processes them via
        # mailbox scan. Backlog-corrective default — drains 20/day
        # (max_per_run × 4 fires) which beats the typical generation rate
        # without thundering-herd on long backlogs.
        # Was missed by the original P2 rollout of curiosity-consumer-gap;
        # operator configs from before 2026-05-16 have NO curiosity_followup
        # block at all, so requests accumulate in raw/requests/ forever.
        "curiosity_followup": {"enabled": True, "cooldown_hours": 6, "max_per_run": 5},
        # M014 dream-cycle piggyback (2026-05-16). Cooldown 24h means at
        # most once-per-day fires; per-fire sweeps `max_per_run` entities
        # (3 default) selected newest-overdue first. Per-entity cost cap
        # AND per-run cumulative cost cap enforced inside dream.py.
        "dream_cycle": {"enabled": True, "cooldown_hours": 24, "max_per_run": 3},
        # 2026-05-17 pictures collector. Vision-LLM-driven, mirrors the
        # screenshots cadence shape (max_per_run cap) but lighter cooldown
        # because iCloud-Shortcut drops arrive throughout the day. Silently
        # skipped when personal.picture_inbox is empty (graceful agnostic).
        "pictures": {"enabled": True, "cooldown_hours": 6, "max_per_run": 20},
        # M025 (2026-05-23) quick-capture collector. Folder-watch like voice,
        # 1h cadence, no per-run cap. Registry auto-discovers the collector;
        # this block is the operator-overridable enabled/cooldown knob. Silently
        # skipped when personal.capture_inbox is empty.
        "capture": {"enabled": True, "cooldown_hours": 1},
        # M019 operator-self-reports schedule dispatcher. 6h cooldown
        # checks 4×/day for due studies; the study's own schedule
        # (weekly/monthly/quarterly) gates the actual run. Default OFF
        # until S05 ships and operator flips features.operator_reports.
        "study_run_due": {"enabled": False, "cooldown_hours": 6},
        # M019-S05 Pass-2 analyst — cross-study synthesist. Pass-1 runs
        # automatically inside `wiki study run`; Pass-2 runs weekly on
        # its own cadence (or on-demand via `wiki analyze --cross-study-only`).
        "analyst_pass2": {"enabled": False, "cooldown_hours": 168},
    },
    "personal": {
        # 2026-05-16 author-attribution feature. Null default keeps the
        # multi-tenant story intact — operators on single-tenant vaults set
        # this to their own name (e.g. "alex") so compile.py routes
        # unattributed beliefs/decisions to their `knowledge/people/<name>.md`
        # page. Explicit `author:` frontmatter on a source file always
        # overrides. See `.ytstack/backlog/author-attribution.md`.
        "implicit_operator_author": None,
        # 2026-05-17 pictures collector. Mirrors voice_inbox shape — operator
        # sets to a folder iOS Shortcut (or similar) drops photos into; the
        # collector folder-watches it, runs gemma4 vision on each file, and
        # archives the source under <picture_inbox>/.processed/. Empty
        # default keeps the multi-tenant story intact.
        "picture_inbox": "",
        # M025 (2026-05-23) quick-capture-correction loop. Operator one-taps
        # cryptic notes into this folder; collectors/capture_collector.py
        # folder-watches it, content-IDs each capture, and writes
        # raw/captures/capture-<id>.md. Empty default keeps the multi-tenant
        # story intact (collector silently skips).
        "capture_inbox": "",
        # M019 (2026-05-17) operator-self-reports surface location. Directory
        # under vault root where reports/studies/ + reports/analyses/ live.
        # Sibling of knowledge/, separate from .wiki/ (engine state).
        "reports_dir": "reports",
        # M013 (2026-05-16): optional `domain:` frontmatter axis on knowledge/
        # articles. Cross-cutting life-domain tag (NOT a folder), extensible
        # per vault. Lint warns on values outside this enum (grace period).
        # `wiki query --domain X` filters to articles whose `domain:` matches.
        # Default lifted from lx-vault audit (Company / Personal / AI top-
        # level split). See `.ytstack/backlog/domain-frontmatter.md`.
        "domains": ["company", "personal", "ai", "meta"],
        # (2026-05-28) audio transcription via whisper.cpp. Empty model
        # path keeps audio-ingest off; text dictation continues to work
        # regardless. Operator pre-reqs: brew install whisper-cpp + download
        # a ggml model file. See AGENTS.md voice-intake section.
        "voice_transcribe_model": "",
        "voice_transcribe_language": "auto",
        "voice_transcribe_threads": 4,
        "voice_transcribe_binary": "",
        "voice_transcribe_ffmpeg": "",
        # 2026-05-28 inbox-bridge. Empty default keeps the feature off — operator
        # populates with {remote, local, mode?, enabled?, name?} dicts to mirror
        # network-mounted / sandbox-restricted intake folders into local paths
        # the substrate collectors then folder-watch. See `wiki bridge --help`.
        "inbox_bridges": [],
        # M027 (2026-06-07) watched-folder curiosity. Empty default keeps the
        # feature off — operator populates with {id, kind: local|smb, path|share}
        # dicts naming folders the curiosity loop may index + (on per-request
        # approval) read. Validated by config._validate_watched_folders_schema.
        "watched_folders": [],
        # Dream web-research (issue #2, 2026-05-31). Exa AI key — empty default
        # keeps the feature inert; falls back to env EXA_API_KEY. Prefer setting
        # it in the vault's .claude/.env, not config.yaml. Match
        # Personal.exa_api_key in config.py.
        "exa_api_key": "",
    },
}

# Elements to add to existing list-valued config entries. Used when an
# engine update widens a list default (e.g. a new substrate type added to
# `compile_force_long_context_types`). KEY_ADDITIONS only injects MISSING
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
}

# Elements to REMOVE from existing list-valued config entries. The
# inverse of LIST_ADDITIONS — used when a list default narrows or an
# entry's old position is no longer correct (e.g. a substrate type
# moves out of compile_force_long_context_types because it got a
# dedicated lean prompt). Structure: dotted parent.key path → list of
# elements to ensure are NOT present. Idempotent.
LIST_REMOVALS: dict[str, list[object]] = {
    # 2026-05-16 — substrate-aware prompt dispatch landed
    # (SUBSTRATE_PROMPTS in compile.py). Both daily-digest and
    # calendar-rollup now have dedicated lean prompts that don't
    # need [1m] up-front; the size-threshold escape hatch handles
    # genuinely large sources. Clean these out of operator configs
    # that picked them up during the brief P1 hotfix window.
    "limits.compile_force_long_context_types": ["daily-digest", "calendar-rollup"],
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

    return out, changes


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

    # Key additions — backfill new knobs under their parent block so they're
    # visible to the operator. Runs unconditionally; entries already present
    # are left untouched.
    changes.extend(migrate_additions(data))

    # Per-account additions — inject discoverable placeholders into
    # `personal.accounts.<id>` sub-blocks (these aren't top-level keys, so
    # the generic KEY_ADDITIONS path can't reach them).
    changes.extend(migrate_account_additions(data))

    # List-element additions — widen existing list-valued knobs (e.g. when
    # a new substrate type joins compile_force_long_context_types). Must
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

    if not changes:
        return None, []

    # PyYAML round-trip drops comments — config.yaml is operator-owned and
    # already documents this trade-off (see wiki config CLI note).
    new_text = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return new_text, changes


# Mirror of scripts/core/config.py's round-robin backup. The migration is
# standalone (vault-parametrised via --vault) and must NOT import config.py —
# that module runs `load()` at import time against the global CONFIG_FILE, which
# need not be the vault we're migrating. So we replicate the location + naming +
# keep-count here so migration backups land in the SAME place as engine writes.
_CONFIG_BACKUP_KEEP_LAST = 10


def _backup_config(config_path: Path) -> str | None:
    """Snapshot config_path into <.wiki>/state/config-backups/ before overwrite.

    Matches scripts/core/config.py: `config-<UTC-ts>.yaml`, keeps the last
    _CONFIG_BACKUP_KEEP_LAST, prunes older. Returns the backup name or None.
    """
    bdir = config_path.parent / "state" / "config-backups"
    bdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = bdir / f"config-{ts}.yaml"
    if out.exists():
        out = bdir / f"config-{ts}-{datetime.now(timezone.utc).microsecond:06d}.yaml"
    shutil.copy2(config_path, out)

    existing = sorted(bdir.glob("config-*.yaml"))
    if len(existing) > _CONFIG_BACKUP_KEEP_LAST:
        for stale in existing[: -_CONFIG_BACKUP_KEEP_LAST]:
            try:
                stale.unlink()
            except OSError:
                pass
    return str(out.relative_to(config_path.parent))


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

    backup = _backup_config(config_path)
    log.info("Backed up → %s", backup)

    config_path.write_text(new_text, encoding="utf-8")
    log.info("Wrote migrated config.yaml (%d change(s)).", len(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
