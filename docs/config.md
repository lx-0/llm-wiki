# Config Reference

Every settable key in `<vault>/.wiki/config.yaml`, plus the secrets surface in `<vault>/.claude/.env`. The schema (every knob's name, type, and default) lives in `scripts/core/config_schema.py` — only the keys you want to *override* need to appear in `config.yaml`. Missing keys fall back to the default; a mistyped value is rejected with a WARNING and the default is kept.

The per-section key tables below are **generated from the schema** (`uv run python scripts/core/config_docs.py --write`); a test diffs them against the dataclasses, so they cannot rot. The *Meaning* column is the first sentence of each field's schema comment — the full rationale (incident history, tuning guidance) lives next to the field in `scripts/core/config_schema.py`.

## Contents

- [Files at a glance](#files-at-a-glance)
- [Section index](#section-index)
- Generated key tables: [scheduling](#scheduling) · [models](#models) · [features](#features) · [limits](#limits) · [piggybacks](#piggybacks) · [graph_view](#graph_view) · [skills](#skills) · [personal](#personal)
- [Non-default piggyback keys](#non-default-piggyback-keys)
- [Accounts (M002+ nested schema)](#accounts-m002-nested-schema)
- [Secrets — `.claude/.env`](#secrets--claudeenv)
- [Editing safely](#editing-safely)

Run `./.wiki/wiki config keys` for the live, full list of every leaf key the schema exposes.

## Files at a glance

| File | Purpose | Tracked? |
|---|---|---|
| `<engine>/config.example.yaml` | Engine-shipped defaults + comments. Copied once at install; sync-checked against the schema by the test suite. | yes |
| `<vault>/.wiki/config.yaml` | Per-install overrides. Read by every script via `core.config.CONFIG`. | gitignored |
| `<vault>/.claude/.env` | Secrets (API keys, IMAP passwords). Loaded by `core.config` at import. | gitignored |
| `<vault>/.claude/.env.example` | Catalogue of every env-var the engine recognises. Seeded by `wiki seed`. | tracked (template) |

The `.env` file: only the **variable NAME** lives in `config.yaml` (e.g. `api_key_env: JAMIE_WORK_API_KEY`); the **value** lives in `.env`. Shell exports override `.env` values (`override=False` policy). A missing `.env` is a clean no-op.

## Section index

| Section | Lives in (`scripts/core/config_schema.py`) |
|---|---|
| `scheduling.*` | `Scheduling` dataclass |
| `models.*` | `Models` dataclass |
| `features.*` | `Features` dataclass |
| `limits.*` | `Limits` dataclass |
| `piggybacks.<task>.*` | `PiggybackTask` dataclass per task; defaults in `_default_piggybacks()` |
| `graph_view.*` | `GraphView` dataclass |
| `skills.*` | `Skills` dataclass |
| `personal.*` | `Personal` dataclass (accounts hold per-service sub-blocks: `reader`, `filter`, `gmeet`, `jamie`, `calendar`, `health`) |

<!-- BEGIN GENERATED TABLES — scripts/core/config_docs.py. Do not edit by hand: edit the field comments in scripts/core/config_schema.py, then run `uv run python scripts/core/config_docs.py --write`. -->

## scheduling

| Key | Default | Meaning |
|---|---|---|
| `scheduling.compile_after_hour` | `18` | Hour-of-day (0-23, local time per `timezone`) at which auto-compile + piggyback tasks may spawn from flush.py. |
| `scheduling.dedup_window_seconds` | `900` | Minimum seconds before the same session is re-captured (and its daily block replaced). |
| `scheduling.piggybacks_on_compile` | `true` | When true, a real (non-dry-run) `wiki compile` drains any due piggybacks (dream-cycle, lint, curiosity, daily-digest, …) at the end of the run, bypassing the `compile_after_hour` evening gate (per-task cooldowns still rate-limit). |
| `scheduling.timezone` | `"UTC"` | IANA timezone name used for human-friendly local-time decisions (compile_after_hour cutoff, daily-log filename, "reviewed" timestamps). |
| `scheduling.dream_cooldown_days` | `7` | M014 dream-cycle (entity-page re-synthesis). An entity whose `last_synthesized_at:` frontmatter is newer than this many days is skipped by `wiki dream --all-entities` and by the dream_cycle piggyback. |
| `scheduling.dream_priority.*` | *(nested)* | M017 — config-driven entity priority for dream-cycle selection. |
| `scheduling.dream_priority.default` | `1.0` | Base weight when nothing more-specific matches |
| `scheduling.dream_priority.paths` | `{}` | Path/glob → weight overrides. First match wins (fnmatch semantics). |
| `scheduling.dream_priority.domain` | `{}` | Domain-axis multipliers (M013 `domain:` frontmatter). |
| `scheduling.dream_priority.tags` | `{}` | Tag-axis multipliers. Strategy below controls multi-tag handling. |
| `scheduling.dream_priority.tag_strategy` | `"max"` | How to combine multiple tag-matches on one entity: "max" — take highest matching tag's multiplier (default) "sum" — sum all matching tag-multipliers "first" — take first tag in frontmatter order that has a config entry |
| `scheduling.dream_priority.status` | `{}` | Status-axis multipliers (M008 areas `status:` frontmatter + similar status-bearing pages). |
| `scheduling.concept_reconcile_cooldown_days` | `14` | Autonomous concept-reconciliation routine (concept-consistency-routine). |
| `scheduling.web_research_cooldown_days` | `30` | Dream web-research (issue #2). An entity whose `## Public Profile` block was refreshed within this many days is skipped by the web-research post-pass. |
| `scheduling.dream_insufficient_corpus_backoff_max_days` | `30` | Insufficient-corpus backoff (2026-06-02). When a dream RUNS but the agent returns the INSUFFICIENT_CORPUS sentinel (no synthesizable claims — common on generic-noun slugs whose mention-scan false-matches, e.g. `kontakte` hitting the German … |

## models

| Key | Default | Meaning |
|---|---|---|
| `models.compile_model` | `"claude-opus-4-8"` | Default Claude model for the AGENTIC surfaces that have no pin of their own: `wiki correct apply` (writes into knowledge/), the takes producer, the suggestions producer, folder-answer extraction, agent tasks, and the dream/intent fallbacks. |
| `models.compile_default_route_model` | `"claude-haiku-4-5-20251001"` | Model for the compile fall-through route (compile_stages/route.py `_DEFAULT_DISPATCH`) — substrates with no SUBSTRATE_PROMPTS row of their own. |
| `models.compile_large_source_model` | `"claude-opus-4-8[1m]"` | Compile retry model on kind=unknown (compile_stages.compile). |
| `models.dream_model` | `"claude-opus-4-8[1m]"` | Dream-cycle entity re-synthesis (M014). dream-entity is a kanonical fan-out workload: 1 entity-page Edit on top of N substrate Reads from its corpus (T1=10-30 files typical) + Grep/Glob exploration of knowledge/. |
| `models.intent_classify_model` | `"claude-haiku-4-5"` | Intent-classification model (intent-dispatch producer). |
| `models.folder_scan_provider` | `"claude-sdk"` | Folder-scan answer provider (M027-S04, Q9 seam). |
| `models.ollama_url` | `"http://localhost:11434"` | Ollama endpoint for every local-LLM call. |
| `models.vision_model` | `"gemma4:e4b"` | Vision model for screenshot OCR, pictures ingest, and YouTube Tier-3 frames. |
| `models.curiosity_model` | `"llama3.1:8b"` | Curiosity gap-detection. Needs *both* schema-honoring AND enough context to fit the curiosity prompt (compact index + source + folder listing). |
| `models.classify_model` | `"gemma4:e4b"` | Inbox / voice-punctuate classifier (local Ollama). |

## features

| Key | Default | Meaning |
|---|---|---|
| `features.curiosity_loop` | `true` | Gap detection after each compile run — writes follow-up requests to `raw/requests/`. |
| `features.vision_screenshots` | `true` | Local vision OCR for the screenshots collector. |
| `features.procmail_execution` | `true` | Allow suggestions/cli.py to call webmail Procmail APIs (server-side mail rules). |
| `features.concept_reconciliation` | `false` | Autonomous concept-reconciliation routine (concept-consistency-routine). |
| `features.health_trends` | `false` | Health-trend synthesis (`wiki health-trends`). |
| `features.clippings_sweep` | `true` | Pre-compile sweep of <vault>/Clippings/*.md into <vault>/raw/articles/ so Obsidian Web Clipper output reaches the source-glob. |
| `features.extract_takes` | `false` | M011 takes substrate. Default OFF — flip True after dogfooding. |
| `features.extract_intents` | `false` | Intent extraction (intent-dispatch). Post-compile pass that classifies an intake note (voice first) into an intent {kind, summary, confidence} and routes it to a per-kind handler (the `task` handler writes an operator- facing record to … |
| `features.dream_web_research` | `false` | Dream web-research (issue #2). When True, `wiki dream <slug>` runs a post-pass that researches PUBLIC entities (founders, execs, speakers) via Exa AI and writes a sentinel-managed `## Public Profile` block. |
| `features.suggestions_source_globs` | `["raw/notes/email/*.md"]` | Source-glob allowlist for the suggestions post-pass. |
| `features.voice_punctuate` | `true` | Pre-process voice transcripts through the local classify_model (Ollama) to add punctuation, sentence-case, and German-noun capitalization. |
| `features.compile_callback_gate` | `true` | Path-scope enforcement for compile + dream agent Write/Edit calls via a `can_use_tool` callback (Python-side gate). |
| `features.extract_picture_metadata` | `true` | Deterministic per-picture metadata extraction (EXIF + Android screenshot filename pattern). |
| `features.materialize_backlinks` | `true` | Corpus-wide post-compile pass that writes a sentinel-managed `## Backlinks` footer into every knowledge/<article>.md so AI agents reading the markdown directly get backlink information without corpus-wide ripgrep. |
| `features.relativize_wikilinks` | `true` | Corpus-wide post-compile pass that rewrites every wikilink to a path relative to its containing article (a link in a markdown file is relative to that file). |
| `features.operator_reports` | `false` | M019 master switch — operator-self-reports surface. |
| `features.dream_require_entity_substrate` | `true` | Pre-flight skip for dream-entity passes whose corpus carries ZERO entity-specific substrate — i.e. the only files are date-pulled daily digests that (provably, since the mention-scan found 0 recent/authored/ tier-2 hits) do not mention the … |

## limits

| Key | Default | Meaning |
|---|---|---|
| `limits.compile_max_files` | `30` | Per-compile-run file cap (rate-limit guard for the 5h Opus window). |
| `limits.compile_max_consecutive_failures` | `3` | Abort the batch after N back-to-back compile failures. |
| `limits.flush_max_retries` | `3` | Retries for flush-extraction calls. |
| `limits.flush_retry_delay_seconds` | `30` | Delay between flush retries (seconds). |
| `limits.flush_assistant_text_budget_chars` | `50000` | Per-class budgets for session/pre-compact flush context (hooks/_transcript.py). |
| `limits.flush_user_text_budget_chars` | `10000` | Budget for user-prompt text in the flush context (same scheme as above). |
| `limits.flush_tool_summary_budget_chars` | `10000` | Budget for one-line tool summaries in the flush context (same scheme). |
| `limits.dashboard_refresh_timeout_s` | `300` | Best-effort dashboard (stats+lint) refresh budget after a flush. |
| `limits.screenshot_resize_width` | `512` | Pixel width screenshots are downscaled to before the vision model. |
| `limits.screenshot_timeout_seconds` | `60` | Per-screenshot Ollama timeout (seconds). |
| `limits.ollama_connect_timeout_s` | `10` | TCP connect timeout for every Ollama HTTP call (ollama_client.py). |
| `limits.piggyback_max_runtime_s` | `14400` | Hard wall-clock cap the piggyback runner (core/piggyback_runner.py) enforces on every spawned piggyback. |
| `limits.doctor_piggyback_stale_factor` | `4` | `wiki doctor` substrate-freshness threshold: an enabled piggyback whose last fire is older than factor × its cooldown_hours is flagged stale (collector dark — audit 2026-08-25 found substrates silently off for weeks with nothing surfacing … |
| `limits.doctor_piggyback_stale_min_hours` | `24` | Floor under that threshold. Piggybacks fire only when the operator compiles/flushes, so factor × a short cadence flags every quiet stretch (live: `voice`, 1h cadence, warned after 12h). |
| `limits.review_ollama_timeout_s` | `300` | review-wiki.py per-article Ollama read timeout (was a hardcoded 300 in the script). |
| `limits.review_consecutive_failure_abort` | `5` | review-wiki.py fail-fast: abort the full-vault sweep after this many CONSECUTIVE per-article Ollama failures. |
| `limits.review_checkpoint_every` | `25` | review-wiki.py incremental checkpoint: flush the partial JSON report every N reviewed articles so an aborted/killed sweep keeps its work (the report was previously written only at end-of-sweep). |
| `limits.review_max_sweep_runtime_s` | `12600` | review-wiki.py soft sweep deadline (seconds). |
| `limits.voice_punctuate_timeout_s` | `120` | Voice punctuation Ollama-chat timeout (collectors/voice.py). |
| `limits.curiosity_max_gaps` | `3` | Max curiosity-requests written per compile run. |
| `limits.curiosity_min_source_chars` | `500` | Skip the curiosity pass for sources shorter than this (chars). |
| `limits.curiosity_timeout_s` | `240` | ollama chat_schema timeout for curiosity gap-detection (gemma4:e4b on long YT-notes regularly hits >90s) |
| `limits.curiosity_max_prompt_chars` | `250000` | Pre-flight cap for the curiosity-pass prompt (Ollama side, not Claude). |
| `limits.curiosity_source_globs` | `["raw/transcripts/*", "raw/articles/*", "raw/notes/*", "daily/*"]` | Curiosity quality gates (2026-05-15 quality arc). |
| `limits.curiosity_exclude_globs` | `["raw/notes/email/deep-*"]` | `curiosity_exclude_globs`: denylist subtracted from the allowlist above. |
| `limits.curiosity_folder_confidence_min` | `3` | `curiosity_folder_confidence_min`: integer 1-5 self-reported by the LLM per gap. |
| `limits.curiosity_folder_max_candidates` | `40` | `curiosity_folder_max_candidates`: when the digests overflow the prompt budget, the producer does NOT inject the folder structure — it injects the top-N candidate files retrieved by rarity-weighted keyword match (rarer keyword = stronger … |
| `limits.curiosity_quote_min_anchor_tokens` | `5` | `curiosity_quote_min_anchor_tokens`: the source_quote gate accepts the quote if ANY contiguous N-token window from the (normalised) quote appears in the (normalised) source excerpt. |
| `limits.sparse_threshold_words` | `200` | Lint warns (`sparse_article`) under this body word count per article. |
| `limits.connection_min_words` | `50` | Connection-article quality gate (M012, 2026-05-16). |
| `limits.reports_default_lookback_days` | `14` | M019 default lookback for clinical-screen instruments (PHQ-9, GAD-7, ASRS-v1.1, WHO-5, MEQ-19). |
| `limits.youtube_max_frames` | `30` | YouTube ingest (scan-youtube.py — see also CONFIG.piggybacks.scan_youtube) Tier-3 visual: cap frames per video |
| `limits.youtube_max_duration_s` | `10800` | Tier-3: skip videos longer than this (3h default) |
| `limits.youtube_frame_resize_width` | `512` | ffmpeg downscale before vision model |
| `limits.youtube_vision_timeout_s` | `240` | Per-frame Ollama call timeout. Must cover a MODEL SWAP, not just inference: a single-GPU Ollama host evicts the resident model, and a swap to the ~10 GB vision model measured 63 s on kcma-d8 with a warm page cache (2026-08-26) — the old 90 … |
| `limits.youtube_aggregate_timeout_s` | `300` | final synthesis call timeout |
| `limits.jamie_request_timeout_s` | `30` | Jamie ingest (collectors/jamie.py — see also CONFIG.piggybacks.jamie). |
| `limits.jamie_max_per_run` | `50` | default cap per account (overridable via the per-account jamie sub-block) |
| `limits.gmeet_request_timeout_s` | `30` | Google Meet ingest (collectors/gmeet.py — see also CONFIG.piggybacks.gmeet). |
| `limits.gmeet_max_per_run` | `50` | default cap; per-account override is the gmeet sub-block's max_per_run |
| `limits.gmeet_export_dead_letter_attempts` | `3` | export failures per doc-id before it parks in the dead-letter |
| `limits.gmeet_export_dead_letter_reprobe_days` | `7` | days a parked doc-id waits before one re-probe (re-granted access heals) |
| `limits.calendar_request_timeout_s` | `30` | Google Calendar ingest (collectors/calendar.py — see also CONFIG.piggybacks.calendar). |
| `limits.calendar_max_per_run` | `500` | default per-calendar cap; per-account override is the calendar sub-block's max_per_run |
| `limits.calendar_backfill_days` | `90` | default past window per run (events with updated >= now-N for delta sync) |
| `limits.calendar_future_days` | `7` | default future window re-fetched every run (catches mutations on upcoming events) |
| `limits.oura_request_timeout_s` | `30` | Oura health ingest (collectors/health.py — Phase 1, oura-only). |
| `limits.oura_max_backfill_days` | `90` | default first-run window; per-account override via backfill_days |
| `limits.sdk_max_buffer_size_mb` | `50` | Claude Agent SDK per-message buffer (stream-json line buffer). |
| `limits.query_max_prompt_chars` | `500000` | Pre-flight cap for `wiki query` prompts. A query embeds the compact index + hard facts; once the knowledge base outgrows the model's context window the SDK dies with an opaque exit-1 / empty-stderr `kind=unknown`. |
| `limits.compile_max_prompt_chars` | `400000` | Pre-flight cap for `wiki compile` prompts. Embeds compact index + AGENTS.md + facts + raw source. |
| `limits.compile_max_turns` | `20` | Tool-turn ceiling per compile run. 30 was generous enough to let the model loop on a huge source until it hit the context window (see KNOWLEDGE.md: gmeet 138 KB transcript). |
| `limits.compile_max_tokens_per_file` | `500000` | Hard per-file TOKEN guard. When a single compile_file call's total token use (input+output, summed from AssistantMessage.usage) exceeds this, the file is marked failed with `kind=tokens_exceeded` and the batch ABORTS (not skips — operator … |
| `limits.compile_skip_substrate_types` | `["email-delta", "folder-index"]` | Substrate types (frontmatter `type:` value) that compile.py skips in batch mode. |
| `limits.folder_index_max_depth` | `0` | Watched-folder index knobs (M027-S02, `wiki index`). |
| `limits.folder_index_recent_n` | `20` | Top-N entries in the digest's recent-changes view. |
| `limits.daily_email_top_senders` | `5` | Email daily-rollup signal (beta, 2026-05-23). |
| `limits.daily_email_sample_subjects` | `12` | Sample size of most-recent subjects in the same daily email block. |
| `limits.compile_per_call_timeout_s` | `600` | Per-compile-call timeout (seconds). Wraps the `async for message in query(...)` iterator with `asyncio.wait_for`. |
| `limits.dream_per_call_timeout_s` | `300` | Dream-cycle per-message stall timeout (M014). |
| `limits.compile_retry_long_context_on_unknown` | `true` | Retry once with `compile_large_source_model` (the 1M-context Opus variant) when a compile call returns kind=unknown — the silent exit-1 / empty-stderr signature of mid-stream context overflow from tool-turn fan-out into knowledge/ articles. |
| `limits.compile_failure_backoff_s` | `60` | Seconds to sleep after a kind=unknown failure before retrying with the long-context model. |
| `limits.compile_retry_long_context_min_source_chars` | `10240` | Skip the long-context retry on small sources. |
| `limits.compile_skip_on_long_context_unknown` | `true` | When a kind=unknown failure has no further retry path available (small source skipping retry, OR already on the long-context model), treat it as a skip rather than a hard failure: log WARNING, return `_skipped`, and don't count toward … |
| `limits.compile_aggregated_max_consecutive_failures` | `3` | Circuit-breaker for aggregated-memory chunked compiles. |
| `limits.compile_role_default_by_location` | `true` | When True (default), `infer_compile_role()` falls back to LOCATION_DEFAULTS (raw/daily/inbox/knowledge → source-only) for files that omit the `compile_role:` frontmatter key. |
| `limits.extract_takes_source_globs` | `["raw/transcripts/*", "raw/transcripts/**/*", "raw/voice/*", "daily/*"]` | M011 takes substrate. fnmatch-style globs limiting which sources get an extract-takes pass after compile (gated by CONFIG.features.extract_takes). |
| `limits.extract_takes_timeout_s` | `180` | Per-call timeout for the extract-takes SDK invocation (seconds). |
| `limits.extract_takes_max_per_source` | `12` | Cap on takes emitted per source. Stops a noisy meeting from spawning 30 low-signal lines for the same holder. |
| `limits.intent_source_globs` | `["raw/voice/*", "raw/inbox-mobile/pictures/*.md"]` | Intent-dispatch (gated by CONFIG.features.extract_intents). |
| `limits.intent_classify_timeout_s` | `120` | Per-call timeout for the intent-classification SDK invocation (seconds). |
| `limits.intent_min_confidence` | `"high"` | Confidence floor (low\|medium\|high). An intent classified below this is logged but NOT dispatched to a handler — keeps the borderline idea/question out of `tasks/`. |
| `limits.dream_entity_max_prompt_chars` | `415000` | M014 dream-cycle (entity-page re-synthesis). Per-entity prompt-SIZE guard (chars). |
| `limits.dream_cycle_max_tokens_per_run` | `2000000` | Cumulative per-run TOKEN ceiling for `wiki dream --all-entities` and the dream_cycle piggyback: the sweeper stops once cumulative real tokens (input+output) cross this. |
| `limits.concept_reconcile_max_files_per_fact` | `25` | Autonomous concept-reconciliation routine (concept-consistency-routine). |
| `limits.concept_reconcile_max_facts_per_run` | `10` | Max facts reconciled per `wiki reconcile` run / concept_reconcile piggyback. |
| `limits.concept_reconcile_max_turns` | `15` | Turn budget for the strict concept-reconciliation agent. |
| `limits.correct_apply_max_turns` | `50` | Turn budget for the operator-driven `wiki correct apply` agent (M028). |
| `limits.correct_broad_term_threshold` | `15` | `wiki correct add` warns when a negation_term matches more than this many existing articles — over-broad terms become lint noise / large apply blast radii (M028 issue #5). |
| `limits.health_trends_recent_months` | `6` | Health-trend synthesis (`wiki health-trends`). |
| `limits.health_trends_min_coverage_days` | `10` | Min covered days for a metric to appear in the trends block (drops near-empty series so no fake trends form over data gaps). |
| `limits.dream_tier1_recent_count` | `20` | M016 dream-cycle sampled-activation knobs (2026-05-17). |
| `limits.dream_tier1_digest_days` | `7` | Tier 1 — last N `daily/<date>.md` rollups always-included. |
| `limits.dream_tier2_sample_count` | `50` | Tier 2 — weighted-sample size from substrate older than Tier 1 covers. |
| `limits.dedup_fuzzy_threshold` | `0.85` | `wiki dedup` (entity-dedup, issue #3). Fuzzy-title match floor 0..1 for a pair to be proposed as a duplicate candidate. |

## piggybacks

Recurring maintenance/collector tasks drained after `scheduling.compile_after_hour`
(flush path) or at the end of every real `wiki compile`
(`scheduling.piggybacks_on_compile`). Each entry takes `enabled` (bool),
`cooldown_hours` (int), and optionally `max_per_run` (int). Defaults live in
`core/config_schema.py:_default_piggybacks` — for Registry collectors the name
is `CollectorSpec.name` and the cooldown is parity-tested against the SPEC.
`max_per_run` appears only where a consumer reads it (built-in command
templates + the self-capping screenshots/pictures collectors); the
jamie/gmeet/calendar caps live in `limits.*_max_per_run` + the per-account
sub-blocks instead.

| Task | enabled | cooldown_hours | max_per_run |
|---|---|---|---|
| `piggybacks.email` | `true` | 24 | — |
| `piggybacks.lint_structural` | `true` | 24 | — |
| `piggybacks.review_wiki` | `true` | 168 | — |
| `piggybacks.optimize_claude_md` | `false` | 24 | — |
| `piggybacks.screenshots` | `true` | 24 | 50 |
| `piggybacks.curiosity_followup` | `true` | 6 | 5 |
| `piggybacks.jamie` | `true` | 6 | — |
| `piggybacks.gmeet` | `true` | 6 | — |
| `piggybacks.calendar` | `true` | 6 | — |
| `piggybacks.health` | `true` | 24 | — |
| `piggybacks.voice` | `true` | 1 | — |
| `piggybacks.capture` | `true` | 1 | — |
| `piggybacks.pictures` | `true` | 6 | 20 |
| `piggybacks.daily_digest_yesterday` | `true` | 24 | — |
| `piggybacks.retry_failed_flushes` | `true` | 24 | 5 |
| `piggybacks.dream_cycle` | `true` | 24 | 3 |
| `piggybacks.study_run_due` | `false` | 6 | — |
| `piggybacks.analyst_pass2` | `false` | 168 | — |
| `piggybacks.publish` | `true` | 6 | — |

## graph_view

| Key | Default | Meaning |
|---|---|---|
| `graph_view.mode` | `"knowledge-only"` | One of: knowledge-only \| full-vault \| sources-only \| custom. |
| `graph_view.custom_search` | `""` | Obsidian search expression used when mode=custom. |
| `graph_view.domain_tags` | `[]` | Tag names treated as "domain anchors" for graph-view coloring and qa-schema lint. |

## skills

| Key | Default | Meaning |
|---|---|---|
| `skills.global_install` | `false` | When true, `wiki skills install` / `wiki skills sync` also link global-eligible skills (currently: use-llm-wiki) into ~/.claude/skills/ and register this vault in ~/.config/llm-wiki/vaults, so agents working in *any* project can discover … |

## personal

| Key | Default | Meaning |
|---|---|---|
| `personal.primary_account` | `""` | default account; used as fallback in compile.py and for prompt rendering |
| `personal.accounts` | `{}` | account-id -> per-account dict. Schema (M002+): email (str) sender identity; required label (str, optional) display label in reports reader (dict, optional) {kind: thunderbird-mbox\|gmail-api\|…, <kind-specific keys>} filter (dict, optional) … |
| `personal.email_folders` | `[]` | ordered list of {path, desc} dicts; drives both compile_curiosity.md listing AND compile.py's schema enum (single source of truth) |
| `personal.curiosity_folders` | `[]` | Optional subset of email_folder paths considered by the curiosity loop. |
| `personal.watched_folders` | `[]` | M027: folders the curiosity loop may scan as substrate (local + NAS). |
| `personal.project_examples` | `[]` | short list of project / product names rendered into scan_screenshots_vision.md as concrete examples |
| `personal.calendar_skip_keywords` | `[]` | Substring keywords whose presence in a calendar event title marks it as a holiday / observance to skip during collectors/calendar.py. |
| `personal.thunderbird_profile` | `""` | Path to local Thunderbird profile directory (mbox + filter roots live here). |
| `personal.firefox_profile` | `""` | Path to a local Firefox profile directory (e.g. ~/Library/Application Support/Firefox/Profiles/<id>.default-release on macOS, or ~/.mozilla/firefox/<id>.default-release on Linux). |
| `personal.stg_backup_dir` | `""` | Path to a Simple Tab Groups (STG) backup directory (where the extension writes its periodic *.json snapshots). |
| `personal.voice_inbox` | `""` | Path to a directory the operator dumps dictation transcripts into (any tool that writes .txt or .md works — OpenWhispr is the default recommendation; FluidVoice / macOS dictation / Hammerspoon snippets also work). |
| `personal.voice_transcribe_model` | `""` | Audio-transcription via whisper.cpp (ad-hoc, 2026-05-28). |
| `personal.voice_transcribe_language` | `"auto"` | Language hint passed to whisper-cli. "auto" auto-detects (slightly slower); language code like "de" or "en" skips detection. |
| `personal.voice_transcribe_threads` | `4` | Threads passed to whisper-cli (-t N). 4 is a sensible default on current Apple Silicon; raise for big models on M-series Max chips. |
| `personal.voice_transcribe_binary` | `""` | Override path to the whisper.cpp binary. Empty = auto-detect `whisper-cli` from $PATH (brew installs to /opt/homebrew/bin). |
| `personal.voice_transcribe_ffmpeg` | `""` | Override path to ffmpeg. Empty = auto-detect from $PATH. |
| `personal.picture_inbox` | `""` | Path to a directory the operator drops camera / phone photos into for ingest. |
| `personal.inbox_bridges` | `[]` | 2026-05-28 inbox-bridge. List of {remote, local, mode?, enabled?} dicts describing folders to mirror from network-mounted / sandbox-restricted paths (e.g. `~/Library/CloudStorage/GoogleDrive-…/wiki-inbox/pictures/`) into local … |
| `personal.exa_api_key` | `""` | Dream web-research (issue #2). Exa AI API key for the public-entity enrichment post-pass. |
| `personal.capture_inbox` | `""` | M025 quick-capture-correction loop. Path to a directory the operator one-taps cryptic notes / article snippets into (any tool that writes .txt / .md / .html — WhatsApp-self-group export, Notion quick-note sync, a shortcut). |
| `personal.reports_dir` | `"reports"` | M019 operator-self-reports surface. Directory under vault root where `reports/studies/<id>/runs/<ts>/*.md` (deterministic study output) and `reports/analyses/<ts>.md` (analyst-agent output, S05) accumulate. |
| `personal.implicit_operator_author` | `null` | Canonical vault-owner identifier. The value (e.g. "alex") is the slug of the operator's own page at `knowledge/people/<value>.md` and drives two things at compile time: 1. Owner-block injection — `compile.py:_build_owner_block()` renders a … |
| `personal.domains` | `["company", "personal", "ai", "meta"]` | M013 (2026-05-16): optional `domain:` frontmatter axis on `knowledge/` articles. |
| `personal.output_language` | `"auto"` | Issue #4 (2026-06-13): pin the OUTPUT prose language of compiled `knowledge/**` articles. |

## publish

| Key | Default | Meaning |
|---|---|---|
| `publish.enabled` | `false` | Master switch. Off = the feature does not exist: no network, no state. |
| `publish.endpoint` | `""` | Streamable-HTTP MCP endpoint of the operator's context-mcp instance, e.g. https://dev.meinkontext.de/mcp. |
| `publish.wiki_slug` | `"llm-wiki"` | Identity of the managed wiki on the server (create_wiki slug — stable, do not rename after the first publish) and its display name. |
| `publish.wiki_name` | `"LLM Wiki"` | — |
| `publish.roots` | `["knowledge"]` | Vault roots whose markdown publishes (vault-relative folder names). |

<!-- END GENERATED TABLES -->

## Non-default piggyback keys

Three piggyback names have **no defaults entry** — their block's *absence* is the off-switch, and adding one enables/configures the task:

- `piggybacks.scan_youtube` — the YouTube collector reads `max_per_run` from this block as its inbox-drain cap when present (it's a `piggyback_default=False` collector: operator-paced, never auto-spawned).
- `piggybacks.concept_reconcile` — the autonomous concept-reconciliation routine only auto-runs with this block present AND `features.concept_reconciliation: true` (double gate).
- `piggybacks.health_trends` — health-trend synthesis only auto-runs with this block present AND `features.health_trends: true` (double gate).

## Accounts (M002+ nested schema)

```yaml
personal:
  accounts:
    work:
      email: alex@example.com           # required — used in prompts + reports
      label: "Work"                     # optional — display label
      reader:
        kind: thunderbird-mbox          # thunderbird-mbox | gmail-api | imap
        mbox_paths:                     # relative to thunderbird_profile
          - ImapMail/server/INBOX.mbox
      filter:
        kind: all-inkl-procmail         # thunderbird-msgfilter | all-inkl-procmail | gmail-api
        imap_user_env: WORK_IMAP_USER   # env var name (not value)
        imap_pass_env: WORK_IMAP_PASS
        imap_host: mail.example.com
```

`reader.kind` and `filter.kind` dispatch independently — an account can read via Thunderbird mbox and write filter rules via All-Inkl Procmail (the legacy hybrid). Unknown kinds are silently skipped (graceful agnostic).

**Reader kinds:**

- `thunderbird-mbox` — reads local mbox files a Thunderbird profile already synced. No credentials in the engine; the mail client owns auth. Keys: `mbox_paths` (relative to `personal.thunderbird_profile`).
- `gmail-api` — Gmail API over OAuth2. Needs an OAuth client at `.claude/gmail-oauth-client.json` and a one-time `wiki gmail-auth <id>`. No extra `reader` keys.
- `imap` — generic IMAP, for accounts with **no local client and no Google Cloud project**. Auth is an IMAP login with a username + **app password**. For Gmail: enable 2-Step Verification, then generate an App Password (`myaccount.google.com/apppasswords`) — it is **16 lowercase letters**; paste those 16 chars into `.env` **without the display spaces** (Google shows it grouped as `xxxx xxxx xxxx xxxx`). Keys: `imap_host` (required), `imap_pass_env` (required — env-var *name* holding the password), `imap_user_env` (optional — env-var name for the username; omit → falls back to `account.email`), `folders` (optional list — only scan these; omit → all folders, which on Gmail includes the `[Gmail]/All Mail` per-label duplicate).

The pre-M002 flat-account schema (`mbox_paths`, `imap_host`, `has_procmail` directly on the account) is rejected at config load with an explicit migration error. Note this only rejects those keys at the *account* level — nested inside `reader:` / `filter:` they are the normal schema.

### Jamie (multi-tenant)

```yaml
personal:
  accounts:
    work:
      email: alex@example.com
      jamie:
        kind: jamie-api
        api_key_env: JAMIE_WORK_API_KEY   # env var holding the jk_... key
        key_type: personal                # personal | workspace
        since: ""                         # ISO date "2026-01-01" — first-install backfill cap
        max_per_run: null                 # null inherits CONFIG.limits.jamie_max_per_run
```

Per-account `jamie:` sub-block with `kind: jamie-api`, mirroring the `reader:` / `filter:` / `gmeet:` / `calendar:` / `health:` pattern. An account with no `jamie:` sub-block is silently skipped; an account whose `api_key_env` resolves to an empty/unset env var is also skipped (graceful-agnostic) — the rest of the loop still runs. State per account at `state/jamie-state.json` keyed by account-id.

## Secrets — `.claude/.env`

Loaded automatically at import via `core.config.load_dotenv(<vault>/.claude/.env, override=False)`. Add new entries to `<engine>/templates/.claude/.env.example` to ship them to fresh vaults via `wiki seed`.

| Variable | Used by | Notes |
|---|---|---|
| `OPENAI_API_KEY` | Whisper audio transcription (and future OpenAI paths) | — |
| `JAMIE_<ACCOUNT>_API_KEY` | `collectors/jamie.py` | One per account with a `jamie:` sub-block. Name matches the `api_key_env` field; `<ACCOUNT>` is your choice. Pro/Team/Enterprise plan. `jk_` prefix. Generate in Jamie: Settings → Developers → API Keys. |
| `IMAP_<ACCOUNT>_USER` / `_PASS` | `adapters/mailbox/imap.py` (`imap` reader), `suggestions/backends/imap.py`, `adapters/mailbox/allinkl.py` | `<ACCOUNT>` matches the value of `imap_user_env` / `imap_pass_env` in the account's `reader` (kind: imap) or `filter` block. Gmail needs an App Password — 16 lowercase chars, pasted without the display spaces. |
| `EXA_API_KEY` | dream web-research post-pass | Fallback when `personal.exa_api_key` is blank — the recommended place for the key. |
| `NAS_HOST` / `NAS_USER` / `NAS_PASS` | Future `scan-nas.py` / SMB-backed collectors | — |
| `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` | adhikasp/mcp-linkedin MCP server | **Not loaded from `.env`** — set in `~/.claude.json` under `mcpServers.linkedin.env`. Listed only as a reminder. |

## Editing safely

- **Programmatic edits** (`wiki config set`) round-robin-backup the file to `.wiki/state/config-backups/` (last 10 retained) before writing. PyYAML drops comments on round-trip — manual edits in `$EDITOR` preserve them.
- **Round-trip caveat**: if you `wiki config set` after hand-editing, the next read-back may not match your file byte-for-byte (comment loss, key reordering inside a section). The dataclass semantics survive — values stay correct.
- **Type safety**: a value that doesn't fit the schema type (string for an int knob, `null` for a non-optional) is rejected at load with a WARNING naming the dotted key path, and the engine default is used. List/dict-valued keys can't be set from the CLI — edit `config.yaml` directly.
