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

| Command | What it does |
|---|---|
| `wiki` | interactive top-level menu |
| `wiki setup [--help]` | first-time wizard (5 questions) + hook install |
| `wiki status` | config summary, hook install table, Ollama probe |
| `wiki update` | `git pull` engine + `uv sync`; never touches `config.yaml` or `.venv/` content |
| `wiki config` | interactive editor — pick section → key → value |
| `wiki config get KEY` | print one value |
| `wiki config set KEY VALUE` | write back to `config.yaml` |
| `wiki config keys` | list every settable key (dot-notation) |
| `wiki config path` | absolute path to `config.yaml` |
| `wiki config wizard` | re-run the 5-question wizard |
| `wiki config status` | summary table |
| `wiki hooks install` | install into selected agents (claude / codex / gemini / cursor) |
| `wiki hooks uninstall` | remove wiki-managed hooks |
| `wiki hooks status` | install table per agent / scope |

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
piggybacks.sync_memories.{enabled, cooldown_hours}
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
