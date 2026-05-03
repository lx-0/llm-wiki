# Decisions

Append-only architectural and product decisions for llm-wiki. Never rewrite past entries. If a decision is reversed, add a new entry that supersedes.

Format for each entry:

## YYYY-MM-DD: <Short title>

**Context:** <what forced the decision>
**Options considered:** <A, B, C>
**Chose:** <selected option>
**Reason:** <why>
**Supersedes:** <link to earlier entry if this reverses a prior decision>

---

## 2026-05-02: Adopt ytstack as project memory; migrate existing docs

**Context:** llm-wiki has been iterating for several weeks with ad-hoc project memory split between `docs/` (engine documentation, design decisions, plans) and Claude project-memory files (project_*.md, feedback_*.md). The follow-up backlog and roadmap were unstructured. Long-term iterative development needs a durable STATE / slice-task structure.
**Options considered:** (A) keep ad-hoc, defer ytstack until a `docs/plans/*` milestone; (B) adopt ytstack now, scaffold `.ytstack/` alongside existing docs with pointer-based duplication; (C) adopt ytstack now and consolidate — migrate `docs/design-decisions.md`, `docs/plans/`, and Claude project-memory artifacts into `.ytstack/` shape.
**Chose:** C.
**Reason:** Pointer-duplication accumulates drift; a single source of truth per artifact type is cleaner. The project is long-horizon (months of iteration ahead) and ytstack's STATE / slice-task discipline is exactly what an unstructured follow-up backlog lacks.
**Supersedes:** —
**Linked artifacts:** `OFFICE-HOURS-self-cartography-engine.md`; upstream ytstack PR #15 (M010 brownfield-detect-analyze-migrate).

## 2026-05-02: Skip plan-ceo-review (concept mode) for initial scaffolding

**Context:** ytstack greenfield flow recommends `office-hours` → `plan-ceo-review` (concept) → `init-project`. For llm-wiki the project is brownfield-retro: validated by months of artifacts, solo-funded by curiosity, no external customer waiting for a wedge.
**Options considered:** (A) run plan-ceo-review concept-mode anyway for discipline; (B) skip and let reality be the critic.
**Chose:** B.
**Reason:** The `Risks` section of the pitch already names the wedge-discipline question explicitly (single-wedge focus rejected); a CEO-style review would land on the same point. Marginal value of formal stress-test is low when the operator is also the user. Reality (M001 outcomes) is the better critic.
**Supersedes:** —

## 2026-05-02: Project-level .ytstack/ (committed), not user-level

**Context:** init-project asks where `.ytstack/` lives. llm-wiki's pitch positions it as potentially public; the engine repo already commits `docs/` engine documentation.
**Options considered:** (A) project-level (.ytstack/ in repo, committed); (B) user-level (~/.ytstack/projects/llm-wiki/, machine-local, private); (C) both.
**Chose:** A.
**Reason:** Engine repo already commits engine-tier documentation. Survives repo clone, visible to other agents and contributors, no machine-loss risk. User-level only correct for secret side-projects, which this is not.
**Supersedes:** —

## 2026-05-02: Naming vocabulary — "LLM Wiki" (pattern) / "wiki" (code) / user-branded (vault)

**Context:** Karpathy's gist used both "LLM Knowledge Bases" and `llm-wiki`. Of the top 10 GitHub implementations within four weeks of his post, nine use "LLM Wiki" in repo name or description. We needed a single locked vocabulary so engine code, prompts, and public docs stop drifting between "Brain", "Knowledge Base", "Memory Compiler", etc.
**Options considered:** (A) "LLM Wiki" (Karpathy + community standard); (B) "Knowledge Compiler" / "Memory Compiler" (describes engine, not artefact); (C) "Brain" / "Exobrain" / "Second Brain" (Forte's broader PKM concept, semantically wider than what we do).
**Chose:** A.
**Reason:** Community gravity — nine of the top ten implementations use it within the first four weeks; matches the gist's filename and avoids overlap with RAG/vector-DB usage of "Knowledge Base". Three layers locked: pattern descriptor "LLM Wiki", code/paths/vars `wiki` / `.wiki/` / `WIKI_DIR` / `WikiConfig`, user-branding free choice (the tooling does not impose a name on the user's vault).
**Supersedes:** —
**Linked artifacts:** `docs/naming.md` carries the full vocabulary table and the explicit non-names ("Brain", "Knowledge Compiler", "Knowledge Base").

## 2026-05-02: Engine `.venv/` location is `.wiki/.venv/` only — never vault root

**Context:** `install.sh` originally allowed `uv sync` from any CWD; an early version of the docs implied the venv could live wherever convenient. KNOWLEDGE.md captures a 2026-05-02 incident where an agent placed `.venv/` at the vault root, breaking `wiki update` and leaking engine internals into the data layer.
**Options considered:** (A) vault-root `.venv/` (matches naive `uv` defaults, simpler to remember); (B) `.wiki/.venv/` only (engine self-contained, vault root stays clean); (C) configurable.
**Chose:** B.
**Reason:** Vault-Engine split is the load-bearing architectural invariant — `.venv/` is engine state, not vault data. Configurable would re-open the same drift. `install.sh` enforces by always passing `--project <DEST>` where DEST = `<vault>/.wiki/`.
**Supersedes:** —
**Linked artifacts:** `docs/engine-layout.md` (Hard rule); `KNOWLEDGE.md` 2026-05-02 entry.

---

## 2026-05-02: Three-layer vault UX — Dashboard.md / index.md / MOCs/

**Context:** `knowledge/index.md` is agent-facing (compile-target for LLM consumption). `templates/dashboard.md` was thin (4 dataview tables). Vault was machine-readable but human-thin. lx vault (`Documents/lx/`) showed a richer pattern (PARA, QuickAdd, Pending Review queues).
**Options considered:** (A) thicken `knowledge/index.md` for both audiences; (B) replace `index.md` with a richer human view; (C) three-layer split — `knowledge/index.md` stays agent-only, `dashboard.md` becomes rich Homepage, `knowledge/MOCs/` for human-curated topic hubs.
**Chose:** C.
**Reason:** Audience separation. Compiler writes index.md flat; user reads dashboard + MOCs. Plugin stack (Homepage, Dataview, Charts, Meta Bind, QuickAdd, Tasks, Heatmap Calendar, Shell commands) anchors at dashboard.md. MOCs land in S04.
**Linked artifacts:** `backlog/vault-dashboard.md`, `M003-CONTEXT.md`, `templates/dashboard.md`, `docs/PROCESS.md` §12.

## 2026-05-02: knowledge/ articles MUST carry `type:` frontmatter

**Context:** Pre-fix compiler wrote frontmatter without `type:`. Substrate-type was implied by folder (`concepts/` → concept etc) but never written. Dataview / lint / dashboard charts had to parse folder strings. AGENTS.example.md only documented `type:` for `raw/`, leaving `knowledge/` schema implicit.
**Options considered:** (A) keep folder-as-type, document the convention; (B) require explicit `type:` field, lint enforces, migrate legacy.
**Chose:** B.
**Reason:** Single source of truth. Folder + `type:` agreement is now invariant; lint flags drift. Dataview + chart queries read one field. MOCs (S04) and facts (user-led) extend the type vocabulary cleanly. Migration cost is one cheap script (no LLM).
**Linked artifacts:** `prompts/compile_main.md`, `templates/AGENTS.example.md`, `scripts/lint.py:FOLDER_TO_TYPE`, `scripts/migrate_add_type.py`.

## 2026-05-02: Hard-facts subsystem — `wiki correct` overrides LLM compilation

**Context:** Compiled wiki articles are LLM output and can hallucinate or repeat false claims from sources. Operator needs a way to assert "this is wrong, the truth is X" without manually editing every article.
**Options considered:** (A) edit articles by hand and trust they don't get re-compiled out; (B) prompt-engineer the compiler to be more cautious; (C) dedicated `knowledge/facts/<slug>.md` with `type: fact` frontmatter, injected as authoritative block at top of compile prompt — facts beat any contradicting claim.
**Chose:** C.
**Reason:** Layer separation — facts are operator-authored, articles are LLM-authored. Compile prompt's "Hard facts" section makes the override explicit. `wiki correct` CLI (`scripts/correct.py`) keeps facts edit-friendly. Negation / disambiguation / clarification statuses cover the common cases.
**Linked artifacts:** `scripts/correct.py`, `prompts/compile_main.md` (Hard facts section), `lint.py:FOLDER_TO_TYPE` (`facts → fact`), `wiki correct` subcommand.

**Addendum (2026-05-02 PM):** Hard-facts gained an agentic propagator — `wiki correct apply <slug>` (`scripts/correct_apply.py` + `prompts/correct_apply.md`). Spawns Claude Agent SDK with `cwd=<vault-root>`, `permission_mode=acceptEdits`, full Read/Write/Edit/Glob/Grep/Bash. Walks `knowledge/` (edits + renames + wikilink fixes), prepends correction notes to `daily/`, leaves `raw/` immutable per substrate-layer convention. Adds `applied: false | <iso-ts>` to fact frontmatter for tracking. Lint gained `check_facts_violations()` grepping `negation_terms` across non-facts knowledge files (structural, $0 cost) — cheap detection backstop independent of the Apply step. Query prompts gained the same `${facts_md}` block. Backlog entry: `.ytstack/backlog/wiki-correct-deferred.md` (LLM paraphrase detection, severity levels, auto-apply on add, raw/ contamination strategy).

## 2026-05-02: Wiki CLI surface expansion — engine ops, not just lifecycle

**Context:** Pre-S01 `wiki` CLI covered setup / config / hooks / skills / update / collect / gmail-auth / version. Core engine operations (compile, flush, lint, query, review-wiki) required `uv run --project .wiki python .wiki/scripts/X.py`. Barrier for operators; broke "manual compile button" UX where Meta Bind / Shell commands need a stable invocation target.
**Options considered:** (A) status quo, document the Python invocations; (B) wrap each script as a thin `wiki <name>` subcommand; (C) fold scripts into the wiki bash entry-point as functions.
**Chose:** B.
**Reason:** Thin wrappers preserve the script-as-truth pattern (scripts are testable Python; wiki is bash dispatch). `_run_script` + `_refresh_dashboard_stats` helpers dedupe the wrapper boilerplate. Compile / flush / lint auto-refresh dashboard stats post-run as the operator-visible side effect.
**Linked artifacts:** `wiki` CLI, `scripts/correct.py`, M003-S01-T08.

## 2026-05-02: Meta Bind > deprecated Buttons plugin (research-driven)

**Context:** lx vault uses `Buttons` plugin for dashboard. Initial plan was to copy that. Research (2026 plugin landscape: dsebastien.net, obsidianstats.com) showed `Buttons` is deprecated; `Meta Bind` is the modern stack — buttons + inline input fields + live frontmatter bindings + view-fields, single plugin.
**Options considered:** (A) Buttons plugin (matches lx exactly); (B) Meta Bind (newer, broader); (C) Dataloom / Datacore (WIP, not stable).
**Chose:** B.
**Reason:** Future-proofs: Meta Bind handles button + input + view in one plugin; supports live frontmatter editing for later slices (e.g. inline status toggle on Pending Review entries). Datacore deferred to M004+ when stable.
**Linked artifacts:** `templates/.obsidian/community-plugins.json`, `templates/dashboard.md`.

## 2026-05-02: `wiki seed` for in-place template re-application

**Context:** `install.sh` template-seeding only ran on fresh installs (`! -f` guards). `wiki update` only did `git pull`. After every engine template change (new dashboard, plugins added), installed vaults stayed stuck — operators had to manually copy files.
**Options considered:** (A) document manual `cp` steps; (B) make install.sh idempotent (overwrite-with-merge); (C) extract template-seeding into `lib/seed.sh`, expose as `wiki seed` (additive default, `--force` overwrite, jq-merge for community-plugins.json).
**Chose:** C.
**Reason:** Operator chooses semantics per-run. Additive default is safe (never overwrites existing files); `--force` for explicit overwrite of dashboard / templates. `community-plugins.json` always merges (additive union via jq) — engine adds plugins without dropping operator's own additions.
**Linked artifacts:** `lib/seed.sh`, `wiki seed` subcommand, `install.sh` (refactored to source seed.sh).

## 2026-05-02: Layout via `cssclasses` frontmatter, not inline `<div>` (for Meta Bind)

**Context:** First dashboard rebuild wrapped Meta Bind buttons in `<div class="wiki-button-row">` to get a horizontal flex row. Buttons rendered as plain code text instead of clickable buttons.
**Options considered:** (A) keep `<div>` and force re-process; (B) `cssclasses` frontmatter + scoped CSS (`.wiki-dashboard .block-language-meta-bind-button { display: inline-block }`); (C) drop the layout, accept stacked buttons.
**Chose:** B.
**Reason:** Obsidian (CommonMark) treats fenced code blocks inside raw-HTML blocks as raw-HTML context. Meta Bind's markdown post-processor only runs in markdown context → buttons fall through as plain code. `cssclasses` keeps everything in markdown context. Dataviewjs is unaffected (different post-processor pathway), so chart-grid `<div class="wiki-chart-grid">` still works.
**Linked artifacts:** `templates/dashboard.md` (frontmatter), `templates/.obsidian/snippets/wiki-dashboard.css`.

## 2026-05-02: Agent-task framework — prompt-as-config + auto-wiring (M004)

**Context:** Engine has three SDK-spawning scripts (`compile.py`, `query.py`, `correct_apply.py`) each with hard-coded prompts and CLI shapes. Need to grow the catalogue (`summarize-day`, `review-mocs`, `weekly-digest`, …) without per-task Python files.
**Options considered:** (A) one Python script per task, (B) generic runner with prompt-as-config (`prompts/agent_<id>.md` declares model + tools + permission + button), (C) build into a heavier "agent definition" YAML separate from prompts/.
**Chose:** B.
**Reason:** Single editing surface per task — operator drops a markdown file with frontmatter + body. Reuses the existing `prompts/` directory pattern. No engine code change to add a task. Auto-wiring via `wiki seed` (jq additive merge for shell-commands, marker-based region rewrite for dashboard.md) keeps button registration data-driven too.
**Linked artifacts:** `scripts/agent_spec.py`, `scripts/agent_task.py`, `scripts/agent_buttons.py`, `prompts/agent_summarize-day.md`, `lib/seed.sh:_merge_agent_shell_commands`, `lib/seed.sh:_rewrite_dashboard_agent_buttons`, `wiki agent` subcommand.

## 2026-05-02: Marker-based region replace as the "rewriteable section" pattern

**Context:** M004 needed to inject auto-generated content into `templates/dashboard.md` (button rows + hidden defs) while preserving operator edits elsewhere in the file. `_seed_file` is all-or-nothing; jq merge is JSON-only.
**Options considered:** (A) full file overwrite (loses operator customisation), (B) generate dashboard.md entirely (operator can never customise), (C) marker-based region replace — `<!-- name:begin -->` + `<!-- name:end -->` defines a managed region; everything else is operator-owned and untouched.
**Chose:** C.
**Reason:** Lets the operator customise everything outside markers (re-order sections, change copy, add custom buttons, tweak callouts). Marker pairs are explicit — operator removing them opts out cleanly. Idempotent re-runs. Works for any markdown file, generalises beyond dashboard.
**Linked artifacts:** `scripts/agent_buttons.py:update_dashboard()`, `lib/seed.sh:_rewrite_dashboard_agent_buttons()`, `templates/dashboard.md` (markers in Run section + at end-of-file).

## 2026-05-03: Cache files (`_dashboard-*.md`) are producer-only — never seeded (M003-S07-T01)

**Context:** `_dashboard-stats.md` was bytegenau identical to its template after `wiki seed --force`. Live counts (303 pending, 470 articles, $7.25 cost) silently regressed to all-zero placeholder text on every seed run.
**Options considered:** (A) keep seeding, add a content-check guard (skip if not placeholder), (B) remove cache files from `seed_vault_templates` entirely — they're producer-only outputs, (C) add a cache-only `--force` flag.
**Chose:** B.
**Reason:** Cache files have a single owner (the producer script: `dashboard_stats.py` / `dashboard_lint.py`). Seeding them at all is a category error — they're the *output* layer, not the *template* layer. First boot: cache file doesn't exist, Dashboard embed renders empty until first flush — acceptable. `wiki seed` end now triggers both producer scripts so a fresh-install vault has populated caches without needing a flush first (S04-T03 / M003-S04 wiring).
**Linked artifacts:** `lib/seed.sh:189` (cache-files-not-seeded comment), `wiki:487-488` (`cmd_seed` end calls both producers), `tests/test_seed_preserves_caches.py` (regression test asserts md5 unchanged after `seed --force`).

## 2026-05-03: Refresh helpers must surface failures (M003-S07-T02 + T03)

**Context:** `flush.py:refresh_dashboard_stats()` and `wiki:_refresh_dashboard_stats()` both routed stderr to `/dev/null` and ignored exit codes. Crashed scripts (ImportError, broken `state.json`, etc.) left the cache stale with zero observable signal — exactly how the lxw bug compounded.
**Options considered:** (A) keep silent (best-effort), (B) capture stderr + log warning on non-zero exit, retain `check=False` so flush still completes, (C) propagate failures (block flush).
**Chose:** B.
**Reason:** Cache refresh is best-effort observability — must not block flush. But silent failure is worse than no refresh: operator never learns about broken state until they notice stale numbers. Capturing stderr + logging WARNING (engine-side via `log.warning`, shell-side via `warn`) gives the signal without coupling lifecycles.
**Linked artifacts:** `scripts/flush.py:refresh_dashboard_stats` + `refresh_dashboard_lint`, `wiki:_refresh_dashboard_stats` + `_refresh_dashboard_lint`.
