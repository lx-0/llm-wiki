# Engine layout

The engine lives under `<vault>/.wiki/` — hidden from Obsidian's file tree (Obsidian ignores `.`-prefixed directories) and never modified by hand. This doc is the file-by-file reference for contributors and operators who want to see exactly what's inside.

For a higher-level view (vault layout, install, CLI usage), see the [README](../README.md). For development conventions (style, side-effect rules, how to add a tunable / prompt / agent target), see [AGENTS.md](../AGENTS.md).

> **Hard rule — `.venv/` location.** The Python virtualenv lives at `<vault>/.wiki/.venv/`, never at the vault root. `install.sh` runs `uv sync --project <DEST>` precisely to enforce this. A vault-root `.venv/` would leak engine internals into the data layer and break `wiki update` round-trips. If you find one there, delete it and re-run `uv sync --project <vault>/.wiki`.

## Contents

- [Directory tree](#directory-tree)
- [Why bash + python + jq?](#why-bash--python--jq)
- [Where to go next](#where-to-go-next)

## Directory tree

```text
.wiki/
├── wiki                       ← entry point — sources lib/*.sh, dispatches subcommands
├── install.sh                 ← one-liner installer (also re-runnable from a checkout)
├── config.example.yaml        ← tracked  ── │ copy at install time
├── config.yaml                ← gitignored ─┘
├── pyproject.toml + uv.lock
├── lib/
│   ├── common.sh              ← paths, colors, logging, deps, backup
│   ├── ui.sh                  ← interactive prompts (confirm / ask / select_one / select_many)
│   ├── agents.sh              ← agent registry, detection, payload generators, install/uninstall
│   ├── hooks.sh               ← interactive flows for `wiki hooks {install,uninstall,status}`
│   └── config.sh              ← Python config CLI wrapper + setup wizard + interactive editor
├── scripts/
│   ├── core/                  ← shared engine plumbing (imported, never invoked)
│   │   ├── config.py              ← path constants (single source of truth for *_DIR)
│   │   ├── wiki_config.py         ← config dataclass + get/set/keys CLI (incl. Personal block)
│   │   ├── prompts.py             ← prompt template loader (${var} substitution)
│   │   ├── ollama_client.py       ← single Ollama transport (chat / chat_schema / chat_vision)
│   │   ├── sdk_helpers.py         ← StderrCapture + log_sdk_failure + assert_prompt_within_budget (Claude Agent SDK)
│   │   ├── utils.py               ← shared helpers (article listing, JSON state, history)
│   │   ├── agent_spec.py          ← agent-task spec parser (prompts/agents/*.md → AgentSpec)
│   │   └── flush_pipeline.py      ← staged-flush state machine (stage / commit / archive / pending)
│   ├── collectors/            ← substrate→raw/ writers (Registry + scan-* CLIs + dispatcher)
│   │   ├── base.py                ← Collector Protocol, SPEC, Registry
│   │   ├── cli.py                 ← `wiki collect` dispatcher (Registry lookup + run-one)
│   │   ├── email_collector.py     ← email Collector (multi-backend via adapters/mailbox/)
│   │   ├── jamie.py               ← Jamie AI meeting-notetaker
│   │   ├── scan-browser.py        ← Firefox + Chrome bookmarks/history/tab-groups
│   │   ├── scan-calendar.py       ← Thunderbird CalDAV cache → timeline overview
│   │   ├── scan-screenshots.py    ← ~/Screenshots/ + Vision LLM (gemma4) → HOME sidecar + vault thumb (384px) + batch report
│   │   ├── scan-tabs.py           ← Firefox Simple Tab Groups backups
│   │   └── scan-youtube.py        ← yt-dlp + youtube-transcript-api + optional gemma4 visual analysis
│   ├── adapters/              ← MailboxReader implementations consumed by email_collector
│   │   └── mailbox/{gmail,thunderbird,allinkl,base}.py
│   ├── domain/                ← pure domain types (mail message, filter rule)
│   ├── facts/                 ← hard-fact subsystem (knowledge/facts/<slug>.md consumers)
│   │   ├── correct.py             ← CRUD CLI: add/list/remove/edit/path
│   │   └── correct_apply.py       ← agent-driven propagation across vault
│   ├── suggestions/           ← email-suggestion pipeline (raw/suggestions/ producer + executor)
│   │   ├── producer.py            ← maybe_generate_suggestions (called from compile.py)
│   │   ├── cli.py                 ← interactive approve/review/reject/execute
│   │   └── backends/imap.py       ← IMAP move/tag/set-flags executor
│   ├── dashboard/             ← Obsidian dashboard helpers (post-flush + seed-time)
│   │   ├── dashboard_stats.py     ← _dashboard-stats.md generator
│   │   ├── dashboard_lint.py      ← _dashboard-lint.md generator
│   │   ├── agent_buttons.py       ← agent-button discovery + dashboard.md rewriter
│   │   └── inject_daily_button.py ← idempotent Summarize-button injection into daily/*.md
│   ├── migrations/            ← one-shot schema/data migrations
│   │   └── migrate_add_type.py    ← backfill type: frontmatter
│   ├── compile.py             ← Claude Agent SDK compiler (raw/ + daily/ → knowledge/)
│   ├── flush.py               ← session-end → daily/ append + piggyback spawner
│   ├── lint.py                ← 8 structural checks + 1 LLM contradiction check
│   ├── query.py               ← Claude Agent SDK natural-language query (read-only / file-back)
│   ├── agent_task.py          ← generic Claude Agent SDK runner for prompts/agents/*.md
│   ├── clippings_sweep.py     ← <vault>/Clippings/ → raw/articles/ (pre-compile lift)
│   ├── ingest-html.py         ← HTML file or URL → text + visual (Playwright + Vision LLM)
│   ├── process-inbox.py       ← <vault>/inbox/ → classify + move to raw/ subfolder
│   ├── review-wiki.py         ← per-article quality scoring via local LLM
│   ├── optimize-claude-md.py  ← cross-project pattern → ~/.claude/CLAUDE.md edits
│   ├── retry-failed-flushes.py ← reprocess archived flush contexts
│   ├── pin.py                 ← `wiki pin <article>` — append wikilink to a MOC section (no LLM)
│   └── health.py              ← read-only colored ASCII vault dashboard
├── hooks/
│   ├── _transcript.py         ← shared transcript walker + tool summarizer
│   ├── session-start.py       ← inject index.md into next session's context
│   ├── session-end.py         ← spawn flush.py with the conversation transcript
│   └── pre-compact.py         ← safety-net flush before context compaction
├── prompts/                   ← LLM prompts as standalone .md files
├── templates/                 ← seeded into <vault>/ on install (never overwritten)
│   ├── AGENTS.example.md
│   ├── dashboard.md
│   └── .obsidian/{community,core}-plugins.json
├── skills/                    ← engine skills (symlinked into <vault>/.claude/skills/)
│   ├── engine-pr/SKILL.md
│   ├── excalidraw-diagram/SKILL.md
│   ├── ingest-audio/SKILL.md
│   ├── use-llm-wiki/SKILL.md   ← global-eligible: also links into ~/.claude/skills/
│   ├── vault-health-check/SKILL.md
│   └── vault-triage/SKILL.md
└── (gitignored runtime)
    ├── .venv/                 ← uv-managed Python environment
    ├── state/                 ← *.json hash trackers, dedup, cooldowns
    ├── logs/                  ← flush.log + flush-errors.log (WARNING+), compile.log (full stderr-mirror) + compile-errors.log (WARNING+)
    ├── sessions/              ← session-flush staging + failed-flushes/
    └── reports/               ← lint + review-wiki output
```

## Why bash + python + jq?

- **bash** for UI and orchestration — selection menus, scope choice, multi-target install.
- **python** for YAML parsing and config invariants — dataclass-backed, type-coerced, validated.
- **jq** for JSON merge of agent configs — preserves the user's existing hooks instead of clobbering them.

No yaml-in-bash, no json-in-python. Each tool does what it's good at.

## Where to go next

| If you want to… | Go to |
|---|---|
| Add a new agent target (Cursor-like, with hooks) | [AGENTS.md → Adding an agent target](../AGENTS.md#adding-an-agent-target-for-hook-install) |
| Add a tunable to `config.yaml` | [AGENTS.md → Adding a tunable](../AGENTS.md#adding-a-tunable) |
| Add an LLM prompt template | [AGENTS.md → Adding a prompt](../AGENTS.md#adding-a-prompt) |
| Understand the data flows (compile, flush, scanners, curiosity loop) | [docs/PROCESS.md](PROCESS.md) |
| Understand the design rationale (compile-vs-RAG, three layers, cognitive functions) | [docs/concept.md](concept.md) |
| See the architecture as a diagram | [docs/architecture.png](architecture.png) |
| Read locked architectural decisions | [.ytstack/DECISIONS.md](../.ytstack/DECISIONS.md) |
| Read hard-won engine learnings (Ollama gotchas, rate limits, anti-patterns) | [.ytstack/KNOWLEDGE.md](../.ytstack/KNOWLEDGE.md) |
