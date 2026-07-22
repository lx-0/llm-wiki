# Features — Implementation Map

Living overview of every engine feature: what's documented, where it's implemented, how to trigger it, and where reality drifts from the docs. Keep this in sync whenever a feature lands, moves, or gets retired.

**Status legend:**

- 🟢 **live** — implemented, wired into the CLI / piggyback / hook path, exercised in tests or by the operator
- 🟡 **partial** — implementation exists but a piece is missing (consumer gone, CLI wrapper missing, doc references stale)
- 🔴 **broken** — documented as working but cannot be invoked the way the docs claim
- 🟠 **planned** — referenced as a near-future feature; no implementation yet
- ⚫ **removed** — formerly shipped, intentionally taken out; kept here as anti-drift anchor

> Cross-reference: every entry below should appear in at least `docs/PROCESS.md` (process description), `docs/cli.md` (CLI surface), and one of the high-level docs (`README.md` / `docs/concept.md`). A feature that lives only in one of those places is a documentation gap; flag it in the **Known gaps** column.

## Contents

- [Capture (Path A)](#capture-path-a) — session-end hooks, flush pipeline, daily/
- [Ingest (Path B)](#ingest-path-b) — Collectors + legacy scanners + drop boxes
- [Compilation & query](#compilation--query) — compile.py, query.py, lint.py
- [Side loops (post-compile)](#side-loops-post-compile) — curiosity, suggestions, claude-md-optimizer, wiki-review
- [Vault UX layer](#vault-ux-layer) — dashboard, MOCs, hard facts, agent tasks, pin
- [Lifecycle CLI](#lifecycle-cli) — setup, status, update, seed, config, hooks, skills
- [Engine seams](#engine-seams-cross-cutting-030-arc) — cross-cutting plumbing from the 0.3.0 arc
- [Known gaps & drift](#known-gaps--drift) — pinned reality-vs-docs checks

---

## Capture (Path A)

| Feature | Status | Code | Trigger | Docs | Known gaps |
|---|---|---|---|---|---|
| Session capture (start/end) | 🟢 | `hooks/session-start.py`, `hooks/session-end.py`, `hooks/_transcript.py`, `scripts/flush.py`, `scripts/core/flush_pipeline.py` | Claude Code / Codex / Gemini / Cursor session lifecycle | README "What you get", PROCESS §2, concept "Sensory buffer" | — |
| Pre-compact safety flush | 🟢 | `hooks/pre-compact.py` | Context-window compaction in Claude Code | PROCESS §2 | — |
| Daily log append (`daily/YYYY-MM-DD/sessions.md`) | 🟢 | `scripts/core/flush_pipeline.py:append_to_daily` | flush.py extraction success | PROCESS §2, concept "Episodic memory" | Post-2026-05-15 rollup arc: writes to per-source subfolder, not flat root. |
| Per-source daily-rollup writer | 🟢 | `scripts/core/daily_capture.py` (fcntl-flocked, `KNOWN_SOURCES`-validated `append` / `replace_section`) | health/voice/jamie/gmeet/email collectors mirror their primary output as one-liners | PROCESS §2, AGENTS.md Layer 2 | New 2026-05-15. 16 unit tests in `tests/test_daily_capture.py`. |
| Daily digest (`daily/<date>.md`) | 🟢 | `prompts/agents/daily-digest.md` (claude-haiku-4-5), `scripts/daily_digest_runner.py` (piggyback wrapper) | `wiki agent daily-digest --var date=…`; auto-fires as `daily_digest_yesterday` piggyback (24h cooldown) | PROCESS §2 piggyback table, cli.md | ≤500-word distillation across all five per-source captures; refuses to overwrite non-digest frontmatter. |
| Migration / backfill / cleanup scripts | 🟢 | `scripts/migrate_daily_to_rollup.py`, `scripts/backfill_daily_rollup.py`, `scripts/cleanup_legacy_daily_roots.py` | operator one-shots after engine upgrade | cli.md "Operator-invoked one-shot scripts" | Migration is copy-not-move; cleanup verifies byte-match before delete. |
| Failed-flush archival + retry | 🟢 | `scripts/core/flush_pipeline.py:archive_failure`, `scripts/retry-failed-flushes.py` | flush.py extraction failure (rate limit, SDK error) → archived to `.wiki/sessions/failed-flushes/`; piggyback retries later | PROCESS §2 piggyback table | — |
| Multi-agent hook install | 🟢 | `lib/agents.sh`, `lib/hooks.sh` | `wiki hooks install` | README "Multi-agent hooks", cli.md "Hooks & skills" | Four agents wired: claude / codex / gemini / cursor. PI (`pi`) and opencode are documented as NOT supported in `help_hooks`. |

## Ingest (Path B)

### Registry-discovered Collectors (`SPEC` + `@register` + `run()`)

| Collector | Status | Code | Output | Docs |
|---|---|---|---|---|
| `email` | 🟢 | `scripts/collectors/email_collector.py` + adapters in `scripts/adapters/mailbox/{thunderbird,gmail,allinkl,base}.py` | `raw/notes/email/<account>-<date>.md` | PROCESS §3 (scanners) |
| `jamie` | 🟢 | `scripts/collectors/jamie.py` | `raw/transcripts/jamie/<date>--<slug>--<id>.md` | PROCESS §3, README jamie line |
| `gmeet` | 🟢 | `scripts/collectors/gmeet.py` (Drive API via `core/google_oauth.py`) | `raw/transcripts/gmeet/<date>--<slug>--<meeting-key>.md` (paired Summary + Transcript) | `docs/setup-gmeet.md` |
| `voice` | 🟢 | `scripts/collectors/voice.py` (folder-watch on `personal.voice_inbox`; text `.txt/.md` ingests as-is; audio `.m4a/.mp4/.mp3/.wav/.flac/.ogg/.aac` transcribed via `whisper-cli` subprocess when `personal.voice_transcribe_model` is set — m4a/mp4/aac route through ffmpeg first → 16 kHz mono PCM; body punctuated via Ollama `classify_model` when `features.voice_punctuate=true` — default — with raw preserved verbatim in frontmatter `raw_transcript:`, fallback-to-raw on Ollama failure; `limits.voice_punctuate_timeout_s=120` absorbs gemma4:e4b cold-call) | `raw/voice/voice-<date>-<HHMM>-<slug>.md` | `docs/setup-voice.md`, `.ytstack/backlog/voice-intake.md`, `.ytstack/AD-HOC-voice-audio-ingest-SUMMARY.md` |
| `pictures` | 🟢 | `scripts/collectors/pictures.py` (folder-watch on `personal.picture_inbox`; per-file gemma4 vision via `scan_pictures_vision`; archive-as-dedup with per-image sidecar; batch report `type: picture-batch` dispatches to `compile_pictures.md`) | `raw/notes/pictures/pictures-<slug>.md` + `raw/notes/pictures/thumb/<file>` | inline in this file + `prompts/scan_pictures_vision.md` |

Dispatcher: `scripts/collectors/cli.py` (`wiki collect <name>` and `wiki collect --list`). Piggyback wiring: `flush.py:_build_piggyback_tasks` auto-discovers Collectors with `SPEC.piggyback_default=True`.

### Substrate scanners (all on the Collector Protocol since 2026-05-14)

| Scanner | Status | Code | Output |
|---|---|---|---|
| `calendar` | 🟢 | `scripts/collectors/calendar.py:CalendarCollector` (Registry, **piggyback**, OAuth via `core/google_oauth.py`) + `wiki calendar-auth <id>` bootstrap + `scripts/adapters/calendar/google.py` REST client | `raw/notes/calendar/<YYYY-MM-DD>.md` per-date rollup (one file per date, regenerated end-to-end per run; operator prose preserved outside the managed `<!-- calendar:events:* -->` region) + `knowledge/concepts/<slug>.md` for recurring series |
| `browser` | 🟢 | `scripts/collectors/scan_browser.py:BrowserCollector` (Registry) + script-mode CLI | `raw/notes/browser/browser-overview-<date>.md` |
| `tabs` | 🟢 | `scripts/collectors/scan_tabs.py:TabsCollector` (Registry) + script-mode CLI | `raw/notes/browser/tab-groups-overview-<date>.md` |
| `screenshots` | 🟢 | `scripts/collectors/scan_screenshots.py:ScreenshotsCollector` (Registry, **piggyback**) + script-mode CLI | `~/Screenshots/<file>.md` (canonical) + `raw/notes/screenshots/thumb/<file>.png` + `raw/notes/screenshots/screenshots-<slug>.md` (batch report) |
| `youtube` | 🟢 | `scripts/collectors/scan_youtube.py:YoutubeCollector` (Registry) + script-mode CLI | `raw/notes/youtube/<channel>--<title>--<vid>.md` |

All collectors are Registry-discovered (`wiki collect --list` is the authoritative enumeration — thirteen today, incl. `capture` and, since 0.3.0, `folder-index`). `email` / `jamie` / `gmeet` / `calendar` / `voice` / `pictures` / `health` / `screenshots` carry `piggyback_default=True` (auto-run after compile); `tabs` / `browser` / `youtube` / `folder-index` are operator-invoked via `wiki collect <name>`. The migrated scanners keep a rich direct-CLI entry for per-URL/-flag use — `youtube` via `wiki ingest-youtube`, `folder-index` via `wiki index` (single root-id, `--force`), the rest via `uv run python scripts/collectors/scan_<name>.py`. The Collector `run()` path handles the piggyback-shaped behaviour (full sweep / inbox-drain); CLI-only flags (`--source`, `--url`, `--tier`) stay on the script entry.

Since 0.3.0 the account substrates (gmeet, jamie, calendar, health, email) build on the shared **account-loop harness** in `scripts/collectors/base.py` (`resolve_accounts` + `filter_accounts` + `Watermark` + `run_account_loop` + `migrate_flat_state`); the folder-watch trio (voice, capture, pictures) build on the **inbox-intake harness** (`scan_inbox` + `archive_to_zone` + `append_rollup`). `wiki collect --account <id>` is honored, gated on `SPEC.supports_account_loop` (clear error on singletons). `email` keeps its own `{"accounts":{...}}` state + two-mode loop; all state-file shapes are byte-compatible with pre-harness vaults.

### Drop-box / manual ingest (Preprocessor seam since 0.3.0)

The three in-vault intake normalizers share a Protocol + Registry mirroring collectors/producers (`scripts/preprocessors/base.py`; singletons, no accounts). `wiki preprocess --list` enumerates them; `wiki preprocess <name> [source] [--dry-run]` runs one (`scripts/preprocessors/cli.py`). The legacy entry points remain as thin shims.

| Feature | Status | Code | Trigger | Known gaps |
|---|---|---|---|---|
| Inbox classifier | 🟢 | `scripts/preprocessors/inbox.py` (shim: `scripts/process-inbox.py`) | `wiki process-inbox` / `wiki preprocess inbox` (+ `--no-compile` / `--dry-run` / `--model`) | The `.html` inbox delegation is in-process since 0.3.0 (was a broken cross-script subprocess that stranded every HTML drop) — a shipped feature restored. |
| HTML ingest (file or URL) | 🟢 | `scripts/preprocessors/html_ingest.py` (shim: `scripts/ingest-html.py`; named to avoid the stdlib `html` shadow) | `wiki ingest-html PATH-OR-URL [--mode content\|visual\|both]` / `wiki preprocess html <source>`; also auto-invoked in-process for inbox HTML drops | — |
| Clippings sweep | 🟢 | `scripts/preprocessors/clippings.py` (compat shim: `scripts/clippings_sweep.py`; compile.py's `import clippings_sweep` unchanged) | Auto-triggered by `compile.py:start` when `features.clippings_sweep=true`; moves `<vault>/Clippings/*` → `raw/articles/` before compile; `wiki preprocess clippings` | — |

## Compilation & query

| Feature | Status | Code | Trigger | Docs |
|---|---|---|---|---|
| Compile (raw + daily → knowledge) | 🟢 | `scripts/compile.py` | `wiki compile`, `wiki compile --all`, `wiki compile --file PATH`; auto-triggered by `flush.py` after `compile_after_hour` if daily/ changed | PROCESS §3, concept "Consolidation", README "Compile once, query fast" |
| Backlinks footer (corpus-wide post-pass) | 🟢 | `scripts/core/backlinks.py` (`build_backlinks_index`, `write_backlinks_footer`, `run_backlinks_pass`) | Auto-runs at end of every `wiki compile` (after per-source loop), gated by `features.materialize_backlinks` (default `true`). Writes a sentinel-managed `## Backlinks` block (delimited by `<!-- backlinks:begin -->` / `<!-- backlinks:end -->`) into every `knowledge/<article>.md` that has at least one incoming wikilink. Idempotent — unchanged corpus = zero writes. ~220 ms on a 1200-article vault. | PROCESS §3, `skills/use-llm-wiki/SKILL.md` (Read-tier) |
| Relativize wikilinks (corpus-wide post-pass) | 🟢 | `scripts/core/links.py` (`resolve_link`, `canonical_slug`, `relativize_text`, `run_relativize_pass`) | Auto-runs after the backlinks pass on every `wiki compile`, gated by `features.relativize_wikilinks` (default `true`). Rewrites every link to a path relative to its containing article so Obsidian resolves cross-article links from nested folders (a link in a markdown file is relative to that file). Resolves against disk — never fabricates a path; unresolvable links left untouched. Idempotent. One-shot migration: `scripts/migrations/relativize_wikilinks.py`. | PROCESS §3, AGENTS.md "Wikilinks", DECISIONS 2026-05-29 |
| Broken-link audit + fixer | 🟢 | `scripts/links_audit.py` | `wiki links` (report); `wiki links --fix` (approval-gated; `--yes` = bucket-tier only) | Categorizes unresolved links (media / placeholder / dangling); fixer rewrites high-confidence dangling refs (≡ exact-basename-different-bucket, ~ fuzzy cutoff 0.85), per-item approval. Missing-article refs reported, never auto-fixed. | cli.md, AGENTS.md "Wikilinks" |
| Query (natural language → answer) | 🟢 | `scripts/query.py` | `wiki query "…"`, `wiki query --file-back "…"` (writes Q&A article) | PROCESS §5, concept "Retrieval" |
| Lint (structural checks + 1 LLM) | 🟢 | `scripts/lint.py` | `wiki lint` (full); `wiki lint --structural-only` (cheap, piggyback) | PROCESS §5, concept "Self-healing", cli.md |

Since 0.3.0 (C04) the structural checks run as pure `check(ctx)` functions over a **LintContext** built once per run (canonical enumeration incl. `knowledge/MOCs/`, footer-aware link graph — engine-written `## Backlinks` footers don't count as edges — and structured `Issue` payloads that reconcile keys on instead of scraping prose). Dashboard structural-lint results are computed once per refresh via `scripts/dashboard/lint_results.py` (stats run writes `STATE_DIR/dashboard-lint-results.json`, lint run consumes it while fresh).

Lint check inventory (core set, in execution order in `lint.py`):

| Check | Severity | Auto-fixable | Function |
|---|---|---|---|
| broken_links | error | no | `check_broken_links` |
| orphan_pages | warning | no | `check_orphan_pages` |
| orphan_sources | warning | no | `check_orphan_sources` |
| stale_articles | warning | no | `check_stale_articles` |
| article_type | warning | yes | `check_article_type` |
| sparse_articles | suggestion | no | `check_sparse_articles` |
| facts_violations | warning | no | `check_facts_violations` |
| contradictions | warning | no (LLM) | `check_contradictions` (async, excluded by `--structural-only`) |

⚫ `missing_backlinks` (`check_missing_backlinks`) removed 2026-07-22 (C04): the M020 backlinks pass materializes the reciprocal edge on every compile, so reciprocity is an engine invariant, not a lint finding. Dashboard queue + template row removed with it.

## Side loops (post-compile)

| Loop | Status | Code | Trigger | Known gaps |
|---|---|---|---|---|
| Producer registry + orchestrator | 🟢 | `scripts/producers/base.py` (Protocol + Spec + Registry), `scripts/producers/orchestrate.py:evaluate_and_run`, `scripts/compile_stages/post_passes.py:run_post_passes` | Post-compile per-file loop in `compile.py:main()` calls `run_post_passes` once per successful compile; iterates `all_producers()` serially; `wiki produce --list` / `wiki produce <name> <source>` is the operator-invoked re-run surface | Failure contract α: per-producer failure never blocks state-save or subsequent producers. `producer_cost_total` accumulates separately from SDK-compile `total_cost`. |
| Curiosity loop — producer | 🟢 | `scripts/producers/curiosity.py:CuriosityProducer` (Protocol-conforming wrapper) delegates to `scripts/curiosity/producer.py:maybe_generate_curiosity_requests` | Post-pass after each compile via `run_post_passes`; gate `features.curiosity_loop` evaluated on `SPEC.enabled_config_key`. Gemma4 via Ollama writes `raw/requests/request-{slug}-{date}.json` | — |
| Curiosity loop — consumer | 🟢 | `scripts/curiosity/cli.py`, `scripts/curiosity/backends/email.py` | `wiki curiosity --list / --run-oldest / --run <slug> / --run-all / --clear-done`; piggyback `piggybacks.curiosity_followup` (24h cooldown) runs `--run-oldest` automatically | Backend dispatches by request `type`. Today: `email-deep-scan` (full bodies via Mailbox-adapter scan_deep). Future types add as `curiosity/backends/<type>.py`. |
| Optimization suggestions — producer | 🟢 | `scripts/producers/suggestions.py:SuggestionsProducer` (Protocol-conforming wrapper) delegates to `scripts/suggestions/producer.py:maybe_generate_suggestions` | Post-pass after each compile via `run_post_passes`; source-glob gate `features.suggestions_source_globs` (default `["raw/email/*.md"]`) evaluated on `SPEC.source_glob_config_key` | — |
| Optimization suggestions — executor | 🟢 | `scripts/suggestions/cli.py` | `wiki suggestions --list / --approve / --reject / --review / --dry-run` (or direct `uv run python scripts/suggestions/cli.py …`) | — |
| Takes — producer | 🟢 | `scripts/producers/takes.py:TakesProducer` (Protocol-conforming wrapper) delegates to `scripts/facts/takes_producer.py:maybe_extract_takes` | Post-pass after each compile via `run_post_passes`; gates `features.extract_takes` (enabled) + `limits.extract_takes_source_globs` (source allowlist) evaluated on Spec. Extracts third-party beliefs/claims from meeting + email substrate into entity-page `## Takes` blocks (M011 substrate). | — |
| Optimization suggestions — IMAP backend | 🟢 | `scripts/suggestions/backends/imap.py` | Invoked by `suggestions/cli.py` for `imap-move` / `imap-tag` / `imap-set-flags` actions | Account credentials via `.claude/.env` |
| CLAUDE.md optimizer | 🟢 | `scripts/optimize-claude-md.py` | `uv run python scripts/optimize-claude-md.py`; piggyback `piggybacks.optimize_claude_md` (24h cooldown) | PROCESS §9 |
| Wiki review (per-article quality) | 🟢 | `scripts/review-wiki.py` | `wiki review-wiki`; piggyback `piggybacks.review_wiki` (168h / weekly) | PROCESS §6 |
| Dream-cycle (entity-page re-synthesis) | 🟢 | `scripts/dream.py` | `wiki dream [<slug>]` / `wiki dream sweep` / `wiki dream list-candidates`; piggyback `piggybacks.dream_cycle` (24h). M016 tiered corpus + M017 priority weighting. Size gate `dream_entity_max_prompt_chars`, per-run `dream_cycle_max_tokens_per_run`. Since 0.3.0 (C11): typed `DreamOutcome` + single `dream_exit_code` map (per_call_timeout=6 / prompt_too_large=3 / sdk_failure=4, uniform across entity/sweep/piggyback — closes the timeout-invisible-to-monitoring class); pure table-tested `pre_sdk_skip()` + `classify_post_sdk_write()` + `build_sweep_candidates()` (list-candidates now shows a `backoff` flag) | PROCESS §13, `.ytstack/backlog/dream-priority-config.md` |
| Concept-reconciliation (autonomous fact-consistency) | 🟢 | `scripts/reconcile.py`, `scripts/facts/correct_apply.py:reconcile_fact` | `wiki reconcile [--apply] [--limit N]`; piggyback `piggybacks.concept_reconcile`. Consumes `lint.check_facts_violations`, structural gates (`concept_reconcile_max_files_per_fact` / `_max_facts_per_run`), scope-locked to `knowledge/concepts/`. Double-gated OFF | PROCESS §14, `.ytstack/backlog/concept-consistency-routine.md` |
| Health-trend synthesis (deterministic, $0) | 🟢 | `scripts/health_trends.py` | `wiki health-trends [--dry-run]`; piggyback `piggybacks.health_trends`. Aggregates `raw/notes/health/**` into a sentinel `## Trends` block in `concepts/health.md`. No LLM. Double-gated OFF | PROCESS §15, `.ytstack/backlog/health-trend-synthesis.md` |
| Dream web-research (public-entity enrichment) | 🟢 | `scripts/web_research.py`, dream post-pass `dream.py:_maybe_web_research` / `_run_web_research_standalone` | Post-pass at the `dream_entity()` success seam — fires on single-entity, sweep AND piggyback since 0.3.0 (was single-entity-only, i.e. dead on every unattended run) + standalone `wiki dream web-research <slug> [--dry-run]`. Researches PUBLIC people via Exa AI → sentinel `## Public Profile` block. Double-gated OFF (`features.dream_web_research` + per-entity `web_research: true` / `public-person` tag), own cooldown `scheduling.web_research_cooldown_days` (30d), key `personal.exa_api_key` / env `EXA_API_KEY`. Air-gapped from `raw/`; fail-soft. _Live Exa HTTP path unverified (no key at build); v1 = deterministic link-list block_ | issue #2, `.ytstack/backlog/dream-web-research.md` |
| Entity dedup (transcription-noise duplicates) | 🟢 | `scripts/dedup.py` | `wiki dedup [--suggest-only\|--dry-run\|--threshold T]` + `wiki dedup merge B --into A`. $0 deterministic detection (difflib fuzzy + German-aware phonetic key + shared `compiled_from` boost-only); operator-confirmed merge folds sections/aliases/sources A←B, rewrites `[[wikilinks]]` B→A via `core.links`, backs up + deletes B, records a canonical-name hard fact. Floor `limits.dedup_fuzzy_threshold` (0.85) | issue #3, `.ytstack/backlog/entity-dedup.md` |
| Usage accounting (token ledger) | 🟢 | `scripts/core/usage.py` (`UsageLedger`, `LEDGER`, atexit-flush), `scripts/usage_report.py` | Auto-records tokens per `(provider, model)` at every LLM call site (Ollama client + Claude SDK sites) → `state/usage.json`; `wiki usage [--days N] [--json]` reads it back. No dollars (DECISIONS 2026-05-23) | PROCESS §16, `.ytstack/backlog/token-usage-accounting.md` |

## Analytical surface — operator self-reports

Air-gapped psychometric layer. Validated clinical screens (PHQ-9 / GAD-7 / WHO-5 / PSS-10 / ISI / OLBI on the live manifest, plus K6 + ASRS-v1.1 available off-manifest) scored by an informant agent reading the operator's own substrate. Engine lives under `scripts/reports/_engine/` and is structurally excluded from compile via `COMPILE_SUBSTRATE_EXCLUDED_PREFIXES`.

Interface sweep 0.3.0 (C10): the instrument loader surfaces the `inference:` config, max total and **concern-band** declaration (declared per-band in cutoffs.yaml — replaces the hardcoded `severe_bands` dict that left ISI/OLBI/PSS-10 flag-blind); per-instrument report frontmatter carries the scoring geometry (old reports recovered via the canonical loader). Substrate-scope resolution (the privacy boundary) is an owning module (`substrate_scope.py`) consumed by both the runner and the token-budget audit probe. Inference retries are decided by a structured `FailureClass.kind` (`cli_crash` / `unknown` / `schema_invalid` retryable), and the two-pass analyst orchestration is a public library (`lib/analyst.py`) taking an explicit `vault_root`, so `wiki study run` and `wiki analyze --vault` share one code path with correct citation resolution.

| Feature | Status | Code | Trigger | Docs |
|---|---|---|---|---|
| Study runner — per-instrument inference + scoring | 🟢 | `scripts/reports/_engine/runner.py:run_inference`, `scripts/reports/_engine/lib/inference.py` | `wiki study run <study-id> [--instrument SLUG]`; per-study fcntl-lock on `state/study-<id>.lock`; 3-attempt SDK retry with (5s, 30s) backoffs | cli.md "Operator self-reports", templates/AGENTS.example.md |
| Instrument loader + Likert scorer | 🟢 | `scripts/reports/_engine/instrument.py`, `scripts/reports/_engine/score.py` | Pure-Python deterministic; reverse-coding + cutoffs from `instruments/<slug>/v<x>/{instrument,items,cutoffs}.yaml` | tests/reports/test_instrument_validity.py pins published clinical thresholds |
| Operator-input override (`operator_answers.yaml`) | 🟢 | `scripts/study.py:cmd_answer`, `runner.py:_load_operator_answers` | `wiki study answer <study> <instrument> <item-id> <value> [--note "…"]`; operator answers excluded from SDK prompt, take precedence at scoring | Only legal path for `substrate_inferable: false` items (PHQ-9 Q9 suicidal ideation never auto-inferred) |
| Per-instrument model override | 🟢 | `runner.py:_read_inference_config().get('model')` → `infer_batch(model=…)` | `inference.model:` key in `instrument.yaml` overrides `DEFAULT_INFERENCE_MODEL` (claude-haiku-4-5). Currently set on ISI → claude-sonnet-4-6 (unverified — Haiku scored 57% in one run, so the "deterministic-0%" premise is open) | — |
| Pass-1 per-study analyst | 🟢 | `scripts/reports/_engine/lib/analyst.py`, `prompts/reports/analyst_per_study.md` | Auto-fires inside `wiki study run` after the run succeeds; writes `runs/<ts>/_analysis.md`. Scope-locked Read+Grep only (same `make_path_scope_gate([])` pattern as inference) | cli.md, templates/AGENTS.example.md |
| Pass-2 cross-study synthesis | 🟢 | `prompts/reports/analyst_cross_study.md`, `scripts/analyze.py` | `wiki analyze` (P1 fresh-run + P2) / `wiki analyze --study <id>` (P1 only) / `wiki analyze --cross-study-only` (P2 only). Output: `reports/analyses/<UTC-ts>.md` | cli.md |
| Cross-instrument meta-report (radar + sparkline + per-instrument item-radar + timelines) | 🟢 | `scripts/reports/_engine/lib/render_summary.py`, `lib/charts.py` (pure-Python SVG, no matplotlib) | Auto-rendered per run into `runs/<ts>/charts/*.svg` + side-by-side flex-layout block in `_summary.md` | overview.png pills + architecture.png M19 block |
| Backfill per-item from body table | 🟢 | `scripts/reports/_engine/backfill_per_item.py` | `uv run python scripts/reports/_engine/backfill_per_item.py --study-dir <path> [--rerender-summary]`. Re-parses pre-2026-05-17T16-14 reports' body `## Items` table, applies reverse-coding, writes `per_item:` into frontmatter, trims timeline to runs ≤ self when re-rendering | — |
| Schedule-driven runs (manual / daily / weekly / monthly / quarterly) | 🟢 | `manifest.yaml:schedule` field, study state-driven | Operator invokes `wiki study run` (today manual; piggyback hookup planned). Schedule semantics documented in `templates/reports/studies/longitudinal-baseline/manifest.yaml`. Currently daily for tweaking; week-1 review 2026-05-24 decides daily→weekly flip | `.ytstack/backlog/m019-week-1-review.md` |

## Vault UX layer

| Feature | Status | Code | Trigger | Docs |
|---|---|---|---|---|
| Dashboard.md (Obsidian Homepage) | 🟢 | `templates/dashboard.md`, `lib/seed.sh:seed_vault_templates` | Seeded on install / `wiki seed` | PROCESS §11, README |
| Dashboard stats refresh (`_dashboard-stats.md`) | 🟢 | `scripts/dashboard/dashboard_stats.py` | Synchronous post-flush in `flush.py:refresh_dashboard_stats` + `wiki compile / lint / seed / correct` shell-wrapper helpers | PROCESS §11 |
| Dashboard lint refresh (`_dashboard-lint.md`) | 🟢 | `scripts/dashboard/dashboard_lint.py` | Synchronous post-flush in `flush.py:refresh_dashboard_lint`; same shell-wrapper helpers | PROCESS §11 |
| Agent-button auto-wiring | 🟢 | `scripts/dashboard/agent_buttons.py`, `lib/seed.sh:_merge_agent_shell_commands` + `_rewrite_dashboard_agent_buttons` | `wiki seed` discovers `prompts/agents/*.md` with `button:` block, merges shell-commands data.json, rewrites marker regions in dashboard.md | PROCESS §13, M004 |
| Daily-button injection | 🟢 | `scripts/dashboard/inject_daily_button.py` | `uv run python scripts/dashboard/inject_daily_button.py` | — |
| Maps of Content (MOCs) | 🟢 | `knowledge/MOCs/*.md`, templates in `templates/knowledge/MOCs/`, `scripts/pin.py` | `wiki seed` seeds `people.md` / `projects.md` / `concepts.md` stubs; operator adds wikilinks | PROCESS §11 MOC subsection |
| `wiki pin` (article → MOC section) | 🟢 | `scripts/pin.py` | `wiki pin <article> [--section "Name"] [--moc people] [--summary "X"]` | PROCESS §11 |
| Bases-browser (`knowledge.base`) | 🟢 | `templates/knowledge.base`, `lib/seed.sh:seed_vault_templates` | Seeded as additive template; Obsidian native (1.10+) | PROCESS §11 |
| History layer (`history.jsonl`) + P2 charts | 🟢 | `scripts/core/utils.py:append_history`, `read_history`; dashboard.md "📈 History" section | Auto-appended on compile / flush events | PROCESS §11 |

### Hard facts (corrections)

| Feature | Status | Code | Trigger |
|---|---|---|---|
| `wiki correct add / list / remove / edit / path` | 🟢 | `scripts/facts/correct.py` | `wiki correct <subcommand>` |
| `wiki correct apply <slug>` (agentic propagator) | 🟢 | `scripts/facts/correct_apply.py` | `wiki correct apply <slug> [--dry-run]` |
| Compile/query/lint integration | 🟢 | `prompts/compile_main.md`, `prompts/query_main.md`, `scripts/core/utils.py:read_hard_facts`, `scripts/lint.py:check_facts_violations` | Facts inject top-of-prompt at compile + query; lint greps `negation_terms` |

### Agent tasks

| Feature | Status | Code | Trigger | Docs |
|---|---|---|---|---|
| Generic agent runner | 🟢 | `scripts/agent_task.py`, spec parser `scripts/core/agent_spec.py` | `wiki agent <id>`, `wiki agent --list`, `wiki agent <id> --dry-run`, `wiki agent <id> --var key=value` | PROCESS §13, M004 |
| `summarize-day` task | 🟢 | `prompts/agents/summarize-day.md` | `wiki agent summarize-day --var date=YYYY-MM-DD` | M004-S02 |

Currently 1 agent task ships. Adding a new task = drop `prompts/agents/<id>.md` with frontmatter spec + optional `button:` block. No engine code change required.

## Lifecycle CLI

| Command | Status | Code | Notes |
|---|---|---|---|
| `wiki setup` | 🟢 | `wiki:cmd_setup`, `lib/config.sh:setup_wizard`, `lib/hooks.sh` | 6-question wizard + hook install |
| `wiki status` | 🟢 | `wiki:cmd_status` | Config summary + hook install table + Ollama probe |
| `wiki update` | 🟢 | `wiki:cmd_update`, `lib/skills.sh` | `git pull --ff-only` + skill sync; preserves `config.yaml` + `.venv/` |
| `wiki seed` / `wiki seed --force` | 🟢 | `wiki:cmd_seed`, `lib/seed.sh` | Additive template seed + drift detection |
| `wiki config` (get/set/keys/path/wizard/status) | 🟢 | `wiki:cmd_config`, `lib/config.sh`, `scripts/core/config.py` | Round-robin backup on every set |
| `wiki hooks` (install/uninstall/status) | 🟢 | `wiki:cmd_hooks`, `lib/hooks.sh`, `lib/agents.sh` | jq-merge into agent settings.json |
| `wiki skills` (install/uninstall/sync/status) | 🟢 | `wiki:cmd_skills`, `lib/skills.sh` | Symlink into `<vault>/.claude/skills/`, foreign entries preserved. `--global` (gated by `skills.global_install`) also links global-eligible skills into `~/.claude/skills/` + registers the vault in `~/.config/llm-wiki/vaults` |
| `wiki auth <service> <id>` (gmail \| gmeet \| calendar) | 🟢 | `scripts/cli.py` auth registry → `scripts/adapters/mailbox/gmail.py` / `core/google_oauth.py` | One-time OAuth bootstrap; `wiki gmail-auth` / `wiki gmeet-auth` / `wiki calendar-auth <id>` remain as aliases. Account id passed as argv, never interpolated into `python -c` source (0.3.0, C06) |
| `wiki version` | 🟢 | `wiki:cmd_version` | Git revision + tag + origin URL |

### `wiki` dispatcher (0.3.0, C06)

The `CommandSpec` table in `scripts/cli.py` is the single source of truth for the command catalog: `wiki help` renders the full list (previously blind to 9 commands), `menu.py` coverage is test-pinned to it, the post-command dashboard refresh runs once via flush.py's fcntl lock, and every Python-backed subcommand delegates through it. The bash `wiki` keeps bootstrap + the fail-closed vault guard + the genuinely-bash commands (setup/hooks/skills/config/seed/update/menu/doctor/status/install-shortcut/version + dream argv routing).

## Engine seams (cross-cutting, 0.3.0 arc)

Internal plumbing consolidated in the 0.3.0 architecture-deepening arc — no operator surface of their own, but load-bearing for everything above. Vocabulary: `CONTEXT.md`; rationale: DECISIONS.md 2026-07-18 / 2026-07-22.

| Seam | Code | What it owns |
|---|---|---|
| Claude-SDK call harness (M021 S01) | `scripts/core/sdk_helpers.py:run_sdk_query` | Options assembly, path-scope gates (hook / legacy / deny-all shapes), stall-timeout loop, dual-basis usage extraction, LEDGER recording on every outcome, failure classification. Migrated: compile_stages/compile, dream, query, agent_task, correct_apply ×2, reports inference+analyst. Known gaps: suggestions/takes/folder_providers/intents/flush/lint/optimize-claude-md still hand-roll loops; Ollama dispatch = M021 S02 |
| Frontmatter grammar | `scripts/core/frontmatter.py` | The engine's single frontmatter parse/write seam (`parse`/`parse_strict`/`field`/`write`/`update_fields`/`backup`). Consumers: compile route+classify, lint, intents/triage record contract, facts, reports timeline. ~15 opportunistic sites keep private parsers until touched |
| Sentinel markers | `scripts/core/markers.py` | `find_region` + `replace/ensure/strip_region` for every `<!-- x:begin/end -->` managed block (flush sessions, health-trends, backlinks, agent buttons, calendar, web-research) |
| State store | `scripts/core/state_store.py` | flock primitives, atomic JSON saves, `state.json` merge-under-lock, ingested-ledger API |
| Exception seam | `scripts/core/errors.py:swallow` | Labeled intentional suppression; decision tree in AGENTS.md § Exception handling |
| Config schema | `scripts/core/config_schema.py` (+ `config_docs.py`) | Every knob's name/type/default/doc-comment; migration values + docs/config.md tables + example-sync derived and drift-tested from it |
| Desktop runner | `desktop/src/vault/wiki-exec.ts:runWiki` | The single desktop-to-engine spawn seam (timeout, ANSI strip, JSON parse, typed errors); consumes the `--json` machine-readable seams (`collect --list --json`, `triage list --json`, `query --json`, `compile --progress-json`, plus the existing `doctor --json` / `menu --json`) |

## Known gaps & drift

These are pinned reality-vs-docs checks. Each should either get fixed or get an explicit ADR explaining why the gap stays.

| # | Gap | Documented as | Actual state | Action |
|---|---|---|---|---|
| 1 | ~~Curiosity-loop consumer missing~~ | PROCESS §7, concept "Curiosity loop", README "Curiosity loop" all describe a producer→consumer cycle | **Closed 2026-05-13:** `scripts/curiosity/` subsystem shipped (Option B from backlog) — producer extracted from compile.py, `wiki curiosity` CLI consumer, `backends/email.py` dispatches `email-deep-scan` requests via the existing Mailbox adapters' `scan_deep`. Piggyback `curiosity_followup` runs `--run-oldest` every 24h. |
| 2 | ~~No `wiki process-inbox` subcommand~~ | PROCESS §1 documents Inbox Processing as a numbered process | **Closed 2026-05-13:** `wiki process-inbox` wrapper landed. |
| 3 | ~~No `wiki ingest-html` subcommand~~ | README "Path B" lists `ingest-html (file or URL)` as a substrate-source writer | **Closed 2026-05-13:** `wiki ingest-html` wrapper landed. |
| 4 | ~~No `wiki suggestions` subcommand~~ | PROCESS §8 documents the suggestion executor as part of the engine CLI surface | **Closed 2026-05-13:** `wiki suggestions` wrapper landed. |
| 5 | ~~`scan-*.py` legacy pattern~~ | README "Two-path ingest" said "remaining `scan-*.py` are scheduled for [Collector] migration" | **Closed 2026-05-14.** Phase 2 complete — all 5 scanners (`tabs`, `calendar`, `browser`, `screenshots`, `youtube`) ported to Registry collectors with snake_case filenames. `_BUILTIN_PIGGYBACK_TASKS` (renamed 2026-07-18, C05; in `core/piggybacks.py` since the compile-drain split) carries zero substrate collectors — its entries are deliberate non-Collector maintenance/synthesis tasks. Config-key migration shipped (`scripts/migrations/migrate_config_keys.py`). |
| 6 | **`origin: "scan-email/<id>"` in email Collector report frontmatter** | n/a (cosmetic) | `collectors/email_collector.py:111` still writes the old origin string. No engine reader; cosmetic only. | Flagged; intentionally left to avoid splitting report vintages |

## Maintenance protocol

When a feature lands:
1. Add or update the row in the matching section table.
2. Cross-reference: add it to `docs/PROCESS.md` (with a process-section if non-trivial), `docs/cli.md` (if it has a `wiki` subcommand), and one of README / concept.md (if it's user-visible).
3. If a config knob is involved, add it to `docs/config.md`.
4. If the feature *removes* something else, mark the removed row as ⚫ and link the supersede entry.

When a feature is retired:
1. Update its row to ⚫ removed with the commit SHA and a one-line reason.
2. Sweep all docs for stale references (`grep -rn '<feature>' docs/ README.md AGENTS.md`).
3. Add a DECISIONS.md entry if the retirement is non-obvious.

When the docs make a claim, verify the implementation exists before merging — that's the whole point of this file.
