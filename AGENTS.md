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

A vault that uses this tooling has three layers:

1. **`raw/`** — curated sources (LLM reads, never writes). Top-level subfolders: `articles/`, `papers/`, `notes/`, `transcripts/`, `audio/`, `requests/`, `suggestions/`. Scanner output lives in nested per-scanner folders: `raw/notes/email/<account>-<date>.md` (scan-email full sweep) + `raw/notes/email/<account>-delta-<ts>.md` (scan-email incremental piggyback — only mail newer than the per-account watermark in `.wiki/state/email-state.json`), `raw/notes/calendar/`, `raw/notes/browser/`, `raw/notes/screenshots/screenshots-<slug>.md` (batch reports) + `raw/notes/screenshots/thumb/<file>.png` (384px previews; original PNGs stay in `~/Screenshots/`, never copied; canonical analysis sidecar lives at `~/Screenshots/<file>.md`), `raw/notes/tabs/`, `raw/notes/youtube/<channel>--<title>--<vid>.md` (scan-youtube — video metadata + transcript + comments + optional gemma4 visual analysis, single-file markdown), `raw/transcripts/jamie/<date>--<slug>--<short-id>.md` (collectors/jamie.py — pulls meetings from the Jamie AI tRPC API; summary + speaker-diarised transcript + action-items in one file).
2. **`daily/`** — auto-captured Claude Code session logs (immutable).
3. **`knowledge/`** — LLM-compiled wiki articles (LLM owns, human reads). Subfolders: `concepts/`, `connections/`, `people/`, `projects/`, `qa/`, `facts/` (the last is human-owned via `wiki correct` — hard facts that override anything in raw/daily sources).

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
│   │   ├── config.py           ← path constants (computed once, used everywhere)
│   │   ├── wiki_config.py      ← config dataclass + get/set/keys CLI (incl. `Personal`)
│   │   ├── prompts.py          ← prompt template loader (${var} substitution)
│   │   ├── ollama_client.py    ← single Ollama transport (chat / chat_schema / chat_vision)
│   │   ├── sdk_helpers.py      ← StderrCapture + log_sdk_failure for Claude Agent SDK calls
│   │   ├── utils.py            ← shared helpers (article listing, JSON state, history)
│   │   ├── agent_spec.py       ← agent-task spec parser (prompts/agent_*.md → AgentSpec)
│   │   └── flush_pipeline.py   ← staged-flush state machine (stage/commit/archive/pending)
│   ├── collectors/         ← substrate→raw/ writers (Registry + scan-* CLIs + dispatcher)
│   │   ├── base.py             ← Collector Protocol, SPEC, Registry
│   │   ├── cli.py              ← `wiki collect` dispatcher (Registry lookup + run-one)
│   │   ├── email_collector.py  ← email collector (renamed from email.py to avoid stdlib shadow)
│   │   ├── jamie.py            ← Jamie AI meeting-notetaker
│   │   ├── scan_tabs.py        ← TabsCollector (Registry; migrated 2026-05-13)
│   │   ├── scan_calendar.py    ← CalendarCollector (Registry; migrated 2026-05-14)
│   │   ├── scan_browser.py     ← BrowserCollector (Registry; migrated 2026-05-14)
│   │   ├── scan_screenshots.py ← ScreenshotsCollector (Registry, piggyback; migrated 2026-05-14)
│   │   └── scan-youtube.py     ← Legacy CLI (port pending — tier system + CLI flags)
│   ├── facts/              ← hard-fact subsystem (knowledge/facts/<slug>.md consumers)
│   │   ├── correct.py          ← CRUD CLI: add/list/remove/edit/path
│   │   └── correct_apply.py    ← agent-driven propagation across vault
│   ├── suggestions/        ← email-suggestion pipeline (raw/suggestions/ producer + executor)
│   │   ├── producer.py         ← maybe_generate_suggestions (called from compile.py)
│   │   ├── cli.py              ← interactive approve/review/reject/execute
│   │   └── backends/imap.py    ← IMAP move/tag/set-flags executor
│   ├── curiosity/          ← gap-detection loop (raw/requests/ producer + consumer)
│   │   ├── producer.py         ← maybe_generate_curiosity_requests (called from compile.py)
│   │   ├── cli.py              ← wiki curiosity: list / run-oldest / run / run-all / clear-done
│   │   └── backends/email.py   ← email-deep-scan: scan_deep via Mailbox-adapter → raw/notes/email/deep-*.md
│   ├── dashboard/          ← Obsidian dashboard helpers
│   │   ├── dashboard_stats.py  ← _dashboard-stats.md generator (post-flush refresh)
│   │   ├── dashboard_lint.py   ← _dashboard-lint.md generator (post-flush refresh)
│   │   ├── agent_buttons.py    ← agent-button discovery + dashboard.md rewriter
│   │   └── inject_daily_button.py ← idempotent Summarize-button injection into daily/*.md
│   ├── migrations/         ← one-shot schema/data migrations (not active CLI surface)
│   ├── adapters/           ← MailboxReader implementations (gmail, thunderbird, allinkl)
│   ├── domain/             ← pure domain types (mail message, etc.)
│   ├── compile.py          ← Claude Agent SDK compiler (raw/daily → knowledge/)
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

1. Extend the matching dataclass in `scripts/core/wiki_config.py`.
2. Document the default in `config.example.yaml` with a comment.
3. Document it in `docs/config.md` (the grouped reference).
4. Replace the hardcoded constant in the script with `CONFIG.<section>.<field>`.
5. Don't add ad-hoc constants back to scripts — extend the config layer.

### Adding per-instance / personal data

Different rule for anything personal: email addresses, customer/partner names,
hostnames, mbox paths, project names mentioned in prompts, etc.

1. Extend `Personal` in `scripts/core/wiki_config.py`.
2. `config.example.yaml` ships an **empty** default for the field — never a real value.
3. The actual value goes in the user's local `config.yaml` (gitignored).
4. Consumers (prompts via `${var}`, compile.py schema enums, scan-* runtime maps) read
   `CONFIG.personal.*` and handle the empty case gracefully.
5. Single source of truth: if a value drives both a prompt AND a schema enum, BOTH read
   from `CONFIG.personal.*` (e.g. `email_folders` drives `compile_curiosity.md` listing
   AND `compile.py`'s schema `enum`). No drift.

### Adding a prompt

1. Drop `<name>.md` into `prompts/`.
2. Use `${var}` for placeholders (not Python's `{var}` — JSON/YAML examples in prompts have literal braces).
3. Call `from prompts import render` and `prompt = render("name", var=value)`.

### Adding an agent target (for hook install)

1. Add a tuple to `WIKI_AGENTS` in `lib/agents.sh`: `name|detection-dir|config-file`.
2. Add `<name>_hooks_payload()` function emitting JSON for that agent's schema.
3. Wire it into `agent_payload()`'s case statement.
4. Status table, install/uninstall flows, and detection logic pick it up automatically.

### Path handling

Scripts use `Path(__file__).resolve().parent` for `SCRIPTS_DIR`, `.parent.parent` for `WIKI_DIR`, `.parent.parent.parent` for the vault root. After `install.sh` clones the repo into `<vault>/.wiki/`, this resolves correctly. Don't hardcode absolute paths.

### Python environment

The Python venv lives at `<vault>/.wiki/.venv/` (inside the engine, NOT at the vault root). `install.sh` runs `uv sync --project <DEST>` so this happens automatically. Two ways to invoke scripts:

- **Interactive** — `cd <vault>/.wiki && uv run python scripts/<X>.py <args>`. Matches all script docstring examples.
- **From any CWD** — `uv run --project <vault>/.wiki python <vault>/.wiki/scripts/<X>.py <args>`. Used by hooks (the `--project` flag is hardcoded in the agent settings.json so the hook works regardless of which directory the user's session was launched from).

`hooks/session-end.py` and `hooks/pre-compact.py` spawn `flush.py` with `--project` for the same reason. Anything that spawns engine scripts from outside `.wiki/` MUST pass `--project`, otherwise `uv` can't find `pyproject.toml`.

### YAML & JSON

- **YAML editing in CLI** → goes through `wiki_config.py set` (Python with PyYAML). Bash never parses YAML.
- **JSON merge for agent configs** → `jq` deep-merge in `lib/agents.sh`. Always backup before write.
- **LLM JSON output** → use `jsonrepair` or schema-constrained decoding (Ollama `format` field). Never raw `JSON.parse`.

### Side effects

- Hooks run in **<10s** budget — no API calls, only file I/O. Heavy work goes to spawned background processes (`flush.py`, piggybacks).
- `compile.py` and `query.py` use the Claude Agent SDK with `model=CONFIG.models.compile_model`. Other scripts use Ollama (configurable via `models.ollama_url`).
- Every config write makes a `.bak.YYYYMMDD-HHMMSS`. Idempotent install/uninstall.

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
