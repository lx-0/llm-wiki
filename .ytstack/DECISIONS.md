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
**Linked artifacts:** `scripts/agent_spec.py`, `scripts/agent_task.py`, `scripts/agent_buttons.py`, `prompts/agents/summarize-day.md`, `lib/seed.sh:_merge_agent_shell_commands`, `lib/seed.sh:_rewrite_dashboard_agent_buttons`, `wiki agent` subcommand.

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

## 2026-05-04 (correction): Narrow distill-don't-cite to `raw/memories/` only

**Context:** The original entry below ("2026-05-04: Distill, don't cite") banned body wikilinks to *all* of `raw/` and `daily/`, citing "gleiche churn-rate eigentlich". That was an unjustified scope expansion: only `raw/memories/` is a managed mirror that prunes (`scripts/sync-memories.py:202`). `daily/*.md`, `raw/notes/*`, `raw/articles/*` are durable — no engine code prunes them. The over-broad migration on the lxw vault stripped 308 valid `daily/` wikilinks, 73 `raw/notes/`, and 9 `raw/articles/` alongside the ~502 `raw/memories/` ones it was supposed to target. Operator caught it: *"hast du ALLES unlinked aus raw/?"*
**Options considered:** (A) leave the over-broad ban in place + accept the loss of citable durable substrates — clean rule, but discards working audit-trail wikilinks the operator relies on; (B) reverse the migration entirely + lose the raw/memories/ fix too; (C) narrow the rule to `raw/memories/` only and selectively restore daily/ + raw/notes/ + raw/articles/ in the live vault from `git show :path` (staged-version) so user's pre-existing staged work is preserved.
**Chose:** C.
**Reason:** Citation-citability is a per-substrate property determined by who owns the prune lifecycle, not by surface-shape similarity ("starts with `raw/`"). Lumping subtrees together because they share a prefix is sloppy. Each subtree gets evaluated on its actual upstream-source behavior:

| Subtree | Pruned by? | Citable in body? |
|---|---|---|
| `raw/memories/` | `sync-memories.py:202` (managed mirror) | NO |
| `raw/notes/email/*`, `raw/notes/screenshots/*`, `raw/notes/youtube/*`, `raw/notes/calendar/*`, `raw/notes/browser/*`, `raw/notes/tabs/*` | nobody (collectors are append-only / skip-existing) | YES |
| `raw/articles/*` | nobody (manual + clipper) | YES |
| `daily/*.md` | nobody (append-only session-history) | YES |

The narrowing also unlocks lint to surface broken `[[daily/...]]` / `[[raw/notes/...]]` wikilinks as ordinary `error broken_link` instead of suppressing them — better signal for the next round of triage.

**Linked artifacts:** `prompts/compile_main.md` rule 6 (rewritten to ban only `raw/memories/`), `scripts/migrate_strip_substrate_links.py` regex narrowed to `raw/memories/[^|\]]+`, `scripts/lint.py:check_broken_links` substrate_link warning fires only for `raw/memories/` + new `_wikilink_target_exists` helper resolves `daily/` and `raw/` paths against `ROOT_DIR`. Lxw vault remediated via a `git show :path` (staged-version) base + narrow re-strip — preserves user's pre-staged work in 99 MM + 182 AM files. Engine commit `4af8e54`, doc-sync `7a750b1`, infographic-sync `ee7e768`.
**Supersedes:** the broad scope of "2026-05-04: Distill, don't cite". The original entry's *principle* still holds (managed-mirror substrates aren't body-citable); only the scope identification was wrong.

## 2026-05-04: Graph view defaults — semantic Material palette, no greens, tuned forces

**Context:** Audit of the lxw vault graph view (~668 nodes) surfaced three problems: (1) `knowledge/facts/` (1 node, authoritative) and `knowledge/MOCs/` (3 nodes, hub navigation) had no color group at all — the rarest and most important node types rendered in the same default color as everything else; (2) the existing palette (pastel pink for people, light violet for connections) had no semantic grouping and low saturation that washed out at small node sizes; (3) forces were contradictory (`linkStrength: 1` + `linkDistance: 250` — max-pull and max-stretch simultaneously) producing the tight-blob look in graph screenshots.
**Options considered:** (A) hand-pick aesthetic colors per group — what the previous template did and what failed; (B) use a published Material/Tailwind palette and pick A-tier saturated hues with explicit hue-distance budgeting — concrete, reproducible, distinguishable at small sizes; (C) use only chroma-distance from a base color — algorithmic but requires a tool, not native to Obsidian's `color: {a, rgb}` JSON.
**Chose:** B with a hard "no greens" rule.
**Reason:** Material Design's A-tier (`A400`/`A700`) is engineered for high-saturation high-readability use at small visual sizes — exactly the graph-view case where each node is 6–12 px. Hue-distance of ≥40° between adjacent groups keeps them distinguishable even at low brightness. Greens (`~120°`) are deliberately avoided because Obsidian's Tags filter (when toggled on) renders tag-nodes green; reusing the hue would conflate two semantic axes that operators commonly toggle independently. Final palette: facts `#FF1744` (red, authoritative pop) → MOCs `#FFC107` (amber, hub gold per Steven Thompson's Zettelkasten convention) → connections `#FF6F00` (orange, glue) → projects `#00BCD4` (cyan, cool entity) → people `#D500F9` (magenta) → concepts `#3D5AFE` (indigo, baseline — 85% of vault, must recede). Forces aligned to ~668 nodes via the obsidian-forum example (repel ≈ 16, distance ≈ 200, linkStrength ≈ 0.45): center 0.3 / repel 15 / linkStrength 0.5 / linkDistance 200. Display tuned: textFadeMultiplier 1.5 (labels appear when zoomed), nodeSizeMultiplier 1.2 (hubs prominent), lineSizeMultiplier 0.5 (less edge noise on dense graphs). `hideUnresolved: true` (post-migration the only ghost-node source is gone). `showOrphans: false`, `showTags: false`, `showAttachments: false`.
**Linked artifacts:** `templates/.obsidian/graph.json` (engine default), commits `725a5e9` (initial pastel proposal + force-tuning) and `15490da` (saturated Material override after operator feedback). Operator vaults pick up the new defaults via `wiki seed` for new installs; existing vaults can either patch in place (preserving last `scale` + `close` runtime state) or let `wiki seed --force` overwrite — chosen for the lxw deployment 2026-05-04.
**Supersedes:** original 5-group pastel palette, missing facts + MOCs entries.

## 2026-05-04: Distill, don't cite — no body wikilinks to `raw/` or `daily/` substrate

**Context:** Audit of the lxw vault Obsidian Graph View (2026-05-04) surfaced ~190 ghost-node entries — wikilinks from `knowledge/*.md` bodies pointing at `raw/memories/<project>__<name>.md` files that no longer exist. Total inventory: 892 substrate-citing wikilinks across knowledge/ (584 raw/, 308 daily/), 156 of which were already broken (~70% of `raw/memories/` links). Root cause is architectural: the compile prompt instructed the model to cite source material via wikilinks, but `raw/memories/` is a managed mirror (`scripts/sync-memories.py:202`) that prunes whenever the upstream `~/.claude/projects/<encoded>/memory/*.md` disappears — and auto-memories disappear constantly: Claude itself rewrites + prunes them actively (it's a documented Claude Code feature), sandbox cwds die (Paperclip ephemeral workspaces), `/claude-cleanup` removes old project entries. `daily/*.md` has the same churn shape (rolls over). `lint.py:check_broken_links` was hard-skipping both prefixes with the comment "source references are valid" — an assumption that was never true once sync-memories started pruning.
**Options considered:** (A) **Distill, don't cite.** Compile prompt forbids body wikilinks to raw/ + daily/; provenance lives in `compiled_from:` frontmatter + `index.md`'s "source file(s)" column. One-time migration strips existing dangling links. — Karpathy + Cole Medin's implicit pattern (neither tries to mirror auto-memory; Karpathy uses a hand-curated `context.md`, Cole captures conversation transcripts only). (B) Snapshot, don't mirror — sync-memories writes content-hash-suffixed paths and never deletes; storage grows linearly with churn. (C) Don't sync at all — drop `raw/memories/` as a substrate.
**Chose:** A, plus C as **default-disabled fallback** — `piggybacks.sync_memories.enabled: false` in `config.example.yaml`, but the script `scripts/sync-memories.py` is kept as a self-contained opt-in tool (no other engine code imports it). Operators who specifically want auto-memory churn tracked can flip the flag back. Removal candidate when no opt-ins for ~6 months.
**Reason:** A is the architecturally honest move — citations imply durability, substrate is ephemeral, the contradiction was the bug. Karpathy + Cole both validate the "ingest then forget the input" pattern: the substance lives in compiled `knowledge/` articles, the source path stays as `compiled_from:` provenance metadata. Keeping C as opt-in respects operators who already use the mirror's cross-project insight (the substance grep has historically been useful) without burdening default installs with the broken-link noise.
**Linked artifacts:** `prompts/compile_main.md` rule 6 (the explicit ban), `scripts/migrate_strip_substrate_links.py` (new — one-time migration, --vault PATH driven, --apply gates writing), `scripts/lint.py:check_broken_links` (skip removed; substrate-link in body now surfaces as `warning severity=substrate_link` with migration command in detail), `config.example.yaml` (sync_memories flipped to false with inline phase-out comment), `scripts/sync-memories.py` docstring (phase-out note), commit `696a643`.
**Supersedes:** the implicit assumption in earlier KNOWLEDGE.md sections that `raw/` is immutable.

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

## 2026-05-05: SessionStart hook injects a pointer block, not the index body

**Context:** `hooks/session-start.py` was embedding the full body of `knowledge/index.md` into every Claude Code session's `additionalContext` (capped locally at 20 000 chars). Comparison against the two named inspiration sources for the project — Karpathy's LLM Wiki gist and Cole Medin's claude-memory-compiler / second-brain implementations — showed that **neither pushes the catalog at session start**. Karpathy reads the index on demand at query time; Medin's hooks (where present) push curated `memory.md` content, never the full catalog. The current design was an own-project extrapolation, justified internally via the "Working memory" row in the `docs/concept.md` cognitive-functions table and grafted onto a compile-time TPM-rate-limit fix (KNOWLEDGE.md "Compile prompt design"). Two operational problems compounded it: Anthropic's official cap on `additionalContext` is **10 000 chars** (not 20 000), so the SDK was already silently truncating ~93 % of our payload to a side-file; and most sessions launched from arbitrary CWDs don't need wiki context at all, paying a fixed prefix tax for nothing.
**Options considered:** (A) keep body-embed, raise the cap — pointless, harness still truncates at 10K; (B) move pointer into `AGENTS.md` (Anthropic's official recommendation for static context) — invalid because the global SessionStart hook fires from any CWD, but vault-local `AGENTS.md` only loads when CC opens in the vault directory; (C) inject only a pointer block (paths to `knowledge/`, `raw/`, `AGENTS.md`) + recent daily-tail; agent pulls articles via Read/Grep on demand.
**Chose:** C.
**Reason:** Matches both inspiration sources' on-demand pattern, drops the no-op tax for the majority of sessions that don't need the wiki, eliminates the silent-truncation problem entirely. Trade-off accepted: when a session does need the wiki, the agent will spend +1-2 tool calls (grep then read) before the right article is in context. Net better because most sessions never grep the wiki at all. The "Working memory" framing in `docs/concept.md` was updated to "the agent pulls articles on demand via Read/Grep" rather than dropped — the cognitive-functions table still maps the engine to memory phases, just with the correct mechanism.
**Linked artifacts:** `hooks/session-start.py` (refactor), `prompts/`-style is intentionally NOT used here — this is a static-content hook, not an LLM prompt, so a Python constant is the right shape; `.ytstack/KNOWLEDGE.md` "SessionStart hook — pointer block, not body embed" entry; `docs/PROCESS.md` + `docs/concept.md` + `AGENTS.md` + `docs/architecture.excalidraw` mirror-updates; commit `ab090b0`.
**Companion backlog:** `prompt-aware-index-injection.md` (opt-in UserPromptSubmit-hook with deterministic ripgrep), `postcompact-only-injection.md` (conditional `source: "compaction"` firing) — both evaluate after the pointer-block has been observed long enough.
**Supersedes:** the "Working memory = inject `index.md`" framing in `docs/concept.md:147` (now revised to "agent pulls on demand").

## 2026-05-10: Compile-pass system prompts: explicit `.md` files in `prompts/`, never the `claude_code` preset

**Context:** Recurring `compile_file ✗ failed · kind=unknown · empty stderr` mid-stream crashes on certain daily/memory files (300-500 s of silence, then bundled CLI subprocess exits 1, no stderr written). Root cause traced: `compile.py` set `system_prompt={"type":"preset","preset":"claude_code"}` on every `query()` call, but the SDK's `_build_command` only serializes preset specs that carry an `"append"` key (`subprocess_cli.py:178-180`). Without `"append"` the spec falls through with no `--system-prompt` flag → the bundled CLI uses its own **interactive default**, which is the full Claude Code system prompt with all agent definitions, deferred tool catalogs, MCP descriptions, ytstack content, and skill listings (~50-100K input tokens of overhead per call). That heavy default is what triggered the streaming death. Bundled CLI invoked manually with the same content but a minimal system prompt completes cleanly. The user explicitly excluded filing an upstream issue (`no anthropic SDK bug reports` policy, recorded as feedback memory + KNOWLEDGE.md cross-link).
**Options considered:** (A) inline a `COMPILE_SYSTEM_PROMPT = "..."` constant in `compile.py` — rejected immediately by user: prompts belong in `prompts/`, not in Python; (B) use `system_prompt=""` (empty) — works but loses any anchor for tool guidance; (C) explicit `prompts/compile_main_system.md` + `prompts/compile_suggestion_system.md` loaded via `render(...)`, matching the existing `flush_extract_system.md` convention. Also add `setting_sources=[]` to block CLAUDE.md / project-settings layering.
**Chose:** C.
**Reason:** Establishes the system-prompt-as-file convention symmetrically with user-prompt-as-file (`compile_main.md`, `compile_suggestion.md` already existed). Single source of truth for LLM-facing text lives in `prompts/`; reviewers see prompt changes in their own diff scope; operators iterate without touching Python. `setting_sources=[]` is the matching pair — without it the SDK still layers CLAUDE.md content on top, defeating the purpose of stripping the preset. Verified: `daily/2026-05-08.md` crashed at 512 s in production; with the patch it compiles in 221 s, $0.025. The previously-cascading `cli_crash` fast-fail sequence (sub-3-second silent exits after an initial mid-stream crash) also disappeared in the post-patch run — strongly suggests the preset overhead was the primary trigger and the cascade was SDK subprocess-pool corruption downstream of the first crash.
**Linked artifacts:** `prompts/compile_main_system.md` + `prompts/compile_suggestion_system.md` (new), `scripts/compile.py:225,316` (call sites — explicit `render("...")` + `setting_sources=[]`), `.ytstack/KNOWLEDGE.md` "Compile silent CLI crash — the `claude_code` preset spec was the trigger" entry, commit `38910a4`.
**Project policy reinforced:** `feedback_no_anthropic_bug_reports.md` (memory) + `feedback_prompts_in_prompts_folder.md` (memory). Both are operating-rules that apply to all future engine work.
**Supersedes:** earlier `system_prompt={"type":"preset","preset":"claude_code"}` invocation pattern across `compile.py`. Other call sites in flush.py already used the correct `render("..._system")` form (no change needed there). Future SDK call sites must follow the flush.py pattern.

## 2026-05-13: Memories are not a substrate — hard-remove sync-memories + seed + raw/memories/ wiring

**Context:** Auto-memories under `~/.claude/projects/<encoded>/memory/*.md` are Claude's runtime-level distillation *of sessions*, written by Claude during the session itself. The engine already captures the upstream source: SessionEnd hook → `flush.py` → `daily/YYYY-MM-DD.md`, then `compile.py` distills daily/ into knowledge/. Empirically verified 2026-05-13: e.g. `project_install_ux_fix.md` (originSessionId `3c58cd7f`) and `daily/2026-05-13.md` session 11:45:32 share the same three lessons verbatim ("Stdout is the value, stderr is the UX", "bash 3.2 mis-parses `$( case … esac )` nested", "Three cascading bugs hide behind one symptom"), with the daily entry carrying *more* context (commit hashes, push status, sub-sessions). The substantive content of memories is already in the wiki — indirectly, via the session-capture path, with a one-session-end lag.

Mirroring `raw/memories/` was therefore downstream double-counting: replicating a *derived* artifact when we already capture the *source*. Plus the broken-link problem (502 of 584 raw/-citations were memories, ~70% dangling per 2026-05-04 audit) because Claude rewrites + prunes memories actively, sandbox cwds die, `/claude-cleanup` removes old projects — fundamentally mutable working state, not a citable durable substrate.

The 2026-05-04 entry "Distill, don't cite" (citation-mechanics rule) plus its companion variant C (`piggybacks.sync_memories.enabled: false`, opt-in script) phased the mirror to default-off with a 6-month removal-candidate clause. After 9 days the default-off-but-still-wired state had cost: lint carried a managed-mirror exception for `raw/memories/`, `prompts/compile_main.md` rule 6 banned `[[raw/memories/...]]` body wikilinks, `hooks/session-start.py` listed `raw/memories/` as a pointer-block target, `templates/AGENTS.example.md` § 5 documented the Seed flow, `docs/PROCESS.md` had a numbered Seed process, README's Path-B box advertised `sync-memories`. Surface area kept accumulating across docs, prompts, lint exceptions, and the architecture diagram — for a substrate with no consumer.

**Architectural framing (Karpathy + Cole Medin alignment):** Neither prior-art project mirrors Claude Code auto-memory. Karpathy's LLM Wiki uses a hand-curated `context.md`. Cole Medin's claude-memory-compiler captures *conversation transcripts*, not memory files. Our session-capture path matches Cole's pattern; auto-memory mirroring was a divergence motivated at the time by completeness. The 2026-05-13 hard-removal aligns us back: capture sessions (the source), let Claude manage its own memory cache, no engine-side mirror.

**Project-policy framing:** llm-wiki has no external users, no semver promise, no migration path. The standard rationale for keeping default-off-but-still-wired code paths (backwards compatibility, gradual operator migration, deprecation cycle) does not apply here. Carrying soft-deprecated subsystems through 9 days of doc-and-prompt accumulation crossed the cost threshold without buying anything that "remove it now" wouldn't also buy.

**Options considered:** (A) Hard-remove all sync-memories surface in one commit — script, seed.py companion, migrate_strip_substrate_links.py purpose-built migration, piggyback entry, config block, lint exception, prompt rule, session-start pointer, AGENTS.md/README/PROCESS.md sections. (B) Keep the 6-month opt-in window and revisit in November — preserves an escape hatch but freezes the doc/prompt surface area for the duration. (C) Reverse Karpathy/Cole alignment and double down on the mirror — would require Snapshot-don't-mirror (content-hash paths, never delete) to fix the broken-link rate; was already rejected as variant (B) of the 2026-05-04 decision.

**Chose:** A.

**Reason:** No operator opt-ins since the 2026-05-04 default-off flip. The 6-month window was a hedge for a population of zero. Surface area was real (every doc-sync pass had to re-decide what to say about `raw/memories/`; every new lint check had to consider the managed-mirror exception). Removing in one commit collapses all of that to a single audit point.

**Operator escape hatch:** The vault directory `<vault>/raw/memories/` is not touched by the engine post-removal. Operators who had data there keep it; engine no longer creates, prunes, or warns about it. Re-introduction (if ever needed) would be a fresh substrate decision, not a feature revival, with whatever lifecycle rules fit the new context.

**Linked artifacts:** Commit `3c40fbe` (deletes `scripts/seed.py`, `scripts/sync-memories.py`, `scripts/migrations/migrate_strip_substrate_links.py`; removes engine wiring in `flush.py:_LEGACY_PIGGYBACK_COMMANDS`, `core/wiki_config.py:_default_piggybacks`, `core/config.py:RAW_MEMORIES_DIR`, `config.example.yaml`; removes exception logic in `lint.py:check_broken_links`, `prompts/compile_main.md` rule 6, `hooks/session-start.py` pointer list; doc-sync across `AGENTS.md`, `templates/AGENTS.example.md`, `docs/PROCESS.md`, `docs/concept.md`, `docs/config.md`, `docs/engine-layout.md`, `README.md`). Pytest 79/79 pass. Piggyback count went 9 → 8.

**Supersedes:** 2026-05-04 "Distill, don't cite" entry's *variant C* (the opt-in mirror fallback). The 2026-05-04 *citation rule* still holds in general — no body wikilinks to managed-mirror substrates — but it's not the load-bearing argument here. The 2026-05-13 argument is upstream: memories are downstream of sessions, sessions are already captured, mirroring memories double-counts. What this entry retires is the specific `raw/memories/` substrate as engine-managed; the citation rule applies to whatever future substrate (if any) takes the managed-mirror shape.

**Follow-up — architecture diagram (open):** `docs/architecture.excalidraw` still has the `pb_sync_memories_rect` piggyback pill and `collector_sync_memories` collector box from the pre-removal state. To be removed in a follow-up diagram-sync pass (no replacement node — substrate is gone). Caught by 2026-05-13 audit, not blocking.

## 2026-05-13: Jamie meeting-notetaker shipped as Collector — tRPC client + diarised-transcript reformatter

**Context:** Operator needs a meeting-ingest substrate. Four FOSS candidates evaluated (Meetily, Hyprnote/anarlog, Screenpipe, Ghostpepper). Meetily was installed and tested first; its diarisation is marketing-claim-only (source comment: `# --diarize Enable speaker diarization (feature not available yet)`; community-edition flag is commented out in the docker entrypoint). Hyprnote rebranded twice (Hyprnote → char → anarlog), team focus moved to commercial char.com, OSS companion in maintenance mode. Screenpipe is a different category (24/7 screen-and-mic memory; meetings are a subset; desktop app paid). Operator switched to Jamie AI: Pro plan, official API key, working speaker diarisation, Cole-Medin-style "compile already-distilled meeting notes" pattern.

**Architectural framing:** Jamie's public API is documented as REST on docs.meetjamie.ai but the wire reality is tRPC (`https://beta-api.meetjamie.ai`, `x-api-key` header, `meetings.list` / `meetings.get` / `tasks.list` / `tags.list` operations, GET-with-input encoding `?input=<JSON-encoded {"json":params}>`, response envelope `{result:{data:{json:<payload>}}}`). Verified by reading `vicampuzano/jamie-mcp` source after marketing-docs guidance produced 404s on every endpoint. Captured as `.ytstack/KNOWLEDGE.md` "Jamie API: marketing says REST, wire is tRPC" entry — applies whenever evaluating a new API: read the existing MCP wrapper or SDK before trusting docs.

**Options considered:** (A) `Collector` Protocol (`scripts/collectors/jamie.py` — substrate-orchestrator + inline HTTP client, no `adapters/meetings/` family yet). (B) `scan-jamie.py` flat CLI script in the legacy pattern. (C) Adopt jamie-mcp as an upstream dependency and shell out to the MCP server. (D) Build against Meetily's SQLite (operator's first instinct before diarisation reality surfaced).

**Chose:** A.

**Reason:** Account-typed access (personal vs workspace key types), network backend (rate-limit + auth), possible second backend later (Otter / Granola if Jamie sunsets). The Collector pattern already accommodates all three concerns via `SPEC` + Registry-walk piggyback discovery. Inline HTTP — no `adapters/meetings/` family — because there's only one backend; abstracting now is premature. MCP wrapping (option C) adds a Node.js runtime layer for a Python-uv-cron-style ingest with zero feature gain; the MCP source was useful as wire-format reference, not as a dep.

**Transcript reformatting:** Jamie ships transcripts as a single markdown string with `<Speaker>\n\n\n###### MM:SS - MM:SS\n\n<text>` shape per turn. Rendered in Obsidian: speaker names become washed-out body text, oversized whitespace gaps, H6 timestamps. Rewrote each turn to the youtube-uniform `**Speaker** [mm:ss] — text` convention via regex parse with verbatim-passthrough fallback if the format ever changes upstream. File size dropped ~50% just from the whitespace collapse.

**Linked artifacts:** Commit `4703c60` (collector + config + concept), `da83ce4` (tRPC rewrite after live probe), `3898205` (transcript reformatter), `c653496` (docs sync — `docs/config.md` NEW grouped reference, cli/AGENTS/PROCESS/KNOWLEDGE updates), `cbac036` (architecture + vault-tour excalidraws). `.ytstack/backlog/jamie-intake.md` carries the concept doc + phase-2 verification. `.ytstack/KNOWLEDGE.md` gained three entries: "Jamie API: marketing says REST, wire is tRPC", "`.env` loader gap" (gap discovered while wiring the secret-provisioning side), "core/ refactor path-computation off-by-one" (caught by the Jamie smoke-test in the productive vault).

**Operator follow-up:** None blocking. `wiki collect jamie` is wired as auto-piggyback at `cooldown_hours: 6, max_per_run: 20`. Six real meetings live in lxw vault `raw/transcripts/jamie/`; first `wiki compile` pass over them will be the proof-of-distillation. If Jamie sunsets, drop a second `Collector` next to `jamie.py` (Otter / Granola / whatever); the engine wiring (config block, Registry, `RAW_TRANSCRIPTS_DIR` substrate, compile-prompt rule 6 covering durable substrates) doesn't need to change.

**Supersedes:** The pre-2026-05-13 "no meeting substrate" state — `RAW_TRANSCRIPTS_DIR` had been declared in `core/config.py` and the substrate listed in AGENTS.md, but nothing wrote to it. Now `raw/transcripts/jamie/` is alive.

## 2026-05-13: Compile-prompt index — compact (path + date), not full body — pointer-first for growth substrates

**Context:** Jamie meeting-compile pipeline rolled out 2026-05-13 (Phases 3-5 of llm-wiki-change). End-to-end test on four real meetings (9 KB / 35 KB / 60 KB / 75 KB sources) revealed a class of silent crashes at ≥60 KB: bundled CLI exits 1 with empty stderr after 4-9 min of activity, no parseable stream-json messages emitted, `$0.00` cost. The SDK-buffer fix from commit `70d2fef` (raised `max_buffer_size` to 50 MB) didn't help — different mechanism.

**Architectural framing:** `compile_main.md` and three sibling prompts embedded the full `${index_md}` body. `knowledge/index.md` at 700+ articles = 550 KB ≈ 140K tokens. Combined with a 60 KB source + 25 KB AGENTS + facts + template = ~190K tokens — straddling Opus's 200K context window. The SessionStart-hook fix (commit `ab090b0`, 2026-05-05) had already established the **pointer-first** pattern: tell the LLM what file to inspect via Read/Grep/Glob, don't embed the body. That pattern was applied to one substrate (SessionStart pointer block) but not to the four compile-side prompts that have the identical growth profile.

**Options considered:** (A) compact-index — strip summary + sources columns from `knowledge/index.md`, keep Article + Updated only, embed the compact form in prompts; full row content available on demand via Grep. (B) full pointer-first — remove `${index_md}` entirely, force Grep-then-Read for every dedup decision; smallest possible prompt but the LLM loses the at-a-glance article catalogue. (C) maintain a separately-generated `knowledge/index-compact.md` file on disk, alongside the main index; the prompt embeds the compact file. (D) chunk the index by article type and embed the type that matches the source (e.g. screenshots → concepts only).

**Chose:** A.

**Reason:** (A) gives the LLM the **complete article catalogue** (every path it can possibly link to) at one-third the prior size, with the workflow-reinforcement (Grep for summary, Read for body) baked into the prompt. (B) loses the catalogue and risks duplicate-creation. (C) doubles the index files and adds a drift-management burden. (D) imposes a substrate→type mapping decision that doesn't generalise (Jamie transcripts produce concepts AND people AND projects from the same source).

The compact form is computed at runtime from `knowledge/index.md` (Python helper `core.utils.read_wiki_index_compact()`) — no second file to keep in sync, no operator-visible artefact. Obsidian's `[[X\|alias]]` pipe-escape syntax is preserved via sentinel-replace before column-split.

**Linked artifacts:** Commit `94c9d6b` (helper + 4 call sites: `compile.py:168/271`, `suggestions/producer.py:45`, `optimize-claude-md.py:55`; four prompts updated: `compile_main.md`, `compile_curiosity.md`, `compile_suggestion.md`, `optimize_claude_md.md`). `core/utils.py:read_wiki_index_compact()` is the canonical implementation. KNOWLEDGE.md entry "Compile context overflow — `${index_md}` body embed grew past Opus's 200K-token window (2026-05-13)". Live verification: 4 Jamie meeting compiles (including the previously-failing 60 KB twice and the 75 KB Bad Nauheim Workshop) all succeed post-fix at $0.03-0.05 per compile.

**Lesson generalised:** Any prompt template substitution carrying an artifact that **grows linearly with the corpus** (an index, a log, a daily archive, a participant directory) is a context-overflow ticking bomb. The pattern applies whenever a `${var}` in `prompts/*.md` is bound to "all the X". Compact (project columns) or pointer (Grep-the-file) is the right shape. Body-embed is fine only for **bounded** surfaces — facts (a few rows), AGENTS schema (operator-curated, capped), the source itself.

**Supersedes:** The pre-2026-05-13 compile-prompt design that embedded the full `${index_md}` in four prompts. The SessionStart-hook `ab090b0` precedent is now generalised across all LLM-prompt call sites that previously body-embedded the index.

**Follow-up (open):** `lint.py:check_orphan_pages` still uses `read_wiki_index()` full body — different consumer (Python grep, no LLM call), no fix needed. If any future LLM-prompt site needs the index, default to `read_wiki_index_compact()`.

## 2026-05-13: Claude Agent SDK per-message buffer — explicit 50 MB, not the 1 MB default

**Context:** Same Jamie meeting-compile pipeline. Three pre-buffer-fix runs surfaced a different class of crash with the same exit-1-empty-stderr symptom: `Failed to decode JSON: ... exceeded maximum buffer size of 1048576 bytes`. The SDK's `_internal/transport/subprocess_cli.py:_DEFAULT_MAX_BUFFER_SIZE = 1024 * 1024` (1 MB) limits each line of stream-json from the bundled CLI to 1 MB. Tool-result messages carrying `knowledge/index.md` body (~300 KB raw → ~600 KB JSON-escaped) and Write/Edit calls on large articles (200 KB content → >1 MB after escaping) blow the limit.

**Options considered:** (A) raise `max_buffer_size` to a generous value via `ClaudeAgentOptions(max_buffer_size=...)` at every call site; the SDK exposes the override per call. (B) wrap `query()` in a custom transport that bumps the buffer at the SDK level (subclass / monkey-patch). (C) shrink every potential big message at the prompt layer — never let the LLM Read/Write big files (would require chunking workflows and severely limits the design).

**Chose:** A.

**Reason:** (A) uses the SDK's documented escape-hatch as designed. (B) re-implements internals. (C) makes the compile prompt design hostage to the SDK's hardcoded constant. Lifted to `CONFIG.limits.sdk_max_buffer_size_mb` (default 50 MB) per the project's "lift hardcoded constants to CONFIG immediately" rule. 50 MB is well above any realistic single-message scenario (largest foreseeable article × 5 safety factor) without hiding genuinely runaway responses.

**Linked artifacts:** Commit `70d2fef`. All 8 SDK call sites threaded with `max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024`: compile, flush, lint, query, agent_task, optimize-claude-md, suggestions/producer, facts/correct_apply. KNOWLEDGE.md entry "Claude Agent SDK silently crashes on >1 MB stream-json messages (2026-05-13)". Verified: 35 KB Jamie compile that previously failed at 543s (`exit-1`) now succeeds in 319s ($0.05).

**Lesson:** When an SDK exposes a per-call tunable for a hard limit, set it explicitly at every call site instead of trusting the documented default. The 1 MB default is reasonable for the SDK's general audience; too small for a knowledge-base compiler that reads/writes long markdown.

**Supersedes:** The pre-fix invocation pattern at all 8 call sites that relied on the SDK default. Future SDK call sites must include the `max_buffer_size=` parameter.


## 2026-05-14: Email delta-ingest restored — per-account watermark, run-start-time, baseline-on-first-run

**Context:** The M002/S02 Collector refactor (commit `14bf844`) ported `scan-email.py` into `EmailCollector` and silently dropped the delta logic — `run()` accepted `incremental` but never used it, never read `email-state.json`, never passed `since=` to the reader. The piggyback kept spawning but produced zero files; the lxw vault's last delta was `2026-05-01`, a 13-day-and-counting regression. The seam (`MailboxReader.scan_metadata(since=)`) was already correct; only the Collector forgot to use it.

**Decision points (each had real alternatives):**

1. **State shape — per-account, not per-mbox-file.** The legacy `scan-email.py` tracked per-mbox-file `{size, count, last_scan}` and used a cheap size-stat to skip unchanged mboxes. The new architecture pushed mbox iteration *into* the stateless `MailboxReader`, so the Collector can't see individual mbox files anymore — and shouldn't (Gmail has no "mbox files"). New shape `{"accounts": {<id>: {"last_run_ts": "<iso>"}}}` mirrors Jamie's `last_seen_ts` but keyed per account (email is `supports_account_loop=True`). The lost size-stat optimisation is accepted: `scan_metadata(since=)` re-opens every mbox each run, but date-filtering inside the reader is correct, and the alternative (leaking mbox-file knowledge back out of the seam) would re-break the abstraction the refactor just built.

2. **Watermark = run-start time, not max-message-date.** Jamie uses the highest `started_at` seen. Email rejects that: bogus future-dated spam is common, and a max-date watermark would jump to the future and skip everything after it. Run-start-time is monotonic, immune to message-date garbage, and the legacy script's date-granularity `last_incremental` already worked this way (just coarser). Trade-off: a message delivered *during* a scan with a `Date` header just before run-start could be missed — accepted as a rare edge, documented.

3. **First incremental run = baseline, emits nothing.** With no watermark, `since=None` would scan the *entire* mailbox and render it as one giant "delta" — re-dumping the operator's one-time bulk ingest. Instead: record `last_run_ts = now`, write no report, let the next run produce the first real delta. Mirrors the legacy script's "baseline recorded, will scan on next run".

4. **Legacy state migrated, not discarded.** `_load_state()` detects the old `{"mboxes": {...}, "last_incremental": "..."}` shape and seeds every configured account's `last_run_ts` from `last_incremental`. On lxw this means the first post-deploy run picks up the full 2026-05-01 → now gap instead of silently re-baselining and losing 13 days of mail.

5. **Full sweep also advances the watermark.** `wiki collect email` (full mode) writes the overview report *and* updates `last_run_ts` — both modes "observed the mailbox", so both maintain the watermark. Keeps a manual full sweep from causing the next incremental run to re-scan everything it just saw.

**Scope:** One code file — `scripts/collectors/email_collector.py`. The fix is localised because the seam was already right; `flush.py`→`cli.py`→`run()` already plumbed `--incremental`, the adapters already honoured `since=`. No new config key (`piggybacks.email` already existed), no new hook.

**Linked artifacts:** `scripts/collectors/email_collector.py` (`_run_full` / `_run_incremental` split, `_load_state` with legacy migration, `_render_delta_report`, `_parse_since`, `_now_slug`). `tests/test_email_collector_fakereader.py` +5 incremental-path tests (baseline, delta, no-new-mail, dry-run-no-state, legacy-migration) + autouse state-isolation fixture; 157/157 pass. KNOWLEDGE.md entry "A Protocol flag the implementation ignores is worse than no flag (2026-05-14)". Delta output: `raw/notes/email/<account>-delta-<ts>.md`, frontmatter `type: email-delta`.

**Operator follow-up:** Deploy to lxw via `wiki update`. First incremental piggyback run after deploy migrates the stale `email-state.json` and emits one delta per account covering the 2026-05-01 → now gap; subsequent runs are true incrementals.

**Follow-up (2026-05-14, same day — first live run on lxw):** The run validated migration + mechanism, but the output analysis forced two refinements (same commit-area, folded into a follow-up commit):
1. **Undated messages leaked into every delta.** `ThunderbirdMboxReader` filtered `date < since` but let `date is None` pass — the legacy `scan-email.py` had explicitly skipped undated mail in delta mode. Without the skip, every message with an unparseable Date header re-reports forever. Fixed in `_iter_metadata` + `_iter_deep`: `since is not None and (date is None or date < since)`.
2. **Delta report was too thin to compile from.** It emitted only folder/count/date-range/top-sender aggregates — `MessageMeta.subject` was carried through the pipeline then discarded. A delta is a bounded set (unlike the 50k-message full sweep), so `_render_delta_report` now lists each message as `date · sender · subject`. The subject is the highest-signal field and the only thing the compiler can meaningfully distil.
The full-sweep `_render_report` is unchanged — aggregation is still correct there because a full mailbox can't be listed line-by-line.


## 2026-05-14: IMAP reader — the no-local-client, no-GCP-project mailbox path

**Context:** The mailbox-collector architecture had two reader kinds: `thunderbird-mbox` (reads what a local mail client already synced — zero credentials in the engine) and `gmail-api` (Gmail API + OAuth). A colleague who runs **no local mail client** and is on a **personal `@gmail.com`** is served by neither: `thunderbird-mbox` has nothing to read, and `gmail-api` dead-ends because end users won't create a Google Cloud project — and a borrowed/sample `client_secret.json` gets hard-blocked by Google ("Diese App ist blockiert"). The wiki is internal-user-only; many colleagues are exactly this cloud-only-Gmail, no-local-client case.

**Research (2026-05, see `.ytstack/backlog/imap-reader-and-gmail-strategy.md`):** Basic-auth over IMAP is dead since 2025. App passwords still work for **consumer `@gmail.com`** (not Workspace) with 2FA — the standard no-GCP-project, no-local-client path, though on Google's slow deprecation watch. Email clients "just work" because they ship a pre-registered, Google-verified OAuth client; a small tool can't replicate that for the restricted `https://mail.google.com/` scope without Google's security assessment. An OAuth app with User Type **"Internal"** skips verification entirely — but only for members of the owning Workspace.

**Options considered:** (A) generic `imap` reader + app password. (B) ship one verified OAuth client with the engine — needs Google's restricted-scope security assessment, annual cost, project-level maintenance. (C) one shared **"Internal"** OAuth app owned by the org — clean for Workspace colleagues, but doesn't cover personal `@gmail.com`, and is org-process not engine code. (D) SaaS OAuth broker (Composio etc.) — adds a third party + their cloud to the data path, antithetical to the local/no-cloud ethos.

**Chose:** A for the engine change (covers the immediate audience: cloud-only personal Gmail + any plain IMAP host). C documented as the org-side path for Workspace colleagues (no engine work — the existing `gmail-api` reader already supports it; what was wrong before was the borrowed `client_secret.json`, not the approach). B and D rejected.

**Reason:** A keeps the engine's "no cloud, credentials are env-var names only" discipline — `config.yaml` carries `imap_pass_env` (a name), the app password lives in `.claude/.env`, exactly like the existing `all-inkl-procmail` filter. It works *today* for the colleagues who are blocked *today*. C is the cleaner long-term answer for Workspace users but it's org bureaucracy, not something the engine can ship.

**Design:** New `scripts/adapters/mailbox/imap.py` — `ImapReader` implements the existing `MailboxReader` Protocol unchanged (`list_folders` / `scan_metadata` / `scan_deep`), so `EmailCollector`, `collectors/cli.py`, and the curiosity deep-scan consume it without edits. Stateless: connect → `SEARCH` → batched `FETCH` → logout per call. `since` pushed to the server via IMAP `SEARCH SINCE` (date-granular) then re-filtered in Python against the precise watermark — and undated messages skipped in delta mode, the same rule as `ThunderbirdMboxReader` (KNOWLEDGE.md). `IMAPClient(normalise_times=False)` keeps timestamps tz-aware. Optional `folders` allowlist scopes Gmail's `[Gmail]/All Mail` double-count away. `imapclient>=3.0.0` was already a dependency.

**Linked artifacts:** New `adapters/mailbox/imap.py`; `adapters/mailbox/__init__.py` (`kind: imap` dispatch + kind-table); `config.example.yaml` + `templates/.claude/.env.example` (imap reader example, `IMAP_<ACCOUNT>_PASS` convention); `tests/test_imap_reader.py` (7 tests — Protocol conformance, MessageMeta build, since+undated filter, folder allowlist, graceful no-creds / login-failure, resolve_reader dispatch); 195/195 pass. lxw `config.yaml` reconfigures `gmail-personal` from `gmail-api` → `imap`. `.ytstack/backlog/imap-reader-and-gmail-strategy.md` carries the concept + the org-side "Internal OAuth app" strategy.

**Operator follow-up:** lxw `gmail-personal` needs `IMAP_GMAIL_PERSONAL_PASS` set in `.claude/.env` to a Google App Password (2FA must be enabled on the account first). Until then the account is a graceful no-op (warning logged, nothing scanned).


## 2026-05-14: Agent specs move to `prompts/agents/` subfolder

**Context:** M004 placed agent-task specs flat in `prompts/` as `agent_<id>.md`. M004-CONTEXT.md justified the flat layout by "they sit alongside the prompt-rendering convention and reuse `prompts.py`'s `${var}` pipeline" — but that rationale never matched the implementation: agent specs are parsed by `agent_spec.py` and do their own `${var}` substitution in `AgentSpec.render_body()`. `prompts.py:render()` is never involved. So `prompts/` was holding two unrelated artifact kinds — `render()` template fragments (`compile_main.md`, `flush_extract.md`, …) and self-contained, frontmatter-declared, independently-runnable agent specs.

**Options considered:** (A) leave flat, keep `agent_` prefix. (B) move to `prompts/agents/<id>.md`, drop the now-redundant prefix. (C) move *and* realign frontmatter to the generic Claude-Code subagent format (`name`/`tools`/`model`).

**Chose:** B.
**Reason:** A dedicated subfolder cleanly separates the two artifact kinds; the folder name carries the semantic, so the `agent_` filename prefix is redundant. C was rejected — the spec format is a deliberate superset (`button`, `cwd`, `last_run`, `shell_command_id`, `max_turns`, `permission_mode`) driven by the dashboard-button + runner integration that *is* M004; adopting the generic format would either lose those fields or just rename overlapping keys for cosmetic conformance. Glob changes from `agent_*.md` to `agents/*.md` — every `.md` in the dedicated dir is now a spec. Path centralised as `core/config.py:AGENT_SPECS_DIR` (was duplicated as a local `PROMPTS_DIR` in `agent_task.py` and `agent_buttons.py`).

**Linked artifacts:** `core/config.py:AGENT_SPECS_DIR`; `core/agent_spec.py:list_specs`; `scripts/agent_task.py`; `scripts/dashboard/agent_buttons.py`; `prompts/agents/summarize-day.md` (moved via `git mv`); `tests/test_agent_task.py` + `tests/test_summarize_day.py`. Supersedes the 2026-05-02 flat-layout note in `M004-CONTEXT.md`.
