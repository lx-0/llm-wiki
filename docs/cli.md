# CLI Reference

Operational layer for an LLM Wiki vault. The `.wiki/` directory is hidden from Obsidian's file tree by default (Obsidian ignores `.`-prefixed dirs).

## Contents

- [Quick start](#quick-start) — top-level commands at a glance
- [Subcommand cheat sheet](#subcommand-cheat-sheet) — every `wiki <subcommand>`
- [Setup wizard — what's asked](#setup-wizard--whats-asked) — the 5 questions
- [Config keys](#config-keys) — pointer to the full reference in [config.md](config.md)
- [Hook targets](#hook-targets) — which agents are wired, with what scope

## Quick start

```bash
./.wiki/wiki                  # interactive home screen — context-sensitive
                              #   suggestions ("3 files in inbox/ → process-inbox"),
                              #   quick actions, browse categories. Non-TTY callers
                              #   (CI, hooks, pipes) get `wiki help` instead.
./.wiki/wiki menu             # same home screen, forced regardless of TTY
./.wiki/wiki setup            # first-time: config wizard + hooks install
./.wiki/wiki status           # config + hooks + Ollama probe
./.wiki/wiki help             # top-level usage (printed verbatim, no prompts)
./.wiki/wiki config --help    # config subcommands
./.wiki/wiki hooks --help     # hooks subcommands
./.wiki/wiki update           # git pull + uv sync, preserves config.yaml
```

### Home-screen anatomy

Bare `wiki` runs `scripts/menu_context.py` to probe the vault (~150ms cold,
hard-capped at 500ms via `SIGALRM`) and renders four sections in order:

```
  wiki — lxw vault (commit 1852029)
  384 articles · last compile 4h ago · ollama ✓     ← (1) status one-liner

  ▸ Pending in your vault                            ← (2) ranked suggestions
      1) 3 files in inbox/             → wiki process-inbox
      2) 12 sources changed            → wiki compile

  ▸ Quick actions                                    ← (3) fixed shortcuts
      [q] query  [f] flush  [l] lint  [s] status

  ▸ Browse                                           ← (4) category sub-menus
      [c] collectors  [i] ingest  [k] knowledge ops
      [d] facts/takes [a] automation [g] setup
      [h] full help   [x] exit  (type /foo to filter all commands)

  Pick one:
```

**(1) Status one-liner** — three fields rendered when available:

| Field              | Source                                                 |
|--------------------|--------------------------------------------------------|
| `N articles`       | `find knowledge/ -name '*.md'` minus `index.md/log.md` |
| `last compile Nh ago` | humanized delta from `state.json["last_compile"]`   |
| `ollama ✓` / `✗`   | TCP-connect probe at `models.ollama_url` (150ms cap)   |

**(2) Pending suggestions** — seven probe signals, only non-zero rows
shown, sorted by priority. When all probes return zero the section
renders `✨ Nothing pending — vault is current.` instead.

| # | Signal                                          | Suggested command            |
|---|-------------------------------------------------|------------------------------|
| 1 | files in `inbox/`                               | `process-inbox`              |
| 2 | sources newer than last compile                 | `compile`                    |
| 3 | `raw/requests/*.json` with `status != done`     | `curiosity --run-oldest`     |
| 4 | `raw/suggestions/*.yaml` `status: approved`     | `suggestions`                |
| 5 | entity pages past `dream_cooldown_days`         | `dream --all-entities`       |
| 6 | today's `daily/sessions/<date>.md` missing      | `flush`                      |
| 7 | knowledge edits newer than newest lint report   | `lint --structural-only`     |

**(3) Quick actions** — `q` query / `f` flush / `l` lint (structural-only) /
`s` status. Letter or number both work.

**(4) Browse** — six category sub-menus (collectors / ingest / knowledge ops
/ facts & takes / automation / setup) cover the 30+ subcommands. Each
sub-menu uses inline letter shortcuts (`[l] list collectors`, `[r] run a
collector`, `[b] back`).

**Fuzzy filter** — typing `/<substring>` at the home prompt matches against
a hand-curated catalog of 49 commands (case-insensitive). One match
auto-dispatches; multiple opens a numbered picker. Catalog covers every
flag variant (`compile-all`, `compile-file`, `lint-structural`, all
OAuth flows, full `correct`/`take` lifecycles, all `curiosity` and
`suggestions` actions, hooks + skills + seed). Cost markers (`$`,
`$$`, `$$$`) appear in descriptions so the operator sees what a
one-keystroke match will actually charge.

Probe is pure-Python, no network beyond the Ollama TCP probe, no LLM. On
error the home screen renders the browse section only.

**Implementation:** `scripts/menu.py` owns the rendering + key handling via
`prompt_toolkit` (arrow keys, redraw, raw mode — all native). The bash
entry-point bare `wiki` / `wiki menu` does `exec uv run python scripts/menu.py`
when stdin/stdout are TTYs, and falls back to `cmd_help` otherwise. Menu
dispatches every action by shelling back to `wiki <subcommand>` — bash stays
the single source of truth for what each subcommand does. Reason for the
Python layer: the prior bash home screen trip-wired on bash-3.2 quirks once
per feature (no `${var,,}`, empty array under `set -u`, fractional `read -t`
unsupported). Background: `.ytstack/backlog/python-interactive-menu.md`.

**Health banner:** Above the status line, the menu renders every
critical + warning issue from `wiki doctor` (probes config + connectivity
+ pipeline). Operator-facing fix-hint inline with each issue. Info-only
issues stay out of the banner (live in `wiki doctor`). Per-issue render:

```
  ⚠ no project-scope hooks installed — session capture won't fire
      → wiki hooks install
```

## Agent-facing surfaces

Two JSON commands let agents (via the `use-llm-wiki` skill or directly)
read vault state programmatically without parsing pretty output:

```bash
./.wiki/wiki menu --json     # context-sensitive suggestions + status
./.wiki/wiki doctor --json   # full config/connectivity/pipeline health
./.wiki/wiki doctor --quick --json   # skip TCP + subprocess probes (~50ms)
```

`wiki menu --json` payload:

```json
{
  "status": {"articles": 384, "last_compile_ago": "4h", "ollama_reachable": true},
  "suggestions": [
    {"key": "1", "count": 3, "label": "3 files in inbox/",
     "cmd": "process-inbox", "priority": 1}
  ]
}
```

`wiki doctor --json` payload:

```json
{
  "vault": "lxw",
  "engine_revision": "abc1234",
  "summary": {"critical": 0, "warning": 1, "info": 1, "ok": 6},
  "checks": [
    {"id": "hooks-installed", "category": "config", "severity": "ok",
     "message": "hooks installed in project scope (claude, cursor)",
     "fix": null, "details": {"agents": ["claude", "cursor"]}}
  ]
}
```

Stable field names per check: `id`, `category`, `severity`, `message`,
`fix?`, `details?`. Severity is one of `critical | warning | info | ok`.
Exit code: `0` if no critical issues, `1` otherwise.

Agents pick a suggestion from `wiki menu --json` then dispatch via the
regular bash subcommand (e.g. `wiki compile`). They never ask the menu
to dispatch — bash stays single source of truth.

## Subcommand cheat sheet

Grouped by purpose. Run `wiki <cmd> --help` for the full per-command help block.

### Lifecycle

| Command | What it does |
|---|---|
| `wiki` | interactive home screen (TTY only) — context-sensitive suggestions + browse menu. Non-TTY → `wiki help`. |
| `wiki menu` | same home screen, forced regardless of TTY. |
| `wiki menu --json` | emit suggestions + status payload as JSON, exit. Agent-facing read of "what's pending". |
| `wiki doctor [--quick] [--json]` | vault-health audit: config + connectivity + pipeline checks. `--quick` skips network + subprocess probes (~50ms). `--json` for agents. Exit code 1 if any critical issue. |
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
| `wiki skills install --global` | also link global-eligible skills (`use-llm-wiki`) into `~/.claude/skills/` and register the vault in `~/.config/llm-wiki/vaults`. Sets `skills.global_install: true` so the opt-in persists across `wiki update`. `--no-global` is the inverse. |
| `wiki skills uninstall` | remove engine-owned symlinks (foreign skill entries kept untouched) |
| `wiki skills uninstall --global` | also remove this vault's global symlinks, deregister it, and set `skills.global_install: false` |
| `wiki skills sync` | install missing + prune stale (auto-called by `wiki update`); also refreshes global symlinks when `skills.global_install` is on |
| `wiki skills status` | per-skill `linked` / `collision` / `missing` table, plus a GLOBAL section (opt-in state, global link state, registered vaults) |

### Content pipeline

| Command | What it does |
|---|---|
| `wiki compile` | run `compile.py` against sources whose hash changed since last run (LLM cost via `models.compile_model`). Refreshes dashboard counts. |
| `wiki compile --all` | force-recompile every source under `raw/` + `daily/`. |
| `wiki compile --file PATH` | compile a single file (path relative to vault root). |
| `wiki flush` | manual flush — capture current Claude Code session transcript into `daily/YYYY-MM-DD/sessions.md` (post-2026-05-15 rollup arc; normally automatic via SessionEnd hook). After `compile_after_hour` triggers compile + piggybacks. |
| `wiki agent daily-digest --var date=YYYY-MM-DD` | run the `daily-digest` agent: read all `daily/<date>/*.md` per-source captures and write a ≤500-word distillation into `daily/<date>.md`. Also runs once-daily as the `daily_digest_yesterday` piggyback. |
| `wiki lint` | full health check — structural + LLM contradiction sweep ($ cost). Report → `.wiki/reports/lint-YYYY-MM-DD.md`. |
| `wiki lint --structural-only` | cheap, no-LLM lint — 8 checks (`broken_links`, `orphan_pages`, `orphan_sources`, `stale_articles`, `missing_backlinks`, `article_type`, `sparse_articles`, `facts_violations`). Used by piggyback. |
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
| `wiki collect email` | sweep configured mailboxes — output to `raw/notes/email/<account>-<date>.md`. Reads accounts from `personal.accounts.*`; secrets from `.claude/.env`. |
| `wiki collect jamie` | pull meetings from the Jamie AI API into `raw/transcripts/jamie/<date>--<slug>--<id>.md`. Multi-tenant: per-account `jamie:` sub-block under `personal.accounts.<id>` with `kind: jamie-api`; api key read from the env var named in `api_key_env`. Auto-runs as piggyback every 6 h. |
| `wiki collect gmeet` | export Google Meet / Gemini transcript+notes Docs from the Drive "Meet Recordings" folder into `raw/transcripts/gmeet/<date>--<slug>--<meeting-key>.md`. Multi-tenant: per-account `gmeet:` sub-block under `personal.accounts.<id>` with `kind: gmeet-api`; one-time OAuth via `wiki gmeet-auth <id>`. Auto-runs as piggyback every 6 h. |
| `wiki collect calendar` | pull Google Calendar events into one per-date markdown file at `raw/notes/calendar/<YYYY-MM-DD>.md` (event_count / meeting_hours / focus_hours / people / event_ids in frontmatter; per-event body block with Calendar / Attendees / Location / Recurring / Transcript / Event ID). Recurring-event series collapse to `knowledge/concepts/<slug>.md`. Same-date title-slug match cross-links gmeet+jamie transcripts. Multi-tenant: per-account `calendar:` sub-block under `personal.accounts.<id>` with `kind: google-calendar`; one-time OAuth via `wiki calendar-auth <id>`. `--incremental` uses the per-calendar `updatedMin` watermark from `state/calendar-state.json`. Auto-runs as piggyback every 6 h. |
| `wiki collect voice` | folder-watch `personal.voice_inbox` for `.txt`/`.md` dictation transcripts; ingest into `raw/voice/voice-<date>-<HHMM>-<slug>.md`, archive source under `<voice_inbox>/.processed/`. Mobile-primary path: iOS Shortcuts → iCloud Drive folder → Mac inbox. Auto-runs as piggyback every 1 h. See `docs/setup-voice.md`. |
| `wiki gmail-auth <account-id>` | one-time OAuth bootstrap for a Gmail account-id. Reads `.claude/gmail-oauth-client.json`, runs local-loopback consent, persists token to `.wiki/state/gmail-token-<id>.json`. |
| `wiki gmeet-auth <account-id>` | one-time OAuth bootstrap for a Google Meet / Drive account-id (scope `drive.meet.readonly`). Reads `.claude/google-oauth-client.json` (falls back to `gmail-oauth-client.json`), persists token to `.wiki/state/gmeet-token-<id>.json`. |
| `wiki calendar-auth <account-id>` | one-time OAuth bootstrap for a Google Calendar account-id (scope `calendar.readonly`). Same OAuth client file as gmeet; persists token to `.wiki/state/calendar-token-<id>.json`. |
| `wiki ingest-youtube --url URL [flags]` | ingest a single video or a playlist. Output to `raw/notes/youtube/`. |
| `wiki ingest-youtube --inbox PATH [flags]` | parse a markdown file with YouTube URLs (bare / markdown-link / shortlink, optional inline `tier: N` directive). |
|  | Shared flags: `--tier {0,1,2,3}` (default 1; 0=metadata, 1=+transcript, 2=+comments, 3=+visual via gemma4@kcma), `--limit N` (cap playlist/inbox to first N), `--dry-run`, `--no-skip` (re-ingest videos that already exist). |
| `wiki ingest-html PATH-OR-URL [--mode content\|visual\|both]` | convert HTML (file or URL) into raw/. `content` mode runs html2text → `raw/articles/`; `visual` mode screenshots via Playwright then a Vision-LLM describes layout → `raw/notes/`; `both` runs them back-to-back. Auto-invoked by `wiki process-inbox` for `.html` files in inbox. |
| `wiki process-inbox [flags]` | walk `<vault>/inbox/`, classify each file via local Ollama, move to matching `raw/<type>/`, then compile. Flags: `--no-compile` (route only), `--dry-run` (show plan), `--model MODEL` (override classifier model). HTML files are delegated to `wiki ingest-html`. |
| `wiki suggestions [flags]` | review + execute YAML optimization suggestions in `raw/suggestions/`. Modes: `--list` (overview), `--review ID` (interactive), `--approve ID N` / `--reject ID N` (per-action), `--dry-run` (preview approved), no-args (execute). IMAP backend uses `.claude/.env` credentials. |
| `wiki curiosity [flags]` | process raw/requests/ deep-scan requests (curiosity-loop consumer). Modes: `--list` (overview), `--run-oldest` (single), `--run SLUG` (substring match), `--run-all` (all pending), `--clear-done` (cleanup), `--dry-run` (plan only). Email backend uses the configured Mailbox adapters via `scan_deep`. Auto-runs as 24h piggyback (`curiosity_followup`). |

### Producers (post-compile derivative material)

Producers consume a *compiled* source file under `raw/` and emit derived material — suggestion notes, knowledge-gap requests, third-party belief extractions. They run automatically as a serial post-pass after each successful compile (`compile.py:main()` → `compile_stages.post_passes.run_post_passes`). The `wiki produce` CLI is for manual re-run / debug / replay against a single source.

| Command | What it does |
|---|---|
| `wiki produce --list` | enumerate registered Producers with their declared gates (`SPEC.enabled_config_key`, `SPEC.source_glob_config_key`) |
| `wiki produce <name> <source>` | run one Producer on one source path; gate evaluation + dispatch via `producers.orchestrate.evaluate_and_run`. Exit code 1 on `failed`. |

Registered Producers (run order = registration order):

| Name | Enabled key | Source-glob key | What it emits |
|---|---|---|---|
| `suggestions` | (always) | `features.suggestions_source_globs` (default `["raw/email/*.md"]`) | `raw/suggestions/<id>.yaml` — pattern-driven email-action proposals (consumed by `wiki suggestions`) |
| `curiosity` | `features.curiosity_loop` | (any source) | `raw/requests/request-<slug>-<date>.json` — knowledge-gap requests (consumed by `wiki curiosity`) |
| `takes` | `features.extract_takes` | `limits.extract_takes_source_globs` | `knowledge/people/<slug>.md` `## Takes` blocks — third-party beliefs/claims extracted from meeting + email substrate |

### Agentic tasks

| Command | What it does |
|---|---|
| `wiki agent --list` | list registered tasks (one per `prompts/agents/<id>.md`) |
| `wiki agent <id>` | spawn Claude Agent SDK with the model / `allowed_tools` / `permission_mode` / `max_turns` / `cwd` declared in the task's frontmatter. Result logged to `.wiki/logs/agent-<id>-<ts>.log`; on success the prompt's frontmatter gets `last_run: <iso-ts>` written back. |
| `wiki agent <id> --dry-run` | resolve + print the spec without spawning |
| `wiki agent <id> --var key=value` | substitute `${key}` in the prompt body (repeatable) |

### Operator-invoked one-shot scripts (`uv run python scripts/<name>.py`)

These scripts are not exposed via `wiki <cmd>` — they're explicit one-shots run from inside `.wiki/` (use `cd .wiki/` or pass paths absolute):

| Script | What it does |
|---|---|
| `migrate_daily_to_rollup.py --vault <path> [--dry-run]` | One-shot migration for vaults installed before the 2026-05-15 `daily/`-as-rollup arc. **Copies** (not moves) each flat `daily/<date>.md` into `daily/<date>/sessions.md`. Idempotent re-runs are no-ops. Originals stay in place until `cleanup_legacy_daily_roots.py` is invoked. |
| `backfill_daily_rollup.py --vault <path> [--source {health,voice,meetings,all}] [--dry-run]` | One-shot: walk existing substrate files in `raw/notes/health/`, `raw/voice/`, `raw/transcripts/{jamie,gmeet}/` and write per-day rollup one-liners to `daily/<date>/<source>.md`. Required after migration to backfill historical substrate that pre-dated the Phase 2 collector wiring. Idempotent (exact-line skip). |
| `cleanup_legacy_daily_roots.py --vault <path> [--dry-run]` | Removes legacy flat `daily/<date>.md` files after verifying byte-identical match against `daily/<date>/sessions.md`. Refuses on content divergence, on `type: daily-digest` frontmatter (real digest), and on today's date. |
| `daily_digest_runner.py --date {today,yesterday,YYYY-MM-DD}` | Wrapper invoked by the `daily_digest_yesterday` piggyback. Short-circuits if no `daily/<date>/` subfolder exists, else shells out to `wiki agent daily-digest --var date=<iso>`. |

## Setup wizard — what's asked

The 5 questions, in order:

1. **Ollama base URL** — probed live; if unreachable the next question gets a warning.
2. **Compile model** — `claude-opus-4-7` / `claude-sonnet-4-6` / `claude-haiku-4-5`. Used by `compile.py` and `retry-failed-flushes.py`.
3. **Auto-compile starts at hour** (`0`–`23`, local time) — `scheduling.compile_after_hour`.
4. **Procmail execution** (default OFF) — only enable if `suggestions/cli.py` should call a webmail-procmail provider API.
5. **Local-LLM features** (curiosity loop + vision screenshots, bundled) — only offered when Ollama probed successfully.

Re-run anytime via `./.wiki/wiki config wizard`.

## Config keys

Full reference with defaults, grouped tables, and the `personal.accounts` schema lives in **[`docs/config.md`](config.md)**. Quick pointers:

- `./.wiki/wiki config get KEY` / `set KEY VALUE` / `keys` / `path` — runtime introspection
- `./.wiki/wiki config wizard` — re-run the 5-question setup
- Secrets go in `<vault>/.claude/.env` (loaded automatically at import; see [config.md § Secrets](config.md#secrets--claudeenv))

Run `./.wiki/wiki config keys` for the live enumeration of every settable leaf.

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
