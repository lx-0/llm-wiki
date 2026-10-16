# AGENTS.md

Conventions for AI coding agents and human contributors working on this repo.

## Contents

- [What this repo is](#what-this-repo-is) — engine vs vault, three vault layers
- [Repo layout](#repo-layout) — top-level tree
- [Conventions](#conventions) — [tunable](#adding-a-tunable) · [personal data](#adding-per-instance--personal-data) · [prompt](#adding-a-prompt) · [agent target](#adding-an-agent-target-for-hook-install) · [path handling](#path-handling) · [Python env](#python-environment) · [YAML & JSON](#yaml--json) · [side effects](#side-effects) · [exception handling](#exception-handling-decision-tree)
- [Style](#style) — bash, python, logging, commits
- [When in doubt](#when-in-doubt) — pointers to concept + architecture

## What this repo is

The **tooling** for an LLM Wiki — a Karpathy-pattern personal knowledge base. The repo is not a vault; it's the code that runs inside one.

A vault that uses this tooling has four layers:

1. **`raw/`** — curated sources (LLM reads, never writes). Top-level subfolders: `articles/`, `papers/`, `notes/`, `transcripts/`, `audio/`, `requests/`, `suggestions/`. Scanner output lives in nested per-scanner folders: `raw/notes/email/<account>-<date>.md` (scan-email full sweep) + `raw/notes/email/<account>-delta-<ts>.md` (scan-email incremental piggyback — only mail newer than the per-account watermark in `.wiki/state/email-state.json`), `raw/notes/calendar/<YYYY-MM-DD>.md` (collectors/calendar_collector.py — Google Calendar v3 via OAuth, **multi-tenant** per `personal.accounts.<id>.calendar`, one file per date with frontmatter `event_count`/`meeting_hours`/`focus_hours`/`people`/`event_ids`; recurring-event series collapse to `knowledge/concepts/<slug>.md`; sentinel-delimited managed region preserves operator prose; same-date title-slug match cross-links gmeet+jamie transcripts), `raw/notes/browser/`, `raw/notes/screenshots/screenshots-<slug>.md` (batch reports) + `raw/notes/screenshots/thumb/<file>.png` (384px previews; original PNGs stay in `~/Screenshots/`, never copied; canonical analysis sidecar lives at `~/Screenshots/<file>.md`), `raw/notes/tabs/`, `raw/notes/youtube/<channel>--<title>--<vid>.md` (scan-youtube — video metadata + transcript + comments + optional gemma4 visual analysis, single-file markdown), `raw/transcripts/jamie/<date>--<slug>--<short-id>.md` (collectors/jamie.py — pulls meetings from the Jamie AI tRPC API; summary + speaker-diarised transcript + action-items in one file), `raw/transcripts/gmeet/<date>--<slug>--<meeting-key>.md` (collectors/gmeet.py — exports the Gemini-generated transcript + notes Docs via the Drive API from **two discovery sources** (`folder-scan ∪ email-link-scan`): the own "Meet Recordings" Drive folder, AND `gemini-notes@google.com` emails (`gmeet.email_discovery`, default on) whose `docs.google.com/document/d/<id>` link surfaces colleague-owned / org-shared meetings the folder-scan can't see (`drive.meet.readonly` reads them by Meet-origin, not owner); **one meeting → one file** with paired `## Summary` (Notes-Doc) + `## Transcript` (Transcript-Doc) sections, cross-run merge via stable meeting-key hash of the normalised title), `raw/voice/voice-<date>-<HHMM>-<slug>.md` (collectors/voice.py — folder-watches `personal.voice_inbox` for `.txt`/`.md` dictation transcripts, archives sources under `raw/inbox-mobile/voice/` (M022 two-zone intake); substrate-agnostic on capture, iOS Shortcuts + iCloud Drive is the mobile-primary path; when `features.voice_punctuate=true` (default) the body is pre-processed through Ollama `classify_model` for punctuation + German-noun-case and the original is preserved verbatim under `raw_transcript:` in the frontmatter, fallback-to-raw on any Ollama failure), `raw/captures/capture-<id>.md` (collectors/capture_collector.py — folder-watches `personal.capture_inbox` for `.txt`/`.md`/`.html` quick-captures, computes a content-hash capture-ID `sha256(content.strip())[:12]` (filename-derived, so re-dropping identical content overwrites the same article — idempotent), writes frontmatter `type: capture`/`capture_id`/`captured_at`/`source` with the body verbatim (no punctuation pass), two-zone-archives the source under `raw/inbox-mobile/captures/` (M022 two-zone intake); the content-hash capture-ID is the join-key the M025 correction back-channel keys on), `raw/notes/pictures/pictures-<slug>.md` (collectors/pictures.py — folder-watches `personal.picture_inbox` for `.jpeg`/`.jpg`/`.png`/`.heic`, runs gemma4 vision per file with the photo-shaped `scan_pictures_vision` prompt (scene/objects/action/text_visible/setting), archives sources under `raw/inbox-mobile/pictures/` (M022 two-zone intake) next to a per-image sidecar + writes a 384px thumb to `raw/notes/pictures/thumb/`; batch report carries `type: picture-batch` for dispatch to `compile_pictures.md`), `raw/notes/health/<year>/<date>--<account>.md` (collectors/health.py — daily biometric rollup from the Oura REST API; numeric frontmatter `sleep_hours/sleep_score/readiness_score/hrv_overnight/steps/resting_hr` with `sensitivity: high` and None-valued fields dropped; Phase 1 = Oura only, HealthKit XML drop-folder deferred to Phase 2).
2. **`daily/`** — per-day operational rollup. Two-shape structure since the 2026-05-15 `daily/`-as-rollup arc: (a) `daily/<date>/<source>.md` per-source append-only captures owned by exactly one writer each — `sessions.md` by the session-end hook, `health.md` by `collectors/health.py`, `meetings.md` by `collectors/{gmeet,jamie}.py`, `voice.md` by `collectors/voice.py`, `captures.md` by `collectors/capture_collector.py`, `email.md` by `collectors/email_collector.py` — written via `core.daily_capture` (fcntl-flocked, `KNOWN_SOURCES`-validated). Source-provenance back to the canonical `raw/` file lives in a `sources:` frontmatter list (`daily_capture.append_with_source`), **not** an in-body `[[…]]` wikilink — Obsidian ignores `raw/` (`userIgnoreFilters`), so a body link would render dead. Legacy in-body voice links migrate via `wiki backfill voice-source-frontmatter`; (b) `daily/<date>.md` is the compile-stage digest (≤500 words, distilled across all per-source captures by the `daily-digest` agent / `daily_digest_yesterday` piggyback). The subfolder is Layer-2 immutable capture; the root file is a Layer-3 distillation that lives in `daily/` for operator ergonomics. Lint `check_daily_consistency` flags subfolder-without-digest, root-without-subfolder (legacy pre-rollup state), and unknown source names. Migration of pre-2026-05-15 flat daily files: `scripts/migrate_daily_to_rollup.py`.
3. **`knowledge/`** — LLM-compiled wiki articles (LLM owns, human reads). Subfolders: `concepts/`, `connections/`, `people/`, `projects/`, `qa/`, `facts/` (the last is human-owned via `wiki correct` — hard facts that override anything in raw/daily sources). **Two article shapes coexist**: atomic (one body, used by `concept | connection | qa | moc | fact`) and two-layer State + Timeline (`person | project`, M005) — compiled-truth State block above `---` (with `## State`, `## Action Items` in Obsidian-Tasks-plugin syntax, `## Open Threads`, `## See also`), append-only `## Timeline` below. Compile prompt branches on `type:` (see `prompts/compile_main.md` Instruction 3). Lint (`scripts/lint.py:check_two_layer_pages` + `check_action_item_syntax`) enforces the shape. Tasks extracted from jamie/gmeet substrates land in entity-page Action Items; resolved items demote to Timeline on the next compile pass when substrate evidence appears. **Domain-tag rule:** `concepts/` and `qa/` must carry at least one domain tag from `CONFIG.graph_view.domain_tags` (`check_concept_domain_tag` + `check_qa_schema` lint enforce). Domain tags drive graph-view coloring; notes without one fall into the grey fallback bucket.
4. **`workspace/`** — the operator's working layer (intent-dispatch + a running `todo.md`). The `intents` producer (post-compile, gated `features.extract_intents` + `limits.intent_source_globs`, default off; model `models.intent_classify_model`, a cheap tier) classifies an intake note into an intent `{kind, summary, confidence}` where **kind ∈ task | idea | note | none** (`none` = noise only). Default channels: voice notes (`raw/voice/*`) + the mobile picture channel (`raw/inbox-mobile/pictures/*.md` — camera photos **and** phone screenshots snapped to self; the .md sidecar carries the vision text). Intent attaches to the **ingest channel**, not the file type — desktop screenshots (`raw/notes/screenshots/`) are a different channel and stay out. It routes through the `intents/` handler registry; the `task`/`idea`/`note` handlers write `workspace/inbox/<source-stem>.md` with `type:`/`status: pending` frontmatter (confidence-floor gates `task` only; idea/note are captured liberally). **Operator-facing + Obsidian-visible** — reviewed before anything runs. **Accepting a task is an action, not just a flag:** it MOVES the record out of `inbox/` into `workspace/tasks/<NNN>.md` (numbered: `001.md`, `002.md`, …) and appends a checkbox line `- [ ] <summary> — [[tasks/<NNN>]]` to `workspace/todo.md` (the todo list). Accepting an idea/note files it in place (`status: accepted`, stays in inbox); dismiss sets `status: dismissed`. **Status axes stay separate:** triage = keep/drop; task execution = `accepted → done | blocked`, so `done` always means "task executed", never "triaged". Execution is operator-gated: the `orchestrate-tasks` agent (`prompts/agents/`) reads `workspace/tasks/`, runs each `accepted` task, flips it to `done`/`blocked`, and ticks its checkbox in `todo.md`. Re-dispatch guard in `.wiki/state/intents-seen.json`. Extensible: new outcome kinds = new handler modules under `intents/`; new intake substrates = extend the source-glob list. **Three triage surfaces, one source of truth** (the `status:`/`type:` frontmatter): `wiki triage` (CLI), the dashboard's 📥 Dataview panel, and `triage.html` — a static, server-less browser UI (seeded at vault root; opens the vault via the File System Access API in Chromium) that lists pending records, previews the original photo/voice source, accepts (task → moved to `tasks/` + listed in `todo.md`; idea/note filed), dismisses, and converts note/idea↔task in place. The frontmatter-key contract between `_record.py` and `triage.html` is pinned by `tests/test_triage_record_contract.py`.

The vault holds the **data**. This repo holds the **engine** (compile, flush, lint, query, hooks, prompts).

The **vault's own `AGENTS.md`** (separate file, not this one) is the article schema the compiler embeds into every compile prompt. This file is for contributors working on the codebase.

## Repo layout

```text
llm-wiki/                    ← installed as <vault>/.wiki/ — the file-by-file reference is docs/engine-layout.md
├── wiki                     ← entry-point CLI (bash, ≤ 150 lines, no library: the bootstrap — its own
│                              path, the venv-location rule, the fail-closed vault guard; every command,
│                              bare `wiki` included, goes to scripts/cli.py)
├── scripts/                 ← the engine's source root — NOT a package (§ Python environment)
│   ├── cli.py               ← table-driven `wiki` dispatcher — the CommandSpec table (cli_catalog.py, help texts in cli_help.py) is the single source of truth
│   ├── core/                ← shared plumbing, imported never invoked: paths, config + config_schema, prompts,
│   │                          sdk_helpers (the ONE Claude-SDK harness), ollama_client, frontmatter, markers,
│   │                          state_store, entry (how one engine process spawns another), errors, console,
│   │                          links, usage, piggybacks, health, actions, daily_capture, flush_pipeline …
│   ├── collectors/          ← substrate → raw/ writers (Registry; `wiki collect`), with adapters/ (mailbox,
│   │                          calendar, health clients) and domain/ (pure types) beside them
│   ├── preprocessors/       ← in-vault intake normalizers, pre-compile (inbox, html, clippings; `wiki preprocess`)
│   ├── compile_stages/      ← the compile pipeline's stages (classify → route → memory → compile → post_passes)
│   ├── producers/           ← post-compile derivative extractors (suggestions, curiosity, takes, intents; `wiki produce`)
│   ├── suggestions/ curiosity/ intents/ facts/ ← the producers' bodies + their consumer CLIs
│   ├── dashboard/           ← Obsidian dashboard generators (stats, lint, agent buttons, daily button)
│   ├── reports/_engine/     ← operator-self-reports, air-gapped from compile (`wiki study` / `wiki analyze`)
│   ├── publish/ bridge/     ← `wiki publish` (meinkontext mirror) and `wiki bridge` (rsync inbox bridge)
│   ├── migrations/          ← one-shot schema / data migrations, run as `python -m migrations.<name>`
│   └── *.py                 ← top-level entry scripts (compile, flush, query, lint, doctor, menu, dream, …) — the
│                              only modules that run by file path
├── hooks/                   ← agent hooks, run as plain scripts: _bootstrap.py (the engine's one sys.path bootstrap),
│                              _transcript.py, session-start.py, session-end.py, pre-compact.py
├── prompts/                 ← LLM prompts as .md files (${var} placeholders)
├── templates/               ← seeded into <vault>/ on install (never overwritten)
├── skills/                  ← engine skills, symlinked into <vault>/.claude/skills/
├── desktop/                 ← Electron menubar GUI (npm, not pnpm) — talks to the engine only through --json seams
├── tests/                   ← pytest (pythonpath = scripts + hooks); tests/golden/{oracle,bash}/ = the behaviour oracle
├── docs/                    ← concept, PROCESS, engine-layout (file-by-file), config (generated tables), diagrams
├── config.example.yaml      ← copy → config.yaml on install (gitignored)
├── pyproject.toml + uv.lock
└── install.sh               ← one-liner installer
```

## Conventions

### Adding a tunable

1. Extend the matching dataclass in `scripts/core/config_schema.py` with a
   `#` comment above the field — that comment IS the documentation (the
   docs table's Meaning column is generated from it).
2. Document the default in `config.example.yaml` with a comment. A test
   (`tests/test_config_docs.py`) fails if the example is missing the key or
   carries a non-default value.
3. Regenerate the reference tables: `PYTHONPATH=scripts uv run python -m
   core.config_docs --write` (rewrites the generated region in
   `docs/config.md`; a drift test fails if you skip this).
4. Replace the hardcoded constant in the script with `CONFIG.<section>.<field>`.
5. Don't add ad-hoc constants back to scripts — extend the config layer.
6. **Add the key NAME to `scripts/migrations/migrate_config_keys.py`** —
   either `INJECTED_KEYS[<parent>]` (injected into operator vaults; the value
   is derived from the schema automatically) or `NEVER_INJECTED[<parent>]`
   (explicit dataclass fall-through, e.g. secrets that belong in `.env`).
   `tests/test_migrate_config_keys.py::test_every_schema_knob_has_a_migration_policy`
   fails until one of the two carries the key. Operator vaults already carry
   their own `config.yaml`; without injection the new key is invisible to the
   operator (dataclass defaults silently fire) and any rollout that depends
   on the operator *seeing* the knob is broken. Same rule for renames
   (extend `PIGGYBACK_RENAMES` etc.) and removals (`new_key=None` /
   `KEY_DROPS`). Direct edits to `<vault>/.wiki/config.yaml` are forbidden —
   the migration is the only legal write path into an operator vault.

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

- **Engine-owned (markdown/YAML — `AGENTS.md`, `dashboard.md`, `knowledge.base`):** whole-file (`seed_cli.Seeder.copy`; `core/seed.py:walk` lists every seeded file and how). Seed-if-missing, keep-if-exists, refresh with a targeted `wiki seed <path> --force`. Operators shouldn't hand-edit these; they're regenerated.
- **Customisable JSON configs (`graph.json`, `app.json`, plugin `data.json`):** route through `seed_cli.Seeder.overlay`. The engine owns the template (base); the operator's delta lives in an **untracked** overlay at `<vault>/.wiki/custom/<rel>`; the live file is derived as `template ⊕ overlay` (`core.seed.apply_overlay` / `derive`: an element-wise deep merge). This keeps the file engine-updatable (new keys flow in) while preserving customisations — operators edit the overlay, `--force` re-derives from template ⊕ overlay, `wiki seed --extract-custom <rel>` bootstraps an overlay from existing drift. An overlay only overrides: a key or array entry the operator removed, or a value cleared to `null`, comes back from the template on `--force` (`.ytstack/backlog/overlay-cannot-carry-deletions.md`). NEVER make a customisable config keep-or-`--force` whole-file — that recreates the force-vs-drift dilemma.
- **Accumulating lists (community-plugins, shell-commands, meta-bind buttons):** bespoke additive merges in `core/seed.py` (`union_list`, `merge_registry` by id, `env_appended`), preserving operator entries while adding/updating engine-managed ones.

Drift detection on the JSON configs is key-order-insensitive (the canonical `jq -S` form, `core.jqjson.canonical` in the port), so don't worry about Obsidian re-serialising key order. Copied files (markdown, html, css, yaml) compare byte for byte.

### Changing a `--json` payload (menu / doctor)

1. Change the `TypedDict` in `scripts/core/contracts.py` — the one definition the builders
   (`core/actions.py`, `core/health/`, `menu_context.py`, `doctor.py`) return.
2. Regenerate the schemas: `PYTHONPATH=scripts uv run python -m core.contracts --write`
   (the suite runs `--check` and validates the oracle goldens against them).
3. Bump `core.actions.SCHEMA` (and the `Literal` in `contracts.py`) when a consumer must learn
   the change — the desktop refuses a schema it does not know.

### Adding a prompt

1. Drop `<name>.md` into `prompts/`.
2. Use `${var}` for placeholders (not Python's `{var}` — JSON/YAML examples in prompts have literal braces).
3. Call `from prompts import render` and `prompt = render("name", var=value)`.

**Per-prompt model (Prompty-style frontmatter).** A prompt MAY open with a YAML frontmatter block declaring its model — e.g. `scan_pictures_vision.md` / `scan_screenshots_vision.md` pin `model: qwen2.5vl:7b` (strong local OCR) and `intent_classify.md` pins `model: claude-haiku-4-5` (cheap triage). `render()` strips the frontmatter from the body (it never reaches the LLM); the caller resolves the model with `prompt_model("<name>", <fallback>, …)` — **frontmatter `model:` wins, else the first truthy fallback** (caller default → config knob → `compile_model`). This puts the model choice next to the prompt it belongs to instead of hardcoded at the call site; config knobs (`models.vision_model`, `models.intent_classify_model`) remain the fallback. (Agent-task specs `prompts/agents/*.md` carry their own `model:` via `AgentSpec`, a separate parser.)

### Adding an agent target (for hook install)

1. Add an `Agent` to `AGENTS` in `scripts/core/agents.py`: name, detection dir, config file,
   its hooks (event, script, timeout in the agent's unit) and `flat=True` for Cursor-style
   bare entries. `wiki hooks`, `wiki status` and doctor's `hooks-installed` read it.
2. Record its payloads: `uv run pytest tests/test_agents_registry.py --snapshot-update`
   writes `tests/golden/agents/payload-<name>-*.json`. Read them and commit them with the
   agent; from then on a changed byte in an installed hook command fails a test.
3. Status table, install/uninstall flows, and detection logic pick it up automatically.

### Wikilinks (relative-to-file convention)

A link in a markdown file is relative to that file. Obsidian resolves a slash-bearing wikilink against the **vault root** (`<vault>/`, where `.obsidian/` lives), so the historic `[[concepts/foo]]` form — relative to `knowledge/`, not the article — pointed at the non-existent `<vault>/concepts/foo.md` and Obsidian offered to create an empty stub when clicked from a nested article. Links are now stored **relative to their containing article**: same-bucket `[[foo]]`, cross-bucket `[[../people/alex]]`, substrate `[[../../daily/2026-05-15.md]]`.

`core.links` is the single resolver (`resolve_link`, `canonical_slug`, `relativize_text`). When **authoring** links (prompts, `wiki pin`, hand-edits) use the unambiguous full-path form `[[knowledge/<type>/<slug>]]` or `[[daily/…]]`/`[[raw/…]]` — the `relativize_wikilinks` post-compile pass (gated by `features.relativize_wikilinks`, default on) rewrites every link to the correct relative path. Don't hand-compute `../`. `core.backlinks` renders footers relative; `lint` resolves source-relative. `index.md` is exempt (its links already resolve source-relative from `knowledge/`). One-off corpus migration: `scripts/migrations/relativize_wikilinks.py --vault <vault> --apply`.

### Path handling

Scripts use `Path(__file__).resolve().parent` for `SCRIPTS_DIR`, `.parent.parent` for `WIKI_DIR`, `.parent.parent.parent` for the vault root. After `install.sh` clones the repo into `<vault>/.wiki/`, this resolves correctly. Don't hardcode absolute paths.

**In a development checkout that last step is wrong by construction:** `ROOT_DIR` resolves to the directory *next to* the repo, so `DAILY_DIR`, `RAW_DIR`, `KNOWLEDGE_DIR` and the `_dashboard-*.md` targets point at the operator's filesystem. Consequences for anything you write:

- **Tests must never reach a `ROOT_DIR`-derived constant.** Monkeypatch it at the module that owns it — `core.daily_capture.DAILY_DIR`, not `core.paths.DAILY_DIR`, if that's where the write site reads it. `tests/conftest.py` repoints the known ones and a write guard (`tests/_vault_isolation.py`) raises `VaultWriteEscape` on anything that escapes the checkout, so a forgotten one is a red test rather than a silent leak.
- **Running engine scripts from the repo writes outside it.** `wiki flush`, dashboard regeneration and friends will happily create `<repo>/../_dashboard-*.md`. Exercise write paths against a real vault or a scratch one (`WIKI_VAULT`-style redirection), never from the checkout.

### Python environment

The Python venv lives at `<vault>/.wiki/.venv/` (inside the engine, NOT at the vault root). The first `wiki` call creates it (`install.sh` runs `wiki seed`), and the bootstrap re-syncs it whenever `uv.lock` or `pyproject.toml` is newer than its `.wiki-synced` stamp. **Exception — cloud-synced vaults** (iCloud Drive, `~/Library/CloudStorage`): the environment lives at `~/.venvs/<vault>-wiki`, addressed via `UV_PROJECT_ENVIRONMENT`, which the `wiki` bootstrap exports and the installed hook commands carry literally (rule: the bootstrap `wiki`, held with `wiki doctor`'s copy to one table in `tests/test_engine_env_location.py`; rationale: `docs/engine-layout.md` hard rule). On such a vault, run engine commands through `wiki …`; a bare `uv run --project .wiki` would rebuild an environment inside the cloud folder.

`scripts/` is the engine's source root, not a package (DECISIONS 2026-10-14; no `scripts/__init__.py`, ever — `tests/test_layout.py` guards it). Three ways to invoke engine code, and which one applies depends on where the module sits:

- **Through `wiki`** — `wiki <command>`. The dispatcher spawns the handler as `python -m <module>` with `scripts/` on `PYTHONPATH` (`core/entry.py` builds argv + env for every Python-side spawn). The operator-facing form; every documented command has one.
- **A top-level script by path** — `cd <vault>/.wiki && uv run python scripts/<X>.py <args>`, or from any CWD `uv run --project <vault>/.wiki python <vault>/.wiki/scripts/<X>.py <args>` (the hooks and the bash layer use the latter). Python puts a script's own directory first on `sys.path`, and for `scripts/<X>.py` that directory *is* the source root, so `core.*` imports resolve.
- **A sub-package module as a module** — `PYTHONPATH=<vault>/.wiki/scripts uv run --project <vault>/.wiki python -m <pkg>.<module> <args>` (`migrations.migrate_config_keys`, `core.config`, `collectors.cli`). Running such a file by path (`python scripts/collectors/scan_tabs.py`) fails with `ModuleNotFoundError: core`: the per-module `sys.path` bootstraps that once made it work are gone (M033-S02-T04), and the only bootstrap left is `hooks/_bootstrap.py`, for the hooks, which run as plain scripts from the agent harness. A package whose `__init__` imports its modules to register them (`collectors`, `preprocessors`, `producers`) double-imports such a module under `-m` (a `RuntimeWarning`); those modules get a top-level entry script instead (`process_inbox.py`, `ingest_html.py`, `ingest_youtube.py`, `index_folders.py`, and `scan_screenshots.py` / `scan_browser.py` / `scan_tabs.py` for the three collectors' direct-CLI flags; `tests/test_cli_dispatch.py` refuses a handler that reaches into such a package directly, `tests/test_layout.py` refuses a documented by-path invocation of a sub-package module).

`hooks/session-end.py` and `hooks/pre-compact.py` spawn `flush.py` with `--project` for the same reason. Anything that spawns engine code from outside `.wiki/` MUST pass `--project`, otherwise `uv` can't find `pyproject.toml`; anything that spawns a sub-package module MUST put `scripts/` on `PYTHONPATH` (`core.entry.python_m` + `child_env` from Python, the `PYTHONPATH="$WIKI_DIR/scripts" uv run … python -m` line from bash).

### YAML & JSON

- **YAML editing in CLI** → goes through `config.py set` (Python with PyYAML). Bash never parses YAML.
- **JSON merge for agent configs** → `core.agents.merge` / `without_wiki_hooks` (they keep other tools' hooks); a backup through `core.backup` before every write.
- **LLM JSON output** → use `jsonrepair` or schema-constrained decoding (Ollama `format` field). Never raw `JSON.parse`.

### Side effects

- Hooks run in **<10s** budget — no API calls, only file I/O. Heavy work goes to spawned background processes (`flush.py`, piggybacks).
- `compile.py` and `query.py` use the Claude Agent SDK with `model=CONFIG.models.compile_model`. Other scripts use Ollama (configurable via `models.ollama_url`).

### Exception handling (decision tree)

The engine runs unattended — its dominant failure mode is the **silent skip**. A failure that
produces no log line is invisible by design, so bare `except Exception: pass` and unlogged
fallback-returns are banned. For every new `except Exception`, walk this tree top-down:

1. **Adapter seam** (mailbox / calendar / Drive reader or filter)? → raise a **typed error**
   (`MailboxReadError`, `DriveAPIError`, `CalendarAPIError`) with `from e`. The collector
   boundary catches, logs, and isolates it (`core watermark-on-failure` stays intact).
2. **Claude SDK call**? → route through `core.sdk_helpers` (`run_sdk_query`,
   `classify_failure` + `log_sdk_failure`). Never hand-roll SDK exception handling.
3. **Collector / Producer boundary** (one account, one source)? → `log.exception(...)` +
   return the typed result (`AccountLoopOutcome` error entry, `ProducerResult(status="failed")`,
   `RunResult(success=False)`, `CheckResult(severity="warning")`). One bad item never kills
   the loop, and never disappears either.
4. **Intentional suppression** (best-effort cleanup, observability write, per-item parse
   fallback)? → `with swallow("label")` from `core.errors` — context manager or decorator.
   The label makes the intent greppable and every suppression logs. Level rules:
   - default `level="warning"` — a degraded capability the operator should see (WARNING+
     also lands in the errors-only log archives, per repo convention);
   - `level="debug"` — best-effort cleanup (`agen.aclose()`, IMAP logout) and hot-loop
     per-item fallbacks (one bad date/header among thousands) where WARNING would flood.
5. Never catch `BaseException`; `swallow` re-raises `KeyboardInterrupt`/`SystemExit` unlogged.

If none of 1-4 fits, the exception should propagate — an uncaught traceback in an errors-only
log beats a swallowed one. When a fallback value must be returned inline (e.g. decode → `""`),
explicit `log.debug/log.warning` + `return` is the equivalent of `swallow` and equally legal.

### Evaluating a new intake channel (substrate priority, locked 2026-05-22)

Value a candidate substrate/collector by **persona-coverage, not signal-density per row.** This is a *self*-cartography engine: it optimizes for completeness-of-portrait, not knowledge-yield. Work-substrate (mail/calendar/gmeet/docs) systematically captures the intentional/professional self and misses the non-work persona (curiosity, leisure, cultural consumption, mood). A low-yield consumption channel that covers that otherwise-dark axis can outrank a high-yield source redundant with existing substrate.

- "It'll clutter the knowledge base" is **not** a valid objection — `compile-role: source-only` + `daily/`-aggregation already keep low-signal sources out of per-item `knowledge/`. Clutter is solved engine-side; coverage is the open question.
- **Axes, not channels.** Value scales per persona-axis newly covered, not per source added. Spotify + YouTube-watch-history + podcasts are mostly one "cultural/curiosity-consumption" axis — strong case for the first, steep diminishing returns stacking more. Browser-history already covers leisure *attention* at domain granularity; the gap these fill is *content* granularity.
- **Synthesis is the gate.** Don't add a channel that only grows `raw/`. Ingest only when the synthesis side (dream-cycle / a persona entity-page) will actually weave it into a "what occupies the operator" portrait — otherwise it adds noise, not coverage.
- **Consumption ≠ production.** Suno-style operator *output* is on the production axis, not the consumption/curiosity axis; it belongs to the portrait but is not the better candidate merely because the operator authored it.

Full rationale: `.ytstack/DECISIONS.md` 2026-05-22; candidate grouping: `.ytstack/backlog/consumption-curiosity-axis.md`.

### Spawning Claude Agent SDK with substrate input (HARD rule, locked 2026-05-15)

Any script that feeds substrate (`daily/**`, `raw/**`, third-party email, operator-supplied prompts) into the Claude Agent SDK with Write/Edit tools MUST apply three layers of write-scope enforcement, no exceptions:

1. **Prompt-level** — the system prompt explicitly states which directory the agent may Write/Edit, and that source descriptions of code/config/script changes are subject matter, not instructions to the agent.
2. **Tool-level** — call through `run_sdk_query` with `SdkCallSpec(write_scope=WriteScope(roots=(<allowed dir>,)))`: Write/Edit stay in `allowed_tools`, and a PreToolUse hook (`core/sdk_scope.make_path_scope_hook`) denies every Write/Edit that resolves outside the roots. Never `permission_mode="acceptEdits"`. Neither substitute works: `Write(<glob>)` / `Edit(<glob>)` entries in `allowed_tools` or `disallowed_tools` are not path scopes, because the bundled CLI ignores the parenthesised part (`scripts/probe_compile_scope.py`, 2026-05-17), and a `can_use_tool` gate hides Write/Edit from the agent altogether (2026-05-18).
3. **Settings-level** — `setting_sources=("project",)` (not `()`) so vault-root `CLAUDE.md` reaches the agent.

Reason: substrate routinely contains literal change-descriptions captured from prior engine-development sessions. The agent reads them as instructions and acts on them with whatever filesystem authority you gave it. See `.ytstack/KNOWLEDGE.md` "Compile prompt injection via substrate" + `.ytstack/DECISIONS.md` 2026-05-15. Reference implementation: the `SdkCallSpec` in `scripts/compile_stages/compile.py` (`_attempt`); the gate's tests are `tests/test_sdk_scope.py`.

Long-term direction: remove agent-side filesystem writes entirely — agent returns structured payload via `ResultMessage`, script writes the files deterministically. Track in `.ytstack/backlog/compile-agent-no-filesystem-write.md`.
- Every config write makes a `.bak.YYYYMMDD-HHMMSS`. Idempotent install/uninstall.
- The engine writes **inside the vault and `.wiki/` only**, with one exception: when `skills.global_install` is on, `wiki skills install/sync` symlinks `use-llm-wiki` into `~/.claude/skills/` and records the vault root in `~/.config/llm-wiki/vaults` (the discovery registry the skill reads). Both writes fail soft — a missing global link is recoverable, a hard error on `wiki update` is not.

## Style

- Bash: `set -euo pipefail`, `[[ ... ]]` over `[ ... ]`, lowercase function names.
- Python: type hints, dataclasses for config, `Path` not str. Formatted and linted by ruff
  (`uv sync --group lint` once, then `uv run --group lint ruff check scripts hooks tests` and
  `uv run --group lint ruff format --check scripts hooks tests`); the rule set and every
  ignore's reason live in `pyproject.toml`. `scripts/core/config_schema.py` is excluded from
  the formatter on purpose — its field comments are the source of `docs/config.md`.
  Type-checked by ty on `scripts/core/` (`uv run --group typecheck ty check scripts/core`,
  pinned exactly — DECISIONS 2026-10-15); the rest of `scripts/` is reported in CI, not gated.
  A suppression names ty's own rule (`# ty: ignore[rule]`) with the reason beside it — a
  foreign-coded `type: ignore` hides errors from one checker and not another. The
  same gates run in pre-commit (`pre-commit install` once per clone) and in CI
  (`.github/workflows/ci.yml`, with `pytest` and the desktop suite). The mechanical format
  commit is listed in `.git-blame-ignore-revs`; run once per clone:
  `git config blame.ignoreRevsFile .git-blame-ignore-revs`.
- Size gates (both in the suite): a function stays under 150 lines
  (`tests/test_function_length.py`, its allowlist is empty), a module under `scripts/` at or
  under 1,000 lines unless `docs/engine-layout.md` § "Large modules" lists it with the reason
  it stays one module (`tests/test_module_size.py`). Both lists only shrink — split the code,
  don't extend the list.
- No emoji in code. Logs use ASCII status markers (✓ ! ✗) only via the helpers in `core/console` (`ok` / `warn` / `info` / `fail` / `print_error`); the bootstrap `wiki` has only its `die`.
- A command module (any handler the catalogue dispatches) writes its output through `core/console`: `say` for plain lines (print's contract), the helpers above for status. It never calls `print(` itself; `tests/test_output_seam.py` refuses one outside its allowlist, which names a reason per entry.
- Commit messages: imperative mood, short subject (≤70 chars), body explains why.

## When in doubt

- Read `docs/concept.md` for the design rationale.
- Read `docs/architecture.excalidraw` (open in Obsidian / excalidraw.com) for the data flow.
- Read `docs/FEATURES.md` for the implementation map (status, code location, known gaps per feature). Update it whenever you add / move / retire a feature.
- Check `.ytstack/backlog/` for unvalidated future-milestone pitches; `.ytstack/STATE.md` for current milestone status.
