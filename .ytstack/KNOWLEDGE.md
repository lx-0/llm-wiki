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

**Workaround for non-empty fields:** define an `enum` covering all expected values.

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
