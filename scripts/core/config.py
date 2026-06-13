"""Single source of truth for tunable wiki-system parameters.

Reads `<vault>/.wiki/config.yaml` once at import time. Falls back to dataclass
defaults when the file or individual keys are missing. Module-level
singleton `CONFIG` is the API — import it from any script.

Usage:
    from core.config import CONFIG
    if CONFIG.features.curiosity_loop:
        ...
    timeout = CONFIG.limits.screenshot_timeout_seconds

Run this file directly to dump the loaded config (useful for debugging):
    uv run python scripts/core/config.py

Side effect on import: loads `<vault>/.claude/.env` via python-dotenv (so
every script that imports CONFIG gets secret env vars without manual shell
export) and derives `TIMEZONE` from `CONFIG.scheduling.timezone`. Pure path
constants live in `core/paths.py`; the datetime helpers in `core/utils.py`.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# config.py is both a package member (`from core.config import CONFIG`) AND a
# direct CLI (`wiki config` → `python scripts/core/config.py`). The bootstrap
# makes `from core.paths import …` resolve in the __main__ case too — relative
# `from .paths import` would raise "no known parent package" when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import CONFIG_FILE, DOTENV_FILE  # noqa: E402

# ── .env bootstrap ─────────────────────────────────────────────────────
# Loaded once at import time, before CONFIG is built. Idempotent (load_dotenv
# is itself idempotent). override=False — a shell export already in the env
# wins; .env is the fallback, not the authority. Missing file: graceful
# no-op (fresh-install vaults ship only `.env.example`).
load_dotenv(DOTENV_FILE, override=False)


@dataclass
class DreamPriority:
    """M017 — config-driven dream-cycle entity priority weighting.

    Operator-shaped selection priority for the dream-cycle piggyback (and
    `wiki dream --all-entities` sweeps). Replaces M014's "pick N most-overdue"
    greedy default with operator-tunable rules-based weighted-selection.

    Resolution order (most-precise wins):
      1. Per-entity frontmatter `dream_priority:` (absolute precedence)
      2. `paths:` glob/exact match (first-match wins via fnmatch)
      3. Formula: default × domain_multiplier × tag_multiplier_via_strategy
         × status_multiplier  (each multiplier defaults to 1.0 when axis
         isn't configured or entity doesn't have that axis value)

    Selection weight = priority × age_days_since_last_synth × jitter(0.85, 1.15).
    Entities with computed priority of 0 are excluded from auto-selection
    (operator must run them manually). Cooldown still applies independently.

    Full spec: `.ytstack/backlog/dream-priority-config.md`.
    """

    # Base weight when nothing more-specific matches
    default: float = 1.0

    # Path/glob → weight overrides. First match wins (fnmatch semantics).
    # Vault-relative paths (e.g. "knowledge/people/alex.md",
    # "knowledge/areas/personal-*-archived.md"). Use weight 0 to exclude
    # an entity (or path-glob of entities) from auto-selection entirely.
    paths: dict[str, float] = field(default_factory=dict)

    # Domain-axis multipliers (M013 `domain:` frontmatter).
    # Applied multiplicatively to the resolved base weight.
    domain: dict[str, float] = field(default_factory=dict)

    # Tag-axis multipliers. Strategy below controls multi-tag handling.
    tags: dict[str, float] = field(default_factory=dict)

    # How to combine multiple tag-matches on one entity:
    #   "max"   — take highest matching tag's multiplier (default)
    #   "sum"   — sum all matching tag-multipliers
    #   "first" — take first tag in frontmatter order that has a config entry
    tag_strategy: str = "max"

    # Status-axis multipliers (M008 areas `status:` frontmatter +
    # similar status-bearing pages).
    status: dict[str, float] = field(default_factory=dict)


@dataclass
class Scheduling:
    compile_after_hour: int = 18
    dedup_window_seconds: int = 60
    # When true, a real (non-dry-run) `wiki compile` drains any due piggybacks
    # (dream-cycle, lint, curiosity, daily-digest, …) at the end of the run,
    # bypassing the `compile_after_hour` evening gate (per-task cooldowns still
    # rate-limit). This keeps maintenance current for operators who live in
    # `wiki update && wiki compile` and rarely `wiki flush` — the flush path was
    # the only other trigger, so their queues otherwise piled up unworked. Set
    # false to keep maintenance evening-/flush-only.
    piggybacks_on_compile: bool = True
    # IANA timezone name used for human-friendly local-time decisions
    # (compile_after_hour cutoff, daily-log filename, "reviewed" timestamps).
    # Default UTC keeps installs portable; override per-instance via config.yaml.
    timezone: str = "UTC"
    # M014 dream-cycle (entity-page re-synthesis). An entity whose
    # `last_synthesized_at:` frontmatter is newer than this many days is
    # skipped by `wiki dream --all-entities` and by the dream_cycle
    # piggyback. Per-entity `--ignore-cooldown` overrides. Default 7 —
    # one weekly sweep keeps State fresh without burning Opus tokens on
    # entities the operator hasn't generated new substrate for.
    dream_cooldown_days: int = 7
    # M017 — config-driven entity priority for dream-cycle selection.
    # Default empty = behave like M014 (greedy by age, all entities equal).
    # See DreamPriority docstring + `.ytstack/backlog/dream-priority-config.md`.
    dream_priority: DreamPriority = field(default_factory=DreamPriority)
    # Autonomous concept-reconciliation routine (concept-consistency-routine).
    # A hard fact whose `last_reconciled:` frontmatter is newer than this many
    # days is skipped by `wiki reconcile` + the concept_reconcile piggyback.
    # Default 14 — concepts drift slower than entities; conservative.
    concept_reconcile_cooldown_days: int = 14
    # Dream web-research (issue #2). An entity whose `## Public Profile` block
    # was refreshed within this many days is skipped by the web-research
    # post-pass. Separate from dream_cooldown_days — public profiles change
    # slowly, so the default is much longer (30 d). `wiki dream web-research
    # <slug>` ignores this for a forced refresh.
    web_research_cooldown_days: int = 30
    # Insufficient-corpus backoff (2026-06-02). When a dream RUNS but the agent
    # returns the INSUFFICIENT_CORPUS sentinel (no synthesizable claims — common
    # on generic-noun slugs whose mention-scan false-matches, e.g. `kontakte`
    # hitting the German word "Kontakte"), the entity is backed off the sweep
    # with an exponential window: dream_cooldown_days × 2^(consecutive_no_ops-1),
    # capped at this many days. A successful synthesis clears the backoff. This
    # caps the worst-case re-spend on a junk/dormant entity at ~one SDK call per
    # this many days instead of one per sweep. 0 disables the mechanism.
    # `wiki dream <slug>` ignores it (explicit runs always proceed).
    dream_insufficient_corpus_backoff_max_days: int = 30


@dataclass
class PiggybackTask:
    enabled: bool = True
    cooldown_hours: int = 24
    max_per_run: int | None = None


@dataclass
class Models:
    compile_model: str = "claude-opus-4-7"
    # Compile fallback for sources >= CONFIG.limits.compile_large_source_chars.
    # The standard 200K-token Opus window dies silently (exit-1, empty stderr)
    # on 100+ KB transcripts even with max_turns capped — Read-tool fan-out into
    # knowledge/ articles plus the source itself blow past the window mid-stream.
    # The 1M variant absorbs both. Set to "" to disable the auto-upgrade and
    # stay on `compile_model` regardless of source size.
    compile_large_source_model: str = "claude-opus-4-7[1m]"
    # Dream-cycle entity re-synthesis (M014). dream-entity is a kanonical
    # fan-out workload: 1 entity-page Edit on top of N substrate Reads from
    # its corpus (T1=10-30 files typical) + Grep/Glob exploration of
    # knowledge/. Tool-turn ballooning blows the 200K Opus window mid-stream
    # the same way compile.py did pre-M010 (see KNOWLEDGE.md "tool-turn
    # ballooning is the new overflow vector"). Default to [1m] up-front so
    # dream-entity calls have headroom for the inherent fan-out, just like
    # `compile_force_long_context_types` does for compile's fan-out
    # substrates (daily-digest, etc). Set "" to fall back to compile_model.
    dream_model: str = "claude-opus-4-7[1m]"
    # Folder-scan answer provider (M027-S04, Q9 seam). The curiosity
    # folder backend reads an operator-approved file in-place and
    # distills an answer-extract. "claude-sdk" is the only provider
    # today; a local LLM/agent provider is the long-term target (then
    # content never leaves the machine). Unknown values raise loudly —
    # never a silent fallback.
    folder_scan_provider: str = "claude-sdk"
    ollama_url: str = "http://localhost:11434"
    vision_model: str = "gemma4:e4b"
    # Curiosity gap-detection. Needs *both* schema-honoring AND enough context
    # to fit the curiosity prompt (compact index + source + folder listing).
    # Decision matrix (skills/local-llm 2026-05-04 + 2026-05-15 probe):
    #   - gemma4:e4b → MT 9.16, 128k ctx, BUT ignores Ollama JSON-Schema entirely
    #     (invents `reasoning`/`suggested_action` field names). 6-week stillstand.
    #   - phi4:14b   → MT 9.26, but only **16k** ctx. lxw curiosity prompt is
    #     ~22-25k tokens (64 KB compact index dominates) → silent truncation,
    #     model reasons on a fragment, hallucinates topics from random index rows.
    #   - llama3.1:8b → MT 9.14, **128k** ctx, schema-honors ✓ (verified probe).
    #     Quality near-tie with phi4 without the context cliff. Right pick.
    curiosity_model: str = "llama3.1:8b"
    classify_model: str = "gemma4:e4b"


@dataclass
class Limits:
    compile_max_files: int = 30
    compile_max_consecutive_failures: int = 3
    flush_max_retries: int = 3
    flush_retry_delay_seconds: int = 30
    # Per-class budgets for session/pre-compact flush context (hooks/_transcript.py).
    # Replaces the pre-2026-05-16 globals MAX_TURNS=30 + MAX_CONTEXT_CHARS=15_000,
    # which were content-blind: a tool-heavy session would push the entire 15 KB
    # into truncated tool dumps and lose the assistant prose where the actual
    # analytical findings live. Separate budgets per content class let us be
    # generous with the high-signal stream (assistant prose) while keeping tool
    # noise on a short leash. Allocation is prefer-tail (newest turns first),
    # so a session that exceeds budget keeps the recent state and drops the
    # opening warm-up. See KNOWLEDGE.md "Flush context — Karpathy/Cole pattern
    # gen-2" and the 2026-05-16 ROM-session incident.
    #
    # 50K assistant-text was chosen by observing typical "long analysis" sessions
    # (~30-50K chars of assistant prose); covers them whole. User-text 10K is
    # generous for prompts. Tool-summary 10K caps how much one-line tool
    # summaries can compete with prose — the per-result 300-char trunc still
    # applies on top.
    flush_assistant_text_budget_chars: int = 50_000
    flush_user_text_budget_chars: int = 10_000
    flush_tool_summary_budget_chars: int = 10_000
    screenshot_resize_width: int = 512
    screenshot_timeout_seconds: int = 60
    # TCP connect timeout for every Ollama HTTP call (ollama_client.py). A
    # single httpx float timeout makes connect == read, so a sleeping/down LAN
    # GPU box could cost the full read budget (e.g. 300 s) just to fail the
    # connect. 10 s is generous on a LAN. The read timeout stays per-call
    # (each caller passes its own); write/pool/keepalive are engine constants
    # in ollama_client.py. Keepalive is what actually bounds a half-open
    # ESTABLISHED socket (review-wiki 19h-hang incident 2026-05-30).
    ollama_connect_timeout_s: int = 10
    # Hard wall-clock cap the piggyback runner (core/piggyback_runner.py)
    # enforces on every spawned piggyback. flush.py spawns piggybacks detached
    # (fire-and-forget, DEVNULL) and can't wait on them, so without this a hung
    # child runs unbounded — review-wiki sat on a half-open socket for 19h47m
    # (incident 2026-05-30). On timeout the runner kills the child and records
    # status="timeout". 4h is generous for a full review-wiki sweep; lower it
    # once per-task overrides exist.
    piggyback_max_runtime_s: int = 14_400
    # review-wiki.py per-article Ollama read timeout (was a hardcoded 300 in
    # the script). Generous because the quality-review prompt is large and
    # gemma cold-calls are slow; the connect cap + keepalive above prevent a
    # dead host from blocking this whole budget.
    review_ollama_timeout_s: int = 300
    # review-wiki.py fail-fast: abort the full-vault sweep after this many
    # CONSECUTIVE per-article Ollama failures. Without it a mid-sweep kcma
    # outage means 1700 × read-timeout of pointless grinding. Set 0 to disable.
    review_consecutive_failure_abort: int = 5
    # review-wiki.py incremental checkpoint: flush the partial JSON report
    # every N reviewed articles so an aborted/killed sweep keeps its work
    # (the report was previously written only at end-of-sweep).
    review_checkpoint_every: int = 25
    # Voice punctuation Ollama-chat timeout (collectors/voice.py). gemma4:e4b
    # cold-call (model-load into VRAM) routinely hits 30–40 s; warm runs are
    # ~5–15 s. Hardcoded 30 s pre-2026-05-28 tripped on every first call after
    # a quiet period. 120 s mirrors the chat() default in ollama_client.py.
    voice_punctuate_timeout_s: int = 120
    curiosity_max_gaps: int = 3
    curiosity_min_source_chars: int = 500
    curiosity_timeout_s: int = 240         # ollama chat_schema timeout for curiosity gap-detection
                                           # (gemma4:e4b on long YT-notes regularly hits >90s)
    # Pre-flight cap for the curiosity-pass prompt (Ollama side, not Claude).
    # llama3.1:8b has 128k context (~430K chars at German density); we leave
    # headroom for the model's own response + cache. If the compact index
    # outgrows this, the producer truncates the index portion in-place
    # rather than aborting — curiosity is a nice-to-have, keep the loop
    # alive with reduced coverage. Symptom-on-overflow without this guard
    # is model-specific: 16k-window models (phi4) silently truncate and
    # hallucinate; 128k-window models eventually OOM-stall on Ollama side.
    curiosity_max_prompt_chars: int = 250_000
    # Curiosity quality gates (2026-05-15 quality arc).
    # `curiosity_source_globs`: only run curiosity on sources matching one
    # of these fnmatch patterns. Memories / knowledge / hard-facts get
    # skipped — they're cognitive self-notes with no email-side context.
    # Operator can override (e.g. empty list = run on everything).
    curiosity_source_globs: list[str] = field(default_factory=lambda: [
        "raw/transcripts/*",
        "raw/articles/*",
        "raw/notes/*",
        "daily/*",
    ])
    # `curiosity_exclude_globs`: denylist subtracted from the allowlist above.
    # Both curiosity passes (regular + folder) skip a source matching any of
    # these BEFORE the Ollama call. Default excludes the email-deep-scan
    # substrate (`raw/notes/email/deep-*.md`): those files are themselves
    # outputs of the email-curiosity deep-scan, so running curiosity on them is
    # circular — on lxw it yielded 58% "no gaps" + 79% duplicate-drops while
    # adding ~10-25 s of Ollama latency to every compile. Operator-extensible;
    # empty list = no exclusions.
    curiosity_exclude_globs: list[str] = field(default_factory=lambda: [
        "raw/notes/email/deep-*",
    ])
    # `curiosity_folder_confidence_min`: integer 1-5 self-reported by the
    # LLM per gap. Below this threshold the producer drops the gap with
    # `folder_low_confidence`. Forces the model to hedge openly instead
    # of defaulting to a generic catch-all folder.
    curiosity_folder_confidence_min: int = 3
    # `curiosity_folder_max_candidates`: when the digests overflow the prompt
    # budget, the producer does NOT inject the folder structure — it injects
    # the top-N candidate files retrieved by rarity-weighted keyword match
    # (rarer keyword = stronger signal). The model judges a short candidate
    # list, not the 1000s-file tree. Keep small enough that a local 8B model
    # processes it fast under schema-constrained decoding (lxw: a full
    # dir-skeleton prompt timed out llama3.1:8b at 240s).
    curiosity_folder_max_candidates: int = 40
    # `curiosity_quote_min_anchor_tokens`: the source_quote gate accepts the
    # quote if ANY contiguous N-token window from the (normalised) quote
    # appears in the (normalised) source excerpt. Strict whole-quote
    # substring is too brittle — LLMs routinely add interpretive
    # prefix/suffix or paraphrase the edges while keeping a verbatim core.
    # Token-window anchor is verifiable AND tolerant of those cosmetic
    # edits. 5 is a healthy minimum — a 5-word phrase rarely matches by
    # accident, so a model that returns a 5+ token verbatim block is
    # genuinely citing the source.
    curiosity_quote_min_anchor_tokens: int = 5
    sparse_threshold_words: int = 200
    # Connection-article quality gate (M012, 2026-05-16). A `type: connection`
    # article below this body word-count fires `connection_shallow_body` in
    # lint — connections that don't reach this floor almost always restate
    # the linked concepts side-by-side instead of asserting a load-bearing
    # mechanism/contrast/dependency between them. Companion check
    # `check_connection_depth` also enforces ≥2 distinct wikilink targets
    # and a `tension|mechanism|dependency` frontmatter field.
    connection_min_words: int = 50
    # M019 default lookback for clinical-screen instruments (PHQ-9, GAD-7,
    # ASRS-v1.1, WHO-5, MEQ-19). The instrument-yaml's `inference.default_
    # lookback_days` overrides this per-instrument; this is the engine-level
    # fallback when the instrument doesn't specify. 14 = "last 2 weeks", the
    # standard clinical reference window for the PHQ-/GAD- family. Bigger
    # windows pull more substrate (more cost, more recall, more risk of
    # mixing periods); smaller windows reduce signal.
    reports_default_lookback_days: int = 14
    # YouTube ingest (scan-youtube.py — see also CONFIG.piggybacks.scan_youtube)
    youtube_max_frames: int = 30          # Tier-3 visual: cap frames per video
    youtube_max_duration_s: int = 10800   # Tier-3: skip videos longer than this (3h default)
    youtube_frame_resize_width: int = 512  # ffmpeg downscale before vision model
    youtube_vision_timeout_s: int = 90    # per-frame ollama call timeout
    youtube_aggregate_timeout_s: int = 300  # final synthesis call timeout
    # Jamie ingest (collectors/jamie.py — see also CONFIG.piggybacks.jamie).
    # Multi-tenant: per-account jamie block under personal.accounts.<id>.jamie
    # (kind: jamie-api, api_key_env, key_type, since, max_per_run).
    jamie_request_timeout_s: int = 30     # per-HTTP-call timeout against api.meetjamie.ai
    jamie_max_per_run: int = 50           # default cap per account (overridable via the per-account jamie sub-block)
    # Google Meet ingest (collectors/gmeet.py — see also CONFIG.piggybacks.gmeet).
    # Multi-tenant: per-account gmeet block under personal.accounts.<id>.gmeet
    # (kind: gmeet-api, drive_folder_id, drive_folder_name, since, max_per_run).
    gmeet_request_timeout_s: int = 30     # per-HTTP-call timeout against the Drive API
    gmeet_max_per_run: int = 50           # default cap; per-account override is the gmeet sub-block's max_per_run
    # Google Calendar ingest (collectors/calendar.py — see also
    # CONFIG.piggybacks.calendar). Multi-tenant: per-account calendar block
    # under personal.accounts.<id>.calendar (kind: google-calendar,
    # include, backfill_days, future_days, since, max_per_run).
    calendar_request_timeout_s: int = 30  # per-HTTP-call timeout against calendar.googleapis.com
    calendar_max_per_run: int = 500       # default per-calendar cap; per-account override is the calendar sub-block's max_per_run
    calendar_backfill_days: int = 90      # default past window per run (events with updated >= now-N for delta sync)
    calendar_future_days: int = 7         # default future window re-fetched every run (catches mutations on upcoming events)
    # Oura health ingest (collectors/health.py — Phase 1, oura-only).
    # Multi-tenant: per-account health.oura block under personal.accounts.<id>.health
    # (kind: oura-pat, api_key_env, backfill_days).
    oura_request_timeout_s: int = 30      # per-HTTP-call timeout against api.ouraring.com
    oura_max_backfill_days: int = 90      # default first-run window; per-account override via backfill_days
    # Claude Agent SDK per-message buffer (stream-json line buffer). SDK default is
    # 1 MB; trips on tool-result messages carrying knowledge/index.md (~300 KB raw,
    # ~600 KB JSON-escaped) or Write/Edit calls on large articles, with a confusing
    # `Failed to decode JSON: ... exceeded maximum buffer size of 1048576 bytes`
    # exception. Bumped to 50 MB by default — safe headroom for any realistic
    # single-message scenario without hiding real runaway responses.
    sdk_max_buffer_size_mb: int = 50
    # Pre-flight cap for `wiki query` prompts. A query embeds the compact
    # index + hard facts; once the knowledge base outgrows the model's
    # context window the SDK dies with an opaque exit-1 / empty-stderr
    # `kind=unknown`. Tripping this limit first turns that into a clear
    # operator message. 500K chars ≈ 167K tokens at German density —
    # inside a 200K-token window with headroom for the response.
    query_max_prompt_chars: int = 500_000
    # Pre-flight cap for `wiki compile` prompts. Embeds compact index +
    # AGENTS.md + facts + raw source. Same overflow class as query, but
    # the source content varies wildly (small daily notes vs 100+ KB
    # gmeet transcripts) — the budget guard catches outliers before they
    # cost 13 minutes of opaque kind=unknown silence. 400K chars ≈ 110K
    # tokens initial; the remaining ~90K tokens absorb tool-turn growth.
    compile_max_prompt_chars: int = 400_000
    # Tool-turn ceiling per compile run. 30 was generous enough to let
    # the model loop on a huge source until it hit the context window
    # (see KNOWLEDGE.md: gmeet 138 KB transcript). Bumped 12 → 20 on
    # 2026-05-17 after a 1.2 KB planning-bullet note (yesterday-marketing-
    # initiative-plan.md) hit max_turns on Haiku — many-entity bullet
    # outlines legitimately need ~15-20 turns to extract+link each
    # bullet's referenced concepts. 20 matches `daily-digest`'s tier
    # (the closest many-entity shape); per-file cost guard
    # (compile_max_tokens_per_file) still bounds runaway burns.
    compile_max_turns: int = 20
    # Higher cap for substrates listed in `compile_force_long_context_types`.
    # Two-layer person/project pages with carry-forward semantics
    # (Read-existing → Edit-State → Verify → maybe re-Edit) consume far more
    # turns per attendee than the flat-atomic shape that informed the 12
    # default. A dense calendar-rollup with 6 attendees + recurring concept
    # updates needs ~15-20 turns; daily-digest with 6 topics needs similar.
    # Hitting max_turns surfaces as `subtype=error_max_turns` on the
    # ResultMessage and burns ~$3-4/attempt at [1m] pricing — the bigger
    # cap is the cheaper end of the trade-off. See KNOWLEDGE.md
    # "max_turns trap on dense fan-out substrates".
    compile_max_turns_long_context: int = 30
    # Hard per-file TOKEN guard. When a single compile_file call's total token
    # use (input+output, summed from AssistantMessage.usage) exceeds this, the
    # file is marked failed with `kind=tokens_exceeded` and the batch ABORTS
    # (not skips — operator must intervene). Defense-in-depth against max_turns
    # loops on substrate-prompt mismatches: a dense-fan-out file re-reads
    # articles every turn and balloons token use. Set to 0 to disable.
    # Default 500_000 — a faithful translation of the prior $2.50 USD cap at
    # the documented Opus rates; re-tune from state/usage.json once real per-
    # file token data accrues (DECISIONS 2026-05-23: tokens, not dollars).
    compile_max_tokens_per_file: int = 500_000
    # Substrate types (frontmatter `type:` value) that compile.py skips
    # in batch mode. Operator can still force-compile a single file via
    # `wiki compile --file <path>`. Last-resort escape hatch for
    # substrate types that have neither a dedicated prompt in
    # SUBSTRATE_PROMPTS nor any extraction value worth burning on. Today:
    #   - `email-delta`: 14-line metadata noting "N new emails in folder
    #     X" — the actual content comes via curiosity/email-deep-scan
    #     separately. Compiling the delta wastes $2+ per file for
    #     no extracted knowledge.
    #   - `folder-index`: body-blind watched-folder digests under
    #     raw/index/ (M027) — pure metadata for the curiosity producer;
    #     the distillable artifacts are the raw/notes/folder/ answers,
    #     which stay compile sources.
    compile_skip_substrate_types: tuple[str, ...] = ("email-delta", "folder-index")
    # Watched-folder index knobs (M027-S02, `wiki index`). The digest is
    # always the COMPLETE inventory — prompt budget is the consumer's
    # concern (trim/grep at the producer), never the artifact's
    # (2026-06-10 reversal: a write-time cap hid 75% of a real trove).
    # max_depth=0 = unlimited; set per-install only as a walk-cost bound
    # for huge NAS roots (S06). recent_n = top-N recent-changes view.
    folder_index_max_depth: int = 0
    folder_index_recent_n: int = 20
    # Email daily-rollup signal (beta, 2026-05-23). The per-account block the
    # EmailCollector appends to daily/<date>/email.md carries -- beyond the bare
    # count + delta-link -- the top-N senders by volume and a sample of the
    # most-recent subjects, so the daily-digest agent can lift correspondents +
    # themes into the portrait instead of "N new messages". Deterministic; the
    # synthesis happens downstream in the digest. Bodies stay
    # curiosity-on-request. Set either to 0 to drop that part of the block.
    daily_email_top_senders: int = 5
    daily_email_sample_subjects: int = 12
    # Threshold above which a source counts as "large" — surfaces one
    # extra INFO line so the operator can see *which* file was big when
    # the SDK call slows down. Pure logging signal, no behavior change.
    compile_large_source_chars: int = 50_000
    # Per-compile-call timeout (seconds). Wraps the `async for message in
    # query(...)` iterator with `asyncio.wait_for`. When the bundled CLI
    # subprocess hangs (vs crashes — see KNOWLEDGE.md "hang vs crash"),
    # there is no upper bound without this guard: the parent waits forever
    # and one stuck file blocks every remaining file in the batch.
    # Observed 2026-05-10: PID 66620 sat in `SN` state for 2 h+ with the
    # parent python waiting on its stdout, blocking 80 remaining files.
    # 600 s (10 min) is generous enough for legitimate long compiles
    # (largest known good case so far: ~13 min on a dense gmeet) and
    # short enough to abort a true hang within an operator-noticeable
    # window. On timeout: log WARNING, return `_skipped:
    # compile_per_call_timeout`, preserve the consecutive-failure budget
    # so a single hang doesn't kill the whole batch. Set to 0 to disable.
    compile_per_call_timeout_s: int = 600
    # Dream-cycle per-message stall timeout (M014). Mirrors
    # compile_per_call_timeout_s: a single SDK message that doesn't
    # arrive within this window converts the call to kind=timeout
    # instead of hanging until the bundled CLI subprocess crashes
    # silently with kind=unknown. Default 300s — dream-entity calls
    # typically complete in 30-180s; anything past 5min is a stall.
    # Set to 0 to disable per-message timeout (use whole-call timeout
    # only — current pre-fix behavior).
    dream_per_call_timeout_s: int = 300
    # Retry once with `compile_large_source_model` (the 1M-context Opus
    # variant) when a compile call returns kind=unknown — the silent
    # exit-1 / empty-stderr signature of mid-stream context overflow from
    # tool-turn fan-out into knowledge/ articles. The 50 KB source-size
    # threshold catches deterministic overflows; this retry catches the
    # stochastic ones on small sources where the same file succeeds 70%
    # of the time and fails 30%. Off-switch for operators who would
    # rather see the failure than pay the 1M-variant premium.
    compile_retry_long_context_on_unknown: bool = True
    # Seconds to sleep after a kind=unknown failure before retrying with the
    # long-context model. The retry is back-to-back with the original failed
    # call against the same Anthropic API account — without backoff, the
    # API's per-minute rate-limit window catches both the retry AND any
    # subsequent batch calls, surfacing as silent CLI exit-1 / empty-stderr
    # (classified by the SDK helper as `cli_crash`). 60s clears the
    # 5-request-per-minute Opus window cleanly. Set 0 to disable.
    compile_failure_backoff_s: int = 60
    # Skip the long-context retry on small sources. The retry only earns
    # its rate-limit cost on sources large enough to actually benefit from
    # the 1M-context variant — small sources fail kind=unknown for OTHER
    # reasons (tool-turn fan-out into many existing articles for a
    # not-yet-described substrate type), and the 1M variant doesn't help
    # there. Sources under this threshold abort on first failure instead
    # of burning a rate-limit slot. Default 10 KB.
    compile_retry_long_context_min_source_chars: int = 10_240
    # Force the long-context model up-front for substrates known to fan out
    # heavily into existing knowledge during compile (matched by frontmatter
    # `type:`). A daily-digest is <2 KB on the surface but references 6+
    # topics — the compile agent Reads each related article to ground the
    # synthesis, and the running context blows past 200K mid-stream → silent
    # CLI exit-1 / kind=unknown after 1-5 minutes. The size-threshold above
    # never catches it (source is small). Force the 1M variant for these
    # types regardless of size. Empty tuple disables the override.
    # Substrates that should auto-upgrade to the 1M-context model when
    # using compile_main.md (the dialog-substrate prompt). DEFAULT IS
    # EMPTY: both `daily-digest` and `calendar-rollup` used to be here
    # because compile_main.md fan-out blew their 200K window, but they
    # now have dedicated lean prompts in SUBSTRATE_PROMPTS that don't
    # need [1m] — the size-threshold (50 KB) is the right escape hatch
    # for any large source. Operators on older configs get cleared via
    # migration LIST_REMOVALS. Add an entry here only if a substrate
    # remains on compile_main AND legitimately overflows 200K.
    compile_force_long_context_types: tuple[str, ...] = ()
    # When a kind=unknown failure has no further retry path available
    # (small source skipping retry, OR already on the long-context model),
    # treat it as a skip rather than a hard failure: log WARNING, return
    # `_skipped`, and don't count toward consecutive-failure abort. The
    # underlying file genuinely cannot compile under the current architecture
    # (tool-fanout overflow on a too-rich substrate) — operator can't fix
    # it by rerunning, so eroding the failure budget on a structural skip
    # would just abort the batch on unrelated files. Off-switch surfaces
    # every kind=unknown as a failure (legacy behavior, pre-2026-05-15).
    compile_skip_on_long_context_unknown: bool = True
    # Circuit-breaker for aggregated-memory chunked compiles. The
    # memory-seed/memory-sync substrate splits an aggregated dump into
    # N ~1-KB chunks (one per `## section`) and compiles each as its own
    # `compile_source` call. Pre-guard, a broken substrate-prompt would
    # burn N × $0.30-0.40 (observed 2026-05-17: 46-chunk memory-seed file
    # hit max_turns on every chunk at $0.35 each — potential $16/file
    # before the outer loop ever sees a result). The per-file cost guard
    # (compile_max_tokens_per_file) fires per-chunk, not cumulatively,
    # so it can't catch this pattern. Aborts the chunk-loop after N
    # consecutive failures (skipped OR failed); already-successful
    # chunks are preserved. Set to 0 to disable the breaker.
    compile_aggregated_max_consecutive_failures: int = 3
    # When True (default), `infer_compile_role()` falls back to LOCATION_DEFAULTS
    # (raw/daily/inbox/knowledge → source-only) for files that omit the
    # `compile_role:` frontmatter key. When False, all files without explicit
    # `compile_role:` short-circuit to source-only regardless of path. Operators
    # with non-standard top-level layouts may want to disable the inference and
    # require explicit per-file frontmatter. Standard `wiki seed` layouts work
    # with the default on.
    compile_role_default_by_location: bool = True
    # M011 takes substrate. fnmatch-style globs limiting which sources get an
    # extract-takes pass after compile (gated by CONFIG.features.extract_takes).
    # Default = transcripts + dailies + voice notes, since those are the
    # substrates where third-party beliefs surface in attributed-speaker form.
    extract_takes_source_globs: list[str] = field(default_factory=lambda: [
        "raw/transcripts/*",
        "raw/transcripts/**/*",
        "raw/voice/*",
        "daily/*",
    ])
    # Per-call timeout for the extract-takes SDK invocation (seconds).
    extract_takes_timeout_s: int = 180
    # Cap on takes emitted per source. Stops a noisy meeting from spawning
    # 30 low-signal lines for the same holder.
    extract_takes_max_per_source: int = 12
    # M014 dream-cycle (entity-page re-synthesis). Per-entity prompt-SIZE guard
    # (chars). dream_entity() builds the corpus prompt; if it exceeds this the
    # SDK call is NEVER made (skipped="prompt_too_large") — a context-overflow
    # guard, NOT a cost gate (DECISIONS 2026-05-23). The M016 tiered collector
    # already bounds the corpus to ~600 KB; this is defense-in-depth. Default
    # 415_000 chars ≈ the prior $2.0 estimate at 4 chars/token.
    dream_entity_max_prompt_chars: int = 415_000
    # Cumulative per-run TOKEN ceiling for `wiki dream --all-entities` and the
    # dream_cycle piggyback: the sweeper stops once cumulative real tokens
    # (input+output) cross this. The per-run entity count (piggyback
    # max_per_run) is the primary structural bound; this catches a runaway.
    # Default 2_000_000; re-tune from state/usage.json (tokens, not dollars).
    dream_cycle_max_tokens_per_run: int = 2_000_000
    # Autonomous concept-reconciliation routine (concept-consistency-routine).
    # Structural gates, NOT dollars (DECISIONS 2026-05-23 — usage is tracked in
    # tokens per provider/model via core/usage.py, never gated in USD). A fact
    # violating more than this many concept files is "too broad to auto-
    # reconcile" and is skipped for manual review rather than letting one agent
    # rewrite a large swath of the corpus unattended. Default 25.
    concept_reconcile_max_files_per_fact: int = 25
    # Max facts reconciled per `wiki reconcile` run / concept_reconcile piggyback.
    # Bounds a sweep structurally; `--limit` overrides. Default 10.
    concept_reconcile_max_facts_per_run: int = 10
    # Turn budget for the strict concept-reconciliation agent. Tight: the task
    # is "edit one flagged concept to match one fact", not corpus synthesis.
    concept_reconcile_max_turns: int = 15
    # Turn budget for the operator-driven `wiki correct apply` agent (M028).
    # Broader than concept_reconcile (propagates one fact across the whole
    # vault), so a larger bound. Was hardcoded 50 pre-M028.
    correct_apply_max_turns: int = 50
    # `wiki correct add` warns when a negation_term matches more than this many
    # existing articles — over-broad terms become lint noise / large apply blast
    # radii (M028 issue #5). Warn-only, never blocks.
    correct_broad_term_threshold: int = 15
    # Health-trend synthesis (`wiki health-trends`). Recent-window length (months)
    # for the trend arrow + "recent avg" column; min coverage (days) for a metric
    # to appear (drops near-empty series so no fake trends over data gaps).
    health_trends_recent_months: int = 6
    health_trends_min_coverage_days: int = 10
    # M016 dream-cycle sampled-activation knobs (2026-05-17). Replaces the
    # M014 "load all mentioning files" approach that hit 2.3 MB context
    # overflow on the operator's own page. 4-tier corpus assembly bounded
    # by construction at ~600 KB per dream regardless of vault size.
    # See `.ytstack/backlog/dream-sampled-activation.md` for the full
    # architecture + research grounding (SCM, SleepGate, A-Mem, MemGPT/Letta).
    # Tier 1 — most-recent substrate always-included. 20 is enough to cover
    # ~2 weeks of typical entity-mentioning substrate; older items rotate
    # through Tier 2's weighted sampling.
    dream_tier1_recent_count: int = 20
    # Tier 1 — last N `daily/<date>.md` rollups always-included. 7 = one
    # week of the M001 compressed-substrate digests, which pack high signal
    # per KB. Drop to 0 to skip daily-digest inclusion.
    dream_tier1_digest_days: int = 7
    # Tier 2 — weighted-sample size from substrate older than Tier 1 covers.
    # 50 is the operating point: at a vault of ~1000 older mentioning files
    # per entity, mean re-sampling interval is ~140 days (20 dreams × 7d
    # cooldown). Bigger K = more coverage per dream + bigger prompt; smaller
    # K = faster individual dreams + longer cycle for any one file.
    dream_tier2_sample_count: int = 50
    # `wiki dedup` (entity-dedup, issue #3). Fuzzy-title match floor 0..1 for a
    # pair to be proposed as a duplicate candidate. 0.85 catches STT spelling
    # noise (`josefine-bartsch`/`josephine-bartc`) without flooding the operator with
    # unrelated near-misses; lower it to widen the net, raise to tighten.
    # Phonetic-key collisions + shared `compiled_from` sources are proposed
    # regardless of this floor. See `.ytstack/backlog/entity-dedup.md`.
    dedup_fuzzy_threshold: float = 0.85


@dataclass
class Features:
    curiosity_loop: bool = True
    vision_screenshots: bool = True
    procmail_execution: bool = True
    # Autonomous concept-reconciliation routine (concept-consistency-routine).
    # OFF by default: the routine makes scoped autonomous writes to
    # knowledge/concepts/, so it ships dry-run-first and the operator opts in
    # after reviewing a `wiki reconcile --dry-run` diff. When False, the
    # `concept_reconcile` piggyback skips and `wiki reconcile` warns.
    concept_reconciliation: bool = False
    # Health-trend synthesis (`wiki health-trends`). When False, `wiki
    # health-trends` falls back to dry-run (prints, writes nothing) and the
    # health_trends piggyback skips. Deterministic + $0 — safe to enable.
    health_trends: bool = False
    # Pre-compile sweep of <vault>/Clippings/*.md into <vault>/raw/articles/
    # so Obsidian Web Clipper output reaches the source-glob. Cheap no-op when
    # Clippings/ is empty or absent. Set false if you reconfigure the Web
    # Clipper extension to drop directly into raw/articles/.
    clippings_sweep: bool = True
    # M011 takes substrate. Default OFF — flip True after dogfooding.
    # Cost: +1 SDK call per gated compile (Claude, no Ollama fallback).
    extract_takes: bool = False
    # Dream web-research (issue #2). When True, `wiki dream <slug>` runs a
    # post-pass that researches PUBLIC entities (founders, execs, speakers)
    # via Exa AI and writes a sentinel-managed `## Public Profile` block.
    # Default OFF — it makes an EXTERNAL, paid API call (Exa). Doubly gated:
    # this flag AND per-entity opt-in (`web_research: true` frontmatter or the
    # `public-person` tag). Never feeds back into raw/ (compile-loop
    # contamination guard). See `.ytstack/backlog/dream-web-research.md`.
    dream_web_research: bool = False
    # Source-glob allowlist for the suggestions post-pass. fnmatch patterns
    # matched against source paths relative to ROOT_DIR. Default mirrors the
    # legacy hardcoded `_is_email_source` filter; widen the list to enable
    # suggestions for other substrates (e.g. raw/transcripts/*). Evaluated by
    # producers.orchestrate at compile time (Producer-seam arc, S03).
    suggestions_source_globs: list[str] = field(default_factory=lambda: [
        "raw/email/*.md",
    ])
    # Pre-process voice transcripts through the local classify_model (Ollama)
    # to add punctuation, sentence-case, and German-noun capitalization. The
    # raw transcript is preserved verbatim under `raw_transcript:` in the
    # voice-note frontmatter so the cleaned body remains auditable. Default
    # ON; flip false if your dictation tool already produces punctuated
    # output (macOS dictation, modern Whisper) or if you don't want the
    # extra Ollama call per ingest. Graceful fallback: Ollama unreachable
    # → body = raw, no error.
    voice_punctuate: bool = True
    # Path-scope enforcement for compile + dream agent Write/Edit calls
    # via a `can_use_tool` callback (Python-side gate). Replaces the
    # `Write(knowledge/**)` / `Edit(knowledge/**)` syntax in
    # `--allowedTools`, which the bundled Claude Code CLI treats as
    # bare `Write` / `Edit` (the parenthesised glob is decoration, not
    # enforcement — verified by `scripts/probe_compile_scope.py`,
    # 2026-05-17). When True the agent runs in streaming mode with the
    # callback as the actual gate; when False the engine reverts to the
    # decorative allowlist for one-line rollback if the streaming-mode
    # rewrite surfaces edge cases under production load. Default True.
    compile_callback_gate: bool = True
    # Deterministic per-picture metadata extraction (EXIF + Android
    # screenshot filename pattern). When True, the pictures collector
    # adds `captured_at`, `device`, `location`, `shot`, `app_context`
    # frontmatter keys (where available) to each archive sidecar before
    # the gemma4 vision pass — orthogonal to the LLM output. EXIF read
    # via Pillow (already a transitive dep). HEIC sources fall through
    # without EXIF (Pillow needs the pillow-heif plugin for HEIC, which
    # is not in the engine's deps yet); JPEG/PNG cover Android screenshots
    # and the dominant iCloud / iOS-Shortcut JPEG path. Default True;
    # flip false if EXIF / location data should never enter the vault
    # (privacy-conscious operators, multi-tenant). Graceful no-op when
    # the source file carries no EXIF and isn't an Android-screenshot.
    extract_picture_metadata: bool = True
    # Corpus-wide post-compile pass that writes a sentinel-managed
    # `## Backlinks` footer into every knowledge/<article>.md so AI agents
    # reading the markdown directly get backlink information without
    # corpus-wide ripgrep. Idempotent — unchanged corpus = zero writes.
    # Flip false to skip the sweep (e.g. to compare compile timing without
    # the O(corpus) extra read/write). Default True. M020, 2026-05-17.
    materialize_backlinks: bool = True
    # Corpus-wide post-compile pass that rewrites every wikilink to a path
    # relative to its containing article (a link in a markdown file is
    # relative to that file). Obsidian resolves a slash-bearing link against
    # the vault root, so the legacy `[[concepts/foo]]` form (relative to
    # knowledge/) created empty stubs when clicked from a nested article.
    # Idempotent — already-relative links produce zero writes. Runs right
    # after the backlinks pass. Default True. 2026-05-29.
    relativize_wikilinks: bool = True
    # M019 master switch — operator-self-reports surface. When True,
    # `wiki study run` / `wiki analyze` subcommands are wired and the
    # piggyback orchestration (Pass-1 per-study after each run; Pass-2
    # cross-study on its own schedule, lands in S05) fires. Default OFF
    # — flip True after S05 dogfooding lands. Reports live at vault-root
    # `<personal.reports_dir>/` (default "reports"), STRUCTURALLY
    # air-gapped from the compile loop (`COMPILE_SUBSTRATE_EXCLUDED_PREFIXES`
    # in this module). See `.ytstack/DECISIONS.md` 2026-05-17 entries on
    # the M019 architecture + air-gap.
    operator_reports: bool = False
    # Pre-flight skip for dream-entity passes whose corpus carries ZERO
    # entity-specific substrate — i.e. the only files are date-pulled daily
    # digests that (provably, since the mention-scan found 0 recent/authored/
    # tier-2 hits) do not mention the entity. Such a pass is a guaranteed
    # INSUFFICIENT_CORPUS no-op, yet still bills a full prompt-cache write
    # (~$0.80/entity). When True, dream_entity() returns
    # skipped="no_entity_substrate" with $0 spend instead of invoking the SDK.
    # Flip false to force a synthesis attempt on digests alone (e.g. when the
    # entity name never appears verbatim but the digests are topically
    # relevant). Default True. 2026-05-31.
    dream_require_entity_substrate: bool = True


@dataclass
class GraphView:
    mode: str = "knowledge-only"
    custom_search: str = ""
    # Tag names treated as "domain anchors" for graph-view coloring and
    # qa-schema lint. Notes carrying at least one of these get a meaningful
    # color in the graph; notes without any fall into the grey fallback.
    # Empty list = use the engine default (see scripts/lint.py
    # _DEFAULT_DOMAIN_TAGS). Override per vault in config.yaml:
    #   graph_view:
    #     domain_tags: [fleet, openclaw, my-product]
    domain_tags: list[str] = field(default_factory=list)


@dataclass
class Skills:
    """Engine-skill distribution preferences (see `wiki skills`)."""

    # When true, `wiki skills install` / `wiki skills sync` also link
    # global-eligible skills (currently: use-llm-wiki) into ~/.claude/skills/
    # and register this vault in ~/.config/llm-wiki/vaults, so agents working
    # in *any* project can discover and query this wiki. Opt-in — default
    # false keeps the install vault-local (the other bundled skills are always
    # vault-local; they operate inside a vault).
    global_install: bool = False


# Note (2026-05-15, multi-tenant policy): `gmeet`, `jamie`, and `calendar`
# are all account-bound — their config lives per-account under
# `personal.accounts.<id>.{gmeet,jamie,calendar}` with `kind: gmeet-api` /
# `jamie-api` / `google-calendar`, mirroring the email Reader/Filter
# sub-block pattern. `collectors/{gmeet,jamie,calendar}.py:_resolve_*_accounts()`
# read the dispatch.


@dataclass
class Personal:
    """Per-instance data that must NOT be committed.

    Defaults are empty so prompts/schema render cleanly even on a fresh
    install. Populate via local config.yaml.
    """
    # default account; used as fallback in compile.py and for prompt rendering
    primary_account: str = ""
    # account-id -> per-account dict. Schema (M002+):
    #   email   (str)               sender identity; required
    #   label   (str, optional)     display label in reports
    #   reader  (dict, optional)    {kind: thunderbird-mbox|gmail-api|…, <kind-specific keys>}
    #   filter  (dict, optional)    {kind: thunderbird-msgfilter|all-inkl-procmail|gmail-api|…, …}
    # See [CONTEXT.md § Account.kind] and [scripts/adapters/mailbox/__init__.py]
    # for the full kind-table. resolve_reader / resolve_filter dispatch on
    # reader.kind / filter.kind respectively. Unknown kinds are silently
    # skipped (graceful agnostic).
    #
    # Legacy top-level fields (mbox_paths, filter_paths, imap_host,
    # imap_user_env, imap_pass_env, has_procmail) are NO LONGER ACCEPTED
    # — load() raises ConfigError pointing at the migration template.
    accounts: dict[str, dict] = field(default_factory=dict)
    # ordered list of {path, desc} dicts; drives both compile_curiosity.md
    # listing AND compile.py's schema enum (single source of truth)
    email_folders: list[dict] = field(default_factory=list)
    # Optional subset of email_folder paths considered by the curiosity loop.
    # Empty list (default) = use all email_folders. Operator-curated allowlist
    # lets you exclude generic catch-alls (e.g. "INBOX/COMPANY/00 COMPANY")
    # that the LLM otherwise picks as a fallback when no specific folder fits.
    # Paths in this list must match a `path:` entry in email_folders; unknown
    # paths are dropped silently with a one-time WARNING on load.
    curiosity_folders: list[str] = field(default_factory=list)
    # M027: folders the curiosity loop may scan as substrate (local + NAS). A
    # body-blind metadata index is built from these (S02); the producer proposes
    # reads, the operator approves per-request in the walk (the content/cloud
    # gate). Each entry: {id, kind: local|smb, path|share, include?, exclude?}.
    # Empty default keeps the feature off. Validated by
    # _validate_watched_folders_schema on load; nothing scans until S02.
    watched_folders: list[dict] = field(default_factory=list)
    # short list of project / product names rendered into
    # scan_screenshots_vision.md as concrete examples
    project_examples: list[str] = field(default_factory=list)
    # Substring keywords whose presence in a calendar event title marks it as a
    # holiday / observance to skip during collectors/calendar.py. Locale-specific
    # (e.g. ["Christmas", "Easter"] for English; ["Weihnacht", "Ostern"] for
    # German). Empty list = no skipping.
    calendar_skip_keywords: list[str] = field(default_factory=list)
    # Path to local Thunderbird profile directory (mbox + filter roots live here).
    # Empty string disables the email Collector's thunderbird-mbox adapter.
    thunderbird_profile: str = ""
    # Path to a local Firefox profile directory (e.g. ~/Library/Application
    # Support/Firefox/Profiles/<id>.default-release on macOS, or
    # ~/.mozilla/firefox/<id>.default-release on Linux). Empty string disables
    # the Firefox half of scan-browser.py.
    firefox_profile: str = ""
    # Path to a Simple Tab Groups (STG) backup directory (where the extension
    # writes its periodic *.json snapshots). Empty string disables STG-import
    # paths in scan-tabs.py / scan-browser.py.
    stg_backup_dir: str = ""
    # Path to a directory the operator dumps dictation transcripts into
    # (any tool that writes .txt or .md works — OpenWhispr is the default
    # recommendation; FluidVoice / macOS dictation / Hammerspoon snippets
    # also work). Audio files (.m4a/.wav/.mp3/.flac/.ogg/.aac/.mp4) are
    # transcribed via whisper.cpp when `voice_transcribe_model` is set;
    # see the next four knobs. Empty string disables collectors/voice.py.
    voice_inbox: str = ""
    # Audio-transcription via whisper.cpp (ad-hoc, 2026-05-28). When set,
    # audio files dropped into `voice_inbox` are transcribed locally and
    # the transcript follows the same pipeline as text dictation (optional
    # voice_punctuate pass, daily/-rollup, raw/voice/ canonical file).
    # Operator pre-reqs: `brew install whisper-cpp` and a ggml model file
    # (e.g. ~/whisper-models/ggml-base.bin from
    # https://huggingface.co/ggerganov/whisper.cpp/tree/main). `.m4a`/`.mp4`/
    # `.aac` go through ffmpeg pre-conversion to 16 kHz mono WAV — ffmpeg
    # ships with macOS via brew but is also widely pre-installed.
    #
    # voice_transcribe_model: absolute or ~-expanded path to the ggml model
    # file. Empty = audio ingest disabled; audio files left in inbox.
    voice_transcribe_model: str = ""
    # Language hint passed to whisper-cli. "auto" auto-detects (slightly
    # slower); language code like "de" or "en" skips detection.
    voice_transcribe_language: str = "auto"
    # Threads passed to whisper-cli (-t N). 4 is a sensible default on
    # current Apple Silicon; raise for big models on M-series Max chips.
    voice_transcribe_threads: int = 4
    # Override path to the whisper.cpp binary. Empty = auto-detect
    # `whisper-cli` from $PATH (brew installs to /opt/homebrew/bin).
    voice_transcribe_binary: str = ""
    # Override path to ffmpeg. Empty = auto-detect from $PATH. Only used
    # for audio formats whisper-cli doesn't natively read (m4a/mp4/aac);
    # mp3/wav/flac/ogg go straight to whisper-cli.
    voice_transcribe_ffmpeg: str = ""
    # Path to a directory the operator drops camera / phone photos into for
    # ingest. Same shape as `voice_inbox` (folder-watch + archive-as-dedup),
    # but the per-file pipeline runs a vision LLM (gemma4 via Ollama) and
    # writes a HOME-side sidecar next to the source + a vault-side batch
    # report under `raw/notes/pictures/`. Mirrors the screenshot collector
    # but sources from a separate, mobile-friendly inbox (iCloud Shortcut
    # target etc.). Empty string disables collectors/pictures.py.
    #
    # As of 2026-05-28 also accepts a list[str] of paths — operator points
    # at multiple inbox directories simultaneously (e.g. iCloud Drive +
    # an inbox_bridges-mirrored Google Drive folder). All paths are
    # scanned per run, results aggregate into one batch report. Empty
    # list / empty string / list of empty strings all disable the
    # collector (graceful agnostic).
    picture_inbox: str | list[str] = ""
    # 2026-05-28 inbox-bridge. List of {remote, local, mode?, enabled?} dicts
    # describing folders to mirror from network-mounted / sandbox-restricted
    # paths (e.g. `~/Library/CloudStorage/GoogleDrive-…/wiki-inbox/pictures/`)
    # into local non-restricted paths the substrate collectors then folder-
    # watch as their `<substrate>_inbox`. Solves macOS-TCC: Claude Code's
    # sandboxed subprocesses can't read CloudStorage, but a user-shell-spawned
    # or LaunchAgent-spawned bridge can; the engine collectors then see a
    # stable local mirror. Substrate-agnostic by design — operator wires each
    # mapping's `local` into the matching `*_inbox` key separately.
    #
    # Schema per entry:
    #   remote:  str (required) absolute path, ~-expanded; missing → warn + skip
    #   local:   str (required) absolute path, ~-expanded; auto-created
    #   mode:    str (optional) "move" (default, rsync --remove-source-files) or "copy"
    #   enabled: bool (optional) default True
    #   name:    str (optional) report label; defaults to basename of `local`
    #
    # Empty list = bridge disabled (graceful no-op). See `wiki bridge --help`
    # and `templates/.launchd/com.llm-wiki.bridge.plist.template` for the
    # LaunchAgent install path. Drive-mode "move" means the source folder is
    # drained on every sync — operator accepts: drop is one-shot, not a mirror.
    inbox_bridges: list[dict] = field(default_factory=list)
    # Dream web-research (issue #2). Exa AI API key for the public-entity
    # enrichment post-pass. Empty default = feature inert even when
    # `features.dream_web_research` is on (the post-pass skips with
    # reason "no_api_key"). Falls back to env `EXA_API_KEY` when blank. Lives
    # in Personal (per-instance secret, never committed) — set it in the
    # vault's `.claude/.env` as `EXA_API_KEY=...` rather than config.yaml.
    exa_api_key: str = ""
    # M025 quick-capture-correction loop. Path to a directory the operator
    # one-taps cryptic notes / article snippets into (any tool that writes
    # .txt / .md / .html — WhatsApp-self-group export, Notion quick-note sync,
    # a shortcut). collectors/capture_collector.py folder-watches it, assigns a
    # deterministic content-derived capture-ID, writes raw/captures/capture-<id>.md,
    # and archives the source under raw/inbox-mobile/captures/. The capture-ID is
    # the join-key the digest + correction back-channel use. Empty string disables
    # the collector (graceful agnostic).
    capture_inbox: str = ""
    # M019 operator-self-reports surface. Directory under vault root where
    # `reports/studies/<id>/runs/<ts>/*.md` (deterministic study output) and
    # `reports/analyses/<ts>.md` (analyst-agent output, S05) accumulate. Lives
    # at vault root sibling of `knowledge/` per DECISIONS 2026-05-17 — same
    # lifecycle properties as knowledge (operator data, version-controllable
    # in the operator's git, durable across engine reinstalls). NOT under
    # `.wiki/` (engine state). Operator may rename to "analyses" or any
    # other slug; the `COMPILE_SUBSTRATE_EXCLUDED_PREFIXES` air-gap is
    # path-anchored to the actual value at engine init time.
    reports_dir: str = "reports"
    # Canonical vault-owner identifier. The value (e.g. "alex") is the slug of
    # the operator's own page at `knowledge/people/<value>.md` and drives two
    # things at compile time:
    #
    #   1. Owner-block injection — `compile.py:_build_owner_block()` renders
    #      a small "## Operator / vault owner" section into every substrate
    #      compile prompt (compile_main / compile_calendar / compile_daily /
    #      compile_health / compile_default). Lets the agent resolve self-
    #      references ("I", "we", "my company") and find connection targets
    #      without grepping AGENTS.md prose.
    #   2. Author-attribution fallback — sources lacking an explicit `author:`
    #      frontmatter key are treated as operator-authored;
    #      beliefs/decisions/opinions route to that person's
    #      `knowledge/people/<value>.md` State / Open Threads / Timeline.
    #
    # Leave null for multi-tenant vaults: the owner-block is then omitted
    # entirely and unattributed content stays generic. An explicit `author:`
    # frontmatter always wins over the implicit default.
    implicit_operator_author: str | None = None
    # Jamie AI + Google Meet + Google Calendar integrations are multi-tenant via
    # per-account `jamie:` / `gmeet:` / `calendar:` sub-blocks under
    # `personal.accounts.<id>` (kinds: `jamie-api`, `gmeet-api`,
    # `google-calendar`). No flat dataclass — resolved at run time by
    # `collectors/{jamie,gmeet,calendar}.py:_resolve_*_accounts()`.
    # M013 (2026-05-16): optional `domain:` frontmatter axis on `knowledge/`
    # articles. Cross-cutting life-domain filter (company/personal/ai/meta),
    # extensible per vault. Lifted from lx-vault audit — captured as a tag,
    # not a folder. Lint `check_domain_value` warns on values outside this
    # enum (warning, not error — grace period for typos / new domains).
    # `wiki query --domain X` filters answers to articles whose `domain:`
    # matches. Empty list = feature off (lint check + CLI flag silently
    # no-op). See `.ytstack/backlog/domain-frontmatter.md`.
    domains: list[str] = field(default_factory=lambda: ["company", "personal", "ai", "meta"])
    # Issue #4 (2026-06-13): pin the OUTPUT prose language of compiled
    # `knowledge/**` articles. "auto" (default) keeps today's behavior — write
    # in the source material's language — and renders every compile substrate
    # prompt byte-identically. Any other value (`"de"`, `"German"`, `"fr"`, …)
    # forces all compiled prose (titles, body, summaries) into that language
    # regardless of source, while keeping code, technical identifiers, proper
    # names, and the canonical structural section headers (`## State`,
    # `## Timeline`, …) verbatim so downstream parsing / dedup don't break.
    # Distinct from `voice_transcribe_language` (that's INPUT transcription;
    # this is OUTPUT prose). Injected via `${output_language_instruction}`,
    # built by `core.prompts.build_output_language_instruction`.
    output_language: str = "auto"


# Default piggyback set — names match core/piggybacks.py's task-table keys.
def _default_piggybacks() -> dict[str, PiggybackTask]:
    return {
        "email_incremental": PiggybackTask(cooldown_hours=24),
        "lint_structural": PiggybackTask(cooldown_hours=24),
        "review_wiki": PiggybackTask(cooldown_hours=168),
        "optimize_claude_md": PiggybackTask(cooldown_hours=24),
        "screenshots": PiggybackTask(cooldown_hours=24, max_per_run=50),
        # Drain rate: max_per_run × (24/cooldown_hours) = 5 × 4 = 20/day.
        # Producer can generate ~3 requests per compiled source; at typical
        # batch sizes the consumer keeps up without falling behind.
        # cooldown_hours=6 sized so 4 fires/day; max_per_run=5 batched per
        # fire to amortize mailbox-scan overhead while staying observable.
        "curiosity_followup": PiggybackTask(cooldown_hours=6, max_per_run=5),
        "jamie": PiggybackTask(cooldown_hours=6, max_per_run=20),
        "gmeet": PiggybackTask(cooldown_hours=6, max_per_run=20),
        "calendar": PiggybackTask(cooldown_hours=6, max_per_run=500),
        "voice": PiggybackTask(cooldown_hours=1),
        # M025 quick-capture inbox. Folder-watch like voice (content-IDs each
        # capture, idempotent re-drop); 1h cadence, no per-run cap — drains the
        # inbox each fire. Silently skipped when personal.capture_inbox is empty.
        "capture": PiggybackTask(cooldown_hours=1),
        # Camera/phone-photo inbox. Vision-LLM step makes this heavier than
        # voice — same cadence as screenshots (4×/day with a per-run cap).
        "pictures": PiggybackTask(cooldown_hours=6, max_per_run=20),
        # Distill yesterday's per-source captures (daily/<yesterday>/*.md)
        # into a single ≤500-word digest at daily/<yesterday>.md. Runs once
        # in the morning after the per-collector piggybacks have settled.
        "daily_digest_yesterday": PiggybackTask(cooldown_hours=24),
        "retry_failed_flushes": PiggybackTask(cooldown_hours=24, max_per_run=5),
        # M014 dream-cycle. Cooldown 24h means it fires at most once per day;
        # per-run sweep is gated by limits.dream_cycle_max_tokens_per_run
        # AND limits.dream_entity_max_prompt_chars. max_per_run=3 keeps a single
        # fire from sweeping the whole entity list in one go — the per-entity
        # cooldown (scheduling.dream_cooldown_days, default 7d) ensures the
        # entire fleet drains over the cooldown window.
        "dream_cycle": PiggybackTask(cooldown_hours=24, max_per_run=3),
        # M019 operator-self-reports schedule-dispatch. Cooldown 6h means
        # we check 4×/day if any study is schedule-due; the study's own
        # schedule (weekly/monthly/quarterly) gates actual run. Default
        # OFF until S05 ships and operator flips features.operator_reports.
        "study_run_due": PiggybackTask(cooldown_hours=6, enabled=False),
        # M019-S05 Pass-2 analyst — cross-study synthesist. Reads Pass-1
        # outputs (which `wiki study run` writes automatically per-study)
        # and emits reports/analyses/<ts>.md. Weekly default — operator
        # consumes the latest one; longer cadence is fine since per-study
        # Pass-1 already fires per-run. Default OFF.
        "analyst_pass2": PiggybackTask(cooldown_hours=168, enabled=False),
    }


@dataclass
class WikiConfig:
    scheduling: Scheduling = field(default_factory=Scheduling)
    piggybacks: dict[str, PiggybackTask] = field(default_factory=_default_piggybacks)
    models: Models = field(default_factory=Models)
    limits: Limits = field(default_factory=Limits)
    features: Features = field(default_factory=Features)
    graph_view: GraphView = field(default_factory=GraphView)
    skills: Skills = field(default_factory=Skills)
    personal: Personal = field(default_factory=Personal)


def _merge_dataclass(default: Any, override: dict[str, Any]) -> Any:
    """Apply dict overrides onto a dataclass instance, recursively for nested dataclasses."""
    if not is_dataclass(default) or not isinstance(override, dict):
        return default
    kwargs: dict[str, Any] = {}
    for f in fields(default):
        current = getattr(default, f.name)
        if f.name not in override:
            kwargs[f.name] = current
            continue
        raw = override[f.name]
        if is_dataclass(current):
            kwargs[f.name] = _merge_dataclass(current, raw or {})
        else:
            kwargs[f.name] = raw
    return type(default)(**kwargs)


def _merge_piggybacks(
    defaults: dict[str, PiggybackTask], override: dict[str, Any] | None
) -> dict[str, PiggybackTask]:
    if not override:
        return defaults
    merged = dict(defaults)
    for name, raw in override.items():
        base = merged.get(name, PiggybackTask())
        if isinstance(raw, dict):
            merged[name] = _merge_dataclass(base, raw)
    return merged


class ConfigError(ValueError):
    """Raised when config.yaml has a structural problem the operator must fix."""


_LEGACY_ACCOUNT_FIELDS = {
    "mbox_paths",
    "filter_paths",
    "imap_host",
    "imap_user_env",
    "imap_pass_env",
    "has_procmail",
}


def _validate_accounts_schema(personal_raw: dict) -> None:
    """Reject the M001-era flat-account schema.

    M002 moved per-backend keys (mbox_paths, has_procmail, …) into
    nested `reader:` / `filter:` blocks. This function raises ConfigError
    pointing at the migration template if the legacy shape is detected.
    """
    accounts = (personal_raw or {}).get("accounts") or {}
    if not isinstance(accounts, dict):
        return
    offenders: list[tuple[str, list[str]]] = []
    for aid, body in accounts.items():
        if not isinstance(body, dict):
            continue
        legacy = sorted(_LEGACY_ACCOUNT_FIELDS & set(body))
        if legacy:
            offenders.append((aid, legacy))
    if not offenders:
        return

    lines = [
        "config.yaml uses the legacy account schema (pre-M002).",
        "Migrate each offending account to the nested reader/filter shape.",
        "",
        "Detected:",
    ]
    for aid, fields in offenders:
        lines.append(f"  - personal.accounts.{aid}: legacy keys {fields}")
    lines += [
        "",
        "Migration template (replace the flat keys per account):",
        "",
        "  personal:",
        "    accounts:",
        "      <id>:",
        "        email: <addr>",
        "        reader:",
        "          kind: thunderbird-mbox        # or gmail-api, etc.",
        "          mbox_paths: [INBOX.mbox, ...]",
        "        filter:",
        "          kind: all-inkl-procmail       # or thunderbird-msgfilter | gmail-api",
        "          imap_pass_env: <ENV_VAR_NAME>",
        "",
        "Full kind-table: CONTEXT.md § Account.kind.",
    ]
    raise ConfigError("\n".join(lines))


_WATCHED_FOLDER_KINDS = {"local", "smb"}


def _validate_watched_folders_schema(personal_raw: dict) -> None:
    """Validate personal.watched_folders entries (M027-S01).

    Each entry needs a non-empty `id` and `kind in {local, smb}`; `local`
    requires `path`, `smb` requires `share`. Raises ConfigError listing every
    offending entry. Validation only — no filesystem / SMB access here.
    """
    folders = (personal_raw or {}).get("watched_folders") or []
    if not isinstance(folders, list):
        raise ConfigError(
            "personal.watched_folders must be a list of "
            "{id, kind, path|share} entries."
        )
    offenders: list[str] = []
    for i, entry in enumerate(folders):
        if not isinstance(entry, dict):
            offenders.append(f"  - entry #{i}: not a mapping")
            continue
        fid = entry.get("id")
        label = fid if isinstance(fid, str) and fid.strip() else f"#{i}"
        if not isinstance(fid, str) or not fid.strip():
            offenders.append(f"  - entry {label}: missing required `id`")
            continue
        kind = entry.get("kind")
        if kind not in _WATCHED_FOLDER_KINDS:
            offenders.append(
                f"  - entry {label}: `kind` must be one of "
                f"{sorted(_WATCHED_FOLDER_KINDS)}, got {kind!r}"
            )
            continue
        if kind == "local" and not entry.get("path"):
            offenders.append(f"  - entry {label}: kind=local requires `path`")
        if kind == "smb" and not entry.get("share"):
            offenders.append(f"  - entry {label}: kind=smb requires `share`")
        # Optional per-root sensitivity tag (M027-S05, Q3 full build):
        # free operator vocabulary, stamped into answer artifacts and
        # propagated by compile. Marking only — the walk is the gate.
        sens = entry.get("sensitivity")
        if sens is not None and (not isinstance(sens, str) or not sens.strip()):
            offenders.append(
                f"  - entry {label}: `sensitivity` must be a non-empty "
                f"string when present, got {sens!r}"
            )
    if not offenders:
        return
    raise ConfigError(
        "\n".join(["personal.watched_folders has invalid entries:", ""] + offenders)
    )


def load() -> WikiConfig:
    cfg = WikiConfig()
    if not CONFIG_FILE.exists():
        return cfg
    try:
        raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        # Fall back silently to defaults — scripts log this at usage site.
        return cfg
    if not isinstance(raw, dict):
        return cfg
    _validate_accounts_schema(raw.get("personal") or {})
    _validate_watched_folders_schema(raw.get("personal") or {})
    cfg.scheduling = _merge_dataclass(cfg.scheduling, raw.get("scheduling") or {})
    cfg.piggybacks = _merge_piggybacks(cfg.piggybacks, raw.get("piggybacks"))
    cfg.models = _merge_dataclass(cfg.models, raw.get("models") or {})
    cfg.limits = _merge_dataclass(cfg.limits, raw.get("limits") or {})
    cfg.features = _merge_dataclass(cfg.features, raw.get("features") or {})
    cfg.graph_view = _merge_dataclass(cfg.graph_view, raw.get("graph_view") or {})
    cfg.skills = _merge_dataclass(cfg.skills, raw.get("skills") or {})
    cfg.personal = _merge_dataclass(cfg.personal, raw.get("personal") or {})
    return cfg


CONFIG: WikiConfig = load()


# ── Compile substrate scope policy ────────────────────────────────────
#
# Directories that the compile pipeline (substrate-walker AND
# compile-agent prompt scope) MUST NOT touch — as either Read or Write.
# Single source of truth referenced by every compile-walker so the
# air-gap policy lives in one place.
#
# `reports/` is hard-excluded per M019 DECISIONS.md (2026-05-17): the
# operator-self-reports surface must never flow back into compile, else
# a self-observation-bias feedback loop forms. The other entries are
# infrastructure paths that compile has never touched but listing them
# explicitly catches the case of a future walker that sweeps vault-root
# `*.md` blindly.
#
# Path-form is "<segment>/" with trailing slash — matched against the
# first path segment of a substrate-relative rel_path via startswith().
# `compile_main_system.md` SCOPE block lists the same set verbatim;
# operator-prompts and prompts must stay in sync.
COMPILE_SUBSTRATE_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "reports/",
    ".wiki/",
    ".ytstack/",
    ".obsidian/",
    ".git/",
    ".claude/",
    "templates/",
)


# ── CLI helpers (used by the bash `wiki` entry point) ────────────────

def _walk(cfg: WikiConfig, parts: list[str]) -> object:
    """Walk a dot-notation path through the loaded WikiConfig."""
    obj: object = cfg
    for part in parts:
        if is_dataclass(obj) and not isinstance(obj, type):
            if part not in {f.name for f in fields(obj)}:
                raise KeyError(f"Unknown key: {'.'.join(parts)}")
            obj = getattr(obj, part)
        elif isinstance(obj, dict):
            if part not in obj:
                raise KeyError(f"Unknown key: {'.'.join(parts)}")
            obj = obj[part]
        else:
            raise KeyError(f"Cannot descend into {'.'.join(parts)} at {part!r}")
    return obj


def _coerce(value: str, hint: object) -> object:
    """Coerce a string CLI input toward the type currently in the config."""
    if isinstance(hint, bool):
        if value.lower() in {"true", "1", "yes", "y", "on"}:
            return True
        if value.lower() in {"false", "0", "no", "n", "off"}:
            return False
        raise ValueError(f"Cannot parse {value!r} as bool")
    if isinstance(hint, int) and not isinstance(hint, bool):
        return int(value)
    if isinstance(hint, float):
        return float(value)
    if hint is None:
        # Try int → float → string
        for caster in (int, float):
            try:
                return caster(value)
            except ValueError:
                continue
    return value


def _enumerate_keys(prefix: str, obj: object) -> list[str]:
    keys: list[str] = []
    if is_dataclass(obj) and not isinstance(obj, type):
        for f in fields(obj):
            child = getattr(obj, f.name)
            sub = f"{prefix}.{f.name}" if prefix else f.name
            if is_dataclass(child) and not isinstance(child, type):
                keys.extend(_enumerate_keys(sub, child))
            elif isinstance(child, dict):
                # piggybacks: dict[str, PiggybackTask]
                for k, v in child.items():
                    keys.extend(_enumerate_keys(f"{sub}.{k}", v))
            else:
                keys.append(sub)
    return keys


_CONFIG_BACKUP_DIR_NAME = "config-backups"
_CONFIG_BACKUP_KEEP_LAST = 10


def _backup_dir() -> Path:
    """Where round-robin config backups live: `<.wiki>/state/config-backups/`."""
    # CONFIG_FILE (from paths.py) = <wiki>/config.yaml → its parent is <wiki>.
    wiki_dir = CONFIG_FILE.parent
    return wiki_dir / "state" / _CONFIG_BACKUP_DIR_NAME


def _backup_config_before_write() -> Path | None:
    """Round-robin backup: snapshot the current config to a timestamped file.

    Keeps the last `_CONFIG_BACKUP_KEEP_LAST` snapshots, prunes older.
    Returns the backup path on success, None when there's nothing to back up.
    Failures are logged but don't abort the calling save (defensive — losing
    a backup is better than blocking a config write).
    """
    if not CONFIG_FILE.exists():
        return None
    try:
        bdir = _backup_dir()
        bdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = bdir / f"config-{ts}.yaml"
        # Avoid overwrite within same second — append micro-suffix.
        if out.exists():
            out = bdir / f"config-{ts}-{datetime.now(timezone.utc).microsecond:06d}.yaml"
        out.write_bytes(CONFIG_FILE.read_bytes())

        # Prune oldest beyond keep-count.
        existing = sorted(bdir.glob("config-*.yaml"))
        if len(existing) > _CONFIG_BACKUP_KEEP_LAST:
            for stale in existing[: -_CONFIG_BACKUP_KEEP_LAST]:
                try:
                    stale.unlink()
                except OSError:
                    pass
        return out
    except OSError:
        return None


def _set_in_yaml(key: str, value: object) -> None:
    """Update or insert key in the YAML file. Falls back to a fresh file when missing.

    Note: PyYAML drops comments on round-trip. Header banner is re-emitted
    so the YAML stays human-friendly.

    Side effect: every write is preceded by a round-robin backup of the
    current config (last `_CONFIG_BACKUP_KEEP_LAST` snapshots kept).
    """
    parts = key.split(".")
    if CONFIG_FILE.exists():
        try:
            raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raw = {}
        except yaml.YAMLError as e:
            raise SystemExit(f"Existing {CONFIG_FILE} is not valid YAML: {e}")
    else:
        raw = {}

    cursor = raw
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value

    # Round-robin backup before overwriting.
    _backup_config_before_write()

    header = (
        "# Wiki Config — single source of truth for tunable parameters.\n"
        "# Defaults live in .wiki/scripts/core/config.py; only overrides need\n"
        "# to be in this file. Edit by hand or via `./.wiki/wiki config set …`.\n"
        "# Note: comments not present here are dropped on programmatic writes.\n"
        "# Round-robin backups in .wiki/state/config-backups/ (last 10 saves).\n\n"
    )
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        header + yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Wiki config introspection / mutation")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("show", help="Print full resolved config (default)")
    g = sub.add_parser("get", help="Print one key (dot-notation, e.g. models.compile_model)")
    g.add_argument("key")
    s = sub.add_parser("set", help="Set a key and write back to config.yaml")
    s.add_argument("key")
    s.add_argument("value")
    sub.add_parser("keys", help="List all settable keys (dot-notation)")
    sub.add_parser("path", help="Print the config file path")
    args = p.parse_args()

    if args.cmd in (None, "show"):
        import json
        print(f"# {CONFIG_FILE} (exists={CONFIG_FILE.exists()})")
        print(json.dumps(asdict(CONFIG), indent=2, default=str))
        return 0

    if args.cmd == "path":
        print(CONFIG_FILE)
        return 0

    if args.cmd == "keys":
        for k in _enumerate_keys("", CONFIG):
            print(k)
        return 0

    if args.cmd == "get":
        try:
            val = _walk(CONFIG, args.key.split("."))
        except KeyError as e:
            print(e, file=__import__("sys").stderr)
            return 1
        if is_dataclass(val) and not isinstance(val, type):
            import json
            print(json.dumps(asdict(val), indent=2, default=str))
        else:
            print(val)
        return 0

    if args.cmd == "set":
        try:
            current = _walk(CONFIG, args.key.split("."))
        except KeyError as e:
            print(e, file=__import__("sys").stderr)
            return 1
        if is_dataclass(current) and not isinstance(current, type):
            print(
                f"Refusing to set {args.key!r} — it's a section, not a leaf. "
                f"Set individual fields under it instead.",
                file=__import__("sys").stderr,
            )
            return 1
        try:
            coerced = _coerce(args.value, current)
        except ValueError as e:
            print(e, file=__import__("sys").stderr)
            return 1
        _set_in_yaml(args.key, coerced)
        print(f"set {args.key} = {coerced!r}")
        return 0

    return 0


# ── Timezone ───────────────────────────────────────────────────────────
# Derived from CONFIG.scheduling.timezone (default "UTC"; override via
# config.yaml). Lives here — not in paths.py — because it's CONFIG-derived,
# not a pure path constant. flush_pipeline.py + others import it from here.
TIMEZONE = CONFIG.scheduling.timezone


if __name__ == "__main__":
    raise SystemExit(_cli())
