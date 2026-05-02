# llm-wiki

An implementation of [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — a personal knowledge base where:

- **`raw/`** holds immutable sources (memories, emails, notes, screenshots, transcripts)
- **`knowledge/`** holds LLM-compiled wiki articles (concepts, connections, people, projects, qa)
- **`.wiki/`** is this tooling layer: CLI, hooks, scripts, prompts, config

Compile-once, query-fast. No retrieval at every query — knowledge is distilled into Markdown wikilinks during compile.

## What's inside

- `wiki` — single-entry CLI (interactive + scriptable). `wiki setup`, `wiki config`, `wiki hooks`, `wiki status`, `wiki update`.
- `scripts/` — Python tools: `compile.py`, `flush.py`, `lint.py`, `query.py`, `scan-{email,calendar,browser,screenshots}.py`, `process-inbox.py`, `optimize-claude-md.py`, `review-wiki.py`, `retry-failed-flushes.py`, `sync-memories.py`.
- `hooks/` — session lifecycle hooks (Claude Code / Codex / Gemini / Cursor).
- `prompts/` — LLM prompt templates as standalone `.md` files (one per use case).
- `lib/` — bash modules that compose the CLI.
- `config.example.yaml` — copy to `config.yaml` to override defaults.
- `docs/` — design concept, architecture diagram (Excalidraw), implementation plans.

> **Documentation language.** Most repo docs are English (`README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/concept.md`, `docs/naming.md`, `.ytstack/*`). **`docs/PROCESS.md` is in German** — it's the live documentation of every data flow inside the engine. Pull requests that touch a flow should keep the existing prose language; bilingual is fine, and Mermaid labels / table headers in English are encouraged so the diagrams remain accessible to non-German readers.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/lx-0/llm-wiki/main/install.sh | bash
# or with explicit target:
curl -fsSL https://raw.githubusercontent.com/lx-0/llm-wiki/main/install.sh | bash -s -- ~/path/to/vault
```

The installer clones into `<target>/.wiki/`, seeds `config.yaml` from `config.example.yaml`, and runs `uv sync` so the venv lives at `<target>/.wiki/.venv/`. Everything engine-related stays inside `.wiki/` — the vault root stays clean.

**Prerequisites:** `bash` ≥ 4, `git`, `jq`, `uv` (Python package manager).

After install:

```bash
cd ~/path/to/vault
./.wiki/wiki setup        # 5-question config wizard + agent hook install
./.wiki/wiki status       # verify
```

## Update

```bash
./.wiki/wiki update       # pulls latest from the repo, preserves config.yaml + venv
```

## Running scripts manually

The venv lives inside `.wiki/`. Two equivalent ways to invoke any script:

```bash
# Option A — cd into .wiki first (matches script docstrings)
cd ~/path/to/vault/.wiki
uv run python scripts/compile.py

# Option B — pin --project from any CWD
uv run --project ~/path/to/vault/.wiki python ~/path/to/vault/.wiki/scripts/compile.py
```

Hooks always use Option B (the project flag is hardcoded into the agent config).

## Security

Secrets-leak prevention runs on two layers:

- **CI** ([.github/workflows/secrets-scan.yml](.github/workflows/secrets-scan.yml)) — gitleaks scans every push + PR + nightly cron. Blocks merge if leaks are found.
- **Pre-commit** ([.pre-commit-config.yaml](.pre-commit-config.yaml)) — local hooks block leaks before they reach git. Install once:

  ```bash
  pip install pre-commit && pre-commit install
  ```

Gitleaks rules + allowlist live in [.gitleaks.toml](.gitleaks.toml). Run a manual scan: `gitleaks detect --no-banner -v`.

If you find a leak in history, rotate the secret immediately, then file an issue (don't post the leaked value).

---

## CLI Reference

Operational layer for an LLM Wiki vault. Hidden from Obsidian's file tree.

## Quick start

```bash
./.wiki/wiki                  # interactive top-level menu
./.wiki/wiki setup            # first-time: config wizard + hooks install
./.wiki/wiki status           # full system status (config + hooks + Ollama probe)
./.wiki/wiki help             # top-level usage
./.wiki/wiki config --help    # config subcommands
./.wiki/wiki hooks --help     # hooks subcommands
```

## Subcommand cheat sheet

| Command | What it does |
|---|---|
| `wiki` | interactive top-level menu |
| `wiki setup [--help]` | first-time wizard: config + hook install |
| `wiki status` | config summary, hook install table, Ollama probe |
| `wiki config` | interactive editor — pick section → pick key → enter value |
| `wiki config get KEY` | print one value |
| `wiki config set KEY VALUE` | set + write back to `config.yaml` |
| `wiki config keys` | list all settable keys (dot-notation) |
| `wiki config path` | absolute path to `config.yaml` |
| `wiki config wizard` | re-run the 5-question wizard |
| `wiki config status` | summary table |
| `wiki hooks install` | install into selected agents (claude / codex / gemini / cursor) |
| `wiki hooks uninstall` | remove wiki-managed hooks |
| `wiki hooks status` | install table per agent / scope |

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
features.procmail_execution            bool — All-Inkl Webmail Procmail API calls (default OFF)

limits.compile_max_files               int — per-run cap (rate-limit guard)
limits.compile_max_consecutive_failures int — abort after N back-to-back failures
limits.flush_max_retries               int
limits.flush_retry_delay_seconds       int
limits.screenshot_resize_width         px
limits.screenshot_timeout_seconds      seconds
limits.curiosity_max_gaps              int — max requests per compile
limits.curiosity_min_source_chars      int — skip curiosity for tiny sources
limits.sparse_threshold_words          int — lint warns under this word count

piggybacks.<task>.enabled              bool — disable to never spawn
piggybacks.<task>.cooldown_hours       int — 24 = daily, 168 = weekly
piggybacks.<task>.max_per_run          int (where applicable)

graph_view.mode                        knowledge-only | full-vault | sources-only | custom
graph_view.custom_search               obsidian search string (when mode=custom)

# Per-instance personal data — drives compile prompts, scan-email, scan-calendar,
# thunderbird-rules, execute-suggestions. Lives in config.yaml only (gitignored);
# config.example.yaml ships empty defaults.
personal.primary_account               account-id used as default in prompts + fallback in compile.py
personal.thunderbird_profile           absolute path; empty disables scan-email + thunderbird-rules
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
| cursor | `.cursor/hooks.json` | — | stop | — |

Install scope:
- **project** (default) — `<repo>/<.agent>/...` — only when CWD is this repo
- **user** — `~/<.agent>/...` — always

Not supported: **pi** (TS-only modules), **opencode** (no native hooks yet, [issue #5409](https://github.com/sst/opencode/issues/5409)).

## Files

```text
.wiki/
├── wiki                  ← entry point — sources lib/*.sh, dispatches subcommands
├── config.yaml           ← single source of truth (see "Config keys" above)
├── README.md             ← this file
├── lib/
│   ├── common.sh         ← paths, colors, logging, deps, backup
│   ├── ui.sh             ← interactive prompts (confirm / ask / select_one / select_many)
│   ├── agents.sh         ← agent registry, detection, payload generators, install/uninstall
│   ├── hooks.sh          ← interactive flows for `wiki hooks {install,uninstall,status}`
│   └── config.sh         ← wraps Python config CLI + setup wizard + interactive editor
├── scripts/
│   ├── wiki_config.py    ← config loader + CLI (get/set/keys/path)
│   ├── prompts.py        ← prompt loader (renders .md templates with ${var} subst)
│   └── ...               ← compile.py, flush.py, lint.py, scan-*.py, query.py, etc.
├── hooks/                ← agent session hooks (Python)
│   ├── session-start.py
│   ├── session-end.py
│   └── pre-compact.py
├── prompts/              ← LLM prompts as standalone .md files
└── reports/              ← lint + review-wiki output (gitignored)
```

## Adding a new agent target

1. Add a tuple to `WIKI_AGENTS` in [lib/agents.sh](lib/agents.sh): `name|detection-dir|config-file`.
2. Add a payload generator function `<name>_hooks_payload` that emits JSON for that agent's schema.
3. Wire it into `agent_payload()`'s case statement.
4. Done. The status table, install/uninstall flows, and detection logic pick it up automatically.

## Adding a new config key

1. Extend the matching dataclass in [scripts/wiki_config.py](scripts/wiki_config.py).
2. Document the default in `config.yaml` with a comment.
3. Replace the hardcoded constant in the script with `CONFIG.<section>.<field>`.
4. The Python `keys` CLI auto-discovers it; `wiki config get/set` works without further changes.

## Why bash + python?

- bash for **UI and orchestration** — selection menus, scope choice, multi-target install.
- python for **YAML parsing and config invariants** — dataclass-backed, type-coerced, validated.
- jq for **JSON merge** of agent configs — preserves user's existing hooks.

No yaml-in-bash, no json-in-python. Each tool does what it's good at.
