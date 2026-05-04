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

## 2026-05-03: YouTube intake — single markdown sidecar, local-first vision, hardcoded-cost guardrails

**Context:** YouTube videos are a primary learning surface for the operator (German tutorials, AI talks, code walkthroughs). Need an intake that handles single videos, playlists, and an inbox-list, with multiple detail tiers (metadata → transcript → comments → visual analysis). Cloud video models (Gemini 2.5) are 7-28¢/10min in reality (verified against `clawrag/transformers/video_gemini.py:51-52`), not the 2¢ marketing-headline number.
**Options considered:** (A) Cloud-first via Gemini 2.5; (B) Local-first via gemma4 frame sampling on kcma-d8 GPU host; (C) JSON+MD dual-sidecar like the original backlog sketched; (D) Markdown-only single source of truth.
**Chose:** Local-first (B) for Tier 3, with cloud as opt-in fallback only via `--allow-cloud` (no silent escalation when Ollama is down). Single markdown sidecar (D), no parallel JSON.
**Reason:**
- Local: kcma-d8 is sunk cost, has gemma4:e4b already pulled for screenshots-intake. Speed irrelevant per operator (kcma 100% online), $0 vs Gemini's 7¢/10min Flash-Lite or 28¢/10min for 3.1-pro.
- Cloud guardrails (lifted from clawrag's pain-driven design): hardcoded `DEFAULT_MODEL = gemini-2.5-flash-lite`, per-URL blob cache (deferred — write when first cloud-run lands), pre-run cost-estimate + confirm-gate, `--allow-cloud` explicit, per-run budget cap, admin-permission gate on REST/plugin endpoints. Documented in `.ytstack/backlog/youtube-intake.md`.
- Single MD: compile.py only reads `.md`. Per-video JSON was 4× the storage of the MD for zero current consumer. Timestamps preserved as `[mm:ss]` text anchors. Audit-when-needed pattern: per-run log, not per-video duplicate state.
**Implemented (commits `aafe2a8` `9ca7c43` `825ea94` `5bb0c0e`):** `scripts/scan-youtube.py` Tier 0/1/2/3-local, `wiki ingest-youtube` CLI, playlist URL normalization, inbox parser, transcript fallback chain (`youtube-transcript-api` → `yt-dlp .json3` → none), frame-sampling strategies (chapter-aligned / fixed-interval), CONFIG-driven tunables, end-to-end verified on a 20min Morpheus video (no transcript) producing 11/20 informative frames + 6 key concepts + 11 visual artifacts + 2 code snippets in ~14min @ $0.
**Deferred to backlog:** Tier 3-cloud (Gemini Flash-Lite with guardrails), Tier 4 chapter-deep-dive, per-URL blob cache, curiosity-loop integration (`youtube-intake.md` + `curiosity-dashboard.md`), `raw/inbox/youtube.md` drop-zone + piggyback hook.
**Supersedes:** —

## 2026-05-03: Lift hardcoded constants into CONFIG when adding tunables

**Context:** First scan-youtube cut shipped with `LOCAL_VISION_MODEL`, `MAX_FRAMES_PER_VIDEO`, `MAX_DURATION_FOR_T3_S`, `FRAME_RESIZE_WIDTH`, hardcoded timeouts as module constants. Operator pushed back: "bitte nicht hardcoden, sowas muss configurable sein. halte dich an die framework standards".
**Options considered:** (A) keep hardcoded for "first cut" simplicity; (B) lift to CONFIG only when a second consumer needs different values; (C) lift to CONFIG immediately per AGENTS.md "Adding a tunable" convention.
**Chose:** C. Always.
**Reason:** AGENTS.md documents the convention explicitly: "Don't add ad-hoc constants back to scripts — extend the config layer." Every prior scanner follows it. New scanners must too — even on first cut. Defaults preserve behavior, and one-line `wiki config set models.vision_model qwen2.5vl:7b` becomes the upgrade path instead of a code edit. Reused `models.vision_model` for both per-frame vision and aggregate text-mode (gemma4 / qwen2.5-vl handle both) — no separate model field needed.
**Supersedes:** —

## 2026-05-03: Hard facts carry trust tier + sources (sources REQUIRED at creation)

**Context:** The hard-facts subsystem (PROCESS.md §13) had no provenance. A throwaway user assertion and an externally-verified contradiction were treated as equivalent authority by the compile/query prompts. Long-term that erodes trust in the override layer itself: which fact is gospel, which is a 3am brain-dump? No way to tell.
**Options considered:** (A) keep flat — facts are facts, all equal; (B) continuous trust score `0.0–1.0` with optional `sources:` list; (C) three discrete tiers `confirmed | asserted | provisional` with REQUIRED `sources:` list (≥1, repeatable); user is a valid source via `user:<context>` sentinel.
**Chose:** C.
**Reason:** Float scores invite false precision (0.7 vs 0.75 — who decides?) and drift across operators. Three tiers are auditable, fit on a single help line, and map to natural operator intuition (artifact / I-said / hörensagen). Required `sources:` shifts cost-of-creation slightly upward, which is the point: a fact without provenance is the failure mode the layer was built to fix. User-as-source via `user:<date>` sentinel keeps quick captures viable without lying about evidence.
**How it works at compile/query time:** `read_hard_facts()` in `scripts/utils.py` sorts injected facts by tier (`confirmed` > `asserted` > `provisional`) then `updated` DESC; renders each with `[trust: X]` header + `> Sources: ...` line. `prompts/compile_main.md` + `prompts/query_main.md` carry one paragraph on conflict resolution (higher tier wins; tie → newer; all three tiers still override raw sources).
**Migration:** No write-migration. `read_hard_facts()` defaults legacy facts to `asserted` + `user:legacy-pre-trust-schema`, which is semantically correct for the two pre-existing entries (both user-typed). Backfill via `wiki correct edit <slug>`.
**Linked artifacts:** `scripts/correct.py:cmd_add` (CLI flags + validation), `scripts/utils.py:read_hard_facts` (sort + render + legacy-default), `prompts/compile_main.md`, `prompts/query_main.md`, `templates/AGENTS.example.md`, `docs/PROCESS.md` §13, `docs/architecture.excalidraw` (CLI + YAML + description), `tests/test_correct.py` (9 cases), commit `4ec926e`.

## 2026-05-04: Centralize SDK failure diagnostics in `sdk_helpers.py`

**Context:** Audit of `lxw/.wiki/logs/compile-errors.log` + `flush-errors.log` (2026-05-03/04) surfaced ~190 records all reading "Command failed with exit code 1 — Check stderr output for details". Every site called `claude_agent_sdk.query(...)` without `stderr=callback`, so the bundled CLI's stderr went to `/dev/null` and the actual cause (auth, network, rate-limit, model name, hard crash) was invisible. `compile.py:main()` compounded this with a heuristic that labelled any 3 consecutive failures "rate-limited (5 h Opus window)" — observed firing on 1.9 s / 2.7 s / 3.3 s fast-fails that were clearly bundled-CLI crashes, not 429s.
**Options considered:** (A) drop a stderr callback into each call site individually — works but every site reinvents classification, format, and ring-buffering; (B) wrap `query()` in a project-internal helper that hides the SDK — couples us to one shape, painful when the SDK adds parameters; (C) ship a small shared module (`sdk_helpers.py`) with `StderrCapture`, `classify_failure`, `log_sdk_failure`, `is_fatal` and wire it explicitly into every call site without hiding `ClaudeAgentOptions`.
**Chose:** C.
**Reason:** Each call site keeps full control of its `ClaudeAgentOptions` (every script has different `allowed_tools`, `max_turns`, `permission_mode`, `system_prompt`) — the helper just attaches `stderr=capture.callback` and provides one ERROR-level diagnostic dump on failure. Classification is one place: pattern-match stderr + exception text first (most reliable: `429`, `401/403`, `invalid model`, `ECONNRESET`, `out of memory`), fall back to duration heuristics (<5 s + empty stderr → `cli_crash`). Loop logic in `compile.py` reads the `FailureClass.kind` to decide between fail-fast (auth/model — config is broken, no point retrying) and continue-but-tally (rate_limit / cli_crash / network — transient or operator-fixable).
**Linked artifacts:** `scripts/sdk_helpers.py` (new), `scripts/compile.py:209-247` + `:528-595` (call site + classified abort), `scripts/flush.py:191-232` (extract_from_context + retries with classification carry-over), `scripts/{correct_apply,agent_task,lint,optimize-claude-md,query}.py` (light-touch wiring), commit `25bcab8`.
**Supersedes:** earlier KNOWLEDGE.md note "Rate limits manifest as fast failures" (corrected — fast failures are CLI crashes; real rate-limits surface via stderr keyword).

## 2026-05-04: Dashboard refresh under non-blocking fcntl lock + 120 s timeout

**Context:** `flush-errors.log` 2026-05-03 showed 103 `subprocess.TimeoutExpired` records clustered in ~30 seconds after the `compile_after_hour=18` trigger. Manual runs of `dashboard_stats.py` / `dashboard_lint.py` took 5–15 s; under the post-compile rush they all blew the 30 s deadline together. Multiple SessionEnd hooks were firing within seconds across an iCloud-synced vault, each spawning its own pair of refreshers; the resulting metadata-read storm stalled all racers.
**Options considered:** (A) bump timeout only (30 → 120 s) — masks the storm but every concurrent run still wastes work; (B) move refresh out-of-band as a fire-and-forget background job — complicates lifecycle, hooks already detach; (C) non-blocking fcntl lock on `state/dashboard-refresh.lock` + bumped timeout: first flush wins, others skip silently because the refresh is idempotent.
**Chose:** C.
**Reason:** The dashboard regen has zero accumulated state — every run derives `_dashboard-{stats,lint}.md` from scratch. Skipping a contended refresh costs nothing because the next flush (microseconds later) picks up identical or strictly-newer state. The 120 s timeout is the safety net for the rare case where the lock owner is genuinely slow on iCloud-stalled stat calls; the lock prevents the storm in the first place. Same idiom should be applied to any future best-effort idempotent regen.
**Linked artifacts:** `scripts/flush.py:_dashboard_refresh_lock` + `_run_dashboard_script`, `state/dashboard-refresh.lock` (created on first run), `DASHBOARD_REFRESH_TIMEOUT_S = 120` constant, commit `25bcab8`.
**Supersedes:** —

## 2026-05-04: Compile cloud, curiosity local — no silent fallback in either direction

**Context:** Operator saw `Curiosity: Ollama timeout` followed by `Using bundled Claude Code CLI` in `compile.log` (lxw run, 2026-05-03 ~16:10) and read it as a curiosity → cloud fallback, violating the local-first / private-by-default expectation. Verification of `scripts/compile.py:441-446` confirmed there is no fallback — the post-timeout `Claude Code CLI` line is the *next file's* compile step (the loop iterates regardless of curiosity outcome). But the architecture itself is split-mode and was never explicitly written down: `compile_file()` always uses Claude Agent SDK (cloud, `models.compile_model = claude-opus-4-7`), `maybe_generate_curiosity_requests()` always uses Ollama (`models.curiosity_model = gemma4:e4b`). When one fails, neither leaks to the other.
**Options considered:** (A) make compile local-first too (gemma4 / qwen2.5:7b for `compile_main`, cloud only via `--allow-cloud`) — quality drop, large change; (B) keep cloud-compile as default but add silent fallback in either direction — explicitly rejected, contradicts privacy contract; (C) keep status quo, document the split + the no-fallback rule explicitly.
**Chose:** C.
**Reason:** Compile produces durable knowledge articles; quality matters more than $0 here, and Opus's tool-use loop (Read/Write/Edit/Glob/Grep) is what makes the compile pass converge. Curiosity emits short JSON gap-lists that gemma4 handles fine — perfect local-tier fit. The split is intentional, not accidental, and the contract is: **each pass uses exactly one provider, with no escalation when that provider fails.** A curiosity timeout drops the gap-list for that file (it's already a best-effort signal); a compile failure is logged and the loop advances. Operator can flip individual passes via `wiki config set models.compile_model gemma4:e4b` (would need a small SDK adapter) or `models.curiosity_model claude-haiku-4-5-20251001` (would need a wiki_config + ollama_client refactor) — neither implemented, both intentionally not free.
**Companion change:** `limits.curiosity_timeout_s` (default 240s) lifted into `Limits` + `config.example.yaml`; `compile.py:381` passes it to `ollama_client.chat_schema(...)`. Default was 90s (ollama_client.py default), gemma4:e4b on long YouTube notes regularly hits >90s. Real fix for the timeout-spam, separate from the no-fallback rule.
**Linked artifacts:** `scripts/compile.py:209-220` (cloud compile call), `scripts/compile.py:381-387` (local curiosity call with explicit timeout), `scripts/compile.py:441-446` (no-fallback exception block), `scripts/wiki_config.py:64` (`curiosity_timeout_s`), `config.example.yaml:77` (operator-visible default).
**Supersedes:** —
