# CLI Reference

Operational layer for an LLM Wiki vault. The `.wiki/` directory is hidden from Obsidian's file tree by default (Obsidian ignores `.`-prefixed dirs).

## Contents

- [Quick start](#quick-start) — top-level commands at a glance
- [Subcommand cheat sheet](#subcommand-cheat-sheet) — every `wiki <subcommand>`
- [Setup wizard — what's asked](#setup-wizard--whats-asked) — the 5 questions
- [Config keys](#config-keys) — every settable key in `config.yaml`
- [Hook targets](#hook-targets) — which agents are wired, with what scope

## Quick start

```bash
./.wiki/wiki                  # interactive top-level menu
./.wiki/wiki setup            # first-time: config wizard + hooks install
./.wiki/wiki status           # config + hooks + Ollama probe
./.wiki/wiki help             # top-level usage
./.wiki/wiki config --help    # config subcommands
./.wiki/wiki hooks --help     # hooks subcommands
./.wiki/wiki update           # git pull + uv sync, preserves config.yaml
```

## Subcommand cheat sheet

Grouped by purpose. Run `wiki <cmd> --help` for the full per-command help block.

### Lifecycle

| Command | What it does |
|---|---|
| `wiki` | interactive top-level menu |
| `wiki setup [--help]` | first-time wizard (5 questions) + hook install |
| `wiki status` | config summary, hook install table, Ollama probe |
| `wiki update [--no-skills]` | `git pull --ff-only` the engine checkout + sync skill symlinks; never touches `config.yaml` or `.venv/` content. `--no-skills` skips the skill sync step. |
| `wiki seed` | additive: drop in missing vault templates (`AGENTS.md`, `dashboard.md`, `.obsidian/*.json`, plugin `data.json`); merge `community-plugins.json` without dropping yours. |
| `wiki seed --force` | overwrite existing vault templates with engine versions (discards your edits to dashboard/AGENTS/`.obsidian`). |
| `wiki version` | print engine git revision + tag + origin URL. |

### Config

| Command | What it does |
|---|---|
| `wiki config` | interactive editor — pick section → key → value |
| `wiki config get KEY` | print one value |
| `wiki config set KEY VALUE` | write back to `config.yaml` |
| `wiki config keys` | list every settable key (dot-notation) |
| `wiki config path` | absolute path to `config.yaml` |
| `wiki config wizard` | re-run the 5-question wizard |
| `wiki config status` | summary table |

### Hooks & skills

| Command | What it does |
|---|---|
| `wiki hooks install` | install into selected agents (claude / codex / gemini / cursor) |
| `wiki hooks uninstall` | remove wiki-managed hooks |
| `wiki hooks status` | install table per agent / scope |
| `wiki skills install` | symlink missing engine skills into `<vault>/.claude/skills/` |
| `wiki skills uninstall` | remove engine-owned symlinks (foreign skill entries kept untouched) |
| `wiki skills sync` | install missing + prune stale (auto-called by `wiki update`) |
| `wiki skills status` | per-skill `linked` / `collision` / `missing` table |

### Content pipeline

| Command | What it does |
|---|---|
| `wiki compile` | run `compile.py` against sources whose hash changed since last run (LLM cost via `models.compile_model`). Refreshes dashboard counts. |
| `wiki compile --all` | force-recompile every source under `raw/` + `daily/`. |
| `wiki compile --file PATH` | compile a single file (path relative to vault root). |
| `wiki flush` | manual flush — capture current Claude Code session transcript into `daily/YYYY-MM-DD.md` (normally automatic via SessionEnd hook). After `compile_after_hour` triggers compile + piggybacks. |
| `wiki lint` | full health check — structural + LLM contradiction sweep ($ cost). Report → `.wiki/reports/lint-YYYY-MM-DD.md`. |
| `wiki lint --structural-only` | cheap, no-LLM lint (`broken_links`, `orphan_pages`, `orphan_sources`, `stale_articles`, `missing_backlinks`, `article_type`, `sparse_articles`). Used by piggyback. |
| `wiki query "QUESTION"` | ask the knowledge base — picks relevant articles via `knowledge/index.md`, answers via configured query model (LLM cost). |
| `wiki review-wiki` | per-article quality-score sweep via local Ollama ($0). Output → `.wiki/reports/review-YYYY-MM-DD.md`. Runs as weekly piggyback by default. |

### Hard facts (`correct`)

| Command | What it does |
|---|---|
| `wiki correct add "TITLE" "TRUTH" [flags]` | record a hard fact at `knowledge/facts/<slug>.md` — overrides sources at compile + query. Flags: `--status negation\|disambiguation\|clarification` (default `negation`), `--term "exact substring"` (repeatable; lint greps these), `--slug SLUG` (override auto-derived), `--force` (overwrite existing). |
| `wiki correct list` | list recorded hard facts |
| `wiki correct remove SLUG` / `edit SLUG` / `path SLUG` | manage individual facts (`.bak.<ts>` kept on remove/edit) |
| `wiki correct apply SLUG [--dry-run]` | spawn Claude Agent SDK over the vault to propagate the correction (edits `knowledge/`, annotates `daily/`, leaves `raw/` immutable). |

### Collectors & ingest

| Command | What it does |
|---|---|
| `wiki collect --list` | list registered Collectors with their `SPEC` |
| `wiki collect <name> [flags]` | run one Collector. Flags: `--dry-run` (log without writing), `--incremental` (delta-only when supported), `--account ID` (restrict to one account, where applicable). |
| `wiki gmail-auth <account-id>` | one-time OAuth bootstrap for a Gmail account-id. Reads `.claude/gmail-oauth-client.json`, runs local-loopback consent, persists token to `.wiki/state/gmail-token-<id>.json`. |
| `wiki ingest-youtube --url URL [flags]` | ingest a single video or a playlist. Output to `raw/notes/youtube/`. |
| `wiki ingest-youtube --inbox PATH [flags]` | parse a markdown file with YouTube URLs (bare / markdown-link / shortlink, optional inline `tier: N` directive). |
|  | Shared flags: `--tier {0,1,2,3}` (default 1; 0=metadata, 1=+transcript, 2=+comments, 3=+visual via gemma4@kcma), `--limit N` (cap playlist/inbox to first N), `--dry-run`, `--no-skip` (re-ingest videos that already exist). |

### Agentic tasks

| Command | What it does |
|---|---|
| `wiki agent --list` | list registered tasks (one per `prompts/agent_<id>.md`) |
| `wiki agent <id>` | spawn Claude Agent SDK with the model / `allowed_tools` / `permission_mode` / `max_turns` / `cwd` declared in the task's frontmatter. Result logged to `.wiki/logs/agent-<id>-<ts>.log`; on success the prompt's frontmatter gets `last_run: <iso-ts>` written back. |
| `wiki agent <id> --dry-run` | resolve + print the spec without spawning |
| `wiki agent <id> --var key=value` | substitute `${key}` in the prompt body (repeatable) |

## Setup wizard — what's asked

The 5 questions, in order:

1. **Ollama base URL** — probed live; if unreachable the next question gets a warning.
2. **Compile model** — `claude-opus-4-7` / `claude-sonnet-4-6` / `claude-haiku-4-5`. Used by `compile.py` and `retry-failed-flushes.py`.
3. **Auto-compile starts at hour** (`0`–`23`, local time) — `scheduling.compile_after_hour`.
4. **Procmail execution** (default OFF) — only enable if `execute-suggestions.py` should call a webmail-procmail provider API.
5. **Local-LLM features** (curiosity loop + vision screenshots, bundled) — only offered when Ollama probed successfully.

Re-run anytime via `./.wiki/wiki config wizard`.

## Config keys

All in `.wiki/config.yaml`, dot-notation:

```text
scheduling.compile_after_hour          0–23 (default 18)
scheduling.dedup_window_seconds        seconds (default 60)

models.compile_model                   claude-opus-4-7 | claude-sonnet-4-6 | claude-haiku-4-5
models.ollama_url                      e.g. http://localhost:11434
models.vision_model                    e.g. gemma4:e4b
models.curiosity_model                 e.g. gemma4:e4b
models.classify_model                  e.g. gemma4:e4b

features.curiosity_loop                bool — gap detection after compile
features.vision_screenshots            bool — local vision OCR for screenshots
features.procmail_execution            bool — webmail Procmail API calls (default OFF)
features.clippings_sweep               bool — pre-compile lift of <vault>/Clippings/

limits.compile_max_files               int — per-run cap (rate-limit guard)
limits.compile_max_consecutive_failures int — abort after N back-to-back failures
limits.flush_max_retries               int
limits.flush_retry_delay_seconds       int
limits.screenshot_resize_width         px
limits.screenshot_timeout_seconds      seconds
limits.youtube_max_frames              int — Tier-3 cap frames per video (default 30)
limits.youtube_max_duration_s          int — Tier-3: skip videos longer than this (default 10800 = 3h)
limits.youtube_frame_resize_width      px — ffmpeg downscale before vision model (default 512)
limits.youtube_vision_timeout_s        seconds — per-frame ollama timeout (default 90)
limits.youtube_aggregate_timeout_s     seconds — final-synthesis ollama timeout (default 300)
limits.curiosity_max_gaps              int — max requests per compile
limits.curiosity_min_source_chars      int — skip curiosity for tiny sources
limits.sparse_threshold_words          int — lint warns under this word count

# Recurring tasks spawned at session-end after flush.
piggybacks.email_incremental.{enabled, cooldown_hours}
piggybacks.lint_structural.{enabled, cooldown_hours}
piggybacks.review_wiki.{enabled, cooldown_hours}
piggybacks.optimize_claude_md.{enabled, cooldown_hours}
piggybacks.scan_screenshots.{enabled, cooldown_hours}
piggybacks.follow_requests.{enabled, cooldown_hours, max_per_run}
piggybacks.sync_memories.{enabled, cooldown_hours}    # default OFF (phase-out, 2026-05-04)
piggybacks.retry_failed_flushes.{enabled, cooldown_hours, max_per_run}

graph_view.mode                        knowledge-only | full-vault | sources-only | custom
graph_view.custom_search               obsidian search string (when mode=custom)

# Per-instance personal data — drives compile prompts, scan-email, scan-calendar,
# thunderbird-rules, execute-suggestions. Lives in config.yaml only (gitignored);
# config.example.yaml ships empty defaults.
personal.primary_account               account-id used as default in prompts + fallback in compile.py
personal.thunderbird_profile           absolute path; empty disables scan-email + thunderbird-rules
personal.stg_backup_dir                Firefox Simple Tab Groups backup dir (drives scan-tabs)
personal.accounts.<id>.email           full address (used in prompts + Webmail login)
personal.accounts.<id>.label           display label for scan-email reports
personal.accounts.<id>.mbox_paths      list of paths under thunderbird_profile (scan-email)
personal.accounts.<id>.filter_paths    list of paths to msgFilterRules.dat (thunderbird-rules)
personal.accounts.<id>.imap_host       IMAP hostname (thunderbird-rules)
personal.accounts.<id>.imap_user_env   env var name for IMAP user
personal.accounts.<id>.imap_pass_env   env var name for IMAP password
personal.accounts.<id>.has_procmail    bool — account exposes Webmail Procmail API
personal.email_folders[]               { path, desc } — drives compile_curiosity prompt + schema enum
personal.project_examples              list[str] — examples in scan_screenshots vision prompt
personal.calendar_work_keywords        list[str] — substrings marking work events in scan-calendar
```

Run `./.wiki/wiki config keys` for the live, full list.

## Hook targets

| Agent | Config file | SessionStart | SessionEnd | PreCompact |
|---|---|---|---|---|
| claude | `.claude/settings.json` | ✓ | ✓ | ✓ |
| codex | `.codex/hooks.json` | ✓ | Stop | — |
| gemini | `.gemini/settings.json` | ✓ | ✓ | PreCompress |
| cursor | `.cursor/hooks.json` | ✓ | ✓ | ✓ |

Install scope:

- **user** (recommended, wizard default) — `~/<.agent>/...` — hooks fire for every agent session regardless of CWD. This is the right scope for llm-wiki's purpose: capture sessions from every project the operator works in, not only sessions launched with CWD = vault root. Generated commands use absolute paths so they resolve correctly from any working directory.
- **project** — `<repo>/<.agent>/...` — hooks fire only when the agent CLI launches with CWD = vault root. Useful if you intentionally want to capture only in-vault work.

Not supported: **pi** (TS-only modules), **opencode** (no native hooks yet, [issue #5409](https://github.com/sst/opencode/issues/5409)).
