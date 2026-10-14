# Engine layout

The engine lives under `<vault>/.wiki/` — hidden from Obsidian's file tree (Obsidian ignores `.`-prefixed directories) and never modified by hand. This doc is the file-by-file reference for contributors and operators who want to see exactly what's inside.

For a higher-level view (vault layout, install, CLI usage), see the [README](../README.md). For development conventions (style, side-effect rules, how to add a tunable / prompt / agent target), see [AGENTS.md](../AGENTS.md).

> **Hard rule — `.venv/` location.** The Python virtualenv lives at `<vault>/.wiki/.venv/`, never at the vault root — **unless the vault is inside a cloud-synced folder** (iCloud Drive `~/Library/Mobile Documents/…`, `~/Library/CloudStorage/…`), in which case it lives at `~/.venvs/<vault>-wiki` and every uv invocation is told so via `UV_PROJECT_ENVIRONMENT`. The rule has one home, `lib/common.sh` (`wiki_venv_dir`): the `wiki` dispatcher exports the variable, `lib/agents.sh` writes it literally into the agent hook commands, `install.sh` asks the rule, and Python only reads the result (`sys.prefix`). Why: cloud sync evicts file contents, and macOS SIGKILLs a running binary whose pages stop matching their code signature mid-swap — the 200 MB bundled Claude CLI died three times in one night on the operator vault (2026-09-17). A symlink at `.wiki/.venv` is not a fix; iCloud shelved it as `.venv 2` and kept its directory. A vault-root `.venv/` would leak engine internals into the data layer and break `wiki update` round-trips. Never start the engine with a bare `uv run --project .wiki` on such a vault — go through `wiki …`, which knows where the environment is; `wiki doctor` → `engine-cloud-eviction` reports the actual state.

## Contents

- [Directory tree](#directory-tree)
- [How a module runs](#how-a-module-runs)
- [Why bash + python + jq?](#why-bash--python--jq)
- [Where to go next](#where-to-go-next)

## Directory tree

```text
.wiki/
├── wiki                       ← entry point (bash) — bootstrap + fail-closed vault guard + TTY detection + genuinely-bash commands; every Python-backed subcommand delegates to scripts/cli.py
├── install.sh                 ← one-liner installer (also re-runnable from a checkout)
├── config.example.yaml        ← tracked  ── │ copy at install time
├── config.yaml                ← gitignored ─┘
├── pyproject.toml + uv.lock
├── lib/
│   ├── common.sh              ← paths, colors, logging, deps, backup
│   ├── ui.sh                  ← interactive prompts (confirm / ask / select_one / select_many)
│   ├── agents.sh              ← agent registry, detection, payload generators, install/uninstall
│   ├── hooks.sh               ← interactive flows for `wiki hooks {install,uninstall,status}`
│   └── config.sh              ← Python config CLI wrapper + setup wizard + interactive editor
├── scripts/
│   ├── core/                  ← shared engine plumbing (imported, never invoked)
│   │   ├── paths.py               ← eager path constants from __file__ — zero deps, no side effects
│   │   ├── config.py              ← CONFIG singleton (YAML-driven) + get/set/keys CLI + TIMEZONE + .env bootstrap
│   │   ├── prompts.py             ← prompt template loader (${var} substitution)
│   │   ├── ollama_client.py       ← single Ollama transport (chat / chat_schema / chat_vision)
│   │   ├── config_schema.py       ← side-effect-free config schema (every knob: name/type/default/doc-comment); consumed by config.py, the key-migration, and config_docs.py (generates docs/config.md tables)
│   │   ├── sdk_helpers.py         ← run_sdk_query(prompt, SdkCallSpec) — the ONE Claude-SDK call harness (options assembly, path-scope gates, stall-timeout loop, usage → LEDGER, failure classification) + StderrCapture + assert_prompt_within_budget
│   │   ├── frontmatter.py         ← the single frontmatter grammar (parse/parse_strict/field/write/update_fields) — never hand-roll a `---` parser
│   │   ├── markers.py             ← sentinel-region primitive (find_region + replace/ensure/strip_region) for `<!-- x:begin/end -->` managed blocks
│   │   ├── state_store.py         ← flock primitives + atomic JSON saves + state.json merge-under-lock + ingested-ledger API
│   │   ├── entry.py               ← how one engine process spawns another: `python -m <module>` with scripts/ on PYTHONPATH (module_for / child_env / python_m); cli, piggybacks, flush, preprocessors use it
│   │   ├── errors.py              ← swallow(label) — labeled intentional exception suppression (AGENTS.md § Exception handling)
│   │   ├── daily_capture.py       ← fcntl-flocked append/replace_section/replace_block into daily/<date>/<source>.md
│   │   ├── utils.py               ← shared helpers (article listing, JSON state, history) + now_iso/today_iso
│   │   ├── backlinks.py           ← corpus-wide backlinks-footer materialization (post-compile global pass; sentinel-managed `## Backlinks` per article)
│   │   ├── agent_spec.py          ← agent-task spec parser (prompts/agents/*.md → AgentSpec)
│   │   ├── google_oauth.py        ← Gmail OAuth2 bootstrap (local-loopback consent flow)
│   │   ├── flush_pipeline.py      ← staged-flush state machine (stage / commit / archive / pending)
│   │   ├── health.py              ← vault-health checks behind the home-screen banner + `wiki doctor`
│   │   ├── console.py             ← shared console-logging setup for the CLI scripts (per-CLI formatter hook)
│   │   ├── actions.py             ← action catalogue — the operator-facing vocabulary of everything a consumer can run (menu + desktop JSON contract)
│   │   ├── links.py               ← wikilink resolution + relativization — single source of truth (resolve_link / canonical_slug / relativize_text)
│   │   ├── index_sync.py          ← deterministic knowledge/index.md sync behind `wiki reindex`
│   │   ├── compile_role.py        ← the `compile_role` frontmatter axis + VALID_ROLES (read by route, lint, the compile prompt)
│   │   ├── capture_index.py       ← capture index — capture_id → {source_path, created, status} for the capture intake
│   │   ├── config_backup.py       ← round-robin config.yaml backup — the one helper both config write paths share
│   │   ├── usage.py               ← token-usage ledger keyed by (provider, model) → state/usage.json
│   │   ├── piggybacks.py          ← piggyback scheduling core — task table, cooldown gate, detached spawn
│   │   └── piggyback_runner.py    ← runs one piggyback command under a wall-clock timeout and records its status (`python -m core.piggyback_runner`)
│   ├── cli.py                 ← table-driven `wiki` dispatcher — the CommandSpec table is the single source of truth for the command catalog (help/menu derive from it; owns the once-per-command locked dashboard refresh + `wiki auth`)
│   ├── collectors/            ← substrate→raw/ writers (Registry + scan-* CLIs + dispatcher)
│   │   ├── base.py                ← Collector Protocol, SPEC, Registry + account-loop harness (resolve_accounts/filter_accounts/Watermark/run_account_loop) + inbox-intake harness (scan_inbox/archive_to_zone/append_rollup)
│   │   ├── cli.py                 ← `wiki collect` dispatcher (Registry lookup + run-one; honors --account via SPEC.supports_account_loop)
│   │   ├── folder_index.py        ← body-blind folder index (entry module: scripts/index_folders.py; registered as the `folder-index` collector)
│   │   ├── email_collector.py     ← email Collector (multi-backend via adapters/mailbox/)
│   │   ├── jamie.py               ← Jamie AI meeting-notetaker
│   │   ├── gmeet.py               ← Google Meet / Gemini transcripts (Drive API)
│   │   ├── voice.py               ← inbox-watch dictation ingester (iOS Shortcuts / OpenWhispr / FluidVoice)
│   │   ├── health.py              ← Oura REST daily biometric rollup (sleep / readiness / HRV / steps)
│   │   ├── calendar_collector.py  ← Google Calendar v3 → per-date rollups (multi-tenant, OAuth)
│   │   ├── wispr.py               ← Wispr Flow meetings via the desktop app's HTTP API
│   │   ├── pictures.py            ← inbox-watch camera / phone-photo ingester (vision per file + batch report)
│   │   ├── _picture_metadata.py   ← EXIF + filename-pattern parsing behind pictures.py
│   │   ├── capture_collector.py   ← folder-watching quick-capture intake (capture index in core/)
│   │   ├── scan_browser.py        ← Firefox + Chrome bookmarks/history/tab-groups
│   │   ├── scan_screenshots.py    ← ~/Screenshots/ + Vision LLM (gemma4) → HOME sidecar + vault thumb (384px) + batch report
│   │   ├── scan_tabs.py           ← Firefox Simple Tab Groups backups
│   │   └── scan_youtube.py        ← yt-dlp + youtube-transcript-api + optional gemma4 visual analysis (entry module: scripts/ingest_youtube.py)
│   ├── adapters/              ← the clients collectors talk through (never substrate-aware)
│   │   ├── calendar/google.py     ← Google Calendar v3 REST wrapper (list_calendars / list_events / get_event)
│   │   ├── health/{oura,healthkit_xml}.py ← Oura REST client; Apple Health Export.xml streaming parser
│   │   └── mailbox/{base,gmail,thunderbird,imap,allinkl}.py ← MailboxReader / Filter adapters (allinkl = server-side filter)
│   ├── domain/mail.py         ← pure mailbox domain types (frozen dataclasses shared by readers, filters, collectors)
│   ├── intents/               ← intent dispatch: Intent record + Handler Protocol + Registry (base.py), task / idea / note handlers, _record.py writer → workspace/inbox/
│   ├── bridge/                ← `wiki bridge` — rsync-based inbox bridge (cli.py, drive_sync.py)
│   ├── publish/               ← `wiki publish` — mirror knowledge/ into meinkontext: cli, corpus, delta (content-hash), describe, render, executor, client (MCP JSON-RPC), oauth, bootstrap
│   ├── preprocessors/         ← in-vault intake normalizers (pre-compile; Protocol + Registry, singletons)
│   │   ├── base.py                ← Preprocessor Protocol, PreprocessorSpec, PreprocessResult, Registry
│   │   ├── cli.py                 ← `wiki preprocess` dispatcher (--list / <name> [source] [--dry-run])
│   │   ├── inbox.py               ← <vault>/inbox/ classifier (entry module: scripts/process_inbox.py)
│   │   ├── html_ingest.py         ← HTML file/URL → raw/articles (named to avoid the stdlib `html` shadow; entry module: scripts/ingest_html.py)
│   │   └── clippings.py           ← <vault>/Clippings/ sweep (shim: scripts/clippings_sweep.py)
│   ├── facts/                 ← hard-fact subsystem (knowledge/facts/<slug>.md consumers) + takes producer
│   │   ├── correct.py             ← CRUD CLI: add/list/remove/edit/path
│   │   ├── correct_apply.py       ← agent-driven propagation across vault
│   │   ├── take.py                ← third-party belief attribution CRUD (who believes what, with confidence + source)
│   │   └── takes_producer.py      ← maybe_extract_takes legacy free function (delegated-to by producers/takes.py)
│   ├── producers/             ← post-compile derivative-material extractors (Registry + orchestrator + CLI)
│   │   ├── base.py                ← Producer Protocol, ProducerSpec, ProducerResult, Registry (`@register`, `all_producers`, `get_producer`)
│   │   ├── orchestrate.py         ← `evaluate_and_run(producer, source)` — gate evaluation + dispatch
│   │   ├── cli.py                 ← `wiki produce` dispatcher (`--list` / `<name> <source>`)
│   │   ├── suggestions.py         ← SuggestionsProducer (delegates to `suggestions/producer.py:maybe_generate_suggestions`)
│   │   ├── curiosity.py           ← CuriosityProducer   (delegates to `curiosity/producer.py:maybe_generate_curiosity_requests`)
│   │   ├── folder_curiosity.py    ← FolderCuriosityProducer (folder-deep-scan requests)
│   │   ├── intents.py             ← IntentsProducer     (actionable intents → intents/ handlers → workspace/inbox/)
│   │   └── takes.py               ← TakesProducer       (delegates to `facts/takes_producer.py:maybe_extract_takes`)
│   ├── compile_stages/        ← pure-ish stages extracted from compile.py's per-file loop
│   │   ├── types.py               ← CompileResult + CompileMetadata + CompileOutcome dataclasses
│   │   ├── classify.py            ← pre-compile substrate classifier
│   │   ├── route.py               ← Route — the discriminated per-source decision compile_file makes (the one frontmatter grammar behind it: core/frontmatter.py)
│   │   ├── memory.py              ← memory-substrate pre-pass: resolve the project page + bootstrap its Timeline section
│   │   ├── compile.py             ← `compile_source(content, metadata) → CompileResult` (LLM-call boundary: prompt assembly, owner-block, pre-flight gate, SDK call, retry-on-kind-unknown, failure classification)
│   │   └── post_passes.py         ← `run_post_passes(source, compile_result, state) → list[ProducerResult]` (iterates ProducerRegistry serially, accumulates `producer_cost_total` into state)
│   ├── suggestions/           ← email-suggestion pipeline (legacy producer body + executor)
│   │   ├── producer.py            ← `maybe_generate_suggestions` legacy free function (delegated-to by producers/suggestions.py)
│   │   ├── cli.py                 ← interactive approve/review/reject/execute
│   │   └── backends/imap.py       ← IMAP move/tag/set-flags executor
│   ├── curiosity/             ← gap-detection loop (legacy producer body + consumer CLI + backends)
│   │   ├── producer.py            ← `maybe_generate_curiosity_requests` legacy free function (delegated-to by producers/curiosity.py)
│   │   ├── cli.py                 ← `wiki curiosity` consumer: list / run-oldest / run / run-all / clear-done
│   │   ├── backends/email.py      ← email-deep-scan dispatch via Mailbox-adapter `scan_deep`
│   │   └── backends/{folder,folder_providers}.py ← folder-deep-scan backend + its answer providers
│   ├── dashboard/             ← Obsidian dashboard helpers (post-flush + seed-time)
│   │   ├── dashboard_stats.py     ← _dashboard-stats.md generator
│   │   ├── dashboard_lint.py      ← _dashboard-lint.md generator
│   │   ├── lint_results.py        ← once-per-refresh structural-lint compute, cached in STATE_DIR (shared by the stats + lint renderers)
│   │   ├── agent_buttons.py       ← agent-button discovery + dashboard.md rewriter
│   │   └── inject_daily_button.py ← idempotent Summarize-button injection into daily/<date>/sessions.md
│   ├── reports/_engine/       ← operator-self-reports surface (air-gapped from compile)
│   │   ├── runner.py              ← `run_inference()` — substrate-scope resolve + batched SDK calls + persist `runs/<ts>/instruments/<slug>.md`
│   │   ├── substrate_scope.py     ← the privacy-boundary seam: which operator substrate an inference run may read (CLINICAL_DEFAULT_SUBSTRATE_GLOBS + resolve_substrate_files; probe imports production, never the reverse)
│   │   ├── instrument.py          ← yaml loader for `instruments/<slug>/v<x>/{instrument,items,cutoffs}.yaml`
│   │   ├── score.py               ← deterministic Likert + reverse-coding + band lookup
│   │   ├── backfill_per_item.py   ← one-shot: re-parse pre-2026-05-17T16-14 reports' body `## Items` table → frontmatter `per_item:`
│   │   ├── study.py               ← study manifest schema + state + run-directory atomic writes (behind scripts/study.py)
│   │   ├── audit_scope.py         ← token-budget audit for the reports surface
│   │   ├── verify_scope_lock.py   ← scope-lock verification for the reports agents (`python -m reports._engine.verify_scope_lock`)
│   │   ├── lib/inference.py       ← `infer_batch_async` SDK wrapper (3-attempt retry + scope-lock + StderrCapture)
│   │   ├── lib/analyst.py         ← Pass-1 / Pass-2 analyst SDK wrapper (Read+Grep scope-locked)
│   │   ├── lib/render_summary.py  ← cross-instrument meta-report (radar + sparkline + per-instrument item-radar + timelines)
│   │   ├── lib/charts.py          ← pure-Python SVG renderers (no matplotlib)
│   │   ├── lib/timeline.py        ← cross-run aggregator → `Timeline` of `RunSnapshot[InstrumentSnapshot]`
│   │   ├── lib/{cutoffs,likert,verify_report}.py  ← scoring + band-lookup + post-write integrity check
│   │   └── instruments/<slug>/v<x>/  ← curated instrument definitions (currently 8: phq-9, gad-7, who-5, k6, asrs-v1.1, pss-10, isi, olbi; 6 on the live longitudinal-baseline manifest)
│   ├── study.py               ← `wiki study list / run / new / answer` CLI (drives `scripts/reports/_engine/runner.py`)
│   ├── analyze.py             ← `wiki analyze` CLI — Pass-1 per-study + Pass-2 cross-study synthesis
│   ├── migrations/            ← one-shot schema/data migrations, run as `PYTHONPATH=.wiki/scripts uv run --project .wiki python -m migrations.<name>`
│   │   ├── migrate_config_keys.py ← config.yaml keys → current schema (renamed / removed / added); `wiki update` runs it after every pull
│   │   ├── migrate_log_md_path.py ← knowledge/log.md → .wiki/logs/operations.md; `wiki update` runs it after every pull
│   │   ├── migrate_add_type.py    ← backfill `type:` frontmatter on knowledge/ articles
│   │   ├── migrate_inbox_archive.py ← mobile-collector `.processed/` archives → the vault audit zone
│   │   ├── relativize_wikilinks.py ← corpus-wide `[[wikilink]]` → relative-to-file form
│   │   └── cleanup_empty_deep_scans.py ← curiosity-loop deep-scan empty outputs
│   ├── compile.py             ← Claude Agent SDK compiler (raw/ + daily/<date>/* + daily/<date>.md → knowledge/); per-file loop delegates the LLM call to `compile_stages/compile.py:compile_source` and the post-pass loop to `compile_stages/post_passes.py:run_post_passes`
│   ├── flush.py               ← session-end → daily/<date>/sessions.md append + piggyback spawner
│   ├── migrate_daily_to_rollup.py   ← one-shot: legacy daily/<date>.md → daily/<date>/sessions.md
│   ├── backfill_daily_rollup.py     ← one-shot: raw/{health,voice,transcripts/{jamie,gmeet}} → daily/<date>/{health,voice,meetings}.md
│   ├── cleanup_legacy_daily_roots.py ← one-shot: byte-match-verified delete of legacy daily/<date>.md
│   ├── daily_digest_runner.py       ← piggyback wrapper for `wiki agent daily-digest`
│   ├── backfill_picture_metadata.py ← one-shot: EXIF + filename metadata into picture-archive sidecars
│   ├── backfill_tasks_to_workspace.py ← one-shot: legacy tasks/ intent queue → workspace/inbox/
│   ├── backfill_voice_source_frontmatter.py ← one-shot: `source:` frontmatter on voice rollups written before it existed
│   ├── menu.py                ← interactive home screen (`wiki` / `wiki menu`; `--json` for the desktop app)
│   ├── menu_context.py        ← the home screen's context probe (status + suggestions; schema-2 JSON — an oracle payload)
│   ├── doctor.py              ← `wiki doctor` — full vault-health audit (`--quick --json` — an oracle payload)
│   ├── dream.py               ← dream cycle — periodic cross-time re-synthesis of entity pages (`wiki dream` / `wiki dream-entity`)
│   ├── web_research.py        ← dream web-research — public-entity enrichment via Exa
│   ├── triage.py              ← `wiki triage` — review + clear the intent-dispatch inbox (workspace/inbox/)
│   ├── reindex.py             ← `wiki reindex` — deterministic knowledge/index.md reconciliation (core/index_sync.py)
│   ├── dedup.py               ← `wiki dedup` — interactive entity deduplication for transcription-noise duplicates
│   ├── reconcile.py           ← autonomous concept-reconciliation routine
│   ├── health_trends.py       ← deterministic health-trend synthesis over the health corpus (no LLM)
│   ├── usage_report.py        ← `wiki usage` — token-usage ledger read-back (state/usage.json)
│   ├── links_audit.py         ← `wiki links` — analyze (and optionally fix) broken wikilinks
│   ├── probe_compile_scope.py ← empirical probe of the compile-scope allowlist (operator-run, real SDK)
│   ├── lint.py                ← structural checks over a once-built LintContext corpus (footer-aware link graph) + 1 LLM contradiction check
│   ├── query.py               ← Claude Agent SDK natural-language query (read-only / file-back)
│   ├── agent_task.py          ← generic Claude Agent SDK runner for prompts/agents/*.md
│   ├── clippings_sweep.py     ← thin shim → preprocessors/clippings.py (<vault>/Clippings/ → raw/articles/, pre-compile lift)
│   ├── ingest_html.py         ← entry module for `wiki ingest-html` (logic: preprocessors/html_ingest.py)
│   ├── process_inbox.py       ← entry module for `wiki process-inbox` (logic: preprocessors/inbox.py)
│   ├── ingest_youtube.py      ← entry module for `wiki ingest-youtube` (logic: collectors/scan_youtube.py — the direct CLI's --url / --inbox / --tier flags)
│   ├── index_folders.py       ← entry module for `wiki index` (logic: collectors/folder_index.py)
│   ├── review_wiki.py         ← per-article quality scoring via local LLM
│   ├── optimize_claude_md.py  ← cross-project pattern → ~/.claude/CLAUDE.md edits
│   ├── retry_failed_flushes.py ← reprocess archived flush contexts
│   ├── pin.py                 ← `wiki pin <article>` — append wikilink to a MOC section (no LLM)
│   └── health.py              ← read-only colored ASCII vault dashboard
├── hooks/
│   ├── _bootstrap.py          ← the engine's one sys.path bootstrap (puts scripts/ on the path)
│   ├── _transcript.py         ← shared transcript walker + tool summarizer
│   ├── session-start.py       ← inject index.md into next session's context
│   ├── session-end.py         ← spawn flush.py with the conversation transcript
│   └── pre-compact.py         ← safety-net flush before context compaction
├── prompts/                   ← LLM prompts as standalone .md files
├── templates/                 ← seeded into <vault>/ on install (never overwritten)
│   ├── AGENTS.example.md
│   ├── dashboard.md
│   └── .obsidian/{community,core}-plugins.json
├── skills/                    ← engine skills (symlinked into <vault>/.claude/skills/)
│   ├── engine-pr/SKILL.md
│   ├── excalidraw-diagram/SKILL.md
│   ├── ingest-audio/SKILL.md
│   ├── use-llm-wiki/SKILL.md   ← global-eligible: also links into ~/.claude/skills/
│   ├── vault-health-check/SKILL.md
│   └── vault-triage/SKILL.md
├── desktop/                   ← Electron menubar GUI (npm) — every engine call goes through src/vault/wiki-exec.ts:runWiki() and the engine's --json seams (collect/triage/query/compile-progress + doctor/menu)
└── (gitignored runtime)
    ├── .venv/                 ← uv-managed Python environment (cloud-synced vaults: ~/.venvs/<vault>-wiki instead, see hard rule above)
    ├── state/                 ← *.json hash trackers, dedup, cooldowns
    ├── logs/                  ← flush.log + flush-errors.log (WARNING+), compile.log (full stderr-mirror) + compile-errors.log (WARNING+)
    ├── sessions/              ← session-flush staging + failed-flushes/
    └── reports/               ← lint + review-wiki output
```

### How a module runs

`scripts/` is the engine's source root, not a package (no `scripts/__init__.py`, ever — `tests/test_layout.py` guards it). Three shapes; which one applies depends on where the module sits:

- **Top-level scripts** (`scripts/<x>.py`) run by path — `uv run --project <vault>/.wiki python <vault>/.wiki/scripts/compile.py …` — because Python puts a script's own directory first on `sys.path`, and here that directory *is* the source root.
- **Sub-package modules** (`core/`, `collectors/`, `migrations/`, `dashboard/`, …) run only as modules with the source root on the path — `PYTHONPATH=<vault>/.wiki/scripts uv run --project <vault>/.wiki python -m migrations.migrate_config_keys …`. By path they fail with `ModuleNotFoundError: core`. `wiki <command>` always takes this shape for you: `core/entry.py` builds the argv + env for every Python-side spawn, and the bash layer spells the same line.
- **Hooks** (`hooks/*.py`) are plain scripts the agent harness runs from `hooks/`; they `import _bootstrap` — the engine's one `sys.path` bootstrap — before anything from `scripts/`.

A package whose `__init__` imports its modules to register them (`collectors`, `preprocessors`, `producers`) double-imports such a module under `-m` — runpy warns, the registry sees the module twice. The commands behind those modules enter through top-level entry scripts instead (`process_inbox.py`, `ingest_html.py`, `ingest_youtube.py`, `index_folders.py`); `tests/test_cli_dispatch.py` refuses a handler that reaches into such a package directly.

## Why bash + python + jq?

- **bash** for UI and orchestration — selection menus, scope choice, multi-target install.
- **python** for YAML parsing and config invariants — dataclass-backed, type-coerced, validated.
- **jq** for JSON merge of agent configs — preserves the user's existing hooks instead of clobbering them.

No yaml-in-bash, no json-in-python. Each tool does what it's good at.

## Where to go next

| If you want to… | Go to |
|---|---|
| Add a new agent target (Cursor-like, with hooks) | [AGENTS.md → Adding an agent target](../AGENTS.md#adding-an-agent-target-for-hook-install) |
| Add a tunable to `config.yaml` | [AGENTS.md → Adding a tunable](../AGENTS.md#adding-a-tunable) |
| Add an LLM prompt template | [AGENTS.md → Adding a prompt](../AGENTS.md#adding-a-prompt) |
| Understand the data flows (compile, flush, scanners, curiosity loop) | [docs/PROCESS.md](PROCESS.md) |
| Understand the design rationale (compile-vs-RAG, three layers, cognitive functions) | [docs/concept.md](concept.md) |
| See the architecture as a diagram | [docs/architecture.png](architecture.png) |
| Read locked architectural decisions | [.ytstack/DECISIONS.md](../.ytstack/DECISIONS.md) |
| Read hard-won engine learnings (Ollama gotchas, rate limits, anti-patterns) | [.ytstack/KNOWLEDGE.md](../.ytstack/KNOWLEDGE.md) |
