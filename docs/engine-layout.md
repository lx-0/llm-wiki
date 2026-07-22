# Engine layout

The engine lives under `<vault>/.wiki/` — hidden from Obsidian's file tree (Obsidian ignores `.`-prefixed directories) and never modified by hand. This doc is the file-by-file reference for contributors and operators who want to see exactly what's inside.

For a higher-level view (vault layout, install, CLI usage), see the [README](../README.md). For development conventions (style, side-effect rules, how to add a tunable / prompt / agent target), see [AGENTS.md](../AGENTS.md).

> **Hard rule — `.venv/` location.** The Python virtualenv lives at `<vault>/.wiki/.venv/`, never at the vault root. `install.sh` runs `uv sync --project <DEST>` precisely to enforce this. A vault-root `.venv/` would leak engine internals into the data layer and break `wiki update` round-trips. If you find one there, delete it and re-run `uv sync --project <vault>/.wiki`.

## Contents

- [Directory tree](#directory-tree)
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
│   │   ├── errors.py              ← swallow(label) — labeled intentional exception suppression (AGENTS.md § Exception handling)
│   │   ├── daily_capture.py       ← fcntl-flocked append/replace_section/replace_block into daily/<date>/<source>.md
│   │   ├── utils.py               ← shared helpers (article listing, JSON state, history) + now_iso/today_iso
│   │   ├── backlinks.py           ← corpus-wide backlinks-footer materialization (post-compile global pass; sentinel-managed `## Backlinks` per article)
│   │   ├── agent_spec.py          ← agent-task spec parser (prompts/agents/*.md → AgentSpec)
│   │   ├── google_oauth.py        ← Gmail OAuth2 bootstrap (local-loopback consent flow)
│   │   └── flush_pipeline.py      ← staged-flush state machine (stage / commit / archive / pending)
│   ├── cli.py                 ← table-driven `wiki` dispatcher — the CommandSpec table is the single source of truth for the command catalog (help/menu derive from it; owns the once-per-command locked dashboard refresh + `wiki auth`)
│   ├── collectors/            ← substrate→raw/ writers (Registry + scan-* CLIs + dispatcher)
│   │   ├── base.py                ← Collector Protocol, SPEC, Registry + account-loop harness (resolve_accounts/filter_accounts/Watermark/run_account_loop) + inbox-intake harness (scan_inbox/archive_to_zone/append_rollup)
│   │   ├── cli.py                 ← `wiki collect` dispatcher (Registry lookup + run-one; honors --account via SPEC.supports_account_loop)
│   │   ├── folder_index.py        ← body-blind folder index (`wiki index`; registered as the `folder-index` collector)
│   │   ├── email_collector.py     ← email Collector (multi-backend via adapters/mailbox/)
│   │   ├── jamie.py               ← Jamie AI meeting-notetaker
│   │   ├── gmeet.py               ← Google Meet / Gemini transcripts (Drive API)
│   │   ├── voice.py               ← inbox-watch dictation ingester (iOS Shortcuts / OpenWhispr / FluidVoice)
│   │   ├── health.py              ← Oura REST daily biometric rollup (sleep / readiness / HRV / steps)
│   │   ├── calendar.py            ← Google Calendar v3 → per-date rollups (multi-tenant, OAuth; M006 — replaces legacy scan_calendar SQLite stub)
│   │   ├── scan_browser.py        ← Firefox + Chrome bookmarks/history/tab-groups
│   │   ├── scan_screenshots.py    ← ~/Screenshots/ + Vision LLM (gemma4) → HOME sidecar + vault thumb (384px) + batch report
│   │   ├── scan_tabs.py           ← Firefox Simple Tab Groups backups
│   │   └── scan_youtube.py        ← yt-dlp + youtube-transcript-api + optional gemma4 visual analysis
│   ├── adapters/              ← MailboxReader + calendar.googleapis.com client used by collectors
│   │   ├── calendar/google.py     ← Google Calendar v3 REST wrapper (list_calendars / list_events / get_event)
│   │   └── mailbox/{gmail,thunderbird,allinkl,imap,base}.py
│   ├── domain/                ← pure domain types (mail message, filter rule)
│   ├── preprocessors/         ← in-vault intake normalizers (pre-compile; Protocol + Registry, singletons)
│   │   ├── base.py                ← Preprocessor Protocol, PreprocessorSpec, PreprocessResult, Registry
│   │   ├── cli.py                 ← `wiki preprocess` dispatcher (--list / <name> [source] [--dry-run])
│   │   ├── inbox.py               ← <vault>/inbox/ classifier (shim: scripts/process-inbox.py)
│   │   ├── html_ingest.py         ← HTML file/URL → raw/articles (named to avoid the stdlib `html` shadow; shim: scripts/ingest-html.py)
│   │   └── clippings.py           ← <vault>/Clippings/ sweep (shim: scripts/clippings_sweep.py)
│   ├── facts/                 ← hard-fact subsystem (knowledge/facts/<slug>.md consumers) + takes producer
│   │   ├── correct.py             ← CRUD CLI: add/list/remove/edit/path
│   │   ├── correct_apply.py       ← agent-driven propagation across vault
│   │   └── takes_producer.py      ← maybe_extract_takes legacy free function (delegated-to by producers/takes.py)
│   ├── producers/             ← post-compile derivative-material extractors (Registry + orchestrator + CLI)
│   │   ├── base.py                ← Producer Protocol, ProducerSpec, ProducerResult, Registry (`@register`, `all_producers`, `get_producer`)
│   │   ├── orchestrate.py         ← `evaluate_and_run(producer, source)` — gate evaluation + dispatch
│   │   ├── cli.py                 ← `wiki produce` dispatcher (`--list` / `<name> <source>`)
│   │   ├── suggestions.py         ← SuggestionsProducer (delegates to `suggestions/producer.py:maybe_generate_suggestions`)
│   │   ├── curiosity.py           ← CuriosityProducer   (delegates to `curiosity/producer.py:maybe_generate_curiosity_requests`)
│   │   └── takes.py               ← TakesProducer       (delegates to `facts/takes_producer.py:maybe_extract_takes`)
│   ├── compile_stages/        ← pure-ish stages extracted from compile.py's per-file loop
│   │   ├── types.py               ← CompileResult + CompileMetadata dataclasses
│   │   ├── compile.py             ← `compile_source(content, metadata) → CompileResult` (LLM-call boundary: prompt assembly, owner-block, pre-flight gate, SDK call, retry-on-kind-unknown, failure classification)
│   │   └── post_passes.py         ← `run_post_passes(source, compile_result, state) → list[ProducerResult]` (iterates ProducerRegistry serially, accumulates `producer_cost_total` into state)
│   ├── suggestions/           ← email-suggestion pipeline (legacy producer body + executor)
│   │   ├── producer.py            ← `maybe_generate_suggestions` legacy free function (delegated-to by producers/suggestions.py)
│   │   ├── cli.py                 ← interactive approve/review/reject/execute
│   │   └── backends/imap.py       ← IMAP move/tag/set-flags executor
│   ├── curiosity/             ← gap-detection loop (legacy producer body + consumer CLI + backends)
│   │   ├── producer.py            ← `maybe_generate_curiosity_requests` legacy free function (delegated-to by producers/curiosity.py)
│   │   ├── cli.py                 ← `wiki curiosity` consumer: list / run-oldest / run / run-all / clear-done
│   │   └── backends/email.py      ← email-deep-scan dispatch via Mailbox-adapter `scan_deep`
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
│   │   ├── lib/inference.py       ← `infer_batch_async` SDK wrapper (3-attempt retry + scope-lock + StderrCapture)
│   │   ├── lib/analyst.py         ← Pass-1 / Pass-2 analyst SDK wrapper (Read+Grep scope-locked)
│   │   ├── lib/render_summary.py  ← cross-instrument meta-report (radar + sparkline + per-instrument item-radar + timelines)
│   │   ├── lib/charts.py          ← pure-Python SVG renderers (no matplotlib)
│   │   ├── lib/timeline.py        ← cross-run aggregator → `Timeline` of `RunSnapshot[InstrumentSnapshot]`
│   │   ├── lib/{cutoffs,likert,verify_report}.py  ← scoring + band-lookup + post-write integrity check
│   │   └── instruments/<slug>/v<x>/  ← curated instrument definitions (currently 8: phq-9, gad-7, who-5, k6, asrs-v1.1, pss-10, isi, olbi; 6 on the live longitudinal-baseline manifest)
│   ├── study.py               ← `wiki study list / run / new / answer` CLI (drives `scripts/reports/_engine/runner.py`)
│   ├── analyze.py             ← `wiki analyze` CLI — Pass-1 per-study + Pass-2 cross-study synthesis
│   ├── migrations/            ← one-shot schema/data migrations
│   │   └── migrate_add_type.py    ← backfill type: frontmatter
│   ├── compile.py             ← Claude Agent SDK compiler (raw/ + daily/<date>/* + daily/<date>.md → knowledge/); per-file loop delegates the LLM call to `compile_stages/compile.py:compile_source` and the post-pass loop to `compile_stages/post_passes.py:run_post_passes`
│   ├── flush.py               ← session-end → daily/<date>/sessions.md append + piggyback spawner
│   ├── migrate_daily_to_rollup.py   ← one-shot: legacy daily/<date>.md → daily/<date>/sessions.md
│   ├── backfill_daily_rollup.py     ← one-shot: raw/{health,voice,transcripts/{jamie,gmeet}} → daily/<date>/{health,voice,meetings}.md
│   ├── cleanup_legacy_daily_roots.py ← one-shot: byte-match-verified delete of legacy daily/<date>.md
│   ├── daily_digest_runner.py       ← piggyback wrapper for `wiki agent daily-digest`
│   ├── lint.py                ← structural checks over a once-built LintContext corpus (footer-aware link graph) + 1 LLM contradiction check
│   ├── query.py               ← Claude Agent SDK natural-language query (read-only / file-back)
│   ├── agent_task.py          ← generic Claude Agent SDK runner for prompts/agents/*.md
│   ├── clippings_sweep.py     ← thin shim → preprocessors/clippings.py (<vault>/Clippings/ → raw/articles/, pre-compile lift)
│   ├── ingest-html.py         ← thin shim → preprocessors/html_ingest.py (HTML file or URL → text + visual)
│   ├── process-inbox.py       ← thin shim → preprocessors/inbox.py (<vault>/inbox/ → classify + move to raw/ subfolder)
│   ├── review-wiki.py         ← per-article quality scoring via local LLM
│   ├── optimize-claude-md.py  ← cross-project pattern → ~/.claude/CLAUDE.md edits
│   ├── retry-failed-flushes.py ← reprocess archived flush contexts
│   ├── pin.py                 ← `wiki pin <article>` — append wikilink to a MOC section (no LLM)
│   └── health.py              ← read-only colored ASCII vault dashboard
├── hooks/
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
    ├── .venv/                 ← uv-managed Python environment
    ├── state/                 ← *.json hash trackers, dedup, cooldowns
    ├── logs/                  ← flush.log + flush-errors.log (WARNING+), compile.log (full stderr-mirror) + compile-errors.log (WARNING+)
    ├── sessions/              ← session-flush staging + failed-flushes/
    └── reports/               ← lint + review-wiki output
```

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
