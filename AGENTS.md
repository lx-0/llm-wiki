# AGENTS.md

Conventions for AI coding agents and human contributors working on this repo.

## Contents

- [What this repo is](#what-this-repo-is) — engine vs vault, three vault layers
- [Repo layout](#repo-layout) — top-level tree
- [Conventions](#conventions) — [tunable](#adding-a-tunable) · [personal data](#adding-per-instance--personal-data) · [prompt](#adding-a-prompt) · [agent target](#adding-an-agent-target-for-hook-install) · [path handling](#path-handling) · [Python env](#python-environment) · [YAML & JSON](#yaml--json) · [side effects](#side-effects)
- [Style](#style) — bash, python, logging, commits
- [When in doubt](#when-in-doubt) — pointers to concept + architecture

## What this repo is

The **tooling** for an LLM Wiki — a Karpathy-pattern personal knowledge base. The repo is not a vault; it's the code that runs inside one.

A vault that uses this tooling has four layers:

1. **`raw/`** — curated sources (LLM reads, never writes). Top-level subfolders: `articles/`, `papers/`, `notes/`, `transcripts/`, `audio/`, `requests/`, `suggestions/`. Scanner output lives in nested per-scanner folders: `raw/notes/email/<account>-<date>.md` (scan-email full sweep) + `raw/notes/email/<account>-delta-<ts>.md` (scan-email incremental piggyback — only mail newer than the per-account watermark in `.wiki/state/email-state.json`), `raw/notes/calendar/<YYYY-MM-DD>.md` (collectors/calendar.py — Google Calendar v3 via OAuth, **multi-tenant** per `personal.accounts.<id>.calendar`, one file per date with frontmatter `event_count`/`meeting_hours`/`focus_hours`/`people`/`event_ids`; recurring-event series collapse to `knowledge/concepts/<slug>.md`; sentinel-delimited managed region preserves operator prose; same-date title-slug match cross-links gmeet+jamie transcripts), `raw/notes/browser/`, `raw/notes/screenshots/screenshots-<slug>.md` (batch reports) + `raw/notes/screenshots/thumb/<file>.png` (384px previews; original PNGs stay in `~/Screenshots/`, never copied; canonical analysis sidecar lives at `~/Screenshots/<file>.md`), `raw/notes/tabs/`, `raw/notes/youtube/<channel>--<title>--<vid>.md` (scan-youtube — video metadata + transcript + comments + optional gemma4 visual analysis, single-file markdown), `raw/transcripts/jamie/<date>--<slug>--<short-id>.md` (collectors/jamie.py — pulls meetings from the Jamie AI tRPC API; summary + speaker-diarised transcript + action-items in one file), `raw/transcripts/gmeet/<date>--<slug>--<meeting-key>.md` (collectors/gmeet.py — exports the Gemini-generated transcript + notes Docs via the Drive API from **two discovery sources** (`folder-scan ∪ email-link-scan`): the own "Meet Recordings" Drive folder, AND `gemini-notes@google.com` emails (`gmeet.email_discovery`, default on) whose `docs.google.com/document/d/<id>` link surfaces colleague-owned / org-shared meetings the folder-scan can't see (`drive.meet.readonly` reads them by Meet-origin, not owner); **one meeting → one file** with paired `## Summary` (Notes-Doc) + `## Transcript` (Transcript-Doc) sections, cross-run merge via stable meeting-key hash of the normalised title), `raw/voice/voice-<date>-<HHMM>-<slug>.md` (collectors/voice.py — folder-watches `personal.voice_inbox` for `.txt`/`.md` dictation transcripts, archives sources under `raw/inbox-mobile/voice/` (M022 two-zone intake); substrate-agnostic on capture, iOS Shortcuts + iCloud Drive is the mobile-primary path; when `features.voice_punctuate=true` (default) the body is pre-processed through Ollama `classify_model` for punctuation + German-noun-case and the original is preserved verbatim under `raw_transcript:` in the frontmatter, fallback-to-raw on any Ollama failure), `raw/captures/capture-<id>.md` (collectors/capture_collector.py — folder-watches `personal.capture_inbox` for `.txt`/`.md`/`.html` quick-captures, computes a content-hash capture-ID `sha256(content.strip())[:12]` (filename-derived, so re-dropping identical content overwrites the same article — idempotent), writes frontmatter `type: capture`/`capture_id`/`captured_at`/`source` with the body verbatim (no punctuation pass), two-zone-archives the source under `raw/inbox-mobile/captures/` (M022 two-zone intake); the content-hash capture-ID is the join-key the M025 correction back-channel keys on), `raw/notes/pictures/pictures-<slug>.md` (collectors/pictures.py — folder-watches `personal.picture_inbox` for `.jpeg`/`.jpg`/`.png`/`.heic`, runs gemma4 vision per file with the photo-shaped `scan_pictures_vision` prompt (scene/objects/action/text_visible/setting), archives sources under `raw/inbox-mobile/pictures/` (M022 two-zone intake) next to a per-image sidecar + writes a 384px thumb to `raw/notes/pictures/thumb/`; batch report carries `type: picture-batch` for dispatch to `compile_pictures.md`), `raw/notes/health/<year>/<date>--<account>.md` (collectors/health.py — daily biometric rollup from the Oura REST API; numeric frontmatter `sleep_hours/sleep_score/readiness_score/hrv_overnight/steps/resting_hr` with `sensitivity: high` and None-valued fields dropped; Phase 1 = Oura only, HealthKit XML drop-folder deferred to Phase 2).
2. **`daily/`** — per-day operational rollup. Two-shape structure since the 2026-05-15 `daily/`-as-rollup arc: (a) `daily/<date>/<source>.md` per-source append-only captures owned by exactly one writer each — `sessions.md` by the session-end hook, `health.md` by `collectors/health.py`, `meetings.md` by `collectors/{gmeet,jamie}.py`, `voice.md` by `collectors/voice.py`, `captures.md` by `collectors/capture_collector.py`, `email.md` by `collectors/email_collector.py` — written via `core.daily_capture` (fcntl-flocked, `KNOWN_SOURCES`-validated). Source-provenance back to the canonical `raw/` file lives in a `sources:` frontmatter list (`daily_capture.append_with_source`), **not** an in-body `[[…]]` wikilink — Obsidian ignores `raw/` (`userIgnoreFilters`), so a body link would render dead. Legacy in-body voice links migrate via `wiki backfill voice-source-frontmatter`; (b) `daily/<date>.md` is the compile-stage digest (≤500 words, distilled across all per-source captures by the `daily-digest` agent / `daily_digest_yesterday` piggyback). The subfolder is Layer-2 immutable capture; the root file is a Layer-3 distillation that lives in `daily/` for operator ergonomics. Lint `check_daily_consistency` flags subfolder-without-digest, root-without-subfolder (legacy pre-rollup state), and unknown source names. Migration of pre-2026-05-15 flat daily files: `scripts/migrate_daily_to_rollup.py`.
3. **`knowledge/`** — LLM-compiled wiki articles (LLM owns, human reads). Subfolders: `concepts/`, `connections/`, `people/`, `projects/`, `qa/`, `facts/` (the last is human-owned via `wiki correct` — hard facts that override anything in raw/daily sources). **Two article shapes coexist**: atomic (one body, used by `concept | connection | qa | moc | fact`) and two-layer State + Timeline (`person | project`, M005) — compiled-truth State block above `---` (with `## State`, `## Action Items` in Obsidian-Tasks-plugin syntax, `## Open Threads`, `## See also`), append-only `## Timeline` below. Compile prompt branches on `type:` (see `prompts/compile_main.md` Instruction 3). Lint (`scripts/lint.py:check_two_layer_pages` + `check_action_item_syntax`) enforces the shape. Tasks extracted from jamie/gmeet substrates land in entity-page Action Items; resolved items demote to Timeline on the next compile pass when substrate evidence appears. **Domain-tag rule:** `concepts/` and `qa/` must carry at least one domain tag from `CONFIG.graph_view.domain_tags` (`check_concept_domain_tag` + `check_qa_schema` lint enforce). Domain tags drive graph-view coloring; notes without one fall into the grey fallback bucket.
4. **`workspace/`** — the operator's working layer (intent-dispatch + a running `todo.md`). The `intents` producer (post-compile, gated `features.extract_intents` + `limits.intent_source_globs`, default off; model `models.intent_classify_model`, a cheap tier) classifies an intake note into an intent `{kind, summary, confidence}` where **kind ∈ task | idea | note | none** (`none` = noise only). Default channels: voice notes (`raw/voice/*`) + the mobile picture channel (`raw/inbox-mobile/pictures/*.md` — camera photos **and** phone screenshots snapped to self; the .md sidecar carries the vision text). Intent attaches to the **ingest channel**, not the file type — desktop screenshots (`raw/notes/screenshots/`) are a different channel and stay out. It routes through the `intents/` handler registry; the `task`/`idea`/`note` handlers write `workspace/inbox/<source-stem>.md` with `type:`/`status: pending` frontmatter (confidence-floor gates `task` only; idea/note are captured liberally). **Operator-facing + Obsidian-visible** — reviewed before anything runs. **Accepting a task is an action, not just a flag:** it MOVES the record out of `inbox/` into `workspace/tasks/<NNN>.md` (numbered: `001.md`, `002.md`, …) and appends a checkbox line `- [ ] <summary> — [[tasks/<NNN>]]` to `workspace/todo.md` (the todo list). Accepting an idea/note files it in place (`status: accepted`, stays in inbox); dismiss sets `status: dismissed`. **Status axes stay separate:** triage = keep/drop; task execution = `accepted → done | blocked`, so `done` always means "task executed", never "triaged". Execution is operator-gated: the `orchestrate-tasks` agent (`prompts/agents/`) reads `workspace/tasks/`, runs each `accepted` task, flips it to `done`/`blocked`, and ticks its checkbox in `todo.md`. Re-dispatch guard in `.wiki/state/intents-seen.json`. Extensible: new outcome kinds = new handler modules under `intents/`; new intake substrates = extend the source-glob list. **Three triage surfaces, one source of truth** (the `status:`/`type:` frontmatter): `wiki triage` (CLI), the dashboard's 📥 Dataview panel, and `triage.html` — a static, server-less browser UI (seeded at vault root; opens the vault via the File System Access API in Chromium) that lists pending records, previews the original photo/voice source, accepts (task → moved to `tasks/` + listed in `todo.md`; idea/note filed), dismisses, and converts note/idea↔task in place. The frontmatter-key contract between `_record.py` and `triage.html` is pinned by `tests/test_triage_record_contract.py`.

The vault holds the **data**. This repo holds the **engine** (compile, flush, lint, query, hooks, prompts).

The **vault's own `AGENTS.md`** (separate file, not this one) is the article schema the compiler embeds into every compile prompt. This file is for contributors working on the codebase.

## Repo layout

```text
llm-wiki/
├── wiki                    ← entry-point CLI (bash, sources lib/*.sh)
├── lib/
│   ├── common.sh           ← paths, colors, log helpers, deps, backup
│   ├── ui.sh               ← interactive prompts (confirm/ask/select_*)
│   ├── agents.sh           ← agent registry + per-agent hook payload generators
│   ├── hooks.sh            ← interactive flows: install/uninstall/status
│   └── config.sh           ← wraps Python config CLI + setup wizard + editor
├── scripts/
│   ├── core/               ← shared engine plumbing (imported, not invoked)
│   │   ├── paths.py            ← eager path constants from __file__ — zero deps
│   │   ├── config.py           ← CONFIG singleton (YAML-driven) + get/set/keys CLI + TIMEZONE + .env bootstrap
│   │   ├── prompts.py          ← prompt template loader (${var} substitution)
│   │   ├── ollama_client.py    ← single Ollama transport (chat / chat_schema / chat_vision)
│   │   ├── sdk_helpers.py      ← StderrCapture + log_sdk_failure + assert_prompt_within_budget (Claude Agent SDK)
│   │   ├── utils.py            ← shared helpers (article listing, JSON state, history) + now_iso/today_iso
│   │   ├── agent_spec.py       ← agent-task spec parser (prompts/agents/*.md → AgentSpec)
│   │   ├── google_oauth.py     ← shared Google OAuth2 helper (local-loopback consent + token cache; used by gmail + gmeet)
│   │   ├── flush_pipeline.py   ← staged-flush state machine (stage/commit/archive/pending)
│   │   └── daily_capture.py    ← fcntl-flocked append/replace into daily/<date>/<source>.md (sources: sessions/health/meetings/voice/email)
│   ├── collectors/         ← substrate→raw/ writers (Registry + scan-* CLIs + dispatcher)
│   │   ├── base.py             ← Collector Protocol, SPEC, Registry
│   │   ├── cli.py              ← `wiki collect` dispatcher (Registry lookup + run-one)
│   │   ├── email_collector.py  ← email collector (renamed from email.py to avoid stdlib shadow)
│   │   ├── jamie.py            ← Jamie AI meeting-notetaker
│   │   ├── gmeet.py            ← Google Meet / Gemini transcripts (Drive API; OAuth via core/google_oauth.py)
│   │   ├── voice.py            ← inbox-watch dictation ingester (iOS Shortcuts / OpenWhispr / FluidVoice) — body punctuated via Ollama `classify_model` when `features.voice_punctuate=true` (default), raw preserved in frontmatter
│   │   ├── pictures.py         ← inbox-watch camera/phone-photo ingester (iOS Shortcut / AirDrop / iCloud Drive) — gemma4 vision per file via `scan_pictures_vision`, batch-report `type: picture-batch`
│   │   ├── health.py           ← daily biometric rollup (Oura REST; HealthKit Phase 2 backlogged)
│   │   ├── calendar.py         ← CalendarCollector (Registry, piggyback, OAuth via core/google_oauth.py) — M006 rewrite 2026-05-15, replaces legacy Thunderbird-SQLite scan_calendar stub
│   │   ├── scan_tabs.py        ← TabsCollector (Registry; migrated 2026-05-13)
│   │   ├── scan_browser.py     ← BrowserCollector (Registry; migrated 2026-05-14)
│   │   ├── scan_screenshots.py ← ScreenshotsCollector (Registry, piggyback; migrated 2026-05-14)
│   │   └── scan_youtube.py     ← YoutubeCollector (Registry; migrated 2026-05-14 — Phase 2 complete)
│   ├── facts/              ← hard-fact subsystem (knowledge/facts/<slug>.md consumers) + takes producer
│   │   ├── correct.py          ← CRUD CLI: add/list/remove/edit/path
│   │   ├── correct_apply.py    ← agent-driven propagation across vault
│   │   └── takes_producer.py   ← maybe_extract_takes legacy free function (delegated-to by producers/takes.py)
│   ├── producers/          ← post-compile derivative-material extractors (Registry + orchestrator + CLI)
│   │   ├── base.py             ← Producer Protocol + ProducerSpec + ProducerResult + Registry (@register, all_producers, get_producer)
│   │   ├── orchestrate.py      ← evaluate_and_run(producer, source) — gate evaluation + dispatch
│   │   ├── cli.py              ← `wiki produce` dispatcher (--list / <name> <source>)
│   │   ├── suggestions.py      ← SuggestionsProducer (delegates to suggestions/producer.py)
│   │   ├── curiosity.py        ← CuriosityProducer   (delegates to curiosity/producer.py)
│   │   └── takes.py            ← TakesProducer       (delegates to facts/takes_producer.py)
│   ├── compile_stages/     ← pure-ish stages extracted from compile.py's per-file loop
│   │   ├── types.py            ← CompileResult + CompileMetadata dataclasses
│   │   ├── compile.py          ← compile_source(content, metadata) → CompileResult (LLM-call boundary)
│   │   └── post_passes.py      ← run_post_passes(source, compile_result, state) → list[ProducerResult] (serial ProducerRegistry iterator)
│   ├── suggestions/        ← email-suggestion pipeline (legacy producer body + executor)
│   │   ├── producer.py         ← maybe_generate_suggestions legacy free function (delegated-to by producers/suggestions.py)
│   │   ├── cli.py              ← interactive approve/review/reject/execute
│   │   └── backends/imap.py    ← IMAP move/tag/set-flags executor
│   ├── curiosity/          ← gap-detection loop (legacy producer body + consumer CLI + backends)
│   │   ├── producer.py         ← maybe_generate_curiosity_requests legacy free function (delegated-to by producers/curiosity.py)
│   │   ├── cli.py              ← wiki curiosity: list / run-oldest / run / run-all / clear-done
│   │   └── backends/email.py   ← email-deep-scan: scan_deep via Mailbox-adapter → raw/notes/email/deep-*.md
│   ├── dashboard/          ← Obsidian dashboard helpers
│   │   ├── dashboard_stats.py  ← _dashboard-stats.md generator (post-flush refresh)
│   │   ├── dashboard_lint.py   ← _dashboard-lint.md generator (post-flush refresh)
│   │   ├── agent_buttons.py    ← agent-button discovery + dashboard.md rewriter
│   │   └── inject_daily_button.py ← idempotent Summarize-button injection into daily/*.md
│   ├── reports/_engine/    ← operator-self-reports surface (air-gapped from compile via COMPILE_SUBSTRATE_EXCLUDED_PREFIXES)
│   │   ├── runner.py          ← run_inference(): substrate-scope resolve + batched SDK calls + persist runs/<ts>/instruments/<slug>.md
│   │   ├── instrument.py + score.py ← yaml loader + deterministic Likert / reverse-coding / cutoff band-lookup
│   │   ├── lib/inference.py   ← infer_batch_async SDK wrapper (3-attempt retry on kind=unknown, scope-locked via make_path_scope_gate([]))
│   │   ├── lib/analyst.py     ← Pass-1 / Pass-2 analyst SDK wrapper (Read+Grep only)
│   │   ├── lib/render_summary.py + lib/charts.py ← cross-instrument radar + per-instrument item-radar + timelines (pure-Python SVG)
│   │   ├── backfill_per_item.py ← one-shot: parse pre-2026-05-17 reports' body `## Items` table → frontmatter `per_item:`
│   │   └── instruments/<slug>/v<x>/{instrument,items,cutoffs}.yaml ← 8 curated instruments (phq-9, gad-7, who-5, k6, asrs-v1.1, pss-10, isi, olbi)
│   ├── study.py            ← wiki study list/run/new/answer CLI (drives reports/_engine/runner.py; per-study fcntl-lock; Pass-1 analyst auto-fires after run)
│   ├── analyze.py          ← wiki analyze CLI (Pass-1 per-study + Pass-2 cross-study synthesis → reports/analyses/<ts>.md)
│   ├── migrations/         ← one-shot schema/data migrations (not active CLI surface)
│   ├── adapters/           ← Mailbox Reader/Filter adapters (thunderbird, gmail, imap; allinkl = filter)
│   ├── domain/             ← pure domain types (mail message, etc.)
│   ├── compile.py          ← Claude Agent SDK compiler (raw/daily → knowledge/); per-file loop calls compile_stages.compile_source for the LLM call, then compile_stages.run_post_passes for the producer post-pass
│   ├── flush.py            ← session-end → daily/ append + piggyback spawner
│   ├── lint.py             ← 8 structural checks + 1 LLM contradiction check
│   ├── query.py            ← Claude Agent SDK query (read-only or file-back)
│   ├── process-inbox.py    ← classify dropped files into raw/ subfolders
│   ├── optimize-claude-md.py ← suggests CLAUDE.md edits from compiled patterns
│   ├── review-wiki.py      ← per-article quality scoring (Ollama)
│   └── retry-failed-flushes.py ← reprocess archived flush contexts
├── hooks/
│   ├── _transcript.py      ← shared transcript walker + tool summarizer
│   ├── session-start.py    ← inject a pointer block + recent daily-log tail; agent pulls articles on demand
│   ├── session-end.py      ← spawn flush.py with the conversation transcript
│   └── pre-compact.py      ← safety-net flush before context compaction
├── prompts/                ← LLM prompts as .md files (${var} placeholders)
├── config.example.yaml     ← copy → config.yaml on install (gitignored)
├── pyproject.toml + uv.lock
├── install.sh              ← one-liner installer
└── docs/                   ← concept, architecture, plans
```

## Conventions

### Adding a tunable

1. Extend the matching dataclass in `scripts/core/config.py`.
2. Document the default in `config.example.yaml` with a comment.
3. Document it in `docs/config.md` (the grouped reference).
4. Replace the hardcoded constant in the script with `CONFIG.<section>.<field>`.
5. Don't add ad-hoc constants back to scripts — extend the config layer.
6. **Add the key to `scripts/migrations/migrate_config_keys.py`** under
   `KEY_ADDITIONS[<parent>]` with the same default. Operator vaults already
   carry their own `config.yaml`; without this entry the new key is invisible
   to the operator (dataclass defaults silently fire) and any rollout that
   depends on the operator *seeing* the knob is broken. Same rule for
   renames (extend `PIGGYBACK_RENAMES` etc.) and removals (`new_key=None`).
   Direct edits to `<vault>/.wiki/config.yaml` are forbidden — the migration
   is the only legal write path into an operator vault.

### Adding per-instance / personal data

Different rule for anything personal: email addresses, customer/partner names,
hostnames, mbox paths, project names mentioned in prompts, etc.

1. Extend `Personal` in `scripts/core/config.py`.
2. `config.example.yaml` ships an **empty** default for the field — never a real value.
3. The actual value goes in the user's local `config.yaml` (gitignored).
4. Consumers (prompts via `${var}`, compile.py schema enums, scan-* runtime maps) read
   `CONFIG.personal.*` and handle the empty case gracefully.
5. Single source of truth: if a value drives both a prompt AND a schema enum, BOTH read
   from `CONFIG.personal.*` (e.g. `email_folders` drives `compile_curiosity.md` listing
   AND `compile.py`'s schema `enum`). No drift.

### Frontmatter — author attribution

Source files may carry an optional `author: <name>` (or `author: [name1, name2]`) frontmatter key. When present, `compile.py` routes distilled beliefs/decisions/opinions to that person's `knowledge/people/<slug>.md` page. When absent, the compile prompt falls back to `personal.implicit_operator_author` (single-tenant convenience; null by default — multi-tenant vaults leave unattributed content generic). Explicit `author:` always wins.

`personal.implicit_operator_author` is also the **canonical vault-owner identifier**. When set, `compile.py:_build_owner_block()` renders a "## Operator / vault owner" section into every substrate compile prompt, naming the owner and pointing the agent at `knowledge/people/<slug>.md`. This lets the agent resolve self-references ("I", "we", "my company") and find connection targets without grepping AGENTS.md prose. Null = no section rendered, multi-tenant story unchanged.

`knowledge/` articles may carry an optional `domain:` frontmatter key — a cross-cutting life-domain axis (default enum `company | personal | ai | meta`, extensible via `CONFIG.personal.domains`). Pure filter, never required: untagged articles appear in every view. Lint `check_domain_value` warns (not errors) on values outside the configured enum. `wiki query --domain <value>` restricts an answer to articles whose `domain:` matches. Lifted from the lx-vault audit; spec: `.ytstack/backlog/domain-frontmatter.md`.

`personal.output_language` (default `"auto"`) pins the **output prose language** of compiled `knowledge/**` articles. `"auto"` keeps today's behavior (write in the source material's language; byte-identical compile). Any other value (`"de"`, `"German"`, `"fr"`, …) forces all compiled prose into that language regardless of source, while keeping code, technical identifiers, proper names, and the canonical structural section headers (`## State`, `## Timeline`, …) verbatim. Injected via `${output_language_instruction}` (built by `core.prompts.build_output_language_instruction`) into every compile substrate prompt and — since 0.2.1 — the curiosity (`curiosity/producer.py`) + dream-entity (`dream.py`) render paths, so forced language also covers curiosity gap-questions and resynthesized entity pages. Distinct from `personal.voice_transcribe_language` (input transcription vs. output prose). Issue #4.

### Frontmatter — `compile_role` axis (M007)

Any `.md` file in the vault may carry `compile_role:` with one of 3 values, controlling how `compile.py` treats it:

- **`source-only`** (default for raw/, daily/, inbox/, knowledge/) — substrate; distilled into `knowledge/` articles. Today's behavior unchanged.
- **`source-and-final`** — the page IS the final form. `compile.py` extracts wikilinks, appends an entry to `knowledge/index.md` by its full pathname, marks it ingested in state.json, but does NOT call the SDK and does NOT produce a separate `knowledge/concepts/<title>.md`. Use for operator-authored long-form: strategy workdocs, manifestos, opinion essays. Convention: place under `raw/notes/longform/`.
- **`final-only`** — engine-skip; hand-curated; reachable via grep/Obsidian search/graph but hidden from MOC auto-includes, dashboard active panes (`articles_total` excludes; `articles_final_only` exposes count), and `wiki query` default scope (use `--include-final-only` to re-include). Use for archived knowledge that's still reference-worthy.

Default inference: when frontmatter omits `compile_role:`, the role is inferred from the file's top-level segment per `core.compile_role.LOCATION_DEFAULTS`. Toggle via `CONFIG.limits.compile_role_default_by_location` (default true). Explicit frontmatter always wins. Lint (`check_compile_role`) rejects unknown enum values.

When referencing a `source-and-final` page from compiled `knowledge/` articles: cite by pathname (`[[raw/notes/longform/<name>]]`), do NOT create a parallel `knowledge/concepts/<same>.md`, do NOT add the path to `compiled_from:` (that key is for distilled substrate). Connections-articles linking source-and-final to other concepts ARE allowed (operator-authored final form + LLM-synthesized analysis layered on top).

MOC auto-include Dataview blocks in `templates/knowledge/MOCs/{concepts,people,projects,areas}.md` carry `WHERE compile_role != "final-only"`. `pin.py` refuses to manually pin a final-only article (operator must edit frontmatter first if they really want it back in active surfaces).

### Tuning dream-cycle entity selection (M017)

The `dream_cycle` piggyback periodically re-synthesizes entity pages (`knowledge/people/`, `knowledge/projects/`, …). By default every overdue entity has equal weight (greedy, oldest first). To bias which entities get auto-dreamed more often, set rules under `scheduling.dream_priority` in `config.yaml`:

- **`default`** (float, default 1.0) — baseline weight for entities no rule matches.
- **`paths`** (dict glob→float) — first-match-wins; `0` excludes from auto-sweep entirely (operator can still `wiki dream <slug>` manually).
- **`domain`** (dict, M013 `domain:` frontmatter → float multiplier).
- **`tags`** + **`tag_strategy`** (`max | sum | first`) — multiplier from page tags.
- **`status`** (dict, e.g. `active: 1.0`, `dormant: 0.3`, `retired: 0.05`).

Resolution order: per-entity frontmatter `dream_priority: <float>` (absolute override) → config `paths:` first-match → formula `default × domain × tag(max|sum|first) × status`. Selection mode for `wiki dream` is `--selection-mode {probabilistic, greedy}` (default greedy). `wiki dream` defaults to a full sweep; `--all-entities` and `sweep` are accepted as legacy aliases.

Debug current ranking with `wiki dream list-candidates --limit 15` — prints rank/weight/priority/age/slug/source-trace per entity. Spec: `.ytstack/backlog/dream-priority-config.md`.

### Concept-reconciliation routine (`wiki reconcile`)

Autonomous consistency loop for `knowledge/concepts/`. Signal-driven: it consumes `lint.check_facts_violations()` (it does NOT detect anything new), groups violations by hard fact, and auto-reconciles the flagged concepts via the STRICT `facts/correct_apply.py::reconcile_fact()` — writes scope-locked to `knowledge/concepts/` (PreToolUse hook, no Bash), structural gates (`concept_reconcile_max_files_per_fact` — skip a fact touching more concepts as too-broad/manual-review — + `_max_facts_per_run`), and a per-fact cooldown stamped as `last_reconciled:` in the fact's frontmatter. Tiered autonomy: only `fact_violation` is auto-fixed (the fact is authority); concept↔concept contradictions + quality are PROPOSE-ONLY, left in the lint/dashboard surface. `correct_apply.apply()` (the broad operator-driven whole-vault propagation) is **also sandboxed since M028** (issue #5 — it had been wide-open with Bash + acceptEdits and once deleted 17 articles applying one fact): `negation`/`supersession` now **supersede by default** (annotate `status: superseded` + `superseded_by:` + banner, never delete history), the agent has no Bash and proposes renames/deletions in a fenced-JSON `## Proposed actions` block the engine executes (renames via `core.links.rename_article`; deletions opt-in via `--allow-delete` / fact `disposition: delete` → `.trash/<ts>/`, gated behind a clean-git-tree precondition unless `--force`), and the engine reports the real filesystem delta with a divergence alarm. `supersession` is a first-class status (was-true-now-outdated) that is annotate-only — never delete-eligible.

Double-gated OFF: needs `features.concept_reconciliation: true` AND a `piggybacks.concept_reconcile` block. `wiki reconcile` is dry-run by default; `--apply` self-downgrades to dry-run when the flag is off. Spec: `.ytstack/backlog/concept-consistency-routine.md`.

### Health-trend synthesis (`wiki health-trends`)

Deterministic ($0, no LLM) synthesis consumer for the health corpus. Per-day `type: health-rollup` stubs are correctly not knowledge (compile skips them deterministically); trends are. `scripts/health_trends.py` walks `raw/notes/health/**` frontmatter, aggregates every numeric metric by month (range, all-time avg, recent-window avg, coverage-aware trend arrow), and upserts ONE sentinel-managed `## Trends` block (`<!-- health-trends:begin/end -->`) into `knowledge/concepts/health.md` (created if absent; mirrors the backlinks-footer sentinel). Idempotent, regenerated wholesale each run. Knobs: `limits.health_trends_recent_months` (6), `limits.health_trends_min_coverage_days` (10). Double-gated OFF: `features.health_trends` + a `piggybacks.health_trends` block; `wiki health-trends` falls back to dry-run when off. A narrative/LLM layer is a deliberate later addition. Spec: `.ytstack/backlog/health-trend-synthesis.md`.

### Dream web-research — public-entity enrichment (`wiki dream web-research`, issue #2)

A dream POST-PASS (NOT a compile producer — the `scripts/producers/` registry is post-compile-shaped; web-research operates on a compiled `knowledge/people/<slug>.md` after synthesis). When gated on, it researches a PUBLIC person via Exa AI and upserts a sentinel-managed `## Public Profile` block (`<!-- web-research:begin/end -->`). Doubly gated OFF: `features.dream_web_research` (vault) AND a per-entity opt-in — frontmatter `web_research: true` OR the `public-person` tag. Own cooldown `scheduling.web_research_cooldown_days` (30d, the block self-stamps `last updated:`); key `personal.exa_api_key` or env `EXA_API_KEY`. **Air-gapped from `raw/`** — `run_web_research` refuses any target outside `knowledge/` (the block must never re-enter `raw/`, or the compiler would re-synthesize web text as operator-authored substrate). Runs automatically after a successful `wiki dream <slug>`; forced standalone `wiki dream web-research <slug> [--dry-run]`. Fail-soft: a backend error never breaks the dream. Spec: `.ytstack/backlog/dream-web-research.md`.

### Entity dedup — transcription-noise duplicates (`wiki dedup`, issue #3)

STT transcribers (Jamie, voice) garble names consistently, planting silent duplicate entity pages (`josefine-bartsch`/`josephine-bartc`, `veltari`/phantom `veltary`). `scripts/dedup.py` detects candidate pairs in `knowledge/{people,projects,areas}/` with $0 deterministic signals — `difflib` fuzzy on title+aliases (floor `limits.dedup_fuzzy_threshold`, 0.85), a German-aware phonetic key (vowel-drop + consonant folding; exact collision OR near-match), and shared `compiled_from` (boost-only — co-occurrence in a daily digest is not duplication). Cross-kind pairs are never proposed. Every merge is operator-confirmed: B's Timeline / Action Items / Open Threads + `aliases` + `compiled_from` fold into A, every `[[wikilink]]` B→A is rewritten across `knowledge/` (via `core.links`, the single resolver — never a second hand-rolled rewriter), B is backed up (`.bak.<ts>`) + deleted, and a `status: negation` canonical-name hard fact is recorded so lint flags any reappearance. `wiki dedup [--suggest-only|--dry-run|--threshold]` + `wiki dedup merge B --into A`. Spec: `.ytstack/backlog/entity-dedup.md`.

### Token-usage accounting (`wiki usage`)

Every LLM call is metered in TOKENS, keyed by `(provider, model)` — never dollars (Claude is a subscription, Ollama is local; `total_cost_usd` is meaningless / conflates billing). `core/usage.py` (`UsageLedger`, process-global `LEDGER`) records at each call site (the Ollama client auto-records; Claude SDK sites record `AssistantMessage.usage` after their loop) and `atexit`-flushes per-run totals to `state/usage.json` (fcntl-locked, `date → provider:model → {input,output,calls}`). `wiki usage [--days N] [--json]` reads it back. Gates are token/structural, not USD: `compile_max_tokens_per_file` (batch-abort, `kind=tokens_exceeded`), `dream_entity_max_prompt_chars` (size guard) + `dream_cycle_max_tokens_per_run`, reconcile's file/fact-count gates. A dollar figure may appear only for a provider explicitly registered as pay-per-token (none today). Accounting half of the M021 model seam. Spec: `.ytstack/backlog/token-usage-accounting.md`; DECISIONS 2026-05-23.

### Adding a seedable config (drift + overlay rules)

`wiki seed` applies `templates/` into the vault. How a template file is handled depends on whether operators customise it:

- **Engine-owned (markdown/YAML — `AGENTS.md`, `dashboard.md`, `knowledge.base`):** whole-file via `_seed_file`. Seed-if-missing, keep-if-exists, refresh with a targeted `wiki seed <path> --force`. Operators shouldn't hand-edit these; they're regenerated.
- **Customisable JSON configs (`graph.json`, `app.json`, plugin `data.json`):** route through `_seed_json_overlay`. The engine owns the template (base); the operator's delta lives in an **untracked** overlay at `<vault>/.wiki/custom/<rel>`; the live file is derived as `template ⊕ overlay` (jq deep-merge). This keeps the file engine-updatable (new keys flow in) while preserving customisations — operators edit the overlay, `--force` re-derives non-destructively, `wiki seed --extract-custom <rel>` bootstraps an overlay from existing drift. NEVER make a customisable config keep-or-`--force` whole-file — that recreates the force-vs-drift dilemma.
- **Accumulating lists (community-plugins, shell-commands, meta-bind buttons):** bespoke additive-merge-by-id/union (`_merge_*`), preserving operator entries while adding/updating engine-managed ones.

Drift detection is JSON-key-order-insensitive (`_files_equivalent` / canonical `jq -S`), so don't worry about Obsidian re-serialising key order.

### Adding a prompt

1. Drop `<name>.md` into `prompts/`.
2. Use `${var}` for placeholders (not Python's `{var}` — JSON/YAML examples in prompts have literal braces).
3. Call `from prompts import render` and `prompt = render("name", var=value)`.

**Per-prompt model (Prompty-style frontmatter).** A prompt MAY open with a YAML frontmatter block declaring its model — e.g. `scan_pictures_vision.md` / `scan_screenshots_vision.md` pin `model: qwen2.5vl:7b` (strong local OCR) and `intent_classify.md` pins `model: claude-haiku-4-5` (cheap triage). `render()` strips the frontmatter from the body (it never reaches the LLM); the caller resolves the model with `prompt_model("<name>", <fallback>, …)` — **frontmatter `model:` wins, else the first truthy fallback** (caller default → config knob → `compile_model`). This puts the model choice next to the prompt it belongs to instead of hardcoded at the call site; config knobs (`models.vision_model`, `models.intent_classify_model`) remain the fallback. (Agent-task specs `prompts/agents/*.md` carry their own `model:` via `AgentSpec`, a separate parser.)

### Adding an agent target (for hook install)

1. Add a tuple to `WIKI_AGENTS` in `lib/agents.sh`: `name|detection-dir|config-file`.
2. Add `<name>_hooks_payload()` function emitting JSON for that agent's schema.
3. Wire it into `agent_payload()`'s case statement.
4. Status table, install/uninstall flows, and detection logic pick it up automatically.

### Wikilinks (relative-to-file convention)

A link in a markdown file is relative to that file. Obsidian resolves a slash-bearing wikilink against the **vault root** (`<vault>/`, where `.obsidian/` lives), so the historic `[[concepts/foo]]` form — relative to `knowledge/`, not the article — pointed at the non-existent `<vault>/concepts/foo.md` and Obsidian offered to create an empty stub when clicked from a nested article. Links are now stored **relative to their containing article**: same-bucket `[[foo]]`, cross-bucket `[[../people/alex]]`, substrate `[[../../daily/2026-05-15.md]]`.

`core.links` is the single resolver (`resolve_link`, `canonical_slug`, `relativize_text`). When **authoring** links (prompts, `wiki pin`, hand-edits) use the unambiguous full-path form `[[knowledge/<type>/<slug>]]` or `[[daily/…]]`/`[[raw/…]]` — the `relativize_wikilinks` post-compile pass (gated by `features.relativize_wikilinks`, default on) rewrites every link to the correct relative path. Don't hand-compute `../`. `core.backlinks` renders footers relative; `lint` resolves source-relative. `index.md` is exempt (its links already resolve source-relative from `knowledge/`). One-off corpus migration: `scripts/migrations/relativize_wikilinks.py --vault <vault> --apply`.

### Path handling

Scripts use `Path(__file__).resolve().parent` for `SCRIPTS_DIR`, `.parent.parent` for `WIKI_DIR`, `.parent.parent.parent` for the vault root. After `install.sh` clones the repo into `<vault>/.wiki/`, this resolves correctly. Don't hardcode absolute paths.

### Python environment

The Python venv lives at `<vault>/.wiki/.venv/` (inside the engine, NOT at the vault root). `install.sh` runs `uv sync --project <DEST>` so this happens automatically. Two ways to invoke scripts:

- **Interactive** — `cd <vault>/.wiki && uv run python scripts/<X>.py <args>`. Matches all script docstring examples.
- **From any CWD** — `uv run --project <vault>/.wiki python <vault>/.wiki/scripts/<X>.py <args>`. Used by hooks (the `--project` flag is hardcoded in the agent settings.json so the hook works regardless of which directory the user's session was launched from).

`hooks/session-end.py` and `hooks/pre-compact.py` spawn `flush.py` with `--project` for the same reason. Anything that spawns engine scripts from outside `.wiki/` MUST pass `--project`, otherwise `uv` can't find `pyproject.toml`.

### YAML & JSON

- **YAML editing in CLI** → goes through `config.py set` (Python with PyYAML). Bash never parses YAML.
- **JSON merge for agent configs** → `jq` deep-merge in `lib/agents.sh`. Always backup before write.
- **LLM JSON output** → use `jsonrepair` or schema-constrained decoding (Ollama `format` field). Never raw `JSON.parse`.

### Side effects

- Hooks run in **<10s** budget — no API calls, only file I/O. Heavy work goes to spawned background processes (`flush.py`, piggybacks).
- `compile.py` and `query.py` use the Claude Agent SDK with `model=CONFIG.models.compile_model`. Other scripts use Ollama (configurable via `models.ollama_url`).

### Evaluating a new intake channel (substrate priority, locked 2026-05-22)

Value a candidate substrate/collector by **persona-coverage, not signal-density per row.** This is a *self*-cartography engine: it optimizes for completeness-of-portrait, not knowledge-yield. Work-substrate (mail/calendar/gmeet/docs) systematically captures the intentional/professional self and misses the non-work persona (curiosity, leisure, cultural consumption, mood). A low-yield consumption channel that covers that otherwise-dark axis can outrank a high-yield source redundant with existing substrate.

- "It'll clutter the knowledge base" is **not** a valid objection — `compile-role: source-only` + `daily/`-aggregation already keep low-signal sources out of per-item `knowledge/`. Clutter is solved engine-side; coverage is the open question.
- **Axes, not channels.** Value scales per persona-axis newly covered, not per source added. Spotify + YouTube-watch-history + podcasts are mostly one "cultural/curiosity-consumption" axis — strong case for the first, steep diminishing returns stacking more. Browser-history already covers leisure *attention* at domain granularity; the gap these fill is *content* granularity.
- **Synthesis is the gate.** Don't add a channel that only grows `raw/`. Ingest only when the synthesis side (dream-cycle / a persona entity-page) will actually weave it into a "what occupies the operator" portrait — otherwise it adds noise, not coverage.
- **Consumption ≠ production.** Suno-style operator *output* is on the production axis, not the consumption/curiosity axis; it belongs to the portrait but is not the better candidate merely because the operator authored it.

Full rationale: `.ytstack/DECISIONS.md` 2026-05-22; candidate grouping: `.ytstack/backlog/consumption-curiosity-axis.md`.

### Spawning Claude Agent SDK with substrate input (HARD rule, locked 2026-05-15)

Any script that feeds substrate (`daily/**`, `raw/**`, operator-supplied prompts) into the Claude Agent SDK with Write/Edit tools MUST apply three layers of write-scope enforcement, no exceptions:

1. **Prompt-level** — the system prompt explicitly states which directory the agent may Write/Edit, and that source descriptions of code/config/script changes are subject matter, not instructions to the agent.
2. **Tool-level** — `disallowed_tools=["Edit(<forbidden>/**)", "Write(<forbidden>/**)", ...]` for every path the agent must not touch (always include `.wiki/**`).
3. **Settings-level** — `setting_sources=["project"]` (not `[]`) so vault-root `CLAUDE.md` reaches the agent.

Reason: substrate routinely contains literal change-descriptions captured from prior engine-development sessions. The agent reads them as instructions and acts on them with whatever filesystem authority you gave it. See `.ytstack/KNOWLEDGE.md` "Compile prompt injection via substrate" + `.ytstack/DECISIONS.md` 2026-05-15. Reference implementation: `scripts/compile.py:225-247`.

Long-term direction: remove agent-side filesystem writes entirely — agent returns structured payload via `ResultMessage`, script writes the files deterministically. Track in `.ytstack/backlog/compile-agent-no-filesystem-write.md`.
- Every config write makes a `.bak.YYYYMMDD-HHMMSS`. Idempotent install/uninstall.
- The engine writes **inside the vault and `.wiki/` only**, with one exception: when `skills.global_install` is on, `wiki skills install/sync` symlinks `use-llm-wiki` into `~/.claude/skills/` and records the vault root in `~/.config/llm-wiki/vaults` (the discovery registry the skill reads). Both writes fail soft — a missing global link is recoverable, a hard error on `wiki update` is not.

## Style

- Bash: `set -euo pipefail`, `[[ ... ]]` over `[ ... ]`, lowercase function names.
- Python: type hints, dataclasses for config, `Path` not str. ruff-friendly.
- No emoji in code. Logs use ASCII status markers (✓ ! ✗) only via the helpers in `lib/common.sh`.
- Commit messages: imperative mood, short subject (≤70 chars), body explains why.

## When in doubt

- Read `docs/concept.md` for the design rationale.
- Read `docs/architecture.excalidraw` (open in Obsidian / excalidraw.com) for the data flow.
- Read `docs/FEATURES.md` for the implementation map (status, code location, known gaps per feature). Update it whenever you add / move / retire a feature.
- Check `.ytstack/backlog/` for unvalidated future-milestone pitches; `.ytstack/STATE.md` for current milestone status.
