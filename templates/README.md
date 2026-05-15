# Your LLM Wiki

A personal knowledge system that compiles itself. You think; an LLM writes; you read. Sessions, scans, clippings, meetings — all feed one wiki that you and your agents read from daily.

Engine lives in `.wiki/` (hidden from Obsidian by default). Vault content lives here at the root. They never mix on disk.

## Quick start

```bash
# Status, config, hooks, Ollama probe — one command
./.wiki/wiki status

# Update engine from origin/main; preserves config + .env + .venv
./.wiki/wiki update

# Pull new content
./.wiki/wiki collect email                   # mailbox sweep
./.wiki/wiki collect jamie                   # meeting notes from Jamie AI

# Manually compile new sources into knowledge/
./.wiki/wiki compile

# Ask the wiki a question
./.wiki/wiki query "How did I structure the auth layer last quarter?"
```

`wiki help` shows everything. Subcommand help via `wiki <cmd> --help`.

## What runs automatically

Every Claude Code / Codex / Gemini / Cursor session ends as a structured entry in `daily/YYYY-MM-DD/sessions.md` — no action from you. Collectors run alongside and land their own one-liners in sibling files (`daily/YYYY-MM-DD/{health,meetings,voice,email}.md`). Once a day, the `daily-digest` agent distills all five per-source captures into a single ≤500-word `daily/YYYY-MM-DD.md`. After 18:00 (or whatever `scheduling.compile_after_hour` is set to), `flush.py` triggers:

- `compile.py` over any new `raw/` + `daily/` content → atomic articles in `knowledge/`
- Piggyback Collectors (Jamie meetings every 6 h, email daily, screenshot OCR daily, health daily, …)
- `daily_digest_yesterday` piggyback — distills yesterday's per-source captures into one digest
- Quality sweeps: structural lint daily, wiki-quality review weekly
- Curiosity loop — Ollama spots gaps after each compile, queues deep-scan requests

Cap, cooldown, and per-task on/off live in `.wiki/config.yaml`.

## Three folders

```
raw/          ← immutable curated sources (LLM reads, never writes)
daily/        ← per-day rollup: <date>/{sessions,health,meetings,voice,email}.md + <date>.md digest
knowledge/    ← LLM-compiled wiki (LLM owns, you and agents read)
```

- **Don't hand-edit `knowledge/`** — the next compile pass may overwrite. Edit the source in `raw/` and recompile instead.
- **`wiki correct add "TITLE" "TRUTH"`** records a hard fact that overrides any source (good for "X is not Y" / "rename old name to new name" cases).

## Where things live

| What | Path | Tracked? |
|---|---|---|
| Engine code | `.wiki/` | engine git |
| Per-install config (`compile_model`, accounts, account IDs, …) | `.wiki/config.yaml` | gitignored |
| Secrets (API keys, IMAP passwords) | `.claude/.env` | gitignored |
| Env-var catalogue (template) | `.claude/.env.example` | seeded by `wiki seed` |
| Article schema for the compiler | `AGENTS.md` (vault root) | seeded — yours to edit |
| Dashboard | `dashboard.md` (vault root) | seeded — Dataview queries |

Full key-by-key config reference: [`.wiki/docs/config.md`](.wiki/docs/config.md).

## Common operations

```bash
./.wiki/wiki status                            # what's wired and what isn't
./.wiki/wiki update                            # pull engine updates
./.wiki/wiki seed                              # re-apply missing vault templates (additive)
./.wiki/wiki seed --check                      # which templates have drifted from the engine version
./.wiki/wiki config get models.compile_model   # introspect any tunable
./.wiki/wiki config set scheduling.compile_after_hour 20
./.wiki/wiki hooks status                      # which agents are wired
./.wiki/wiki collect --list                    # registered collectors
./.wiki/wiki agent --list                      # agentic-task definitions in prompts/agents/*.md
./.wiki/wiki lint --structural-only            # free vault-health sweep
```

## Provisioning secrets

Copy `.claude/.env.example` to `.claude/.env`, fill values. `.wiki/scripts/core/config.py` loads it on import; no shell-export needed. Shell exports still win if you want a per-run override.

The most common secrets:
- `OPENAI_API_KEY` — Whisper audio transcription
- `JAMIE_<ACCOUNT>_API_KEY` — Jamie AI meeting collector (one per account)
- `IMAP_<ACCOUNT>_USER` / `_PASS` — mailbox writes via the email Collector

## Updating

```bash
./.wiki/wiki update                            # git pull --ff-only + sync skill symlinks
./.wiki/wiki seed --check                      # see if engine templates have moved
./.wiki/wiki seed                              # apply additive template seeds
./.wiki/wiki seed --force                      # overwrite vault templates with engine versions (destructive)
```

`wiki update` never touches `config.yaml`, `.claude/.env`, or `.venv/`. Your customisations survive every pull.

## Going deeper

| Topic | Doc |
|---|---|
| Every `wiki <cmd>` flag | [`.wiki/docs/cli.md`](.wiki/docs/cli.md) |
| Every config key (defaults, types, examples) | [`.wiki/docs/config.md`](.wiki/docs/config.md) |
| What runs when — every data flow in the engine *(German)* | [`.wiki/docs/PROCESS.md`](.wiki/docs/PROCESS.md) |
| The cognitive-architecture argument | [`.wiki/docs/concept.md`](.wiki/docs/concept.md) |
| Engine-internal layout (file by file) | [`.wiki/docs/engine-layout.md`](.wiki/docs/engine-layout.md) |
| Cross-agent conventions for the engine codebase | [`.wiki/AGENTS.md`](.wiki/AGENTS.md) |

---

This file was seeded by `wiki seed`. Edit it freely — the seeder will skip it on subsequent runs and report drift via `wiki seed --check`. Replace with `--force` if you want to revert to the engine default.
