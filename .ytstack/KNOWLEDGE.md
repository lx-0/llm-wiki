# Knowledge

Patterns, rules, and lessons learned while building llm-wiki. This file is read by every future session.

The "Conventions" / "Workflow" / "Quick gotchas" sections are quick-reference. The "Hard-won learnings" section preserves long-form postmortems — read before changing related code.

## Conventions

- **Engine vs vault split** — engine code lives in `<vault>/.wiki/`; the user's data lives at vault root (`raw/`, `daily/`, `knowledge/`, etc.). New file? Ask: who maintains this — engine codebase or per-install? Engine code → engine repo. Per-install customization → vault. Templates/examples → engine repo with `.example.` suffix.
- **No pyproject.toml or `.venv/` at vault root.** Old workflow; replaced by `.wiki/.venv/`. Vault doesn't own engine deps.
- **Single source of truth via CONFIG.personal.*** — when data drives multiple consumers (e.g. `email_folders` drives both `compile_curiosity` prompt and `compile.py` schema enum), both consumers read from `CONFIG.personal.*`. Never hard-code in two places.
- **AGENTS.md is tool-agnostic** — Claude Code, Cursor, Aider, Codex, and others read it. Project-specific rules go there, not in CLAUDE.md.

## Workflow

- **uv invocation has three patterns** — humans `cd .wiki/ && uv run python scripts/<X>.py`; hooks `uv run --project <vault>/.wiki python <vault>/.wiki/scripts/<X>.py` (because Claude Code launches them with arbitrary CWD); engine-internal subprocess spawns use `[sys.executable, str(SCRIPT)]` (parent already in venv).
- **--project flag wired in** `lib/agents.sh`, `lib/config.sh`, `hooks/session-end.py`, `hooks/pre-compact.py`. Don't spawn engine scripts from a hook via `uv run` without `--project`.
- **Verify after deps changes:** `cd <vault> && uv run --project .wiki python -c "import flush_pipeline; print('ok')"` should succeed.

## Quick gotchas

- **Excalidraw renderer pin.** `@excalidraw/excalidraw@0.18.0` is hard-pinned in `skills/excalidraw-diagram/references/render_template.html` because the unpinned `?bundle` 404s on a transitive `@braintree/sanitize-url` dep. Watch for upstream fix; can re-unpin when 0.18+ becomes the default.
- **Renderer timeouts.** Bumped to 90s/60s in `render_excalidraw.py` for the 181-element architecture diagram. May need per-call configurability.
- **Excalidraw theme flag.** `render_excalidraw.py` defaults to `--theme dark` (matches the README hero `architecture.png`). Pass `--theme light` for light-bg targets. The light/dark switch is *post-render SVG inversion* (`filter: invert(93%) hue-rotate(180deg)`) — `appState.viewBackgroundColor` is forced to `#ffffff` either way, so authored colors look different in dark mode than they will on a light page. Always render in the theme the diagram will be consumed in before judging color choices.
- **Excalidraw library shapes are sketchy.** All four bundled libs (`skills/excalidraw-diagram/references/libraries/*.excalidrawlib` — system-design, technology-logos, cloud-design-patterns, lo-fi-wireframing-kit) use `roughness > 0` (hand-drawn aesthetic). Don't pull from them when the surrounding diagram uses `roughness: 0` (clean modern). They'll look like a Frankenstein mix. Use them only for fully-sketched diagrams, or build geometric icons from primitives for clean-style ones.
- **Two diagrams in `docs/`, two roles.** `docs/architecture.png` = full cognitive-architecture deep-dive (181 elements, dark, dense). `docs/overview.png` = README hero infographic (Grafana-style stat cards + 3×2 feature panel grid + black footer quote, dark). README hero links overview, body links architecture as the deep-dive. Don't merge — they answer different questions ("what is this in 3 seconds" vs "how does it actually work").
- **`_skip_prefixes()` in `scripts/seed.py` and `scripts/sync-memories.py`** auto-derives from `Path.home()` parts plus a small generic-workspace set. If this misses a project on a non-standard layout, extend the `_GENERIC_WORKSPACE_DIRS` constant or fall back to the cwd-from-JSONL path used in `sync-memories.py`.
- **Setup-wizard provider-specific copy.** `lib/config.sh:77-79` mentions "All-Inkl kasserver" by name. Generalize when a second provider is added.

## Cross-conversation rules (operator preferences for agents)

- **System-reminders about user edits are stale snapshots.** Always `ls`/`grep` the filesystem before claiming where a file lives or what a file contains. Reminders may reference state from earlier in the session.
- **Don't apologize after corrections.** The operator reads "sorry/verstanden" loops as worse than the original mistake. Fix and move.

---

## Hard-won learnings (engine internals)

Distilled from sessions 2026-04-11 → 2026-04-30 building this implementation. Each section is something that bit us in production — read before changing related code.

### Claude Agent SDK — `query()` with `allowed_tools=[]` is not enough

#### Symptom

`flush.log` showed 130× `Fatal error in message reader: Command failed with exit code 1`. Five sessions ended up in `failed-flushes/` and were never recovered. The SDK's stderr is a placeholder, not the real CLI stderr.

#### Root cause

`query()` with `ClaudeAgentOptions(allowed_tools=[], max_turns=2)` still loads:

- the full Claude-Code default system prompt (which encourages tool use)
- CLAUDE.md auto-discovery from user/project/local settings
- five `SystemMessage`s with tool definitions

The model **tries** to call tools (especially when the input contains `[tool: Read]` markers from prior session transcripts). `allowed_tools=[]` blocks each call but every attempt costs a turn. With `max_turns=2`, after two failed tool attempts: `result.subtype=error_max_turns`, `stop=tool_use`, exit code 1, empty `result` string.

#### Diagnosis technique

Set `stderr=callback` in `ClaudeAgentOptions`. Log every message with `type(msg).__name__`. The fields that matter on `ResultMessage`: `subtype` (`success` vs `error_max_turns`), `stop_reason`, `result` (can be `None`).

#### Fix

```python
ClaudeAgentOptions(
    system_prompt="You are a text-only X. Reply with markdown only. Do NOT call tools — you have none.",
    allowed_tools=[],
    max_turns=3,           # safety buffer
    setting_sources=[],    # skips CLAUDE.md auto-discovery
    stderr=log_callback,   # forward to our log
)
```

In result handling: `if message.subtype == "success" and message.result:` — never persist empty strings.

**Why it works:** `system_prompt` as a string **replaces** the default entirely. `setting_sources=[]` skips CLAUDE.md. The model sees only the text-only instruction and stops trying to call tools.

**Verified:** what previously failed at 7 turns now succeeds at 2 turns with 2,909 chars of clean output.

### Compile prompt design — don't embed the whole wiki

#### Anti-pattern

Original design: a `{all_articles}` placeholder embedded ALL articles (~1 MB at 200+ articles) into EVERY compile call. Result:

- TPM (tokens-per-minute) limits triggered after ~50 files
- Looks like a rate limit, but it's prompt size
- Even with prompt caching: 8× more expensive per file ($0.08 instead of $0.01)

#### Correct design: index + tools

Embed only `index.md`. Give the agent `Read`, `Grep`, `Glob` tools and let it fetch articles on demand. Prompt drops 1 MB → 70 KB. 8× cheaper, no rate limit.

**Why:** prompt caching does not compensate for TPM limits. Large static prompts are not a free lunch.

### Flush context — Karpathy/Cole's pattern is wrong for agentic workflows

#### Anti-pattern (Cole Medin's `claude-memory-compiler`)

The pre-compact hook used to map all non-text content blocks to `[tool: X]` / `[tool result]`. Consequence: 90% of session information disappears. In agentic sessions (heavy tool use, light chat), the daily log gets three lines of small-talk and the compiler has nothing useful to compile.

Cole's rationale: speed + noise reduction + "compile.py can read the filesystem itself." But the compiler no longer gets any file paths — it doesn't know what to read.

#### Correct: summarize tool inputs, truncate tool results

One signal-bearing summary per tool:

- `[Edit] path` + truncated old/new line
- `[Write] path (N chars)` + content preview
- `[Bash] command`
- `[Read] path`
- tool results capped at 300 chars + `is_error` flag

Stays under the 10s hook timeout but preserves massive signal.

**Why:** Karpathy's pattern was designed for chat journals. For agentic workflows where work happens **inside** the tools, stripping tool calls is destructive.

#### Resolution

`session-end.py` always had the rich summarizer. `pre-compact.py` shipped with the lossy mapping until both hooks were unified through `hooks/_transcript.py` — same `extract_text` / `read_transcript` / `build_context` for both. Adding a new hook = drop a file, import from `_transcript`. The lossy shape is no longer reachable.

### Ollama structured output

#### `format: "json"` is not enough

- The model invents its own field names.
- It only guarantees valid JSON, not a valid schema.

#### Use a full JSON Schema via `format: {type: object, properties: {...}}`

- Constrained decoding at the token level.
- `enum` works (forces a string into a value list).
- `minLength` is **ignored** (empty strings get through).
- `required` ensures field presence, not content.
- **Item-level `type: object` is not always honored.** Observed in production: `compile.py`'s curiosity schema declared `gaps[].type = object` with `required: [topic, folder, account, rationale]`, but Ollama (gemma4:e4b) still returned `{"gaps": ["str", "str"]}` on at least one input — strings instead of objects. Consequence: `gap.get(...)` raised `AttributeError` and killed the whole curiosity pass. Fix: validate every parsed item with `isinstance(g, dict)` before treating it as one; log + drop non-conforming items.

**Workaround for non-empty fields:** define an `enum` covering all expected values.

**Defensive read pattern after `chat_schema`:** never assume the parsed structure matches the declared schema. Always shape-guard at the boundary — same principle as the `state.ingested[rel]` string-vs-dict gotcha further down. Constrained decoding is best-effort, not a contract.

#### Cache-buster needed at `temperature: 0`

Ollama caches responses for identical prompt + temp=0. Inject a timestamp (or other nonce) into the prompt to get fresh results between runs.

#### Vision API

Use the native endpoint (`/api/chat`), not the OpenAI-compatible one. Images go base64-encoded in `messages[].images[]`, not `image_url`. Resize to 512 px for 11 GB VRAM.

### Rate limits are hard to debug

#### Claude Agent SDK swallows stderr

`Command failed with exit code 1 — Check stderr output for details` — but stderr isn't accessible from the SDK. To see the real error, run the bundled CLI directly.

#### Claude Code has a 5 h rolling window (Opus)

Cascading failures after ~2 h of runtime usually mean the rate cap, not a crash. Handle with `--max-files N` and `--max-consecutive-failures N` flags in the script — abort instead of failing repeatedly.

#### Rate limits manifest as fast failures

Normal API calls take 10–60 s. Rate-limited calls fail in 2–5 s. The timing pattern is the giveaway.

### NAS connectivity: SMB > WebDAV > SSH

- **SSH** would bypass QTS shared-folder permissions (POSIX root) — security gone.
- **WebDAV** is HTTP overhead per file — bad for many small files.
- **SMB** has a persistent connection, native FS semantics, random access — best choice for level-by-level ingest.

Python client: `smbprotocol` (works everywhere, no `smbclient` CLI dependency).

### AGENTS.md > CLAUDE.md as the convention

`AGENTS.md` is tool-agnostic (Claude Code, Cursor, Aider, Codex all read it). `CLAUDE.md` is read only by Claude Code. Scripts that scan `CLAUDE.md` MUST also handle `AGENTS.md` — otherwise they miss the main doc on projects that adopted the newer convention.

### Artefact protection: archive, don't delete

Flush-context files used to be deleted on API failure → information lost. Now: on failure, move to `scripts/failed-flushes/`; a daily `retry-failed-flushes` piggyback retries them.

**Principle:** there must be **no gap in the chain between capture and persist**. Every stage has to be retry-safe.

### File-per-memory beats project-bundled memories

`sync-memories.py` writes EACH memory as its own raw source (`{project}__{memory_name}.md`), not bundled per project. Reason: hash-based compile-skip works per file. A single memory edit doesn't trigger recompilation of the whole project group.

### Don't delete files that look like temp/state without checking

There are several file types in this system that **look** like junk you can clean up but actually carry pending user work:

- `scripts/sessions/session-flush-*.md` — staged transcripts; deleted on successful flush, archived to `failed-flushes/` on failure. **A leftover here means flush.py crashed silently** before extraction or archiving — the content is real pending work.
- `scripts/sessions/flush-context-*.md` — same, written by the pre-compact hook.
- `scripts/state/*.json` — hash trackers, dedup windows, cooldowns. Deleting `state.json` forces re-compilation of all 100+ already-ingested files (~$1–2 in API calls + time).

**Rule:** before any `git rm` / `rm` / `mv` of these, cross-reference. For session-flush leftovers, check whether the session-id appears in `daily/*.md` (= already extracted, leftover is redundant) or only in `flush.log` (= flush.py crashed, real pending work).

**Recipe:**

```bash
for f in scripts/sessions/session-flush-*.md scripts/sessions/flush-context-*.md; do
  id=$(echo "$f" | sed -E 's/.*-(([0-9a-f-]+))-[0-9]+\.md/\1/')
  grep -q "$id" daily/*.md && echo "REDUNDANT $f" || echo "PENDING $f"
done
```

Anything `PENDING` → move to `scripts/sessions/failed-flushes/` (the retry-piggyback will reprocess them on its 24 h cycle), don't delete. Anything `REDUNDANT` → safe to keep or drop, no data risk either way.

**`git rm` is multi-system destructive.** When the source repo `git rm`s a tracked file, every cloned instance loses that file the next time `wiki update` pulls — silent cascade. If the file was a private staging artefact that was accidentally committed, treat the cleanup as a two-step: gitignore + rm only after verifying nothing pending is in it.

### `.gitignore`: inline `# comments` are NOT comments

#### What broke

`scripts/state/`, `scripts/logs/`, and `scripts/sessions/` were all listed in `.gitignore` but appeared as untracked in `git status`. `git check-ignore -v scripts/logs/flush.log` returned exit 1 (not ignored).

#### Why

The lines looked like:

```gitignore
scripts/state/      # *.json hash trackers, dedup, cooldowns
scripts/logs/       # *.log files
scripts/sessions/   # session-flush-*.md / flush-context-*.md staging + failed-flushes/
```

Git's gitignore syntax treats `#` as a comment marker **only at the start of a line**. Mid-line `#` is part of the pattern. So git was looking for a literal pattern `scripts/logs/       # *.log files` (with the trailing whitespace and comment) — which matches nothing on disk.

#### How to avoid

Move comments to their own lines:

```gitignore
# *.log files
scripts/logs/
```

#### Verify with `git check-ignore -v <path>`

It prints which `.gitignore` line matched (or exits non-zero if nothing did). Fast feedback loop for any rule that "should" match but doesn't.

### `Personal` config: depersonalized content via `${var}` templates

#### Why it exists

Several artefacts that ship in the repo (compile prompts, scan-email account map, scan-calendar work-keyword filter, schema enums in `compile.py`) used to hardcode personal data — email addresses, customer/partner names, IMAP server hostnames, mbox paths. That made the repo unsuitable for sharing and created write-read-symmetry violations (same data hardcoded in both a prompt and the compiler's schema enum, easy to drift).

#### Pattern

`personal:` section in `config.yaml` (gitignored, per-install) is the single source of truth. `wiki_config.py:Personal` exposes:

- `accounts: dict[str, dict]` — per-account `email`, `label`, `mbox_paths`, `filter_paths`, `imap_host`, `imap_user_env`, `imap_pass_env`, `has_procmail`
- `email_folders: list[{path, desc}]` — drives both the curiosity-prompt listing AND the schema enum in `compile.py` (one source, no drift)
- `project_examples`, `calendar_work_keywords`, `thunderbird_profile`

Prompts use the existing `${var}` substitution (e.g. `${email_folders_listing}`, `${primary_account}`). `config.example.yaml` ships empty defaults; consumers (compile, scan-email, scan-calendar, thunderbird-rules, execute-suggestions) handle absent values gracefully.

#### When adding a new personal-data dependency

If you find yourself about to commit an email address, customer name, hostname, or local-FS path to the repo — extend `Personal` instead and pull the value through `CONFIG.personal.*`.

### Single-source modules

Three internal modules consolidate cross-cutting concerns that used to be duplicated:

- **`scripts/ollama_client.py`** — every Ollama call goes through here (`chat`, `chat_schema`, `chat_vision`, `parse_json_lenient`, `is_reachable`). Owns the gotchas section above; callers don't reinvent fence-stripping or the `format` schema shape.
- **`scripts/flush_pipeline.py`** — staged-flush state machine (`stage`, `append_to_daily`, `mark_complete`, `archive_failure`, `pending`). The "no gap between capture and persist" invariant lives here. Hooks, `flush.py`, and `retry-failed-flushes.py` all go through it.
- **`hooks/_transcript.py`** — shared transcript walker + tool summarizer used by both `session-end.py` and `pre-compact.py` (see Karpathy/Cole resolution above).

If you're tempted to copy code out of one of these into a caller, that's a smell — extend the module instead.

### Procmail Webmail API: empty body deletes the config

The All-Inkl `kasserver` Webmail Procmail API endpoint is destructive when called with an empty body. POSTing `exec-pref-procmail-save` with `{}` does not return an error — it **silently overwrites the live procmail config with an empty rule set**.

Workaround: never call the save endpoint during exploration. Always read first, mutate the read result, then save. Keep a local backup before every save (`get_procmail_config()` → file with timestamp suffix).

Same principle generalizes: any API endpoint named `*save*`, `*write*`, `*set*`, `*update*` is a write surface. Treat it as destructive until proven idempotent.

---

## Obsidian + plugins gotchas (added during M003-S01)

### Fenced code blocks inside `<div>` HTML lose plugin post-processing

Obsidian (CommonMark spec) treats fenced code blocks inside raw `<div>` HTML wrappers as **raw-HTML context**. Markdown post-processors that target code-fence languages (Meta Bind for ` ```meta-bind-button`) DO NOT run there — the block falls through as plain `<code>` text.

**Asymmetric impact:** Dataviewjs uses a different post-processor pathway and IS unaffected. Charts inside `<div class="wiki-chart-grid">` work fine; Meta Bind buttons inside `<div class="wiki-button-row">` do not.

**Fix:** layout via `cssclasses: [wiki-dashboard]` frontmatter + scoped CSS. Never wrap meta-bind blocks in inline HTML.

### Dataview JS queries default off

Dataview ships with `enableDataviewJs: false` for security. Charts using `dataviewjs` blocks won't render until the operator toggles "Enable JavaScript Queries" in Dataview settings — or until you seed `templates/.obsidian/plugins/dataview/data.json` with `enableDataviewJs: true`.

### Chart.js defaults break on dark themes

Default Chart.js text/grid colors are dark gray → invisible on Obsidian's dark theme. Read Obsidian CSS vars (`--text-normal`, `--background-modifier-border`, `--color-blue/red/green/...`) at chart-creation time and pass to Chart.js options. Defaults in case a var is missing.

### `state.ingested[rel]` is a string, not a dict

`compile.py` writes `state["ingested"][rel] = file_hash(source)` — a string. Older code paths (e.g. `lint.py:check_stale_articles` pre-fix) read it as `.get("hash", "")` expecting a dict. Result: `AttributeError` that aborts the entire lint run unless wrapped.

**Defensive pattern:** `isinstance(stored, dict)` branch handles both shapes. **Plus:** wrap each lint check in `try/except` in the main loop so one crash doesn't kill the rest.

### Wiki seed must be additive on `community-plugins.json`

The plugin list might contain operator-added plugins the engine doesn't know about. Default seed mode does **jq union merge** (`jq -s '.[0] + .[1] | unique'`) — never drops entries. Other files (dashboard.md, AGENTS.md) skip-if-exists with `--force` to overwrite.

### Obsidian writes `.obsidian/*.json` from RAM — race-condition with `wiki seed`

`graph.json`, `workspace.json`, `appearance.json`, plugin `data.json` files are all serialized from Obsidian's in-memory state on view-changes / pane-saves / app-quit. If Obsidian is running while `wiki seed --force` deploys a new template, Obsidian's next save **clobbers the template** silently — the search field in `graph.json` survived once because reads happened before saves, but `colorGroups` got wiped to `[]`.

**Operator workflow when re-seeding Obsidian configs:**

1. Cmd+Q Obsidian (full quit, not just window close — background process keeps writing)
2. `wiki seed --force` (or selective re-deploy)
3. Reopen Obsidian

Engine perspective: any file under `templates/.obsidian/` that Obsidian also writes to is racing. Seeding is best-effort while the app is live.

### Graph View filter — `knowledge/index.md` and `knowledge/log.md` are excluded by template default

These two top-level files are flat-overview hubs (`index.md` is the auto-generated article table written by `compile.py`; `log.md` is the chronological roll-up). They link to every article by definition → in the Graph View they form a hairball where every node connects to both, dwarfing real semantic edges.

**Filter:** `templates/.obsidian/graph.json` ships `search: "path:knowledge -path:knowledge/index -path:knowledge/log"`. Exclusion works because both are top-level files (not folders) — there's no risk of accidentally hiding a `knowledge/index/*.md` subtree.

**Reports/Dashboard/Lint are already correct** — `WIKI_SUBDIRS` in `scripts/utils.py` only iterates `concepts/`, `connections/`, `qa/`, `people/`, `projects/`, `facts/`, so `list_wiki_articles()` excludes `index.md` / `log.md` from connection-counting, orphan-detection, and missing-backlink scans. The Graph View was the only surface that needed an explicit filter.

The single intentional exception: `lint.py:check_orphan_pages` reads `read_wiki_index()` and treats articles listed in `index.md` as "not orphan". That's by design — the auto-generated index is the canonical reachability list.

### `homepage` plugin needs binary install + config seed

Seeding `.obsidian/plugins/homepage/data.json` with `value: "dashboard"` and `openOnStartup: true` is necessary but not sufficient. The plugin **binary** must be installed via Settings → Community Plugins → Browse. Once binary lands, it reads our seeded config. Same for `obsidian-charts`, `obsidian-meta-bind-plugin`, `obsidian-tasks-plugin`, `obsidian-shellcommands`, `quickadd`, `heatmap-calendar`.

### macOS HFS+/APFS is case-insensitive

`Dashboard.md` and `dashboard.md` resolve to the same file on default macOS. Don't rename for casing — pick one (we use lowercase to match `install.sh`'s historic guard).

## Compiler / wiki-engine semantics (added during M003-S01)

### Folder = type, but `type:` frontmatter is also required

Knowledge articles live under `knowledge/<folder>/`. Pre-fix the folder was the ONLY signal of substrate-type; articles had no `type:` frontmatter. Now both must agree:

- `knowledge/concepts/`    → `type: concept`
- `knowledge/connections/` → `type: connection`
- `knowledge/qa/`          → `type: qa`
- `knowledge/people/`      → `type: person`
- `knowledge/projects/`    → `type: project`
- `knowledge/MOCs/`        → `type: moc`     (S04 — manual curation)
- `knowledge/facts/`       → `type: fact`    (hard-facts override system)

The compile prompt sets the field per folder; `lint.py:check_article_type` flags drift; `scripts/migrate_add_type.py` backfills legacy articles (cheap, no LLM).

### Hard-facts beat source claims (authority hierarchy in compile context)

The LLM compiler treats every source equally — a stale memo and a current decision both feed the same prompt. Without an authority layer, low-quality sources contaminate the wiki and stay there. Hard facts solve this by injecting an **operator-authored** override layer above sources.

`knowledge/facts/<slug>.md` carries `type: fact`. The compile + query prompts open with a "Hard facts (override anything in the source material)" block right after the system prompt — explicitly higher authority than `${agents_md}`, `${index_md}`, or any source. The Compile prompt instructs: "do NOT write contradicting claims; correct existing articles that contradict a fact."

Three orthogonal layers handle the lifecycle:

1. **Prevention** — `read_hard_facts()` in `scripts/utils.py` builds the prompt block; `compile.py` and `query.py` pass it as `${facts_md}`. New compiles honor every recorded fact.
2. **Detection** — `lint.py:check_facts_violations()` greps each fact's `negation_terms:` list (case-insensitive) across all non-facts knowledge files. The list is the lint signal, **not** the compile signal — the compiler reads the fact body verbatim and matches semantically; lint is the cheap structural backstop.
3. **Propagation** — `wiki correct apply <slug>` spawns Claude Agent SDK with `cwd=<vault-root>`, `acceptEdits`, full Read/Write/Edit/Glob/Grep/Bash tools. The agent walks `knowledge/` (edits + renames + wikilink fixes), prepends correction notes to `daily/`, and treats `raw/` as immutable. After success, `applied:` flips from `false` to an ISO timestamp. Per-fact `.bak.<ts>` snapshots before and after.

Statuses are policy hints, not enforcement: `negation` (false claim — strike), `disambiguation` (name conflict — rename + relink), `clarification` (factual fix — edit). Lint only acts on `negation_terms`; the agentic apply step honors all three because it reads the fact body as instructions.

`wiki correct add/list/remove/edit/path/apply` is the operator interface. Backups land next to the fact file as `.bak.YYYYMMDD-HHMMSS` on every write.

### Dashboard counts come from `_dashboard-stats.md`, not Dataview-on-state.json

`scripts/dashboard_stats.py` reads `state.json` + filesystem + cheap structural lint checks, then writes `<vault>/_dashboard-stats.md` with frontmatter (numerical counts) and a rendered Markdown callout (transcluded by Dashboard via `![[_dashboard-stats]]`).

`state.json` lives at `.wiki/state/state.json` — Obsidian/Dataview can't read it directly (dot-folder excluded). The cache file is the bridge. Refreshed synchronously after every `wiki flush`, plus manually via the Run > Refresh-stats button on the dashboard.

### Lint check_stale_articles fix preserves both schema shapes

`isinstance(stored, dict)` branch handles old `{hash: ..., compiled_at: ...}` dict shape and current bare-string. No migration needed for state.json — defensive read.

### Obsidian raw-HTML wrappers don't form a DOM hierarchy in reading mode

#### Symptom

Dashboard `## 📊 Vault stats` had four `<div>`-wrapped charts inside `<div class="wiki-chart-grid">…</div>`, with CSS `display: grid` on the wrapper. User reported "charts are still stacked vertically" — grid never engaged.

#### Root cause (two layers)

**Layer 1: snippet not enabled.** Engine seeded `wiki-dashboard.css` into `.obsidian/snippets/` but never wrote `.obsidian/appearance.json` with `enabledCssSnippets: ["wiki-dashboard"]`. Obsidian only loads snippets that are listed there. The CSS file sat on disk, untouched. Operator didn't toggle it manually because the README/dashboard.md mentioned snippet activation only as an aside.

**Layer 2: `<div>` wrappers don't nest in reading mode.** Even with the snippet loaded, the grid wouldn't have worked. Obsidian's reading-mode renderer wraps every top-level markdown block (heading, paragraph, code-fence, raw-HTML block) in its own `.el-X` container under `.markdown-preview-sizer`. Raw-HTML blocks separated by blank lines (CommonMark Type-6 termination) become independent siblings — `<div class="wiki-chart-grid">` ends up an empty wrapper, the inner `<div>`s are also empty wrappers, and the dataviewjs charts render as orphaned `.el-pre` siblings. CSS `display: grid` applies to an empty container; the charts have no grid parent.

This is the same gotcha that hit Meta Bind buttons — the post-processor doesn't run inside HTML blocks for Meta Bind, and the parent-child DOM relationship is broken for any wrapper-style layout.

#### Fix pattern

For grid layouts in Obsidian dashboards, do **not** rely on raw-HTML wrappers. Two reliable patterns:

1. **CSS-only via `cssclasses`** — works when each cell is its own `.block-language-X` and CSS targets siblings (Meta Bind buttons → inline-block via the snippet).
2. **JS-built grid in a single dataviewjs** — when cells need different content and a parent grid container, build the entire grid + cells in JS within one `dataviewjs` block. The container is created by `this.container.createDiv()` and its children are added by JS — a real DOM hierarchy that Obsidian's per-block wrapping never sees.

The chart grid uses pattern (2): `templates/dashboard.md` consolidates four formerly-separate dataviewjs blocks into one, builds `<div class="wiki-chart-grid">` with `Object.assign(grid.style, {display: "grid", …})` inline, and renders each chart into a `cell()` helper that creates a sized container.

#### Snippet auto-enablement

`templates/.obsidian/appearance.json` ships `{"enabledCssSnippets": ["wiki-dashboard"]}`. `lib/seed.sh:_merge_appearance_json()` unions our entry into the operator's existing list (preserving `cssTheme`, `theme`, etc.) — additive merge, never overwrites. Without this auto-enable step, every `wiki seed` left the snippet off and any cssclasses-driven CSS silently failed.

#### Diagnostic technique

Reading the rendered DOM directly is the only reliable signal. From a running Obsidian session: DevTools → Inspect the dashboard's stats section → confirm whether `.wiki-chart-grid` actually contains the chart elements as descendants or only sits as an empty sibling. CSS-Grid not applying isn't a styling bug; it's a DOM-shape bug.

**Verified:** after the fix, four charts render in a responsive 2-column grid (laptop) / 4-column grid (wide monitor), title + chart per cell, `auto-fit` driven, no snippet required for the grid layout itself.

#### Follow-up — three more gotchas surfaced after the first round

Reload of the live vault revealed the grid still rendered single-column and Meta Bind buttons still stacked. Three additional layers were biting:

**Readable Line Length caps the dashboard width.** Obsidian's "Readable line length" setting (default ON in reading + live preview) sets `--file-line-width: 700px` on the markdown sizer. With `auto-fit minmax(380px, 1fr)`, that container fits at most 1 column once a sidebar is open. Best practice (sourced from `forum.obsidian.md` Dashboard++ + readable-line-length threads): override the variable AND force the sizer wide:

```css
.wiki-dashboard {
  --file-line-width: 100%;
  --max-width: 100%;
}
.wiki-dashboard .markdown-preview-sizer,
.wiki-dashboard .cm-sizer,
.wiki-dashboard .cm-contentContainer {
  max-width: 100% !important;
  width: 100% !important;
}
```

Minimal Theme ships ready-made `max` / `wide` cssclasses that do this. Default theme doesn't — we do it ourselves under the dashboard's own `.wiki-dashboard` scope so it never affects regular notes.

**Meta Bind buttons stack because their `.el-pre` wrapper is block-level.** Obsidian wraps every code-fence in a `.el-pre` with `display: block`. Setting the BUTTON to `display: inline-block` doesn't help — the wrapper still breaks the line. Fix targets the wrapper via `:has()`:

```css
.wiki-dashboard .el-pre:has(.block-language-meta-bind-button) {
  display: inline-block;
  margin: 0 0.5rem 0.5rem 0;
  vertical-align: top;
}
```

`:has()` is supported by Electron's Chromium in Obsidian ≥ 1.4 (we ship for current Obsidian).

**Grid `minmax` was too wide.** `minmax(380px, 1fr)` only fits 2 columns at ≥ 760px container width. Lowered to `minmax(280px, 1fr)` so we get a smooth 1 → 2 → 3 → 4 column flow as the window widens with sidebar open / closed.

**Net pattern for Obsidian dashboards (LLM-wiki convention):**
1. Build the grid in JS (avoid raw-HTML wrappers — gotcha #3).
2. Add a `cssclasses` scope (`wiki-dashboard`) and a snippet that enables it.
3. In the snippet, **always** override `--file-line-width` + sizer `max-width` for the scope (Reading Line Length is on by default).
4. For inline button rows, target `.el-pre:has(.block-language-meta-bind-button)` not the button itself.
5. Auto-enable the snippet via `.obsidian/appearance.json` (additive merge in `lib/seed.sh`).

### Agent-task framework — prompt-as-config + region-marker auto-wiring

Three engine scripts (`compile.py`, `query.py`, `correct_apply.py`) each wrap one Claude Agent SDK call with a hard-coded prompt and CLI shape. M004 introduced a fourth pattern: **the task spec itself is data** (`prompts/agent_<id>.md` with YAML frontmatter declaring model + tools + permission + button + cwd), and a single generic runner (`scripts/agent_task.py`) reads it. New tasks ship as one markdown file — no engine code changes.

The frontmatter is parsed by `scripts/agent_spec.py:parse_spec()` into an `AgentSpec` dataclass. Required fields (`id`, `title`, `allowed_tools`) raise `SpecError` if missing. Tool names validated against the SDK's allowlist. `${today}` and `${now}` substitution baked in; operator can add more via `wiki agent <id> --var k=v`.

**Auto-wiring through `wiki seed`** combines two patterns we already had:

1. **jq additive merge** (same shape as `community-plugins.json` and `appearance.json`): every spec with a `button:` block contributes an entry under `shell_commands.agent-<id>` in `.obsidian/plugins/obsidian-shellcommands/data.json`. User's other shell commands stay untouched.
2. **Marker-based region replacement** (new pattern, lives in `scripts/agent_buttons.py:update_dashboard`): `<!-- agent-buttons:begin --> … <!-- agent-buttons:end -->` and `<!-- agent-button-defs:begin --> … <!-- agent-button-defs:end -->` define rewriteable regions in `templates/dashboard.md`. The seed regenerates contents from spec discovery; nothing outside the markers is touched. Idempotent.

This keeps the operator's editing surface a single `.md` file per task, while the engine stays untouched. The same pattern can be lifted to other auto-wired surfaces (e.g. piggyback registration, hook generators) if needed later.

**Why not bespoke per-task scripts** (rejected): we already had `correct_apply.py`, `compile.py`, `query.py`, and a per-feature trajectory ahead (`summarize-day`, `review-mocs`, `weekly-digest`, `extract-todos`, `cluster-orphans`). One more script per feature → script explosion. Pulling the SDK-spawn into one runner + spec files keeps engine code stable as the task catalogue grows.

**Why not pure plumbing without a concrete task** (rejected): empty framework with no users invites drift between spec format intent and actual usage. Shipping `summarize-day` alongside the framework forces the spec to handle a real case (Haiku model for cost, append-vs-replace logic in the prompt body, button auto-wiring) before the abstraction calcifies.
